"""Construction des charges ``productSet`` publiques depuis le catalogue validé (agent integrations).

Principes (BP §5-§7, SPEC §0.2 et §2.6) :

* **Liste blanche stricte** (:data:`PRODUCT_INPUT_SCHEMA`) : titre exact (format + extension +
  langue), description, images autorisées, prix CHF, SKU boutique, code-barres, statut
  ``DRAFT`` / ``ACTIVE``, SEO, métachamps ``boutique.*`` et tags miroirs **exactement** comme
  le contrat du thème (``site/shopify/STRUCTURE_BOUTIQUE.md`` §2 : statut de stock, langue,
  extension, format, contenu validé, date de sortie et statut, délai, quantité maximale,
  alerte réassort, fin de série ; tags ``statut:*``, ``ext:<slug>``, ``nouveaute``,
  ``cadeau``). Tout autre champ est refusé par :func:`assert_no_sensitive_fields`, appelée à la
  construction **et** par le client Shopify avant tout envoi.
* Aucune donnée de coût, marge, fournisseur, prix B2B ni donnée personnelle (clés et valeurs
  analysées ; termes internes fournis par l'appelant : identifiants et SKU fournisseurs).
* Aucun stock dans la fiche : la quantité passe uniquement par ``inventorySetQuantities`` avec
  contrôle de concurrence ; ``inventoryPolicy = DENY`` (aucune vente à découvert).
* **Nouvelle référence -> brouillon.** Publication automatique (niveau 3) seulement si la règle
  de catégorie est validée, tous les champs présents, les droits d'images acquis, le contenu
  validé et la décision de prix ``OK`` (BP §6).
* **Prix** : celui de la décision ``OK`` du moteur (ou validé par une personne) ; variation au-delà
  du plafond journalier (5 %) ou ×10 : aucun nouveau prix sans validation ; décision ``DRAFT``
  ou ``BLOCKED`` : aucun nouveau prix public. Ce module ne produit **aucune** écriture de
  commande : le prix d'une commande conclue n'est jamais modifié (il est figé dans ses lignes).
* Référence en quarantaine ou bloquée par le stop-loss produit : dépubliée (brouillon), dernier
  prix validé conservé.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .catalog import (
    FORMAT_LABELS_FR,
    NO_EXTENSION,
    CatalogError,
    ExtensionTable,
    ProductFormat,
    expected_language_for,
    is_fictitious_gtin,
    product_title_fr,
    validate_gtin,
)
from .errors import PokeshopError
from .models import AvailabilityPromise, DecisionStatus, FrozenModel, PriceDecision, ProductIdentity, PromiseKind
from .pricing import is_price_anomaly, q2

__all__ = [
    "PUBLIC_METAFIELD_NAMESPACE",
    "PUBLIC_METAFIELDS",
    "PRODUCT_INPUT_SCHEMA",
    "SENSITIVE_KEY_FRAGMENTS",
    "PublishError",
    "SensitiveFieldError",
    "ImageRights",
    "PublicImage",
    "StockStatus",
    "stock_status_from_promise",
    "ReleaseDateStatus",
    "ShopStatus",
    "CatalogListing",
    "PriceValidation",
    "PublishBlocker",
    "BLOCKER_LABELS_FR",
    "PlanOutcome",
    "PublicationPlan",
    "assert_no_sensitive_fields",
    "assert_metafields_public",
    "sensitive_violations",
    "forbidden_claims",
    "slugify",
    "build_publication",
]

PUBLIC_METAFIELD_NAMESPACE = "boutique"
"""Espace de noms lu par le thème (``site/shopify/STRUCTURE_BOUTIQUE.md`` §2)."""
PUBLIC_METAFIELDS: dict[str, str] = {
    "statut_stock": "single_line_text_field",
    "langue": "single_line_text_field",
    "extension": "single_line_text_field",
    "format": "single_line_text_field",
    "contenu_valide": "multi_line_text_field",
    "date_sortie": "date",
    "date_sortie_statut": "single_line_text_field",
    "delai_expedition": "single_line_text_field",
    "quantite_max": "number_integer",
    "alerte_reassort": "boolean",
    "fin_de_serie": "boolean",
}
"""Seuls métachamps publiables (clé -> type Shopify), contrat du thème."""

_S = "str"
_B = "bool"
PRODUCT_INPUT_SCHEMA: dict[str, Any] = {
    "title": _S,
    "handle": _S,
    "status": _S,
    "descriptionHtml": _S,
    "productType": _S,
    "tags": [_S],
    "productOptions": [{"name": _S, "values": [{"name": _S}]}],
    "variants": [
        {
            "optionValues": [{"optionName": _S, "name": _S}],
            "price": _S,
            "barcode": _S,
            "inventoryPolicy": _S,
            "inventoryItem": {"sku": _S, "tracked": _B},
        }
    ],
    "files": [{"originalSource": _S, "alt": _S, "contentType": _S}],
    "metafields": [{"namespace": _S, "key": _S, "type": _S, "value": _S}],
    "seo": {"title": _S, "description": _S},
}
"""Structure exacte autorisée d'un ``ProductSetInput`` public (toute autre clé = violation)."""

SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "cost",
    "cout",
    "marg",
    "supplier",
    "fournisseur",
    "b2b",
    "purchase",
    "achat",
    "landed",
    "contribution",
    "floor",
    "plancher",
    "wholesale",
    "grossiste",
    "profit",
    "vendor",
    "internal",
    "interne",
    "unitcost",
    "fx",
    "invoice",
    "facture",
    "customer",
    "client",
    "email",
    "phone",
    "telephone",
    "address",
    "adresse",
)
"""Fragments de nom de clé révélant une donnée interne ou personnelle (comparaison sans accents ni casse)."""

_SENSITIVE_VALUE_RE = re.compile(
    r"\b(prix\s+d\W?achat|prix\s+net|couts?|marges?|margins?|fournisseurs?|grossistes?|b2b|wholesale|landed|"
    r"contributions?|costs?|suppliers?|purchase|prix\s+plancher|coefficient)\b"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(\+41|0041|0)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}(?!\d)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b")
_PRICE_RE = re.compile(r"^\d{1,6}\.\d{2}$")
_HANDLE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TAG_RE = re.compile(r"^(statut:(stock-local|precommande|rupture)|ext:[a-z0-9]+(-[a-z0-9]+)*|nouveaute|cadeau)$")
_SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,60}$")
_UNSAFE_HTML_RE = re.compile(r"<\s*(script|iframe|object|embed|form)|javascript:|\son\w+\s*=", re.IGNORECASE)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_CLAIMS: tuple[str, ...] = (
    "investissement",
    "investir",
    "placement",
    "valeur future",
    "prendra de la valeur",
    "plus-value",
    "plus value",
    "rentabilite garantie",
    "carte rare garantie",
    "hit garanti",
    "rare garanti",
    "boutique officielle",
    "revendeur officiel",
    "partenaire officiel",
    "distributeur officiel",
    "stock illimite",
)
"""Promesses interdites (BP §7 : ni carte rare ni valeur financière promises ; BP §8 : pas de statut officiel)."""


class PublishError(PokeshopError, ValueError):
    """Charge de publication invalide."""


class SensitiveFieldError(PublishError):
    """Champ interne, sensible ou hors liste blanche dans une charge publique (SPEC §2.6)."""

    def __init__(self, violations: Sequence[str]) -> None:
        self.violations = tuple(violations)
        super().__init__("Charge publique refusée : " + " ; ".join(self.violations))


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def _key_fold(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(key))


def slugify(text: str) -> str:
    """Handle Shopify : minuscules ASCII, chiffres et tirets."""
    slug = re.sub(r"[^a-z0-9]+", "-", _fold(text)).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:200].strip("-")


