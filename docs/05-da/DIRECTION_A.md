# Direction A — « Quai » (signal)

> Proposition de direction visuelle n° 1 sur 2 (BP §8). Nom de travail : **Quai des Cartes** (non validé).
> Aperçu interactif : `CHARTE.html` (bouton « Direction A ») · fiche produit : `components/page-produit.html?da=a`.

## 1. Concept

**La signalétique d'un quai et l'étiquette d'un colis bien préparé.** Tout est lisible au premier coup d'œil : où est le produit, quelle langue, est-il en stock, combien il coûte. Le ton visuel est celui d'un service fiable plutôt que d'un magasin de jouets.

- **Mots-clés** : précis, net, suisse, logistique, confiance.
- **Signature graphique** : la *barre-quai* — un trait orange horizontal sous le logo, en bas des visuels et des cartes de remerciement. Il évoque le bord du quai d'où partent les commandes.
- **Pourquoi elle sert l'étoile polaire** (contribution nette cumulée) : la clarté réduit les erreurs d'achat (langue, format), donc le SAV et les retours ; les gabarits sont sobres et rapides à produire, donc peu coûteux ; elle reste valable si la boutique ajoute d'autres jeux.
- **Ce qu'elle n'est pas** : ni personnages, ni Poké Ball, ni jaune et bleu de la licence, ni effets « holo » criards.

## 2. Palette

Fond clair neutre, contraste noir, **un seul accent vif : l'Orange Signal**. Proportions : 70 % neutres, 20 % encre, 10 % accent maximum. Valeurs sources : `tokens/tokens.json`.

### Mode clair

| Token | Hex | Rôle |
|---|---|---|
| `bg` | `#F6F5F1` | Fond de page — « papier quai », neutre chaud |
| `surface` | `#FFFFFF` | Cartes produit, champs, modales |
| `surface-alt` | `#ECEAE4` | Bandeaux, fond photo, sections alternées |
| `ink` | `#111111` | Encre — texte, prix, bouton principal |
| `ink-muted` | `#55534E` | Texte secondaire |
| `on-ink` | `#FFFFFF` | Texte sur fond encre |
| `line` | `#D9D6CF` | Filets décoratifs (aucune information) |
| `line-strong` | `#8A867E` | Bordures de champs et de composants |
| `accent` | `#FF5B14` | **Orange Signal** — barre-quai, badge Nouveauté, surlignage |
| `on-accent` | `#111111` | Texte sur l'orange (**jamais blanc**) |
| `accent-text` | `#B33F00` | Orange lisible en texte : liens, chiffres clés |
| `accent-soft` | `#FFE4D6` | Teinte d'accent pour fonds |
| `focus` | `#111111` | Anneau de focus clavier |
| `error` | `#B42318` | Erreurs de formulaire, paiement refusé |
| Statuts | voir tableau | Stock local (vert), Précommande (indigo), Nouveauté (orange), Rupture (gris), Alerte réassort (ambre), FR (noir) |

### Mode sombre

| Token | Hex | Rôle |
|---|---|---|
| `bg` | `#121212` | Fond de page |
| `surface` / `surface-alt` | `#1C1C1B` / `#262624` | Cartes, bandeaux |
| `ink` / `ink-muted` | `#F2F1ED` / `#A9A6A0` | Texte principal / secondaire |
| `line` / `line-strong` | `#34332F` / `#7A7770` | Filets / bordures |
| `accent` / `on-accent` | `#FF6A2B` / `#111111` | Orange Signal, texte noir dessus |
| `accent-text` | `#FF8A55` | Liens |

### Contrastes WCAG 2.x (calculés, tronqués à 2 décimales)

Seuils : texte ≥ 4.5:1 (AA), bordures de composants et focus ≥ 3:1 (WCAG 1.4.11). Tableau généré et contrôlé par `tools/generer_da.py` / `tools/verifier_da.py`.

