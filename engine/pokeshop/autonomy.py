"""Niveaux d'autonomie (BP §13) et porte de gouvernance de toute écriture (agent integrations).

**Niveaux** (BP §13, ``docs/08-agents/MATRICE_AUTONOMIE.md``) :

1. tout en simulation et brouillons ;
2. prix et stock des références approuvées synchronisés dans des seuils ;
3. nouveaux produits conformes publiés et campagnes déclenchées selon règles ;
4. réassorts automatiques avec budgets, allocations et trésorerie contrôlés.

Chaque action d'écriture déclare son niveau requis (:data:`REQUIRED_LEVEL`). Monter d'un niveau
est réservé à la propriétaire (jeton vérifié par empreinte, un niveau à la fois, après recette) ;
agents et système ne peuvent que descendre. Un incident critique rétablit le niveau précédent ;
le stop-loss global ramène au niveau 1. Le niveau est stocké (mémoire, fichier JSON en ajout
seul, ou table ``pokeshop.autonomy_levels``).

**Porte de gouvernance** (:class:`GovernanceGate`) — règle des trois verrous
(``BRIEF_COMMUN.md`` §2 : niveau + mandat + aucun stop-loss). Toute écriture réelle
(publication, prix, stock, campagne, proposition d'achat, paiement) passe par :

1. le niveau d'autonomie (:class:`AutonomyController`) ;
2. :meth:`pokeshop.stoploss.StopLossEngine.evaluate` sur la dernière photo d'activité ; état
   indisponible ou périmé => refus (sécurité par défaut) ; gel global => refus, incident
   critique INC-09 et retour au niveau 1 ;
3. le mandat signé ; pour une action qui dépense, :func:`pokeshop.mandate.check` doit rendre
   ``APPROVED_WITHIN_MANDATE`` (``NEEDS_HUMAN_APPROVAL`` => en attente, rien n'est exécuté).

Les actions **protectrices** (geler, dépublier, couper une campagne) restent permises pendant
un gel ou une suspension : elles réduisent le risque. Le dry-run est toujours permis (il
n'écrit rien à l'extérieur). Ce module réutilise les fonctions de la gouvernance, il ne les
réimplémente pas.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from .audit import ActorKind, AuditLog, ConnectionFactory, _PgRunner
from .errors import PokeshopError
from .incidents import Incident, IncidentCode, IncidentManager, IncidentScope, Severity
from .mandate import (
    Mandate,
    MandateDecision,
    MandateOutcome,
    SpendLedger,
    SpendReason,
    SpendRequest,
    TreasurySnapshot,
    check,
)
from .models import FrozenModel
from .stoploss import (
    OWNER_TOKEN_SHA256_ENV_VAR,
    StopLossEngine,
    StopLossError,
    StopLossState,
    StopLossStatus,
    Trigger,
    hash_owner_token,
)

__all__ = [
    "AutonomyError",
    "AutonomyRefusedError",
    "AutonomyLevel",
    "LEVEL_LABELS_FR",
    "WriteAction",
    "REQUIRED_LEVEL",
    "ACTION_LABELS_FR",
    "PROTECTIVE_ACTIONS",
    "SPEND_ACTIONS",
    "PRODUCT_SALE_ACTIONS",
    "PURCHASE_ACTIONS",
    "ChangeRole",
    "AutonomyState",
    "AutonomyStore",
    "InMemoryAutonomyStore",
    "JsonFileAutonomyStore",
    "PostgresAutonomyStore",
    "AutonomyCheck",
    "AutonomyController",
    "GateReason",
    "GATE_REASON_LABELS_FR",
    "GateDecision",
    "GovernanceGate",
    "verify_owner_token",
]


class AutonomyError(PokeshopError, ValueError):
    """Changement de niveau invalide."""


class AutonomyRefusedError(AutonomyError):
    """Changement refusé : seule la propriétaire (jeton valide) peut relever le niveau."""


class AutonomyLevel(IntEnum):
    """Niveaux BP §13."""

    SIMULATION = 1
    SYNC_APPROVED = 2
    PUBLISH_AND_CAMPAIGNS = 3
    AUTO_REORDER = 4


LEVEL_LABELS_FR: dict[AutonomyLevel, str] = {
    AutonomyLevel.SIMULATION: "Niveau 1 : tout en simulation et brouillons",
    AutonomyLevel.SYNC_APPROVED: "Niveau 2 : prix et stock des références approuvées synchronisés dans des seuils",
    AutonomyLevel.PUBLISH_AND_CAMPAIGNS: "Niveau 3 : nouveaux produits conformes publiés, campagnes selon règles",
    AutonomyLevel.AUTO_REORDER: "Niveau 4 : réassorts automatiques avec budgets, allocations et trésorerie contrôlés",
}


class WriteAction(str, Enum):
    """Actions d'écriture ; chacune déclare son niveau requis dans :data:`REQUIRED_LEVEL`."""

    FREEZE = "FREEZE"
    UNPUBLISH_PRODUCT = "UNPUBLISH_PRODUCT"
    CUT_CAMPAIGN = "CUT_CAMPAIGN"
    PROPOSE_PURCHASE = "PROPOSE_PURCHASE"
    SPEND_WITHIN_MANDATE = "SPEND_WITHIN_MANDATE"
    SAVE_DRAFT_PRODUCT = "SAVE_DRAFT_PRODUCT"
    SYNC_PRICE = "SYNC_PRICE"
    SYNC_STOCK = "SYNC_STOCK"
    UPDATE_APPROVED_PRODUCT = "UPDATE_APPROVED_PRODUCT"
    PUBLISH_NEW_PRODUCT = "PUBLISH_NEW_PRODUCT"
    APPLY_PROMOTION = "APPLY_PROMOTION"
    LAUNCH_CAMPAIGN = "LAUNCH_CAMPAIGN"
    AUTO_REORDER = "AUTO_REORDER"


