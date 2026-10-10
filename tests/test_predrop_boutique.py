"""Pré-drop, étape « boutique » (décision de la propriétaire du 6.10.2026) : fiche jumelle « Réservation garantie ».

Couvre :

* la charge Shopify de la fiche de réservation (:func:`pokeshop.publish.build_predrop_publication`) : liste blanche
  des champs publics, métachamps du pré-drop (date du drop, statut des réservations, fiche liée), une seule variante
  au SKU ``-RESA-<date>`` et au prix pré-drop figé, jamais de quota, de coût, de marge ni de compte à rebours ;
* les blocages (prix hors bornes, coût inconnu, plancher, quarantaine, stop-loss, FICTIF en boutique réelle, fiche
  ``-PRECO``, validations de la propriétaire) et le retrait protecteur (brouillon) au drop, à la fermeture, sur blocage ;
* les métachamps du pré-drop sur la fiche normale (:func:`pokeshop.publish.build_publication`) ;
* le service (:meth:`pokeshop.sync.SyncService.publish_predrop`) : simulation par défaut, écriture vérifiée sur une
  boutique de test, inventaire en compare-and-swap (baisse protectrice, hausse soumise au niveau), registre distinct ;
* la route ``POST /predrop/{predrop_id}/publish`` (rôles, états), les champs internes de ``GET /predrop/offers`` et
  le rattachement des lignes ``-RESA-`` à l'expédition (``/orders/shipped``), y compris ``<commande>#2``.

Données, jetons, montants et identifiants FICTIFS.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import httpx
import jetons_roles as JR
import pytest
import test_predrop as PD
import test_publish as TP
import test_sync as TS
from pokeshop.publish import (
    PREDROP_PRODUCT_TYPE,
    PREDROP_TAG,
    PREDROP_TITLE_PREFIX,
    PUBLIC_METAFIELDS,
    PlanOutcome,
    PredropPublication,
    PublishedState,
    ShopStatus,
    assert_protective_payload,
    build_predrop_publication,
    predrop_reservation_handle,
    predrop_reservation_sku,
    reservation_publication_key,
    sensitive_violations,
)
from pokeshop.shopify_client import RemoteInventoryLevel
from pokeshop.sync import ShopPublication, predrop_inventory_target
from pydantic import ValidationError

DROP = date(2026, 10, 20)
COST = D("100.00")  # coût rendu FICTIF
DROP_PRICE = TP.ENGINE_PRICE  # 154.90 : prix du moteur au coût 100
PRE_PRICE = D("169.90")  # ≤ 154.90 × 1,10 = 170.39
RESA_SKU = "DSP-FICTIF_ALPHA-FR-RESA-20261020"
GID = "gid://shopify/Product/77"
LIVE = PublishedState(shopify_product_id=GID, status=ShopStatus.ACTIVE, price_chf=PRE_PRICE)


def predrop(**kw: Any) -> PredropPublication:
    base: dict[str, Any] = dict(
        predrop_id="PD-FICTIF-P1-20261020", product_key="FICTIF-P1", drop_date=DROP, phase="ouvertes",
        predrop_price=PRE_PRICE, drop_price=DROP_PRICE, per_customer_limit=1, reservations_available=3,
        reservations_committed=0,
    )  # fmt: skip
    base.update(kw)
    return PredropPublication(**base)


def closed(**kw: Any) -> PredropPublication:
    return predrop(phase="fermees", reservations_available=0, **kw)


def resa_plan(item: Any = None, pre: PredropPublication | None = None, **kw: Any) -> Any:
    item = item or TP.listing(approved=True)
    kw.setdefault("params", TP.PARAMS)
    kw.setdefault("landed_cost", COST)
    kw.setdefault("table", TP.TABLE)
    kw.setdefault("validations", item.validations)
    return build_predrop_publication(item.listing, pre or predrop(), **kw)


def mf(product_input: dict[str, Any]) -> dict[str, str]:
    return {m["key"]: m["value"] for m in product_input["metafields"]}


# ================================================================================ charge de la fiche de réservation


def test_reservation_payload_passes_the_whitelist_and_carries_only_public_predrop_fields() -> None:
    p = resa_plan()
    assert p.outcome is PlanOutcome.SEND_ACTIVE and p.action == "PUBLISH_NEW_PRODUCT"
    assert p.target_status is ShopStatus.ACTIVE and p.identifier == {"handle": p.handle}
    assert p.price_chf == PRE_PRICE and p.price_source == "UNCHANGED" and p.blockers == () and p.reviews == ()
    pi = p.product_input
    assert pi is not None and sensitive_violations(pi) == [] and p.violations == ()
    assert pi["title"].startswith(PREDROP_TITLE_PREFIX) and pi["productType"] == PREDROP_PRODUCT_TYPE
    assert pi["handle"] == p.handle and p.handle.endswith("-reservation-garantie")
    (variant,) = pi["variants"]
    assert variant["price"] == "169.90" and variant["inventoryPolicy"] == "DENY"
    assert variant["inventoryItem"] == {"sku": RESA_SKU, "tracked": True}
    assert predrop_reservation_sku("DSP-FICTIF_ALPHA-FR", DROP) == RESA_SKU
    assert PREDROP_TAG in pi["tags"] and "statut:precommande" in pi["tags"]
    m = mf(pi)
    assert set(m) <= set(PUBLIC_METAFIELDS)
    assert m["date_drop"] == "2026-10-20" and m["reservation_statut"] == "ouvertes"
    assert m["statut_stock"] == "precommande" and m["quantite_max"] == "1"  # limite par client, jamais un quota
    normal = m["fiche_liee"]
    assert predrop_reservation_handle(normal) == p.handle and not normal.endswith("-reservation-garantie")
    # Revue pré-drop (PDL-02) : les deux prix FIGÉS du moteur sont publiés en métachamps (lus par l'encart « Au drop »)
    # — exactement les prix natifs des deux fiches, jamais un autre montant.
    assert m["prix_drop"] == "154.90" and m["prix_reservation"] == "169.90"
    text = json.dumps({k: v for k, v in pi.items() if k != "metafields"}, ensure_ascii=False).lower()
    for forbidden in ("quota", "committed", "available", "restant", "plus que", "dernière", "compte à rebours",
                      "coût", "cost", "marge", "margin", "100.00", "154.90", "contribution"):  # fmt: skip
        assert forbidden not in text, forbidden  # ni coût, ni marge, ni prix du drop hors métachamp, ni fausse urgence
    full = json.dumps(pi, ensure_ascii=False).lower()
    assert "100.00" not in full and "contribution" not in full and "marge" not in full


def test_normal_handle_comes_from_the_engine_registry_when_given() -> None:
    p = resa_plan(normal_handle="display-alpha-publie")
    assert p.handle == "display-alpha-publie-reservation-garantie"
    assert mf(p.product_input)["fiche_liee"] == "display-alpha-publie"


def test_priority_window_and_closed_reservations() -> None:
    prio = resa_plan(pre=predrop(phase="prioritaire"))
    assert mf(prio.product_input)["reservation_statut"] == "prioritaire" and PREDROP_TAG in prio.product_input["tags"]
    # Quota épuisé, fiche en ligne : reste visible « Réservations fermées », non achetable (statut rupture).
    full = resa_plan(pre=closed(reservations_committed=3), published=LIVE)
    assert full.outcome is PlanOutcome.SEND_ACTIVE and full.action == "UPDATE_APPROVED_PRODUCT"
    assert full.identifier == {"id": GID}
    m = mf(full.product_input)
    assert m["reservation_statut"] == "fermees" and m["statut_stock"] == "rupture"
    assert PREDROP_TAG not in full.product_input["tags"] and "statut:precommande" not in full.product_input["tags"]
    # Jamais créée fermée.
    never = resa_plan(pre=closed())
    assert never.outcome is PlanOutcome.NOT_SENT and never.product_input is None and "PREDROP_CLOSED" in never.reviews


def test_retired_reservation_is_unpublished_by_its_identifier_and_never_created() -> None:
    pre = closed(retired=True)
    live = resa_plan(pre=pre, published=LIVE)
    assert live.outcome is PlanOutcome.UNPUBLISH and live.action == "UNPUBLISH_PRODUCT"
    assert live.product_input == {"status": "DRAFT"} and live.identifier == {"id": GID}
    assert_protective_payload(live.product_input)
    assert "PREDROP_RETIRED" in live.reviews and live.price_chf is None
    assert resa_plan(pre=pre).outcome is PlanOutcome.NOT_SENT
    draft = PublishedState(shopify_product_id=GID, status=ShopStatus.DRAFT)
    assert resa_plan(pre=pre, published=draft).outcome is PlanOutcome.NOT_SENT  # déjà en brouillon : rien à écrire


@pytest.mark.parametrize(
    ("kw", "item_kw", "blocker"),
    [
        ({"pre": predrop(predrop_price=D("170.90"))}, {}, "PREDROP_PRICE_INVALID"),  # > prix drop × 1,10
        ({"pre": predrop(predrop_price=D("149.90"))}, {}, "PREDROP_PRICE_INVALID"),  # < prix drop
        ({"landed_cost": None}, {}, "PREDROP_COST_UNKNOWN"),
        ({"landed_cost": D("0")}, {}, "PREDROP_COST_UNKNOWN"),
        ({"landed_cost": D("160.00")}, {}, "PREDROP_PRICE_BELOW_FLOOR"),
        ({"quarantined": True}, {}, "QUARANTINED"),
        ({"stoploss_blocked": True}, {}, "STOPLOSS_PRODUCT"),
        ({"real_shop": True}, {}, "FICTIF_DATA"),  # fiche FICTIVE : jamais en boutique réelle
        ({"pre": predrop(product_key="FICTIF-P2")}, {}, "PREDROP_LISTING_MISMATCH"),
        ({}, {"public_sku": "DSP-FICTIF_ALPHA-FR-PRECO", "stock_status": TP.StockStatus.PRECOMMANDE},
         "PREDROP_ON_PREORDER_LISTING"),
    ],
)
def test_hard_blockers_never_publish_and_unpublish_a_live_reservation(kw: dict[str, Any], item_kw: dict[str, Any],
                                                                     blocker: str) -> None:
    item = TP.listing(approved=True, **item_kw)
    new = resa_plan(item, **kw)
    assert new.outcome is PlanOutcome.NOT_SENT and new.product_input is None and blocker in new.blockers
    live = resa_plan(item, published=LIVE, **kw)
    assert live.outcome is PlanOutcome.UNPUBLISH and live.product_input == {"status": "DRAFT"}


def test_owner_validations_on_the_exact_content_are_required() -> None:
    refused = resa_plan(TP.listing(approved=False))
    assert refused.outcome is PlanOutcome.NOT_SENT and "NOT_APPROVED" in refused.reviews
    assert resa_plan(TP.listing(approved=False), published=LIVE).outcome is PlanOutcome.UNPUBLISH
    other = TP.listing(approved=True, content_text="24 boosters")
    outdated = resa_plan(TP.listing(approved=True), validations=other.validations)
    assert outdated.outcome is PlanOutcome.NOT_SENT and "VALIDATION_OUTDATED" in outdated.reviews
    assert resa_plan(validations=None).outcome is PlanOutcome.NOT_SENT
    # Contenu non validé : rien n'est créé ni écrasé ; une fiche en ligne garde son état (revue humaine).
    unvalidated = TP.listing(approved=True, content_validated=False)
    for published in (None, LIVE):
        p = resa_plan(unvalidated, published=published)
        assert p.outcome is PlanOutcome.NOT_SENT and p.product_input is None and "CONTENT_NOT_VALIDATED" in p.reviews


def test_supplier_term_in_the_content_blocks_the_reservation_payload() -> None:
    item = TP.listing(approved=True, description_html="<p>Display FICTIF livré par Grossiste Fictif SA, neuf et scellé.</p>")
    p = resa_plan(item, sensitive_terms=("Grossiste Fictif",))
    assert p.outcome is PlanOutcome.NOT_SENT and p.product_input is None
    assert "SENSITIVE_FIELD" in p.blockers and p.violations


@pytest.mark.parametrize(
    "mutate",
    [
        lambda pi: pi["metafields"].__setitem__(-4, {**pi["metafields"][-4], "value": "plus que 2"}),
        lambda pi: pi["metafields"].__setitem__(-4, {**pi["metafields"][-4], "value": "bientot"}),
        lambda pi: pi["metafields"].__setitem__(-5, {**pi["metafields"][-5], "value": "20.10.2026"}),
        lambda pi: pi["metafields"].__setitem__(-3, {**pi["metafields"][-3], "value": "Fiche Liée !"}),
        lambda pi: pi["metafields"].__setitem__(-2, {**pi["metafields"][-2], "value": "154.90 (-10 %)"}),
        lambda pi: pi["metafields"].__setitem__(-1, {**pi["metafields"][-1], "value": "plus que 2"}),
        lambda pi: pi["metafields"].append({"namespace": "boutique", "key": "quota_restant", "type": "number_integer",
                                            "value": "2"}),
        lambda pi: pi["metafields"].append({"namespace": "boutique", "key": "fermeture", "type": "single_line_text_field",
                                            "value": "2026-10-19T23:59"}),
        lambda pi: pi["tags"].append("plus que 2"),
        lambda pi: pi["variants"][0].__setitem__("compareAtPrice", "209.90"),
    ],
)
def test_whitelist_rejects_a_tampered_reservation_payload(mutate: Any) -> None:
    pi = copy.deepcopy(resa_plan().product_input)
    assert [m["key"] for m in pi["metafields"][-5:]] == ["date_drop", "reservation_statut", "fiche_liee", "prix_drop",
                                                         "prix_reservation"]
    mutate(pi)
    assert sensitive_violations(pi)


def test_predrop_publication_invariants() -> None:
    with pytest.raises(ValidationError):
        predrop(retired=True)  # retiré => fermé
    with pytest.raises(ValidationError):
        predrop(phase="fermees")  # fermé => aucune unité publiée
    with pytest.raises(ValidationError):
        predrop(per_customer_limit=3)
    with pytest.raises(ValidationError):
        predrop(predrop_price=D("0"))
    assert predrop().accepting and predrop(phase="prioritaire").accepting
    assert not closed().accepting and not closed(retired=True).accepting


# ======================================================================================== fiche normale


def test_normal_fiche_carries_the_three_predrop_metafields_and_nothing_else_changes() -> None:
    base = TP.plan(TP.existing())
    with_pd = TP.plan(TP.existing(), predrop=predrop())
    assert base.outcome is with_pd.outcome is PlanOutcome.SEND_ACTIVE
    assert base.price_chf == with_pd.price_chf and base.product_input["variants"] == with_pd.product_input["variants"]
    added = {k: v for k, v in mf(with_pd.product_input).items() if k not in mf(base.product_input)}
    assert added == {"date_drop": "2026-10-20", "reservation_statut": "ouvertes",
                     "fiche_liee": predrop_reservation_handle(base.handle), "prix_drop": "154.90",
                     "prix_reservation": "169.90"}  # fmt: skip
    assert sensitive_violations(with_pd.product_input) == []
    assert with_pd.product_input["title"] == base.product_input["title"]  # jamais « Réservation garantie » ici
    # Autre référence, ou fiche -PRECO : aucun métachamp de pré-drop.
    other = TP.plan(TP.existing(), predrop=predrop(product_key="FICTIF-P2"))
    assert mf(other.product_input) == mf(base.product_input)
    preco = TP.existing(public_sku="DSP-FICTIF_ALPHA-FR-PRECO", stock_status=TP.StockStatus.PRECOMMANDE)
    preco_plan = TP.plan(preco, predrop=predrop())
    assert preco_plan.product_input is None or "date_drop" not in mf(preco_plan.product_input)


# ========================================================================================= inventaire


@pytest.mark.parametrize(
    ("pre", "committed", "target"),
    [
        (predrop(reservations_available=3, reservations_committed=1), 1, 3),
        (predrop(reservations_available=3, reservations_committed=1), 0, 3),
        (predrop(reservations_available=3, reservations_committed=1), 2, 2),  # une commande pas encore relevée
        (predrop(reservations_available=3, reservations_committed=1), 9, 0),
        (predrop(phase="prioritaire", reservations_available=2), 0, 2),
        (closed(reservations_committed=4), 0, 0),
        (closed(retired=True), 0, 0),
    ],
)
def test_inventory_target_never_promises_beyond_the_quota(pre: PredropPublication, committed: int, target: int) -> None:
    remote = RemoteInventoryLevel(inventory_item_id=TS.ITEM, available=5, committed=committed)
    assert predrop_inventory_target(pre, remote) == target


# ============================================================================================ service


class ResaShop(TS.FakeShop):
    """Boutique de test : la lecture par identifiant renvoie le SKU réellement écrit (fiche de réservation)."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        resp = super().__call__(request)
        body = json.loads(request.content)
        if "productByIdentifier" not in body["query"] or resp.status_code != 200:
            return resp
        data = resp.json()
        node = data["data"]["productByIdentifier"]
        if node is None:
            return resp
        ident = body["variables"]["identifier"]
        stored = self.products.get(ident.get("handle") or ident.get("id")) or {}
        variant = (stored.get("variants") or [{}])[0]
        node["variants"]["nodes"][0]["sku"] = (variant.get("inventoryItem") or {}).get("sku", "x")
        return httpx.Response(200, json=data)