<!-- CONTRASTES:DEBUT (généré par tools/generer_da.py, ne pas éditer) -->
| Mode | Usage | Avant-plan | Arrière-plan | Ratio | Seuil | Niveau |
|---|---|---|---|---|---|---|
| Clair | Texte courant sur fond de page | `#111111` ink | `#F6F5F1` bg | **17.30:1** | 4.5 | AAA |
| Clair | Texte sur carte produit | `#111111` ink | `#FFFFFF` surface | **18.88:1** | 4.5 | AAA |
| Clair | Texte sur bandeau | `#111111` ink | `#ECEAE4` surface-alt | **15.69:1** | 4.5 | AAA |
| Clair | Texte sur bannière teintée | `#111111` ink | `#FFE4D6` accent-soft | **15.57:1** | 4.5 | AAA |
| Clair | Texte secondaire sur fond | `#55534E` ink-muted | `#F6F5F1` bg | **7.04:1** | 4.5 | AAA |
| Clair | Texte secondaire sur carte | `#55534E` ink-muted | `#FFFFFF` surface | **7.68:1** | 4.5 | AAA |
| Clair | Texte secondaire sur bandeau | `#55534E` ink-muted | `#ECEAE4` surface-alt | **6.38:1** | 4.5 | AA |
| Clair | Bouton principal / bandeau inversé | `#FFFFFF` on-ink | `#111111` ink | **18.88:1** | 4.5 | AAA |
| Clair | Texte sur accent (bouton, badge) | `#111111` on-accent | `#FF5B14` accent | **6.07:1** | 4.5 | AA |
| Clair | Lien sur fond | `#B33F00` accent-text | `#F6F5F1` bg | **5.30:1** | 4.5 | AA |
| Clair | Lien sur carte | `#B33F00` accent-text | `#FFFFFF` surface | **5.78:1** | 4.5 | AA |
| Clair | Lien sur bandeau | `#B33F00` accent-text | `#ECEAE4` surface-alt | **4.81:1** | 4.5 | AA |
| Clair | Message d'erreur sur fond | `#B42318` error | `#F6F5F1` bg | **6.02:1** | 4.5 | AA |
| Clair | Message d'erreur dans un formulaire | `#B42318` error | `#FFFFFF` surface | **6.57:1** | 4.5 | AA |
| Clair | Bordure de champ sur fond (WCAG 1.4.11) | `#8A867E` line-strong | `#F6F5F1` bg | **3.32:1** | 3.0 | UI ≥ 3:1 |
| Clair | Bordure de champ sur carte (WCAG 1.4.11) | `#8A867E` line-strong | `#FFFFFF` surface | **3.62:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur fond (WCAG 1.4.11) | `#111111` focus | `#F6F5F1` bg | **17.30:1** | 3.0 | UI ≥ 3:1 |
| Clair | Anneau de focus sur carte (WCAG 1.4.11) | `#111111` focus | `#FFFFFF` surface | **18.88:1** | 3.0 | UI ≥ 3:1 |
| Clair | Badge Stock local | `#0F5A2A` status-local-fg | `#E3F4E8` status-local-bg | **7.30:1** | 4.5 | AAA |
| Clair | Badge Précommande | `#2B3990` status-preorder-fg | `#E6E9FB` status-preorder-bg | **8.32:1** | 4.5 | AAA |
| Clair | Badge Nouveauté | `#111111` status-new-fg | `#FF5B14` status-new-bg | **6.07:1** | 4.5 | AA |
| Clair | Badge Rupture | `#4A4843` status-out-fg | `#E7E5E0` status-out-bg | **7.25:1** | 4.5 | AAA |
| Clair | Badge Alerte réassort | `#6B4A00` status-restock-fg | `#FFF1CC` status-restock-bg | **7.18:1** | 4.5 | AAA |
| Clair | Badge langue FR | `#FFFFFF` lang-fr-fg | `#111111` lang-fr-bg | **18.88:1** | 4.5 | AAA |
| Sombre | Texte courant sur fond de page | `#F2F1ED` ink | `#121212` bg | **16.57:1** | 4.5 | AAA |
| Sombre | Texte sur carte produit | `#F2F1ED` ink | `#1C1C1B` surface | **15.09:1** | 4.5 | AAA |
| Sombre | Texte sur bandeau | `#F2F1ED` ink | `#262624` surface-alt | **13.41:1** | 4.5 | AAA |
| Sombre | Texte sur bannière teintée | `#F2F1ED` ink | `#3A1E10` accent-soft | **13.53:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur fond | `#A9A6A0` ink-muted | `#121212` bg | **7.71:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur carte | `#A9A6A0` ink-muted | `#1C1C1B` surface | **7.02:1** | 4.5 | AAA |
| Sombre | Texte secondaire sur bandeau | `#A9A6A0` ink-muted | `#262624` surface-alt | **6.24:1** | 4.5 | AA |
| Sombre | Bouton principal / bandeau inversé | `#121212` on-ink | `#F2F1ED` ink | **16.57:1** | 4.5 | AAA |
| Sombre | Texte sur accent (bouton, badge) | `#111111` on-accent | `#FF6A2B` accent | **6.60:1** | 4.5 | AA |
| Sombre | Lien sur fond | `#FF8A55` accent-text | `#121212` bg | **8.04:1** | 4.5 | AAA |
| Sombre | Lien sur carte | `#FF8A55` accent-text | `#1C1C1B` surface | **7.32:1** | 4.5 | AAA |
| Sombre | Lien sur bandeau | `#FF8A55` accent-text | `#262624` surface-alt | **6.51:1** | 4.5 | AA |
| Sombre | Message d'erreur sur fond | `#FF8A80` error | `#121212` bg | **8.20:1** | 4.5 | AAA |
| Sombre | Message d'erreur dans un formulaire | `#FF8A80` error | `#1C1C1B` surface | **7.47:1** | 4.5 | AAA |
| Sombre | Bordure de champ sur fond (WCAG 1.4.11) | `#7A7770` line-strong | `#121212` bg | **4.19:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Bordure de champ sur carte (WCAG 1.4.11) | `#7A7770` line-strong | `#1C1C1B` surface | **3.81:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur fond (WCAG 1.4.11) | `#F2F1ED` focus | `#121212` bg | **16.57:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Anneau de focus sur carte (WCAG 1.4.11) | `#F2F1ED` focus | `#1C1C1B` surface | **15.09:1** | 3.0 | UI ≥ 3:1 |
| Sombre | Badge Stock local | `#8EE0A8` status-local-fg | `#12331F` status-local-bg | **8.80:1** | 4.5 | AAA |
| Sombre | Badge Précommande | `#B7C0FF` status-preorder-fg | `#1C2250` status-preorder-bg | **8.60:1** | 4.5 | AAA |
| Sombre | Badge Nouveauté | `#111111` status-new-fg | `#FF6A2B` status-new-bg | **6.60:1** | 4.5 | AA |
| Sombre | Badge Rupture | `#C9C6BF` status-out-fg | `#2C2B28` status-out-bg | **8.30:1** | 4.5 | AAA |
| Sombre | Badge Alerte réassort | `#FFD978` status-restock-fg | `#3A2C05` status-restock-bg | **10.01:1** | 4.5 | AAA |
| Sombre | Badge langue FR | `#111111` lang-fr-fg | `#F2F1ED` lang-fr-bg | **16.70:1** | 4.5 | AAA |
<!-- CONTRASTES:FIN -->

