"""Validation commune aux formats : enregistrement brut -> offre normalisée ou quarantaine.

Contrôles (SPEC §2.5, BP §12 étape 2 « Valider devise, TVA, unité, langue et quantité ») :

* ligne : SKU, prix (lisible, > 0), devise (connue, autorisée, cohérente), base HT/TTC,
  base unité/carton et conditionnement, GTIN (checksum), langue, paliers, quantités,
  fraîcheur de la ligne, marquage FICTIF ;
* import : doublons de SKU, prix ×10 / ÷10, devise ou base HT/TTC changées depuis le
  dernier import, import incomplet (lignes < seuil), import vide, capture > 24 h.

Une donnée non critique inconnue (format, extension, contenu, scellé, TVA) n'est **pas**
mise en quarantaine : l'offre passe avec une anomalie et le catalogue/pricing la laissent
en brouillon (BP §5). Aucune donnée n'est devinée ; aucun stock local n'est touché.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from pydantic import ValidationError

from pokeshop.catalog import (
    NO_EXTENSION,
    ExtensionTable,
    Language,
    ProductFormat,
    booster_count,
    clean_gtin,
    is_accessory,
    is_case_level_gtin,
    normalize_content,
    normalize_format,
    normalize_gtin,
    normalize_language,
)
from pokeshop.catalog import fold as _fold
from pokeshop.importers.base import (
    Anomaly,
    AnomalyCode,
    ImportBaseline,
    ImporterError,
    ImportPolicy,
    ImportResult,
    ImportStatus,
    QuarantinedRow,
    QuarantineReason,
    RawRecord,
    RawSnapshot,
    RecordBatch,
    Severity,
    SnapshotMeta,
    SourceKind,
)
from pokeshop.importers.mapping import SupplierMapping
from pokeshop.importers.values import (
    CellValue,
    UnitBasis,
    UnknownCurrencyError,
    ValueParseError,
    cell_text,
    mapped_value,
    normalize_currency,
    parse_availability,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_money,
    parse_quantity,
    parse_rate,
    parse_unit_basis,
    parse_vat_basis,
)
from pokeshop.models import AvailabilityStatus, SupplierOffer, TierDiscount
from pokeshop.pricing import is_price_anomaly
from pokeshop.stock import is_stale

__all__ = ["header_key", "resolve_columns", "build_import_result", "failed_result"]

_MAX_LIST = 20


def header_key(name: str) -> str:
    """Clé de comparaison d'un nom de colonne (casse, accents, ponctuation ; ``@`` conservé)."""
    return _fold(name.replace("@", " attr "))


def resolve_columns(header: Sequence[str], names: Iterable[str]) -> tuple[str | None, list[str]]:
    """Colonne du fichier correspondant à l'un des ``names`` ; erreurs si plusieurs colonnes distinctes."""
    wanted = {header_key(n) for n in names}
    matches = [h for h in header if header_key(h) in wanted]
    if len(matches) > 1:
        return None, [f"colonnes ambiguës {matches}"]
    return (matches[0] if matches else None), []


@dataclass
class _Columns:
    fields: dict[str, str]
    tiers: list[tuple[int, dict[str, str | None]]]
    errors: list[str]
    unmapped: list[str]
    warnings: list[str]


def _resolve_all(batch: RecordBatch, mapping: SupplierMapping) -> _Columns:
    fields: dict[str, str] = {}
    errors: list[str] = []
    used: set[str] = set()
    for name, aliases in mapping.columns.items():
        col, errs = resolve_columns(batch.header, aliases)
        errors.extend(f"{name} : {e}" for e in errs)
        if col is not None:
            fields[name] = col
            used.add(col)
        elif name in mapping.required_fields and not errs:
            errors.append(f"{name} : aucune colonne parmi {list(aliases)}")
    tiers: list[tuple[int, dict[str, str | None]]] = []
    warnings: list[str] = []
    for i, spec in enumerate(mapping.tiers, start=1):
        resolved: dict[str, str | None] = {}
        missing = False
        for attr in ("min_qty_column", "price_column", "discount_pct_column"):
            name = getattr(spec, attr)
            if name is None:
                resolved[attr] = None
                continue
            col, errs = resolve_columns(batch.header, (name,))
            errors.extend(f"palier {i} : {e}" for e in errs)
            if col is None:
                missing = True
            else:
                used.add(col)
            resolved[attr] = col
        if missing:
            warnings.append(f"palier {i} : colonne absente du fichier, palier ignoré")
        else:
            tiers.append((i, resolved))
    unmapped = [h for h in batch.header if h not in used]
    return _Columns(fields=fields, tiers=tiers, errors=errors, unmapped=unmapped, warnings=warnings)


