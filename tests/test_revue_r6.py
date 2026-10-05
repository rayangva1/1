"""Régressions de la revue adverse, 6ᵉ passe (moteur) : un test par point, échouant avant correctif.

* R5-NEW-01 : la contribution d'une commande attribuée à une campagne est **dérivée des registres du moteur**
  (ventes nettes − avoirs − frais − logistique réelle − coût des ventes du registre de coûts), jamais la valeur de
  conversion transmise par le connecteur ; coût des ventes inconnu : 0 (fermé), re-dérivé à chaque photo.
* R5-NEW-02 : une commande payée avec un ancien SKU après une correction du catalogue n'est jamais perdue (alias de
  SKU historiques relus du journal du catalogue, résolution vers la clé canonique) ; SKU inconnu ou ambigu : ligne
  non rattachée (coût des ventes en attente, incomplet), rattachée par la propriétaire.
Données, jetons et montants FICTIFS ; bases PostgreSQL : aucune (journaux en fichiers par test, tmp_path).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import jetons_roles as JR
import test_orchestration_f4 as F
import test_revue_r3 as R3
import test_revue_r5 as R5
from pokeshop.northstar import UNRESOLVED_KEY_PREFIX, CostMovement, CostRegister
from pokeshop.stoploss import AttributedOrder
from pokeshop.stoploss_snapshot import derive_attributed

NOW = F.NOW
H = F.H
OWNER = R5.OWNER
SKU = R5.SKU
NEW_SKU = "DSP-FICTIF_ALPHA-FR-V2"
CAMPAIGN = "FICTIF-CAMP-1"


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def catalog(client: Any, listing: dict[str, Any] | None = None, pid: str = "FICTIF-P1") -> Any:
    item = {"product_id": pid, "listing": listing or F.LISTING,
            "supplier_links": [{"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-SKU-1"}]}  # fmt: skip
    return client.post("/catalog/items", headers=JR.HCAT, json={"items": [item]})


def shop(tmp_path: Path, *, valued: bool = True) -> tuple[Any, Any]:
    """Boutique FICTIVE : cash, fiche P1, frais de la propriétaire, cycle 01, 6 displays reçus (au coût 91.06)."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="1000", bank="3000")
    assert catalog(client).status_code == 200
    R5.owner_fees_and_cycle(client)
    R5.receive(client)
    if valued:
        assert client.post("/costs/movements", headers=JR.HF, json=R5.receipt("91.06")).status_code == 200
    return client, svc


def attribute(client: Any, order_id: str, declared: str, spend: str = "100.00") -> Any:
    paid = (NOW - timedelta(hours=1)).astimezone(F.TZ)
    ads = {"ad_spends": [{"campaign_id": CAMPAIGN, "day": paid.date().isoformat(), "amount": spend}],
           "attributed_orders": [{"order_id": order_id, "campaign_id": CAMPAIGN, "paid_at": paid.isoformat(),
                                  "status": "PAID", "contribution_before_acquisition": declared}]}  # fmt: skip
    resp = client.post("/ads/activity", headers=JR.HADS, json=ads)
    assert resp.status_code == 200, resp.text
    return resp


def photo(client: Any) -> dict[str, Any]:
    resp = client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    assert resp.status_code == 200, resp.text
    return body(resp)


def kept(svc: Any) -> list[D]:
    return [o.contribution_before_acquisition for o in svc.stoploss_state.attributed_orders]


# ================================================================= R5-NEW-01 : contribution attribuée dérivée


def test_r5new01_declared_conversion_value_never_hides_the_campaign_cut(tmp_path: Path) -> None:
    """PoC v4b : 130.90 déclarés (ventes − frais − port, sans coût produit) masquaient la coupure de FICTIF-CAMP-1."""
    for declared in ("130.90", "39.84", "500.00"):
        client, svc = shop(tmp_path / declared)
        assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
        attribute(client, "2001", declared)
        # Contribution réelle : 142.50 − 4.20 − 7.40 − 91.06 (coût des ventes dérivé par le moteur) = 39.84.
        assert [o.contribution_before_acquisition for o in svc.ads.window(NOW.date() - timedelta(days=30))[1]] == [D("39.84")]
        status = photo(client)["status"]
        assert status["cut_campaigns"] == [CAMPAIGN], declared  # CAC 100 > 39.84
        assert kept(svc) == [D("39.84")]
    # Parcours légitime : une valeur déclarée plus prudente reste retenue ; dépense sous la contribution : pas de coupure.
    client, svc = shop(tmp_path / "prudent")
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
    attribute(client, "2001", "20.00", spend="15.00")
    assert photo(client)["status"]["cut_campaigns"] == [] and kept(svc) == [D("20.00")]


