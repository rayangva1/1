"""Parcours réel du formulaire dans un navigateur (Playwright + Chromium, facultatifs).

Ignoré si Playwright ou Chromium sont absents (ce ne sont pas des dépendances du projet).
Chromium : variable d'environnement ``CHROMIUM`` (chemin de l'exécutable), sinon celui de Playwright.
Le webhook est intercepté : aucune requête ne sort de la machine.
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

LANDING = Path(__file__).resolve().parents[1] / "landing"
WEBHOOK = "https://n8n.exemple.invalid/webhook/alertes-inscription"


@pytest.fixture(scope="module")
def navigateur() -> Iterator[Any]:
    chemin = os.environ.get("CHROMIUM")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=chemin) if chemin else p.chromium.launch()
        except Exception as exc:  # navigateur absent ou non installé
            pytest.skip(f"Chromium indisponible : {exc}")
        yield b
        b.close()


def _servir(dossier: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    gestionnaire = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(dossier))
    gestionnaire.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), gestionnaire)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}/"


@pytest.fixture()
def site(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    dossier = tmp_path / "landing"
    shutil.copytree(LANDING, dossier)
    serveur, url = _servir(dossier)
    yield dossier, url
    serveur.shutdown()


def _configurer(dossier: Path, webhook: str) -> None:
    cfg = dossier / "js" / "config.js"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace('webhookUrl: ""', f'webhookUrl: "{webhook}"'), encoding="utf-8")


def _page(navigateur: Any, url: str, requetes: list[dict[str, Any]], statut: int = 200) -> Any:
    page = navigateur.new_page(viewport={"width": 390, "height": 844})

    def repondre(route: Any) -> None:
        requete = route.request
        requetes.append({"methode": requete.method, "corps": parse_qs(requete.post_data or ""), "entetes": requete.headers})
        route.fulfill(status=statut, body='{"ok": true}', headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"})

    page.route("https://n8n.exemple.invalid/**", repondre)
    page.goto(url + "index.html?utm_source=Instagram&utm_campaign=lancement")
    return page


def test_formulaire_desactive_sans_webhook(navigateur: Any, site: tuple[Path, str]) -> None:
    _, url = site
    requetes: list[dict[str, Any]] = []
    page = _page(navigateur, url, requetes)
    assert page.is_disabled("#lp-envoyer")
    assert "pas encore ouvertes" in page.inner_text("#lp-statut")
    assert page.get_attribute("#lp-formulaire", "data-etat") == "desactive"
    page.close()


def test_inscription_envoyee_et_confirmation_affichee(navigateur: Any, site: tuple[Path, str]) -> None:
    dossier, url = site
    _configurer(dossier, WEBHOOK)
    requetes: list[dict[str, Any]] = []
    page = _page(navigateur, url, requetes)
    assert page.is_enabled("#lp-envoyer")
    page.fill("#lp-email", "lea@exemple.ch")
    page.fill("#lp-prenom", "Léa")
    page.check('input[value="etb"]')
    page.check('input[value="displays"]')
    page.check('input[value="30-60"]')
    page.select_option("#lp-canton", "GE")
    page.check("#lp-consentement")
    page.click("#lp-envoyer")
    page.wait_for_selector(".lp-confirmation")
    assert len(requetes) == 1
    corps = {k: v[0] for k, v in requetes[0]["corps"].items()}
    assert requetes[0]["methode"] == "POST"
    assert corps["email"] == "lea@exemple.ch" and corps["prenom"] == "Léa" and corps["formats"] == "displays,etb"
    assert corps["budget"] == "30-60" and corps["canton"] == "GE" and corps["consentement"] == "oui"
    assert corps["utm_source"] == "instagram" and corps["utm_campaign"] == "lancement" and corps["source"] == "landing"
    assert corps["consentement_texte"].startswith("J'accepte de recevoir l'alerte d'ouverture")
    assert "site_web" not in corps
    assert page.evaluate("document.activeElement.textContent").startswith("Merci")
    page.close()


def test_erreurs_de_saisie_sans_envoi(navigateur: Any, site: tuple[Path, str]) -> None:
    dossier, url = site
    _configurer(dossier, WEBHOOK)
    requetes: list[dict[str, Any]] = []
    page = _page(navigateur, url, requetes)
    page.fill("#lp-email", "pas-un-email")
    page.click("#lp-envoyer")
    assert page.get_attribute("#lp-email", "aria-invalid") == "true"
    assert page.get_attribute("#lp-consentement", "aria-invalid") == "true"
    assert page.is_visible("#lp-email-erreur") and page.is_visible("#lp-consentement-erreur")
    assert page.evaluate("document.activeElement.id") == "lp-email"
    assert requetes == []
    page.close()


def test_echec_du_webhook_annonce_et_bouton_reactive(navigateur: Any, site: tuple[Path, str]) -> None:
    dossier, url = site
    _configurer(dossier, WEBHOOK)
    requetes: list[dict[str, Any]] = []
    page = _page(navigateur, url, requetes, statut=500)
    page.fill("#lp-email", "lea@exemple.ch")
    page.check("#lp-consentement")
    page.click("#lp-envoyer")
    page.wait_for_selector(".lp-statut--erreur")
    assert "n'a pas pu être envoyée" in page.inner_text("#lp-statut")
    assert page.is_enabled("#lp-envoyer")
    page.close()


def test_champ_piege_simule_un_succes_sans_envoi(navigateur: Any, site: tuple[Path, str]) -> None:
    dossier, url = site
    _configurer(dossier, WEBHOOK)
    requetes: list[dict[str, Any]] = []
    page = _page(navigateur, url, requetes)
    page.fill("#lp-email", "robot@exemple.ch")
    page.check("#lp-consentement")
    page.evaluate("document.getElementById('lp-site-web').value = 'http://spam.exemple'")
    page.click("#lp-envoyer")
    page.wait_for_selector(".lp-confirmation")
    assert requetes == []
    page.close()


def test_pause_des_animations_et_absence_de_debordement(navigateur: Any, site: tuple[Path, str]) -> None:
    """Ambiance Atelier (toujours claire) : un bouton « Pause des animations » (WCAG 2.2.2) fige tout, fil orange compris."""
    _, url = site
    page = _page(navigateur, url, [])
    assert page.query_selector("#lp-theme") is None
    assert page.get_attribute("html", "data-ambiance") == "atelier"
    assert page.is_visible(".lp-logo__img")
    page.wait_for_function("document.documentElement.classList.contains('lp-fil-pret')")
    assert page.evaluate("document.querySelectorAll('.lp-fil__trait').length") == 4  # héro → Braise → drop → alertes → pied
    assert page.get_attribute("#lp-animations", "aria-pressed") == "false"
    page.click("#lp-animations")
    assert page.get_attribute("html", "data-animations") == "pause"
    assert page.get_attribute("#lp-animations", "aria-pressed") == "true"
    assert page.evaluate("[...document.querySelectorAll('.lp-fil__trait')].every(p => getComputedStyle(p).strokeDasharray === 'none')")
    assert page.evaluate("getComputedStyle(document.querySelector('.lp-hero__img')).animationName") == "none"
    page.reload()
    assert page.get_attribute("html", "data-animations") == "pause"  # choix mémorisé
    page.click("#lp-animations")
    assert page.get_attribute("html", "data-animations") is None
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.set_viewport_size({"width": 1440, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.close()


def test_mouvement_reduit_et_images_indisponibles(navigateur: Any, site: tuple[Path, str]) -> None:
    """prefers-reduced-motion coupe toutes les animations (fil entier et immobile) ; une image qui ne charge pas est
    masquée et laisse la silhouette du renard."""
    _, url = site
    contexte = navigateur.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    page = contexte.new_page()
    # Visuels servis en local (assets/visuels/) : on coupe leur chargement, ainsi que toute image distante.
    page.route("**/assets/visuels/**", lambda route: route.abort())
    page.route("https://**/*.webp", lambda route: route.abort())
    page.route("https://**/*.png", lambda route: route.abort())
    page.goto(url + "index.html")
    page.wait_for_timeout(300)
    assert page.evaluate("getComputedStyle(document.querySelector('.lp-hero__img')).animationName") == "none"
    assert page.evaluate("[...document.querySelectorAll('[data-apparition]')].every(e => getComputedStyle(e).opacity === '1')")
    assert page.evaluate("getComputedStyle(document.querySelector('.lp-hero__img')).visibility") == "hidden"
    assert page.is_visible(".lp-hero .lp-secours")
    contexte.close()


def test_fil_entier_en_mouvement_reduit(navigateur: Any, site: tuple[Path, str]) -> None:
    """Le fil se raccorde aux filets photographiés ; en mouvement réduit, il est affiché entier, sans tirets."""
    _, url = site
    contexte = navigateur.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = contexte.new_page()
    page.goto(url + "index.html", wait_until="networkidle")
    page.wait_for_function("document.documentElement.classList.contains('lp-fil-pret')")
    traits = page.evaluate("[...document.querySelectorAll('.lp-fil__trait')].map(p => [getComputedStyle(p).strokeDasharray, p.getTotalLength()])")
    assert len(traits) == 4 and all(d == "none" and longueur > 100 for d, longueur in traits)
    contexte.close()


# ----------------------------------------------------------------------------- visuels (revue PERF-01) et contrastes (A11Y-01)
@pytest.fixture(scope="module")
def site_rapatrie(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Landing copiée puis importée en local (vraies variantes WebP produites à partir de sources FICTIVES d'aplat)."""
    pytest.importorskip("PIL")
    import fictifs

    racine, _, rapport = fictifs.depot_importe(tmp_path_factory.mktemp("importe"))
    assert rapport.bascule, rapport.erreurs
    serveur, url = _servir(racine.parent)
    yield url
    serveur.shutdown()


