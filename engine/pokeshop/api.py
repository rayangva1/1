"""API HTTP interne du moteur (FastAPI), appelée par n8n et le tableau de bord (agent integrations).

* **Authentification et autorisation (revue R3, SEC-16)** : matrice versionnée, **refus par défaut**
  (``pokeshop.authz.ROUTE_MATRIX``, table ``docs/08-agents/MATRICE_API.md``), appliquée par une
  dépendance d'application à **chaque** route, y compris celles ajoutées plus tard : une route absente
  de la matrice répond 403 (``authz.route_refused``). ``X-Pokeshop-Token`` porte le jeton commun
  (``POKESHOP_API_TOKEN_SHA256``, acteur « api » : lecture et aperçus en simulation **seulement**,
  toute écriture 403) ou le jeton d'un **rôle** (``POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>`` ou
  ``POKESHOP_AGENT_TOKENS_SHA256``) dont le nom **devient l'acteur** (un champ ``actor``/``requested_by``
  déclaré est ignoré ou refusé s'il diffère). Chaque écriture n'est admise que pour les rôles listés ;
  ``X-Pokeshop-Owner-Token`` valide (distinct du jeton d'API) admet la propriétaire, seule sur les
  actes réservés (réarmement, point zéro, mémoire des apports, apports, taux, approbations de prix,
  validations de fiches ``/catalog/approvals``). Sans empreinte configurée : 503 ; tout refus est
  journalisé. ``/docs`` et ``/openapi.json`` sont fermés.
* **Valeurs décisives jamais auto-déclarées** : ``/mandate/check`` ignore toute trésorerie du corps
  et lit les registres du moteur (photo stop-loss acceptée, solde PayPal relevé, taux de référence,
  propositions de réassort enregistrées) ; une photo déposée par le jeton qui demande la dépense
  n'est pas vérifiable (``TREASURY_UNVERIFIED`` => validation humaine). Séparation des rôles :
  dépense pub = MAX(déclaration de ``connecteur-publicite``, paiements pub engagés du mandat) ; coût
  historique adossé à une réception d'un autre jeton et borné par une référence du moteur ; ventes et
  avoirs de l'étoile polaire dérivés des commandes enregistrées (``/orders/shipped``, coût transporteur réel) ; un test de
  correction **réussi** d'incident : ``qa-conformite`` (≠ ouvreur, cycle réel lancé par un autre
  principal) ou la propriétaire ; validations humaines des fiches : propriétaire seule.
  ``/stoploss/state`` remplace plafond jour pub et budget stock de la photo par ceux du mandat
  signé et des règles, et **refuse tout mouvement de capital** (422) : apports et retraits viennent
  uniquement du registre de la propriétaire (``POST /capital/movements``). ``/northstar/entries``
  refuse tout coût historique (registre interne ``/costs/movements`` uniquement) ; un lot est atomique.
* **Revue R4** : jeton propriétaire **suffisant seul** (R3-DOC-01) ; clé produit unique ``product_id`` =
  ``listing.product_key`` (R3-NEW-01) ; photo déposée ``/stoploss/state`` : propriétaire seule, cash recoupé
  avec les relevés du connecteur (R3-NEW-03) ; créances : propriétaire seule, dettes : plancher des factures
  enregistrées non payées (R3-NEW-02, ``POST /costs/invoices``) ; coût unitaire d'une réception à ± 2 % d'une
  référence du moteur (R2-NEW-01) ; paiements pub **engagés** dans le stop-loss pub (R2-NEW-03) ; identifiants
  ``order:``/``refund:``/``cost:`` réservés, commande atomique avec lignes et sortie au CMP dérivée
  (R3-NEW-04/05) ; frais PSP d'une commande comptés une fois (R3-DOC-03) ; relais 08 limité aux agents qui
  dépensent (R3-NEW-06) ; « simulation » d'un incident admis seulement moteur en simulation (R3-DOC-04).
* **Revue R5** : référence du coût d'une réception jamais nourrie par son bénéficiaire (R2-NEW-01 / R3-DOC-02 /
  R4-DOC-09) — facture enregistrée prioritaire (quantités reçues ≤ quantité facturée, lignes ≤ montant dû,
  fournisseur lié), sinon offre évaluée avec des frais posés par la propriétaire ; cycle avec catalogue ou frais du
  corps : aucun coût de remplacement inscrit ; réception valorisée une fois sur (SKU à la réception, bon) ; TVA
  d'import des lignes comptée selon le profil TVA du moteur (R4-DOC-02) ; retour en stock au coût : lignes de l'avoir
  + retour physique déclaré (R3-NEW-05) ; commande payée jamais refusée faute de coût (coût des ventes en attente,
  dépenses en validation humaine) et lot pub jamais refusé pour une commande attribuée inconnue (R4-NEW-01) ; dettes
  et créances en deux registres persistés (R4-NEW-02, R4-DOC-01, R3-NEW-02) ; ``POST /mandate/human-decision``
  (propriétaire, R4-DOC-03) ; ``finance-pricing`` ne demande jamais de dépense (R4-DOC-11).
* **Taux de change** : uniquement le registre de la propriétaire (``POST /fx/rates``) ; aucun champ
  ``fx_*`` accepté dans ``/sync/run`` ni ``/catalog/cost-inputs`` (422) ; sans taux : coût incomplet,
  fiche en brouillon. ``/mandate/check`` ne retient jamais le taux déclaré (contrôle à ± 1 % contre la
  référence ; sans référence : ``FX_RATE_UNVERIFIED``, validation humaine).
* **Seuils signés** (revue R6, R5C-DOC-09 : comportement propre à chaque empreinte, toujours fermé) :
  - mandat (``POKESHOP_MANDATE_FINGERPRINT``) différent du fichier => **mandat inactif**
    (``MANDATE_FINGERPRINT_MISMATCH``) : aucune dépense approuvée sans vous, aucun gel ;
  - seuils du stop-loss (``POKESHOP_STOPLOSS_FINGERPRINT``) différents => **stop-loss non chargé** : routes du
    stop-loss en 503, écritures réelles refusées (``STOPLOSS_UNAVAILABLE``), ``/mandate/check`` en 503, aucune
    dépense ; pas de ``CONFIG_UNSIGNED`` (il n'y a pas de stop-loss à geler) ;
  - règles de prix (``POKESHOP_RULES_FINGERPRINT``) différentes, ou écart entre sources d'une même règle
    (``consistency_errors``) => valeurs les plus strictes et **service gelé** (``CONFIG_UNSIGNED``).
  Empreinte absente => seuils et règles les plus stricts entre fichier et référence du code ; mandat jamais actif.
* **Montants** : chaînes décimales en entrée (un nombre JSON à virgule est refusé : 422) et en
  sortie (``"209.90"``), CHF. Aucun ``float`` ne traverse l'API. NaN, Infinity, exposants
  extrêmes, montants > 10 000 000, coûts ou prix négatifs, remise > 100 % : 422 (jamais 500).
* **Prix approuvés** : aucune « validation humaine » de prix dans un corps de requête ; la
  propriétaire approuve un prix par ``POST /pricing/approvals`` (jeton propriétaire), le moteur
  relit son registre (jamais sous le plancher dur sans exception C18 référencée).
* **Imports** : ``/imports/{supplier}/run`` et ``/sync/run`` comparent chaque import à la
  référence « dernier import » persistée (×10, incomplet, devise, HT/TTC) ; ``/sync/run`` en
  écriture réelle sans référence => 409 (premier import en simulation).
* **Stock** : ``POST /stock/receive`` alimente le registre du stock local (persisté, idempotent par
  SKU + référence) ; le statut public publié est recalculé depuis ce registre.
* **Simulation par défaut** : ``/imports/{supplier}/run`` est toujours en simulation ;
  ``/sync/run`` l'est sauf ``"dry_run": false`` explicite, qui passe ensuite par la porte de
  gouvernance (niveau d'autonomie, stop-loss, mandat) et par ``POKESHOP_DRY_RUN=false``.
* Les réponses internes peuvent contenir des coûts (cotation, panier) ; ``/publish/preview`` ne
  renvoie que la charge publique filtrée. Lancement : ``uvicorn pokeshop.api:create_app --factory``.
* **Catalogue et cycles** (revue E2E-07) : ``/sync/run`` lit le catalogue validé et les frais du
  moteur (``POST /catalog/items``, ``POST /catalog/cost-inputs`` ; taux de la propriétaire) quand le
  corps n'en fournit pas ; aucun des deux : 409. ``clean`` n'est vrai que pour un cycle **PROPRE**
  (aucune erreur critique et au moins une offre au coût rendu calculé) ; ``GET /sync/history`` expose
  les cycles persistés et ``consecutive_clean_runs`` (critère de recette BP §13) qui ne compte que les
  cycles **réels** : données non FICTIVES, catalogue du registre, source datée, une fois par contenu.
* **Dépublication protectrice** (revue SEC-09) : après chaque écriture vérifiée, identifiant Shopify et
  statut sont inscrits (journal ``shop_publications``) ; une référence en quarantaine ou bloquée par le
  stop-loss produit est dépubliée (``{"status": "DRAFT"}``) même si la fiche du registre n'a pas
  d'identifiant ; inconnue du registre en écriture réelle : relue par handle sur la boutique.
* **Photo du stop-loss construite par le moteur** (revue E2E-08) : ``POST /stoploss/state/refresh``
  l'assemble à partir de ses registres — apports et retraits attestés par la propriétaire
  (``POST /capital/movements``, jeton propriétaire), soldes PayPal et banque relevés par des
  connecteurs (``/treasury/paypal-balance``, ``/treasury/bank-balance``), dettes et créances déclarées
  (``POST /treasury/balance-items``, jamais supposées nulles), stock au coût historique, catalogue,
  prix publics, publicité (``POST /ads/activity``) ; source manquante ou périmée : 409.
* **Suspensions** (revue E2E-10) : un incident ouvert sur la clé canonique ``mandat-depenses`` (ou une
  suspension de toutes les écritures hors gel du stop-loss) rend ``/mandate/check`` en 423.
  ``/health`` indique si les alertes d'incident partent réellement vers n8n (``notifications``).
* **États de sécurité persistés** (journaux d'état en ajout seul, :mod:`pokeshop.audit`) : verrou
  et journal du stop-loss (point zéro compris), dernière photo stop-loss **acceptée**, registre du
  mandat, étoile polaire, incidents et confinements, historique des prix, niveau d'autonomie,
  approbations de prix, références « dernier import », mouvements du stock local, catalogue de
  synchronisation et frais, cycles de synchronisation, apports de capital, activité publicitaire,
  fiches publiées (identifiant Shopify et statut), factures fournisseur, commandes, dettes et créances
  (``balance_statements``, revue R5).
  Base si ``POKESHOP_DATABASE_URL``, sinon fichiers JSON Lines dans ``POKESHOP_STATE_DIR``.
  :meth:`Services.build` les relit ; un journal illisible => service gelé (``RESTORE_FAILED``),
  mandat et étoile polaire en 503, jusqu'à réparation et redémarrage (fermé par défaut).
"""

from __future__ import annotations

import hmac
import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from . import __version__
from . import authz
from .audit import (
    ActorKind,
    AuditLog,
    FailedStateJournal,
    IdempotencyStore,
    InMemoryAuditLog,
    InMemoryIdempotencyStore,
    InMemoryStateJournal,
    JsonlStateJournal,
    PostgresAuditLog,
    PostgresIdempotencyStore,
    PostgresStateJournal,
    StateJournal,
    StateStoreError,
    to_jsonable,
)
from .autonomy import (
    ACTION_LABELS_FR,
    LEVEL_LABELS_FR,
    PROTECTIVE_ACTIONS,
    REQUIRED_LEVEL,
    AutonomyController,
    AutonomyError,
    AutonomyLevel,
    AutonomyRefusedError,
    AutonomyStore,
    GovernanceGate,
    InMemoryAutonomyStore,
    JsonFileAutonomyStore,
    PostgresAutonomyStore,
    verify_owner_token,
)
from .catalog import DEFAULT_EXTENSIONS_PATH, CatalogProduct, SupplierLink, load_extension_table
from .catalogue_sync import (
    ACCEPTANCE_DEFINITION,
    CLEAN_RUNS_TARGET,
    CatalogEntry,
    CatalogRegistry,
    SupplierCostEntry,
    SyncRegistryError,
    SyncRegistryPersistenceError,
    SyncRunLog,
    SyncRunSummary,
)
from .costs import PriceHistory
from .errors import PokeshopError
from .importers import ImporterError, MappingError, extension_table_for, load_mapping, run_import
from .invoices import InvoiceError, InvoiceLine, InvoicePayment, InvoicePersistenceError, SupplierInvoice, SupplierInvoiceBook
from .incidents import (
    IncidentCode,
    IncidentError,
    IncidentManager,
    IncidentPersistenceError,
    IncidentScope,
    IncidentStatus,
    LogNotifier,
    MultiNotifier,
    Notifier,
    PostgresIncidentSink,
    Severity,
    WebhookNotifier,
)
from .mandate import (
    EngineProposalBook,
    FxRate,
    FxRateBook,
    LedgerPersistenceError,
    Mandate,
    MandateError,
    MandateRevocations,
    PayPalBalanceReading,
    RegistryPersistenceError,
    SpendLedger,
    SpendRequest,
    TreasurySnapshot,
    check,
    load_mandate,
    treasury_from_registers,
)
from .models import BasketLine, Discount, PriceEvent, ReorderCandidate, ReplacementCost, VatMode, canonical_hash, explain
from .northstar import (
    ContributionEntry,
    CostMovement,
    CostRegister,
    NorthStarError,
    NorthStarLedger,
    NorthStarPersistenceError,
    OrderLine,
    OrderRefund,
    OrderRegister,
    ShippedOrder,
    is_unresolved_key,
    unresolved_key,
)
from .predrop import (
    Eligibility,
    FirmAllocation,
    DemandSignal,
    Predrop,
    PredropConfigStatus,
    PredropError,
    PredropPersistenceError,
    PredropRegistry,
    evaluate_eligibility,
    load_predrop_config,
    public_offer,
)
from .pricing import basket_contribution, decide_price
from .publish import (
    CatalogApprovalBook,
    CatalogApprovalPersistenceError,
    CatalogListing,
    ListingApproval,
    PriceApprovalBook,
    PriceApprovalPersistenceError,
    PriceValidation,
    SensitiveFieldError,
    build_publication,
    listing_digest,
    refuse_declared_listing_fields,
    stock_status_for,
)
from .rules import RuleSet, load_rules
from .settings import REPO_ROOT, Settings, SettingsError, is_owner_like, load_settings, sha256_hex
from .shopify_client import ShopifyAccessDeniedError, ShopifyClient, ShopifyError
from .stock import PersistentStockRegistry, StockPersistenceError, propose_reorder, sellable_local
from .stoploss import (
    AdSpend,
    AttributedOrder,
    BalanceItem,
    CapitalMovement,
    RearmReferenceMismatchError,
    RearmRefusedError,
    StopLossConfig,
    StopLossEngine,
    StopLossError,
    StopLossPersistenceError,
    StopLossState,
    consistency_errors,
    load_stoploss_config,
    net_worth,
    render_report,
    strictest_price_rules,
    with_authoritative_limits,
)
from .stoploss_snapshot import (
    ActivityRegisterError,
    ActivityRegisterPersistenceError,
    AdsActivityRegister,
    BalanceStatement,
    BalanceStatementBook,
    BankBalanceReading,
    CapitalRegister,
    PhotoSourcesError,
    ReceivablesStatement,
    build_activity_photo,
    committed_ad_payments,
    merge_ad_spends,
)
from .sync import (
    WORKFLOW_SUPPLIER_TO_SHOP,
    BaselinePersistenceError,
    ImportBaselineStore,
    OfferCostInputs,
    ShopPublicationBook,
    ShopStatePersistenceError,
    SyncContext,
    SyncError,
    SyncService,
)
from .treasury import CASH_STOPLOSS_RESERVE

__all__ = [
    "Services",
    "create_app",
    "API_TOKEN_HEADER",
    "OWNER_TOKEN_HEADER",
    "FICTIF_EXTENSIONS_PATH",
    "PHOTO_STREAM",
    "PersistentPriceHistory",
    "WORKFLOW_MANDATE",
    "WORKFLOW_KEYS",
]

API_TOKEN_HEADER = "X-Pokeshop-Token"
OWNER_TOKEN_HEADER = "X-Pokeshop-Owner-Token"
FICTIF_EXTENSIONS_PATH = REPO_ROOT / "data" / "samples" / "FICTIF_extensions_aliases.yaml"
_SUPPLIER_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
T = TypeVar("T", bound=BaseModel)
PHOTO_STREAM = "stoploss_photo"
"""Journal d'état des photos stop-loss **acceptées** (la dernière est relue au démarrage)."""
WORKFLOW_MANDATE = "mandat-depenses"
"""Clé canonique du workflow de dépense (n8n 08) : un incident ouvert sur elle suspend ``/mandate/check``."""
WORKFLOW_KEYS: dict[str, str] = {
    "01": WORKFLOW_SUPPLIER_TO_SHOP,
    "02": "commande-livraison",
    "03": "facture-marge",
    "04": "incident",
    "05": "digest",
    "06": "marketing",
    "07": "stoploss-watch",
    "08": WORKFLOW_MANDATE,
}
"""Clé canonique de chaque workflow n8n (nœud « Paramètres », incidents, suspensions) : une seule
clé par workflow, la même que celle du moteur (``fournisseur-site`` pour 01)."""


# ----------------------------------------------------------------------- erreurs HTTP


class HTTPProblem(Exception):
    """Erreur HTTP avec message français."""

    def __init__(self, status: int, message: str, **extra: Any) -> None:
        self.status = status
        self.message = message
        self.extra = extra
        super().__init__(message)


class PokeshopJSONResponse(JSONResponse):
    """JSON sans float : Decimal en chaîne, dates ISO, énumérations par valeur."""

    def render(self, content: Any) -> bytes:
        return json.dumps(to_jsonable(content), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _ok(content: Any, status: int = 200) -> PokeshopJSONResponse:
    return PokeshopJSONResponse(content=content, status_code=status)


def _reject_float(text: str) -> Any:
    raise ValueError(f'nombre décimal JSON interdit ({text}) : écrire le montant en chaîne, ex. "{text}"')


async def _body(request: Request, model: type[T]) -> T:
    """Corps JSON validé ; tout nombre à virgule est refusé (montants en chaîne)."""
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}", parse_float=_reject_float)
    except ValueError as exc:
        raise HTTPProblem(422, f"JSON invalide : {exc}") from None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise HTTPProblem(
            422, "requête invalide", details=to_jsonable(exc.errors(include_url=False, include_context=False))
        ) from None


MAX_MONEY = Decimal("10000000")
"""Plus grand montant admis en entrée (CHF) : au-delà, saisie aberrante (422)."""


def _strict_money(value: Any) -> Any:
    """Montant décimal **fini**, en chaîne ou entier, |montant| ≤ 10 000 000, au plus 6 décimales.

    Refus (422) : float, booléen, NaN, sNaN, ±Infinity, exposants extrêmes (``1e999999``).
    """
    if isinstance(value, (bool, float)):
        raise ValueError("montant en chaîne ou entier (jamais de float)")
    if isinstance(value, (int, str)):
        try:
            value = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"montant invalide : {value!r}") from exc
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("montant non fini (NaN, Infinity) refusé")
        exponent = value.as_tuple().exponent
        # ``adjusted()`` d'abord : aucune opération contextuelle sur un exposant extrême (1E+400000000).
        if value.adjusted() > MAX_MONEY.adjusted() or value.copy_abs() > MAX_MONEY:
            raise ValueError(f"montant hors bornes (|montant| > {MAX_MONEY})")
        if isinstance(exponent, int) and exponent < -6:
            raise ValueError("montant : 6 décimales au plus")
    return value


