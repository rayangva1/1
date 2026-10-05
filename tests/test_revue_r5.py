"""Régressions de la revue adverse, 5ᵉ passe : un test par point (code et génération n8n), échouant avant correctif.

* R2-NEW-01 / R3-DOC-02 / R4-DOC-09 : la référence du coût de réception n'est jamais nourrie par son bénéficiaire —
  frais du registre posés par ``finance-pricing`` exclus, cycle avec catalogue ou frais du corps sans effet sur le
  coût de remplacement, facture enregistrée prioritaire avec quantités rapprochées, réception valorisée une fois
  sur (SKU à la réception, bon).
* R3-NEW-05 : un retour en stock au coût exige les lignes de l'avoir et le retour physique déclaré.
* R4-NEW-01 : une commande payée n'est jamais perdue (coût des ventes en attente, dépenses en validation humaine) ;
  un lot publicitaire n'est jamais refusé pour une commande attribuée inconnue.
* R4-NEW-02, R4-DOC-01, R3-NEW-02 (partiel) : créances de la propriétaire et dettes des rôles séparées et
  persistées ; le plancher des dettes survit au redémarrage.
* R4-NEW-03 : tests de sauvegarde isolés (préfixe propre, aucune opération globale).
* R4-DOC-02, R4-DOC-08 : nœud n8n 03 — TVA d'import ventilée à part (profil TVA du moteur), date d'émission jamais
  future. R4-DOC-03 : ``POST /mandate/human-decision`` (jeton propriétaire). R4-DOC-07 : credential PayPal de lecture
  distinct. R4-DOC-10 : âge accepté explicite de la déclaration des dettes. R3-DOC-04 : incident « simulation »
  déclaré. R4-DOC-11 : ``finance-pricing`` ne demande jamais de dépense.
Données, jetons et montants FICTIFS ; bases PostgreSQL : aucune (journaux en fichiers par test, tmp_path).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import jetons_roles as JR
import pytest
import test_n8n_workflows as N
import test_orchestration_f4 as F
import test_revue_r3 as R3
from pokeshop import authz
from pokeshop.api import OWNER_TOKEN_HEADER
from pokeshop.catalogue_sync import SyncRunSummary
from pokeshop.mandate import SpendStatus
from pokeshop.stoploss_snapshot import committed_ad_payments

GEN = N.GEN
ROOT = Path(__file__).resolve().parents[1]
NOW = F.NOW
H, HO = F.H, F.HO
OWNER = {OWNER_TOKEN_HEADER: F.OWNER_TOKEN}
H03 = JR.headers("n8n-03-factures")
SKU = "DSP-FICTIF_ALPHA-FR"
OWNER_FEES = {"supplier_id": "fictif_grossiste_a", "currency": "EUR", "inbound_freight_alloc": "2.00",
              "customs_and_fees": "0", "import_vat": "0", "source": "devis transporteur FICTIF (propriétaire)"}


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def receipt(unit_cost: str, *, key: str = "FICTIF-P1", qty: int = 6, ref: str = "FICTIF-LOT-1",
            stock_ref: str = "FICTIF-BL-1", invoice_ref: str = "FICTIF-FACT-1") -> dict[str, Any]:  # fmt: skip
    return {"kind": "RECEIPT", "product_key": key, "at": (NOW - timedelta(days=1)).isoformat(), "ref": ref, "qty": qty,
            "unit_cost": unit_cost, "stock_ref": stock_ref, "invoice_ref": invoice_ref}  # fmt: skip


def catalog(client: Any, *, links: bool = False) -> None:
    item: dict[str, Any] = {"product_id": "FICTIF-P1", "listing": F.LISTING}
    if links:
        item["supplier_links"] = [{"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-SKU-1"}]
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [item]}).status_code == 200


def receive(client: Any, qty: int = 6, ref: str = "FICTIF-BL-1", sku: str = SKU) -> None:
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": sku, "qty": qty, "ref": ref}).status_code == 200


def owner_fees_and_cycle(client: Any) -> None:
    """Frais posés par la propriétaire, taux de la propriétaire, cycle normal du workflow 01 (simulation, registre)."""
    assert client.post("/catalog/cost-inputs", headers=OWNER, json=OWNER_FEES).status_code == 200
    rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": "2026-10-04", "source": "BNS FICTIF 11:00"}
    assert client.post("/fx/rates", headers=OWNER, json=rate).status_code == 200
    assert client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY).status_code == 200


def order(order_id: str, qty: int = 1, sales: str = "142.50") -> dict[str, Any]:
    return {"order_id": order_id, "paid_at": (NOW - timedelta(hours=1)).isoformat(), "net_sales_ht": sales,
            "payment_fees": "4.20", "shipping_cost_actual": "7.40", "shipping_label_ref": f"FICTIF-ETIQ-{order_id}",
            "source": "webhook Shopify FICTIF", "lines": [{"public_sku": SKU, "qty": qty}]}  # fmt: skip


# ============================================================ R2-NEW-01 (a) / R3-DOC-02 : frais du bénéficiaire


def test_r2new01_fees_posted_by_finance_never_feed_the_receipt_reference(tmp_path: Path) -> None:
    """PoC b1 : fret gonflé × 7 par finance-pricing, cycle n8n-01 normal, RECEIPT 6 × 637.06 levait le gel global."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="1500")  # apport 4 200, cash 2 000 : gel global
    F.register_catalog(client)  # fiche, frais posés par finance-pricing, taux de la propriétaire
    inflated = {**OWNER_FEES, "inbound_freight_alloc": "548.00", "source": "devis FICTIF gonflé"}
    assert client.post("/catalog/cost-inputs", headers=JR.HF, json=inflated).status_code == 200
    assert client.post("/sync/run", headers=JR.HSYNC, json=F.N8N_SYNC_BODY).status_code == 200
    offer = svc.sync.replacement_costs.latest("FICTIF-P1")
    assert offer is not None and offer.unit_cost == D("637.06") and offer.fees_recorded_by == "finance-pricing"
    receive(client)
    for unit in ("637.06", "91.06"):  # ni le coût gonflé ni un coût honnête : aucune référence admise
        refused = client.post("/costs/movements", headers=JR.HF, json=receipt(unit))
        assert refused.status_code == 403 and "frais posés par la propriétaire" in body(refused)["erreur"], unit
    photo = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert photo["status"]["global_frozen"] is True and D(photo["net_worth_chf"]) == D("2000")
    # Parcours légitime : frais posés par la propriétaire => offre admise comme référence.
    owner_fees_and_cycle(client)
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("637.06")).status_code == 403  # > 2 %
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("91.06")).status_code == 200
    stoploss = (ROOT / "docs/00-pilotage/STOP_LOSS.md").read_text(encoding="utf-8")
    assert "dont les frais ont été posés par vous" in stoploss and "× 6 ou × 36" not in stoploss


