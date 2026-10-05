"""Catalogue central : identité produit, normalisation et rapprochement offre ↔ produit.

Propriété : agent data-pipeline (SPEC §2.4, BP §6 et §11 ligne 4).

* Clé d'identité produit (BP §6) : **GTIN + langue + extension + format + contenu + scellé**.
* GTIN : contrôle GS1 modulo 10 (GTIN-8/12/13/14). Les jeux d'essai utilisent des GTIN
  FICTIFS ``200…`` (plage GS1 « restricted circulation », SPEC §0.7).
* Normalisations déterministes (aucune IA) : langue, format, extension (table d'alias
  versionnée ``data/extensions_aliases.yaml``), contenu.
* Rapprochement : ``MATCHED`` seulement si l'identité est complète, scellée et identique à
  un produit connu sans conflit. Nouvelle référence => ``NEW_DRAFT`` (BP §6 : toute nouvelle
  référence passe d'abord en brouillon). Doute (même nom mais contenu différent, GTIN
  absent ou en conflit, langue inconnue…) => ``AMBIGUOUS`` : brouillon jamais publié.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, ValidationError, field_validator

from pokeshop.errors import PokeshopError
from pokeshop.models import FrozenModel, ProductIdentity, SupplierOffer

__all__ = [
    "CatalogError",
    "Language",
    "ProductFormat",
    "ACCESSORY_FORMATS",
    "CARD_PRODUCT_FORMATS",
    "FORMAT_LABELS_FR",
    "FORMAT_BUDGET_CATEGORY",
    "NO_EXTENSION",
    "EXTENSIONS_ENV_VAR",
    "DEFAULT_EXTENSIONS_PATH",
    "fold",
    "clean_gtin",
    "gtin_check_digit",
    "validate_gtin",
    "normalize_gtin",
    "is_case_level_gtin",
    "is_fictitious_gtin",
    "fictitious_gtin13",
    "normalize_language",
    "accessory_language",
    "normalize_format",
    "is_accessory",
    "expected_language_for",
    "normalize_content",
    "booster_count",
    "SourceRef",
    "ExtensionEntry",
    "ExtensionMatch",
    "ExtensionTable",
    "load_extension_table",
    "normalize_extension",
    "IdentityIssue",
    "IDENTITY_ISSUE_LABELS_FR",
    "NormalizedIdentity",
    "normalize_identity",
    "product_identity_key",
    "product_title_fr",
    "SupplierLink",
    "CatalogProduct",
    "CatalogIndex",
    "MatchStatus",
    "MatchResult",
    "match_offer_to_product",
]


class CatalogError(PokeshopError, ValueError):
    """Table d'alias ou donnée de catalogue invalide."""


# ------------------------------------------------------------------- texte


