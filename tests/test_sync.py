"""Tests du cycle « fournisseur → site » en 8 étapes (BP §12) et de la synchronisation du stock local.

Jeux d'essai FICTIFS du dépôt (``data/samples``) ; boutique Shopify simulée (httpx.MockTransport).
Le chemin d'écriture réelle est testé sur une « boutique de test » (recette) : sur la boutique de
production, une donnée FICTIVE n'est jamais publiée.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from pokeshop.audit import InMemoryAuditLog
from pokeshop.autonomy import AutonomyController, GateReason, GovernanceGate
from pokeshop.catalog import DEFAULT_EXTENSIONS_PATH, CatalogProduct, load_extension_table, normalize_identity
from pokeshop.costs import PriceHistory
from pokeshop.importers import run_import
from pokeshop.incidents import IncidentCode, IncidentManager, LogNotifier, Severity
from pokeshop.models import ReplacementCost, StockLevel
from pokeshop.pricing import decide_price
from pokeshop.publish import CatalogListing, ImageRights, PlanOutcome, PublicImage, ShopStatus, StockStatus
from pokeshop.rules import load_rules
from pokeshop.shopify_client import RemoteInventoryLevel, ShopifyClient
from pokeshop.stock import StockRegistry
from pokeshop.stoploss import (
    CapitalMovement,
    NetWorthSnapshot,
    ProductMargin,
    StopLossEngine,
    StopLossState,
    hash_owner_token,
    load_stoploss_config,
)
from pokeshop.sync import (
    WORKFLOW_SUPPLIER_TO_SHOP,
    OfferCostInputs,
    StockSyncReport,
    SyncContext,
    SyncError,
    SyncService,
    SyncStep,
    consecutive_clean_runs,
    price_reference_24h,
    stock_target,
)
from test_autonomy import signed_mandate  # noqa: E402  (mandat FICTIF signé en mémoire)

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 11, 10, 10, 0, tzinfo=TZ)
ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
CSV_A = SAMPLES / "FICTIF_offres_grossiste_a.csv"
TABLE = load_extension_table([DEFAULT_EXTENSIONS_PATH, SAMPLES / "FICTIF_extensions_aliases.yaml"])
RULES = load_rules()
OWNER_HASH = hash_owner_token("FICTIF-jeton-proprietaire-tres-long-0001")
SHOP = "fictif-recette.myshopify.com"
LOC = "gid://shopify/Location/42"
ITEM = "gid://shopify/InventoryItem/1001"
FX = OfferCostInputs(inbound_freight_alloc=D("2.00"), customs_and_fees=D("0"), import_vat=D("0"),
                     fx_rate_to_chf=D("0.9375"), fx_source="FICTIF taux de test", fx_date=NOW.date())


def offers_by_sku() -> dict[str, Any]:
    result = run_import("fictif_grossiste_a", CSV_A, now=SOURCE_NOW, extensions=TABLE)
    return result.offers_by_sku


SOURCE_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=TZ)  # le flux FICTIF est daté du 4.10.2026 06:00


def identity_of(sku: str) -> Any:
    o = offers_by_sku()[sku]
    return normalize_identity(gtin=o.gtin, language=o.language, extension=o.extension, format=o.format,
                              content=o.content, sealed=o.sealed, table=TABLE).identity


IDENT_A1 = identity_of("FICTIF-A-001")


def listing(**kw: Any) -> CatalogListing:
    base: dict[str, Any] = dict(
        product_key="FICTIF-P1", identity=IDENT_A1, public_sku="DSP-FICTIF_ALPHA-FR",
        description_html="<p>Display de l'extension Extension Fictive Alpha, en français, neuf et scellé.</p>",
        images=(PublicImage(url="https://cdn.example.org/fictif.jpg", alt="Display face avant", rights=ImageRights.OWN_PHOTO),),
        stock_status=StockStatus.STOCK_LOCAL, content_text="36 boosters", content_validated=True,
        category_rule_validated=True, fictif=True, shopify_inventory_item_id=ITEM,
    )
    base.update(kw)
    return CatalogListing(**base)


def context(item: CatalogListing | None = None, **kw: Any) -> SyncContext:
    item = item or listing()
    base: dict[str, Any] = dict(
        rules=RULES, catalog_products=[CatalogProduct(product_id="FICTIF-P1", identity=IDENT_A1)],
        listings={"FICTIF-P1": item}, table=TABLE, cost_inputs={"fictif_grossiste_a": FX},
    )
    base.update(kw)
    return SyncContext(**base)


def healthy_state(at: datetime, **kw: Any) -> StopLossState:
    base: dict[str, Any] = dict(
        as_of=at, stock_budget_chf=D("3000"), cash_available_chf=D("5000"),
        capital_movements=(CapitalMovement(movement_id="FICTIF_APPORT", at=at - timedelta(days=30),
                                           kind="CONTRIBUTION", amount=D("8000")),),
        net_worth=NetWorthSnapshot(as_of=at, cash_chf=D("8000")), ads_daily_cap_chf=D("33"),
    )
    base.update(kw)
    return StopLossState(**base)


class FakeShop:
    """Boutique de test simulée : productSet, lecture par handle, inventaire avec compare-and-swap."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.applied: list[dict[str, Any]] = []
        self.products: dict[str, dict[str, Any]] = {}
        self.levels: dict[str, dict[str, int]] = {ITEM: {"available": 0, "committed": 0, "on_hand": 0}}
        self.idempotent: dict[str, httpx.Response] = {}
        self.price_override: str | None = None
        self.deny = False
        self.before_inventory_write: Callable[[], None] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.deny:
            return httpx.Response(403)
        q, v = body["query"], body.get("variables") or {}
        if "productSet" in q:
            data = v["input"]
            self.products[data["handle"]] = data
            self.applied.append({"productSet": data})
            return httpx.Response(200, json={"data": {"productSet": {"product": {"id": "gid://shopify/Product/7"},
                                                                     "productSetOperation": None, "userErrors": []}}})
        if "productByIdentifier" in q:
            data = self.products.get(v["identifier"]["handle"])
            if data is None:
                return httpx.Response(200, json={"data": {"productByIdentifier": None}})
            price = self.price_override or data["variants"][0]["price"]
            return httpx.Response(200, json={"data": {"productByIdentifier": {
                "id": "gid://shopify/Product/7", "handle": data["handle"], "status": data["status"], "title": data["title"],
                "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "sku": "x", "price": price,
                                        "barcode": data["variants"][0]["barcode"], "inventoryItem": {"id": ITEM}}]}}}})
        if "inventorySetQuantities" in q:
            key = v["idempotencyKey"]
            if key in self.idempotent:
                return self.idempotent[key]
            if self.before_inventory_write is not None:
                hook, self.before_inventory_write = self.before_inventory_write, None
                hook()
            errors = []
            for item in v["input"]["quantities"]:
                current = self.levels[item["inventoryItemId"]]
                if item["changeFromQuantity"] != current["available"]:
                    errors.append({"code": "CHANGE_FROM_QUANTITY_STALE", "field": None, "message": "quantité modifiée"})
            if not errors:
                for item in v["input"]["quantities"]:
                    self.levels[item["inventoryItemId"]]["available"] = item["quantity"]
                self.applied.append({"inventory": v["input"]})
            resp = httpx.Response(200, json={"data": {"inventorySetQuantities": {"inventoryAdjustmentGroup": None,
                                                                                 "userErrors": errors}}})
            self.idempotent[key] = resp
            return resp
        if "nodes(ids" in q:
            return httpx.Response(200, json={"data": {"nodes": [
                {"id": i, "sku": "x", "inventoryLevel": {"quantities": [{"name": n, "quantity": val} for n, val in self.levels[i].items()]}}
                for i in v["ids"] if i in self.levels]}})
        return httpx.Response(400)


