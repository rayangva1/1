"""Lot F2 (gouvernance) : régressions de la revue adverse, toutes fermées par défaut.

Chaque test porte l'identifiant du défaut corrigé (MOT-xx, SEC-xx, CON-xx, COH-xx, E2E-xx) et échouait
avant la correction. Principe : aucune valeur décisive (taux, trésorerie, validation, seuil, signature)
n'est déclarée par l'agent qui en bénéficie ; en cas de doute, refus ou validation humaine.
Jetons, montants et références FICTIFS.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
import jetons_roles as JR
from fastapi.testclient import TestClient
from pokeshop import forecast as fc
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.audit import InMemoryStateJournal
from pokeshop.autonomy import GateReason, WriteAction
from pokeshop.incidents import LogNotifier
from pokeshop.mandate import (
    DEFAULT_MANDATE_PATH,
    CASH_FREEZE_CATEGORIES,
    FxRate,
    FxRateBook,
    MandateError,
    MandateOutcome,
    MandateRevocations,
    PaymentMethod,
    SpendCategory,
    SpendLedger,
    SpendReason,
    StatementLine,
    TreasurySnapshot,
    check,
    mandate_fingerprint,
    parse_mandate,
    previous_business_day,
    treasury_from_registers,
)
from pokeshop.models import ReorderCandidate, SupplierOffer
from pokeshop.northstar import (
    COST_LEDGER_SOURCE,
    ContributionEntry,
    CostMovement,
    CostRegister,
    NorthStarError,
    NorthStarLedger,
    Post,
)
from pokeshop.rules import load_rules
from pokeshop.settings import SettingsError, load_settings, sha256_hex
from pokeshop.stoploss import (
    DEFAULT_STOPLOSS_PATH,
    REFERENCE_THRESHOLDS,
    CapitalMovement,
    ExtensionExposure,
    NetWorthSnapshot,
    StopLossEngine,
    StopLossError,
    StopLossState,
    StopLossStatus,
    consistency_errors,
    enforce_signature,
    hash_owner_token,
    load_stoploss_config,
    parse_stoploss_config,
    stoploss_fingerprint,
    strictest_price_rules,
)
from test_autonomy import Rig, spend
from test_mandate import ENVELOPES, NOW, no_fees, proposal, proposals, req, signed, signed_data, status, stock_req, treasury
from test_persistance_postgres import pg  # noqa: F401, F811  (fixture : base jetable, test ignoré sans PostgreSQL)

TZ = ZoneInfo("Europe/Zurich")
R = SpendReason
OK = MandateOutcome.APPROVED_WITHIN_MANDATE
HUMAN = MandateOutcome.NEEDS_HUMAN_APPROVAL
REJECTED = MandateOutcome.REJECTED
API_TOKEN = "FICTIF-jeton-api-0000000000000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
FINANCE_TOKEN = JR.ROLE_TOKENS["finance-pricing"]
OPS_TOKEN = JR.ROLE_TOKENS["operations-sav"]
QA_TOKEN = JR.ROLE_TOKENS["qa-conformite"]
H = {API_TOKEN_HEADER: API_TOKEN}
HO = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: OWNER_TOKEN}
HF, HOPS, HQA, HPHOTO, HTRES, HSYNC, HCAT = JR.HF, JR.HOPS, JR.HQA, JR.HPHOTO, JR.HTRES, JR.HSYNC, JR.HCAT
API_NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def settings(tmp_path: Path, **extra: str):
    env = {
        "POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN),
        "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN),
        "POKESHOP_STATE_DIR": str(tmp_path),
        "POKESHOP_AGENT_TOKENS_SHA256": JR.agent_tokens_env(),
    }
    env.update(extra)
    return load_settings(env)


OWNER_APPORT = {"movement_id": "FICTIF_APPORT", "at": (API_NOW - timedelta(days=30)).isoformat(),
                "kind": "CONTRIBUTION", "amount": "8000"}  # fmt: skip


def boot(tmp_path: Path, *, mandate=None, capital: bool = True, **extra: str) -> tuple[TestClient, Services]:
    """Démarre le service ; ``capital`` : apport FICTIF attesté par la propriétaire (POST /capital/movements, SEC-06)."""
    svc = Services.build(settings(tmp_path, **extra), clock=lambda: API_NOW, notifier=LogNotifier())
    if mandate is not None:
        svc.mandate = mandate
    client = TestClient(create_app(services=svc))
    if capital:
        assert client.post("/capital/movements", headers=HO, json=OWNER_APPORT).status_code in (200, 201)
    return client, svc


def api_mandate():
    """Mandat FICTIF signé, empreinte au coffre, actif le 10.11.2026 (PACKAGING 300 CHF)."""
    return signed(no_fees)


def photo(cash: str = "8000", *, available: str = "5000", at: datetime = API_NOW, **extra: Any) -> dict[str, Any]:
    data = {
        "as_of": at.isoformat(), "stock_budget_chf": "3000", "cash_available_chf": available, "ads_daily_cap_chf": "33",
        "net_worth": {"as_of": at.isoformat(), "cash_chf": cash},
    }
    data.update(extra)
    return data


def spend_payload(key: str, amount: str = "280", *, requested_by: str = "operations-sav",
                  treasury: dict[str, Any] | None = None, **request: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "request": {"amount": amount, "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                    "payment_method": "PAYPAL", "purpose": "Cartons FICTIFS", "idempotency_key": key,
                    "requested_by": requested_by, "requested_at": API_NOW.isoformat(),
                    "amount_source": "devis FICTIF n°1", **request},
        "record": True,
    }
    if treasury is not None:
        data["treasury"] = treasury
    return data


def deposit(client: TestClient, *, available: str = "5000", paypal: str = "5000") -> None:
    """Photo (workflow 07, n8n-07-stoploss) et solde PayPal (connecteur de trésorerie) : jamais l'agent qui dépense."""
    assert client.post("/stoploss/state", headers=HO, json=photo(available=available)).status_code == 200
    reading = {"as_of": API_NOW.isoformat(), "balance_chf": paypal, "source": "relevé PayPal FICTIF"}
    assert client.post("/treasury/paypal-balance", headers=HTRES, json=reading).status_code == 200


# =============================================================================== MOT-02 taux de change


def test_mot02_foreign_currency_without_reference_rate_never_approved() -> None:
    """MOT-02 : EUR 4000 au taux « 0.01 » déclaré par l'agent n'est plus approuvé sur 40 CHF."""
    eur = req(amount=D("4000"), currency="EUR", fx_rate_to_chf=D("0.01"), fx_source="agent", fx_date=NOW.date(),
              category=SpendCategory.PACKAGING)
    decision = check(eur, signed(no_fees), SpendLedger(), status(), treasury(), now=NOW)
    assert decision.outcome is not OK and decision.has(R.FX_RATE_UNVERIFIED)
    empty_book = check(eur, signed(no_fees), SpendLedger(), status(), treasury(), now=NOW, fx_rates=FxRateBook())
    assert empty_book.outcome is HUMAN and empty_book.has(R.FX_RATE_UNVERIFIED)