_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def fold(text: str) -> str:
    """Forme de comparaison : sans accents, minuscules, ponctuation -> espace, espaces réduits.

    ``"Méga-Évolution – Nuit Noire"`` -> ``"mega evolution nuit noire"`` ;
    ``"30ᵉ Anniversaire"`` -> ``"30e anniversaire"``.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return _NON_ALNUM.sub(" ", stripped).strip()


def _contains(haystack: str, needle: str) -> bool:
    """Vrai si ``needle`` (forme repliée) apparaît comme suite de mots dans ``haystack``."""
    return f" {needle} " in f" {haystack} "


# -------------------------------------------------------------------- GTIN

_GTIN_LENGTHS = (8, 12, 13, 14)
_GTIN_STRIP = re.compile(r"[\s\-  ]+")


def clean_gtin(raw: str | int | None) -> str | None:
    """Retire espaces et tirets ; ``None``/vide -> ``None``. Ne valide pas le contenu."""
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw) if isinstance(raw, int) else raw
    cleaned = _GTIN_STRIP.sub("", text)
    return cleaned or None


def gtin_check_digit(payload: str) -> int:
    """Chiffre de contrôle GS1 (modulo 10) d'un GTIN privé de son dernier chiffre."""
    if not payload.isdigit() or not payload.isascii():
        raise CatalogError(f"GTIN : chiffres attendus, reçu {payload!r}")
    total = 0
    for i, ch in enumerate(reversed(payload)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10


def validate_gtin(code: str | int | None) -> bool:
    """Vrai si ``code`` est un GTIN-8/12/13/14 au checksum GS1 valide (tout à zéro refusé)."""
    cleaned = clean_gtin(code)
    if cleaned is None or not cleaned.isascii() or not cleaned.isdigit():
        return False
    if len(cleaned) not in _GTIN_LENGTHS or set(cleaned) == {"0"}:
        return False
    return gtin_check_digit(cleaned[:-1]) == int(cleaned[-1])


def normalize_gtin(code: str | int | None) -> str | None:
    """Forme canonique d'un GTIN valide, ``None`` sinon.

    GTIN-12 (UPC) et GTIN-14 d'indicateur 0 -> forme 13 chiffres ; GTIN-8 -> 8 chiffres ;
    GTIN-14 d'indicateur 1 à 9 (unité logistique, ex. carton) conservé sur 14 chiffres.
    Deux écritures du même article donnent donc la même clé.
    """
    if not validate_gtin(code):
        return None
    cleaned = clean_gtin(code)
    assert cleaned is not None
    g14 = cleaned.zfill(14)
    if g14[0] != "0":
        return g14
    g13 = g14[1:]
    if g13.startswith("00000"):
        return g13[5:]
    return g13


def is_case_level_gtin(code: str | int | None) -> bool:
    """Vrai pour un GTIN-14 d'indicateur 1 à 8 : il désigne un colis/carton, pas l'unité retail."""
    gtin = normalize_gtin(code)
    return gtin is not None and len(gtin) == 14 and gtin[0] in "12345678"


def is_fictitious_gtin(code: str | int | None) -> bool:
    """Vrai pour un GTIN-13 de test ``200…`` (jeux d'essai FICTIFS, SPEC §0.7)."""
    gtin = normalize_gtin(code)
    return gtin is not None and len(gtin) == 13 and gtin.startswith("200")


def fictitious_gtin13(seq: int) -> str:
    """GTIN-13 FICTIF ``200`` + numéro sur 9 chiffres + contrôle. Jamais un EAN réel."""
    if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 999_999_999:
        raise CatalogError("seq doit être un entier entre 0 et 999 999 999")
    payload = f"200{seq:09d}"
    return payload + str(gtin_check_digit(payload))


# ----------------------------------------------------------------- langue


class Language(str, Enum):
    """Langue d'impression d'un produit JCC (SPEC §2.4).

    ``NA`` (non applicable) est réservé aux accessoires sans texte de jeu (protège-cartes,
    classeur…). Pour un produit de cartes, ``NA`` équivaut à une langue inconnue.
    """

    FR = "FR"
    EN = "EN"
    JP = "JP"
    DE = "DE"
    IT = "IT"
    NA = "NA"
    UNKNOWN = "UNKNOWN"


_LANGUAGE_ALIASES: dict[str, Language] = {}
for _lang, _aliases in {
    Language.FR: (
        "fr", "fra", "fre", "francais", "francaise", "french", "vf", "version francaise",
        "langue francaise", "fr fr", "fr ch", "fr be", "fr ca", "francais fr",
    ),
    Language.EN: (
        "en", "eng", "ang", "anglais", "anglaise", "english", "va", "version anglaise",
        "en gb", "en us", "uk", "us",
    ),
    Language.JP: ("jp", "ja", "jap", "jpn", "japonais", "japonaise", "japanese", "japon", "version japonaise"),
    Language.DE: ("de", "deu", "ger", "allemand", "allemande", "german", "deutsch", "version allemande", "de ch"),
    Language.IT: ("it", "ita", "italien", "italienne", "italian", "italiano", "version italienne"),
    Language.NA: ("n a", "na", "sans objet", "non applicable", "aucune", "multilingue", "multilangue", "multi"),
}.items():
    for _alias in _aliases:
        _LANGUAGE_ALIASES[_alias] = _lang

_LANGUAGE_WORDS: dict[str, Language] = {
    "francais": Language.FR, "francaise": Language.FR, "french": Language.FR, "vf": Language.FR,
    "anglais": Language.EN, "anglaise": Language.EN, "english": Language.EN,
    "japonais": Language.JP, "japonaise": Language.JP, "japanese": Language.JP,
    "allemand": Language.DE, "allemande": Language.DE, "german": Language.DE, "deutsch": Language.DE,
    "italien": Language.IT, "italienne": Language.IT, "italian": Language.IT, "italiano": Language.IT,
}
_LANGUAGE_UPPER_CODES = re.compile(r"(?<![A-Za-z0-9])(FR|VF|EN|ENG|JP|JAP|JPN|DE|IT|ITA)(?![A-Za-z0-9])")
_UPPER_CODE_MAP = {
    "FR": Language.FR, "VF": Language.FR, "EN": Language.EN, "ENG": Language.EN,
    "JP": Language.JP, "JAP": Language.JP, "JPN": Language.JP, "DE": Language.DE,
    "IT": Language.IT, "ITA": Language.IT,
}


def accessory_language(lang: Language) -> Language:
    """Langue d'un accessoire : ``NA`` si absente, inconnue, ``NA`` ou ``FR`` ; une autre langue est conservée.

    Un libellé d'accessoire n'efface jamais une langue étrangère déclarée (« Japonais ») : elle
    reste visible et bloque la publication (langue attendue ``NA``, règle FR uniquement).
    """
    return Language.NA if lang in (Language.UNKNOWN, Language.NA, Language.FR) else lang


def normalize_language(raw: str | None) -> Language:
    """Langue normalisée depuis un libellé libre (``"Français"``, ``"VF"``, ``"JAP"``, ``"ENG"``…).

    Valeur entière reconnue -> sa langue ; sinon mots non ambigus (``"Display … Japonais"``)
    ou codes en MAJUSCULES isolés (``"… – FR"``). Plusieurs langues (``"FR/EN"``), version
    originale (``"VO"``) ou libellé inconnu -> ``UNKNOWN`` (jamais deviné).
    """
    if raw is None:
        return Language.UNKNOWN
    if isinstance(raw, Language):
        return raw
    folded = fold(raw)
    if not folded:
        return Language.UNKNOWN
    if folded in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[folded]
    found: set[Language] = {_LANGUAGE_WORDS[w] for w in folded.split() if w in _LANGUAGE_WORDS}
    found.update(_UPPER_CODE_MAP[m] for m in _LANGUAGE_UPPER_CODES.findall(raw))
    if len(found) == 1:
        return found.pop()
    return Language.UNKNOWN


# ----------------------------------------------------------------- format


class ProductFormat(str, Enum):
    """Format de vente normalisé (identifiants en anglais, libellés FR dans FORMAT_LABELS_FR)."""

    DISPLAY = "DISPLAY"
    HALF_DISPLAY = "HALF_DISPLAY"
    ETB = "ETB"
    BUNDLE = "BUNDLE"
    TRIPACK = "TRIPACK"
    COLLECTION_BOX = "COLLECTION_BOX"
    TIN = "TIN"
    BOOSTER = "BOOSTER"
    SLEEVES = "SLEEVES"
    BINDER = "BINDER"
    DECK_BOX = "DECK_BOX"
    PLAYMAT = "PLAYMAT"
    ACCESSORY = "ACCESSORY"
    UNKNOWN = "UNKNOWN"


ACCESSORY_FORMATS: frozenset[ProductFormat] = frozenset(
    {ProductFormat.SLEEVES, ProductFormat.BINDER, ProductFormat.DECK_BOX, ProductFormat.PLAYMAT, ProductFormat.ACCESSORY}
)
CARD_PRODUCT_FORMATS: frozenset[ProductFormat] = frozenset(
    {
        ProductFormat.DISPLAY,
        ProductFormat.HALF_DISPLAY,
        ProductFormat.ETB,
        ProductFormat.BUNDLE,
        ProductFormat.TRIPACK,
        ProductFormat.COLLECTION_BOX,
        ProductFormat.TIN,
        ProductFormat.BOOSTER,
    }
)

FORMAT_LABELS_FR: dict[ProductFormat, str] = {
    ProductFormat.DISPLAY: "Display",
    ProductFormat.HALF_DISPLAY: "Demi-display",
    ProductFormat.ETB: "Coffret Dresseur d'Élite (ETB)",
    ProductFormat.BUNDLE: "Bundle",
    ProductFormat.TRIPACK: "Tripack",
    ProductFormat.COLLECTION_BOX: "Coffret",
    ProductFormat.TIN: "Pokébox / tin",
    ProductFormat.BOOSTER: "Booster",
    ProductFormat.SLEEVES: "Protège-cartes",
    ProductFormat.BINDER: "Classeur",
    ProductFormat.DECK_BOX: "Boîte de rangement (deck box)",
    ProductFormat.PLAYMAT: "Tapis de jeu",
    ProductFormat.ACCESSORY: "Accessoire",
    ProductFormat.UNKNOWN: "Format inconnu",
}

FORMAT_BUDGET_CATEGORY: dict[ProductFormat, str | None] = {
    ProductFormat.DISPLAY: "displays",
    ProductFormat.HALF_DISPLAY: "displays",
    ProductFormat.ETB: "etb",
    ProductFormat.BUNDLE: "bundles_tripacks",
    ProductFormat.TRIPACK: "bundles_tripacks",
    ProductFormat.COLLECTION_BOX: "coffrets",
    ProductFormat.TIN: "coffrets",
    ProductFormat.BOOSTER: None,  # BP §1 : boosters absents de la répartition du budget (écart signalé)
    ProductFormat.SLEEVES: "accessoires",
    ProductFormat.BINDER: "accessoires",
    ProductFormat.DECK_BOX: "accessoires",
    ProductFormat.PLAYMAT: "accessoires",
    ProductFormat.ACCESSORY: "accessoires",
    ProductFormat.UNKNOWN: None,
}

_TIER_CARD, _TIER_ACCESSORY, _TIER_BOOSTER = 0, 1, 2
_FORMAT_PATTERNS_RAW: tuple[tuple[ProductFormat, int, tuple[str, ...]], ...] = (
    (ProductFormat.HALF_DISPLAY, _TIER_CARD, ("demi display", "half display", "half booster box", "display 18", "display 18 boosters")),
    (
        ProductFormat.ETB,
        _TIER_CARD,
        ("etb", "elite trainer box", "coffret dresseur d elite", "coffret dresseur delite", "dresseur d elite", "coffret etb"),
    ),
    (
        ProductFormat.COLLECTION_BOX,
        _TIER_CARD,
        (
            "coffret", "coffrets", "collection", "collection box", "coffret collection", "collection classeur",
            "collection premium", "premium collection", "ultra premium collection", "coffret premium",
        ),
    ),
    (ProductFormat.TIN, _TIER_CARD, ("tin", "tins", "mini tin", "mini tins", "pokebox", "poke box", "boite metal", "boite metallique")),
    (ProductFormat.BUNDLE, _TIER_CARD, ("bundle", "booster bundle", "lot de boosters")),
    (
        ProductFormat.TRIPACK,
        _TIER_CARD,
        ("tripack", "tri pack", "triple pack", "3 pack", "pack de 3 boosters", "blister 3 boosters", "3 boosters blister"),
    ),
    (
        ProductFormat.DISPLAY,
        _TIER_CARD,
        ("display", "booster box", "boite de boosters", "boite de 36 boosters", "booster display", "display 36", "display 36 boosters"),
    ),
    (
        ProductFormat.SLEEVES,
        _TIER_ACCESSORY,
        ("sleeves", "sleeve", "card sleeves", "protege cartes", "proteges cartes", "protege carte", "pochettes"),
    ),
    (ProductFormat.BINDER, _TIER_ACCESSORY, ("binder", "classeur", "portfolio", "album")),
    (
        ProductFormat.DECK_BOX,
        _TIER_ACCESSORY,
        ("deck box", "deckbox", "boite de rangement", "boite a deck", "boite de deck"),
    ),
    (ProductFormat.PLAYMAT, _TIER_ACCESSORY, ("playmat", "play mat", "tapis de jeu", "tapis")),
    (
        ProductFormat.ACCESSORY,
        _TIER_ACCESSORY,
        ("accessory", "accessoire", "accessoires", "toploader", "toploaders", "top loader"),
    ),
    (ProductFormat.BOOSTER, _TIER_BOOSTER, ("booster", "boosters", "booster pack", "sachet", "sachet de cartes")),
)
# Plus longs d'abord : « coffret dresseur d elite » est consommé avant « coffret ».
_FORMAT_PATTERNS: tuple[tuple[str, ProductFormat, int], ...] = tuple(
    sorted(
        ((p, fmt, tier) for fmt, tier, patterns in _FORMAT_PATTERNS_RAW for p in patterns),
        key=lambda item: (-len(item[0]), item[0]),
    )
)
_AMBIGUOUS_FORMAT_WORDS = ("blister", "pack", "lot", "kit")


def normalize_format(raw: str | None) -> ProductFormat:
    """Format normalisé depuis un libellé libre (``"Coffret Dresseur d'Élite"`` -> ``ETB``).

    Les motifs les plus longs sont consommés d'abord. Un format de produit de cartes
    l'emporte sur une mention d'accessoire (« ETB … + sleeves » = ETB) ou de booster
    (« Display 36 boosters » = DISPLAY). Deux formats de cartes distincts, un « blister »
    ou un « pack » sans précision -> ``UNKNOWN`` (jamais deviné). Un accessoire **accompagné de
    boosters** (« Classeur + 2 boosters ») contient des cartes : ``UNKNOWN`` (jamais un accessoire
    « sans langue », qui échapperait à la règle FR uniquement).
    """
    if raw is None:
        return ProductFormat.UNKNOWN
    if isinstance(raw, ProductFormat):
        return raw
    text = f" {fold(raw)} "
    if not text.strip():
        return ProductFormat.UNKNOWN
    found: dict[int, set[ProductFormat]] = {_TIER_CARD: set(), _TIER_ACCESSORY: set(), _TIER_BOOSTER: set()}
    for pattern, fmt, tier in _FORMAT_PATTERNS:
        needle = f" {pattern} "
        while needle in text:
            found[tier].add(fmt)
            text = text.replace(needle, " | ", 1)
    cards = found[_TIER_CARD]
    if cards:
        return cards.pop() if len(cards) == 1 else ProductFormat.UNKNOWN
    accessories = found[_TIER_ACCESSORY]
    if accessories and found[_TIER_BOOSTER]:
        return ProductFormat.UNKNOWN  # accessoire + boosters : cartes incluses, format ambigu
    if len(accessories) > 1:
        accessories.discard(ProductFormat.ACCESSORY)
    if accessories:
        return accessories.pop() if len(accessories) == 1 else ProductFormat.UNKNOWN
    if any(_contains(text, word) for word in _AMBIGUOUS_FORMAT_WORDS):
        return ProductFormat.UNKNOWN
    if found[_TIER_BOOSTER]:
        return ProductFormat.BOOSTER
    return ProductFormat.UNKNOWN


def _as_format(value: ProductFormat | str | None) -> ProductFormat:
    if value is None:
        return ProductFormat.UNKNOWN
    if isinstance(value, ProductFormat):
        return value
    try:
        return ProductFormat(value)
    except ValueError:
        return normalize_format(value)


def is_accessory(fmt: ProductFormat | str | None) -> bool:
    """Vrai pour un accessoire (protège-cartes, classeur, deck box, tapis, autre)."""
    return _as_format(fmt) in ACCESSORY_FORMATS


def expected_language_for(fmt: ProductFormat | str | None) -> str:
    """Langue attendue par :func:`pokeshop.pricing.evaluate_offer` : ``NA`` pour un accessoire, sinon ``FR``.

    Les accessoires sont normalisés en langue ``NA`` (sans objet) par :func:`normalize_identity`
    et par les importeurs : la clé d'identité est la même chez tous les fournisseurs.
    """
    return Language.NA.value if is_accessory(fmt) else Language.FR.value


# ---------------------------------------------------------------- contenu

_BOOSTER_COUNT_PATTERNS = (
    re.compile(r"\b(\d{1,3})\s*X\s*BOOSTERS?\b"),
    re.compile(r"\bX\s*(\d{1,3})\s*BOOSTERS?\b"),
    re.compile(r"\bBOOSTERS?\s*X\s*(\d{1,3})\b"),
    re.compile(r"\b(\d{1,3})\s*BOOSTERS?\b"),
)
_CONTENT_NOISE = re.compile(r"[^0-9A-Z+]+")


def _upper_fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.replace("×", "x"))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def booster_count(raw: str | None) -> int | None:
    """Nombre de boosters annoncé (``"36 boosters"``, ``"x36 boosters"``, ``"Boosters x 6"``).

    ``None`` si absent ou si plusieurs nombres différents sont annoncés (ambigu).
    """
    if not raw:
        return None
    text = _upper_fold(raw)
    counts: set[int] = set()
    for pattern in _BOOSTER_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            counts.add(int(match.group(1)))
        text = pattern.sub(" ", text)
    counts.discard(0)
    return counts.pop() if len(counts) == 1 else None