class Env:
    """Service de synchronisation complet (porte, incidents, client) avec boutique simulée."""

    def __init__(self, *, level: int = 3, real: bool = True, test_store: bool = True, configured: bool = True,
                 state_kw: dict[str, Any] | None = None, at: datetime = SOURCE_NOW) -> None:
        self.now = at
        clock = lambda: self.now  # noqa: E731
        self.shop = FakeShop()
        self.audit = InMemoryAuditLog(clock=clock)
        self.autonomy = AutonomyController(audit=self.audit, owner_token_sha256=OWNER_HASH, default_level=level, clock=clock)
        self.notifier = LogNotifier()
        self.incidents = IncidentManager(audit=self.audit, notifier=self.notifier,
                                         on_critical=self.autonomy.on_critical_incident, clock=clock)
        self.state = healthy_state(at, **(state_kw or {}))
        signed = signed_mandate()  # signé la veille du cycle (le flux FICTIF est daté du 4.10.2026)
        mandate = signed.replace(valid_from=at.date() - timedelta(days=1),
                                 approval=signed.approval.replace(approved_at=at - timedelta(days=1)))
        assert mandate.is_active(at)
        self.gate = GovernanceGate(
            self.autonomy, audit=self.audit, stoploss_engine=StopLossEngine(load_stoploss_config(), owner_token_sha256=OWNER_HASH),
            state_provider=lambda: self.state, mandate_provider=lambda: mandate,
            incidents=self.incidents, real_writes_enabled=real, clock=clock,
        )
        self.client = ShopifyClient(shop_domain=SHOP if configured else None, access_token="shpat_FICTIF" if configured else None,
                                    transport=httpx.MockTransport(self.shop), audit=self.audit, clock=clock,
                                    sleep=lambda s: None, max_retries=1)
        self.history = PriceHistory()
        self.sync = SyncService(client=self.client, gate=self.gate, incidents=self.incidents, audit=self.audit,
                                price_history=self.history, clock=clock, test_store=test_store)

    def cycle(self, ctx: SyncContext | None = None, *, dry_run: bool = True, source: Path = CSV_A, mapping: str = "fictif_grossiste_a"):
        return self.sync.run_supplier_cycle(mapping, source, ctx or context(), now=self.now, dry_run=dry_run)


