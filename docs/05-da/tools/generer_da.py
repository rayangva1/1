#!/usr/bin/env python3
"""Génère les fichiers DA dérivés à partir de tokens/tokens.json et du lettrage.

Sorties (toutes dans docs/05-da/) :
- tokens/tokens.css            variables CSS des 2 directions, clair + sombre
- tokens/tokens-nuit.css       ambiance « Nuit sur le Léman » (data-ambiance="nuit", bâtie sur B, toujours sombre)
- logo/{a,b}/*.svg             logos vectoriels (contours pleins, sans police)
- social/{a,b}/*.svg           templates 9:16, 4:5, 1:1 (zones photo à remplacer)
- social/guides/*.svg          zones sûres indicatives
- packaging/{a,b}/*.svg        sticker, carte A6 recto/verso, repère commande (mm)
- components/email-transactionnel-{a,b}.html   email HTML « email-safe »
- components/icones.svg        sprite des pictogrammes
- CHARTE.html, components/{badges,carte-produit,banniere,page-produit}.html   (tools/pages_html.py)
- DIRECTION_A.md / DIRECTION_B.md / DIRECTION_NUIT.md : tableaux de contrastes réinjectés entre marqueurs
- logo/png/*.png               exports PNG (option --png, nécessite cairosvg)

Usage : python docs/05-da/tools/generer_da.py [--png]
Le script est déterministe : relancer sans changement ne modifie aucun octet.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))

from icones import ICONES, icone_inline, sprite_icones  # noqa: E402,F401
from glyphes import (  # noqa: E402
    ESPACE_A,
    ESPACE_B,
    GLYPHES_A,
    GLYPHES_B,
    INTERLETTRE_A,
    INTERLETTRE_B,
    KERN_A,
    KERN_B,
    Pen,
    b_q,
    composer,
    num,
)

RACINE = Path(__file__).resolve().parents[1]
TOKENS: dict = json.loads((RACINE / "tokens" / "tokens.json").read_text(encoding="utf-8"))
NOM = TOKENS["meta"]["nomDeTravail"]
DIRECTIONS = ("a", "b")
AMBIANCES = tuple(TOKENS.get("ambiances", {}))


# ---------------------------------------------------------------------------
# Accès aux tokens
# ---------------------------------------------------------------------------
def couleurs(da: str, mode: str = "light") -> dict[str, str]:
    """Couleurs d'une direction/mode : {nom: '#RRGGBB'}."""
    return {k: v["$value"] for k, v in TOKENS["directions"][da]["color"][mode].items()}


def couleurs_ambiance(nom: str) -> dict[str, str]:
    """Couleurs d'une ambiance (toujours sombre) : {nom: '#RRGGBB'}."""
    return {k: v["$value"] for k, v in TOKENS["ambiances"][nom]["color"]["dark"].items()}


def police(da: str, role: str) -> str:
    """Pile de polices (guillemets simples, utilisable dans un attribut SVG/HTML)."""
    return TOKENS["directions"][da]["font"][role]["$value"].replace('"', "'")


# ---------------------------------------------------------------------------
# tokens.css
# ---------------------------------------------------------------------------
def _bloc(selecteurs: list[str], decls: list[tuple[str, str]], indent: str = "") -> str:
    sel = (",\n" + indent).join(selecteurs)
    corps = "".join(f"{indent}  {k}: {v};\n" for k, v in decls)
    return f"{indent}{sel} {{\n{corps}{indent}}}\n"


def _decls_direction(da: str) -> list[tuple[str, str]]:
    d = TOKENS["directions"][da]
    out = [(f"--da-font-{k}", v["$value"]) for k, v in d["font"].items()]
    out += [(f"--da-{k}", v["$value"]) for k, v in d["style"].items()]
    return out


def _decls_couleurs(da: str, mode: str) -> list[tuple[str, str]]:
    return [("color-scheme", "light" if mode == "light" else "dark")] + [
        (f"--da-color-{k}", v) for k, v in couleurs(da, mode).items()
    ]


def generer_css() -> str:
    """Construit tokens.css (variables uniquement, aucune règle de mise en page)."""
    sh = TOKENS["shared"]
    partage: list[tuple[str, str]] = []
    for groupe, prefixe in (("space", "space"), ("text", "text"), ("leading", "leading")):
        partage += [(f"--da-{prefixe}-{k}", v["$value"]) for k, v in sh[groupe].items()]
    partage += [(f"--da-{k}", v["$value"]) for k, v in sh["layout"].items()]

    nl = '[data-theme="light"]'
    parts = [
        "/*\n"
        f" * Design tokens — {NOM} (nom de travail, non validé)\n"
        " * FICHIER GÉNÉRÉ par docs/05-da/tools/generer_da.py depuis tokens.json — ne pas éditer à la main.\n"
        " * Direction : data-da=\"a\" (défaut) | \"b\" sur <html> ou sur une section.\n"
        " * Mode : suit prefers-color-scheme ; forcer avec data-theme=\"dark\" | \"light\" sur <html>.\n"
        " * Polices Google Fonts à charger séparément (URL dans tokens.json > directions > googleFonts).\n"
        " */\n",
        _bloc([":root"], partage),
        "\n/* Direction A — Quai (signal) : clair */\n",
        _bloc([":root", '[data-da="a"]'], _decls_direction("a") + _decls_couleurs("a", "light")),
        "\n/* Direction B — Pochette (collection) : clair */\n",
        _bloc(['[data-da="b"]'], _decls_direction("b") + _decls_couleurs("b", "light")),
        "\n/* Mode sombre automatique (sauf data-theme=\"light\" sur <html>) */\n@media (prefers-color-scheme: dark) {\n",
        _bloc([f":root:not({nl})", f':root:not({nl}) [data-da="a"]'], _decls_couleurs("a", "dark"), "  "),
        _bloc([f':root:not({nl})[data-da="b"]', f':root:not({nl}) [data-da="b"]'], _decls_couleurs("b", "dark"), "  "),
        "}\n",
        "\n/* Mode sombre forcé : data-theme=\"dark\" sur <html> */\n",
        _bloc([':root[data-theme="dark"]', ':root[data-theme="dark"] [data-da="a"]'], _decls_couleurs("a", "dark")),
        _bloc([':root[data-theme="dark"][data-da="b"]', ':root[data-theme="dark"] [data-da="b"]'], _decls_couleurs("b", "dark")),
    ]
    return "".join(parts)


def generer_css_ambiance(nom: str) -> str:
    """Construit tokens-<nom>.css : surcharge des variables de la direction de base, toujours en sombre.

    Sélecteur ``:root[data-ambiance="<nom>"][data-da]`` : même spécificité que les blocs sombres de tokens.css
    (0,3,0) et chargé après lui, il l'emporte quel que soit le réglage clair/sombre du système.
    """
    amb = TOKENS["ambiances"][nom]
    decls = [("color-scheme", "dark")]
    decls += [(f"--da-font-{k}", v["$value"]) for k, v in amb["font"].items()]
    decls += [(f"--da-{k}", v["$value"]) for k, v in amb["style"].items()]
    decls += [(f"--da-color-{k}", v) for k, v in couleurs_ambiance(nom).items()]
    return (
        "/*\n"
        f" * Ambiance « {amb['nom']} » — {NOM} (nom de travail, non validé)\n"
        " * FICHIER GÉNÉRÉ par docs/05-da/tools/generer_da.py depuis tokens.json — ne pas éditer à la main.\n"
        f" * À charger APRÈS tokens.css ; s'active avec data-ambiance=\"{nom}\" et data-da=\"{amb['base']}\" sur <html>.\n"
        " * Toujours sombre : aucun mode clair (contrastes calculés dans DIRECTION_NUIT.md).\n"
        " * Polices Google Fonts : URL dans tokens.json > ambiances > googleFonts.\n"
        " */\n"
        + _bloc([f':root[data-ambiance="{nom}"][data-da]'], decls)
    )


# ---------------------------------------------------------------------------
# SVG utilitaires
# ---------------------------------------------------------------------------
def svg_doc(
    w: float,
    h: float,
    titre: str,
    desc: str,
    corps: str,
    unite: str = "",
) -> str:
    """Document SVG autonome avec titre/description accessibles."""
    largeur = f"{num(w)}{unite}"
    hauteur = f"{num(h)}{unite}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(w)} {num(h)}" '
        f'width="{largeur}" height="{hauteur}" role="img" aria-labelledby="titre desc">\n'
        f"  <title id=\"titre\">{escape(titre)}</title>\n"
        f"  <desc id=\"desc\">{escape(desc)}</desc>\n"
        f"{corps}"
        "</svg>\n"
    )


