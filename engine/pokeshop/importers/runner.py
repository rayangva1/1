"""Exécution d'un import et intégration de son résultat (simulation par défaut).

* :func:`run_import` — dictionnaire + source (chemin, octets, capture ou connecteur) -> résultat.
* :func:`merge_offer_book` — applique un résultat à la vue des offres d'un fournisseur :
  un import rejeté conserve **toutes** les offres précédentes (elles deviennent périmées
  d'elles-mêmes après 24 h), une référence absente n'est jamais supprimée ni mise à zéro.
  Le stock local n'est jamais lu ni écrit ici (BP §12 : une panne de flux n'efface pas
  le stock local confirmé).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pokeshop.catalog import ExtensionTable, load_extension_table
from pokeshop.importers.base import (
    BytesConnector,
    FileConnector,
    ImportBaseline,
    ImporterError,
    ImportPolicy,
    ImportResult,
    ImportStatus,
    QuarantineReason,
    RawSnapshot,
    RecordBatch,
    SourceReadError,
    SupplierConnector,
)
from pokeshop.importers.csv_importer import CsvReader
from pokeshop.importers.mapping import FileFormat, MappingError, SupplierMapping, load_mapping
from pokeshop.importers.validation import build_import_result, failed_result
from pokeshop.importers.xlsx_importer import XlsxReader
from pokeshop.importers.xml_importer import XmlReader
from pokeshop.models import FrozenModel, SupplierOffer

__all__ = [
    "RecordReader",
    "reader_for",
    "extension_table_for",
    "parse_snapshot",
    "run_import",
    "failed_result",
    "OfferBookUpdate",
    "merge_offer_book",
    "next_baseline",
]


class RecordReader(Protocol):
    """Lecteur d'un format de fichier."""

    def read(self, snapshot: RawSnapshot, mapping: SupplierMapping) -> RecordBatch:
        """Découpe une capture en enregistrements bruts."""
        ...


_READERS: dict[FileFormat, RecordReader] = {
    FileFormat.CSV: CsvReader(),
    FileFormat.XLSX: XlsxReader(),
    FileFormat.XML: XmlReader(),
}


def reader_for(file_format: FileFormat) -> RecordReader:
    """Lecteur du format demandé."""
    return _READERS[file_format]


def extension_table_for(mapping: SupplierMapping, extensions: ExtensionTable | None = None) -> ExtensionTable:
    """Table d'alias à utiliser : celle fournie, sinon la table par défaut + tables FICTIVES du dictionnaire."""
    if extensions is not None:
        return extensions
    base = load_extension_table()
    loaded = set(base.sources)
    extra = [p for p in mapping.extension_table_paths() if str(p) not in loaded]
    return base.merged(load_extension_table(extra)) if extra else base