def fx_book(rate: str = "0.9375", day: date | None = None, at: datetime = NOW) -> FxRateBook:
    book = FxRateBook()
    book.record(FxRate(currency="EUR", rate_to_chf=D(rate), rate_date=day or at.date(), source="BNS FICTIF",
                       recorded_by="propriétaire", recorded_at=at))
    return book


def test_mot02_reference_rate_fixes_the_chf_amount_and_rejects_a_forged_rate() -> None:
    book = fx_book()
    forged = req(amount=D("4000"), currency="EUR", fx_rate_to_chf=D("0.01"), fx_source="agent", fx_date=NOW.date())
    d = check(forged, signed(no_fees), SpendLedger(), status(), treasury(), now=NOW, fx_rates=book)
    assert d.outcome is REJECTED and d.has(R.FX_RATE_MISMATCH)
    assert d.amount_chf == D("3750.00") and d.context.fx_reference_rate == D("0.9375")  # jamais 40 CHF
    honest = req(amount=D("100"), currency="EUR", fx_rate_to_chf=D("0.94"), fx_source="banque", fx_date=NOW.date())
    ok = check(honest, signed(no_fees), SpendLedger(), status(), treasury(), now=NOW, fx_rates=book)
    assert ok.outcome is OK and ok.amount_chf == D("93.75") and ok.has(R.PAYPAL_FX_CONVERSION)
    assert not ok.has(R.FX_RATE_MISMATCH)  # 0,27 % d'écart ≤ 1 %


def test_mot02_reference_rate_older_than_one_business_day_is_unverified() -> None:
    monday = datetime(2026, 11, 16, 10, 0, tzinfo=TZ)
    assert previous_business_day(monday.date()) == date(2026, 11, 13)  # vendredi
    eur = req(amount=D("100"), currency="EUR", fx_rate_to_chf=D("0.9375"), fx_source="banque",
              fx_date=date(2026, 11, 13), requested_at=monday)
    m = signed(no_fees)
    snap, st = treasury(as_of=monday), status(as_of=monday)
    friday = check(eur, m, SpendLedger(), st, snap, now=monday, fx_rates=fx_book(day=date(2026, 11, 13), at=monday))
    assert not friday.has(R.FX_RATE_UNVERIFIED)
    thursday = check(eur, m, SpendLedger(), st, snap, now=monday, fx_rates=fx_book(day=date(2026, 11, 12), at=monday))
    assert thursday.outcome is HUMAN and thursday.has(R.FX_RATE_UNVERIFIED)
    with pytest.raises(ValueError, match="futur"):
        FxRate(currency="EUR", rate_to_chf=D("1"), rate_date=date(2026, 11, 11), source="x" * 3, recorded_by="xx",
               recorded_at=NOW)


def test_mot02_fx_rates_route_is_owner_only_and_persisted(tmp_path: Path) -> None:
    client, svc = boot(tmp_path)
    rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": API_NOW.date().isoformat(), "source": "BNS FICTIF"}
    assert client.post("/fx/rates", headers=H, json=rate).status_code == 403
    assert client.post("/fx/rates", headers={**H, OWNER_TOKEN_HEADER: "mauvais-jeton-0000000000"}, json=rate).status_code == 403
    assert client.post("/fx/rates", headers=HO, json=rate).status_code == 200
    _, svc2 = boot(tmp_path)
    reference = svc2.fx_rates.reference("EUR", API_NOW)
    assert reference is not None and reference.rate_to_chf == D("0.9375") and reference.recorded_by == "propriétaire"


# =============================================================================== MOT-05 / MOT-06 signature


def test_mot05_agent_self_signed_mandate_is_inactive_without_vault_fingerprint() -> None:
    data = signed_data(lambda d: d["approval"].update(approved_by="agent-12-qa (pas la propriétaire)"))
    m = parse_mandate(data)  # empreinte recopiée dans le YAML, coffre vide
    assert m.inactive_reasons(NOW) == [R.MANDATE_NOT_SIGNED] and not m.is_signed and m.vault_missing
    d = check(req(), m, SpendLedger(), status(), treasury(), now=NOW)
    assert d.outcome is HUMAN and any("coffre" in msg for msg in d.messages)
    assert parse_mandate(data, expected_fingerprint=data["approval"]["fingerprint_sha256"]).is_active(NOW)
    blockers = load_settings({"POKESHOP_DRY_RUN": "false"}).real_write_blockers()
    assert any("POKESHOP_MANDATE_FINGERPRINT" in b for b in blockers)


def test_mot06_revocation_is_monotonic_even_if_revoked_at_is_erased() -> None:
    data = signed_data()
    vault = data["approval"]["fingerprint_sha256"]
    journal = InMemoryStateJournal(MandateRevocations.STREAM)
    book = MandateRevocations(store=journal)
    book.revoke(vault, at=NOW - timedelta(hours=1), actor="propriétaire", reason="révocation FICTIVE")
    restored = MandateRevocations.restore(journal)
    m = parse_mandate(data, expected_fingerprint=vault).with_revocations(restored.fingerprints())
    assert data["approval"]["revoked_at"] is None and R.MANDATE_REVOKED in m.inactive_reasons(NOW)
    resigned = signed_data(lambda d: d.update(mandate_version="mandat-v2-FICTIF"))
    fresh = parse_mandate(resigned, expected_fingerprint=resigned["approval"]["fingerprint_sha256"])
    assert fresh.with_revocations(restored.fingerprints()).is_active(NOW)  # nouvelle signature = nouvelle empreinte


def test_mot06_yaml_revocation_is_recorded_and_survives_its_erasure(tmp_path: Path) -> None:
    data = signed_data(lambda d: d["approval"].update(revoked_at="2026-11-01T08:00:00+01:00"))
    vault = data["approval"]["fingerprint_sha256"]
    path = tmp_path / "mandat.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    state = tmp_path / "etat"
    _, svc = boot(state, POKESHOP_MANDATE_PATH=str(path), POKESHOP_MANDATE_FINGERPRINT=vault)
    assert svc.mandate is not None and R.MANDATE_REVOKED in svc.mandate.inactive_reasons(API_NOW)
    data["approval"]["revoked_at"] = None  # un agent efface la ligne de révocation
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    client2, svc2 = boot(state, POKESHOP_MANDATE_PATH=str(path), POKESHOP_MANDATE_FINGERPRINT=vault)
    assert svc2.mandate is not None and not svc2.mandate.is_active(API_NOW)
    assert body(client2.get("/health"))["mandate_active"] is False


def test_mot06_revoke_route_is_protective_and_definitive(tmp_path: Path) -> None:
    client, svc = boot(tmp_path, mandate=api_mandate())
    assert svc.mandate.is_active(API_NOW)
    resp = client.post("/mandate/revoke", headers=HQA, json={"reason": "débit inconnu FICTIF"})
    assert resp.status_code == 200 and body(resp)["mandate_active"] is False
    assert svc.audit.events(action="mandate.revoke")
    _, svc2 = boot(tmp_path, mandate=None)
    assert api_mandate().fingerprint in svc2.revocations.fingerprints()