def normalize_content(raw: str | None) -> str | None:
    """Contenu canonique pour la clé d'identité.

    Si un nombre unique de boosters est annoncé, la signature ``"N BOOSTERS"`` (``"1 BOOSTER"``)
    suffit (le GTIN distingue les variantes) ; sinon texte en majuscules sans accents ni
    ponctuation (``+`` conservé). Idempotent.
    """
    if raw is None:
        return None
    text = _upper_fold(raw)
    if not text.strip():
        return None
    count = booster_count(raw)
    if count is not None:
        return "1 BOOSTER" if count == 1 else f"{count} BOOSTERS"
    cleaned = _CONTENT_NOISE.sub(" ", text).replace("+", " + ")
    result = " ".join(cleaned.split())
    return result or None


# -------------------------------------------------------------- extensions

NO_EXTENSION = "SANS_EXTENSION"
"""Extension d'un accessoire générique (non rattaché à une extension)."""

EXTENSIONS_ENV_VAR = "POKESHOP_EXTENSIONS_PATH"
DEFAULT_EXTENSIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "extensions_aliases.yaml"

_NO_EXTENSION_ALIASES = frozenset({"", "n a", "na", "aucune", "sans", "sans extension", "sans objet", "generique", "none"})
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,31}$")


class SourceRef(FrozenModel):
    """Source publique datée justifiant une entrée de la table."""

    url: str = Field(min_length=8)
    consulte_le: date

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("URL de source en https:// attendue")
        return v


