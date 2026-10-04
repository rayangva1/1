"""Types partagés du moteur coûts / prix / stock (propriété : agent core-engine).

Conventions (non négociables, cf. docs/SPEC.md §0) :

* **Decimal partout**, jamais ``float`` pour un montant. Les modèles pydantic acceptent
  une chaîne, un entier ou un ``Decimal`` ; un flottant JSON est converti par pydantic
  via sa représentation décimale courte (``str(0.1) == "0.1"``), jamais via le binaire.
  Préférer des chaînes ("140.00") dans les échanges JSON. NaN et infinis sont refusés.
* Modèles **immuables** (``frozen=True``) et stricts (``extra="forbid"``).
* Toutes les quantités d'une :class:`SupplierOffer` sont exprimées en **unités de vente
  boutique** (unité retail : 1 display, 1 ETB, 1 booster…). Le prix fournisseur couvre
  ``units_per_pack`` unités retail.
* Les décisions portent ``rules_version`` et ``inputs_hash`` (sha256 des entrées
  canoniques, voir :func:`canonical_hash`) pour la traçabilité.
* Coûts, marges et prix B2B présents ici sont **internes** : ils ne doivent jamais être
  sérialisés vers le HTML public, Shopify public ou un prompt marketing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "FrozenModel",
    "VatMode",
    "DecisionStatus",
    "Reason",
    "REASON_LABELS_FR",
    "AvailabilityStatus",
    "RoundingTier",
    "DEFAULT_ROUNDING_TIERS",
    "TierDiscount",
    "PricingParams",
    "StockParams",
    "LandedCostInput",
    "LandedCostBreakdown",
    "ContributionBreakdown",
    "PriceDecision",
    "Discount",
    "BasketLine",
    "BasketLineResult",
    "BasketResult",
    "SupplierOffer",
    "ProductIdentity",
    "AllocationLine",
    "AllocatedCost",
    "PromiseKind",
    "AvailabilityPromise",
    "StockLevel",
    "ReservationStatus",
    "Reservation",
    "MovementKind",
    "StockMovement",
    "ReorderCandidate",
    "ReorderLine",
    "ReorderSkip",
    "ReorderProposal",
    "CostLot",
    "CostVariance",
    "InventoryValuation",
    "ReplacementCost",
    "PriceEventKind",
    "PriceEvent",
    "canonical_decimal",
    "canonical_json",
    "canonical_hash",
    "explain",
]

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


class FrozenModel(BaseModel):
    """Base pydantic immuable, stricte sur les champs, NaN/inf refusés."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    def replace(self, **changes: Any) -> Any:
        """Copie **revalidée** avec modifications (``model_copy`` ne revalide pas)."""
        data = {name: getattr(self, name) for name in type(self).model_fields}
        data.update(changes)
        return type(self).model_validate(data)


# --------------------------------------------------------------------------- enums


class VatMode(str, Enum):
    """Traitement TVA de l'entité exploitante (BP §4)."""

    EFFECTIVE = "EFFECTIVE"
    """Assujettie, méthode effective : TVA suisse récupérable, ventes calculées HT."""
    NOT_REGISTERED = "NOT_REGISTERED"
    """Non assujettie : TVA non récupérable intégrée au coût, t = 0 sur les ventes."""


class DecisionStatus(str, Enum):
    """Statut d'une décision de prix ou de panier. Gravité : BLOCKED > DRAFT > REVIEW > OK."""

    OK = "OK"
    REVIEW = "REVIEW"
    DRAFT = "DRAFT"
    BLOCKED = "BLOCKED"

    @property
    def severity(self) -> int:
        """Rang de gravité (0 = OK)."""
        return _STATUS_SEVERITY[self]


_STATUS_SEVERITY = {
    DecisionStatus.OK: 0,
    DecisionStatus.REVIEW: 1,
    DecisionStatus.DRAFT: 2,
    DecisionStatus.BLOCKED: 3,
}


