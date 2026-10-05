"""Régressions de la revue adverse, 4ᵉ passe : un test par point (code et génération n8n), échouant avant correctif.

* R2-NEW-01 : coût unitaire d'une réception borné par une référence du moteur (écart > 2 % ou aucune référence :
  propriétaire) ; une réception valorisée une fois ; passerelle n8n de réception avec un secret propre à l'agent 11.
* R2-NEW-03 : stop-loss pub nourri par les paiements pub **engagés** du mandat ; docs alignées.
* SEC-16 : un secret de passerelle par webhook et par agent ; administration de n8n non déléguée.
* R3-NEW-01 : clé produit unique ; ré-identification refusée ; catalogue du corps refusé en écriture réelle ;
  quarantaine et stop-loss produit sur toutes les clés ; aucune validation retrouvée par une autre clé.
* R3-NEW-02 / R3-NEW-03 : créances de la propriétaire seule, plancher des factures enregistrées, dettes jamais
  abaissées par l'agent finance ; photo déposée réservée à la propriétaire, cash recoupé avec les relevés.
* R3-NEW-04 / R3-NEW-05 / R3-DOC-03 : espace de noms des écritures dérivées réservé, commande atomique avec lignes,
  coût des ventes dérivé au CMP, frais PSP d'une commande comptés une fois.
* R3-NEW-06 : relais 08 limité aux agents qui dépensent.
* R3-DOC-01 : jeton propriétaire suffisant seul. R3-DOC-02 : facture enregistrée = référence du coût de réception.
* R3-DOC-04 : « simulation » d'un incident déduite de l'état du moteur.
* R2-ADV-01, R3-DOC-05, R3-DOC-06, R3-DOC-07 : sources générées et procédures (07 après C19, note de 07,
  transfert des empreintes, migrations).
Données, jetons et montants FICTIFS ; bases PostgreSQL : aucune (journaux en fichiers par test, tmp_path).
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
import test_mandate as M
import test_n8n_workflows as N
import test_orchestration_f4 as F
import test_revue_r3 as R3
import test_sync as S
from fastapi.testclient import TestClient
from pokeshop import authz
from pokeshop.api import OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.catalog import CatalogProduct
from pokeshop.catalogue_sync import CatalogEntry
from pokeshop.incidents import IncidentCode, LogNotifier
from pokeshop.mandate import PaymentMethod, SpendCategory, SpendStatus
from pokeshop.northstar import ContributionEntry, Post
from pokeshop.publish import ListingApproval, listing_digest
from pokeshop.settings import load_settings
from pokeshop.stoploss import ProductMargin, hash_owner_token
from pokeshop.stoploss_snapshot import committed_ad_payments

ROOT = Path(__file__).resolve().parents[1]
NOW = F.NOW
H, HO = F.H, F.HO
OWNER_ONLY = {OWNER_TOKEN_HEADER: F.OWNER_TOKEN}
H03 = JR.headers("n8n-03-factures")
SKU = "DSP-FICTIF_ALPHA-FR"


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def receipt(unit_cost: str, *, qty: int = 6, ref: str = "FICTIF-LOT-1", stock_ref: str = "FICTIF-BL-1",
            invoice_ref: str = "FICTIF-FACT-1", key: str = "FICTIF-P1") -> dict[str, Any]:  # fmt: skip
    return {"kind": "RECEIPT", "product_key": key, "at": (NOW - timedelta(days=1)).isoformat(), "ref": ref, "qty": qty,
            "unit_cost": unit_cost, "stock_ref": stock_ref, "invoice_ref": invoice_ref}  # fmt: skip


def catalog_and_receive(client: TestClient, qty: int = 6, ref: str = "FICTIF-BL-1") -> None:
    assert client.post("/catalog/items", headers=JR.HCAT,
                       json={"items": [{"product_id": "FICTIF-P1", "listing": F.LISTING}]}).status_code == 200  # fmt: skip
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": SKU, "qty": qty, "ref": ref}).status_code == 200


def order(order_id: str, *, qty: int = 1, fees: str = "5.30", lines: bool = True) -> dict[str, Any]:
    out = {"order_id": order_id, "paid_at": (NOW - timedelta(hours=1)).isoformat(), "net_sales_ht": "184.92",
           "payment_fees": fees, "shipping_cost_actual": "7.40", "shipping_label_ref": f"FICTIF-ETIQ-{order_id}",
           "source": "webhook Shopify FICTIF"}  # fmt: skip
    if lines:
        out["lines"] = [{"public_sku": SKU, "qty": qty}]
    return out


def legacy_entry(svc: Services, product_id: str = "P-001") -> None:
    """Entrée ancienne incohérente (product_id ≠ listing.product_key), relue d'un journal d'avant la revue R4."""
    svc.catalog._entries[product_id] = CatalogEntry(product_id=product_id, listing=F.LISTING, recorded_by="catalogue",
                                                    recorded_at=NOW - timedelta(days=3))  # fmt: skip


# ======================================================================= R2-NEW-01 (code, recheck3-0)


def test_r2new01_receipt_unit_cost_is_bounded_by_an_engine_reference(tmp_path: Path) -> None:
    """PoC a1/a2 : 6 × 650 au lieu de 101 taisait le gel global ; une réception valorisée deux fois."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="1500")  # apport 4 200, cash 2 000 : gel global
    catalog_and_receive(client)
    no_reference = client.post("/costs/movements", headers=JR.HF, json=receipt("101.23"))
    assert no_reference.status_code == 403 and "référence du moteur" in body(no_reference)["erreur"]
    F.engine_offer(svc, "101.23")  # coût rendu de l'offre évaluée par le moteur
    for inflated in ("650", "607.38", "3644.28"):  # gonflé, carton de 6, carton de 36 saisis comme unité
        refused = client.post("/costs/movements", headers=JR.HF, json=receipt(inflated))
        assert refused.status_code == 403 and "2 %" in body(refused)["erreur"], inflated
    assert svc.costs.movements() == () and svc.audit.events(action="costs.movement_refused")
    frozen = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert frozen["status"]["global_frozen"] is True
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("102.00")).status_code == 200  # écart 0,76 %
    # (b) la même réception physique ne se valorise qu'une fois, quelle que soit la référence de lot.
    again = client.post("/costs/movements", headers=JR.HF, json=receipt("102.00", ref="FICTIF-LOT-B"))
    assert again.status_code == 409 and "déjà valorisée" in body(again)["erreur"]
    # La propriétaire inscrit un coût hors référence (écart signalé) sur une autre réception.
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": SKU, "qty": 2, "ref": "FICTIF-BL-2"}).status_code == 200
    owner = client.post("/costs/movements", headers=HO, json=receipt("650", qty=2, ref="FICTIF-LOT-2", stock_ref="FICTIF-BL-2"))
    assert owner.status_code == 200
    assert body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["status"]["global_frozen"] is True


