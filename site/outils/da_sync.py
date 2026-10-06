#!/usr/bin/env python3
"""Copie les fichiers DA approuvés (docs/05-da) dans la landing (site/landing/assets/da).

La landing doit pouvoir être déposée seule (Netlify Drop, page Shopify, Carrd) : elle ne
peut donc pas pointer vers ``../../docs/05-da``. La source de vérité reste ``docs/05-da`` ;
ce script recopie les fichiers sous des noms neutres et écrit un manifeste (direction,
source, empreinte SHA-256). ``verifier_site.py`` refuse toute copie désynchronisée.

Ambiance (facultative) : une ambiance de ``tokens.json > ambiances`` (ex. « nuit », Nuit sur le Léman, bâtie sur B)
ajoute ``ambiance.css`` (copie de ``tokens/tokens-<ambiance>.css``), remplace le logo sur fond sombre par celui de
l'ambiance, pose ``data-ambiance`` sur ``<html>`` et l'URL Google Fonts de l'ambiance sur chaque page (landing et
maquettes ``site/maquettes/``).

Usage :
    python site/outils/da_sync.py                                  # direction et ambiance du manifeste
    python site/outils/da_sync.py --direction b --ambiance nuit    # Nuit sur le Léman (défaut actuel)
    python site/outils/da_sync.py --direction a --ambiance aucune  # direction A sans ambiance
    python site/outils/da_sync.py --verifier                       # contrôle seul (code 1 si désynchronisé)
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
MAQUETTES = REPO / "site" / "maquettes"
DIRECTIONS = ("a", "b")
GOOGLE_FONTS_RE = re.compile(r'href="(https://fonts\.googleapis\.com/css2\?[^"]+)"')
DATA_DA_RE = re.compile(r'<html\b[^>]*\bdata-da="([ab])"')
DATA_AMBIANCE_RE = re.compile(r'<html\b[^>]*\bdata-ambiance="([a-z]+)"')
LIEN_AMBIANCE_RE = re.compile(r'[ \t]*<link rel="stylesheet" href="[^"]*assets/da/ambiance\.css">[ \t]*\n?')
LIEN_COMPOSANTS_RE = re.compile(r'([ \t]*)<link rel="stylesheet" href="([^"]*)assets/da/components\.css">[ \t]*\n')


def _tokens() -> dict:
    return json.loads((DA / "tokens" / "tokens.json").read_text(encoding="utf-8"))


def ambiances() -> tuple[str, ...]:
    """Ambiances déclarées dans tokens.json (ex. « nuit »)."""
    return tuple(_tokens().get("ambiances", {}))


def _verifier_ambiance(direction: str, ambiance: str | None) -> None:
    if ambiance is None:
        return
    amb = _tokens().get("ambiances", {}).get(ambiance)
    if amb is None:
        raise ValueError(f"ambiance inconnue : {ambiance!r} (attendu : {', '.join(ambiances()) or 'aucune'})")
    if amb["base"] != direction:
        raise ValueError(f"l'ambiance {ambiance} est bâtie sur la direction {amb['base']} (direction demandée : {direction})")


def plan_copie(direction: str, ambiance: str | None = None) -> dict[str, Path]:
    """Chemin publié (relatif à assets/da) -> fichier source DA, pour une direction (et une ambiance)."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction inconnue : {direction!r} (attendu : a ou b)")
    _verifier_ambiance(direction, ambiance)
    logo = DA / "logo" / direction
    horizontal = "logo-a-horizontal" if direction == "a" else "logo-b-principal"
    plan = {
        "tokens.css": DA / "tokens" / "tokens.css",
        "components.css": DA / "components" / "components.css",
        "logo-horizontal.svg": logo / f"{horizontal}.svg",
        "logo-horizontal-fond-sombre.svg": logo / f"{horizontal}-fond-sombre.svg",
        "favicon.svg": logo / "favicon.svg",
        "favicon-32.png": DA / "logo" / "png" / f"favicon-{direction}-32.png",
        "apple-touch-icon.png": DA / "logo" / "png" / f"favicon-{direction}-180.png",
        "logo-1200.png": DA / "logo" / "png" / f"logo-{direction}-principal-1200.png",
    }
    if ambiance is not None:
        plan["ambiance.css"] = DA / "tokens" / f"tokens-{ambiance}.css"
        plan["logo-horizontal-fond-sombre.svg"] = logo / f"logo-{direction}-{ambiance}.svg"
    return plan


