#!/usr/bin/env python3
"""Visuels de la marque : une seule source (``site/config/visuels.json``), appliquée aux pages.

Les pages (landing ``site/landing/*.html`` et maquettes ``site/maquettes/*.html``) ne contiennent que des balises
marquées ``data-visuel="<identifiant>"`` : ``<img>``, ``<source>`` (dans ``<picture>``) et ``<link rel="preload">``.
Ce module réécrit leurs attributs gérés à partir du manifeste :

* ``<img>`` : ``src``, ``srcset``, ``width``, ``height``, ``alt`` (texte alternatif du manifeste ; une page qui doit
  dire autre chose dans son contexte pose ``data-alt-contexte`` et garde son propre ``alt``) et ``data-fil`` ;
* ``<source>`` : ``srcset``, ``width``, ``height`` et ``data-fil`` ;
* ``<link rel="preload">`` : ``href``, ``imagesrcset``.

``data-fil`` : le filet orange photographié (« x1 y1 x2 y2 » en fractions de l'image d'origine, champ ``fil``), lu par
le script de la page pour raccorder le « fil orange » dessiné (DIRECTION_ATELIER.md §6) ; absent si ``fil`` est nul (un
``data-fil`` resté dans la page est alors retiré). ``sizes``, ``loading``, ``fetchpriority`` et ``media`` restent écrits
dans la page (ils dépendent de la mise en page).
Deux sources :

* ``local`` (publication, état normal) : variantes WebP à plusieurs largeurs (``<fichier>-<largeur>.webp``) dans
  ``site/landing/assets/visuels/``, produites par ``site/outils/rapatrier_visuels.py`` à partir des fichiers
  d'origine (import local ``--importer <dossier>``, ou rapatriement depuis ``base_distante``), qui restent une
  archive hors du dossier publié (``site/visuels-sources/``). Le ``srcset`` ne contient que ces variantes
  (descripteurs de largeur exacts) ;
* ``distant`` (aperçu seulement, si ``base_distante`` est renseignée) : la variante légère ``<fichier>_min.webp`` du
  service d'hébergement, **seule** (jamais la PNG haute définition).

Chaque visuel déclare aussi sa ``nature`` (``illustration`` de marque ou ``photo`` d'ambiance), son ``format``
(proportions « 21:9 », contrôlées), son ``usage``, sa ``description``, son ``alt`` (``""`` seulement si ``decoratif``),
le filet orange photographié (``fil`` : deux points en fractions de l'image, ou ``null``) et, une fois importé,
``fichier_source`` et ``empreinte_source`` (SHA-256 du fichier d'origine). Règles de rédaction contrôlées (fermé par
défaut, ``docs/05-da/DIRECTION_ATELIER.md`` §7 et §8) : aucun nom de la licence ; une photo d'ambiance ne se présente
jamais comme un produit en vente ; une illustration du renard ne décrit ni plusieurs queues, ni une posture debout, ni
vêtements, et toute boîte, carte ou étui décrit est « vierge » ou « sans marque ».

La publication est refusée tant que la source n'est pas ``local`` (``erreurs_publication``) : la page publiée ne
charge aucune image d'un tiers (politique de sécurité ``img-src 'self'``, aucune adresse IP de visiteur transmise).
Elle est aussi refusée si une variante dépasse son budget de poids (``plafond_octets``).

Usage :
    python site/outils/visuels.py appliquer   # réécrit les balises data-visuel des pages
    python site/outils/visuels.py verifier    # code 1 si une page est désynchronisée ou un fichier local manque
    python site/outils/visuels.py liste       # adresses distantes et variantes locales de chaque visuel
"""

from __future__ import annotations