class ExtensionEntry(FrozenModel):
    """Extension connue : code canonique, nom FR, alias, sources (ou marquage FICTIF)."""

    code: str
    name_fr: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    officiel: bool = False
    release_date_fr: date | None = None
    verification: str = ""
    sources: tuple[SourceRef, ...] = ()
    fictif: bool = False

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not _CODE_RE.match(v):
            raise ValueError(f"code d'extension invalide : {v!r}")
        return v

    def folded_aliases(self) -> tuple[str, ...]:
        """Alias repliés, code et nom FR compris, sans doublon."""
        seen: dict[str, None] = {}
        for alias in (self.code, self.name_fr, *self.aliases):
            folded = fold(alias)
            if folded:
                seen[folded] = None
        return tuple(seen)


class ExtensionMatch(FrozenModel):
    """Résultat de la reconnaissance d'une extension dans un libellé."""

    code: str | None
    ambiguous: bool = False
    candidates: tuple[str, ...] = ()
    matched_alias: str | None = None


class ExtensionTable:
    """Table d'alias d'extensions (immuable après construction)."""

    def __init__(self, entries: Iterable[ExtensionEntry], *, sources: Sequence[str] = ()) -> None:
        self._entries: dict[str, ExtensionEntry] = {}
        self._aliases: dict[str, str] = {}
        self.sources: tuple[str, ...] = tuple(sources)
        errors: list[str] = []
        for entry in entries:
            if entry.code == NO_EXTENSION:
                errors.append(f"{NO_EXTENSION} est réservé")
                continue
            if entry.code in self._entries:
                errors.append(f"code en double : {entry.code}")
                continue
            if entry.fictif and not entry.code.startswith("FICTIF_"):
                errors.append(f"{entry.code} : une entrée fictive doit commencer par FICTIF_")
            if not entry.fictif and not entry.sources:
                errors.append(f"{entry.code} : extension réelle sans source datée (interdit)")
            if not entry.fictif and entry.code.startswith("FICTIF_"):
                errors.append(f"{entry.code} : préfixe FICTIF_ réservé aux entrées fictives")
            self._entries[entry.code] = entry
            for alias in entry.folded_aliases():
                if alias in _NO_EXTENSION_ALIASES:
                    errors.append(f"{entry.code} : alias réservé {alias!r}")
                owner = self._aliases.get(alias)
                if owner is not None and owner != entry.code:
                    errors.append(f"alias {alias!r} partagé par {owner} et {entry.code}")
                self._aliases[alias] = entry.code
        if errors:
            raise CatalogError("Table d'extensions invalide : " + " ; ".join(errors))
        # Alias les plus longs d'abord pour la recherche dans un libellé.
        self._sorted_aliases = sorted(self._aliases.items(), key=lambda kv: (-len(kv[0]), kv[0]))

    @classmethod
    def from_data(cls, data: Any, *, source: str = "<data>") -> ExtensionTable:
        """Construit la table depuis un document YAML déjà chargé."""
        if not isinstance(data, Mapping) or not isinstance(data.get("extensions"), list):
            raise CatalogError(f"{source} : clé 'extensions' (liste) attendue")
        entries: list[ExtensionEntry] = []
        for i, raw in enumerate(data["extensions"]):
            try:
                entries.append(ExtensionEntry.model_validate(raw))
            except ValidationError as exc:
                raise CatalogError(f"{source} : extension n°{i + 1} invalide : {exc}") from exc
        return cls(entries, sources=(source,))

    @classmethod
    def load(cls, paths: str | Path | Sequence[str | Path]) -> ExtensionTable:
        """Charge et fusionne un ou plusieurs fichiers YAML (doublons de code refusés)."""
        items = [paths] if isinstance(paths, (str, Path)) else list(paths)
        entries: list[ExtensionEntry] = []
        names: list[str] = []
        for item in items:
            path = Path(item)
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                raise CatalogError(f"{path} : lecture impossible ({exc})") from exc
            entries.extend(cls.from_data(data, source=str(path)).entries)
            names.append(str(path))
        return cls(entries, sources=names)

    @property
    def entries(self) -> tuple[ExtensionEntry, ...]:
        """Entrées de la table, dans l'ordre de chargement."""
        return tuple(self._entries.values())

    @property
    def codes(self) -> frozenset[str]:
        """Codes canoniques connus (hors ``SANS_EXTENSION``)."""
        return frozenset(self._entries)

    def get(self, code: str) -> ExtensionEntry | None:
        """Entrée d'un code, ou ``None``."""
        return self._entries.get(code)

    def name_fr(self, code: str) -> str | None:
        """Nom FR d'un code (``None`` pour ``SANS_EXTENSION`` ou un code inconnu)."""
        entry = self._entries.get(code)
        return entry.name_fr if entry else None

    def merged(self, other: ExtensionTable) -> ExtensionTable:
        """Nouvelle table fusionnant ``self`` et ``other``."""
        return ExtensionTable((*self.entries, *other.entries), sources=(*self.sources, *other.sources))

    def match(self, raw: str | None) -> ExtensionMatch:
        """Reconnaît une extension : alias exact, sinon alias contenu dans le libellé.

        Seules les correspondances maximales comptent (« Méga-Évolution Nuit Noire » contient
        « Nuit Noire », même code). Deux extensions différentes -> ambigu, ``code=None``.
        """
        if raw is None:
            return ExtensionMatch(code=None)
        folded = fold(raw)
        if not folded:
            return ExtensionMatch(code=None)
        exact = self._aliases.get(folded)
        if exact is not None:
            return ExtensionMatch(code=exact, candidates=(exact,), matched_alias=folded)
        text = f" {folded} "
        spans: list[tuple[int, int, str, str]] = []
        for alias, code in self._sorted_aliases:
            needle = f" {alias} "
            start = text.find(needle)
            while start != -1:
                end = start + len(needle)
                if not any(s <= start and end <= e for s, e, _, _ in spans):
                    spans.append((start, end, code, alias))
                start = text.find(needle, start + 1)
        codes = tuple(dict.fromkeys(code for _, _, code, _ in spans))
        if len(codes) == 1:
            best = max(spans, key=lambda s: s[1] - s[0])
            return ExtensionMatch(code=codes[0], candidates=codes, matched_alias=best[3])
        return ExtensionMatch(code=None, ambiguous=len(codes) > 1, candidates=codes)

    def normalize(self, raw: str | None) -> str | None:
        """Code canonique, ``None`` si inconnu ou ambigu (=> brouillon)."""
        return self.match(raw).code


