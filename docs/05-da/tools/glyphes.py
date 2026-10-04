"""Lettrage original des logos « Quai des Cartes » (nom de travail).

Chaque lettre est construite à la main à partir de primitives géométriques
(rectangles, polygones, couronnes d'ellipse, cercles, cartes arrondies).
Toutes les formes sont des CONTOURS PLEINS orientés dans le sens horaire
(à l'écran) : leur union s'affiche correctement avec la règle de
remplissage « nonzero », sans police ni trait (prêt pour l'imprimeur).

- Direction A « Quai » : capitales géométriques, graisse 18, hauteur 100.
- Direction B « Pochette » : bas-de-casse arrondies, graisse 18,
  hauteur d'x 76 (y 24 → 100), point du « i » en forme de carte inclinée.

Aucun élément n'est dérivé d'un logo, d'une police ou d'un symbole Pokémon.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field


def num(v: float) -> str:
    """Formate un nombre SVG (2 décimales max, sans zéro inutile)."""
    s = f"{round(v, 2):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _aire_signee(pts: list[tuple[float, float]]) -> float:
    """Somme de Gauss ; > 0 = sens horaire à l'écran (axe y vers le bas)."""
    total = 0.0
    for i, (x0, y0) in enumerate(pts):
        x1, y1 = pts[(i + 1) % len(pts)]
        total += x0 * y1 - x1 * y0
    return total