def env(level: int = 3) -> TS.Env:
    e = TS.Env(level=level)
    e.shop.__class__ = ResaShop
    return e


def publish(e: TS.Env, pre: PredropPublication, **kw: Any) -> Any:
    item = TS.listing()
    kw.setdefault("validations", TS.owner_validations(item, approved=True))
    kw.setdefault("location_id", TS.LOC)
    return e.sync.publish_predrop(item, pre, params=TS.RULES.pricing, landed_cost=COST, table=TS.TABLE, **kw)


def test_service_simulates_by_default_without_any_shop_call() -> None:
    e = env()
    report = publish(e, predrop())
    assert report.dry_run and report.plan_outcome == "SEND_ACTIVE" and report.action == "PUBLISH_NEW_PRODUCT"
    assert report.gate_allowed and report.verified and not report.written and report.critical_errors == ()
    assert report.inventory_action == "SKIPPED" and report.inventory_target == 3 and not report.inventory_written
    assert e.shop.requests == []
    assert e.sync.publications.get(reservation_publication_key("FICTIF-P1")) is None
    assert e.audit.events(action="sync.predrop_publish")
    dumped = report.model_dump_json()
    assert "landed" not in dumped and "contribution" not in dumped and "100.00" not in dumped


def test_service_writes_verifies_then_follows_the_quota_and_retires_at_the_drop() -> None:
    e = env()
    first = publish(e, predrop(), dry_run=False)
    assert first.written and first.verified and first.critical_errors == (), first
    assert first.inventory_action == "SET" and first.inventory_written and e.shop.levels[TS.ITEM]["available"] == 3
    key = reservation_publication_key("FICTIF-P1")
    known = e.sync.publications.get(key)
    assert known is not None and known.status == "ACTIVE" and known.handle == first.handle
    stored = e.shop.products[first.handle]
    assert stored["variants"][0]["inventoryItem"]["sku"] == RESA_SKU and stored["productType"] == PREDROP_PRODUCT_TYPE
    assert e.sync.publications.get("FICTIF-P1") is None  # la fiche normale n'est pas touchée
    assert list(e.history.events("FICTIF-P1")) == []  # aucun prix inscrit dans l'historique de la fiche normale
    # Quota épuisé : mise à jour « fermées », inventaire ramené à 0 (baisse protectrice).
    full = publish(e, closed(reservations_committed=3), dry_run=False)
    assert full.action == "UPDATE_APPROVED_PRODUCT" and full.written and full.verified
    assert full.inventory_action == "SET" and e.shop.levels[TS.ITEM]["available"] == 0
    assert mf(e.shop.products[first.handle])["reservation_statut"] == "fermees"
    # Drop atteint : retrait (brouillon) par identifiant.
    gone = publish(e, closed(retired=True, reservations_committed=3), dry_run=False)
    assert gone.plan_outcome == "UNPUBLISH" and gone.written and gone.verified
    assert e.sync.publications.get(key).status == "DRAFT"
    assert e.shop.applied[-1] == {"productSet": {"status": "DRAFT"}}