import argparse
import html
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
#: Fichiers distants : variante légère (aperçu) et PNG haute définition (source du rapatriement, jamais servie).
VARIANTES_DISTANTES = {"min": "_min.webp", "hd": ".png"}
#: Budget de poids d'une variante locale : 250 Ko jusqu'à 1600 px de large (téléphones, cadres), 450 Ko au-delà
#: (grands écrans). Objectif : image principale ≤ 250 Ko sur mobile, ≤ 450 Ko sur ordinateur.
PLAFONDS_OCTETS = ((1600, 250 * 1024), (8192, 450 * 1024))
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FICHIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
FICHIER_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}\.(?:jpe?g|png|webp)$", re.IGNORECASE)
EMPREINTE_RE = re.compile(r"^[0-9a-f]{64}$")
FORMAT_RE = re.compile(r"^([1-9][0-9]?):([1-9][0-9]?)$")
#: Écart toléré entre les proportions déclarées (« 16:9 ») et les dimensions réelles (1920 × 1086 : 0,6 %).
TOLERANCE_FORMAT = 0.012
NATURES = ("illustration", "photo")
BALISE_RE = re.compile(r"<(img|source|link)\b([^<>]*?)\s*(/?)>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'([^\s=/>"]+)(?:\s*=\s*"([^"]*)")?')
GERES = {
    "img": ("src", "srcset", "width", "height", "alt", "data-fil"),
    "source": ("srcset", "width", "height", "data-fil"),
    "link": ("href", "imagesrcset"),
}
#: Attribut d'une balise <img> qui garde son propre texte alternatif (contexte de la page).
ALT_CONTEXTE = "data-alt-contexte"
#: Règles de rédaction (descriptions et textes alternatifs), DIRECTION_ATELIER.md §7–§8.
TERMES_LICENCE = re.compile(
    r"pok[ée]\s*-?\s*(?:mon|ball)|[ée]voli|eevee|feunard|ninetales|goupix|vulpix|roussil|braixen|zorua|zoroark|pikachu"
    r"|kurama|\btails\b|\bsega\b|\bnaruto\b",
    re.IGNORECASE,
)
TERMES_VENTE = re.compile(
    r"\b(?:nos|notre|en vente|à vendre|vendus?|prix|stock|disponibles?|achet\w*|commander)\b", re.IGNORECASE
)
TERMES_MASCOTTE_INTERDITS = re.compile(
    r"\bqueues\b|deux queues|neuf queues|\bdebout\b|deux pattes|\bgants?\b|chaussures?|v[êe]tements?|habill[ée]|"
    r"[ée]charpe|collerette|m[èe]che frontale",
    re.IGNORECASE,
)
OBJETS_DECRITS = re.compile(r"\b(?:bo[îi]tes?|[ée]tuis?|cartes?|classeurs?|pochettes?|sleeves?|toploaders?)\b", re.IGNORECASE)
OBJETS_VIERGES = re.compile(r"\bvierges?\b|sans marque", re.IGNORECASE)


class VisuelsError(ValueError):
    """Manifeste invalide."""


# --------------------------------------------------------------------------- manifeste
def charger(chemin: Path = CONFIG, *, exiger_variantes: bool = True) -> dict:
    """Manifeste validé ; lève ``VisuelsError`` si invalide.

    ``exiger_variantes=False`` : seul l'import local l'utilise, pour lire un manifeste dont un visuel vient d'être
    déclaré (source « local », variantes encore à produire) ; tous les autres contrôles restent appliqués.
    """
    manifeste = json.loads(chemin.read_text(encoding="utf-8"))
    erreurs = valider(manifeste, exiger_variantes=exiger_variantes)
    if erreurs:
        raise VisuelsError("; ".join(erreurs))
    return manifeste


def _entier(val: object, maxi: int = 8192) -> bool:
    return isinstance(val, int) and not isinstance(val, bool) and 0 < val <= maxi


def ratio_format(fmt: str) -> float | None:
    """Proportions d'un format « L:H » (ex. « 21:9 » → 2.333…) ; None si le format est invalide."""
    m = FORMAT_RE.match(str(fmt))
    return int(m.group(1)) / int(m.group(2)) if m else None


def _fil_valide(fil: object) -> bool:
    if fil is None:
        return True
    if not isinstance(fil, list) or len(fil) != 2:
        return False
    for point in fil:
        if not isinstance(point, list) or len(point) != 2:
            return False
        if not all(isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 1 for c in point):
            return False
    return True


