"""Le renard dessiné en SVG : décor de secours sobre quand une illustration ne charge pas.

Silhouette originale du renard de la marque (« Braise », nom provisoire ; ``docs/05-da/DIRECTION_ATELIER.md`` §8) :
assis, **quadrupède**, **une seule queue** au bout orange, pointes des oreilles orange, plastron et museau crème. Aucun
élément sous licence, aucun vêtement, aucune posture debout. Elle n'est visible que si l'illustration ne charge pas
(classe ``a-visuel`` posée par le script de la page) ; couleurs portées par les classes ``rn-*`` de ``css/landing.css``
(aucune couleur en dur ici). Utilisée par ``site/outils/publication.py`` (pages de remerciement) et la landing.
"""

#: Renard assis, de trois quarts, tourné vers la droite (viewBox 120 × 140).
RENARD_ASSIS = (
    '<svg class="rn-renard" viewBox="0 0 120 140" aria-hidden="true" focusable="false">'
    '<path class="rn-pelage" d="M84 131C66 138 34 137 20 122C10 111 10 95 20 86C28 99 44 113 64 117Z"/>'
    '<path class="rn-braise" d="M20 86C10 95 10 111 20 122C25 127 31 130 38 132C29 121 25 104 29 92Z"/>'
    '<path class="rn-pelage" d="M48 133C42 113 43 92 51 76C56 67 63 61 71 60C81 66 87 80 89 96C91 110 91 122 89 133Z"/>'
    '<path class="rn-creme" d="M61 68C64 80 66 93 68 105C72 92 75 80 77 67C72 64 66 64 61 68Z"/>'
    '<path class="rn-pelage" d="M46 40L49 5L72 28Z"/>'
    '<path class="rn-pelage" d="M68 27L91 5L92 40Z"/>'
    '<path class="rn-creme" d="M55 32L53.5 19L62 28Z"/>'
    '<path class="rn-creme" d="M77 29L86 19L86.5 33Z"/>'
    '<path class="rn-braise" d="M49 5L48 16.5L56 12.5Z"/>'
    '<path class="rn-braise" d="M91 5L83.5 12.2L91.4 16Z"/>'
    '<path class="rn-pelage" d="M50 45C49 33 59 25 70 25C82 25 90 34 90 43C94 47 99 51 102 55C96 60 87 62 79 62C66 64 51 58 50 45Z"/>'
    '<path class="rn-creme" d="M68 52C77 50 91 51 102 55C95 60 86 62 78 62C71 61 66 58 68 52Z"/>'
    '<ellipse class="rn-oeil" cx="77" cy="42" rx="2.8" ry="3.3"/>'
    '<circle class="rn-truffe" cx="101.5" cy="55.2" r="2.4"/>'
    '<path class="rn-trait" d="M66 109V131M76 107V131"/>'
    "</svg>"
)
