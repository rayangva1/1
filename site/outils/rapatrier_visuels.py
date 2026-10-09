#!/usr/bin/env python3
"""Importe (ou rapatrie) les visuels de la marque, produit leurs variantes WebP et bascule les pages vers ces fichiers.

La page publiée ne charge aucune image d'un tiers (politique de sécurité ``img-src 'self'``, aucune adresse IP de
visiteur transmise) : ``publication.py`` refuse de publier tant que la source des visuels n'est pas ``local``.

**Import local** (``--importer <dossier>``, aucun réseau) : chaque visuel du manifeste ``site/config/visuels.json``
est cherché dans le dossier sous son ``fichier_source`` (sinon ``<clé>.jpg|.jpeg|.png|.webp``). Contrôles, avant
d'écrire quoi que ce soit : format réel lu dans l'en-tête (JPEG, PNG ou WebP, quelle que soit l'extension), taille
maximale, **proportions** conformes au ``format`` déclaré (« 21:9 », tolérance ``visuels.TOLERANCE_FORMAT``),
largeur suffisante pour la plus grande variante. Puis, pour chaque visuel : orientation EXIF appliquée, profil de
couleur converti en sRGB, variantes WebP aux largeurs ``largeurs`` dans le budget de poids (sans aucune
métadonnée : ni EXIF, ni GPS, ni XMP), fichier d'origine archivé tel quel dans ``site/visuels-sources/`` (hors du
dossier publié, ignoré par git), manifeste rempli (dimensions, ``variantes``, ``fichier_source``,
``empreinte_source`` SHA-256), source « local », pages réécrites. Fermé par défaut : si un seul fichier manque ou
est refusé, rien ne change (ni variantes, ni archive, ni manifeste, ni pages).

**Rapatriement** (sans option, seulement si ``base_distante`` est renseignée) : sur une machine dont le réseau atteint
l'adresse distante des visuels. Étapes, pour chaque visuel du manifeste :

1. **Archive** : la PNG haute définition d'origine (``<fichier>.png``) est téléchargée dans ``site/visuels-sources/``
   (hors du dossier publié, ignoré par git). Contrôles : signature PNG réelle, taille maximale, dimensions identiques
   au manifeste.
2. **Variantes** : une WebP par largeur de ``largeurs`` (``<fichier>-<largeur>.webp``, mêmes proportions) dans
   ``site/landing/assets/visuels/``, qualité 82 puis abaissée par paliers (jusqu'à 52) pour tenir le budget de poids
   (``visuels.plafond_octets`` : 250 Ko jusqu'à 1600 px, 450 Ko au-delà). Une variante qui ne tient pas son budget à
   la qualité 52 est écartée (signalée) ; la plus petite est toujours gardée. Les ``srcset`` des pages ne listent
   que ces variantes, avec leur largeur exacte : jamais la PNG.
3. **Bascule** : ``source`` passe à ``local``, ``variantes`` liste les largeurs produites, les pages sont réécrites.

Fermé par défaut : si un seul fichier manque ou est refusé, le manifeste et les pages ne changent pas (les PNG
valides déjà téléchargées restent dans l'archive pour la prochaine tentative). Nécessite Pillow (``pip install
Pillow``) pour produire les variantes.

Usage :
    python site/outils/rapatrier_visuels.py --importer <dossier>               # import local de tous les visuels
    python site/outils/rapatrier_visuels.py --importer <dossier> --seulement renard-heros,photo-classeur
    python site/outils/rapatrier_visuels.py --verifier   # contrôle les variantes locales (et l'archive si présente)
    python site/outils/rapatrier_visuels.py              # rapatrie depuis base_distante (si renseignée)
    python site/outils/rapatrier_visuels.py --forcer     # retélécharge les PNG d'origine
    python site/outils/rapatrier_visuels.py --distant    # revient aux adresses distantes (aperçu), fichiers gardés
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

OUTILS = Path(__file__).resolve().parent
sys.path.insert(0, str(OUTILS))

import visuels  # noqa: E402

ARCHIVE = visuels.REPO / "site" / "visuels-sources"
TAILLE_MAX = 40 * 1024 * 1024
DELAI_S = 60
#: Paliers de qualité WebP : on commence haut (photographie « quiet luxury », dégradés de papier sans bandes), puis on
#: descend seulement si le budget de poids l'exige.
QUALITES = (82, 76, 70, 64, 58, 52)
#: Extensions acceptées pour un fichier source local et extension d'archive selon le format réel.
EXTENSIONS_SOURCE = (".jpg", ".jpeg", ".png", ".webp")
EXTENSION_ARCHIVE = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
#: Blocs RIFF de métadonnées qu'une variante publiée ne doit jamais contenir.
BLOCS_METADONNEES = (b"EXIF", b"XMP ", b"ICCP")


class RapatriementError(RuntimeError):
    """Fichier refusé (format, taille ou dimensions)."""


@dataclass
class Rapport:
    """Résultat d'un rapatriement."""

    telecharges: list[str] = field(default_factory=list)
    deja_presents: list[str] = field(default_factory=list)
    variantes: list[str] = field(default_factory=list)
    ecartees: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    bascule: bool = False
    pages: list[str] = field(default_factory=list)
    importes: list[str] = field(default_factory=list)
    archives: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- formats
