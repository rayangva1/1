"""Client Shopify Admin GraphQL : simulation par défaut, idempotence, retry, journal (agent integrations).

Forme des mutations — vérification du 4 octobre 2026. Les pages ``shopify.dev`` (BP [S8], [S9])
sont **bloquées par le proxy** de l'environnement de build : la forme ci-dessous provient des
extraits de l'index de recherche de shopify.dev (pages des mutations, changelog et notes de
version), consultés le 4.10.2026, et doit être **revérifiée** sur la documentation avant la
première écriture réelle :

* version stable ``2026-10`` publiée le 1.10.2026 (support jusqu'au 16.10.2027) ;
  https://shopify.dev/changelog/release-notes/2026-10 ;
* ``inventorySetQuantities(input: InventorySetQuantitiesInput!)`` : ``name``, ``reason``,
  ``referenceDocumentUri``, ``quantities[]`` (``inventoryItemId``, ``locationId``, ``quantity``,
  ``changeFromQuantity``). ``changeFromQuantity`` (2026-01) remplace ``compareQuantity`` et
  ``ignoreCompareQuantity`` (supprimés en 2026-04) ; la directive ``@idempotent(key: …)`` est
  **obligatoire** depuis 2026-04 ; https://shopify.dev/docs/api/admin-graphql/latest/mutations/inventorySetQuantities ;
  https://shopify.dev/changelog/making-idempotency-mandatory-for-inventory-adjustments-and-refund-mutations ;
* ``productSet(input: ProductSetInput!, synchronous: Boolean, identifier: …)`` : sémantique
  « ensemble » (les variantes absentes sont supprimées), SKU sous ``inventoryItem.sku``, limite
  de 100 variantes en mode synchrone ; aucune directive d'idempotence documentée pour
  ``productSet`` (l'idempotence est assurée ici par le registre local et par la sémantique
  « ensemble ») ; https://shopify.dev/docs/api/admin-graphql/latest/mutations/productSet ;
* limitation de débit : ``errors[].extensions.code = THROTTLED`` et
  ``extensions.cost.throttleStatus`` (``currentlyAvailable``, ``restoreRate``) ;
  https://shopify.dev/docs/apps/build/apis/graphql-admin/rate-limits.

Garanties :

* ``dry_run=True`` par défaut : la charge est validée et journalisée, **rien n'est envoyé** ;
* liste blanche de mutations (``productSet``, ``inventorySetQuantities``, ``metafieldsSet``) :
  ce client ne peut **pas** modifier une commande (prix d'une commande conclue intouchable) ;
* clé d'idempotence obligatoire par écriture : même clé + même requête = réponse rejouée sans
  nouvel envoi ; même clé + autre requête = refus ;
* reprise sûre : un échec transitoire libère la clé ; une réservation restée « en cours »
  au-delà de ``stale_claim_after`` est renvoyée avec la **même** clé (Shopify déduplique) ;
* retry avec backoff sur 429, 5xx, erreurs réseau et ``THROTTLED`` (attente calculée sur le
  coût GraphQL) ; 401/403 = « API boutique refusée », sans retry ;
* ``userErrors`` analysés (conflit de concurrence ``changeFromQuantity`` signalé) ;
* charges ``productSet`` / ``metafieldsSet`` revérifiées par
  :func:`pokeshop.publish.assert_no_sensitive_fields` avant tout envoi ou simulation ;
* le jeton n'est jamais journalisé.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import Field, SecretStr, field_validator

from .audit import (
    ActorKind,
    AuditLog,
    ClaimStatus,
    IdempotencyStore,
    InMemoryAuditLog,
    InMemoryIdempotencyStore,
    payload_sha256,
    to_jsonable,
)
from .errors import PokeshopError
from .models import FrozenModel, canonical_json
from .publish import assert_metafields_public, assert_no_sensitive_fields
from .settings import DEFAULT_SHOPIFY_API_VERSION, Settings

__all__ = [
    "DEFAULT_API_VERSION",
    "ALLOWED_MUTATIONS",
    "IDEMPOTENT_DIRECTIVE_MUTATIONS",
    "INVENTORY_REASONS",
    "CAS_STALE_CODES",
    "PRODUCT_SET_MUTATION",
    "INVENTORY_SET_QUANTITIES_MUTATION",
    "METAFIELDS_SET_MUTATION",
    "INVENTORY_LEVELS_QUERY",
    "PRODUCT_BY_HANDLE_QUERY",
    "ShopifyError",
    "ShopifyConfigError",
    "ShopifyForbiddenOperationError",
    "ShopifyAccessDeniedError",
    "ShopifyThrottledError",
    "ShopifyTransportError",
    "ShopifyHTTPError",
    "ShopifyGraphQLError",
    "ShopifyIdempotencyError",
    "ShopifyInFlightError",
    "UserError",
    "QueryCost",
    "ShopifyResponse",
    "InventoryChange",
    "RemoteInventoryLevel",
    "RemoteVariant",
    "RemoteProduct",
    "derive_idempotency_key",
    "ShopifyClient",
]

DEFAULT_API_VERSION = DEFAULT_SHOPIFY_API_VERSION
_API_VERSION_RE = re.compile(r"^(\d{4}-(01|04|07|10)|unstable)$")
_SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$")
_GID_RE = {
    "InventoryItem": re.compile(r"^gid://shopify/InventoryItem/\d+$"),
    "Location": re.compile(r"^gid://shopify/Location/\d+$"),
    "Product": re.compile(r"^gid://shopify/Product/\d+$"),
}

ALLOWED_MUTATIONS: frozenset[str] = frozenset({"productSet", "inventorySetQuantities", "metafieldsSet"})
"""Seules mutations émises : aucune mutation de commande, remboursement ou paiement."""
IDEMPOTENT_DIRECTIVE_MUTATIONS: frozenset[str] = frozenset({"inventorySetQuantities"})
"""Mutations pour lesquelles ``@idempotent(key:)`` est exigé par Shopify depuis 2026-04."""
INVENTORY_REASONS: frozenset[str] = frozenset(
    {
        "correction",
        "cycle_count_available",
        "damaged",
        "movement_created",
        "movement_updated",
        "movement_received",
        "movement_canceled",
        "other",
        "promotion",
        "quality_control",
        "received",
        "reservation_created",
        "reservation_deleted",
        "reservation_updated",
        "restock",
        "safety_stock",
        "shrinkage",
    }
)
"""Motifs d'ajustement d'inventaire acceptés par Shopify (liste à revérifier sur shopify.dev)."""
CAS_STALE_CODES: frozenset[str] = frozenset({"CHANGE_FROM_QUANTITY_STALE", "COMPARE_QUANTITY_STALE"})
"""Codes ``userErrors`` d'un conflit compare-and-swap (le premier est le code attendu après 2026-04 ; à revérifier)."""

