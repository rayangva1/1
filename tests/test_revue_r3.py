"""Régressions de la revue adverse, 3ᵉ passe (code) : chaque test échouait sur le code d'avant correctif.

Cause commune : des routes d'écriture n'appelaient que ``require_api`` ; le jeton commun (non attribuable) et
n'importe quel jeton nommé pouvaient déposer des valeurs décisives. Correctif systémique : matrice
d'autorisations explicite et versionnée (:mod:`pokeshop.authz`), refus par défaut, jetons nommés par rôle.

* SEC-16 : toute route est dans la matrice ; aucune écriture ouverte au jeton commun ; route hors matrice refusée.
* SEC-09 (a/b), R2-NEW-02 : identifiants, statut et prix publiés viennent du registre du moteur ; dépublication
  d'une référence bloquée même sans offre du jour ; jamais de « prix courant » déclaré.
* R2-NEW-05 : validations humaines de fiche par la propriétaire seulement, liées au contenu.
* R2-NEW-01 : coûts historiques adossés à une réception physique d'un autre jeton ; écart de facture > 2 % :
  propriétaire ; déposants des coûts et de la publicité dans le contrôle du mandat.
* R2-NEW-03 : activité publicitaire du connecteur seulement, en ajout seul ; MAX avec les paiements exécutés.
* R2-NEW-04, MOT-18 : étoile polaire dérivée de commandes enregistrées (logistique réelle) ; montants négatifs
  référencés ; écriture manuelle : propriétaire.
* NEW-01 : test d'incident réussi attesté par qa-conformite (ou la propriétaire) sur un cycle réel pertinent.
* R2-ADV-01 : point zéro posé avec la première photo, de façon atomique.
Données, jetons et montants FICTIFS.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jetons_roles as JR
import pytest
import test_api as A
import test_orchestration_f4 as F
import test_sync as S
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pokeshop import authz
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.catalogue_sync import SyncRunSummary
from pokeshop.incidents import IncidentCode, LogNotifier
from pokeshop.mandate import SpendCategory, SpendStatus
from pokeshop.northstar import ContributionEntry, NorthStarError, NorthStarLedger, Post
from pokeshop.publish import PlanOutcome, PublishBlocker, ShopStatus, build_publication
from pokeshop.settings import ROLE_TOKEN_VARIABLES, load_settings
from pokeshop.stoploss import AdSpend, ProductMargin
from pokeshop.stoploss_snapshot import UNASSIGNED_CAMPAIGN, executed_ad_payments, merge_ad_spends
from pokeshop.sync import ShopPublication

ROOT = Path(__file__).resolve().parents[1]
NOW = F.NOW
H, HO = F.H, F.HO


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "FICTIF-X", path)


# =============================================================================== SEC-16 : matrice


def all_routes(app: Any) -> set[tuple[str, str]]:
    """(méthode, gabarit) de toutes les routes de l'application, routeurs inclus (schéma OpenAPI)."""
    routes = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}
    routes |= {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}
    return routes