@dataclass
class Pen:
    """Traceur : coordonnées locales → absolues (translation + échelle).

    Deux calques : ``main`` (couleur du texte) et ``accent``.
    """

    ox: float = 0.0
    oy: float = 0.0
    s: float = 1.0
    main: list[str] = field(default_factory=list)
    accent: list[str] = field(default_factory=list)
    bbox: list[float] = field(default_factory=lambda: [math.inf, math.inf, -math.inf, -math.inf])

    # -- utilitaires -------------------------------------------------------
    def _p(self, x: float, y: float) -> str:
        return f"{num(self.ox + self.s * x)} {num(self.oy + self.s * y)}"

    def _out(self, d: str, layer: str) -> None:
        (self.accent if layer == "accent" else self.main).append(d)

    def _grow(self, x: float, y: float) -> None:
        """Étend la boîte englobante (coordonnées locales → absolues)."""
        ax, ay = self.ox + self.s * x, self.oy + self.s * y
        b = self.bbox
        b[0], b[1], b[2], b[3] = min(b[0], ax), min(b[1], ay), max(b[2], ax), max(b[3], ay)

    def _grow_arc(self, cx: float, cy: float, rx: float, ry: float, a0: float, a1: float) -> None:
        steps = max(2, int(abs(a1 - a0)))
        for k in range(steps + 1):
            self._grow(*self._pt(cx, cy, rx, ry, a0 + (a1 - a0) * k / steps))

    def _pt(self, cx: float, cy: float, rx: float, ry: float, deg: float) -> tuple[float, float]:
        a = math.radians(deg)
        return cx + rx * math.cos(a), cy + ry * math.sin(a)

    # -- primitives (toutes en sens horaire) -------------------------------
    def rect(self, x: float, y: float, w: float, h: float, layer: str = "main") -> None:
        """Rectangle plein."""
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], layer)

    def poly(self, pts: list[tuple[float, float]], layer: str = "main") -> None:
        """Polygone plein (orientation corrigée automatiquement)."""
        if _aire_signee(pts) < 0:
            pts = list(reversed(pts))
        for x, y in pts:
            self._grow(x, y)
        d = "M" + "L".join(self._p(x, y) for x, y in pts) + "Z"
        self._out(d, layer)

    def circle(self, cx: float, cy: float, r: float, layer: str = "main", reverse: bool = False) -> None:
        """Disque plein (ou trou si ``reverse``)."""
        self._grow_arc(cx, cy, r, r, 0, 360)
        rr = num(self.s * r)
        sweep = "0" if reverse else "1"
        d = (
            f"M{self._p(cx + r, cy)}A{rr} {rr} 0 1 {sweep} {self._p(cx - r, cy)}"
            f"A{rr} {rr} 0 1 {sweep} {self._p(cx + r, cy)}Z"
        )
        self._out(d, layer)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, layer: str = "main", reverse: bool = False) -> None:
        """Ellipse pleine (ou trou si ``reverse``)."""
        self._grow_arc(cx, cy, rx, ry, 0, 360)
        a, b = num(self.s * rx), num(self.s * ry)
        sweep = "0" if reverse else "1"
        d = (
            f"M{self._p(cx + rx, cy)}A{a} {b} 0 1 {sweep} {self._p(cx - rx, cy)}"
            f"A{a} {b} 0 1 {sweep} {self._p(cx + rx, cy)}Z"
        )
        self._out(d, layer)

    def ring(self, cx: float, cy: float, ro: float, ri: float, layer: str = "main") -> None:
        """Anneau complet : disque extérieur + trou intérieur."""
        self.circle(cx, cy, ro, layer)
        self.circle(cx, cy, ri, layer, reverse=True)

    def band(
        self,
        cx: float,
        cy: float,
        rxo: float,
        ryo: float,
        rxi: float,
        ryi: float,
        a0: float,
        a1: float,
        layer: str = "main",
    ) -> None:
        """Secteur de couronne elliptique de a0 à a1 (degrés, sens horaire)."""
        span = a1 - a0
        if not 0 < span < 360:
            raise ValueError("L'ouverture d'une couronne doit être comprise entre 0 et 360°")
        large = "1" if span > 180 else "0"
        self._grow_arc(cx, cy, rxo, ryo, a0, a1)
        self._grow_arc(cx, cy, rxi, ryi, a0, a1)
        o0 = self._pt(cx, cy, rxo, ryo, a0)
        o1 = self._pt(cx, cy, rxo, ryo, a1)
        i1 = self._pt(cx, cy, rxi, ryi, a1)
        i0 = self._pt(cx, cy, rxi, ryi, a0)
        d = (
            f"M{self._p(*o0)}A{num(self.s * rxo)} {num(self.s * ryo)} 0 {large} 1 {self._p(*o1)}"
            f"L{self._p(*i1)}A{num(self.s * rxi)} {num(self.s * ryi)} 0 {large} 0 {self._p(*i0)}Z"
        )
        self._out(d, layer)

    def card(
        self,
        cx: float,
        cy: float,
        w: float,
        h: float,
        r: float,
        deg: float = 0.0,
        layer: str = "main",
        reverse: bool = False,
    ) -> None:
        """Carte (rectangle à coins arrondis) centrée, tournée de ``deg``."""
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)

        def rot(x: float, y: float) -> tuple[float, float]:
            return cx + x * ca - y * sa, cy + x * sa + y * ca

        hw, hh = w / 2, h / 2
        for qx, qy, s0 in ((hw - r, -hh + r, 270), (hw - r, hh - r, 0), (-hw + r, hh - r, 90), (-hw + r, -hh + r, 180)):
            for k in range(91):
                ang = math.radians(s0 + k)
                self._grow(*rot(qx + r * math.cos(ang), qy + r * math.sin(ang)))
        # Points dans l'ordre horaire, arcs aux coins.
        seq = [
            ("M", (-hw + r, -hh)),
            ("L", (hw - r, -hh)),
            ("A", (hw, -hh + r)),
            ("L", (hw, hh - r)),
            ("A", (hw - r, hh)),
            ("L", (-hw + r, hh)),
            ("A", (-hw, hh - r)),
            ("L", (-hw, -hh + r)),
            ("A", (-hw + r, -hh)),
        ]
        if reverse:
            pts = [p for _, p in seq]
            kinds = [k for k, _ in seq]
            # Parcours inverse : on garde la nature (L/A) du segment parcouru.
            rev_pts = list(reversed(pts))
            rev_kinds = ["M"] + list(reversed(kinds[1:]))
            seq = list(zip(rev_kinds, rev_pts))
        rr = num(self.s * r)
        sweep = "0" if reverse else "1"
        d = ""
        for kind, (x, y) in seq:
            p = self._p(*rot(x, y))
            if kind == "M":
                d += f"M{p}"
            elif kind == "L":
                d += f"L{p}"
            else:
                d += f"A{rr} {rr} 0 0 {sweep} {p}"
        self._out(d + "Z", layer)


