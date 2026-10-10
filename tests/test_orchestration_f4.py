"""Lot F4 (orchestration) : routes du moteur appelées par n8n, vérifiées de bout en bout sur l'API.

* E2E-07 : ``/sync/run`` sans catalogue => 409 ; catalogue validé et frais **persistés** ; un cycle sans
  offre évaluée est VIDE (jamais « propre ») ; compteur de cycles propres persistant (``/sync/history``).
* E2E-08 : la photo du stop-loss est construite par le moteur à partir de ses registres
  (``/stoploss/state/refresh``) ; apports réservés à la propriétaire ; sources manquantes ou périmées
  => 409, jamais une photo inventée.
* E2E-10 : clé canonique par workflow ; un incident ouvert sur le workflow de dépense (ou une
  suspension globale) suspend ``/mandate/check`` (423).
* E2E-13 : un incident n'est « livré » que s'il est parti vers n8n ; ``/health`` dit si les alertes
  temps réel sont actives.
Jetons, montants et références FICTIFS.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal as D
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import jetons_roles as JR
from fastapi.testclient import TestClient

from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, WORKFLOW_KEYS, WORKFLOW_MANDATE, Services, create_app
from pokeshop.catalogue_sync import SyncRunLog, SyncRunSummary
from pokeshop.incidents import LogNotifier
from pokeshop.settings import load_settings, sha256_hex
from pokeshop.stoploss import hash_owner_token
from pokeshop.sync import WORKFLOW_SUPPLIER_TO_SHOP

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=TZ)
API_TOKEN = "FICTIF-jeton-api-0000000000000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
CONNECTOR_TOKEN = JR.ROLE_TOKENS["connecteur-tresorerie"]
PHOTO_TOKEN = JR.ROLE_TOKENS["n8n-07-stoploss"]
H = {API_TOKEN_HEADER: API_TOKEN}
HO = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: OWNER_TOKEN}
HCONN = JR.HTRES
HPHOTO = JR.HPHOTO
HF, HOPS, HCAT, HSYNC, HINC, HMANDAT = JR.HF, JR.HOPS, JR.HCAT, JR.HSYNC, JR.HINC, JR.HMANDAT
IDENTITY = {"gtin": "2000000001012", "language": "FR", "extension": "FICTIF_ALPHA", "format": "DISPLAY",
            "content": "36 BOOSTERS", "sealed": True}
LISTING = {
    "product_key": "FICTIF-P1", "identity": IDENTITY, "public_sku": "DSP-FICTIF_ALPHA-FR",
    "description_html": "<p>Display de l'extension Extension Fictive Alpha, en français, neuf et scellé.</p>",
    "images": [{"url": "https://cdn.example.org/fictif.jpg", "alt": "Display face avant", "rights": "OWN_PHOTO"}],
    "stock_status": "stock_local", "content_text": "36 boosters", "fictif": True,
}
N8N_SYNC_BODY = {"supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv", "dry_run": True}
"""Corps exact envoyé par le nœud « Cycle fournisseur vers site (dry-run) » du workflow 01."""


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def boot(tmp_path: Path, clock: Clock | None = None, **env: str) -> tuple[TestClient, Services, Clock]:
    clock = clock or Clock(NOW)
    settings = load_settings({
        "POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN),
        "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN),
        "POKESHOP_AGENT_TOKENS_SHA256": JR.agent_tokens_env(),
        "POKESHOP_STATE_DIR": str(tmp_path / "etat"),
        **env,
    })
    svc = Services.build(settings, clock=clock, notifier=LogNotifier())
    return TestClient(create_app(services=svc)), svc, clock


# =============================================================================== E2E-07


def register_catalog(client: TestClient, *, fx: bool = True) -> None:
    assert client.post("/catalog/items", headers=HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": LISTING}]}).status_code == 200
    costs = {"supplier_id": "fictif_grossiste_a", "currency": "EUR", "inbound_freight_alloc": "2.00",
             "customs_and_fees": "0", "import_vat": "0", "source": "devis transporteur FICTIF"}
    assert client.post("/catalog/cost-inputs", headers=HF, json=costs).status_code == 200
    if fx:
        rate = {"currency": "EUR", "rate_to_chf": "0.9375", "rate_date": "2026-10-04", "source": "BNS FICTIF 11:00"}
        assert client.post("/fx/rates", headers=HO, json=rate).status_code == 200


def test_e2e07_n8n_body_without_catalog_is_refused_not_counted_clean(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    resp = client.post("/sync/run", headers=HSYNC, json=N8N_SYNC_BODY)
    assert resp.status_code == 409 and "catalogue requis" in body(resp)["erreur"]
    assert svc.sync_runs.runs() == () and body(client.get("/sync/history", headers=H))["consecutive_clean_runs"] == 0


def test_e2e07_registry_catalog_and_owner_fx_make_a_clean_counted_cycle(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    register_catalog(client)
    data = body(client.post("/sync/run", headers=HSYNC, json=N8N_SYNC_BODY))
    assert data["catalog_source"] == "registre" and data["cycle_status"] == "PROPRE" and data["clean"] is True
    # Revue E2E-07 (2ᵉ passe) : un cycle PROPRE sur données FICTIVES ne compte jamais pour la recette.
    assert data["offers_costed"] >= 1 and data["consecutive_clean_runs"] == 0
    assert data["counted_for_acceptance"] is False and data["acceptance_exclusion"] == "données FICTIVES"
    p1 = next(i for i in data["report"]["items"] if i["product_id"] == "FICTIF-P1")
    assert p1["match_status"] == "MATCHED" and p1["decision_status"] is not None
    # Redémarrage : catalogue, frais et compteur relus depuis les journaux d'état.
    client2, svc2, _ = boot(tmp_path)
    assert [e.product_id for e in svc2.catalog.entries()] == ["FICTIF-P1"] and svc2.catalog.costs("fictif_grossiste_a")
    history = body(client2.get("/sync/history", headers=H))
    assert history["consecutive_clean_runs"] == 0 and history["target"] == 20 and not history["criterion_met"]
    assert [r["status"] for r in history["runs"]] == ["PROPRE"] and history["runs"][0]["fictif"] is True
    assert history["runs"][0]["acceptance_exclusion"] == "données FICTIVES" and "FICTIF" in history["definition"]
    again = body(client2.post("/sync/run", headers=HSYNC, json=N8N_SYNC_BODY))
    assert again["clean"] is True and again["consecutive_clean_runs"] == 0


def test_e2e07_cycle_without_evaluated_offer_is_empty_and_never_counted(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    register_catalog(client, fx=False)  # aucun taux de la propriétaire : coût rendu incomplet (EUR)
    data = body(client.post("/sync/run", headers=HSYNC, json=N8N_SYNC_BODY))
    assert data["cycle_status"] == "VIDE" and data["clean"] is False and data["offers_costed"] == 0
    unmatched = dict(LISTING, product_key="FICTIF-AUTRE", identity=dict(IDENTITY, gtin="2000000009998"),
                     public_sku="DSP-FICTIF_ALPHA-FR")  # clé produit unique (revue R4, R3-NEW-01)
    other = body(client.post("/sync/run", headers=HSYNC, json=dict(N8N_SYNC_BODY, catalog=[{"product_id": "FICTIF-AUTRE",
                                                                                         "listing": unmatched}])))
    assert other["cycle_status"] == "VIDE" and other["clean"] is False
    incomplete = body(client.post("/sync/run", headers=HSYNC, json=dict(N8N_SYNC_BODY,
                                                                    source_path="FICTIF_offres_grossiste_a_incomplet.csv")))
    assert incomplete["clean"] is False
    assert body(client.get("/sync/history", headers=H))["consecutive_clean_runs"] == 0


def test_e2e07_cost_inputs_never_carry_a_self_declared_fx_rate(tmp_path: Path) -> None:
    client, _, _ = boot(tmp_path)
    bad = {"supplier_id": "fictif_grossiste_a", "currency": "EUR", "source": "devis FICTIF", "fx_rate_to_chf": "0.50"}
    assert client.post("/catalog/cost-inputs", headers=H, json=bad).status_code == 403  # jeton commun : jamais
    assert client.post("/catalog/cost-inputs", headers=HF, json=bad).status_code == 422


def test_e2e07_streak_counts_clean_runs_ignores_empty_and_resets_on_anomaly() -> None:
    log = SyncRunLog()

    def run(i: int, status: str) -> SyncRunSummary:
        return SyncRunSummary(run_id=f"r{i}", supplier_id="s", dry_run=True, started_at=NOW, finished_at=NOW, status=status,
                              offers_costed=1 if status == "PROPRE" else 0, items=1, catalog_source="registre",
                              recorded_by="api", critical_errors=("x",) if status == "ANOMALIES" else (),
                              fictif=False, source_sha256=f"{i:064x}", source_ts=NOW - timedelta(hours=10 - i))  # fmt: skip

    for i, status in enumerate(["PROPRE", "ANOMALIES", "PROPRE", "VIDE", "PROPRE"]):
        log.record(run(i, status))
    assert log.consecutive_clean_runs() == 2


# =============================================================================== E2E-08


def engine_offer(svc: Services, unit_cost: str, product_key: str = "FICTIF-P1", fees_by: str | None = "propriétaire") -> None:
    """Coût rendu d'une offre évaluée par le moteur (comme après un ``/sync/run``) : référence du coût de réception.

    Revue R5 (R2-NEW-01) : référence admise seulement si les frais du registre utilisés ont été posés par la
    propriétaire (ou un rôle qui ne valorise pas les réceptions) — ``fees_by`` = leur auteur.
    """
    from pokeshop.models import ReplacementCost

    svc.sync.replacement_costs.update(ReplacementCost(product_key=product_key, supplier_id="fictif_grossiste_a",
                                                      unit_cost=D(unit_cost), source_ts=NOW - timedelta(days=2),
                                                      offer_ref="FICTIF-OFFRE-1", fees_recorded_by=fees_by))  # fmt: skip


def feed_registers(client: TestClient, svc: Services) -> None:
    movement = {"movement_id": "FICTIF-APPORT-1", "at": (NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
                "amount": "4200", "ref": "virement FICTIF"}
    assert client.post("/capital/movements", headers=HO, json=movement).status_code == 201
    paypal = {"as_of": (NOW - timedelta(minutes=10)).isoformat(), "balance_chf": "1500", "source": "API PayPal FICTIVE"}
    bank = {"as_of": (NOW - timedelta(minutes=20)).isoformat(), "balance_chf": "2000.00", "source": "relevé bancaire FICTIF"}
    assert client.post("/treasury/paypal-balance", headers=HCONN, json=paypal).status_code == 200
    assert client.post("/treasury/bank-balance", headers=HCONN, json=bank).status_code == 200
    balances = {"as_of": (NOW - timedelta(minutes=15)).isoformat(), "preorders_collected_chf": "0", "debts": [],
                "receivables": [], "source": "agent finance FICTIF : aucune précommande ni facture en attente"}
    assert client.post("/treasury/balance-items", headers=HCONN, json=balances).status_code == 200
    seed_stock(client, svc)
    svc.price_history.publish("FICTIF-P1", D("154.90"), NOW - timedelta(days=1), "engine", validated=True)


ORDER_LINES = [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]
"""Lignes d'une commande FICTIVE d'un display (revue R4, R3-NEW-05 : lignes obligatoires)."""


def seed_stock(client: TestClient, svc: Services, *, qty: int = 6, unit_cost: str = "101.2345") -> None:
    """Fiche FICTIF-P1, réception physique (operations-sav) et coût de réception adossé (finance-pricing)."""
    assert client.post("/catalog/items", headers=HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": LISTING}]}).status_code == 200
    # Revue R3 : coût de réception adossé à la réception physique (operations-sav), déposé par finance-pricing.
    assert client.post("/stock/receive", headers=HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": qty,
                                                             "ref": "FICTIF-BL-1"}).status_code == 200
    # Revue R4 (R2-NEW-01) : coût de réception borné par une référence du moteur (coût rendu de l'offre évaluée).
    engine_offer(svc, unit_cost)
    receipt = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": (NOW - timedelta(days=2)).isoformat(), "ref": "FICTIF-LOT-1",
               "qty": qty, "unit_cost": unit_cost, "stock_ref": "FICTIF-BL-1", "invoice_ref": "FICTIF-FACT-1"}
    assert client.post("/costs/movements", headers=HCONN, json=receipt).status_code == 403  # connecteur : pas son rôle
    assert client.post("/costs/movements", headers=HF, json=receipt).status_code == 200


def test_e2e08_refresh_without_registers_lists_what_is_missing(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    resp = client.post("/stoploss/state/refresh", headers=HPHOTO)
    assert resp.status_code == 409 and svc.stoploss_state is None
    missing = " ".join(body(resp)["manquantes"])
    assert "solde PayPal" in missing and "solde bancaire" in missing and "apport de capital" in missing
    assert "dettes et créances absente" in missing  # jamais supposées nulles
    assert svc.audit.events(action="stoploss.refresh_refused")
    assert body(client.get("/stoploss/status", headers=H))["available"] is False


def test_e2e08_capital_movements_are_owner_only_and_append_only(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    movement = {"movement_id": "FICTIF-APPORT-1", "at": NOW.isoformat(), "kind": "CONTRIBUTION", "amount": "4200"}
    assert client.post("/capital/movements", headers=H, json=movement).status_code == 403
    bad_owner = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: "FICTIF-mauvais-jeton-proprietaire-01"}
    assert client.post("/capital/movements", headers=bad_owner, json=movement).status_code == 403
    assert svc.audit.events(action="capital.movement.owner_token_refused") and svc.capital.movements() == ()
    assert client.post("/capital/movements", headers=HO, json=movement).status_code == 201
    assert client.post("/capital/movements", headers=HO, json=movement).status_code == 200  # rejeu identique
    rewritten = client.post("/capital/movements", headers=HO, json=dict(movement, amount="99"))
    assert rewritten.status_code == 409 and len(svc.capital.movements()) == 1
    future = client.post("/capital/movements", headers=HO,
                         json=dict(movement, movement_id="FICTIF-APPORT-2", at=(NOW + timedelta(days=1)).isoformat()))
    assert future.status_code == 409


def test_e2e08_photo_is_built_from_engine_registers_and_evaluated(tmp_path: Path) -> None:
    client, svc, clock = boot(tmp_path)
    feed_registers(client, svc)
    resp = client.post("/stoploss/state/refresh", headers=HPHOTO)
    assert resp.status_code == 200, resp.text
    data = body(resp)
    assert data["origin"] == "registres du moteur" and data["cash_available_chf"] == "3500.00"
    assert data["sources"]["as_of"].startswith((NOW - timedelta(minutes=20)).isoformat()[:16])  # plus ancien relevé
    state = svc.stoploss_state
    assert state is not None and state.as_of == NOW - timedelta(minutes=20)
    assert [(m.movement_id, m.amount) for m in state.capital_movements] == [("FICTIF-APPORT-1", D("4200"))]
    assert [(e.extension, e.stock_value_at_cost) for e in state.extensions] == [("FICTIF_ALPHA", D("607.41"))]
    assert [line.product_key for line in state.net_worth.stock] == ["FICTIF-P1"]
    margin = state.products[0]
    assert margin.product_key == "FICTIF-P1" and margin.contribution_chf > 0
    assert state.stock_budget_chf == svc.rules.stock.stock_budget_chf and state.ads_daily_cap_chf is None
    status = body(client.get("/stoploss/status", headers=H))
    assert status["available"] is True and status["photo_posted_by"] == "n8n-07-stoploss"
    # Relevé plus ancien que celui en vigueur : refusé (aucun retour en arrière).
    older = {"as_of": (NOW - timedelta(hours=2)).isoformat(), "balance_chf": "9000", "source": "relevé FICTIF"}
    assert client.post("/treasury/bank-balance", headers=HCONN, json=older).status_code == 409
    # Relevés périmés (> 24 h) : refus, la photo précédente reste et se périme seule.
    clock.now = NOW + timedelta(hours=25)
    stale = client.post("/stoploss/state/refresh", headers=HPHOTO)
    assert stale.status_code == 409 and "périmé" in body(stale)["erreur"] and body(stale)["previous_photo_kept"] is True
    # Redémarrage : les apports sont relus ; les soldes (mémoire) doivent être relevés de nouveau.
    client2, svc2, _ = boot(tmp_path, Clock(NOW))
    assert [m.movement_id for m in svc2.capital.movements()] == ["FICTIF-APPORT-1"]
    again = client2.post("/stoploss/state/refresh", headers=HPHOTO)
    assert again.status_code == 409 and "non relevé" in body(again)["erreur"]


def test_e2e08_withdrawal_after_reading_is_not_in_the_photo_and_mandate_sees_bank_poster(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    feed_registers(client, svc)
    late = {"movement_id": "FICTIF-RETRAIT-1", "at": (NOW - timedelta(minutes=5)).isoformat(), "kind": "WITHDRAWAL",
            "amount": "100"}
    assert client.post("/capital/movements", headers=HO, json=late).status_code == 201
    assert client.post("/stoploss/state/refresh", headers=HPHOTO).status_code == 200
    # Mouvement postérieur au plus ancien relevé de cash : il entrera dans la photo suivante, avec le cash qui le reflète.
    assert [m.movement_id for m in svc.stoploss_state.capital_movements] == ["FICTIF-APPORT-1"]


# =============================================================================== E2E-10

SPEND = {"request": {"amount": "150", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                     "payment_method": "PAYPAL", "purpose": "Cartons FICTIFS", "idempotency_key": "FICTIF-PKG-0001",
                     "requested_by": "operations-sav", "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF"}}


def test_e2e10_canonical_workflow_keys_match_the_engine() -> None:
    assert WORKFLOW_KEYS["01"] == WORKFLOW_SUPPLIER_TO_SHOP == "fournisseur-site"
    assert WORKFLOW_KEYS["08"] == WORKFLOW_MANDATE
    assert len(set(WORKFLOW_KEYS.values())) == len(WORKFLOW_KEYS)


@pytest.mark.parametrize("scope", ["WORKFLOW", "GLOBAL"])
def test_e2e10_open_incident_suspends_the_spending_check(tmp_path: Path, scope: str) -> None:
    client, svc, _ = boot(tmp_path)
    before = client.post("/mandate/check", headers=HOPS, json=SPEND)
    assert before.status_code != 423
    incident = {"cause": "Exécution 42 en échec au nœud Contrôle du mandat", "kind": "WORKFLOW_EN_ECHEC", "severity": "MAJEUR",
                "scope": scope, "workflow": WORKFLOW_MANDATE if scope == "WORKFLOW" else None,
                "proposed_action": "Corriger puis relancer", "actor": "n8n:04-incident", "simulation": False}
    assert client.post("/incidents", headers=HINC, json=incident).status_code == 201
    resp = client.post("/mandate/check", headers=HOPS, json=SPEND)
    assert resp.status_code == 423 and body(resp)["outcome"] == "REJECTED"
    assert svc.audit.events(action="mandate.check_suspended")
    # Un incident ouvert sur un AUTRE workflow ne suspend pas les dépenses.
    client2, _, _ = boot(tmp_path / "autre")
    other = dict(incident, scope="WORKFLOW", workflow=WORKFLOW_SUPPLIER_TO_SHOP)
    assert client2.post("/incidents", headers=HINC, json=other).status_code == 201
    assert client2.post("/mandate/check", headers=HOPS, json=SPEND).status_code != 423


# =============================================================================== E2E-13


NOTIFY_SECRET = "fictif-secret-notification-moteur-0123456789"  # FICTIF ; n8n (04) vérifie X-Pokeshop-Notify


@pytest.fixture
def webhook() -> Iterator[tuple[str, list[bytes]]]:
    """Faux workflow 04 : comme le credential n8n, refuse (403) tout envoi sans le secret du moteur (revue R6)."""
    hits: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - API http.server
            data = self.rfile.read(int(self.headers.get("content-length", 0)))
            if self.headers.get("X-Pokeshop-Notify") != NOTIFY_SECRET:
                self.send_response(403)
                self.end_headers()
                return
            hits.append(data)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://localhost:{server.server_port}/webhook/pokeshop-incidents", hits
    finally:
        server.shutdown()


@pytest.mark.parametrize("dry_run", ["true", "false"])
def test_e2e13_critical_incident_is_delivered_only_when_really_sent(tmp_path: Path, webhook: tuple[str, list[bytes]],
                                                                     dry_run: str) -> None:
    url, hits = webhook
    client, svc, _ = boot(tmp_path, POKESHOP_N8N_WEBHOOK_URL=url, POKESHOP_NOTIFY_DRY_RUN=dry_run,
                          POKESHOP_N8N_WEBHOOK_SECRET=NOTIFY_SECRET)  # fmt: skip
    notifications = body(client.get("/health"))["notifications"]
    assert notifications == {"webhook_configured": True, "webhook_dry_run": dry_run == "true",
                             "webhook_secret_configured": True, "real_time_alerts": dry_run == "false",
                             "last_delivery": None}  # fmt: skip
    frozen = client.post("/stoploss/freeze", headers=HPHOTO, json={"actor": "n8n:07-stoploss-watch", "reason": "Gel global FICTIF"})
    assert frozen.status_code == 200
    receipt = svc.incidents.receipts[-1]
    event = svc.audit.events(action="incident.notify")[-1].payload
    if dry_run == "true":
        assert hits == [] and receipt.delivered is False and receipt.dry_run is True and event["delivered"] is False
        assert "simulé" in event["detail"]
    else:
        assert len(hits) == 1 and json.loads(hits[0])["sop"] == "S1"
        assert receipt.delivered is True and event["delivered"] is True
    last = body(client.get("/health"))["notifications"]["last_delivery"]
    assert last["delivered"] is (dry_run == "false") and last["dry_run"] is (dry_run == "true")


@pytest.mark.parametrize("secret", [None, "fictif-autre-secret-apres-rotation-0123456789"])
def test_r6_doc07_alert_without_the_shared_secret_is_never_delivered_and_is_reported(
    tmp_path: Path, webhook: tuple[str, list[bytes]], secret: str | None
) -> None:
    """Revue R6 (R5C-DOC-07) : secret absent => rien n'est envoyé ; secret différent (rotation d'un seul côté) =>
    n8n refuse (403) ; dans les deux cas l'incident est « non livré », /health et le digest le signalent."""
    url, hits = webhook
    env = {"POKESHOP_N8N_WEBHOOK_SECRET": secret} if secret else {}
    client, svc, _ = boot(tmp_path, POKESHOP_N8N_WEBHOOK_URL=url, POKESHOP_NOTIFY_DRY_RUN="false", **env)
    notifications = body(client.get("/health"))["notifications"]
    assert notifications["real_time_alerts"] is (secret is not None)
    assert notifications["webhook_secret_configured"] is (secret is not None)
    frozen = client.post("/stoploss/freeze", headers=HPHOTO, json={"actor": "n8n:07-stoploss-watch", "reason": "Gel global FICTIF"})
    assert frozen.status_code == 200 and hits == []
    receipt = svc.incidents.receipts[-1]
    assert receipt.delivered is False and receipt.dry_run is False
    assert ("POKESHOP_N8N_WEBHOOK_SECRET" if secret is None else "HTTP 403") in receipt.detail
    last = body(client.get("/health"))["notifications"]["last_delivery"]
    assert last["delivered"] is False and last["dry_run"] is False
    assert svc.audit.events(action="incident.notify")[-1].payload["delivered"] is False