# ===================================================================== R4-DOC-09 : simulations avec corps


def test_r4doc09_body_costs_or_catalog_never_update_the_replacement_cost(tmp_path: Path) -> None:
    """PoC b1b / b4 : une simulation avec frais ou catalogue dans le corps écrivait la référence du moteur."""
    client, svc, _ = F.boot(tmp_path)
    catalog(client)
    owner_fees_and_cycle(client)
    before = svc.sync.replacement_costs.history("FICTIF-P1")
    assert before and before[-1].unit_cost == D("91.06") and before[-1].fees_recorded_by == "propriétaire"
    body_fees = {**F.N8N_SYNC_BODY, "cost_inputs": {"fictif_grossiste_a": {"currency": "EUR", "inbound_freight_alloc": "548.00",
                                                                             "customs_and_fees": "0", "import_vat": "0"}}}
    assert body(client.post("/sync/run", headers=JR.HSITE, json=body_fees))["cycle_status"] == "PROPRE"
    p2 = {**F.LISTING, "product_key": "FICTIF-P2", "public_sku": "DSP-FICTIF_ALPHA-SIM"}
    sim = body(client.post("/sync/run", headers=JR.HSITE, json={**F.N8N_SYNC_BODY, "catalog": [{"product_id": "FICTIF-P2",
                                                                                              "listing": p2}]}))  # fmt: skip
    assert sim["cycle_status"] == "PROPRE"
    assert svc.sync.replacement_costs.history("FICTIF-P1") == before  # rien d'inscrit par les simulations du corps
    assert svc.sync.replacement_costs.latest("FICTIF-P2") is None


# ============================================================ R2-NEW-01 (c) : quantités de la facture


