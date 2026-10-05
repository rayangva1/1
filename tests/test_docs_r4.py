"""Docs de la revue R4 tenues contre le code : procédures exécutables, ordre d'activation unique, aucune promesse périmée.

* Jetons (R3-DOC-01, R3-DOC-06) : la commande de génération de ``DELEGATION_AUTONOMIE.md`` §10 étape 6 est exécutée
  telle quelle dans un dossier temporaire (17 jetons, 17 empreintes, 10 secrets de passerelle — revue R5 : plus de passerelle 08 pour l'agent 05) ; le bloc de transfert
  (contrôle des 17 lignes, ajout, ``shred -u``) est rejoué, y compris le refus d'un fichier doublé ; README « Démarrage »
  et B27 montrent le même transfert ; l'API configurée comme à B27 (sans jeton commun) accepte chaque jeton produit.
* Ordre d'activation (R2-ADV-01) : les commandes propriétaire de ``STOP_LOSS.md`` §5 et ``DELEGATION_AUTONOMIE.md`` §10
  étape 7 sont extraites des docs et rejouées sur l'API avec le seul jeton propriétaire : apports, soldes, point zéro
  avec la première photo, puis seulement 07 ; tous les documents d'activation placent 07 après C19.
* Aucune phrase périmée (passerelle commune, paiements pub « exécutés », photo déposée par un jeton nommé…).
Données, jetons et montants FICTIFS ; aucune base PostgreSQL (journaux en fichiers par test, ``tmp_path``).
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import jetons_roles as JR
import pytest
import test_orchestration_f4 as F
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, OWNER_TOKEN_HEADER, Services, create_app
from pokeshop.authz import KNOWN_ROLES
from pokeshop.incidents import LogNotifier
from pokeshop.settings import load_settings
from pokeshop.stoploss import hash_owner_token

ROOT = Path(__file__).resolve().parents[1]
DELEGATION = ROOT / "docs/00-pilotage/DELEGATION_AUTONOMIE.md"
STOP_LOSS = ROOT / "docs/00-pilotage/STOP_LOSS.md"
OWNER_ONLY = {OWNER_TOKEN_HEADER: F.OWNER_TOKEN}
DOC_SET = (
    "README.md", "docs/SPEC.md", "orchestration/README.md", "dashboard/README.md", ".env.example",
    "docs/00-pilotage/INTERVENTIONS_HUMAINES.md", "docs/00-pilotage/BACKLOG.csv", "docs/00-pilotage/PLAN_90_JOURS.md",
    "docs/00-pilotage/STOP_LOSS.md", "docs/00-pilotage/DELEGATION_AUTONOMIE.md", "docs/00-pilotage/ETOILE_POLAIRE.md",
    "docs/00-pilotage/GATES_GO_NO_GO.md", "docs/07-ops/SOP_RECEPTION_STOCK.md", "docs/07-ops/RECETTE_AVANT_OUVERTURE.md",
    "docs/07-ops/SOP_INCIDENTS.md", "docs/06-contenu/PUBLICITE_TEST.md",
)  # fmt: skip


def _text(rel: str | Path) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _agent_docs() -> list[Path]:
    return sorted((ROOT / "docs/08-agents").glob("*.md")) + sorted((ROOT / ".claude/agents").glob("*.md"))


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


def _bash_blocks(text: str) -> list[str]:
    """Blocs ```bash d'un extrait, désindentés (les blocs des listes numérotées sont indentés de 3 espaces)."""
    blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
    out = []
    for block in blocks:
        lines = block.splitlines()
        indent = min((len(ln) - len(ln.lstrip(" ")) for ln in lines if ln.strip()), default=0)
        out.append("\n".join(ln[indent:] for ln in lines) + "\n")
    return out


# ======================================================================= jetons : génération, transfert, stockage


def _generation_block() -> str:
    step6 = _section(_text(DELEGATION), "6. Générer **un jeton par rôle utilisé**", "7. Enregistrer vos apports")
    return _bash_blocks(step6)[0]


def _transfer_block() -> str:
    step6 = _section(_text(DELEGATION), "6. Générer **un jeton par rôle utilisé**", "7. Enregistrer vos apports")
    return _bash_blocks(step6)[1]


def test_documented_roles_are_the_17_known_roles_with_the_three_mandatory_ones() -> None:
    loop = re.search(r"for role in (.*?); do", _generation_block(), re.S)
    assert loop is not None
    roles = loop.group(1).replace("\\", " ").split()
    assert len(roles) == len(set(roles)) == 17 and set(roles) <= KNOWN_ROLES
    assert {"n8n-07-stoploss", "connecteur-tresorerie", "finance-pricing"} <= set(roles)
    gateways = re.search(r"for passerelle in (.*?); do", _generation_block(), re.S)
    assert gateways is not None and len(gateways.group(1).replace("\\", " ").split()) == 10


@pytest.mark.skipif(not all(shutil.which(t) for t in ("bash", "openssl", "sha256sum", "shred")),
                    reason="outils de la procédure absents")  # fmt: skip
def test_token_procedure_runs_as_written_and_the_api_accepts_every_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["bash", "-e", "-c", _generation_block()], env=env, check=True, capture_output=True)
    folder = home / "pokeshop-jetons"
    assert oct(folder.stat().st_mode & 0o777) == "0o700"
    for name, lines in (("jetons-roles.txt", 17), ("empreintes-roles.env", 17), ("secrets-passerelles.txt", 10)):
        assert len((folder / name).read_text().splitlines()) == lines, name
        assert oct((folder / name).stat().st_mode & 0o777) == "0o600", name
    # Transfert : « scp » remplacé par une copie locale, /etc/pokeshop/api.env par un fichier temporaire.
    api_env = tmp_path / "api.env"
    api_env.write_text("POKESHOP_ENV=dev\n")
    transfer = (_transfer_block()
                .replace("scp ~/pokeshop-jetons/empreintes-roles.env serveur:~/empreintes-roles.env",
                         "cp ~/pokeshop-jetons/empreintes-roles.env ~/empreintes-roles.env")
                .replace("/etc/pokeshop/api.env", str(api_env)))  # fmt: skip
    transfer = "\n".join(ln for ln in transfer.splitlines() if not ln.startswith("scripts/compose.sh"))
    subprocess.run(["bash", "-e", "-c", transfer], env=env, check=True, capture_output=True)
    added = [ln for ln in api_env.read_text().splitlines() if ln.startswith("POKESHOP_ROLE_TOKEN_SHA256_")]
    assert len(added) == 17 and not (home / "empreintes-roles.env").exists()
    assert not (folder / "empreintes-roles.env").exists()  # copie locale effacée après le contrôle
    # Un fichier doublé (commande lancée deux fois) n'ajoute rien.
    (home / "empreintes-roles.env").write_text("\n".join(added + added) + "\n")
    check = re.search(r'test "\$\(grep -cE .*?shred -u ~/empreintes-roles\.env', transfer, re.S)
    assert check is not None
    doubled = subprocess.run(["bash", "-c", check.group(0)], env=env, capture_output=True, check=False)
    assert doubled.returncode != 0 and len(api_env.read_text().splitlines()) == 1 + 17
    # L'API lancée avec ces empreintes (sans jeton commun) accepte chaque jeton sous son rôle.
    values = dict(ln.split("=", 1) for ln in added)
    settings = load_settings({**values, "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(F.OWNER_TOKEN),
                              "POKESHOP_STATE_DIR": str(tmp_path / "etat")})  # fmt: skip
    assert settings.api_token_sha256 is None
    client = TestClient(create_app(services=Services.build(settings, clock=F.Clock(F.NOW), notifier=LogNotifier())))
    tokens = dict(ln.split("\t", 1) for ln in (folder / "jetons-roles.txt").read_text().splitlines())
    for role, token in tokens.items():
        assert client.get("/incidents", headers={API_TOKEN_HEADER: token}).status_code == 200, role
    assert client.get("/incidents", headers={API_TOKEN_HEADER: "FICTIF-jeton-inconnu-000000000000"}).status_code == 401


def test_readme_and_b27_show_the_same_explicit_transfer() -> None:
    steps = ("scp ~/pokeshop-jetons/empreintes-roles.env serveur:", "grep -cE '^POKESHOP_ROLE_TOKEN_SHA256_",
             "cat ~/empreintes-roles.env >> /etc/pokeshop/api.env", "shred -u ~/empreintes-roles.env")  # fmt: skip
    readme = _text("README.md")
    positions = [readme.index(s) for s in steps]
    assert positions == sorted(positions)
    b27 = next(ln for ln in _text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md").splitlines() if ln.startswith("| B27 |"))
    assert all(s in b27 for s in steps) and "cat empreintes-roles.env >>" not in b27
    for rel in DOC_SET:
        assert "cat empreintes-roles.env >>" not in _text(rel), rel


# ======================================================================= ordre d'activation : point zéro, puis 07


def _owner_commands(text: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    out = []
    for block in _bash_blocks(text):
        for line in block.splitlines():
            m = re.match(r"^api (POST|GET)\s+(\S+)(?:\s+'(.*)')?", line)
            if m:
                out.append((m.group(1), m.group(2), json.loads(m.group(3)) if m.group(3) else None))
    return out


def _dated(payload: dict[str, Any] | None, day: str) -> dict[str, Any] | None:
    return None if payload is None else json.loads(json.dumps(payload).replace("AAAA-MM-JJ", day))


def test_documented_owner_commands_pose_the_zero_point_before_workflow_07(tmp_path: Path) -> None:
    """Configuration de B27 (sans jeton commun) ; commandes lues dans les docs, rejouées dans l'ordre documenté."""
    settings = load_settings({"POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(F.OWNER_TOKEN),
                              "POKESHOP_AGENT_TOKENS_SHA256": JR.agent_tokens_env(),
                              "POKESHOP_STATE_DIR": str(tmp_path / "etat")})  # fmt: skip
    client = TestClient(create_app(services=Services.build(settings, clock=F.Clock(F.NOW), notifier=LogNotifier())))
    step7 = _section(_text(DELEGATION), "7. Enregistrer vos apports", "**Modifier**")
    zero = _section(_text(STOP_LOSS), "Commandes prêtes pour les étapes 3 et 4", "Les deux options")
    yesterday, today = (F.NOW - timedelta(days=1)).date().isoformat(), F.NOW.date().isoformat()
    for method, path, payload in _owner_commands(step7):  # B25 : apports, jeton propriétaire seul
        resp = client.request(method, path, headers=OWNER_ONLY, json=_dated(payload, yesterday))
        assert resp.status_code in (200, 201), (path, resp.text)
    debts = {"as_of": (F.NOW - timedelta(hours=1)).isoformat(), "preorders_collected_chf": "0", "debts": [],
             "receivables": [], "source": "déclaration FICTIVE de l'agent 05 (BL-190)"}  # fmt: skip
    assert client.post("/treasury/balance-items", headers=JR.HF, json=debts).status_code == 200
    commands = _owner_commands(zero)
    assert [p for _, p, _ in commands] == ["/treasury/bank-balance", "/treasury/paypal-balance", "/stoploss/status",
                                           "/stoploss/baseline", "/stoploss/status"]  # fmt: skip
    for method, path, payload in commands:
        resp = client.request(method, path, headers=OWNER_ONLY, json=_dated(payload, today))
        assert resp.status_code in (200, 201), (path, resp.text)
    status = json.loads(client.get("/stoploss/status", headers=OWNER_ONLY).content)
    assert status["global_frozen"] is False and status["latch"]["baseline"] is not None
    # Étape 5 seulement maintenant : 07 demande la photo, aucun gel.
    refresh = client.post("/stoploss/state/refresh", headers=JR.HPHOTO, json={})
    assert refresh.status_code == 200 and json.loads(refresh.content)["status"]["global_frozen"] is False


def test_workflow_07_before_c19_freezes_and_blocks_the_zero_point(tmp_path: Path) -> None:
    """Ce que les docs interdisent (07 actif ou exécuté à la main avant C19) : gel global, point zéro refusé (409)."""
    client, _, _ = F.boot(tmp_path)
    at = (F.NOW - timedelta(hours=1)).isoformat()
    movement = {"movement_id": "FICTIF-APPORT-1", "at": (F.NOW - timedelta(days=1)).isoformat(),
                "kind": "CONTRIBUTION", "amount": "8000", "ref": "virement FICTIF"}  # fmt: skip
    assert client.post("/capital/movements", headers=OWNER_ONLY, json=movement).status_code == 201
    for path, amount in (("/treasury/bank-balance", "5800.00"), ("/treasury/paypal-balance", "200.00")):
        reading = {"as_of": at, "balance_chf": amount, "source": "relevé FICTIF (propriétaire)"}
        assert client.post(path, headers=OWNER_ONLY, json=reading).status_code == 200
    debts = {"as_of": at, "preorders_collected_chf": "0", "debts": [], "receivables": [], "source": "FICTIF"}
    assert client.post("/treasury/balance-items", headers=JR.HF, json=debts).status_code == 200
    early = client.post("/stoploss/state/refresh", headers=JR.HPHOTO, json={})
    assert early.status_code == 200 and json.loads(early.content)["status"]["global_frozen"] is True
    zero = {"reason": "point zéro option A décidé à J3 (C03)", "reference_chf": "4200", "with_photo": True}
    assert client.post("/stoploss/baseline", headers=OWNER_ONLY, json=zero).status_code == 409


def test_every_activation_document_puts_workflow_07_after_c19() -> None:
    readme = _text("orchestration/README.md")
    assert "**Ne pas exécuter 07 avant C19**" in readme
    section = readme.split("## 7.", 1)[1].split("## 8.", 1)[0]
    level1 = section.split("**Niveau 1", 1)[1].split("**Niveau 2", 1)[0]
    items = [ln[6:8] for ln in level1.splitlines() if ln.startswith("- [ ] ")]
    assert items[-1] == "07" and items[0] == "04", items  # 07 en dernier, après C19
    chrono = {ln.split("|")[3].strip(): ln for ln in _text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md").splitlines()
              if ln.startswith("| ☐ |")}  # fmt: skip
    # Revue R5 (R4-DOC-04) : plus de « tous sauf 07 » — l'ordre unique du §7 (02 et déclencheurs Shopify de 06 au niveau 2).
    assert "05, 08, 01 et 03 à J26" in chrono["B23"] and "07 seulement après C19" in chrono["B23"]
    assert "02 et les déclencheurs Shopify de 06 au niveau 2" in chrono["B23"] and "sauf 07" not in chrono["B23"]
    assert "puis seulement** activer le workflow 07" in chrono["C19"]
    assert "votre jeton" in chrono["B26"] and "07 restant inactif" in chrono["B26"]
    rows = {r["ID"]: r for r in csv.DictReader(io.StringIO(_text("docs/00-pilotage/BACKLOG.csv")))}
    assert "07 ni activé ni exécuté à la main avant le point zéro (BL-191)" in rows["BL-178"]["Critère de done"]
    assert "02 et les déclencheurs Shopify de 06 inactifs jusqu'au niveau 2" in rows["BL-178"]["Critère de done"]
    assert "tous sauf 07" not in rows["BL-178"]["Critère de done"]
    assert "07 restant inactif jusqu'à BL-191" in rows["BL-189"]["Critère de done"]
    assert {"BL-188", "BL-189", "BL-190"} <= {d.strip() for d in rows["BL-191"]["Dépendances"].split(",")}
    assert "**puis** activation du workflow 07" in _text("docs/00-pilotage/PLAN_90_JOURS.md")
    assert "jamais avant l'étape 4**, même pour un essai manuel" in _text(STOP_LOSS)


# ======================================================================= aucune promesse périmée


STALE = (
    "Passerelle agents — X-Pokeshop-Gateway",  # SEC-16 : un secret par passerelle et par agent
    "juste après 04",  # R2-ADV-01
    "paiements pub exécutés",  # R2-NEW-03 : paiements pub engagés
    "Une dépense pub exécutée sans déclaration compte donc quand même",
    "déposée par `POST /stoploss/state` avec un jeton nommé",  # R3-NEW-03 : propriétaire seule
    "viennent des connecteurs en lecture seule (`n8n-07-stoploss`)",  # R3-DOC-05
    "« Passerelle agent 11 (réception contrôlée) »",  # nom réel du nœud : « Réception contrôlée (passerelle agent 11) »
    "dettes et créances chaque jour",  # R3-NEW-02 : créances = propriétaire seule
    "réceptions au coût rendu, ventes, retours",  # R3-NEW-05 : sorties de vente dérivées des commandes
    "Construire, activer en simulation",  # SEC-16 : l'administration de n8n n'est pas déléguée
)


def test_no_stale_promise_survives_in_the_docs() -> None:
    for path in [*(ROOT / rel for rel in DOC_SET), *_agent_docs()]:
        text = path.read_text(encoding="utf-8")
        for phrase in STALE:
            assert phrase not in text, f"{path.relative_to(ROOT)} : « {phrase} »"


def test_workflow_03_note_matches_its_enabled_invoice_node() -> None:
    wf = json.loads(_text("orchestration/n8n/03_facture_vers_marge_reelle.json"))
    note = next(n for n in wf["nodes"] if n["name"] == "Note — à lire")["parameters"]["content"]
    node = next(n for n in wf["nodes"] if n["name"] == "Enregistrer la facture validée (POST /costs/invoices)")
    assert not node.get("disabled") and "`POST /costs/invoices`" in note and "route moteur attendue" not in note
