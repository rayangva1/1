"""Docs de la revue R5 tenues contre le code : procédure des jetons portable, ordre d'activation unique, revue adverse.

* R4-DOC-06 : la commande de génération de ``DELEGATION_AUTONOMIE.md`` §10 étape 6 est exécutée **telle qu'écrite** avec
  les seuls outils de macOS (``shasum -a 256`` et ``rm -P`` simulés, ni ``sha256sum`` ni ``shred``) : 17 jetons, 17
  empreintes justes, 10 secrets ; sans outil d'empreinte, arrêt avant toute écriture ; valeur vide en cours de route,
  arrêt et fichiers déjà écrits effacés ; fichiers déjà présents, refus sans rien toucher.
* R4-DOC-04 et R4-DOC-05 : un seul ordre d'activation des workflows, cohérent avec les niveaux d'autonomie (02 et les
  déclencheurs Shopify de 06 au niveau 2, 07 après C19) ; C29 bloque l'alerte S1 de 04 et l'activation de 07, jamais
  l'activation de 04 (actif depuis J8).
* Revue adverse de sécurité : ``REVUE_SECURITE.md`` (historique, risques résiduels, procédure) existe et sa règle de
  passage figure dans les gates, les interventions humaines et le backlog pour les niveaux 2, 3 et 4.
Données, jetons et montants FICTIFS ; aucun réseau, aucune base PostgreSQL ; tout s'écrit sous ``tmp_path``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import test_docs_r4 as D4

ROOT = Path(__file__).resolve().parents[1]
REVUE = ROOT / "docs/00-pilotage/REVUE_SECURITE.md"
FILES = ("jetons-roles.txt", "empreintes-roles.env", "secrets-passerelles.txt")
GATE_RULE = "revue adverse de sécurité relancée et sans critical/high ouvert"

# ======================================================================= R4-DOC-06 : jetons, Linux ou macOS

SHASUM_STUB = f"""#!{sys.executable}
# shasum de macOS simulé : « shasum -a 256 » lit l'entrée standard et écrit « <empreinte>  - ».
import hashlib, sys
assert sys.argv[1:] == ["-a", "256"], sys.argv
print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest() + "  -")
"""

RM_STUB = """#!/bin/bash
# rm de macOS simulé : accepte -P (écrasement avant suppression) et note son usage.
args=(); for a in "$@"; do if [ "$a" = -P ]; then : > "$HOME/rm-P-utilise"; else args+=("$a"); fi; done
exec /bin/rm "${args[@]}"
"""

OPENSSL_FAILING_STUB = f"""#!{sys.executable}
# openssl qui rend une valeur vide au 5e appel (sortie tronquée) : le bloc doit s'arrêter et tout effacer.
import os, pathlib, secrets
counter = pathlib.Path(os.environ["HOME"]) / "openssl-appels"
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
print("" if n >= 5 else secrets.token_hex(32))
"""


def _toolbox(tmp_path: Path, *, hashing: bool = True, failing_openssl: bool = False) -> Path:
    """Dossier ``bin`` réduit aux outils de macOS : ni ``sha256sum`` ni ``shred`` (``shasum`` et ``rm -P`` simulés)."""
    box = tmp_path / ("bin-macos" if hashing else "bin-sans-empreinte")
    box.mkdir()
    for tool in ("bash", "cat", "cut", "grep", "mkdir", "tr", "wc", "openssl"):
        if tool == "openssl" and failing_openssl:
            continue
        found = shutil.which(tool)
        assert found is not None, tool
        (box / tool).symlink_to(found)
    stubs = {"rm": RM_STUB}
    if hashing:
        stubs["shasum"] = SHASUM_STUB
    if failing_openssl:
        stubs["openssl"] = OPENSSL_FAILING_STUB
    for name, body in stubs.items():
        (box / name).write_text(body, encoding="utf-8")
        (box / name).chmod(0o755)
    assert not (box / "sha256sum").exists() and not (box / "shred").exists()
    return box


def _run_generation(box: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(home), "PATH": str(box)}
    return subprocess.run([str(box / "bash"), "-e", "-c", D4._generation_block()], env=env, capture_output=True,
                          text=True, check=False)  # fmt: skip


pytestmark_tools = pytest.mark.skipif(not all(shutil.which(t) for t in ("bash", "openssl", "cut", "grep", "tr", "wc")),
                                      reason="outils de base absents")  # fmt: skip


def test_r4doc06_generation_block_is_strict_and_portable_as_written() -> None:
    block = D4._generation_block()
    assert block.startswith("bash <<'FIN'\nset -euo pipefail\n") and block.rstrip().endswith("FIN")
    assert 'command -v sha256sum' in block and 'shasum -a 256' in block and 'rm -P' in block and 'shred -u' in block
    # contrôle de J2 = contrôle de J8 : 64 hexadécimaux par valeur, sur chacun des trois fichiers
    assert block.count("[0-9a-f]{64}$'") == 3 and "hex64() { [[ \"$1\" =~ ^[0-9a-f]{64}$ ]]" in block
    assert 'hex64 "$jeton"' in block and 'hex64 "$hash"' in block and 'hex64 "$secret"' in block
    text = D4._text(D4.DELEGATION)
    for needle in ("**Prérequis** : Linux ou macOS", "`shasum -a 256`", "`rm -P`", "`set -euo pipefail`",
                   "même contrôle qu'à J8"):  # fmt: skip
        assert needle in text, needle
    b22 = next(ln for ln in D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md").splitlines() if ln.startswith("| B22 |"))
    assert "Linux ou macOS" in b22 and "shasum -a 256" in b22 and "set -euo pipefail" in b22 and "rm -P" in b22
    rows = {r["ID"]: r for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}
    assert "shasum -a 256" in rows["BL-177"]["Critère de done"] and "rm -P" in rows["BL-177"]["Critère de done"]
    readme = D4._text("README.md")
    assert "shasum -a 256" in readme and "rm -P" in readme


@pytestmark_tools
def test_r4doc06_generation_runs_with_macos_tools_only(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    done = _run_generation(_toolbox(tmp_path), home)
    assert done.returncode == 0, done.stderr
    assert "OK : 17 jetons, 17 empreintes, 10 secrets" in done.stdout
    folder = home / "pokeshop-jetons"
    tokens = dict(ln.split("\t") for ln in (folder / "jetons-roles.txt").read_text().splitlines())
    hashes = dict(ln.split("=", 1) for ln in (folder / "empreintes-roles.env").read_text().splitlines())
    gateways = (folder / "secrets-passerelles.txt").read_text().splitlines()
    assert len(tokens) == len(hashes) == 17 and len(gateways) == 10
    for role, token in tokens.items():  # empreinte = sha256 du jeton, jamais vide (sortie de shasum découpée)
        var = "POKESHOP_ROLE_TOKEN_SHA256_" + role.upper().replace("-", "_")
        assert hashes[var] == hashlib.sha256(token.encode()).hexdigest(), role
    assert "08-agent-05-finance-pricing" not in {g.split("\t")[0] for g in gateways}  # R4-DOC-11 : l'agent 05 paie
    # Relancer sans ranger : refus, rien n'est touché (pas de doublon, pas d'écrasement).
    before = {name: (folder / name).read_bytes() for name in FILES}
    (tmp_path / "bis").mkdir()
    again = _run_generation(_toolbox(tmp_path / "bis"), home)
    assert again.returncode != 0 and "existe déjà" in again.stderr
    assert {name: (folder / name).read_bytes() for name in FILES} == before


@pytestmark_tools
def test_r4doc06_no_hashing_tool_stops_before_any_write(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    done = _run_generation(_toolbox(tmp_path, hashing=False), home)
    assert done.returncode != 0 and "ni sha256sum ni shasum" in done.stderr
    assert not (home / "pokeshop-jetons").exists()  # aucune empreinte vide écrite (défaut R4-DOC-06)


@pytestmark_tools
def test_r4doc06_empty_value_mid_way_erases_every_file_already_written(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    done = _run_generation(_toolbox(tmp_path, failing_openssl=True), home)
    assert done.returncode != 0 and "valeur vide ou invalide" in done.stderr
    folder = home / "pokeshop-jetons"
    assert folder.is_dir() and not any((folder / name).exists() for name in FILES)
    assert (home / "rm-P-utilise").exists()  # effacement par « rm -P » sous macOS (pas de shred)


# ======================================================================= R4-DOC-04, R4-DOC-05 : ordre d'activation unique


def _section7() -> str:
    return D4._text("orchestration/README.md").split("## 7.", 1)[1].split("## 8.", 1)[0]


def test_r4doc04_activation_table_is_unique_and_follows_the_autonomy_levels() -> None:
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in _section7().splitlines()
            if ln.startswith("| ") and not ln.startswith("| Quand") and not ln.startswith("|---")]  # fmt: skip
    by_when = {r[0]: r for r in rows}
    assert by_when["J8 (B27)"][1] == "1" and "**04**" in by_when["J8 (B27)"][2] and "**06**" in by_when["J8 (B27)"][2]
    j26 = by_when["J26 (B23)"]
    assert j26[1] == "1" and all(f"**{w}**" in j26[2] for w in ("05", "08", "01", "03"))
    assert "**02** et **07** importés mais **inactifs**" in j26[2]
    assert "**07**" in by_when["J27 (C19)"][2] and "point zéro" in by_when["J27 (C19)"][3]
    assert by_when["C14 (≈ J38)"][1] == "2" and "**02**" in by_when["C14 (≈ J38)"][2]
    assert "déclencheurs Shopify de **06**" in by_when["C14 (≈ J38)"][2]
    for when, level in (("C14 (≈ J38)", "2"), ("C15 (≈ J45)", "3"), ("C17 (option, ≈ J85)", "4")):
        assert by_when[when][1] == level and "revue adverse sans critical/high ouvert" in by_when[when][3], when
    order = _section7().split("Ordre unique : ", 1)[1].split("\n", 1)[0]
    assert order.index("04 et 06 (J8)") < order.index("05, 08, 01, 03 (J26)") < order.index("point zéro C19")
    assert order.rstrip(". ").endswith("07 (J27)")


def test_r4doc04_no_document_activates_02_or_every_workflow_at_j26() -> None:
    stale = ("tous activés à J26", "tous à J26", "tous sauf 07", "**sauf 07**", "activés **sauf 07**")
    rows = {r["ID"]: r for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}
    interventions = D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md")
    b23 = [ln for ln in interventions.splitlines() if ln.startswith("| B23 |") or (ln.startswith("| ☐ |") and "| B23 |" in ln)]
    plan_s4 = next(ln for ln in D4._text("docs/00-pilotage/PLAN_90_JOURS.md").splitlines() if ln.startswith("| S4 |"))
    texts = {"BL-178": rows["BL-178"]["Critère de done"], "PLAN S4": plan_s4, **{f"B23 {i}": t for i, t in enumerate(b23)},
             "§7": _section7()}  # fmt: skip
    assert len(b23) == 2
    for name, text in texts.items():
        for phrase in stale:
            assert phrase not in text, (name, phrase)
        assert re.search(r"02 et les (trois )?déclencheurs Shopify de 06 (au niveau 2|restent inactifs jusqu'au niveau 2|inactifs jusqu'au niveau 2)",
                         text), name  # fmt: skip


def test_r4doc05_c29_blocks_the_s1_alert_and_workflow_07_never_the_activation_of_04() -> None:
    interventions = D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md")
    lines = [ln for ln in interventions.splitlines() if "| C29 |" in ln]
    rows = {r["ID"]: r for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}
    assert len(lines) == 2
    for text in [*lines, rows["BL-194"]["Critère de done"]]:
        assert "Activation des workflows 04" not in text and "activation des workflows 04" not in text
        assert "Alerte immédiate S1" in text and "07" in text
        assert "J8" in text or "BL-186" in text  # 04 est actif par email depuis J8 (B27, BL-186)


def test_gateway_secret_count_is_ten_everywhere() -> None:
    for rel in ("docs/08-agents/README.md", "docs/00-pilotage/PLAN_90_JOURS.md", "docs/00-pilotage/INTERVENTIONS_HUMAINES.md",
                "docs/00-pilotage/DELEGATION_AUTONOMIE.md", "README.md"):  # fmt: skip
        text = D4._text(rel)
        assert not re.search(r"secrets? (par|de) passerelles?[^|.;]{0,20}\(11\b", text), rel
        assert "11 secrets" not in text and "11 passerelles" not in text, rel
    assert "secret par passerelle n8n (10" in D4._text("docs/08-agents/README.md")
    assert "secret par passerelle n8n (10)" in D4._text("docs/00-pilotage/PLAN_90_JOURS.md")


# ======================================================================= revue adverse de sécurité


def test_security_review_document_holds_history_residual_risks_and_procedure() -> None:
    text = REVUE.read_text(encoding="utf-8")
    heads = re.findall(r"^## (.+)$", text, re.M)
    assert heads[:6] == ["1. Règle de passage", "2. Historique des 6 rounds",  # revue R6 : 6e round ajouté
                         "3. Catégories de défauts et principaux correctifs", "4. Risques résiduels connus",
                         "5. Procédure de revue à relancer avant chaque passage de niveau",
                         "6. Décisions de la propriétaire sur les risques résiduels"]  # fmt: skip
    assert heads[-1] == "Validation humaine requise"
    history = text.split("## 2.", 1)[1].split("## 3.", 1)[0]
    assert "**124 signalés**" in history and "**99 confirmés**" in history and "13 / 26 / 32 / 28" in history
    assert [ln.split("|")[1].strip() for ln in history.splitlines() if re.match(r"^\| [1-5] \|", ln)] == list("12345")
    for fix in ("Persistance fail-closed", "Mandat et seuils non auto-signables", "Taux de change de la propriétaire",
                "Matrice d'autorisations, refus par défaut", "Registres dérivés", "Validations de la propriétaire"):
        assert f"**{fix}" in text, fix  # fmt: skip
    # §4.1 : chaque point du round 5 laissé à la documentation par l'agent code est suivi.
    followed = text.split("### 4.1", 1)[1].split("### 4.2", 1)[0]
    for item in ("R4-DOC-04", "R4-DOC-05", "R4-DOC-06", "R3-DOC-06"):
        assert f"| {item}" in followed, item
    # §4.2 : chaque risque a impact, gravité, mitigation, niveau avant lequel le traiter et statut.
    register = text.split("### 4.2", 1)[1].split("## 5.", 1)[0]
    risks = [[c.strip() for c in ln.strip("|").split("|")] for ln in register.splitlines() if re.match(r"^\| RS-\d{2} \|", ln)]
    assert [r[0] for r in risks] == [f"RS-{i:02d}" for i in range(1, len(risks) + 1)] and len(risks) >= 12
    for r in risks:
        assert len(r) == 8 and all(r), r[0]
        assert re.search(r"(critical|high|medium|low)", r[4]), r[0]
        assert re.search(r"[Nn]iveau [234]", r[6]), r[0]
    joined = "\n".join(" ".join(r) for r in risks)
    for limit in ("administre n8n et détient tous les credentials", "contourner les règles `deny`", "Données **FICTIVES**",
                  "vraie boutique Shopify ni un vrai compte PayPal"):  # fmt: skip
        assert limit in joined, limit
    # Aucun finding critical/high n'est acceptable : un risque high ne s'accepte qu'après mitigation vérifiée.
    rule = text.split("## 1.", 1)[1].split("## 2.", 1)[0]
    assert "**revue adverse de sécurité relancée et sans critical/high ouvert**" in rule
    assert "n'est jamais accepté" in rule and "**caduque**" in rule
    procedure = text.split("## 5.", 1)[1].split("## 6.", 1)[0]
    for step in ("**Figer la version**", "**Socle vert**", "**Recheck**", "**Attaque**", "**Gravité**", "**Preuve**",
                 "**Correction**", "**Décision**", "jamais de `DROP` ni de `LIKE` global", "**niveau 2**", "**niveau 3**",
                 "**niveau 4**"):  # fmt: skip
        assert step in procedure, step


def test_security_review_cites_only_existing_paths_and_backlog_tasks() -> None:
    text = REVUE.read_text(encoding="utf-8")
    for cited in set(re.findall(r"`([A-Za-z0-9_.][A-Za-z0-9_.-]*/[A-Za-z0-9_./-]+)`", text)):
        assert (ROOT / cited.rstrip("/")).exists(), cited
    known = {r["ID"] for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}
    assert set(re.findall(r"\bBL-\d{3}\b", text)) <= known


def test_levels_2_3_and_4_require_a_fresh_security_review_everywhere() -> None:
    gates = D4._text("docs/00-pilotage/GATES_GO_NO_GO.md")
    rule = gates.split("## 1.", 1)[1].split("**Les quatre issues", 1)[0]
    assert GATE_RULE in rule and "niveaux **2**" in rule and "**3**" in rule and "**4**" in rule
    assert "REVUE_SECURITE.md" in rule and "**n'est pas relevé**" in rule
    assert re.search(r"^\| 4\.6 \| Revue adverse de sécurité avant le niveau 3", gates, re.M)
    assert re.search(r"^\| 6\.7 \| Revue adverse de sécurité avant le niveau 4", gates, re.M)
    assert "Niveau 2 après G3" in gates and "Revue adverse de sécurité (si le gate relève un niveau d'autonomie)" in gates
    details = {ln.split("|")[1].strip(): ln for ln in D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md").splitlines()
               if re.match(r"^\| [ABC]\d{2} \|", ln)}  # fmt: skip
    for item in ("C14", "C15", "C17"):
        assert GATE_RULE in details[item], item
    assert "REVUE_SECURITE.md" in details["C31"] and all(f"BL-20{n}" in details["C31"] for n in "012")
    rows = {r["ID"]: r for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}
    for level_task, review in (("BL-116", "BL-200"), ("BL-132", "BL-201"), ("BL-146", "BL-202")):
        assert review in {d.strip() for d in rows[level_task]["Dépendances"].split(",")}, level_task
        assert "revue adverse de sécurité relancée et sans critical/high ouvert" in rows[level_task]["Critère de done"]
    matrice = D4._text("docs/08-agents/MATRICE_AUTONOMIE.md")
    assert matrice.count("revue adverse de sécurité relancée et sans critical/high ouvert") >= 4  # niveaux 2, 3, 4 + monter


# ======================================================================= aucune promesse périmée (revue R5)


STALE_R5 = (
    "une commande dont le stock au coût ne couvre pas les lignes est refusée",  # R4-NEW-01 : coût des ventes en attente
    "exige un avoir enregistré",  # R3-NEW-05 : avoir à lignes ≥ coût + retour physique d'un autre jeton
    "tous activés à J26 sauf 07",  # R4-DOC-04
    "Activation des workflows 04 et 07",  # R4-DOC-05
    "secret par passerelle n8n (11",  # R4-DOC-11 : 10 secrets, plus de passerelle 08 pour l'agent 05
    "× 6 ou × 36",  # R2-NEW-01 c : quantités rapprochées
    "Passerelle 08 dépense — secret de l'agent 05",  # R4-DOC-11
    "| sha256sum | cut -d' ' -f1)\" >> empreintes-roles.env",  # R4-DOC-06 : empreinte non portable, jamais contrôlée
)


def test_no_stale_r5_promise_survives_in_the_docs() -> None:
    extra = ("docs/00-pilotage/REVUE_SECURITE.md", "docs/08-agents/MATRICE_API.md", "db/README.md")
    for path in [*(ROOT / rel for rel in (*D4.DOC_SET, *extra)), *D4._agent_docs()]:
        text = path.read_text(encoding="utf-8")
        for phrase in STALE_R5:
            assert phrase not in text, f"{path.relative_to(ROOT)} : « {phrase} »"