def _dimensions_jpeg(octets: bytes) -> tuple[int, int]:
    """Largeur et hauteur d'un JPEG, lues dans le premier segment SOF (sans décoder l'image)."""
    i = 2
    while i + 9 < len(octets):
        if octets[i] != 0xFF:
            raise RapatriementError("JPEG mal formé (marqueur attendu)")
        marqueur = octets[i + 1]
        if marqueur == 0xFF:  # octet de remplissage
            i += 1
            continue
        if marqueur in (0xD8, 0x01) or 0xD0 <= marqueur <= 0xD7:  # marqueurs sans longueur
            i += 2
            continue
        longueur = struct.unpack(">H", octets[i + 2 : i + 4])[0]
        if 0xC0 <= marqueur <= 0xCF and marqueur not in (0xC4, 0xC8, 0xCC):
            hauteur, largeur = struct.unpack(">HH", octets[i + 5 : i + 9])
            return largeur, hauteur
        if marqueur == 0xDA or longueur < 2:
            break
        i += 2 + longueur
    raise RapatriementError("JPEG sans dimensions lisibles")


def dimensions(octets: bytes) -> tuple[str, int, int]:
    """(format, largeur, hauteur) lus dans l'en-tête d'un fichier PNG, WebP ou JPEG ; lève RapatriementError sinon."""
    if octets[:3] == b"\xff\xd8\xff":
        largeur, hauteur = _dimensions_jpeg(octets)
        return "jpeg", largeur, hauteur
    if octets[:8] == b"\x89PNG\r\n\x1a\n" and octets[12:16] == b"IHDR" and len(octets) >= 24:
        largeur, hauteur = struct.unpack(">II", octets[16:24])
        return "png", largeur, hauteur
    if octets[:4] == b"RIFF" and octets[8:12] == b"WEBP" and len(octets) >= 30:
        bloc = octets[12:16]
        if bloc == b"VP8 " and octets[23:26] == b"\x9d\x01\x2a":
            largeur, hauteur = struct.unpack("<HH", octets[26:30])
            return "webp", largeur & 0x3FFF, hauteur & 0x3FFF
        if bloc == b"VP8L" and octets[20] == 0x2F:
            b = int.from_bytes(octets[21:25], "little")
            return "webp", (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if bloc == b"VP8X":
            largeur = int.from_bytes(octets[24:27], "little") + 1
            hauteur = int.from_bytes(octets[27:30], "little") + 1
            return "webp", largeur, hauteur
    raise RapatriementError("format non reconnu (JPEG, PNG ou WebP attendu)")


def controler_source(octets: bytes, attendu: dict) -> tuple[int, int]:
    """Contrôle la PNG d'origine téléchargée ; retourne ses dimensions."""
    if not octets:
        raise RapatriementError("fichier vide")
    if len(octets) > TAILLE_MAX:
        raise RapatriementError(f"fichier trop lourd ({len(octets)} octets > {TAILLE_MAX})")
    fmt, largeur, hauteur = dimensions(octets)
    if fmt != "png":
        raise RapatriementError(f"format {fmt} reçu, png attendu")
    if (largeur, hauteur) != (attendu["largeur"], attendu["hauteur"]):
        raise RapatriementError(f"dimensions {largeur}×{hauteur}, {attendu['largeur']}×{attendu['hauteur']} attendues")
    return largeur, hauteur


def controler_proportions(largeur: int, hauteur: int, v: dict) -> None:
    """Proportions conformes au format déclaré et largeur suffisante pour la plus grande variante."""
    proportion = visuels.ratio_format(v.get("format", ""))
    if proportion is None:
        raise RapatriementError(f"format déclaré invalide {v.get('format')!r}")
    ecart = abs(largeur / hauteur / proportion - 1)
    if ecart > visuels.TOLERANCE_FORMAT:
        raise RapatriementError(f"proportions {largeur}×{hauteur} hors du format {v['format']} (écart {ecart:.1%})")
    if largeur < v["largeurs"][-1]:
        raise RapatriementError(f"largeur {largeur} px insuffisante pour la variante de {v['largeurs'][-1]} px")


#: Orientations EXIF qui font pivoter l'image d'un quart de tour (largeur et hauteur affichées inversées).
ORIENTATIONS_QUART_DE_TOUR = (5, 6, 7, 8)


def orientation_exif(octets: bytes) -> int:
    """Orientation EXIF (1 à 8) d'un fichier image ; 1 si absente ou illisible (Pillow facultatif ici)."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(octets)) as image:
            return int(image.getexif().get(0x0112, 1))
    except Exception:  # noqa: BLE001 - lecture facultative : l'image sera décodée et contrôlée ensuite
        return 1


def controler_import(octets: bytes, v: dict, orientation: int = 1) -> tuple[str, int, int]:
    """Contrôle un fichier source local (format réel, taille, proportions telles qu'affichées) ; (format, l, h)."""
    if not octets:
        raise RapatriementError("fichier vide")
    if len(octets) > TAILLE_MAX:
        raise RapatriementError(f"fichier trop lourd ({len(octets)} octets > {TAILLE_MAX})")
    fmt, largeur, hauteur = dimensions(octets)
    if orientation in ORIENTATIONS_QUART_DE_TOUR:
        largeur, hauteur = hauteur, largeur
    controler_proportions(largeur, hauteur, v)
    return fmt, largeur, hauteur


def blocs_riff(octets: bytes) -> list[bytes]:
    """Identifiants des blocs d'un fichier WebP (RIFF) : VP8, VP8L, VP8X, ALPH, EXIF, XMP, ICCP…"""
    blocs, i = [], 12
    while i + 8 <= len(octets):
        ident, taille = octets[i : i + 4], struct.unpack("<I", octets[i + 4 : i + 8])[0]
        blocs.append(ident)
        i += 8 + taille + (taille & 1)
    return blocs


def controler_variante(octets: bytes, largeur: int, v: dict) -> None:
    """Contrôle une variante produite (format WebP, dimensions, budget de poids, aucune métadonnée)."""
    fmt, l_reel, h_reel = dimensions(octets)
    if fmt != "webp":
        raise RapatriementError(f"variante {largeur} : format {fmt}, webp attendu")
    if (l_reel, h_reel) != (largeur, visuels.hauteur_variante(v, largeur)):
        raise RapatriementError(f"variante {largeur} : dimensions {l_reel}×{h_reel} inattendues")
    if len(octets) > visuels.plafond_octets(largeur):
        raise RapatriementError(f"variante {largeur} : {len(octets) // 1024} Ko > budget {visuels.plafond_octets(largeur) // 1024} Ko")
    meta = [b.decode("ascii", "replace").strip() for b in blocs_riff(octets) if b in BLOCS_METADONNEES]
    if meta:
        raise RapatriementError(f"variante {largeur} : métadonnées {meta} (jamais publiées)")


def telecharger(url: str) -> bytes:
    """Télécharge une adresse https (proxy et certificats du système), taille bornée."""
    if not url.startswith("https://"):
        raise RapatriementError(f"adresse non https : {url}")
    requete = urllib.request.Request(url, headers={"User-Agent": "quai-des-cartes-rapatrier-visuels/2"})
    with urllib.request.urlopen(requete, timeout=DELAI_S) as reponse:  # noqa: S310 (https contrôlé ci-dessus)
        octets = reponse.read(TAILLE_MAX + 1)
    return octets


def _ecrire_atomique(cible: Path, octets: bytes) -> None:
    cible.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(prefix=".telechargement-", dir=cible.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(octets)
        os.chmod(temporaire, 0o644)  # mkstemp crée en 0600 : un fichier publié doit être lisible par le serveur web
        os.replace(temporaire, cible)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise


def _ecrire_manifeste(chemin: Path, m: dict) -> None:
    chemin.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- variantes
def _pillow():  # type: ignore[no-untyped-def]
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise RapatriementError("Pillow absent : pip install Pillow (nécessaire pour produire les variantes WebP)") from exc
    return Image


def encoder_variante(image, largeur: int, v: dict) -> tuple[bytes, int] | None:  # type: ignore[no-untyped-def]
    """WebP de la largeur demandée au meilleur palier de qualité qui tient le budget ; None si aucun ne le tient."""
    Image = _pillow()
    hauteur = visuels.hauteur_variante(v, largeur)
    reduite = image if image.size == (largeur, hauteur) else image.resize((largeur, hauteur), Image.Resampling.LANCZOS)
    plafond = visuels.plafond_octets(largeur)
    for qualite in QUALITES:
        tampon = io.BytesIO()
        reduite.save(tampon, format="WEBP", quality=qualite, method=6)
        octets = tampon.getvalue()
        if len(octets) <= plafond:
            return octets, qualite
    return None


def vers_srgb(image, icc: bytes | None):  # type: ignore[no-untyped-def]
    """Image convertie en sRGB si elle embarque un autre profil de couleur (Display P3, Adobe RGB…)."""
    if not icc:
        return image
    from PIL import ImageCms

    try:
        profil = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if "srgb" in ImageCms.getProfileDescription(profil).lower():
            return image
        mode = "RGBA" if "A" in image.getbands() else "RGB"
        return ImageCms.profileToProfile(image.convert(mode), profil, ImageCms.createProfile("sRGB"), outputMode=mode)
    except (OSError, ImageCms.PyCMSError) as exc:
        raise RapatriementError(f"profil de couleur illisible ({exc})") from exc


def ouvrir_source(source: Path):  # type: ignore[no-untyped-def]
    """Image prête à réduire : orientation EXIF appliquée, sRGB, RGB (RGBA si transparente), sans métadonnées."""
    Image = _pillow()
    from PIL import ImageOps

    with Image.open(source) as brute:
        brute.load()
        icc = brute.info.get("icc_profile")
        image = ImageOps.exif_transpose(brute)
    image = vers_srgb(image, icc)
    transparente = "A" in image.getbands() or "transparency" in image.info
    return image.convert("RGBA" if transparente else "RGB")


def produire_variantes(
    m: dict, ident: str, source: Path, racine: Path, rapport: Rapport, *, image=None, sortie: Path | None = None  # type: ignore[no-untyped-def]
) -> list[int]:
    """Écrit les variantes WebP d'un visuel ; retourne les largeurs gardées (lève RapatriementError si aucune).

    ``image`` : image déjà ouverte (import local) ; ``sortie`` : dossier d'écriture (dossier de préparation de
    l'import local), par défaut le dossier publié de la landing (où les variantes périmées sont retirées).
    """
    v = m["visuels"][ident]
    if image is None:
        Image = _pillow()
        with Image.open(source) as brute:
            brute.load()
            image = brute.convert("RGB")
    gardees: list[int] = []
    for largeur in v["largeurs"]:
        resultat = encoder_variante(image, largeur, v)
        if resultat is None:
            rapport.ecartees.append(f"{ident} {largeur} px : au-delà du budget de {visuels.plafond_octets(largeur) // 1024} Ko même en qualité {QUALITES[-1]}")
            continue
        octets, qualite = resultat
        controler_variante(octets, largeur, v)
        cible = visuels.chemin_variante(m, ident, largeur, racine)
        if sortie is not None:
            cible = sortie / cible.name
        _ecrire_atomique(cible, octets)
        gardees.append(largeur)
        rapport.variantes.append(f"{m['dossier_local']}{cible.name} ({len(octets) // 1024} Ko, qualité {qualite})")
    if not gardees:
        raise RapatriementError("aucune variante dans son budget de poids (réduire « largeurs »)")
    if sortie is not None:
        return gardees
    dossier = racine / m["dossier_local"]
    for perime in dossier.glob(f"{v['fichier']}-*.webp"):
        suffixe = perime.stem[len(v["fichier"]) + 1 :]
        if suffixe.isdigit() and int(suffixe) not in gardees:
            perime.unlink()
    return gardees


# --------------------------------------------------------------------------- actions
def rapatrier(
    chemin_manifeste: Path = visuels.CONFIG,
    racine: Path = visuels.LANDING,
    *,
    archive: Path = ARCHIVE,
    telecharge: Callable[[str], bytes] = telecharger,
    forcer: bool = False,
    pages: list[Path] | None = None,
) -> Rapport:
    """Archive les PNG d'origine, produit les variantes WebP, bascule manifeste et pages en local si tout est valide."""
    m = visuels.charger(chemin_manifeste)
    rapport = Rapport()
    if not m.get("base_distante"):
        rapport.erreurs.append("aucune base_distante dans le manifeste : les visuels s'importent en local "
                               "(python site/outils/rapatrier_visuels.py --importer <dossier>)")
        return rapport
    sources: dict[str, Path] = {}
    for ident, v in m["visuels"].items():
        cible = archive / f"{v['fichier']}.png"
        try:
            if cible.is_file() and not forcer:
                controler_source(cible.read_bytes(), v)
                rapport.deja_presents.append(cible.name)
            else:
                octets = telecharge(visuels.url_distante(m, ident, "hd"))
                controler_source(octets, v)
                _ecrire_atomique(cible, octets)
                rapport.telecharges.append(cible.name)
        except (RapatriementError, OSError, ValueError) as exc:
            rapport.erreurs.append(f"{ident} (png) : {exc}")
            continue
        sources[ident] = cible
    if rapport.erreurs:
        return rapport
    produites: dict[str, list[int]] = {}
    for ident, source in sources.items():
        try:
            produites[ident] = produire_variantes(m, ident, source, racine, rapport)
        except (RapatriementError, OSError, ValueError) as exc:
            rapport.erreurs.append(f"{ident} (variantes) : {exc}")
    if rapport.erreurs:
        return rapport
    for ident, largeurs in produites.items():
        m["visuels"][ident]["variantes"] = largeurs
    m["source"] = "local"
    erreurs = visuels.valider(m)
    if erreurs:
        rapport.erreurs += erreurs
        return rapport
    _ecrire_manifeste(chemin_manifeste, m)
    rapport.bascule = True
    rapport.pages = visuels.appliquer(m, pages, racine)
    return rapport


def verifier_locaux(
    chemin_manifeste: Path = visuels.CONFIG, racine: Path = visuels.LANDING, archive: Path = ARCHIVE
) -> list[str]:
    """Contrôle les variantes locales (format, dimensions, budget, aucune métadonnée) et l'archive si présente."""
    m = visuels.charger(chemin_manifeste)
    if m["source"] != "local":
        return ["source distante : aucune variante locale à contrôler (lancer rapatrier_visuels.py)"]
    erreurs = []
    for ident, v in m["visuels"].items():
        for largeur in v["variantes"]:
            cible = visuels.chemin_variante(m, ident, largeur, racine)
            if not cible.is_file():
                erreurs.append(f"{ident} ({largeur}) : absent")
                continue
            try:
                controler_variante(cible.read_bytes(), largeur, v)
            except RapatriementError as exc:
                erreurs.append(f"{ident} : {exc}")
        empreinte = v.get("empreinte_source")
        if empreinte:
            for archivee in sorted(archive.glob(f"{v['fichier']}.*")):
                if archivee.suffix.lower() in EXTENSIONS_SOURCE and _sha256(archivee.read_bytes()) != empreinte:
                    erreurs.append(f"{ident} : archive {archivee.name} différente du fichier importé (empreinte)")
    return erreurs


def revenir_distant(
    chemin_manifeste: Path = visuels.CONFIG, pages: list[Path] | None = None, racine: Path = visuels.LANDING
) -> list[str]:
    """Repasse le manifeste en source distante (aperçu) et réécrit les pages ; les fichiers locaux restent."""
    m = visuels.charger(chemin_manifeste)
    if not m.get("base_distante"):
        raise RapatriementError("aucune base_distante : les visuels sont uniquement locaux (aucun aperçu distant possible)")
    m["source"] = "distant"
    _ecrire_manifeste(chemin_manifeste, m)
    return visuels.appliquer(m, pages, racine)


# --------------------------------------------------------------------------- import local
def _sha256(octets: bytes) -> str:
    return hashlib.sha256(octets).hexdigest()


def trouver_source(dossier: Path, ident: str, v: dict) -> Path:
    """Fichier source d'un visuel : ``fichier_source`` s'il existe, sinon l'unique ``<clé>.<jpg|jpeg|png|webp>``."""
    nom = v.get("fichier_source")
    if nom and (dossier / nom).is_file():
        return dossier / nom
    candidats = sorted(
        p for p in dossier.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONS_SOURCE and p.stem in {ident, v["fichier"]}
    )
    if len(candidats) == 1:
        return candidats[0]
    if not candidats:
        attendu = nom or f"{ident}.jpg|.jpeg|.png|.webp"
        raise RapatriementError(f"fichier source absent de {dossier} ({attendu})")
    raise RapatriementError(f"plusieurs fichiers sources possibles : {', '.join(p.name for p in candidats)}")


def importer(
    dossier: Path,
    chemin_manifeste: Path = visuels.CONFIG,
    racine: Path = visuels.LANDING,
    *,
    archive: Path = ARCHIVE,
    pages: list[Path] | None = None,
    seulement: list[str] | None = None,
) -> Rapport:
    """Importe des fichiers locaux (JPEG, PNG, WebP) : contrôles, variantes, archive, manifeste local, pages.

    Fermé par défaut : tout est préparé dans un dossier temporaire et rien n'est écrit (variantes, archive,
    manifeste, pages) si un seul fichier manque ou est refusé. ``seulement`` limite l'import à ces visuels ; les
    autres doivent alors déjà avoir leurs variantes locales.
    """
    m = visuels.charger(chemin_manifeste, exiger_variantes=False)
    rapport = Rapport()
    if not dossier.is_dir():
        rapport.erreurs.append(f"dossier d'import introuvable : {dossier}")
        return rapport
    choisis = list(m["visuels"]) if seulement is None else list(seulement)
    for ident in choisis:
        if ident not in m["visuels"]:
            rapport.erreurs.append(f"{ident} : visuel inconnu (absent de site/config/visuels.json)")
    sources: dict[str, tuple[Path, bytes, str]] = {}
    for ident in [i for i in choisis if i in m["visuels"]]:
        v = m["visuels"][ident]
        try:
            chemin = trouver_source(dossier, ident, v)
            octets = chemin.read_bytes()
            fmt, _, _ = controler_import(octets, v, orientation_exif(octets))
        except (RapatriementError, OSError, ValueError) as exc:
            rapport.erreurs.append(f"{ident} (source) : {exc}")
            continue
        sources[ident] = (chemin, octets, fmt)
    for ident, v in m["visuels"].items():
        if ident not in choisis and not v.get("variantes"):
            rapport.erreurs.append(f"{ident} : aucune variante locale (à importer aussi : la source locale exige tous les visuels)")
    if rapport.erreurs:
        return rapport
    dossier_publie = racine / m["dossier_local"]
    produites: dict[str, list[int]] = {}
    # Préparation dans la landing (même système de fichiers : déplacement atomique), retirée en cas de refus.
    with tempfile.TemporaryDirectory(prefix=".import-", dir=racine) as tmp:
        preparation = Path(tmp)
        for ident, (chemin, octets, fmt) in sources.items():
            v = m["visuels"][ident]
            try:
                image = ouvrir_source(chemin)
                largeur, hauteur = image.size
                controler_proportions(largeur, hauteur, v)
                if (largeur, hauteur) != (v["largeur"], v["hauteur"]):
                    rapport.dimensions.append(f"{ident} : {v['largeur']}×{v['hauteur']} → {largeur}×{hauteur}")
                    v["largeur"], v["hauteur"] = largeur, hauteur
                produites[ident] = produire_variantes(m, ident, chemin, racine, rapport, image=image, sortie=preparation)
            except (RapatriementError, OSError, ValueError) as exc:
                rapport.erreurs.append(f"{ident} (variantes) : {exc}")
        if rapport.erreurs:
            return rapport
        for ident, largeurs in produites.items():
            v = m["visuels"][ident]
            chemin, octets, fmt = sources[ident]
            v["variantes"] = largeurs
            v["fichier_source"] = chemin.name
            v["empreinte_source"] = _sha256(octets)
        m["source"] = "local"
        erreurs = visuels.valider(m)
        for page in visuels.pages() if pages is None else pages:
            visuels.appliquer_texte(page.read_text(encoding="utf-8"), m, page, erreurs, racine)
        if erreurs:
            rapport.erreurs += erreurs  # manifeste invalide ou page qui cite un visuel inconnu : rien n'est écrit
            return rapport
        # Tout est valide : publication des variantes, archive des sources, manifeste, pages.
        dossier_publie.mkdir(parents=True, exist_ok=True)
        for ident, largeurs in produites.items():
            v = m["visuels"][ident]
            for largeur in largeurs:
                nom = visuels.nom_variante(m, ident, largeur)
                os.replace(preparation / nom, dossier_publie / nom)
            for perime in dossier_publie.glob(f"{v['fichier']}-*.webp"):
                suffixe = perime.stem[len(v["fichier"]) + 1 :]
                if suffixe.isdigit() and int(suffixe) not in largeurs:
                    perime.unlink()
            chemin, octets, fmt = sources[ident]
            cible = archive / f"{v['fichier']}{EXTENSION_ARCHIVE[fmt]}"
            for ancienne in archive.glob(f"{v['fichier']}.*"):
                if ancienne != cible and ancienne.suffix.lower() in EXTENSIONS_SOURCE:
                    ancienne.unlink()
            _ecrire_atomique(cible, octets)
            rapport.archives.append(cible.name)
            rapport.importes.append(ident)
    _ecrire_manifeste(chemin_manifeste, m)
    rapport.bascule = True
    rapport.pages = visuels.appliquer(m, pages, racine)
    return rapport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--importer", type=Path, metavar="DOSSIER", help="importer des fichiers locaux (JPEG, PNG, WebP), sans réseau")
    groupe.add_argument("--forcer", action="store_true", help="retélécharger les PNG d'origine déjà archivées")
    groupe.add_argument("--verifier", action="store_true", help="contrôler les variantes locales sans réseau")
    groupe.add_argument("--distant", action="store_true", help="revenir aux adresses distantes (aperçu)")
    parser.add_argument("--seulement", default=None, help="avec --importer : clés à importer, séparées par des virgules")
    args = parser.parse_args(argv)
    if args.seulement and not args.importer:
        parser.error("--seulement s'utilise avec --importer")
    if args.importer:
        seulement = [c.strip() for c in args.seulement.split(",") if c.strip()] if args.seulement else None
        rapport = importer(args.importer, seulement=seulement)
        for nom in rapport.variantes:
            print(f"variante : site/landing/{nom}")
        for e in rapport.ecartees:
            print(f"ÉCARTÉE {e}")
        for d in rapport.dimensions:
            print(f"dimensions mises à jour : {d}")
        if rapport.erreurs:
            print(f"REFUS : {len(rapport.erreurs)} problème(s) ; rien n'a été écrit (variantes, archive, manifeste, pages).")
            for e in rapport.erreurs:
                print(f"  - {e}")
            return 1
        print(f"Import local : {len(rapport.importes)} visuel(s), sources archivées dans site/visuels-sources/, "
              f"source « local », {len(rapport.pages)} page(s) réécrite(s).")
        return 0
    if args.verifier:
        erreurs = verifier_locaux()
        for e in erreurs:
            print(f"ERREUR {e}")
        print("Variantes locales conformes." if not erreurs else f"{len(erreurs)} erreur(s).")
        return 1 if erreurs else 0
    if args.distant:
        try:
            pages = revenir_distant()
        except RapatriementError as exc:
            print(f"REFUS : {exc}")
            return 1
        print(f"Source distante (aperçu seulement) : {len(pages)} page(s) réécrite(s). La publication sera refusée.")
        return 0
    rapport = rapatrier(forcer=args.forcer)
    for nom in rapport.telecharges:
        print(f"archivé : site/visuels-sources/{nom}")
    if rapport.deja_presents:
        print(f"déjà archivés et conformes : {len(rapport.deja_presents)} PNG")
    for nom in rapport.variantes:
        print(f"variante : site/landing/{nom}")
    for e in rapport.ecartees:
        print(f"ÉCARTÉE {e}")
    if rapport.erreurs:
        print(f"REFUS : {len(rapport.erreurs)} problème(s) ; manifeste et pages inchangés.")
        for e in rapport.erreurs:
            print(f"  - {e}")
        return 1
    print(f"Source locale : manifeste mis à jour, {len(rapport.pages)} page(s) réécrite(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
