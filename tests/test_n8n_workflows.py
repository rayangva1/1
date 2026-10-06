"""Tests des workflows n8n (orchestration/n8n/*.json) : structure importable, connexions, garde-fous.

Vérifie notamment : JSON à jour avec le générateur, connexions vers des nœuds existants, aucune
credential en clair, aucun nœud d'écriture externe actif, workflows inactifs, appels du moteur
vers des routes qui existent (sinon désactivés), simulation explicite, et les exigences propres
à chaque workflow (BP §5, §9, §12 ; contexte propriétaire : étoile polaire, stop-loss, mandat).
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
N8N_DIR = ROOT / "orchestration" / "n8n"
EXPECTED_FILES = {
    "01_fournisseur_vers_site.json",
    "02_commande_vers_livraison.json",
    "03_facture_vers_marge_reelle.json",
    "04_incident.json",
    "05_digest_quotidien.json",
    "06_marketing_automations.json",
    "07_stoploss_watch.json",
    "08_mandat_depenses.json",
}
TRIGGER_TYPES = {
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.errorTrigger",
    "n8n-nodes-base.shopifyTrigger",
}
ENGINE_URL_PREFIX = re.compile(r"^=\{\{ \$\('Paramètres[^']*'\)\.first\(\)\.json\.api_base_url \}\}")


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location("build_workflows", ROOT / "orchestration" / "build_workflows.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()
ENGINE_CREDENTIALS = {GEN.CREDENTIALS[key][2] for key in GEN.CREDENTIAL_ROLES}
"""Credentials moteur : un jeton nommé par rôle (revue R3) ; le jeton commun n'est jamais confié à n8n."""


def _workflows() -> dict[str, dict[str, Any]]:
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(N8N_DIR.glob("*.json"))}


WORKFLOWS = _workflows()


def nodes(wf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["name"]: n for n in wf["nodes"]}


def strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def is_engine_call(node: dict[str, Any]) -> bool:
    return node["type"] == "n8n-nodes-base.httpRequest" and bool(ENGINE_URL_PREFIX.match(node["parameters"]["url"]))


def engine_path(node: dict[str, Any]) -> str:
    """Chemin de la route (expressions remplacées par un segment générique, requête retirée)."""
    path = ENGINE_URL_PREFIX.sub("", node["parameters"]["url"]).split("?")[0]
    return re.sub(r"\{\{.*?\}\}", "X", path)


def outputs_count(node: dict[str, Any]) -> int:
    if node["type"] == "n8n-nodes-base.if":
        return 2
    if node["type"] == "n8n-nodes-base.switch":
        params = node["parameters"]
        extra = 1 if params.get("options", {}).get("fallbackOutput") == "extra" else 0
        return len(params["rules"]["values"]) + extra
    return 2 if node.get("onError") == "continueErrorOutput" else 1


def links(wf: dict[str, Any]) -> Iterator[tuple[str, int, str]]:
    for src, outs in wf["connections"].items():
        for index, branch in enumerate(outs["main"]):
            for link in branch:
                yield src, index, link["node"]


def successors(wf: dict[str, Any], name: str, output: int | None = None) -> list[str]:
    return [dst for src, idx, dst in links(wf) if src == name and (output is None or idx == output)]


def reachable(wf: dict[str, Any]) -> set[str]:
    by_name = nodes(wf)
    seen = {n for n, node in by_name.items() if node["type"] in TRIGGER_TYPES}
    stack = list(seen)
    while stack:
        current = stack.pop()
        for nxt in successors(wf, current):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


# --------------------------------------------------------------------------- générateur


def test_exactly_the_eight_workflows_are_present() -> None:
    assert set(WORKFLOWS) == EXPECTED_FILES


def test_committed_json_matches_generator() -> None:
    exports = GEN.build_all()
    assert set(exports) == EXPECTED_FILES
    for name, data in exports.items():
        assert (N8N_DIR / name).read_text(encoding="utf-8") == GEN.render(data), f"régénérer {name}"
    assert GEN.main(["--check"]) == 0


def test_credentials_map_produces_a_separate_customised_copy(tmp_path: Path) -> None:
    mapping = tmp_path / "ids.json"
    mapping.write_text(json.dumps({"api_05": "AbCdEf0123456789"}), encoding="utf-8")
    out = tmp_path / "import"
    assert GEN.main(["--credentials-map", str(mapping), "--out", str(out)]) == 0
    custom = json.loads((out / "05_digest_quotidien.json").read_text(encoding="utf-8"))
    api_nodes = [
        n
        for n in custom["nodes"]
        if n.get("credentials", {}).get("httpHeaderAuth", {}).get("name", "").startswith("Pokeshop API")
    ]
    assert api_nodes and all(n["credentials"]["httpHeaderAuth"]["id"] == "AbCdEf0123456789" for n in api_nodes)
    assert GEN.main(["--credentials-map", str(mapping)]) == 2  # jamais dans le dossier committé
    mapping.write_text(json.dumps({"inconnu": "x"}), encoding="utf-8")
    assert GEN.main(["--credentials-map", str(mapping), "--out", str(out)]) == 2


def test_check_detects_stale_and_unexpected_files(tmp_path: Path) -> None:
    for name in EXPECTED_FILES:
        shutil.copy(N8N_DIR / name, tmp_path / name)
    assert GEN.main(["--check", "--out", str(tmp_path)]) == 0
    (tmp_path / "99_inconnu.json").write_text("{}", encoding="utf-8")
    assert GEN.main(["--check", "--out", str(tmp_path)]) == 1
    (tmp_path / "99_inconnu.json").unlink()
    (tmp_path / "05_digest_quotidien.json").write_text("{}", encoding="utf-8")
    assert GEN.main(["--check", "--out", str(tmp_path)]) == 1


@pytest.mark.parametrize(
    ("expr", "ok"),
    [
        ("={{ $json.a }}", True),
        ("=x {{ $json.a }} y {{ $json.b }}", True),
        ("={{ JSON.stringify({ a: { b: 1 } }) }}", True),
        ("={{ JSON.stringify({ a: { b: 1 }}) }}", False),
        ("=Paiement {{NOM_BOUTIQUE}} {{ $json.a }}", True),
        ("={{ $json.a }}}}", False),
        ("={{ {{ $json.a }} }}", False),
    ],
)
def test_expression_template_checker(expr: str, ok: bool) -> None:
    assert (GEN.expression_errors(expr) == []) is ok