# ======================================================================= R2-NEW-01 (séparation, recheck3-1)


def test_r2new01_reception_gateway_secret_is_held_by_agent_11_only() -> None:
    """La passerelle 06 de réception a son propre secret (agent 11) ; aucun webhook d'écriture n'en partage un."""
    wf06 = N.nodes(N.WORKFLOWS["06_marketing_automations.json"])
    hook = wf06["Réception contrôlée (passerelle agent 11)"]
    cred = hook["credentials"]["httpHeaderAuth"]
    key = next(k for k, (_t, cid, name) in N.GEN.CREDENTIALS.items() if cid == cred["id"] and name == cred["name"])
    assert N.GEN.GATEWAY_HOLDERS[key] == "operations-sav"
    seen: dict[str, str] = {}
    for name, wf in N.WORKFLOWS.items():
        for node in wf["nodes"]:
            if node["type"] == "n8n-nodes-base.webhook" and node["parameters"]["authentication"] == "headerAuth":
                cid = node["credentials"]["httpHeaderAuth"]["id"]
                assert cid not in seen, f"{name} / {node['name']} partage le secret de {seen[cid]}"
                seen[cid] = node["name"]
    assert len(seen) == len(N.GEN.GATEWAY_HOLDERS)
    assert "pkshpGateway0001" not in json.dumps(N.WORKFLOWS, ensure_ascii=False)  # ancien secret commun


# ======================================================================= R2-NEW-03 (code, recheck3-0)


