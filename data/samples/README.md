# Jeux d'essai FICTIFS — imports fournisseurs

> **Tout est FICTIF.** Fournisseurs `fictif_grossiste_*`, SKU `FICTIF-…`, extensions « Extension Fictive … »
> (table `FICTIF_extensions_aliases.yaml`), GTIN de test `200…` au checksum valide (plage GS1 « restricted
> circulation », SPEC §0.7), prix inventés. Aucun tarif, EAN ou fournisseur réel. Référence : 4 octobre 2026.

Fichiers générés par `python data/samples/generate_samples.py` (déterministe ; `tests/test_importers.py` vérifie
que les fichiers versionnés correspondent au générateur). Résultats attendus : `FICTIF_attendus.yaml`.

| Fichier | Dictionnaire | Format | Rôle |
|---|---|---|---|
| `FICTIF_offres_grossiste_a_J-1.csv` | `fictif_grossiste_a` | CSV `;`, virgule décimale, EUR HT | Import de la veille (référence ×10, devise, HT/TTC, lignes) |
| `FICTIF_offres_grossiste_a.csv` | `fictif_grossiste_a` | idem | Import du jour : une anomalie volontaire par ligne |
| `FICTIF_offres_grossiste_a_incomplet.csv` | `fictif_grossiste_a` | idem | Import tronqué (5 lignes au lieu de 22) |
| `FICTIF_tarif_grossiste_b.xlsx` | `fictif_grossiste_b` | Excel, feuille « Tarif », en-tête ligne 4, export en B2, CHF TTC | Tarif type distributeur suisse |
| `FICTIF_flux_grossiste_c.xml` | `fictif_grossiste_c` | XML, attributs, paliers répétés | Flux type API |
| `FICTIF_flux_grossiste_c_perime.xml` | `fictif_grossiste_c` | idem, exporté le 1.10.2026 | Capture > 24 h |
| `FICTIF_tarif_email_assiste.yaml` | — (import assisté) | fiche YAML d'un tarif email | Contrôle unités et totaux |
| `FICTIF_extensions_aliases.yaml` | — | YAML | Extensions fictives (jamais en production) |

Couverture des règles de quarantaine (SPEC §2.5, BP §13) : devise inconnue, HT/TTC inconnu, prix 0 ou négatif,
prix ×10 ou ÷10 vs dernier import, doublons, import incomplet, GTIN invalide, langue inconnue, capture > 24 h,
unité vs carton, paliers incohérents, devise ou base HT/TTC changées, ligne fictive dans un flux réel.

## `FICTIF_offres_grossiste_a.csv` — statut attendu PARTIAL (45 lignes lues)