@pytest.mark.parametrize(("largeur", "hauteur", "densite", "attendu"), [(390, 844, 3, "-1520.webp"), (1440, 900, 2, "-2688.webp"), (1280, 720, 1, "-1280.webp")])
def test_image_principale_en_webp_jamais_en_png(navigateur: Any, site_rapatrie: str, largeur: int, hauteur: int, densite: int, attendu: str) -> None:
    """Après rapatriement, aucun écran ne charge de PNG : le srcset ne contient que des variantes WebP budgétées."""
    import visuels

    contexte = navigateur.new_context(viewport={"width": largeur, "height": hauteur}, device_scale_factor=densite)
    page = contexte.new_page()
    images: list[str] = []
    page.on("request", lambda r: images.append(r.url) if r.resource_type == "image" else None)
    page.goto(site_rapatrie + "landing/index.html", wait_until="networkidle")
    choisie = page.evaluate("document.querySelector('.lp-hero__img').currentSrc")
    assert choisie.endswith(attendu), choisie
    assert not [u for u in images if u.endswith(".png") and "/assets/visuels/" in u], images
    largeur_variante = int(choisie.rsplit("-", 1)[1].removesuffix(".webp"))
    corps = page.evaluate("fetch(document.querySelector('.lp-hero__img').currentSrc).then(r => r.arrayBuffer()).then(b => b.byteLength)")
    assert corps <= visuels.plafond_octets(largeur_variante)
    contexte.close()


