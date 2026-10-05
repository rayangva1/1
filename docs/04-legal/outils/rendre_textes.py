"""Rend les blocs publics des textes clients avec les valeurs du registre des champs.

Usage ::

    python docs/04-legal/outils/rendre_textes.py                  # régénère docs/04-legal/apercu/
    python docs/04-legal/outils/rendre_textes.py --verifier       # code 1 si apercu/ n'est pas à jour
    python docs/04-legal/outils/rendre_textes.py --publication --sortie DOSSIER
        # textes définitifs ; code 1 tant qu'un champ utilisé n'est pas « valide »

Le mode aperçu signale les valeurs proposées (⟦à valider⟧) et les champs manquants
(⟦À REMPLIR : …⟧) : il ne doit jamais être publié. Seul le mode publication produit des
textes publiables, et seulement quand tous les champs utilisés sont validés.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import registre_champs as rc
import yaml

APERCU_DIR = rc.LEGAL_DIR / "apercu"

#: Documents contenant un bloc public, dans l'ordre de lecture conseillé.
PUBLIC_DOCS: tuple[Path, ...] = (
    rc.LEGAL_DIR / "CGV.md",
    rc.LEGAL_DIR / "LIVRAISON_RETOURS.md",
    rc.LEGAL_DIR / "PRECOMMANDES.md",
    rc.LEGAL_DIR / "CONFIDENTIALITE.md",
    rc.LEGAL_DIR / "CONFIDENTIALITE_LANDING.md",
    rc.LEGAL_DIR / "COOKIES.md",
    rc.LEGAL_DIR / "MENTIONS_LEGALES.md",
    rc.LEGAL_DIR / "USAGE_MARQUES.md",
    rc.OPS_DIR / "FAQ_CLIENTS.md",
)

APERCU_HEADER = (
    "<!-- FICHIER GÉNÉRÉ par docs/04-legal/outils/rendre_textes.py à partir de {source} "
    "et de champs_a_remplir.yaml (version {version}). Ne pas modifier à la main. -->\n"
    "> **APERÇU — NE PAS PUBLIER.** Texte public de `{source}` rendu avec les valeurs du registre. "
    "« ⟦à valider⟧ » signale une valeur proposée non validée ; « ⟦À REMPLIR : …⟧ » un champ sans valeur. "
    "**À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION.**\n\n"
)


def _relative(path: Path, repo: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.name


def registry_version(path: Path = rc.REGISTRY_PATH) -> str:
    """Version déclarée en tête du registre (``version``)."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return str(data.get("version", "inconnue"))


def build_previews(
    docs: Sequence[Path] = PUBLIC_DOCS,
    fields: Mapping[str, rc.Field] | None = None,
    version: str | None = None,
    repo: Path = rc.REPO,
) -> dict[str, str]:
    """Contenu attendu de chaque fichier d'aperçu, par nom de fichier."""
    fields = rc.load_registry() if fields is None else fields
    version = registry_version() if version is None else version
    out: dict[str, str] = {}
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        body = rc.render_public(text, fields, rc.Mode.APERCU)
        out[doc.name] = APERCU_HEADER.format(source=_relative(doc, repo), version=version) + body
    return out


def write_previews(previews: Mapping[str, str], target: Path | None = None) -> list[Path]:
    """Écrit les aperçus et supprime les aperçus orphelins ; renvoie les fichiers écrits."""
    target = APERCU_DIR if target is None else target
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in previews.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    for stale in target.glob("*.md"):
        if stale.name not in previews:
            stale.unlink()
    return written


def stale_previews(previews: Mapping[str, str], target: Path | None = None) -> list[str]:
    """Liste des écarts entre les aperçus attendus et ceux présents sur disque."""
    target = APERCU_DIR if target is None else target
    problems: list[str] = []
    for name, content in previews.items():
        path = target / name
        if not path.exists():
            problems.append(f"aperçu manquant : {name}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"aperçu périmé : {name} (relancer rendre_textes.py)")
    if target.exists():
        for extra in sorted(target.glob("*.md")):
            if extra.name not in previews:
                problems.append(f"aperçu orphelin : {extra.name}")
    return problems


def publish(
    target: Path,
    docs: Sequence[Path] = PUBLIC_DOCS,
    fields: Mapping[str, rc.Field] | None = None,
) -> list[Path]:
    """Écrit les textes définitifs ; lève ``RenderError`` si un champ n'est pas validé."""
    fields = rc.load_registry() if fields is None else fields
    rendered: dict[str, str] = {}
    errors: list[str] = []
    for doc in docs:
        try:
            rendered[doc.name] = rc.render_public(doc.read_text(encoding="utf-8"), fields, rc.Mode.PUBLICATION)
        except rc.RenderError as exc:
            errors.extend(f"{doc.name} : {err}" for err in exc.errors)
    if errors:
        raise rc.RenderError(errors)
    target.mkdir(parents=True, exist_ok=True)
    out = []
    for name, content in rendered.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        out.append(path)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verifier", action="store_true", help="contrôle que apercu/ est à jour")
    group.add_argument("--publication", action="store_true", help="textes définitifs (champs validés seulement)")
    parser.add_argument("--sortie", type=Path, help="dossier de sortie du mode publication")
    args = parser.parse_args(argv)

    try:
        if args.publication:
            if args.sortie is None:
                parser.error("--publication exige --sortie DOSSIER")
            for path in publish(args.sortie):
                print(f"écrit : {path}")
            return 0
        previews = build_previews()
        if args.verifier:
            problems = stale_previews(previews)
            for problem in problems:
                print(problem)
            print("OK : aperçus à jour" if not problems else f"{len(problems)} écart(s)")
            return 1 if problems else 0
        for path in write_previews(previews):
            print(f"aperçu : {_relative(path, rc.REPO)}")
        return 0
    except (rc.RegistryError, rc.RenderError, rc.BlockError) as exc:
        errors = getattr(exc, "errors", [str(exc)])
        print(f"REFUS : {len(errors)} problème(s)")
        for err in errors:
            print(f"  - {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
