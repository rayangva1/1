"""Mandat de dépense des agents : contrôle de chaque demande et registre append-only (gouvernance).

La flotte dépense **uniquement dans le mandat écrit et signé** de la propriétaire
(``config/mandate.v1.yaml``, lecture humaine : ``docs/00-pilotage/DELEGATION_AUTONOMIE.md``).
:func:`check` rend l'une de trois issues, avec motifs à codes stables :

* ``APPROVED_WITHIN_MANDATE`` — l'agent finance peut payer par PayPal (passerelle n8n) ;
* ``NEEDS_HUMAN_APPROVAL`` — au-delà du mandat, ou virement bancaire (préparé, validé en 1 clic
  par la propriétaire) ; une demande non validée sous 24 h expire (statu quo sûr) ;
* ``REJECTED`` — interdit (catégorie, moyen de paiement, bénéficiaire hors liste blanche,
  stop-loss actif, donnée périmée, conflit d'idempotence).

Règles (toutes appliquées, motifs cumulés, issue = la plus grave) :

1. **Interdits en dur**, indépendants du mandat : cartes à l'unité, grading, rachats clients,
   achats spéculatifs, produits non FR, financement/dette ; moyens de paiement autres que
   PayPal ou virement préparé ; gel stop-loss global (tout), cash (stock, pub), extension,
   produit, campagne ; trésorerie sous la réserve (1 600 CHF) pour le stock et la pub.
2. **Mandat inactif** (incomplet, non signé, empreinte modifiée, hors période, révoqué) : aucune
   approbation autonome ; tout ce qui n'est pas interdit part en validation humaine.
3. **Mandat actif** : bénéficiaire sur liste blanche (catégorie et moyen autorisés), catégorie
   déléguée, niveau d'autonomie suffisant, plafond par transaction (coût PayPal inclus),
   anti-fractionnement (même bénéficiaire, même jour), plafond mensuel des dépenses
   autonomes, enveloppe de catégorie (cumul depuis l'ouverture du registre, toutes versions
   du mandat) et plafond mensuel de catégorie, plafond de 25 % par extension
   (stock + engagés + demande), réserve cash préservée, solde PayPal suffisant, achat de stock
   adossé à une proposition du moteur (aucun achat spéculatif), langue FR et identité connues.

Montants : ``Decimal`` (``float`` refusé), CHF à 0,01 HALF_UP. Aucune écriture externe ici.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BeforeValidator, Field, StrictInt, ValidationError, field_validator, model_validator

from .errors import PokeshopError
from .models import FrozenModel, canonical_hash, canonical_json
from .stoploss import StopLossStatus

__all__ = [
    "MANDATE_ENV_VAR",
    "MANDATE_FINGERPRINT_ENV_VAR",
    "DEFAULT_MANDATE_PATH",
    "REGISTRY_COLUMNS",
    "MandateError",
    "IdempotencyConflictError",
    "SpendCategory",
    "PaymentMethod",
    "MandateOutcome",
    "SpendReason",
    "SPEND_REASON_LABELS_FR",
    "REASON_OUTCOME",
    "FORBIDDEN_CATEGORIES",
    "NON_DELEGABLE_CATEGORIES",
    "CASH_FREEZE_CATEGORIES",
    "CategoryLimit",
    "SupplierAuthorization",
    "PayPalCostModel",
    "Approval",
    "Mandate",
    "mandate_fingerprint",
    "validate_mandate_data",
    "parse_mandate",
    "load_mandate",
    "default_mandate_path",
    "SpendRequest",
    "TreasurySnapshot",
    "DecisionContext",
    "TransferDraft",
    "MandateDecision",
    "paypal_cost",
    "check",
    "SpendStatus",
    "SpendEntry",
    "LedgerEvent",
    "StatementLine",
    "ReconciliationLine",
    "ReconciliationReport",
    "SpendLedger",
    "main",
]

MANDATE_ENV_VAR = "POKESHOP_MANDATE_PATH"
MANDATE_FINGERPRINT_ENV_VAR = "POKESHOP_MANDATE_FINGERPRINT"
"""Empreinte attendue, placée par la propriétaire dans le coffre : seconde barrière contre une édition du YAML."""
DEFAULT_MANDATE_PATH = Path(__file__).resolve().parents[2] / "config" / "mandate.v1.yaml"
TZ = ZoneInfo("Europe/Zurich")
ZERO = Decimal("0")
CENT = Decimal("0.01")
HUMAN_APPROVAL_TTL = timedelta(hours=24)
_FUTURE_SKEW = timedelta(minutes=5)
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{5,127}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

#: En-tête exact de ``docs/08-agents/modeles/REGISTRE_MANDAT.csv`` (format du registre).
REGISTRY_COLUMNS: tuple[str, ...] = (
    "ligne", "date", "demande_id", "agent_demandeur", "objet", "beneficiaire_id", "categorie_mandat",
    "montant_origine", "devise_origine", "taux_chf", "source_taux", "date_taux", "montant_chf",
    "plafond_transaction_chf", "reste_categorie_avant_chf", "cash_disponible_avant_chf", "stoploss_cash_ok",
    "stoploss_global_ok", "niveau_autonomie", "decision", "ref_decision", "moyen_paiement", "ref_paiement",
    "cle_idempotence", "statut", "rapprochement_date", "rapprochement_resultat", "fictif",
)  # fmt: skip


# --------------------------------------------------------------------------- erreurs


class MandateError(PokeshopError, ValueError):
    """Mandat illisible/invalide ou opération de registre interdite."""


class IdempotencyConflictError(MandateError):
    """Même clé d'idempotence, contenu différent : refus (jamais de double dépense)."""


# --------------------------------------------------------------------------- types


def _strict_decimal(value: Any) -> Any:
    if isinstance(value, (bool, float)):
        raise ValueError(f"{type(value).__name__} interdit : utiliser Decimal, int ou str")
    if isinstance(value, (int, str)):
        try:
            value = Decimal(str(value).strip())
        except ArithmeticError as exc:
            raise ValueError(f"valeur décimale invalide {value!r}") from exc
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("valeur non finie interdite")
    return value


StrictDecimal = Annotated[Decimal, BeforeValidator(_strict_decimal)]


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MandateError(f"{name} doit être un datetime avec fuseau horaire")


def _local_day(at: datetime) -> date:
    return at.astimezone(TZ).date()


def _month(at: datetime) -> tuple[int, int]:
    d = _local_day(at)
    return d.year, d.month


class SpendCategory(str, Enum):
    """Catégories de dépense (enveloppes BP §3 + interdits du modèle d'opération)."""

    STOCK = "STOCK"
    """Produits scellés FR pour la revente (stock local)."""
    ACCESSORIES = "ACCESSORIES"
    SAMPLES = "SAMPLES"
    SITE_TOOLS = "SITE_TOOLS"
    DA_CONTENT = "DA_CONTENT"
    PACKAGING = "PACKAGING"
    SHIPPING = "SHIPPING"
    ADVERTISING = "ADVERTISING"
    ADMIN = "ADMIN"
    """Fiduciaire, juriste, assurances, contrats : toujours la propriétaire."""
    OTHER = "OTHER"
    SINGLE_CARDS = "SINGLE_CARDS"
    GRADING = "GRADING"
    CUSTOMER_BUYBACK = "CUSTOMER_BUYBACK"
    SPECULATIVE = "SPECULATIVE"
    NON_FR_PRODUCTS = "NON_FR_PRODUCTS"
    FINANCING = "FINANCING"
    """Crédit, paiement fractionné, prêt : s'endetter est interdit aux agents."""


FORBIDDEN_CATEGORIES: frozenset[SpendCategory] = frozenset(
    {
        SpendCategory.SINGLE_CARDS,
        SpendCategory.GRADING,
        SpendCategory.CUSTOMER_BUYBACK,
        SpendCategory.SPECULATIVE,
        SpendCategory.NON_FR_PRODUCTS,
        SpendCategory.FINANCING,
    }
)
"""Interdits absolus (hors périmètre BP « Le périmètre de départ » ; aucune dette ; aucun achat spéculatif)."""

NON_DELEGABLE_CATEGORIES: frozenset[SpendCategory] = frozenset({SpendCategory.ADMIN, SpendCategory.OTHER})
CASH_FREEZE_CATEGORIES: frozenset[SpendCategory] = frozenset(
    {SpendCategory.STOCK, SpendCategory.ACCESSORIES, SpendCategory.SAMPLES, SpendCategory.ADVERTISING}
)
"""Bloquées par le stop-loss cash (« plus d'achat ni de pub ») ; étiquettes et emballages restent possibles."""
_STOCK_LIKE = frozenset({SpendCategory.STOCK, SpendCategory.ACCESSORIES})
_LANGUAGE_CHECKED = frozenset({SpendCategory.STOCK, SpendCategory.SAMPLES})


class PaymentMethod(str, Enum):
    """Moyens de paiement ; seuls PAYPAL (compte dédié) et BANK_TRANSFER (préparé) sont admis."""

    PAYPAL = "PAYPAL"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    PAY_LATER = "PAY_LATER"
    CRYPTO = "CRYPTO"
    CASH = "CASH"
    OTHER = "OTHER"


