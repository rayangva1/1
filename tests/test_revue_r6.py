"""Régressions de la revue adverse, 6ᵉ passe (moteur) : un test par point, échouant avant correctif.

* R5-NEW-01 : la contribution d'une commande attribuée à une campagne est **dérivée des registres du moteur**
  (ventes nettes − avoirs − frais − logistique réelle − coût des ventes du registre de coûts), jamais la valeur de
  conversion transmise par le connecteur ; coût des ventes inconnu : 0 (fermé), re-dérivé à chaque photo.
* R5-NEW-02 : une commande payée avec un ancien SKU après une correction du catalogue n'est jamais perdue (alias de
  SKU historiques relus du journal du catalogue, résolution vers la clé canonique) ; SKU inconnu ou ambigu : ligne
  non rattachée (coût des ventes en attente, incomplet), rattachée par la propriétaire.
* R5C-DOC-05 (n8n) : un workflow qui reçoit un en-tête secret (passerelles, notification du moteur) ne conserve ni
  exécution réussie ni exécution manuelle ; les exécutions en échec sont purgées par n8n (7 jours).
* R5C-DOC-07 (n8n, moteur, compose) : le webhook moteur -> 04 est authentifié par un secret dédié
  (``POKESHOP_N8N_WEBHOOK_SECRET``, en-tête ``X-Pokeshop-Notify``) ; sans lui, rien n'est envoyé et c'est signalé.
* R5C-DOC-09 (moteur) : chaque empreinte reste fermée à sa manière (mandat inactif ; stop-loss non chargé, 503 ;
  règles gelées ``CONFIG_UNSIGNED``) et la docstring de l'API le dit empreinte par empreinte.
Données, jetons et montants FICTIFS ; bases PostgreSQL : aucune (journaux en fichiers par test, tmp_path).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import jetons_roles as JR
import pokeshop.api as API
import pytest
import test_gouvernance_f2 as G
import test_n8n_workflows as N
import test_orchestration_f4 as F
import test_revue_r3 as R3
import test_revue_r5 as R5
import yaml
from pokeshop.autonomy import GateReason, WriteAction
from pokeshop.incidents import NOTIFY_SECRET_HEADER
from pokeshop.mandate import SpendReason
from pokeshop.northstar import UNRESOLVED_KEY_PREFIX, CostMovement, CostRegister
from pokeshop.rules import load_rules
from pokeshop.stoploss import DEFAULT_STOPLOSS_PATH, AttributedOrder, stoploss_fingerprint
from pokeshop.stoploss_snapshot import derive_attributed

NOW = F.NOW
H = F.H
OWNER = R5.OWNER
SKU = R5.SKU
NEW_SKU = "DSP-FICTIF_ALPHA-FR-V2"
CAMPAIGN = "FICTIF-CAMP-1"


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def catalog(client: Any, listing: dict[str, Any] | None = None, pid: str = "FICTIF-P1") -> Any:
    item = {"product_id": pid, "listing": listing or F.LISTING,
            "supplier_links": [{"supplier_id": "fictif_grossiste_a", "supplier_sku": "FICTIF-SKU-1"}]}  # fmt: skip
    return client.post("/catalog/items", headers=JR.HCAT, json={"items": [item]})


def shop(tmp_path: Path, *, valued: bool = True) -> tuple[Any, Any]:
    """Boutique FICTIVE : cash, fiche P1, frais de la propriétaire, cycle 01, 6 displays reçus (au coût 91.06)."""
    client, svc, _ = F.boot(tmp_path)
    R3.cash_registers(client, paypal="1000", bank="3000")
    assert catalog(client).status_code == 200
    R5.owner_fees_and_cycle(client)
    R5.receive(client)
    if valued:
        assert client.post("/costs/movements", headers=JR.HF, json=R5.receipt("91.06")).status_code == 200
    return client, svc


def attribute(client: Any, order_id: str, declared: str, spend: str = "100.00") -> Any:
    paid = (NOW - timedelta(hours=1)).astimezone(F.TZ)
    ads = {"ad_spends": [{"campaign_id": CAMPAIGN, "day": paid.date().isoformat(), "amount": spend}],
           "attributed_orders": [{"order_id": order_id, "campaign_id": CAMPAIGN, "paid_at": paid.isoformat(),
                                  "status": "PAID", "contribution_before_acquisition": declared}]}  # fmt: skip
    resp = client.post("/ads/activity", headers=JR.HADS, json=ads)
    assert resp.status_code == 200, resp.text
    return resp


def photo(client: Any) -> dict[str, Any]:
    resp = client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    assert resp.status_code == 200, resp.text
    return body(resp)


def kept(svc: Any) -> list[D]:
    return [o.contribution_before_acquisition for o in svc.stoploss_state.attributed_orders]


# ================================================================= R5-NEW-01 : contribution attribuée dérivée


def test_r5new01_declared_conversion_value_never_hides_the_campaign_cut(tmp_path: Path) -> None:
    """PoC v4b : 130.90 déclarés (ventes − frais − port, sans coût produit) masquaient la coupure de FICTIF-CAMP-1."""
    for declared in ("130.90", "39.84", "500.00"):
        client, svc = shop(tmp_path / declared)
        assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
        attribute(client, "2001", declared)
        # Contribution réelle : 142.50 − 4.20 − 7.40 − 91.06 (coût des ventes dérivé par le moteur) = 39.84.
        assert [o.contribution_before_acquisition for o in svc.ads.window(NOW.date() - timedelta(days=30))[1]] == [D("39.84")]
        status = photo(client)["status"]
        assert status["cut_campaigns"] == [CAMPAIGN], declared  # CAC 100 > 39.84
        assert kept(svc) == [D("39.84")]
    # Parcours légitime : une valeur déclarée plus prudente reste retenue ; dépense sous la contribution : pas de coupure.
    client, svc = shop(tmp_path / "prudent")
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
    attribute(client, "2001", "20.00", spend="15.00")
    assert photo(client)["status"]["cut_campaigns"] == [] and kept(svc) == [D("20.00")]


def test_r5new01_unknown_cost_of_sales_counts_zero_then_is_re_derived(tmp_path: Path) -> None:
    """Coût des ventes en attente : contribution 0 (fermé) ; le coût inscrit, la photo suivante re-dérive (jamais figé)."""
    client, svc = shop(tmp_path, valued=False)
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001"))
    assert created.status_code == 201 and body(created)["cost_of_sales_pending"] == {"FICTIF-P1": 1}
    attribute(client, "2001", "130.90", spend="30.00")
    first = photo(client)
    assert first["sources"]["attributed_orders_cost_of_sales_unknown"] == ["2001"] and kept(svc) == [D("0")]
    assert first["status"]["cut_campaigns"] == [CAMPAIGN] and first["sources"]["complete"] is False
    assert client.post("/costs/movements", headers=JR.HF, json=R5.receipt("91.06")).status_code == 200
    second = photo(client)
    assert second["sources"]["attributed_orders_cost_of_sales_unknown"] == [] and kept(svc) == [D("39.84")]
    assert second["status"]["cut_campaigns"] == []  # 30 < 39.84 : la campagne n'est plus coupée à tort


def test_r5new01_refund_after_attribution_is_never_a_paid_order(tmp_path: Path) -> None:
    client, svc = shop(tmp_path)
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("2001")).status_code == 201
    attribute(client, "2001", "39.84", spend="25.00")  # ≥ 20 CHF (seuil pour juger une campagne sans commande)
    assert photo(client)["status"]["cut_campaigns"] == []
    full = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50"}
    assert client.post("/orders/2001/refunds", headers=JR.HORDERS, json=full).status_code == 201
    assert photo(client)["status"]["cut_campaigns"] == [CAMPAIGN]  # plus aucune commande payée nette
    assert [o.status for o in svc.stoploss_state.attributed_orders] == ["REFUNDED"]


def test_r5new01_without_the_order_register_an_attributed_order_counts_zero() -> None:
    paid = AttributedOrder(order_id="2001", campaign_id=CAMPAIGN, paid_at=NOW, contribution_before_acquisition=D("130.90"))
    orders, unknown = derive_attributed([paid], None, None)
    assert [o.contribution_before_acquisition for o in orders] == [D("0")] and unknown == ("2001",)


def test_r5new01_order_cost_of_sales_follows_the_return_movement_not_its_free_reference() -> None:
    """Deux retours de même ``ref`` sur deux commandes : chacun reste rattaché à sa vente (sale_ref)."""
    costs = CostRegister()
    at = NOW - timedelta(days=1)
    for m in (
        CostMovement(kind="RECEIPT", product_key="FICTIF-P1", at=at, ref="LOT-1", qty=10, unit_cost=D("10")),
        CostMovement(kind="ISSUE", product_key="FICTIF-P1", at=at, ref="order:A", qty=2),
        CostMovement(kind="ISSUE", product_key="FICTIF-P1", at=at, ref="order:B", qty=2),
        CostMovement(kind="RETURN", product_key="FICTIF-P1", at=NOW, ref="RET", qty=1, sale_ref="order:A"),
        CostMovement(kind="RETURN", product_key="FICTIF-P1", at=NOW, ref="RET", qty=1, sale_ref="order:B"),
    ):
        costs.apply(m)
    assert costs.order_cogs("order:A") == D("10.00") and costs.order_cogs("order:B") == D("10.00")
    assert costs.order_cogs("order:C") == D("0")


# ================================================================= R5-NEW-02 : ancien SKU après correction


def test_r5new02_paid_order_with_the_sku_before_a_catalogue_fix_is_recorded_on_its_key(tmp_path: Path) -> None:
    """PoC v7 : SKU corrigé par le catalogue, commande payée avant avec l'ancien SKU => 409 pour tous, vente perdue."""
    client, svc = shop(tmp_path)
    assert catalog(client, {**F.LISTING, "public_sku": NEW_SKU}).status_code == 200
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("5001"))
    assert created.status_code == 201 and body(created)["incomplete"] is False and body(created)["unresolved_lines"] == {}
    assert svc.orders.get("5001").lines[0].product_key == "FICTIF-P1"
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5  # sortie au CMP dérivée : l'unité vendue quitte le stock
    northstar = body(client.get("/northstar", headers=H))
    assert northstar["cumulative"] == "39.84" and northstar["incomplete"] is False
    assert client.post("/orders/shipped", headers=OWNER, json=R5.order("5001")).status_code == 200  # même commande
    # Le nouveau SKU désigne la même clé ; l'historique survit au redémarrage (journal du catalogue).
    client2, svc2, _ = F.boot(tmp_path)
    assert svc2.catalog.sku_holders(SKU) == ("FICTIF-P1",)
    later = {**R5.order("5002"), "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client2.post("/orders/shipped", headers=JR.HORDERS, json=later).status_code == 201
    renamed = {**R5.order("5003"), "lines": [{"public_sku": NEW_SKU, "qty": 1}]}
    assert client2.post("/orders/shipped", headers=JR.HORDERS, json=renamed).status_code == 201
    assert svc2.costs.ledger("FICTIF-P1").qty_on_hand == 3 and svc2.orders.pending_cogs() == {}
    # Attribution pub : la commande n'est plus mise de côté.
    assert body(attribute(client2, "5001", "39.84"))["attributed_orders_set_aside"] == {}


def test_r5new02_unknown_sku_is_recorded_unresolved_and_attached_by_the_owner(tmp_path: Path) -> None:
    client, svc = shop(tmp_path)
    paid = {**R5.order("5001"), "lines": [{"public_sku": "ETB-INCONNU-FR", "qty": 1}]}
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=paid)
    assert created.status_code == 201 and body(created)["incomplete"] is True
    assert body(created)["unresolved_lines"] == {"ETB-INCONNU-FR": []}
    assert body(created)["cost_of_sales_pending"] == {f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR": 1}
    northstar = body(client.get("/northstar", headers=H))
    assert northstar["incomplete"] is True and "lines/resolve" in northstar["derivation_errors"]["commande 5001"]
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 6  # aucune sortie devinée
    attribute(client, "5001", "39.84", spend="10.00")
    snap = photo(client)
    assert snap["sources"]["complete"] is False and snap["sources"]["attributed_orders_cost_of_sales_unknown"] == ["5001"]
    # Rattachement : propriétaire seule, fiche canonique connue.
    resolve = {"public_sku": "ETB-INCONNU-FR", "product_key": "FICTIF-P1"}
    for headers in (JR.HORDERS, JR.HF, JR.HCAT, H):
        assert client.post("/orders/5001/lines/resolve", headers=headers, json=resolve).status_code == 403
    unknown_key = client.post("/orders/5001/lines/resolve", headers=OWNER, json={**resolve, "product_key": "FICTIF-P9"})
    assert unknown_key.status_code == 409
    reserved = {**resolve, "product_key": f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR"}
    assert client.post("/orders/5001/lines/resolve", headers=OWNER, json=reserved).status_code == 409
    done = client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve)
    assert done.status_code == 200 and body(done)["created"] is True and body(done)["incomplete"] is False
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5 and body(client.get("/northstar", headers=H))["incomplete"] is False
    again = client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve)
    assert again.status_code == 200 and body(again)["created"] is False
    # Webhook rejoué par n8n-02 après le rattachement : même commande (idempotente), rien de neuf.
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=paid).status_code == 200
    assert photo(client)["sources"]["attributed_orders_cost_of_sales_unknown"] == [] and kept(svc) == [D("39.84")]
    # Redémarrage : rattachement relu du journal des commandes, aucune sortie en double.
    _, svc2, _ = F.boot(tmp_path)
    assert svc2.orders.get("5001").lines[0].product_key == "FICTIF-P1"
    assert svc2.orders.pending_cogs() == {} and svc2.costs.ledger("FICTIF-P1").qty_on_hand == 5


