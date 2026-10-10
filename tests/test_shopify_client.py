"""Tests du client Shopify Admin GraphQL : transport simulé (httpx.MockTransport), aucun appel réseau.

Cas BP §13 : succès, userErrors, limitation de débit, API boutique refusée, reprise sans double
écriture (idempotence), conflit de concurrence d'inventaire. Boutique, jetons et identifiants FICTIFS.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from typing import Any

import httpx
import pytest
from pokeshop.audit import ClaimStatus, InMemoryAuditLog, InMemoryIdempotencyStore, payload_sha256
from pokeshop.publish import SensitiveFieldError
from pokeshop.settings import load_settings
from pokeshop.shopify_client import (
    ALLOWED_MUTATIONS,
    DEFAULT_API_VERSION,
    INVENTORY_SET_QUANTITIES_MUTATION,
    METAFIELDS_SET_MUTATION,
    PRODUCT_SET_MUTATION,
    InventoryChange,
    ShopifyAccessDeniedError,
    ShopifyClient,
    ShopifyConfigError,
    ShopifyForbiddenOperationError,
    ShopifyGraphQLError,
    ShopifyHTTPError,
    ShopifyIdempotencyError,
    ShopifyInFlightError,
    ShopifyThrottledError,
    ShopifyTransportError,
    allowed_mutation,
    derive_idempotency_key,
    root_field,
)

SHOP = "fictif-boutique.myshopify.com"
TOKEN = "shpat_FICTIF_0000000000000000"
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
ITEM = "gid://shopify/InventoryItem/1001"
ITEM2 = "gid://shopify/InventoryItem/1002"
LOC = "gid://shopify/Location/42"
KEY = "6f1c2a4e-0000-5000-8000-00000000f1c7"

PRODUCT_INPUT: dict[str, Any] = {
    "title": "Display Extension Fictive Alpha – FR",
    "handle": "display-extension-fictive-alpha-fr-dsp-fictif-alpha-fr",
    "status": "DRAFT",
    "productType": "Display",
    "tags": ["statut:stock-local"],
    "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
    "variants": [
        {
            "optionValues": [{"optionName": "Title", "name": "Default Title"}],
            "price": "144.90",
            "barcode": "2000000001012",
            "inventoryPolicy": "DENY",
            "inventoryItem": {"sku": "DSP-FICTIF_ALPHA-FR", "tracked": True},
        }
    ],
}


def ok_json(data: dict[str, Any], **extra: Any) -> httpx.Response:
    body = {"data": data, "extensions": {"cost": {"requestedQueryCost": 10, "actualQueryCost": 10,
            "throttleStatus": {"maximumAvailable": 1000.0, "currentlyAvailable": 990, "restoreRate": 50.0}}}}
    body.update(extra)
    return httpx.Response(200, json=body, headers={"X-Request-Id": "FICTIF-REQ"})


def throttled(requested: int = 100, available: int = 50, restore: str = "50.0") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
            "extensions": {"cost": {"requestedQueryCost": requested, "actualQueryCost": None,
                                    "throttleStatus": {"maximumAvailable": 1000.0, "currentlyAvailable": available,
                                                       "restoreRate": float(restore)}}},
        },
    )


class FakeShopify:
    """Boutique simulée : applique les écritures, déduplique par clé @idempotent comme Shopify."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self.script: list[httpx.Response | Callable[[dict[str, Any]], httpx.Response]] = []
        self.applied: list[dict[str, Any]] = []
        self.idempotent: dict[str, httpx.Response] = {}
        self.levels: dict[str, dict[str, int]] = {ITEM: {"available": 5, "committed": 1, "on_hand": 6}}
        self.products: dict[str, dict[str, Any]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        if self.script:
            step = self.script.pop(0)
            return step(body) if callable(step) else step
        return self.default(body)

    def default(self, body: dict[str, Any]) -> httpx.Response:
        query, variables = body["query"], body.get("variables") or {}
        if "inventorySetQuantities" in query:
            key = variables["idempotencyKey"]
            if key in self.idempotent:
                return self.idempotent[key]
            errors = []
            for q in variables["input"]["quantities"]:
                current = self.levels.setdefault(q["inventoryItemId"], {"available": 0, "committed": 0, "on_hand": 0})
                if q["changeFromQuantity"] != current["available"]:
                    errors.append({"code": "CHANGE_FROM_QUANTITY_STALE", "field": ["input", "quantities", "0"],
                                   "message": "La quantité a changé"})
            if not errors:
                for q in variables["input"]["quantities"]:
                    self.levels[q["inventoryItemId"]]["available"] = q["quantity"]
                self.applied.append(variables)
            resp = ok_json({"inventorySetQuantities": {
                "inventoryAdjustmentGroup": None if errors else {"reason": variables["input"]["reason"],
                                                                 "referenceDocumentUri": variables["input"]["referenceDocumentUri"],
                                                                 "changes": [{"name": "available", "delta": 1}]},
                "userErrors": errors}})
            self.idempotent[key] = resp
            return resp
        if "productSet" in query:
            data = variables["input"]
            self.products[data["handle"]] = data
            self.applied.append(variables)
            return ok_json({"productSet": {"product": {"id": "gid://shopify/Product/7", "handle": data["handle"],
                                                       "status": data["status"], "title": data["title"],
                                                       "variants": {"nodes": []}},
                                           "productSetOperation": None, "userErrors": []}})
        if "metafieldsSet" in query:
            self.applied.append(variables)
            return ok_json({"metafieldsSet": {"metafields": [], "userErrors": []}})
        if "productByIdentifier" in query:
            handle = variables["identifier"]["handle"]
            data = self.products.get(handle)
            if data is None:
                return ok_json({"productByIdentifier": None})
            variant = data["variants"][0]
            return ok_json({"productByIdentifier": {
                "id": "gid://shopify/Product/7", "handle": handle, "status": data["status"], "title": data["title"],
                "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9", "sku": variant["inventoryItem"]["sku"],
                                        "price": variant["price"], "barcode": variant["barcode"],
                                        "inventoryItem": {"id": ITEM}}]}}})
        if "nodes(ids" in query:
            nodes = []
            for item_id in variables["ids"]:
                lv = self.levels.get(item_id)
                nodes.append(None if lv is None else {"id": item_id, "sku": "SKU", "inventoryLevel": {
                    "quantities": [{"name": n, "quantity": v} for n, v in lv.items()]}})
            return ok_json({"nodes": nodes})
        return httpx.Response(400, text="requête inconnue")