| Ligne | SKU | Anomalie volontaire | Quarantaine attendue | Signal attendu |
|---|---|---|---|---|
| 2 | FICTIF-A-001 | Ligne propre, deux paliers (prix et %) | — (offre valide) | — |
| 3 | FICTIF-A-002 | Ligne propre | — (offre valide) | — |
| 4 | FICTIF-A-003 | Ligne propre | — (offre valide) | — |
| 5 | FICTIF-A-004 | Hausse ×1,56 vs veille (signalée, pas bloquante) | — (offre valide) | PRICE_CHANGE_LARGE |
| 6 | FICTIF-A-005 | Ligne propre | — (offre valide) | — |
| 7 | FICTIF-A-006 | Prix ×10 vs veille (98,00) | PRICE_ANOMALY | — |
| 8 | FICTIF-A-007 | Prix ÷10 vs veille (39,00) | PRICE_ANOMALY | — |
| 9 | FICTIF-A-008 | Accessoire, langue « n/a » acceptée (langue NA) | — (offre valide) | — |
| 10 | FICTIF-A-009 | Accessoire sans extension (SANS_EXTENSION) | — (offre valide) | — |
| 11 | FICTIF-A-010 | Devise inconnue XYZ | UNKNOWN_CURRENCY | — |
| 12 | FICTIF-A-011 | Devise absente | UNKNOWN_CURRENCY | — |
| 13 | FICTIF-A-012 | HT/TTC absent | UNKNOWN_VAT_BASIS | — |
| 14 | FICTIF-A-013 | « net » ≠ HT : base inconnue | UNKNOWN_VAT_BASIS | — |
| 15 | FICTIF-A-014 | Prix zéro | NON_POSITIVE_PRICE | — |
| 16 | FICTIF-A-015 | Prix négatif | NON_POSITIVE_PRICE | — |
| 17 | FICTIF-A-016 | Doublon de SKU (valeurs différentes, 1/2) | DUPLICATE_SKU | — |
| 18 | FICTIF-A-016 | Doublon de SKU (valeurs différentes, 2/2) | DUPLICATE_SKU | — |
| 19 | FICTIF-A-017 | GTIN au checksum faux | INVALID_GTIN | — |
| 20 | FICTIF-A-018 | Langue « VO » : inconnue | UNKNOWN_LANGUAGE | — |
| 21 | FICTIF-A-019 | Langues multiples | UNKNOWN_LANGUAGE | — |
| 22 | FICTIF-A-020 | Unité « palette » : unité/carton inconnue | UNKNOWN_UNIT_BASIS | — |
| 23 | FICTIF-A-021 | Prix au carton sans nombre d'unités ni colisage | UNKNOWN_UNIT_BASIS | — |
| 24 | FICTIF-A-022 | Palier plus cher que le prix de base | INVALID_TIER | — |
| 25 | FICTIF-A-023 | Point décimal dans un fichier à virgule (ambigu) | UNPARSEABLE_PRICE | — |
| 26 | FICTIF-A-024 | Ligne datée de J-2 (> 24 h) | STALE_SOURCE | — |
| 27 | FICTIF-A-025 | GTIN absent : offre acceptée, fiche en brouillon | — (offre valide) | MISSING_GTIN |
| 28 | FICTIF-A-026 | Devise EUR -> CHF depuis la veille | CURRENCY_CHANGED | — |
| 29 | FICTIF-A-027 | Prix au carton de 6 (570,00 = 6 × 95,00) | — (offre valide) | — |
| 30 | FICTIF-A-028 | Allocation annoncée sans accord écrit : ignorée | — (offre valide) | ALLOCATION_NOT_FIRM |
| 31 | (vide) | SKU vide | MISSING_SKU | — |
| 32 | FICTIF-A-004 | Copie identique de la ligne FICTIF-A-004 : ignorée | — (offre valide) | DUPLICATE_IDENTICAL_ROW |
| 33 | FICTIF-A-030 | Format « Blister » ambigu : offre en brouillon | — (offre valide) | UNKNOWN_FORMAT |
| 34 | FICTIF-A-031 | Extension absente de la table d'alias | — (offre valide) | UNKNOWN_EXTENSION |
| 35 | FICTIF-A-032 | Ligne « non fictive » dans un jeu FICTIF | FICTIF_FLAG_MISMATCH | — |
| 36 | FICTIF-A-033 | Même nom que FICTIF-A-002 mais 11 boosters (catalogue : AMBIGUOUS) | — (offre valide) | — |
| 37 | FICTIF-A-034 | HT -> TTC depuis la veille | VAT_BASIS_CHANGED | — |
| 38 | FICTIF-A-035 | Prix « unité » mais 6 unités par colis | UNIT_CONFLICT | — |
| 39 | FICTIF-A-036 | MOQ nul | INVALID_QUANTITY | — |
| 40 | FICTIF-A-037 | MOQ illisible | UNPARSEABLE_VALUE | — |
| 41 | FICTIF-A-038 | Langue JP : offre valide, bloquée ensuite par le pricing (FR attendu) | — (offre valide) | — |
| 42 | FICTIF-A-039 | Produit non scellé : hors périmètre | — (offre valide) | NOT_SEALED |
| 43 | FICTIF-A-040 | Ligne propre | — (offre valide) | — |
| 44 | FICTIF-A-041 | Ligne propre | — (offre valide) | — |
| 45 | FICTIF-A-042 | Ligne propre | — (offre valide) | — |
| 46 | FICTIF-A-043 | Ligne propre | — (offre valide) | — |

