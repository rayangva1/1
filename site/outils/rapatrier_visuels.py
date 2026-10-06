#!/usr/bin/env python3
"""Rapatrie les visuels de la marque dans ``site/landing/assets/visuels/`` et bascule les pages vers ces fichiers.

À lancer **avant toute mise en ligne**, sur une machine dont le réseau atteint l'adresse distante des visuels
(``site/config/visuels.json`` > ``base_distante``) : la page publiée ne doit charger aucune image d'un tiers
(politique de sécurité ``img-src 'self'``, aucune adresse IP de visiteur transmise), et ``publication.py`` refuse
de publier tant que la source des visuels n'est pas ``local``.

Pour chaque visuel, deux fichiers : la variante légère ``<fichier>_min.webp`` et la PNG haute définition
``<fichier>.png``. Chaque fichier est contrôlé avant d'être gardé : format réel (signature WebP ou PNG), taille
maximale, dimensions de la PNG identiques au manifeste, proportions de la variante légère identiques (± 2 %).
La largeur réelle de la variante légère est écrite dans le manifeste (``largeur_min``, ``hauteur_min``) : les
``srcset`` des pages deviennent exacts.

Fermé par défaut : si un seul fichier manque ou est refusé, le manifeste et les pages ne changent pas (les fichiers
valides déjà téléchargés restent pour la prochaine tentative).

Usage :
    python site/outils/rapatrier_visuels.py              # télécharge ce qui manque, contrôle, bascule en local
    python site/outils/rapatrier_visuels.py --forcer     # retélécharge tout
    python site/outils/rapatrier_visuels.py --verifier   # contrôle les fichiers locaux sans rien télécharger
    python site/outils/rapatrier_visuels.py --distant    # revient aux adresses distantes (aperçu), fichiers gardés
"""

from __future__ import annotations

import argparse
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

TAILLE_MAX = 40 * 1024 * 1024
DELAI_S = 60
TOLERANCE_PROPORTIONS = 0.02
FORMATS_ATTENDUS = {"min": "webp", "hd": "png"}


class RapatriementError(RuntimeError):
    """Fichier refusé (format, taille ou dimensions)."""


@dataclass
class Rapport:
    """Résultat d'un rapatriement."""

    telecharges: list[str] = field(default_factory=list)
    deja_presents: list[str] = field(default_factory=list)
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


def controler(octets: bytes, variante: str, attendu: dict) -> tuple[int, int]:
    """Contrôle un fichier téléchargé ; retourne ses dimensions."""
    if not octets:
        raise RapatriementError("fichier vide")
    if len(octets) > TAILLE_MAX:
        raise RapatriementError(f"fichier trop lourd ({len(octets)} octets > {TAILLE_MAX})")
    fmt, largeur, hauteur = dimensions(octets)
    if fmt != FORMATS_ATTENDUS[variante]:
        raise RapatriementError(f"format {fmt} reçu, {FORMATS_ATTENDUS[variante]} attendu")
    if variante == "hd" and (largeur, hauteur) != (attendu["largeur"], attendu["hauteur"]):
        raise RapatriementError(f"dimensions {largeur}×{hauteur}, {attendu['largeur']}×{attendu['hauteur']} attendues")
    if variante == "min":
        if largeur > attendu["largeur"] or hauteur > attendu["hauteur"]:
            raise RapatriementError(f"variante légère plus grande que la PNG ({largeur}×{hauteur})")
        if abs(largeur / hauteur - attendu["largeur"] / attendu["hauteur"]) > TOLERANCE_PROPORTIONS * attendu["largeur"] / attendu["hauteur"]:
            raise RapatriementError(f"proportions de la variante légère différentes ({largeur}×{hauteur})")
    return largeur, hauteur


def telecharger(url: str) -> bytes:
    """Télécharge une adresse https (proxy et certificats du système), taille bornée."""
    if not url.startswith("https://"):
        raise RapatriementError(f"adresse non https : {url}")
    requete = urllib.request.Request(url, headers={"User-Agent": "quai-des-cartes-rapatrier-visuels/1"})
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