def test_r2new01_registered_invoice_reconciles_quantities_total_and_supplier(tmp_path: Path) -> None:
    """PoC b7 : facture « 1 × carton de 6 » à 546.36 puis réception de 6 valorisée 6 × 546.36 (gel levé)."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="2046.36")
    catalog(client, links=True)
    carton = {"invoice_ref": "FICTIF-FACT-1", "supplier_id": "fictif_grossiste_a", "issued_at": (NOW - timedelta(days=1)).isoformat(),
              "total_chf": "546.36", "lines": [{"product_key": "FICTIF-P1", "qty": 1, "unit_cost_chf": "546.36"}],
              "source": "facture FICTIVE (formulaire 03)"}  # fmt: skip
    assert client.post("/costs/invoices", headers=H03, json=carton).status_code == 201
    receive(client)
    refused = client.post("/costs/movements", headers=JR.HF, json=receipt("546.36"))
    assert refused.status_code == 409 and "unité(s) facturée(s)" in body(refused)["erreur"]
    # Lignes au-dessus du montant dû : refus à l'enregistrement.
    inflated = {**carton, "invoice_ref": "FICTIF-FACT-2", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "546.36"}]}
    over = client.post("/costs/invoices", headers=H03, json=inflated)
    assert over.status_code == 409 and "montant dû" in body(over)["erreur"]
    # Facture d'un autre fournisseur que celui lié à la référence : refus.
    other = {**carton, "invoice_ref": "FICTIF-FACT-3", "supplier_id": "fictif_grossiste_c",
             "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "91.06"}]}
    assert client.post("/costs/invoices", headers=H03, json=other).status_code == 201
    wrong = client.post("/costs/movements", headers=JR.HF, json=receipt("91.06", invoice_ref="FICTIF-FACT-3"))
    assert wrong.status_code == 409 and "fictif_grossiste_c" in body(wrong)["erreur"]
    # Parcours légitime : facture à l'unité (6 × 91.06), une réception de 6 ; une 2ᵉ réception de 6 sur la même ligne : 409.
    unit = {**carton, "invoice_ref": "FICTIF-FACT-4", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "91.06"}]}
    assert client.post("/costs/invoices", headers=H03, json=unit).status_code == 201
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("91.06", invoice_ref="FICTIF-FACT-4")).status_code == 200
    receive(client, ref="FICTIF-BL-2")
    second = receipt("91.06", ref="FICTIF-LOT-2", stock_ref="FICTIF-BL-2", invoice_ref="FICTIF-FACT-4")
    assert client.post("/costs/movements", headers=JR.HF, json=second).status_code == 409
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 6


def test_r2new01_invoice_supplier_must_be_known_to_the_engine_even_after_a_restart(tmp_path: Path) -> None:
    """Sans lien fournisseur au catalogue, le contrôle du fournisseur de la facture était sauté (ouvert par défaut)."""
    client, _, _ = F.boot(tmp_path)
    catalog(client)  # aucun lien fournisseur, aucune offre rapprochée : fournisseur invérifiable
    receive(client)
    invoice = {"invoice_ref": "FICTIF-FACT-1", "supplier_id": "fictif_grossiste_a", "issued_at": (NOW - timedelta(days=1)).isoformat(),
               "total_chf": "546.36", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "91.06"}],
               "source": "facture FICTIVE (formulaire 03)"}  # fmt: skip
    assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 201
    unknown = client.post("/costs/movements", headers=JR.HF, json=receipt("91.06"))
    assert unknown.status_code == 409 and "aucun fournisseur connu" in body(unknown)["erreur"]
    # Cycle n8n-01 sur le catalogue du registre : l'offre de fictif_grossiste_a est rapprochée (journal persisté).
    owner_fees_and_cycle(client)
    client2, svc2, _ = F.boot(tmp_path)  # redémarrage : coûts de remplacement perdus, journal des cycles relu
    assert svc2.sync.replacement_costs.history("FICTIF-P1") == ()
    other = {**invoice, "invoice_ref": "FICTIF-FACT-C", "supplier_id": "fictif_grossiste_c"}
    assert client2.post("/costs/invoices", headers=H03, json=other).status_code == 201
    wrong = client2.post("/costs/movements", headers=JR.HF, json=receipt("91.06", invoice_ref="FICTIF-FACT-C"))
    assert wrong.status_code == 409 and "fictif_grossiste_c" in body(wrong)["erreur"]
    assert client2.post("/costs/movements", headers=JR.HF, json=receipt("91.06")).status_code == 200
    assert svc2.costs.ledger("FICTIF-P1").qty_on_hand == 6


# ============================================================ R2-NEW-01 (d) : SKU au moment de la réception


def test_r2new01_same_physical_receipt_is_never_valued_twice_after_a_sku_reshuffle(tmp_path: Path) -> None:
    """PoC b4 : SKU de P1 déplacé, P2 reprend l'ancien SKU, la même réception BL-1 valorisée une 2ᵉ fois."""
    client, svc, _ = F.boot(tmp_path)
    catalog(client)
    receive(client)
    owner_fees_and_cycle(client)
    assert client.post("/costs/movements", headers=JR.HF, json=receipt("91.06")).status_code == 200
    assert svc.costs.movements()[0].sku == SKU  # SKU inscrit par le moteur à la réception
    moved = {**F.LISTING, "public_sku": "DSP-FICTIF_ALPHA-FR2"}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": moved}]}).status_code == 200
    p2 = {**F.LISTING, "product_key": "FICTIF-P2", "identity": {**F.IDENTITY, "gtin": "2000000001029", "content": "18 BOOSTERS"}}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P2", "listing": p2}]}).status_code == 200
    F.engine_offer(svc, "91.06", product_key="FICTIF-P2")  # référence admise pour P2 : seul le SKU à la réception arrête
    again = client.post("/costs/movements", headers=JR.HF, json=receipt("91.06", key="FICTIF-P2", ref="FICTIF-LOT-2"))
    assert again.status_code == 409 and "déjà valorisée" in body(again)["erreur"]
    assert [(m.product_key, m.qty) for m in svc.costs.movements()] == [("FICTIF-P1", 6)]


# ===================================================================== R3-NEW-05 : retour physique


