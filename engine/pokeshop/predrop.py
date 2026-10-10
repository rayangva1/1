"""Pré-drop : réservation **GARANTIE** avant réception du stock (décision de la propriétaire du 6.10.2026).

Deux prix par produit éligible :

* **prix DROP** = prix normal décidé par le moteur (:func:`pokeshop.pricing.decide_price`, inchangé) ;
* **prix PRÉ-DROP** = prix drop × (1 + supplément), arrondi retail du moteur (grille des règles) puis marge
  **revérifiée** ; jamais plus de 10 % au-dessus du prix drop (plafond du code, :data:`MAX_PREMIUM_PCT`) ni
  au-dessus de la référence marché connue (si elle est inconnue : validation de la propriétaire).

Le supplément paie la **garantie** d'être servi en premier et expédié dès réception, pas le produit ; **aucun
remboursement de la différence** si des unités restent au drop (:data:`GUARANTEE_TEXT_FR`,
:data:`NO_DIFFERENCE_REFUND_FR`, repris sur chaque offre publique).

Principes appliqués (fermé par défaut, aucune valeur décisive fournie par son bénéficiaire) :

* **Paramètres signés** (``config/predrop.v1.yaml``) : même mécanisme d'empreinte que les seuils du stop-loss
  (:func:`predrop_fingerprint`, ``POKESHOP_PREDROP_FINGERPRINT`` au coffre). Sans empreinte, empreinte différente
  ou valeur hors des bornes du code : pré-drop **désactivé** (:func:`load_predrop_config`).
* **Éligibilité** (:func:`evaluate_eligibility`, toutes requises) : allocation **ferme** enregistrée (confirmation
  fournisseur posée par la propriétaire ou le workflow 03 adossé à sa validation, jamais par l'agent qui en
  bénéficie) ; quota pré-drop ≥ 1 (allocation ferme − réservations engagées − réserve,
  :func:`pokeshop.stock.preorder_quota`) ; score de demande = inscrits consentants intéressés (compte **agrégé**
  posé par le workflow marketing, aucune donnée personnelle) / allocation ≥ seuil ; fiche validée par la
  propriétaire ; coût connu du moteur ; prix drop sans blocage et au-dessus des planchers ; prix pré-drop ≤
  référence marché connue ; aucun gel du stop-loss (état connu), aucune quarantaine.
* **Quota partagé** (:func:`split_quota`) : réserve de sécurité (au moins 1 unité et au moins 10 %), part de
  l'allocation ouverte en pré-drop (défaut 50 %), le reste au drop.
* **Réservations payées persistées** (:class:`PredropRegistry`, journal ``predrop``, ajout seul) enregistrées par le
  workflow 02 : idempotentes par commande, limite par client sur l'**empreinte HMAC de l'identifiant client** fournie
  par la boutique (jamais un email), fenêtre prioritaire des inscrits aux alertes. Une commande **payée** n'est jamais
  perdue : hors quota, hors limite, hors fenêtre ou à un autre prix, elle est enregistrée « non servie » et son
  **remboursement intégral** est préparé.
* **Réduction d'allocation** (:func:`plan_service`) : réservations pré-drop servies **en premier** (ordre de
  paiement) ; le quota drop baisse d'abord ; s'il manque encore des unités, remboursement intégral des
  **dernières** réservations + brouillon d'email. Exécution selon le niveau d'autonomie : préparé puis validé par
  la propriétaire en un clic aux niveaux 1 et 2, approuvé par le moteur à partir du niveau
  :data:`AUTO_REFUND_MIN_LEVEL` ; l'exécution (remboursement PSP) est relevée par le workflow 02 ; le moteur
  n'écrit jamais vers un service tiers.
* **Annulation à la demande du client** (:meth:`PredropRegistry.cancel_reservation`, service client) : annulation libre
  avant la date du drop, report au-delà du seuil des conditions ou contenu modifié => remboursement **intégral**,
  supplément compris, préparé dans le même circuit (validation de la propriétaire aux niveaux 1 et 2) ; l'unité revient
  au quota.
* **Dette jusqu'à livraison** : l'argent encaissé en pré-drop (frais de livraison payés compris) est une dette
  (:meth:`PredropRegistry.outstanding_debt`) jusqu'à l'expédition de **sa ligne** de réservation (SKU ``-RESA-`` du
  pré-drop expédié en quantité au moins égale à la quantité réservée, envois partiels cumulés : ``POST /orders/shipped``)
  ou au remboursement exécuté — une réservation non servie ou en cours de remboursement reste une dette même si un
  autre article de la commande part ; la photo du stop-loss la **dérive** de ce registre. Étoile polaire : chiffre
  d'affaires reconnu **à l'expédition**, jamais à l'encaissement (aucune écriture de l'étoile polaire ici).
* **Suspension par précaution** (gel, quarantaine, paramètres non signés) : elle ferme toute **nouvelle** promesse
  (fiche retirée) ; un paiement antérieur au **retrait vérifié** de la fiche de réservation reste servi (le contrat est
  conclu, l'exécution attend) ; seul un paiement postérieur au retrait vérifié est « non servi » et remboursé.
* **Report de la date du drop** (:meth:`PredropRegistry.postpone`) : journalisé (ancienne et nouvelle date), SKU de
  réservation **stable** (figé à l'ouverture), délais d'annulation calculés sur la date en vigueur.
* **Aucune fausse urgence** : l'offre publique (:func:`public_offer`) ne dit que « Réservations ouvertes » ou
  « Réservations fermées » et la date du drop ; ni compte à rebours, ni « plus que N », ni coût, ni marge.

Montants en ``Decimal`` (CHF) ; calcul déterministe ; aucune écriture vers un service tiers (simulation par défaut).
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, field_validator

from .audit import StateJournal, StateStoreError
from .errors import PokeshopError, PricingError
from .models import DEFAULT_ROUNDING_TIERS, DecisionStatus, FrozenModel, PricingParams, RoundingTier, canonical_json
from .northstar import SHIPMENT_SEPARATOR, shipment_order_base
from .pricing import as_decimal, contribution, decide_price, price_floor_violations, q2, q4, round_up_retail
from .publish import predrop_reservation_sku
from .stock import preorder_quota

__all__ = [
    "PREDROP_ENV_VAR",
    "PREDROP_FINGERPRINT_ENV_VAR",
    "DEFAULT_PREDROP_PATH",
    "MAX_PREMIUM_PCT",
    "MAX_PER_CUSTOMER_LIMIT",
    "MIN_RESERVE_UNITS",
    "MIN_RESERVE_SHARE",
    "DEMAND_SIGNAL_MAX_AGE",
    "AUTO_REFUND_MIN_LEVEL",
    "GUARANTEE_TEXT_FR",
    "NO_DIFFERENCE_REFUND_FR",
    "PREDROP_DEBT_LABEL",
    "PREDROP_IN_TRANSIT_LABEL",
    "STATUS_OPEN_FR",
    "STATUS_CLOSED_FR",
    "PUBLIC_OFFER_FIELDS",
    "NOT_SERVED_REASONS_FR",
    "CANCELLATION_REASONS_FR",
    "refund_reason_fr",
    "PredropError",
    "PredropPersistenceError",
    "PredropConfig",
    "PredropConfigStatus",
    "validate_predrop_data",
    "predrop_fingerprint",
    "parse_predrop_config",
    "load_predrop_config",
    "round_down_retail",
    "PredropPrices",
    "compute_prices",
    "reserve_units",
    "QuotaSplit",
    "split_quota",
    "EligibilityCheck",
    "Eligibility",
    "evaluate_eligibility",
    "demand_score",
    "FirmAllocation",
    "AllocationReduction",
    "DemandSignal",
    "Predrop",
    "PredropReservation",
    "PreparedRefund",
    "ServicePlan",
    "plan_service",
    "ReductionResult",
    "PredropDebt",
    "PredropRegistry",
    "public_offer",
    "refund_email_draft",
    "RESERVATION_LINE_SEPARATOR",
    "SHIPMENT_SEPARATOR",
    "reservation_order_base",
    "shipment_order_base",
    "PredropPostponement",
    "MAX_FREE_CANCELLATION_DAYS",
    "reservation_phase",
    "main",
]

PREDROP_ENV_VAR = "POKESHOP_PREDROP_PATH"
PREDROP_FINGERPRINT_ENV_VAR = "POKESHOP_PREDROP_FINGERPRINT"
"""Empreinte des paramètres signés, placée par la propriétaire dans le coffre (jamais par un agent)."""
DEFAULT_PREDROP_PATH = Path(__file__).resolve().parents[2] / "config" / "predrop.v1.yaml"

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
MAX_PREMIUM_PCT = Decimal("0.10")
"""Plafond du code : supplément configuré **et** supplément effectif après arrondi ≤ 10 % du prix drop."""
MAX_PER_CUSTOMER_LIMIT = 2
"""Plafond du code de la limite par client et par pré-drop."""
MIN_RESERVE_UNITS = 1
MIN_RESERVE_SHARE = Decimal("0.10")
"""Réserve de sécurité minimale : au moins 1 unité et au moins 10 % de l'allocation ferme (la plus grande)."""
DEMAND_SIGNAL_MAX_AGE = timedelta(days=7)
"""Âge maximal du compte agrégé d'inscrits intéressés (au-delà : demande inconnue, pas d'ouverture)."""
AUTO_REFUND_MIN_LEVEL = 3
"""Niveau d'autonomie à partir duquel un remboursement préparé est approuvé par le moteur (sinon : propriétaire)."""
MAX_FREE_CANCELLATION_DAYS = 60
"""Borne du code du délai d'annulation libre (jours avant la date du drop) : au moins 1 (jamais le jour du drop)."""
FUTURE_SKEW = timedelta(minutes=5)

GUARANTEE_TEXT_FR = (
    "Le supplément pré-drop paie la garantie d'être servi en premier et expédié dès réception du stock, "
    "pas le produit."
)
NO_DIFFERENCE_REFUND_FR = (
    "Aucun remboursement de la différence avec le prix du drop, même s'il reste des unités au drop."
)
PREDROP_DEBT_LABEL = "Réservations pré-drop encaissées non livrées (registre du moteur)"
"""Libellé de la dette dérivée du registre dans la photo du stop-loss (construite ou déposée)."""
PREDROP_IN_TRANSIT_LABEL = (
    "Réservations pré-drop encaissées en attente de versement du prestataire (relevé du connecteur, plafonné)"
)
"""Créance de la photo du stop-loss : argent des réservations encaissé mais pas encore versé sur le compte (solde du
prestataire relevé **après** la banque, plafonné à la dette pré-drop) — revue pré-drop ARG-02."""
STATUS_OPEN_FR = "Réservations ouvertes"
STATUS_CLOSED_FR = "Réservations fermées"
PUBLIC_OFFER_FIELDS: tuple[str, ...] = (
    "predrop_id",
    "product_key",
    "public_sku",
    "statut",
    "reservations_ouvertes",
    "date_drop",
    "prix_predrop_chf",
    "prix_drop_chf",
    "limite_par_client",
    "acces_prioritaire",
    "garantie",
    "difference",
)
"""Liste blanche des champs d'une offre publique : ni coût, ni marge, ni quota, ni compte à rebours."""

NOT_SERVED_REASONS_FR: dict[str, str] = {
    "QUOTA_EXHAUSTED": "les réservations pré-drop étaient complètes au moment de votre paiement",
    "CUSTOMER_LIMIT": "la limite de réservations par client était déjà atteinte",
    "CLOSED": "les réservations pré-drop n'étaient pas ouvertes au moment de votre paiement",
    "PRIORITY_WINDOW": "les réservations étaient réservées aux inscrits aux alertes pendant la fenêtre prioritaire",
    "AMOUNT_MISMATCH": "le montant payé ne correspond pas au prix pré-drop",
    "BLOCKED": "les réservations pré-drop ont été suspendues par précaution",
    "DISABLED": "les réservations pré-drop ont été suspendues par précaution",
    "ALLOCATION_REDUCED": "la quantité qui nous a été attribuée a été réduite et nous ne pourrons pas vous servir",
}
"""Motif (code stable) d'une réservation non servie ou remboursée -> phrase de l'email au client (sans terme interne :
ni « fournisseur », ni coût, ni quantité ; mêmes règles que les emails de ``docs/06-contenu/EMAILS``)."""

