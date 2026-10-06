"""Pré-drop, étape « n8n » (décision de la propriétaire du 6.10.2026) : branches des workflows 01, 02, 03 et 06.

Structure (générée par ``orchestration/build_workflows.py``) : publication de la fiche de réservation en simulation
(01), identifiant client haché avant le moteur et remboursement prestataire désactivé (02), passerelle des allocations
propre à l'agent 02, fermeture protectrice **avant** la validation humaine d'une réduction, aucune valeur décisive
enregistrée sans le formulaire de la propriétaire (03), signal de demande agrégé et annonces au plus une fois (06).

Comportement du code JavaScript des nœuds (exécuté avec node, comme n8n) : réservations groupées par pré-drop
(``<commande>``, ``<commande>#2``), accès prioritaire attesté (étiquette ET consentement), bilan du remboursement,
contrôles des confirmations fournisseur, liste des remboursements à valider, comptage agrégé sans donnée personnelle,
étapes annoncées une fois. Données FICTIVES.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections import deque
from pathlib import Path
from typing import Any

import pytest
import test_n8n_workflows as N

GEN = N.GEN
WF01 = N.WORKFLOWS["01_fournisseur_vers_site.json"]
WF02 = N.WORKFLOWS["02_commande_vers_livraison.json"]
WF03 = N.WORKFLOWS["03_facture_vers_marge_reelle.json"]
WF06 = N.WORKFLOWS["06_marketing_automations.json"]
B01, B02, B03, B06 = (N.nodes(wf) for wf in (WF01, WF02, WF03, WF06))
needs_node = pytest.mark.skipif(N.NODE_BIN is None, reason="node absent : comportement JavaScript non vérifié")


def successors(wf: dict[str, Any], *, without: str | None = None) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for src, outs in wf["connections"].items():
        if src == without:
            continue
        for links in outs.get("main", []):
            for link in links or []:
                if link["node"] != without:
                    graph.setdefault(src, []).append(link["node"])
    return graph


def reachable(wf: dict[str, Any], start: str, *, without: str | None = None) -> set[str]:
    graph = successors(wf, without=without)
    seen, todo = {start}, deque([start])
    while todo:
        for nxt in graph.get(todo.popleft(), []):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def credential_role(node: dict[str, Any]) -> str | None:
    name = node.get("credentials", {}).get("httpHeaderAuth", {}).get("name")
    for key, role in GEN.CREDENTIAL_ROLES.items():
        if GEN.CREDENTIALS[key][2] == name:
            return role
    return None


def code(by: dict[str, dict[str, Any]], name: str, constant: str) -> str:
    """Code d'un nœud, identique à la constante du générateur (ce qui est testé est ce qui est importé)."""
    js = by[name]["parameters"]["jsCode"]
    assert js == constant.strip() + "\n", name
    return js


# ============================================================================================ structure


def test_01_publishes_the_reservation_fiche_in_simulation_with_its_own_role() -> None:
    node = B01["Fiche de réservation (POST /predrop/{id}/publish, simulation)"]
    assert N.is_engine_call(node) and node["parameters"]["method"] == "POST"
    assert N.engine_path(node).startswith("/predrop/") and N.engine_path(node).endswith("/publish")
    assert "dry_run: true" in node["parameters"]["jsonBody"] and "price" not in node["parameters"]["jsonBody"]
    assert credential_role(node) == "n8n-01-sync"
    start = "Toutes les heures (:20) — fiches de réservation pré-drop"
    assert node["name"] in reachable(WF01, start)
    assert node["name"] not in reachable(WF01, start, without="Workflow suspendu ? (pré-drop)")  # garde d'incident
    assert B01["Alerter : fiche de réservation (email, désactivé)"].get("disabled") is True


