#!/usr/bin/env python3
"""Visuels de la marque : une seule source d'adresses (``site/config/visuels.json``), appliquée aux pages.

Les pages (landing ``site/landing/*.html`` et maquettes ``site/maquettes/*.html``) ne contiennent que des balises
marquées ``data-visuel="<identifiant>"`` : ``<img>``, ``<source>`` (dans ``<picture>``) et ``<link rel="preload">``.
Ce module réécrit leurs attributs gérés à partir du manifeste :

* ``<img>`` : ``src`` (variante légère), ``srcset`` (légère + PNG haute définition), ``width``, ``height`` ;
* ``<source>`` : ``srcset``, ``width``, ``height`` ;
* ``<link rel="preload">`` : ``href``, ``imagesrcset``.

Le texte alternatif, ``sizes``, ``loading``, ``fetchpriority`` et ``media`` restent écrits dans la page (ils dépendent
du contexte). Deux sources :

* ``distant`` (aperçu) : adresses du service de génération, telles que la propriétaire les voit ;
* ``local`` (publication) : fichiers rapatriés dans ``site/landing/assets/visuels/`` par
  ``site/outils/rapatrier_visuels.py``, qui mesure aussi la largeur réelle des variantes légères.

La publication est refusée tant que la source n'est pas ``local`` (``erreurs_publication``) : la page publiée ne
charge aucune image d'un tiers (politique de sécurité ``img-src 'self'``, aucune adresse IP de visiteur transmise).

Usage :
    python site/outils/visuels.py appliquer   # réécrit les balises data-visuel des pages
    python site/outils/visuels.py verifier    # code 1 si une page est désynchronisée ou un fichier local manque
    python site/outils/visuels.py liste       # adresses de chaque variante
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "site" / "config" / "visuels.json"
LANDING = REPO / "site" / "landing"
MAQUETTES = REPO / "site" / "maquettes"
SOURCES = ("distant", "local")
VARIANTES = {"min": "_min.webp", "hd": ".png"}
#: Largeur supposée de la variante légère tant qu'elle n'a pas été mesurée (fraction de la largeur de la PNG).
HYPOTHESE_RATIO_MIN = 0.5
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FICHIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
BALISE_RE = re.compile(r"<(img|source|link)\b([^<>]*?)\s*(/?)>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'([^\s=/>"]+)(?:\s*=\s*"([^"]*)")?')
GERES = {
    "img": ("src", "srcset", "width", "height"),
    "source": ("srcset", "width", "height"),
    "link": ("href", "imagesrcset"),
}


class VisuelsError(ValueError):
    """Manifeste invalide."""


# --------------------------------------------------------------------------- manifeste
def charger(chemin: Path = CONFIG) -> dict:
    """Manifeste validé ; lève ``VisuelsError`` si invalide."""
    manifeste = json.loads(chemin.read_text(encoding="utf-8"))
    erreurs = valider(manifeste)
    if erreurs:
        raise VisuelsError("; ".join(erreurs))
    return manifeste


def valider(m: dict) -> list[str]:
    """Erreurs de structure du manifeste (fermé par défaut : tout champ douteux est refusé)."""
    err: list[str] = []
    if m.get("source") not in SOURCES:
        err.append(f"source invalide {m.get('source')!r} (attendu : distant ou local)")
    base = str(m.get("base_distante", ""))
    u = urlparse(base)
    if u.scheme != "https" or not u.hostname or not base.endswith("/") or "?" in base or "#" in base:
        err.append("base_distante : adresse https se terminant par « / » attendue")
    dossier = str(m.get("dossier_local", ""))
    if not dossier.endswith("/") or dossier.startswith("/") or ".." in Path(dossier).parts or "\\" in dossier:
        err.append("dossier_local : chemin relatif à site/landing/ se terminant par « / » attendu (sans « .. »)")
    visuels = m.get("visuels")
    if not isinstance(visuels, dict) or not visuels:
        return err + ["visuels : liste vide"]
    for ident, v in visuels.items():
        if not ID_RE.match(ident):
            err.append(f"{ident} : identifiant invalide (minuscules, chiffres et tirets)")
        if not FICHIER_RE.match(str(v.get("fichier", ""))):
            err.append(f"{ident} : nom de fichier invalide (lettres, chiffres, « _ » et « - » ; sans extension)")
        for cle in ("largeur", "hauteur"):
            if not isinstance(v.get(cle), int) or isinstance(v.get(cle), bool) or not 0 < v[cle] <= 8192:
                err.append(f"{ident} : {cle} entière attendue (1 à 8192)")
        for cle in ("largeur_min", "hauteur_min"):
            val = v.get(cle)
            if val is not None and (not isinstance(val, int) or isinstance(val, bool) or not 0 < val <= 8192):
                err.append(f"{ident} : {cle} entière ou null attendue")
        if not str(v.get("description", "")).strip():
            err.append(f"{ident} : description manquante")
    return err


def nom_fichier(m: dict, ident: str, variante: str) -> str:
    """Nom du fichier d'une variante (``min`` ou ``hd``)."""
    return m["visuels"][ident]["fichier"] + VARIANTES[variante]


