"""Régressions de la revue adverse, 2ᵉ passe (code) : chaque test échouait sur le code d'avant correctif.

* SEC-06 : mouvements de capital **uniquement** au registre de la propriétaire ; une photo ne les déclare
  jamais (faux retrait qui taisait le gel global) ; photo et relevés de trésorerie : jeton nommé.
* SEC-09 : dépublication protectrice effective avec le flux standard (catalogue du registre sans
  identifiant Shopify) : état publié inscrit après écriture vérifiée, sinon relu par handle.
* MOT-02 : aucun taux de change de l'appelant sur ``/sync/run`` ; taux de la propriétaire, sinon brouillon.
* E2E-07 : le critère « 20 synchronisations sans erreur » ne compte que des cycles réels et distincts.
* COH-02 : sans signature, **toutes** les valeurs décisives des règles au plus strict (TVA comprise).
* NEW-01 : un test de correction réussi n'est jamais déclaré par le jeton commun ni par l'ouvreur ; il
  cite un cycle PROPRE du journal persisté portant sur la cible de l'incident.
* NEW-02 : un gel de démarrage n'est jamais enregistré, même après une évaluation pendant le gel.
* NEW-03 : le tableau de bord suit l'authentification par jeton nommé et la restauration.
* MOT-18 (reste) : l'étoile polaire refuse une logistique supposée ; SEC-07 (reste) : le 409 du réarmement
  donne la valeur et l'empreinte à attester.
Données, jetons et montants FICTIFS.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
import test_api as A
import test_orchestration_f4 as F
import test_persistance_etats as P
import test_sync as S
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app, guard_rules
from pokeshop.audit import JsonlStateJournal
from pokeshop.catalogue_sync import SyncRunLog, SyncRunSummary
from pokeshop.incidents import IncidentCode, LogNotifier
from pokeshop.models import BasketLine, PricingParams, StockParams, VatMode
from pokeshop.northstar import NorthStarError, NorthStarLedger
from pokeshop.pricing import basket_contribution, decide_price
from pokeshop.rules import load_rules
from pokeshop.settings import load_settings, sha256_hex
from pokeshop.stoploss import (
    PRICE_RULE_KEYS_HANDLED,
    REFERENCE_PRICE_RULES,
    ProductMargin,
    StopLossEngine,
    StopLossState,
    hash_owner_token,
    load_stoploss_config,
)
from pokeshop.sync import ShopPublication, ShopPublicationBook

ROOT = Path(__file__).resolve().parents[1]


def body(resp: Any) -> Any:
    return json.loads(resp.content)


# =============================================================================== SEC-06


def test_sec06_photo_cannot_declare_capital_and_fake_withdrawal_no_longer_hides_the_loss(tmp_path: Path) -> None:
    """Apport réel 8 000, valeur nette 900 : un faux retrait de 7 100 dans la photo est refusé, le gel tombe."""
    client, svc = P.boot(tmp_path)  # apport FICTIF de 8 000 au registre de la propriétaire
    forged = P.photo("900")
    forged["capital_movements"] = [
        {"movement_id": "FICTIF_APPORT", "at": (P.NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
         "amount": "8000"},
        {"movement_id": "FICTIF_RETRAIT_FAUX", "at": (P.NOW - timedelta(days=1)).isoformat(), "kind": "WITHDRAWAL",
         "amount": "7100"},
    ]  # fmt: skip
    refused = client.post("/stoploss/state", headers=P.HF, json=forged)
    assert refused.status_code == 422 and "POST /capital/movements" in body(refused)["erreur"]
    assert svc.stoploss_state is None and svc.audit.events(action="stoploss.state.capital_movements_refused")
    honest = body(client.post("/stoploss/state", headers=P.HF, json=P.photo("900")))
    assert honest["status"]["global_frozen"] is True and svc.stoploss_engine.frozen
    assert [m.movement_id for m in svc.stoploss_state.capital_movements] == ["FICTIF_APPORT"]  # registre seul


def test_sec06_only_the_owner_register_changes_capital(tmp_path: Path) -> None:
    client, svc = P.boot(tmp_path)
    withdrawal = {"movement_id": "FICTIF_RETRAIT", "at": (P.NOW - timedelta(days=1)).isoformat(), "kind": "WITHDRAWAL",
                  "amount": "7100"}  # fmt: skip
    assert client.post("/capital/movements", headers=P.HF, json=withdrawal).status_code == 403  # agent : jamais
    assert client.post("/capital/movements", headers=P.H, json=withdrawal).status_code == 403  # jeton commun : jamais
    assert client.post("/capital/movements", headers=P.HO, json=withdrawal).status_code == 201  # propriétaire
    data = body(client.post("/stoploss/state", headers=P.HF, json=P.photo("900")))
    # Capital de référence 8 000 − 7 100 = 900 attesté par la propriétaire : valeur nette 900, aucune perte.
    assert data["status"]["global_frozen"] is False
    assert {m.movement_id for m in svc.stoploss_state.capital_movements} == {"FICTIF_APPORT", "FICTIF_RETRAIT"}


def test_sec06_treasury_values_need_a_named_token(tmp_path: Path) -> None:
    client, svc = P.boot(tmp_path)
    reading = {"as_of": P.NOW.isoformat(), "balance_chf": "2000", "source": "relevé FICTIF"}
    statement = {"as_of": P.NOW.isoformat(), "preorders_collected_chf": "0", "source": "déclaration FICTIVE"}
    for path, payload in (("/stoploss/state", P.photo()), ("/treasury/paypal-balance", reading),
                          ("/treasury/bank-balance", reading), ("/treasury/balance-items", statement)):
        common = client.post(path, headers=P.H, json=payload)
        assert common.status_code == 403 and "jeton nommé" in body(common)["erreur"], path
        assert client.post(path, headers=P.HF, json=payload).status_code == 200, path
    assert len(svc.audit.events(action="stoploss.state.common_token_refused")) == 1


# =============================================================================== SEC-09


def _quarantine_and_block(env: Any) -> None:
    env.incidents.open(code=IncidentCode.INC_01, product_key="FICTIF-P1", cause="prix publié anormal (test)",
                       actor="agent-12")  # fmt: skip
    env.state = S.healthy_state(env.now, products=(ProductMargin(product_key="FICTIF-P1", contribution_chf=D("3"),
                                                                 contribution_pct=D("0.03")),))  # fmt: skip
    env.gate.invalidate()


def test_sec09_registry_listing_published_then_quarantined_is_unpublished() -> None:
    env = S.Env()
    item = S.listing()  # fiche du registre (POST /catalog/items) : aucun identifiant Shopify
    first = S.item_for(env.cycle(S.context(item), dry_run=False))
    assert first.action == "PUBLISH_NEW_PRODUCT" and first.written and first.verified
    known = env.sync.publications.get("FICTIF-P1")
    assert known is not None and known.status == "ACTIVE" and known.shopify_product_id == "gid://shopify/Product/7"
    _quarantine_and_block(env)
    second = S.item_for(env.cycle(S.context(item), dry_run=False))
    assert second.plan_outcome == "UNPUBLISH" and second.action == "UNPUBLISH_PRODUCT" and second.written
    unpublish = env.shop.requests[-2]["variables"]  # productSet puis lecture de vérification
    assert unpublish["input"] == {"status": "DRAFT"} and unpublish["identifier"] == {"id": "gid://shopify/Product/7"}
    assert env.sync.publications.get("FICTIF-P1").status == "DRAFT"


def test_sec09_unknown_publication_is_read_from_the_shop_before_protective_unpublish() -> None:
    env = S.Env()
    item = S.listing()
    env.cycle(S.context(item), dry_run=False)
    env.sync.publications = ShopPublicationBook()  # registre perdu (autre instance) : l'état réel est relu
    _quarantine_and_block(env)
    second = S.item_for(env.cycle(S.context(item), dry_run=False))
    assert second.plan_outcome == "UNPUBLISH" and second.written
    assert any("productByIdentifier" in r["query"] and r["variables"]["identifier"].get("handle") for r in env.shop.requests)


def test_sec09_publication_book_is_persisted(tmp_path: Path) -> None:
    journal = JsonlStateJournal(tmp_path / "shop_publications.jsonl", stream="shop_publications")
    book = ShopPublicationBook(store=journal)
    item = ShopPublication(product_id="FICTIF-P1", shopify_product_id="gid://shopify/Product/7", status="ACTIVE",
                           handle="fictif-p1", run_id="SYNC-1", recorded_at=P.NOW)  # fmt: skip
    book.record(item)
    book.record(item)  # identique : aucune nouvelle ligne
    restored = ShopPublicationBook.restore(JsonlStateJournal(tmp_path / "shop_publications.jsonl", stream="shop_publications"))
    assert restored.get("FICTIF-P1") == item and len(journal.load()) == 1
    client, svc = P.boot(tmp_path)  # l'API relit le même journal au démarrage
    assert svc.sync.publications.get("FICTIF-P1") == item and svc.publications is svc.sync.publications


# =============================================================================== MOT-02


def test_mot02_sync_run_never_accepts_a_caller_fx_rate() -> None:
    client = TestClient(create_app(services=A.Services.build(A.make_settings(), clock=lambda: A.NOW,
                                                             notifier=LogNotifier())))  # fmt: skip
    base = {"supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv",
            "catalog": [{"product_id": "FICTIF-P1", "listing": A.LISTING}]}  # fmt: skip
    forged = {"fictif_grossiste_a": {"inbound_freight_alloc": "2.00", "customs_and_fees": "0", "import_vat": "0",
                                     "fx_rate_to_chf": "0.30", "fx_source": "agent", "fx_date": "2026-10-04"}}
    resp = client.post("/sync/run", headers=A.H, json={**base, "cost_inputs": forged})
    assert resp.status_code == 422 and "fx_rate_to_chf" in resp.text
    # Sans taux de la propriétaire : coût incomplet => brouillon, jamais un prix public.
    no_rate = body(client.post("/sync/run", headers=A.H, json={**base, "cost_inputs": A.BODY_COSTS}))
    p1 = next(i for i in no_rate["report"]["items"] if i["product_id"] == "FICTIF-P1")
    assert p1["decision_status"] == "DRAFT" and p1["plan_outcome"] == "NOT_SENT" and no_rate["cycle_status"] == "VIDE"
    assert client.post("/fx/rates", headers=A.HO, json=A.OWNER_FX).status_code == 200
    rated = body(client.post("/sync/run", headers=A.H, json={**base, "cost_inputs": A.BODY_COSTS}))
    p1 = next(i for i in rated["report"]["items"] if i["product_id"] == "FICTIF-P1")
    assert p1["decision_status"] == "OK" and p1["price_chf"] == "144.90"  # 95 EUR × 0.9375 + 2 : jamais 55.90
    real = client.post("/sync/run", headers=A.H, json={**base, "cost_inputs": A.BODY_COSTS, "dry_run": False})
    assert real.status_code == 409 and "simulation seulement" in body(real)["erreur"]


# =============================================================================== E2E-07


def test_e2e07_twenty_identical_fictif_cycles_never_meet_the_criterion(tmp_path: Path) -> None:
    client, _, _ = F.boot(tmp_path)
    F.register_catalog(client)
    for _ in range(20):
        data = body(client.post("/sync/run", headers=F.H, json=F.N8N_SYNC_BODY))
        assert data["cycle_status"] == "PROPRE" and data["counted_for_acceptance"] is False
    history = body(client.get("/sync/history", headers=F.H))
    assert history["consecutive_clean_runs"] == 0 and history["criterion_met"] is False
    assert {r["acceptance_exclusion"] for r in history["runs"]} == {"données FICTIVES"}


def _summary(i: int, **kw: Any) -> SyncRunSummary:
    base: dict[str, Any] = dict(
        run_id=f"r{i}", supplier_id="fournisseur_reel", dry_run=True, started_at=P.NOW, finished_at=P.NOW, status="PROPRE",
        offers_costed=3, items=3, catalog_source="registre", recorded_by="agent-07", fictif=False,
        source_sha256=f"{i:064x}", source_ts=P.NOW - timedelta(days=30 - i),
    )
    base.update(kw)
    return SyncRunSummary(**base)


def test_e2e07_only_real_distinct_cycles_count() -> None:
    log = SyncRunLog()
    for i in range(1, 4):
        log.record(_summary(i))
    log.record(_summary(10, source_sha256=f"{3:064x}"))  # même fichier rejoué
    log.record(_summary(11, source_ts=P.NOW - timedelta(days=27)))  # même horodatage de source (r3)
    log.record(_summary(12, catalog_source="corps"))  # catalogue fourni dans le corps
    log.record(_summary(13, fictif=True))  # données FICTIVES
    log.record(_summary(14, source_ts=None))  # source non datée
    log.record(_summary(15, status="VIDE", offers_costed=0))
    log.record(_summary(16, status="ANOMALIES", fictif=True, critical_errors=("x",)))  # anomalie FICTIVE : ignorée
    assert [r.run_id for r in log.counted_runs()] == ["r3", "r2", "r1"] and log.consecutive_clean_runs() == 3
    verdict = log.acceptance()
    assert verdict["r10"].startswith("source déjà vue") and verdict["r11"].startswith("source déjà vue")
    assert verdict["r12"].startswith("catalogue fourni dans le corps") and verdict["r13"] == "données FICTIVES"
    log.record(_summary(17, status="ANOMALIES", critical_errors=("prix ×10",)))  # anomalie réelle : remise à zéro
    log.record(_summary(18))
    assert log.consecutive_clean_runs() == 1
    legacy = SyncRunSummary.model_validate({k: v for k, v in _summary(19).model_dump(mode="json").items()
                                            if k not in ("fictif", "source_sha256", "source_ts", "product_ids")})
    assert legacy.acceptance_exclusion() == "données FICTIVES"  # ancien enregistrement : jamais compté


def test_e2e07_sync_report_clean_means_propre() -> None:
    env = S.Env()
    report = env.cycle(S.context(cost_inputs={}))  # aucun coût rendu calculé
    assert not report.critical_errors and report.offers_costed == 0 and report.empty and not report.clean
    assert S.consecutive_clean_runs([report]) == 0


# =============================================================================== COH-02


def test_coh02_unsigned_rules_force_every_decisive_value_including_vat(tmp_path: Path) -> None:
    raw = (ROOT / "config" / "pricing_rules.v1.yaml").read_text(encoding="utf-8")
    low = tmp_path / "pricing_rules.v1.yaml"
    low.write_text(raw.replace('vat_rate_sales: "0.081"', 'vat_rate_sales: "0.001"'), encoding="utf-8")
    guarded, state, tightened = guard_rules(load_rules(low, VatMode.EFFECTIVE), None)
    assert state == "UNSIGNED_STRICTEST" and guarded.pricing.vat_rate_sales == D("0.081")
    assert any("vat_rate_sales" in t for t in tightened)
    reference = guard_rules(load_rules(None, VatMode.EFFECTIVE), None)[0]
    assert decide_price(D("100"), guarded.pricing).recommended_price == decide_price(D("100"), reference.pricing).recommended_price
    lowest = next(
        D(c) / 100 for c in range(12000, 16000, 10)
        if decide_price(D("100"), guarded.pricing, candidate_price=D(c) / 100).status.value in ("OK", "REVIEW")
    )  # fmt: skip
    assert lowest == D("138.6")  # comme la référence : jamais 128.00 (4,99 % réels)
    not_registered = guard_rules(load_rules(None, VatMode.NOT_REGISTERED), None)[0]
    assert not_registered.pricing.vat_rate_sales == 0  # non assujetti : t = 0 (BP §4)


def test_coh02_no_decisive_rule_key_escapes_the_strictest_rules() -> None:
    pricing_keys = set(PricingParams.model_fields) - PRICE_RULE_KEYS_HANDLED
    assert pricing_keys == set(REFERENCE_PRICE_RULES["pricing"]), pricing_keys ^ set(REFERENCE_PRICE_RULES["pricing"])
    assert set(StockParams.model_fields) == set(REFERENCE_PRICE_RULES["stock"])
    loose = StockParams(reorder_coverage_days=180, future_skew_minutes=60)
    rules = load_rules()
    guarded = guard_rules(rules.replace(stock=loose), None)[0]
    assert guarded.stock.reorder_coverage_days == 14 and guarded.stock.future_skew_minutes == 5


# =============================================================================== NEW-01


def _incident_boot(tmp_path: Path) -> tuple[TestClient, Services, dict[str, str]]:
    ops, qa = "FICTIF-jeton-agent-07-integrations-01", "FICTIF-jeton-agent-12-qa-00000001"
    env = {"POKESHOP_API_TOKEN_SHA256": sha256_hex(A.API_TOKEN), "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(A.OWNER_TOKEN),
           "POKESHOP_STATE_DIR": str(tmp_path),
           "POKESHOP_AGENT_TOKENS_SHA256": f"agent-07-integrations:{sha256_hex(ops)},agent-12-qa:{sha256_hex(qa)}"}  # fmt: skip
    svc = Services.build(load_settings(env), clock=lambda: A.NOW, notifier=LogNotifier())
    return TestClient(create_app(services=svc)), svc, {"ops": ops, "qa": qa}


def _run(client: TestClient, product_id: str = "FICTIF-P1", costs: bool = True) -> str:
    listing = dict(A.LISTING, product_key=product_id)
    payload: dict[str, Any] = {"supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv",
                               "catalog": [{"product_id": product_id, "listing": listing}]}  # fmt: skip
    if costs:
        payload["cost_inputs"] = A.BODY_COSTS
    return body(client.post("/sync/run", headers=A.H, json=payload))["report"]["run_id"]


def test_new01_resume_test_needs_a_named_token_other_than_the_opener_and_a_relevant_clean_run(tmp_path: Path) -> None:
    client, svc, tok = _incident_boot(tmp_path)
    assert client.post("/fx/rates", headers=A.HO, json=A.OWNER_FX).status_code == 200
    ops, qa = {API_TOKEN_HEADER: tok["ops"]}, {API_TOKEN_HEADER: tok["qa"]}
    inc = body(client.post("/incidents", headers=ops, json={"code": "INC-01", "product_key": "FICTIF-P9",
                                                            "cause": "prix publié anormal (FICTIF)"}))["incident"]  # fmt: skip
    url = f"/incidents/{inc['incident_id']}/test"
    unrelated = _run(client, "FICTIF-P1")  # cycle PROPRE, mais sur une autre référence
    common = client.post(url, headers=A.H, json={"test_ref": unrelated, "passed": True, "actor": "agent-07"})
    assert common.status_code == 403 and "jeton commun" in body(common)["erreur"]
    own = client.post(url, headers=ops, json={"test_ref": unrelated, "passed": True, "actor": "x1"})
    assert own.status_code == 403 and "auto-attesté" in body(own)["erreur"]
    other = client.post(url, headers=qa, json={"test_ref": unrelated, "passed": True, "actor": "x1"})
    assert other.status_code == 409 and "FICTIF-P9" in body(other)["erreur"]
    empty = client.post(url, headers=qa, json={"test_ref": _run(client, "FICTIF-P9", costs=False), "passed": True,
                                               "actor": "x1"})  # fmt: skip
    assert empty.status_code == 409 and "PROPRE" in body(empty)["erreur"]
    assert svc.incidents.is_quarantined("FICTIF-P9")
    target = _run(client, "FICTIF-P9")
    # Redémarrage : la preuve est lue dans le journal persisté des cycles, pas dans l'historique en mémoire.
    client2, svc2, _ = _incident_boot(tmp_path)
    assert svc2.sync.history == []
    ok = client2.post(url, headers=qa, json={"test_ref": target, "passed": True, "actor": "x1"})
    assert ok.status_code == 200 and body(ok)["incident"]["test_passed"] is True
    resumed = client2.post(f"/incidents/{inc['incident_id']}/resume", headers=A.H, json={"actor": "agent-07"})
    assert resumed.status_code == 200 and not svc2.incidents.is_quarantined("FICTIF-P9")


def test_new01_failed_test_can_still_be_reported_by_anyone(tmp_path: Path) -> None:
    client, _, _ = _incident_boot(tmp_path)
    inc = body(client.post("/incidents", headers=A.H, json={"code": "INC-01", "product_key": "FICTIF-P9",
                                                            "cause": "prix publié anormal (FICTIF)"}))["incident"]  # fmt: skip
    failed = client.post(f"/incidents/{inc['incident_id']}/test", headers=A.H,
                         json={"test_ref": "contrôle FICTIF", "passed": False, "actor": "agent-07"})  # fmt: skip
    assert failed.status_code == 200 and body(failed)["incident"]["test_passed"] is False


# =============================================================================== NEW-02


def test_new02_startup_hold_is_never_written_even_after_an_evaluation(tmp_path: Path) -> None:
    client, _ = P.boot(tmp_path)
    assert client.post("/stoploss/state", headers=P.HF, json=P.photo()).status_code == 200
    bad = tmp_path / "northstar.jsonl"
    bad.write_text("garbage\n", encoding="utf-8")
    client2, svc2 = P.boot(tmp_path)
    assert svc2.stoploss_engine.latch.cause == "RESTORE_FAILED" and svc2.stoploss_engine.frozen
    during = client2.post("/stoploss/state", headers=P.HF, json=P.photo())  # workflow 07 continue de déposer
    assert during.status_code == 200 and svc2.stoploss_engine.journal[-1].event == "EVALUATION"
    assert svc2.stoploss_engine.persisted_latch.frozen is False
    lines = [json.loads(line) for line in (tmp_path / "stoploss.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("RESTORE_FAILED" not in json.dumps(line) and "CONFIG_UNSIGNED" not in json.dumps(line) for line in lines)
    bad.unlink()  # réparation
    _, svc3 = P.boot(tmp_path)
    assert not svc3.stoploss_engine.frozen and svc3.stoploss_engine.restore_hold is None


def test_new02_real_trip_or_manual_freeze_during_the_hold_is_kept() -> None:
    journal = P.InMemoryStateJournal("stoploss")
    engine = StopLossEngine(P.CONFIG, owner_token_sha256=hash_owner_token(P.OWNER_TOKEN), store=journal)
    engine.hold_config_unsigned("règles modifiées sans signature (FICTIF)", P.NOW)
    engine.evaluate(P.state("8000"), P.NOW)  # évaluation saine pendant le gel : rien de gelé n'est écrit
    assert engine.frozen and engine.persisted_latch.frozen is False
    engine.evaluate(P.state("4000"), P.NOW)  # perte réelle de 50 % pendant le gel : enregistrée
    assert engine.persisted_latch.cause == "THRESHOLD"
    restored = StopLossEngine.restore(P.CONFIG, store=journal, owner_token_sha256=hash_owner_token(P.OWNER_TOKEN))
    assert restored.frozen and restored.latch.cause == "THRESHOLD"
    other = StopLossEngine(P.CONFIG, owner_token_sha256=hash_owner_token(P.OWNER_TOKEN), store=P.InMemoryStateJournal("s"))
    other.hold_restore_failed("journal illisible (FICTIF)", P.NOW)
    other.freeze("agent-12", "débit inconnu FICTIF", P.NOW)
    assert other.persisted_latch.cause == "MANUAL" and other.latch.cause == "MANUAL"


# =============================================================================== NEW-03


def test_new03_dashboard_accepts_named_tokens_and_reports_unreadable_journals(tmp_path: Path) -> None:
    client, _ = P.boot(tmp_path)
    assert client.get("/dashboard/weekly", headers=P.HF).status_code == 200  # jeton nommé admis
    named_only = load_settings({"POKESHOP_AGENT_TOKENS_SHA256": f"agent-05-finance:{sha256_hex(P.FINANCE_TOKEN)}",
                                "POKESHOP_STATE_DIR": str(tmp_path / "autre")})  # fmt: skip
    only = TestClient(create_app(services=Services.build(named_only, clock=P.Clock(), notifier=LogNotifier())))
    assert only.get("/dashboard/daily", headers=P.HF).status_code == 200  # un jeton par agent, sans jeton commun
    assert only.get("/dashboard/daily", headers=P.H).status_code == 401
    entry = {"entries": [{"entry_id": "FICTIF-1", "at": P.NOW.isoformat(), "post": "NET_SALES", "amount": "184.92",
                          "order_id": "FICTIF-O1"}]}  # fmt: skip
    assert client.post("/northstar/entries", headers=P.H, json=entry).status_code == 200
    (tmp_path / "northstar.jsonl").write_text("garbage\n", encoding="utf-8")
    client2, _ = P.boot(tmp_path)
    assert client2.get("/northstar", headers=P.H).status_code == 503
    report = body(client2.get("/dashboard/weekly", headers=P.H))["report"]
    north = report["north_star"]
    assert north["available"] is False and north["status"] == "CRITIQUE" and "non relu" in north["reason"]
    assert "Aucune écriture" not in json.dumps(report, ensure_ascii=False)
    assert any("northstar" in item for item in report["unavailable"])


# =============================================================================== restes MOT-18 et SEC-07


def test_mot18_northstar_refuses_an_assumed_logistics_cost() -> None:
    params = load_rules().pricing
    line = [BasketLine(sku="FICTIF_DISPLAY", qty=1, unit_price_ttc=D("199.90"), unit_cost=D("1"))]
    for basket in (basket_contribution(line, params, D("7.00")),  # port facturé, coût réel inconnu : hypothèse L
                   basket_contribution(line, params, D("0"))):  # port offert sans coût réel
        assert {"SHIPPING_COST_ASSUMED", "SHIPPING_COST_UNKNOWN"} & {getattr(r, "value", r) for r in basket.reasons}
        with pytest.raises(NorthStarError, match="shipping_cost_actual"):
            NorthStarLedger().record_basket("FICTIF-O1", P.NOW, basket)
    real = basket_contribution(line, params, D("0"), shipping_cost_actual=D("3.00"))
    assert NorthStarLedger().record_basket("FICTIF-O2", P.NOW, real)


def test_sec07_rearm_without_reference_returns_the_value_and_the_photo_fingerprint(tmp_path: Path) -> None:
    client, svc = P.boot(tmp_path)
    assert client.post("/stoploss/state", headers=P.HF, json=P.photo()).status_code == 200
    client.post("/stoploss/freeze", headers=P.H, json={"actor": "agent-12", "reason": "gel de test FICTIF"})
    resp = client.post("/stoploss/rearm", headers=P.HO, json={"reason": "valeur nette examinée (FICTIF)"})
    data = body(resp)
    assert resp.status_code == 409 and data["rearm_reference"]["net_worth_chf"] == "8000"
    assert len(data["rearm_reference"]["photo_sha256"]) == 64 and svc.stoploss_engine.frozen


# Garde-fou : ce fichier n'utilise que des modèles du moteur (aucun état partagé entre tests).
assert StopLossState and OWNER_TOKEN_HEADER and load_stoploss_config


# =============================================================================== COH-01 (livrables finance)


def test_coh01_finance_deliverables_use_the_single_840_chf_definition() -> None:
    from pokeshop import forecast as fc

    assert fc.north_star([fc.NorthStarWeek(1, D(0), D(0), D(0), D(0), D(0), D(0), D(0), D(840))]).frozen  # défaut = 840
    finance = ROOT / "docs" / "03-finance"
    readme = (finance / "README.md").read_text(encoding="utf-8")
    note = (finance / "NOTE_VERIFICATION_BP.md").read_text(encoding="utf-8")
    assert "**840 CHF**" in readme and "−840 CHF" in readme and "gel à −1 600 CHF" not in readme
    assert "**840 CHF**" in note and "**semaine 13**" in note and "**gel en semaine 28**" not in note
    assert "capital engagé = 8 000 CHF (seuil 1 600 CHF)" not in note
    generator = (finance / "generer_classeurs.py").read_text(encoding="utf-8")
    assert "(1-0.7)*" in generator and "point zéro" in generator  # Perte_max = 20 % × référence du point zéro
