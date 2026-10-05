"""Contrôle d'isolation de la flotte (revue R6 : RS-02, RS-16, R5C-DOC-10) : chaque contrôle échoue fermé.

Données FICTIVES, tout sous ``tmp_path`` ; aucun secret réel n'est lu ni affiché.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verifier_isolation as vi  # noqa: E402

TOOL = Path(vi.__file__)


def test_root_or_a_privileged_group_is_refused() -> None:
    assert vi.check_identity(0, ["users"]) == ["compte root : la flotte ne tourne jamais en root"]
    errors = vi.check_identity(1001, ["users", "docker"])
    assert len(errors) == 1 and "docker" in errors[0] and "superutilisateur" in errors[0]
    for group in ("sudo", "wheel", "admin"):
        assert vi.check_identity(1001, [group]), group
    assert vi.check_identity(1001, ["users", "pokeshop-agents"]) == []


def test_writable_docker_socket_and_passwordless_sudo_are_refused(tmp_path: Path) -> None:
    sock = tmp_path / "docker.sock"
    sock.write_text("")
    assert vi.check_docker_socket([sock], lambda _: True) == [f"socket Docker accessible en écriture : {sock}"]
    assert vi.check_docker_socket([sock], lambda _: False) == []
    assert vi.check_docker_socket([tmp_path / "absent.sock"], lambda _: True) == []
    assert vi.check_sudo(lambda cmd: 0 if cmd == ["sudo", "-n", "true"] else 1) != []
    assert vi.check_sudo(lambda _: 1) == [] and vi.check_sudo(lambda _: None) == []  # refusé, ou sudo absent


def test_sensitive_paths_cover_the_owner_tokens_the_vault_file_and_other_fleet_accounts(tmp_path: Path) -> None:
    homes = tmp_path / "home"
    owner, own, other = homes / "proprietaire", homes / "pokeshop-a05", homes / "pokeshop-a10"
    for d in (owner / "pokeshop-jetons", own, other):
        d.mkdir(parents=True)
    paths = vi.sensitive_paths(owner, own, homes, "pokeshop-", [tmp_path / "coffre.kdbx"])
    assert vi.INFRA_SECRETS in paths and owner in paths and owner / "pokeshop-jetons" in paths
    assert owner / ".ssh" in paths and owner / "pokeshop-sauvegardes" in paths
    assert other in paths and own not in paths  # son propre dossier n'est pas un secret, celui d'un autre rôle l'est
    assert tmp_path / "coffre.kdbx" in paths


def test_a_readable_secret_is_reported_by_path_never_by_content(tmp_path: Path) -> None:
    secret = tmp_path / "pokeshop-jetons" / "jetons-roles.txt"
    secret.parent.mkdir()
    secret.write_text("qa-conformite\tFICTIF-JETON-NE-JAMAIS-AFFICHER\n", encoding="utf-8")
    errors = vi.check_paths([secret, tmp_path / "absent"], vi.readable)
    assert errors == [f"chemin sensible lisible : {secret}"]
    assert all("FICTIF-JETON" not in e for e in errors)
    assert vi.check_paths([secret], lambda _: False) == []  # illisible pour le compte : conforme


def test_environment_of_another_account_is_reported_and_missing_proc_is_never_ok(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    for pid in ("123", "456"):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "environ").write_text("POKESHOP_FICTIF=1\0")
    (proc / "self").mkdir()
    me = os.getuid()
    errors, checked = vi.check_proc(proc, me + 4242, vi.readable)  # processus d'un « autre » compte
    assert checked and errors == [f"environnement du processus {pid} (compte {me}) lisible" for pid in ("123", "456")]
    assert vi.check_proc(proc, me, vi.readable) == ([], True)  # ses propres processus : admis
    assert vi.check_proc(tmp_path / "pas-de-proc", me) == ([], False)
    code, lines = vi.report([], ["environnement des autres processus (/proc absent)"])
    assert code == 2 and not any(line.startswith("OK") for line in lines) and lines[0].startswith("INCOMPLET")
    assert vi.report(["x"], [])[0] == 1 and vi.report([], [])[0] == 0


def test_infrastructure_secrets_in_the_environment_are_reported_by_name() -> None:
    env = {"PATH": "/usr/bin", "POSTGRES_PASSWORD": "x", "POKESHOP_DB_PASSWORD": "x", "N8N_ENCRYPTION_KEY": "x",
           "POKESHOP_N8N_WEBHOOK_SECRET": "x", "OWNER_TOKEN": "x", "POKESHOP_API_URL": "http://127.0.0.1:8000"}  # fmt: skip
    errors = vi.check_environment(env)
    assert len(errors) == 5 and all(e.startswith("variable de secret dans l'environnement : ") for e in errors)
    assert not any("PATH" in e or "API_URL" in e for e in errors)


def test_run_checks_on_a_clean_fictive_account_is_ok(tmp_path: Path) -> None:
    homes = tmp_path / "home"
    owner, own = homes / "proprietaire", homes / "pokeshop-agents"
    (owner / "pokeshop-jetons").mkdir(parents=True)
    own.mkdir()
    errors, unchecked = vi.run_checks(
        owner, uid=1001, groups=["pokeshop-agents"], environ={"PATH": "/usr/bin"}, proc_root=tmp_path / "proc-vide",
        homes_root=homes, own_home=own, sockets=[], run=lambda _: 1, is_readable=lambda p: p == own,
    )  # fmt: skip
    (tmp_path / "proc-vide").mkdir()
    assert errors == [] and unchecked == [
        "environnement des autres processus (" + str(tmp_path / "proc-vide") + " absent)"
    ]
    errors, unchecked = vi.run_checks(
        owner, uid=1001, groups=["pokeshop-agents"], environ={"PATH": "/usr/bin"}, proc_root=tmp_path / "proc-vide",
        homes_root=homes, own_home=own, sockets=[], run=lambda _: 1, is_readable=lambda p: p == own,
    )  # fmt: skip
    assert errors == [] and unchecked == []


@pytest.mark.skipif(os.getuid() != 0, reason="seulement quand les tests tournent en root")
def test_the_tool_run_as_root_fails_closed(tmp_path: Path) -> None:
    out = subprocess.run([sys.executable, str(TOOL), "--proprietaire-home", str(tmp_path)], capture_output=True,
                         text=True, check=False)  # fmt: skip
    assert out.returncode == 1 and "compte root" in out.stdout and "OK —" not in out.stdout
