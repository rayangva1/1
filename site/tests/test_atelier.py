"""Landing en ambiance « Atelier » : DA synchronisée (Nuit archivée et refusée), récit en chapitres, fil orange raccordé
aux filets photographiés, mascotte Braise (nom provisoire), maquettes contrôlées, textes de garantie, JS.

Décision du propriétaire du 06.10.2026 : l'Atelier remplace « Nuit sur le Léman » et la loutre « Lumi ». Refonte de la
landing, des pages secondaires et des maquettes : étape 2 (10.10.2026), puis corrections des deux critiques (DA-01 à
DA-17, HON-01, A11Y-01, TST-01) et des derniers constats (HON-02, A11Y-02, A11Y-03, PERF-01, IP-02, IP-03). Chaque
garde-fou des étapes précédentes est gardé et adapté au nouveau contenu.
"""

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
#: Chapitres du récit, dans l'ordre (héro, puis 01 à 08) : chacun porté par une illustration ou une photo.
CHAPITRES = ("mascotte", "drop", "reservation", "formats", "soin", "geneve", "alertes", "faq")


def _index() -> str:
    return (LANDING / "index.html").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- DA et ambiance
def test_landing_en_direction_a_ambiance_atelier() -> None:
    assert da_sync.lire_manifeste() == ("a", "atelier")
    assert da_sync.verifier() == []
    for page in da_sync.pages_html():
        texte = page.read_text(encoding="utf-8")
        assert 'data-da="a" data-ambiance="atelier"' in texte, page.name
        assert "assets/da/ambiance.css" in texte and "family=Geist" in texte and "Instrument+Serif" in texte, page.name
        assert 'content="light"' in texte, page.name
        assert "nuit" not in texte.lower().replace("nuit-noire", ""), page.name  # aucune trace de l'ambiance archivée
    assert {p.name for p in da_sync.pages_html()} >= {"index.html", "fiche-produit.html", "drop.html"}


def test_plan_de_copie_ambiance_atelier() -> None:
    plan = da_sync.plan_copie("a", "atelier")
    assert plan["ambiance.css"].name == "tokens-atelier.css"
    assert plan["logo-horizontal.svg"].name == "logo-a-atelier.svg"
    assert plan["logo-horizontal-fond-sombre.svg"].name == "logo-a-atelier-fond-sombre.svg"
    assert plan["favicon.svg"].name == "favicon-atelier.svg"
    assert all(p.exists() for p in plan.values())
    assert da_sync.mode_ambiance("atelier") == "light"
    with pytest.raises(ValueError):
        da_sync.plan_copie("b", "atelier")  # l'ambiance Atelier est bâtie sur A
    with pytest.raises(ValueError):
        da_sync.plan_copie("a", "jour")


def test_ambiance_archivee_refusee_par_le_site() -> None:
    """Nuit reste documentée dans docs/05-da (archive) mais ne peut plus être appliquée au site."""
    assert "nuit" in da_sync.ambiances() and da_sync.ambiance_archivee("nuit")
    assert da_sync.ambiances_actives() == ("atelier",)
    with pytest.raises(ValueError, match="archivée"):
        da_sync.plan_copie("b", "nuit")
    with pytest.raises(ValueError, match="archivée"):
        da_sync.synchroniser("b", ambiance="nuit")
    with pytest.raises(SystemExit):
        da_sync.main(["--direction", "b", "--ambiance", "nuit"])  # absente des choix de la ligne de commande
    assert da_sync.verifier() == []  # rien n'a été écrit


def test_bascule_sur_une_copie_puis_retour_a_l_atelier(tmp_path: Path) -> None:
    """Retrait puis remise de l'ambiance sur une copie de la landing : le dépôt n'est jamais modifié."""
    racine = tmp_path / "lp"
    shutil.copytree(LANDING, racine)
    avant = {p.name: p.read_bytes() for p in LANDING.glob("*.html")}
    cible = racine / "assets" / "da"
    da_sync.synchroniser("a", cible=cible, ambiance=None, racine=racine)
    index = (racine / "index.html").read_text(encoding="utf-8")
    assert "data-ambiance" not in index and "ambiance.css" not in index and 'content="light dark"' in index
    manifeste = da_sync.synchroniser("a", cible=cible, ambiance="atelier", racine=racine)
    assert manifeste["ambiance"] == "atelier" and da_sync.verifier(cible=cible, racine=racine) == []
    index = (racine / "index.html").read_text(encoding="utf-8")
    assert 'data-da="a" data-ambiance="atelier"' in index and 'content="light"' in index and "family=Geist" in index
    assert (cible / "ambiance.css").read_bytes() == (da_sync.DA / "tokens" / "tokens-atelier.css").read_bytes()
    assert {p.name: p.read_bytes() for p in LANDING.glob("*.html")} == avant and da_sync.verifier() == []


