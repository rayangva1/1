"""Conversions déterministes des cellules fournisseur (texte CSV/XML, valeur typée Excel).

Aucune heuristique « intelligente » : une valeur ambiguë lève :class:`ValueParseError`
(la ligne part en quarantaine) plutôt que d'être devinée. Exemples refusés : ``"12.50"``
dans un fichier à virgule décimale, ``"1.23,4"`` (groupes de milliers faux), ``"$"``.
Les flottants sont refusés : le lecteur Excel les convertit d'abord via :func:`excel_number`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from zoneinfo import ZoneInfo

from pokeshop.catalog import fold
from pokeshop.errors import PokeshopError
from pokeshop.models import AvailabilityStatus

__all__ = [
    "CellValue",
    "ValueParseError",
    "UnknownCurrencyError",
    "UnitBasis",
    "DEFAULT_THOUSANDS_SEPARATORS",
    "DEFAULT_DATE_FORMATS",
    "excel_number",
    "cell_text",
    "is_blank",
    "parse_decimal",
    "normalize_currency",
    "parse_money",
    "parse_rate",
    "parse_quantity",
    "parse_bool",
    "parse_vat_basis",
    "parse_unit_basis",
    "parse_availability",
    "parse_date",
    "parse_datetime",
    "mapped_value",
]

CellValue = str | int | Decimal | date | datetime | bool | None
"""Valeur brute d'une cellule après lecture (jamais ``float``)."""


class ValueParseError(PokeshopError, ValueError):
    """Valeur de cellule illisible ou ambiguë."""


class UnknownCurrencyError(ValueParseError):
    """Devise ou symbole monétaire non reconnu (ex. ``$`` : dollar de quel pays ?)."""


class UnitBasis(str, Enum):
    """Base d'un prix ou d'une quantité fournisseur."""

    UNIT = "UNIT"
    """Unité de vente boutique (1 display, 1 ETB, 1 booster…)."""
    PACK = "PACK"
    """Colis/carton de ``units_per_pack`` unités de vente."""


DEFAULT_THOUSANDS_SEPARATORS: tuple[str, ...] = (" ", "'", "’", " ", " ")
DEFAULT_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y")
_DATETIME_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def excel_number(value: float) -> int | Decimal:
    """Convertit un nombre lu dans Excel : entier exact -> ``int``, sinon ``Decimal`` de sa
    représentation décimale la plus courte (``12.3`` -> ``Decimal("12.3")``), jamais le binaire."""
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueParseError("nombre Excel non fini")
    if value.is_integer() and abs(value) < 2**53:
        return int(value)
    return Decimal(repr(value))


