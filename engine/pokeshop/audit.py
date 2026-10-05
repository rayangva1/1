"""Journal d'audit append-only et registre d'idempotence (agent integrations, SPEC §2.9, BP §6).

Deux garanties du BP §6 « Fiabilité » : *journal de chaque changement* et *clés
d'idempotence / reprise sans double écriture*.

* :class:`InMemoryAuditLog` — journal chaîné par sha256 (``prev_hash`` -> ``row_hash``),
  thread-safe, sans méthode de modification ni de suppression. :meth:`verify` recalcule la
  chaîne. Les charges utiles sont copiées en JSON canonique à l'écriture : l'appelant ne peut
  plus les modifier ensuite.
* :class:`PostgresAuditLog` — même interface sur ``pokeshop.audit_log`` (migrations
  ``db/migrations/001`` et ``002`` : chaîne, horodatage et séquence imposés par la base,
  UPDATE/DELETE/TRUNCATE refusés). SQL **paramétré** uniquement, aucun ORM.
* :class:`InMemoryIdempotencyStore` / :class:`PostgresIdempotencyStore` — réservation
  ``(scope, clé, sha256 de la requête)`` : ``NEW`` (exécuter), ``DUPLICATE_*`` (ne pas
  réécrire, rejouer la réponse), ``CONFLICT`` (même clé, autre requête : refus). La base
  utilise ``pokeshop.claim_idempotency_key``.

* :class:`StateJournal` — journaux d'état **en ajout seul**, chaînés sha256, des composants de
  sécurité (verrou et journal du stop-loss, dernière photo valide, registre du mandat, étoile
  polaire, incidents et confinements, historique des prix) : fichier JSON Lines
  (:class:`JsonlStateJournal`, ``POKESHOP_STATE_DIR``) ou table ``pokeshop.engine_state_journal``
  (:class:`PostgresStateJournal`, migration 004). Écriture d'abord, application ensuite ; un
  journal illisible au démarrage gèle le service (:class:`StateStoreError`, fermé par défaut).

Règles de contenu : aucun ``float`` (TypeError), aucun secret (les clés de type jeton, mot de
passe, IBAN… sont masquées par :func:`redact`), datetimes avec fuseau. Les adaptateurs Postgres
acceptent toute connexion DB-API 2.0 au style de paramètres ``%s`` (psycopg 3 conseillé).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .errors import PokeshopError
from .models import FrozenModel

__all__ = [
    "AuditError",
    "IdempotencyError",
    "ActorKind",
    "AuditEvent",
    "AuditLog",
    "InMemoryAuditLog",
    "PostgresAuditLog",
    "ClaimStatus",
    "IdempotencyRecord",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "PostgresIdempotencyStore",
    "DBConnection",
    "to_jsonable",
    "redact",
    "REDACTED",
    "payload_sha256",
    "StateStoreError",
    "StateJournal",
    "InMemoryStateJournal",
    "JsonlStateJournal",
    "PostgresStateJournal",
    "FailedStateJournal",
    "state_row_digest",
]

REDACTED = "***MASQUÉ***"
_SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|mot_de_passe|authorization|api[_-]?key|credential|iban|cookie|session)",
    re.IGNORECASE,
)
_IDEMPOTENCY_KEY_FIELDS = frozenset({"idempotency_key", "idempotencykey"})
_ACTION_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")


class AuditError(PokeshopError, ValueError):
    """Écriture d'audit invalide ou journal altéré."""


class IdempotencyError(PokeshopError, ValueError):
    """Opération d'idempotence invalide (clé mal formée, transition interdite)."""


class ActorKind(str, Enum):
    """Nature de l'auteur d'une action (mêmes valeurs que la colonne ``audit_log.actor_kind``)."""

    AGENT = "AGENT"
    SYSTEME = "SYSTEME"
    PROPRIETAIRE = "PROPRIETAIRE"
    PRESTATAIRE = "PRESTATAIRE"


# ---------------------------------------------------------------- JSON canonique