def test_02_hashes_the_customer_before_the_engine_and_keeps_the_psp_refund_disabled() -> None:
    crypto = B02["Empreinte client (HMAC-SHA256, clé secrète)"]
    assert crypto["type"] == "n8n-nodes-base.crypto"
    params = crypto["parameters"]
    assert params["action"] == "hmac" and params["type"] == "SHA256" and params["dataPropertyName"] == "customer_ref"
    assert params["secret"] == "={{ $('Paramètres — commande').first().json.cle_empreinte_client }}"
    keys = {a["name"]: a["value"] for a in B02["Paramètres — commande"]["parameters"]["assignments"]["assignments"]}
    assert keys["cle_empreinte_client"] == GEN.CUSTOMER_REF_KEY_PLACEHOLDER  # jamais une vraie clé dans le dépôt
    post = B02["Enregistrer la réservation payée (POST /predrop/reservations)"]
    body = post["parameters"]["jsonBody"]
    assert "customer_ref: $json.customer_ref" in body
    for leak in ("customer_key", "email", "order_name", "tags"):
        assert leak not in body, leak
    assert post["onError"] == "continueErrorOutput" and credential_role(post) == "n8n-02-commandes"
    assert post["name"] in reachable(WF02, crypto["name"])
    assert post["name"] not in reachable(WF02, "Réservation rattachée à un pré-drop ?", without=crypto["name"])
    refund = B02["Rembourser intégralement — Shopify refundCreate (désactivé)"]
    assert refund.get("disabled") is True
    assert B02["Email au client : remboursement intégral — outil d’emailing (désactivé)"].get("disabled") is True
    executed = "Relever le remboursement exécuté (POST /predrop/refunds/{id}/executed)"
    assert executed not in reachable(WF02, "Bilan du remboursement (prestataire)",
                                     without="Remboursement confirmé par le prestataire ?")  # fmt: skip


def test_03_allocations_come_through_the_sourcing_gateway_and_the_owner_form() -> None:
    hook = B03["Confirmation d’allocation extraite par l’agent 02 (passerelle)"]
    assert hook["type"] == "n8n-nodes-base.webhook" and hook["parameters"]["path"] == "pokeshop-allocation"
    assert hook["credentials"]["httpHeaderAuth"]["name"] == GEN.CREDENTIALS["gateway_03_alloc"][2]
    assert GEN.GATEWAY_HOLDERS["gateway_03_alloc"] == "sourcing"
    holders = [k for k, v in GEN.GATEWAY_HOLDERS.items() if k.startswith("gateway_03")]
    assert len({GEN.CREDENTIALS[k][1] for k in holders}) == len(holders)  # un secret par passerelle, jamais partagé
    form = "Validation humaine de la confirmation fournisseur (formulaire, 72 h)"
    assert B03[form]["type"] == "n8n-nodes-base.wait"
    close = "Fermer les réservations (acte protecteur, POST /predrop/{id}/close)"
    reduce_ = "Enregistrer la réduction (POST /predrop/allocations/{référence}/reduce)"
    alloc = "Enregistrer l’allocation ferme (POST /predrop/allocations)"
    # Réduction annoncée : réservations fermées AVANT la validation (acte protecteur, plus d'argent à rembourser).
    assert form in reachable(WF03, close) and close not in reachable(WF03, form)
    # Rien n'est enregistré au moteur sans le formulaire de la propriétaire.
    for decisive in (reduce_, alloc):
        assert decisive in reachable(WF03, hook["name"]) and decisive not in reachable(WF03, hook["name"], without=form)
        assert credential_role(B03[decisive]) == "n8n-03-factures"
    assert credential_role(B03[close]) == "n8n-03-factures"
    for mail in ("Demander la validation des remboursements (email, désactivé)",
                 "Rappeler les remboursements à valider (email, désactivé)"):  # fmt: skip
        assert B03[mail].get("disabled") is True


def test_06_demand_is_aggregate_and_announcements_are_at_most_once_per_person() -> None:
    demand = B06["Signal de demande agrégé (POST /predrop/demand)"]
    body = demand["parameters"]["jsonBody"]
    assert credential_role(demand) == "n8n-06-marketing"
    for field in ("product_key", "interested_consenting_subscribers", "as_of", "source"):
        assert field in body
    for leak in ("email", "subscriber", "customer"):
        assert leak not in body.replace("interested_consenting_subscribers", ""), leak
    dedupe = B06["Une annonce par pré-drop et par personne"]["parameters"]
    assert dedupe["operation"] == "removeItemsSeenInPreviousExecutions"
    assert dedupe["dedupeValue"] == "={{ $json.predrop_id }}|{{ $json.subscriber_id }}"
    for name in ("Lire les inscrits confirmés — outil d’emailing (désactivé, demande)",
                 "Lire les inscrits confirmés — outil d’emailing (désactivé, annonces)",
                 "Envoyer l’annonce pré-drop — outil d’emailing (désactivé)"):  # fmt: skip
        assert B06[name].get("disabled") is True, name
    compose = json.dumps(B06["Composer l’annonce pré-drop (sans prix ni compte à rebours)"]["parameters"], ensure_ascii=False)
    for forbidden in ("prix", "price", "quota", "closes_at", "restant", "compte"):
        assert forbidden not in compose.replace("sans prix ni compte à rebours", ""), forbidden