@pytest.fixture
def fake() -> FakeShopify:
    return FakeShopify()


@pytest.fixture
def sleeps() -> list[float]:
    return []


def make_client(fake: FakeShopify, sleeps: list[float], **kw: Any) -> ShopifyClient:
    """Client configuré en écriture réelle (``POKESHOP_DRY_RUN=false``) ; ``dry_run=True`` pour un client en simulation."""
    params: dict[str, Any] = dict(
        shop_domain=SHOP, access_token=TOKEN, transport=httpx.MockTransport(fake), sleep=sleeps.append,
        clock=lambda: NOW, max_retries=3, backoff_base_ms=100, backoff_max_ms=5_000, dry_run=False,
    )
    params.update(kw)
    return ShopifyClient(**params)


def inv(quantity: int = 7, change_from: int = 5, item: str = ITEM) -> InventoryChange:
    return InventoryChange(inventory_item_id=item, location_id=LOC, quantity=quantity, change_from_quantity=change_from)


def set_inv(client: ShopifyClient, *, key: str = KEY, dry_run: bool | None = False, **kw: Any):
    return client.inventory_set_quantities(
        [kw.pop("change", inv())], reason="correction", reference_document_uri="pokeshop://stock-sync/FICTIF/v1",
        idempotency_key=key, dry_run=dry_run, **kw,
    )


# ----------------------------------------------------------------------- simulation