PRODUCT_SET_MUTATION = """
mutation PokeshopProductSet($input: ProductSetInput!, $identifier: ProductSetIdentifiers, $synchronous: Boolean!) {
  productSet(input: $input, identifier: $identifier, synchronous: $synchronous) {
    product { id handle status title variants(first: 5) { nodes { id sku price barcode inventoryItem { id } } } }
    productSetOperation { id status }
    userErrors { field message code }
  }
}
""".strip()

INVENTORY_SET_QUANTITIES_MUTATION = """
mutation PokeshopInventorySet($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
    inventoryAdjustmentGroup { reason referenceDocumentUri changes { name delta } }
    userErrors { code field message }
  }
}
""".strip()

METAFIELDS_SET_MUTATION = """
mutation PokeshopMetafieldsSet($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { key namespace value }
    userErrors { field message code }
  }
}
""".strip()

INVENTORY_LEVELS_QUERY = """
query PokeshopInventoryLevels($ids: [ID!]!, $locationId: ID!) {
  nodes(ids: $ids) {
    ... on InventoryItem {
      id
      sku
      inventoryLevel(locationId: $locationId) {
        quantities(names: ["available", "committed", "on_hand"]) { name quantity }
      }
    }
  }
}
""".strip()

PRODUCT_BY_HANDLE_QUERY = """
query PokeshopProductByHandle($identifier: ProductIdentifierInput!) {
  productByIdentifier(identifier: $identifier) {
    id handle status title
    variants(first: 5) { nodes { id sku price barcode inventoryItem { id } } }
  }
}
""".strip()

_ROOT_FIELD_RE = re.compile(r"^\s*(mutation|query)\b[^{]*\{\s*([A-Za-z_][A-Za-z0-9_]*)", re.DOTALL)
_KEY_NAMESPACE = uuid.UUID("8f5e3a4c-6b1d-5c2e-9a7f-0d4b2c6e8a10")


