"""Tests du mandat de dépense : chaque règle, idempotence, mandat non signé, frais PayPal, registre.

Bénéficiaires, montants et références FICTIFS (préfixe FICTIF_) ; aucun n'est un fournisseur validé.
"""

from __future__ import annotations

import copy
import csv
import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from pokeshop.mandate import (
    CASH_FREEZE_CATEGORIES,
    DEFAULT_MANDATE_PATH,
    EngineProposalBook,
    FORBIDDEN_CATEGORIES,
    MANDATE_ENV_VAR,
    MANDATE_FINGERPRINT_ENV_VAR,
    REASON_OUTCOME,
    REGISTRY_COLUMNS,
    SPEND_REASON_LABELS_FR,
    IdempotencyConflictError,
    Mandate,
    MandateError,
    MandateOutcome,
    PaymentMethod,
    PayPalCostModel,
    SpendCategory,
    SpendLedger,
    SpendReason,
    SpendRequest,
    SpendStatus,
    StatementLine,
    TreasurySnapshot,
    check,
    load_mandate,
    main,
    mandate_fingerprint,
    parse_mandate,
    paypal_cost,
    validate_mandate_data,
)
from pokeshop.models import ReorderLine, ReorderProposal
from pokeshop.stoploss import StopLossStatus, load_stoploss_config
from pokeshop.treasury import CASH_STOPLOSS_RESERVE
from pydantic import ValidationError

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)
REPO = Path(__file__).resolve().parents[1]
TEMPLATE = yaml.safe_load(DEFAULT_MANDATE_PATH.read_text(encoding="utf-8"))
R = SpendReason
OK = MandateOutcome.APPROVED_WITHIN_MANDATE
HUMAN = MandateOutcome.NEEDS_HUMAN_APPROVAL
REJECTED = MandateOutcome.REJECTED

SUPPLIERS = [
    {
        "supplier_id": "FICTIF_EMBALLAGES",
        "label": "Emballages (fictif)",
        "categories": ["PACKAGING", "SHIPPING"],
        "payment_methods": ["PAYPAL"],
        "validated_on": "2026-10-10",
        "due_diligence_ref": "checklist FICTIF_EMBALLAGES",
        "payee_ref": "coffre:beneficiaires/FICTIF_EMBALLAGES",
    },
    {
        "supplier_id": "FICTIF_GROSSISTE",
        "label": "Grossiste FR (fictif)",
        "categories": ["STOCK", "ACCESSORIES", "SAMPLES"],
        "payment_methods": ["PAYPAL", "BANK_TRANSFER"],
        "validated_on": "2026-10-10",
        "due_diligence_ref": "checklist FICTIF_GROSSISTE",
        "payee_ref": "coffre:beneficiaires/FICTIF_GROSSISTE",
    },
    {
        "supplier_id": "FICTIF_PUB",
        "label": "Plateforme publicitaire (fictif)",
        "categories": ["ADVERTISING"],
        "payment_methods": ["PAYPAL"],
        "max_per_transaction_chf": "100",
        "validated_on": "2026-10-10",
        "due_diligence_ref": "checklist FICTIF_PUB",
        "payee_ref": "coffre:beneficiaires/FICTIF_PUB",
    },
]
ENVELOPES = {
    "STOCK": "2700",  # COH-03 : STOCK + ACCESSORIES = budget stock (3 000, BP §3)
    "ACCESSORIES": "300",
    "SAMPLES": "100",
    "SITE_TOOLS": "1500",
    "DA_CONTENT": "400",
    "PACKAGING": "300",
    "SHIPPING": "600",
    "ADVERTISING": "500",
}
NO_FEES = {"fee_pct": "0", "fee_fixed_chf": "0", "fx_conversion_pct": "0", "flag_above_pct": "0"}


def signed_data(mutate: Callable[[dict], None] | None = None, *, sign: bool = True) -> dict:
    d = copy.deepcopy(TEMPLATE)
    d["valid_from"] = "2026-10-10"
    d["valid_until"] = "2027-01-31"
    d["limits"].update(
        per_transaction_chf="500", per_month_chf="3000", stock_budget_chf="3000", ads_daily_cap_chf="33",
        email_daily_send_quota=20,
    )  # fmt: skip
    for name, value in ENVELOPES.items():
        d["categories"][name]["envelope_chf"] = value
    d["suppliers"] = copy.deepcopy(SUPPLIERS)
    d["approval"] = {
        "approved_by": "FICTIF Propriétaire",
        "approved_at": "2026-10-10T09:00:00+02:00",
        "fingerprint_sha256": None,
        "revoked_at": None,
    }
    if mutate:
        mutate(d)
    if sign:
        d["approval"]["fingerprint_sha256"] = mandate_fingerprint(d)
    return d


def signed(mutate: Callable[[dict], None] | None = None, **kw) -> Mandate:
    """Mandat signé ET dont l'empreinte est au coffre (sauf ``expected_fingerprint`` explicite)."""
    data = signed_data(mutate)
    kw.setdefault("expected_fingerprint", data["approval"]["fingerprint_sha256"])
    return parse_mandate(data, **kw)


def no_fees(d: dict) -> None:
    d["paypal"].update(NO_FEES)


def template() -> Mandate:
    return parse_mandate(copy.deepcopy(TEMPLATE))


def req(**kw) -> SpendRequest:
    base = dict(
        amount=D("100"),
        currency="CHF",
        supplier_id="FICTIF_EMBALLAGES",
        category=SpendCategory.PACKAGING,
        payment_method=PaymentMethod.PAYPAL,
        purpose="200 étuis d'expédition (fictif)",
        idempotency_key="FICTIF-DEM-" + hashlib.sha256(repr(sorted(kw.items(), key=str)).encode()).hexdigest()[:24],
        requested_by="A-11",
        requested_at=NOW,
        amount_source="devis FICTIF n° 1 du 2026-11-09",
        fictif=True,
    )
    base.update(kw)
    return SpendRequest(**base)


def stock_req(**kw) -> SpendRequest:
    base = dict(
        supplier_id="FICTIF_GROSSISTE",
        category=SpendCategory.STOCK,
        extension="FICTIF_EXT_A",
        product_key="FICTIF_DISPLAY_A",
        product_language="FR",
        justification_ref="reorder:FICTIF0001",
        amount=D("200"),
    )
    base.update(kw)
    return req(**base)


def status(**kw) -> StopLossStatus:
    base = dict(as_of=NOW, autonomy_level=4)
    base.update(kw)
    return StopLossStatus(**base)


