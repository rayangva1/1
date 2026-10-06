"""Visuels de la marque : manifeste unique, synchronisation des pages, rapatriement en local (sans réseau)."""

from __future__ import annotations

import copy
import json
import shutil
import struct
from pathlib import Path

import pytest
import rapatrier_visuels as rv
import verifier_site as vs
import visuels

REPO = Path(__file__).resolve().parents[2]
LANDING = REPO / "site" / "landing"


# ----------------------------------------------------------------------------- octets factices (en-têtes réels)
def png(largeur: int, hauteur: int) -> bytes:
    """En-tête PNG minimal (signature + IHDR) aux dimensions données."""
    ihdr = struct.pack(">II", largeur, hauteur) + b"\x08\x06\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00" + b"\x00" * 16


def webp_vp8x(largeur: int, hauteur: int) -> bytes:
    """En-tête WebP étendu (VP8X) aux dimensions données."""
    corps = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (largeur - 1).to_bytes(3, "little") + (hauteur - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(corps)) + b"WEBP" + corps + b"\x00" * 8


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
def test_manifeste_unique_et_valide() -> None:
    m = visuels.charger()
    assert visuels.valider(m) == []
    assert len(m["visuels"]) == 12 and m["source"] == "distant"
    assert m["base_distante"].startswith("https://") and m["base_distante"].endswith("/")
    utilises = set()
    for page in visuels.pages():
        utilises |= visuels.identifiants_utilises(page.read_text(encoding="utf-8"))
    assert utilises == set(m["visuels"]), set(m["visuels"]) ^ utilises


@pytest.mark.parametrize(
    ("chemin", "valeur", "attendu"),
    [
        (("source",), "cdn", "source invalide"),
        (("base_distante",), "http://exemple.invalid/", "base_distante"),
        (("dossier_local",), "../ailleurs/", "dossier_local"),
        (("visuels", "autocollant-lumi", "fichier"), "../../etc/passwd", "nom de fichier invalide"),
        (("visuels", "autocollant-lumi", "largeur"), 0, "largeur entière"),
        (("visuels", "autocollant-lumi", "largeur_min"), "1024", "largeur_min entière"),
    ],
)
def test_manifeste_invalide_refuse(chemin: tuple[str, ...], valeur: object, attendu: str) -> None:
    m = copy.deepcopy(visuels.charger())
    cible = m
    for cle in chemin[:-1]:
        cible = cible[cle]
    cible[chemin[-1]] = valeur
    assert any(attendu in e for e in visuels.valider(m))


def test_attributs_distants_puis_locaux() -> None:
    m = copy.deepcopy(visuels.charger())
    page = LANDING / "index.html"
    a = visuels.attributs(m, "heros-nuit-etoilee", "img", page)
    base = m["base_distante"] + m["visuels"]["heros-nuit-etoilee"]["fichier"]
    assert a == {"src": base + "_min.webp", "srcset": f"{base}_min.webp 1344w, {base}.png 2688w", "width": "2688", "height": "1152"}
    m["source"] = "local"
    m["visuels"]["heros-nuit-etoilee"]["largeur_min"] = 1600
    a = visuels.attributs(m, "heros-nuit-etoilee", "img", page)
    nom = m["visuels"]["heros-nuit-etoilee"]["fichier"]
    assert a["src"] == f"assets/visuels/{nom}_min.webp" and a["srcset"].startswith(f"assets/visuels/{nom}_min.webp 1600w, ")
    maquette = REPO / "site" / "maquettes" / "drop.html"
    assert visuels.url(m, "heros-nuit-etoilee", "hd", maquette) == f"../landing/assets/visuels/{nom}.png"
    assert set(visuels.attributs(m, "heros-nuit-etoilee", "link", page)) == {"href", "imagesrcset"}