# =============================================================================== MOT-07 / SEC-05 rejeu


def test_mot07_replay_of_an_approval_is_rejected_during_a_global_freeze() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    request = req(idempotency_key="FICTIF-REPLAY-1")
    first = check(request, m, ledger, status(), treasury(), now=NOW)
    ledger.record(request, first)
    assert first.outcome is OK
    within_hour = check(request, m, ledger, status(as_of=NOW + timedelta(minutes=30)),
                        treasury(as_of=NOW + timedelta(minutes=30)), now=NOW + timedelta(minutes=30))  # fmt: skip
    assert within_hour.replayed and within_hour.outcome is OK
    later = NOW + timedelta(days=3)
    frozen = StopLossStatus(as_of=later, autonomy_level=1, global_frozen=True, purchases_and_ads_frozen=True)
    replay = check(request, m, ledger, frozen, treasury(as_of=later, cash_available_chf=D("100")), now=later)
    assert replay.replayed and replay.outcome is REJECTED
    assert {R.STOPLOSS_GLOBAL_FREEZE.value, R.REPLAY_NOT_PAYABLE.value} <= set(replay.reasons)
    assert ledger.record(request, replay) is ledger.get("FICTIF-REPLAY-1")  # aucune nouvelle dépense


def test_mot07_replay_after_execution_or_expiry_never_pays_twice() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    request = req(idempotency_key="FICTIF-REPLAY-2")
    ledger.record(request, check(request, m, ledger, status(), treasury(), now=NOW))
    late = NOW + timedelta(hours=2)
    stale = check(request, m, ledger, status(as_of=late), treasury(as_of=late), now=late)
    assert stale.outcome is REJECTED and stale.has(R.REPLAY_NOT_PAYABLE)
    ledger.mark_executed("FICTIF-REPLAY-2", at=NOW, amount_chf=D("100"), payment_ref="FICTIF-PP-R2")
    paid = check(request, m, ledger, status(), treasury(), now=NOW)
    assert paid.outcome is REJECTED and paid.reasons == (R.ALREADY_EXECUTED.value,)


def test_sec05_gate_replay_refused_under_cash_freeze_for_advertising() -> None:
    rig = Rig(level=3, mandate=signed_mandate_for_gate())
    ads = spend(amount="90", category=SpendCategory.ADVERTISING, supplier="FICTIF_PUB", key="FICTIF-ADS-1")
    first = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=ads)
    assert first.allowed and first.mandate_decision.outcome is OK
    rig.clock.now = NOW + timedelta(days=3)
    rig.state = gate_state(as_of=rig.clock.now, cash_available_chf=D("1000"))
    rig.paypal = rig.paypal.replace(as_of=rig.clock.now)
    rig.gate.invalidate()
    replay = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=ads)
    assert not replay.allowed and replay.mandate_decision.replayed
    assert replay.mandate_decision.outcome is REJECTED and replay.has(GateReason.MANDATE_REJECTED)
    assert replay.has(GateReason.STOPLOSS_CASH)  # SAMPLES et ADVERTISING comptent (CASH_FREEZE_CATEGORIES)
    assert {SpendCategory.ADVERTISING, SpendCategory.SAMPLES} <= CASH_FREEZE_CATEGORIES


def signed_mandate_for_gate():
    from test_autonomy import signed_mandate

    return signed_mandate()


def gate_state(**kw: Any) -> StopLossState:
    from test_autonomy import state

    at = kw.get("as_of", NOW)
    kw.setdefault("net_worth", NetWorthSnapshot(as_of=at, cash_chf=D("8000")))
    kw.setdefault("capital_movements", (CapitalMovement(movement_id="FICTIF_APPORT_1", at=at - timedelta(days=30),
                                                        kind="CONTRIBUTION", amount=D("8000")),))  # fmt: skip
    return state(**kw)


# =============================================================================== MOT-08 / SEC-04 trésorerie