# ---------------------------------------------------------------------------- structure


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
def test_export_structure_is_importable(name: str) -> None:
    wf = WORKFLOWS[name]
    assert {"name", "nodes", "connections", "settings"} <= set(wf)
    assert wf["active"] is False, "inactif à l'import"
    assert wf["name"].startswith("Pokeshop ")
    assert re.fullmatch(r"[A-Za-z0-9]{16}", wf["id"])
    names = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    assert len(set(names)) == len(names) and len(set(ids)) == len(ids)
    for node in wf["nodes"]:
        uuid.UUID(node["id"])
        assert node["type"].startswith("n8n-nodes-base.")
        assert isinstance(node["typeVersion"], (int, float)) and node["typeVersion"] >= 1
        assert isinstance(node["parameters"], dict)
        assert len(node["position"]) == 2 and all(isinstance(v, int) for v in node["position"])
        if node["type"] in {"n8n-nodes-base.webhook", "n8n-nodes-base.shopifyTrigger"}:
            uuid.UUID(node["webhookId"])
    settings = wf["settings"]
    assert settings["executionOrder"] == "v1" and settings["timezone"] == "Europe/Zurich"
    if name == "04_incident.json":
        assert "errorWorkflow" not in settings
    else:
        assert settings["errorWorkflow"] == WORKFLOWS["04_incident.json"]["id"]
    if name in {"02_commande_vers_livraison.json", "06_marketing_automations.json"}:
        assert settings["saveDataSuccessExecution"] == "none"  # données personnelles : rien de conservé
    # Revue R6 (R5C-DOC-05) : en-têtes secrets reçus => ni exécution réussie ni exécution manuelle conservée.
    secret_hooks = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook"
                    and n["parameters"]["authentication"] == "headerAuth"]  # fmt: skip
    if secret_hooks:
        assert settings["saveDataSuccessExecution"] == "none" and settings["saveManualExecutions"] is False, name


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
def test_connections_point_to_existing_nodes_and_valid_outputs(name: str) -> None:
    wf = WORKFLOWS[name]
    by_name = nodes(wf)
    for src, outs in wf["connections"].items():
        assert src in by_name, f"source inconnue {src}"
        assert set(outs) == {"main"}
        assert len(outs["main"]) <= outputs_count(by_name[src]), f"{src} : sortie inexistante"
        for branch in outs["main"]:
            for link in branch:
                assert link["node"] in by_name, f"{src} -> {link['node']} inconnu"
                assert link["type"] == "main" and link["index"] == 0
    for node in by_name.values():
        if node["type"] in TRIGGER_TYPES:
            assert successors(wf, node["name"]), f"déclencheur sans suite : {node['name']}"
    orphans = {n for n, node in by_name.items() if node["type"] != "n8n-nodes-base.stickyNote"} - reachable(wf)
    assert not orphans, f"nœuds jamais atteints : {orphans}"


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
def test_expressions_are_well_formed(name: str) -> None:
    for node in WORKFLOWS[name]["nodes"]:
        if node["type"] == "n8n-nodes-base.code":
            continue
        for text in strings(node["parameters"]):
            if text.startswith("="):
                assert GEN.expression_errors(text) == [], f"{node['name']} : {text[:80]}"
            assert "$env" not in text, "n8n 2.x bloque $env par défaut : passer par le nœud Paramètres"


def test_each_workflow_has_a_sticky_note_with_activation_and_validation() -> None:
    for name, wf in WORKFLOWS.items():
        notes = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.stickyNote"]
        assert len(notes) == 1, name
        content = notes[0]["parameters"]["content"]
        assert "**Activation**" in content and "Validation humaine requise" in content, name


# ------------------------------------------------------------------------- sécurité


SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"shp(at|ss|ca|pa)_[0-9a-fA-F]{8,}"),
    re.compile(r"sk_(live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[0-9a-f]{64}\b"),  # empreinte ou clé hexadécimale
    re.compile(r"CH\d{2}\s?\d{4}\s?\d{4}"),  # IBAN suisse
]


@pytest.mark.parametrize("name", sorted(EXPECTED_FILES))
def test_no_credential_in_clear(name: str) -> None:
    wf = WORKFLOWS[name]
    text = json.dumps(wf, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text), f"{name} : motif secret {pattern.pattern}"
    known = {(ctype, cid, cname) for ctype, cid, cname in GEN.CREDENTIALS.values()}
    for node in wf["nodes"]:
        params = node["parameters"]
        assert not params.get("sendHeaders"), f"{node['name']} : en-têtes en clair interdits (credential)"
        assert "headerParameters" not in params and "password" not in json.dumps(params).lower()
        for ctype, ref in node.get("credentials", {}).items():
            assert set(ref) == {"id", "name"}, f"{node['name']} : référence de credential seulement"
            assert (ctype, ref["id"], ref["name"]) in known, f"{node['name']} : credential inconnue {ref}"
        if node["type"] == "n8n-nodes-base.httpRequest":
            assert params["authentication"] in {"genericCredentialType", "predefinedCredentialType"}
            assert node.get("credentials"), f"{node['name']} : appel HTTP sans credential"


def test_inbound_webhooks_are_authenticated_except_documented_ones() -> None:
    unauthenticated: set[tuple[str, str]] = set()
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            if node["type"] != "n8n-nodes-base.webhook":
                continue
            auth = node["parameters"]["authentication"]
            if auth == "none":
                unauthenticated.add((name, node["parameters"]["path"]))
            else:
                assert auth == "headerAuth" and "httpHeaderAuth" in node["credentials"]
    # Liens publics des emails seulement (jeton unique, GET). Revue R6 (R5C-DOC-07) : le webhook moteur -> 04 est
    # authentifié par le secret dédié du moteur (joignable depuis la boucle locale de l'hôte, pas seulement le compose).
    hook04 = next(n for n in WORKFLOWS["04_incident.json"]["nodes"] if n["parameters"].get("path") == "pokeshop-incidents")
    assert hook04["credentials"]["httpHeaderAuth"]["id"] == GEN.CREDENTIALS[GEN.ENGINE_NOTIFY_CREDENTIAL][1]
    assert unauthenticated == {
        ("06_marketing_automations.json", "alertes-desinscrire"),
        ("06_marketing_automations.json", "avis-refus"),
        ("06_marketing_automations.json", "alertes-preferences"),
        ("06_marketing_automations.json", "alertes-confirmer"),
    }


def test_human_forms_are_protected_and_time_limited() -> None:
    forms = [
        (name, n)
        for name, wf in WORKFLOWS.items()
        for n in wf["nodes"]
        if n["type"] == "n8n-nodes-base.wait" and n["parameters"].get("resume") == "form"
    ]
    assert len(forms) == 4  # 03 : facture et, pré-drop (6.10.2026), confirmation d'allocation ou de réduction ; 04 ; 08
    for name, node in forms:
        params = node["parameters"]
        assert params["incomingAuthentication"] == "basicAuth" and "httpBasicAuth" in node["credentials"], name
        assert params["limitWaitTime"] is True and params["resumeUnit"] == "hours"
        labels = [f["fieldLabel"] for f in params["formFields"]["values"]]
        assert labels == ["Décision", "Motif"]
    hours = {name: n["parameters"]["resumeAmount"] for name, n in forms}
    assert hours["08_mandat_depenses.json"] == 24  # = HUMAN_APPROVAL_TTL du mandat


# --------------------------------------------------------------- aucune écriture active


def test_no_external_write_node_is_active_by_default() -> None:
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            ntype = node["type"]
            if ntype in GEN.WRITE_NODE_TYPES:
                assert node.get("disabled") is True, f"{name} : {node['name']} actif"
            if ntype == "n8n-nodes-base.httpRequest" and not is_engine_call(node):
                assert node.get("disabled") is True, f"{name} : appel externe actif {node['name']}"
            if ntype == "n8n-nodes-base.readWriteFile":
                assert node.get("disabled") is True
            if ntype in {"n8n-nodes-base.emailSend", "n8n-nodes-base.slack"}:
                assert "DÉSACTIV" in node["name"].upper()