CANCELLATION_REASONS_FR: dict[str, str] = {
    "CUSTOMER_CANCELLATION": "vous avez annulé votre réservation dans le délai prévu par nos conditions",
    "DATE_POSTPONED": "la date du drop a été reportée au-delà du délai prévu par nos conditions et vous avez choisi "
    "d'annuler",
    "PRODUCT_CHANGED": "le contenu du produit a changé de manière importante et vous avez choisi d'annuler",
}
"""Annulation d'une réservation **confirmée** à la demande écrite du client (``PRECOMMANDES.md``, partie « Pré-drop » ;
CGV ch. 7.7 à 7.12) : annulation libre dans le délai, report au-delà du seuil, contenu modifié. Toujours un
remboursement **intégral**, supplément compris (:meth:`PredropRegistry.cancel_reservation`)."""


def refund_reason_fr(reason: str) -> str:
    """Phrase française du motif d'un remboursement (email au client) ; motif inconnu : formule générale."""
    return NOT_SERVED_REASONS_FR.get(reason) or CANCELLATION_REASONS_FR.get(
        reason, "nous ne pourrons pas honorer votre réservation pré-drop"
    )

RESERVATION_LINE_SEPARATOR = "#"
"""Une commande Shopify qui porte des réservations de **plusieurs** pré-drops est enregistrée une fois par pré-drop :
``<commande>`` puis ``<commande>#2``, ``<commande>#3``… (workflow 02) ; chaque entrée est expédiée par **sa** ligne
(SKU ``-RESA-`` de son pré-drop) dans un envoi de la commande ``<commande>``."""


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:#/-]{0,119}$")


# --------------------------------------------------------------------------- erreurs


class PredropError(PokeshopError, ValueError):
    """Opération de pré-drop refusée (conflit avec le registre, état incompatible, entrée invalide)."""


class PredropPersistenceError(PredropError, StateStoreError):
    """Journal du pré-drop illisible ou écriture refusée : rien n'est appliqué (fermé par défaut)."""


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


# --------------------------------------------------------------------- configuration


class PredropApproval(FrozenModel):
    """Signature informative du fichier ; l'empreinte qui fait foi est celle du **coffre**."""

    approved_by: str | None = None
    approved_at: datetime | None = None
    fingerprint_sha256: str | None = None

    @field_validator("fingerprint_sha256")
    @classmethod
    def _fp(cls, v: str | None) -> str | None:
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError("empreinte sha256 hexadécimale (64 caractères) attendue")
        return v


class PredropConfig(FrozenModel):
    """Paramètres du pré-drop validés (bornes du code appliquées)."""

    predrop_version: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1)
    source: str = ""
    effective_date: date | None = None
    premium_pct: Decimal = Field(ge=0, le=MAX_PREMIUM_PCT)
    predrop_share_of_allocation: Decimal = Field(gt=0, le=1)
    safety_reserve_min_units: int = Field(ge=MIN_RESERVE_UNITS, le=10_000)
    safety_reserve_share: Decimal = Field(ge=MIN_RESERVE_SHARE, le=Decimal("0.5"))
    per_customer_limit: int = Field(ge=1, le=MAX_PER_CUSTOMER_LIMIT)
    priority_window_hours: int = Field(ge=0, le=168)
    demand_threshold: Decimal = Field(ge=Decimal("0.1"), le=Decimal("10"))
    free_cancellation_days_before_drop: int = Field(ge=1, le=MAX_FREE_CANCELLATION_DAYS)
    """Annulation libre d'une réservation confirmée **jusqu'à N jours avant la date du drop** (incluse), appliquée par
    :meth:`PredropRegistry.cancel_reservation` et reprise mot pour mot par les conditions publiques."""
    approval: PredropApproval = PredropApproval()
    fingerprint: str = ""
    """Empreinte canonique des paramètres (:func:`predrop_fingerprint`), comparée à celle du coffre."""
    source_path: str = ""


class PredropConfigStatus(FrozenModel):
    """État du pré-drop au chargement : activé seulement si les paramètres sont valides **et signés**."""

    enabled: bool
    signature: Literal["SIGNED", "UNSIGNED", "TAMPERED", "INVALID"]
    reason: str
    config: PredropConfig | None = None
    fingerprint: str = ""
    """Empreinte du fichier (vide s'il est illisible) : à recopier au coffre par la propriétaire pour signer."""


_TOP_KEYS = {
    "predrop_version", "status", "source", "effective_date", "premium_pct", "predrop_share_of_allocation",
    "safety_reserve_min_units", "safety_reserve_share", "per_customer_limit", "priority_window_hours",
    "demand_threshold", "free_cancellation_days_before_drop", "approval",
}  # fmt: skip
_DECIMAL_KEYS = ("premium_pct", "predrop_share_of_allocation", "safety_reserve_share", "demand_threshold")
_INT_KEYS = ("safety_reserve_min_units", "per_customer_limit", "priority_window_hours", "free_cancellation_days_before_drop")
_REQUIRED = ("predrop_version", "status", *_DECIMAL_KEYS, *_INT_KEYS)


def _strict_dec(value: Any, name: str, errors: list[str]) -> Decimal | None:
    if isinstance(value, bool) or isinstance(value, float) or value is None:
        errors.append(f"{name} : décimal entre guillemets attendu (reçu {value!r})")
        return None
    try:
        out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        errors.append(f"{name} : valeur décimale invalide {value!r}")
        return None
    if not out.is_finite():
        errors.append(f"{name} : valeur non finie")
        return None
    return out


def validate_predrop_data(data: Any) -> list[str]:
    """Erreurs (en français) d'un document de paramètres ; vide si valide. Bornes du code comprises."""
    if not isinstance(data, Mapping):
        return ["document du pré-drop : mapping YAML attendu"]
    errors: list[str] = []
    unknown = set(map(str, data)) - _TOP_KEYS
    if unknown:
        errors.append(f"clés inconnues : {', '.join(sorted(unknown))}")
    for key in _REQUIRED:
        if key not in data:
            errors.append(f"{key} manquant")
    for key in _DECIMAL_KEYS:
        if key in data:
            _strict_dec(data[key], key, errors)
    for key in _INT_KEYS:
        if key in data and (isinstance(data[key], bool) or not isinstance(data[key], int)):
            errors.append(f"{key} : entier attendu (reçu {data[key]!r})")
    if errors:
        return errors
    try:
        _build_config(data, source="<validation>")
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "pré-drop"
            errors.append(f"{loc} : {err['msg']}")
    except (ValueError, TypeError) as exc:  # date illisible, contenu non canonisable (flottant YAML…)
        errors.append(str(exc))
    return errors


def predrop_fingerprint(data: Mapping[str, Any]) -> str:
    """sha256 du contenu canonique des paramètres, hors ``approval.fingerprint_sha256`` (comme le stop-loss).

    Toute modification d'une valeur, d'une date ou du signataire change l'empreinte : sans nouvelle empreinte
    reportée au coffre par la propriétaire, le fichier n'est plus « signé » et le pré-drop est désactivé.
    """
    content = {k: v for k, v in data.items() if k != "approval"}
    approval = data.get("approval") if isinstance(data.get("approval"), Mapping) else {}
    content["approval"] = {k: approval.get(k) for k in ("approved_by", "approved_at")}  # type: ignore[union-attr]
    try:
        return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise PredropError(f"paramètres du pré-drop non canonisables : {exc}") from exc


def _build_config(data: Mapping[str, Any], *, source: str) -> PredropConfig:
    payload: dict[str, Any] = {k: data[k] for k in data if k != "approval"}
    for key in _DECIMAL_KEYS:
        payload[key] = Decimal(str(payload[key]).strip())
    eff = payload.get("effective_date")
    if isinstance(eff, str):
        payload["effective_date"] = date.fromisoformat(eff)
    approval = data.get("approval")
    if isinstance(approval, Mapping):
        payload["approval"] = PredropApproval.model_validate(dict(approval))
    payload["fingerprint"] = predrop_fingerprint(data)
    payload["source_path"] = source
    return PredropConfig.model_validate(payload)


def parse_predrop_config(data: Mapping[str, Any], *, source: str = "<memory>") -> PredropConfig:
    """Valide puis construit les paramètres ; :class:`PredropError` si invalides (bornes du code comprises)."""
    errors = validate_predrop_data(data)
    if errors:
        raise PredropError("paramètres du pré-drop invalides : " + " ; ".join(errors))
    return _build_config(data, source=source)


def default_predrop_path() -> Path:
    """Chemin des paramètres : ``POKESHOP_PREDROP_PATH`` sinon ``config/predrop.v1.yaml``."""
    env = os.environ.get(PREDROP_ENV_VAR)
    return Path(env) if env else DEFAULT_PREDROP_PATH


def load_predrop_config(
    path: str | Path | None = None, *, expected_fingerprint: str | None = None
) -> PredropConfigStatus:
    """Charge les paramètres et **vérifie la signature** ; ne lève jamais : renvoie un état désactivé si besoin.

    Empreinte attendue : argument, sinon variable ``POKESHOP_PREDROP_FINGERPRINT`` (coffre). Fermé par défaut :

    * fichier illisible ou invalide (valeur hors bornes) => ``INVALID``, désactivé ;
    * aucune empreinte au coffre => ``UNSIGNED``, désactivé ;
    * empreinte du coffre ≠ fichier (ou ≠ ``approval.fingerprint_sha256`` s'il est rempli) => ``TAMPERED``, désactivé ;
    * sinon ``SIGNED``, activé.
    """
    target = Path(path) if path is not None else default_predrop_path()
    try:
        raw = target.read_bytes()
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        return PredropConfigStatus(enabled=False, signature="INVALID", reason=f"paramètres illisibles : {target} ({exc})")
    if not isinstance(data, Mapping):
        return PredropConfigStatus(enabled=False, signature="INVALID", reason="paramètres : mapping YAML attendu")
    try:
        fingerprint = predrop_fingerprint(data)
        config = parse_predrop_config(data, source=str(target))
    except PredropError as exc:
        return PredropConfigStatus(enabled=False, signature="INVALID", reason=str(exc))
    expected = expected_fingerprint if expected_fingerprint is not None else os.environ.get(PREDROP_FINGERPRINT_ENV_VAR)
    expected = (expected or "").strip().lower() or None
    if expected is None:
        return PredropConfigStatus(
            enabled=False, signature="UNSIGNED", config=config, fingerprint=fingerprint,
            reason="paramètres du pré-drop non signés (POKESHOP_PREDROP_FINGERPRINT absent du coffre) : pré-drop désactivé",
        )  # fmt: skip
    declared = config.approval.fingerprint_sha256
    if not _SHA256_RE.match(expected) or expected != fingerprint or (declared is not None and declared != expected):
        return PredropConfigStatus(
            enabled=False, signature="TAMPERED", config=config, fingerprint=fingerprint,
            reason=f"paramètres du pré-drop modifiés sans signature (empreinte {fingerprint[:12]}… ≠ coffre) : "
            "pré-drop désactivé jusqu'à une nouvelle signature de la propriétaire",
        )  # fmt: skip
    return PredropConfigStatus(enabled=True, signature="SIGNED", config=config, fingerprint=fingerprint,
                               reason="paramètres signés par la propriétaire")  # fmt: skip


# --------------------------------------------------------------------------- prix


