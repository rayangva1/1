#!/usr/bin/env python3
"""Contrôle de l'isolation d'un compte de la flotte d'agents (revue R6 : RS-02, RS-16, R5C-DOC-10 ; BL-204, B28).

À lancer **sous chaque compte de la flotte** (jamais sous celui de la propriétaire), depuis le dépôt cloné sous ce
compte :

    python docs/08-agents/outils/verifier_isolation.py --proprietaire-home /home/<propriétaire>

Lecture seule : le script tente d'ouvrir des fichiers et de lister des dossiers, n'écrit rien et n'affiche **jamais** un
contenu lu (seulement le chemin, le numéro de processus ou le nom d'une variable). Code 0 et « OK » si aucun contrôle
n'échoue ; sinon code 1 et la liste des anomalies. Un contrôle impossible à mener (pas de ``/proc``, par exemple
sous macOS) donne « INCOMPLET » et le code 2, jamais « OK » : la revue le mène alors à la main.

Contrôles, tous fermés par défaut :

1. le compte n'est pas root ;
2. il n'est membre d'aucun groupe qui donne root ou la base en superutilisateur (``docker``, ``sudo``, ``wheel``,
   ``admin``, ``root``) et n'écrit pas sur le socket Docker ;
3. ``sudo -n true`` échoue (aucun sudo sans mot de passe) ;
4. aucun chemin sensible n'est lisible : ``/etc/pokeshop`` (fichier de variables), le dossier personnel de la
   propriétaire (liste), ``~/pokeshop-jetons`` (jetons et secrets en clair), ``~/.ssh``, les sauvegardes
   (``~/pokeshop-sauvegardes``), les dossiers personnels des **autres** comptes de la flotte (``--prefixe-comptes``)
   et chaque ``--chemin`` ajouté ;
5. l'environnement d'aucun processus d'un autre compte n'est lisible (``/proc/<pid>/environ``) ;
6. l'environnement du processus ne porte aucune variable de secret d'infrastructure (mots de passe, clé de
   chiffrement de n8n, secret du moteur, jeton de la propriétaire).

Ce contrôle ne remplace pas la revue (BL-200) : il en est le socle rejouable. Données lues : aucune.
"""

from __future__ import annotations

import argparse
import grp
import os
import pwd
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

PRIVILEGED_GROUPS = frozenset({"docker", "sudo", "wheel", "admin", "root"})
DOCKER_SOCKETS = (Path("/var/run/docker.sock"), Path("/run/docker.sock"))
INFRA_SECRETS = Path("/etc/pokeshop")
OWNER_SENSITIVE = ("pokeshop-jetons", ".ssh", "pokeshop-sauvegardes")
SECRET_ENV_RE = re.compile(r"(PASSWORD|ENCRYPTION_KEY|WEBHOOK_SECRET|OWNER_TOKEN|PRIVATE_KEY|_SECRET$)", re.I)


def _exists(path: Path) -> bool:
    """Existence sans lever d'erreur : un chemin sous un dossier interdit (EACCES) n'est pas « lisible »."""
    try:
        return os.path.lexists(path)
    except OSError:
        return False


def readable(path: Path) -> bool:
    """Vrai si le compte courant lit ce chemin : liste d'un dossier, ou premier octet d'un fichier (jamais affiché)."""
    try:
        if path.is_dir():
            os.listdir(path)
            return True
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False


def check_identity(uid: int, group_names: Iterable[str]) -> list[str]:
    errors = []
    if uid == 0:
        errors.append("compte root : la flotte ne tourne jamais en root")
    privileged = sorted(PRIVILEGED_GROUPS & set(group_names))
    if privileged:
        errors.append(
            f"membre du ou des groupes {', '.join(privileged)} (équivaut à root ou à la base en superutilisateur)"
        )
    return errors


def check_docker_socket(sockets: Iterable[Path], can_write: Callable[[Path], bool]) -> list[str]:
    return [f"socket Docker accessible en écriture : {s}" for s in sockets if _exists(s) and can_write(s)]


def check_sudo(run: Callable[[list[str]], int | None]) -> list[str]:
    """``run`` rend le code de sortie, ou None si sudo est absent."""
    code = run(["sudo", "-n", "true"])
    return ["sudo sans mot de passe possible (sudo -n true réussit)"] if code == 0 else []