_ALLOWED_METHODS = frozenset({PaymentMethod.PAYPAL, PaymentMethod.BANK_TRANSFER})


class MandateOutcome(str, Enum):
    """Issue d'un contrôle de dépense (gravité croissante)."""

    APPROVED_WITHIN_MANDATE = "APPROVED_WITHIN_MANDATE"
    NEEDS_HUMAN_APPROVAL = "NEEDS_HUMAN_APPROVAL"
    REJECTED = "REJECTED"

    @property
    def severity(self) -> int:
        """0 = approuvé, 2 = refusé."""
        return {"APPROVED_WITHIN_MANDATE": 0, "NEEDS_HUMAN_APPROVAL": 1, "REJECTED": 2}[self.value]


class SpendReason(str, Enum):
    """Codes stables des motifs (libellés : :data:`SPEND_REASON_LABELS_FR`)."""

    # --- refus
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    FORBIDDEN_CATEGORY = "FORBIDDEN_CATEGORY"
    NON_FR_PRODUCT = "NON_FR_PRODUCT"
    PAYMENT_METHOD_FORBIDDEN = "PAYMENT_METHOD_FORBIDDEN"
    STALE_TREASURY_SNAPSHOT = "STALE_TREASURY_SNAPSHOT"
    STALE_STOPLOSS_STATUS = "STALE_STOPLOSS_STATUS"
    STOPLOSS_GLOBAL_FREEZE = "STOPLOSS_GLOBAL_FREEZE"
    STOPLOSS_CASH_FREEZE = "STOPLOSS_CASH_FREEZE"
    CASH_BELOW_RESERVE = "CASH_BELOW_RESERVE"
    STOPLOSS_EXTENSION = "STOPLOSS_EXTENSION"
    STOPLOSS_PRODUCT = "STOPLOSS_PRODUCT"
    STOPLOSS_ADS = "STOPLOSS_ADS"
    SUPPLIER_NOT_WHITELISTED = "SUPPLIER_NOT_WHITELISTED"
    SUPPLIER_CATEGORY_NOT_ALLOWED = "SUPPLIER_CATEGORY_NOT_ALLOWED"
    SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED = "SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED"
    # --- validation humaine
    MANDATE_INCOMPLETE = "MANDATE_INCOMPLETE"
    MANDATE_NOT_SIGNED = "MANDATE_NOT_SIGNED"
    MANDATE_FINGERPRINT_MISMATCH = "MANDATE_FINGERPRINT_MISMATCH"
    MANDATE_NOT_IN_FORCE = "MANDATE_NOT_IN_FORCE"
    MANDATE_REVOKED = "MANDATE_REVOKED"
    CATEGORY_NOT_DELEGATED = "CATEGORY_NOT_DELEGATED"
    AUTONOMY_LEVEL_TOO_LOW = "AUTONOMY_LEVEL_TOO_LOW"
    BANK_TRANSFER_PREPARED = "BANK_TRANSFER_PREPARED"
    ABOVE_TRANSACTION_CAP = "ABOVE_TRANSACTION_CAP"
    SPLIT_SUSPECTED = "SPLIT_SUSPECTED"
    ABOVE_MONTHLY_CAP = "ABOVE_MONTHLY_CAP"
    ABOVE_CATEGORY_ENVELOPE = "ABOVE_CATEGORY_ENVELOPE"
    ABOVE_CATEGORY_MONTHLY_CAP = "ABOVE_CATEGORY_MONTHLY_CAP"
    ABOVE_EXTENSION_CAP = "ABOVE_EXTENSION_CAP"
    EXTENSION_UNKNOWN = "EXTENSION_UNKNOWN"
    PRODUCT_UNKNOWN = "PRODUCT_UNKNOWN"
    LANGUAGE_UNKNOWN = "LANGUAGE_UNKNOWN"
    NO_ENGINE_PROPOSAL = "NO_ENGINE_PROPOSAL"
    CASH_RESERVE_WOULD_BE_BREACHED = "CASH_RESERVE_WOULD_BE_BREACHED"
    PAYPAL_BALANCE_INSUFFICIENT = "PAYPAL_BALANCE_INSUFFICIENT"
    # --- signalements (n'aggravent pas l'issue)
    PAYPAL_COST_ABOVE_THRESHOLD = "PAYPAL_COST_ABOVE_THRESHOLD"
    PAYPAL_FX_CONVERSION = "PAYPAL_FX_CONVERSION"


_R = SpendReason
_REJECT = MandateOutcome.REJECTED
_HUMAN = MandateOutcome.NEEDS_HUMAN_APPROVAL
_WARN = MandateOutcome.APPROVED_WITHIN_MANDATE
_REJECT_REASONS = frozenset(
    {
        _R.IDEMPOTENCY_CONFLICT,
        _R.FORBIDDEN_CATEGORY,
        _R.NON_FR_PRODUCT,
        _R.PAYMENT_METHOD_FORBIDDEN,
        _R.STALE_TREASURY_SNAPSHOT,
        _R.STALE_STOPLOSS_STATUS,
        _R.STOPLOSS_GLOBAL_FREEZE,
        _R.STOPLOSS_CASH_FREEZE,
        _R.CASH_BELOW_RESERVE,
        _R.STOPLOSS_EXTENSION,
        _R.STOPLOSS_PRODUCT,
        _R.STOPLOSS_ADS,
        _R.SUPPLIER_NOT_WHITELISTED,
        _R.SUPPLIER_CATEGORY_NOT_ALLOWED,
        _R.SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED,
    }
)
_WARN_REASONS = frozenset({_R.PAYPAL_COST_ABOVE_THRESHOLD, _R.PAYPAL_FX_CONVERSION})
REASON_OUTCOME: dict[SpendReason, MandateOutcome] = {
    r: _REJECT if r in _REJECT_REASONS else _WARN if r in _WARN_REASONS else _HUMAN for r in SpendReason
}
"""Issue minimale imposée par chaque motif (les signalements n'aggravent pas l'issue)."""

SPEND_REASON_LABELS_FR: dict[SpendReason, str] = {
    _R.IDEMPOTENCY_CONFLICT: "Clé d'idempotence déjà utilisée pour une autre demande : refus (pas de double dépense).",
    _R.FORBIDDEN_CATEGORY: "Catégorie interdite (cartes à l'unité, grading, rachats, spéculation, non-FR, dette).",
    _R.NON_FR_PRODUCT: "Produit non FR : hors périmètre du BP.",
    _R.PAYMENT_METHOD_FORBIDDEN: "Moyen de paiement interdit : seuls PayPal dédié et virement préparé sont admis.",
    _R.STALE_TREASURY_SNAPSHOT: "Photo de trésorerie périmée ou datée du futur : recalculer.",
    _R.STALE_STOPLOSS_STATUS: "État du stop-loss périmé ou daté du futur : réévaluer.",
    _R.STOPLOSS_GLOBAL_FREEZE: "Stop-loss global actif : tout est gelé jusqu'au réarmement par la propriétaire.",
    _R.STOPLOSS_CASH_FREEZE: "Stop-loss cash actif : plus d'achat ni de publicité.",
    _R.CASH_BELOW_RESERVE: "Cash disponible déjà sous la réserve : plus d'achat ni de publicité.",
    _R.STOPLOSS_EXTENSION: "Extension gelée par le stop-loss : aucun réassort.",
    _R.STOPLOSS_PRODUCT: "Référence bloquée par le stop-loss produit : aucun achat.",
    _R.STOPLOSS_ADS: "Campagne coupée par le stop-loss : aucune dépense publicitaire.",
    _R.SUPPLIER_NOT_WHITELISTED: "Bénéficiaire hors liste blanche du mandat : interdit (ajout = décision C08).",
    _R.SUPPLIER_CATEGORY_NOT_ALLOWED: "Catégorie non autorisée pour ce bénéficiaire.",
    _R.SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED: "Moyen de paiement non autorisé pour ce bénéficiaire.",
    _R.MANDATE_INCOMPLETE: "Mandat incomplet (montants à remplir) : validation humaine.",
    _R.MANDATE_NOT_SIGNED: "Mandat non signé : aucune dépense autonome.",
    _R.MANDATE_FINGERPRINT_MISMATCH: "Mandat modifié après signature (empreinte) : nouvelle signature requise.",
    _R.MANDATE_NOT_IN_FORCE: "Mandat hors période de validité.",
    _R.MANDATE_REVOKED: "Mandat révoqué par la propriétaire.",
    _R.CATEGORY_NOT_DELEGATED: "Catégorie non déléguée au mandat : validation humaine.",
    _R.AUTONOMY_LEVEL_TOO_LOW: "Niveau d'autonomie insuffisant pour cette catégorie (BP §13).",
    _R.BANK_TRANSFER_PREPARED: "Virement préparé : validation de la propriétaire en 1 clic.",
    _R.ABOVE_TRANSACTION_CAP: "Montant (coût de paiement inclus) au-dessus du plafond par transaction.",
    _R.SPLIT_SUSPECTED: "Cumul du jour chez ce bénéficiaire au-dessus du plafond : fractionnement suspecté.",
    _R.ABOVE_MONTHLY_CAP: "Plafond mensuel des dépenses autonomes atteint.",
    _R.ABOVE_CATEGORY_ENVELOPE: "Enveloppe de la catégorie dépassée.",
    _R.ABOVE_CATEGORY_MONTHLY_CAP: "Plafond mensuel de la catégorie dépassé.",
    _R.ABOVE_EXTENSION_CAP: "Plafond par extension (25 % du budget stock) dépassé : exception C18.",
    _R.EXTENSION_UNKNOWN: "Extension non renseignée : plafond par extension non vérifiable.",
    _R.PRODUCT_UNKNOWN: "Référence produit non renseignée.",
    _R.LANGUAGE_UNKNOWN: "Langue du produit inconnue (BP §5 : champ inconnu = brouillon).",
    _R.NO_ENGINE_PROPOSAL: "Achat de stock sans proposition de réassort du moteur : pas d'achat spéculatif.",
    _R.CASH_RESERVE_WOULD_BE_BREACHED: "La dépense entamerait la réserve de 1 600 CHF : décision humaine.",
    _R.PAYPAL_BALANCE_INSUFFICIENT: "Solde PayPal dédié insuffisant ou inconnu : rechargement par la propriétaire.",
    _R.PAYPAL_COST_ABOVE_THRESHOLD: "Coût PayPal estimé au-dessus du seuil : virement recommandé.",
    _R.PAYPAL_FX_CONVERSION: "Conversion de devise PayPal : marge de change ajoutée au coût.",
}