def chemins(calques: list[tuple[str, list[str]]], indent: str = "  ") -> str:
    """Un <path> par couleur (règle nonzero)."""
    return "".join(f'{indent}<path fill="{c}" d="{"".join(d)}"/>\n' for c, d in calques if d)


def texte(
    x: float,
    y: float,
    contenu: str,
    *,
    famille: str,
    taille: float,
    graisse: int = 400,
    fill: str,
    ancre: str = "start",
    espacement: float | None = None,
    ident: str | None = None,
) -> str:
    """Élément <text> éditable (une ligne, pas de retour automatique)."""
    attrs = (
        f'x="{num(x)}" y="{num(y)}" font-family="{famille}" font-size="{num(taille)}" '
        f'font-weight="{graisse}" fill="{fill}"'
    )
    if ancre != "start":
        attrs += f' text-anchor="{ancre}"'
    if espacement is not None:
        attrs += f' letter-spacing="{num(espacement)}"'
    if ident:
        attrs += f' id="{ident}"'
    return f"  <text {attrs}>{escape(contenu)}</text>\n"


# ---------------------------------------------------------------------------
# Logos
# ---------------------------------------------------------------------------
def _trace(fn: Callable[[Pen], None], ox: float = 0.0, oy: float = 0.0, s: float = 1.0) -> Pen:
    p = Pen(ox=ox, oy=oy, s=s)
    fn(p)
    return p


def _recaler(fn: Callable[[Pen], None], s: float = 1.0, ox: float = 0.0, oy: float = 0.0) -> tuple[Pen, float, float]:
    """Trace ``fn`` de sorte que sa boîte englobante commence en (ox, oy)."""
    essai = _trace(fn, 0, 0, s)
    minx, miny, maxx, maxy = essai.bbox
    p = _trace(fn, ox - minx, oy - miny, s)
    return p, maxx - minx, maxy - miny


def _mot_a(texte_: str) -> Callable[[Pen], float]:
    return lambda p: composer(p, texte_, GLYPHES_A, KERN_A, INTERLETTRE_A, ESPACE_A)


def _mot_b(texte_: str) -> Callable[[Pen], float]:
    return lambda p: composer(p, texte_, GLYPHES_B, KERN_B, INTERLETTRE_B, ESPACE_B)


def dessin_a_empile(p: Pen) -> None:
    """A principal : « QUAI DES / CARTES » + barre-quai (calque accent)."""
    oy0, ox0 = p.oy, p.ox
    _mot_a("QUAI DES")(p)
    larg1 = p.bbox[2]
    p.oy = oy0 + 128 * p.s
    _mot_a("CARTES")(p)
    larg = max(larg1, p.bbox[2]) - ox0
    p.oy = oy0
    p.rect(0, 250, larg / p.s, 18, layer="accent")


def dessin_a_horizontal(p: Pen) -> None:
    """A horizontal : « QUAI DES CARTES » sur une ligne + barre-quai."""
    ox0 = p.ox
    _mot_a("QUAI DES CARTES")(p)
    p.rect(0, 122, (p.bbox[2] - ox0) / p.s, 18, layer="accent")


def dessin_a_monogramme(p: Pen, fond: str, lettre: str, accent: str) -> list[tuple[str, list[str]]]:
    """A monogramme 120×120 : carré encre, Q papier, barre-quai accent."""
    carre = Pen(ox=p.ox, oy=p.oy, s=p.s)
    carre.card(60, 60, 120, 120, 16)
    q = Pen(ox=p.ox + 31 * p.s, oy=p.oy + 20 * p.s, s=0.58 * p.s)
    GLYPHES_A["Q"](q)
    barre = Pen(ox=p.ox, oy=p.oy, s=p.s)
    barre.rect(22, 88, 76, 10)
    return [(fond, carre.main), (lettre, q.main), (accent, barre.main)]


def dessin_a_monogramme_mono(p: Pen) -> None:
    """A monogramme une couleur : Q + barre-quai, sans carré de fond."""
    GLYPHES_A["Q"](p)
    p.rect(-8, 118, 122, 18)


def dessin_a_favicon(fond: str, lettre: str, accent: str) -> list[tuple[str, list[str]]]:
    """Favicon A 32×32, graisse renforcée pour 16 px."""
    carre = Pen()
    carre.card(16, 16, 32, 32, 6)
    q = Pen()
    q.ring(16, 13.5, 9.5, 5.2)
    q.poly([(17.2, 16.6), (21.4, 16.6), (26.4, 23.5), (22.2, 23.5)])
    barre = Pen()
    barre.rect(5.5, 25.5, 21, 3.5)
    return [(fond, carre.main), (lettre, q.main), (accent, barre.main)]


def dessin_b_mot(p: Pen) -> None:
    """B principal : « quai des cartes » sur une ligne, point du i en carte (accent)."""
    _mot_b("quai des cartes")(p)


def dessin_b_empile(p: Pen) -> None:
    """B empilé : « quai des / cartes »."""
    oy0 = p.oy
    _mot_b("quai des")(p)
    p.oy = oy0 + 112 * p.s
    _mot_b("cartes")(p)
    p.oy = oy0


def dessin_b_monogramme(p: Pen, contour: str, carte: str, lettre: str) -> list[tuple[str, list[str]]]:
    """B monogramme 120×120 : deux cartes inclinées, « q » sur la carte avant."""
    arriere = Pen(ox=p.ox, oy=p.oy, s=p.s)
    arriere.card(66, 58, 60, 84, 9, 8)
    arriere.card(66, 58, 48, 72, 4, 8, reverse=True)
    avant = Pen(ox=p.ox, oy=p.oy, s=p.s)
    avant.card(54, 62, 60, 84, 9, -8)
    q = Pen(ox=p.ox + 35 * p.s, oy=p.oy + 24.5 * p.s, s=0.5 * p.s)
    b_q(q)
    return [(contour, arriere.main), (carte, avant.main), (lettre, q.main)]


def dessin_b_favicon(fond: str, lettre: str) -> list[tuple[str, list[str]]]:
    """Favicon B 32×32 : carte accent, « q » blanc renforcé."""
    carre = Pen()
    carre.card(16, 16, 32, 32, 7)
    q = Pen()
    q.ring(14, 15, 8, 4)
    q.rect(18, 9, 4, 16)
    q.circle(20, 9, 2)
    q.circle(20, 25, 2)
    return [(fond, carre.main), (lettre, q.main)]


DESC_LOGO = (
    "Nom de travail NON VALIDÉ. Lettrage original construit à la main en contours pleins "
    "(aucune police, aucun personnage, symbole ou typographie de licence). Voir logo/REGLES_LOGO.md."
)