def test_r2new03_approved_ad_payments_feed_the_ads_stoploss_and_ad_spends_need_the_connector(tmp_path: Path) -> None:
    """PoC a8 : 3 paiements pub de 30 APPROUVÉS (aucun connecteur) => déclencheurs ADS (avant : aucun)."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    for i in range(3):
        day = NOW - timedelta(days=i)
        rq = M.req(amount=D("30"), category=SpendCategory.ADVERTISING, supplier_id="FICTIF_PUB",
                   payment_method=PaymentMethod.PAYPAL, campaign_id="FICTIF-CAMP-1", purpose="campagne FICTIVE",
                   idempotency_key=f"FICTIF-PUB-{i}", requested_at=day, requested_by="acquisition")  # fmt: skip
        mandate = M.signed(lambda d: (M.no_fees(d), d.update(valid_from="2026-09-01"),
                                      d["approval"].update(approved_at="2026-09-01T09:00:00+02:00")))  # fmt: skip
        decision = M.decide(rq, mandate, svc.spend_ledger, stoploss=M.status(as_of=day), snapshot=M.treasury(as_of=day), now=day)
        svc.spend_ledger.record(rq, decision)
    assert {e.status for e in svc.spend_ledger.entries()} == {SpendStatus.APPROVED}
    data = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    ads = {(t["scope"], t.get("metric")) for t in data["triggers"] if t["level"] == "ADS"}
    assert ("FICTIF-CAMP-1", "depense_7j_sans_commande_chf") in ads
    spend = {"request": {"amount": "20", "currency": "CHF", "supplier_id": "FICTIF_PUB", "category": "ADVERTISING",
                         "payment_method": "PAYPAL", "purpose": "campagne FICTIVE", "idempotency_key": "FICTIF-PUB-9",
                         "requested_by": "acquisition", "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF",
                         "campaign_id": "FICTIF-CAMP-2"}}  # fmt: skip
    checked = body(client.post("/mandate/check", headers=JR.HACQ, json=spend))
    assert any("connecteur-publicite" in label for label in checked["unverified"])


# ======================================================================= R2-NEW-03 (docs, recheck3-1)


def test_r2new03_docs_and_code_agree_on_committed_ad_payments() -> None:
    human = SimpleNamespace(request=SimpleNamespace(category=SpendCategory.ADVERTISING, campaign_id=None),
                            status=SpendStatus.HUMAN_APPROVED, human_decided_at=NOW - timedelta(days=1),
                            decision=SimpleNamespace(decided_at=NOW - timedelta(days=2), amount_chf=D("40")),
                            executed_at=None, executed_amount_chf=None)  # fmt: skip
    refused = SimpleNamespace(request=SimpleNamespace(category=SpendCategory.ADVERTISING, campaign_id="X"),
                              status=SpendStatus.HUMAN_REFUSED, decision=SimpleNamespace(decided_at=NOW, amount_chf=D("9")))
    committed = committed_ad_payments([human, refused], NOW.tzinfo)
    assert list(committed.values()) == [D("40")] and next(iter(committed))[1] == (NOW - timedelta(days=1)).date()
    stoploss = (ROOT / "docs/00-pilotage/STOP_LOSS.md").read_text(encoding="utf-8")
    assert "Une dépense pub exécutée sans déclaration compte donc quand même" not in stoploss
    assert "paiements publicitaires **engagés**" in stoploss and "aucune campagne sans connecteur publicitaire" in stoploss
    assert "paiements pub **engagés**" in authz.matrix_markdown()
    assert "paiements pub **engagés**" in (ROOT / "docs/SPEC.md").read_text(encoding="utf-8")


# ======================================================================= SEC-16


def test_sec16_one_gateway_secret_per_webhook_and_per_agent() -> None:
    holders = N.GEN.GATEWAY_HOLDERS
    assert set(holders.values()) <= authz.KNOWN_ROLES
    names = {N.GEN.CREDENTIALS[k][2]: role for k, role in holders.items()}
    assert len(set(names)) == len(names) and not any("agents —" in name for name in names)
    wf08 = N.WORKFLOWS["08_mandat_depenses.json"]
    by = N.nodes(wf08)
    hooks = [n for n in by.values() if n["type"] == "n8n-nodes-base.webhook"]
    assert {names[h["credentials"]["httpHeaderAuth"]["name"]] for h in hooks} == set(authz.RELAYED_SPENDERS)
    for hook in hooks:
        role = names[hook["credentials"]["httpHeaderAuth"]["name"]]
        (tag,) = N.successors(wf08, hook["name"], 0)
        assert f"requested_by: '{role}'" in by[tag]["parameters"]["jsCode"]  # demandeur imposé par le webhook
    readme = (ROOT / "orchestration/README.md").read_text(encoding="utf-8")
    assert "jamais délégué à un agent" in readme and "Passerelle agents — X-Pokeshop-Gateway" not in readme


# ======================================================================= R3-NEW-01


def test_r3new01_one_canonical_product_key_and_no_rekeying(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    mismatch = client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "P-001", "listing": F.LISTING}]})
    assert mismatch.status_code == 422 and "clé produit incohérente" in mismatch.text
    F.register_catalog(client)
    client.post("/incidents", headers=JR.HINC, json={"code": "INC-01", "product_key": "FICTIF-P1", "cause": "prix anormal"})
    assert svc.incidents.is_quarantined("FICTIF-P1")
    # PoC a3c : l'ancienne fiche sort du rapprochement, la même fiche revient sous un autre identifiant.
    old = dict(F.LISTING, identity=dict(F.IDENTITY, gtin="2000000009998"))
    bis = dict(F.LISTING, product_key="FICTIF-P1-BIS")
    rekey = {"items": [{"product_id": "FICTIF-P1", "listing": old}, {"product_id": "FICTIF-P1-BIS", "listing": bis}]}
    refused = client.post("/catalog/items", headers=JR.HCAT, json=rekey)
    assert refused.status_code == 409 and "propriétaire" in body(refused)["erreur"]
    assert [e.product_id for e in svc.catalog.entries()] == ["FICTIF-P1"]
    # PoC a3e : catalogue du corps en écriture réelle : refusé (registre seulement).
    assert client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY).status_code == 200  # référence d'import
    real = client.post("/sync/run", headers=JR.HSITE, json={**F.N8N_SYNC_BODY, "dry_run": False,
                                                            "catalog": [{"product_id": "FICTIF-P1", "listing": F.LISTING}]})
    assert real.status_code == 409 and "simulation seulement" in body(real)["erreur"]


def test_r3new01_legacy_mismatch_never_escapes_quarantine_stoploss_or_borrows_a_validation(tmp_path: Path) -> None:
    """PoC a3/a3b : product_id P-001, listing.product_key FICTIF-P1 (entrée ancienne) — quarantaine et stop-loss
    posés sur FICTIF-P1 valent pour P-001 ; la validation de FICTIF-P1 n'est jamais prêtée à P-001."""
    for pid in ("FICTIF-P1", "P-001"):
        env = S.Env()
        item = S.listing()
        ctx = S.context(item, approved=True, catalog_products=[CatalogProduct(product_id=pid, identity=S.IDENT_A1)],
                        listings={pid: item}, validations={pid: S.owner_validations(item, approved=True)})  # fmt: skip
        assert S.item_for(env.cycle(ctx, dry_run=False), pid).written
        env.incidents.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix anormal (test)", actor="n8n-04-incidents")
        env.state = S.healthy_state(env.now, products=(ProductMargin(product_key="FICTIF-P1", contribution_chf=D("3"),
                                                                     contribution_pct=D("0.03")),))  # fmt: skip
        env.gate.invalidate()
        second = S.item_for(env.cycle(ctx, dry_run=False), pid)
        assert second.action == "UNPUBLISH_PRODUCT" and second.written, pid
    # PoC a3 (validation) : la propriétaire a validé « FICTIF-P1 » ; l'entrée ancienne P-001 porte la même fiche.
    client, svc, _ = F.boot(tmp_path)
    costs = {"supplier_id": "fictif_grossiste_a", "currency": "EUR", "inbound_freight_alloc": "2.00",
             "customs_and_fees": "0", "import_vat": "0", "source": "devis transporteur FICTIF"}
    assert client.post("/catalog/cost-inputs", headers=JR.HF, json=costs).status_code == 200
    rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": "2026-10-04", "source": "BNS FICTIF 11:00"}
    assert client.post("/fx/rates", headers=HO, json=rate).status_code == 200
    legacy_entry(svc)
    digest = listing_digest(svc.catalog.entry_for("P-001").listing)
    svc.catalog_approvals.record(ListingApproval(product_key="FICTIF-P1", listing_sha256=digest, approved=True,
                                                 content_validated=True, category_rule_validated=True,
                                                 reason="fiche FICTIVE relue par la propriétaire", approved_at=NOW))  # fmt: skip
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": SKU, "qty": 6, "ref": "FICTIF-BL-1"}).status_code == 200
    assert svc.catalog.incoherent() == ("P-001",)
    run = body(client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY))
    item = next(i for i in run["report"]["items"] if i["product_id"] == "P-001")
    assert item["match_status"] == "MATCHED" and item["plan_outcome"] != "SEND_ACTIVE"  # aucun repli sur la clé de la fiche
    # Une entrée incohérente ne se valorise sous aucune de ses clés.
    F.engine_offer(svc, "101.23", product_key="P-001")
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("101.23", key="P-001")).status_code == 409