def _check_now(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ImporterError("now doit porter un fuseau horaire")


def _check_mode(mapping: SupplierMapping, dry_run: bool) -> None:
    if not dry_run and mapping.simulation_only:
        raise MappingError(
            f"dictionnaire {mapping.supplier_id} au statut {mapping.status.value} : simulation uniquement "
            "(un import réel exige un dictionnaire VALIDE sur fichier réel)"
        )


def parse_snapshot(
    snapshot: RawSnapshot,
    mapping: SupplierMapping,
    *,
    now: datetime,
    policy: ImportPolicy | None = None,
    baseline: ImportBaseline | None = None,
    extensions: ExtensionTable | None = None,
    dry_run: bool = True,
) -> ImportResult:
    """Lit une capture et applique les validations. Fichier illisible -> ``FAILED`` (pas d'exception)."""
    _check_now(now)
    _check_mode(mapping, dry_run)
    try:
        batch = reader_for(mapping.file_format).read(snapshot, mapping)
    except SourceReadError as exc:
        return failed_result(mapping, QuarantineReason.UNREADABLE_SOURCE, str(exc), now=now, snapshot=snapshot, dry_run=dry_run)
    except MappingError as exc:
        return failed_result(mapping, QuarantineReason.MAPPING_MISMATCH, str(exc), now=now, snapshot=snapshot, dry_run=dry_run)
    table = extension_table_for(mapping, extensions)
    return build_import_result(
        snapshot, batch, mapping, now=now, table=table, policy=policy, baseline=baseline, dry_run=dry_run
    )


def run_import(
    mapping: SupplierMapping | str | Path,
    source: RawSnapshot | SupplierConnector | str | Path | bytes,
    *,
    now: datetime,
    policy: ImportPolicy | None = None,
    baseline: ImportBaseline | None = None,
    extensions: ExtensionTable | None = None,
    dry_run: bool = True,
    source_ts: datetime | None = None,
    fetched_at: datetime | None = None,
) -> ImportResult:
    """Import complet en simulation : jamais d'exception pour une panne de source (résultat ``FAILED``).

    ``mapping`` : objet, chemin YAML ou identifiant fournisseur. ``source`` : capture, connecteur,
    chemin de fichier ou contenu. ``fetched_at`` : heure de capture (défaut ``now``).
    """
    _check_now(now)
    m = mapping if isinstance(mapping, SupplierMapping) else load_mapping(mapping)
    _check_mode(m, dry_run)
    if isinstance(source, RawSnapshot):
        return parse_snapshot(source, m, now=now, policy=policy, baseline=baseline, extensions=extensions, dry_run=dry_run)
    clock_value = fetched_at or now

    def clock() -> datetime:
        return clock_value

    connector: SupplierConnector
    if isinstance(source, SupplierConnector):
        connector = source
        if connector.mapping.supplier_id != m.supplier_id:
            raise ImporterError("connecteur et dictionnaire de fournisseurs différents")
    elif isinstance(source, bytes):
        connector = BytesConnector(source, m, clock=clock, source_ts=source_ts)
    else:
        connector = FileConnector(source, m, clock=clock, source_ts=source_ts)
    return connector.run(now=now, policy=policy, baseline=baseline, extensions=extensions, dry_run=dry_run)


class OfferBookUpdate(FrozenModel):
    """Vue des offres d'un fournisseur après application d'un import."""

    offers: dict[str, SupplierOffer]
    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()
    """Offres précédentes conservées telles quelles (absentes, en quarantaine ou import rejeté)."""
    import_rejected: bool = False


def merge_offer_book(previous: Mapping[str, SupplierOffer], result: ImportResult) -> OfferBookUpdate:
    """Applique un import à la vue ``{supplier_sku: offre}`` sans jamais supprimer une offre."""
    for sku, offer in previous.items():
        if offer.supplier_id != result.supplier_id or offer.supplier_sku != sku:
            raise ImporterError(f"vue d'offres incohérente pour {sku}")
    if result.retain_previous_offers:
        return OfferBookUpdate(offers=dict(previous), retained=tuple(sorted(previous)), import_rejected=True)
    offers = dict(previous)
    added: list[str] = []
    updated: list[str] = []
    for offer in result.offers:
        (updated if offer.supplier_sku in previous else added).append(offer.supplier_sku)
        offers[offer.supplier_sku] = offer
    fresh = {o.supplier_sku for o in result.offers}
    retained = sorted(sku for sku in previous if sku not in fresh)
    return OfferBookUpdate(offers=offers, added=tuple(sorted(added)), updated=tuple(sorted(updated)), retained=tuple(retained))


def next_baseline(baseline: ImportBaseline | None, result: ImportResult) -> ImportBaseline | None:
    """Référence pour le prochain import : inchangée si l'import est rejeté."""
    if baseline is None:
        if result.status in (ImportStatus.ACCEPTED, ImportStatus.PARTIAL):
            return ImportBaseline.from_result(result)
        return None
    return baseline.updated_with(result)