def round_down_retail(p: Decimal, *, tiers: Sequence[RoundingTier] | None = None) -> Decimal | None:
    """Plus grand point de la grille retail **≤** ``p`` (None s'il n'y en a pas) ; symétrique de ``round_up_retail``."""
    grid = tuple(tiers) if tiers else DEFAULT_ROUNDING_TIERS
    price = as_decimal(p, "p")
    if price <= 0 or not grid or grid[0].min_price != 0:
        return None
    idx = max(i for i, t in enumerate(grid) if t.min_price <= price)
    high = price
    while idx >= 0:
        tier = grid[idx]
        upper = grid[idx + 1].min_price if idx + 1 < len(grid) else None
        if upper is not None and high >= upper:
            high = upper - CENT
        n0 = (high / tier.step).to_integral_value(rounding=ROUND_FLOOR)
        candidates = [n * tier.step + e for n in (n0 - 1, n0) for e in tier.endings]
        valid = [c for c in candidates if tier.min_price <= c <= high and c > 0]
        if valid:
            return max(valid).quantize(CENT)
        high = tier.min_price - CENT
        idx -= 1
        if high <= 0:
            return None
    return None


class PredropPrices(FrozenModel):
    """Les deux prix d'un produit éligible (internes : le coût ne sort jamais dans une offre publique)."""

    landed_cost: Decimal
    drop_price: Decimal | None
    predrop_price: Decimal | None
    premium_pct_config: Decimal
    effective_premium_pct: Decimal | None
    capped_by: tuple[str, ...] = ()
    """``PLAFOND_10_POURCENT`` (supplément effectif ramené ≤ 10 %), ``REFERENCE_MARCHE`` (≤ référence marché)."""
    market_ref_chf: Decimal | None = None
    drop_decision_status: str
    drop_decision_reasons: tuple[str, ...] = ()
    small_product: bool = False
    rules_version: str
    problems: tuple[str, ...] = ()
    """Conditions de prix non remplies (bloquantes) : ``DROP_PRICE_BLOCKED``, ``DROP_BELOW_FLOOR``,
    ``ABOVE_MARKET``, ``PREDROP_BELOW_FLOOR``, ``PREDROP_BELOW_TARGET``."""
    needs_owner: tuple[str, ...] = ()
    """Validation de la propriétaire requise : ``MARKET_REF_UNKNOWN``, ``DROP_PRICE_REVIEW``."""

    @property
    def ok(self) -> bool:
        """Vrai si les deux prix existent et qu'aucune condition bloquante n'est violée."""
        return not self.problems and self.drop_price is not None and self.predrop_price is not None


def compute_prices(
    cost: Decimal, params: PricingParams, config: PredropConfig, *, market_ref: Decimal | None = None
) -> PredropPrices:
    """Prix drop (moteur, inchangé) et prix pré-drop (supplément, arrondi retail, plafonds, marge revérifiée).

    1. ``decide_price`` sur le coût rendu (BLOCKED ou DRAFT : pas de pré-drop ; REVIEW : validation propriétaire) ;
       planchers durs revérifiés sur le prix drop.
    2. Cible = drop × (1 + ``premium_pct``) arrondie **vers le haut** sur la grille ; si l'arrondi dépasse drop × 1,10,
       plus grand point de grille ≤ drop × 1,10 (jamais sous le prix drop).
    3. Référence marché connue : prix drop au-dessus => pas de pré-drop ; prix pré-drop au-dessus => plus grand point
       de grille ≤ référence (jamais sous le prix drop). Inconnue : validation de la propriétaire.
    4. Marge revérifiée au prix pré-drop (planchers durs et marge cible).
    """
    c = as_decimal(cost, "cost")
    premium = config.premium_pct
    if not ZERO <= premium <= MAX_PREMIUM_PCT:  # défense en profondeur : la configuration est déjà bornée
        raise PredropError(f"supplément {premium} hors de [0, {MAX_PREMIUM_PCT}]")
    market = as_decimal(market_ref, "market_ref") if market_ref is not None else None
    if market is not None and market <= 0:
        raise PredropError("référence marché ≤ 0")
    decision = decide_price(c, params, market)
    problems: list[str] = []
    needs_owner: list[str] = []
    capped: list[str] = []
    base: dict[str, Any] = {
        "landed_cost": q2(c),
        "premium_pct_config": premium,
        "market_ref_chf": market,
        "drop_decision_status": decision.status.value,
        "drop_decision_reasons": tuple(decision.reasons),
        "small_product": decision.small_product,
        "rules_version": params.rules_version,
    }
    drop = decision.recommended_price
    if decision.status in (DecisionStatus.BLOCKED, DecisionStatus.DRAFT) or drop is None:
        return PredropPrices(**base, drop_price=drop, predrop_price=None, effective_premium_pct=None,
                             problems=("DROP_PRICE_BLOCKED",))  # fmt: skip
    if decision.status is DecisionStatus.REVIEW:
        needs_owner.append("DROP_PRICE_REVIEW")
    if price_floor_violations(drop, c, params, small_product=decision.small_product):
        problems.append("DROP_BELOW_FLOOR")
    tiers = params.rounding_tiers
    cap = drop * (ONE + MAX_PREMIUM_PCT)
    target = drop * (ONE + premium)
    try:
        candidate = round_up_retail(target, tiers=tiers) if target > drop else drop
    except PricingError:
        candidate = drop
    if candidate > cap:
        candidate = max(drop, round_down_retail(cap, tiers=tiers) or drop)
        capped.append("PLAFOND_10_POURCENT")
    if market is None:
        needs_owner.append("MARKET_REF_UNKNOWN")
    elif drop > market:
        problems.append("ABOVE_MARKET")
    elif candidate > market:
        candidate = max(drop, round_down_retail(market, tiers=tiers) or drop)
        capped.append("REFERENCE_MARCHE")
    if price_floor_violations(candidate, c, params, small_product=decision.small_product):
        problems.append("PREDROP_BELOW_FLOOR")
    _, pct = contribution(candidate, c, params, per_order_costs=not decision.small_product)
    if pct < params.target_margin:
        problems.append("PREDROP_BELOW_TARGET")
    effective = q4(candidate / drop - ONE)
    if effective > MAX_PREMIUM_PCT:  # pragma: no cover - garanti par le plafond ci-dessus
        problems.append("PREMIUM_ABOVE_CAP")
    return PredropPrices(
        **base,
        drop_price=drop,
        predrop_price=candidate.quantize(CENT),
        effective_premium_pct=effective,
        capped_by=tuple(capped),
        problems=tuple(problems),
        needs_owner=tuple(needs_owner),
    )


# --------------------------------------------------------------------------- quotas


def reserve_units(allocation: int, *, min_units: int, share: Decimal) -> int:
    """Réserve de sécurité : max(``min_units``, 1, ⌈max(``share``, 10 %) × allocation⌉)."""
    alloc = max(0, int(allocation))
    pct = max(share, MIN_RESERVE_SHARE)
    return max(int(min_units), MIN_RESERVE_UNITS, int((Decimal(alloc) * pct).to_integral_value(rounding=ROUND_CEILING)))


class QuotaSplit(FrozenModel):
    """Partage de l'allocation ferme entre réserve, pré-drop et drop (unités ; interne, jamais publié)."""

    firm_allocation: int = Field(ge=0)
    safety_reserve: int = Field(ge=0)
    sellable: int = Field(ge=0)
    """Allocation ferme − réserve (jamais < 0)."""
    predrop_cap: int = Field(ge=0)
    """⌊part × vendable⌋ : unités ouvertes en pré-drop."""
    predrop_committed: int = Field(ge=0)
    """Unités des réservations confirmées encore à servir (ni remboursées ni retirées par une réduction)."""
    predrop_remaining: int = Field(ge=0)
    """min(``preorder_quota``(allocation, engagées, réserve), plafond − engagées), jamais < 0."""
    drop_quota: int = Field(ge=0)
    """Unités du drop : vendable − max(engagées, plafond pré-drop si ouvert), jamais < 0."""
    shortfall: int = Field(ge=0)
    """Unités engagées au-delà du vendable (réduction d'allocation non encore traitée)."""


def split_quota(
    firm_allocation: int,
    committed: int,
    *,
    share: Decimal,
    reserve_min_units: int,
    reserve_share: Decimal,
    predrop_open: bool = True,
) -> QuotaSplit:
    """Partage de l'allocation : réserve, quota pré-drop (:func:`pokeshop.stock.preorder_quota`), quota drop."""
    alloc = max(0, int(firm_allocation))
    used = max(0, int(committed))
    reserve = reserve_units(alloc, min_units=reserve_min_units, share=reserve_share)
    sellable = preorder_quota(alloc, 0, reserve)
    cap = int((share * Decimal(sellable)).to_integral_value(rounding=ROUND_FLOOR))
    remaining = max(0, min(preorder_quota(alloc, used, reserve), cap - used)) if predrop_open else 0
    held = max(used, cap) if predrop_open else used
    return QuotaSplit(
        firm_allocation=alloc,
        safety_reserve=reserve,
        sellable=sellable,
        predrop_cap=cap,
        predrop_committed=used,
        predrop_remaining=remaining,
        drop_quota=max(0, sellable - held),
        shortfall=max(0, used - sellable),
    )


# ---------------------------------------------------------------------- registres


def _id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"{name} invalide (1 à 120 caractères : lettres, chiffres, _ . : # / -)")
    return value


class FirmAllocation(FrozenModel):
    """Allocation **ferme** d'un fournisseur pour une référence (confirmation fournisseur enregistrée).

    Posée par la propriétaire ou par le workflow 03 adossé à sa validation (``n8n-03-factures``), jamais par
    l'agent qui bénéficie du pré-drop. ``qty`` est la quantité **en vigueur** (après réductions).
    """

    product_key: str = Field(min_length=1, max_length=120)
    supplier_id: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=0, le=100_000)
    supplier_confirmation_ref: str = Field(min_length=3, max_length=200)
    expected_delivery: date | None = None
    source: str = Field(min_length=3, max_length=300)
    recorded_by: str = Field(min_length=2, max_length=120)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "recorded_at")

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence (hors acteur et date d'enregistrement)."""
        return self.model_dump(mode="json", exclude={"recorded_by", "recorded_at"})


class AllocationReduction(FrozenModel):
    """Réduction d'allocation annoncée par le fournisseur (acte protecteur : ne peut que baisser)."""

    product_key: str = Field(min_length=1, max_length=120)
    previous_qty: int = Field(ge=0)
    new_qty: int = Field(ge=0)
    supplier_confirmation_ref: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=10, max_length=500)
    recorded_by: str = Field(min_length=2, max_length=120)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "recorded_at")