def test_live_reservation_inventory_is_lowered_even_when_the_update_is_refused() -> None:
    """Niveau 1 : la mise à jour de la fiche est refusée, mais l'inventaire suit le registre (baisse protectrice)."""
    e = env(level=1)
    plan = build_predrop_publication(TS.listing(), predrop(), params=TS.RULES.pricing, landed_cost=COST, table=TS.TABLE,
                                     validations=TS.owner_validations(TS.listing(), approved=True))  # fmt: skip
    e.shop.products[plan.handle] = plan.product_input
    e.shop.levels[TS.ITEM]["available"] = 3
    e.sync.publications.record(ShopPublication(
        product_id=reservation_publication_key("FICTIF-P1"), shopify_product_id="gid://shopify/Product/7", status="ACTIVE",
        handle=plan.handle, run_id="PREDROP-FICTIF-0", recorded_at=TS.SOURCE_NOW - timedelta(days=1), price_chf=PRE_PRICE))  # fmt: skip
    lowered = publish(e, closed(reservations_committed=3), dry_run=False)
    assert lowered.gate_allowed is False and not lowered.written
    assert lowered.inventory_action == "SET" and e.shop.levels[TS.ITEM]["available"] == 0
    # Une hausse reste soumise à la porte (niveau 2) : refusée au niveau 1.
    raised = publish(e, predrop(reservations_available=2), dry_run=False)
    assert raised.inventory_action == "REFUSED" and e.shop.levels[TS.ITEM]["available"] == 0