def fichiers_logos() -> dict[str, str]:
    """Tous les SVG de logo, {chemin relatif: contenu}."""
    out: dict[str, str] = {}
    ca, cad = couleurs("a"), couleurs("a", "dark")
    cb, cbd = couleurs("b"), couleurs("b", "dark")

    def logo(chemin: str, fn: Callable[[Pen], None], ink: str, acc: str, titre: str) -> None:
        p, w, h = _recaler(fn)
        out[chemin] = svg_doc(w, h, titre, DESC_LOGO, chemins([(ink, p.main), (acc, p.accent)]))

    # Direction A
    logo("logo/a/logo-a-principal.svg", dessin_a_empile, ca["ink"], ca["accent"], f"{NOM} — logo principal, direction A")
    logo("logo/a/logo-a-horizontal.svg", dessin_a_horizontal, ca["ink"], ca["accent"], f"{NOM} — logo horizontal, direction A")
    logo("logo/a/logo-a-principal-fond-sombre.svg", dessin_a_empile, cad["ink"], cad["accent"], f"{NOM} — logo principal sur fond sombre, direction A")
    logo("logo/a/logo-a-horizontal-fond-sombre.svg", dessin_a_horizontal, cad["ink"], cad["accent"], f"{NOM} — logo horizontal sur fond sombre, direction A")
    logo("logo/a/logo-a-mono-noir.svg", dessin_a_empile, "#000000", "#000000", f"{NOM} — logo monochrome noir, direction A")
    logo("logo/a/logo-a-mono-blanc.svg", dessin_a_empile, "#FFFFFF", "#FFFFFF", f"{NOM} — logo monochrome blanc (fond foncé), direction A")
    logo("logo/a/logo-a-horizontal-mono-noir.svg", dessin_a_horizontal, "#000000", "#000000", f"{NOM} — logo horizontal monochrome noir, direction A")
    mono = dessin_a_monogramme(Pen(), ca["ink"], ca["bg"], ca["accent"])
    out["logo/a/logo-a-monogramme.svg"] = svg_doc(120, 120, f"{NOM} — monogramme Q, direction A", DESC_LOGO, chemins(mono))
    p, w, h = _recaler(dessin_a_monogramme_mono)
    out["logo/a/logo-a-monogramme-mono-noir.svg"] = svg_doc(w, h, f"{NOM} — monogramme monochrome noir, direction A", DESC_LOGO, chemins([("#000000", p.main)]))
    out["logo/a/favicon.svg"] = svg_doc(32, 32, f"{NOM} — favicon, direction A", DESC_LOGO, chemins(dessin_a_favicon(ca["ink"], ca["bg"], ca["accent"])))

    # Direction B
    logo("logo/b/logo-b-principal.svg", dessin_b_mot, cb["ink"], cb["accent"], f"{NOM} — logo principal, direction B")
    logo("logo/b/logo-b-empile.svg", dessin_b_empile, cb["ink"], cb["accent"], f"{NOM} — logo empilé, direction B")
    logo("logo/b/logo-b-principal-fond-sombre.svg", dessin_b_mot, cbd["ink"], cbd["accent-text"], f"{NOM} — logo principal sur fond sombre, direction B")
    logo("logo/b/logo-b-mono-noir.svg", dessin_b_mot, "#000000", "#000000", f"{NOM} — logo monochrome noir, direction B")
    logo("logo/b/logo-b-mono-blanc.svg", dessin_b_mot, "#FFFFFF", "#FFFFFF", f"{NOM} — logo monochrome blanc (fond foncé), direction B")
    mono_b = dessin_b_monogramme(Pen(), cb["ink"], cb["accent"], "#FFFFFF")
    out["logo/b/logo-b-monogramme.svg"] = svg_doc(120, 120, f"{NOM} — monogramme cartes, direction B", DESC_LOGO, chemins(mono_b))
    mono_bn = Pen()
    mono_bn.card(66, 58, 60, 84, 9, 8)
    mono_bn.card(66, 58, 48, 72, 4, 8, reverse=True)
    mono_bn.card(54, 62, 60, 84, 9, -8)
    qn = Pen(ox=35, oy=24.5, s=0.5)
    b_q(qn)
    out["logo/b/logo-b-monogramme-mono-noir.svg"] = svg_doc(
        120, 120, f"{NOM} — monogramme monochrome noir, direction B", DESC_LOGO,
        chemins([("#000000", mono_bn.main), ("#FFFFFF", qn.main)]),
    )
    out["logo/b/favicon.svg"] = svg_doc(32, 32, f"{NOM} — favicon, direction B", DESC_LOGO, chemins(dessin_b_favicon(cb["accent"], "#FFFFFF")))
    # Ambiance Nuit (bâtie sur B) : même lettrage, clair de lune et point du « i » rose lune
    if "nuit" in AMBIANCES:
        cn = couleurs_ambiance("nuit")
        logo("logo/b/logo-b-nuit.svg", dessin_b_mot, cn["ink"], cn["accent-text"], f"{NOM} — logo principal, ambiance Nuit sur le Léman")
    return out


# ---------------------------------------------------------------------------
# Éléments graphiques communs aux templates
# ---------------------------------------------------------------------------
STATUTS = {
    "fr": ("lang-fr-bg", "lang-fr-fg"),
    "local": ("status-local-bg", "status-local-fg"),
    "preorder": ("status-preorder-bg", "status-preorder-fg"),
    "new": ("status-new-bg", "status-new-fg"),
    "out": ("status-out-bg", "status-out-fg"),
    "restock": ("status-restock-bg", "status-restock-fg"),
}
LIBELLES = {
    "a": {"fr": "FR", "local": "STOCK LOCAL", "preorder": "PRÉCOMMANDE", "new": "NOUVEAUTÉ", "out": "RUPTURE", "restock": "ALERTE RÉASSORT"},
    "b": {"fr": "FR", "local": "stock local", "preorder": "précommande", "new": "nouveauté", "out": "rupture", "restock": "alerte réassort"},
}
# Largeur moyenne d'un caractère en em (estimation pour dimensionner les badges).
CHASSE_EM = {"a": 0.66, "b": 0.56}


def badge(da: str, x: float, y: float, statut: str, taille: float) -> tuple[str, float]:
    """Badge SVG (fond + texte) ; renvoie (svg, largeur)."""
    c = couleurs(da)
    fond, encre = STATUTS[statut]
    libelle = LIBELLES[da][statut]
    pad = taille * 0.75
    w = len(libelle) * taille * CHASSE_EM[da] + 2 * pad
    h = taille * 2.0
    rx = 4 if da == "a" else h / 2
    svg = (
        f'  <rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="{num(rx)}" fill="{c[fond]}"/>\n'
        + texte(
            x + w / 2, y + h * 0.68, libelle,
            famille=police(da, "text"), taille=taille, graisse=700 if da == "a" else 700,
            fill=c[encre], ancre="middle", espacement=taille * 0.06 if da == "a" else None,
        )
    )
    return svg, w


def badges(da: str, x: float, y: float, statuts: list[str], taille: float) -> str:
    """Rangée de badges espacés."""
    out = ""
    for s in statuts:
        svg, w = badge(da, x, y, s, taille)
        out += svg
        x += w + taille * 0.6
    return out


def zone_photo(da: str, x: float, y: float, w: float, h: float, consigne: str, ident: str = "ZONE_PHOTO") -> str:
    """Emplacement de photo produit RÉELLE (à remplacer, jamais d'emballage généré)."""
    c = couleurs(da)
    rx = 0 if da == "a" else 36
    t = min(w, h)
    taille = max(22.0, min(34.0, t / 16))
    cx, cy = x + w / 2, y + h / 2
    return (
        f'  <g id="{ident}">\n'
        f'    <rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="{rx}" fill="{c["surface-alt"]}" '
        f'stroke="{c["line-strong"]}" stroke-width="3" stroke-dasharray="14 10"/>\n'
        + "  "
        + texte(cx, cy - taille * 0.4, "PHOTO PRODUIT RÉELLE", famille=police(da, "text"), taille=taille, graisse=700, fill=c["ink-muted"], ancre="middle", espacement=1)
        + "  "
        + texte(cx, cy + taille * 1.1, consigne, famille=police(da, "text"), taille=taille * 0.72, graisse=400, fill=c["ink-muted"], ancre="middle")
        + "  "
        + texte(cx, cy + taille * 2.2, "Jamais d'emballage généré ni de visuel non autorisé", famille=police(da, "text"), taille=taille * 0.62, graisse=400, fill=c["ink-muted"], ancre="middle")
        + "  </g>\n"
    )


def logo_inline(da: str, x: float, y: float, hauteur: float, fond_sombre: bool = False) -> str:
    """Logo horizontal intégré en contours (pas de lien externe)."""
    c = couleurs(da, "dark" if fond_sombre else "light")
    if da == "a":
        essai = _trace(dessin_a_horizontal)
        s = hauteur / (essai.bbox[3] - essai.bbox[1])
        p, _, _ = _recaler(dessin_a_horizontal, s=s, ox=x, oy=y)
        acc = c["accent"]
    else:
        essai = _trace(dessin_b_mot)
        s = hauteur / (essai.bbox[3] - essai.bbox[1])
        p, _, _ = _recaler(dessin_b_mot, s=s, ox=x, oy=y)
        acc = c["accent"] if not fond_sombre else c["accent-text"]
    return '  <g id="LOGO">\n' + chemins([(c["ink"], p.main), (acc, p.accent)], "    ") + "  </g>\n"


def largeur_logo(da: str, hauteur: float) -> float:
    """Largeur du logo horizontal pour une hauteur donnée."""
    essai = _trace(dessin_a_horizontal if da == "a" else dessin_b_mot)
    w = essai.bbox[2] - essai.bbox[0]
    return w * hauteur / (essai.bbox[3] - essai.bbox[1])


def fond(da: str, w: float, h: float) -> str:
    return f'  <rect id="FOND" width="{num(w)}" height="{num(h)}" fill="{couleurs(da)["bg"]}"/>\n'


