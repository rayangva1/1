"""Visuels de la marque : manifeste unique, synchronisation des pages, rapatriement en local (sans réseau).

Aucun test ne lit l'état courant (``source``) du manifeste du dépôt : chaque test se construit son manifeste et ses
copies de pages (``fictifs.manifeste``), en source distante ET locale. La suite reste donc verte avant comme après
l'étape obligatoire ``rapatrier_visuels.py`` (revue TEST-01).
"""

from __future__ import annotations

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
from fictifs import LANDING, MAQUETTES, png_entete, webp_vp8x


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
def test_manifeste_unique_valide_et_complet() -> None:
    m = visuels.charger()
    assert visuels.valider(m) == []
    assert len(m["visuels"]) == 12
    assert m["base_distante"].startswith("https://") and m["base_distante"].endswith("/")
    utilises: set[str] = set()
    for page in visuels.pages():
        utilises |= visuels.identifiants_utilises(page.read_text(encoding="utf-8"))
    assert utilises == set(m["visuels"]), set(m["visuels"]) ^ utilises
    for ident, v in m["visuels"].items():
        assert v["largeurs"][-1] <= v["largeur"], ident


@pytest.mark.parametrize(
    ("chemin", "valeur", "attendu"),
    [
        (("source",), "cdn", "source invalide"),
        (("base_distante",), "http://exemple.invalid/", "base_distante"),
        (("dossier_local",), "../ailleurs/", "dossier_local"),
        (("visuels", "autocollant-lumi", "fichier"), "../../etc/passwd", "nom de fichier invalide"),
        (("visuels", "autocollant-lumi", "largeur"), 0, "largeur entière"),
        (("visuels", "autocollant-lumi", "largeurs"), [512, 256], "largeurs"),
        (("visuels", "autocollant-lumi", "largeurs"), [256, 4096], "largeurs"),
        (("visuels", "autocollant-lumi", "variantes"), [300], "variantes"),
        (("visuels", "autocollant-lumi", "variantes"), "256", "variantes"),
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


@pytest.mark.parametrize("source", ["distant", "local"])
def test_attributs_sans_png_et_largeurs_exactes(source: str) -> None:
    m = fictifs.manifeste(source)
    page = LANDING / "index.html"
    nom = m["visuels"]["heros-nuit-etoilee"]["fichier"]
    a = visuels.attributs(m, "heros-nuit-etoilee", "img", page)
    assert (a["width"], a["height"]) == ("2688", "1152")
    assert ".png" not in a["srcset"] and ".png" not in a["src"]
    if source == "distant":
        # Aperçu : la variante légère seule (la PNG HD serait choisie par presque tous les écrans).
        assert a["src"] == a["srcset"] == f"{m['base_distante']}{nom}_min.webp"
    else:
        assert a["srcset"] == ", ".join(f"assets/visuels/{nom}-{w}.webp {w}w" for w in (640, 960, 1280, 1920, 2688))
        assert a["src"] == f"assets/visuels/{nom}-1280.webp"
        maquette = MAQUETTES / "drop.html"
        assert visuels.src(m, "heros-nuit-etoilee", maquette) == f"../landing/assets/visuels/{nom}-1280.webp"
        assert visuels.src(m, "autocollant-lumi", page).endswith("-768.webp")
    assert set(visuels.attributs(m, "heros-nuit-etoilee", "link", page)) == {"href", "imagesrcset"}
    assert set(visuels.attributs(m, "heros-nuit-etoilee", "source", page)) == {"srcset", "width", "height"}


def test_pages_synchronisees_et_desynchronisation_detectee(tmp_path: Path) -> None:
    assert visuels.verifier() == []  # quel que soit l'état (aperçu distant ou visuels rapatriés)
    dossier, m = fictifs.landing_aux_visuels(tmp_path, "distant")
    page = dossier / "index.html"
    texte = page.read_text(encoding="utf-8")
    assert visuels.verifier(m, [page], dossier) == []
    assert visuels.appliquer_texte(texte, m, page, racine=dossier) == texte  # idempotent
    page.write_text(texte.replace('width="2688"', 'width="9999"', 1), encoding="utf-8")
    assert any("désynchronisées" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte.replace('data-visuel="quai-nuit"', 'data-visuel="inconnu"'), encoding="utf-8")
    assert any("visuel inconnu" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte + f'<!-- {m["base_distante"]}x.png -->', encoding="utf-8")
    assert any("hors d'une balise data-visuel" in e for e in visuels.verifier(m, [page], dossier))
    page.write_text(texte.replace('<img class="nt-visuel__img"', '<img srcset="x.png 2688w" class="nt-visuel__img"', 1), encoding="utf-8")
    assert any("PNG dans un srcset" in e for e in visuels.verifier(m, [page], dossier))


@pytest.mark.parametrize("source", ["distant", "local"])
def test_reecriture_conserve_les_attributs_de_contexte(tmp_path: Path, source: str) -> None:
    m = fictifs.manifeste(source)
    page = tmp_path / "p.html"
    html = '<img alt="Lumi" sizes="50vw" loading="lazy" data-visuel="autocollant-lumi" src="ancien.png">'
    sortie = visuels.appliquer_texte(html, m, page, racine=tmp_path)
    debut = "https://" if source == "distant" else "assets/visuels/"
    assert sortie.startswith(f'<img alt="Lumi" sizes="50vw" loading="lazy" data-visuel="autocollant-lumi" src="{debut}')
    assert 'width="2048" height="2048"' in sortie and "ancien.png" not in sortie
    assert visuels.appliquer_texte(sortie, m, page, racine=tmp_path) == sortie


def test_verificateur_site_admet_le_distant_en_apercu_seulement(tmp_path: Path) -> None:
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
    visuels.chemin_variante(m, "quai-nuit", 640, dossier).unlink()
    assert any("visuel introuvable" in e for e in vs.verifier_page(index, dossier))


# ----------------------------------------------------------------------------- formats et contrôles
@pytest.mark.parametrize(
    ("octets", "attendu"),
    [(png_entete(2688, 1152), ("png", 2688, 1152)), (webp_vp8x(1344, 576), ("webp", 1344, 576)),
     (webp_vp8(800, 343), ("webp", 800, 343)), (webp_vp8l(1024, 439), ("webp", 1024, 439))],
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
    for octets, motif in (
        (png_entete(1280, 549), "webp attendu"),
        (webp_vp8x(1280, 600), "dimensions"),
        (webp_vp8x(1280, 549) + b"\x00" * (visuels.plafond_octets(1280) + 1), "budget"),
    ):
        with pytest.raises(rv.RapatriementError, match=motif):
            rv.controler_variante(octets, 1280, v)


def test_budgets_de_poids() -> None:
    assert visuels.plafond_octets(1520) == 250 * 1024  # mobile (couverture 9:16, 390 px en DPR 3 ou 4)
    assert visuels.plafond_octets(1920) == visuels.plafond_octets(2688) == 450 * 1024  # ordinateur


# ----------------------------------------------------------------------------- rapatriement (réseau simulé)
def _petit_manifeste(tmp_path: Path) -> tuple[Path, Path, list[Path], dict]:
    """Deux visuels de petite taille (tests rapides) et une page qui les porte."""
    pytest.importorskip("PIL")
    m = fictifs.manifeste("distant")
    m["visuels"] = {
        "banniere": {**m["visuels"]["heros-nuit-etoilee"], "largeur": 420, "hauteur": 180, "largeurs": [160, 320, 420]},
        "portrait": {**m["visuels"]["cover-leman"], "largeur": 190, "hauteur": 336, "largeurs": [120, 190]},
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


# ----------------------------------------------------------------------------- régression : après le rapatriement
@pytest.fixture(scope="module")
def depot(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    pytest.importorskip("PIL")
    return fictifs.depot_rapatrie(tmp_path_factory.mktemp("depot"))


def test_apres_rapatriement_les_controles_et_la_publication_passent(depot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """L'étape obligatoire avant publication ne rend aucun contrôle rouge (revue TEST-01)."""
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
    assert m["base_distante"] not in index
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