GlyphFn = Callable[[Pen], float]

# ---------------------------------------------------------------------------
# Direction A — capitales géométriques (graisse 18, hauteur de capitale 100)
# ---------------------------------------------------------------------------
W_A = 18.0


def a_Q(p: Pen) -> float:
    p.ring(50, 50, 50, 32)
    p.poly([(58, 64), (80, 64), (106, 100), (84, 100)])  # queue
    return 100


def a_U(p: Pen) -> float:
    p.rect(0, 0, W_A, 61)
    p.rect(60, 0, W_A, 61)
    p.band(39, 61, 39, 39, 21, 21, 0, 180)
    return 78


def a_A(p: Pen) -> float:
    width, t = 84.0, 19.0
    apex = width / 2 - t / 2
    p.poly([(0, 100), (apex, 0), (apex + t, 0), (t, 100)])
    p.poly([(width - t, 100), (apex, 0), (apex + t, 0), (width, 100)])
    y0 = 60.0
    start = apex * (100 - y0) / 100 + t / 2
    p.rect(start, y0, width - 2 * start, 17)
    return width


def a_I(p: Pen) -> float:
    p.rect(0, 0, W_A, 100)
    return W_A


def a_D(p: Pen) -> float:
    p.rect(0, 0, W_A, 100)
    p.rect(0, 0, 34, W_A)
    p.rect(0, 82, 34, W_A)
    p.band(34, 50, 50, 50, 32, 32, 270, 450)
    return 84


def a_E(p: Pen) -> float:
    p.rect(0, 0, W_A, 100)
    p.rect(0, 0, 62, W_A)
    p.rect(0, 41, 54, W_A)
    p.rect(0, 82, 62, W_A)
    return 62


def a_S(p: Pen) -> float:
    p.band(32, 29.5, 32, 29.5, 14, 11.5, 90, 330)
    p.band(32, 70.5, 32, 29.5, 14, 11.5, 270, 510)
    return 64


def a_C(p: Pen) -> float:
    p.band(46, 50, 46, 50, 28, 32, 45, 315)
    return 80


def a_R(p: Pen) -> float:
    p.rect(0, 0, W_A, 100)
    p.rect(0, 0, 30, W_A)
    p.rect(0, 50, 30, W_A)
    p.band(30, 34, 34, 34, 16, 16, 270, 450)
    p.poly([(30, 60), (50, 60), (70, 100), (50, 100)])  # jambe
    return 70


def a_T(p: Pen) -> float:
    p.rect(0, 0, 72, W_A)
    p.rect(27, 0, W_A, 100)
    return 72


GLYPHES_A: dict[str, GlyphFn] = {
    "Q": a_Q, "U": a_U, "A": a_A, "I": a_I, "D": a_D,
    "E": a_E, "S": a_S, "C": a_C, "R": a_R, "T": a_T,
}
KERN_A: dict[tuple[str, str], float] = {
    ("C", "A"): -6, ("T", "E"): -6, ("R", "T"): -4, ("U", "A"): -3, ("Q", "U"): -2, ("A", "I"): -2,
}
ESPACE_A = 42.0
INTERLETTRE_A = 10.0

# ---------------------------------------------------------------------------
# Direction B — bas-de-casse arrondies (graisse 18, hauteur d'x 76)
# Ligne d'x y=24, ligne de base y=100, ascendante y=0, descendante y=126.
# ---------------------------------------------------------------------------
R_B = 9.0  # demi-graisse = rayon des terminaisons rondes


def _stem(p: Pen, x: float, y0: float, y1: float) -> None:
    """Fût vertical à extrémités rondes, axe x, de y0 à y1 (centres)."""
    p.rect(x - R_B, y0, 2 * R_B, y1 - y0)
    p.circle(x, y0, R_B)
    p.circle(x, y1, R_B)