def _default_extension_paths() -> list[Path]:
    env = os.environ.get(EXTENSIONS_ENV_VAR)
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    return [DEFAULT_EXTENSIONS_PATH]


@lru_cache(maxsize=16)
def _load_cached(key: tuple[tuple[str, int], ...]) -> ExtensionTable:
    return ExtensionTable.load([path for path, _ in key])


def load_extension_table(paths: str | Path | Sequence[str | Path] | None = None) -> ExtensionTable:
    """Table d'alias (par défaut ``data/extensions_aliases.yaml`` ou ``$POKESHOP_EXTENSIONS_PATH``).

    Mise en cache par chemin et date de modification : une table modifiée est relue.
    """
    items = _default_extension_paths() if paths is None else ([paths] if isinstance(paths, (str, Path)) else list(paths))
    key: list[tuple[str, int]] = []
    for item in items:
        path = Path(item).resolve()
        try:
            key.append((str(path), path.stat().st_mtime_ns))
        except OSError as exc:
            raise CatalogError(f"{path} : table d'extensions introuvable ({exc})") from exc
    return _load_cached(tuple(key))


def normalize_extension(
    raw: str | None,
    table: ExtensionTable | None = None,
    *,
    fmt: ProductFormat | str | None = None,
) -> str | None:
    """Code d'extension canonique ou ``None`` (inconnu/ambigu => brouillon).

    Pour un accessoire (``fmt``), un libellé vide ou « aucune » donne ``SANS_EXTENSION`` ;
    pour un produit de cartes, ``SANS_EXTENSION`` est refusé (``None``).
    """
    if is_accessory(fmt) and fold(raw or "") in _NO_EXTENSION_ALIASES:
        return NO_EXTENSION
    tbl = table if table is not None else load_extension_table()
    return tbl.normalize(raw)


