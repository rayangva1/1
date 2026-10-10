# Relevés en magasin physique : un signal, pas une référence marché

> Fichier de données : `RELEVES_MAGASIN.csv`. Premier relevé le 10.10.2026, à partir de 5 photos de rayon transmises par la propriétaire. Le magasin et la date de prise de vue sont à préciser.

## Règle d'usage

| Question | Réponse |
|---|---|
| Ces prix entrent-ils dans la médiane de `GRILLE_CONCURRENCE.csv` ? | **Non.** La référence marché reste la médiane du **prix total livré en ligne** (`PROTOCOLE_CONCURRENCE.md` §5). Un prix d'étiquette n'a ni port, ni URL, ni page datée. La colonne `utilisable_reference_marche` vaut toujours `non`. |
| Débloquent-ils un achat (« aucun achat sans relevé ») ? | **Non.** Il faut toujours au moins 3 lignes comparables en ligne de moins de 7 jours, ou la validation explicite de la propriétaire. |
| À quoi servent-ils alors ? | (1) **Plafond de crédibilité** : le client romand peut acheter le même produit en rayon et repartir avec. (2) **Prix d'achat maximal** à négocier avec les fournisseurs (tableau ci-dessous). (3) Un repère pour les formats hors grille. |
| Comment ajouter une ligne ? | Une ligne par produit et par magasin, avec la date de prise de vue, le nom du magasin, le prix exact de l'étiquette, la langue et le contenu lus sur la boîte. Archiver la photo hors du repo public (`photo_fichier`). Une étiquette illisible garde un prix vide. |

## Lecture du relevé du 10.10.2026

| Constat | Conséquence |
|---|---|
| ETB FR *Équilibre Parfait* (REF-11) à **69.95** en rayon. | En ligne, notre prix **plus le port** sera comparé à 69.95, payé sur place et emporté tout de suite. Les prix de démonstration des maquettes (69.90 en pré-drop, 64.90 au drop, tous deux fictifs) ne laissent presque aucune marge pour facturer le port. |
| ETB EN *Chaos Rising* à **79.95**, soit 10 CHF de plus que l'ETB FR. | Hors périmètre (FR uniquement). Cela confirme seulement que la version anglaise se vend plus cher en magasin. |
| *Collection Premium Méga-Amphinobi-ex* FR à **69.95**. | Ce n'est **pas** REF-04 (coffret 30ᵉ Anniversaire Amphinobi-ex, 4 boosters + promo). Ne pas substituer sans relever le contenu exact. |
| Deck des Championnats du Monde 2025 FR à **29.95**. | Format absent du pilote. C'est un produit d'appel possible, mais à ce prix la marge cible exige un coût rendu ≤ 9.65 CHF (tableau). |
| Classeurs, Boîte Poké Ball : prix illisibles. | Reprendre une photo des étiquettes. |

## Prix d'achat maximal (coût rendu C) pour vendre au prix d'étiquette

Calcul fait avec le moteur (`config/pricing_rules.v1.yaml`, `rules_version` v1-2026-10-04, hypothèses BP §4-5 à confirmer par devis). Il s'agit de la commande d'une seule unité, frais par commande b + L + R + A = 9.30 CHF compris. C'est la plus grande valeur de C, au centime, pour laquelle `pricing._meets_target` (contribution ≥ 20 % **et** ≥ 8 CHF) puis `pricing.price_floor_violations` (planchers durs 12 % / 8 CHF) sont respectés.

| Prix de vente TTC | C max à la cible 20 % — assujetti (TVA 8,1 %) | C max à la cible 20 % — non assujetti | C max au plancher dur — assujetti | C max au plancher dur — non assujetti |
|---|---|---|---|---|
| 29.95 | 9.65 | 11.90 | 9.66 | 11.90 |
| 59.90 | 33.53 | 37.12 | 36.61 | 41.10 |
| 64.90 | 37.10 | 40.99 | 41.12 | 45.98 |
| 69.95 | 40.71 | 44.91 | 45.66 | 50.50 |
| 79.95 | 47.86 | 52.66 | 53.78 | 59.05 |

Lecture : pour vendre l'ETB FR au même prix que le magasin (69.95) avec la marge cible, l'ETB doit arriver chez nous à **40.71 CHF au plus** (assujetti), port fournisseur, douane et TVA non récupérable compris. Sous le plancher dur, aucune promotion n'est possible.

## Validation humaine requise

- [ ] Nommer le magasin et la date de prise de vue des photos (traçabilité).
- [ ] Archiver les 5 photos hors du repo public et renseigner `photo_fichier`.
- [ ] Décider si un prix affiché **au-dessus** du prix d'étiquette d'un magasin romand, pour un produit identique, exige la validation de la propriétaire (proposition : oui, en plus de la règle « marché + 10 % » du moteur).