@dataclass
class _Row:
    record: RawRecord
    sku: str | None
    raw: dict[str, str | None]
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    offer: SupplierOffer | None = None
    row_ts: datetime | None = None

    def reject(self, reason: QuarantineReason, detail: str) -> None:
        if reason.value not in self.reasons:
            self.reasons.append(reason.value)
        self.details.append(detail)

    def warn(self, code: AnomalyCode, detail: str, severity: Severity = Severity.WARNING) -> None:
        self.anomalies.append(
            Anomaly(code=code.value, severity=severity, detail=detail, line_no=self.record.line_no, supplier_sku=self.sku)
        )


def _raw_text(value: CellValue) -> str | None:
    try:
        return cell_text(value)
    except ValueParseError:  # pragma: no cover - les lecteurs ne produisent jamais de float
        return repr(value)


class _RowBuilder:
    """Transforme un enregistrement en offre (ou motifs de quarantaine)."""

    def __init__(
        self,
        snapshot: RawSnapshot,
        mapping: SupplierMapping,
        columns: _Columns,
        table: ExtensionTable,
        policy: ImportPolicy,
        now: datetime,
        default_ts: datetime | None,
    ) -> None:
        self.snapshot = snapshot
        self.mapping = mapping
        self.columns = columns
        self.table = table
        self.policy = policy
        self.now = now
        self.default_ts = default_ts
        self.tz = mapping.dates.tz
        self.dec = mapping.numbers.decimal_separator
        self.thousands = mapping.numbers.thousands_separators
        self.maps = mapping.value_maps

    def _get(self, record: RawRecord, name: str) -> CellValue:
        col = self.columns.fields.get(name)
        return record.cells.get(col) if col is not None else None

    def _text(self, record: RawRecord, name: str) -> str | None:
        return _raw_text(self._get(record, name))

    def _qty(self, row: _Row, name: str, *, critical: bool) -> tuple[int | None, bool]:
        value = self._get(row.record, name)
        try:
            return parse_quantity(value, decimal_separator=self.dec)
        except ValueParseError as exc:
            if critical:
                row.reject(QuarantineReason.UNPARSEABLE_VALUE, f"{name} : {exc}")
            else:
                row.warn(AnomalyCode.UNPARSEABLE_OPTIONAL, f"{name} ignoré : {exc}")
            return None, False

    def build(self, record: RawRecord) -> _Row:
        raw = {k: _raw_text(v) for k, v in record.cells.items()}
        sku = self._text(record, "supplier_sku")
        row = _Row(record=record, sku=sku, raw=raw)
        if record.malformed:
            row.reject(QuarantineReason.MALFORMED_ROW, record.malformed)
        if sku is None:
            row.reject(QuarantineReason.MISSING_SKU, "SKU fournisseur vide")
        self._fictif(row)
        price, cell_currency = self._price(row)
        currency = self._currency(row, cell_currency)
        includes_vat = self._vat_basis(row)
        upp, carton, pack_size = self._packaging(row)
        gtin = self._gtin(row)
        fmt = self._format(row)
        language = self._language(row, fmt)
        extension = self._extension(row, fmt)
        content = self._content(row)
        sealed = self._sealed(row)
        vat_rate = self._vat_rate(row)
        moq = self._moq(row, pack_size, carton)
        availability = self._availability(row)
        available_qty = self._stock(row, pack_size)
        allocation_qty = self._allocation(row, pack_size)
        release_date = self._release_date(row)
        ship_from = self._country(row, "ship_from_country")
        vat_country = self._country(row, "vat_country")
        row_ts = self._row_ts(row)
        tiers = self._tiers(row, price, currency, pack_size)
        if row.reasons:
            return row
        assert sku is not None and price is not None
        incoterm = self._text(record, "incoterm") or self.mapping.defaults.incoterm
        pool = self._text(record, "stock_pool_id") or self.mapping.defaults.stock_pool_id
        try:
            row.offer = SupplierOffer(
                supplier_id=self.mapping.supplier_id,
                supplier_sku=sku,
                gtin=gtin,
                language=language,
                extension=extension,
                format=None if fmt is ProductFormat.UNKNOWN else fmt.value,
                content=content,
                sealed=sealed,
                units_per_pack=upp,
                price=price,
                currency=currency,
                price_includes_vat=includes_vat,
                vat_rate=vat_rate,
                tier_discounts=tiers,
                moq=moq,
                carton_qty=carton,
                availability_status=availability,
                available_qty=available_qty,
                allocation_qty=allocation_qty,
                release_date=release_date,
                incoterm=incoterm.upper() if incoterm else None,
                ship_from_country=ship_from,
                source_ts=row_ts,
                raw_ref=f"{self.snapshot.supplier_id}:{self.snapshot.checksum_sha256[:12]}#L{record.line_no}",
                vat_country=vat_country,
                stock_pool_id=pool,
            )
        except ValidationError as exc:
            row.reject(QuarantineReason.INVALID_ROW, "; ".join(e["msg"] for e in exc.errors()))
        return row

    # -- champs -------------------------------------------------------------

    def _fictif(self, row: _Row) -> None:
        if "fictif" not in self.columns.fields:
            return
        flag = parse_bool(self._get(row.record, "fictif"))
        if flag is True and not self.mapping.fictif:
            row.reject(QuarantineReason.FICTIF_FLAG_MISMATCH, "ligne marquée FICTIVE dans un flux réel")
        elif flag is False and self.mapping.fictif:
            row.reject(QuarantineReason.FICTIF_FLAG_MISMATCH, "ligne non fictive dans un jeu d'essai FICTIF")

    def _price(self, row: _Row) -> tuple[Decimal | None, str | None]:
        value = self._get(row.record, "price")
        if _raw_text(value) is None:
            row.reject(QuarantineReason.MISSING_PRICE, "prix vide")
            return None, None
        try:
            amount, currency = parse_money(
                value,
                decimal_separator=self.dec,
                thousands_separators=self.thousands,
                currency_aliases=self.maps.get("currency"),
            )
        except UnknownCurrencyError as exc:
            row.reject(QuarantineReason.UNKNOWN_CURRENCY, f"prix : {exc}")
            return None, None
        except ValueParseError as exc:
            row.reject(QuarantineReason.UNPARSEABLE_PRICE, str(exc))
            return None, None
        if amount is not None and amount <= 0:
            row.reject(QuarantineReason.NON_POSITIVE_PRICE, f"prix {amount}")
        return amount, currency

    def _currency(self, row: _Row, from_cell: str | None) -> str | None:
        column: str | None = None
        raw = self._get(row.record, "currency")
        try:
            column = normalize_currency(raw, self.maps.get("currency"))
        except UnknownCurrencyError as exc:
            row.reject(QuarantineReason.UNKNOWN_CURRENCY, str(exc))
            return None
        if column and from_cell and column != from_cell:
            row.reject(QuarantineReason.CURRENCY_CONFLICT, f"colonne {column} ≠ cellule prix {from_cell}")
            return None
        default = self.mapping.defaults.currency
        if column is None and from_cell and default and from_cell != default:
            row.reject(QuarantineReason.CURRENCY_CONFLICT, f"symbole {from_cell} ≠ devise du tarif {default}")
            return None
        currency = column or from_cell or default
        if currency is None:
            if QuarantineReason.UNKNOWN_CURRENCY.value not in row.reasons:
                row.reject(QuarantineReason.UNKNOWN_CURRENCY, "devise absente (ni colonne, ni symbole, ni défaut)")
            return None
        if currency not in self.mapping.allowed_currencies:
            row.reject(QuarantineReason.UNKNOWN_CURRENCY, f"devise {currency} non autorisée {list(self.mapping.allowed_currencies)}")
            return None
        return currency

    def _vat_basis(self, row: _Row) -> bool | None:
        raw = self._get(row.record, "price_basis")
        text = _raw_text(raw)
        if text is not None:
            basis = parse_vat_basis(raw, self.maps.get("price_basis"))
            if basis is None:
                row.reject(QuarantineReason.UNKNOWN_VAT_BASIS, f"base HT/TTC illisible : {text!r}")
            return basis
        default = self.mapping.defaults.price_basis
        if default is None:
            row.reject(QuarantineReason.UNKNOWN_VAT_BASIS, "base HT/TTC absente")
            return None
        return default == "TTC"

    def _packaging(self, row: _Row) -> tuple[int | None, int | None, int | None]:
        raw = self._get(row.record, "unit_basis")
        text = _raw_text(raw)
        basis: UnitBasis | None
        if text is not None:
            basis = parse_unit_basis(raw, self.maps.get("unit_basis"))
            if basis is None:
                row.reject(QuarantineReason.UNKNOWN_UNIT_BASIS, f"base unité/carton ambiguë : {text!r}")
        else:
            basis = self.mapping.defaults.unit_basis
            if basis is None:
                row.reject(QuarantineReason.UNKNOWN_UNIT_BASIS, "base unité/carton absente")
        upp, _ = self._qty(row, "units_per_pack", critical=True)
        if upp is None:
            upp = self.mapping.defaults.units_per_pack
        carton, _ = self._qty(row, "carton_qty", critical=True)
        if carton is not None and carton < 1:
            row.reject(QuarantineReason.INVALID_QUANTITY, "carton_qty < 1")
            carton = None
        if basis is UnitBasis.UNIT:
            if upp is not None and upp != 1 and "units_per_pack" in self.columns.fields:
                row.reject(QuarantineReason.UNIT_CONFLICT, f"prix à l'unité mais {upp} unités par colis")
            upp = 1
        elif basis is UnitBasis.PACK:
            if upp is None:
                upp = carton  # « unités par carton » : c'est ce que couvre un prix au carton
            if upp is None:
                row.reject(QuarantineReason.UNKNOWN_UNIT_BASIS, "prix au carton mais unités par carton inconnues")
            elif upp < 1:
                row.reject(QuarantineReason.INVALID_QUANTITY, "units_per_pack < 1")
                upp = None
            elif carton is None:
                carton = upp
        pack_size = carton or (upp if upp and upp > 1 else None)
        return upp, carton, pack_size

    def _to_units(self, row: _Row, qty: int | None, basis: UnitBasis, pack_size: int | None, name: str) -> int | None:
        if qty is None or basis is UnitBasis.UNIT:
            return qty
        if pack_size is None:
            row.reject(QuarantineReason.UNKNOWN_UNIT_BASIS, f"{name} en cartons mais taille de carton inconnue")
            return None
        return qty * pack_size

    def _gtin(self, row: _Row) -> str | None:
        raw = self._text(row.record, "gtin")
        if clean_gtin(raw) is None:
            row.warn(AnomalyCode.MISSING_GTIN, "GTIN absent : fiche en brouillon")
            return None
        gtin = normalize_gtin(raw)
        if gtin is None:
            row.reject(QuarantineReason.INVALID_GTIN, f"GTIN invalide : {raw!r}")
            return None
        if is_case_level_gtin(gtin):
            row.warn(AnomalyCode.CASE_LEVEL_GTIN, f"GTIN-14 de carton {gtin} : vérifier l'unité de vente")
        return gtin

    def _format(self, row: _Row) -> ProductFormat:
        raw = self._text(row.record, "format")
        fmt = ProductFormat.UNKNOWN
        if raw is not None:
            mapped = mapped_value(raw, self.maps.get("format", {}))
            fmt = normalize_format(mapped if mapped is not None else raw)
        if fmt is ProductFormat.UNKNOWN:
            designation = self._text(row.record, "designation")
            if designation is not None:
                fmt = normalize_format(designation)
        if fmt is ProductFormat.UNKNOWN:
            row.warn(AnomalyCode.UNKNOWN_FORMAT, f"format inconnu ou ambigu : {raw!r}")
        return fmt

    def _language(self, row: _Row, fmt: ProductFormat) -> str | None:
        if is_accessory(fmt):
            return Language.NA.value
        raw = self._text(row.record, "language")
        if raw is None:
            default = self.mapping.defaults.language
            lang = Language(default) if default else Language.UNKNOWN
        else:
            mapped = mapped_value(raw, self.maps.get("language", {}))
            lang = normalize_language(mapped if mapped is not None else raw)
        if lang in (Language.UNKNOWN, Language.NA):
            row.reject(QuarantineReason.UNKNOWN_LANGUAGE, f"langue inconnue ou non applicable : {raw!r}")
            return None
        return str(lang.value)

    def _extension(self, row: _Row, fmt: ProductFormat) -> str | None:
        raw = self._text(row.record, "extension")
        if raw is not None:
            mapped = mapped_value(raw, self.maps.get("extension", {}))
            if mapped is not None:
                raw = mapped
        if is_accessory(fmt) and (raw is None or _fold(raw) in ("", "n a", "na", "aucune", "sans", "sans extension")):
            return NO_EXTENSION
        candidates = [raw] if raw is not None else []
        designation = self._text(row.record, "designation")
        if raw is None and designation is not None:
            candidates.append(designation)
        for text in candidates:
            match = self.table.match(text)
            if match.code is not None:
                return match.code
            if match.ambiguous:
                row.warn(AnomalyCode.AMBIGUOUS_EXTENSION, f"plusieurs extensions citées : {text!r}")
                return None
        row.warn(AnomalyCode.UNKNOWN_EXTENSION, f"extension absente de la table d'alias : {raw!r}")
        return None

    def _content(self, row: _Row) -> str | None:
        content = normalize_content(self._text(row.record, "content"))
        if content is None:
            designation = self._text(row.record, "designation")
            if booster_count(designation) is not None:
                content = normalize_content(designation)
        if content is None:
            row.warn(AnomalyCode.MISSING_CONTENT, "contenu non annoncé : fiche en brouillon")
        return content

    def _sealed(self, row: _Row) -> bool | None:
        raw = self._get(row.record, "sealed")
        sealed = parse_bool(raw, self.maps.get("sealed"))
        if sealed is None and _raw_text(raw) is None:
            sealed = self.mapping.defaults.sealed
        if sealed is None:
            row.warn(AnomalyCode.UNKNOWN_SEALED, f"état scellé inconnu : {_raw_text(raw)!r}")
        elif sealed is False:
            row.warn(AnomalyCode.NOT_SEALED, "produit non scellé : hors périmètre de lancement")
        return sealed

    def _vat_rate(self, row: _Row) -> Decimal | None:
        raw = self._get(row.record, "vat_rate")
        try:
            rate = parse_rate(raw, decimal_separator=self.dec)
        except ValueParseError as exc:
            row.reject(QuarantineReason.UNPARSEABLE_VALUE, f"vat_rate : {exc}")
            return None
        if rate is None:
            rate = self.mapping.defaults.vat_rate
        if rate is None:
            row.warn(AnomalyCode.MISSING_VAT_RATE, "taux de TVA facturé inconnu : prix en brouillon")
        return rate

    def _moq(self, row: _Row, pack_size: int | None, carton: int | None) -> int | None:
        qty, _ = self._qty(row, "moq", critical=True)
        moq = self._to_units(row, qty, self.mapping.quantities.moq, pack_size, "moq")
        if moq is not None and moq < 1:
            row.reject(QuarantineReason.INVALID_QUANTITY, "MOQ < 1")
            return None
        if moq is not None and carton and moq % carton:
            row.warn(AnomalyCode.MOQ_NOT_CARTON_MULTIPLE, f"MOQ {moq} non multiple du carton {carton}")
        return moq

    def _availability(self, row: _Row) -> AvailabilityStatus:
        raw = self._get(row.record, "availability")
        status = parse_availability(raw, self.maps.get("availability"))
        if status is AvailabilityStatus.UNKNOWN and _raw_text(raw) is not None:
            row.warn(AnomalyCode.UNKNOWN_AVAILABILITY, f"disponibilité non reconnue : {_raw_text(raw)!r}", Severity.INFO)
        return status

    def _stock(self, row: _Row, pack_size: int | None) -> int | None:
        qty, approx = self._qty(row, "available_qty", critical=False)
        if approx:
            row.warn(AnomalyCode.APPROXIMATE_STOCK, f"stock approximatif : borne basse {qty}", Severity.INFO)
        if qty is None or self.mapping.quantities.stock is UnitBasis.UNIT:
            return qty
        if pack_size is None:
            row.warn(AnomalyCode.UNPARSEABLE_OPTIONAL, "stock en cartons, taille de carton inconnue : ignoré")
            return None
        return qty * pack_size

    def _allocation(self, row: _Row, pack_size: int | None) -> int | None:
        if _raw_text(self._get(row.record, "allocation_qty")) is None:
            return None
        if not self.mapping.allocation_is_firm:
            row.warn(
                AnomalyCode.ALLOCATION_NOT_FIRM,
                "allocation annoncée sans accord écrit : ignorée (aucune précommande possible)",
                Severity.INFO,
            )
            return None
        qty, _ = self._qty(row, "allocation_qty", critical=True)
        return self._to_units(row, qty, self.mapping.quantities.allocation, pack_size, "allocation_qty")

    def _release_date(self, row: _Row) -> date | None:
        raw = self._get(row.record, "release_date")
        try:
            return parse_date(raw, self.mapping.dates.formats)
        except ValueParseError as exc:
            row.warn(AnomalyCode.UNPARSEABLE_OPTIONAL, f"date de sortie ignorée : {exc}")
            return None

    def _country(self, row: _Row, name: str) -> str | None:
        default: str | None = getattr(self.mapping.defaults, name)
        text = self._text(row.record, name)
        if text is None:
            return default
        code = text.strip().upper()
        if len(code) != 2 or not code.isalpha() or not code.isascii():
            row.warn(AnomalyCode.INVALID_COUNTRY, f"{name} invalide : {text!r} (ignoré)")
            return default
        return code

    def _row_ts(self, row: _Row) -> datetime:
        raw = self._get(row.record, "source_ts")
        ts: datetime | None = None
        if _raw_text(raw) is not None:
            try:
                ts = parse_datetime(raw, self.tz, self.mapping.dates.formats)
            except ValueParseError as exc:
                row.reject(QuarantineReason.UNPARSEABLE_VALUE, f"horodatage : {exc}")
        if ts is not None:
            row.row_ts = ts
            if is_stale(ts, self.now, self.policy.max_age, future_skew=self.policy.future_skew):
                row.reject(QuarantineReason.STALE_SOURCE, f"donnée du {ts.isoformat()} (> {self.policy.max_age} ou future)")
            return ts
        return self.default_ts or self.snapshot.fetched_at

    def _tiers(self, row: _Row, price: Decimal | None, currency: str | None, pack_size: int | None) -> tuple[TierDiscount, ...]:
        tiers: list[TierDiscount] = []
        for index, cols in self.columns.tiers:
            spec = self.mapping.tiers[index - 1]
            qty_value: CellValue = spec.min_qty if spec.min_qty is not None else row.record.cells.get(cols["min_qty_column"] or "")
            value_col = cols["price_column"] or cols["discount_pct_column"]
            value = row.record.cells.get(value_col or "")
            if _raw_text(qty_value) is None and _raw_text(value) is None:
                continue
            if (spec.min_qty_column is not None and _raw_text(qty_value) is None) or _raw_text(value) is None:
                row.reject(QuarantineReason.INVALID_TIER, f"palier {index} incomplet")
                continue
            try:
                qty, _ = parse_quantity(qty_value, decimal_separator=self.dec)
                assert qty is not None
                if self.mapping.quantities.tiers is UnitBasis.PACK:
                    if pack_size is None:
                        raise ValueParseError("quantité de palier en cartons, carton inconnu")
                    qty *= pack_size
                if spec.price_column is not None:
                    amount, tier_currency = parse_money(
                        value, decimal_separator=self.dec, thousands_separators=self.thousands,
                        currency_aliases=self.maps.get("currency"),
                    )
                    if tier_currency and currency and tier_currency != currency:
                        raise ValueParseError(f"devise du palier {tier_currency} ≠ {currency}")
                    tiers.append(TierDiscount(min_qty=qty, price=amount))
                else:
                    tiers.append(TierDiscount(min_qty=qty, discount_pct=parse_rate(value, decimal_separator=self.dec)))
            except (ValueParseError, ValidationError, AssertionError) as exc:
                row.reject(QuarantineReason.INVALID_TIER, f"palier {index} : {exc}")
        return self._check_tiers(row, tiers, price)

    @staticmethod
    def _check_tiers(row: _Row, tiers: list[TierDiscount], price: Decimal | None) -> tuple[TierDiscount, ...]:
        ordered = sorted(tiers, key=lambda t: t.min_qty)
        mins = [t.min_qty for t in ordered]
        if len(set(mins)) != len(mins):
            row.reject(QuarantineReason.INVALID_TIER, f"paliers en double : {mins}")
            return ()
        last_price: Decimal | None = price
        last_pct = Decimal(0)
        for tier in ordered:
            if tier.price is not None:
                if tier.price <= 0:
                    row.reject(QuarantineReason.INVALID_TIER, f"prix de palier {tier.price} ≤ 0")
                elif last_price is not None and tier.price > last_price:
                    row.reject(QuarantineReason.INVALID_TIER, f"palier {tier.min_qty} : prix {tier.price} > prix précédent {last_price}")
                last_price = tier.price
            elif tier.discount_pct is not None:
                if tier.discount_pct < last_pct:
                    row.reject(QuarantineReason.INVALID_TIER, f"palier {tier.min_qty} : remise décroissante")
                last_pct = tier.discount_pct
        return tuple(ordered)