def test_sec04_treasury_from_the_request_body_is_ignored(tmp_path: Path) -> None:
    """Réserve 1 600 : cash réel 1 700 (photo de l'agent finance) ; l'agent qui dépense déclare 100 000."""
    client, svc = boot(tmp_path, mandate=api_mandate())
    deposit(client, available="1700", paypal="5000")
    honest = {"as_of": API_NOW.isoformat(), "cash_available_chf": "1700", "paypal_balance_chf": "1700"}
    forged = {"as_of": API_NOW.isoformat(), "cash_available_chf": "100000", "paypal_balance_chf": "100000"}
    d1 = body(client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SEC04-1", treasury=honest)))
    d2 = body(client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SEC04-2", treasury=forged)))
    for d in (d1, d2):
        assert d["decision"]["outcome"] == "NEEDS_HUMAN_APPROVAL"
        assert "CASH_RESERVE_WOULD_BE_BREACHED" in d["decision"]["reasons"]
        assert d["treasury"]["cash_available_chf"] == "1700"
    assert svc.audit.events(action="mandate.check")[-1].payload["treasury_from_body_ignored"] is True


def test_mot08_self_declared_or_shared_token_figures_are_not_verifiable(tmp_path: Path) -> None:
    client, _ = boot(tmp_path, mandate=api_mandate())
    reading = {"as_of": API_NOW.isoformat(), "balance_chf": "5000", "source": "relevé PayPal FICTIF"}
    # Revue R3 : l'agent qui dépense ne dépose ni la photo ni le solde (matrice d'autorisations : 403).
    assert client.post("/stoploss/state", headers=HOPS, json=photo()).status_code == 403
    assert client.post("/treasury/paypal-balance", headers=HOPS, json=reading).status_code == 403
    deposit(client)  # photo du workflow 07 et solde du connecteur : vérifiables
    shared = client.post("/mandate/check", headers=H, json=spend_payload("FICTIF-SELF-2", "40"))
    assert shared.status_code == 403  # jeton commun : lecture et aperçus seulement
    relay = body(client.post("/mandate/check", headers=JR.HMANDAT, json=spend_payload("FICTIF-SELF-5", "40")))
    assert relay["decision"]["outcome"] == "NEEDS_HUMAN_APPROVAL" and "TREASURY_UNVERIFIED" in relay["decision"]["reasons"]
    ok = body(client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SELF-3", "40")))["decision"]
    assert ok["outcome"] == "APPROVED_WITHIN_MANDATE"
    # l'agent finance déclare les dettes : il ne demande jamais de dépense (revue R5, R4-DOC-11 : 403), et une demande
    # d'un autre agent reste vérifiable (déposant ≠ demandeur).
    statement = {"as_of": API_NOW.isoformat(), "preorders_collected_chf": "0", "source": "déclaration FICTIVE"}
    assert client.post("/treasury/balance-items", headers=HF, json=statement).status_code == 200
    own = client.post("/mandate/check", headers=HF, json=spend_payload("FICTIF-SELF-1", "40", requested_by="finance-pricing"))
    assert own.status_code == 403
    other = body(client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SELF-6", "40")))
    assert "Dettes et précommandes" not in other["unverified"]
    impostor = client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SELF-4", "40",
                                                                              requested_by="finance-pricing"))
    assert impostor.status_code == 403


def test_mot08_no_engine_treasury_means_human_approval() -> None:
    d = check(req(), signed(no_fees), SpendLedger(), status(), None, now=NOW)
    assert d.outcome is HUMAN and d.has(R.TREASURY_UNAVAILABLE) and d.has(R.PAYPAL_BALANCE_INSUFFICIENT)


def test_mot08_extension_exposure_comes_from_the_accepted_photo() -> None:
    state = StopLossState(as_of=NOW, stock_budget_chf=D("3000"), cash_available_chf=D("6000"),
                          capital_movements=(CapitalMovement(movement_id="A", at=NOW - timedelta(days=9),
                                                             kind="CONTRIBUTION", amount=D("8000")),),
                          net_worth=NetWorthSnapshot(as_of=NOW, cash_chf=D("8000")),
                          extensions=(ExtensionExposure(extension="FICTIF_EXT_A", stock_value_at_cost=D("700"),
                                                        on_order_value=D("40")),))  # fmt: skip
    snap = treasury_from_registers(state)
    assert snap is not None and snap.extension_exposure_chf == {"FICTIF_EXT_A": D("740")}
    snap = snap.replace(paypal_balance_chf=D("2000"))
    d = check(stock_req(amount=D("20")), signed(no_fees), SpendLedger(), status(), snap, now=NOW,
              proposals=proposals())  # fmt: skip
    assert d.has(R.ABOVE_EXTENSION_CAP) and d.context.extension_exposure_before_chf == D("740")


# =============================================================================== MOT-09 fraîcheur


def test_mot09_staleness_is_judged_on_the_photo_date_not_the_evaluation_time() -> None:
    old = NOW - timedelta(hours=2)
    st = StopLossStatus(as_of=NOW, state_as_of=old, autonomy_level=4)
    d = check(req(), signed(no_fees), SpendLedger(), st, treasury(), now=NOW)
    assert d.outcome is REJECTED and d.has(R.STALE_STOPLOSS_STATUS)
    rig = Rig(level=2, mandate=signed_mandate_for_gate(), st=gate_state(as_of=NOW - timedelta(hours=20)))
    status_, _ = rig.gate.stoploss_status()
    assert status_ is not None and status_.state_as_of == NOW - timedelta(hours=20) and status_.as_of == NOW
    decision = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=spend())
    assert decision.mandate_decision.has(R.STALE_STOPLOSS_STATUS)


# =============================================================================== MOT-12 / SEC-06 global


def test_sec06_photo_without_contribution_is_refused_and_spending_blocked(tmp_path: Path) -> None:
    client, svc = boot(tmp_path, mandate=api_mandate(), capital=False)  # aucun apport au registre de la propriétaire
    no_capital = client.post("/stoploss/state", headers=HO, json=photo("100"))
    assert no_capital.status_code == 409 and "aucun apport" in body(no_capital)["erreur"]
    assert svc.stoploss_state is None
    assert client.post("/mandate/check", headers=HOPS, json=spend_payload("FICTIF-SL-1", "40")).status_code == 503
    gate = svc.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert gate.has(GateReason.STOPLOSS_UNAVAILABLE)


def test_mot12_omitted_contributions_are_refused_until_owner_reset(tmp_path: Path) -> None:
    client, svc = boot(tmp_path, capital=False)
    for movement_id, days, amount in (("FICTIF_A1", 30, "8000"), ("FICTIF_A2", 2, "2000")):
        apport = {"movement_id": movement_id, "at": (API_NOW - timedelta(days=days)).isoformat(),
                  "kind": "CONTRIBUTION", "amount": amount}  # fmt: skip
        assert client.post("/capital/movements", headers=HO, json=apport).status_code == 201
    assert client.post("/stoploss/state", headers=HO, json=photo()).status_code == 200
    assert svc.stoploss_engine.latch.contributions_seen_chf == D("10000")
    # SEC-06 : une photo ne déclare jamais de mouvements de capital (apport omis ou faux retrait) : 422.
    declared = client.post("/stoploss/state", headers=HO, json=photo("6000", capital_movements=[OWNER_APPORT]))
    assert declared.status_code == 422 and body(declared)["previous_photo_kept"] is True
    # Registre des apports restauré d'une sauvegarde plus ancienne (apport de 2 000 perdu) : perte masquée => refus.
    journal = tmp_path / "capital_movements.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8").splitlines(keepends=True)[0], encoding="utf-8")
    client_b, _ = boot(tmp_path, capital=False)
    omitted = client_b.post("/stoploss/state", headers=HO, json=photo("6000"))
    assert omitted.status_code == 409 and body(omitted)["previous_photo_kept"] is True
    _, svc2 = boot(tmp_path, capital=False)  # la mémoire des apports survit au redémarrage
    assert svc2.stoploss_engine.latch.contributions_seen_chf == D("10000")
    client2 = TestClient(create_app(services=svc2))
    refused = client2.post("/stoploss/capital-memory/reset", headers=H, json={"reason": "apport erroné FICTIF corrigé"})
    assert refused.status_code == 403
    reset = client2.post("/stoploss/capital-memory/reset", headers=HO, json={"reason": "apport erroné FICTIF corrigé"})
    assert reset.status_code == 200 and svc2.stoploss_engine.latch.contributions_seen_chf is None
    assert client2.post("/stoploss/state", headers=HO, json=photo("8000")).status_code == 200
    assert svc2.stoploss_engine.latch.contributions_seen_chf == D("8000")


def test_mot12_point_zero_remembers_contributions() -> None:
    engine = StopLossEngine(load_stoploss_config(), owner_token_sha256=hash_owner_token(OWNER_TOKEN))
    state = gate_state()
    engine.set_baseline(OWNER_TOKEN, "J3 : point zéro FICTIF", now=NOW, state=state, reference_chf=D("4200"))
    assert engine.latch.baseline.contributions_total_chf == D("8000")
    with pytest.raises(StopLossError, match="point zéro"):
        engine.validate_photo(state.replace(capital_movements=()), NOW)


# =============================================================================== MOT-13 plafonds