def test_verification_mismatch_is_a_critical_incident_and_nothing_else_is_written() -> None:
    e = env()
    e.shop.price_override = "1.00"
    report = publish(e, predrop(), dry_run=False)
    assert report.written and report.verified is False and report.critical_errors
    assert report.inventory_action == "SKIPPED" and e.shop.levels[TS.ITEM]["available"] == 0
    assert e.sync.publications.get(reservation_publication_key("FICTIF-P1")) is None
    assert report.incident_ids


def test_real_write_without_location_is_reported_never_guessed() -> None:
    e = env()
    report = publish(e, predrop(), dry_run=False, location_id=None)
    assert report.written and report.verified and report.inventory_action == "SKIPPED"
    assert any("emplacement" in c for c in report.critical_errors)
    assert e.shop.levels[TS.ITEM]["available"] == 0


# ================================================================================================ API

SYNC_ROLE = JR.headers("n8n-01-sync")


def content_validated(client: Any) -> None:
    """La propriétaire confirme aussi le contenu de la fiche (exigé pour toute fiche en ligne, réservation comprise)."""
    ok = client.post("/catalog/approvals", headers=PD.OWNER, json={
        "product_id": PD.P1, "approved": True, "content_validated": True,
        "reason": "fiche et contenu FICTIFS relus par la propriétaire"})  # fmt: skip
    assert ok.status_code == 201, ok.text