def item_for(report: Any, product_id: str = "FICTIF-P1") -> Any:
    return next(i for i in report.items if i.product_id == product_id)


# ------------------------------------------------------------------------------ simulation


def test_dry_run_cycle_runs_the_eight_steps_without_any_shop_call() -> None:
    env = Env()
    report = env.cycle()
    assert [s.step for s in report.steps] == list(SyncStep)
    assert all(s.status != "IGNORE" for s in report.steps)
    assert report.dry_run and report.clean and report.fictif
    assert report.import_status == "PARTIAL" and report.offers_accepted > 0
    assert env.shop.requests == []
    p1 = item_for(report)
    assert p1.match_status == "MATCHED" and p1.decision_status == "OK" and p1.plan_outcome == "SEND_ACTIVE"
    assert p1.action == "PUBLISH_NEW_PRODUCT" and p1.gate_allowed and not p1.written and p1.verified
    assert p1.price_chf is not None and str(p1.price_chf).endswith(".90")
    assert env.audit.events(action="shopify.dry_run")
    assert env.audit.events(action="sync.cycle")[0].payload["supplier_id"] == "fictif_grossiste_a"
    new_drafts = [i for i in report.items if i.match_status == "NEW_DRAFT"]
    assert new_drafts and all(i.plan_outcome == "NOT_SENT" for i in new_drafts)
    md = report.render_markdown()
    assert "SIMULATION" in md and "## Validation humaine requise" in md and "Rapprocher la référence exacte" in md
    events = env.history.events("FICTIF-P1")
    assert events and all(e.kind.value == "PROPOSED" for e in events)  # rien de publié en simulation