def test_e2e13_health_without_webhook_reports_no_real_time_alerts(tmp_path: Path) -> None:
    client, _, _ = boot(tmp_path)
    assert body(client.get("/health"))["notifications"] == {
        "webhook_configured": False, "webhook_dry_run": True, "webhook_secret_configured": False,
        "real_time_alerts": False, "last_delivery": None}  # fmt: skip


def test_e2e08_declared_debts_reduce_cash_and_net_worth_and_are_never_assumed_zero(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    feed_registers(client, svc)
    statement = {"as_of": (NOW - timedelta(minutes=5)).isoformat(), "preorders_collected_chf": "500",
                 "debts": [{"label": "Facture FICTIVE non payée", "amount": "300"}],
                 "receivables": [{"label": "Versement PSP en transit", "amount": "100"}], "source": "agent finance FICTIF"}
    # Revue R4 (R3-NEW-02) : une créance n'est relevée que par la propriétaire (un rôle : 403).
    assert client.post("/treasury/balance-items", headers=HCONN, json=statement).status_code == 403
    assert client.post("/treasury/balance-items", headers=HO, json=statement).status_code == 200
    data = body(client.post("/stoploss/state/refresh", headers=HPHOTO))
    assert data["cash_available_chf"] == "3000.00"  # 1500 + 2000 − 500 de précommandes encaissées non livrées
    worth = svc.stoploss_state.net_worth
    assert sum(d.amount for d in worth.debts) == D("800") and sum(r.amount for r in worth.receivables) == D("100")
    older = dict(statement, as_of=(NOW - timedelta(hours=1)).isoformat(), receivables=[])
    assert client.post("/treasury/balance-items", headers=HCONN, json=older).status_code == 409
    # Redémarrage : revue R5 (R3-NEW-02 partiel) — dettes et créances relues du journal (plancher en vigueur) ; les
    # soldes (mémoire) doivent être relevés de nouveau, sans eux aucune photo.
    client2, svc2, _ = boot(tmp_path)
    assert client2.post("/stoploss/state/refresh", headers=HPHOTO).status_code == 409
    client2.post("/treasury/paypal-balance", headers=HCONN,
                 json={"as_of": NOW.isoformat(), "balance_chf": "1500", "source": "API PayPal FICTIVE"})
    client2.post("/treasury/bank-balance", headers=HCONN,
                 json={"as_of": NOW.isoformat(), "balance_chf": "2000", "source": "relevé FICTIF"})
    again = client2.post("/stoploss/state/refresh", headers=HPHOTO)
    assert again.status_code == 200
    worth2 = svc2.stoploss_state.net_worth
    assert sum(d.amount for d in worth2.debts) == D("800") and sum(r.amount for r in worth2.receivables) == D("100")