class DemandSignal(FrozenModel):
    """Compte **agrégé** d'inscrits consentants intéressés par une référence (aucune donnée personnelle).

    Posé par le workflow marketing (``n8n-06-marketing``) depuis la liste d'alertes (consentement explicite) :
    un nombre, une date, une source ; tout autre champ (email, nom…) est refusé.
    """

    product_key: str = Field(min_length=1, max_length=120)
    interested_consenting_subscribers: int = Field(ge=0, le=10_000_000)
    as_of: datetime
    source: str = Field(min_length=3, max_length=200)
    recorded_by: str = Field(min_length=2, max_length=120)
    recorded_at: datetime

    @field_validator("as_of", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")

    @field_validator("source")
    @classmethod
    def _no_personal_data(cls, v: str) -> str:
        if "@" in v:
            raise ValueError("source : aucune donnée personnelle (adresse email refusée), compte agrégé seulement")
        return v


PredropStatus = Literal["PENDING_OWNER", "OPEN", "CLOSED"]


class PredropPostponement(FrozenModel):
    """Report de la date du drop (journalisé : ancienne et nouvelle date, motif, acteur, référence du justificatif)."""

    previous_date: date
    new_date: date
    reason: str = Field(min_length=10, max_length=500)
    supplier_ref: str = Field(min_length=3, max_length=200)
    by: str = Field(min_length=2, max_length=120)
    at: datetime

    @field_validator("at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "at")


class Predrop(FrozenModel):
    """Pré-drop d'une référence : prix et paramètres **figés** à l'ouverture (instantané de la configuration signée)."""

    predrop_id: str = Field(min_length=1, max_length=120)
    product_key: str = Field(min_length=1, max_length=120)
    public_sku: str | None = None
    allocation_ref: str = Field(min_length=3, max_length=200)
    drop_date: date
    opens_at: datetime
    closes_at: datetime
    status: PredropStatus
    prices: PredropPrices
    config_version: str
    config_fingerprint: str
    premium_pct: Decimal
    predrop_share: Decimal
    reserve_min_units: int
    reserve_share: Decimal
    per_customer_limit: int = Field(ge=1, le=MAX_PER_CUSTOMER_LIMIT)
    priority_window_hours: int = Field(ge=0, le=168)
    demand_threshold: Decimal
    demand_interested: int = Field(ge=0)
    demand_allocation: int = Field(ge=0)
    demand_score: Decimal
    market_ref_chf: Decimal | None = None
    market_ref_attested_by: str | None = None
    requested_by: str
    requested_at: datetime
    validated_by: str | None = None
    """``propriétaire`` quand la propriétaire a ouvert ou validé (référence marché inconnue, prix REVIEW)."""
    validated_at: datetime | None = None
    needs_owner: tuple[str, ...] = ()
    closed_by: str | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    reservation_sku: str | None = None
    """SKU de la fiche de réservation **figé à l'ouverture** (``<SKU>-RESA-<date d'origine>``) : stable même après un
    report de la date (les lignes déjà vendues gardent ce SKU). None (enregistrement ancien) : calculé."""
    free_cancellation_days: int = Field(default=1, ge=1, le=MAX_FREE_CANCELLATION_DAYS)
    """Annulation libre jusqu'à N jours avant la date du drop **en vigueur** (paramètre signé figé à l'ouverture)."""
    expected_delivery: date | None = None
    """Livraison attendue de l'allocation ferme à l'ouverture (contrôle de la date du drop)."""
    postponements: tuple[PredropPostponement, ...] = ()
    """Reports de la date du drop (historique)."""

    @field_validator("opens_at", "closes_at", "requested_at", "validated_at", "closed_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _aware(v, "horodatage")

    @property
    def sku(self) -> str | None:
        """SKU de la fiche de réservation (figé à l'ouverture ; calculé pour un enregistrement ancien)."""
        if self.reservation_sku:
            return self.reservation_sku
        return predrop_reservation_sku(self.public_sku, self.drop_date) if self.public_sku else None

    @property
    def free_cancellation_until(self) -> date:
        """Dernier jour de l'annulation libre (date du drop en vigueur − N jours)."""
        return self.drop_date - timedelta(days=self.free_cancellation_days)

    def accepting_at(self, at: datetime) -> bool:
        """Vrai si le pré-drop acceptait des réservations à ``at`` (ouvert, fenêtre d'ouverture, pas encore fermé)."""
        if self.status == "PENDING_OWNER":
            return False
        if self.status == "CLOSED" and (self.closed_at is None or at >= self.closed_at):
            return False
        return self.opens_at <= at < self.closes_at

    def in_priority_window(self, at: datetime) -> bool:
        """Vrai pendant la fenêtre prioritaire des inscrits aux alertes (après l'ouverture)."""
        return at < self.opens_at + timedelta(hours=self.priority_window_hours)


ReservationStatus = Literal["CONFIRMED", "NOT_SERVED"]


class PredropReservation(FrozenModel):
    """Réservation **payée** enregistrée par le workflow 02 (commande Shopify) ; jamais une donnée personnelle en clair.

    ``customer_ref`` = sha256 hexadécimal de l'identifiant client calculé par la boutique (sert seulement à la limite
    par client ; jamais renvoyé par une lecture). ``status`` : ``CONFIRMED`` (servie en premier, ordre de paiement)
    ou ``NOT_SERVED`` (remboursement intégral préparé, motif ``not_served_reason``).
    """

    order_id: str = Field(min_length=1, max_length=120)
    predrop_id: str = Field(min_length=1, max_length=120)
    product_key: str = Field(min_length=1, max_length=120)
    customer_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    qty: int = Field(ge=1, le=100_000)
    """Quantité payée (jamais bornée ici : une commande payée est toujours enregistrée ; au-delà de la limite par
    client ou du quota, elle est non servie et remboursée intégralement)."""
    amount_paid_ttc: Decimal = Field(ge=0)
    """Montant payé pour les lignes de réservation (remises déduites ; 0 : bon d'achat, non servi)."""
    shipping_paid_ttc: Decimal = Field(default=Decimal("0"), ge=0)
    """Part des frais de livraison payés par le client rattachée à cette réservation (commande composée seulement de
    réservations ; workflow 02) : remboursée avec elle si elle n'est pas servie, dette jusqu'à l'expédition."""
    expected_ttc: Decimal = Field(gt=0)
    paid_at: datetime
    priority_access: bool = False
    seq: int = Field(ge=1)
    status: ReservationStatus
    not_served_reason: str | None = None
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("paid_at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "horodatage")

    def content(self) -> dict[str, Any]:
        """Champs postés comparés pour l'idempotence (une commande = une réservation)."""
        return {
            "order_id": self.order_id, "predrop_id": self.predrop_id, "customer_ref": self.customer_ref,
            "qty": self.qty, "amount_paid_ttc": str(q2(self.amount_paid_ttc)), "paid_at": self.paid_at.isoformat(),
            "priority_access": self.priority_access, "shipping_paid_ttc": str(q2(self.shipping_paid_ttc)),
        }  # fmt: skip

    @property
    def refund_amount(self) -> Decimal:
        """Remboursement **intégral** : montant payé (supplément compris) + part des frais de livraison payée."""
        return q2(self.amount_paid_ttc + self.shipping_paid_ttc)

    @property
    def debt_amount(self) -> Decimal:
        """Dette retenue. Confirmée : max(montant encaissé, prix pré-drop × quantité) + frais de livraison payés —
        jamais minorée (fermé par défaut) ; non servie : exactement ce qui est dû au client (remboursement intégral)."""
        if self.status == "NOT_SERVED":
            return self.refund_amount
        return q2(max(self.amount_paid_ttc, self.expected_ttc) + self.shipping_paid_ttc)

    def public_view(self) -> dict[str, Any]:
        """Lecture interne sans l'empreinte de l'identifiant client."""
        return self.model_dump(mode="json", exclude={"customer_ref"})


RefundStatus = Literal["PENDING_OWNER", "APPROVED", "EXECUTED"]


class PreparedRefund(FrozenModel):
    """Remboursement **intégral** préparé par le moteur (jamais exécuté par lui : aucune écriture vers un tiers).

    ``PENDING_OWNER`` (niveaux d'autonomie 1-2 : validation de la propriétaire en un clic) → ``APPROVED`` (par elle,
    ou par le moteur à partir du niveau :data:`AUTO_REFUND_MIN_LEVEL`) → ``EXECUTED`` (remboursement PSP relevé par
    le workflow 02). Tant qu'il n'est pas exécuté, le montant reste une dette de la photo du stop-loss.
    """

    refund_id: str = Field(min_length=1, max_length=130)
    order_id: str = Field(min_length=1, max_length=120)
    predrop_id: str = Field(min_length=1, max_length=120)
    product_key: str = Field(min_length=1, max_length=120)
    amount_ttc: Decimal = Field(ge=0)
    """Montant **intégral** : lignes de réservation (supplément compris) + part des frais de livraison payée."""
    shipping_ttc: Decimal = Field(default=Decimal("0"), ge=0)
    """Part de ``amount_ttc`` qui rembourse les frais de livraison (remboursement « livraison » chez le prestataire)."""
    reason: str
    prepared_at: datetime
    prepared_by: str
    autonomy_level: int = Field(ge=1, le=4)
    status: RefundStatus
    approved_by: str | None = None
    approved_at: datetime | None = None
    executed_by: str | None = None
    executed_at: datetime | None = None
    psp_refund_ref: str | None = None
    email_draft: str
    reason_fr: str = ""
    """Motif en français (variable ``motif_remboursement`` de l'email 18), figé à la préparation."""
    request_ref: str | None = None
    """Annulation demandée par le client : référence de sa demande écrite (ticket du service client)."""

    @field_validator("prepared_at", "approved_at", "executed_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _aware(v, "horodatage")


def refund_id_for(order_id: str) -> str:
    """Identifiant du remboursement préparé d'une commande (un seul par commande)."""
    return f"pdr:{order_id}"


def reservation_order_base(order_id: str) -> str:
    """Commande Shopify d'une réservation (``<commande>#<n>`` -> ``<commande>``) : expédition, dette, reconnaissance."""
    return order_id.split(RESERVATION_LINE_SEPARATOR, 1)[0]



def reservation_phase(predrop: Predrop, *, accepting: bool, at: datetime) -> Literal["prioritaire", "ouvertes", "fermees"]:
    """Statut public des réservations : ``prioritaire`` (inscrits aux alertes, fenêtre prioritaire), ``ouvertes``
    (tout le monde) ou ``fermees`` — jamais une heure de fermeture, un compte à rebours ni un nombre d'unités."""
    if not accepting:
        return "fermees"
    return "prioritaire" if predrop.in_priority_window(at) else "ouvertes"


def refund_email_draft(
    *, order_id: str, amount: Decimal, reason: str, public_sku: str | None, shipping: Decimal = Decimal("0")
) -> str:
    """Brouillon d'email au client (français, sans donnée personnelle : n8n retrouve le destinataire par la commande)."""
    why = refund_reason_fr(reason)
    product = f" ({public_sku})" if public_sku else ""
    included = "supplément et frais de livraison compris" if shipping > 0 else "supplément compris"
    return (
        "Bonjour,\n\n"
        f"Votre réservation pré-drop{product}, commande {order_id} : {why}.\n"
        f"Conformément à nos conditions de réservation garantie, nous vous remboursons intégralement {q2(amount)} CHF, "
        f"{included}, "
        "sur votre moyen de paiement d'origine.\n\n"
        "Nous vous présentons nos excuses pour ce désagrément.\n\n"
        "{{NOM_BOUTIQUE}}"
    )


class ServicePlan(FrozenModel):
    """Plan de service après une réduction d'allocation : pré-drop servi en premier, puis le drop."""

    new_allocation: int = Field(ge=0)
    safety_reserve: int = Field(ge=0)
    """Réserve de sécurité du **drop** sur l'allocation réduite (jamais retenue contre une réservation payée)."""
    servable: int = Field(ge=0)
    """Unités qui servent les réservations : **toute** l'allocation réduite (la réserve passe après elles)."""
    kept: tuple[str, ...] = ()
    """Commandes servies (ordre de paiement)."""
    refunded: tuple[str, ...] = ()
    """Dernières commandes à rembourser intégralement (ordre de paiement : à partir de la première qui ne tient plus)."""
    kept_units: int = Field(ge=0)
    drop_quota_before: int = Field(ge=0)
    drop_quota_after: int = Field(ge=0)


def plan_service(
    confirmed: Sequence[PredropReservation],
    new_allocation: int,
    *,
    reserve_min_units: int,
    reserve_share: Decimal,
    drop_quota_before: int = 0,
    already_served: frozenset[str] = frozenset(),
) -> ServicePlan:
    """Réservations servies en **ordre de paiement** sur **toute** l'allocation réduite.

    Revue pré-drop (PDL-05) : la réserve de sécurité n'est jamais retenue contre une réservation payée (sinon l'unité
    gardée partirait au prix du drop pendant que le dernier réservant est remboursé) ; elle ne vaut que pour le drop.
    La réduction prend d'abord sur le quota drop ; s'il manque encore des unités, la première réservation qui ne tient
    plus et **toutes les suivantes** (ordre de paiement) sont remboursées intégralement — jamais une réservation payée
    avant une autre servie. ``already_served`` : réservations dont la **ligne** a déjà été expédiée (servies, jamais
    remboursées par un plan).
    """
    alloc = max(0, int(new_allocation))
    reserve = reserve_units(alloc, min_units=reserve_min_units, share=reserve_share)
    servable = alloc
    served = [r for r in confirmed if r.order_id in already_served]
    ordered = sorted((r for r in confirmed if r.order_id not in already_served), key=lambda r: (r.paid_at, r.seq))
    kept: list[str] = [r.order_id for r in sorted(served, key=lambda r: (r.paid_at, r.seq))]
    refunded: list[str] = []
    used = sum(r.qty for r in served)
    for r in ordered:
        if not refunded and used + r.qty <= servable:
            kept.append(r.order_id)
            used += r.qty
        else:
            refunded.append(r.order_id)
    return ServicePlan(
        new_allocation=alloc,
        safety_reserve=reserve,
        servable=servable,
        kept=tuple(kept),
        refunded=tuple(refunded),
        kept_units=used,
        drop_quota_before=max(0, drop_quota_before),
        drop_quota_after=preorder_quota(alloc, used, reserve),
    )


ShippedCheck = Callable[[PredropReservation], bool]
"""Vrai si la **ligne** de la réservation a été expédiée (SKU ``-RESA-`` du pré-drop, quantité au moins égale)."""


def _no_shipment(_: PredropReservation) -> bool:
    return False


class ReductionResult(FrozenModel):
    """Résultat d'une réduction d'allocation : allocation en vigueur, plan de service, remboursements préparés."""

    allocation: FirmAllocation
    reduction: AllocationReduction
    plan: ServicePlan
    refunds: tuple[PreparedRefund, ...] = ()
    created: bool = True


class PredropDebt(FrozenModel):
    """Argent encaissé en pré-drop non encore livré ni remboursé : **dette** de la photo du stop-loss."""

    total_chf: Decimal
    reservations: int = Field(ge=0)
    by_predrop: dict[str, Decimal] = Field(default_factory=dict)


# ------------------------------------------------------------------------ éligibilité


class EligibilityCheck(FrozenModel):
    """Une condition d'éligibilité (code stable, remplie ou non, détail en français)."""

    code: str
    ok: bool
    detail: str


class Eligibility(FrozenModel):
    """Éligibilité d'une référence au pré-drop (toutes les conditions requises, sinon pas de pré-drop)."""

    product_key: str
    eligible: bool
    needs_owner: tuple[str, ...] = ()
    checks: tuple[EligibilityCheck, ...] = ()
    prices: PredropPrices | None = None
    quota: QuotaSplit | None = None
    demand_score: Decimal | None = None
    demand_interested: int | None = None

    def failed(self) -> tuple[str, ...]:
        """Codes des conditions non remplies."""
        return tuple(c.code for c in self.checks if not c.ok)

    def view(self) -> dict[str, Any]:
        """Lecture sans coût ni marge (les prix drop et pré-drop seulement)."""
        prices = self.prices
        return {
            "product_key": self.product_key,
            "eligible": self.eligible,
            "needs_owner": list(self.needs_owner),
            "failed": list(self.failed()),
            "checks": [c.model_dump(mode="json") for c in self.checks],
            "prix_drop_chf": None if prices is None else prices.drop_price,
            "prix_predrop_chf": None if prices is None else prices.predrop_price,
            "supplement_effectif": None if prices is None else prices.effective_premium_pct,
            "plafonnements": [] if prices is None else list(prices.capped_by),
            "quota": None if self.quota is None else self.quota.model_dump(mode="json"),
            "demand_score": self.demand_score,
            "demand_interested": self.demand_interested,
        }


def demand_score(interested: int, allocation: int) -> Decimal | None:
    """Inscrits consentants intéressés / allocation ferme (None si l'allocation est nulle)."""
    if allocation <= 0:
        return None
    return q4(Decimal(max(0, interested)) / Decimal(allocation))


def evaluate_eligibility(
    *,
    product_key: str,
    config_status: PredropConfigStatus,
    allocation: FirmAllocation | None,
    demand: DemandSignal | None,
    now: datetime,
    listing_known: bool,
    listing_approved: bool,
    cost: Decimal | None,
    params: PricingParams,
    market_ref: Decimal | None,
    stoploss_problem: str | None,
    quarantined: bool,
    committed: int = 0,
    open_predrop: str | None = None,
) -> Eligibility:
    """Toutes les conditions du pré-drop, évaluées sur les registres du moteur (rien n'est déclaré par le demandeur).

    ``stoploss_problem`` : None si le stop-loss est évalué sans gel ni blocage de la référence ; sinon le motif
    (état inconnu compris : fermé par défaut). ``open_predrop`` : identifiant d'un pré-drop déjà ouvert ou en attente
    pour la référence (un seul à la fois).
    """
    checks: list[EligibilityCheck] = []

    def add(code: str, ok: bool, detail: str) -> None:
        checks.append(EligibilityCheck(code=code, ok=ok, detail=detail))

    config = config_status.config if config_status.enabled else None
    add("CONFIG_SIGNED", config is not None,
        "paramètres signés par la propriétaire" if config is not None else config_status.reason)  # fmt: skip
    add("SINGLE_PREDROP", open_predrop is None,
        "aucun autre pré-drop en cours ni à solder sur la référence" if open_predrop is None
        else f"pré-drop {open_predrop} en cours, à solder ou déjà sur cette allocation ferme")  # fmt: skip
    add("LISTING_APPROVED", listing_known and listing_approved,
        "fiche validée par la propriétaire (contenu en vigueur)" if listing_known and listing_approved
        else ("fiche absente du catalogue validé" if not listing_known
              else "fiche non validée par la propriétaire (POST /catalog/approvals, contenu en vigueur)"))  # fmt: skip
    alloc_qty = allocation.qty if allocation is not None else 0
    add("FIRM_ALLOCATION", allocation is not None and alloc_qty > 0,
        f"allocation ferme {alloc_qty} unité(s), confirmation {allocation.supplier_confirmation_ref}"
        if allocation is not None and alloc_qty > 0
        else "aucune allocation ferme enregistrée (confirmation fournisseur : propriétaire ou workflow 03)")  # fmt: skip
    quota: QuotaSplit | None = None
    if config is not None:
        quota = split_quota(alloc_qty, committed, share=config.predrop_share_of_allocation,
                            reserve_min_units=config.safety_reserve_min_units,
                            reserve_share=config.safety_reserve_share)  # fmt: skip
        add("QUOTA", quota.predrop_remaining >= 1,
            f"quota pré-drop {quota.predrop_remaining} (allocation {quota.firm_allocation}, réserve "
            f"{quota.safety_reserve}, engagées {quota.predrop_committed})")  # fmt: skip
    else:
        add("QUOTA", False, "quota non calculable sans paramètres signés")
    score: Decimal | None = None
    interested: int | None = None
    if demand is None:
        add("DEMAND", False, "aucun compte d'inscrits intéressés (POST /predrop/demand, workflow marketing)")
    elif now - demand.as_of > DEMAND_SIGNAL_MAX_AGE or demand.as_of - now > FUTURE_SKEW:
        add("DEMAND", False, f"compte d'inscrits du {demand.as_of.isoformat()} périmé (> {DEMAND_SIGNAL_MAX_AGE.days} j) "
                             "ou daté du futur")  # fmt: skip
    else:
        interested = demand.interested_consenting_subscribers
        score = demand_score(interested, alloc_qty)
        threshold = config.demand_threshold if config is not None else None
        ok = score is not None and threshold is not None and score >= threshold
        add("DEMAND", ok, f"score de demande {score} (inscrits {interested} / allocation {alloc_qty}) ; seuil {threshold}")
    prices: PredropPrices | None = None
    needs_owner: list[str] = []
    if cost is None or cost <= 0:
        add("COST_KNOWN", False, "coût rendu inconnu du moteur (offre évaluée de moins de 24 h ou stock au coût)")
    else:
        add("COST_KNOWN", True, "coût rendu connu du moteur")
        if config is not None:
            prices = compute_prices(cost, params, config, market_ref=market_ref)
            add("DROP_PRICE", "DROP_PRICE_BLOCKED" not in prices.problems and "DROP_BELOW_FLOOR" not in prices.problems,
                f"prix drop {prices.drop_price} ({prices.drop_decision_status})")  # fmt: skip
            add("PREDROP_MARGIN", not ({"PREDROP_BELOW_FLOOR", "PREDROP_BELOW_TARGET"} & set(prices.problems)),
                f"prix pré-drop {prices.predrop_price} : marge revérifiée (planchers durs et marge cible)")  # fmt: skip
            add("MARKET", "ABOVE_MARKET" not in prices.problems,
                "référence marché inconnue : validation de la propriétaire" if market_ref is None
                else f"prix pré-drop {prices.predrop_price} ≤ référence marché {market_ref}"
                if "ABOVE_MARKET" not in prices.problems else f"prix drop {prices.drop_price} > référence marché {market_ref}")  # fmt: skip
            needs_owner.extend(prices.needs_owner)
    add("STOPLOSS", stoploss_problem is None, "aucun gel du stop-loss" if stoploss_problem is None else stoploss_problem)
    add("QUARANTINE", not quarantined, "aucune quarantaine" if not quarantined else "référence en quarantaine (incident)")
    eligible = all(c.ok for c in checks) and prices is not None and prices.ok
    return Eligibility(
        product_key=product_key,
        eligible=eligible,
        needs_owner=tuple(dict.fromkeys(needs_owner)),
        checks=tuple(checks),
        prices=prices,
        quota=quota,
        demand_score=score,
        demand_interested=interested,
    )


# ------------------------------------------------------------------------ offre publique


def public_offer(predrop: Predrop, *, accepting: bool) -> dict[str, Any]:
    """Offre publique (liste blanche :data:`PUBLIC_OFFER_FIELDS`) : statut, date du drop, deux prix, garantie.

    Aucune fausse urgence : ni compte à rebours, ni heure de fermeture, ni « plus que N » ; aucun coût ni marge.
    """
    window = predrop.priority_window_hours
    out = {
        "predrop_id": predrop.predrop_id,
        "product_key": predrop.product_key,
        "public_sku": predrop.public_sku,
        "statut": STATUS_OPEN_FR if accepting else STATUS_CLOSED_FR,
        "reservations_ouvertes": accepting,
        "date_drop": predrop.drop_date.isoformat(),
        "prix_predrop_chf": predrop.prices.predrop_price,
        "prix_drop_chf": predrop.prices.drop_price,
        "limite_par_client": predrop.per_customer_limit,
        "acces_prioritaire": (
            f"Les inscrits aux alertes réservent en priorité pendant les {window} premières heures." if window else None
        ),
        "garantie": GUARANTEE_TEXT_FR,
        "difference": NO_DIFFERENCE_REFUND_FR,
    }
    assert tuple(out) == PUBLIC_OFFER_FIELDS
    return out


# ------------------------------------------------------------------------- registre


class PredropRegistry:
    """Registre persisté du pré-drop (journal ``predrop``, ajout seul, écrit d'abord, appliqué ensuite).

    Contient : allocations fermes et réductions, comptes agrégés de demande, pré-drops, réservations payées et
    remboursements préparés. Un seul verrou : chaque décision (quota, limite par client, plan de service) est prise
    et écrite atomiquement — deux paiements simultanés sur la dernière unité n'en confirment jamais qu'un.
    Relu au démarrage (:meth:`restore`) ; un journal illisible lève :class:`PredropPersistenceError` (service gelé).
    """

    STREAM = "predrop"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._store = store
        self._allocations: dict[str, FirmAllocation] = {}
        self._allocation_sets: dict[tuple[str, str], FirmAllocation] = {}
        """(référence, confirmation fournisseur) -> allocation telle qu'enregistrée (avant toute réduction)."""
        self._reductions: list[AllocationReduction] = []
        self._plans: dict[tuple[str, str], ServicePlan] = {}
        """(référence, confirmation de la réduction) -> plan de service décidé (rejeu idempotent)."""
        self._demand: dict[str, DemandSignal] = {}
        self._predrops: dict[str, Predrop] = {}
        self._reservations: dict[str, PredropReservation] = {}
        self._refunds: dict[str, PreparedRefund] = {}

    # -- persistance --------------------------------------------------------------
    @classmethod
    def restore(cls, store: StateJournal) -> PredropRegistry:
        """Relit et rejoue le journal (:class:`PredropPersistenceError` s'il est illisible ou incohérent)."""
        try:
            records = store.load()
        except StateStoreError as exc:
            raise PredropPersistenceError(f"journal du pré-drop : {exc}") from exc
        registry = cls()
        for n, record in enumerate(records, start=1):
            try:
                registry._apply(record)
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise PredropPersistenceError(f"journal du pré-drop : enregistrement {n} illisible ({exc})") from exc
        registry._store = store
        return registry

    def _write(self, record: dict[str, Any]) -> None:
        if self._store is None:
            return
        try:
            self._store.append(record)
        except StateStoreError as exc:
            raise PredropPersistenceError(f"pré-drop : enregistrement refusé ({exc}) — rien n'est appliqué") from exc

    def _commit(self, record: dict[str, Any]) -> None:
        """Écrit d'abord, applique ensuite (même code qu'au rejeu)."""
        self._write(record)
        self._apply(record)

    def _apply(self, record: Mapping[str, Any]) -> None:
        op = record["op"]
        if op == "allocation":
            item = FirmAllocation.model_validate(record["allocation"])
            self._allocations[item.product_key] = item
            self._allocation_sets[(item.product_key, item.supplier_confirmation_ref)] = item
        elif op == "reduction":
            reduction = AllocationReduction.model_validate(record["reduction"])
            item = FirmAllocation.model_validate(record["allocation"])
            plan = ServicePlan.model_validate(record["plan"])
            self._reductions.append(reduction)
            self._plans[(reduction.product_key, reduction.supplier_confirmation_ref)] = plan
            self._allocations[item.product_key] = item
            for raw in record.get("refunds", []):
                refund = PreparedRefund.model_validate(raw)
                self._refunds[refund.refund_id] = refund
        elif op == "demand":
            signal = DemandSignal.model_validate(record["signal"])
            self._demand[signal.product_key] = signal
        elif op == "predrop":
            predrop = Predrop.model_validate(record["predrop"])
            self._predrops[predrop.predrop_id] = predrop
        elif op == "reservation":
            reservation = PredropReservation.model_validate(record["reservation"])
            if reservation.predrop_id not in self._predrops:
                raise KeyError(reservation.predrop_id)
            self._reservations[reservation.order_id] = reservation
            if record.get("refund") is not None:
                refund = PreparedRefund.model_validate(record["refund"])
                self._refunds[refund.refund_id] = refund
        elif op == "refund":
            refund = PreparedRefund.model_validate(record["refund"])
            self._refunds[refund.refund_id] = refund
        else:
            raise KeyError(f"opération inconnue : {op}")

    # -- allocations fermes ---------------------------------------------------------
    def allocation(self, product_key: str) -> FirmAllocation | None:
        """Allocation ferme en vigueur (None si aucune)."""
        with self._lock:
            return self._allocations.get(product_key)

    def allocations(self) -> tuple[FirmAllocation, ...]:
        """Allocations en vigueur, par référence."""
        with self._lock:
            return tuple(self._allocations[k] for k in sorted(self._allocations))

    def reductions(self, product_key: str | None = None) -> tuple[AllocationReduction, ...]:
        """Réductions enregistrées (historique)."""
        with self._lock:
            return tuple(r for r in self._reductions if product_key is None or r.product_key == product_key)

    def set_allocation(self, allocation: FirmAllocation) -> tuple[FirmAllocation, bool]:
        """Enregistre une allocation ferme ; (allocation, nouvelle ?). Une baisse passe par :meth:`reduce_allocation`.

        Même confirmation, même contenu : sans effet ; même confirmation, autre contenu : refus (jamais réécrite) ;
        nouvelle confirmation : remplace l'allocation si elle ne baisse pas (sinon refus : réduction et remboursements).
        """
        if allocation.qty < 1:
            raise PredropError("allocation ferme : au moins 1 unité (une annulation passe par la réduction)")
        with self._lock:
            current = self._allocations.get(allocation.product_key)
            recorded = self._allocation_sets.get((allocation.product_key, allocation.supplier_confirmation_ref))
            if recorded is not None:
                if recorded.content() == allocation.content():
                    # Rejeu (même après une réduction) : l'allocation en vigueur reste celle du registre.
                    return current if current is not None else recorded, False
                raise PredropError(
                    f"allocation {allocation.supplier_confirmation_ref} déjà enregistrée avec un autre contenu : "
                    "jamais réécrite (nouvelle confirmation fournisseur ou réduction)"
                )
            if current is not None:
                if allocation.qty < current.qty:
                    raise PredropError(
                        f"allocation en baisse ({current.qty} → {allocation.qty}) : passer par la réduction "
                        "(POST /predrop/allocations/{product_key}/reduce), qui sert le pré-drop en premier et prépare "
                        "les remboursements"
                    )
            self._commit({"op": "allocation", "allocation": allocation.model_dump(mode="json")})
            return allocation, True

    def reduce_allocation(
        self,
        product_key: str,
        new_qty: int,
        *,
        supplier_confirmation_ref: str,
        reason: str,
        recorded_by: str,
        at: datetime,
        autonomy_level: int,
        shipped: ShippedCheck = _no_shipment,
    ) -> ReductionResult:
        """Réduction annoncée par le fournisseur : plan de service, quota drop réduit d'abord, remboursements préparés.

        Idempotente par référence de confirmation (même nouvelle quantité : sans effet ; autre : refus). Une hausse
        n'est jamais une réduction (refus). ``shipped`` : réservations dont la **ligne** est déjà expédiée (servies,
        jamais remboursées) — l'expédition d'un autre article de la même commande ne compte pas.
        """
        _aware(at, "at")
        with self._lock:
            current = self._allocations.get(product_key)
            if current is None:
                raise PredropError(f"{product_key} : aucune allocation ferme à réduire")
            for done in self._reductions:
                if done.product_key == product_key and done.supplier_confirmation_ref == supplier_confirmation_ref:
                    if done.new_qty != new_qty:
                        raise PredropError(
                            f"réduction {supplier_confirmation_ref} déjà enregistrée à {done.new_qty} unité(s)"
                        )
                    plan = self._plans[(product_key, supplier_confirmation_ref)]
                    refunds = tuple(self._refunds[refund_id_for(oid)] for oid in plan.refunded
                                    if refund_id_for(oid) in self._refunds)  # fmt: skip
                    return ReductionResult(allocation=current, reduction=done, plan=plan, refunds=refunds, created=False)
            if new_qty < 0 or new_qty >= current.qty:
                raise PredropError(
                    f"réduction : nouvelle quantité {new_qty} ≥ allocation en vigueur {current.qty} (une hausse est une "
                    "nouvelle allocation ferme)"
                )
            reduction = AllocationReduction(
                product_key=product_key, previous_qty=current.qty, new_qty=new_qty,
                supplier_confirmation_ref=supplier_confirmation_ref, reason=reason, recorded_by=recorded_by,
                recorded_at=at,
            )  # fmt: skip
            plan = self._plan(product_key, new_qty, shipped)
            prepared: list[PreparedRefund] = []
            for order_id in plan.refunded:
                res = self._reservations[order_id]
                if refund_id_for(order_id) in self._refunds:
                    continue
                prepared.append(self._new_refund(res, "ALLOCATION_REDUCED", at=at, by=recorded_by,
                                                 autonomy_level=autonomy_level))  # fmt: skip
            updated = current.model_copy(update={"qty": new_qty})
            self._commit({
                "op": "reduction",
                "reduction": reduction.model_dump(mode="json"),
                "allocation": updated.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "refunds": [r.model_dump(mode="json") for r in prepared],
            })  # fmt: skip
            return ReductionResult(allocation=updated, reduction=reduction, plan=plan, refunds=tuple(prepared))

    def _plan(self, product_key: str, new_qty: int, shipped: ShippedCheck = _no_shipment) -> ServicePlan:
        predrop = self._predrop_on_allocation(product_key)
        if predrop is None:
            reserve = reserve_units(new_qty, min_units=MIN_RESERVE_UNITS, share=MIN_RESERVE_SHARE)
            servable = preorder_quota(new_qty, 0, reserve)
            current = self._allocations.get(product_key)
            before = 0
            if current is not None:
                before = preorder_quota(current.qty, 0, reserve_units(current.qty, min_units=MIN_RESERVE_UNITS,
                                                                       share=MIN_RESERVE_SHARE))  # fmt: skip
            return ServicePlan(new_allocation=new_qty, safety_reserve=reserve, servable=servable, kept_units=0,
                               drop_quota_before=before, drop_quota_after=servable)  # fmt: skip
        confirmed = self._committed_reservations(predrop.predrop_id)
        before = self._quota_locked(predrop).drop_quota
        served = frozenset(r.order_id for r in confirmed if shipped(r))
        return plan_service(confirmed, new_qty, reserve_min_units=predrop.reserve_min_units,
                            reserve_share=predrop.reserve_share, drop_quota_before=before,
                            already_served=served)  # fmt: skip

    # -- demande agrégée -------------------------------------------------------------
    def demand(self, product_key: str) -> DemandSignal | None:
        """Dernier compte agrégé d'inscrits intéressés (None si aucun)."""
        with self._lock:
            return self._demand.get(product_key)

    def record_demand(self, signal: DemandSignal) -> tuple[DemandSignal, bool]:
        """Enregistre un compte agrégé ; plus ancien que celui en vigueur : refus (jamais de retour en arrière)."""
        with self._lock:
            current = self._demand.get(signal.product_key)
            if current is not None:
                if current.as_of == signal.as_of:
                    if current.interested_consenting_subscribers == signal.interested_consenting_subscribers:
                        return current, False
                    raise PredropError("compte d'inscrits déjà relevé à cette date avec une autre valeur")
                if signal.as_of < current.as_of:
                    raise PredropError("compte d'inscrits plus ancien que celui en vigueur : refusé")
            self._commit({"op": "demand", "signal": signal.model_dump(mode="json")})
            return signal, True

    # -- pré-drops -------------------------------------------------------------------
    def get(self, predrop_id: str) -> Predrop | None:
        """Pré-drop par identifiant."""
        with self._lock:
            return self._predrops.get(predrop_id)

    def predrops(self) -> tuple[Predrop, ...]:
        """Pré-drops par date d'ouverture demandée."""
        with self._lock:
            return tuple(sorted(self._predrops.values(), key=lambda p: (p.requested_at, p.predrop_id)))

    def active_for(self, product_key: str) -> Predrop | None:
        """Pré-drop ouvert ou en attente de la propriétaire pour la référence (un seul à la fois)."""
        with self._lock:
            return next((p for p in self._predrops.values() if p.product_key == product_key and p.status != "CLOSED"), None)

    def _predrop_on_allocation(self, product_key: str) -> Predrop | None:
        allocation = self._allocations.get(product_key)
        if allocation is None:
            return None
        found = [p for p in self._predrops.values()
                 if p.product_key == product_key and p.allocation_ref == allocation.supplier_confirmation_ref]  # fmt: skip
        if not found:
            # Allocation remplacée (nouvelle confirmation) après l'ouverture : le pré-drop le plus récent de la référence.
            found = [p for p in self._predrops.values() if p.product_key == product_key]
        return max(found, key=lambda p: p.requested_at) if found else None

    def open(self, predrop: Predrop) -> tuple[Predrop, bool]:
        """Enregistre un pré-drop (``OPEN`` ou ``PENDING_OWNER``) ; un seul en cours par référence."""
        with self._lock:
            existing = self._predrops.get(predrop.predrop_id)
            if existing is not None:
                raise PredropError(f"pré-drop {predrop.predrop_id} déjà enregistré ({existing.status})")
            active = self.active_for(predrop.product_key)
            if active is not None:
                raise PredropError(f"{predrop.product_key} : pré-drop {active.predrop_id} déjà en cours ({active.status})")
            same = next((p for p in self._predrops.values() if p.product_key == predrop.product_key
                         and p.allocation_ref == predrop.allocation_ref), None)  # fmt: skip
            if same is not None:
                raise PredropError(
                    f"allocation {predrop.allocation_ref} déjà engagée par le pré-drop {same.predrop_id} : un seul "
                    "pré-drop par allocation ferme (nouvelle confirmation fournisseur requise)"
                )
            self._commit({"op": "predrop", "predrop": predrop.model_dump(mode="json")})
            return predrop, True

    def unsettled(self, product_key: str, shipped: ShippedCheck, *, ignore: str | None = None) -> str | None:
        """Pré-drop de la référence encore en cours (ouvert ou en attente) ou dont des réservations confirmées ne sont
        ni expédiées ni remboursées, ou qui a déjà engagé l'allocation ferme en vigueur (None : aucun).

        Un nouveau pré-drop n'est ouvert qu'une fois le précédent soldé : jamais deux quotas sur les mêmes unités.
        """
        with self._lock:
            allocation = self._allocations.get(product_key)
            for p in sorted(self._predrops.values(), key=lambda x: x.requested_at):
                if p.product_key != product_key or p.predrop_id == ignore:
                    continue
                if p.status != "CLOSED":
                    return p.predrop_id
                if allocation is not None and p.allocation_ref == allocation.supplier_confirmation_ref:
                    return p.predrop_id
                if any(not shipped(r) for r in self._committed_reservations(p.predrop_id)):
                    return p.predrop_id
        return None

    def update(self, predrop: Predrop) -> Predrop:
        """Remplace l'état d'un pré-drop existant (validation de la propriétaire, fermeture)."""
        with self._lock:
            if predrop.predrop_id not in self._predrops:
                raise PredropError(f"pré-drop {predrop.predrop_id} inconnu")
            self._commit({"op": "predrop", "predrop": predrop.model_dump(mode="json")})
            return predrop

    def close(self, predrop_id: str, *, by: str, at: datetime, reason: str) -> tuple[Predrop, bool]:
        """Ferme un pré-drop (acte protecteur) ; déjà fermé : sans effet."""
        with self._lock:
            predrop = self._predrops.get(predrop_id)
            if predrop is None:
                raise PredropError(f"pré-drop {predrop_id} inconnu")
            if predrop.status == "CLOSED":
                return predrop, False
            closed = predrop.model_copy(update={"status": "CLOSED", "closed_by": by, "closed_at": at,
                                                "close_reason": reason})  # fmt: skip
            self._commit({"op": "predrop", "predrop": closed.model_dump(mode="json")})
            return closed, True

    # -- quotas ----------------------------------------------------------------------
    def _committed_reservations(self, predrop_id: str) -> list[PredropReservation]:
        return [r for r in self._reservations.values()
                if r.predrop_id == predrop_id and r.status == "CONFIRMED" and refund_id_for(r.order_id) not in self._refunds]  # fmt: skip

    def committed_units(self, predrop_id: str) -> int:
        """Unités confirmées (ni remboursées, ni retirées par une réduction), expédiées comprises : base du quota."""
        with self._lock:
            return sum(r.qty for r in self._committed_reservations(predrop_id))

    def unshipped_committed_units(self, predrop_id: str, shipped: ShippedCheck) -> int:
        """Unités confirmées **non encore expédiées** (ligne de réservation pas encore partie) : unités à retenir hors de
        toute vente au prix du drop et grandeur homogène avec les unités engagées non expédiées de Shopify."""
        with self._lock:
            items = self._committed_reservations(predrop_id)
        return sum(r.qty for r in items if not shipped(r))

    def _quota_locked(self, predrop: Predrop, *, at: datetime | None = None) -> QuotaSplit:
        allocation = self._allocations.get(predrop.product_key)
        qty = allocation.qty if allocation is not None else 0
        open_now = predrop.status != "CLOSED" if at is None else predrop.accepting_at(at)
        return split_quota(qty, sum(r.qty for r in self._committed_reservations(predrop.predrop_id)),
                           share=predrop.predrop_share, reserve_min_units=predrop.reserve_min_units,
                           reserve_share=predrop.reserve_share, predrop_open=open_now)  # fmt: skip

    def quota(self, predrop_id: str, *, at: datetime | None = None) -> QuotaSplit:
        """Partage de l'allocation du pré-drop (unités ; interne)."""
        with self._lock:
            predrop = self._predrops.get(predrop_id)
            if predrop is None:
                raise PredropError(f"pré-drop {predrop_id} inconnu")
            return self._quota_locked(predrop, at=at)

    def accepting(self, predrop_id: str, at: datetime) -> bool:
        """Vrai si le pré-drop accepte une réservation à ``at`` (ouvert et quota restant ≥ 1)."""
        with self._lock:
            predrop = self._predrops.get(predrop_id)
            if predrop is None or not predrop.accepting_at(at):
                return False
            return self._quota_locked(predrop, at=at).predrop_remaining >= 1

    # -- réservations -----------------------------------------------------------------
    def is_reservation(self, order_id: str) -> bool:
        """Vrai si la commande porte une réservation pré-drop enregistrée.

        Une commande à plusieurs pré-drops est enregistrée ``<commande>``, ``<commande>#2``… ; un envoi
        ``<commande>/envoi-<n>`` désigne la même commande.
        """
        base = shipment_order_base(order_id)
        return bool(self.reservations_for_order(base))

    def reservations_for_order(self, order_base: str) -> tuple[PredropReservation, ...]:
        """Réservations enregistrées d'une commande Shopify (``<commande>`` et ``<commande>#<n>``), par ordre."""
        prefix = f"{order_base}{RESERVATION_LINE_SEPARATOR}"
        with self._lock:
            found = [r for k, r in self._reservations.items() if k == order_base or k.startswith(prefix)]
        return tuple(sorted(found, key=lambda r: r.seq))

    def predrop_for_reservation_sku(self, sku: str) -> Predrop | None:
        """Pré-drop d'une ligne au SKU d'une fiche de réservation (SKU **figé à l'ouverture**, stable après un report)."""
        with self._lock:
            for predrop in sorted(self._predrops.values(), key=lambda p: (p.requested_at, p.predrop_id)):
                if predrop.sku is not None and sku == predrop.sku:
                    return predrop
        return None

    def product_for_reservation_sku(self, sku: str) -> str | None:
        """Référence d'une ligne de commande au SKU d'une fiche de réservation (``<SKU>-RESA-<AAAAMMJJ>``) — None sinon.

        Le SKU d'une fiche de réservation n'est pas celui de la fiche normale : sans cette résolution, la ligne
        expédiée resterait « non rattachée » (coût des ventes en attente). Seuls les pré-drops enregistrés comptent.
        """
        predrop = self.predrop_for_reservation_sku(sku)
        return predrop.product_key if predrop is not None else None

    def latest_for(self, product_key: str) -> Predrop | None:
        """Dernier pré-drop validé (ouvert ou fermé) de la référence — jamais un pré-drop en attente de la propriétaire."""
        with self._lock:
            found = [p for p in self._predrops.values() if p.product_key == product_key and p.status != "PENDING_OWNER"]
        return max(found, key=lambda p: (p.requested_at, p.predrop_id)) if found else None

    def reservation(self, order_id: str) -> PredropReservation | None:
        """Réservation d'une commande (None si inconnue)."""
        with self._lock:
            return self._reservations.get(order_id)

    def reservations(self, predrop_id: str | None = None) -> tuple[PredropReservation, ...]:
        """Réservations (d'un pré-drop), dans l'ordre d'enregistrement."""
        with self._lock:
            items = sorted(self._reservations.values(), key=lambda r: r.seq)
        return tuple(r for r in items if predrop_id is None or r.predrop_id == predrop_id)

    def _new_refund(
        self, res: PredropReservation, reason: str, *, at: datetime, by: str, autonomy_level: int,
        request_ref: str | None = None,
    ) -> PreparedRefund:
        level = max(1, min(4, int(autonomy_level)))
        auto = level >= AUTO_REFUND_MIN_LEVEL
        predrop = self._predrops.get(res.predrop_id)
        return PreparedRefund(
            refund_id=refund_id_for(res.order_id),
            order_id=res.order_id,
            predrop_id=res.predrop_id,
            product_key=res.product_key,
            amount_ttc=res.refund_amount,
            shipping_ttc=q2(res.shipping_paid_ttc),
            reason=reason,
            prepared_at=at,
            prepared_by=by,
            autonomy_level=level,
            status="APPROVED" if auto else "PENDING_OWNER",
            approved_by=f"moteur (niveau d'autonomie {level})" if auto else None,
            approved_at=at if auto else None,
            email_draft=refund_email_draft(order_id=res.order_id, amount=res.refund_amount, reason=reason,
                                           public_sku=predrop.public_sku if predrop is not None else None,
                                           shipping=res.shipping_paid_ttc),  # fmt: skip
            reason_fr=refund_reason_fr(reason),
            request_ref=request_ref,
        )

    def record_reservation(
        self,
        *,
        predrop_id: str,
        order_id: str,
        customer_ref: str,
        qty: int,
        amount_paid_ttc: Decimal,
        paid_at: datetime,
        priority_access: bool,
        recorded_by: str,
        at: datetime,
        enabled: bool,
        blocked_reason: str | None,
        autonomy_level: int,
        shipping_paid_ttc: Decimal = ZERO,
        listing_retired_at: datetime | None = None,
    ) -> tuple[PredropReservation, PreparedRefund | None, bool]:
        """Enregistre une réservation **payée** (atomique) ; (réservation, remboursement préparé, nouvelle ?).

        Jamais refusée pour un motif métier (le client a payé) : fermé à la date du paiement, hors fenêtre prioritaire,
        montant ≠ prix pré-drop × quantité, limite par client atteinte ou quota épuisé => ``NOT_SERVED`` et
        remboursement **intégral** préparé (frais de livraison payés compris). Même commande, même contenu : sans effet ;
        autre contenu : :class:`PredropError` (409). Pré-drop inconnu : :class:`PredropError` (rien à rattacher).

        Suspension par précaution (revue pré-drop PDL-03) : pré-drop désactivé (``enabled`` faux) ou suspendu
        (``blocked_reason`` : gel, quarantaine, relevé de trésorerie manquant) => ``NOT_SERVED`` **seulement** si le
        paiement est postérieur au **retrait vérifié** de la fiche de réservation (``listing_retired_at``, registre des
        fiches publiées) ; un paiement antérieur a été fait sur une fiche « Réservations ouvertes » : le contrat est
        conclu, la réservation reste servie (l'exécution attend la levée du blocage).
        """
        _aware(paid_at, "paid_at")
        _aware(at, "at")
        if listing_retired_at is not None:
            _aware(listing_retired_at, "listing_retired_at")
        if not _SHA256_RE.match(customer_ref or ""):
            raise PredropError("customer_ref : empreinte sha256 hexadécimale de l'identifiant client (jamais l'email)")
        if qty < 1:
            raise PredropError("quantité payée : au moins 1")
        if amount_paid_ttc < 0 or shipping_paid_ttc < 0:
            raise PredropError("montants payés : jamais négatifs")
        with self._lock:
            existing = self._reservations.get(order_id)
            probe = {
                "order_id": order_id, "predrop_id": predrop_id, "customer_ref": customer_ref, "qty": qty,
                "amount_paid_ttc": str(q2(amount_paid_ttc)), "paid_at": paid_at.isoformat(),
                "priority_access": priority_access, "shipping_paid_ttc": str(q2(shipping_paid_ttc)),
            }  # fmt: skip
            if existing is not None:
                if existing.content() != probe:
                    raise PredropError(f"commande {order_id} déjà enregistrée avec un autre contenu")
                return existing, self._refunds.get(refund_id_for(order_id)), False
            predrop = self._predrops.get(predrop_id)
            if predrop is None:
                raise PredropError(f"pré-drop {predrop_id} inconnu : réservation non rattachable")
            price = predrop.prices.predrop_price
            if price is None:  # pragma: no cover - un pré-drop enregistré a toujours ses deux prix
                raise PredropError(f"pré-drop {predrop_id} sans prix")
            expected = q2(price * qty)
            suspended = (not enabled or bool(blocked_reason)) and listing_retired_at is not None \
                and paid_at >= listing_retired_at
            reason: str | None = None
            if suspended and not enabled:
                reason = "DISABLED"
            elif suspended:
                reason = "BLOCKED"
            elif not predrop.accepting_at(paid_at):
                reason = "CLOSED"
            elif predrop.in_priority_window(paid_at) and not priority_access:
                reason = "PRIORITY_WINDOW"
            elif q2(amount_paid_ttc) != expected:
                reason = "AMOUNT_MISMATCH"
            else:
                already = sum(r.qty for r in self._committed_reservations(predrop_id) if r.customer_ref == customer_ref)
                if already + qty > predrop.per_customer_limit:
                    reason = "CUSTOMER_LIMIT"
                elif self._quota_locked(predrop, at=paid_at).predrop_remaining < qty:
                    reason = "QUOTA_EXHAUSTED"
            reservation = PredropReservation(
                order_id=order_id, predrop_id=predrop_id, product_key=predrop.product_key, customer_ref=customer_ref,
                qty=qty, amount_paid_ttc=q2(amount_paid_ttc), shipping_paid_ttc=q2(shipping_paid_ttc),
                expected_ttc=expected, paid_at=paid_at, priority_access=priority_access,
                seq=len(self._reservations) + 1, status="CONFIRMED" if reason is None else "NOT_SERVED",
                not_served_reason=reason, recorded_by=recorded_by, recorded_at=at,
            )  # fmt: skip
            refund = None
            if reason is not None:
                refund = self._new_refund(reservation, reason, at=at, by="moteur", autonomy_level=autonomy_level)
            self._commit({
                "op": "reservation",
                "reservation": reservation.model_dump(mode="json"),
                "refund": None if refund is None else refund.model_dump(mode="json"),
            })  # fmt: skip
            return reservation, refund, True

    def cancel_reservation(
        self,
        order_id: str,
        *,
        reason: str,
        request_ref: str,
        by: str,
        at: datetime,
        today: date,
        autonomy_level: int,
        shipped: ShippedCheck = _no_shipment,
    ) -> tuple[PreparedRefund, bool]:
        """Annulation d'une réservation **confirmée**, à la demande écrite du client : remboursement **intégral** préparé.

        Motifs (:data:`CANCELLATION_REASONS_FR`) : ``CUSTOMER_CANCELLATION`` (annulation libre jusqu'à N jours avant la
        date du drop **en vigueur**, :attr:`Predrop.free_cancellation_until`, paramètre signé ; ensuite : retour
        volontaire des CGV après réception), ``DATE_POSTPONED`` (report au-delà du seuil des conditions),
        ``PRODUCT_CHANGED`` (contenu modifié). Même circuit que les autres remboursements : validation de la propriétaire
        en un clic aux niveaux 1 et 2, exécution relevée par le workflow 02 ; l'unité revient au quota (pré-drop encore
        ouvert) ou au drop. Déjà remboursée ou en cours de remboursement : sans effet (``(remboursement, False)``, jamais
        deux remboursements). Ligne de réservation expédiée : refus (retour volontaire après réception) — l'expédition
        d'un autre article de la même commande ne compte pas.
        """
        _aware(at, "at")
        if reason not in CANCELLATION_REASONS_FR:
            raise PredropError(f"motif d'annulation inconnu : {reason} ({', '.join(sorted(CANCELLATION_REASONS_FR))})")
        with self._lock:
            res = self._reservations.get(order_id)
            if res is None:
                raise PredropError(f"réservation {order_id} inconnue")
            existing = self._refunds.get(refund_id_for(order_id))
            if existing is not None:
                return existing, False
            if shipped(res):
                raise PredropError(
                    f"réservation {order_id} déjà expédiée : plus d'annulation, retour volontaire après réception (CGV ch. 10)"
                )
            if res.status != "CONFIRMED":  # pragma: no cover - une réservation non servie a toujours son remboursement
                raise PredropError(f"réservation {order_id} non servie : remboursement déjà préparé")
            predrop = self._predrops.get(res.predrop_id)
            if reason == "CUSTOMER_CANCELLATION" and predrop is not None and today > predrop.free_cancellation_until:
                raise PredropError(
                    f"annulation libre close le {predrop.free_cancellation_until.isoformat()} ({predrop.free_cancellation_days} "
                    f"jour(s) avant la date du drop {predrop.drop_date.isoformat()}) : après réception, retour volontaire "
                    "(CGV ch. 10) ; report ou contenu modifié : motif DATE_POSTPONED ou PRODUCT_CHANGED"
                )
            refund = self._new_refund(res, reason, at=at, by=by, autonomy_level=autonomy_level, request_ref=request_ref)
            self._commit({"op": "refund", "refund": refund.model_dump(mode="json")})
            return refund, True

    def postpone(
        self, predrop_id: str, *, new_date: date, new_closes_at: datetime, reason: str, supplier_ref: str, by: str,
        at: datetime,
    ) -> Predrop:
        """Report de la date du drop (revue pré-drop PDL-06) : journalisé, SKU de réservation **stable**.

        Seulement vers une date **postérieure** à la date en vigueur (avancer le drop raccourcirait l'annulation libre
        promise) ; ``new_closes_at`` : fermeture des réservations recalculée par l'appelant (début du nouveau jour du
        drop, ou fermeture antérieure inchangée). Les délais d'annulation suivent la nouvelle date. Pré-drop en attente
        de la propriétaire : refus (la date se corrige en le rouvrant).
        """
        _aware(at, "at")
        _aware(new_closes_at, "new_closes_at")
        with self._lock:
            predrop = self._predrops.get(predrop_id)
            if predrop is None:
                raise PredropError(f"pré-drop {predrop_id} inconnu")
            if predrop.status == "PENDING_OWNER":
                raise PredropError(f"pré-drop {predrop_id} en attente de la propriétaire : rien à reporter")
            if new_date <= predrop.drop_date:
                raise PredropError(
                    f"report : nouvelle date {new_date.isoformat()} ≤ date en vigueur {predrop.drop_date.isoformat()} "
                    "(un drop n'est jamais avancé)"
                )
            entry = PredropPostponement(previous_date=predrop.drop_date, new_date=new_date, reason=reason,
                                        supplier_ref=supplier_ref, by=by, at=at)  # fmt: skip
            updated = predrop.model_copy(update={
                "reservation_sku": predrop.sku,  # figé avant tout changement de date (lignes déjà vendues)
                "drop_date": new_date,
                "closes_at": new_closes_at,
                "postponements": (*predrop.postponements, entry),
            })  # fmt: skip
            updated = Predrop.model_validate(updated.model_dump(mode="json"))
            self._commit({"op": "predrop", "predrop": updated.model_dump(mode="json")})
            return updated

    # -- remboursements ---------------------------------------------------------------
    def refund(self, refund_id: str) -> PreparedRefund | None:
        """Remboursement préparé (None si inconnu)."""
        with self._lock:
            return self._refunds.get(refund_id)

    def refunds(self, status: str | None = None) -> tuple[PreparedRefund, ...]:
        """Remboursements préparés (filtrés par statut), par date de préparation."""
        with self._lock:
            items = sorted(self._refunds.values(), key=lambda r: (r.prepared_at, r.refund_id))
        return tuple(r for r in items if status is None or r.status == status)

    def approve_refund(self, refund_id: str, *, by: str, at: datetime) -> tuple[PreparedRefund, bool]:
        """Validation de la propriétaire en un clic (``PENDING_OWNER`` → ``APPROVED``) ; déjà approuvé : sans effet."""
        with self._lock:
            refund = self._refunds.get(refund_id)
            if refund is None:
                raise PredropError(f"remboursement {refund_id} inconnu")
            if refund.status != "PENDING_OWNER":
                return refund, False
            approved = refund.model_copy(update={"status": "APPROVED", "approved_by": by, "approved_at": at})
            self._commit({"op": "refund", "refund": approved.model_dump(mode="json")})
            return approved, True

    def mark_refund_executed(
        self, refund_id: str, *, by: str, at: datetime, executed_at: datetime, psp_refund_ref: str
    ) -> tuple[PreparedRefund, bool]:
        """Remboursement exécuté (relevé du PSP par le workflow 02) : seule sortie de la dette d'un remboursement.

        Exige ``APPROVED`` (validation de la propriétaire ou niveau d'autonomie suffisant) : en attente => refus.
        Même référence PSP rejouée : sans effet ; autre référence : refus.
        """
        _aware(executed_at, "executed_at")
        with self._lock:
            refund = self._refunds.get(refund_id)
            if refund is None:
                raise PredropError(f"remboursement {refund_id} inconnu")
            if refund.status == "EXECUTED":
                if refund.psp_refund_ref == psp_refund_ref:
                    return refund, False
                raise PredropError(f"remboursement {refund_id} déjà exécuté ({refund.psp_refund_ref})")
            if refund.status != "APPROVED":
                raise PredropError(
                    f"remboursement {refund_id} en attente de la validation de la propriétaire "
                    "(POST /predrop/refunds/{refund_id}/approve) : exécution refusée"
                )
            if executed_at < refund.prepared_at - FUTURE_SKEW or executed_at - at > FUTURE_SKEW:
                raise PredropError("date d'exécution antérieure à la préparation ou datée du futur")
            done = refund.model_copy(update={"status": "EXECUTED", "executed_by": by, "executed_at": executed_at,
                                             "psp_refund_ref": psp_refund_ref})  # fmt: skip
            self._commit({"op": "refund", "refund": done.model_dump(mode="json")})
            return done, True

    # -- dette ------------------------------------------------------------------------
    def reservation_state(self, order_id: str, shipped: ShippedCheck) -> str:
        """État dérivé : ``REFUNDED``, ``REFUND_PENDING``, ``SHIPPED``, ``CONFIRMED`` ou ``NOT_SERVED``.

        Un remboursement préparé prime toujours (non exécuté : ``REFUND_PENDING``, la dette reste due) ; ``SHIPPED``
        seulement si la **ligne** de la réservation est partie.
        """
        with self._lock:
            res = self._reservations[order_id]
            refund = self._refunds.get(refund_id_for(order_id))
        if refund is not None:
            return "REFUNDED" if refund.status == "EXECUTED" else "REFUND_PENDING"
        if res.status == "CONFIRMED" and shipped(res):
            return "SHIPPED"
        return res.status

    def outstanding_debt(self, *, as_of: datetime, shipped: ShippedCheck) -> PredropDebt:
        """Argent encaissé (payé au plus tard à ``as_of``) ni livré, ni remboursé (exécuté au plus tard à ``as_of``).

        Dérivé du registre (jamais déclaré) : chaque réservation payée, servie ou non, est une dette jusqu'à
        l'expédition de **sa ligne** (chiffre d'affaires reconnu) ou à son remboursement exécuté. Une réservation non
        servie ou dont le remboursement est préparé reste une dette jusqu'à l'exécution du remboursement, même si sa
        commande a été expédiée (autre article) — fermé par défaut.
        """
        _aware(as_of, "as_of")
        total = ZERO
        count = 0
        by_predrop: dict[str, Decimal] = {}
        with self._lock:
            items = list(self._reservations.values())
            refunds = dict(self._refunds)
        for res in items:
            if res.paid_at > as_of:
                continue
            refund = refunds.get(refund_id_for(res.order_id))
            if refund is not None:
                if refund.status == "EXECUTED" and refund.executed_at is not None and refund.executed_at <= as_of:
                    continue
                amount = max(res.debt_amount, refund.amount_ttc)
            elif res.status == "CONFIRMED" and shipped(res):
                continue
            else:
                amount = res.debt_amount
            total += amount
            count += 1
            by_predrop[res.predrop_id] = by_predrop.get(res.predrop_id, ZERO) + amount
        return PredropDebt(total_chf=q2(total), reservations=count,
                           by_predrop={k: q2(v) for k, v in sorted(by_predrop.items())})  # fmt: skip


# ------------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m pokeshop.predrop fingerprint [chemin]`` : empreinte à reporter au coffre, état de signature."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pokeshop.predrop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fp = sub.add_parser("fingerprint", help="empreinte à recopier dans le coffre (POKESHOP_PREDROP_FINGERPRINT)")
    fp.add_argument("path", nargs="?", default=None)
    args = parser.parse_args(argv)
    status = load_predrop_config(args.path)
    if not status.fingerprint:
        print(f"paramètres invalides : {status.reason}")
        return 1
    print(f"empreinte   : {status.fingerprint}")
    print(f"signature   : {status.signature} ({status.reason})")
    if status.signature == "INVALID":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