def test_report_items_never_carry_costs() -> None:
    report = Env().cycle()
    dumped = report.model_dump_json()
    assert "landed" not in dumped and "contribution" not in dumped and "floor" not in dumped


def test_simulated_anomalies_open_simulation_incidents_without_containment() -> None:
    env = Env()
    report = env.cycle()
    assert report.incident_ids
    for incident_id in report.incident_ids:
        incident = env.incidents.get(incident_id)
        assert incident.simulation and incident.containment == ()
    assert env.incidents.suspended() == {} and env.autonomy.level == 3


def test_twenty_dry_run_cycles_without_critical_error() -> None:
    env = Env()
    for _ in range(20):
        env.cycle()
    assert consecutive_clean_runs(env.sync.history) == 20
    assert env.shop.requests == []


def test_missing_cost_inputs_keep_the_listing_as_internal_draft() -> None:
    env = Env()
    report = env.cycle(context(cost_inputs={}))
    p1 = item_for(report)
    assert p1.decision_status == "DRAFT" and p1.plan_outcome == "NOT_SENT"
    assert report.step(SyncStep.COST).status == "AVERTISSEMENT"


def test_ambiguous_identity_opens_inc02() -> None:
    other = CatalogProduct(product_id="FICTIF-P9", identity=IDENT_A1.replace(content="30 BOOSTERS"))
    env = Env()
    report = env.cycle(context(catalog_products=[other]))
    ambiguous = [i for i in report.items if i.match_status == "AMBIGUOUS"]
    assert ambiguous and ambiguous[0].incident_ids
    assert env.incidents.get(ambiguous[0].incident_ids[0]).code is IncidentCode.INC_02


def test_product_without_listing_is_not_published() -> None:
    report = Env().cycle(context(listings={}))
    p1 = item_for(report)
    assert p1.plan_outcome == "NOT_SENT" and "fiche validée" in p1.messages[0]


# ----------------------------------------------------------------------- flux en panne


def test_fictif_mapping_is_refused_for_the_production_shop() -> None:
    env = Env(test_store=False)
    report = env.cycle(dry_run=False)
    assert report.step(SyncStep.FETCH).status == "ECHEC" and "simulation uniquement" in report.step(SyncStep.FETCH).detail
    assert report.step(SyncStep.PUBLISH).status == "IGNORE"
    assert env.shop.requests == []
    incident = env.incidents.get(report.incident_ids[0])
    assert incident.code is IncidentCode.INC_03 and env.incidents.is_suspended("source:fictif_grossiste_a")


def test_stale_feed_is_quarantined_and_never_touches_local_stock() -> None:
    env = Env(at=SOURCE_NOW + timedelta(days=3))
    registry = StockRegistry(clock=lambda: env.now)
    registry.receive("DSP-FICTIF_ALPHA-FR", 6, "réception FICTIVE", at=env.now)
    before = registry.level("DSP-FICTIF_ALPHA-FR")
    report = env.cycle()
    assert report.import_status == "QUARANTINED" and report.step(SyncStep.VALIDATE).status == "ECHEC"
    assert env.incidents.get(report.incident_ids[0]).code is IncidentCode.INC_03
    assert registry.level("DSP-FICTIF_ALPHA-FR") == before
    stock = env.sync.push_stock([(listing(), before)], location_id=LOC, dry_run=True)
    assert stock.lines[0].target_available == 6  # le stock local confirmé reste vendable


# ------------------------------------------------------------------- écriture réelle (recette)