def test_r3new05_return_needs_refund_lines_and_a_physical_return(tmp_path: Path) -> None:
    """PoC b2 : geste commercial de 5 CHF puis RETURN 6 sans retour physique (+602 sur l'étoile polaire)."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)  # 6 displays au coût
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001", qty=6, sales="855.00")).status_code == 201
    geste = {"refund_id": "FICTIF-GESTE-1", "at": NOW.isoformat(), "net_sales_ht": "5.00"}
    assert client.post("/orders/1001/refunds", headers=JR.HORDERS, json=geste).status_code == 201
    northstar = body(client.get("/northstar", headers=H))["cumulative"]
    back = {"kind": "RETURN", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-RET-1", "qty": 6,
            "sale_ref": "order:1001", "stock_ref": "return:FICTIF-GESTE-1"}
    for attempt in (back, {k: v for k, v in back.items() if k != "stock_ref"}):
        refused = client.post("/costs/movements", headers=JR.HF, json=attempt)
        motif = body(refused)["erreur"]
        assert refused.status_code == 403 and ("réception physique" in motif or "geste commercial" in motif), motif
    assert body(client.get("/northstar", headers=H))["cumulative"] == northstar and svc.costs.ledger("FICTIF-P1").qty_on_hand == 0
    # Avoir avec plus d'unités retournées que vendues : refus.
    too_many = {"refund_id": "FICTIF-AV-9", "at": NOW.isoformat(), "net_sales_ht": "10.00", "lines": [{"public_sku": SKU, "qty": 7}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=too_many).status_code == 409
    # Parcours légitime : avoir à lignes (1 unité), retour physique déclaré par operations-sav, puis RETURN au coût.
    refund = {"refund_id": "FICTIF-AV-2", "at": NOW.isoformat(), "net_sales_ht": "142.50", "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=refund).status_code == 201
    one = {**back, "qty": 1, "ref": "FICTIF-RET-2", "stock_ref": "return:FICTIF-AV-2"}
    assert client.post("/costs/movements", headers=JR.HF, json=one).status_code == 403  # retour physique pas encore déclaré
    receive(client, qty=1, ref="return:FICTIF-AV-2")
    assert client.post("/costs/movements", headers=JR.HF, json=one).status_code == 200
    assert client.post("/costs/movements", headers=JR.HF, json={**one, "ref": "FICTIF-RET-3"}).status_code == 403  # > lignes
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 1
    assert svc.costs.movements()[-1].sku == SKU


def test_r3new05_refund_below_the_cost_of_returned_units_and_return_receipts_never_inflate_the_stock(tmp_path: Path) -> None:
    """Avoir de 5 CHF « à lignes » (6 unités) + retour physique : la paire relevait l'étoile polaire de ~600 CHF ;
    un retour physique cité par une RÉCEPTION au coût entrait deux fois (RECEIPT puis RETURN)."""
    back = {"kind": "RETURN", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-RET-5", "qty": 6,
            "sale_ref": "order:1001", "stock_ref": "return:FICTIF-AV-5"}
    links = [{"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-SKU-1"}]
    invoice = {"invoice_ref": "FICTIF-FACT-9", "supplier_id": "fictif_grossiste_a", "issued_at": (NOW - timedelta(days=1)).isoformat(),
               "total_chf": "607.41", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "101.23"}],
               "source": "facture FICTIVE (formulaire 03)"}  # fmt: skip

    def boot(sub: str) -> tuple[Any, Any]:
        client, svc, _ = F.boot(tmp_path / sub)
        F.feed_registers(client, svc)  # 6 displays au coût (101.2345)
        assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": F.LISTING,
                                                                               "supplier_links": links}]}).status_code == 200
        assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 201
        assert client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001", qty=6, sales="855.00")).status_code == 201
        return client, svc

    # 1. Geste de 5 CHF déclaré « avec 6 unités retournées » par operations-sav, retour physique déclaré : refusé.
    client, svc = boot("geste")
    geste = {"refund_id": "FICTIF-AV-5", "at": NOW.isoformat(), "net_sales_ht": "5.00", "lines": [{"public_sku": SKU, "qty": 6}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=geste).status_code == 201
    receive(client, qty=6, ref="return:FICTIF-AV-5")
    northstar = body(client.get("/northstar", headers=H))["cumulative"]
    refused = client.post("/costs/movements", headers=JR.HF, json=back)
    assert refused.status_code == 403 and "coût des unités retournées" in body(refused)["erreur"]
    # Le retour physique n'est jamais valorisé comme une réception au coût d'une facture.
    as_receipt = receipt("101.23", ref="FICTIF-LOT-R", stock_ref="return:FICTIF-AV-5", invoice_ref="FICTIF-FACT-9")
    reserved = client.post("/costs/movements", headers=JR.HF, json=as_receipt)
    assert reserved.status_code == 409 and "réservée aux retours" in body(reserved)["erreur"]
    assert body(client.get("/northstar", headers=H))["cumulative"] == northstar and svc.costs.ledger("FICTIF-P1").qty_on_hand == 0
    # La propriétaire décide (décote, unité rouverte…) : elle inscrit elle-même le retour au coût.
    assert client.post("/costs/movements", headers=HO, json={**back, "qty": 1, "ref": "FICTIF-RET-P"}).status_code == 200

    # 2. Retour contre remboursement (avoir ≥ coût) déjà entré au coût par une réception : jamais une 2ᵉ fois.
    client, svc = boot("double")
    full = {"refund_id": "FICTIF-AV-6", "at": NOW.isoformat(), "net_sales_ht": "700.00", "lines": [{"public_sku": SKU, "qty": 5}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=full).status_code == 201
    receive(client, qty=5, ref="return:FICTIF-AV-6")
    by_owner = receipt("101.23", qty=5, ref="FICTIF-LOT-P", stock_ref="return:FICTIF-AV-6", invoice_ref="FICTIF-FACT-9")
    assert client.post("/costs/movements", headers=HO, json=by_owner).status_code == 200
    five = {**back, "qty": 5, "ref": "FICTIF-RET-6", "stock_ref": "return:FICTIF-AV-6"}
    twice = client.post("/costs/movements", headers=JR.HF, json=five)
    assert twice.status_code == 403 and "physiquement reçue" in body(twice)["erreur"]
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5


def test_r3new05_return_on_an_order_whose_cost_of_sales_is_pending_waits_for_the_cost(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order("1000", qty=6, sales="855.00")).status_code == 201
    receive(client, ref="FICTIF-BL-2")  # stock reçu, coût pas encore inscrit
    assert body(client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001")))["cost_of_sales_pending"] == {"FICTIF-P1": 1}
    refund = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50", "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client.post("/orders/1001/refunds", headers=JR.HOPS, json=refund).status_code == 201
    receive(client, qty=1, ref="return:FICTIF-AV-1")
    back = {"kind": "RETURN", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-RET-1", "qty": 1,
            "sale_ref": "order:1001", "stock_ref": "return:FICTIF-AV-1"}
    waiting = client.post("/costs/movements", headers=JR.HF, json=back)
    assert waiting.status_code == 409 and "en attente" in body(waiting)["erreur"]
    F.engine_offer(svc, "101.23")
    late = receipt("101.23", ref="FICTIF-LOT-2", stock_ref="FICTIF-BL-2", invoice_ref="FICTIF-FACT-2")
    assert client.post("/costs/movements", headers=JR.HF, json=late).status_code == 200
    assert client.post("/costs/movements", headers=JR.HF, json=back).status_code == 200
    assert svc.orders.pending_cogs() == {} and svc.costs.ledger("FICTIF-P1").qty_on_hand == 6


# ===================================================================== R4-NEW-01 : commande jamais perdue


def test_r4new01_paid_order_before_cost_is_recorded_pending_and_ads_spends_are_kept(tmp_path: Path) -> None:
    """PoC b6 : commande refusée (409) faute de stock valorisé ; lot pub refusé en entier (dépense invisible)."""
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)  # 6 displays au coût
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order("1000", qty=6, sales="855.00")).status_code == 201
    receive(client, ref="FICTIF-BL-2")  # stock physique reçu, coût pas encore inscrit (facture en validation)
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=order("1001"))
    assert created.status_code == 201 and body(created)["cost_of_sales_pending"] == {"FICTIF-P1": 1}
    northstar = body(client.get("/northstar", headers=H))
    assert northstar["incomplete"] is True and "coût des ventes en attente" in northstar["derivation_errors"]["commande 1001"]
    # Lot du connecteur pub : dépenses + commande connue + commande inconnue (écartée seule).
    day = (NOW - timedelta(hours=1)).date().isoformat()
    attributed = [{"order_id": oid, "campaign_id": "FICTIF-CAMP-1", "paid_at": (NOW - timedelta(hours=1)).isoformat(),
                   "status": "PAID", "contribution_before_acquisition": "30.00"} for oid in ("1001", "9999")]  # fmt: skip
    batch = client.post("/ads/activity", headers=JR.HADS,
                        json={"ad_spends": [{"campaign_id": "FICTIF-CAMP-1", "day": day, "amount": "45.00"}], "attributed_orders": attributed})
    assert batch.status_code == 200 and list(body(batch)["attributed_orders_set_aside"]) == ["9999"]
    spends, orders = svc.ads.window(NOW.date() - timedelta(days=30))
    assert [s.amount for s in spends] == [D("45.00")] and [o.order_id for o in orders] == ["1001"]
    # Photo et dépenses : incomplètes => validation humaine (fermé par défaut).
    photo = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert photo["sources"]["complete"] is False and "commande 1001" in photo["sources"]["incomplete"]
    spend = {**F.SPEND, "request": {**F.SPEND["request"], "idempotency_key": "FICTIF-R5-1"}, "record": False}
    unverified = body(client.post("/mandate/check", headers=JR.HOPS, json=spend))["unverified"]
    assert any("incomplètes" in label for label in unverified)
    # Redémarrage : le coût en attente est recalculé (jamais perdu, jamais inventé).
    _, svc2, _ = F.boot(tmp_path)
    assert svc2.orders.pending_cogs() == {"1001": {"FICTIF-P1": 1}}
    # Coût inscrit (référence admise) => sortie au CMP dérivée, étoile polaire complète.
    F.engine_offer(svc, "101.23")
    late = receipt("101.23", ref="FICTIF-LOT-2", stock_ref="FICTIF-BL-2", invoice_ref="FICTIF-FACT-2")
    assert client.post("/costs/movements", headers=JR.HF, json=late).status_code == 200
    assert svc.orders.pending_cogs() == {} and svc.costs.ledger("FICTIF-P1").qty_on_hand == 5
    assert body(client.get("/northstar", headers=H))["incomplete"] is False


# ============================================================ R4-NEW-02 / R4-DOC-01 : créances et dettes séparées


def test_r4new02_owner_receivables_survive_the_finance_agent_statement(tmp_path: Path) -> None:
    """PoC b5 : la déclaration routinière de l'agent 05 effaçait la créance de 600 de la propriétaire."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="1000", bank="1900")  # apport 4 200, cash 2 900
    own = {"as_of": (NOW - timedelta(minutes=8)).isoformat(), "preorders_collected_chf": "0",
           "debts": [{"label": "TVA due FICTIVE", "amount": "400"}],
           "receivables": [{"label": "Versement PSP en transit FICTIF", "amount": "600"}], "source": "relevé propriétaire"}
    assert client.post("/treasury/balance-items", headers=OWNER, json=own).status_code == 200
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("3100")
    fin = {"as_of": (NOW - timedelta(minutes=5)).isoformat(), "preorders_collected_chf": "0",
           "debts": [{"label": "TVA due FICTIVE", "amount": "400"}], "source": "routine agent 05"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=fin).status_code == 200
    photo = body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))
    assert D(photo["net_worth_chf"]) == D("3100") and photo["sources"]["dettes_creances"]["receivables"] == 1
    # Une liste vide d'un rôle (ancienne forme) ne touche pas aux créances ; une créance d'un rôle : 403.
    assert client.post("/treasury/balance-items", headers=JR.HF, json={**fin, "receivables": []}).status_code == 200
    assert client.post("/treasury/balance-items", headers=JR.HF,
                       json={**fin, "receivables": [{"label": "x", "amount": "1"}]}).status_code == 403  # fmt: skip
    assert svc.balances.receivables is not None and svc.balances.receivables.receivables[0].amount == D("600")


