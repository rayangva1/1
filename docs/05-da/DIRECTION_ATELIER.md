# Ambiance « Atelier » (bâtie sur la direction A)

> Direction retenue par le propriétaire le 06.10.2026 : elle **remplace** l'ambiance « Nuit sur le Léman » et la loutre « Lumi » (`DIRECTION_NUIT.md`, archivée). Nom de travail de la boutique : **Quai des Cartes** (non validé). Mascotte : un **renard original**, nom provisoire **Braise** (à valider, §8.5).
> Sources : `tokens/tokens.json` (bloc `ambiances.atelier`, généré en `tokens/tokens-atelier.css`), les 3 photos du propriétaire et les 10 illustrations du renard (`site/config/visuels.json`), `DIRECTION_A.md` (lettrage, composants), `docs/04-legal/USAGE_MARQUES.md`, BP §7 et §8. Application : `site/landing/` (landing et pages secondaires) et `site/maquettes/`, refaites en Atelier le 10.10.2026 (étape 2), puis corrigées après deux critiques (DA, accessibilité et honnêteté) le même jour : un seul papier, statuts monochromes, héro plein écran, fil qui traverse les illustrations ; derniers constats traités le même jour (HON-02 boîte du drop légendée, A11Y-02 et A11Y-03 textes alternatifs, PERF-01 héro mobile, IP-02 image de partage, IP-03 mascotte générée).

## 1. Intention

**Un établi de collectionneur, le matin, à Genève.** Du papier crème dans la lumière d'une fenêtre, l'ombre douce d'un feuillage, une boîte noire mate, des étuis transparents — et un seul fil orange qui traverse la scène. C'est la photographie produit « quiet luxury » des photos du propriétaire, transposée en page : éditorial suisse, très grande typographie, beaucoup d'air, presque rien à l'écran sinon ce qui compte.

- **Effet visé** : « le plus beau site de cartes que j'ai vu », sans rien de tape-à-l'œil. La qualité vient de la retenue : un charbon, un papier, un orange ; des marges généreuses ; des images qui respirent.
- **Fil narratif** : le renard (Braise, nom provisoire) traverse les chapitres. Il attend à côté d'une boîte, se présente, soulève le jour du drop le couvercle d'une boîte symbolique (il n'en sort qu'une lumière), garde les réservations avec un clin d'œil, passe la tête au-dessus d'un classeur, dresse les oreilles pour les alertes, regarde le Jet d'eau depuis le quai, puis s'endort contre une boîte en pied de page.
- **Signature** : **le fil orange** (§6). Le filet orange posé sur le papier dans les photos devient une ligne continue qui relie les chapitres.
- **Ce qu'elle n'est pas** : ni personnage, symbole, police ou logo de la licence ; ni jaune et bleu de la licence ; ni effet qui presse l'achat (aucun compte à rebours, aucun « plus que N », aucun stock fictif) ; ni décor « gaming » (néon, holographique, arc-en-ciel).

## 2. Activation

```html
<html lang="fr-CH" data-da="a" data-ambiance="atelier">
<link rel="stylesheet" href="assets/da/tokens.css">
<link rel="stylesheet" href="assets/da/components.css">
<link rel="stylesheet" href="assets/da/ambiance.css">   <!-- copie de tokens/tokens-atelier.css -->
```