def erreurs_redaction(ident: str, v: dict) -> list[str]:
    """Règles de rédaction des descriptions et textes alternatifs (licence, vente, règles de la mascotte)."""
    err: list[str] = []
    textes = {"alt": str(v.get("alt", "")), "description": str(v.get("description", "")), "usage": str(v.get("usage", ""))}
    for cle, texte in textes.items():
        m = TERMES_LICENCE.search(texte)
        if m:
            err.append(f"{ident} : {cle} cite « {m.group(0)} » (aucun nom ni personnage de la licence ou d'une autre marque)")
    if v.get("nature") == "photo":
        for cle in ("alt", "description"):
            m = TERMES_VENTE.search(textes[cle])
            if m:
                err.append(f"{ident} : {cle} d'une photo d'ambiance dit « {m.group(0)} » (jamais présentée comme un produit en vente)")
    if v.get("nature") == "illustration":
        for cle in ("alt", "description"):
            m = TERMES_MASCOTTE_INTERDITS.search(textes[cle])
            if m:
                err.append(f"{ident} : {cle} décrit « {m.group(0)} » (renard quadrupède, une seule queue, sans vêtement : "
                           "DIRECTION_ATELIER.md §8)")
    for cle in ("alt", "description"):
        if OBJETS_DECRITS.search(textes[cle]) and not OBJETS_VIERGES.search(textes[cle]):
            err.append(f"{ident} : {cle} décrit une boîte, une carte ou un étui sans dire « vierge » ou « sans marque »")
    return err


def valider(m: dict, *, exiger_variantes: bool = True) -> list[str]:
    """Erreurs de structure du manifeste (fermé par défaut : tout champ douteux est refusé)."""
    err: list[str] = []
    if m.get("source") not in SOURCES:
        err.append(f"source invalide {m.get('source')!r} (attendu : distant ou local)")
    base = m.get("base_distante")
    if base is None:
        if m.get("source") == "distant":
            err.append("base_distante : absente alors que la source est distante (visuels importés en local : source « local »)")
    else:
        base = str(base)
        u = urlparse(base)
        if u.scheme != "https" or not u.hostname or not base.endswith("/") or "?" in base or "#" in base:
            err.append("base_distante : adresse https se terminant par « / » attendue (ou null)")
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
            if not _entier(v.get(cle)):
                err.append(f"{ident} : {cle} entière attendue (1 à 8192)")
        largeurs = v.get("largeurs")
        if (
            not isinstance(largeurs, list)
            or not largeurs
            or not all(_entier(x) for x in largeurs)
            or largeurs != sorted(set(largeurs))
            or (_entier(v.get("largeur")) and largeurs[-1] > v["largeur"])
        ):
            err.append(f"{ident} : largeurs = liste croissante d'entiers, sans doublon, au plus la largeur de la PNG")
        variantes = v.get("variantes")
        if variantes is not None and (
            not isinstance(variantes, list)
            or not variantes
            or not all(_entier(x) for x in variantes)
            or variantes != sorted(set(variantes))
            or (isinstance(largeurs, list) and not set(variantes) <= set(largeurs))
        ):
            err.append(f"{ident} : variantes = null ou sous-liste croissante de largeurs (écrite par rapatrier_visuels.py)")
        for cle in ("description", "usage"):
            if not str(v.get(cle, "")).strip():
                err.append(f"{ident} : {cle} manquante")
        if v.get("nature") not in NATURES:
            err.append(f"{ident} : nature {v.get('nature')!r} invalide (illustration ou photo)")
        alt = v.get("alt")
        decoratif = v.get("decoratif", False)
        if not isinstance(alt, str) or not isinstance(decoratif, bool):
            err.append(f"{ident} : alt (texte) et decoratif (booléen) attendus")
        elif decoratif != (alt.strip() == ""):
            err.append(f"{ident} : alt vide si et seulement si decoratif = true")
        proportion = ratio_format(v.get("format", ""))
        if proportion is None:
            err.append(f"{ident} : format « L:H » attendu (ex. 21:9)")
        elif _entier(v.get("largeur")) and _entier(v.get("hauteur")):
            ecart = abs(v["largeur"] / v["hauteur"] / proportion - 1)
            if ecart > TOLERANCE_FORMAT:
                err.append(f"{ident} : {v['largeur']}×{v['hauteur']} ne respecte pas le format {v['format']} (écart {ecart:.1%})")
        if v.get("fichier_source") is not None and not FICHIER_SOURCE_RE.match(str(v["fichier_source"])):
            err.append(f"{ident} : fichier_source invalide (nom simple en .jpg, .jpeg, .png ou .webp)")
        if v.get("empreinte_source") is not None and not EMPREINTE_RE.match(str(v["empreinte_source"])):
            err.append(f"{ident} : empreinte_source = SHA-256 hexadécimal (écrit par rapatrier_visuels.py) ou null")
        if not _fil_valide(v.get("fil")):
            err.append(f"{ident} : fil = null ou deux points [x, y] en fractions de l'image (0 à 1)")
        err += erreurs_redaction(ident, v)
    if m.get("source") == "local" and isinstance(visuels, dict) and exiger_variantes:
        for ident, v in visuels.items():
            if not v.get("variantes"):
                err.append(f"{ident} : source locale sans variantes (lancer python site/outils/rapatrier_visuels.py --importer <dossier>)")
    return err


