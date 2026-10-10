# Protocole de relevé concurrentiel

> But (BP §1) : « Comparer 10 à 15 références identiques chez 5 boutiques suisses : langue, extension, contenu, stock, prix total livré et délai. Conserver URL et date. »
> La grille correspondante est pré-remplie : `GRILLE_CONCURRENCE.csv` (15 références × 5 boutiques = 75 lignes, **aucun prix saisi**).
> Résultat attendu : une **référence marché** par produit (médiane du prix total livré), reportée dans `docs/02-sourcing/COMPARATEUR_OFFRES.xlsx` (colonne « prix marché observé ») et utilisée par la règle BP §5 (prix rentable > marché + 10 % ⇒ à revoir).
> Tâches : BL-020 (relevé), BL-021 (re-vérification des URL), BL-022 (médiane).

## 1. État au 4 octobre 2026 (build)

**Aucun prix n'a été relevé.** Depuis l'environnement de build, l'accès direct aux sites des boutiques a été refusé par le proxy de sortie (HTTP 403, écart EC-05). Les noms et URL ci-dessous proviennent de l'**index de recherche web** consulté le 4.10.2026 : les pages n'ont pas été ouvertes.

Des extraits de recherche affichaient des prix pour certains produits. Ils **ne sont pas repris** : un prix n'est admis dans la grille que s'il a été **lu sur la page produit**, avec la date et l'heure.

## 2. Boutiques retenues

| ID | Boutique | URL relevée (index) | Pourquoi | Indices FR (extraits indexés) | Statut de vérification |
|---|---|---|---|---|---|
| B1 | Swiss Pokéshop | https://swiss-pokeshop.ch/ | Spécialiste en ligne Pokémon, CHF, toute la Suisse | « versions française (FR) et anglaise (EN) », ETB, displays, coffrets, précommandes | Indexée le 4.10.2026, page non ouverte |
| B2 | TamoriCards | https://tamoricards.ch/ | Spécialiste en ligne : displays, ETB, boosters | Fiches produits suffixées « (FR) » ou « -fr », par ex. https://tamoricards.ch/products/asc-265-mega-momartik-ex-fr | Indexée le 4.10.2026, page non ouverte |
| B3 | Pika Store | https://pikastore.ch/ (collection : https://pikastore.ch/collections/pokemon) | Romandie (La Verrerie, FR), spécialiste | « cartes Pokémon en français » | Indexée le 4.10.2026, page non ouverte |
| B4 | JCC-Shop Unlimited | https://www.jcc-shop.ch/ (boutique : https://www.jcc-shop.ch/shop) | Romandie (Valais), spécialiste FR et JP | « cartes et articles Pokémon en français et japonais » | Indexée le 4.10.2026, page non ouverte |
| B5 | Galaxus | https://www.galaxus.ch/fr | Généraliste national : sert de point de prix grand public | Fiche ETB FR indexée : https://www.galaxus.ch/fr/s5/product/pokemon-jcc-ecarlate-et-violet-coffret-dresseur-delite-ev65-francais-boite-elite-top-trainer-cartes--43289812 | Indexée le 4.10.2026, page non ouverte |

**Remplaçants** (à utiliser si une boutique ne propose pas au moins 8 des 15 références en FR) :

| ID | Boutique | URL relevée (index) | Remarque |
|---|---|---|---|
| R1 | Poke Swiss | https://poke-swiss.ch/ | Boutique physique à Genève (concurrent local direct) ; vérifier la vente en ligne |
| R2 | The Mana Shop | https://themanashop.ch/fr/205-pokemon | Rayon Pokémon |
| R3 | King Jouet Suisse | https://www.king-jouet.ch/ | Chaîne de jouets, 17 magasins en Suisse selon l'index ; point de prix grand public |

Sources de la sélection (index de recherche, 4.10.2026) : guide « Où acheter des cartes Pokémon en Suisse » https://swiss-pokeshop.ch/blogs/news/ou-acheter-cartes-pokemon-suisse-2026 (publié par un concurrent : à lire avec recul) ; résultats de recherche « boutique en ligne suisse cartes Pokémon français ».