def proposal(ref: str = "reorder:FICTIF0001", *, line_cost: str = "5000", generated_at: datetime | None = None,
             product_key: str = "FICTIF_DISPLAY_A", extension: str = "FICTIF_EXT_A") -> ReorderProposal:
    line = ReorderLine(product_key=product_key, extension=extension, supplier_id="fictif_grossiste_a",
                       supplier_sku="FICTIF-A-001", qty=10, unit_cost_chf=D(line_cost) / 10, line_cost_chf=D(line_cost),
                       reorder_point=D("2"), position=0)
    return ReorderProposal(lines=(line,), skipped=(), total_cost_chf=D(line_cost), budget_available_chf=D("6000"),
                           budget_remaining_chf=D("1000"), extension_exposure_after={extension: D(line_cost)},
                           rules_version="v1-2026-10-04", inputs_hash=ref,
                           generated_at=generated_at or NOW - timedelta(hours=1))  # fmt: skip


def proposals(*items: ReorderProposal) -> EngineProposalBook:
    book = EngineProposalBook()
    for item in items or (proposal(),):
        book.register(item, recorded_by="moteur")
    return book


def treasury(**kw) -> TreasurySnapshot:
    base = dict(as_of=NOW, cash_available_chf=D("6000"), paypal_balance_chf=D("2000"),
                extension_exposure_chf={"FICTIF_EXT_A": D("0")})  # fmt: skip
    base.update(kw)
    return TreasurySnapshot(**base)


def decide(request: SpendRequest, mandate: Mandate | None = None, ledger: SpendLedger | None = None, **kw):
    if "proposals" not in kw:  # proposition du moteur enregistrée 30 min avant la demande
        kw["proposals"] = proposals(proposal(generated_at=request.requested_at - timedelta(minutes=30)))
    return check(
        request,
        mandate or signed(no_fees),
        ledger or SpendLedger(),
        kw.pop("stoploss", status()),
        kw.pop("snapshot", treasury()),
        **kw,
    )


def approve_and_record(ledger: SpendLedger, request: SpendRequest, mandate: Mandate | None = None, **kw):
    decision = decide(request, mandate, ledger, **kw)
    ledger.record(request, decision)
    return decision


# ----------------------------------------------------------------------------- gabarit livré


def test_template_is_readable_but_inactive() -> None:
    m = template()
    assert m.mandate_version == "mandat-v1-2026-10-04"
    assert m.suppliers == () and not m.is_signed
    assert m.cash_reserve_chf == CASH_STOPLOSS_RESERVE == load_stoploss_config().cash.reserve_chf
    assert m.extension_max_share == load_stoploss_config().extension.max_share_of_stock_budget
    assert set(m.missing_fields()) >= {"limits.per_transaction_chf", "limits.per_month_chf", "valid_until"}
    assert m.inactive_reasons(NOW) == [R.MANDATE_INCOMPLETE, R.MANDATE_NOT_SIGNED]
    assert m.paypal.fee_pct == D("0.034") and m.paypal.fx_conversion_pct == D("0.04")


@pytest.mark.parametrize("category", [c for c in SpendCategory if c not in FORBIDDEN_CATEGORIES])
@pytest.mark.parametrize("method", [PaymentMethod.PAYPAL, PaymentMethod.BANK_TRANSFER])
def test_unsigned_template_never_approves(category: SpendCategory, method: PaymentMethod) -> None:
    request = stock_req(category=category, payment_method=method, supplier_id="FICTIF_INCONNU")
    decision = decide(request, template())
    assert decision.outcome is HUMAN
    assert decision.has(R.MANDATE_NOT_SIGNED) and decision.has(R.MANDATE_INCOMPLETE)
    assert not decision.has(R.SUPPLIER_NOT_WHITELISTED)  # liste blanche non évaluée sans mandat


@pytest.mark.parametrize("category", sorted(FORBIDDEN_CATEGORIES, key=lambda c: c.value))
def test_hard_prohibitions_rejected_even_without_mandate(category: SpendCategory) -> None:
    decision = decide(req(category=category), template())
    assert decision.outcome is REJECTED and decision.has(R.FORBIDDEN_CATEGORY)


# ------------------------------------------------------------------------- signature, empreinte


def test_signed_mandate_is_active() -> None:
    m = signed()
    assert m.is_signed and m.is_active(NOW) and m.missing_fields() == ()


def test_editing_after_signature_invalidates_mandate() -> None:
    data = signed_data()
    data["limits"]["per_transaction_chf"] = "5000"  # modification non signée
    m = parse_mandate(data)
    assert not m.is_signed and m.inactive_reasons(NOW) == [R.MANDATE_FINGERPRINT_MISMATCH]
    assert decide(req(), m).outcome is HUMAN


def test_signatory_is_part_of_fingerprint() -> None:
    data = signed_data()
    data["approval"]["approved_by"] = "Quelqu'un d'autre"
    assert parse_mandate(data).inactive_reasons(NOW) == [R.MANDATE_FINGERPRINT_MISMATCH]


def test_vault_fingerprint_is_second_barrier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = signed_data()
    good = data["approval"]["fingerprint_sha256"]
    assert parse_mandate(data, expected_fingerprint=good.upper()).is_active(NOW)
    assert parse_mandate(data, expected_fingerprint="0" * 64).inactive_reasons(NOW) == [R.MANDATE_FINGERPRINT_MISMATCH]
    with pytest.raises(MandateError, match="empreinte attendue"):
        parse_mandate(data, expected_fingerprint="xyz")
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv(MANDATE_FINGERPRINT_ENV_VAR, "f" * 64)
    assert not load_mandate(path).is_active(NOW)
    monkeypatch.setenv(MANDATE_FINGERPRINT_ENV_VAR, good)
    assert load_mandate(path).is_active(NOW)
    monkeypatch.setenv(MANDATE_ENV_VAR, str(path))
    assert load_mandate().source_path == str(path)


def test_revocation_and_validity_period() -> None:
    revoked = signed(lambda d: d["approval"].update(revoked_at="2026-11-10T09:59:00+01:00"))
    assert R.MANDATE_REVOKED in revoked.inactive_reasons(NOW)
    later = signed(lambda d: d["approval"].update(revoked_at="2026-11-11T00:00:00+01:00"))
    assert later.is_active(NOW)
    assert signed(lambda d: d.update(valid_from="2026-11-11")).inactive_reasons(NOW) == [R.MANDATE_NOT_IN_FORCE]
    assert signed(lambda d: d.update(valid_until="2026-11-09")).inactive_reasons(NOW) == [R.MANDATE_NOT_IN_FORCE]
    assert signed(lambda d: d.update(valid_until="2026-11-10")).is_active(NOW)
    future = signed(lambda d: d["approval"].update(approved_at="2026-11-11T09:00:00+01:00"))
    assert future.inactive_reasons(NOW) == [R.MANDATE_NOT_SIGNED]
    by_date = signed(lambda d: d["approval"].update(approved_at=date(2026, 10, 10)))
    assert by_date.is_active(NOW)


