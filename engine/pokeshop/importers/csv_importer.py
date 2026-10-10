"""Import CSV piloté par le dictionnaire de champs (séparateur, encodage, lignes de titre)."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from pokeshop.importers.base import ImportResult, RawRecord, RawSnapshot, RecordBatch, SourceReadError
from pokeshop.importers.mapping import FileFormat, MappingError, SupplierMapping
from pokeshop.importers.values import CellValue

__all__ = ["CsvReader", "import_csv"]


class CsvReader:
    """Lit un CSV en enregistrements bruts (texte), numéros de ligne physiques conservés."""

    def read(self, snapshot: RawSnapshot, mapping: SupplierMapping) -> RecordBatch:
        """Décode et découpe le fichier ; erreurs de format -> :class:`SourceReadError`."""
        if mapping.file_format is not FileFormat.CSV:
            raise MappingError(f"dictionnaire {mapping.supplier_id} : format {mapping.file_format.value}, pas csv")
        opts = mapping.csv
        try:
            text = snapshot.content.decode(opts.encoding)
        except UnicodeDecodeError as exc:
            raise SourceReadError(f"encodage {opts.encoding} incorrect : {exc.reason} (octet {exc.start})") from exc
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=opts.delimiter, quotechar=opts.quotechar, strict=True)
        try:
            for _ in range(opts.skip_rows):
                next(reader)
            raw_header = next(reader)
        except StopIteration as exc:
            raise SourceReadError("fichier vide ou sans en-tête") from exc
        except csv.Error as exc:
            raise SourceReadError(f"CSV invalide : {exc}") from exc
        header = tuple(h.strip() for h in raw_header)
        if not any(header):
            raise SourceReadError("en-tête vide")
        named = [h for h in header if h]
        if len(set(named)) != len(named):
            raise SourceReadError("en-tête : noms de colonnes en double")
        records: list[RawRecord] = []
        blank = 0
        try:
            for row in reader:
                line_no = reader.line_num
                if all(not cell.strip() for cell in row):
                    blank += 1
                    continue
                malformed = None
                if len(row) != len(header):
                    malformed = f"{len(row)} colonnes au lieu de {len(header)}"
                cells: dict[str, CellValue] = {}
                for i, name in enumerate(header):
                    if name:
                        cells[name] = row[i] if i < len(row) else None
                records.append(RawRecord(line_no=line_no, cells=cells, malformed=malformed))
        except csv.Error as exc:
            raise SourceReadError(f"CSV invalide ligne {reader.line_num} : {exc}") from exc
        return RecordBatch(records=tuple(records), header=tuple(h for h in header if h), blank_rows=blank)


def import_csv(
    source: str | Path | bytes,
    mapping: SupplierMapping | str | Path,
    *,
    now: datetime,
    **kwargs: Any,
) -> ImportResult:
    """Raccourci : importe un fichier CSV (chemin ou contenu) en simulation."""
    from pokeshop.importers.runner import run_import

    return run_import(mapping, source, now=now, **kwargs)
