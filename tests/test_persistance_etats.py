"""Persistance des états de sécurité (lot F1) : rien n'est perdu au redémarrage, tout est fermé par défaut.

Chaque test reconstruit :class:`Services` sur le **même** dossier d'état (JSON Lines) pour simuler un
redémarrage du conteneur (``restart: unless-stopped``) : gel du stop-loss (point zéro compris),
dernière photo valide, registre du mandat (enveloppes, idempotence), étoile polaire, incidents,
quarantaines et suspensions, historique des prix, niveau d'autonomie. Un journal illisible gèle
le service. Réarmement attesté (SEC-07), jeton court refusé (SEC-24), tentatives journalisées
(SEC-26), route du point zéro (E2E-21). Jetons, montants et références FICTIFS.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
import jetons_roles as R
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, PersistentPriceHistory, Services, create_app
from pokeshop.audit import (
    FailedStateJournal,
    InMemoryAuditLog,
    InMemoryStateJournal,
    JsonlStateJournal,
    StateStoreError,
)
from pokeshop.autonomy import GateReason, WriteAction
from pokeshop.incidents import (
    RESTORE_HOLD,
    IncidentCode,
    IncidentManager,
    IncidentPersistenceError,
    LogNotifier,
)
from pokeshop.mandate import (
    DEFAULT_MANDATE_PATH,
    LedgerPersistenceError,
    Mandate,
    SpendCategory,
    SpendLedger,
    mandate_fingerprint,
    parse_mandate,
)
from pokeshop.models import DecisionStatus, PriceDecision, ReplacementCost
from pokeshop.northstar import ContributionEntry, NorthStarLedger, NorthStarPersistenceError, Post
from pokeshop.settings import STATE_DIR_MEMORY, Settings, SettingsError, default_state_dir, load_settings, sha256_hex
from pokeshop.stoploss import (
    CapitalMovement,
    GlobalLatch,
    RearmReferenceMismatchError,
    RearmRefusedError,
    StopLossEngine,
    StopLossError,
    StopLossPersistenceError,
    StopLossState,
    hash_owner_token,
    load_stoploss_config,
)
from pokeshop.sync import price_reference_24h

TZ = ZoneInfo("Europe/Zurich")
NOW = datetime(2026, 10, 20, 10, 0, tzinfo=TZ)
API_TOKEN = "FICTIF-jeton-api-0000000000000001"
OWNER_TOKEN = "FICTIF-jeton-proprietaire-tres-long-0001"
H = {API_TOKEN_HEADER: API_TOKEN}
HO = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: OWNER_TOKEN}
# Jetons nommés par rôle (matrice pokeshop.authz) : la photo est déposée par le workflow 07 (n8n-07-stoploss),
# le solde PayPal par le connecteur de trésorerie, la dépense demandée par l'agent opérations ; le jeton
# commun n'a que la lecture et les aperçus.
FINANCE_TOKEN = R.ROLE_TOKENS["finance-pricing"]
OPS_TOKEN = R.ROLE_TOKENS["operations-sav"]
HF, HOPS, HPHOTO, HTRES, HQA = R.HF, R.HOPS, R.HPHOTO, R.HTRES, R.HQA
HDATA, HINC, HCHEF, HORDERS, HCAT = R.HDATA, R.HINC, R.HCHEF, R.HORDERS, R.HCAT
CONFIG = load_stoploss_config()
LISTING_P1 = {
    "product_key": "FICTIF-P1", "public_sku": "DSP-FICTIF_ALPHA-FR", "fictif": True,
    "identity": {"gtin": "2000000001012", "language": "FR", "extension": "FICTIF_ALPHA", "format": "DISPLAY",
                 "content": "36 BOOSTERS", "sealed": True},
}
STREAMS = ("stoploss", "stoploss_photo", "mandate_ledger", "northstar", "incidents", "price_history")


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def settings(state_dir: Path, **extra: str) -> Settings:
    env = {
        "POKESHOP_API_TOKEN_SHA256": sha256_hex(API_TOKEN),
        "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(OWNER_TOKEN),
        "POKESHOP_STATE_DIR": str(state_dir),
        "POKESHOP_AGENT_TOKENS_SHA256": R.agent_tokens_env(),
    }
    env.update(extra)
    return load_settings(env)


OWNER_APPORT = CapitalMovement(movement_id="FICTIF_APPORT", at=NOW - timedelta(days=30), kind="CONTRIBUTION",
                               amount=D("8000"))  # fmt: skip
"""Apport FICTIF attesté par la propriétaire : registre POST /capital/movements, jamais la photo (SEC-06)."""


def boot(state_dir: Path, *, clock: Clock | None = None, mandate: Mandate | None = None, capital: bool = True,
         **extra: str) -> tuple[TestClient, Services]:  # fmt: skip
    """Démarre (ou redémarre) le service sur le dossier d'état donné (apport de la propriétaire au registre)."""
    svc = Services.build(settings(state_dir, **extra), clock=clock or Clock(), notifier=LogNotifier())
    if mandate is not None:
        svc.mandate = mandate
    if capital and "capital_movements" not in svc.restore_errors:
        svc.capital.record(OWNER_APPORT, now=NOW)  # idempotent : même mouvement => sans effet
    return TestClient(create_app(services=svc)), svc


