"""Calcul de contraste WCAG 2.x (luminance relative sRGB).

Module sans dépendance, utilisé par le générateur et le vérificateur DA.
Les ratios affichés dans la documentation sont TRONQUÉS à 2 décimales
(jamais arrondis vers le haut) pour ne pas surévaluer un contraste limite.
"""

from __future__ import annotations

import math
import re

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

SEUIL_TEXTE = 4.5  # WCAG 1.4.3 AA, texte courant
SEUIL_GRAND_TEXTE = 3.0  # WCAG 1.4.3 AA, texte >= 24 px ou >= 18,66 px gras
SEUIL_UI = 3.0  # WCAG 1.4.11, composants d'interface et objets graphiques


def est_hex(valeur: str) -> bool:
    """Vrai si la valeur est une couleur hexadécimale #RRGGBB."""
    return bool(HEX_RE.match(valeur))


def _canal_lineaire(c8: int) -> float:
    c = c8 / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    """Luminance relative WCAG d'une couleur #RRGGBB."""
    if not est_hex(hex_color):
        raise ValueError(f"Couleur invalide : {hex_color!r}")
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _canal_lineaire(r) + 0.7152 * _canal_lineaire(g) + 0.0722 * _canal_lineaire(b)


def ratio(avant_plan: str, arriere_plan: str) -> float:
    """Ratio de contraste WCAG (1.0 à 21.0), symétrique."""
    la, lb = sorted((luminance(avant_plan), luminance(arriere_plan)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ratio_affiche(avant_plan: str, arriere_plan: str) -> str:
    """Ratio tronqué à 2 décimales, au format « 7.04 »."""
    r = math.floor(ratio(avant_plan, arriere_plan) * 100) / 100
    return f"{r:.2f}"


def niveau(r: float) -> str:
    """Niveau WCAG atteint pour du texte courant / grand texte."""
    if r >= 7.0:
        return "AAA"
    if r >= SEUIL_TEXTE:
        return "AA"
    if r >= SEUIL_GRAND_TEXTE:
        return "AA grand texte / UI"
    return "insuffisant"