def _snapshot_ts(batch: RecordBatch, snapshot: RawSnapshot, mapping: SupplierMapping, anomalies: list[Anomaly]) -> datetime | None:
    if batch.source_ts_raw is not None:
        try:
            ts = parse_datetime(batch.source_ts_raw, mapping.dates.tz, mapping.dates.formats)
        except ValueParseError as exc:
            anomalies.append(
                Anomaly(code=QuarantineReason.UNPARSEABLE_VALUE.value, severity=Severity.CRITICAL, detail=f"horodatage d'export : {exc}")
            )
            ts = None
        if ts is not None:
            return ts
    return snapshot.source_ts


def failed_result(
    mapping: SupplierMapping,
    reason: QuarantineReason,
    detail: str,
    *,
    now: datetime,
    snapshot: RawSnapshot | SnapshotMeta | None = None,
    dry_run: bool = True,
) -> ImportResult:
    """Résultat ``FAILED`` : aucune offre, offres précédentes conservées, stock local intact."""
    if snapshot is None:
        meta = SnapshotMeta(
            supplier_id=mapping.supplier_id,
            source_kind=SourceKind(mapping.file_format.value.upper()),
            source_uri="(indisponible)",
            fetched_at=now,
            checksum_sha256="0" * 64,
            byte_size=0,
            fictif=mapping.fictif,
        )
    else:
        meta = snapshot.meta() if isinstance(snapshot, RawSnapshot) else snapshot
    return ImportResult(
        supplier_id=mapping.supplier_id,
        mapping_version=mapping.mapping_version,
        snapshot=meta,
        status=ImportStatus.FAILED,
        anomalies=(Anomaly(code=reason.value, severity=Severity.CRITICAL, detail=detail),),
        evaluated_at=now,
        dry_run=dry_run,
        fictif=mapping.fictif,
    )


