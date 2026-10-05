"""Conversion Markdown → HTML minimale et sûre, pour les textes publics (blocs légaux).

Prend en charge exactement ce qu'utilisent les blocs publics de ``docs/04-legal`` :
titres ``##`` à ``####``, paragraphes, listes à puces ou numérotées, tableaux à barres,
gras, italique, code en ligne et liens ``[texte](url)``. Tout le reste est échappé :
aucun HTML brut du Markdown ne passe dans la page.
"""

from __future__ import annotations

import html
import re

_TITRE = re.compile(r"^(#{1,6})\s+(.*)$")
_PUCE = re.compile(r"^\s*[-*]\s+(.*)$")
_NUMERO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_LIEN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_GRAS = re.compile(r"\*\*(.+?)\*\*")
_ITALIQUE = re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])")
_CODE = re.compile(r"`([^`]+)`")
_A_REMPLIR = re.compile(r"⟦([^⟧]+)⟧")
_SCHEMAS_LIENS = ("https://", "http://", "mailto:", "#", "./", "../")


def _lien_sur(url: str) -> bool:
    return url.startswith(_SCHEMAS_LIENS) or re.match(r"^[\w./-]+\.html(#[\w-]+)?$", url) is not None


def en_ligne(texte: str) -> str:
    """Convertit la syntaxe en ligne d'un texte déjà brut (il est échappé ici)."""
    t = html.escape(texte, quote=False)

    def lien(m: re.Match[str]) -> str:
        libelle, url = m.group(1), html.unescape(m.group(2))
        if not _lien_sur(url):
            return m.group(0)
        return f'<a href="{html.escape(url, quote=True)}">{libelle}</a>'

    t = _CODE.sub(r"<code>\1</code>", t)
    t = _LIEN.sub(lien, t)
    t = _GRAS.sub(r"<strong>\1</strong>", t)
    t = _ITALIQUE.sub(r"<em>\1</em>", t)
    return _A_REMPLIR.sub(r'<mark class="lp-a-remplir">⟦\1⟧</mark>', t)


def _cellules(ligne: str) -> list[str]:
    ligne = ligne.strip()
    if ligne.startswith("|"):
        ligne = ligne[1:]
    if ligne.endswith("|"):
        ligne = ligne[:-1]
    return [c.strip() for c in ligne.split("|")]


def convertir(markdown: str, decalage_titres: int = 0) -> str:
    """Convertit un texte Markdown en HTML ; ``decalage_titres`` ajuste le niveau (## → h2 - décalage)."""
    lignes = markdown.replace("\r\n", "\n").split("\n")
    sortie: list[str] = []
    paragraphe: list[str] = []
    i = 0

    def vider_paragraphe() -> None:
        if paragraphe:
            sortie.append("<p>" + en_ligne(" ".join(s.strip() for s in paragraphe)) + "</p>")
            paragraphe.clear()

    while i < len(lignes):
        ligne = lignes[i]
        if not ligne.strip():
            vider_paragraphe()
            i += 1
            continue
        m = _TITRE.match(ligne)
        if m:
            vider_paragraphe()
            niveau = min(6, max(1, len(m.group(1)) - decalage_titres))
            sortie.append(f"<h{niveau}>{en_ligne(m.group(2).strip())}</h{niveau}>")
            i += 1
            continue
        if ligne.lstrip().startswith("|") and i + 1 < len(lignes) and _TABLE_SEP.match(lignes[i + 1]):
            vider_paragraphe()
            entetes = _cellules(ligne)
            i += 2
            corps: list[list[str]] = []
            while i < len(lignes) and lignes[i].lstrip().startswith("|"):
                corps.append(_cellules(lignes[i]))
                i += 1
            th = "".join(f"<th scope=\"col\">{en_ligne(c)}</th>" for c in entetes)
            trs = "".join(
                "<tr>" + "".join(f"<td>{en_ligne(c)}</td>" for c in rangee) + "</tr>" for rangee in corps
            )
            libelle = html.escape(entetes[0] if entetes else "Tableau", quote=True)
            sortie.append(
                f'<div class="lp-tableau" role="region" tabindex="0" aria-label="Tableau : {libelle}">'
                f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>"
            )
            continue
        for motif, balise in ((_PUCE, "ul"), (_NUMERO, "ol")):
            if motif.match(ligne):
                vider_paragraphe()
                items: list[str] = []
                while i < len(lignes) and motif.match(lignes[i]):
                    texte = motif.match(lignes[i]).group(1)  # type: ignore[union-attr]
                    i += 1
                    while i < len(lignes) and lignes[i].startswith("  ") and lignes[i].strip() and not _PUCE.match(lignes[i]) and not _NUMERO.match(lignes[i]):
                        texte += " " + lignes[i].strip()
                        i += 1
                    items.append(f"<li>{en_ligne(texte)}</li>")
                sortie.append(f"<{balise}>" + "".join(items) + f"</{balise}>")
                break
        else:
            paragraphe.append(ligne)
            i += 1
    vider_paragraphe()
    return "\n".join(sortie)
