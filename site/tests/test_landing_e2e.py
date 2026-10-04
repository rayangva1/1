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


def test_bascule_de_theme_et_absence_de_debordement(navigateur: Any, site: tuple[Path, str]) -> None:
    _, url = site
    page = _page(navigateur, url, [])
    assert page.inner_text("#lp-theme").endswith("automatique")
    page.click("#lp-theme")
    assert page.get_attribute("html", "data-theme") == "light"
    page.click("#lp-theme")
    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.is_visible(".lp-logo__img--sombre") and not page.is_visible(".lp-logo__img--clair")
    page.click("#lp-theme")
    assert page.get_attribute("html", "data-theme") is None
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.close()
