"""Visuels de la marque : manifeste unique, synchronisation des pages, import local et rapatriement (sans réseau).

Aucun test ne dépend des fichiers lourds : chaque test se construit son manifeste et ses copies de pages
(``fictifs.manifeste``), en source distante FICTIVE ET locale, et ses sources d'import (aplats générés). Les vrais
visuels ne sont contrôlés que par leur manifeste et leurs variantes publiées (revue TEST-01).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
from pathlib import Path

import fictifs
import publication
import pytest
import rapatrier_visuels as rv
import verifier_site as vs
import visuels
from fictifs import LANDING, MAQUETTES, jpeg_entete, png_entete, webp_vp8x


def webp_vp8(largeur: int, hauteur: int) -> bytes:
    """En-tête WebP avec perte (VP8) aux dimensions données."""
    trame = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", largeur, hauteur)
    corps = b"VP8 " + struct.pack("<I", len(trame)) + trame
    return b"RIFF" + struct.pack("<I", 4 + len(corps)) + b"WEBP" + corps


def webp_vp8l(largeur: int, hauteur: int) -> bytes:
    """En-tête WebP sans perte (VP8L) aux dimensions données."""
    bits = (largeur - 1) | ((hauteur - 1) << 14)
    trame = b"\x2f" + bits.to_bytes(4, "little")
    corps = b"VP8L" + struct.pack("<I", len(trame)) + trame
    return b"RIFF" + struct.pack("<I", 4 + len(corps)) + b"WEBP" + corps + b"\x00" * 16


# ----------------------------------------------------------------------------- manifeste
CLES_ATTENDUES = {
    "renard-heros", "renard-heros-portrait", "renard-assis", "renard-couche", "renard-jour-de-drop", "renard-reservation",
    "renard-alertes", "renard-classeur", "renard-leman", "renard-pied-de-page",
    "photo-boite-etuis", "photo-mains-sleeve", "photo-classeur",
}


def test_manifeste_unique_valide_et_complet() -> None:
    m = visuels.charger()
    assert visuels.valider(m) == []
    assert set(m["visuels"]) == CLES_ATTENDUES
    # Visuels 100 % locaux : aucune adresse distante, toutes les variantes publiées présentes et budgétées.
    assert m["source"] == "local" and m["base_distante"] is None
    assert visuels.erreurs_publication(m) == []
    assert rv.verifier_locaux() == []
    utilises: set[str] = set()
    for page in visuels.pages():
        utilises |= visuels.identifiants_utilises(page.read_text(encoding="utf-8"))
    assert utilises == set(m["visuels"]), set(m["visuels"]) ^ utilises
    for ident, v in m["visuels"].items():
        assert v["largeurs"][-1] <= v["largeur"], ident
        assert v["nature"] == ("photo" if ident.startswith("photo-") else "illustration"), ident
        assert re.fullmatch(r"[0-9a-f]{64}", v["empreinte_source"]) and v["fichier_source"].startswith(ident), ident
        assert (v["alt"] == "") == v.get("decoratif", False) == (ident == "renard-pied-de-page"), ident
    # Les photos d'ambiance ne se présentent jamais comme des produits en vente.
    for ident in ("photo-boite-etuis", "photo-mains-sleeve", "photo-classeur"):
        assert m["visuels"][ident]["alt"].startswith("Photo d'ambiance : "), ident


def test_sources_hors_du_dossier_publie() -> None:
    publies = sorted((LANDING / "assets" / "visuels").iterdir())
    assert publies and all(p.suffix == ".webp" for p in publies)
    assert not list(LANDING.rglob("*.jpg")) and not list(LANDING.rglob("*.jpeg"))
    assert "site/visuels-sources/" in (visuels.REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert rv.ARCHIVE == visuels.REPO / "site" / "visuels-sources"
    for f in publies:
        octets = f.read_bytes()
        assert not [b for b in rv.blocs_riff(octets) if b in rv.BLOCS_METADONNEES], f.name


@pytest.mark.parametrize(
    ("chemin", "valeur", "attendu"),
    [
        (("source",), "cdn", "source invalide"),
        (("base_distante",), "http://exemple.invalid/", "base_distante"),
        (("dossier_local",), "../ailleurs/", "dossier_local"),
        (("visuels", "renard-couche", "fichier"), "../../etc/passwd", "nom de fichier invalide"),
        (("visuels", "renard-couche", "largeur"), 0, "largeur entière"),
        (("visuels", "renard-couche", "largeurs"), [800, 480], "largeurs"),
        (("visuels", "renard-couche", "largeurs"), [480, 4096], "largeurs"),
        (("visuels", "renard-couche", "variantes"), [300], "variantes"),
        (("visuels", "renard-couche", "variantes"), "480", "variantes"),
        (("visuels", "renard-couche", "format"), "16:9", "ne respecte pas le format"),
        (("visuels", "renard-couche", "format"), "carré", "format « L:H »"),
        (("visuels", "renard-couche", "nature"), "dessin", "nature"),
        (("visuels", "renard-couche", "alt"), "", "decoratif"),
        (("visuels", "renard-pied-de-page", "alt"), "Le renard dort.", "decoratif"),
        (("visuels", "renard-couche", "usage"), " ", "usage manquante"),
        (("visuels", "renard-couche", "fichier_source"), "../renard.jpg", "fichier_source"),
        (("visuels", "renard-couche", "fichier_source"), "renard.gif", "fichier_source"),
        (("visuels", "renard-couche", "empreinte_source"), "abc", "empreinte_source"),
        (("visuels", "renard-couche", "fil"), [[0, 0.5], [1.2, 1]], "fil"),
        (("visuels", "renard-couche", "fil"), [[0, 0.5]], "fil"),
        # Règles de rédaction (DIRECTION_ATELIER.md §7–§8)
        (("visuels", "photo-classeur", "alt"), "Photo d'ambiance : nos classeurs, en vente à l'ouverture.", "jamais présentée comme un produit en vente"),
        (("visuels", "photo-boite-etuis", "description"), "Une boîte vierge et son prix.", "jamais présentée comme un produit en vente"),
        (("visuels", "renard-assis", "description"), "Le renard debout sur ses pattes arrière.", "quadrupède"),
        (("visuels", "renard-assis", "alt"), "Illustration : le renard et ses neuf queues.", "une seule queue"),
        (("visuels", "renard-assis", "alt"), "Illustration : le renard porte des gants blancs.", "sans vêtement"),
        (("visuels", "renard-couche", "alt"), "Illustration : le renard comme Évoli.", "licence"),
        (("visuels", "renard-couche", "description"), "Il tient un booster Pokémon.", "licence"),
        (("visuels", "renard-reservation", "alt"), "Illustration : le renard garde trois boîtes noires.", "vierge"),
    ],
)
def test_manifeste_invalide_refuse(chemin: tuple[str, ...], valeur: object, attendu: str) -> None:
    m = fictifs.manifeste("distant")
    cible = m
    for cle in chemin[:-1]:
        cible = cible[cle]
    cible[chemin[-1]] = valeur
    assert any(attendu in e for e in visuels.valider(m))


def test_source_locale_sans_variantes_refusee() -> None:
    m = fictifs.manifeste("distant")
    m["source"] = "local"
    assert any("sans variantes" in e for e in visuels.valider(m))
    # Seul l'import local lit un manifeste dont les variantes restent à produire ; tout le reste est contrôlé.
    assert visuels.valider(m, exiger_variantes=False) == []


def test_base_distante_facultative_seulement_en_local() -> None:
    m = fictifs.manifeste("local")
    m["base_distante"] = None
    assert visuels.valider(m) == []
    m["source"] = "distant"
    assert any("base_distante : absente" in e for e in visuels.valider(m))
    with pytest.raises(visuels.VisuelsError):
        visuels.url_distante(m, "renard-heros", "min")
    assert visuels.hote_distant(m) == ""


@pytest.mark.parametrize("source", ["distant", "local"])
def test_attributs_sans_png_et_largeurs_exactes(source: str) -> None:
    m = fictifs.manifeste(source)
    page = LANDING / "index.html"
    nom = m["visuels"]["renard-heros"]["fichier"]
    a = visuels.attributs(m, "renard-heros", "img", page)
    assert (a["width"], a["height"]) == ("2688", "1152")
    assert a["alt"] == m["visuels"]["renard-heros"]["alt"].replace('"', "&quot;")
    assert ".png" not in a["srcset"] and ".png" not in a["src"]
    if source == "distant":
        # Aperçu : la variante légère seule (la PNG HD serait choisie par presque tous les écrans).
        assert a["src"] == a["srcset"] == f"{m['base_distante']}{nom}_min.webp"
    else:
        assert a["srcset"] == ", ".join(f"assets/visuels/{nom}-{w}.webp {w}w" for w in (640, 960, 1280, 1920, 2688))
        assert a["src"] == f"assets/visuels/{nom}-1280.webp"
        maquette = MAQUETTES / "drop.html"
        assert visuels.src(m, "renard-heros", maquette) == f"../landing/assets/visuels/{nom}-1280.webp"
        assert visuels.src(m, "renard-couche", page).endswith("-1280.webp")
        assert visuels.src(m, "renard-heros-portrait", page).endswith("-1140.webp")
    assert set(visuels.attributs(m, "renard-heros", "link", page)) == {"href", "imagesrcset"}
    # Filet orange mesuré (« fil ») : écrit sur <img> et <source> d'un visuel qui en a un, jamais sur un <link>.
    assert set(visuels.attributs(m, "renard-heros", "source", page)) == {"srcset", "width", "height", "data-fil"}
    assert a["data-fil"] == "0.012 0.871 0.729 0.997" == visuels.fil_html(m, "renard-heros")
    assert "data-fil" not in visuels.attributs(m, "renard-leman", "img", page)  # visuel sans filet
    assert set(visuels.attributs(m, "renard-leman", "source", page)) == {"srcset", "width", "height"}


def test_data_fil_ecrit_retire_et_jamais_a_la_main(tmp_path: Path) -> None:
    """Le filet vient du manifeste : réécrit s'il est modifié, retiré d'un visuel sans filet, désynchronisation détectée."""
    m = fictifs.manifeste("local")
    page = tmp_path / "p.html"
    sortie = visuels.appliquer_texte('<img alt="" data-visuel="renard-assis" data-fil="0 0 1 1" src="">', m, page, racine=tmp_path)
    assert 'data-fil="0 0.877 0.909 1"' in sortie and 'data-fil="0 0 1 1"' not in sortie
    sans = visuels.appliquer_texte('<img alt="" data-visuel="renard-classeur" data-fil="0 0.5 1 0.5" src="">', m, page, racine=tmp_path)
    assert "data-fil" not in sans
    assert visuels.appliquer_texte(sortie, m, page, racine=tmp_path) == sortie  # idempotent
    dossier, m2 = fictifs.landing_aux_visuels(tmp_path, "local", nom="fil")
    index = dossier / "index.html"
    texte = index.read_text(encoding="utf-8")
    assert 'data-fil="0 0.877 0.909 1"' in texte
    index.write_text(texte.replace('data-fil="0 0.877 0.909 1"', 'data-fil="0 0.5 0.9 1"', 1), encoding="utf-8")
    assert any("désynchronisées" in e for e in visuels.verifier(m2, [index], dossier))


def test_pages_synchronisees_et_desynchronisation_detectee(tmp_path: Path) -> None:
    assert visuels.verifier() == []  # quel que soit l'état (aperçu distant ou visuels rapatriés)
    dossier, m = fictifs.landing_aux_visuels(tmp_path, "distant")
    page = dossier / "index.html"
    texte = page.read_text(encoding="utf-8")
    assert visuels.verifier(m, [page], dossier) == []
    assert visuels.appliquer_texte(texte, m, page, racine=dossier) == texte  # idempotent
    page.write_text(texte.replace('width="2688"', 'width="9999"', 1), encoding="utf-8")
    assert any("désynchronisées" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte.replace('data-visuel="renard-pied-de-page"', 'data-visuel="inconnu"'), encoding="utf-8")
    assert any("visuel inconnu" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte + f'<!-- {m["base_distante"]}x.png -->', encoding="utf-8")
    assert any("hors d'une balise data-visuel" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte.replace('<img class="lp-hero__img"', '<img srcset="x.png 2688w" class="lp-hero__img"', 1), encoding="utf-8")
    assert any("PNG dans un srcset" in e for e in visuels.verifier(m, [page], dossier))
    # Le texte alternatif vient du manifeste : une page qui le modifie à la main est désynchronisée.
    alt = m["visuels"]["renard-heros"]["alt"]
    page.write_text(texte.replace(f'alt="{alt}"', 'alt="Un renard sur le quai"', 1), encoding="utf-8")
    assert any("désynchronisées" in e for e in visuels.verifier(m, [page], dossier))


@pytest.mark.parametrize("source", ["distant", "local"])
def test_reecriture_conserve_les_attributs_de_contexte(tmp_path: Path, source: str) -> None:
    m = fictifs.manifeste(source)
    page = tmp_path / "p.html"
    alt = m["visuels"]["renard-couche"]["alt"]
    html = '<img alt="ancien" sizes="50vw" loading="lazy" data-visuel="renard-couche" src="ancien.png">'
    sortie = visuels.appliquer_texte(html, m, page, racine=tmp_path)
    debut = "https://" if source == "distant" else "assets/visuels/"
    assert sortie.startswith(f'<img alt="{alt}" sizes="50vw" loading="lazy" data-visuel="renard-couche" src="{debut}')
    assert 'width="1280" height="1600"' in sortie and "ancien" not in sortie
    assert visuels.appliquer_texte(sortie, m, page, racine=tmp_path) == sortie
    # Texte alternatif propre au contexte : gardé seulement si la balise le déclare.
    contexte = '<img alt="Le renard, en vignette." data-alt-contexte data-visuel="renard-couche" src="x">'
    garde = visuels.appliquer_texte(contexte, m, page, racine=tmp_path)
    assert 'alt="Le renard, en vignette."' in garde and alt not in garde
    sans_alt = visuels.appliquer_texte('<img data-visuel="renard-pied-de-page" src="x">', m, page, racine=tmp_path)
    assert 'alt=""' in sans_alt  # visuel décoratif : alt vide écrit par le manifeste


def test_verificateur_site_admet_le_distant_en_apercu_seulement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Le manifeste du dépôt n'a aucune adresse distante : l'aperçu distant est simulé avec un hôte FICTIF.
    assert vs._hote_visuels() is None
    monkeypatch.setattr(vs, "_hote_visuels", lambda: fictifs.HOTE_DISTANT_FICTIF)
    dossier, m = fictifs.landing_aux_visuels(tmp_path, "distant")
    index = dossier / "index.html"
    texte = index.read_text(encoding="utf-8")
    assert vs.verifier_page(index, dossier) == []
    assert any("visuel distant dans un dossier de publication" in e for e in vs.verifier_page(index, dossier, publication_mode=True))
    index.write_text(texte.replace(m["base_distante"], "https://images.exemple.invalid/", 1), encoding="utf-8")
    assert any("hôte hors de site/config/visuels.json" in e for e in vs.verifier_page(index, dossier))


def test_verificateur_site_admet_le_local(tmp_path: Path) -> None:
    dossier, m = fictifs.landing_aux_visuels(tmp_path, "local")
    index = dossier / "index.html"
    assert vs.verifier_page(index, dossier) == []
    assert not [e for e in vs.verifier_page(index, dossier, publication_mode=True) if "visuel" in e]
    visuels.chemin_variante(m, "renard-pied-de-page", 640, dossier).unlink()
    assert any("visuel introuvable" in e for e in vs.verifier_page(index, dossier))
    # Sans base distante, toute adresse distante d'un visuel est refusée, même en aperçu.
    index.write_text(index.read_text(encoding="utf-8").replace('src="assets/visuels/', f'src="{fictifs.BASE_DISTANTE_FICTIVE}', 1), encoding="utf-8")
    assert any("hôte hors de site/config/visuels.json" in e for e in vs.verifier_page(index, dossier))


# ----------------------------------------------------------------------------- formats et contrôles
@pytest.mark.parametrize(
    ("octets", "attendu"),
    [(png_entete(2688, 1152), ("png", 2688, 1152)), (webp_vp8x(1344, 576), ("webp", 1344, 576)),
     (webp_vp8(800, 343), ("webp", 800, 343)), (webp_vp8l(1024, 439), ("webp", 1024, 439)),
     (jpeg_entete(1920, 1086), ("jpeg", 1920, 1086)), (jpeg_entete(1152, 1440, sof=0xC2), ("jpeg", 1152, 1440))],
)
def test_dimensions_lues_dans_les_en_tetes(octets: bytes, attendu: tuple[str, int, int]) -> None:
    assert rv.dimensions(octets) == attendu


def test_controles_de_la_source_et_des_variantes() -> None:
    v = {"largeur": 2688, "hauteur": 1152}
    assert rv.controler_source(png_entete(2688, 1152), v) == (2688, 1152)
    for octets, motif in (
        (b"<html>erreur</html>", "format non reconnu"),
        (webp_vp8x(2688, 1152), "png attendu"),
        (png_entete(2000, 1152), "dimensions"),
        (b"", "vide"),
    ):
        with pytest.raises(rv.RapatriementError, match=motif):
            rv.controler_source(octets, v)
    rv.controler_variante(webp_vp8x(1280, 549), 1280, v)
    exif = b"EXIF" + struct.pack("<I", 4) + b"GPS!"
    avec_exif = webp_vp8x(1280, 549) + exif
    avec_exif = avec_exif[:4] + struct.pack("<I", len(avec_exif) - 8) + avec_exif[8:]
    for octets, motif in (
        (png_entete(1280, 549), "webp attendu"),
        (webp_vp8x(1280, 600), "dimensions"),
        (webp_vp8x(1280, 549) + b"\x00" * (visuels.plafond_octets(1280) + 1), "budget"),
        (avec_exif, "métadonnées"),
    ):
        with pytest.raises(rv.RapatriementError, match=motif):
            rv.controler_variante(octets, 1280, v)


def test_controles_d_un_fichier_source_local() -> None:
    v = {"format": "16:9", "largeurs": [640, 1280, 1920], "largeur": 1920, "hauteur": 1086}
    assert rv.controler_import(jpeg_entete(1920, 1086), v) == ("jpeg", 1920, 1086)
    assert rv.controler_import(webp_vp8x(3840, 2160), v) == ("webp", 3840, 2160)  # plus grande, mêmes proportions
    for octets, motif in (
        (b"", "vide"),
        (b"GIF89a" + b"\x00" * 20, "format non reconnu"),
        (jpeg_entete(1920, 1440), "proportions"),
        (png_entete(1280, 720), "insuffisante"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "JPEG"),
    ):
        with pytest.raises(rv.RapatriementError, match=motif):
            rv.controler_import(octets, v)


def test_budgets_de_poids() -> None:
    assert visuels.plafond_octets(1520) == 250 * 1024  # mobile (couverture 9:16, 390 px en DPR 3 ou 4)
    assert visuels.plafond_octets(1920) == visuels.plafond_octets(2688) == 450 * 1024  # ordinateur


# ----------------------------------------------------------------------------- rapatriement (réseau simulé)
def _petit_manifeste(tmp_path: Path) -> tuple[Path, Path, list[Path], dict]:
    """Deux visuels de petite taille (tests rapides) et une page qui les porte."""
    pytest.importorskip("PIL")
    m = fictifs.manifeste("distant")
    m["visuels"] = {
        "banniere": {**m["visuels"]["renard-heros"], "fichier": "banniere", "largeur": 420, "hauteur": 180, "largeurs": [160, 320, 420]},
        "portrait": {**m["visuels"]["renard-heros-portrait"], "fichier": "portrait", "largeur": 190, "hauteur": 336, "largeurs": [120, 190]},
    }
    chemin = tmp_path / "visuels.json"
    chemin.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    racine = tmp_path / "landing"
    racine.mkdir()
    page = racine / "index.html"
    page.write_text(
        '<link rel="preload" as="image" data-visuel="banniere" href="x">\n'
        '<picture><source media="(max-width: 699px)" sizes="100vw" data-visuel="portrait" srcset="x">'
        '<img alt="" sizes="100vw" data-visuel="banniere" src="x"></picture>\n',
        encoding="utf-8",
    )
    visuels.appliquer(m, [page], racine)
    return chemin, racine, [page], m


def test_rapatriement_archive_produit_les_variantes_et_bascule(tmp_path: Path) -> None:
    chemin, racine, pages, m = _petit_manifeste(tmp_path)
    archive = tmp_path / "archive"
    appels, telecharge = fictifs.reseau_simule(m)
    rapport = rv.rapatrier(chemin, racine, archive=archive, telecharge=telecharge, pages=pages)
    assert rapport.erreurs == [] and rapport.bascule and len(appels) == 2 and rapport.ecartees == []
    # La PNG d'origine est archivée HORS du dossier publié ; seules des WebP sont écrites dans la landing.
    assert sorted(p.name for p in archive.iterdir()) == sorted(v["fichier"] + ".png" for v in m["visuels"].values())
    publies = sorted(p.name for p in (racine / "assets" / "visuels").iterdir())
    assert publies and all(n.endswith(".webp") for n in publies) and len(publies) == 5
    apres = visuels.charger(chemin)
    assert apres["source"] == "local" and apres["visuels"]["banniere"]["variantes"] == [160, 320, 420]
    for ident, v in apres["visuels"].items():
        for largeur in v["variantes"]:
            fmt, l_reel, h_reel = rv.dimensions(visuels.chemin_variante(apres, ident, largeur, racine).read_bytes())
            assert (fmt, l_reel, h_reel) == ("webp", largeur, visuels.hauteur_variante(v, largeur))
    index = pages[0].read_text(encoding="utf-8")
    assert m["base_distante"] not in index and ".png" not in index
    nom = m["visuels"]["banniere"]["fichier"]
    assert f'srcset="assets/visuels/{nom}-160.webp 160w, assets/visuels/{nom}-320.webp 320w, assets/visuels/{nom}-420.webp 420w"' in index
    assert visuels.erreurs_publication(apres, racine) == []
    assert rv.verifier_locaux(chemin, racine) == []
    assert visuels.verifier(apres, pages, racine) == []
    # Relance : rien n'est retéléchargé (archive contrôlée), les variantes sont reproduites à l'identique.
    appels2, telecharge2 = fictifs.reseau_simule(m)
    rapport2 = rv.rapatrier(chemin, racine, archive=archive, telecharge=telecharge2, pages=pages)
    assert appels2 == [] and len(rapport2.deja_presents) == 2 and rapport2.bascule
    # Retour à l'aperçu distant : fichiers gardés, publication de nouveau refusée.
    rv.revenir_distant(chemin, pages, racine)
    assert m["base_distante"] in pages[0].read_text(encoding="utf-8")
    assert visuels.erreurs_publication(visuels.charger(chemin), racine)


def test_rapatriement_ferme_par_defaut_si_un_fichier_manque(tmp_path: Path) -> None:
    chemin, racine, pages, m = _petit_manifeste(tmp_path)
    avant = chemin.read_text(encoding="utf-8")
    index_avant = pages[0].read_text(encoding="utf-8")
    _, telecharge = fictifs.reseau_simule(m, echec="portrait")
    rapport = rv.rapatrier(chemin, racine, archive=tmp_path / "archive", telecharge=telecharge, pages=pages)
    assert not rapport.bascule and any("portrait" in e for e in rapport.erreurs)
    assert chemin.read_text(encoding="utf-8") == avant
    assert pages[0].read_text(encoding="utf-8") == index_avant
    assert not (racine / "assets").exists()
    assert not list((tmp_path / "archive").glob(".telechargement-*"))


def test_source_archivee_corrompue_refusee_puis_forcee(tmp_path: Path) -> None:
    chemin, racine, pages, m = _petit_manifeste(tmp_path)
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / (m["visuels"]["portrait"]["fichier"] + ".png")).write_bytes(b"<html>page d'erreur</html>")
    _, telecharge = fictifs.reseau_simule(m)
    rapport = rv.rapatrier(chemin, racine, archive=archive, telecharge=telecharge, pages=pages)
    assert not rapport.bascule and any("portrait (png)" in e for e in rapport.erreurs)
    assert rv.rapatrier(chemin, racine, archive=archive, telecharge=telecharge, pages=pages, forcer=True).bascule


def test_variante_hors_budget_ecartee_et_aucune_refusee(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chemin, racine, pages, m = _petit_manifeste(tmp_path)
    _, telecharge = fictifs.reseau_simule(m)
    monkeypatch.setattr(visuels, "plafond_octets", lambda largeur: 10**9 if largeur <= 160 else 10)
    rapport = rv.rapatrier(chemin, racine, archive=tmp_path / "archive", telecharge=telecharge, pages=pages)
    assert rapport.erreurs == [] and rapport.bascule
    assert any("banniere 320 px" in e for e in rapport.ecartees)
    assert visuels.charger(chemin)["visuels"]["banniere"]["variantes"] == [160]
    monkeypatch.setattr(visuels, "plafond_octets", lambda largeur: 10)
    rapport = rv.rapatrier(chemin, racine, archive=tmp_path / "archive", telecharge=telecharge, pages=pages)
    assert not rapport.bascule and any("aucune variante" in e for e in rapport.erreurs)


def test_telechargement_https_uniquement() -> None:
    with pytest.raises(rv.RapatriementError):
        rv.telecharger("http://exemple.invalid/x.png")


def test_rapatriement_impossible_sans_base_distante(tmp_path: Path) -> None:
    chemin, racine, pages, m = _petit_manifeste(tmp_path)
    m["base_distante"] = None
    m["source"] = "local"
    for v in m["visuels"].values():
        v["variantes"] = list(v["largeurs"])
    chemin.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    rapport = rv.rapatrier(chemin, racine, archive=tmp_path / "archive", telecharge=lambda url: b"", pages=pages)
    assert not rapport.bascule and any("--importer" in e for e in rapport.erreurs)
    with pytest.raises(rv.RapatriementError, match="aucune base_distante"):
        rv.revenir_distant(chemin, pages, racine)


# ----------------------------------------------------------------------------- import local (sources FICTIVES)
def _a_importer(tmp_path: Path, formats: dict[str, str] | None = None) -> tuple[Path, Path, list[Path], dict, Path]:
    """Trois visuels à importer (JPEG, PNG, WebP) aux dimensions réduites, une page, un dossier de sources."""
    pytest.importorskip("PIL")
    base = fictifs.manifeste("a-importer")
    m = {**base, "visuels": {
        "banniere": {**base["visuels"]["renard-heros"], "fichier": "banniere", "fichier_source": "banniere.jpg",
                     "largeur": 420, "hauteur": 180, "largeurs": [160, 320, 420]},
        "portrait": {**base["visuels"]["renard-heros-portrait"], "fichier": "portrait", "fichier_source": "portrait.png",
                     "largeur": 190, "hauteur": 336, "largeurs": [120, 190]},
        "photo": {**base["visuels"]["photo-mains-sleeve"], "fichier": "photo", "fichier_source": "photo.webp",
                  "largeur": 240, "hauteur": 300, "largeurs": [120, 240]},
    }}
    chemin = tmp_path / "visuels.json"
    chemin.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    racine = tmp_path / "landing"
    racine.mkdir()
    page = racine / "index.html"
    page.write_text(
        '<picture><source media="(max-width: 699px)" sizes="100vw" data-visuel="portrait" srcset="">'
        '<img alt="" sizes="100vw" data-visuel="banniere" src=""></picture>\n'
        '<img alt="" sizes="30vw" loading="lazy" data-visuel="photo" src="">\n',
        encoding="utf-8",
    )
    sources = tmp_path / "sources"
    fictifs.sources_fictives(m, sources)
    return chemin, racine, [page], m, sources


def test_import_local_archive_produit_les_variantes_et_bascule(tmp_path: Path) -> None:
    chemin, racine, pages, m, sources = _a_importer(tmp_path)
    archive = tmp_path / "archive"
    rapport = rv.importer(sources, chemin, racine, archive=archive, pages=pages)
    assert rapport.erreurs == [] and rapport.bascule and sorted(rapport.importes) == ["banniere", "photo", "portrait"]
    # Sources archivées telles quelles HORS du dossier publié, à l'extension de leur format réel.
    assert sorted(p.name for p in archive.iterdir()) == ["banniere.jpg", "photo.webp", "portrait.png"]
    for p in archive.iterdir():
        assert p.read_bytes() == (sources / p.name).read_bytes()
    publies = sorted(p.name for p in (racine / "assets" / "visuels").iterdir())
    assert publies == ["banniere-160.webp", "banniere-320.webp", "banniere-420.webp", "photo-120.webp", "photo-240.webp",
                       "portrait-120.webp", "portrait-190.webp"]
    assert not [p for p in racine.rglob("*") if p.name.startswith(".import-")]
    apres = visuels.charger(chemin)
    assert apres["source"] == "local" and apres["visuels"]["banniere"]["variantes"] == [160, 320, 420]
    for ident, v in apres["visuels"].items():
        source = sources / v["fichier_source"]
        assert v["empreinte_source"] == hashlib.sha256(source.read_bytes()).hexdigest()
        for largeur in v["variantes"]:
            octets = visuels.chemin_variante(apres, ident, largeur, racine).read_bytes()
            assert rv.dimensions(octets) == ("webp", largeur, visuels.hauteur_variante(v, largeur))
            assert not [b for b in rv.blocs_riff(octets) if b in rv.BLOCS_METADONNEES]
            assert (visuels.chemin_variante(apres, ident, largeur, racine).stat().st_mode & 0o777) == 0o644
    index = pages[0].read_text(encoding="utf-8")
    assert 'srcset="assets/visuels/banniere-160.webp 160w, assets/visuels/banniere-320.webp 320w, assets/visuels/banniere-420.webp 420w"' in index
    assert f'alt="{apres["visuels"]["photo"]["alt"]}"' in index and "https://" not in index
    assert visuels.erreurs_publication(apres, racine) == []
    assert visuels.verifier(apres, pages, racine) == []
    assert rv.verifier_locaux(chemin, racine, archive) == []
    # Relance : idempotente (mêmes variantes, même manifeste, pages inchangées).
    avant = {p.name: p.read_bytes() for p in (racine / "assets" / "visuels").iterdir()}
    manifeste_avant = chemin.read_text(encoding="utf-8")
    rapport2 = rv.importer(sources, chemin, racine, archive=archive, pages=pages)
    assert rapport2.bascule and rapport2.pages == [] and chemin.read_text(encoding="utf-8") == manifeste_avant
    assert {p.name: p.read_bytes() for p in (racine / "assets" / "visuels").iterdir()} == avant
    # Une archive remplacée en douce est signalée par le contrôle.
    (archive / "photo.webp").write_bytes(fictifs.image_reelle(240, 300, "WEBP", (10, 10, 10)))
    assert any("archive photo.webp différente" in e for e in rv.verifier_locaux(chemin, racine, archive))


@pytest.mark.parametrize(
    ("alteration", "motif"),
    [
        (lambda s: (s / "portrait.png").unlink(), "fichier source absent"),
        (lambda s: (s / "banniere.jpg").write_bytes(fictifs.image_reelle(420, 300, "JPEG")), "proportions"),
        (lambda s: (s / "banniere.jpg").write_bytes(fictifs.image_reelle(210, 90, "JPEG")), "insuffisante"),
        (lambda s: (s / "photo.webp").write_text("<html>pas une image</html>", encoding="utf-8"), "format non reconnu"),
        (lambda s: (s / "banniere.png").write_bytes(fictifs.image_reelle(420, 180, "PNG")), None),  # fichier_source prime
    ],
)
def test_import_ferme_par_defaut(tmp_path: Path, alteration, motif: str | None) -> None:  # type: ignore[no-untyped-def]
    chemin, racine, pages, m, sources = _a_importer(tmp_path)
    avant, page_avant = chemin.read_text(encoding="utf-8"), pages[0].read_text(encoding="utf-8")
    alteration(sources)
    rapport = rv.importer(sources, chemin, racine, archive=tmp_path / "archive", pages=pages)
    if motif is None:
        assert rapport.bascule and rapport.erreurs == []
        return
    assert not rapport.bascule and any(motif in e for e in rapport.erreurs), rapport.erreurs
    # Rien n'est écrit : ni variantes, ni archive, ni manifeste, ni pages.
    assert chemin.read_text(encoding="utf-8") == avant and pages[0].read_text(encoding="utf-8") == page_avant
    assert not (racine / "assets").exists() and not (tmp_path / "archive").exists()
    assert [p.name for p in racine.iterdir()] == ["index.html"]


def test_import_refuse_une_page_au_visuel_inconnu(tmp_path: Path) -> None:
    chemin, racine, pages, m, sources = _a_importer(tmp_path)
    pages[0].write_text(pages[0].read_text(encoding="utf-8") + '<img alt="" data-visuel="lumi" src="">', encoding="utf-8")
    rapport = rv.importer(sources, chemin, racine, archive=tmp_path / "archive", pages=pages)
    assert not rapport.bascule and any("visuel inconnu « lumi »" in e for e in rapport.erreurs)
    assert not (racine / "assets").exists() and visuels.charger(chemin, exiger_variantes=False)["visuels"]["photo"]["variantes"] is None


def test_import_partiel_seulement(tmp_path: Path) -> None:
    chemin, racine, pages, m, sources = _a_importer(tmp_path)
    rapport = rv.importer(sources, chemin, racine, archive=tmp_path / "a", pages=pages, seulement=["banniere"])
    assert not rapport.bascule and any("portrait : aucune variante locale" in e for e in rapport.erreurs)
    assert rv.importer(sources, chemin, racine, archive=tmp_path / "a", pages=pages).bascule
    (sources / "banniere.jpg").write_bytes(fictifs.image_reelle(420, 180, "JPEG", (30, 27, 25)))
    rapport = rv.importer(sources, chemin, racine, archive=tmp_path / "a", pages=pages, seulement=["banniere"])
    assert rapport.bascule and rapport.importes == ["banniere"]
    assert visuels.charger(chemin)["visuels"]["banniere"]["empreinte_source"] == hashlib.sha256((sources / "banniere.jpg").read_bytes()).hexdigest()
    assert any("inconnu" in e for e in rv.importer(sources, chemin, racine, archive=tmp_path / "a", pages=pages, seulement=["lumi"]).erreurs)


def test_import_applique_l_orientation_et_retire_les_metadonnees(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    chemin, racine, pages, m, sources = _a_importer(tmp_path)
    # Bannière stockée « couchée » (180 × 420) avec orientation EXIF 6 et des coordonnées GPS : affichée en 420 × 180.
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x8825] = {1: "N", 2: (46.0, 12.0, 0.0)}
    tampon = io.BytesIO()
    Image.new("RGB", (180, 420), (239, 234, 225)).save(tampon, format="JPEG", exif=exif.tobytes(), quality=80)
    (sources / "banniere.jpg").write_bytes(tampon.getvalue())
    assert rv.dimensions(tampon.getvalue()) == ("jpeg", 180, 420) and rv.orientation_exif(tampon.getvalue()) == 6
    assert rv.controler_import(tampon.getvalue(), {**m["visuels"]["banniere"], "largeurs": [160]}, 6) == ("jpeg", 420, 180)
    rapport = rv.importer(sources, chemin, racine, archive=tmp_path / "archive", pages=pages)
    assert rapport.erreurs == [] and rapport.bascule
    octets = visuels.chemin_variante(visuels.charger(chemin), "banniere", 420, racine).read_bytes()
    assert rv.dimensions(octets) == ("webp", 420, 180)
    assert b"EXIF" not in octets and b"GPS" not in octets and b"Exif" not in octets
    # L'archive garde le fichier d'origine intact (hors du dossier publié, ignoré par git).
    assert (tmp_path / "archive" / "banniere.jpg").read_bytes() == tampon.getvalue()


def test_cli_seulement_exige_importer() -> None:
    with pytest.raises(SystemExit):
        rv.main(["--seulement", "renard-heros"])


# ----------------------------------------------------------------------------- régression : après l'import ou le rapatriement
@pytest.fixture(scope="module", params=["import", "rapatriement"])
def depot(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    pytest.importorskip("PIL")
    if request.param == "import":
        return fictifs.depot_importe(tmp_path_factory.mktemp("depot-import"))
    return fictifs.depot_rapatrie(tmp_path_factory.mktemp("depot-rapatrie"))


def test_apres_import_ou_rapatriement_les_controles_et_la_publication_passent(depot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """L'étape obligatoire avant publication ne rend aucun contrôle rouge (revue TEST-01) ; publication en local."""
    racine, chemin, rapport = depot
    assert rapport.erreurs == [] and rapport.bascule, rapport.erreurs
    m = visuels.charger(chemin)
    pages = sorted(racine.glob("*.html")) + sorted((racine.parent / "maquettes").glob("*.html"))
    assert visuels.verifier(m, pages, racine) == []
    assert visuels.erreurs_publication(m, racine) == []
    assert vs.verifier_landing(racine) == []
    for maquette in sorted((racine.parent / "maquettes").glob("*.html")):
        assert vs.verifier_maquette(maquette) == [], maquette.name
    index = (racine / "index.html").read_text(encoding="utf-8")
    assert fictifs.BASE_DISTANTE_FICTIVE not in index
    assert not [u for u in re.findall(r'\b(?:src|srcset|imagesrcset)="([^"]*)"', index) if "://" in u]
    assert not [b for b in re.findall(r'(?:srcset|imagesrcset)="([^"]*)"', index) if ".png" in b]
    sortie = tmp_path / "pub"
    rapport_pub = publication.construire("publication", sortie, champs=fictifs.champs_fictifs(), source=racine, visuels_manifeste=m)
    assert vs.verifier_landing(sortie, publication_mode=True) == []
    publies = [f for f in rapport_pub.fichiers if f.startswith("assets/visuels/")]
    assert publies and all(f.endswith(".webp") for f in publies)
    assert not [f for f in rapport_pub.fichiers if f.endswith(".png") and f.startswith("assets/visuels")]
    for f in publies:
        largeur = int(f.rsplit("-", 1)[1].removesuffix(".webp"))
        assert (sortie / f).stat().st_size <= visuels.plafond_octets(largeur), f
