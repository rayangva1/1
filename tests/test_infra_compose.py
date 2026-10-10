"""Pile docker compose, image de l'API et démarrage documenté (E2E-18, E2E-22, E2E-23, E2E-25).

* Moindre privilège : aucun service ne charge ``.env`` en entier ; l'API ne reçoit que des variables
  ``POKESHOP_*`` (ni ``POSTGRES_PASSWORD`` ni ``N8N_ENCRYPTION_KEY``) et se connecte avec le compte du
  moteur, jamais l'administrateur ; n8n ne reçoit aucun jeton du moteur.
* ``WEBHOOK_URL`` et ``N8N_RESTRICT_FILE_ACCESS_TO`` sont réellement câblés dans n8n.
* ``.dockerignore`` : secrets et caches hors du contexte de construction.
* Le démarrage du README est exécutable tel quel : chaque variable obligatoire est nommée.
* Revue SEC-13 : le fichier de secrets vit **hors du dépôt** (``/etc/pokeshop/api.env``) ; aucun document
  de démarrage ne fait créer un ``.env`` à la racine ; ``scripts/compose.sh`` refuse un ``.env`` dans le dépôt,
  un fichier de variables dans le dépôt ou lisible par d'autres ; ``.gitignore`` couvre les secrets.
* Revue CON-10 : le service ``db-backup`` a un healthcheck ``db/backup.sh etat`` (R-I04).
``docker compose config`` est exécuté si Docker Compose est présent (aucun conteneur lancé).
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES: dict[str, Any] = COMPOSE["services"]
REQUIRED = sorted(set(re.findall(r"\$\{([A-Z0-9_]+):\?", (ROOT / "docker-compose.yml").read_text(encoding="utf-8"))))
FAKE_VARS = {
    "POSTGRES_PASSWORD": "fictif-admin-pg-0123456789",
    "POKESHOP_DB_PASSWORD": "fictif-moteur-pg-0123456789",
    "N8N_ENCRYPTION_KEY": "fictif-n8n-key-0123456789abcdef",
    "POKESHOP_OWNER_TOKEN_SHA256": "2" * 64,
    # Revue R3 : jeton commun facultatif ; jetons par rôle sans lesquels le stop-loss n'est jamais évaluable.
    "POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS": "3" * 64,
    "POKESHOP_ROLE_TOKEN_SHA256_CONNECTEUR_TRESORERIE": "4" * 64,
    "POKESHOP_ROLE_TOKEN_SHA256_FINANCE_PRICING": "5" * 64,
}
SECRETS_OF_OTHERS = {"api": ("POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY"), "n8n": ("POSTGRES_PASSWORD", "POKESHOP_")}


def _env(service: str) -> dict[str, str]:
    env = SERVICES[service].get("environment", {})
    assert isinstance(env, dict), f"{service} : environnement en dictionnaire"
    return {k: str(v) for k, v in env.items()}


def test_no_service_loads_the_whole_env_file() -> None:
    for name, service in SERVICES.items():
        assert "env_file" not in service, f"{name} : env_file transmettrait tous les secrets du fichier .env"


def test_api_receives_only_engine_variables_and_the_engine_login() -> None:
    env = _env("api")
    assert all(k.startswith("POKESHOP_") or k == "TZ" for k in env), sorted(env)
    text = " ".join(env.values())
    for secret in SECRETS_OF_OTHERS["api"]:
        assert secret not in text, f"l'API ne doit pas recevoir {secret}"
    url = env["POKESHOP_DATABASE_URL"]
    assert url.startswith("postgresql://api_moteur:${POKESHOP_DB_PASSWORD") and "pokeshop_admin" not in url
    assert env["POKESHOP_N8N_WEBHOOK_URL"] == "http://n8n:5678/webhook/pokeshop-incidents"
    assert env["POKESHOP_DRY_RUN"] == "${POKESHOP_DRY_RUN:-true}"  # simulation par défaut


def test_n8n_has_webhook_url_and_file_restriction_but_no_engine_secret() -> None:
    env = _env("n8n")
    assert env["WEBHOOK_URL"] == "${N8N_WEBHOOK_URL:-}"
    assert env["N8N_RESTRICT_FILE_ACCESS_TO"] == "/data/imports"
    assert not any(k.startswith("POKESHOP_") for k in env)
    assert "POSTGRES_PASSWORD" not in " ".join(env.values())
    mounts = SERVICES["n8n"]["volumes"]
    assert "imports:/data/imports" in mounts and "imports:/data/imports:ro" in SERVICES["api"]["volumes"]


def test_engine_login_is_created_by_the_migration_job_and_backups_run() -> None:
    entry = " ".join(SERVICES["db-migrate"]["entrypoint"])
    assert "/db/apply.sh none" in entry and "/db/engine_login.sh" in entry
    assert _env("db-migrate")["POKESHOP_DB_USER"] == "api_moteur"
    backup = SERVICES["db-backup"]
    assert backup["entrypoint"] == ["bash", "/db/backup.sh", "boucle"]
    assert _env("db-backup")["POKESHOP_BACKUP_DIR"] == "/sauvegardes" and "backups:/sauvegardes" in backup["volumes"]
    for name in ("engine_login.sh", "backup.sh"):
        assert (ROOT / "db" / name).stat().st_mode & 0o111, f"db/{name} exécutable"


def test_every_required_variable_is_documented_in_env_example_and_readme() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert set(REQUIRED) == set(FAKE_VARS), REQUIRED
    for var in REQUIRED:
        assert re.search(rf"^{var}=$", example, re.M), f".env.example : {var}= (vide, à remplir depuis le coffre)"
        assert var in readme, f"README : {var} à remplir avant docker compose"
    for step in ('sudo install -D -m 600 -o "$USER" .env.example /etc/pokeshop/api.env', "scripts/compose.sh config --quiet",
                 "scripts/compose.sh up -d db db-migrate db-backup api n8n"):
        assert step in readme, step
    assert re.search(r"^N8N_WEBHOOK_URL=$", example, re.M)
    # E2E-13 : avec la configuration documentée, les incidents partent réellement vers le workflow 04.
    assert re.search(r"^POKESHOP_NOTIFY_DRY_RUN=false$", example, re.M)
    assert _env("api")["POKESHOP_NOTIFY_DRY_RUN"] == "${POKESHOP_NOTIFY_DRY_RUN:-false}"


def _ignored(rel: str, patterns: list[str]) -> bool:
    parts = rel.split("/")
    for pattern in patterns:
        pat = pattern.rstrip("/")
        if pat.startswith("**/"):
            if any(fnmatch.fnmatch(p, pat[3:]) for p in parts) or fnmatch.fnmatch(rel, pat[3:]):
                return True
        elif fnmatch.fnmatch(rel, pat) or any(fnmatch.fnmatch("/".join(parts[: i + 1]), pat) for i in range(len(parts))):
            return True
    return False


def test_dockerignore_excludes_secrets_and_caches_but_keeps_the_image_sources() -> None:
    patterns = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for rel in (".env", ".env.local", "prod.env", "secrets/coffre.txt", ".git/config",
                "engine/.mypy_cache/x.json", ".mypy_cache/3.11/x.json", "engine/pokeshop/__pycache__/api.cpython-311.pyc",
                ".ruff_cache/x", ".pytest_cache/v", "dashboard/out/index.html", "docs/SPEC.md", "orchestration/n8n/01.json"):
        assert _ignored(rel, patterns), f"{rel} doit être exclu du contexte de construction"
    copied = re.findall(r"^COPY (\S+)/ ", (ROOT / "Dockerfile").read_text(encoding="utf-8"), re.M)
    assert copied == ["engine", "config", "data"]
    for rel in ("engine/pokeshop/api.py", "config/pricing_rules.v1.yaml", "data/samples/FICTIF_offres_grossiste_a.csv"):
        assert not _ignored(rel, patterns), f"{rel} est nécessaire à l'image"


DOCKER = shutil.which("docker")


def _compose_config(tmp_path: Path, values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "variables_compose.txt"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return subprocess.run(
        [DOCKER or "docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "docker-compose.yml"),
         "--env-file", str(env_file), "config", "--format", "json"],
        capture_output=True, text=True, timeout=60, check=False,
    )


@pytest.mark.skipif(DOCKER is None, reason="docker absent : docker compose config non exécuté")
def test_docker_compose_config_with_documented_variables(tmp_path: Path) -> None:
    probe = subprocess.run([DOCKER or "docker", "compose", "version"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        pytest.skip("plugin docker compose absent")
    # .env.example copié tel quel : échec explicite (variable du coffre manquante), rien n'est lancé.
    example = {
        k: v for k, v in re.findall(r"^([A-Z0-9_]+)=(.*)$", (ROOT / ".env.example").read_text(encoding="utf-8"), re.M)
    }
    bare = _compose_config(tmp_path, example)
    assert bare.returncode != 0 and "missing a value" in bare.stderr
    # Variables remplies : configuration valide ; chaque service ne reçoit que ses variables.
    import json

    ok = _compose_config(tmp_path, {**example, **FAKE_VARS})
    assert ok.returncode == 0, ok.stderr
    services = json.loads(ok.stdout)["services"]
    api_env = services["api"]["environment"]
    assert FAKE_VARS["POSTGRES_PASSWORD"] not in json.dumps(api_env)
    assert FAKE_VARS["N8N_ENCRYPTION_KEY"] not in json.dumps(api_env)
    assert api_env["POKESHOP_DATABASE_URL"].startswith("postgresql://api_moteur:")
    n8n_env = services["n8n"]["environment"]
    assert not any(v in json.dumps(n8n_env) for v in (FAKE_VARS["POKESHOP_DB_PASSWORD"], FAKE_VARS["POSTGRES_PASSWORD"]))
    assert n8n_env["N8N_RESTRICT_FILE_ACCESS_TO"] == "/data/imports" and "WEBHOOK_URL" in n8n_env


# =============================================================================== SEC-13 : secrets hors du dépôt

START_DOCS = ("README.md", "docker-compose.yml", ".env.example", "orchestration/README.md", "db/README.md")


def test_sec13_no_startup_doc_creates_a_secret_file_inside_the_repository() -> None:
    for rel in START_DOCS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for bad in ("cp .env.example .env", "Copier en .env", "dans `.env`", "de `.env`", "dans .env ("):
            assert bad not in text, f"{rel} : « {bad} » ferait créer le fichier de secrets dans le dépôt"
    assert "/etc/pokeshop/api.env" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'sudo install -D -m 600 -o "$USER" .env.example /etc/pokeshop/api.env' in (ROOT / ".env.example").read_text(encoding="utf-8")


def _git_ignored(rel: str) -> bool:
    out = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", rel], check=False)
    return out.returncode == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_sec13_gitignore_covers_secret_files_but_keeps_the_example() -> None:
    for rel in (".env", ".env.local", ".env.prod", "prod.env", "api.env", "secrets/coffre.txt", "config/cle.key",
                "certs/serveur.pem"):
        assert _git_ignored(rel), f"{rel} doit être ignoré par git"
    assert not _git_ignored(".env.example")


COMPOSE_SH = ROOT / "scripts" / "compose.sh"


def _compose_sh(env_file: Path, *args: str, repo_env: bool = False) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", "POKESHOP_ENV_FILE": str(env_file), "POKESHOP_DOCKER_BIN": "echo"}
    return subprocess.run(["bash", str(COMPOSE_SH), *args], capture_output=True, text=True, env=env, check=False)


def test_sec13_compose_wrapper_uses_an_env_file_outside_the_repository(tmp_path: Path) -> None:
    assert COMPOSE_SH.stat().st_mode & 0o111, "scripts/compose.sh exécutable"
    missing = _compose_sh(tmp_path / "absent.env", "config")
    assert missing.returncode == 1 and "introuvable" in missing.stderr
    env_file = tmp_path / "api.env"
    env_file.write_text("POSTGRES_PASSWORD=fictif\n", encoding="utf-8")
    env_file.chmod(0o644)
    loose = _compose_sh(env_file, "config")
    assert loose.returncode == 1 and "mode 644" in loose.stderr and "fictif" not in loose.stderr
    env_file.chmod(0o600)
    ok = _compose_sh(env_file, "config", "--quiet")
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.split() == ["compose", "--project-directory", str(ROOT), "-f", str(ROOT / "docker-compose.yml"),
                                 "--env-file", str(env_file), "config", "--quiet"]
    inside = ROOT / "tests" / "__fictif_api.env"
    try:
        inside.write_text("X=1\n", encoding="utf-8")
        inside.chmod(0o600)
        refused = _compose_sh(inside, "config")
        assert refused.returncode == 1 and "dans le dépôt" in refused.stderr
    finally:
        inside.unlink(missing_ok=True)


def test_sec13_compose_wrapper_refuses_a_dotenv_at_the_repository_root(tmp_path: Path) -> None:
    env_file = tmp_path / "api.env"
    env_file.write_text("X=1\n", encoding="utf-8")
    env_file.chmod(0o600)
    stray = ROOT / ".env"
    if stray.exists():
        pytest.skip(".env présent à la racine du dépôt : à déplacer hors du dépôt (SEC-13)")
    try:
        stray.write_text("POSTGRES_PASSWORD=fictif\n", encoding="utf-8")
        refused = _compose_sh(env_file, "up", "-d")
        assert refused.returncode == 1 and "dépôt" in refused.stderr and refused.stdout == ""
    finally:
        stray.unlink(missing_ok=True)


# =============================================================================== CON-10 : R-I04 vérifiable


def test_con10_backup_service_health_is_the_last_verified_restore() -> None:
    backup = SERVICES["db-backup"]
    assert backup["healthcheck"]["test"] == ["CMD", "bash", "/db/backup.sh", "etat"]
    assert _env("db-backup")["POKESHOP_BACKUP_MAX_AGE_HOURS"] == "${POKESHOP_BACKUP_MAX_AGE_HOURS:-36}"


def _etat(backup_dir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(ROOT / "db" / "backup.sh"), "etat"], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "POKESHOP_BACKUP_DIR": str(backup_dir), **env}, check=False)


def test_con10_backup_state_is_fail_closed_without_a_recent_verified_restore(tmp_path: Path) -> None:
    import time

    none = _etat(tmp_path)
    assert none.returncode == 1 and "aucune restauration vérifiée" in none.stderr
    trace = tmp_path / "derniere-verification.tsv"
    trace.write_text(f"{int(time.time())}\t2026-10-05T06:00:00Z\tpokeshop-x.dump\t{'a' * 64}\n", encoding="utf-8")
    ok = _etat(tmp_path)
    assert ok.returncode == 0 and ok.stdout.startswith("OK : restauration vérifiée")
    trace.write_text(f"{int(time.time()) - 40 * 3600}\tancienne\tpokeshop-x.dump\t{'a' * 64}\n", encoding="utf-8")
    old = _etat(tmp_path)
    assert old.returncode == 1 and "R-I04 non satisfait" in old.stderr
    assert _etat(tmp_path, POKESHOP_BACKUP_MAX_AGE_HOURS="48").returncode == 0
    trace.write_text("illisible\n", encoding="utf-8")
    assert _etat(tmp_path).returncode == 1