def test_r4doc01_owner_receivables_alone_never_erase_the_agents_debts(tmp_path: Path) -> None:
    """PoC R4-DOC-01 : créances de la propriétaire avec « debts: [] » => 300 de dettes de l'agent 05 disparues."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="500", bank="1500")  # apport 4 200, cash 2 000
    debts = {"as_of": (NOW - timedelta(minutes=9)).isoformat(), "preorders_collected_chf": "0",
             "debts": [{"label": "TVA due FICTIVE", "amount": "300"}], "source": "agent 05"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=debts).status_code == 200
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("1700")
    receivables = {"as_of": (NOW - timedelta(minutes=8)).isoformat(), "source": "relevé propriétaire",
                   "receivables": [{"label": "Stock payé en transit (au coût)", "amount": "1000"}]}
    updated = client.post("/treasury/balance-items", headers=OWNER, json=receivables)
    assert updated.status_code == 200 and body(updated)["updated"] == ["créances"]
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("2700")
    assert client.post("/treasury/balance-items", headers=JR.HF, json={**debts, "as_of": (NOW - timedelta(minutes=2)).isoformat()}).status_code == 200
    assert D(body(client.post("/stoploss/state/refresh", headers=JR.HPHOTO))["net_worth_chf"]) == D("2700")
    for rel in ("docs/00-pilotage/STOP_LOSS.md", "docs/08-agents/BRIEF_COMMUN.md", "orchestration/README.md"):
        assert "registre distinct" in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_r3new02_debt_floor_survives_a_restart(tmp_path: Path) -> None:
    """PoC R3-NEW-02 : après redémarrage, la déclaration (mémoire) disparaissait et l'agent 05 abaissait les dettes."""
    client, _, _ = F.boot(tmp_path)
    high = {"as_of": (NOW - timedelta(minutes=10)).isoformat(), "preorders_collected_chf": "250",
            "debts": [{"label": "TVA due FICTIVE", "amount": "900"}], "source": "agent 05"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=high).status_code == 200
    client2, svc2, _ = F.boot(tmp_path)
    assert svc2.balance_statement is not None and svc2.balance_statement.preorders_collected_chf == D("250")
    low = {**high, "as_of": (NOW - timedelta(minutes=1)).isoformat(), "preorders_collected_chf": "0", "debts": []}
    refused = client2.post("/treasury/balance-items", headers=JR.HF, json=low)
    assert refused.status_code == 403 and "baisse" in body(refused)["erreur"]
    assert client2.post("/treasury/balance-items", headers=JR.HTRES, json=low).status_code == 200  # paiement relevé


