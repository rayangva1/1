# Ambiance « Nuit sur le Léman » (bâtie sur la direction B)

> **ARCHIVÉE — remplacée par l'ambiance « Atelier » (`DIRECTION_ATELIER.md`), décision du propriétaire du 06.10.2026.**
> Le propriétaire abandonne l'ambiance nocturne et la loutre « Lumi » au profit d'une direction tirée de ses photos (papier crème, charbon mat, fil orange) et d'un renard original (« Braise », nom provisoire). Ce document est gardé pour mémoire : ne plus l'appliquer à un nouveau visuel ou à une nouvelle page. Ses tokens (`tokens/tokens-nuit.css`) restent générés tant que la landing actuelle n'est pas refaite (étape 2), puis seront retirés. Les douze visuels générés de Lumi ont été retirés de `site/config/visuels.json`.

> Proposition d'ambiance immersive pour la landing et les pages de drop, construite **sur la direction B « Pochette »** (mêmes formes arrondies, même lettrage, mêmes composants `da-*`). Nom de travail : **Quai des Cartes** (non validé). Mascotte : **Lumi** (nom provisoire, non validé).
> Sources : `tokens/tokens.json` (bloc `ambiances.nuit`, généré en `tokens/tokens-nuit.css`), `DIRECTION_B.md`, `docs/04-legal/USAGE_MARQUES.md`, `docs/04-legal/PRECOMMANDES.md` (textes de la réservation garantie). Application : `site/landing/` et `site/maquettes/`.

## 1. Concept

**Une nuit claire au bord du Léman** : un ciel indigo qui tourbillonne, des étoiles d'or, une lune rose qui se reflète dans le lac, et une loutre qui veille sur le quai. Le site devient une scène que l'on traverse en défilant ; les informations (stock réel, langue vérifiée, réservation garantie) restent écrites en toutes lettres, au premier plan.

- **Mots-clés** : nocturne, lumineux, poétique, précis, local (Genève).
- **Signature** : la **lune rose** (`lune`, `accent`) et les **croissants** de la mascotte ; l'**or des étoiles** (`or`) pour les surtitres et le focus clavier.
- **Ce qu'elle n'est pas** : ni personnage, symbole, police ou logo de la licence ; ni jaune et bleu de la licence ; ni arc-en-ciel imitant une carte réelle ; ni effet qui presse l'achat (aucun compte à rebours, aucun « plus que N »).

## 2. Activation

```html
<html lang="fr-CH" data-da="b" data-ambiance="nuit">
<link rel="stylesheet" href="assets/da/tokens.css">
<link rel="stylesheet" href="assets/da/components.css">
<link rel="stylesheet" href="assets/da/ambiance.css">   <!-- copie de tokens/tokens-nuit.css (site/outils/da_sync.py) -->
```

L'ambiance est **toujours sombre** : elle l'emporte sur le réglage clair/sombre du système (sélecteur `:root[data-ambiance="nuit"][data-da]`, chargé après `tokens.css`). Il n'y a donc plus de bouton de thème sur la landing ; il est remplacé par un bouton rond **« Pause des animations »** (icône seule, nom accessible conservé ; repris en texte dans le pied de page, voir §5).

## 3. Palette

Neutres indigo, encre clair de lune, **un accent rose lune** et deux touches de décor (or des étoiles, turquoise aurore). Proportions : 75 % nuit, 15 % clair de lune, 10 % accents au plus.

