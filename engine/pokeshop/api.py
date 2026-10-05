"""API HTTP interne du moteur (FastAPI), appelée par n8n et le tableau de bord (agent integrations).

* **Authentification** : toutes les routes sauf ``/health`` exigent l'en-tête
  ``X-Pokeshop-Token`` : jeton commun (``POKESHOP_API_TOKEN_SHA256``, acteur « api ») ou **jeton
  nommé** d'un agent (``POKESHOP_AGENT_TOKENS_SHA256``) dont le nom **devient l'acteur** (un champ
  ``actor``/``requested_by`` déclaré est ignoré ou refusé s'il diffère). Un acteur qui se dit
  « propriétaire » sans jeton propriétaire valide est refusé (403). Sans empreinte configurée, les
  routes internes répondent 503 (fermé par défaut). Les actes réservés à la propriétaire
  (réarmement du stop-loss global, point zéro ``/stoploss/baseline``, mémoire des apports, hausse du
  niveau d'autonomie, reprise d'un incident critique, taux de change ``/fx/rates``) exigent **en plus**
  ``X-Pokeshop-Owner-Token``, distinct du jeton d'API ; tout refus est journalisé. Un réarmement
  rebasé exige ``reference_chf`` : la valeur nette de la photo, **attestée** par la propriétaire.
* **Valeurs décisives jamais auto-déclarées** : ``/mandate/check`` ignore toute trésorerie du corps
  et lit les registres du moteur (photo stop-loss acceptée, solde PayPal relevé, taux de référence,
  propositions de réassort enregistrées) ; une photo déposée par le jeton qui demande la dépense
  (ou par le jeton commun) n'est pas vérifiable (``TREASURY_UNVERIFIED`` => validation humaine).
  ``/stoploss/state`` remplace plafond jour pub et budget stock de la photo par ceux du mandat
  signé et des règles. ``/northstar/entries`` refuse tout coût historique (registre interne
  ``/costs/movements`` uniquement) ; un lot est atomique.
* **Seuils signés** : stop-loss (``POKESHOP_STOPLOSS_FINGERPRINT``) et règles de prix
  (``POKESHOP_RULES_FINGERPRINT``) : empreinte différente => service gelé (``CONFIG_UNSIGNED``) ;
  absente => seuils les plus stricts entre fichier et référence du code. Un écart entre sources
  d'une même règle (``consistency_errors``) gèle aussi le service.
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
  les cycles persistés et ``consecutive_clean_runs`` (critère de recette BP §13).
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
  synchronisation et frais, cycles de synchronisation, apports de capital, activité publicitaire.
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

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from . import __version__
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
from .models import BasketLine, Discount, PriceEvent, ReorderCandidate, VatMode, canonical_hash, explain
from .northstar import (
    ContributionEntry,
    CostMovement,
    CostRegister,
    NorthStarError,
    NorthStarLedger,
    NorthStarPersistenceError,
)
from .pricing import basket_contribution, decide_price
from .publish import (
    CatalogListing,
    PriceApprovalBook,
    PriceApprovalPersistenceError,
    PriceValidation,
    SensitiveFieldError,
    build_publication,
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
    BankBalanceReading,
    CapitalRegister,
    PhotoSourcesError,
    build_activity_photo,
)
from .sync import (
    WORKFLOW_SUPPLIER_TO_SHOP,
    BaselinePersistenceError,
    ImportBaselineStore,
    OfferCostInputs,
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
    """Porteur du jeton d'API : jeton commun (« api », non attribuable) ou jeton nommé d'un agent."""

    name: str
    named: bool


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
    balance_statement: BalanceStatement | None = None
    """Dernière déclaration des dettes et créances (mémoire, comme les soldes ; jamais supposée nulle)."""

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
            channels.append(WebhookNotifier(cfg.n8n_webhook_url, dry_run=cfg.notify_dry_run))
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
            capital = CapitalRegister.restore(journal_for(CapitalRegister.STREAM))
        except ActivityRegisterPersistenceError as exc:
            capital = CapitalRegister(store=failed(CapitalRegister.STREAM, exc))
        try:
            ads = AdsActivityRegister.restore(journal_for(AdsActivityRegister.STREAM))
        except ActivityRegisterPersistenceError as exc:
            ads = AdsActivityRegister(store=failed(AdsActivityRegister.STREAM, exc))
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
    actor: str = "agent-05-finance"

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


class PublishPreviewIn(_In):
    """Aperçu de publication : fiche + coût rendu (jamais renvoyé).

    Aucune « validation de prix » dans le corps : l'approbation éventuelle est lue dans le registre
    du moteur (``POST /pricing/approvals``, jeton propriétaire) ; le statut de stock est recalculé.
    """

    listing: CatalogListing
    quote: QuoteIn | None = None
    reference_price_24h: PositiveMoney | None = None
    stoploss_blocked: bool = False
    sensitive_terms: list[str] = Field(default_factory=list)


class CatalogItemIn(_In):
    product_id: str
    supplier_links: list[SupplierLink] = Field(default_factory=list)
    listing: CatalogListing


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
    """Dettes et créances à date (agent finance ou connecteur, jeton nommé) ; listes vides = « aucune », attesté."""

    as_of: datetime
    preorders_collected_chf: NonNegativeMoney
    debts: list[BalanceItem] = Field(default_factory=list, max_length=200)
    receivables: list[BalanceItem] = Field(default_factory=list, max_length=200)
    source: str = Field(min_length=3, max_length=300)


class AdsActivityIn(_In):
    """Dépenses publicitaires (campagne, jour) et commandes attribuées, relevées par le connecteur publicitaire."""

    ad_spends: list[AdSpend] = Field(default_factory=list, max_length=2000)
    attributed_orders: list[AttributedOrder] = Field(default_factory=list, max_length=5000)


class SyncIn(_In):
    """Cycle fournisseur → site (simulation par défaut).

    Sans ``catalog`` dans le corps, le moteur lit son catalogue validé (``POST /catalog/items``) ; sans
    l'un ni l'autre : 409 « catalogue requis ». Sans ``cost_inputs``, frais du registre
    (``POST /catalog/cost-inputs``) et taux de la propriétaire (``POST /fx/rates``).
    """

    supplier: str
    source_path: str
    dry_run: bool = True
    catalog: list[CatalogItemIn] = Field(default_factory=list)
    cost_inputs: dict[str, OfferCostInputs] = Field(default_factory=dict)
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
    """Point zéro du capital engagé, déclaré par la propriétaire (STOP_LOSS.md §5, option A ou B)."""

    reason: str = Field(min_length=10)
    reference_chf: Money


class MandateCheckIn(_In):
    """Demande de dépense ; ``treasury`` éventuel est **ignoré** (trésorerie lue dans les registres du moteur)."""

    request: SpendRequest
    treasury: TreasurySnapshot | None = None
    record: bool = False


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


class NorthStarEntriesIn(_In):
    entries: list[ContributionEntry] = Field(min_length=1)


# --------------------------------------------------------------------------- application


def _token_ok(token: str | None, expected: str | None) -> bool:
    if not token or not expected:
        return False
    return hmac.compare_digest(sha256_hex(token), expected)


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> FastAPI:
    """Application FastAPI (fabrique : ``uvicorn pokeshop.api:create_app --factory``)."""
    svc = services or Services.build(settings)
    cfg = svc.settings
    app = FastAPI(
        title="Moteur boutique Pokémon JCC FR — API interne",
        version=__version__,
        description="API interne appelée par n8n. Montants CHF en chaînes. Simulation par défaut.",
        default_response_class=PokeshopJSONResponse,
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
        (StockPersistenceError, 503),
        (SyncRegistryPersistenceError, 503),
        (ActivityRegisterPersistenceError, 503),
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
        """Jeton commun (acteur « api ») ou jeton nommé (acteur = nom de l'agent, jamais auto-déclaré)."""
        if cfg.api_token_sha256 is None and not cfg.agent_tokens_sha256:
            raise HTTPProblem(
                503,
                "jeton d'API non configuré (POKESHOP_API_TOKEN_SHA256 ou POKESHOP_AGENT_TOKENS_SHA256) : "
                "routes internes fermées",
            )
        token = request.headers.get(API_TOKEN_HEADER)
        found: Principal | None = None
        if token:
            digest = sha256_hex(token)
            if cfg.api_token_sha256 is not None and hmac.compare_digest(digest, cfg.api_token_sha256):
                found = Principal("api", False)
            for name, expected in cfg.agent_tokens_sha256.items():  # parcours complet (temps constant)
                if hmac.compare_digest(digest, expected):
                    found = Principal(name, True)
        if found is None:
            raise HTTPProblem(401, f"en-tête {API_TOKEN_HEADER} absent ou invalide")
        return found

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
                "persistence": {
                    "backend": svc.state_backend,
                    "restored": not svc.restore_errors,
                    "unreadable": sorted(svc.restore_errors),
                },
                # Alertes d'incident en temps réel vers n8n (workflow 04) : simulées tant que
                # POKESHOP_NOTIFY_DRY_RUN n'est pas false (le digest 05 le signale chaque matin).
                "notifications": {
                    "webhook_configured": cfg.n8n_webhook_url is not None,
                    "webhook_dry_run": cfg.notify_dry_run,
                    "real_time_alerts": cfg.n8n_webhook_url is not None and not cfg.notify_dry_run,
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
        """Réception physique en stock local (registre persisté) ; idempotente par (SKU, référence)."""
        principal = require_api(request)
        _persistence_guard(PersistentStockRegistry.STREAM, "journal du stock local")
        body = await _body(request, StockReceiveIn)
        actor = principal.name
        try:
            level, replayed = svc.stock.receive_once(body.sku, body.qty, body.ref, at=svc.clock())
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
        require_api(request)
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
            actor="n8n",
            actor_kind=ActorKind.SYSTEME,
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
                    }
                    for e in svc.catalog.entries()
                ],
                "cost_inputs": svc.catalog.all_costs(),
            }
        )

    def _registry_cost_inputs(mapping: Any, now: datetime) -> dict[str, OfferCostInputs]:
        """Frais du registre ; taux de la propriétaire (``POST /fx/rates``) seulement, sinon coût incomplet."""
        entry = svc.catalog.costs(mapping.supplier_id)
        if entry is None:
            return {}
        rate = svc.fx_rates.reference(entry.currency, now) if entry.currency != "CHF" else None
        return {
            mapping.supplier_id: entry.to_offer_inputs(
                allowed_currencies=tuple(mapping.allowed_currencies),
                fx_rate=rate.rate_to_chf if rate is not None else None,
                fx_source=rate.source if rate is not None else None,
                fx_date=rate.rate_date if rate is not None else None,
            )
        }

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
            cost_inputs = dict(body.cost_inputs)
        else:
            for stream, what in (
                (CatalogRegistry.COSTS_STREAM, "frais fournisseurs"),
                (FxRateBook.STREAM, "registre des taux de change"),
            ):
                _persistence_guard(stream, what)
            cost_inputs = _registry_cost_inputs(mapping, now)
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
            SyncRunSummary.from_report(report, catalog_source=catalog_source, recorded_by=principal.name)
        )
        return _ok(
            {
                "report": report,
                "clean": summary.status == "PROPRE",
                "cycle_status": summary.status,
                "offers_costed": summary.offers_costed,
                "catalog_source": catalog_source,
                "consecutive_clean_runs": svc.sync_runs.consecutive_clean_runs(),
                "report_markdown": report.render_markdown(),
            }
        )

    @app.get("/sync/history")
    def sync_history(request: Request, limit: int = 50) -> PokeshopJSONResponse:
        """Cycles de synchronisation persistés et cycles PROPRES consécutifs (critère de recette BP §13)."""
        require_api(request)
        _persistence_guard(SyncRunLog.STREAM, "journal des cycles de synchronisation")
        streak = svc.sync_runs.consecutive_clean_runs()
        return _ok(
            {
                "consecutive_clean_runs": streak,
                "target": CLEAN_RUNS_TARGET,
                "criterion_met": streak >= CLEAN_RUNS_TARGET,
                "definition": "PROPRE = aucune erreur critique et au moins une offre au coût rendu calculé ; "
                "VIDE (rien évalué) ne compte pas et n'interrompt pas la série ; ANOMALIES la remet à zéro.",
                "runs": svc.sync_runs.runs(limit=max(1, min(limit, 500))),
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
            actor_kind=ActorKind.AGENT,
            simulation=body.simulation,
        )
        svc.gate.invalidate()
        return _ok({"incident": incident, "notification": svc.incidents.notification_for(incident.incident_id)}, 201)

    @app.post("/incidents/{incident_id}/test")
    async def incidents_test(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Enregistre le test de correction (préalable à toute reprise).

        Un test **réussi** déclaré par un agent doit désigner (``test_ref``) un cycle de synchronisation
        en simulation (``POST /sync/run``) exécuté **après** l'ouverture de l'incident, sans erreur
        critique, et par un autre jeton nommé que celui qui a ouvert l'incident ; la propriétaire
        (jeton propriétaire) peut attester librement.
        """
        principal = require_api(request)
        body = await _body(request, IncidentTestIn)
        incident = svc.incidents.get(incident_id)
        token = request.headers.get(OWNER_TOKEN_HEADER)
        owner = owner_verified(request)
        if token and not owner:
            raise HTTPProblem(403, "jeton propriétaire invalide")
        actor = "propriétaire" if owner else actor_of(principal, body.actor, request, route="incidents.test")
        if body.passed and not owner:
            run = next((r for r in reversed(svc.sync.history) if r.run_id == body.test_ref), None)
            started = getattr(run, "started_at", None) or getattr(run, "at", None)
            problem = None
            if run is None or started is None:
                problem = "test_ref doit être l'identifiant d'un cycle POST /sync/run en simulation de ce service"
            elif not run.dry_run or run.critical_errors:
                problem = "le cycle cité n'est pas une simulation propre (erreurs critiques ou écriture réelle)"
            elif started < incident.opened_at:
                problem = "le cycle cité précède l'ouverture de l'incident : rejouer après la correction"
            elif principal.named and incident.opened_by == principal.name:
                problem = "test auto-attesté : un autre agent (agent 12 QA) doit enregistrer le test"
            if problem is not None:
                svc.audit.append(
                    actor=actor,
                    actor_kind=ActorKind.AGENT,
                    action="incident.test_refused",
                    entity="incident",
                    entity_id=incident_id,
                    dry_run=incident.simulation,
                    payload={"test_ref": body.test_ref, "motif": problem},
                )
                raise HTTPProblem(409, f"test non vérifiable : {problem}")
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
        """Dépose la photo d'activité (construite par les workflows) puis l'évalue.

        La photo est d'abord évaluée à part : refusée (périmée, datée du futur, sans apport ou avec des
        apports en baisse : fermé par défaut), elle ne remplace **jamais** la dernière photo valide (409).
        Plafond jour pub et budget stock sont ceux du moteur (mandat signé actif, règles), jamais ceux
        postés (``overridden`` liste les écarts). Acceptée, elle est enregistrée (journal d'état
        ``stoploss_photo``, avec l'acteur déduit du jeton) avant de devenir la photo en vigueur.
        """
        principal = require_api(request)
        engine = _require_engine()
        posted = await _body(request, StopLossState)
        return _accept_photo(principal, engine, posted, origin="déposée")

    def _accept_photo(
        principal: Principal,
        engine: StopLossEngine,
        posted: StopLossState,
        *,
        origin: str,
        sources: dict[str, Any] | None = None,
    ) -> PokeshopJSONResponse:
        """Évalue à part, enregistre puis met en vigueur une photo (déposée ou construite par le moteur)."""
        now = svc.clock()
        body, overridden = svc.authoritative_photo(posted, now)
        try:
            engine.validate_photo(body, now)
        except StopLossError as exc:
            raise HTTPProblem(
                409, f"photo refusée : {exc}", previous_photo_kept=svc.stoploss_state is not None
            ) from None
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
        for stream, what in (
            (CapitalRegister.STREAM, "registre des apports"),
            (CostRegister.STREAM, "registre de coûts historiques"),
            (CatalogRegistry.CATALOG_STREAM, "catalogue de synchronisation"),
            (AdsActivityRegister.STREAM, "registre de l'activité publicitaire"),
            (PersistentPriceHistory.STREAM, "historique des prix"),
        ):
            _persistence_guard(stream, what)
        now = svc.clock()
        try:
            state, sources = build_activity_photo(
                now=now,
                capital=svc.capital,
                paypal=svc.paypal_balance,
                bank=svc.bank_balance,
                balances=svc.balance_statement,
                costs=svc.costs,
                catalog=svc.catalog,
                price_history=svc.price_history,
                replacement_costs=svc.sync.replacement_costs,
                params=svc.rules.pricing,
                stock_budget_chf=svc.rules.stock.stock_budget_chf,
                ads_daily_cap_chf=None,
                ads=svc.ads,
                max_age=timedelta(hours=engine.config.state_max_age_hours),
            )
        except PhotoSourcesError as exc:
            svc.audit.append(
                actor=principal.name,
                actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
                action="stoploss.refresh_refused",
                entity="stoploss",
                entity_id="photo",
                dry_run=False,
                payload={"problems": exc.problems},
            )
            raise HTTPProblem(
                409, str(exc), manquantes=exc.problems, previous_photo_kept=svc.stoploss_state is not None
            ) from None
        return _accept_photo(principal, engine, state, origin="registres du moteur", sources=sources)

    @app.get("/stoploss/status")
    def stoploss_status(request: Request) -> PokeshopJSONResponse:
        """État des six stop-loss sur la dernière photo ; verrou global toujours rapporté."""
        require_api(request)
        engine = _require_engine()
        status, triggers = svc.gate.stoploss_status()
        state = svc.stoploss_state
        reference = (
            {
                "net_worth_chf": net_worth(state.net_worth, engine.config).total,
                "photo_as_of": state.as_of,
                "photo_sha256": canonical_hash(state),
            }
            if state is not None
            else None
        )
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
        """Point zéro du capital engagé : **propriétaire uniquement** (jeton distinct, motif, journal persisté)."""
        require_api(request)
        engine = _require_engine()
        token = owner_token(
            request,
            required=True,
            route="stoploss.baseline",
            on_refused=lambda motif: engine.record_refused_attempt(
                "BASELINE_REFUSED", now=svc.clock(), actor="inconnu", detail=f"en-tête propriétaire {motif}"
            ),
        )
        body = await _body(request, BaselineIn)
        now = svc.clock()
        if svc.stoploss_state is None:
            raise HTTPProblem(
                409, "photo d'activité requise (POST /stoploss/state) : le point zéro mémorise les apports du moment"
            )
        try:
            entry = engine.set_baseline(
                token or "", body.reason, now=now, state=svc.stoploss_state, reference_chf=body.reference_chf
            )
        except RearmRefusedError:
            svc.audit.append(
                actor="inconnu",
                actor_kind=ActorKind.AGENT,
                action="stoploss.baseline_refused",
                entity="stoploss",
                entity_id="global",
                dry_run=False,
                payload={"reason": body.reason},
            )
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
        if principal.named and requester != principal.name:
            raise HTTPProblem(403, f"requested_by « {requester} » ≠ agent du jeton « {principal.name} »")
        if not principal.named:
            requester = actor_of(principal, requester, request, route="mandate.check")
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
        if svc.balance_statement is not None:
            posters.append(("Dettes et créances", svc.balance_statement.recorded_by))
        for label, poster in posters:
            # Vérifiable seulement si demande et dépôt viennent de deux jetons nommés distincts.
            if not principal.named or poster is None or poster == "api" or poster == principal.name:
                unverified.append(label)
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
            }
        )

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
        """Dépose le solde du compte PayPal dédié relevé par un connecteur (acteur déduit du jeton)."""
        principal = require_api(request)
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
        """Dépose le solde du compte bancaire de l'activité relevé par un connecteur (acteur déduit du jeton)."""
        principal = require_api(request)
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
        """Déclare les dettes et créances à date (précommandes encaissées, factures non payées, TVA, transit)."""
        principal = require_api(request)
        body = await _body(request, BalanceItemsIn)
        now = svc.clock()
        if body.as_of - now > timedelta(minutes=5):
            raise HTTPProblem(409, "déclaration datée du futur : horloge non fiable")
        if svc.balance_statement is not None and body.as_of < svc.balance_statement.as_of:
            raise HTTPProblem(409, "déclaration plus ancienne que celle en vigueur : refusée (jamais de retour en arrière)")
        statement = BalanceStatement(
            as_of=body.as_of,
            preorders_collected_chf=body.preorders_collected_chf,
            debts=tuple(body.debts),
            receivables=tuple(body.receivables),
            source=body.source,
            recorded_by=principal.name,
        )
        svc.balance_statement = statement
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="treasury.balance_items",
            entity="treasury",
            entity_id="dettes_creances",
            dry_run=False,
            payload={
                "as_of": body.as_of,
                "preorders_collected_chf": body.preorders_collected_chf,
                "debts": [d.model_dump(mode="json") for d in body.debts],
                "receivables": [r.model_dump(mode="json") for r in body.receivables],
                "source": body.source,
            },
        )
        return _ok({"statement": statement})

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
        """Dépenses publicitaires et commandes attribuées relevées par le connecteur publicitaire."""
        principal = require_api(request)
        _persistence_guard(AdsActivityRegister.STREAM, "registre de l'activité publicitaire")
        body = await _body(request, AdsActivityIn)
        now = svc.clock()
        tz = svc.stoploss_config.tz if svc.stoploss_config is not None else UTC
        received = svc.ads.record(list(body.ad_spends), list(body.attributed_orders), today=now.astimezone(tz).date())
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="ads.activity",
            entity="ads",
            entity_id=str(received),
            dry_run=False,
            payload={"ad_spends": len(body.ad_spends), "attributed_orders": len(body.attributed_orders)},
        )
        return _ok({"received": received})

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
        if not svc.northstar.entries() and (start is None or end is None):
            return _ok({"cumulative": Decimal("0.00"), "rows": [], "markdown": "", "note": "aucune écriture"})
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
            }
        )

    @app.post("/northstar/entries")
    async def northstar_entries(request: Request) -> PokeshopJSONResponse:
        """Enregistre des écritures de contribution (idempotentes par ``entry_id``)."""
        principal = require_api(request)
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        body = await _body(request, NorthStarEntriesIn)
        # Lot atomique ; coût historique refusé (registre interne /costs/movements uniquement).
        added = svc.northstar.add_entries(body.entries)
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

    @app.post("/costs/movements")
    async def cost_movements(request: Request) -> PokeshopJSONResponse:
        """Registre de coûts historiques interne : seule voie du coût des ventes dans l'étoile polaire."""
        principal = require_api(request)
        _persistence_guard(CostRegister.STREAM, "registre de coûts historiques")
        _persistence_guard(NorthStarLedger.STREAM, "journal de l'étoile polaire")
        body = await _body(request, CostMovementIn)
        movement = CostMovement(**body.model_dump(), recorded_by=principal.name)
        added = svc.costs.apply(movement)
        ledger = svc.costs.ledger(movement.product_key)
        svc.audit.append(
            actor=principal.name,
            actor_kind=ActorKind.AGENT if principal.named else ActorKind.SYSTEME,
            action="costs.movement",
            entity="cost_ledger",
            entity_id=movement.product_key,
            dry_run=False,
            payload={"kind": movement.kind, "ref": movement.ref, "qty": movement.qty, "northstar_added": added},
        )
        return _ok({"northstar_added": added, "valuation": ledger.valuation() if ledger is not None else None})

    from .api_dashboard import build_dashboard_router  # tableau de bord interne (lecture seule)

    app.include_router(build_dashboard_router(svc))
    return app