def test_pages_synchronisees_et_desynchronisation_detectee(tmp_path: Path) -> None:
    assert visuels.verifier() == []
    page = tmp_path / "index.html"
    texte = (LANDING / "index.html").read_text(encoding="utf-8")
    m = visuels.charger()
    assert visuels.appliquer_texte(texte, m, LANDING / "index.html") == texte  # idempotent
    page.write_text(texte.replace("2688w", "9999w", 1), encoding="utf-8")
    assert any("désynchronisées" in e for e in visuels.verifier(m, [page]))
    page.write_text(texte.replace('data-visuel="quai-nuit"', 'data-visuel="inconnu"'), encoding="utf-8")
    assert any("visuel inconnu" in e for e in visuels.verifier(m, [page]))
    page.write_text(texte + f'<!-- {m["base_distante"]}x.png -->', encoding="utf-8")
    assert any("hors d'une balise data-visuel" in e for e in visuels.verifier(m, [page]))


def test_reecriture_conserve_les_attributs_de_contexte(tmp_path: Path) -> None:
    m = visuels.charger()
    page = tmp_path / "p.html"
    html = '<img alt="Lumi" sizes="50vw" loading="lazy" data-visuel="autocollant-lumi" src="ancien.png">'
    sortie = visuels.appliquer_texte(html, m, page)
    assert sortie.startswith('<img alt="Lumi" sizes="50vw" loading="lazy" data-visuel="autocollant-lumi" src="https://')
    assert 'width="2048" height="2048"' in sortie and "ancien.png" not in sortie
    assert visuels.appliquer_texte(sortie, m, page) == sortie


def test_verificateur_site_admet_le_distant_en_apercu_seulement(tmp_path: Path) -> None:
    dossier = tmp_path / "lp"
    shutil.copytree(LANDING, dossier)
    index = dossier / "index.html"
    texte = index.read_text(encoding="utf-8")
    assert vs.verifier_page(index, dossier) == []
    assert any("visuel distant dans un dossier de publication" in e for e in vs.verifier_page(index, dossier, publication_mode=True))
    index.write_text(texte.replace(visuels.charger()["base_distante"], "https://images.exemple.invalid/", 1), encoding="utf-8")
    assert any("hôte hors de site/config/visuels.json" in e for e in vs.verifier_page(index, dossier))


# ----------------------------------------------------------------------------- formats d'image
@pytest.mark.parametrize(
    ("octets", "attendu"),
    [(png(2688, 1152), ("png", 2688, 1152)), (webp_vp8x(1344, 576), ("webp", 1344, 576)),
     (webp_vp8(800, 343), ("webp", 800, 343)), (webp_vp8l(1024, 439), ("webp", 1024, 439))],
)
def test_dimensions_lues_dans_les_en_tetes(octets: bytes, attendu: tuple[str, int, int]) -> None:
    assert rv.dimensions(octets) == attendu


def test_controles_des_fichiers_telecharges() -> None:
    v = {"largeur": 2688, "hauteur": 1152}
    assert rv.controler(png(2688, 1152), "hd", v) == (2688, 1152)
    assert rv.controler(webp_vp8x(1344, 576), "min", v) == (1344, 576)
    for octets, variante, motif in (
        (b"<html>erreur</html>", "hd", "format non reconnu"),
        (webp_vp8x(1344, 576), "hd", "png attendu"),
        (png(2000, 1152), "hd", "dimensions"),
        (webp_vp8x(1000, 1000), "min", "proportions"),
        (webp_vp8x(4000, 1715), "min", "plus grande"),
        (b"", "min", "vide"),
    ):
        with pytest.raises(rv.RapatriementError, match=motif):
            rv.controler(octets, variante, v)


