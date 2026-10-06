#!/usr/bin/env python3
"""Rapatrie les visuels de la marque, produit leurs variantes WebP et bascule les pages vers ces fichiers.

À lancer **avant toute mise en ligne**, sur une machine dont le réseau atteint l'adresse distante des visuels
(``site/config/visuels.json`` > ``base_distante``) : la page publiée ne doit charger aucune image d'un tiers
(politique de sécurité ``img-src 'self'``, aucune adresse IP de visiteur transmise), et ``publication.py`` refuse
de publier tant que la source des visuels n'est pas ``local``.

Étapes, pour chaque visuel du manifeste :

1. **Archive** : la PNG haute définition d'origine (``<fichier>.png``) est téléchargée dans ``site/visuels-sources/``
   (hors du dossier publié, ignoré par git). Contrôles : signature PNG réelle, taille maximale, dimensions identiques
   au manifeste.
2. **Variantes** : une WebP par largeur de ``largeurs`` (``<fichier>-<largeur>.webp``, mêmes proportions) dans
   ``site/landing/assets/visuels/``, qualité 74 puis abaissée par paliers (jusqu'à 50) pour tenir le budget de poids
   (``visuels.plafond_octets`` : 250 Ko jusqu'à 1600 px, 450 Ko au-delà). Une variante qui ne tient pas son budget à
   la qualité 50 est écartée (signalée) ; la plus petite est toujours gardée. Les ``srcset`` des pages ne listent
   que ces variantes, avec leur largeur exacte : jamais la PNG.
3. **Bascule** : ``source`` passe à ``local``, ``variantes`` liste les largeurs produites, les pages sont réécrites.

Fermé par défaut : si un seul fichier manque ou est refusé, le manifeste et les pages ne changent pas (les PNG
valides déjà téléchargées restent dans l'archive pour la prochaine tentative). Nécessite Pillow (``pip install
Pillow``) pour produire les variantes.

Usage :
    python site/outils/rapatrier_visuels.py              # télécharge ce qui manque, produit les variantes, bascule en local
    python site/outils/rapatrier_visuels.py --forcer     # retélécharge les PNG d'origine
    python site/outils/rapatrier_visuels.py --verifier   # contrôle les variantes locales sans rien télécharger
    python site/outils/rapatrier_visuels.py --distant    # revient aux adresses distantes (aperçu), fichiers gardés
"""

from __future__ import annotations

import argparse
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
QUALITES = (74, 68, 62, 56, 50)


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


# --------------------------------------------------------------------------- formats
def dimensions(octets: bytes) -> tuple[str, int, int]:
    """(format, largeur, hauteur) lus dans l'en-tête d'un fichier PNG ou WebP ; lève RapatriementError sinon."""
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
    raise RapatriementError("format non reconnu (PNG ou WebP attendu)")


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


def controler_variante(octets: bytes, largeur: int, v: dict) -> None:
    """Contrôle une variante produite (format WebP, dimensions, budget de poids)."""
    fmt, l_reel, h_reel = dimensions(octets)
    if fmt != "webp":
        raise RapatriementError(f"variante {largeur} : format {fmt}, webp attendu")
    if (l_reel, h_reel) != (largeur, visuels.hauteur_variante(v, largeur)):
        raise RapatriementError(f"variante {largeur} : dimensions {l_reel}×{h_reel} inattendues")
    if len(octets) > visuels.plafond_octets(largeur):
        raise RapatriementError(f"variante {largeur} : {len(octets) // 1024} Ko > budget {visuels.plafond_octets(largeur) // 1024} Ko")


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


def produire_variantes(m: dict, ident: str, source: Path, racine: Path, rapport: Rapport) -> list[int]:
    """Écrit les variantes WebP d'un visuel ; retourne les largeurs gardées (lève RapatriementError si aucune)."""
    Image = _pillow()
    v = m["visuels"][ident]
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
        _ecrire_atomique(cible, octets)
        gardees.append(largeur)
        rapport.variantes.append(f"{m['dossier_local']}{cible.name} ({len(octets) // 1024} Ko, qualité {qualite})")
    if not gardees:
        raise RapatriementError("aucune variante dans son budget de poids (réduire « largeurs »)")
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


def verifier_locaux(chemin_manifeste: Path = visuels.CONFIG, racine: Path = visuels.LANDING) -> list[str]:
    """Contrôle les variantes locales listées par le manifeste (format, dimensions, budget), sans réseau."""
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
    return erreurs


def revenir_distant(
    chemin_manifeste: Path = visuels.CONFIG, pages: list[Path] | None = None, racine: Path = visuels.LANDING
) -> list[str]:
    """Repasse le manifeste en source distante (aperçu) et réécrit les pages ; les fichiers locaux restent."""
    m = visuels.charger(chemin_manifeste)
    m["source"] = "distant"
    _ecrire_manifeste(chemin_manifeste, m)
    return visuels.appliquer(m, pages, racine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    groupe = parser.add_mutually_exclusive_group()
    groupe.add_argument("--forcer", action="store_true", help="retélécharger les PNG d'origine déjà archivées")
    groupe.add_argument("--verifier", action="store_true", help="contrôler les variantes locales sans réseau")
    groupe.add_argument("--distant", action="store_true", help="revenir aux adresses distantes (aperçu)")
    args = parser.parse_args(argv)
    if args.verifier:
        erreurs = verifier_locaux()
        for e in erreurs:
            print(f"ERREUR {e}")
        print("Variantes locales conformes." if not erreurs else f"{len(erreurs)} erreur(s).")
        return 1 if erreurs else 0
    if args.distant:
        pages = revenir_distant()
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