def titre(da: str, x: float, y: float, lignes: list[str], taille: float, ancre: str = "start", interligne: float = 1.05) -> str:
    """Titre multi-lignes (capitales en A, bas-de-casse en B)."""
    c = couleurs(da)
    out = ""
    for i, ligne in enumerate(lignes):
        out += texte(
            x, y + i * taille * interligne, ligne.upper() if da == "a" else ligne,
            famille=police(da, "display"), taille=taille, graisse=800, fill=c["ink"], ancre=ancre,
            espacement=taille * 0.01 if da == "a" else -taille * 0.01,
        )
    return out


def prix(da: str, x: float, y: float, taille: float, ancre: str = "start", valeur: str = "{{PRIX_VALIDE}}") -> str:
    """Prix public CHF — doit être le prix validé par le moteur au moment de publier."""
    c = couleurs(da)
    return texte(x, y, f"CHF {valeur}", famille=police(da, "price"), taille=taille, graisse=600 if da == "a" else 700, fill=c["ink"], ancre=ancre, ident="PRIX")


def ligne_texte(da: str, x: float, y: float, contenu: str, taille: float, muted: bool = True, graisse: int = 400, ancre: str = "start") -> str:
    c = couleurs(da)
    return texte(x, y, contenu, famille=police(da, "text"), taille=taille, graisse=graisse, fill=c["ink-muted" if muted else "ink"], ancre=ancre)


def deco(da: str, w: float, h: float, cx: float | None = None, cy: float = 150.0) -> str:
    """Motif propre à la direction : barre-quai (A) ou carte inclinée en contour (B)."""
    c = couleurs(da)
    if da == "a":
        return f'  <rect id="BARRE_QUAI" x="0" y="{num(h - 16)}" width="{num(w)}" height="16" fill="{c["accent"]}"/>\n'
    cx = w - 120 if cx is None else cx
    p = Pen()
    p.card(cx, cy, 150, 210, 18, 12)
    p.card(cx, cy, 126, 186, 8, 12, reverse=True)
    return f'  <g id="CARTES_DECO">\n    <path fill="{c["accent"]}" d="{"".join(p.main)}"/>\n  </g>\n'


# ---------------------------------------------------------------------------
# Templates réseaux sociaux
# ---------------------------------------------------------------------------
W = 1080.0
M = 72.0
DESC_SOCIAL = (
    "Template FICTIF à compléter. Remplacer ZONE_PHOTO par une photo réelle du produit (langue FR visible). "
    "Les {{CHAMPS}} viennent du catalogue validé ; le prix doit être le prix validé au moment de la publication. "
    "Aucune donnée interne (voir README DA). Zones sûres : social/guides/."
)


def couverture(da: str, h: float) -> str:
    """Couverture produit « nouveau en stock local » (1:1, 4:5 ou 9:16)."""
    haut = 250.0 if h == 1920 else M
    bas = h - (340.0 if h == 1920 else M)
    corps = fond(da, W, h)
    if da == "b":
        corps += deco(da, W, h)
    corps += logo_inline(da, M, haut, 46)
    # Bloc bas : badges, titre, prix, mention TVA, pied (de bas en haut).
    t_titre = 64.0 if h == 1080 else 72.0
    y_pied = bas
    y_mention = y_pied - 44
    y_prix = y_mention - 46
    y_titre2 = y_prix - 74
    y_titre1 = y_titre2 - t_titre * 1.05
    y_badges = y_titre1 - t_titre - 46
    corps += zone_photo(da, M, haut + 46 + 40, W - 2 * M, y_badges - 36 - (haut + 46 + 40), "Boîte FR, face avant, fond neutre, lumière du jour")
    corps += badges(da, M, y_badges, ["fr", "local", "new"], 26)
    corps += titre(da, M, y_titre1, ["Display", "{{EXTENSION}}"] if da == "a" else ["display", "{{extension}}"], t_titre)
    corps += prix(da, M, y_prix, 56)
    corps += ligne_texte(da, M, y_mention, "{{MENTION_TVA}} · frais de livraison affichés avant paiement", 24)
    corps += ligne_texte(da, M, y_pied, "Expédié depuis la Suisse · {{SITE}}", 28, muted=False, graisse=500)
    if da == "a":
        corps += deco(da, W, h)
    nom = {1080: "1x1", 1350: "4x5", 1920: "9x16"}[int(h)]
    return svg_doc(W, h, f"Couverture {nom} — direction {da.upper()} — {NOM}", DESC_SOCIAL, corps)


def story(da: str) -> str:
    """Story 9:16 « nouveau en stock local » avec zone sticker lien."""
    h = 1920.0
    c = couleurs(da)
    corps = fond(da, W, h)
    if da == "b":
        corps += deco(da, W, h)
    lw = largeur_logo(da, 44)
    corps += logo_inline(da, (W - lw) / 2, 250, 44)
    corps += titre(da, W / 2, 400, ["Nouveau en", "stock local"], 84, ancre="middle")
    corps += zone_photo(da, M, 520, W - 2 * M, 640, "Boîte FR, face avant + côté avec la mention de langue")
    corps += badges(da, M, 1196, ["fr", "local"], 28)
    corps += titre(da, M, 1318, ["Display {{EXTENSION}}"] if da == "a" else ["display {{extension}}"], 54)
    corps += prix(da, M, 1394, 56)
    corps += ligne_texte(da, M, 1446, "Expédition depuis la Suisse sous {{DELAI_EXPEDITION}}", 28, muted=False)
    corps += ligne_texte(da, M, 1488, "Limite : {{LIMITE_PAR_CLIENT}} · {{MENTION_TVA}}", 28)
    rx = 6 if da == "a" else 40
    corps += (
        f'  <g id="ZONE_STICKER_LIEN">\n    <rect x="{num(W / 2 - 260)}" y="1510" width="520" height="62" rx="{rx}" fill="none" '
        f'stroke="{c["line-strong"]}" stroke-width="3" stroke-dasharray="10 8"/>\n'
        + "  " + ligne_texte(da, W / 2, 1550, "Zone sticker lien (ajouté dans l'app)", 24, ancre="middle")
        + "  </g>\n"
    )
    if da == "a":
        corps += deco(da, W, h)
    return svg_doc(W, h, f"Story 9x16 — nouveau stock local — direction {da.upper()} — {NOM}", DESC_SOCIAL, corps)


def _pagination(da: str, h: float, n: int) -> str:
    return ligne_texte(da, W - M, M + 30, f"{n}/3", 30, muted=False, graisse=700, ancre="end")


