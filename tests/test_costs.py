"""Tests coût historique (CMP), coût de remplacement, écarts facture et historique des prix (BP §4, §12, §13).

Lots, factures et offres FICTIFS (préfixe FICTIF_).
"""

from __future__ import annotations

import random
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from pokeshop.costs import CostEntry, HistoricalCostLedger, PriceHistory, ReplacementCostBook
from pokeshop.errors import CostError, PokeshopError, PricingError
from pokeshop.models import (
    BasketLine,
    CostLot,
    DecisionStatus,
    PriceEventKind,
    PricingParams,
    ReplacementCost,
)
from pokeshop.pricing import basket_contribution, decide_price

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
KEY = "FICTIF_ETB_ALPHA_FR"

PARAMS = PricingParams(
    vat_rate_sales=D("0.081"),
    payment_pct=D("0.025"),
    payment_fixed=D("0.30"),
    logistics_cost=D("3"),
    after_sales_provision=D("1"),
    acquisition_cost=D("5"),
    target_margin=D("0.20"),
    rules_version="test-v1",
)


def lot(lot_id: str = "FICTIF_LOT_1", qty: int = 10, cost: str = "100", **kw) -> CostLot:
    base = dict(lot_id=lot_id, product_key=KEY, received_at=NOW, qty=qty, unit_cost=D(cost))
    base.update(kw)
    return CostLot(**base)


def rc(cost: str, supplier: str = "FICTIF_SUPPLIER_A", age_h: float = 1, key: str = KEY) -> ReplacementCost:
    return ReplacementCost(
        product_key=key,
        supplier_id=supplier,
        unit_cost=D(cost),
        source_ts=NOW - timedelta(hours=age_h),
        offer_ref=f"FICTIF_OFFER_{supplier}_{cost}",
    )


@pytest.fixture
def ledger() -> HistoricalCostLedger:
    led = HistoricalCostLedger(KEY)
    led.receive(lot())
    return led


# ============================================================ coût historique