def test_unsigned_mandate_reasons_in_decision() -> None:
    m = parse_mandate(signed_data(sign=False))
    decision = decide(req(), m)
    assert decision.outcome is HUMAN and decision.reasons == (R.MANDATE_NOT_SIGNED.value,)


# ---------------------------------------------------------------------------- cas nominal


def test_happy_path_within_mandate() -> None:
    m = signed()
    decision = decide(req(), m)
    assert decision.outcome is OK and decision.reasons == ()
    assert decision.payment_cost_chf == D("3.95")  # 3,4 % × 100 + 0,55
    assert decision.effective_cost_chf == D("103.95")
    assert decision.has(R.PAYPAL_COST_ABOVE_THRESHOLD) and decision.warnings == (R.PAYPAL_COST_ABOVE_THRESHOLD.value,)
    ctx = decision.context
    assert ctx.per_transaction_cap_chf == D("500") and ctx.monthly_cap_chf == D("3000")
    assert ctx.category_envelope_chf == D("300") and ctx.category_remaining_before_chf == D("300")
    assert ctx.cash_available_before_chf == D("6000") and ctx.paypal_available_before_chf == D("2000")
    assert ctx.stoploss_cash_ok and ctx.stoploss_global_ok and ctx.autonomy_level == 4
    assert decision.mandate_fingerprint == m.fingerprint and len(decision.decision_ref) == 16
    assert decision.transfer_draft is None
    assert any("virement" in msg for msg in decision.messages)


# ------------------------------------------------------------------------------ interdits


def test_non_fr_stock_rejected_unknown_language_needs_human() -> None:
    assert decide(stock_req(product_language="EN")).has(R.NON_FR_PRODUCT)
    assert decide(stock_req(product_language="jp")).outcome is REJECTED
    unknown = decide(stock_req(product_language="unknown"))
    assert unknown.outcome is HUMAN and unknown.reasons == (R.LANGUAGE_UNKNOWN.value,)
    assert decide(stock_req(product_language=None)).has(R.LANGUAGE_UNKNOWN)
    sample = decide(req(category=SpendCategory.SAMPLES, supplier_id="FICTIF_GROSSISTE", product_language="DE"))
    assert sample.outcome is REJECTED and sample.has(R.NON_FR_PRODUCT)


def test_extra_forbidden_category_from_owner() -> None:
    m = signed(lambda d: d.update(extra_forbidden_categories=["SAMPLES"]))
    decision = decide(req(category=SpendCategory.SAMPLES, supplier_id="FICTIF_GROSSISTE"), m)
    assert decision.outcome is REJECTED and decision.has(R.FORBIDDEN_CATEGORY)


@pytest.mark.parametrize(
    "method",
    [PaymentMethod.CARD, PaymentMethod.PAY_LATER, PaymentMethod.CRYPTO, PaymentMethod.CASH, PaymentMethod.OTHER],
)
def test_payment_outside_paypal_or_prepared_transfer_rejected(method: PaymentMethod) -> None:
    decision = decide(req(payment_method=method))
    assert decision.outcome is REJECTED and decision.has(R.PAYMENT_METHOD_FORBIDDEN)
    assert not decision.has(R.SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED)


def test_supplier_whitelist() -> None:
    assert decide(req(supplier_id="FICTIF_INCONNU")).has(R.SUPPLIER_NOT_WHITELISTED)
    assert decide(req(supplier_id="FICTIF_INCONNU")).outcome is REJECTED
    wrong_cat = decide(req(supplier_id="FICTIF_PUB"))
    assert wrong_cat.outcome is REJECTED and wrong_cat.has(R.SUPPLIER_CATEGORY_NOT_ALLOWED)
    wrong_method = decide(req(payment_method=PaymentMethod.BANK_TRANSFER))
    assert wrong_method.outcome is REJECTED and wrong_method.has(R.SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED)


def test_category_not_delegated_needs_human() -> None:
    m = signed(lambda d: (d["categories"].pop("SAMPLES"), d["suppliers"][1].update(categories=["STOCK"])))
    decision = decide(req(category=SpendCategory.SAMPLES, supplier_id="FICTIF_GROSSISTE"), m)
    assert decision.has(R.CATEGORY_NOT_DELEGATED) and decision.has(R.SUPPLIER_CATEGORY_NOT_ALLOWED)
    admin = decide(req(category=SpendCategory.ADMIN))
    assert admin.has(R.CATEGORY_NOT_DELEGATED)


def test_autonomy_level_per_category() -> None:
    assert decide(stock_req(), stoploss=status(autonomy_level=3)).has(R.AUTONOMY_LEVEL_TOO_LOW)
    assert decide(stock_req(), stoploss=status(autonomy_level=4)).outcome is OK
    ads_req = req(supplier_id="FICTIF_PUB", category=SpendCategory.ADVERTISING, amount=D("50"))
    assert decide(ads_req, stoploss=status(autonomy_level=2)).outcome is HUMAN
    assert decide(ads_req, stoploss=status(autonomy_level=3)).outcome is OK
    assert decide(req(), stoploss=status(autonomy_level=1)).outcome is OK  # emballages : niveau 1


# --------------------------------------------------------------------------------- stop-loss


@pytest.mark.parametrize("category", [SpendCategory.PACKAGING, SpendCategory.SHIPPING, SpendCategory.STOCK])
def test_global_freeze_rejects_everything(category: SpendCategory) -> None:
    request = stock_req(category=category, supplier_id="FICTIF_EMBALLAGES" if category is not SpendCategory.STOCK
                        else "FICTIF_GROSSISTE")  # fmt: skip
    decision = decide(request, stoploss=status(global_frozen=True, autonomy_level=1))
    assert decision.outcome is REJECTED and decision.has(R.STOPLOSS_GLOBAL_FREEZE)
    assert decision.context.stoploss_global_ok is False


def test_cash_freeze_blocks_purchases_and_ads_only() -> None:
    frozen = status(purchases_and_ads_frozen=True)
    assert decide(stock_req(), stoploss=frozen).has(R.STOPLOSS_CASH_FREEZE)
    ads_req = req(supplier_id="FICTIF_PUB", category=SpendCategory.ADVERTISING, amount=D("50"))
    assert decide(ads_req, stoploss=frozen).outcome is REJECTED
    assert decide(req(), stoploss=frozen).outcome is OK  # emballages des commandes payées
    assert SpendCategory.PACKAGING not in CASH_FREEZE_CATEGORIES