class Reason(str, Enum):
    """Codes stables des motifs de décision (les libellés FR sont dans REASON_LABELS_FR)."""

    ZERO_OR_NEGATIVE_COST = "ZERO_OR_NEGATIVE_COST"
    ZERO_PRICE = "ZERO_PRICE"
    DENOMINATOR_NOT_POSITIVE = "DENOMINATOR_NOT_POSITIVE"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    UNKNOWN_FIELDS = "UNKNOWN_FIELDS"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    ABOVE_MARKET = "ABOVE_MARKET"
    INVALID_MARKET_REF = "INVALID_MARKET_REF"
    DAILY_CHANGE_ABOVE_CAP = "DAILY_CHANGE_ABOVE_CAP"
    INVALID_CURRENT_PRICE = "INVALID_CURRENT_PRICE"
    CURRENT_PRICE_BELOW_HARD_FLOOR = "CURRENT_PRICE_BELOW_HARD_FLOOR"
    BELOW_TARGET_MARGIN = "BELOW_TARGET_MARGIN"
    BELOW_HARD_FLOOR = "BELOW_HARD_FLOOR"
    BELOW_ORDER_FLOOR_CHF = "BELOW_ORDER_FLOOR_CHF"
    ORDER_FLOOR_CHF_BINDING = "ORDER_FLOOR_CHF_BINDING"
    SMALL_PRODUCT_ADDON = "SMALL_PRODUCT_ADDON"
    STALE_OFFER = "STALE_OFFER"
    ROUNDING_RECHECK_FAILED = "ROUNDING_RECHECK_FAILED"
    DISCOUNT_CAPPED = "DISCOUNT_CAPPED"
    SHIPPING_COST_ASSUMED = "SHIPPING_COST_ASSUMED"
    NON_POSITIVE_NET_REVENUE = "NON_POSITIVE_NET_REVENUE"


REASON_LABELS_FR: dict[Reason, str] = {
    Reason.ZERO_OR_NEGATIVE_COST: "Coût rendu nul ou négatif : anomalie, aucun prix calculé.",
    Reason.ZERO_PRICE: "Prix fournisseur à zéro : anomalie d'import, mise en quarantaine.",
    Reason.DENOMINATOR_NOT_POSITIVE: "Paramètres incohérents : dénominateur de la formule ≤ 0.",
    Reason.PRICE_ANOMALY: "Variation ×10 (ou ÷10) par rapport à la référence : quarantaine.",
    Reason.UNKNOWN_FIELDS: "Frais, taxe, langue ou conditionnement inconnus : fiche en brouillon.",
    Reason.LANGUAGE_MISMATCH: "Langue de l'offre différente de la langue attendue (FR).",
    Reason.ABOVE_MARKET: "Prix rentable > marché comparable +10 % : proposition à revoir.",
    Reason.INVALID_MARKET_REF: "Prix de marché de référence invalide (≤ 0) : ignoré, à revoir.",
    Reason.DAILY_CHANGE_ABOVE_CAP: "Variation du prix public > plafond journalier : validation requise.",
    Reason.INVALID_CURRENT_PRICE: "Prix public actuel invalide (≤ 0) : à revoir.",
    Reason.CURRENT_PRICE_BELOW_HARD_FLOOR: "Le prix public actuel est sous le plancher dur.",
    Reason.BELOW_TARGET_MARGIN: "Contribution sous la cible (20 %) mais au-dessus du plancher dur.",
    Reason.BELOW_HARD_FLOOR: "Contribution sous le plancher dur (12 %) : bloqué.",
    Reason.BELOW_ORDER_FLOOR_CHF: "Contribution de la commande < 8 CHF : bloqué.",
    Reason.ORDER_FLOOR_CHF_BINDING: "Le plancher de 8 CHF par commande relève le prix recommandé.",
    Reason.SMALL_PRODUCT_ADDON: "Petit produit : frais par commande exclus, vente seule contrôlée au panier.",
    Reason.STALE_OFFER: "Offre fournisseur périmée (> 24 h) : inéligible au réassort.",
    Reason.ROUNDING_RECHECK_FAILED: "Revérification de marge après arrondi en échec.",
    Reason.DISCOUNT_CAPPED: "Remise supérieure au montant des produits : plafonnée.",
    Reason.SHIPPING_COST_ASSUMED: "Coût logistique réel non fourni : hypothèse BP (L) utilisée.",
    Reason.NON_POSITIVE_NET_REVENUE: "Chiffre d'affaires net ≤ 0 : commande bloquée.",
}


def explain(reasons: tuple[str, ...] | list[str]) -> list[str]:
    """Traduit des codes de motifs en libellés français (code inconnu renvoyé tel quel)."""
    out: list[str] = []
    for code in reasons:
        try:
            out.append(REASON_LABELS_FR[Reason(code)])
        except ValueError:
            out.append(code)
    return out


class AvailabilityStatus(str, Enum):
    """Statut de disponibilité déclaré par le fournisseur (normalisé par l'import)."""

    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    PREORDER = "PREORDER"
    ALLOCATION = "ALLOCATION"
    DISCONTINUED = "DISCONTINUED"
    UNKNOWN = "UNKNOWN"


# ------------------------------------------------------------------ helpers / hash