# ======================================================================= R3-NEW-02


def test_r3new02_receivables_are_the_owners_and_debts_have_a_register_floor(tmp_path: Path) -> None:
    """PoC a7 : une « TVA à récupérer » de 5 000 déclarée par l'agent finance taisait une perte de 52 %."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="1500")
    assert body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["status"]["global_frozen"] is True
    at = (NOW - timedelta(minutes=5)).isoformat()
    forged = {"as_of": at, "preorders_collected_chf": "0", "receivables": [{"label": "TVA à récupérer", "amount": "5000"}],
              "source": "déclaration FICTIVE agent finance"}  # fmt: skip
    refused = client.post("/treasury/balance-items", headers=JR.HF, json=forged)
    assert refused.status_code == 403 and "propriétaire" in body(refused)["erreur"]
    assert client.post("/treasury/balance-items", headers=JR.HTRES, json=forged).status_code == 403
    still = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert still["status"]["global_frozen"] is True and D(still["net_worth_chf"]) == D("2000")
    # Dettes : l'agent finance les relève, jamais ne les abaisse.
    debts = {"as_of": at, "preorders_collected_chf": "0", "debts": [{"label": "TVA due", "amount": "300"}], "source": "FICTIF"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=debts).status_code == 200
    lower = client.post("/treasury/balance-items", headers=JR.HF, json={**debts, "debts": []})
    assert lower.status_code == 403 and "baisse" in body(lower)["erreur"]
    # Facture enregistrée (workflow 03) non payée : plancher des dettes, jusqu'au paiement relevé.
    invoice = {"invoice_ref": "FICTIF-FACT-9", "supplier_id": "fictif_grossiste_a", "issued_at": at, "total_chf": "700.00",
               "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "101.23"}], "source": "facture FICTIVE"}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": F.LISTING}]}).status_code == 200
    assert client.post("/costs/invoices", headers=JR.HF, json=invoice).status_code == 403  # jamais l'agent finance
    assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 201
    with_invoice = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert D(with_invoice["net_worth_chf"]) == D("1000") and "FICTIF-FACT-9" in with_invoice["sources"]["dettes_creances"]["unpaid_invoices"]
    pay = {"payment_ref": "FICTIF-TX-1", "paid_at": at, "amount_chf": "700.00"}
    assert client.post("/costs/invoices/FICTIF-FACT-9/payments", headers=JR.HF, json=pay).status_code == 403
    assert client.post("/costs/invoices/FICTIF-FACT-9/payments", headers=JR.HTRES, json=pay).status_code == 201
    # Paiement postérieur aux relevés de la photo : la dette reste tant que le cash ne l'a pas vu (fermé par défaut).
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("1000")
    for path, amount in (("/treasury/paypal-balance", "500"), ("/treasury/bank-balance", "800")):
        fresh = {"as_of": (NOW - timedelta(minutes=1)).isoformat(), "balance_chf": amount, "source": "relevé FICTIF"}
        assert client.post(path, headers=JR.HTRES, json=fresh).status_code == 200
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("1000.00")  # neutre
    # La propriétaire relève une créance (son jeton seul) : elle compte.
    owner = {"as_of": NOW.isoformat(), "preorders_collected_chf": "0", "debts": [{"label": "TVA due", "amount": "300"}],
             "receivables": [{"label": "Versement PSP en transit", "amount": "200"}], "source": "relevé de la propriétaire"}
    assert client.post("/treasury/balance-items", headers=OWNER_ONLY, json=owner).status_code == 200
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("1200")


# ======================================================================= R3-NEW-03


def test_r3new03_declared_photo_is_the_owners_and_its_cash_must_match_the_readings(tmp_path: Path) -> None:
    """PoC a4 : photo déclarée par n8n-07 (cash 9 000 au lieu de 2 000) levait le gel et nourrissait le mandat."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="1500")
    assert body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["status"]["global_frozen"] is True
    as_of = (NOW - timedelta(minutes=10)).isoformat()
    forged = {"as_of": as_of, "stock_budget_chf": "3000", "cash_available_chf": "9000",
              "net_worth": {"as_of": as_of, "cash_chf": "9000"}}  # fmt: skip
    assert client.post("/stoploss/state", headers=JR.HPHOTO, json=forged).status_code == 403
    mismatch = client.post("/stoploss/state", headers=OWNER_ONLY, json=forged)
    assert mismatch.status_code == 409 and "relevés du connecteur" in body(mismatch)["erreur"]
    assert svc.stoploss_engine.frozen and svc.stoploss_state.cash_available_chf == D("2000")
    honest = {**forged, "cash_available_chf": "2000", "net_worth": {"as_of": as_of, "cash_chf": "2000"}}
    accepted = client.post("/stoploss/state", headers=OWNER_ONLY, json=honest)
    assert accepted.status_code == 200 and body(accepted)["status"]["global_frozen"] is True
    assert svc.photo_poster == "propriétaire"