def test_sec16_every_route_is_in_the_matrix_and_no_write_is_open_to_the_common_token(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    app = client.app
    assert not [r for r in app.routes if not isinstance(r, APIRoute) and type(r).__name__ != "_IncludedRouter"]
    routes = all_routes(app)
    assert routes, "aucune route trouvée"
    missing = sorted(routes - set(authz.ROUTE_MATRIX))
    assert not missing, f"routes hors matrice : {missing}"
    assert not sorted(set(authz.ROUTE_MATRIX) - routes), "entrée de matrice sans route"
    for (method, path), rule in authz.ROUTE_MATRIX.items():
        if method != "GET":
            assert rule.kind in (authz.Kind.WRITE, authz.Kind.PREVIEW), (method, path)
        if rule.kind is authz.Kind.WRITE:
            assert not rule.common and not authz.allowed(rule, role=None, owner=False), (method, path)
            assert rule.roles <= authz.KNOWN_ROLES and (rule.roles or rule.owner), (method, path)
    previews = {k for k, r in authz.ROUTE_MATRIX.items() if r.kind is authz.Kind.PREVIEW}
    assert previews == {("POST", "/pricing/quote"), ("POST", "/pricing/basket"), ("POST", "/stock/sellable"),
                        ("POST", "/publish/preview")}  # aperçus sans écriture d'état


@pytest.mark.parametrize(("method", "path"), sorted(k for k, r in authz.ROUTE_MATRIX.items() if r.kind is authz.Kind.WRITE))
def test_sec16_common_token_is_refused_on_every_write_route(tmp_path: Path, method: str, path: str) -> None:
    client, svc, _ = F.boot(tmp_path)
    resp = client.request(method, concrete(path), headers=H, json={})
    assert resp.status_code == 403, (path, resp.text)
    rule = authz.ROUTE_MATRIX[(method, path)]
    action = f"{rule.audit}.owner_token_refused" if rule.owner_only else f"{rule.audit}.common_token_refused"
    assert svc.audit.events(action=action), action


@pytest.mark.parametrize(("method", "path"), sorted(k for k, r in authz.ROUTE_MATRIX.items()
                                                    if r.kind is authz.Kind.WRITE and r.roles != authz.ALL_NAMED))
def test_sec16_a_role_outside_the_matrix_is_refused(tmp_path: Path, method: str, path: str) -> None:
    client, _, _ = F.boot(tmp_path)
    rule = authz.ROUTE_MATRIX[(method, path)]
    outsider = next(r for r in sorted(authz.KNOWN_ROLES) if r not in rule.roles)
    resp = client.request(method, concrete(path), headers=JR.headers(outsider), json={})
    assert resp.status_code == 403, (outsider, path, resp.text)


def test_sec16_deny_by_default_for_a_route_absent_from_the_matrix(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)

    @client.app.post("/route-temoin-hors-matrice")
    def temoin() -> dict[str, bool]:  # pragma: no cover - jamais atteinte
        return {"atteinte": True}

    resp = client.post("/route-temoin-hors-matrice", headers=HO, json={})
    assert resp.status_code == 403 and "matrice" in body(resp)["erreur"]
    assert svc.audit.events(action="authz.route_refused")
    for docs in ("/openapi.json", "/docs", "/redoc"):  # aucune documentation interactive exposée
        assert client.get(docs).status_code == 404


def test_sec16_reads_and_previews_stay_open_to_the_common_token(tmp_path: Path) -> None:
    client, _, _ = F.boot(tmp_path)
    for (method, path), rule in authz.ROUTE_MATRIX.items():
        if rule.kind is authz.Kind.READ and "{" not in path:
            assert client.request(method, path, headers=H).status_code not in (401, 403), path
    assert client.post("/pricing/quote", headers=H, json={"cost_chf": "140"}).status_code == 200


def test_sec16_token_names_are_roles_and_per_role_variables_are_read() -> None:
    assert set(ROLE_TOKEN_VARIABLES) == authz.KNOWN_ROLES
    assert set(authz.AGENT_ROLES) == {p.stem for p in (ROOT / ".claude" / "agents").glob("*.md")}
    cfg = load_settings({ROLE_TOKEN_VARIABLES["qa-conformite"]: "a" * 64, ROLE_TOKEN_VARIABLES["n8n-07-stoploss"]: "b" * 64})
    assert cfg.agent_tokens_sha256 == {"qa-conformite": "a" * 64, "n8n-07-stoploss": "b" * 64}
    assert cfg.api_token_sha256 is None  # jeton commun facultatif


def test_sec16_matrix_document_is_generated_from_the_code() -> None:
    doc = (ROOT / "docs" / "08-agents" / "MATRICE_API.md").read_text(encoding="utf-8")
    assert doc == authz.matrix_markdown(), "régénérer : python -m pokeshop.authz > docs/08-agents/MATRICE_API.md"


# =============================================================================== SEC-09 / R2-NEW-02


def published(env: Any, *, status: str = "ACTIVE", price: D | None = D("160.00")) -> None:
    env.sync.publications.record(ShopPublication(product_id="FICTIF-P1", shopify_product_id="gid://shopify/Product/7",
                                                 status=status, handle="display-fictif", run_id="SYNC-FICTIF-0",
                                                 recorded_at=S.SOURCE_NOW - timedelta(days=1), price_chf=price))  # fmt: skip


def quarantine(env: Any) -> None:
    env.incidents.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix publié anormal (test)",
                       actor="qa-conformite")  # fmt: skip
    env.state = S.healthy_state(env.now, products=(ProductMargin(product_key="FICTIF-P1", contribution_chf=D("3"),
                                                                 contribution_pct=D("0.03")),))  # fmt: skip
    env.gate.invalidate()


def test_sec09a_registry_state_wins_over_anything_in_the_listing() -> None:
    """Fiche « gid + DRAFT périmé » impossible : le registre dit ACTIVE => dépublication (charge statut seul)."""
    env = S.Env()
    published(env)
    quarantine(env)
    p1 = S.item_for(env.cycle(S.context(approved=True), dry_run=False))
    assert p1.plan_outcome == PlanOutcome.UNPUBLISH.value and p1.written
    assert env.shop.applied[-1] == {"productSet": {"status": "DRAFT"}}
    assert env.sync.publications.get("FICTIF-P1").status == "DRAFT"
    assert env.sync.publications.get("FICTIF-P1").price_chf == D("160.00")  # dernier prix publié conservé


def test_sec09b_blocked_reference_without_offer_today_is_unpublished(tmp_path: Path) -> None:
    env = S.Env()
    first = S.item_for(env.cycle(S.context(), dry_run=False))
    assert first.written and env.sync.publications.get("FICTIF-P1").status == "ACTIVE"
    quarantine(env)
    lines = S.CSV_A.read_text(encoding="utf-8").splitlines()
    without = tmp_path / "FICTIF_offres_sans_A001.csv"
    without.write_text("\n".join(ln for ln in lines if ";2000000001012;" not in ln) + "\n", encoding="utf-8")
    report = env.cycle(S.context(), dry_run=False, source=without)
    p1 = S.item_for(report)
    assert p1.match_status == "SANS_OFFRE" and p1.plan_outcome == PlanOutcome.UNPUBLISH.value and p1.written
    assert env.shop.applied[-1] == {"productSet": {"status": "DRAFT"}}