def test_r5new02_sku_carried_by_two_keys_is_ambiguous_never_guessed(tmp_path: Path) -> None:
    """SKU de P1 corrigé puis repris par P2 : une commande à ce SKU n'est attribuée à aucune des deux d'office."""
    client, svc = shop(tmp_path)
    assert catalog(client, {**F.LISTING, "public_sku": NEW_SKU}).status_code == 200
    p2 = {**F.LISTING, "product_key": "FICTIF-P2",
          "identity": {**F.IDENTITY, "gtin": "2000000001029", "content": "18 BOOSTERS"}}  # fmt: skip
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [{"product_id": "FICTIF-P2", "listing": p2}]}).status_code == 200
    created = client.post("/orders/shipped", headers=JR.HORDERS, json=R5.order("5001"))
    assert created.status_code == 201 and body(created)["unresolved_lines"] == {SKU: ["FICTIF-P1", "FICTIF-P2"]}
    assert body(created)["incomplete"] is True and svc.costs.ledger("FICTIF-P1").qty_on_hand == 6
    # Avoir avec retour sur la ligne non rattachée : rattaché à la ligne de la commande, puis à la clé choisie.
    refund = {"refund_id": "FICTIF-AV-1", "at": NOW.isoformat(), "net_sales_ht": "142.50", "lines": [{"public_sku": SKU, "qty": 1}]}
    assert client.post("/orders/5001/refunds", headers=JR.HOPS, json=refund).status_code == 201
    resolve = {"public_sku": SKU, "product_key": "FICTIF-P1"}
    assert client.post("/orders/5001/lines/resolve", headers=OWNER, json=resolve).status_code == 200
    assert svc.orders.refund("FICTIF-AV-1").lines[0].product_key == "FICTIF-P1"
    other = client.post("/orders/5001/lines/resolve", headers=OWNER, json={**resolve, "product_key": "FICTIF-P2"})
    assert other.status_code == 409 and "déjà rattachée" in body(other)["erreur"]
    assert svc.costs.ledger("FICTIF-P1").qty_on_hand == 5 and svc.orders.pending_cogs() == {}