REQUIRED_LEVEL: dict[WriteAction, AutonomyLevel] = {
    WriteAction.FREEZE: AutonomyLevel.SIMULATION,
    WriteAction.UNPUBLISH_PRODUCT: AutonomyLevel.SIMULATION,
    WriteAction.CUT_CAMPAIGN: AutonomyLevel.SIMULATION,
    WriteAction.PROPOSE_PURCHASE: AutonomyLevel.SIMULATION,
    WriteAction.SPEND_WITHIN_MANDATE: AutonomyLevel.SIMULATION,
    WriteAction.SAVE_DRAFT_PRODUCT: AutonomyLevel.SYNC_APPROVED,
    WriteAction.SYNC_PRICE: AutonomyLevel.SYNC_APPROVED,
    WriteAction.SYNC_STOCK: AutonomyLevel.SYNC_APPROVED,
    WriteAction.UPDATE_APPROVED_PRODUCT: AutonomyLevel.SYNC_APPROVED,
    WriteAction.PUBLISH_NEW_PRODUCT: AutonomyLevel.PUBLISH_AND_CAMPAIGNS,
    WriteAction.APPLY_PROMOTION: AutonomyLevel.PUBLISH_AND_CAMPAIGNS,
    WriteAction.LAUNCH_CAMPAIGN: AutonomyLevel.PUBLISH_AND_CAMPAIGNS,
    WriteAction.AUTO_REORDER: AutonomyLevel.AUTO_REORDER,
}
"""Niveau minimal par action (matrice d'autonomie §2). Les dépenses ont en plus le niveau de catégorie du mandat."""

ACTION_LABELS_FR: dict[WriteAction, str] = {
    WriteAction.FREEZE: "Gel conservatoire (protecteur)",
    WriteAction.UNPUBLISH_PRODUCT: "Dépublier une fiche (repasser en brouillon, protecteur)",
    WriteAction.CUT_CAMPAIGN: "Couper une campagne (protecteur)",
    WriteAction.PROPOSE_PURCHASE: "Proposer un panier fournisseur à valider (aucune dépense)",
    WriteAction.SPEND_WITHIN_MANDATE: "Dépense dans le mandat (niveau de catégorie du mandat)",
    WriteAction.SAVE_DRAFT_PRODUCT: "Créer ou mettre à jour une fiche en brouillon sur la boutique",
    WriteAction.SYNC_PRICE: "Synchroniser le prix d'une référence approuvée",
    WriteAction.SYNC_STOCK: "Synchroniser le stock local d'une référence approuvée",
    WriteAction.UPDATE_APPROVED_PRODUCT: "Mettre à jour une fiche approuvée",
    WriteAction.PUBLISH_NEW_PRODUCT: "Publier une nouvelle référence conforme (règle de catégorie validée)",
    WriteAction.APPLY_PROMOTION: "Appliquer une promotion calculée par le moteur",
    WriteAction.LAUNCH_CAMPAIGN: "Lancer une campagne du plan validé",
    WriteAction.AUTO_REORDER: "Réassort automatique dans l'enveloppe",
}