def test_r2new02_rejected_engine_price_falls_back_to_the_last_published_price_only() -> None:
    """Prix du moteur écarté (REVIEW, DRAFT, plafond) : dernier prix publié du registre, jamais un prix déclaré."""
    fiche = S.listing()
    validations = S.owner_validations(fiche, approved=True)
    state = ShopPublication(product_id="FICTIF-P1", shopify_product_id="gid://shopify/Product/7", status="ACTIVE",
                            handle="h", run_id="r", recorded_at=S.SOURCE_NOW, price_chf=D("160.00")).state()  # fmt: skip
    params = S.RULES.pricing
    for decision in (S.decide_price(D("100"), params, market_ref=D("120")),  # REVIEW
                     S.decide_price(D("100"), params, unknown_fields=["customs_and_fees"]),  # DRAFT
                     None):
        plan = build_publication(fiche, decision, max_daily_change=params.max_daily_price_change, params=params,
                                 now=S.SOURCE_NOW, published=state, validations=validations, table=S.TABLE)  # fmt: skip
        assert plan.price_chf == D("160.00") and plan.price_source == "UNCHANGED", decision
        assert plan.product_input["variants"][0]["price"] == "160.00"
    unknown = build_publication(fiche, None, max_daily_change=params.max_daily_price_change, params=params,
                                now=S.SOURCE_NOW, published=state.model_copy(update={"price_chf": None}),
                                validations=validations, table=S.TABLE)  # fmt: skip
    assert unknown.outcome is PlanOutcome.NOT_SENT and unknown.price_chf is None  # rien n'est publié actif
    stale = build_publication(fiche, S.decide_price(D("150"), params, unknown_fields=["x"]),
                              max_daily_change=params.max_daily_price_change, params=params, now=S.SOURCE_NOW,
                              published=state, validations=validations, table=S.TABLE)  # fmt: skip
    assert PublishBlocker.PUBLISHED_PRICE_BELOW_FLOOR.value in stale.reviews and stale.outcome is PlanOutcome.NOT_SENT


def test_r2new02_price_cap_with_registry_price_never_sends_a_declared_price() -> None:
    """PoC p1b : historique 160, plafond dépassé => renvoi à 160 (registre), jamais 1.00."""
    env = S.Env()
    published(env, price=D("160.00"))
    env.history.publish("FICTIF-P1", D("160.00"), S.SOURCE_NOW - timedelta(days=2), "engine", validated=True)
    p1 = S.item_for(env.cycle(S.context(approved=True), dry_run=False))
    assert p1.action == "UPDATE_APPROVED_PRODUCT" and p1.price_chf == D("160.00")  # registre, jamais 1.00
    assert "DAILY_CHANGE_ABOVE_CAP" in p1.decision_reasons
    sent = [a["productSet"] for a in env.shop.applied if "productSet" in a]
    assert all(v.get("variants", [{}])[0].get("price", "160.00") != "1.00" for v in sent)


@pytest.mark.parametrize("field", ["current_price_chf", "shopify_product_id", "shopify_status", "shopify_inventory_item_id",
                                   "approved", "category_rule_validated", "content_validated"])
def test_r2new02_r2new05_engine_and_human_fields_are_refused_on_input(tmp_path: Path, field: str) -> None:
    client, _, _ = F.boot(tmp_path)
    value = {"current_price_chf": "1.00", "shopify_product_id": "gid://shopify/Product/7", "shopify_status": "DRAFT",
             "shopify_inventory_item_id": "gid://shopify/InventoryItem/1"}.get(field, True)
    listing = {**F.LISTING, field: value}
    item = client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": listing}]})
    assert item.status_code == 422, item.text
    sync = client.post("/sync/run", headers=JR.HSYNC, json={**F.N8N_SYNC_BODY, "catalog": [{"product_id": "FICTIF-P1",
                                                                                              "listing": listing}]})
    assert sync.status_code == 422


# =============================================================================== R2-NEW-05