def sha256(path: Path) -> str:
    """Empreinte SHA-256 d'un fichier."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def google_fonts(direction: str, ambiance: str | None = None) -> str:
    """URL Google Fonts de la direction, ou de l'ambiance si elle est posée (source : tokens.json)."""
    tokens = _tokens()
    if ambiance is not None:
        return str(tokens["ambiances"][ambiance]["googleFonts"])
    return str(tokens["directions"][direction]["googleFonts"])


def fichiers_attendus(direction: str, ambiance: str | None = None) -> dict[str, dict[str, str]]:
    """Chemin publié -> {source, sha256} pour une direction (et une ambiance)."""
    return {
        publie: {"source": src.relative_to(REPO).as_posix(), "sha256": sha256(src)}
        for publie, src in sorted(plan_copie(direction, ambiance).items())
    }


def manifeste_attendu(direction: str, ambiance: str | None = None) -> dict[str, object]:
    """Manifeste que la copie doit reproduire (déterministe, sans horodatage)."""
    fichiers = fichiers_attendus(direction, ambiance)
    return {
        "avertissement": "Copies générées par site/outils/da_sync.py depuis docs/05-da : ne pas modifier ici.",
        "direction": direction,
        "ambiance": ambiance,
        "google_fonts": google_fonts(direction, ambiance),
        "fichiers": fichiers,
    }


def lire_manifeste(cible: Path = ASSETS_DA) -> tuple[str, str | None]:
    """(direction, ambiance) du manifeste en place ; (« a », None) s'il est absent ou illisible."""
    try:
        m = json.loads((cible / MANIFESTE.name).read_text(encoding="utf-8"))
        return str(m["direction"]), m.get("ambiance")
    except (OSError, ValueError, KeyError):
        return "a", None


