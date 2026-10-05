"""Workflow incident du BP §12 : quarantaine, suspension, notification, test, reprise (agent integrations).

« Prix anormal, langue ambiguë, flux absent, échec paiement, marge sous seuil ou survente →
mise en quarantaine de la référence ou suspension du workflow concerné → notification avec
cause et action proposée → correction → test → reprise. » (BP §12). Catalogue INC-01 à INC-16
et gravités : ``docs/07-ops/SOP_INCIDENTS.md``.

* **Confinement automatique** selon le périmètre : ``REFERENCE`` -> quarantaine de la
  référence ; ``WORKFLOW`` -> suspension du workflow ; ``SOURCE`` -> suspension des achats et
  promesses de ce fournisseur (``source:<id>``) ; ``GLOBAL`` -> toutes les écritures suspendues
  (sauf actions protectrices : dépublier, couper une campagne, geler).
* **Incident critique** (S1) : rappel ``on_critical`` (branché sur
  :meth:`pokeshop.autonomy.AutonomyController.on_critical_incident`) = retour au niveau
  d'autonomie précédent (BP §13).
* **Reprise** uniquement après un test réussi enregistré ; un incident critique ne peut être
  repris que par la propriétaire (SOP §1). Le confinement n'est levé que si aucun autre
  incident ouvert ne le tient.
* **Simulation** : un incident ouvert pendant un cycle en dry-run est tracé et notifié avec la
  mention ``[SIMULATION]`` mais n'applique ni confinement ni rétrogradation.
* Doublon : un incident ouvert de même code et même cible est renvoyé tel quel (pas de
  seconde notification) — un cycle répété ne noie pas la propriétaire.

Une panne de flux fournisseur ne touche jamais au stock local confirmé : ce module ne modifie
aucun stock. Chaque transition est journalisée (:mod:`pokeshop.audit`).
"""

from __future__ import annotations

import builtins
import json
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

import httpx
from pydantic import Field

from .audit import ActorKind, AuditLog, ConnectionFactory, _PgRunner, to_jsonable
from .errors import PokeshopError
from .models import FrozenModel, Reason

__all__ = [
    "IncidentError",
    "Severity",
    "IncidentScope",
    "IncidentStatus",
    "Escalation",
    "IncidentCode",
    "IncidentSpec",
    "INCIDENT_CATALOG",
    "ALL_WRITES",
    "Incident",
    "Notification",
    "NotificationReceipt",
    "Notifier",
    "LogNotifier",
    "WebhookNotifier",
    "MultiNotifier",
    "IncidentSink",
    "PostgresIncidentSink",
    "IncidentManager",
    "codes_for_reasons",
    "source_target",
]

logger = logging.getLogger("pokeshop.incidents")

ALL_WRITES = "*"
"""Cible de suspension globale (incident de périmètre GLOBAL)."""


class IncidentError(PokeshopError, ValueError):
    """Transition d'incident interdite (reprise sans test, réarmement non autorisé…)."""


class Severity(str, Enum):
    """Gravité (valeurs de la colonne ``incidents.severity``) ; correspondance SOP S1/S2/S3."""

    INFO = "INFO"
    MINEUR = "MINEUR"
    MAJEUR = "MAJEUR"
    CRITIQUE = "CRITIQUE"

    @property
    def sop_label(self) -> str:
        """S1 critique, S2 majeur, S3 mineur, INFO (SOP §1)."""
        return {"CRITIQUE": "S1", "MAJEUR": "S2", "MINEUR": "S3", "INFO": "INFO"}[self.value]

    @property
    def rank(self) -> int:
        """Rang de gravité (0 = information)."""
        return {"INFO": 0, "MINEUR": 1, "MAJEUR": 2, "CRITIQUE": 3}[self.value]


class IncidentScope(str, Enum):
    """Périmètre du confinement."""

    REFERENCE = "REFERENCE"
    WORKFLOW = "WORKFLOW"
    SOURCE = "SOURCE"
    GLOBAL = "GLOBAL"


class IncidentStatus(str, Enum):
    """Cycle de vie (valeurs de la colonne ``incidents.status``)."""

    OUVERT = "OUVERT"
    EN_COURS = "EN_COURS"
    RESOLU = "RESOLU"
    CLOS = "CLOS"


class Escalation(str, Enum):
    """Niveaux d'escalade du brief commun (E1 chef de projet + QA, E2 propriétaire 48 h, E3 immédiat)."""

    E1 = "E1"
    E2 = "E2"
    E3 = "E3"


