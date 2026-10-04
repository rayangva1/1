# Modèle de fiche produit — {{NOM_BOUTIQUE}}

> Propriétaire (build) : agent « site-contenu ». Utilisateurs : agent 04 Catalogue (données), agent 08 SEO et rédaction (textes), agent 05 (prix), agent 12 (contrôle avant publication).
> Source : BP §7 « Fiche produit standard » : titre exact format + extension + langue ; SKU stable et EAN lorsqu'il existe ; contenu validé ; photos officielles autorisées ou photos propres, jamais d'emballage généré ; prix public en CHF ; frais de livraison accessibles ; quantité autorisée ; état du stock explicite ; délai réaliste ; date de sortie confirmée ou statut incertain ; conditions des commandes mixtes et précommandes ; description et guide d'usage simples ; **aucune promesse de carte rare ou de valeur financière future**. Aussi : BP §5 (champ inconnu ⇒ brouillon), SPEC §0.2-0.5, `docs/04-legal/USAGE_MARQUES.md`.

## 1. Règle d'entrée : une fiche incomplète reste en brouillon

Une fiche ne passe en « Active » que si **chaque** ligne du §2 marquée « obligatoire » est remplie et sourcée. Un champ inconnu (frais, taxe, langue, conditionnement, contenu) ⇒ **brouillon, aucun prix public nouveau** (BP §5). La publication est faite par le workflow (niveau d'autonomie 3) ou par l'agent 07 après contrôle de l'agent 12.

## 2. Champs de la fiche

| # | Champ Shopify | Obligatoire | Règle | Source autorisée | Interdit |
|---|---|---|---|---|---|
| 1 | Titre | Oui | `{Format} {précision de contenu} — {Extension exacte} — FR` | Emballage FR + fiche technique confirmée | Traduction maison, abréviation trompeuse, « Pokémon Shop », « officiel » |
| 2 | Type de produit | Oui | Libellé FR du format (`catalog.FORMAT_LABELS_FR`) | Moteur | Type libre |
| 3 | SKU (variante) | Oui | `{FMT}-{CODEEXT}-{LANGUE}[-{VAR}]` en majuscules, stable à vie : `DSP` display, `HDSP` demi-display, `ETB`, `BDL` bundle, `TRI` tripack, `COF` coffret, `TIN`, `BOO` booster, `ACC` accessoire ; `-PRECO` pour la variante de précommande | Catalogue | Réutiliser un SKU pour un autre produit |
| 4 | Code-barres (EAN/GTIN) | Si existe | GTIN réel lu sur la fiche technique **et** contrôlé à réception ; somme de contrôle valide (`catalog.validate_gtin`) | Fiche technique, emballage | Inventer un EAN ; publier un GTIN de test `200…` (réservé aux données FICTIVES) ; un GTIN de carton (GTIN-14) |
| 5 | Métachamp `boutique.langue` | Oui | `FR` | Catalogue, contrôle à réception | Langue supposée d'après le titre du fournisseur |
| 6 | Métachamp `boutique.extension` | Oui | Nom exact FR | Emballage FR | Nom anglais ou abrégé |
| 7 | Métachamp `boutique.contenu_valide` | Oui | Contenu confirmé par écrit : nombre de boosters, accessoires, promos éventuelles | Fiche technique confirmée, contrôle à réception | « Contenu probable », contenu d'une autre langue |
| 8 | Photos | Oui (≥ 1) | Photos propres (session A06) ou visuels avec autorisation **écrite** (registre `USAGE_MARQUES.md` §4.1) ; fond neutre ; produit scellé tel que vendu | Session photo, registre des autorisations | Emballage généré par IA, photo d'un autre site, photo d'une autre langue, carte « mise en avant » |
| 9 | Texte alternatif des photos | Oui | Description factuelle : « Display 36 boosters Extension X, version française, face avant » | Rédaction | Mots-clés empilés |
| 10 | Prix (CHF) | Oui | Prix du moteur (`pricing.decide_price`) au statut `OK` (ou `REVIEW` validé) ; terminaison .90 ; jamais changé sur une commande conclue | Moteur | Prix saisi à la main ; prix barré sans prix antérieur réel (OIP) ; prix sous le plancher dur (stop-loss produit) |
| 11 | Frais de livraison | Oui (lien) | Lien vers la page Livraison et retours ; montant affiché au panier avant paiement | `LIVRAISON_RETOURS.md` | « Livraison gratuite » non calculée par le moteur |
| 12 | Quantité maximale (`boutique.quantite_max`) | Oui pour nouveautés et précommandes | `LIMITE_PAR_CLIENT` validé | Registre légal | Limite affichée mais non appliquée |
| 13 | Statut de stock (`boutique.statut_stock`) | Oui | `stock_local` · `precommande` · `rupture` (§3) | `stock.availability_promise` | Stock d'un tiers présenté comme disponible ; précommande sans allocation ferme écrite |
| 14 | Date de sortie + statut | Oui si précommande | `confirmee` ou `estimee` ; sinon « non confirmée » | Annonce datée | Date inventée ; « livré le jour de la sortie » |
| 15 | Délai d'expédition | Oui | Réglage du thème (`DELAI_EXPEDITION` validé) ou métachamp | Registre légal | Délai non tenu par les SOP |
| 16 | Description | Oui | Structure du §4 | Faits sourcés | Termes du §5 |
| 17 | Titre SEO et méta-description | Oui | Modèles de `docs/06-contenu/SEO.md` §3 | Rédaction | Promesse de rareté, prix en dur dans la méta-description |
| 18 | Tags | Oui | `statut:*`, `ext:<slug>`, `nouveaute` (si achetable), `cadeau` (sélection) | Workflow | Tag libre qui crée une collection non prévue |

Ne figurent **jamais** dans Shopify (ni champ, ni métachamp, ni tag, ni note) : coût, prix d'achat, marge, contribution, nom de fournisseur, allocation chiffrée, stock amont, remise obtenue (SPEC §0.2 ; filtre de `publish.py`).

## 3. Statut affiché (snippets `site/shopify/snippets/`)

| Situation réelle | Statut | Libellé affiché | Détail affiché | Bouton |
|---|---|---|---|---|
| Stock vendable local > 0 | `stock_local` | **Stock local** | « Expédié depuis Genève sous {délai}. » | Ajouter au panier |
| Allocation ferme écrite, quota > 0 | `precommande` | **Précommande (allocation confirmée)** | « Sortie le … » / « Sortie estimée au … (peut changer) » / « Date de sortie non confirmée » + « expédition dès réception » | Précommander |
| Plus rien de vendable, alerte ouverte | `rupture` | **Rupture – alerte** | « Plus d'unité disponible. Demandez une alerte : nous vous écrivons dès le retour en stock local, sans date promise. » | Formulaire d'alerte |
| Plus rien, fin de série | `rupture` + `fin_de_serie` | **Rupture** | « Fin de série : pas de réassort prévu. » | Aucun |
| Stock seulement chez un tiers, non alloué | `rupture` | Rupture – alerte | (idem) | Formulaire d'alerte |

## 4. Structure de la description (agent 08)

```text
[1 phrase factuelle] {Format} de l'extension {Extension}, en français, neuf et scellé.
Contenu : {liste exacte de boutique.contenu_valide}.
Pour qui : {collection | jeu | cadeau — 1 phrase, sans superlatif}.
Bon à savoir : {1 à 3 puces utiles — ex. « les boosters sont ceux de l'extension {Extension} » ; « protège-cartes non inclus »}.
Guide : {lien vers le guide pertinent de docs/06-contenu/15_SUJETS.md, ex. « ETB ou display : lequel choisir ? »}.
Rappel : le contenu des boosters est aléatoire ; aucune carte précise ni rareté n'est garantie.
```

## 5. Formulations interdites et remplacements

| Interdit | Pourquoi | Écrire plutôt |
|---|---|---|
| « Dernières pièces », « bientôt épuisé », « plus que 2 en stock », minuteur | Fausse urgence (BP §8) ; quantité non affichée | « Stock local » ou « Rupture – alerte » |
| « Carte rare garantie », « hits garantis », « gros potentiel » | Contenu aléatoire (BP §7, CGV) | « Contenu des boosters aléatoire » |
| « Investissement », « prendra de la valeur », « idéal pour la revente » | Promesse de valeur financière (BP §7) | « Pour collectionner ou jouer » |
| « Officiel », « revendeur agréé », « partenaire » | Statut non obtenu (BP §8, `USAGE_MARQUES.md`) | « Produit authentique, neuf et scellé » ; « boutique indépendante » |
| « Disponible » pour un produit chez un tiers | Stock fournisseur ≠ stock boutique (BP §5) | « Rupture – alerte » |
| « Livré le jour de la sortie » | Non garanti (PRECOMMANDES) | « Expédié dès réception » |

## 6. Exemple rempli — **FICTIF** (aucune donnée réelle)

| Champ | Valeur (FICTIF) |
|---|---|
| Titre | Display 36 boosters — Extension Exemple — FR |
| Type de produit | Display |
| SKU | DSP-EXEMPLE-FR (FICTIF) |
| Code-barres | 2000000000015 — GTIN de **test** (plage `200`, SPEC §0.7) : **ne jamais publier** ; en production, GTIN réel lu sur l'emballage |
| `boutique.langue` | FR |
| `boutique.extension` | Extension Exemple (FICTIF) |
| `boutique.contenu_valide` | 36 boosters de l'extension Exemple (FICTIF — contenu réel à reprendre de la fiche technique confirmée) |
| Photos | 3 photos propres (face, dos, côté avec la mention de langue), session A06 |
| Prix | 209.90 CHF — exemple chiffré **fictif** du BP §4 (coût fictif de 140 CHF, plancher 208.79 arrondi), pas un prix réel |
| `boutique.quantite_max` | 2 (hypothèse ; valeur réelle = `LIMITE_PAR_CLIENT` validé) |
| `boutique.statut_stock` | stock_local |
| `boutique.date_sortie` / statut | 2026-07-17 / confirmee (FICTIF) |
| Description | « Display de l'extension Exemple, en français, neuf et scellé. Contenu : 36 boosters de l'extension Exemple. Pour qui : pour ouvrir beaucoup de boosters d'une même extension, seul ou à plusieurs. Bon à savoir : protège-cartes non inclus. Guide : ETB ou display, lequel choisir ? Rappel : le contenu des boosters est aléatoire ; aucune carte précise ni rareté n'est garantie. » |
| Titre SEO | Display 36 boosters Extension Exemple (FR) — expédié de Genève · Quai des Cartes |
| Méta-description | Display de l'extension Exemple en français, neuf et scellé, en stock local à Genève. Livraison en Suisse ; contenu exact et délai indiqués sur la fiche. |
| Tags | statut:stock-local, ext:extension-exemple, nouveaute |

## 7. Contrôle avant publication (agent 12 ; bloque si une case manque)

- [ ] Titre = format + extension exacte + langue ; type de produit et SKU conformes.
- [ ] GTIN réel valide (ou champ vide si aucun GTIN), jamais un GTIN de test.
- [ ] Contenu confirmé par écrit ; langue FR contrôlée à réception (stock local) ou sur la confirmation d'allocation (précommande).
- [ ] Photos propres ou autorisées (ligne du registre) ; aucune image générée.
- [ ] Prix = décision du moteur, horodatée, statut `OK` ou `REVIEW` validé ; pas de stop-loss produit actif sur la référence.
- [ ] Statut, date de sortie, délai et quantité maximale cohérents avec le §3.
- [ ] Description sans aucune formulation du §5 ; mention « contenu aléatoire » présente pour tout produit contenant des boosters.
- [ ] Aucune donnée interne dans la fiche, ses métachamps, ses tags ou ses notes.

## Validation humaine requise

- [ ] Valider la convention de SKU (§2, ligne 3) avant la création des 10 premières fiches (BL-094).
- [ ] Valider la structure de description et la liste des formulations interdites (§4, §5).
- [ ] Fixer `LIMITE_PAR_CLIENT` (registre légal) : la quantité maximale de l'exemple (2) est une hypothèse.
- [ ] Confirmer que les fiches sans GTIN réel peuvent être publiées avec un champ code-barres vide (sinon : brouillon).
