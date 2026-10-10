"""Dictionnaire de champs par fournisseur (``data/supplier_mappings/<fournisseur>.yaml``).

Un dictionnaire décrit, pour UN fournisseur et UN format de fichier : les colonnes source
de chaque champ normalisé, la devise, la base HT/TTC, le séparateur décimal, la base
unité/carton des prix et des quantités, les paliers de remise et les valeurs par défaut
**confirmées par écrit**. Statuts :

* ``TEMPLATE`` : aucun format confirmé (fournisseur sans fichier réel) — simulation seulement ;
* ``FICTIF`` : jeux d'essai ``data/samples/`` — simulation seulement ;
* ``VALIDE`` : vérifié sur un fichier réel (``validated_on_sample_sha256``) par une personne.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from pokeshop.catalog import Language
from pokeshop.errors import PokeshopError
from pokeshop.importers.values import DEFAULT_DATE_FORMATS, DEFAULT_THOUSANDS_SEPARATORS, UnitBasis
from pokeshop.models import FrozenModel

__all__ = [
    "MappingError",
    "FileFormat",
    "MappingStatus",
    "FIELD_NAMES",
    "VALUE_MAP_FIELDS",
    "MAPPINGS_ENV_VAR",
    "DEFAULT_MAPPINGS_DIR",
    "REPO_ROOT",
    "CsvOptions",
    "XlsxOptions",
    "XmlOptions",
    "NumberOptions",
    "DateOptions",
    "TierSpec",
    "MappingDefaults",
    "QuantityUnits",
    "SupplierMapping",
    "load_mapping",
    "list_mappings",
]

REPO_ROOT = Path(__file__).resolve().parents[3]
MAPPINGS_ENV_VAR = "POKESHOP_MAPPINGS_DIR"
DEFAULT_MAPPINGS_DIR = REPO_ROOT / "data" / "supplier_mappings"


class MappingError(PokeshopError, ValueError):
    """Dictionnaire de champs absent, invalide ou incompatible avec le fichier."""


class FileFormat(str, Enum):
    """Format du flux fournisseur."""

    CSV = "csv"
    XLSX = "xlsx"
    XML = "xml"


class MappingStatus(str, Enum):
    """Statut du dictionnaire de champs."""

    TEMPLATE = "TEMPLATE"
    FICTIF = "FICTIF"
    VALIDE = "VALIDE"


FIELD_NAMES: tuple[str, ...] = (
    "supplier_sku",
    "gtin",
    "designation",
    "language",
    "extension",
    "format",
    "content",
    "sealed",
    "price",
    "currency",
    "price_basis",
    "vat_rate",
    "unit_basis",
    "units_per_pack",
    "carton_qty",
    "moq",
    "availability",
    "available_qty",
    "allocation_qty",
    "release_date",
    "incoterm",
    "ship_from_country",
    "vat_country",
    "stock_pool_id",
    "source_ts",
    "fictif",
)
"""Champs normalisés qu'un dictionnaire peut relier à une colonne source."""

VALUE_MAP_FIELDS = frozenset({"language", "format", "extension", "availability", "price_basis", "unit_basis", "sealed", "currency"})

_SUPPLIER_ID_RE = re.compile(r"^[a-z0-9_]{2,64}$")
_CELL_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class CsvOptions(FrozenModel):
    """Options de lecture CSV."""

    delimiter: str = Field(default=";", min_length=1, max_length=1)
    quotechar: str = Field(default='"', min_length=1, max_length=1)
    encoding: str = "utf-8-sig"
    skip_rows: int = Field(default=0, ge=0, le=50)
    """Lignes à ignorer avant l'en-tête (titre, commentaire)."""

    @field_validator("encoding")
    @classmethod
    def _encoding(cls, v: str) -> str:
        import codecs

        try:
            codecs.lookup(v)
        except LookupError as exc:
            raise ValueError(f"encodage inconnu : {v}") from exc
        return v


