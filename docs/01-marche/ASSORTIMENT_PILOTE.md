# Assortiment pilote — structure et règles

> BP §1 : « Prévoir 15 à 25 références, dont 8 à 12 réellement en stock. Répartition indicative du budget stock : displays 25 %, ETB 25 %, bundles et tripacks 20 %, coffrets 20 %, accessoires 10 %. Cette répartition doit suivre les marges et les allocations disponibles. » « Pas plus de 25 % du budget stock dans une extension au lancement ; documenter les exceptions. Les allocations rares ne sont pas un motif suffisant pour acheter un produit à faible marge. »
> Budget stock pilote : **3 000 CHF rendu Suisse** (BP §3, hypothèse de coût cash). Plafond par extension : **750 CHF** (25 % de 3 000 ; base à confirmer, écart EC-14).
> **Aucun prix ni coût n'est connu à ce jour.** Les montants ci-dessous sont des **enveloppes budgétaires**, pas des prix. Les quantités se calculent avec les devis (`docs/02-sourcing/COMPARATEUR_OFFRES.xlsx`).

## 1. Calendrier des sorties JCC Pokémon en français (contexte octobre 2026)

Consulté le 4.10.2026 via index de recherche web (accès direct bloqué depuis l'environnement de build, écart EC-05). À reconfirmer sur pokemon.com/fr et auprès des fournisseurs (date, contenu, conditionnement).

| Extension (FR) | Sortie FR | Produits relevés dans les sources | Source(s) indexée(s) |
|---|---|---|---|
| Méga-Évolution – Héros Transcendants | Fin janvier 2026 (ETB annoncé le 20.2.2026 selon une source secondaire) | ETB, boosters | https://leblogdewilly.fr/calendrier-sorties-jcc-pokemon-2026-30-ans-mega-evolutions/ ; https://www.pokemon.com/us/pokemon-news/get-the-new-pokemon-tcg-expansion-mega-evolution-ascended-heroes-on-january-30-2026 |
| Méga-Évolution – Équilibre Parfait | 27.3.2026 | ETB, display, coffrets premium | https://lecoindesbarons.com/calendrier-des-sorties-de-cartes-jcc-pokemon-2026-2027/ ; https://icv2.com/articles/news/view/61079/pokemon-tcg-2026-product-calendar |
| Méga-Évolution – Chaos Ascendant | 22.5.2026 | Display, ETB, boosters | https://www.pokebip.com/news/7257/jcc-pokemon-nouvelle-extension-mega-evolution-chaos-ascendant ; https://tcg.pokemon.com/fr-fr/galleries/chaos-rising/ |
| Méga-Évolution – Nuit Noire (ME05) | 17.7.2026 | Display, ETB, autres produits | https://www.pokemon.com/fr/actualites/produits-mega-evolution-nuit-noire-du-jcc-pokemon ; https://www.pokekalos.fr/news/actualites-nouvelle-extension-du-jcc-annoncee-me05-nuit-noire-2727.html |
| 30ᵉ Anniversaire (extension spéciale) | 16.9.2026 (sortie mondiale simultanée) | Coffrets Nymphali-ex et Amphinobi-ex, ETB (septembre) ; bundle 6 boosters et mini-tins (2.10) ; collection classeur 5 boosters (23.10) ; autres collections au 4ᵉ trimestre | https://www.pokemon.com/fr/actualites/decouvrez-tous-les-produits-du-jcc-pokemon-qui-sortiront-en-septembre-2026 ; https://www.pokemon.com/fr/actualites/jcc-pokemon-produits-30-anniversaire ; https://www.pokekalos.fr/news/actualites-jcc-pokemon-30e-anniversaire-le-plein-d-infos-2742.html |
| Méga-Évolution – Règne Delta (ME06) | **6.11.2026** (avant-premières dès le 24.10) | Display 36 boosters, demi-display 18, ETB, tripack, boosters | https://www.pokebip.com/news/7489/jcc-pokemon-nouvelle-extension-mega-evolution-regne-delta ; https://www.pokemon.com/fr/actualites/participez-a-un-evenement-davant-premiere-pour-lextension-mega-evolution-regne-delta-du-jcc-pokemon |
| Extension suivante | Rien d'annoncé au 4.10.2026 ; fenêtre habituelle fin janvier ou début février 2027 | — | https://jollycards.fr/pages/calendrier-des-sorties-pokemon |

**Placeholders à confirmer :** le contenu exact de chaque produit (nombre de boosters, promos), l'existence d'un tripack FR pour Nuit Noire et Chaos Ascendant, et les codes d'extension autres que ME05 et ME06. Les fiches restent en brouillon tant que le fournisseur n'a pas confirmé (SPEC §0.5).

## 2. Répartition du budget : enveloppes par catégorie × extension

Les colonnes respectent le plafond de 750 CHF par extension ; les lignes respectent la répartition du BP. Il faut **au moins 4 extensions** pour placer 2 700 CHF de scellé sous ce plafond (écart EC-14).

| Catégorie (part BP) | E1 30ᵉ Anniversaire | E2 Nuit Noire | E3 Chaos Ascendant | E4 Équilibre Parfait ou Héros Transcendants | Hors extension | **Total ligne** |
|---|---:|---:|---:|---:|---:|---:|
| Displays (25 %) | — | 375 | 375 | — | — | **750** |
| ETB (25 %) | 250 | 250 | — | 250 | — | **750** |
| Bundles et tripacks (20 %) | 250 | 100 | 250 | — | — | **600** |
| Coffrets (20 %) | 250 | — | — | 350 | — | **600** |
| Accessoires (10 %) | — | — | — | — | 300 | **300** |
| **Total colonne** | **750** | **725** | **625** | **600** | **300** | **3 000** |
| Plafond 25 % | 750 ✓ | 750 ✓ | 750 ✓ | 750 ✓ | n/a | |

Règles d'usage :

- Ce sont des **plafonds de dépense** par case, pas des objectifs. Une case peut rester vide si les marges ou les allocations ne suivent pas (BP §1). Le reliquat retourne en trésorerie ; il n'est pas reporté automatiquement sur une autre extension.
- **Règne Delta (E5) = 0 CHF par défaut.** Une allocation ferme et rentable peut prendre jusqu'à 750 CHF, **à budget total constant** : on réduit d'abord E4, puis E3. Cette exception est décidée par la propriétaire (C18).
- Une extension qui dépasserait 750 CHF déclenche le **stop-loss extension** (plus de réassort, proposition de démarque).

## 3. Structure proposée : 20 références, dont 12 au maximum en stock

**Statuts** (écart EC-16) :

- **STOCK** : acheté au pilote, vendable localement.
- **ALERTE** : fiche visible « indisponible, être alerté du réassort », prix calculé possible, jamais de stock fournisseur affiché comme expédiable.
- **COND.** : précommande ou stock **uniquement** si allocation ferme écrite et marge conforme ; sinon ALERTE.

| ref_id | Désignation (format + extension + langue) | Catégorie | Ext. | Statut visé | Enveloppe (CHF) | Priorité |
|---|---|---|---|---|---:|---|
| REF-06 | Display 36 boosters Méga-Évolution – Nuit Noire – FR | Displays | E2 | STOCK | 375 | A |
| REF-09 | Display 36 boosters Méga-Évolution – Chaos Ascendant – FR | Displays | E3 | STOCK | 375 | A |
| REF-01 | ETB 30ᵉ Anniversaire – FR | ETB | E1 | STOCK | 250 | A |
| REF-07 | ETB Méga-Évolution – Nuit Noire – FR | ETB | E2 | STOCK | 250 | A |
| REF-11 | ETB Méga-Évolution – Équilibre Parfait – FR | ETB | E4 | STOCK | 250 | B |
| REF-02 | Bundle 30ᵉ Anniversaire (6 boosters) – FR | Bundles/tripacks | E1 | STOCK | 250 | A |
| REF-08 | Tripack Méga-Évolution – Nuit Noire – FR (existence à confirmer) | Bundles/tripacks | E2 | STOCK | 100 | B |
| REF-19 | Tripack ou bundle Méga-Évolution – Chaos Ascendant – FR (selon offres) | Bundles/tripacks | E3 | STOCK | 250 | B |
| REF-04 | Coffret 30ᵉ Anniversaire Nymphali-ex – FR (ou REF-05 selon la marge) | Coffrets | E1 | STOCK | 250 | A |
| REF-20 | Coffret ou collection – Équilibre Parfait ou Héros Transcendants – FR (selon offres) | Coffrets | E4 | STOCK | 350 | B |
| REF-16 | Protège-cartes format standard (marque proposée par le fournisseur) | Accessoires | — | STOCK | 150 | A |
| REF-17 | Classeur 9 cases (marque proposée par le fournisseur) | Accessoires | — | STOCK | 150 | B |
| REF-03 | Mini-Tin 30ᵉ Anniversaire – FR | Coffrets | E1 | ALERTE | 0 | C |
| REF-05 | Collection Classeur 30ᵉ Anniversaire – FR | Coffrets | E1 | ALERTE (alternative à REF-04) | 0 | C |
| REF-10 | ETB Méga-Évolution – Chaos Ascendant – FR | ETB | E3 | ALERTE | 0 | C |
| REF-12 | ETB Méga-Évolution – Héros Transcendants – FR | ETB | E4 | ALERTE | 0 | C |
| REF-13 | Display 36 boosters Méga-Évolution – Règne Delta – FR | Displays | E5 | COND. | 0 (≤ 750 si exception) | B |
| REF-14 | ETB Méga-Évolution – Règne Delta – FR | ETB | E5 | COND. | 0 | B |
| REF-15 | Tripack Méga-Évolution – Règne Delta – FR | Bundles/tripacks | E5 | COND. | 0 | C |
| REF-18 | Boîte de rangement de deck (deck box) | Accessoires | — | ALERTE | 0 | C |

Contrôle : 20 références (fourchette BP : 15 à 25) ; **12 en STOCK** (fourchette : 8 à 12) ; somme des enveloppes STOCK = 3 000 CHF. Si les quantités minimales des devis l'imposent, ramener le STOCK à 10 références en supprimant d'abord les priorités B.

Les retours d'entretiens (BL-027) et de la landing (préférences de formats) peuvent faire **permuter** des références de priorité B et C, sans changer les enveloppes.

## 4. Critères d'éligibilité d'une référence en STOCK

Une référence n'est achetée que si **tous** les critères sont remplis. Sinon, elle passe en ALERTE ou en brouillon.

| # | Critère | Source de la règle |
|---|---|---|
| 1 | Langue FR, extension, format et contenu confirmés **par écrit** par le fournisseur ; EAN connu | BP §6, §7 ; SPEC §2.4 |
| 2 | Coût rendu calculé sans champ inconnu (frais, taxes, conditionnement) | BP §5 ; SPEC §0.5 |
| 3 | Prix plancher (m = 20 %) ≤ référence marché × 1,10, **ou** validation explicite de la propriétaire (statut « À REVOIR ») | BP §1, §5 |
| 4 | Au prix public prévu : contribution ≥ 12 % du CA net **et** ≥ 8 CHF par commande | BP §5 (plancher dur = stop-loss produit) |
| 5 | Disponibilité ou allocation confirmée par écrit, avec délai | BP §5 |
| 6 | Enveloppe de la case et plafond de l'extension respectés | BP §1 |
| 7 | Droits d'image obtenus, ou photos propres prévues | BP §7 |
| 8 | Fournisseur dans la liste autorisée du mandat (due diligence faite) | Modèle d'opération |

## 5. Calcul des quantités (à faire avec les devis)

```
quantité_max = arrondi_inférieur( enveloppe_case_CHF / coût_rendu_unitaire_C )
quantité     = max(MOQ, multiple du carton) si ≤ quantité_max, sinon référence non achetée (ou exception C18)
```

Exemple **FICTIF** (aucun coût réel) : enveloppe de 375 CHF, C FICTIF de 150,00 CHF ⇒ quantité max = 2. Si le MOQ fournisseur est de 3, la référence n'est pas achetée sans exception.

Contrôles automatiques du moteur (`engine/pokeshop/stock.py`, `propose_reorder`) : MOQ, cartons, budget disponible, plafond de 25 % par extension. La sortie est toujours une **proposition à valider**, jamais une commande.

## 6. Après l'ouverture

| Signal | Règle | Source |
|---|---|---|
| Stock local sous le point de commande (ventes journalières moyennes × délai de réapprovisionnement + sécurité) | Proposition de réassort (validation C17 jusqu'au niveau 4) | BP §5 Réassort |
| 45 jours sans vente dans une extension | Stop-loss extension : plus de réassort + proposition de démarque | Mandat |
| Contribution réelle (facture) sous le plancher | Stop-loss produit : vente et promotion bloquées | BP §5, §12 |
| Nouvelle extension annoncée | Placée en ALERTE ; précommande seulement sur allocation ferme | BP §3, §5 |

## Validation humaine requise

- [ ] Valider la grille d'enveloppes du §2 (ou la modifier en respectant les 5 parts du BP et le plafond de 750 CHF par extension).
- [ ] Confirmer la base du plafond (3 000 CHF) et le traitement de l'extension 30ᵉ Anniversaire comme une seule extension (EC-14, EC-15).
- [ ] Décider la position face à Règne Delta : COND. par défaut, exception possible jusqu'à 750 CHF à budget constant.
- [ ] Valider la liste des 12 références en STOCK au gate G3, une fois les devis reçus.