def forbidden_claims(*texts: str | None) -> list[str]:
    """Promesses interdites trouvées dans les textes publics (vide = conforme)."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        folded = _fold(_TAG_STRIP_RE.sub(" ", text))
        for claim in _CLAIMS:
            if claim in folded and claim not in found:
                found.append(claim)
    return found


def _scan_value(value: str, path: str, terms: Sequence[str], out: list[str]) -> None:
    folded = _fold(value)
    plain = _fold(_TAG_STRIP_RE.sub(" ", value))
    match = _SENSITIVE_VALUE_RE.search(plain)
    if match:
        out.append(f"{path} : terme interne « {match.group(0)} »")
    if _EMAIL_RE.search(value):
        out.append(f"{path} : adresse email (donnée personnelle)")
    if _PHONE_RE.search(value):
        out.append(f"{path} : numéro de téléphone (donnée personnelle)")
    if _IBAN_RE.search(value.upper()) and not value.startswith("https://"):
        out.append(f"{path} : IBAN ou numéro de compte")
    for term in terms:
        t = _fold(term).strip()
        if len(t) >= 3 and t in folded:
            out.append(f"{path} : référence interne « {term} »")


def _walk(obj: Any, schema: Any, path: str, terms: Sequence[str], out: list[str]) -> None:
    if isinstance(schema, dict):
        if not isinstance(obj, Mapping):
            out.append(f"{path or 'racine'} : objet attendu")
            return
        for key, value in obj.items():
            sub = f"{path}.{key}" if path else str(key)
            folded = _key_fold(str(key))
            if any(frag in folded for frag in SENSITIVE_KEY_FRAGMENTS):
                out.append(f"{sub} : champ sensible (coût, marge, fournisseur ou donnée personnelle)")
                continue
            if key not in schema:
                out.append(f"{sub} : champ hors liste blanche")
                continue
            _walk(value, schema[key], sub, terms, out)
        return
    if isinstance(schema, list):
        if not isinstance(obj, (list, tuple)):
            out.append(f"{path} : liste attendue")
            return
        for i, item in enumerate(obj):
            _walk(item, schema[0], f"{path}[{i}]", terms, out)
        return
    if schema == _B:
        if not isinstance(obj, bool):
            out.append(f"{path} : booléen attendu")
        return
    if not isinstance(obj, str):
        out.append(f"{path} : texte attendu (montants en chaîne, jamais de nombre flottant)")
        return
    _scan_value(obj, path, terms, out)


_METAFIELD_VALUES: dict[str, re.Pattern[str]] = {
    "statut_stock": re.compile(r"^(stock_local|precommande|rupture)$"),
    "date_sortie": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "date_sortie_statut": re.compile(r"^(confirmee|estimee|inconnue)$"),
    "quantite_max": re.compile(r"^[1-9]\d{0,2}$"),
    "alerte_reassort": re.compile(r"^(true|false)$"),
    "fin_de_serie": re.compile(r"^(true|false)$"),
    "langue": re.compile(r"^(FR|DE|IT|EN|JP)$"),
}


def _check_metafield(mf: Mapping[str, Any], path: str, require_owner: bool, out: list[str]) -> None:
    ns, key, typ = mf.get("namespace"), mf.get("key"), mf.get("type")
    if ns != PUBLIC_METAFIELD_NAMESPACE or key not in PUBLIC_METAFIELDS:
        out.append(f"{path} : métachamp non public ({ns}.{key})")
    elif typ != PUBLIC_METAFIELDS[str(key)]:
        out.append(f"{path} : type {typ!r} attendu {PUBLIC_METAFIELDS[str(key)]!r}")
    else:
        pattern = _METAFIELD_VALUES.get(str(key))
        value = mf.get("value")
        if pattern is not None and (not isinstance(value, str) or not pattern.match(value)):
            out.append(f"{path} : valeur {value!r} invalide pour {ns}.{key}")
    if require_owner and not re.match(r"^gid://shopify/Product/\d+$", str(mf.get("ownerId", ""))):
        out.append(f"{path}.ownerId : gid://shopify/Product/<n> attendu")


def sensitive_violations(product_input: Mapping[str, Any], *, sensitive_terms: Collection[str] = ()) -> list[str]:
    """Liste des violations d'une charge ``ProductSetInput`` (vide = conforme)."""
    out: list[str] = []
    terms = tuple(sensitive_terms)
    _walk(product_input, PRODUCT_INPUT_SCHEMA, "", terms, out)
    if not isinstance(product_input, Mapping):
        return out
    status = product_input.get("status")
    if status is not None and status not in ("DRAFT", "ACTIVE"):
        out.append("status : DRAFT ou ACTIVE uniquement")
    handle = product_input.get("handle")
    if handle is not None and (not isinstance(handle, str) or not _HANDLE_RE.match(handle)):
        out.append("handle : minuscules, chiffres et tirets")
    for i, tag in enumerate(product_input.get("tags") or ()):
        if not isinstance(tag, str) or not _TAG_RE.match(tag):
            out.append(f"tags[{i}] : étiquette invalide")
    for i, variant in enumerate(product_input.get("variants") or ()):
        if not isinstance(variant, Mapping):
            continue
        price = variant.get("price")
        if price is not None and (not isinstance(price, str) or not _PRICE_RE.match(price) or Decimal(price) <= 0):
            out.append(f"variants[{i}].price : prix CHF > 0 au format 0.00")
        if variant.get("inventoryPolicy") not in (None, "DENY"):
            out.append(f"variants[{i}].inventoryPolicy : DENY obligatoire (aucune vente à découvert)")
        barcode = variant.get("barcode")
        if barcode is not None and (not isinstance(barcode, str) or not validate_gtin(barcode)):
            out.append(f"variants[{i}].barcode : GTIN invalide")
        sku = (
            (variant.get("inventoryItem") or {}).get("sku")
            if isinstance(variant.get("inventoryItem"), Mapping)
            else None
        )
        if sku is not None and (not isinstance(sku, str) or not _SKU_RE.match(sku)):
            out.append(f"variants[{i}].inventoryItem.sku : SKU boutique invalide")
    for i, f in enumerate(product_input.get("files") or ()):
        if not isinstance(f, Mapping):
            continue
        if not str(f.get("originalSource", "")).startswith("https://"):
            out.append(f"files[{i}].originalSource : URL https obligatoire")
        if f.get("contentType") not in (None, "IMAGE"):
            out.append(f"files[{i}].contentType : IMAGE uniquement")
    for i, mf in enumerate(product_input.get("metafields") or ()):
        if isinstance(mf, Mapping):
            _check_metafield(mf, f"metafields[{i}]", False, out)
    for field in ("descriptionHtml",):
        value = product_input.get(field)
        if isinstance(value, str) and _UNSAFE_HTML_RE.search(value):
            out.append(f"{field} : HTML actif interdit (script, iframe, gestionnaire d'événement)")
    return list(dict.fromkeys(out))


def assert_no_sensitive_fields(product_input: Mapping[str, Any], *, sensitive_terms: Collection[str] = ()) -> None:
    """Lève :class:`SensitiveFieldError` si la charge contient autre chose que des champs publics."""
    violations = sensitive_violations(product_input, sensitive_terms=sensitive_terms)
    if violations:
        raise SensitiveFieldError(violations)


def assert_metafields_public(
    metafields: Sequence[Mapping[str, Any]], *, sensitive_terms: Collection[str] = (), require_owner: bool = False
) -> None:
    """Contrôle d'une liste ``MetafieldsSetInput`` (métachamps publics uniquement)."""
    out: list[str] = []
    allowed = {"namespace", "key", "type", "value"} | ({"ownerId"} if require_owner else set())
    for i, mf in enumerate(metafields):
        path = f"metafields[{i}]"
        if not isinstance(mf, Mapping):
            out.append(f"{path} : objet attendu")
            continue
        for key in mf:
            if key not in allowed:
                out.append(f"{path}.{key} : champ hors liste blanche")
        value = mf.get("value")
        if not isinstance(value, str):
            out.append(f"{path}.value : texte attendu")
        else:
            _scan_value(value, f"{path}.value", tuple(sensitive_terms), out)
        _check_metafield(mf, path, require_owner, out)
    if out:
        raise SensitiveFieldError(list(dict.fromkeys(out)))