# ===================================================================== R4-NEW-03 : sauvegardes isolées


def test_r4new03_backup_tests_only_touch_their_own_scratch_databases(tmp_path: Path) -> None:
    text = (ROOT / "tests/test_sauvegarde_restauration.py").read_text(encoding="utf-8")
    assert "LIKE 'pokeshop_verif_" not in text and "POKESHOP_VERIF_PREFIX" in text and "starts_with(datname" in text
    script = (ROOT / "db/backup.sh").read_text(encoding="utf-8")
    assert 'POKESHOP_VERIF_PREFIX:-pokeshop_verif_' in script
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "DATABASE_URL": "postgresql://fictif@127.0.0.1:1/fictif",
           "POKESHOP_VERIF_PREFIX": "pokeshop_verif_%' OR 1=1 --"}
    out = subprocess.run(["bash", str(ROOT / "db/backup.sh"), "verifier", "/inexistant.dump"], capture_output=True,
                         text=True, env=env, timeout=30, check=False)  # fmt: skip
    assert out.returncode != 0 and "POKESHOP_VERIF_PREFIX invalide" in out.stderr  # refusé avant tout accès


# ===================================================================== R4-DOC-02 : TVA d'import


def test_r4doc02_import_vat_counts_in_the_receipt_reference_by_the_engine_vat_profile(tmp_path: Path) -> None:
    """6 × 100 CHF, fret 30, douane 10, TVA d'import 51,84 : coût rendu 106,67 (effective) ou 115,31 (non assujettie)."""
    invoice = {"invoice_ref": "FICTIF-FACT-1", "supplier_id": "fictif_grossiste_a", "issued_at": (NOW - timedelta(days=1)).isoformat(),
               "total_chf": "691.84", "lines": [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "106.67",
                                                 "import_vat_unit_chf": "8.64"}],
               "source": "facture FICTIVE (formulaire 03)"}  # fmt: skip
    for profile, accepted, refused in (("EFFECTIVE", "106.67", "115.31"), ("NOT_REGISTERED", "115.31", "106.67")):
        client, _, _ = F.boot(tmp_path / profile, POKESHOP_VAT_PROFILE=profile)
        catalog(client, links=True)  # fournisseur de la facture connu du moteur (lien déclaré par `catalogue`)
        receive(client)
        assert client.post("/costs/invoices", headers=H03, json=invoice).status_code == 201
        assert client.post("/costs/movements", headers=JR.HF, json=receipt(refused)).status_code == 403, profile
        assert client.post("/costs/movements", headers=JR.HF, json=receipt(accepted)).status_code == 200, profile


