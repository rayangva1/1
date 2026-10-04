"""Types communs des connecteurs fournisseurs (SPEC §2.5, BP §6 et §12).

* :class:`RawSnapshot` — capture brute **datée** d'une source (contenu + horodatages + source +
  sha256). Elle est conservée telle quelle (table ``raw_snapshots``) pour l'audit.
* :class:`SupplierConnector` — ``fetch() -> RawSnapshot`` puis ``parse(snapshot) -> ImportResult``.
  ``run()`` ne lève jamais : une panne de flux donne un résultat ``FAILED`` qui conserve les
  offres précédentes et ne touche jamais au stock local (BP §12 « Workflow incident »).
* :class:`ImportResult` — offres valides, lignes en quarantaine (motifs), anomalies, statut,
  niveau d'escalade (brief A-03 §9) et rapport Markdown prêt à archiver.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator, model_validator

from pokeshop.errors import PokeshopError
from pokeshop.importers.values import CellValue
from pokeshop.models import FrozenModel, SupplierOffer

if TYPE_CHECKING:
    from pokeshop.importers.mapping import SupplierMapping
    from pokeshop.rules import RuleSet

__all__ = [
    "ImporterError",
    "FetchError",
    "SourceReadError",
    "SourceKind",
    "RawSnapshot",
    "SnapshotMeta",
    "Severity",
    "QuarantineReason",
    "QUARANTINE_LABELS_FR",
    "SNAPSHOT_LEVEL_REASONS",
    "AnomalyCode",
    "Anomaly",
    "QuarantinedRow",
    "ImportStatus",
    "ImportPolicy",
    "BaselinePrice",
    "ImportBaseline",
    "ImportResult",
    "RawRecord",
    "RecordBatch",
    "SupplierConnector",
    "FileConnector",
    "BytesConnector",
    "utcnow",
]


def utcnow() -> datetime:
    """Horloge par défaut (UTC, avec fuseau)."""
    return datetime.now(UTC)


class ImporterError(PokeshopError, ValueError):
    """Erreur d'import (racine)."""


class FetchError(ImporterError):
    """La source n'a pas pu être récupérée (panne de flux, fichier absent, accès refusé)."""


class SourceReadError(ImporterError):
    """Le contenu récupéré est illisible (encodage, fichier corrompu, XML invalide, DTD)."""


class SourceKind(str, Enum):
    """Nature de la source (BP §6 « Acquisition des données »)."""

    API = "API"
    CSV = "CSV"
    XLSX = "XLSX"
    XML = "XML"
    EMAIL = "EMAIL"
    PDF = "PDF"
    MANUAL = "MANUAL"