class TestHistoricalCost:
    def test_receipt_values_stock(self, ledger):
        v = ledger.valuation()
        assert (v.qty_on_hand, v.total_value, v.average_unit_cost) == (10, D("1000.00"), D("100.0000"))
        assert ledger.lots()[0].cost_basis == "ESTIMATE"

    def test_moving_weighted_average(self, ledger):
        ledger.receive(lot("FICTIF_LOT_2", qty=5, cost="130"))
        assert ledger.total_value == D("1650.00")
        assert ledger.average_unit_cost == D("110.0000")
        cogs = ledger.issue(3, "FICTIF_CMD_1", NOW)
        assert cogs == D("330.00")
        assert ledger.average_unit_cost == D("110.0000")  # une sortie ne modifie pas le CMP
        ledger.receive(lot("FICTIF_LOT_3", qty=8, cost="95"))
        # (12 × 110 + 8 × 95) / 20 = 104
        assert ledger.average_unit_cost == D("104.0000")

    def test_rounding_and_no_residual_dust(self):
        led = HistoricalCostLedger(KEY)
        led.receive(lot(qty=3, cost="33.3333"))  # 99.9999 -> 100.00
        assert led.total_value == D("100.00")
        first = led.issue(1, "C1", NOW)
        second = led.issue(1, "C2", NOW)
        last = led.issue(1, "C3", NOW)
        assert (first, second) == (D("33.33"), D("33.34"))
        assert first + second + last == D("100.00")
        assert led.total_value == D("0") and led.qty_on_hand == 0
        assert led.average_unit_cost is None

    def test_issue_more_than_stock_refused(self, ledger):
        with pytest.raises(CostError, match="sortie 11"):
            ledger.issue(11, "C1", NOW)
        assert ledger.qty_on_hand == 10  # rien n'a bougé

    @pytest.mark.parametrize("qty", [0, -1, True])
    def test_invalid_issue_qty(self, ledger, qty):
        with pytest.raises(CostError):
            ledger.issue(qty, "C1", NOW)

    def test_duplicate_lot_refused(self, ledger):
        with pytest.raises(CostError, match="déjà reçu"):
            ledger.receive(lot())
        assert ledger.qty_on_hand == 10

    def test_lot_of_other_product_refused(self, ledger):
        with pytest.raises(CostError, match="produit"):
            ledger.receive(lot("FICTIF_LOT_X", product_key="FICTIF_AUTRE"))

    def test_naive_datetimes_refused(self, ledger):
        with pytest.raises(CostError):
            ledger.receive(lot("FICTIF_LOT_N", received_at=datetime(2026, 10, 4)))
        with pytest.raises(CostError):
            ledger.issue(1, "C1", datetime(2026, 10, 4))

    def test_lot_model_validation(self):
        with pytest.raises(ValidationError):
            lot(cost="0")
        with pytest.raises(ValidationError):
            lot(qty=0)
        with pytest.raises(ValidationError):
            lot(cost_basis="GUESS")

    def test_constructor_validation(self):
        with pytest.raises(CostError):
            HistoricalCostLedger("")
        with pytest.raises(CostError):
            HistoricalCostLedger(KEY, variance_tolerance_pct=D("-0.1"))

    def test_lookup(self, ledger):
        assert ledger.lot("FICTIF_LOT_1").qty == 10
        with pytest.raises(CostError, match="inconnu"):
            ledger.lot("FICTIF_LOT_404")

    def test_customer_return_at_recorded_cost(self, ledger):
        cogs = ledger.issue(2, "FICTIF_CMD_1", NOW)
        unit = cogs / 2
        ledger.return_units(1, unit, "FICTIF_RET_1", NOW)
        assert ledger.qty_on_hand == 9
        assert ledger.total_value == D("900.00")
        entry = ledger.journal()[-1]
        assert entry.kind == "RETURN" and entry.cogs == D("-100.00")

    @pytest.mark.parametrize("bad", [0, -1, True])
    def test_return_invalid_qty(self, ledger, bad):
        with pytest.raises(CostError):
            ledger.return_units(bad, D("100"), "R", NOW)

    def test_damaged_write_off(self, ledger):
        loss = ledger.write_off(1, "FICTIF_CASSE_1", NOW)
        assert loss == D("100.00")
        assert ledger.qty_on_hand == 9
        assert ledger.journal()[-1].kind == "WRITE_OFF"
        assert ledger.journal()[-1].cogs == D("0")  # perte, pas un coût des ventes

    @pytest.mark.parametrize("bad", [100.0, True, None, [D("1")]])
    def test_float_and_non_decimal_money_refused(self, ledger, bad):
        with pytest.raises(TypeError):
            ledger.return_units(1, bad, "R", NOW)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            ledger.apply_invoice("FICTIF_LOT_1", bad, "F", NOW)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", [D("0"), D("-1"), D("NaN"), D("Infinity"), "abc", 0])
    def test_non_positive_money_refused(self, ledger, bad):
        with pytest.raises(CostError):
            ledger.apply_invoice("FICTIF_LOT_1", bad, "F", NOW)
        with pytest.raises(CostError):
            ledger.return_units(1, bad, "R", NOW)

    def test_int_and_str_amounts_accepted_like_pricing(self, ledger):
        ledger.issue(2, "C1", NOW)
        ledger.return_units(1, "100", "RET", NOW)
        var = ledger.apply_invoice("FICTIF_LOT_1", 110, "FICTIF_FACT_1", NOW)
        assert var.actual_unit_cost == D("110")
        assert isinstance(var.actual_unit_cost, D)

    def test_journal_balances_with_valuation(self, ledger):
        ledger.receive(lot("FICTIF_LOT_2", qty=7, cost="91.17"))
        ledger.issue(4, "C1", NOW)
        ledger.write_off(1, "CASSE", NOW)
        ledger.return_units(1, D("95.5"), "RET", NOW)
        ledger.apply_invoice("FICTIF_LOT_2", D("93.40"), "FICTIF_FACT_2", NOW)
        journal = ledger.journal()
        assert [e.seq for e in journal] == list(range(1, len(journal) + 1))
        assert sum((e.amount for e in journal), D("0")) == ledger.total_value
        assert sum(e.qty if e.kind in ("RECEIPT", "RETURN") else -e.qty for e in journal) == ledger.qty_on_hand
        assert all(isinstance(e, CostEntry) for e in journal)

    def test_property_random_operations(self):
        rng = random.Random(1234)
        for run in range(40):
            led = HistoricalCostLedger(KEY)
            issued = D("0")
            received = D("0")
            for i in range(60):
                op = rng.random()
                if op < 0.4 or led.qty_on_hand == 0:
                    q = rng.randint(1, 12)
                    c = D(rng.randint(100, 30_000)) / 100
                    led.receive(lot(f"L{run}-{i}", qty=q, cost=str(c)))
                    received += (q * c).quantize(D("0.01"), rounding="ROUND_HALF_UP")
                elif op < 0.9:
                    q = rng.randint(1, led.qty_on_hand)
                    issued += led.issue(q, f"C{i}", NOW)
                else:
                    q = rng.randint(1, led.qty_on_hand)
                    issued += led.write_off(q, f"W{i}", NOW)
                assert led.total_value >= 0
                assert (led.qty_on_hand == 0) == (led.total_value == 0)
                assert received - issued == led.total_value
            if led.qty_on_hand:
                led.issue(led.qty_on_hand, "VIDAGE", NOW)
            assert led.total_value == D("0")

    def test_concurrent_issues_never_go_negative(self):
        led = HistoricalCostLedger(KEY)
        led.receive(lot(qty=50, cost="10"))
        barrier = threading.Barrier(20)
        ok: list[D] = []
        refused: list[Exception] = []
        guard = threading.Lock()

        def sell(i: int) -> None:
            barrier.wait()
            for _ in range(5):
                try:
                    amount = led.issue(1, f"C{i}", NOW)
                    with guard:
                        ok.append(amount)
                except CostError as exc:
                    with guard:
                        refused.append(exc)

        threads = [threading.Thread(target=sell, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(ok) == 50 and len(refused) == 50
        assert sum(ok) == D("500.00")
        assert led.qty_on_hand == 0 and led.total_value == 0


# ===================================== BP §13 : nouvelle offre moins chère


class TestCheaperOfferKeepsHistoricalCost:
    def test_cheaper_replacement_offer_does_not_touch_historical_cost(self, ledger):
        book = ReplacementCostBook()
        book.update(rc("100", age_h=48))
        book.update(rc("80", age_h=1))  # baisse de tarif fournisseur
        before = ledger.valuation()
        assert book.current(KEY, NOW).unit_cost == D("80")
        # coût historique inchangé : les unités déjà achetées restent à 100
        assert ledger.valuation() == before
        assert ledger.issue(1, "FICTIF_CMD_1", NOW) == D("100.00")

    def test_margin_realised_on_historical_cost_not_replacement(self, ledger):
        """La marge réalisée utilise le coût historique ; le coût de remplacement sert au prix futur."""
        book = ReplacementCostBook()
        book.update(rc("80"))
        future = decide_price(book.current(KEY, NOW).unit_cost, PARAMS)
        historical = ledger.average_unit_cost
        sale = basket_contribution(
            [BasketLine(sku=KEY, qty=1, unit_price_ttc=future.recommended_price, unit_cost=historical)],
            PARAMS,
            shipping_cost_actual=D("3"),
        )
        assert sale.product_cost == D("100.00")
        assert future.landed_cost == D("80.00")
        # prix calculé au coût de remplacement plus bas : la vente du stock historique est signalée
        assert sale.contribution_pct < PARAMS.target_margin


# ============================================ BP §13 : facture réelle plus chère


class TestInvoiceVariance:
    def test_higher_invoice_creates_flagged_variance(self, ledger):
        ledger.issue(4, "FICTIF_CMD_1", NOW)  # 6 unités encore en stock
        var = ledger.apply_invoice("FICTIF_LOT_1", D("110"), "FICTIF_FACT_1", NOW)
        assert var.direction == "HIGHER"
        assert var.flagged is True
        assert var.delta_unit == D("10")
        assert var.delta_total == D("100.00")
        assert var.delta_pct == D("0.1000")
        assert var.inventory_adjustment == D("60.00")
        assert var.cogs_adjustment == D("40.00")  # unités déjà vendues : écart en coût des ventes
        assert ledger.total_value == D("660.00")
        assert ledger.average_unit_cost == D("110.0000")
        updated = ledger.lot("FICTIF_LOT_1")
        assert updated.cost_basis == "INVOICE" and updated.unit_cost == D("110")
        assert updated.ref == "FICTIF_FACT_1"
        assert ledger.variances() == (var,)
        assert ledger.journal()[-1].kind == "INVOICE_ADJUSTMENT"

    def test_invoice_reconciliation_is_idempotent(self, ledger):
        a = ledger.apply_invoice("FICTIF_LOT_1", D("110"), "FICTIF_FACT_1", NOW)
        value = ledger.total_value
        b = ledger.apply_invoice("FICTIF_LOT_1", D("110"), "FICTIF_FACT_1", NOW + timedelta(hours=1))
        assert a == b
        assert ledger.total_value == value  # reprise sans double écriture
        assert len(ledger.journal()) == 2
        with pytest.raises(CostError, match="déjà rapproché"):
            ledger.apply_invoice("FICTIF_LOT_1", D("111"), "FICTIF_FACT_2", NOW)

    def test_lower_invoice(self, ledger):
        var = ledger.apply_invoice("FICTIF_LOT_1", D("95"), "FICTIF_FACT_1", NOW)
        assert var.direction == "LOWER" and var.flagged
        assert ledger.total_value == D("950.00")

    @pytest.mark.parametrize(
        "actual,flagged",
        [(D("100"), False), (D("100.004"), False), (D("100.40"), False), (D("100.50"), True), (D("99.50"), True)],
    )
    def test_tolerance_requires_both_pct_and_chf(self, ledger, actual, flagged):
        var = ledger.apply_invoice("FICTIF_LOT_1", actual, "FICTIF_FACT_1", NOW)
        assert var.flagged is flagged
        if actual == D("100"):
            assert var.direction == "EQUAL"

    def test_invoice_after_everything_sold_goes_to_cogs(self, ledger):
        ledger.issue(10, "FICTIF_CMD_1", NOW)
        var = ledger.apply_invoice("FICTIF_LOT_1", D("120"), "FICTIF_FACT_1", NOW)
        assert var.inventory_adjustment == D("0.00")
        assert var.cogs_adjustment == D("200.00")
        assert ledger.total_value == D("0")

    def test_lower_invoice_never_makes_value_negative(self):
        led = HistoricalCostLedger(KEY)
        led.receive(lot("FICTIF_LOT_A", qty=10, cost="100"))
        led.receive(lot("FICTIF_LOT_B", qty=10, cost="10"))
        led.issue(19, "C", NOW)  # reste 1 unité valorisée 55
        var = led.apply_invoice("FICTIF_LOT_A", D("1"), "FICTIF_FACT_A", NOW)
        assert led.total_value >= 0
        assert var.inventory_adjustment + var.cogs_adjustment == var.delta_total

    def test_invoice_requires_reference_and_known_lot(self, ledger):
        with pytest.raises(CostError, match="référence"):
            ledger.apply_invoice("FICTIF_LOT_1", D("110"), "", NOW)
        with pytest.raises(CostError, match="inconnu"):
            ledger.apply_invoice("FICTIF_LOT_404", D("110"), "F", NOW)
        with pytest.raises(CostError):
            ledger.apply_invoice("FICTIF_LOT_1", D("110"), "F", datetime(2026, 10, 4))

    def test_higher_invoice_raises_replacement_cost_and_price(self, ledger):
        """Écart signalé => nouveau coût rendu => nouvelle décision (jamais sur une commande conclue)."""
        var = ledger.apply_invoice("FICTIF_LOT_1", D("110"), "FICTIF_FACT_1", NOW)
        before = decide_price(var.estimated_unit_cost, PARAMS)
        after = decide_price(var.actual_unit_cost, PARAMS, current_public=before.recommended_price)
        assert after.recommended_price > before.recommended_price
        assert after.status is DecisionStatus.REVIEW  # > 5 % en un jour => validation


# ============================================================ remplacement


class TestReplacementCostBook:
    def test_latest_and_out_of_order_updates(self):
        book = ReplacementCostBook()
        assert book.update(rc("100", age_h=2)) is True
        assert book.update(rc("90", age_h=5)) is False  # plus ancien : ignoré
        assert book.latest(KEY).unit_cost == D("100")
        assert len(book.history(KEY)) == 2  # conservé dans l'historique

    def test_current_is_cheapest_fresh_offer(self):
        book = ReplacementCostBook()
        book.update(rc("100", "FICTIF_A", age_h=1))
        book.update(rc("95", "FICTIF_B", age_h=2))
        book.update(rc("70", "FICTIF_C", age_h=30))  # périmée : jamais retenue
        cur = book.current(KEY, NOW)
        assert cur.supplier_id == "FICTIF_B" and cur.unit_cost == D("95")
        assert book.latest(KEY).supplier_id == "FICTIF_A"
        assert book.latest(KEY, "FICTIF_C").unit_cost == D("70")

    def test_no_valid_offer_returns_none(self):
        book = ReplacementCostBook()
        assert book.current(KEY, NOW) is None
        assert book.latest(KEY) is None
        book.update(rc("100", age_h=25))
        assert book.current(KEY, NOW) is None
        assert book.current(KEY, NOW, max_age=timedelta(hours=48)).unit_cost == D("100")

    def test_tie_broken_by_supplier_id(self):
        book = ReplacementCostBook()
        book.update(rc("90", "FICTIF_Z"))
        book.update(rc("90", "FICTIF_A"))
        assert book.current(KEY, NOW).supplier_id == "FICTIF_A"

    def test_products_are_isolated(self):
        book = ReplacementCostBook()
        book.update(rc("90", key="FICTIF_DISPLAY"))
        assert book.current(KEY, NOW) is None
        assert book.history(KEY) == ()

    def test_model_validation(self):
        with pytest.raises(ValidationError):
            rc("0")
        with pytest.raises(ValidationError):
            ReplacementCost(product_key=KEY, supplier_id="S", unit_cost=D("1"), source_ts=datetime(2026, 10, 4))


# ====================================== BP §13 : retour au dernier prix validé


def decision(cost: str = "140", **kw):
    return decide_price(D(cost), PARAMS, **kw)


class TestPriceHistory:
    def test_publish_ok_decision_and_rollback_to_last_validated(self):
        h = PriceHistory()
        d1 = decision("140")
        h.publish(KEY, d1.recommended_price, NOW, "engine", validated=True, decision=d1)
        d2 = decision("150", current_public=D("209.90"))
        assert d2.status is DecisionStatus.REVIEW
        h.publish(KEY, d2.recommended_price, NOW + timedelta(hours=1), "proprietaire", validated=True, decision=d2)
        d3 = decision("160")
        h.publish(KEY, d3.recommended_price, NOW + timedelta(hours=2), "engine", validated=False, decision=d3)
        assert h.current_price(KEY) == d3.recommended_price
        assert h.last_validated_price(KEY) == d2.recommended_price
        event = h.rollback(KEY, NOW + timedelta(hours=3), "qa", "prix anormal signalé")
        assert event.kind is PriceEventKind.ROLLED_BACK
        assert event.price == d2.recommended_price
        assert h.current_price(KEY) == d2.recommended_price
        # second retour : on revient au validé antérieur
        h.rollback(KEY, NOW + timedelta(hours=4), "qa", "second incident")
        assert h.current_price(KEY) == D("209.90")
        with pytest.raises(PricingError, match="aucun prix validé antérieur"):
            h.rollback(KEY, NOW + timedelta(hours=5), "qa", "plus rien")

    def test_rollback_requires_reason(self):
        h = PriceHistory()
        with pytest.raises(PricingError, match="motif"):
            h.rollback(KEY, NOW, "qa", "")

    def test_rollback_without_history(self):
        with pytest.raises(PricingError):
            PriceHistory().rollback(KEY, NOW, "qa", "incident")

    @pytest.mark.parametrize(
        "kw,status",
        [
            (dict(unknown_fields=["language"]), DecisionStatus.DRAFT),
            (dict(previous_cost=D("10")), DecisionStatus.BLOCKED),
        ],
    )
    def test_draft_and_blocked_never_published(self, kw, status):
        d = decision(**kw)
        assert d.status is status
        with pytest.raises(PricingError, match="publication interdite"):
            PriceHistory().publish(KEY, D("209.90"), NOW, "engine", validated=True, decision=d)

    def test_review_requires_human_validation(self):
        d = decision(market_ref=D("150"))
        assert d.status is DecisionStatus.REVIEW
        h = PriceHistory()
        with pytest.raises(PricingError, match="validation humaine"):
            h.publish(KEY, d.recommended_price, NOW, "engine", validated=False, decision=d)
        h.publish(KEY, d.recommended_price, NOW, "proprietaire", validated=True, decision=d)
        assert h.last_validated_price(KEY) == d.recommended_price

    def test_unvalidated_price_must_match_engine_decision(self):
        d = decision()
        h = PriceHistory()
        with pytest.raises(PricingError, match="validation humaine"):
            h.publish(KEY, D("199.90"), NOW, "engine", validated=False, decision=d)
        h.publish(KEY, D("214.90"), NOW, "proprietaire", validated=True, decision=d)
        assert h.current_price(KEY) == D("214.90")

    @pytest.mark.parametrize("price", [D("0"), D("-1"), D("NaN"), "abc"])
    def test_invalid_public_price(self, price):
        with pytest.raises(PricingError):
            PriceHistory().publish(KEY, price, NOW, "engine", validated=True)

    def test_float_price_refused(self):
        with pytest.raises(TypeError):
            PriceHistory().publish(KEY, 209.9, NOW, "engine", validated=True)  # type: ignore[arg-type]

    def test_empty_product_key_refused(self):
        with pytest.raises(PricingError):
            PriceHistory().publish("", D("10"), NOW, "engine", validated=True)

    def test_validate_marks_current_price(self):
        h = PriceHistory()
        h.publish(KEY, D("209.90"), NOW, "engine", validated=False)
        assert h.last_validated_price(KEY) is None
        ev = h.validate(KEY, NOW, "proprietaire", "ok après contrôle marché")
        assert ev.kind is PriceEventKind.VALIDATED
        assert h.last_validated_price(KEY) == D("209.90")
        with pytest.raises(PricingError):
            h.validate("FICTIF_INCONNU", NOW, "proprietaire")

    def test_record_decision_traces_without_publishing(self):
        h = PriceHistory()
        d = decision(unknown_fields=["frais"])
        ev = h.record_decision(KEY, d, NOW)
        assert ev.kind is PriceEventKind.PROPOSED
        assert ev.status is DecisionStatus.DRAFT
        assert ev.inputs_hash == d.inputs_hash and ev.rules_version == "test-v1"
        assert "UNKNOWN_FIELDS" in ev.note
        assert h.current_price(KEY) is None

    def test_journal_is_append_only_and_filterable(self):
        h = PriceHistory()
        d = decision()
        h.record_decision(KEY, d, NOW)
        h.publish(KEY, d.recommended_price, NOW, "engine", validated=True, decision=d)
        h.publish("FICTIF_AUTRE", D("41.90"), NOW, "engine", validated=True)
        assert [e.seq for e in h.events()] == [1, 2, 3]
        assert [e.kind for e in h.events(KEY)] == [PriceEventKind.PROPOSED, PriceEventKind.PUBLISHED]
        published = h.events(KEY)[1]
        assert published.inputs_hash == d.inputs_hash and published.note == "validé"
        with pytest.raises(CostError):
            h.publish(KEY, D("10"), datetime(2026, 10, 4), "engine", validated=True)

    def test_rollback_never_changes_a_concluded_order(self):
        """BP §5 : ne jamais changer le prix d'une commande déjà conclue."""
        h = PriceHistory()
        h.publish(KEY, D("209.90"), NOW, "engine", validated=True)
        h.publish(KEY, D("219.90"), NOW, "proprietaire", validated=True)
        order_line = BasketLine(sku=KEY, qty=1, unit_price_ttc=h.current_price(KEY), unit_cost=D("140"))
        concluded = basket_contribution([order_line], PARAMS, shipping_cost_actual=D("3"))
        h.rollback(KEY, NOW, "qa", "retour arrière")
        assert h.current_price(KEY) == D("209.90")
        assert order_line.unit_price_ttc == D("219.90")
        assert basket_contribution([order_line], PARAMS, shipping_cost_actual=D("3")) == concluded

    def test_concurrent_publications_keep_sequence(self):
        h = PriceHistory()
        barrier = threading.Barrier(10)

        def pub(i: int) -> None:
            barrier.wait()
            h.publish(f"FICTIF_{i % 3}", D("10.90") + i, NOW, "engine", validated=True)

        threads = [threading.Thread(target=pub, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(e.seq for e in h.events()) == list(range(1, 11))


def test_cost_errors_are_pokeshop_errors():
    assert issubclass(CostError, PokeshopError) and issubclass(CostError, ValueError)
