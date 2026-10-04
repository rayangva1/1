"""API HTTP interne du moteur (FastAPI), appelée par n8n et le tableau de bord (agent integrations).

* **Authentification** : toutes les routes sauf ``/health`` exigent l'en-tête
  ``X-Pokeshop-Token`` (comparé en temps constant à ``POKESHOP_API_TOKEN_SHA256``). Sans
  empreinte configurée, les routes internes répondent 503 (fermé par défaut). Les actes réservés
  à la propriétaire (réarmement du stop-loss global, hausse du niveau d'autonomie, reprise d'un
  incident critique) exigent **en plus** ``X-Pokeshop-Owner-Token``, distinct du jeton d'API.
* **Montants** : chaînes décimales en entrée (un nombre JSON à virgule est refusé : 422) et en
  sortie (``"209.90"``), CHF. Aucun ``float`` ne traverse l'API.
* **Simulation par défaut** : ``/imports/{supplier}/run`` est toujours en simulation ;
  ``/sync/run`` l'est sauf ``"dry_run": false`` explicite, qui passe ensuite par la porte de
  gouvernance (niveau d'autonomie, stop-loss, mandat) et par ``POKESHOP_DRY_RUN=false``.
* Les réponses internes peuvent contenir des coûts (cotation, panier) ; ``/publish/preview`` ne
  renvoie que la charge publique filtrée. Lancement : ``uvicorn pokeshop.api:create_app --factory``.
"""

from __future__ import annotations

import hmac
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from . import __version__
from .audit import (
    ActorKind,
    AuditLog,
    IdempotencyStore,
    InMemoryAuditLog,
    InMemoryIdempotencyStore,
    PostgresAuditLog,
    PostgresIdempotencyStore,
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
from .costs import PriceHistory
from .errors import PokeshopError
from .importers import ImporterError, MappingError, extension_table_for, load_mapping, run_import
from .incidents import (
    IncidentCode,
    IncidentError,
    IncidentManager,
    IncidentScope,
    IncidentStatus,
    LogNotifier,
    MultiNotifier,
    Notifier,
    PostgresIncidentSink,
    Severity,
    WebhookNotifier,
)
from .mandate import Mandate, SpendLedger, SpendRequest, TreasurySnapshot, check, load_mandate
from .models import BasketLine, Discount, ReorderCandidate, StockLevel, VatMode, explain
from .northstar import ContributionEntry, NorthStarError, NorthStarLedger
from .pricing import basket_contribution, decide_price
from .publish import CatalogListing, PriceValidation, SensitiveFieldError, build_publication
from .rules import RuleSet, load_rules
from .settings import REPO_ROOT, Settings, SettingsError, load_settings, sha256_hex
from .shopify_client import ShopifyAccessDeniedError, ShopifyClient, ShopifyError
from .stock import StockRegistry, propose_reorder, sellable_local
from .stoploss import (
    RearmRefusedError,
    StopLossConfig,
    StopLossEngine,
    StopLossError,
    StopLossState,
    load_stoploss_config,
    render_report,
)
from .sync import OfferCostInputs, SyncContext, SyncService

__all__ = ["Services", "create_app", "API_TOKEN_HEADER", "OWNER_TOKEN_HEADER", "FICTIF_EXTENSIONS_PATH"]

API_TOKEN_HEADER = "X-Pokeshop-Token"
OWNER_TOKEN_HEADER = "X-Pokeshop-Owner-Token"
FICTIF_EXTENSIONS_PATH = REPO_ROOT / "data" / "samples" / "FICTIF_extensions_aliases.yaml"
_SUPPLIER_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")
T = TypeVar("T", bound=BaseModel)


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
    raise ValueError(f"nombre décimal JSON interdit ({text}) : écrire le montant en chaîne, ex. \"{text}\"")


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


def _strict_money(value: Any) -> Any:
    if isinstance(value, (bool, float)):
        raise ValueError("montant en chaîne ou entier (jamais de float)")
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"montant invalide : {value!r}") from exc
    return value