def test_r2new05_human_validations_come_only_from_the_owner_and_follow_the_content(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 6,
                                                                "ref": "FICTIF-BL-1"}).status_code == 200
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1",
                                                                           "listing": F.LISTING}]}).status_code == 200
    approval = {"product_id": "FICTIF-P1", "category_rule_validated": True, "content_validated": True,
                "reason": "règle de catégorie FICTIVE validée"}
    for role in ("catalogue", "qa-conformite", "chef-de-projet"):  # catalogue ne valide pas ses propres fiches
        assert client.post("/catalog/approvals", headers=JR.headers(role), json=approval).status_code == 403, role
    assert client.post("/catalog/approvals", headers=H, json=approval).status_code == 403
    preview = {"listing": F.LISTING, "quote": {"cost_chf": "100.00"}}
    assert body(client.post("/publish/preview", headers=H, json=preview))["plan"]["outcome"] == "SEND_DRAFT"
    created = client.post("/catalog/approvals", headers=HO, json=approval)
    assert created.status_code == 201 and svc.audit.events(action="catalog.approval")
    assert body(client.post("/publish/preview", headers=H, json=preview))["plan"]["outcome"] == "SEND_ACTIVE"
    # l'agent catalogue modifie la fiche après validation : elle n'est plus validée
    edited = {**F.LISTING, "description_html": "<p>Description réécrite après validation (FICTIF).</p>"}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1",
                                                                           "listing": edited}]}).status_code == 200
    plan = body(client.post("/publish/preview", headers=H, json={**preview, "listing": edited}))["plan"]
    assert plan["outcome"] == "SEND_DRAFT" and "VALIDATION_OUTDATED" in plan["reviews"]
    stale = client.post("/catalog/approvals", headers=HO, json={**approval, "listing_sha256": "0" * 64})
    assert stale.status_code == 409  # fiche modifiée depuis l'examen de la propriétaire
    _, svc2, _ = F.boot(tmp_path)
    assert svc2.catalog_approvals.get("FICTIF-P1").category_rule_validated  # persisté


# =============================================================================== R2-NEW-01


def cash_registers(client: TestClient, *, capital: str = "4200", paypal: str = "1000", bank: str = "2000") -> None:
    movement = {"movement_id": "FICTIF-APPORT-1", "at": (NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
                "amount": capital}
    assert client.post("/capital/movements", headers=HO, json=movement).status_code == 201
    for path, amount in (("/treasury/paypal-balance", paypal), ("/treasury/bank-balance", bank)):
        reading = {"as_of": (NOW - timedelta(minutes=10)).isoformat(), "balance_chf": amount, "source": "relevé FICTIF"}
        assert client.post(path, headers=JR.HTRES, json=reading).status_code == 200
    balances = {"as_of": (NOW - timedelta(minutes=10)).isoformat(), "preorders_collected_chf": "0",
                "source": "déclaration FICTIVE : aucune dette"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=balances).status_code == 200


def test_r2new01_phantom_receipt_never_reaches_the_photo(tmp_path: Path) -> None:
    """PoC p2 : apport 4 200, cash 3 000 => gel ; une réception fantôme (100 × 50) ne lève plus le gel."""
    client, svc, _ = F.boot(tmp_path)
    cash_registers(client)
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1",
                                                                           "listing": F.LISTING}]}).status_code == 200
    honest = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert honest["status"]["global_frozen"] is True
    phantom = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": (NOW - timedelta(days=1)).isoformat(),
               "ref": "FICTIF-LOT-FANTOME", "qty": 100, "unit_cost": "50"}
    assert client.post("/costs/movements", headers=H, json=phantom).status_code == 403  # jeton commun
    assert client.post("/costs/movements", headers=JR.HOPS, json=phantom).status_code == 403  # autre rôle
    assert client.post("/costs/movements", headers=JR.HF, json=phantom).status_code == 422  # sans référence
    refs = {**phantom, "stock_ref": "FICTIF-BL-FANTOME", "invoice_ref": "FICTIF-FACT-1"}
    refused = client.post("/costs/movements", headers=JR.HF, json=refs)
    assert refused.status_code == 409 and "POST /stock/receive" in body(refused)["erreur"]
    assert svc.audit.events(action="costs.movement_refused") and svc.costs.movements() == ()
    # réception réelle de 6 unités : la quantité au coût doit être la même
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 6,
                                                                "ref": "FICTIF-BL-1"}).status_code == 200
    assert client.post("/costs/movements", headers=JR.HF, json={**refs, "stock_ref": "FICTIF-BL-1"}).status_code == 409
    again = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert again["status"]["global_frozen"] is True and svc.stoploss_state.net_worth.stock == ()