def test_dry_run_is_default_and_sends_nothing(fake: FakeShopify, sleeps: list[float]) -> None:
    client = ShopifyClient(shop_domain=SHOP, access_token=TOKEN, transport=httpx.MockTransport(fake),
                           sleep=sleeps.append, clock=lambda: NOW)
    assert client.dry_run is True
    resp = client.product_set(PRODUCT_INPUT, identifier={"handle": PRODUCT_INPUT["handle"]}, idempotency_key=KEY)
    assert resp.dry_run and resp.ok and resp.data is None
    assert fake.requests == [] and client.requests_sent == 0
    events = client.audit.events(action="shopify.dry_run")
    assert len(events) == 1
    assert events[0].payload["variables"]["input"]["variants"][0]["price"] == "144.90"
    assert events[0].idempotency_key == KEY and events[0].dry_run is True


def test_dry_run_works_without_shop_configuration() -> None:
    client = ShopifyClient()
    resp = client.inventory_set_quantities(
        [inv()], reason="correction", reference_document_uri="pokeshop://stock-sync/X/v1", idempotency_key=KEY
    )
    assert resp.dry_run and not client.configured


def test_real_write_requires_configuration(fake: FakeShopify, sleeps: list[float]) -> None:
    with pytest.raises(ShopifyConfigError):
        set_inv(make_client(fake, sleeps, access_token=None))
    with pytest.raises(ShopifyConfigError):
        set_inv(make_client(fake, sleeps, shop_domain=None))
    assert fake.requests == []


# ------------------------------------------------------------------------- succès