Money = Annotated[Decimal, BeforeValidator(_strict_money)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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
    stock: StockRegistry
    price_history: PriceHistory
    client: ShopifyClient
    gate: GovernanceGate
    sync: SyncService
    load_errors: dict[str, str] = field(default_factory=dict)
    stoploss_state: StopLossState | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

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
        """Assemble les composants ; Postgres si ``POKESHOP_DATABASE_URL`` (ou ``connect``) est fourni."""
        cfg = settings or load_settings()
        now = clock or (lambda: datetime.now(UTC))
        errors: dict[str, str] = {}
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
        store: AutonomyStore
        if factory:
            store = PostgresAutonomyStore(factory)
        elif cfg.autonomy_state_path is not None:
            store = JsonFileAutonomyStore(cfg.autonomy_state_path)
        else:
            store = InMemoryAutonomyStore()
        autonomy = AutonomyController(
            store, audit=audit, owner_token_sha256=cfg.owner_token_sha256 or "", default_level=cfg.autonomy_level,
            clock=now,
        )  # fmt: skip
        channels: list[Notifier] = [notifier or LogNotifier()]
        if cfg.n8n_webhook_url:
            channels.append(WebhookNotifier(cfg.n8n_webhook_url, dry_run=cfg.notify_dry_run))
        incidents = IncidentManager(
            audit=audit, notifier=MultiNotifier(channels) if len(channels) > 1 else channels[0],
            on_critical=autonomy.on_critical_incident, sink=PostgresIncidentSink(factory) if factory else None,
            clock=now,
        )  # fmt: skip
        rules = load_rules(cfg.rules_path, cfg.vat_profile)
        config: StopLossConfig | None = None
        engine: StopLossEngine | None = None
        try:
            config = load_stoploss_config(cfg.stoploss_path)
            engine = StopLossEngine(config, owner_token_sha256=cfg.owner_token_sha256 or None)
        except PokeshopError as exc:
            errors["stoploss"] = str(exc)
        mandate: Mandate | None = None
        try:
            mandate = load_mandate(cfg.mandate_path, expected_fingerprint=cfg.mandate_fingerprint)
        except PokeshopError as exc:
            errors["mandate"] = str(exc)
        ledger = SpendLedger()
        client = ShopifyClient.from_settings(
            cfg, transport=shopify_transport, audit=audit, idempotency=idempotency, clock=now,
            **({"sleep": sleep} if sleep is not None else {}),
        )  # fmt: skip
        holder: dict[str, Any] = {}
        gate = GovernanceGate(
            autonomy, audit=audit, stoploss_engine=engine, state_provider=lambda: holder["svc"].stoploss_state,
            mandate_provider=lambda: holder["svc"].mandate, spend_ledger=ledger, incidents=incidents,
            real_writes_enabled=cfg.real_writes_enabled, clock=now,
        )  # fmt: skip
        history = PriceHistory()
        sync = SyncService(client=client, gate=gate, incidents=incidents, audit=audit, price_history=history, clock=now)
        svc = cls(
            settings=cfg, clock=now, audit=audit, idempotency=idempotency, autonomy=autonomy, incidents=incidents,
            rules=rules, stoploss_config=config, stoploss_engine=engine, mandate=mandate, spend_ledger=ledger,
            northstar=NorthStarLedger(timezone=cfg.timezone), stock=StockRegistry(clock=now), price_history=history,
            client=client, gate=gate, sync=sync, load_errors=errors,
        )  # fmt: skip
        holder["svc"] = svc
        return svc


# ------------------------------------------------------------------------- requêtes


class QuoteIn(_In):
    """Cotation d'un coût rendu (BP §4-5)."""

    cost_chf: Money
    profile: VatMode | None = None
    market_ref: Money | None = None
    current_public: Money | None = None
    unknown_fields: list[str] = Field(default_factory=list)
    candidate_price: Money | None = None
    small_product: bool | None = None
    offer_stale: bool = False
    previous_cost: Money | None = None


class BasketLineIn(_In):
    sku: str
    qty: int = Field(ge=1)
    unit_price_ttc: Money
    unit_cost: Money


class DiscountIn(_In):
    kind: Literal["PERCENT", "AMOUNT"]
    value: Money
    code: str | None = None


class BasketIn(_In):
    """Panier multi-produits (frais par commande comptés une fois)."""

    lines: list[BasketLineIn] = Field(min_length=1)
    shipping_charged: Money = Decimal("0")
    discount: DiscountIn | None = None
    shipping_cost_actual: Money | None = None
    profile: VatMode | None = None


class SellableIn(_In):
    """Stock vendable : registre du service (``sku``) ou calcul direct."""

    sku: str | None = None
    on_hand: int | None = Field(default=None, ge=0)
    reserved: int = Field(default=0, ge=0)
    damaged: int = Field(default=0, ge=0)
    safety: int = Field(default=0, ge=0)


class ReorderIn(_In):
    """Proposition de réassort (jamais une commande)."""

    candidates: list[ReorderCandidate]
    budget_available: Money
    stock_budget_total: Money | None = None
    extension_exposure: dict[str, Money] = Field(default_factory=dict)
    cap_exceptions: dict[str, Money] = Field(default_factory=dict)
    actor: str = "agent-05-finance"


class ImportIn(_In):
    """Import en simulation d'un fichier du dossier autorisé (``POKESHOP_IMPORTS_DIR``)."""

    source_path: str = Field(min_length=1)
    source_ts: datetime | None = None


class PublishPreviewIn(_In):
    """Aperçu de publication : fiche + coût rendu (jamais renvoyé) ou décision déjà calculée."""

    listing: CatalogListing
    quote: QuoteIn | None = None
    reference_price_24h: Money | None = None
    price_validation: PriceValidation | None = None
    stoploss_blocked: bool = False
    sensitive_terms: list[str] = Field(default_factory=list)


class CatalogItemIn(_In):
    product_id: str
    supplier_links: list[SupplierLink] = Field(default_factory=list)
    listing: CatalogListing


class SyncIn(_In):
    """Cycle fournisseur → site (simulation par défaut)."""

    supplier: str
    source_path: str
    dry_run: bool = True
    catalog: list[CatalogItemIn] = Field(default_factory=list)
    cost_inputs: dict[str, OfferCostInputs] = Field(default_factory=dict)
    market_refs: dict[str, Money] = Field(default_factory=dict)
    price_validations: dict[str, PriceValidation] = Field(default_factory=dict)
    source_ts: datetime | None = None


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
    reason: str = Field(min_length=10)
    rebase: bool = True


class MandateCheckIn(_In):
    request: SpendRequest
    treasury: TreasurySnapshot
    record: bool = False


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

    for exc_type, status in (
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

    def require_api(request: Request) -> None:
        if cfg.api_token_sha256 is None:
            raise HTTPProblem(503, "jeton d'API non configuré (POKESHOP_API_TOKEN_SHA256) : routes internes fermées")
        if not _token_ok(request.headers.get(API_TOKEN_HEADER), cfg.api_token_sha256):
            raise HTTPProblem(401, f"en-tête {API_TOKEN_HEADER} absent ou invalide")

    def owner_token(request: Request, *, required: bool) -> str | None:
        token = request.headers.get(OWNER_TOKEN_HEADER)
        if token and token == request.headers.get(API_TOKEN_HEADER):
            raise HTTPProblem(403, "jeton propriétaire identique au jeton d'API : jetons distincts exigés")
        if required and not token:
            raise HTTPProblem(403, f"acte réservé à la propriétaire : en-tête {OWNER_TOKEN_HEADER} requis")
        return token

    def params_for(profile: VatMode | None) -> Any:
        if profile is None or profile is svc.rules.profile:
            return svc.rules.pricing
        return load_rules(cfg.rules_path, profile).pricing

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
            body.cost_chf, params_for(body.profile), body.market_ref, body.current_public, body.unknown_fields,
            candidate_price=body.candidate_price, small_product=body.small_product, offer_stale=body.offer_stale,
            previous_cost=body.previous_cost,
        )  # fmt: skip
        return _ok({"decision": decision, "labels_fr": explain(decision.reasons), "publishable": decision.is_publishable})

    @app.post("/pricing/basket")
    async def pricing_basket(request: Request) -> PokeshopJSONResponse:
        """Contribution d'un panier ; BLOCKED sous 12 % ou 8 CHF."""
        require_api(request)
        body = await _body(request, BasketIn)
        lines = [BasketLine(sku=ln.sku, qty=ln.qty, unit_price_ttc=ln.unit_price_ttc, unit_cost=ln.unit_cost) for ln in body.lines]
        discount = Discount(kind=body.discount.kind, value=body.discount.value, code=body.discount.code) if body.discount else None
        result = basket_contribution(
            lines, params_for(body.profile), body.shipping_charged, discount, shipping_cost_actual=body.shipping_cost_actual
        )
        return _ok({"basket": result, "labels_fr": explain(result.reasons), "allowed": result.is_allowed})

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

    @app.post("/stock/reorder-proposal")
    async def reorder_proposal(request: Request) -> PokeshopJSONResponse:
        """Panier fournisseur **à valider** ; gels du stop-loss et réserve de trésorerie appliqués."""
        require_api(request)
        body = await _body(request, ReorderIn)
        now = svc.clock()
        gate = svc.gate.authorize("PROPOSE_PURCHASE", dry_run=False, actor=body.actor, workflow="reassort")
        if not gate.allowed and gate.has("STOPLOSS_GLOBAL_FREEZE"):
            raise HTTPProblem(423, "stop-loss global : aucune proposition d'achat", gate=gate)
        status = gate.stoploss
        reserve = svc.mandate.cash_reserve_chf if svc.mandate else (svc.stoploss_config.cash.reserve_chf if svc.stoploss_config else Decimal("1600"))
        blocked_ext = set(status.no_reorder_extensions) if status else set()
        blocked_prod = set(status.blocked_products) if status else set()
        # Stop-loss trésorerie : plus aucun achat => budget utilisable nul (motif CASH_RESERVE).
        budget = Decimal("0") if status is not None and status.purchases_and_ads_frozen else body.budget_available
        proposal = propose_reorder(
            body.candidates, budget_available=budget,
            stock_budget_total=body.stock_budget_total or svc.rules.stock.stock_budget_chf, now=now,
            extension_exposure=body.extension_exposure, extension_cap_pct=svc.rules.stock.extension_budget_cap,
            cap_exceptions=body.cap_exceptions, max_age=svc.rules.stock.max_age, rules_version=svc.rules.rules_version,
            blocked_extensions=sorted(blocked_ext), blocked_products=sorted(blocked_prod), cash_reserve_chf=reserve,
        )  # fmt: skip
        svc.audit.append(
            actor=body.actor, actor_kind=ActorKind.AGENT, action="reorder.proposal", entity="purchase_proposal",
            entity_id=proposal.inputs_hash[:16], dry_run=True, autonomy_level=gate.current_level,
            payload={"lines": len(proposal.lines), "total_chf": proposal.total_cost_chf, "gate": list(gate.reasons)},
        )  # fmt: skip
        return _ok({"proposal": proposal, "gate": gate, "stoploss_known": status is not None})

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
        """Import **en simulation** ; rapport interne (peut citer des prix B2B : jamais publié)."""
        require_api(request)
        if not _SUPPLIER_RE.match(supplier):
            raise HTTPProblem(422, "identifiant fournisseur invalide")
        body = await _body(request, ImportIn)
        result = run_import(supplier, _source(body.source_path), now=svc.clock(), dry_run=True, source_ts=body.source_ts)
        svc.audit.append(
            actor="n8n", actor_kind=ActorKind.SYSTEME, action="import.run", entity="supplier", entity_id=supplier,
            dry_run=True, payload={"status": result.status, "rows": result.rows_read, "accepted": result.accepted_count,
                                   "quarantined": result.quarantined_count, "sha256": result.snapshot.checksum_sha256},
        )  # fmt: skip
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
        """Aperçu de la charge ``productSet`` **publique** (aucun coût dans la réponse)."""
        require_api(request)
        body = await _body(request, PublishPreviewIn)
        decision = None
        if body.quote is not None:
            q = body.quote
            decision = decide_price(
                q.cost_chf, params_for(q.profile), q.market_ref, q.current_public or body.reference_price_24h,
                q.unknown_fields, candidate_price=q.candidate_price, small_product=q.small_product,
                offer_stale=q.offer_stale, previous_cost=q.previous_cost,
            )  # fmt: skip
        status, _ = svc.gate.stoploss_status()
        blocked = body.stoploss_blocked or (status is not None and body.listing.product_key in status.blocked_products)
        plan = build_publication(
            body.listing, decision, max_daily_change=svc.rules.pricing.max_daily_price_change,
            reference_price_24h=body.reference_price_24h, price_validation=body.price_validation,
            stoploss_blocked=blocked, quarantined=svc.incidents.is_quarantined(body.listing.product_key),
            sensitive_terms=body.sensitive_terms, table=_table(body.listing.fictif),
        )  # fmt: skip
        return _ok({"plan": plan, "dry_run": True})

    @app.post("/sync/run")
    async def sync_run(request: Request) -> PokeshopJSONResponse:
        """Cycle fournisseur → site en 8 étapes ; simulation sauf ``dry_run: false`` (gouvernance appliquée)."""
        require_api(request)
        body = await _body(request, SyncIn)
        if not _SUPPLIER_RE.match(body.supplier):
            raise HTTPProblem(422, "identifiant fournisseur invalide")
        mapping = load_mapping(body.supplier)
        fictif = mapping.fictif or any(item.listing.fictif for item in body.catalog)
        table = extension_table_for(mapping, _table(fictif))
        ctx = SyncContext(
            rules=svc.rules,
            catalog_products=[
                CatalogProduct(product_id=i.product_id, identity=i.listing.identity, supplier_links=tuple(i.supplier_links))
                for i in body.catalog
            ],
            listings={i.product_id: i.listing for i in body.catalog},
            table=table,
            cost_inputs=body.cost_inputs,
            market_refs=body.market_refs,
            price_validations=body.price_validations,
        )
        report = svc.sync.run_supplier_cycle(
            mapping, _source(body.source_path), ctx, now=svc.clock(), dry_run=body.dry_run, source_ts=body.source_ts
        )
        return _ok({"report": report, "clean": report.clean, "report_markdown": report.render_markdown()})

    # -- incidents --------------------------------------------------------------------
    @app.get("/incidents")
    def incidents_list(request: Request, status: IncidentStatus | None = None, open_only: bool = False) -> PokeshopJSONResponse:
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
        require_api(request)
        body = await _body(request, IncidentIn)
        incident = svc.incidents.open(
            cause=body.cause, code=body.code, kind=body.kind, severity=body.severity, scope=body.scope,
            proposed_action=body.proposed_action, product_key=body.product_key, supplier_id=body.supplier_id,
            workflow=body.workflow, details=body.details, actor=body.actor, actor_kind=ActorKind.AGENT,
            simulation=body.simulation,
        )  # fmt: skip
        svc.gate.invalidate()
        return _ok({"incident": incident, "notification": svc.incidents.notification_for(incident.incident_id)}, 201)

    @app.post("/incidents/{incident_id}/test")
    async def incidents_test(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Enregistre le test de correction (préalable à toute reprise)."""
        require_api(request)
        body = await _body(request, IncidentTestIn)
        return _ok({"incident": svc.incidents.record_test(incident_id, test_ref=body.test_ref, passed=body.passed, actor=body.actor)})

    @app.post("/incidents/{incident_id}/resume")
    async def incidents_resume(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Reprise après test ; incident critique : jeton de la propriétaire exigé."""
        require_api(request)
        body = await _body(request, ActorIn)
        token = owner_token(request, required=False)
        kind = ActorKind.AGENT
        if token is not None:
            if not verify_owner_token(token, cfg.owner_token_sha256):
                raise HTTPProblem(403, "jeton propriétaire invalide")
            kind = ActorKind.PROPRIETAIRE
        incident = svc.incidents.resume(incident_id, actor=body.actor, actor_kind=kind)
        svc.gate.invalidate()
        return _ok({"incident": incident})

    @app.post("/incidents/{incident_id}/close")
    async def incidents_close(incident_id: str, request: Request) -> PokeshopJSONResponse:
        """Clôture d'un incident résolu."""
        require_api(request)
        body = await _body(request, ActorIn)
        return _ok({"incident": svc.incidents.close(incident_id, actor=body.actor)})

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
        require_api(request)
        body = await _body(request, AutonomyIn)
        if body.level > int(svc.autonomy.level):
            token = owner_token(request, required=True)
            state = svc.autonomy.raise_level(body.level, owner_token=token or "", reason=body.reason, actor=body.actor)
        else:
            state = svc.autonomy.lower(body.level, actor=body.actor, role="AGENT", reason=body.reason)
        svc.gate.invalidate()
        return _ok({"state": state, "label": LEVEL_LABELS_FR[AutonomyLevel(state.level)]})

    # -- stop-loss --------------------------------------------------------------------------
    def _require_engine() -> StopLossEngine:
        if svc.stoploss_engine is None:
            raise HTTPProblem(503, "stop-loss indisponible : " + svc.load_errors.get("stoploss", "configuration absente"))
        return svc.stoploss_engine

    @app.post("/stoploss/state")
    async def stoploss_state(request: Request) -> PokeshopJSONResponse:
        """Dépose la photo d'activité (construite par les workflows) puis l'évalue."""
        require_api(request)
        _require_engine()
        body = await _body(request, StopLossState)
        with svc.lock:
            svc.stoploss_state = body
        svc.gate.invalidate()
        status, triggers = svc.gate.stoploss_status()
        if status is None:
            raise HTTPProblem(409, f"photo refusée : {svc.gate.last_stoploss_error}")
        return _ok({"status": status, "triggers": triggers})

    @app.get("/stoploss/status")
    def stoploss_status(request: Request) -> PokeshopJSONResponse:
        """État des six stop-loss sur la dernière photo ; verrou global toujours rapporté."""
        require_api(request)
        engine = _require_engine()
        status, triggers = svc.gate.stoploss_status()
        return _ok(
            {
                "available": status is not None,
                "error": svc.gate.last_stoploss_error,
                "global_frozen": engine.frozen,
                "latch": engine.latch,
                "status": status,
                "triggers": triggers,
                "report_markdown": render_report(triggers, now=svc.clock()) if status is not None else None,
                "journal": engine.journal[-20:],
            }
        )

    @app.post("/stoploss/freeze")
    async def stoploss_freeze(request: Request) -> PokeshopJSONResponse:
        """Gel global manuel (tout agent, par précaution) ; levée par la propriétaire seule."""
        require_api(request)
        engine = _require_engine()
        body = await _body(request, FreezeIn)
        latch = engine.freeze(body.actor, body.reason, svc.clock())
        svc.autonomy.force_level_one(reason=f"gel manuel : {body.reason}", actor=body.actor)
        svc.gate.invalidate()
        svc.audit.append(
            actor=body.actor, actor_kind=ActorKind.AGENT, action="stoploss.freeze", entity="stoploss", entity_id="global",
            dry_run=False, payload={"reason": body.reason},
        )  # fmt: skip
        return _ok({"latch": latch})

    @app.post("/stoploss/rearm")
    async def stoploss_rearm(request: Request) -> PokeshopJSONResponse:
        """Réarmement du gel global : **propriétaire uniquement** (jeton distinct, motif, journal)."""
        require_api(request)
        engine = _require_engine()
        token = owner_token(request, required=True)
        body = await _body(request, RearmIn)
        now = svc.clock()
        try:
            entry = engine.rearm(token or "", body.reason, now=now, state=svc.stoploss_state, rebase=body.rebase)
        except RearmRefusedError:
            svc.audit.append(
                actor="inconnu", actor_kind=ActorKind.AGENT, action="stoploss.rearm_refused", entity="stoploss",
                entity_id="global", dry_run=False, payload={"reason": body.reason},
            )  # fmt: skip
            raise
        svc.gate.invalidate()
        svc.audit.append(
            actor="propriétaire", actor_kind=ActorKind.PROPRIETAIRE, action="stoploss.rearm", entity="stoploss",
            entity_id="global", dry_run=False, autonomy_level=int(svc.autonomy.level),
            payload={"reason": body.reason, "rebase": body.rebase, "journal_seq": entry.seq},
        )  # fmt: skip
        return _ok({"journal_entry": entry, "latch": engine.latch, "autonomy_level": int(svc.autonomy.level),
                    "note": "Le niveau d'autonomie n'est pas restauré : décision distincte (POST /autonomy)."})

    # -- mandat ------------------------------------------------------------------------------
    @app.post("/mandate/check")
    async def mandate_check(request: Request) -> PokeshopJSONResponse:
        """Contrôle d'une demande de dépense (mandat + stop-loss + trésorerie) ; enregistrement optionnel."""
        require_api(request)
        body = await _body(request, MandateCheckIn)
        if svc.mandate is None:
            raise HTTPProblem(503, "mandat illisible : " + svc.load_errors.get("mandate", "absent"))
        status, _ = svc.gate.stoploss_status()
        if status is None:
            raise HTTPProblem(503, f"état du stop-loss indisponible ({svc.gate.last_stoploss_error}) : décision impossible")
        decision = check(body.request, svc.mandate, svc.spend_ledger, status, body.treasury, now=svc.clock())
        entry = svc.spend_ledger.record(body.request, decision, actor=body.request.requested_by) if body.record else None
        svc.audit.append(
            actor=body.request.requested_by, actor_kind=ActorKind.AGENT, action="mandate.check", entity="spend_request",
            entity_id=body.request.idempotency_key, dry_run=not body.record,
            payload={"outcome": decision.outcome, "reasons": list(decision.reasons), "amount_chf": decision.amount_chf},
            idempotency_key=body.request.idempotency_key,
        )  # fmt: skip
        return _ok({"decision": decision, "labels_fr": decision.labels_fr, "recorded": entry is not None})

    # -- étoile polaire --------------------------------------------------------------------------
    @app.get("/northstar")
    def northstar(request: Request, start: date | None = None, end: date | None = None) -> PokeshopJSONResponse:
        """Contribution nette cumulée par semaine (étoile polaire)."""
        require_api(request)
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
        require_api(request)
        body = await _body(request, NorthStarEntriesIn)
        added = sum(1 for e in body.entries if svc.northstar.record(e))
        return _ok({"added": added, "received": len(body.entries)})

    return app