Signaux de niveau import : MISSING_SINCE_PREVIOUS, NEW_SINCE_PREVIOUS, QUARANTINE_RATIO_EXCEEDED.

## `FICTIF_tarif_grossiste_b.xlsx` — statut attendu PARTIAL (23 lignes lues)

| Ligne | SKU | Anomalie volontaire | Quarantaine attendue | Signal attendu |
|---|---|---|---|---|
| 5 | FICTIF-B-001 | Ligne propre (nombres Excel, date Excel) | — (offre valide) | — |
| 6 | FICTIF-B-002 | EAN numérique ; stock « 10+ » | — (offre valide) | APPROXIMATE_STOCK |
| 7 | FICTIF-B-003 | Ligne propre | — (offre valide) | — |
| 8 | FICTIF-B-004 | Rupture déclarée (stock 0) | — (offre valide) | — |
| 9 | FICTIF-B-005 | Précommande, date texte | — (offre valide) | — |
| 10 | FICTIF-B-006 | Ligne propre | — (offre valide) | — |
| 11 | FICTIF-B-007 | Accessoire sans langue ni série | — (offre valide) | — |
| 12 | FICTIF-B-008 | Langue JP : valide ici, bloquée par le pricing FR | — (offre valide) | — |
| 13 | FICTIF-B-009 | Carton : GTIN-14 de colis, prix « 1'299.00 » | — (offre valide) | CASE_LEVEL_GTIN |
| 14 | FICTIF-B-010 | Prix zéro | NON_POSITIVE_PRICE | — |
| 15 | FICTIF-B-011 | Symbole € dans un tarif CHF | CURRENCY_CONFLICT | — |
| 16 | FICTIF-B-012 | Symbole $ ambigu | UNKNOWN_CURRENCY | — |
| 17 | FICTIF-B-013 | GTIN-8 au checksum faux | INVALID_GTIN | — |
| 18 | FICTIF-B-014 | Langue vide pour un produit de cartes | UNKNOWN_LANGUAGE | — |
| 19 | FICTIF-B-015 | Stock négatif : ignoré (pas de stock inventé) | — (offre valide) | UNPARSEABLE_OPTIONAL |
| 20 | FICTIF-B-016 | Unité « display » pour un booster : ambiguë | UNKNOWN_UNIT_BASIS | — |
| 21 | FICTIF-B-017 | TVA illisible | UNPARSEABLE_VALUE | — |
| 22 | FICTIF-B-018 | Date de sortie illisible : ignorée | — (offre valide) | UNPARSEABLE_OPTIONAL |
| 23 | FICTIF-B-019 | Prix vide | MISSING_PRICE | — |
| 24 | FICTIF-B-003 | Copie identique de FICTIF-B-003 : ignorée | — (offre valide) | DUPLICATE_IDENTICAL_ROW |
| 26 | FICTIF-B-021 | Langue IT : valide ici, bloquée par le pricing FR | — (offre valide) | — |
| 27 | FICTIF-B-022 | Ligne « non fictive » dans un jeu FICTIF | FICTIF_FLAG_MISMATCH | — |
| 28 | FICTIF-B-023 | TVA en texte « 8.1 % » | — (offre valide) | — |

Signaux de niveau import : BLANK_ROWS, QUARANTINE_RATIO_EXCEEDED.

## `FICTIF_flux_grossiste_c.xml` — statut attendu PARTIAL (23 lignes lues)