PROTECTIVE_ACTIONS: frozenset[WriteAction] = frozenset(
    {WriteAction.FREEZE, WriteAction.UNPUBLISH_PRODUCT, WriteAction.CUT_CAMPAIGN}
)
"""Réduisent le risque : permises pendant un gel, une quarantaine ou une suspension."""
SPEND_ACTIONS: frozenset[WriteAction] = frozenset(
    {WriteAction.SPEND_WITHIN_MANDATE, WriteAction.LAUNCH_CAMPAIGN, WriteAction.AUTO_REORDER}
)
"""Engagent de l'argent : ``mandate.check`` obligatoire (demande de dépense exigée)."""
PRODUCT_SALE_ACTIONS: frozenset[WriteAction] = frozenset(
    {
        WriteAction.PUBLISH_NEW_PRODUCT,
        WriteAction.UPDATE_APPROVED_PRODUCT,
        WriteAction.APPLY_PROMOTION,
        WriteAction.LAUNCH_CAMPAIGN,
    }
)
"""Rendent une référence vendable ou la promeuvent : interdites si le stop-loss produit la bloque."""
PURCHASE_ACTIONS: frozenset[WriteAction] = frozenset({WriteAction.PROPOSE_PURCHASE, WriteAction.AUTO_REORDER})
"""Achats de stock : interdits si extension, produit ou trésorerie gelés."""

ChangeRole = Literal["PROPRIETAIRE", "AGENT", "SYSTEME"]


def verify_owner_token(token: str | None, expected_sha256: str | None) -> bool:
    """Vrai si le jeton correspond à l'empreinte de la propriétaire (comparaison en temps constant)."""
    if not token or not expected_sha256:
        return False
    try:
        candidate = hash_owner_token(token)
    except StopLossError:
        return False
    return hmac.compare_digest(candidate, expected_sha256.strip().lower())


# ---------------------------------------------------------------------- stockage


class AutonomyState(FrozenModel):
    """Niveau en vigueur et origine du dernier changement (une ligne de ``autonomy_levels``)."""

    scope: str = "global"
    level: int = Field(ge=1, le=4)
    previous_level: int | None = Field(default=None, ge=1, le=4)
    changed_by: str = Field(min_length=1)
    changed_by_role: ChangeRole
    reason: str = Field(min_length=1)
    at: datetime


@runtime_checkable
class AutonomyStore(Protocol):
    """Historique append-only des niveaux d'autonomie."""

    def current(self, scope: str = "global") -> AutonomyState | None:
        """Dernier état du périmètre (None si jamais fixé)."""
        ...

    def append(self, state: AutonomyState) -> AutonomyState:
        """Ajoute un changement de niveau."""
        ...

    def history(self, scope: str = "global") -> tuple[AutonomyState, ...]:
        """Tous les changements, du plus ancien au plus récent."""
        ...


class InMemoryAutonomyStore:
    """Historique en mémoire (tests, simulation)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: list[AutonomyState] = []

    def current(self, scope: str = "global") -> AutonomyState | None:
        """Dernier état."""
        with self._lock:
            for row in reversed(self._rows):
                if row.scope == scope:
                    return row
        return None

    def append(self, state: AutonomyState) -> AutonomyState:
        """Ajout seul."""
        with self._lock:
            self._rows.append(state)
        return state

    def history(self, scope: str = "global") -> tuple[AutonomyState, ...]:
        """Historique du périmètre."""
        with self._lock:
            return tuple(r for r in self._rows if r.scope == scope)


class JsonFileAutonomyStore:
    """Historique dans un fichier JSON Lines en **ajout seul** (niveau persistant sans base)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> list[AutonomyState]:
        if not self.path.exists():
            return []
        rows = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(AutonomyState.model_validate(json.loads(line)))
            except (ValueError, TypeError) as exc:
                raise AutonomyError(f"{self.path} ligne {n} illisible : {exc}") from exc
        return rows

    def current(self, scope: str = "global") -> AutonomyState | None:
        """Dernier état lu sur disque."""
        with self._lock:
            for row in reversed(self._read()):
                if row.scope == scope:
                    return row
        return None

    def append(self, state: AutonomyState) -> AutonomyState:
        """Ajoute une ligne (fichier ouvert en mode ajout)."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(state.model_dump_json() + "\n")
        return state

    def history(self, scope: str = "global") -> tuple[AutonomyState, ...]:
        """Historique du périmètre."""
        with self._lock:
            return tuple(r for r in self._read() if r.scope == scope)


class PostgresAutonomyStore:
    """Table ``pokeshop.autonomy_levels`` : la base refuse qu'un agent ou le système relève le niveau."""

    INSERT_SQL = (
        "INSERT INTO pokeshop.autonomy_levels (scope, level, changed_by, changed_by_role, reason) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING previous_level, at"
    )
    SELECT_SQL = (
        "SELECT scope, level, previous_level, changed_by, changed_by_role, reason, at "
        "FROM pokeshop.autonomy_levels WHERE scope = %s ORDER BY change_id"
    )

    def __init__(self, connect: ConnectionFactory) -> None:
        self._db = _PgRunner(connect)

    @staticmethod
    def _state(row: Sequence[Any]) -> AutonomyState:
        return AutonomyState(
            scope=row[0],
            level=int(row[1]),
            previous_level=None if row[2] is None else int(row[2]),
            changed_by=row[3],
            changed_by_role=row[4],
            reason=row[5],
            at=row[6],
        )

    def history(self, scope: str = "global") -> tuple[AutonomyState, ...]:
        """Historique (ordre des changements)."""
        rows = self._db.run(self.SELECT_SQL, (scope,), "all") or []
        return tuple(self._state(r) for r in rows)

    def current(self, scope: str = "global") -> AutonomyState | None:
        """Dernier état."""
        rows = self.history(scope)
        return rows[-1] if rows else None

    def append(self, state: AutonomyState) -> AutonomyState:
        """INSERT ; le trigger fixe ``previous_level`` et la contrainte refuse une hausse non propriétaire."""
        row = self._db.run(
            self.INSERT_SQL, (state.scope, state.level, state.changed_by, state.changed_by_role, state.reason), "one"
        )
        return state.replace(previous_level=None if row[0] is None else int(row[0]), at=row[1])


