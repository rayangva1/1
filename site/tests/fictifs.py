"""Données FICTIVES pour les tests du site : fichiers image factices, champs validés, dépôts aux visuels importés.

Rien ici n'est publié : valeurs « exemple.invalid », images d'aplat (jamais les vrais visuels, trop lourds),
réseau simulé. Le manifeste du dépôt est en source locale sans adresse distante : les tests de l'aperçu distant
posent une base FICTIVE (``BASE_DISTANTE_FICTIVE``).
"""

from __future__ import annotations

import copy
import dataclasses
import io
import json
import shutil
import struct
from pathlib import Path

import publication
import registre_champs as rc
import visuels

REPO = Path(__file__).resolve().parents[2]
LANDING = REPO / "site" / "landing"
MAQUETTES = REPO / "site" / "maquettes"
WEBHOOK_FICTIF = "https://n8n.exemple.invalid/webhook/alertes-inscription"
URL_FICTIVE = "https://landing.exemple.invalid/"
BASE_DISTANTE_FICTIVE = "https://visuels.exemple.invalid/marque/"
HOTE_DISTANT_FICTIF = "visuels.exemple.invalid"


# ----------------------------------------------------------------------------- en-têtes et images
def png_entete(largeur: int, hauteur: int) -> bytes:
    """En-tête PNG minimal (signature + IHDR) aux dimensions données (non décodable : contrôles d'en-tête)."""
    ihdr = struct.pack(">II", largeur, hauteur) + b"\x08\x06\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00" + b"\x00" * 16


def webp_vp8x(largeur: int, hauteur: int) -> bytes:
    """En-tête WebP étendu (VP8X) aux dimensions données."""
    corps = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (largeur - 1).to_bytes(3, "little") + (hauteur - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(corps)) + b"WEBP" + corps + b"\x00" * 8