@pytest.mark.skipif(N.NODE_BIN is None, reason="node absent : code non exécuté")
def test_r4doc02_r4doc08_workflow_03_separates_import_vat_and_never_dates_an_invoice_in_the_future(tmp_path: Path) -> None:
    code = GEN.JS_INVOICE_FOR_ENGINE
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()  # Zurich déjà au lendemain, UTC pas encore
    extracted = {"body": {"invoice_ref": "FICTIF-F-9", "supplier_id": "fictif_grossiste_a", "invoice_date": tomorrow,
                          "lines": [{"product_key": "FICTIF-P1", "qty": 6, "invoice_unit_cost_chf": "100.00"}],
                          "fees_chf": {"freight": "30.00", "customs": "10.00", "import_vat": "51.84"}}}  # fmt: skip
    (out,), _ = N.run_js(tmp_path, code, [{}], nodes={"Facture extraite par l’agent 05 (passerelle)": extracted})
    assert out["lines"] == [{"product_key": "FICTIF-P1", "qty": 6, "unit_cost_chf": "106.67", "import_vat_unit_chf": "8.64"}]
    assert out["total_chf"] == "691.84"
    issued = datetime.fromisoformat(out["issued_at"].replace("Z", "+00:00"))
    assert issued <= datetime.now(UTC) + timedelta(minutes=1)  # jamais « T12:00 » d'un jour à venir
    past = {"body": {**extracted["body"], "invoice_date": "2026-10-01"}}
    (old,), _ = N.run_js(tmp_path, code, [{}], nodes={"Facture extraite par l’agent 05 (passerelle)": past})
    assert old["issued_at"] == "2026-10-01T00:00:00.000Z"
    checks = GEN.JS_INVOICE_CHECKS
    carton = {"body": {**extracted["body"], "invoice_date": "2026-10-01", "goods_total_chf": "600.00",
                       "currency": "CHF", "lines": [{"lot_id": "L1", "product_key": "FICTIF-P1", "qty": 6, "unit_basis": "carton de 6",
                                                     "estimated_unit_cost_chf": "100.00", "invoice_unit_cost_chf": "100.00"}]}}
    (verdict,), _ = N.run_js(tmp_path, checks, [carton])
    assert any("carton de 6" in a for a in verdict["anomalies"]) and "6 × carton de 6" in verdict["resume"]
    assert "TVA d'import 51.84" in verdict["fees_resume"]


# ===================================================================== R4-DOC-03 : décision humaine


def test_r4doc03_owner_records_the_human_decision_and_it_feeds_the_ads_stoploss(tmp_path: Path) -> None:
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    assert client.post("/stoploss/state/refresh", headers=JR.HPHOTO).status_code == 200
    spend = {"request": {"amount": "20", "currency": "CHF", "supplier_id": "FICTIF_PUB", "category": "ADVERTISING",
                         "payment_method": "PAYPAL", "purpose": "campagne FICTIVE", "idempotency_key": "FICTIF-PUB-H1",
                         "requested_by": "acquisition", "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF",
                         "campaign_id": "FICTIF-CAMP-H"}, "record": True}  # fmt: skip
    decided = body(client.post("/mandate/check", headers=JR.HACQ, json=spend))
    assert decided["decision"]["outcome"] == "NEEDS_HUMAN_APPROVAL" and decided["recorded"] is True
    decision = {"idempotency_key": "FICTIF-PUB-H1", "decision": "APPROVE", "motif": "test FICTIF validé"}
    for role in ("n8n-08-mandat", "acquisition", "finance-pricing", "qa-conformite"):
        assert client.post("/mandate/human-decision", headers=JR.headers(role), json=decision).status_code == 403, role
    assert committed_ad_payments(svc.spend_ledger.entries(), F.TZ) == {}
    ok = client.post("/mandate/human-decision", headers=OWNER, json=decision)
    assert ok.status_code == 200 and body(ok)["status"] == "HUMAN_APPROVED"
    assert svc.spend_ledger.get("FICTIF-PUB-H1").status is SpendStatus.HUMAN_APPROVED
    assert committed_ad_payments(svc.spend_ledger.entries(), F.TZ) == {("FICTIF-CAMP-H", NOW.date()): D("20")}
    assert client.post("/mandate/human-decision", headers=OWNER, json=decision).status_code == 409  # déjà décidée
    rule = authz.rule_for("POST", "/mandate/human-decision")
    assert rule is not None and rule.owner_only
    readme = (ROOT / "orchestration/README.md").read_text(encoding="utf-8")
    assert "`POST /mandate/human-decision` (registre du mandat : `HUMAN_APPROVED` / `HUMAN_REFUSED`)" in readme


# ===================================================================== R4-DOC-07 : credential PayPal de lecture


def test_r4doc07_paypal_balance_read_uses_a_credential_distinct_from_payments() -> None:
    read_type, read_id, read_name = GEN.CREDENTIALS["paypal_read"]
    pay_type, pay_id, pay_name = GEN.CREDENTIALS["paypal"]
    assert read_id != pay_id and read_name != pay_name and "lecture" in read_name
    by = {n["name"]: n for n in N.WORKFLOWS["07_stoploss_watch.json"]["nodes"]}
    node = next(n for name, n in by.items() if name.startswith("Lire le solde PayPal"))
    assert node["credentials"][read_type]["name"] == read_name
    for wf in N.WORKFLOWS.values():
        for n in wf["nodes"]:
            if pay_name in json.dumps(n.get("credentials", {}), ensure_ascii=False):
                assert "reporting/balances" not in json.dumps(n["parameters"]), n["name"]
    for rel in ("orchestration/README.md", "docs/00-pilotage/INTERVENTIONS_HUMAINES.md"):
        assert read_name in (ROOT / rel).read_text(encoding="utf-8"), rel


# ===================================================================== R4-DOC-10 : fraîcheur des entrées