def test_r5new02_catalogue_never_takes_the_reserved_key_of_unresolved_lines(tmp_path: Path) -> None:
    client, _, _ = F.boot(tmp_path)
    key = f"{UNRESOLVED_KEY_PREFIX}ETB-INCONNU-FR"
    resp = client.post("/catalog/items", headers=JR.HCAT,
                       json={"items": [{"product_id": key, "listing": {**F.LISTING, "product_key": key}}]})  # fmt: skip
    assert resp.status_code in (409, 422) and "réservée" in body(resp)["erreur"]


# ================================================================ R5C-DOC-05 : secrets reçus jamais conservés

COMPOSE = yaml.safe_load((N.ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
ORCH_README = (N.ROOT / "orchestration" / "README.md").read_text(encoding="utf-8")


def secret_hooks(wf: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook" and n["parameters"]["authentication"] == "headerAuth"]


def test_r5cdoc05_workflows_receiving_a_secret_header_keep_no_successful_or_manual_execution() -> None:
    """n8n garde la sortie du nœud webhook (en-têtes compris) dans toute exécution conservée : 03, 04, 06 et 08 n'en
    conservent aucune réussie ni manuelle ; le générateur l'impose à tout nouveau webhook authentifié."""
    carrying = set()
    for name, wf in N.WORKFLOWS.items():
        if secret_hooks(wf):
            carrying.add(name[:2])
            settings = wf["settings"]
            assert settings["saveDataSuccessExecution"] == "none", name
            assert settings["saveManualExecutions"] is False and settings["saveExecutionProgress"] is False, name
    assert carrying == {"03", "04", "06", "08"}
    wf = N.GEN.Workflow("pkshpTestR6Gate1", "Test", "99_test.json", api_cred="api_08", keep_success_data=True)
    N.GEN.webhook(wf, "Passerelle de test", (0, 0), "test-r6", gateway="gateway_03")
    exported = wf.export()["settings"]
    assert exported["saveDataSuccessExecution"] == "none" and exported["saveManualExecutions"] is False
    with pytest.raises(ValueError, match="sans credential propre"):
        N.GEN.webhook(wf, "Webhook sans secret propre", (0, 1), "test-r6b", gateway="api_08")
    env = COMPOSE["services"]["n8n"]["environment"]
    assert env["EXECUTIONS_DATA_PRUNE"] == "true" and 0 < int(env["EXECUTIONS_DATA_MAX_AGE"]) <= 168
    assert "ni exécution réussie ni exécution manuelle" in ORCH_README and "**changer le secret**" in ORCH_README


# ================================================================ R5C-DOC-07 : webhook moteur -> 04 authentifié


def test_r5cdoc07_engine_to_04_webhook_needs_the_engine_secret_and_exposure_is_written_exactly() -> None:
    by = N.nodes(N.WORKFLOWS["04_incident.json"])
    hook = by["Notification d’incident du moteur"]
    key = N.GEN.ENGINE_NOTIFY_CREDENTIAL
    assert hook["parameters"]["authentication"] == "headerAuth"
    assert hook["credentials"]["httpHeaderAuth"]["id"] == N.GEN.CREDENTIALS[key][1]
    assert N.GEN.ENGINE_NOTIFY_HEADER == NOTIFY_SECRET_HEADER == "X-Pokeshop-Notify"
    assert N.GEN.INBOUND_SECRET_HOLDERS[key] == "moteur" and key not in N.GEN.GATEWAY_HOLDERS
    api_env, n8n_env = COMPOSE["services"]["api"]["environment"], COMPOSE["services"]["n8n"]["environment"]
    assert api_env["POKESHOP_N8N_WEBHOOK_SECRET"] == "${POKESHOP_N8N_WEBHOOK_SECRET:-}"
    assert not any("WEBHOOK_SECRET" in str(v) or k.startswith("POKESHOP_") for k, v in n8n_env.items())
    assert "127.0.0.1:5678:5678" in COMPOSE["services"]["n8n"]["ports"]  # boucle locale de l'hôte : d'où le secret
    compose_text = (N.ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "aucune exposition réseau)." not in compose_text and "par TOUT processus de l'hôte" in compose_text
    row = next(line for line in ORCH_README.splitlines() if line.startswith(f"| `{N.GEN.CREDENTIALS[key][2]}`"))
    assert "`X-Pokeshop-Notify`" in row and "POKESHOP_N8N_WEBHOOK_SECRET" in row
    assert "webhook limité au réseau interne docker" not in ORCH_README and "boucle locale de l'hôte" in ORCH_README


@pytest.mark.skipif(N.NODE_BIN is None, reason="node absent : code non exécuté")
def test_r5cdoc07_digest_names_a_missing_secret_and_an_undelivered_alert(tmp_path: Path) -> None:
    js = N.nodes(N.WORKFLOWS["05_digest_quotidien.json"])["Composer le digest (étoile polaire en premier)"]["parameters"]["jsCode"]
    notif = {"webhook_configured": True, "webhook_dry_run": False, "webhook_secret_configured": False,
             "real_time_alerts": False, "last_delivery": None}  # fmt: skip
    ctx = {
        "Étoile polaire (GET /northstar)": {"cumulative": "0.00", "rows": []},
        "État du stop-loss (GET /stoploss/status)": {"available": False, "error": "aucune photo", "triggers": []},
        "Tableau de bord du jour (GET /dashboard/daily)": {"report": {}},
        "Cycles de synchronisation (GET /sync/history)": {"consecutive_clean_runs": 0, "target": 20, "runs": []},
        "État du moteur (GET /health)": {"notifications": notif, "persistence": {"unreadable": []}},
    }
    text = N.run_js(tmp_path, js, [{}], ctx)[0][0]["texte"]
    assert "ALERTES TEMPS RÉEL INACTIVES (secret des notifications absent : POKESHOP_N8N_WEBHOOK_SECRET)" in text
    notif.update(webhook_secret_configured=True, real_time_alerts=True,
                 last_delivery={"delivered": False, "dry_run": False, "detail": "webhook-n8n : non livré (HTTP 403)"})
    text = N.run_js(tmp_path, js, [{}], ctx)[0][0]["texte"]
    assert "DERNIÈRE ALERTE NON LIVRÉE À 04 (webhook-n8n : non livré (HTTP 403))" in text
    notif["last_delivery"] = {"delivered": True, "dry_run": False, "detail": "webhook-n8n : livré"}
    text = N.run_js(tmp_path, js, [{}], ctx)[0][0]["texte"]
    assert "NON LIVRÉE" not in text and "ALERTES TEMPS RÉEL INACTIVES" not in text


# ================================================================ R5C-DOC-09 : trois empreintes, trois fermetures


def test_r5cdoc09_each_fingerprint_fails_closed_in_its_own_documented_way(tmp_path: Path) -> None:
    """Mandat différent => mandat inactif (pas de gel) ; seuils différents => stop-loss non chargé (503, aucune
    écriture réelle) ; règles différentes => gel CONFIG_UNSIGNED. Choix gardé (revue R6) : chacun est fermé sur son
    périmètre ; un gel global pour le mandat bloquerait des parcours sans rapport (commandes, réceptions) alors que
    le mandat inactif retire déjà toute dépense autonome, et il n'y a pas de stop-loss à geler quand ses seuils sont
    refusés (le 503 est plus strict qu'un gel)."""
    # 1. Mandat modifié et « re-signé » dans le YAML par un tiers : l'empreinte du coffre ne correspond plus.
    vault = G.signed_data(G.no_fees)["approval"]["fingerprint_sha256"]
    resigned = G.signed_data(lambda d: (G.no_fees(d), d.update(mandate_version="mandat-v2-FICTIF")))
    path = tmp_path / "mandat.yaml"
    path.write_text(yaml.safe_dump(resigned, allow_unicode=True), encoding="utf-8")
    client, svc = G.boot(tmp_path / "mandat", POKESHOP_MANDATE_PATH=str(path), POKESHOP_MANDATE_FINGERPRINT=vault)
    assert SpendReason.MANDATE_FINGERPRINT_MISMATCH in svc.mandate.inactive_reasons(G.API_NOW)
    assert body(client.get("/health"))["mandate_active"] is False
    assert svc.stoploss_engine is not None and not svc.stoploss_engine.frozen  # aucun gel CONFIG_UNSIGNED
    # 2. Seuils du stop-loss modifiés : stop-loss non chargé, routes en 503, écritures réelles refusées.
    sl_path, _ = G.tampered_stoploss(tmp_path)
    original = yaml.safe_load(DEFAULT_STOPLOSS_PATH.read_text(encoding="utf-8"))
    client2, svc2 = G.boot(tmp_path / "seuils", POKESHOP_STOPLOSS_PATH=str(sl_path),
                           POKESHOP_STOPLOSS_FINGERPRINT=stoploss_fingerprint(original))  # fmt: skip
    assert svc2.stoploss_engine is None and client2.get("/stoploss/status", headers=G.H).status_code == 503
    assert svc2.gate.authorize(WriteAction.SYNC_PRICE, dry_run=False).has(GateReason.STOPLOSS_UNAVAILABLE)
    # 3. Règles de prix modifiées : valeurs les plus strictes et gel CONFIG_UNSIGNED.
    rules = yaml.safe_load((DEFAULT_STOPLOSS_PATH.parent / "pricing_rules.v1.yaml").read_text(encoding="utf-8"))
    rules["pricing"]["hard_floor_margin"] = "0.01"
    rules_path = tmp_path / "regles.yaml"
    rules_path.write_text(yaml.safe_dump(rules, allow_unicode=True), encoding="utf-8")
    _, svc3 = G.boot(tmp_path / "regles", POKESHOP_RULES_PATH=str(rules_path),
                     POKESHOP_RULES_FINGERPRINT=load_rules().content_sha256)  # fmt: skip
    assert svc3.stoploss_engine.frozen and svc3.stoploss_engine.latch.cause == "CONFIG_UNSIGNED"
    doc = " ".join((API.__doc__ or "").split())
    assert "=> service gelé (``CONFIG_UNSIGNED``) ; absente" not in doc  # ancienne description inexacte
    for phrase in ("=> **mandat inactif**", "=> **stop-loss non chargé**", "pas de ``CONFIG_UNSIGNED``",
                   "=> valeurs les plus strictes et **service gelé** (``CONFIG_UNSIGNED``)"):
        assert phrase in doc, phrase