def jpeg_entete(largeur: int, hauteur: int, sof: int = 0xC0) -> bytes:
    """En-tête JPEG minimal (SOI, APP0, SOF0 ou SOF2 progressif) aux dimensions données (non décodable)."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof_ = b"\xff" + bytes([sof]) + struct.pack(">HBHHB", 17, 8, hauteur, largeur, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + sof_ + b"\xff\xd9"


def png_reelle(largeur: int, hauteur: int, couleur: tuple[int, int, int] = (20, 30, 90)) -> bytes:
    """PNG décodable (Pillow requis) : un aplat de couleur aux dimensions données."""
    return image_reelle(largeur, hauteur, "PNG", couleur)


def image_reelle(largeur: int, hauteur: int, fmt: str, couleur: tuple[int, int, int] = (239, 234, 225), **options) -> bytes:  # type: ignore[no-untyped-def]
    """Image décodable (Pillow requis) au format demandé (JPEG, PNG, WEBP) : un aplat avec un trait orange."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (largeur, hauteur), couleur)
    ImageDraw.Draw(image).line([(0, int(hauteur * 0.9)), (largeur, hauteur - 1)], fill=(242, 106, 27), width=max(1, hauteur // 60))
    tampon = io.BytesIO()
    if fmt == "PNG":
        options.setdefault("compress_level", 1)
    image.save(tampon, format=fmt, **options)
    return tampon.getvalue()


# ----------------------------------------------------------------------------- manifestes
def manifeste(source: str = "distant", base: dict | None = None) -> dict:
    """Copie du manifeste du dépôt posée sur une source donnée (jamais l'état courant du dépôt).

    Source distante : base FICTIVE (le manifeste du dépôt n'a aucune adresse distante). Source locale : toutes les
    largeurs comme variantes. ``"a-importer"`` : source locale dont aucune variante n'est encore produite.
    """
    m = copy.deepcopy(base if base is not None else json.loads(visuels.CONFIG.read_text(encoding="utf-8")))
    m["source"] = "local" if source == "a-importer" else source
    if source == "distant":
        m["base_distante"] = BASE_DISTANTE_FICTIVE
    for v in m["visuels"].values():
        v["variantes"] = list(v["largeurs"]) if source == "local" else None
        if source != "local":
            v["empreinte_source"] = None
    return m


def ecrire_variantes_factices(m: dict, racine: Path) -> None:
    """Écrit, pour un manifeste local, chaque variante sous forme d'en-tête WebP aux bonnes dimensions."""
    for ident, v in m["visuels"].items():
        for largeur in v["variantes"] or []:
            cible = visuels.chemin_variante(m, ident, largeur, racine)
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(webp_vp8x(largeur, visuels.hauteur_variante(v, largeur)))


def landing_aux_visuels(tmp_path: Path, source: str, nom: str = "lp") -> tuple[Path, dict]:
    """Copie de la landing dont les balises data-visuel suivent un manifeste FICTIF de la source demandée."""
    dossier = tmp_path / nom
    shutil.copytree(LANDING, dossier)
    m = manifeste(source)
    if source == "local":
        ecrire_variantes_factices(m, dossier)
    visuels.appliquer(m, sorted(dossier.glob("*.html")), racine=dossier)
    return dossier, m


# ----------------------------------------------------------------------------- champs de publication
def champs_fictifs(nom: str = publication.NOM_DE_TRAVAIL) -> dict[str, rc.Field]:
    """Tous les champs validés avec des valeurs FICTIVES (jamais publiées)."""
    champs = publication.charger_champs()
    valeurs = {
        "NOM_BOUTIQUE": nom,
        "WEBHOOK_INSCRIPTION": WEBHOOK_FICTIF,
        "URL_LANDING": URL_FICTIVE,
        "EMAIL_SUPPORT": "contact@exemple.invalid",
        "EMAIL_DONNEES": "donnees@exemple.invalid",
        "MOIS_OUVERTURE": "novembre 2026",
        "URL_COOKIES": URL_FICTIVE + "cookies",
        "ST_POLICES": "Google Fonts (Google)",
    }
    sortie = {}
    for cle, f in champs.items():
        if f.alias_of:
            sortie[cle] = f
            continue
        sortie[cle] = dataclasses.replace(f, status=rc.Status.VALIDE, value=valeurs.get(cle, f"FICTIF {cle.lower()}"), validated_by="test")
    return sortie


# ----------------------------------------------------------------------------- rapatriement simulé
def reseau_simule(m: dict, echec: str | None = None):  # type: ignore[no-untyped-def]
    """Téléchargeur sans réseau : PNG d'aplat aux dimensions du manifeste ; ``echec`` simule une coupure."""
    appels: list[str] = []
    cache: dict[tuple[int, int], bytes] = {}

    def telecharge(url: str) -> bytes:
        appels.append(url)
        for ident, v in m["visuels"].items():
            if url == visuels.url_distante(m, ident, "hd"):
                if ident == echec:
                    raise OSError("connexion refusée")
                cle = (v["largeur"], v["hauteur"])
                if cle not in cache:
                    cache[cle] = png_reelle(*cle)
                return cache[cle]
        raise AssertionError(f"adresse inattendue : {url}")

    return appels, telecharge


def sources_fictives(m: dict, dossier: Path) -> dict[str, Path]:
    """Écrit, pour chaque visuel, un fichier source FICTIF (aplat) au format de son ``fichier_source``, à ses dimensions."""
    dossier.mkdir(parents=True, exist_ok=True)
    formats = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    cache: dict[tuple[int, int, str], bytes] = {}
    ecrits = {}
    for ident, v in m["visuels"].items():
        nom = v.get("fichier_source") or f"{ident}.jpg"
        fmt = formats[Path(nom).suffix.lower()]
        cle = (v["largeur"], v["hauteur"], fmt)
        if cle not in cache:
            options = {} if fmt == "PNG" else {"quality": 80}
            cache[cle] = image_reelle(v["largeur"], v["hauteur"], fmt, **options)
        (dossier / nom).write_bytes(cache[cle])
        ecrits[ident] = dossier / nom
    return ecrits


def depot_importe(tmp: Path):  # type: ignore[no-untyped-def]
    """Copie site/landing, site/maquettes et le manifeste « à importer », puis import local de sources FICTIVES.

    Retourne (racine de la landing copiée, chemin du manifeste copié, rapport de l'import). Aucun vrai visuel lu.
    """
    import rapatrier_visuels as rv

    site = tmp / "site"
    shutil.copytree(LANDING, site / "landing", ignore=shutil.ignore_patterns("visuels"))
    shutil.copytree(MAQUETTES, site / "maquettes")
    (site / "config").mkdir()
    chemin = site / "config" / "visuels.json"
    m = manifeste("a-importer")
    chemin.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sources_fictives(m, tmp / "sources")
    racine = site / "landing"
    pages = sorted(racine.glob("*.html")) + sorted((site / "maquettes").glob("*.html"))
    rapport = rv.importer(tmp / "sources", chemin, racine, archive=tmp / "archive", pages=pages)
    return racine, chemin, rapport


def depot_rapatrie(tmp: Path):  # type: ignore[no-untyped-def]
    """Copie site/landing, site/maquettes et le manifeste, puis rapatriement simulé (vraies variantes WebP).

    Retourne (racine de la landing copiée, chemin du manifeste copié, rapport du rapatriement).
    """
    import rapatrier_visuels as rv

    site = tmp / "site"
    shutil.copytree(LANDING, site / "landing", ignore=shutil.ignore_patterns("visuels"))
    shutil.copytree(MAQUETTES, site / "maquettes")
    (site / "config").mkdir()
    chemin = site / "config" / "visuels.json"
    chemin.write_text(json.dumps(manifeste("distant"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    racine = site / "landing"
    visuels.appliquer(visuels.charger(chemin), sorted(racine.glob("*.html")) + sorted((site / "maquettes").glob("*.html")), racine=racine)
    _, telecharge = reseau_simule(visuels.charger(chemin))
    pages = sorted(racine.glob("*.html")) + sorted((site / "maquettes").glob("*.html"))
    rapport = rv.rapatrier(chemin, racine, archive=tmp / "archive", telecharge=telecharge, pages=pages)
    return racine, chemin, rapport