def canonical_decimal(value: Decimal) -> str:
    """Forme canonique d'un Decimal : ``Decimal("140.00")`` et ``Decimal("140")`` -> ``"140"``."""
    if not value.is_finite():
        raise ValueError("Decimal non fini interdit")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _canonicalize(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return {k: _canonicalize(getattr(obj, k)) for k in type(obj).model_fields}
    if isinstance(obj, Enum):
        return _canonicalize(obj.value)
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, Decimal):
        return canonical_decimal(obj)
    if isinstance(obj, float):
        raise TypeError("float interdit dans une entrée canonique : utiliser Decimal")
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            raise ValueError("datetime naïf interdit : fournir un fuseau horaire")
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return canonical_decimal(Decimal(str(obj.total_seconds()))) + "s"
    if isinstance(obj, Mapping):
        return {str(_canonicalize(k)): _canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted((_canonicalize(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, (list, tuple)):
        return [_canonicalize(v) for v in obj]
    raise TypeError(f"Type non canonisable : {type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    """JSON canonique (clés triées, Decimal normalisés, sans espaces) d'une structure d'entrées."""
    return json.dumps(_canonicalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(obj: Any) -> str:
    """sha256 hexadécimal de :func:`canonical_json` — utilisé pour ``inputs_hash``."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _check_rate(value: Decimal, name: str, *, upper_inclusive: bool = False) -> Decimal:
    if value < 0 or (value > 1 if upper_inclusive else value >= 1):
        bound = "[0, 1]" if upper_inclusive else "[0, 1["
        raise ValueError(f"{name} doit être dans {bound} (reçu {value})")
    return value


# --------------------------------------------------------------- pricing params


class RoundingTier(FrozenModel):
    """Palier de la grille d'arrondi psychologique.

    Les points de prix du palier sont ``n × step + e`` (n entier ≥ 0, e ∈ ``endings``),
    valables pour ``min_price ≤ point < min_price du palier suivant``.
    """

    min_price: Decimal = Field(ge=0)
    step: Decimal = Field(gt=0)
    endings: tuple[Decimal, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> RoundingTier:
        for e in self.endings:
            if e < 0 or e >= self.step:
                raise ValueError(f"terminaison {e} hors de [0, {self.step}[")
            if e % CENT != 0:
                raise ValueError(f"terminaison {e} non multiple de 0.01")
        if self.step % CENT != 0:
            raise ValueError("le pas doit être un multiple de 0.01")
        if len(set(self.endings)) != len(self.endings):
            raise ValueError("terminaisons en double")
        return self


DEFAULT_ROUNDING_TIERS: tuple[RoundingTier, ...] = (
    # < 10 CHF : X.50 ou X.90 (hausse max 0.40 CHF) — règle petits prix
    RoundingTier(min_price=Decimal("0"), step=Decimal("1.00"), endings=(Decimal("0.50"), Decimal("0.90"))),
    # 10 à 99.99 CHF : X.90 (hausse max 1 CHF)
    RoundingTier(min_price=Decimal("10"), step=Decimal("1.00"), endings=(Decimal("0.90"),)),
    # ≥ 100 CHF : X4.90 ou X9.90 (hausse max 5 CHF) — reproduit 208.79 -> 209.90 (BP §4)
    RoundingTier(min_price=Decimal("100"), step=Decimal("10.00"), endings=(Decimal("4.90"), Decimal("9.90"))),
)


class PricingParams(FrozenModel):
    """Paramètres de la formule de prix (BP §4) et de la table de règles (BP §5).

    Valeurs par défaut des seuils = hypothèses BP §5, à confirmer. Le contrôle du
    dénominateur est fait par :func:`pokeshop.pricing.floor_price` (PricingError) et par
    :mod:`pokeshop.rules` au chargement, pas ici, pour pouvoir tester le cas limite.
    """

    vat_rate_sales: Decimal
    """t : TVA sur ventes (0.081 si EFFECTIVE, 0 si NOT_REGISTERED)."""
    payment_pct: Decimal
    """r : frais de paiement proportionnels au montant encaissé TTC."""
    payment_fixed: Decimal = Field(ge=0)
    """b : frais fixes de paiement, CHF par commande."""
    logistics_cost: Decimal = Field(ge=0)
    """L : coût net de préparation/expédition supporté, CHF par commande."""
    after_sales_provision: Decimal = Field(ge=0)
    """R : provision SAV, CHF par commande."""
    acquisition_cost: Decimal = Field(ge=0)
    """A : coût d'acquisition attribué, CHF par commande."""
    target_margin: Decimal
    """m : contribution cible en % du CA net (HT)."""
    hard_floor_margin: Decimal = Decimal("0.12")
    hard_floor_chf_per_order: Decimal = Field(default=Decimal("8"), ge=0)
    rules_version: str = Field(min_length=1)
    vat_mode: VatMode | None = None
    """Déduit de t si absent : t = 0 -> NOT_REGISTERED, sinon EFFECTIVE."""
    market_review_threshold: Decimal = Field(default=Decimal("0.10"), ge=0)
    max_daily_price_change: Decimal = Field(default=Decimal("0.05"), gt=0)
    price_anomaly_factor: Decimal = Field(default=Decimal("10"), gt=1)
    small_product_max_cost: Decimal | None = Field(default=None, ge=0)
    """Seuil de coût rendu sous lequel un produit est « petit » (None = règle désactivée)."""
    rounding_tiers: tuple[RoundingTier, ...] = DEFAULT_ROUNDING_TIERS

    @model_validator(mode="before")
    @classmethod
    def _infer_mode(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and data.get("vat_mode") is None and "vat_rate_sales" in data:
            rate = Decimal(str(data["vat_rate_sales"]))
            data = {**data, "vat_mode": VatMode.NOT_REGISTERED if rate == 0 else VatMode.EFFECTIVE}
        return data

    @model_validator(mode="after")
    def _check(self) -> PricingParams:
        _check_rate(self.vat_rate_sales, "vat_rate_sales (t)")
        _check_rate(self.payment_pct, "payment_pct (r)")
        _check_rate(self.target_margin, "target_margin (m)")
        _check_rate(self.hard_floor_margin, "hard_floor_margin")
        if self.hard_floor_margin > self.target_margin:
            raise ValueError("le plancher dur ne peut pas dépasser la marge cible")
        mode = self.vat_mode
        if mode is None:
            raise ValueError("vat_mode indéterminé")
        if mode is VatMode.NOT_REGISTERED and self.vat_rate_sales != 0:
            raise ValueError("NOT_REGISTERED impose t = 0 (BP §4)")
        if mode is VatMode.EFFECTIVE and self.vat_rate_sales == 0:
            raise ValueError("EFFECTIVE impose t > 0")
        tiers = self.rounding_tiers
        if not tiers or tiers[0].min_price != 0:
            raise ValueError("la grille d'arrondi doit commencer à 0")
        for a, b in zip(tiers, tiers[1:]):
            if b.min_price <= a.min_price:
                raise ValueError("paliers d'arrondi non strictement croissants")
        return self

    def replace(self, **changes: Any) -> PricingParams:
        """Copie revalidée ; si t change sans ``vat_mode`` explicite, le mode est re-déduit."""
        if "vat_rate_sales" in changes and "vat_mode" not in changes:
            changes["vat_mode"] = None
        return super().replace(**changes)  # type: ignore[no-any-return]

    @property
    def mode(self) -> VatMode:
        """Mode TVA effectif (jamais None après validation)."""
        assert self.vat_mode is not None
        return self.vat_mode

    @property
    def per_order_costs(self) -> Decimal:
        """b + L + R + A : frais engagés une fois par commande."""
        return self.payment_fixed + self.logistics_cost + self.after_sales_provision + self.acquisition_cost


class StockParams(FrozenModel):
    """Paramètres stock/réassort (BP §1, §5) — hypothèses à valider."""

    staleness_hours: int = Field(default=24, ge=1, le=168)
    extension_budget_cap: Decimal = Field(default=Decimal("0.25"), gt=0, le=1)
    stock_budget_chf: Decimal = Field(default=Decimal("3000"), ge=0)
    reorder_coverage_days: int = Field(default=14, ge=0, le=180)
    future_skew_minutes: int = Field(default=5, ge=0, le=60)

    @property
    def max_age(self) -> timedelta:
        """Âge maximal d'une donnée amont avant péremption."""
        return timedelta(hours=self.staleness_hours)


# ------------------------------------------------------------------ landed cost


class TierDiscount(FrozenModel):
    """Palier de remise fournisseur : à partir de ``min_qty`` unités retail commandées.

    Exactement un de ``discount_pct`` (fraction, 0.05 = 5 %) ou ``price`` (prix du pack,
    même devise et même base HT/TTC que le prix de base) doit être renseigné.
    """

    min_qty: int = Field(ge=1)
    discount_pct: Decimal | None = None
    price: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> TierDiscount:
        if (self.discount_pct is None) == (self.price is None):
            raise ValueError("renseigner exactement discount_pct OU price")
        if self.discount_pct is not None:
            _check_rate(self.discount_pct, "discount_pct")
        return self


def _upper_code(value: str | None, pattern: re.Pattern[str], name: str) -> str | None:
    if value is None:
        return None
    code = value.strip().upper()
    if not code:
        return None
    if not pattern.match(code):
        raise ValueError(f"{name} invalide : {value!r}")
    return code


class LandedCostInput(FrozenModel):
    """Entrées du coût rendu par unité retail (BP §4 « Coût rendu par unité »).

    * ``purchase_net`` : prix du pack fournisseur (``units_per_pack`` unités) dans ``currency``,
      avant remise par palier ; TTC si ``price_includes_vat`` sinon HT.
    * ``supplier_vat_rate`` : TVA que le fournisseur facture (0 si facture export HT).
      Si le prix est HT et le taux > 0, la TVA s'ajoute à la facture.
    * ``supplier_vat_country`` : pays de cette TVA. Seule une TVA **suisse** est récupérable,
      et seulement en mode EFFECTIVE. TVA étrangère ou pays inconnu => coût (prudence).
    * ``inbound_freight_alloc``, ``customs_and_fees``, ``import_vat`` : CHF **par unité retail**,
      déjà ventilés (voir :func:`pokeshop.pricing.allocate_inbound_costs`). Saisir les frais
      HT si EFFECTIVE, TTC si NOT_REGISTERED. ``import_vat`` n'entre dans le coût qu'en
      NOT_REGISTERED.
    * ``tier_discounts`` / ``order_qty`` : remise par palier, quantité en unités retail
      (sans ``order_qty`` aucune remise n'est appliquée — prudence).
    """

    purchase_net: Decimal = Field(ge=0)
    currency: str
    fx_rate_to_chf: Decimal = Field(gt=0)
    """CHF pour 1 unité de ``currency`` (1 si CHF)."""
    fx_source: str = Field(min_length=1)
    fx_date: date
    price_includes_vat: bool
    supplier_vat_rate: Decimal
    units_per_pack: int = Field(ge=1)
    inbound_freight_alloc: Decimal = Field(default=ZERO, ge=0)
    customs_and_fees: Decimal = Field(default=ZERO, ge=0)
    import_vat: Decimal = Field(default=ZERO, ge=0)
    vat_mode: VatMode
    supplier_vat_country: str | None = None
    tier_discounts: tuple[TierDiscount, ...] = ()
    order_qty: int | None = Field(default=None, ge=1)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        code = _upper_code(v, _CURRENCY_RE, "currency")
        if code is None:
            raise ValueError("currency obligatoire")
        return code

    @field_validator("supplier_vat_country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        return _upper_code(v, _COUNTRY_RE, "supplier_vat_country")

    @model_validator(mode="after")
    def _check(self) -> LandedCostInput:
        _check_rate(self.supplier_vat_rate, "supplier_vat_rate")
        if self.currency == "CHF" and self.fx_rate_to_chf != 1:
            raise ValueError("devise CHF : fx_rate_to_chf doit valoir 1")
        mins = [t.min_qty for t in self.tier_discounts]
        if len(set(mins)) != len(mins):
            raise ValueError("paliers de remise en double (min_qty)")
        return self


class LandedCostBreakdown(FrozenModel):
    """Détail du coût rendu par unité retail, CHF. Composantes à 0.0001, total à 0.01."""

    pack_price_after_discount: Decimal
    """Prix du pack après remise palier, devise fournisseur, base du devis (HT ou TTC)."""
    tier_applied: int | None
    """min_qty du palier appliqué (None = aucun)."""
    purchase_ex_vat_unit_chf: Decimal
    supplier_vat_unit_chf: Decimal
    supplier_vat_recoverable: bool
    inbound_freight_unit_chf: Decimal
    customs_and_fees_unit_chf: Decimal
    import_vat_in_cost_unit_chf: Decimal
    recoverable_vat_unit_chf: Decimal
    """TVA récupérable (fournisseur CH + import) exclue du coût — impact trésorerie seulement."""
    total: Decimal


class ContributionBreakdown(FrozenModel):
    """Contribution d'une vente unitaire au prix public TTC ``price_ttc`` (BP §4)."""

    price_ttc: Decimal
    net_revenue: Decimal
    vat: Decimal
    payment_fees: Decimal
    product_cost: Decimal
    per_order_costs: Decimal
    """L + R + A (b est inclus dans payment_fees). 0 pour un petit produit additionnel."""
    contribution_chf: Decimal
    contribution_pct: Decimal
    """Fraction du CA net (0.1656 = 16.56 %)."""


class PriceDecision(FrozenModel):
    """Décision de prix d'une référence (BP §5). Interne : ne jamais publier tel quel.

    ``floor_price`` = formule BP à la marge cible (arrondie 0.01) ; ``profitable_price`` =
    max(plancher cible, plancher 8 CHF/commande) ; ``recommended_price`` = arrondi retail
    du prix rentable, revérifié ; ``evaluated_price`` = prix sur lequel portent la
    contribution et les contrôles (prix candidat s'il est fourni, sinon recommandé).
    """

    floor_price: Decimal | None
    recommended_price: Decimal | None
    contribution_chf: Decimal | None
    contribution_pct: Decimal | None
    status: DecisionStatus
    reasons: tuple[str, ...]
    rules_version: str
    inputs_hash: str
    profitable_price: Decimal | None = None
    evaluated_price: Decimal | None = None
    landed_cost: Decimal | None = None
    small_product: bool = False
    restock_eligible: bool = True
    notes: tuple[str, ...] = ()

    @property
    def is_publishable(self) -> bool:
        """Vrai seulement si OK : REVIEW exige une validation humaine, DRAFT/BLOCKED jamais."""
        return self.status is DecisionStatus.OK

    def has(self, reason: Reason | str) -> bool:
        """Vrai si le motif est présent."""
        code = reason.value if isinstance(reason, Reason) else reason
        return code in self.reasons


# ------------------------------------------------------------------------ basket


class Discount(FrozenModel):
    """Remise ou code promo, TTC, appliqué aux produits (pas au port)."""

    kind: Literal["PERCENT", "AMOUNT"]
    value: Decimal = Field(ge=0)
    code: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Discount:
        if self.kind == "PERCENT" and self.value > 1:
            raise ValueError("remise PERCENT exprimée en fraction (0.10 = 10 %)")
        return self


class BasketLine(FrozenModel):
    """Ligne de panier. ``unit_price_ttc`` est le prix public figé de la commande."""

    sku: str = Field(min_length=1)
    qty: int = Field(ge=1)
    unit_price_ttc: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    """Coût rendu unitaire (coût historique moyen pour la marge réalisée)."""


class BasketLineResult(FrozenModel):
    """Résultat ventilé par ligne (frais de commande répartis au prorata du CA net)."""

    sku: str
    qty: int
    goods_ttc: Decimal
    discount_ttc: Decimal
    net_revenue: Decimal
    product_cost: Decimal
    allocated_order_costs: Decimal
    contribution_chf: Decimal


class BasketResult(FrozenModel):
    """Contribution d'une commande complète : frais fixes comptés **une seule fois**."""

    goods_ttc: Decimal
    discount_ttc: Decimal
    shipping_charged_ttc: Decimal
    total_paid_ttc: Decimal
    net_revenue: Decimal
    vat: Decimal
    payment_fees: Decimal
    product_cost: Decimal
    logistics_cost: Decimal
    after_sales: Decimal
    acquisition: Decimal
    shipping_gap: Decimal
    """Port facturé HT − coût logistique réel (négatif = port subventionné)."""
    contribution_chf: Decimal
    contribution_pct: Decimal | None
    status: DecisionStatus
    reasons: tuple[str, ...]
    lines: tuple[BasketLineResult, ...]
    rules_version: str
    inputs_hash: str

    @property
    def is_allowed(self) -> bool:
        """Vrai si le panier/la promotion peut être accepté."""
        return self.status is not DecisionStatus.BLOCKED


# ---------------------------------------------------------------- cost allocation


class AllocationLine(FrozenModel):
    """Ligne d'une réception pour ventiler transport/frais : ``value`` = valeur marchandise CHF."""

    key: str = Field(min_length=1)
    qty: int = Field(ge=1)
    value: Decimal = Field(ge=0)


class AllocatedCost(FrozenModel):
    """Part d'un coût global affectée à une ligne (total 0.01, unitaire 0.0001)."""

    key: str
    qty: int
    allocated_total: Decimal
    per_unit: Decimal


# ---------------------------------------------------------------- supplier offer


class SupplierOffer(FrozenModel):
    """Offre fournisseur normalisée (sortie des importeurs, entrée du moteur).

    Quantités en unités retail ; ``price`` couvre ``units_per_pack`` unités. ``None`` =
    information inconnue (=> brouillon si le champ est critique, BP §5).
    ``allocation_qty`` ne doit être renseigné que pour une allocation **ferme confirmée par
    écrit** au revendeur. ``stock_pool_id`` : offres d'un même pool partagent le même stock
    amont (jamais additionnées) ; ``None`` = pool inconnu (jamais additionné non plus).
    ``vat_country`` : pays de la TVA facturée (défaut : ``ship_from_country``).
    """

    supplier_id: str = Field(min_length=1)
    supplier_sku: str = Field(min_length=1)
    gtin: str | None = None
    language: str | None = None
    extension: str | None = None
    format: str | None = None
    content: str | None = None
    sealed: bool | None = None
    units_per_pack: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    price_includes_vat: bool | None = None
    vat_rate: Decimal | None = None
    tier_discounts: tuple[TierDiscount, ...] = ()
    moq: int | None = Field(default=None, ge=1)
    carton_qty: int | None = Field(default=None, ge=1)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    available_qty: int | None = Field(default=None, ge=0)
    allocation_qty: int | None = Field(default=None, ge=0)
    release_date: date | None = None
    incoterm: str | None = None
    ship_from_country: str | None = None
    source_ts: datetime
    raw_ref: str = Field(min_length=1)
    vat_country: str | None = None
    stock_pool_id: str | None = None

    @field_validator("gtin", "extension", "format", "content", "incoterm", "stock_pool_id")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("language")
    @classmethod
    def _language(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return v or None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        return _upper_code(v, _CURRENCY_RE, "currency")

    @field_validator("ship_from_country", "vat_country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        return _upper_code(v, _COUNTRY_RE, "country")

    @field_validator("vat_rate")
    @classmethod
    def _vat(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else _check_rate(v, "vat_rate")

    @field_validator("source_ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("source_ts doit porter un fuseau horaire")
        return v

    @property
    def effective_vat_country(self) -> str | None:
        """Pays de la TVA facturée : ``vat_country`` sinon ``ship_from_country``."""
        return self.vat_country or self.ship_from_country

    def identity(self) -> ProductIdentity:
        """Identité produit portée par l'offre (non validée : voir catalog)."""
        return ProductIdentity(
            gtin=self.gtin,
            language=self.language,
            extension=self.extension,
            format=self.format,
            content=self.content,
            sealed=self.sealed,
        )


class ProductIdentity(FrozenModel):
    """Clé d'identité produit (BP §6) : GTIN + langue + extension + format + contenu + scellé."""

    gtin: str | None = None
    language: str | None = None
    extension: str | None = None
    format: str | None = None
    content: str | None = None
    sealed: bool | None = None

    def missing_fields(self) -> tuple[str, ...]:
        """Champs d'identité inconnus (langue ``UNKNOWN`` comprise)."""
        missing = []
        for name in ("gtin", "language", "extension", "format", "content", "sealed"):
            value = getattr(self, name)
            if value is None or (name == "language" and value == "UNKNOWN"):
                missing.append(name)
        return tuple(missing)

    @property
    def is_complete(self) -> bool:
        """Vrai si tous les champs d'identité sont connus."""
        return not self.missing_fields()

    @property
    def key(self) -> str:
        """Clé canonique ``GTIN|LANG|EXT|FORMAT|CONTENU|SEALED`` (``?`` = inconnu)."""

        def part(v: str | None) -> str:
            return "?" if v is None else " ".join(v.split()).upper()

        sealed = "?" if self.sealed is None else ("SEALED" if self.sealed else "OPEN")
        return "|".join(
            [part(self.gtin), part(self.language), part(self.extension), part(self.format), part(self.content), sealed]
        )


# ------------------------------------------------------------------------ stock


class PromiseKind(str, Enum):
    """Promesse de disponibilité affichable au client."""

    LOCAL_STOCK = "LOCAL_STOCK"
    """Stock local réel, expédié depuis Genève."""
    PREORDER = "PREORDER"
    """Précommande couverte par une allocation ferme confirmée."""
    UNAVAILABLE = "UNAVAILABLE"
    """Indisponible (éventuellement « alerte réassort »)."""


class AvailabilityPromise(FrozenModel):
    """Disponibilité promise. Le stock amont non alloué n'est **jamais** une promesse client."""

    kind: PromiseKind
    local_qty: int
    preorder_qty: int
    firm_allocation: int
    """Allocation ferme retenue (offres fraîches, pools non additionnés)."""
    restock_signal: bool
    """Signal interne : stock amont frais disponible pour un réassort (jamais affiché client)."""
    reasons: tuple[str, ...] = ()
    excluded_offers: tuple[str, ...] = ()

    @property
    def promisable_qty(self) -> int:
        """Quantité vendable maintenant (local) ou en précommande, selon ``kind``."""
        if self.kind is PromiseKind.LOCAL_STOCK:
            return self.local_qty
        if self.kind is PromiseKind.PREORDER:
            return self.preorder_qty
        return 0


class StockLevel(FrozenModel):
    """Photo du stock local d'un SKU avec sa version (contrôle de concurrence)."""

    sku: str
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0)
    damaged: int = Field(ge=0)
    safety: int = Field(ge=0)
    version: int = Field(ge=0)

    @property
    def sellable(self) -> int:
        """Vendable = physique − réservé − endommagé − sécurité (jamais < 0)."""
        return max(0, self.on_hand - self.reserved - self.damaged - self.safety)


class ReservationStatus(str, Enum):
    """Cycle de vie d'une réservation."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    FULFILLED = "FULFILLED"


class Reservation(FrozenModel):
    """Réservation de stock local pour une commande payée."""

    reservation_id: str
    sku: str
    order_id: str
    qty: int = Field(ge=1)
    status: ReservationStatus
    created_at: datetime
    updated_at: datetime
    refunded_qty: int = Field(default=0, ge=0)


class MovementKind(str, Enum):
    """Type de mouvement du journal de stock (append-only)."""

    RECEIPT = "RECEIPT"
    RESERVE = "RESERVE"
    CANCEL = "CANCEL"
    FULFILL = "FULFILL"
    REFUND_NO_RETURN = "REFUND_NO_RETURN"
    RETURN_RESTOCK = "RETURN_RESTOCK"
    RETURN_DAMAGED = "RETURN_DAMAGED"
    MARK_DAMAGED = "MARK_DAMAGED"
    WRITE_OFF = "WRITE_OFF"
    SET_SAFETY = "SET_SAFETY"


class StockMovement(FrozenModel):
    """Ligne du journal de stock."""

    seq: int
    sku: str
    kind: MovementKind
    qty: int
    ref: str
    at: datetime
    version_after: int


class ReorderCandidate(FrozenModel):
    """Référence évaluée pour un réassort (``unit_cost_chf`` = coût rendu de remplacement)."""

    product_key: str = Field(min_length=1)
    extension: str = Field(min_length=1)
    offer: SupplierOffer
    unit_cost_chf: Decimal
    sellable_qty: int = Field(ge=0)
    on_order_qty: int = Field(default=0, ge=0)
    avg_daily_sales: Decimal = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    safety_stock: int = Field(default=0, ge=0)
    coverage_days: int = Field(default=14, ge=0)
    """Jours de ventes probables couverts au-delà du délai (hypothèse à valider)."""


class ReorderLine(FrozenModel):
    """Ligne de proposition de réassort (jamais une commande)."""

    product_key: str
    extension: str
    supplier_id: str
    supplier_sku: str
    qty: int
    unit_cost_chf: Decimal
    line_cost_chf: Decimal
    reorder_point: Decimal
    position: int
    notes: tuple[str, ...] = ()


class ReorderSkip(FrozenModel):
    """Référence écartée de la proposition, avec motif."""

    product_key: str
    reason: str
    detail: str = ""


class ReorderProposal(FrozenModel):
    """Panier fournisseur **à valider par une personne** (BP §5) — n'engage aucune commande."""

    lines: tuple[ReorderLine, ...]
    skipped: tuple[ReorderSkip, ...]
    total_cost_chf: Decimal
    budget_available_chf: Decimal
    budget_remaining_chf: Decimal
    extension_exposure_after: dict[str, Decimal]
    status: Literal["PROPOSAL_TO_VALIDATE"] = "PROPOSAL_TO_VALIDATE"
    requires_human_validation: Literal[True] = True
    rules_version: str
    inputs_hash: str
    generated_at: datetime


# ------------------------------------------------------------------------ costs


class CostLot(FrozenModel):
    """Lot de réception (coût comptable historique). ``unit_cost`` = coût rendu CHF/unité."""

    lot_id: str = Field(min_length=1)
    product_key: str = Field(min_length=1)
    received_at: datetime
    qty: int = Field(ge=1)
    unit_cost: Decimal = Field(gt=0)
    cost_basis: Literal["ESTIMATE", "INVOICE"] = "ESTIMATE"
    ref: str = ""


class CostVariance(FrozenModel):
    """Écart entre coût estimé à la réception et facture réelle (BP §12)."""

    lot_id: str
    product_key: str
    qty: int
    estimated_unit_cost: Decimal
    actual_unit_cost: Decimal
    delta_unit: Decimal
    delta_total: Decimal
    delta_pct: Decimal
    inventory_adjustment: Decimal
    """Part de l'écart portée sur le stock encore en main (revalorisation du CMP)."""
    cogs_adjustment: Decimal
    """Part de l'écart portée en coût des ventes (unités déjà vendues)."""
    direction: Literal["HIGHER", "LOWER", "EQUAL"]
    flagged: bool
    invoice_ref: str
    at: datetime


class InventoryValuation(FrozenModel):
    """Valorisation au coût moyen pondéré mobile (CMP)."""

    product_key: str
    qty_on_hand: int
    total_value: Decimal
    average_unit_cost: Decimal | None


class ReplacementCost(FrozenModel):
    """Coût de remplacement : coût rendu à la dernière offre fournisseur valide."""

    product_key: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    unit_cost: Decimal = Field(gt=0)
    source_ts: datetime
    offer_ref: str = ""

    @field_validator("source_ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("source_ts doit porter un fuseau horaire")
        return v


class PriceEventKind(str, Enum):
    """Événement de l'historique des prix publics."""

    PROPOSED = "PROPOSED"
    PUBLISHED = "PUBLISHED"
    VALIDATED = "VALIDATED"
    ROLLED_BACK = "ROLLED_BACK"


class PriceEvent(FrozenModel):
    """Ligne append-only de l'historique des décisions de prix."""

    seq: int
    product_key: str
    kind: PriceEventKind
    price: Decimal | None
    at: datetime
    actor: str
    status: DecisionStatus | None = None
    inputs_hash: str | None = None
    rules_version: str | None = None
    note: str = ""