class IncidentCode(str, Enum):
    """Catalogue de ``docs/07-ops/SOP_INCIDENTS.md`` §3."""

    INC_01 = "INC-01"
    INC_02 = "INC-02"
    INC_03 = "INC-03"
    INC_04 = "INC-04"
    INC_05 = "INC-05"
    INC_06 = "INC-06"
    INC_07 = "INC-07"
    INC_08 = "INC-08"
    INC_09 = "INC-09"
    INC_10 = "INC-10"
    INC_11 = "INC-11"
    INC_12 = "INC-12"
    INC_13 = "INC-13"
    INC_14 = "INC-14"
    INC_15 = "INC-15"
    INC_16 = "INC-16"


class IncidentSpec(FrozenModel):
    """Valeurs par défaut d'un code d'incident (titre, gravité, périmètre, action proposée)."""

    title: str
    severity: Severity
    scope: IncidentScope
    proposed_action: str


INCIDENT_CATALOG: dict[IncidentCode, IncidentSpec] = {
    IncidentCode.INC_01: IncidentSpec(
        title="Prix anormal",
        severity=Severity.MAJEUR,
        scope=IncidentScope.REFERENCE,
        proposed_action="Quarantaine de la référence, retour au dernier prix validé, contrôle de l'import "
        "(unité ou carton, devise, HT ou TTC). Les commandes conclues gardent leur prix.",
    ),
    IncidentCode.INC_02: IncidentSpec(
        title="Langue ou identité ambiguë",
        severity=Severity.MAJEUR,
        scope=IncidentScope.REFERENCE,
        proposed_action="Fiche en brouillon, aucun nouveau prix public ; confirmation écrite du fournisseur.",
    ),
    IncidentCode.INC_03: IncidentSpec(
        title="Flux fournisseur absent ou périmé",
        severity=Severity.MAJEUR,
        scope=IncidentScope.SOURCE,
        proposed_action="Achats et nouvelles promesses bloqués pour cette source ; relancer le fournisseur ou "
        "passer en import assisté. Le stock local confirmé continue de se vendre.",
    ),
    IncidentCode.INC_04: IncidentSpec(
        title="Échec de paiement",
        severity=Severity.MAJEUR,
        scope=IncidentScope.WORKFLOW,
        proposed_action="Suspendre les campagnes payantes pendant la panne ; contacter le prestataire ; "
        "rapprocher chaque transaction.",
    ),
    IncidentCode.INC_05: IncidentSpec(
        title="Marge sous seuil",
        severity=Severity.MAJEUR,
        scope=IncidentScope.REFERENCE,
        proposed_action="Vente et promotion bloquées ; revoir le coût rendu ou le prix ; exception seulement "
        "par la propriétaire (C18).",
    ),
    IncidentCode.INC_06: IncidentSpec(
        title="Survente",
        severity=Severity.CRITIQUE,
        scope=IncidentScope.REFERENCE,
        proposed_action="Quarantaine de la référence et suspension de la synchronisation ; servir la commande "
        "payée la plus ancienne ; proposer remboursement intégral ou attente d'un réassort confirmé.",
    ),
    IncidentCode.INC_07: IncidentSpec(
        title="Fuite d'un champ interne ou d'une donnée personnelle",
        severity=Severity.CRITIQUE,
        scope=IncidentScope.REFERENCE,
        proposed_action="Dépublier immédiatement ; corriger le filtre de publication ; contrôler les autres fiches.",
    ),
    IncidentCode.INC_08: IncidentSpec(
        title="Double écriture ou écriture refusée",
        severity=Severity.MAJEUR,
        scope=IncidentScope.WORKFLOW,
        proposed_action="Suspendre le workflow, arrêter les écritures, revenir au dernier état vérifié ; rejouer "
        "la file de reprise avec les mêmes clés d'idempotence.",
    ),
    IncidentCode.INC_09: IncidentSpec(
        title="Stop-loss déclenché",
        severity=Severity.MAJEUR,
        scope=IncidentScope.WORKFLOW,
        proposed_action="Effet automatique du stop-loss ; dossier de décision par le chef de projet ; "
        "le gel global ne se lève que par la propriétaire.",
    ),
    IncidentCode.INC_10: IncidentSpec(
        title="Violation de la sécurité des données personnelles",
        severity=Severity.CRITIQUE,
        scope=IncidentScope.GLOBAL,
        proposed_action="Couper les accès, conserver les preuves, évaluer le risque ; annonce au PFPDT décidée "
        "par la propriétaire (art. 24 LPD).",
    ),
    IncidentCode.INC_11: IncidentSpec(
        title="Lot suspect",
        severity=Severity.CRITIQUE,
        scope=IncidentScope.REFERENCE,
        proposed_action="Quarantaine physique et logique de tout le lot ; réclamation fournisseur ; décision de "
        "la propriétaire.",
    ),
    IncidentCode.INC_12: IncidentSpec(
        title="Allocation annulée ou compte fournisseur coupé",
        severity=Severity.MAJEUR,
        scope=IncidentScope.SOURCE,
        proposed_action="Fermer les précommandes, suspendre les achats chez ce fournisseur, rembourser les "
        "précommandes non servies, basculer sur la deuxième source.",
    ),
    IncidentCode.INC_13: IncidentSpec(
        title="Réclamation d'un titulaire de droits",
        severity=Severity.MAJEUR,
        scope=IncidentScope.REFERENCE,
        proposed_action="Retirer le contenu visé ; transmission au juriste par la propriétaire.",
    ),
    IncidentCode.INC_14: IncidentSpec(
        title="Agent hors mandat",
        severity=Severity.CRITIQUE,
        scope=IncidentScope.GLOBAL,
        proposed_action="Geler l'agent concerné, retour au niveau d'autonomie 1, revue du mandat avec la propriétaire.",
    ),
    IncidentCode.INC_15: IncidentSpec(
        title="Erreurs de préparation ou pertes en série",
        severity=Severity.MAJEUR,
        scope=IncidentScope.WORKFLOW,
        proposed_action="Contrôle renforcé (double scan), envoi contre signature, analyse de cause.",
    ),
    IncidentCode.INC_16: IncidentSpec(
        title="Email client inexact",
        severity=Severity.MAJEUR,
        scope=IncidentScope.WORKFLOW,
        proposed_action="Suspendre l'automatisation concernée ; email rectificatif ; corriger le modèle.",
    ),
}

