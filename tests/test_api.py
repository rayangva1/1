"""Tests de l'API FastAPI (TestClient) : chaque route, authentification, montants en chaînes, gouvernance.

Inclut le contrôle des fichiers de déploiement (Dockerfile, docker-compose.yml, .env.example) sans rien
lancer. Jetons, montants et références FICTIFS.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.incidents import LogNotifier
from pokeshop.settings import ENV_VARIABLES, Settings, SettingsError, load_settings, sha256_hex
from pokeshop.stoploss import hash_owner_token

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=TZ)
ROOT = Path(__file__).resolve().parents[1]
API_TOKEN = "FICTIF-jeton-api-0000000000000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
H = {API_TOKEN_HEADER: API_TOKEN}
HO = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: OWNER_TOKEN}


def reject_float(text: str) -> Any:
    raise AssertionError(f"nombre flottant dans une réponse JSON : {text}")


def body(resp: Any) -> Any:
    return json.loads(resp.content, parse_float=reject_float)


def make_settings(**extra: str) -> Settings:
    env = {"POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN), "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN)}
    env.update(extra)
    return load_settings(env)


@pytest.fixture
def svc() -> Services:
    return Services.build(make_settings(), clock=lambda: NOW, notifier=LogNotifier())


@pytest.fixture
def client(svc: Services) -> TestClient:
    return TestClient(create_app(services=svc))


def state_payload(cash: str = "8000", available: str = "5000", at: datetime = NOW) -> dict[str, Any]:
    return {
        "as_of": at.isoformat(), "stock_budget_chf": "3000", "cash_available_chf": available, "ads_daily_cap_chf": "33",
        "capital_movements": [{"movement_id": "FICTIF_APPORT", "at": (at - timedelta(days=30)).isoformat(),
                               "kind": "CONTRIBUTION", "amount": "8000"}],
        "net_worth": {"as_of": at.isoformat(), "cash_chf": cash},
    }


IDENTITY = {"gtin": "2000000001012", "language": "FR", "extension": "FICTIF_ALPHA", "format": "DISPLAY",
            "content": "36 BOOSTERS", "sealed": True}
LISTING = {
    "product_key": "FICTIF-P1", "identity": IDENTITY, "public_sku": "DSP-FICTIF_ALPHA-FR",
    "description_html": "<p>Display de l'extension Extension Fictive Alpha, en français, neuf et scellé.</p>",
    "images": [{"url": "https://cdn.example.org/fictif.jpg", "alt": "Display face avant", "rights": "OWN_PHOTO"}],
    "stock_status": "stock_local", "content_text": "36 boosters", "content_validated": True,
    "category_rule_validated": True, "fictif": True,
}


# ------------------------------------------------------------------------- santé et accès


def test_health_is_public_and_secret_free(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = body(resp)
    assert data["status"] == "ok" and data["rules_version"] == "v1-2026-10-04" and data["vat_profile"] == "EFFECTIVE"
    assert data["configuration"]["dry_run"] is True and data["autonomy_level"] == 1
    assert data["mandate_active"] is False and data["global_frozen"] is False
    assert "POKESHOP_DRY_RUN=true (simulation)" in data["real_write_blockers"]
    text = resp.text
    assert API_TOKEN not in text and OWNER_TOKEN not in text and sha256_hex(API_TOKEN) not in text


ROUTES = [
    ("post", "/pricing/quote"), ("post", "/pricing/basket"), ("post", "/stock/sellable"),
    ("post", "/stock/reorder-proposal"), ("post", "/imports/fictif_grossiste_a/run"), ("post", "/publish/preview"),
    ("post", "/sync/run"), ("get", "/incidents"), ("post", "/incidents"), ("get", "/autonomy"), ("post", "/autonomy"),
    ("get", "/stoploss/status"), ("post", "/stoploss/state"), ("post", "/stoploss/freeze"), ("post", "/stoploss/rearm"),
    ("post", "/stoploss/baseline"), ("post", "/stock/receive"), ("post", "/pricing/approvals"),
    ("get", "/pricing/approvals"), ("post", "/pricing/approvals/PA-X/revoke"),
    ("post", "/mandate/check"), ("get", "/northstar"), ("post", "/northstar/entries"),
    ("post", "/incidents/INC-X/test"), ("post", "/incidents/INC-X/resume"), ("post", "/incidents/INC-X/close"),
    ("post", "/catalog/items"), ("post", "/catalog/cost-inputs"), ("get", "/catalog"), ("get", "/sync/history"),
    ("post", "/stoploss/state/refresh"), ("post", "/capital/movements"), ("get", "/capital/movements"),
    ("post", "/treasury/bank-balance"), ("post", "/treasury/balance-items"), ("post", "/ads/activity"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_internal_route_requires_the_api_token(client: TestClient, method: str, path: str) -> None:
    missing = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert missing.status_code == 401, path
    wrong = getattr(client, method)(path, headers={API_TOKEN_HEADER: "mauvais"}, **({"json": {}} if method == "post" else {}))
    assert wrong.status_code == 401
    assert "X-Pokeshop-Token" in body(missing)["erreur"]


def test_internal_routes_closed_without_configured_token() -> None:
    closed = TestClient(create_app(services=Services.build(load_settings({}), clock=lambda: NOW)))
    resp = closed.get("/autonomy", headers=H)
    assert resp.status_code == 503 and "POKESHOP_API_TOKEN_SHA256" in body(resp)["erreur"]
    assert closed.get("/health").status_code == 200


def test_float_amounts_are_rejected(client: TestClient) -> None:
    resp = client.post("/pricing/quote", headers=H, content=b'{"cost_chf": 140.5}')
    assert resp.status_code == 422 and "chaîne" in body(resp)["erreur"]
    bad = client.post("/pricing/quote", headers=H, json={"cost_chf": "pas un nombre"})
    assert bad.status_code == 422 and body(bad)["details"]
    garbage = client.post("/pricing/quote", headers=H, content=b"{pas du json")
    assert garbage.status_code == 422


# ------------------------------------------------------------------------------------ prix


def test_pricing_quote_reproduces_bp_reference_cases(client: TestClient) -> None:
    resp = client.post("/pricing/quote", headers=H, json={"cost_chf": "140"})
    data = body(resp)
    assert resp.status_code == 200
    assert data["decision"]["floor_price"] == "208.79" and data["decision"]["recommended_price"] == "209.90"
    assert data["decision"]["status"] == "OK" and data["publishable"] is True
    nr = body(client.post("/pricing/quote", headers=H, json={"cost_chf": "151.34", "profile": "NOT_REGISTERED"}))
    assert nr["decision"]["floor_price"] == "207.28"
    draft = body(client.post("/pricing/quote", headers=H, json={"cost_chf": "140", "unknown_fields": ["vat_rate"]}))
    assert draft["decision"]["status"] == "DRAFT" and draft["labels_fr"]


def test_pricing_basket_counts_fixed_costs_once(client: TestClient) -> None:
    resp = client.post("/pricing/basket", headers=H, json={
        "lines": [{"sku": "FICTIF-A", "qty": 1, "unit_price_ttc": "199.90", "unit_cost": "140"},
                  {"sku": "FICTIF-B", "qty": 2, "unit_price_ttc": "9.90", "unit_cost": "4"}],
        "shipping_charged": "0", "shipping_cost_actual": "3.00",
        "discount": {"kind": "PERCENT", "value": "0.05", "code": "FICTIF5"},
    })
    data = body(resp)
    assert resp.status_code == 200 and data["basket"]["after_sales"] == "1.00" and data["basket"]["acquisition"] == "5.00"
    assert data["allowed"] in (True, False) and isinstance(data["basket"]["contribution_chf"], str)
    blocked = body(client.post("/pricing/basket", headers=H, json={
        "lines": [{"sku": "FICTIF-A", "qty": 1, "unit_price_ttc": "20.00", "unit_cost": "15"}]}))
    assert blocked["allowed"] is False and blocked["basket"]["status"] == "BLOCKED"


# ------------------------------------------------------------------------------------ stock


def test_stock_sellable_computation_and_registry(client: TestClient, svc: Services) -> None:
    computed = body(client.post("/stock/sellable", headers=H, json={"on_hand": 10, "reserved": 3, "damaged": 1, "safety": 2}))
    assert computed == {"sellable": 4, "source": "calcul"}
    svc.stock.receive("DSP-FICTIF_ALPHA-FR", 5, "réception FICTIVE", at=NOW)
    reg = body(client.post("/stock/sellable", headers=H, json={"sku": "DSP-FICTIF_ALPHA-FR"}))
    assert reg["sellable"] == 5 and reg["source"] == "registre"
    assert client.post("/stock/sellable", headers=H, json={}).status_code == 422
    assert client.post("/stock/sellable", headers=H, json={"on_hand": -1}).status_code == 422


def candidate(product_key: str = "FICTIF-P1", extension: str = "FICTIF_ALPHA") -> dict[str, Any]:
    return {
        "product_key": product_key, "extension": extension, "unit_cost_chf": "90.00", "sellable_qty": 0,
        "avg_daily_sales": "0.5", "lead_time_days": 7, "safety_stock": 1,
        "offer": {"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-A-001", "availability_status": "IN_STOCK",
                  "available_qty": 24, "moq": 1, "carton_qty": 1, "source_ts": NOW.isoformat(), "raw_ref": "FICTIF:1"},
    }


def test_reorder_proposal_is_a_proposal_to_validate(client: TestClient) -> None:
    # MOT-24 : sans photo stop-loss, les gels sont inconnus => aucune proposition (fermé par défaut)
    unknown = client.post("/stock/reorder-proposal", headers=H, json={"candidates": [candidate()], "budget_available": "5000"})
    assert unknown.status_code == 409 and "stop-loss" in body(unknown)["erreur"]
    assert client.post("/stoploss/state", headers=H, json=state_payload()).status_code == 200
    resp = client.post("/stock/reorder-proposal", headers=H, json={"candidates": [candidate()], "budget_available": "5000"})
    data = body(resp)
    assert resp.status_code == 200
    proposal = data["proposal"]
    assert proposal["status"] == "PROPOSAL_TO_VALIDATE" and proposal["requires_human_validation"] is True
    assert proposal["lines"] and data["stoploss_known"] is True and data["stock_budget_chf"] == "3000"
    assert data["gate"]["allowed"] is False  # mandat non signé : aucune exécution possible


def test_reorder_proposal_respects_stoploss(client: TestClient) -> None:
    assert client.post("/stoploss/state", headers=H, json=state_payload(available="1000")).status_code == 200
    cash = body(client.post("/stock/reorder-proposal", headers=H, json={"candidates": [candidate()], "budget_available": "5000"}))
    assert cash["proposal"]["lines"] == [] and cash["proposal"]["skipped"][0]["reason"] == "CASH_RESERVE"
    client.post("/stoploss/state", headers=H, json=state_payload(cash="5000"))
    frozen = client.post("/stock/reorder-proposal", headers=H, json={"candidates": [candidate()], "budget_available": "5000"})
    assert frozen.status_code == 423 and "global" in body(frozen)["erreur"]


# ---------------------------------------------------------------------------------- imports


def test_import_route_runs_in_simulation_with_internal_report(client: TestClient) -> None:
    resp = client.post("/imports/fictif_grossiste_a/run", headers=H, json={"source_path": "FICTIF_offres_grossiste_a.csv"})
    data = body(resp)
    assert resp.status_code == 200 and data["dry_run"] is True and data["fictif"] is True
    assert data["status"] == "PARTIAL" and data["accepted"] > 0 and data["quarantined"] > 0
    assert "## Validation humaine requise" in data["report_markdown"]


@pytest.mark.parametrize(
    ("supplier", "path", "status"),
    [
        ("fictif_grossiste_a", "../../config/mandate.v1.yaml", 403),
        ("fictif_grossiste_a", "/etc/passwd", 403),
        ("fictif_grossiste_a", "absent.csv", 404),
        ("Fictif-Majuscule", "FICTIF_offres_grossiste_a.csv", 422),
        ("fournisseur_inconnu", "FICTIF_offres_grossiste_a.csv", 422),
    ],
)
def test_import_route_refuses_paths_and_suppliers(client: TestClient, supplier: str, path: str, status: int) -> None:
    resp = client.post(f"/imports/{supplier}/run", headers=H, json={"source_path": path})
    assert resp.status_code == status, resp.text


# ------------------------------------------------------------------------------- publication


def receive_stock(client: TestClient, qty: int = 6) -> None:
    """Réception physique FICTIVE (le statut public « stock local » exige du stock réel, E2E-12)."""
    resp = client.post("/stock/receive", headers=H, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": qty, "ref": "FICTIF-BL-0001"})
    assert resp.status_code == 200, resp.text


def test_publish_preview_returns_only_the_public_payload(client: TestClient) -> None:
    receive_stock(client)
    resp = client.post("/publish/preview", headers=H, json={"listing": LISTING, "quote": {"cost_chf": "123.45"}})
    data = body(resp)
    assert resp.status_code == 200 and data["dry_run"] is True
    plan = data["plan"]
    assert plan["outcome"] == "SEND_ACTIVE" and plan["product_input"]["title"] == "Display Extension Fictive Alpha – FR"
    assert plan["price_chf"].endswith(".90")
    text = resp.text
    for internal in ("123.45", "contribution", "landed", "floor_price", "marge"):
        assert internal not in text, internal


def test_publish_preview_refuses_leaks(client: TestClient) -> None:
    leaking = dict(LISTING, description_html="<p>Prix d'achat chez fictif_grossiste_a</p>")
    data = body(client.post("/publish/preview", headers=H, json={"listing": leaking, "quote": {"cost_chf": "100"},
                                                                 "sensitive_terms": ["fictif_grossiste_a"]}))
    assert data["plan"]["outcome"] == "NOT_SENT" and data["plan"]["product_input"] is None
    assert "SENSITIVE_FIELD" in data["plan"]["blockers"]
    bad = client.post("/publish/preview", headers=H, json={"listing": dict(LISTING, cost="95")})
    assert bad.status_code == 422


def test_sync_run_is_a_dry_run_by_default(client: TestClient) -> None:
    receive_stock(client)
    resp = client.post("/sync/run", headers=H, json={
        "supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv",
        "catalog": [{"product_id": "FICTIF-P1", "listing": LISTING}],
        "cost_inputs": {"fictif_grossiste_a": {"inbound_freight_alloc": "2.00", "customs_and_fees": "0", "import_vat": "0",
                                               "fx_rate_to_chf": "0.9375", "fx_source": "FICTIF", "fx_date": "2026-10-04"}},
    })
    data = body(resp)
    assert resp.status_code == 200 and data["report"]["dry_run"] is True and data["clean"] is True
    assert [s["step"] for s in data["report"]["steps"]][0] == "1_RECUPERER" and len(data["report"]["steps"]) == 8
    p1 = next(i for i in data["report"]["items"] if i["product_id"] == "FICTIF-P1")
    assert p1["plan_outcome"] == "SEND_ACTIVE" and p1["written"] is False
    assert "SIMULATION" in data["report_markdown"]
    assert client.post("/sync/run", headers=H, json={"supplier": "../x", "source_path": "a"}).status_code == 422


def test_sync_run_real_mode_with_fictif_data_is_refused_safely(client: TestClient, svc: Services) -> None:
    real = {"supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv", "dry_run": False}
    first = client.post("/sync/run", headers=H, json=real)  # aucun import précédent : simulation obligatoire
    assert first.status_code == 409 and "simulation" in body(first)["erreur"]
    client.post("/imports/fictif_grossiste_a/run", headers=H, json={"source_path": "FICTIF_offres_grossiste_a.csv"})
    assert client.post("/sync/run", headers=H, json=real).status_code == 409  # E2E-07 : catalogue requis
    data = body(client.post("/sync/run", headers=H, json=dict(real, catalog=[{"product_id": "FICTIF-P1", "listing": LISTING}])))
    # Écriture réelle refusée dès l'étape 1 : rien n'est évalué, le cycle est VIDE (jamais compté propre).
    assert data["report"]["steps"][0]["status"] == "ECHEC" and data["cycle_status"] == "VIDE" and data["clean"] is False
    assert svc.client.requests_sent == 0


# ---------------------------------------------------------------------------------- incidents


def dry_run_id(client: TestClient) -> str:
    """Cycle de synchronisation en simulation (preuve de test vérifiable par le moteur)."""
    report = body(client.post("/sync/run", headers=H, json={
        "supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv",
        "catalog": [{"product_id": "FICTIF-P1", "listing": LISTING}]}))["report"]
    assert report["dry_run"] is True and report["critical_errors"] == []
    return report["run_id"]


def test_incident_lifecycle_through_the_api(client: TestClient) -> None:
    created = client.post("/incidents", headers=H, json={"code": "INC-01", "product_key": "FICTIF-P1",
                                                         "cause": "prix ×10 sur FICTIF-A-001", "actor": "agent-03"})
    assert created.status_code == 201
    inc = body(created)["incident"]
    assert inc["status"] == "OUVERT" and "Action proposée" in body(created)["notification"]["text"]
    listing = body(client.get("/incidents", headers=H, params={"open_only": "true"}))
    assert listing["quarantined"] == {"FICTIF-P1": [inc["incident_id"]]} and listing["summary"]["OUVERT"] == 1
    early = client.post(f"/incidents/{inc['incident_id']}/resume", headers=H, json={"actor": "agent-12"})
    assert early.status_code == 409
    # SEC-16 : un test « réussi » auto-déclaré sans preuve est refusé ; il doit citer un cycle en simulation.
    free_text = client.post(f"/incidents/{inc['incident_id']}/test", headers=H,
                            json={"test_ref": "dry-run OK", "passed": True, "actor": "agent-12"})
    assert free_text.status_code == 409 and "non vérifiable" in body(free_text)["erreur"]
    tested = client.post(f"/incidents/{inc['incident_id']}/test", headers=H,
                         json={"test_ref": dry_run_id(client), "passed": True, "actor": "agent-12"})
    assert tested.status_code == 200
    resumed = body(client.post(f"/incidents/{inc['incident_id']}/resume", headers=H, json={"actor": "agent-12"}))
    assert resumed["incident"]["status"] == "RESOLU" and resumed["incident"]["resolved_by"] == "agent:agent-12"
    closed = body(client.post(f"/incidents/{inc['incident_id']}/close", headers=H, json={"actor": "agent-01"}))
    assert closed["incident"]["status"] == "CLOS"
    assert body(client.get("/incidents", headers=H, params={"status": "CLOS"}))["incidents"][0]["incident_id"] == inc["incident_id"]


def test_critical_incident_resume_requires_owner_token(client: TestClient, svc: Services) -> None:
    inc = body(client.post("/incidents", headers=H, json={"code": "INC-07", "product_key": "FICTIF-P1",
                                                          "cause": "champ coût publié", "actor": "agent-12"}))["incident"]
    # la propriétaire atteste le test avec son jeton (test_ref libre)
    attested = client.post(f"/incidents/{inc['incident_id']}/test", headers=HO,
                           json={"test_ref": "test_publish relu", "passed": True, "actor": "qa"})
    assert attested.status_code == 200 and body(attested)["incident"]["test_passed"] is True
    agent = client.post(f"/incidents/{inc['incident_id']}/resume", headers=H, json={"actor": "agent-12"})
    assert agent.status_code == 409
    wrong = client.post(f"/incidents/{inc['incident_id']}/resume", headers={**H, OWNER_TOKEN_HEADER: "mauvais-jeton-0000000000"},
                        json={"actor": "agent-12"})
    assert wrong.status_code == 403
    impostor = client.post(f"/incidents/{inc['incident_id']}/resume", headers=H, json={"actor": "Propriétaire"})
    assert impostor.status_code == 403 and svc.audit.events(action="incidents.resume.owner_impersonation_refused")
    owner = client.post(f"/incidents/{inc['incident_id']}/resume", headers=HO, json={"actor": "propriétaire"})
    assert owner.status_code == 200 and body(owner)["incident"]["status"] == "RESOLU"
    unknown = client.post("/incidents/INC-INCONNU/test", headers=H, json={"test_ref": "x1x", "passed": True, "actor": "qa"})
    assert unknown.status_code == 409


# ---------------------------------------------------------------------------------- autonomie


def test_autonomy_routes(client: TestClient) -> None:
    data = body(client.get("/autonomy", headers=H))
    assert data["level"] == 1 and data["required_levels"]["PUBLISH_NEW_PRODUCT"] == 3
    assert "UNPUBLISH_PRODUCT" in data["protective_actions"]
    refused = client.post("/autonomy", headers=H, json={"level": 2, "reason": "ouverture douce FICTIVE", "actor": "agent-01"})
    assert refused.status_code == 403
    same = client.post("/autonomy", headers={**H, OWNER_TOKEN_HEADER: API_TOKEN},
                       json={"level": 2, "reason": "jetons identiques", "actor": "agent-01"})
    assert same.status_code == 403 and "distincts" in body(same)["erreur"]
    raised = client.post("/autonomy", headers=HO, json={"level": 2, "reason": "C14 FICTIF : recette OK", "actor": "propriétaire"})
    assert raised.status_code == 200 and body(raised)["state"]["level"] == 2
    lowered = client.post("/autonomy", headers=H, json={"level": 1, "reason": "gel conservatoire", "actor": "agent-12"})
    assert body(lowered)["state"]["level"] == 1


# ---------------------------------------------------------------------------------- stop-loss


def test_stoploss_status_without_state(client: TestClient) -> None:
    data = body(client.get("/stoploss/status", headers=H))
    assert data["available"] is False and data["global_frozen"] is False and data["error"]


def test_stoploss_state_status_freeze_and_owner_rearm(client: TestClient, svc: Services) -> None:
    ok = body(client.post("/stoploss/state", headers=H, json=state_payload()))
    assert ok["status"]["global_frozen"] is False
    stale = client.post("/stoploss/state", headers=H, json=state_payload(at=NOW - timedelta(days=3)))
    assert stale.status_code == 409
    client.post("/stoploss/state", headers=H, json=state_payload())
    frozen = body(client.post("/stoploss/freeze", headers=H, json={"actor": "agent-12", "reason": "débit inconnu FICTIF"}))
    assert frozen["latch"]["frozen"] is True and frozen["incident_id"] is not None
    assert svc.incidents.get(frozen["incident_id"]).code.value == "INC-09" and svc.autonomy.level == 1
    status = body(client.get("/stoploss/status", headers=H))
    assert status["global_frozen"] is True and status["status"]["global_frozen"] is True
    assert "Gel global" in status["report_markdown"]
    no_owner = client.post("/stoploss/rearm", headers=H, json={"reason": "reprise décidée après examen"})
    assert no_owner.status_code == 403
    wrong = client.post("/stoploss/rearm", headers={**H, OWNER_TOKEN_HEADER: "mauvais-jeton-0000000000"},
                        json={"reason": "reprise décidée après examen"})
    assert wrong.status_code == 403
    short = client.post("/stoploss/rearm", headers=HO, json={"reason": "ok"})
    assert short.status_code == 422
    # Réarmement rebasé : la propriétaire atteste la valeur nette de la photo (SEC-07).
    unattested = client.post("/stoploss/rearm", headers=HO, json={"reason": "valeur nette examinée, reprise (FICTIF)"})
    assert unattested.status_code == 409 and "8 000,00 CHF" in body(unattested)["erreur"] and svc.stoploss_engine.frozen
    reference = status["rearm_reference"]
    assert reference["net_worth_chf"] == "8000" and len(reference["photo_sha256"]) == 64
    rearmed = client.post("/stoploss/rearm", headers=HO, json={"reason": "valeur nette examinée, reprise (FICTIF)",
                                                               "reference_chf": reference["net_worth_chf"],
                                                               "photo_sha256": reference["photo_sha256"]})
    data = body(rearmed)
    assert rearmed.status_code == 200 and data["latch"]["frozen"] is False and data["autonomy_level"] == 1
    assert svc.audit.events(action="stoploss.rearm") and svc.audit.events(action="stoploss.rearm_refused")
    journal = [e.event for e in svc.stoploss_engine.journal]
    assert "MANUAL_FREEZE" in journal and "REARM_REFUSED" in journal and "REARM" in journal


def test_global_loss_state_is_reported(client: TestClient, svc: Services) -> None:
    svc.autonomy.raise_level(2, owner_token=OWNER_TOKEN, reason="C14 FICTIF")
    data = body(client.post("/stoploss/state", headers=H, json=state_payload(cash="6000")))
    assert data["status"]["global_frozen"] is True and data["status"]["autonomy_level"] == 1
    assert svc.stoploss_engine.frozen and svc.autonomy.level == 1
    incident = svc.incidents.get(data["incident_id"])
    assert incident.severity.value == "CRITIQUE" and incident.scope.value == "GLOBAL"


# ----------------------------------------------------------------------------------- mandat


def spend_payload(key: str = "FICTIF-SPEND-API-1") -> dict[str, Any]:
    return {
        "request": {"amount": "40", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                    "payment_method": "PAYPAL", "purpose": "Étuis FICTIFS", "idempotency_key": key,
                    "requested_by": "agent-05", "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF n°1"},
        "treasury": {"as_of": NOW.isoformat(), "cash_available_chf": "5000", "paypal_balance_chf": "500"},
    }


def test_mandate_check_needs_stoploss_state_then_applies_unsigned_mandate(client: TestClient, svc: Services) -> None:
    unavailable = client.post("/mandate/check", headers=H, json=spend_payload())
    assert unavailable.status_code == 503
    client.post("/stoploss/state", headers=H, json=state_payload())
    data = body(client.post("/mandate/check", headers=H, json={**spend_payload(), "record": True}))
    assert data["decision"]["outcome"] == "NEEDS_HUMAN_APPROVAL" and "MANDATE_NOT_SIGNED" in data["decision"]["reasons"]
    assert data["recorded"] is True and svc.spend_ledger.get("FICTIF-SPEND-API-1") is not None
    forbidden = spend_payload("FICTIF-SPEND-API-2")
    forbidden["request"]["category"] = "FINANCING"
    assert body(client.post("/mandate/check", headers=H, json=forbidden))["decision"]["outcome"] == "REJECTED"


# ----------------------------------------------------------------------------- étoile polaire


def test_northstar_report(client: TestClient) -> None:
    empty = body(client.get("/northstar", headers=H))
    assert empty["cumulative"] == "0.00" and empty["rows"] == []
    entries = [
        {"entry_id": "FICTIF-1", "at": NOW.isoformat(), "post": "NET_SALES", "amount": "184.92", "order_id": "FICTIF-O1"},
        {"entry_id": "FICTIF-3", "at": NOW.isoformat(), "post": "PAYMENT", "amount": "5.30", "order_id": "FICTIF-O1"},
    ]
    added = body(client.post("/northstar/entries", headers=H, json={"entries": entries}))
    assert added == {"added": 2, "received": 2}
    again = body(client.post("/northstar/entries", headers=H, json={"entries": entries}))
    assert again["added"] == 0
    # coût historique : registre interne uniquement (réception au coût, vente au CMP calculé par le moteur)
    receipt = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-LOT-1",
               "qty": 2, "unit_cost": "140.00"}
    assert body(client.post("/costs/movements", headers=H, json=receipt))["northstar_added"] == 0
    sale = {"kind": "ISSUE", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-O1", "qty": 1}
    assert body(client.post("/costs/movements", headers=H, json=sale))["northstar_added"] == 1
    report = body(client.get("/northstar", headers=H))
    assert report["cumulative"] == "39.62" and report["rows"][0]["orders"] == 1 and "Contribution nette" in report["markdown"]
    bad = client.get("/northstar", headers=H, params={"start": "2026-12-01", "end": "2026-11-01"})
    assert bad.status_code == 422


# ------------------------------------------------------------------------- fichiers de déploiement


def parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_env_example_documents_every_setting_without_secret_values() -> None:
    env = parse_env_example()
    expected = {names[0] for names in ENV_VARIABLES.values()} | {
        "POSTGRES_PASSWORD", "POKESHOP_DB_PASSWORD", "N8N_ENCRYPTION_KEY", "N8N_WEBHOOK_URL", "N8N_IMAGE"}
    assert set(env) == expected
    for secret in ("POKESHOP_SHOPIFY_ADMIN_TOKEN", "POKESHOP_DATABASE_URL", "POKESHOP_API_TOKEN_SHA256",
                   "POKESHOP_OWNER_TOKEN_SHA256", "POKESHOP_MANDATE_FINGERPRINT", "POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY",
                   "POKESHOP_DB_PASSWORD"):
        assert env[secret] == "", secret
    assert env["POKESHOP_DRY_RUN"] == "true" and env["POKESHOP_SHOPIFY_TEST_STORE"] == "false"
    settings = load_settings({k: v for k, v in env.items() if k.startswith("POKESHOP_")})
    assert settings.dry_run and not settings.shopify_test_store and settings.shopify_api_version == "2026-10"
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "Validation humaine requise" in text
    assert not re.search(r"shpat_[A-Za-z0-9]{8,}|[0-9a-f]{64}", text)


def test_compose_file_is_ready_but_local_only() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {"db", "db-migrate", "db-backup", "api", "n8n"}
    assert services["db"]["image"] == "postgres:16"
    assert services["db-migrate"]["entrypoint"] == ["bash", "-c", "bash /db/apply.sh none && bash /db/engine_login.sh"]
    for name in ("db", "api", "n8n"):
        assert all(str(p).startswith("127.0.0.1:") for p in services[name]["ports"]), name
    assert services["api"]["build"] == "."
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "${POSTGRES_PASSWORD:?" in text and "${N8N_ENCRYPTION_KEY:?" in text
    assert services["api"]["environment"]["POKESHOP_DRY_RUN"] == "${POKESHOP_DRY_RUN:-true}"  # simulation par défaut
    assert "env_file" not in services["api"]  # E2E-18 : jamais tout le fichier .env dans le conteneur


def test_dockerfile_runs_the_api_factory_in_simulation() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim" in text and "POKESHOP_DRY_RUN=true" in text
    assert '"pokeshop.api:create_app", "--factory"' in text and "USER pokeshop" in text
    assert "HEALTHCHECK" in text and "/health" in text
    assert not re.search(r"(?i)(token|password)\s*=\s*\S+", text.replace("POKESHOP_DRY_RUN=true", ""))


def test_settings_validation_messages_name_the_variable() -> None:
    with pytest.raises(SettingsError, match="POKESHOP_SHOPIFY_SHOP_DOMAIN"):
        load_settings({"POKESHOP_SHOPIFY_SHOP_DOMAIN": "boutique.example.com"})
    with pytest.raises(SettingsError, match="POKESHOP_API_TOKEN_SHA256"):
        load_settings({"POKESHOP_API_TOKEN_SHA256": "pas-un-sha"})
    same = sha256_hex(API_TOKEN)
    with pytest.raises(SettingsError, match="distincts"):
        load_settings({"POKESHOP_API_TOKEN_SHA256": same, "POKESHOP_OWNER_TOKEN_SHA256": same})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_SHOPIFY_LOCATION_ID": "42"})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_SHOPIFY_API_VERSION": "2026-05"})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_N8N_WEBHOOK_URL": "ftp://n8n"})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_TIMEZONE": "Mars/Olympus"})
    with pytest.raises(SettingsError):
        load_settings({"POKESHOP_SHOPIFY_BACKOFF_BASE_MS": "5000", "POKESHOP_SHOPIFY_BACKOFF_MAX_MS": "100"})
    alias = load_settings({"SHOPIFY_ADMIN_TOKEN": "shpat_FICTIF", "POKESHOP_SHOPIFY_SHOP_DOMAIN": "fictif.myshopify.com"})
    assert alias.shopify_configured and "shpat_FICTIF" not in repr(alias)
    full = make_settings(POKESHOP_DRY_RUN="false", POKESHOP_SHOPIFY_SHOP_DOMAIN="fictif.myshopify.com",
                         POKESHOP_SHOPIFY_ADMIN_TOKEN="shpat_FICTIF", POKESHOP_SHOPIFY_LOCATION_ID="gid://shopify/Location/1",
                         POKESHOP_MANDATE_FINGERPRINT="a" * 64, POKESHOP_STOPLOSS_FINGERPRINT="b" * 64,
                         POKESHOP_RULES_FINGERPRINT="c" * 64)
    assert full.real_write_blockers() == [] and full.real_writes_enabled
    unsigned = make_settings(POKESHOP_DRY_RUN="false")
    assert any("POKESHOP_MANDATE_FINGERPRINT" in b for b in unsigned.real_write_blockers())
    assert any("POKESHOP_STOPLOSS_FINGERPRINT" in b for b in unsigned.real_write_blockers())
    assert load_settings({"POKESHOP_DRY_RUN": " "}).dry_run is True  # valeur vide = défaut (simulation)