def test_r5new01_unknown_cost_of_sales_counts_zero_then_is_re_derived(tmp_path: Path) -> None:
    """Coût des ventes en attente : contribution 0 (fermé) ; le coût inscrit, la photo suivante re-dérive (jamais figé)."""
    client, svc = shop(tmp_path, valued=False)
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001"))
    assert created.status_code == 201 and body(created)["cost_of_sales_pending"] == {"FICTIF-P1": 1}
    attribute(client, "2001", "130.90", spend="30.00")
    first = photo(client)
    assert first["sources"]["attributed_orders_cost_of_sales_unknown"] == ["2001"] and kept(svc) == [D("0")]
    assert first["status"]["cut_campaigns"] == [CAMPAIGN] and first["sources"]["complete"] is False
    assert client.post("/costs/movements", headers=JR.HF, json=R5.receipt("91.06")).status_code == 200
    second = photo(client)
    assert second["sources"]["attributed_orders_cost_of_sales_unknown"] == [] and kept(svc) == [D("39.84")]
    assert second["status"]["cut_campaigns"] == []  # 30 < 39.84 : la campagne n'est plus coupée à tort


def test_r5new01_refund_after_attribution_is_never_a_paid_order(tmp_path: Path) -> None:
    client, svc = shop(tmp_path)
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
    attribute(client, "2001", "39.84", spend="25.00")  # ≥ 20 CHF (seuil pour juger une campagne sans commande)
    assert photo(client)["status"]["cut_campaigns"] == []
    full = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50"}
    assert client.post("/orders/2001/refunds", headers=JR.HORDERS, json=full).status_code == 201
    assert photo(client)["status"]["cut_campaigns"] == [CAMPAIGN]  # plus aucune commande payée nette
    assert [o.status for o in svc.stoploss_state.attributed_orders] == ["REFUNDED"]


def test_r5new01_without_the_order_register_an_attributed_order_counts_zero() -> None:
    paid = AttributedOrder(order_id="2001", campaign_id=CAMPAIGN, paid_at=NOW, contribution_before_acquisition=D("130.90"))
    orders, unknown = derive_attributed([paid], None, None)
    assert [o.contribution_before_acquisition for o in orders] == [D("0")] and unknown == ("2001",)


def test_r5new01_order_cost_of_sales_follows_the_return_movement_not_its_free_reference() -> None:
    """Deux retours de même ``ref`` sur deux commandes : chacun reste rattaché à sa vente (sale_ref)."""
    costs = CostRegister()
    at = NOW - timedelta(days=1)
    for m in (
        CostMovement(kind="RECEIPT", product_key="FICTIF-P1", at=at, ref="LOT-1", qty=10, unit_cost=D("10")),
        CostMovement(kind="ISSUE", product_key="FICTIF-P1", at=at, ref="order:A", qty=2),
        CostMovement(kind="ISSUE", product_key="FICTIF-P1", at=at, ref="order:B", qty=2),
        CostMovement(kind="RETURN", product_key="FICTIF-P1", at=NOW, ref="RET", qty=1, sale_ref="order:A"),
        CostMovement(kind="RETURN", product_key="FICTIF-P1", at=NOW, ref="RET", qty=1, sale_ref="order:B"),
    ):
        costs.apply(m)
    assert costs.order_cogs("order:A") == D("10.00") and costs.order_cogs("order:B") == D("10.00")
    assert costs.order_cogs("order:C") == D("0")


# ================================================================= R5-NEW-02 : ancien SKU après correction


