"""Sauvegarde ET test de restauration réels (CON-10, BP §6) : ``db/backup.sh`` contre un PostgreSQL local.

Base jetable (migrations + jeu FICTIF + journaux d'état écrits par le moteur), compte superutilisateur
temporaire (mot de passe aléatoire), sauvegardes dans un dossier temporaire hors du dépôt. Chaque test
supprime ses bases et son compte. Ignoré si PostgreSQL ou psycopg est absent. Données FICTIVES.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pokeshop.audit import PostgresAuditLog, PostgresStateJournal

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "db"
MIGRATIONS = sorted((DB_DIR / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
SEEDS = [DB_DIR / "seeds" / "reference_seed.sql", DB_DIR / "seeds" / "fictif_seed.sql"]
BACKUP = DB_DIR / "backup.sh"
ENGINE_LOGIN = DB_DIR / "engine_login.sh"


def _psql(sql: str, db: str = "postgres") -> subprocess.CompletedProcess[str]:
    prefix = ["runuser", "-u", "postgres", "--"] if hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser") else []
    return subprocess.run([*prefix, shutil.which("psql") or "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                           "-d", db, "-f", "-"], input=sql, capture_output=True, text=True, timeout=120, check=False)


class Server:
    def __init__(self, admin: str, password: str) -> None:
        self.admin, self.password = admin, password
        self.databases: list[str] = []
        # Revue R5 (R4-NEW-03) : préfixe PROPRE à ce test pour les bases jetables de `db/backup.sh verifier` ; le test
        # ne supprime et ne compte que ses bases (jamais tout « pokeshop_verif_% » : une exécution parallèle survit).
        self.verif_prefix = f"pokeshop_verif_t{uuid.uuid4().hex[:10]}_"

    def own_scratch(self) -> list[str]:
        """Bases jetables créées par CE test (préfixe exact, sans joker LIKE)."""
        out = _psql(f"SELECT datname FROM pg_database WHERE starts_with(datname, '{self.verif_prefix}');")
        assert out.returncode == 0, out.stderr
        return out.stdout.split()

    def url(self, db: str, user: str | None = None, password: str | None = None) -> str:
        return f"postgresql://{user or self.admin}:{password or self.password}@127.0.0.1:5432/{db}"

    def create(self, prefix: str = "pk_bk") -> str:
        name = f"{prefix}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        out = _psql(f'CREATE DATABASE "{name}";')
        assert out.returncode == 0, out.stderr
        self.databases.append(name)
        return name

    def factory(self, db: str) -> Any:
        import psycopg

        return lambda: psycopg.connect(self.url(db), connect_timeout=10)


@pytest.fixture
def server() -> Iterator[Server]:
    pytest.importorskip("psycopg", reason="pilote psycopg absent")
    for tool in ("psql", "pg_dump", "pg_restore"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} absent")
    if _psql("SELECT 1;").returncode != 0:
        pytest.skip("PostgreSQL injoignable")
    admin, password = f"pk_bk_admin_{uuid.uuid4().hex[:8]}", uuid.uuid4().hex
    assert _psql(f"CREATE ROLE {admin} LOGIN SUPERUSER PASSWORD '{password}';").returncode == 0
    srv = Server(admin, password)
    try:
        yield srv
    finally:
        for name in srv.databases + srv.own_scratch():  # seulement les bases créées par ce test
            _psql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')
        _psql(f"DROP ROLE IF EXISTS {admin};")


@pytest.fixture
def source(server: Server) -> str:
    """Base du moteur peuplée : migrations, jeu FICTIF, journaux d'état et audit écrits par le moteur."""
    db = server.create()
    for path in MIGRATIONS + SEEDS:
        out = _psql(path.read_text(encoding="utf-8"), db)
        assert out.returncode == 0, f"{path.name} : {out.stderr}"
    connect = server.factory(db)
    for stream, n in (("stoploss", 3), ("incidents", 2)):
        journal = PostgresStateJournal(connect, stream)
        journal.load()
        for i in range(n):
            journal.append({"fictif": True, "stream": stream, "i": i})
    PostgresAuditLog(connect).append(
        actor="test", actor_kind="SYSTEME", action="backup.test", entity="tests", entity_id="x", dry_run=True, payload={"fictif": True}
    )
    return db


