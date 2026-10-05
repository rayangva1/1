"""Tests du tableau de bord interne : KPI du BP §12 calculés à la main, routes /dashboard, HTML statique.

Jeu FICTIF de ``pokeshop.dashboard.demo_inputs`` (photo du lundi 16.11.2026 07:30, Europe/Zurich) :

* Étoile polaire = exemple de ``docs/00-pilotage/ETOILE_POLAIRE.md`` §3 : W45 −53,49 ; W46 −81,17
  (delta −27,68) ; cumul −134,66 ; moyenne des 2 semaines closes (−53,49 − 81,17) / 2 = −67,33.
* Dimanche 15.11 : aucune vente, publicité 35,00 => contribution du jour −35,00.
* Vendredi 13.11 : commande E, 87,88 − 60,00 − 2,68 − 3,00 = 22,20 CHF ; 22,20 / 87,88 = 25,26 %.
* Samedi 14.11 : remboursement de B (−87,88 de ventes, +60,00 de coût repris, 7,00 de SAV) => −34,88.
* W46 : CAC = 35,00 / 3 = 11,67 ; contribution avant acquisition 46,14 / 3 = 15,38 ; SAV 7,00 / 3 = 2,33.
* Novembre (en cours) : 15,5 h ; −134,66 / 15,5 = −8,69 CHF/h ; CA de l'entité 11 × 5 000 + 5 545,60
  = 60 545,60 (60,55 % de 100 000) ; projection (5 000 + 5 000 + 5 545,60) × 4 = 62 182,40.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, Services, create_app
from pokeshop.audit import to_jsonable
from pokeshop.dashboard import (
    DEMO_AS_OF,
    INTERNAL_BANNER,
    CashPosition,
    DashboardConfig,
    DashboardError,
    DashboardInputs,
    MonthlyTurnover,
    OpenOrder,
    ProductStock,
    SaleLine,
    StopLossView,
    ToolExpense,
    build_reports,
    business_days_between,
    daily_report,
    demo_inputs,
    fmt_chf,
    fmt_pct,
    monthly_report,
    north_star_block,
    pending_decisions,
    stoploss_block,
    weekly_report,
)
from pokeshop.incidents import LogNotifier
from pokeshop.northstar import ContributionEntry, Post
from pokeshop.rules import load_rules
from pokeshop.settings import load_settings, sha256_hex
from pokeshop.stoploss import (
    CapitalBaseline,
    StopLossLevel,
    StopLossState,
    hash_owner_token,
    load_stoploss_config,
)
from pokeshop.treasury import CASH_STOPLOSS_RESERVE
from pydantic import ValidationError

TZ = ZoneInfo("Europe/Zurich")
ROOT = Path(__file__).resolve().parents[1]
API_TOKEN = "FICTIF-jeton-api-dashboard-000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-dashboard-01"
H = {API_TOKEN_HEADER: API_TOKEN}


@pytest.fixture(scope="module")
def demo() -> DashboardInputs:
    return demo_inputs()


@pytest.fixture(scope="module")
def bundle(demo: DashboardInputs) -> Any:
    return build_reports(demo, month="2026-11", now=DEMO_AS_OF)


def at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, datetime.min.time().replace(hour=hour), tzinfo=TZ)


# ------------------------------------------------------------------------------- formats


def test_formats_are_swiss_french() -> None:
    assert fmt_chf(D("1600")) == "1 600,00 CHF"
    assert fmt_chf(D("-134.66")) == "−134,66 CHF"
    assert fmt_chf(None) == "—"
    assert fmt_pct(D("0.1656")) == "16,56 %"
    assert fmt_pct(D("-0.0758")) == "−7,58 %"
    assert fmt_pct(None) == "—"


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 11, 13), date(2026, 11, 16), 1),  # vendredi -> lundi
        (date(2026, 11, 10), date(2026, 11, 16), 4),  # mardi -> lundi suivant
        (date(2026, 11, 11), date(2026, 11, 16), 3),
        (date(2026, 11, 16), date(2026, 11, 16), 0),
        (date(2026, 11, 16), date(2026, 11, 13), 0),
        (date(2026, 11, 11), date(2026, 11, 18), 5),
    ],
)
def test_business_days_between(start: date, end: date, expected: int) -> None:
    assert business_days_between(start, end) == expected


# ------------------------------------------------------------------------- configuration


def test_config_defaults_match_bp_and_engine_values() -> None:
    cfg = DashboardConfig()
    assert cfg.cash_reserve_chf == CASH_STOPLOSS_RESERVE == D("1600")
    assert (cfg.stock_budget_chf, cfg.extension_cap_share) == (D("3000"), D("0.25"))
    assert (cfg.monthly_fixed_costs_chf, cfg.tools_monthly_envelope_chf) == (D("400"), D("180"))
    assert cfg.vat_threshold_chf == D("100000") and cfg.vat_alert_share == D("0.70")
    assert cfg.hourly_rate_chf is None  # TAUX_HORAIRE_VALORISATION : décision de la propriétaire
    engine = DashboardConfig.from_engine(rules=load_rules(), stoploss=load_stoploss_config())
    assert engine.cash_reserve_chf == D("1600") and engine.stock_budget_chf == D("3000")
    assert engine.extension_cap_share == D("0.25") and engine.after_sales_provision_chf == D("1.00")
    assert engine.no_sale_days[2] == 45 and engine.max_offer_age_hours == 24
    assert DashboardConfig.from_engine(stoploss=load_stoploss_config()).extension_cap_share == D("0.25")


def test_config_refuses_float_bool_and_bad_values() -> None:
    with pytest.raises(ValidationError):
        DashboardConfig(cash_reserve_chf=1600.0)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DashboardConfig(hourly_rate_chf=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        DashboardConfig(no_sale_days=(30, 14, 45))
    with pytest.raises(ValidationError):
        DashboardConfig(timezone="Mars/Olympus")
    assert DashboardConfig(hourly_rate_chf="25").hourly_rate_chf == D("25")


def test_inputs_refuse_naive_dates_duplicates_and_floats() -> None:
    with pytest.raises(ValidationError):
        DashboardInputs(as_of=datetime(2026, 11, 16, 7, 30))
    with pytest.raises(ValidationError, match="doublon"):
        DashboardInputs(
            as_of=DEMO_AS_OF,
            open_orders=(OpenOrder(order_ref="#1", paid_at=DEMO_AS_OF), OpenOrder(order_ref="#1", paid_at=DEMO_AS_OF)),
        )
    with pytest.raises(ValidationError):
        CashPosition(as_of=DEMO_AS_OF, cash_available_chf=2650.0)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SaleLine(order_id="X", sold_at=DEMO_AS_OF, product_key="P", extension="E", qty=1, cost_chf=1.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------- démonstration


def test_demo_is_fictitious_and_complete(demo: DashboardInputs) -> None:
    assert demo.fictif is True and demo.as_of == DEMO_AS_OF
    unset = [name for name in DashboardInputs.model_fields if getattr(demo, name) is None]
    assert unset == []
    text = json.dumps(to_jsonable(demo), ensure_ascii=False)
    assert "@" not in text  # aucune adresse email
    for product in demo.stock or ():
        assert product.product_key.startswith("FICTIF")
    for offer in demo.offers or ():
        assert offer.supplier_id.startswith("fictif_")
    assert all(i.fictif for i in demo.incidents or ())
    assert all(e.request.fictif for e in demo.spend_entries or ())


# ----------------------------------------------------------------------- étoile polaire


def test_north_star_block_reproduces_the_hand_example(bundle: Any) -> None:
    ns = bundle.daily.north_star
    assert ns.available and ns.cumulative == D("-134.66")
    assert (ns.last_closed_week, ns.last_closed_net, ns.last_closed_delta) == ("2026-W46", D("-81.17"), D("-27.68"))
    assert (ns.current_week, ns.current_week_net) == ("2026-W47", D("0"))
    assert ns.average_4_weeks == D("-67.33") and ns.average_weeks_count == 2
    assert ns.trend == "BAISSE" and ns.status == "ALERTE"
    assert [(w.iso_week, w.net, w.cumulative, w.complete) for w in ns.weeks] == [
        ("2026-W45", D("-53.49"), D("-53.49"), True),
        ("2026-W46", D("-81.17"), D("-134.66"), True),
        ("2026-W47", D("0"), D("-134.66"), False),
    ]
    assert "−134,66 CHF" in ns.headline and "2026-W46" in ns.headline


def test_north_star_ignores_entries_after_cutoff(demo: DashboardInputs) -> None:
    cutoff = at(date(2026, 11, 13), 23)
    ns = north_star_block(
        demo.entries,
        cutoff=cutoff,
        tz=TZ,
        period_start=date(2026, 11, 9),
        period_end=date(2026, 11, 16),
        period_label="W46",
    )
    # W46 au vendredi soir : 360,68 − 260,00 − 10,66 − 9,00 − 92,31 = −11,29 (remboursement pas encore connu).
    assert ns.current_week == "2026-W46" and ns.current_week_net == D("-11.29")
    assert ns.cumulative == D("-64.78") and ns.last_closed_week == "2026-W45"
    assert ns.average_4_weeks == D("-53.49") and ns.trend == "INCONNUE"
    assert ns.period_before_acquisition == D("81.02")  # 360,68 − 260 − 10,66 − 9


def test_north_star_unavailable_and_empty() -> None:
    missing = north_star_block(
        None, cutoff=DEMO_AS_OF, tz=TZ, period_start=date(2026, 11, 15), period_end=date(2026, 11, 16), period_label="j"
    )
    assert not missing.available and missing.status == "INDISPONIBLE" and "Source non branchée" in missing.reason
    empty = north_star_block(
        (), cutoff=DEMO_AS_OF, tz=TZ, period_start=date(2026, 11, 15), period_end=date(2026, 11, 16), period_label="j"
    )
    assert not empty.available and empty.status == "INFO" and empty.cumulative == 0


def test_north_star_positive_average_is_ok() -> None:
    entries = (
        ContributionEntry(entry_id="o1", at=at(date(2026, 11, 3)), post=Post.NET_SALES, amount="100.00", order_id="1"),
        ContributionEntry(entry_id="o2", at=at(date(2026, 11, 10)), post=Post.NET_SALES, amount="150.00", order_id="2"),
    )
    ns = north_star_block(
        entries,
        cutoff=at(date(2026, 11, 16), 8),
        tz=TZ,
        period_start=date(2026, 11, 9),
        period_end=date(2026, 11, 16),
        period_label="W46",
    )
    assert ns.status == "OK" and ns.trend == "HAUSSE" and ns.average_4_weeks == D("125.00")


# ---------------------------------------------------------------------------- stop-loss


def test_stoploss_block_from_demo_evaluation(bundle: Any) -> None:
    sl = bundle.daily.stoploss
    assert sl.available and sl.status == "ALERTE" and not sl.global_frozen and sl.autonomy_level == 1
    assert [(t.level, t.scope, t.action.value) for t in sl.triggers] == [
        (StopLossLevel.EXTENSION, "FICTIF_GAMMA", "NO_REORDER"),
        (StopLossLevel.EXTENSION, "FICTIF_GAMMA", "PROPOSE_MARKDOWN"),
        (StopLossLevel.PRODUCT, "FICTIF_DISPLAY_ALPHA", "BLOCK_SALE"),
    ]
    promo = sl.triggers[2]
    assert (promo.value_display, promo.threshold_display) == ("7,58 %", "12,00 %")
    assert sl.triggers[0].threshold_display == "45,00 j"
    counts = {lc.level: lc.count for lc in sl.levels}
    assert counts == {
        StopLossLevel.PRODUCT: 1,
        StopLossLevel.EXTENSION: 1,
        StopLossLevel.ADS: 0,
        StopLossLevel.CASH: 0,
        StopLossLevel.GLOBAL: 0,
        StopLossLevel.TIME: 0,
    }
    assert sl.blocked_products == ("FICTIF_DISPLAY_ALPHA",) and sl.no_reorder_extensions == ("FICTIF_GAMMA",)
    assert sl.rearm_instructions == () and "produit (1)" in sl.headline


def _demo_state(demo: DashboardInputs) -> StopLossState:
    """Reconstruit la photo de démonstration pour la modifier (cash, capital)."""
    from pokeshop import dashboard as module

    captured: dict[str, Any] = {}
    original = module.StopLossView.evaluate

    def spy(state: StopLossState, *args: Any, **kwargs: Any) -> StopLossView:
        captured["state"] = state
        captured["baseline"] = kwargs.get("baseline")
        return original(state, *args, **kwargs)

    module.StopLossView.evaluate = spy  # type: ignore[method-assign]
    try:
        module.demo_inputs()
    finally:
        module.StopLossView.evaluate = original  # type: ignore[method-assign]
    return captured["state"]


def test_global_freeze_is_critical_with_rearm_instructions(demo: DashboardInputs) -> None:
    state = _demo_state(demo)
    # Sans point zéro : capital 8 000, valeur nette 3 521,52 => perte 4 478,48 ≥ 1 600 => gel global.
    view = StopLossView.evaluate(state, DEMO_AS_OF, load_stoploss_config(), autonomy_level=3)
    block = stoploss_block(view)
    assert block.status == "CRITIQUE" and block.global_frozen and block.autonomy_level == 1
    assert block.headline.startswith("GEL GLOBAL")
    assert any("POST /stoploss/rearm" in line for line in block.rearm_instructions)
    glob = next(t for t in block.triggers if t.level is StopLossLevel.GLOBAL)
    assert glob.value_display == "4 478,48 CHF" and glob.threshold_display == "1 600,00 CHF"
    decisions = pending_decisions(demo.replace(stoploss=view))
    assert decisions[0].ref == "GLOBAL" and "propriétaire" in decisions[0].label


def test_cash_stoploss_is_critical(demo: DashboardInputs) -> None:
    state = _demo_state(demo).replace(cash_available_chf=D("1599.99"))
    baseline = CapitalBaseline(
        set_at=at(date(2026, 10, 1)), origin="POINT_ZERO", net_value_chf=D("4200"), capital_total_chf=D("8000")
    )
    view = StopLossView.evaluate(state, DEMO_AS_OF, load_stoploss_config(), baseline=baseline)
    block = stoploss_block(view)
    assert block.status == "CRITIQUE" and not block.global_frozen
    cash = next(t for t in block.triggers if t.level is StopLossLevel.CASH)
    assert cash.value_display == "1 599,99 CHF"


def test_stale_state_and_missing_view_are_unavailable(demo: DashboardInputs) -> None:
    state = _demo_state(demo)
    stale = StopLossView.evaluate(state, DEMO_AS_OF + timedelta(days=2), load_stoploss_config())
    assert not stale.available and "périmé" in (stale.error or "")
    block = stoploss_block(stale)
    assert block.status == "INDISPONIBLE" and "refusées" in block.headline
    frozen = stale.replace(global_frozen=True, latch_since=DEMO_AS_OF, latch_cause="MANUAL")
    fblock = stoploss_block(frozen)
    assert fblock.status == "CRITIQUE" and fblock.autonomy_level == 1 and fblock.rearm_instructions
    none = stoploss_block(None, autonomy_level=2)
    assert none.status == "INDISPONIBLE" and "POST /stoploss/state" in none.headline and none.autonomy_level == 2
    with pytest.raises(ValidationError):
        StopLossView(available=True)


# ---------------------------------------------------------------------------------- jour


def test_daily_default_day_is_yesterday(bundle: Any) -> None:
    daily = bundle.daily
    assert daily.kind == "daily" and daily.period_start == date(2026, 11, 15) and daily.complete
    assert daily.period_label == "dimanche 15 novembre 2026" and daily.banner == INTERNAL_BANNER
    assert daily.kpi("ventes_payees").value == 0
    contrib = daily.kpi("contribution_jour")
    assert contrib.value == D("-35.00") and contrib.status == "ALERTE"
    cash = daily.kpi("cash_disponible")
    assert cash.value == D("2650.00") and cash.status == "OK" and "+1 050,00 CHF" in cash.detail
    orders = daily.kpi("commandes_a_preparer")
    assert orders.value == 3 and orders.status == "ALERTE" and "1 en retard" in orders.detail
    assert [r[4] for r in daily.table("commandes_a_preparer").rows] == [
        "EN RETARD",
        "à remettre aujourd'hui",
        "dans le délai",
    ]
    assert [r[2] for r in daily.table("commandes_a_preparer").rows] == ["4 j ouvré(s)", "3 j ouvré(s)", "1 j ouvré(s)"]
    ruptures = daily.kpi("ruptures_locales")
    assert ruptures.value == 1 and ruptures.detail == "FICTIF-TRI-ALPHA"
    stale = daily.kpi("offres_perimees")
    assert stale.value == 1 and stale.status == "ALERTE" and "fictif_grossiste_c" in stale.detail
    assert daily.table("flux_fournisseurs").rows[1][4] == "EN PANNE"
    incidents = daily.kpi("incidents_ouverts")
    assert incidents.value == 2 and incidents.status == "ALERTE" and incidents.detail.startswith("S1 0 | S2 1 | S3 1")
    assert daily.kpi("decisions_attendues").value == 4
    assert daily.unavailable == ()
    assert daily.status == "ALERTE"


def test_daily_sales_day_hand_computed(demo: DashboardInputs) -> None:
    friday = daily_report(demo, day=date(2026, 11, 13), now=DEMO_AS_OF)
    sales = friday.kpi("ventes_payees")
    assert sales.value == 1 and "87,88 CHF" in sales.detail
    contrib = friday.kpi("contribution_jour")
    assert contrib.value == D("22.20") and contrib.status == "OK" and contrib.detail.startswith("25,26 %")
    saturday = daily_report(demo, day=date(2026, 11, 14), now=DEMO_AS_OF)
    assert saturday.kpi("ventes_payees").value == 0
    assert "1 remboursement(s) : −87,88 CHF" in saturday.kpi("ventes_payees").detail
    assert saturday.kpi("contribution_jour").value == D("-34.88")
    with pytest.raises(DashboardError):
        daily_report(demo, day=date(2026, 11, 17))


def test_daily_without_sources_is_unavailable_never_zero() -> None:
    report = daily_report(DashboardInputs(as_of=DEMO_AS_OF))
    statuses = {k.key: k.status for k in report.kpis}
    assert statuses.pop("decisions_attendues") == "OK"
    assert set(statuses.values()) == {"INDISPONIBLE"}
    assert all(k.value is None and k.display == "—" for k in report.kpis if k.key != "decisions_attendues")
    assert report.north_star.status == "INDISPONIBLE" and report.stoploss.status == "INDISPONIBLE"
    assert len(report.unavailable) == 7 and report.status == "INDISPONIBLE"
    assert all("Source à brancher" in k.detail for k in report.kpis if k.status == "INDISPONIBLE")


def test_daily_counts_real_incidents_only_and_preorders(demo: DashboardInputs) -> None:
    sim = demo.incidents[0].replace(simulation=True, incident_id="INC-SIM-1", dedup_key="sim")  # type: ignore[index]
    crit = demo.incidents[0].replace(
        severity="CRITIQUE",
        incident_id="INC-CRIT-1",
        dedup_key="crit",  # type: ignore[index]
        decision_expected="Autoriser la reprise après test (propriétaire uniquement)",
    )
    orders = (
        OpenOrder(order_ref="#P1", paid_at=at(date(2026, 11, 2)), preorder=True, allocation_received=False),
        OpenOrder(order_ref="#P2", paid_at=at(date(2026, 11, 13)), preorder=True),
    )
    report = daily_report(demo.replace(incidents=(sim, crit), open_orders=orders), now=DEMO_AS_OF)
    inc = report.kpi("incidents_ouverts")
    assert inc.value == 1 and inc.status == "CRITIQUE" and "1 en simulation" in inc.detail
    assert any(d.ref == "INC-CRIT-1" for d in report.decisions)
    prep = report.kpi("commandes_a_preparer")
    assert prep.value == 1 and prep.status == "OK" and "2 précommande(s) (1 en attente d'allocation)" in prep.detail


def test_cash_below_reserve_is_critical(demo: DashboardInputs) -> None:
    low = demo.replace(
        cash=CashPosition(as_of=DEMO_AS_OF, cash_available_chf=D("1599.99"), preorders_collected_chf=D("180"))
    )
    kpi = daily_report(low).kpi("cash_disponible")
    assert kpi.status == "CRITIQUE" and "−0,01 CHF" in kpi.detail and "180,00 CHF" in kpi.detail


def test_expired_spend_request_is_not_a_pending_decision(demo: DashboardInputs) -> None:
    later = demo.replace(as_of=DEMO_AS_OF + timedelta(hours=25))
    labels = [d.source for d in pending_decisions(later)]
    assert "mandat" not in labels and "réassort" not in labels
    current = [d for d in pending_decisions(demo) if d.source == "mandat"]
    assert len(current) == 1 and current[0].due == DEMO_AS_OF + timedelta(hours=24)
    assert "48,60 CHF" in current[0].label


# ------------------------------------------------------------------------------- semaine


def test_weekly_w46_hand_computed(bundle: Any) -> None:
    weekly = bundle.weekly
    assert weekly.period_start == date(2026, 11, 9) and weekly.complete
    assert weekly.period_label == "Semaine 2026-W46 (9 novembre – 15 novembre 2026)"
    net = weekly.kpi("contribution_nette_semaine")
    assert net.value == D("-81.17") and "11,14 CHF" in net.detail and "92,31 CHF" in net.detail
    cac = weekly.kpi("cac")
    assert cac.value == D("11.67") and cac.status == "OK" and "15,38 CHF" in cac.detail
    assert weekly.kpi("reachat").value == D(1) / D(3) and weekly.kpi("reachat").display == "33,33 %"
    rotation = {row[0]: row for row in weekly.table("rotation_extensions").rows}
    assert rotation["FICTIF_ALPHA"][1:] == ("140,00 CHF", "420,00 CHF", "33,33 %", "21 j", "14,00 %", "ok")
    assert rotation["FICTIF_BETA"][1:] == ("120,00 CHF", "480,00 CHF", "25,00 %", "28 j", "16,00 %", "ok")
    assert rotation["FICTIF_GAMMA"][4] == "∞ (aucune vente)" and rotation["FICTIF_GAMMA"][2] == "123,60 CHF"
    assert weekly.kpi("extensions_au_dessus_plafond").value == 0
    idle = weekly.kpi("produits_sans_vente")
    assert idle.value == 1 and idle.status == "ALERTE"
    assert weekly.table("produits_sans_vente").rows[0][:3] == ("FICTIF_BOOSTER_GAMMA", "FICTIF_GAMMA", "46 j")
    var = weekly.kpi("ecarts_couts")
    assert var.value == 1 and var.status == "ALERTE" and "3,60 CHF" in var.detail
    assert weekly.table("ecarts_couts").rows[0][4] == "3,00 %"
    assert weekly.kpi("litiges").value == 1 and weekly.kpi("litiges").status == "ALERTE"
    refunds = weekly.kpi("remboursements")
    assert refunds.value == 1 and "87,88 CHF" in refunds.detail
    sav = weekly.kpi("cout_sav_par_commande")
    assert sav.value == D("2.33") and sav.status == "ALERTE"
    proposed = weekly.kpi("commandes_proposees")
    assert proposed.value == 1 and "144,00 CHF" in proposed.detail
    table = weekly.table("commandes_proposees")
    assert table.rows[0][:4] == ("FICTIF_TRIPACK_ALPHA", "FICTIF_ALPHA", "fictif_grossiste_a", "6")
    assert "FICTIF_BOOSTER_GAMMA (STOP_LOSS_EXTENSION)" in table.note
    assert weekly.kpi("heures_proprietaire").value == D("8.5")
    posts = dict(weekly.table("etoile_postes").rows)
    assert posts["Ventes nettes HT"] == "272,80 CHF" and posts["Coût historique"] == "−200,00 CHF"
    assert posts["Contribution nette"] == "−81,17 CHF"
    campaigns = weekly.table("cac_campagnes").rows
    assert campaigns == (("FICTIF-CAMP-1", "35,00 CHF", "2", "17,50 CHF", "22,20 CHF", "rentable"),)


def test_weekly_w45_nets_known_refunds_in_cac(demo: DashboardInputs) -> None:
    w45 = weekly_report(demo, week=date(2026, 11, 4), now=DEMO_AS_OF)
    assert w45.period_start == date(2026, 11, 2)
    assert w45.kpi("contribution_nette_semaine").value == D("-53.49")
    cac = w45.kpi("cac")
    # B remboursée le 14.11 : seule A reste une commande payée nette ; 58,82 = 272,80 − 200 − 7,98 − 6.
    assert cac.value == D("20.00") and "1 commande(s)" in cac.detail and "58,82 CHF" in cac.detail
    assert w45.kpi("reachat").value == 0
    with pytest.raises(DashboardError):
        weekly_report(demo, week=date(2026, 11, 23))


def test_weekly_cac_alerts() -> None:
    week = date(2026, 11, 9)
    base = [
        ContributionEntry(entry_id="s", at=at(week), post=Post.NET_SALES, amount="50.00", order_id="1"),
        ContributionEntry(entry_id="p", at=at(week), post=Post.ACQUISITION, amount="60.00"),
    ]
    inputs = DashboardInputs(as_of=DEMO_AS_OF, entries=tuple(base))
    assert weekly_report(inputs).kpi("cac").status == "ALERTE"
    no_order = DashboardInputs(as_of=DEMO_AS_OF, entries=(base[1],))
    kpi = weekly_report(no_order).kpi("cac")
    assert kpi.value is None and kpi.status == "ALERTE" and "CAC infini" in kpi.detail
    none = DashboardInputs(as_of=DEMO_AS_OF, entries=(base[0],))
    assert weekly_report(none).kpi("cac").status == "INFO"


def test_extension_over_cap_and_no_sale_buckets() -> None:
    stock = (
        ProductStock(
            product_key="P1",
            extension="EXT",
            qty_on_hand=10,
            value_at_cost=D("750.01"),
            first_stocked_at=DEMO_AS_OF - timedelta(days=20),
        ),
        ProductStock(
            product_key="P2",
            extension="EXT2",
            qty_on_hand=1,
            value_at_cost=D("10"),
            first_stocked_at=DEMO_AS_OF - timedelta(days=35),
        ),
        ProductStock(
            product_key="P3",
            extension="EXT2",
            qty_on_hand=0,
            value_at_cost=D("0"),
            first_stocked_at=DEMO_AS_OF - timedelta(days=90),
        ),
    )
    report = weekly_report(DashboardInputs(as_of=DEMO_AS_OF, stock=stock), week=date(2026, 11, 16))
    assert report.kpi("extensions_au_dessus_plafond").value == 1
    assert report.kpi("extensions_au_dessus_plafond").status == "ALERTE"
    rows = {r[0]: r for r in report.table("produits_sans_vente").rows}
    assert set(rows) == {"P1", "P2"} and rows["P1"][5] == "≥ 14 j" and rows["P2"][5] == "≥ 30 j"
    assert report.kpi("produits_sans_vente").status == "INFO"


# ---------------------------------------------------------------------------------- mois


def test_monthly_november_hand_computed(bundle: Any) -> None:
    monthly = bundle.monthly
    assert monthly.period_label == "novembre 2026" and not monthly.complete
    result = monthly.kpi("resultat_mois")
    assert result.value == D("-134.66") and "184,62 CHF" in result.detail
    assert monthly.kpi("heures_mois").value == D("15.5")
    assert monthly.kpi("taux_horaire_implicite").value == D("-8.69")
    assert monthly.kpi("resultat_apres_temps").status == "INDISPONIBLE"
    vat = monthly.kpi("seuil_tva")
    assert vat.value == D("0.6055") and vat.status == "OK"
    assert "60 545,60 CHF" in vat.detail and "62 182,40 CHF" in vat.detail and "12 mois connus" in vat.detail
    assert len(monthly.table("ca_tva").rows) == 12
    capacity = monthly.kpi("capacite_stock")
    assert capacity.value == D("1976.40") and "1 023,60 CHF" in capacity.detail
    caps = {r[0]: r[3] for r in monthly.table("capacite_extensions").rows}
    assert caps == {"FICTIF_ALPHA": "330,00 CHF", "FICTIF_BETA": "270,00 CHF", "FICTIF_GAMMA": "626,40 CHF"}
    tools = monthly.kpi("depenses_outils")
    assert tools.value == D("92.00") and tools.status == "OK"
    assert dict(monthly.table("etoile_postes").rows)["Charges fixes"] == "−184,62 CHF"


def test_monthly_with_hourly_rate_storage_and_alerts(demo: DashboardInputs) -> None:
    cfg = DashboardConfig(hourly_rate_chf="25", storage_capacity_units=30)
    report = monthly_report(demo, cfg, month="2026-11", now=DEMO_AS_OF)
    after = report.kpi("resultat_apres_temps")
    assert after.value == D("-522.16") and "387,50 CHF" in after.detail  # 15,5 h × 25 = 387,50
    storage = report.kpi("occupation_stockage")
    assert storage.value == D("1.1667") and storage.status == "ALERTE"  # 3 + 8 + 24 = 35 unités / 30
    high = demo.replace(turnover=tuple(MonthlyTurnover(month=f"2026-{m:02d}", amount_chf="6000") for m in range(1, 12)))
    vat = monthly_report(high, month="2026-11").kpi("seuil_tva")
    assert vat.status == "ALERTE" and "11 mois connus" in vat.detail  # projection 72 000 ≥ 70 000
    over = demo.replace(turnover=tuple(MonthlyTurnover(month=f"2026-{m:02d}", amount_chf="9500") for m in range(1, 12)))
    assert monthly_report(over, month="2026-11").kpi("seuil_tva").status == "CRITIQUE"  # 104 500 ≥ 100 000
    tools = demo.replace(tool_expenses=(ToolExpense(month="2026-11", tool="Outil FICTIF", amount_chf="180.01"),))
    assert monthly_report(tools, month="2026-11").kpi("depenses_outils").status == "ALERTE"


def test_monthly_default_previous_month_and_errors(demo: DashboardInputs) -> None:
    october = monthly_report(demo)
    assert october.period_label == "octobre 2026" and october.complete
    assert october.kpi("resultat_mois").value == 0
    with pytest.raises(DashboardError):
        monthly_report(demo, month="2026-12")
    with pytest.raises(DashboardError):
        monthly_report(demo, month="novembre")


def test_reports_serialize_without_float(bundle: Any) -> None:
    payload = json.dumps(to_jsonable(bundle), ensure_ascii=False)
    data = json.loads(payload, parse_float=lambda s: (_ for _ in ()).throw(AssertionError(s)))
    assert data["daily"]["north_star"]["cumulative"] == "-134.66"
    assert data["weekly"]["banner"] == INTERNAL_BANNER


# --------------------------------------------------------------------------------- API


@pytest.fixture
def svc() -> Services:
    settings = load_settings(
        {
            "POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN),
            "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN),
        }
    )
    return Services.build(settings, clock=lambda: DEMO_AS_OF, notifier=LogNotifier())


@pytest.fixture
def client(svc: Services) -> TestClient:
    return TestClient(create_app(services=svc))


def body(resp: Any) -> Any:
    def refuse(text: str) -> Any:
        raise AssertionError(f"nombre flottant dans la réponse : {text}")

    return json.loads(resp.content, parse_float=refuse)


ROUTES = ("/dashboard/daily", "/dashboard/weekly", "/dashboard/monthly")


@pytest.mark.parametrize("path", ROUTES)
def test_dashboard_routes_require_token(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401
    assert client.get(path, headers={API_TOKEN_HEADER: "mauvais"}).status_code == 401
    assert client.post(path, headers=H).status_code == 405  # lecture seule


def test_dashboard_routes_closed_without_configured_token() -> None:
    closed = TestClient(create_app(services=Services.build(load_settings({}), clock=lambda: DEMO_AS_OF)))
    resp = closed.get("/dashboard/daily", headers=H)
    assert resp.status_code == 503 and "POKESHOP_API_TOKEN_SHA256" in body(resp)["erreur"]


@pytest.mark.parametrize("path", ROUTES)
def test_dashboard_routes_internal_headers_and_empty_sources(client: TestClient, path: str) -> None:
    resp = client.get(path, headers=H)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store" and "noindex" in resp.headers["x-robots-tag"]
    data = body(resp)
    assert data["interne"] == INTERNAL_BANNER and data["report"]["banner"] == INTERNAL_BANNER
    report = data["report"]
    assert report["north_star"]["status"] == "INFO"  # journal branché mais vide
    assert report["stoploss"]["status"] == "INDISPONIBLE"  # aucune photo d'activité
    assert report["unavailable"]


def test_dashboard_routes_read_engine_state(client: TestClient) -> None:
    payload = {
        "as_of": DEMO_AS_OF.isoformat(),
        "stock_budget_chf": "3000",
        "cash_available_chf": "1500",
        "ads_daily_cap_chf": "33",
        "capital_movements": [
            {
                "movement_id": "FICTIF_APPORT",
                "at": (DEMO_AS_OF - timedelta(days=30)).isoformat(),
                "kind": "CONTRIBUTION",
                "amount": "1500",
            }
        ],
        "net_worth": {"as_of": DEMO_AS_OF.isoformat(), "cash_chf": "1500"},
    }
    assert client.post("/stoploss/state", headers=H, json=payload).status_code == 200
    entries = [
        {
            "entry_id": "FICTIF-o1",
            "at": "2026-11-10T10:00:00+01:00",
            "post": "NET_SALES",
            "amount": "184.92",
            "order_id": "FICTIF-1",
        },
        {"entry_id": "FICTIF-f1", "at": "2026-11-09T10:00:00+01:00", "post": "FIXED_COSTS", "amount": "92.31"},
    ]
    assert client.post("/northstar/entries", headers=H, json={"entries": entries}).status_code == 200
    data = body(client.get("/dashboard/daily", headers=H))["report"]
    assert data["north_star"]["cumulative"] == "92.61" and data["north_star"]["last_closed_week"] == "2026-W46"
    assert data["stoploss"]["status"] == "CRITIQUE"  # cash 1 500 < 1 600
    assert any(t["level"] == "CASH" for t in data["stoploss"]["triggers"])
    kpis = {k["key"]: k for k in data["kpis"]}
    assert kpis["cash_disponible"]["value"] == "1500" and kpis["cash_disponible"]["status"] == "CRITIQUE"
    assert kpis["incidents_ouverts"]["status"] in {"OK", "ALERTE", "CRITIQUE"}
    assert kpis["commandes_a_preparer"]["status"] == "INDISPONIBLE"


def test_dashboard_provider_override_and_parameters(client: TestClient) -> None:
    client.app.state.dashboard_provider = lambda svc, now: demo_inputs()  # type: ignore[attr-defined]
    weekly = body(client.get("/dashboard/weekly", headers=H))["report"]
    kpis = {k["key"]: k for k in weekly["kpis"]}
    assert kpis["contribution_nette_semaine"]["value"] == "-81.17" and kpis["cac"]["value"] == "11.67"
    friday = body(client.get("/dashboard/daily", headers=H, params={"day": "2026-11-13"}))["report"]
    assert {k["key"]: k for k in friday["kpis"]}["contribution_jour"]["value"] == "22.20"
    w45 = body(client.get("/dashboard/weekly", headers=H, params={"week": "2026-11-05"}))["report"]
    assert w45["period_start"] == "2026-11-02"
    november = body(client.get("/dashboard/monthly", headers=H, params={"month": "2026-11"}))["report"]
    assert {k["key"]: k for k in november["kpis"]}["seuil_tva"]["value"] == "0.6055"
    assert client.get("/dashboard/daily", headers=H, params={"day": "13.11.2026"}).status_code == 422
    assert client.get("/dashboard/monthly", headers=H, params={"month": "2026-13"}).status_code == 422
    future = client.get("/dashboard/daily", headers=H, params={"day": "2026-12-01"})
    assert future.status_code == 422 and "postérieur" in body(future)["erreur"]


# --------------------------------------------------------------------------- HTML statique


def _build_module() -> Any:
    spec = importlib.util.spec_from_file_location("dashboard_build", ROOT / "dashboard" / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_dashboard_example_is_up_to_date() -> None:
    build = _build_module()
    expected = build.render_html(
        build.demo_payloads(), source_label="démonstration FICTIVE (pokeshop.dashboard.demo_inputs)"
    )
    committed = (ROOT / "dashboard" / "out" / "index.html").read_text(encoding="utf-8")
    assert committed == expected, "relancer : python dashboard/build.py"
    assert build.main(["--check"]) == 0


def test_static_dashboard_is_internal_self_contained_and_ordered() -> None:
    html_text = (ROOT / "dashboard" / "out" / "index.html").read_text(encoding="utf-8")
    assert html_text.count(INTERNAL_BANNER) >= 2
    assert '<meta name="robots" content="noindex, nofollow, noarchive">' in html_text
    assert "default-src 'none'" in html_text and "DONNÉES FICTIVES" in html_text
    assert not re.search(r"(src|href)=\"(https?:)?//", html_text)  # aucune ressource externe
    assert "@import" not in html_text and "fonts.googleapis" not in html_text
    assert "prefers-color-scheme:dark" in html_text and 'data-theme="dark"' in html_text
    assert 'name="viewport"' in html_text
    for kind in ("daily", "weekly", "monthly"):
        start = html_text.index(f'id="view-{kind}"')
        section = html_text[start : html_text.index("</section>", start)]
        # Étoile polaire puis stop-loss, avant tout autre bloc.
        assert section.index("Étoile polaire") < section.index("Stop-loss") < section.index("Décisions attendues")
        assert section.index("Décisions attendues") < section.index('class="kpis"')
    assert "−134,66 CHF" in html_text and "Comment réarmer" not in html_text
    assert "<script>" in html_text and "localStorage" in html_text and "try{" in html_text


def test_static_render_escapes_and_handles_freeze(tmp_path: Path, demo: DashboardInputs) -> None:
    build = _build_module()
    state = _demo_state(demo)
    frozen_view = StopLossView.evaluate(state, DEMO_AS_OF, load_stoploss_config())
    hostile = demo.replace(
        stoploss=frozen_view,
        open_orders=(OpenOrder(order_ref="<script>alert(1)</script>", paid_at=DEMO_AS_OF - timedelta(days=1)),),
    )
    payloads = to_jsonable(build_reports(hostile, month="2026-11", now=DEMO_AS_OF))
    out = build.build(tmp_path / "x.html", payloads, source_label="test")
    text = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "Comment réarmer (propriétaire uniquement)" in text and "GEL GLOBAL" in text


def test_static_build_api_mode_requires_token_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    build = _build_module()
    monkeypatch.delenv(build.TOKEN_ENV, raising=False)
    assert build.main(["--api", "http://127.0.0.1:9", "--out", str(tmp_path / "y.html")]) == 2
    assert not (tmp_path / "y.html").exists()
    assert build.main(["--check", "--out", str(tmp_path / "absent.html")]) == 1


def test_real_dashboard_is_never_written_inside_the_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SEC-20 / COH-09 : ``--api`` (coûts et marges réels) refuse toute sortie dans le dépôt ; défaut hors dépôt."""
    build = _build_module()
    monkeypatch.setenv(build.TOKEN_ENV, "FICTIF-jeton-api-0000000000000001")
    fetched: list[str] = []

    def fake_fetch(api: str, token: str, **_: object) -> dict[str, dict[str, object]]:
        fetched.append(api)
        return build.demo_payloads()

    monkeypatch.setattr(build, "fetch_payloads", fake_fetch)
    tracked = build.DEFAULT_OUT
    before = tracked.read_bytes()
    for inside in (tracked, build.ROOT / "dashboard" / "out" / "reel.html", build.ROOT / "tableau.html"):
        assert build.main(["--api", "http://127.0.0.1:9", "--out", str(inside)]) == 2
        assert not fetched, "aucune donnée réelle lue avant le refus"
    assert tracked.read_bytes() == before and not (build.ROOT / "dashboard" / "out" / "reel.html").exists()
    # Lien symbolique hors dépôt vers le dépôt : refusé aussi (chemin résolu).
    link = tmp_path / "lien"
    link.symlink_to(build.ROOT / "dashboard" / "out", target_is_directory=True)
    assert build.main(["--api", "http://127.0.0.1:9", "--out", str(link / "x.html")]) == 2
    # Défaut avec --api : hors du dépôt, fichier lisible par son seul auteur.
    assert not build.API_DEFAULT_OUT.resolve().is_relative_to(build.ROOT.resolve())
    monkeypatch.setattr(build, "API_DEFAULT_OUT", tmp_path / "prive" / "tableau.html")
    assert build.main(["--api", "http://127.0.0.1:9"]) == 0
    written = tmp_path / "prive" / "tableau.html"
    assert written.exists() and (written.stat().st_mode & 0o777) == 0o600 and fetched
    assert tracked.read_bytes() == before
    # .gitignore : seules les sorties réelles éventuelles de dashboard/out sont ignorées, pas l'exemple FICTIF.
    ignore = (build.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "dashboard/out/*" in ignore and "!dashboard/out/index.html" in ignore
