"""Import ASSISTÉ d'un tarif reçu par email ou PDF (priorité 3 du BP §6).

Une personne (ou un outil d'extraction relu par une personne) recopie le tarif dans une
fiche structurée :class:`AssistedPriceList` (YAML, voir ``data/samples/FICTIF_tarif_email_assiste.yaml``).
Ce module **contrôle** — il ne décide rien :

* devise connue et autorisée, base HT/TTC explicite ;
* par ligne : SKU, quantité × prix unitaire = total de ligne (± 0,01), base unité/carton et
  conditionnement cohérents, GTIN valide, langue connue ;
* document : somme des lignes + port + frais = total déclaré (± 0,01).

La revue porte toujours le statut ``A_VALIDER_HUMAINEMENT``. Seule :func:`approve_review`,
appelée avec le nom de la personne qui valide et sans contrôle bloquant restant, produit
un :class:`ImportResult` exploitable. Aucune IA ne choisit une devise, une TVA ou un montant.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from pokeshop.catalog import (
    ExtensionTable,
    Language,
    ProductFormat,
    clean_gtin,
    is_accessory,
    load_extension_table,
    normalize_content,
    normalize_extension,
    normalize_format,
    normalize_gtin,
    normalize_language,
)
from pokeshop.importers.base import (
    Anomaly,
    AnomalyCode,
    ImporterError,
    ImportResult,
    ImportStatus,
    Severity,
    SnapshotMeta,
    SourceKind,
)
from pokeshop.importers.mapping import REPO_ROOT
from pokeshop.importers.values import (
    UnitBasis,
    ValueParseError,
    normalize_currency,
    parse_money,
    parse_quantity,
    parse_rate,
    parse_unit_basis,
    parse_vat_basis,
)
from pokeshop.models import FrozenModel, SupplierOffer
from pokeshop.stock import is_stale

__all__ = [
    "AssistedImportError",
    "AssistedLine",
    "AssistedPriceList",
    "AssistedCheck",
    "AssistedReview",
    "REVIEW_STATUS",
    "load_price_list",
    "review_price_list",
    "approve_review",
]

REVIEW_STATUS = "A_VALIDER_HUMAINEMENT"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class AssistedImportError(ImporterError):
    """Validation d'un import assisté refusée (contrôle bloquant ou validateur absent)."""


class AssistedLine(FrozenModel):
    """Ligne recopiée du tarif, **telle que lue** (textes bruts, aucune interprétation)."""

    line_no: int = Field(ge=1)
    supplier_sku: str | None = None
    designation: str | None = None
    gtin: str | None = None
    language: str | None = None
    extension: str | None = None
    format: str | None = None
    content: str | None = None
    sealed: bool | None = None
    quantity: str | None = None
    unit_basis: str | None = None
    units_per_pack: str | None = None
    unit_price: str | None = None
    line_total: str | None = None
    vat_rate: str | None = None