def hauteur_variante(v: dict, largeur: int) -> int:
    """Hauteur d'une variante (proportions de la PNG d'origine)."""
    return max(1, round(largeur * v["hauteur"] / v["largeur"]))


def plafond_octets(largeur: int) -> int:
    """Poids maximal d'une variante locale selon sa largeur."""
    for borne, plafond in PLAFONDS_OCTETS:
        if largeur <= borne:
            return plafond
    return PLAFONDS_OCTETS[-1][1]


def nom_variante(m: dict, ident: str, largeur: int) -> str:
    """Nom du fichier local d'une variante (``<fichier>-<largeur>.webp``)."""
    return f"{m['visuels'][ident]['fichier']}-{largeur}.webp"


def chemin_variante(m: dict, ident: str, largeur: int, racine: Path = LANDING) -> Path:
    """Emplacement d'une variante locale (dans le dossier publié de la landing)."""
    return racine / m["dossier_local"] / nom_variante(m, ident, largeur)


def url_distante(m: dict, ident: str, variante: str) -> str:
    """Adresse distante d'un fichier (``min`` : WebP léger de l'aperçu ; ``hd`` : PNG d'origine à rapatrier)."""
    if not m.get("base_distante"):
        raise VisuelsError("aucune base_distante : les visuels sont importés en local (rapatrier_visuels.py --importer)")
    return m["base_distante"] + m["visuels"][ident]["fichier"] + VARIANTES_DISTANTES[variante]


def hote_distant(m: dict) -> str:
    """Hôte de ``base_distante`` (chaîne vide si les visuels sont uniquement locaux)."""
    return urlparse(m.get("base_distante") or "").hostname or ""


def fil_html(m: dict, ident: str) -> str | None:
    """Filet photographié « x1 y1 x2 y2 » (fractions de l'image d'origine) ; None si le visuel n'en a pas."""
    fil = m["visuels"][ident].get("fil")
    if not fil:
        return None
    return " ".join(f"{c:g}" for point in fil for c in point)


def alt_html(m: dict, ident: str) -> str:
    """Texte alternatif du manifeste, échappé pour un attribut entre guillemets doubles."""
    return html.escape(str(m["visuels"][ident].get("alt", "")), quote=False).replace('"', "&quot;")


def _relatif(cible: Path, page: Path) -> str:
    return Path(os.path.relpath(cible, page.parent)).as_posix()


def variante_defaut(m: dict, ident: str) -> int:
    """Variante de ``src`` (navigateurs sans ``srcset``) : la plus large jusqu'à 1280 px, sinon la plus petite."""
    variantes = m["visuels"][ident]["variantes"]
    candidates = [w for w in variantes if w <= 1280]
    return candidates[-1] if candidates else variantes[0]


def src(m: dict, ident: str, page: Path, racine: Path = LANDING) -> str:
    """Adresse de repli (attribut ``src`` / ``href``)."""
    if m["source"] == "distant":
        return url_distante(m, ident, "min")
    return _relatif(chemin_variante(m, ident, variante_defaut(m, ident), racine), page)


def srcset(m: dict, ident: str, page: Path, racine: Path = LANDING) -> str:
    """Liste ``srcset`` : la variante légère distante seule (aperçu), ou les variantes locales avec leur largeur."""
    if m["source"] == "distant":
        return url_distante(m, ident, "min")
    return ", ".join(
        f"{_relatif(chemin_variante(m, ident, w, racine), page)} {w}w" for w in m["visuels"][ident]["variantes"]
    )