# ======================================================================= R3-NEW-04


def test_r3new04_derived_entry_namespace_is_reserved_and_orders_are_atomic(tmp_path: Path) -> None:
    """PoC a6 : « order:1001:PAYMENT » posté avant la commande bloquait la vente puis, au redémarrage, tout le registre."""
    client, svc, _ = F.boot(tmp_path)
    F.seed_stock(client, svc)
    at = (NOW - timedelta(hours=2)).isoformat()
    for entry in ({"entry_id": "order:1001:PAYMENT", "at": at, "post": "PAYMENT", "amount": "0.01"},
                  {"entry_id": "REFUND:9:PAYMENT", "at": at, "post": "PAYMENT", "amount": "0.01"},
                  {"entry_id": "FICTIF-X", "at": at, "post": "PAYMENT", "amount": "0.01", "source": "commande"}):
        squat = client.post("/northstar/entries", headers=JR.HF, json={"entries": [entry]})
        assert squat.status_code == 422 and "réservé" in body(squat)["erreur"], entry
    # Conflit ancien (journal d'avant la revue) : la commande est refusée sans rien écrire.
    svc.northstar._add([ContributionEntry(entry_id="order:1001:PAYMENT", at=NOW - timedelta(hours=2), post=Post.PAYMENT,
                                          amount=D("0.01"), source="frais PSP FICTIFS")], internal=True)  # fmt: skip
    refused = client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001"))
    assert refused.status_code == 409 and svc.orders.get("1001") is None
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 6
    # Une commande déjà inscrite au registre dont l'écriture dérivée est en conflit ne gèle plus rien au redémarrage.
    svc.orders._append({"order": {**order("1001"), "lines": [{"public_sku": SKU, "product_key": "FICTIF-P1", "qty": 1}],
                                  "recorded_by": "n8n-02-commandes", "recorded_at": NOW.isoformat()}})  # fmt: skip
    client2, svc2, _ = F.boot(tmp_path)
    assert "orders" not in svc2.restore_errors and svc2.stoploss_engine.restore_hold is None
    northstar = body(client2.get("/northstar", headers=H))
    assert northstar["incomplete"] is True and "commande 1001" in northstar["derivation_errors"]
    assert client2.post("/orders/shipped", headers=JR.HORDERS, json=order("1002")).status_code == 201


