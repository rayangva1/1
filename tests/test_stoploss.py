"""Tests du stop-loss multi-niveaux : chaque niveau aux bornes exactes, verrou global, réarmement.

Toutes les données sont FICTIVES (préfixe FICTIF_) ; aucun montant n'est un devis.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from pokeshop.costs import HistoricalCostLedger
from pokeshop.mandate import load_mandate
from pokeshop.models import AvailabilityStatus, CostLot, ReorderCandidate, SupplierOffer
from pokeshop.pricing import decide_price, floor_violations
from pokeshop.rules import load_rules
from pokeshop.stock import propose_reorder
from pokeshop.stoploss import (
    ACTION_LABELS_FR,
    DEFAULT_STOPLOSS_PATH,
    LEVEL_LABELS_FR,
    OWNER_TOKEN_SHA256_ENV_VAR,
    STOPLOSS_ENV_VAR,
    AdSpend,
    AttributedOrder,
    BalanceItem,
    CapitalBaseline,
    CapitalMovement,
    ExtensionExposure,
    GlobalLatch,
    NetWorthSnapshot,
    ProductMargin,
    RearmRefusedError,
    StockValuationLine,
    StopLossAction,
    StopLossEngine,
    StopLossError,
    StopLossLevel,
    StopLossState,
    StopLossStatus,
    Trigger,
    ValidationWindow,
    capital_total,
    consistency_errors,
    effective_capital,
    evaluate_levels,
    format_chf,
    hash_owner_token,
    load_stoploss_config,
    net_worth,
    parse_stoploss_config,
    prudent_stock_value,
    render_report,
    validate_stoploss_data,
)
from pokeshop.treasury import CASH_STOPLOSS_RESERVE
from pydantic import ValidationError

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 12, 15, 18, 0, tzinfo=TZ)
TODAY = NOW.date()
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
OWNER_HASH = hash_owner_token(OWNER_TOKEN)
CONFIG = load_stoploss_config()


def cfg_data() -> dict:
    return yaml.safe_load(DEFAULT_STOPLOSS_PATH.read_text(encoding="utf-8"))


def worth(cash: str = "8000", *, stock=(), receivables=(), debts=(), as_of: datetime = NOW) -> NetWorthSnapshot:
    return NetWorthSnapshot(
        as_of=as_of, cash_chf=D(cash), stock=tuple(stock), receivables=tuple(receivables), debts=tuple(debts)
    )


def capital(*amounts: str, at: datetime | None = None) -> tuple[CapitalMovement, ...]:
    at = at or NOW - timedelta(days=30)
    return tuple(
        CapitalMovement(movement_id=f"FICTIF_APPORT_{i}", at=at, kind="CONTRIBUTION", amount=D(a))
        for i, a in enumerate(amounts)
    )


def state(**kw) -> StopLossState:
    base = dict(
        as_of=NOW,
        stock_budget_chf=D("3000"),
        cash_available_chf=D("5000"),
        capital_movements=capital("8000"),
        net_worth=worth("8000"),
        ads_daily_cap_chf=D("33"),
    )
    base.update(kw)
    return StopLossState(**base)


def run(**kw) -> list[Trigger]:
    return evaluate_levels(state(**kw), NOW, CONFIG)


def of_level(triggers: list[Trigger], level: StopLossLevel) -> list[Trigger]:
    return [t for t in triggers if t.level is level]


def engine(**kw) -> StopLossEngine:
    return StopLossEngine(CONFIG, owner_token_sha256=kw.pop("owner_token_sha256", OWNER_HASH), **kw)


# --------------------------------------------------------------------------- configuration


def test_shipped_config_loads_with_expected_thresholds() -> None:
    c = CONFIG
    assert c.stoploss_version == "stoploss-v1-2026-10-04"
    assert "hypothèses" in c.status
    assert c.product.min_contribution_pct == D("0.12")
    assert c.product.min_contribution_chf_per_order == D("8.00")
    assert c.extension.max_share_of_stock_budget == D("0.25")
    assert c.extension.max_days_without_sale == 45
    assert c.ads.window_days == 7
    assert c.cash.reserve_chf == D("1600")
    assert c.global_.max_loss_share_of_capital == D("0.20")
    assert c.global_.autonomy_level_on_freeze == 1
    assert c.time.validation_days == 60 and c.time.min_paid_orders == 30
    assert c.time.min_sell_through_share_at_cost == D("0.50")
    assert c.tz == ZoneInfo("Europe/Zurich")
    assert len(c.content_sha256) == 64
    assert c.effective_date == date(2026, 10, 4)


def test_one_rule_one_value_across_repo() -> None:
    rules = load_rules()
    template = load_mandate(expected_fingerprint=None)
    assert (
        consistency_errors(
            CONFIG,
            pricing=rules.pricing,
            stock=rules.stock,
            treasury_reserve=CASH_STOPLOSS_RESERVE,
            mandate_cash_reserve=template.cash_reserve_chf,
            mandate_extension_share=template.extension_max_share,
        )
        == []
    )


def test_consistency_detects_each_divergence() -> None:
    rules = load_rules()
    errors = consistency_errors(
        CONFIG,
        pricing=rules.pricing.replace(hard_floor_margin=D("0.10"), hard_floor_chf_per_order=D("7")),
        stock=rules.stock.replace(extension_budget_cap=D("0.30")),
        treasury_reserve=D("1500"),
        mandate_cash_reserve=D("1700"),
        mandate_extension_share=D("0.20"),
    )
    assert len(errors) == 6


def test_env_var_overrides_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = cfg_data()
    data["stoploss_version"] = "stoploss-test"
    path = tmp_path / "sl.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv(STOPLOSS_ENV_VAR, str(path))
    assert load_stoploss_config().stoploss_version == "stoploss-test"


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d.update(inconnu=1), "clés inconnues"),
        (lambda d: d.pop("cash"), "cash : section manquante"),
        (lambda d: d["product"].update(min_contribution_pct=0.12), "float interdit"),
        (lambda d: d["extension"].update(max_days_without_sale=True), "extension.max_days_without_sale"),
        (lambda d: d["extension"].update(max_days_without_sale="45"), "extension.max_days_without_sale"),
        (lambda d: d["global"].update(max_loss_share_of_capital="1.5"), "global.max_loss_share_of_capital"),
        (lambda d: d["global"].update(autonomy_level_on_freeze=0), "global.autonomy_level_on_freeze"),
        (lambda d: d["ads"].update(window_days=0), "ads.window_days"),
        (lambda d: d["ads"].update(extra="1"), "ads.extra"),
        (lambda d: d["cash"].update(reserve_chf="abc"), "cash.reserve_chf"),
        (lambda d: d["cash"].update(reserve_chf="-1"), "cash.reserve_chf"),
        (lambda d: d["time"].update(min_sell_through_share_at_cost="NaN"), "time.min_sell_through_share_at_cost"),
        (lambda d: d.update(timezone="Mars/Olympus"), "timezone"),
        (lambda d: d.update(timezone=3), "timezone"),
        (lambda d: d.update(stoploss_version="v 1"), "stoploss_version"),
        (lambda d: d.update(status=""), "status"),
        (lambda d: d.update(source=3), "source"),
        (lambda d: d.update(effective_date="04.10.2026"), "effective_date"),
        (lambda d: d.update(effective_date=3), "effective_date"),
        (lambda d: d.update(state_max_age_hours=True), "state_max_age_hours"),
        (lambda d: d.update(state_max_age_hours=0), "state_max_age_hours"),
    ],
)
def test_invalid_documents_are_rejected(mutate, fragment: str) -> None:
    data = cfg_data()
    mutate(data)
    errors = validate_stoploss_data(data)
    assert any(fragment in e for e in errors), errors
    with pytest.raises(StopLossError):
        parse_stoploss_config(data)


def test_non_mapping_and_unreadable_files(tmp_path: Path) -> None:
    assert validate_stoploss_data([1]) == ["document de stop-loss : mapping YAML attendu"]
    with pytest.raises(StopLossError, match="illisible"):
        load_stoploss_config(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [", encoding="utf-8")
    with pytest.raises(StopLossError, match="YAML invalide"):
        load_stoploss_config(bad)
    lst = tmp_path / "list.yaml"
    lst.write_text("- 1\n", encoding="utf-8")
    with pytest.raises(StopLossError, match="mapping"):
        load_stoploss_config(lst)


def test_effective_date_as_yaml_date_is_accepted() -> None:
    data = cfg_data()
    data["effective_date"] = date(2026, 10, 4)
    assert parse_stoploss_config(data).effective_date == date(2026, 10, 4)


def test_config_replace_keeps_alias() -> None:
    assert CONFIG.replace(state_max_age_hours=12).global_ == CONFIG.global_


# --------------------------------------------------------------------------------- produit


def pm(pct: str, chf: str, **kw) -> ProductMargin:
    return ProductMargin(
        product_key=kw.pop("product_key", "FICTIF_DISPLAY"), contribution_pct=D(pct), contribution_chf=D(chf), **kw
    )


def test_product_exact_floor_is_compliant() -> None:
    assert of_level(run(products=(pm("0.12", "8.00"),)), StopLossLevel.PRODUCT) == []


def test_product_pct_just_below_floor_blocks_sale() -> None:
    (t,) = of_level(run(products=(pm("0.1199", "30"),)), StopLossLevel.PRODUCT)
    assert t.action is StopLossAction.BLOCK_SALE and t.metric == "contribution_pct"
    assert t.value == D("0.1199") and t.threshold == D("0.12") and t.scope == "FICTIF_DISPLAY"
    assert "vente bloquée" in t.reason


def test_product_chf_just_below_floor_blocks_sale() -> None:
    (t,) = of_level(run(products=(pm("0.20", "7.99"),)), StopLossLevel.PRODUCT)
    assert t.metric == "contribution_chf_par_commande" and t.value == D("7.99") and t.threshold == D("8.00")


def test_product_both_floors_violated_gives_two_triggers() -> None:
    triggers = of_level(run(products=(pm("0.05", "2", context="PROMO"),)), StopLossLevel.PRODUCT)
    assert {t.metric for t in triggers} == {"contribution_pct", "contribution_chf_par_commande"}
    assert all("promotion bloquée" in t.reason for t in triggers)


def test_small_product_checked_in_pct_only() -> None:
    assert of_level(run(products=(pm("0.30", "2", small_product=True),)), StopLossLevel.PRODUCT) == []
    (t,) = of_level(run(products=(pm("0.11", "2", small_product=True),)), StopLossLevel.PRODUCT)
    assert t.metric == "contribution_pct"


@pytest.mark.parametrize("pct", ["0.1199", "0.12", "0.1201", "0.05", "0.30"])
@pytest.mark.parametrize("chf", ["7.99", "8.00", "8.01", "0", "-3"])
@pytest.mark.parametrize("small", [False, True])
def test_product_level_matches_pricing_floor_violations(pct: str, chf: str, small: bool) -> None:
    params = load_rules().pricing
    expected = floor_violations(D(chf), D(pct), params, small_product=small)
    got = of_level(run(products=(pm(pct, chf, small_product=small),)), StopLossLevel.PRODUCT)
    assert len(got) == len(expected)


def test_product_margin_from_engine_decision() -> None:
    params = load_rules().pricing
    decision = decide_price(D("140"), params, candidate_price=D("199.90"))
    margin = ProductMargin.from_decision("FICTIF_DISPLAY", decision, extension="FICTIF_EXT")
    assert margin.contribution_chf == D("30.62") and margin.contribution_pct == D("0.1656")
    assert of_level(run(products=(margin,)), StopLossLevel.PRODUCT) == []


def test_product_margin_requires_computed_contribution() -> None:
    params = load_rules().pricing
    draft = decide_price(D("140"), params, unknown_fields=["language"])
    with pytest.raises(StopLossError, match="sans contribution"):
        ProductMargin.from_decision("FICTIF_X", draft.replace(contribution_chf=None, contribution_pct=None))


# ------------------------------------------------------------------------------- extension


def ext(**kw) -> ExtensionExposure:
    base = dict(extension="FICTIF_EXT_A", stock_value_at_cost=D("300"), last_sale_at=NOW - timedelta(days=1))
    base.update(kw)
    return ExtensionExposure(**base)


def test_extension_exposure_exactly_25_percent_is_compliant() -> None:
    assert of_level(run(extensions=(ext(stock_value_at_cost=D("750")),)), StopLossLevel.EXTENSION) == []


def test_extension_exposure_above_25_percent_stops_reorder_and_proposes_markdown() -> None:
    triggers = of_level(run(extensions=(ext(stock_value_at_cost=D("700"), on_order_value=D("50.01")),)),
                        StopLossLevel.EXTENSION)  # fmt: skip
    assert [t.action for t in triggers] == [StopLossAction.NO_REORDER, StopLossAction.PROPOSE_MARKDOWN]
    assert all(t.metric == "exposition_chf" and t.value == D("750.01") and t.threshold == D("750.00") for t in triggers)


def test_extension_cap_override_documented_by_owner() -> None:
    assert of_level(run(extensions=(ext(stock_value_at_cost=D("900"), cap_override=D("0.30")),)),
                    StopLossLevel.EXTENSION) == []  # fmt: skip


def test_extension_with_zero_stock_budget_is_overexposed() -> None:
    triggers = of_level(run(stock_budget_chf=D("0"), extensions=(ext(),)), StopLossLevel.EXTENSION)
    assert {t.action for t in triggers} == {StopLossAction.NO_REORDER, StopLossAction.PROPOSE_MARKDOWN}


def test_extension_exactly_45_days_without_sale_triggers() -> None:
    triggers = of_level(run(extensions=(ext(last_sale_at=NOW - timedelta(days=45)),)), StopLossLevel.EXTENSION)
    assert len(triggers) == 2 and triggers[0].metric == "jours_sans_vente"
    assert triggers[0].value == D("45.00") and triggers[0].threshold == D("45")


def test_extension_one_second_before_45_days_is_compliant() -> None:
    e = ext(last_sale_at=NOW - timedelta(days=45) + timedelta(seconds=1))
    assert of_level(run(extensions=(e,)), StopLossLevel.EXTENSION) == []


def test_extension_never_sold_counts_from_first_stock_entry() -> None:
    e = ext(last_sale_at=None, first_stocked_at=NOW - timedelta(days=46))
    (t, _) = of_level(run(extensions=(e,)), StopLossLevel.EXTENSION)
    assert "aucune vente" in t.reason and t.value == D("46.00")


def test_extension_without_stock_or_reference_is_not_idle() -> None:
    old = NOW - timedelta(days=200)
    assert of_level(run(extensions=(ext(stock_value_at_cost=D("0"), last_sale_at=old),)), StopLossLevel.EXTENSION) == []
    assert of_level(run(extensions=(ext(last_sale_at=None),)), StopLossLevel.EXTENSION) == []


# ------------------------------------------------------------------------------------- pub


def spend(campaign: str, days_ago: int, amount: str) -> AdSpend:
    return AdSpend(campaign_id=campaign, day=TODAY - timedelta(days=days_ago), amount=D(amount))


def order(oid: str, campaign: str, contribution: str, *, hours_ago: int = 30, status: str = "PAID") -> AttributedOrder:
    return AttributedOrder(
        order_id=oid,
        campaign_id=campaign,
        paid_at=NOW - timedelta(hours=hours_ago),
        contribution_before_acquisition=D(contribution),
        status=status,  # type: ignore[arg-type]
    )


def ads(*, spends=(), orders=(), cap: str | None = "1000") -> list[Trigger]:
    return of_level(
        run(
            ad_spends=tuple(spends),
            attributed_orders=tuple(orders),
            ads_daily_cap_chf=None if cap is None else D(cap),
        ),
        StopLossLevel.ADS,
    )


def test_ads_cac_equal_to_contribution_is_compliant() -> None:
    assert ads(spends=[spend("FICTIF_CAMP", 2, "40")], orders=[order("O1", "FICTIF_CAMP", "20"),
                                                               order("O2", "FICTIF_CAMP", "20")]) == []  # fmt: skip


def test_ads_cac_above_contribution_cuts_campaign() -> None:
    (t,) = ads(spends=[spend("FICTIF_CAMP", 2, "40.01")],
               orders=[order("O1", "FICTIF_CAMP", "20"), order("O2", "FICTIF_CAMP", "20")])  # fmt: skip
    assert t.action is StopLossAction.CUT_CAMPAIGN and t.scope == "FICTIF_CAMP" and t.metric == "cac_7j_chf"
    assert t.value == D("20.01") and t.threshold == D("20.00")


def test_ads_counts_only_paid_orders_net_of_cancellations_and_refunds() -> None:
    orders = [
        order("O1", "FICTIF_CAMP", "20"),
        order("O2", "FICTIF_CAMP", "20", status="CANCELLED"),
        order("O3", "FICTIF_CAMP", "20", status="REFUNDED"),
    ]
    (t,) = ads(spends=[spend("FICTIF_CAMP", 1, "30")], orders=orders)
    assert t.value == D("30.00") and t.threshold == D("20.00")


def test_ads_window_is_seven_local_days_including_today() -> None:
    assert ads(spends=[spend("FICTIF_CAMP", 7, "500")]) == []  # hors fenêtre
    (t,) = ads(spends=[spend("FICTIF_CAMP", 6, "500")])
    assert t.metric == "depense_7j_sans_commande_chf"
    old_order = order("O1", "FICTIF_CAMP", "1000", hours_ago=24 * 8)
    (t,) = ads(spends=[spend("FICTIF_CAMP", 1, "50")], orders=[old_order])
    assert t.metric == "depense_7j_sans_commande_chf"


def test_ads_order_day_uses_zurich_timezone() -> None:
    # 22:30 UTC le 8.12 = 23:30 à Zurich le 8.12 ; 23:30 UTC le 8.12 = 00:30 le 9.12 (dans la fenêtre)
    first_day = TODAY - timedelta(days=6)
    inside = AttributedOrder(order_id="O1", campaign_id="FICTIF_CAMP",
                             paid_at=datetime.combine(first_day - timedelta(days=1), time(23, 30), tzinfo=UTC),
                             contribution_before_acquisition=D("100"))  # fmt: skip
    late = datetime.combine(first_day - timedelta(days=1), time(22, 30), tzinfo=UTC)
    outside = inside.replace(order_id="O2", paid_at=late)
    assert ads(spends=[spend("FICTIF_CAMP", 1, "50")], orders=[inside]) == []
    assert len(ads(spends=[spend("FICTIF_CAMP", 1, "50")], orders=[outside])) == 1


def test_ads_future_orders_ignored_and_future_spend_rejected() -> None:
    future = AttributedOrder(order_id="O1", campaign_id="FICTIF_CAMP", paid_at=NOW + timedelta(minutes=1),
                             contribution_before_acquisition=D("100"))  # fmt: skip
    assert len(ads(spends=[spend("FICTIF_CAMP", 0, "25")], orders=[future])) == 1
    with pytest.raises(StopLossError, match="futur"):
        ads(spends=[spend("FICTIF_CAMP", -1, "1")])


def test_ads_without_order_judged_from_minimum_spend() -> None:
    assert ads(spends=[spend("FICTIF_CAMP", 1, "19.99")]) == []
    (t,) = ads(spends=[spend("FICTIF_CAMP", 1, "20.00")])
    assert t.value == D("20.00") and t.threshold == D("20.00") and "CAC infini" in t.reason


def test_ads_daily_cap_boundary() -> None:
    assert ads(spends=[spend("A", 0, "19"), spend("B", 0, "13.99")], cap="33") == []
    triggers = ads(spends=[spend("A", 0, "19"), spend("B", 0, "14")], cap="33")
    (t,) = [t for t in triggers if t.scope == "*"]
    assert t.metric == "depense_jour_chf" and t.value == D("33") and t.threshold == D("33")


def test_ads_daily_cap_ignores_yesterday_and_zero_spend() -> None:
    assert [t for t in ads(spends=[spend("A", 1, "19")], cap="10") if t.scope == "*"] == []
    assert ads(spends=[spend("A", 0, "0")], cap="0") == []


def test_ads_any_spend_cut_when_mandate_not_signed() -> None:
    (t,) = ads(spends=[spend("A", 0, "0.01")], cap=None)
    assert t.scope == "*" and t.threshold is None and "sans plafond signé" in t.reason
    assert ads(spends=[spend("A", 0, "0")], cap=None) == []


def test_ads_campaigns_judged_independently() -> None:
    triggers = ads(spends=[spend("GOOD", 1, "10"), spend("BAD", 1, "30")],
                   orders=[order("O1", "GOOD", "25"), order("O2", "BAD", "25")])  # fmt: skip
    assert [t.scope for t in triggers] == ["BAD"]


# ------------------------------------------------------------------------------------ cash


def test_cash_exactly_reserve_is_compliant() -> None:
    assert of_level(run(cash_available_chf=D("1600.00")), StopLossLevel.CASH) == []


def test_cash_one_cent_below_reserve_freezes_purchases_and_ads() -> None:
    (t,) = of_level(run(cash_available_chf=D("1599.99")), StopLossLevel.CASH)
    assert t.action is StopLossAction.FREEZE_PURCHASES_AND_ADS
    assert t.value == D("1599.99") and t.threshold == D("1600")


# ---------------------------------------------------------------------------------- global


def test_global_loss_exactly_20_percent_freezes_everything() -> None:
    (t,) = of_level(run(net_worth=worth("6400.00")), StopLossLevel.GLOBAL)
    assert t.action is StopLossAction.FREEZE_ALL and t.autonomy_level == 1
    assert t.value == D("1600.00") and t.threshold == D("1600.00")
    assert "propriétaire uniquement" in t.reason


def test_global_loss_one_cent_below_threshold_is_compliant() -> None:
    assert of_level(run(net_worth=worth("6400.01")), StopLossLevel.GLOBAL) == []


def test_global_net_worth_uses_prudent_stock_receivables_and_debts() -> None:
    stock = [
        StockValuationLine(product_key="FICTIF_A", qty=5, historical_value=D("1000"), liquidation_value=D("800")),
        StockValuationLine(product_key="FICTIF_B", qty=2, historical_value=D("100"), liquidation_value=D("150")),
        StockValuationLine(product_key="FICTIF_C", qty=1, historical_value=D("1000")),  # défaut 70 %
    ]
    snap = worth("5000", stock=stock, receivables=[BalanceItem(label="PSP en transit", amount=D("300"))],
                 debts=[BalanceItem(label="précommandes encaissées", amount=D("500")),
                        BalanceItem(label="TVA due", amount=D("100"))])  # fmt: skip
    b = net_worth(snap, CONFIG)
    assert b.stock_historical == D("2100") and b.stock_prudent == D("1600.00")
    assert b.total == D("5000") + D("1600.00") + D("300") - D("600")
    # capital 8 000, valeur nette 6 300 => perte 1 700 ≥ 1 600 : gel
    (t,) = of_level(run(net_worth=snap), StopLossLevel.GLOBAL)
    assert t.value == D("1700.00")


def test_prudent_stock_value_is_min_of_cost_and_liquidation() -> None:
    line = StockValuationLine(product_key="FICTIF_A", qty=1, historical_value=D("100"))
    assert prudent_stock_value(line, D("0.70")) == D("70.00")
    assert prudent_stock_value(line.replace(liquidation_value=D("120")), D("0.70")) == D("100")
    assert prudent_stock_value(line.replace(liquidation_value=D("40")), D("0.70")) == D("40")


def test_stock_line_from_historical_cost_ledger() -> None:
    ledger = HistoricalCostLedger("FICTIF_DISPLAY")
    ledger.receive(CostLot(lot_id="L1", product_key="FICTIF_DISPLAY", received_at=NOW - timedelta(days=3), qty=4,
                           unit_cost=D("140")))  # fmt: skip
    line = StockValuationLine.from_ledger(ledger, liquidation_value=D("400"))
    assert line.qty == 4 and line.historical_value == D("560.00") and line.liquidation_value == D("400")


def test_capital_is_contributions_minus_withdrawals() -> None:
    moves = (*capital("8000", "2000"), CapitalMovement(movement_id="FICTIF_RETRAIT", at=NOW - timedelta(days=1),
                                                       kind="WITHDRAWAL", amount=D("1000")))  # fmt: skip
    assert capital_total(moves) == D("9000")
    # retrait de 1 000 : capital 9 000, seuil 1 800 ; valeur nette 7 200 => perte 1 800 : gel
    assert of_level(run(capital_movements=moves, net_worth=worth("7200")), StopLossLevel.GLOBAL)
    assert not of_level(run(capital_movements=moves, net_worth=worth("7200.01")), StopLossLevel.GLOBAL)


def test_no_capital_engaged_no_global_trigger() -> None:
    assert of_level(run(capital_movements=(), net_worth=worth("-50")), StopLossLevel.GLOBAL) == []


def test_effective_capital_after_rebase() -> None:
    base = CapitalBaseline(set_at=NOW, net_value_chf=D("6000"), capital_total_chf=D("8000"))
    assert effective_capital(capital("8000"), base) == D("6000")
    assert effective_capital(capital("8000", "1000"), base) == D("7000")


# ----------------------------------------------------------------------------- verrou global


def frozen_engine() -> StopLossEngine:
    eng = engine()
    eng.evaluate(state(net_worth=worth("6000")), NOW)
    assert eng.frozen
    return eng


def test_global_freeze_is_latched_and_never_rearms_by_itself() -> None:
    eng = frozen_engine()
    for i in range(1, 4):
        later = NOW + timedelta(hours=i)
        triggers = eng.evaluate(state(as_of=later, net_worth=worth("9000", as_of=later)), later)
        (t,) = of_level(triggers, StopLossLevel.GLOBAL)
        assert t.latched and t.metric == "gel_verrouille" and t.action is StopLossAction.FREEZE_ALL
        assert t.autonomy_level == 1
    assert eng.frozen and eng.latch.cause == "THRESHOLD" and eng.latch.since == NOW
    assert [e.event for e in eng.journal].count("GLOBAL_TRIP") == 1


def test_latched_trigger_keeps_current_loss_when_still_breached() -> None:
    eng = frozen_engine()
    (t,) = of_level(eng.evaluate(state(net_worth=worth("5000")), NOW), StopLossLevel.GLOBAL)
    assert t.latched and t.metric == "perte_cumulee_chf" and t.value == D("3000.00")


def test_rearm_with_wrong_token_is_refused_and_logged() -> None:
    eng = frozen_engine()
    with pytest.raises(RearmRefusedError, match="jeton invalide"):
        eng.rearm("FICTIF-mauvais-jeton-000000", "reprise", now=NOW, state=state())
    assert eng.frozen
    last = eng.journal[-1]
    assert last.event == "REARM_REFUSED" and "FICTIF-mauvais" not in last.detail
    assert all(OWNER_TOKEN not in e.detail for e in eng.journal)


def test_rearm_impossible_without_configured_owner_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(OWNER_TOKEN_SHA256_ENV_VAR, raising=False)
    eng = StopLossEngine(CONFIG)
    eng.freeze("A-12", "test de gel", NOW)
    with pytest.raises(RearmRefusedError, match="aucune empreinte"):
        eng.rearm(OWNER_TOKEN, "reprise", now=NOW, state=state())
    assert eng.frozen


def test_owner_hash_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OWNER_TOKEN_SHA256_ENV_VAR, OWNER_HASH.upper())
    eng = StopLossEngine(CONFIG)
    eng.freeze("A-12", "test", NOW)
    eng.rearm(OWNER_TOKEN, "test env", now=NOW, state=state())
    assert not eng.frozen


def test_rearm_by_owner_is_logged_and_rebases_capital() -> None:
    eng = frozen_engine()
    entry = eng.rearm(OWNER_TOKEN, "plan d'ajustement validé", now=NOW, state=state(net_worth=worth("6000")))
    assert entry.event == "REARM" and "plan d'ajustement validé" in entry.detail and "6 000,00 CHF" in entry.detail
    assert not eng.frozen and eng.latch.baseline is not None
    assert eng.latch.baseline.net_value_chf == D("6000") and eng.latch.baseline.capital_total_chf == D("8000")
    # même situation après réarmement : la perte se mesure depuis 6 000 => pas de regel
    assert of_level(eng.evaluate(state(net_worth=worth("6000")), NOW), StopLossLevel.GLOBAL) == []
    # nouvelle perte de 20 % de 6 000 = 1 200 => regel
    (t,) = of_level(eng.evaluate(state(net_worth=worth("4800")), NOW), StopLossLevel.GLOBAL)
    assert t.value == D("1200.00") and t.threshold == D("1200.00") and eng.frozen


def test_rearm_without_rebase_refreezes_if_loss_persists() -> None:
    eng = frozen_engine()
    eng.rearm(OWNER_TOKEN, "réarmement simple", now=NOW, rebase=False)
    assert not eng.frozen and eng.latch.baseline is None
    eng.evaluate(state(net_worth=worth("6000")), NOW)
    assert eng.frozen


def test_rearm_guards() -> None:
    eng = engine()
    with pytest.raises(StopLossError, match="aucun gel"):
        eng.rearm(OWNER_TOKEN, "rien à réarmer", now=NOW, state=state())
    eng = frozen_engine()
    with pytest.raises(StopLossError, match="motif"):
        eng.rearm(OWNER_TOKEN, "  ", now=NOW, state=state())
    with pytest.raises(StopLossError, match="état"):
        eng.rearm(OWNER_TOKEN, "reprise", now=NOW)
    with pytest.raises(StopLossError, match="apport"):
        eng.rearm(OWNER_TOKEN, "reprise", now=NOW, state=state(net_worth=worth("0")))
    with pytest.raises(StopLossError, match="périmé"):
        eng.rearm(OWNER_TOKEN, "reprise", now=NOW + timedelta(days=2), state=state())
    with pytest.raises(RearmRefusedError):
        eng.rearm("", "reprise", now=NOW, state=state())
    with pytest.raises(StopLossError):
        eng.rearm(OWNER_TOKEN, "reprise", now=datetime(2026, 12, 15), state=state())  # naïf
    assert eng.frozen


def test_manual_freeze_by_agent_needs_owner_to_rearm() -> None:
    eng = engine()
    latch = eng.freeze("A-12 QA", "débit inconnu sur PayPal", NOW)
    assert latch.frozen and latch.cause == "MANUAL"
    (t,) = of_level(eng.evaluate(state(), NOW), StopLossLevel.GLOBAL)
    assert t.latched and "MANUAL" in t.reason
    eng.freeze("A-05", "second signalement", NOW)
    assert [e.event for e in eng.journal].count("MANUAL_FREEZE") == 2
    with pytest.raises(StopLossError):
        eng.freeze("", "x", NOW)
    eng.rearm(OWNER_TOKEN, "fausse alerte vérifiée", now=NOW, state=state())
    assert not eng.frozen


def test_latch_and_journal_survive_restart() -> None:
    eng = frozen_engine()
    restored = StopLossEngine(CONFIG, owner_token_sha256=OWNER_HASH, latch=eng.latch, journal=eng.journal)
    assert restored.frozen
    (t,) = of_level(restored.evaluate(state(), NOW), StopLossLevel.GLOBAL)
    assert t.latched
    assert [e.seq for e in restored.journal] == list(range(1, len(restored.journal) + 1))
    with pytest.raises(StopLossError, match="séquentiel"):
        StopLossEngine(CONFIG, journal=eng.journal[1:])
    assert GlobalLatch.model_validate_json(eng.latch.model_dump_json()) == eng.latch


def test_latch_model_rejects_incoherent_state() -> None:
    with pytest.raises(ValidationError):
        GlobalLatch(frozen=True)


def test_engine_rejects_invalid_owner_hash() -> None:
    with pytest.raises(StopLossError, match="sha256"):
        StopLossEngine(CONFIG, owner_token_sha256="pas-un-hash")


def test_hash_owner_token_requires_long_token() -> None:
    with pytest.raises(StopLossError):
        hash_owner_token("court")
    assert len(OWNER_HASH) == 64


def test_engine_status_reports_freeze_and_level_1() -> None:
    eng = frozen_engine()
    status = eng.status([], as_of=NOW, autonomy_level=3)
    assert status.global_frozen and status.autonomy_level == 1
    assert engine().status([], as_of=NOW, autonomy_level=3).autonomy_level == 3


def test_evaluation_journal_is_append_only_and_hashed() -> None:
    eng = engine()
    eng.evaluate(state(), NOW)
    eng.evaluate(state(cash_available_chf=D("100")), NOW)
    events = eng.journal
    assert [e.event for e in events] == ["EVALUATION", "EVALUATION"]
    assert events[0].triggers_hash != events[1].triggers_hash
    assert isinstance(events, tuple)  # copie en lecture seule : aucune écriture externe


# ------------------------------------------------------------------------------------ temps


def window(**kw) -> ValidationWindow:
    base = dict(
        started_at=NOW - timedelta(days=60),
        paid_orders_net=30,
        contribution_after_ads_chf=D("0.01"),
        oversells=0,
        pilot_stock_cost_chf=D("3000"),
        sold_cost_chf=D("1500"),
    )
    base.update(kw)
    return ValidationWindow(**base)


def test_time_all_thresholds_met_no_report() -> None:
    assert of_level(run(validation_window=window()), StopLossLevel.TIME) == []


def test_time_not_evaluated_before_60_days() -> None:
    w = window(started_at=NOW - timedelta(days=60) + timedelta(seconds=1), paid_orders_net=0)
    assert of_level(run(validation_window=w), StopLossLevel.TIME) == []


@pytest.mark.parametrize(
    "change, metric",
    [
        ({"paid_orders_net": 29}, "commandes_payees_nettes"),
        ({"contribution_after_ads_chf": D("0")}, "contribution_apres_pub_chf"),
        ({"oversells": 1}, "surventes"),
        ({"sold_cost_chf": D("1499.99")}, "ecoulement_stock_pilote"),
        ({"pilot_stock_cost_chf": D("0"), "sold_cost_chf": D("0")}, "ecoulement_stock_pilote"),
    ],
)
def test_time_each_missed_threshold_requests_decision_report(change: dict, metric: str) -> None:
    (t,) = of_level(run(validation_window=window(**change)), StopLossLevel.TIME)
    assert t.action is StopLossAction.DECISION_REPORT and t.metric == metric
    assert "continuer / ajuster / arrêter" in t.reason


def test_time_all_missed_gives_four_reports() -> None:
    w = window(paid_orders_net=3, contribution_after_ads_chf=D("-250"), oversells=2, sold_cost_chf=D("100"))
    triggers = of_level(run(validation_window=w), StopLossLevel.TIME)
    assert len(triggers) == 4
    assert next(t for t in triggers if t.metric == "ecoulement_stock_pilote").value == D("0.0333")


def test_time_prelaunch_60_days_after_first_contribution() -> None:
    at = NOW - timedelta(days=60)
    (t,) = of_level(run(capital_movements=capital("8000", at=at)), StopLossLevel.TIME)
    assert t.scope == "ouverture" and t.value == D("60.00")
    assert of_level(run(capital_movements=capital("8000", at=at + timedelta(seconds=1))), StopLossLevel.TIME) == []


# ---------------------------------------------------------------------- état et validations


def test_stale_or_future_state_is_refused() -> None:
    with pytest.raises(StopLossError, match="périmé"):
        evaluate_levels(state(), NOW + timedelta(hours=24, seconds=1), CONFIG)
    assert evaluate_levels(state(), NOW + timedelta(hours=24), CONFIG) == []
    with pytest.raises(StopLossError, match="futur"):
        evaluate_levels(state(as_of=NOW + timedelta(minutes=6), net_worth=worth(as_of=NOW)), NOW, CONFIG)
    with pytest.raises(StopLossError, match="valeur nette"):
        evaluate_levels(state(net_worth=worth(as_of=NOW - timedelta(days=2))), NOW, CONFIG)
    with pytest.raises(StopLossError, match="fuseau"):
        evaluate_levels(state(), datetime(2026, 12, 15, 18), CONFIG)


@pytest.mark.parametrize(
    "kw",
    [
        {"ad_spends": (spend("A", 1, "1"), spend("A", 1, "2"))},
        {"attributed_orders": (order("O1", "A", "1"), order("O1", "B", "1"))},
        {"products": (pm("0.2", "10"), pm("0.3", "10"))},
        {"extensions": (ext(), ext())},
        {"capital_movements": capital("1", "2") + capital("3")},
        {"capital_movements": capital("8000", at=NOW + timedelta(hours=1))},
        {"cash_available_chf": 1600.0},
        {"stock_budget_chf": True},
    ],
)
def test_invalid_state_is_rejected(kw: dict) -> None:
    with pytest.raises(ValidationError):
        state(**kw)


def test_naive_datetimes_rejected_in_inputs() -> None:
    with pytest.raises(ValidationError):
        ext(last_sale_at=datetime(2026, 12, 1))
    with pytest.raises(ValidationError):
        NetWorthSnapshot(as_of=datetime(2026, 12, 1), cash_chf=D("1"))
    with pytest.raises(ValidationError):
        NetWorthSnapshot(as_of=NOW, cash_chf=D("1"), stock=(
            StockValuationLine(product_key="X", qty=1, historical_value=D("1")),
            StockValuationLine(product_key="X", qty=1, historical_value=D("1"))))  # fmt: skip


def test_healthy_state_has_no_trigger() -> None:
    assert run() == []


# ----------------------------------------------------------------------- statut et intégration


def test_status_aggregates_triggers_for_mandate_and_reorder() -> None:
    triggers = run(
        products=(pm("0.05", "30", product_key="FICTIF_P1"),),
        extensions=(ext(stock_value_at_cost=D("800")),),
        ad_spends=(spend("FICTIF_CAMP", 0, "50"),),
        cash_available_chf=D("1000"),
        net_worth=worth("6000"),
        ads_daily_cap_chf=D("33"),
    )
    assert triggers[0].level is StopLossLevel.GLOBAL  # tri : le plus grave d'abord
    status = StopLossStatus.from_triggers(triggers, as_of=NOW, autonomy_level=4)
    assert status.global_frozen and status.purchases_and_ads_frozen and status.autonomy_level == 1
    assert status.blocked_products == ("FICTIF_P1",)
    assert status.no_reorder_extensions == ("FICTIF_EXT_A",) == status.markdown_extensions
    assert status.cut_campaigns == ("FICTIF_CAMP",) and status.ads_globally_cut
    assert status.blocks_reorder_of("FICTIF_Z", "FICTIF_EXT_Z")
    assert len(status.triggers_hash) == 64


def test_status_requires_valid_autonomy_level() -> None:
    for bad in (0, 5, True):
        with pytest.raises(StopLossError):
            StopLossStatus.from_triggers([], as_of=NOW, autonomy_level=bad)  # type: ignore[arg-type]
    calm = StopLossStatus.from_triggers([], as_of=NOW, autonomy_level=2)
    assert not calm.blocks_reorder_of("FICTIF_P", "FICTIF_E") and calm.decision_report_due is False


def test_stoploss_feeds_propose_reorder() -> None:
    offer = SupplierOffer(supplier_id="FICTIF_SUPPLIER", supplier_sku="FICTIF-SKU", language="FR", moq=1, carton_qty=1,
                          availability_status=AvailabilityStatus.IN_STOCK, available_qty=50,
                          source_ts=NOW - timedelta(hours=1), raw_ref="FICTIF")  # fmt: skip
    cands = [
        ReorderCandidate(product_key="FICTIF_P1", extension="FICTIF_EXT_A", offer=offer, unit_cost_chf=D("50"),
                         sellable_qty=0, avg_daily_sales=D("1"), lead_time_days=3),
        ReorderCandidate(product_key="FICTIF_P2", extension="FICTIF_EXT_B", offer=offer, unit_cost_chf=D("50"),
                         sellable_qty=0, avg_daily_sales=D("1"), lead_time_days=3),
    ]  # fmt: skip
    triggers = run(extensions=(ext(stock_value_at_cost=D("800")),))
    status = StopLossStatus.from_triggers(triggers, as_of=NOW, autonomy_level=4)
    proposal = propose_reorder(cands, budget_available=D("5000"), stock_budget_total=D("3000"), now=NOW,
                               blocked_extensions=status.no_reorder_extensions,
                               blocked_products=status.blocked_products,
                               cash_reserve_chf=CONFIG.cash.reserve_chf)  # fmt: skip
    assert [s.reason for s in proposal.skipped] == ["STOP_LOSS_EXTENSION"]
    assert [ln.product_key for ln in proposal.lines] == ["FICTIF_P2"]


# ---------------------------------------------------------------------------------- rapport


def test_render_report_lists_triggers_and_owner_decisions() -> None:
    eng = engine()
    triggers = eng.evaluate(state(net_worth=worth("6000"), validation_window=window(paid_orders_net=2),
                                  extensions=(ext(stock_value_at_cost=D("800")),)), NOW)  # fmt: skip
    text = render_report(triggers, now=NOW)
    assert "| Global | entreprise | perte_cumulee_chf |" in text and "(verrouillé)" in text
    assert "## Validation humaine requise" in text and "Continuer" in text and "Arrêter" in text
    assert "Démarques proposées" in text
    calm = render_report([], now=NOW)
    assert "Aucun stop-loss déclenché" in calm and "Validation humaine requise" in calm


def test_labels_cover_all_levels_and_actions() -> None:
    assert set(LEVEL_LABELS_FR) == set(StopLossLevel)
    assert set(ACTION_LABELS_FR) == set(StopLossAction)
    assert max(lvl.severity for lvl in StopLossLevel) == StopLossLevel.GLOBAL.severity == 6


def test_format_chf_swiss_romand() -> None:
    assert format_chf(D("1600")) == "1 600,00 CHF"
    assert format_chf(D("-1234567.555")) == "−1 234 567,56 CHF"
    assert format_chf(None) == "—"


# ------------------------------------------------------------------------- document lisible


DOC = Path(__file__).resolve().parents[1] / "docs" / "00-pilotage" / "STOP_LOSS.md"


def test_stop_loss_doc_states_every_threshold_and_rearm_rule() -> None:
    text = DOC.read_text(encoding="utf-8")
    for needle in ("12 %", "8 CHF", "25 %", "45 jours", "7 derniers jours", "1 600 CHF", "20 %", "60 jours"):
        assert needle in text, needle
    assert "Propriétaire uniquement" in text and "réarm" in text.lower()
    assert "`config/stoploss.v1.yaml`" in text and CONFIG.stoploss_version in text
    assert text.rstrip().rsplit("\n## ", 1)[-1].startswith("Validation humaine requise")


def test_stop_loss_doc_examples_are_engine_results() -> None:
    from pokeshop.pricing import contribution

    text = DOC.read_text(encoding="utf-8")
    params = load_rules().pricing
    assert contribution(D("199.90"), D("140"), params) == (D("30.62"), D("0.1656"))
    assert contribution(D("179.90"), D("140"), params) == (D("12.62"), D("0.0758"))
    assert "12,62 CHF ; **7,58 %**" in text and "30,62 CHF ; 16,56 %" in text
    snap = worth("4000", stock=[StockValuationLine(product_key="FICTIF_S", qty=20, historical_value=D("2800"))],
                 receivables=[BalanceItem(label="PSP", amount=D("250"))],
                 debts=[BalanceItem(label="précommandes", amount=D("180")),
                        BalanceItem(label="TVA", amount=D("90"))])  # fmt: skip
    (t,) = of_level(run(net_worth=snap), StopLossLevel.GLOBAL)
    assert net_worth(snap, CONFIG).total == D("5940.00") and t.value == D("2060.00")
    assert "Valeur nette = 4 000 + 1 960 + 250 − 270 = 5 940 ; perte = 2 060" in text
    eng = engine()
    eng.evaluate(state(net_worth=snap), NOW)
    eng.rearm(OWNER_TOKEN, "exemple du document", now=NOW, state=state(net_worth=snap))
    assert not of_level(eng.evaluate(state(net_worth=worth("4752.01")), NOW), StopLossLevel.GLOBAL)
    (again,) = of_level(eng.evaluate(state(net_worth=worth("4752")), NOW), StopLossLevel.GLOBAL)
    assert again.threshold == D("1188.00")
    assert "1 188 CHF" in text and "4 752 CHF" in text


# ------------------------------------------------------------------- point zéro après lancement


def launch_state(cash: str, stock: str | None) -> StopLossState:
    """Budget BP §3 : 8 000 CHF apportés ; 2 900 de lancement non récupérables ; stock pilote 3 000."""
    pilot = StockValuationLine(product_key="FICTIF_PILOTE", qty=30, historical_value=D(stock or "0"))
    lines = () if stock is None else (pilot,)
    return state(cash_available_chf=D(cash), net_worth=worth(cash, stock=lines))


def test_literal_definition_freezes_once_launch_budget_is_spent() -> None:
    (before_stock,) = of_level(evaluate_levels(launch_state("5100", None), NOW, CONFIG), StopLossLevel.GLOBAL)
    assert before_stock.value == D("2900.00")  # coûts de lancement = perte au sens littéral
    (after_stock,) = of_level(evaluate_levels(launch_state("2100", "3000"), NOW, CONFIG), StopLossLevel.GLOBAL)
    assert after_stock.value == D("3800.00")  # + décote prudente de 30 % sur le stock


def test_point_zero_set_by_owner_measures_loss_from_opening() -> None:
    eng = engine()
    entry = eng.set_baseline(OWNER_TOKEN, "ouverture : lancement assumé", now=NOW, state=launch_state("2100", "3000"))
    assert entry.event == "BASELINE_SET" and "4 200,00 CHF" in entry.detail
    assert eng.latch.baseline is not None and eng.latch.baseline.origin == "POINT_ZERO"
    assert of_level(eng.evaluate(launch_state("2100", "3000"), NOW), StopLossLevel.GLOBAL) == []
    # 20 % de 4 200 = 840 : gel si la valeur nette tombe à 3 360
    assert not of_level(eng.evaluate(state(net_worth=worth("3360.01")), NOW), StopLossLevel.GLOBAL)
    (t,) = of_level(eng.evaluate(state(net_worth=worth("3360")), NOW), StopLossLevel.GLOBAL)
    assert t.threshold == D("840.00") and eng.frozen


def test_point_zero_guards() -> None:
    eng = engine()
    with pytest.raises(RearmRefusedError):
        eng.set_baseline("FICTIF-mauvais-jeton-000000", "x", now=NOW, state=state())
    assert eng.journal[-1].event == "BASELINE_REFUSED" and eng.latch.baseline is None
    with pytest.raises(StopLossError, match="motif"):
        eng.set_baseline(OWNER_TOKEN, "", now=NOW, state=state())
    with pytest.raises(StopLossError, match="apport"):
        eng.set_baseline(OWNER_TOKEN, "x", now=NOW, state=state(net_worth=worth("-1")))
    eng.freeze("A-12", "précaution", NOW)
    with pytest.raises(StopLossError, match="rearm"):
        eng.set_baseline(OWNER_TOKEN, "x", now=NOW, state=state())


def test_stop_loss_doc_point_zero_figures() -> None:
    text = DOC.read_text(encoding="utf-8")
    for figure in ("**2 900 CHF ≥ 1 600 CHF**", "**3 800 CHF**", "**840 CHF**", "**3 360 CHF**", "set_baseline"):
        assert figure in text, figure


def test_point_zero_declared_on_day_one_with_accepted_launch_costs() -> None:
    eng = engine()
    deposit_day = state(net_worth=worth("8000"), cash_available_chf=D("8000"))
    eng.set_baseline(OWNER_TOKEN, "J1 : 2 900 de lancement + 900 de décote assumés", now=NOW, state=deposit_day,
                     reference_chf=D("4200"))  # fmt: skip
    assert eng.latch.baseline is not None and eng.latch.baseline.net_value_chf == D("4200")
    # lancement réalisé comme prévu : aucune perte au sens du stop-loss
    assert of_level(eng.evaluate(launch_state("2100", "3000"), NOW), StopLossLevel.GLOBAL) == []
    # lancement plus cher que prévu (840 CHF de plus) : gel
    assert of_level(eng.evaluate(launch_state("1260", "3000"), NOW), StopLossLevel.GLOBAL)
    with pytest.raises(StopLossError):
        engine().set_baseline(OWNER_TOKEN, "x", now=NOW, state=deposit_day, reference_chf=D("0"))
    for bad in (4200.0, [1]):
        with pytest.raises(StopLossError, match="référence"):
            engine().set_baseline(OWNER_TOKEN, "x", now=NOW, state=deposit_day, reference_chf=bad)  # type: ignore[arg-type]
