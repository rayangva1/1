"""Pile docker compose, image de l'API et démarrage documenté (E2E-18, E2E-22, E2E-23, E2E-25).

* Moindre privilège : aucun service ne charge ``.env`` en entier ; l'API ne reçoit que des variables
  ``POKESHOP_*`` (ni ``POSTGRES_PASSWORD`` ni ``N8N_ENCRYPTION_KEY``) et se connecte avec le compte du
  moteur, jamais l'administrateur ; n8n ne reçoit aucun jeton du moteur.
* ``WEBHOOK_URL`` et ``N8N_RESTRICT_FILE_ACCESS_TO`` sont réellement câblés dans n8n.
* ``.dockerignore`` : secrets et caches hors du contexte de construction.
* Le démarrage du README est exécutable tel quel : chaque variable obligatoire est nommée.
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
    "POKESHOP_API_TOKEN_SHA256": "1" * 64,
    "POKESHOP_OWNER_TOKEN_SHA256": "2" * 64,
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
    for step in ("cp .env.example .env", "docker compose config --quiet", "docker compose up -d db db-migrate db-backup api n8n"):
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