def test_publish_route_roles_states_and_simulation(tmp_path: Path) -> None:
    client, svc, clock = PD.ready(tmp_path, priority_window_hours=24)
    assert client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={}).status_code == 404
    assert PD.open_predrop(client).status_code == 201
    # Contenu non confirmé par la propriétaire : rien n'est publié (revue humaine).
    unconfirmed = PD.body(client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={}))["report"]
    assert unconfirmed["plan_outcome"] == "NOT_SENT" and "CONTENT_NOT_VALIDATED" in unconfirmed["reviews"]
    content_validated(client)
    resp = client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={})
    assert resp.status_code == 200, resp.text
    data = PD.body(resp)
    report = data["report"]
    assert data["simulation"] is True and data["phase"] == "prioritaire" and data["retired"] is False
    assert report["plan_outcome"] == "SEND_ACTIVE" and report["action"] == "PUBLISH_NEW_PRODUCT"
    assert report["price_chf"] == "229.90" and not report["written"] and report["critical_errors"] == []
    assert report["handle"].endswith("-reservation-garantie")
    text = resp.text.lower()
    assert "landed" not in text and "140" not in text and "marge" not in text
    assert client.post(f"/predrop/{PD.PID}/publish", headers=JR.headers("site-integrations"), json={}).status_code == 200
    # Jeton commun et autres rôles : refusés (écriture).
    assert client.post(f"/predrop/{PD.PID}/publish", headers=PD.H, json={}).status_code == 403
    for role in ("acquisition", "chef-de-projet", "finance-pricing", "n8n-02-commandes", "catalogue"):
        assert client.post(f"/predrop/{PD.PID}/publish", headers=JR.headers(role), json={}).status_code == 403, role
    # Champ décisif fourni par l'appelant : refusé (le moteur calcule tout).
    for forged in ({"phase": "ouvertes"}, {"price": "1.00"}, {"reservations_available": 99}):
        assert client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json=forged).status_code == 422, forged
    # Écriture demandée, moteur en simulation (POKESHOP_DRY_RUN par défaut) : rien n'est écrit.
    real = PD.body(client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={"dry_run": False}))
    assert real["simulation"] is True and real["report"]["written"] is False
    assert svc.audit.events(action="predrop.publish")
    # Jour du drop : retrait (rien en ligne dans le registre : rien à écrire).
    clock.now = datetime.combine(PD.DROP, datetime.min.time(), tzinfo=PD.TZ) + timedelta(hours=8)
    gone = PD.body(client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={}))
    assert gone["retired"] is True and gone["phase"] == "fermees" and gone["report"]["plan_outcome"] == "NOT_SENT"