def test_r2new01_invoice_gap_above_two_percent_awaits_the_owner_and_cost_posters_are_checked(tmp_path: Path) -> None:
    """PoC p2b : INVOICE_ADJUSTMENT à 40 sur un lot à 101 => refusé (propriétaire) ; marge produit inchangée."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)  # lot FICTIF-LOT-1 : 6 × 101.2345, adossé à FICTIF-BL-1
    adjust = {"kind": "INVOICE_ADJUSTMENT", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-FACT-2",
              "lot_id": "FICTIF-LOT-1", "unit_cost": "40.00", "invoice_ref": "FICTIF-FACT-2"}
    assert client.post("/costs/movements", headers=JR.HF, json={k: v for k, v in adjust.items() if k != "invoice_ref"}).status_code == 422
    gap = client.post("/costs/movements", headers=JR.HF, json=adjust)
    assert gap.status_code == 403 and "propriétaire" in body(gap)["erreur"]
    owner = client.post("/costs/movements", headers=HO, json=adjust)
    assert owner.status_code == 200  # la propriétaire inscrit l'écart signalé
    # second lot, écart < 2 % : l'agent finance l'inscrit lui-même
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 2,
                                                                "ref": "FICTIF-BL-2"}).status_code == 200
    lot2 = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-LOT-2", "qty": 2,
            "unit_cost": "100.00", "stock_ref": "FICTIF-BL-2", "invoice_ref": "FICTIF-FACT-L2"}
    assert client.post("/costs/movements", headers=JR.HF, json=lot2).status_code == 200
    small = {**adjust, "lot_id": "FICTIF-LOT-2", "unit_cost": "101.50", "ref": "FICTIF-FACT-4", "invoice_ref": "FICTIF-FACT-4"}
    assert client.post("/costs/movements", headers=JR.HF, json=small).status_code == 200
    assert svc.costs.posters() == {"finance-pricing", "propriétaire"}


def test_r2new01_spender_who_posted_costs_is_not_verifiable(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    assert client.post("/stoploss/state/refresh", headers=JR.HPHOTO).status_code == 200
    spend = {"request": {"amount": "40", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                         "payment_method": "PAYPAL", "purpose": "Étuis FICTIFS", "idempotency_key": "FICTIF-R3-1",
                         "requested_by": "finance-pricing", "requested_at": NOW.isoformat(), "amount_source": "devis"}}
    data = body(client.post("/mandate/check", headers=JR.HF, json=spend))
    assert "Stock au coût historique" in data["unverified"]  # finance a déposé les coûts : non vérifiable
    ops = body(client.post("/mandate/check", headers=JR.HOPS, json={"request": {**spend["request"], "requested_by": "operations-sav",
                                                                                "idempotency_key": "FICTIF-R3-2"}}))
    assert "Stock au coût historique" not in ops["unverified"]


# =============================================================================== R2-NEW-03


def test_r2new03_ads_register_is_append_only_and_owned_by_the_connector(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    days = [(NOW - timedelta(days=i)).date().isoformat() for i in range(3)]
    spends = {"ad_spends": [{"campaign_id": "FICTIF-CAMP-1", "day": d, "amount": "100"} for d in days]}
    assert client.post("/ads/activity", headers=H, json=spends).status_code == 403
    assert client.post("/ads/activity", headers=JR.HACQ, json=spends).status_code == 403  # l'agent qui dépense
    assert client.post("/ads/activity", headers=JR.HADS, json=spends).status_code == 200
    zero = {"ad_spends": [{"campaign_id": "FICTIF-CAMP-1", "day": d, "amount": "0"} for d in days]}
    erased = client.post("/ads/activity", headers=JR.HADS, json=zero)
    assert erased.status_code == 409 and "baisse" in body(erased)["erreur"]
    higher = {"ad_spends": [{"campaign_id": "FICTIF-CAMP-1", "day": days[0], "amount": "120"}]}
    assert client.post("/ads/activity", headers=JR.HADS, json=higher).status_code == 200
    fake = {"attributed_orders": [{"order_id": "FICTIF-INVENTEE", "campaign_id": "FICTIF-CAMP-1",
                                   "paid_at": NOW.isoformat(), "contribution_before_acquisition": "500"}]}
    unknown = client.post("/ads/activity", headers=JR.HADS, json=fake)
    assert unknown.status_code == 409 and "inconnue du moteur" in body(unknown)["erreur"]
    F.seed_stock(client, svc)
    order = {"order_id": "FICTIF-O1", "paid_at": (NOW - timedelta(hours=2)).isoformat(), "net_sales_ht": "60.00",
             "payment_fees": "1.80", "shipping_cost_actual": "8.20", "shipping_label_ref": "FICTIF-ETIQ-1",
             "source": "Shopify FICTIF", "lines": F.ORDER_LINES}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order).status_code == 201
    capped = {"attributed_orders": [{**fake["attributed_orders"][0], "order_id": "FICTIF-O1"}]}
    assert client.post("/ads/activity", headers=JR.HADS, json=capped).status_code == 200
    _, attributed = svc.ads.window((NOW - timedelta(days=7)).date())
    assert attributed[0].contribution_before_acquisition == D("50.00")  # 60 − 1.80 − 8.20 : jamais 500
    assert svc.ads.posters() == {"connecteur-publicite"}


def test_r2new03_stoploss_retains_the_max_of_declaration_and_executed_payments(tmp_path: Path) -> None:
    """La dépense pub retenue n'est jamais sous les paiements pub exécutés du registre du mandat."""
    client, svc, _ = F.boot(tmp_path)
    paid = SimpleNamespace(request=SimpleNamespace(category=SpendCategory.ADVERTISING, campaign_id="FICTIF-CAMP-1"),
                           status=SpendStatus.EXECUTED, executed_at=NOW - timedelta(hours=1), executed_amount_chf=D("300"))
    orphan = SimpleNamespace(request=SimpleNamespace(category=SpendCategory.ADVERTISING, campaign_id=None),
                             status=SpendStatus.EXECUTED, executed_at=NOW - timedelta(days=1), executed_amount_chf=D("25"))
    pending = SimpleNamespace(request=SimpleNamespace(category=SpendCategory.ADVERTISING, campaign_id="FICTIF-CAMP-1"),
                              status=SpendStatus.APPROVED, executed_at=None, executed_amount_chf=None)
    executed = executed_ad_payments([paid, orphan, pending], NOW.tzinfo)
    assert executed == {("FICTIF-CAMP-1", NOW.date()): D("300"), (UNASSIGNED_CAMPAIGN, (NOW - timedelta(days=1)).date()): D("25")}
    declared = [AdSpend(campaign_id="FICTIF-CAMP-1", day=NOW.date(), amount=D("0"))]
    merged = merge_ad_spends(declared, executed, until=NOW.date())
    assert {(s.campaign_id, s.amount) for s in merged} == {("FICTIF-CAMP-1", D("300")), (UNASSIGNED_CAMPAIGN, D("25"))}
    # API : le connecteur déclare 0, le mandat a payé 300 => stop-loss pub déclenché quand même.
    svc.spend_ledger.entries = lambda: (paid,)  # type: ignore[method-assign]
    F.feed_registers(client, svc)
    zero = {"ad_spends": [{"campaign_id": "FICTIF-CAMP-1", "day": NOW.date().isoformat(), "amount": "0"}]}
    assert client.post("/ads/activity", headers=JR.HADS, json=zero).status_code == 200
    data = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    ads = [t for t in data["triggers"] if t["level"] == "ADS"]
    assert ads and any(t["scope"] == "FICTIF-CAMP-1" for t in ads)