def test_product_set_real_write_success_and_audit_without_token(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    resp = client.product_set(PRODUCT_INPUT, identifier={"handle": PRODUCT_INPUT["handle"]}, idempotency_key=KEY, dry_run=False)
    assert resp.ok and not resp.dry_run and not resp.replayed and resp.attempts == 1
    assert resp.root()["product"]["status"] == "DRAFT"
    assert resp.request_id == "FICTIF-REQ"
    assert len(fake.applied) == 1
    sent = fake.requests[0]
    assert sent["variables"]["identifier"] == {"handle": PRODUCT_INPUT["handle"]}
    assert sent["variables"]["synchronous"] is True
    assert fake.headers[0]["X-Shopify-Access-Token"] == TOKEN
    dump = json.dumps([e.model_dump(mode="json") for e in client.audit.events()])
    assert TOKEN not in dump and "shopify.write" in dump
    assert TOKEN not in repr(client.__dict__.get("_token"))
    record = client.idempotency.get("shopify:productSet", KEY)
    assert record is not None and record.status == "TERMINE"


def test_endpoint_uses_configured_api_version(fake: FakeShopify, sleeps: list[float]) -> None:
    assert make_client(fake, sleeps).endpoint == f"https://{SHOP}/admin/api/{DEFAULT_API_VERSION}/graphql.json"
    assert DEFAULT_API_VERSION == "2026-10"
    assert make_client(fake, sleeps, api_version="2026-07").endpoint.endswith("/2026-07/graphql.json")
    for bad in ("2026-05", "latest", "26-10"):
        with pytest.raises(ShopifyConfigError):
            make_client(fake, sleeps, api_version=bad)
    with pytest.raises(ShopifyConfigError):
        make_client(fake, sleeps, shop_domain="boutique.example.com")


def test_inventory_payload_uses_change_from_quantity_and_idempotent_directive(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    resp = set_inv(client)
    assert resp.ok and fake.levels[ITEM]["available"] == 7
    sent = fake.requests[0]
    assert "@idempotent(key: $idempotencyKey)" in sent["query"]
    q = sent["variables"]["input"]["quantities"][0]
    assert q == {"inventoryItemId": ITEM, "locationId": LOC, "quantity": 7, "changeFromQuantity": 5}
    assert sent["variables"]["idempotencyKey"] == KEY
    assert sent["variables"]["input"]["name"] == "available" and sent["variables"]["input"]["reason"] == "correction"
    text = json.dumps(sent)
    assert "compareQuantity" not in text and "ignoreCompareQuantity" not in text


# ------------------------------------------------------------------------ userErrors


def test_user_errors_are_returned_and_replayed_without_resend(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    stale = set_inv(client, change=inv(change_from=99))
    assert not stale.ok and stale.concurrency_conflict
    assert stale.user_errors[0].code == "CHANGE_FROM_QUANTITY_STALE"
    assert stale.user_errors[0].field == ("input", "quantities", "0")
    assert fake.applied == []
    again = set_inv(client, change=inv(change_from=99))
    assert again.replayed and again.concurrency_conflict and len(fake.requests) == 1
    assert client.idempotency.get("shopify:inventorySetQuantities", KEY).status == "ECHEC"
    assert client.audit.events(action="shopify.user_errors")


def test_product_set_user_errors(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script.append(ok_json({"productSet": {"product": None, "productSetOperation": None,
                                               "userErrors": [{"field": ["input", "handle"], "message": "pris", "code": "TAKEN"}]}}))
    resp = make_client(fake, sleeps).product_set(PRODUCT_INPUT, idempotency_key=KEY, dry_run=False)
    assert not resp.ok and resp.user_errors[0].code == "TAKEN" and not resp.concurrency_conflict


# ----------------------------------------------------------------- limitation de débit


def test_graphql_throttled_waits_on_query_cost_then_succeeds(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script.append(throttled(requested=100, available=50, restore="50.0"))
    resp = set_inv(make_client(fake, sleeps))
    assert resp.ok and resp.attempts == 2
    assert sleeps == [1.0]  # (100 − 50) / 50 points par seconde
    assert len(fake.applied) == 1


def test_http_429_respects_retry_after(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script.append(httpx.Response(429, headers={"Retry-After": "2"}))
    resp = set_inv(make_client(fake, sleeps))
    assert resp.ok and sleeps == [2.0]


def test_server_errors_retry_with_exponential_backoff(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script += [httpx.Response(502), httpx.Response(503)]
    resp = set_inv(make_client(fake, sleeps))
    assert resp.ok and resp.attempts == 3 and sleeps == [0.1, 0.2]


def test_throttling_exhausted_releases_claim_then_resume_writes_once(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps, max_retries=2)
    fake.script += [throttled(), throttled(), throttled()]
    with pytest.raises(ShopifyThrottledError):
        set_inv(client)
    assert client.idempotency.get("shopify:inventorySetQuantities", KEY) is None
    assert client.audit.events(action="shopify.write_failed")
    resp = set_inv(client)
    assert resp.ok and len(fake.applied) == 1


def test_transport_failure_exhausted(fake: FakeShopify, sleeps: list[float]) -> None:
    def boom(_: dict[str, Any]) -> httpx.Response:
        raise httpx.ConnectError("réseau coupé")

    fake.script += [boom, boom]
    with pytest.raises(ShopifyTransportError):
        set_inv(make_client(fake, sleeps, max_retries=1))
    fake.script += [httpx.Response(500), httpx.Response(500)]
    with pytest.raises(ShopifyTransportError):
        set_inv(make_client(fake, sleeps, max_retries=1), key="autre-cle-000001")


# --------------------------------------------------------------------- API refusée


def test_access_denied_is_not_retried_and_recovers_with_same_key(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    fake.script.append(httpx.Response(401, text="jeton invalide"))
    with pytest.raises(ShopifyAccessDeniedError):
        set_inv(client)
    assert len(fake.requests) == 1 and sleeps == []
    assert client.idempotency.get("shopify:inventorySetQuantities", KEY) is None
    resp = set_inv(client)  # jeton corrigé : la même écriture passe une seule fois
    assert resp.ok and len(fake.applied) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_http_forbidden_statuses_are_access_denied(fake: FakeShopify, sleeps: list[float], status: int) -> None:
    fake.script.append(httpx.Response(status))
    with pytest.raises(ShopifyAccessDeniedError):
        set_inv(make_client(fake, sleeps))


def test_graphql_access_denied_code(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script.append(httpx.Response(200, json={"errors": [{"message": "Access denied for inventorySetQuantities",
                                                             "extensions": {"code": "ACCESS_DENIED"}}]}))
    with pytest.raises(ShopifyAccessDeniedError):
        set_inv(make_client(fake, sleeps))


def test_graphql_validation_error_and_non_retryable_http(fake: FakeShopify, sleeps: list[float]) -> None:
    fake.script.append(httpx.Response(200, json={"errors": [{"message": "Field 'x' doesn't exist"}]}))
    with pytest.raises(ShopifyGraphQLError) as err:
        set_inv(make_client(fake, sleeps))
    assert "doesn't exist" in str(err.value)
    for status in (402, 404, 423):
        fake.script.append(httpx.Response(status, text="non"))
        with pytest.raises(ShopifyHTTPError) as http_err:
            set_inv(make_client(fake, sleeps), key=f"cle-statut-{status}")
        assert http_err.value.status_code == status
    fake.script.append(httpx.Response(200, text="pas du json"))
    with pytest.raises(ShopifyHTTPError):
        set_inv(make_client(fake, sleeps), key="cle-json-invalide")
    assert sleeps == []


# ---------------------------------------------------------------- idempotence et reprise


def test_replay_same_key_never_writes_twice(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    first = set_inv(client)
    second = set_inv(client)
    assert first.ok and second.ok and second.replayed
    assert len(fake.requests) == 1 and len(fake.applied) == 1
    assert client.audit.events(action="shopify.replay")


def test_connection_lost_after_apply_is_retried_with_same_key_and_deduplicated(fake: FakeShopify, sleeps: list[float]) -> None:
    def apply_then_drop(body: dict[str, Any]) -> httpx.Response:
        fake.default(body)  # Shopify a appliqué l'écriture…
        raise httpx.ReadError("connexion perdue")  # … mais la réponse est perdue

    fake.script.append(apply_then_drop)
    resp = set_inv(make_client(fake, sleeps))
    assert resp.ok and resp.attempts == 2
    assert len(fake.applied) == 1  # aucune double écriture
    assert fake.requests[0]["variables"]["idempotencyKey"] == fake.requests[1]["variables"]["idempotencyKey"] == KEY


def test_same_key_with_different_payload_is_refused(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    set_inv(client)
    with pytest.raises(ShopifyIdempotencyError):
        set_inv(client, change=inv(quantity=8, change_from=7))
    assert len(fake.applied) == 1
    assert client.audit.events(action="shopify.idempotency_conflict")


def test_fresh_in_flight_claim_is_refused_and_stale_claim_is_resent(fake: FakeShopify, sleeps: list[float]) -> None:
    store = InMemoryIdempotencyStore()
    variables = {"input": {"name": "available", "reason": "correction",
                           "referenceDocumentUri": "pokeshop://stock-sync/FICTIF/v1",
                           "quantities": [{"inventoryItemId": ITEM, "locationId": LOC, "quantity": 7,
                                           "changeFromQuantity": 5}]}}
    sha = payload_sha256({"mutation": "inventorySetQuantities", "variables": variables})
    status, _ = store.claim("shopify:inventorySetQuantities", KEY, sha, now=NOW - timedelta(minutes=1))
    assert status is ClaimStatus.NEW
    client = make_client(fake, sleeps, idempotency=store)
    with pytest.raises(ShopifyInFlightError):
        set_inv(client)
    assert fake.requests == []
    late = make_client(fake, sleeps, idempotency=store, clock=lambda: NOW + timedelta(hours=1))
    resp = set_inv(late)
    assert resp.ok and len(fake.applied) == 1
    assert late.audit.events(action="shopify.resume_stale_claim")


def test_derive_idempotency_key_is_deterministic() -> None:
    a = derive_idempotency_key("productSet", {"handle": "x"}, {"price": "10.00"})
    assert a == derive_idempotency_key("productSet", {"handle": "x"}, {"price": "10.00"})
    assert a != derive_idempotency_key("productSet", {"handle": "x"}, {"price": "10.90"})
    assert len(a) == 36


def test_idempotency_key_is_mandatory(fake: FakeShopify, sleeps: list[float]) -> None:
    with pytest.raises(ShopifyIdempotencyError):
        set_inv(make_client(fake, sleeps), key="court")


# ------------------------------------------------------------------ opérations interdites


@pytest.mark.parametrize(
    "document",
    [
        "mutation X($id: ID!) { orderUpdate(input: {id: $id}) { order { id } } }",
        "mutation X { orderEditBegin(id: \"gid://shopify/Order/1\") { calculatedOrder { id } } }",
        "mutation X { refundCreate(input: {}) { refund { id } } }",
        "mutation X { draftOrderCreate(input: {}) { draftOrder { id } } }",
        "mutation X { productVariantsBulkUpdate(productId: \"1\", variants: []) { userErrors { message } } }",
        "mutation X { productDelete(input: {id: \"1\"}) { deletedProductId } }",
    ],
)
def test_order_and_unlisted_mutations_are_forbidden(fake: FakeShopify, sleeps: list[float], document: str) -> None:
    client = make_client(fake, sleeps)
    with pytest.raises(ShopifyForbiddenOperationError):
        client.mutate(document, {}, idempotency_key=KEY, dry_run=False)
    with pytest.raises(ShopifyForbiddenOperationError):
        client.mutate(document, {}, idempotency_key=KEY)  # même en simulation
    assert fake.requests == []
    assert ALLOWED_MUTATIONS == {"productSet", "inventorySetQuantities", "metafieldsSet"}


def test_global_dry_run_switch_wins_over_call_parameter(fake: FakeShopify, sleeps: list[float]) -> None:
    """SEC-10 : ``POKESHOP_DRY_RUN=true`` => aucun appel ne peut écrire, même avec ``dry_run=False``."""
    settings = load_settings({"POKESHOP_SHOPIFY_SHOP_DOMAIN": SHOP, "POKESHOP_SHOPIFY_ADMIN_TOKEN": TOKEN})
    assert settings.dry_run is True
    client = ShopifyClient.from_settings(settings, transport=httpx.MockTransport(fake), sleep=sleeps.append)
    resp = client.product_set(PRODUCT_INPUT, identifier={"handle": PRODUCT_INPUT["handle"]}, idempotency_key=KEY,
                              dry_run=False)
    assert resp.dry_run is True and fake.requests == [] and client.requests_sent == 0
    assert set_inv(client, dry_run=False).dry_run is True
    assert fake.requests == []
    live = make_client(fake, sleeps)  # client en écriture réelle : un appel peut encore restreindre
    assert live.product_set(PRODUCT_INPUT, idempotency_key=KEY, dry_run=True).dry_run is True
    assert fake.requests == []


@pytest.mark.parametrize(
    "document",
    [
        # alias : le premier nom lu est « productSet », la mutation réelle est orderCancel
        "mutation M($id: ID!) { productSet: orderCancel(orderId: $id, reason: OTHER, refund: false, restock: false) "
        "{ userErrors { message } } }",
        # deux champs racine : productSet puis productDelete
        "mutation M($input: ProductSetInput!) { productSet(input: $input) { product { id } } "
        "productDelete(input: {id: \"gid://shopify/Product/1\"}) { deletedProductId } }",
        # document constant modifié (champ supplémentaire)
        PRODUCT_SET_MUTATION.replace("userErrors { field message code }",
                                     "userErrors { field message code } } productDelete(input: {id: \"1\"}) { deletedProductId"),
    ],
)
def test_mutation_whitelist_compares_exact_constant_documents(fake: FakeShopify, sleeps: list[float], document: str) -> None:
    """SEC-11 : alias GraphQL, second champ racine ou document modifié => refus avant tout envoi."""
    client = make_client(fake, sleeps)
    for dry in (True, False):
        with pytest.raises(ShopifyForbiddenOperationError):
            client.mutate(document, {"input": dict(PRODUCT_INPUT)}, idempotency_key=KEY, dry_run=dry)
    assert fake.requests == [] and client.requests_sent == 0


def test_mutate_applies_sensitive_field_checks_itself(fake: FakeShopify, sleeps: list[float]) -> None:
    """SEC-11 : ``mutate(productSet)`` direct ne contourne plus la liste blanche des champs publics."""
    client = make_client(fake, sleeps)
    leaking = {"title": "Display", "status": "ACTIVE", "vendor": "Asmodee (prix B2B 98.50)",
               "metafields": [{"namespace": "interne", "key": "cout_achat_fournisseur", "type": "number_decimal",
                               "value": "98.50"}]}
    for dry in (True, False):
        with pytest.raises(SensitiveFieldError):
            client.mutate(PRODUCT_SET_MUTATION, {"input": leaking, "identifier": None, "synchronous": True},
                          idempotency_key=KEY, dry_run=dry)
    with pytest.raises(SensitiveFieldError):
        client.mutate(METAFIELDS_SET_MUTATION, {"metafields": leaking["metafields"]}, idempotency_key=KEY)
    assert fake.requests == []


def test_protective_product_set_accepts_status_only(fake: FakeShopify, sleeps: list[float]) -> None:
    """SEC-15 : une dépublication protectrice n'envoie que ``{"status": "DRAFT"}`` avec l'identifiant."""
    client = make_client(fake, sleeps)
    with pytest.raises(SensitiveFieldError):
        client.product_set(PRODUCT_INPUT, identifier={"id": "gid://shopify/Product/7"}, idempotency_key=KEY,
                           protective=True)
    with pytest.raises(ShopifyConfigError):
        client.product_set({"status": "DRAFT"}, identifier={"handle": "x"}, idempotency_key=KEY, protective=True)
    resp = client.product_set({"status": "DRAFT"}, identifier={"id": "gid://shopify/Product/7"},
                              idempotency_key=KEY, protective=True, dry_run=True)
    assert resp.dry_run and fake.requests == []


def test_query_refuses_mutations_and_inventory_requires_directive(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    with pytest.raises(ShopifyForbiddenOperationError):
        client.query(PRODUCT_SET_MUTATION, {})
    without = INVENTORY_SET_QUANTITIES_MUTATION.replace(" @idempotent(key: $idempotencyKey)", "")
    with pytest.raises(ShopifyForbiddenOperationError):
        client.mutate(without, {}, idempotency_key=KEY)
    with pytest.raises(ShopifyForbiddenOperationError):
        root_field("{ shop { name } }")
    assert root_field(PRODUCT_SET_MUTATION) == ("mutation", "productSet")
    assert allowed_mutation(PRODUCT_SET_MUTATION) == "productSet"
    assert allowed_mutation(INVENTORY_SET_QUANTITIES_MUTATION) == "inventorySetQuantities"


def test_query_requires_configuration(fake: FakeShopify, sleeps: list[float]) -> None:
    with pytest.raises(ShopifyConfigError):
        make_client(fake, sleeps, access_token=None).inventory_levels([ITEM], LOC)


# ----------------------------------------------------------------------- validations


def test_product_set_refuses_sensitive_fields_before_any_send(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    leaking = json.loads(json.dumps(PRODUCT_INPUT))
    leaking["variants"][0]["inventoryItem"]["cost"] = "95.00"
    for dry in (True, False):
        with pytest.raises(SensitiveFieldError) as err:
            client.product_set(leaking, idempotency_key=KEY, dry_run=dry)
        assert "inventoryItem.cost" in str(err.value)
    assert fake.requests == [] and client.audit.events() == ()


def test_product_set_refuses_supplier_terms_configured_on_client(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps, sensitive_terms=("fictif_grossiste_a",))
    leaking = dict(PRODUCT_INPUT, descriptionHtml="<p>Arrivage fictif_grossiste_a</p>")
    with pytest.raises(SensitiveFieldError):
        client.product_set(leaking, idempotency_key=KEY)


def test_product_set_identifier_validation(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    for bad in ({"id": "123"}, {"handle": "a", "id": "gid://shopify/Product/1"}, {"sku": "x"}):
        with pytest.raises(ShopifyConfigError):
            client.product_set(PRODUCT_INPUT, identifier=bad, idempotency_key=KEY)


@pytest.mark.parametrize(
    ("kwargs", "change"),
    [
        ({"reason": "inventaire"}, None),
        ({"reference_document_uri": "pas une uri"}, None),
        ({"name": "committed"}, None),
    ],
)
def test_inventory_input_validation(fake: FakeShopify, sleeps: list[float], kwargs: dict[str, str], change: Any) -> None:
    client = make_client(fake, sleeps)
    params = {"reason": "correction", "reference_document_uri": "pokeshop://stock-sync/X/v1", "idempotency_key": KEY}
    params.update(kwargs)
    with pytest.raises(ShopifyConfigError):
        client.inventory_set_quantities([inv()], **params)


def test_inventory_change_model_validation(fake: FakeShopify, sleeps: list[float]) -> None:
    with pytest.raises(ValueError):
        InventoryChange(inventory_item_id="1001", location_id=LOC, quantity=1, change_from_quantity=0)
    with pytest.raises(ValueError):
        InventoryChange(inventory_item_id=ITEM, location_id="gid://shopify/Location/x", quantity=1, change_from_quantity=0)
    with pytest.raises(ValueError):
        InventoryChange(inventory_item_id=ITEM, location_id=LOC, quantity=-1, change_from_quantity=0)
    client = make_client(fake, sleeps)
    with pytest.raises(ShopifyConfigError):
        client.inventory_set_quantities([], reason="correction", reference_document_uri="pokeshop://x/y", idempotency_key=KEY)
    with pytest.raises(ShopifyConfigError):
        client.inventory_set_quantities([inv(), inv()], reason="correction", reference_document_uri="pokeshop://x/y",
                                        idempotency_key=KEY)


def test_metafields_set_only_public_metafields(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    good = [{"ownerId": "gid://shopify/Product/7", "namespace": "boutique", "key": "statut_stock",
             "type": "single_line_text_field", "value": "rupture"}]
    assert client.metafields_set(good, idempotency_key=KEY, dry_run=False).ok
    for bad in (
        [{**good[0], "key": "cout_rendu", "value": "95.00"}],
        [{**good[0], "namespace": "interne"}],
        [{**good[0], "ownerId": "1"}],
        [{**good[0], "value": "fournisseur X"}],
        [{**good[0], "value": "inconnu"}],
    ):
        with pytest.raises(SensitiveFieldError):
            client.metafields_set(bad, idempotency_key="autre-cle-0002")


# ------------------------------------------------------------------------ lectures


def test_inventory_levels_and_product_by_handle(fake: FakeShopify, sleeps: list[float]) -> None:
    client = make_client(fake, sleeps)
    levels = client.inventory_levels([ITEM, ITEM2], LOC)
    assert set(levels) == {ITEM}
    assert (levels[ITEM].available, levels[ITEM].committed, levels[ITEM].on_hand) == (5, 1, 6)
    assert client.inventory_levels([], LOC) == {}
    with pytest.raises(ShopifyConfigError):
        client.inventory_levels(["1001"], LOC)
    assert client.product_by_handle("inconnue") is None
    client.product_set(PRODUCT_INPUT, idempotency_key=KEY, dry_run=False)
    product = client.product_by_handle(PRODUCT_INPUT["handle"])
    assert product is not None and product.status == "DRAFT"
    assert product.variants[0].price == D("144.90") and product.variants[0].sku == "DSP-FICTIF_ALPHA-FR"
    assert client.last_cost is not None and client.last_cost.restore_rate == D("50.0")


def test_from_settings_inherits_dry_run_and_versions() -> None:
    settings = load_settings({"POKESHOP_SHOPIFY_SHOP_DOMAIN": SHOP, "POKESHOP_SHOPIFY_ADMIN_TOKEN": TOKEN,
                              "POKESHOP_SHOPIFY_API_VERSION": "2026-07", "POKESHOP_SHOPIFY_MAX_RETRIES": "2"})
    client = ShopifyClient.from_settings(settings, audit=InMemoryAuditLog())
    assert client.dry_run is True and client.configured and client.api_version == "2026-07"
    assert client.max_retries == 2
    real = ShopifyClient.from_settings(load_settings({"POKESHOP_DRY_RUN": "false"}))
    assert real.dry_run is False and not real.configured