def test_real_cycle_on_test_store_publishes_verifies_and_never_writes_twice() -> None:
    env = Env()
    first = env.cycle(dry_run=False)
    p1 = item_for(first)
    assert first.clean and p1.written and p1.verified and p1.gate_allowed and not p1.replayed
    assert len([a for a in env.shop.applied if "productSet" in a]) == 1
    sent = env.shop.products[next(iter(env.shop.products))]
    assert sent["status"] == "ACTIVE" and sent["variants"][0]["inventoryPolicy"] == "DENY"
    assert "fictif_grossiste_a" not in json.dumps(sent) and "FICTIF-A-001" not in json.dumps(sent)
    published = [e for e in env.history.events("FICTIF-P1") if e.kind.value == "PUBLISHED"]
    assert len(published) == 1 and published[0].price == p1.price_chf
    second = env.cycle(dry_run=False)
    p1b = item_for(second)
    assert p1b.replayed and p1b.verified
    assert len([a for a in env.shop.applied if "productSet" in a]) == 1  # reprise sans double écriture
    assert consecutive_clean_runs(env.sync.history) == 2
    assert not env.incidents.is_suspended("source:fictif_grossiste_a")  # escalade d'import : signalement seul


def test_last_check_in_client_turns_a_leak_into_a_critical_error() -> None:
    env = Env()
    env.client.sensitive_terms = ("FICTIF-LOT-77",)
    item = listing(description_html="<p>Display de l'extension Extension Fictive Alpha (lot FICTIF-LOT-77).</p>")
    report = env.cycle(context(item), dry_run=False)
    p1 = item_for(report)
    assert not p1.written and not report.clean and "charge publique refusée" in report.critical_errors[0]
    leak = [env.incidents.get(i) for i in p1.incident_ids if env.incidents.get(i).code is IncidentCode.INC_07]
    assert leak and leak[0].severity is Severity.CRITIQUE
    assert [a for a in env.shop.applied if "productSet" in a] == []


def test_real_cycle_refused_by_level_writes_nothing() -> None:
    env = Env(level=2)
    report = env.cycle(dry_run=False)
    p1 = item_for(report)
    assert not p1.gate_allowed and GateReason.AUTONOMY_LEVEL_TOO_LOW.value in p1.gate_reasons
    assert not p1.written and env.shop.requests == []


def test_shop_api_refused_suspends_the_workflow() -> None:
    env = Env()
    env.shop.deny = True
    report = env.cycle(dry_run=False)
    assert report.step(SyncStep.PUBLISH).status == "ECHEC"
    incident = next(env.incidents.get(i) for i in report.incident_ids if env.incidents.get(i).code is IncidentCode.INC_08)
    assert "API boutique refusée" in incident.cause and env.incidents.is_suspended(WORKFLOW_SUPPLIER_TO_SHOP)
    env.shop.deny = False
    again = env.cycle(dry_run=False)
    assert GateReason.WORKFLOW_SUSPENDED.value in item_for(again).gate_reasons
    assert [a for a in env.shop.applied if "productSet" in a] == []


def test_verification_mismatch_is_a_critical_error_and_demotes_autonomy() -> None:
    env = Env()
    env.shop.price_override = "1.90"
    report = env.cycle(dry_run=False)
    assert not report.clean and "vérification" in report.critical_errors[0]
    p1 = item_for(report)
    assert p1.verified is False
    critical = [env.incidents.get(i) for i in p1.incident_ids if env.incidents.get(i).severity is Severity.CRITIQUE]
    assert critical and critical[0].code is IncidentCode.INC_01
    assert env.autonomy.level == 2  # incident critique : niveau précédent
    assert consecutive_clean_runs(env.sync.history) == 0


def test_product_stoploss_unpublishes_existing_listing() -> None:
    env = Env(state_kw={"products": (ProductMargin(product_key="FICTIF-P1", contribution_chf=D("3"),
                                                   contribution_pct=D("0.03")),)})
    item = listing(shopify_product_id="gid://shopify/Product/7", shopify_status=ShopStatus.ACTIVE, approved=True,
                   current_price_chf=D("149.90"))
    report = env.cycle(context(item), dry_run=False)
    p1 = item_for(report)
    assert p1.plan_outcome == PlanOutcome.UNPUBLISH.value and p1.action == "UNPUBLISH_PRODUCT"
    assert p1.written and p1.price_chf == D("149.90")
    assert env.shop.products[next(iter(env.shop.products))]["status"] == "DRAFT"


