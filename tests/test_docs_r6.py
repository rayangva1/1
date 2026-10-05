"""Docs de la revue R6 (clôture) tenues contre le code et le plan.

* R5C-DOC-01 : la revue du niveau 2 est planifiée **après** le câblage de 02 (BL-199), dont elle dépend.
* R5C-DOC-02 : le connecteur publicitaire, construit après la hausse au niveau 3, a sa revue limitée à son diff
  (BL-203) avant la première campagne ; la règle est écrite au §1 de la revue et partout où le niveau 3 est décrit.
* R5C-DOC-03 : chaque acte de la propriétaire « à traiter avant le niveau 2 » (RS-02, RS-03, RS-11, RS-12, RS-15) a sa
  fiche, sa tâche de backlog datée avant la revue (qui en dépend) et sa place au plan.
* R5C-DOC-04, -06, -08, -09, -10 : registre des risques exact (RS-16, RS-14, RS-11, empreintes, dossier des jetons).
* Rotation (RS-12) : la procédure de ``DELEGATION_AUTONOMIE.md`` §10 étape 8 est exécutée **telle qu'écrite** sur une
  copie du fichier de variables ; l'API relancée refuse l'ancien jeton et accepte le nouveau ; un fichier invalide ne
  change rien.
Données, jetons et montants FICTIFS ; aucun réseau, aucune base PostgreSQL ; tout s'écrit sous ``tmp_path``.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import test_docs_r4 as D4
import test_orchestration_f4 as F
from fastapi.testclient import TestClient
from pokeshop.api import API_TOKEN_HEADER, Services, create_app
from pokeshop.incidents import LogNotifier
from pokeshop.settings import load_settings
from pokeshop.stoploss import hash_owner_token

ROOT = Path(__file__).resolve().parents[1]
REVUE = ROOT / "docs/00-pilotage/REVUE_SECURITE.md"
LEVEL2_REVIEW = "BL-200"


def _backlog() -> dict[str, dict[str, str]]:
    return {r["ID"]: r for r in csv.DictReader(io.StringIO(D4._text("docs/00-pilotage/BACKLOG.csv")))}


def _day(text: str) -> int:
    return min(int(n) for n in re.findall(r"\bJ(\d+)\b", text))


def _deps(row: dict[str, str]) -> set[str]:
    return {d.strip() for d in row["Dépendances"].split(",") if d.strip()}


def _risk(rid: str) -> list[str]:
    line = next(ln for ln in REVUE.read_text(encoding="utf-8").splitlines() if ln.startswith(f"| {rid} |"))
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _revue_section(start: str, end: str) -> str:
    text = REVUE.read_text(encoding="utf-8")
    return text.split(start, 1)[1].split(end, 1)[0]


def _fiches() -> dict[str, str]:
    details = D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md").split("## 2.", 1)[1]
    return {m.group(1): ln for ln in details.splitlines() if (m := re.match(r"^\| ([ABC]\d{2}) \|", ln))}


def _checklist() -> list[str]:
    text = D4._text("docs/00-pilotage/INTERVENTIONS_HUMAINES.md")
    return [ln for ln in text.split("## 1.", 1)[1].split("## 2.", 1)[0].splitlines() if ln.startswith("| ☐ |")]


def _plan_week(week: str) -> str:
    return next(ln for ln in D4._text("docs/00-pilotage/PLAN_90_JOURS.md").splitlines() if ln.startswith(f"| {week} |"))


# ======================================================================= R5C-DOC-01 : 02 câblé avant la revue


def test_r5cdoc01_level_2_review_runs_after_workflow_02_is_wired() -> None:
    rows = _backlog()
    assert "BL-199" in _deps(rows[LEVEL2_REVIEW])
    assert _day(rows["BL-199"]["Échéance"]) < _day(rows[LEVEL2_REVIEW]["Échéance"]) < _day(rows["BL-116"]["Échéance"])
    assert {"BL-199", LEVEL2_REVIEW} <= _deps(rows["BL-116"])
    c31_j36 = next(ln for ln in _checklist() if "| J36 | C31 |" in ln)
    assert "BL-199" in c31_j36 and "B28 à B31" in c31_j36
    assert "(199" in _plan_week("S5") and "(199)" not in _plan_week("S6")
    rule = _revue_section("## 1.", "## 2.")
    assert "**Ordre**" in rule and "BL-199" in rule and "jamais avant" in rule


# ======================================================================= R5C-DOC-02 : connecteur publicitaire revu


def test_r5cdoc02_ad_connector_is_reviewed_on_its_diff_before_the_first_campaign() -> None:
    rows = _backlog()
    assert {"BL-198", "BL-201"} <= _deps(rows["BL-203"]) and rows["BL-203"]["Agent/rôle"].startswith("Propriétaire")
    assert _day(rows["BL-198"]["Échéance"]) <= _day(rows["BL-203"]["Échéance"]) < 50  # option B : test dès J50
    assert "BL-203" in _deps(rows["BL-133"]) and "(BL-203" in rows["BL-198"]["Critère de done"]
    assert "revu à part avant la première campagne (BL-203)" in rows["BL-201"]["Critère de done"]
    rule = _revue_section("## 1.", "## 2.")
    assert "**Composant ajouté après la hausse de niveau**" in rule and "BL-203" in rule
    assert "BL-203" in _risk("RS-09")[6] and "première campagne" in _risk("RS-09")[6]
    section7 = D4._text("orchestration/README.md").split("## 7.", 1)[1].split("## 8.", 1)[0]
    c15 = next(ln for ln in section7.splitlines() if ln.startswith("| C15 (≈ J45) |"))
    assert "BL-203" in c15 and "première campagne" in c15
    level3 = next(ln for ln in D4._text("docs/08-agents/MATRICE_AUTONOMIE.md").splitlines() if ln.startswith("| **3** |"))
    assert "BL-203" in level3
    g4 = D4._text("docs/00-pilotage/GATES_GO_NO_GO.md").split("### G4 ", 1)[1].split("### G5 ", 1)[0]
    assert "BL-203" in g4 and "dès J46" not in g4
    assert "BL-203" in D4._text("docs/06-contenu/PUBLICITE_TEST.md")
    attack = _revue_section("## 5.", "## 6.")
    assert "connecteur publicitaire et stop-loss pub (RS-09)" not in attack and "BL-203" in attack
    assert any("| J49 | C31 |" in ln and "diff du connecteur publicitaire" in ln for ln in _checklist())


# ======================================================================= R5C-DOC-03 : actes avant le niveau 2


def test_r5cdoc03_every_owner_act_before_level_2_is_planned_and_gates_the_review() -> None:
    rows, fiches = _backlog(), _fiches()
    review_day = _day(rows[LEVEL2_REVIEW]["Échéance"])
    for rid, task in (("RS-02", "BL-204"), ("RS-03", "BL-205"), ("RS-11", "BL-207"), ("RS-12", "BL-206"),
                      ("RS-15", "BL-205"), ("RS-16", "BL-204")):  # fmt: skip
        assert task in _risk(rid)[6], (rid, task)
        row = rows[task]
        assert row["Agent/rôle"].startswith("Propriétaire") and row["Validation humaine (O/N)"] == "O", task
        assert _day(row["Échéance"]) < review_day and task in _deps(rows[LEVEL2_REVIEW]), task
        holders = [ident for ident, line in fiches.items() if task in line.rsplit("|", 2)[-2]]
        assert len(holders) == 1 and holders[0].startswith("B"), (task, holders)
        assert any(f"| {holders[0]} |" in ln for ln in _checklist()), holders[0]
        assert f"({task[3:]})" in _plan_week("S5"), task
    level2 = next(ln for ln in _revue_section("### 4.3", "## 5.").splitlines() if ln.startswith("| 2 (C14"))
    assert all(f"RS-{n:02d}" in level2 for n in (1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 14, 15, 16))
    assert "treize risques avant le niveau 2" in fiches["C31"]


# ======================================================================= R5C-DOC-04 : troncature par un superutilisateur


def test_r5cdoc04_superuser_truncation_is_registered_and_restart_claims_are_nuanced() -> None:
    rs16 = _risk("RS-16")
    assert "superutilisateur" in rs16[1] and "levé au redémarrage" in rs16[3] and "high" in rs16[4]
    assert "BL-204" in rs16[6] and "hors base" in rs16[6]
    rs02 = _risk("RS-02")
    assert "superutilisateur" in rs02[3] and "RS-16" in rs02[3] and "docker" in rs02[3]
    persistence = next(ln for ln in _revue_section("## 3.", "## 4.").splitlines() if "**Persistance fail-closed**" in ln)
    assert "RS-16" in persistence
    stop_loss = D4._text("docs/00-pilotage/STOP_LOSS.md")
    assert "un redémarrage ne lève jamais un gel enregistré. **Limite** (revue R6, RS-16)" in stop_loss
    assert "RS-16" in D4._text("db/README.md")


# ======================================================================= R5C-DOC-06, -08 : RS-14 et RS-11 exacts


def test_r5cdoc06_rs14_states_the_dangerous_side_of_underestimated_invoice_lines() -> None:
    impact = _risk("RS-14")[3]
    assert "étoile polaire" in impact and "stop-loss Temps" in impact and "stop-loss pub" in impact
    assert "jamais plus tard (côté prudent)" not in REVUE.read_text(encoding="utf-8")


def test_r5cdoc08_every_active_workflow_runs_in_the_pinned_n8n_before_activation() -> None:
    rows, treatment = _backlog(), _risk("RS-11")[6]
    assert "**tous** les workflows" in treatment and "N8N_IMAGE" in treatment
    for wf in ("02", "04", "05", "06", "07", "08", "01", "03"):
        assert wf in treatment, wf
    assert "N8N_IMAGE" in rows["BL-186"]["Critère de done"] and "BL-207" in rows["BL-178"]["Critère de done"]
    assert "déclencheurs Shopify de 06" in rows["BL-207"]["Critère de done"] and "BL-199" in _deps(rows["BL-207"])
    assert any("| J8 | B31 |" in ln and "N8N_IMAGE" in ln for ln in _checklist())


# ======================================================================= R5C-DOC-09 : trois empreintes, trois fermetures


STALE_FINGERPRINT = (
    "empreinte différente du fichier = démarrage gelé",
    "une empreinte différente gèle le service",
    "avec une empreinte différente du fichier, le service démarre gelé",
    "Une configuration modifiée sans signature ou incohérente démarre aussi le service gelé",
    "différentes du fichier : service gelé jusqu'à nouvelle signature",
    "empreinte différente : service gelé)",
)


def test_r5cdoc09_each_fingerprint_is_described_in_its_own_way_everywhere() -> None:
    for rel in ("docs/00-pilotage/REVUE_SECURITE.md", "docs/00-pilotage/STOP_LOSS.md",
                "docs/00-pilotage/DELEGATION_AUTONOMIE.md", "docs/00-pilotage/INTERVENTIONS_HUMAINES.md"):  # fmt: skip
        text = D4._text(rel)
        for phrase in STALE_FINGERPRINT:
            assert phrase not in text, (rel, phrase)
    mandate_row = next(ln for ln in _revue_section("## 3.", "## 4.").splitlines() if "**Mandat et seuils" in ln)
    stop_loss = D4._text("docs/00-pilotage/STOP_LOSS.md")
    for text in (mandate_row, stop_loss):
        assert "mandat **inactif**" in text or "**mandat inactif**" in text
        assert "stop-loss **non chargé**" in text or "**stop-loss non chargé**" in text
        assert "`CONFIG_UNSIGNED`" in text


# ======================================================================= R5C-DOC-10 : dossier des jetons, machine de la flotte


def test_r5cdoc10_token_folder_is_denied_and_the_fleet_machine_is_written() -> None:
    deny = json.loads(D4._text(".claude/settings.json"))["permissions"]["deny"]
    spec = importlib.util.spec_from_file_location("verifier_agents_r6", ROOT / "docs/08-agents/outils/verifier_agents.py")
    assert spec is not None and spec.loader is not None
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    for rule in ("Read(~/pokeshop-jetons/**)", "Edit(~/pokeshop-jetons/**)"):
        assert rule in deny and rule in verifier.REQUIRED_DENY, rule
    assert verifier.check_secret_permissions(ROOT) == []
    assert "jamais sur la machine des agents" not in REVUE.read_text(encoding="utf-8")
    runbook = D4._text("docs/08-agents/RUNBOOK.md").split("## 2.", 1)[1].split("## 3.", 1)[0]
    assert "**Machine et compte de la flotte**" in runbook and "verifier_isolation.py" in runbook
    assert "jamais sous votre compte" in runbook and "`docker`" in runbook
    assert "**b. Ranger, sur votre ordinateur, aussitôt après a**" in D4._text("docs/00-pilotage/DELEGATION_AUTONOMIE.md")


# ======================================================================= RS-12 : rotation exécutée telle qu'écrite


def _step8() -> str:
    return D4._section(D4._text(D4.DELEGATION), "8. **Remplacer un jeton de rôle ou un secret", "**Modifier**")


def _rotation_blocks() -> tuple[str, str]:
    blocks = D4._bash_blocks(_step8())
    server = re.search(r"bash <<'FIN'\n.*?\nFIN\n", blocks[1], re.S)
    assert len(blocks) == 2 and server is not None
    return blocks[0], server.group(0)


@pytest.mark.skipif(not all(shutil.which(t) for t in ("bash", "openssl", "sha256sum", "shred")),
                    reason="outils de la procédure absents")  # fmt: skip
def test_rotation_procedure_runs_as_written_and_the_restarted_api_refuses_the_old_token(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    run = lambda script: subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)  # noqa: E731
    assert run(D4._generation_block()).returncode == 0
    folder = home / "pokeshop-jetons"
    old_tokens = dict(ln.split("\t", 1) for ln in (folder / "jetons-roles.txt").read_text().splitlines())
    api_env = tmp_path / "api.env"
    api_env.write_text("POKESHOP_ENV=dev\nPOSTGRES_PASSWORD=FICTIF-mot-de-passe\n" + (folder / "empreintes-roles.env").read_text()
                       + "POKESHOP_N8N_WEBHOOK_SECRET=\n")  # fmt: skip
    api_env.chmod(0o600)
    before = api_env.read_text().splitlines()
    owner_block, server_block = _rotation_blocks()
    server_block = server_block.replace("/etc/pokeshop/api.env", str(api_env))
    # a. sur l'ordinateur de la propriétaire, tel qu'écrit (rôle qa-conformite)
    out = run(owner_block)
    assert out.returncode == 0, out.stderr
    role, new_token = (folder / "rotation-jeton.txt").read_text().rstrip("\n").split("\t")
    assert role == "qa-conformite" and re.fullmatch(r"[0-9a-f]{64}", new_token) and new_token != old_tokens[role]
    for name in ("rotation-jeton.txt", "rotation.env"):
        assert oct((folder / name).stat().st_mode & 0o777) == "0o600", name
    assert run(owner_block).returncode != 0  # rotation en cours : refus, rien n'est écrasé
    assert (folder / "rotation-jeton.txt").read_text().endswith(f"\t{new_token}\n")
    # c. transfert (« scp » remplacé par une copie) puis remplacement en place sur le serveur
    shutil.copy(folder / "rotation.env", home / "rotation.env")
    out = run(server_block)
    assert out.returncode == 0, out.stderr
    after = api_env.read_text().splitlines()
    var = "POKESHOP_ROLE_TOKEN_SHA256_QA_CONFORMITE"
    assert [ln for ln in after if ln.startswith(f"{var}=")] == [f"{var}={hash_owner_token(new_token)}"]
    assert sorted(ln for ln in after if not ln.startswith(f"{var}=")) == sorted(ln for ln in before if not ln.startswith(f"{var}="))
    assert oct(api_env.stat().st_mode & 0o777) == "0o600" and not (home / "rotation.env").exists()
    # API relancée avec le fichier modifié : ancien jeton 401, nouveau 200, les 16 autres inchangés.
    values = dict(ln.split("=", 1) for ln in after if ln.startswith("POKESHOP_ROLE_TOKEN_SHA256_"))
    settings = load_settings({**values, "POKESHOP_OWNER_TOKEN_SHA256": hash_owner_token(F.OWNER_TOKEN),
                              "POKESHOP_STATE_DIR": str(tmp_path / "etat")})  # fmt: skip
    client = TestClient(create_app(services=Services.build(settings, clock=F.Clock(F.NOW), notifier=LogNotifier())))
    assert client.get("/incidents", headers={API_TOKEN_HEADER: old_tokens["qa-conformite"]}).status_code == 401
    assert client.get("/incidents", headers={API_TOKEN_HEADER: new_token}).status_code == 200
    for other, token in old_tokens.items():
        if other != "qa-conformite":
            assert client.get("/incidents", headers={API_TOKEN_HEADER: token}).status_code == 200, other
    # Fichier invalide, variable absente ou valeur tronquée : rien n'est changé.
    reference = api_env.read_bytes()
    for bad in (f"{var}={'a' * 64}\n{var}={'b' * 64}\n", f"POKESHOP_ROLE_TOKEN_SHA256_INCONNU={'c' * 64}\n",
                f"{var}={'d' * 63}\n", f"POSTGRES_PASSWORD={'e' * 64}\n"):  # fmt: skip
        (home / "rotation.env").write_text(bad)
        assert run(server_block).returncode != 0, bad
        assert api_env.read_bytes() == reference, bad
    # e. secret du moteur : même bloc, la ligne vide de .env.example est remplacée, les empreintes ne bougent pas.
    secret = "f" * 64
    (home / "rotation.env").write_text(f"POKESHOP_N8N_WEBHOOK_SECRET={secret}\n")
    assert run(server_block).returncode == 0
    final = api_env.read_text().splitlines()
    assert f"POKESHOP_N8N_WEBHOOK_SECRET={secret}" in final and "POKESHOP_N8N_WEBHOOK_SECRET=" not in final
    assert sum(ln.startswith("POKESHOP_ROLE_TOKEN_SHA256_") for ln in final) == 17


# ======================================================================= §7 : clôture du round 6


ROUND6 = ("R5-NEW-01", "R5-NEW-02", *(f"R5C-DOC-{n:02d}" for n in range(1, 11)))


def test_round6_closure_section_gives_a_final_status_for_every_point() -> None:
    text = REVUE.read_text(encoding="utf-8")
    assert "## 7. Round 6 (clôture)" in text
    closure = text.split("## 7. Round 6 (clôture)", 1)[1].split("## Validation humaine requise", 1)[0]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in closure.splitlines() if ln.startswith("| R5")]
    assert [r[0] for r in rows] == list(ROUND6)
    for r in rows:
        assert len(r) == 6 and all(r), r[0]
        assert r[1] in ("medium", "low") and r[3].startswith("Corrigé"), r[0]
    history = _revue_section("## 2.", "## 3.")
    assert re.search(r"^\| 6 \(clôture\) \| .*\| 0 / 0 / 5 / 7 \|", history, re.M)
    assert sum(r[1] == "medium" for r in rows) == 5 and sum(r[1] == "low" for r in rows) == 7


# ======================================================================= aucune promesse périmée (revue R6)


STALE_R6 = (
    "SKU inconnu du catalogue validé : 409",  # R5-NEW-02 : jamais refusée pour un SKU
    "jamais sur la machine des agents",  # R5C-DOC-10 : aucune procédure ne le garantissait
    "webhook limité au réseau interne",  # R5C-DOC-07
    "gel plus tôt et jamais plus tard",  # R5C-DOC-06
    "test dès J46",  # R5C-DOC-02 : jamais de campagne avant BL-198 et BL-203
    "BL-198, J49",  # BL-198 à J48, puis BL-203 à J49
    "connecteur publicitaire recetté (BL-198), revue adverse sans critical/high ouvert |",  # R5C-DOC-02
)


def test_no_stale_r6_promise_survives_in_the_docs() -> None:
    extra = ("docs/00-pilotage/REVUE_SECURITE.md", "docs/08-agents/MATRICE_API.md", "db/README.md",
             "docs/06-contenu/CALENDRIER_90J.csv")  # fmt: skip
    for path in [*(ROOT / rel for rel in (*D4.DOC_SET, *extra)), *D4._agent_docs()]:
        text = path.read_text(encoding="utf-8")
        for phrase in STALE_R6:
            assert phrase not in text, f"{path.relative_to(ROOT)} : « {phrase} »"
