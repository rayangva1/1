"""Import XML piloté par le dictionnaire de champs (chemin des enregistrements, attribut d'export).

Sécurité : les documents contenant une DTD ou des entités (``<!DOCTYPE``, ``<!ENTITY``)
sont refusés (pas de bibliothèque tierce de durcissement autorisée par le SPEC §1).
Chaque enregistrement est aplati : attribut ``@nom``, enfant ``nom``, petit-enfant
``parent/enfant``, répétition ``palier[2]/@qte``. ``line_no`` = rang de l'enregistrement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pokeshop.importers.base import ImportResult, RawRecord, RawSnapshot, RecordBatch, SourceReadError
from pokeshop.importers.mapping import FileFormat, MappingError, SupplierMapping
from pokeshop.importers.values import CellValue

__all__ = ["XmlReader", "import_xml", "flatten_element"]

_FORBIDDEN_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def flatten_element(element: ET.Element, prefix: str = "", out: dict[str, CellValue] | None = None) -> dict[str, CellValue]:
    """Aplatit un élément XML en ``{chemin: texte}`` (voir docstring du module)."""
    result: dict[str, CellValue] = {} if out is None else out
    for key, value in element.attrib.items():
        result[f"{prefix}@{_local(key)}"] = value.strip() or None
    counts: Counter[str] = Counter()
    for child in element:
        if not isinstance(child.tag, str):  # commentaires / instructions
            continue
        tag = _local(child.tag)
        counts[tag] += 1
        name = tag if counts[tag] == 1 else f"{tag}[{counts[tag]}]"
        path = f"{prefix}{name}"
        text = (child.text or "").strip() or None
        if len(child) == 0 and not child.attrib:
            result[path] = text
        else:
            if text is not None:
                result[path] = text
            flatten_element(child, f"{path}/", result)
    return result


class XmlReader:
    """Lit un flux XML en enregistrements bruts."""

    def read(self, snapshot: RawSnapshot, mapping: SupplierMapping) -> RecordBatch:
        """Analyse le document ; DTD, entités ou XML invalide -> :class:`SourceReadError`."""
        if mapping.file_format is not FileFormat.XML:
            raise MappingError(f"dictionnaire {mapping.supplier_id} : format {mapping.file_format.value}, pas xml")
        upper = snapshot.content.upper()
        if any(marker in upper for marker in _FORBIDDEN_MARKERS):
            raise SourceReadError("DTD ou entités XML interdites (sécurité)")
        try:
            root = ET.fromstring(snapshot.content)
        except ET.ParseError as exc:
            raise SourceReadError(f"XML invalide : {exc}") from exc
        opts = mapping.xml
        try:
            elements = root.findall(opts.record_path, opts.namespaces)
        except (SyntaxError, KeyError, TypeError, ValueError) as exc:  # ElementPath lève parfois TypeError
            raise MappingError(f"record_path XML invalide : {opts.record_path!r} ({exc})") from exc
        records: list[RawRecord] = []
        header: dict[str, None] = {}
        blank = 0
        for index, element in enumerate(elements, start=1):
            cells = flatten_element(element)
            if all(v is None for v in cells.values()):
                blank += 1
                continue
            header.update(dict.fromkeys(cells))
            records.append(RawRecord(line_no=index, cells=cells))
        source_ts_raw = root.get(opts.source_ts_attribute) if opts.source_ts_attribute else None
        return RecordBatch(records=tuple(records), header=tuple(header), source_ts_raw=source_ts_raw, blank_rows=blank)


def import_xml(
    source: str | Path | bytes,
    mapping: SupplierMapping | str | Path,
    *,
    now: datetime,
    **kwargs: Any,
) -> ImportResult:
    """Raccourci : importe un flux XML (chemin ou contenu) en simulation."""
    from pokeshop.importers.runner import run_import

    return run_import(mapping, source, now=now, **kwargs)