# --------------------------------------------------------------------------- actions
def rapatrier(
    chemin_manifeste: Path = visuels.CONFIG,
    racine: Path = visuels.LANDING,
    *,
    telecharge: Callable[[str], bytes] = telecharger,
    forcer: bool = False,
    pages: list[Path] | None = None,
) -> Rapport:
    """Télécharge et contrôle chaque variante ; bascule le manifeste et les pages en local si tout est valide."""
    m = visuels.charger(chemin_manifeste)
    rapport = Rapport()
    mesures: dict[str, tuple[int, int]] = {}
    for ident, v in m["visuels"].items():
        for variante in visuels.VARIANTES:
            cible = visuels.chemin_local(m, ident, variante, racine)
            nom = f"{m['dossier_local']}{cible.name}"
            try:
                if cible.is_file() and not forcer:
                    taille = controler(cible.read_bytes(), variante, v)
                    rapport.deja_presents.append(nom)
                else:
                    octets = telecharge(visuels.url_distante(m, ident, variante))
                    taille = controler(octets, variante, v)
                    _ecrire_atomique(cible, octets)
                    rapport.telecharges.append(nom)
            except (RapatriementError, OSError, ValueError) as exc:
                rapport.erreurs.append(f"{ident} ({variante}) : {exc}")
                continue
            if variante == "min":
                mesures[ident] = taille
    if rapport.erreurs:
        return rapport
    for ident, (largeur, hauteur) in mesures.items():
        m["visuels"][ident]["largeur_min"] = largeur
        m["visuels"][ident]["hauteur_min"] = hauteur
    m["source"] = "local"
    _ecrire_manifeste(chemin_manifeste, m)
    rapport.bascule = True
    rapport.pages = visuels.appliquer(m, pages, racine)
    return rapport


def verifier_locaux(chemin_manifeste: Path = visuels.CONFIG, racine: Path = visuels.LANDING) -> list[str]:
    """Contrôle les fichiers locaux présents (format, dimensions), sans réseau."""
    m = visuels.charger(chemin_manifeste)
    erreurs = []
    for ident, v in m["visuels"].items():
        for variante in visuels.VARIANTES:
            cible = visuels.chemin_local(m, ident, variante, racine)
            if not cible.is_file():
                erreurs.append(f"{ident} ({variante}) : absent")
                continue
            try:
                largeur, hauteur = controler(cible.read_bytes(), variante, v)
            except RapatriementError as exc:
                erreurs.append(f"{ident} ({variante}) : {exc}")
                continue
            if variante == "min" and m["source"] == "local" and (v.get("largeur_min"), v.get("hauteur_min")) != (largeur, hauteur):
                erreurs.append(f"{ident} (min) : dimensions du manifeste ≠ fichier ({largeur}×{hauteur})")
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
    groupe.add_argument("--forcer", action="store_true", help="retélécharger même les fichiers déjà présents")
    groupe.add_argument("--verifier", action="store_true", help="contrôler les fichiers locaux sans réseau")
    groupe.add_argument("--distant", action="store_true", help="revenir aux adresses distantes (aperçu)")
    args = parser.parse_args(argv)
    if args.verifier:
        erreurs = verifier_locaux()
        for e in erreurs:
            print(f"ERREUR {e}")
        print("Fichiers locaux conformes." if not erreurs else f"{len(erreurs)} erreur(s).")
        return 1 if erreurs else 0
    if args.distant:
        pages = revenir_distant()
        print(f"Source distante (aperçu seulement) : {len(pages)} page(s) réécrite(s). La publication sera refusée.")
        return 0
    rapport = rapatrier(forcer=args.forcer)
    for nom in rapport.telecharges:
        print(f"téléchargé : site/landing/{nom}")
    if rapport.deja_presents:
        print(f"déjà présents et conformes : {len(rapport.deja_presents)} fichier(s)")
    if rapport.erreurs:
        print(f"REFUS : {len(rapport.erreurs)} fichier(s) manquant(s) ou refusé(s) ; manifeste et pages inchangés.")
        for e in rapport.erreurs:
            print(f"  - {e}")
        return 1
    print(f"Source locale : manifeste mis à jour, {len(rapport.pages)} page(s) réécrite(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