# ---------------------------------------------------------------------- erreurs


class ShopifyError(PokeshopError):
    """Racine des erreurs du client Shopify."""


class ShopifyConfigError(ShopifyError, ValueError):
    """Configuration absente ou invalide (domaine, jeton, version)."""


class ShopifyForbiddenOperationError(ShopifyError, ValueError):
    """Document GraphQL hors liste blanche (ex. mutation de commande)."""


class ShopifyAccessDeniedError(ShopifyError):
    """« API boutique refusée » (401/403, ``ACCESS_DENIED``) : aucun retry, incident à ouvrir."""


class ShopifyThrottledError(ShopifyError):
    """Limitation de débit persistante après tous les essais."""


class ShopifyTransportError(ShopifyError):
    """Panne réseau ou 5xx persistante après tous les essais."""


class ShopifyHTTPError(ShopifyError):
    """Statut HTTP non récupérable (402, 404, 423…) ou réponse illisible."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} : {message}")


class ShopifyGraphQLError(ShopifyError):
    """Erreurs GraphQL de premier niveau (requête invalide)."""

    def __init__(self, messages: Sequence[str], codes: Sequence[str] = ()) -> None:
        self.messages = tuple(messages)
        self.codes = tuple(codes)
        super().__init__("GraphQL : " + " ; ".join(self.messages))


class ShopifyIdempotencyError(ShopifyError):
    """Clé d'idempotence réutilisée pour une autre requête."""


class ShopifyInFlightError(ShopifyError):
    """Même écriture déjà en cours (réservation récente) : ne pas renvoyer."""


# ---------------------------------------------------------------------- modèles


class UserError(FrozenModel):
    """``userErrors`` d'une mutation."""

    field: tuple[str, ...] | None = None
    message: str
    code: str | None = None


class QueryCost(FrozenModel):
    """Coût GraphQL et état du seau de débit (``extensions.cost``)."""

    requested: Decimal | None = None
    actual: Decimal | None = None
    maximum_available: Decimal | None = None
    currently_available: Decimal | None = None
    restore_rate: Decimal | None = None


class ShopifyResponse(FrozenModel):
    """Résultat d'un appel (réel, simulé ou rejoué)."""

    operation: str
    dry_run: bool
    replayed: bool = False
    data: dict[str, Any] | None = None
    user_errors: tuple[UserError, ...] = ()
    cost: QueryCost | None = None
    request_id: str | None = None
    attempts: int = 0
    idempotency_key: str | None = None
    request_sha256: str = ""

    @property
    def ok(self) -> bool:
        """Vrai si aucune ``userError``."""
        return not self.user_errors

    @property
    def concurrency_conflict(self) -> bool:
        """Vrai si Shopify a refusé un compare-and-swap (quantité de départ périmée)."""
        return any(e.code in CAS_STALE_CODES for e in self.user_errors)

    def root(self) -> dict[str, Any]:
        """Objet racine de la mutation ou de la requête (vide en simulation)."""
        if not self.data:
            return {}
        value = self.data.get(self.operation)
        return value if isinstance(value, dict) else {}


class InventoryChange(FrozenModel):
    """Quantité à fixer avec compare-and-swap obligatoire (jamais de contournement du contrôle)."""

    inventory_item_id: str
    location_id: str
    quantity: int = Field(ge=0)
    change_from_quantity: int
    """Quantité attendue côté Shopify avant l'écriture (lue juste avant)."""

    @field_validator("inventory_item_id")
    @classmethod
    def _item(cls, v: str) -> str:
        if not _GID_RE["InventoryItem"].match(v):
            raise ValueError("gid://shopify/InventoryItem/<n> attendu")
        return v

    @field_validator("location_id")
    @classmethod
    def _loc(cls, v: str) -> str:
        if not _GID_RE["Location"].match(v):
            raise ValueError("gid://shopify/Location/<n> attendu")
        return v


class RemoteInventoryLevel(FrozenModel):
    """Quantités Shopify d'un article à un emplacement (autorité des réservations de vente)."""

    inventory_item_id: str
    available: int
    committed: int = Field(default=0, ge=0)
    on_hand: int | None = None
    sku: str | None = None
    assumed: bool = False
    """Vrai si la valeur est supposée (simulation sans lecture Shopify)."""


class RemoteVariant(FrozenModel):
    """Variante lue sur la boutique (vérification après publication)."""

    id: str
    sku: str | None = None
    price: Decimal | None = None
    barcode: str | None = None
    inventory_item_id: str | None = None


