# Direction B — « Pochette » (collection)

> Proposition de direction visuelle n° 2 sur 2 (BP §8). Nom de travail : **Quai des Cartes** (non validé).
> Aperçu interactif : `CHARTE.html?da=b` · fiche produit : `components/page-produit.html?da=b`.

## 1. Concept

**Le moment où l'on sort une carte de sa pochette.** Formes arrondies, cartes légèrement inclinées, une couleur vive qui évoque l'éclat d'une carte brillante sans imiter un effet holographique. Plus enthousiaste que A, toujours aussi lisible.

- **Mots-clés** : vif, rond, collection, ouverture, communauté.
- **Signature graphique** : le *point du « i » en carte inclinée* dans le logo, repris en contour violet incliné sur les visuels et la carte de remerciement.
- **Pourquoi elle sert l'étoile polaire** : plus mémorable sur les réseaux (coût d'acquisition), tout en gardant les statuts de stock explicites qui limitent le SAV. Les cartes inclinées sont des formes génériques : extensibles à tous les TCG.
- **Ce qu'elle n'est pas** : ni personnages, ni Poké Ball, ni jaune et bleu de la licence, ni dégradés arc-en-ciel imitant une carte réelle.

## 2. Palette

Fond clair neutre légèrement froid, encre bleutée, **un seul accent vif : le Violet Électrique**. Proportions : 70 % neutres, 20 % encre, 10 % accent maximum. Valeurs sources : `tokens/tokens.json`.

### Mode clair

| Token | Hex | Rôle |
|---|---|---|
| `bg` | `#F4F4F7` | Fond de page — gris clair froid |
| `surface` | `#FFFFFF` | Cartes produit, champs |
| `surface-alt` | `#E9E9F0` | Bandeaux, fond photo |
| `ink` | `#0B0B12` | Encre bleutée — texte, prix |
| `ink-muted` | `#545466` | Texte secondaire |
| `on-ink` | `#FFFFFF` | Texte sur fond encre |
| `line` | `#D8D8E2` | Filets décoratifs |
| `line-strong` | `#83839A` | Bordures de composants |
| `accent` | `#5A31F4` | **Violet Électrique** — bouton principal, point du i, badge Nouveauté |
| `on-accent` | `#FFFFFF` | Texte sur le violet (**jamais noir**) |
| `accent-text` | `#5A31F4` | Liens et chiffres clés |
| `accent-soft` | `#ECE7FF` | Teinte d'accent pour fonds de bannière |
| `focus` | `#5A31F4` | Anneau de focus clavier |
| `error` | `#B42318` | Erreurs |
| Statuts | voir tableau | Stock local (vert), Précommande (bleu nuit), Nouveauté (violet), Rupture (gris), Alerte réassort (ambre), FR (encre) |

### Mode sombre

| Token | Hex | Rôle |
|---|---|---|
| `bg` | `#0F0F17` | Fond de page |
| `surface` / `surface-alt` | `#181824` / `#222232` | Cartes, bandeaux |
| `ink` / `ink-muted` | `#F1F1F7` / `#A6A6BA` | Texte principal / secondaire |
| `line` / `line-strong` | `#2E2E40` / `#74748E` | Filets / bordures |
| `accent` / `on-accent` | `#6A4BFF` / `#FFFFFF` | Violet éclairci pour rester ≥ 4.5:1 avec le blanc |
| `accent-text` | `#A797FF` | Liens |

### Contrastes WCAG 2.x (calculés, tronqués à 2 décimales)

Seuils : texte ≥ 4.5:1 (AA), bordures de composants et focus ≥ 3:1 (WCAG 1.4.11). Tableau généré et contrôlé par `tools/generer_da.py` / `tools/verifier_da.py`.