Copie et alignement des pages : `python site/outils/da_sync.py --direction a --ambiance atelier` (logos de l'ambiance : `logo/a/logo-a-atelier.svg` sur papier, `logo/a/logo-a-atelier-fond-sombre.svg` sur charbon, `logo/a/favicon-atelier.svg`).

L'ambiance est **toujours claire** (`mode: light`, `color-scheme: light`) : elle l'emporte sur le réglage clair/sombre du système (sélecteur `:root[data-ambiance="atelier"][data-da]`, chargé après `tokens.css`). Les chapitres charbon (jour du drop, pied de page) sont des **sections inversées** avec leurs propres tokens `inverse-*`, pas un mode sombre.

## 3. Palette (mesurée sur les photos)

### 3.1 Méthode de mesure

Mesures du 09.10.2026 (script de mesure local, Pillow) sur les fichiers fournis : les 3 photos du propriétaire (profil ICC **sRGB** embarqué, donc aucune conversion de couleur) et les 10 illustrations du renard (JPEG sans profil, interprétés en sRGB). Pour chaque couleur : médiane par canal d'une zone homogène, ou quantile de luminance sur les pixels peu saturés (papier, charbon). Les valeurs retenues arrondissent ces mesures vers le rôle (lisibilité, contraste prouvé).

| Rôle | Mesure (fichier, zone) | Valeur retenue |
|---|---|---|
| Papier éclairé | `#EEEBE3` médiane du mur éclairé (photo boîte, tiers gauche) ; `#E7E2DA` médiane de tout le papier de la photo | `bg` `#EFEAE1` (référence du propriétaire, à 1–2 unités de la mesure) |
| Papier en pleine lumière | `#F7F3ED` (95e centile, photo boîte) | `surface` `#F8F5EF` |
| Papier à l'ombre | `#E4DFD7` (bas de la photo boîte), `#E0D9CF` (photo mains) | `surface-alt` `#E4DED3` |
| Papier des illustrations | Bords des 9 illustrations du renard (bande de 2 % sur les quatre côtés, pixels clairs, mesure du 10.10.2026) : médiane `#EBDAC8`, quartile haut `#FCE7D4` ; hauts plus sombres (`#E1CEBD` à `#E9D9C9`, ombres de feuillage), bas et côtés éclairés (`#F7E3CD` à `#FBEEDE`). La première valeur (`#FCF2E2`, mesurée au cœur des zones claires) laissait une couture de 6 à 8 points de luminance au bord de chaque image | `papier-chaud` `#F1E4D3` (entre la médiane et les bords éclairés) |
| Ombre de feuillage | `#E4DFD5` (5e centile du mur, photo) ; `#E8D7C7` (héro illustré) | `ombre` `#DDD5C8` (un ton plus marqué, décor) |
| Charbon mat | `#1D1E1B` (couverture du classeur), `#1A1512` (fourrure), `#2B2927` (face éclairée de la boîte) | `ink` `#1D1B19`, `inverse-surface` `#2A2724` |
| Gris des cartes vierges | `#575657` (photo mains), `#4E4C4C` (photo boîte) | `ink-muted` `#5D5750` (réchauffé pour le papier) |
| Fil orange | `#EF6D28` (photo boîte) ; `#F66A16`, `#F16C20`, `#F16919`, `#F3691A` (filets des illustrations) : médiane `#F16A1A` | `accent` `#F26A1B` (référence du propriétaire) |
| Carte orange du classeur | `#EE5C1F` | non retenu (même famille que l'accent) |
| Yeux du renard | `#E7923C` (ambre) | non retenu en couleur d'interface (réservé aux illustrations) |

### 3.2 Rôles

| Token | Hex | Rôle |
|---|---|---|
| `bg` / `surface` / `surface-alt` | `#EFEAE1` / `#F8F5EF` / `#E4DED3` | Papier éclairé / en pleine lumière / à l'ombre |
| `papier-chaud` | `#F1E4D3` | **Le papier de toute la page** (un seul papier pour tous les chapitres clairs, plus d'alternance avec `bg`) ; le cadre des illustrations y est fondu (masque à gauche, à droite et en haut, bord net en bas là où sort le filet) : le bord de l'image ne se voit plus |
| `ombre` | `#DDD5C8` | Ombre de feuillage dessinée (décor) |
| `ink` / `ink-muted` | `#1D1B19` / `#5D5750` | Charbon (texte, bouton principal) / gris chaud (texte secondaire) |
| `on-ink` | `#F8F5EF` | Texte sur charbon |
| `line` / `line-strong` | `#D8D1C5` / `#7A7268` | Filets décoratifs / bordures de champs (≥ 3:1) |
| `accent` / `on-accent` | `#F26A1B` / `#1D1B19` | **Le fil orange** ; texte dessus toujours charbon |
| `accent-text` | `#A6420C` | Rouille : l'orange lisible en texte (liens) |
| `accent-soft` | `#FBE3D2` | Lin orangé : encart de la réservation garantie |
| `focus` | `#1D1B19` | Anneau de focus charbon |
| `inverse-bg` / `inverse-surface` | `#1D1B19` / `#2A2724` | Chapitre charbon / panneau « boîte noire » |
| `inverse-ink` / `inverse-muted` / `inverse-accent` / `inverse-focus` | `#EFEAE1` / `#B8AFA4` / `#F26A1B` / `#EFEAE1` | Texte, texte secondaire, surtitre orange et focus sur charbon |
| `inverse-line` | `#4A453F` | Filets sur charbon (décor) |
| Statuts, langue | voir `tokens.json` | Badges **monochromes** (l'icône et le libellé les distinguent) : Stock local papier `#F8F5EF` et contour charbon ; Précommande `#E4DED3` et contour `line-strong` ; Rupture gris chaud `#5D5750` sur `#E4DED3` ; Réassort charbon sur lin orangé ; Nouveauté charbon sur orange ; FR crème sur charbon. **Réservation garantie** = la « boîte noire à bande orange » de l'illustration : crème sur charbon, bande orange de 3 px en bas (`components.css`). Plus d'indigo ni de vert : ils cassaient la proportion 80/15/5 |

Proportions : **80 % papier, 15 % charbon, 5 % orange au plus**. L'orange est un trait, jamais une surface (sauf le badge Nouveauté).

Règles qui en découlent (ratios recalculés par `tools/verifier_da.py`) :
- **L'orange n'est jamais du texte sur le papier** : 2.55:1 seulement entre `#F26A1B` et `#EFEAE1` (2.81:1 entre `#F26A1B` et `#F8F5EF`). Le fil est un **décor** : il ne porte aucune information et ne sert jamais de contour à un élément interactif (focus et bordures restent charbon ou `line-strong`).
- **Texte sur orange : charbon seulement** : 5.60:1 entre `#1D1B19` et `#F26A1B` ; jamais blanc (3.06:1 entre `#FFFFFF` et `#F26A1B`) ni crème (2.81:1 entre `#F8F5EF` et `#F26A1B`).
- **L'orange s'écrit sur charbon** : 5.60:1 entre `#F26A1B` et `#1D1B19` (surtitres des chapitres inversés).
- Liens sur papier : rouille, 5.14:1 entre `#A6420C` et `#EFEAE1`, toujours soulignés.
- Pas de noir pur : le charbon `#1D1B19` (14.33:1 entre `#1D1B19` et `#EFEAE1`) garde la douceur mate des photos.
- **Texte posé sur une illustration** : uniquement dans la zone libre des visuels — titre, introduction et bouton du héro sur ordinateur (dès 1280 px, moitié gauche), titre du héro sur mobile (haut libre du portrait), titre de Genève dans le ciel (dès 900 px), en-tête des alertes sur le mur libre (dès 1100 px). Le texte y est **charbon** (jamais `ink-muted` : numéros et introductions passent en `ink`) et posé sur un voile `papier-chaud` d'au moins **64 %** (`.lp-voile` : plein sous chaque glyphe, bords fondus sur 120 à 240 px pour ne jamais dessiner un calque visible) : 5.30:1 même si l'image devenait noire, 15.4:1 si elle devenait blanche. Le voile s'arrête avant la boîte noire du héro (cadrage `object-position: 62% 100%`). Preuve Playwright : chaque image remplacée par du noir et du blanc purs, contraste mesuré sous chaque texte posé sur une image (`site/tests/e2e/atelier.mjs`, lancé par `scripts/run_all_tests.sh`, et `site/tests/test_landing_e2e.py`).

### 3.3 Contrastes WCAG 2.x (calculés, tronqués à 2 décimales)

Seuils : texte ≥ 4.5:1 (AA), bordures, focus et composants ≥ 3:1 (WCAG 1.4.11). Chaque couple réellement utilisé est déclaré (paires communes + `ambiances.atelier.contrastPairs`) ; le tableau est généré et contrôlé par `tools/generer_da.py` / `tools/verifier_da.py`, et un couple sous son seuil fait échouer les tests.

<!-- CONTRASTES:DEBUT (généré par tools/generer_da.py, ne pas éditer) -->
| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |
|---|---|---|---|---|---|---|
| Clair | Texte courant sur fond de page | `#1D1B19` ink | `#EFEAE1` bg | **14.33:1** | 4.5 | AAA |
| Clair | Texte sur carte produit | `#1D1B19` ink | `#F8F5EF` surface | **15.77:1** | 4.5 | AAA |
| Clair | Texte sur bandeau | `#1D1B19` ink | `#E4DED3` surface-alt | **12.82:1** | 4.5 | AAA |
| Clair | Texte sur bannière teintée | `#1D1B19` ink | `#FBE3D2` accent-soft | **13.91:1** | 4.5 | AAA |
| Clair | Texte secondaire sur fond | `#5D5750` ink-muted | `#EFEAE1` bg | **5.95:1** | 4.5 | AA |
| Clair | Texte secondaire sur carte | `#5D5750` ink-muted | `#F8F5EF` surface | **6.55:1** | 4.5 | AA |
| Clair | Texte secondaire sur bandeau | `#5D5750` ink-muted | `#E4DED3` surface-alt | **5.32:1** | 4.5 | AA |
| Clair | Bouton principal / bandeau inversé | `#F8F5EF` on-ink | `#1D1B19` ink | **15.77:1** | 4.5 | AAA |
| Clair | Texte sur accent (bouton, badge) | `#1D1B19` on-accent | `#F26A1B` accent | **5.60:1** | 4.5 | AA |
| Clair | Lien sur fond | `#A6420C` accent-text | `#EFEAE1` bg | **5.14:1** | 4.5 | AA |
| Clair | Lien sur carte | `#A6420C` accent-text | `#F8F5EF` surface | **5.66:1** | 4.5 | AA |
| Clair | Lien sur bandeau | `#A6420C` accent-text | `#E4DED3` surface-alt | **4.60:1** | 4.5 | AA |
| Clair | Message d'erreur sur fond | `#B42318` error | `#EFEAE1` bg | **5.48:1** | 4.5 | AA |
| Clair | Message d'erreur dans un formulaire | `#B42318` error | `#F8F5EF` surface | **6.04:1** | 4.5 | AA |
| Clair | Bordure de champ sur fond (WCAG 1.4.11) | `#7A7268` line-strong | `#EFEAE1` bg | **3.95:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bordure de champ sur carte (WCAG 1.4.11) | `#7A7268` line-strong | `#F8F5EF` surface | **4.35:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur fond (WCAG 1.4.11) | `#1D1B19` focus | `#EFEAE1` bg | **14.33:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur carte (WCAG 1.4.11) | `#1D1B19` focus | `#F8F5EF` surface | **15.77:1** | 3.0 | UI ≥ 3:1 |
| Clair | Badge Stock local | `#1D1B19` status-local-fg | `#F8F5EF` status-local-bg | **15.77:1** | 4.5 | AAA |
| Clair | Badge Précommande | `#1D1B19` status-preorder-fg | `#E4DED3` status-preorder-bg | **12.82:1** | 4.5 | AAA |
| Clair | Badge Nouveauté | `#1D1B19` status-new-fg | `#F26A1B` status-new-bg | **5.60:1** | 4.5 | AA |
| Clair | Badge Rupture | `#5D5750` status-out-fg | `#E4DED3` status-out-bg | **5.32:1** | 4.5 | AA |
| Clair | Badge Alerte réassort | `#1D1B19` status-restock-fg | `#FBE3D2` status-restock-bg | **13.91:1** | 4.5 | AAA |
| Clair | Badge langue FR | `#F8F5EF` lang-fr-fg | `#1D1B19` lang-fr-bg | **15.77:1** | 4.5 | AAA |
| Clair | Texte posé à côté d'une illustration du renard | `#1D1B19` ink | `#F1E4D3` papier-chaud | **13.71:1** | 4.5 | AAA |
| Clair | Texte secondaire à côté d'une illustration | `#5D5750` ink-muted | `#F1E4D3` papier-chaud | **5.69:1** | 4.5 | AA |
| Clair | Lien rouille dans un chapitre illustré | `#A6420C` accent-text | `#F1E4D3` papier-chaud | **4.92:1** | 4.5 | AA |
| Clair | Texte posé sur une ombre de feuillage | `#1D1B19` ink | `#DDD5C8` ombre | **11.79:1** | 4.5 | AAA |
| Clair | Texte secondaire sur une ombre de feuillage | `#5D5750` ink-muted | `#DDD5C8` ombre | **4.89:1** | 4.5 | AA |
| Clair | Texte secondaire sur encart lin orangé | `#5D5750` ink-muted | `#FBE3D2` accent-soft | **5.78:1** | 4.5 | AA |
| Clair | Lien rouille sur encart lin orangé | `#A6420C` accent-text | `#FBE3D2` accent-soft | **4.99:1** | 4.5 | AA |
| Clair | Message d'erreur sur bandeau | `#B42318` error | `#E4DED3` surface-alt | **4.91:1** | 4.5 | AA |
| Clair | Anneau de focus sur bandeau (WCAG 1.4.11) | `#1D1B19` focus | `#E4DED3` surface-alt | **12.82:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus dans un chapitre illustré (WCAG 1.4.11) | `#1D1B19` focus | `#F1E4D3` papier-chaud | **13.71:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bordure de champ sur bandeau (WCAG 1.4.11) | `#7A7268` line-strong | `#E4DED3` surface-alt | **3.53:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bordure de champ dans un chapitre illustré (WCAG 1.4.11) | `#7A7268` line-strong | `#F1E4D3` papier-chaud | **3.78:1** | 3.0 | UI ≥ 3:1 |
| Clair | Texte crème sur charbon | `#EFEAE1` inverse-ink | `#1D1B19` inverse-bg | **14.33:1** | 4.5 | AAA |
| Clair | Texte secondaire sur charbon | `#B8AFA4` inverse-muted | `#1D1B19` inverse-bg | **7.93:1** | 4.5 | AAA |
| Clair | Surtitre orange sur charbon | `#F26A1B` inverse-accent | `#1D1B19` inverse-bg | **5.60:1** | 4.5 | AA |
| Clair | Texte crème sur panneau de boîte noire | `#EFEAE1` inverse-ink | `#2A2724` inverse-surface | **12.39:1** | 4.5 | AAA |
| Clair | Texte secondaire sur panneau de boîte noire | `#B8AFA4` inverse-muted | `#2A2724` inverse-surface | **6.86:1** | 4.5 | AA |
| Clair | Surtitre orange sur panneau de boîte noire | `#F26A1B` inverse-accent | `#2A2724` inverse-surface | **4.84:1** | 4.5 | AA |
| Clair | Anneau de focus crème sur charbon (WCAG 1.4.11) | `#EFEAE1` inverse-focus | `#1D1B19` inverse-bg | **14.33:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus crème sur panneau de boîte noire (WCAG 1.4.11) | `#EFEAE1` inverse-focus | `#2A2724` inverse-surface | **12.39:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bouton principal charbon | `#F8F5EF` on-ink | `#1D1B19` ink | **15.77:1** | 4.5 | AAA |
<!-- CONTRASTES:FIN -->

## 4. Typographies (Google Fonts, licence SIL OFL)

| Rôle | Police | Réglages | Repli |
|---|---|---|---|
| Grands titres | **Geist** 500–600 (variable 300–800) | Bas-de-casse, interlettrage −3,5 %, interligne 0.92 (héro) à 1.0 ; `display-xl` 52 → 152 px, `display-l` 40 → 96 px | Helvetica Neue, Helvetica, Arial |
| Mot d'accent | **Instrument Serif** italique | Un mot (deux au plus) dans un titre, un titre par écran au plus ; même corps que le titre | Times New Roman, Georgia |
| Texte | **Geist** 400/500 | 17–18 px, interligne 1.6, 66 caractères par ligne (`largeur-texte` 38 rem) | Helvetica Neue, Arial |
| Surtitres, numéros, dates, prix (boutique) | **Geist Mono** 500 | Capitales, 12 px, interlettrage +16 % ; `tabular-nums` | SFMono-Regular, Menlo, Consolas |

- **Pourquoi** : Geist est une grotesque nette d'inspiration suisse, très lisible en petit et élégante en très grand ; Instrument Serif apporte une seule note éditoriale (italique fine, en écho aux magazines) ; Geist Mono donne aux numéros de chapitre et aux dates le ton d'une étiquette d'atelier. Deux familles d'une même maison (Geist, Geist Mono) plus un accent : chargement maîtrisé.
- **Alternatives libres** si Geist est refusée : Inter Tight (titres) + Inter (texte), Hanken Grotesk, Schibsted Grotesk ; accent : Fraunces italique (déjà connu du projet) ; mono : JetBrains Mono, IBM Plex Mono.
- URL : `tokens.json > ambiances > atelier > googleFonts` (appliquée à chaque page par `site/outils/da_sync.py`). En production, préférer l'auto-hébergement (aucune adresse IP de visiteur transmise à Google, nLPD) ; sans Google Fonts (`publication.py --sans-google-fonts`), les replis système restent élégants (Helvetica Neue / Times italique).

## 5. Grille et espace

- **Grille** : 12 colonnes dès 900 px (gouttière 24 px), 8 colonnes de 600 à 899 px, 4 colonnes en dessous ; largeur max **1360 px** ; marges `clamp(20px, 5vw, 80px)` ; rythme vertical sur une base de 8 px.
- **Air** : `espace-section` `clamp(96px, 14vw, 208px)` entre chapitres ; jamais deux blocs de texte collés à une image sans au moins 48 px.
- **Mise en page éditoriale** : numéro de chapitre en Geist Mono dans la colonne 1 (« 01 — Le jour du drop »), titre de la colonne 2 à 9, texte limité à 5 colonnes ; les images débordent volontiers jusqu'au bord de la page (pleine largeur 21:9, ou 7 colonnes collées à la marge). Asymétrie assumée : la moitié vide des visuels (gauche du héro, droite des alertes) accueille le titre.
- **Coins** : 2 / 4 / 8 px (cartes, champs), jamais de pilule sauf les badges ; ombres longues et douces (`shadow-card`), comme la boîte sur le papier.

## 6. Motif signature : « le fil orange »

Dans les photos, un filet orange est posé sur le papier. Sur le site, il devient **une seule ligne continue** qui traverse la page de haut en bas et relie les chapitres :

1. **Départ** : il sort du filet photographié du héro (bas gauche de `renard-heros`, mesuré de (0.012, 0.871) à (0.729, 0.997) en fraction de l'image) et descend vers le premier chapitre.
2. **Parcours** : entre deux chapitres, il suit la marge gauche (colonne 1), passe sous les numéros de chapitre, longe une image puis **rejoint le filet photographié** de l'image suivante quand elle en a un (points d'entrée et de sortie mesurés et stockés dans `site/config/visuels.json`, champ `fil`, en fractions de largeur et de hauteur). Il s'efface derrière les images sans filet (classeur, Léman, réservation).
3. **Arrivée** : il se pose sous le renard endormi du pied de page (`renard-pied-de-page`, filet de (0, 0.793) à (0.999, 0.993)).

Réalisation (landing, 10.10.2026, revue après critique) : SVG `aria-hidden="true"` (`.lp-fil`, tracé par `site/landing/js/atelier.js`), trait `accent` de `fil-epaisseur` (2 px).

- **Il traverse les illustrations** (`[data-fil-ancre]`) : il entre dans le filet photographié et en ressort. Points d'entrée et de sortie, **épaisseur** (`fil_epaisseur`, fraction de la hauteur) et **teintes** (`fil_couleurs`, près de l'entrée et de la sortie) mesurés et stockés dans `site/config/visuels.json`, écrits dans `data-fil`, `data-fil-ep` et `data-fil-couleurs` par `site/outils/visuels.py`, projetés par le script (cadrage `object-fit` compris). Le raccord est **effilé** : sur 96 px à la sortie (64 px à l'entrée), un polygone part de l'épaisseur projetée du filet photographié et de sa teinte (orange pâle sur les illustrations) et s'affine jusqu'au trait de 2 px orange — plus de couture entre un filet de 8 px pastel et un trait vectoriel saturé.
- **Aucun crochet** : à la sortie d'un filet, le fil le prolonge, tourne vers le bas, descend dans un couloir libre (jamais à moins de 32 px d'un texte, d'un formulaire ou d'une figure), puis glisse en S jusqu'à la marge dans l'espace entre deux chapitres. Il entre dans le filet suivant par un coin arrondi qui prolonge le filet lui-même ; sur un cadre fondu, il recouvre la partie fondue du filet.
- **Il passe sous les illustrations pleine largeur** (Genève, alertes dès 1100 px, pied de page) : il disparaît au milieu du fondu du haut de l'image et réapparaît dans son filet. Au Léman, il **ressort de la corde orange** enroulée au bollard (`data-fil-ancre="corde"`, bout de corde mesuré), descend du quai et traverse l'espace jusqu'aux alertes.
- **Il relie les chapitres** : chaque numéro porte son tiret orange *devant* le chiffre (« —— 05 ») ; le fil s'y branche quand le numéro est posé contre la marge (`[data-fil-chapitre]`), et le tiret se dessine de 0 à 32 px quand le fil l'atteint. Il se branche aussi sur la bande orange de la photo de la boîte (la bande devient le fil) et sur le filet en diagonale de la photo des mains (`data-fil-ancre="branche"`).
- **Mobile (moins de 700 px)** : pas de fil dans la marge (il serait à 10 px du texte) ; chaque filet se prolonge de 64 px et s'effile.
- **Dessiné au défilement** (`stroke-dashoffset` suivant le niveau de lecture, à 85 % de la fenêtre, avec une transition douce) ; **coupé** avec `prefers-reduced-motion: reduce` et avec le bouton « Pause des animations » : la ligne est alors entière et immobile, tous les tirets dessinés. Sans JavaScript, une ligne continue est tracée en CSS dans la marge des chapitres. Le fil ne porte **aucune information** (décor, 2.45:1 sur le papier : jamais un repère de navigation ni un indicateur de progression). Il ne passe jamais sur un texte (contrôle Playwright : chaque point du tracé hors des boîtes de texte).

## 7. Photographie

| Règle | Détail |
|---|---|
| Lumière | Fenêtre latérale (de gauche), matin ; ombres de feuillage douces en diagonale ; jamais de flash, jamais de néon. |
| Fond | Papier crème mat ; aucune texture bruyante ; le bord du cadre respire (≥ 30 % d'espace libre). |
| Objets | Vierges : aucun logo, aucun texte, aucune illustration. Charbon mat, transparents (étuis rigides, pochettes), papier. |
| Composition | Objet principal au tiers droit, moitié gauche libre pour le titre ; le fil orange traverse le cadre en bas ou en diagonale. |
| Formats | 21:9 (héro, bandeaux), 16:9 (chapitres), 4:5 (portraits), 9:16 (héro mobile). |
| Retouche | Balance légèrement chaude ; noirs autour de `#1D1B19` (jamais bouchés) ; blancs au plus `#F8F5EF`. |
| Fiches produit | **Photo réelle du produit vendu uniquement** (BP §7) ; jamais une illustration du renard ni une photo d'ambiance. |

**Les 3 photos du propriétaire sont des visuels d'ambiance.** Le BP prévoit de vendre « quelques accessoires » (sleeves, 10 % du budget stock) : précisément pour cela, ces photos (boîte noire, étuis rigides, pochettes, classeur, tous vierges) **ne sont jamais présentées comme des produits en vente** : texte alternatif et légende neutres et vérifiables (« Photo d'ambiance : objets vierges, sans marque. Sur la boutique, chaque fiche montre la photo réelle du produit vendu. » — jamais « nos accessoires », jamais « ne représente pas un produit de la boutique », affirmation que le propriétaire n'a pas validée), aucun prix, aucun statut de stock. **Aucune image montrant un type d'accessoire** (photo, ou illustration du renard avec un classeur, des étuis ou une boîte) n'est dans une section qui cite « Accessoires » : le chapitre des formats est sans image, et le formulaire d'alertes (case « Accessoires ») n'est accompagné que du renard seul (contrôlé par `site/tests/test_atelier.py`). Sur la landing : la photo de la boîte et celle des mains dans le chapitre du soin, celle du classeur dans la colonne des questions (ordinateur seulement). Si un accessoire photographié est un jour vendu, sa fiche utilise sa propre photo produit. La photo des mains qui glissent une carte vierge dans une pochette montre un geste de collectionneur : elle n'illustre ni un service de cartes à l'unité (pas au lancement), ni le contrôle à réception (les produits scellés ne sont jamais ouverts). `site/outils/visuels.py` refuse un texte alternatif de photo qui dirait « nos », « en vente », « prix » ou « stock ».

## 8. Mascotte : Braise (nom provisoire)

### 8.1 Fiche personnage

Renard **original** créé pour la boutique, style **« réaliste-animé »** : personnage stylisé (tête un peu plus grande, grands yeux expressifs, mimiques d'animation) et fourrure photoréaliste, comme dans les films en prises de vues réelles ou en images de synthèse.

- **Pelage** noir charbon ; **plastron, joues et museau crème** ; intérieur des oreilles crème.
- **Pointes des oreilles orange vif** et **bout de l'unique queue orange vif** (le dernier tiers, touffu).
- **Grands yeux ambrés**, truffe noire, **sourire en coin**.
- **Caractère** : malicieux, calme, attentif ; il attend, observe, garde, cligne de l'œil, s'endort. Jamais pressé, jamais vendeur.

Visuels de référence : `renard-assis` (pied, face), `renard-couche`, `renard-heros` (voir §9).

### 8.2 Règles de marque (à respecter sur chaque visuel)

| À faire | À ne jamais faire |
|---|---|
| Toujours **quadrupède** : assis sur l'arrière-train, couché, roulé en boule, à quatre pattes, pattes avant posées sur un objet | **Jamais debout sur deux pattes**, jamais une posture humaine (bras croisés, mains sur les hanches) |
| **Une seule queue**, touffue, au bout orange | Jamais deux, trois ou neuf queues (→ **Feunard / Ninetales**, le renard à neuf queues **Kurama** de Naruto, **Tails** de Sega) |
| Corps nu de renard : sa fourrure suffit | **Jamais de gants, de chaussures ni de vêtements** (→ **Tails**, Sega), ni écharpe, ni sac, ni accessoire porté |
| Plastron crème en V étroit, queue noire au bout **orange**, front noir | **Aucun trait d'Évoli** ni d'un Pokémon : pas de **collerette** crème géante autour du cou, pas de **bout de queue crème**, pas de **mèche frontale** orange ; pas non plus de crinière ou de mèche rouge, ni de maquillage rouge autour des yeux (Zorua, Zoroark) |
| Oreilles de renard proportionnées, **intérieur des oreilles crème**, l'orange seulement aux **pointes** (sur le bord extérieur) | **Jamais de touffe orange à l'intérieur des oreilles**, ni de très grandes oreilles à touffe orange ou rouge (→ **Feunnec / Fennekin** et **Roussil / Braixen**, renards de la licence aux grandes oreilles à touffe orange intérieure ; Roussil est aussi proche du nom « Braise », §8.5) |
| Montrer des **boîtes noires, étuis et cartes vierges**, sans logo ni texte | Il **ne tient jamais un produit Pokémon** (vrai ou imité) : aucun booster, display, coffret, carte illustrée, Poké Ball, énergie, type |
| Narrateur discret : il veille, garde, salue, dort | Lui faire dire « vite », « dernière chance », un prix ou un stock ; l'associer à un compte à rebours |
| Afficher « Braise (nom provisoire) » tant que le nom n'est pas validé | Le présenter comme un personnage de la licence ou « officiel » |

**Les illustrations n'illustrent jamais un produit vendu** : elles accompagnent un chapitre (drop, réservation, alertes, expédition) et ne remplacent jamais une photo réelle de produit. Les boîtes noires des illustrations sont des symboles (« un produit scellé »), pas un article du catalogue. Les boîtes ne sont jamais ouvertes sur un contenu identifiable (le jour du drop : une lumière, rien d'autre). **Une boîte ouverte dessinée est un symbole du drop, jamais un produit ouvert** : elle est toujours légendée comme telle (« La boîte noire est un symbole du drop, pas un produit ouvert : il n'en sort qu'une lumière, et les cartes posées au sol sont vierges. »), et aucun texte ne dit que Braise ou la boutique « ouvre la boîte » — à réception, les produits scellés sont contrôlés sans être ouverts, et le drop « n'ouvre » qu'une fois le produit à Genève (`site/outils/verifier_site.py` refuse « ouvre la boîte », « ouvrir les produits »… ; `site/tests/test_atelier.py` exige la légende). Sur une page de produit (maquettes), le renard n'est **jamais dans la même section** que le titre du produit ou ses prix, et il est accompagné de la mention « Braise (nom provisoire), création originale pour la boutique, ne représente pas ce produit » ; le héro d'une page de drop montre l'emplacement de la photo réelle du produit (contrôlé par `site/tests/test_atelier.py`).

### 8.3 Contrôle d'un nouveau visuel (avant import)

1. Quadrupède ? Une seule queue ? Aucun vêtement, gant, chaussure ?
2. Bout de la queue et pointes des oreilles orange (jamais crème) ? Pas de collerette ni de mèche frontale ? Intérieur des oreilles crème, **sans touffe orange** (Feunnec / Fennekin, Roussil / Braixen) ? Recherche d'image inversée faite (aucune ressemblance avec un personnage existant) ?
3. Aucun logo, texte, carte illustrée, symbole ou couleur de la licence ? Boîtes et cartes vierges ?
4. Description et texte alternatif dans `site/config/visuels.json` sans nom de la licence ni promesse ; `site/outils/visuels.py` refuse une description d'illustration qui évoquerait plusieurs queues, des gants, des vêtements, une posture debout, une touffe orange ou un nom de la licence (Feunnec, Roussil, Feunard…), et exige « vierge » ou « sans marque » dès qu'une boîte, un étui ou une carte est décrit.
5. Fichier importé en local (`python site/outils/rapatrier_visuels.py --importer <dossier>`) : jamais servi depuis le service de génération.

### 8.4 Style et cohérence

- Même lumière que les photos (fenêtre de gauche, ombres de feuillage), même papier, même fil orange : le renard vit **dans** l'atelier, pas sur un fond abstrait.
- Un seul papier (`papier-chaud`) pour toute la page ; les cadres des illustrations y sont fondus. Les photos du propriétaire, plus froides, gardent un cadre net (photographie produit).
- Un renard par écran au plus ; jamais recadré à travers les yeux ; jamais déformé (étirement, miroir qui inverserait l'oreille la plus haute d'un visuel à l'autre sans raison).

### 8.5 Nom : Braise (nom provisoire), alternatives et recherche de marque

| Nom | Pour | Points d'attention |
|---|---|---|
| **Braise** (proposé) | Les pointes orange comme des braises sur un pelage noir ; mot français, chaleureux, facile à dire en FR et compréhensible en DE | Proximité graphique et phonétique avec **Braixen**, nom anglais d'un Pokémon renard de type Feu (« Roussil » en français) : point à trancher **en priorité** par la recherche de marque et l'avis du juriste |
| **Suie** | Le pelage noir mat ; court, singulier | Connotation « sale » possible ; prononciation difficile en allemand |
| **Kit** | Court, international ; « kit » désigne le petit du renard en anglais | Mot courant (« kit » = ensemble d'objets en français), faible caractère distinctif, nombreuses marques existantes |

Recherche par le propriétaire avant tout usage commercial (autocollants, packaging, réseaux) : **Swissreg** (IPI), EUIPO (eSearch plus), OMPI (Global Brand Database), TMview, Zefix, domaines .ch et identifiants Instagram/TikTok ; classes de Nice 16 (papeterie, autocollants), 28 (jeux, cartes à jouer), 35 (vente au détail) ; recherche d'antériorité du **dessin** (recherche d'image inversée sur les visuels de référence). Tant que rien n'est validé, le site écrit « Braise (nom provisoire) ».

## 9. Visuels (inventaire, 100 % locaux)

Treize visuels, déclarés dans **un seul fichier** (`site/config/visuels.json` : clé, dimensions, format, usage, description, texte alternatif, nature, filet mesuré) et servis **en local** : variantes WebP multi-largeurs produites par `python site/outils/rapatrier_visuels.py --importer <dossier>` dans `site/landing/assets/visuels/` (budget 250 Ko jusqu'à 1600 px, 450 Ko au-delà), source archivée hors du dossier publié (`site/visuels-sources/`, ignoré par git), métadonnées (EXIF, GPS) jamais recopiées.

| Clé | Format | Nature | Chapitre |
|---|---|---|---|
| `renard-heros` | 21:9, 2688 × 1152 | Illustration | Héro ordinateur (renard à droite, boîte noire et étuis ; moitié gauche libre) |
| `renard-heros-portrait` | 9:16, 1520 × 2688 | Illustration | Héro mobile (haut libre) ; variantes 480, 760, **1180** (390 et 393 px en densité 3) et 1520 px |
| `renard-assis` | 4:5, 1280 × 1600 | Illustration | Présentation de la mascotte |
| `renard-couche` | 4:5, 1280 × 1600 | Illustration | Page merci, confirmation |
| `renard-jour-de-drop` | 16:9, 1920 × 1086 | Illustration | « Le jour du drop » (il soulève le couvercle d'une boîte noire lumineuse : **symbole du drop**, légendé ; il n'en sort qu'une lumière, les cartes au sol sont vierges) |
| `renard-reservation` | 4:5, 1152 × 1440 | Illustration | « Réservation garantie » (clin d'œil, une pile de boîtes noires vierges à bande orange : quatre, la dernière en partie cachée par la queue) |
| `renard-alertes` | 16:9, 1920 × 1086 | Illustration | Alertes et formulaire (oreilles dressées à gauche, droite libre) |
| `renard-classeur` | 16:9, 1728 × 977 | Illustration | Collection et formats (tête au-dessus d'un classeur) |
| `renard-leman` | 21:9, 2688 × 1152 | Illustration | « Expédié depuis Genève » (quai, Jet d'eau) |
| `renard-pied-de-page` | 21:9, 2688 × 1152 | Illustration | Pied de page (il dort contre une boîte), décoratif |
| `photo-boite-etuis` | 16:9, 2000 × 1131 | Photo d'ambiance | Boîte noire, étuis rigides et cartes vierges |
| `photo-mains-sleeve` | 4:5, 1600 × 2000 | Photo d'ambiance | Mains qui glissent une carte vierge dans une pochette |
| `photo-classeur` | 3:2, 2000 × 1328 | Photo d'ambiance | Classeur ouvert, cartes vierges |

## 10. Mouvement et accessibilité

- **Un seul geste signature** : le fil orange qui se dessine au défilement (§6), et le tiret de chaque numéro qui se dessine quand le fil l'atteint. Deux mises en scène discrètes, sans minuteur ni compteur : l'illustration du héro se pose (échelle seule, `transform` uniquement, jamais d'opacité : le décor de secours ne transparaît pas et l'image principale est peinte dès sa première image, sans retarder le LCP) et le Léman recule légèrement au défilement (`animation-timeline: view()`, centré sur la corde). Apparitions sobres (opacité et translation de 16 px, 800 ms, courbe `cubic-bezier(0.22, 1, 0.36, 1)`), aucun rebond, aucune rotation 3D, aucun reflet holographique.
- `prefers-reduced-motion: reduce` coupe **toutes** les animations, transitions et effets de défilement ; le bouton « Pause des animations » (discret dans l'en-tête, libellé lu par les lecteurs d'écran, et dans le pied de page ; état mémorisé) met tout en pause pour tout le monde (WCAG 2.2.2), **défilement doux compris** (`scroll-behavior` porté par `<html>`).
- Sans JavaScript, tout le contenu est visible (les apparitions ne masquent rien sans script) et le fil est entier.
- Image indisponible : masquée à l'écran (opacité nulle et découpage), **jamais** `visibility: hidden` ni `display: none` : son texte alternatif reste dans l'arbre d'accessibilité, la silhouette de secours étant `aria-hidden` (contrôlé par `site/tests/e2e/atelier.mjs`).
- Seules l'opacité et les transformations sont animées ; aucun mouvement ne porte d'information (jamais un stock, une date, une urgence).

## 11. À faire / à ne pas faire

| À faire | À ne pas faire |
|---|---|
| Un titre immense, un paragraphe court, une image qui respire | Empiler cartes, badges et boutons sur un même écran |
| L'orange en trait (fil, filet, badge Nouveauté), le charbon en masse | L'orange en aplat de section, en dégradé, en texte sur papier |
| Des numéros de chapitre en Geist Mono, un mot d'accent en Instrument Serif | Plus d'un mot d'accent par écran ; l'italique sur un paragraphe |
| Le renard dans la lumière de l'atelier, quadrupède, une seule queue | Le renard debout, habillé, avec plusieurs queues ou un produit de la licence |
| Photos réelles sur les fiches ; photos d'ambiance neutres ailleurs | Une photo d'ambiance ou une illustration présentée comme un produit en vente |
| Statuts écrits en toutes lettres, garanties reprises mot pour mot | Compte à rebours, « plus que N », stock inventé, promesse de carte rare |
| Mention « boutique indépendante » sur chaque page | Toute imitation de la licence (couleurs, typographie, symboles) |

## 12. Nuit sur le Léman (archivée)

`DIRECTION_NUIT.md`, ses tokens (`tokens/tokens-nuit.css`) et la loutre Lumi sont **archivés** (décision du propriétaire du 06.10.2026). La landing est refaite en Atelier (10.10.2026) : les tokens Nuit restent générés comme archive documentaire, mais `site/outils/da_sync.py` refuse toute ambiance archivée et `site/outils/verifier_site.py` refuse toute mention de Lumi ou de la loutre dans le site. Aucun nouveau visuel ni texte n'utilise Lumi.

## Validation humaine requise

- [ ] **C10 bis** : valider l'ambiance « Atelier » (papier `#EFEAE1`, charbon `#1D1B19`, fil orange `#F26A1B`, rouille `#A6420C` pour les liens) et la retenue des proportions (80 / 15 / 5).
- [ ] Valider les polices **Geist**, **Instrument Serif**, **Geist Mono** (licence OFL à reconfirmer sur fonts.google.com au moment de valider) ou une alternative du §4 ; trancher Google Fonts ou auto-hébergement (nLPD).
- [ ] Valider la mascotte (fiche §8.1, règles §8.2) et **son nom** : Braise, Suie ou Kit, après la recherche de marque du §8.5 (Braixen à examiner en priorité) ; juriste : antériorité du dessin (recherche d'image inversée, ressemblance avec Feunnec / Roussil), conditions d'utilisation commerciale de l'outil de génération des illustrations, dépôt d'une **marque figurative** pour protéger Braise (protection par le droit d'auteur d'une image générée incertaine en Suisse, LDA art. 2 : `docs/04-legal/USAGE_MARQUES.md`, ligne « Mascotte illustrée générée »).
- [ ] Confirmer que les 3 photos sont bien les photos du propriétaire (droits d'auteur et droit à l'image pour la photo des mains) et qu'elles peuvent être publiées comme photos d'ambiance.
- [ ] Juriste : relire les textes alternatifs des photos d'ambiance (aucune promesse de vente d'un accessoire montré) et la mention d'indépendance.
- [ ] Valider le papier unique `#F1E4D3` (au lieu de `#FCF2E2` et de l'alternance avec `#EFEAE1`) et les **badges de statut monochromes** (plus d'indigo ni de vert ; « Réservation garantie » en boîte noire à bande orange).
- [ ] `renard-couche` (pages merci et désinscription) : derrière le corps, une touffe orange peut se lire comme un **second bout de queue** (règle « une seule queue », §8.2). Trancher : garder, faire retoucher la zone (repeindre en noir) par l'auteur des illustrations, ou régénérer le visuel ; aucune retouche n'a été faite sans accord.
- [ ] Valider la place des photos du propriétaire sur la landing (boîte et mains dans « Le soin », classeur à côté des questions sur ordinateur) et leur légende vérifiable (« Sur la boutique, chaque fiche montre la photo réelle du produit vendu »).