Règles qui en découlent :
- Texte **blanc sur l'orange interdit** (3.10:1 seulement entre `#FFFFFF` et `#FF5B14`) : toujours noir dessus.
- L'orange `#FF5B14` n'est **jamais** utilisé pour du texte sur fond clair : prendre `accent-text` `#B33F00`.
- La barre-quai est décorative : son contraste avec le fond n'est pas une exigence, mais elle n'est jamais le seul porteur d'une information.

## 3. Typographies (Google Fonts, licence SIL OFL)

| Rôle | Police | Graisses | Réglages | Repli |
|---|---|---|---|---|
| Titres | **Archivo** | 700, 800 | Capitales, largeur 112 % (axe `wdth`), interlettrage +1 % | Arial Narrow, Arial |
| Texte | **Inter** | 400, 500, 600, 700 | 16 px minimum sur mobile, interligne 1.5 | Helvetica Neue, Arial |
| Prix, quantités, n° de commande | **IBM Plex Mono** | 500, 600 | Chasse fixe : les chiffres s'alignent en colonne | Courier New |

Chargement : `https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=Inter:opsz,wght@14..32,400..700&family=IBM+Plex+Mono:wght@500;600&display=swap`

Vérifié le 04.10.2026 sur les fichiers servis par Google Fonts : les trois familles couvrent é è ê à ç œ « » ’ – € ; Archivo et Inter ont la fonction OpenType `tnum` (chiffres tabulaires).