def _dedupe(rows: list[_Row], anomalies: list[Anomaly]) -> list[_Row]:
    by_sku: dict[str, list[_Row]] = {}
    for row in rows:
        if row.sku is not None:
            by_sku.setdefault(row.sku, []).append(row)
    dropped: set[int] = set()
    for sku, group in by_sku.items():
        if len(group) < 2:
            continue
        first = group[0]
        if all(r.raw == first.raw for r in group[1:]):
            for dup in group[1:]:
                dropped.add(id(dup))
                anomalies.append(
                    Anomaly(
                        code=AnomalyCode.DUPLICATE_IDENTICAL_ROW.value,
                        severity=Severity.INFO,
                        detail=f"ligne identique à la ligne {first.record.line_no} : ignorée",
                        line_no=dup.record.line_no,
                        supplier_sku=sku,
                    )
                )
            continue
        lines = [r.record.line_no for r in group]
        for dup in group:
            dup.offer = None
            dup.reject(QuarantineReason.DUPLICATE_SKU, f"SKU {sku} présent lignes {lines} avec des valeurs différentes")
    return [r for r in rows if id(r) not in dropped]


def _compare_baseline(
    rows: list[_Row], baseline: ImportBaseline, policy: ImportPolicy, anomalies: list[Anomaly]
) -> None:
    for row in rows:
        offer = row.offer
        if offer is None or offer.price is None:
            continue
        ref = baseline.prices.get(offer.supplier_sku)
        if ref is None:
            continue
        if offer.currency != ref.currency:
            row.offer = None
            row.reject(QuarantineReason.CURRENCY_CHANGED, f"devise {ref.currency} -> {offer.currency}")
            continue
        if offer.price_includes_vat != ref.price_includes_vat:
            row.offer = None
            before, after = ("TTC" if ref.price_includes_vat else "HT"), ("TTC" if offer.price_includes_vat else "HT")
            row.reject(QuarantineReason.VAT_BASIS_CHANGED, f"base {before} -> {after}")
            continue
        unit = offer.price / (offer.units_per_pack or 1)
        ratio = unit / ref.unit_price
        if is_price_anomaly(unit, ref.unit_price, policy.price_anomaly_factor):
            row.offer = None
            row.reject(
                QuarantineReason.PRICE_ANOMALY,
                f"prix unitaire ×{ratio.quantize(Decimal('0.01'))} vs dernier import (seuil ×{policy.price_anomaly_factor})",
            )
        elif ratio >= policy.price_warning_ratio or ratio <= 1 / policy.price_warning_ratio:
            row.warn(AnomalyCode.PRICE_CHANGE_LARGE, f"prix unitaire ×{ratio.quantize(Decimal('0.01'))} vs dernier import")
    present = {r.sku for r in rows if r.sku is not None}
    missing = sorted(set(baseline.prices) - present)
    if missing:
        shown = ", ".join(missing[:_MAX_LIST]) + (" …" if len(missing) > _MAX_LIST else "")
        anomalies.append(
            Anomaly(
                code=AnomalyCode.MISSING_SINCE_PREVIOUS.value,
                severity=Severity.INFO,
                detail=f"{len(missing)} référence(s) disparue(s) : {shown} (offres précédentes conservées, elles vieillissent)",
            )
        )
    new = sorted(r.sku for r in rows if r.offer is not None and r.sku is not None and r.sku not in baseline.prices)
    if new:
        shown = ", ".join(new[:_MAX_LIST]) + (" …" if len(new) > _MAX_LIST else "")
        anomalies.append(
            Anomaly(code=AnomalyCode.NEW_SINCE_PREVIOUS.value, severity=Severity.INFO, detail=f"{len(new)} nouvelle(s) : {shown}")
        )