def to_jsonable(obj: Any) -> Any:
    """Convertit une structure en JSON pur : Decimal -> str, datetime -> ISO, Enum -> valeur.

    ``float`` est refusé (TypeError) : aucun montant approximatif dans un journal (SPEC §0.1).
    """
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        raise TypeError("float interdit dans le journal : utiliser Decimal ou str")
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise TypeError("Decimal non fini interdit dans le journal")
        return str(obj)
    if isinstance(obj, Enum):
        return to_jsonable(obj.value)
    if isinstance(obj, datetime):
        if obj.tzinfo is None or obj.utcoffset() is None:
            raise TypeError("datetime naïf interdit dans le journal")
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return f"{obj // timedelta(seconds=1)}s"
    if isinstance(obj, BaseModel):
        return to_jsonable({name: getattr(obj, name) for name in type(obj).model_fields})
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted((to_jsonable(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "get_secret_value"):
        return REDACTED
    raise TypeError(f"type non journalisable : {type(obj).__name__}")


def redact(obj: Any) -> Any:
    """Masque récursivement les valeurs dont la clé évoque un secret (jeton, mot de passe, IBAN…)."""
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)
            if key.lower() not in _IDEMPOTENCY_KEY_FIELDS and _SECRET_KEY_RE.search(key):
                out[key] = REDACTED
            else:
                out[key] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_sha256(payload: Any) -> str:
    """sha256 du JSON canonique (après conversion) : empreinte d'une requête pour l'idempotence."""
    return hashlib.sha256(_canonical(to_jsonable(payload)).encode("utf-8")).hexdigest()


def _utc_text(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------- événements


class AuditEvent(FrozenModel):
    """Ligne du journal d'audit (immuable)."""

    seq: int = Field(ge=1)
    at: datetime
    actor: str = Field(min_length=1)
    actor_kind: ActorKind
    action: str = Field(min_length=1)
    entity: str = Field(min_length=1)
    entity_id: str | None = None
    dry_run: bool = True
    autonomy_level: int | None = Field(default=None, ge=1, le=4)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    prev_hash: str | None = None
    row_hash: str


@runtime_checkable
class AuditLog(Protocol):
    """Interface commune des journaux d'audit (mémoire, Postgres)."""

    def append(
        self,
        *,
        actor: str,
        actor_kind: ActorKind | str,
        action: str,
        entity: str,
        entity_id: str | None = None,
        dry_run: bool = True,
        autonomy_level: int | None = None,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> AuditEvent:
        """Ajoute une ligne et la renvoie."""
        ...

    def events(
        self, *, entity: str | None = None, entity_id: str | None = None, action: str | None = None
    ) -> tuple[AuditEvent, ...]:
        """Lignes filtrées, dans l'ordre de la chaîne."""
        ...

    def verify(self) -> list[str]:
        """Problèmes de chaîne détectés (liste vide = journal intact)."""
        ...


def _validate_entry(actor: str, action: str, entity: str, autonomy_level: int | None) -> None:
    if not actor or not actor.strip():
        raise AuditError("acteur obligatoire")
    if not _ACTION_RE.match(action):
        raise AuditError(f"action invalide : {action!r} (minuscules, chiffres, . _ : -)")
    if not entity or not entity.strip():
        raise AuditError("entité obligatoire")
    if autonomy_level is not None and (isinstance(autonomy_level, bool) or not 1 <= autonomy_level <= 4):
        raise AuditError("niveau d'autonomie hors 1..4")


def _prepare_payload(payload: Mapping[str, Any] | None) -> str:
    try:
        clean = redact(to_jsonable(dict(payload or {})))
    except TypeError as exc:
        raise AuditError(f"charge utile non journalisable : {exc}") from exc
    return _canonical(clean)


def _digest(
    prev: str | None,
    seq: int,
    at: datetime,
    actor: str,
    actor_kind: str,
    action: str,
    entity: str,
    entity_id: str | None,
    dry_run: bool,
    level: int | None,
    payload_json: str,
    idem: str | None,
) -> str:
    parts = [
        prev or "",
        str(seq),
        _utc_text(at),
        actor,
        actor_kind,
        action,
        entity,
        entity_id or "",
        "true" if dry_run else "false",
        "" if level is None else str(level),
        payload_json,
        idem or "",
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class InMemoryAuditLog:
    """Journal append-only en mémoire, chaîné sha256, thread-safe (tests, simulation, secours)."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._rows: list[tuple[AuditEvent, str]] = []

    def __len__(self) -> int:
        with self._lock:
            return len(self._rows)

    def append(
        self,
        *,
        actor: str,
        actor_kind: ActorKind | str,
        action: str,
        entity: str,
        entity_id: str | None = None,
        dry_run: bool = True,
        autonomy_level: int | None = None,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> AuditEvent:
        """Ajoute une ligne chaînée (la date est celle de l'horloge du journal, pas de l'appelant)."""
        _validate_entry(actor, action, entity, autonomy_level)
        kind = ActorKind(actor_kind)
        payload_json = _prepare_payload(payload)
        with self._lock:
            at = self._clock()
            if at.tzinfo is None or at.utcoffset() is None:
                raise AuditError("horloge du journal sans fuseau horaire")
            seq = len(self._rows) + 1
            prev = self._rows[-1][0].row_hash if self._rows else None
            row_hash = _digest(
                prev,
                seq,
                at,
                actor,
                kind.value,
                action,
                entity,
                entity_id,
                dry_run,
                autonomy_level,
                payload_json,
                idempotency_key,
            )
            event = AuditEvent(
                seq=seq,
                at=at,
                actor=actor,
                actor_kind=kind,
                action=action,
                entity=entity,
                entity_id=entity_id,
                dry_run=dry_run,
                autonomy_level=autonomy_level,
                payload=json.loads(payload_json),
                idempotency_key=idempotency_key,
                prev_hash=prev,
                row_hash=row_hash,
            )
            self._rows.append((event, payload_json))
            return event.replace(payload=json.loads(payload_json))

    def events(
        self, *, entity: str | None = None, entity_id: str | None = None, action: str | None = None
    ) -> tuple[AuditEvent, ...]:
        """Copies des lignes (charges utiles recréées depuis le JSON figé)."""
        with self._lock:
            rows = list(self._rows)
        out = []
        for event, payload_json in rows:
            if entity is not None and event.entity != entity:
                continue
            if entity_id is not None and event.entity_id != entity_id:
                continue
            if action is not None and event.action != action:
                continue
            out.append(event.replace(payload=json.loads(payload_json)))
        return tuple(out)

    def verify(self) -> list[str]:
        """Recalcule toute la chaîne ; renvoie les anomalies (vide = intact)."""
        problems: list[str] = []
        prev: str | None = None
        with self._lock:
            rows = list(self._rows)
        for expected, (event, payload_json) in enumerate(rows, start=1):
            if event.seq != expected:
                problems.append(f"{event.seq} : séquence rompue ({expected} attendu)")
            if event.prev_hash != prev:
                problems.append(f"{event.seq} : prev_hash incohérent")
            recomputed = _digest(
                event.prev_hash,
                event.seq,
                event.at,
                event.actor,
                event.actor_kind.value,
                event.action,
                event.entity,
                event.entity_id,
                event.dry_run,
                event.autonomy_level,
                payload_json,
                event.idempotency_key,
            )
            if recomputed != event.row_hash:
                problems.append(f"{event.seq} : empreinte invalide (ligne modifiée)")
            prev = event.row_hash
        return problems


# ------------------------------------------------------------------- Postgres


class _Cursor(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = ...) -> Any: ...

    def fetchone(self) -> Sequence[Any] | None: ...

    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def close(self) -> None: ...


class DBConnection(Protocol):
    """Connexion DB-API 2.0 minimale (psycopg 3, psycopg2…), paramètres au style ``%s``."""

    def cursor(self) -> Any: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


ConnectionFactory = Callable[[], DBConnection]


class _PgRunner:
    """Exécute une requête paramétrée dans une transaction courte (une connexion par appel)."""

    def __init__(self, connect: ConnectionFactory) -> None:
        self._connect = connect

    def run(self, sql: str, params: Sequence[Any], fetch: Literal["one", "all", "none"]) -> Any:
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute(sql, tuple(params))
                result: Any = None
                if fetch == "one":
                    result = cur.fetchone()
                elif fetch == "all":
                    result = cur.fetchall()
            finally:
                cur.close()
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _json_value(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


class PostgresAuditLog:
    """Journal ``pokeshop.audit_log`` : la base fixe séquence, horodatage et chaîne (002_integrity)."""

    INSERT_SQL = (
        "INSERT INTO pokeshop.audit_log (actor, actor_kind, action, entity, entity_id, dry_run, "
        "autonomy_level, payload, idempotency_key) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) "
        "RETURNING chain_seq, at, prev_hash, row_hash"
    )
    SELECT_SQL = (
        "SELECT chain_seq, at, actor, actor_kind, action, entity, entity_id, dry_run, autonomy_level, "
        "payload::text, idempotency_key, prev_hash, row_hash FROM pokeshop.audit_log"
    )
    VERIFY_SQL = "SELECT seq, problem FROM pokeshop.verify_audit_chain()"

    def __init__(self, connect: ConnectionFactory) -> None:
        self._db = _PgRunner(connect)

    def append(
        self,
        *,
        actor: str,
        actor_kind: ActorKind | str,
        action: str,
        entity: str,
        entity_id: str | None = None,
        dry_run: bool = True,
        autonomy_level: int | None = None,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> AuditEvent:
        """INSERT paramétré ; renvoie la ligne avec la séquence et l'empreinte calculées par la base."""
        _validate_entry(actor, action, entity, autonomy_level)
        kind = ActorKind(actor_kind)
        payload_json = _prepare_payload(payload)
        row = self._db.run(
            self.INSERT_SQL,
            (actor, kind.value, action, entity, entity_id, dry_run, autonomy_level, payload_json, idempotency_key),
            "one",
        )
        if row is None:
            raise AuditError("insertion d'audit sans retour")
        seq, at, prev_hash, row_hash = row
        return AuditEvent(
            seq=int(seq),
            at=at,
            actor=actor,
            actor_kind=kind,
            action=action,
            entity=entity,
            entity_id=entity_id,
            dry_run=dry_run,
            autonomy_level=autonomy_level,
            payload=json.loads(payload_json),
            idempotency_key=idempotency_key,
            prev_hash=prev_hash.strip() if isinstance(prev_hash, str) else prev_hash,
            row_hash=str(row_hash).strip(),
        )

    def events(
        self, *, entity: str | None = None, entity_id: str | None = None, action: str | None = None
    ) -> tuple[AuditEvent, ...]:
        """SELECT filtré (colonnes de filtre constantes, valeurs paramétrées)."""
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("entity", entity), ("entity_id", entity_id), ("action", action)):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        sql = self.SELECT_SQL + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY chain_seq"
        rows = self._db.run(sql, params, "all") or []
        out = []
        for r in rows:
            out.append(
                AuditEvent(
                    seq=int(r[0]),
                    at=r[1],
                    actor=r[2],
                    actor_kind=ActorKind(r[3]),
                    action=r[4],
                    entity=r[5],
                    entity_id=r[6],
                    dry_run=bool(r[7]),
                    autonomy_level=None if r[8] is None else int(r[8]),
                    payload=_json_value(r[9]) or {},
                    idempotency_key=r[10],
                    prev_hash=r[11].strip() if isinstance(r[11], str) else r[11],
                    row_hash=str(r[12]).strip(),
                )
            )
        return tuple(out)

    def verify(self) -> list[str]:
        """``pokeshop.verify_audit_chain()`` : aucune ligne = journal intact."""
        rows = self._db.run(self.VERIFY_SQL, (), "all") or []
        return [f"{seq} : {problem}" for seq, problem in rows]


# ------------------------------------------------------------------ idempotence


class ClaimStatus(str, Enum):
    """Issue d'une réservation de clé (mêmes valeurs que ``pokeshop.claim_idempotency_key``)."""

    NEW = "NEW"
    DUPLICATE_EN_COURS = "DUPLICATE_EN_COURS"
    DUPLICATE_TERMINE = "DUPLICATE_TERMINE"
    DUPLICATE_ECHEC = "DUPLICATE_ECHEC"
    CONFLICT = "CONFLICT"


class IdempotencyRecord(FrozenModel):
    """État d'une clé d'idempotence."""

    scope: str
    key: str
    request_sha256: str
    status: Literal["EN_COURS", "TERMINE", "ECHEC"]
    response: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


@runtime_checkable
class IdempotencyStore(Protocol):
    """Registre des clés d'idempotence (mémoire ou Postgres)."""

    def claim(
        self, scope: str, key: str, request_sha256: str, *, now: datetime
    ) -> tuple[ClaimStatus, IdempotencyRecord]:
        """Réserve la clé ; ``NEW`` = exécuter, sinon ne pas réécrire."""
        ...

    def complete(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """Clôt une clé EN_COURS avec succès (réponse rejouable)."""
        ...

    def fail(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """Clôt une clé EN_COURS en échec métier définitif (réponse rejouable)."""
        ...

    def release(self, scope: str, key: str) -> None:
        """Libère une clé EN_COURS après un échec transitoire (rien n'a été confirmé)."""
        ...

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        """État courant de la clé."""
        ...


_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _check_key(scope: str, key: str, request_sha256: str | None = None) -> None:
    if not scope or not scope.strip():
        raise IdempotencyError("scope d'idempotence obligatoire")
    if not isinstance(key, str) or not 8 <= len(key) <= 200:
        raise IdempotencyError("clé d'idempotence : 8 à 200 caractères")
    if request_sha256 is not None and not _SHA_RE.match(request_sha256):
        raise IdempotencyError("empreinte de requête sha256 attendue")


class InMemoryIdempotencyStore:
    """Registre d'idempotence en mémoire, thread-safe (même sémantique que la base)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}

    def claim(
        self, scope: str, key: str, request_sha256: str, *, now: datetime
    ) -> tuple[ClaimStatus, IdempotencyRecord]:
        """Réservation atomique de la clé."""
        _check_key(scope, key, request_sha256)
        with self._lock:
            existing = self._records.get((scope, key))
            if existing is None:
                record = IdempotencyRecord(
                    scope=scope, key=key, request_sha256=request_sha256, status="EN_COURS", created_at=now
                )
                self._records[(scope, key)] = record
                return ClaimStatus.NEW, record
            if existing.request_sha256 != request_sha256:
                return ClaimStatus.CONFLICT, existing
            return ClaimStatus(f"DUPLICATE_{existing.status}"), existing

    def _finish(
        self, scope: str, key: str, status: Literal["TERMINE", "ECHEC"], response: Mapping[str, Any], now: datetime
    ) -> IdempotencyRecord:
        _check_key(scope, key)
        with self._lock:
            existing = self._records.get((scope, key))
            if existing is None:
                raise IdempotencyError(f"clé {scope}/{key} inconnue")
            if existing.status != "EN_COURS":
                raise IdempotencyError(f"clé {scope}/{key} : statut final {existing.status}")
            record = existing.replace(status=status, response=to_jsonable(dict(response)), completed_at=now)
            self._records[(scope, key)] = record
            return record

    def complete(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """EN_COURS -> TERMINE."""
        return self._finish(scope, key, "TERMINE", response, now)

    def fail(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """EN_COURS -> ECHEC."""
        return self._finish(scope, key, "ECHEC", response, now)

    def release(self, scope: str, key: str) -> None:
        """Supprime une réservation EN_COURS (sans effet sur une clé close)."""
        _check_key(scope, key)
        with self._lock:
            existing = self._records.get((scope, key))
            if existing is not None and existing.status == "EN_COURS":
                del self._records[(scope, key)]

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        """État de la clé."""
        with self._lock:
            return self._records.get((scope, key))


class PostgresIdempotencyStore:
    """Registre ``pokeshop.idempotency_keys`` (fonction ``claim_idempotency_key`` et triggers de 002)."""

    CLAIM_SQL = "SELECT pokeshop.claim_idempotency_key(%s, %s, %s)"
    GET_SQL = (
        "SELECT scope, idempotency_key, request_sha256, status, response::text, created_at, completed_at "
        "FROM pokeshop.idempotency_keys WHERE scope = %s AND idempotency_key = %s"
    )
    FINISH_SQL = (
        "UPDATE pokeshop.idempotency_keys SET status = %s, response = %s::jsonb, completed_at = %s "
        "WHERE scope = %s AND idempotency_key = %s AND status = 'EN_COURS'"
    )
    RELEASE_SQL = (
        "DELETE FROM pokeshop.idempotency_keys WHERE scope = %s AND idempotency_key = %s AND status = 'EN_COURS'"
    )

    def __init__(self, connect: ConnectionFactory) -> None:
        self._db = _PgRunner(connect)

    @staticmethod
    def _record(row: Sequence[Any]) -> IdempotencyRecord:
        return IdempotencyRecord(
            scope=row[0],
            key=row[1],
            request_sha256=str(row[2]).strip(),
            status=row[3],
            response=_json_value(row[4]),
            created_at=row[5],
            completed_at=row[6],
        )

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        """État de la clé (None si absente)."""
        _check_key(scope, key)
        row = self._db.run(self.GET_SQL, (scope, key), "one")
        return None if row is None else self._record(row)

    def claim(
        self, scope: str, key: str, request_sha256: str, *, now: datetime
    ) -> tuple[ClaimStatus, IdempotencyRecord]:
        """Réservation atomique côté base (verrou de clé primaire)."""
        _check_key(scope, key, request_sha256)
        row = self._db.run(self.CLAIM_SQL, (scope, key, request_sha256), "one")
        status = ClaimStatus(row[0])
        record = self.get(scope, key)
        if record is None:  # pragma: no cover - libérée entre-temps par un autre processus
            raise IdempotencyError(f"clé {scope}/{key} disparue après réservation")
        return status, record

    def _finish(
        self, scope: str, key: str, status: str, response: Mapping[str, Any], now: datetime
    ) -> IdempotencyRecord:
        _check_key(scope, key)
        body = _canonical(to_jsonable(dict(response)))
        self._db.run(self.FINISH_SQL, (status, body, now, scope, key), "none")
        record = self.get(scope, key)
        if record is None or record.status != status:
            raise IdempotencyError(f"clé {scope}/{key} : transition vers {status} refusée")
        return record

    def complete(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """EN_COURS -> TERMINE."""
        return self._finish(scope, key, "TERMINE", response, now)

    def fail(self, scope: str, key: str, response: Mapping[str, Any], *, now: datetime) -> IdempotencyRecord:
        """EN_COURS -> ECHEC."""
        return self._finish(scope, key, "ECHEC", response, now)

    def release(self, scope: str, key: str) -> None:
        """DELETE de la réservation EN_COURS uniquement."""
        _check_key(scope, key)
        self._db.run(self.RELEASE_SQL, (scope, key), "none")


# ------------------------------------------------------------ journaux d'état


class StateStoreError(PokeshopError, RuntimeError):
    """Journal d'état illisible, altéré, en conflit ou impossible à écrire.

    Toujours traité en **fermé par défaut** : au démarrage, un journal illisible gèle le service ;
    en cours de route, une écriture refusée n'est jamais considérée comme faite.
    """


_STREAM_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _check_stream(stream: str) -> str:
    if not isinstance(stream, str) or not _STREAM_RE.match(stream):
        raise StateStoreError(f"nom de journal d'état invalide : {stream!r}")
    return stream


def state_row_digest(prev_hash: str | None, seq: int, body: str) -> str:
    """Empreinte d'une ligne de journal d'état : sha256(prev ␟ seq ␟ corps JSON canonique).

    Même formule que la fonction SQL ``pokeshop.state_row_digest`` (migration 004).
    """
    return hashlib.sha256("\x1f".join((prev_hash or "", str(seq), body)).encode("utf-8")).hexdigest()


def _state_body(record: Mapping[str, Any]) -> str:
    try:
        return _canonical(to_jsonable(dict(record)))
    except TypeError as exc:
        raise StateStoreError(f"enregistrement d'état non sérialisable : {exc}") from exc


@runtime_checkable
class StateJournal(Protocol):
    """Journal d'état **en ajout seul**, chaîné sha256, d'un composant de sécurité (« flux »).

    ``load`` relit tout le flux (et vérifie la chaîne) ; ``append`` écrit une ligne **avant**
    que l'appelant n'applique le changement en mémoire (écriture d'abord) et lève
    :class:`StateStoreError` si elle n'est pas durablement enregistrée.
    """

    stream: str
    backend: str

    def load(self) -> list[dict[str, Any]]:
        """Enregistrements du flux, du plus ancien au plus récent (StateStoreError si illisible)."""
        ...

    def append(self, record: Mapping[str, Any]) -> int:
        """Ajoute un enregistrement ; renvoie son numéro de séquence (StateStoreError si refusé)."""
        ...


class _ChainState:
    """Position courante de la chaîne (séquence, dernière empreinte) d'un flux."""

    def __init__(self) -> None:
        self.loaded = False
        self.seq = 0
        self.last_hash: str | None = None

    def verify(self, stream: str, rows: Sequence[tuple[int, str | None, str, str]]) -> list[dict[str, Any]]:
        """Vérifie séquence, chaînage et empreintes ; renvoie les corps décodés."""
        out: list[dict[str, Any]] = []
        prev: str | None = None
        for expected, (seq, prev_hash, row_hash, body) in enumerate(rows, start=1):
            if seq != expected:
                raise StateStoreError(f"journal d'état {stream} : séquence rompue en {seq} ({expected} attendu)")
            if (prev_hash or None) != prev:
                raise StateStoreError(f"journal d'état {stream} : chaînage rompu en {seq}")
            if state_row_digest(prev, seq, body) != row_hash:
                raise StateStoreError(f"journal d'état {stream} : ligne {seq} modifiée (empreinte invalide)")
            try:
                data = json.loads(body)
            except ValueError as exc:
                raise StateStoreError(f"journal d'état {stream} : ligne {seq} illisible") from exc
            if not isinstance(data, dict):
                raise StateStoreError(f"journal d'état {stream} : ligne {seq} n'est pas un objet JSON")
            out.append(data)
            prev = row_hash
        self.loaded = True
        self.seq = len(rows)
        self.last_hash = prev
        return out

    def next_row(self, record: Mapping[str, Any]) -> tuple[int, str | None, str, str]:
        body = _state_body(record)
        seq = self.seq + 1
        return seq, self.last_hash, state_row_digest(self.last_hash, seq, body), body

    def advance(self, seq: int, row_hash: str) -> None:
        self.seq = seq
        self.last_hash = row_hash


class InMemoryStateJournal:
    """Journal d'état en mémoire (tests ; ``POKESHOP_STATE_DIR=:memory:`` hors production)."""

    backend = "memoire"

    def __init__(self, stream: str) -> None:
        self.stream = _check_stream(stream)
        self._lock = threading.RLock()
        self._rows: list[tuple[int, str | None, str, str]] = []
        self._chain = _ChainState()

    def load(self) -> list[dict[str, Any]]:
        """Relit (et vérifie) le flux."""
        with self._lock:
            return self._chain.verify(self.stream, self._rows)

    def append(self, record: Mapping[str, Any]) -> int:
        """Ajout seul."""
        with self._lock:
            if not self._chain.loaded:
                self._chain.verify(self.stream, self._rows)
            row = self._chain.next_row(record)
            self._rows.append(row)
            self._chain.advance(row[0], row[2])
            return row[0]


class JsonlStateJournal:
    """Journal d'état dans un fichier JSON Lines en **ajout seul** (``<POKESHOP_STATE_DIR>/<flux>.jsonl``).

    Chaque ligne : ``{"seq", "prev", "hash", "data"}`` ; la chaîne sha256 détecte une ligne
    modifiée, supprimée au milieu ou tronquée. Écriture : verrou exclusif (``flock``), contrôle
    que personne d'autre n'a écrit depuis la dernière lecture (taille du fichier), ``fsync``.
    Un seul processus écrivain par fichier : un second écrivain est refusé (conflit).
    """

    backend = "fichier"

    def __init__(self, path: str | Path, *, stream: str | None = None) -> None:
        self.path = Path(path)
        self.stream = _check_stream(stream or self.path.stem)
        self._lock = threading.RLock()
        self._chain = _ChainState()
        self._size = 0

    def _ensure_dir(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateStoreError(f"dossier d'état {self.path.parent} inaccessible ({exc.strerror})") from exc
        if not os.access(self.path.parent, os.W_OK | os.X_OK):
            raise StateStoreError(f"dossier d'état {self.path.parent} non inscriptible")

    def _read_rows(self) -> tuple[list[tuple[int, str | None, str, str]], int]:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return [], 0
        except OSError as exc:
            raise StateStoreError(f"journal d'état {self.path} illisible ({exc.strerror})") from exc
        if raw and not raw.endswith(b"\n"):
            raise StateStoreError(f"journal d'état {self.path} : dernière ligne tronquée (écriture interrompue ?)")
        rows: list[tuple[int, str | None, str, str]] = []
        for n, line in enumerate(raw.decode("utf-8", errors="strict").split("\n")[:-1] if raw else [], start=1):
            try:
                item = json.loads(line)
                seq, prev, row_hash, data = item["seq"], item["prev"], item["hash"], item["data"]
            except (ValueError, KeyError, TypeError) as exc:
                raise StateStoreError(f"journal d'état {self.path} : ligne {n} illisible") from exc
            if isinstance(seq, bool) or not isinstance(seq, int) or not isinstance(row_hash, str):
                raise StateStoreError(f"journal d'état {self.path} : ligne {n} mal formée")
            rows.append((seq, prev, row_hash, _canonical(data)))
        return rows, len(raw)

    def load(self) -> list[dict[str, Any]]:
        """Relit et vérifie tout le fichier ; crée le dossier au besoin (contrôle d'écriture)."""
        with self._lock:
            self._ensure_dir()
            try:
                rows, size = self._read_rows()
            except UnicodeDecodeError as exc:
                raise StateStoreError(f"journal d'état {self.path} : encodage invalide") from exc
            data = self._chain.verify(self.stream, rows)
            self._size = size
            return data

    def append(self, record: Mapping[str, Any]) -> int:
        """Écrit une ligne (verrou exclusif, contrôle de conflit, fsync) ; StateStoreError sinon."""
        import fcntl

        with self._lock:
            if not self._chain.loaded:
                self.load()
            seq, prev, row_hash, body = self._chain.next_row(record)
            line = _canonical({"data": json.loads(body), "hash": row_hash, "prev": prev, "seq": seq}) + "\n"
            encoded = line.encode("utf-8")
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            except OSError as exc:
                raise StateStoreError(f"journal d'état {self.path} : ouverture impossible ({exc.strerror})") from exc
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                size = os.fstat(fd).st_size
                if size != self._size:
                    raise StateStoreError(
                        f"journal d'état {self.path} modifié par un autre processus : écriture refusée "
                        "(un seul service par dossier d'état ; redémarrer pour relire)"
                    )
                written = os.write(fd, encoded)
                if written != len(encoded):
                    raise StateStoreError(f"journal d'état {self.path} : écriture partielle")
                os.fsync(fd)
            except OSError as exc:
                raise StateStoreError(f"journal d'état {self.path} : écriture impossible ({exc.strerror})") from exc
            finally:
                os.close(fd)
            self._size += len(encoded)
            self._chain.advance(seq, row_hash)
            return seq


class PostgresStateJournal:
    """Journal d'état dans ``pokeshop.engine_state_journal`` (migration 004, ajout seul).

    La base refuse UPDATE/DELETE/TRUNCATE, impose la séquence continue et le chaînage par flux
    (trigger) et vérifie l'empreinte : un second écrivain concurrent est refusé.
    """

    backend = "postgres"

    SELECT_SQL = (
        "SELECT seq, prev_hash, row_hash, body FROM pokeshop.engine_state_journal WHERE stream = %s ORDER BY seq"
    )
    INSERT_SQL = (
        "INSERT INTO pokeshop.engine_state_journal (stream, seq, prev_hash, row_hash, body) "
        "VALUES (%s, %s, %s, %s, %s)"
    )

    def __init__(self, connect: ConnectionFactory, stream: str) -> None:
        self.stream = _check_stream(stream)
        self._db = _PgRunner(connect)
        self._lock = threading.RLock()
        self._chain = _ChainState()

    def load(self) -> list[dict[str, Any]]:
        """SELECT du flux puis vérification de la chaîne."""
        with self._lock:
            try:
                rows = self._db.run(self.SELECT_SQL, (self.stream,), "all") or []
            except Exception as exc:  # noqa: BLE001 - toute panne de base = journal illisible (fermé)
                raise StateStoreError(
                    f"journal d'état {self.stream} : lecture en base impossible ({type(exc).__name__})"
                ) from exc
            clean = [
                (int(r[0]), r[1].strip() if isinstance(r[1], str) else r[1], str(r[2]).strip(), str(r[3])) for r in rows
            ]
            return self._chain.verify(self.stream, clean)

    def append(self, record: Mapping[str, Any]) -> int:
        """INSERT de la ligne suivante de la chaîne (la base refuse tout trou ou doublon)."""
        with self._lock:
            if not self._chain.loaded:
                self.load()
            seq, prev, row_hash, body = self._chain.next_row(record)
            try:
                self._db.run(self.INSERT_SQL, (self.stream, seq, prev, row_hash, body), "none")
            except Exception as exc:  # noqa: BLE001 - conflit ou panne : rien n'est considéré comme écrit
                raise StateStoreError(
                    f"journal d'état {self.stream} : écriture en base refusée ({type(exc).__name__}: {exc})"
                ) from exc
            self._chain.advance(seq, row_hash)
            return seq


class FailedStateJournal:
    """Journal d'un flux qui n'a pas pu être relu au démarrage : toute écriture est refusée."""

    backend = "indisponible"

    def __init__(self, stream: str, reason: str) -> None:
        self.stream = _check_stream(stream)
        self.reason = reason

    def load(self) -> list[dict[str, Any]]:
        """Toujours en échec."""
        raise StateStoreError(f"journal d'état {self.stream} indisponible : {self.reason}")

    def append(self, record: Mapping[str, Any]) -> int:
        """Toujours refusé (le service reste gelé jusqu'à réparation et redémarrage)."""
        raise StateStoreError(f"journal d'état {self.stream} indisponible : {self.reason}")