# --------------------------------------------------------------------- entrées


class ImageRights(str, Enum):
    """Droit d'usage d'une image (BP §7 : photos officielles autorisées ou photos propres)."""

    SUPPLIER_WRITTEN_AUTHORIZATION = "SUPPLIER_WRITTEN_AUTHORIZATION"
    OWN_PHOTO = "OWN_PHOTO"
    UNKNOWN = "UNKNOWN"


class PublicImage(FrozenModel):
    """Image candidate ; seules les images autorisées entrent dans la charge."""

    url: str
    alt: str = Field(min_length=1, max_length=512)
    rights: ImageRights = ImageRights.UNKNOWN
    rights_ref: str | None = None
    """Référence de l'autorisation écrite (email, contrat) pour une photo fournisseur."""

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("URL d'image https obligatoire")
        return v

    @property
    def authorized(self) -> bool:
        """Photo propre, ou photo fournisseur avec autorisation écrite référencée."""
        if self.rights is ImageRights.OWN_PHOTO:
            return True
        return self.rights is ImageRights.SUPPLIER_WRITTEN_AUTHORIZATION and bool(self.rights_ref)


class StockStatus(str, Enum):
    """Statut public de stock (``boutique.statut_stock``), issu de :func:`pokeshop.stock.availability_promise`."""

    STOCK_LOCAL = "stock_local"
    PRECOMMANDE = "precommande"
    RUPTURE = "rupture"


def stock_status_from_promise(promise: AvailabilityPromise) -> StockStatus:
    """``LOCAL_STOCK`` -> stock_local ; ``PREORDER`` -> precommande ; ``UNAVAILABLE`` -> rupture (aucun faux stock)."""
    return {
        PromiseKind.LOCAL_STOCK: StockStatus.STOCK_LOCAL,
        PromiseKind.PREORDER: StockStatus.PRECOMMANDE,
        PromiseKind.UNAVAILABLE: StockStatus.RUPTURE,
    }[promise.kind]


class ReleaseDateStatus(str, Enum):
    """Statut de la date de sortie (``boutique.date_sortie_statut``)."""

    CONFIRMEE = "confirmee"
    ESTIMEE = "estimee"
    INCONNUE = "inconnue"