def test_engine_calls_are_simulated_and_target_existing_routes() -> None:
    from pokeshop.api import Services, create_app
    from pokeshop.settings import load_settings

    app = create_app(services=Services.build(load_settings({}), clock=lambda: datetime(2026, 10, 4, tzinfo=UTC)))
    # Schéma OpenAPI : couvre aussi les routeurs inclus (FastAPI récent les inclut de façon paresseuse).
    routes = [
        (method.upper(), re.sub(r"\{[^}]+\}", "X", path))
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    ]
    assert ("GET", "/dashboard/daily") in routes
    enabled_paths: set[tuple[str, str]] = set()
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            if not is_engine_call(node):
                continue
            params = node["parameters"]
            assert params["genericAuthType"] == "httpHeaderAuth"
            assert node["credentials"]["httpHeaderAuth"]["name"] in ENGINE_CREDENTIALS
            body = params.get("jsonBody", "")
            assert "treasury" not in body, f"{name} : trésorerie jamais déclarée par n8n (registres du moteur)"
            assert not re.search(r"dry_run\s*:\s*false|\"dry_run\"\s*:\s*false", body), f"{name} : dry_run false"
            key = (params["method"], engine_path(node))
            exists = key in routes
            if node.get("disabled"):
                assert not exists, f"{name} : {node['name']} désactivé alors que la route existe : l'activer"
                assert "route moteur attendue" in node["name"]
            else:
                assert exists, f"{name} : route inexistante {key}"
                enabled_paths.add(key)
    assert ("POST", "/sync/run") in enabled_paths and ("POST", "/stoploss/freeze") in enabled_paths
    assert ("POST", "/mandate/check") in enabled_paths and ("GET", "/northstar") in enabled_paths
    assert ("GET", "/dashboard/daily") in enabled_paths and ("POST", "/imports/X/run") in enabled_paths
    # F4 : photo du stop-loss, relevés de trésorerie, réception de stock, historique des cycles, santé.
    for key in (("POST", "/stoploss/state/refresh"), ("POST", "/treasury/paypal-balance"),
                ("POST", "/treasury/bank-balance"), ("POST", "/stock/receive"), ("GET", "/sync/history"),
                ("GET", "/health")):
        assert key in enabled_paths, key
    sync = next(
        n
        for n in WORKFLOWS["01_fournisseur_vers_site.json"]["nodes"]
        if is_engine_call(n) and engine_path(n) == "/sync/run"
    )
    assert "dry_run: true" in sync["parameters"]["jsonBody"]


def test_incident_bodies_carry_the_simulation_flag() -> None:
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            if is_engine_call(node) and engine_path(node) == "/incidents" and node["parameters"]["method"] == "POST":
                assert "simulation:" in node["parameters"]["jsonBody"], f"{name} : {node['name']}"


def test_parameters_nodes_default_to_simulation() -> None:
    for name, wf in WORKFLOWS.items():
        params = [n for n in wf["nodes"] if n["name"].startswith("Paramètres")]
        assert params, name
        for node in params:
            values = {a["name"]: a["value"] for a in node["parameters"]["assignments"]["assignments"]}
            assert values["simulation"] is True and values["api_base_url"] == "http://api:8000"
            assert values["responsable_email"].endswith(".invalid")


# --------------------------------------------------------------------- exigences par workflow


def test_01_supplier_to_site_schedules_and_incident_branch() -> None:
    wf = WORKFLOWS["01_fournisseur_vers_site.json"]
    by = nodes(wf)
    crons = [
        n["parameters"]["rule"]["interval"][0] for n in by.values() if n["type"] == "n8n-nodes-base.scheduleTrigger"
    ]
    assert {"field": "cronExpression", "expression": "5 */6 * * *"} in crons  # prix : toutes les 6 h
    assert {"field": "minutes", "minutesInterval": 45} in crons  # stock amont : 30 à 60 min
    assert successors(wf, "Import exploitable ?", 0) == ["Cycle stock amont ?"]
    assert successors(wf, "Cycle stock amont ?", 1) == ["Cycle fournisseur vers site (dry-run)"]
    assert successors(wf, "Import exploitable ?", 1) == ["Ouvrir un incident de flux (INC-03)"]
    assert "'INC-03'" in by["Ouvrir un incident de flux (INC-03)"]["parameters"]["jsonBody"]
    assert successors(wf, "Workflow suspendu ?", 0) == ["Workflow suspendu : cycle ignoré"]
    values = {a["name"]: a["value"] for a in by["Paramètres"]["parameters"]["assignments"]["assignments"]}
    assert "FICTIF_offres_grossiste_a.csv" in values["fournisseurs"]
    for path in ("FICTIF_offres_grossiste_a.csv", "FICTIF_tarif_grossiste_b.xlsx", "FICTIF_flux_grossiste_c.xml"):
        assert (ROOT / "data" / "samples" / path).is_file()


def test_02_order_flow_has_dedupe_human_parcel_task_and_no_personal_data() -> None:
    wf = WORKFLOWS["02_commande_vers_livraison.json"]
    by = nodes(wf)
    trigger = by["Shopify : commande payée (orders/paid)"]
    assert trigger["parameters"]["topic"] == "orders/paid"
    assert successors(wf, "Paramètres — commande") == ["Contrôle doublon (idempotence)"]
    assert by["Contrôle doublon (idempotence)"]["parameters"]["operation"] == "removeItemsSeenInPreviousExecutions"
    js = by["Normaliser la commande (centimes, sans donnée personnelle)"]["parameters"]["jsCode"]
    for field in ("email", "first_name", "last_name", "address1", "phone", "customer"):
        assert not re.search(rf"\.{field}\b|\[['\"]{field}['\"]\]", js), f"donnée personnelle lue : {field}"
    assert "parseFloat" not in js and "toFixed" not in js
    task = by["Tâche colis HUMAINE — notifier la responsable (email, désactivé)"]
    assert task.get("disabled") is True
    slip = json.dumps(by["Bon de préparation"]["parameters"], ensure_ascii=False)
    assert "SOP_PREPARATION_COLIS.md" in slip and "Tâche HUMAINE" in slip
    assert "Enregistrer les frais réels (étoile polaire)" in by


def test_03_invoice_flow_requires_human_validation_before_cost() -> None:
    wf = WORKFLOWS["03_facture_vers_marge_reelle.json"]
    # Revue R4 : facture validée par la propriétaire -> registre des factures du moteur (POST /costs/invoices).
    assert successors(wf, "Extraction validée ?", 0) == ["Préparer la facture validée (coût rendu ventilé)"]
    record = nodes(wf)["Enregistrer la facture validée (POST /costs/invoices)"]
    assert successors(wf, "Préparer la facture validée (coût rendu ventilé)", 0) == [record["name"]]
    assert not record.get("disabled") and engine_path(record) == "/costs/invoices"
    assert record["credentials"]["httpHeaderAuth"]["name"] == "Pokeshop API — jeton nommé n8n-03-factures"
    js = nodes(wf)["Contrôles déterministes (centimes)"]["parameters"]["jsCode"]
    assert "* 50 > est" in js and "parseFloat" not in js  # écart > 2 % en arithmétique entière