# ---------------------------------------------------------------- identité


class IdentityIssue(str, Enum):
    """Motifs d'identité incomplète ou douteuse (codes stables)."""

    MISSING_GTIN = "MISSING_GTIN"
    INVALID_GTIN = "INVALID_GTIN"
    CASE_LEVEL_GTIN = "CASE_LEVEL_GTIN"
    UNKNOWN_LANGUAGE = "UNKNOWN_LANGUAGE"
    LANGUAGE_NOT_APPLICABLE = "LANGUAGE_NOT_APPLICABLE"
    UNKNOWN_EXTENSION = "UNKNOWN_EXTENSION"
    AMBIGUOUS_EXTENSION = "AMBIGUOUS_EXTENSION"
    UNKNOWN_FORMAT = "UNKNOWN_FORMAT"
    MISSING_CONTENT = "MISSING_CONTENT"
    UNKNOWN_SEALED = "UNKNOWN_SEALED"
    NOT_SEALED = "NOT_SEALED"


IDENTITY_ISSUE_LABELS_FR: dict[IdentityIssue, str] = {
    IdentityIssue.MISSING_GTIN: "GTIN/EAN absent : identité non confirmable, brouillon.",
    IdentityIssue.INVALID_GTIN: "GTIN invalide (checksum GS1 ou longueur) : brouillon.",
    IdentityIssue.CASE_LEVEL_GTIN: "GTIN-14 de carton : il ne désigne pas l'unité vendue.",
    IdentityIssue.UNKNOWN_LANGUAGE: "Langue inconnue ou multiple : brouillon.",
    IdentityIssue.LANGUAGE_NOT_APPLICABLE: "« Sans langue » réservé aux accessoires : langue inconnue.",
    IdentityIssue.UNKNOWN_EXTENSION: "Extension absente de la table d'alias : brouillon.",
    IdentityIssue.AMBIGUOUS_EXTENSION: "Libellé citant plusieurs extensions : brouillon.",
    IdentityIssue.UNKNOWN_FORMAT: "Format inconnu ou ambigu : brouillon.",
    IdentityIssue.MISSING_CONTENT: "Contenu non annoncé : brouillon.",
    IdentityIssue.UNKNOWN_SEALED: "État (scellé ou non) inconnu : brouillon.",
    IdentityIssue.NOT_SEALED: "Produit non scellé : hors périmètre de lancement (BP).",
}


class NormalizedIdentity(FrozenModel):
    """Identité normalisée + motifs d'incomplétude (vide = identité complète et scellée)."""

    identity: ProductIdentity
    issues: tuple[IdentityIssue, ...] = ()

    @property
    def key(self) -> str:
        """Clé canonique ``GTIN|LANGUE|EXTENSION|FORMAT|CONTENU|SCELLÉ``."""
        return self.identity.key

    @property
    def is_complete(self) -> bool:
        """Vrai si aucun motif bloquant (identité publiable si le produit est validé)."""
        return not self.issues

    @property
    def format(self) -> ProductFormat:
        """Format normalisé (``UNKNOWN`` si absent)."""
        return _as_format(self.identity.format)


def normalize_identity(
    *,
    gtin: str | int | None = None,
    language: str | None = None,
    extension: str | None = None,
    format: str | None = None,  # noqa: A002 - nom métier du BP
    content: str | None = None,
    sealed: bool | None = None,
    table: ExtensionTable | None = None,
) -> NormalizedIdentity:
    """Normalise les six éléments d'identité et liste les motifs de brouillon."""
    issues: list[IdentityIssue] = []
    fmt = normalize_format(format)
    accessory = fmt in ACCESSORY_FORMATS
    norm_gtin = normalize_gtin(gtin)
    if clean_gtin(gtin) is None:
        issues.append(IdentityIssue.MISSING_GTIN)
    elif norm_gtin is None:
        issues.append(IdentityIssue.INVALID_GTIN)
    elif is_case_level_gtin(norm_gtin):
        issues.append(IdentityIssue.CASE_LEVEL_GTIN)
    lang = normalize_language(language)
    if accessory:
        # Accessoire : langue sans objet (clé identique chez tous les fournisseurs), SAUF langue de cartes
        # fournie autre que FR : conservée, elle bloque la publication (règle FR uniquement).
        lang = accessory_language(lang)
    elif lang is Language.NA:
        issues.append(IdentityIssue.LANGUAGE_NOT_APPLICABLE)
        lang = Language.UNKNOWN
    elif lang is Language.UNKNOWN:
        issues.append(IdentityIssue.UNKNOWN_LANGUAGE)
    tbl = table if table is not None else load_extension_table()
    ext = normalize_extension(extension, tbl, fmt=fmt)
    if ext is None:
        ambiguous = extension is not None and tbl.match(extension).ambiguous
        issues.append(IdentityIssue.AMBIGUOUS_EXTENSION if ambiguous else IdentityIssue.UNKNOWN_EXTENSION)
    if fmt is ProductFormat.UNKNOWN:
        issues.append(IdentityIssue.UNKNOWN_FORMAT)
    norm_content = normalize_content(content)
    if norm_content is None:
        issues.append(IdentityIssue.MISSING_CONTENT)
    if sealed is None:
        issues.append(IdentityIssue.UNKNOWN_SEALED)
    elif sealed is False:
        issues.append(IdentityIssue.NOT_SEALED)
    identity = ProductIdentity(
        gtin=norm_gtin,
        language=lang.value,
        extension=ext,
        format=None if fmt is ProductFormat.UNKNOWN else fmt.value,
        content=norm_content,
        sealed=sealed,
    )
    return NormalizedIdentity(identity=identity, issues=tuple(issues))


