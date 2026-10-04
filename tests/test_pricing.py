"""Tests du moteur de prix (BP §4-5, §13 « Tests obligatoires du moteur »).

Toutes les offres et tous les montants sont FICTIFS (GTIN de test préfixe 200).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from pokeshop.errors import IncompleteDataError, PricingError
from pokeshop.models import (
    DEFAULT_ROUNDING_TIERS,
    AllocationLine,
    AvailabilityStatus,
    BasketLine,
    DecisionStatus,
    Discount,
    LandedCostInput,
    PricingParams,
    ProductIdentity,
    Reason,
    RoundingTier,
    SupplierOffer,
    TierDiscount,
    VatMode,
    canonical_hash,
    canonical_json,
    explain,
)
from pokeshop.pricing import (
    allocate_amount,
    allocate_inbound_costs,
    apply_tier_discount,
    as_decimal,
    basket_contribution,
    contribution,
    contribution_breakdown,
    decide_price,
    estimate_import_vat,
    evaluate_offer,
    floor_price,
    floor_price_exact,
    floor_violations,
    is_price_anomaly,
    landed_cost_breakdown,
    landed_input_from_offer,
    landed_unit_cost,
    offer_unknown_fields,
    order_floor_price_exact,
    round_up_retail,
    select_tier,
)

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
FICTIF_GTIN = "2000000000008"  # GTIN de test (plage 200, checksum valide) — FICTIF


def params(**kw) -> PricingParams:
    base = dict(
        vat_rate_sales=D("0.081"),
        payment_pct=D("0.025"),
        payment_fixed=D("0.30"),
        logistics_cost=D("3"),
        after_sales_provision=D("1"),
        acquisition_cost=D("5"),
        target_margin=D("0.20"),
        rules_version="test-v1",
        small_product_max_cost=D("15"),
    )
    base.update(kw)
    return PricingParams(**base)


EFF = params()
NREG = params(vat_rate_sales=D("0"))


def lci(**kw) -> LandedCostInput:
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


def offer(**kw) -> SupplierOffer:
    base = dict(
        supplier_id="FICTIF_SUPPLIER_A",
        supplier_sku="FICTIF-ETB-001",
        gtin=FICTIF_GTIN,
        language="FR",
        extension="FICTIF Extension Alpha",
        format="etb",
        content="9 boosters + accessoires",
        sealed=True,
        units_per_pack=1,
        price=D("140.00"),
        currency="CHF",
        price_includes_vat=False,
        vat_rate=D("0"),
        moq=1,
        carton_qty=6,
        availability_status=AvailabilityStatus.IN_STOCK,
        available_qty=30,
        ship_from_country="CH",
        source_ts=NOW - timedelta(hours=1),
        raw_ref="FICTIF_snapshot_001",
    )
    base.update(kw)
    return SupplierOffer(**base)


# =============================================================== modèles


class TestModels:
    def test_pricing_params_infers_vat_mode(self):
        assert EFF.vat_mode is VatMode.EFFECTIVE
        assert NREG.vat_mode is VatMode.NOT_REGISTERED
        assert EFF.per_order_costs == D("9.30")

    @pytest.mark.parametrize(
        "kw",
        [
            dict(vat_rate_sales=D("0.081"), vat_mode=VatMode.NOT_REGISTERED),
            dict(vat_rate_sales=D("0"), vat_mode=VatMode.EFFECTIVE),
            dict(hard_floor_margin=D("0.25")),
            dict(payment_pct=D("1")),
            dict(target_margin=D("-0.1")),
            dict(payment_fixed=D("-0.01")),
            dict(price_anomaly_factor=D("1")),
            dict(rounding_tiers=(RoundingTier(min_price=D("5"), step=D("1"), endings=(D("0.9"),)),)),
            dict(
                rounding_tiers=(
                    RoundingTier(min_price=D("0"), step=D("1"), endings=(D("0.9"),)),
                    RoundingTier(min_price=D("0"), step=D("1"), endings=(D("0.5"),)),
                )
            ),
            dict(vat_rate_sales="nan"),
            dict(vat_rate_sales="abc"),
            dict(vat_rate_sales=None),
            dict(vat_rate_sales=True),
            dict(unknown_field=1),
        ],
    )
    def test_pricing_params_rejects_invalid(self, kw):
        with pytest.raises(ValidationError):
            params(**kw)

    def test_replace_revalidates_and_reinfers_mode(self):
        p = EFF.replace(vat_rate_sales=D("0"))
        assert p.vat_mode is VatMode.NOT_REGISTERED
        with pytest.raises(ValidationError):
            EFF.replace(hard_floor_margin=D("0.5"))

    def test_models_are_frozen(self):
        with pytest.raises(ValidationError):
            EFF.target_margin = D("0.5")  # type: ignore[misc]

    @pytest.mark.parametrize(
        "kw",
        [
            dict(endings=(D("1.00"),)),
            dict(endings=(D("-0.1"),)),
            dict(endings=(D("0.905"),)),
            dict(endings=(D("0.9"), D("0.9"))),
            dict(step=D("0")),
            dict(step=D("1.005")),
            dict(endings=()),
        ],
    )
    def test_rounding_tier_validation(self, kw):
        base = dict(min_price=D("0"), step=D("1"), endings=(D("0.9"),))
        base.update(kw)
        with pytest.raises(ValidationError):
            RoundingTier(**base)

    def test_canonical_hash_normalizes_decimals(self):
        assert canonical_hash({"a": D("140")}) == canonical_hash({"a": D("140.00")})
        assert canonical_hash({"a": D("0")}) == canonical_hash({"a": D("-0.00")})
        assert canonical_hash({"a": D("140")}) != canonical_hash({"a": D("140.01")})
        assert canonical_json({"b": 1, "a": [D("1.50")]}) == '{"a":["1.5"],"b":1}'

    def test_canonical_hash_rejects_float_and_naive_datetime(self):
        with pytest.raises(TypeError):
            canonical_hash({"a": 1.5})
        with pytest.raises(ValueError):
            canonical_hash({"ts": datetime(2026, 10, 4)})
        with pytest.raises(TypeError):
            canonical_hash({"x": object()})

    def test_canonical_hash_supports_dates_sets_enums_timedeltas(self):
        h1 = canonical_hash({"d": date(2026, 10, 4), "s": {"b", "a"}, "e": VatMode.EFFECTIVE, "t": timedelta(hours=24)})
        h2 = canonical_hash({"t": timedelta(seconds=86400), "e": "EFFECTIVE", "s": {"a", "b"}, "d": date(2026, 10, 4)})
        assert h1 == h2

    def test_supplier_offer_normalization(self):
        o = offer(currency="eur", language=" fr ", gtin="  ", ship_from_country="fr", extension=" ")
        assert o.currency == "EUR"
        assert o.language == "FR"
        assert o.gtin is None
        assert o.extension is None
        assert o.ship_from_country == "FR"
        assert o.effective_vat_country == "FR"
        assert offer(vat_country="CH", ship_from_country="FR").effective_vat_country == "CH"

    @pytest.mark.parametrize(
        "kw",
        [
            dict(currency="EURO"),
            dict(ship_from_country="FRA"),
            dict(vat_rate=D("1")),
            dict(source_ts=datetime(2026, 10, 4, 12)),
            dict(price=D("-1")),
            dict(units_per_pack=0),
            dict(raw_ref=""),
            dict(supplier_id=""),
        ],
    )
    def test_supplier_offer_rejects_invalid(self, kw):
        with pytest.raises(ValidationError):
            offer(**kw)

    def test_identity_key_distinguishes_language_and_content(self):
        fr36 = offer(content="36 boosters").identity()
        fr18 = offer(content="18 boosters").identity()
        jp36 = offer(content="36 boosters", language="JP").identity()
        assert fr36.key != fr18.key
        assert fr36.key != jp36.key
        assert fr36.is_complete
        assert ProductIdentity(gtin=None, language="UNKNOWN").missing_fields() == (
            "gtin",
            "language",
            "extension",
            "format",
            "content",
            "sealed",
        )
        assert ProductIdentity(sealed=False).key.endswith("|OPEN")

    def test_explain_translates_codes(self):
        labels = explain(("ABOVE_MARKET", "CODE_INCONNU"))
        assert "marché" in labels[0]
        assert labels[1] == "CODE_INCONNU"

    def test_discount_percent_must_be_fraction(self):
        with pytest.raises(ValidationError):
            Discount(kind="PERCENT", value=D("10"))


# ============================================================ coût rendu


class TestLandedCost:
    def test_as_decimal_rejects_float_and_bool(self):
        with pytest.raises(TypeError):
            as_decimal(1.5)
        with pytest.raises(TypeError):
            as_decimal(True)
        with pytest.raises(PricingError):
            as_decimal("abc")
        with pytest.raises(PricingError):
            as_decimal("NaN")
        assert as_decimal("1.10") == D("1.10")
        assert as_decimal(3) == D(3)

    def test_chf_unit_ht(self):
        assert landed_unit_cost(lci()) == D("100.00")

    @pytest.mark.parametrize(
        "currency,price,fx,expected",
        [
            ("EUR", D("100"), D("0.9400"), D("94.00")),
            ("EUR", D("100"), D("0.93125"), D("93.13")),
            ("CHF", D("100"), D("1"), D("100.00")),
        ],
    )
    def test_eur_versus_chf(self, currency, price, fx, expected):
        inp = lci(purchase_net=price, currency=currency, fx_rate_to_chf=fx, fx_source="FICTIF_BNS")
        assert landed_unit_cost(inp) == expected

    def test_chf_requires_fx_one(self):
        with pytest.raises(ValidationError):
            lci(fx_rate_to_chf=D("0.95"))

    @pytest.mark.parametrize(
        "mode,includes_vat,price,country,expected",
        [
            (VatMode.EFFECTIVE, True, D("108.10"), "CH", D("100.00")),
            (VatMode.EFFECTIVE, False, D("100"), "CH", D("100.00")),
            (VatMode.NOT_REGISTERED, True, D("108.10"), "CH", D("108.10")),
            (VatMode.NOT_REGISTERED, False, D("100"), "CH", D("108.10")),
            # TVA française facturée : jamais récupérable en Suisse (prudence BP §4)
            (VatMode.EFFECTIVE, True, D("108.10"), "FR", D("108.10")),
            # pays de TVA inconnu : traité comme non récupérable
            (VatMode.EFFECTIVE, True, D("108.10"), None, D("108.10")),
        ],
    )
    def test_ht_versus_ttc_and_vat_recoverability(self, mode, includes_vat, price, country, expected):
        inp = lci(
            purchase_net=price,
            price_includes_vat=includes_vat,
            supplier_vat_rate=D("0.081"),
            supplier_vat_country=country,
            vat_mode=mode,
        )
        assert landed_unit_cost(inp) == expected

    def test_breakdown_reports_recoverable_vat(self):
        b = landed_cost_breakdown(
            lci(
                purchase_net=D("108.10"),
                price_includes_vat=True,
                supplier_vat_rate=D("0.081"),
                supplier_vat_country="CH",
            )
        )
        assert b.supplier_vat_recoverable is True
        assert b.supplier_vat_unit_chf == D("8.1000")
        assert b.recoverable_vat_unit_chf == D("8.1000")
        assert b.total == D("100.00")

    @pytest.mark.parametrize("mode,expected", [(VatMode.EFFECTIVE, D("107.00")), (VatMode.NOT_REGISTERED, D("115.10"))])
    def test_import_vat_only_in_cost_when_not_registered(self, mode, expected):
        inp = lci(
            purchase_net=D("100"),
            currency="EUR",
            fx_rate_to_chf=D("1"),
            fx_source="FICTIF",
            inbound_freight_alloc=D("5"),
            customs_and_fees=D("2"),
            import_vat=D("8.10"),
            vat_mode=mode,
        )
        b = landed_cost_breakdown(inp)
        assert b.total == expected
        assert b.import_vat_in_cost_unit_chf == (D("0") if mode is VatMode.EFFECTIVE else D("8.1"))
        assert b.recoverable_vat_unit_chf == (D("8.1") if mode is VatMode.EFFECTIVE else D("0"))

    @pytest.mark.parametrize(
        "pack_price,units,expected",
        [(D("600"), 6, D("100.00")), (D("100"), 1, D("100.00")), (D("100"), 3, D("33.33")), (D("200"), 3, D("66.67"))],
    )
    def test_carton_versus_unit(self, pack_price, units, expected):
        assert landed_unit_cost(lci(purchase_net=pack_price, units_per_pack=units)) == expected

    TIERS = (TierDiscount(min_qty=6, discount_pct=D("0.05")), TierDiscount(min_qty=12, discount_pct=D("0.10")))

    @pytest.mark.parametrize(
        "qty,expected",
        [
            (None, D("100")),
            (1, D("100")),
            (5, D("100")),
            (6, D("95.00")),
            (11, D("95.00")),
            (12, D("90.00")),
            (100, D("90.00")),
        ],
    )
    def test_tier_discounts(self, qty, expected):
        assert apply_tier_discount(D("100"), self.TIERS, qty) == expected
        assert landed_unit_cost(lci(tier_discounts=self.TIERS, order_qty=qty)) == expected

    def test_tier_with_absolute_price_and_order_independence(self):
        tiers = (TierDiscount(min_qty=24, price=D("80")), TierDiscount(min_qty=6, discount_pct=D("0.05")))
        assert apply_tier_discount(D("100"), tiers, 24) == D("80")
        assert apply_tier_discount(D("100"), tiers, 23) == D("95.00")
        assert select_tier(tiers, 30).min_qty == 24
        assert select_tier((), 30) is None
        b = landed_cost_breakdown(lci(tier_discounts=tiers, order_qty=30))
        assert b.tier_applied == 24
        assert b.total == D("80.00")

    def test_tier_validation(self):
        with pytest.raises(ValidationError):
            TierDiscount(min_qty=6)
        with pytest.raises(ValidationError):
            TierDiscount(min_qty=6, discount_pct=D("0.1"), price=D("5"))
        with pytest.raises(ValidationError):
            TierDiscount(min_qty=6, discount_pct=D("1"))
        with pytest.raises(ValidationError):
            lci(tier_discounts=(TierDiscount(min_qty=6, discount_pct=D("0.1")), TierDiscount(min_qty=6, price=D("5"))))
        with pytest.raises(PricingError):
            select_tier(self.TIERS, 0)
        with pytest.raises(PricingError):
            apply_tier_discount(D("-1"), self.TIERS, 6)

    def test_zero_purchase_price_is_an_anomaly(self):
        with pytest.raises(PricingError, match="nul"):
            landed_unit_cost(lci(purchase_net=D("0")))

    def test_freight_and_fees_added_per_unit(self):
        assert landed_unit_cost(lci(inbound_freight_alloc=D("2.5"), customs_and_fees=D("1.25"))) == D("103.75")

    def test_estimate_import_vat(self):
        assert estimate_import_vat(D("100")) == D("8.10")
        assert estimate_import_vat(D("123.45"), D("0.081")) == D("10.00")
        with pytest.raises(PricingError):
            estimate_import_vat(D("-1"))
        with pytest.raises(PricingError):
            estimate_import_vat(D("1"), D("1"))


class TestAllocation:
    def test_freight_split_by_value(self):
        lines = [AllocationLine(key="A", qty=3, value=D("60")), AllocationLine(key="B", qty=1, value=D("40"))]
        res = allocate_inbound_costs(D("10.00"), lines)
        assert [r.allocated_total for r in res] == [D("6.00"), D("4.00")]
        assert [r.per_unit for r in res] == [D("2.0000"), D("4.0000")]

    def test_freight_split_by_quantity(self):
        lines = [AllocationLine(key="A", qty=3, value=D("60")), AllocationLine(key="B", qty=1, value=D("40"))]
        res = allocate_inbound_costs(D("10.00"), lines, basis="quantity")
        assert [r.allocated_total for r in res] == [D("7.50"), D("2.50")]

    def test_allocated_freight_flows_into_landed_cost(self):
        lines = [AllocationLine(key="ETB", qty=6, value=D("600")), AllocationLine(key="DISPLAY", qty=2, value=D("400"))]
        res = {r.key: r for r in allocate_inbound_costs(D("25.00"), lines)}
        assert res["ETB"].allocated_total + res["DISPLAY"].allocated_total == D("25.00")
        etb = landed_unit_cost(lci(inbound_freight_alloc=res["ETB"].per_unit))
        assert etb == D("102.50")

    @pytest.mark.parametrize(
        "total,weights,expected",
        [
            (D("10.00"), [D("1"), D("1"), D("1")], [D("3.34"), D("3.33"), D("3.33")]),
            (D("0.02"), [D("1"), D("1"), D("1")], [D("0.01"), D("0.01"), D("0.00")]),
            (D("5"), [D("0"), D("0")], [D("2.50"), D("2.50")]),
            (D("-1.00"), [D("1"), D("2")], [D("-0.33"), D("-0.67")]),
            (D("1.005"), [D("1")], [D("1.01")]),
        ],
    )
    def test_allocate_amount_exact_sum(self, total, weights, expected):
        res = allocate_amount(total, weights)
        assert res == expected

    def test_allocate_amount_random_sums(self):
        rng = random.Random(42)
        for _ in range(300):
            n = rng.randint(1, 8)
            weights = [D(rng.randint(0, 10_000)) / 100 for _ in range(n)]
            total = D(rng.randint(0, 1_000_000)) / 100
            res = allocate_amount(total, weights)
            assert sum(res) == total
            assert all(r >= 0 for r in res)

    def test_allocation_errors(self):
        with pytest.raises(PricingError):
            allocate_amount(D("1"), [])
        with pytest.raises(PricingError):
            allocate_amount(D("1"), [D("-1"), D("2")])
        with pytest.raises(PricingError):
            allocate_inbound_costs(D("-1"), [AllocationLine(key="A", qty=1, value=D("1"))])
        with pytest.raises(PricingError):
            allocate_inbound_costs(D("1"), [AllocationLine(key="A", qty=1, value=D("1"))], basis="weight")  # type: ignore[arg-type]
        dup = [AllocationLine(key="A", qty=1, value=D("1")), AllocationLine(key="A", qty=1, value=D("1"))]
        with pytest.raises(PricingError):
            allocate_inbound_costs(D("1"), dup)


# ============================================================ prix plancher


class TestFloorPrice:
    def test_denominator_not_positive_raises(self):
        p = params(target_margin=D("0.98"), hard_floor_margin=D("0.12"))
        with pytest.raises(PricingError, match="dénominateur"):
            floor_price(D("100"), p)

    def test_denominator_zero_raises(self):
        # (1 − m)/(1 + t) − r = 0 avec t = 0, m = 0.5, r = 0.5
        p = params(vat_rate_sales=D("0"), target_margin=D("0.5"), payment_pct=D("0.5"))
        with pytest.raises(PricingError):
            floor_price_exact(D("10"), p)

    def test_negative_or_float_cost(self):
        with pytest.raises(PricingError):
            floor_price(D("-1"), EFF)
        with pytest.raises(TypeError):
            floor_price(140.0, EFF)  # type: ignore[arg-type]

    def test_per_order_costs_excluded_for_addon(self):
        assert floor_price(D("3.50"), EFF, per_order_costs=False) == D("4.89")

    def test_order_floor_guarantees_8_chf(self):
        price = order_floor_price_exact(D("20"), EFF)
        chf, _ = contribution(price.quantize(D("0.01")) + D("0.01"), D("20"), EFF)
        assert chf >= D("8")

    def test_floor_linear_in_cost(self):
        den = (1 - D("0.2")) / D("1.081") - D("0.025")
        assert abs(floor_price_exact(D("50"), EFF) - (D("50") + D("9.30")) / den) < D("1E-20")


# ================================================================ arrondi


class TestRounding:
    @pytest.mark.parametrize(
        "p,expected",
        [
            ("0.01", "0.50"),
            ("0.50", "0.50"),
            ("0.51", "0.90"),
            ("0.91", "1.50"),
            ("3.12", "3.50"),
            ("4.89", "4.90"),
            ("9.90", "9.90"),
            ("9.91", "10.90"),
            ("9.95", "10.90"),
            ("10", "10.90"),
            ("10.90", "10.90"),
            ("10.91", "11.90"),
            ("41.44", "41.90"),
            ("99.90", "99.90"),
            ("99.91", "104.90"),
            ("100", "104.90"),
            ("104.90", "104.90"),
            ("104.91", "109.90"),
            ("208.79", "209.90"),
            ("208.7949804", "209.90"),
            ("209.90", "209.90"),
            ("209.91", "214.90"),
            ("1000", "1004.90"),
        ],
    )
    def test_default_grid(self, p, expected):
        assert round_up_retail(D(p)) == D(expected)

    @pytest.mark.parametrize(
        "p,ending,expected",
        [("208.79", "0.90", "208.90"), ("208.95", "0.90", "209.90"), ("5", "0.95", "5.95"), ("7.00", "0.00", "7.00")],
    )
    def test_simple_ending_rule(self, p, ending, expected):
        assert round_up_retail(D(p), D(ending)) == D(expected)

    def test_custom_tiers(self):
        tiers = (RoundingTier(min_price=D("0"), step=D("5"), endings=(D("4.95"),)),)
        assert round_up_retail(D("12.10"), tiers=tiers) == D("14.95")

    @pytest.mark.parametrize("p", ["0", "-1"])
    def test_non_positive_rejected(self, p):
        with pytest.raises(PricingError):
            round_up_retail(D(p))

    @pytest.mark.parametrize("ending", ["1.00", "-0.10", "0.905", "abc"])
    def test_invalid_ending_is_pricing_error(self, ending):
        with pytest.raises(PricingError):
            round_up_retail(D("5"), D(ending) if ending != "abc" else ending)

    def test_invalid_grid(self):
        with pytest.raises(PricingError):
            round_up_retail(D("5"), tiers=(RoundingTier(min_price=D("1"), step=D("1"), endings=(D("0.9"),)),))

    def test_properties_random(self):
        rng = random.Random(7)
        prices = sorted(D(rng.randint(1, 300_000)) / 100 for _ in range(2000))
        prev = D("0")
        for p in prices:
            r = round_up_retail(p)
            assert r >= p
            assert r >= prev  # monotone
            assert round_up_retail(r) == r  # idempotent
            assert r % D("0.05") == 0  # compatible 5 centimes
            assert r - p < (D("1.00") if p < 100 else D("5.00"))
            prev = r


# =========================================================== contribution


class TestContribution:
    def test_breakdown_consistency(self):
        b = contribution_breakdown(D("209.90"), D("140"), EFF)
        assert b.vat + b.net_revenue == b.price_ttc
        assert b.per_order_costs == D("9.00")
        assert b.contribution_pct >= D("0.20")

    def test_addon_contribution_excludes_order_costs(self):
        chf, pct = contribution(D("4.90"), D("3.50"), EFF, per_order_costs=False)
        assert chf == D("0.91")
        assert pct == D("0.2009")

    def test_invalid_inputs(self):
        with pytest.raises(PricingError):
            contribution(D("0"), D("1"), EFF)
        with pytest.raises(PricingError):
            contribution(D("10"), D("-1"), EFF)

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_property_price_above_floor_meets_target(self, p):
        """Pour tout prix ≥ plancher exact : contribution % ≥ m − ε (arrondis à 0.01)."""
        rng = random.Random(2026)
        for _ in range(1500):
            cost = D(rng.randint(100, 200_000)) / 100
            floor = floor_price_exact(cost, p)
            price = (floor + D(rng.randint(0, 5000)) / 100).quantize(D("0.01"), rounding="ROUND_CEILING")
            chf, pct = contribution(price, cost, p)
            net = price / (1 + p.vat_rate_sales)
            eps = D("0.015") / net + D("0.0001")
            assert pct >= p.target_margin - eps, (cost, price, pct)

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_property_price_below_floor_misses_target(self, p):
        rng = random.Random(99)
        for _ in range(500):
            cost = D(rng.randint(2000, 200_000)) / 100
            floor = floor_price_exact(cost, p)
            price = (floor * D("0.97")).quantize(D("0.01"))
            _, pct = contribution(price, cost, p)
            assert pct < p.target_margin


# ============================================================== décision


class TestDecidePrice:
    def test_ok_case(self):
        d = decide_price(D("140"), EFF)
        assert d.status is DecisionStatus.OK
        assert d.is_publishable
        assert d.reasons == ()
        assert d.evaluated_price == D("209.90")
        assert d.landed_cost == D("140.00")
        assert d.restock_eligible

    @pytest.mark.parametrize("fields", [["frais"], ["language"], ["units_per_pack", "vat_rate"], ["  ", "taxe"]])
    def test_unknown_fields_draft(self, fields):
        d = decide_price(D("140"), EFF, unknown_fields=fields)
        assert d.status is DecisionStatus.DRAFT
        assert d.has(Reason.UNKNOWN_FIELDS)
        assert not d.is_publishable
        assert any("Champs inconnus" in n for n in d.notes)

    def test_empty_unknown_fields_ignored(self):
        assert decide_price(D("140"), EFF, unknown_fields=["", " "]).status is DecisionStatus.OK

    @pytest.mark.parametrize("cost", [D("0"), D("-5")])
    def test_zero_cost_blocked(self, cost):
        d = decide_price(cost, EFF)
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.ZERO_OR_NEGATIVE_COST)
        assert d.recommended_price is None

    @pytest.mark.parametrize(
        "market,status,reason",
        [
            (D("180"), DecisionStatus.REVIEW, Reason.ABOVE_MARKET),
            (D("189.80"), DecisionStatus.REVIEW, Reason.ABOVE_MARKET),
            (D("190"), DecisionStatus.OK, None),
            (D("250"), DecisionStatus.OK, None),
            (D("0"), DecisionStatus.REVIEW, Reason.INVALID_MARKET_REF),
        ],
    )
    def test_market_rule(self, market, status, reason):
        d = decide_price(D("140"), EFF, market_ref=market)
        assert d.status is status
        if reason:
            assert d.has(reason)
        # la marge n'est jamais sacrifiée automatiquement
        assert d.recommended_price == D("209.90")

    @pytest.mark.parametrize(
        "current,status,reason",
        [
            (D("209.90"), DecisionStatus.OK, None),
            (D("205"), DecisionStatus.OK, None),
            (D("199.91"), DecisionStatus.OK, None),
            (D("199.90"), DecisionStatus.REVIEW, Reason.DAILY_CHANGE_ABOVE_CAP),
            (D("220.90"), DecisionStatus.OK, None),
            (D("220.95"), DecisionStatus.REVIEW, Reason.DAILY_CHANGE_ABOVE_CAP),
            (D("20.99"), DecisionStatus.BLOCKED, Reason.PRICE_ANOMALY),
            (D("2099"), DecisionStatus.BLOCKED, Reason.PRICE_ANOMALY),
            (D("-1"), DecisionStatus.REVIEW, Reason.INVALID_CURRENT_PRICE),
        ],
    )
    def test_daily_variation_rule(self, current, status, reason):
        d = decide_price(D("140"), EFF, current_public=current)
        assert d.status is status
        if reason:
            assert d.has(reason)

    def test_current_price_below_hard_floor_flagged(self):
        d = decide_price(D("140"), EFF, current_public=D("160"))
        assert d.has(Reason.CURRENT_PRICE_BELOW_HARD_FLOOR)
        assert d.status is DecisionStatus.REVIEW

    @pytest.mark.parametrize(
        "prev,blocked",
        [
            (D("14"), True),
            (D("13.99"), True),
            (D("14.01"), False),
            (D("140"), False),
            (D("1399.99"), False),
            (D("1400"), True),
        ],
    )
    def test_cost_x10_anomaly(self, prev, blocked):
        d = decide_price(D("140"), EFF, previous_cost=prev)
        assert (d.status is DecisionStatus.BLOCKED) is blocked
        assert d.has(Reason.PRICE_ANOMALY) is blocked

    def test_is_price_anomaly_helper(self):
        assert is_price_anomaly(D("100"), D("10"))
        assert is_price_anomaly(D("1"), D("10"))
        assert not is_price_anomaly(D("99.99"), D("10"))
        with pytest.raises(PricingError):
            is_price_anomaly(D("1"), D("0"))

    @pytest.mark.parametrize(
        "candidate,status,reasons",
        [
            (D("219.90"), DecisionStatus.OK, ()),
            (D("199.90"), DecisionStatus.REVIEW, (Reason.BELOW_TARGET_MARGIN,)),
            (D("180"), DecisionStatus.BLOCKED, (Reason.BELOW_HARD_FLOOR,)),
            (D("160"), DecisionStatus.BLOCKED, (Reason.BELOW_HARD_FLOOR, Reason.BELOW_ORDER_FLOOR_CHF)),
        ],
    )
    def test_candidate_price_promotion(self, candidate, status, reasons):
        d = decide_price(D("140"), EFF, candidate_price=candidate)
        assert d.status is status
        for r in reasons:
            assert d.has(r)
        assert d.evaluated_price == candidate

    def test_candidate_must_be_positive(self):
        with pytest.raises(PricingError):
            decide_price(D("140"), EFF, candidate_price=D("0"))
        with pytest.raises(PricingError):
            decide_price(D("140"), EFF, previous_cost=D("0"))

    def test_stale_offer_not_restock_eligible_but_price_ok(self):
        d = decide_price(D("140"), EFF, offer_stale=True)
        assert d.status is DecisionStatus.OK
        assert d.has(Reason.STALE_OFFER)
        assert d.restock_eligible is False

    def test_small_product_addon_rule(self):
        d = decide_price(D("3.50"), EFF)
        assert d.small_product
        assert d.has(Reason.SMALL_PRODUCT_ADDON)
        assert d.recommended_price == D("4.90")
        assert d.contribution_pct >= D("0.20")

    def test_small_product_override_and_disabled_rule(self):
        d = decide_price(D("3.50"), EFF, small_product=False)
        assert not d.small_product
        assert d.has(Reason.ORDER_FLOOR_CHF_BINDING)
        assert d.contribution_chf >= D("8")
        no_rule = params(small_product_max_cost=None)
        assert not decide_price(D("3.50"), no_rule).small_product
        assert decide_price(D("50"), EFF, small_product=True).small_product

    def test_order_floor_binds_for_mid_price_products(self):
        d = decide_price(D("20"), EFF)
        assert d.has(Reason.ORDER_FLOOR_CHF_BINDING)
        assert d.floor_price == D("40.98")
        assert d.profitable_price == D("41.44")
        assert d.recommended_price == D("41.90")
        assert d.contribution_chf >= D("8")

    def test_small_candidate_checked_on_pct_only(self):
        d = decide_price(D("3.50"), EFF, candidate_price=D("4.50"))
        assert d.status is DecisionStatus.REVIEW
        assert not d.has(Reason.BELOW_ORDER_FLOOR_CHF)
        d2 = decide_price(D("3.50"), EFF, candidate_price=D("3.90"))
        assert d2.status is DecisionStatus.BLOCKED

    def test_denominator_failure_is_blocked_not_raised(self):
        d = decide_price(D("100"), params(target_margin=D("0.98")))
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.DENOMINATOR_NOT_POSITIVE)
        assert d.recommended_price is None

    def test_status_precedence_blocked_over_draft(self):
        d = decide_price(D("140"), EFF, unknown_fields=["frais"], previous_cost=D("10"), market_ref=D("100"))
        assert d.status is DecisionStatus.BLOCKED
        assert {Reason.UNKNOWN_FIELDS.value, Reason.PRICE_ANOMALY.value, Reason.ABOVE_MARKET.value} <= set(d.reasons)

    def test_draft_over_review(self):
        d = decide_price(D("140"), EFF, unknown_fields=["frais"], market_ref=D("100"))
        assert d.status is DecisionStatus.DRAFT

    def test_inputs_hash_traceability(self):
        a = decide_price(D("140"), EFF, market_ref=D("200"))
        b = decide_price(D("140.00"), EFF, market_ref=D("200.0"))
        c = decide_price(D("140"), EFF, market_ref=D("201"))
        d = decide_price(D("140"), EFF.replace(rules_version="test-v2"), market_ref=D("200"))
        e = decide_price(D("140"), EFF, unknown_fields=["b", "a"])
        f = decide_price(D("140"), EFF, unknown_fields=["a", "b", "a"])
        assert a.inputs_hash == b.inputs_hash
        assert len({a.inputs_hash, c.inputs_hash, d.inputs_hash}) == 3
        assert e.inputs_hash == f.inputs_hash
        assert d.rules_version == "test-v2"

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            decide_price(140.0, EFF)  # type: ignore[arg-type]

    def test_independent_of_global_decimal_context(self):
        import decimal

        with decimal.localcontext() as ctx:
            ctx.prec = 6
            ctx.rounding = decimal.ROUND_DOWN
            d = decide_price(D("140"), EFF)
        assert d.floor_price == D("208.79")
        assert d.recommended_price == D("209.90")

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_property_recommended_meets_target_and_floors(self, p):
        rng = random.Random(4)
        for _ in range(1500):
            cost = D(rng.randint(1, 300_000)) / 100
            d = decide_price(cost, p)
            assert d.status is DecisionStatus.OK
            assert d.recommended_price >= d.profitable_price
            assert d.contribution_pct >= p.target_margin
            assert d.contribution_pct >= p.hard_floor_margin
            if not d.small_product:
                assert d.contribution_chf >= p.hard_floor_chf_per_order
            assert round_up_retail(d.recommended_price, tiers=DEFAULT_ROUNDING_TIERS) == d.recommended_price


# ================================================================ offres


class TestEvaluateOffer:
    def kwargs(self, **kw):
        base = dict(now=NOW, inbound_freight_alloc=D("0"))
        base.update(kw)
        return base

    def test_complete_domestic_offer_ok(self):
        d = evaluate_offer(offer(), EFF, **self.kwargs())
        assert d.status is DecisionStatus.OK
        assert d.recommended_price == D("209.90")
        assert d.landed_cost == D("140.00")
        ref = decide_price(D("140"), EFF)
        assert d.recommended_price == ref.recommended_price
        assert d.inputs_hash != ref.inputs_hash

    def test_gtin_absent_draft(self):
        d = evaluate_offer(offer(gtin=None), EFF, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        assert "gtin" in d.notes[0]

    @pytest.mark.parametrize("lang", [None, "UNKNOWN", ""])
    def test_unknown_language_draft(self, lang):
        d = evaluate_offer(offer(language=lang), EFF, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        assert any("language" in n for n in d.notes)

    @pytest.mark.parametrize("lang", ["JP", "EN", "de"])
    def test_other_language_blocked(self, lang):
        d = evaluate_offer(offer(language=lang), EFF, **self.kwargs())
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.LANGUAGE_MISMATCH)

    def test_lowercase_fr_accepted(self):
        assert evaluate_offer(offer(language="fr"), EFF, **self.kwargs()).status is DecisionStatus.OK

    def test_expected_language_parameter(self):
        d = evaluate_offer(offer(language="JP"), EFF, **self.kwargs(expected_language="jp"))
        assert d.status is DecisionStatus.OK

    def test_zero_price_blocked(self):
        d = evaluate_offer(offer(price=D("0")), EFF, **self.kwargs())
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.ZERO_PRICE)
        assert d.recommended_price is None

    def test_missing_price_draft_without_numbers(self):
        d = evaluate_offer(offer(price=None), EFF, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        assert d.recommended_price is None

    @pytest.mark.parametrize(
        "field",
        [
            "units_per_pack",
            "currency",
            "price_includes_vat",
            "vat_rate",
            "extension",
            "format",
            "content",
            "sealed",
            "ship_from_country",
        ],
    )
    def test_any_missing_critical_field_is_draft(self, field):
        d = evaluate_offer(offer(**{field: None}), EFF, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        assert field in offer_unknown_fields(offer(**{field: None}))

    def test_eur_without_fx_is_draft(self):
        o = offer(currency="EUR", price=D("130"), ship_from_country="FR")
        d = evaluate_offer(o, EFF, **self.kwargs(customs_and_fees=D("0")))
        assert d.status is DecisionStatus.DRAFT
        assert any("fx_rate" in n for n in d.notes)
        assert d.recommended_price is None

    def test_eur_with_fx_and_import_costs(self):
        o = offer(currency="EUR", price=D("130"), ship_from_country="FR")
        d = evaluate_offer(
            o,
            NREG,
            **self.kwargs(
                fx_rate_to_chf=D("0.94"),
                fx_source="FICTIF_BNS",
                fx_date=date(2026, 10, 4),
                inbound_freight_alloc=D("4"),
                customs_and_fees=D("2"),
                import_vat=D("10.39"),
            ),
        )
        assert d.status is DecisionStatus.OK
        assert d.landed_cost == D("138.59")  # 122.20 + 4 + 2 + 10.39

    def test_foreign_offer_requires_customs_and_import_vat_when_not_registered(self):
        o = offer(ship_from_country="FR")
        d = evaluate_offer(o, NREG, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        joined = " ".join(d.notes)
        assert "customs_and_fees" in joined and "import_vat" in joined
        d_eff = evaluate_offer(o, EFF, **self.kwargs(customs_and_fees=D("1")))
        assert d_eff.status is DecisionStatus.OK

    def test_missing_freight_is_draft(self):
        d = evaluate_offer(offer(), EFF, now=NOW)
        assert d.status is DecisionStatus.DRAFT
        assert any("inbound_freight_alloc" in n for n in d.notes)
        assert d.recommended_price is not None  # indicatif seulement

    def test_stale_source(self):
        d = evaluate_offer(offer(source_ts=NOW - timedelta(hours=25)), EFF, **self.kwargs())
        assert d.status is DecisionStatus.OK
        assert d.restock_eligible is False
        assert d.has(Reason.STALE_OFFER)
        fresh = evaluate_offer(offer(source_ts=NOW - timedelta(hours=24)), EFF, **self.kwargs())
        assert fresh.restock_eligible is True

    def test_stale_and_incomplete(self):
        d = evaluate_offer(offer(price=None, source_ts=NOW - timedelta(days=3)), EFF, **self.kwargs())
        assert d.status is DecisionStatus.DRAFT
        assert d.restock_eligible is False

    def test_price_x10_versus_previous_cost(self):
        d = evaluate_offer(offer(price=D("1400")), EFF, **self.kwargs(previous_cost=D("140")))
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.PRICE_ANOMALY)

    def test_tier_discount_and_carton(self):
        o = offer(price=D("840"), units_per_pack=6, tier_discounts=(TierDiscount(min_qty=12, discount_pct=D("0.10")),))
        assert evaluate_offer(o, EFF, **self.kwargs()).landed_cost == D("140.00")
        assert evaluate_offer(o, EFF, **self.kwargs(order_qty=12)).landed_cost == D("126.00")

    def test_blocked_and_unknown_combined(self):
        d = evaluate_offer(offer(language="JP", gtin=None), EFF, **self.kwargs())
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.UNKNOWN_FIELDS) and d.has(Reason.LANGUAGE_MISMATCH)

    def test_zero_price_and_foreign_language_both_reported(self):
        d = evaluate_offer(offer(price=D("0"), language="EN"), EFF, **self.kwargs())
        assert d.status is DecisionStatus.BLOCKED
        assert d.has(Reason.ZERO_PRICE) and d.has(Reason.LANGUAGE_MISMATCH)
        assert len(d.notes) == 2
        assert any("EN" in n for n in d.notes) and any("quarantaine" in n for n in d.notes)

    def test_empty_expected_language_rejected(self):
        with pytest.raises(PricingError):
            evaluate_offer(offer(), EFF, **self.kwargs(expected_language=" "))

    def test_blocked_without_cost(self):
        d = evaluate_offer(offer(language="JP", price=None), EFF, **self.kwargs())
        assert d.status is DecisionStatus.BLOCKED
        assert d.recommended_price is None

    def test_landed_input_from_offer(self):
        inp = landed_input_from_offer(
            offer(currency="EUR"),
            vat_mode=VatMode.EFFECTIVE,
            fx_rate_to_chf=D("0.94"),
            fx_source="FICTIF",
            fx_date=date(2026, 10, 3),
        )
        assert inp.fx_rate_to_chf == D("0.94")
        assert inp.supplier_vat_country == "CH"
        chf = landed_input_from_offer(offer(), vat_mode=VatMode.EFFECTIVE)
        assert chf.fx_rate_to_chf == D("1") and chf.fx_source == "CHF" and chf.fx_date == NOW.date()
        with pytest.raises(IncompleteDataError) as exc:
            landed_input_from_offer(offer(price=None, currency="EUR"), vat_mode=VatMode.EFFECTIVE)
        assert set(exc.value.fields) == {"price", "fx_rate"}


# ================================================================== panier


def line(sku="ETB", qty=1, price="199.90", cost="140") -> BasketLine:
    return BasketLine(sku=sku, qty=qty, unit_price_ttc=D(price), unit_cost=D(cost))


class TestBasket:
    def test_single_line_matches_unit_contribution(self):
        r = basket_contribution([line()], EFF, shipping_cost_actual=D("3"))
        assert r.net_revenue == D("184.92")
        assert r.payment_fees == D("5.30")
        assert r.contribution_chf == D("30.62")
        assert r.contribution_pct == D("0.1656")
        assert r.status is DecisionStatus.OK
        assert Reason.BELOW_TARGET_MARGIN.value in r.reasons

    def test_fixed_fees_charged_once_per_order(self):
        a = basket_contribution([line("A", price="209.90")], EFF, shipping_cost_actual=D("3"))
        b = basket_contribution([line("B", price="41.90", cost="20")], EFF, shipping_cost_actual=D("3"))
        both = basket_contribution(
            [line("A", price="209.90"), line("B", price="41.90", cost="20")], EFF, shipping_cost_actual=D("3")
        )
        expected_payment = ((D("209.90") + D("41.90")) * D("0.025") + D("0.30")).quantize(D("0.01"))
        assert both.payment_fees == expected_payment
        saved = both.contribution_chf - (a.contribution_chf + b.contribution_chf)
        assert abs(saved - D("9.30")) <= D("0.03")

    def test_multi_product_lines_sum_to_totals(self):
        lines = [line("A", 2, "209.90", "140"), line("B", 3, "41.90", "20"), line("C", 5, "4.90", "3.50")]
        r = basket_contribution(lines, EFF, D("7.90"), Discount(kind="PERCENT", value=D("0.10"), code="FICTIF10"))
        assert sum(ln.net_revenue for ln in r.lines) == r.net_revenue
        assert sum(ln.discount_ttc for ln in r.lines) == r.discount_ttc
        assert sum(ln.product_cost for ln in r.lines) == r.product_cost
        assert sum(ln.contribution_chf for ln in r.lines) == r.contribution_chf
        assert r.goods_ttc == D("570.00")
        assert r.discount_ttc == D("57.00")
        assert r.total_paid_ttc == D("520.90")

    def test_free_shipping_uses_actual_cost(self):
        default = basket_contribution([line(price="209.90")], EFF)
        free = basket_contribution([line(price="209.90")], EFF, D("0"), shipping_cost_actual=D("9"))
        assert Reason.SHIPPING_COST_ASSUMED.value in default.reasons
        assert Reason.SHIPPING_COST_ASSUMED.value not in free.reasons
        assert default.contribution_chf - free.contribution_chf == D("6.00")
        assert free.shipping_gap == D("-9.00")

    def test_charged_shipping_assumed_to_cover_postage(self):
        r = basket_contribution([line(price="209.90")], EFF, D("7.90"))
        assert r.shipping_charged_ttc == D("7.90")
        assert r.shipping_gap == D("-3.00")
        assert r.logistics_cost == D("10.31")

    def test_free_shipping_blocks_small_basket(self):
        r = basket_contribution([line(price="41.90", cost="20")], EFF, D("0"), shipping_cost_actual=D("9.50"))
        assert r.status is DecisionStatus.BLOCKED
        assert Reason.BELOW_ORDER_FLOOR_CHF.value in r.reasons

    @pytest.mark.parametrize(
        "discount,expected",
        [
            (D("20"), D("20.00")),
            (Discount(kind="AMOUNT", value=D("15.555")), D("15.56")),
            (Discount(kind="PERCENT", value=D("0.05")), D("10.50")),
            (None, D("0.00")),
        ],
    )
    def test_discount_forms(self, discount, expected):
        r = basket_contribution([line(price="209.90")], EFF, D("0"), discount, shipping_cost_actual=D("3"))
        assert r.discount_ttc == expected

    def test_unprofitable_promo_blocked(self):
        r = basket_contribution(
            [line(price="209.90")], EFF, D("0"), Discount(kind="PERCENT", value=D("0.20")), shipping_cost_actual=D("3")
        )
        assert r.status is DecisionStatus.BLOCKED
        assert Reason.BELOW_HARD_FLOOR.value in r.reasons
        assert not r.is_allowed

    def test_discount_capped(self):
        r = basket_contribution([line(price="10.90", cost="5")], EFF, D("7.90"), D("50"), shipping_cost_actual=D("8"))
        assert Reason.DISCOUNT_CAPPED.value in r.reasons
        assert r.discount_ttc == D("10.90")
        assert r.total_paid_ttc == D("7.90")
        assert r.status is DecisionStatus.BLOCKED

    def test_full_discount_without_shipping(self):
        r = basket_contribution(
            [line(price="10.90", cost="5")],
            EFF,
            D("0"),
            Discount(kind="PERCENT", value=D("1")),
            shipping_cost_actual=D("8"),
        )
        assert r.status is DecisionStatus.BLOCKED
        assert r.contribution_pct is None
        assert r.payment_fees == D("0.00")
        assert Reason.NON_POSITIVE_NET_REVENUE.value in r.reasons

    def test_small_product_alone_blocked_but_ok_with_main_product(self):
        alone = basket_contribution([line("BOOSTER", 1, "4.90", "3.50")], EFF, D("0"), shipping_cost_actual=D("3"))
        assert alone.status is DecisionStatus.BLOCKED
        mixed = basket_contribution(
            [line("ETB", 1, "209.90", "140"), line("BOOSTER", 2, "4.90", "3.50")],
            EFF,
            D("0"),
            shipping_cost_actual=D("3"),
        )
        assert mixed.status is DecisionStatus.OK
        assert mixed.contribution_chf > D("8")

    def test_not_registered_basket_has_no_vat(self):
        r = basket_contribution([line(price="209.90", cost="151.34")], NREG, shipping_cost_actual=D("3"))
        assert r.vat == D("0.00")
        assert r.net_revenue == D("209.90")

    def test_errors(self):
        with pytest.raises(PricingError):
            basket_contribution([], EFF)
        with pytest.raises(PricingError):
            basket_contribution([line("A"), line("A")], EFF)
        with pytest.raises(PricingError):
            basket_contribution([line()], EFF, D("-1"))
        with pytest.raises(PricingError):
            basket_contribution([line()], EFF, shipping_cost_actual=D("-1"))
        with pytest.raises(ValidationError):
            line(qty=0)
        with pytest.raises(ValidationError):
            line(price="0")

    def test_hash_and_version(self):
        a = basket_contribution([line()], EFF, D("0"), D("5"))
        b = basket_contribution([line()], EFF, D("0.00"), Discount(kind="AMOUNT", value=D("5.00")))
        c = basket_contribution([line()], EFF, D("0"), D("6"))
        assert a.inputs_hash == b.inputs_hash != c.inputs_hash
        assert a.rules_version == "test-v1"


# ======================================================== planchers durs


class TestFloorViolations:
    @pytest.mark.parametrize(
        "chf,pct,small,expected",
        [
            (D("30.62"), D("0.1656"), False, []),
            (D("8.00"), D("0.12"), False, []),
            (D("7.99"), D("0.20"), False, [Reason.BELOW_ORDER_FLOOR_CHF]),
            (D("20"), D("0.1199"), False, [Reason.BELOW_HARD_FLOOR]),
            (D("2"), D("0.05"), False, [Reason.BELOW_HARD_FLOOR, Reason.BELOW_ORDER_FLOOR_CHF]),
            (D("0.91"), D("0.2009"), True, []),
            (D("0.10"), D("0.05"), True, [Reason.BELOW_HARD_FLOOR]),
        ],
    )
    def test_hard_floors(self, chf, pct, small, expected):
        assert floor_violations(chf, pct, EFF, small_product=small) == expected

    def test_float_rejected(self):
        with pytest.raises(TypeError):
            floor_violations(8.0, D("0.2"), EFF)  # type: ignore[arg-type]

    def test_consistent_with_decide_price_and_basket(self):
        for candidate in (D("160"), D("180"), D("199.90"), D("219.90")):
            d = decide_price(D("140"), EFF, candidate_price=candidate)
            v = floor_violations(d.contribution_chf, d.contribution_pct, EFF)
            assert (d.status is DecisionStatus.BLOCKED) == bool(v)
            b = basket_contribution([line(price=str(candidate))], EFF, shipping_cost_actual=D("3"))
            assert b.contribution_chf == d.contribution_chf
            assert (b.status is DecisionStatus.BLOCKED) == bool(
                floor_violations(b.contribution_chf, b.contribution_pct, EFF)
            )


# ================================================= propriétés du panier


class TestBasketProperties:
    def random_lines(self, rng: random.Random, n: int) -> list[BasketLine]:
        lines = []
        for i in range(n):
            cost = D(rng.randint(100, 30_000)) / 100
            price = round_up_retail(floor_price_exact(cost, EFF, per_order_costs=False) + D(rng.randint(0, 3000)) / 100)
            lines.append(BasketLine(sku=f"FICTIF-{i}", qty=rng.randint(1, 4), unit_price_ttc=price, unit_cost=cost))
        return lines

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_lines_always_sum_to_order_totals(self, p):
        rng = random.Random(77)
        for _ in range(300):
            lines = self.random_lines(rng, rng.randint(1, 6))
            disc = Discount(kind="PERCENT", value=D(rng.randint(0, 30)) / 100) if rng.random() < 0.5 else None
            ship = D(rng.choice(["0", "7.90", "9.50"]))
            r = basket_contribution(lines, p, ship, disc, shipping_cost_actual=D(rng.randint(300, 1200)) / 100)
            assert sum(ln.net_revenue for ln in r.lines) == r.net_revenue
            assert sum(ln.discount_ttc for ln in r.lines) == r.discount_ttc
            assert sum(ln.product_cost for ln in r.lines) == r.product_cost
            assert (
                sum(ln.allocated_order_costs for ln in r.lines)
                == r.payment_fees + r.logistics_cost + r.after_sales + r.acquisition
            )
            assert sum(ln.contribution_chf for ln in r.lines) == r.contribution_chf
            assert r.vat + r.net_revenue == r.total_paid_ttc
            assert r.total_paid_ttc == r.goods_ttc - r.discount_ttc + r.shipping_charged_ttc
            # additivité stricte des montants affichés (aucun centime inexpliqué)
            assert r.contribution_chf == (
                r.net_revenue - r.product_cost - r.payment_fees - r.logistics_cost - r.after_sales - r.acquisition
            )

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_additivity_with_assumed_shipping_cost(self, p):
        """Coût logistique supposé (L + port HT, non arrondi) : l'additivité tient quand même."""
        rng = random.Random(3)
        for _ in range(300):
            lines = self.random_lines(rng, rng.randint(1, 4))
            ship = D(rng.randint(0, 1500)) / 100
            r = basket_contribution(lines, p, ship)
            assert Reason.SHIPPING_COST_ASSUMED.value in r.reasons
            parts = r.net_revenue - r.product_cost - r.payment_fees - r.logistics_cost - r.after_sales - r.acquisition
            assert r.contribution_chf == parts
            assert sum(ln.allocated_order_costs for ln in r.lines) == (
                r.payment_fees + r.logistics_cost + r.after_sales + r.acquisition
            )

    @pytest.mark.parametrize("p", [EFF, NREG])
    def test_unit_contribution_is_additive(self, p):
        rng = random.Random(8)
        for _ in range(500):
            cost = D(rng.randint(100, 50_000)) / 100
            price = D(rng.randint(100, 90_000)) / 100
            b = contribution_breakdown(price, cost, p)
            assert b.contribution_chf == b.net_revenue - b.product_cost - b.payment_fees - b.per_order_costs
            assert b.vat + b.net_revenue == b.price_ttc

    def test_fixed_costs_counted_once_whatever_the_number_of_lines(self):
        """Fusionner n commandes d'une ligne en un panier économise (n − 1) × (b + R + A + logistique)."""
        rng = random.Random(5)
        per_order = EFF.payment_fixed + EFF.after_sales_provision + EFF.acquisition_cost + D("3")
        for _ in range(200):
            lines = self.random_lines(rng, rng.randint(2, 6))
            merged = basket_contribution(lines, EFF, D("0"), shipping_cost_actual=D("3"))
            separate = sum(
                (basket_contribution([ln], EFF, D("0"), shipping_cost_actual=D("3")).contribution_chf for ln in lines),
                D("0"),
            )
            saved = merged.contribution_chf - separate
            expected = per_order * (len(lines) - 1)
            assert abs(saved - expected) <= D("0.01") * (2 * len(lines) + 1), (saved, expected)

    def test_discount_monotonic(self):
        """Plus de remise => jamais plus de contribution (même moteur pour toutes les promos)."""
        lines = [line("A", 1, "209.90", "140"), line("B", 2, "41.90", "20")]
        prev = None
        for pct in range(0, 41, 2):
            r = basket_contribution(
                lines, EFF, D("0"), Discount(kind="PERCENT", value=D(pct) / 100), shipping_cost_actual=D("3")
            )
            if prev is not None:
                assert r.contribution_chf <= prev
            prev = r.contribution_chf

    def test_status_matches_hard_floors(self):
        rng = random.Random(11)
        for _ in range(300):
            lines = self.random_lines(rng, rng.randint(1, 3))
            r = basket_contribution(
                lines,
                EFF,
                D("0"),
                Discount(kind="PERCENT", value=D(rng.randint(0, 50)) / 100),
                shipping_cost_actual=D("8"),
            )
            if r.contribution_pct is None:
                assert r.status is DecisionStatus.BLOCKED
                continue
            violated = bool(floor_violations(r.contribution_chf, r.contribution_pct, EFF))
            assert (r.status is DecisionStatus.BLOCKED) == violated