def carrousel(da: str, h: float, n: int) -> str:
    """Carrousel éducatif « ETB ou display ? », 3 slides (4:5 ou 1:1)."""
    c = couleurs(da)
    carre = h == 1080
    corps = fond(da, W, h)
    if da == "b" and n != 2:
        corps += deco(da, W, h, cx=W + 20, cy=h * 0.5)
    corps += _pagination(da, h, n)
    if n == 1:
        corps += logo_inline(da, M, M, 40)
        t = 96.0 if not carre else 84.0
        y0 = 250.0 if not carre else 220.0
        corps += titre(da, M, y0, ["ETB ou", "display ?"], t)
        corps += ligne_texte(da, M, y0 + t * 1.05 + 66, "Ce qui change vraiment avant d'acheter", 34, muted=False, graisse=500)
        ph_y = y0 + t * 1.05 + 120
        ph_h = h - ph_y - M - 60
        gw = (W - 2 * M - 24) / 2
        corps += zone_photo(da, M, ph_y, gw, ph_h, "ETB FR, face avant", "ZONE_PHOTO_1")
        corps += zone_photo(da, M + gw + 24, ph_y, gw, ph_h, "Display FR, face avant", "ZONE_PHOTO_2")
        corps += ligne_texte(da, W - M, h - M, "Glissez →", 30, muted=False, graisse=700, ancre="end")
    elif n == 2:
        corps += titre(da, M, M + 110, ["La différence"] if da == "a" else ["la différence"], 72 if not carre else 64)
        rangs = [
            ("Pour qui", ["Débuter,", "offrir"], ["Collectionner", "une extension"]),
            ("Dans la boîte", ["Boosters +", "accessoires de jeu"], ["Boosters scellés", "uniquement"]),
            ("À vérifier", ["Contenu exact :", "voir la fiche"], ["Nb de boosters :", "voir la fiche"]),
        ]
        y = M + 200 if not carre else M + 170
        col_x = [M, M + 250, M + 250 + (W - 2 * M - 250) / 2]
        rh = 250.0 if not carre else 190.0
        tl = 32.0 if not carre else 30.0
        for i, e in enumerate(("", "ETB", "Display")):
            if e:
                corps += texte(col_x[i], y, e.upper() if da == "a" else e, famille=police(da, "display"), taille=44, graisse=800, fill=c["ink"])
        y += 30
        for lib, etb, disp in rangs:
            corps += f'  <rect x="{num(M)}" y="{num(y)}" width="{num(W - 2 * M)}" height="3" fill="{c["ink"] if da == "a" else c["line-strong"]}"/>\n'
            corps += ligne_texte(da, col_x[0], y + 62, lib, tl, muted=False, graisse=700)
            for j, lignes_ in ((1, etb), (2, disp)):
                for k, contenu in enumerate(lignes_):
                    corps += ligne_texte(da, col_x[j], y + 62 + k * tl * 1.35, contenu, tl, muted=False)
            y += rh
        corps += ligne_texte(da, M, h - M - (40 if da == "a" else 0), "Les contenus varient selon l'extension : la fiche produit fait foi.", 28)
    else:
        t = 80.0 if not carre else 68.0
        corps += titre(da, M, M + 130, ["Avant d'acheter,", "vérifiez :"], t)
        items = ["Langue : FR", "Extension exacte", "Format et contenu", "Stock local ou précommande"]
        y = M + 130 + t * 1.05 + 110
        pas = 92.0 if not carre else 76.0
        for it in items:
            if da == "a":
                corps += f'  <rect x="{num(M)}" y="{num(y - 30)}" width="34" height="34" fill="none" stroke="{c["ink"]}" stroke-width="4"/>\n'
            else:
                corps += f'  <rect x="{num(M)}" y="{num(y - 32)}" width="38" height="38" rx="10" fill="{c["accent"]}"/>\n'
            corps += ligne_texte(da, M + 60, y, it, 40, muted=False, graisse=600)
            y += pas
        corps += ligne_texte(da, M, y + 30, "Stock réel affiché · prix en CHF", 32, muted=False, graisse=500)
        corps += ligne_texte(da, M, y + 76, "{{SITE}}", 32, muted=False, graisse=700)
        corps += logo_inline(da, M, h - M - 40 - (24 if da == "a" else 0), 40)
    if da == "a":
        corps += deco(da, W, h)
    nom = "1x1" if carre else "4x5"
    return svg_doc(W, h, f"Carrousel {nom} — slide {n}/3 — direction {da.upper()} — {NOM}", DESC_SOCIAL, corps)


def guide_zones(h: float) -> str:
    """Zones sûres indicatives (à vérifier sur chaque plateforme lors de la production)."""
    nom = {1080: "1x1", 1350: "4x5", 1920: "9x16"}[int(h)]
    corps = f'  <rect width="{num(W)}" height="{num(h)}" fill="#FFFFFF"/>\n'
    rouge = "#B42318"
    if h == 1920:
        corps += f'  <rect width="{num(W)}" height="250" fill="{rouge}" fill-opacity="0.18"/>\n'
        corps += f'  <rect y="1580" width="{num(W)}" height="340" fill="{rouge}" fill-opacity="0.18"/>\n'
        corps += texte(W / 2, 140, "Réservé interface (≈ 250 px)", famille="Arial, sans-serif", taille=34, graisse=700, fill="#111111", ancre="middle")
        corps += texte(W / 2, 1760, "Réservé interface / légende (≈ 340 px)", famille="Arial, sans-serif", taille=34, graisse=700, fill="#111111", ancre="middle")
        safe = (64.0, 250.0, W - 128, 1330.0)
    elif h == 1350:
        corps += f'  <rect width="34" height="{num(h)}" fill="{rouge}" fill-opacity="0.18"/>\n'
        corps += f'  <rect x="{num(W - 34)}" width="34" height="{num(h)}" fill="{rouge}" fill-opacity="0.18"/>\n'
        corps += texte(W / 2, 120, "Bords latéraux possiblement rognés dans la grille du profil (≈ 3:4)", famille="Arial, sans-serif", taille=28, graisse=700, fill="#111111", ancre="middle")
        safe = (72.0, 72.0, W - 144, h - 144)
    else:
        safe = (64.0, 64.0, W - 128, h - 128)
    x, y, w, hh = safe
    corps += f'  <rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(hh)}" fill="none" stroke="#111111" stroke-width="4" stroke-dasharray="16 10"/>\n'
    corps += texte(W / 2, h / 2, f"Zone sûre indicative {nom}", famille="Arial, sans-serif", taille=44, graisse=700, fill="#111111", ancre="middle")
    corps += texte(W / 2, h / 2 + 60, "À revérifier sur chaque plateforme au moment de produire (BP §8)", famille="Arial, sans-serif", taille=28, fill="#111111", ancre="middle")
    return svg_doc(W, h, f"Guide zones sûres {nom}", "Calque guide, ne pas publier. Valeurs indicatives au 4 octobre 2026.", corps)


def fichiers_social() -> dict[str, str]:
    out: dict[str, str] = {}
    for da in DIRECTIONS:
        out[f"social/{da}/couverture-1x1.svg"] = couverture(da, 1080)
        out[f"social/{da}/couverture-4x5.svg"] = couverture(da, 1350)
        out[f"social/{da}/couverture-9x16.svg"] = couverture(da, 1920)
        out[f"social/{da}/story-9x16-nouveau-stock.svg"] = story(da)
        for n in (1, 2, 3):
            out[f"social/{da}/carrousel-4x5-{n}.svg"] = carrousel(da, 1350, n)
            out[f"social/{da}/carrousel-1x1-{n}.svg"] = carrousel(da, 1080, n)
    for h in (1080, 1350, 1920):
        nom = {1080: "1x1", 1350: "4x5", 1920: "9x16"}[h]
        out[f"social/guides/zones-sures-{nom}.svg"] = guide_zones(float(h))
    return out


# ---------------------------------------------------------------------------
# Packaging imprimable (unités : mm)
# ---------------------------------------------------------------------------
DESC_PRINT = (
    "Fichier d'impression en millimètres. Fond perdu inclus (voir NOTE_CHIFFRAGE.md). "
    "Le calque DECOUPE_ne_pas_imprimer indique la coupe. Convertir les textes en contours et "
    "vérifier le profil couleur demandé par l'imprimeur avant envoi (BAT obligatoire)."
)


def _decoupe(contenu: str) -> str:
    return f'  <g id="DECOUPE_ne_pas_imprimer" fill="none" stroke="#FF00FF" stroke-width="0.15">\n    {contenu}\n  </g>\n'


def sticker(da: str) -> str:
    """Sticker rond Ø 50 mm (+ 2 mm de fond perdu)."""
    c = couleurs(da)
    corps = f'  <circle id="FOND_PERDU" cx="27" cy="27" r="27" fill="{c["accent"]}"/>\n'
    if da == "a":
        essai = _trace(dessin_a_empile)
        s = 30 / (essai.bbox[2] - essai.bbox[0])
        p, w, h = _recaler(dessin_a_empile, s=s, ox=27 - 15, oy=0)
        dy = 24.5 - h / 2
        p, w, h = _recaler(dessin_a_empile, s=s, ox=27 - w / 2, oy=dy)
        corps += chemins([(c["ink"], p.main + p.accent)])
        corps += texte(27, dy + h + 6.2, "MERCI !", famille=police(da, "display"), taille=4.6, graisse=800, fill=c["ink"], ancre="middle", espacement=0.3)
    else:
        essai = _trace(dessin_b_empile)
        s = 32 / (essai.bbox[2] - essai.bbox[0])
        _, w, h = _recaler(dessin_b_empile, s=s)
        dy = 24 - h / 2
        p, w, h = _recaler(dessin_b_empile, s=s, ox=27 - w / 2, oy=dy)
        corps += chemins([("#FFFFFF", p.main), (c["ink"], p.accent)])
        corps += texte(27, dy + h + 6.4, "merci !", famille=police(da, "display"), taille=4.8, graisse=800, fill="#FFFFFF", ancre="middle")
    corps += _decoupe('<circle cx="27" cy="27" r="25"/>')
    return svg_doc(54, 54, f"Sticker rond Ø 50 mm — direction {da.upper()} — {NOM}", DESC_PRINT, corps, "mm")