## 3. Références à relever

Mêmes identifiants que l'assortiment (`ASSORTIMENT_PILOTE.md`) et le panier fournisseur (`docs/02-sourcing/PANIER_PILOTE.csv`).

**Règle : chacune des 12 références STOCK du panier pilote est dans la grille** (contrôlé par `docs/02-sourcing/outils/test_couverture_marche.py`). Les 3 places restantes vont à des références sans budget utiles à la décision ; les références ALERTE de priorité C (REF-03, REF-05, REF-10) et le tripack Règne Delta (REF-15) n'y sont plus. Une référence hors de la grille n'est **jamais** une alternative d'achat à une référence STOCK : REF-05 (collection classeur) n'est plus une alternative à REF-04 (le même test refuse toute « alternative » déclarée sans relevé).

| ref_id | Désignation attendue | Pourquoi dans la grille |
|---|---|---|
| REF-01, REF-02, REF-04 | Extension spéciale 30ᵉ Anniversaire : ETB, bundle, coffret Nymphali-ex **ou** Amphinobi-ex (selon offre, même prix exigé) | STOCK : produits du moment (septembre-octobre 2026), formats cadeaux |
| REF-06 à REF-08 | Méga-Évolution – Nuit Noire (juillet 2026) : display, ETB, tripack | STOCK : extension récente, normalement disponible |
| REF-09, REF-19 | Méga-Évolution – Chaos Ascendant (mai 2026) : display ; tripack **ou** bundle (selon offre) | STOCK : extension plus ancienne, mesure de la disponibilité |
| REF-11, REF-20 | Équilibre Parfait : ETB ; coffret ou collection Équilibre Parfait **ou** Héros Transcendants (selon offre) | STOCK : respect du plafond de 25 % par extension (écart EC-14) |
| REF-16, REF-17 | Accessoires : protège-cartes (paquet), classeur 9 cases | STOCK : 300 CHF du budget, prix très comparés par les clients |
| REF-12 | Héros Transcendants : ETB | ALERTE : point de prix de l'extension de REF-20 |
| REF-13, REF-14 | Méga-Évolution – Règne Delta (sortie 6.11.2026) : display, ETB | COND. : mesure des prix de **précommande** chez les concurrents ; nous n'en ferons pas sans allocation ferme |

**Références « selon offre » (REF-04, REF-19, REF-20)** : tant que l'offre fournisseur ne fixe pas la variante, relever toutes les variantes candidates nommées (coffrets 30ᵉ Anniversaire Nymphali-ex et Amphinobi-ex ; tripack et bundle Chaos Ascendant ; coffrets Équilibre Parfait et Héros Transcendants) : la moins chère au prix total livré dans la ligne, les autres en commentaire avec leur URL. Dès que la variante est fixée, **re-relever cette variante avant l'achat**.

**Accessoires (REF-16, REF-17)** : pas d'extension ; « FR » désigne l'emballage ou la notice en français s'il existe et ne rend pas la ligne non comparable. Comparable = même marque, même modèle, même quantité par paquet que l'offre fournisseur retenue.

**Aucun achat sans relevé** : une référence STOCK n'est achetée que si sa référence marché existe (au moins 3 lignes comparables de moins de 7 jours, §5) ; sinon, seulement avec la validation explicite de la propriétaire (critère 3 de `ASSORTIMENT_PILOTE.md` §4).

## 4. Procédure de relevé (par ligne de la grille)