# ----------------------------------------------------------------------------- rapatriement (réseau simulé)
def _environnement(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    manifeste = tmp_path / "visuels.json"
    shutil.copyfile(visuels.CONFIG, manifeste)
    racine = tmp_path / "landing"
    racine.mkdir()
    page = racine / "index.html"
    shutil.copyfile(LANDING / "index.html", page)
    return manifeste, racine, [page]


def _faux_reseau(m: dict, echec: str | None = None) -> tuple[list[str], object]:
    appels: list[str] = []

    def telecharge(url: str) -> bytes:
        appels.append(url)
        for ident, v in m["visuels"].items():
            if url == visuels.url_distante(m, ident, "hd"):
                return png(v["largeur"], v["hauteur"])
            if url == visuels.url_distante(m, ident, "min"):
                if ident == echec:
                    raise OSError("connexion refusée")
                return webp_vp8x(v["largeur"] // 2, v["hauteur"] // 2)
        raise AssertionError(url)

    return appels, telecharge


def test_rapatriement_bascule_en_local(tmp_path: Path) -> None:
    manifeste, racine, pages = _environnement(tmp_path)
    m = visuels.charger(manifeste)
    appels, telecharge = _faux_reseau(m)
    rapport = rv.rapatrier(manifeste, racine, telecharge=telecharge, pages=pages)
    assert rapport.erreurs == [] and rapport.bascule and len(rapport.telecharges) == 24 and len(appels) == 24
    apres = json.loads(manifeste.read_text(encoding="utf-8"))
    assert apres["source"] == "local"
    assert apres["visuels"]["heros-nuit-etoilee"]["largeur_min"] == 1344
    index = pages[0].read_text(encoding="utf-8")
    assert m["base_distante"] not in index
    nom = m["visuels"]["heros-nuit-etoilee"]["fichier"]
    assert f'srcset="assets/visuels/{nom}_min.webp 1344w, assets/visuels/{nom}.png 2688w"' in index
    assert visuels.erreurs_publication(apres, racine) == []
    assert rv.verifier_locaux(manifeste, racine) == []
    # Relance : rien n'est retéléchargé
    appels2, telecharge2 = _faux_reseau(m)
    rapport2 = rv.rapatrier(manifeste, racine, telecharge=telecharge2, pages=pages)
    assert appels2 == [] and len(rapport2.deja_presents) == 24
    # Retour à l'aperçu distant : fichiers gardés, publication de nouveau refusée
    rv.revenir_distant(manifeste, pages, racine)
    assert m["base_distante"] in pages[0].read_text(encoding="utf-8")
    assert visuels.erreurs_publication(visuels.charger(manifeste), racine)


def test_rapatriement_ferme_par_defaut_si_un_fichier_manque(tmp_path: Path) -> None:
    manifeste, racine, pages = _environnement(tmp_path)
    avant = manifeste.read_text(encoding="utf-8")
    index_avant = pages[0].read_text(encoding="utf-8")
    m = visuels.charger(manifeste)
    _, telecharge = _faux_reseau(m, echec="cover-leman")
    rapport = rv.rapatrier(manifeste, racine, telecharge=telecharge, pages=pages)
    assert not rapport.bascule and any("cover-leman" in e for e in rapport.erreurs)
    assert manifeste.read_text(encoding="utf-8") == avant
    assert pages[0].read_text(encoding="utf-8") == index_avant
    assert not list((racine / "assets" / "visuels").glob(".telechargement-*"))


def test_fichier_local_corrompu_retelecharge_refuse(tmp_path: Path) -> None:
    manifeste, racine, pages = _environnement(tmp_path)
    m = visuels.charger(manifeste)
    cible = visuels.chemin_local(m, "autocollant-lumi", "hd", racine)
    cible.parent.mkdir(parents=True)
    cible.write_bytes(b"<html>page d'erreur</html>")
    _, telecharge = _faux_reseau(m)
    rapport = rv.rapatrier(manifeste, racine, telecharge=telecharge, pages=pages)
    assert not rapport.bascule and any("autocollant-lumi (hd)" in e for e in rapport.erreurs)
    assert rv.rapatrier(manifeste, racine, telecharge=telecharge, pages=pages, forcer=True).bascule


def test_telechargement_https_uniquement() -> None:
    with pytest.raises(rv.RapatriementError):
        rv.telecharger("http://exemple.invalid/x.png")