def _luminance(rgb: tuple[float, ...]) -> float:
    def lin(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


#: Textes posés sur (ou contre) une illustration : le titre du héro (sur l'image dès 1280 px, au-dessus ailleurs).
TEXTES_SUR_ILLUSTRATION = (
    ".lp-hero .lp-surtitre", ".lp-hero__seo", ".lp-hero__accroche .lp-ligne", ".lp-hero__accroche .lp-accent", ".lp-nav a",
    "#titre-mascotte", "#titre-alertes", "#titre-promesse",
)


@pytest.mark.parametrize("couleur", [(255, 255, 255), (0, 0, 0)], ids=["image-blanche", "image-noire"])
@pytest.mark.parametrize(("largeur", "hauteur"), [(1440, 900), (1024, 768), (390, 844)])
def test_texte_sur_illustration_contraste_aa_meme_sur_une_image_blanche(navigateur: Any, site: tuple[Path, str], largeur: int, hauteur: int, couleur: tuple[int, int, int]) -> None:
    """Chaque illustration remplacée par du blanc pur puis du noir pur (pires cas) : le texte reste AA (voile du héro)."""
    import io
    import re

    image = pytest.importorskip("PIL.Image")
    _, url = site
    tampon = io.BytesIO()
    image.new("RGB", (8, 8), couleur).save(tampon, format="PNG")
    blanc = tampon.getvalue()
    contexte = navigateur.new_context(viewport={"width": largeur, "height": hauteur}, reduced_motion="reduce")
    # Pire cas : chaque visuel (local, ou distant en aperçu) remplacé par un aplat pur.
    contexte.route("**/assets/visuels/**", lambda route: route.fulfill(status=200, content_type="image/png", body=blanc))
    contexte.route("https://**/*.webp", lambda route: route.fulfill(status=200, content_type="image/png", body=blanc))
    page = contexte.new_page()
    page.goto(url + "index.html", wait_until="networkidle")
    page.evaluate("document.querySelector('.lp-apercu')?.remove()")
    insuffisants = []
    for selecteur in TEXTES_SUR_ILLUSTRATION:
        for element in page.query_selector_all(selecteur):
            if not element.is_visible():
                continue
            element.scroll_into_view_if_needed()
            info = element.evaluate(
                """e => { const r = document.createRange(); r.selectNodeContents(e);
                const rs = [...r.getClientRects()].filter(x => x.width > 2 && x.height > 2);
                const x0 = Math.max(0, Math.min(...rs.map(x => x.left))), y0 = Math.max(0, Math.min(...rs.map(x => x.top)));
                const cs = getComputedStyle(e);
                return {x: x0, y: y0, w: Math.min(innerWidth, Math.max(...rs.map(x => x.right))) - x0,
                        h: Math.min(innerHeight, Math.max(...rs.map(x => x.bottom))) - y0, couleur: cs.color,
                        taille: parseFloat(cs.fontSize), graisse: parseInt(cs.fontWeight), accent: e.matches('.lp-accent'),
                        texte: e.textContent.trim().slice(0, 30)}; }"""
            )
            masque = page.add_style_tag(content="body *, body *::before, body *::after { color: transparent !important; "
                                        "-webkit-text-fill-color: transparent !important; text-shadow: none !important; } .lp-accent { background: none !important; }")
            capture = page.screenshot(clip={"x": info["x"], "y": info["y"], "width": info["w"], "height": info["h"]})
            masque.evaluate("t => t.remove()")
            octets = image.open(io.BytesIO(capture)).convert("RGB").tobytes()
            fonds = sorted(_luminance(tuple(octets[i : i + 3])) for i in range(0, len(octets), 3))
            # Pire fond derrière un texte sombre : le plus sombre (1er centile) ; derrière un texte clair : le plus clair.
            texte_sombre = _luminance(tuple(float(v) for v in re.findall(r"[\d.]+", info["couleur"])[:3])) < 0.2
            fond = fonds[max(0, int(len(fonds) * 0.01))] if texte_sombre else fonds[int(len(fonds) * 0.99) - 1]
            rgb = tuple(float(v) for v in re.findall(r"[\d.]+", info["couleur"])[:3])
            texte = _luminance(rgb)
            ratio = (max(texte, fond) + 0.05) / (min(texte, fond) + 0.05)
            seuil = 3.0 if info["taille"] >= 24 or (info["taille"] >= 18.66 and info["graisse"] >= 700) else 4.5
            if ratio < seuil:
                insuffisants.append((selecteur, info["texte"], round(ratio, 2), seuil))
    contexte.close()
    assert insuffisants == []