| Token | Hex | Rôle |
|---|---|---|
| `bg` | `#0B0A1F` | Fond de page — nuit indigo |
| `nuit-profonde` | `#06051A` | Pied de page, voiles de lisibilité |
| `surface` / `surface-alt` | `#16143A` / `#1F1C4D` | Panneaux de verre (opacité ≥ 82 % au-dessus d'une image), bandeaux |
| `ink` / `ink-muted` | `#F5F2FF` / `#BDB7DE` | Texte principal / secondaire |
| `line` / `line-strong` | `#2F2B66` / `#8079BD` | Filets / bordures de composants |
| `accent` / `on-accent` | `#FF6FAE` / `#1A0826` | **Rose lune** : bouton principal, **texte foncé dessus** |
| `accent-text` | `#FF9ACB` | Liens |
| `focus` | `#FFD27A` | Anneau de focus (or) |
| `or` / `or-doux` | `#FFC857` / `#FFE6A8` | Étoiles, surtitres, halos |
| `lune` | `#FF7AB8` | Lune, croissants, mots d'accent |
| `aurore` | `#5FE3C8` | Coches, reflets du lac |
| `ciel-1` à `ciel-3`, `lac-1`, `lac-2`, `papier` | voir `tokens.json` | Décor uniquement (jamais du texte) |

Règles qui en découlent :
- **Texte blanc sur le rose interdit** : 2.33:1 seulement entre `#F5F2FF` et `#FF6FAE`. Le texte d'un bouton rose est toujours `on-accent` (7.35:1 entre `#1A0826` et `#FF6FAE`).
- Un panneau de verre posé sur une image garde au moins 82 % d'opacité de `surface` (`--lp-verre` 86 %, `--lp-verre-fort` 94 %) : les ratios ci-dessous restent alors ≥ 4.5:1 pour le texte principal même sur une zone claire de l'image.
- **Texte posé sur une illustration** (héro, bandeaux Léman et Aube) : toujours sur un voile `nuit-profonde` d'au moins 82 % sous le texte courant et 76 % sous un grand titre. Calcul du pire cas (pixel blanc pur sous un voile à 82 %) : fond résultant `#333243`, soit 11.34:1 pour `ink`, 6.55:1 pour `ink-muted`, 8.14:1 pour l'or et 5.20:1 pour le rose `lune` ; à 76 % (`#424151`) : 9.03:1 pour `ink` et 4.14:1 pour `lune` (grand titre, seuil 3:1). Vérifié par `site/tests/test_landing_e2e.py` (images remplacées par du blanc, 1440, 1024 et 390 px). Sur mobile, le texte des bandeaux passe **sous** l'image, jamais dessus.
- **Une seule lune visible par écran** : la lune en croissant du héro (décor de secours), avec un écho dans le pied de page ; ailleurs, un soleil couchant (Léman) ou la lumière d'une boîte (drop).
- Les couleurs de décor (`ciel-*`, `lac-*`, `papier`) ne portent jamais de texte, sauf la légende `lac-1` sur `papier` contrôlée ci-dessous.

### Contrastes WCAG 2.x (calculés, tronqués à 2 décimales)

Seuils : texte ≥ 4.5:1 (AA), bordures, focus et boutons ≥ 3:1 (WCAG 1.4.11). Tableau généré et contrôlé par `tools/generer_da.py` / `tools/verifier_da.py` (paires communes aux directions + paires propres aux ambiances).

<!-- CONTRASTES:DEBUT (généré par tools/generer_da.py, ne pas éditer) -->
| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |
|---|---|---|---|---|---|---|
| Sombre | Texte courant sur fond de page | `#F5F2FF` ink | `#0B0A1F` bg | **17.65:1** | 4.5 | AAA |
| Sombre | Texte sur carte produit | `#F5F2FF` ink | `#16143A` surface | **15.91:1** | 4.5 | AAA |
| Sombre | Texte sur bandeau | `#F5F2FF` ink | `#1F1C4D` surface-alt | **14.28:1** | 4.5 | AAA |
| Sombre | Texte sur bannière teintée | `#F5F2FF` ink | `#3A1745` accent-soft | **13.70:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur fond | `#BDB7DE` ink-muted | `#0B0A1F` bg | **10.20:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur carte | `#BDB7DE` ink-muted | `#16143A` surface | **9.19:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur bandeau | `#BDB7DE` ink-muted | `#1F1C4D` surface-alt | **8.25:1** | 4.5 | AAA |
| Sombre | Bouton principal / bandeau inversé | `#0B0A1F` on-ink | `#F5F2FF` ink | **17.65:1** | 4.5 | AAA |
| Sombre | Texte sur accent (bouton, badge) | `#1A0826` on-accent | `#FF6FAE` accent | **7.35:1** | 4.5 | AAA |
| Sombre | Lien sur fond | `#FF9ACB` accent-text | `#0B0A1F` bg | **9.96:1** | 4.5 | AAA |
| Sombre | Lien sur carte | `#FF9ACB` accent-text | `#16143A` surface | **8.98:1** | 4.5 | AAA |
| Sombre | Lien sur bandeau | `#FF9ACB` accent-text | `#1F1C4D` surface-alt | **8.06:1** | 4.5 | AAA |
| Sombre | Message d'erreur sur fond | `#FF8F87` error | `#0B0A1F` bg | **8.84:1** | 4.5 | AAA |
| Sombre | Message d'erreur dans un formulaire | `#FF8F87` error | `#16143A` surface | **7.97:1** | 4.5 | AAA |
| Sombre | Bordure de champ sur fond (WCAG 1.4.11) | `#8079BD` line-strong | `#0B0A1F` bg | **5.00:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Bordure de champ sur carte (WCAG 1.4.11) | `#8079BD` line-strong | `#16143A` surface | **4.50:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur fond (WCAG 1.4.11) | `#FFD27A` focus | `#0B0A1F` bg | **13.69:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur carte (WCAG 1.4.11) | `#FFD27A` focus | `#16143A` surface | **12.34:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Badge Stock local | `#8FF0C3` status-local-fg | `#0E3227` status-local-bg | **10.25:1** | 4.5 | AAA |
| Sombre | Badge Précommande | `#BCCBFF` status-preorder-fg | `#1B2560` status-preorder-bg | **8.86:1** | 4.5 | AAA |
| Sombre | Badge Nouveauté | `#1A0826` status-new-fg | `#FF6FAE` status-new-bg | **7.35:1** | 4.5 | AAA |
| Sombre | Badge Rupture | `#D2CEEB` status-out-fg | `#27254A` status-out-bg | **9.49:1** | 4.5 | AAA |
| Sombre | Badge Alerte réassort | `#FFD978` status-restock-fg | `#3B2B07` status-restock-bg | **10.06:1** | 4.5 | AAA |
| Sombre | Badge langue FR | `#0B0A1F` lang-fr-fg | `#F5F2FF` lang-fr-bg | **17.65:1** | 4.5 | AAA |
| Sombre | Surtitre or sur fond de page | `#FFC857` or | `#0B0A1F` bg | **12.67:1** | 4.5 | AAA |
| Sombre | Surtitre or sur panneau | `#FFC857` or | `#16143A` surface | **11.42:1** | 4.5 | AAA |
| Sombre | Mot d'accent rose sur fond de page | `#FF7AB8` lune | `#0B0A1F` bg | **8.10:1** | 4.5 | AAA |
| Sombre | Mot d'accent rose sur panneau | `#FF7AB8` lune | `#16143A` surface | **7.30:1** | 4.5 | AAA |
| Sombre | Coche et libellé turquoise sur fond | `#5FE3C8` aurore | `#0B0A1F` bg | **12.35:1** | 4.5 | AAA |
| Sombre | Coche et libellé turquoise sur panneau | `#5FE3C8` aurore | `#16143A` surface | **11.13:1** | 4.5 | AAA |
| Sombre | Texte du pied de page | `#F5F2FF` ink | `#06051A` nuit-profonde | **18.21:1** | 4.5 | AAA |
| Sombre | Texte secondaire du pied de page | `#BDB7DE` ink-muted | `#06051A` nuit-profonde | **10.52:1** | 4.5 | AAA |
| Sombre | Texte sur encart rose | `#F5F2FF` ink | `#3A1745` accent-soft | **13.70:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur encart rose | `#BDB7DE` ink-muted | `#3A1745` accent-soft | **7.91:1** | 4.5 | AAA |
| Sombre | Anneau de focus sur bandeau (WCAG 1.4.11) | `#FFD27A` focus | `#1F1C4D` surface-alt | **11.07:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Bordure de champ sur bandeau (WCAG 1.4.11) | `#8079BD` line-strong | `#1F1C4D` surface-alt | **4.04:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Bouton rose sur fond de page (WCAG 1.4.11) | `#FF6FAE` accent | `#0B0A1F` bg | **7.55:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Badge clair de lune | `#0B0A1F` on-ink | `#F5F2FF` ink | **17.65:1** | 4.5 | AAA |
| Sombre | Légende indigo sur planche blanc cassé | `#0D2052` lac-1 | `#F6F1E7` papier | **13.86:1** | 4.5 | AAA |
<!-- CONTRASTES:FIN -->

## 4. Typographies (Google Fonts, licence SIL OFL)

| Rôle | Police | Réglages | Repli |
|---|---|---|---|
| Grands titres | **Bricolage Grotesque** 700–800, optique 96 | Bas-de-casse, interlettrage −2,5 %, interligne 0.95 | Trebuchet MS, Arial |
| Mots d'accent | **Fraunces** italique 500, SOFT 100, optique 144 (instance fixe, plus légère) | Un à quatre mots par titre, un titre sur deux au plus, jamais un paragraphe | Georgia |
| Texte | **DM Sans** 400/500/700 | 16 px minimum, interligne 1.6 | Helvetica Neue, Arial |
| Dates, surtitres, prix | **DM Sans** 600 | `tabular-nums` ; surtitres en capitales espacées (0.8125 rem, +14 %) | Helvetica Neue, Arial |

URL : `tokens.json > ambiances > nuit > googleFonts` (appliquée à chaque page par `site/outils/da_sync.py`). Sans Google Fonts (`publication.py --sans-google-fonts`), les replis restent lisibles.

## 5. Mouvement

- **Récit « la nuit avance »** : un visuel par chapitre — héro (nuit étoilée), Lumi (planche et autocollant), jour du drop, réservation garantie, aube des alertes (aurore), Léman (Alpes au coucher, jet d'eau sur mobile), quai la nuit (pied de page). Mises en page variées : plein écran, alternance gauche/droite, frise typographique, bandeaux plein cadre, manifeste typographique. Mot d'accent italique rose sur un titre sur deux au plus.
- **Moment signature, piloté par le défilement** (CSS `animation-timeline`, amélioration progressive) : la peinture du héro s'approche, le titre s'élève et s'efface, la lune monte et son reflet s'allonge sur le lac ; chaque chapitre teinte la nuit à son passage (or du drop, rose de la réservation, turquoise de l'aube) ; la bordure du formulaire fait un seul tour en entrant dans l'écran. L'autocollant de Lumi « se décolle » au survol.
- **Décor de secours** (si une illustration ne charge pas) : ciel tourbillonnant au trait de pinceau (SVG, filtre de turbulence, 180 s le tour), lune en croissant qui « respire » (halo seul, opacité et échelle), étoiles qui scintillent, étoile filante rare, et Lumi dessinée (silhouette assise sur le quai, bustes de la planche). Il disparaît dès que l'illustration est chargée (classe `a-visuel`) : jamais deux lunes ni une trame d'étoiles par-dessus la peinture.
- **Apparitions** au défilement (IntersectionObserver, 900 ms, courbe `cubic-bezier(0.22, 1, 0.36, 1)`), cartes « verre dépoli » avec **survol 3D léger** et reflet nacré **limité à la palette** (rose, or, turquoise) : jamais un arc-en-ciel imitant une carte réelle.
- **Accessibilité** : `prefers-reduced-motion: reduce` coupe **toutes** les animations, transitions et effets de défilement ; le bouton « Pause des animations » (en-tête et pied de page, état mémorisé) met tout en pause pour tout le monde (WCAG 2.2.2). Sans JavaScript, tout le contenu est visible (les apparitions ne masquent rien sans script).
- **Coût de rendu** : seules l'opacité et les transformations sont animées (aucune ombre animée) ; le flou d'arrière-plan est réservé à l'en-tête défilé et au formulaire ; `will-change` seulement pendant un survol.
- Aucun mouvement ne porte d'information : une animation n'annonce jamais un stock, une date ou une urgence.

## 6. Mascotte : Lumi (nom provisoire)

Loutre **originale** créée pour la boutique : fourrure indigo profond, **marques en croissant de lune roses** lumineuses sur les joues et le dos, grands yeux doux, queue plate terminée par une forme de carte qui brille en rose.

| À faire | À ne jamais faire |
|---|---|
| Afficher « Lumi (nom provisoire) » tant que le nom n'est pas validé | Présenter Lumi comme un personnage de la licence, ou lui faire porter un symbole, une Poké Ball, une énergie, un type |
| Garder les croissants en **forme de croissant** (jamais des disques sur les joues), le pelage indigo, la queue-carte rose | Lui donner du jaune vif, des joues rondes rouges, des oreilles pointues de créature connue, une silhouette rappelant un personnage existant |
| L'utiliser comme narratrice douce : elle veille, garde, salue | La faire tenir, ouvrir ou désigner un **produit réel** ; lui faire dire « dernière chance », « vite », un prix ou un stock |
| Montrer des **boîtes blanches génériques** (sans logo, sans texte, sans illustration) comme symbole de « produit scellé » | Générer un emballage, une carte ou un logo de produit (BP §7 ; `USAGE_MARQUES.md` : « Tout emballage, carte, personnage ou logo Pokémon généré par IA » est interdit) |

- Expressions disponibles (planche) : contente, surprise, endormie, serre une boîte, salue. Autocollant rond pour le packaging.
- Les visuels de la mascotte sont des **illustrations de marque** : ils ne remplacent jamais une photo réelle de produit (fiche produit : photo réelle uniquement, `DIRECTION_B.md` §6).

## 7. Visuels générés pour la marque

- Douze visuels générés pour la marque avec Higgsfield (fichiers `hf_…` ; bannières 21:9 et 16:9, couvertures 9:16, planche d'expressions, autocollant) listés dans **un seul fichier** : `site/config/visuels.json` (adresse distante, dimensions, usage). Les pages ne contiennent que des balises `data-visuel="…"` synchronisées par `site/outils/visuels.py`.
- **Aperçu** : images servies par l'adresse distante. **Publication** : refusée tant que les images ne sont pas rapatriées en local (`python site/outils/rapatrier_visuels.py`) ; la politique de sécurité de la page publiée n'autorise que les images du site.
- Chaque emplacement d'image a un **fond de secours** dessiné en CSS et SVG (ciel, lune, lac, montagnes, Lumi) : la page reste belle si une image ne charge pas, et ce décor est masqué dès que l'illustration arrive.
- **Poids** : en aperçu, seule la variante légère `_min.webp` est chargée (jamais la PNG haute définition). Au rapatriement, la PNG d'origine est archivée hors du dossier publié et des variantes WebP sont produites à plusieurs largeurs (`largeurs` du manifeste), dans un budget de 250 Ko jusqu'à 1600 px et 450 Ko au-delà ; le `srcset` ne liste que ces variantes, et `sizes` tient compte du recadrage `object-fit: cover` du héro.
- Texte alternatif descriptif pour chaque image porteuse de sens ; `alt=""` pour les images purement décoratives.

## Validation humaine requise

- [x] **C10** : ambiance « Nuit sur le Léman » **non retenue** (décision du propriétaire du 06.10.2026, remplacée par « Atelier » : `DIRECTION_ATELIER.md`).
- [ ] Après la refonte de la landing en ambiance Atelier (étape 2) : confirmer le retrait des tokens Nuit (`tokens.json > ambiances > nuit`, `tokens/tokens-nuit.css`, `logo/b/logo-b-nuit.svg`).
- Les autres points (rose lune, or du focus, Fraunces, mascotte Lumi, visuels générés de Lumi) sont **sans objet** : l'ambiance et la mascotte sont abandonnées.