def test_aligner_html_pose_et_retire_l_ambiance() -> None:
    source = publication.pages_secondaires()["merci.html"]
    atelier = da_sync.aligner_html(source, "a", "atelier")
    assert 'data-da="a" data-ambiance="atelier"' in atelier and 'href="assets/da/ambiance.css"' in atelier
    assert 'content="light"' in atelier and "family=Geist" in atelier and "Instrument+Serif" in atelier
    assert da_sync.aligner_html(atelier, "a", "atelier") == atelier
    sans = da_sync.aligner_html(atelier, "a", None)
    assert "data-ambiance" not in sans and "ambiance.css" not in sans and 'data-da="a"' in sans
    assert 'content="light dark"' in sans and "Instrument+Serif" not in sans
    assert da_sync.aligner_html(sans, "a", "atelier") == atelier


def test_ambiance_desynchronisee_detectee(tmp_path: Path) -> None:
    racine = tmp_path / "lp"
    shutil.copytree(LANDING, racine)
    index = racine / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace(' data-ambiance="atelier"', "", 1), encoding="utf-8")
    erreurs = da_sync.verifier(cible=racine / "assets" / "da", racine=racine)
    assert any("data-ambiance" in e for e in erreurs)


def test_css_landing_sans_couleur_et_mouvement_reductible() -> None:
    css = (LANDING / "css" / "landing.css").read_text(encoding="utf-8")
    assert vs.verifier_css_js(LANDING) == []
    assert "@media (prefers-reduced-motion: no-preference)" in css
    assert ':root[data-animations="pause"] *' in css and "animation: none !important" in css
    assert "transition: none !important" in css
    # La pause coupe aussi le défilement doux, porté par <html> lui-même (A11Y-01).
    assert ':root[data-animations="pause"] { scroll-behavior: auto !important; }' in css
    # La pose du héro n'anime jamais l'opacité : le décor de secours ne transparaît pas (DA-03) ; il est masqué dès que
    # l'image est chargée.
    pose = re.search(r"@keyframes lp-pose \{(.*?)\}\s*\}", css, re.DOTALL)
    assert pose and "opacity" not in pose.group(1)
    assert ".lp-media.a-visuel .lp-secours { visibility: hidden; }" in css
    # Aucune animation ni transition déclarée hors du bloc conditionnel (rien ne bouge d'office).
    hors_bloc = re.sub(r"@media \(prefers-reduced-motion: no-preference\) \{.*?\n\}\n", "", css, flags=re.DOTALL)
    assert "infinite" not in css
    assert not re.search(r"(?<![\w-])(?:animation|transition)\s*:(?!\s*none)", hors_bloc), "mouvement hors du bloc no-preference"
    composants = (LANDING / "assets" / "da" / "components.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce) { .da-root * { transition: none !important; animation: none !important; } }" in composants


def test_voile_de_lisibilite_du_hero_suffisant_sur_image_noire() -> None:
    """Le titre du héro (ordinateur) est charbon sur un voile papier chaud : AA même si l'image devenait noire."""
    css = (LANDING / "css" / "landing.css").read_text(encoding="utf-8")
    m = re.search(r"--lp-voile: color-mix\(in srgb, var\(--da-color-papier-chaud\) (\d+)%, transparent\);", css)
    assert m, "voile de lisibilité absent"
    alpha = int(m.group(1)) / 100
    tokens = json.loads((da_sync.DA / "tokens" / "tokens.json").read_text(encoding="utf-8"))
    couleurs = tokens["ambiances"]["atelier"]["color"]["light"]
    papier = couleurs["papier-chaud"]["$value"]
    encre = couleurs["ink"]["$value"]

    def rgb(h: str) -> tuple[int, ...]:
        return tuple(int(h.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))

    def lum(c: tuple[float, ...]) -> float:
        lin = [(v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    for fond in ((0, 0, 0), (255, 255, 255)):
        voile = tuple(round(alpha * p + (1 - alpha) * f) for p, f in zip(rgb(papier), fond))
        a, b = lum(voile), lum(rgb(encre))
        assert (max(a, b) + 0.05) / (min(a, b) + 0.05) >= 4.5, (fond, voile)


def test_statuts_monochromes_dans_l_atelier() -> None:
    """DA-05 : badges de statut dans la palette (papier, charbon, gris chaud, lin orangé, orange) ; « Réservation
    garantie » est la boîte noire à bande orange de l'illustration."""
    tokens = json.loads((da_sync.DA / "tokens" / "tokens.json").read_text(encoding="utf-8"))
    c = {k: v["$value"] for k, v in tokens["ambiances"]["atelier"]["color"]["light"].items()}
    palette = {c[k] for k in ("bg", "surface", "surface-alt", "ink", "ink-muted", "accent", "accent-soft", "papier-chaud")}
    for k, v in c.items():
        if k.startswith("status-"):
            assert v in palette, (k, v)
    composants = (LANDING / "assets" / "da" / "components.css").read_text(encoding="utf-8")
    regle = re.search(r'\[data-ambiance="atelier"\] \.da-badge--reservation \{(.*?)\}', composants, re.DOTALL)
    assert regle and "inverse-bg" in regle.group(1) and "inset 0 -3px 0 var(--da-color-accent)" in regle.group(1)


# ----------------------------------------------------------------------------- page principale
def test_index_garde_le_contrat_et_les_textes_exacts() -> None:
    texte = _index()
    visible = vs._texte_visible(texte)
    garantie, difference = vs.textes_garantie_moteur()
    assert garantie in visible and difference in visible
    assert "Braise" in visible and "Nom provisoire" in visible and "création originale" in visible
    assert "Qui est Braise" in visible and "Ce n'est pas un personnage Pokémon" in visible
    assert not re.search(r"\bLumi\b|loutre", texte, re.IGNORECASE), "mascotte abandonnée (décision du 06.10.2026)"
    assert "ni approuvée par The Pokémon Company" in visible
    assert "Pokémon JCC en français, expédié depuis Genève" in re.search(r"<h1.*?</h1>", texte, re.DOTALL).group(0)
    a = vs.analyser(texte)
    assert [i.get("data-visuel") for i in a.imgs if i.get("fetchpriority") == "high"] == ["renard-heros"]
    assert all(i.get("loading") == "lazy" for i in a.imgs if "data-visuel" in i and i.get("fetchpriority") != "high")
    assert all(i.get("width") and i.get("height") for i in a.imgs)
    assert re.search(r'<source media="\(max-width: 699px\)"[^>]*data-visuel="renard-heros-portrait"', texte)
    assert texte.count('rel="preload" as="image"') == 2
    # PERF-01 : le portrait de Braise (chapitre 01) ne concurrence jamais l'image du héro.
    assert [i.get("fetchpriority") for i in a.imgs if i.get("data-visuel") == "renard-assis"] == ["low"]
    consentement = next(c for c in a.champs if c.get("name") == "consentement")
    assert "checked" not in consentement and "required" in consentement


def test_recit_en_chapitres_dans_l_ordre() -> None:
    """Héro → Braise → jour du drop → réservation → formats → soin → Genève → alertes → questions → pied de page."""
    texte = _index()
    positions = [texte.index(f'id="{c}"') for c in CHAPITRES]
    assert positions == sorted(positions)
    assert texte.index('class="lp-hero"') < positions[0] and positions[-1] < texte.index('<footer class="lp-pied">')
    ordre = re.findall(r'data-visuel="([a-z-]+)"', texte.split("<main", 1)[1])
    # Braise porte chaque chapitre récit (DA-09 : le fil narratif ne disparaît plus sur 4 000 px) ; le chapitre des
    # formats est sans image (HON-01) ; une photo du propriétaire par chapitre au plus, sauf le soin.
    attendu = ["renard-heros-portrait", "renard-heros", "renard-assis", "renard-jour-de-drop", "renard-reservation",
               "renard-classeur", "photo-boite-etuis", "photo-mains-sleeve", "renard-leman", "renard-alertes",
               "photo-classeur", "renard-pied-de-page"]
    assert ordre == attendu
    numeros = re.findall(r'<p class="lp-numero" data-fil-chapitre><span class="lp-numero__chiffre">(\d\d)</span>', texte)
    assert numeros == [f"{i:02d}" for i in range(1, 9)]


def test_page_d_attente_resserree() -> None:
    """DA-09 : la réservation garantie n'est plus expliquée trois fois, les statuts passent en question fréquente et
    les champs facultatifs du formulaire sont repliés (toujours dans la page, consentement et confidentialité dehors)."""
    texte = _index()
    drop = re.search(r'<section [^>]*id="drop".*?</section>', texte, re.DOTALL).group(0)
    assert "lp-etapes" not in drop and "Réservation garantie</span>" not in drop
    assert 'id="statuts"' not in texte and 'id="faq-statuts"' in texte
    faq = re.search(r'<section [^>]*id="faq".*?</section>', texte, re.DOTALL).group(0)
    assert all(s in vs._texte_visible(faq) for s in ("Stock local", "Précommande", "Rupture"))
    formulaire = re.search(r'<form .*?</form>', texte, re.DOTALL).group(0)
    replie = re.search(r'<details class="lp-preciser">(.*?)</details>', formulaire, re.DOTALL)
    assert replie and "<summary>" in replie.group(1)
    for nom in ('name="formats"', 'name="budget"', 'name="pour_qui"', 'name="canton"'):
        assert nom in replie.group(1), nom
    for nom in ('name="email"', 'name="consentement"', 'href="confidentialite.html"', 'id="lp-envoyer"'):
        assert nom in formulaire and nom not in replie.group(1), nom
    assert "open" not in re.search(r'<details class="lp-preciser"[^>]*>', formulaire).group(0)


def test_fil_orange_raccorde_aux_filets_mesures() -> None:
    """Chaque ancre du fil porte le filet mesuré du manifeste (data-fil écrit par visuels.py), jamais à la main."""
    texte = _index()
    m = visuels.charger()
    assert '<div class="lp-fil" aria-hidden="true"><svg class="lp-fil__svg" focusable="false"></svg></div>' in texte
    figures = re.findall(r"<figure\b[^>]*\bdata-fil-ancre(?:=\"([a-z]*)\")?[^>]*>(.*?)</figure>", texte, re.DOTALL)
    # Départ (héro), traversées (Braise, drop, alertes), branches (bande de la photo de la boîte, filet des mains),
    # corde du Léman (le fil passe sous l'image et ressort du bout de la corde), arrivée (pied de page).
    assert [r for r, _ in figures] == ["depart", "", "", "branche", "branche", "corde", "", "arrivee"]
    for _, contenu in figures:
        balises = re.findall(r"<(?:img|source)\b[^>]*>", contenu)
        assert balises
        for balise in balises:
            ident = re.search(r'data-visuel="([^"]+)"', balise).group(1)
            assert m["visuels"][ident]["fil"], ident
            assert f'data-fil="{visuels.fil_html(m, ident)}"' in balise, ident
            assert f'data-fil-ep="{visuels.fil_ep_html(m, ident)}"' in balise, ident
            assert f'data-fil-couleurs="{visuels.fil_couleurs_html(m, ident)}"' in balise, ident
    # Chaque numéro de chapitre est un point d'attache du fil (son tiret se dessine quand le fil l'atteint).
    assert texte.count('<p class="lp-numero" data-fil-chapitre>') == 8
    # Un visuel sans filet ne porte jamais d'attribut data-fil* (retiré s'il était écrit à la main).
    for balise in re.findall(r"<img\b[^>]*>", texte):
        ident = re.search(r'data-visuel="([^"]+)"', balise)
        if ident and not m["visuels"][ident.group(1)]["fil"]:
            assert "data-fil" not in balise, ident.group(1)


#: Objets qui sont des types d'accessoires vendus (BP : « quelques accessoires », sleeves) : protège-cartes, étuis,
#: classeurs, pochettes, boîtes (de rangement ou non : une boîte noire peut se lire comme une boîte de rangement).
ACCESSOIRES_MONTRES = re.compile(r"[ée]tuis?|classeurs?|pochettes?|sleeves?|toploaders?|prot[èe]ge-cartes|bo[îi]tes?", re.IGNORECASE)


def _sections(texte: str) -> list[str]:
    return re.findall(r"<section\b.*?</section>", texte, re.DOTALL)


def test_photos_d_ambiance_jamais_presentees_comme_des_produits() -> None:
    """Les photos du propriétaire ont une légende neutre et vérifiable ; aucune image montrant un type d'accessoire
    n'est dans une section qui cite « Accessoires » (BP : accessoires vendus ; DIRECTION_ATELIER.md §7 ; HON-01)."""
    texte = _index()
    m = visuels.charger()
    for ident in ("photo-classeur", "photo-mains-sleeve", "photo-boite-etuis"):
        assert f'data-visuel="{ident}"' in texte
    legendes = re.findall(r'<(?:p|figcaption) class="lp-legende[^"]*">(.*?)</(?:p|figcaption)>', texte, re.DOTALL)
    photos = [vs._normaliser(lg) for lg in legendes if "Photo" in lg]
    assert len(photos) == 2
    for lg in photos:
        assert "ambiance" in lg and "vierges" in lg and "sans marque" in lg and "photo réelle du produit vendu" in lg, lg
        # Aucune affirmation invérifiable sur ce que la boutique vendra ou non (HON-01).
        assert not re.search(r"ne représente(?:nt)? pas (?:un|des) produits?|\bnos\b", lg), lg
    montre = {ident for ident, v in m["visuels"].items() if ACCESSOIRES_MONTRES.search(v["description"])}
    assert {"photo-classeur", "photo-mains-sleeve", "photo-boite-etuis", "renard-classeur", "renard-heros"} <= montre
    citent = [s for s in _sections(texte) if "Accessoires" in vs._texte_visible(s) or 'value="accessoires"' in s]
    assert citent  # le chapitre des formats et le formulaire d'alertes
    for section in citent:
        images = set(re.findall(r'data-visuel="([a-z-]+)"', section))
        assert not images & montre, (re.search(r'id="([a-z]+)"', section).group(1), images & montre)
    formats = re.search(r'<section [^>]*id="formats".*?</section>', texte, re.DOTALL).group(0)
    assert "data-visuel" not in formats  # le chapitre qui annonce ce qui sera vendu n'a aucune image


def test_jour_du_drop_boite_symbolique_legendee() -> None:
    """HON-02 : la boîte ouverte de l'illustration du drop est un symbole, légendé comme tel ; aucun texte ne dit que
    Braise ou la boutique « ouvre la boîte » (les produits scellés sont contrôlés sans être ouverts)."""
    texte = _index()
    drop = re.search(r'<section [^>]*id="drop".*?</section>', texte, re.DOTALL).group(0)
    legende = re.search(r'data-visuel="renard-jour-de-drop".*?</figure>\s*<p class="lp-legende[^"]*"[^>]*>(.*?)</p>', drop, re.DOTALL)
    assert legende, "légende absente juste après l'illustration du drop"
    lg = vs._normaliser(legende.group(1))
    assert "symbole du drop" in lg and "pas un produit ouvert" in lg and "qu'une lumière" in lg and "vierges" in lg, lg
    visible = vs._texte_visible(drop)
    assert "Le drop n'ouvre que lorsque le produit est là" in visible and "toujours scellé" in visible
    assert "symbole du drop" in visuels.charger()["visuels"]["renard-jour-de-drop"]["alt"]
    motif = next(m for m, libelle in vs.AFFIRMATIONS_INEXACTES if "jamais ouverts" in libelle)
    # La règle elle-même (« sans ouvrir les produits ») n'est jamais prise pour une affirmation contradictoire.
    assert not motif.search("Contrôlés à réception sans ouvrir les produits.")
    assert motif.search("Nous ouvrons les boîtes devant vous.")
    for page in [*LANDING.glob("*.html"), *MAQUETTES.glob("*.html")]:
        assert not motif.search(vs._texte_visible(page.read_text(encoding="utf-8"))), page.name


def test_textes_alternatifs_fideles_aux_images() -> None:
    """A11Y-02 : l'illustration de la réservation montre quatre boîtes (la dernière en partie cachée par la queue) : le
    texte alternatif ne les compte pas."""
    v = visuels.charger()["visuels"]["renard-reservation"]
    assert "une pile de boîtes noires vierges à bande orange" in v["alt"]
    assert not re.search(r"\b(?:trois|deux|3)\b", v["alt"] + " " + v["description"])
    for page in (LANDING / "index.html", MAQUETTES / "fiche-produit.html"):
        assert visuels.alt_html(visuels.charger(), "renard-reservation") in page.read_text(encoding="utf-8"), page.name


def test_creations_originales_pour_la_boutique() -> None:
    """IP-03 : « création originale pour la boutique », jamais « de la boutique » (droits sur une illustration générée
    incertains, LDA art. 2) : pages, pages générées, maquettes et DA."""
    textes = {p.name: p.read_text(encoding="utf-8") for p in [*LANDING.glob("*.html"), *MAQUETTES.glob("*.html")]}
    textes.update({f"généré {k}": v for k, v in publication.pages_secondaires().items()})
    textes["DIRECTION_ATELIER.md"] = (da_sync.DA / "DIRECTION_ATELIER.md").read_text(encoding="utf-8")
    for nom, texte in textes.items():
        assert not vs.CREATION_DE_LA_BOUTIQUE_RE.search(texte), nom
    assert "créations originales pour la boutique" in vs._texte_visible(_index())


def test_textes_de_garantie_identiques_au_moteur() -> None:
    predrop = pytest.importorskip("pokeshop.predrop")
    assert vs.textes_garantie_moteur() == (predrop.GUARANTEE_TEXT_FR, predrop.NO_DIFFERENCE_REFUND_FR)


@pytest.mark.parametrize(
    ("modification", "attendu"),
    [
        (lambda t: t.replace('loading="lazy" decoding="async" data-visuel="renard-pied-de-page"', 'decoding="async" data-visuel="renard-pied-de-page"'), "loading"),
        (lambda t: t.replace('data-visuel="renard-pied-de-page"', 'fetchpriority="high" data-visuel="renard-pied-de-page"'), "fetchpriority"),
        (lambda t: t.replace('width="1083" height="140" loading="lazy">', 'loading="lazy">', 1), "width/height"),
        (lambda t: t.replace("<li>Aucune fausse urgence</li>", "<li>Plus que 3 boîtes</li>", 1), "fausse urgence"),
        (lambda t: t.replace("Le supplément pré-drop paie", "Le supplément paie"), "GUARANTEE_TEXT_FR"),
        (lambda t: t.replace("même s'il reste des unités au drop.", "sauf exception."), "NO_DIFFERENCE_REFUND_FR"),
        # Mascotte (DIRECTION_ATELIER.md §8)
        (lambda t: t.replace("Voici <em", "Voici Lumi, <em", 1), "mascotte abandonnée"),
        (lambda t: t.replace("<!-- APERCU:DEBUT -->", "<!-- APERCU:DEBUT (loutre) -->", 1), "mascotte abandonnée"),
        (lambda t: re.sub(r"[Nn]om (?:est )?provisoire", "nom", t), "nom provisoire"),
        (lambda t: re.sub(r"(?:création|illustration) originale", "création", t), "création originale"),
        (lambda t: t.replace("création originale pour la boutique", "création originale de la boutique"), "pour la boutique"),
        # HON-02 : la boutique n'ouvre jamais un produit scellé.
        (lambda t: t.replace("Le drop n'ouvre que lorsque", "Braise n'ouvre la boîte que lorsque"), "jamais ouverts"),
        (lambda t: t.replace("Aucun prix n'est encore fixé.", "Nous ouvrons chaque display pour vous."), "jamais ouverts"),
    ],
)
def test_regles_images_et_contenu_detectees(tmp_path: Path, modification, attendu: str) -> None:  # type: ignore[no-untyped-def]
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    index = dossier / "index.html"
    index.write_text(modification(index.read_text(encoding="utf-8")), encoding="utf-8")
    erreurs = vs.verifier_page(index, dossier)
    assert any(attendu in e for e in erreurs), erreurs


# ----------------------------------------------------------------------------- pages secondaires
def test_pages_secondaires_illustrees_par_braise() -> None:
    pages = publication.pages_secondaires()
    attendu = {"merci.html": "renard-couche", "inscription-confirmee.html": "renard-assis",
               "desinscription.html": "renard-couche", "confidentialite.html": "renard-assis"}
    assert publication.ILLUSTRATIONS == attendu
    for nom, ident in attendu.items():
        texte = pages[nom]
        assert f'data-visuel="{ident}"' in texte, nom
        assert "js/atelier.js" in texte and "lp-atelier" in texte and "nuit" not in texte.lower(), nom
        a = vs.analyser(texte)
        principales = [i for i in a.imgs if i.get("fetchpriority") == "high"]
        assert len(principales) == (0 if nom == "confidentialite.html" else 1), nom
        assert "création originale" in vs._texte_visible(texte), nom
    assert "Braise (nom provisoire)" in vs._texte_visible(pages["merci.html"])
    # Le texte dit ce que montre l'image (renard couché, éveillé, l'œil en coin : DA-16) ; titres avec point final.
    assert "l'œil en coin" in vs._texte_visible(pages["merci.html"]) and "roulé en boule" not in pages["merci.html"]
    for nom in ("merci.html", "inscription-confirmee.html", "desinscription.html"):
        titre = re.search(r'<h1 class="da-title">(.*?)</h1>', pages[nom]).group(1)
        assert titre.endswith("."), (nom, titre)


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
        ("fiche-produit.html", lambda t: t.replace("(nom provisoire)", ""), "nom provisoire"),
        ("drop.html", lambda t: t.replace("<h3 class=\"lp-h3\">Réception à Genève</h3>", "<h3 class=\"lp-h3\">Lumi réceptionne</h3>", 1), "mascotte abandonnée"),
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


def test_maquettes_jamais_braise_a_cote_du_produit_ou_de_ses_prix() -> None:
    """DA-04 : une illustration n'illustre jamais un produit vendu. Aucune section d'une maquette ne contient à la fois
    une illustration du renard et le titre du produit (h1, .lp-fiche__titre) ou ses deux prix (.lp-deux-prix)."""
    for page in MAQUETTES.glob("*.html"):
        texte = page.read_text(encoding="utf-8")
        principal = texte.split("<main", 1)[1]
        blocs = re.findall(r"<section\b.*?</section>", principal, re.DOTALL)
        blocs.append(re.split(r"<section\b", principal)[0])  # contenu hors section (galerie de la fiche)
        for bloc in blocs:
            if re.search(r'data-visuel="renard-', bloc):
                assert not re.search(r"<h1\b|lp-deux-prix|lp-fiche__titre", bloc), page.name
        if 'data-visuel="renard-' in texte:
            assert "ne représente pas ce produit" in vs._texte_visible(texte), page.name
    drop = (MAQUETTES / "drop.html").read_text(encoding="utf-8")
    heros = re.search(r'<section class="lp-chapitre--charbon lp-drop-hero".*?</section>', drop, re.DOTALL).group(0)
    assert "data-visuel" not in heros and "Photo réelle du produit scellé" in heros


def test_maquette_fiche_sans_illustration_en_guise_de_photo_produit() -> None:
    """La fiche montre des emplacements de photos réelles ; Braise n'apparaît que dans l'explication, jamais en galerie."""
    texte = (MAQUETTES / "fiche-produit.html").read_text(encoding="utf-8")
    galerie = re.search(r'<div class="lp-fiche__galerie">(.*?)</ul>', texte, re.DOTALL).group(1)
    assert "data-visuel" not in galerie and "Photo réelle du produit scellé" in galerie


# ----------------------------------------------------------------------------- JavaScript
def test_scripts_valides_et_sans_reseau() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent")
    for nom in ("atelier.js", "theme.js", "landing.js"):
        subprocess.run([node, "--check", str(LANDING / "js" / nom)], check=True, capture_output=True, timeout=30)
    assert not (LANDING / "js" / "nuit.js").exists()
    atelier = (LANDING / "js" / "atelier.js").read_text(encoding="utf-8")
    for interdit in ("fetch(", "XMLHttpRequest", "sendBeacon", "http://", "https://", "document.cookie", "innerHTML"):
        assert interdit not in atelier, interdit
    assert "prefers-reduced-motion: reduce" in atelier and "lp-animations" in atelier
    assert "data-fil-ancre" in atelier and "data-fil-masque" in atelier and "data-fil" in atelier
    for page in [*LANDING.glob("*.html"), *MAQUETTES.glob("*.html")]:
        assert "nuit.js" not in page.read_text(encoding="utf-8"), page.name


def test_config_visuels_hors_dossier_publie() -> None:
    assert visuels.CONFIG.parent == REPO / "site" / "config"
    assert not list(LANDING.rglob("visuels.json"))
    assert json.loads(visuels.CONFIG.read_text(encoding="utf-8"))["_avertissement"].startswith("Source UNIQUE")
