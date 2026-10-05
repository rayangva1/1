"""Tests de l'étoile polaire : contribution nette cumulée réalisée, au coût historique.

Exemple calculé à la main (FICTIF, repris dans docs/00-pilotage/ETOILE_POLAIRE.md) :

Semaine 2026-W45 : commandes A (184,92 net ; paiement 5,30 ; logistique 3,00 ; coût 140,00) et
B (87,88 ; 2,68 ; 3,00 ; 60,00), pub 20,00, charges fixes 92,31 (= 400 × 12 / 52)
=> 272,80 − 200,00 − 7,98 − 6,00 − 0 − 20,00 − 92,31 = −53,49.

Semaine 2026-W46 : commandes C (comme A), D et E (comme B), remboursement de B (−87,88 de ventes,
retour en stock −60,00 de coût, port retour 7,00 en SAV), pub 35,00, charges fixes 92,31
=> 272,80 − 200,00 − 10,66 − 9,00 − 7,00 − 35,00 − 92,31 = −81,17 ;
delta = −81,17 − (−53,49) = −27,68 ; cumul = −134,66.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest
from pokeshop.costs import HistoricalCostLedger, ReplacementCostBook
from pokeshop.forecast import north_star
from pokeshop.models import BasketLine, CostLot, ReplacementCost
from pokeshop.northstar import (
    COST_LEDGER_SOURCE,
    POST_LABELS_FR,
    ContributionEntry,
    NorthStarError,
    NorthStarLedger,
    Post,
    PostBreakdown,
    iso_week_label,
    week_start,
)
from pokeshop.pricing import basket_contribution
from pokeshop.rules import load_rules
from pydantic import ValidationError

TZ = ZoneInfo("Europe/Zurich")
W1 = date.fromisocalendar(2026, 45, 1)
W2 = W1 + timedelta(days=7)


def at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=TZ)


def lot(product: str, cost: str, qty: int = 10) -> CostLot:
    return CostLot(lot_id=f"LOT-{product}", product_key=product, received_at=at(W1 - timedelta(days=3)), qty=qty,
                   unit_cost=D(cost))  # fmt: skip


def hand_example() -> tuple[NorthStarLedger, HistoricalCostLedger, HistoricalCostLedger]:
    display = HistoricalCostLedger("FICTIF_DISPLAY")
    etb = HistoricalCostLedger("FICTIF_ETB")
    display.receive(lot("FICTIF_DISPLAY", "140"))
    etb.receive(lot("FICTIF_ETB", "60"))
    ns = NorthStarLedger()
    ns.record_order("A", at(W1 + timedelta(1)), net_sales_ht="184.92", payment_fees="5.30", logistics="3.00")
    display.issue(1, "A", at(W1 + timedelta(1)))
    ns.record_order("B", at(W1 + timedelta(3)), net_sales_ht="87.88", payment_fees="2.68", logistics="3.00")
    etb.issue(1, "B", at(W1 + timedelta(3)))
    ns.record_expense("pub-w45", at(W1 + timedelta(6)), Post.ACQUISITION, "20.00")
    ns.record_expense("fixes-w45", at(W1), Post.FIXED_COSTS, "92.31")
    for oid, offset, ledger, net, fee in (
        ("C", 1, display, "184.92", "5.30"),
        ("D", 2, etb, "87.88", "2.68"),
        ("E", 4, etb, "87.88", "2.68"),
    ):
        ns.record_order(oid, at(W2 + timedelta(offset)), net_sales_ht=net, payment_fees=fee, logistics="3.00")
        ledger.issue(1, oid, at(W2 + timedelta(offset)))
    ns.record_refund("R-B", at(W2 + timedelta(5)), net_sales_ht="87.88", order_id="B")
    etb.return_units(1, D("60"), "R-B", at(W2 + timedelta(5)))
    ns.record_expense("retour-B", at(W2 + timedelta(5)), Post.AFTER_SALES, "7.00")
    ns.record_expense("pub-w46", at(W2 + timedelta(6)), Post.ACQUISITION, "35.00")
    ns.record_expense("fixes-w46", at(W2), Post.FIXED_COSTS, "92.31")
    ns.sync_cost_ledger(display)
    ns.sync_cost_ledger(etb)
    return ns, display, etb


# ---------------------------------------------------------------------------- exemple à la main


def test_hand_computed_example_week_by_week() -> None:
    ns, _, _ = hand_example()
    report = ns.weekly_report()
    w45, w46 = report.rows
    assert (w45.iso_week, w46.iso_week) == ("2026-W45", "2026-W46")
    assert w45.breakdown == PostBreakdown(
        net_sales_ht=D("272.80"), historical_cost=D("200.00"), payment=D("7.98"), logistics=D("6.00"),
        acquisition=D("20.00"), fixed_costs=D("92.31"),
    )  # fmt: skip
    assert w45.net_contribution == D("-53.49") and w45.cumulative == D("-53.49") and w45.orders == 2
    assert w46.breakdown == PostBreakdown(
        net_sales_ht=D("272.80"), historical_cost=D("200.00"), payment=D("10.66"), logistics=D("9.00"),
        after_sales=D("7.00"), acquisition=D("35.00"), fixed_costs=D("92.31"),
    )  # fmt: skip
    assert w46.net_contribution == D("-81.17") and w46.orders == 3
    assert w46.delta_vs_previous_week == D("-27.68")
    assert w46.delta_by_post.payment == D("2.68") and w46.delta_by_post.after_sales == D("7.00")
    assert w46.delta_by_post.net_contribution == D("-27.68")
    assert report.cumulative == D("-134.66") and report.opening_cumulative == 0
    assert report.total.net_contribution == D("-134.66")
    assert w46.breakdown.contribution_before_acquisition == D("46.14")
    assert w46.breakdown.contribution_after_acquisition == D("11.14")


def test_hand_example_matches_forecast_north_star() -> None:
    ns, _, _ = hand_example()
    report = ns.weekly_report()
    projected = north_star(report.to_forecast_weeks())
    assert projected.cumulative == report.cumulative == D("-134.66")
    assert [r.net_contribution for r in projected.rows] == [D("-53.49"), D("-81.17")]


def test_markdown_review_table() -> None:
    ns, _, _ = hand_example()
    text = ns.weekly_report().render_markdown()
    expected = (
        "| 2026-W46 | 3 | 272,80 | 200,00 | 10,66 | 9,00 | 7,00 | 35,00 | 92,31 "
        "| **−81,17** | −27,68 | **−134,66** |"
    )
    assert expected in text
    assert all(label in text for label in POST_LABELS_FR.values())


# --------------------------------------------------------------------- coût historique seulement


def test_historical_cost_only_from_cost_ledger() -> None:
    ns = NorthStarLedger()
    with pytest.raises(NorthStarError, match="HistoricalCostLedger"):
        ns.record(ContributionEntry(entry_id="x", at=at(W1), post=Post.HISTORICAL_COST, amount=D("10")))
    with pytest.raises(NorthStarError, match="interdit"):
        ns.record_expense("x", at(W1), Post.HISTORICAL_COST, "10")
    with pytest.raises(NorthStarError, match="interdit"):
        ns.record_expense("y", at(W1), Post.NET_SALES, "10")


def test_cheaper_offer_never_changes_realised_contribution() -> None:
    ns, display, _ = hand_example()
    before = ns.weekly_report().cumulative
    book = ReplacementCostBook()
    book.update(ReplacementCost(product_key="FICTIF_DISPLAY", supplier_id="FICTIF_S", unit_cost=D("90"),
                                source_ts=at(W2 + timedelta(6))))  # fmt: skip
    assert ns.sync_cost_ledger(display) == 0
    assert ns.weekly_report().cumulative == before


def test_basket_cost_is_ignored_in_favour_of_historical_cost() -> None:
    params = load_rules().pricing
    basket = basket_contribution(
        [BasketLine(sku="FICTIF_DISPLAY", qty=1, unit_price_ttc=D("199.90"), unit_cost=D("1"))], params,
        shipping_cost_actual=D("3.00"),
    )  # fmt: skip
    ns = NorthStarLedger()
    entries = ns.record_basket("O-1", at(W1), basket)
    assert {e.post for e in entries} == {Post.NET_SALES, Post.PAYMENT, Post.LOGISTICS}
    totals = ns.totals()
    assert totals.net_sales_ht == D("184.92") and totals.payment == D("5.30") and totals.logistics == D("3.00")
    assert totals.historical_cost == 0 and totals.after_sales == 0 and totals.acquisition == 0


def test_invoice_adjustment_and_write_off_flow_into_cost() -> None:
    ledger = HistoricalCostLedger("FICTIF_ETB")
    ledger.receive(lot("FICTIF_ETB", "60", qty=4))
    ledger.issue(2, "O-1", at(W1 + timedelta(1)))
    variance = ledger.apply_invoice("LOT-FICTIF_ETB", D("62.50"), "FACT-FICTIF-1", at(W1 + timedelta(2)))
    ledger.write_off(1, "casse transport", at(W1 + timedelta(3)))
    ns = NorthStarLedger()
    assert ns.sync_cost_ledger(ledger) == 3  # sortie, écart de facture (part vendue), casse
    expected = D("120.00") + variance.cogs_adjustment + D("62.50")
    assert variance.cogs_adjustment == D("5.00")
    assert ns.totals().historical_cost == expected
    assert all(e.source == COST_LEDGER_SOURCE for e in ns.entries())


def test_invoice_adjustment_without_sold_units_is_not_a_cost() -> None:
    ledger = HistoricalCostLedger("FICTIF_ETB")
    ledger.receive(lot("FICTIF_ETB", "60", qty=4))
    ledger.apply_invoice("LOT-FICTIF_ETB", D("62.50"), "FACT-FICTIF-2", at(W1))
    ns = NorthStarLedger()
    assert ns.sync_cost_ledger(ledger) == 0 and ns.entries() == ()


# --------------------------------------------------------------------------------- idempotence


def test_sync_and_records_are_idempotent() -> None:
    ns, display, etb = hand_example()
    n = len(ns.entries())
    assert ns.sync_cost_ledger(display) == 0 and ns.sync_cost_ledger(etb) == 0
    ns.record_order("A", at(W1 + timedelta(1)), net_sales_ht="184.92", payment_fees="5.30", logistics="3.00")
    assert len(ns.entries()) == n
    assert ns.record(ns.entries()[0]) is False


def test_conflicting_rewrite_is_refused_atomically() -> None:
    ns = NorthStarLedger()
    ns.record_order("A", at(W1), net_sales_ht="100.00", payment_fees="2.80", logistics="3.00")
    with pytest.raises(NorthStarError, match="autre contenu"):
        ns.record_order("A", at(W1), net_sales_ht="100.00", payment_fees="2.90", logistics="4.00")
    assert ns.totals().logistics == D("3.00") and ns.totals().payment == D("2.80")  # rien d'écrit partiellement
    with pytest.raises(NorthStarError):
        ns.record(ns.entries()[0].replace(amount=D("1")))


def test_restore_from_entries() -> None:
    ns, _, _ = hand_example()
    restored = NorthStarLedger.from_entries(ns.entries())
    assert restored.weekly_report() == ns.weekly_report()


# ------------------------------------------------------------------------------- montants


@pytest.mark.parametrize("bad", ["1.005", 1.5, True, "abc", "NaN"])
def test_amounts_must_be_exact_cents(bad) -> None:
    ns = NorthStarLedger()
    with pytest.raises((NorthStarError, TypeError, ValueError)):
        ns.record_expense("x", at(W1), Post.LOGISTICS, bad)


def test_entry_validation() -> None:
    with pytest.raises(ValidationError):
        ContributionEntry(entry_id="x", at=datetime(2026, 11, 2, 10), post=Post.LOGISTICS, amount=D("1"))
    with pytest.raises(ValidationError):
        ContributionEntry(entry_id="x", at=at(W1), post=Post.LOGISTICS, amount=0.1)
    assert ContributionEntry(entry_id="x", at=at(W1), post=Post.LOGISTICS, amount="1.5").amount == D("1.50")


def test_order_and_refund_guards() -> None:
    ns = NorthStarLedger()
    with pytest.raises(NorthStarError):
        ns.record_order("A", at(W1), net_sales_ht="0", payment_fees="0", logistics="3.00")
    for missing in (None, "0", "-1"):  # MOT-18 : logistique réelle obligatoire sur le chemin réel
        with pytest.raises(NorthStarError, match="transporteur"):
            ns.record_order("B", at(W1), net_sales_ht="10.00", payment_fees="0", logistics=missing)
    with pytest.raises(NorthStarError):
        ns.record_refund("R", at(W1), net_sales_ht="-5")
    with pytest.raises(NorthStarError):
        ns.record_refund("R", at(W1), net_sales_ht="5", payment_fees_refunded="-1")
    entries = ns.record_refund("R", at(W1), net_sales_ht="50.00", payment_fees_refunded="1.25", order_id="A")
    assert [(e.post, e.amount) for e in entries] == [(Post.NET_SALES, D("-50.00")), (Post.PAYMENT, D("-1.25"))]
    zero_fee = ns.record_order("Z", at(W1), net_sales_ht="10.00", payment_fees="0", logistics="2.50")
    assert [e.post for e in zero_fee] == [Post.NET_SALES, Post.LOGISTICS]


# ------------------------------------------------------------------------------ charges fixes


def test_fixed_costs_accrued_by_day_sum_exactly() -> None:
    ns = NorthStarLedger()
    entries = ns.accrue_fixed_costs("400", 2026, 11)
    assert sum(e.amount for e in entries) == D("400.00")
    assert [e.amount for e in entries] == [D("13.34"), D("93.38"), D("93.33"), D("93.31"), D("93.31"), D("13.33")]
    assert all(e.post is Post.FIXED_COSTS for e in entries)
    assert ns.accrue_fixed_costs("400", 2026, 11) == entries  # idempotent
    assert len(ns.entries()) == 6
    with pytest.raises(NorthStarError):
        ns.accrue_fixed_costs("-1", 2026, 12)
    report = ns.weekly_report(date(2026, 11, 1), date(2026, 11, 30))
    assert report.total.fixed_costs == D("400.00") and len(report.rows) == 6


# ------------------------------------------------------------------------------- semaines


def test_empty_weeks_are_reported_with_delta() -> None:
    ns = NorthStarLedger()
    ns.record_expense("a", at(W1), Post.LOGISTICS, "10.00")
    ns.record_order("O", at(W1 + timedelta(days=14)), net_sales_ht="50.00", payment_fees="1.50", logistics="3.00")
    report = ns.weekly_report()
    assert [r.net_contribution for r in report.rows] == [D("-10.00"), D("0"), D("45.50")]
    assert [r.delta_vs_previous_week for r in report.rows] == [D("-10.00"), D("10.00"), D("45.50")]
    assert report.cumulative == D("35.50")


def test_report_window_has_opening_cumulative_and_previous_week_delta() -> None:
    ns, _, _ = hand_example()
    report = ns.weekly_report(start=W2, end=W2)
    assert report.opening_cumulative == D("-53.49")
    (row,) = report.rows
    assert row.delta_vs_previous_week == D("-27.68") and row.cumulative == D("-134.66")
    assert report.total.net_contribution == D("-81.17")
    later = ns.weekly_report(start=W2 + timedelta(days=7), end=W2 + timedelta(days=7))
    assert later.rows[0].net_contribution == 0 and later.cumulative == D("-134.66")


def test_report_guards() -> None:
    with pytest.raises(NorthStarError, match="aucune"):
        NorthStarLedger().weekly_report()
    assert NorthStarLedger().weekly_report(W1, W1).cumulative == 0
    with pytest.raises(NorthStarError, match="antérieur"):
        NorthStarLedger().weekly_report(W2, W1)


def test_weeks_follow_zurich_timezone() -> None:
    ns = NorthStarLedger()
    sunday_late_utc = datetime.combine(W1 - timedelta(days=1), time(23, 30), tzinfo=UTC)  # lundi 00:30 à Zurich
    ns.record_expense("x", sunday_late_utc, Post.LOGISTICS, "5.00")
    assert ns.weekly_report().rows[0].iso_week == "2026-W45"


def test_totals_by_period_for_validation_window() -> None:
    ns, _, _ = hand_example()
    w46 = ns.totals(at(W2, 0), at(W2 + timedelta(days=7), 0))
    assert w46.contribution_after_acquisition == D("11.14")
    assert ns.totals(end=at(W2, 0)).net_contribution == D("-53.49")


def test_week_helpers_and_breakdown() -> None:
    assert week_start(date(2026, 11, 8)) == date(2026, 11, 2)
    assert iso_week_label(date(2026, 12, 28)) == "2026-W53"
    b = PostBreakdown(net_sales_ht=D("100"), historical_cost=D("60"), payment=D("3"), logistics=D("4"),
                      after_sales=D("1"), acquisition=D("10"), fixed_costs=D("20"))  # fmt: skip
    assert (b.contribution_before_acquisition, b.contribution_after_acquisition, b.net_contribution) == (
        D("32"), D("22"), D("2"))  # fmt: skip
    assert b.get(Post.ACQUISITION) == D("10") and b.minus(b).net_contribution == 0


def test_etoile_polaire_doc_carries_the_hand_example() -> None:
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "docs" / "00-pilotage" / "ETOILE_POLAIRE.md"
    text = doc.read_text(encoding="utf-8")
    report = hand_example()[0].weekly_report()
    w45, w46 = report.rows
    for value in (w45.net_contribution, w46.net_contribution, w46.delta_vs_previous_week, report.cumulative):
        assert f"− {abs(value):.2f}".replace(".", ",") in text
    assert "11,14 CHF" in text and w46.breakdown.contribution_after_acquisition == D("11.14")
    assert "92,31" in text
    assert "## 5. Ce qui ne compte pas" in text
    assert text.rstrip().rsplit("\n## ", 1)[-1].startswith("Validation humaine requise")