# =============================================================================== R2-NEW-04 / MOT-18


def test_r2new04_northstar_sales_come_from_recorded_orders_with_real_logistics(tmp_path: Path) -> None:
    """PoC p3 : NET_SALES 25 000 et avoirs négatifs déclarés => refusés ; ventes dérivées des commandes."""
    client, svc, _ = F.boot(tmp_path)
    forged = [{"entry_id": "FICTIF-V1", "at": NOW.isoformat(), "post": "NET_SALES", "amount": "25000.00", "order_id": "X"},
              {"entry_id": "FICTIF-A1", "at": NOW.isoformat(), "post": "ACQUISITION", "amount": "-2000.00"}]
    assert client.post("/northstar/entries", headers=H, json={"entries": forged}).status_code == 403
    assert client.post("/northstar/entries", headers=JR.HACQ, json={"entries": forged}).status_code == 403
    for entry in forged + [{"entry_id": "FICTIF-L1", "at": NOW.isoformat(), "post": "LOGISTICS", "amount": "3.00"}]:
        resp = client.post("/northstar/entries", headers=JR.HORDERS, json={"entries": [entry]})
        assert resp.status_code == 422, entry
    assert svc.northstar.entries() == ()
    F.seed_stock(client, svc)
    missing = {"order_id": "FICTIF-O1", "paid_at": NOW.isoformat(), "net_sales_ht": "184.92", "payment_fees": "5.30",
               "shipping_label_ref": "FICTIF-ETIQ-1", "source": "Shopify FICTIF", "lines": F.ORDER_LINES}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=missing).status_code == 422  # transporteur réel
    assert client.post("/orders/shipped", headers=JR.HORDERS, json={**missing, "shipping_cost_actual": "0"}).status_code == 422
    order = {**missing, "shipping_cost_actual": "7.40"}
    assert client.post("/orders/shipped", headers=JR.HF, json=order).status_code == 403  # rôle des commandes
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order).status_code == 201
    totals = svc.northstar.totals()
    assert (totals.net_sales_ht, totals.payment, totals.logistics) == (D("184.92"), D("5.30"), D("7.40"))
    over = client.post("/orders/FICTIF-O1/refunds", headers=JR.HOPS, json={"refund_id": "FICTIF-R1", "at": NOW.isoformat(),
                                                                            "net_sales_ht": "500.00"})
    assert over.status_code == 409
    ghost = client.post("/orders/FICTIF-INCONNUE/refunds", headers=JR.HOPS,
                        json={"refund_id": "FICTIF-R2", "at": NOW.isoformat(), "net_sales_ht": "10.00"})
    assert ghost.status_code == 409
    ok = client.post("/orders/FICTIF-O1/refunds", headers=JR.HOPS, json={"refund_id": "FICTIF-R3", "at": NOW.isoformat(),
                                                                          "net_sales_ht": "84.92"})
    assert ok.status_code == 201 and svc.northstar.totals().net_sales_ht == D("100.00")