class AssistedPriceList(FrozenModel):
    """Fiche structurée d'un tarif email/PDF (l'original est archivé hors dépôt)."""

    supplier_id: str = Field(min_length=2)
    source_kind: Literal["EMAIL", "PDF"]
    source_ref: str = Field(min_length=1)
    """Message-ID de l'email ou nom du fichier PDF archivé."""
    document_sha256: str
    """Empreinte de l'original archivé (preuve de la source)."""
    received_at: datetime
    document_date: date | None = None
    currency: str | None = None
    price_basis: str | None = None
    vat_rate: str | None = None
    decimal_separator: Literal[".", ","] = "."
    declared_total: str | None = None
    declared_shipping: str | None = None
    declared_other_fees: str | None = None
    extracted_by: str = Field(min_length=1)
    ship_from_country: str | None = None
    allowed_currencies: tuple[str, ...] = ("CHF", "EUR")
    lines: tuple[AssistedLine, ...] = Field(min_length=1)
    fictif: bool = False
    extension_tables: tuple[str, ...] = ()
    """Tables d'alias supplémentaires (chemins relatifs au dépôt) — fiches FICTIVES uniquement."""

    @model_validator(mode="after")
    def _fictif_tables(self) -> AssistedPriceList:
        if self.extension_tables and not self.fictif:
            raise ValueError("extension_tables réservé aux fiches FICTIVES")
        return self

    @field_validator("document_sha256")
    @classmethod
    def _sha(cls, v: str) -> str:
        if not _SHA_RE.match(v):
            raise ValueError("document_sha256 : sha256 hexadécimal (64 caractères) attendu")
        return v

    @field_validator("ship_from_country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^[A-Z]{2}$", v):
            raise ValueError("ship_from_country : code pays ISO à 2 lettres majuscules")
        return v

    @field_validator("received_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("received_at doit porter un fuseau horaire")
        return v


class AssistedCheck(FrozenModel):
    """Résultat d'un contrôle (``blocking`` = empêche la validation)."""

    code: str
    ok: bool
    blocking: bool
    detail: str = ""
    line_no: int | None = None


class AssistedReview(FrozenModel):
    """Revue d'un tarif assisté : toujours à valider par une personne."""

    supplier_id: str
    source_ref: str
    snapshot: SnapshotMeta
    status: Literal["A_VALIDER_HUMAINEMENT"] = "A_VALIDER_HUMAINEMENT"
    requires_human_validation: Literal[True] = True
    checks: tuple[AssistedCheck, ...]
    draft_offers: tuple[SupplierOffer, ...]
    computed_total: Decimal | None
    declared_total: Decimal | None
    reviewed_at: datetime
    lines_count: int
    fictif: bool = False

    @property
    def blocking_checks(self) -> tuple[AssistedCheck, ...]:
        """Contrôles en échec qui empêchent la validation."""
        return tuple(c for c in self.checks if not c.ok and c.blocking)

    @property
    def warnings(self) -> tuple[AssistedCheck, ...]:
        """Contrôles en échec non bloquants (la fiche restera en brouillon côté catalogue)."""
        return tuple(c for c in self.checks if not c.ok and not c.blocking)

    @property
    def is_approvable(self) -> bool:
        """Vrai si une personne peut valider (aucun contrôle bloquant)."""
        return not self.blocking_checks

    def report_markdown(self) -> str:
        """Fiche de revue à transmettre à la personne qui valide (aucun coût interne calculé)."""
        lines = [
            f"# Tarif assisté — {self.supplier_id} — {self.source_ref} — {REVIEW_STATUS}",
            "",
            f"Revue du {self.reviewed_at:%Y-%m-%d %H:%M} · {self.lines_count} ligne(s) · "
            f"total recalculé {self.computed_total} / déclaré {self.declared_total}"
            + (" · **FICTIF**" if self.fictif else ""),
            "",
            "| Contrôle | Ligne | Résultat | Bloquant | Détail |",
            "|---|---|---|---|---|",
        ]
        for c in self.checks:
            if c.ok and c.line_no is not None:
                continue
            lines.append(
                f"| {c.code} | {c.line_no or '—'} | {'OK' if c.ok else 'ÉCHEC'} | {'oui' if c.blocking else 'non'} | "
                f"{c.detail.replace('|', '/')} |"
            )
        lines += [
            "",
            "## Validation humaine requise",
            "",
            "- [ ] Comparer chaque ligne à l'original (email/PDF) : SKU, quantité, unité, prix, total.",
            "- [ ] Corriger la fiche puis relancer la revue tant qu'un contrôle bloquant subsiste.",
            "- [ ] Valider nominativement (approve_review) : la validation est journalisée.",
        ]
        return "\n".join(lines) + "\n"


def load_price_list(path: str | Path) -> AssistedPriceList:
    """Charge une fiche de tarif assisté (YAML)."""
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AssistedImportError(f"{p} : lecture impossible ({exc})") from exc
    try:
        return AssistedPriceList.model_validate(data)
    except ValidationError as exc:
        raise AssistedImportError(f"{p} : fiche invalide ({exc})") from exc


class _Checks:
    def __init__(self) -> None:
        self.items: list[AssistedCheck] = []

    def add(self, code: str, ok: bool, *, blocking: bool = True, detail: str = "", line_no: int | None = None) -> bool:
        self.items.append(AssistedCheck(code=code, ok=ok, blocking=blocking, detail=detail, line_no=line_no))
        return ok


def _money(text: str | None, dec: str) -> tuple[Decimal | None, str | None]:
    return parse_money(text, decimal_separator=dec)


def review_price_list(
    doc: AssistedPriceList,
    *,
    now: datetime,
    table: ExtensionTable | None = None,
    tolerance: Decimal = Decimal("0.01"),
    max_age: timedelta = timedelta(hours=24),
) -> AssistedReview:
    """Contrôle une fiche de tarif assisté et prépare des offres **brouillon** (jamais publiées)."""
    if table is not None:
        tbl = table
    else:
        tbl = load_extension_table()
        extra = [REPO_ROOT / p for p in doc.extension_tables]
        if extra:
            tbl = tbl.merged(load_extension_table(extra))
    dec = doc.decimal_separator
    checks = _Checks()
    currency: str | None = None
    try:
        currency = normalize_currency(doc.currency)
    except ValueParseError as exc:
        checks.add("CURRENCY", False, detail=str(exc))
    else:
        if currency is None:
            checks.add("CURRENCY", False, detail="devise non indiquée sur le document")
        elif currency not in doc.allowed_currencies:
            checks.add("CURRENCY", False, detail=f"devise {currency} non autorisée")
            currency = None
        else:
            checks.add("CURRENCY", True, detail=currency)
    includes_vat = parse_vat_basis(doc.price_basis)
    checks.add("PRICE_BASIS", includes_vat is not None, detail=f"base lue : {doc.price_basis!r}")
    doc_vat: Decimal | None = None
    try:
        doc_vat = parse_rate(doc.vat_rate, decimal_separator=dec)
    except ValueParseError as exc:
        checks.add("VAT_RATE", False, detail=str(exc))
    stale = is_stale(doc.received_at, now, max_age)
    checks.add(
        "FRESHNESS", not stale, blocking=False,
        detail="tarif > 24 h : offres non éligibles au réassort ni aux promesses sans reconfirmation" if stale else "",
    )
    computed = Decimal(0)
    totals_ok = True
    offers: list[SupplierOffer] = []
    seen_skus: set[str] = set()
    for line in doc.lines:
        n = line.line_no
        line_ok = True
        sku = (line.supplier_sku or "").strip() or None
        line_ok &= checks.add("SKU", sku is not None, detail="SKU absent" if sku is None else "", line_no=n)
        if sku is not None:
            line_ok &= checks.add("DUPLICATE_SKU", sku not in seen_skus, detail=f"SKU {sku} en double", line_no=n)
            seen_skus.add(sku)
        qty: int | None = None
        unit_price: Decimal | None = None
        total: Decimal | None = None
        try:
            qty, _ = parse_quantity(line.quantity, decimal_separator=dec)
            line_ok &= checks.add("QUANTITY", qty is not None and qty > 0, detail=f"quantité lue {line.quantity!r}", line_no=n)
        except ValueParseError as exc:
            line_ok &= checks.add("QUANTITY", False, detail=str(exc), line_no=n)
        try:
            unit_price, token = _money(line.unit_price, dec)
            ok = unit_price is not None and unit_price > 0 and (token is None or token == currency)
            line_ok &= checks.add("UNIT_PRICE", ok, detail=f"prix lu {line.unit_price!r}", line_no=n)
        except ValueParseError as exc:
            line_ok &= checks.add("UNIT_PRICE", False, detail=str(exc), line_no=n)
        try:
            total, _ = _money(line.line_total, dec)
            line_ok &= checks.add("LINE_TOTAL", total is not None, detail=f"total lu {line.line_total!r}", line_no=n)
        except ValueParseError as exc:
            line_ok &= checks.add("LINE_TOTAL", False, detail=str(exc), line_no=n)
        if total is not None:
            computed += total
        else:
            totals_ok = False
        if qty is not None and unit_price is not None and total is not None:
            expected = qty * unit_price
            line_ok &= checks.add(
                "LINE_TOTAL_MATCH", abs(expected - total) <= tolerance,
                detail=f"{qty} × {unit_price} = {expected} ; total lu {total}", line_no=n,
            )
        basis = parse_unit_basis(line.unit_basis)
        upp: int | None = None
        try:
            upp, _ = parse_quantity(line.units_per_pack, decimal_separator=dec)
        except ValueParseError as exc:
            line_ok &= checks.add("UNITS_PER_PACK", False, detail=str(exc), line_no=n)
        if basis is None:
            line_ok &= checks.add("UNIT_BASIS", False, detail=f"unité/carton ambiguë : {line.unit_basis!r}", line_no=n)
        elif basis is UnitBasis.PACK:
            line_ok &= checks.add("UNIT_BASIS", upp is not None and upp >= 1, detail="carton sans nombre d'unités", line_no=n)
        else:
            line_ok &= checks.add("UNIT_BASIS", upp in (None, 1), detail=f"prix à l'unité mais {upp} unités par colis", line_no=n)
            upp = 1
        gtin = normalize_gtin(line.gtin)
        if clean_gtin(line.gtin) is None:
            checks.add("GTIN", False, blocking=False, detail="GTIN absent : fiche en brouillon", line_no=n)
        else:
            line_ok &= checks.add("GTIN", gtin is not None, detail=f"GTIN lu {line.gtin!r}", line_no=n)
        fmt = normalize_format(line.format or line.designation)
        checks.add("FORMAT", fmt is not ProductFormat.UNKNOWN, blocking=False, detail=f"format lu {line.format!r}", line_no=n)
        if is_accessory(fmt):
            language: str | None = Language.NA.value
        else:
            lang = normalize_language(line.language)
            language = lang.value if lang not in (Language.UNKNOWN, Language.NA) else None
            line_ok &= checks.add("LANGUAGE", language is not None, detail=f"langue lue {line.language!r}", line_no=n)
        raw_extension = line.extension if (line.extension or is_accessory(fmt)) else line.designation
        extension = normalize_extension(raw_extension, tbl, fmt=fmt)
        checks.add("EXTENSION", extension is not None, blocking=False, detail=f"extension lue {line.extension!r}", line_no=n)
        content = normalize_content(line.content)
        checks.add("CONTENT", content is not None, blocking=False, detail="contenu non indiqué" if content is None else "", line_no=n)
        vat_rate = doc_vat
        if line.vat_rate is not None:
            try:
                vat_rate = parse_rate(line.vat_rate, decimal_separator=dec)
            except ValueParseError as exc:
                line_ok &= checks.add("VAT_RATE", False, detail=str(exc), line_no=n)
        if line_ok and currency is not None and includes_vat is not None and sku is not None and unit_price is not None:
            offers.append(
                SupplierOffer(
                    supplier_id=doc.supplier_id,
                    supplier_sku=sku,
                    gtin=gtin,
                    language=language,
                    extension=extension,
                    format=None if fmt is ProductFormat.UNKNOWN else fmt.value,
                    content=content,
                    sealed=line.sealed,
                    units_per_pack=upp,
                    price=unit_price,
                    currency=currency,
                    price_includes_vat=includes_vat,
                    vat_rate=vat_rate,
                    carton_qty=upp if basis is UnitBasis.PACK else None,
                    source_ts=doc.received_at,
                    raw_ref=f"{doc.source_kind}:{doc.source_ref}#L{n}",
                    ship_from_country=(doc.ship_from_country or None),
                )
            )
    declared: Decimal | None = None
    extras = Decimal(0)
    try:
        declared, _ = _money(doc.declared_total, dec)
        for value in (doc.declared_shipping, doc.declared_other_fees):
            amount, _ = _money(value, dec)
            extras += amount or Decimal(0)
    except ValueParseError as exc:
        checks.add("DOCUMENT_TOTAL", False, detail=str(exc))
    else:
        if declared is None:
            checks.add("DOCUMENT_TOTAL", False, detail="total du document non recopié : contrôle impossible")
        elif not totals_ok:
            checks.add("DOCUMENT_TOTAL", False, detail="total non vérifiable : total de ligne manquant")
        else:
            checks.add(
                "DOCUMENT_TOTAL",
                abs(computed + extras - declared) <= tolerance,
                detail=f"lignes {computed} + port/frais {extras} = {computed + extras} ; total déclaré {declared}",
            )
    snapshot = SnapshotMeta(
        supplier_id=doc.supplier_id,
        source_kind=SourceKind(doc.source_kind),
        source_uri=doc.source_ref,
        fetched_at=doc.received_at,
        source_ts=doc.received_at,
        checksum_sha256=doc.document_sha256,
        byte_size=0,
        fictif=doc.fictif,
    )
    return AssistedReview(
        supplier_id=doc.supplier_id,
        source_ref=doc.source_ref,
        snapshot=snapshot,
        checks=tuple(checks.items),
        draft_offers=tuple(offers) if all(c.ok or not c.blocking for c in checks.items if c.line_no is None) else (),
        computed_total=computed if totals_ok else None,
        declared_total=declared,
        reviewed_at=now,
        lines_count=len(doc.lines),
        fictif=doc.fictif,
    )


def approve_review(review: AssistedReview, *, validated_by: str, validated_at: datetime) -> ImportResult:
    """Validation **humaine** nominative d'une revue sans contrôle bloquant -> import accepté."""
    name = validated_by.strip()
    if not name:
        raise AssistedImportError("validated_by obligatoire : nom de la personne qui valide")
    if validated_at.tzinfo is None or validated_at.utcoffset() is None:
        raise AssistedImportError("validated_at doit porter un fuseau horaire")
    if review.blocking_checks:
        codes = ", ".join(sorted({f"{c.code}@L{c.line_no}" if c.line_no else c.code for c in review.blocking_checks}))
        raise AssistedImportError(f"validation refusée : contrôles bloquants restants ({codes})")
    if not review.draft_offers:
        raise AssistedImportError("validation refusée : aucune offre exploitable")
    anomalies = [
        Anomaly(
            code=AnomalyCode.ASSISTED_IMPORT_VALIDATED.value,
            severity=Severity.INFO,
            detail=f"import assisté {review.source_ref} validé par {name} le {validated_at.isoformat()}",
        )
    ]
    anomalies += [
        Anomaly(code=c.code, severity=Severity.WARNING, detail=c.detail, line_no=c.line_no) for c in review.warnings
    ]
    return ImportResult(
        supplier_id=review.supplier_id,
        mapping_version=f"assisted:{review.snapshot.source_kind.value}",
        snapshot=review.snapshot,
        status=ImportStatus.ACCEPTED,
        offers=review.draft_offers,
        anomalies=tuple(anomalies),
        rows_read=review.lines_count,
        effective_source_ts=review.snapshot.source_ts,
        evaluated_at=validated_at,
        dry_run=True,
        fictif=review.fictif,
        assisted=True,
        validated_by=name,
    )