| Ligne | SKU | Anomalie volontaire | Quarantaine attendue | Signal attendu |
|---|---|---|---|---|
| 1 | FICTIF-C-001 | Ligne propre, deux paliers | — (offre valide) | — |
| 2 | FICTIF-C-002 | Ligne propre | — (offre valide) | — |
| 3 | FICTIF-C-003 | Ligne propre | — (offre valide) | — |
| 4 | FICTIF-C-004 | Ligne propre | — (offre valide) | — |
| 5 | FICTIF-C-005 | Ligne propre | — (offre valide) | — |
| 6 | FICTIF-C-006 | Allocation annoncée sans accord écrit : ignorée | — (offre valide) | ALLOCATION_NOT_FIRM |
| 7 | FICTIF-C-007 | Accessoire multilingue (langue NA) | — (offre valide) | — |
| 8 | FICTIF-C-008 | Langue EN : valide ici, bloquée par le pricing FR | — (offre valide) | — |
| 9 | FICTIF-C-009 | Devise GBP non autorisée | UNKNOWN_CURRENCY | — |
| 10 | FICTIF-C-010 | Base HT/TTC vide | UNKNOWN_VAT_BASIS | — |
| 11 | FICTIF-C-011 | Prix zéro | NON_POSITIVE_PRICE | — |
| 12 | FICTIF-C-012 | Doublon de SKU (1/2) | DUPLICATE_SKU | — |
| 13 | FICTIF-C-012 | Doublon de SKU (2/2) | DUPLICATE_SKU | — |
| 14 | FICTIF-C-013 | GTIN au checksum faux | INVALID_GTIN | — |
| 15 | FICTIF-C-014 | « multilingue » refusé pour un produit de cartes | UNKNOWN_LANGUAGE | — |
| 16 | FICTIF-C-015 | Paliers : prix qui remonte | INVALID_TIER | — |
| 17 | FICTIF-C-016 | Palier sans quantité | INVALID_TIER | — |
| 18 | FICTIF-C-017 | Prix illisible | UNPARSEABLE_PRICE | — |
| 19 | FICTIF-C-018 | Prix au carton sans nombre d'unités ni colisage | UNKNOWN_UNIT_BASIS | — |
| 20 | (vide) | Attribut sku absent | MISSING_SKU | — |
| 21 | FICTIF-C-020 | Prix au carton (6 displays) | — (offre valide) | — |
| 22 | FICTIF-C-021 | Coffret « Collection Classeur » | — (offre valide) | — |
| 23 | FICTIF-C-022 | « Coffret ETB » = ETB ; rupture | — (offre valide) | — |

Signaux de niveau import : QUARANTINE_RATIO_EXCEEDED.

## `FICTIF_offres_grossiste_a_incomplet.csv` et `FICTIF_flux_grossiste_c_perime.xml`

- Import tronqué : 5 lignes < 80 % des 22 lignes de la veille (hypothèse de seuil) => `INCOMPLETE_IMPORT`,
  import entier en quarantaine, offres de la veille conservées (elles vieillissent), stock local intact.
- Flux périmé : `exporte_le` = 1.10.2026 (> 24 h) => `STALE_SNAPSHOT`, import entier en quarantaine.

## `FICTIF_tarif_email_assiste.yaml` (import assisté email/PDF)

- Ligne 5 : 20 × 4,10 = 82,00 mais total recopié 80,00 => contrôle `LINE_TOTAL_MATCH` bloquant.
- Ligne 6 : GTIN absent => avertissement (fiche brouillon), non bloquant.
- Total du document : lignes + port 35,00 = 1 316,80 (cohérent avec les totaux recopiés).
- La revue reste « A_VALIDER_HUMAINEMENT » ; `approve_review` refuse tant qu'un contrôle bloquant subsiste.

## Validation humaine requise

- [ ] Aucune décision commerciale : ces fichiers ne servent qu'aux tests.
- [ ] Vérifier qu'aucun fichier de ce dossier n'est utilisé par un dictionnaire non FICTIF ni publié.
- [ ] Remplacer ces jeux par l'exemple de fichier réel du premier fournisseur dès réception (BP §13), archivé hors dépôt.