def run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    full = {k: v for k, v in os.environ.items() if not k.startswith(("POKESHOP_", "DATABASE_URL"))} | env
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=300, check=False, env=full)


def envs(server: Server, source: str, backup_dir: Path, **extra: str) -> dict[str, str]:
    """Environnement de `db/backup.sh` : base source, dossier de sauvegarde, préfixe des bases jetables de CE test."""
    return {"DATABASE_URL": server.url(source), "POKESHOP_BACKUP_DIR": str(backup_dir),
            "POKESHOP_VERIF_PREFIX": server.verif_prefix, **extra}


def count(db: str, sql: str) -> str:
    out = _psql(sql, db)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_backup_then_restore_test_in_a_throwaway_database(server: Server, source: str, tmp_path: Path) -> None:
    env = envs(server, source, tmp_path / "sauvegardes")
    made = run(BACKUP, "sauvegarde", env=env)
    assert made.returncode == 0, made.stderr
    dump = Path(made.stdout.strip().splitlines()[-1])
    manifest = dump.with_suffix(".manifest")
    assert dump.exists() and manifest.exists()
    assert (dump.stat().st_mode & 0o777) == 0o600 and (manifest.stat().st_mode & 0o777) == 0o600
    text = manifest.read_text(encoding="utf-8")
    assert "ajout_seul\tpokeshop.engine_state_journal\t5" in text
    assert all(f"{p.name[:3]}:" in text for p in MIGRATIONS)
    checked = run(BACKUP, "verifier", env=env)  # dernière sauvegarde du dossier
    assert checked.returncode == 0, checked.stderr
    assert "restauration vérifiée" in checked.stdout
    assert server.own_scratch() == []  # base jetable de CE test supprimée (jamais un comptage global)


def test_altered_or_incomplete_backup_is_rejected(server: Server, source: str, tmp_path: Path) -> None:
    env = envs(server, source, tmp_path / "s")
    dump = Path(run(BACKUP, "sauvegarde", env=env).stdout.strip().splitlines()[-1])
    data = bytearray(dump.read_bytes())
    data[len(data) // 2] ^= 0xFF
    dump.write_bytes(bytes(data))
    bad = run(BACKUP, "verifier", str(dump), env=env)
    assert bad.returncode != 0 and "sha256" in bad.stderr
    # Manifeste plus récent que le contenu (lignes manquantes dans la sauvegarde) : refus.
    dump2 = Path(run(BACKUP, "sauvegarde", env=env).stdout.strip().splitlines()[-1])
    manifest = dump2.with_suffix(".manifest")
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("pokeshop.engine_state_journal\t5",
                                                                     "pokeshop.engine_state_journal\t9"), encoding="utf-8")
    short = run(BACKUP, "verifier", str(dump2), env=env)
    assert short.returncode != 0 and "engine_state_journal : 5 ligne(s) < 9" in short.stderr
    assert server.own_scratch() == []  # base jetable de CE test supprimée (jamais un comptage global)


def test_restore_test_detects_a_broken_audit_chain(server: Server, source: str, tmp_path: Path) -> None:
    assert _psql("SET session_replication_role = replica; UPDATE pokeshop.audit_log SET action = 'falsifie' "
                 "WHERE audit_id = (SELECT min(audit_id) FROM pokeshop.audit_log);", source).returncode == 0
    env = envs(server, source, tmp_path / "s")
    assert run(BACKUP, "sauvegarde", env=env).returncode == 0
    bad = run(BACKUP, "verifier", env=env)
    assert bad.returncode != 0 and "verify_audit_chain" in bad.stderr