_REASON_CODES: dict[str, IncidentCode] = {
    Reason.PRICE_ANOMALY.value: IncidentCode.INC_01,
    Reason.ZERO_PRICE.value: IncidentCode.INC_01,
    Reason.ZERO_OR_NEGATIVE_COST.value: IncidentCode.INC_01,
    Reason.LANGUAGE_MISMATCH.value: IncidentCode.INC_02,
    Reason.STALE_OFFER.value: IncidentCode.INC_03,
    Reason.BELOW_HARD_FLOOR.value: IncidentCode.INC_05,
    Reason.BELOW_ORDER_FLOOR_CHF.value: IncidentCode.INC_05,
    Reason.CURRENT_PRICE_BELOW_HARD_FLOOR.value: IncidentCode.INC_05,
}


def codes_for_reasons(reasons: Sequence[str]) -> list[IncidentCode]:
    """Codes d'incident déclenchés par des motifs du moteur de prix (ordre stable, sans doublon)."""
    out: list[IncidentCode] = []
    for r in reasons:
        code = _REASON_CODES.get(r)
        if code is not None and code not in out:
            out.append(code)
    return out


def source_target(supplier_id: str) -> str:
    """Cible de suspension d'une source fournisseur."""
    return f"source:{supplier_id}"


class Incident(FrozenModel):
    """Incident tracé (aucune donnée personnelle de client ici : seulement des références)."""

    incident_id: str
    code: IncidentCode | None = None
    kind: str = Field(min_length=1, max_length=64)
    title: str
    severity: Severity
    scope: IncidentScope
    status: IncidentStatus = IncidentStatus.OUVERT
    escalation_level: Escalation | None = None
    target: str = Field(min_length=1)
    """Référence, workflow, ``source:<fournisseur>`` ou ``*`` selon le périmètre."""
    product_key: str | None = None
    supplier_id: str | None = None
    workflow: str | None = None
    cause: str = Field(min_length=1)
    proposed_action: str = Field(min_length=1)
    decision_expected: str = "aucune"
    details: dict[str, Any] = Field(default_factory=dict)
    opened_at: datetime
    opened_by: str
    simulation: bool = False
    containment: tuple[str, ...] = ()
    autonomy_before: int | None = None
    autonomy_after: int | None = None
    test_ref: str | None = None
    test_passed: bool = False
    tested_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    lifted: tuple[str, ...] = ()
    fictif: bool = False
    dedup_key: str

    @property
    def is_open(self) -> bool:
        """Vrai tant que l'incident n'est ni résolu ni clos."""
        return self.status in (IncidentStatus.OUVERT, IncidentStatus.EN_COURS)