def test_publish_route_refuses_a_predrop_waiting_for_the_owner(tmp_path: Path) -> None:
    client, _svc, _ = PD.ready(tmp_path)
    pending = PD.open_predrop(client, headers=JR.HF, market=None)
    assert PD.body(pending)["predrop"]["status"] == "PENDING_OWNER"
    assert client.post(f"/predrop/{PD.PID}/publish", headers=SYNC_ROLE, json={}).status_code == 409


def test_offers_expose_the_reservation_sku_handle_and_alert_tag_internally_only(tmp_path: Path) -> None:
    client, _svc, _ = PD.ready(tmp_path, priority_window_hours=24)
    assert PD.open_predrop(client).status_code == 201
    data = PD.body(client.get("/predrop/offers", headers=PD.H))
    (view,) = data["internal"]
    assert view["reservation_sku"] == RESA_SKU and view["phase"] == "prioritaire" and view["retired"] is False
    assert view["reservation_handle"] == predrop_reservation_handle(view["normal_handle"])
    assert view["alert_tag"] == f"alerte-produit:{view['normal_handle']}"
    offer = data["offers"][0]
    assert tuple(offer) == PD.PUBLIC_OFFER_FIELDS
    for internal in ("reservation_sku", "alert_tag", "reservation_handle", "phase"):
        assert internal not in offer


