#!/usr/bin/env python3
"""Rend l'image de partage (Open Graph, 1200 × 630) de la landing depuis site/outils/og/og-image.html.

Outil LOCAL et facultatif (comme l'export PNG de la DA) : il exige un Chromium piloté par Playwright, pour Python
ou, à défaut, pour Node (``site/outils/og/rendre_og.mjs``), qui ne sont PAS des dépendances du projet. Sans eux,
l'image existante reste en place. **Aucun appel réseau** : les polices Google sont servies depuis
``site/tests/e2e/polices`` (mêmes fichiers, licence OFL) et toute autre requête externe est refusée.

Sortie : ``site/landing/assets/og-image.jpg`` (balises ``og:image`` et ``twitter:image`` de la landing), JPEG
progressif sans métadonnées, qualité abaissée par paliers jusqu'à tenir la cible de 150 Ko ; refus au-delà de
300 Ko (``PLAFOND_OCTETS``, contrôlé aussi par ``verifier_site.py``). L'ancienne PNG (588 Ko) n'est plus produite.

Contenu (IP-02, contrôlé par ``verifier_site.py``) : aucune affirmation que la boutique ne peut pas encore tenir
(jamais « stock réel » avant l'ouverture) et mention lisible « Boutique indépendante · non affiliée à Pokémon /
Nintendo / The Pokémon Company ».

Usage : python site/outils/generer_og.py [--chromium /chemin/vers/chrome]
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
GABARIT = SITE / "outils" / "og" / "og-image.html"
RENDU_NODE = SITE / "outils" / "og" / "rendre_og.mjs"
POLICES = SITE / "tests" / "e2e" / "polices"
#: Chemin publié, relatif à la landing (balises og:image et twitter:image : ``{{URL_LANDING}}`` + ce chemin).
CHEMIN_PUBLIE = "assets/og-image.jpg"
SORTIE = SITE / "landing" / CHEMIN_PUBLIE
LARGEUR, HAUTEUR = 1200, 630
#: Poids visé (aperçu rapide sur les réseaux et messageries) et plafond refusé par verifier_site.py.
CIBLE_OCTETS = 150 * 1024
PLAFOND_OCTETS = 300 * 1024
QUALITES = (86, 82, 78, 74, 70, 66, 62)


class OgError(RuntimeError):
    """Rendu ou encodage impossible."""


def _capturer_python(chromium: str | None) -> bytes:
    """PNG du gabarit via Playwright pour Python (ImportError s'il est absent)."""
    from playwright.sync_api import sync_playwright  # dépendance locale facultative

    import http.server
    import threading

    class Gestion(http.server.SimpleHTTPRequestHandler):
        """Sert site/ en local, sans journal."""

        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, directory=str(SITE), **kwargs)

        def log_message(self, *args) -> None:  # type: ignore[no-untyped-def]
            pass

    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{serveur.server_address[1]}/"
    css = (POLICES / "fonts.css").read_text(encoding="utf-8")

    def police(route):  # type: ignore[no-untyped-def]
        nom = route.request.url.split("://", 1)[1].split("/", 1)[1].replace("/", "_")
        fichier = POLICES / nom
        if not fichier.exists():
            return route.abort()
        return route.fulfill(status=200, content_type="font/woff2", body=fichier.read_bytes(), headers={"access-control-allow-origin": "*"})

    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(executable_path=chromium) if chromium else p.chromium.launch()
            ctx = navigateur.new_context(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=1)
            ctx.route(lambda u: not u.startswith(base) and "fonts.g" not in u, lambda r: r.abort())
            ctx.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=css))
            ctx.route("https://fonts.gstatic.com/**", police)
            page = ctx.new_page()
            page.goto(base + "outils/og/og-image.html", wait_until="networkidle")
            page.evaluate("document.fonts.ready.then(() => true)")
            if not page.evaluate("[...document.images].every(i => i.complete && i.naturalWidth > 0)"):
                raise OgError("image du gabarit non chargée")
            page.wait_for_timeout(300)
            png = page.screenshot(type="png", clip={"x": 0, "y": 0, "width": LARGEUR, "height": HAUTEUR})
            navigateur.close()
    finally:
        serveur.shutdown()
    return png


def _capturer_node(chromium: str | None) -> bytes:
    """PNG du gabarit via Playwright pour Node (``rendre_og.mjs``)."""
    node = shutil.which("node")
    if node is None:
        raise OgError("ni Playwright pour Python ni Node.js : image non régénérée (outil local facultatif)")
    with tempfile.TemporaryDirectory() as tmp:
        cible = Path(tmp) / "og.png"
        env = {**os.environ, "CHROMIUM": chromium} if chromium else None
        res = subprocess.run([node, str(RENDU_NODE), str(cible)], capture_output=True, text=True, timeout=180, env=env)
        if res.returncode != 0 or not cible.exists():
            raise OgError(f"rendu Node impossible : {(res.stderr or res.stdout).strip()}")
        return cible.read_bytes()


def capturer(chromium: str | None = None) -> bytes:
    """PNG 1200 × 630 du gabarit (Playwright pour Python, sinon pour Node)."""
    try:
        return _capturer_python(chromium)
    except ImportError:
        return _capturer_node(chromium)


def encoder_jpeg(png: bytes) -> tuple[bytes, int]:
    """JPEG progressif sans métadonnées, à la meilleure qualité qui tient la cible ; (octets, qualité).

    Lève ``OgError`` si même la qualité la plus basse dépasse le plafond, ou si l'image n'a pas la bonne taille.
    """
    from PIL import Image  # dépendance des outils de visuels (rapatrier_visuels.py)

    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.size != (LARGEUR, HAUTEUR):
        raise OgError(f"rendu de {image.size[0]} × {image.size[1]} px (attendu {LARGEUR} × {HAUTEUR})")
    meilleur: tuple[bytes, int] | None = None
    for qualite in QUALITES:
        tampon = io.BytesIO()
        image.save(tampon, "JPEG", quality=qualite, optimize=True, progressive=True)
        meilleur = (tampon.getvalue(), qualite)
        if len(meilleur[0]) <= CIBLE_OCTETS:
            break
    assert meilleur is not None
    if len(meilleur[0]) > PLAFOND_OCTETS:
        raise OgError(f"{len(meilleur[0]) // 1024} Ko > plafond de {PLAFOND_OCTETS // 1024} Ko même en qualité {QUALITES[-1]}")
    return meilleur


def rendre(chromium: str | None = None, sortie: Path = SORTIE) -> tuple[Path, int, int]:
    """Capture le gabarit à 1200 × 630 et écrit le JPEG ; (chemin, octets, qualité)."""
    octets, qualite = encoder_jpeg(capturer(chromium))
    sortie.write_bytes(octets)
    ancienne = sortie.with_suffix(".png")
    if ancienne.exists():
        ancienne.unlink()  # l'ancienne image de partage PNG n'est plus référencée
    return sortie, len(octets), qualite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chromium", default=None, help="exécutable Chromium à utiliser")
    args = parser.parse_args(argv)
    try:
        chemin, taille, qualite = rendre(args.chromium)
    except OgError as exc:
        print(f"Image non régénérée : {exc}")
        return 1
    except ImportError as exc:
        print(f"Image non régénérée : {exc.name or exc} absent (outil local facultatif)")
        return 1
    print(f"Image écrite : {chemin.relative_to(REPO)} ({taille // 1024} Ko, JPEG qualité {qualite})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