def _identity_fields(source: ProductIdentity | SupplierOffer | Mapping[str, Any]) -> dict[str, Any]:
    names = ("gtin", "language", "extension", "format", "content", "sealed")
    if isinstance(source, SupplierOffer):
        source = source.identity()
    if isinstance(source, ProductIdentity):
        return {n: getattr(source, n) for n in names}
    if isinstance(source, Mapping):
        unknown = set(source) - set(names)
        if unknown:
            raise CatalogError(f"champs d'identité inconnus : {sorted(unknown)}")
        return {n: source.get(n) for n in names}
    raise TypeError(f"identité attendue, reçu {type(source).__name__}")


def product_identity_key(
    source: ProductIdentity | SupplierOffer | Mapping[str, Any],
    table: ExtensionTable | None = None,
) -> str:
    """Clé d'identité canonique (``?`` = élément inconnu) après normalisation des six éléments."""
    return normalize_identity(**_identity_fields(source), table=table).key


def product_title_fr(identity: ProductIdentity, table: ExtensionTable | None = None) -> str | None:
    """Titre exact BP §7 : format + extension + langue (``None`` si identité incomplète)."""
    if not identity.is_complete or identity.format is None or identity.extension is None:
        return None
    fmt = _as_format(identity.format)
    parts = [FORMAT_LABELS_FR[fmt]]
    if identity.extension != NO_EXTENSION:
        tbl = table if table is not None else load_extension_table()
        name = tbl.name_fr(identity.extension)
        if name is None:
            return None
        parts.append(name)
    title = " ".join(parts)
    if identity.language != Language.NA.value:
        title += f" – {identity.language}"
    return title


# ------------------------------------------------------------- rapprochement


class SupplierLink(FrozenModel):
    """Lien SKU fournisseur ↔ produit du catalogue."""

    supplier_id: str = Field(min_length=1)
    supplier_sku: str = Field(min_length=1)


class CatalogProduct(FrozenModel):
    """Produit connu du catalogue central (identité déjà normalisée ou brute)."""

    product_id: str = Field(min_length=1)
    identity: ProductIdentity
    supplier_links: tuple[SupplierLink, ...] = ()


class MatchStatus(str, Enum):
    """Issue du rapprochement offre ↔ produit."""

    MATCHED = "MATCHED"
    NEW_DRAFT = "NEW_DRAFT"
    AMBIGUOUS = "AMBIGUOUS"


class MatchResult(FrozenModel):
    """Résultat du rapprochement. Seul ``MATCHED`` peut alimenter une fiche existante."""

    status: MatchStatus
    identity: ProductIdentity
    identity_key: str
    product_id: str | None = None
    candidates: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    issues: tuple[IdentityIssue, ...] = ()

    @property
    def is_draft(self) -> bool:
        """Vrai si la référence reste en brouillon (NEW_DRAFT ou AMBIGUOUS)."""
        return self.status is not MatchStatus.MATCHED

    @property
    def can_update_existing(self) -> bool:
        """Vrai si l'offre peut mettre à jour la fiche du produit rapproché."""
        return self.status is MatchStatus.MATCHED


_REASON_EXACT = "EXACT_IDENTITY"
_REASON_LINK = "SUPPLIER_LINK_CONFIRMED"
_REASON_NEW = "NEW_REFERENCE"
_REASON_GTIN_CONFLICT = "GTIN_CONFLICT"
_REASON_LINK_CONFLICT = "SUPPLIER_LINK_CONFLICT"
_REASON_SAME_NAME = "SAME_NAME_DIFFERENT_CONTENT"
_REASON_PARTIAL = "PARTIAL_IDENTITY_MATCH"
_REASON_MULTIPLE = "MULTIPLE_CANDIDATES"