Money = Annotated[Decimal, BeforeValidator(_strict_money)]
PositiveMoney = Annotated[Decimal, BeforeValidator(_strict_money), Field(gt=0)]
NonNegativeMoney = Annotated[Decimal, BeforeValidator(_strict_money), Field(ge=0)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ------------------------------------------------------------------- persistance


class PersistentPriceHistory(PriceHistory):
    """Historique des prix publics dont chaque événement est écrit dans le journal d'état ``price_history``.

    La référence à 24 h du plafond de variation de 5 %/jour (:func:`pokeshop.sync.price_reference_24h`)
    et le dernier prix validé survivent ainsi au redémarrage. Écriture refusée => l'opération est
    annulée en mémoire et :class:`StateStoreError` est levée.
    """

    STREAM = "price_history"

    def __init__(self, store: StateJournal | None = None) -> None:
        super().__init__()
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> PersistentPriceHistory:
        """Relit événements et piles de prix (StateStoreError si illisible ou incohérent)."""
        records = store.load()
        history = cls()
        for n, record in enumerate(records, start=1):
            try:
                event = PriceEvent.model_validate(record["event"])
                stack = [(Decimal(str(price)), bool(ok)) for price, ok in record["stack"]]
            except (KeyError, TypeError, ValueError, ArithmeticError, ValidationError) as exc:
                raise StateStoreError(f"historique des prix : enregistrement {n} illisible") from exc
            if event.seq != len(history._events) + 1:
                raise StateStoreError(f"historique des prix : séquence rompue à l'enregistrement {n}")
            history._events.append(event)
            history._stacks[event.product_key] = stack
        history._store = store
        return history

    def _append(self, product_key: str, kind: Any, price: Decimal | None, at: datetime, actor: str, **kw: Any) -> Any:
        event = super()._append(product_key, kind, price, at, actor, **kw)
        if self._store is not None:
            stack = [[str(p), ok] for p, ok in self._stacks.get(product_key, [])]
            self._store.append({"event": event.model_dump(mode="json"), "stack": stack})
        return event

    def _guarded(self, product_key: str, call: Callable[[], Any]) -> Any:
        with self._lock:
            had = product_key in self._stacks
            before = list(self._stacks.get(product_key, []))
            count = len(self._events)
            try:
                return call()
            except StateStoreError:
                del self._events[count:]
                if had:
                    self._stacks[product_key] = before
                else:
                    self._stacks.pop(product_key, None)
                raise

    def record_decision(self, product_key: str, *args: Any, **kwargs: Any) -> Any:
        """Voir :meth:`PriceHistory.record_decision` (persisté)."""
        base = super().record_decision
        return self._guarded(product_key, lambda: base(product_key, *args, **kwargs))

    def publish(self, product_key: str, *args: Any, **kwargs: Any) -> Any:
        """Voir :meth:`PriceHistory.publish` (persisté)."""
        base = super().publish
        return self._guarded(product_key, lambda: base(product_key, *args, **kwargs))

    def validate(self, product_key: str, *args: Any, **kwargs: Any) -> Any:
        """Voir :meth:`PriceHistory.validate` (persisté)."""
        base = super().validate
        return self._guarded(product_key, lambda: base(product_key, *args, **kwargs))

    def rollback(self, product_key: str, *args: Any, **kwargs: Any) -> Any:
        """Voir :meth:`PriceHistory.rollback` (persisté)."""
        base = super().rollback
        return self._guarded(product_key, lambda: base(product_key, *args, **kwargs))


def guard_rules(rules: RuleSet, expected_sha256: str | None) -> tuple[RuleSet, str, tuple[str, ...]]:
    """Règles de prix : signées (empreinte du fichier = coffre) ou ramenées aux valeurs les plus strictes.

    Renvoie (règles appliquées, état ``SIGNED`` / ``UNSIGNED_STRICTEST`` / ``TAMPERED``, valeurs durcies).
    Un fichier modifié après signature (``TAMPERED``) est lui aussi ramené au plus strict, et le
    service est gelé par l'appelant.
    """
    if expected_sha256 is not None and hmac.compare_digest(rules.content_sha256, expected_sha256):
        return rules, "SIGNED", ()
    pricing, stock, tightened = strictest_price_rules(rules.pricing, rules.stock)
    if pricing.small_product_min_order_ttc is not None or pricing.small_product_max_shipping_ttc is not None:
        # Règle petits produits (frais par commande exclus) : jamais activée par un fichier non signé.
        pricing = pricing.replace(small_product_min_order_ttc=None, small_product_max_shipping_ttc=None)
        tightened = (*tightened, "pricing.small_product_min_order_ttc", "pricing.small_product_max_shipping_ttc")
    state = "TAMPERED" if expected_sha256 is not None else "UNSIGNED_STRICTEST"
    return rules.replace(pricing=pricing, stock=stock), state, tightened


@dataclass(frozen=True)
class Principal:
    """Appelant authentifié : jeton commun (« api », non attribuable), jeton nommé (nom = rôle de la matrice
    :mod:`pokeshop.authz`) ou propriétaire (jeton propriétaire vérifié, acteur « propriétaire »)."""

    name: str
    named: bool
    owner: bool = False

    @property
    def role(self) -> str | None:
        """Rôle de la matrice (None pour le jeton commun ; ``propriétaire`` pour la propriétaire)."""
        return self.name if self.named else None


def _journal_opener(cfg: Settings, factory: Callable[[], Any] | None) -> Callable[[str], StateJournal]:
    """Journal d'état par flux : base si configurée, sinon fichier JSON Lines, sinon mémoire (``:memory:``)."""
    if factory is not None:
        return lambda stream: PostgresStateJournal(factory, stream)
    if cfg.state_dir is not None:
        base = cfg.state_dir
        return lambda stream: JsonlStateJournal(base / f"{stream}.jsonl", stream=stream)
    return InMemoryStateJournal


# --------------------------------------------------------------------------- services


@dataclass
class Services:
    """Dépendances du service (construites depuis :class:`Settings`, remplaçables en test)."""

    settings: Settings
    clock: Callable[[], datetime]
    audit: AuditLog
    idempotency: IdempotencyStore
    autonomy: AutonomyController
    incidents: IncidentManager
    rules: RuleSet
    stoploss_config: StopLossConfig | None
    stoploss_engine: StopLossEngine | None
    mandate: Mandate | None
    spend_ledger: SpendLedger
    northstar: NorthStarLedger
    stock: PersistentStockRegistry
    price_history: PriceHistory
    client: ShopifyClient
    gate: GovernanceGate
    sync: SyncService
    load_errors: dict[str, str] = field(default_factory=dict)
    stoploss_state: StopLossState | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    photo_journal: StateJournal = field(default_factory=lambda: InMemoryStateJournal(PHOTO_STREAM))
    restore_errors: dict[str, str] = field(default_factory=dict)
    """Journaux d'état non relus au démarrage (flux -> motif) : service gelé tant qu'il n'est pas vide."""
    state_backend: str = "memoire"
    """Stockage des états de sécurité : ``postgres``, ``fichier`` ou ``memoire``."""
    fx_rates: FxRateBook = field(default_factory=FxRateBook)
    proposals: EngineProposalBook = field(default_factory=EngineProposalBook)
    revocations: MandateRevocations = field(default_factory=MandateRevocations)
    costs: CostRegister = field(default_factory=CostRegister)
    paypal_balance: PayPalBalanceReading | None = None
    """Dernier solde PayPal relevé (mémoire : à relever de nouveau après redémarrage, fermé par défaut)."""
    photo_poster: str | None = None
    """Acteur (déduit du jeton) qui a déposé la photo stop-loss en vigueur (None = inconnu)."""
    signatures: dict[str, str] = field(default_factory=dict)
    """État de signature des configurations (mandat, stop-loss, règles)."""
    price_approvals: PriceApprovalBook = field(default_factory=PriceApprovalBook)
    """Approbations de prix de la propriétaire (journal ``price_approvals``)."""
    baselines: ImportBaselineStore = field(default_factory=ImportBaselineStore)
    """Références « dernier import » par fournisseur (journal ``import_baselines``)."""
    catalog: CatalogRegistry = field(default_factory=CatalogRegistry)
    """Catalogue validé et frais connus lus par ``/sync/run`` (journaux ``sync_catalog``, ``sync_cost_inputs``)."""
    sync_runs: SyncRunLog = field(default_factory=SyncRunLog)
    """Résumés des cycles de synchronisation et compteur de cycles propres (journal ``sync_runs``)."""
    capital: CapitalRegister = field(default_factory=CapitalRegister)
    """Apports et retraits attestés par la propriétaire (journal ``capital_movements``)."""
    ads: AdsActivityRegister = field(default_factory=AdsActivityRegister)
    """Dépenses publicitaires et commandes attribuées (journal ``ads_activity``)."""
    bank_balance: BankBalanceReading | None = None
    """Dernier solde bancaire relevé (mémoire : à relever de nouveau après redémarrage, fermé par défaut)."""
    publications: ShopPublicationBook = field(default_factory=ShopPublicationBook)
    """Fiches écrites et vérifiées sur la boutique (journal ``shop_publications``) : dépublication protectrice."""
    balances: BalanceStatementBook = field(default_factory=BalanceStatementBook)
    """Déclaration des dettes et relevé des créances de la propriétaire, **séparés et persistés** (journal
    ``balance_statements``, revue R5 : R3-NEW-02 partiel, R4-NEW-02, R4-DOC-01) ; jamais supposés nuls."""
    catalog_approvals: CatalogApprovalBook = field(default_factory=CatalogApprovalBook)
    """Validations de fiches de la propriétaire (journal ``catalog_approvals``) : seule source de
    ``approved``, ``content_validated`` et ``category_rule_validated`` (revue R3, R2-NEW-05)."""
    orders: OrderRegister = field(default_factory=OrderRegister)
    """Commandes expédiées et avoirs (journal ``orders``) : seule source des ventes de l'étoile polaire."""
    invoices: SupplierInvoiceBook = field(default_factory=SupplierInvoiceBook)
    """Factures fournisseur enregistrées et paiements (journal ``supplier_invoices``, revue R4) : référence du coût
    d'une réception et plancher des dettes de la photo du stop-loss."""
    predrop: PredropRegistry = field(default_factory=PredropRegistry)
    """Pré-drop (journal ``predrop``) : allocations fermes, demande agrégée, pré-drops, réservations payées,
    remboursements préparés ; argent encaissé = dette dérivée de la photo du stop-loss jusqu'à l'expédition."""
    predrop_config: PredropConfigStatus = field(
        default_factory=lambda: PredropConfigStatus(enabled=False, signature="UNSIGNED", reason="non chargé")
    )
    """Paramètres du pré-drop : activé seulement s'ils sont signés (``POKESHOP_PREDROP_FINGERPRINT``)."""

    @property
    def balance_statement(self) -> BalanceStatement | None:
        """Déclaration des dettes et précommandes en vigueur (lecture ; écriture : :attr:`balances`)."""
        return self.balances.debts

    def authoritative_photo(self, state: StopLossState, now: datetime) -> tuple[StopLossState, list[str]]:
        """Photo avec plafond pub et budget stock du moteur (mandat signé actif, règles), jamais ceux postés."""
        mandate = self.mandate
        active = mandate is not None and mandate.is_active(now)
        ads_cap = mandate.ads_daily_cap_chf if active and mandate is not None else None
        budget = self.rules.stock.stock_budget_chf
        if active and mandate is not None and mandate.stock_budget_chf is not None:
            budget = min(budget, mandate.stock_budget_chf)
        return with_authoritative_limits(state, ads_daily_cap_chf=ads_cap, stock_budget_chf=budget)

    @classmethod
    def build(
        cls,
        settings: Settings | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        shopify_transport: httpx.BaseTransport | None = None,
        notifier: Notifier | None = None,
        connect: Callable[[], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> Services:
        """Assemble les composants ; Postgres si ``POKESHOP_DATABASE_URL`` (ou ``connect``) est fourni.

        Relit chaque journal d'état ; un journal illisible gèle le service (``RESTORE_FAILED``) et,
        pour les incidents, suspend toutes les écritures : réparer le stockage puis redémarrer.
        """
        cfg = settings or load_settings()
        now = clock or (lambda: datetime.now(UTC))
        errors: dict[str, str] = {}
        restore_errors: dict[str, str] = {}
        factory = connect
        if factory is None and cfg.database_url is not None:
            try:
                import psycopg
            except ImportError as exc:  # pragma: no cover - dépend de l'image
                raise SettingsError("POKESHOP_DATABASE_URL fourni mais pilote psycopg absent") from exc
            url = cfg.database_url.get_secret_value()

            def factory() -> Any:
                return psycopg.connect(url)

        audit: AuditLog = PostgresAuditLog(factory) if factory else InMemoryAuditLog(clock=now)
        idempotency: IdempotencyStore = PostgresIdempotencyStore(factory) if factory else InMemoryIdempotencyStore()
        journal_for = _journal_opener(cfg, factory)

        def failed(stream: str, exc: Exception) -> FailedStateJournal:
            restore_errors[stream] = str(exc) or type(exc).__name__
            return FailedStateJournal(stream, restore_errors[stream])

        store: AutonomyStore
        if factory:
            store = PostgresAutonomyStore(factory)
        elif cfg.autonomy_state_path is not None:
            store = JsonFileAutonomyStore(cfg.autonomy_state_path)
        elif cfg.state_dir is not None:
            store = JsonFileAutonomyStore(cfg.state_dir / "autonomy.jsonl")
        else:
            store = InMemoryAutonomyStore()
        default_level = cfg.autonomy_level
        try:
            store.current("global")
        except Exception as exc:  # noqa: BLE001 - historique illisible : niveau 1 en mémoire, service gelé
            restore_errors["autonomy"] = f"{type(exc).__name__}: {exc}"
            store, default_level = InMemoryAutonomyStore(), 1
        autonomy = AutonomyController(
            store,
            audit=audit,
            owner_token_sha256=cfg.owner_token_sha256 or "",
            default_level=default_level,
            clock=now,
        )
        channels: list[Notifier] = [notifier or LogNotifier()]
        if cfg.n8n_webhook_url:
            secret = cfg.n8n_webhook_secret.get_secret_value() if cfg.n8n_webhook_secret is not None else None
            channels.append(WebhookNotifier(cfg.n8n_webhook_url, dry_run=cfg.notify_dry_run, secret=secret))
        notify = MultiNotifier(channels) if len(channels) > 1 else channels[0]
        sink = PostgresIncidentSink(factory) if factory else None
        incidents = IncidentManager(
            audit=audit,
            notifier=notify,
            on_critical=autonomy.on_critical_incident,
            sink=sink,
            clock=now,
            store=journal_for(IncidentManager.STREAM),
        )
        try:
            incidents.restore()
        except IncidentPersistenceError as exc:
            incidents = IncidentManager(
                audit=audit,
                notifier=notify,
                on_critical=autonomy.on_critical_incident,
                sink=sink,
                clock=now,
                store=failed(IncidentManager.STREAM, exc),
            )
        signatures: dict[str, str] = {}
        config_holds: list[str] = []
        rules, signatures["rules"], _ = guard_rules(load_rules(cfg.rules_path, cfg.vat_profile), cfg.rules_fingerprint)
        if signatures["rules"] == "TAMPERED":
            errors["rules"] = "règles de prix modifiées sans signature (empreinte ≠ coffre) : valeurs les plus strictes, service gelé"
            config_holds.append("règles de prix modifiées sans signature")
        config: StopLossConfig | None = None
        engine: StopLossEngine | None = None
        try:
            config = load_stoploss_config(cfg.stoploss_path, expected_fingerprint=cfg.stoploss_fingerprint)
            signatures["stoploss"] = config.signature
        except PokeshopError as exc:
            errors["stoploss"] = str(exc)
            signatures["stoploss"] = "REFUSED"
        if config is not None:
            owner_hash = cfg.owner_token_sha256 or None
            try:
                engine = StopLossEngine.restore(
                    config, store=journal_for(StopLossEngine.STREAM), owner_token_sha256=owner_hash
                )
            except StopLossPersistenceError as exc:
                engine = StopLossEngine(
                    config, owner_token_sha256=owner_hash, store=failed(StopLossEngine.STREAM, exc)
                )
            except PokeshopError as exc:  # empreinte propriétaire invalide : stop-loss indisponible (fermé)
                errors["stoploss"] = str(exc)
        photo_journal = journal_for(PHOTO_STREAM)
        photo: StopLossState | None = None
        photo_poster: str | None = None
        try:
            records = photo_journal.load()
            if records:
                photo = StopLossState.model_validate(records[-1]["state"])
                poster = records[-1].get("posted_by")
                photo_poster = poster if isinstance(poster, str) else None
        except (StateStoreError, KeyError, TypeError, AttributeError, ValidationError) as exc:
            photo_journal = failed(PHOTO_STREAM, exc)
        mandate: Mandate | None = None
        try:
            mandate = load_mandate(cfg.mandate_path, expected_fingerprint=cfg.mandate_fingerprint)
        except PokeshopError as exc:
            errors["mandate"] = str(exc)
        try:
            revocations = MandateRevocations.restore(journal_for(MandateRevocations.STREAM))
        except RegistryPersistenceError as exc:
            revocations = MandateRevocations(store=failed(MandateRevocations.STREAM, exc))
        if mandate is not None:
            revoked_at = mandate.approval.revoked_at
            if revoked_at is not None and revoked_at <= now() and MandateRevocations.STREAM not in restore_errors:
                try:  # révocation inscrite au YAML : rendue définitive (registre en ajout seul)
                    revocations.revoke(
                        mandate.fingerprint, at=revoked_at, actor="mandat (approval.revoked_at)",
                        reason="révocation inscrite dans le mandat",
                    )  # fmt: skip
                except RegistryPersistenceError as exc:
                    errors["mandate_revocation"] = str(exc)
            mandate = mandate.with_revocations(revocations.fingerprints())
            signatures["mandate"] = (
                "SIGNED" if mandate.is_signed else "VAULT_MISSING" if mandate.vault_missing else "UNSIGNED"
            )
        try:
            fx_rates = FxRateBook.restore(journal_for(FxRateBook.STREAM))
        except RegistryPersistenceError as exc:
            fx_rates = FxRateBook(store=failed(FxRateBook.STREAM, exc))
        try:
            proposals = EngineProposalBook.restore(journal_for(EngineProposalBook.STREAM))
        except RegistryPersistenceError as exc:
            proposals = EngineProposalBook(store=failed(EngineProposalBook.STREAM, exc))
        try:
            ledger = SpendLedger.restore(journal_for(SpendLedger.STREAM))
        except LedgerPersistenceError as exc:
            ledger = SpendLedger(store=failed(SpendLedger.STREAM, exc))
        try:
            northstar = NorthStarLedger.restore(journal_for(NorthStarLedger.STREAM), timezone=cfg.timezone)
        except NorthStarPersistenceError as exc:
            northstar = NorthStarLedger(timezone=cfg.timezone, store=failed(NorthStarLedger.STREAM, exc))
        try:
            costs = CostRegister.restore(journal_for(CostRegister.STREAM), northstar)
            if NorthStarLedger.STREAM not in restore_errors:
                costs.sync()  # rattrape un coût des ventes enregistré dans le registre mais pas encore dans l'étoile
        except NorthStarPersistenceError as exc:
            costs = CostRegister(northstar, store=failed(CostRegister.STREAM, exc))
        if config is not None:
            incoherent = consistency_errors(
                config,
                pricing=rules.pricing,
                stock=rules.stock,
                treasury_reserve=CASH_STOPLOSS_RESERVE,
                mandate_cash_reserve=mandate.cash_reserve_chf if mandate is not None else None,
                mandate_extension_share=mandate.extension_max_share if mandate is not None else None,
                mandate_stock_budget=mandate.stock_budget_chf if mandate is not None else None,
            )
            if incoherent:
                errors["coherence"] = " ; ".join(incoherent)
                config_holds.append("une même règle a deux valeurs : " + " ; ".join(incoherent))
        try:
            history = PersistentPriceHistory.restore(journal_for(PersistentPriceHistory.STREAM))
        except StateStoreError as exc:
            history = PersistentPriceHistory(failed(PersistentPriceHistory.STREAM, exc))
        try:
            approvals = PriceApprovalBook.restore(journal_for(PriceApprovalBook.STREAM))
        except PriceApprovalPersistenceError as exc:
            approvals = PriceApprovalBook(store=failed(PriceApprovalBook.STREAM, exc))
        try:
            baselines = ImportBaselineStore.restore(journal_for(ImportBaselineStore.STREAM))
        except BaselinePersistenceError as exc:
            baselines = ImportBaselineStore(store=failed(ImportBaselineStore.STREAM, exc))
        try:
            stock = PersistentStockRegistry.restore(journal_for(PersistentStockRegistry.STREAM), clock=now)
        except StockPersistenceError as exc:
            stock = PersistentStockRegistry(clock=now, store=failed(PersistentStockRegistry.STREAM, exc))
        catalog_journal = journal_for(CatalogRegistry.CATALOG_STREAM)
        costs_journal = journal_for(CatalogRegistry.COSTS_STREAM)
        try:
            catalog = CatalogRegistry.restore(catalog_journal, costs_journal)
        except SyncRegistryPersistenceError as exc:
            catalog = CatalogRegistry(
                catalog_store=failed(CatalogRegistry.CATALOG_STREAM, exc), costs_store=failed(CatalogRegistry.COSTS_STREAM, exc)
            )
        try:
            sync_runs = SyncRunLog.restore(journal_for(SyncRunLog.STREAM))
        except SyncRegistryPersistenceError as exc:
            sync_runs = SyncRunLog(store=failed(SyncRunLog.STREAM, exc))
        try:
            publications = ShopPublicationBook.restore(journal_for(ShopPublicationBook.STREAM))
        except ShopStatePersistenceError as exc:
            publications = ShopPublicationBook(store=failed(ShopPublicationBook.STREAM, exc))
        try:
            capital = CapitalRegister.restore(journal_for(CapitalRegister.STREAM))
        except ActivityRegisterPersistenceError as exc:
            capital = CapitalRegister(store=failed(CapitalRegister.STREAM, exc))
        try:
            ads = AdsActivityRegister.restore(journal_for(AdsActivityRegister.STREAM))
        except ActivityRegisterPersistenceError as exc:
            ads = AdsActivityRegister(store=failed(AdsActivityRegister.STREAM, exc))
        try:
            catalog_approvals = CatalogApprovalBook.restore(journal_for(CatalogApprovalBook.STREAM))
        except CatalogApprovalPersistenceError as exc:
            catalog_approvals = CatalogApprovalBook(store=failed(CatalogApprovalBook.STREAM, exc))
        try:
            invoices = SupplierInvoiceBook.restore(journal_for(SupplierInvoiceBook.STREAM))
        except InvoicePersistenceError as exc:
            invoices = SupplierInvoiceBook(store=failed(SupplierInvoiceBook.STREAM, exc))
        try:
            orders = OrderRegister.restore(journal_for(OrderRegister.STREAM))
        except NorthStarError as exc:
            orders = OrderRegister(store=failed(OrderRegister.STREAM, exc))
        try:  # revue R5 (R3-NEW-02 partiel) : le plancher des dettes survit au redémarrage
            balances = BalanceStatementBook.restore(journal_for(BalanceStatementBook.STREAM))
        except ActivityRegisterPersistenceError as exc:
            balances = BalanceStatementBook(store=failed(BalanceStatementBook.STREAM, exc))
        # Pré-drop (6.10.2026) : paramètres signés (sinon désactivé) et registre persisté (dettes de la photo).
        predrop_config = load_predrop_config(cfg.predrop_path, expected_fingerprint=cfg.predrop_fingerprint)
        signatures["predrop"] = predrop_config.signature
        if predrop_config.signature == "TAMPERED":
            errors["predrop"] = predrop_config.reason
        try:
            predrop = PredropRegistry.restore(journal_for(PredropRegistry.STREAM))
        except PredropPersistenceError as exc:
            predrop = PredropRegistry(store=failed(PredropRegistry.STREAM, exc))
        if NorthStarLedger.STREAM not in restore_errors and OrderRegister.STREAM not in restore_errors:
            # Rattrape une vente (et sa sortie de stock) enregistrée mais pas encore dérivée. Revue R4 (R3-NEW-04) :
            # un conflit sur une écriture dérivée ne gèle plus le registre : étoile polaire signalée incomplète.
            try:
                derivation = orders.sync(northstar, costs if CostRegister.STREAM not in restore_errors else None)
            except NorthStarPersistenceError as exc:
                orders = OrderRegister(store=failed(OrderRegister.STREAM, exc))
            else:
                if derivation:
                    errors["northstar.derivation"] = " ; ".join(f"{k} : {v}" for k, v in sorted(derivation.items()))
        if restore_errors:
            reason = " ; ".join(f"{k} : {v}" for k, v in sorted(restore_errors.items()))
            for stream, message in restore_errors.items():
                errors[f"persistence.{stream}"] = message
            if engine is not None:
                engine.hold_restore_failed(reason, now())
            if IncidentManager.STREAM in restore_errors:
                incidents.hold_all_writes(reason)
        if config_holds and engine is not None:
            engine.hold_config_unsigned(" ; ".join(config_holds), now())
        ledger_ok = not {SpendLedger.STREAM, MandateRevocations.STREAM, FxRateBook.STREAM} & set(restore_errors)
        client = ShopifyClient.from_settings(
            cfg,
            transport=shopify_transport,
            audit=audit,
            idempotency=idempotency,
            clock=now,
            **({"sleep": sleep} if sleep is not None else {}),
        )
        holder: dict[str, Any] = {}
        gate = GovernanceGate(
            autonomy,
            audit=audit,
            stoploss_engine=engine,
            state_provider=lambda: holder["svc"].stoploss_state,
            mandate_provider=lambda: holder["svc"].mandate if ledger_ok else None,
            spend_ledger=ledger,
            incidents=incidents,
            real_writes_enabled=cfg.real_writes_enabled,
            clock=now,
            treasury_provider=lambda: treasury_from_registers(
                holder["svc"].stoploss_state, holder["svc"].paypal_balance
            ),
            fx_rates=fx_rates,
            proposals=proposals,
        )
        sync = SyncService(
            client=client,
            gate=gate,
            incidents=incidents,
            audit=audit,
            price_history=history,
            clock=now,
            test_store=cfg.shopify_test_store,
            stock=stock,
            baselines=baselines,
            publications=publications,
        )
        svc = cls(
            settings=cfg,
            clock=now,
            audit=audit,
            idempotency=idempotency,
            autonomy=autonomy,
            incidents=incidents,
            rules=rules,
            stoploss_config=config,
            stoploss_engine=engine,
            mandate=mandate,
            spend_ledger=ledger,
            northstar=northstar,
            stock=stock,
            price_history=history,
            client=client,
            gate=gate,
            sync=sync,
            load_errors=errors,
            stoploss_state=photo,
            photo_journal=photo_journal,
            restore_errors=restore_errors,
            state_backend="postgres" if factory is not None else cfg.state_backend,
            fx_rates=fx_rates,
            proposals=proposals,
            revocations=revocations,
            costs=costs,
            photo_poster=photo_poster,
            signatures=signatures,
            price_approvals=approvals,
            baselines=baselines,
            catalog=catalog,
            sync_runs=sync_runs,
            capital=capital,
            ads=ads,
            publications=publications,
            catalog_approvals=catalog_approvals,
            orders=orders,
            invoices=invoices,
            balances=balances,
            predrop=predrop,
            predrop_config=predrop_config,
        )
        if photo is not None:  # plafond pub et budget stock du moteur, jamais ceux de la photo relue
            svc.stoploss_state, _ = svc.authoritative_photo(photo, now())
        holder["svc"] = svc
        return svc


# ------------------------------------------------------------------------- requêtes


class QuoteIn(_In):
    """Cotation d'un coût rendu (BP §4-5). ``small_product`` ne peut que restreindre (False)."""

    cost_chf: NonNegativeMoney
    profile: VatMode | None = None
    market_ref: NonNegativeMoney | None = None
    current_public: NonNegativeMoney | None = None
    unknown_fields: list[str] = Field(default_factory=list)
    candidate_price: PositiveMoney | None = None
    small_product: bool | None = None
    offer_stale: bool = False
    previous_cost: PositiveMoney | None = None


class BasketLineIn(_In):
    sku: str = Field(min_length=1)
    qty: int = Field(ge=1, le=10_000)
    unit_price_ttc: PositiveMoney
    unit_cost: NonNegativeMoney


class DiscountIn(_In):
    """Remise : ``PERCENT`` en fraction (0.10 = 10 %, au plus 1) ; ``AMOUNT`` en CHF TTC ≥ 0."""

    kind: Literal["PERCENT", "AMOUNT"]
    value: NonNegativeMoney
    code: str | None = None

    @model_validator(mode="after")
    def _percent(self) -> DiscountIn:
        if self.kind == "PERCENT" and self.value > 1:
            raise ValueError("remise PERCENT en fraction : 0 à 1 (0.10 = 10 %)")
        return self


class BasketIn(_In):
    """Panier multi-produits (frais par commande comptés une fois)."""

    lines: list[BasketLineIn] = Field(min_length=1, max_length=200)
    shipping_charged: NonNegativeMoney = Decimal("0")
    discount: DiscountIn | None = None
    shipping_cost_actual: NonNegativeMoney | None = None
    profile: VatMode | None = None


class SellableIn(_In):
    """Stock vendable : registre du service (``sku``) ou calcul direct."""

    sku: str | None = None
    on_hand: int | None = Field(default=None, ge=0)
    reserved: int = Field(default=0, ge=0)
    damaged: int = Field(default=0, ge=0)
    safety: int = Field(default=0, ge=0)


class ReorderIn(_In):
    """Proposition de réassort (jamais une commande).

    Budget stock total : celui du moteur (règles signées, mandat signé), jamais celui de l'appelant.
    ``extension_exposure`` ne peut qu'**ajouter** à l'exposition de la photo stop-loss acceptée ;
    ``cap_exceptions`` (C18) exige le jeton de la propriétaire.
    """

    candidates: list[ReorderCandidate]
    budget_available: NonNegativeMoney
    extension_exposure: dict[str, NonNegativeMoney] = Field(default_factory=dict)
    cap_exceptions: dict[str, NonNegativeMoney] = Field(default_factory=dict)
    actor: str = "finance-pricing"

    @model_validator(mode="after")
    def _caps(self) -> ReorderIn:
        for ext, cap in self.cap_exceptions.items():
            if not 0 < cap <= 1:
                raise ValueError(f"exception de plafond {ext} : fraction dans ]0, 1]")
        return self


class StockReceiveIn(_In):
    """Réception physique contrôlée en stock local (agent 11 logistique) ; idempotente par (sku, ref)."""

    sku: str = Field(min_length=3, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9._-]{2,63}$")
    qty: int = Field(ge=1, le=10_000)
    ref: str = Field(min_length=3, max_length=120)
    """Référence du bon de livraison ou du lot (clé d'idempotence avec le SKU)."""


class PriceApprovalIn(_In):
    """Approbation d'un prix public par la propriétaire (jeton propriétaire obligatoire)."""

    product_key: str = Field(min_length=1, max_length=120)
    price: PositiveMoney
    reason: str = Field(min_length=10, max_length=500)
    floor_exception_ref: str | None = Field(default=None, min_length=3, max_length=120)
    valid_hours: int = Field(default=48, ge=1, le=168)


class ImportIn(_In):
    """Import en simulation d'un fichier du dossier autorisé (``POKESHOP_IMPORTS_DIR``)."""

    source_path: str = Field(min_length=1)
    source_ts: datetime | None = None


def _declared_listing(value: Any) -> Any:
    """Fiche d'entrée : aucun champ du moteur ni validation humaine (422) — revue R3 (SEC-09, R2-NEW-02, R2-NEW-05)."""
    return refuse_declared_listing_fields(value)


DeclaredListing = Annotated[CatalogListing, BeforeValidator(_declared_listing)]
"""Fiche reçue d'un appelant : ``approved``, ``content_validated``, ``category_rule_validated``,
``shopify_product_id``, ``shopify_status``, ``shopify_inventory_item_id`` et ``current_price_chf`` refusés."""


class PublishPreviewIn(_In):
    """Aperçu de publication : fiche + coût rendu (jamais renvoyé).

    Aucune « validation de prix » dans le corps : l'approbation éventuelle est lue dans le registre
    du moteur (``POST /pricing/approvals``, jeton propriétaire) ; le statut de stock est recalculé ;
    validations de fiche et état publié : registres du moteur et de la propriétaire (jamais la fiche).
    """

    listing: DeclaredListing
    quote: QuoteIn | None = None
    reference_price_24h: PositiveMoney | None = None
    stoploss_blocked: bool = False
    sensitive_terms: list[str] = Field(default_factory=list)


class CatalogItemIn(_In):
    """Produit du catalogue : **une seule clé** (revue R4, R3-NEW-01) — ``product_id`` = ``listing.product_key``."""

    product_id: str = Field(min_length=1, max_length=120)
    supplier_links: list[SupplierLink] = Field(default_factory=list)
    listing: DeclaredListing

    @model_validator(mode="after")
    def _canonical(self) -> CatalogItemIn:
        if self.product_id != self.listing.product_key:
            raise ValueError(
                f"clé produit incohérente : product_id {self.product_id!r} ≠ listing.product_key "
                f"{self.listing.product_key!r} (quarantaine, stop-loss, publication et coûts portent sur une seule clé)"
            )
        return self


class CatalogApprovalIn(_In):
    """Validations humaines d'une fiche du catalogue : **propriétaire uniquement** (jeton propriétaire).

    Portent sur le contenu en vigueur de la fiche au registre (empreinte inscrite) ; ``false`` retire.
    """

    product_id: str = Field(min_length=1, max_length=120)
    approved: bool = False
    content_validated: bool = False
    category_rule_validated: bool = False
    reason: str = Field(min_length=10, max_length=500)
    listing_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    """Empreinte de la fiche examinée (``GET /catalog/approvals``) : refus si la fiche a changé depuis."""


class ShippedOrderLineIn(_In):
    """Ligne expédiée : SKU boutique du catalogue validé et quantité (unités vendues)."""

    public_sku: str = Field(min_length=3, max_length=64)
    qty: int = Field(ge=1, le=10_000)


class ShippedOrderIn(_In):
    """Commande payée **et expédiée** (workflow 02) : coût réel du transporteur obligatoire (revue MOT-18).

    Revue R4 (R3-NEW-05) : ``lines`` obligatoires (SKU × quantité) — sortie de stock et coût des ventes au CMP
    dérivés par le moteur, jamais déclarés par l'agent finance.
    """

    order_id: str = Field(min_length=1, max_length=120)
    lines: list[ShippedOrderLineIn] = Field(min_length=1, max_length=200)
    paid_at: datetime
    net_sales_ht: PositiveMoney
    payment_fees: NonNegativeMoney
    shipping_cost_actual: PositiveMoney
    shipping_label_ref: str = Field(min_length=3, max_length=120)
    source: str = Field(min_length=3, max_length=200)


class OrderLineResolveIn(_In):
    """Rattachement d'une ligne non rattachée (revue R6, R5-NEW-02) : SKU de la ligne, clé produit canonique."""

    public_sku: str = Field(min_length=3, max_length=64)
    product_key: str = Field(min_length=1, max_length=120)


class OrderRefundIn(_In):
    """Avoir sur une commande enregistrée (cumul ≤ ventes de la commande).

    Revue R5 (R3-NEW-05) : ``lines`` = unités **retournées** (SKU × quantité ≤ vendues − déjà retournées) ; vide pour
    un remboursement sans retour (geste commercial), qui ne remet jamais rien en stock au coût.
    """

    refund_id: str = Field(min_length=1, max_length=120)
    at: datetime
    net_sales_ht: PositiveMoney
    payment_fees_refunded: NonNegativeMoney = Decimal("0")
    lines: list[ShippedOrderLineIn] = Field(default_factory=list, max_length=200)


class CatalogItemsIn(_In):
    """Lot de produits du catalogue validé (agent catalogue) : enregistré tout ou rien."""

    items: list[CatalogItemIn] = Field(min_length=1, max_length=500)


class CostInputsIn(_In):
    """Frais connus d'un fournisseur (CHF par unité retail) ; aucun taux de change déclaré ici."""

    supplier_id: str = Field(min_length=2, max_length=64)
    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    inbound_freight_alloc: NonNegativeMoney | None = None
    customs_and_fees: NonNegativeMoney | None = None
    import_vat: NonNegativeMoney | None = None
    order_qty: int | None = Field(default=None, ge=1, le=100_000)
    source: str = Field(min_length=3, max_length=300)


class CapitalMovementIn(_In):
    """Apport (``CONTRIBUTION``) ou retrait (``WITHDRAWAL``) de capital : **propriétaire uniquement**."""

    movement_id: str = Field(min_length=3, max_length=80)
    at: datetime
    kind: Literal["CONTRIBUTION", "WITHDRAWAL"]
    amount: PositiveMoney
    ref: str = Field(default="", max_length=200)


class BankBalanceIn(_In):
    """Solde du compte bancaire de l'activité relevé par un connecteur (jamais par l'agent qui dépense)."""

    as_of: datetime
    balance_chf: Money
    source: str = Field(min_length=3, max_length=200)


class BalanceItemsIn(_In):
    """Dettes et/ou créances à date ; listes vides = « aucune », attesté.

    Revue R5 (R4-NEW-02, R4-DOC-01) : deux registres **séparés**. Déclaration des **dettes** = champ
    ``preorders_collected_chf`` présent (avec ``debts``, vide si aucune) — agent finance, connecteur de trésorerie ou
    propriétaire. Relevé des **créances** = champ ``receivables`` — propriétaire seule ; un dépôt de la propriétaire
    avec ``receivables`` seul ne touche pas aux dettes, une déclaration de dettes d'un rôle ne touche pas aux créances
    (``receivables: []`` d'un rôle est ignoré, une créance d'un rôle : 403).
    """

    as_of: datetime
    preorders_collected_chf: NonNegativeMoney | None = None
    debts: list[BalanceItem] | None = Field(default=None, max_length=200)
    receivables: list[BalanceItem] | None = Field(default=None, max_length=200)
    source: str = Field(min_length=3, max_length=300)


class AdsActivityIn(_In):
    """Dépenses publicitaires (campagne, jour) et commandes attribuées, relevées par le connecteur publicitaire."""

    ad_spends: list[AdSpend] = Field(default_factory=list, max_length=2000)
    attributed_orders: list[AttributedOrder] = Field(default_factory=list, max_length=5000)


class SyncCostInputsIn(_In):
    """Frais d'un fournisseur fournis dans le corps de ``/sync/run`` (**simulation seulement**).

    Aucun champ de taux de change (``fx_rate_to_chf``, ``fx_source``, ``fx_date`` : 422) : le taux vient
    toujours du registre de la propriétaire (``POST /fx/rates``), sinon le coût reste incomplet (brouillon).
    """

    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    inbound_freight_alloc: NonNegativeMoney | None = None
    customs_and_fees: NonNegativeMoney | None = None
    import_vat: NonNegativeMoney | None = None
    order_qty: int | None = Field(default=None, ge=1, le=100_000)


class SyncIn(_In):
    """Cycle fournisseur → site (simulation par défaut).

    Sans ``catalog`` dans le corps, le moteur lit son catalogue validé (``POST /catalog/items``) ; sans
    l'un ni l'autre : 409 « catalogue requis ». Sans ``cost_inputs``, frais du registre
    (``POST /catalog/cost-inputs``). Taux de change : **toujours** celui de la propriétaire
    (``POST /fx/rates``), jamais celui de l'appelant (revue MOT-02) ; ``cost_inputs`` du corps :
    simulation seulement (écriture réelle => 409).
    """

    supplier: str
    source_path: str
    dry_run: bool = True
    catalog: list[CatalogItemIn] = Field(default_factory=list)
    cost_inputs: dict[str, SyncCostInputsIn] = Field(default_factory=dict)
    market_refs: dict[str, PositiveMoney] = Field(default_factory=dict)
    source_ts: datetime | None = None
    """Horodatage déclaré par l'appelant pour une source non datée : il ne peut que la vieillir."""


class IncidentIn(_In):
    cause: str = Field(min_length=3)
    code: IncidentCode | None = None
    kind: str | None = None
    severity: Severity | None = None
    scope: IncidentScope | None = None
    proposed_action: str | None = None
    product_key: str | None = None
    supplier_id: str | None = None
    workflow: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="agent", min_length=2)
    simulation: bool = False


class IncidentTestIn(_In):
    test_ref: str = Field(min_length=3)
    passed: bool
    actor: str = Field(min_length=2)


class ActorIn(_In):
    actor: str = Field(min_length=2)


class AutonomyIn(_In):
    level: int = Field(ge=1, le=4)
    reason: str = Field(min_length=5)
    actor: str = Field(min_length=2)


class FreezeIn(_In):
    actor: str = Field(min_length=2)
    reason: str = Field(min_length=5)


class RearmIn(_In):
    """Réarmement : ``reference_chf`` = valeur nette de la photo, **attestée** par la propriétaire (rebase)."""

    reason: str = Field(min_length=10)
    rebase: bool = True
    reference_chf: Money | None = None
    photo_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class BaselineIn(_In):
    """Point zéro du capital engagé, déclaré par la propriétaire (STOP_LOSS.md §5, option A ou B).

    ``with_photo`` (revue R2-ADV-01) : la **première** photo est construite par le moteur depuis ses
    registres et le point zéro est posé **avant** toute évaluation, de façon atomique (sinon la photo du
    lancement, évaluée sans point zéro, gèlerait tout et rendrait le point zéro impossible).
    """

    reason: str = Field(min_length=10)
    reference_chf: Money
    with_photo: bool = False


class MandateCheckIn(_In):
    """Demande de dépense ; ``treasury`` éventuel est **ignoré** (trésorerie lue dans les registres du moteur)."""

    request: SpendRequest
    treasury: TreasurySnapshot | None = None
    record: bool = False


class HumanDecisionIn(_In):
    """Décision de la propriétaire sur une dépense en attente de validation humaine (revue R5, R4-DOC-03)."""

    idempotency_key: str = Field(min_length=3, max_length=200)
    decision: Literal["APPROVE", "REFUSE"]
    motif: str = Field(default="", max_length=500)


class PayPalBalanceIn(_In):
    """Solde du compte PayPal dédié relevé par un connecteur (jamais par l'agent qui demande la dépense)."""

    as_of: datetime
    balance_chf: Money
    source: str = Field(min_length=3)


class FxRateIn(_In):
    """Taux de change de référence saisi par la propriétaire (source officielle datée)."""

    currency: str
    rate_to_chf: Money
    rate_date: date
    source: str = Field(min_length=3)


class RevokeIn(_In):
    reason: str = Field(min_length=5)
    actor: str = Field(default="agent", min_length=2)


class CapitalResetIn(_In):
    reason: str = Field(min_length=10)


class CostMovementIn(_In):
    """Mouvement du registre de coûts historiques (le coût d'une sortie est calculé par le moteur)."""

    kind: Literal["RECEIPT", "ISSUE", "RETURN", "WRITE_OFF", "INVOICE_ADJUSTMENT"]
    product_key: str = Field(min_length=1)
    at: datetime
    ref: str = Field(min_length=1)
    qty: int | None = Field(default=None, ge=1)
    unit_cost: Money | None = None
    lot_id: str | None = None
    sale_ref: str | None = None
    stock_ref: str | None = Field(default=None, min_length=3, max_length=120)
    """RECEIPT : référence de la réception physique ``POST /stock/receive`` (même SKU, même quantité, autre jeton)."""
    invoice_ref: str | None = Field(default=None, min_length=3, max_length=120)
    """RECEIPT et INVOICE_ADJUSTMENT : référence de la facture fournisseur."""


class NorthStarEntriesIn(_In):
    entries: list[ContributionEntry] = Field(min_length=1)


class InvoiceLineIn(_In):
    """Ligne de facture : clé produit canonique, quantité, coût rendu unitaire ventilé (CHF).

    Revue R5 (R4-DOC-02) : ``unit_cost_chf`` hors TVA d'import ; ``import_vat_unit_chf`` = TVA d'import ventilée par
    unité, comptée au coût rendu selon le profil TVA du **moteur** (méthode effective : récupérable, hors coût).
    """

    product_key: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1, le=100_000)
    unit_cost_chf: PositiveMoney
    import_vat_unit_chf: NonNegativeMoney = Decimal("0")


class SupplierInvoiceIn(_In):
    """Facture fournisseur validée par la propriétaire (workflow 03) : montant dû en CHF, lignes au coût rendu."""

    invoice_ref: str = Field(min_length=3, max_length=120)
    supplier_id: str = Field(min_length=2, max_length=64)
    issued_at: datetime
    total_chf: PositiveMoney
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=500)
    source: str = Field(min_length=3, max_length=300)