def test_extension_product_and_campaign_stoplosses() -> None:
    assert decide(stock_req(), stoploss=status(no_reorder_extensions=("FICTIF_EXT_A",))).has(R.STOPLOSS_EXTENSION)
    assert decide(stock_req(), stoploss=status(blocked_products=("FICTIF_DISPLAY_A",))).has(R.STOPLOSS_PRODUCT)
    ads_req = req(supplier_id="FICTIF_PUB", category=SpendCategory.ADVERTISING, amount=D("50"), campaign_id="FICTIF_C1")
    assert decide(ads_req, stoploss=status(cut_campaigns=("FICTIF_C1",))).has(R.STOPLOSS_ADS)
    assert decide(ads_req, stoploss=status(cut_campaigns=("FICTIF_C2",))).outcome is OK
    assert decide(ads_req.replace(campaign_id=None), stoploss=status(ads_globally_cut=True)).has(R.STOPLOSS_ADS)


def test_stale_or_future_snapshots_rejected() -> None:
    old = NOW - timedelta(minutes=61)
    assert decide(req(), snapshot=treasury(as_of=old)).has(R.STALE_TREASURY_SNAPSHOT)
    assert decide(req(), snapshot=treasury(as_of=NOW - timedelta(minutes=60))).outcome is OK
    assert decide(req(), stoploss=status(as_of=old)).has(R.STALE_STOPLOSS_STATUS)
    assert decide(req(), snapshot=treasury(as_of=NOW + timedelta(minutes=6))).outcome is REJECTED


# ------------------------------------------------------------------------------------ plafonds


def test_per_transaction_cap_boundary_and_paypal_cost_included() -> None:
    m = signed(no_fees)
    assert decide(req(amount=D("500"), category=SpendCategory.SHIPPING), m).outcome is OK
    over = decide(req(amount=D("500.01"), category=SpendCategory.SHIPPING), m)
    assert over.outcome is HUMAN and over.has(R.ABOVE_TRANSACTION_CAP)
    with_fees = decide(req(amount=D("490"), category=SpendCategory.SHIPPING), signed())
    assert with_fees.effective_cost_chf == D("507.21") and with_fees.has(R.ABOVE_TRANSACTION_CAP)


def test_supplier_cap_is_stricter() -> None:
    ads_req = req(supplier_id="FICTIF_PUB", category=SpendCategory.ADVERTISING, amount=D("100.01"))
    decision = decide(ads_req)
    assert decision.has(R.ABOVE_TRANSACTION_CAP) and decision.context.per_transaction_cap_chf == D("100")


def test_split_payments_same_day_detected() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    first = req(category=SpendCategory.SHIPPING, amount=D("300"), idempotency_key="FICTIF-SPLIT-1")
    assert approve_and_record(ledger, first, m).outcome is OK
    second = req(category=SpendCategory.SHIPPING, amount=D("250"), idempotency_key="FICTIF-SPLIT-2")
    split = decide(second, m, ledger)
    assert split.outcome is HUMAN and split.has(R.SPLIT_SUSPECTED)
    tomorrow = second.replace(requested_at=NOW + timedelta(days=1))
    assert decide(tomorrow, m, ledger, snapshot=treasury(as_of=NOW + timedelta(days=1)),
                  stoploss=status(as_of=NOW + timedelta(days=1))).outcome is OK  # fmt: skip


def test_monthly_cap_counts_autonomous_spend_only() -> None:
    m = signed(lambda d: (no_fees(d), d["limits"].update(per_month_chf="1000", stock_budget_chf="10000"),
                          d["categories"]["STOCK"].update(envelope_chf="5000")))  # fmt: skip
    ledger = SpendLedger()
    for i, day in enumerate((1, 2)):
        at = NOW - timedelta(days=day)
        r = stock_req(amount=D("400"), idempotency_key=f"FICTIF-M-{i}", requested_at=at)
        approve_and_record(ledger, r, m, snapshot=treasury(as_of=at), stoploss=status(as_of=at))
    human = stock_req(amount=D("600"), idempotency_key="FICTIF-M-H", requested_at=NOW - timedelta(days=3))
    d_h = approve_and_record(ledger, human, m, snapshot=treasury(as_of=human.requested_at),
                             stoploss=status(as_of=human.requested_at))  # fmt: skip
    assert d_h.has(R.ABOVE_MONTHLY_CAP)
    ledger.approve_by_human("FICTIF-M-H", approver="FICTIF Propriétaire", at=NOW - timedelta(days=3))
    assert decide(stock_req(amount=D("200"), idempotency_key="FICTIF-M-3"), m, ledger).outcome is OK  # 800 + 200
    over = decide(stock_req(amount=D("200.01"), idempotency_key="FICTIF-M-4"), m, ledger)
    assert over.has(R.ABOVE_MONTHLY_CAP) and over.context.month_autonomous_before_chf == D("800")
    next_month = datetime(2026, 12, 1, 9, 0, tzinfo=TZ)
    fresh = stock_req(amount=D("200.01"), idempotency_key="FICTIF-M-5", requested_at=next_month)
    assert not decide(fresh, m, ledger, snapshot=treasury(as_of=next_month),
                      stoploss=status(as_of=next_month)).has(R.ABOVE_MONTHLY_CAP)  # fmt: skip


def test_category_envelope_counts_all_commitments() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    big = req(amount=D("250"), idempotency_key="FICTIF-ENV-1", requested_at=NOW - timedelta(days=1))
    when = big.requested_at
    approve_and_record(ledger, big, m, snapshot=treasury(as_of=when), stoploss=status(as_of=when))
    assert decide(req(amount=D("50"), idempotency_key="FICTIF-ENV-2"), m, ledger).outcome is OK  # 250 + 50 = 300
    over = decide(req(amount=D("50.01"), idempotency_key="FICTIF-ENV-3"), m, ledger)
    assert over.has(R.ABOVE_CATEGORY_ENVELOPE) and over.context.category_remaining_before_chf == D("50")
    ledger.cancel("FICTIF-ENV-1", at=NOW, reason="commande annulée", actor="A-05")
    assert decide(req(amount=D("50.01"), idempotency_key="FICTIF-ENV-3"), m, ledger).outcome is OK


def test_category_monthly_cap() -> None:
    ledger = SpendLedger()
    tools = dict(category=SpendCategory.SITE_TOOLS, supplier_id="FICTIF_OUTILS")
    m = signed(lambda d: (no_fees(d), d["categories"]["SITE_TOOLS"].update(per_month_chf="180"),
                          d["suppliers"].append({**SUPPLIERS[0], "supplier_id": "FICTIF_OUTILS",
                                                 "categories": ["SITE_TOOLS"]})))  # fmt: skip
    approve_and_record(ledger, req(amount=D("150"), idempotency_key="FICTIF-T-1",
                                   requested_at=NOW - timedelta(days=2), **tools), m,
                       snapshot=treasury(as_of=NOW - timedelta(days=2)), stoploss=status(as_of=NOW - timedelta(days=2)))
    assert decide(req(amount=D("30"), idempotency_key="FICTIF-T-2", **tools), m, ledger).outcome is OK
    assert decide(req(amount=D("30.01"), idempotency_key="FICTIF-T-3", **tools), m, ledger).has(
        R.ABOVE_CATEGORY_MONTHLY_CAP
    )