class CatalogIndex:
    """Index du catalogue (identités normalisées) pour des rapprochements rapides."""

    def __init__(self, products: Iterable[CatalogProduct], table: ExtensionTable | None = None) -> None:
        self.table = table if table is not None else load_extension_table()
        self._products: dict[str, CatalogProduct] = {}
        self._normalized: dict[str, NormalizedIdentity] = {}
        self._by_key: dict[str, list[str]] = {}
        self._by_gtin: dict[str, list[str]] = {}
        self._by_name: dict[tuple[str | None, str | None, str | None], list[str]] = {}
        self._by_link: dict[tuple[str, str], list[str]] = {}
        for product in products:
            if product.product_id in self._products:
                raise CatalogError(f"product_id en double : {product.product_id}")
            norm = normalize_identity(**_identity_fields(product.identity), table=self.table)
            pid = product.product_id
            self._products[pid] = product
            self._normalized[pid] = norm
            ident = norm.identity
            self._by_key.setdefault(norm.key, []).append(pid)
            if ident.gtin is not None:
                self._by_gtin.setdefault(ident.gtin, []).append(pid)
            self._by_name.setdefault((ident.language, ident.extension, ident.format), []).append(pid)
            for link in product.supplier_links:
                self._by_link.setdefault((link.supplier_id, link.supplier_sku), []).append(pid)

    def __len__(self) -> int:
        return len(self._products)

    def product(self, product_id: str) -> CatalogProduct:
        """Produit par identifiant (KeyError si inconnu)."""
        return self._products[product_id]

    def normalized(self, product_id: str) -> NormalizedIdentity:
        """Identité normalisée d'un produit."""
        return self._normalized[product_id]

    def by_key(self, key: str) -> tuple[str, ...]:
        """Produits d'identité exactement ``key``."""
        return tuple(self._by_key.get(key, ()))

    def by_gtin(self, gtin: str) -> tuple[str, ...]:
        """Produits portant ce GTIN (canonique)."""
        return tuple(self._by_gtin.get(gtin, ()))

    def by_name(self, language: str | None, extension: str | None, fmt: str | None) -> tuple[str, ...]:
        """Produits de même « nom » : même langue, extension et format."""
        return tuple(self._by_name.get((language, extension, fmt), ()))

    def by_link(self, supplier_id: str, supplier_sku: str) -> tuple[str, ...]:
        """Produits liés à ce SKU fournisseur."""
        return tuple(self._by_link.get((supplier_id, supplier_sku), ()))

    def agreeing(self, ident: ProductIdentity) -> tuple[str, ...]:
        """Produits compatibles avec tous les éléments **connus** de ``ident`` (au moins extension et format)."""
        if ident.extension is None or ident.format is None:
            return ()
        language_known = ident.language not in (None, Language.UNKNOWN.value)
        out: list[str] = []
        for (language, extension, fmt), pids in self._by_name.items():
            if extension != ident.extension or fmt != ident.format:
                continue
            if language_known and language != ident.language:
                continue
            for pid in pids:
                other = self._normalized[pid].identity
                if ident.gtin is not None and other.gtin != ident.gtin:
                    continue
                if ident.content is not None and other.content != ident.content:
                    continue
                if ident.sealed is not None and other.sealed != ident.sealed:
                    continue
                out.append(pid)
        return tuple(out)


def match_offer_to_product(
    offer: SupplierOffer | ProductIdentity,
    catalog: CatalogIndex | Iterable[CatalogProduct],
    *,
    table: ExtensionTable | None = None,
    supplier_id: str | None = None,
    supplier_sku: str | None = None,
) -> MatchResult:
    """Rapproche une offre (ou une identité) du catalogue : MATCHED | NEW_DRAFT | AMBIGUOUS.

    * ``MATCHED`` : identité complète et scellée, égale à un seul produit, sans conflit de GTIN
      ni de lien fournisseur.
    * ``AMBIGUOUS`` : même GTIN mais identité différente, même nom (langue + extension +
      format) mais contenu différent, SKU fournisseur lié à un autre produit, ou identité
      incomplète compatible avec un produit existant.
    * ``NEW_DRAFT`` : aucune correspondance (nouvelle référence => brouillon, BP §6).
    """
    index = catalog if isinstance(catalog, CatalogIndex) else CatalogIndex(catalog, table)
    tbl = table if table is not None else index.table
    if isinstance(offer, SupplierOffer):
        supplier_id = supplier_id or offer.supplier_id
        supplier_sku = supplier_sku or offer.supplier_sku
    norm = normalize_identity(**_identity_fields(offer), table=tbl)
    ident = norm.identity
    key = norm.key
    reasons: list[str] = []
    linked = index.by_link(supplier_id, supplier_sku) if supplier_id and supplier_sku else ()
    same_gtin = index.by_gtin(ident.gtin) if ident.gtin is not None else ()

    def result(status: MatchStatus, product_id: str | None = None, candidates: Iterable[str] = ()) -> MatchResult:
        return MatchResult(
            status=status,
            identity=ident,
            identity_key=key,
            product_id=product_id,
            candidates=tuple(dict.fromkeys(candidates)),
            reasons=tuple(dict.fromkeys(reasons)),
            issues=norm.issues,
        )

    if norm.is_complete:
        exact = index.by_key(key)
        if len(exact) > 1:
            reasons.append(_REASON_MULTIPLE)
            return result(MatchStatus.AMBIGUOUS, candidates=exact)
        if len(exact) == 1:
            pid = exact[0]
            gtin_conflicts = [p for p in same_gtin if p != pid]
            link_conflicts = [p for p in linked if p != pid]
            if gtin_conflicts:
                reasons.append(_REASON_GTIN_CONFLICT)
            if link_conflicts:
                reasons.append(_REASON_LINK_CONFLICT)
            if gtin_conflicts or link_conflicts:
                return result(MatchStatus.AMBIGUOUS, candidates=[pid, *gtin_conflicts, *link_conflicts])
            reasons.append(_REASON_EXACT)
            if pid in linked:
                reasons.append(_REASON_LINK)
            return result(MatchStatus.MATCHED, product_id=pid, candidates=[pid])
        same_name = [
            p for p in index.by_name(ident.language, ident.extension, ident.format)
            if index.normalized(p).identity.content != ident.content
        ]
        if same_gtin:
            reasons.append(_REASON_GTIN_CONFLICT)
        if linked:
            reasons.append(_REASON_LINK_CONFLICT)
        if same_name:
            reasons.append(_REASON_SAME_NAME)
        if same_gtin or linked or same_name:
            return result(MatchStatus.AMBIGUOUS, candidates=[*same_gtin, *linked, *same_name])
        reasons.append(_REASON_NEW)
        return result(MatchStatus.NEW_DRAFT)

    reasons.extend(issue.value for issue in norm.issues)
    agreeing = index.agreeing(ident)
    gtin_conflicts = [p for p in same_gtin if p not in agreeing]
    if gtin_conflicts:
        reasons.append(_REASON_GTIN_CONFLICT)
    if linked:
        reasons.append(_REASON_LINK_CONFLICT if any(p not in agreeing for p in linked) else _REASON_PARTIAL)
    if agreeing:
        reasons.append(_REASON_PARTIAL)
    candidates = [*agreeing, *gtin_conflicts, *linked]
    if candidates:
        return result(MatchStatus.AMBIGUOUS, candidates=candidates)
    reasons.append(_REASON_NEW)
    return result(MatchStatus.NEW_DRAFT)