def test_mot13_ads_cap_and_stock_budget_never_come_from_the_photo(tmp_path: Path) -> None:
    client, svc = boot(tmp_path)  # mandat non signé : aucun plafond pub délégué
    today = API_NOW.date().isoformat()
    orders = [{"order_id": f"FICTIF-O{i}", "campaign_id": "C", "paid_at": API_NOW.isoformat(),
               "contribution_before_acquisition": "200"} for i in range(5)]  # fmt: skip
    posted = photo(ads_daily_cap_chf="1000", ad_spends=[{"campaign_id": "C", "day": today, "amount": "500"}],
                   attributed_orders=orders, stock_budget_chf="100000",
                   extensions=[{"extension": "FICTIF_EXT", "stock_value_at_cost": "3000",
                                "last_sale_at": API_NOW.isoformat()}])  # fmt: skip
    data = body(client.post("/stoploss/state", headers=HO, json=posted))
    assert any("plafond jour pub" in n for n in data["overridden"]) and any("budget stock" in n for n in data["overridden"])
    assert data["status"]["ads_globally_cut"] is True
    assert "FICTIF_EXT" in data["status"]["no_reorder_extensions"]
    assert svc.stoploss_state.ads_daily_cap_chf is None and svc.stoploss_state.stock_budget_chf == D("3000")
    svc.mandate = api_mandate()  # mandat signé actif : plafond pub = celui du mandat (33)
    data = body(client.post("/stoploss/state", headers=HO, json=posted))
    assert svc.stoploss_state.ads_daily_cap_chf == D("33") and data["status"]["ads_globally_cut"] is True


# =============================================================================== MOT-21 / MOT-22 achats de stock


def test_mot21_justification_must_be_a_registered_engine_proposal() -> None:
    m = signed(no_fees)
    free = check(stock_req(justification_ref="n-importe-quoi"), m, SpendLedger(), status(), treasury(), now=NOW,
                 proposals=proposals())  # fmt: skip
    assert free.outcome is HUMAN and free.has(R.NO_ENGINE_PROPOSAL)
    assert check(stock_req(), m, SpendLedger(), status(), treasury(), now=NOW, proposals=None).has(R.NO_ENGINE_PROPOSAL)
    stale = proposals(proposal(generated_at=NOW - timedelta(hours=25)))
    assert check(stock_req(), m, SpendLedger(), status(), treasury(), now=NOW, proposals=stale).has(R.NO_ENGINE_PROPOSAL)
    other = check(stock_req(product_key="FICTIF_AUTRE"), m, SpendLedger(), status(), treasury(), now=NOW,
                  proposals=proposals())  # fmt: skip
    assert other.has(R.NO_ENGINE_PROPOSAL)
    small = proposals(proposal(line_cost="250"))
    ledger = SpendLedger()
    first = stock_req(amount=D("200"), idempotency_key="FICTIF-PROP-1")
    d1 = check(first, m, ledger, status(), treasury(), now=NOW, proposals=small)
    assert d1.outcome is OK
    ledger.record(first, d1)
    second = stock_req(amount=D("60"), idempotency_key="FICTIF-PROP-2")
    d2 = check(second, m, ledger, status(), treasury(), now=NOW, proposals=small)
    assert d2.has(R.NO_ENGINE_PROPOSAL)  # 200 déjà engagés + 60 > ligne de 250 : proposition consommée


def test_mot21_reorder_route_registers_the_proposal(tmp_path: Path) -> None:
    client, svc = boot(tmp_path)
    cand = {"product_key": "FICTIF-P1", "extension": "FICTIF_ALPHA", "unit_cost_chf": "90.00", "sellable_qty": 0,
            "avg_daily_sales": "0.5", "lead_time_days": 7, "safety_stock": 1,
            "offer": {"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-A-001", "availability_status": "IN_STOCK",
                      "available_qty": 24, "moq": 1, "carton_qty": 1, "source_ts": API_NOW.isoformat(),
                      "raw_ref": "FICTIF:1"}}  # fmt: skip
    # F3 (MOT-24) : une proposition exige un état du stop-loss connu (photo acceptée), sinon 409.
    assert client.post("/stoploss/state", headers=HO, json=photo()).status_code == 200
    data = body(client.post("/stock/reorder-proposal", headers=HF, json={"candidates": [cand], "budget_available": "5000"}))
    ref = data["justification_ref"]
    assert data["registered"] is True and svc.proposals.get(ref) is not None
    _, svc2 = boot(tmp_path)
    assert svc2.proposals.get(ref) is not None


def test_mot22_accessory_with_extension_is_checked_as_sealed_stock() -> None:
    m = signed(no_fees)
    snap = treasury(extension_exposure_chf={"FICTIF_EXT_A": D("740")})
    disguised = stock_req(category=SpendCategory.ACCESSORIES, product_language="JP", amount=D("200"))
    d = check(disguised, m, SpendLedger(), status(), snap, now=NOW, proposals=proposals())
    assert d.outcome is REJECTED
    assert {R.NON_FR_PRODUCT.value, R.ABOVE_EXTENSION_CAP.value, R.CATEGORY_IDENTITY_MISMATCH.value} <= set(d.reasons)
    jp_sleeves = stock_req(category=SpendCategory.ACCESSORIES, extension=None, product_language="JP")
    assert check(jp_sleeves, m, SpendLedger(), status(), snap, now=NOW, proposals=proposals()).has(R.NON_FR_PRODUCT)
    sleeves = stock_req(category=SpendCategory.ACCESSORIES, extension=None, product_language="NA")
    assert check(sleeves, m, SpendLedger(), status(), snap, now=NOW, proposals=proposals()).outcome is OK
    sealed_na = check(stock_req(product_language="NA"), m, SpendLedger(), status(), treasury(), now=NOW,
                      proposals=proposals())  # fmt: skip
    assert sealed_na.outcome is REJECTED and sealed_na.has(R.NON_FR_PRODUCT)  # un scellé a toujours une langue
    sample_na = req(category=SpendCategory.SAMPLES, supplier_id="FICTIF_GROSSISTE", product_language="NA")
    assert check(sample_na, m, SpendLedger(), status(), treasury(), now=NOW).has(R.NON_FR_PRODUCT)


# =============================================================================== MOT-26 exécution


def test_mot26_overpayment_is_recorded_but_raises_an_alert() -> None:
    m = signed()
    ledger = SpendLedger()
    request = req(amount=D("40"), idempotency_key="FICTIF-OVER-1")
    decision = check(request, m, ledger, status(), treasury(), now=NOW)
    ledger.record(request, decision)
    assert decision.effective_cost_chf == D("41.91")
    entry = ledger.mark_executed("FICTIF-OVER-1", at=NOW, amount_chf=D("3760.00"), payment_ref="FICTIF-PP-OVER")
    assert entry.execution_alert is not None and ledger.events()[-1].kind == "RECONCILIATION_ALERT"
    report = ledger.reconcile([StatementLine(source="PAYPAL", transaction_id="FICTIF-PP-OVER", booked_on=NOW.date(),
                                             amount_chf=D("3760.00"))], at=NOW)  # fmt: skip
    assert [ln.status for ln in report.lines] == ["AMOUNT_ABOVE_APPROVAL"] and len(report.alerts) == 1
    other = SpendLedger()
    small = req(amount=D("40"), idempotency_key="FICTIF-OVER-2")
    other.record(small, check(small, m, other, status(), treasury(), now=NOW))
    within = other.mark_executed("FICTIF-OVER-2", at=NOW, amount_chf=D("43.74"), payment_ref="FICTIF-PP-OK")
    assert within.execution_alert is None  # 41,91 × 1,02 + 1 = 43,75 : dans la tolérance


