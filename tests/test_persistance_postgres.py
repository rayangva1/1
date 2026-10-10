"""Persistance en base (migration 004) : journaux d'état, incidents sans écrasement, hausse d'autonomie.

Base jetable (toutes les migrations), comptes de connexion **membres de pokeshop_engine** (compte de
production documenté, docker-compose.yml) et de ``pokeshop_owner``. Ignoré si PostgreSQL ou psycopg
est absent. Jetons et données FICTIFS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import jetons_roles as JR
from pokeshop.models import ReplacementCost
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.audit import PostgresStateJournal, StateStoreError
from pokeshop.autonomy import AutonomyRefusedError, AutonomyState, PostgresAutonomyStore
from pokeshop.incidents import IncidentError, LogNotifier, PostgresIncidentSink
from pokeshop.settings import load_settings, sha256_hex
from pokeshop.stoploss import hash_owner_token

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=TZ)
API_TOKEN = "FICTIF-jeton-api-0000000000000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
H = {API_TOKEN_HEADER: API_TOKEN}
HO = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: OWNER_TOKEN}
FINANCE_TOKEN = JR.ROLE_TOKENS["finance-pricing"]
HF, HPHOTO, HORDERS, HDATA, HQA = JR.HF, JR.HPHOTO, JR.HORDERS, JR.HDATA, JR.HQA  # jetons nommés par rôle

Factory = Callable[[], Any]


def _psql(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
    prefix = ["runuser", "-u", "postgres", "--"] if hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser") else []
    return subprocess.run([*prefix, shutil.which("psql") or "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db, "-f", "-"],
                          input=sql, capture_output=True, text=True, timeout=120, check=False)


@pytest.fixture
def pg(tmp_path: Path) -> Iterator[dict[str, Factory]]:
    """Base neuve par test : comptes ``engine`` (membre de pokeshop_engine) et ``owner`` (pokeshop_owner)."""
    psycopg = pytest.importorskip("psycopg", reason="pilote psycopg absent : persistance Postgres non testée")
    if shutil.which("psql") is None or _psql("SELECT 1;").returncode != 0:
        pytest.skip("PostgreSQL injoignable")
    suffix = uuid.uuid4().hex[:8]
    name, password = f"pokeshop_f1_{os.getpid()}_{suffix}", uuid.uuid4().hex
    roles = {"engine": f"pk_f1_engine_{suffix}", "owner": f"pk_f1_owner_{suffix}"}
    assert _psql(f'CREATE DATABASE "{name}";').returncode == 0
    try:
        for path in MIGRATIONS:
            out = _psql(path.read_text(encoding="utf-8"), name)
            assert out.returncode == 0, out.stderr
        out = _psql(f"CREATE ROLE {roles['engine']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_engine;\n"
                    f"CREATE ROLE {roles['owner']} LOGIN PASSWORD '{password}' IN ROLE pokeshop_owner;")
        assert out.returncode == 0, out.stderr

        def factory(role: str) -> Factory:
            return lambda: psycopg.connect(host="127.0.0.1", port=5432, dbname=name, user=roles[role],
                                           password=password, connect_timeout=10)

        yield {"engine": factory("engine"), "owner": factory("owner")}
    finally:
        _psql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')
        _psql(f"DROP ROLE IF EXISTS {roles['engine']}; DROP ROLE IF EXISTS {roles['owner']};")


def query(factory: Factory, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    conn = factory()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else []
        conn.commit()
        return rows
    finally:
        conn.close()


def boot(pg: dict[str, Factory]) -> tuple[TestClient, Services]:
    """(Re)démarrage de l'API sur la même base, avec le compte de production (membre de pokeshop_engine)."""
    settings = load_settings({"POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN),
                              "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN),
                              "POKESHOP_AGENT_TOKENS_SHA256": JR.agent_tokens_env()})
    svc = Services.build(settings, clock=lambda: NOW, notifier=LogNotifier(), connect=pg["engine"])
    client = TestClient(create_app(services=svc))
    # Apport attesté par la propriétaire (registre en base, SEC-06) : idempotent d'un démarrage à l'autre.
    apport = {"movement_id": "FICTIF_APPORT", "at": (NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
              "amount": "8000"}  # fmt: skip
    assert client.post("/capital/movements", headers={**H, OWNER_TOKEN_HEADER: OWNER_TOKEN}, json=apport).status_code in (
        200, 201)
    return client, svc


def photo(cash: str = "8000") -> dict[str, Any]:
    return {
        "as_of": NOW.isoformat(), "stock_budget_chf": "3000", "cash_available_chf": "5000", "ads_daily_cap_chf": "33",
        "net_worth": {"as_of": NOW.isoformat(), "cash_chf": cash},
    }


def test_postgres_state_journal_is_chained_and_refuses_a_second_writer(pg: dict[str, Factory]) -> None:
    first = PostgresStateJournal(pg["engine"], "stoploss")
    second = PostgresStateJournal(pg["engine"], "stoploss")
    assert first.load() == [] and second.load() == []
    assert first.append({"n": 1, "montant": D("12.50")}) == 1
    with pytest.raises(StateStoreError, match="refusée"):
        second.append({"n": "autre processus"})
    assert first.append({"n": 2}) == 2
    assert PostgresStateJournal(pg["engine"], "stoploss").load() == [{"n": 1, "montant": "12.50"}, {"n": 2}]
    assert query(pg["engine"], "SELECT count(*) FROM pokeshop.verify_engine_state_journal()") == [(0,)]
    for stmt in ("UPDATE pokeshop.engine_state_journal SET body = '{}'", "DELETE FROM pokeshop.engine_state_journal"):
        with pytest.raises(Exception):  # ajout seul : le compte du moteur ne peut ni modifier ni effacer
            query(pg["engine"], stmt)
    assert query(pg["engine"], "SELECT record->>'montant' FROM pokeshop.engine_state_journal WHERE seq = 1") == [("12.50",)]


def test_restart_on_postgres_keeps_freeze_photo_ledger_northstar_and_quarantine(pg: dict[str, Factory]) -> None:
    """MOT-01 / SEC-01 / E2E-01/02/03/06 avec la base : tout survit au redémarrage du conteneur."""
    client, svc = boot(pg)
    assert client.post("/stoploss/state", headers=HO, json=photo()).status_code == 200
    spend = {"request": {"amount": "40", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                         "payment_method": "PAYPAL", "purpose": "Étuis FICTIFS", "idempotency_key": "FICTIF-PG-SPEND-1",
                         "requested_by": "operations-sav", "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF"},
             "treasury": {"as_of": NOW.isoformat(), "cash_available_chf": "5000", "paypal_balance_chf": "500"},
             "record": True}
    assert body(client.post("/mandate/check", headers=JR.HOPS, json=spend))["recorded"] is True  # revue R5 : pas finance
    # Revue R4 (R3-NEW-05) : commande avec lignes, sortie au CMP dérivée (stock au coût adossé, référence du moteur).
    listing = {"product_key": "FICTIF-P1", "public_sku": "DSP-FICTIF_ALPHA-FR", "fictif": True,
               "identity": {"gtin": "2000000001012", "language": "FR", "extension": "FICTIF_ALPHA", "format": "DISPLAY",
                            "content": "36 BOOSTERS", "sealed": True}}  # fmt: skip
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P1", "listing": listing}]}).status_code == 200
    assert client.post("/stock/receive", headers=JR.HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 1, "ref": "FICTIF-BL-PG"}).status_code == 200
    svc.sync.replacement_costs.update(ReplacementCost(product_key="FICTIF-P1", supplier_id="fictif_grossiste_a",
                                                      unit_cost=D("100.00"), source_ts=NOW, offer_ref="FICTIF",
                                                      fees_recorded_by="propriétaire"))  # revue R5 : frais de la propriétaire
    lot = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-LOT-PG", "qty": 1,
           "unit_cost": "100.00", "stock_ref": "FICTIF-BL-PG", "invoice_ref": "FICTIF-FACT-PG"}
    assert client.post("/costs/movements", headers=JR.HF, json=lot).status_code == 200
    order = {"order_id": "FICTIF-PG-1", "paid_at": NOW.isoformat(), "net_sales_ht": "184.92", "payment_fees": "0",
             "shipping_cost_actual": "3.00", "shipping_label_ref": "FICTIF-ETIQ-1", "source": "Shopify FICTIF",
             "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=HORDERS, json=order).status_code == 201
    inc = body(client.post("/incidents", headers=HDATA, json={"code": "INC-01", "product_key": "FICTIF-P1",
                                                              "cause": "prix ×10 FICTIF", "actor": "agent-05"}))["incident"]
    assert client.post("/stoploss/freeze", headers=HQA, json={"actor": "agent-12", "reason": "débit inconnu FICTIF"}).status_code == 200

    client2, svc2 = boot(pg)
    health = body(client2.get("/health"))
    assert health["global_frozen"] is True and health["persistence"]["backend"] == "postgres"
    assert health["persistence"]["restored"] is True
    assert svc2.stoploss_state is not None and svc2.stoploss_engine.latch.cause == "MANUAL"
    replay = body(client2.post("/mandate/check", headers=JR.HOPS, json=spend))["decision"]
    assert replay["replayed"] is True
    assert body(client2.get("/northstar", headers=H))["cumulative"] == "81.92"  # 184.92 − 3.00 − 100.00 (CMP)
    assert svc2.costs.ledger("FICTIF-P1").qty_on_hand == 0  # sortie dérivée persistée
    assert svc2.orders.get("FICTIF-PG-1") is not None  # registre des commandes en base
    assert svc2.incidents.is_quarantined("FICTIF-P1") and svc2.incidents.get(inc["incident_id"]).is_open
    refs = query(pg["engine"], "SELECT details->>'ref' FROM pokeshop.incidents ORDER BY incident_id")
    assert len({r[0] for r in refs}) == len(refs) >= 2  # INC-01 + INC-09 du gel : deux lignes distinctes


def test_incident_mirror_never_overwrites_another_incident(pg: dict[str, Factory]) -> None:
    """SEC-14 / E2E-05 : même référence, autre incident => refus (aucune ligne critique écrasée)."""
    client, svc = boot(pg)
    critical = svc.incidents.open(code="INC-06", product_key="FICTIF-P1", cause="Survente FICTIVE (critique)")
    sink = PostgresIncidentSink(pg["engine"])
    impostor = critical.replace(kind="COMMANDE_ANOMALIE", severity="MAJEUR", cause="autre incident", product_key="FICTIF-P9")
    with pytest.raises(IncidentError, match="autre incident"):
        sink.record(impostor)
    with pytest.raises(IncidentError):
        sink.record(impostor.replace(status="RESOLU", resolved_at=NOW, resolved_by="agent"))
    rows = query(pg["engine"], "SELECT kind, severity, status, cause FROM pokeshop.incidents WHERE details->>'ref' = %s",
                 (critical.incident_id,))
    assert rows == [("INC-06", "CRITIQUE", "OUVERT", "Survente FICTIVE (critique)")]
    with pytest.raises(Exception):  # index unique sur la référence
        query(pg["engine"], "INSERT INTO pokeshop.incidents (kind, severity, scope, cause, proposed_action, details) "
              "VALUES ('X', 'INFO', 'GLOBAL', 'x', 'x', %s::jsonb)", (json.dumps({"ref": critical.incident_id}),))


def test_owner_raises_autonomy_with_the_production_engine_account(pg: dict[str, Factory]) -> None:
    """E2E-14 / SEC-19 : hausse par la propriétaire possible avec le compte membre de pokeshop_engine, vérifiée par la base."""
    client, svc = boot(pg)
    missing = client.post("/autonomy", headers=HO, json={"level": 2, "reason": "C14 FICTIF : recette OK", "actor": "propriétaire"})
    assert missing.status_code == 403 and "non enregistrée" in body(missing)["erreur"]  # plus de 500 opaque
    with pytest.raises(Exception):  # le compte du moteur ne peut pas enregistrer d'empreinte
        query(pg["engine"], "INSERT INTO pokeshop.owner_token_fingerprint (token_sha256) VALUES (%s)",
              (hash_owner_token(OWNER_TOKEN),))
    # Intervention unique de la propriétaire (compte membre de pokeshop_owner) : enregistrer son empreinte.
    query(pg["owner"], "INSERT INTO pokeshop.owner_token_fingerprint (token_sha256) VALUES (%s)",
          (hash_owner_token(OWNER_TOKEN),))
    raised = client.post("/autonomy", headers=HO, json={"level": 2, "reason": "C14 FICTIF : recette OK", "actor": "propriétaire"})
    assert raised.status_code == 200 and body(raised)["state"]["level"] == 2
    jump = client.post("/autonomy", headers=HO, json={"level": 4, "reason": "saut interdit FICTIF", "actor": "propriétaire"})
    assert jump.status_code == 409 and svc.autonomy.level == 2
    store = PostgresAutonomyStore(pg["engine"])
    with pytest.raises(AutonomyRefusedError):  # la base revérifie le jeton elle-même
        store.append(AutonomyState(level=3, changed_by="agent", changed_by_role="PROPRIETAIRE", reason="usurpation", at=NOW),
                     owner_token="FICTIF-faux-jeton-0000000000000")
    with pytest.raises(AutonomyRefusedError):  # et un niveau à la fois, même avec le bon jeton
        store.append(AutonomyState(level=4, changed_by="propriétaire", changed_by_role="PROPRIETAIRE", reason="saut", at=NOW),
                     owner_token=OWNER_TOKEN)
    with pytest.raises(AutonomyRefusedError):  # sans jeton, le compte du moteur ne peut pas se déclarer propriétaire
        store.append(AutonomyState(level=3, changed_by="agent", changed_by_role="PROPRIETAIRE", reason="usurpation", at=NOW))
    assert [row[0] for row in query(pg["engine"], "SELECT level FROM pokeshop.autonomy_levels ORDER BY change_id")] == [2]
    _, svc2 = boot(pg)
    assert svc2.autonomy.level == 2


def body(resp: Any) -> Any:
    return json.loads(resp.content)
