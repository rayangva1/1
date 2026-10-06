"""Ambiance « Nuit sur le Léman » : DA synchronisée, maquettes contrôlées, règles d'images, textes de garantie, JS."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import da_sync
import publication
import pytest
import verifier_site as vs
import visuels

REPO = Path(__file__).resolve().parents[2]
LANDING = REPO / "site" / "landing"
MAQUETTES = REPO / "site" / "maquettes"


# ----------------------------------------------------------------------------- DA et ambiance
def test_landing_en_direction_b_ambiance_nuit() -> None:
    assert da_sync.lire_manifeste() == ("b", "nuit")
    assert da_sync.verifier() == []
    for page in da_sync.pages_html():
        texte = page.read_text(encoding="utf-8")
        assert 'data-da="b" data-ambiance="nuit"' in texte, page.name
        assert "assets/da/ambiance.css" in texte and "family=Fraunces" in texte, page.name
    assert {p.name for p in da_sync.pages_html()} >= {"index.html", "fiche-produit.html", "drop.html"}


def test_plan_de_copie_ambiance() -> None:
    plan = da_sync.plan_copie("b", "nuit")
    assert plan["ambiance.css"].name == "tokens-nuit.css"
    assert plan["logo-horizontal-fond-sombre.svg"].name == "logo-b-nuit.svg"
    assert all(p.exists() for p in plan.values())
    with pytest.raises(ValueError):
        da_sync.plan_copie("a", "nuit")  # l'ambiance Nuit est bâtie sur B
    with pytest.raises(ValueError):
        da_sync.plan_copie("b", "jour")


def test_aligner_html_pose_et_retire_l_ambiance() -> None:
    source = publication.pages_secondaires()["merci.html"]
    nuit = da_sync.aligner_html(source, "b", "nuit")
    assert 'data-da="b" data-ambiance="nuit"' in nuit and 'href="assets/da/ambiance.css"' in nuit
    assert 'content="dark"' in nuit and "Fraunces" in nuit
    assert da_sync.aligner_html(nuit, "b", "nuit") == nuit
    sans = da_sync.aligner_html(nuit, "a", None)
    assert "data-ambiance" not in sans and "ambiance.css" not in sans and 'data-da="a"' in sans
    assert 'content="light dark"' in sans and "Fraunces" not in sans


def test_ambiance_desynchronisee_detectee(tmp_path: Path) -> None:
    racine = tmp_path / "lp"
    shutil.copytree(LANDING, racine)
    index = racine / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace(' data-ambiance="nuit"', "", 1), encoding="utf-8")
    erreurs = da_sync.verifier(cible=racine / "assets" / "da", racine=racine)
    assert any("data-ambiance" in e for e in erreurs)


def test_css_landing_sans_couleur_et_mouvement_reductible() -> None:
    css = (LANDING / "css" / "landing.css").read_text(encoding="utf-8")
    assert vs.verifier_css_js(LANDING) == []
    assert "@media (prefers-reduced-motion: no-preference)" in css
    assert ':root[data-animations="pause"] *' in css and "animation: none !important" in css
    # Toutes les animations infinies sont déclarées dans le bloc conditionnel (aucune ne tourne d'office)
    hors_bloc = css.split("@media (prefers-reduced-motion: no-preference)")[0]
    assert "infinite" not in hors_bloc
    composants = (LANDING / "assets" / "da" / "components.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce) { .da-root * { transition: none !important; animation: none !important; } }" in composants


# ----------------------------------------------------------------------------- page principale
def test_index_garde_le_contrat_et_les_textes_exacts() -> None:
    texte = (LANDING / "index.html").read_text(encoding="utf-8")
    visible = vs._texte_visible(texte)
    garantie, difference = vs.textes_garantie_moteur()
    assert garantie in visible and difference in visible
    assert "Lumi" in visible and "Nom provisoire" in visible
    assert "ni approuvée par The Pokémon Company" in visible
    a = vs.analyser(texte)
    assert [i.get("data-visuel") for i in a.imgs if i.get("fetchpriority") == "high"] == ["heros-nuit-etoilee"]
    assert all(i.get("loading") == "lazy" for i in a.imgs if "data-visuel" in i and i.get("fetchpriority") != "high")
    assert all(i.get("width") and i.get("height") for i in a.imgs)
    assert re.search(r'<source media="\(max-width: 699px\)"[^>]*data-visuel="heros-nuit-etoilee-portrait"', texte)
    assert texte.count('rel="preload" as="image"') == 2
    consentement = next(c for c in a.champs if c.get("name") == "consentement")
    assert "checked" not in consentement and "required" in consentement


def test_textes_de_garantie_identiques_au_moteur() -> None:
    predrop = pytest.importorskip("pokeshop.predrop")
    assert vs.textes_garantie_moteur() == (predrop.GUARANTEE_TEXT_FR, predrop.NO_DIFFERENCE_REFUND_FR)


@pytest.mark.parametrize(
    ("modification", "attendu"),
    [
        (lambda t: t.replace('loading="lazy" decoding="async" data-visuel="quai-nuit"', 'decoding="async" data-visuel="quai-nuit"'), "loading"),
        (lambda t: t.replace('data-visuel="quai-nuit"', 'fetchpriority="high" data-visuel="quai-nuit"'), "fetchpriority"),
        (lambda t: t.replace('width="963" height="132" loading="lazy">', 'loading="lazy">', 1), "width/height"),
        (lambda t: t.replace("<li>Aucune fausse urgence</li>", "<li>Plus que 3 boîtes</li>", 1), "fausse urgence"),
        (lambda t: t.replace("Le supplément pré-drop paie", "Le supplément paie"), "GUARANTEE_TEXT_FR"),
        (lambda t: t.replace("même s'il reste des unités au drop.", "sauf exception."), "NO_DIFFERENCE_REFUND_FR"),
    ],
)
def test_regles_images_et_contenu_detectees(tmp_path: Path, modification, attendu: str) -> None:  # type: ignore[no-untyped-def]
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    index = dossier / "index.html"
    index.write_text(modification(index.read_text(encoding="utf-8")), encoding="utf-8")
    erreurs = vs.verifier_page(index, dossier)
    assert any(attendu in e for e in erreurs), erreurs


# ----------------------------------------------------------------------------- maquettes
def test_maquettes_conformes_et_jamais_publiees(tmp_path: Path) -> None:
    assert vs.verifier_maquettes() == []
    assert {p.name for p in MAQUETTES.glob("*.html")} == {"fiche-produit.html", "drop.html"}
    rapport = publication.construire("apercu", tmp_path / "ap")
    assert not any("maquette" in f or f in ("fiche-produit.html", "drop.html") for f in rapport.fichiers)


def _maquette(tmp_path: Path, nom: str, modification) -> list[str]:  # type: ignore[no-untyped-def]
    dossier = tmp_path / "maquettes"
    dossier.mkdir(exist_ok=True)
    cible = dossier / nom
    cible.write_text(modification((MAQUETTES / nom).read_text(encoding="utf-8")), encoding="utf-8")
    # liens relatifs vers ../landing : on reproduit l'arborescence
    if not (tmp_path / "landing").exists():
        shutil.copytree(LANDING, tmp_path / "landing")
    for autre in MAQUETTES.glob("*.html"):
        if not (dossier / autre.name).exists():
            shutil.copyfile(autre, dossier / autre.name)
    return vs.verifier_maquette(cible)


@pytest.mark.parametrize(
    ("nom", "modification", "attendu"),
    [
        ("fiche-produit.html", lambda t: t.replace('<span class="da-price">CHF 64.90</span> <span class="lp-fictif">FICTIF</span>', '<span class="da-price">CHF 64.90</span>', 1), "prix sans mention FICTIF"),
        ("fiche-produit.html", lambda t: t.replace("pas le produit.", "et le produit.", 1), "GUARANTEE_TEXT_FR"),
        ("drop.html", lambda t: t.replace("même s'il reste des unités au drop.</p>", "sauf exception.</p>"), "NO_DIFFERENCE_REFUND_FR"),
        ("drop.html", lambda t: t.replace("Réservations ouvertes</span>", "Réservations presque complètes</span>", 1), "statut de réservation"),
        ("drop.html", lambda t: t.replace("Pas de minuteur", "Dépêchez-vous", 1), "fausse urgence"),
        ("drop.html", lambda t: t.replace('<meta name="robots" content="noindex, nofollow">', "", 1), "noindex"),
        ("fiche-produit.html", lambda t: t.replace("<p><strong>Maquette FICTIVE", "<p><strong>Fiche", 1), "bandeau"),
        ("drop.html", lambda t: t.replace('Le 20.11.2026 (date estimée) <span class="lp-fictif">FICTIF</span>', "Le 20.11.2026", 1), "date sans mention"),
        ("fiche-produit.html", lambda t: t.replace("ni sponsorisée, ", "", 1), "mention d'indépendance"),
    ],
)
def test_controles_des_maquettes_detectent_les_defauts(tmp_path: Path, nom: str, modification, attendu: str) -> None:  # type: ignore[no-untyped-def]
    erreurs = _maquette(tmp_path, nom, modification)
    assert any(attendu in e for e in erreurs), erreurs


def test_maquette_dans_la_landing_refusee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    racine = tmp_path / "landing"
    shutil.copytree(LANDING, racine)
    shutil.copyfile(MAQUETTES / "drop.html", racine / "drop.html")
    monkeypatch.setattr(vs, "LANDING", racine)
    assert any("maquette dans le dossier publié" in e for e in vs.verifier_maquettes())


def test_maquettes_prix_fictifs_coherents_avec_la_regle_des_10_pourcent() -> None:
    for page in MAQUETTES.glob("*.html"):
        prix = [float(p) for p in re.findall(r"CHF (\d+\.\d{2})</span> <span class=\"lp-fictif\">", page.read_text(encoding="utf-8"))]
        if len(prix) >= 2:
            resa, drop = prix[0], prix[1]
            assert drop < resa <= round(drop * 1.10, 2), page.name


# ----------------------------------------------------------------------------- JavaScript
def test_scripts_valides_et_sans_reseau() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent")
    for nom in ("nuit.js", "theme.js", "landing.js"):
        subprocess.run([node, "--check", str(LANDING / "js" / nom)], check=True, capture_output=True, timeout=30)
    nuit = (LANDING / "js" / "nuit.js").read_text(encoding="utf-8")
    for interdit in ("fetch(", "XMLHttpRequest", "sendBeacon", "http://", "https://", "document.cookie"):
        assert interdit not in nuit, interdit
    assert "prefers-reduced-motion: reduce" in nuit and "lp-animations" in nuit


def test_config_visuels_hors_dossier_publie() -> None:
    assert visuels.CONFIG.parent == REPO / "site" / "config"
    assert not list(LANDING.rglob("visuels.json"))
    assert json.loads(visuels.CONFIG.read_text(encoding="utf-8"))["_avertissement"].startswith("Source UNIQUE")