def test_extension_cap_25_percent_of_stock_budget() -> None:
    m = signed(no_fees)
    snap = treasury(extension_exposure_chf={"FICTIF_EXT_A": D("700")})
    assert decide(stock_req(amount=D("50")), m, snapshot=snap).outcome is OK  # 700 + 50 = 750 = 25 %
    over = decide(stock_req(amount=D("50.01")), m, snapshot=snap)
    assert over.outcome is HUMAN and over.has(R.ABOVE_EXTENSION_CAP)
    assert over.context.extension_exposure_before_chf == D("700") and over.context.extension_cap_chf == D("750.00")


def test_extension_cap_counts_unsettled_commitments_once() -> None:
    m = signed(lambda d: (no_fees(d), d["limits"].update(per_transaction_chf="2000")))
    ledger = SpendLedger()
    before = NOW - timedelta(minutes=30)
    first = stock_req(amount=D("400"), idempotency_key="FICTIF-X-1", requested_at=before)
    approve_and_record(ledger, first, m, snapshot=treasury(as_of=before), stoploss=status(as_of=before))
    second = stock_req(amount=D("350.01"), idempotency_key="FICTIF-X-2")
    assert decide(second, m, ledger).has(R.ABOVE_EXTENSION_CAP)  # 400 en attente + 350,01 > 750
    ledger.mark_executed("FICTIF-X-1", at=NOW - timedelta(minutes=20), amount_chf=D("400"), payment_ref="FICTIF-PP-1")
    # photo prise après l'exécution : l'exposition (400) est dans la photo, pas recomptée
    snap = treasury(as_of=NOW - timedelta(minutes=10), extension_exposure_chf={"FICTIF_EXT_A": D("400")})
    assert decide(second.replace(amount=D("350")), m, ledger, snapshot=snap).outcome is OK
    assert decide(second, m, ledger, snapshot=snap).has(R.ABOVE_EXTENSION_CAP)
    # photo antérieure à l'exécution : l'engagement exécuté après la photo est ajouté
    old = treasury(as_of=NOW - timedelta(minutes=25))
    assert decide(second, m, ledger, snapshot=old).has(R.ABOVE_EXTENSION_CAP)


def test_stock_requirements_against_speculation() -> None:
    d = decide(stock_req(extension=None, product_key=None, justification_ref=None))
    assert d.outcome is HUMAN
    assert {R.EXTENSION_UNKNOWN.value, R.PRODUCT_UNKNOWN.value, R.NO_ENGINE_PROPOSAL.value} <= set(d.reasons)
    acc = decide(stock_req(category=SpendCategory.ACCESSORIES, extension=None, product_language=None))
    assert acc.outcome is OK  # accessoires : ni langue ni extension


# ----------------------------------------------------------------------------- trésorerie


def test_cash_reserve_preserved() -> None:
    m = signed(no_fees)
    assert decide(req(amount=D("100")), m, snapshot=treasury(cash_available_chf=D("1700"))).outcome is OK
    breach = decide(req(amount=D("100.01")), m, snapshot=treasury(cash_available_chf=D("1700")))
    assert breach.outcome is HUMAN and breach.has(R.CASH_RESERVE_WOULD_BE_BREACHED)
    below = decide(stock_req(), m, snapshot=treasury(cash_available_chf=D("1599.99")))
    assert below.outcome is REJECTED and below.has(R.CASH_BELOW_RESERVE) and not below.context.stoploss_cash_ok
    packaging = decide(req(), m, snapshot=treasury(cash_available_chf=D("1599.99")))
    assert packaging.outcome is HUMAN and packaging.has(R.CASH_RESERVE_WOULD_BE_BREACHED)


def test_unsettled_commitments_reduce_available_cash() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    approve_and_record(ledger, req(amount=D("100"), idempotency_key="FICTIF-C-1"), m,
                       snapshot=treasury(cash_available_chf=D("1800")))  # fmt: skip
    decision = decide(req(amount=D("100.01"), idempotency_key="FICTIF-C-2"), m, ledger,
                      snapshot=treasury(cash_available_chf=D("1800")))  # fmt: skip
    assert decision.context.cash_available_before_chf == D("1700") and decision.has(R.CASH_RESERVE_WOULD_BE_BREACHED)


def test_paypal_balance_is_physical_cap() -> None:
    m = signed(no_fees)
    assert decide(req(amount=D("100")), m, snapshot=treasury(paypal_balance_chf=D("100"))).outcome is OK
    low = decide(req(amount=D("100.01")), m, snapshot=treasury(paypal_balance_chf=D("100")))
    assert low.outcome is HUMAN and low.has(R.PAYPAL_BALANCE_INSUFFICIENT)
    assert decide(req(), m, snapshot=treasury(paypal_balance_chf=None)).has(R.PAYPAL_BALANCE_INSUFFICIENT)


# ---------------------------------------------------------------------------- moyens de paiement


def test_bank_transfer_prepared_for_one_click_validation() -> None:
    decision = decide(stock_req(payment_method=PaymentMethod.BANK_TRANSFER, amount=D("450")))
    assert decision.outcome is HUMAN and decision.reasons == (R.BANK_TRANSFER_PREPARED.value,)
    draft = decision.transfer_draft
    assert draft is not None and draft.payee_ref == "coffre:beneficiaires/FICTIF_GROSSISTE"
    assert draft.amount_chf == D("450.00") and draft.status == "PREPARED_FOR_HUMAN_VALIDATION"
    assert draft.reference == decision.idempotency_key[:35] and decision.payment_cost_chf == 0
    rejected = decide(stock_req(payment_method=PaymentMethod.BANK_TRANSFER, product_language="EN"))
    assert rejected.outcome is REJECTED and rejected.transfer_draft is None
    unsigned = decide(stock_req(payment_method=PaymentMethod.BANK_TRANSFER), template())
    assert unsigned.transfer_draft is not None and unsigned.transfer_draft.payee_ref is None


def test_paypal_cost_estimate() -> None:
    model = PayPalCostModel(fee_pct=D("0.034"), fee_fixed_chf=D("0.55"), fx_conversion_pct=D("0.04"),
                            flag_above_pct=D("0.02"))  # fmt: skip
    assert paypal_cost(D("100"), "CHF", model) == D("3.95")
    assert paypal_cost(D("1000"), "EUR", model) == D("74.55")  # 34 + 0,55 + 40
    assert paypal_cost(D("0.01"), "CHF", model) == D("0.55")