# =============================================================================== CON-01 / COH-02 seuils signés


def tampered_stoploss(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    data = yaml.safe_load(DEFAULT_STOPLOSS_PATH.read_text(encoding="utf-8"))
    data["global"]["max_loss_share_of_capital"] = "0.95"
    data["extension"]["max_days_without_sale"] = 365
    data["cash"]["reserve_chf"] = "0"
    data["product"]["min_contribution_pct"] = "0.01"
    path = tmp_path / "stoploss_tampered.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path, data


def test_con01_unsigned_relaxation_falls_back_to_the_strictest_threshold(tmp_path: Path) -> None:
    path, data = tampered_stoploss(tmp_path)
    config = load_stoploss_config(path)
    assert config.signature == "UNSIGNED_STRICTEST"
    assert config.global_.max_loss_share_of_capital == D("0.20") and config.extension.max_days_without_sale == 45
    assert config.cash.reserve_chf == D("1600") and config.product.min_contribution_pct == D("0.12")
    assert len(config.tightened) == 4
    stricter = copy.deepcopy(data)
    stricter["global"]["max_loss_share_of_capital"] = "0.10"  # durcir sans signature : permis
    assert enforce_signature(parse_stoploss_config(stricter), None).global_.max_loss_share_of_capital == D("0.10")
    assert REFERENCE_THRESHOLDS["global"]["max_loss_share_of_capital"] == D("0.20")


def test_con01_vault_fingerprint_mismatch_refuses_the_config_and_signed_values_apply(tmp_path: Path) -> None:
    path, data = tampered_stoploss(tmp_path)
    original = yaml.safe_load(DEFAULT_STOPLOSS_PATH.read_text(encoding="utf-8"))
    with pytest.raises(StopLossError, match="sans signature"):
        load_stoploss_config(path, expected_fingerprint=stoploss_fingerprint(original))
    signed_cfg = load_stoploss_config(path, expected_fingerprint=stoploss_fingerprint(data))
    assert signed_cfg.signature == "SIGNED" and signed_cfg.global_.max_loss_share_of_capital == D("0.95")


def test_coh02_api_freezes_on_unsigned_stoploss_change_with_vault(tmp_path: Path) -> None:
    path, _ = tampered_stoploss(tmp_path)
    original = yaml.safe_load(DEFAULT_STOPLOSS_PATH.read_text(encoding="utf-8"))
    client, svc = boot(tmp_path / "etat", POKESHOP_STOPLOSS_PATH=str(path),
                       POKESHOP_STOPLOSS_FINGERPRINT=stoploss_fingerprint(original))  # fmt: skip
    assert svc.stoploss_engine is None and "stoploss" in body(client.get("/health"))["load_errors"]
    assert client.get("/stoploss/status", headers=H).status_code == 503
    assert svc.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False).has(GateReason.STOPLOSS_UNAVAILABLE)
    _, unsigned = boot(tmp_path / "etat2", POKESHOP_STOPLOSS_PATH=str(path))
    assert unsigned.stoploss_config.global_.max_loss_share_of_capital == D("0.20")
    assert unsigned.signatures["stoploss"] == "UNSIGNED_STRICTEST"


def test_coh02_price_rules_are_signed_or_strictest(tmp_path: Path) -> None:
    rules_data = yaml.safe_load((DEFAULT_STOPLOSS_PATH.parent / "pricing_rules.v1.yaml").read_text(encoding="utf-8"))
    rules_data["pricing"]["hard_floor_margin"] = "0.01"
    rules_data["pricing"]["max_daily_price_change"] = "0.50"
    rules_data["stock"]["extension_budget_cap"] = "1"
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(rules_data, allow_unicode=True), encoding="utf-8")
    pricing, stock, tightened = strictest_price_rules(load_rules(path).pricing, load_rules(path).stock)
    assert pricing.hard_floor_margin == D("0.12") and pricing.max_daily_price_change == D("0.05")
    assert stock.extension_budget_cap == D("0.25") and len(tightened) == 3
    _, svc = boot(tmp_path / "etat", POKESHOP_RULES_PATH=str(path))
    assert svc.rules.pricing.hard_floor_margin == D("0.12") and svc.signatures["rules"] == "UNSIGNED_STRICTEST"
    assert not svc.stoploss_engine.frozen
    client, svc2 = boot(tmp_path / "etat2", POKESHOP_RULES_PATH=str(path),
                        POKESHOP_RULES_FINGERPRINT=load_rules().content_sha256)  # fmt: skip
    assert svc2.stoploss_engine.frozen and svc2.stoploss_engine.latch.cause == "CONFIG_UNSIGNED"
    assert "rules" in body(client.get("/health"))["load_errors"]
    rearm = client.post("/stoploss/rearm", headers=HO, json={"reason": "tentative de levée FICTIVE", "rebase": False})
    assert rearm.status_code == 503  # aucun réarmement : signer ou corriger puis redémarrer
    _, signed_svc = boot(tmp_path / "etat3", POKESHOP_RULES_PATH=str(path),
                         POKESHOP_RULES_FINGERPRINT=load_rules(path).content_sha256)  # fmt: skip
    assert signed_svc.signatures["rules"] == "SIGNED" and signed_svc.rules.pricing.hard_floor_margin == D("0.01")


def test_coh02_consistency_covers_projection_and_stock_budget() -> None:
    config = load_stoploss_config()
    rules = load_rules()
    assert consistency_errors(config, stock=rules.stock, mandate_stock_budget=D("3000")) == []
    errors = consistency_errors(config.replace(global_=config.global_.replace(max_loss_share_of_capital=D("0.30"))),
                                stock=rules.stock, mandate_stock_budget=D("2500"))  # fmt: skip
    assert len(errors) == 2


# =============================================================================== COH-01 définition unique


def test_coh01_single_global_stoploss_definition_in_docs_and_projection() -> None:
    assert fc.global_stoploss_threshold() == D("840.00")
    pilot = fc.ScenarioAssumptions("pilote_validation", 15, D(8))
    weeks = fc.project_north_star(pilot, weeks=104, opening_week=5)
    aligned = fc.north_star(weeks, capital_engaged=fc.BP_STOPLOSS_REFERENCE)
    assert aligned.max_cumulative_loss == D("840.00") and aligned.first_global_stoploss_week == 13
    root = Path(__file__).resolve().parents[1] / "docs" / "00-pilotage"
    stop_loss = (root / "STOP_LOSS.md").read_text(encoding="utf-8")
    north = (root / "ETOILE_POLAIRE.md").read_text(encoding="utf-8")
    assert "définition unique" in stop_loss and "**840 CHF**" in stop_loss and "J3, avec la décision de budget (C03)" in stop_loss
    assert "J1, avec la décision de budget" not in stop_loss
    assert "840 CHF" in north and "option A" in north and "à l'ouverture (`docs" not in north


# =============================================================================== MOT-23 / SEC-17 / E2E-09


