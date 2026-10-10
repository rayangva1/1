"""Pictogrammes originaux de la boutique (grille 24 px, trait 2 px, currentColor).

Utilisés par le générateur (sprite components/icones.svg) et par les pages HTML.
Aucun symbole de licence (énergies, Poké Ball, créatures) : formes génériques.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

NOM_SPRITE = "Quai des Cartes (nom de travail)"

ICONES: dict[str, tuple[str, str]] = {
    # nom: (libellé, contenu SVG)
    "stock-local": ("Stock local", '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M9 15l2 2 4-4"/>'),
    "precommande": ("Précommande", '<rect x="3" y="5" width="18" height="16" rx="1"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
    "nouveaute": ("Nouveauté", '<path d="M12 3v5M12 16v5M3 12h5M16 12h5"/><path d="M12 9l3 3-3 3-3-3z"/>'),
    "rupture": ("Rupture", '<circle cx="12" cy="12" r="9"/><path d="M7 17L17 7"/>'),
    "alerte": ("Alerte réassort", '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>'),
    "langue": ("Langue", '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M7 9v6M7 9h3M7 12h2.5M13 15V9h2.5a1.5 1.5 0 0 1 0 3H13M15.5 12l1.5 3"/>'),
    "colis": ("Livraison", '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>'),
    "scelle": ("Scellé contrôlé", '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9"/>'),
    "panier": ("Panier", '<path d="M3 4h2l2.5 11h11L21 7H6.4"/><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/>'),
    "recherche": ("Recherche", '<circle cx="11" cy="11" r="7"/><path d="M16 16l5 5"/>'),
    "info": ("Information", '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>'),
    "carte": ("Carte à collectionner", '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 7h6M9 17h6"/>'),
}


def sprite_icones() -> str:
    """Sprite SVG <symbol> (à servir en HTTPS ; en local, copier le SVG en ligne)."""
    symboles = "".join(
        f'  <symbol id="i-{nom}" viewBox="0 0 24 24"><title>{escape(lib)}</title>{corps}</symbol>\n'
        for nom, (lib, corps) in ICONES.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" stroke-linejoin="miter">\n'
        f"  <title>Icônes {escape(NOM_SPRITE)} — trait 2 px, grille 24 px (direction B : extrémités arrondies via CSS)</title>\n"
        f"{symboles}</svg>\n"
    )


def icone_inline(nom: str, taille: int = 16) -> str:
    """Icône SVG en ligne (décorative : le libellé texte voisin porte l'information)."""
    return (
        f'<svg class="da-icon" width="{taille}" height="{taille}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" aria-hidden="true" focusable="false">{ICONES[nom][1]}</svg>'
    )
