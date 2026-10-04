"""Cas de référence chiffrés du business plan (BP §4 « Exemple fictif et reproductible »).

Ces valeurs sont des HYPOTHÈSES FICTIVES du BP, pas des devis fournisseur.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest

from pokeshop.costs import HistoricalCostLedger, PriceHistory, ReplacementCostBook
from pokeshop.errors import CostError, InsufficientStockError, PricingError
from pokeshop.models import (
    AllocationLine,
    AvailabilityStatus,
    BasketLine,
    CostLot,
    DecisionStatus,
    Discount,
    LandedCostInput,
    PromiseKind,
    Reason,
    ReorderCandidate,
    ReplacementCost,
    ReservationStatus,
    SupplierOffer,
    TierDiscount,
    VatMode,
)
from pokeshop.pricing import (
    allocate_inbound_costs,
    basket_contribution,
    contribution,
    contribution_breakdown,
    decide_price,
    evaluate_offer,
    floor_price,
    floor_price_exact,
    landed_unit_cost,
    round_up_retail,
)
from pokeshop.rules import load_all_profiles, load_rules
from pokeshop.stock import StockRegistry, availability_promise, preorder_quota, propose_reorder


@pytest.fixture(scope="module")
def profiles():
    return load_all_profiles()


@pytest.fixture(scope="module")
def eff(profiles):
    return profiles[VatMode.EFFECTIVE].pricing


@pytest.fixture(scope="module")
def nreg(profiles):
    return profiles[VatMode.NOT_REGISTERED].pricing


def test_rules_file_carries_bp_hypotheses(eff, nreg):
    for p in (eff, nreg):
        assert p.payment_pct == D("0.025")
        assert p.payment_fixed == D("0.30")
        assert p.logistics_cost == D("3")
        assert p.after_sales_provision == D("1")
        assert p.acquisition_cost == D("5")
        assert p.target_margin == D("0.20")
        assert p.hard_floor_margin == D("0.12")
        assert p.hard_floor_chf_per_order == D("8")
        assert p.market_review_threshold == D("0.10")
        assert p.max_daily_price_change == D("0.05")
    assert eff.vat_rate_sales == D("0.081")
    assert nreg.vat_rate_sales == D("0")
    rs = load_rules()
    assert rs.stock.staleness_hours == 24
    assert rs.stock.extension_budget_cap == D("0.25")
    assert "hypoth" in rs.status


def test_floor_price_effective_c140(eff):
    exact = floor_price_exact(D("140"), eff)
    assert str(exact).startswith("208.7949")
    assert floor_price(D("140"), eff) == D("208.79")


def test_floor_rounded_up_to_209_90(eff):
    assert round_up_retail(floor_price_exact(D("140"), eff)) == D("209.90")
    assert round_up_retail(D("208.79")) == D("209.90")


def test_decide_price_reproduces_bp_example(eff):
    d = decide_price(D("140"), eff)
    assert d.status is DecisionStatus.OK
    assert d.floor_price == D("208.79")
    assert d.recommended_price == D("209.90")
    assert d.contribution_pct >= D("0.20")
    assert d.rules_version == "v1-2026-10-04"
    assert len(d.inputs_hash) == 64


def test_contribution_at_199_90(eff):
    b = contribution_breakdown(D("199.90"), D("140"), eff)
    assert b.net_revenue == D("184.92")
    assert b.payment_fees == D("5.30")
    assert b.contribution_chf == D("30.62")
    assert b.contribution_pct == D("0.1656")
    assert contribution(D("199.90"), D("140"), eff) == (D("30.62"), D("0.1656"))


def test_199_90_is_below_target_but_above_hard_floor(eff):
    d = decide_price(D("140"), eff, candidate_price=D("199.90"))
    assert d.status is DecisionStatus.REVIEW
    assert d.has(Reason.BELOW_TARGET_MARGIN)
    assert d.contribution_chf == D("30.62")
    assert d.recommended_price == D("209.90")


def test_not_registered_floor_207_28(nreg):
    assert floor_price(D("151.34"), nreg) == D("207.28")


def test_not_registered_cost_includes_8_1_pct_non_recoverable(nreg):
    inp = LandedCostInput(
        purchase_net=D("140"),
        currency="CHF",
        fx_rate_to_chf=D("1"),
        fx_source="CHF",
        fx_date=date(2026, 10, 4),
        price_includes_vat=False,
        supplier_vat_rate=D("0.081"),
        supplier_vat_country="CH",
        units_per_pack=1,
        vat_mode=VatMode.NOT_REGISTERED,
    )
    c = landed_unit_cost(inp)
    assert c == D("151.34")
    assert floor_price(c, nreg) == D("207.28")


def test_effective_cost_excludes_recoverable_swiss_vat(eff):
    inp = LandedCostInput(
        purchase_net=D("151.34"),
        currency="CHF",
        fx_rate_to_chf=D("1"),
        fx_source="CHF",
        fx_date=date(2026, 10, 4),
        price_includes_vat=True,
        supplier_vat_rate=D("0.081"),
        supplier_vat_country="CH",
        units_per_pack=1,
        vat_mode=VatMode.EFFECTIVE,
    )
    assert landed_unit_cost(inp) == D("140.00")
    assert floor_price(landed_unit_cost(inp), eff) == D("208.79")


def test_floor_exact_value_and_two_decimal_rounding(eff):
    """208.7949… arrondi HALF_UP à 2 décimales = 208.79 ; arrondi retail vers le haut = 209.90."""
    exact = floor_price_exact(D("140"), eff)
    assert D("208.7949") < exact < D("208.7950")
    assert exact.quantize(D("0.01")) == D("208.79")
    assert floor_price(D("140"), eff) == D("208.79")
    assert round_up_retail(floor_price(D("140"), eff)) == D("209.90")


def test_reference_price_recheck_after_rounding(eff):
    """Arrondir puis revérifier : 209.90 respecte la cible 20 % et le plancher 8 CHF."""
    chf, pct = contribution(D("209.90"), D("140"), eff)
    assert pct >= eff.target_margin
    assert chf >= eff.hard_floor_chf_per_order


# ============================================================================
# BP §13 « Tests obligatoires du moteur » — une preuve exécutable par item,
# sur le fichier de règles livré (config/pricing_rules.v1.yaml). Données FICTIVES.
# ============================================================================

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _offer(**kw) -> SupplierOffer:
    base = dict(
        supplier_id="FICTIF_SUPPLIER_A",
        supplier_sku="FICTIF-ETB-001",
        gtin="2000000000008",
        language="FR",
        extension="FICTIF Extension Alpha",
        format="etb",
        content="9 boosters",
        sealed=True,
        units_per_pack=1,
        price=D("140"),
        currency="CHF",
        price_includes_vat=False,
        vat_rate=D("0"),
        moq=1,
        carton_qty=1,
        availability_status=AvailabilityStatus.IN_STOCK,
        available_qty=30,
        ship_from_country="CH",
        source_ts=NOW - timedelta(hours=1),
        raw_ref="FICTIF_snapshot",
    )
    base.update(kw)
    return SupplierOffer(**base)


def _lci(**kw) -> LandedCostInput:
    base = dict(
        purchase_net=D("100"),
        currency="CHF",
        fx_rate_to_chf=D("1"),
        fx_source="CHF",
        fx_date=date(2026, 10, 4),
        price_includes_vat=False,
        supplier_vat_rate=D("0"),
        units_per_pack=1,
        vat_mode=VatMode.EFFECTIVE,
    )
    base.update(kw)
    return LandedCostInput(**base)


class TestBP13Checklist:
    # -- ligne 1 : devises, TVA, conditionnement, paliers ------------------------------
    def test_01_eur_versus_chf(self):
        eur = _lci(currency="EUR", fx_rate_to_chf=D("0.94"), fx_source="FICTIF_BNS_2026-10-04")
        assert landed_unit_cost(eur) == D("94.00")
        assert landed_unit_cost(_lci()) == D("100.00")

    def test_02_ht_versus_ttc(self):
        ht = _lci(purchase_net=D("100"), supplier_vat_rate=D("0.081"), supplier_vat_country="CH")
        ttc = _lci(
            purchase_net=D("108.10"), price_includes_vat=True, supplier_vat_rate=D("0.081"), supplier_vat_country="CH"
        )
        assert landed_unit_cost(ht) == landed_unit_cost(ttc) == D("100.00")

    def test_03_vat_recoverable_or_not(self):
        kw = dict(purchase_net=D("100"), supplier_vat_rate=D("0.081"), supplier_vat_country="CH", import_vat=D("5"))
        assert landed_unit_cost(_lci(vat_mode=VatMode.EFFECTIVE, **kw)) == D("100.00")
        assert landed_unit_cost(_lci(vat_mode=VatMode.NOT_REGISTERED, **kw)) == D("113.10")

    def test_04_carton_versus_unit(self):
        assert landed_unit_cost(_lci(purchase_net=D("600"), units_per_pack=6)) == D("100.00")

    def test_05_tier_discounts(self):
        tiers = (TierDiscount(min_qty=6, discount_pct=D("0.05")), TierDiscount(min_qty=12, discount_pct=D("0.10")))
        costs = [landed_unit_cost(_lci(tier_discounts=tiers, order_qty=q)) for q in (1, 6, 12)]
        assert costs == [D("100.00"), D("95.00"), D("90.00")]

    # -- ligne 2 : identité produit ----------------------------------------------------
    def test_06_fr_versus_jp_en(self, eff):
        assert evaluate_offer(_offer(), eff, now=NOW, inbound_freight_alloc=D("0")).status is DecisionStatus.OK
        for lang in ("JP", "EN"):
            d = evaluate_offer(_offer(language=lang), eff, now=NOW, inbound_freight_alloc=D("0"))
            assert d.status is DecisionStatus.BLOCKED and d.has(Reason.LANGUAGE_MISMATCH)
        d = evaluate_offer(_offer(language="UNKNOWN"), eff, now=NOW, inbound_freight_alloc=D("0"))
        assert d.status is DecisionStatus.DRAFT

    def test_07_same_name_different_content(self):
        a = _offer(content="36 boosters").identity()
        b = _offer(content="18 boosters").identity()
        assert a.key != b.key

    def test_08_gtin_absent(self, eff):
        d = evaluate_offer(_offer(gtin=None), eff, now=NOW, inbound_freight_alloc=D("0"))
        assert d.status is DecisionStatus.DRAFT and not d.is_publishable

    def test_09_zero_price(self, eff):
        d = evaluate_offer(_offer(price=D("0")), eff, now=NOW, inbound_freight_alloc=D("0"))
        assert d.status is DecisionStatus.BLOCKED and d.has(Reason.ZERO_PRICE)
        with pytest.raises(PricingError):
            landed_unit_cost(_lci(purchase_net=D("0")))

    def test_10_duplicates_never_double_count(self, eff):
        with pytest.raises(PricingError):
            basket_contribution([BasketLine(sku="A", qty=1, unit_price_ttc=D("10"), unit_cost=D("5"))] * 2, eff)
        led = HistoricalCostLedger("FICTIF_P")
        led.receive(CostLot(lot_id="L1", product_key="FICTIF_P", received_at=NOW, qty=1, unit_cost=D("10")))
        with pytest.raises(CostError):
            led.receive(CostLot(lot_id="L1", product_key="FICTIF_P", received_at=NOW, qty=1, unit_cost=D("10")))

    # -- ligne 3 : frais et panier -----------------------------------------------------
    def test_11_inbound_freight_allocated(self):
        lines = [AllocationLine(key="ETB", qty=6, value=D("600")), AllocationLine(key="DISPLAY", qty=2, value=D("400"))]
        alloc = {a.key: a for a in allocate_inbound_costs(D("25"), lines)}
        assert alloc["ETB"].allocated_total + alloc["DISPLAY"].allocated_total == D("25.00")
        assert landed_unit_cost(_lci(inbound_freight_alloc=alloc["ETB"].per_unit)) == D("102.50")

    def test_12_free_shipping(self, eff):
        line = [BasketLine(sku="ETB", qty=1, unit_price_ttc=D("209.90"), unit_cost=D("140"))]
        paid = basket_contribution(line, eff, D("0"), shipping_cost_actual=D("3"))
        free = basket_contribution(line, eff, D("0"), shipping_cost_actual=D("9.50"))
        assert paid.contribution_chf - free.contribution_chf == D("6.50")
        assert free.shipping_gap == D("-9.50")

    def test_13_discount(self, eff):
        line = [BasketLine(sku="ETB", qty=1, unit_price_ttc=D("209.90"), unit_cost=D("140"))]
        ok = basket_contribution(
            line, eff, D("0"), Discount(kind="PERCENT", value=D("0.05")), shipping_cost_actual=D("3")
        )
        ko = basket_contribution(
            line, eff, D("0"), Discount(kind="PERCENT", value=D("0.20")), shipping_cost_actual=D("3")
        )
        assert ok.status is not DecisionStatus.BLOCKED
        assert ko.status is DecisionStatus.BLOCKED and Reason.BELOW_HARD_FLOOR.value in ko.reasons

    def test_14_fixed_fees_once_per_order(self, eff):
        a = BasketLine(sku="A", qty=1, unit_price_ttc=D("209.90"), unit_cost=D("140"))
        b = BasketLine(sku="B", qty=1, unit_price_ttc=D("41.90"), unit_cost=D("20"))
        both = basket_contribution([a, b], eff, shipping_cost_actual=D("3"))
        sep = sum((basket_contribution([x], eff, shipping_cost_actual=D("3")).contribution_chf for x in (a, b)), D("0"))
        assert abs(both.contribution_chf - sep - D("9.30")) <= D("0.02")

    def test_15_multi_product_basket(self, eff):
        lines = [
            BasketLine(sku="ETB", qty=2, unit_price_ttc=D("209.90"), unit_cost=D("140")),
            BasketLine(sku="BOOSTER", qty=4, unit_price_ttc=D("4.90"), unit_cost=D("3.50")),
        ]
        r = basket_contribution(lines, eff, D("7.90"), Discount(kind="AMOUNT", value=D("10"), code="FICTIF10"))
        assert sum(x.contribution_chf for x in r.lines) == r.contribution_chf
        assert r.status is DecisionStatus.OK

    # -- ligne 4 : fraîcheur et anomalies --------------------------------------------
    def test_16_stale_source(self, eff):
        old = _offer(source_ts=NOW - timedelta(hours=25), allocation_qty=10)
        d = evaluate_offer(old, eff, now=NOW, inbound_freight_alloc=D("0"))
        assert d.restock_eligible is False and d.has(Reason.STALE_OFFER)
        promise = availability_promise(local_sellable=0, offers=[old], now=NOW, preorders_enabled=True)
        assert promise.kind is PromiseKind.UNAVAILABLE
        local = availability_promise(local_sellable=2, offers=[old], now=NOW)
        assert local.kind is PromiseKind.LOCAL_STOCK  # le stock local réel reste vendable

    def test_17_price_times_ten(self, eff):
        d = evaluate_offer(_offer(price=D("1400")), eff, now=NOW, inbound_freight_alloc=D("0"), previous_cost=D("140"))
        assert d.status is DecisionStatus.BLOCKED and d.has(Reason.PRICE_ANOMALY)

    def test_18_incomplete_import_is_draft(self, eff):
        d = evaluate_offer(_offer(units_per_pack=None, vat_rate=None), eff, now=NOW, inbound_freight_alloc=D("0"))
        assert d.status is DecisionStatus.DRAFT and d.recommended_price is None

    def test_19_resume_without_double_write(self):
        reg = StockRegistry(clock=lambda: NOW)
        reg.receive("SKU", 3, "R1")
        r1 = reg.reserve("SKU", 1, "CMD-1")
        assert reg.reserve("SKU", 1, "CMD-1") == r1  # rejeu du même événement
        reg.fulfill(r1.reservation_id)
        reg.refund(r1.reservation_id, "RMB-1", returned=True)
        reg.refund(r1.reservation_id, "RMB-1", returned=True)  # rejeu
        assert reg.level("SKU").on_hand == 3 and reg.sellable("SKU") == 3

    # -- ligne 5 : stock ---------------------------------------------------------------
    def test_20_last_unit_bought_simultaneously(self):
        reg = StockRegistry()
        reg.receive("DISPLAY", 1, "R")
        barrier = threading.Barrier(10)
        results: list[bool] = []
        lock = threading.Lock()

        def buy(i: int) -> None:
            barrier.wait()
            try:
                reg.reserve("DISPLAY", 1, f"CMD-{i}")
                ok = True
            except InsufficientStockError:
                ok = False
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=buy, args=(i,)) for i in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert results.count(True) == 1 and reg.sellable("DISPLAY") == 0

    def test_21_reservation_cancelled(self):
        reg = StockRegistry(clock=lambda: NOW)
        reg.receive("SKU", 2, "R")
        res = reg.reserve("SKU", 2, "CMD-1")
        assert reg.cancel(res.reservation_id).status is ReservationStatus.CANCELLED
        assert reg.sellable("SKU") == 2

    def test_22_refund(self):
        reg = StockRegistry(clock=lambda: NOW)
        reg.receive("SKU", 2, "R")
        res = reg.reserve("SKU", 1, "CMD-1")
        reg.fulfill(res.reservation_id)
        assert reg.refund(res.reservation_id, "RMB-1", returned=True).refunded_qty == 1
        assert reg.sellable("SKU") == 2

    def test_23_damaged_stock(self):
        reg = StockRegistry(clock=lambda: NOW)
        reg.receive("SKU", 3, "R")
        reg.mark_damaged("SKU", 1, "CASSE")
        assert reg.sellable("SKU") == 2

    def test_24_preorder_quota(self):
        assert preorder_quota(firm_allocation=20, committed_preorders=5, safety=2) == 13
        o = _offer(allocation_qty=20, available_qty=None, availability_status=AvailabilityStatus.ALLOCATION)
        p = availability_promise(
            local_sellable=0, offers=[o], now=NOW, preorders_enabled=True, committed_preorders=5, preorder_safety=2
        )
        assert p.kind is PromiseKind.PREORDER and p.promisable_qty == 13

    # -- ligne 6 : coûts et prix validés ------------------------------------------------
    def test_25_cheaper_offer_keeps_historical_cost(self):
        led = HistoricalCostLedger("P")
        led.receive(CostLot(lot_id="L1", product_key="P", received_at=NOW, qty=5, unit_cost=D("100")))
        book = ReplacementCostBook()
        book.update(ReplacementCost(product_key="P", supplier_id="S", unit_cost=D("80"), source_ts=NOW))
        assert book.current("P", NOW).unit_cost == D("80")
        assert led.average_unit_cost == D("100.0000")

    def test_26_real_invoice_higher(self):
        led = HistoricalCostLedger("P")
        led.receive(CostLot(lot_id="L1", product_key="P", received_at=NOW, qty=5, unit_cost=D("100")))
        var = led.apply_invoice("L1", D("108"), "FICTIF_FACT_1", NOW)
        assert var.flagged and var.direction == "HIGHER" and led.average_unit_cost == D("108.0000")

    def test_27_back_to_last_validated_price(self, eff):
        h = PriceHistory()
        d = decide_price(D("140"), eff)
        h.publish("P", d.recommended_price, NOW, "engine", validated=True, decision=d)
        h.publish("P", D("249.90"), NOW, "engine", validated=False)
        h.rollback("P", NOW, "qa", "prix anormal")
        assert h.current_price("P") == D("209.90")

    def test_28_reorder_is_a_proposal_never_an_order(self):
        c = ReorderCandidate(
            product_key="P",
            extension="FICTIF Extension Alpha",
            offer=_offer(moq=6, carton_qty=6),
            unit_cost_chf=D("100"),
            sellable_qty=0,
            avg_daily_sales=D("1"),
            lead_time_days=7,
        )
        p = propose_reorder([c], budget_available=D("3000"), stock_budget_total=D("3000"), now=NOW)
        assert p.status == "PROPOSAL_TO_VALIDATE" and p.requires_human_validation is True
        assert p.total_cost_chf <= D("750")  # plafond 25 % par extension