# ------------------------------------------------------------------- notifications


class Notification(FrozenModel):
    """Message au format SOP §4 (cause + action proposée + décision attendue)."""

    incident_id: str
    severity: Severity
    code: str | None
    title: str
    cause: str
    proposed_action: str
    decision_expected: str
    scope: IncidentScope
    target: str
    simulation: bool
    opened_at: datetime
    text: str

    def as_payload(self) -> dict[str, Any]:
        """Charge JSON pour un webhook n8n (sans détail interne ni donnée personnelle)."""
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "sop": self.severity.sop_label,
            "code": self.code,
            "title": self.title,
            "cause": self.cause,
            "proposed_action": self.proposed_action,
            "decision_expected": self.decision_expected,
            "scope": self.scope.value,
            "target": self.target,
            "simulation": self.simulation,
            "opened_at": self.opened_at.isoformat(),
            "text": self.text,
        }


class NotificationReceipt(FrozenModel):
    """Accusé d'envoi (``delivered=False`` en simulation ou en cas d'échec, jamais d'exception)."""

    channel: str
    delivered: bool
    dry_run: bool
    detail: str = ""


@runtime_checkable
class Notifier(Protocol):
    """Canal de notification abstrait (journal applicatif, webhook n8n…)."""

    def send(self, notification: Notification) -> NotificationReceipt:
        """Envoie (ou simule) la notification ; ne lève jamais d'exception de transport."""
        ...


class LogNotifier:
    """Notification dans le journal applicatif ; garde la liste des messages (tests, digest)."""

    channel = "log"

    def __init__(self, log: logging.Logger | None = None) -> None:
        self._log = log or logger
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> NotificationReceipt:
        """Écrit le message (niveau WARNING ; ERROR pour S1)."""
        level = logging.ERROR if notification.severity is Severity.CRITIQUE else logging.WARNING
        self._log.log(level, "%s", notification.text)
        self.sent.append(notification)
        return NotificationReceipt(channel=self.channel, delivered=True, dry_run=False)