class RemoteProduct(FrozenModel):
    """Produit lu sur la boutique."""

    id: str
    handle: str
    status: str
    title: str
    variants: tuple[RemoteVariant, ...] = ()


def derive_idempotency_key(*parts: Any) -> str:
    """Clé déterministe (UUID v5) dérivée du contenu : même écriture => même clé."""
    return str(uuid.uuid5(_KEY_NAMESPACE, canonical_json(list(parts))))


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _cost(body: Mapping[str, Any]) -> QueryCost | None:
    ext = body.get("extensions")
    if not isinstance(ext, Mapping) or not isinstance(ext.get("cost"), Mapping):
        return None
    cost = ext["cost"]
    throttle = cost.get("throttleStatus") if isinstance(cost.get("throttleStatus"), Mapping) else {}
    return QueryCost(
        requested=_dec(cost.get("requestedQueryCost")),
        actual=_dec(cost.get("actualQueryCost")),
        maximum_available=_dec(throttle.get("maximumAvailable")),
        currently_available=_dec(throttle.get("currentlyAvailable")),
        restore_rate=_dec(throttle.get("restoreRate")),
    )


def _user_errors(root: Any) -> tuple[UserError, ...]:
    if not isinstance(root, Mapping):
        return ()
    out = []
    for raw in root.get("userErrors") or ():
        if not isinstance(raw, Mapping):
            continue
        field = raw.get("field")
        out.append(
            UserError(
                field=tuple(str(f) for f in field) if isinstance(field, list) else None,
                message=str(raw.get("message") or ""),
                code=str(raw["code"]) if raw.get("code") is not None else None,
            )
        )
    return tuple(out)


def root_field(document: str) -> tuple[str, str]:
    """(type d'opération, premier champ racine) d'un document GraphQL simple."""
    match = _ROOT_FIELD_RE.match(document)
    if match is None:
        raise ShopifyForbiddenOperationError("document GraphQL illisible : opération nommée attendue")
    return match.group(1), match.group(2)


# ----------------------------------------------------------------------- client