# ============================================================================================ JavaScript


def run(tmp_path: Path, js: str, items: list[dict[str, Any]], *, first: dict[str, Any] | None = None,
        all_: dict[str, list[dict[str, Any]]] | None = None, static: dict[str, Any] | None = None) -> tuple[list[Any], Any]:
    """Exécute un nœud Code comme n8n : ``$input``, ``$('nœud').first()`` / ``.all()``, données statiques."""
    assert N.NODE_BIN is not None
    harness = f"""
const FIRST = {json.dumps(first or {}, ensure_ascii=False)};
const ALL = {json.dumps({k: [{"json": i} for i in v] for k, v in (all_ or {}).items()}, ensure_ascii=False)};
const STATIC = {json.dumps(static or {}, ensure_ascii=False)};
const ITEMS = {json.dumps([{"json": i} for i in items], ensure_ascii=False)};
const $input = {{ all: () => ITEMS, first: () => ITEMS[0] }};
const $ = (name) => {{
  if (!(name in FIRST) && !(name in ALL)) throw new Error('nœud inconnu ' + name);
  return {{ first: () => (name in FIRST ? {{ json: FIRST[name] }} : ALL[name][0]), all: () => ALL[name] || [{{ json: FIRST[name] }}] }};
}};
const $getWorkflowStaticData = () => STATIC;
const run = new Function('$input', '$', '$getWorkflowStaticData', {json.dumps(js)});
const out = run($input, $, $getWorkflowStaticData);
console.log(JSON.stringify({{ out: out.map((o) => o.json), static: STATIC }}));
"""
    src = tmp_path / f"pd{uuid.uuid4().hex[:8]}.js"
    src.write_text(harness, encoding="utf-8")
    result = subprocess.run([N.NODE_BIN, str(src)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return data["out"], data["static"]


P1 = {"predrop_id": "PD-FICTIF-P1-20261020", "product_key": "FICTIF-P1", "status": "OPEN", "accepting": True,
      "phase": "prioritaire", "drop_date": "2026-10-20", "opens_at": "2026-10-06T08:00:00+02:00",
      "reservation_sku": "DSP-FICTIF_ALPHA-FR-RESA-20261020",
      "reservation_handle": "display-alpha-fictif-reservation-garantie", "normal_handle": "display-alpha-fictif",
      "alert_tag": "alerte-produit:display-alpha-fictif"}  # fmt: skip
P2 = {**P1, "predrop_id": "PD-FICTIF-P2-20261020", "product_key": "FICTIF-P2",
      "reservation_sku": "DSP-FICTIF_BETA-FR-RESA-20261020", "alert_tag": "alerte-produit:display-beta-fictif"}  # fmt: skip
ORDER = {"id": 1001, "name": "#FICTIF-1001", "processed_at": "2026-10-06T10:00:00+02:00", "email": "client@exemple.invalid",
         "customer": {"id": 55, "tags": "alerte-produit:display-alpha-fictif, autre", "email": "client@exemple.invalid",
                      "email_marketing_consent": {"state": "subscribed", "opt_in_level": "confirmed_opt_in",
                                                  "consent_updated_at": "2026-10-01T09:00:00+02:00"}},
         "line_items": [
             {"sku": "DSP-FICTIF_BETA-FR-RESA-20261020", "quantity": 1, "price": "219.90", "discount_allocations": []},
             {"sku": "DSP-FICTIF_ALPHA-FR-RESA-20261020", "quantity": 2, "price": "229.90",
              "discount_allocations": [{"amount": "10.00"}]},
             {"sku": "DSP-FICTIF_ALPHA-FR", "quantity": 1, "price": "209.90"},
             {"sku": "DSP-FICTIF_GAMMA-FR-RESA-20261101", "quantity": 1, "price": "99.90"}]}  # fmt: skip
DEDUP = "Contrôle doublon (idempotence)"
PARAMS02 = {"cle_empreinte_client": "FICTIF-cle-empreinte-client-0123456789abcdef"}
"""Paramètres du workflow 02 avec une clé d'empreinte FICTIVE configurée (≥ 32 caractères)."""


@needs_node
def test_reservations_are_grouped_by_predrop_with_attested_priority(tmp_path: Path) -> None:
    js = code(B02, "Préparer les réservations (une par pré-drop)", GEN.JS_PREDROP_RESERVATIONS)
    offers = {"internal": [P1, P2, {**P1, "predrop_id": "PD-ATTENTE", "status": "PENDING_OWNER",
                                    "reservation_sku": "DSP-FICTIF_GAMMA-FR-RESA-20261101"}]}  # fmt: skip
    out, _ = run(tmp_path, js, [offers], first={DEDUP: ORDER, "Paramètres — commande": PARAMS02})
    first, second, unknown = out
    assert first["predrop_id"] == "PD-FICTIF-P1-20261020" and first["order_id"] == "1001"
    assert first["qty"] == 2 and first["amount_paid_ttc"] == "449.80"  # 2 × 229.90 − 10.00 (centimes, jamais de flottant)
    assert first["priority_access"] is True and first["customer_key"] == "shopify-customer:55"
    assert second["predrop_id"] == "PD-FICTIF-P2-20261020" and second["order_id"] == "1001#2"
    assert second["amount_paid_ttc"] == "219.90" and second["priority_access"] is False  # étiquette d'une autre fiche
    assert unknown == {"rattachee": False, "motif": "SKU de réservation inconnu du moteur",
                       "sku": "DSP-FICTIF_GAMMA-FR-RESA-20261101", "order_name": "#FICTIF-1001",
                       "order_id": "1001"}  # pré-drop en attente de la propriétaire : jamais rattaché
    # Commande mixte (article en stock, SKU inconnu) : aucun frais de livraison rattaché aux réservations.
    assert first["shipping_paid_ttc"] == "0.00" and second["shipping_paid_ttc"] == "0.00"
    assert "client@" not in json.dumps(out)  # identifiant client Shopify présent : l'email n'est pas lu
    # Consentement non confirmé : jamais d'accès prioritaire, même avec l'étiquette.
    pending = {**ORDER, "customer": {**ORDER["customer"], "email_marketing_consent": {"state": "pending"}}}
    out, _ = run(tmp_path, js, [offers], first={DEDUP: pending, "Paramètres — commande": PARAMS02})
    assert [o.get("priority_access") for o in out if o.get("rattachee")] == [False, False]
    # Revue pré-drop (PDL-08) : consentement simple (sans double opt-in) ou donné APRÈS l'ouverture : pas d'accès.
    for consent in ({"state": "subscribed", "opt_in_level": "single_opt_in", "consent_updated_at": "2026-10-01T09:00:00+02:00"},
                    {"state": "subscribed", "opt_in_level": "confirmed_opt_in", "consent_updated_at": "2026-10-06T09:00:00+02:00"}):
        late = {**ORDER, "customer": {**ORDER["customer"], "email_marketing_consent": consent}}
        out, _ = run(tmp_path, js, [offers], first={DEDUP: late, "Paramètres — commande": PARAMS02})
        assert out[0]["priority_access"] is False, consent
    # Commande sans client : clé de repli (empreinte HMAC au nœud suivant), accès prioritaire impossible.
    guest = {k: v for k, v in ORDER.items() if k != "customer"}
    out, _ = run(tmp_path, js, [offers], first={DEDUP: guest, "Paramètres — commande": PARAMS02})
    assert out[0]["customer_key"] == "shopify-email:client@exemple.invalid" and out[0]["priority_access"] is False
    # Clé d'empreinte non configurée (valeur de l'export) : rien n'est rattaché, incident (jamais une empreinte faible).
    out, _ = run(tmp_path, js, [offers], first={DEDUP: ORDER, "Paramètres — commande": {
        "cle_empreinte_client": GEN.CUSTOMER_REF_KEY_PLACEHOLDER}})  # fmt: skip
    assert all(o["rattachee"] is False for o in out) and "clé" in out[0]["motif"]


@needs_node
def test_shipping_paid_on_a_reservation_only_order_is_split_and_sent_to_the_engine(tmp_path: Path) -> None:
    """Revue pré-drop (ARG-06 / PDL-04) : commande composée seulement de réservations, frais de livraison payés
    répartis au prorata des montants (centimes, le dernier reçoit le reste) et envoyés au moteur."""
    js = code(B02, "Préparer les réservations (une par pré-drop)", GEN.JS_PREDROP_RESERVATIONS)
    only = {**ORDER, "total_shipping_price_set": {"shop_money": {"amount": "9.00", "currency_code": "CHF"}},
            "line_items": ORDER["line_items"][:2]}  # fmt: skip
    out, _ = run(tmp_path, js, [{"internal": [P1, P2]}], first={DEDUP: only, "Paramètres — commande": PARAMS02})
    assert [(o["predrop_id"], o["amount_paid_ttc"], o["shipping_paid_ttc"]) for o in out] == [
        ("PD-FICTIF-P1-20261020", "449.80", "6.04"), ("PD-FICTIF-P2-20261020", "219.90", "2.96")]
    single = {**only, "line_items": ORDER["line_items"][1:2]}
    out, _ = run(tmp_path, js, [{"internal": [P1]}], first={DEDUP: single, "Paramètres — commande": PARAMS02})
    assert out[0]["shipping_paid_ttc"] == "9.00"
    post = B02["Enregistrer la réservation payée (POST /predrop/reservations)"]["parameters"]["jsonBody"]
    assert "shipping_paid_ttc: $json.shipping_paid_ttc" in post


@needs_node
def test_publication_list_skips_pending_and_long_past_predrops(tmp_path: Path) -> None:
    js = code(B01, "Pré-drops à publier ou à retirer", GEN.JS_PREDROP_TO_PUBLISH)
    internal = [P1 | {"drop_date": "2099-10-20"}, P2 | {"drop_date": "2020-01-01"},
                P1 | {"predrop_id": "PD-ATTENTE", "status": "PENDING_OWNER", "drop_date": "2099-10-20"}]  # fmt: skip
    out, _ = run(tmp_path, js, [{"internal": internal}])
    assert out == [{"predrop_id": "PD-FICTIF-P1-20261020", "phase": "prioritaire", "drop_date": "2099-10-20"}]
    alert = code(B01, "Erreurs critiques de publication ?", GEN.JS_PREDROP_PUBLISH_ALERT)
    reports = [{"report": {"predrop_id": "PD-1", "phase": "ouvertes", "plan_outcome": "SEND_ACTIVE", "inventory_action": "ERROR",
                           "critical_errors": ["quantité Shopify inconnue"]}},
               {"report": {"predrop_id": "PD-2", "critical_errors": []}}]  # fmt: skip
    out, _ = run(tmp_path, alert, reports)
    assert len(out) == 1 and "PD-1" in out[0]["sujet"] and "INTERNE" in out[0]["texte"]


@needs_node
def test_refunds_are_executed_only_when_approved_and_recorded_only_when_confirmed(tmp_path: Path) -> None:
    pick = code(B02, "Un remboursement par élément", GEN.JS_PREDROP_REFUNDS_TO_EXECUTE)
    refunds = {"refunds": [{"refund_id": "pdr:1", "order_id": "1001#2", "amount_ttc": "238.90", "shipping_ttc": "9.00",
                            "reason": "QUOTA", "status": "APPROVED"},
                           {"refund_id": "pdr:2", "order_id": "1002", "amount_ttc": "229.90", "reason": "QUOTA",
                            "status": "PENDING_OWNER"},
                           {"refund_id": "pdr:3", "order_id": "1003", "amount_ttc": "0.00", "reason": "AMOUNT_MISMATCH",
                            "status": "APPROVED"}]}  # fmt: skip
    out, _ = run(tmp_path, pick, [refunds])
    assert out == [{"refund_id": "pdr:1", "shopify_order_id": "1001", "amount_ttc": "238.90", "shipping_ttc": "9.00",
                    "reason": "QUOTA"}]  # montant nul : rien à rembourser chez le prestataire
    psp = B02["Rembourser intégralement — Shopify refundCreate (désactivé)"]["parameters"]["jsonBody"]
    assert "shipping: { amount: $json.shipping_ttc }" in psp and "amount: $json.amount_ttc" in psp
    bilan = code(B02, "Bilan du remboursement (prestataire)", GEN.JS_PSP_REFUND_BILAN)
    source = out * 3
    responses = [
        {"data": {"refundCreate": {"refund": {"id": "gid://shopify/Refund/9", "createdAt": "2026-10-07T10:00:00Z"}, "userErrors": []}}},
        {"error": {"message": "timeout"}},
        out[0],  # nœud désactivé : l'élément passe tel quel
    ]
    res, _ = run(tmp_path, bilan, responses, all_={"Un remboursement par élément": source})
    assert [r["confirme"] for r in res] == [True, False, False]
    assert res[0]["psp_refund_ref"] == "gid://shopify/Refund/9" and res[0]["refund_id"] == "pdr:1"
    assert res[1]["motif"].startswith("échec") and res[2]["motif"] == "non branché (nœud désactivé)"
    assert res[1]["psp_refund_ref"] is None and res[2]["executed_at"] is None


@needs_node
def test_supplier_confirmation_checks(tmp_path: Path) -> None:
    js = code(B03, "Contrôles de la confirmation (déterministes)", GEN.JS_ALLOCATION_CHECKS)
    ok = {"kind": "allocation", "product_key": "FICTIF-P1", "supplier_id": "fictif_grossiste_a", "qty": 10,
          "supplier_confirmation_ref": "FICTIF-CONF-1", "expected_delivery": "2026-10-15", "document": "conf.pdf"}  # fmt: skip
    out, _ = run(tmp_path, js, [{"body": ok}])
    assert out[0]["anomalies_count"] == 0 and out[0]["kind"] == "allocation" and "ALLOCATION FERME" in out[0]["resume"]
    reduction = {"kind": "reduction", "product_key": "FICTIF-P1", "new_qty": 4, "supplier_confirmation_ref": "FICTIF-CONF-2",
                 "reason": "allocation réduite par le fournisseur FICTIF", "document": "conf2.pdf"}  # fmt: skip
    out, _ = run(tmp_path, js, [{"body": reduction}])
    assert out[0]["anomalies_count"] == 0 and out[0]["qty"] == 4 and "RÉDUCTION" in out[0]["resume"]
    bad = [
        {**ok, "document": None},  # rien sans pièce
        {**ok, "qty": 0},
        {**ok, "qty": 2.5},
        {**ok, "kind": "bonus"},
        {**ok, "supplier_id": ""},
        {**ok, "expected_delivery": "15.10.2026"},
        {**reduction, "reason": "court"},
        {**reduction, "new_qty": -1},
        {**ok, "supplier_confirmation_ref": "x"},
    ]
    for body in bad:
        out, _ = run(tmp_path, js, [{"body": body}])
        assert out[0]["anomalies_count"] >= 1, body
    find = code(B03, "Pré-drop ouvert de la référence", GEN.JS_OPEN_PREDROP_OF_PRODUCT)
    checks = {"Contrôles de la confirmation (déterministes)": {"product_key": "FICTIF-P1"}}
    out, _ = run(tmp_path, find, [{"internal": [P2, P1, {**P1, "predrop_id": "PD-VIEUX", "status": "CLOSED"}]}], first=checks)
    assert out == [{"predrop_id": "PD-FICTIF-P1-20261020", "ouvert": True}]
    out, _ = run(tmp_path, find, [{"internal": [P2]}], first=checks)
    assert out == [{"predrop_id": None, "ouvert": False}]


@needs_node
def test_owner_refund_list_never_carries_a_token(tmp_path: Path) -> None:
    js = code(B03, "Liste des remboursements à valider", GEN.JS_REFUNDS_FOR_OWNER)
    assert B03["Remboursements à valider par la propriétaire ?"]["parameters"]["jsCode"] == js
    refunds = {"refunds": [{"refund_id": "pdr:PD-1:1001", "order_id": "1001", "amount_ttc": "229.90", "reason": "ALLOCATION_REDUCED",
                            "status": "PENDING_OWNER"},
                           {"refund_id": "pdr:PD-1:1000", "order_id": "1000", "amount_ttc": "229.90", "reason": "QUOTA",
                            "status": "APPROVED"}]}  # fmt: skip
    out, _ = run(tmp_path, js, [refunds])
    assert len(out) == 1 and out[0]["sujet"].startswith("[PRÉ-DROP] 1 remboursement")
    texte = out[0]["texte"]
    assert "pdr:PD-1:1001" in texte and "pdr:PD-1:1000" not in texte and "229.90 CHF intégral" in texte
    assert '"$API/predrop/refunds/pdr%3APD-1%3A1001/approve"' in texte and "$JETON" in texte
    assert "INTERNE" in texte
    out, _ = run(tmp_path, js, [{"refunds": []}])
    assert out == []


@needs_node
def test_demand_count_is_aggregate_without_personal_data(tmp_path: Path) -> None:
    js = code(B06, "Compter les inscrits par référence (agrégé, sans donnée personnelle)", GEN.JS_DEMAND_COUNT)
    subscribers = [
        {"id": "s1", "email": "a@exemple.invalid", "status": "confirme", "alert_products": ["FICTIF-P1", "FICTIF-P1", "FICTIF-P2"]},
        {"id": "s2", "email": "b@exemple.invalid", "status": "confirme", "alert_products": ["FICTIF-P1"]},
        {"id": "s3", "email": "c@exemple.invalid", "status": "en_attente", "alert_products": ["FICTIF-P1"]},
        {"id": "s4", "email": "d@exemple.invalid", "status": "confirme", "unsubscribed": True, "alert_products": ["FICTIF-P1"]},
        {"id": "s5", "email": "e@exemple.invalid", "status": "confirme", "alert_products": ["mauvaise clé !"]},
    ]
    out, _ = run(tmp_path, js, [{"subscribers": subscribers}])
    assert [(o["product_key"], o["interested_consenting_subscribers"]) for o in out] == [("FICTIF-P1", 2), ("FICTIF-P2", 1)]
    text = json.dumps(out)
    assert "@" not in text and "s1" not in text and "s2" not in text
    out, _ = run(tmp_path, js, [{"etape": "non branché"}])  # outil désactivé : aucun signal (pré-drop fermé faute de demande)
    assert out == []


@needs_node
def test_steps_are_announced_once_and_never_for_closed_reservations(tmp_path: Path) -> None:
    js = code(B06, "Étapes à annoncer (une par pré-drop)", GEN.JS_PREDROP_STEPS)
    closed = {**P2, "phase": "fermees", "accepting": False}
    out, memo = run(tmp_path, js, [{"internal": [P1, closed]}])
    assert [(o["predrop_id"], o["etape"]) for o in out] == [("PD-FICTIF-P1-20261020", "prioritaire")]
    assert out[0]["url_reservation"] == "/products/display-alpha-fictif-reservation-garantie"
    for forbidden in ("prix", "quota", "closes_at", "per_customer_limit"):
        assert forbidden not in json.dumps(out), forbidden
    again, memo = run(tmp_path, js, [{"internal": [P1]}], static=memo)
    assert again == []
    opened, memo = run(tmp_path, js, [{"internal": [{**P1, "phase": "ouvertes"}]}], static=memo)
    assert [o["etape"] for o in opened] == ["ouvertes"]
    back, memo = run(tmp_path, js, [{"internal": [P1]}], static=memo)
    assert back == []  # jamais un retour à la fenêtre prioritaire
    pending, _ = run(tmp_path, js, [{"internal": [{**P2, "status": "PENDING_OWNER"}]}], static=memo)
    assert pending == []
    audience = code(B06, "Inscrits consentants qui suivent la référence", GEN.JS_PREDROP_AUDIENCE)
    step = {"predrop_id": P1["predrop_id"], "product_key": "FICTIF-P1", "etape": "prioritaire", "opens_at": P1["opens_at"]}
    subscribers = {"subscribers": [
        {"id": "s1", "status": "confirme", "alert_products": ["FICTIF-P1"], "shopify_customer_id": "gid://shopify/Customer/55",
         "date_consentement": "2026-10-01T09:00:00+02:00"},
        {"id": "s2", "status": "confirme", "alert_products": ["FICTIF-P2"]},
        {"id": "s3", "status": "en_attente", "alert_products": ["FICTIF-P1"]},
        {"id": "s4", "status": "confirme", "unsubscribed": True, "alert_products": ["FICTIF-P1"]},
        {"id": "s5", "status": "confirme", "alert_products": ["FICTIF-P1"], "date_consentement": "2026-10-01T09:00:00+02:00"},
        {"id": "s6", "status": "confirme", "alert_products": ["FICTIF-P1"], "shopify_customer_id": "56",
         "date_consentement": "2026-10-06T09:00:00+02:00"}]}  # fmt: skip
    out, _ = run(tmp_path, audience, [subscribers], all_={"Étapes à annoncer (une par pré-drop)": [step]})
    # Revue pré-drop (PDL-08) : email 16 seulement avec un compte client lié ET une inscription confirmée avant
    # l'ouverture (s5 sans compte lié, s6 inscrit après l'ouverture : rien pendant la fenêtre prioritaire).
    assert [(o["subscriber_id"], o["shopify_customer_id"]) for o in out] == [("s1", "55")]
    opening = {**step, "etape": "ouvertes"}
    out, _ = run(tmp_path, audience, [subscribers], all_={"Étapes à annoncer (une par pré-drop)": [opening]})
    assert sorted(o["subscriber_id"] for o in out) == ["s1", "s5", "s6"]  # email 17 : tous les inscrits qui suivent
    out, _ = run(tmp_path, audience, [step], all_={"Étapes à annoncer (une par pré-drop)": [step]})
    assert out == []  # outil d'emailing non branché : personne


# ============================================================================== étape 3 : emails du pré-drop


def test_every_email_template_sent_by_n8n_exists_in_the_email_generator() -> None:
    """Chaque ``template: '<id>'`` (ou modèle composé) des exports n8n est un email de docs/06-contenu (générateur)."""
    import re

    import yaml

    source = yaml.safe_load((N.ROOT / "docs" / "06-contenu" / "EMAILS" / "source" / "emails.yaml").read_text(encoding="utf-8"))
    ids = {e["id"] for e in source["emails"]}
    sent: set[str] = set()
    for wf in N.WORKFLOWS.values():
        text = json.dumps(wf, ensure_ascii=False)
        sent |= set(re.findall(r"template: '([0-9]{2}-[a-z0-9-]+)'", text))
        sent |= set(re.findall(r"'([0-9]{2}-pre-drop-[a-z-]+)'", text))
    predrop = {i for i in sent if "-pre-drop-" in i}
    assert predrop == {"15-pre-drop-reservation-confirmee", "16-pre-drop-acces-prioritaire", "17-pre-drop-ouverture",
                       "18-pre-drop-remboursement", "19-pre-drop-expedition-prioritaire"}
    assert sent <= ids, sorted(sent - ids)
    assert "pre-drop-remboursement'" not in json.dumps(WF02, ensure_ascii=False).replace("18-pre-drop-remboursement'", "")


def test_predrop_customer_emails_are_disabled_and_carry_no_price_or_quantity() -> None:
    confirm = B02["Email au client : réservation garantie confirmée — outil d’emailing (désactivé)"]
    refund = B02["Email au client : remboursement intégral — outil d’emailing (désactivé)"]
    shipped = B06["Email 19 : réservation garantie expédiée en priorité — outil d’emailing (désactivé)"]
    for node in (confirm, refund, shipped):
        assert node.get("disabled") is True, node["name"]
    # 15 : seulement pour une réservation confirmée nouvellement enregistrée (rejeu du webhook : aucun second email).
    assert confirm["name"] in reachable(WF02, "Réservation servie ?")
    assert confirm["name"] not in reachable(WF02, "Réservation servie ?", without="Journal : réservation confirmée (servie en premier)")
    outs = WF02["connections"]["Réservation nouvellement enregistrée ?"]["main"]
    assert [link["node"] for link in outs[0]] == [confirm["name"]]
    assert [link["node"] for link in outs[1]] == ["Rejeu : email déjà envoyé"]
    body15 = confirm["parameters"]["jsonBody"]
    for leak in ("amount", "prix", "price", "qty", "quota", "customer"):
        assert leak not in body15, leak
    # 18 : montant intégral et motif en français lus dans le moteur, jamais recalculés.
    body18 = refund["parameters"]["jsonBody"]
    assert "montant_rembourse: $json.refund.amount_ttc" in body18 and "motif_remboursement: $json.refund.reason_fr" in body18
    # 19 : seulement pour un envoi qui contient une ligne de réservation (SKU -RESA-<date>).
    cond = json.dumps(B06["Réservation pré-drop dans l’envoi ?"]["parameters"], ensure_ascii=False)
    assert "-RESA-" in cond and shipped["name"] in reachable(WF06, "Shopify : commande expédiée (orders/fulfilled)")
    assert "variables: {}" in shipped["parameters"]["jsonBody"]


@needs_node
def test_prepared_reservations_carry_the_drop_date_for_email_15(tmp_path: Path) -> None:
    js = code(B02, "Préparer les réservations (une par pré-drop)", GEN.JS_PREDROP_RESERVATIONS)
    offers = {"internal": [{**P1, "drop_date": "2026-10-20"}, P2]}
    out, _ = run(tmp_path, js, [offers], first={DEDUP: ORDER, "Paramètres — commande": PARAMS02})
    assert out[0]["date_drop"] == "2026-10-20" and "prix" not in json.dumps(out)
    assert "cle_empreinte" not in json.dumps(out) and PARAMS02["cle_empreinte_client"] not in json.dumps(out)