def photo(cash: str = "8000", *, at: datetime = NOW, available: str = "5000") -> dict[str, Any]:
    """Photo déposée (POST /stoploss/state) : sans mouvement de capital (registre de la propriétaire)."""
    return {
        "as_of": at.isoformat(), "stock_budget_chf": "3000", "cash_available_chf": available, "ads_daily_cap_chf": "33",
        "net_worth": {"as_of": at.isoformat(), "cash_chf": cash},
    }


def signed_mandate() -> Mandate:
    """Mandat FICTIF signé (enveloppe PACKAGING 300 CHF), actif du 10.10.2026 au 31.1.2027."""
    data = copy.deepcopy(yaml.safe_load(DEFAULT_MANDATE_PATH.read_text(encoding="utf-8")))
    data["valid_from"], data["valid_until"] = "2026-10-10", "2027-01-31"
    data["limits"].update(per_transaction_chf="500", per_month_chf="3000", stock_budget_chf="3000",
                          ads_daily_cap_chf="33", email_daily_send_quota=20)
    for name, value in {"STOCK": "2700", "ACCESSORIES": "300", "SAMPLES": "100", "SITE_TOOLS": "1500",
                        "DA_CONTENT": "400", "PACKAGING": "300", "SHIPPING": "600", "ADVERTISING": "500"}.items():
        data["categories"][name]["envelope_chf"] = value
    data["suppliers"] = [
        {"supplier_id": "FICTIF_EMBALLAGES", "label": "Emballages (fictif)", "categories": ["PACKAGING"],
         "payment_methods": ["PAYPAL"], "validated_on": "2026-10-10", "due_diligence_ref": "checklist FICTIF",
         "payee_ref": "coffre:beneficiaires/FICTIF_EMBALLAGES"},
    ]
    data["approval"] = {"approved_by": "FICTIF Propriétaire", "approved_at": "2026-10-10T09:00:00+02:00",
                        "fingerprint_sha256": None, "revoked_at": None}
    data["approval"]["fingerprint_sha256"] = mandate_fingerprint(data)
    return parse_mandate(data, expected_fingerprint=data["approval"]["fingerprint_sha256"])  # empreinte au coffre


def deposit_treasury(client: TestClient, cash: str = "8000") -> None:
    """Photo stop-loss (workflow 07) et solde PayPal (connecteur de trésorerie) : registres du moteur."""
    assert client.post("/stoploss/state", headers=HO, json=photo(cash)).status_code == 200
    reading = {"as_of": NOW.isoformat(), "balance_chf": "2000", "source": "relevé PayPal FICTIF"}
    assert client.post("/treasury/paypal-balance", headers=HTRES, json=reading).status_code == 200


def spend(i: int, amount: str = "150") -> dict[str, Any]:
    return {
        "request": {"amount": amount, "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                    "payment_method": "PAYPAL", "purpose": "Cartons d'expédition FICTIFS",
                    "idempotency_key": f"FICTIF-PKG-{i:04d}", "requested_by": "operations-sav",
                    "requested_at": NOW.isoformat(), "amount_source": "devis FICTIF n°1", "fictif": True},
        "treasury": {"as_of": NOW.isoformat(), "cash_available_chf": "5000", "paypal_balance_chf": "2000"},
        "record": True,
    }


# ------------------------------------------------------------------ journaux d'état


def test_jsonl_journal_is_chained_append_only_and_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "etat" / "stoploss.jsonl"
    journal = JsonlStateJournal(path)
    assert journal.load() == [] and journal.backend == "fichier"
    for i in range(3):
        assert journal.append({"n": i, "montant": D("1.10")}) == i + 1
    assert JsonlStateJournal(path).load() == [{"n": 0, "montant": "1.10"}, {"n": 1, "montant": "1.10"},
                                              {"n": 2, "montant": "1.10"}]
    with pytest.raises(StateStoreError):
        journal.append({"float": 0.1})  # aucun float dans un journal d'état
    lines = path.read_text(encoding="utf-8").splitlines()
    # ligne modifiée (montant changé sans recalculer la chaîne)
    path.write_text("\n".join([lines[0], lines[1].replace('"n":1', '"n":9'), lines[2]]) + "\n", encoding="utf-8")
    with pytest.raises(StateStoreError, match="modifiée"):
        JsonlStateJournal(path).load()
    # ligne supprimée au milieu
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    with pytest.raises(StateStoreError, match="séquence"):
        JsonlStateJournal(path).load()
    # écriture interrompue (dernière ligne tronquée)
    path.write_text("\n".join(lines) + "\n" + lines[2][:20], encoding="utf-8")
    with pytest.raises(StateStoreError, match="tronquée"):
        JsonlStateJournal(path).load()