def cell_text(value: CellValue) -> str | None:
    """Texte d'une cellule (``None`` si vide). Les dates sont rendues en ISO."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueParseError("float interdit : convertir via excel_number")
    text = str(value).strip()
    return text or None


def is_blank(value: CellValue) -> bool:
    """Vrai si la cellule est vide (``None`` ou texte blanc)."""
    return cell_text(value) is None


def _strip_thousands(text: str, sep: str, decimal_separator: str) -> str:
    if sep not in text:
        return text
    sign = text[0] if text[0] in "+-" else ""
    body = text[len(sign) :]
    int_part, _, frac = body.partition(decimal_separator)
    if sep in frac:
        raise ValueParseError(f"séparateur de milliers {sep!r} après la décimale")
    groups = int_part.split(sep)
    ok = 1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:]) and all(g.isdigit() for g in groups)
    if not ok:
        raise ValueParseError(f"séparateur de milliers {sep!r} mal placé dans {text!r}")
    return text.replace(sep, "")


def parse_decimal(
    value: CellValue,
    *,
    decimal_separator: str = ".",
    thousands_separators: Sequence[str] = DEFAULT_THOUSANDS_SEPARATORS,
) -> Decimal | None:
    """Nombre décimal exact ; ``None`` si vide. Refuse tout format ambigu."""
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueParseError(f"{type(value).__name__} refusé pour un nombre")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueParseError("nombre non fini")
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, (date, datetime)):
        raise ValueParseError("date reçue à la place d'un nombre")
    text = str(value).strip()
    if not text:
        return None
    if decimal_separator not in (".", ","):
        raise ValueParseError(f"séparateur décimal non géré : {decimal_separator!r}")
    for sep in thousands_separators:
        if sep != decimal_separator:
            text = _strip_thousands(text, sep, decimal_separator)
    other = "," if decimal_separator == "." else "."
    if other in text:
        raise ValueParseError(f"{value!r} : séparateur {other!r} ambigu (décimal attendu {decimal_separator!r})")
    text = text.replace(decimal_separator, ".")
    if not _NUMBER_RE.match(text):
        raise ValueParseError(f"nombre illisible : {value!r}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - garanti par la regex
        raise ValueParseError(f"nombre illisible : {value!r}") from exc


_CURRENCY_TOKENS: dict[str, str | None] = {
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "chf": "CHF",
    "fr": "CHF",
    "frs": "CHF",
    "sfr": "CHF",
    "francs": "CHF",
    "francs suisses": "CHF",
    "franc suisse": "CHF",
    "usd": "USD",
    "us": "USD",
    "gbp": "GBP",
    "£": "GBP",
    "$": None,  # ambigu (USD, CAD, AUD…) => refusé
}
_ISO_RE = re.compile(r"^[A-Z]{3}$")


def normalize_currency(raw: CellValue, extra: Mapping[str, str] | None = None) -> str | None:
    """Code ISO 4217 depuis un libellé (``"€"``, ``"EUR"``, ``"Fr."``, ``"CHF"``) ; ``None`` si vide.

    Un code ISO inconnu de la table est renvoyé tel quel (le contrôle « devise autorisée »
    est fait par l'importeur). Symbole ambigu ou libellé inconnu -> :class:`UnknownCurrencyError`.
    """
    text = cell_text(raw)
    if text is None:
        return None
    if extra:
        mapped = mapped_value(text, extra)
        if mapped is not None:
            return mapped
    stripped = text.strip()
    if stripped in ("€", "£", "$"):
        key = stripped
    else:
        key = fold(stripped)
    if key in _CURRENCY_TOKENS:
        code = _CURRENCY_TOKENS[key]
        if code is None:
            raise UnknownCurrencyError(f"symbole monétaire ambigu : {text!r}")
        return code
    upper = stripped.upper()
    if _ISO_RE.match(upper):
        return upper
    raise UnknownCurrencyError(f"devise non reconnue : {text!r}")


_MONEY_RE = re.compile(r"^(?P<pre>[^\d+\-]*?)\s*(?P<num>[+-]?\d[\d\s'’.,  ]*?)\s*(?P<post>[^\d]*)$")


def parse_money(
    value: CellValue,
    *,
    decimal_separator: str = ".",
    thousands_separators: Sequence[str] = DEFAULT_THOUSANDS_SEPARATORS,
    currency_aliases: Mapping[str, str] | None = None,
) -> tuple[Decimal | None, str | None]:
    """Montant et devise éventuellement accolée (``"12,50 €"`` -> ``(12.50, "EUR")``).

    Devise absente de la cellule -> ``None`` (la colonne devise ou le défaut s'appliquent).
    """
    if value is None or isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        return parse_decimal(value, decimal_separator=decimal_separator), None
    text = cell_text(value)
    if text is None:
        return None, None
    match = _MONEY_RE.match(text)
    if match is None:
        raise ValueParseError(f"montant illisible : {text!r}")
    pre = match.group("pre").strip()
    post = match.group("post").strip()
    if pre and post:
        raise ValueParseError(f"deux indications de devise : {text!r}")
    token = pre or post
    currency = normalize_currency(token, currency_aliases) if token else None
    amount = parse_decimal(
        match.group("num").strip(), decimal_separator=decimal_separator, thousands_separators=thousands_separators
    )
    return amount, currency


def parse_rate(value: CellValue, *, decimal_separator: str = ".") -> Decimal | None:
    """Taux (TVA, remise) en fraction : ``"20 %"``, ``"20"``, ``"0.2"`` -> ``0.2``.

    Valeur > 1 sans signe % = pourcentage. Résultat hors de [0, 1[ -> erreur.
    """
    if value is None:
        return None
    percent = False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("%"):
            percent = True
            text = text[:-1].strip()
        number = parse_decimal(text, decimal_separator=decimal_separator)
    else:
        number = parse_decimal(value, decimal_separator=decimal_separator)
    if number is None:
        return None
    if number < 0:
        raise ValueParseError(f"taux négatif : {value!r}")
    if percent or number > 1:
        number = number / 100
    if number >= 1:
        raise ValueParseError(f"taux ≥ 100 % : {value!r}")
    return number


_APPROX_RE = re.compile(r"^(?:(?P<a>\d+)\s*\+|(?:>|≥|>=)\s*(?P<b>\d+))$")


def parse_quantity(value: CellValue, *, decimal_separator: str = ".") -> tuple[int | None, bool]:
    """Quantité entière ≥ 0 et indicateur « approximative » (``"10+"``, ``">50"`` -> borne basse).

    Vide -> ``(None, False)``. Négatif, décimal non entier ou texte -> :class:`ValueParseError`.
    """
    if value is None:
        return None, False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, False
        approx = _APPROX_RE.match(text)
        if approx:
            return int(approx.group("a") or approx.group("b")), True
        number = parse_decimal(text, decimal_separator=decimal_separator)
    else:
        number = parse_decimal(value, decimal_separator=decimal_separator)
    if number is None:
        return None, False
    if number < 0:
        raise ValueParseError(f"quantité négative : {value!r}")
    if number != number.to_integral_value():
        raise ValueParseError(f"quantité non entière : {value!r}")
    return int(number), False


_TRUE_WORDS = frozenset({"oui", "yes", "true", "vrai", "1", "x", "o", "y", "scelle", "neuf scelle", "sealed", "sous blister"})
_FALSE_WORDS = frozenset({"non", "no", "false", "faux", "0", "n", "ouvert", "open", "unsealed", "occasion", "descelle"})


def parse_bool(value: CellValue, extra: Mapping[str, str] | None = None) -> bool | None:
    """Booléen (``"oui"``, ``"scellé"``, ``"non"``…) ; vide ou inconnu -> ``None``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {1: True, 0: False}.get(value)
    text = cell_text(value)
    if text is None:
        return None
    if extra:
        mapped = mapped_value(text, extra)
        if mapped is not None:
            return parse_bool(mapped)
    key = fold(text)
    if key in _TRUE_WORDS:
        return True
    if key in _FALSE_WORDS:
        return False
    return None


_HT_WORDS = frozenset(
    {
        "ht", "h t", "hors taxe", "hors taxes", "hors tva", "excl tva", "exkl mwst", "net ht", "prix ht",
        "sans tva", "ex vat", "excl vat", "excluding vat", "prix net ht", "tarif ht",
    }
)
_TTC_WORDS = frozenset(
    {
        "ttc", "t t c", "toutes taxes comprises", "tva comprise", "tva incluse", "incl tva", "inkl mwst",
        "avec tva", "incl vat", "including vat", "prix ttc", "tarif ttc",
    }
)


def parse_vat_basis(value: CellValue, extra: Mapping[str, str] | None = None) -> bool | None:
    """Base TVA d'un prix : ``True`` = TTC, ``False`` = HT, ``None`` = inconnue.

    « net » seul est **inconnu** (prix net de remise ≠ prix hors taxe).
    """
    if isinstance(value, bool):
        return None
    text = cell_text(value)
    if text is None:
        return None
    if extra:
        mapped = mapped_value(text, extra)
        if mapped is not None:
            return parse_vat_basis(mapped)
    key = fold(text)
    if key in _HT_WORDS:
        return False
    if key in _TTC_WORDS:
        return True
    return None


_UNIT_WORDS = frozenset(
    {
        "unite", "unites", "u", "unit", "units", "piece", "pieces", "pc", "pce", "pces", "each", "ea", "stk",
        "stuck", "prix unitaire", "a l unite", "par unite", "unitaire",
    }
)
_PACK_WORDS = frozenset(
    {"carton", "cartons", "colis", "pack", "lot", "caisse", "case", "ctn", "cs", "par carton", "prix carton", "inner"}
)


def parse_unit_basis(value: CellValue, extra: Mapping[str, str] | None = None) -> UnitBasis | None:
    """Base d'un prix : ``UNIT`` (unité de vente) ou ``PACK`` (carton) ; ambigu -> ``None``.

    « display », « palette » ou « boîte » sont ambigus (unité de vente ou carton selon le produit).
    """
    if isinstance(value, UnitBasis):
        return value
    text = cell_text(value)
    if text is None:
        return None
    if extra:
        mapped = mapped_value(text, extra)
        if mapped is not None:
            return parse_unit_basis(mapped)
    key = fold(text)
    if key in _UNIT_WORDS:
        return UnitBasis.UNIT
    if key in _PACK_WORDS:
        return UnitBasis.PACK
    if text.strip().upper() in UnitBasis.__members__:
        return UnitBasis(text.strip().upper())
    return None


_AVAILABILITY_WORDS: dict[str, AvailabilityStatus] = {}
for _status, _words in {
    AvailabilityStatus.IN_STOCK: ("en stock", "disponible", "dispo", "in stock", "available", "stock", "oui"),
    AvailabilityStatus.LOW_STOCK: (
        "stock faible", "stock limite", "limite", "peu de stock", "low stock", "derniers", "dernieres pieces",
    ),
    AvailabilityStatus.OUT_OF_STOCK: (
        "rupture", "rupture de stock", "epuise", "indisponible", "out of stock", "non", "sold out",
    ),
    AvailabilityStatus.PREORDER: (
        "precommande", "pre commande", "preorder", "pre order", "a paraitre", "sortie prochaine",
    ),
    AvailabilityStatus.ALLOCATION: ("allocation", "sur allocation", "allocated", "quota", "sur quota"),
    AvailabilityStatus.DISCONTINUED: ("fin de serie", "arrete", "discontinued", "plus fabrique", "fin de vie"),
}.items():
    for _word in _words:
        _AVAILABILITY_WORDS[_word] = _status


def parse_availability(value: CellValue, extra: Mapping[str, str] | None = None) -> AvailabilityStatus:
    """Statut de disponibilité normalisé ; libellé inconnu -> ``UNKNOWN`` (jamais « en stock »)."""
    text = cell_text(value)
    if text is None:
        return AvailabilityStatus.UNKNOWN
    if extra:
        mapped = mapped_value(text, extra)
        if mapped is not None:
            return parse_availability(mapped)
    upper = text.strip().upper()
    if upper in AvailabilityStatus.__members__:
        return AvailabilityStatus(upper)
    return _AVAILABILITY_WORDS.get(fold(text), AvailabilityStatus.UNKNOWN)


def parse_date(value: CellValue, formats: Sequence[str] = DEFAULT_DATE_FORMATS) -> date | None:
    """Date (formats jour-mois-année suisses/français ou ISO) ; ``None`` si vide."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = cell_text(value)
    if text is None:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueParseError(f"date illisible : {text!r}")


def parse_datetime(value: CellValue, tz: ZoneInfo, date_formats: Sequence[str] = DEFAULT_DATE_FORMATS) -> datetime | None:
    """Horodatage avec fuseau ; une valeur sans fuseau est interprétée dans ``tz``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time(0, 0))
    else:
        text = cell_text(value)
        if text is None:
            return None
        parsed: datetime | None = None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for fmt in _DATETIME_FORMATS:
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            day = parse_date(text, date_formats)
            assert day is not None
            parsed = datetime.combine(day, time(0, 0))
        result = parsed
    if result.tzinfo is None or result.utcoffset() is None:
        result = result.replace(tzinfo=tz)
    return result


def mapped_value(text: str, mapping: Mapping[str, str]) -> str | None:
    """Valeur canonique d'un dictionnaire de correspondances (clés comparées après repli)."""
    key = fold(text)
    for raw, canonical in mapping.items():
        if fold(raw) == key:
            return canonical
    return None