A6 = (111.0, 154.0)  # 105 × 148 mm + 3 mm de fond perdu


def carte_recto(da: str) -> str:
    """Carte de remerciement A6, recto."""
    c = couleurs(da)
    w, h = A6
    corps = f'  <rect id="FOND_PERDU" width="{num(w)}" height="{num(h)}" fill="{c["bg"]}"/>\n'
    if da == "a":
        essai = _trace(dessin_a_empile)
        s = 52 / (essai.bbox[2] - essai.bbox[0])
        p, lw, lh = _recaler(dessin_a_empile, s=s, ox=11, oy=14)
        corps += chemins([(c["ink"], p.main), (c["accent"], p.accent)])
        y = 14 + lh + 34
        for i, contenu in enumerate(["MERCI POUR", "VOTRE", "COMMANDE."]):
            corps += texte(11, y + i * 10.6, contenu, famille=police(da, "display"), taille=10.4, graisse=800, fill=c["ink"])
        corps += texte(11, y + 3 * 10.6 + 8, "Préparée et contrôlée à la main en Suisse.", famille=police(da, "text"), taille=3.6, fill=c["ink-muted"])
        corps += f'  <rect id="BARRE_QUAI" x="0" y="{num(h - 17)}" width="{num(w)}" height="17" fill="{c["accent"]}"/>\n'
        corps += texte(11, h - 8, "{{SITE}}", famille=police(da, "price"), taille=3.8, graisse=600, fill=c["on-accent"])
    else:
        dec = Pen()
        dec.card(84, 30, 34, 48, 4, 10)
        dec.card(84, 30, 28, 42, 2, 10, reverse=True)
        corps += f'  <path fill="{c["accent"]}" d="{"".join(dec.main)}"/>\n'
        essai = _trace(dessin_b_empile)
        s = 52 / (essai.bbox[2] - essai.bbox[0])
        p, lw, lh = _recaler(dessin_b_empile, s=s, ox=11, oy=16)
        corps += chemins([(c["ink"], p.main), (c["accent"], p.accent)])
        y = 16 + lh + 34
        for i, contenu in enumerate(["merci pour", "votre commande."]):
            corps += texte(11, y + i * 10.8, contenu, famille=police(da, "display"), taille=10.2, graisse=800, fill=c["ink"], espacement=-0.1)
        corps += texte(11, y + 2 * 10.8 + 6, "Préparée et contrôlée à la main en Suisse.", famille=police(da, "text"), taille=3.6, fill=c["ink-muted"])
        corps += f'  <rect x="11" y="{num(h - 22)}" width="{num(w - 22)}" height="10" rx="5" fill="{c["accent"]}"/>\n'
        corps += texte(w / 2, h - 15.6, "{{SITE}}", famille=police(da, "price"), taille=3.8, graisse=700, fill=c["on-accent"], ancre="middle")
    corps += _decoupe(f'<rect x="3" y="3" width="{num(w - 6)}" height="{num(h - 6)}"/>')
    return svg_doc(w, h, f"Carte de remerciement A6 recto — direction {da.upper()} — {NOM}", DESC_PRINT, corps, "mm")


def carte_verso(da: str) -> str:
    """Carte de remerciement A6, verso (informations pratiques, à valider)."""
    c = couleurs(da)
    w, h = A6
    tf, df = police(da, "text"), police(da, "display")
    corps = f'  <rect id="FOND_PERDU" width="{num(w)}" height="{num(h)}" fill="{c["surface"]}"/>\n'
    x = 11.0
    y = 22.0
    titre_ = "TOUT EST CONFORME ?" if da == "a" else "tout est conforme ?"
    corps += texte(x, y, titre_, famille=df, taille=6.4, graisse=800, fill=c["ink"])
    y += 9
    corps += texte(x, y, "À réception, vérifiez :", famille=tf, taille=3.8, graisse=600, fill=c["ink"])
    y += 5.6
    for contenu in ["la langue (FR) et l'extension", "le format et la quantité", "l'emballage scellé intact"]:
        corps += f'  <rect x="{num(x)}" y="{num(y - 2.7)}" width="2.8" height="2.8" rx="{0.6 if da == "b" else 0}" fill="none" stroke="{c["ink"]}" stroke-width="0.3"/>\n'
        corps += texte(x + 4.2, y, contenu, famille=tf, taille=3.8, fill=c["ink"])
        y += 5.6
    y += 4
    titre2 = "UN SOUCI ?" if da == "a" else "un souci ?"
    corps += texte(x, y, titre2, famille=df, taille=6.4, graisse=800, fill=c["ink"])
    y += 8
    for contenu in [
        "Écrivez-nous sous {{DELAI_SIGNALEMENT}}",
        "avec votre n° de commande et une photo :",
        "{{EMAIL_SUPPORT}}",
        "Retours : {{URL_RETOURS}}",
    ]:
        gras = contenu.startswith("{{EMAIL")
        corps += texte(x, y, contenu, famille=police(da, "price") if gras else tf, taille=3.8, graisse=600 if gras else 400, fill=c["ink"])
        y += 5.6
    y += 4
    titre3 = "PROTÉGER VOS CARTES" if da == "a" else "protéger vos cartes"
    corps += texte(x, y, titre3, famille=df, taille=6.4, graisse=800, fill=c["ink"])
    y += 8
    for contenu in ["Pochettes de protection + classeur,", "à l'abri de l'humidité et du soleil."]:
        corps += texte(x, y, contenu, famille=tf, taille=3.8, fill=c["ink"])
        y += 5.6
    corps += f'  <rect x="{num(x)}" y="{num(h - 33)}" width="{num(w - 22)}" height="0.3" fill="{c["line-strong"]}"/>\n'
    corps += texte(x, h - 27, "Commande n° ____________", famille=police(da, "price"), taille=3.6, graisse=600, fill=c["ink"])
    corps += texte(x, h - 20, "Boutique indépendante, sans lien officiel avec les éditeurs", famille=tf, taille=2.9, fill=c["ink-muted"])
    corps += texte(x, h - 16.2, "des jeux vendus. {{RAISON_SOCIALE}} · {{ADRESSE}}", famille=tf, taille=2.9, fill=c["ink-muted"])
    if da == "a":
        corps += f'  <rect x="0" y="{num(h - 9)}" width="{num(w)}" height="9" fill="{c["accent"]}"/>\n'
    corps += _decoupe(f'<rect x="3" y="3" width="{num(w - 6)}" height="{num(h - 6)}"/>')
    return svg_doc(w, h, f"Carte de remerciement A6 verso — direction {da.upper()} — {NOM}", DESC_PRINT, corps, "mm")


def repere_commande(da: str) -> str:
    """Étiquette d'identification de commande 70 × 37 mm (planche A4 de 24)."""
    c = {k: v for k, v in couleurs(da).items()}
    w, h = 70.0, 37.0
    tf = police(da, "text")
    corps = f'  <rect width="{num(w)}" height="{num(h)}" fill="#FFFFFF"/>\n'
    if da == "a":
        mono = dessin_a_monogramme(Pen(ox=3, oy=3, s=8 / 120), c["ink"], "#FFFFFF", c["accent"])
    else:
        mono = dessin_b_monogramme(Pen(ox=2.5, oy=2.5, s=9 / 120), c["ink"], c["accent"], "#FFFFFF")
    corps += chemins(mono)
    corps += texte(13.5, 6.4, "COMMANDE N°" if da == "a" else "commande n°", famille=police(da, "display"), taille=3.2, graisse=800, fill=c["ink"])
    corps += texte(13.5, 10.6, "{{N_COMMANDE}}", famille=police(da, "price"), taille=3.0, graisse=600, fill=c["ink"], ident="NUMERO_COMMANDE")
    corps += f'  <rect x="49" y="3" width="18" height="9.5" rx="{1 if da == "b" else 0}" fill="none" stroke="{c["line-strong"]}" stroke-width="0.25" stroke-dasharray="1 0.6"/>\n'
    corps += texte(58, 8.6, "code-barres", famille=tf, taille=2.2, fill=c["ink-muted"], ancre="middle")
    corps += f'  <rect x="3" y="14.5" width="64" height="0.25" fill="{c["line-strong"]}"/>\n'
    cases = [("Langue FR", 3.0, 19.5), ("Scellé intact", 35.0, 19.5), ("Quantité conforme", 3.0, 24.5), ("Carte merci", 35.0, 24.5)]
    for lib, x, y in cases:
        corps += f'  <rect x="{num(x)}" y="{num(y - 2.6)}" width="3" height="3" rx="{0.6 if da == "b" else 0}" fill="none" stroke="{c["ink"]}" stroke-width="0.3"/>\n'
        corps += texte(x + 4.4, y, lib, famille=tf, taille=2.6, graisse=500, fill=c["ink"])
    corps += texte(3, 31, "Préparée le ___.___.______  par ______", famille=tf, taille=2.5, fill=c["ink"])
    corps += texte(3, 34.6, "Contrôlée par ______  Colis n° ______", famille=tf, taille=2.5, fill=c["ink"])
    if da == "a":
        corps += f'  <rect x="64" y="17" width="3" height="18" fill="{c["accent"]}"/>\n'
    corps += _decoupe(f'<rect x="0" y="0" width="{num(w)}" height="{num(h)}" rx="0"/>')
    return svg_doc(w, h, f"Repère d'identification de commande 70 × 37 mm — direction {da.upper()} — {NOM}", DESC_PRINT, corps, "mm")