Format des prix : `CHF 209.90` · milliers : `CHF 1’209.90` · dates : `14.11.2026`.

## 4. Grille

| Écran | Colonnes | Marge | Gouttière |
|---|---|---|---|
| Mobile < 600 px | 4 | 16 px | 16 px |
| Tablette 600–899 px | 8 | 32 px | 16 px |
| Ordinateur ≥ 900 px | 12 | auto (max 1200 px) | 24 px |

- Espacements sur base 4 px : 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Rayons : 2 / 4 / 8 px — angles presque vifs. Bordure supérieure noire de 4 px sur les cartes produit (« étiquette »).
- Produits : 2 par ligne sur mobile, 4 sur ordinateur. Cible tactile ≥ 44 px.

## 5. Iconographie

- 12 pictogrammes originaux (`components/icones.svg`) : trait 2 px, grille 24 px, **extrémités carrées**, couleur du texte.
- Toujours accompagnés d'un libellé (« Stock local », « Précommande »…).
- Interdits : symboles d'énergie/types, Poké Ball, éclairs façon personnage, silhouettes de créatures.

## 6. Ton photo

- Photos **réelles** uniquement (visuels officiels autorisés par écrit ou photos maison) ; jamais d'emballage généré (BP §7).
- Fond papier gris chaud proche de `#ECEAE4`, lumière du jour latérale, **ombre courte et nette** (comme un objet posé sur un quai).
- Boîte de face, droite, centrée ; produit ≈ 70 % du cadre 1:1 ; mention de langue lisible sur au moins une vue.
- Retouche limitée : exposition, recadrage, détourage. Pas de reflets ajoutés, pas de cartes « rares » mises en scène.

## 7. Références (inspiration, rien à copier)

| Référence | Ce qu'on retient | Ce qu'on évite |
|---|---|---|
| Style typographique international (graphisme suisse, années 1950–60) | Grille stricte, hiérarchie par la taille et la graisse, asymétrie calme | Austérité totale : on garde un accent vif |
| Signalétique de quais, gares et ports | Lisible de loin, codes de couleur fonctionnels, pictogrammes simples | Copier un pictogramme ou une charte de transporteur existant (marques protégées) |
| Étiquettes logistiques et bons de livraison | Données nettes, chiffres en chasse fixe, cases à cocher | Code-barres décoratifs « factices » |
| Boutiques en ligne sobres de produits techniques | Fiches denses mais aérées, statut de stock visible | Badges promotionnels agressifs |

## 8. Application à une page produit

Maquette fonctionnelle : `components/page-produit.html` (données FICTIF, bouton « Direction A »).

```
┌─────────────────────────────┐  mobile 390 px
│ ▣ Livraison Suisse uniquement│  bandeau encre, texte blanc
│ QUAI DES CARTES ▔▔▔   ⌕ 🛒   │  logo horizontal + barre-quai
│ Accueil / Displays / …      │
│ ┌─────────────────────────┐ │
│ │  PHOTO RÉELLE 1:1       │ │  face avant, fond #ECEAE4
│ └─────────────────────────┘ │
│ [Dos][Langue][Scellé][Échelle]
│ [FR] [STOCK LOCAL]          │  badges : texte + icône
│ DISPLAY — EXTENSION — FR    │  Archivo 800 capitales
│ CHF 209.90                  │  IBM Plex Mono 600
│ {{MENTION_TVA}} · livraison │
│ ┌ En stock local ─────────┐ │  statut écrit en toutes lettres
│ │ Expédié sous {{DÉLAI}}  │ │
│ │ [− 1 +] [AJOUTER]       │ │  bouton encre, 44 px
│ └─────────────────────────┘ │
│ Format · Langue · Contenu…  │  faits vérifiés
│ ⓘ Contenu aléatoire, aucune │  pas de promesse de valeur
│   carte garantie            │
└─────────────────────────────┘
```

## Validation humaine requise

- [ ] Choisir A **ou** B (pas de mélange) lors de la séance unique de validation de l'identité.
- [ ] Si A : valider l'Orange Signal `#FF5B14` et la règle « texte noir sur orange ».
- [ ] Valider les trois polices (et vérifier leur licence OFL sur fonts.google.com au moment de l'intégration du thème).
- [ ] Valider le ton photo avant la session photo groupée (matériel, fond, lumière).