def sensitive_paths(
    owner_home: Path, own_home: Path, homes_root: Path, prefix: str, extra: Iterable[Path]
) -> list[Path]:
    paths: list[Path] = [INFRA_SECRETS, owner_home, *(owner_home / name for name in OWNER_SENSITIVE)]
    try:
        paths += sorted(INFRA_SECRETS.iterdir())
    except OSError:
        pass  # absent ou non listable : c'est le résultat attendu, déjà couvert par le contrôle du dossier
    if prefix:
        try:
            paths += sorted(
                p for p in homes_root.iterdir() if p.name.startswith(prefix) and p.resolve() != own_home.resolve()
            )
        except OSError:
            pass
    paths += list(extra)
    seen: set[Path] = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def check_paths(paths: Iterable[Path], is_readable: Callable[[Path], bool] = readable) -> list[str]:
    return [f"chemin sensible lisible : {p}" for p in paths if _exists(p) and is_readable(p)]


def check_proc(proc_root: Path, own_uid: int, is_readable: Callable[[Path], bool] = readable) -> tuple[list[str], bool]:
    """(anomalies, vérifié) : environnement d'un processus d'un autre compte lisible."""
    try:
        entries = sorted(proc_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return [], False
    errors = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            owner = entry.stat().st_uid
        except OSError:
            continue
        if owner != own_uid and is_readable(entry / "environ"):
            errors.append(f"environnement du processus {entry.name} (compte {owner}) lisible")
    return errors, True


def check_environment(environ: Mapping[str, str]) -> list[str]:
    return [
        f"variable de secret dans l'environnement : {name}" for name in sorted(environ) if SECRET_ENV_RE.search(name)
    ]


def _run(cmd: list[str]) -> int | None:
    try:
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False).returncode
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return 1


def _group_names() -> set[str]:
    names = set()
    for gid in {os.getgid(), *os.getgroups()}:
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    return names


def run_checks(
    owner_home: Path,
    *,
    prefix: str = "pokeshop-",
    extra: Iterable[Path] = (),
    uid: int | None = None,
    groups: Iterable[str] | None = None,
    environ: Mapping[str, str] | None = None,
    proc_root: Path = Path("/proc"),
    homes_root: Path | None = None,
    own_home: Path | None = None,
    sockets: Iterable[Path] = DOCKER_SOCKETS,
    run: Callable[[list[str]], int | None] = _run,
    is_readable: Callable[[Path], bool] = readable,
) -> tuple[list[str], list[str]]:
    """(anomalies, contrôles non vérifiés)."""
    uid = os.getuid() if uid is None else uid
    own_home = Path(pwd.getpwuid(uid).pw_dir) if own_home is None else own_home
    homes_root = owner_home.parent if homes_root is None else homes_root
    errors: list[str] = []
    errors += check_identity(uid, _group_names() if groups is None else groups)
    errors += check_docker_socket(sockets, lambda s: os.access(s, os.W_OK))
    errors += check_sudo(run)
    errors += check_paths(sensitive_paths(owner_home, own_home, homes_root, prefix, extra), is_readable)
    proc_errors, proc_checked = check_proc(proc_root, uid, is_readable)
    errors += proc_errors
    errors += check_environment(os.environ if environ is None else environ)
    unchecked = [] if proc_checked else [f"environnement des autres processus ({proc_root} absent)"]
    return errors, unchecked


def report(errors: list[str], unchecked: list[str]) -> tuple[int, list[str]]:
    """Code de sortie et lignes à afficher : 1 = anomalie, 2 = contrôle non mené (jamais « OK »), 0 = OK."""
    if errors:
        return 1, [f"{len(errors)} anomalie(s) d'isolation :", *(f"  ÉCHEC : {err}" for err in errors)]
    if unchecked:  # fermé par défaut : un contrôle non mené n'est jamais un « OK »
        return 2, [f"INCOMPLET : non vérifié — {item} ; à vérifier par la revue (BL-200)" for item in unchecked]
    return 0, [
        "OK — isolation vérifiée pour ce compte (aucun secret, aucun jeton d'un autre compte, ni docker ni sudo)"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--proprietaire-home", type=Path, required=True, help="dossier personnel de la propriétaire")
    parser.add_argument(
        "--prefixe-comptes", default="pokeshop-", help="préfixe des comptes de la flotte (défaut : pokeshop-)"
    )
    parser.add_argument(
        "--chemin", type=Path, action="append", default=[], help="autre chemin qui doit rester illisible"
    )
    args = parser.parse_args(argv)
    errors, unchecked = run_checks(args.proprietaire_home, prefix=args.prefixe_comptes, extra=args.chemin)
    code, lines = report(errors, unchecked)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