def test_foreign_currency_needs_sourced_rate_and_adds_conversion() -> None:
    eur = stock_req(amount=D("400"), currency="eur", fx_rate_to_chf=D("0.9375"), fx_source="BNS FICTIF",
                    fx_date=date(2026, 11, 9))  # fmt: skip
    assert eur.amount_chf == D("375.00") and eur.currency == "EUR"
    decision = decide(eur, signed())
    assert decision.has(R.PAYPAL_FX_CONVERSION) and decision.has(R.PAYPAL_COST_ABOVE_THRESHOLD)
    assert decision.payment_cost_chf == D("28.30")  # 12,75 + 0,55 + 15,00
    with pytest.raises(ValidationError, match="taux"):
        req(currency="EUR")
    with pytest.raises(ValidationError):
        req(fx_rate_to_chf=D("1.1"))
    assert req(fx_rate_to_chf=D("1")).amount_chf == D("100.00")


def test_low_cost_paypal_not_flagged() -> None:
    m = signed(lambda d: d["paypal"].update(fee_pct="0.01", fee_fixed_chf="0", flag_above_pct="0.02"))
    decision = decide(req(), m)
    assert decision.warnings == () and decision.payment_cost_chf == D("1.00")


# ---------------------------------------------------------------------------------- demande


@pytest.mark.parametrize(
    "kw",
    [
        {"amount": 100.0},
        {"amount": True},
        {"amount": D("0")},
        {"amount": D("NaN")},
        {"currency": "CHFF"},
        {"idempotency_key": "court"},
        {"idempotency_key": "clé avec espace"},
        {"requested_at": datetime(2026, 11, 10, 10)},
        {"purpose": ""},
        {"amount_source": ""},
        {"category": "NEW"},
    ],
)
def test_invalid_requests_rejected(kw: dict) -> None:
    with pytest.raises(ValidationError):
        req(**kw)


def test_naive_now_rejected() -> None:
    with pytest.raises(MandateError):
        decide(req(), now=datetime(2026, 11, 10, 10))


# ------------------------------------------------------------------------------- idempotence


def test_same_key_same_request_is_replayed_without_double_spend() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    request = req(idempotency_key="FICTIF-IDEM-1")
    first = approve_and_record(ledger, request, m)
    replay = decide(request, m, ledger)
    assert replay.replayed and replay.outcome is first.outcome and replay.decision_ref == first.decision_ref
    assert ledger.record(request, replay) is ledger.get("FICTIF-IDEM-1")
    assert ledger.committed() == D("100") and [e.kind for e in ledger.events()] == ["RECORDED", "REPLAYED"]


def test_same_key_different_request_is_rejected() -> None:
    m = signed(no_fees)
    ledger = SpendLedger()
    approve_and_record(ledger, req(idempotency_key="FICTIF-IDEM-2"), m)
    other = req(idempotency_key="FICTIF-IDEM-2", amount=D("150"))
    decision = decide(other, m, ledger)
    assert decision.outcome is REJECTED and decision.reasons == (R.IDEMPOTENCY_CONFLICT.value,)
    with pytest.raises(IdempotencyConflictError):
        ledger.record(other, decision)
    with pytest.raises(MandateError, match="ne correspond pas"):
        ledger.record(other, decide(req(idempotency_key="FICTIF-IDEM-3"), m))
    orphan = decide(req(idempotency_key="FICTIF-IDEM-4"), m).replace(replayed=True)
    with pytest.raises(MandateError, match="rejouée"):
        ledger.record(req(idempotency_key="FICTIF-IDEM-4"), orphan)


# ------------------------------------------------------------------------------- registre


def test_human_approval_lifecycle_and_expiry() -> None:
    ledger = SpendLedger()
    request = stock_req(payment_method=PaymentMethod.BANK_TRANSFER, idempotency_key="FICTIF-H-1")
    approve_and_record(ledger, request)
    assert ledger.get("FICTIF-H-1").status is SpendStatus.PENDING_HUMAN
    assert ledger.committed() == 0  # en attente : non engagé
    assert not ledger.can_execute("FICTIF-H-1", now=NOW)
    entry = ledger.approve_by_human("FICTIF-H-1", approver="FICTIF Propriétaire", at=NOW + timedelta(hours=2))
    assert entry.status is SpendStatus.HUMAN_APPROVED and ledger.committed() == D("200.00")
    assert ledger.can_execute("FICTIF-H-1", now=NOW + timedelta(hours=2, minutes=30))
    assert not ledger.can_execute("FICTIF-H-1", now=NOW + timedelta(hours=4))
    with pytest.raises(MandateError, match="validation impossible"):
        ledger.approve_by_human("FICTIF-H-1", approver="x", at=NOW)
    late = stock_req(payment_method=PaymentMethod.BANK_TRANSFER, idempotency_key="FICTIF-H-2")
    approve_and_record(ledger, late)
    with pytest.raises(MandateError, match="expirée"):
        ledger.approve_by_human("FICTIF-H-2", approver="FICTIF Propriétaire", at=NOW + timedelta(hours=24, seconds=1))
    assert ledger.get("FICTIF-H-2").status is SpendStatus.EXPIRED
    third = stock_req(payment_method=PaymentMethod.BANK_TRANSFER, idempotency_key="FICTIF-H-3")
    approve_and_record(ledger, third)
    refused = ledger.refuse_by_human("FICTIF-H-3", approver="FICTIF Propriétaire", at=NOW)
    assert refused.status is SpendStatus.HUMAN_REFUSED
    with pytest.raises(MandateError):
        ledger.refuse_by_human("FICTIF-H-3", approver="x", at=NOW)
    with pytest.raises(MandateError, match="approbateur"):
        ledger.approve_by_human("FICTIF-H-3", approver=" ", at=NOW)
    with pytest.raises(MandateError, match="inconnue"):
        ledger.approve_by_human("FICTIF-ABSENT", approver="x", at=NOW)


def test_rejected_entries_cannot_be_paid_or_approved() -> None:
    ledger = SpendLedger()
    bad = req(category=SpendCategory.GRADING, idempotency_key="FICTIF-REJ-1")
    approve_and_record(ledger, bad)
    assert ledger.get("FICTIF-REJ-1").status is SpendStatus.REJECTED
    with pytest.raises(MandateError):
        ledger.mark_executed("FICTIF-REJ-1", at=NOW, amount_chf=D("100"), payment_ref="FICTIF-PP")
    with pytest.raises(MandateError):
        ledger.approve_by_human("FICTIF-REJ-1", approver="x", at=NOW)
    with pytest.raises(MandateError):
        ledger.cancel("FICTIF-REJ-1", at=NOW, reason="x", actor="A-05")