# ======================================================================= R3-NEW-05


def test_r3new05_shipped_orders_carry_lines_and_derive_cost_of_sales(tmp_path: Path) -> None:
    """PoC a9 : sans ISSUE de l'agent finance, l'étoile polaire gagnait 607 CHF et le stock vendu restait dans la photo."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)  # 6 displays au coût 101.2345
    no_lines = client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001", lines=False))
    assert no_lines.status_code == 422
    unknown = client.post("/orders/shipped", headers=JR.HORDERS,
                          json={**order("1001"), "lines": [{"public_sku": "ETB-INCONNU-FR", "qty": 1}]})  # fmt: skip
    assert unknown.status_code == 409
    sale = {**order("1001", qty=6, fees="25.00"), "net_sales_ht": "855.00"}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=sale).status_code == 201
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 0
    assert svc.northstar.totals().historical_cost == D("607.41")
    assert body(client.get("/northstar", headers=H))["cumulative"] == "215.19"  # 855 − 25 − 7.40 − 607.41
    photo = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert svc.stoploss_state.net_worth.stock == () and D(photo["net_worth_chf"]) == D("3500.00")
    # Stock au coût insuffisant : revue R5 (R4-NEW-01) — commande enregistrée, coût des ventes en attente (jamais perdue).
    short = client.post("/orders/shipped", headers=JR.HORDERS, json=order("1002"))
    assert short.status_code == 201 and body(short)["cost_of_sales_pending"] == {"FICTIF-P1": 1}
    assert svc.orders.get("1002") is not None and body(client.get("/northstar", headers=H))["incomplete"] is True
    issue = {"kind": "ISSUE", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "1001", "qty": 1}
    assert client.post("/costs/movements", headers=JR.HF, json=issue).status_code == 403  # jamais déclarée
    back = {"kind": "RETURN", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-RET-1", "qty": 1,
            "sale_ref": "order:1001", "stock_ref": "return:FICTIF-AV-1"}
    assert client.post("/costs/movements", headers=JR.HF, json=back).status_code == 409  # sans avoir enregistré
    # Revue R5 (R3-NEW-05) : avoir AVEC lignes retournées et retour physique déclaré par operations-sav.
    refund = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50", "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=refund).status_code == 201
    assert client.post("/costs/movements", headers=JR.HF, json=back).status_code == 403  # pas encore de retour physique
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": SKU, "qty": 1, "ref": "return:FICTIF-AV-1"}).status_code == 200
    assert client.post("/costs/movements", headers=JR.HF, json=back).status_code == 200
    # L'unité revenue au coût sert aussitôt la commande 1002 en attente : coût des ventes dérivé, étoile complète.
    assert svc.orders.pending_cogs() == {} and body(client.get("/northstar", headers=H))["incomplete"] is False


# ======================================================================= R3-NEW-06


def test_r3new06_relay_carries_only_agents_that_spend(tmp_path: Path) -> None:
    """PoC a10 : qa-conformite et catalogue, exclus du mandat en direct, passaient par le relais 08."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    for who, expected in (("qa-conformite", 403), ("catalogue", 403), ("n8n-08-mandat", 403), ("acquisition", 200)):
        spend = {"request": {"amount": "40", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                             "payment_method": "PAYPAL", "purpose": "Étuis FICTIFS", "idempotency_key": f"FICTIF-RELAI-{who}",
                             "requested_by": who, "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF"},
                 "record": True}  # fmt: skip
        assert client.post("/mandate/check", headers=JR.HMANDAT, json=spend).status_code == expected, who
    assert len(svc.audit.events(action="mandate.check.relay_requester_refused")) == 3
    assert [e.request.requested_by for e in svc.spend_ledger.entries()] == ["acquisition"]