def synchroniser(direction: str = "a", cible: Path = ASSETS_DA, ambiance: str | None = None) -> dict[str, object]:
    """Copie les fichiers et écrit le manifeste ; retourne le manifeste."""
    cible.mkdir(parents=True, exist_ok=True)
    plan = plan_copie(direction, ambiance)
    for publie, src in plan.items():
        if not src.exists():
            raise FileNotFoundError(f"fichier DA introuvable : {src.relative_to(REPO)}")
        shutil.copyfile(src, cible / publie)
    for orphelin in sorted(cible.iterdir()):
        if orphelin.name not in plan and orphelin.name != MANIFESTE.name:
            orphelin.unlink()
    manifeste = manifeste_attendu(direction, ambiance)
    (cible / MANIFESTE.name).write_text(json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    appliquer_direction_html(direction, ambiance=ambiance)
    return manifeste


def pages_html(racine: Path = LANDING) -> list[Path]:
    """Pages HTML de la landing (hors gabarits) et, pour la landing du dépôt, les maquettes qui la réutilisent."""
    pages = sorted(p for p in racine.glob("*.html"))
    if racine.resolve() == LANDING.resolve() and MAQUETTES.is_dir():
        pages += sorted(MAQUETTES.glob("*.html"))
    return pages


def aligner_html(texte: str, direction: str, ambiance: str | None = None) -> str:
    """Texte d'une page aligné sur la DA : data-da, data-ambiance, feuille d'ambiance, URL Google Fonts."""
    url = google_fonts(direction, ambiance).replace("&", "&amp;")
    nouveau = re.sub(r'(<html\b[^>]*\bdata-da=")[ab]"', rf'\g<1>{direction}"', texte, count=1)
    nouveau = re.sub(r'(<html\b[^>]*?)\s+data-ambiance="[a-z]*"', r"\g<1>", nouveau, count=1)
    nouveau = LIEN_AMBIANCE_RE.sub("", nouveau)
    if ambiance is not None:
        nouveau = re.sub(r'(<html\b[^>]*\bdata-da="[ab]")', rf'\g<1> data-ambiance="{ambiance}"', nouveau, count=1)
        nouveau = LIEN_COMPOSANTS_RE.sub(
            lambda m: f'{m.group(0)}{m.group(1)}<link rel="stylesheet" href="{m.group(2)}assets/da/ambiance.css">\n',
            nouveau,
            count=1,
        )
    schema = "dark" if ambiance is not None else "light dark"
    nouveau = re.sub(r'(<meta name="color-scheme" content=")[^"]*(">)', rf"\g<1>{schema}\g<2>", nouveau, count=1)
    return GOOGLE_FONTS_RE.sub(f'href="{url}"', nouveau)


def appliquer_direction_html(direction: str, racine: Path = LANDING, ambiance: str | None = None) -> None:
    """Aligne data-da, data-ambiance, la feuille d'ambiance et l'URL Google Fonts de chaque page."""
    for page in pages_html(racine):
        texte = page.read_text(encoding="utf-8")
        nouveau = aligner_html(texte, direction, ambiance)
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
    ambiance = manifeste.get("ambiance")
    try:
        attendu = manifeste_attendu(direction, ambiance)
    except ValueError as exc:
        return [f"manifeste : {exc}"]
    if manifeste != attendu:
        erreurs.append("manifeste désynchronisé de docs/05-da (relancer da_sync.py)")
    for publie, info in fichiers_attendus(direction, ambiance).items():
        copie = cible / publie
        if not copie.exists():
            erreurs.append(f"assets/da/{publie} absent")
        elif sha256(copie) != info["sha256"]:
            erreurs.append(f"assets/da/{publie} différent de {info['source']}")
    url = google_fonts(direction, ambiance).replace("&", "&amp;")
    for page in pages_html(racine):
        texte = page.read_text(encoding="utf-8")
        m = DATA_DA_RE.search(texte)
        if not m or m.group(1) != direction:
            erreurs.append(f"{page.name} : data-da ≠ direction synchronisée ({direction})")
        m = DATA_AMBIANCE_RE.search(texte)
        if (m.group(1) if m else None) != ambiance:
            erreurs.append(f"{page.name} : data-ambiance ≠ ambiance synchronisée ({ambiance or 'aucune'})")
        if bool(LIEN_AMBIANCE_RE.search(texte)) != (ambiance is not None):
            erreurs.append(f"{page.name} : feuille assets/da/ambiance.css {'absente' if ambiance else 'en trop'}")
        for href in GOOGLE_FONTS_RE.findall(texte):
            if href != url:
                erreurs.append(f"{page.name} : URL Google Fonts ≠ tokens.json (direction {direction}, ambiance {ambiance or 'aucune'})")
    return erreurs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--direction", choices=DIRECTIONS, default=None, help="direction DA à copier (défaut : celle du manifeste, sinon a)")
    parser.add_argument("--ambiance", choices=(*ambiances(), "aucune"), default=None,
                        help="ambiance à appliquer (défaut : celle du manifeste ; « aucune » pour la retirer)")
    parser.add_argument("--verifier", action="store_true", help="contrôle seul, sans écrire")
    args = parser.parse_args(argv)
    if args.verifier:
        erreurs = verifier()
        for e in erreurs:
            print(f"ERREUR {e}")
        print("DA synchronisée." if not erreurs else f"{len(erreurs)} erreur(s).")
        return 1 if erreurs else 0
    direction_actuelle, ambiance_actuelle = lire_manifeste()
    direction = args.direction or direction_actuelle
    ambiance = ambiance_actuelle if args.ambiance is None else (None if args.ambiance == "aucune" else args.ambiance)
    if args.direction and args.ambiance is None and ambiance is not None:
        amb = _tokens()["ambiances"].get(ambiance, {})
        if amb.get("base") != direction:
            ambiance = None  # changer de direction retire une ambiance bâtie sur une autre direction
    try:
        synchroniser(direction, ambiance=ambiance)
    except ValueError as exc:
        print(f"ERREUR {exc}")
        return 1
    nombre = len(plan_copie(direction, ambiance))
    print(f"Direction {direction.upper()}, ambiance {ambiance or 'aucune'} : {nombre} fichiers copiés dans site/landing/assets/da/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