def test_execution_is_idempotent_and_conflicts_detected() -> None:
    ledger = SpendLedger()
    approve_and_record(ledger, req(idempotency_key="FICTIF-E-1"))
    assert ledger.can_execute("FICTIF-E-1", now=NOW + timedelta(minutes=10))
    e1 = ledger.mark_executed("FICTIF-E-1", at=NOW, amount_chf=D("100.00"), payment_ref="FICTIF-PP-1")
    assert e1.status is SpendStatus.EXECUTED and ledger.committed() == D("100.00")
    assert ledger.mark_executed("FICTIF-E-1", at=NOW, amount_chf=D("100"), payment_ref="FICTIF-PP-1") is e1
    with pytest.raises(IdempotencyConflictError):
        ledger.mark_executed("FICTIF-E-1", at=NOW, amount_chf=D("100"), payment_ref="FICTIF-PP-2")
    with pytest.raises(MandateError):
        ledger.cancel("FICTIF-E-1", at=NOW, reason="trop tard", actor="A-05")
    approve_and_record(ledger, req(idempotency_key="FICTIF-E-2"))
    for bad_amount in (100.0, D("0"), "abc"):
        with pytest.raises(MandateError):
            ledger.mark_executed("FICTIF-E-2", at=NOW, amount_chf=bad_amount, payment_ref="FICTIF-PP-3")  # type: ignore[arg-type]
    with pytest.raises(MandateError, match="référence"):
        ledger.mark_executed("FICTIF-E-2", at=NOW, amount_chf=D("1"), payment_ref=" ")
    with pytest.raises(MandateError, match="motif"):
        ledger.cancel("FICTIF-E-2", at=NOW, reason="", actor="A-05")
    assert ledger.cancel("FICTIF-E-2", at=NOW, reason="doublon", actor="A-05").status is SpendStatus.CANCELLED


def statement(*lines: tuple[str, str, str]) -> list[StatementLine]:
    return [
        StatementLine(source="PAYPAL", transaction_id=tx, booked_on=NOW.date(), amount_chf=D(amount), reference=ref)
        for tx, amount, ref in lines
    ]


def test_reconciliation_matches_flags_and_is_idempotent() -> None:
    ledger = SpendLedger()
    for key in ("FICTIF-R-1", "FICTIF-R-2", "FICTIF-R-3", "FICTIF-R-4"):
        approve_and_record(ledger, req(idempotency_key=key, category=SpendCategory.SHIPPING))
    assert all(e.status is SpendStatus.APPROVED for e in ledger.entries())
    ledger.mark_executed("FICTIF-R-1", at=NOW, amount_chf=D("100.00"), payment_ref="TX-1")
    ledger.mark_executed("FICTIF-R-2", at=NOW, amount_chf=D("100.00"), payment_ref="TX-2")
    ledger.mark_executed("FICTIF-R-3", at=NOW, amount_chf=D("100.00"), payment_ref="TX-3")
    ledger.mark_executed("FICTIF-R-4", at=NOW - timedelta(days=5), amount_chf=D("100.00"), payment_ref="TX-4")
    report = ledger.reconcile(
        statement(("TX-1", "100.00", ""), ("TX-X", "101.00", "lot FICTIF-R-2"), ("TX-9", "49.00", "inconnu")),
        at=NOW + timedelta(days=1),
    )
    by_status = {ln.status: ln for ln in report.lines}
    assert by_status["OK"].idempotency_key == "FICTIF-R-1"
    assert by_status["AMOUNT_MISMATCH"].idempotency_key == "FICTIF-R-2"  # trouvé par la clé, 1,00 CHF d'écart
    assert by_status["UNKNOWN_DEBIT"].transaction_id == "TX-9"
    assert by_status["PENDING"].idempotency_key == "FICTIF-R-3"
    assert by_status["MISSING_ON_STATEMENT"].idempotency_key == "FICTIF-R-4"
    assert not report.ok and len(report.alerts) == 3
    again = ledger.reconcile(statement(("TX-1", "100.00", "")), at=NOW + timedelta(days=1))
    assert [ln.status for ln in again.lines].count("OK") == 0
    tolerant = ledger.reconcile(statement(("TX-3", "100.04", "")), at=NOW + timedelta(days=1))
    assert tolerant.lines[0].status == "OK"  # écart 0,04 ≤ tolérance 0,05
    with pytest.raises(MandateError, match="double"):
        ledger.reconcile(statement(("A", "1", ""), ("A", "1", "")), at=NOW)


def test_registry_rows_follow_shared_template() -> None:
    header = next(csv.reader((REPO / "docs/08-agents/modeles/REGISTRE_MANDAT.csv").open(encoding="utf-8")))
    assert tuple(header) == REGISTRY_COLUMNS
    ledger = SpendLedger()
    approve_and_record(ledger, req(idempotency_key="FICTIF-REG-1"), signed())
    ledger.mark_executed("FICTIF-REG-1", at=NOW, amount_chf=D("103.95"), payment_ref="FICTIF-PP-9")
    (row,) = ledger.to_registry_rows()
    assert tuple(row) == REGISTRY_COLUMNS
    assert row["decision"] == "APPROVED_WITHIN_MANDATE" and row["statut"] == "EXECUTED"
    assert row["montant_chf"] == "100.00" and row["taux_chf"] == "1.00" and row["source_taux"] == "CHF"
    assert row["plafond_transaction_chf"] == "500.00" and row["reste_categorie_avant_chf"] == "300.00"
    assert row["stoploss_cash_ok"] == "oui" and row["stoploss_global_ok"] == "oui" and row["niveau_autonomie"] == "4"
    assert row["ref_paiement"] == "FICTIF-PP-9" and row["fictif"] == "true" and row["cle_idempotence"] == "FICTIF-REG-1"