# ======================================================================= R2-ADV-01 (docs : point zéro avant 07)


def test_r2adv01_workflow_07_is_activated_only_after_c19() -> None:
    readme = (ROOT / "orchestration/README.md").read_text(encoding="utf-8")
    row = next(line for line in readme.splitlines() if line.startswith("| `n8n/07_stoploss_watch.json`"))
    assert "après C19" in row and "juste après 04" not in readme
    section = readme.split("## 7.", 1)[1].split("## 8.", 1)[0]
    activation = next(line for line in section.splitlines() if line.startswith("- [ ] 07"))
    assert "seulement après C19" in activation and "with_photo: true" in activation
    assert "votre jeton" in activation  # soldes de B26 déposés avant d'activer 07
    note = next(n for n in N.WORKFLOWS["07_stoploss_watch.json"]["nodes"] if n["name"] == "Note — à lire")
    content = note["parameters"]["content"]
    assert "**après C19**" in content and "juste après 04" not in content


# ======================================================================= R3-DOC-01


def test_r3doc01_owner_token_alone_is_enough(tmp_path: Path) -> None:
    """Configuration de B27 : empreinte propriétaire et jetons de rôle, sans jeton commun."""
    settings = load_settings({"POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(F.OWNER_TOKEN),
                              "POKESHOP_AGENT_TOKENS_SHA256": JR.agent_tokens_env(),
                              "POKESHOP_STATE_DIR": str(tmp_path / "etat")})  # fmt: skip
    assert settings.api_token_sha256 is None
    client = TestClient(create_app(services=Services.build(settings, clock=F.Clock(NOW), notifier=LogNotifier())))
    movement = {"movement_id": "FICTIF-APPORT-1", "at": (NOW - timedelta(days=1)).isoformat(), "kind": "CONTRIBUTION",
                "amount": "8000"}
    assert client.post("/capital/movements", headers=OWNER_ONLY, json=movement).status_code == 201
    assert body(client.get("/capital/movements", headers=OWNER_ONLY))["movements"][0]["movement_id"] == "FICTIF-APPORT-1"
    rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": NOW.date().isoformat(), "source": "BNS FICTIF"}
    assert client.post("/fx/rates", headers=OWNER_ONLY, json=rate).status_code == 200
    assert client.get("/stoploss/status", headers=OWNER_ONLY).status_code == 200
    bad = {OWNER_TOKEN_HEADER: "FICTIF-jeton-proprietaire-faux-000000001"}
    assert client.post("/capital/movements", headers=bad, json=movement).status_code == 401
    assert client.post("/capital/movements", headers=JR.HF, json=movement).status_code == 403


# ======================================================================= R3-DOC-02


def test_r3doc02_registered_invoice_bounds_the_receipt_cost(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    catalog_and_receive(client)
    F.engine_offer(svc, "650")  # une offre évaluée à 650 ne prime jamais sur la facture enregistrée citée
    invoice = {"invoice_ref": "FICTIF-FACT-1", "supplier_id": "fictif_grossiste_a", "issued_at": NOW.isoformat(),
               "total_chf": "607.38", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "101.23"}],
               "source": "facture FICTIVE validée par la propriétaire (formulaire 03)"}  # fmt: skip
    assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 201
    assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 200  # rejeu identique
    assert client.post("/costs/invoices", headers=H03, json={**invoice, "total_chf": "9.00"}).status_code == 409
    inflated = client.post("/costs/movements", headers=JR.HF, json=receipt("650"))
    assert inflated.status_code == 403 and "facture enregistrée FICTIF-FACT-1" in body(inflated)["erreur"]
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("101.50")).status_code == 200
    stoploss = (ROOT / "docs/00-pilotage/STOP_LOSS.md").read_text(encoding="utf-8")
    assert "référence du moteur" in stoploss and "POST /costs/invoices" in stoploss