# --------------------------------------------------------------------- contrôleur


class AutonomyCheck(FrozenModel):
    """Résultat du contrôle de niveau pour une action."""

    action: WriteAction
    allowed: bool
    required_level: int
    current_level: int
    dry_run: bool
    reason: str


class AutonomyController:
    """Niveau d'autonomie courant, changements journalisés, rétrogradation sur incident critique."""

    def __init__(
        self,
        store: AutonomyStore | None = None,
        *,
        audit: AuditLog,
        owner_token_sha256: str | None = None,
        default_level: int = 1,
        scope: str = "global",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(default_level, bool) or not 1 <= default_level <= 4:
            raise AutonomyError("niveau par défaut hors 1..4")
        self._store: AutonomyStore = store or InMemoryAutonomyStore()
        self._audit = audit
        expected = owner_token_sha256 if owner_token_sha256 is not None else os.environ.get(OWNER_TOKEN_SHA256_ENV_VAR)
        self._owner_hash = expected.strip().lower() if expected else None
        self._default = default_level
        self.scope = scope
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    # -- lecture ------------------------------------------------------------------
    @property
    def state(self) -> AutonomyState:
        """État en vigueur (niveau par défaut s'il n'a jamais été fixé)."""
        current = self._store.current(self.scope)
        if current is not None:
            return current
        return AutonomyState(
            scope=self.scope,
            level=self._default,
            changed_by="configuration",
            changed_by_role="SYSTEME",
            reason="niveau initial (POKESHOP_AUTONOMY_LEVEL)",
            at=self._clock(),
        )

    @property
    def level(self) -> AutonomyLevel:
        """Niveau en vigueur."""
        return AutonomyLevel(self.state.level)

    def history(self) -> tuple[AutonomyState, ...]:
        """Changements de niveau (ajout seul)."""
        return self._store.history(self.scope)

    @staticmethod
    def required_level(action: WriteAction) -> AutonomyLevel:
        """Niveau requis par une action."""
        return REQUIRED_LEVEL[WriteAction(action)]

    def check(self, action: WriteAction, *, dry_run: bool, level: int | None = None) -> AutonomyCheck:
        """Contrôle de niveau seul (la porte de gouvernance ajoute stop-loss et mandat)."""
        act = WriteAction(action)
        required = REQUIRED_LEVEL[act]
        current = int(level if level is not None else self.level)
        if dry_run:
            return AutonomyCheck(
                action=act,
                allowed=True,
                required_level=required,
                current_level=current,
                dry_run=True,
                reason="simulation : aucune écriture externe",
            )
        allowed = current >= required
        reason = "niveau suffisant" if allowed else f"niveau {current} < niveau {int(required)} requis"
        return AutonomyCheck(
            action=act, allowed=allowed, required_level=required, current_level=current, dry_run=False, reason=reason
        )

    # -- changements ----------------------------------------------------------------
    def _write(self, level: int, *, actor: str, role: ChangeRole, reason: str) -> AutonomyState:
        if not reason or not reason.strip():
            raise AutonomyError("motif obligatoire")
        if not actor or not actor.strip():
            raise AutonomyError("auteur obligatoire")
        before = self.level
        state = AutonomyState(
            scope=self.scope,
            level=level,
            previous_level=int(before),
            changed_by=actor,
            changed_by_role=role,
            reason=reason.strip(),
            at=self._clock(),
        )
        stored = self._store.append(state)
        kind = {"PROPRIETAIRE": ActorKind.PROPRIETAIRE, "AGENT": ActorKind.AGENT, "SYSTEME": ActorKind.SYSTEME}[role]
        self._audit.append(
            actor=actor,
            actor_kind=kind,
            action="autonomy.change",
            entity="autonomy",
            entity_id=self.scope,
            dry_run=False,
            autonomy_level=level,
            payload={"from": int(before), "to": level, "role": role, "reason": reason.strip()},
        )
        return stored

    def lower(self, to_level: int, *, actor: str, role: ChangeRole = "AGENT", reason: str) -> AutonomyState:
        """Abaisse (ou confirme) le niveau ; toujours permis (gel conservatoire, BP §13)."""
        if isinstance(to_level, bool) or not 1 <= int(to_level) <= 4:
            raise AutonomyError("niveau hors 1..4")
        with self._lock:
            if int(to_level) > self.level:
                raise AutonomyRefusedError("relever le niveau est réservé à la propriétaire (raise_level)")
            return self._write(int(to_level), actor=actor, role=role, reason=reason)

    def demote(self, *, actor: str = "systeme", reason: str) -> AutonomyState:
        """Retour au niveau précédent (niveau − 1, minimum 1) : effet d'un incident critique."""
        with self._lock:
            return self._write(max(1, int(self.level) - 1), actor=actor, role="SYSTEME", reason=reason)

    def force_level_one(self, *, reason: str, actor: str = "stop-loss") -> AutonomyState | None:
        """Niveau 1 (gel global) ; sans écriture si déjà au niveau 1."""
        with self._lock:
            if self.level == AutonomyLevel.SIMULATION:
                return None
            return self._write(1, actor=actor, role="SYSTEME", reason=reason)

    def raise_level(
        self, to_level: int, *, owner_token: str, reason: str, actor: str = "propriétaire"
    ) -> AutonomyState:
        """Relève le niveau d'**un** cran (après recette) : jeton de la propriétaire exigé, refus journalisé."""
        if isinstance(to_level, bool) or not 1 <= int(to_level) <= 4:
            raise AutonomyError("niveau hors 1..4")
        with self._lock:
            current = int(self.level)
            if not verify_owner_token(owner_token, self._owner_hash):
                why = "aucune empreinte de jeton configurée" if self._owner_hash is None else "jeton invalide"
                self._audit.append(
                    actor=actor,
                    actor_kind=ActorKind.AGENT,
                    action="autonomy.raise_refused",
                    entity="autonomy",
                    entity_id=self.scope,
                    dry_run=False,
                    autonomy_level=current,
                    payload={"requested": int(to_level), "why": why, "reason": reason},
                )
                raise AutonomyRefusedError(f"hausse de niveau refusée : {why}")
            if int(to_level) <= current:
                raise AutonomyError("utiliser lower() pour abaisser ou confirmer le niveau")
            if int(to_level) != current + 1:
                raise AutonomyError("un niveau à la fois (BP §13 : chaque niveau est activé après recette)")
            return self._write(int(to_level), actor=actor, role="PROPRIETAIRE", reason=reason)

    def on_critical_incident(self, incident: Incident) -> tuple[int, int]:
        """Rappel pour :class:`IncidentManager` : un incident critique rétablit le niveau précédent."""
        before = int(self.level)
        after = int(self.demote(reason=f"incident critique {incident.incident_id} : {incident.title}").level)
        return before, after


# ------------------------------------------------------------------ porte de gouvernance


class GateReason(str, Enum):
    """Motifs stables de la porte de gouvernance."""

    DRY_RUN = "DRY_RUN"
    REAL_WRITES_DISABLED = "REAL_WRITES_DISABLED"
    AUTONOMY_LEVEL_TOO_LOW = "AUTONOMY_LEVEL_TOO_LOW"
    STOPLOSS_UNAVAILABLE = "STOPLOSS_UNAVAILABLE"
    STOPLOSS_GLOBAL_FREEZE = "STOPLOSS_GLOBAL_FREEZE"
    STOPLOSS_PRODUCT = "STOPLOSS_PRODUCT"
    STOPLOSS_EXTENSION = "STOPLOSS_EXTENSION"
    STOPLOSS_ADS = "STOPLOSS_ADS"
    STOPLOSS_CASH = "STOPLOSS_CASH"
    MANDATE_UNAVAILABLE = "MANDATE_UNAVAILABLE"
    MANDATE_INACTIVE = "MANDATE_INACTIVE"
    MANDATE_REJECTED = "MANDATE_REJECTED"
    MANDATE_NEEDS_HUMAN_APPROVAL = "MANDATE_NEEDS_HUMAN_APPROVAL"
    SPEND_REQUEST_MISSING = "SPEND_REQUEST_MISSING"
    PRODUCT_QUARANTINED = "PRODUCT_QUARANTINED"
    WORKFLOW_SUSPENDED = "WORKFLOW_SUSPENDED"
    ALL_WRITES_SUSPENDED = "ALL_WRITES_SUSPENDED"


GATE_REASON_LABELS_FR: dict[GateReason, str] = {
    GateReason.DRY_RUN: "Simulation : rien n'est écrit à l'extérieur.",
    GateReason.REAL_WRITES_DISABLED: "Écritures réelles désactivées par la configuration (POKESHOP_DRY_RUN=true).",
    GateReason.AUTONOMY_LEVEL_TOO_LOW: "Niveau d'autonomie insuffisant pour cette action (BP §13).",
    GateReason.STOPLOSS_UNAVAILABLE: "État du stop-loss indisponible ou périmé : écriture refusée par sécurité.",
    GateReason.STOPLOSS_GLOBAL_FREEZE: "Stop-loss global : tout est gelé jusqu'au réarmement par la propriétaire.",
    GateReason.STOPLOSS_PRODUCT: "Référence bloquée par le stop-loss produit (vente et promotion).",
    GateReason.STOPLOSS_EXTENSION: "Extension gelée par le stop-loss : aucun réassort.",
    GateReason.STOPLOSS_ADS: "Campagne coupée par le stop-loss publicité.",
    GateReason.STOPLOSS_CASH: "Stop-loss trésorerie : plus d'achat ni de publicité.",
    GateReason.MANDATE_UNAVAILABLE: "Mandat illisible ou absent : aucune écriture réelle.",
    GateReason.MANDATE_INACTIVE: "Mandat non signé, incomplet, modifié, révoqué ou hors période.",
    GateReason.MANDATE_REJECTED: "Dépense refusée par le mandat.",
    GateReason.MANDATE_NEEDS_HUMAN_APPROVAL: "Dépense au-delà du mandat : validation de la propriétaire requise.",
    GateReason.SPEND_REQUEST_MISSING: "Action qui dépense sans demande de dépense ni photo de trésorerie.",
    GateReason.PRODUCT_QUARANTINED: "Référence en quarantaine (incident ouvert).",
    GateReason.WORKFLOW_SUSPENDED: "Workflow suspendu par un incident ouvert.",
    GateReason.ALL_WRITES_SUSPENDED: "Toutes les écritures suspendues par un incident global ouvert.",
}


class GateDecision(FrozenModel):
    """Décision de la porte : autorisé ou non, motifs, état du stop-loss et décision du mandat."""

    action: WriteAction
    allowed: bool
    dry_run: bool
    required_level: int
    current_level: int
    reasons: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    pending_human_approval: bool = False
    stoploss: StopLossStatus | None = None
    mandate_decision: MandateDecision | None = None
    incident_id: str | None = None
    decided_at: datetime

    def has(self, reason: GateReason | str) -> bool:
        """Vrai si le motif est présent."""
        code = reason.value if isinstance(reason, GateReason) else reason
        return code in self.reasons


StateProvider = Callable[[], StopLossState | None]
MandateProvider = Callable[[], Mandate | None]


class GovernanceGate:
    """Porte unique de toute écriture réelle : autonomie + stop-loss + mandat (+ incidents ouverts)."""

    def __init__(
        self,
        autonomy: AutonomyController,
        *,
        audit: AuditLog,
        stoploss_engine: StopLossEngine | None,
        state_provider: StateProvider,
        mandate_provider: MandateProvider,
        spend_ledger: SpendLedger | None = None,
        incidents: IncidentManager | None = None,
        real_writes_enabled: bool = False,
        clock: Callable[[], datetime] | None = None,
        status_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        self.autonomy = autonomy
        self._audit = audit
        self._engine = stoploss_engine
        self._state_provider = state_provider
        self._mandate_provider = mandate_provider
        self._ledger = spend_ledger if spend_ledger is not None else SpendLedger()
        self._incidents = incidents
        self.real_writes_enabled = real_writes_enabled
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ttl = status_ttl
        self._lock = threading.RLock()
        self._cache: tuple[int, datetime, datetime, StopLossStatus, tuple[Trigger, ...]] | None = None
        self.last_stoploss_error: str | None = None

    @property
    def spend_ledger(self) -> SpendLedger:
        """Registre des dépenses utilisé pour ``mandate.check``."""
        return self._ledger

    def invalidate(self) -> None:
        """Oublie l'évaluation en cache (nouvelle photo, réarmement)."""
        with self._lock:
            self._cache = None

    def stoploss_status(self, now: datetime | None = None) -> tuple[StopLossStatus | None, tuple[Trigger, ...]]:
        """Évalue (ou relit en cache) le stop-loss ; None si l'état est absent, périmé ou invalide."""
        at = now or self._clock()
        with self._lock:
            state = self._state_provider()
            if self._engine is None or state is None:
                self.last_stoploss_error = (
                    "moteur de stop-loss non configuré" if self._engine is None else "aucune photo d'activité"
                )
                return None, ()
            key = id(state)
            if self._cache is not None:
                c_key, c_as_of, c_at, c_status, c_triggers = self._cache
                if c_key == key and c_as_of == state.as_of and at - c_at < self._ttl:
                    return c_status, c_triggers
            try:
                triggers = tuple(self._engine.evaluate(state, at))
            except StopLossError as exc:
                self.last_stoploss_error = str(exc)
                self._cache = None
                return None, ()
            status = self._engine.status(triggers, as_of=at, autonomy_level=int(self.autonomy.level))
            self.last_stoploss_error = None
            self._cache = (key, state.as_of, at, status, triggers)
            return status, triggers

    def _global_freeze(self, triggers: Sequence[Trigger], actor: str) -> str | None:
        self.autonomy.force_level_one(reason="stop-loss global : retour au niveau d'autonomie 1")
        if self._incidents is None:
            return None
        fallback = self._engine.latch.detail if self._engine is not None and self._engine.latch.detail else None
        default = fallback or "gel global verrouillé"
        reason = next((t.reason for t in triggers if t.action.value == "FREEZE_ALL"), default)
        incident = self._incidents.open(
            code=IncidentCode.INC_09,
            severity=Severity.CRITIQUE,
            scope=IncidentScope.GLOBAL,
            cause=f"Stop-loss global : {reason}",
            proposed_action="Tout est gelé et l'autonomie est au niveau 1. Examiner la valeur nette ; seul le jeton "
            "de la propriétaire réarme (POST /stoploss/rearm).",
            decision_expected="Réarmer ou non le stop-loss global (propriétaire uniquement)",
            actor=actor,
        )
        return incident.incident_id

    def enforce(
        self, *, actor: str = "systeme", now: datetime | None = None
    ) -> tuple[StopLossStatus | None, str | None]:
        """Applique sans attendre les effets d'un gel global (niveau 1, incident INC-09) ; renvoie (état, incident).

        Le verrou du moteur suffit (gel manuel sans photo d'activité compris).
        """
        status, triggers = self.stoploss_status(now)
        frozen = (status is not None and status.global_frozen) or (self._engine is not None and self._engine.frozen)
        if not frozen:
            return status, None
        return status, self._global_freeze(triggers, actor)

    def authorize(
        self,
        action: WriteAction | str,
        *,
        dry_run: bool = True,
        actor: str = "systeme",
        product_key: str | None = None,
        extension: str | None = None,
        campaign_id: str | None = None,
        workflow: str | None = None,
        spend_request: SpendRequest | None = None,
        treasury: TreasurySnapshot | None = None,
    ) -> GateDecision:
        """Décide si l'action peut être **réellement** exécutée ; journalise la décision."""
        act = WriteAction(action)
        now = self._clock()
        required = int(REQUIRED_LEVEL[act])
        level = int(self.autonomy.level)
        if dry_run:
            decision = GateDecision(
                action=act,
                allowed=True,
                dry_run=True,
                required_level=required,
                current_level=level,
                reasons=(GateReason.DRY_RUN.value,),
                messages=(GATE_REASON_LABELS_FR[GateReason.DRY_RUN],),
                decided_at=now,
            )
            self._log(decision, actor, product_key, workflow)
            return decision
        reasons: list[GateReason] = []
        extra: list[str] = []
        protective = act in PROTECTIVE_ACTIONS
        if not self.real_writes_enabled:
            reasons.append(GateReason.REAL_WRITES_DISABLED)
        status, triggers = self.stoploss_status(now)
        incident_id: str | None = None
        effective = level
        if status is None:
            if not protective:
                reasons.append(GateReason.STOPLOSS_UNAVAILABLE)
                if self.last_stoploss_error:
                    extra.append(f"Stop-loss : {self.last_stoploss_error}.")
        else:
            effective = min(level, status.autonomy_level)
            if status.global_frozen:
                incident_id = self._global_freeze(triggers, actor)
                effective = 1
                if not protective:
                    reasons.append(GateReason.STOPLOSS_GLOBAL_FREEZE)
            if not protective:
                if act in PRODUCT_SALE_ACTIONS and product_key and product_key in status.blocked_products:
                    reasons.append(GateReason.STOPLOSS_PRODUCT)
                if act in PURCHASE_ACTIONS or (
                    act in SPEND_ACTIONS
                    and spend_request is not None
                    and spend_request.category.value in ("STOCK", "ACCESSORIES")
                ):
                    if status.purchases_and_ads_frozen:
                        reasons.append(GateReason.STOPLOSS_CASH)
                    if extension and extension in status.no_reorder_extensions:
                        reasons.append(GateReason.STOPLOSS_EXTENSION)
                    if (
                        product_key
                        and product_key in status.blocked_products
                        and GateReason.STOPLOSS_PRODUCT not in reasons
                    ):
                        reasons.append(GateReason.STOPLOSS_PRODUCT)
                if act is WriteAction.LAUNCH_CAMPAIGN:
                    if status.purchases_and_ads_frozen and GateReason.STOPLOSS_CASH not in reasons:
                        reasons.append(GateReason.STOPLOSS_CASH)
                    if status.ads_globally_cut or (campaign_id and campaign_id in status.cut_campaigns):
                        reasons.append(GateReason.STOPLOSS_ADS)
        if not protective and effective < required:
            reasons.append(GateReason.AUTONOMY_LEVEL_TOO_LOW)
            extra.append(f"Niveau {effective} < niveau {required} requis ({ACTION_LABELS_FR[act]}).")
        if self._incidents is not None and not protective:
            if self._incidents.all_writes_suspended:
                reasons.append(GateReason.ALL_WRITES_SUSPENDED)
            elif workflow and self._incidents.is_suspended(workflow):
                reasons.append(GateReason.WORKFLOW_SUSPENDED)
            if product_key and self._incidents.is_quarantined(product_key):
                reasons.append(GateReason.PRODUCT_QUARANTINED)
        mandate_decision: MandateDecision | None = None
        pending = False
        if not protective:
            mandate = self._mandate_provider()
            if mandate is None:
                reasons.append(GateReason.MANDATE_UNAVAILABLE)
            else:
                inactive = mandate.inactive_reasons(now)
                if inactive:
                    reasons.append(GateReason.MANDATE_INACTIVE)
                    extra.append("Mandat inactif : " + ", ".join(r.value for r in inactive) + ".")
                if act in SPEND_ACTIONS:
                    if spend_request is None or treasury is None:
                        reasons.append(GateReason.SPEND_REQUEST_MISSING)
                    elif status is not None:
                        mandate_decision = check(spend_request, mandate, self._ledger, status, treasury, now=now)
                        if mandate_decision.outcome is MandateOutcome.REJECTED:
                            reasons.append(GateReason.MANDATE_REJECTED)
                        elif mandate_decision.outcome is MandateOutcome.NEEDS_HUMAN_APPROVAL:
                            reasons.append(GateReason.MANDATE_NEEDS_HUMAN_APPROVAL)
                            pending = True
                        extra.extend(mandate_decision.labels_fr)
        unique = list(dict.fromkeys(reasons))
        decision = GateDecision(
            action=act,
            allowed=not unique,
            dry_run=False,
            required_level=required,
            current_level=effective,
            reasons=tuple(r.value for r in unique),
            messages=tuple([GATE_REASON_LABELS_FR[r] for r in unique] + extra),
            pending_human_approval=pending and len(unique) == 1,
            stoploss=status,
            mandate_decision=mandate_decision,
            incident_id=incident_id,
            decided_at=now,
        )
        if (
            mandate_decision is not None
            and spend_request is not None
            and not mandate_decision.replayed
            and not mandate_decision.has(SpendReason.IDEMPOTENCY_CONFLICT)  # la clé appartient à une autre demande
        ):
            approved = mandate_decision.outcome is MandateOutcome.APPROVED_WITHIN_MANDATE
            # Registre du mandat : une dépense approuvée n'y entre que si la porte l'autorise (sinon elle
            # consommerait une enveloppe sans être payée) ; attente humaine et refus y sont toujours tracés.
            if decision.allowed or not approved:
                self._ledger.record(spend_request, mandate_decision, actor=actor)
        self._log(decision, actor, product_key, workflow)
        return decision

    def _log(self, decision: GateDecision, actor: str, product_key: str | None, workflow: str | None) -> None:
        self._audit.append(
            actor=actor,
            actor_kind=ActorKind.AGENT if actor.startswith("agent") else ActorKind.SYSTEME,
            action="gate.allow" if decision.allowed else "gate.refuse",
            entity="write_action",
            entity_id=decision.action.value,
            dry_run=decision.dry_run,
            autonomy_level=decision.current_level,
            payload={
                "product_key": product_key,
                "workflow": workflow,
                "reasons": list(decision.reasons),
                "required_level": decision.required_level,
                "incident_id": decision.incident_id,
                "mandate_outcome": decision.mandate_decision.outcome.value if decision.mandate_decision else None,
            },
        )