def test_price_anomaly_quarantines_the_reference_in_real_mode() -> None:
    env = Env()
    env.sync.replacement_costs.update(
        ReplacementCost(product_key="FICTIF-P1", supplier_id="fictif_grossiste_a", unit_cost=D("9.00"),
                        source_ts=SOURCE_NOW - timedelta(hours=1))
    )
    report = env.cycle(dry_run=False)
    p1 = item_for(report)
    assert "PRICE_ANOMALY" in p1.decision_reasons and p1.decision_status == "BLOCKED"
    assert env.incidents.is_quarantined("FICTIF-P1")
    assert p1.plan_outcome == "NOT_SENT" and not p1.written


# -------------------------------------------------------------------------------- utilitaires


def test_price_reference_24h() -> None:
    history = PriceHistory()
    assert price_reference_24h(history, "P", NOW, D("10.90")) == D("10.90")
    assert price_reference_24h(None, "P", NOW, None) is None
    decision = decide_price(D("100"), RULES.pricing)
    history.publish("P", decision.recommended_price, NOW - timedelta(hours=30), "test", validated=True, decision=decision)
    history.publish("P", D("200.00"), NOW - timedelta(hours=2), "test", validated=True)
    assert price_reference_24h(history, "P", NOW) == decision.recommended_price
    fresh = PriceHistory()
    fresh.publish("Q", D("50.90"), NOW - timedelta(hours=3), "test", validated=True)
    fresh.publish("Q", D("52.90"), NOW - timedelta(hours=1), "test", validated=True)
    assert price_reference_24h(fresh, "Q", NOW) == D("50.90")


def test_stock_target_uses_the_most_conservative_reservation() -> None:
    level = StockLevel(sku="S", on_hand=10, reserved=1, damaged=1, safety=1, version=3)
    t = stock_target(level, RemoteInventoryLevel(inventory_item_id=ITEM, available=8, committed=3, on_hand=10))
    assert t.target_available == 5 and t.reserved_effective == 3
    assert any("ECART_RESERVATIONS" in d for d in t.discrepancies) and any("ECART_PHYSIQUE" in d for d in t.discrepancies)
    assert not t.oversell
    blocked = stock_target(level, RemoteInventoryLevel(inventory_item_id=ITEM, available=8), blocked=True)
    assert blocked.target_available == 0
    oversold = stock_target(StockLevel(sku="S", on_hand=1, reserved=1, damaged=0, safety=0, version=1),
                            RemoteInventoryLevel(inventory_item_id=ITEM, available=0, committed=2))
    assert oversold.oversell and oversold.target_available == 0


def test_consecutive_clean_runs_stops_at_first_critical() -> None:
    ok = StockSyncReport(run_id="a", at=NOW, dry_run=True, location_id=LOC, lines=())
    bad = ok.replace(run_id="b", critical_errors=("survente",))
    assert consecutive_clean_runs([ok, bad, ok, ok]) == 2 and consecutive_clean_runs([]) == 0


# --------------------------------------------------------------------------------- stock local


def level(on_hand: int = 6, reserved: int = 0, **kw: Any) -> StockLevel:
    return StockLevel(sku="DSP-FICTIF_ALPHA-FR", on_hand=on_hand, reserved=reserved, damaged=kw.get("damaged", 0),
                      safety=kw.get("safety", 0), version=kw.get("version", 1))


def test_push_stock_dry_run_assumes_remote_and_sends_nothing() -> None:
    env = Env(configured=False)
    report = env.sync.push_stock([(listing(), level())], location_id=LOC, dry_run=True)
    line = report.lines[0]
    assert line.action == "SET" and line.remote_assumed and line.target_available == 6 and not line.written
    assert env.shop.requests == [] and report.dry_run