# ======================================================================= R3-DOC-03


def test_r3doc03_psp_fees_of_an_order_are_never_counted_twice(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    F.seed_stock(client, svc)
    at = (NOW - timedelta(hours=3)).isoformat()
    early = [{"entry_id": "psp:FICTIF-T1:PAYMENT", "at": at, "post": "PAYMENT", "amount": "5.00", "source": "psp",
              "order_id": "1001"}]
    assert client.post("/northstar/entries", headers=JR.HORDERS, json={"entries": early}).status_code == 200
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001", fees="14.80")).status_code == 201
    assert svc.northstar.totals().payment == D("14.80")  # 5.00 du rapprochement + complément 9.80 de la commande
    late = [{"entry_id": "psp:FICTIF-T2:PAYMENT", "at": at, "post": "PAYMENT", "amount": "14.80", "source": "psp",
             "order_id": "1001"}]
    twice = client.post("/northstar/entries", headers=JR.HORDERS, json={"entries": late})
    assert twice.status_code == 422 and "jamais comptés deux fois" in body(twice)["erreur"]
    js = N.GEN.JS_PSP_FEES
    assert ".filter((t) => !t.associatedOrder)" in js  # 02 ne porte que les frais sans commande


# ======================================================================= R3-DOC-04


def test_r3doc04_incident_simulation_comes_from_the_engine_state(tmp_path: Path) -> None:
    payload = {"code": "INC-01", "product_key": "REEL-P9", "cause": "prix publié anormal", "simulation": True}
    real, real_svc, _ = F.boot(tmp_path / "reel", POKESHOP_DRY_RUN="false")
    incident = body(real.post("/incidents", headers=JR.HINC, json=payload))["incident"]
    assert incident["simulation"] is False and real_svc.incidents.is_quarantined("REEL-P9")
    assert real_svc.audit.events(action="incidents.simulation_ignored")
    sim, sim_svc, _ = F.boot(tmp_path / "simulation")
    assert body(sim.post("/incidents", headers=JR.HINC, json=payload))["incident"]["simulation"] is True
    assert not sim_svc.incidents.is_quarantined("REEL-P9")
    for rel in ("docs/SPEC.md", "docs/00-pilotage/DELEGATION_AUTONOMIE.md"):
        assert "moteur en simulation" in (ROOT / rel).read_text(encoding="utf-8") or "moteur est en simulation" in (
            ROOT / rel).read_text(encoding="utf-8"), rel


# ======================================================================= R3-DOC-05


def test_r3doc05_workflow_07_note_names_both_tokens() -> None:
    note = next(n for n in N.WORKFLOWS["07_stoploss_watch.json"]["nodes"] if n["name"] == "Note — à lire")
    content = note["parameters"]["content"]
    assert "photo `n8n-07-stoploss` ; soldes `connecteur-tresorerie`" in content
    assert "la photo et les soldes ne viennent jamais du jeton" not in content
    balances = [n for n in N.WORKFLOWS["07_stoploss_watch.json"]["nodes"]
                if N.is_engine_call(n) and N.engine_path(n).startswith("/treasury/")]
    assert {n["credentials"]["httpHeaderAuth"]["name"] for n in balances} == {
        "Pokeshop API — jeton nommé connecteur-tresorerie"}


# ======================================================================= R3-DOC-06


def test_r3doc06_role_fingerprints_are_transferred_to_the_server_explicitly() -> None:
    text = (ROOT / "docs/00-pilotage/DELEGATION_AUTONOMIE.md").read_text(encoding="utf-8")
    scp = text.index("scp ~/pokeshop-jetons/empreintes-roles.env serveur:")
    check = text.index("grep -cE '^POKESHOP_ROLE_TOKEN_SHA256_")
    append = text.index("cat ~/empreintes-roles.env >> /etc/pokeshop/api.env && shred -u ~/empreintes-roles.env")
    assert scp < check < append


# ======================================================================= R3-DOC-07


def test_r3doc07_env_example_cites_every_migration() -> None:
    numbers = sorted(int(p.name[:3]) for p in (ROOT / "db/migrations").glob("[0-9][0-9][0-9]_*.sql"))
    text = " ".join(line.lstrip("# ").strip() for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines())
    cited = [int(m) for m in re.findall(r"migrations? [^.;]*?001 à (\d{3})", text)]
    assert cited and all(n == numbers[-1] for n in cited), (cited, numbers)
    assert "toutes les migrations de db/migrations" in text