class ShopStatus(str, Enum):
    """Statuts publiables d'une fiche."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"


class CatalogListing(FrozenModel):
    """Fiche du catalogue validé destinée à la publication (aucun coût ni fournisseur ici)."""

    product_key: str = Field(min_length=1)
    identity: ProductIdentity
    public_sku: str
    """SKU boutique stable (``{FMT}-{CODEEXT}-{LANGUE}[-PRECO]``), jamais un SKU fournisseur."""
    handle: str | None = None
    description_html: str | None = Field(default=None, max_length=20_000)
    images: tuple[PublicImage, ...] = ()
    stock_status: StockStatus = StockStatus.RUPTURE
    content_text: str | None = Field(default=None, max_length=2_000)
    """Contenu confirmé par écrit (``boutique.contenu_valide``)."""
    release_date: date | None = None
    release_date_status: ReleaseDateStatus = ReleaseDateStatus.INCONNUE
    shipping_delay: str | None = Field(default=None, max_length=60)
    max_qty: int | None = Field(default=None, ge=1, le=999)
    restock_alert: bool = False
    end_of_series: bool = False
    new_arrival: bool = False
    gift: bool = False
    approved: bool = False
    """Fiche approuvée par une personne (mises à jour automatiques au niveau 2)."""
    category_rule_validated: bool = False
    """Règle de catégorie validée par la propriétaire (publication automatique au niveau 3)."""
    content_validated: bool = False
    """Contenu confirmé par le fournisseur (BP §7)."""
    shopify_product_id: str | None = None
    """None = nouvelle référence (jamais publiée)."""
    shopify_status: ShopStatus | None = None
    shopify_inventory_item_id: str | None = None
    current_price_chf: Decimal | None = Field(default=None, gt=0)
    """Prix public actuel sur la boutique (dernier prix validé)."""
    fictif: bool = False

    @field_validator("public_sku")
    @classmethod
    def _sku(cls, v: str) -> str:
        if not _SKU_RE.match(v):
            raise ValueError("SKU boutique : majuscules, chiffres et tirets (3 à 41 caractères)")
        return v

    @field_validator("handle")
    @classmethod
    def _handle(cls, v: str | None) -> str | None:
        if v is not None and not _HANDLE_RE.match(v):
            raise ValueError("handle : minuscules, chiffres et tirets")
        return v

    @model_validator(mode="after")
    def _shop(self) -> CatalogListing:
        preco = self.public_sku.endswith("-PRECO")
        if self.stock_status is StockStatus.PRECOMMANDE and not preco:
            raise ValueError("fiche de précommande : SKU suffixé -PRECO (fiche distincte du stock local)")
        if self.stock_status is StockStatus.STOCK_LOCAL and preco:
            raise ValueError("SKU -PRECO réservé à la fiche de précommande")
        if self.release_date is None and self.release_date_status is not ReleaseDateStatus.INCONNUE:
            raise ValueError("statut de date de sortie sans date")
        if self.shopify_product_id is not None and not re.match(
            r"^gid://shopify/Product/\d+$", self.shopify_product_id
        ):
            raise ValueError("shopify_product_id : gid://shopify/Product/<n>")
        if self.shopify_product_id is None and self.shopify_status is not None:
            raise ValueError("statut boutique sans identifiant produit")
        return self


class PriceValidation(FrozenModel):
    """Prix validé par une personne (décision REVIEW, variation > plafond, exception C18)."""

    price: Decimal = Field(gt=0)
    validated_by: str = Field(min_length=2)
    validated_at: datetime
    note: str = ""

    @field_validator("validated_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("validated_at doit porter un fuseau horaire")
        return v


class PublishBlocker(str, Enum):
    """Motifs stables du plan de publication."""

    IDENTITY_INCOMPLETE = "IDENTITY_INCOMPLETE"
    NOT_SEALED = "NOT_SEALED"
    LANGUAGE_NOT_FR = "LANGUAGE_NOT_FR"
    INVALID_GTIN = "INVALID_GTIN"
    FICTITIOUS_GTIN = "FICTITIOUS_GTIN"
    FICTIF_DATA = "FICTIF_DATA"
    QUARANTINED = "QUARANTINED"
    STOPLOSS_PRODUCT = "STOPLOSS_PRODUCT"
    FORBIDDEN_CLAIM = "FORBIDDEN_CLAIM"
    UNSAFE_HTML = "UNSAFE_HTML"
    SENSITIVE_FIELD = "SENSITIVE_FIELD"
    NOT_APPROVED = "NOT_APPROVED"
    DECISION_MISSING = "DECISION_MISSING"
    DECISION_DRAFT = "DECISION_DRAFT"
    DECISION_BLOCKED = "DECISION_BLOCKED"
    DECISION_REVIEW = "DECISION_REVIEW"
    PRICE_CHANGE_ABOVE_CAP = "PRICE_CHANGE_ABOVE_CAP"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    PRICE_UNKNOWN = "PRICE_UNKNOWN"
    CATEGORY_RULE_NOT_VALIDATED = "CATEGORY_RULE_NOT_VALIDATED"
    CONTENT_NOT_VALIDATED = "CONTENT_NOT_VALIDATED"
    MAX_QTY_MISSING = "MAX_QTY_MISSING"
    RELEASE_DATE_MISSING = "RELEASE_DATE_MISSING"
    DESCRIPTION_MISSING = "DESCRIPTION_MISSING"
    NO_AUTHORIZED_IMAGE = "NO_AUTHORIZED_IMAGE"
    IMAGE_RIGHTS_MISSING = "IMAGE_RIGHTS_MISSING"


BLOCKER_LABELS_FR: dict[PublishBlocker, str] = {
    PublishBlocker.IDENTITY_INCOMPLETE: "Identité incomplète ou ambiguë : brouillon, aucun titre public.",
    PublishBlocker.NOT_SEALED: "Produit non scellé ou état inconnu : hors périmètre de lancement.",
    PublishBlocker.LANGUAGE_NOT_FR: "Langue différente du français : hors périmètre (FR uniquement).",
    PublishBlocker.INVALID_GTIN: "GTIN absent ou invalide.",
    PublishBlocker.FICTITIOUS_GTIN: "GTIN interne 200… : ne peut pas être publié comme un EAN réel.",
    PublishBlocker.FICTIF_DATA: "Donnée FICTIVE : jamais publiée sur une boutique réelle.",
    PublishBlocker.QUARANTINED: "Référence en quarantaine : non achetable, dernier prix validé conservé.",
    PublishBlocker.STOPLOSS_PRODUCT: "Stop-loss produit : vente et promotion bloquées.",
    PublishBlocker.FORBIDDEN_CLAIM: "Promesse interdite (valeur future, rareté garantie, statut officiel).",
    PublishBlocker.UNSAFE_HTML: "HTML actif dans la description.",
    PublishBlocker.SENSITIVE_FIELD: "Champ interne ou donnée personnelle dans la charge : envoi refusé.",
    PublishBlocker.NOT_APPROVED: "Fiche non approuvée : reste en brouillon.",
    PublishBlocker.DECISION_MISSING: "Aucune décision de prix : aucun nouveau prix public.",
    PublishBlocker.DECISION_DRAFT: "Décision DRAFT (champ inconnu) : aucun nouveau prix public.",
    PublishBlocker.DECISION_BLOCKED: "Décision BLOCKED : aucun nouveau prix public.",
    PublishBlocker.DECISION_REVIEW: "Décision REVIEW : validation humaine requise avant tout nouveau prix.",
    PublishBlocker.PRICE_CHANGE_ABOVE_CAP: "Variation au-delà du plafond journalier : validation requise.",
    PublishBlocker.PRICE_ANOMALY: "Nouveau prix ×10 ou ÷10 par rapport à la veille : bloqué.",
    PublishBlocker.PRICE_UNKNOWN: "Aucun prix public connu ni calculé.",
    PublishBlocker.CATEGORY_RULE_NOT_VALIDATED: "Règle de catégorie non validée : nouvelle référence en brouillon.",
    PublishBlocker.CONTENT_NOT_VALIDATED: "Contenu non confirmé par écrit (boutique.contenu_valide).",
    PublishBlocker.MAX_QTY_MISSING: "Quantité maximale obligatoire pour une nouveauté ou une précommande.",
    PublishBlocker.RELEASE_DATE_MISSING: "Précommande sans date de sortie confirmée ou estimée.",
    PublishBlocker.DESCRIPTION_MISSING: "Description absente.",
    PublishBlocker.NO_AUTHORIZED_IMAGE: "Aucune image autorisée.",
    PublishBlocker.IMAGE_RIGHTS_MISSING: "Au moins une image sans droit d'usage (exclue de la fiche).",
}

_HARD = frozenset(
    {
        PublishBlocker.IDENTITY_INCOMPLETE,
        PublishBlocker.NOT_SEALED,
        PublishBlocker.LANGUAGE_NOT_FR,
        PublishBlocker.INVALID_GTIN,
        PublishBlocker.FICTITIOUS_GTIN,
        PublishBlocker.FICTIF_DATA,
        PublishBlocker.QUARANTINED,
        PublishBlocker.STOPLOSS_PRODUCT,
        PublishBlocker.FORBIDDEN_CLAIM,
        PublishBlocker.UNSAFE_HTML,
    }
)
_CONTENT = frozenset(
    {
        PublishBlocker.CONTENT_NOT_VALIDATED,
        PublishBlocker.DESCRIPTION_MISSING,
        PublishBlocker.NO_AUTHORIZED_IMAGE,
        PublishBlocker.IMAGE_RIGHTS_MISSING,
        PublishBlocker.MAX_QTY_MISSING,
        PublishBlocker.RELEASE_DATE_MISSING,
    }
)


class PlanOutcome(str, Enum):
    """Ce que le plan fait sur la boutique."""

    SEND_ACTIVE = "SEND_ACTIVE"
    SEND_DRAFT = "SEND_DRAFT"
    UNPUBLISH = "UNPUBLISH"
    NOT_SENT = "NOT_SENT"


class PublicationPlan(FrozenModel):
    """Plan de publication : charge publique + motifs. Ne contient ni coût ni marge."""

    product_key: str
    handle: str
    outcome: PlanOutcome
    target_status: ShopStatus | None
    action: str | None
    """Action d'écriture (:class:`pokeshop.autonomy.WriteAction`) à soumettre à la porte de gouvernance."""
    price_chf: Decimal | None
    price_source: Literal["ENGINE", "HUMAN_VALIDATED", "UNCHANGED"] | None
    product_input: dict[str, Any] | None
    identifier: dict[str, str] | None
    blockers: tuple[str, ...] = ()
    reviews: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    decision_status: str | None = None
    rules_version: str | None = None
    inputs_hash: str | None = None

    @property
    def send(self) -> bool:
        """Vrai si une écriture ``productSet`` est prévue."""
        return self.outcome is not PlanOutcome.NOT_SENT and self.product_input is not None

    @property
    def price_changed(self) -> bool:
        """Vrai si le prix public change (prix moteur ou validé différent du prix actuel)."""
        return self.price_source in ("ENGINE", "HUMAN_VALIDATED")