class XlsxOptions(FrozenModel):
    """Options de lecture Excel."""

    sheet: str | None = None
    """Nom de la feuille (première feuille si absent)."""
    header_row: int = Field(default=1, ge=1, le=100)
    source_ts_cell: str | None = None
    """Cellule portant l'horodatage d'export (ex. ``"B2"``)."""

    @field_validator("source_ts_cell")
    @classmethod
    def _cell(cls, v: str | None) -> str | None:
        if v is not None and not _CELL_RE.match(v):
            raise ValueError(f"référence de cellule invalide : {v!r}")
        return v


class XmlOptions(FrozenModel):
    """Options de lecture XML (chemins ElementTree, sans DTD)."""

    record_path: str = Field(default=".//offre", min_length=1)
    source_ts_attribute: str | None = None
    """Attribut de la racine portant l'horodatage d'export."""
    namespaces: dict[str, str] = Field(default_factory=dict)


class NumberOptions(FrozenModel):
    """Écriture des nombres dans le fichier."""

    decimal_separator: Literal[".", ","] = "."
    thousands_separators: tuple[str, ...] = DEFAULT_THOUSANDS_SEPARATORS

    @model_validator(mode="after")
    def _check(self) -> NumberOptions:
        if self.decimal_separator in self.thousands_separators:
            raise ValueError("le séparateur décimal ne peut pas être un séparateur de milliers")
        return self


class DateOptions(FrozenModel):
    """Formats de date et fuseau des horodatages sans fuseau."""

    formats: tuple[str, ...] = DEFAULT_DATE_FORMATS
    timezone: str = "Europe/Zurich"

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau inconnu : {v}") from exc
        return v

    @property
    def tz(self) -> ZoneInfo:
        """Fuseau ``ZoneInfo``."""
        return ZoneInfo(self.timezone)


class TierSpec(FrozenModel):
    """Palier de remise : quantité fixe ou colonne, prix du palier ou % de remise en colonne."""

    min_qty: int | None = Field(default=None, ge=1)
    min_qty_column: str | None = None
    price_column: str | None = None
    discount_pct_column: str | None = None

    @model_validator(mode="after")
    def _check(self) -> TierSpec:
        if (self.min_qty is None) == (self.min_qty_column is None):
            raise ValueError("palier : renseigner min_qty OU min_qty_column")
        if (self.price_column is None) == (self.discount_pct_column is None):
            raise ValueError("palier : renseigner price_column OU discount_pct_column")
        return self