def test_mot23_historical_cost_label_is_not_declarable() -> None:
    ns = NorthStarLedger()
    forged = ContributionEntry(entry_id="x", at=NOW, post=Post.HISTORICAL_COST, amount=D("-500.00"),
                               source=COST_LEDGER_SOURCE, ref="avoir inventé")  # fmt: skip
    with pytest.raises(NorthStarError, match="registre de coûts"):
        ns.record(forged)
    with pytest.raises(NorthStarError):
        ns.record(ContributionEntry(entry_id="y", at=NOW, post=Post.NET_SALES, amount=D("10"), source=COST_LEDGER_SOURCE))
    valid = ContributionEntry(entry_id="e1", at=NOW, post=Post.NET_SALES, amount=D("10.00"))
    with pytest.raises(NorthStarError):
        ns.add_entries([valid, forged])
    assert ns.entries() == ()  # lot atomique


def test_sec17_api_refuses_forged_costs_and_batches_are_atomic(tmp_path: Path) -> None:
    client, svc = boot(tmp_path)
    forged = [{"entry_id": "fake-1", "at": API_NOW.isoformat(), "post": "NET_SALES", "amount": "10.00"},
              {"entry_id": "fake-2", "at": API_NOW.isoformat(), "post": "HISTORICAL_COST", "amount": "-50000.00",
               "source": "HistoricalCostLedger"}]  # fmt: skip
    assert client.post("/northstar/entries", headers=H, json={"entries": forged}).status_code == 403  # jeton commun
    resp = client.post("/northstar/entries", headers=HF, json={"entries": forged})
    assert resp.status_code == 422 and svc.northstar.entries() == ()
    assert body(client.get("/northstar", headers=H))["cumulative"] == "0.00"


def test_e2e09_cost_register_is_the_only_cost_source_and_returns_use_the_sale_cost() -> None:
    ns = NorthStarLedger()
    costs = CostRegister(ns, store=InMemoryStateJournal(CostRegister.STREAM))
    costs.apply(CostMovement(kind="RECEIPT", product_key="P", at=NOW, ref="L1", qty=2, unit_cost=D("140")))
    with pytest.raises(NorthStarError, match="CMP"):
        costs.apply(CostMovement(kind="ISSUE", product_key="P", at=NOW, ref="O1", qty=1, unit_cost=D("1")))
    costs.apply(CostMovement(kind="ISSUE", product_key="P", at=NOW, ref="O1", qty=1))
    assert ns.totals().historical_cost == D("140.00")
    with pytest.raises(NorthStarError, match="coût repris"):
        costs.apply(CostMovement(kind="RETURN", product_key="P", at=NOW, ref="R1", qty=1, sale_ref="O1",
                                 unit_cost=D("1000")))  # fmt: skip
    costs.apply(CostMovement(kind="RETURN", product_key="P", at=NOW, ref="R1", qty=1, sale_ref="O1"))
    assert ns.totals().historical_cost == D("0.00")
    with pytest.raises(NorthStarError, match="vendues"):
        costs.apply(CostMovement(kind="RETURN", product_key="P", at=NOW, ref="R2", qty=1, sale_ref="O1"))


# =============================================================================== SEC-16 jetons nommés


def test_sec16_named_tokens_derive_the_actor_and_owner_cannot_be_impersonated(tmp_path: Path) -> None:
    client, svc = boot(tmp_path)
    inc = body(client.post("/incidents", headers=HOPS, json={"code": "INC-05", "product_key": "FICTIF-P1",
                                                             "cause": "Marge 4 % sous le plancher dur",
                                                             "actor": "propriétaire"}))["incident"]  # fmt: skip
    assert inc["opened_by"] == "operations-sav"  # acteur déduit du jeton, jamais déclaré
    shared = client.post("/stoploss/freeze", headers=H, json={"actor": "Propriétaire", "reason": "usurpation FICTIVE"})
    assert shared.status_code == 403
    run = body(client.post("/sync/run", headers=HSYNC, json={"supplier": "fictif_grossiste_a",
                                                           "source_path": "FICTIF_offres_grossiste_a.csv",
                                                           "catalog": [{"product_id": "FICTIF-P1", "listing": {
                                                               "product_key": "FICTIF-P1", "public_sku": "DSP-FICTIF_ALPHA-FR",
                                                               "identity": {"gtin": "2000000001012", "language": "FR",
                                                                            "extension": "FICTIF_ALPHA", "format": "DISPLAY",
                                                                            "content": "36 BOOSTERS", "sealed": True},
                                                               "fictif": True}}]}))  # E2E-07 : catalogue requis
    self_test = client.post(f"/incidents/{inc['incident_id']}/test", headers=HOPS,
                            json={"test_ref": run["report"]["run_id"], "passed": True, "actor": "x1"})
    assert self_test.status_code == 403 and "qa-conformite" in body(self_test)["erreur"]  # liste fermée d'attestants
    qa_inc = body(client.post("/incidents", headers=HQA, json={"code": "INC-05", "product_key": "FICTIF-P2",
                                                               "cause": "Marge FICTIVE sous le plancher"}))["incident"]
    own = client.post(f"/incidents/{qa_inc['incident_id']}/test", headers=HQA,
                      json={"test_ref": run["report"]["run_id"], "passed": True, "actor": "x1"})
    assert own.status_code == 403 and "auto-attesté" in body(own)["erreur"]
    # NEW-01 : le flux FICTIF du 4.10 est périmé au 10.11 => cycle non PROPRE, il ne prouve pas la correction.
    assert run["cycle_status"] != "PROPRE"
    weak = client.post(f"/incidents/{inc['incident_id']}/test", headers=HQA,
                       json={"test_ref": run["report"]["run_id"], "passed": True, "actor": "x1"})
    assert weak.status_code == 409 and "PROPRE" in body(weak)["erreur"]
    owner_test = client.post(f"/incidents/{inc['incident_id']}/test", headers=HO,
                             json={"test_ref": "contrôle manuel FICTIF", "passed": True, "actor": "x1"})
    assert owner_test.status_code == 200 and body(owner_test)["incident"]["test_passed"] is True
    resumed = body(client.post(f"/incidents/{inc['incident_id']}/resume", headers=HQA, json={"actor": "propriétaire"}))
    assert resumed["incident"]["resolved_by"] == "agent:qa-conformite"
    resume_events = svc.audit.events(action="incident.resume")
    assert resume_events and all(e.actor != "propriétaire" for e in resume_events)


