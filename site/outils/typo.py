"""Typographie française (Suisse romande) dans le texte visible d'un document HTML.

Espaces insécables : fine (U+202F) avant « ? ! ; », normale (U+00A0) avant « : » et à
l'intérieur des guillemets « ». Seuls les nœuds texte sont modifiés : balises, attributs,
commentaires, entités, ``<script>``, ``<style>``, ``<pre>``, ``<code>`` et ``<textarea>``
restent intacts.
"""

from __future__ import annotations

import re

NBSP = "\u00a0"
NNBSP = "\u202f"
_JETONS = re.compile(r"(<!--.*?-->|<[^>]*>)", re.DOTALL)
_BRUTS = ("script", "style", "pre", "code", "textarea")
_REGLES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[ \u00a0\u202f]*([?!;])"), NNBSP + r"\1"),
    (re.compile(r"[ \u00a0\u202f]*:(?=[\s\u00a0]|$)"), NBSP + ":"),
    (re.compile(r"«[ \u00a0\u202f]*"), "«" + NBSP),
    (re.compile(r"[ \u00a0\u202f]*»"), NBSP + "»"),
)
_FAUTES = re.compile(r"[^\s\u00a0\u202f][?!;»]|«[ \t\r\n]|[ \t\r\n][?!;:»]")
_ENTITE = re.compile(r"&[#a-zA-Z0-9]+;|(?:https?://|www\.)[^\s<>\"']+")
_REPERE = re.compile("\ue000(\\d+)\ue001")


def _masquer(texte: str) -> tuple[str, list[str]]:
    """Remplace entités HTML (« &amp; ») et adresses web par des repères sans ponctuation."""
    entites: list[str] = []

    def repl(m: re.Match[str]) -> str:
        entites.append(m.group(0))
        return f"\ue000{len(entites) - 1}\ue001"

    return _ENTITE.sub(repl, texte), entites


def _demasquer(texte: str, entites: list[str]) -> str:
    return _REPERE.sub(lambda m: entites[int(m.group(1))], texte)


def _nom_balise(jeton: str) -> tuple[str, bool]:
    m = re.match(r"<\s*(/?)\s*([a-zA-Z0-9]+)", jeton)
    if not m:
        return "", False
    return m.group(2).lower(), m.group(1) == "/"


def _corriger_texte(texte: str) -> str:
    texte, entites = _masquer(texte)
    for motif, remplacement in _REGLES:
        texte = motif.sub(remplacement, texte)
    # « ? » et « ! » collés (« ?! ») : une seule espace avant le groupe.
    texte = re.sub(NNBSP + r"([?!])" + NNBSP + r"([?!])", NNBSP + r"\1\2", texte)
    return _demasquer(texte, entites)


def _segments_texte(html: str) -> list[tuple[bool, str]]:
    """Découpe en (est_texte_visible, segment)."""
    morceaux: list[tuple[bool, str]] = []
    pile_brute = 0
    for jeton in _JETONS.split(html):
        if not jeton:
            continue
        if jeton.startswith("<"):
            nom, fermante = _nom_balise(jeton)
            if nom in _BRUTS:
                pile_brute = max(0, pile_brute - 1) if fermante else pile_brute + 1
            morceaux.append((False, jeton))
        else:
            morceaux.append((pile_brute == 0, jeton))
    return morceaux


def typographier(html: str) -> str:
    """Applique les espaces insécables au texte visible ; idempotent."""
    return "".join(_corriger_texte(s) if visible else s for visible, s in _segments_texte(html))


def fautes(html: str) -> list[str]:
    """Extraits de texte visible où une espace insécable manque (ou une espace ordinaire subsiste)."""
    trouvees: list[str] = []
    for visible, segment in _segments_texte(html):
        if not visible:
            continue
        masque, _ = _masquer(segment)
        for m in _FAUTES.finditer(masque):
            debut = max(0, m.start() - 20)
            extrait = masque[debut : m.end() + 5].replace("\n", " ").strip()
            if "://" in extrait or "{{" in extrait:
                continue
            trouvees.append(extrait)
    return trouvees
