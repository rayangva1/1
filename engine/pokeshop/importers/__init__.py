"""Connecteurs fournisseurs et import des offres (propriété : agent data-pipeline, SPEC §2.5).

Ordre de priorité des sources (BP §6) : 1. API ou flux documenté ; 2. fichier fourni
(CSV / Excel / XML) ; 3. tarif email/PDF en **import assisté** (:mod:`.email_pdf_assist`).
Tout import tourne en simulation : il produit un :class:`ImportResult` (offres valides,
quarantaine motivée, anomalies, rapport) et n'écrit nulle part.

Usage courant ::

    from pokeshop.importers import run_import, ImportBaseline
    result = run_import("fictif_grossiste_a", "data/samples/FICTIF_offres_grossiste_a.csv", now=now)
    print(result.report_markdown())
"""

from pokeshop.importers.base import (
    QUARANTINE_LABELS_FR,
    SNAPSHOT_LEVEL_REASONS,
    Anomaly,
    AnomalyCode,
    BaselinePrice,
    BytesConnector,
    FetchError,
    FileConnector,
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
    SourceReadError,
    SupplierConnector,
)
from pokeshop.importers.csv_importer import CsvReader, import_csv
from pokeshop.importers.email_pdf_assist import (
    AssistedCheck,
    AssistedImportError,
    AssistedLine,
    AssistedPriceList,
    AssistedReview,
    approve_review,
    load_price_list,
    review_price_list,
)
from pokeshop.importers.mapping import (
    DEFAULT_MAPPINGS_DIR,
    FIELD_NAMES,
    FileFormat,
    MappingError,
    MappingStatus,
    SupplierMapping,
    list_mappings,
    load_mapping,
)
from pokeshop.importers.runner import (
    OfferBookUpdate,
    extension_table_for,
    failed_result,
    merge_offer_book,
    next_baseline,
    parse_snapshot,
    reader_for,
    run_import,
)
from pokeshop.importers.values import UnitBasis, ValueParseError
from pokeshop.importers.xlsx_importer import XlsxReader, import_xlsx
from pokeshop.importers.xml_importer import XmlReader, import_xml

__all__ = [
    "QUARANTINE_LABELS_FR",
    "SNAPSHOT_LEVEL_REASONS",
    "Anomaly",
    "AnomalyCode",
    "AssistedCheck",
    "AssistedImportError",
    "AssistedLine",
    "AssistedPriceList",
    "AssistedReview",
    "BaselinePrice",
    "BytesConnector",
    "CsvReader",
    "DEFAULT_MAPPINGS_DIR",
    "FIELD_NAMES",
    "FetchError",
    "FileConnector",
    "FileFormat",
    "ImportBaseline",
    "ImportPolicy",
    "ImportResult",
    "ImportStatus",
    "ImporterError",
    "MappingError",
    "MappingStatus",
    "OfferBookUpdate",
    "QuarantineReason",
    "QuarantinedRow",
    "RawRecord",
    "RawSnapshot",
    "RecordBatch",
    "Severity",
    "SnapshotMeta",
    "SourceKind",
    "SourceReadError",
    "SupplierConnector",
    "SupplierMapping",
    "UnitBasis",
    "ValueParseError",
    "XlsxReader",
    "XmlReader",
    "approve_review",
    "extension_table_for",
    "failed_result",
    "import_csv",
    "import_xlsx",
    "import_xml",
    "list_mappings",
    "load_mapping",
    "load_price_list",
    "merge_offer_book",
    "next_baseline",
    "parse_snapshot",
    "reader_for",
    "review_price_list",
    "run_import",
]