def fichiers_packaging() -> dict[str, str]:
    out: dict[str, str] = {}
    for da in DIRECTIONS:
        out[f"packaging/{da}/sticker-rond-50mm.svg"] = sticker(da)
        out[f"packaging/{da}/carte-merci-a6-recto.svg"] = carte_recto(da)
        out[f"packaging/{da}/carte-merci-a6-verso.svg"] = carte_verso(da)
        out[f"packaging/{da}/repere-commande-70x37mm.svg"] = repere_commande(da)
    return out


# ---------------------------------------------------------------------------
# Email transactionnel (HTML email-safe : tableaux, styles en ligne)
# ---------------------------------------------------------------------------
LIGNES_EMAIL = [
    # (désignation, statut, détail de statut, quantité, prix unitaire, total) — FICTIF
    ("Display — Extension exemple — FR", "local", "Expédition sous {{DELAI_EXPEDITION}}", 1, "209.90", "209.90"),
    ("Pochettes de protection ×100 (exemple)", "local", "Expédition sous {{DELAI_EXPEDITION}}", 2, "9.90", "19.80"),
    ("Coffret — Extension exemple 2 — FR", "preorder", "Sortie prévue le {{DATE_SORTIE}} · expédiée à part", 1, "59.90", "59.90"),
]
SOUS_TOTAL_EMAIL = "289.60"


def email(da: str) -> str:
    """Confirmation de commande — gabarit transactionnel (données FICTIVES)."""
    c = couleurs(da)
    ff = "Arial, Helvetica, sans-serif"
    fm = "'Courier New', Courier, monospace" if da == "a" else ff
    titre_ = "Merci, votre commande est confirmée" if da == "b" else "MERCI, VOTRE COMMANDE EST CONFIRMÉE"
    radius = "0" if da == "a" else "12px"
    btn_bg, btn_fg = (c["ink"], c["on-ink"]) if da == "a" else (c["accent"], c["on-accent"])
    lignes = ""
    for nom_, statut, detail, qte, pu, tot in LIGNES_EMAIL:
        bg, fg = (c[STATUTS[statut][0]], c[STATUTS[statut][1]])
        lib = LIBELLES[da][statut]
        lignes += f"""
              <tr>
                <td style="padding:14px 0;border-top:1px solid {c['line']};font-family:{ff};font-size:15px;line-height:21px;color:{c['ink']};word-break:break-word;">
                  <strong>{escape(nom_)}</strong> <span style="font-size:13px;color:{c['ink-muted']};">(FICTIF)</span><br>
                  <span style="display:inline-block;margin-top:6px;padding:2px 8px;border-radius:{'3px' if da == 'a' else '999px'};background:{bg};color:{fg};font-size:12px;font-weight:bold;">{escape(lib)}</span>
                  <span style="font-size:13px;color:{c['ink-muted']};">&nbsp;{escape(detail)}</span>
                </td>
                <td align="right" valign="top" style="padding:14px 0 14px 12px;border-top:1px solid {c['line']};font-family:{fm};font-size:15px;line-height:21px;color:{c['ink']};white-space:nowrap;">
                  {qte} × {pu}<br><strong>CHF {tot}</strong>
                </td>
              </tr>"""
    return f"""<!DOCTYPE html>
<html lang="fr-CH">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>Confirmation de commande {{{{NUMERO_COMMANDE}}}} — {NOM} (direction {da.upper()})</title>
  <!--
    GABARIT EMAIL TRANSACTIONNEL — direction {da.upper()} — FICHIER GÉNÉRÉ par tools/generer_da.py
    Données d'exemple FICTIVES. Les {{{{CHAMPS}}}} sont à relier aux variables Liquid des notifications
    Shopify lors de l'intégration (à vérifier dans la documentation Shopify en vigueur).
    Règles : afficher exactement ce qui a été acheté ; aucune donnée interne (voir README DA, règle n° 1) ;
    statut de chaque ligne explicite (stock local / précommande) ; pas de contenu promotionnel.
    Logo : PNG hébergé (Gmail n'affiche pas les SVG) — exporter logo/png/logo-{da}-email.png.
    Bloc TVA : n'afficher la ligne TVA que si l'entité est assujettie (décision fiduciaire).
  -->
</head>
<body style="margin:0;padding:0;background:{c['bg']};">
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">Commande {{{{NUMERO_COMMANDE}}}} confirmée : récapitulatif, statut de chaque article et suivi.</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{c['bg']};">
    <tr>
      <td align="center" style="padding:16px 8px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:{c['surface']};border-radius:{radius};">
          <tr>
            <td style="padding:24px 20px 8px 20px;">
              <img src="{{{{URL_LOGO_PNG}}}}" width="{200 if da == 'a' else 220}" alt="{escape(NOM)}" style="display:block;border:0;outline:none;text-decoration:none;height:auto;font-family:{ff};font-size:18px;font-weight:bold;color:{c['ink']};">
            </td>
          </tr>
          {"<tr><td style='padding:0 20px;'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'><tr><td height='6' style='height:6px;line-height:6px;font-size:0;background:" + c['accent'] + ";'>&nbsp;</td></tr></table></td></tr>" if da == "a" else ""}
          <tr>
            <td style="padding:20px 20px 0 20px;font-family:{ff};">
              <h1 style="margin:0 0 8px 0;font-size:22px;line-height:28px;font-weight:bold;word-break:break-word;color:{c['ink']};">{titre_}</h1>
              <p style="margin:0;font-size:15px;line-height:22px;color:{c['ink']};">Bonjour {{{{PRENOM}}}}, nous avons bien reçu votre paiement. Voici exactement ce que vous avez commandé.</p>
              <p style="margin:12px 0 0 0;font-family:{fm};font-size:15px;line-height:22px;color:{c['ink']};word-break:break-word;"><strong>Commande {{{{NUMERO_COMMANDE}}}}</strong> · {{{{DATE_COMMANDE}}}}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px 0 20px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{lignes}
                <tr>
                  <td style="padding:12px 0 4px 0;border-top:2px solid {c['ink']};font-family:{ff};font-size:15px;color:{c['ink']};">Sous-total articles</td>
                  <td align="right" style="padding:12px 0 4px 0;border-top:2px solid {c['ink']};font-family:{fm};font-size:15px;color:{c['ink']};">CHF {SOUS_TOTAL_EMAIL}</td>
                </tr>
                <tr>
                  <td style="padding:4px 0;font-family:{ff};font-size:15px;color:{c['ink']};">Livraison ({{{{MODE_LIVRAISON}}}})</td>
                  <td align="right" style="padding:4px 0;font-family:{fm};font-size:15px;color:{c['ink']};word-break:break-word;">CHF {{{{FRAIS_LIVRAISON}}}}</td>
                </tr>
                <tr>
                  <td style="padding:8px 0 4px 0;font-family:{ff};font-size:18px;font-weight:bold;color:{c['ink']};">Total payé</td>
                  <td align="right" style="padding:8px 0 4px 0;font-family:{fm};font-size:18px;font-weight:bold;color:{c['ink']};">CHF {{{{TOTAL_PAYE}}}}</td>
                </tr>
                <!-- SI ENTITÉ ASSUJETTIE À LA TVA (décision fiduciaire) -->
                <tr>
                  <td colspan="2" style="padding:0 0 4px 0;font-family:{ff};font-size:13px;color:{c['ink-muted']};">{{{{MENTION_TVA}}}}</td>
                </tr>
                <!-- FIN SI -->
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 20px 0 20px;font-family:{ff};font-size:14px;line-height:21px;color:{c['ink']};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{c['surface-alt']};border-radius:{radius};">
                <tr>
                  <td style="padding:16px;font-family:{ff};font-size:14px;line-height:21px;color:{c['ink']};word-break:break-word;">
                    <strong>Commande mixte :</strong> les articles en stock local partent dès qu'ils sont prêts ;
                    la précommande est expédiée séparément à réception de l'allocation, à la date annoncée ou dès qu'elle est confirmée.
                    Nous vous écrivons si une date change.<br><br>
                    <strong>Livraison :</strong> {{{{ADRESSE_LIVRAISON}}}} (Suisse uniquement)<br>
                    <strong>Paiement :</strong> {{{{MOYEN_PAIEMENT}}}}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="left" style="padding:24px 20px 8px 20px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="border-radius:{'4px' if da == 'a' else '999px'};background:{btn_bg};">
                    <a href="{{{{URL_SUIVI_COMMANDE}}}}" style="display:inline-block;padding:14px 22px;font-family:{ff};font-size:15px;font-weight:bold;color:{btn_fg};text-decoration:none;border-radius:{'4px' if da == 'a' else '999px'};">Voir ma commande</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px 24px 20px;font-family:{ff};font-size:13px;line-height:19px;color:{c['ink-muted']};word-break:break-word;">
              Une question ? Répondez à cet email ou écrivez à {{{{EMAIL_SUPPORT}}}} en indiquant votre numéro de commande.<br>
              Conditions de vente, livraison et retours : <a href="{{{{URL_CGV}}}}" style="color:{c['accent-text']};">{{{{URL_CGV}}}}</a><br><br>
              {{{{RAISON_SOCIALE}}}} · {{{{ADRESSE_POSTALE}}}} · {{{{NUMERO_IDE}}}}<br>
              Boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus.<br>
              Vous recevez cet email parce que vous avez passé commande ; il ne contient aucune publicité.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Tableaux de contrastes injectés dans DIRECTION_A.md / DIRECTION_B.md
# ---------------------------------------------------------------------------
MARQUE_DEBUT = "<!-- CONTRASTES:DEBUT (généré par tools/generer_da.py, ne pas éditer) -->"
MARQUE_FIN = "<!-- CONTRASTES:FIN -->"


def tableau_contrastes_md(da: str) -> str:
    """Tableau Markdown des contrastes WCAG (ratios tronqués à 2 décimales)."""
    from contraste import niveau, ratio, ratio_affiche

    lignes = [
        "| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, lib in (("light", "Clair"), ("dark", "Sombre")):
        cols = couleurs(da, mode)
        for paire in TOKENS["contrastPairs"]:
            fg, bg = cols[paire["fg"]], cols[paire["bg"]]
            r = ratio(fg, bg)
            niv = niveau(r) if paire["min"] >= 4.5 else ("UI ≥ 3:1" if r >= 3 else "insuffisant")
            lignes.append(
                f"| {lib} | {paire['usage']} | `{fg}` {paire['fg']} | `{bg}` {paire['bg']} | "
                f"**{ratio_affiche(fg, bg)}:1** | {paire['min']} | {niv} |"
            )
    return "\n".join(lignes)


def paires_ambiance() -> list[dict]:
    """Paires contrôlées pour une ambiance : paires communes + paires propres aux ambiances."""
    return list(TOKENS["contrastPairs"]) + list(TOKENS.get("ambianceContrastPairs", []))


def tableau_contrastes_ambiance_md(nom: str) -> str:
    """Tableau Markdown des contrastes d'une ambiance (toujours sombre, ratios tronqués)."""
    from contraste import niveau, ratio, ratio_affiche

    lignes = [
        "| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |",
        "|---|---|---|---|---|---|---|",
    ]
    cols = couleurs_ambiance(nom)
    for paire in paires_ambiance():
        fg, bg = cols[paire["fg"]], cols[paire["bg"]]
        r = ratio(fg, bg)
        niv = niveau(r) if paire["min"] >= 4.5 else ("UI ≥ 3:1" if r >= 3 else "insuffisant")
        lignes.append(
            f"| Sombre | {paire['usage']} | `{fg}` {paire['fg']} | `{bg}` {paire['bg']} | "
            f"**{ratio_affiche(fg, bg)}:1** | {paire['min']} | {niv} |"
        )
    return "\n".join(lignes)


