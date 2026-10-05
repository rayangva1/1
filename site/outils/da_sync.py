#!/usr/bin/env python3
"""Copie les fichiers DA approuvés (docs/05-da) dans la landing (site/landing/assets/da).

La landing doit pouvoir être déposée seule (Netlify Drop, page Shopify, Carrd) : elle ne
peut donc pas pointer vers ``../../docs/05-da``. La source de vérité reste ``docs/05-da`` ;
ce script recopie les fichiers sous des noms neutres et écrit un manifeste (direction,
source, empreinte SHA-256). ``verifier_site.py`` refuse toute copie désynchronisée.

Usage :
    python site/outils/da_sync.py                 # direction A (défaut DA)
    python site/outils/da_sync.py --direction b   # bascule vers la direction B
    python site/outils/da_sync.py --verifier      # contrôle seul (code 1 si désynchronisé)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DA = REPO / "docs" / "05-da"
LANDING = REPO / "site" / "landing"
ASSETS_DA = LANDING / "assets" / "da"
MANIFESTE = ASSETS_DA / "manifeste.json"
DIRECTIONS = ("a", "b")
GOOGLE_FONTS_RE = re.compile(r'href="(https://fonts\.googleapis\.com/css2\?[^"]+)"')
DATA_DA_RE = re.compile(r'<html\b[^>]*\bdata-da="([ab])"')


def plan_copie(direction: str) -> dict[str, Path]:
    """Chemin publié (relatif à assets/da) -> fichier source DA, pour une direction."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction inconnue : {direction!r} (attendu : a ou b)")
    logo = DA / "logo" / direction
    horizontal = "logo-a-horizontal" if direction == "a" else "logo-b-principal"
    return {
        "tokens.css": DA / "tokens" / "tokens.css",
        "components.css": DA / "components" / "components.css",
        "logo-horizontal.svg": logo / f"{horizontal}.svg",
        "logo-horizontal-fond-sombre.svg": logo / f"{horizontal}-fond-sombre.svg",
        "favicon.svg": logo / "favicon.svg",
        "favicon-32.png": DA / "logo" / "png" / f"favicon-{direction}-32.png",
        "apple-touch-icon.png": DA / "logo" / "png" / f"favicon-{direction}-180.png",
        "logo-1200.png": DA / "logo" / "png" / f"logo-{direction}-principal-1200.png",
    }


def sha256(path: Path) -> str:
    """Empreinte SHA-256 d'un fichier."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def google_fonts(direction: str) -> str:
    """URL Google Fonts de la direction (source : tokens.json)."""
    tokens = json.loads((DA / "tokens" / "tokens.json").read_text(encoding="utf-8"))
    return str(tokens["directions"][direction]["googleFonts"])


def fichiers_attendus(direction: str) -> dict[str, dict[str, str]]:
    """Chemin publié -> {source, sha256} pour une direction."""
    return {
        publie: {"source": src.relative_to(REPO).as_posix(), "sha256": sha256(src)}
        for publie, src in sorted(plan_copie(direction).items())
    }


def manifeste_attendu(direction: str) -> dict[str, object]:
    """Manifeste que la copie doit reproduire (déterministe, sans horodatage)."""
    fichiers = fichiers_attendus(direction)
    return {
        "avertissement": "Copies générées par site/outils/da_sync.py depuis docs/05-da : ne pas modifier ici.",
        "direction": direction,
        "google_fonts": google_fonts(direction),
        "fichiers": fichiers,
    }


def synchroniser(direction: str = "a", cible: Path = ASSETS_DA) -> dict[str, object]:
    """Copie les fichiers et écrit le manifeste ; retourne le manifeste."""
    cible.mkdir(parents=True, exist_ok=True)
    plan = plan_copie(direction)
    for publie, src in plan.items():
        if not src.exists():
            raise FileNotFoundError(f"fichier DA introuvable : {src.relative_to(REPO)}")
        shutil.copyfile(src, cible / publie)
    for orphelin in sorted(cible.iterdir()):
        if orphelin.name not in plan and orphelin.name != MANIFESTE.name:
            orphelin.unlink()
    manifeste = manifeste_attendu(direction)
    (cible / MANIFESTE.name).write_text(json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    appliquer_direction_html(direction)
    return manifeste


def pages_html(racine: Path = LANDING) -> list[Path]:
    """Pages HTML de la landing (hors gabarits)."""
    return sorted(p for p in racine.glob("*.html"))


def appliquer_direction_html(direction: str, racine: Path = LANDING) -> None:
    """Aligne data-da et l'URL Google Fonts de chaque page sur la direction."""
    url = google_fonts(direction).replace("&", "&amp;")
    for page in pages_html(racine):
        texte = page.read_text(encoding="utf-8")
        nouveau = re.sub(r'(<html\b[^>]*\bdata-da=")[ab]"', rf'\g<1>{direction}"', texte, count=1)
        nouveau = GOOGLE_FONTS_RE.sub(f'href="{url}"', nouveau)
        if nouveau != texte:
            page.write_text(nouveau, encoding="utf-8")


def verifier(cible: Path = ASSETS_DA, racine: Path = LANDING) -> list[str]:
    """Erreurs de synchronisation entre docs/05-da et les copies de la landing."""
    erreurs: list[str] = []
    if not (cible / MANIFESTE.name).exists():
        return ["assets/da/manifeste.json absent : lancer site/outils/da_sync.py"]
    manifeste = json.loads((cible / MANIFESTE.name).read_text(encoding="utf-8"))
    direction = manifeste.get("direction")
    if direction not in DIRECTIONS:
        return [f"manifeste : direction invalide {direction!r}"]
    attendu = manifeste_attendu(direction)
    if manifeste != attendu:
        erreurs.append("manifeste désynchronisé de docs/05-da (relancer da_sync.py)")
    for publie, info in fichiers_attendus(direction).items():
        copie = cible / publie
        if not copie.exists():
            erreurs.append(f"assets/da/{publie} absent")
        elif sha256(copie) != info["sha256"]:
            erreurs.append(f"assets/da/{publie} différent de {info['source']}")
    url = google_fonts(direction).replace("&", "&amp;")
    for page in pages_html(racine):
        texte = page.read_text(encoding="utf-8")
        m = DATA_DA_RE.search(texte)
        if not m or m.group(1) != direction:
            erreurs.append(f"{page.name} : data-da ≠ direction synchronisée ({direction})")
        for href in GOOGLE_FONTS_RE.findall(texte):
            if href != url:
                erreurs.append(f"{page.name} : URL Google Fonts ≠ tokens.json (direction {direction})")
    return erreurs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--direction", choices=DIRECTIONS, default=None, help="direction DA à copier (défaut : celle du manifeste, sinon a)")
    parser.add_argument("--verifier", action="store_true", help="contrôle seul, sans écrire")
    args = parser.parse_args(argv)
    if args.verifier:
        erreurs = verifier()
        for e in erreurs:
            print(f"ERREUR {e}")
        print("DA synchronisée." if not erreurs else f"{len(erreurs)} erreur(s).")
        return 1 if erreurs else 0
    direction = args.direction
    if direction is None:
        try:
            direction = json.loads(MANIFESTE.read_text(encoding="utf-8"))["direction"]
        except (OSError, ValueError, KeyError):
            direction = "a"
    synchroniser(direction)
    print(f"Direction {direction.upper()} : {len(plan_copie(direction))} fichiers copiés dans site/landing/assets/da/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