def test_04_incident_matches_engine_webhook_and_error_trigger() -> None:
    wf = WORKFLOWS["04_incident.json"]
    by = nodes(wf)
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    url = compose["services"]["api"]["environment"]["POKESHOP_N8N_WEBHOOK_URL"]
    assert url.endswith("/webhook/" + by["Notification d’incident du moteur"]["parameters"]["path"])
    assert any(n["type"] == "n8n-nodes-base.errorTrigger" for n in by.values())
    gravity = by["Gravité"]["parameters"]["rules"]["values"]
    assert [r["outputKey"] for r in gravity] == ["S1", "S2"]
    resume = by["Reprendre (POST /incidents/{id}/resume)"]
    assert resume["onError"] == "continueErrorOutput"
    assert successors(wf, resume["name"], 1) == ["Préparer les instructions S1 (propriétaire)"]
    assert successors(wf, "Test réussi ?", 0) == ["Préparer la demande de reprise"]
    assert "Owner-Token" not in json.dumps(
        [n["parameters"] for n in by.values() if n["type"] == "n8n-nodes-base.httpRequest"]
    )


def test_05_digest_puts_north_star_then_stoploss_first() -> None:
    wf = WORKFLOWS["05_digest_quotidien.json"]
    order = [
        "Chaque jour 07:45 — digest",
        "Paramètres",
        "Étoile polaire (GET /northstar)",
        "État du stop-loss (GET /stoploss/status)",
        "Tableau de bord du jour (GET /dashboard/daily)",
        "Cycles de synchronisation (GET /sync/history)",
        "État du moteur (GET /health)",
        "Composer le digest (étoile polaire en premier)",
    ]
    for a, b in zip(order, order[1:], strict=False):
        assert b in successors(wf, a)
    js = nodes(wf)["Composer le digest (étoile polaire en premier)"]["parameters"]["jsCode"]
    assert js.index("1. ÉTOILE POLAIRE") < js.index("2. STOP-LOSS") < js.index("DÉCISIONS ATTENDUES")
    assert "INTERNE — contient coûts et marges" in js and "parseFloat" not in js


def test_06_marketing_guards_and_unsubscribe() -> None:
    wf = WORKFLOWS["06_marketing_automations.json"]
    by = nodes(wf)
    rails = by["Garde-fous campagne (stock, marge, gel)"]["parameters"]["conditions"]
    ops = {(c["operator"]["type"], c["operator"]["operation"]) for c in rails["conditions"]}
    assert rails["combinator"] == "and"
    assert {("boolean", "true"), ("boolean", "false"), ("array", "notContains"), ("number", "gte")} == ops
    texts = " ".join(c["leftValue"] + str(c["rightValue"]) for c in rails["conditions"])
    assert (
        "blocked_products" in texts
        and "sellable" in texts
        and "seuil_stock_alerte" in texts
        and "global_frozen" in texts
    )
    assert successors(wf, "Garde-fous campagne (stock, marge, gel)", 1) == ["Campagne stoppée (motif)"]
    topics = {n["parameters"]["topic"] for n in by.values() if n["type"] == "n8n-nodes-base.shopifyTrigger"}
    assert topics == {"orders/fulfilled", "fulfillment_events/create", "customers/update"}
    assert by["Attendre 7 jours après livraison (hypothèse)"]["parameters"] == {
        "resume": "timeInterval",
        "amount": 7,
        "unit": "days",
    }
    redirect = by["Répondre : demande de désinscription traitée"]["parameters"]
    assert redirect["respondWith"] == "redirect" and redirect["redirectURL"].endswith("/desinscription.html")
    assert successors(wf, "Lien de désinscription valide ?", 0) == ["Désinscrire dans l’outil d’emailing (désactivé)"]
    assert successors(wf, "Lien de désinscription valide ?", 1) == ["Incident : lien de désinscription invalide"]
    assert successors(wf, "Enregistrer la réception (POST /stock/receive)") == ["Garde : incidents ouverts (alertes stock)"]
    for name in (
        "Envoyer l’email 04 — outil d’emailing (désactivé)",
        "Envoyer l’email 11 — outil d’emailing (désactivé)",
    ):
        assert by[name].get("disabled") is True
    assert by["Une alerte par produit et par personne"]["type"] == "n8n-nodes-base.removeDuplicates"


def test_07_stoploss_watch_freezes_and_notifies_on_change() -> None:
    wf = WORKFLOWS["07_stoploss_watch.json"]
    by = nodes(wf)
    trigger = by["Toutes les heures — stop-loss"]["parameters"]["rule"]["interval"][0]
    assert trigger["field"] == "hours" and trigger["hoursInterval"] == 1
    assert set(successors(wf, "Nouvel état ? (une alerte par changement)")) == {
        "Gel global à appliquer ?",
        "Campagnes à couper ?",
        "Notification immédiate à la propriétaire (email, désactivé)",
        "Notification immédiate (Slack, désactivé)",
    }
    freeze = by["Appliquer le gel global (POST /stoploss/freeze)"]
    assert not freeze.get("disabled") and engine_path(freeze) == "/stoploss/freeze"
    js = by["Analyser l’état (cause, chiffres, action, réarmement)"]["parameters"]["jsCode"]
    for words in ("cause", "mesure", "seuil", "action", "Comment réarmer", "X-Pokeshop-Owner-Token"):
        assert words in js
    assert not any("rearm" in engine_path(n) for n in by.values() if is_engine_call(n))  # jamais de réarmement


def test_08_mandate_routes_each_outcome_and_answers_the_agent() -> None:
    wf = WORKFLOWS["08_mandat_depenses.json"]
    by = nodes(wf)
    # Revue R4 (SEC-16, R3-NEW-06) : un webhook et un secret par agent qui dépense ; demandeur imposé par le webhook.
    from pokeshop import authz

    hooks = {n["parameters"]["path"]: n for n in by.values() if n["type"] == "n8n-nodes-base.webhook"}
    assert set(hooks) == {f"pokeshop-depense-{role}" for role in authz.RELAYED_SPENDERS}
    for path, hook in hooks.items():
        role = path.removeprefix("pokeshop-depense-")
        assert hook["parameters"]["responseMode"] == "responseNode"
        (tag,) = successors(wf, hook["name"], 0)
        assert f"requested_by: '{role}'" in by[tag]["parameters"]["jsCode"]
        assert successors(wf, tag, 0) == ["Demande de dépense (passerelle agents)"]
    check = by["Contrôle du mandat (POST /mandate/check)"]
    assert "record: true" in check["parameters"]["jsonBody"] and check["onError"] == "continueErrorOutput"
    assert successors(wf, check["name"], 1) == ["Répondre : contrôle impossible (refus par défaut)"]
    keys = [r["outputKey"] for r in by["Issue de la décision"]["parameters"]["rules"]["values"]]
    assert keys == ["APPROVED_WITHIN_MANDATE", "NEEDS_HUMAN_APPROVAL", "REJECTED"]
    for output in range(4):
        (first,) = successors(wf, "Issue de la décision", output)
        assert by[first]["type"] == "n8n-nodes-base.respondToWebhook"
    assert successors(wf, "Workflow suspendu ?", 0) == ["Répondre : dépenses suspendues"]
    human = by["Préparer l’email de validation 1 clic"]
    assert "$execution.resumeFormUrl" in json.dumps(human["parameters"], ensure_ascii=False)
    assert by["Exécuter le paiement PayPal — DÉSACTIVÉ"].get("disabled") is True
    # Revue R5 (R4-DOC-03) : POST /mandate/human-decision exige le jeton propriétaire (jamais dans n8n) : rappel.
    assert successors(wf, "Approuvée par la propriétaire ?", 0) == [
        "Rappel : enregistrer la validation au moteur (propriétaire, son jeton)"
    ]
    assert successors(wf, "Approuvée par la propriétaire ?", 1) == ["Refus ou expiration : rien à payer (statu quo sûr)"]
    for node in by.values():
        if node["type"] == "n8n-nodes-base.respondToWebhook":
            assert not re.search(r"iban|cvv|password", json.dumps(node["parameters"]).lower())


