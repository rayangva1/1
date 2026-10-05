"""Tests des niveaux d'autonomie (BP §13) et de la porte de gouvernance (autonomie + stop-loss + mandat).

Mandat, jetons, montants et références FICTIFS (le mandat signé est construit en mémoire à partir
du gabarit ``config/mandate.v1.yaml`` ; le fichier du dépôt n'est jamais modifié).
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
from pokeshop.audit import InMemoryAuditLog
from pokeshop.autonomy import (
    PROTECTIVE_ACTIONS,
    PURCHASE_ACTIONS,
    REQUIRED_LEVEL,
    SPEND_ACTIONS,
    AutonomyController,
    AutonomyError,
    AutonomyLevel,
    AutonomyRefusedError,
    AutonomyState,
    GateReason,
    GovernanceGate,
    InMemoryAutonomyStore,
    JsonFileAutonomyStore,
    PostgresAutonomyStore,
    WriteAction,
    verify_owner_token,
)
from pokeshop.incidents import IncidentCode, IncidentManager, IncidentScope, LogNotifier, Severity
from pokeshop.mandate import (
    DEFAULT_MANDATE_PATH,
    Mandate,
    MandateOutcome,
    PaymentMethod,
    SpendCategory,
    PayPalBalanceReading,
    SpendRequest,
    TreasurySnapshot,
    mandate_fingerprint,
    parse_mandate,
    treasury_from_registers,
)
from pokeshop.stoploss import (
    AdSpend,
    CapitalMovement,
    ExtensionExposure,
    NetWorthSnapshot,
    ProductMargin,
    StopLossEngine,
    StopLossState,
    hash_owner_token,
    load_stoploss_config,
    net_worth,
)

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
OWNER_HASH = hash_owner_token(OWNER_TOKEN)
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
CONFIG = load_stoploss_config()


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def signed_mandate() -> Mandate:
    data = copy.deepcopy(yaml.safe_load(DEFAULT_MANDATE_PATH.read_text(encoding="utf-8")))
    data["valid_from"], data["valid_until"] = "2026-10-10", "2027-01-31"
    data["limits"].update(per_transaction_chf="500", per_month_chf="3000", stock_budget_chf="3000",
                          ads_daily_cap_chf="33", email_daily_send_quota=20)
    for name, value in {"STOCK": "2700", "ACCESSORIES": "300", "SAMPLES": "100", "SITE_TOOLS": "1500",
                        "DA_CONTENT": "400", "PACKAGING": "300", "SHIPPING": "600", "ADVERTISING": "500"}.items():
        data["categories"][name]["envelope_chf"] = value
    data["suppliers"] = [
        {"supplier_id": "FICTIF_EMBALLAGES", "label": "Emballages (fictif)", "categories": ["PACKAGING"],
         "payment_methods": ["PAYPAL"], "validated_on": "2026-10-10", "due_diligence_ref": "checklist FICTIF",
         "payee_ref": "coffre:beneficiaires/FICTIF_EMBALLAGES"},
        {"supplier_id": "FICTIF_PUB", "label": "Pub (fictif)", "categories": ["ADVERTISING"],
         "payment_methods": ["PAYPAL"], "validated_on": "2026-10-10", "due_diligence_ref": "checklist FICTIF",
         "payee_ref": "coffre:beneficiaires/FICTIF_PUB"},
    ]
    data["approval"] = {"approved_by": "FICTIF Propriétaire", "approved_at": "2026-10-10T09:00:00+02:00",
                        "fingerprint_sha256": None, "revoked_at": None}
    data["approval"]["fingerprint_sha256"] = mandate_fingerprint(data)
    # empreinte reportée au coffre par la propriétaire (POKESHOP_MANDATE_FINGERPRINT) : sans elle, inactif
    return parse_mandate(data, expected_fingerprint=data["approval"]["fingerprint_sha256"])


def template_mandate() -> Mandate:
    return parse_mandate(yaml.safe_load(DEFAULT_MANDATE_PATH.read_text(encoding="utf-8")))


def state(**kw: Any) -> StopLossState:
    base: dict[str, Any] = dict(
        as_of=NOW,
        stock_budget_chf=D("3000"),
        cash_available_chf=D("5000"),
        capital_movements=(CapitalMovement(movement_id="FICTIF_APPORT_1", at=NOW - timedelta(days=30),
                                           kind="CONTRIBUTION", amount=D("8000")),),
        net_worth=NetWorthSnapshot(as_of=NOW, cash_chf=D("8000")),
        ads_daily_cap_chf=D("33"),
    )
    base.update(kw)
    return StopLossState(**base)


GLOBAL_LOSS = {"net_worth": NetWorthSnapshot(as_of=NOW, cash_chf=D("6000"))}
CASH_LOW = {"cash_available_chf": D("1000")}
PRODUCT_LOW = {"products": (ProductMargin(product_key="FICTIF-P1", contribution_chf=D("5"), contribution_pct=D("0.05")),)}
EXTENSION_HIGH = {"extensions": (ExtensionExposure(extension="FICTIF_ALPHA", stock_value_at_cost=D("900"),
                                                   first_stocked_at=NOW - timedelta(days=5),
                                                   last_sale_at=NOW - timedelta(days=1)),)}
ADS_CUT = {"ad_spends": (AdSpend(campaign_id="FICTIF-CAMP-1", day=NOW.date(), amount=D("25")),)}


class Rig:
    """Porte de gouvernance complète avec dépendances en mémoire."""

    def __init__(self, *, level: int = 2, st: StopLossState | None = None, mandate: Mandate | None = None,
                 real: bool = True, no_state: bool = False) -> None:
        self.clock = Clock()
        self.audit = InMemoryAuditLog(clock=self.clock)
        self.autonomy = AutonomyController(audit=self.audit, owner_token_sha256=OWNER_HASH, default_level=level,
                                           clock=self.clock)
        self.engine = StopLossEngine(CONFIG, owner_token_sha256=OWNER_HASH)
        self.notifier = LogNotifier()
        self.incidents = IncidentManager(audit=self.audit, notifier=self.notifier,
                                         on_critical=self.autonomy.on_critical_incident, clock=self.clock)
        self.state = None if no_state else (st or state())
        self.mandate = mandate
        self.paypal: PayPalBalanceReading | None = PayPalBalanceReading(
            as_of=NOW, balance_chf=D("500"), source="relevé PayPal FICTIF", recorded_by="agent-05-finance")
        self.gate = GovernanceGate(
            self.autonomy, audit=self.audit, stoploss_engine=self.engine, state_provider=lambda: self.state,
            mandate_provider=lambda: self.mandate, incidents=self.incidents, real_writes_enabled=real, clock=self.clock,
            treasury_provider=lambda: treasury_from_registers(self.state, self.paypal),
        )


@pytest.fixture
def rig() -> Rig:
    return Rig(mandate=signed_mandate())


def spend(amount: str = "40", category: SpendCategory = SpendCategory.PACKAGING, supplier: str = "FICTIF_EMBALLAGES",
          key: str = "FICTIF-SPEND-0001", **kw: Any) -> SpendRequest:
    base: dict[str, Any] = dict(amount=amount, currency="CHF", supplier_id=supplier, category=category,
                                payment_method=PaymentMethod.PAYPAL, purpose="Étuis d'expédition FICTIFS",
                                idempotency_key=key, requested_by="agent-05", requested_at=NOW,
                                amount_source="devis FICTIF n°1")
    base.update(kw)
    return SpendRequest(**base)


TREASURY = TreasurySnapshot(as_of=NOW, cash_available_chf=D("5000"), paypal_balance_chf=D("500"))


# ------------------------------------------------------------------------------- niveaux


def test_required_levels_follow_bp_section_13() -> None:
    by_level = {lv: {a for a, req in REQUIRED_LEVEL.items() if req == lv} for lv in AutonomyLevel}
    assert by_level[AutonomyLevel.SIMULATION] == {WriteAction.FREEZE, WriteAction.UNPUBLISH_PRODUCT,
                                                  WriteAction.CUT_CAMPAIGN, WriteAction.PROPOSE_PURCHASE,
                                                  WriteAction.SPEND_WITHIN_MANDATE}
    assert by_level[AutonomyLevel.SYNC_APPROVED] == {WriteAction.SAVE_DRAFT_PRODUCT, WriteAction.SYNC_PRICE,
                                                     WriteAction.SYNC_STOCK, WriteAction.UPDATE_APPROVED_PRODUCT}
    assert by_level[AutonomyLevel.PUBLISH_AND_CAMPAIGNS] == {WriteAction.PUBLISH_NEW_PRODUCT, WriteAction.APPLY_PROMOTION,
                                                             WriteAction.LAUNCH_CAMPAIGN}
    assert by_level[AutonomyLevel.AUTO_REORDER] == {WriteAction.AUTO_REORDER}
    assert set(REQUIRED_LEVEL) == set(WriteAction)
    assert PROTECTIVE_ACTIONS <= {a for a, lv in REQUIRED_LEVEL.items() if lv == 1}
    assert WriteAction.AUTO_REORDER in SPEND_ACTIONS & PURCHASE_ACTIONS


def test_default_level_is_one_and_dry_run_is_always_allowed() -> None:
    ctl = AutonomyController(audit=InMemoryAuditLog(), owner_token_sha256="")
    assert ctl.level is AutonomyLevel.SIMULATION and ctl.state.changed_by == "configuration"
    for action in WriteAction:
        assert ctl.check(action, dry_run=True).allowed
    assert not ctl.check(WriteAction.SYNC_PRICE, dry_run=False).allowed
    assert ctl.check(WriteAction.FREEZE, dry_run=False).allowed
    with pytest.raises(AutonomyError):
        AutonomyController(audit=InMemoryAuditLog(), default_level=5)


def test_lowering_is_free_raising_is_owner_only_one_step_at_a_time() -> None:
    audit = InMemoryAuditLog()
    ctl = AutonomyController(audit=audit, owner_token_sha256=OWNER_HASH, default_level=2)
    with pytest.raises(AutonomyRefusedError):
        ctl.lower(3, actor="agent-01", reason="tentative de hausse")
    with pytest.raises(AutonomyRefusedError):
        ctl.raise_level(3, owner_token="mauvais-jeton-0000000000", reason="hausse")
    assert audit.events(action="autonomy.raise_refused")
    with pytest.raises(AutonomyError):
        ctl.raise_level(4, owner_token=OWNER_TOKEN, reason="saut de niveau")
    with pytest.raises(AutonomyError):
        ctl.raise_level(2, owner_token=OWNER_TOKEN, reason="même niveau")
    state = ctl.raise_level(3, owner_token=OWNER_TOKEN, reason="G4 vert, recette OK (FICTIF)")
    assert state.level == 3 and state.changed_by_role == "PROPRIETAIRE" and state.previous_level == 2
    lowered = ctl.lower(1, actor="agent-12", reason="gel conservatoire")
    assert lowered.level == 1 and ctl.level is AutonomyLevel.SIMULATION
    assert [s.level for s in ctl.history()] == [3, 1]
    with pytest.raises(AutonomyError):
        ctl.lower(1, actor="agent-12", reason=" ")
    with pytest.raises(AutonomyError):
        ctl.lower(0, actor="agent-12", reason="niveau zéro")


def test_raise_refused_without_configured_owner_hash() -> None:
    ctl = AutonomyController(audit=InMemoryAuditLog(), owner_token_sha256="")
    with pytest.raises(AutonomyRefusedError, match="aucune empreinte"):
        ctl.raise_level(2, owner_token=OWNER_TOKEN, reason="pas d'empreinte au coffre")
    assert verify_owner_token(OWNER_TOKEN, OWNER_HASH)
    assert not verify_owner_token("court", OWNER_HASH) and not verify_owner_token(None, OWNER_HASH)
    assert not verify_owner_token(OWNER_TOKEN, None)


def test_critical_incident_restores_previous_level() -> None:
    audit = InMemoryAuditLog()
    ctl = AutonomyController(audit=audit, owner_token_sha256=OWNER_HASH, default_level=3)
    mgr = IncidentManager(audit=audit, notifier=LogNotifier(), on_critical=ctl.on_critical_incident)
    inc = mgr.open(code=IncidentCode.INC_06, product_key="FICTIF-P1", cause="survente")
    assert ctl.level == 2 and (inc.autonomy_before, inc.autonomy_after) == (3, 2)
    mgr.open(code=IncidentCode.INC_07, product_key="FICTIF-P2", cause="champ interne publié")
    assert ctl.level == 1
    mgr.open(code=IncidentCode.INC_10, cause="accès non autorisé")
    assert ctl.level == 1  # plancher
    assert ctl.history()[-1].changed_by_role == "SYSTEME"


def test_force_level_one_is_idempotent() -> None:
    ctl = AutonomyController(audit=InMemoryAuditLog(), owner_token_sha256=OWNER_HASH, default_level=4)
    assert ctl.force_level_one(reason="gel global").level == 1
    assert ctl.force_level_one(reason="gel global") is None
    assert len(ctl.history()) == 1


def test_json_file_store_persists_level(tmp_path: Path) -> None:
    path = tmp_path / "etat" / "autonomie.jsonl"
    first = AutonomyController(JsonFileAutonomyStore(path), audit=InMemoryAuditLog(), owner_token_sha256=OWNER_HASH)
    first.raise_level(2, owner_token=OWNER_TOKEN, reason="C14 FICTIF : ouverture douce")
    second = AutonomyController(JsonFileAutonomyStore(path), audit=InMemoryAuditLog(), owner_token_sha256=OWNER_HASH)
    assert second.level == 2 and second.history()[0].reason.startswith("C14")
    second.demote(reason="incident critique FICTIF")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert JsonFileAutonomyStore(path).current().level == 1
    assert JsonFileAutonomyStore(path).current("autre") is None
    path.write_text(path.read_text(encoding="utf-8") + "{pas du json}\n", encoding="utf-8")
    with pytest.raises(AutonomyError):
        JsonFileAutonomyStore(path).current()


def test_in_memory_store_scopes() -> None:
    store = InMemoryAutonomyStore()
    store.append(AutonomyState(scope="campagnes", level=1, changed_by="x", changed_by_role="SYSTEME", reason="r", at=NOW))
    assert store.current() is None and store.current("campagnes").level == 1
    assert store.history("campagnes") and store.history() == ()


# ------------------------------------------------------------------------ porte de gouvernance


def test_dry_run_always_allowed_even_when_frozen() -> None:
    rig = Rig(level=1, st=state(**GLOBAL_LOSS), mandate=None, real=False)
    decision = rig.gate.authorize(WriteAction.PUBLISH_NEW_PRODUCT, dry_run=True, product_key="FICTIF-P1")
    assert decision.allowed and decision.dry_run and decision.reasons == (GateReason.DRY_RUN.value,)
    assert rig.incidents.list() == ()  # une simulation n'évalue pas le stop-loss


def test_real_write_allowed_with_level_mandate_and_no_stoploss(rig: Rig) -> None:
    decision = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1", workflow="fournisseur-site")
    assert decision.allowed and not decision.dry_run and decision.reasons == ()
    assert decision.stoploss is not None and not decision.stoploss.global_frozen
    assert rig.audit.events(action="gate.allow")


def test_real_write_refused_when_service_in_simulation() -> None:
    rig = Rig(mandate=signed_mandate(), real=False)
    decision = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert not decision.allowed and decision.has(GateReason.REAL_WRITES_DISABLED)


def test_level_too_low_is_refused(rig: Rig) -> None:
    decision = rig.gate.authorize(WriteAction.PUBLISH_NEW_PRODUCT, dry_run=False, product_key="FICTIF-P1")
    assert not decision.allowed and decision.has(GateReason.AUTONOMY_LEVEL_TOO_LOW)
    assert decision.required_level == 3 and decision.current_level == 2
    assert rig.audit.events(action="gate.refuse")


@pytest.mark.parametrize("problem", ["absent", "stale", "future"])
def test_unavailable_or_stale_stoploss_state_fails_closed(problem: str) -> None:
    if problem == "absent":
        rig = Rig(mandate=signed_mandate(), no_state=True)
    else:
        delta = timedelta(days=2) if problem == "stale" else timedelta(hours=-2)
        rig = Rig(mandate=signed_mandate(), st=state(as_of=NOW - delta, net_worth=NetWorthSnapshot(as_of=NOW - delta, cash_chf=D("8000"))))
    decision = rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P1")
    assert not decision.allowed and decision.has(GateReason.STOPLOSS_UNAVAILABLE)
    assert rig.gate.last_stoploss_error
    protective = rig.gate.authorize(WriteAction.UNPUBLISH_PRODUCT, dry_run=False, product_key="FICTIF-P1")
    assert protective.allowed


def test_global_freeze_refuses_everything_opens_incident_and_returns_to_level_one() -> None:
    rig = Rig(level=3, st=state(**GLOBAL_LOSS), mandate=signed_mandate())
    decision = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1")
    assert not decision.allowed and decision.has(GateReason.STOPLOSS_GLOBAL_FREEZE)
    assert decision.current_level == 1 and rig.autonomy.level == 1
    assert decision.incident_id is not None
    incident = rig.incidents.get(decision.incident_id)
    assert (incident.code, incident.severity, incident.scope) == (IncidentCode.INC_09, Severity.CRITIQUE, IncidentScope.GLOBAL)
    assert rig.incidents.all_writes_suspended and rig.engine.frozen
    again = rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P1")
    assert again.incident_id == decision.incident_id and len(rig.incidents.list()) == 1
    for action in PROTECTIVE_ACTIONS:
        assert rig.gate.authorize(action, dry_run=False, product_key="FICTIF-P1").allowed
    # Les métriques redeviennent bonnes : le gel reste verrouillé jusqu'au réarmement par la propriétaire.
    rig.state = state()
    rig.gate.invalidate()
    still = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert still.has(GateReason.STOPLOSS_GLOBAL_FREEZE)
    rig.engine.rearm(OWNER_TOKEN, "Valeur nette examinée, reprise décidée (FICTIF)", now=NOW, state=rig.state,
                     attested_reference_chf=net_worth(rig.state.net_worth, rig.engine.config).total)
    rig.gate.invalidate()
    after = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert not after.has(GateReason.STOPLOSS_GLOBAL_FREEZE)
    assert after.has(GateReason.AUTONOMY_LEVEL_TOO_LOW)  # niveau non restauré par le réarmement
    assert after.has(GateReason.ALL_WRITES_SUSPENDED)  # l'incident global reste à reprendre après test


def test_enforce_applies_freeze_effects_immediately() -> None:
    healthy = Rig(level=3, mandate=signed_mandate())
    assert healthy.gate.enforce() == (healthy.gate.stoploss_status()[0], None)
    loss = Rig(level=3, st=state(**GLOBAL_LOSS), mandate=signed_mandate())
    status, incident_id = loss.gate.enforce(actor="workflow:stop-loss")
    assert status is not None and status.global_frozen and incident_id is not None
    assert loss.autonomy.level == 1 and loss.incidents.all_writes_suspended
    manual = Rig(level=2, mandate=signed_mandate(), no_state=True)
    manual.engine.freeze("agent-12", "débit inconnu sur le relevé FICTIF", NOW)
    status, incident_id = manual.gate.enforce(actor="agent-12")
    assert status is None and incident_id is not None
    assert "débit inconnu" in manual.incidents.get(incident_id).cause and manual.autonomy.level == 1


def test_product_stoploss_blocks_sale_but_not_price_fix() -> None:
    rig = Rig(level=3, st=state(**PRODUCT_LOW), mandate=signed_mandate())
    publish = rig.gate.authorize(WriteAction.PUBLISH_NEW_PRODUCT, dry_run=False, product_key="FICTIF-P1")
    assert not publish.allowed and publish.has(GateReason.STOPLOSS_PRODUCT)
    promo = rig.gate.authorize(WriteAction.APPLY_PROMOTION, dry_run=False, product_key="FICTIF-P1")
    assert promo.has(GateReason.STOPLOSS_PRODUCT)
    assert rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1").allowed
    assert rig.gate.authorize(WriteAction.PUBLISH_NEW_PRODUCT, dry_run=False, product_key="FICTIF-P2").allowed


def test_cash_stoploss_blocks_purchases_and_campaigns() -> None:
    rig = Rig(level=4, st=state(**CASH_LOW), mandate=signed_mandate())
    proposal = rig.gate.authorize(WriteAction.PROPOSE_PURCHASE, dry_run=False, extension="FICTIF_ALPHA")
    assert proposal.has(GateReason.STOPLOSS_CASH)
    campaign = rig.gate.authorize(WriteAction.LAUNCH_CAMPAIGN, dry_run=False, campaign_id="FICTIF-CAMP-2",
                                  spend_request=spend(category=SpendCategory.ADVERTISING, supplier="FICTIF_PUB"))
    assert campaign.has(GateReason.STOPLOSS_CASH)
    assert rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P1").allowed


def test_extension_stoploss_blocks_reorder_of_that_extension() -> None:
    rig = Rig(level=4, st=state(**EXTENSION_HIGH), mandate=signed_mandate())
    blocked = rig.gate.authorize(WriteAction.PROPOSE_PURCHASE, dry_run=False, extension="FICTIF_ALPHA")
    assert blocked.has(GateReason.STOPLOSS_EXTENSION)
    assert rig.gate.authorize(WriteAction.PROPOSE_PURCHASE, dry_run=False, extension="FICTIF_BETA").allowed


def test_ads_stoploss_cuts_campaign() -> None:
    rig = Rig(level=3, st=state(**ADS_CUT), mandate=signed_mandate())
    request = spend(category=SpendCategory.ADVERTISING, supplier="FICTIF_PUB", campaign_id="FICTIF-CAMP-1", amount="20")
    cut = rig.gate.authorize(WriteAction.LAUNCH_CAMPAIGN, dry_run=False, campaign_id="FICTIF-CAMP-1",
                             spend_request=request)
    assert not cut.allowed and cut.has(GateReason.STOPLOSS_ADS)
    assert rig.gate.authorize(WriteAction.CUT_CAMPAIGN, dry_run=False, campaign_id="FICTIF-CAMP-1").allowed


def test_mandate_must_be_signed_and_available() -> None:
    unsigned = Rig(mandate=template_mandate())
    decision = unsigned.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert decision.has(GateReason.MANDATE_INACTIVE)
    assert any("MANDATE_NOT_SIGNED" in m for m in decision.messages)
    missing = Rig(mandate=None)
    assert missing.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False).has(GateReason.MANDATE_UNAVAILABLE)
    assert missing.gate.authorize(WriteAction.FREEZE, dry_run=False).allowed


def test_spend_actions_go_through_mandate_check(rig: Rig) -> None:
    missing = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False)
    assert missing.has(GateReason.SPEND_REQUEST_MISSING)
    approved = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=spend())
    assert approved.allowed and approved.mandate_decision is not None
    assert approved.mandate_decision.outcome is MandateOutcome.APPROVED_WITHIN_MANDATE
    above = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, 
                               spend_request=spend(amount="600", key="FICTIF-SPEND-0002"))
    assert not above.allowed and above.pending_human_approval and above.has(GateReason.MANDATE_NEEDS_HUMAN_APPROVAL)
    forbidden = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, 
                                   spend_request=spend(category=SpendCategory.FINANCING, key="FICTIF-SPEND-0003"))
    assert not forbidden.allowed and forbidden.has(GateReason.MANDATE_REJECTED) and not forbidden.pending_human_approval
    ledger = rig.gate.spend_ledger
    assert {e.idempotency_key for e in ledger.entries()} == {"FICTIF-SPEND-0001", "FICTIF-SPEND-0002", "FICTIF-SPEND-0003"}
    replay = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=spend())
    assert replay.allowed and replay.mandate_decision.replayed and len(ledger.entries()) == 3
    conflict = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, 
                                  spend_request=spend(amount="41"))
    assert conflict.has(GateReason.MANDATE_REJECTED) and "IDEMPOTENCY_CONFLICT" in conflict.mandate_decision.reasons


def test_approved_spend_blocked_by_gate_is_not_booked() -> None:
    rig = Rig(level=1, mandate=signed_mandate())
    rig.incidents.open(code=IncidentCode.INC_14, cause="agent hors mandat (exercice FICTIF)")
    decision = rig.gate.authorize(WriteAction.SPEND_WITHIN_MANDATE, dry_run=False, spend_request=spend())
    assert decision.mandate_decision.outcome is MandateOutcome.APPROVED_WITHIN_MANDATE
    assert not decision.allowed and decision.has(GateReason.ALL_WRITES_SUSPENDED)
    assert rig.gate.spend_ledger.entries() == ()  # aucune enveloppe consommée par une dépense non exécutée
    ads = spend(category=SpendCategory.ADVERTISING, supplier="FICTIF_PUB", campaign_id="FICTIF-CAMP-9", amount="20",
                key="FICTIF-SPEND-0009")
    pending = rig.gate.authorize(WriteAction.LAUNCH_CAMPAIGN, dry_run=False, campaign_id="FICTIF-CAMP-9",
                                 spend_request=ads)
    assert pending.mandate_decision.outcome is MandateOutcome.NEEDS_HUMAN_APPROVAL  # niveau 1 < niveau 3 du mandat
    assert [e.idempotency_key for e in rig.gate.spend_ledger.entries()] == ["FICTIF-SPEND-0009"]


def test_auto_reorder_needs_level_four_and_mandate(rig: Rig) -> None:
    request = spend(category=SpendCategory.STOCK, supplier="FICTIF_EMBALLAGES", key="FICTIF-SPEND-0004",
                    product_key="FICTIF-P1", product_language="FR", extension="FICTIF_ALPHA", justification_ref="abc")
    decision = rig.gate.authorize(WriteAction.AUTO_REORDER, dry_run=False, product_key="FICTIF-P1",
                                  extension="FICTIF_ALPHA", spend_request=request)
    assert not decision.allowed and decision.has(GateReason.AUTONOMY_LEVEL_TOO_LOW)
    assert decision.has(GateReason.MANDATE_REJECTED)  # bénéficiaire non autorisé pour la catégorie STOCK


def test_open_incidents_quarantine_and_suspension_block_writes(rig: Rig) -> None:
    rig.incidents.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix ×10")
    q = rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1")
    assert q.has(GateReason.PRODUCT_QUARANTINED)
    assert rig.gate.authorize(WriteAction.UNPUBLISH_PRODUCT, dry_run=False, product_key="FICTIF-P1").allowed
    rig.incidents.open(code=IncidentCode.INC_08, workflow="stock-local", cause="API refusée")
    s = rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P2", workflow="stock-local")
    assert s.has(GateReason.WORKFLOW_SUSPENDED)
    assert rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P2", workflow="autre").allowed


def test_stoploss_status_is_cached_then_invalidated(rig: Rig) -> None:
    rig.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False)
    evaluations = [e for e in rig.engine.journal if e.event == "EVALUATION"]
    assert len(evaluations) == 1
    rig.gate.invalidate()
    rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False)
    assert len([e for e in rig.engine.journal if e.event == "EVALUATION"]) == 2
    rig.clock.now = NOW + timedelta(minutes=6)
    rig.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False)
    assert len([e for e in rig.engine.journal if e.event == "EVALUATION"]) == 3


def test_gate_without_engine_fails_closed() -> None:
    audit = InMemoryAuditLog()
    ctl = AutonomyController(audit=audit, owner_token_sha256=OWNER_HASH, default_level=2)
    gate = GovernanceGate(ctl, audit=audit, stoploss_engine=None, state_provider=state, mandate_provider=signed_mandate,
                          real_writes_enabled=True, clock=lambda: NOW)
    decision = gate.authorize(WriteAction.SYNC_PRICE, dry_run=False)
    assert decision.has(GateReason.STOPLOSS_UNAVAILABLE) and "non configuré" in (gate.last_stoploss_error or "")


# ------------------------------------------------------------------------- Postgres (intégration)


def _psql(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
    prefix = ["runuser", "-u", "postgres", "--"] if hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser") else []
    return subprocess.run([*prefix, shutil.which("psql") or "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"],
                          input=sql, capture_output=True, text=True, timeout=120, check=False)


@pytest.fixture(scope="module")
def pg_roles() -> Iterator[Callable[[str], Callable[[], Any]]]:
    psycopg = pytest.importorskip("psycopg", reason="pilote psycopg absent : stockage Postgres non testé")
    if shutil.which("psql") is None or _psql("SELECT 1;").returncode != 0:
        pytest.skip("PostgreSQL injoignable")
    suffix = uuid.uuid4().hex[:8]
    name, password = f"pokeshop_auto_{os.getpid()}_{suffix}", uuid.uuid4().hex
    roles = {"engine": f"pk_auto_engine_{suffix}", "owner": f"pk_auto_owner_{suffix}"}
    assert _psql(f'CREATE DATABASE "{name}";').returncode == 0
    try:
        for path in MIGRATIONS:
            out = _psql(path.read_text(encoding="utf-8"), name)
            assert out.returncode == 0, out.stderr
        out = _psql(f"CREATE ROLE {roles['engine']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_engine;\n"
                    f"CREATE ROLE {roles['owner']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_owner;")
        assert out.returncode == 0, out.stderr

        def factory(role: str) -> Callable[[], Any]:
            return lambda: psycopg.connect(host="127.0.0.1", port=5432, dbname=name, user=roles[role], password=password,
                                           connect_timeout=10)

        yield factory
    finally:
        _psql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')
        _psql(f"DROP ROLE IF EXISTS {roles['engine']}; DROP ROLE IF EXISTS {roles['owner']};")


def test_postgres_store_enforces_owner_only_raise(pg_roles: Callable[[str], Callable[[], Any]]) -> None:
    engine_store = PostgresAutonomyStore(pg_roles("engine"))
    owner_store = PostgresAutonomyStore(pg_roles("owner"))
    raise_two = AutonomyState(level=2, changed_by="propriétaire", changed_by_role="PROPRIETAIRE", reason="C14 FICTIF", at=NOW)
    with pytest.raises(Exception):  # un compte moteur ne peut pas se déclarer propriétaire
        engine_store.append(raise_two)
    stored = owner_store.append(raise_two)
    assert stored.level == 2 and stored.previous_level is None
    with pytest.raises(Exception):  # agent : hausse refusée par la contrainte de la base
        engine_store.append(AutonomyState(level=3, changed_by="agent-07", changed_by_role="AGENT", reason="hausse", at=NOW))
    ctl = AutonomyController(engine_store, audit=InMemoryAuditLog(), owner_token_sha256=OWNER_HASH, clock=lambda: NOW)
    assert ctl.level == 2
    ctl.demote(reason="incident critique FICTIF")
    assert ctl.level == 1 and engine_store.current().previous_level == 2
    assert [s.level for s in engine_store.history()] == [2, 1]