class WebhookNotifier:
    """POST JSON vers un webhook n8n. ``dry_run=True`` par défaut : rien n'est envoyé.

    HTTPS exigé, sauf pour un hôte interne sans point (``http://n8n:5678`` dans docker compose)
    ou ``localhost``. Transport httpx injectable (tests). Un échec d'envoi est rendu dans
    l'accusé (jamais d'exception : une notification ratée ne doit pas casser le workflow).
    """

    channel = "webhook-n8n"

    def __init__(
        self,
        url: str,
        *,
        dry_run: bool = True,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        internal = host == "localhost" or "." not in host
        if parsed.scheme not in ("https", "http") or not host:
            raise IncidentError("URL de webhook invalide")
        if parsed.scheme == "http" and not internal:
            raise IncidentError("webhook externe en HTTPS uniquement")
        self.url = url
        self.dry_run = dry_run
        self._client = httpx.Client(transport=transport, timeout=timeout_seconds)
        self.sent: list[dict[str, Any]] = []

    def send(self, notification: Notification) -> NotificationReceipt:
        """Envoie la notification (ou la simule)."""
        payload = notification.as_payload()
        if self.dry_run:
            self.sent.append(payload)
            return NotificationReceipt(channel=self.channel, delivered=False, dry_run=True, detail="simulation")
        try:
            response = self._client.post(self.url, json=payload)
        except httpx.HTTPError as exc:
            return NotificationReceipt(channel=self.channel, delivered=False, dry_run=False, detail=type(exc).__name__)
        if response.status_code >= 300:
            return NotificationReceipt(
                channel=self.channel, delivered=False, dry_run=False, detail=f"HTTP {response.status_code}"
            )
        self.sent.append(payload)
        return NotificationReceipt(channel=self.channel, delivered=True, dry_run=False)

    def close(self) -> None:
        """Ferme le client HTTP."""
        self._client.close()


class MultiNotifier:
    """Diffuse sur plusieurs canaux ; renvoie l'accusé du premier canal livré (sinon le dernier)."""

    channel = "multi"

    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        if not notifiers:
            raise IncidentError("au moins un canal de notification")
        self.notifiers = tuple(notifiers)

    def send(self, notification: Notification) -> NotificationReceipt:
        """Envoie sur chaque canal."""
        receipts = [n.send(notification) for n in self.notifiers]
        delivered = [r for r in receipts if r.delivered]
        return delivered[0] if delivered else receipts[-1]


# --------------------------------------------------------------------- persistance


@runtime_checkable
class IncidentSink(Protocol):
    """Miroir persistant des incidents (table ``pokeshop.incidents``)."""

    def record(self, incident: Incident) -> None:
        """Crée ou met à jour la ligne de l'incident."""
        ...


class PostgresIncidentSink:
    """Écrit les incidents dans ``pokeshop.incidents`` (SQL paramétré, ligne repérée par ``details->>'ref'``).

    Les colonnes ``product_id`` / ``supplier_id`` (clés étrangères internes) restent nulles : la
    référence produit et le fournisseur sont recopiés dans ``details``.
    """

    UPSERT_SQL = (
        "WITH upd AS (UPDATE pokeshop.incidents SET status = %s, escalation_level = %s, resolved_at = %s, "
        "resolved_by = %s, details = %s::jsonb WHERE details->>'ref' = %s RETURNING incident_id) "
        "INSERT INTO pokeshop.incidents (kind, severity, scope, status, escalation_level, workflow, cause, "
        "proposed_action, details, opened_at, resolved_at, resolved_by, fictif) "
        "SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM upd)"
    )

    def __init__(self, connect: ConnectionFactory) -> None:
        self._db = _PgRunner(connect)

    @staticmethod
    def _details(incident: Incident) -> str:
        body = {
            "ref": incident.incident_id,
            "code": incident.code.value if incident.code else None,
            "target": incident.target,
            "product_key": incident.product_key,
            "supplier_id": incident.supplier_id,
            "simulation": incident.simulation,
            "containment": list(incident.containment),
            "test_ref": incident.test_ref,
            "test_passed": incident.test_passed,
            "details": incident.details,
        }
        return json.dumps(to_jsonable(body), sort_keys=True, ensure_ascii=False)

    def record(self, incident: Incident) -> None:
        """Upsert de l'incident."""
        details = self._details(incident)
        esc = incident.escalation_level.value if incident.escalation_level else None
        workflow = incident.workflow or (incident.target if incident.scope is IncidentScope.WORKFLOW else None)
        self._db.run(
            self.UPSERT_SQL,
            (
                incident.status.value,
                esc,
                incident.resolved_at,
                incident.resolved_by,
                details,
                incident.incident_id,
                incident.kind,
                incident.severity.value,
                incident.scope.value,
                incident.status.value,
                esc,
                workflow,
                incident.cause,
                incident.proposed_action,
                details,
                incident.opened_at,
                incident.resolved_at,
                incident.resolved_by,
                incident.fictif,
            ),
            "none",
        )


# ----------------------------------------------------------------------- gestion


OnCritical = Callable[["Incident"], tuple[int, int] | None]


def _fmt_dt(at: datetime) -> str:
    return at.strftime("%d.%m.%Y %H:%M")


class IncidentManager:
    """Ouvre, confine, notifie, teste et reprend les incidents (thread-safe, journalisé)."""

    def __init__(
        self,
        *,
        audit: AuditLog,
        notifier: Notifier | None = None,
        on_critical: OnCritical | None = None,
        sink: IncidentSink | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._audit = audit
        self._notifier: Notifier = notifier or LogNotifier()
        self._on_critical = on_critical
        self._sink = sink
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._incidents: dict[str, Incident] = {}
        self._quarantine: dict[str, set[str]] = {}
        self._suspended: dict[str, set[str]] = {}
        self._seq = 0
        self.receipts: list[NotificationReceipt] = []

    def set_on_critical(self, hook: OnCritical | None) -> None:
        """Branche (ou débranche) la rétrogradation d'autonomie sur incident critique."""
        self._on_critical = hook

    # -- lecture ------------------------------------------------------------------
    def get(self, incident_id: str) -> Incident:
        """Incident par identifiant (IncidentError si inconnu)."""
        with self._lock:
            try:
                return self._incidents[incident_id]
            except KeyError:
                raise IncidentError(f"incident inconnu : {incident_id}") from None

    def list(self, *, status: IncidentStatus | None = None, open_only: bool = False) -> tuple[Incident, ...]:
        """Incidents dans l'ordre d'ouverture (filtrés)."""
        with self._lock:
            items = list(self._incidents.values())
        return tuple(i for i in items if (status is None or i.status is status) and (not open_only or i.is_open))

    def is_quarantined(self, ref: str | None) -> bool:
        """Vrai si la référence est en quarantaine."""
        if not ref:
            return False
        with self._lock:
            return bool(self._quarantine.get(ref))

    def is_suspended(self, workflow: str | None) -> bool:
        """Vrai si ce workflow (ou toutes les écritures) est suspendu."""
        with self._lock:
            if self._suspended.get(ALL_WRITES):
                return True
            return bool(workflow) and bool(self._suspended.get(workflow or ""))

    @property
    def all_writes_suspended(self) -> bool:
        """Vrai si un incident GLOBAL ouvert suspend toutes les écritures."""
        with self._lock:
            return bool(self._suspended.get(ALL_WRITES))

    def quarantined(self) -> dict[str, tuple[str, ...]]:
        """Références en quarantaine -> incidents qui les tiennent."""
        with self._lock:
            return {k: tuple(sorted(v)) for k, v in self._quarantine.items() if v}

    def suspended(self) -> dict[str, tuple[str, ...]]:
        """Workflows suspendus -> incidents qui les tiennent."""
        with self._lock:
            return {k: tuple(sorted(v)) for k, v in self._suspended.items() if v}

    # -- ouverture ----------------------------------------------------------------
    def open(
        self,
        *,
        cause: str,
        code: IncidentCode | str | None = None,
        kind: str | None = None,
        severity: Severity | str | None = None,
        scope: IncidentScope | str | None = None,
        proposed_action: str | None = None,
        product_key: str | None = None,
        supplier_id: str | None = None,
        workflow: str | None = None,
        target: str | None = None,
        details: Mapping[str, Any] | None = None,
        decision_expected: str | None = None,
        actor: str = "systeme",
        actor_kind: ActorKind | str = ActorKind.SYSTEME,
        simulation: bool = False,
        fictif: bool = False,
        escalation: Escalation | str | None = None,
        contain: bool = True,
    ) -> Incident:
        """Ouvre un incident, applique le confinement, rétrograde si critique, notifie, journalise.

        ``contain=False`` : signalement sans confinement (ex. lignes déjà mises en quarantaine par l'import).
        """
        if not cause or not cause.strip():
            raise IncidentError("cause obligatoire")
        inc_code = IncidentCode(code) if code is not None else None
        if inc_code is not None:
            spec = INCIDENT_CATALOG[inc_code]
        elif kind is not None and severity is not None and scope is not None and proposed_action:
            spec = IncidentSpec(
                title=kind, severity=Severity(severity), scope=IncidentScope(scope), proposed_action=proposed_action
            )
        else:
            raise IncidentError("sans code INC-xx : type, gravité, périmètre et action proposée obligatoires")
        sev = Severity(severity) if severity is not None else spec.severity
        sc = IncidentScope(scope) if scope is not None else spec.scope
        action = proposed_action or spec.proposed_action
        title = spec.title
        the_kind = kind or (inc_code.value if inc_code else "INCIDENT")
        tgt = target or self._target_for(sc, product_key, supplier_id, workflow)
        esc = Escalation(escalation) if escalation is not None else self._default_escalation(sev)
        dedup = f"{inc_code.value if inc_code else the_kind}|{sc.value}|{tgt}|{'sim' if simulation else 'reel'}"
        with self._lock:
            now = self._clock()
            for existing in self._incidents.values():
                if existing.is_open and existing.dedup_key == dedup:
                    self._audit.append(
                        actor=actor,
                        actor_kind=actor_kind,
                        action="incident.duplicate",
                        entity="incident",
                        entity_id=existing.incident_id,
                        dry_run=simulation,
                        payload={"cause": cause, "target": tgt},
                    )
                    return existing
            self._seq += 1
            incident_id = f"INC-{now:%Y%m%d}-{self._seq:05d}"
            containment: list[str] = []
            before = after = None
            if not simulation and contain:
                containment = self._contain(sc, tgt, incident_id)
            incident = Incident(
                incident_id=incident_id,
                code=inc_code,
                kind=the_kind,
                title=title,
                severity=sev,
                scope=sc,
                escalation_level=esc,
                target=tgt,
                product_key=product_key,
                supplier_id=supplier_id,
                workflow=workflow,
                cause=cause.strip(),
                proposed_action=action,
                decision_expected=decision_expected or self._default_decision(sev),
                details=to_jsonable(dict(details or {})),
                opened_at=now,
                opened_by=actor,
                simulation=simulation,
                containment=tuple(containment),
                fictif=fictif,
                dedup_key=dedup,
            )
            self._incidents[incident_id] = incident
        if sev is Severity.CRITIQUE and not simulation and self._on_critical is not None:
            levels = self._on_critical(incident)
            if levels is not None:
                before, after = levels
                if after is not None and before is not None and after < before:
                    containment.append(f"niveau d'autonomie {before} → {after}")
                with self._lock:
                    incident = incident.replace(
                        autonomy_before=before, autonomy_after=after, containment=tuple(containment)
                    )
                    self._incidents[incident_id] = incident
        self._audit.append(
            actor=actor,
            actor_kind=actor_kind,
            action="incident.open",
            entity="incident",
            entity_id=incident_id,
            dry_run=simulation,
            autonomy_level=after,
            payload={
                "code": inc_code.value if inc_code else None,
                "severity": sev.value,
                "scope": sc.value,
                "target": tgt,
                "cause": incident.cause,
                "proposed_action": action,
                "containment": list(incident.containment),
            },
        )
        self._persist(incident)
        self._notify(incident)
        return incident

    @staticmethod
    def _target_for(
        scope: IncidentScope, product_key: str | None, supplier_id: str | None, workflow: str | None
    ) -> str:
        if scope is IncidentScope.GLOBAL:
            return ALL_WRITES
        if scope is IncidentScope.REFERENCE:
            if not product_key:
                raise IncidentError("incident de référence : product_key (ou target) obligatoire")
            return product_key
        if scope is IncidentScope.SOURCE:
            if not supplier_id:
                raise IncidentError("incident de source : supplier_id (ou target) obligatoire")
            return source_target(supplier_id)
        if not workflow:
            raise IncidentError("incident de workflow : workflow (ou target) obligatoire")
        return workflow

    @staticmethod
    def _default_escalation(severity: Severity) -> Escalation | None:
        return {Severity.CRITIQUE: Escalation.E3, Severity.MAJEUR: Escalation.E1}.get(severity)

    @staticmethod
    def _default_decision(severity: Severity) -> str:
        if severity is Severity.CRITIQUE:
            return "Autoriser la reprise après test (propriétaire uniquement)"
        return "aucune"

    def _contain(self, scope: IncidentScope, target: str, incident_id: str) -> builtins.list[str]:
        if scope is IncidentScope.REFERENCE:
            self._quarantine.setdefault(target, set()).add(incident_id)
            return [f"quarantaine de {target}"]
        self._suspended.setdefault(target, set()).add(incident_id)
        if target == ALL_WRITES:
            return ["toutes les écritures suspendues (actions protectrices permises)"]
        return [f"{target} suspendu"]

    def _render(self, incident: Incident) -> Notification:
        prefix = "[SIMULATION] " if incident.simulation else ""
        code = incident.code.value if incident.code else incident.kind
        confinement = " / ".join(incident.containment) if incident.containment else "aucun (simulation ou information)"
        text = "\n".join(
            [
                f"{prefix}[INCIDENT {incident.severity.sop_label}] {code} — {incident.title}",
                f"Détecté le : {_fmt_dt(incident.opened_at)}, par : {incident.opened_by}",
                f"Périmètre : {incident.scope.value} {incident.target}",
                f"Cause probable : {incident.cause}",
                f"Confinement appliqué : {confinement}",
                "Impact client : voir l'incident (jamais dans un canal public)",
                f"Action proposée : {incident.proposed_action}",
                f"Décision attendue de la propriétaire : {incident.decision_expected}",
            ]
        )
        return Notification(
            incident_id=incident.incident_id,
            severity=incident.severity,
            code=incident.code.value if incident.code else None,
            title=incident.title,
            cause=incident.cause,
            proposed_action=incident.proposed_action,
            decision_expected=incident.decision_expected,
            scope=incident.scope,
            target=incident.target,
            simulation=incident.simulation,
            opened_at=incident.opened_at,
            text=text,
        )

    def notification_for(self, incident_id: str) -> Notification:
        """Message SOP §4 d'un incident (pour un renvoi manuel)."""
        return self._render(self.get(incident_id))

    def _notify(self, incident: Incident) -> None:
        receipt = self._notifier.send(self._render(incident))
        self.receipts.append(receipt)
        self._audit.append(
            actor="systeme",
            actor_kind=ActorKind.SYSTEME,
            action="incident.notify",
            entity="incident",
            entity_id=incident.incident_id,
            dry_run=receipt.dry_run or incident.simulation,
            payload={"channel": receipt.channel, "delivered": receipt.delivered, "detail": receipt.detail},
        )

    def _persist(self, incident: Incident) -> None:
        if self._sink is not None:
            self._sink.record(incident)

    # -- transitions ----------------------------------------------------------------
    def _update(self, incident: Incident, action: str, actor: str, actor_kind: ActorKind | str, **payload: Any) -> None:
        with self._lock:
            self._incidents[incident.incident_id] = incident
        self._audit.append(
            actor=actor,
            actor_kind=actor_kind,
            action=action,
            entity="incident",
            entity_id=incident.incident_id,
            dry_run=incident.simulation,
            payload={"status": incident.status.value, **payload},
        )
        self._persist(incident)

    def start(self, incident_id: str, *, actor: str, actor_kind: ActorKind | str = ActorKind.AGENT) -> Incident:
        """OUVERT -> EN_COURS (correction en cours)."""
        incident = self.get(incident_id)
        if incident.status is not IncidentStatus.OUVERT:
            raise IncidentError(f"{incident_id} : statut {incident.status.value}, prise en charge impossible")
        updated = incident.replace(status=IncidentStatus.EN_COURS)
        self._update(updated, "incident.start", actor, actor_kind)
        return updated

    def record_test(
        self,
        incident_id: str,
        *,
        test_ref: str,
        passed: bool,
        actor: str,
        actor_kind: ActorKind | str = ActorKind.AGENT,
    ) -> Incident:
        """Enregistre le résultat du test de correction (rejeu dry-run, recette, cycle complet)."""
        if not test_ref or not test_ref.strip():
            raise IncidentError("référence du test obligatoire")
        incident = self.get(incident_id)
        if not incident.is_open:
            raise IncidentError(f"{incident_id} : incident déjà {incident.status.value}")
        updated = incident.replace(test_ref=test_ref.strip(), test_passed=passed, tested_at=self._clock())
        self._update(updated, "incident.test", actor, actor_kind, test_ref=test_ref, passed=passed)
        return updated

    def resume(self, incident_id: str, *, actor: str, actor_kind: ActorKind | str = ActorKind.AGENT) -> Incident:
        """Reprise : exige un test réussi ; incident critique => propriétaire uniquement."""
        kind = ActorKind(actor_kind)
        incident = self.get(incident_id)
        if not incident.is_open:
            raise IncidentError(f"{incident_id} : incident déjà {incident.status.value}")
        if not incident.test_passed:
            raise IncidentError("reprise refusée : aucun test réussi enregistré (correction → test → reprise)")
        if incident.severity is Severity.CRITIQUE and kind is not ActorKind.PROPRIETAIRE:
            self._audit.append(
                actor=actor,
                actor_kind=kind,
                action="incident.resume_refused",
                entity="incident",
                entity_id=incident_id,
                dry_run=incident.simulation,
                payload={"motif": "incident critique"},
            )
            raise IncidentError("incident critique : reprise autorisée par la propriétaire uniquement")
        lifted: list[str] = []
        with self._lock:
            for registry in (self._quarantine, self._suspended):
                holders = registry.get(incident.target)
                if holders and incident_id in holders:
                    holders.discard(incident_id)
                    if not holders:
                        lifted.append(incident.target)
            now = self._clock()
        updated = incident.replace(
            status=IncidentStatus.RESOLU, resolved_at=now, resolved_by=actor, lifted=tuple(lifted)
        )
        self._update(updated, "incident.resume", actor, kind, lifted=lifted)
        return updated

    def close(self, incident_id: str, *, actor: str, actor_kind: ActorKind | str = ActorKind.AGENT) -> Incident:
        """RESOLU -> CLOS (post-mortem fait pour un S1)."""
        incident = self.get(incident_id)
        if incident.status is not IncidentStatus.RESOLU:
            raise IncidentError(f"{incident_id} : seul un incident résolu peut être clos")
        updated = incident.replace(status=IncidentStatus.CLOS)
        self._update(updated, "incident.close", actor, actor_kind)
        return updated

    def summary(self) -> dict[str, int]:
        """Compteurs par statut et nombre de critiques ouverts (tableau de bord)."""
        items = self.list()
        out: dict[str, int] = {s.value: 0 for s in IncidentStatus}
        for i in items:
            out[i.status.value] += 1
        out["CRITIQUE_OUVERTS"] = sum(1 for i in items if i.is_open and i.severity is Severity.CRITIQUE)
        return out