class MappingDefaults(FrozenModel):
    """Valeurs appliquées quand la colonne est absente ou vide — **confirmées par écrit** seulement."""

    currency: str | None = None
    price_basis: Literal["HT", "TTC"] | None = None
    unit_basis: UnitBasis | None = None
    units_per_pack: int | None = Field(default=None, ge=1)
    vat_rate: Decimal | None = None
    sealed: bool | None = None
    language: str | None = None
    ship_from_country: str | None = None
    vat_country: str | None = None
    stock_pool_id: str | None = None
    incoterm: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[A-Z]{3}$", v):
            raise ValueError(f"devise ISO attendue : {v!r}")
        return v

    @field_validator("ship_from_country", "vat_country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[A-Z]{2}$", v):
            raise ValueError(f"code pays ISO à 2 lettres attendu : {v!r}")
        return v

    @field_validator("vat_rate")
    @classmethod
    def _vat(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not Decimal(0) <= v < 1:
            raise ValueError("vat_rate en fraction dans [0, 1[")
        return v

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {lang.value for lang in Language} - {Language.UNKNOWN.value}
        if v not in allowed:
            raise ValueError(f"langue par défaut invalide : {v!r}")
        return v


class QuantityUnits(FrozenModel):
    """Base (unité de vente ou carton) des quantités du fichier."""

    stock: UnitBasis = UnitBasis.UNIT
    moq: UnitBasis = UnitBasis.UNIT
    tiers: UnitBasis = UnitBasis.UNIT
    allocation: UnitBasis = UnitBasis.UNIT


def _as_tuple(value: Any) -> Any:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(value)
    return value


class SupplierMapping(FrozenModel):
    """Dictionnaire de champs d'un fournisseur (voir docstring du module)."""

    supplier_id: str
    supplier_name: str = ""
    mapping_version: str = Field(min_length=1)
    status: MappingStatus
    fictif: bool = False
    description: str = ""
    notes: tuple[str, ...] = ()
    """Points à confirmer avec le fournisseur (texte libre, non interprété)."""
    file_format: FileFormat
    csv: CsvOptions = CsvOptions()
    xlsx: XlsxOptions = XlsxOptions()
    xml: XmlOptions = XmlOptions()
    numbers: NumberOptions = NumberOptions()
    dates: DateOptions = DateOptions()
    columns: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    defaults: MappingDefaults = MappingDefaults()
    quantities: QuantityUnits = QuantityUnits()
    tiers: tuple[TierSpec, ...] = ()
    value_maps: dict[str, dict[str, str]] = Field(default_factory=dict)
    allowed_currencies: tuple[str, ...] = ("CHF", "EUR")
    allocation_is_firm: bool = False
    allocation_evidence: str | None = None
    required_fields: tuple[str, ...] = ("supplier_sku", "price")
    extension_tables: tuple[str, ...] = ()
    """Tables d'alias supplémentaires (chemins relatifs à la racine du dépôt) — FICTIF seulement."""
    validated_by: str | None = None
    validated_at: date | None = None
    validated_on_sample_sha256: str | None = None
    source_path: str | None = None
    content_sha256: str | None = None

    @field_validator("columns", mode="before")
    @classmethod
    def _columns(cls, v: Any) -> Any:
        if isinstance(v, Mapping):
            return {k: _as_tuple(val) for k, val in v.items()}
        return v

    @field_validator("supplier_id")
    @classmethod
    def _sid(cls, v: str) -> str:
        if not _SUPPLIER_ID_RE.match(v):
            raise ValueError(f"supplier_id en minuscules, chiffres et _ : {v!r}")
        return v

    @model_validator(mode="after")
    def _check(self) -> SupplierMapping:
        errors: list[str] = []
        unknown = set(self.columns) - set(FIELD_NAMES)
        if unknown:
            errors.append(f"champs inconnus dans columns : {sorted(unknown)}")
        for name, aliases in self.columns.items():
            if not aliases or any(not a.strip() for a in aliases):
                errors.append(f"columns.{name} : au moins un nom de colonne non vide")
        bad_maps = set(self.value_maps) - VALUE_MAP_FIELDS
        if bad_maps:
            errors.append(f"value_maps non gérés : {sorted(bad_maps)}")
        missing_required = {"supplier_sku", "price"} - set(self.required_fields)
        if missing_required:
            errors.append(f"required_fields doit contenir {sorted(missing_required)}")
        if set(self.required_fields) - set(FIELD_NAMES):
            errors.append("required_fields contient un champ inconnu")
        for name in self.required_fields:
            if name not in self.columns:
                errors.append(f"champ obligatoire {name} sans colonne dans columns")
        for code in self.allowed_currencies:
            if not re.match(r"^[A-Z]{3}$", code):
                errors.append(f"allowed_currencies : code ISO invalide {code!r}")
        if self.defaults.currency and self.defaults.currency not in self.allowed_currencies:
            errors.append("defaults.currency hors allowed_currencies")
        is_fictif_id = self.supplier_id.startswith("fictif_")
        if self.fictif != is_fictif_id:
            errors.append("fictif=true exige un supplier_id 'fictif_…' (et réciproquement)")
        if self.fictif != (self.status is MappingStatus.FICTIF):
            errors.append("status FICTIF ⇔ fictif=true")
        if self.status is MappingStatus.VALIDE:
            if not (self.validated_by and self.validated_at and self.validated_on_sample_sha256):
                errors.append("status VALIDE exige validated_by, validated_at et validated_on_sample_sha256")
            elif not _SHA_RE.match(self.validated_on_sample_sha256):
                errors.append("validated_on_sample_sha256 : sha256 hexadécimal attendu")
        if self.allocation_is_firm and not self.allocation_evidence:
            errors.append("allocation_is_firm exige allocation_evidence (accord écrit)")
        if self.extension_tables and not self.fictif:
            errors.append("extension_tables réservé aux dictionnaires FICTIF (production : table réelle)")
        if errors:
            raise ValueError(" ; ".join(errors))
        return self

    @property
    def is_template(self) -> bool:
        """Vrai si aucun format n'est confirmé."""
        return self.status is MappingStatus.TEMPLATE

    @property
    def simulation_only(self) -> bool:
        """Vrai si le dictionnaire ne peut servir qu'en simulation (TEMPLATE ou FICTIF)."""
        return self.status is not MappingStatus.VALIDE

    def columns_for(self, field: str) -> tuple[str, ...]:
        """Noms de colonne acceptés pour un champ (vide si non relié)."""
        if field not in FIELD_NAMES:
            raise MappingError(f"champ inconnu : {field}")
        return self.columns.get(field, ())

    def extension_table_paths(self) -> tuple[Path, ...]:
        """Chemins absolus des tables d'alias supplémentaires."""
        return tuple((REPO_ROOT / p).resolve() for p in self.extension_tables)


def _mappings_dir(mappings_dir: str | Path | None) -> Path:
    if mappings_dir is not None:
        return Path(mappings_dir)
    env = os.environ.get(MAPPINGS_ENV_VAR)
    return Path(env) if env else DEFAULT_MAPPINGS_DIR


def _format_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "document"
        parts.append(f"{loc} : {err['msg']}")
    return " ; ".join(parts)


def load_mapping(ref: str | Path, *, mappings_dir: str | Path | None = None) -> SupplierMapping:
    """Charge un dictionnaire par chemin ou par identifiant fournisseur (``asmodee_fr``).

    Le nom du fichier doit être ``<supplier_id>.yaml``. Erreurs -> :class:`MappingError`.
    """
    path = Path(ref)
    if not (path.suffix in (".yaml", ".yml") and path.exists()):
        if isinstance(ref, str) and _SUPPLIER_ID_RE.match(ref):
            path = _mappings_dir(mappings_dir) / f"{ref}.yaml"
        if not path.exists():
            raise MappingError(f"dictionnaire de champs introuvable : {ref}")
    try:
        raw = path.read_bytes()
        data = yaml.safe_load(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise MappingError(f"{path} : lecture impossible ({exc})") from exc
    if not isinstance(data, Mapping):
        raise MappingError(f"{path} : document YAML (objet) attendu")
    payload = {**data, "source_path": str(path), "content_sha256": hashlib.sha256(raw).hexdigest()}
    try:
        mapping = SupplierMapping.model_validate(payload)
    except ValidationError as exc:
        raise MappingError(f"{path} : {_format_validation(exc)}") from exc
    if mapping.supplier_id != path.stem:
        raise MappingError(f"{path} : supplier_id {mapping.supplier_id!r} ≠ nom de fichier {path.stem!r}")
    for extra in mapping.extension_table_paths():
        if not extra.exists():
            raise MappingError(f"{path} : table d'extensions introuvable {extra}")
    return mapping


def list_mappings(mappings_dir: str | Path | None = None) -> dict[str, SupplierMapping]:
    """Tous les dictionnaires ``*.yaml`` d'un dossier, par supplier_id."""
    folder = _mappings_dir(mappings_dir)
    return {p.stem: load_mapping(p) for p in sorted(folder.glob("*.yaml"))}
