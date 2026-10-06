"""Pré-drop : tests de non-régression de la revue adverse (ARG-01 à ARG-07, PDL-01 à PDL-13).

Chaque test reprend le scénario de la revue (commande mixte, versement du prestataire en transit, fiche jumelle et
commande payée non relevée, quantité payée hors bornes, gel des achats, frais de livraison, configuration signée
modifiée entre la demande et la validation, réception avant le drop, prix normal ≠ prix du drop figé, suspension après
paiement, réserve de sécurité, report de date, date du drop, délai d'annulation) et vérifie le comportement corrigé.

Données, jetons, montants et identifiants FICTIFS.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import jetons_roles as JR
import test_orchestration_f4 as F
import test_predrop as T
import test_predrop_boutique as PB
import test_publish as TP
from pokeshop.audit import InMemoryStateJournal
from pokeshop.northstar import OrderLine, OrderRegister, ShippedOrder
from pokeshop.predrop import (
    PREDROP_IN_TRANSIT_LABEL,
    FirmAllocation,
    PredropRegistry,
    compute_prices,
    refund_email_draft,
    reservation_order_base,
)
from pokeshop.publish import (
    PlanOutcome,
    PublishBlocker,
    PublishedState,
    ShopStatus,
    reservation_publication_key,
)
from pokeshop.shopify_client import RemoteInventoryLevel
from pokeshop.sync import ShopPublication, predrop_inventory_target, predrop_sellable

NOW = T.NOW
TZ = T.TZ
P1 = T.P1
PID = T.PID
RESA_SKU = T.RESA_SKU
IN_STOCK_SKU = "DSP-FICTIF_AUTRE-FR"  # article en stock d'un panier mixte (ligne non rattachée : jamais un refus)


def shipped(order_id: str, sku: str, label: str, *, qty: int = 1, paid_at: datetime = NOW) -> dict[str, Any]:
    return {"order_id": order_id, "paid_at": paid_at.isoformat(), "net_sales_ht": "40.00", "payment_fees": "1.20",
            "shipping_cost_actual": "7.40", "shipping_label_ref": label, "source": "webhook Shopify FICTIF",
            "lines": [{"public_sku": sku, "qty": qty}]}  # fmt: skip


def reserve(client: Any, order_id: str, customer: str = "a", *, qty: int = 1, amount: str | None = None,
            shipping: str | None = None, paid_at: datetime | None = None) -> Any:
    payload: dict[str, Any] = {
        "predrop_id": PID, "order_id": order_id, "customer_ref": T.cref(customer), "qty": qty,
        "amount_paid_ttc": amount if amount is not None else str(D("229.90") * qty),
        "paid_at": (paid_at or NOW).isoformat(), "priority_access": False,
    }  # fmt: skip
    if shipping is not None:
        payload["shipping_paid_ttc"] = shipping
    return client.post("/predrop/reservations", headers=JR.HORDERS, json=payload)


def states(client: Any) -> dict[str, str]:
    return {r["order_id"]: r["state"] for r in T.body(client.get("/predrop/reservations", headers=T.H))["reservations"]}


def debt(client: Any) -> str:
    return T.body(client.get("/predrop/reservations", headers=T.H))["collected_not_delivered"]["total_chf"]


# ====================================================================================== ARG-01 : ligne expédiée


def test_arg01_a_mixed_cart_partial_shipment_never_ships_the_reservation(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    assert T.body(reserve(client, "FICTIF-A", "a"))["reservation"]["status"] == "CONFIRMED"
    assert T.body(reserve(client, "FICTIF-MIX-1", "b", paid_at=NOW + timedelta(minutes=1)))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(minutes=30)
    # L'article en stock du panier part tout de suite (envoi 1, sans la ligne de réservation).
    first = client.post("/orders/shipped", headers=JR.HORDERS, json=shipped("FICTIF-MIX-1", IN_STOCK_SKU, "FICTIF-ETIQ-M1"))
    assert first.status_code == 201, first.text
    # Commande d'une réservation : ventes de l'envoi reconnues à leur expédition (jamais au paiement).
    assert svc.orders.get("FICTIF-MIX-1").recognized_at == NOW + timedelta(minutes=30)
    assert states(client)["FICTIF-MIX-1"] == "CONFIRMED" and debt(client) == "459.80"
    data = T.photo(client, clock.now, capital=False, bank="2459.80")
    assert data["sources"]["precommandes"]["predrop_derivees_chf"] == "459.80"
    # Le même identifiant avec un autre contenu : 409 avec l'indication de l'envoi suivant.
    again = client.post("/orders/shipped", headers=JR.HORDERS, json=shipped("FICTIF-MIX-1", RESA_SKU, "FICTIF-ETIQ-M2"))
    assert again.status_code == 409 and "FICTIF-MIX-1/envoi-<n>" in T.body(again)["erreur"]
    # À la réception, l'envoi réel de la réservation s'enregistre (envoi 2) : vente reconnue à cette date.
    clock.now = NOW + timedelta(days=12)
    second = client.post("/orders/shipped", headers=JR.HORDERS,
                         json=shipped("FICTIF-MIX-1/envoi-2", RESA_SKU, "FICTIF-ETIQ-M2"))
    assert second.status_code == 201, second.text
    assert T.body(second)["predrop_unregistered_lines"] == []
    assert svc.orders.get("FICTIF-MIX-1/envoi-2").recognized_at == NOW + timedelta(days=12)
    assert states(client) == {"FICTIF-A": "CONFIRMED", "FICTIF-MIX-1": "SHIPPED"} and debt(client) == "229.90"
    # La réservation A, non expédiée, reste annulable (l'expédition d'une autre commande ne compte pas).
    clock.now = NOW + timedelta(days=1)
    cancel = client.post("/predrop/reservations/FICTIF-A/cancel", headers=JR.HOPS,
                         json={"reason": "CUSTOMER_CANCELLATION", "request_ref": "FICTIF-TICKET-A"})
    assert cancel.status_code == 201
    # Ligne de réservation expédiée : plus d'annulation libre (retour volontaire).
    late = client.post("/predrop/reservations/FICTIF-MIX-1/cancel", headers=JR.HOPS,
                       json={"reason": "CUSTOMER_CANCELLATION", "request_ref": "FICTIF-TICKET-M"})
    assert late.status_code == 409 and "retour volontaire" in T.body(late)["erreur"]


def test_arg01_reduction_keeps_strict_payment_order_after_an_unrelated_shipment(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    reserve(client, "FICTIF-A", "a")
    reserve(client, "FICTIF-MIX-1", "b", paid_at=NOW + timedelta(minutes=1))
    clock.now = NOW + timedelta(minutes=30)
    assert client.post("/orders/shipped", headers=JR.HORDERS,
                       json=shipped("FICTIF-MIX-1", IN_STOCK_SKU, "FICTIF-ETIQ-M1")).status_code == 201
    cut = client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                      json={"new_qty": 1, "supplier_confirmation_ref": "FICTIF-REDUC-MIX", "reason": "livraison partielle FICTIVE"})
    plan = T.body(cut)["plan"]
    assert plan["kept"] == ["FICTIF-A"] and plan["refunded"] == ["FICTIF-MIX-1"]  # A payée avant : servie


def test_arg01_a_not_served_refund_stays_a_debt_when_other_items_of_the_order_ship(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    assert T.body(reserve(client, "FICTIF-L1", "a"))["reservation"]["status"] == "CONFIRMED"
    second = T.body(reserve(client, "FICTIF-L2", "a", paid_at=NOW + timedelta(minutes=1)))
    assert second["reservation"]["status"] == "NOT_SERVED" and second["refund"]["status"] == "PENDING_OWNER"
    clock.now = NOW + timedelta(minutes=30)
    assert client.post("/orders/shipped", headers=JR.HORDERS,
                       json=shipped("FICTIF-L2", IN_STOCK_SKU, "FICTIF-ETIQ-L2")).status_code == 201
    assert states(client)["FICTIF-L2"] == "REFUND_PENDING" and debt(client) == "459.80"
    data = T.photo(client, clock.now, capital=False, bank="2459.80")
    assert data["sources"]["precommandes"]["predrop_derivees_chf"] == "459.80"
    assert data["cash_available_chf"] == "3500.00"  # jamais surévalué par l'expédition d'un autre article


def test_arg01_each_entry_is_served_by_its_own_line_and_shipments_add_up() -> None:
    """Commande à deux pré-drops (entrées <commande> et <commande>#2) reçus à des dates différentes, et quantité 2
    expédiée en deux envois : chaque réservation n'est expédiée que par SA ligne, quantités cumulées."""
    registry = PredropRegistry(store=InMemoryStateJournal("predrop"))
    orders = OrderRegister()
    prices = compute_prices(D("140"), T.PARAMS, T.signed_config(per_customer_limit=2), market_ref=D("250"))
    for key, sku in (("FICTIF-P1", "DSP-FICTIF_ALPHA-FR"), ("FICTIF-P2", "DSP-FICTIF_BETA-FR")):
        registry.set_allocation(FirmAllocation(product_key=key, supplier_id=T.SUPPLIER, qty=20,
                                               supplier_confirmation_ref=f"FICTIF-CONF-{key}", source="FICTIF",
                                               recorded_by="propriétaire", recorded_at=NOW))  # fmt: skip
        registry.open(T._predrop(prices, predrop_id=f"PD-{key}", product_key=key, public_sku=sku,
                                 allocation_ref=f"FICTIF-CONF-{key}", per_customer_limit=2))  # fmt: skip
    for entry, pid, qty in (("FICTIF-DUO", "PD-FICTIF-P1", 2), ("FICTIF-DUO#2", "PD-FICTIF-P2", 1)):
        registry.record_reservation(predrop_id=pid, order_id=entry, customer_ref=T.cref("duo"), qty=qty,
                                    amount_paid_ttc=D("229.90") * qty, paid_at=NOW, priority_access=True,
                                    recorded_by="n8n-02-commandes", at=NOW, enabled=True, blocked_reason=None,
                                    autonomy_level=1)  # fmt: skip

    def is_shipped(res: Any) -> bool:  # même règle que l'API : ligne -RESA- du pré-drop, quantités cumulées
        return orders.shipped_units(reservation_order_base(res.order_id), registry.get(res.predrop_id).sku) >= res.qty

    sku1, sku2 = registry.get("PD-FICTIF-P1").sku, registry.get("PD-FICTIF-P2").sku

    def ship(order_id: str, sku: str, qty: int, at: datetime) -> None:
        orders.record_shipped(ShippedOrder(
            order_id=order_id, paid_at=NOW, net_sales_ht=D("200"), payment_fees=D("5"), shipping_cost_actual=D("7.40"),
            shipping_label_ref=f"ETIQ-{order_id}", source="FICTIF", recorded_by="n8n-02-commandes", recorded_at=at,
            lines=(OrderLine(public_sku=sku, product_key="k", qty=qty),), recognized_at=at), None)  # fmt: skip

    ship("FICTIF-DUO", sku2, 1, NOW + timedelta(days=3))  # P2 reçu d'abord
    assert registry.reservation_state("FICTIF-DUO#2", is_shipped) == "SHIPPED"
    assert registry.reservation_state("FICTIF-DUO", is_shipped) == "CONFIRMED"
    ship("FICTIF-DUO/envoi-2", sku1, 1, NOW + timedelta(days=9))  # P1 : une unité sur deux
    assert registry.reservation_state("FICTIF-DUO", is_shipped) == "CONFIRMED"
    assert registry.outstanding_debt(as_of=NOW + timedelta(days=9), shipped=is_shipped).total_chf == D("459.80")
    ship("FICTIF-DUO/envoi-3", sku1, 1, NOW + timedelta(days=10))
    assert registry.reservation_state("FICTIF-DUO", is_shipped) == "SHIPPED"
    assert registry.outstanding_debt(as_of=NOW + timedelta(days=10), shipped=is_shipped).total_chf == D("0.00")


# ====================================================================== ARG-02 : versement du prestataire en transit


def test_arg02_money_waiting_for_payout_is_a_receivable_and_never_freezes_a_healthy_shop(tmp_path: Path) -> None:
    client, svc, clock = T.boot(tmp_path)
    T.catalog(client)
    T.offer_cost(svc)
    assert T.allocation(client, 10).status_code == 201
    assert T.demand(client, 10).status_code == 201
    T.photo(client, bank="2200.00")  # apport 4 200 ; cash 3 700 ; perte 11,9 % : sain
    assert T.open_predrop(client).status_code == 201
    for i, c in enumerate("ab"):
        assert T.body(reserve(client, f"FICTIF-P{i}", c, paid_at=NOW + timedelta(minutes=i)))["reservation"]["status"] == "CONFIRMED"
    # Photo suivante : versement pas encore arrivé ; le prestataire détient 459.80 (relevé après la banque).
    clock.now = NOW + timedelta(hours=2)
    data = T.photo(client, clock.now, capital=False, bank="2200.00", psp="459.80")
    st = svc.gate.stoploss_status()[0]
    pre = data["sources"]["precommandes"]
    assert pre["predrop_derivees_chf"] == "459.80" and pre["predrop_en_attente_de_versement_chf"] == "459.80"
    assert data["cash_available_chf"] == "3700.00" and st.global_frozen is False and st.purchases_and_ads_frozen is False
    receivables = [(r.label, r.amount) for r in svc.stoploss_state.net_worth.receivables]
    assert (PREDROP_IN_TRANSIT_LABEL, D("459.80")) in receivables
    assert data["sources"]["prestataire"]["counted"] is True
    # Le client suivant est servi, la fiche reste en ligne.
    r = T.body(reserve(client, "FICTIF-P2", "c", paid_at=clock.now + timedelta(minutes=1)))
    assert r["reservation"]["status"] == "CONFIRMED"
    assert svc.sync.predrop_lookup(P1, clock.now + timedelta(minutes=2)).retired is False


def test_arg02_without_a_usable_payout_reading_no_new_predrop_promise(tmp_path: Path) -> None:
    client, svc, clock = T.boot(tmp_path)
    T.catalog(client)
    T.offer_cost(svc)
    assert T.allocation(client, 10).status_code == 201
    assert T.demand(client, 10).status_code == 201
    T.photo(client, psp=None)  # aucun relevé du prestataire
    refused = T.open_predrop(client)
    assert refused.status_code == 409 and "STOPLOSS" in T.body(refused)["erreur"]
    check = [c for c in T.body(refused)["eligibility"]["checks"] if c["code"] == "STOPLOSS"][0]
    assert "prestataire" in check["detail"]
    # Relevé du prestataire ANTÉRIEUR au relevé bancaire : jamais compté (double compte d'un versement possible).
    early = {"as_of": (NOW - timedelta(minutes=20)).isoformat(), "balance_chf": "100.00", "source": "FICTIF"}
    assert client.post("/treasury/psp-balance", headers=JR.HTRES, json=early).status_code == 200
    data = T.body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert data["sources"]["prestataire"]["counted"] is False and "avant la banque" in data["sources"]["prestataire"]["problem"]
    assert T.open_predrop(client).status_code == 409
    # Jeton commun ou autre rôle : jamais un relevé de trésorerie.
    for headers in (T.H, JR.HF, JR.HORDERS):
        assert client.post("/treasury/psp-balance", headers=headers, json=early).status_code == 403
    T.photo(client, capital=False)  # relevé du prestataire après la banque
    assert T.open_predrop(client).status_code == 201


# ===================================================================== ARG-03 : inventaire de la fiche jumelle


def test_arg03_shipped_reservations_never_hide_an_unrecorded_paid_order(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    for i, c in enumerate("abc"):
        assert T.body(reserve(client, f"FICTIF-R{i}", c, paid_at=NOW + timedelta(minutes=i)))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(days=2)
    T.photo(client, clock.now, capital=False, bank="2689.70")
    for i in range(2):
        assert client.post("/orders/shipped", headers=JR.HORDERS,
                           json=shipped(f"FICTIF-R{i}", RESA_SKU, f"FICTIF-ETIQ-R{i}")).status_code == 201
    pub = svc.sync.predrop_lookup(P1, clock.now)
    assert pub.reservations_available == 1 and pub.reservations_committed == 1  # confirmées NON expédiées
    remote = RemoteInventoryLevel(inventory_item_id="gid://shopify/InventoryItem/FICTIF", available=0, committed=2)
    assert predrop_inventory_target(pub, remote) == 0  # la dernière unité, déjà vendue, n'est jamais republiée


# =========================================================== ARG-04 : toute commande payée est enregistrée et reconnue


def test_arg04_any_paid_quantity_or_zero_amount_is_recorded_and_refunded(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path, alloc=40, interested=40)
    assert T.open_predrop(client).status_code == 201
    big = reserve(client, "FICTIF-BIG", "z", qty=11)
    assert big.status_code == 201, big.text
    data = T.body(big)
    assert data["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT" and data["refund"]["amount_ttc"] == "2528.90"
    zero = T.body(reserve(client, "FICTIF-ZERO", "y", amount="0.00"))
    assert zero["reservation"]["not_served_reason"] == "AMOUNT_MISMATCH" and zero["refund"]["amount_ttc"] == "0.00"
    clock.now = NOW + timedelta(minutes=30)
    assert debt(client) == "2528.90"  # dû au client jusqu'au remboursement exécuté (0 dû pour le bon à 100 %)
    # La propriétaire rattache elle aussi toute quantité.
    owner = {"predrop_id": PID, "order_id": "FICTIF-BIG-2", "customer_ref": T.cref("w"), "qty": 12,
             "amount_paid_ttc": "2758.80", "paid_at": NOW.isoformat(), "priority_access": False}
    assert client.post("/predrop/reservations", headers=T.HO, json=owner).status_code == 201


def test_arg04_a_reservation_line_is_recognized_at_shipment_even_if_unregistered(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    clock.now = NOW + timedelta(days=12)
    resp = client.post("/orders/shipped", headers=JR.HORDERS, json=shipped("FICTIF-ORPHELINE", RESA_SKU, "FICTIF-ETIQ-O"))
    assert resp.status_code == 201, resp.text
    assert T.body(resp)["predrop_unregistered_lines"] == [RESA_SKU]
    order = svc.orders.get("FICTIF-ORPHELINE")
    assert order.recognized_at == NOW + timedelta(days=12) and [ln.product_key for ln in order.lines] == [P1]
    sales = [e for e in svc.northstar.entries() if e.entry_id == "order:FICTIF-ORPHELINE:NET_SALES"]
    assert sales[0].at == NOW + timedelta(days=12)  # jamais daté du paiement
    opened = [i for i in svc.incidents.list() if i.kind == "PREDROP_EXPEDITION_SANS_RESERVATION"]
    assert opened and "FICTIF-ORPHELINE" in opened[0].cause and not opened[0].containment


# ============================================================================== ARG-05 : gel des achats et de la pub


def test_arg05_purchase_freeze_blocks_the_firm_allocation_and_the_predrop(tmp_path: Path) -> None:
    client, svc, clock = T.boot(tmp_path)
    T.catalog(client)
    T.offer_cost(svc)
    movement = {"movement_id": "FICTIF-APPORT-1", "at": (NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
                "amount": "1800", "ref": "virement FICTIF"}
    assert client.post("/capital/movements", headers=T.HO, json=movement).status_code in (200, 201)
    T.photo(client, capital=False, bank="50.00")  # cash 1 550 < 1 600 : gel des achats et de la pub
    st = svc.gate.stoploss_status()[0]
    assert st.purchases_and_ads_frozen is True and st.global_frozen is False
    refused = T.allocation(client, 10)
    assert refused.status_code == 409 and "gel des achats" in T.body(refused)["erreur"]
    assert T.allocation(client, 10, headers=T.OWNER).status_code == 201  # acte de la propriétaire
    assert T.demand(client, 10).status_code == 201
    elig = T.body(client.get(f"/predrop/eligibility/{P1}", headers=T.H))["eligibility"]
    stop = [c for c in elig["checks"] if c["code"] == "STOPLOSS"][0]
    assert stop["ok"] is False and "gel des achats" in stop["detail"]
    assert T.open_predrop(client).status_code == 409


# =========================================================================== ARG-06 / PDL-04 : frais de livraison


def test_arg06_shipping_paid_is_refunded_with_the_reservation_and_counted_as_debt(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    ok = T.body(reserve(client, "FICTIF-S1", "a", shipping="9.00"))
    assert ok["reservation"]["status"] == "CONFIRMED" and ok["reservation"]["shipping_paid_ttc"] == "9.00"
    late = T.body(reserve(client, "FICTIF-S2", "a", shipping="9.00", paid_at=NOW + timedelta(minutes=1)))
    refund = late["refund"]
    assert late["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT"
    assert refund["amount_ttc"] == "238.90" and refund["shipping_ttc"] == "9.00"
    assert "238.90 CHF, supplément et frais de livraison compris" in refund["email_draft"]
    clock.now = NOW + timedelta(minutes=30)
    assert debt(client) == "477.80"  # 2 × (229.90 + 9.00)
    # Annulation par le client : remboursement intégral, frais de livraison compris.
    cancel = T.body(client.post("/predrop/reservations/FICTIF-S1/cancel", headers=JR.HOPS,
                                json={"reason": "CUSTOMER_CANCELLATION", "request_ref": "FICTIF-TICKET-S1"}))
    assert cancel["refund"]["amount_ttc"] == "238.90" and cancel["refund"]["shipping_ttc"] == "9.00"
    assert "frais de livraison" not in refund_email_draft(order_id="X", amount=D("229.90"), reason="CLOSED",
                                                          public_sku=None)  # sans frais payés : texte inchangé


# ======================================================================= ARG-07 : validation et configuration signée


def test_arg07_owner_approval_takes_a_full_snapshot_of_the_signed_config_in_force(tmp_path: Path) -> None:
    client, svc, _ = T.ready(tmp_path, premium_pct="0.05", per_customer_limit=2, predrop_share_of_allocation="0.5")
    pending = T.open_predrop(client, headers=JR.HF, market=None)
    assert T.body(pending)["predrop"]["status"] == "PENDING_OWNER"
    client2, svc2, _ = T.boot(tmp_path, clock=F.Clock(NOW + timedelta(minutes=10)), premium_pct="0.10",
                              per_customer_limit=1, predrop_share_of_allocation="0.3")  # fmt: skip
    v2 = svc2.predrop_config.fingerprint
    T.photo(client2, NOW + timedelta(minutes=10), capital=False)
    T.offer_cost(svc2)
    ok = client2.post(f"/predrop/{PID}/approve", headers=T.OWNER, json={"market_ref_chf": "300", "reason": "validation FICTIVE v2"})
    assert ok.status_code == 200, ok.text
    p = svc2.predrop.get(PID)
    assert p.status == "OPEN" and p.config_fingerprint == v2
    assert p.premium_pct == p.prices.premium_pct_config == D("0.10")
    assert p.per_customer_limit == 1 and p.predrop_share == D("0.3") and p.free_cancellation_days == 7
    two = T.body(reserve(client2, "FICTIF-V2-1", "a", qty=2, amount=str(p.prices.predrop_price * 2),
                         paid_at=NOW + timedelta(minutes=11)))  # fmt: skip
    assert two["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT"  # limite signée en vigueur : 1
    events = svc2.audit.events(action="predrop.approve")
    assert events and events[-1].payload["config_changed"] is True


# ====================================================== PDL-01 : réception avant le drop, unités réservées hors vente


def test_pdl01_stock_received_before_the_drop_is_held_and_reserved_units_never_sold(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    for i, c in enumerate("ab"):
        reserve(client, f"FICTIF-H{i}", c, paid_at=NOW + timedelta(minutes=i))
    clock.now = datetime(2026, 10, 15, 9, 0, tzinfo=TZ)  # réception R avant le drop J (20.10)
    T.photo(client, clock.now, capital=False, bank="2459.80")
    received = client.post("/stock/receive", headers=JR.HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 10, "ref": "FICTIF-BL-1"})
    assert received.status_code == 200, received.text
    data = T.body(received)
    assert data["sellable"] == 10 and data["sellable_at_drop_price"] == 0
    assert data["predrop"]["hold_until_drop"] is True and data["predrop"]["reserved_unshipped_units"] == 2
    lookup = svc.sync.predrop_lookup(P1, clock.now)
    assert lookup.hold_until_drop and predrop_sellable(10, lookup) == 0
    # Une réservation part dès réception (ligne -RESA-) ; au jour du drop : stock − réservations non expédiées.
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=shipped("FICTIF-H0", RESA_SKU, "FICTIF-ETIQ-H0")).status_code == 201
    clock.now = datetime(2026, 10, 20, 8, 0, tzinfo=TZ)
    at_drop = svc.sync.predrop_lookup(P1, clock.now)
    assert not at_drop.hold_until_drop and at_drop.held_units == 1 and predrop_sellable(9, at_drop) == 8
    assert at_drop.retired is True  # fiche de réservation retirée au drop


# ========================================================== PDL-02 : prix « Au drop » réellement pratiqué


def test_pdl02_normal_listing_price_is_pinned_and_a_mismatch_retires_the_reservation_listing(tmp_path: Path) -> None:
    # Fiche normale : prix figé au prix du drop du pré-drop jusqu'au jour du drop inclus (prix moteur ignoré).
    pre = PB.predrop(drop_price=D("149.90"), predrop_price=D("159.90"), pin_drop_price=True)
    plan = TP.plan(TP.existing(), predrop=pre)
    assert plan.outcome is PlanOutcome.SEND_ACTIVE and plan.price_chf == D("149.90")
    assert plan.product_input["variants"][0]["price"] == "149.90"
    assert PB.mf(plan.product_input)["prix_drop"] == "149.90"
    unpinned = TP.plan(TP.existing(), predrop=PB.predrop(drop_price=D("149.90"), predrop_price=D("159.90")))
    assert unpinned.price_chf != D("149.90")  # après le drop : prix du moteur
    # Prix du drop figé sous plancher au coût actuel : prix inchangé, revue humaine.
    low = TP.plan(TP.existing(), predrop=PB.predrop(drop_price=D("20.00"), predrop_price=D("21.90"), pin_drop_price=True))
    assert PublishBlocker.PREDROP_DROP_PRICE_BELOW_FLOOR.value in low.reviews
    # Fiche jumelle : fiche normale connue à un autre prix => blocage dur ; boutique réelle sans fiche normale => idem.
    live = PublishedState(shopify_product_id="gid://shopify/Product/5", status=ShopStatus.ACTIVE, price_chf=D("149.90"))
    bad = PB.resa_plan(normal_published=live)
    assert PublishBlocker.PREDROP_NORMAL_PRICE_MISMATCH.value in bad.blockers and bad.outcome is PlanOutcome.NOT_SENT
    good = PB.resa_plan(normal_published=live.model_copy(update={"price_chf": PB.DROP_PRICE}))
    assert good.outcome is PlanOutcome.SEND_ACTIVE
    # API : fiche normale écrite à un autre prix que le prix du drop figé => fiche de réservation retirée.
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    assert svc.sync.predrop_lookup(P1, NOW + timedelta(minutes=1)).retired is False
    svc.publications.record(ShopPublication(product_id=P1, shopify_product_id="gid://shopify/Product/6", status="ACTIVE",
                                            handle="display-fictif", run_id="SYNC-FICTIF", recorded_at=NOW,
                                            price_chf=D("199.90")))  # fmt: skip
    view = svc.sync.predrop_lookup(P1, NOW + timedelta(minutes=1))
    assert view.retired is True and "prix du drop figé" in view.retired_reason
    late = T.body(reserve(client, "FICTIF-PX", "a", paid_at=NOW + timedelta(minutes=2)))
    assert late["reservation"]["status"] == "CONFIRMED"  # fiche pas encore retirée sur la boutique : servi


# ================================================================ PDL-03 : suspension après le paiement


def test_pdl03_a_block_after_payment_never_cancels_and_only_later_payments_are_refunded(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    # Gel survenu après le paiement (réservation relevée plus tard par le workflow 02) : servie.
    assert client.post("/stoploss/freeze", headers=JR.HQA, json={"actor": "agent-12", "reason": "gel FICTIF"}).status_code == 200
    clock.now = NOW + timedelta(minutes=40)
    first = T.body(reserve(client, "FICTIF-G1", "a", paid_at=NOW + timedelta(minutes=5)))
    assert first["reservation"]["status"] == "CONFIRMED" and first["refund"] is None
    # Retrait vérifié de la fiche à 12:45 ; paiement postérieur : non servi, remboursé (motif BLOCKED).
    svc.publications.record(ShopPublication(
        product_id=reservation_publication_key(P1), shopify_product_id="gid://shopify/Product/92", status="DRAFT",
        handle="x-reservation-garantie", run_id="PREDROP-FICTIF", recorded_at=NOW + timedelta(minutes=45),
        price_chf=D("229.90")))  # fmt: skip
    clock.now = NOW + timedelta(minutes=50)
    after = T.body(reserve(client, "FICTIF-G2", "b", paid_at=NOW + timedelta(minutes=46)))
    assert after["reservation"]["not_served_reason"] == "BLOCKED" and after["refund"]["amount_ttc"] == "229.90"
    before = T.body(reserve(client, "FICTIF-G3", "c", paid_at=NOW + timedelta(minutes=44)))
    assert before["reservation"]["status"] == "CONFIRMED"


# ================================================================ PDL-05 : la réserve passe après les réservations


def test_pdl05_a_reduction_never_keeps_a_reserve_unit_while_a_paid_reservation_is_refunded(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path, alloc=5, interested=5)  # réserve 1, vendable 4, pré-drop 2
    assert T.open_predrop(client).status_code == 201
    for i, c in enumerate("ab"):
        assert T.body(reserve(client, f"FICTIF-O{i}", c, paid_at=NOW + timedelta(minutes=i)))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(minutes=10)
    cut = T.body(client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                             json={"new_qty": 2, "supplier_confirmation_ref": "FICTIF-REDUC-5", "reason": "arrivage réduit FICTIF"}))
    assert cut["plan"]["kept"] == ["FICTIF-O0", "FICTIF-O1"] and cut["plan"]["refunded"] == [] and cut["refunds"] == []
    assert cut["plan"]["drop_quota_after"] == 0


# ======================================================================= PDL-06 : report de la date du drop


def test_pdl06_postponement_moves_the_date_keeps_the_sku_and_the_cancellation_rights(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    assert T.body(reserve(client, "FICTIF-R1", "a"))["reservation"]["status"] == "CONFIRMED"
    ask = {"new_drop_date": "2026-11-03", "reason": "retard de livraison FICTIF confirmé", "supplier_ref": "FICTIF-AVIS-1"}
    for headers in (T.H, JR.HF, JR.HORDERS, JR.headers("chef-de-projet")):
        assert client.post(f"/predrop/{PID}/postpone", headers=headers, json=ask).status_code == 403
    assert client.post(f"/predrop/{PID}/postpone", headers=JR.HOPS, json={**ask, "new_drop_date": "2026-10-18"}).status_code == 409
    moved = client.post(f"/predrop/{PID}/postpone", headers=JR.HOPS, json=ask)
    assert moved.status_code == 200, moved.text
    view = T.body(moved)["predrop"]
    assert view["drop_date"] == "2026-11-03" and view["reservation_sku"] == RESA_SKU  # SKU stable
    assert view["free_cancellation_until"] == "2026-10-27"
    assert view["postponements"][0]["previous_date"] == "2026-10-20"
    p = svc.predrop.get(PID)
    assert p.closes_at == datetime(2026, 11, 3, tzinfo=TZ) and p.reservation_sku == RESA_SKU
    # Ancienne date passée : la fiche n'est plus retirée, l'annulation libre reste ouverte (date en vigueur).
    clock.now = datetime(2026, 10, 21, 10, 0, tzinfo=TZ)
    T.photo(client, clock.now, capital=False, bank="2229.90")
    lookup = svc.sync.predrop_lookup(P1, clock.now)
    assert lookup.drop_date == date(2026, 11, 3) and lookup.retired is False and lookup.hold_until_drop is True
    cancel = client.post("/predrop/reservations/FICTIF-R1/cancel", headers=JR.HOPS,
                         json={"reason": "CUSTOMER_CANCELLATION", "request_ref": "FICTIF-TICKET-R1"})
    assert cancel.status_code == 201
    # Une ligne vendue avec le SKU d'origine reste rattachée au pré-drop après le report.
    assert svc.predrop.product_for_reservation_sku(RESA_SKU) == P1
    # Persisté.
    _, svc2, _ = T.boot(tmp_path, clock=F.Clock(clock.now))
    assert svc2.predrop.get(PID).drop_date == date(2026, 11, 3) and len(svc2.predrop.get(PID).postponements) == 1


# ======================================================================== PDL-07 : date du drop vérifiée


def test_pdl07_a_drop_date_before_the_expected_delivery_waits_for_the_owner(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)  # livraison attendue de l'allocation : 15.10
    early = client.post("/predrop/open", headers=JR.HF, json={"product_key": P1, "drop_date": "2026-10-12"})
    assert early.status_code == 201 and T.body(early)["predrop"]["status"] == "PENDING_OWNER"
    assert "DROP_DATE_BEFORE_DELIVERY" in T.body(early)["predrop"]["needs_owner"]
    # Allocation sans livraison attendue : la date n'est jamais tenue pour vérifiée.
    client2, svc2, _ = T.boot(tmp_path / "b")
    T.catalog(client2)
    T.offer_cost(svc2)
    payload = {"product_key": P1, "supplier_id": T.SUPPLIER, "qty": 10, "supplier_confirmation_ref": "FICTIF-CONF-1",
               "source": "confirmation fournisseur FICTIVE validée (workflow 03)"}
    assert client2.post("/predrop/allocations", headers=JR.headers("n8n-03-factures"), json=payload).status_code == 201
    assert T.demand(client2, 10).status_code == 201
    T.photo(client2)
    unknown = T.body(client2.post("/predrop/open", headers=JR.HF, json={"product_key": P1, "drop_date": "2026-10-20"}))
    assert unknown["predrop"]["status"] == "PENDING_OWNER" and "DROP_DATE_UNVERIFIED" in unknown["predrop"]["needs_owner"]


# ======================================================================== PDL-10 : délai d'annulation signé


def test_pdl10_free_cancellation_closes_n_days_before_the_drop(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path)  # paramètre signé : 7 jours
    assert T.open_predrop(client).status_code == 201
    for i, c in enumerate("ab"):
        reserve(client, f"FICTIF-C{i}", c, paid_at=NOW + timedelta(minutes=i))
    ask = {"reason": "CUSTOMER_CANCELLATION", "request_ref": "FICTIF-TICKET-C"}
    clock.now = datetime(2026, 10, 13, 23, 0, tzinfo=TZ)  # J−7 : encore annulable
    assert client.post("/predrop/reservations/FICTIF-C0/cancel", headers=JR.HOPS, json=ask).status_code == 201
    clock.now = datetime(2026, 10, 14, 8, 0, tzinfo=TZ)  # J−6 : close
    closed = client.post("/predrop/reservations/FICTIF-C1/cancel", headers=JR.HOPS, json=ask)
    assert closed.status_code == 409 and "2026-10-13" in T.body(closed)["erreur"]


def test_review_scenarios_never_publish_internal_fields(tmp_path: Path) -> None:
    """Les nouveaux champs internes (motif de retrait, unités retenues) ne sortent jamais dans l'offre publique."""
    client, svc, _ = T.ready(tmp_path)
    assert T.open_predrop(client).status_code == 201
    data = T.body(client.get("/predrop/offers", headers=T.H))
    offer = json.dumps(data["offers"], ensure_ascii=False)
    for internal in ("retired_reason", "held_units", "unshipped", "free_cancellation", "postpone"):
        assert internal not in offer, internal


# ================================================== PDL-03 : la fermeture retire aussitôt la fiche de réservation


def test_pdl03_closing_retires_the_live_reservation_listing_immediately(tmp_path: Path) -> None:
    client, svc, clock = T.ready(tmp_path, priority_window_hours=24)
    assert T.open_predrop(client).status_code == 201
    PB.content_validated(client)
    # Rien en ligne : la fermeture ne tente aucun retrait.
    clean, _svc, _ = T.ready(tmp_path / "vide", priority_window_hours=24)
    assert T.open_predrop(clean).status_code == 201
    quiet = T.body(clean.post(f"/predrop/{PID}/close", headers=JR.HQA, json={"reason": "fermeture FICTIVE sans fiche"}))
    assert quiet["changed"] is True and quiet["retirement"] is None
    # Fiche de réservation en ligne : retrait immédiat (simulation par défaut), sans attendre le cycle de publication.
    svc.publications.record(ShopPublication(
        product_id=reservation_publication_key(P1), shopify_product_id="gid://shopify/Product/93", status="ACTIVE",
        handle="display-fictif-reservation-garantie", run_id="PREDROP-FICTIF", recorded_at=NOW,
        price_chf=D("229.90")))  # fmt: skip
    closed = T.body(client.post(f"/predrop/{PID}/close", headers=JR.HQA, json={"reason": "fermeture FICTIVE en ligne"}))
    assert closed["changed"] is True and closed["predrop"]["status"] == "CLOSED"
    retirement = closed["retirement"]
    assert retirement is not None and retirement["outcome"] == PlanOutcome.UNPUBLISH.value
    assert retirement["written"] is False  # moteur en simulation : rien n'est écrit chez Shopify
    # Deuxième fermeture : sans effet, aucun nouveau retrait.
    again = T.body(client.post(f"/predrop/{PID}/close", headers=JR.HQA, json={"reason": "deuxième fermeture"}))
    assert again["changed"] is False and again["retirement"] is None