class InvoicePaymentIn(_In):
    """Paiement d'une facture relevé sur le compte (référence de la transaction)."""

    payment_ref: str = Field(min_length=3, max_length=120)
    paid_at: datetime
    amount_chf: PositiveMoney


# --------------------------------------------------------------------------- application


class PredropAllocationIn(_In):
    """Allocation **ferme** confirmée par le fournisseur (propriétaire ou workflow 03 après sa validation)."""

    product_key: str = Field(min_length=1, max_length=120)
    supplier_id: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1, le=100_000)
    supplier_confirmation_ref: str = Field(min_length=3, max_length=200)
    expected_delivery: date | None = None
    source: str = Field(min_length=3, max_length=300)


class PredropReduceIn(_In):
    """Réduction d'allocation annoncée par le fournisseur ou constatée à la réception (baisse seulement)."""

    new_qty: int = Field(ge=0, le=100_000)
    supplier_confirmation_ref: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=10, max_length=500)


class PredropDemandIn(_In):
    """Compte **agrégé** d'inscrits consentants intéressés : aucun autre champ (donnée personnelle : 422)."""

    product_key: str = Field(min_length=1, max_length=120)
    interested_consenting_subscribers: int = Field(ge=0, le=10_000_000)
    as_of: AwareDatetime
    source: str = Field(min_length=3, max_length=200)


class PredropOpenIn(_In):
    """Ouverture d'un pré-drop : le moteur évalue toutes les conditions sur ses registres."""

    product_key: str = Field(min_length=1, max_length=120)
    drop_date: date
    opens_at: AwareDatetime | None = None
    closes_at: AwareDatetime | None = None
    market_ref_chf: PositiveMoney | None = None
    """Référence marché : **propriétaire seule** (un rôle qui en fournit une : 403)."""


class PredropApproveIn(_In):
    """Validation d'un pré-drop en attente par la propriétaire (référence marché attestée, ou inconnue assumée)."""

    market_ref_chf: PositiveMoney | None = None
    reason: str = Field(min_length=10, max_length=500)


class PredropCloseIn(_In):
    """Fermeture d'un pré-drop (acte protecteur)."""

    reason: str = Field(min_length=10, max_length=500)


class PredropReservationIn(_In):
    """Réservation **payée** (commande Shopify, workflow 02) ; ``customer_ref`` = sha256 de l'identifiant client."""

    predrop_id: str = Field(min_length=1, max_length=120)
    order_id: str = Field(min_length=1, max_length=120)
    customer_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    qty: int = Field(ge=1, le=10)
    amount_paid_ttc: PositiveMoney
    paid_at: AwareDatetime
    priority_access: bool = False
    """Commande passée par l'accès prioritaire des inscrits aux alertes (attesté par la boutique)."""


class PredropRefundExecutedIn(_In):
    """Remboursement exécuté par le PSP (relevé par le workflow 02)."""

    executed_at: AwareDatetime
    psp_refund_ref: str = Field(min_length=3, max_length=120)