def test_r4doc10_debt_statement_has_an_explicit_accepted_age_and_never_ages_the_photo(tmp_path: Path) -> None:
    client, svc, clock = F.boot(tmp_path)
    R3.cash_registers(client)  # relevés de cash à NOW − 10 min, déclaration des dettes à NOW − 10 min
    clock.now = NOW + timedelta(hours=20)
    for path, amount in (("/treasury/paypal-balance", "1000"), ("/treasury/bank-balance", "2000")):
        fresh = {"as_of": (clock.now - timedelta(minutes=5)).isoformat(), "balance_chf": amount, "source": "relevé horaire"}
        assert client.post(path, headers=JR.HTRES, json=fresh).status_code == 200
    photo = client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    assert photo.status_code == 200 and svc.stoploss_state.as_of == clock.now - timedelta(minutes=5)
    debts = body(photo)["sources"]["dettes_creances"]
    assert debts["max_age_minutes"] == 24 * 60 and debts["age_minutes"] == 20 * 60 + 10
    clock.now = NOW + timedelta(hours=25)
    for path, amount in (("/treasury/paypal-balance", "1000"), ("/treasury/bank-balance", "2000")):
        fresh = {"as_of": (clock.now - timedelta(minutes=5)).isoformat(), "balance_chf": amount, "source": "relevé horaire"}
        assert client.post(path, headers=JR.HTRES, json=fresh).status_code == 200
    stale = client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    assert stale.status_code == 409 and "âge accepté" in body(stale)["erreur"]
    for rel in ("docs/08-agents/05_finance-pricing.md", ".claude/agents/finance-pricing.md",
                "docs/00-pilotage/DELEGATION_AUTONOMIE.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "24 h" in text and "ne vieillit pas la photo" in text, rel


# ===================================================================== R3-DOC-04 : incident « simulation »


def test_r3doc04_only_an_incident_declared_simulation_accepts_a_fictif_cycle(tmp_path: Path) -> None:
    """Moteur en simulation : un incident sur données réelles ouvert SANS « simulation: true » exige un cycle réel."""
    client, svc, _ = F.boot(tmp_path)  # moteur en simulation (POKESHOP_DRY_RUN par défaut)
    for declared, expected in ((False, 409), (True, 200)):
        key = f"REEL-P{int(declared)}"
        payload = {"code": "INC-01", "product_key": key, "cause": "prix publié anormal", "simulation": declared}
        inc = body(client.post("/incidents", headers=JR.HINC, json=payload))["incident"]
        assert inc["simulation"] is declared and inc["fictif"] is False
        run = svc.sync_runs.record(SyncRunSummary(
            run_id=f"SYNC-FICTIF-{key}", supplier_id="fictif_grossiste_a", dry_run=True, started_at=NOW, finished_at=NOW,
            status="PROPRE", offers_costed=1, items=1, catalog_source="registre", recorded_by="n8n-01-sync",
            product_ids=(key,), fictif=True))  # fmt: skip
        resp = client.post(f"/incidents/{inc['incident_id']}/test", headers=JR.HQA,
                           json={"test_ref": run.run_id, "passed": True, "actor": "x1"})
        assert resp.status_code == expected, (declared, body(resp))
        if expected == 409:
            assert "cycle réel" in body(resp)["erreur"]
    for rel in ("docs/SPEC.md", "docs/00-pilotage/DELEGATION_AUTONOMIE.md", "docs/08-agents/12_qa-conformite.md",
                ".claude/agents/qa-conformite.md", "docs/08-agents/MATRICE_AUTONOMIE.md", "docs/07-ops/SOP_INCIDENTS.md",
                "docs/08-agents/BRIEF_COMMUN.md", "docs/08-agents/MATRICE_API.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "`simulation: true`" in text, rel
        assert "ou ouvert alors que le moteur est en simulation" not in text, rel


# ===================================================================== R4-DOC-11 : finance-pricing ne dépense pas


def test_r4doc11_finance_pricing_never_requests_a_spend(tmp_path: Path) -> None:
    assert "finance-pricing" not in authz.SPENDING_ROLES and "finance-pricing" not in authz.RELAYED_SPENDERS
    assert "finance-pricing" not in GEN.SPEND_RELAY_ROLES and "gateway_08_finance-pricing" not in GEN.CREDENTIALS
    hooks = [n["parameters"].get("path") for n in N.WORKFLOWS["08_mandat_depenses.json"]["nodes"] if n["type"].endswith("webhook")]
    assert "pokeshop-depense-finance-pricing" not in hooks and "pokeshop-depense-acquisition" in hooks
    client, svc, _ = F.boot(tmp_path)
    F.feed_registers(client, svc)
    spend = {**F.SPEND, "request": {**F.SPEND["request"], "requested_by": "finance-pricing", "idempotency_key": "FICTIF-R5-F"}}
    assert client.post("/mandate/check", headers=JR.HF, json=spend).status_code == 403
    assert client.post("/mandate/check", headers=JR.HMANDAT, json=spend).status_code == 403  # relais : jamais lui
    matrix = (ROOT / "docs/08-agents/MATRICE_AUTONOMIE.md").read_text(encoding="utf-8")
    assert "jamais de demande de dépense à son nom" in matrix
    readme = (ROOT / "orchestration/README.md").read_text(encoding="utf-8")
    assert "pokeshop-depense-finance-pricing" not in readme
    assert "08-agent-05" not in (ROOT / "docs/00-pilotage/DELEGATION_AUTONOMIE.md").read_text(encoding="utf-8")