<!-- CONTRASTES:DEBUT (généré par tools/generer_da.py, ne pas éditer) -->
| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |
|---|---|---|---|---|---|---|
| Clair | Texte courant sur fond de page | `#0B0B12` ink | `#F4F4F7` bg | **17.86:1** | 4.5 | AAA |
| Clair | Texte sur carte produit | `#0B0B12` ink | `#FFFFFF` surface | **19.61:1** | 4.5 | AAA |
| Clair | Texte sur bandeau | `#0B0B12` ink | `#E9E9F0` surface-alt | **16.22:1** | 4.5 | AAA |
| Clair | Texte sur bannière teintée | `#0B0B12` ink | `#ECE7FF` accent-soft | **16.28:1** | 4.5 | AAA |
| Clair | Texte secondaire sur fond | `#545466` ink-muted | `#F4F4F7` bg | **6.74:1** | 4.5 | AA |
| Clair | Texte secondaire sur carte | `#545466` ink-muted | `#FFFFFF` surface | **7.40:1** | 4.5 | AAA |
| Clair | Texte secondaire sur bandeau | `#545466` ink-muted | `#E9E9F0` surface-alt | **6.12:1** | 4.5 | AA |
| Clair | Bouton principal / bandeau inversé | `#FFFFFF` on-ink | `#0B0B12` ink | **19.61:1** | 4.5 | AAA |
| Clair | Texte sur accent (bouton, badge) | `#FFFFFF` on-accent | `#5A31F4` accent | **6.60:1** | 4.5 | AA |
| Clair | Lien sur fond | `#5A31F4` accent-text | `#F4F4F7` bg | **6.01:1** | 4.5 | AA |
| Clair | Lien sur carte | `#5A31F4` accent-text | `#FFFFFF` surface | **6.60:1** | 4.5 | AA |
| Clair | Lien sur bandeau | `#5A31F4` accent-text | `#E9E9F0` surface-alt | **5.46:1** | 4.5 | AA |
| Clair | Message d'erreur sur fond | `#B42318` error | `#F4F4F7` bg | **5.98:1** | 4.5 | AA |
| Clair | Message d'erreur dans un formulaire | `#B42318` error | `#FFFFFF` surface | **6.57:1** | 4.5 | AA |
| Clair | Bordure de champ sur fond (WCAG 1.4.11) | `#83839A` line-strong | `#F4F4F7` bg | **3.36:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bordure de champ sur carte (WCAG 1.4.11) | `#83839A` line-strong | `#FFFFFF` surface | **3.69:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur fond (WCAG 1.4.11) | `#5A31F4` focus | `#F4F4F7` bg | **6.01:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur carte (WCAG 1.4.11) | `#5A31F4` focus | `#FFFFFF` surface | **6.60:1** | 3.0 | UI ≥ 3:1 |
| Clair | Badge Stock local | `#0C5A2C` status-local-fg | `#DFF5E7` status-local-bg | **7.29:1** | 4.5 | AAA |
| Clair | Badge Précommande | `#1D3F8A` status-preorder-fg | `#E3ECFA` status-preorder-bg | **8.28:1** | 4.5 | AAA |
| Clair | Badge Nouveauté | `#FFFFFF` status-new-fg | `#5A31F4` status-new-bg | **6.60:1** | 4.5 | AA |
| Clair | Badge Rupture | `#46465A` status-out-fg | `#E6E6EC` status-out-bg | **7.39:1** | 4.5 | AAA |
| Clair | Badge Alerte réassort | `#674700` status-restock-fg | `#FFF0C7` status-restock-bg | **7.48:1** | 4.5 | AAA |
| Clair | Badge langue FR | `#FFFFFF` lang-fr-fg | `#0B0B12` lang-fr-bg | **19.61:1** | 4.5 | AAA |
| Sombre | Texte courant sur fond de page | `#F1F1F7` ink | `#0F0F17` bg | **16.95:1** | 4.5 | AAA |
| Sombre | Texte sur carte produit | `#F1F1F7` ink | `#181824` surface | **15.61:1** | 4.5 | AAA |
| Sombre | Texte sur bandeau | `#F1F1F7` ink | `#222232` surface-alt | **13.89:1** | 4.5 | AAA |
| Sombre | Texte sur bannière teintée | `#F1F1F7` ink | `#231C4D` accent-soft | **13.88:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur fond | `#A6A6BA` ink-muted | `#0F0F17` bg | **7.97:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur carte | `#A6A6BA` ink-muted | `#181824` surface | **7.35:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur bandeau | `#A6A6BA` ink-muted | `#222232` surface-alt | **6.54:1** | 4.5 | AA |
| Sombre | Bouton principal / bandeau inversé | `#0F0F17` on-ink | `#F1F1F7` ink | **16.95:1** | 4.5 | AAA |
| Sombre | Texte sur accent (bouton, badge) | `#FFFFFF` on-accent | `#6A4BFF` accent | **5.16:1** | 4.5 | AA |
| Sombre | Lien sur fond | `#A797FF` accent-text | `#0F0F17` bg | **7.73:1** | 4.5 | AAA |
| Sombre | Lien sur carte | `#A797FF` accent-text | `#181824` surface | **7.12:1** | 4.5 | AAA |
| Sombre | Lien sur bandeau | `#A797FF` accent-text | `#222232` surface-alt | **6.33:1** | 4.5 | AA |
| Sombre | Message d'erreur sur fond | `#FF8A80` error | `#0F0F17` bg | **8.35:1** | 4.5 | AAA |
| Sombre | Message d'erreur dans un formulaire | `#FF8A80` error | `#181824` surface | **7.69:1** | 4.5 | AAA |
| Sombre | Bordure de champ sur fond (WCAG 1.4.11) | `#74748E` line-strong | `#0F0F17` bg | **4.20:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Bordure de champ sur carte (WCAG 1.4.11) | `#74748E` line-strong | `#181824` surface | **3.87:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur fond (WCAG 1.4.11) | `#A797FF` focus | `#0F0F17` bg | **7.73:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur carte (WCAG 1.4.11) | `#A797FF` focus | `#181824` surface | **7.12:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Badge Stock local | `#8EE0A8` status-local-fg | `#10301E` status-local-bg | **9.14:1** | 4.5 | AAA |
| Sombre | Badge Précommande | `#AFC6FF` status-preorder-fg | `#17264A` status-preorder-bg | **8.73:1** | 4.5 | AAA |
| Sombre | Badge Nouveauté | `#FFFFFF` status-new-fg | `#6A4BFF` status-new-bg | **5.16:1** | 4.5 | AA |
| Sombre | Badge Rupture | `#C6C6D4` status-out-fg | `#2A2A38` status-out-bg | **8.36:1** | 4.5 | AAA |
| Sombre | Badge Alerte réassort | `#FFD978` status-restock-fg | `#382A06` status-restock-bg | **10.28:1** | 4.5 | AAA |
| Sombre | Badge langue FR | `#0F0F17` lang-fr-fg | `#F1F1F7` lang-fr-bg | **16.95:1** | 4.5 | AAA |
<!-- CONTRASTES:FIN -->

