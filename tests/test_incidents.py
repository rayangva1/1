"""Tests du workflow incident (BP §12), du journal d'audit append-only et de l'idempotence.

Les adaptateurs Postgres sont testés sur une base jetable (migrations du dépôt) si PostgreSQL 16
et le pilote psycopg sont disponibles ; sinon ces tests sont ignorés avec la raison exacte.
Toutes les références sont FICTIVES.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import httpx
import pytest
from pokeshop.audit import (
    REDACTED,
    ActorKind,
    AuditError,
    ClaimStatus,
    IdempotencyError,
    InMemoryAuditLog,
    InMemoryIdempotencyStore,
    PostgresAuditLog,
    PostgresIdempotencyStore,
    payload_sha256,
    redact,
    to_jsonable,
)
from pokeshop.incidents import (
    ALL_WRITES,
    INCIDENT_CATALOG,
    Escalation,
    Incident,
    IncidentCode,
    IncidentError,
    IncidentManager,
    IncidentScope,
    IncidentStatus,
    LogNotifier,
    MultiNotifier,
    PostgresIncidentSink,
    Severity,
    WebhookNotifier,
    codes_for_reasons,
)
from pokeshop.models import Reason

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
T0 = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self, **kw: int) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def audit(clock: Clock) -> InMemoryAuditLog:
    return InMemoryAuditLog(clock=clock)


@pytest.fixture
def notifier() -> LogNotifier:
    return LogNotifier()


def manager(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock, **kw: Any) -> IncidentManager:
    return IncidentManager(audit=audit, notifier=notifier, clock=clock, **kw)


# ------------------------------------------------------------------------ catalogue


def test_catalog_covers_sop_codes() -> None:
    assert [c.value for c in IncidentCode] == [f"INC-{i:02d}" for i in range(1, 17)]
    assert set(INCIDENT_CATALOG) == set(IncidentCode)
    critical = {c for c, spec in INCIDENT_CATALOG.items() if spec.severity is Severity.CRITIQUE}
    assert critical == {IncidentCode.INC_06, IncidentCode.INC_07, IncidentCode.INC_10, IncidentCode.INC_11, IncidentCode.INC_14}
    assert Severity.CRITIQUE.sop_label == "S1" and Severity.MAJEUR.sop_label == "S2" and Severity.MINEUR.sop_label == "S3"


def test_codes_for_reasons() -> None:
    reasons = [Reason.PRICE_ANOMALY.value, Reason.ZERO_PRICE.value, Reason.LANGUAGE_MISMATCH.value,
               Reason.BELOW_HARD_FLOOR.value, Reason.STALE_OFFER.value, Reason.ABOVE_MARKET.value]
    assert codes_for_reasons(reasons) == [IncidentCode.INC_01, IncidentCode.INC_02, IncidentCode.INC_05, IncidentCode.INC_03]
    assert codes_for_reasons([]) == []


# --------------------------------------------------------------------------- ouverture


def test_open_reference_incident_quarantines_and_notifies(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    inc = mgr.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="Prix fournisseur ×10 sur FICTIF-A-001")
    assert re.fullmatch(r"INC-20261004-[0-9A-F]{8}", inc.incident_id)  # unique entre processus (SEC-14)
    assert (inc.severity, inc.scope, inc.status, inc.escalation_level) == (
        Severity.MAJEUR, IncidentScope.REFERENCE, IncidentStatus.OUVERT, Escalation.E1)
    assert inc.title == "Prix anormal" and inc.target == "FICTIF-P1"
    assert mgr.is_quarantined("FICTIF-P1") and not mgr.is_quarantined("FICTIF-P2") and not mgr.is_quarantined(None)
    assert mgr.quarantined() == {"FICTIF-P1": (inc.incident_id,)}
    assert len(notifier.sent) == 1
    text = notifier.sent[0].text
    assert "[INCIDENT S2] INC-01 — Prix anormal" in text
    assert "Cause probable : Prix fournisseur ×10" in text
    assert "Action proposée : Quarantaine de la référence" in text
    assert "quarantaine de FICTIF-P1" in text
    actions = [e.action for e in audit.events(entity="incident")]
    assert actions == ["incident.open", "incident.notify"]


def test_scopes_apply_the_right_containment(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    mgr.open(code=IncidentCode.INC_08, workflow="fournisseur-site", cause="API boutique refusée")
    assert mgr.is_suspended("fournisseur-site") and not mgr.is_suspended("stock-local") and not mgr.all_writes_suspended
    src = mgr.open(code=IncidentCode.INC_03, supplier_id="fictif_grossiste_a", cause="flux > 24 h")
    assert src.target == "source:fictif_grossiste_a" and mgr.is_suspended("source:fictif_grossiste_a")
    mgr.open(kind="EXERCICE", severity=Severity.MAJEUR, scope=IncidentScope.GLOBAL, cause="exercice FICTIF",
             proposed_action="Tout suspendre")
    assert mgr.all_writes_suspended and mgr.is_suspended("n-importe-quel-workflow")
    assert set(mgr.suspended()) == {"fournisseur-site", "source:fictif_grossiste_a", ALL_WRITES}


def test_duplicate_open_incident_is_returned_once(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    a = mgr.open(code=IncidentCode.INC_02, product_key="FICTIF-P1", cause="langue ambiguë")
    b = mgr.open(code=IncidentCode.INC_02, product_key="FICTIF-P1", cause="langue ambiguë (cycle suivant)")
    assert a.incident_id == b.incident_id and len(mgr.list()) == 1 and len(notifier.sent) == 1
    assert audit.events(action="incident.duplicate")
    sim = mgr.open(code=IncidentCode.INC_02, product_key="FICTIF-P1", cause="langue ambiguë", simulation=True)
    assert sim.incident_id != a.incident_id  # une simulation ne se confond pas avec le réel


def test_critical_incident_demotes_autonomy(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    calls: list[str] = []

    def demote(incident: Incident) -> tuple[int, int]:
        calls.append(incident.incident_id)
        return 3, 2

    mgr = manager(audit, notifier, clock, on_critical=demote)
    inc = mgr.open(code=IncidentCode.INC_06, product_key="FICTIF-P1", cause="2 commandes payées pour 1 unité")
    assert calls == [inc.incident_id]
    assert (inc.autonomy_before, inc.autonomy_after) == (3, 2)
    assert "niveau d'autonomie 3 → 2" in inc.containment
    assert inc.escalation_level is Escalation.E3 and "propriétaire" in inc.decision_expected
    assert "[INCIDENT S1]" in notifier.sent[0].text and "3 → 2" in notifier.sent[0].text
    mgr.open(code=IncidentCode.INC_05, product_key="FICTIF-P2", cause="marge 10 %")
    assert len(calls) == 1  # un incident majeur ne rétrograde pas


def test_simulation_incident_has_no_containment_nor_demotion(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    calls: list[Incident] = []
    mgr = manager(audit, notifier, clock, on_critical=lambda i: calls.append(i) or (2, 1))
    inc = mgr.open(code=IncidentCode.INC_06, product_key="FICTIF-P1", cause="survente simulée", simulation=True)
    assert inc.simulation and inc.containment == () and calls == []
    assert not mgr.is_quarantined("FICTIF-P1")
    assert notifier.sent[0].text.startswith("[SIMULATION] [INCIDENT S1]")


def test_signal_without_containment(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    inc = mgr.open(code=IncidentCode.INC_01, scope=IncidentScope.SOURCE, supplier_id="fictif", cause="lignes ×10",
                   contain=False)
    assert inc.containment == () and mgr.suspended() == {} and len(notifier.sent) == 1
    assert "aucun" in notifier.sent[0].text


def test_open_validation(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    with pytest.raises(IncidentError):
        mgr.open(cause=" ", code=IncidentCode.INC_01, product_key="X")
    with pytest.raises(IncidentError):
        mgr.open(cause="sans code", kind="X", severity=Severity.MINEUR)
    with pytest.raises(IncidentError):
        mgr.open(cause="référence absente", code=IncidentCode.INC_01)
    with pytest.raises(IncidentError):
        mgr.open(cause="source absente", code=IncidentCode.INC_03)
    with pytest.raises(IncidentError):
        mgr.open(cause="workflow absent", code=IncidentCode.INC_08)
    with pytest.raises(IncidentError):
        mgr.get("INC-INCONNU")
    custom = mgr.open(cause="faute de frappe", kind="TYPO", severity="MINEUR", scope="WORKFLOW", workflow="emails",
                      proposed_action="Corriger le modèle")
    assert custom.code is None and custom.escalation_level is None and custom.title == "TYPO"


# ------------------------------------------------------------------- test puis reprise


def test_resume_requires_a_passing_test_and_lifts_containment(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    inc = mgr.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix ×10")
    with pytest.raises(IncidentError):
        mgr.resume(inc.incident_id, actor="agent-12")
    started = mgr.start(inc.incident_id, actor="agent-03")
    assert started.status is IncidentStatus.EN_COURS
    with pytest.raises(IncidentError):
        mgr.start(inc.incident_id, actor="agent-03")
    mgr.record_test(inc.incident_id, test_ref="dry-run SYNC-FICTIF-1", passed=False, actor="agent-12")
    with pytest.raises(IncidentError):
        mgr.resume(inc.incident_id, actor="agent-12")
    clock.tick(minutes=5)
    mgr.record_test(inc.incident_id, test_ref="dry-run SYNC-FICTIF-2", passed=True, actor="agent-12")
    resumed = mgr.resume(inc.incident_id, actor="agent-12")
    assert resumed.status is IncidentStatus.RESOLU and resumed.resolved_by == "agent-12"
    assert resumed.lifted == ("FICTIF-P1",) and not mgr.is_quarantined("FICTIF-P1")
    with pytest.raises(IncidentError):
        mgr.resume(inc.incident_id, actor="agent-12")
    with pytest.raises(IncidentError):
        mgr.record_test(inc.incident_id, test_ref="encore", passed=True, actor="agent-12")
    closed = mgr.close(inc.incident_id, actor="agent-01")
    assert closed.status is IncidentStatus.CLOS
    with pytest.raises(IncidentError):
        mgr.close(inc.incident_id, actor="agent-01")
    assert [e.action for e in audit.events(entity_id=inc.incident_id)] == [
        "incident.open", "incident.notify", "incident.start", "incident.test", "incident.test", "incident.resume",
        "incident.close",
    ]


def test_critical_incident_resume_is_owner_only(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    inc = mgr.open(code=IncidentCode.INC_07, product_key="FICTIF-P1", cause="champ coût publié")
    mgr.record_test(inc.incident_id, test_ref="test_publish OK", passed=True, actor="agent-12")
    with pytest.raises(IncidentError):
        mgr.resume(inc.incident_id, actor="agent-12", actor_kind=ActorKind.AGENT)
    assert audit.events(action="incident.resume_refused")
    done = mgr.resume(inc.incident_id, actor="propriétaire", actor_kind=ActorKind.PROPRIETAIRE)
    assert done.status is IncidentStatus.RESOLU


def test_containment_held_by_two_incidents(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    a = mgr.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix ×10")
    b = mgr.open(code=IncidentCode.INC_05, product_key="FICTIF-P1", cause="marge sous 12 %")
    for inc in (a, b):
        mgr.record_test(inc.incident_id, test_ref="ok", passed=True, actor="agent-12")
    assert mgr.resume(a.incident_id, actor="agent-12").lifted == ()
    assert mgr.is_quarantined("FICTIF-P1")
    assert mgr.resume(b.incident_id, actor="agent-12").lifted == ("FICTIF-P1",)
    assert not mgr.is_quarantined("FICTIF-P1")
    assert mgr.summary()["RESOLU"] == 2 and mgr.summary()["CRITIQUE_OUVERTS"] == 0


def test_list_filters(audit: InMemoryAuditLog, notifier: LogNotifier, clock: Clock) -> None:
    mgr = manager(audit, notifier, clock)
    a = mgr.open(code=IncidentCode.INC_01, product_key="P1", cause="x")
    mgr.open(code=IncidentCode.INC_01, product_key="P2", cause="y")
    mgr.record_test(a.incident_id, test_ref="ok", passed=True, actor="qa")
    mgr.resume(a.incident_id, actor="qa")
    assert len(mgr.list(open_only=True)) == 1
    assert [i.incident_id for i in mgr.list(status=IncidentStatus.RESOLU)] == [a.incident_id]
    assert mgr.notification_for(a.incident_id).cause == "x"


# ---------------------------------------------------------------------- notifications


def test_webhook_notifier_dry_run_by_default(audit: InMemoryAuditLog, clock: Clock) -> None:
    calls: list[httpx.Request] = []
    hook = WebhookNotifier("https://n8n.example.org/webhook/x", transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200)))
    mgr = IncidentManager(audit=audit, notifier=hook, clock=clock)
    mgr.open(code=IncidentCode.INC_03, supplier_id="fictif", cause="flux absent")
    assert calls == [] and len(hook.sent) == 1 and mgr.receipts[0].dry_run and not mgr.receipts[0].delivered


def test_webhook_notifier_posts_public_payload(audit: InMemoryAuditLog, clock: Clock) -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200)

    hook = WebhookNotifier("http://n8n:5678/webhook/pokeshop-incidents", dry_run=False, transport=httpx.MockTransport(handler))
    mgr = IncidentManager(audit=audit, notifier=hook, clock=clock)
    mgr.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix ×10", details={"landed_cost": "95.00"})
    assert len(calls) == 1 and mgr.receipts[0].delivered
    body = calls[0]
    assert body["sop"] == "S2" and body["code"] == "INC-01" and body["proposed_action"]
    assert "details" not in body and "95.00" not in json.dumps(body)
    hook.close()


@pytest.mark.parametrize("failure", ["status", "network"])
def test_webhook_failure_never_raises(audit: InMemoryAuditLog, clock: Clock, failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError("n8n injoignable")
        return httpx.Response(500)

    hook = WebhookNotifier("https://n8n.example.org/webhook/x", dry_run=False, transport=httpx.MockTransport(handler))
    mgr = IncidentManager(audit=audit, notifier=MultiNotifier([hook]), clock=clock)
    inc = mgr.open(code=IncidentCode.INC_03, supplier_id="fictif", cause="flux absent")
    assert inc.status is IncidentStatus.OUVERT and not mgr.receipts[0].delivered
    assert audit.events(action="incident.notify")[0].payload["delivered"] is False


def test_webhook_url_rules_and_multi_notifier() -> None:
    with pytest.raises(IncidentError):
        WebhookNotifier("http://n8n.example.org/webhook")
    with pytest.raises(IncidentError):
        WebhookNotifier("ftp://n8n/webhook")
    WebhookNotifier("http://localhost:5678/webhook/x")
    with pytest.raises(IncidentError):
        MultiNotifier([])
    log = LogNotifier(logging.getLogger("test.incidents"))
    hook = WebhookNotifier("https://n8n.example.org/webhook/x")
    receipt = MultiNotifier([hook, log]).send(_sample_notification())
    # E2E-13 : le journal seul n'alerte personne ; webhook simulé => ni « livré » ni silence sur la simulation.
    assert receipt.channel == "webhook-n8n+log" and not receipt.delivered and receipt.dry_run and len(hook.sent) == 1
    assert "webhook-n8n : simulé" in receipt.detail and "log : livré" in receipt.detail


def _sample_notification():
    mgr = IncidentManager(audit=InMemoryAuditLog(), notifier=LogNotifier())
    inc = mgr.open(code=IncidentCode.INC_16, workflow="emails", cause="email client inexact")
    return mgr.notification_for(inc.incident_id)


# ------------------------------------------------------------------------- journal d'audit


def test_audit_chain_is_verifiable_and_tamper_evident(audit: InMemoryAuditLog, clock: Clock) -> None:
    for i in range(3):
        clock.tick(seconds=1)
        audit.append(actor="agent-07", actor_kind=ActorKind.AGENT, action="test.event", entity="essai", entity_id=str(i),
                     payload={"montant": D("10.90"), "jour": date(2026, 10, 4)})
    events = audit.events()
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[0].prev_hash is None and events[1].prev_hash == events[0].row_hash
    assert events[0].payload == {"montant": "10.90", "jour": "2026-10-04"}
    assert audit.verify() == []
    row, payload_json = audit._rows[1]  # altération volontaire (simulation d'un accès direct)
    audit._rows[1] = (row, payload_json.replace("10.90", "1.09"))
    assert any("empreinte invalide" in p for p in audit.verify())


def test_audit_payload_is_frozen_redacted_and_float_free(audit: InMemoryAuditLog) -> None:
    payload: dict[str, Any] = {"liste": [1, 2], "access_token": "shpat_FICTIF", "headers": {"Authorization": "Bearer x"},
                               "idempotency_key": "cle-0001-FICTIF", "iban": "CH00 FICTIF"}
    event = audit.append(actor="a", actor_kind="AGENT", action="test.redact", entity="essai", payload=payload)
    payload["liste"].append(3)
    assert audit.events()[0].payload["liste"] == [1, 2]
    stored = audit.events()[0].payload
    assert stored["access_token"] == REDACTED and stored["headers"]["Authorization"] == REDACTED
    assert stored["iban"] == REDACTED and stored["idempotency_key"] == "cle-0001-FICTIF"
    assert event.row_hash and len(event.row_hash) == 64
    with pytest.raises(AuditError):
        audit.append(actor="a", actor_kind="AGENT", action="test.float", entity="essai", payload={"prix": 10.9})
    with pytest.raises(AuditError):
        audit.append(actor="a", actor_kind="AGENT", action="test.naive", entity="essai", payload={"at": datetime(2026, 1, 1)})
    for bad in ({"actor": " "}, {"action": "Majuscule interdite"}, {"entity": ""}, {"autonomy_level": 5}):
        args: dict[str, Any] = {"actor": "a", "actor_kind": "AGENT", "action": "ok.action", "entity": "e"}
        args.update(bad)
        with pytest.raises(AuditError):
            audit.append(**args)
    with pytest.raises(ValueError):
        audit.append(actor="a", actor_kind="ROBOT", action="ok.action", entity="e")


def test_audit_filters_and_has_no_mutation_api(audit: InMemoryAuditLog) -> None:
    audit.append(actor="a", actor_kind="AGENT", action="x.one", entity="product", entity_id="P1")
    audit.append(actor="a", actor_kind="AGENT", action="x.two", entity="product", entity_id="P2")
    assert len(audit.events(entity="product")) == 2
    assert [e.entity_id for e in audit.events(entity_id="P2")] == ["P2"]
    assert [e.action for e in audit.events(action="x.one")] == ["x.one"]
    assert len(audit) == 2
    for name in ("update", "delete", "remove", "clear", "truncate", "edit"):
        assert not hasattr(audit, name)


def test_to_jsonable_and_redact() -> None:
    from enum import Enum

    class E(Enum):
        A = "a"

    data = {"d": D("1.50"), "e": E.A, "s": {3, 1}, "t": (1, 2), "td": timedelta(minutes=2), "n": None, "b": True}
    assert to_jsonable(data) == {"d": "1.50", "e": "a", "s": [1, 3], "t": [1, 2], "td": "120s", "n": None, "b": True}
    with pytest.raises(TypeError):
        to_jsonable(D("NaN"))
    with pytest.raises(TypeError):
        to_jsonable(object())
    assert redact([{"password": "x", "ok": 1}]) == [{"password": REDACTED, "ok": 1}]
    assert payload_sha256({"a": D("1.0")}) == payload_sha256({"a": D("1.0")})


# ----------------------------------------------------------------------------- idempotence


def test_in_memory_idempotency_semantics() -> None:
    store = InMemoryIdempotencyStore()
    sha_a, sha_b = "a" * 64, "b" * 64
    assert store.claim("scope", "cle-00001", sha_a, now=T0)[0] is ClaimStatus.NEW
    assert store.claim("scope", "cle-00001", sha_a, now=T0)[0] is ClaimStatus.DUPLICATE_EN_COURS
    assert store.claim("scope", "cle-00001", sha_b, now=T0)[0] is ClaimStatus.CONFLICT
    rec = store.complete("scope", "cle-00001", {"ok": True}, now=T0)
    assert rec.status == "TERMINE" and rec.response == {"ok": True}
    assert store.claim("scope", "cle-00001", sha_a, now=T0)[0] is ClaimStatus.DUPLICATE_TERMINE
    with pytest.raises(IdempotencyError):
        store.fail("scope", "cle-00001", {}, now=T0)
    store.release("scope", "cle-00001")  # sans effet sur une clé close
    assert store.get("scope", "cle-00001").status == "TERMINE"
    assert store.claim("scope", "cle-00002", sha_a, now=T0)[0] is ClaimStatus.NEW
    store.fail("scope", "cle-00002", {"userErrors": 1}, now=T0)
    assert store.claim("scope", "cle-00002", sha_a, now=T0)[0] is ClaimStatus.DUPLICATE_ECHEC
    store.claim("scope", "cle-00003", sha_a, now=T0)
    store.release("scope", "cle-00003")
    assert store.get("scope", "cle-00003") is None
    with pytest.raises(IdempotencyError):
        store.complete("scope", "cle-inconnue", {}, now=T0)
    for scope, key, sha in (("", "cle-00004", sha_a), ("s", "court", sha_a), ("s", "cle-00004", "pas-un-sha")):
        with pytest.raises(IdempotencyError):
            store.claim(scope, key, sha, now=T0)


# ----------------------------------------------------------------------- Postgres (intégration)


def _psql_prefix() -> list[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser"):
        return ["runuser", "-u", "postgres", "--"]
    return []


def _psql(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
    psql = shutil.which("psql")
    assert psql is not None
    return subprocess.run([*_psql_prefix(), psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"],
                          input=sql, capture_output=True, text=True, timeout=120, check=False)


@pytest.fixture(scope="module")
def pg_connect() -> Iterator[Callable[[str], Callable[[], Any]]]:
    """Base jetable migrée + comptes de connexion FICTIFS ; renvoie une fabrique de connexions par rôle."""
    psycopg = pytest.importorskip("psycopg", reason="pilote psycopg absent : adaptateurs Postgres non testés")
    if shutil.which("psql") is None:
        pytest.skip("psql introuvable")
    if _psql("SELECT 1;").returncode != 0:
        subprocess.run(["service", "postgresql", "start"], capture_output=True, check=False, timeout=60)
        if _psql("SELECT 1;").returncode != 0:
            pytest.skip("PostgreSQL injoignable")
    suffix = uuid.uuid4().hex[:8]
    name = f"pokeshop_integ_{os.getpid()}_{suffix}"
    password = uuid.uuid4().hex
    roles = {"engine": f"pk_engine_{suffix}", "owner": f"pk_owner_{suffix}"}
    assert _psql(f'CREATE DATABASE "{name}";').returncode == 0
    try:
        for path in MIGRATIONS:
            out = _psql(path.read_text(encoding="utf-8"), name)
            assert out.returncode == 0, out.stderr
        out = _psql(
            f"CREATE ROLE {roles['engine']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_engine;\n"
            f"CREATE ROLE {roles['owner']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_owner;\n"
        )
        assert out.returncode == 0, out.stderr

        def factory(role: str) -> Callable[[], Any]:
            def connect() -> Any:
                return psycopg.connect(host="127.0.0.1", port=5432, dbname=name, user=roles[role], password=password,
                                       connect_timeout=10)

            return connect

        try:
            factory("engine")().close()
        except Exception as exc:  # pragma: no cover - dépend de pg_hba
            pytest.skip(f"connexion TCP refusée : {exc}")
        yield factory
    finally:
        _psql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')
        _psql(f"DROP ROLE IF EXISTS {roles['engine']}; DROP ROLE IF EXISTS {roles['owner']};")


def test_postgres_audit_log_chain(pg_connect: Callable[[str], Callable[[], Any]]) -> None:
    log = PostgresAuditLog(pg_connect("engine"))
    a = log.append(actor="agent-07", actor_kind=ActorKind.AGENT, action="test.pg", entity="essai", entity_id="1",
                   dry_run=True, autonomy_level=1, payload={"prix": D("144.90"), "token": "secret"}, idempotency_key="cle-pg-0001")
    b = log.append(actor="agent-07", actor_kind="AGENT", action="test.pg", entity="essai", entity_id="2")
    assert b.seq == a.seq + 1 and b.prev_hash == a.row_hash and len(a.row_hash) == 64
    events = log.events(entity="essai")
    assert [e.entity_id for e in events] == ["1", "2"]
    assert events[0].payload == {"prix": "144.90", "token": REDACTED} and events[0].autonomy_level == 1
    assert log.events(entity_id="2")[0].seq == b.seq and log.events(action="inexistant") == ()
    assert log.verify() == []


def test_postgres_audit_log_is_append_only(pg_connect: Callable[[str], Callable[[], Any]]) -> None:
    connect = pg_connect("engine")
    PostgresAuditLog(connect).append(actor="a", actor_kind="AGENT", action="test.pg", entity="essai")
    conn = connect()
    try:
        with pytest.raises(Exception):
            conn.execute("UPDATE pokeshop.audit_log SET actor = 'pirate'")
    finally:
        conn.rollback()
        conn.close()


def test_postgres_idempotency_store(pg_connect: Callable[[str], Callable[[], Any]]) -> None:
    store = PostgresIdempotencyStore(pg_connect("engine"))
    sha_a, sha_b = "a" * 64, "b" * 64
    status, rec = store.claim("shopify:test", "cle-pg-00001", sha_a, now=T0)
    assert status is ClaimStatus.NEW and rec.status == "EN_COURS"
    assert store.claim("shopify:test", "cle-pg-00001", sha_a, now=T0)[0] is ClaimStatus.DUPLICATE_EN_COURS
    assert store.claim("shopify:test", "cle-pg-00001", sha_b, now=T0)[0] is ClaimStatus.CONFLICT
    done = store.complete("shopify:test", "cle-pg-00001", {"data": {"ok": True}}, now=T0)
    assert done.status == "TERMINE" and done.response == {"data": {"ok": True}}
    assert store.claim("shopify:test", "cle-pg-00001", sha_a, now=T0)[0] is ClaimStatus.DUPLICATE_TERMINE
    with pytest.raises(IdempotencyError):
        store.fail("shopify:test", "cle-pg-00001", {}, now=T0)
    store.claim("shopify:test", "cle-pg-00002", sha_a, now=T0)
    store.release("shopify:test", "cle-pg-00002")
    assert store.get("shopify:test", "cle-pg-00002") is None
    store.claim("shopify:test", "cle-pg-00003", sha_a, now=T0)
    assert store.fail("shopify:test", "cle-pg-00003", {"userErrors": []}, now=T0).status == "ECHEC"


def test_postgres_incident_sink(pg_connect: Callable[[str], Callable[[], Any]], clock: Clock) -> None:
    connect = pg_connect("engine")
    audit = PostgresAuditLog(connect)
    mgr = IncidentManager(audit=audit, notifier=LogNotifier(), sink=PostgresIncidentSink(connect), clock=clock)
    inc = mgr.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix ×10", fictif=True)
    mgr.record_test(inc.incident_id, test_ref="ok", passed=True, actor="qa")
    mgr.resume(inc.incident_id, actor="qa")
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT kind, severity, scope, status, escalation_level, resolved_by, fictif, details->>'target' "
            "FROM pokeshop.incidents WHERE details->>'ref' = %s", (inc.incident_id,)
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("INC-01", "MAJEUR", "REFERENCE", "RESOLU", "E1", "qa", True, "FICTIF-P1")]
    assert audit.verify() == []