def build_import_result(
    snapshot: RawSnapshot,
    batch: RecordBatch,
    mapping: SupplierMapping,
    *,
    now: datetime,
    table: ExtensionTable,
    policy: ImportPolicy | None = None,
    baseline: ImportBaseline | None = None,
    dry_run: bool = True,
) -> ImportResult:
    """Applique toutes les validations et construit le :class:`ImportResult`."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ImporterError("now doit porter un fuseau horaire")
    if snapshot.supplier_id != mapping.supplier_id:
        raise ImporterError(f"capture {snapshot.supplier_id} ≠ dictionnaire {mapping.supplier_id}")
    if baseline is not None and baseline.supplier_id != mapping.supplier_id:
        raise ImporterError("référence d'un autre fournisseur")
    pol = policy or ImportPolicy()
    anomalies: list[Anomaly] = []
    if mapping.is_template:
        anomalies.append(
            Anomaly(
                code=AnomalyCode.MAPPING_TEMPLATE.value,
                severity=Severity.WARNING,
                detail="dictionnaire TEMPLATE : aucun format confirmé, résultat indicatif",
            )
        )
    columns = _resolve_all(batch, mapping)
    if columns.errors:
        return failed_result(mapping, QuarantineReason.MAPPING_MISMATCH, " ; ".join(columns.errors), now=now, snapshot=snapshot, dry_run=dry_run)
    for warning in columns.warnings:
        anomalies.append(Anomaly(code=QuarantineReason.MAPPING_MISMATCH.value, severity=Severity.WARNING, detail=warning))
    if columns.unmapped:
        anomalies.append(
            Anomaly(code=AnomalyCode.UNMAPPED_COLUMNS.value, severity=Severity.INFO, detail="colonnes non reliées : " + ", ".join(columns.unmapped))
        )
    if "currency" not in columns.fields and mapping.defaults.currency is None:
        anomalies.append(
            Anomaly(
                code=AnomalyCode.CURRENCY_NOT_CONFIGURED.value,
                severity=Severity.CRITICAL,
                detail="ni colonne devise ni devise par défaut : seules les cellules avec symbole passent",
            )
        )
    if batch.blank_rows:
        anomalies.append(Anomaly(code=AnomalyCode.BLANK_ROWS.value, severity=Severity.INFO, detail=f"{batch.blank_rows} ligne(s) vide(s) ignorée(s)"))
    declared_ts = _snapshot_ts(batch, snapshot, mapping, anomalies)
    builder = _RowBuilder(snapshot, mapping, columns, table, pol, now, declared_ts)
    rows = [builder.build(record) for record in batch.records]
    rows_read = len(rows)
    rows = _dedupe(rows, anomalies)
    if baseline is not None:
        _compare_baseline(rows, baseline, pol, anomalies)
        if baseline.checksum_sha256 == snapshot.checksum_sha256:
            anomalies.append(
                Anomaly(
                    code=AnomalyCode.SAME_CONTENT_AS_PREVIOUS.value,
                    severity=Severity.WARNING,
                    detail="contenu identique à l'import précédent : la source n'a peut-être pas été mise à jour",
                )
            )
    effective_ts = declared_ts
    if effective_ts is None:
        row_times = [r.row_ts for r in rows if r.row_ts is not None]
        plausible = [ts for ts in row_times if ts <= now + pol.future_skew]  # une ligne « future » ne date pas l'import
        effective_ts = max(plausible or row_times) if row_times else None
    if effective_ts is None:
        effective_ts = snapshot.fetched_at
        anomalies.append(
            Anomaly(
                code=AnomalyCode.SOURCE_TS_ASSUMED.value,
                severity=Severity.WARNING,
                detail="aucun horodatage dans la source : heure de capture retenue",
            )
        )
    snapshot_reasons: list[tuple[QuarantineReason, str]] = []
    if rows_read == 0:
        snapshot_reasons.append((QuarantineReason.EMPTY_IMPORT, "aucune ligne de données"))
    if is_stale(effective_ts, now, pol.max_age, future_skew=pol.future_skew):
        snapshot_reasons.append((QuarantineReason.STALE_SNAPSHOT, f"source datée du {effective_ts.isoformat()}"))
    if baseline is not None and baseline.rows_read > 0 and Decimal(rows_read) < Decimal(baseline.rows_read) * pol.min_rows_ratio:
        snapshot_reasons.append(
            (
                QuarantineReason.INCOMPLETE_IMPORT,
                f"{rows_read} ligne(s) < {pol.min_rows_ratio * 100:.0f} % des {baseline.rows_read} de l'import précédent",
            )
        )
    for row in rows:
        anomalies.extend(row.anomalies)
    if snapshot_reasons:
        for reason, detail in snapshot_reasons:
            anomalies.append(Anomaly(code=reason.value, severity=Severity.CRITICAL, detail=detail))
        for row in rows:
            row.offer = None
            for reason, detail in snapshot_reasons:
                row.reject(reason, detail)
        status = ImportStatus.QUARANTINED
    else:
        status = ImportStatus.PARTIAL if any(r.offer is None for r in rows) else ImportStatus.ACCEPTED
    quarantined = tuple(
        QuarantinedRow(
            line_no=r.record.line_no,
            supplier_sku=r.sku,
            reasons=tuple(r.reasons) or (QuarantineReason.INVALID_ROW.value,),
            details=tuple(r.details),
            raw=r.raw,
        )
        for r in rows
        if r.offer is None
    )
    offers = tuple(r.offer for r in rows if r.offer is not None)
    if rows_read and Decimal(len(quarantined)) / Decimal(rows_read) > pol.max_quarantine_ratio and status is not ImportStatus.QUARANTINED:
        anomalies.append(
            Anomaly(
                code=AnomalyCode.QUARANTINE_RATIO_EXCEEDED.value,
                severity=Severity.CRITICAL,
                detail=f"{len(quarantined)}/{rows_read} lignes en quarantaine (> {pol.max_quarantine_ratio * 100:.0f} %)",
            )
        )
    return ImportResult(
        supplier_id=mapping.supplier_id,
        mapping_version=mapping.mapping_version,
        snapshot=snapshot.meta(),
        status=status,
        offers=offers,
        quarantined=quarantined,
        anomalies=tuple(anomalies),
        rows_read=rows_read,
        effective_source_ts=effective_ts,
        evaluated_at=now,
        dry_run=dry_run,
        fictif=mapping.fictif,
    )