def _aware(value: datetime | None, name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


class SnapshotMeta(FrozenModel):
    """Métadonnées d'une capture (sans le contenu) — recopiées dans chaque résultat d'import."""

    supplier_id: str
    source_kind: SourceKind
    source_uri: str
    fetched_at: datetime
    source_ts: datetime | None = None
    checksum_sha256: str
    byte_size: int = Field(ge=0)
    fictif: bool = False

    @property
    def snapshot_id(self) -> str:
        """Identifiant stable : ``<fournisseur>:<16 premiers caractères du sha256>``."""
        return f"{self.supplier_id}:{self.checksum_sha256[:16]}"


class RawSnapshot(FrozenModel):
    """Capture brute datée d'une source fournisseur. Le sha256 est recalculé et vérifié."""

    supplier_id: str = Field(min_length=1)
    source_kind: SourceKind
    source_uri: str = Field(min_length=1)
    content: bytes = Field(repr=False)
    fetched_at: datetime
    source_ts: datetime | None = None
    """Horodatage déclaré par la source (export, en-tête HTTP…) s'il est connu à la capture."""
    checksum_sha256: str = ""
    fictif: bool = False

    @field_validator("fetched_at")
    @classmethod
    def _fetched(cls, v: datetime) -> datetime:
        _aware(v, "fetched_at")
        return v

    @field_validator("source_ts")
    @classmethod
    def _source(cls, v: datetime | None) -> datetime | None:
        return _aware(v, "source_ts")

    @model_validator(mode="before")
    @classmethod
    def _fill_checksum(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and not data.get("checksum_sha256") and isinstance(data.get("content"), bytes):
            data = {**data, "checksum_sha256": hashlib.sha256(data["content"]).hexdigest()}
        return data

    @model_validator(mode="after")
    def _checksum(self) -> RawSnapshot:
        if self.checksum_sha256 != hashlib.sha256(self.content).hexdigest():
            raise ValueError("checksum_sha256 ne correspond pas au contenu (capture altérée)")
        return self

    @classmethod
    def capture(
        cls,
        *,
        supplier_id: str,
        content: bytes,
        source_kind: SourceKind,
        source_uri: str,
        fetched_at: datetime,
        source_ts: datetime | None = None,
        fictif: bool = False,
    ) -> RawSnapshot:
        """Crée une capture et calcule son sha256."""
        return cls(
            supplier_id=supplier_id,
            source_kind=source_kind,
            source_uri=source_uri,
            content=content,
            fetched_at=fetched_at,
            source_ts=source_ts,
            fictif=fictif,
        )

    @property
    def byte_size(self) -> int:
        """Taille du contenu en octets."""
        return len(self.content)

    def meta(self) -> SnapshotMeta:
        """Métadonnées sans le contenu."""
        return SnapshotMeta(
            supplier_id=self.supplier_id,
            source_kind=self.source_kind,
            source_uri=self.source_uri,
            fetched_at=self.fetched_at,
            source_ts=self.source_ts,
            checksum_sha256=self.checksum_sha256,
            byte_size=self.byte_size,
            fictif=self.fictif,
        )


class Severity(str, Enum):
    """Gravité d'une anomalie."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class QuarantineReason(str, Enum):
    """Motifs de quarantaine (codes stables). Une ligne en quarantaine n'alimente rien."""

    MISSING_SKU = "MISSING_SKU"
    MISSING_PRICE = "MISSING_PRICE"
    UNPARSEABLE_PRICE = "UNPARSEABLE_PRICE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    UNKNOWN_CURRENCY = "UNKNOWN_CURRENCY"
    CURRENCY_CONFLICT = "CURRENCY_CONFLICT"
    UNKNOWN_VAT_BASIS = "UNKNOWN_VAT_BASIS"
    UNKNOWN_UNIT_BASIS = "UNKNOWN_UNIT_BASIS"
    UNIT_CONFLICT = "UNIT_CONFLICT"
    INVALID_GTIN = "INVALID_GTIN"
    UNKNOWN_LANGUAGE = "UNKNOWN_LANGUAGE"
    INVALID_TIER = "INVALID_TIER"
    UNPARSEABLE_VALUE = "UNPARSEABLE_VALUE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    MALFORMED_ROW = "MALFORMED_ROW"
    STALE_SOURCE = "STALE_SOURCE"
    DUPLICATE_SKU = "DUPLICATE_SKU"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    CURRENCY_CHANGED = "CURRENCY_CHANGED"
    VAT_BASIS_CHANGED = "VAT_BASIS_CHANGED"
    FICTIF_FLAG_MISMATCH = "FICTIF_FLAG_MISMATCH"
    INVALID_ROW = "INVALID_ROW"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"
    INCOMPLETE_IMPORT = "INCOMPLETE_IMPORT"
    EMPTY_IMPORT = "EMPTY_IMPORT"
    FETCH_FAILED = "FETCH_FAILED"
    UNREADABLE_SOURCE = "UNREADABLE_SOURCE"
    MAPPING_MISMATCH = "MAPPING_MISMATCH"


QUARANTINE_LABELS_FR: dict[QuarantineReason, str] = {
    QuarantineReason.MISSING_SKU: "SKU fournisseur absent : ligne non traçable.",
    QuarantineReason.MISSING_PRICE: "Prix absent.",
    QuarantineReason.UNPARSEABLE_PRICE: "Prix illisible ou ambigu (séparateur décimal).",
    QuarantineReason.NON_POSITIVE_PRICE: "Prix nul ou négatif : anomalie d'import (BP §13).",
    QuarantineReason.UNKNOWN_CURRENCY: "Devise absente, ambiguë ou non autorisée.",
    QuarantineReason.CURRENCY_CONFLICT: "Devise de la cellule ≠ devise de la colonne.",
    QuarantineReason.UNKNOWN_VAT_BASIS: "Base HT/TTC inconnue.",
    QuarantineReason.UNKNOWN_UNIT_BASIS: "Base unité/carton ou conditionnement inconnu.",
    QuarantineReason.UNIT_CONFLICT: "Prix « à l'unité » mais conditionnement > 1 : incohérent.",
    QuarantineReason.INVALID_GTIN: "GTIN/EAN invalide (checksum GS1 ou longueur).",
    QuarantineReason.UNKNOWN_LANGUAGE: "Langue inconnue, multiple ou non applicable.",
    QuarantineReason.INVALID_TIER: "Paliers de remise incohérents.",
    QuarantineReason.UNPARSEABLE_VALUE: "Valeur illisible (quantité, taux, date, horodatage).",
    QuarantineReason.INVALID_QUANTITY: "Quantité invalide (négative ou nulle).",
    QuarantineReason.MALFORMED_ROW: "Ligne mal formée (nombre de colonnes).",
    QuarantineReason.STALE_SOURCE: "Donnée de la ligne > 24 h (ou datée dans le futur).",
    QuarantineReason.DUPLICATE_SKU: "SKU en double avec des valeurs différentes.",
    QuarantineReason.PRICE_ANOMALY: "Prix ×10 ou ÷10 par rapport au dernier import.",
    QuarantineReason.CURRENCY_CHANGED: "Devise changée depuis le dernier import, sans annonce.",
    QuarantineReason.VAT_BASIS_CHANGED: "Base HT/TTC changée depuis le dernier import, sans annonce.",
    QuarantineReason.FICTIF_FLAG_MISMATCH: "Donnée FICTIVE dans un flux réel (ou l'inverse).",
    QuarantineReason.INVALID_ROW: "Ligne refusée par le modèle d'offre.",
    QuarantineReason.STALE_SNAPSHOT: "Capture > 24 h : import entier en quarantaine.",
    QuarantineReason.INCOMPLETE_IMPORT: "Import incomplet (lignes < seuil vs précédent).",
    QuarantineReason.EMPTY_IMPORT: "Import vide.",
    QuarantineReason.FETCH_FAILED: "Flux indisponible : offres précédentes conservées, stock local intact.",
    QuarantineReason.UNREADABLE_SOURCE: "Fichier illisible (encodage, format, DTD interdite).",
    QuarantineReason.MAPPING_MISMATCH: "Colonnes obligatoires absentes ou ambiguës.",
}

SNAPSHOT_LEVEL_REASONS = frozenset(
    {
        QuarantineReason.STALE_SNAPSHOT,
        QuarantineReason.INCOMPLETE_IMPORT,
        QuarantineReason.EMPTY_IMPORT,
        QuarantineReason.FETCH_FAILED,
        QuarantineReason.UNREADABLE_SOURCE,
        QuarantineReason.MAPPING_MISMATCH,
    }
)
"""Motifs qui mettent l'import entier en quarantaine (ou en échec)."""

_E1_ROW_REASONS = frozenset(
    {QuarantineReason.PRICE_ANOMALY.value, QuarantineReason.CURRENCY_CHANGED.value, QuarantineReason.VAT_BASIS_CHANGED.value}
)


class AnomalyCode(str, Enum):
    """Signaux non bloquants (ou de niveau import) — codes stables."""

    MISSING_GTIN = "MISSING_GTIN"
    CASE_LEVEL_GTIN = "CASE_LEVEL_GTIN"
    UNKNOWN_FORMAT = "UNKNOWN_FORMAT"
    UNKNOWN_EXTENSION = "UNKNOWN_EXTENSION"
    AMBIGUOUS_EXTENSION = "AMBIGUOUS_EXTENSION"
    MISSING_CONTENT = "MISSING_CONTENT"
    UNKNOWN_SEALED = "UNKNOWN_SEALED"
    NOT_SEALED = "NOT_SEALED"
    MISSING_VAT_RATE = "MISSING_VAT_RATE"
    ALLOCATION_NOT_FIRM = "ALLOCATION_NOT_FIRM"
    UNKNOWN_AVAILABILITY = "UNKNOWN_AVAILABILITY"
    UNPARSEABLE_OPTIONAL = "UNPARSEABLE_OPTIONAL"
    APPROXIMATE_STOCK = "APPROXIMATE_STOCK"
    MOQ_NOT_CARTON_MULTIPLE = "MOQ_NOT_CARTON_MULTIPLE"
    PRICE_CHANGE_LARGE = "PRICE_CHANGE_LARGE"
    MISSING_SINCE_PREVIOUS = "MISSING_SINCE_PREVIOUS"
    NEW_SINCE_PREVIOUS = "NEW_SINCE_PREVIOUS"
    SOURCE_TS_ASSUMED = "SOURCE_TS_ASSUMED"
    SAME_CONTENT_AS_PREVIOUS = "SAME_CONTENT_AS_PREVIOUS"
    MAPPING_TEMPLATE = "MAPPING_TEMPLATE"
    UNMAPPED_COLUMNS = "UNMAPPED_COLUMNS"
    CURRENCY_NOT_CONFIGURED = "CURRENCY_NOT_CONFIGURED"
    QUARANTINE_RATIO_EXCEEDED = "QUARANTINE_RATIO_EXCEEDED"
    DUPLICATE_IDENTICAL_ROW = "DUPLICATE_IDENTICAL_ROW"
    BLANK_ROWS = "BLANK_ROWS"
    INVALID_COUNTRY = "INVALID_COUNTRY"
    ASSISTED_IMPORT_VALIDATED = "ASSISTED_IMPORT_VALIDATED"


class Anomaly(FrozenModel):
    """Signal d'import : ``code`` (AnomalyCode ou QuarantineReason de niveau import)."""

    code: str
    severity: Severity
    detail: str = ""
    line_no: int | None = None
    supplier_sku: str | None = None


class QuarantinedRow(FrozenModel):
    """Ligne mise de côté : jamais transformée en offre ni en prix."""

    line_no: int | None
    supplier_sku: str | None
    reasons: tuple[str, ...] = Field(min_length=1)
    details: tuple[str, ...] = ()
    raw: dict[str, str | None] = Field(default_factory=dict)


class ImportStatus(str, Enum):
    """Statut global d'un import."""

    ACCEPTED = "ACCEPTED"
    PARTIAL = "PARTIAL"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class ImportPolicy(FrozenModel):
    """Seuils des contrôles d'import. Valeurs marquées *hypothèse* : à valider (brief A-03)."""

    max_age: timedelta = timedelta(hours=24)
    """BP §5 : donnée amont > 24 h => achats et promesses bloqués."""
    future_skew: timedelta = timedelta(minutes=5)
    min_rows_ratio: Decimal = Field(default=Decimal("0.8"), gt=0, le=1)
    """Hypothèse : import incomplet si lignes < 80 % de l'import précédent."""
    price_anomaly_factor: Decimal = Field(default=Decimal("10"), gt=1)
    """BP §13 : prix ×10 / ÷10."""
    price_warning_ratio: Decimal = Field(default=Decimal("1.5"), gt=1)
    """Hypothèse : variation ≥ ×1,5 signalée (carton pris pour unité ?), sans quarantaine."""
    max_quarantine_ratio: Decimal = Field(default=Decimal("0.2"), ge=0, le=1)
    """Hypothèse brief A-03 : > 20 % de lignes en quarantaine => escalade E1."""

    @classmethod
    def from_rules(cls, rules: RuleSet, **overrides: Any) -> ImportPolicy:
        """Politique alignée sur les règles versionnées (fraîcheur, facteur d'anomalie)."""
        data: dict[str, Any] = {
            "max_age": rules.stock.max_age,
            "future_skew": timedelta(minutes=rules.stock.future_skew_minutes),
            "price_anomaly_factor": rules.pricing.price_anomaly_factor,
        }
        data.update(overrides)
        return cls(**data)


class BaselinePrice(FrozenModel):
    """Dernier prix accepté d'un SKU (par unité de vente, dans la devise et la base d'origine)."""

    currency: str
    price_includes_vat: bool
    unit_price: Decimal = Field(gt=0)


class ImportBaseline(FrozenModel):
    """Référence de comparaison : dernier import accepté (prix, nombre de lignes, sha256)."""

    supplier_id: str
    rows_read: int = Field(ge=0)
    checksum_sha256: str
    taken_at: datetime
    prices: dict[str, BaselinePrice] = Field(default_factory=dict)

    @staticmethod
    def _prices(offers: tuple[SupplierOffer, ...]) -> dict[str, BaselinePrice]:
        out: dict[str, BaselinePrice] = {}
        for offer in offers:
            if offer.price is None or offer.price <= 0 or offer.currency is None or offer.price_includes_vat is None:
                continue
            units = offer.units_per_pack or 1
            out[offer.supplier_sku] = BaselinePrice(
                currency=offer.currency,
                price_includes_vat=offer.price_includes_vat,
                unit_price=offer.price / units,
            )
        return out

    @classmethod
    def from_result(cls, result: ImportResult) -> ImportBaseline:
        """Référence initiale depuis un import ACCEPTED ou PARTIAL."""
        if result.status not in (ImportStatus.ACCEPTED, ImportStatus.PARTIAL):
            raise ImporterError("un import en quarantaine ou en échec ne peut pas servir de référence")
        return cls(
            supplier_id=result.supplier_id,
            rows_read=result.rows_read,
            checksum_sha256=result.snapshot.checksum_sha256,
            taken_at=result.snapshot.fetched_at,
            prices=cls._prices(result.offers),
        )

    def updated_with(self, result: ImportResult) -> ImportBaseline:
        """Nouvelle référence après un import ; inchangée si l'import est rejeté (QUARANTINED/FAILED)."""
        if result.supplier_id != self.supplier_id:
            raise ImporterError("référence d'un autre fournisseur")
        if result.status not in (ImportStatus.ACCEPTED, ImportStatus.PARTIAL):
            return self
        prices = dict(self.prices)
        prices.update(self._prices(result.offers))
        return ImportBaseline(
            supplier_id=self.supplier_id,
            rows_read=result.rows_read,
            checksum_sha256=result.snapshot.checksum_sha256,
            taken_at=result.snapshot.fetched_at,
            prices=prices,
        )


class ImportResult(FrozenModel):
    """Résultat d'un import (toujours en simulation tant que ``dry_run``)."""

    supplier_id: str
    mapping_version: str
    snapshot: SnapshotMeta
    status: ImportStatus
    offers: tuple[SupplierOffer, ...] = ()
    quarantined: tuple[QuarantinedRow, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()
    rows_read: int = Field(default=0, ge=0)
    effective_source_ts: datetime | None = None
    evaluated_at: datetime
    dry_run: bool = True
    fictif: bool = False
    assisted: bool = False
    validated_by: str | None = None

    @property
    def accepted_count(self) -> int:
        """Nombre d'offres valides."""
        return len(self.offers)

    @property
    def quarantined_count(self) -> int:
        """Nombre de lignes en quarantaine."""
        return len(self.quarantined)

    @property
    def quarantine_ratio(self) -> Decimal:
        """Part des lignes lues en quarantaine (0 si aucune ligne)."""
        if self.rows_read == 0:
            return Decimal(0)
        return Decimal(self.quarantined_count) / Decimal(self.rows_read)

    @property
    def retain_previous_offers(self) -> bool:
        """Vrai si l'import est rejeté : garder les offres précédentes (elles vieillissent seules)."""
        return self.status in (ImportStatus.QUARANTINED, ImportStatus.FAILED)

    @property
    def offers_by_sku(self) -> dict[str, SupplierOffer]:
        """Offres valides indexées par SKU fournisseur."""
        return {o.supplier_sku: o for o in self.offers}

    def reason_counts(self) -> dict[str, int]:
        """Nombre de lignes par motif de quarantaine."""
        counter: Counter[str] = Counter()
        for row in self.quarantined:
            counter.update(set(row.reasons))
        return dict(sorted(counter.items()))

    def anomalies_with(self, code: str | Enum) -> tuple[Anomaly, ...]:
        """Anomalies d'un code donné."""
        value = code.value if isinstance(code, Enum) else code
        return tuple(a for a in self.anomalies if a.code == value)

    def quarantined_with(self, reason: str | Enum) -> tuple[QuarantinedRow, ...]:
        """Lignes en quarantaine portant ce motif."""
        value = reason.value if isinstance(reason, Enum) else reason
        return tuple(r for r in self.quarantined if value in r.reasons)

    @property
    def escalation(self) -> str | None:
        """``"E1"`` (brief A-03 §9) si import rejeté, anomalie critique ou prix/devise/base suspects."""
        if self.status in (ImportStatus.QUARANTINED, ImportStatus.FAILED):
            return "E1"
        if any(a.severity is Severity.CRITICAL for a in self.anomalies):
            return "E1"
        if any(_E1_ROW_REASONS & set(r.reasons) for r in self.quarantined):
            return "E1"
        return None

    def report_markdown(self) -> str:
        """Rapport d'import INTERNE (modèle du brief A-03 §12).

        Il peut citer des prix fournisseur (B2B) dans le détail des quarantaines : à archiver
        dans l'espace interne uniquement, jamais publié ni injecté dans un prompt marketing.
        """
        snap = self.snapshot
        mode = "SIMULATION" if self.dry_run else "RÉEL"
        lines = [
            f"# Import — {self.supplier_id} — {self.evaluated_at:%Y-%m-%d %H:%M} — mode {mode}",
            "",
            f"Source : {snap.source_kind.value} `{snap.source_uri}` · capture {snap.fetched_at.isoformat()} · "
            f"sha256 `{snap.checksum_sha256[:16]}…` · dictionnaire {self.mapping_version}"
            + (" · **FICTIF**" if self.fictif else ""),
            f"Statut : **{self.status.value}**" + (f" · escalade {self.escalation}" if self.escalation else ""),
            f"Lignes : lues {self.rows_read} · acceptées {self.accepted_count} · quarantaine "
            f"{self.quarantined_count}"
            + (" (motifs : " + ", ".join(f"{k}×{v}" for k, v in self.reason_counts().items()) + ")" if self.quarantined else ""),
        ]
        if self.effective_source_ts is not None:
            age = self.evaluated_at - self.effective_source_ts
            hours = Decimal(int(age.total_seconds())) / Decimal(3600)
            stale = any(a.code == QuarantineReason.STALE_SNAPSHOT.value for a in self.anomalies)
            lines.append(
                f"Fraîcheur : {hours.quantize(Decimal('0.1'))} h → "
                + ("**périmé : achats et promesses bloqués**" if stale else "OK")
            )
        if self.assisted:
            lines.append(f"Import assisté validé par : {self.validated_by}")
        drift = [a for a in self.anomalies if a.code in (AnomalyCode.MISSING_SINCE_PREVIOUS.value, AnomalyCode.NEW_SINCE_PREVIOUS.value)]
        if drift:
            lines.append("Écarts avec l'import précédent : " + " ; ".join(a.detail for a in drift))
        if self.quarantined:
            lines += ["", "## Quarantaine", "", "| Ligne | SKU | Motifs | Détail |", "|---|---|---|---|"]
            for row in self.quarantined:
                detail = " ; ".join(row.details).replace("|", "/")
                lines.append(f"| {row.line_no or '—'} | {row.supplier_sku or '—'} | {', '.join(row.reasons)} | {detail} |")
        if self.anomalies:
            lines += ["", "## Anomalies", "", "| Gravité | Code | Ligne | Détail |", "|---|---|---|---|"]
            for a in self.anomalies:
                lines.append(f"| {a.severity.value} | {a.code} | {a.line_no or '—'} | {a.detail.replace('|', '/')} |")
        lines += ["", "## Validation humaine requise", ""]
        checks = []
        if self.quarantined:
            checks.append("Traiter chaque ligne en quarantaine (correction fournisseur via A-02 ou dictionnaire de champs).")
        if self.escalation:
            checks.append("Escalade E1 : informer A-01 et A-12 (brief A-03 §9).")
        if any(a.code == AnomalyCode.MAPPING_TEMPLATE.value for a in self.anomalies):
            checks.append("Dictionnaire TEMPLATE : confirmer le format sur un fichier réel avant tout usage.")
        if not checks:
            checks.append("Aucune action bloquante : contrôle par sondage des offres importées.")
        lines += [f"- [ ] {c}" for c in checks]
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class RawRecord:
    """Enregistrement brut (ligne CSV/Excel ou élément XML) : en-tête -> valeur de cellule."""

    line_no: int
    cells: Mapping[str, CellValue]
    malformed: str | None = None


@dataclass(frozen=True)
class RecordBatch:
    """Enregistrements lus dans une capture, avec l'horodatage d'export s'il existe."""

    records: tuple[RawRecord, ...]
    header: tuple[str, ...]
    source_ts_raw: CellValue = None
    blank_rows: int = 0
    notes: tuple[str, ...] = field(default=())


class SupplierConnector(ABC):
    """Connecteur fournisseur : récupère une capture puis la transforme en offres.

    Les connecteurs concrets n'implémentent que :meth:`fetch` (API autorisée, fichier,
    téléchargement authentifié selon l'accord écrit). Aucun scraping, aucun contournement
    de contrôle d'accès (SPEC §0.9).
    """

    def __init__(self, mapping: SupplierMapping, *, clock: Callable[[], datetime] | None = None) -> None:
        self.mapping = mapping
        self.clock = clock or utcnow

    @property
    def supplier_id(self) -> str:
        """Identifiant fournisseur du dictionnaire."""
        return self.mapping.supplier_id

    @abstractmethod
    def fetch(self) -> RawSnapshot:
        """Récupère la source et la date. Lève :class:`FetchError` en cas de panne."""

    def parse(self, snapshot: RawSnapshot, **kwargs: Any) -> ImportResult:
        """Transforme une capture en résultat d'import (voir :func:`pokeshop.importers.runner.parse_snapshot`)."""
        from pokeshop.importers.runner import parse_snapshot

        kwargs.setdefault("now", self.clock())
        return parse_snapshot(snapshot, self.mapping, **kwargs)

    def run(self, **kwargs: Any) -> ImportResult:
        """``fetch`` + ``parse`` ; une panne de flux donne un résultat ``FAILED`` (jamais d'exception)."""
        from pokeshop.importers.runner import failed_result

        now = kwargs.setdefault("now", self.clock())
        try:
            snapshot = self.fetch()
        except Exception as exc:  # noqa: BLE001 - toute panne de flux devient un incident
            return failed_result(self.mapping, QuarantineReason.FETCH_FAILED, f"{type(exc).__name__}: {exc}", now=now)
        return self.parse(snapshot, **kwargs)


class FileConnector(SupplierConnector):
    """Fichier local fourni par le fournisseur (priorité 2 du BP §6)."""

    def __init__(
        self,
        path: str | Path,
        mapping: SupplierMapping,
        *,
        clock: Callable[[], datetime] | None = None,
        source_ts: datetime | None = None,
    ) -> None:
        super().__init__(mapping, clock=clock)
        self.path = Path(path)
        self.source_ts = source_ts

    def fetch(self) -> RawSnapshot:
        """Lit le fichier (le contenu n'est jamais modifié)."""
        try:
            content = self.path.read_bytes()
        except OSError as exc:
            raise FetchError(f"fichier indisponible : {self.path} ({exc.strerror or exc})") from exc
        return RawSnapshot.capture(
            supplier_id=self.supplier_id,
            content=content,
            source_kind=SourceKind(self.mapping.file_format.value.upper()),
            source_uri=str(self.path),
            fetched_at=self.clock(),
            source_ts=self.source_ts,
            fictif=self.mapping.fictif,
        )


class BytesConnector(SupplierConnector):
    """Contenu déjà en mémoire (pièce jointe, export reçu par l'orchestrateur, tests)."""

    def __init__(
        self,
        content: bytes,
        mapping: SupplierMapping,
        *,
        source_uri: str = "memory://",
        clock: Callable[[], datetime] | None = None,
        source_ts: datetime | None = None,
    ) -> None:
        super().__init__(mapping, clock=clock)
        self.content = content
        self.source_uri = source_uri
        self.source_ts = source_ts

    def fetch(self) -> RawSnapshot:
        """Capture du contenu en mémoire."""
        return RawSnapshot.capture(
            supplier_id=self.supplier_id,
            content=self.content,
            source_kind=SourceKind(self.mapping.file_format.value.upper()),
            source_uri=self.source_uri,
            fetched_at=self.clock(),
            source_ts=self.source_ts,
            fictif=self.mapping.fictif,
        )