# ----------------------------------------------------------------------- mandat


class CategoryLimit(FrozenModel):
    """Délégation d'une catégorie : enveloppe totale, plafond mensuel, niveau d'autonomie requis."""

    category: SpendCategory
    envelope_chf: StrictDecimal | None = Field(default=None, ge=0)
    per_month_chf: StrictDecimal | None = Field(default=None, ge=0)
    min_autonomy_level: StrictInt = Field(ge=1, le=4)


class SupplierAuthorization(FrozenModel):
    """Bénéficiaire de la liste blanche (validé par la propriétaire, intervention C08)."""

    supplier_id: str
    label: str = Field(min_length=1)
    categories: tuple[SpendCategory, ...] = Field(min_length=1)
    payment_methods: tuple[PaymentMethod, ...] = Field(min_length=1)
    max_per_transaction_chf: StrictDecimal | None = Field(default=None, gt=0)
    validated_on: date
    due_diligence_ref: str = Field(min_length=3)
    payee_ref: str = Field(min_length=3)
    """Référence des coordonnées de paiement dans le coffre (jamais l'IBAN ou l'adresse elle-même)."""

    @field_validator("supplier_id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"supplier_id invalide : {v!r}")
        return v

    @field_validator("payment_methods")
    @classmethod
    def _methods(cls, v: tuple[PaymentMethod, ...]) -> tuple[PaymentMethod, ...]:
        bad = [m.value for m in v if m not in _ALLOWED_METHODS]
        if bad:
            raise ValueError(f"moyens de paiement interdits : {', '.join(bad)}")
        return v


class PayPalCostModel(FrozenModel):
    """Coût estimé d'un paiement PayPal (hypothèses à vérifier sur la grille tarifaire officielle)."""

    fee_pct: StrictDecimal = Field(ge=0, lt=Decimal("0.2"))
    fee_fixed_chf: StrictDecimal = Field(ge=0, le=10)
    fx_conversion_pct: StrictDecimal = Field(ge=0, lt=Decimal("0.2"))
    flag_above_pct: StrictDecimal = Field(ge=0, lt=1)


class Approval(FrozenModel):
    """Signature du mandat. ``fingerprint_sha256`` = :func:`mandate_fingerprint` du document signé."""

    approved_by: str | None = None
    approved_at: datetime | None = None
    fingerprint_sha256: str | None = None
    revoked_at: datetime | None = None

    @field_validator("approved_at", "revoked_at", mode="before")
    @classmethod
    def _dt(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = date.fromisoformat(v) if len(v.strip()) == 10 else datetime.fromisoformat(v)
        if isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, time(0), tzinfo=TZ)
        if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("date de signature/révocation sans fuseau horaire")
        return v

    @field_validator("approved_by")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


_LIMIT_KEYS = {
    "per_transaction_chf",
    "per_month_chf",
    "stock_budget_chf",
    "extension_max_share",
    "cash_reserve_chf",
    "ads_daily_cap_chf",
    "email_daily_send_quota",
    "snapshot_max_age_minutes",
}
_REQUIRED_LIMITS = (
    "per_transaction_chf",
    "per_month_chf",
    "stock_budget_chf",
    "ads_daily_cap_chf",
    "email_daily_send_quota",
)
_TOP_KEYS = {
    "mandate_version",
    "status",
    "source",
    "valid_from",
    "valid_until",
    "limits",
    "categories",
    "paypal",
    "suppliers",
    "extra_forbidden_categories",
    "approval",
}


class Mandate(FrozenModel):
    """Mandat chargé ; ``inactive_reasons`` dit pourquoi les agents ne peuvent pas dépenser seuls."""

    mandate_version: str
    status: str
    source: str = ""
    valid_from: date | None = None
    valid_until: date | None = None
    per_transaction_chf: StrictDecimal | None = Field(default=None, gt=0)
    per_month_chf: StrictDecimal | None = Field(default=None, gt=0)
    stock_budget_chf: StrictDecimal | None = Field(default=None, ge=0)
    extension_max_share: StrictDecimal = Field(gt=0, le=1)
    cash_reserve_chf: StrictDecimal = Field(ge=0)
    ads_daily_cap_chf: StrictDecimal | None = Field(default=None, ge=0)
    email_daily_send_quota: StrictInt | None = Field(default=None, ge=0)
    snapshot_max_age_minutes: StrictInt = Field(default=60, ge=1, le=1440)
    categories: tuple[CategoryLimit, ...] = ()
    suppliers: tuple[SupplierAuthorization, ...] = ()
    extra_forbidden_categories: tuple[SpendCategory, ...] = ()
    paypal: PayPalCostModel
    approval: Approval = Approval()
    fingerprint: str
    """Empreinte recalculée du contenu (hors empreinte et révocation)."""
    expected_fingerprint: str | None = None
    """Empreinte attendue lue dans le coffre (``POKESHOP_MANDATE_FINGERPRINT``), si configurée."""
    source_path: str = "<memory>"
    content_sha256: str = ""

    @model_validator(mode="after")
    def _check(self) -> Mandate:
        cats = [c.category for c in self.categories]
        if len(set(cats)) != len(cats):
            raise ValueError("catégorie en double")
        bad = [c.value for c in cats if c in FORBIDDEN_CATEGORIES or c in NON_DELEGABLE_CATEGORIES]
        if bad:
            raise ValueError(f"catégories non délégables : {', '.join(bad)}")
        ids = [s.supplier_id for s in self.suppliers]
        if len(set(ids)) != len(ids):
            raise ValueError("bénéficiaire en double")
        for s in self.suppliers:
            outside = [c.value for c in s.categories if c not in cats]
            if outside:
                raise ValueError(f"{s.supplier_id} : catégories non déléguées au mandat {', '.join(outside)}")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until antérieure à valid_from")
        return self

    def category(self, category: SpendCategory) -> CategoryLimit | None:
        """Délégation de la catégorie (None = non déléguée)."""
        return next((c for c in self.categories if c.category is category), None)

    def supplier(self, supplier_id: str) -> SupplierAuthorization | None:
        """Bénéficiaire autorisé (None = hors liste blanche)."""
        return next((s for s in self.suppliers if s.supplier_id == supplier_id), None)

    def missing_fields(self) -> tuple[str, ...]:
        """Champs à remplir avant signature."""
        out = [f"limits.{k}" for k in _REQUIRED_LIMITS if getattr(self, k) is None]
        for k in ("valid_from", "valid_until"):
            if getattr(self, k) is None:
                out.append(k)
        out += [f"categories.{c.category.value}.envelope_chf" for c in self.categories if c.envelope_chf is None]
        return tuple(out)

    @property
    def is_signed(self) -> bool:
        """Signé : nom, date et empreinte présents et conformes au contenu."""
        a = self.approval
        return bool(a.approved_by and a.approved_at and a.fingerprint_sha256 == self.fingerprint)

    def inactive_reasons(self, now: datetime) -> list[SpendReason]:
        """Motifs empêchant toute approbation autonome à ``now`` (liste vide = mandat actif)."""
        _require_aware(now, "now")
        reasons: list[SpendReason] = []
        if self.missing_fields():
            reasons.append(SpendReason.MANDATE_INCOMPLETE)
        a = self.approval
        if not (a.approved_by and a.approved_at and a.fingerprint_sha256):
            reasons.append(SpendReason.MANDATE_NOT_SIGNED)
        elif a.fingerprint_sha256 != self.fingerprint or (
            self.expected_fingerprint is not None and self.expected_fingerprint != self.fingerprint
        ):
            reasons.append(SpendReason.MANDATE_FINGERPRINT_MISMATCH)
        elif a.approved_at is not None and a.approved_at > now:
            reasons.append(SpendReason.MANDATE_NOT_SIGNED)
        if a.revoked_at is not None and a.revoked_at <= now:
            reasons.append(SpendReason.MANDATE_REVOKED)
        today = _local_day(now)
        if (self.valid_from and today < self.valid_from) or (self.valid_until and today > self.valid_until):
            reasons.append(SpendReason.MANDATE_NOT_IN_FORCE)
        return reasons

    def is_active(self, now: datetime) -> bool:
        """Vrai si les agents peuvent dépenser seuls dans ce mandat à ``now``."""
        return not self.inactive_reasons(now)


def mandate_fingerprint(data: Mapping[str, Any]) -> str:
    """sha256 du contenu canonique du mandat, hors ``approval.fingerprint_sha256`` et ``approval.revoked_at``.

    Toute modification d'un plafond, d'un bénéficiaire, d'une date ou du signataire change
    l'empreinte et désactive le mandat jusqu'à nouvelle signature.
    """
    content = {k: v for k, v in data.items() if k != "approval"}
    approval = dict(data.get("approval") or {})
    content["approval"] = {k: approval.get(k) for k in ("approved_by", "approved_at")}
    try:
        return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise MandateError(f"mandat non canonisable : {exc}") from exc


def _date_field(value: Any, where: str, errors: list[str]) -> None:
    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
            return
        except ValueError:
            pass
    errors.append(f"{where} : date AAAA-MM-JJ ou null attendue (reçu {value!r})")


def _walk_floats(obj: Any, where: str, errors: list[str]) -> None:
    if isinstance(obj, float):
        errors.append(f"{where} : nombre à virgule flottante interdit (écrire le montant entre guillemets)")
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            _walk_floats(v, f"{where}.{k}" if where else str(k), errors)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_floats(v, f"{where}[{i}]", errors)


def _build(data: Mapping[str, Any], errors: list[str], **extra: Any) -> Mandate | None:
    limits = dict(data.get("limits") or {})
    categories = []
    for name, body in (data.get("categories") or {}).items():
        categories.append({"category": name, **dict(body or {})})
    payload = {
        "mandate_version": data.get("mandate_version"),
        "status": data.get("status"),
        "source": data.get("source") or "",
        "valid_from": data.get("valid_from"),
        "valid_until": data.get("valid_until"),
        **limits,
        "categories": categories,
        "suppliers": list(data.get("suppliers") or []),
        "extra_forbidden_categories": list(data.get("extra_forbidden_categories") or []),
        "paypal": data.get("paypal"),
        "approval": data.get("approval") or {},
        "fingerprint": mandate_fingerprint(data),
        **extra,
    }
    try:
        return Mandate.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "mandat"
            errors.append(f"{loc} : {err['msg']}")
        return None


def validate_mandate_data(data: Any) -> list[str]:
    """Erreurs de structure (en français) d'un document de mandat ; vide si lisible (même non signé)."""
    if not isinstance(data, Mapping):
        return ["document de mandat : mapping YAML attendu"]
    errors: list[str] = []
    unknown = set(map(str, data)) - _TOP_KEYS
    if unknown:
        errors.append(f"clés inconnues : {', '.join(sorted(unknown))}")
    version = data.get("mandate_version")
    if not isinstance(version, str) or not re.match(r"^\S{1,64}$", version):
        errors.append("mandate_version : chaîne non vide sans espace obligatoire")
    if not isinstance(data.get("status"), str) or not data.get("status"):
        errors.append("status : chaîne obligatoire")
    for key in ("valid_from", "valid_until"):
        _date_field(data.get(key), key, errors)
    for key, kind in (("limits", Mapping), ("categories", Mapping), ("paypal", Mapping), ("approval", Mapping)):
        if not isinstance(data.get(key), kind):
            errors.append(f"{key} : section manquante ou mal formée")
    for key in ("suppliers", "extra_forbidden_categories"):
        if key in data and data[key] is not None and not isinstance(data[key], list):
            errors.append(f"{key} : liste attendue")
    limits = data.get("limits")
    if isinstance(limits, Mapping):
        extra = set(map(str, limits)) - _LIMIT_KEYS
        missing = _LIMIT_KEYS - set(map(str, limits))
        if extra:
            errors.append(f"limits : clés inconnues {', '.join(sorted(extra))}")
        if missing:
            errors.append(f"limits : clés manquantes {', '.join(sorted(missing))}")
    _walk_floats(data, "", errors)
    if errors:
        return errors
    try:
        _build(data, errors)
    except MandateError as exc:
        errors.append(str(exc))
    return errors


def parse_mandate(
    data: Mapping[str, Any],
    *,
    source: str = "<memory>",
    content_sha256: str = "",
    expected_fingerprint: str | None = None,
) -> Mandate:
    """Valide et construit le mandat ; :class:`MandateError` si illisible (un gabarit non signé est lisible)."""
    errors = validate_mandate_data(data)
    if errors:
        raise MandateError("Mandat invalide : " + " ; ".join(errors))
    if expected_fingerprint is not None:
        expected_fingerprint = expected_fingerprint.strip().lower()
        if not _SHA256_RE.match(expected_fingerprint):
            raise MandateError("empreinte attendue invalide (sha256 hexadécimal)")
    mandate = _build(
        data, errors, source_path=source, content_sha256=content_sha256, expected_fingerprint=expected_fingerprint
    )
    if mandate is None:  # pragma: no cover - couvert par validate_mandate_data
        raise MandateError("Mandat invalide : " + " ; ".join(errors))
    return mandate


def default_mandate_path() -> Path:
    """Chemin du mandat : ``POKESHOP_MANDATE_PATH`` sinon ``config/mandate.v1.yaml``."""
    env = os.environ.get(MANDATE_ENV_VAR)
    return Path(env) if env else DEFAULT_MANDATE_PATH


def _read_yaml(path: str | Path | None) -> tuple[Mapping[str, Any], Path, str]:
    target = Path(path) if path is not None else default_mandate_path()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise MandateError(f"mandat illisible : {target} ({exc.strerror})") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise MandateError(f"YAML invalide : {target}") from exc
    if not isinstance(data, Mapping):
        raise MandateError("document de mandat : mapping YAML attendu")
    return data, target, hashlib.sha256(raw).hexdigest()


def load_mandate(path: str | Path | None = None, *, expected_fingerprint: str | None = None) -> Mandate:
    """Charge le mandat. Empreinte attendue : argument, sinon variable ``POKESHOP_MANDATE_FINGERPRINT``."""
    data, target, sha = _read_yaml(path)
    expected = expected_fingerprint if expected_fingerprint is not None else os.environ.get(MANDATE_FINGERPRINT_ENV_VAR)
    return parse_mandate(data, source=str(target), content_sha256=sha, expected_fingerprint=expected or None)


# --------------------------------------------------------------------- demande


class SpendRequest(FrozenModel):
    """Demande de dépense d'un agent (gabarit ``docs/08-agents/modeles/DEMANDE_ENGAGEMENT.md``)."""

    amount: StrictDecimal = Field(gt=0)
    """Montant TTC facturé par le bénéficiaire, dans ``currency`` (source obligatoire)."""
    currency: str
    supplier_id: str = Field(min_length=1)
    category: SpendCategory
    extension: str | None = None
    payment_method: PaymentMethod
    purpose: str = Field(min_length=3)
    idempotency_key: str
    requested_by: str = Field(min_length=2)
    requested_at: datetime
    amount_source: str = Field(min_length=3)
    """Devis n°, facture, page consultée (URL + date) — jamais un montant supposé."""
    product_key: str | None = None
    product_language: str | None = None
    campaign_id: str | None = None
    justification_ref: str | None = None
    """Référence de la proposition du moteur (ex. ``ReorderProposal.inputs_hash``) pour un achat de stock."""
    fx_rate_to_chf: StrictDecimal | None = Field(default=None, gt=0)
    fx_source: str | None = None
    fx_date: date | None = None
    fictif: bool = False

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        code = v.strip().upper()
        if not _CURRENCY_RE.match(code):
            raise ValueError(f"devise ISO 4217 attendue : {v!r}")
        return code

    @field_validator("idempotency_key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not _KEY_RE.match(v):
            raise ValueError("clé d'idempotence : 6 à 128 caractères [A-Za-z0-9_.:-]")
        return v

    @field_validator("product_language")
    @classmethod
    def _lang(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        return None if v in ("", "UNKNOWN") else v

    @field_validator("extension", "product_key", "campaign_id", "justification_ref")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @field_validator("requested_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "requested_at")

    @model_validator(mode="after")
    def _fx(self) -> SpendRequest:
        if self.currency == "CHF":
            if self.fx_rate_to_chf not in (None, Decimal(1)):
                raise ValueError("devise CHF : taux de change 1 ou absent")
        elif self.fx_rate_to_chf is None or not self.fx_source or self.fx_date is None:
            raise ValueError("devise étrangère : taux, source et date obligatoires (l'IA ne choisit pas un taux)")
        return self

    @property
    def amount_chf(self) -> Decimal:
        """Montant converti en CHF (0,01 HALF_UP)."""
        rate = self.fx_rate_to_chf if self.fx_rate_to_chf is not None else Decimal(1)
        return _q2(self.amount * rate)

    @property
    def request_hash(self) -> str:
        """Empreinte canonique de la demande (contrôle d'idempotence)."""
        return canonical_hash(self)


class TreasurySnapshot(FrozenModel):
    """Photo financière au moment de la demande (calculée par l'agent finance)."""

    as_of: datetime
    cash_available_chf: StrictDecimal
    """Banque + PayPal − précommandes encaissées non livrées (avant engagements non débités)."""
    paypal_balance_chf: StrictDecimal | None = None
    """Solde du compte PayPal dédié (None = inconnu)."""
    extension_exposure_chf: dict[str, StrictDecimal] = Field(default_factory=dict)
    """Par extension : stock au coût historique + achats engagés non reçus, à ``as_of``."""

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")


class DecisionContext(FrozenModel):
    """Chiffres utilisés par la décision (recopiés dans le registre)."""

    per_transaction_cap_chf: Decimal | None = None
    monthly_cap_chf: Decimal | None = None
    month_autonomous_before_chf: Decimal = ZERO
    category_envelope_chf: Decimal | None = None
    category_committed_before_chf: Decimal = ZERO
    category_remaining_before_chf: Decimal | None = None
    cash_available_before_chf: Decimal = ZERO
    paypal_available_before_chf: Decimal | None = None
    extension_exposure_before_chf: Decimal | None = None
    extension_cap_chf: Decimal | None = None
    stoploss_cash_ok: bool = True
    stoploss_global_ok: bool = True
    autonomy_level: int = 1


class TransferDraft(FrozenModel):
    """Virement **préparé** pour validation humaine en 1 clic (aucune coordonnée bancaire ici)."""

    beneficiary_id: str
    payee_ref: str | None
    """Référence des coordonnées au coffre (None : bénéficiaire hors mandat, à compléter par la propriétaire)."""
    amount: Decimal
    currency: str
    amount_chf: Decimal
    reference: str
    purpose: str
    status: Literal["PREPARED_FOR_HUMAN_VALIDATION"] = "PREPARED_FOR_HUMAN_VALIDATION"


class MandateDecision(FrozenModel):
    """Décision tracée d'une demande de dépense."""

    outcome: MandateOutcome
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    amount_chf: Decimal
    payment_cost_chf: Decimal
    effective_cost_chf: Decimal
    mandate_version: str
    mandate_fingerprint: str
    request_hash: str
    idempotency_key: str
    decided_at: datetime
    context: DecisionContext
    transfer_draft: TransferDraft | None = None
    replayed: bool = False

    @property
    def decision_ref(self) -> str:
        """Référence courte et stable de la décision (hors indicateur de rejeu)."""
        return canonical_hash(self.replace(replayed=False))[:16]

    def has(self, reason: SpendReason | str) -> bool:
        """Vrai si le motif (ou signalement) est présent."""
        code = reason.value if isinstance(reason, SpendReason) else reason
        return code in self.reasons or code in self.warnings

    @property
    def labels_fr(self) -> list[str]:
        """Libellés français des motifs et signalements."""
        return [SPEND_REASON_LABELS_FR[SpendReason(c)] for c in (*self.reasons, *self.warnings)]


def paypal_cost(amount_chf: Decimal, currency: str, model: PayPalCostModel) -> Decimal:
    """Coût estimé d'un paiement PayPal : r × montant + fixe (+ marge de change si devise ≠ CHF)."""
    cost = _q2(amount_chf * model.fee_pct) + model.fee_fixed_chf
    if currency != "CHF":
        cost += _q2(amount_chf * model.fx_conversion_pct)
    return _q2(cost)


class _Verdict:
    def __init__(self) -> None:
        self.reasons: list[SpendReason] = []
        self.warnings: list[SpendReason] = []
        self.messages: list[str] = []

    def add(self, reason: SpendReason, message: str | None = None) -> None:
        bucket = self.warnings if REASON_OUTCOME[reason] is _WARN else self.reasons
        if reason not in bucket:
            bucket.append(reason)
        self.messages.append(message or SPEND_REASON_LABELS_FR[reason])

    @property
    def outcome(self) -> MandateOutcome:
        worst = MandateOutcome.APPROVED_WITHIN_MANDATE
        for r in self.reasons:
            if REASON_OUTCOME[r].severity > worst.severity:
                worst = REASON_OUTCOME[r]
        return worst


def _stale(as_of: datetime, now: datetime, max_age: timedelta) -> bool:
    return as_of - now > _FUTURE_SKEW or now - as_of > max_age


def _fmt(value: Decimal | None) -> str:
    return "—" if value is None else f"{_q2(value)} CHF"


def check(
    request: SpendRequest,
    mandate: Mandate,
    ledger: SpendLedger,
    stoploss_state: StopLossStatus,
    treasury_snapshot: TreasurySnapshot,
    *,
    now: datetime | None = None,
) -> MandateDecision:
    """Contrôle une demande de dépense contre le mandat, le registre, le stop-loss et la trésorerie.

    Idempotent : une clé déjà enregistrée renvoie la décision d'origine (``replayed=True``) si la
    demande est identique, ``REJECTED`` / ``IDEMPOTENCY_CONFLICT`` sinon. ``now`` = date de la
    demande par défaut. Ne modifie pas le registre : appeler ensuite :meth:`SpendLedger.record`.
    """
    at = now if now is not None else request.requested_at
    _require_aware(at, "now")
    request_hash = request.request_hash
    existing = ledger.get(request.idempotency_key)
    amount_chf = request.amount_chf
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing.decision.replace(replayed=True)
        return MandateDecision(
            outcome=MandateOutcome.REJECTED,
            reasons=(SpendReason.IDEMPOTENCY_CONFLICT.value,),
            messages=(SPEND_REASON_LABELS_FR[SpendReason.IDEMPOTENCY_CONFLICT],),
            amount_chf=amount_chf,
            payment_cost_chf=ZERO,
            effective_cost_chf=amount_chf,
            mandate_version=mandate.mandate_version,
            mandate_fingerprint=mandate.fingerprint,
            request_hash=request_hash,
            idempotency_key=request.idempotency_key,
            decided_at=at,
            context=DecisionContext(autonomy_level=stoploss_state.autonomy_level),
        )

    v = _Verdict()
    cat = request.category
    max_age = timedelta(minutes=mandate.snapshot_max_age_minutes)

    # -- coût effectif (PayPal : frais + change ajoutés au montant)
    cost = ZERO
    if request.payment_method is PaymentMethod.PAYPAL:
        cost = paypal_cost(amount_chf, request.currency, mandate.paypal)
        if request.currency != "CHF":
            v.add(SpendReason.PAYPAL_FX_CONVERSION)
        if cost > amount_chf * mandate.paypal.flag_above_pct:
            v.add(
                SpendReason.PAYPAL_COST_ABOVE_THRESHOLD,
                f"Coût PayPal estimé {_fmt(cost)} pour {_fmt(amount_chf)} "
                f"(> {mandate.paypal.flag_above_pct * 100} %) : "
                "pour une commande de stock, préférer le virement préparé.",
            )
    effective = amount_chf + cost

    # -- 1. interdits en dur (indépendants du mandat)
    if cat in FORBIDDEN_CATEGORIES or cat in mandate.extra_forbidden_categories:
        v.add(SpendReason.FORBIDDEN_CATEGORY)
    if cat in _LANGUAGE_CHECKED and request.product_language is not None and request.product_language != "FR":
        v.add(SpendReason.NON_FR_PRODUCT, f"Langue {request.product_language} : seuls les produits FR sont achetés.")
    if request.payment_method not in _ALLOWED_METHODS:
        v.add(SpendReason.PAYMENT_METHOD_FORBIDDEN)
    treasury_stale = _stale(treasury_snapshot.as_of, at, max_age)
    if treasury_stale:
        v.add(SpendReason.STALE_TREASURY_SNAPSHOT)
    if _stale(stoploss_state.as_of, at, max_age):
        v.add(SpendReason.STALE_STOPLOSS_STATUS)
    if stoploss_state.global_frozen:
        v.add(SpendReason.STOPLOSS_GLOBAL_FREEZE)
    if cat in CASH_FREEZE_CATEGORIES and stoploss_state.purchases_and_ads_frozen:
        v.add(SpendReason.STOPLOSS_CASH_FREEZE)
    if cat in _STOCK_LIKE and request.extension and request.extension in stoploss_state.no_reorder_extensions:
        v.add(SpendReason.STOPLOSS_EXTENSION)
    if cat in _STOCK_LIKE and request.product_key and request.product_key in stoploss_state.blocked_products:
        v.add(SpendReason.STOPLOSS_PRODUCT)
    if cat is SpendCategory.ADVERTISING and (
        stoploss_state.ads_globally_cut or (request.campaign_id and request.campaign_id in stoploss_state.cut_campaigns)
    ):
        v.add(SpendReason.STOPLOSS_ADS)

    unsettled = ledger.unsettled_commitments(since=treasury_snapshot.as_of)
    cash_before = treasury_snapshot.cash_available_chf - unsettled
    reserve = mandate.cash_reserve_chf
    if treasury_snapshot.cash_available_chf < reserve and cat in CASH_FREEZE_CATEGORIES:
        v.add(
            SpendReason.CASH_BELOW_RESERVE,
            f"Cash disponible {_fmt(treasury_snapshot.cash_available_chf)} < réserve {_fmt(reserve)}.",
        )
    elif cash_before - effective < reserve:
        v.add(
            SpendReason.CASH_RESERVE_WOULD_BE_BREACHED,
            f"Cash après dépense {_fmt(cash_before - effective)} < réserve {_fmt(reserve)}.",
        )

    ctx: dict[str, Any] = {
        "cash_available_before_chf": cash_before,
        "stoploss_cash_ok": (
            not stoploss_state.purchases_and_ads_frozen and treasury_snapshot.cash_available_chf >= reserve
        ),
        "stoploss_global_ok": not stoploss_state.global_frozen,
        "autonomy_level": stoploss_state.autonomy_level,
    }
    supplier = mandate.supplier(request.supplier_id)

    # -- 2. mandat inactif : aucune approbation autonome
    inactive = mandate.inactive_reasons(at)
    for reason in inactive:
        detail = None
        if reason is SpendReason.MANDATE_INCOMPLETE:
            detail = "Mandat incomplet : " + ", ".join(mandate.missing_fields())
        v.add(reason, detail)

    # -- 3. règles du mandat actif
    if not inactive:
        if supplier is None:
            v.add(SpendReason.SUPPLIER_NOT_WHITELISTED, f"Bénéficiaire {request.supplier_id} hors liste blanche.")
        else:
            if cat not in supplier.categories:
                v.add(SpendReason.SUPPLIER_CATEGORY_NOT_ALLOWED)
            if request.payment_method in _ALLOWED_METHODS and request.payment_method not in supplier.payment_methods:
                v.add(SpendReason.SUPPLIER_PAYMENT_METHOD_NOT_ALLOWED)
        limit = mandate.category(cat)
        if limit is None:
            if cat not in FORBIDDEN_CATEGORIES:
                v.add(SpendReason.CATEGORY_NOT_DELEGATED)
        else:
            if stoploss_state.autonomy_level < limit.min_autonomy_level:
                v.add(
                    SpendReason.AUTONOMY_LEVEL_TOO_LOW,
                    f"Niveau {stoploss_state.autonomy_level} < niveau {limit.min_autonomy_level} "
                    f"requis pour {cat.value}.",
                )
            committed = ledger.committed(category=cat)  # budget cumulé, toutes versions du mandat
            ctx["category_envelope_chf"] = limit.envelope_chf
            ctx["category_committed_before_chf"] = committed
            if limit.envelope_chf is not None:
                ctx["category_remaining_before_chf"] = limit.envelope_chf - committed
                if committed + effective > limit.envelope_chf:
                    v.add(
                        SpendReason.ABOVE_CATEGORY_ENVELOPE,
                        f"Enveloppe {cat.value} : {_fmt(committed)} engagés + {_fmt(effective)} "
                        f"> {_fmt(limit.envelope_chf)}.",
                    )
            if limit.per_month_chf is not None:
                month_cat = ledger.committed(category=cat, month=_month(at))
                if month_cat + effective > limit.per_month_chf:
                    v.add(
                        SpendReason.ABOVE_CATEGORY_MONTHLY_CAP,
                        f"Mois {cat.value} : {_fmt(month_cat)} + {_fmt(effective)} > {_fmt(limit.per_month_chf)}.",
                    )
        if request.payment_method is PaymentMethod.BANK_TRANSFER:
            v.add(SpendReason.BANK_TRANSFER_PREPARED)
        caps = [c for c in (mandate.per_transaction_chf, supplier.max_per_transaction_chf if supplier else None) if c]
        tx_cap = min(caps) if caps else None
        ctx["per_transaction_cap_chf"] = tx_cap
        if tx_cap is not None:
            if effective > tx_cap:
                v.add(SpendReason.ABOVE_TRANSACTION_CAP, f"{_fmt(effective)} > plafond {_fmt(tx_cap)}.")
            else:
                day_total = ledger.committed(supplier_id=request.supplier_id, day=_local_day(at), autonomous_only=True)
                if day_total + effective > tx_cap:
                    v.add(
                        SpendReason.SPLIT_SUSPECTED,
                        f"{request.supplier_id} : {_fmt(day_total)} déjà approuvés aujourd'hui + {_fmt(effective)} "
                        f"> plafond {_fmt(tx_cap)}.",
                    )
        month_total = ledger.committed(month=_month(at), autonomous_only=True)
        ctx["monthly_cap_chf"] = mandate.per_month_chf
        ctx["month_autonomous_before_chf"] = month_total
        if mandate.per_month_chf is not None and month_total + effective > mandate.per_month_chf:
            v.add(
                SpendReason.ABOVE_MONTHLY_CAP,
                f"Mois : {_fmt(month_total)} + {_fmt(effective)} > plafond {_fmt(mandate.per_month_chf)}.",
            )
        if request.payment_method is PaymentMethod.PAYPAL:
            paypal_pending = ledger.unsettled_commitments(since=treasury_snapshot.as_of, method=PaymentMethod.PAYPAL)
            if treasury_snapshot.paypal_balance_chf is None:
                v.add(SpendReason.PAYPAL_BALANCE_INSUFFICIENT, "Solde PayPal inconnu : à relever avant paiement.")
            else:
                available = treasury_snapshot.paypal_balance_chf - paypal_pending
                ctx["paypal_available_before_chf"] = available
                if available < effective:
                    v.add(
                        SpendReason.PAYPAL_BALANCE_INSUFFICIENT,
                        f"Solde PayPal disponible {_fmt(available)} < {_fmt(effective)}.",
                    )

    # -- exigences propres au stock (achat adossé au moteur, identité FR, plafond par extension)
    if cat in _STOCK_LIKE:
        if request.product_key is None:
            v.add(SpendReason.PRODUCT_UNKNOWN)
        if request.justification_ref is None:
            v.add(SpendReason.NO_ENGINE_PROPOSAL)
    if cat is SpendCategory.STOCK:
        if request.product_language is None:
            v.add(SpendReason.LANGUAGE_UNKNOWN)
        if request.extension is None:
            v.add(SpendReason.EXTENSION_UNKNOWN)
        elif mandate.stock_budget_chf is not None:
            pending_ext = ledger.unsettled_commitments(since=treasury_snapshot.as_of, extension=request.extension)
            exposure = treasury_snapshot.extension_exposure_chf.get(request.extension, ZERO) + pending_ext
            cap = mandate.extension_max_share * mandate.stock_budget_chf
            ctx["extension_exposure_before_chf"] = exposure
            ctx["extension_cap_chf"] = _q2(cap)
            if exposure + effective > cap:
                v.add(
                    SpendReason.ABOVE_EXTENSION_CAP,
                    f"Extension {request.extension} : {_fmt(exposure)} + {_fmt(effective)} > {_fmt(cap)} "
                    f"({mandate.extension_max_share * 100} % du budget stock).",
                )

    outcome = v.outcome
    order = list(SpendReason)
    reasons = tuple(r.value for r in sorted(v.reasons, key=lambda r: (-REASON_OUTCOME[r].severity, order.index(r))))
    draft = None
    if request.payment_method is PaymentMethod.BANK_TRANSFER and outcome is MandateOutcome.NEEDS_HUMAN_APPROVAL:
        draft = TransferDraft(
            beneficiary_id=request.supplier_id,
            payee_ref=supplier.payee_ref if supplier is not None and not inactive else None,
            amount=request.amount,
            currency=request.currency,
            amount_chf=amount_chf,
            reference=request.idempotency_key[:35],
            purpose=request.purpose,
        )
    return MandateDecision(
        outcome=outcome,
        reasons=reasons,
        warnings=tuple(r.value for r in v.warnings),
        messages=tuple(v.messages),
        amount_chf=amount_chf,
        payment_cost_chf=cost,
        effective_cost_chf=effective,
        mandate_version=mandate.mandate_version,
        mandate_fingerprint=mandate.fingerprint,
        request_hash=request_hash,
        idempotency_key=request.idempotency_key,
        decided_at=at,
        context=DecisionContext(**ctx),
        transfer_draft=draft,
    )


# ---------------------------------------------------------------------- registre


class SpendStatus(str, Enum):
    """Cycle de vie d'une demande dans le registre."""

    REJECTED = "REJECTED"
    PENDING_HUMAN = "PENDING_HUMAN"
    APPROVED = "APPROVED"
    """Approuvée dans le mandat, paiement non encore exécuté."""
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REFUSED = "HUMAN_REFUSED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


_COMMITTED = frozenset({SpendStatus.APPROVED, SpendStatus.HUMAN_APPROVED, SpendStatus.EXECUTED})
_UNEXECUTED = frozenset({SpendStatus.APPROVED, SpendStatus.HUMAN_APPROVED})


class SpendEntry(FrozenModel):
    """État courant d'une demande (dérivé du journal append-only)."""

    idempotency_key: str
    request: SpendRequest
    request_hash: str
    decision: MandateDecision
    status: SpendStatus
    recorded_at: datetime
    human_actor: str | None = None
    human_decided_at: datetime | None = None
    executed_at: datetime | None = None
    executed_amount_chf: Decimal | None = None
    payment_ref: str | None = None
    reconciled_at: datetime | None = None
    reconciliation: Literal["OK", "AMOUNT_MISMATCH"] | None = None
    note: str = ""

    @property
    def autonomous(self) -> bool:
        """Vrai si approuvée par les règles du mandat (sans décision humaine)."""
        return self.decision.outcome is MandateOutcome.APPROVED_WITHIN_MANDATE

    @property
    def committed_amount_chf(self) -> Decimal:
        """Montant engagé : réel si exécuté, sinon coût effectif estimé ; 0 si non engagé."""
        if self.status not in _COMMITTED:
            return ZERO
        if self.executed_amount_chf is not None:
            return self.executed_amount_chf
        return self.decision.effective_cost_chf


class LedgerEvent(FrozenModel):
    """Ligne du journal append-only du registre (jamais de coordonnée bancaire)."""

    seq: int
    at: datetime
    idempotency_key: str
    kind: Literal[
        "RECORDED",
        "REPLAYED",
        "HUMAN_APPROVED",
        "HUMAN_REFUSED",
        "EXPIRED",
        "EXECUTED",
        "CANCELLED",
        "RECONCILED",
        "RECONCILIATION_ALERT",
    ]
    actor: str
    detail: str = ""


class StatementLine(FrozenModel):
    """Débit relevé sur le compte PayPal dédié ou le compte bancaire (export de relevé)."""

    source: Literal["PAYPAL", "BANK"]
    transaction_id: str = Field(min_length=1)
    booked_on: date
    amount_chf: StrictDecimal = Field(gt=0)
    counterparty: str = ""
    reference: str = ""


class ReconciliationLine(FrozenModel):
    """Résultat de rapprochement d'une ligne."""

    status: Literal["OK", "AMOUNT_MISMATCH", "UNKNOWN_DEBIT", "MISSING_ON_STATEMENT", "PENDING"]
    idempotency_key: str | None = None
    transaction_id: str | None = None
    ledger_amount_chf: Decimal | None = None
    statement_amount_chf: Decimal | None = None
    detail: str = ""


class ReconciliationReport(FrozenModel):
    """Rapprochement registre ↔ relevés : tout débit inconnu est une alerte (fraude possible, E3)."""

    at: datetime
    lines: tuple[ReconciliationLine, ...]

    @property
    def alerts(self) -> tuple[ReconciliationLine, ...]:
        """Écarts à traiter (montant, débit inconnu, paiement absent du relevé)."""
        alert_statuses = ("AMOUNT_MISMATCH", "UNKNOWN_DEBIT", "MISSING_ON_STATEMENT")
        return tuple(ln for ln in self.lines if ln.status in alert_statuses)

    @property
    def ok(self) -> bool:
        """Vrai si aucun écart."""
        return not self.alerts


class SpendLedger:
    """Registre append-only des demandes de dépense, idempotent et rapprochable (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, SpendEntry] = {}
        self._events: list[LedgerEvent] = []

    # -- lecture ------------------------------------------------------------------
    def get(self, idempotency_key: str) -> SpendEntry | None:
        """Entrée par clé d'idempotence (None si inconnue)."""
        with self._lock:
            return self._entries.get(idempotency_key)

    def entries(self) -> tuple[SpendEntry, ...]:
        """Entrées dans l'ordre d'enregistrement."""
        with self._lock:
            return tuple(self._entries.values())

    def events(self) -> tuple[LedgerEvent, ...]:
        """Journal append-only."""
        with self._lock:
            return tuple(self._events)

    def committed(
        self,
        *,
        category: SpendCategory | None = None,
        supplier_id: str | None = None,
        month: tuple[int, int] | None = None,
        day: date | None = None,
        mandate_version: str | None = None,
        autonomous_only: bool = False,
    ) -> Decimal:
        """Somme engagée (approuvée, validée ou exécutée ; ni refusée, ni annulée, ni en attente)."""
        total = ZERO
        with self._lock:
            for e in self._entries.values():
                if e.status not in _COMMITTED or (autonomous_only and not e.autonomous):
                    continue
                if category is not None and e.request.category is not category:
                    continue
                if supplier_id is not None and e.request.supplier_id != supplier_id:
                    continue
                if mandate_version is not None and e.decision.mandate_version != mandate_version:
                    continue
                if month is not None and _month(e.decision.decided_at) != month:
                    continue
                if day is not None and _local_day(e.decision.decided_at) != day:
                    continue
                total += e.committed_amount_chf
        return total

    def unsettled_commitments(
        self,
        *,
        since: datetime,
        method: PaymentMethod | None = None,
        extension: str | None = None,
    ) -> Decimal:
        """Engagements absents d'une photo prise à ``since`` : non exécutés, ou exécutés après ``since``."""
        total = ZERO
        with self._lock:
            for e in self._entries.values():
                pending = e.status in _UNEXECUTED
                late = e.status is SpendStatus.EXECUTED and e.executed_at is not None and e.executed_at > since
                if not (pending or late):
                    continue
                if method is not None and e.request.payment_method is not method:
                    continue
                if extension is not None and (
                    e.request.category is not SpendCategory.STOCK or e.request.extension != extension
                ):
                    continue
                total += e.committed_amount_chf
        return total

    def can_execute(self, idempotency_key: str, *, now: datetime, max_age: timedelta = timedelta(hours=1)) -> bool:
        """La passerelle de paiement ne paie que des approbations récentes (photo cash encore valable)."""
        _require_aware(now, "now")
        entry = self.get(idempotency_key)
        if entry is None or entry.status not in _UNEXECUTED:
            return False
        reference = entry.human_decided_at or entry.decision.decided_at
        return timedelta(0) <= now - reference <= max_age

    # -- écriture -----------------------------------------------------------------
    def _log(self, at: datetime, key: str, kind: Any, actor: str, detail: str = "") -> None:
        self._events.append(
            LedgerEvent(seq=len(self._events) + 1, at=at, idempotency_key=key, kind=kind, actor=actor, detail=detail)
        )

    def _require(self, key: str) -> SpendEntry:
        entry = self._entries.get(key)
        if entry is None:
            raise MandateError(f"demande inconnue : {key}")
        return entry

    def record(self, request: SpendRequest, decision: MandateDecision, *, actor: str = "moteur") -> SpendEntry:
        """Enregistre une décision. Même clé + même demande => entrée existante (aucune double dépense)."""
        request_hash = request.request_hash
        if decision.request_hash != request_hash or decision.idempotency_key != request.idempotency_key:
            raise MandateError("la décision ne correspond pas à la demande")
        with self._lock:
            existing = self._entries.get(request.idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyConflictError(f"clé {request.idempotency_key} déjà utilisée (autre demande)")
                self._log(decision.decided_at, request.idempotency_key, "REPLAYED", actor, "aucune nouvelle dépense")
                return existing
            if decision.replayed:
                raise MandateError("décision rejouée sans entrée d'origine")
            status = {
                MandateOutcome.APPROVED_WITHIN_MANDATE: SpendStatus.APPROVED,
                MandateOutcome.NEEDS_HUMAN_APPROVAL: SpendStatus.PENDING_HUMAN,
                MandateOutcome.REJECTED: SpendStatus.REJECTED,
            }[decision.outcome]
            entry = SpendEntry(
                idempotency_key=request.idempotency_key,
                request=request,
                request_hash=request_hash,
                decision=decision,
                status=status,
                recorded_at=decision.decided_at,
            )
            self._entries[request.idempotency_key] = entry
            self._log(
                decision.decided_at,
                request.idempotency_key,
                "RECORDED",
                actor,
                f"{decision.outcome.value} {','.join(decision.reasons)}",
            )
            return entry

    def _update(self, entry: SpendEntry, **changes: Any) -> SpendEntry:
        updated = entry.replace(**changes)
        self._entries[entry.idempotency_key] = updated
        return updated

    def approve_by_human(
        self, idempotency_key: str, *, approver: str, at: datetime, note: str = "", ttl: timedelta = HUMAN_APPROVAL_TTL
    ) -> SpendEntry:
        """Validation humaine d'une demande en attente ; expirée après ``ttl`` (24 h, statu quo sûr)."""
        _require_aware(at, "at")
        if not approver.strip():
            raise MandateError("approbateur obligatoire")
        with self._lock:
            entry = self._require(idempotency_key)
            if entry.status is not SpendStatus.PENDING_HUMAN:
                raise MandateError(f"{idempotency_key} : statut {entry.status.value}, validation impossible")
            if at - entry.decision.decided_at > ttl:
                self._update(entry, status=SpendStatus.EXPIRED)
                self._log(at, idempotency_key, "EXPIRED", approver, "validation hors délai : resoumettre")
                raise MandateError(f"{idempotency_key} : demande expirée, la resoumettre avec des données fraîches")
            updated = self._update(
                entry, status=SpendStatus.HUMAN_APPROVED, human_actor=approver, human_decided_at=at, note=note
            )
            self._log(at, idempotency_key, "HUMAN_APPROVED", approver, note)
            return updated

    def refuse_by_human(self, idempotency_key: str, *, approver: str, at: datetime, note: str = "") -> SpendEntry:
        """Refus humain d'une demande en attente."""
        _require_aware(at, "at")
        with self._lock:
            entry = self._require(idempotency_key)
            if entry.status is not SpendStatus.PENDING_HUMAN:
                raise MandateError(f"{idempotency_key} : statut {entry.status.value}, refus impossible")
            updated = self._update(
                entry, status=SpendStatus.HUMAN_REFUSED, human_actor=approver, human_decided_at=at, note=note
            )
            self._log(at, idempotency_key, "HUMAN_REFUSED", approver, note)
            return updated

    def mark_executed(
        self, idempotency_key: str, *, at: datetime, amount_chf: Decimal, payment_ref: str, actor: str = "passerelle"
    ) -> SpendEntry:
        """Paiement exécuté (idempotent pour la même référence de paiement et le même montant)."""
        _require_aware(at, "at")
        try:
            amount = _strict_decimal(amount_chf)
        except ValueError as exc:
            raise MandateError(f"montant exécuté : {exc}") from exc
        if not isinstance(amount, Decimal) or amount <= 0:
            raise MandateError("montant exécuté > 0 attendu")
        if not payment_ref.strip():
            raise MandateError("référence de paiement obligatoire")
        with self._lock:
            entry = self._require(idempotency_key)
            if entry.status is SpendStatus.EXECUTED:
                if entry.payment_ref == payment_ref and entry.executed_amount_chf == amount:
                    return entry
                raise IdempotencyConflictError(f"{idempotency_key} déjà exécuté ({entry.payment_ref})")
            if entry.status not in _UNEXECUTED:
                raise MandateError(f"{idempotency_key} : statut {entry.status.value}, paiement interdit")
            delta = amount - entry.decision.effective_cost_chf
            updated = self._update(
                entry, status=SpendStatus.EXECUTED, executed_at=at, executed_amount_chf=amount, payment_ref=payment_ref
            )
            self._log(at, idempotency_key, "EXECUTED", actor, f"{payment_ref} {amount} CHF (écart estimation {delta})")
            return updated

    def cancel(self, idempotency_key: str, *, at: datetime, reason: str, actor: str) -> SpendEntry:
        """Annule une demande non exécutée (le montant cesse d'être engagé)."""
        _require_aware(at, "at")
        if not reason.strip():
            raise MandateError("motif d'annulation obligatoire")
        with self._lock:
            entry = self._require(idempotency_key)
            if entry.status not in (*_UNEXECUTED, SpendStatus.PENDING_HUMAN):
                raise MandateError(f"{idempotency_key} : statut {entry.status.value}, annulation impossible")
            updated = self._update(entry, status=SpendStatus.CANCELLED, note=reason)
            self._log(at, idempotency_key, "CANCELLED", actor, reason)
            return updated

    def reconcile(
        self,
        statement: Sequence[StatementLine],
        *,
        at: datetime,
        amount_tolerance_chf: Decimal = Decimal("0.05"),
        grace_days: int = 3,
    ) -> ReconciliationReport:
        """Rapproche les paiements exécutés des relevés (par référence de paiement ou clé d'idempotence).

        Débit du relevé sans demande correspondante => ``UNKNOWN_DEBIT`` (dépense non autorisée
        possible : fiche E3, gel manuel conseillé). Paiement exécuté absent du relevé après
        ``grace_days`` => ``MISSING_ON_STATEMENT``. Idempotent : une entrée rapprochée ne l'est qu'une fois.
        """
        _require_aware(at, "at")
        ids = [ln.transaction_id for ln in statement]
        if len(set(ids)) != len(ids):
            raise MandateError("relevé : transaction en double")
        lines: list[ReconciliationLine] = []
        with self._lock:
            by_ref = {e.payment_ref: e for e in self._entries.values() if e.payment_ref}
            matched_keys: set[str] = set()
            for ln in statement:
                entry = by_ref.get(ln.transaction_id) or next(
                    (e for e in self._entries.values() if e.idempotency_key in ln.reference and e.payment_ref), None
                )
                if entry is None:
                    lines.append(
                        ReconciliationLine(
                            status="UNKNOWN_DEBIT",
                            transaction_id=ln.transaction_id,
                            statement_amount_chf=ln.amount_chf,
                            detail=f"{ln.source} {ln.booked_on} {ln.counterparty} : aucune demande au registre",
                        )
                    )
                    self._log(at, "-", "RECONCILIATION_ALERT", "rapprochement", f"débit inconnu {ln.transaction_id}")
                    continue
                matched_keys.add(entry.idempotency_key)
                if entry.reconciled_at is not None:
                    continue
                assert entry.executed_amount_chf is not None
                ok = abs(entry.executed_amount_chf - ln.amount_chf) <= amount_tolerance_chf
                status: Literal["OK", "AMOUNT_MISMATCH"] = "OK" if ok else "AMOUNT_MISMATCH"
                self._update(entry, reconciled_at=at, reconciliation=status)
                lines.append(
                    ReconciliationLine(
                        status=status,
                        idempotency_key=entry.idempotency_key,
                        transaction_id=ln.transaction_id,
                        ledger_amount_chf=entry.executed_amount_chf,
                        statement_amount_chf=ln.amount_chf,
                    )
                )
                self._log(
                    at,
                    entry.idempotency_key,
                    "RECONCILED" if ok else "RECONCILIATION_ALERT",
                    "rapprochement",
                    f"{ln.transaction_id} {status}",
                )
            for e in self._entries.values():
                done = e.reconciled_at is not None or e.idempotency_key in matched_keys
                if e.status is not SpendStatus.EXECUTED or done:
                    continue
                assert e.executed_at is not None
                late = at - e.executed_at > timedelta(days=grace_days)
                lines.append(
                    ReconciliationLine(
                        status="MISSING_ON_STATEMENT" if late else "PENDING",
                        idempotency_key=e.idempotency_key,
                        transaction_id=e.payment_ref,
                        ledger_amount_chf=e.executed_amount_chf,
                        detail="paiement exécuté absent du relevé" if late else "dans le délai de comptabilisation",
                    )
                )
                if late:
                    self._log(at, e.idempotency_key, "RECONCILIATION_ALERT", "rapprochement", "absent du relevé")
        return ReconciliationReport(at=at, lines=tuple(lines))

    def to_registry_rows(self) -> list[dict[str, str]]:
        """Lignes au format ``docs/08-agents/modeles/REGISTRE_MANDAT.csv`` (colonnes :data:`REGISTRY_COLUMNS`)."""

        def s(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, bool):
                return "oui" if value else "non"
            if isinstance(value, Decimal):
                return str(_q2(value))
            if isinstance(value, Enum):
                return str(value.value)
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            return str(value)

        rows = []
        for i, e in enumerate(self.entries(), start=1):
            r, d = e.request, e.decision
            row = {
                "ligne": str(i),
                "date": d.decided_at.isoformat(),
                "demande_id": r.idempotency_key,
                "agent_demandeur": r.requested_by,
                "objet": r.purpose,
                "beneficiaire_id": r.supplier_id,
                "categorie_mandat": r.category.value,
                "montant_origine": str(r.amount),
                "devise_origine": r.currency,
                "taux_chf": s(r.fx_rate_to_chf or Decimal(1)),
                "source_taux": r.fx_source or ("CHF" if r.currency == "CHF" else ""),
                "date_taux": s(r.fx_date),
                "montant_chf": s(d.amount_chf),
                "plafond_transaction_chf": s(d.context.per_transaction_cap_chf),
                "reste_categorie_avant_chf": s(d.context.category_remaining_before_chf),
                "cash_disponible_avant_chf": s(d.context.cash_available_before_chf),
                "stoploss_cash_ok": s(d.context.stoploss_cash_ok),
                "stoploss_global_ok": s(d.context.stoploss_global_ok),
                "niveau_autonomie": str(d.context.autonomy_level),
                "decision": d.outcome.value,
                "ref_decision": d.decision_ref,
                "moyen_paiement": r.payment_method.value,
                "ref_paiement": e.payment_ref or "",
                "cle_idempotence": r.idempotency_key,
                "statut": e.status.value,
                "rapprochement_date": s(e.reconciled_at),
                "rapprochement_resultat": e.reconciliation or "",
                "fictif": "true" if r.fictif else "false",
            }
            rows.append(row)
        return rows


# --------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m pokeshop.mandate fingerprint [chemin]`` : empreinte, champs manquants, état du mandat."""
    parser = argparse.ArgumentParser(prog="python -m pokeshop.mandate", description="Outils du mandat de dépense")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fp = sub.add_parser("fingerprint", help="calcule l'empreinte à recopier dans approval.fingerprint_sha256")
    fp.add_argument("path", nargs="?", default=None)
    args = parser.parse_args(argv)
    try:
        data, target, _ = _read_yaml(args.path)
        mandate = parse_mandate(data, source=str(target))
    except MandateError as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    print(f"mandat      : {target}")
    print(f"version     : {mandate.mandate_version}")
    print(f"empreinte   : {mandate.fingerprint}")
    missing = mandate.missing_fields()
    print(f"à remplir   : {', '.join(missing) if missing else 'rien'}")
    reasons = mandate.inactive_reasons(now)
    print(f"état        : {'ACTIF' if not reasons else 'INACTIF (' + ', '.join(r.value for r in reasons) + ')'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