def test_r2new04_owner_manual_entries_never_carry_an_arbitrary_negative_value(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    credit = [{"entry_id": "FICTIF-AV1", "at": NOW.isoformat(), "post": "ACQUISITION", "amount": "-50.00", "ref": "rien"}]
    assert client.post("/northstar/entries", headers=HO, json={"entries": credit}).status_code == 422
    base = [{"entry_id": "FICTIF-PUB1", "at": NOW.isoformat(), "post": "ACQUISITION", "amount": "80.00"}]
    assert client.post("/northstar/entries", headers=JR.HF, json={"entries": base}).status_code == 200
    linked = [{**credit[0], "ref": "FICTIF-PUB1"}]
    assert client.post("/northstar/entries", headers=HO, json={"entries": linked}).status_code == 200
    too_much = [{**credit[0], "entry_id": "FICTIF-AV2", "ref": "FICTIF-PUB1", "amount": "-40.00"}]
    assert client.post("/northstar/entries", headers=HO, json={"entries": too_much}).status_code == 422  # 50 + 40 > 80
    sale = [{"entry_id": "FICTIF-VM1", "at": NOW.isoformat(), "post": "NET_SALES", "amount": "30.00", "order_id": "FICTIF-M1"}]
    assert client.post("/northstar/entries", headers=HO, json={"entries": sale}).status_code == 422  # logistique supposée
    with_logistics = sale + [{"entry_id": "FICTIF-LM1", "at": NOW.isoformat(), "post": "LOGISTICS", "amount": "7.00",
                              "order_id": "FICTIF-M1"}]
    assert client.post("/northstar/entries", headers=HO, json={"entries": with_logistics}).status_code == 200
    assert svc.northstar.totals().acquisition == D("30.00")


def test_mot18_the_real_path_refuses_assumed_logistics() -> None:
    ns = NorthStarLedger()
    with pytest.raises(NorthStarError, match="transporteur"):
        ns.record_order("FICTIF-O1", NOW, net_sales_ht="50.00", payment_fees="1.00", logistics=None)
    with pytest.raises(NorthStarError):
        ns.add_entries([ContributionEntry(entry_id="x", at=NOW, post=Post.NET_SALES, amount=D("10"), order_id="o")])
    with pytest.raises(NorthStarError):
        ns.add_entries([ContributionEntry(entry_id="y", at=NOW, post=Post.LOGISTICS, amount=D("-3"))], owner=True)


# =============================================================================== NEW-01


def incident_setup(tmp_path: Path, **incident: Any) -> tuple[TestClient, Services, str]:
    client, svc, _ = F.boot(tmp_path)
    F.register_catalog(client)
    payload = {"code": "INC-01", "product_key": "FICTIF-P1", "cause": "prix publié anormal (FICTIF)", **incident}
    inc = body(client.post("/incidents", headers=JR.HINC, json=payload))["incident"]
    return client, svc, inc["incident_id"]


def test_new01_only_qa_or_owner_attest_and_the_run_must_be_launched_by_someone_else(tmp_path: Path) -> None:
    client, svc, inc = incident_setup(tmp_path)
    run = body(client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY))["report"]["run_id"]
    url = f"/incidents/{inc}/test"
    for role in ("finance-pricing", "operations-sav", "n8n-07-stoploss", "n8n-04-incidents"):  # PoC p9 : agent-05
        resp = client.post(url, headers=JR.headers(role), json={"test_ref": run, "passed": True, "actor": "x1"})
        assert resp.status_code == 403 and "qa-conformite" in body(resp)["erreur"], role
    own = svc.sync_runs.record(SyncRunSummary(
        run_id="SYNC-PAR-QA", supplier_id="fictif_grossiste_a", dry_run=True, started_at=NOW, finished_at=NOW,
        status="PROPRE", offers_costed=1, items=1, catalog_source="registre", recorded_by="qa-conformite",
        product_ids=("FICTIF-P1",)))  # fmt: skip
    self_run = client.post(url, headers=JR.HQA, json={"test_ref": own.run_id, "passed": True, "actor": "x1"})
    assert self_run.status_code == 409 and "attestant" in body(self_run)["erreur"]
    ok = client.post(url, headers=JR.HQA, json={"test_ref": run, "passed": True, "actor": "x1"})
    assert ok.status_code == 200 and body(ok)["incident"]["test_passed"] is True


def test_new01_body_catalog_or_other_supplier_never_proves_the_fix(tmp_path: Path) -> None:
    client, _, inc = incident_setup(tmp_path, supplier_id="fictif_grossiste_c")
    body_run = body(client.post("/sync/run", headers=JR.HSYNC, json={**F.N8N_SYNC_BODY, "catalog": [
        {"product_id": "FICTIF-P1", "listing": F.LISTING}]}))["report"]["run_id"]
    resp = client.post(f"/incidents/{inc}/test", headers=JR.HQA, json={"test_ref": body_run, "passed": True, "actor": "x1"})
    assert resp.status_code == 409 and "corps" in body(resp)["erreur"]
    registry_run = body(client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY))["report"]["run_id"]
    other = client.post(f"/incidents/{inc}/test", headers=JR.HQA, json={"test_ref": registry_run, "passed": True,
                                                                          "actor": "x1"})
    assert other.status_code == 409 and "fournisseur" in body(other)["erreur"]  # même si la référence est connue