1. **Ouvrir la page produit** dans un navigateur normal. Ne pas créer de compte, ne pas passer commande, ne pas contourner de CAPTCHA ni de contrôle d'accès (SPEC §0.9). Pas de robot d'extraction automatique sans accord écrit du site.
2. **Identité** : noter la langue affichée (`langue_constatee`) et le contenu (`contenu_constate`). La ligne est `comparable = oui` seulement si format, extension, langue **FR** et contenu sont identiques à la désignation attendue. Si un EAN est affiché, le noter en commentaire.
3. **Stock** : `stock_affiche` ∈ {`en stock`, `rupture`, `précommande`, `non référencé`, `inconnu`}. Recopier la date de disponibilité annoncée en commentaire.
4. **Prix** : `prix_produit_chf` = prix TTC affiché pour 1 unité, sans code promo personnel. Si une promotion publique est affichée, saisir le prix promo et noter « promo jusqu'au … ».
5. **Livraison** : mettre 1 unité au panier **sans valider la commande** et lire les frais pour une adresse à Genève (1201). À défaut, relever la page « Livraison ». Renseigner `frais_livraison_chf`, `seuil_port_gratuit_chf`, et `frais_paiement_chf` (surcoût éventuel d'un moyen de paiement).
6. **Prix total livré** : `prix_total_livre_chf` = prix produit + frais de livraison (0 si le produit seul dépasse le seuil de port gratuit) + frais de paiement. À 2 décimales.
7. **Délai** : `delai_annonce_jours` = délai d'expédition + livraison annoncé, en jours ouvrés (borne haute s'il s'agit d'une fourchette).
8. **Traçabilité** : `date_releve` (AAAA-MM-JJ), `heure_releve` (HH:MM), `source_lecture = page lue`, `releveur` (agent ou initiales), `capture_fichier` = `CONC_{boutique_id}_{ref_id}_{AAAAMMJJ}.png`, à archiver dans le dossier de captures du projet (hors repo public si nécessaire).
9. **Marketplace** (Galaxus) : renseigner `vendu_par` (Galaxus ou nom du vendeur tiers). Un vendeur tiers non suisse rend la ligne non comparable.
10. Une ligne jamais trouvée reste `stock_affiche = non référencé`, `source_lecture = page lue`, prix vides.

**Durée estimée :** 3 à 4 min par ligne, soit ≈ 4 à 5 h pour 75 lignes. Faisable par un agent disposant d'un accès web, sinon par la propriétaire.

## 5. Calcul de la référence marché (BL-022)

Pour chaque `ref_id` :

| Étape | Règle |
|---|---|
| Échantillon | Lignes `comparable = oui` et `stock_affiche = en stock`. Si moins de 3 lignes, ajouter les lignes `précommande`, signalées. |
| Référence marché | **Médiane** du `prix_total_livre_chf` de l'échantillon. |
| Dispersion | Minimum, maximum, nombre de lignes. Si l'écart max/min dépasse 40 %, le signaler (prix anormal ou contenu différent probable). |
| Validité | 7 jours. Au-delà, re-relever les références du panier pilote (chaque lundi après l'ouverture). |
| Usage | Reporter la médiane dans le comparateur (colonne V « prix marché observé TTC »). Le moteur compare le prix plancher à la médiane × 1,10 (BP §5). |

> Notre prix public n'inclut pas forcément les frais de livraison. La comparaison se fait sur le **prix total livré** d'une commande d'une unité, notre propre tarif de livraison compris, pour rester à égalité.

> Les prix d'étiquette relevés **en magasin physique** (`RELEVES_MAGASIN.csv`) n'entrent jamais dans cette médiane : pas de port, pas d'URL. Ils servent de plafond de crédibilité et au calcul du prix d'achat maximal (`RELEVES_MAGASIN.md`).

## 6. Synthèse à produire (une page)

| Indicateur | Valeur |
|---|---|
| Lignes relevées / comparables | … / … |
| Références avec ≥ 3 offres en stock | … / 15 (dont … / 12 références STOCK) |
| Écart médian entre boutiques spécialisées et généraliste | … % |
| Seuils de port gratuit observés | … à … CHF |
| Délais annoncés | … à … jours |
| Précommandes Règne Delta observées | Oui / non, chez … |
| Constats utiles au positionnement (confiance, sélection, service) | 3 puces |

## Validation humaine requise

- [ ] Accepter la sélection B1 à B5 (ou en remplacer une par R1 à R3, par exemple Poke Swiss pour suivre le concurrent genevois).
- [ ] Désigner qui fait le relevé si aucun agent n'a d'accès web ouvert (≈ 4 à 5 h) ; sinon l'agent 02 le fait (BL-020).
- [ ] Valider la règle de la référence marché (médiane du prix total livré, validité 7 jours).