# ---------------------------------------------------------------------- construction


def _price_text(price: Decimal) -> str:
    return f"{q2(price):.2f}"


def _plain(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(_TAG_STRIP_RE.sub(" ", text).split())


def _metafields(listing: CatalogListing, fmt: ProductFormat, extension_name: str | None) -> list[dict[str, str]]:
    ns = PUBLIC_METAFIELD_NAMESPACE

    def mf(key: str, value: str) -> dict[str, str]:
        return {"namespace": ns, "key": key, "type": PUBLIC_METAFIELDS[key], "value": value}

    out = [mf("statut_stock", listing.stock_status.value), mf("format", FORMAT_LABELS_FR[fmt])]
    if listing.identity.language and listing.identity.language != "NA":
        out.append(mf("langue", listing.identity.language))
    if extension_name:
        out.append(mf("extension", extension_name))
    if listing.content_text:
        out.append(mf("contenu_valide", listing.content_text))
    if listing.release_date is not None:
        out.append(mf("date_sortie", listing.release_date.isoformat()))
    out.append(mf("date_sortie_statut", listing.release_date_status.value))
    if listing.shipping_delay:
        out.append(mf("delai_expedition", listing.shipping_delay))
    if listing.max_qty is not None:
        out.append(mf("quantite_max", str(listing.max_qty)))
    out.append(mf("alerte_reassort", "true" if listing.restock_alert else "false"))
    out.append(mf("fin_de_serie", "true" if listing.end_of_series else "false"))
    return out


def _tags(listing: CatalogListing, extension_name: str | None, target: ShopStatus) -> list[str]:
    tags = {"statut:" + listing.stock_status.value.replace("_", "-")}
    if extension_name:
        tags.add("ext:" + slugify(extension_name))
    if listing.new_arrival and target is ShopStatus.ACTIVE and listing.stock_status is not StockStatus.RUPTURE:
        tags.add("nouveaute")  # posé seulement sur un produit achetable (contrat du thème)
    if listing.gift:
        tags.add("cadeau")
    return sorted(t for t in tags if _TAG_RE.match(t))


def _extension_name(identity: ProductIdentity, table: ExtensionTable | None) -> str | None:
    if identity.extension in (None, NO_EXTENSION):
        return None
    if table is None:
        from .catalog import load_extension_table

        table = load_extension_table()
    return table.name_fr(identity.extension or "") or identity.extension or ""


def build_publication(
    listing: CatalogListing,
    decision: PriceDecision | None,
    *,
    max_daily_change: Decimal,
    reference_price_24h: Decimal | None = None,
    price_validation: PriceValidation | None = None,
    stoploss_blocked: bool = False,
    quarantined: bool = False,
    sensitive_terms: Collection[str] = (),
    table: ExtensionTable | None = None,
    real_shop: bool = False,
) -> PublicationPlan:
    """Plan de publication d'une fiche selon les règles BP §5-§7 (voir l'en-tête du module).

    ``reference_price_24h`` : prix public d'il y a 24 h (base du plafond journalier).
    ``real_shop`` : vrai pour une écriture réelle (refuse les données FICTIVES).
    """
    blockers: list[PublishBlocker] = []
    reviews: list[PublishBlocker] = []
    content: list[PublishBlocker] = []
    ident = listing.identity
    try:
        title = product_title_fr(ident, table)
    except CatalogError:
        title = None
    if title is None:
        blockers.append(PublishBlocker.IDENTITY_INCOMPLETE)
    if ident.sealed is not True:
        blockers.append(PublishBlocker.NOT_SEALED)
    fmt = ProductFormat(ident.format) if ident.format in ProductFormat.__members__ else ProductFormat.UNKNOWN
    if ident.language != expected_language_for(fmt):
        blockers.append(PublishBlocker.LANGUAGE_NOT_FR)
    if not validate_gtin(ident.gtin):
        blockers.append(PublishBlocker.INVALID_GTIN)
    elif is_fictitious_gtin(ident.gtin) and not listing.fictif:
        blockers.append(PublishBlocker.FICTITIOUS_GTIN)
    if listing.fictif and real_shop:
        blockers.append(PublishBlocker.FICTIF_DATA)
    if quarantined:
        blockers.append(PublishBlocker.QUARANTINED)
    if stoploss_blocked:
        blockers.append(PublishBlocker.STOPLOSS_PRODUCT)
    if forbidden_claims(title, listing.description_html, listing.content_text, *(img.alt for img in listing.images)):
        blockers.append(PublishBlocker.FORBIDDEN_CLAIM)
    if listing.description_html and _UNSAFE_HTML_RE.search(listing.description_html):
        blockers.append(PublishBlocker.UNSAFE_HTML)

    # -- prix
    current = listing.current_price_chf
    new_price: Decimal | None = None
    source: Literal["ENGINE", "HUMAN_VALIDATED", "UNCHANGED"] | None = None
    if decision is None:
        reviews.append(PublishBlocker.DECISION_MISSING)
    elif decision.status is DecisionStatus.BLOCKED:
        reviews.append(PublishBlocker.DECISION_BLOCKED)
    elif decision.status is DecisionStatus.DRAFT:
        reviews.append(PublishBlocker.DECISION_DRAFT)
    elif decision.status is DecisionStatus.REVIEW:
        if price_validation is not None:
            new_price, source = price_validation.price, "HUMAN_VALIDATED"
        else:
            reviews.append(PublishBlocker.DECISION_REVIEW)
    else:
        engine_price = decision.evaluated_price or decision.recommended_price
        if price_validation is not None and price_validation.price != engine_price:
            new_price, source = price_validation.price, "HUMAN_VALIDATED"
        elif engine_price is not None:
            new_price = engine_price
            source = "HUMAN_VALIDATED" if price_validation is not None else "ENGINE"
    if new_price is not None and reference_price_24h is not None and reference_price_24h > 0:
        if is_price_anomaly(new_price, reference_price_24h):
            reviews.append(PublishBlocker.PRICE_ANOMALY)
            new_price, source = None, None
        elif source == "ENGINE" and abs(new_price - reference_price_24h) / reference_price_24h > max_daily_change:
            reviews.append(PublishBlocker.PRICE_CHANGE_ABOVE_CAP)
            new_price, source = None, None
    if new_price is not None and current is not None and q2(new_price) == q2(current):
        source = "UNCHANGED"
    price = new_price if new_price is not None else current
    if new_price is None and current is not None:
        source = "UNCHANGED"

    # -- contenu
    authorized = [img for img in listing.images if img.authorized]
    if not listing.content_validated or not (listing.content_text or "").strip():
        content.append(PublishBlocker.CONTENT_NOT_VALIDATED)
    if listing.max_qty is None and (listing.new_arrival or listing.stock_status is StockStatus.PRECOMMANDE):
        content.append(PublishBlocker.MAX_QTY_MISSING)
    if listing.stock_status is StockStatus.PRECOMMANDE and listing.release_date_status is ReleaseDateStatus.INCONNUE:
        content.append(PublishBlocker.RELEASE_DATE_MISSING)
    if not _plain(listing.description_html):
        content.append(PublishBlocker.DESCRIPTION_MISSING)
    if not authorized:
        content.append(PublishBlocker.NO_AUTHORIZED_IMAGE)
    if len(authorized) != len(listing.images):
        content.append(PublishBlocker.IMAGE_RIGHTS_MISSING)

    # -- issue
    existing = listing.shopify_product_id is not None
    hard = [b for b in blockers if b in _HARD]
    outcome = PlanOutcome.NOT_SENT
    target: ShopStatus | None = None
    action: str | None = None
    if existing:
        if hard or not listing.approved:
            if not listing.approved and not hard:
                reviews.append(PublishBlocker.NOT_APPROVED)
            if listing.shopify_status is ShopStatus.ACTIVE:
                outcome, target, action = PlanOutcome.UNPUBLISH, ShopStatus.DRAFT, "UNPUBLISH_PRODUCT"
                price, source = current, "UNCHANGED"
            elif not hard and price is not None:
                outcome, target, action = PlanOutcome.SEND_DRAFT, ShopStatus.DRAFT, "SAVE_DRAFT_PRODUCT"
        elif content:
            pass  # fiche approuvée devenue incomplète : rien n'est écrasé, revue humaine
        elif price is not None:
            outcome, target, action = PlanOutcome.SEND_ACTIVE, ShopStatus.ACTIVE, "UPDATE_APPROVED_PRODUCT"
    elif not hard and new_price is not None:
        auto = (
            listing.category_rule_validated
            and not content
            and decision is not None
            and decision.status in (DecisionStatus.OK, DecisionStatus.REVIEW)
        )
        if auto:
            outcome, target, action = PlanOutcome.SEND_ACTIVE, ShopStatus.ACTIVE, "PUBLISH_NEW_PRODUCT"
        else:
            if not listing.category_rule_validated:
                reviews.append(PublishBlocker.CATEGORY_RULE_NOT_VALIDATED)
            outcome, target, action = PlanOutcome.SEND_DRAFT, ShopStatus.DRAFT, "SAVE_DRAFT_PRODUCT"
    if outcome is not PlanOutcome.NOT_SENT and price is None:
        reviews.append(PublishBlocker.PRICE_UNKNOWN)
        outcome, target, action = PlanOutcome.NOT_SENT, None, None
    if outcome is PlanOutcome.NOT_SENT and price is None and PublishBlocker.PRICE_UNKNOWN not in reviews:
        reviews.append(PublishBlocker.PRICE_UNKNOWN)

    handle = listing.handle or slugify(f"{title or listing.product_key}-{listing.public_sku}")
    product_input: dict[str, Any] | None = None
    identifier: dict[str, str] | None = None
    violations: list[str] = []
    if outcome is not PlanOutcome.NOT_SENT and title is not None and price is not None and target is not None:
        ext_name = _extension_name(ident, table)
        option, value = (
            ("Disponibilité", "Précommande")
            if listing.stock_status is StockStatus.PRECOMMANDE
            else ("Title", "Default Title")
        )
        product_input = {
            "title": title,
            "handle": handle,
            "status": target.value,
            "productType": FORMAT_LABELS_FR[fmt],
            "tags": _tags(listing, ext_name, target),
            "productOptions": [{"name": option, "values": [{"name": value}]}],
            "variants": [
                {
                    "optionValues": [{"optionName": option, "name": value}],
                    "price": _price_text(price),
                    "barcode": ident.gtin or "",
                    "inventoryPolicy": "DENY",
                    "inventoryItem": {"sku": listing.public_sku, "tracked": True},
                }
            ],
            "files": [{"originalSource": img.url, "alt": img.alt, "contentType": "IMAGE"} for img in authorized],
            "metafields": _metafields(listing, fmt, ext_name),
            "seo": {"title": title[:70], "description": _plain(listing.description_html)[:320]},
        }
        if listing.description_html:
            product_input["descriptionHtml"] = listing.description_html
        identifier = {"id": listing.shopify_product_id} if listing.shopify_product_id else {"handle": handle}
        violations = sensitive_violations(product_input, sensitive_terms=sensitive_terms)
        if violations:
            blockers.append(PublishBlocker.SENSITIVE_FIELD)
            product_input, identifier = None, None
            outcome, target, action = PlanOutcome.NOT_SENT, None, None
    all_codes = list(dict.fromkeys([*blockers, *reviews, *content]))
    return PublicationPlan(
        product_key=listing.product_key,
        handle=handle,
        outcome=outcome,
        target_status=target,
        action=action,
        price_chf=q2(price) if price is not None and outcome is not PlanOutcome.NOT_SENT else None,
        price_source=source if outcome is not PlanOutcome.NOT_SENT else None,
        product_input=product_input,
        identifier=identifier,
        blockers=tuple(b.value for b in dict.fromkeys(blockers)),
        reviews=tuple(r.value for r in dict.fromkeys([*reviews, *content])),
        messages=tuple(BLOCKER_LABELS_FR[c] for c in all_codes),
        violations=tuple(violations),
        decision_status=decision.status.value if decision is not None else None,
        rules_version=decision.rules_version if decision is not None else None,
        inputs_hash=decision.inputs_hash if decision is not None else None,
    )