def _token_ok(token: str | None, expected: str | None) -> bool:
    if not token or not expected:
        return False
    return hmac.compare_digest(sha256_hex(token), expected)


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> FastAPI:
    """Application FastAPI (fabrique : ``uvicorn pokeshop.api:create_app --factory``)."""
    svc = services or Services.build(settings)
    cfg = svc.settings
    owner_refusal_hooks: dict[str, Callable[[str], None]] = {}
    """Journal propre à une route quand la propriétaire est exigée et absente (ex. tentative de réarmement)."""

    def api_principal(request: Request) -> Principal:
        """Jeton d'API valide : commun (« api ») ou nommé (nom = rôle) ; 503 sans empreinte, 401 sinon."""
        if cfg.api_token_sha256 is None and not cfg.agent_tokens_sha256:
            raise HTTPProblem(
                503,
                "jeton d'API non configuré (POKESHOP_AGENT_TOKENS_SHA256 ou POKESHOP_API_TOKEN_SHA256) : "
                "routes internes fermées",
            )
        token = request.headers.get(API_TOKEN_HEADER)
        found: Principal | None = None
        if token:
            digest = sha256_hex(token)
            if cfg.api_token_sha256 is not None and hmac.compare_digest(digest, cfg.api_token_sha256):
                found = Principal(authz.COMMON, False)
            for name, expected in cfg.agent_tokens_sha256.items():  # parcours complet (temps constant)
                if hmac.compare_digest(digest, expected):
                    found = Principal(name, True)
        if found is None:
            raise HTTPProblem(401, f"en-tête {API_TOKEN_HEADER} absent ou invalide")
        return found

    def owner_check(request: Request) -> str | None:
        """Motif de refus du jeton propriétaire (None = valide)."""
        token = request.headers.get(OWNER_TOKEN_HEADER)
        if not token:
            return "absent"
        if token == request.headers.get(API_TOKEN_HEADER):
            return "identique au jeton d'API"
        return None if verify_owner_token(token, cfg.owner_token_sha256) else "jeton invalide"

    def authorize(request: Request) -> None:
        """Garde unique de **toutes** les routes : matrice :mod:`pokeshop.authz`, refus par défaut (revue R3).

        Route absente de la matrice : 403. Jeton commun : lecture et aperçus seulement. Écriture : rôle du
        jeton nommé listé, ou propriétaire (jeton propriétaire vérifié). Tout refus est journalisé.

        Revue R4 (R3-DOC-01) : un jeton propriétaire **valide suffit seul** sur toute route qui admet la
        propriétaire (actes réservés, lectures, aperçus) : aucun ``X-Pokeshop-Token`` n'est exigé en plus (le
        jeton commun est facultatif et n'est jamais remis à la propriétaire pour ses actes).
        """
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        rule = authz.rule_for(request.method, path) if isinstance(path, str) else None
        if rule is None:
            svc.audit.append(
                actor="inconnu", actor_kind=ActorKind.AGENT, action="authz.route_refused", entity="route",
                entity_id=f"{request.method} {path or request.url.path}", dry_run=False,
                payload={"motif": "route absente de la matrice d'autorisations"},
            )  # fmt: skip
            raise HTTPProblem(
                403, "route absente de la matrice d'autorisations (engine/pokeshop/authz.py) : refusée par défaut"
            )
        if rule.kind is authz.Kind.PUBLIC:
            request.state.principal = None
            return
        motif = owner_check(request)
        if motif is None and rule.owner:
            request.state.principal = Principal(authz.OWNER, True, owner=True)
            return
        principal = api_principal(request)
        if rule.owner_only:
            if motif is not None:
                svc.audit.append(
                    actor="inconnu", actor_kind=ActorKind.AGENT, action=f"{rule.audit}.owner_token_refused",
                    entity="owner_token", entity_id=request.url.path, dry_run=False,
                    payload={"motif": motif, "token": principal.name},
                )  # fmt: skip
                hook = owner_refusal_hooks.get(rule.audit)
                if hook is not None:
                    hook(motif)
                raise HTTPProblem(
                    403,
                    {
                        "absent": f"acte réservé à la propriétaire : en-tête {OWNER_TOKEN_HEADER} requis",
                        "identique au jeton d'API": "jeton propriétaire identique au jeton d'API : jetons distincts exigés",
                    }.get(motif, "acte réservé à la propriétaire : jeton propriétaire invalide"),
                )
            request.state.principal = Principal(authz.OWNER, True, owner=True)  # pragma: no cover - traité plus haut
            return
        if not authz.allowed(rule, role=principal.role, owner=False):
            kind = "common_token_refused" if not principal.named else "role_refused"
            svc.audit.append(
                actor=principal.name, actor_kind=ActorKind.AGENT, action=f"{rule.audit}.{kind}", entity="token",
                entity_id=request.url.path, dry_run=False,
                payload={"motif": "jeton commun non attribuable" if not principal.named else "rôle non autorisé",
                         "role": principal.name, "authz_version": authz.AUTHZ_VERSION},
            )  # fmt: skip
            admitted = "tout rôle nommé" if rule.roles == authz.ALL_NAMED else (", ".join(sorted(rule.roles)) or "aucun rôle")
            if not principal.named:
                message = (
                    "jeton commun : lecture et aperçus en simulation seulement ; écriture réservée à un jeton nommé "
                    f"par rôle ({admitted}{' ou propriétaire' if rule.owner else ''})"
                )
            else:
                message = (
                    f"rôle « {principal.name} » non autorisé sur {request.method} {path} "
                    f"(matrice engine/pokeshop/authz.py : {admitted}{' ou propriétaire' if rule.owner else ''})"
                )
            raise HTTPProblem(403, message)
        request.state.principal = principal

    app = FastAPI(
        title="Moteur boutique Pokémon JCC FR — API interne",
        version=__version__,
        description="API interne appelée par n8n. Montants CHF en chaînes. Simulation par défaut.",
        default_response_class=PokeshopJSONResponse,
        dependencies=[Depends(authorize)],
        # Refus par défaut : aucune route hors matrice (pas de documentation interactive exposée).
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.services = svc

    @app.exception_handler(HTTPProblem)
    async def _problem(_: Request, exc: HTTPProblem) -> PokeshopJSONResponse:
        return _ok({"erreur": exc.message, **exc.extra}, exc.status)

    def _error(status: int) -> Callable[[Request, Exception], Any]:
        async def handler(_: Request, exc: Exception) -> PokeshopJSONResponse:
            return _ok({"erreur": str(exc), "type": type(exc).__name__}, status)

        return handler

    async def _invalid(_: Request, exc: Exception) -> PokeshopJSONResponse:
        details = to_jsonable(exc.errors(include_url=False, include_context=False)) if isinstance(exc, ValidationError) else None
        return _ok({"erreur": "requête invalide", "type": type(exc).__name__, "details": details}, 422)

    # Valeur invalide détectée après le corps (modèle interne, calcul décimal) : 422, jamais 500.
    app.add_exception_handler(ValidationError, _invalid)
    app.add_exception_handler(ArithmeticError, _invalid)

    for exc_type, status in (
        (StopLossPersistenceError, 503),
        (LedgerPersistenceError, 503),
        (NorthStarPersistenceError, 503),
        (IncidentPersistenceError, 503),
        (StateStoreError, 503),
        (PriceApprovalPersistenceError, 503),
        (BaselinePersistenceError, 503),
        (ShopStatePersistenceError, 503),
        (StockPersistenceError, 503),
        (SyncRegistryPersistenceError, 503),
        (ActivityRegisterPersistenceError, 503),
        (InvoicePersistenceError, 503),
        (PredropPersistenceError, 503),
        (PredropError, 409),
        (InvoiceError, 409),
        (SyncRegistryError, 409),
        (ActivityRegisterError, 409),
        (PhotoSourcesError, 409),
        (RearmRefusedError, 403),
        (AutonomyRefusedError, 403),
        (ShopifyAccessDeniedError, 502),
        (ShopifyError, 502),
        (IncidentError, 409),
        (StopLossError, 409),
        (AutonomyError, 409),
        (SensitiveFieldError, 422),
        (MappingError, 422),
        (ImporterError, 422),
        (PokeshopError, 422),
    ):
        app.add_exception_handler(exc_type, _error(status))

    def require_api(request: Request) -> Principal:
        """Appelant déjà autorisé par :func:`authorize` (matrice) ; jamais évalué ici => 403 (fermé par défaut)."""
        principal = getattr(request.state, "principal", None)
        if not isinstance(principal, Principal):
            raise HTTPProblem(403, "autorisation non évaluée : route refusée (fermé par défaut)")
        return principal

    def owner_verified(request: Request) -> bool:
        token = request.headers.get(OWNER_TOKEN_HEADER)
        return bool(token) and token != request.headers.get(API_TOKEN_HEADER) and verify_owner_token(
            token, cfg.owner_token_sha256
        )

    def actor_of(principal: Principal, declared: str | None, request: Request, *, route: str) -> str:
        """Acteur journalisé : nom du jeton nommé ; sinon nom déclaré, jamais « propriétaire » sans son jeton."""
        if principal.named:
            return principal.name
        name = (declared or "").strip() or "api"
        if is_owner_like(name) and not owner_verified(request):
            svc.audit.append(
                actor=name,
                actor_kind=ActorKind.AGENT,
                action=f"{route}.owner_impersonation_refused",
                entity="actor",
                entity_id=request.url.path,
                dry_run=False,
                payload={"declared": name},
            )
            raise HTTPProblem(403, "acteur « propriétaire » réservé au jeton de la propriétaire (X-Pokeshop-Owner-Token)")
        return name

    def require_named(principal: Principal, request: Request, *, route: str, what: str) -> None:
        """Valeur décisive (trésorerie, photo du stop-loss) : jeton **nommé** obligatoire, jamais le jeton commun.

        Le jeton commun n'est attribuable à personne : il ne peut pas fournir une valeur dont dépendent
        le gel du stop-loss ou une dépense (principe « aucune valeur décisive auto-déclarée »).
        """
        if principal.named:
            return
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT,
            action=f"{route}.common_token_refused",
            entity="token",
            entity_id=request.url.path,
            dry_run=False,
            payload={"motif": "jeton commun non attribuable"},
        )
        raise HTTPProblem(
            403,
            f"{what} : valeur décisive, jeton nommé obligatoire (connecteur ou agent, POKESHOP_AGENT_TOKENS_SHA256) ; "
            "le jeton commun n'est attribuable à personne",
        )

    def owner_token(
        request: Request,
        *,
        required: bool,
        route: str,
        on_refused: Callable[[str], None] | None = None,
    ) -> str | None:
        """En-tête propriétaire ; tout refus (absent, identique au jeton d'API) est journalisé, jamais le jeton."""
        token = request.headers.get(OWNER_TOKEN_HEADER)
        motif: str | None = None
        message = ""
        if token and token == request.headers.get(API_TOKEN_HEADER):
            motif = "identique au jeton d'API"
            message = "jeton propriétaire identique au jeton d'API : jetons distincts exigés"
        elif required and not token:
            motif, message = "absent", f"acte réservé à la propriétaire : en-tête {OWNER_TOKEN_HEADER} requis"
        if motif is not None:
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action=f"{route}.owner_token_refused",
                entity="owner_token",
                entity_id=request.url.path,
                dry_run=False,
                payload={"motif": motif},
            )
            if on_refused is not None:
                on_refused(motif)
            raise HTTPProblem(403, message)
        return token

    def _persistence_guard(stream: str, what: str) -> None:
        if stream in svc.restore_errors:
            raise HTTPProblem(
                503,
                f"{what} non relu au démarrage ({svc.restore_errors[stream]}) : réparer le stockage puis redémarrer",
            )

    def params_for(profile: VatMode | None) -> Any:
        if profile is None or profile is svc.rules.profile:
            return svc.rules.pricing
        return guard_rules(load_rules(cfg.rules_path, profile), cfg.rules_fingerprint)[0].pricing

    # -- santé ----------------------------------------------------------------------
    @app.get("/health")
    def health() -> PokeshopJSONResponse:
        """État du service (aucun secret, aucune donnée interne chiffrée)."""
        return _ok(
            {
                "status": "ok",
                "version": __version__,
                "time": svc.clock(),
                "rules_version": svc.rules.rules_version,
                "vat_profile": svc.rules.profile,
                "stoploss_version": svc.stoploss_config.stoploss_version if svc.stoploss_config else None,
                "mandate_version": svc.mandate.mandate_version if svc.mandate else None,
                "mandate_active": svc.mandate.is_active(svc.clock()) if svc.mandate else False,
                "autonomy_level": int(svc.autonomy.level),
                "global_frozen": svc.stoploss_engine.frozen if svc.stoploss_engine else None,
                "signatures": svc.signatures,
                "predrop": {"enabled": svc.predrop_config.enabled, "signature": svc.predrop_config.signature},
                "persistence": {
                    "backend": svc.state_backend,
                    "restored": not svc.restore_errors,
                    "unreadable": sorted(svc.restore_errors),
                },
                # Alertes d'incident en temps réel vers n8n (workflow 04) : simulées tant que
                # POKESHOP_NOTIFY_DRY_RUN n'est pas false, jamais envoyées sans le secret dédié
                # (POKESHOP_N8N_WEBHOOK_SECRET, revue R6) ; le digest 05 le signale chaque matin, ainsi que
                # le dernier envoi non livré (secret différent dans n8n après une rotation, 04 inactif…).
                "notifications": {
                    "webhook_configured": cfg.n8n_webhook_url is not None,
                    "webhook_dry_run": cfg.notify_dry_run,
                    "webhook_secret_configured": cfg.n8n_webhook_secret is not None,
                    "real_time_alerts": cfg.n8n_webhook_url is not None
                    and not cfg.notify_dry_run
                    and cfg.n8n_webhook_secret is not None,
                    "last_delivery": (
                        None
                        if not svc.incidents.receipts
                        else {
                            "delivered": svc.incidents.receipts[-1].delivered,
                            "dry_run": svc.incidents.receipts[-1].dry_run,
                            "detail": svc.incidents.receipts[-1].detail,
                        }
                    ),
                },
                "configuration": cfg.public_summary(),
                "real_write_blockers": cfg.real_write_blockers(),
                "load_errors": sorted(svc.load_errors),
            }
        )

    # -- prix -----------------------------------------------------------------------
    @app.post("/pricing/quote")
    async def pricing_quote(request: Request) -> PokeshopJSONResponse:
        """Décision de prix d'un coût rendu (règles versionnées)."""
        require_api(request)
        body = await _body(request, QuoteIn)
        decision = decide_price(
            body.cost_chf,
            params_for(body.profile),
            body.market_ref,
            body.current_public,
            body.unknown_fields,
            candidate_price=body.candidate_price,
            small_product=body.small_product,
            offer_stale=body.offer_stale,
            previous_cost=body.previous_cost,
        )
        return _ok(
            {"decision": decision, "labels_fr": explain(decision.reasons), "publishable": decision.is_publishable}
        )

    @app.post("/pricing/basket")
    async def pricing_basket(request: Request) -> PokeshopJSONResponse:
        """Contribution d'un panier ; BLOCKED sous 12 % ou 8 CHF."""
        require_api(request)
        body = await _body(request, BasketIn)
        lines = [
            BasketLine(sku=ln.sku, qty=ln.qty, unit_price_ttc=ln.unit_price_ttc, unit_cost=ln.unit_cost)
            for ln in body.lines
        ]
        discount = (
            Discount(kind=body.discount.kind, value=body.discount.value, code=body.discount.code)
            if body.discount
            else None
        )
        result = basket_contribution(
            lines,
            params_for(body.profile),
            body.shipping_charged,
            discount,
            shipping_cost_actual=body.shipping_cost_actual,
        )
        return _ok({"basket": result, "labels_fr": explain(result.reasons), "allowed": result.is_allowed})

    @app.post("/pricing/approvals", status_code=201)
    async def pricing_approval_create(request: Request) -> PokeshopJSONResponse:
        """Approuve un prix public : **propriétaire uniquement** (jeton distinct vérifié, motif, journal).

        Seule voie d'une « validation humaine » de prix (décision REVIEW, variation > 5 %/jour) :
        jamais sous le plancher dur 12 % / 8 CHF sans référence d'exception écrite C18
        (``floor_exception_ref``) ; validité 1 à 168 h.
        """
        require_api(request)
        token = owner_token(request, required=True, route="pricing.approval")
        if not verify_owner_token(token, cfg.owner_token_sha256):
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="pricing.approval.owner_token_refused",
                entity="owner_token",
                entity_id=request.url.path,
                dry_run=False,
                payload={"motif": "jeton invalide"},
            )
            raise HTTPProblem(403, "approbation de prix : jeton propriétaire valide requis")
        _persistence_guard(PriceApprovalBook.STREAM, "registre des approbations de prix")
        body = await _body(request, PriceApprovalIn)
        now = svc.clock()
        try:
            approval = PriceValidation.new(
                product_key=body.product_key,
                price=body.price,
                reason=body.reason,
                now=now,
                valid_for=timedelta(hours=body.valid_hours),
                floor_exception_ref=body.floor_exception_ref,
            )
        except ValidationError as exc:
            raise HTTPProblem(422, "approbation invalide", details=to_jsonable(exc.errors(include_url=False))) from None
        svc.price_approvals.record(approval)
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="pricing.approval",
            entity="product",
            entity_id=approval.product_key,
            dry_run=False,
            autonomy_level=int(svc.autonomy.level),
            payload={
                "approval_id": approval.approval_id,
                "price_chf": approval.price,
                "expires_at": approval.expires_at,
                "floor_exception_ref": approval.floor_exception_ref,
                "reason": approval.reason,
            },
        )
        return _ok({"approval": approval}, 201)

    @app.get("/pricing/approvals")
    def pricing_approvals_list(request: Request) -> PokeshopJSONResponse:
        """Approbations de prix en vigueur (registre du moteur)."""
        require_api(request)
        _persistence_guard(PriceApprovalBook.STREAM, "registre des approbations de prix")
        return _ok({"approvals": list(svc.price_approvals.active(svc.clock()).values())})

    @app.post("/pricing/approvals/{approval_id}/revoke")
    async def pricing_approval_revoke(approval_id: str, request: Request) -> PokeshopJSONResponse:
        """Retire une approbation (acte protecteur, tout porteur de jeton) ; journalisé."""
        principal = require_api(request)
        body = await _body(request, RevokeIn)
        actor = "propriétaire" if owner_verified(request) else actor_of(principal, body.actor, request,
                                                                         route="pricing.approval.revoke")  # fmt: skip
        revoked = svc.price_approvals.revoke(approval_id)
        svc.audit.append(
            actor=actor,
            actor_kind=ActorKind.PROPRIETAIRE if actor == "propriétaire" else ActorKind.AGENT,
            action="pricing.approval.revoke",
            entity="price_approval",
            entity_id=approval_id,
            dry_run=False,
            payload={"reason": body.reason, "revoked": revoked},
        )
        if not revoked:
            raise HTTPProblem(404, f"approbation {approval_id} inconnue ou déjà retirée")
        return _ok({"revoked": approval_id})

    # -- stock ----------------------------------------------------------------------
    @app.post("/stock/sellable")
    async def stock_sellable(request: Request) -> PokeshopJSONResponse:
        """Stock vendable local (jamais le stock fournisseur)."""
        require_api(request)
        body = await _body(request, SellableIn)
        if body.sku:
            level = svc.stock.level(body.sku)
            return _ok({"sku": body.sku, "sellable": level.sellable, "level": level, "source": "registre"})
        if body.on_hand is None:
            raise HTTPProblem(422, "fournir sku, ou on_hand (+ reserved, damaged, safety)")
        value = sellable_local(body.on_hand, body.reserved, body.damaged, body.safety)
        return _ok({"sellable": value, "source": "calcul"})

    @app.post("/stock/receive")
    async def stock_receive(request: Request) -> PokeshopJSONResponse:
        """Réception physique en stock local (registre persisté) ; idempotente par (SKU, référence).

        Rôle ``operations-sav`` (ou propriétaire) : l'acteur est journalisé avec la réception ; un coût
        historique de réception (``POST /costs/movements``) doit la citer depuis un **autre** jeton.
        """
        principal = require_api(request)
        _persistence_guard(PersistentStockRegistry.STREAM, "journal du stock local")
        body = await _body(request, StockReceiveIn)
        actor = principal.name
        try:
            level, replayed = svc.stock.receive_once(body.sku, body.qty, body.ref, at=svc.clock(), recorded_by=actor)
        except StockPersistenceError:
            raise
        except PokeshopError as exc:  # même référence, autre quantité
            raise HTTPProblem(409, str(exc)) from None
        svc.audit.append(
            actor=actor,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="stock.receive",
            entity="stock",
            entity_id=body.sku,
            dry_run=False,
            payload={"qty": body.qty, "ref": body.ref, "replayed": replayed, "version": level.version},
            idempotency_key=f"{body.sku}:{body.ref}",
        )
        return _ok({"level": level, "sellable": level.sellable, "replayed": replayed})

    @app.post("/stock/reorder-proposal")
    async def reorder_proposal(request: Request) -> PokeshopJSONResponse:
        """Panier fournisseur **à valider** ; gels du stop-loss et réserve de trésorerie appliqués.

        Budget stock total : règles signées (et mandat signé actif, le plus bas) ; exposition par
        extension : photo stop-loss acceptée, l'appelant ne pouvant qu'y **ajouter** ; exceptions de
        plafond (C18) : jeton propriétaire. État du stop-loss indisponible => 409 (fermé par défaut).
        """
        principal = require_api(request)
        body = await _body(request, ReorderIn)
        actor = actor_of(principal, body.actor, request, route="reorder")
        if body.cap_exceptions:
            token = owner_token(request, required=True, route="reorder.cap_exceptions")
            if not verify_owner_token(token, cfg.owner_token_sha256):
                svc.audit.append(
                    actor="inconnu",
                    actor_kind=ActorKind.AGENT,
                    action="reorder.cap_exceptions.owner_token_refused",
                    entity="owner_token",
                    entity_id=request.url.path,
                    dry_run=False,
                    payload={"motif": "jeton invalide"},
                )
                raise HTTPProblem(403, "exceptions de plafond (C18) : jeton propriétaire valide requis")
        now = svc.clock()
        gate = svc.gate.authorize("PROPOSE_PURCHASE", dry_run=False, actor=actor, workflow="reassort")
        if not gate.allowed and gate.has("STOPLOSS_GLOBAL_FREEZE"):
            raise HTTPProblem(423, "stop-loss global : aucune proposition d'achat", gate=gate)
        status = gate.stoploss
        if status is None:
            raise HTTPProblem(
                409,
                f"état du stop-loss indisponible ({svc.gate.last_stoploss_error}) : gels inconnus, aucune proposition",
            )
        reserve = (
            svc.mandate.cash_reserve_chf
            if svc.mandate
            else (svc.stoploss_config.cash.reserve_chf if svc.stoploss_config else Decimal("1600"))
        )
        stock_budget = svc.rules.stock.stock_budget_chf
        if svc.mandate is not None and svc.mandate.is_active(now) and svc.mandate.stock_budget_chf is not None:
            stock_budget = min(stock_budget, svc.mandate.stock_budget_chf)
        exposure: dict[str, Decimal] = {}
        if svc.stoploss_state is not None:
            for item in svc.stoploss_state.extensions:
                exposure[item.extension] = item.stock_value_at_cost + item.on_order_value
        for ext, value in body.extension_exposure.items():  # l'appelant ne peut qu'aggraver l'exposition
            exposure[ext] = max(exposure.get(ext, Decimal("0")), value)
        blocked_ext = set(status.no_reorder_extensions)
        blocked_prod = set(status.blocked_products)
        # Stop-loss trésorerie : plus aucun achat => budget utilisable nul (motif CASH_RESERVE).
        budget = Decimal("0") if status.purchases_and_ads_frozen else body.budget_available
        proposal = propose_reorder(
            body.candidates,
            budget_available=budget,
            stock_budget_total=stock_budget,
            now=now,
            extension_exposure=exposure,
            extension_cap_pct=svc.rules.stock.extension_budget_cap,
            cap_exceptions=body.cap_exceptions,
            max_age=svc.rules.stock.max_age,
            rules_version=svc.rules.rules_version,
            blocked_extensions=sorted(blocked_ext),
            blocked_products=sorted(blocked_prod),
            cash_reserve_chf=reserve,
        )
        # Registre des propositions du moteur : seule référence admise pour adosser un achat de stock.
        registered = svc.proposals.register(proposal, recorded_by=actor) if proposal.lines else False
        svc.audit.append(
            actor=actor,
            actor_kind=ActorKind.AGENT,
            action="reorder.proposal",
            entity="purchase_proposal",
            entity_id=proposal.inputs_hash[:16],
            dry_run=True,
            autonomy_level=gate.current_level,
            payload={
                "lines": len(proposal.lines),
                "total_chf": proposal.total_cost_chf,
                "gate": list(gate.reasons),
                "stock_budget_chf": stock_budget,
                "cap_exceptions": dict(body.cap_exceptions),
            },
        )
        return _ok(
            {
                "proposal": proposal,
                "gate": gate,
                "stoploss_known": True,
                "stock_budget_chf": stock_budget,
                "justification_ref": proposal.inputs_hash if proposal.lines else None,
                "registered": registered,
            }
        )

    # -- imports --------------------------------------------------------------------
    def _source(path_text: str) -> Path:
        base = cfg.imports_dir.resolve()
        candidate = (base / path_text).resolve()
        if not candidate.is_relative_to(base):
            raise HTTPProblem(403, "chemin hors du dossier d'import autorisé")
        if not candidate.is_file():
            raise HTTPProblem(404, f"fichier introuvable dans le dossier d'import : {path_text}")
        return candidate

    @app.post("/imports/{supplier}/run")
    async def import_run(supplier: str, request: Request) -> PokeshopJSONResponse:
        """Import **en simulation** ; rapport interne (peut citer des prix B2B : jamais publié).

        Comparé à la référence « dernier import » du fournisseur (prix ×10 ou ÷10, devise ou HT/TTC
        changés, import incomplet, contenu identique non daté), mise à jour s'il est accepté.
        """
        principal = require_api(request)
        if not _SUPPLIER_RE.match(supplier):
            raise HTTPProblem(422, "identifiant fournisseur invalide")
        _persistence_guard(ImportBaselineStore.STREAM, "références « dernier import »")
        body = await _body(request, ImportIn)
        result = run_import(
            supplier,
            _source(body.source_path),
            now=svc.clock(),
            dry_run=True,
            source_ts=body.source_ts,
            baseline=svc.baselines.get(supplier),
        )
        svc.baselines.update(result)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT,
            action="import.run",
            entity="supplier",
            entity_id=supplier,
            dry_run=True,
            payload={
                "status": result.status,
                "rows": result.rows_read,
                "accepted": result.accepted_count,
                "quarantined": result.quarantined_count,
                "sha256": result.snapshot.checksum_sha256,
            },
        )
        return _ok(
            {
                "supplier_id": result.supplier_id,
                "status": result.status,
                "dry_run": True,
                "fictif": result.fictif,
                "rows_read": result.rows_read,
                "accepted": result.accepted_count,
                "quarantined": result.quarantined_count,
                "reason_counts": result.reason_counts(),
                "escalation": result.escalation,
                "source_ts": result.effective_source_ts,
                "baseline_known": svc.baselines.get(result.supplier_id) is not None,
                "report_markdown": result.report_markdown(),
            }
        )

    # -- publication ------------------------------------------------------------------
    def _table(fictif: bool) -> Any:
        if fictif:
            return load_extension_table([DEFAULT_EXTENSIONS_PATH, FICTIF_EXTENSIONS_PATH])
        return load_extension_table()

    @app.post("/publish/preview")
    async def publish_preview(request: Request) -> PokeshopJSONResponse:
        """Aperçu de la charge ``productSet`` **publique** (aucun coût dans la réponse).

        Approbation de prix : registre du moteur uniquement ; statut de stock : recalculé depuis le
        registre du stock local (une fiche de précommande sans allocation connue reste en rupture).
        """
        require_api(request)
        body = await _body(request, PublishPreviewIn)
        now = svc.clock()
        decision = None
        params = params_for(body.quote.profile if body.quote is not None else None)
        if body.quote is not None:
            q = body.quote
            decision = decide_price(
                q.cost_chf,
                params,
                q.market_ref,
                q.current_public or body.reference_price_24h,
                q.unknown_fields,
                candidate_price=q.candidate_price,
                small_product=q.small_product,
                offer_stale=q.offer_stale,
                previous_cost=q.previous_cost,
            )
        status, _ = svc.gate.stoploss_status()
        listing = body.listing
        blocked = body.stoploss_blocked or (status is not None and listing.product_key in status.blocked_products)
        _persistence_guard(CatalogApprovalBook.STREAM, "registre des validations de fiches")
        _persistence_guard(ShopPublicationBook.STREAM, "registre des fiches publiées")
        pid = listing.product_key  # clé canonique (revue R4, R3-NEW-01 : product_id = listing.product_key)
        known = svc.publications.get(pid)
        plan = build_publication(
            listing,
            decision,
            max_daily_change=params.max_daily_price_change,
            reference_price_24h=body.reference_price_24h,
            price_validation=svc.price_approvals.active_for(listing.product_key, now),
            params=params,
            now=now,
            stoploss_blocked=blocked,
            quarantined=svc.incidents.is_quarantined(listing.product_key),
            sensitive_terms=body.sensitive_terms,
            table=_table(listing.fictif),
            stock_status=stock_status_for(listing, local_sellable=svc.stock.sellable(listing.public_sku)),
            published=known.state() if known is not None else None,  # registre du moteur, jamais la fiche
            validations=svc.catalog_approvals.get(pid),  # registre de la propriétaire
        )
        return _ok({"plan": plan, "dry_run": True})

    # -- catalogue validé et frais (registres lus par /sync/run) ----------------------------------
    @app.post("/catalog/items")
    async def catalog_items(request: Request) -> PokeshopJSONResponse:
        """Enregistre un lot du catalogue validé (produit, liens fournisseur, fiche) : tout ou rien, persisté."""
        principal = require_api(request)
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        body = await _body(request, CatalogItemsIn)
        now = svc.clock()
        takeover = _catalog_takeover(body.items)
        if takeover and not principal.owner:
            svc.audit.append(
                actor=principal.name, actor_kind=ActorKind.AGENT, action="catalog.items.takeover_refused",
                entity="catalog", entity_id=",".join(sorted(takeover)), dry_run=False, payload={"motifs": takeover},
            )  # fmt: skip
            raise HTTPProblem(
                409,
                "nouvel identifiant qui reprend une référence existante : " + " ; ".join(takeover.values())
                + " — ré-identifier une référence est un acte de la propriétaire (jeton propriétaire)",
                takeover=takeover,
            )
        entries = [
            CatalogEntry(
                product_id=i.product_id,
                supplier_links=tuple(i.supplier_links),
                listing=i.listing,
                recorded_by=principal.name,
                recorded_at=now,
            )
            for i in body.items
        ]
        changed = svc.catalog.upsert(entries)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="catalog.items",
            entity="catalog",
            entity_id=str(len(entries)),
            dry_run=False,
            payload={"product_ids": [e.product_id for e in entries], "changed": changed},
        )
        return _ok({"received": len(entries), "changed": changed, "total": len(svc.catalog.entries())})

    def _catalog_takeover(items: list[CatalogItemIn]) -> dict[str, str]:
        """Nouveaux identifiants qui reprendraient une référence existante (revue R4, R3-NEW-01) : pid -> motif.

        Un nouveau ``product_id`` ne reprend jamais le SKU boutique ni le handle d'une fiche déjà enregistrée
        (même déplacée dans le même lot), ni l'identité produit d'une référence en quarantaine, bloquée par le
        stop-loss produit, ou dont l'état du stop-loss est inconnu (fermé par défaut) : sinon quarantaine et
        validation de la propriétaire ne la suivraient pas.
        """
        existing = {e.product_id: e for e in svc.catalog.entries()}
        status, _ = svc.gate.stoploss_status()
        blocked = set(status.blocked_products) if status is not None else None
        out: dict[str, str] = {}
        for item in items:
            if item.product_id in existing:
                continue
            listing = item.listing
            for pid, entry in sorted(existing.items()):
                held = svc.incidents.is_quarantined(pid) or blocked is None or bool(entry.keys & blocked)
                if entry.listing.public_sku == listing.public_sku:
                    out[item.product_id] = f"{item.product_id} reprend le SKU {listing.public_sku} de {pid}"
                elif entry.listing.handle is not None and entry.listing.handle == listing.handle:
                    out[item.product_id] = f"{item.product_id} reprend le handle {listing.handle} de {pid}"
                elif held and entry.listing.identity == listing.identity:
                    out[item.product_id] = (
                        f"{item.product_id} reprend l'identité de {pid} (en quarantaine, bloquée ou état du stop-loss inconnu)"
                    )
                else:
                    continue
                break
        return out

    @app.post("/catalog/cost-inputs")
    async def catalog_cost_inputs(request: Request) -> PokeshopJSONResponse:
        """Frais connus d'un fournisseur (fret, douane, TVA import, quantité) ; jamais de taux de change."""
        principal = require_api(request)
        _persistence_guard(CatalogRegistry.COSTS_STREAM, "frais fournisseurs")
        body = await _body(request, CostInputsIn)
        if not _SUPPLIER_RE.match(body.supplier_id):
            raise HTTPProblem(422, "identifiant fournisseur invalide")
        entry = SupplierCostEntry(**body.model_dump(), recorded_by=principal.name, recorded_at=svc.clock())
        changed = svc.catalog.set_costs(entry)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="catalog.cost_inputs",
            entity="supplier",
            entity_id=entry.supplier_id,
            dry_run=False,
            payload={"changed": changed, "currency": entry.currency, "source": entry.source},
        )
        return _ok({"cost_inputs": entry, "changed": changed})

    @app.get("/catalog")
    def catalog_list(request: Request) -> PokeshopJSONResponse:
        """Catalogue validé et frais en vigueur (interne)."""
        require_api(request)
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        return _ok(
            {
                "products": [
                    {
                        "product_id": e.product_id,
                        "product_key": e.listing.product_key,
                        "public_sku": e.listing.public_sku,
                        "extension": e.listing.identity.extension,
                        "supplier_links": e.supplier_links,
                        "fictif": e.listing.fictif,
                        "recorded_by": e.recorded_by,
                        "recorded_at": e.recorded_at,
                        "listing_sha256": listing_digest(e.listing),
                    }
                    for e in svc.catalog.entries()
                ],
                "cost_inputs": svc.catalog.all_costs(),
            }
        )

    @app.post("/catalog/approvals", status_code=201)
    async def catalog_approval(request: Request) -> PokeshopJSONResponse:
        """Valide une fiche du catalogue : **propriétaire uniquement** (jeton propriétaire, journal persisté).

        Seule voie de ``approved`` (mises à jour automatiques au niveau 2), ``content_validated`` (contenu
        confirmé par écrit par le fournisseur) et ``category_rule_validated`` (publication automatique au
        niveau 3) — jamais un champ de ``POST /catalog/items`` ni du corps de ``/sync/run`` (422). La
        validation porte sur le contenu en vigueur de la fiche (empreinte) : une fiche modifiée ensuite par
        l'agent catalogue n'est plus validée (revue R2-NEW-05 : « catalogue ne valide pas ses propres fiches »).
        """
        require_api(request)
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        _persistence_guard(CatalogApprovalBook.STREAM, "registre des validations de fiches")
        body = await _body(request, CatalogApprovalIn)
        entry = next((e for e in svc.catalog.entries() if e.product_id == body.product_id), None)
        if entry is None:
            raise HTTPProblem(409, f"{body.product_id} : fiche absente du catalogue validé (POST /catalog/items)")
        digest = listing_digest(entry.listing)
        if body.listing_sha256 is not None and body.listing_sha256 != digest:
            raise HTTPProblem(409, "fiche modifiée depuis votre examen : relire GET /catalog/approvals", listing_sha256=digest)
        try:
            approval = ListingApproval(
                product_key=entry.product_id,
                listing_sha256=digest,
                approved=body.approved,
                content_validated=body.content_validated,
                category_rule_validated=body.category_rule_validated,
                reason=body.reason,
                approved_at=svc.clock(),
            )
        except ValidationError as exc:
            raise HTTPProblem(422, "validation invalide", details=to_jsonable(exc.errors(include_url=False))) from None
        svc.catalog_approvals.record(approval)
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="catalog.approval",
            entity="product",
            entity_id=approval.product_key,
            dry_run=False,
            autonomy_level=int(svc.autonomy.level),
            payload={
                "approved": approval.approved,
                "content_validated": approval.content_validated,
                "category_rule_validated": approval.category_rule_validated,
                "listing_sha256": digest,
                "listing_recorded_by": entry.recorded_by,
                "reason": approval.reason,
            },
        )
        return _ok({"approval": approval}, 201)

    @app.get("/catalog/approvals")
    def catalog_approvals_list(request: Request) -> PokeshopJSONResponse:
        """Validations de fiches de la propriétaire et fiches à examiner (empreinte du contenu en vigueur)."""
        require_api(request)
        _persistence_guard(CatalogApprovalBook.STREAM, "registre des validations de fiches")
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        rows = []
        for e in svc.catalog.entries():
            approval = svc.catalog_approvals.get(e.product_id)
            digest = listing_digest(e.listing)
            rows.append(
                {
                    "product_id": e.product_id,
                    "listing_sha256": digest,
                    "recorded_by": e.recorded_by,
                    "approval": approval,
                    "current": approval is not None and approval.listing_sha256 == digest,
                }
            )
        return _ok({"products": rows})

    def _owner_rated(entry: SupplierCostEntry, mapping: Any, now: datetime) -> OfferCostInputs:
        """Frais + taux de la propriétaire (``POST /fx/rates``) seulement ; sans taux : coût incomplet (brouillon)."""
        rate = svc.fx_rates.reference(entry.currency, now) if entry.currency != "CHF" else None
        return entry.to_offer_inputs(
            allowed_currencies=tuple(mapping.allowed_currencies),
            fx_rate=rate.rate_to_chf if rate is not None else None,
            fx_source=rate.source if rate is not None else None,
            fx_date=rate.rate_date if rate is not None else None,
        )

    def _registry_cost_inputs(mapping: Any, now: datetime) -> dict[str, OfferCostInputs]:
        """Frais du registre ; taux de la propriétaire (``POST /fx/rates``) seulement, sinon coût incomplet."""
        entry = svc.catalog.costs(mapping.supplier_id)
        if entry is None:
            return {}
        return {mapping.supplier_id: _owner_rated(entry, mapping, now)}

    def _body_cost_inputs(
        body: dict[str, SyncCostInputsIn], mapping: Any, now: datetime, actor: str
    ) -> dict[str, OfferCostInputs]:
        """Frais du corps (simulation) avec le taux de la propriétaire, jamais un taux de l'appelant."""
        out: dict[str, OfferCostInputs] = {}
        for supplier_id, item in body.items():
            entry = SupplierCostEntry(
                supplier_id=supplier_id,
                **item.model_dump(),
                source="corps de POST /sync/run (simulation)",
                recorded_by=actor,
                recorded_at=now,
            )
            out[supplier_id] = _owner_rated(entry, mapping, now)
        return out

    @app.post("/sync/run")
    async def sync_run(request: Request) -> PokeshopJSONResponse:
        """Cycle fournisseur → site en 8 étapes ; simulation sauf ``dry_run: false`` (gouvernance appliquée).

        Approbations de prix : registre du moteur (jamais le corps) ; référence « dernier import »
        persistée ; écriture réelle sans référence (premier import du fournisseur) : 409. Catalogue :
        corps, sinon registre ; aucun des deux : 409. ``clean`` n'est vrai que pour un cycle **PROPRE**
        (aucune erreur critique **et** au moins une offre au coût rendu calculé) : un cycle **VIDE**
        n'est jamais compté pour la recette (``GET /sync/history``).
        """
        principal = require_api(request)
        body = await _body(request, SyncIn)
        if not _SUPPLIER_RE.match(body.supplier):
            raise HTTPProblem(422, "identifiant fournisseur invalide")
        for stream, what in (
            (ImportBaselineStore.STREAM, "références « dernier import »"),
            (PriceApprovalBook.STREAM, "registre des approbations de prix"),
            (PersistentStockRegistry.STREAM, "journal du stock local"),
            (SyncRunLog.STREAM, "journal des cycles de synchronisation"),
            (ShopPublicationBook.STREAM, "registre des fiches publiées"),
            (FxRateBook.STREAM, "registre des taux de change"),
            (CatalogApprovalBook.STREAM, "registre des validations de fiches"),
        ):
            _persistence_guard(stream, what)
        mapping = load_mapping(body.supplier)
        if not body.dry_run and svc.baselines.get(mapping.supplier_id) is None:
            raise HTTPProblem(
                409,
                f"{mapping.supplier_id} : aucun import précédent connu — lancer d'abord une simulation "
                "(contrôles ×10, import incomplet, devise et HT/TTC impossibles sans référence)",
            )
        now = svc.clock()
        items: list[tuple[str, tuple[SupplierLink, ...], CatalogListing]]
        catalog_source: Literal["corps", "registre"]
        if body.catalog:
            if not body.dry_run:
                # Revue R4 (R3-NEW-01) : une écriture réelle lit toujours le catalogue du registre (clé, validations).
                raise HTTPProblem(
                    409,
                    "catalogue fourni dans le corps : simulation seulement ; une écriture réelle lit le catalogue du "
                    "registre (POST /catalog/items) et les validations de la propriétaire",
                )
            items = [(i.product_id, tuple(i.supplier_links), i.listing) for i in body.catalog]
            catalog_source = "corps"
        else:
            _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
            items = [(e.product_id, e.supplier_links, e.listing) for e in svc.catalog.entries()]
            catalog_source = "registre"
            if not items:
                raise HTTPProblem(
                    409,
                    "catalogue requis : aucun produit validé enregistré (POST /catalog/items) ni fourni dans le "
                    "corps — un cycle sans catalogue n'évalue aucune offre et ne compte pas pour la recette",
                )
        if body.cost_inputs:
            if not body.dry_run:
                raise HTTPProblem(
                    409,
                    "frais fournis dans le corps : simulation seulement ; une écriture réelle lit les frais du "
                    "registre (POST /catalog/cost-inputs) et le taux de la propriétaire (POST /fx/rates)",
                )
            cost_inputs = _body_cost_inputs(dict(body.cost_inputs), mapping, now, principal.name)
            fees_by: dict[str, str] = {}
        else:
            _persistence_guard(CatalogRegistry.COSTS_STREAM, "frais fournisseurs")
            cost_inputs = _registry_cost_inputs(mapping, now)
            registered = svc.catalog.costs(mapping.supplier_id)
            fees_by = {mapping.supplier_id: registered.recorded_by} if registered is not None else {}
        fictif = mapping.fictif or any(listing.fictif for _, _, listing in items)
        table = extension_table_for(mapping, _table(fictif))
        ctx = SyncContext(
            rules=svc.rules,
            catalog_products=[
                CatalogProduct(product_id=pid, identity=listing.identity, supplier_links=links)
                for pid, links, listing in items
            ],
            listings={pid: listing for pid, _, listing in items},
            table=table,
            cost_inputs=cost_inputs,
            market_refs=body.market_refs,
            price_validations=svc.price_approvals.active(now),
            # Validations humaines : registre de la propriétaire seulement, appliquées au contenu exact validé,
            # par clé canonique uniquement (revue R4, R3-NEW-01 : aucun repli sur listing.product_key).
            validations={
                pid: a
                for pid, _, listing in items
                if pid == listing.product_key and (a := svc.catalog_approvals.get(pid)) is not None
            },
            # Revue R5 (R4-DOC-09, R2-NEW-01 b) : un cycle avec catalogue ou frais du corps (simulation) n'inscrit
            # jamais de coût de remplacement ; sinon la provenance des frais du registre est inscrite avec lui.
            record_replacement_costs=catalog_source == "registre" and not body.cost_inputs,
            cost_inputs_recorded_by=fees_by,
        )
        try:
            report = svc.sync.run_supplier_cycle(
                mapping, _source(body.source_path), ctx, now=now, dry_run=body.dry_run, source_ts=body.source_ts
            )
        except BaselinePersistenceError:
            raise
        except SyncError as exc:
            raise HTTPProblem(409, str(exc)) from None
        summary = svc.sync_runs.record(
            SyncRunSummary.from_report(
                report, catalog_source=catalog_source, recorded_by=principal.name, fictif=fictif
            )
        )
        verdict = svc.sync_runs.acceptance()
        return _ok(
            {
                "report": report,
                "clean": summary.status == "PROPRE",
                "cycle_status": summary.status,
                "offers_costed": summary.offers_costed,
                "catalog_source": catalog_source,
                "counted_for_acceptance": verdict.get(summary.run_id, "?") is None,
                "acceptance_exclusion": verdict.get(summary.run_id),
                "consecutive_clean_runs": sum(1 for reason in verdict.values() if reason is None),
                "report_markdown": report.render_markdown(),
            }
        )

    @app.get("/sync/history")
    def sync_history(request: Request, limit: int = 50) -> PokeshopJSONResponse:
        """Cycles de synchronisation persistés et cycles PROPRES consécutifs (critère de recette BP §13)."""
        require_api(request)
        _persistence_guard(SyncRunLog.STREAM, "journal des cycles de synchronisation")
        counted = svc.sync_runs.counted_runs()
        streak = len(counted)
        verdict = svc.sync_runs.acceptance()
        runs = svc.sync_runs.runs(limit=max(1, min(limit, 500)))
        return _ok(
            {
                "consecutive_clean_runs": streak,
                "target": CLEAN_RUNS_TARGET,
                "criterion_met": streak >= CLEAN_RUNS_TARGET,
                "definition": ACCEPTANCE_DEFINITION,
                "counted_run_ids": [r.run_id for r in counted],
                "runs": [
                    {
                        **r.model_dump(mode="json"),
                        "counted_for_acceptance": verdict.get(r.run_id, "?") is None,
                        "acceptance_exclusion": verdict.get(r.run_id),
                    }
                    for r in runs
                ],
            }
        )

    # -- incidents --------------------------------------------------------------------
    @app.get("/incidents")
    def incidents_list(
        request: Request, status: IncidentStatus | None = None, open_only: bool = False
    ) -> PokeshopJSONResponse:
        """Incidents (filtre par statut), quarantaines et suspensions en cours."""
        require_api(request)
        return _ok(
            {
                "incidents": svc.incidents.list(status=status, open_only=open_only),
                "quarantined": svc.incidents.quarantined(),
                "suspended": svc.incidents.suspended(),
                "summary": svc.incidents.summary(),
            }
        )

    @app.post("/incidents", status_code=201)
    async def incidents_open(request: Request) -> PokeshopJSONResponse:
        """Ouvre un incident (confinement, notification cause + action proposée)."""
        principal = require_api(request)
        body = await _body(request, IncidentIn)
        actor = actor_of(principal, body.actor, request, route="incidents.open")
        # Revue R4 (R3-DOC-04) : « simulation » n'est admis que si le moteur est lui-même en simulation
        # (POKESHOP_DRY_RUN) ; écritures réelles activées => incident réel (confinement, test sur cycle réel).
        simulation = body.simulation and not cfg.real_writes_enabled
        if body.simulation and not simulation:
            svc.audit.append(
                actor=actor, actor_kind=ActorKind.AGENT, action="incidents.simulation_ignored", entity="incident",
                entity_id=body.product_key or body.supplier_id or body.workflow or "*", dry_run=False,
                payload={"motif": "écritures réelles activées : un incident déclaré en simulation est traité comme réel"},
            )  # fmt: skip
        # Données FICTIVES : déduit par le moteur (fiche du catalogue, dictionnaire du fournisseur), jamais déclaré.
        fictif = False
        if body.product_key is not None:
            entry = next((e for e in svc.catalog.entries() if body.product_key in (e.product_id, e.listing.product_key)), None)
            fictif = entry is not None and entry.listing.fictif
        if body.supplier_id is not None and _SUPPLIER_RE.match(body.supplier_id):
            try:
                fictif = fictif or load_mapping(body.supplier_id).fictif
            except (MappingError, OSError):
                pass
        incident = svc.incidents.open(
            cause=body.cause,
            code=body.code,
            kind=body.kind,
            severity=body.severity,
            scope=body.scope,
            proposed_action=body.proposed_action,
            product_key=body.product_key,
            supplier_id=body.supplier_id,
            workflow=body.workflow,
            details=body.details,
            actor=actor,
            actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
            simulation=simulation,
            fictif=fictif,
        )
        svc.gate.invalidate()
        return _ok({"incident": incident, "notification": svc.incidents.notification_for(incident.incident_id)}, 201)

    @app.post("/incidents/{incident_id}/test")
    async def incidents_test(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Enregistre le test de correction (préalable à toute reprise).

        Un test **réussi** est une valeur décisive (il ouvre la reprise) — revue R3 (NEW-01) : soit la
        propriétaire l'atteste (jeton propriétaire), soit le rôle ``qa-conformite`` (liste fermée
        :data:`pokeshop.authz.INCIDENT_TEST_ATTESTERS`), **différent de l'ouvreur**. ``test_ref`` désigne alors
        un cycle ``POST /sync/run`` du **journal persisté** (``sync_runs``) : simulation PROPRE, postérieure à
        l'ouverture, **lancée par un autre principal que l'attestant**, avec le **catalogue du registre**
        (jamais celui du corps), sur des données **réelles** (non FICTIVES, source datée) sauf incident sur données
        FICTIVES ou **déclaré** ``simulation: true`` alors que le moteur est en simulation (revue R5, R3-DOC-04 : un
        incident sur données réelles ouvert sans ce drapeau exige un cycle réel, même moteur en simulation), et
        portant sur le **fournisseur** de l'incident (quand il est
        connu, même si une référence l'est aussi) et sur sa **référence**. Un test échoué peut être déclaré
        par tout rôle nommé.
        """
        principal = require_api(request)
        body = await _body(request, IncidentTestIn)
        incident = svc.incidents.get(incident_id)
        token = request.headers.get(OWNER_TOKEN_HEADER)
        owner = principal.owner or owner_verified(request)
        if token and not owner:
            raise HTTPProblem(403, "jeton propriétaire invalide")
        actor = "propriétaire" if owner else actor_of(principal, body.actor, request, route="incidents.test")
        if body.passed and not owner:
            status_code, problem = 409, None
            if principal.role not in authz.INCIDENT_TEST_ATTESTERS:
                status_code = 403
                problem = (
                    f"test réussi déclaré par « {principal.name} » : seul le rôle qa-conformite (jeton nommé, "
                    "différent de l'ouvreur) ou la propriétaire atteste un test de correction"
                )
            elif incident.opened_by in (principal.name, f"agent:{principal.name}"):
                status_code = 403
                problem = "test auto-attesté : l'ouvreur de l'incident ne l'atteste jamais (propriétaire requise)"
            else:
                _persistence_guard(SyncRunLog.STREAM, "journal des cycles de synchronisation")
                run = svc.sync_runs.get(body.test_ref)
                synthetic = incident.simulation or incident.fictif
                if run is None:
                    problem = "test_ref doit être l'identifiant d'un cycle POST /sync/run enregistré par ce service"
                elif not run.dry_run or run.status != "PROPRE":
                    problem = (
                        f"le cycle cité n'est pas une simulation PROPRE (statut {run.status}, "
                        f"{'simulation' if run.dry_run else 'écriture réelle'}) : aucune offre évaluée ou erreur critique"
                    )
                elif run.started_at < incident.opened_at:
                    problem = "le cycle cité précède l'ouverture de l'incident : rejouer après la correction"
                elif run.recorded_by in (principal.name, f"agent:{principal.name}"):
                    problem = "le cycle cité a été lancé par l'attestant : un autre principal doit le lancer"
                elif run.catalog_source != "registre":
                    problem = "le cycle cité utilise un catalogue fourni dans le corps : catalogue du registre exigé"
                elif not synthetic and run.acceptance_exclusion() is not None:
                    problem = (
                        f"le cycle cité n'est pas un cycle réel ({run.acceptance_exclusion()}) alors que l'incident "
                        "porte sur des données réelles"
                    )
                elif incident.supplier_id is not None and run.supplier_id != incident.supplier_id:
                    problem = f"le cycle cité ne porte pas sur le fournisseur de l'incident ({incident.supplier_id})"
                elif incident.product_key is not None and incident.product_key not in run.product_ids:
                    problem = f"le cycle cité ne porte pas sur la référence de l'incident ({incident.product_key})"
                elif incident.product_key is None and incident.supplier_id is None and (
                    incident.workflow != WORKFLOW_SUPPLIER_TO_SHOP
                ):
                    problem = (
                        "incident sans référence ni fournisseur hors du workflow fournisseur → site : aucun cycle "
                        "ne le prouve, attestation de la propriétaire requise"
                    )
            if problem is not None:
                svc.audit.append(
                    actor=actor,
                    actor_kind=ActorKind.AGENT,
                    action="incident.test_refused",
                    entity="incident",
                    entity_id=incident_id,
                    dry_run=incident.simulation,
                    payload={"test_ref": body.test_ref, "motif": problem, "token": principal.name},
                )
                raise HTTPProblem(status_code, f"test non vérifiable : {problem}")
        return _ok(
            {
                "incident": svc.incidents.record_test(
                    incident_id,
                    test_ref=body.test_ref,
                    passed=body.passed,
                    actor=actor,
                    actor_kind=ActorKind.PROPRIETAIRE if owner else ActorKind.AGENT,
                )
            }
        )

    @app.post("/incidents/{incident_id}/resume")
    async def incidents_resume(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Reprise après test ; incident critique : jeton de la propriétaire exigé."""
        principal = require_api(request)
        body = await _body(request, ActorIn)
        token = owner_token(request, required=False, route="incidents.resume")
        kind = ActorKind.AGENT
        if token is not None:
            if not verify_owner_token(token, cfg.owner_token_sha256):
                raise HTTPProblem(403, "jeton propriétaire invalide")
            kind = ActorKind.PROPRIETAIRE
        # Reprise par un agent : « agent:<acteur> » (jamais un nom qui ferait croire à la propriétaire).
        actor = "propriétaire" if kind is ActorKind.PROPRIETAIRE else (
            "agent:" + actor_of(principal, body.actor, request, route="incidents.resume")
        )
        incident = svc.incidents.resume(incident_id, actor=actor, actor_kind=kind)
        svc.gate.invalidate()
        return _ok({"incident": incident})

    @app.post("/incidents/{incident_id}/close")
    async def incidents_close(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Clôture d'un incident résolu."""
        principal = require_api(request)
        body = await _body(request, ActorIn)
        actor = actor_of(principal, body.actor, request, route="incidents.close")
        return _ok({"incident": svc.incidents.close(incident_id, actor=actor)})

    # -- autonomie ----------------------------------------------------------------------
    @app.get("/autonomy")
    def autonomy_get(request: Request) -> PokeshopJSONResponse:
        """Niveau en vigueur, historique et niveau requis par action."""
        require_api(request)
        level = svc.autonomy.level
        return _ok(
            {
                "level": int(level),
                "label": LEVEL_LABELS_FR[level],
                "state": svc.autonomy.state,
                "history": svc.autonomy.history(),
                "required_levels": {a.value: int(lv) for a, lv in REQUIRED_LEVEL.items()},
                "actions_fr": {a.value: ACTION_LABELS_FR[a] for a in REQUIRED_LEVEL},
                "protective_actions": sorted(a.value for a in PROTECTIVE_ACTIONS),
            }
        )

    @app.post("/autonomy")
    async def autonomy_set(request: Request) -> PokeshopJSONResponse:
        """Abaisser (tout agent) ou relever d'un cran (propriétaire, jeton distinct)."""
        principal = require_api(request)
        body = await _body(request, AutonomyIn)
        if body.level > int(svc.autonomy.level):
            token = owner_token(request, required=True, route="autonomy.raise")
            actor = "propriétaire" if owner_verified(request) else actor_of(principal, body.actor, request,
                                                                             route="autonomy.raise")  # fmt: skip
            state = svc.autonomy.raise_level(body.level, owner_token=token or "", reason=body.reason, actor=actor)
        else:
            actor = actor_of(principal, body.actor, request, route="autonomy.lower")
            state = svc.autonomy.lower(body.level, actor=actor, role="AGENT", reason=body.reason)
        svc.gate.invalidate()
        return _ok({"state": state, "label": LEVEL_LABELS_FR[AutonomyLevel(state.level)]})

    # -- stop-loss --------------------------------------------------------------------------
    def _require_engine() -> StopLossEngine:
        if svc.stoploss_engine is None:
            raise HTTPProblem(
                503, "stop-loss indisponible : " + svc.load_errors.get("stoploss", "configuration absente")
            )
        return svc.stoploss_engine

    @app.post("/stoploss/state")
    async def stoploss_state(request: Request) -> PokeshopJSONResponse:
        """Dépose une photo d'activité (relevé de la propriétaire) puis l'évalue — **propriétaire seule**.

        Revue R4 (R3-NEW-03) : plus aucune photo déclarée par un rôle d'automatisation (``n8n-07-stoploss`` ne
        fait que demander la photo **construite par le moteur**, ``POST /stoploss/state/refresh``). Le cash
        déposé est **recoupé** avec les derniers relevés du connecteur de trésorerie (PayPal + banque) : écart
        => 409, photo non vérifiable, la précédente reste en vigueur (fermé par défaut).

        La photo ne déclare **jamais** de mouvements de capital (``capital_movements`` non vide : 422) :
        apports et retraits sont ceux du registre de la propriétaire (``POST /capital/movements``) à la date
        de la photo (revue SEC-06). Elle est d'abord évaluée à part : refusée (périmée, datée du futur, sans
        apport ou avec des apports en baisse : fermé par défaut), elle ne remplace **jamais** la dernière
        photo valide (409). Plafond jour pub et budget stock sont ceux du moteur (mandat signé actif,
        règles), jamais ceux postés (``overridden`` liste les écarts). Acceptée, elle est enregistrée
        (journal d'état ``stoploss_photo``, avec l'acteur déduit du jeton) avant de devenir la photo en vigueur.
        """
        principal = require_api(request)
        engine = _require_engine()
        posted = await _body(request, StopLossState)
        if svc.paypal_balance is not None and svc.bank_balance is not None:
            readings = svc.paypal_balance.balance_chf + svc.bank_balance.balance_chf
            if posted.net_worth.cash_chf != readings:
                svc.audit.append(
                    actor=principal.name, actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                    action="stoploss.state.cash_mismatch_refused", entity="stoploss", entity_id="photo", dry_run=False,
                    payload={"posted_cash_chf": posted.net_worth.cash_chf, "readings_chf": readings},
                )  # fmt: skip
                raise HTTPProblem(
                    409,
                    f"photo non vérifiable : cash déposé {posted.net_worth.cash_chf} CHF ≠ relevés du connecteur de "
                    f"trésorerie {readings} CHF (PayPal + banque) — utiliser POST /stoploss/state/refresh",
                    previous_photo_kept=svc.stoploss_state is not None,
                )
        if posted.capital_movements:
            # Revue SEC-06 : un faux retrait réduisait le capital de référence et taisait le gel global.
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.AGENT,
                action="stoploss.state.capital_movements_refused",
                entity="stoploss",
                entity_id="photo",
                dry_run=False,
                payload={"movements": [m.movement_id for m in posted.capital_movements]},
            )
            raise HTTPProblem(
                422,
                "capital_movements interdit dans la photo : apports et retraits viennent uniquement du registre de "
                "la propriétaire (POST /capital/movements, jeton propriétaire)",
                previous_photo_kept=svc.stoploss_state is not None,
            )
        return _accept_photo(principal, engine, posted, origin="déposée")

    def _accept_photo(
        principal: Principal,
        engine: StopLossEngine,
        posted: StopLossState,
        *,
        origin: str,
        sources: dict[str, Any] | None = None,
        before_accept: Callable[[StopLossState], None] | None = None,
    ) -> PokeshopJSONResponse:
        """Évalue à part, enregistre puis met en vigueur une photo (déposée ou construite par le moteur).

        Apports et retraits : **toujours** ceux du registre de la propriétaire à la date de la photo,
        jamais ceux d'une photo (revue SEC-06). Publicité : par (campagne, jour), le MAX entre la dépense
        de la photo et les paiements pub **engagés** (approuvés ou exécutés) du registre du mandat (revue R4, R2-NEW-03).
        """
        now = svc.clock()
        body, overridden = _authoritative_photo(engine, posted, now)
        try:
            engine.validate_photo(body, now)
        except StopLossError as exc:
            raise HTTPProblem(
                409, f"photo refusée : {exc}", previous_photo_kept=svc.stoploss_state is not None
            ) from None
        if before_accept is not None:
            before_accept(body)  # ex. point zéro posé avant la première évaluation (revue R2-ADV-01)
        with svc.lock:
            try:
                svc.photo_journal.append(
                    {"state": body.model_dump(mode="json"), "accepted_at": now, "posted_by": principal.name,
                     "origin": origin}
                )  # fmt: skip
            except StateStoreError as exc:
                raise HTTPProblem(
                    503, f"photo non enregistrée ({exc}) : la photo précédente reste en vigueur"
                ) from None
            svc.stoploss_state = body
            svc.photo_poster = principal.name
        svc.gate.invalidate()
        status, triggers = svc.gate.stoploss_status()
        _, incident_id = svc.gate.enforce(actor="workflow:stop-loss")
        if status is None:
            raise HTTPProblem(
                503, f"stop-loss non évaluable : {svc.gate.last_stoploss_error}", incident_id=incident_id
            )
        content: dict[str, Any] = {
            "status": status,
            "triggers": triggers,
            "incident_id": incident_id,
            "overridden": overridden,
            "origin": origin,
        }
        if sources is not None:
            content["sources"] = sources
            content["net_worth_chf"] = net_worth(body.net_worth, engine.config).total
            content["cash_available_chf"] = body.cash_available_chf
        return _ok(content)

    @app.post("/stoploss/state/refresh")
    def stoploss_state_refresh(request: Request) -> PokeshopJSONResponse:
        """Construit la photo d'activité **à partir des registres du moteur** puis l'évalue (workflow n8n 07).

        Apports (propriétaire), relevés de cash (connecteurs), stock au coût historique, catalogue,
        prix publics, publicité : aucune valeur décisive n'est postée par l'appelant. Source manquante,
        périmée ou datée du futur : 409 avec la liste (la photo précédente reste en vigueur et se périme).
        """
        principal = require_api(request)
        engine = _require_engine()
        state, sources = _build_photo(engine, principal)
        return _accept_photo(principal, engine, state, origin="registres du moteur", sources=sources)

    def _authoritative_photo(engine: StopLossEngine, posted: StopLossState, now: datetime) -> tuple[StopLossState, list[str]]:
        """Photo avec les valeurs du moteur : apports du registre, publicité ≥ paiements engagés, plafonds signés."""
        _persistence_guard(CapitalRegister.STREAM, "registre des apports")
        _persistence_guard(SpendLedger.STREAM, "registre du mandat")
        # Revue R4 (R2-NEW-03) : paiements pub approuvés (à leur date de décision) ET exécutés.
        committed = committed_ad_payments(svc.spend_ledger.entries(), engine.config.tz)
        posted = posted.replace(
            capital_movements=svc.capital.movements(until=posted.as_of),
            ad_spends=merge_ad_spends(posted.ad_spends, committed, until=posted.as_of.astimezone(engine.config.tz).date()),
        )
        return svc.authoritative_photo(posted, now)

    def _build_photo(engine: StopLossEngine, principal: Principal) -> tuple[StopLossState, dict[str, Any]]:
        """Photo d'activité construite par le moteur depuis ses registres (409 si une source manque)."""
        for stream, what in (
            (CapitalRegister.STREAM, "registre des apports"),
            (CostRegister.STREAM, "registre de coûts historiques"),
            (CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"),
            (AdsActivityRegister.STREAM, "registre de l'activité publicitaire"),
            (OrderRegister.STREAM, "registre des commandes"),  # revue R6 : contribution attribuée dérivée
            (PersistentPriceHistory.STREAM, "historique des prix"),
            (SupplierInvoiceBook.STREAM, "registre des factures fournisseur"),
            (BalanceStatementBook.STREAM, "registre des dettes et créances"),
            (PredropRegistry.STREAM, "registre du pré-drop"),  # réservations payées : dette dérivée
        ):
            _persistence_guard(stream, what)
        now = svc.clock()
        try:
            return build_activity_photo(
                predrop_debts=lambda as_of: svc.predrop.outstanding_debt(as_of=as_of, shipped=_shipped),
                now=now,
                capital=svc.capital,
                paypal=svc.paypal_balance,
                bank=svc.bank_balance,
                balances=svc.balances.debts,
                receivables=svc.balances.receivables,
                incomplete=svc.orders.incomplete_reasons(),
                order_book=svc.orders,  # revue R6 (R5-NEW-01) : contribution attribuée re-dérivée des registres
                costs=svc.costs,
                catalog=svc.catalog,
                price_history=svc.price_history,
                replacement_costs=svc.sync.replacement_costs,
                params=svc.rules.pricing,
                stock_budget_chf=svc.rules.stock.stock_budget_chf,
                ads_daily_cap_chf=None,
                ads=svc.ads,
                max_age=timedelta(hours=engine.config.state_max_age_hours),
                invoices=svc.invoices,
            )
        except PhotoSourcesError as exc:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                action="stoploss.refresh_refused",
                entity="stoploss",
                entity_id="photo",
                dry_run=False,
                payload={"problems": exc.problems},
            )
            raise HTTPProblem(
                409, str(exc), manquantes=exc.problems, previous_photo_kept=svc.stoploss_state is not None
            ) from None

    def _rearm_reference(engine: StopLossEngine) -> dict[str, Any] | None:
        """Valeur à attester au réarmement (valeur nette de la photo en vigueur, date, empreinte)."""
        state = svc.stoploss_state
        if state is None:
            return None
        return {
            "net_worth_chf": net_worth(state.net_worth, engine.config).total,
            "photo_as_of": state.as_of,
            "photo_sha256": canonical_hash(state),
        }

    @app.get("/stoploss/status")
    def stoploss_status(request: Request) -> PokeshopJSONResponse:
        """État des six stop-loss sur la dernière photo ; verrou global toujours rapporté."""
        require_api(request)
        engine = _require_engine()
        status, triggers = svc.gate.stoploss_status()
        reference = _rearm_reference(engine)
        return _ok(
            {
                "available": status is not None,
                "error": svc.gate.last_stoploss_error,
                "signature": engine.config.signature,
                "tightened": engine.config.tightened,
                "photo_posted_by": svc.photo_poster,
                "global_frozen": engine.frozen,
                "latch": engine.latch,
                "restore_hold": engine.restore_hold,
                "rearm_reference": reference,
                "status": status,
                "triggers": triggers,
                "report_markdown": render_report(triggers, now=svc.clock()) if status is not None else None,
                "journal": engine.journal[-20:],
            }
        )

    @app.post("/stoploss/freeze")
    async def stoploss_freeze(request: Request) -> PokeshopJSONResponse:
        """Gel global manuel (tout agent, par précaution) ; levée par la propriétaire seule."""
        principal = require_api(request)
        engine = _require_engine()
        body = await _body(request, FreezeIn)
        actor = actor_of(principal, body.actor, request, route="stoploss.freeze")
        unsaved: str | None = None
        try:
            latch = engine.freeze(actor, body.reason, svc.clock())
        except StopLossPersistenceError as exc:  # gel appliqué en mémoire (fermé par défaut), non enregistré
            latch, unsaved = engine.latch, str(exc)
        svc.autonomy.force_level_one(reason=f"gel manuel : {body.reason}", actor=actor)
        svc.gate.invalidate()
        _, incident_id = svc.gate.enforce(actor=actor)
        svc.audit.append(
            actor=actor,
            actor_kind=ActorKind.AGENT,
            action="stoploss.freeze",
            entity="stoploss",
            entity_id="global",
            dry_run=False,
            payload={"reason": body.reason, "persisted": unsaved is None},
        )
        if unsaved is not None:
            raise HTTPProblem(
                503,
                f"gel appliqué mais NON enregistré : {unsaved} (réparer le stockage)",
                latch=latch,
                incident_id=incident_id,
            )
        return _ok({"latch": latch, "incident_id": incident_id})

    @app.post("/stoploss/rearm")
    async def stoploss_rearm(request: Request) -> PokeshopJSONResponse:
        """Réarmement du gel global : **propriétaire uniquement** (jeton distinct, motif, journal)."""
        require_api(request)
        engine = _require_engine()
        token = owner_token(
            request,
            required=True,
            route="stoploss.rearm",
            on_refused=lambda motif: engine.record_refused_attempt(
                "REARM_REFUSED", now=svc.clock(), actor="inconnu", detail=f"en-tête propriétaire {motif}"
            ),
        )
        body = await _body(request, RearmIn)
        now = svc.clock()
        state = svc.stoploss_state

        def refused(motif: str) -> None:
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="stoploss.rearm_refused",
                entity="stoploss",
                entity_id="global",
                dry_run=False,
                payload={"reason": body.reason, "motif": motif, "reference_chf": body.reference_chf},
            )

        if (
            body.photo_sha256 is not None
            and verify_owner_token(token, cfg.owner_token_sha256)
            and (state is None or canonical_hash(state) != body.photo_sha256)
        ):
            engine.record_refused_attempt(
                "REARM_REFUSED", now=now, actor="propriétaire", detail="photo remplacée depuis l'examen (empreinte)"
            )
            refused("photo remplacée")
            raise HTTPProblem(409, "photo d'activité remplacée depuis votre examen : relire GET /stoploss/status")
        try:
            entry = engine.rearm(
                token or "",
                body.reason,
                now=now,
                state=state,
                rebase=body.rebase,
                attested_reference_chf=body.reference_chf,
            )
        except (RearmRefusedError, RearmReferenceMismatchError) as exc:
            refused(type(exc).__name__)
            raise
        except StopLossPersistenceError:
            raise
        except StopLossError as exc:
            # Revue SEC-07 : sans référence attestée, la réponse donne la valeur ET l'empreinte de la photo à citer.
            raise HTTPProblem(409, str(exc), rearm_reference=_rearm_reference(engine)) from None
        svc.gate.invalidate()
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="stoploss.rearm",
            entity="stoploss",
            entity_id="global",
            dry_run=False,
            autonomy_level=int(svc.autonomy.level),
            payload={
                "reason": body.reason,
                "rebase": body.rebase,
                "reference_chf": body.reference_chf,
                "journal_seq": entry.seq,
            },
        )
        return _ok(
            {
                "journal_entry": entry,
                "latch": engine.latch,
                "autonomy_level": int(svc.autonomy.level),
                "note": "Le niveau d'autonomie n'est pas restauré : décision distincte (POST /autonomy).",
            }
        )

    @app.post("/stoploss/baseline")
    async def stoploss_baseline(request: Request) -> PokeshopJSONResponse:
        """Point zéro du capital engagé : **propriétaire uniquement** (jeton distinct, motif, journal persisté).

        ``with_photo: true`` (revue R2-ADV-01) : sans point zéro antérieur, le moteur construit la **première**
        photo depuis ses registres, pose le point zéro (``reference_chf`` attestée) **puis** évalue la photo,
        de façon atomique : la photo du lancement n'est jamais évaluée sans point zéro (ce qui gèlerait tout
        et rendrait le point zéro impossible). Ordre : apports, soldes, dettes et créances, point zéro avec
        la première photo, puis activation du workflow 07.
        """
        principal = require_api(request)
        engine = _require_engine()
        token = owner_token(request, required=True, route="stoploss.baseline")
        body = await _body(request, BaselineIn)
        now = svc.clock()

        def refused() -> None:
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="stoploss.baseline_refused",
                entity="stoploss",
                entity_id="global",
                dry_run=False,
                payload={"reason": body.reason},
            )

        if body.with_photo:
            if engine.latch.baseline is not None:
                raise HTTPProblem(409, "point zéro déjà posé : with_photo réservé au premier point zéro (sinon réarmement)")
            state, sources = _build_photo(engine, principal)
            entries: list[Any] = []

            def set_first_baseline(photo: StopLossState) -> None:
                try:
                    entries.append(
                        engine.set_baseline(
                            token or "", body.reason, now=now, state=photo, reference_chf=body.reference_chf
                        )
                    )
                except RearmRefusedError:
                    refused()
                    raise

            response = _accept_photo(
                principal, engine, state, origin="registres du moteur (point zéro)", sources=sources,
                before_accept=set_first_baseline,
            )  # fmt: skip
            svc.gate.invalidate()
            svc.audit.append(
                actor="propriétaire",
                actor_kind=ActorKind.PROPRIETAIRE,
                action="stoploss.baseline",
                entity="stoploss",
                entity_id="global",
                dry_run=False,
                autonomy_level=int(svc.autonomy.level),
                payload={"reason": body.reason, "reference_chf": body.reference_chf, "with_photo": True,
                         "journal_seq": entries[0].seq if entries else None},
            )  # fmt: skip
            content = json.loads(response.body)
            content["journal_entry"] = entries[0] if entries else None
            content["latch"] = engine.latch
            return _ok(content, response.status_code)
        if svc.stoploss_state is None:
            raise HTTPProblem(
                409,
                "photo d'activité requise : utiliser with_photo: true pour poser le point zéro avec la première photo "
                "(construite par le moteur, sans évaluation préalable)",
            )
        try:
            entry = engine.set_baseline(
                token or "", body.reason, now=now, state=svc.stoploss_state, reference_chf=body.reference_chf
            )
        except RearmRefusedError:
            refused()
            raise
        svc.gate.invalidate()
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="stoploss.baseline",
            entity="stoploss",
            entity_id="global",
            dry_run=False,
            autonomy_level=int(svc.autonomy.level),
            payload={"reason": body.reason, "reference_chf": body.reference_chf, "journal_seq": entry.seq},
        )
        return _ok({"journal_entry": entry, "latch": engine.latch})

    @app.post("/stoploss/capital-memory/reset")
    async def stoploss_capital_reset(request: Request) -> PokeshopJSONResponse:
        """Réinitialise la mémoire des apports (correction d'un apport erroné) : **propriétaire uniquement**."""
        require_api(request)
        engine = _require_engine()
        token = owner_token(
            request,
            required=True,
            route="stoploss.capital_reset",
            on_refused=lambda motif: engine.record_refused_attempt(
                "REARM_REFUSED", now=svc.clock(), actor="inconnu", detail=f"mémoire des apports : en-tête {motif}"
            ),
        )
        body = await _body(request, CapitalResetIn)
        entry = engine.reset_capital_memory(token or "", body.reason, now=svc.clock())
        svc.gate.invalidate()
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="stoploss.capital_memory_reset",
            entity="stoploss",
            entity_id="global",
            dry_run=False,
            payload={"reason": body.reason, "journal_seq": entry.seq},
        )
        return _ok({"journal_entry": entry, "latch": engine.latch})

    # -- mandat ------------------------------------------------------------------------------
    @app.post("/mandate/check")
    async def mandate_check(request: Request) -> PokeshopJSONResponse:
        """Contrôle d'une demande de dépense (mandat + stop-loss + registres du moteur) ; enregistrement optionnel.

        La trésorerie, le solde PayPal, l'exposition par extension, le taux de change et la proposition
        de réassort viennent des **registres du moteur** ; ``treasury`` du corps est ignoré. Avec un
        jeton nommé, ``requested_by`` doit être le nom du jeton (403 sinon).
        """
        principal = require_api(request)
        body = await _body(request, MandateCheckIn)
        for stream, what in (
            (SpendLedger.STREAM, "registre du mandat"),
            (MandateRevocations.STREAM, "registre des révocations du mandat"),
            (FxRateBook.STREAM, "registre des taux de change"),
            (EngineProposalBook.STREAM, "registre des propositions de réassort"),
        ):
            _persistence_guard(stream, what)
        requester = body.request.requested_by
        relay = principal.role in authz.RELAY_ROLES
        if relay:
            # Passerelle n8n 08 : relaie la demande d'un agent ; le demandeur déclaré n'est pas authentifié.
            # Revue R4 (R3-NEW-06) : seulement un agent qui dépense (jamais qa-conformite ni catalogue).
            if requester not in authz.RELAYED_SPENDERS:
                svc.audit.append(
                    actor=principal.name, actor_kind=ActorKind.AGENT, action="mandate.check.relay_requester_refused",
                    entity="spend_request", entity_id=body.request.idempotency_key, dry_run=True,
                    payload={"requested_by": requester, "authz_version": authz.AUTHZ_VERSION},
                )  # fmt: skip
                raise HTTPProblem(
                    403,
                    f"requested_by « {requester} » : relais réservé aux agents qui dépensent "
                    f"({', '.join(sorted(authz.RELAYED_SPENDERS))}) — matrice authz",
                )
        elif requester != principal.name:
            raise HTTPProblem(403, f"requested_by « {requester} » ≠ rôle du jeton « {principal.name} »")
        suspended_now = svc.incidents.suspended()
        frozen = svc.stoploss_engine is not None and svc.stoploss_engine.frozen
        # Incident ouvert sur le workflow de dépense (clé canonique), ou suspension de toutes les écritures
        # hors gel du stop-loss (pendant un gel, le contrôle rend REJECTED « gel global », motivé et enregistré).
        if WORKFLOW_MANDATE in suspended_now or (svc.incidents.all_writes_suspended and not frozen):
            holders = {k: v for k, v in suspended_now.items() if k in (WORKFLOW_MANDATE, "*")}
            svc.audit.append(
                actor=requester,
                actor_kind=ActorKind.AGENT,
                action="mandate.check_suspended",
                entity="spend_request",
                entity_id=body.request.idempotency_key,
                dry_run=True,
                payload={"suspended": holders},
            )
            raise HTTPProblem(
                423,
                "dépenses suspendues par un incident ouvert (workflow de dépense ou toutes les écritures) : aucune dépense",
                suspended=holders,
                outcome="REJECTED",
            )
        if svc.mandate is None:
            raise HTTPProblem(503, "mandat illisible : " + svc.load_errors.get("mandate", "absent"))
        status, _ = svc.gate.stoploss_status()
        if status is None:
            raise HTTPProblem(
                503, f"état du stop-loss indisponible ({svc.gate.last_stoploss_error}) : décision impossible"
            )
        treasury = treasury_from_registers(svc.stoploss_state, svc.paypal_balance)
        unverified: list[str] = []
        posters = [("Photo stop-loss / trésorerie", svc.photo_poster)]
        if svc.paypal_balance is not None:
            posters.append(("Solde PayPal", svc.paypal_balance.recorded_by))
        if svc.bank_balance is not None:
            posters.append(("Solde bancaire", svc.bank_balance.recorded_by))
        if svc.balances.debts is not None:
            posters.append(("Dettes et précommandes", svc.balances.debts.recorded_by))
        if svc.balances.receivables is not None:
            posters.append(("Créances", svc.balances.receivables.recorded_by))
        # Revue R3 (R2-NEW-01, SEC-16) : déposants des coûts historiques (stock de la photo) et de la publicité.
        posters.extend(("Stock au coût historique", poster) for poster in sorted(svc.costs.posters()))
        posters.extend(("Activité publicitaire", poster) for poster in sorted(svc.ads.posters()))
        posters.extend(("Factures fournisseur", poster) for poster in sorted(svc.invoices.posters()))
        for label, poster in posters:
            # Vérifiable seulement si demande et dépôt viennent de deux jetons nommés distincts ; un relais
            # (passerelle 08) n'authentifie pas le demandeur : jamais vérifiable.
            if relay or poster is None or poster in (authz.COMMON, "inconnu") or poster in (principal.name, requester):
                if label not in unverified:
                    unverified.append(label)
        incomplete = svc.orders.incomplete_reasons()
        if incomplete:
            # Revue R5 (R4-NEW-01) : coût des ventes en attente (ou écriture dérivée impossible) => étoile polaire et
            # photo incomplètes : aucune dépense autonome (validation humaine), fermé par défaut.
            unverified.append(
                "Étoile polaire et photo incomplètes (" + " ; ".join(f"{k} : {v}" for k, v in sorted(incomplete.items()))
                + ")"
            )
        if body.request.category.value == "ADVERTISING":
            # Revue R4 (R2-NEW-03) : sans relevé récent du connecteur publicitaire, le stop-loss pub ne voit pas la
            # dépense réelle de la plateforme : toute dépense pub demande une validation humaine (fermé par défaut).
            last = svc.ads.last_recorded_at("connecteur-publicite")
            if last is None or svc.clock() - last > timedelta(hours=24):
                unverified.append("Activité publicitaire (aucun relevé de connecteur-publicite de moins de 24 h)")
        decision = check(
            body.request,
            svc.mandate,
            svc.spend_ledger,
            status,
            treasury,
            now=svc.clock(),
            fx_rates=svc.fx_rates,
            proposals=svc.proposals,
            unverified=unverified,
        )
        entry = svc.spend_ledger.record(body.request, decision, actor=requester) if body.record else None
        svc.audit.append(
            actor=requester,
            actor_kind=ActorKind.AGENT,
            action="mandate.check",
            entity="spend_request",
            entity_id=body.request.idempotency_key,
            dry_run=not body.record,
            payload={
                "outcome": decision.outcome,
                "reasons": list(decision.reasons),
                "amount_chf": decision.amount_chf,
                "treasury_from_body_ignored": body.treasury is not None,
                "replayed": decision.replayed,
            },
            idempotency_key=body.request.idempotency_key,
        )
        return _ok(
            {
                "decision": decision,
                "labels_fr": decision.labels_fr,
                "recorded": entry is not None,
                "treasury": treasury,
                "treasury_source": "registres du moteur (photo stop-loss acceptée, solde PayPal relevé)",
                "unverified": unverified,
            }
        )

    @app.post("/mandate/human-decision")
    async def mandate_human_decision(request: Request) -> PokeshopJSONResponse:
        """Enregistre la décision de la **propriétaire** sur une dépense ``PENDING_HUMAN`` (jeton propriétaire seul).

        Revue R5 (R4-DOC-03) : seule voie de ``HUMAN_APPROVED`` / ``HUMAN_REFUSED`` au registre du mandat. Une dépense
        pub validée compte dès lors dans le stop-loss pub (paiements **engagés**, à la date de la décision) et devient
        payable par la passerelle (``can_execute``, moins d'une heure). Validation au-delà de 24 h : expirée (409,
        resoumettre avec des données fraîches). Jamais depuis n8n : le jeton propriétaire n'y est pas.
        """
        require_api(request)
        _persistence_guard(SpendLedger.STREAM, "registre du mandat")
        body = await _body(request, HumanDecisionIn)
        now = svc.clock()
        try:
            if body.decision == "APPROVE":
                entry = svc.spend_ledger.approve_by_human(body.idempotency_key, approver=authz.OWNER, at=now, note=body.motif)
            else:
                entry = svc.spend_ledger.refuse_by_human(body.idempotency_key, approver=authz.OWNER, at=now, note=body.motif)
        except LedgerPersistenceError:
            raise
        except MandateError as exc:
            raise HTTPProblem(409, str(exc)) from None
        svc.gate.invalidate()
        svc.audit.append(
            actor=authz.OWNER, actor_kind=ActorKind.PROPRIETAIRE, action="mandate.human_decision", entity="spend_request",
            entity_id=body.idempotency_key, dry_run=False,
            payload={"decision": body.decision, "status": entry.status.value, "motif": body.motif},
        )  # fmt: skip
        frozen = svc.stoploss_engine is not None and svc.stoploss_engine.frozen
        return _ok({"entry": entry, "status": entry.status, "global_frozen": frozen})

    @app.post("/mandate/revoke")
    async def mandate_revoke(request: Request) -> PokeshopJSONResponse:
        """Révoque le mandat en vigueur (acte protecteur, tout porteur de jeton) : définitif pour cette empreinte."""
        principal = require_api(request)
        body = await _body(request, RevokeIn)
        actor = "propriétaire" if owner_verified(request) else actor_of(principal, body.actor, request,
                                                                         route="mandate.revoke")  # fmt: skip
        if svc.mandate is None:
            raise HTTPProblem(409, "aucun mandat chargé : rien à révoquer")
        now = svc.clock()
        unsaved: str | None = None
        try:
            item = svc.revocations.revoke(svc.mandate.fingerprint, at=now, actor=actor, reason=body.reason)
        except RegistryPersistenceError as exc:  # révocation appliquée en mémoire (fermé par défaut)
            unsaved, item = str(exc), None
        svc.mandate = svc.mandate.with_revocations(svc.revocations.fingerprints())
        if svc.stoploss_state is not None:
            svc.stoploss_state, _ = svc.authoritative_photo(svc.stoploss_state, now)
        svc.gate.invalidate()
        svc.audit.append(
            actor=actor,
            actor_kind=ActorKind.PROPRIETAIRE if actor == "propriétaire" else ActorKind.AGENT,
            action="mandate.revoke",
            entity="mandate",
            entity_id=svc.mandate.mandate_version,
            dry_run=False,
            payload={"reason": body.reason, "persisted": unsaved is None},
        )
        if unsaved is not None:
            raise HTTPProblem(503, f"révocation appliquée mais NON enregistrée : {unsaved} (réparer le stockage)")
        return _ok({"revocation": item, "mandate_active": svc.mandate.is_active(now)})

    @app.post("/treasury/paypal-balance")
    async def treasury_paypal_balance(request: Request) -> PokeshopJSONResponse:
        """Dépose le solde du compte PayPal dédié relevé par un connecteur (jeton nommé obligatoire)."""
        principal = require_api(request)
        require_named(principal, request, route="treasury.paypal_balance", what="solde PayPal")
        body = await _body(request, PayPalBalanceIn)
        now = svc.clock()
        if body.as_of - now > timedelta(minutes=5):
            raise HTTPProblem(409, "relevé daté du futur : horloge non fiable")
        if svc.paypal_balance is not None and body.as_of < svc.paypal_balance.as_of:
            raise HTTPProblem(409, "relevé plus ancien que le relevé en vigueur : refusé (jamais de retour en arrière)")
        reading = PayPalBalanceReading(
            as_of=body.as_of, balance_chf=body.balance_chf, source=body.source, recorded_by=principal.name
        )
        svc.paypal_balance = reading
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="treasury.paypal_balance",
            entity="treasury",
            entity_id="paypal",
            dry_run=False,
            payload={"as_of": body.as_of, "balance_chf": body.balance_chf, "source": body.source},
        )
        return _ok({"reading": reading})

    @app.post("/treasury/bank-balance")
    async def treasury_bank_balance(request: Request) -> PokeshopJSONResponse:
        """Dépose le solde du compte bancaire de l'activité relevé par un connecteur (jeton nommé obligatoire)."""
        principal = require_api(request)
        require_named(principal, request, route="treasury.bank_balance", what="solde bancaire")
        body = await _body(request, BankBalanceIn)
        now = svc.clock()
        if body.as_of - now > timedelta(minutes=5):
            raise HTTPProblem(409, "relevé daté du futur : horloge non fiable")
        if svc.bank_balance is not None and body.as_of < svc.bank_balance.as_of:
            raise HTTPProblem(409, "relevé plus ancien que le relevé en vigueur : refusé (jamais de retour en arrière)")
        reading = BankBalanceReading(
            as_of=body.as_of, balance_chf=body.balance_chf, source=body.source, recorded_by=principal.name
        )
        svc.bank_balance = reading
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="treasury.bank_balance",
            entity="treasury",
            entity_id="banque",
            dry_run=False,
            payload={"as_of": body.as_of, "balance_chf": body.balance_chf, "source": body.source},
        )
        return _ok({"reading": reading})

    @app.post("/treasury/balance-items")
    async def treasury_balance_items(request: Request) -> PokeshopJSONResponse:
        """Déclare les dettes (précommandes encaissées, TVA due, remboursements promis…) et/ou relève les créances.

        Valeur décisive de la photo du stop-loss (revues R4, R3-NEW-02, et R5, R4-NEW-02 / R4-DOC-01) — deux registres
        **séparés et persistés** (journal ``balance_statements``), combinés dans la photo :

        * **dettes et précommandes** (``preorders_collected_chf`` + ``debts``) : l'agent finance peut les **relever**,
          jamais les abaisser sous la déclaration en vigueur — **même après un redémarrage** (403 : baisse par la
          propriétaire ou le connecteur de trésorerie, qui voit les paiements) ; les factures fournisseur enregistrées
          non payées (``POST /costs/invoices``) s'y ajoutent toujours dans la photo (plancher du moteur) ;
        * **créances** (``receivables``, elles augmentent la valeur nette) : relevé de la **propriétaire** seulement
          (jeton propriétaire) ; un rôle qui en déclare : 403 ; une déclaration de dettes ne les efface jamais.
        """
        principal = require_api(request)
        require_named(principal, request, route="treasury.balance_items", what="dettes et créances")
        _persistence_guard(BalanceStatementBook.STREAM, "registre des dettes et créances")
        body = await _body(request, BalanceItemsIn)
        now = svc.clock()
        if body.as_of - now > timedelta(minutes=5):
            raise HTTPProblem(409, "déclaration datée du futur : horloge non fiable")
        has_debts = body.preorders_collected_chf is not None or body.debts is not None
        if has_debts and body.preorders_collected_chf is None:
            raise HTTPProblem(422, "déclaration des dettes : preorders_collected_chf obligatoire (« 0 » si aucune)")
        # Un rôle ne relève jamais de créance ; « receivables: [] » d'un rôle (ancienne forme) est sans effet.
        has_receivables = body.receivables is not None and (principal.owner or bool(body.receivables))
        if not has_debts and not has_receivables:
            raise HTTPProblem(422, "rien à déclarer : dettes (preorders_collected_chf, debts) ou créances (receivables)")
        current = svc.balances.debts
        current_receivables = svc.balances.receivables
        if has_debts and current is not None and body.as_of < current.as_of:
            raise HTTPProblem(409, "déclaration plus ancienne que celle en vigueur : refusée (jamais de retour en arrière)")
        if has_receivables and current_receivables is not None and body.as_of < current_receivables.as_of:
            raise HTTPProblem(409, "relevé de créances plus ancien que celui en vigueur : refusé (jamais de retour en arrière)")
        refusal: str | None = None
        if has_receivables and not principal.owner:
            refusal = (
                "créances : relevé de la propriétaire seulement (jeton propriétaire) — une créance déclarée par un "
                "rôle augmenterait la valeur nette sans justificatif vérifiable"
            )
        if refusal is None and has_debts and current is not None and not principal.owner and (
            principal.role != "connecteur-tresorerie"
        ):
            declared = sum((d.amount for d in body.debts or ()), Decimal("0"))
            in_force = sum((d.amount for d in current.debts), Decimal("0"))
            preorders = body.preorders_collected_chf or Decimal("0")
            if declared < in_force or preorders < current.preorders_collected_chf:
                refusal = (
                    f"baisse des dettes ({in_force} → {declared} CHF) ou des précommandes "
                    f"({current.preorders_collected_chf} → {preorders} CHF) : réservée à la propriétaire "
                    "ou au connecteur de trésorerie (paiement relevé) ; l'agent finance ne peut que les relever "
                    "(plancher persisté, valable aussi après un redémarrage)"
                )
        if refusal is not None:
            svc.audit.append(
                actor=principal.name, actor_kind=ActorKind.AGENT, action="treasury.balance_items_refused",
                entity="treasury", entity_id="dettes_creances", dry_run=False, payload={"motif": refusal},
            )  # fmt: skip
            raise HTTPProblem(403, refusal)
        statement = (
            BalanceStatement(
                as_of=body.as_of,
                preorders_collected_chf=body.preorders_collected_chf or Decimal("0"),
                debts=tuple(body.debts or ()),
                source=body.source,
                recorded_by=principal.name,
            )
            if has_debts
            else None
        )
        receivables = (
            ReceivablesStatement(as_of=body.as_of, receivables=tuple(body.receivables or ()), source=body.source)
            if has_receivables
            else None
        )
        svc.balances.record(debts=statement, receivables=receivables)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
            action="treasury.balance_items",
            entity="treasury",
            entity_id="dettes_creances",
            dry_run=False,
            payload={
                "as_of": body.as_of,
                "preorders_collected_chf": body.preorders_collected_chf,
                "debts": None if body.debts is None else [d.model_dump(mode="json") for d in body.debts],
                "receivables": None if receivables is None else [r.model_dump(mode="json") for r in receivables.receivables],
                "source": body.source,
            },
        )
        return _ok({"statement": svc.balances.debts, "receivables": svc.balances.receivables,
                    "updated": [k for k, v in (("dettes", statement), ("créances", receivables)) if v is not None]})  # fmt: skip

    @app.post("/capital/movements", status_code=201)
    async def capital_movements(request: Request) -> PokeshopJSONResponse:
        """Apport ou retrait de capital : **propriétaire uniquement** (jeton distinct), registre en ajout seul."""
        require_api(request)
        token = owner_token(request, required=True, route="capital.movement")
        if not verify_owner_token(token, cfg.owner_token_sha256):
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="capital.movement.owner_token_refused",
                entity="owner_token",
                entity_id=request.url.path,
                dry_run=False,
                payload={"motif": "jeton invalide"},
            )
            raise HTTPProblem(403, "jeton propriétaire invalide")
        _persistence_guard(CapitalRegister.STREAM, "registre des apports")
        body = await _body(request, CapitalMovementIn)
        try:
            movement = CapitalMovement(**body.model_dump())
        except ValidationError as exc:
            raise HTTPProblem(422, "mouvement invalide", details=to_jsonable(exc.errors(include_url=False))) from None
        item, created = svc.capital.record(movement, now=svc.clock())
        if created:
            svc.audit.append(
                actor="propriétaire",
                actor_kind=ActorKind.PROPRIETAIRE,
                action="capital.movement",
                entity="capital",
                entity_id=movement.movement_id,
                dry_run=False,
                payload={"kind": movement.kind, "amount": movement.amount, "at": movement.at, "ref": movement.ref},
            )
        return _ok({"movement": item, "created": created}, 201 if created else 200)

    @app.get("/capital/movements")
    def capital_list(request: Request) -> PokeshopJSONResponse:
        """Apports et retraits enregistrés (interne)."""
        require_api(request)
        _persistence_guard(CapitalRegister.STREAM, "registre des apports")
        return _ok({"movements": svc.capital.movements()})

    @app.post("/ads/activity")
    async def ads_activity(request: Request) -> PokeshopJSONResponse:
        """Dépenses publicitaires et commandes attribuées relevées par le **connecteur publicitaire**.

        Jamais l'agent acquisition (qui dépense) : rôle ``connecteur-publicite`` ou propriétaire (matrice).
        Registre en ajout seul : une dépense déjà relevée pour (campagne, jour) ne baisse jamais (409) ; une
        commande attribuée doit être enregistrée par le moteur (``POST /orders/shipped``), sa contribution
        est plafonnée par ses données (revue R3, R2-NEW-03) ; inconnue ou en conflit, elle est **écartée seule**
        (``attributed_orders_set_aside``) et les dépenses du lot sont enregistrées (revue R5, R4-NEW-01). Le stop-loss pub retient en plus, par
        (campagne, jour), le MAX entre cette déclaration et les paiements pub engagés (approuvés ou exécutés) du mandat.
        """
        principal = require_api(request)
        _persistence_guard(AdsActivityRegister.STREAM, "registre de l'activité publicitaire")
        _persistence_guard(OrderRegister.STREAM, "registre des commandes")
        body = await _body(request, AdsActivityIn)
        now = svc.clock()
        tz = svc.stoploss_config.tz if svc.stoploss_config is not None else UTC
        received = svc.ads.record(
            list(body.ad_spends),
            list(body.attributed_orders),
            today=now.astimezone(tz).date(),
            recorded_by=principal.name,
            order_book=svc.orders,
            recorded_at=now,
            costs=svc.costs,  # revue R6 (R5-NEW-01) : contribution bornée par le coût des ventes du moteur
        )
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="ads.activity",
            entity="ads",
            entity_id=str(received),
            dry_run=False,
            payload={"ad_spends": len(body.ad_spends), "attributed_orders": len(body.attributed_orders),
                     "attributed_orders_set_aside": svc.ads.last_set_aside},
        )  # fmt: skip
        # Revue R5 (R4-NEW-01) : une commande attribuée inconnue (ou en conflit) est écartée seule, jamais les dépenses.
        return _ok({"received": received, "attributed_orders_set_aside": svc.ads.last_set_aside})

    @app.post("/fx/rates")
    async def fx_rates_record(request: Request) -> PokeshopJSONResponse:
        """Taux de change de référence : **propriétaire uniquement** (source officielle datée)."""
        require_api(request)
        token = owner_token(request, required=True, route="fx.rates")
        if not verify_owner_token(token, cfg.owner_token_sha256):
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="fx.rates.owner_token_refused",
                entity="owner_token",
                entity_id=request.url.path,
                dry_run=False,
                payload={"motif": "jeton invalide"},
            )
            raise HTTPProblem(403, "jeton propriétaire invalide")
        body = await _body(request, FxRateIn)
        _persistence_guard(FxRateBook.STREAM, "registre des taux de change")
        try:
            rate = FxRate(
                currency=body.currency,
                rate_to_chf=body.rate_to_chf,
                rate_date=body.rate_date,
                source=body.source,
                recorded_by="propriétaire",
                recorded_at=svc.clock(),
            )
        except ValidationError as exc:
            raise HTTPProblem(422, "taux invalide", details=to_jsonable(exc.errors(include_url=False))) from None
        svc.fx_rates.record(rate)
        svc.audit.append(
            actor="propriétaire",
            actor_kind=ActorKind.PROPRIETAIRE,
            action="fx.rate",
            entity="fx_rate",
            entity_id=rate.currency,
            dry_run=False,
            payload={"rate_to_chf": rate.rate_to_chf, "rate_date": rate.rate_date, "source": rate.source},
        )
        return _ok({"rate": rate})

    # -- étoile polaire --------------------------------------------------------------------------
    @app.get("/northstar")
    def northstar(request: Request, start: date | None = None, end: date | None = None) -> PokeshopJSONResponse:
        """Contribution nette cumulée par semaine (étoile polaire)."""
        require_api(request)
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        # Revues R4 (R3-NEW-04/05) et R5 (R4-NEW-01) : écriture dérivée impossible ou coût des ventes en attente.
        incomplete = svc.orders.incomplete_reasons()
        if not svc.northstar.entries() and (start is None or end is None):
            return _ok({"cumulative": Decimal("0.00"), "rows": [], "markdown": "", "note": "aucune écriture",
                        "incomplete": bool(incomplete), "derivation_errors": incomplete})  # fmt: skip
        try:
            report = svc.northstar.weekly_report(start, end)
        except NorthStarError as exc:
            raise HTTPProblem(422, str(exc)) from None
        return _ok(
            {
                "cumulative": report.cumulative,
                "opening_cumulative": report.opening_cumulative,
                "rows": report.rows,
                "total": report.total,
                "markdown": report.render_markdown(),
                # Revue R4 (R3-NEW-04/05) : écriture dérivée impossible (conflit, commande sans lignes) => incomplète.
                "incomplete": bool(incomplete),
                "derivation_errors": incomplete,
                "cost_of_sales_pending": svc.orders.pending_cogs(),
            }
        )

    @app.post("/northstar/entries")
    async def northstar_entries(request: Request) -> PokeshopJSONResponse:
        """Enregistre des écritures de contribution (idempotentes par ``entry_id``), lot atomique.

        Rôles nommés (``n8n-02-commandes``, ``finance-pricing``) : coûts **positifs** seulement (paiement,
        SAV, acquisition, charges fixes) ; ventes et avoirs : ``POST /orders/shipped`` et
        ``/orders/{id}/refunds`` (commandes enregistrées). Propriétaire : écriture manuelle, montant négatif
        seulement en annulation d'une écriture positive existante du même poste ; une vente exige la
        logistique réelle de la même commande (revue MOT-18). Coût historique : jamais (``/costs/movements``).
        """
        principal = require_api(request)
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        body = await _body(request, NorthStarEntriesIn)
        added = svc.northstar.add_entries(body.entries, owner=principal.owner)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="northstar.entries",
            entity="northstar",
            entity_id=str(len(added)),
            dry_run=False,
            payload={"added": [e.entry_id for e in added], "received": len(body.entries)},
        )
        return _ok({"added": len(added), "received": len(body.entries)})

    @app.post("/orders/shipped", status_code=201)
    async def orders_shipped(request: Request) -> PokeshopJSONResponse:
        """Commande payée et expédiée : enregistrée par le moteur, ventes de l'étoile polaire **dérivées** d'elle.

        Rôle ``n8n-02-commandes`` (webhook Shopify vérifié) ou propriétaire. Coût **réel** du transporteur et
        référence de l'étiquette achetée obligatoires (revue MOT-18 : une logistique supposée n'est jamais
        inscrite) ; idempotente par ``order_id`` (autre contenu : 409). Revue R5 (R4-NEW-01) : jamais refusée faute
        de stock valorisé — coût des ventes **en attente** (``cost_of_sales_pending``), étoile polaire et photo
        signalées incomplètes (dépenses : validation humaine) jusqu'à l'inscription du coût de réception. Revue R6
        (R5-NEW-02) : jamais refusée pour un SKU — un SKU corrigé par le catalogue reste rattaché à sa clé (alias
        historique du journal du catalogue) ; un SKU inconnu ou ambigu (porté par plusieurs clés) donne une ligne
        **non rattachée** (``unresolved_lines``, coût des ventes en attente, incomplet) que la propriétaire rattache
        (``POST /orders/{order_id}/lines/resolve``).
        """
        principal = require_api(request)
        _persistence_guard(OrderRegister.STREAM, "registre des commandes")
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        _persistence_guard(CostRegister.STREAM, "registre de coûts historiques")
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        body = await _body(request, ShippedOrderIn)
        now = svc.clock()
        if body.paid_at - now > timedelta(minutes=5):
            raise HTTPProblem(409, "commande datée du futur : horloge non fiable")
        lines: list[OrderLine] = []
        unresolved: dict[str, list[str]] = {}
        for line in body.lines:
            # Revue R6 (R5-NEW-02) : SKU actuel ou ancien SKU de la même clé ; inconnu ou ambigu : ligne non rattachée.
            entry, holders = svc.catalog.resolve_sku(line.public_sku)
            if entry is None:
                unresolved[line.public_sku] = list(holders)
            key = entry.product_id if entry is not None else unresolved_key(line.public_sku)
            lines.append(OrderLine(public_sku=line.public_sku, product_key=key, qty=line.qty))
        data = body.model_dump(exclude={"lines"})
        # Pré-drop : chiffre d'affaires reconnu à l'expédition (date posée par le moteur), jamais à l'encaissement.
        _persistence_guard(PredropRegistry.STREAM, "registre du pré-drop")
        recognized_at = now if svc.predrop.is_reservation(body.order_id) else None
        try:
            order, created = svc.orders.record_shipped(
                ShippedOrder(**data, lines=tuple(lines), recorded_by=principal.name, recorded_at=now,
                             recognized_at=recognized_at),
                svc.northstar,
                svc.costs,
            )  # fmt: skip
        except NorthStarPersistenceError:
            raise
        except NorthStarError as exc:
            status = 422 if any(w in str(exc) for w in ("transporteur", "centime", "négatif", "≤ 0", "étiquette")) else 409
            raise HTTPProblem(status, str(exc)) from None
        if created:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                action="orders.shipped",
                entity="order",
                entity_id=order.order_id,
                dry_run=False,
                payload={"net_sales_ht": order.net_sales_ht, "shipping_cost_actual": order.shipping_cost_actual,
                         "shipping_label_ref": order.shipping_label_ref,
                         "lines": [(ln.public_sku, ln.product_key, ln.qty) for ln in order.lines],
                         "unresolved_lines": unresolved,
                         "cost_of_sales_pending": svc.orders.pending_cogs().get(order.order_id)},
            )  # fmt: skip
        # Revue R5 (R4-NEW-01) : enregistrée même sans stock valorisé ; coût des ventes en attente signalé.
        # Revue R6 (R5-NEW-02) : lignes non rattachées (SKU inconnu ou ambigu) signalées, jamais un refus.
        pending = svc.orders.pending_cogs().get(order.order_id)
        open_lines = {ln.public_sku: unresolved.get(ln.public_sku, [])
                      for ln in order.lines if is_unresolved_key(ln.product_key)}  # fmt: skip
        return _ok({"order": order, "created": created, "cost_of_sales_pending": pending,
                    "unresolved_lines": open_lines, "incomplete": pending is not None}, 201 if created else 200)  # fmt: skip

    @app.post("/orders/{order_id}/refunds", status_code=201)
    async def orders_refund(order_id: str, request: Request) -> PokeshopJSONResponse:
        """Avoir sur une commande enregistrée (cumul ≤ ventes) : ventes négatives **dérivées** de lui."""
        principal = require_api(request)
        _persistence_guard(OrderRegister.STREAM, "registre des commandes")
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        body = await _body(request, OrderRefundIn)
        now = svc.clock()
        if body.at - now > timedelta(minutes=5):
            raise HTTPProblem(409, "avoir daté du futur : horloge non fiable")
        lines: list[OrderLine] = []
        known = svc.orders.get(order_id)
        for line in body.lines:
            # Revue R6 (R5-NEW-02) : la ligne retournée désigne d'abord la ligne de la commande de même SKU (rattachée
            # ou non), puis la clé du SKU (historique du catalogue compris).
            same = [ln.product_key for ln in (known.lines if known is not None else ()) if ln.public_sku == line.public_sku]
            if same:
                key = same[0]
            else:
                entry, _ = svc.catalog.resolve_sku(line.public_sku)
                if entry is None:
                    raise HTTPProblem(
                        409, f"ligne retournée {line.public_sku} : ni ligne de la commande ni SKU du catalogue validé — avoir refusé"
                    )
                key = entry.product_id
            lines.append(OrderLine(public_sku=line.public_sku, product_key=key, qty=line.qty))
        try:
            refund, created = svc.orders.record_refund(
                OrderRefund(order_id=order_id, **body.model_dump(exclude={"lines"}), lines=tuple(lines),
                            recorded_by=principal.name, recorded_at=now),
                svc.northstar,
            )  # fmt: skip
        except NorthStarPersistenceError:
            raise
        except NorthStarError as exc:
            raise HTTPProblem(409, str(exc)) from None
        if created:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                action="orders.refund",
                entity="order",
                entity_id=order_id,
                dry_run=False,
                payload={"refund_id": refund.refund_id, "net_sales_ht": refund.net_sales_ht,
                         "lines": [(ln.public_sku, ln.qty) for ln in refund.lines]},
            )  # fmt: skip
        return _ok({"refund": refund, "created": created}, 201 if created else 200)

    @app.post("/orders/{order_id}/lines/resolve")
    async def orders_line_resolve(order_id: str, request: Request) -> PokeshopJSONResponse:
        """Rattache une ligne **non rattachée** d'une commande à sa clé produit canonique : **propriétaire** seule.

        Revue R6 (R5-NEW-02) : une commande payée n'est jamais refusée pour un SKU inconnu ou ambigu (porté par
        plusieurs clés au fil des corrections du catalogue) ; la ligne attend ce rattachement (coût des ventes en
        attente, étoile polaire et photo incomplètes). La clé doit être une fiche canonique du catalogue ; la sortie au
        CMP est ensuite dérivée par le moteur. Journalisé (ajout seul), rejoué au démarrage.
        """
        principal = require_api(request)
        if not principal.owner:  # matrice : propriétaire seule (défense en profondeur)
            raise HTTPProblem(403, "rattachement d'une ligne de commande : jeton propriétaire")
        _persistence_guard(OrderRegister.STREAM, "registre des commandes")
        _persistence_guard(CostRegister.STREAM, "registre de coûts historiques")
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        body = await _body(request, OrderLineResolveIn)
        entry = svc.catalog.entry_for(body.product_key)
        if entry is None or not entry.canonical:
            raise HTTPProblem(409, f"clé produit {body.product_key} : fiche canonique inconnue du catalogue validé")
        try:
            order, created = svc.orders.resolve_line(
                order_id, body.public_sku, entry.product_id, recorded_by=principal.name, recorded_at=svc.clock(),
                costs=svc.costs,
            )  # fmt: skip
        except NorthStarPersistenceError:
            raise
        except NorthStarError as exc:
            raise HTTPProblem(409, str(exc)) from None
        pending = svc.orders.pending_cogs().get(order_id)
        if created:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.PROPRIETAIRE,
                action="orders.line_resolved",
                entity="order",
                entity_id=order_id,
                dry_run=False,
                payload={"public_sku": body.public_sku, "product_key": entry.product_id,
                         "holders": list(svc.catalog.sku_holders(body.public_sku)), "cost_of_sales_pending": pending},
            )  # fmt: skip
        return _ok({"order": order, "created": created, "cost_of_sales_pending": pending,
                    "unresolved_lines": svc.orders.unresolved_lines().get(order_id, ()),
                    "incomplete": pending is not None})  # fmt: skip

    INVOICE_GAP_OWNER = Decimal("0.02")
    """Écart (facture, coût de réception) au-delà duquel seule la propriétaire inscrit le coût (workflow 03 : > 2 %)."""

    def _cost_beneficiaries(principal: Principal) -> frozenset[str]:
        """Jetons qui bénéficient d'un coût de réception : rôles admis sur ``POST /costs/movements`` et l'appelant."""
        rule = authz.rule_for("POST", "/costs/movements")
        return (rule.roles if rule is not None else frozenset()) | {principal.name, authz.COMMON, "inconnu"}

    def _admissible_offer(rc: ReplacementCost, principal: Principal) -> bool:
        """Offre admise comme référence d'une réception (revue R5, R2-NEW-01 / R3-DOC-02).

        Coût rendu évalué par le moteur (catalogue et frais **du registre**, jamais du corps : voir ``/sync/run``)
        avec des frais posés par la propriétaire ou par un rôle qui ne valorise pas les réceptions ; des frais posés
        par ``finance-pricing`` (bénéficiaire de la référence) ou de provenance inconnue ne bornent rien.
        """
        by = rc.fees_recorded_by
        return by is not None and (by == authz.OWNER or by not in _cost_beneficiaries(principal))

    def _receipt_reference(
        product_key: str, invoice_line: InvoiceLine | None, invoice_ref: str | None, principal: Principal
    ) -> tuple[Decimal, str] | None:
        """Référence **du moteur** du coût unitaire d'une réception (revues R4 et R5, R2-NEW-01 / R3-DOC-02).

        1. ligne de la facture enregistrée ``invoice_ref`` (``POST /costs/invoices``, workflow 03 après validation de
           la propriétaire ; quantités rapprochées par l'appelant) : coût rendu au profil TVA du moteur ;
        2. sinon, coût rendu de la dernière offre évaluée par le moteur **admise** (:func:`_admissible_offer`).
        Aucune des deux : None (la propriétaire inscrit le coût).
        """
        if invoice_line is not None:
            in_cost = svc.rules.profile is not VatMode.EFFECTIVE
            return invoice_line.landed_unit_cost(import_vat_in_cost=in_cost), f"facture enregistrée {invoice_ref}"
        offer = svc.sync.replacement_costs.latest_where(product_key, lambda rc: _admissible_offer(rc, principal))
        if offer is not None:
            return offer.unit_cost, (
                f"coût rendu de l'offre {offer.offer_ref or offer.supplier_id} du {offer.source_ts.date()} "
                f"(frais posés par {offer.fees_recorded_by})"
            )
        return None

    def _known_suppliers(product_key: str, entry: CatalogEntry) -> frozenset[str]:
        """Fournisseurs connus **du moteur** pour une référence (revue R5, R2-NEW-01 c) — jamais déclarés par l'agent 05.

        Liens fournisseur du catalogue (``catalogue``), offres rapprochées et évaluées par le moteur (coûts de
        remplacement, toute provenance de frais : seul le fournisseur compte ici) et cycles ``/sync/run`` **sur le
        catalogue du registre** qui ont rapproché la référence (journal persisté ``sync_runs`` : survit au
        redémarrage). Vide : fournisseur d'une facture invérifiable (fermé par défaut).
        """
        known = {link.supplier_id for link in entry.supplier_links}
        known.update(rc.supplier_id for rc in svc.sync.replacement_costs.history(product_key))
        known.update(
            run.supplier_id for run in svc.sync_runs.runs()
            if run.catalog_source == "registre" and product_key in run.product_ids
        )  # fmt: skip
        return frozenset(known)

    def _moved_qty(kind: str, stock_ref: str | None, *, sku: str | None = None, product_key: str | None = None,
                   invoice_ref: str | None = None, exclude_ref: str | None = None) -> int:  # fmt: skip
        """Unités déjà portées par les mouvements ``kind`` qui citent ce bon / cette facture (même SKU ou référence)."""
        total = 0
        for m in svc.costs.movements():
            if m.kind != kind or (stock_ref is not None and m.stock_ref != stock_ref):
                continue
            if invoice_ref is not None and m.invoice_ref != invoice_ref:
                continue
            if exclude_ref is not None and m.ref == exclude_ref and m.product_key == product_key:
                continue  # le même mouvement rejoué
            m_sku = m.sku
            if m_sku is None:  # mouvement d'avant la revue R5 : SKU actuel de sa fiche
                other = svc.catalog.entry_for(m.product_key)
                m_sku = other.listing.public_sku if other is not None else None
            if (sku is not None and m_sku == sku) or (product_key is not None and m.product_key == product_key):
                total += m.qty or 0
        return total

    def _cost_reference_problem(body: CostMovementIn, principal: Principal) -> tuple[int, str] | None:
        """Adossement d'un mouvement de coût (revues R3, R4 et R5, R2-NEW-01, R3-NEW-05) ; None = vérifié."""
        if body.kind == "RECEIPT":
            if body.stock_ref is None or body.invoice_ref is None:
                return 422, "réception : stock_ref (réception POST /stock/receive) et invoice_ref (facture) obligatoires"
            entry = svc.catalog.entry_for(body.product_key)
            if entry is None or not entry.canonical:
                return 409, (
                    f"{body.product_key} : clé produit canonique absente du catalogue validé (product_id = "
                    "listing.product_key) — SKU de la réception inconnu"
                )
            if not principal.owner and body.stock_ref.startswith("return:"):
                # Revue R5 (R3-NEW-05) : un retour physique ne se valorise que par RETURN, au coût de la vente d'origine
                # (sinon la même unité retournée entrerait deux fois au coût : RECEIPT puis RETURN).
                return 409, (
                    f"réception {body.stock_ref} : référence « return: » réservée aux retours (RETURN, au coût de la "
                    "vente d'origine) — jamais une réception au coût d'une facture"
                )
            sku = entry.listing.public_sku
            receipt = svc.stock.receipt(sku, body.stock_ref)
            if receipt is None:
                return 409, (
                    f"réception {body.stock_ref} inconnue pour {sku} : déclarer d'abord la "
                    "réception physique (POST /stock/receive, operations-sav)"
                )
            qty, receiver = receipt
            if body.qty != qty:
                return 409, f"réception {body.stock_ref} : {qty} unité(s) reçue(s) ≠ {body.qty} au coût"
            if not principal.owner and (receiver is None or receiver == principal.name):
                return 409, "réception déclarée par le même jeton (ou inconnu) : un autre jeton doit l'avoir déclarée"
            # Revues R4 et R5 (R2-NEW-01 b et d) : une réception physique (SKU **à la réception**, bon) n'est valorisée
            # qu'une fois, quelle que soit la clé citée ou le SKU actuel de la fiche d'un mouvement plus ancien.
            for m in svc.costs.movements():
                if m.kind != "RECEIPT" or m.stock_ref != body.stock_ref:
                    continue
                m_sku = m.sku
                if m_sku is None:
                    other = svc.catalog.entry_for(m.product_key)
                    m_sku = other.listing.public_sku if other is not None else None
                same = m.product_key == body.product_key or m_sku == sku
                if same and (m.ref != body.ref or m.product_key != body.product_key):
                    return 409, f"réception {body.stock_ref} déjà valorisée (lot {m.ref}, {m.product_key}, SKU {m_sku})"
            if not principal.owner:
                if body.unit_cost is None:
                    return 422, "réception : unit_cost obligatoire"
                invoice = svc.invoices.get(body.invoice_ref)
                line = invoice.line_for(body.product_key) if invoice is not None else None
                if invoice is not None and line is not None:
                    # Revue R5 (R2-NEW-01 c) : facture d'un fournisseur connu pour la référence (fermé par défaut :
                    # fournisseur inconnu => 409), quantités rapprochées.
                    suppliers = _known_suppliers(body.product_key, entry)
                    if not suppliers:
                        return 409, (
                            f"facture {body.invoice_ref} : aucun fournisseur connu du moteur pour {body.product_key} (lien "
                            "fournisseur au catalogue, POST /catalog/items par catalogue, ou offre rapprochée par un cycle "
                            "/sync/run sur le catalogue du registre) — fournisseur de la facture invérifiable : lien à "
                            "déclarer, ou la propriétaire inscrit le coût"
                        )
                    if invoice.supplier_id not in suppliers:
                        return 409, (
                            f"facture {body.invoice_ref} du fournisseur {invoice.supplier_id} : {body.product_key} n'est "
                            f"connu que chez {', '.join(sorted(suppliers))} (catalogue, offres rapprochées) — la "
                            "propriétaire rapproche"
                        )
                    already = _moved_qty("RECEIPT", None, product_key=body.product_key, invoice_ref=body.invoice_ref,
                                         exclude_ref=body.ref)  # fmt: skip
                    if already + (body.qty or 0) > line.qty:
                        return 409, (
                            f"réception de {body.qty} unité(s) (déjà {already} au coût sur cette facture) > {line.qty} "
                            f"unité(s) facturée(s) sur la ligne {body.product_key} de la facture {body.invoice_ref} : "
                            "carton saisi comme unité, ou facture d'un autre envoi ? la propriétaire rapproche"
                        )
                reference = _receipt_reference(body.product_key, line, body.invoice_ref, principal)
                if reference is None:
                    return 403, (
                        "coût de réception sans référence du moteur (facture enregistrée POST /costs/invoices pour cette "
                        "référence, ou offre évaluée par /sync/run avec des frais posés par la propriétaire — jamais des "
                        "frais posés par finance-pricing ni ceux du corps d'une simulation) : la propriétaire l'inscrit "
                        "(jeton propriétaire)"
                    )
                ref_cost, ref_label = reference
                gap = abs(Decimal(body.unit_cost) - ref_cost) / ref_cost
                if gap > INVOICE_GAP_OWNER:
                    return 403, (
                        f"coût de réception {body.unit_cost} : écart {gap:.2%} > 2 % de la référence du moteur "
                        f"({ref_cost}, {ref_label}) — carton saisi comme unité, devise ou frais ? signalé, la "
                        "propriétaire l'inscrit (jeton propriétaire)"
                    )
        elif body.kind == "ISSUE":
            if not principal.owner:
                return 403, (
                    "sortie de vente : dérivée par le moteur des commandes enregistrées (POST /orders/shipped avec "
                    "lignes, au CMP) ; correction manuelle : propriétaire"
                )
        elif body.kind == "RETURN":
            if not principal.owner:
                order_id = (body.sale_ref or "").removeprefix("order:")
                if not (body.sale_ref or "").startswith("order:") or svc.orders.get(order_id) is None:
                    return 409, "retour : sale_ref = « order:<id> » d'une commande enregistrée (sortie dérivée par le moteur)"
                if svc.orders.refunded(order_id) <= 0:
                    return 409, (
                        f"retour sur la commande {order_id} sans avoir enregistré (POST /orders/{order_id}/refunds) : "
                        "un retour en stock ne se déclare pas seul"
                    )
                # Revue R5 (R3-NEW-05) : un retour en stock au coût exige les LIGNES de l'avoir (unités retournées) et
                # la réception PHYSIQUE du retour (operations-sav) ; un geste commercial ne remet rien en stock.
                entry = svc.catalog.entry_for(body.product_key)
                refund_id = (body.stock_ref or "").removeprefix("return:")
                refund = svc.orders.refund(refund_id) if (body.stock_ref or "").startswith("return:") else None
                if entry is None or not entry.canonical or refund is None or refund.order_id != order_id:
                    return 403, (
                        "retour en stock au coût : stock_ref = « return:<refund_id> » d'un avoir de cette commande avec "
                        "lignes (POST /orders/{id}/refunds, lines = SKU × unités retournées) et réception physique du "
                        "retour (POST /stock/receive, ref return:<refund_id>, operations-sav) — sinon la propriétaire "
                        "l'inscrit (jeton propriétaire)"
                    )
                returned = sum(ln.qty for ln in refund.lines if ln.product_key == body.product_key)
                already = _moved_qty("RETURN", body.stock_ref, product_key=body.product_key)
                if already + (body.qty or 0) > returned:
                    return 403, (
                        f"retour de {body.qty} unité(s) (déjà {already}) > {returned} unité(s) retournée(s) sur les lignes "
                        f"de l'avoir {refund_id} : un remboursement sans retour (geste commercial) ne remet rien en "
                        "stock ; correction : la propriétaire"
                    )
                if body.product_key in svc.orders.pending_cogs().get(order_id, {}):
                    # Revue R5 (R4-NEW-01) : la sortie au CMP de la commande attend encore un stock valorisé.
                    return 409, (
                        f"commande {order_id} : coût des ventes de {body.product_key} encore en attente (sortie au CMP non "
                        "dérivée) — inscrire d'abord le coût de réception ; le retour au coût suit"
                    )
                # Revue R5 (R3-NEW-05) : un avoir inférieur au coût des unités qu'il dit retournées n'est pas un retour
                # contre remboursement (geste commercial, décote d'une unité ouverte) : la paire avoir + retour ne
                # relève jamais l'étoile polaire ni la photo ; sinon la propriétaire décide.
                cost_back = Decimal("0")
                for ln in refund.lines:
                    ledger = svc.costs.ledger(ln.product_key)
                    issues = [e for e in (ledger.journal() if ledger is not None else ()) if e.kind == "ISSUE"
                              and e.ref == body.sale_ref]  # fmt: skip
                    sold_qty = sum(e.qty for e in issues)
                    if sold_qty > 0:
                        cost_back += sum((e.cogs for e in issues), Decimal("0")) * ln.qty / sold_qty
                if refund.net_sales_ht < cost_back.quantize(Decimal("0.01")):
                    return 403, (
                        f"avoir {refund_id} : {refund.net_sales_ht} CHF HT < coût des unités retournées "
                        f"{cost_back.quantize(Decimal('0.01'))} CHF (coût de la vente d'origine) — geste commercial ou "
                        "décote, pas un retour contre remboursement : la propriétaire inscrit le retour au coût"
                    )
                sku = entry.listing.public_sku
                physical = svc.stock.receipt(sku, body.stock_ref or "")
                if physical is None:
                    return 403, (
                        f"retour physique {body.stock_ref} non déclaré pour {sku} (POST /stock/receive, operations-sav) : "
                        "rien ne rentre en stock au coût sans retour physique"
                    )
                received, receiver = physical
                if receiver is None or receiver == principal.name:
                    return 403, "retour physique déclaré par le même jeton (ou inconnu) : un autre jeton doit l'avoir déclaré"
                # Unités de ce retour physique déjà entrées au coût, par RETURN ou par une RECEIPT de la propriétaire.
                in_stock = _moved_qty("RETURN", body.stock_ref, sku=sku) + _moved_qty("RECEIPT", body.stock_ref, sku=sku)
                if in_stock + (body.qty or 0) > received:
                    return 403, (
                        f"retour de {body.qty} unité(s) > {received - in_stock} unité(s) physiquement reçue(s) "
                        f"({body.stock_ref}, {sku})"
                    )
        elif body.kind == "INVOICE_ADJUSTMENT":
            if body.invoice_ref is None:
                return 422, "ajustement de facture : invoice_ref obligatoire"
            original = svc.costs.receipt_unit_cost(body.product_key, body.lot_id or "")
            if original is None:
                return 409, f"lot {body.lot_id} inconnu du registre de coûts"
            if body.unit_cost is not None and not principal.owner:
                gap = abs(Decimal(body.unit_cost) - original) / original
                if gap > INVOICE_GAP_OWNER:
                    return 403, (
                        f"écart de facture {gap:.2%} > 2 % du coût à la réception ({original}) : signalé, la "
                        "propriétaire l'inscrit (jeton propriétaire)"
                    )
        return None

    @app.post("/costs/invoices", status_code=201)
    async def costs_invoices(request: Request) -> PokeshopJSONResponse:
        """Enregistre une facture fournisseur **validée par la propriétaire** (workflow 03) — revue R4.

        Rôle ``n8n-03-factures`` (après le formulaire de validation de l'extraction) ou propriétaire ; jamais
        l'agent finance qui valorise les réceptions. Lignes : clé produit **canonique** du catalogue, quantité,
        coût rendu unitaire ventilé (CHF) — référence du coût d'une réception (± 2 %). Solde non payé : dette
        de la photo du stop-loss jusqu'au paiement relevé. Idempotente par ``invoice_ref`` (autre contenu : 409).
        """
        principal = require_api(request)
        _persistence_guard(SupplierInvoiceBook.STREAM, "registre des factures fournisseur")
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        body = await _body(request, SupplierInvoiceIn)
        now = svc.clock()
        if body.issued_at - now > timedelta(minutes=5):
            raise HTTPProblem(409, "facture datée du futur : horloge non fiable")
        unknown = [ln.product_key for ln in body.lines if (e := svc.catalog.entry_for(ln.product_key)) is None or not e.canonical]
        if unknown:
            raise HTTPProblem(409, f"lignes sur des clés produit inconnues du catalogue validé : {', '.join(unknown)}")
        try:
            invoice = SupplierInvoice(
                invoice_ref=body.invoice_ref, supplier_id=body.supplier_id, issued_at=body.issued_at,
                total_chf=body.total_chf,
                lines=tuple(InvoiceLine(product_key=ln.product_key, qty=ln.qty, unit_cost_chf=ln.unit_cost_chf,
                                        import_vat_unit_chf=ln.import_vat_unit_chf)
                            for ln in body.lines),
                source=body.source, recorded_by=principal.name, recorded_at=now,
            )  # fmt: skip
        except ValidationError as exc:
            raise HTTPProblem(422, "facture invalide", details=to_jsonable(exc.errors(include_url=False))) from None
        # Revue R5 (R2-NEW-01 c) : lignes rapprochées du montant dû — Σ quantité × (coût rendu + TVA d'import) jamais
        # au-dessus du total (tolérance d'arrondi : 1 centime par unité facturée).
        tolerance = Decimal("0.01") * invoice.units()
        if invoice.lines_total() > invoice.total_chf + tolerance:
            raise HTTPProblem(
                409,
                f"facture {invoice.invoice_ref} : lignes {invoice.lines_total():.2f} CHF (quantité × coût rendu unitaire) > "
                f"montant dû {invoice.total_chf} CHF — quantité, unité (carton ou pièce) ou coût unitaire incohérents",
            )
        item, created = svc.invoices.record(invoice)
        if created:
            svc.audit.append(
                actor=principal.name, actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                action="costs.invoice", entity="supplier_invoice", entity_id=item.invoice_ref, dry_run=False,
                payload={"supplier_id": item.supplier_id, "total_chf": item.total_chf, "lines": len(item.lines),
                         "source": item.source},
            )  # fmt: skip
        return _ok({"invoice": item, "created": created, "unpaid_chf": item.total_chf - svc.invoices.paid(item.invoice_ref)},
                   201 if created else 200)  # fmt: skip

    @app.post("/costs/invoices/{invoice_ref}/payments", status_code=201)
    async def costs_invoice_payment(invoice_ref: str, request: Request) -> PokeshopJSONResponse:
        """Inscrit le paiement d'une facture enregistrée, relevé sur le compte — revue R4.

        Rôle ``connecteur-tresorerie`` (débit relevé) ou propriétaire : seule voie qui abaisse la dette d'une
        facture dans la photo du stop-loss (cumul ≤ montant ; idempotent par ``payment_ref``).
        """
        principal = require_api(request)
        _persistence_guard(SupplierInvoiceBook.STREAM, "registre des factures fournisseur")
        body = await _body(request, InvoicePaymentIn)
        now = svc.clock()
        if body.paid_at - now > timedelta(minutes=5):
            raise HTTPProblem(409, "paiement daté du futur : horloge non fiable")
        payment = InvoicePayment(
            invoice_ref=invoice_ref, payment_ref=body.payment_ref, paid_at=body.paid_at, amount_chf=body.amount_chf,
            recorded_by=principal.name, recorded_at=now,
        )  # fmt: skip
        item, created = svc.invoices.record_payment(payment)
        if created:
            svc.audit.append(
                actor=principal.name, actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
                action="costs.invoice_payment", entity="supplier_invoice", entity_id=invoice_ref, dry_run=False,
                payload={"payment_ref": item.payment_ref, "amount_chf": item.amount_chf, "paid_at": item.paid_at},
            )  # fmt: skip
        invoice = svc.invoices.get(invoice_ref)
        remaining = invoice.total_chf - svc.invoices.paid(invoice_ref) if invoice is not None else None
        return _ok({"payment": item, "created": created, "unpaid_chf": remaining}, 201 if created else 200)

    @app.post("/costs/movements")
    async def cost_movements(request: Request) -> PokeshopJSONResponse:
        """Registre de coûts historiques interne : seule voie du coût des ventes dans l'étoile polaire.

        Rôle ``finance-pricing`` (ou propriétaire). Revue R3 (R2-NEW-01) : une **réception** (stock au coût
        historique de la photo du stop-loss) cite la réception physique ``POST /stock/receive`` (même SKU,
        même quantité, déclarée par un **autre** jeton, ``stock_ref``) et la facture (``invoice_ref``) ; un
        **ajustement de facture** cite la facture et, au-delà de 2 % du coût à la réception, attend la
        propriétaire. Revues R4 et R5 : le **coût unitaire** d'une réception est borné à ± 2 % d'une référence du
        moteur que son bénéficiaire ne nourrit jamais — ligne de la facture enregistrée (unités reçues au coût ≤
        quantité facturée : un carton saisi comme unité est refusé, 409 ; fournisseur de la facture connu du moteur
        pour la référence, sinon 409), sinon coût rendu de l'offre évaluée avec des frais posés par la propriétaire ;
        au-delà ou sans référence => propriétaire ; une réception physique (SKU à la réception, bon) n'est valorisée
        qu'une fois ; ``return:`` est réservé aux retours ; une sortie de vente (ISSUE) est dérivée des commandes
        enregistrées (rôle : 403) ; un retour (RETURN) exige un avoir à lignes couvrant au moins le coût des unités
        retournées et le retour physique déclaré par un autre jeton. Sinon 409/422/403 (journalisé).
        """
        principal = require_api(request)
        _persistence_guard(CostRegister.STREAM, "registre de coûts historiques")
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        _persistence_guard(PersistentStockRegistry.STREAM, "journal du stock local")
        _persistence_guard(CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation")
        _persistence_guard(SupplierInvoiceBook.STREAM, "registre des factures fournisseur")
        _persistence_guard(OrderRegister.STREAM, "registre des commandes")
        body = await _body(request, CostMovementIn)
        problem = _cost_reference_problem(body, principal)
        if problem is not None:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.AGENT,
                action="costs.movement_refused",
                entity="cost_ledger",
                entity_id=body.product_key,
                dry_run=False,
                payload={"kind": body.kind, "ref": body.ref, "stock_ref": body.stock_ref, "motif": problem[1]},
            )
            raise HTTPProblem(problem[0], problem[1])
        entry = svc.catalog.entry_for(body.product_key)
        sku = entry.listing.public_sku if entry is not None and body.kind in ("RECEIPT", "RETURN") else None
        movement = CostMovement(**body.model_dump(), recorded_by=principal.name, sku=sku)
        added = svc.costs.apply(movement)
        # Revue R5 (R4-NEW-01) : coût des ventes en attente (commande expédiée avant le coût) dérivé dès qu'il existe.
        added += svc.orders.derive_pending(svc.costs)
        ledger = svc.costs.ledger(movement.product_key)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
            action="costs.movement",
            entity="cost_ledger",
            entity_id=movement.product_key,
            dry_run=False,
            payload={"kind": movement.kind, "ref": movement.ref, "qty": movement.qty, "northstar_added": added,
                     "stock_ref": movement.stock_ref, "invoice_ref": movement.invoice_ref},
        )  # fmt: skip
        return _ok({"northstar_added": added, "valuation": ledger.valuation() if ledger is not None else None})

    # -- pré-drop (décision de la propriétaire du 6.10.2026) ------------------------------------------------
    def _shipped(order_id: str) -> bool:
        """Commande expédiée enregistrée par le moteur (fin de la dette d'une réservation pré-drop)."""
        return svc.orders.get(order_id) is not None

    def _predrop_guard(*more: tuple[str, str]) -> None:
        _persistence_guard(PredropRegistry.STREAM, "registre du pré-drop")
        for stream, what in more:
            _persistence_guard(stream, what)

    def _predrop_quarantined(entry: CatalogEntry | None, product_key: str) -> bool:
        keys = entry.keys if entry is not None else frozenset({product_key})
        return any(svc.incidents.is_quarantined(k) for k in keys)

    def _predrop_block(entry: CatalogEntry | None, product_key: str) -> str | None:
        """Motif qui interdit toute nouvelle promesse pré-drop (None : aucun) — fermé par défaut."""
        if _predrop_quarantined(entry, product_key):
            return "référence en quarantaine (incident ouvert)"
        return _predrop_stoploss_problem(entry, product_key)

    def _predrop_stoploss_problem(entry: CatalogEntry | None, product_key: str) -> str | None:
        """Gel ou blocage du stop-loss, ou état inconnu (photo absente, périmée) : fermé par défaut."""
        keys = entry.keys if entry is not None else frozenset({product_key})
        engine = svc.stoploss_engine
        if engine is None:
            return "stop-loss indisponible (seuils non chargés)"
        if engine.frozen:
            return "gel global du stop-loss (verrou)"
        status, _ = svc.gate.stoploss_status()
        if status is None:
            return f"état du stop-loss inconnu ({svc.gate.last_stoploss_error or 'photo absente ou périmée'})"
        if status.global_frozen:
            return "gel global du stop-loss"
        if keys & set(status.blocked_products):
            return "référence bloquée par le stop-loss produit"
        return None

    def _predrop_cost(entry: CatalogEntry | None, product_key: str, allocation: FirmAllocation | None) -> Decimal | None:
        """Coût rendu du moteur (jamais déclaré) : max(offre fraîche du fournisseur de l'allocation, CMP du stock)."""
        keys = entry.keys if entry is not None else frozenset({product_key})
        now = svc.clock()
        max_age = svc.rules.stock.max_age
        found: list[Decimal] = []
        for key in sorted(keys):
            if allocation is not None:
                rc = svc.sync.replacement_costs.latest(key, allocation.supplier_id)
                if rc is not None and now - rc.source_ts <= max_age and rc.source_ts - now <= timedelta(minutes=5):
                    found.append(rc.unit_cost)
            else:
                rc = svc.sync.replacement_costs.current(key, now, max_age)
                if rc is not None:
                    found.append(rc.unit_cost)
            ledger = svc.costs.ledger(key)
            if ledger is not None and ledger.average_unit_cost is not None:
                found.append(ledger.average_unit_cost)
        return max(found) if found else None

    def _predrop_eligibility(product_key: str, *, market_ref: Decimal | None, ignore: str | None = None) -> Eligibility:
        """Éligibilité évaluée sur les registres du moteur (catalogue, validations, coûts, stop-loss, incidents)."""
        for stream, what in ((CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"),
                             (CatalogApprovalBook.STREAM, "registre des validations de fiches"),
                             (CostRegister.STREAM, "registre de coûts historiques"),
                             (OrderRegister.STREAM, "registre des commandes")):  # fmt: skip
            _persistence_guard(stream, what)
        entry = svc.catalog.entry_for(product_key)
        listing_known = entry is not None and entry.canonical
        approval = svc.catalog_approvals.effective_for(entry.listing, entry.product_id) if entry is not None else None
        allocation = svc.predrop.allocation(product_key)
        return evaluate_eligibility(
            product_key=product_key,
            config_status=svc.predrop_config,
            allocation=allocation,
            demand=svc.predrop.demand(product_key),
            now=svc.clock(),
            listing_known=listing_known,
            listing_approved=approval is not None and approval.approved,
            cost=_predrop_cost(entry, product_key, allocation),
            params=svc.rules.pricing,
            market_ref=market_ref,
            stoploss_problem=_predrop_stoploss_problem(entry, product_key),
            quarantined=_predrop_quarantined(entry, product_key),
            committed=0,
            open_predrop=svc.predrop.unsettled(product_key, _shipped, ignore=ignore),
        )

    def _predrop_view(predrop: Predrop, now: datetime) -> dict[str, Any]:
        """Lecture interne d'un pré-drop : sans coût ni marge (prix, paramètres figés, quota, dette)."""
        quota = svc.predrop.quota(predrop.predrop_id, at=now)
        debt = svc.predrop.outstanding_debt(as_of=now, shipped=_shipped).by_predrop.get(predrop.predrop_id, Decimal("0"))
        return {
            "predrop_id": predrop.predrop_id,
            "product_key": predrop.product_key,
            "status": predrop.status,
            "accepting": svc.predrop_config.enabled and svc.predrop.accepting(predrop.predrop_id, now)
            and _predrop_block(svc.catalog.entry_for(predrop.product_key), predrop.product_key) is None,
            "drop_date": predrop.drop_date,
            "opens_at": predrop.opens_at,
            "closes_at": predrop.closes_at,
            "prix_drop_chf": predrop.prices.drop_price,
            "prix_predrop_chf": predrop.prices.predrop_price,
            "supplement_effectif": predrop.prices.effective_premium_pct,
            "plafonnements": list(predrop.prices.capped_by),
            "market_ref_chf": predrop.market_ref_chf,
            "needs_owner": list(predrop.needs_owner),
            "validated_by": predrop.validated_by,
            "per_customer_limit": predrop.per_customer_limit,
            "priority_window_hours": predrop.priority_window_hours,
            "demand_score": predrop.demand_score,
            "config_version": predrop.config_version,
            "quota": quota,
            "collected_not_delivered_chf": debt,
            "closed_at": predrop.closed_at,
            "close_reason": predrop.close_reason,
        }

    def _predrop_audit(principal: Principal, action: str, entity_id: str, payload: dict[str, Any]) -> None:
        svc.audit.append(
            actor=principal.name, actor_kind=ActorKind.PROPRIETAIRE if principal.owner else ActorKind.AGENT,
            action=action, entity="predrop", entity_id=entity_id, dry_run=False, payload=payload,
        )  # fmt: skip

    @app.post("/predrop/allocations", status_code=201)
    async def predrop_allocation(request: Request) -> PokeshopJSONResponse:
        """Allocation **ferme** (confirmation fournisseur) : propriétaire ou workflow 03 après sa validation.

        Jamais déclarée par l'agent qui bénéficie du pré-drop. Le fournisseur doit être connu du moteur pour la
        référence (lien du catalogue, offre évaluée, cycle sur le catalogue du registre) — sinon 409, sauf
        propriétaire. Même confirmation et même contenu : sans effet ; une baisse passe par la réduction (409).
        """
        principal = require_api(request)
        _predrop_guard((CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"))
        body = await _body(request, PredropAllocationIn)
        entry = svc.catalog.entry_for(body.product_key)
        if entry is None or not entry.canonical:
            raise HTTPProblem(409, f"{body.product_key} : fiche canonique absente du catalogue validé")
        if not principal.owner and body.supplier_id not in _known_suppliers(entry.product_id, entry):
            raise HTTPProblem(
                409, f"fournisseur {body.supplier_id} inconnu du moteur pour {body.product_key} : allocation à poser par "
                "la propriétaire (confirmation fournisseur vérifiée)"
            )
        allocation, created = svc.predrop.set_allocation(FirmAllocation(
            **body.model_dump(), recorded_by=principal.name, recorded_at=svc.clock()))  # fmt: skip
        if created:
            _predrop_audit(principal, "predrop.allocation", allocation.product_key,
                           {"qty": allocation.qty, "supplier_id": allocation.supplier_id,
                            "supplier_confirmation_ref": allocation.supplier_confirmation_ref})  # fmt: skip
        return _ok({"allocation": allocation, "created": created}, 201 if created else 200)

    @app.post("/predrop/allocations/{product_key}/reduce")
    async def predrop_allocation_reduce(product_key: str, request: Request) -> PokeshopJSONResponse:
        """Réduction d'allocation : pré-drop servi en premier (ordre de paiement), quota drop réduit d'abord, puis
        remboursement intégral des dernières réservations (préparé, avec brouillon d'email ; validation de la
        propriétaire aux niveaux d'autonomie 1 et 2)."""
        principal = require_api(request)
        _predrop_guard((OrderRegister.STREAM, "registre des commandes"))
        body = await _body(request, PredropReduceIn)
        result = svc.predrop.reduce_allocation(
            product_key, body.new_qty, supplier_confirmation_ref=body.supplier_confirmation_ref, reason=body.reason,
            recorded_by=principal.name, at=svc.clock(), autonomy_level=int(svc.autonomy.level), shipped=_shipped,
        )  # fmt: skip
        if result.created:
            _predrop_audit(principal, "predrop.allocation_reduce", product_key,
                           {"previous_qty": result.reduction.previous_qty, "new_qty": result.reduction.new_qty,
                            "kept": list(result.plan.kept), "refunded": list(result.plan.refunded),
                            "drop_quota_after": result.plan.drop_quota_after})  # fmt: skip
        return _ok({"allocation": result.allocation, "plan": result.plan, "refunds": result.refunds,
                    "created": result.created})  # fmt: skip

    @app.post("/predrop/demand", status_code=201)
    async def predrop_demand(request: Request) -> PokeshopJSONResponse:
        """Compte **agrégé** d'inscrits consentants intéressés (workflow marketing) : aucune donnée personnelle."""
        principal = require_api(request)
        _predrop_guard()
        body = await _body(request, PredropDemandIn)
        now = svc.clock()
        if body.as_of - now > timedelta(minutes=5):
            raise HTTPProblem(409, "compte d'inscrits daté du futur : horloge non fiable")
        signal, created = svc.predrop.record_demand(DemandSignal(
            **body.model_dump(), recorded_by=principal.name, recorded_at=now))  # fmt: skip
        if created:
            _predrop_audit(principal, "predrop.demand", signal.product_key,
                           {"interested_consenting_subscribers": signal.interested_consenting_subscribers})  # fmt: skip
        return _ok({"signal": signal, "created": created}, 201 if created else 200)

    @app.get("/predrop/eligibility/{product_key}")
    def predrop_eligibility(product_key: str, request: Request) -> PokeshopJSONResponse:
        """Conditions du pré-drop évaluées sur les registres du moteur ; deux prix, sans coût ni marge."""
        require_api(request)
        _predrop_guard()
        return _ok({"enabled": svc.predrop_config.enabled, "signature": svc.predrop_config.signature,
                    "eligibility": _predrop_eligibility(product_key, market_ref=None).view()})  # fmt: skip

    @app.post("/predrop/open", status_code=201)
    async def predrop_open(request: Request) -> PokeshopJSONResponse:
        """Ouvre un pré-drop si **toutes** les conditions sont remplies (sinon 409 avec la liste).

        Référence marché : propriétaire seule (rôle : 403). Ouvert par un rôle avec une référence marché inconnue ou un
        prix drop en REVIEW : enregistré **en attente** de la propriétaire (aucune réservation acceptée). Ouvert par la
        propriétaire : ouvert (son acte vaut validation). Prix et paramètres figés à l'ouverture.
        """
        principal = require_api(request)
        _predrop_guard((CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"),
                       (CatalogApprovalBook.STREAM, "registre des validations de fiches"),
                       (CostRegister.STREAM, "registre de coûts historiques"))  # fmt: skip
        body = await _body(request, PredropOpenIn)
        if body.market_ref_chf is not None and not principal.owner:
            _predrop_audit(principal, "predrop.open.market_ref_refused", body.product_key,
                           {"motif": "référence marché déclarée par un rôle"})  # fmt: skip
            raise HTTPProblem(403, "référence marché : valeur décisive, posée par la propriétaire seule")
        now = svc.clock()
        tz = ZoneInfo(cfg.timezone)
        if body.drop_date <= now.astimezone(tz).date():
            raise HTTPProblem(422, "date du drop : postérieure à aujourd'hui")
        opens_at = body.opens_at or now
        if now - opens_at > timedelta(minutes=5):
            raise HTTPProblem(422, "ouverture dans le passé")
        drop_start = datetime.combine(body.drop_date, datetime.min.time(), tzinfo=tz)
        closes_at = body.closes_at or drop_start
        if closes_at > drop_start or closes_at <= opens_at:
            raise HTTPProblem(422, "fermeture des réservations : après l'ouverture et au plus tard au début du jour du drop")
        eligibility = _predrop_eligibility(body.product_key, market_ref=body.market_ref_chf)
        if not eligibility.eligible:
            _predrop_audit(principal, "predrop.open_refused", body.product_key, {"failed": list(eligibility.failed())})
            raise HTTPProblem(409, "pré-drop refusé : conditions non remplies (" + ", ".join(eligibility.failed()) + ")",
                              eligibility=eligibility.view())  # fmt: skip
        config = svc.predrop_config.config
        allocation = svc.predrop.allocation(body.product_key)
        entry = svc.catalog.entry_for(body.product_key)
        assert config is not None and allocation is not None and entry is not None and eligibility.prices is not None
        pending = bool(eligibility.needs_owner) and not principal.owner
        predrop = Predrop(
            predrop_id=f"PD-{body.product_key}-{body.drop_date:%Y%m%d}",
            product_key=body.product_key,
            public_sku=entry.listing.public_sku,
            allocation_ref=allocation.supplier_confirmation_ref,
            drop_date=body.drop_date,
            opens_at=opens_at,
            closes_at=closes_at,
            status="PENDING_OWNER" if pending else "OPEN",
            prices=eligibility.prices,
            config_version=config.predrop_version,
            config_fingerprint=config.fingerprint,
            premium_pct=config.premium_pct,
            predrop_share=config.predrop_share_of_allocation,
            reserve_min_units=config.safety_reserve_min_units,
            reserve_share=config.safety_reserve_share,
            per_customer_limit=config.per_customer_limit,
            priority_window_hours=config.priority_window_hours,
            demand_threshold=config.demand_threshold,
            demand_interested=eligibility.demand_interested or 0,
            demand_allocation=allocation.qty,
            demand_score=eligibility.demand_score or Decimal("0"),
            market_ref_chf=body.market_ref_chf,
            market_ref_attested_by=authz.OWNER if body.market_ref_chf is not None else None,
            requested_by=principal.name,
            requested_at=now,
            validated_by=authz.OWNER if principal.owner else None,
            validated_at=now if principal.owner else None,
            needs_owner=eligibility.needs_owner,
        )
        predrop, _ = svc.predrop.open(predrop)
        _predrop_audit(principal, "predrop.open", predrop.predrop_id,
                       {"status": predrop.status, "needs_owner": list(predrop.needs_owner),
                        "prix_drop_chf": predrop.prices.drop_price, "prix_predrop_chf": predrop.prices.predrop_price})  # fmt: skip
        view = _predrop_view(predrop, now)
        offer = public_offer(predrop, accepting=bool(view["accepting"])) if predrop.status == "OPEN" else None
        return _ok({"predrop": view, "offer": offer}, 201)

    @app.post("/predrop/{predrop_id}/approve")
    async def predrop_approve(predrop_id: str, request: Request) -> PokeshopJSONResponse:
        """Validation par la propriétaire d'un pré-drop en attente : conditions réévaluées (référence marché attestée
        ou inconnue assumée), prix recalculés et figés, ouverture."""
        principal = require_api(request)
        if not principal.owner:  # matrice : propriétaire seule (défense en profondeur)
            raise HTTPProblem(403, "validation d'un pré-drop : jeton propriétaire")
        _predrop_guard((CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"),
                       (CatalogApprovalBook.STREAM, "registre des validations de fiches"))  # fmt: skip
        body = await _body(request, PredropApproveIn)
        predrop = svc.predrop.get(predrop_id)
        if predrop is None:
            raise HTTPProblem(404, f"pré-drop {predrop_id} inconnu")
        if predrop.status != "PENDING_OWNER":
            raise HTTPProblem(409, f"pré-drop {predrop_id} : {predrop.status}, rien à valider")
        eligibility = _predrop_eligibility(predrop.product_key, market_ref=body.market_ref_chf, ignore=predrop_id)
        if not eligibility.eligible or eligibility.prices is None:
            raise HTTPProblem(409, "validation refusée : conditions non remplies (" + ", ".join(eligibility.failed()) + ")",
                              eligibility=eligibility.view())  # fmt: skip
        now = svc.clock()
        approved = predrop.model_copy(update={
            "status": "OPEN", "prices": eligibility.prices, "opens_at": max(predrop.opens_at, now),
            "market_ref_chf": body.market_ref_chf,
            "market_ref_attested_by": authz.OWNER if body.market_ref_chf is not None else None,
            "validated_by": authz.OWNER, "validated_at": now, "needs_owner": eligibility.needs_owner,
        })  # fmt: skip
        if approved.opens_at >= approved.closes_at:
            raise HTTPProblem(409, "fermeture des réservations déjà passée : rouvrir un nouveau pré-drop")
        svc.predrop.update(approved)
        _predrop_audit(principal, "predrop.approve", predrop_id,
                       {"reason": body.reason, "market_ref_chf": body.market_ref_chf,
                        "prix_predrop_chf": approved.prices.predrop_price})  # fmt: skip
        return _ok({"predrop": _predrop_view(approved, now)})

    @app.post("/predrop/{predrop_id}/close")
    async def predrop_close(predrop_id: str, request: Request) -> PokeshopJSONResponse:
        """Ferme un pré-drop (acte protecteur) : plus aucune réservation acceptée ; les unités non réservées vont au drop."""
        principal = require_api(request)
        _predrop_guard()
        body = await _body(request, PredropCloseIn)
        now = svc.clock()
        closed, changed = svc.predrop.close(predrop_id, by=principal.name, at=now, reason=body.reason)
        if changed:
            _predrop_audit(principal, "predrop.close", predrop_id, {"reason": body.reason})
        return _ok({"predrop": _predrop_view(closed, now), "changed": changed})

    @app.get("/predrop/offers")
    def predrop_offers(request: Request) -> PokeshopJSONResponse:
        """Offres publiques (statut « Réservations ouvertes / fermées », date du drop, deux prix, garantie, aucune
        différence remboursée ; ni compte à rebours, ni « plus que N », ni coût, ni marge) et lecture interne."""
        require_api(request)
        _predrop_guard()
        now = svc.clock()
        offers, internal = [], []
        for predrop in svc.predrop.predrops():
            if predrop.status == "PENDING_OWNER":
                internal.append(_predrop_view(predrop, now))
                continue
            view = _predrop_view(predrop, now)
            offers.append(public_offer(predrop, accepting=bool(view["accepting"])))
            internal.append(view)
        return _ok({"enabled": svc.predrop_config.enabled, "signature": svc.predrop_config.signature,
                    "simulation": cfg.dry_run, "offers": offers, "internal": internal})  # fmt: skip

    @app.post("/predrop/reservations", status_code=201)
    async def predrop_reservation(request: Request) -> PokeshopJSONResponse:
        """Réservation **payée** (workflow 02) : idempotente par commande, enregistrée atomiquement.

        Jamais refusée pour un motif métier (le client a payé) : hors quota, limite par client atteinte, hors fenêtre
        prioritaire, montant ≠ prix pré-drop × quantité, pré-drop fermé, désactivé ou suspendu (gel, quarantaine)
        => non servie et **remboursement intégral préparé** (validation de la propriétaire aux niveaux 1 et 2).
        L'argent encaissé est une dette jusqu'à l'expédition (photo du stop-loss) ; chiffre d'affaires reconnu à
        l'expédition (``POST /orders/shipped``).
        """
        principal = require_api(request)
        _predrop_guard((CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"))
        body = await _body(request, PredropReservationIn)
        now = svc.clock()
        if body.paid_at - now > timedelta(minutes=5):
            raise HTTPProblem(409, "paiement daté du futur : horloge non fiable")
        predrop = svc.predrop.get(body.predrop_id)
        blocked = None
        if predrop is not None:
            blocked = _predrop_block(svc.catalog.entry_for(predrop.product_key), predrop.product_key)
        reservation, refund, created = svc.predrop.record_reservation(
            predrop_id=body.predrop_id, order_id=body.order_id, customer_ref=body.customer_ref, qty=body.qty,
            amount_paid_ttc=body.amount_paid_ttc, paid_at=body.paid_at, priority_access=body.priority_access,
            recorded_by=principal.name, at=now, enabled=svc.predrop_config.enabled, blocked_reason=blocked,
            autonomy_level=int(svc.autonomy.level),
        )  # fmt: skip
        if created:
            _predrop_audit(principal, "predrop.reservation", reservation.order_id,
                           {"predrop_id": reservation.predrop_id, "status": reservation.status,
                            "not_served_reason": reservation.not_served_reason, "qty": reservation.qty,
                            "amount_paid_ttc": reservation.amount_paid_ttc, "blocked": blocked,
                            "refund_status": refund.status if refund is not None else None})  # fmt: skip
        return _ok({"reservation": reservation.public_view(), "refund": refund, "created": created,
                    "state": svc.predrop.reservation_state(reservation.order_id, _shipped)},
                   201 if created else 200)  # fmt: skip

    @app.get("/predrop/reservations")
    def predrop_reservations(request: Request, predrop_id: str | None = None) -> PokeshopJSONResponse:
        """Réservations (sans identifiant client) avec leur état dérivé (expédiée, remboursée…)."""
        require_api(request)
        _predrop_guard((OrderRegister.STREAM, "registre des commandes"))
        rows = [{**r.public_view(), "state": svc.predrop.reservation_state(r.order_id, _shipped)}
                for r in svc.predrop.reservations(predrop_id)]  # fmt: skip
        return _ok({"reservations": rows,
                    "collected_not_delivered": svc.predrop.outstanding_debt(as_of=svc.clock(), shipped=_shipped)})  # fmt: skip

    @app.get("/predrop/refunds")
    def predrop_refunds(request: Request, status: str | None = None) -> PokeshopJSONResponse:
        """Remboursements préparés (en attente de la propriétaire, approuvés, exécutés) et brouillons d'email."""
        require_api(request)
        _predrop_guard()
        return _ok({"refunds": svc.predrop.refunds(status)})

    @app.post("/predrop/refunds/{refund_id}/approve")
    async def predrop_refund_approve(refund_id: str, request: Request) -> PokeshopJSONResponse:
        """Validation de la propriétaire **en un clic** d'un remboursement préparé (corps vide admis)."""
        principal = require_api(request)
        if not principal.owner:  # matrice : propriétaire seule (défense en profondeur)
            raise HTTPProblem(403, "validation d'un remboursement : jeton propriétaire")
        _predrop_guard()
        refund, changed = svc.predrop.approve_refund(refund_id, by=authz.OWNER, at=svc.clock())
        if changed:
            _predrop_audit(principal, "predrop.refund_approve", refund_id,
                           {"order_id": refund.order_id, "amount_ttc": refund.amount_ttc})  # fmt: skip
        return _ok({"refund": refund, "changed": changed})

    @app.post("/predrop/refunds/{refund_id}/executed")
    async def predrop_refund_executed(refund_id: str, request: Request) -> PokeshopJSONResponse:
        """Remboursement exécuté par le PSP (relevé du workflow 02) : approuvé seulement (sinon 409) ; la dette sort."""
        principal = require_api(request)
        _predrop_guard()
        body = await _body(request, PredropRefundExecutedIn)
        refund, changed = svc.predrop.mark_refund_executed(
            refund_id, by=principal.name, at=svc.clock(), executed_at=body.executed_at, psp_refund_ref=body.psp_refund_ref
        )
        if changed:
            _predrop_audit(principal, "predrop.refund_executed", refund_id,
                           {"order_id": refund.order_id, "psp_refund_ref": refund.psp_refund_ref})  # fmt: skip
        return _ok({"refund": refund, "changed": changed})

    def _engine_refusal(event: str, label: str) -> Callable[[str], None]:
        def hook(motif: str) -> None:
            if svc.stoploss_engine is not None:
                svc.stoploss_engine.record_refused_attempt(
                    event, now=svc.clock(), actor="inconnu", detail=f"{label}{motif}"
                )

        return hook

    owner_refusal_hooks.update(
        {
            "stoploss.rearm": _engine_refusal("REARM_REFUSED", "en-tête propriétaire "),
            "stoploss.baseline": _engine_refusal("BASELINE_REFUSED", "en-tête propriétaire "),
            "stoploss.capital_reset": _engine_refusal("REARM_REFUSED", "mémoire des apports : en-tête "),
        }
    )

    from .api_dashboard import build_dashboard_router  # tableau de bord interne (lecture seule)

    app.include_router(build_dashboard_router(svc, require_api=require_api))
    return app
