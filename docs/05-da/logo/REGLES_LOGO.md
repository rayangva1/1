# Règles d'usage du logo

> Nom de travail **« Quai des Cartes »** — non validé. Les logos sont un lettrage **original** dessiné en contours pleins (générés par `tools/glyphes.py` + `tools/generer_da.py`) : aucune police n'est nécessaire, aucun élément ne provient d'un logo, d'une police, d'un personnage ou d'un symbole Pokémon.

## 1. Fichiers livrés

### Direction A — Quai (`logo/a/`)

| Fichier | Usage | Fond |
|---|---|---|
| `logo-a-principal.svg` | Logo principal empilé « QUAI DES / CARTES » + barre-quai | Clair |
| `logo-a-horizontal.svg` | En-tête du site, email, signature | Clair |
| `logo-a-principal-fond-sombre.svg` / `logo-a-horizontal-fond-sombre.svg` | Mêmes versions, encre claire | Sombre |
| `logo-a-mono-noir.svg` / `logo-a-horizontal-mono-noir.svg` | Tampon, impression 1 couleur, gravure | Clair |
| `logo-a-mono-blanc.svg` | Réserve blanche | Foncé ou photo sombre |
| `logo-a-monogramme.svg` | Avatar réseaux, sticker, app | Tout fond |
| `logo-a-monogramme-mono-noir.svg` | Monogramme 1 couleur | Clair |
| `favicon.svg` | Onglet navigateur (16–48 px) | — |

### Direction B — Pochette (`logo/b/`)

| Fichier | Usage | Fond |
|---|---|---|
| `logo-b-principal.svg` | Logo principal une ligne « quai des cartes », point du i en carte violette | Clair |
| `logo-b-empile.svg` | Formats carrés : sticker, carte de remerciement | Clair |
| `logo-b-principal-fond-sombre.svg` | Encre claire, point du i violet clair | Sombre |
| `logo-b-mono-noir.svg` / `logo-b-mono-blanc.svg` | Une couleur | Clair / foncé |
| `logo-b-monogramme.svg` / `logo-b-monogramme-mono-noir.svg` | Avatar, sticker | Tout fond / clair |
| `favicon.svg` | Onglet navigateur | — |

### Exports PNG (`logo/png/`)

Générés depuis les SVG (`python docs/05-da/tools/generer_da.py --png`, outil local cairosvg) : logo principal 1200 px, logo pour email (400–440 px, à héberger : Gmail n'affiche pas le SVG), monogramme 512 px, favicon 32 px et 180 px (icône d'écran d'accueil iOS).

## 2. Zone de protection

| Direction | Unité X | Zone libre autour du logo |
|---|---|---|
| A | X = **2 × l'épaisseur de la barre-quai** (= 36 unités sur 268 de haut, ≈ 13 % de la hauteur du logo principal) | X sur les 4 côtés |
| B | X = **½ hauteur d'x** (hauteur d'un « a » = 76 unités → X = 38, ≈ 29 % de la hauteur du logo une ligne) | X sur les 4 côtés |

Rien ne pénètre dans la zone : texte, bord de photo, autre logo, pli ou découpe.

## 3. Tailles minimales

| Version | Écran (largeur) | Impression (largeur) |
|---|---|---|
| A principal empilé | 96 px | 25 mm |
| A horizontal | 140 px | 35 mm |
| A monogramme | 24 px | 7 mm |
| B principal une ligne | 120 px | 30 mm |
| B empilé | 80 px | 20 mm |
| B monogramme | 24 px | 8 mm |
| En dessous | `favicon.svg` (16–32 px) | — |

Contrôlé par rendu à ces tailles le 04.10.2026 (lettres distinctes, barre-quai et point du i visibles).

## 4. Couleurs autorisées

| Direction | Lettres | Accent | Variante |
|---|---|---|---|
| A clair | `#111111` | barre `#FF5B14` | mono noir `#000000` |
| A sombre | `#F2F1ED` | barre `#FF6A2B` | mono blanc `#FFFFFF` |
| B clair | `#0B0B12` | point du i `#5A31F4` | mono noir `#000000` |
| B sombre | `#F1F1F7` | point du i `#A797FF` | mono blanc `#FFFFFF` |

## 5. Interdits

- Redessiner, déformer, incliner (sauf la carte du « i », déjà inclinée), espacer autrement les lettres.
- Ajouter ombre, contour, dégradé, effet holographique ou 3D.
- Recolorer hors du tableau ci-dessus ; poser la version couleur sur une photo chargée (utiliser la version mono).
- Associer le logo à un personnage, une Poké Ball, un symbole d'énergie ou au logo d'un éditeur.
- Placer le monogramme dans un cercle coupé horizontalement (évocation de la Poké Ball).
- Écrire « officiel », « partenaire officiel » ou « boutique Pokémon » à côté du logo.

## 6. Intégration rapide

- **Shopify** : Thème > Personnaliser > En-tête > Logo : importer `logo-a-horizontal.svg` (ou PNG 1200 px si le thème refuse le SVG) ; Paramètres du thème > Favicon : `favicon-a-32.png` (vérifier le format accepté par le thème choisi).
- **Canva / Adobe Express** : importer le SVG (reste vectoriel) ; verrouiller l'élément logo dans les modèles.
- **Figma** : glisser le SVG ; il arrive en vecteurs éditables, couleurs = tokens.
- **Imprimeur** : envoyer le SVG ou un PDF vectoriel ; les logos sont déjà en contours (pas de police à fournir).

## Validation humaine requise

- [ ] Valider le nom (voir `NAMING.md`) **avant** toute impression ou achat de domaine.
- [ ] Choisir la direction (A ou B) et archiver les fichiers de l'autre.
- [ ] Valider le logo principal, le monogramme et le favicon de la direction retenue.
- [ ] Vérifier le rendu réel du favicon dans le thème Shopify retenu (format accepté, taille).