def test_sec16_named_token_settings_are_validated() -> None:
    good = load_settings({"POKESHOP_AGENT_TOKENS_SHA256": f"finance-pricing:{'a' * 64}"})
    assert good.agent_tokens_sha256 == {"finance-pricing": "a" * 64}
    for bad in (f"proprietaire:{'a' * 64}", f"owner-1:{'a' * 64}", "finance-pricing:xyz", f"a:{'a' * 64}",
                f"finance-pricing:{'a' * 64},qa-conformite:{'a' * 64}", "sans-separateur",
                f"agent-05-finance:{'a' * 64}"):  # revue R3 : nom inconnu de la matrice d'autorisations
        with pytest.raises(SettingsError):
            load_settings({"POKESHOP_AGENT_TOKENS_SHA256": bad})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_API_TOKEN_SHA256": "b" * 64, "POKESHOP_AGENT_TOKENS_SHA256": f"qa-conformite:{'b' * 64}"})
    with pytest.raises(SettingsError, match="double"):  # un rôle défini deux fois (liste et variable par rôle)
        load_settings({"POKESHOP_AGENT_TOKENS_SHA256": f"qa-conformite:{'a' * 64}",
                       "POKESHOP_ROLE_TOKEN_SHA256_QA_CONFORMITE": "c" * 64})


# =============================================================================== COH-03 enveloppes


def test_coh03_accessories_are_part_of_the_stock_budget() -> None:
    assert D(ENVELOPES["STOCK"]) + D(ENVELOPES["ACCESSORIES"]) == D("3000")
    with pytest.raises(MandateError, match="budget stock"):
        signed(lambda d: d["categories"]["STOCK"].update(envelope_chf="3000"))
    template = yaml.safe_load(DEFAULT_MANDATE_PATH.read_text(encoding="utf-8"))
    raw = DEFAULT_MANDATE_PATH.read_text(encoding="utf-8")
    assert 'proposé : "2700"' in raw and "HORS BP §3" in raw and set(template["categories"]) >= {"SAMPLES", "SHIPPING"}
    doc = (Path(__file__).resolve().parents[1] / "docs" / "00-pilotage" / "DELEGATION_AUTONOMIE.md").read_text(
        encoding="utf-8"
    )
    assert "| `STOCK` | 2 700 CHF |" in doc and "**Hors BP §3**" in doc and "**5 700 CHF**" in doc
    assert mandate_fingerprint(template)  # gabarit toujours lisible


def test_payment_method_still_restricted_after_changes() -> None:
    d = check(req(payment_method=PaymentMethod.CARD), signed(no_fees), SpendLedger(), status(), treasury(), now=NOW)
    assert d.outcome is REJECTED and d.has(R.PAYMENT_METHOD_FORBIDDEN)
    assert isinstance(treasury(), TreasurySnapshot)
    assert ReorderCandidate and SupplierOffer  # modèles du réassort toujours exportés


# =============================================================================== registres en base (migration 004)


def test_f2_registries_survive_restart_in_postgres(pg: dict[str, Any], tmp_path: Path) -> None:  # noqa: F811
    """Révocations, taux de référence, propositions et registre de coûts : journal d'état en base, relu au démarrage."""
    cfg = settings(tmp_path)

    def start() -> tuple[TestClient, Services]:
        svc = Services.build(cfg, clock=lambda: API_NOW, notifier=LogNotifier(), connect=pg["engine"])
        return TestClient(create_app(services=svc)), svc

    client, svc = start()
    svc.mandate = api_mandate()
    rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": API_NOW.date().isoformat(), "source": "BNS FICTIF"}
    assert client.post("/fx/rates", headers=HO, json=rate).status_code == 200
    assert client.post("/mandate/revoke", headers=HQA, json={"reason": "débit inconnu FICTIF"}).status_code == 200
    # Revue R3 : la réception au coût cite la réception physique déclarée par un autre jeton (operations-sav).
    listing = {"product_key": "FICTIF-P1", "public_sku": "DSP-FICTIF_ALPHA-FR", "fictif": True,
               "identity": {"gtin": "2000000001012", "language": "FR", "extension": "FICTIF_ALPHA", "format": "DISPLAY",
                            "content": "36 BOOSTERS", "sealed": True}}
    assert client.post("/catalog/items", headers=HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": listing}]}).status_code == 200
    approval = {"product_id": "FICTIF-P1", "approved": True, "reason": "fiche FICTIVE relue par la propriétaire"}
    assert client.post("/catalog/approvals", headers=HO, json=approval).status_code == 201
    assert client.post("/stock/receive", headers=HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 1,
                                                             "ref": "FICTIF-BL-1"}).status_code == 200
    # Revue R4 : facture enregistrée (workflow 03) = référence du coût de réception ; commande avec lignes.
    invoice = {"invoice_ref": "FICTIF-FACT-1", "supplier_id": "fictif_grossiste_a", "issued_at": API_NOW.isoformat(),
               "total_chf": "140.00", "lines": [{"product_key": "FICTIF-P1", "qty": 1, "unit_cost_chf": "140.00"}],
               "source": "facture FICTIVE validée par la propriétaire"}
    assert client.post("/costs/invoices", headers=JR.headers("n8n-03-factures"), json=invoice).status_code == 201
    lot = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": API_NOW.isoformat(), "ref": "FICTIF-LOT-1", "qty": 1,
           "unit_cost": "140.00", "stock_ref": "FICTIF-BL-1", "invoice_ref": "FICTIF-FACT-1"}
    assert client.post("/costs/movements", headers=HF, json=lot).status_code == 200
    order = {"order_id": "FICTIF-O1", "paid_at": API_NOW.isoformat(), "net_sales_ht": "184.92", "payment_fees": "5.30",
             "shipping_cost_actual": "3.00", "shipping_label_ref": "FICTIF-ETIQ-1", "source": "Shopify FICTIF",
             "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=order).status_code == 201
    cand = {"product_key": "FICTIF-P1", "extension": "FICTIF_ALPHA", "unit_cost_chf": "90.00", "sellable_qty": 0,
            "avg_daily_sales": "0.5", "lead_time_days": 7, "safety_stock": 1,
            "offer": {"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-A-001", "availability_status": "IN_STOCK",
                      "available_qty": 24, "moq": 1, "carton_qty": 1, "source_ts": API_NOW.isoformat(),
                      "raw_ref": "FICTIF:1"}}  # fmt: skip
    assert client.post("/capital/movements", headers=HO, json=OWNER_APPORT).status_code == 201  # SEC-06
    assert client.post("/stoploss/state", headers=HO, json=photo()).status_code == 200  # F3 (MOT-24)
    ref = body(client.post("/stock/reorder-proposal", headers=HF,
                           json={"candidates": [cand], "budget_available": "5000"}))["justification_ref"]
    _, svc2 = start()
    assert svc2.proposals.get(ref) is not None
    assert svc2.restore_errors == {} and svc2.fx_rates.reference("EUR", API_NOW) is not None
    assert api_mandate().fingerprint in svc2.revocations.fingerprints()
    assert svc2.costs.ledger("FICTIF-P1").qty_on_hand == 0  # sortie dérivée de la commande (revue R4)
    assert svc2.invoices.get("FICTIF-FACT-1") is not None and svc2.invoices.unpaid_total() == D("140.00")
    assert svc2.stock.receipt("DSP-FICTIF_ALPHA-FR", "FICTIF-BL-1") == (1, "operations-sav")  # acteur persisté
    assert svc2.catalog_approvals.get("FICTIF-P1").approved and svc2.orders.get("FICTIF-O1") is not None
