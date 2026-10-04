"""Stop-loss multi-niveaux de la gouvernance (agent « gouvernance »).

Six niveaux, évalués de façon **déterministe** (Decimal, aucune IA dans la décision) à partir
d'une photo de l'activité (:class:`StopLossState`) et des seuils versionnés
``config/stoploss.v1.yaml`` (hypothèses à confirmer par la propriétaire) :

=========  ==========================================================  =============================
Niveau     Déclencheur                                                  Action(s)
=========  ==========================================================  =============================
PRODUCT    contribution < 12 % du CA net **ou** < 8 CHF par commande    ``BLOCK_SALE`` (vente/promo)
EXTENSION  exposition > 25 % du budget stock **ou** ≥ 45 j sans vente   ``NO_REORDER`` + ``PROPOSE_MARKDOWN``
ADS        CAC > contribution sur 7 j glissants **ou** plafond jour     ``CUT_CAMPAIGN``
CASH       cash disponible < réserve (1 600 CHF)                        ``FREEZE_PURCHASES_AND_ADS``
GLOBAL     perte ≥ 20 % du capital engagé                               ``FREEZE_ALL`` + autonomie niveau 1
TIME       ≥ 60 j sans atteindre les seuils de validation du BP         ``DECISION_REPORT``
=========  ==========================================================  =============================

Définitions exactes (bornes) :

* **Produit** : ``pct < min_contribution_pct`` (12 % exactement = conforme) ; ``chf < 8`` (8,00 =
  conforme). Un « petit produit » (BP §5) n'est contrôlé qu'en % : son plancher en CHF est
  vérifié sur le panier (même règle que :func:`pokeshop.pricing.floor_violations`).
* **Extension** : exposition = stock au coût historique + achats engagés non reçus ; déclenche si
  exposition **>** part × budget stock (25 % exactement = conforme). « Sans vente » : temps écoulé
  depuis la dernière vente (à défaut, depuis la première entrée en stock) **≥ 45 jours** ; une
  extension sans stock n'est pas concernée.
* **Pub** : fenêtre = les 7 derniers jours civils (fuseau ``Europe/Zurich``), aujourd'hui compris.
  Commandes = commandes payées attribuées à la campagne, **nettes d'annulations et de
  remboursements**. CAC = dépense / commandes ; déclenche si CAC **>** contribution moyenne avant
  acquisition (égalité = conforme). Sans commande nette, la campagne est coupée dès que sa
  dépense atteint ``min_spend_to_judge_chf`` (hypothèse : 20 CHF ≈ contribution d'une commande
  au scénario central BP §10). Plafond jour : dépense totale du jour **≥** plafond du mandat ;
  mandat non signé (plafond inconnu) => toute dépense du jour déclenche la coupure.
* **Cash** : cash disponible (banque + PayPal − précommandes encaissées non livrées) **<** réserve.
  1 600,00 CHF exactement = conforme (même convention que :mod:`pokeshop.treasury`).
* **Global** : capital engagé = apports cumulés − retraits de la propriétaire ; valeur nette =
  cash + stock valorisé au **min(coût historique, valeur de liquidation prudente)** + créances −
  dettes ; perte = capital − valeur nette ; déclenche si perte **≥** 20 % × capital. Le gel est
  **verrouillé** (latch) : il persiste, même si les métriques redeviennent bonnes, jusqu'à
  :meth:`StopLossEngine.rearm` avec le jeton de la propriétaire (journalisé). Aucun réarmement
  automatique. Après réarmement « rebasé », le capital engagé de référence devient la valeur
  nette au moment du réarmement (+ apports ultérieurs − retraits ultérieurs). La propriétaire
  peut aussi poser un **point zéro** (:meth:`StopLossEngine.set_baseline`) une fois les
  investissements de lancement assumés : au sens littéral, dépenser l'enveloppe de lancement du
  BP §3 (2 900 CHF non récupérables sur 8 000) suffit à déclencher le gel.
* **Temps** : à partir de ``started_at + 60 jours`` (inclus), chaque seuil de validation non
  atteint (30 commandes payées nettes, contribution après pub > 0, zéro survente, ≥ 50 % du stock
  pilote écoulé en valeur de coût) produit un ``DECISION_REPORT``. Avant l'ouverture, 60 jours
  après le premier apport sans fenêtre de validation ouverte => ``DECISION_REPORT`` « ouverture ».

Le module n'exécute rien : il renvoie des déclencheurs. Les workflows (n8n), le mandat de
dépense (:mod:`pokeshop.mandate`) et le réassort (:func:`pokeshop.stock.propose_reorder`,
paramètres ``blocked_products`` / ``blocked_extensions``) appliquent les actions.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BeforeValidator, Field, StrictInt, ValidationError, field_validator, model_validator

from .costs import HistoricalCostLedger
from .errors import PokeshopError
from .models import FrozenModel, PriceDecision, PricingParams, StockParams, canonical_hash

__all__ = [
    "STOPLOSS_ENV_VAR",
    "DEFAULT_STOPLOSS_PATH",
    "OWNER_TOKEN_SHA256_ENV_VAR",
    "StopLossError",
    "RearmRefusedError",
    "StopLossLevel",
    "StopLossAction",
    "LEVEL_LABELS_FR",
    "ACTION_LABELS_FR",
    "ProductThresholds",
    "ExtensionThresholds",
    "AdsThresholds",
    "CashThresholds",
    "GlobalThresholds",
    "TimeThresholds",
    "StopLossConfig",
    "validate_stoploss_data",
    "parse_stoploss_config",
    "load_stoploss_config",
    "default_stoploss_path",
    "consistency_errors",
    "ProductMargin",
    "ExtensionExposure",
    "AdSpend",
    "AttributedOrder",
    "CapitalMovement",
    "StockValuationLine",
    "BalanceItem",
    "NetWorthSnapshot",
    "NetWorthBreakdown",
    "ValidationWindow",
    "StopLossState",
    "Trigger",
    "StopLossStatus",
    "CapitalBaseline",
    "GlobalLatch",
    "JournalEntry",
    "capital_total",
    "prudent_stock_value",
    "net_worth",
    "effective_capital",
    "evaluate_levels",
    "StopLossEngine",
    "hash_owner_token",
    "format_chf",
    "render_report",
]

STOPLOSS_ENV_VAR = "POKESHOP_STOPLOSS_PATH"
DEFAULT_STOPLOSS_PATH = Path(__file__).resolve().parents[2] / "config" / "stoploss.v1.yaml"
OWNER_TOKEN_SHA256_ENV_VAR = "POKESHOP_OWNER_TOKEN_SHA256"
"""Empreinte sha256 (hex) du jeton de réarmement de la propriétaire, lue dans le coffre (jamais le jeton)."""

ZERO = Decimal("0")
CENT = Decimal("0.01")
BASIS_POINT = Decimal("0.0001")
_US_PER_DAY = Decimal(86_400_000_000)
_FUTURE_SKEW = timedelta(minutes=5)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MIN_TOKEN_LENGTH = 16


# --------------------------------------------------------------------------- erreurs


class StopLossError(PokeshopError, ValueError):
    """Entrée ou opération de stop-loss invalide (donnée périmée, configuration, réarmement)."""


class RearmRefusedError(StopLossError):
    """Réarmement refusé : jeton propriétaire absent ou invalide (tentative journalisée)."""


# --------------------------------------------------------------- types d'entrée stricts


def _strict_decimal(value: Any) -> Any:
    """Refuse float et bool (non déterministes) ; convertit int/str en Decimal fini."""
    if isinstance(value, (bool, float)):
        raise ValueError(f"{type(value).__name__} interdit : utiliser Decimal, int ou str")
    if isinstance(value, (int, str)):
        try:
            value = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"valeur décimale invalide {value!r}") from exc
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("valeur non finie interdite")
    return value


StrictDecimal = Annotated[Decimal, BeforeValidator(_strict_decimal)]


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire (datetime naïf refusé)")
    return value


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(BASIS_POINT, rounding=ROUND_HALF_UP)


def _days(delta: timedelta) -> Decimal:
    """Durée en jours (Decimal exact, sans float), arrondie à 0,01 jour pour l'affichage."""
    return _q2(Decimal(delta // timedelta(microseconds=1)) / _US_PER_DAY)


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StopLossError(f"{name} doit être un datetime avec fuseau horaire")


# --------------------------------------------------------------------------- enums


class StopLossLevel(str, Enum):
    """Les six niveaux du stop-loss (contexte propriétaire du 4.10.2026)."""

    PRODUCT = "PRODUCT"
    EXTENSION = "EXTENSION"
    ADS = "ADS"
    CASH = "CASH"
    GLOBAL = "GLOBAL"
    TIME = "TIME"

    @property
    def severity(self) -> int:
        """Gravité pour le tri des alertes (GLOBAL = la plus grave)."""
        return _LEVEL_SEVERITY[self]


_LEVEL_SEVERITY = {
    StopLossLevel.GLOBAL: 6,
    StopLossLevel.CASH: 5,
    StopLossLevel.ADS: 4,
    StopLossLevel.EXTENSION: 3,
    StopLossLevel.PRODUCT: 2,
    StopLossLevel.TIME: 1,
}


class StopLossAction(str, Enum):
    """Action exigée par un déclencheur (appliquée par les workflows, jamais contournée)."""

    BLOCK_SALE = "BLOCK_SALE"
    NO_REORDER = "NO_REORDER"
    PROPOSE_MARKDOWN = "PROPOSE_MARKDOWN"
    CUT_CAMPAIGN = "CUT_CAMPAIGN"
    FREEZE_PURCHASES_AND_ADS = "FREEZE_PURCHASES_AND_ADS"
    FREEZE_ALL = "FREEZE_ALL"
    DECISION_REPORT = "DECISION_REPORT"


LEVEL_LABELS_FR: dict[StopLossLevel, str] = {
    StopLossLevel.PRODUCT: "Produit",
    StopLossLevel.EXTENSION: "Extension",
    StopLossLevel.ADS: "Publicité",
    StopLossLevel.CASH: "Trésorerie",
    StopLossLevel.GLOBAL: "Global",
    StopLossLevel.TIME: "Temps",
}

ACTION_LABELS_FR: dict[StopLossAction, str] = {
    StopLossAction.BLOCK_SALE: "Vente et promotion bloquées",
    StopLossAction.NO_REORDER: "Plus de réassort",
    StopLossAction.PROPOSE_MARKDOWN: "Proposition de démarque (à valider)",
    StopLossAction.CUT_CAMPAIGN: "Campagne coupée",
    StopLossAction.FREEZE_PURCHASES_AND_ADS: "Plus d'achat ni de publicité",
    StopLossAction.FREEZE_ALL: "Tout gelé, retour au niveau d'autonomie 1, alerte",
    StopLossAction.DECISION_REPORT: "Dossier continuer / ajuster / arrêter",
}

_ACTION_ORDER = {action: i for i, action in enumerate(StopLossAction)}


# ------------------------------------------------------------------- configuration


class _ConfigSection(FrozenModel):
    """Section de configuration : clés strictes, montants Decimal (float refusé)."""


class ProductThresholds(_ConfigSection):
    """Stop-loss produit : mêmes valeurs que les planchers durs du moteur de prix (BP §5)."""

    min_contribution_pct: StrictDecimal = Field(ge=0, le=Decimal("0.60"))
    min_contribution_chf_per_order: StrictDecimal = Field(ge=0, le=100)


class ExtensionThresholds(_ConfigSection):
    """Stop-loss extension (BP §1 : 25 % du budget stock ; 45 j sans vente : contexte propriétaire)."""

    max_share_of_stock_budget: StrictDecimal = Field(gt=0, le=1)
    max_days_without_sale: StrictInt = Field(ge=1, le=365)


class AdsThresholds(_ConfigSection):
    """Stop-loss publicité (BP §9 : CAC sur commandes payées nettes ; plafond jour : mandat)."""

    window_days: StrictInt = Field(ge=1, le=31)
    min_spend_to_judge_chf: StrictDecimal = Field(ge=0, le=1000)


class CashThresholds(_ConfigSection):
    """Stop-loss trésorerie (BP §3 : réserve de 1 600 CHF)."""

    reserve_chf: StrictDecimal = Field(ge=0)


class GlobalThresholds(_ConfigSection):
    """Stop-loss global : perte cumulée en part du capital engagé."""

    max_loss_share_of_capital: StrictDecimal = Field(gt=0, le=1)
    default_liquidation_ratio: StrictDecimal = Field(ge=0, le=1)
    """Valeur de liquidation prudente par défaut, en part du coût historique (hypothèse)."""
    autonomy_level_on_freeze: StrictInt = Field(ge=1, le=4)


class TimeThresholds(_ConfigSection):
    """Stop-loss temps : seuils de validation du BP §1 sur 60 jours de vente."""

    validation_days: StrictInt = Field(ge=1, le=365)
    prelaunch_max_days: StrictInt = Field(ge=1, le=365)
    min_paid_orders: StrictInt = Field(ge=0)
    min_contribution_after_ads_chf: StrictDecimal
    """La contribution après publicité doit être **strictement** supérieure à cette valeur."""
    max_oversells: StrictInt = Field(ge=0)
    min_sell_through_share_at_cost: StrictDecimal = Field(ge=0, le=1)


_CONFIG_SECTIONS: dict[str, type[_ConfigSection]] = {
    "product": ProductThresholds,
    "extension": ExtensionThresholds,
    "ads": AdsThresholds,
    "cash": CashThresholds,
    "global": GlobalThresholds,
    "time": TimeThresholds,
}
_TOP_KEYS = {"stoploss_version", "status", "source", "effective_date", "timezone", "state_max_age_hours"} | set(
    _CONFIG_SECTIONS
)
_VERSION_RE = re.compile(r"^\S{1,64}$")


class StopLossConfig(FrozenModel):
    """Seuils versionnés du stop-loss (``config/stoploss.vN.yaml``)."""

    stoploss_version: str
    status: str
    source: str = ""
    effective_date: date | None = None
    timezone: str = "Europe/Zurich"
    state_max_age_hours: StrictInt = Field(default=24, ge=1, le=168)
    product: ProductThresholds
    extension: ExtensionThresholds
    ads: AdsThresholds
    cash: CashThresholds
    global_: GlobalThresholds = Field(alias="global")
    time: TimeThresholds
    source_path: str = "<memory>"
    content_sha256: str = ""

    model_config = FrozenModel.model_config | {"populate_by_name": True}

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {v!r}") from exc
        return v

    @property
    def tz(self) -> ZoneInfo:
        """Fuseau des jours civils (plafond jour, fenêtre 7 j)."""
        return ZoneInfo(self.timezone)


def default_stoploss_path() -> Path:
    """Chemin des seuils : variable ``POKESHOP_STOPLOSS_PATH`` sinon ``config/stoploss.v1.yaml``."""
    env = os.environ.get(STOPLOSS_ENV_VAR)
    return Path(env) if env else DEFAULT_STOPLOSS_PATH


def _errors_from(exc: ValidationError, prefix: str) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        out.append(f"{prefix}{'.' + loc if loc else ''} : {err['msg']}")
    return out


def validate_stoploss_data(data: Any) -> list[str]:
    """Liste des erreurs (en français) d'un document de seuils ; vide si valide."""
    if not isinstance(data, Mapping):
        return ["document de stop-loss : mapping YAML attendu"]
    errors: list[str] = []
    unknown = set(map(str, data)) - _TOP_KEYS
    if unknown:
        errors.append(f"clés inconnues : {', '.join(sorted(unknown))}")
    version = data.get("stoploss_version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        errors.append("stoploss_version : chaîne non vide sans espace obligatoire")
    if not isinstance(data.get("status"), str) or not data.get("status"):
        errors.append("status : mention d'hypothèse obligatoire")
    if "source" in data and not isinstance(data["source"], str):
        errors.append("source : chaîne attendue")
    if "effective_date" in data:
        eff = data["effective_date"]
        ok = isinstance(eff, date) and not isinstance(eff, datetime)
        if isinstance(eff, str):
            try:
                date.fromisoformat(eff)
                ok = True
            except ValueError:
                ok = False
        if not ok:
            errors.append(f"effective_date : date ISO AAAA-MM-JJ attendue (reçu {eff!r})")
    if "timezone" in data:
        tz = data["timezone"]
        try:
            if not isinstance(tz, str):
                raise ValueError
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"timezone : fuseau IANA attendu (reçu {tz!r})")
    if "state_max_age_hours" in data:
        age = data["state_max_age_hours"]
        if isinstance(age, bool) or not isinstance(age, int) or not 1 <= age <= 168:
            errors.append(f"state_max_age_hours : entier de 1 à 168 attendu (reçu {age!r})")
    for name, model in _CONFIG_SECTIONS.items():
        section = data.get(name)
        if not isinstance(section, Mapping):
            errors.append(f"{name} : section manquante")
            continue
        try:
            model.model_validate(dict(section))
        except ValidationError as exc:
            errors.extend(_errors_from(exc, name))
    return errors


def parse_stoploss_config(
    data: Mapping[str, Any], *, source: str = "<memory>", content_sha256: str = ""
) -> StopLossConfig:
    """Valide puis construit la configuration ; :class:`StopLossError` si invalide."""
    errors = validate_stoploss_data(data)
    if errors:
        raise StopLossError("Seuils de stop-loss invalides : " + " ; ".join(errors))
    eff = data.get("effective_date")
    payload = {k: v for k, v in data.items()}
    if isinstance(eff, str):
        payload["effective_date"] = date.fromisoformat(eff)
    payload["source_path"] = source
    payload["content_sha256"] = content_sha256
    return StopLossConfig.model_validate(payload)


def load_stoploss_config(path: str | Path | None = None) -> StopLossConfig:
    """Charge et valide ``config/stoploss.v1.yaml`` (ou ``POKESHOP_STOPLOSS_PATH``)."""
    target = Path(path) if path is not None else default_stoploss_path()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise StopLossError(f"fichier de stop-loss illisible : {target} ({exc.strerror})") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise StopLossError(f"YAML invalide : {target}") from exc
    if not isinstance(data, Mapping):
        raise StopLossError("document de stop-loss : mapping YAML attendu")
    return parse_stoploss_config(data, source=str(target), content_sha256=hashlib.sha256(raw).hexdigest())


def consistency_errors(
    config: StopLossConfig,
    *,
    pricing: PricingParams | None = None,
    stock: StockParams | None = None,
    treasury_reserve: Decimal | None = None,
    mandate_cash_reserve: Decimal | None = None,
    mandate_extension_share: Decimal | None = None,
) -> list[str]:
    """Écarts entre les seuils du stop-loss et les autres sources (règles de prix, trésorerie, mandat).

    Une même règle ne doit avoir qu'une valeur : plancher produit = plancher dur du moteur de
    prix ; part par extension = ``StockParams.extension_budget_cap`` ; réserve cash =
    ``treasury.CASH_STOPLOSS_RESERVE`` = réserve du mandat.
    """
    errors: list[str] = []
    if pricing is not None:
        if pricing.hard_floor_margin != config.product.min_contribution_pct:
            errors.append(
                f"plancher produit {config.product.min_contribution_pct} ≠ "
                f"hard_floor_margin {pricing.hard_floor_margin}"
            )
        if pricing.hard_floor_chf_per_order != config.product.min_contribution_chf_per_order:
            errors.append(
                f"plancher CHF {config.product.min_contribution_chf_per_order} ≠ "
                f"hard_floor_chf_per_order {pricing.hard_floor_chf_per_order}"
            )
    if stock is not None and stock.extension_budget_cap != config.extension.max_share_of_stock_budget:
        errors.append(
            f"part par extension {config.extension.max_share_of_stock_budget} ≠ "
            f"extension_budget_cap {stock.extension_budget_cap}"
        )
    if mandate_extension_share is not None and mandate_extension_share != config.extension.max_share_of_stock_budget:
        errors.append(
            f"part par extension {config.extension.max_share_of_stock_budget} ≠ mandat {mandate_extension_share}"
        )
    for label, value in (("trésorerie", treasury_reserve), ("mandat", mandate_cash_reserve)):
        if value is not None and value != config.cash.reserve_chf:
            errors.append(f"réserve cash {config.cash.reserve_chf} ≠ {label} {value}")
    return errors


# --------------------------------------------------------------------- état d'entrée


class ProductMargin(FrozenModel):
    """Contribution d'une référence au prix public (``PRICE``) ou promotionnel (``PROMO``) évalué."""

    product_key: str = Field(min_length=1)
    extension: str | None = None
    contribution_chf: StrictDecimal
    contribution_pct: StrictDecimal
    """Fraction du CA net (0.12 = 12 %)."""
    small_product: bool = False
    context: Literal["PRICE", "PROMO"] = "PRICE"

    @classmethod
    def from_decision(
        cls,
        product_key: str,
        decision: PriceDecision,
        *,
        extension: str | None = None,
        context: Literal["PRICE", "PROMO"] = "PRICE",
    ) -> ProductMargin:
        """Construit la marge à partir d'une décision du moteur de prix (contribution connue exigée)."""
        if decision.contribution_chf is None or decision.contribution_pct is None:
            raise StopLossError(f"{product_key} : décision {decision.status.value} sans contribution calculée")
        return cls(
            product_key=product_key,
            extension=extension,
            contribution_chf=decision.contribution_chf,
            contribution_pct=decision.contribution_pct,
            small_product=decision.small_product,
            context=context,
        )


class ExtensionExposure(FrozenModel):
    """Exposition et activité d'une extension (valeurs au coût historique, jamais au coût de remplacement)."""

    extension: str = Field(min_length=1)
    stock_value_at_cost: StrictDecimal = Field(ge=0)
    on_order_value: StrictDecimal = Field(default=ZERO, ge=0)
    """Achats engagés non reçus (au coût)."""
    first_stocked_at: datetime | None = None
    last_sale_at: datetime | None = None
    cap_override: StrictDecimal | None = Field(default=None, gt=0, le=1)
    """Exception de plafond **validée par la propriétaire** (mandat, intervention C18)."""

    @field_validator("first_stocked_at", "last_sale_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _aware(v, "date")

    @property
    def exposure(self) -> Decimal:
        """Stock au coût + engagé non reçu."""
        return self.stock_value_at_cost + self.on_order_value


class AdSpend(FrozenModel):
    """Dépense publicitaire d'une campagne pour un jour civil (fuseau de la configuration)."""

    campaign_id: str = Field(min_length=1)
    day: date
    amount: StrictDecimal = Field(ge=0)


class AttributedOrder(FrozenModel):
    """Commande attribuée à une campagne ; seules les ``PAID`` comptent (nettes d'annulations/remboursements)."""

    order_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    paid_at: datetime
    contribution_before_acquisition: StrictDecimal
    status: Literal["PAID", "CANCELLED", "REFUNDED"] = "PAID"

    @field_validator("paid_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "paid_at")


class CapitalMovement(FrozenModel):
    """Apport (``CONTRIBUTION``) ou retrait (``WITHDRAWAL``) de capital par la propriétaire."""

    movement_id: str = Field(min_length=1)
    at: datetime
    kind: Literal["CONTRIBUTION", "WITHDRAWAL"]
    amount: StrictDecimal = Field(gt=0)
    ref: str = ""

    @field_validator("at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "at")


class StockValuationLine(FrozenModel):
    """Stock d'une référence : coût historique et valeur de liquidation prudente (total de la ligne)."""

    product_key: str = Field(min_length=1)
    qty: StrictInt = Field(ge=0)
    historical_value: StrictDecimal = Field(ge=0)
    liquidation_value: StrictDecimal | None = Field(default=None, ge=0)
    """Estimation prudente, nette des frais de vente ; None => ratio par défaut de la configuration."""

    @classmethod
    def from_ledger(
        cls, ledger: HistoricalCostLedger, *, liquidation_value: Decimal | None = None
    ) -> StockValuationLine:
        """Ligne tirée du coût historique (:class:`pokeshop.costs.HistoricalCostLedger`)."""
        valuation = ledger.valuation()
        return cls(
            product_key=valuation.product_key,
            qty=valuation.qty_on_hand,
            historical_value=valuation.total_value,
            liquidation_value=liquidation_value,
        )


class BalanceItem(FrozenModel):
    """Créance ou dette libellée (ex. versements PSP en transit, TVA due, précommandes encaissées)."""

    label: str = Field(min_length=1)
    amount: StrictDecimal = Field(ge=0)


class NetWorthSnapshot(FrozenModel):
    """Photo de la valeur nette.

    * ``cash_chf`` : **tout** le cash (banque + PayPal), y compris les précommandes encaissées ;
    * ``debts`` doit donc inclure les précommandes encaissées non livrées, factures fournisseurs
      reçues non payées, TVA due, remboursements promis ;
    * ``receivables`` : versements PSP en transit, TVA à récupérer, stock payé en transit (au coût).
    """

    as_of: datetime
    cash_chf: StrictDecimal
    stock: tuple[StockValuationLine, ...] = ()
    receivables: tuple[BalanceItem, ...] = ()
    debts: tuple[BalanceItem, ...] = ()

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")

    @model_validator(mode="after")
    def _unique(self) -> NetWorthSnapshot:
        keys = [line.product_key for line in self.stock]
        if len(set(keys)) != len(keys):
            raise ValueError("product_key en double dans le stock valorisé")
        return self


class NetWorthBreakdown(FrozenModel):
    """Détail de la valeur nette (CHF, 0,01)."""

    cash: Decimal
    stock_historical: Decimal
    stock_prudent: Decimal
    receivables: Decimal
    debts: Decimal
    total: Decimal


class ValidationWindow(FrozenModel):
    """Fenêtre des seuils de validation BP §1 (ouverture des ventes, ou dernière décision « continuer »)."""

    started_at: datetime
    kind: Literal["OPENING", "AFTER_DECISION"] = "OPENING"
    paid_orders_net: StrictInt = Field(ge=0)
    """Commandes payées, nettes d'annulations et de remboursements."""
    contribution_after_ads_chf: StrictDecimal
    """Contribution après publicité, avant charges fixes (voir :mod:`pokeshop.northstar`)."""
    oversells: StrictInt = Field(ge=0)
    pilot_stock_cost_chf: StrictDecimal = Field(ge=0)
    sold_cost_chf: StrictDecimal = Field(ge=0)
    """Coût historique des unités du stock pilote vendues (nettes de retours)."""

    @field_validator("started_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "started_at")


class StopLossState(FrozenModel):
    """Photo complète de l'activité soumise au stop-loss (construite par les workflows)."""

    as_of: datetime
    products: tuple[ProductMargin, ...] = ()
    extensions: tuple[ExtensionExposure, ...] = ()
    stock_budget_chf: StrictDecimal = Field(ge=0)
    """Budget stock en vigueur (mandat signé ; BP §3 : 3 000 CHF)."""
    ad_spends: tuple[AdSpend, ...] = ()
    attributed_orders: tuple[AttributedOrder, ...] = ()
    ads_daily_cap_chf: StrictDecimal | None = Field(default=None, ge=0)
    """Plafond jour pub du mandat signé ; None (mandat non signé) => aucune dépense admise."""
    cash_available_chf: StrictDecimal
    """Banque + PayPal − précommandes encaissées non livrées (comme ``treasury``)."""
    capital_movements: tuple[CapitalMovement, ...] = ()
    net_worth: NetWorthSnapshot
    validation_window: ValidationWindow | None = None

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")

    @model_validator(mode="after")
    def _check(self) -> StopLossState:
        def dupes(values: Iterable[Any]) -> list[Any]:
            seen: set[Any] = set()
            out = []
            for v in values:
                if v in seen:
                    out.append(v)
                seen.add(v)
            return out

        checks = {
            "produit (product_key, context)": dupes((p.product_key, p.context) for p in self.products),
            "extension": dupes(e.extension for e in self.extensions),
            "dépense pub (campagne, jour)": dupes((s.campaign_id, s.day) for s in self.ad_spends),
            "commande attribuée": dupes(o.order_id for o in self.attributed_orders),
            "mouvement de capital": dupes(m.movement_id for m in self.capital_movements),
        }
        for label, found in checks.items():
            if found:
                raise ValueError(f"doublon {label} : {found[0]!r} (import en double ?)")
        for mv in self.capital_movements:
            if mv.at > self.as_of:
                raise ValueError(f"mouvement de capital {mv.movement_id} postérieur à as_of")
        return self


# ------------------------------------------------------------------- déclencheurs


class Trigger(FrozenModel):
    """Déclencheur de stop-loss : niveau, périmètre, métrique mesurée, seuil, action exigée."""

    level: StopLossLevel
    scope: str
    metric: str
    value: Decimal | None
    threshold: Decimal | None
    action: StopLossAction
    reason: str
    latched: bool = False
    """Vrai pour le gel global verrouillé (persiste jusqu'au réarmement par la propriétaire)."""
    autonomy_level: int | None = None
    """Niveau d'autonomie maximal imposé (1 pour FREEZE_ALL)."""

    def sort_key(self) -> tuple[int, str, str, int]:
        """Ordre déterministe : gravité décroissante, périmètre, métrique, action."""
        return (-self.level.severity, self.scope, self.metric, _ACTION_ORDER[self.action])


def _sorted(triggers: Iterable[Trigger]) -> list[Trigger]:
    return sorted(triggers, key=Trigger.sort_key)


class StopLossStatus(FrozenModel):
    """Résumé consommé par le mandat de dépense, le réassort et les workflows."""

    as_of: datetime
    autonomy_level: int = Field(ge=1, le=4)
    """Niveau d'autonomie effectif (déclaré, ramené à 1 si gel global)."""
    global_frozen: bool = False
    purchases_and_ads_frozen: bool = False
    blocked_products: tuple[str, ...] = ()
    no_reorder_extensions: tuple[str, ...] = ()
    markdown_extensions: tuple[str, ...] = ()
    cut_campaigns: tuple[str, ...] = ()
    ads_globally_cut: bool = False
    decision_report_due: bool = False
    triggers_hash: str = ""

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")

    @classmethod
    def from_triggers(cls, triggers: Sequence[Trigger], *, as_of: datetime, autonomy_level: int) -> StopLossStatus:
        """Agrège des déclencheurs ; le gel global ramène l'autonomie au niveau imposé (1)."""
        if isinstance(autonomy_level, bool) or not isinstance(autonomy_level, int) or not 1 <= autonomy_level <= 4:
            raise StopLossError("autonomy_level doit être un entier de 1 à 4")
        by_action: dict[StopLossAction, set[str]] = {a: set() for a in StopLossAction}
        level = autonomy_level
        for t in triggers:
            by_action[t.action].add(t.scope)
            if t.autonomy_level is not None:
                level = min(level, t.autonomy_level)
        cut = by_action[StopLossAction.CUT_CAMPAIGN]
        return cls(
            as_of=as_of,
            autonomy_level=level,
            global_frozen=bool(by_action[StopLossAction.FREEZE_ALL]),
            purchases_and_ads_frozen=bool(by_action[StopLossAction.FREEZE_PURCHASES_AND_ADS]),
            blocked_products=tuple(sorted(by_action[StopLossAction.BLOCK_SALE])),
            no_reorder_extensions=tuple(sorted(by_action[StopLossAction.NO_REORDER])),
            markdown_extensions=tuple(sorted(by_action[StopLossAction.PROPOSE_MARKDOWN])),
            cut_campaigns=tuple(sorted(cut - {"*"})),
            ads_globally_cut="*" in cut,
            decision_report_due=bool(by_action[StopLossAction.DECISION_REPORT]),
            triggers_hash=canonical_hash(list(_sorted(triggers))),
        )

    def blocks_reorder_of(self, product_key: str, extension: str) -> bool:
        """Vrai si le réassort de cette référence est interdit par un stop-loss."""
        return (
            self.global_frozen
            or self.purchases_and_ads_frozen
            or product_key in self.blocked_products
            or extension in self.no_reorder_extensions
        )


# ----------------------------------------------------------------- calculs globaux


class CapitalBaseline(FrozenModel):
    """Référence du capital engagé posée par la propriétaire : point zéro ou réarmement « rebasé »."""

    set_at: datetime
    origin: Literal["POINT_ZERO", "REARM"] = "REARM"
    net_value_chf: Decimal = Field(gt=0)
    capital_total_chf: Decimal


def capital_total(movements: Iterable[CapitalMovement]) -> Decimal:
    """Apports cumulés − retraits cumulés (CHF)."""
    total = ZERO
    for mv in movements:
        total += mv.amount if mv.kind == "CONTRIBUTION" else -mv.amount
    return total


def effective_capital(movements: Iterable[CapitalMovement], baseline: CapitalBaseline | None = None) -> Decimal:
    """Capital engagé de référence : apports nets, ou valeur nette au réarmement + apports nets ultérieurs."""
    total = capital_total(movements)
    if baseline is None:
        return total
    return baseline.net_value_chf + (total - baseline.capital_total_chf)


def prudent_stock_value(line: StockValuationLine, default_liquidation_ratio: Decimal) -> Decimal:
    """min(coût historique, valeur de liquidation prudente) ; ratio par défaut si non estimée."""
    liquidation = (
        line.liquidation_value
        if line.liquidation_value is not None
        else _q2(line.historical_value * default_liquidation_ratio)
    )
    return min(line.historical_value, liquidation)


def net_worth(snapshot: NetWorthSnapshot, config: StopLossConfig) -> NetWorthBreakdown:
    """Valeur nette = cash + stock prudent + créances − dettes."""
    ratio = config.global_.default_liquidation_ratio
    historical = sum((line.historical_value for line in snapshot.stock), ZERO)
    prudent = sum((prudent_stock_value(line, ratio) for line in snapshot.stock), ZERO)
    receivables = sum((item.amount for item in snapshot.receivables), ZERO)
    debts = sum((item.amount for item in snapshot.debts), ZERO)
    return NetWorthBreakdown(
        cash=snapshot.cash_chf,
        stock_historical=historical,
        stock_prudent=prudent,
        receivables=receivables,
        debts=debts,
        total=snapshot.cash_chf + prudent + receivables - debts,
    )


def format_chf(value: Decimal | None) -> str:
    """Format suisse romand : ``1 600,00 CHF`` (espaces de milliers, virgule décimale)."""
    if value is None:
        return "—"
    q = _q2(value)
    sign = "−" if q < 0 else ""
    integer, _, cents = f"{abs(q):.2f}".partition(".")
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return f"{sign}{' '.join(groups)},{cents} CHF"


def _pct(value: Decimal) -> str:
    return f"{_q2(value * 100)} %".replace(".", ",")


# ----------------------------------------------------------------------- évaluation


def _check_state_age(state: StopLossState, now: datetime, config: StopLossConfig) -> None:
    if state.as_of - now > _FUTURE_SKEW:
        raise StopLossError("état daté dans le futur : horloge non fiable")
    if now - state.as_of > timedelta(hours=config.state_max_age_hours):
        raise StopLossError(
            f"état du {state.as_of.isoformat()} périmé (> {config.state_max_age_hours} h) : "
            "recalculer avant toute décision"
        )
    if state.net_worth.as_of - now > _FUTURE_SKEW or now - state.net_worth.as_of > timedelta(
        hours=config.state_max_age_hours
    ):
        raise StopLossError("valeur nette périmée ou datée dans le futur : recalculer")


def _product_triggers(state: StopLossState, config: StopLossConfig) -> list[Trigger]:
    th = config.product
    out: list[Trigger] = []
    for pm in state.products:
        what = "promotion" if pm.context == "PROMO" else "vente"
        if pm.contribution_pct < th.min_contribution_pct:
            out.append(
                Trigger(
                    level=StopLossLevel.PRODUCT,
                    scope=pm.product_key,
                    metric="contribution_pct",
                    value=pm.contribution_pct,
                    threshold=th.min_contribution_pct,
                    action=StopLossAction.BLOCK_SALE,
                    reason=(
                        f"Contribution {_pct(pm.contribution_pct)} < {_pct(th.min_contribution_pct)} "
                        f"du CA net : {what} bloquée."
                    ),
                )
            )
        if not pm.small_product and pm.contribution_chf < th.min_contribution_chf_per_order:
            out.append(
                Trigger(
                    level=StopLossLevel.PRODUCT,
                    scope=pm.product_key,
                    metric="contribution_chf_par_commande",
                    value=pm.contribution_chf,
                    threshold=th.min_contribution_chf_per_order,
                    action=StopLossAction.BLOCK_SALE,
                    reason=(
                        f"Contribution {format_chf(pm.contribution_chf)} < "
                        f"{format_chf(th.min_contribution_chf_per_order)} par commande : {what} bloquée."
                    ),
                )
            )
    return out


def _extension_pair(ext: str, metric: str, value: Decimal, threshold: Decimal, reason: str) -> list[Trigger]:
    return [
        Trigger(
            level=StopLossLevel.EXTENSION,
            scope=ext,
            metric=metric,
            value=value,
            threshold=threshold,
            action=action,
            reason=reason,
        )
        for action in (StopLossAction.NO_REORDER, StopLossAction.PROPOSE_MARKDOWN)
    ]


def _extension_triggers(state: StopLossState, now: datetime, config: StopLossConfig) -> list[Trigger]:
    th = config.extension
    out: list[Trigger] = []
    max_idle = timedelta(days=th.max_days_without_sale)
    for ext in state.extensions:
        share = ext.cap_override if ext.cap_override is not None else th.max_share_of_stock_budget
        limit = share * state.stock_budget_chf
        if ext.exposure > limit:
            out.extend(
                _extension_pair(
                    ext.extension,
                    "exposition_chf",
                    ext.exposure,
                    _q2(limit),
                    f"Exposition {format_chf(ext.exposure)} > {_pct(share)} du budget stock "
                    f"({format_chf(limit)}) : plus de réassort, démarque à proposer.",
                )
            )
        if ext.stock_value_at_cost <= 0:
            continue
        reference = ext.last_sale_at or ext.first_stocked_at
        if reference is None:
            continue
        idle = now - reference
        if idle >= max_idle:
            since = "dernière vente" if ext.last_sale_at else "mise en stock, aucune vente"
            out.extend(
                _extension_pair(
                    ext.extension,
                    "jours_sans_vente",
                    _days(idle),
                    Decimal(th.max_days_without_sale),
                    f"{_days(idle)} jours depuis la {since} (seuil {th.max_days_without_sale} j) : "
                    "plus de réassort, démarque à proposer.",
                )
            )
    return out


def _ads_triggers(state: StopLossState, now: datetime, config: StopLossConfig) -> list[Trigger]:
    th = config.ads
    tz = config.tz
    today = now.astimezone(tz).date()
    window = {today - timedelta(days=i) for i in range(th.window_days)}
    spend: dict[str, Decimal] = {}
    spend_today = ZERO
    for s in state.ad_spends:
        if s.day > today:
            raise StopLossError(f"dépense pub datée du futur : {s.campaign_id} {s.day}")
        if s.day in window:
            spend[s.campaign_id] = spend.get(s.campaign_id, ZERO) + s.amount
        if s.day == today:
            spend_today += s.amount
    orders: dict[str, int] = {}
    contrib: dict[str, Decimal] = {}
    for o in state.attributed_orders:
        if o.status != "PAID" or o.paid_at.astimezone(tz).date() not in window or o.paid_at > now:
            continue
        orders[o.campaign_id] = orders.get(o.campaign_id, 0) + 1
        contrib[o.campaign_id] = contrib.get(o.campaign_id, ZERO) + o.contribution_before_acquisition
    out: list[Trigger] = []
    for campaign in sorted(spend):
        amount = spend[campaign]
        n = orders.get(campaign, 0)
        if n > 0:
            total_contrib = contrib[campaign]
            if amount > total_contrib:
                cac = amount / Decimal(n)
                avg = total_contrib / Decimal(n)
                out.append(
                    Trigger(
                        level=StopLossLevel.ADS,
                        scope=campaign,
                        metric="cac_7j_chf",
                        value=_q2(cac),
                        threshold=_q2(avg),
                        action=StopLossAction.CUT_CAMPAIGN,
                        reason=(
                            f"CAC {format_chf(cac)} > contribution moyenne {format_chf(avg)} "
                            f"sur {th.window_days} j ({n} commande(s) nette(s)) : campagne coupée."
                        ),
                    )
                )
        elif amount > 0 and amount >= th.min_spend_to_judge_chf:
            out.append(
                Trigger(
                    level=StopLossLevel.ADS,
                    scope=campaign,
                    metric="depense_7j_sans_commande_chf",
                    value=amount,
                    threshold=th.min_spend_to_judge_chf,
                    action=StopLossAction.CUT_CAMPAIGN,
                    reason=(
                        f"{format_chf(amount)} dépensés sur {th.window_days} j sans commande payée nette : "
                        "CAC infini, campagne coupée."
                    ),
                )
            )
    cap = state.ads_daily_cap_chf
    if (cap is None and spend_today > 0) or (cap is not None and spend_today > 0 and spend_today >= cap):
        out.append(
            Trigger(
                level=StopLossLevel.ADS,
                scope="*",
                metric="depense_jour_chf",
                value=spend_today,
                threshold=cap,
                action=StopLossAction.CUT_CAMPAIGN,
                reason=(
                    "Dépense pub du jour sans plafond signé au mandat : toutes les campagnes coupées."
                    if cap is None
                    else f"Plafond jour atteint ({format_chf(spend_today)} ≥ {format_chf(cap)}) : "
                    "toutes les campagnes coupées jusqu'à demain."
                ),
            )
        )
    return out


def _cash_triggers(state: StopLossState, config: StopLossConfig) -> list[Trigger]:
    reserve = config.cash.reserve_chf
    if state.cash_available_chf >= reserve:
        return []
    return [
        Trigger(
            level=StopLossLevel.CASH,
            scope="tresorerie",
            metric="cash_disponible_chf",
            value=state.cash_available_chf,
            threshold=reserve,
            action=StopLossAction.FREEZE_PURCHASES_AND_ADS,
            reason=(
                f"Cash disponible {format_chf(state.cash_available_chf)} < réserve {format_chf(reserve)} : "
                "plus d'achat ni de publicité."
            ),
        )
    ]


def _global_triggers(
    state: StopLossState, config: StopLossConfig, baseline: CapitalBaseline | None
) -> list[Trigger]:
    capital = effective_capital(state.capital_movements, baseline)
    if capital <= 0:
        return []
    worth = net_worth(state.net_worth, config)
    loss = capital - worth.total
    limit = config.global_.max_loss_share_of_capital * capital
    if loss < limit:
        return []
    basis = "valeur nette au réarmement + apports nets" if baseline else "apports cumulés − retraits"
    return [
        Trigger(
            level=StopLossLevel.GLOBAL,
            scope="entreprise",
            metric="perte_cumulee_chf",
            value=_q2(loss),
            threshold=_q2(limit),
            action=StopLossAction.FREEZE_ALL,
            reason=(
                f"Perte {format_chf(loss)} ≥ {_pct(config.global_.max_loss_share_of_capital)} du capital engagé "
                f"{format_chf(capital)} ({basis}) ; valeur nette {format_chf(worth.total)}. Tout est gelé, "
                f"autonomie ramenée au niveau {config.global_.autonomy_level_on_freeze}. "
                "Réarmement par la propriétaire uniquement."
            ),
            autonomy_level=config.global_.autonomy_level_on_freeze,
        )
    ]


def _time_triggers(state: StopLossState, now: datetime, config: StopLossConfig) -> list[Trigger]:
    th = config.time
    window = state.validation_window
    out: list[Trigger] = []

    def report(scope: str, metric: str, value: Decimal | None, threshold: Decimal | None, reason: str) -> None:
        out.append(
            Trigger(
                level=StopLossLevel.TIME,
                scope=scope,
                metric=metric,
                value=value,
                threshold=threshold,
                action=StopLossAction.DECISION_REPORT,
                reason=reason,
            )
        )

    if window is None:
        contributions = [mv.at for mv in state.capital_movements if mv.kind == "CONTRIBUTION"]
        if contributions and capital_total(state.capital_movements) > 0:
            first = min(contributions)
            if now - first >= timedelta(days=th.prelaunch_max_days):
                report(
                    "ouverture",
                    "jours_sans_ouverture",
                    _days(now - first),
                    Decimal(th.prelaunch_max_days),
                    f"{_days(now - first)} jours depuis le premier apport sans ouverture des ventes "
                    f"(seuil {th.prelaunch_max_days} j) : dossier continuer / ajuster / arrêter.",
                )
        return out
    if now - window.started_at < timedelta(days=th.validation_days):
        return out
    suffix = f" après {th.validation_days} j : dossier continuer / ajuster / arrêter."
    if window.paid_orders_net < th.min_paid_orders:
        report(
            "validation",
            "commandes_payees_nettes",
            Decimal(window.paid_orders_net),
            Decimal(th.min_paid_orders),
            f"{window.paid_orders_net} commandes payées nettes < {th.min_paid_orders}" + suffix,
        )
    if window.contribution_after_ads_chf <= th.min_contribution_after_ads_chf:
        report(
            "validation",
            "contribution_apres_pub_chf",
            window.contribution_after_ads_chf,
            th.min_contribution_after_ads_chf,
            f"Contribution après publicité {format_chf(window.contribution_after_ads_chf)} non positive" + suffix,
        )
    if window.oversells > th.max_oversells:
        report(
            "validation",
            "surventes",
            Decimal(window.oversells),
            Decimal(th.max_oversells),
            f"{window.oversells} survente(s) (tolérance {th.max_oversells})" + suffix,
        )
    if window.pilot_stock_cost_chf <= 0:
        report(
            "validation",
            "ecoulement_stock_pilote",
            None,
            th.min_sell_through_share_at_cost,
            "Stock pilote au coût inconnu ou nul : écoulement non mesurable" + suffix,
        )
    else:
        share = window.sold_cost_chf / window.pilot_stock_cost_chf
        if share < th.min_sell_through_share_at_cost:
            report(
                "validation",
                "ecoulement_stock_pilote",
                _q4(share),
                th.min_sell_through_share_at_cost,
                f"Stock pilote écoulé à {_pct(share)} de sa valeur au coût "
                f"(< {_pct(th.min_sell_through_share_at_cost)})" + suffix,
            )
    return out


def evaluate_levels(
    state: StopLossState,
    now: datetime,
    config: StopLossConfig,
    *,
    baseline: CapitalBaseline | None = None,
) -> list[Trigger]:
    """Évaluation **pure** des six niveaux (sans verrou). Préférer :meth:`StopLossEngine.evaluate`.

    Lève :class:`StopLossError` si l'état est périmé (> ``state_max_age_hours``) ou daté du futur :
    une décision de stop-loss sur donnée périmée serait trompeuse.
    """
    _require_aware(now, "now")
    _check_state_age(state, now, config)
    triggers = [
        *_product_triggers(state, config),
        *_extension_triggers(state, now, config),
        *_ads_triggers(state, now, config),
        *_cash_triggers(state, config),
        *_global_triggers(state, config, baseline),
        *_time_triggers(state, now, config),
    ]
    return _sorted(triggers)


# ------------------------------------------------------------------- verrou global


class GlobalLatch(FrozenModel):
    """État persistant du gel global (à sauvegarder en base et à restaurer au démarrage)."""

    frozen: bool = False
    since: datetime | None = None
    cause: Literal["THRESHOLD", "MANUAL"] | None = None
    trigger: Trigger | None = None
    detail: str = ""
    baseline: CapitalBaseline | None = None

    @model_validator(mode="after")
    def _check(self) -> GlobalLatch:
        if self.frozen and (self.since is None or self.cause is None):
            raise ValueError("gel actif sans date ni cause")
        return self


class JournalEntry(FrozenModel):
    """Ligne append-only du journal de gouvernance (jamais de jeton ni de secret)."""

    seq: int
    at: datetime
    event: Literal[
        "EVALUATION", "GLOBAL_TRIP", "MANUAL_FREEZE", "REARM", "REARM_REFUSED", "BASELINE_SET", "BASELINE_REFUSED"
    ]
    actor: str
    detail: str
    triggers_hash: str | None = None


def hash_owner_token(token: str) -> str:
    """Empreinte sha256 du jeton de la propriétaire (à placer dans le coffre, ``POKESHOP_OWNER_TOKEN_SHA256``)."""
    if not isinstance(token, str) or len(token) < _MIN_TOKEN_LENGTH:
        raise StopLossError(f"jeton trop court (≥ {_MIN_TOKEN_LENGTH} caractères aléatoires)")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class StopLossEngine:
    """Évaluateur avec **gel global verrouillé**, réarmement réservé à la propriétaire, journal append-only.

    ``owner_token_sha256`` : empreinte du jeton de la propriétaire (défaut : variable
    ``POKESHOP_OWNER_TOKEN_SHA256``). Sans empreinte configurée, aucun réarmement n'est possible
    (sécurité par défaut). ``latch`` et ``journal`` permettent de restaurer l'état persistant.
    """

    def __init__(
        self,
        config: StopLossConfig,
        *,
        owner_token_sha256: str | None = None,
        latch: GlobalLatch | None = None,
        journal: Sequence[JournalEntry] = (),
    ) -> None:
        expected = owner_token_sha256 if owner_token_sha256 is not None else os.environ.get(OWNER_TOKEN_SHA256_ENV_VAR)
        if expected is not None:
            expected = expected.strip().lower()
            if not _SHA256_RE.match(expected):
                raise StopLossError("empreinte du jeton propriétaire invalide (sha256 hexadécimal attendu)")
        self.config = config
        self._owner_hash = expected
        self._latch = latch or GlobalLatch()
        self._journal: list[JournalEntry] = list(journal)
        for i, entry in enumerate(self._journal, start=1):
            if entry.seq != i:
                raise StopLossError("journal restauré non séquentiel")
        self._lock = threading.RLock()

    # -- lecture ----------------------------------------------------------------
    @property
    def latch(self) -> GlobalLatch:
        """État du verrou global (à persister)."""
        return self._latch

    @property
    def frozen(self) -> bool:
        """Vrai tant que le gel global n'a pas été réarmé par la propriétaire."""
        return self._latch.frozen

    @property
    def journal(self) -> tuple[JournalEntry, ...]:
        """Journal append-only."""
        return tuple(self._journal)

    def _log(self, at: datetime, event: Any, actor: str, detail: str, triggers_hash: str | None = None) -> JournalEntry:
        entry = JournalEntry(
            seq=len(self._journal) + 1, at=at, event=event, actor=actor, detail=detail, triggers_hash=triggers_hash
        )
        self._journal.append(entry)
        return entry

    # -- évaluation -------------------------------------------------------------
    def _latched_trigger(self, worth_loss: Trigger | None) -> Trigger:
        if worth_loss is not None:
            return worth_loss.replace(latched=True)
        since = self._latch.since.isoformat() if self._latch.since else "?"
        origin = self._latch.trigger
        return Trigger(
            level=StopLossLevel.GLOBAL,
            scope=origin.scope if origin else "entreprise",
            metric="gel_verrouille",
            value=None,
            threshold=None,
            action=StopLossAction.FREEZE_ALL,
            reason=(
                f"Gel global verrouillé depuis {since} ({self._latch.cause}) : il persiste même si les "
                "métriques se rétablissent. Réarmement par la propriétaire uniquement."
            ),
            latched=True,
            autonomy_level=self.config.global_.autonomy_level_on_freeze,
        )

    def evaluate(self, state: StopLossState, now: datetime) -> list[Trigger]:
        """Évalue les six niveaux, verrouille le gel global au premier déclenchement, journalise."""
        _require_aware(now, "now")
        with self._lock:
            triggers = evaluate_levels(state, now, self.config, baseline=self._latch.baseline)
            current = next((t for t in triggers if t.level is StopLossLevel.GLOBAL), None)
            if current is not None and not self._latch.frozen:
                self._latch = GlobalLatch(
                    frozen=True,
                    since=now,
                    cause="THRESHOLD",
                    trigger=current,
                    detail=current.reason,
                    baseline=self._latch.baseline,
                )
                self._log(now, "GLOBAL_TRIP", "moteur", current.reason, canonical_hash(current))
            if self._latch.frozen:
                triggers = [t for t in triggers if t.level is not StopLossLevel.GLOBAL]
                triggers.append(self._latched_trigger(current))
            triggers = _sorted(triggers)
            digest = canonical_hash(triggers)
            self._log(now, "EVALUATION", "moteur", f"{len(triggers)} déclencheur(s)", digest)
            return triggers

    def status(self, triggers: Sequence[Trigger], *, as_of: datetime, autonomy_level: int) -> StopLossStatus:
        """Résumé pour le mandat ; le gel verrouillé est reporté même s'il manque dans ``triggers``."""
        items = list(triggers)
        if self._latch.frozen and not any(t.action is StopLossAction.FREEZE_ALL for t in items):
            items.append(self._latched_trigger(None))
        return StopLossStatus.from_triggers(items, as_of=as_of, autonomy_level=autonomy_level)

    # -- gel manuel et réarmement -------------------------------------------------
    def freeze(self, actor: str, reason: str, now: datetime) -> GlobalLatch:
        """Gel global manuel (agent QA, propriétaire) : toujours permis, réarmement propriétaire seule."""
        _require_aware(now, "now")
        if not actor.strip() or not reason.strip():
            raise StopLossError("acteur et motif obligatoires pour un gel manuel")
        with self._lock:
            if self._latch.frozen:
                self._log(now, "MANUAL_FREEZE", actor, f"déjà gelé ; motif ajouté : {reason}")
                return self._latch
            self._latch = GlobalLatch(
                frozen=True, since=now, cause="MANUAL", detail=reason, baseline=self._latch.baseline
            )
            self._log(now, "MANUAL_FREEZE", actor, reason)
            return self._latch

    def _verify(self, owner_token: str) -> bool:
        if self._owner_hash is None or not isinstance(owner_token, str) or not owner_token:
            return False
        candidate = hashlib.sha256(owner_token.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, self._owner_hash)

    def rearm(
        self,
        owner_token: str,
        reason: str,
        *,
        now: datetime,
        state: StopLossState | None = None,
        rebase: bool = True,
        actor: str = "propriétaire",
    ) -> JournalEntry:
        """Réarme le gel global (propriétaire uniquement), avec motif, journalisé.

        ``rebase=True`` (défaut) : le capital engagé de référence devient la valeur nette de
        ``state`` (obligatoire, > 0) ; la perte se mesure ensuite depuis ce point.
        ``rebase=False`` : référence inchangée ; si la perte dépasse encore le seuil, la
        prochaine évaluation regèle aussitôt. Le niveau d'autonomie n'est **pas** restauré :
        le remonter est une décision distincte (BP §13, après recette).
        """
        _require_aware(now, "now")
        if not isinstance(reason, str) or not reason.strip():
            raise StopLossError("motif de réarmement obligatoire")
        with self._lock:
            if not self._verify(owner_token):
                why = "aucune empreinte de jeton configurée" if self._owner_hash is None else "jeton invalide"
                self._log(now, "REARM_REFUSED", actor, f"{why} ; motif annoncé : {reason}")
                raise RearmRefusedError(f"réarmement refusé : {why}")
            if not self._latch.frozen:
                raise StopLossError("aucun gel global à réarmer")
            baseline = self._latch.baseline
            if rebase:
                if state is None:
                    raise StopLossError("réarmement rebasé : état (valeur nette) obligatoire")
                baseline = self._baseline_from(state, now, "REARM")
            self._latch = GlobalLatch(frozen=False, baseline=baseline)
            basis = f"rebasé sur {format_chf(baseline.net_value_chf)}" if rebase and baseline else "référence inchangée"
            detail = f"réarmé ({basis}) : {reason}"
            return self._log(now, "REARM", actor, detail)


    def _baseline_from(
        self,
        state: StopLossState,
        now: datetime,
        origin: Literal["POINT_ZERO", "REARM"],
        reference: Decimal | None = None,
    ) -> CapitalBaseline:
        _check_state_age(state, now, self.config)
        worth = net_worth(state.net_worth, self.config).total if reference is None else reference
        if worth <= 0:
            raise StopLossError("valeur nette ≤ 0 : un apport de capital est requis")
        return CapitalBaseline(
            set_at=now, origin=origin, net_value_chf=worth, capital_total_chf=capital_total(state.capital_movements)
        )

    def set_baseline(
        self,
        owner_token: str,
        reason: str,
        *,
        now: datetime,
        state: StopLossState,
        reference_chf: Decimal | None = None,
        actor: str = "propriétaire",
    ) -> JournalEntry:
        """Pose le **point zéro** du capital engagé (propriétaire uniquement, journalisé).

        Sans point zéro, dépenser plus de 20 % du capital en coûts de lancement non récupérables
        déclenche le gel global par construction. Deux usages :

        * dès J1, ``reference_chf`` = apports − investissements de lancement assumés (ex. BP §3 :
          8 000 − 2 900 de lancement − 900 de décote prudente du stock = 4 200) ;
        * à l'ouverture, sans ``reference_chf`` : la valeur nette constatée dans ``state``.

        La perte se mesure ensuite depuis cette référence (+ apports ultérieurs − retraits).
        Interdit pendant un gel : utiliser :meth:`rearm`.
        """
        _require_aware(now, "now")
        if not isinstance(reason, str) or not reason.strip():
            raise StopLossError("motif du point zéro obligatoire")
        if reference_chf is not None:
            try:
                reference_chf = _strict_decimal(reference_chf)
            except ValueError as exc:
                raise StopLossError(f"référence : {exc}") from exc
            if not isinstance(reference_chf, Decimal):
                raise StopLossError("référence : montant Decimal attendu")
        with self._lock:
            if not self._verify(owner_token):
                why = "aucune empreinte de jeton configurée" if self._owner_hash is None else "jeton invalide"
                self._log(now, "BASELINE_REFUSED", actor, f"{why} ; motif annoncé : {reason}")
                raise RearmRefusedError(f"point zéro refusé : {why}")
            if self._latch.frozen:
                raise StopLossError("gel global actif : décider d'abord du réarmement (rearm)")
            baseline = self._baseline_from(state, now, "POINT_ZERO", reference_chf)
            self._latch = self._latch.replace(baseline=baseline)
            return self._log(now, "BASELINE_SET", actor, f"point zéro {format_chf(baseline.net_value_chf)} : {reason}")


# ----------------------------------------------------------------------------- rapport


def render_report(triggers: Sequence[Trigger], *, now: datetime, title: str = "Alerte stop-loss") -> str:
    """Rapport Markdown (français) : tableau des déclencheurs, actions, décisions attendues."""
    _require_aware(now, "now")
    lines = [f"# {title} — {now.isoformat(timespec='minutes')}", ""]
    items = _sorted(triggers)
    if not items:
        lines += ["Aucun stop-loss déclenché.", "", "## Validation humaine requise", "", "- [ ] Aucune."]
        return "\n".join(lines) + "\n"
    lines += [
        "| Niveau | Périmètre | Métrique | Valeur | Seuil | Action | Motif |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in items:
        value = "—" if t.value is None else str(t.value)
        threshold = "—" if t.threshold is None else str(t.threshold)
        lock = " (verrouillé)" if t.latched else ""
        lines.append(
            f"| {LEVEL_LABELS_FR[t.level]} | {t.scope} | {t.metric} | {value} | {threshold} | "
            f"{ACTION_LABELS_FR[t.action]}{lock} | {t.reason} |"
        )
    actions = {t.action for t in items}
    lines += ["", "## Validation humaine requise", ""]
    if StopLossAction.FREEZE_ALL in actions:
        lines.append(
            "- [ ] **Gel global** : examiner la valeur nette et décider ; seul votre jeton réarme "
            "(`StopLossEngine.rearm`). L'autonomie reste au niveau 1 jusqu'à nouvelle décision."
        )
    if StopLossAction.DECISION_REPORT in actions:
        lines += [
            "- [ ] **Dossier temps** : cocher une option et la motiver.",
            "  - [ ] Continuer (nouvelle fenêtre de 60 jours, mêmes seuils)",
            "  - [ ] Ajuster (assortiment, prix, canal, budget : préciser)",
            "  - [ ] Arrêter (liquidation du stock au mieux, fermeture des comptes)",
        ]
    if StopLossAction.PROPOSE_MARKDOWN in actions:
        lines.append("- [ ] Démarques proposées : accepter ou refuser (une démarque sous plancher reste bloquée).")
    if StopLossAction.FREEZE_PURCHASES_AND_ADS in actions:
        lines.append("- [ ] Trésorerie sous la réserve : décider d'un apport ou attendre les versements.")
    if StopLossAction.CUT_CAMPAIGN in actions:
        lines.append("- [ ] Campagne coupée : nouveau plan de test ou arrêt (aucune relance par un agent).")
    if StopLossAction.BLOCK_SALE in actions:
        lines.append("- [ ] Références bloquées : nouveau prix rentable, ou exception écrite (C18).")
    if StopLossAction.NO_REORDER in actions and StopLossAction.PROPOSE_MARKDOWN not in actions:
        lines.append("- [ ] Extensions sans réassort : confirmer.")
    return "\n".join(lines) + "\n"