Règles qui en découlent :
- Texte **noir sur le violet interdit** (2.97:1 seulement entre `#0B0B12` et `#5A31F4`) : toujours blanc dessus.
- En mode sombre, l'accent passe à `#6A4BFF` : le violet du mode clair ne donnerait que 2.88:1 entre `#5A31F4` et `#0F0F17` (fond sombre), insuffisant pour un bouton.

## 3. Typographies (Google Fonts, licence SIL OFL)

| Rôle | Police | Graisses | Réglages | Repli |
|---|---|---|---|---|
| Titres | **Bricolage Grotesque** | 700, 800 | Bas-de-casse (phrase normale), interlettrage −1 % | Trebuchet MS, Arial |
| Texte | **DM Sans** | 400, 500, 700 | 16 px minimum sur mobile, interligne 1.5 | Helvetica Neue, Arial |
| Prix, quantités | **Space Grotesk** | 500, 700 | `font-variant-numeric: tabular-nums` | DM Sans, Arial |

Chargement : `https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=DM+Sans:opsz,wght@9..40,400..700&family=Space+Grotesk:wght@500;700&display=swap`

Vérifié le 04.10.2026 sur les fichiers servis par Google Fonts : les trois familles couvrent é è ê à ç œ « » ’ – € ; Space Grotesk et Bricolage Grotesque ont la fonction `tnum`. **DM Sans ne l'a pas** dans la version servie : ne jamais l'utiliser pour une colonne de prix.