# ------------------------------------------------------------------------- code JavaScript


NODE_BIN = next((p for p in (shutil.which("node"), "/opt/node22/bin/node") if p and Path(p).exists()), None)


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : syntaxe JavaScript non vérifiée")
def test_code_nodes_are_valid_javascript(tmp_path: Path) -> None:
    count = 0
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            if node["type"] != "n8n-nodes-base.code":
                continue
            src = tmp_path / f"{count}.js"
            src.write_text(
                f"async function n8nCode($input, $) {{\n{node['parameters']['jsCode']}\n}}\n", encoding="utf-8"
            )
            result = subprocess.run([NODE_BIN, "--check", str(src)], capture_output=True, text=True, check=False)
            assert result.returncode == 0, f"{name} / {node['name']} : {result.stderr}"
            count += 1
    assert count >= 9


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : comportement JavaScript non vérifié")
def test_order_normalisation_and_invoice_checks_behave(tmp_path: Path) -> None:
    by2 = nodes(WORKFLOWS["02_commande_vers_livraison.json"])
    by3 = nodes(WORKFLOWS["03_facture_vers_marge_reelle.json"])
    harness = """
const order = {id: 1001, name: '#FICTIF-1001', currency: 'CHF', financial_status: 'paid', tags: 'precommande',
  processed_at: '2026-11-10T10:00:00+01:00', current_total_price: '207.90', current_total_tax: '15.56',
  shipping_address: {country_code: 'CH', address1: 'NE PAS COPIER'}, email: 'client@exemple.invalid',
  line_items: [{sku: 'FICTIF-DSP', quantity: 1, title: 'Display FICTIF'}]};
const bad = Object.assign({}, order, {currency: 'EUR', shipping_address: {country_code: 'FR'}, line_items: [{quantity: 1}]});
const $input = {all: () => [{json: order}, {json: bad}], first: () => ({json: order})};
const normalize = new Function('$input', NORMALIZE);
const out = normalize($input);
const invoice = {body: {invoice_ref: 'FICTIF-F-1', supplier_id: 'fictif_a', invoice_date: '2026-11-12', currency: 'CHF',
  goods_total_chf: '673.50', lines: [{lot_id: 'L1', product_key: 'P1', qty: 5, estimated_unit_cost_chf: '140.00', invoice_unit_cost_chf: '140.00'},
  {lot_id: 'L2', product_key: 'P2', qty: 3, estimated_unit_cost_chf: '50.00', invoice_unit_cost_chf: '57.83'}]}};
const checks = new Function('$input', INVOICE)({first: () => ({json: invoice})});
console.log(JSON.stringify({out: out.map(o => o.json), checks: checks[0].json}));
"""
    script = harness.replace(
        "NORMALIZE",
        json.dumps(by2["Normaliser la commande (centimes, sans donnée personnelle)"]["parameters"]["jsCode"]),
    )
    script = script.replace("INVOICE", json.dumps(by3["Contrôles déterministes (centimes)"]["parameters"]["jsCode"]))
    src = tmp_path / "harness.js"
    src.write_text(script, encoding="utf-8")
    result = subprocess.run([NODE_BIN, str(src)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    good, bad = data["out"]
    assert good["net_ht"] == "192.34" and good["total_ttc"] == "207.90" and good["preorder"] is True
    assert good["anomalies_count"] == 0 and "NE PAS COPIER" not in result.stdout and "client@" not in result.stdout
    assert bad["anomalies_count"] == 3  # devise, pays, SKU manquant
    checks = data["checks"]
    # 5 × 140,00 + 3 × 57,83 = 873,49 ≠ 673,50 => anomalie de total ; écart 57,83 / 50,00 = +15,66 % > 2 %.
    assert checks["goods_total_chf"] == "873.49" and checks["anomalies_count"] == 1
    assert checks["flagged_count"] == 1 and [v["flagged"] for v in checks["variances"]] == [False, True]


# ------------------------------------------------------------------------------- README


def test_readme_documents_import_credentials_and_activation_order() -> None:
    text = (ROOT / "orchestration" / "README.md").read_text(encoding="utf-8")
    for name in EXPECTED_FILES:
        assert name in text
    for _ctype, _cid, cname in GEN.CREDENTIALS.values():
        assert cname in text
    assert "n8n import:workflow" in text and "/workflows" in text
    for level in ("Niveau 1", "Niveau 2", "Niveau 3", "Niveau 4"):
        assert level in text
    assert "## Validation humaine requise" in text
    assert text.rstrip().splitlines()[-1].startswith("- [ ]")


# ================================================================ lot F4 (revue E2E-07 à E2E-20, CON-05)


def run_js(tmp_path: Path, code: str, items: list[dict[str, Any]], nodes: dict[str, Any] | None = None,
           static: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Exécute le code d'un nœud Code comme n8n (``$input``, ``$('nœud')``, données statiques) ; renvoie (sorties, statique)."""
    assert NODE_BIN is not None
    harness = f"""
const NODES = {json.dumps(nodes or {}, ensure_ascii=False)};
const STATIC = {json.dumps(static or {}, ensure_ascii=False)};
const ITEMS = {json.dumps([{"json": i} for i in items], ensure_ascii=False)};
const $input = {{ all: () => ITEMS, first: () => ITEMS[0] }};
const $ = (name) => {{ if (!(name in NODES)) throw new Error('nœud inconnu ' + name); return {{ first: () => ({{ json: NODES[name] }}) }}; }};
const $getWorkflowStaticData = () => STATIC;
const run = new Function('$input', '$', '$getWorkflowStaticData', {json.dumps(code)});
const out = run($input, $, $getWorkflowStaticData);
console.log(JSON.stringify({{ out: out.map((o) => o.json), static: STATIC }}));
"""
    src = tmp_path / f"h{uuid.uuid4().hex[:8]}.js"
    src.write_text(harness, encoding="utf-8")
    result = subprocess.run([NODE_BIN, str(src)], capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return data["out"], data["static"]


def test_f4_canonical_workflow_keys_everywhere() -> None:
    """E2E-10 : une seule clé par workflow (Paramètres, gardes, incidents de 04, moteur)."""
    from pokeshop.api import WORKFLOW_KEYS as ENGINE_KEYS
    from pokeshop.sync import WORKFLOW_SUPPLIER_TO_SHOP

    assert GEN.WORKFLOW_KEYS == ENGINE_KEYS and GEN.WORKFLOW_KEYS["01"] == WORKFLOW_SUPPLIER_TO_SHOP
    assert len(set(GEN.WORKFLOW_NAMES.values())) == len(GEN.WORKFLOW_NAMES) == 8
    for name, wf in WORKFLOWS.items():
        prefix = name[:2]
        assert wf["name"] == GEN.WORKFLOW_NAMES[prefix] and wf["id"] == GEN.WORKFLOW_IDS[prefix]
        for node in wf["nodes"]:
            if node["name"].startswith("Paramètres"):
                values = {a["name"]: a["value"] for a in node["parameters"]["assignments"]["assignments"]}
                assert values["workflow"] == GEN.WORKFLOW_KEYS[prefix], (name, node["name"])


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : expression non évaluée")
def test_f4_execution_failure_suspends_the_failed_workflow_key(tmp_path: Path) -> None:
    """E2E-10 : l'incident d'échec ouvert par 04 porte la clé canonique => la garde de 08 et le moteur s'arrêtent."""
    node = nodes(WORKFLOWS["04_incident.json"])["Ouvrir un incident d’exécution"]
    expr = node["parameters"]["jsonBody"][len("={{ "):-len(" }}")]
    results = {}
    for prefix, wf_name in GEN.WORKFLOW_NAMES.items():
        for err_wf in ({"id": GEN.WORKFLOW_IDS[prefix], "name": "renommé dans n8n"}, {"id": "autreId", "name": wf_name}):
            nodes_data = {
                "Échec d’exécution d’un workflow": {"execution": {"id": "42", "lastNodeExecuted": "X", "error": {"message": "t"}},
                                                     "workflow": err_wf},
                "Paramètres — erreurs": {"simulation": False},
            }
            out, _ = run_js(tmp_path, f"return [{{ json: JSON.parse({expr}) }}];", [{}], nodes_data)
            results[(prefix, err_wf["id"])] = out[0]["workflow"]
    for (prefix, _), key in results.items():
        assert key == GEN.WORKFLOW_KEYS[prefix]
    # Chaîne complète sur l'API : incident d'échec du workflow 08 (corps exact du nœud 04) => /mandate/check refusé.
    from fastapi.testclient import TestClient
    from pokeshop.api import Services, create_app
    from pokeshop.settings import load_settings, sha256_hex

    token = "FICTIF-jeton-n8n-04-incidents-00001"
    relay = "FICTIF-jeton-n8n-08-mandat-0000001"
    client = TestClient(create_app(services=Services.build(
        load_settings({"POKESHOP_AGENT_TOKENS_SHA256": f"n8n-04-incidents:{sha256_hex(token)},n8n-08-mandat:{sha256_hex(relay)}",
                       "POKESHOP_STATE_DIR": ":memory:"}),
        clock=lambda: datetime(2026, 10, 4, 12, tzinfo=UTC))))
    nodes_data = {"Échec d’exécution d’un workflow": {"execution": {"id": "42", "lastNodeExecuted": "Contrôle du mandat",
                                                                     "error": {"message": "délai"}},
                                                       "workflow": {"id": GEN.WORKFLOW_IDS["08"], "name": GEN.WORKFLOW_NAMES["08"]}},
                  "Paramètres — erreurs": {"simulation": False}}
    out, _ = run_js(tmp_path, f"return [{{ json: JSON.parse({expr}) }}];", [{}], nodes_data)
    headers = {"X-Pokeshop-Token": token}
    assert client.post("/incidents", headers=headers, json=out[0]).status_code == 201
    suspended = client.get("/incidents?open_only=true", headers=headers).json()["suspended"]
    guard_key = {a["name"]: a["value"] for a in nodes(WORKFLOWS["08_mandat_depenses.json"])["Paramètres"]["parameters"]
                 ["assignments"]["assignments"]}["workflow"]
    assert guard_key in suspended
    spend = {"request": {"amount": "150", "currency": "CHF", "supplier_id": "FICTIF_EMBALLAGES", "category": "PACKAGING",
                         "payment_method": "PAYPAL", "purpose": "Cartons FICTIFS", "idempotency_key": "FICTIF-PKG-0001",
                         "requested_by": "operations-sav", "requested_at": "2026-10-04T10:00:00+02:00", "amount_source": "devis"},
             "record": True}
    assert client.post("/mandate/check", headers={"X-Pokeshop-Token": relay}, json=spend).status_code == 423


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : code non exécuté")
def test_f4_stoploss_alerts_on_every_change_not_only_first_sight(tmp_path: Path) -> None:
    """E2E-16 : A -> (rien) -> A est de nouveau signalé ; A -> A ne l'est qu'une fois."""
    wf = WORKFLOWS["07_stoploss_watch.json"]
    by = nodes(wf)
    assert not any(n["type"] == "n8n-nodes-base.removeDuplicates" for n in by.values())
    on_change = by["Nouvel état ? (une alerte par changement)"]["parameters"]["jsCode"]
    forget = by["Aucun déclencheur : oublier l’état signalé"]["parameters"]["jsCode"]
    assert successors(wf, "À signaler ?", 1) == ["Aucun déclencheur : oublier l’état signalé"]
    state: dict[str, Any] = {}
    a = {"fingerprint": "|ko:aucune photo d'activité|libre"}
    out, state = run_js(tmp_path, on_change, [a], static=state)
    assert len(out) == 1
    out, state = run_js(tmp_path, on_change, [a], static=state)
    assert out == []  # même état, pas de nouvelle alerte
    _, state = run_js(tmp_path, forget, [{"fingerprint": "ok"}], static=state)
    out, state = run_js(tmp_path, on_change, [a], static=state)
    assert len(out) == 1, "un état qui réapparaît doit être signalé de nouveau"


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : code non exécuté")
def test_f4_stoploss_photo_is_built_by_the_engine_and_balances_never_invented(tmp_path: Path) -> None:
    """E2E-08 : 07 construit la photo (jeton nommé) avant de lire l'état ; relevés de trésorerie sans invention."""
    wf = WORKFLOWS["07_stoploss_watch.json"]
    by = nodes(wf)
    refresh = by["Construire la photo (POST /stoploss/state/refresh)"]
    assert engine_path(refresh) == "/stoploss/state/refresh" and refresh["onError"] == "continueRegularOutput"
    assert successors(wf, refresh["name"]) == ["État du stop-loss (GET /stoploss/status)"]
    for node in by.values():
        if is_engine_call(node):  # photo, état, gel : n8n-07-stoploss ; relevés de cash : connecteur-tresorerie (R3)
            expected = "connecteur-tresorerie" if engine_path(node).startswith("/treasury/") else "n8n-07-stoploss"
            assert node["credentials"]["httpHeaderAuth"]["name"] == f"Pokeshop API — jeton nommé {expected}"
    assert by["Toutes les heures (:05) — relevés de trésorerie (désactivé)"].get("disabled") is True
    paypal = by["Normaliser le solde PayPal"]["parameters"]["jsCode"]
    out, _ = run_js(tmp_path, paypal, [{"api_base_url": "x"}])  # lecture non configurée (nœud désactivé)
    assert out == []
    response = {"as_of_time": "2026-10-04T09:50:00Z", "balances": [
        {"currency": "EUR", "available_balance": {"currency_code": "EUR", "value": "10.00"}},
        {"currency": "CHF", "primary": True, "available_balance": {"currency_code": "CHF", "value": "1500.25"}}]}
    out, _ = run_js(tmp_path, paypal, [response])
    assert out == [{"as_of": "2026-10-04T09:50:00Z", "balance_chf": "1500.25",
                    "source": "API PayPal v1/reporting/balances (compte dédié)"}]
    out, _ = run_js(tmp_path, paypal, [dict(response, as_of_time=None)])
    assert out == []  # relevé sans date : rien n'est déposé
    bank = by["Normaliser le solde bancaire"]["parameters"]["jsCode"]
    assert run_js(tmp_path, bank, [{"currency": "EUR", "balance_chf": "1", "as_of": "x"}])[0] == []
    assert run_js(tmp_path, bank, [{"currency": "CHF", "balance_chf": "2000.00", "as_of": "2026-10-04T09:40:00Z"}])[0][0][
        "balance_chf"] == "2000.00"
    js = by["Analyser l’état (cause, chiffres, action, réarmement)"]["parameters"]["jsCode"]
    assert '"reference_chf"' in js and '"photo_sha256"' in js  # réarmement : valeur nette attestée


def test_f4_upstream_stock_trigger_never_reprices() -> None:
    """E2E-20 : le déclencheur 45 min (stock amont) n'atteint jamais /sync/run ; le 6 h, si."""
    wf = WORKFLOWS["01_fournisseur_vers_site.json"]
    by = nodes(wf)
    cond = by["Cycle stock amont ?"]["parameters"]["conditions"]["conditions"][0]
    assert "json.cycle" in cond["leftValue"] and cond["rightValue"] == "stock_amont"
    values = {n["name"]: {a["name"]: a["value"] for a in n["parameters"]["assignments"]["assignments"]}
              for n in by.values() if n["name"].startswith("Cycle :")}
    assert values == {"Cycle : prix et offres": {"cycle": "prix_offres"}, "Cycle : stock amont": {"cycle": "stock_amont"}}

    def reach(start: str, blocked: tuple[str, int] | None = None) -> set[str]:
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            for src, idx, dst in links(wf):
                if src == cur and (blocked is None or (src, idx) != blocked) and dst not in seen:
                    seen.add(dst)
                    stack.append(dst)
        return seen

    assert "Cycle fournisseur vers site (dry-run)" in reach("Cycle stock amont ?")
    assert "Cycle fournisseur vers site (dry-run)" not in reach("Cycle stock amont ?", blocked=("Cycle stock amont ?", 1))
    sync = by["Cycle fournisseur vers site (dry-run)"]["parameters"]["jsonBody"]
    assert "catalog" not in sync  # catalogue et frais : registres du moteur (POST /catalog/items, /catalog/cost-inputs)


def test_f4_every_link_of_the_emails_has_a_webhook() -> None:
    """E2E-19 : chaque lien /webhook/<chemin> des emails existe dans un export ; l'opposition pose « avis-refus »."""
    emails = (ROOT / "docs" / "06-contenu" / "EMAILS" / "source" / "emails.yaml").read_text(encoding="utf-8")
    expected = set(re.findall(r"/webhook/([a-z0-9-]+)", emails))
    assert {"alertes-desinscrire", "alertes-preferences", "avis-refus", "alertes-confirmer"} <= expected
    paths = {(n["parameters"]["path"], n["parameters"]["httpMethod"]) for wf in WORKFLOWS.values() for n in wf["nodes"]
             if n["type"] == "n8n-nodes-base.webhook"}
    for path in expected:
        assert (path, "GET") in paths, f"lien des emails sans webhook n8n : {path}"
    by = nodes(WORKFLOWS["06_marketing_automations.json"])
    tag = by["Poser l’étiquette avis-refus — Shopify (désactivé)"]["parameters"]["jsonBody"]
    assert "tagsAdd" in tag and "'avis-refus'" in tag
    assert "'avis-refus'" in by["Éligible à la demande d’avis ?"]["parameters"]["jsCode"]


def _respond_nodes_reachable(wf: dict[str, Any], start: str, without: str | None = None) -> set[str]:
    by = nodes(wf)
    seen, stack = {start}, [start]
    while stack:
        cur = stack.pop()
        for nxt in successors(wf, cur):
            if nxt != without and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return {n for n in seen if by[n]["type"] == "n8n-nodes-base.respondToWebhook"}


@pytest.mark.parametrize(("hook", "bilan", "label"), [
    ("Lien de désinscription (emails)", "Bilan (désinscription)", "désinscription"),
    ("Lien de refus d’avis (emails)", "Bilan (refus d’avis)", "refus d’avis"),
])
def test_f4_confirmation_page_only_after_the_tools_answered(hook: str, bilan: str, label: str) -> None:
    """CON-05 : aucune réponse de succès en amont des retraits ; lien invalide => page d'erreur 400 + incident."""
    wf = WORKFLOWS["06_marketing_automations.json"]
    by = nodes(wf)
    hook_node = by[hook]
    assert hook_node["parameters"]["responseMode"] == "responseNode" and hook_node["parameters"]["httpMethod"] == "GET"
    reachable = _respond_nodes_reachable(wf, hook)
    success = {f"Répondre : demande de {label} traitée", f"Répondre : demande de {label} reçue (traitement manuel)"}
    assert success <= reachable
    without_bilan = _respond_nodes_reachable(wf, hook, without=bilan)
    assert without_bilan == {f"Répondre : lien de {label} invalide"}, "succès possible sans bilan des outils"
    bad = by[f"Répondre : lien de {label} invalide"]["parameters"]
    assert bad["options"]["responseCode"] == 400 and "pas</strong> enregistrée" in bad["responseBody"]
    assert successors(wf, f"Incident : lien de {label} invalide", 0) == [f"Répondre : lien de {label} invalide"]
    assert successors(wf, f"Incident : lien de {label} invalide", 1) == [f"Répondre : lien de {label} invalide"]
    for node in by.values():  # appels aux outils : un échec suit la sortie d'erreur, il n'en bloque pas un autre
        if node["name"].startswith(("Désinscrire dans", "Retirer le consentement", "Enregistrer le refus", "Poser l’étiquette")):
            assert node.get("onError") == "continueErrorOutput" and len(successors(wf, node["name"], 1)) == 1


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : code non exécuté")
def test_f4_unsubscribe_bilan_never_confirms_without_the_tools(tmp_path: Path) -> None:
    """CON-05 : jeton invalide => non valide ; nœud désactivé ou erreur => non confirmé ; réponses réelles => confirmé."""
    by = nodes(WORKFLOWS["06_marketing_automations.json"])
    norm = by["Normaliser le lien de désinscription"]["parameters"]["jsCode"]
    out, _ = run_js(tmp_path, norm, [{"query": {"jeton": "court"}}])
    assert out[0]["valide"] is False and out[0]["jeton"] is None
    out, _ = run_js(tmp_path, norm, [{"query": {"jeton": "A" * 24}}])
    link = out[0]
    assert link["valide"] is True and link["etape"] == "normalise"
    prep_code = by["Préparer l’étape Shopify (désinscription)"]["parameters"]["jsCode"]
    bilan_code = by["Bilan (désinscription)"]["parameters"]["jsCode"]
    ctx = {"Normaliser le lien de désinscription": link}

    def run_flow(emailing: dict[str, Any], shopify: dict[str, Any] | None) -> dict[str, Any]:
        prep, _ = run_js(tmp_path, prep_code, [emailing], ctx)
        inputs = [shopify if (prep[0]["shopify_applicable"] and shopify is not None) else prep[0]]
        out, _ = run_js(tmp_path, bilan_code, inputs, {**ctx, "Préparer l’étape Shopify (désinscription)": prep[0]})
        return out[0]

    disabled = run_flow(link, None)  # outil non branché : la donnée normalisée traverse le nœud désactivé
    assert disabled["tous_confirmes"] is False and "non branché" in disabled["resume"]
    failed = run_flow({"error": {"message": "HTTP 500"}}, None)
    assert failed["tous_confirmes"] is False and "échec" in failed["resume"]
    no_customer = run_flow({"unsubscribed": True}, None)
    assert no_customer["tous_confirmes"] is True and "sans objet" in no_customer["resume"]
    shop_ok = {"data": {"customerEmailMarketingConsentUpdate": {"userErrors": []}}}
    both = run_flow({"unsubscribed": True, "shopify_customer_id": "123"}, shop_ok)
    assert both["tous_confirmes"] is True
    shop_err = {"data": {"customerEmailMarketingConsentUpdate": {"userErrors": [{"message": "x"}]}}}
    assert run_flow({"unsubscribed": True, "shopify_customer_id": "123"}, shop_err)["tous_confirmes"] is False
    prep_disabled, _ = run_js(tmp_path, prep_code, [{"unsubscribed": True, "shopify_customer_id": "123"}], ctx)
    out, _ = run_js(tmp_path, bilan_code, [prep_disabled[0]],
                    {**ctx, "Préparer l’étape Shopify (désinscription)": prep_disabled[0]})
    assert out[0]["tous_confirmes"] is False and "Shopify : non branché" in out[0]["resume"]


def test_f4_landing_page_says_request_received_not_done() -> None:
    """CON-05 : la page de retour annonce une demande reçue et le traitement manuel, sans prétendre plus."""
    page = (ROOT / "site" / "landing" / "desinscription.html").read_text(encoding="utf-8")
    assert "Demande de désinscription reçue" in page and "à la main" in page
    assert "Votre désinscription est enregistrée et s'applique à tous nos outils" not in page


@pytest.mark.skipif(NODE_BIN is None, reason="node absent : code non exécuté")
def test_f4_digest_warns_when_real_time_alerts_are_off(tmp_path: Path) -> None:
    """E2E-13 / E2E-07 : le digest signale des alertes simulées et le compteur de cycles propres."""
    js = nodes(WORKFLOWS["05_digest_quotidien.json"])["Composer le digest (étoile polaire en premier)"]["parameters"]["jsCode"]
    ctx = {
        "Étoile polaire (GET /northstar)": {"cumulative": "0.00", "rows": []},
        "État du stop-loss (GET /stoploss/status)": {"available": False, "error": "aucune photo", "triggers": []},
        "Tableau de bord du jour (GET /dashboard/daily)": {"report": {}},
        "Cycles de synchronisation (GET /sync/history)": {"consecutive_clean_runs": 3, "target": 20, "runs": [
            {"status": "VIDE", "supplier_id": "fictif_grossiste_a", "offers_costed": 0}]},
        "État du moteur (GET /health)": {"notifications": {"webhook_configured": True, "webhook_dry_run": True,
                                                            "real_time_alerts": False}, "persistence": {"unreadable": []}},
    }
    out, _ = run_js(tmp_path, js, [{}], ctx)
    text = out[0]["texte"]
    assert "ALERTES TEMPS RÉEL INACTIVES (POKESHOP_NOTIFY_DRY_RUN=true)" in text
    assert "3 cycle(s) propre(s) consécutif(s) sur 20" in text and "dernier cycle VIDE" in text
    ctx["État du moteur (GET /health)"]["notifications"]["real_time_alerts"] = True
    assert "ALERTES TEMPS RÉEL INACTIVES" not in run_js(tmp_path, js, [{}], ctx)[0][0]["texte"]


def test_f4_mandate_requests_carry_no_treasury() -> None:
    """MOT-08 / SEC-04 (partie n8n) : 08 n'envoie jamais de trésorerie ; le moteur lit ses registres."""
    by = nodes(WORKFLOWS["08_mandat_depenses.json"])
    body = by["Contrôle du mandat (POST /mandate/check)"]["parameters"]["jsonBody"]
    assert "treasury" not in body and "record: true" in body


# ------------------------------------------------------------------- revue R3 : jetons nommés par rôle


def test_r3_every_engine_call_uses_a_role_token_authorized_by_the_matrix() -> None:
    """Revue R3 (SEC-16) : chaque appel moteur actif utilise le jeton nommé de son rôle, admis par la matrice."""
    from pokeshop import authz

    names = {GEN.CREDENTIALS[key][2]: role for key, role in GEN.CREDENTIAL_ROLES.items()}
    assert set(GEN.CREDENTIAL_ROLES.values()) <= authz.KNOWN_ROLES
    assert not any("jeton commun" in name or name.endswith("X-Pokeshop-Token") for name in names)
    checked = 0
    for name, wf in WORKFLOWS.items():
        for node in wf["nodes"]:
            if not is_engine_call(node) or node.get("disabled"):
                continue
            role = names[node["credentials"]["httpHeaderAuth"]["name"]]
            method = node["parameters"]["method"]
            path = engine_path(node)
            rule = next((r for (m, tpl), r in authz.ROUTE_MATRIX.items()
                         if m == method and re.fullmatch(re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(tpl)), path)), None)
            assert rule is not None, f"{name} : {method} {path} absent de la matrice"
            assert authz.allowed(rule, role=role, owner=False), f"{name} : {role} refusé sur {method} {path}"
            checked += 1
    assert checked >= 30
    receive = next(n for n in WORKFLOWS["06_marketing_automations.json"]["nodes"]
                   if is_engine_call(n) and engine_path(n) == "/stock/receive")
    assert names[receive["credentials"]["httpHeaderAuth"]["name"]] == "operations-sav"  # jamais le jeton commun
    balances = [n for n in WORKFLOWS["07_stoploss_watch.json"]["nodes"]
                if is_engine_call(n) and engine_path(n).startswith("/treasury/")]
    assert balances and {names[n["credentials"]["httpHeaderAuth"]["name"]] for n in balances} == {"connecteur-tresorerie"}