def _injecter(doc: Path, tableau: str) -> bool:
    if not doc.exists():
        return False
    texte_ = doc.read_text(encoding="utf-8")
    if MARQUE_DEBUT not in texte_ or MARQUE_FIN not in texte_:
        return False
    avant = texte_.split(MARQUE_DEBUT)[0]
    apres = texte_.split(MARQUE_FIN, 1)[1]
    nouveau = f"{avant}{MARQUE_DEBUT}\n{tableau}\n{MARQUE_FIN}{apres}"
    if nouveau != texte_:
        doc.write_text(nouveau, encoding="utf-8")
    return True


def injecter_tableaux() -> list[str]:
    """Remplace le bloc entre marqueurs dans DIRECTION_A/B.md (si présents)."""
    faits = []
    for da in DIRECTIONS:
        doc = RACINE / f"DIRECTION_{da.upper()}.md"
        if _injecter(doc, tableau_contrastes_md(da)):
            faits.append(doc.name)
    for nom in AMBIANCES:
        doc = RACINE / f"DIRECTION_{nom.upper()}.md"
        if _injecter(doc, tableau_contrastes_ambiance_md(nom)):
            faits.append(doc.name)
    return faits


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
def tous_les_fichiers() -> dict[str, str]:
    """Ensemble des fichiers texte générés {chemin relatif à docs/05-da: contenu}."""
    out = {"tokens/tokens.css": generer_css()}
    for nom in AMBIANCES:
        out[f"tokens/tokens-{nom}.css"] = generer_css_ambiance(nom)
    out.update(fichiers_logos())
    out.update(fichiers_social())
    out.update(fichiers_packaging())
    for da in DIRECTIONS:
        out[f"components/email-transactionnel-{da}.html"] = email(da)
    out["components/icones.svg"] = sprite_icones()
    from pages_html import pages  # import tardif : module de gabarits HTML volumineux

    out.update(pages())
    return out


PNG_EXPORTS = [
    # (source svg, sortie png, largeur px)
    ("logo/a/logo-a-principal.svg", "logo/png/logo-a-principal-1200.png", 1200),
    ("logo/a/logo-a-horizontal.svg", "logo/png/logo-a-email.png", 400),
    ("logo/a/logo-a-monogramme.svg", "logo/png/logo-a-monogramme-512.png", 512),
    ("logo/a/favicon.svg", "logo/png/favicon-a-32.png", 32),
    ("logo/a/favicon.svg", "logo/png/favicon-a-180.png", 180),
    ("logo/b/logo-b-principal.svg", "logo/png/logo-b-principal-1200.png", 1200),
    ("logo/b/logo-b-principal.svg", "logo/png/logo-b-email.png", 440),
    ("logo/b/logo-b-monogramme.svg", "logo/png/logo-b-monogramme-512.png", 512),
    ("logo/b/favicon.svg", "logo/png/favicon-b-32.png", 32),
    ("logo/b/favicon.svg", "logo/png/favicon-b-180.png", 180),
]


def exporter_png() -> list[str]:
    """Exports PNG (optionnel) ; nécessite cairosvg (outil local, hors moteur)."""
    import cairosvg  # type: ignore[import-not-found]

    faits = []
    (RACINE / "logo" / "png").mkdir(parents=True, exist_ok=True)
    for src, dst, largeur in PNG_EXPORTS:
        cairosvg.svg2png(url=str(RACINE / src), write_to=str(RACINE / dst), output_width=largeur)
        faits.append(dst)
    return faits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--png", action="store_true", help="exporter aussi les PNG de logos (cairosvg requis)")
    args = parser.parse_args(argv)
    fichiers = tous_les_fichiers()
    for rel, contenu in sorted(fichiers.items()):
        chemin = RACINE / rel
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    print(f"{len(fichiers)} fichiers générés dans {RACINE}")
    for nom_doc in injecter_tableaux():
        print(f"Tableau de contrastes injecté dans {nom_doc}")
    if args.png:
        print(f"{len(exporter_png())} PNG exportés")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