def test_push_stock_real_write_with_cas_and_no_double_write() -> None:
    env = Env(level=2)
    env.shop.levels[ITEM] = {"available": 2, "committed": 1, "on_hand": 3}
    report = env.sync.push_stock([(listing(), level(on_hand=6, reserved=1))], location_id=LOC, dry_run=False)
    line = report.lines[0]
    assert line.action == "SET" and line.written and line.target_available == 5
    assert env.shop.levels[ITEM]["available"] == 5
    sent = [a["inventory"] for a in env.shop.applied]
    assert sent[0]["quantities"][0]["changeFromQuantity"] == 2 and sent[0]["reason"] == "correction"
    again = env.sync.push_stock([(listing(), level(on_hand=6, reserved=1))], location_id=LOC, dry_run=False)
    assert again.lines[0].action == "NONE" and len(env.shop.applied) == 1
    assert any("ECART_PHYSIQUE" in d for d in line.discrepancies)


def test_push_stock_retries_after_concurrent_sale() -> None:
    env = Env(level=2)
    env.shop.levels[ITEM] = {"available": 2, "committed": 0, "on_hand": 2}

    def concurrent_sale() -> None:
        env.shop.levels[ITEM] = {"available": 1, "committed": 1, "on_hand": 2}

    env.shop.before_inventory_write = concurrent_sale
    report = env.sync.push_stock([(listing(), level(on_hand=6))], location_id=LOC, dry_run=False)
    line = report.lines[0]
    assert line.action == "SET" and line.written
    assert any("conflit de concurrence" in r for r in line.reasons)
    assert env.shop.levels[ITEM]["available"] == 5  # 6 physiques − 1 engagé Shopify
    assert len(env.shop.applied) == 1


def test_push_stock_detects_oversell_as_critical() -> None:
    env = Env(level=2)
    env.shop.levels[ITEM] = {"available": 0, "committed": 3, "on_hand": 3}
    report = env.sync.push_stock([(listing(), level(on_hand=2, reserved=2))], location_id=LOC, dry_run=False)
    assert not report.clean and "survente" in report.critical_errors[0]
    incident = env.incidents.get(report.incident_ids[0])
    assert incident.code is IncidentCode.INC_06 and incident.severity is Severity.CRITIQUE
    assert env.autonomy.level == 1


def test_push_stock_blocked_product_sets_zero_even_at_level_one() -> None:
    env = Env(level=1, state_kw={"products": (ProductMargin(product_key="FICTIF-P1", contribution_chf=D("2"),
                                                            contribution_pct=D("0.02")),)})
    env.shop.levels[ITEM] = {"available": 4, "committed": 0, "on_hand": 4}
    report = env.sync.push_stock([(listing(), level(on_hand=4))], location_id=LOC, dry_run=False)
    line = report.lines[0]
    assert line.target_available == 0 and line.written and env.shop.levels[ITEM]["available"] == 0
    assert any("BLOQUE" in r for r in line.reasons)


def test_push_stock_refused_at_level_one_for_normal_sync() -> None:
    env = Env(level=1)
    env.shop.levels[ITEM] = {"available": 0, "committed": 0, "on_hand": 0}
    report = env.sync.push_stock([(listing(), level(on_hand=3))], location_id=LOC, dry_run=False)
    line = report.lines[0]
    assert line.action == "REFUSED" and GateReason.AUTONOMY_LEVEL_TOO_LOW.value in line.reasons
    assert env.shop.applied == []


def test_push_stock_input_validation() -> None:
    env = Env(configured=False)
    with pytest.raises(SyncError):
        env.sync.push_stock([(listing(shopify_inventory_item_id=None), level())], location_id=LOC)
    with pytest.raises(SyncError):
        env.sync.push_stock([(listing(), level().replace(sku="AUTRE-SKU"))], location_id=LOC)
    with pytest.raises(SyncError):
        env.sync.push_stock([(listing(), level())], location_id=LOC, dry_run=False)  # quantité Shopify inconnue