def test_r5new02_paid_order_with_the_sku_before_a_catalogue_fix_is_recorded_on_its_key(tmp_path: Path) -> None:
    """PoC v7 : SKU corrigé par le catalogue, commande payée avant avec l'ancien SKU => 409 pour tous, vente perdue."""
    client, svc = shop(tmp_path)
    assert catalog(client, {**F.LISTING, "public_sku": NEW_SKU}).status_code == 200
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("5001"))
    assert created.status_code == 201 and body(created)["incomplete"] is False and body(created)["unresolved_lines"] == {}
    assert svc.orders.get("5001").lines[0].product_key == "FICTIF-P1"
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5  # sortie au CMP dérivée : l'unité vendue quitte le stock
    northstar = body(client.get("/northstar", headers=H))
    assert northstar["cumulative"] == "39.84" and northstar["incomplete"] is False
    assert client.post("/orders/shipped", headers=OWNER, json=R5.order("5001")).status_code == 200  # même commande
    # Le nouveau SKU désigne la même clé ; l'historique survit au redémarrage (journal du catalogue).
    client2, svc2, _ = F.boot(tmp_path)
    assert svc2.catalog.sku_holders(SKU) == ("FICTIF-P1",)
    later = {**R5.order("5002"), "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client2.post("/orders/shipped", headers=JR.HORDERS, json=later).status_code == 201
    renamed = {**R5.order("5003"), "lines": [{"public_sku": NEW_SKU, "qty": 1}]}
    assert client2.post("/orders/shipped", headers=JR.HORDERS, json=renamed).status_code == 201
    assert svc2.costs.ledger("FICTIF-P1").qty_on_hand == 3 and svc2.orders.pending_cogs() == {}
    # Attribution pub : la commande n'est plus mise de côté.
    assert body(attribute(client2, "5001", "39.84"))["attributed_orders_set_aside"] == {}


def test_r5new02_unknown_sku_is_recorded_unresolved_and_attached_by_the_owner(tmp_path: Path) -> None:
    client, svc = shop(tmp_path)
    paid = {**R5.order("5001"), "lines": [{"public_sku": "ETB-INCONNU-FR", "qty": 1}]}
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=paid)
    assert created.status_code == 201 and body(created)["incomplete"] is True
    assert body(created)["unresolved_lines"] == {"ETB-INCONNU-FR": []}
    assert body(created)["cost_of_sales_pending"] == {f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR": 1}
    northstar = body(client.get("/northstar", headers=H))
    assert northstar["incomplete"] is True and "lines/resolve" in northstar["derivation_errors"]["commande 5001"]
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 6  # aucune sortie devinée
    attribute(client, "5001", "39.84", spend="10.00")
    snap = photo(client)
    assert snap["sources"]["complete"] is False and snap["sources"]["attributed_orders_cost_of_sales_unknown"] == ["5001"]
    # Rattachement : propriétaire seule, fiche canonique connue.
    resolve = {"public_sku": "ETB-INCONNU-FR", "product_key": "FICTIF-P1"}
    for headers in (JR.HORDERS, JR.HF, JR.HCAT, H):
        assert client.post("/orders/5001/lines/resolve", headers=headers, json=resolve).status_code == 403
    unknown_key = client.post("/orders/5001/lines/resolve", headers=OWNER, json={**resolve, "product_key": "FICTIF-P9"})
    assert unknown_key.status_code == 409
    reserved = {**resolve, "product_key": f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR"}
    assert client.post("/orders/5001/lines/resolve", headers=OWNER, json=reserved).status_code == 409
    done = client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve)
    assert done.status_code == 200 and body(done)["created"] is True and body(done)["incomplete"] is False
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5 and body(client.get("/northstar", headers=H))["incomplete"] is False
    again = client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve)
    assert again.status_code == 200 and body(again)["created"] is False
    # Webhook rejoué par n8n-02 après le rattachement : même commande (idempotente), rien de neuf.
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=paid).status_code == 200
    assert photo(client)["sources"]["attributed_orders_cost_of_sales_unknown"] == [] and kept(svc) == [D("39.84")]
    # Redémarrage : rattachement relu du journal des commandes, aucune sortie en double.
    _, svc2, _ = F.boot(tmp_path)
    assert svc2.orders.get("5001").lines[0].product_key == "FICTIF-P1"
    assert svc2.orders.pending_cogs() == {} and svc2.costs.ledger("FICTIF-P1").qty_on_hand == 5


def test_r5new02_sku_carried_by_two_keys_is_ambiguous_never_guessed(tmp_path: Path) -> None:
    """SKU de P1 corrigé puis repris par P2 : une commande à ce SKU n'est attribuée à aucune des deux d'office."""
    client, svc = shop(tmp_path)
    assert catalog(client, {**F.LISTING, "public_sku": NEW_SKU}).status_code == 200
    p2 = {**F.LISTING, "product_key": "FICTIF-P2",
          "identity": {**F.IDENTITY, "gtin": "2000000001029", "content": "18 BOOSTERS"}}  # fmt: skip
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P2", "listing": p2}]}).status_code == 200
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("5001"))
    assert created.status_code == 201 and body(created)["unresolved_lines"] == {SKU: ["FICTIF-P1", "FICTIF-P2"]}
    assert body(created)["incomplete"] is True and svc.costs.ledger("FICTIF-P1").qty_on_hand == 6
    # Avoir avec retour sur la ligne non rattachée : rattaché à la ligne de la commande, puis à la clé choisie.
    refund = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50", "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client.post("/orders/5001/refunds", headers=JR.HOPS, json=refund).status_code == 201
    resolve = {"public_sku": SKU, "product_key": "FICTIF-P1"}
    assert client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve).status_code == 200
    assert svc.orders.refund("FICTIF-AV-1").lines[0].product_key == "FICTIF-P1"
    other = client.post("/orders/5001/lines/resolve", headers=OWNER, json={**resolve, "product_key": "FICTIF-P2"})
    assert other.status_code == 409 and "déjà rattachée" in body(other)["erreur"]
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5 and svc.orders.pending_cogs() == {}


def test_r5new02_catalogue_never_takes_the_reserved_key_of_unresolved_lines(tmp_path: Path) -> None:
    client, _, _ = F.boot(tmp_path)
    key = f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR"
    resp = client.post("/catalog/items", headers=JR.HCAT,
                       json={"items": [{"product_id": key, "listing": {**F.LISTING, "product_key": key}}]})  # fmt: skip
    assert resp.status_code in (409, 422) and "réservée" in body(resp)["erreur"]