Format des prix : `CHF 209.90` · milliers : `CHF 1’209.90` · dates : `14.11.2026`.

## 4. Grille

| Écran | Colonnes | Marge | Gouttière |
|---|---|---|---|
| Mobile < 600 px | 4 | 16 px | 16 px |
| Tablette 600–899 px | 8 | 32 px | 16 px |
| Ordinateur ≥ 900 px | 12 | auto (max 1200 px) | 24 px |

- Espacements sur base 4 px : 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Rayons : 6 / 12 / 20 px ; boutons et badges en pastille. Cartes produit sans bordure, ombre douce.
- Produits : 2 par ligne sur mobile, 4 sur ordinateur. Cible tactile ≥ 44 px.

## 5. Iconographie

- Les mêmes 12 pictogrammes que A (`components/icones.svg`), trait 2 px, grille 24 px, **extrémités et angles arrondis** (appliqué par CSS).
- Toujours accompagnés d'un libellé ; jamais de symboles de la licence.

## 6. Ton photo

- Photos **réelles** uniquement ; jamais d'emballage généré (BP §7).
- Fond papier gris clair proche de `#E9E9F0`, lumière diffuse (boîte à lumière ou fenêtre voilée), ombres douces.
- Mise en scène légère autorisée : boîtes empilées, inclinaison ≤ 10°, une main pour l'échelle. Le produit vendu reste net, entier et identifiable (langue visible).
- Pas de cartes « rares » mises en avant, pas de reflets ajoutés.

## 7. Références (inspiration, rien à copier)

| Référence | Ce qu'on retient | Ce qu'on évite |
|---|---|---|
| Culture du sticker et des fanzines | Formes arrondies, pastilles, inclinaisons ludiques | Accumulation : 1 forme décorative par visuel maximum |
| Emballages de marques indépendantes de jeux de société | Une couleur forte + beaucoup de blanc | Reprendre une illustration ou une typographie de marque |
| Pochettes et classeurs de rangement | Le geste « sortir la carte » : carte inclinée, contour | Imiter un dos de carte d'un éditeur existant |
| Applications grand public récentes | Boutons en pastille, hiérarchie douce, ombres légères | Effets néon, dégradés arc-en-ciel |

## 8. Application à une page produit

Maquette fonctionnelle : `components/page-produit.html?da=b` (données FICTIF).

```
┌─────────────────────────────┐  mobile 390 px
│ ▣ Livraison Suisse uniquement│
│ quai des cartes      (⌕)(🛒) │  logo une ligne, point du i violet
│ Accueil / Displays / …      │
│ ╭─────────────────────────╮ │
│ │  PHOTO RÉELLE 1:1       │ │  coins 12 px, fond #E9E9F0
│ ╰─────────────────────────╯ │
│ (Dos)(Langue)(Scellé)(Échelle)
│ (FR) (stock local)          │  badges pastille
│ Display — Extension — FR    │  Bricolage Grotesque 800
│ CHF 209.90                  │  Space Grotesk 700, tnum
│ ╭ En stock local ─────────╮ │
│ │ Expédié sous {{DÉLAI}}  │ │
│ │ (− 1 +) (Ajouter)       │ │  bouton violet, texte blanc
│ ╰─────────────────────────╯ │
│ Format · Langue · Contenu…  │
│ ⓘ Contenu aléatoire, aucune │
│   carte garantie            │
└─────────────────────────────┘
```

## Validation humaine requise

- [ ] Choisir A **ou** B (pas de mélange) lors de la séance unique de validation de l'identité.
- [ ] Si B : valider le Violet Électrique `#5A31F4` (et `#6A4BFF` en sombre) et la règle « texte blanc sur violet ».
- [ ] Valider les trois polices (licence OFL à reconfirmer sur fonts.google.com lors de l'intégration).
- [ ] Valider le niveau de mise en scène photo (inclinaison, main) avant la session photo groupée.