def _shipped(order_id: str, label: str, sku: str = RESA_SKU) -> dict[str, Any]:
    return {"order_id": order_id, "paid_at": PD.NOW.isoformat(), "net_sales_ht": "212.67", "payment_fees": "6.05",
            "shipping_cost_actual": "7.40", "shipping_label_ref": label, "source": "webhook Shopify FICTIF",
            "lines": [{"public_sku": sku, "qty": 1}]}  # fmt: skip


def test_shipped_reservation_lines_are_resolved_and_split_orders_are_recognized(tmp_path: Path) -> None:
    client, svc, clock = PD.ready(tmp_path)
    assert PD.open_predrop(client).status_code == 201
    assert PD.body(PD.reserve(client, "FICTIF-CMD-1", "a"))["reservation"]["status"] == "CONFIRMED"
    assert PD.body(PD.reserve(client, "FICTIF-CMD-2#2", "b"))["reservation"]["status"] == "CONFIRMED"
    clock.now = PD.NOW + timedelta(days=12)
    for order_id, label in (("FICTIF-CMD-1", "FICTIF-ETIQ-1"), ("FICTIF-CMD-2", "FICTIF-ETIQ-2")):
        resp = client.post("/orders/shipped", headers=JR.HORDERS, json=_shipped(order_id, label))
        assert resp.status_code == 201, resp.text
        assert not PD.body(resp)["unresolved_lines"], order_id  # SKU -RESA- rattaché à la référence du pré-drop
        assert svc.orders.get(order_id).recognized_at == PD.NOW + timedelta(days=12), order_id
    assert PD.body(client.get("/northstar", headers=PD.H))["predrop_collected_not_recognized_chf"] == "0.00"
    # SKU de réservation inconnu (aucun pré-drop à cette date) : ligne non rattachée, jamais refusée.
    unknown = client.post("/orders/shipped", headers=JR.HORDERS,
                          json=_shipped("FICTIF-CMD-3", "FICTIF-ETIQ-3", sku="DSP-FICTIF_ALPHA-FR-RESA-20991231"))
    assert unknown.status_code == 201 and PD.body(unknown)["unresolved_lines"]