def test_new01_real_incident_needs_a_real_cycle(tmp_path: Path) -> None:
    """PoC advr2 : incident sur une référence réelle ; un cycle FICTIF ne prouve jamais la correction."""
    client, svc, _ = F.boot(tmp_path)
    F.register_catalog(client)
    inc = body(client.post("/incidents", headers=JR.HINC, json={"code": "INC-01", "product_key": "REF-04-REEL",
                                                                "cause": "prix publié anormal"}))["incident"]
    assert inc["fictif"] is False
    run = body(client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY))["report"]["run_id"]
    resp = client.post(f"/incidents/{inc['incident_id']}/test", headers=JR.HQA,
                       json={"test_ref": run, "passed": True, "actor": "x1"})
    assert resp.status_code == 409 and "cycle réel" in body(resp)["erreur"]
    assert svc.incidents.is_quarantined("REF-04-REEL")


# =============================================================================== R2-ADV-01


def test_r2adv01_point_zero_is_set_with_the_first_photo_atomically(tmp_path: Path) -> None:
    """PoC baseline_order : apport 8 000, soldes 600 + 4 500 (2 900 de lancement) ; point zéro 4 200 posé."""
    client, svc, _ = F.boot(tmp_path)
    cash_registers(client, capital="8000", paypal="600", bank="4500")
    request = {"reason": "Point zéro J26 : lancement 2 900 assumé (FICTIF)", "reference_chf": "4200", "with_photo": True}
    assert client.post("/stoploss/baseline", headers=JR.HQA, json=request).status_code == 403
    done = client.post("/stoploss/baseline", headers=HO, json=request)
    assert done.status_code == 200, done.text
    data = body(done)
    assert data["status"]["global_frozen"] is False and data["latch"]["baseline"]["net_value_chf"] == "4200"
    assert svc.stoploss_state is not None and not svc.stoploss_engine.frozen
    again = client.post("/stoploss/baseline", headers=HO, json=request)
    assert again.status_code == 409  # premier point zéro seulement ; ensuite : réarmement
    _, svc2, _ = F.boot(tmp_path)
    assert svc2.stoploss_engine.latch.baseline.net_value_chf == D("4200")


def test_r2adv01_without_point_zero_the_launch_photo_freezes(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    cash_registers(client, capital="8000", paypal="600", bank="4500")
    assert body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["status"]["global_frozen"] is True
    late = client.post("/stoploss/baseline", headers=HO, json={"reason": "Point zéro trop tard (FICTIF)",
                                                                "reference_chf": "4200"})
    assert late.status_code == 409 and svc.stoploss_engine.frozen  # d'où l'ordre : point zéro AVANT le workflow 07


# =============================================================================== docs et infra (R2-ADV-02, CON-10, CON-06)


def test_r2adv02_compose_makes_the_common_token_optional_and_role_tokens_explicit() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "POKESHOP_API_TOKEN_SHA256: ${POKESHOP_API_TOKEN_SHA256:-}" in text
    for role in ("n8n-07-stoploss", "connecteur-tresorerie", "finance-pricing"):
        var = ROLE_TOKEN_VARIABLES[role]
        assert f"{var}: ${{{var}:?" in text, var  # sans eux, le stop-loss n'est jamais évaluable
    for var in ROLE_TOKEN_VARIABLES.values():
        assert f"{var}: ${{{var}" in text, var
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'install -D -m 600 -o "$USER"' in readme and "POKESHOP_ROLE_TOKEN_SHA256_" in readme
    assert "fichier ``.env`` local" not in (ROOT / "engine" / "pokeshop" / "settings.py").read_text(encoding="utf-8")


def test_con10_backup_restore_is_blocking_and_monthly() -> None:
    recette = (ROOT / "docs" / "07-ops" / "RECETTE_AVANT_OUVERTURE.md").read_text(encoding="utf-8")
    line = next(ln for ln in recette.splitlines() if "R-I04" in ln and ln.startswith("|"))
    assert "| O |" in line and "db/backup.sh etat" in line
    assert "chaque mois" in (ROOT / "docs" / "07-ops" / "ROUTINES_PILOTAGE.md").read_text(encoding="utf-8")
    assert "R-I04" in (ROOT / "docs" / "00-pilotage" / "GATES_GO_NO_GO.md").read_text(encoding="utf-8")


def test_con06_n8n_is_public_from_b27_and_failures_alert_without_the_api() -> None:
    readme = (ROOT / "orchestration" / "README.md").read_text(encoding="utf-8")
    assert "B27" in readme and "J8" in readme
    assert "avant le niveau 2" not in readme.split("## Validation humaine requise")[-1]


# Garde-fous d'import (aucun état partagé) : en-têtes et types utilisés.
assert API_TOKEN_HEADER and OWNER_TOKEN_HEADER and ShopStatus and create_app and LogNotifier and A
