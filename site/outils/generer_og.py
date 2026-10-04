#!/usr/bin/env python3
"""Rend l'image de partage (Open Graph, 1200 × 630) de la landing depuis site/outils/og/og-image.html.

Outil LOCAL et facultatif (comme l'export PNG de la DA) : il exige Playwright et un Chromium,
qui ne sont PAS des dépendances du projet. Sans eux, l'image existante reste en place.

Usage : python site/outils/generer_og.py [--chromium /chemin/vers/chrome]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GABARIT = REPO / "site" / "outils" / "og" / "og-image.html"
SORTIE = REPO / "site" / "landing" / "assets" / "og-image.png"


def rendre(chromium: str | None = None, sortie: Path = SORTIE) -> Path:
    """Capture le gabarit à 1200 × 630 et écrit le PNG."""
    from playwright.sync_api import sync_playwright  # dépendance locale facultative

    with sync_playwright() as p:
        navigateur = p.chromium.launch(executable_path=chromium) if chromium else p.chromium.launch()
        page = navigateur.new_page(viewport={"width": 1200, "height": 630})
        page.goto(GABARIT.as_uri())
        page.wait_for_timeout(1500)
        page.screenshot(path=str(sortie), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        navigateur.close()
    return sortie


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chromium", default=None, help="exécutable Chromium à utiliser")
    args = parser.parse_args(argv)
    try:
        chemin = rendre(args.chromium)
    except ImportError:
        print("Playwright absent : image non régénérée (outil local facultatif).")
        return 1
    print(f"Image écrite : {chemin.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