def test_jsonl_journal_refuses_a_second_writer(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    first, second = JsonlStateJournal(path), JsonlStateJournal(path)
    first.load(), second.load()
    first.append({"processus": 1})
    with pytest.raises(StateStoreError, match="autre processus"):
        second.append({"processus": 2})
    assert JsonlStateJournal(path).load() == [{"processus": 1}]


def test_failed_journal_refuses_everything() -> None:
    failed = FailedStateJournal("northstar", "ligne 3 illisible")
    with pytest.raises(StateStoreError, match="illisible"):
        failed.load()
    with pytest.raises(StateStoreError):
        failed.append({"x": 1})


def test_settings_state_dir_default_memory_and_prod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    assert default_state_dir() == tmp_path / "xdg" / "pokeshop"
    assert load_settings({}).state_dir == tmp_path / "xdg" / "pokeshop" and load_settings({}).state_backend == "fichier"
    memory = load_settings({"POKESHOP_STATE_DIR": STATE_DIR_MEMORY})
    assert memory.state_dir is None and memory.state_backend == "memoire"
    with pytest.raises(SettingsError, match="production"):
        load_settings({"POKESHOP_ENV": "prod", "POKESHOP_STATE_DIR": STATE_DIR_MEMORY})
    assert load_settings({"POKESHOP_ENV": "prod"}).state_backend == "fichier"


# ------------------------------------------------------------------ stop-loss global


def test_manual_freeze_survives_restart_and_still_blocks_spending(tmp_path: Path) -> None:
    """MOT-01 / SEC-01 / E2E-01 : un redémarrage ne lève jamais un gel."""
    client, svc = boot(tmp_path, mandate=signed_mandate())
    deposit_treasury(client)
    first = body(client.post("/mandate/check", headers=HOPS, json=spend(1)))["decision"]
    assert first["outcome"] == "APPROVED_WITHIN_MANDATE"
    frozen = client.post("/stoploss/freeze", headers=HQA, json={"actor": "agent-12-qa", "reason": "débit inconnu FICTIF"})
    assert frozen.status_code == 200 and body(frozen)["latch"]["frozen"] is True

    client2, svc2 = boot(tmp_path, mandate=signed_mandate())  # redémarrage du conteneur
    health = body(client2.get("/health"))
    assert health["global_frozen"] is True and health["persistence"] == {
        "backend": "fichier", "restored": True, "unreadable": []}
    assert svc2.stoploss_engine.latch.cause == "MANUAL" and svc2.stoploss_engine.latch.detail == "débit inconnu FICTIF"
    assert [e.event for e in svc2.stoploss_engine.journal].count("MANUAL_FREEZE") == 1
    assert svc2.autonomy.level == 1
    # métriques saines, nouvelle photo : le gel reste verrouillé, les dépenses restent refusées
    assert body(client2.post("/stoploss/state", headers=HO, json=photo()))["status"]["global_frozen"] is True
    after = body(client2.post("/mandate/check", headers=HOPS, json=spend(2, "20")))["decision"]
    assert after["outcome"] == "REJECTED" and "STOPLOSS_GLOBAL_FREEZE" in after["reasons"]
    # MOT-07 / SEC-05 : le rejeu de la dépense approuvée avant le gel n'est jamais APPROVED pendant le gel
    replay = body(client2.post("/mandate/check", headers=HOPS, json=spend(1)))["decision"]
    assert replay["replayed"] is True and replay["outcome"] == "REJECTED"
    assert "STOPLOSS_GLOBAL_FREEZE" in replay["reasons"] and "REPLAY_NOT_PAYABLE" in replay["reasons"]
    gate = svc2.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1")
    assert gate.has(GateReason.STOPLOSS_GLOBAL_FREEZE)


def test_autonomy_level_without_database_survives_restart(tmp_path: Path) -> None:
    """SEC-01 / E2E-21 (t21) : sans base, le niveau ne remonte pas à POKESHOP_AUTONOMY_LEVEL au redémarrage."""
    client, svc = boot(tmp_path, POKESHOP_AUTONOMY_LEVEL="3")
    assert svc.autonomy.level == 3
    client.post("/stoploss/freeze", headers=HQA, json={"actor": "n8n:07-stoploss-watch", "reason": "gel constaté FICTIF"})
    assert svc.autonomy.level == 1
    client2, svc2 = boot(tmp_path, POKESHOP_AUTONOMY_LEVEL="3")
    assert svc2.autonomy.level == 1 and svc2.stoploss_engine.frozen
    assert (tmp_path / "autonomy.jsonl").is_file()


def test_threshold_trip_and_point_zero_survive_restart(tmp_path: Path) -> None:
    """E2E-21 : route du point zéro (jeton propriétaire), point zéro et gel au seuil persistés."""
    client, svc = boot(tmp_path)
    no_photo = client.post("/stoploss/baseline", headers=HO, json={"reason": "J1 : lancement assumé (FICTIF)",
                                                                     "reference_chf": "4200"})
    assert no_photo.status_code == 409
    client.post("/stoploss/state", headers=HO, json=photo())
    agent = client.post("/stoploss/baseline", headers=H, json={"reason": "J1 : lancement assumé (FICTIF)",
                                                                "reference_chf": "4200"})
    assert agent.status_code == 403
    zero = client.post("/stoploss/baseline", headers=HO, json={"reason": "J1 : 2 900 de lancement + 900 de décote assumés",
                                                                "reference_chf": "4200"})
    assert zero.status_code == 200 and body(zero)["latch"]["baseline"]["net_value_chf"] == "4200"
    assert svc.audit.events(action="stoploss.baseline")

    client2, svc2 = boot(tmp_path)
    baseline = svc2.stoploss_engine.latch.baseline
    assert baseline is not None and baseline.origin == "POINT_ZERO" and baseline.net_value_chf == D("4200")
    # 20 % de 4 200 = 840 : valeur nette 3 360 => gel verrouillé (mesuré depuis le point zéro, pas depuis 8 000)
    assert body(client2.post("/stoploss/state", headers=HO, json=photo("3360.01")))["status"]["global_frozen"] is False
    assert body(client2.post("/stoploss/state", headers=HO, json=photo("3360")))["status"]["global_frozen"] is True

    client3, svc3 = boot(tmp_path)
    assert svc3.stoploss_engine.frozen and svc3.stoploss_engine.latch.cause == "THRESHOLD"
    events = [e.event for e in svc3.stoploss_engine.journal]
    assert "BASELINE_SET" in events and events.count("GLOBAL_TRIP") == 1
    assert body(client3.post("/stoploss/state", headers=HO, json=photo("9000")))["status"]["global_frozen"] is True


def test_refused_photo_never_replaces_the_valid_one_even_after_restart(tmp_path: Path) -> None:
    """E2E-15 : une photo refusée (409) ne remplace pas la dernière photo valide, qui est relue au démarrage."""
    client, svc = boot(tmp_path)
    assert client.post("/stoploss/state", headers=HO, json=photo()).status_code == 200
    stale = client.post("/stoploss/state", headers=HO, json=photo(at=NOW - timedelta(days=3)))
    assert stale.status_code == 409 and body(stale)["previous_photo_kept"] is True
    status = body(client.get("/stoploss/status", headers=H))
    assert status["available"] is True and status["rearm_reference"]["net_worth_chf"] == "8000"
    assert svc.stoploss_state is not None and svc.stoploss_state.as_of == NOW

    client2, svc2 = boot(tmp_path)
    restored = body(client2.get("/stoploss/status", headers=H))
    assert restored["available"] is True and restored["rearm_reference"]["photo_sha256"] == status["rearm_reference"]["photo_sha256"]
    assert client2.post("/mandate/check", headers=HOPS, json=spend(1)).status_code == 200  # photo connue : décision possible


# ------------------------------------------------------------------ mandat, étoile polaire


def test_mandate_ledger_envelopes_and_idempotency_survive_restart(tmp_path: Path) -> None:
    """MOT-03 / SEC-02 / E2E-03 : enveloppe cumulée, plafonds et idempotence survivent au redémarrage."""
    client, svc = boot(tmp_path, mandate=signed_mandate())
    deposit_treasury(client)
    first = body(client.post("/mandate/check", headers=HOPS, json=spend(1)))["decision"]
    assert first["outcome"] == "APPROVED_WITHIN_MANDATE"
    second = body(client.post("/mandate/check", headers=HOPS, json=spend(2)))["decision"]
    assert second["outcome"] == "NEEDS_HUMAN_APPROVAL" and "ABOVE_CATEGORY_ENVELOPE" in second["reasons"]
    committed = svc.spend_ledger.committed(category=SpendCategory.PACKAGING)
    assert committed > D("150")

    client2, svc2 = boot(tmp_path, mandate=signed_mandate())
    assert svc2.spend_ledger.committed(category=SpendCategory.PACKAGING) == committed
    assert [e.kind for e in svc2.spend_ledger.events()] == [e.kind for e in svc.spend_ledger.events()]
    replay = body(client2.post("/mandate/check", headers=HOPS, json=spend(1)))["decision"]
    assert replay["replayed"] is True and replay["outcome"] == "APPROVED_WITHIN_MANDATE"  # < 1 h, aucun gel
    fresh = body(client2.post("/mandate/check", headers=HOPS, json=spend(3)))["decision"]
    assert fresh["outcome"] == "NEEDS_HUMAN_APPROVAL" and "ABOVE_CATEGORY_ENVELOPE" in fresh["reasons"]
    assert svc2.spend_ledger.events()[-1].kind == "RECORDED"
    assert svc2.spend_ledger.get("FICTIF-PKG-0001").status.value == "APPROVED"


def test_northstar_cumulative_survives_restart(tmp_path: Path) -> None:
    """E2E-06 : la contribution nette cumulée ne revient pas à 0 au redémarrage."""
    client, svc = boot(tmp_path)
    # coût historique : registre interne (lot reçu au coût, adossé à la réception physique et à une référence du
    # moteur — revue R4 ; sortie au CMP dérivée de la commande)
    item = {"product_id": "FICTIF-P1", "listing": LISTING_P1}
    assert client.post("/catalog/items", headers=HCAT, json={"items": [item]}).status_code == 200
    assert client.post("/stock/receive", headers=HOPS, json={"sku": "DSP-FICTIF_ALPHA-FR", "qty": 1,
                                                             "ref": "FICTIF-BL-1"}).status_code == 200
    svc.sync.replacement_costs.update(ReplacementCost(product_key="FICTIF-P1", supplier_id="fictif_grossiste_a",
                                                      unit_cost=D("140.00"), source_ts=NOW, offer_ref="FICTIF"))
    lot = {"kind": "RECEIPT", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-LOT-1", "qty": 1,
           "unit_cost": "140.00", "stock_ref": "FICTIF-BL-1", "invoice_ref": "FICTIF-FACT-1"}
    sale = {"kind": "ISSUE", "product_key": "FICTIF-P1", "at": NOW.isoformat(), "ref": "FICTIF-O1", "qty": 1}
    assert client.post("/costs/movements", headers=HF, json=lot).status_code == 200
    # Vente dérivée d'une commande enregistrée (coût transporteur réel, lignes), revues R3 (R2-NEW-04, MOT-18) et R4.
    order = {"order_id": "FICTIF-O1", "paid_at": NOW.isoformat(), "net_sales_ht": "184.92", "payment_fees": "5.30",
             "shipping_cost_actual": "3.00", "shipping_label_ref": "FICTIF-ETIQ-1", "source": "Shopify FICTIF",
             "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=HORDERS, json=order).status_code == 201
    assert client.post("/costs/movements", headers=HF, json=sale).status_code == 403  # sortie dérivée, jamais déclarée
    client2, svc2 = boot(tmp_path)
    assert body(client2.get("/northstar", headers=H))["cumulative"] == "36.62"
    assert client2.post("/orders/shipped", headers=HORDERS, json=order).status_code == 200  # rejeu : sans effet
    assert client2.post("/costs/movements", headers=HO, json=sale).status_code == 422  # stock épuisé : refus
    changed = {**order, "net_sales_ht": "999.00"}
    assert client2.post("/orders/shipped", headers=HORDERS, json=changed).status_code == 409
    declared = [{"entry_id": "FICTIF-1", "at": NOW.isoformat(), "post": "NET_SALES", "amount": "999.00", "order_id": "X"}]
    assert client2.post("/northstar/entries", headers=HORDERS, json={"entries": declared}).status_code == 422
    assert len(svc2.northstar.entries()) == 4 and svc2.costs.ledger("FICTIF-P1").qty_on_hand == 0


# ------------------------------------------------------------------ incidents


def test_quarantine_suspension_and_dedup_survive_restart(tmp_path: Path) -> None:
    """E2E-02 / SEC-01 : quarantaines et suspensions relues au démarrage ; reprise après test seulement."""
    client, svc = boot(tmp_path)
    ref = body(client.post("/incidents", headers=HDATA, json={"code": "INC-01", "product_key": "FICTIF-P1",
                                                          "cause": "Prix fournisseur ×10 FICTIF", "actor": "agent-05"}))["incident"]
    glob = body(client.post("/incidents", headers=HQA, json={"code": "INC-14", "cause": "agent hors mandat FICTIF",
                                                           "actor": "agent-12-qa"}))["incident"]
    assert svc.incidents.all_writes_suspended and svc.incidents.is_quarantined("FICTIF-P1")

    client2, svc2 = boot(tmp_path)
    listing = body(client2.get("/incidents", headers=H, params={"open_only": "true"}))
    assert listing["quarantined"] == {"FICTIF-P1": [ref["incident_id"]]}
    assert listing["suspended"] == {"*": [glob["incident_id"]]} and len(listing["incidents"]) == 2
    decision = svc2.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False, product_key="FICTIF-P1")
    assert decision.has(GateReason.PRODUCT_QUARANTINED) and decision.has(GateReason.ALL_WRITES_SUSPENDED)
    again = body(client2.post("/incidents", headers=HDATA, json={"code": "INC-01", "product_key": "FICTIF-P1",
                                                             "cause": "même anomalie", "actor": "agent-05"}))["incident"]
    assert again["incident_id"] == ref["incident_id"]  # doublon reconnu après redémarrage
    early = client2.post(f"/incidents/{ref['incident_id']}/resume", headers=HINC, json={"actor": "agent-12"})
    assert early.status_code == 409  # aucun test enregistré : pas de reprise implicite
    client2.post(f"/incidents/{ref['incident_id']}/test", headers=HO,  # test attesté par la propriétaire
                 json={"test_ref": "rejeu dry-run FICTIF", "passed": True, "actor": "agent-12"})
    assert client2.post(f"/incidents/{ref['incident_id']}/resume", headers=HINC, json={"actor": "agent-12"}).status_code == 200

    _, svc3 = boot(tmp_path)
    assert not svc3.incidents.is_quarantined("FICTIF-P1") and svc3.incidents.all_writes_suspended
    assert svc3.incidents.get(ref["incident_id"]).status.value == "RESOLU"
    assert svc3.incidents.get(ref["incident_id"]).test_passed is True


def test_incident_ids_are_unique_across_processes(tmp_path: Path) -> None:
    """SEC-14 / E2E-05 : deux processus (ou un redémarrage) ne réattribuent jamais le même identifiant."""
    clock = Clock()
    managers = [IncidentManager(audit=InMemoryAuditLog(clock=clock), clock=clock,
                                store=JsonlStateJournal(tmp_path / f"p{i}" / "incidents.jsonl")) for i in range(2)]
    ids = [m.open(code=IncidentCode.INC_06, product_key=f"FICTIF-P{n}", cause="survente FICTIVE").incident_id
           for n in range(5) for m in managers]
    assert len(set(ids)) == len(ids)
    assert all(re.fullmatch(r"INC-20261020-[0-9A-F]{8}", i) for i in ids)
    restarted = IncidentManager(audit=InMemoryAuditLog(clock=clock), clock=clock,
                                store=JsonlStateJournal(tmp_path / "p0" / "incidents.jsonl"))
    assert restarted.restore() == 5
    new = restarted.open(code=IncidentCode.INC_01, product_key="FICTIF-NEW", cause="prix anormal FICTIF").incident_id
    assert new not in ids


# ------------------------------------------------------------------ fermé par défaut


@pytest.mark.parametrize("stream", STREAMS)
def test_unreadable_state_journal_starts_frozen(tmp_path: Path, stream: str) -> None:
    """Journal d'état configuré mais illisible => démarrage gelé (RESTORE_FAILED), réarmement impossible."""
    client, _ = boot(tmp_path)
    client.post("/stoploss/state", headers=HO, json=photo())
    (tmp_path / f"{stream}.jsonl").open("a", encoding="utf-8").write('{"seq": 99, "pas": "une ligne valide"}\n')

    client2, svc2 = boot(tmp_path, mandate=signed_mandate())
    health = body(client2.get("/health"))
    assert health["global_frozen"] is True and health["persistence"]["restored"] is False
    assert health["persistence"]["unreadable"] == [stream] and f"persistence.{stream}" in health["load_errors"]
    assert svc2.stoploss_engine.restore_hold is not None
    if stream != "stoploss":
        assert svc2.stoploss_engine.latch.cause == "RESTORE_FAILED"
    rearm = client2.post("/stoploss/rearm", headers=HO, json={"reason": "tentative de levée du gel de démarrage",
                                                              "rebase": False})
    assert rearm.status_code == 503 and svc2.stoploss_engine.frozen
    gate = svc2.gate.authorize(WriteAction.SYNC_STOCK, dry_run=False, product_key="FICTIF-P1")
    assert not gate.allowed
    if stream == "mandate_ledger":
        assert client2.post("/mandate/check", headers=HOPS, json=spend(9)).status_code == 503
    if stream == "northstar":
        assert client2.get("/northstar", headers=H).status_code == 503
    if stream == "incidents":
        assert svc2.incidents.all_writes_suspended and RESTORE_HOLD in svc2.incidents.suspended()["*"]
    if stream == "stoploss_photo":
        assert svc2.stoploss_state is None
        assert client2.post("/stoploss/state", headers=HO, json=photo()).status_code == 503


def test_unreadable_autonomy_history_starts_frozen_at_level_one(tmp_path: Path) -> None:
    boot(tmp_path, POKESHOP_AUTONOMY_LEVEL="3")
    (tmp_path / "autonomy.jsonl").write_text("{pas du json\n", encoding="utf-8")
    client, svc = boot(tmp_path, POKESHOP_AUTONOMY_LEVEL="3")
    assert svc.autonomy.level == 1 and svc.stoploss_engine.frozen
    assert body(client.get("/health"))["persistence"]["unreadable"] == ["autonomy"]


class FlakyJournal(InMemoryStateJournal):
    """Journal dont l'écriture peut tomber en panne (disque plein, base injoignable)."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.broken = False

    def append(self, record: Any) -> int:
        if self.broken:
            raise StateStoreError("disque plein (FICTIF)")
        return super().append(record)


def state(cash: str = "8000") -> StopLossState:
    return StopLossState.model_validate({**photo(cash), "capital_movements": [OWNER_APPORT.model_dump(mode="json")]})


def test_storage_failure_keeps_freezes_and_never_applies_relaxation() -> None:
    journal = FlakyJournal("stoploss")
    engine = StopLossEngine(CONFIG, owner_token_sha256=hash_owner_token(OWNER_TOKEN), store=journal)
    journal.broken = True
    with pytest.raises(StopLossPersistenceError):
        engine.freeze("agent-12", "débit inconnu FICTIF", NOW)
    assert engine.frozen  # le gel s'applique quand même (fermé par défaut)
    journal.broken = False
    engine.freeze("agent-12", "débit inconnu FICTIF", NOW)  # nouvelle tentative : enregistré
    journal.broken = True
    with pytest.raises(StopLossPersistenceError):
        engine.rearm(OWNER_TOKEN, "reprise après examen FICTIF", now=NOW, rebase=False)
    assert engine.frozen  # réarmement non enregistré = non appliqué
    with pytest.raises(StopLossPersistenceError):
        engine.evaluate(state(), NOW)  # évaluation non journalisée => stop-loss indisponible
    restored = StopLossEngine.restore(CONFIG, store=journal, owner_token_sha256=hash_owner_token(OWNER_TOKEN))
    assert restored.frozen and restored.latch.cause == "MANUAL"


def test_ledger_northstar_incidents_and_prices_refuse_unsaved_changes() -> None:
    from pokeshop.mandate import MandateDecision, SpendRequest, TreasurySnapshot, check
    from pokeshop.stoploss import StopLossStatus

    ledger_journal = FlakyJournal("mandate_ledger")
    ledger = SpendLedger(store=ledger_journal)
    request = SpendRequest.model_validate(spend(1)["request"])
    status = StopLossStatus(as_of=NOW, autonomy_level=1)
    decision: MandateDecision = check(request, signed_mandate(), ledger, status,
                                      TreasurySnapshot.model_validate(spend(1)["treasury"]), now=NOW)
    ledger_journal.broken = True
    with pytest.raises(LedgerPersistenceError):
        ledger.record(request, decision)
    assert ledger.get(request.idempotency_key) is None and ledger.events() == ()

    ns_journal = FlakyJournal("northstar")
    northstar = NorthStarLedger(store=ns_journal)
    ns_journal.broken = True
    with pytest.raises(NorthStarPersistenceError):
        northstar.record(ContributionEntry(entry_id="FICTIF-1", at=NOW, post=Post.PAYMENT, amount=D("10.00")))
    assert northstar.entries() == ()

    inc_journal = FlakyJournal("incidents")
    manager = IncidentManager(audit=InMemoryAuditLog(clock=Clock()), clock=Clock(), store=inc_journal)
    incident = manager.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix anormal FICTIF")
    manager.record_test(incident.incident_id, test_ref="rejeu FICTIF", passed=True, actor="agent-12")
    inc_journal.broken = True
    with pytest.raises(IncidentPersistenceError):
        manager.resume(incident.incident_id, actor="agent-12")
    assert manager.is_quarantined("FICTIF-P1") and manager.get(incident.incident_id).is_open
    with pytest.raises(IncidentPersistenceError):  # confinement appliqué même si l'écriture échoue
        manager.open(code=IncidentCode.INC_06, product_key="FICTIF-P2", cause="survente FICTIVE")
    assert manager.is_quarantined("FICTIF-P2")

    price_journal = FlakyJournal("price_history")
    history = PersistentPriceHistory(price_journal)
    history.publish("FICTIF-P1", D("199.90"), NOW - timedelta(days=2), "agent", validated=True)
    price_journal.broken = True
    with pytest.raises(StateStoreError):
        history.publish("FICTIF-P1", D("149.90"), NOW, "agent", validated=True)
    assert history.current_price("FICTIF-P1") == D("199.90") and len(history.events()) == 1


def test_price_history_reference_survives_restart(tmp_path: Path) -> None:
    """MOT-03 : la référence à 24 h du plafond de 5 %/jour n'est pas perdue au redémarrage."""
    path = tmp_path / "price_history.jsonl"
    history = PersistentPriceHistory(JsonlStateJournal(path))
    history.publish("FICTIF-P1", D("199.90"), NOW - timedelta(days=2), "agent", validated=True)
    decision = PriceDecision(floor_price=D("150.00"), recommended_price=D("209.90"), contribution_chf=D("30.00"),
                             contribution_pct=D("0.16"), status=DecisionStatus.OK, reasons=[], rules_version="v1",
                             inputs_hash="0" * 64)
    history.record_decision("FICTIF-P1", decision, NOW - timedelta(hours=1))
    history.publish("FICTIF-P1", D("204.90"), NOW - timedelta(hours=1), "agent", validated=True)
    restored = PersistentPriceHistory.restore(JsonlStateJournal(path))
    assert restored.events() == history.events()
    assert price_reference_24h(restored, "FICTIF-P1", NOW, D("204.90")) == D("199.90")
    assert restored.current_price("FICTIF-P1") == D("204.90")
    restored.rollback("FICTIF-P1", NOW, "agent", "retour au dernier prix validé FICTIF")
    assert PersistentPriceHistory.restore(JsonlStateJournal(path)).current_price("FICTIF-P1") == D("199.90")


# ------------------------------------------------------------------ réarmement (SEC-07, SEC-24, SEC-26)


def test_rearm_needs_attested_reference_and_resists_a_poisoned_photo(tmp_path: Path) -> None:
    """SEC-07 : la référence du réarmement rebasé est attestée par la propriétaire, pas la dernière photo d'un agent."""
    client, svc = boot(tmp_path)
    tripped = body(client.post("/stoploss/state", headers=HO, json=photo("4000")))
    assert tripped["status"]["global_frozen"] is True
    examined = body(client.get("/stoploss/status", headers=H))["rearm_reference"]
    assert examined["net_worth_chf"] == "4000"
    # un agent dépose une photo minorée juste avant le réarmement
    assert client.post("/stoploss/state", headers=HO, json=photo("100")).status_code == 200
    mismatch = client.post("/stoploss/rearm", headers=HO, json={"reason": "réarmement après examen de la valeur nette",
                                                                "reference_chf": "4000"})
    assert mismatch.status_code == 409 and "100,00 CHF" in body(mismatch)["erreur"] and svc.stoploss_engine.frozen
    pinned = client.post("/stoploss/rearm", headers=HO, json={"reason": "réarmement après examen de la valeur nette",
                                                              "reference_chf": "4000", "photo_sha256": examined["photo_sha256"]})
    assert pinned.status_code == 409 and "remplacée" in body(pinned)["erreur"] and svc.stoploss_engine.frozen
    journal = [e.event for e in svc.stoploss_engine.journal]
    assert journal.count("REARM_REFUSED") == 2 and len(svc.audit.events(action="stoploss.rearm_refused")) == 2
    # la photo honnête revient : le réarmement attesté passe, rebasé sur 4 000
    client.post("/stoploss/state", headers=HO, json=photo("4000"))
    ok = client.post("/stoploss/rearm", headers=HO, json={"reason": "réarmement après examen de la valeur nette",
                                                          "reference_chf": "4000.40"})
    assert ok.status_code == 200 and body(ok)["latch"]["baseline"]["net_value_chf"] == "4000"
    _, svc2 = boot(tmp_path)
    assert not svc2.stoploss_engine.frozen and svc2.stoploss_engine.latch.baseline.net_value_chf == D("4000")


def test_engine_rearm_attestation_rules() -> None:
    engine = StopLossEngine(CONFIG, owner_token_sha256=hash_owner_token(OWNER_TOKEN))
    engine.evaluate(state("4000"), NOW)
    assert engine.frozen
    with pytest.raises(StopLossError, match="attestée obligatoire"):
        engine.rearm(OWNER_TOKEN, "reprise FICTIVE", now=NOW, state=state("4000"))
    with pytest.raises(RearmReferenceMismatchError):
        engine.rearm(OWNER_TOKEN, "reprise FICTIVE", now=NOW, state=state("100"), attested_reference_chf=D("4000"))
    with pytest.raises(StopLossError):
        engine.rearm(OWNER_TOKEN, "reprise FICTIVE", now=NOW, state=state("4000"), attested_reference_chf=0.5)  # type: ignore[arg-type]
    assert engine.frozen
    engine.rearm(OWNER_TOKEN, "reprise FICTIVE", now=NOW, state=state("4000"), attested_reference_chf=D("4001.00"))
    assert not engine.frozen and engine.latch.baseline.net_value_chf == D("4000")


def test_short_owner_token_never_rearms(tmp_path: Path) -> None:
    """SEC-24 : un jeton de moins de 16 caractères est refusé au réarmement comme pour l'autonomie."""
    short = "1234"
    client, svc = boot(tmp_path, POKESHOP_OWNER_TOKEN_SHA256=sha256_hex(short))
    client.post("/stoploss/state", headers=HO, json=photo())
    client.post("/stoploss/freeze", headers=HQA, json={"actor": "agent-12", "reason": "gel de test FICTIF"})
    headers = {API_TOKEN_HEADER: API_TOKEN, OWNER_TOKEN_HEADER: short}
    rearm = client.post("/stoploss/rearm", headers=headers, json={"reason": "réarmement avec jeton court",
                                                                  "rebase": False})
    assert rearm.status_code == 403 and svc.stoploss_engine.frozen
    assert svc.stoploss_engine.journal[-1].event == "REARM_REFUSED"
    raise_level = client.post("/autonomy", headers=headers, json={"level": 2, "reason": "jeton court", "actor": "x1"})
    assert raise_level.status_code == 403
    engine = StopLossEngine(CONFIG, owner_token_sha256=sha256_hex(short))
    engine.freeze("agent-12", "test", NOW)
    with pytest.raises(RearmRefusedError):
        engine.rearm(short, "reprise FICTIVE", now=NOW, rebase=False)


def test_every_owner_token_refusal_is_logged(tmp_path: Path) -> None:
    """SEC-26 : en-tête absent ou identique au jeton d'API => refus journalisé (audit + journal du stop-loss)."""
    client, svc = boot(tmp_path)
    client.post("/stoploss/state", headers=HO, json=photo())
    client.post("/stoploss/freeze", headers=HQA, json={"actor": "agent-12", "reason": "gel de test FICTIF"})
    absent = client.post("/stoploss/rearm", headers=H, json={"reason": "sondage de la route de réarmement"})
    assert absent.status_code == 403
    same = client.post("/stoploss/rearm", headers={**H, OWNER_TOKEN_HEADER: API_TOKEN},
                       json={"reason": "sondage de la route de réarmement"})
    assert same.status_code == 403
    refused = svc.audit.events(action="stoploss.rearm.owner_token_refused")
    assert [e.payload["motif"] for e in refused] == ["absent", "identique au jeton d'API"]
    assert all(API_TOKEN not in json.dumps(e.payload) for e in refused)
    assert [e.event for e in svc.stoploss_engine.journal].count("REARM_REFUSED") == 2
    client.post("/autonomy", headers=HCHEF, json={"level": 2, "reason": "sondage FICTIF", "actor": "agent-01"})
    assert svc.audit.events(action="autonomy.raise.owner_token_refused")
    client.post("/stoploss/baseline", headers=H, json={"reason": "sondage du point zéro", "reference_chf": "1"})
    assert svc.audit.events(action="stoploss.baseline.owner_token_refused")
    assert svc.stoploss_engine.journal[-1].event == "BASELINE_REFUSED"
    # journal du stop-loss relu au démarrage : les tentatives restent tracées
    _, svc2 = boot(tmp_path)
    assert [e.event for e in svc2.stoploss_engine.journal].count("REARM_REFUSED") == 2


def test_restore_hold_is_never_persisted(tmp_path: Path) -> None:
    """Le gel de démarrage (journal illisible) n'est pas enregistré : réparer puis redémarrer suffit."""
    client, _ = boot(tmp_path)
    client.post("/stoploss/state", headers=HO, json=photo())
    bad = tmp_path / "northstar.jsonl"
    bad.write_text("garbage\n", encoding="utf-8")
    client_hold, svc = boot(tmp_path)
    assert svc.stoploss_engine.latch.cause == "RESTORE_FAILED"
    # NEW-02 : le workflow 07 continue de déposer des photos pendant le gel ; l'évaluation est journalisée
    # avec le verrou ENREGISTRÉ, jamais avec le gel de démarrage.
    assert client_hold.post("/stoploss/state", headers=HO, json=photo()).status_code == 200
    assert svc.stoploss_engine.journal[-1].event == "EVALUATION" and not svc.stoploss_engine.persisted_latch.frozen
    assert "RESTORE_FAILED" not in (tmp_path / "stoploss.jsonl").read_text(encoding="utf-8")
    bad.unlink()  # réparation (ex. restauration de sauvegarde)
    _, svc2 = boot(tmp_path)
    assert not svc2.stoploss_engine.frozen and svc2.stoploss_engine.restore_hold is None
    assert GlobalLatch(frozen=True, since=NOW, cause="RESTORE_FAILED").frozen