def chemin_local(m: dict, ident: str, variante: str, racine: Path = LANDING) -> Path:
    """Emplacement du fichier rapatrié d'une variante."""
    return racine / m["dossier_local"] / nom_fichier(m, ident, variante)


def url_distante(m: dict, ident: str, variante: str) -> str:
    """Adresse distante d'une variante."""
    return m["base_distante"] + nom_fichier(m, ident, variante)


def url(m: dict, ident: str, variante: str, page: Path, racine: Path = LANDING) -> str:
    """Adresse d'une variante vue depuis une page (distante, ou chemin relatif au fichier local de ``racine``)."""
    if m["source"] == "distant":
        return url_distante(m, ident, variante)
    cible = chemin_local(m, ident, variante, racine)
    return Path(os.path.relpath(cible, page.parent)).as_posix()


def largeur_min(m: dict, ident: str) -> int:
    """Largeur de la variante légère : mesurée, sinon hypothèse (moitié de la PNG)."""
    v = m["visuels"][ident]
    return int(v.get("largeur_min") or round(v["largeur"] * HYPOTHESE_RATIO_MIN))


def srcset(m: dict, ident: str, page: Path, racine: Path = LANDING) -> str:
    """Liste ``srcset`` : variante légère puis PNG haute définition (descripteurs de largeur)."""
    v = m["visuels"][ident]
    wmin = largeur_min(m, ident)
    if wmin >= v["largeur"]:
        return f"{url(m, ident, 'min', page, racine)} {v['largeur']}w"
    return f"{url(m, ident, 'min', page, racine)} {wmin}w, {url(m, ident, 'hd', page, racine)} {v['largeur']}w"


def attributs(m: dict, ident: str, balise: str, page: Path, racine: Path = LANDING) -> dict[str, str]:
    """Valeurs des attributs gérés d'une balise ``data-visuel``."""
    v = m["visuels"][ident]
    tout = {
        "src": url(m, ident, "min", page, racine),
        "href": url(m, ident, "min", page, racine),
        "srcset": srcset(m, ident, page, racine),
        "imagesrcset": srcset(m, ident, page, racine),
        "width": str(v["largeur"]),
        "height": str(v["hauteur"]),
    }
    return {k: tout[k] for k in GERES[balise]}


# --------------------------------------------------------------------------- pages
def pages() -> list[Path]:
    """Pages qui peuvent porter des visuels : landing et maquettes."""
    return sorted(LANDING.glob("*.html")) + (sorted(MAQUETTES.glob("*.html")) if MAQUETTES.is_dir() else [])


def _analyser_attributs(brut: str) -> list[tuple[str, str | None]]:
    return [(nom, val) for nom, val in ATTR_RE.findall(brut)]


def _reecrire(m: dict, page: Path, balise: str, brut: str, ferme: str, erreurs: list[str], racine: Path) -> str | None:
    attrs = _analyser_attributs(brut)
    noms = [n.lower() for n, _ in attrs]
    if "data-visuel" not in noms:
        return None
    ident = {n.lower(): v for n, v in attrs}["data-visuel"] or ""
    if ident not in m["visuels"]:
        erreurs.append(f"{page.name} : visuel inconnu « {ident} » (absent de site/config/visuels.json)")
        return None
    valeurs = attributs(m, ident, balise.lower(), page, racine)
    sortie: list[str] = []
    vus: set[str] = set()
    for nom, val in attrs:
        cle = nom.lower()
        if cle in valeurs:
            sortie.append(f'{nom}="{valeurs[cle]}"')
            vus.add(cle)
        else:
            sortie.append(nom if val is None else f'{nom}="{val}"')
    sortie += [f'{k}="{valeurs[k]}"' for k in GERES[balise.lower()] if k not in vus]
    return f"<{balise} {' '.join(sortie)}{' /' if ferme else ''}>"


def appliquer_texte(texte: str, m: dict, page: Path, erreurs: list[str] | None = None, racine: Path = LANDING) -> str:
    """Texte de la page avec les attributs gérés réécrits (idempotent)."""
    erreurs = [] if erreurs is None else erreurs

    def repl(x: re.Match[str]) -> str:
        nouveau = _reecrire(m, page, x.group(1), x.group(2), x.group(3), erreurs, racine)
        return x.group(0) if nouveau is None else nouveau

    return BALISE_RE.sub(repl, texte)