def attributs(m: dict, ident: str, balise: str, page: Path, racine: Path = LANDING) -> dict[str, str]:
    """Valeurs des attributs gérés d'une balise ``data-visuel`` (``data-fil`` omis si le visuel n'a pas de filet)."""
    v = m["visuels"][ident]
    tout: dict[str, str | None] = {
        "src": src(m, ident, page, racine),
        "href": src(m, ident, page, racine),
        "srcset": srcset(m, ident, page, racine),
        "imagesrcset": srcset(m, ident, page, racine),
        "width": str(v["largeur"]),
        "height": str(v["hauteur"]),
        "alt": alt_html(m, ident),
        "data-fil": fil_html(m, ident),
    }
    return {k: val for k in GERES[balise] if (val := tout[k]) is not None}


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
    geres = GERES[balise.lower()]
    if ALT_CONTEXTE in noms:
        valeurs.pop("alt", None)
        geres = tuple(k for k in geres if k != "alt")
    sortie: list[str] = []
    vus: set[str] = set()
    for nom, val in attrs:
        cle = nom.lower()
        if cle in valeurs:
            sortie.append(f'{nom}="{valeurs[cle]}"')
            vus.add(cle)
        elif cle in geres:
            continue  # attribut géré sans valeur pour ce visuel (ex. data-fil sans filet) : retiré
        else:
            sortie.append(nom if val is None else f'{nom}="{val}"')
    sortie += [f'{k}="{valeurs[k]}"' for k in geres if k in valeurs and k not in vus]
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


def _erreurs_fichiers_locaux(m: dict, racine: Path, *, poids: bool) -> list[str]:
    err: list[str] = []
    for ident, v in m["visuels"].items():
        for largeur in v.get("variantes") or []:
            cible = chemin_variante(m, ident, largeur, racine)
            nom = f"{m['dossier_local']}{cible.name}"
            if not cible.is_file():
                err.append(f"{ident} : fichier local absent {nom} (lancer python site/outils/rapatrier_visuels.py)")
                continue
            if not poids:
                continue
            octets = cible.read_bytes()
            if octets[:4] != b"RIFF" or octets[8:12] != b"WEBP":
                err.append(f"{ident} : {nom} n'est pas un fichier WebP")
            elif len(octets) > plafond_octets(largeur):
                err.append(f"{ident} : {nom} pèse {len(octets) // 1024} Ko, au-delà du budget de "
                           f"{plafond_octets(largeur) // 1024} Ko (relancer rapatrier_visuels.py)")
    return err


def verifier(m: dict | None = None, liste: list[Path] | None = None, racine: Path = LANDING) -> list[str]:
    """Manifeste valide, pages synchronisées, aucune adresse distante hors balise gérée, fichiers locaux présents."""
    try:
        m = charger() if m is None else m
    except (OSError, ValueError) as exc:
        return [f"site/config/visuels.json : {exc}"]
    err = valider(m)
    if err:
        return [f"site/config/visuels.json : {e}" for e in err]
    hote = hote_distant(m)
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
        for bloc in re.findall(r'\b(?:srcset|imagesrcset)="([^"]*)"', texte):
            if ".png" in bloc.lower():
                err.append(f"{page.name} : PNG dans un srcset (seules les variantes WebP sont servies)")
    for css in sorted((racine / "css").glob("*.css")) + sorted((racine / "js").glob("*.js")):
        if hote and hote in css.read_text(encoding="utf-8"):
            err.append(f"{css.relative_to(racine).as_posix()} : adresse {hote} en dur (une seule source : visuels.json)")
    if m["source"] == "local":
        err += _erreurs_fichiers_locaux(m, racine, poids=False)
    return err


def erreurs_publication(m: dict | None = None, racine: Path = LANDING) -> list[str]:
    """Conditions de publication : images servies en local, présentes, au format WebP et dans leur budget de poids."""
    try:
        m = charger() if m is None else m
    except (OSError, ValueError) as exc:
        return [f"site/config/visuels.json : {exc}"]
    if m["source"] != "local":
        return [
            (
                "visuels servis depuis une adresse distante : importer les fichiers en local (python "
                "site/outils/rapatrier_visuels.py --importer <dossier>) ou lancer python site/outils/rapatrier_visuels.py "
                "avant de publier (la page publiée ne charge aucune image d'un tiers)"
            )
        ]
    return _erreurs_fichiers_locaux(m, racine, poids=True)


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
        for ident, v in m["visuels"].items():
            if m.get("base_distante"):
                for variante in VARIANTES_DISTANTES:
                    print(f"{ident:30} {variante:5} {url_distante(m, ident, variante)}")
            for largeur in v.get("variantes") or []:
                print(f"{ident:30} {largeur:<5} {m['dossier_local']}{nom_variante(m, ident, largeur)}")
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