# ---------------------------------------------------------------------------- validation YAML


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["limits"].update(per_transaction_chf=500.0), "virgule flottante"),
        (lambda d: d.update(inconnu=1), "clés inconnues"),
        (lambda d: d["limits"].pop("cash_reserve_chf"), "clés manquantes"),
        (lambda d: d["limits"].update(plafond="1"), "clés inconnues"),
        (lambda d: d["categories"].update(GRADING={"min_autonomy_level": 1}), "non délégables"),
        (lambda d: d["categories"].update(ADMIN={"min_autonomy_level": 1}), "non délégables"),
        (lambda d: d["categories"]["STOCK"].update(min_autonomy_level=5), "min_autonomy_level"),
        (lambda d: d["categories"]["STOCK"].update(extra=1), "extra"),
        (lambda d: d["suppliers"].append({**SUPPLIERS[0], "payment_methods": ["CARD"]}), "interdits"),
        (lambda d: d["suppliers"].append(dict(SUPPLIERS[0])), "en double"),
        (lambda d: d["suppliers"].append({**SUPPLIERS[0], "supplier_id": "X Y"}), "supplier_id"),
        (lambda d: d["categories"].pop("ADVERTISING"), "non déléguées"),
        (lambda d: d.update(valid_from="2027-02-01"), "valid_until"),
        (lambda d: d.update(valid_from="10.10.2026"), "valid_from"),
        (lambda d: d["approval"].update(approved_at="2026-10-10T09:00:00"), "fuseau"),
        (lambda d: d["approval"].update(approved_at=datetime(2026, 10, 10, 9)), "naïf"),
        (lambda d: d.update(suppliers={"a": 1}), "liste attendue"),
        (lambda d: d.update(limits=None), "limits"),
        (lambda d: d.update(mandate_version="v 1"), "mandate_version"),
        (lambda d: d.update(status=""), "status"),
        (lambda d: d["paypal"].update(fee_pct="0.5"), "paypal.fee_pct"),
        (lambda d: d["limits"].update(cash_reserve_chf=None), "cash_reserve_chf"),
    ],
)
def test_invalid_mandate_documents(mutate, fragment: str) -> None:
    data = signed_data(sign=False)
    mutate(data)
    errors = validate_mandate_data(data)
    assert any(fragment in e for e in errors), errors
    with pytest.raises(MandateError):
        parse_mandate(data)


def test_mandate_loading_errors(tmp_path: Path) -> None:
    assert validate_mandate_data(["x"]) == ["document de mandat : mapping YAML attendu"]
    with pytest.raises(MandateError, match="illisible"):
        load_mandate(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [", encoding="utf-8")
    with pytest.raises(MandateError, match="YAML"):
        load_mandate(bad)
    lst = tmp_path / "lst.yaml"
    lst.write_text("- 1\n", encoding="utf-8")
    with pytest.raises(MandateError, match="mapping"):
        load_mandate(lst)


def test_shipped_template_has_no_supplier_and_no_secret() -> None:
    text = DEFAULT_MANDATE_PATH.read_text(encoding="utf-8")
    assert TEMPLATE["suppliers"] == []
    for word in ("IBAN:", "password", "mot de passe:", "@paypal"):
        assert word not in text
    assert TEMPLATE["approval"] == {"approved_by": None, "approved_at": None, "fingerprint_sha256": None,
                                    "revoked_at": None}  # fmt: skip


def test_cli_prints_fingerprint(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["fingerprint", str(DEFAULT_MANDATE_PATH)]) == 0
    out = capsys.readouterr().out
    assert template().fingerprint in out and "INACTIF" in out and "limits.per_transaction_chf" in out
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(signed_data(), allow_unicode=True), encoding="utf-8")
    assert main(["fingerprint", str(path)]) == 0
    assert "à remplir   : rien" in capsys.readouterr().out
    broken = tmp_path / "x.yaml"
    broken.write_text("mandate_version: 1\n", encoding="utf-8")
    assert main(["fingerprint", str(broken)]) == 2


def test_reason_tables_complete_and_ordered() -> None:
    assert set(REASON_OUTCOME) == set(SpendReason) == set(SPEND_REASON_LABELS_FR)
    d = decide(stock_req(product_language="EN", amount=D("600")))
    assert d.reasons[0] == R.NON_FR_PRODUCT.value and R.ABOVE_TRANSACTION_CAP.value in d.reasons
    assert len(d.labels_fr) == len(d.reasons) + len(d.warnings)
    assert OK.severity < HUMAN.severity < REJECTED.severity


def test_yaml_timestamp_signature_accepted(tmp_path: Path) -> None:
    data = signed_data(lambda d: d["approval"].update(
        approved_at=datetime(2026, 10, 10, 9, tzinfo=UTC)))  # fmt: skip
    path = tmp_path / "m.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert not load_mandate(path).is_active(NOW)  # empreinte du coffre absente : jamais actif (MOT-05)
    assert load_mandate(path, expected_fingerprint=data["approval"]["fingerprint_sha256"]).is_active(NOW)


# ------------------------------------------------------------------------- document lisible


def test_delegation_doc_mirrors_template_and_paypal_examples() -> None:
    text = (REPO / "docs" / "00-pilotage" / "DELEGATION_AUTONOMIE.md").read_text(encoding="utf-8")
    for key in TEMPLATE["limits"]:
        assert f"limits.{key}" in text, key
    for category in TEMPLATE["categories"]:
        assert f"`{category}`" in text, category
    model = template().paypal
    for amount, currency, shown in (("40", "CHF", "1,91"), ("100", "CHF", "3,95"), ("450", "CHF", "15,85"),
                                    ("937.50", "EUR", "69,93")):  # fmt: skip
        assert f"{paypal_cost(D(amount), currency, model):.2f}".replace(".", ",") == shown
        assert f"| {shown} |" in text
    for forbidden in ("signer un contrat", "endetter", "hors liste blanche", "PayPal dédié ou virement préparé"):
        assert forbidden.lower() in text.lower(), forbidden
    assert "Révocation de la dépense en une action" in text
    assert text.rstrip().rsplit("\n## ", 1)[-1].startswith("Validation humaine requise")


def test_signature_date_without_time_is_accepted() -> None:
    m = signed(lambda d: d["approval"].update(approved_at="2026-10-10"))
    assert m.approval.approved_at == datetime(2026, 10, 10, tzinfo=TZ) and m.is_active(NOW)


def test_envelope_consumption_survives_new_mandate_version() -> None:
    v1 = signed(no_fees)
    ledger = SpendLedger()
    earlier = NOW - timedelta(days=1)
    approve_and_record(ledger, req(amount=D("250"), idempotency_key="FICTIF-V-1", requested_at=earlier), v1,
                       snapshot=treasury(as_of=earlier), stoploss=status(as_of=earlier))  # fmt: skip
    v2 = signed(lambda d: (no_fees(d), d.update(mandate_version="mandat-v2-FICTIF"),
                           d["limits"].update(per_transaction_chf="600")))  # fmt: skip
    decision = decide(req(amount=D("60"), idempotency_key="FICTIF-V-2"), v2, ledger)
    assert decision.has(R.ABOVE_CATEGORY_ENVELOPE) and decision.context.category_committed_before_chf == D("250")


def test_tampered_mandate_never_provides_payee_reference() -> None:
    data = signed_data()
    data["suppliers"][1]["payee_ref"] = "coffre:beneficiaires/AUTRE"  # modification après signature
    tampered = parse_mandate(data)
    decision = decide(stock_req(payment_method=PaymentMethod.BANK_TRANSFER), tampered)
    assert decision.has(R.MANDATE_FINGERPRINT_MISMATCH)
    assert decision.transfer_draft is not None and decision.transfer_draft.payee_ref is None
