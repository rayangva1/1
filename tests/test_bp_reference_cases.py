"""Cas de référence chiffrés du business plan (BP §4 « Exemple fictif et reproductible »).

Ces valeurs sont des HYPOTHÈSES FICTIVES du BP, pas des devis fournisseur.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from pokeshop.models import DecisionStatus, LandedCostInput, Reason, VatMode
from pokeshop.pricing import (
    contribution,
    contribution_breakdown,
    decide_price,
    floor_price,
    floor_price_exact,
    landed_unit_cost,
    round_up_retail,
)
from pokeshop.rules import load_all_profiles, load_rules


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