def appliquer(m: dict | None = None, liste: list[Path] | None = None, racine: Path = LANDING) -> list[str]:
    """Réécrit les pages ; retourne les noms des pages modifiées. Lève ``VisuelsError`` si un visuel est inconnu.

    ``racine`` : dossier de la landing qui contient (ou contiendra) ``dossier_local`` (copie de test, aperçu…).
    """
    m = charger() if m is None else m
    modifiees = []
    for page in pages() if liste is None else liste:
        texte = page.read_text(encoding="utf-8")
        erreurs: list[str] = []
        nouveau = appliquer_texte(texte, m, page, erreurs, racine)
        if erreurs:
            raise VisuelsError("; ".join(erreurs))
        if nouveau != texte:
            page.write_text(nouveau, encoding="utf-8")
            modifiees.append(page.name)
    return modifiees


def identifiants_utilises(texte: str) -> set[str]:
    """Identifiants ``data-visuel`` d'une page."""
    return set(re.findall(r'\bdata-visuel="([^"]*)"', texte))


def verifier(m: dict | None = None, liste: list[Path] | None = None, racine: Path = LANDING) -> list[str]:
    """Manifeste valide, pages synchronisées, aucune adresse distante hors balise gérée, fichiers locaux présents."""
    try:
        m = charger() if m is None else m
    except (OSError, ValueError) as exc:
        return [f"site/config/visuels.json : {exc}"]
    err = valider(m)
    if err:
        return [f"site/config/visuels.json : {e}" for e in err]
    hote = urlparse(m["base_distante"]).hostname or ""
    for page in pages() if liste is None else liste:
        texte = page.read_text(encoding="utf-8")
        erreurs: list[str] = []
        attendu = appliquer_texte(texte, m, page, erreurs, racine)
        err += erreurs
        if attendu != texte:
            err.append(f"{page.name} : balises data-visuel désynchronisées de site/config/visuels.json "
                       "(lancer python site/outils/visuels.py appliquer)")
        hors_balises = BALISE_RE.sub(lambda x: "" if "data-visuel" in x.group(2) else x.group(0), texte)
        if hote and hote in hors_balises:
            err.append(f"{page.name} : adresse {hote} hors d'une balise data-visuel (une seule source : visuels.json)")
    for css in sorted((racine / "css").glob("*.css")) + sorted((racine / "js").glob("*.js")):
        if hote and hote in css.read_text(encoding="utf-8"):
            err.append(f"{css.relative_to(racine).as_posix()} : adresse {hote} en dur (une seule source : visuels.json)")
    if m["source"] == "local":
        for ident in m["visuels"]:
            for variante in VARIANTES:
                if not chemin_local(m, ident, variante, racine).is_file():
                    err.append(f"{ident} : fichier local absent {m['dossier_local']}{nom_fichier(m, ident, variante)} "
                               "(lancer python site/outils/rapatrier_visuels.py)")
    return err


def erreurs_publication(m: dict | None = None, racine: Path = LANDING) -> list[str]:
    """Conditions de publication : images servies en local, mesurées, présentes."""
    try:
        m = charger() if m is None else m
    except (OSError, ValueError) as exc:
        return [f"site/config/visuels.json : {exc}"]
    if m["source"] != "local":
        return [
            (
                "visuels servis depuis une adresse distante : lancer python site/outils/rapatrier_visuels.py "
                "avant de publier (la page publiée ne charge aucune image d'un tiers)"
            )
        ]
    err = []
    for ident, v in m["visuels"].items():
        if v.get("largeur_min") is None:
            err.append(f"{ident} : largeur de la variante légère non mesurée (relancer rapatrier_visuels.py)")
        for variante in VARIANTES:
            if not chemin_local(m, ident, variante, racine).is_file():
                err.append(f"{ident} : fichier local absent {m['dossier_local']}{nom_fichier(m, ident, variante)}")
    return err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("appliquer", "verifier", "liste"))
    args = parser.parse_args(argv)
    try:
        m = charger()
    except (OSError, ValueError) as exc:
        print(f"ERREUR site/config/visuels.json : {exc}")
        return 1
    if args.action == "liste":
        for ident in m["visuels"]:
            for variante in VARIANTES:
                print(f"{ident:30} {variante:3} {url_distante(m, ident, variante)}")
        return 0
    if args.action == "appliquer":
        try:
            modifiees = appliquer(m)
        except VisuelsError as exc:
            print(f"ERREUR {exc}")
            return 1
        print(f"Source {m['source']} : {len(modifiees)} page(s) mise(s) à jour {modifiees}")
        return 0
    erreurs = verifier(m)
    for e in erreurs:
        print(f"ERREUR {e}")
    print("Visuels synchronisés." if not erreurs else f"{len(erreurs)} erreur(s).")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