def test_real_restore_into_an_empty_database_only(server: Server, source: str, tmp_path: Path) -> None:
    env = envs(server, source, tmp_path / "s")
    dump = run(BACKUP, "sauvegarde", env=env).stdout.strip().splitlines()[-1]
    target = server.create("pk_bk_cible")
    restored = run(BACKUP, "restaurer", dump, server.url(target), env=env)
    assert restored.returncode == 0, restored.stderr
    assert count(target, "SELECT count(*) FROM pokeshop.engine_state_journal WHERE stream = 'stoploss'") == "3"
    assert count(target, "SELECT count(*) FROM pokeshop.verify_engine_state_journal()") == "0"
    again = run(BACKUP, "restaurer", dump, server.url(target), env=env)
    assert again.returncode != 0 and "non vide" in again.stderr
    same = run(BACKUP, "restaurer", dump, server.url(source), env=env)
    assert same.returncode != 0


def test_backups_are_refused_inside_the_repository(server: Server, source: str) -> None:
    inside = ROOT / "pokeshop-sauvegardes-test"
    try:
        out = run(BACKUP, "sauvegarde", env=envs(server, source, inside))
        assert out.returncode != 0 and "dans le dépôt" in out.stderr
        assert not list(inside.glob("*.dump"))
    finally:
        shutil.rmtree(inside, ignore_errors=True)


@pytest.mark.skipif(shutil.which("age") is None or shutil.which("age-keygen") is None, reason="age absent")
def test_encrypted_backup_never_kept_in_clear(server: Server, source: str, tmp_path: Path) -> None:
    identity = tmp_path / "cle_proprietaire.txt"
    subprocess.run(["age-keygen", "-o", str(identity)], capture_output=True, check=True)
    recipient = next(line.split(": ")[1] for line in identity.read_text().splitlines() if "public key" in line)
    env = envs(server, source, tmp_path / "s", POKESHOP_BACKUP_AGE_RECIPIENT=recipient)
    made = run(BACKUP, "sauvegarde", env=env)
    assert made.returncode == 0, made.stderr
    dump = Path(made.stdout.strip().splitlines()[-1])
    assert dump.name.endswith(".dump.age") and not list((tmp_path / "s").glob("*.dump"))
    assert not dump.read_bytes().startswith(b"PGDMP")
    assert run(BACKUP, "verifier", env=env).returncode != 0  # clé privée absente : refus
    ok = run(BACKUP, "verifier", env=env | {"POKESHOP_BACKUP_AGE_IDENTITY": str(identity)})
    assert ok.returncode == 0, ok.stderr


def test_engine_login_is_a_least_privilege_member_of_pokeshop_engine(server: Server, source: str) -> None:
    login = f"pk_moteur_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    env = {"DATABASE_URL": server.url(source), "POKESHOP_DB_USER": login, "POKESHOP_DB_PASSWORD": password}
    try:
        assert run(ENGINE_LOGIN, env=env | {"POKESHOP_DB_PASSWORD": "court"}).returncode == 2
        first = run(ENGINE_LOGIN, env=env)
        assert first.returncode == 0, first.stderr
        assert run(ENGINE_LOGIN, env=env).returncode == 0  # idempotent
        assert count(source, f"SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = '{login}'") == "f|f|f"
        assert count(source, f"SELECT pg_has_role('{login}', 'pokeshop_engine', 'MEMBER')") == "t"
        import psycopg

        with psycopg.connect(server.url(source, login, password), connect_timeout=10) as conn:
            assert conn.execute("SELECT count(*) > 0 FROM pokeshop.products").fetchone() == (True,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("SELECT * FROM pokeshop.owner_token_fingerprint")
    finally:
        _psql(f"DROP OWNED BY {login}; DROP ROLE IF EXISTS {login};", source)