def _bowl(p: Pen) -> None:
    p.ring(38, 62, 38, 20)


def b_q(p: Pen) -> float:
    _bowl(p)
    _stem(p, 67, 33, 117)
    return 76


def b_a(p: Pen) -> float:
    _bowl(p)
    _stem(p, 67, 33, 91)
    return 76


def b_d(p: Pen) -> float:
    _bowl(p)
    _stem(p, 67, 9, 91)
    return 76


def b_u(p: Pen) -> float:
    p.rect(0, 33, 18, 29)
    p.circle(9, 33, R_B)
    p.band(38, 62, 38, 38, 20, 20, 0, 180)
    _stem(p, 67, 33, 91)
    return 76


def b_i(p: Pen) -> float:
    _stem(p, 9, 33, 91)
    p.card(9.5, 6, 16, 22, 3.5, -12, layer="accent")  # point = carte inclinée
    return 18


def b_c(p: Pen) -> float:
    p.band(38, 62, 38, 38, 20, 20, 40, 320)
    for ang in (40, 320):
        x, y = p._pt(38, 62, 29, 29, ang)
        p.circle(x, y, R_B)
    return 70


def b_e(p: Pen) -> float:
    p.band(38, 62, 38, 38, 20, 20, 30, 360)
    p.rect(4, 53, 71, 18)
    x, y = p._pt(38, 62, 29, 29, 30)
    p.circle(x, y, R_B)
    return 76


def b_s(p: Pen) -> float:
    p.band(27, 47.5, 27, 23.5, 9, 5.5, 90, 340)
    p.band(27, 76.5, 27, 23.5, 9, 5.5, 270, 520)
    for cx, cy, ang in ((27, 47.5, 340), (27, 76.5, 160)):
        x, y = p._pt(cx, cy, 18, 14.5, ang)
        p.circle(x, y, R_B)
    return 54


def b_r(p: Pen) -> float:
    _stem(p, 9, 33, 91)
    p.band(38, 62, 38, 38, 20, 20, 180, 300)
    x, y = p._pt(38, 62, 29, 29, 300)
    p.circle(x, y, R_B)
    return 62


def b_t(p: Pen) -> float:
    _stem(p, 23, 12, 91)
    p.rect(9, 24, 36, 18)
    p.circle(9, 33, R_B)
    p.circle(45, 33, R_B)
    return 54


GLYPHES_B: dict[str, GlyphFn] = {
    "q": b_q, "u": b_u, "a": b_a, "i": b_i, "d": b_d,
    "e": b_e, "s": b_s, "c": b_c, "r": b_r, "t": b_t,
}
KERN_B: dict[tuple[str, str], float] = {("r", "t"): -4, ("t", "e"): -3}
ESPACE_B = 28.0
INTERLETTRE_B = 7.0


def composer(
    pen: Pen,
    texte: str,
    glyphes: dict[str, GlyphFn],
    kern: dict[tuple[str, str], float],
    interlettre: float,
    espace: float,
) -> float:
    """Trace ``texte`` à partir de l'origine du traceur ; renvoie la chasse totale (unités locales)."""
    x = 0.0
    prev = ""
    base_ox = pen.ox
    for ch in texte:
        if ch == " ":
            x += espace
            prev = ""
            continue
        if ch not in glyphes:
            raise KeyError(f"Glyphe absent du lettrage : {ch!r}")
        if prev:
            x += interlettre + kern.get((prev, ch), 0.0)
        pen.ox = base_ox + pen.s * x
        x += glyphes[ch](pen)
        prev = ch
    pen.ox = base_ox
    return x


def chasse(texte: str, glyphes: dict[str, GlyphFn], kern: dict[tuple[str, str], float], interlettre: float, espace: float) -> float:
    """Chasse d'un texte sans rien tracer (unités locales)."""
    return composer(Pen(), texte, glyphes, kern, interlettre, espace)