class ShopifyClient:
    """Client Admin GraphQL (httpx), transport injectable, simulation par défaut."""

    def __init__(
        self,
        *,
        shop_domain: str | None = None,
        access_token: SecretStr | str | None = None,
        api_version: str = DEFAULT_API_VERSION,
        dry_run: bool = True,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 5,
        backoff_base_ms: int = 500,
        backoff_max_ms: int = 30_000,
        audit: AuditLog | None = None,
        idempotency: IdempotencyStore | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
        stale_claim_after: timedelta = timedelta(minutes=10),
        actor: str = "agent-07-integrations",
        sensitive_terms: Sequence[str] = (),
    ) -> None:
        if not _API_VERSION_RE.match(api_version):
            raise ShopifyConfigError(f"version d'API invalide : {api_version!r}")
        if shop_domain is not None and not _SHOP_RE.match(shop_domain):
            raise ShopifyConfigError("domaine attendu de la forme <boutique>.myshopify.com")
        if max_retries < 0 or backoff_base_ms < 1 or backoff_max_ms < backoff_base_ms:
            raise ShopifyConfigError("paramètres de retry invalides")
        self.shop_domain = shop_domain
        self._token = (
            access_token if isinstance(access_token, SecretStr) or access_token is None else SecretStr(access_token)
        )
        self.api_version = api_version
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.backoff_base_ms = backoff_base_ms
        self.backoff_max_ms = backoff_max_ms
        self.audit: AuditLog = audit if audit is not None else InMemoryAuditLog()
        self.idempotency: IdempotencyStore = idempotency if idempotency is not None else InMemoryIdempotencyStore()
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self.stale_claim_after = stale_claim_after
        self.actor = actor
        self.sensitive_terms = tuple(sensitive_terms)
        self._http = httpx.Client(transport=transport, timeout=timeout_seconds)
        self.last_cost: QueryCost | None = None
        self.requests_sent = 0

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> ShopifyClient:
        """Client configuré depuis :class:`pokeshop.settings.Settings` (dry-run hérité)."""
        params: dict[str, Any] = {
            "shop_domain": settings.shopify_shop_domain,
            "access_token": settings.shopify_admin_token,
            "api_version": settings.shopify_api_version,
            "dry_run": settings.dry_run,
            "timeout_seconds": settings.shopify_timeout_seconds,
            "max_retries": settings.shopify_max_retries,
            "backoff_base_ms": settings.shopify_backoff_base_ms,
            "backoff_max_ms": settings.shopify_backoff_max_ms,
            "stale_claim_after": timedelta(minutes=settings.stale_claim_minutes),
        }
        params.update(kwargs)
        return cls(**params)

    # -- configuration --------------------------------------------------------------
    @property
    def configured(self) -> bool:
        """Vrai si domaine et jeton sont fournis."""
        return self.shop_domain is not None and self._token is not None

    @property
    def endpoint(self) -> str:
        """URL Admin GraphQL de la boutique."""
        if self.shop_domain is None:
            raise ShopifyConfigError("POKESHOP_SHOPIFY_SHOP_DOMAIN absent")
        return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            raise ShopifyConfigError("jeton Shopify absent (coffre : POKESHOP_SHOPIFY_ADMIN_TOKEN)")
        return {
            "X-Shopify-Access-Token": self._token.get_secret_value(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "pokeshop-integrations/0.1",
        }

    def close(self) -> None:
        """Ferme le client HTTP."""
        self._http.close()

    # -- transport --------------------------------------------------------------------
    def _backoff_ms(self, attempt: int) -> int:
        return min(self.backoff_max_ms, self.backoff_base_ms * (1 << attempt))

    def _throttle_wait_ms(self, body: Mapping[str, Any], attempt: int) -> int:
        cost = _cost(body)
        if cost and cost.requested is not None and cost.currently_available is not None and cost.restore_rate:
            missing = cost.requested - cost.currently_available
            if missing > 0 and cost.restore_rate > 0:
                wait = math.ceil(missing * 1000 / cost.restore_rate)
                return max(self.backoff_base_ms, min(self.backoff_max_ms, wait))
        return self._backoff_ms(attempt)

    def _wait(self, ms: int) -> None:
        self._sleep(ms / 1000)

    def _post(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], str | None, int]:
        """POST avec retry ; renvoie (corps JSON, X-Request-Id, nombre d'essais)."""
        url = self.endpoint
        headers = self._headers()
        last_error = ""
        for attempt in range(self.max_retries + 1):
            final = attempt == self.max_retries
            try:
                self.requests_sent += 1
                resp = self._http.post(url, json=payload, headers=headers)
            except httpx.TransportError as exc:
                last_error = type(exc).__name__
                if final:
                    raise ShopifyTransportError(f"réseau : {last_error} après {attempt + 1} essai(s)") from exc
                self._wait(self._backoff_ms(attempt))
                continue
            request_id = resp.headers.get("X-Request-Id")
            if resp.status_code in (401, 403):
                raise ShopifyAccessDeniedError(f"API boutique refusée (HTTP {resp.status_code})")
            if resp.status_code == 429:
                if final:
                    raise ShopifyThrottledError(f"HTTP 429 après {attempt + 1} essai(s)")
                retry_after = resp.headers.get("Retry-After")
                wait = self._backoff_ms(attempt)
                if retry_after:
                    seconds = _dec(retry_after)
                    if seconds is not None and seconds >= 0:
                        wait = max(1, math.ceil(seconds * 1000))
                self._wait(min(wait, self.backoff_max_ms))
                continue
            if 500 <= resp.status_code < 600:
                last_error = f"HTTP {resp.status_code}"
                if final:
                    raise ShopifyTransportError(f"{last_error} après {attempt + 1} essai(s)")
                self._wait(self._backoff_ms(attempt))
                continue
            if resp.status_code != 200:
                raise ShopifyHTTPError(resp.status_code, resp.text[:200])
            try:
                body = resp.json()
            except ValueError as exc:
                raise ShopifyHTTPError(resp.status_code, "réponse JSON illisible") from exc
            if not isinstance(body, dict):
                raise ShopifyHTTPError(resp.status_code, "réponse JSON inattendue")
            self.last_cost = _cost(body) or self.last_cost
            errors = body.get("errors")
            if errors:
                items = errors if isinstance(errors, list) else [errors]
                codes = [
                    str(e.get("extensions", {}).get("code"))
                    for e in items
                    if isinstance(e, Mapping) and isinstance(e.get("extensions"), Mapping)
                ]
                if "THROTTLED" in codes:
                    if final:
                        raise ShopifyThrottledError(f"THROTTLED après {attempt + 1} essai(s)")
                    self._wait(self._throttle_wait_ms(body, attempt))
                    continue
                messages = [str(e.get("message", e)) if isinstance(e, Mapping) else str(e) for e in items]
                if "ACCESS_DENIED" in codes:
                    raise ShopifyAccessDeniedError("API boutique refusée (ACCESS_DENIED) : " + " ; ".join(messages))
                raise ShopifyGraphQLError(messages, codes)
            return body, request_id, attempt + 1
        raise ShopifyTransportError(last_error or "essais épuisés")  # pragma: no cover - boucle toujours conclue

    # -- lecture ------------------------------------------------------------------------
    def query(self, document: str, variables: Mapping[str, Any] | None = None) -> ShopifyResponse:
        """Requête de lecture (envoyée même en simulation : elle ne modifie rien ; configuration requise)."""
        kind, field = root_field(document)
        if kind != "query":
            raise ShopifyForbiddenOperationError("query() n'accepte que des lectures")
        if not self.configured:
            raise ShopifyConfigError("lecture Shopify impossible : domaine ou jeton absent")
        body, request_id, attempts = self._post({"query": document, "variables": to_jsonable(dict(variables or {}))})
        return ShopifyResponse(
            operation=field,
            dry_run=False,
            data=body.get("data"),
            cost=_cost(body),
            request_id=request_id,
            attempts=attempts,
        )

    def inventory_levels(self, inventory_item_ids: Sequence[str], location_id: str) -> dict[str, RemoteInventoryLevel]:
        """Quantités ``available`` / ``committed`` / ``on_hand`` par article à l'emplacement."""
        for item in inventory_item_ids:
            if not _GID_RE["InventoryItem"].match(item):
                raise ShopifyConfigError(f"identifiant d'article invalide : {item}")
        if not _GID_RE["Location"].match(location_id):
            raise ShopifyConfigError(f"identifiant d'emplacement invalide : {location_id}")
        if not inventory_item_ids:
            return {}
        resp = self.query(INVENTORY_LEVELS_QUERY, {"ids": list(inventory_item_ids), "locationId": location_id})
        out: dict[str, RemoteInventoryLevel] = {}
        for node in (resp.data or {}).get("nodes") or ():
            if not isinstance(node, Mapping) or "id" not in node:
                continue
            level = node.get("inventoryLevel") or {}
            q = {str(x.get("name")): int(x.get("quantity") or 0) for x in level.get("quantities") or ()}
            out[str(node["id"])] = RemoteInventoryLevel(
                inventory_item_id=str(node["id"]),
                available=q.get("available", 0),
                committed=max(0, q.get("committed", 0)),
                on_hand=q.get("on_hand"),
                sku=node.get("sku"),
            )
        return out

    def product_by_handle(self, handle: str) -> RemoteProduct | None:
        """Produit par handle (vérification de l'état réel après publication, BP §12 étape 8)."""
        resp = self.query(PRODUCT_BY_HANDLE_QUERY, {"identifier": {"handle": handle}})
        node = (resp.data or {}).get("productByIdentifier")
        if not isinstance(node, Mapping):
            return None
        variants = []
        for v in ((node.get("variants") or {}).get("nodes")) or ():
            item = v.get("inventoryItem") or {}
            variants.append(
                RemoteVariant(
                    id=str(v.get("id")),
                    sku=v.get("sku"),
                    price=_dec(v.get("price")),
                    barcode=v.get("barcode"),
                    inventory_item_id=item.get("id"),
                )
            )
        return RemoteProduct(
            id=str(node.get("id")),
            handle=str(node.get("handle")),
            status=str(node.get("status")),
            title=str(node.get("title")),
            variants=tuple(variants),
        )

    # -- écriture ------------------------------------------------------------------------
    def mutate(
        self,
        document: str,
        variables: Mapping[str, Any],
        *,
        idempotency_key: str,
        dry_run: bool | None = None,
        entity: str = "shopify",
        entity_id: str | None = None,
        autonomy_level: int | None = None,
    ) -> ShopifyResponse:
        """Mutation de la liste blanche ; dry-run par défaut ; idempotente par clé."""
        kind, field = root_field(document)
        if kind != "mutation" or field not in ALLOWED_MUTATIONS:
            raise ShopifyForbiddenOperationError(f"mutation non autorisée : {field}")
        if field in IDEMPOTENT_DIRECTIVE_MUTATIONS and "@idempotent" not in document:
            raise ShopifyForbiddenOperationError(f"{field} exige la directive @idempotent (Shopify 2026-04)")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 200:
            raise ShopifyIdempotencyError("clé d'idempotence obligatoire (8 à 200 caractères)")
        simulate = self.dry_run if dry_run is None else dry_run
        clean_vars = to_jsonable(dict(variables))
        content = {k: v for k, v in clean_vars.items() if k != "idempotencyKey"}
        request_sha = payload_sha256({"mutation": field, "variables": content})
        scope = f"shopify:{field}"
        if simulate:
            self.audit.append(
                actor=self.actor,
                actor_kind=ActorKind.AGENT,
                action="shopify.dry_run",
                entity=entity,
                entity_id=entity_id,
                dry_run=True,
                autonomy_level=autonomy_level,
                payload={"mutation": field, "variables": clean_vars, "request_sha256": request_sha},
                idempotency_key=idempotency_key,
            )
            return ShopifyResponse(
                operation=field, dry_run=True, idempotency_key=idempotency_key, request_sha256=request_sha
            )
        if not self.configured:
            raise ShopifyConfigError("écriture réelle impossible : domaine ou jeton Shopify absent")
        now = self._clock()
        status, record = self.idempotency.claim(scope, idempotency_key, request_sha, now=now)
        if status is ClaimStatus.CONFLICT:
            self._audit_write(
                "shopify.idempotency_conflict", field, entity, entity_id, idempotency_key, request_sha, {}
            )
            raise ShopifyIdempotencyError(f"clé {idempotency_key} déjà utilisée pour une autre requête {field}")
        if status in (ClaimStatus.DUPLICATE_TERMINE, ClaimStatus.DUPLICATE_ECHEC):
            stored = record.response or {}
            self._audit_write(
                "shopify.replay", field, entity, entity_id, idempotency_key, request_sha, {"status": record.status}
            )
            return ShopifyResponse(
                operation=field,
                dry_run=False,
                replayed=True,
                data=stored.get("data"),
                user_errors=_user_errors((stored.get("data") or {}).get(field)),
                idempotency_key=idempotency_key,
                request_sha256=request_sha,
                request_id=stored.get("request_id"),
            )
        if status is ClaimStatus.DUPLICATE_EN_COURS:
            if now - record.created_at < self.stale_claim_after:
                raise ShopifyInFlightError(f"écriture {field} {idempotency_key} déjà en cours")
            self._audit_write(
                "shopify.resume_stale_claim",
                field,
                entity,
                entity_id,
                idempotency_key,
                request_sha,
                {"claimed_at": record.created_at},
            )
        payload = {"query": document, "variables": clean_vars}
        try:
            body, request_id, attempts = self._post(payload)
        except (
            ShopifyThrottledError,
            ShopifyTransportError,
            ShopifyAccessDeniedError,
            ShopifyHTTPError,
            ShopifyGraphQLError,
        ) as exc:
            self.idempotency.release(scope, idempotency_key)
            self._audit_write(
                "shopify.write_failed",
                field,
                entity,
                entity_id,
                idempotency_key,
                request_sha,
                {"error": type(exc).__name__, "message": str(exc)},
            )
            raise
        data = body.get("data") if isinstance(body.get("data"), dict) else None
        errors = _user_errors((data or {}).get(field))
        stored_response = {"data": data, "request_id": request_id}
        if errors:
            self.idempotency.fail(scope, idempotency_key, stored_response, now=self._clock())
        else:
            self.idempotency.complete(scope, idempotency_key, stored_response, now=self._clock())
        self._audit_write(
            "shopify.write" if not errors else "shopify.user_errors",
            field,
            entity,
            entity_id,
            idempotency_key,
            request_sha,
            {
                "attempts": attempts,
                "request_id": request_id,
                "user_errors": [e.model_dump(mode="json") for e in errors],
                "variables": clean_vars,
            },
            autonomy_level=autonomy_level,
        )
        return ShopifyResponse(
            operation=field,
            dry_run=False,
            data=data,
            user_errors=errors,
            cost=_cost(body),
            request_id=request_id,
            attempts=attempts,
            idempotency_key=idempotency_key,
            request_sha256=request_sha,
        )

    def _audit_write(
        self,
        action: str,
        field: str,
        entity: str,
        entity_id: str | None,
        key: str,
        request_sha: str,
        payload: Mapping[str, Any],
        *,
        autonomy_level: int | None = None,
    ) -> None:
        self.audit.append(
            actor=self.actor,
            actor_kind=ActorKind.AGENT,
            action=action,
            entity=entity,
            entity_id=entity_id,
            dry_run=False,
            autonomy_level=autonomy_level,
            payload={"mutation": field, "request_sha256": request_sha, **payload},
            idempotency_key=key,
        )

    def product_set(
        self,
        product_input: Mapping[str, Any],
        *,
        idempotency_key: str,
        identifier: Mapping[str, str] | None = None,
        synchronous: bool = True,
        dry_run: bool | None = None,
        autonomy_level: int | None = None,
    ) -> ShopifyResponse:
        """``productSet`` d'une fiche **publique** (liste blanche revérifiée avant tout envoi)."""
        assert_no_sensitive_fields(product_input, sensitive_terms=self.sensitive_terms)
        ident: dict[str, str] | None = None
        if identifier is not None:
            if set(identifier) - {"id", "handle"} or len(identifier) != 1:
                raise ShopifyConfigError("identifiant productSet : {'id': gid} ou {'handle': …}")
            if "id" in identifier and not _GID_RE["Product"].match(identifier["id"]):
                raise ShopifyConfigError("gid://shopify/Product/<n> attendu")
            ident = dict(identifier)
        handle = str(product_input.get("handle") or (ident or {}).get("handle") or "")
        return self.mutate(
            PRODUCT_SET_MUTATION,
            {"input": dict(product_input), "identifier": ident, "synchronous": synchronous},
            idempotency_key=idempotency_key,
            dry_run=dry_run,
            entity="product",
            entity_id=handle or None,
            autonomy_level=autonomy_level,
        )

    def inventory_set_quantities(
        self,
        changes: Sequence[InventoryChange],
        *,
        reason: str,
        reference_document_uri: str,
        idempotency_key: str,
        name: str = "available",
        dry_run: bool | None = None,
        autonomy_level: int | None = None,
    ) -> ShopifyResponse:
        """``inventorySetQuantities`` avec ``changeFromQuantity`` (compare-and-swap) et ``@idempotent``."""
        if not changes:
            raise ShopifyConfigError("aucune quantité à fixer")
        if reason not in INVENTORY_REASONS:
            raise ShopifyConfigError(f"motif d'inventaire inconnu : {reason!r}")
        if name not in ("available", "on_hand"):
            raise ShopifyConfigError("nom de quantité : 'available' ou 'on_hand'")
        if not re.match(r"^[a-z][a-z0-9+.-]*://\S+$", reference_document_uri):
            raise ShopifyConfigError("referenceDocumentUri : URI attendue (ex. pokeshop://stock-sync/…)")
        pairs = [(c.inventory_item_id, c.location_id) for c in changes]
        if len(set(pairs)) != len(pairs):
            raise ShopifyConfigError("article/emplacement en double dans la même écriture")
        variables = {
            "input": {
                "name": name,
                "reason": reason,
                "referenceDocumentUri": reference_document_uri,
                "quantities": [
                    {
                        "inventoryItemId": c.inventory_item_id,
                        "locationId": c.location_id,
                        "quantity": c.quantity,
                        "changeFromQuantity": c.change_from_quantity,
                    }
                    for c in changes
                ],
            },
            "idempotencyKey": idempotency_key,
        }
        return self.mutate(
            INVENTORY_SET_QUANTITIES_MUTATION,
            variables,
            idempotency_key=idempotency_key,
            dry_run=dry_run,
            entity="inventory",
            entity_id=changes[0].inventory_item_id if len(changes) == 1 else None,
            autonomy_level=autonomy_level,
        )

    def metafields_set(
        self,
        metafields: Sequence[Mapping[str, Any]],
        *,
        idempotency_key: str,
        dry_run: bool | None = None,
        autonomy_level: int | None = None,
    ) -> ShopifyResponse:
        """``metafieldsSet`` limité aux métachamps publics (mise à jour hors ``productSet``)."""
        assert_metafields_public(metafields, sensitive_terms=self.sensitive_terms, require_owner=True)
        return self.mutate(
            METAFIELDS_SET_MUTATION,
            {"metafields": [dict(m) for m in metafields]},
            idempotency_key=idempotency_key,
            dry_run=dry_run,
            entity="metafields",
            autonomy_level=autonomy_level,
        )
