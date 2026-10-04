# Dictionnaires de champs fournisseurs

Un fichier YAML par fournisseur : `<supplier_id>.yaml`. Il dit à l'importeur
(`engine/pokeshop/importers/`) comment lire le fichier de CE fournisseur : colonnes, devise,
HT ou TTC, séparateur décimal, prix à l'unité ou au carton, paliers de remise. Chargement :
`pokeshop.importers.load_mapping("<supplier_id>")` (dossier modifiable par `POKESHOP_MAPPINGS_DIR`).

> Aucun fournisseur réel n'a envoyé de fichier au 4 octobre 2026. Les cinq dictionnaires
> fournisseurs sont des **TEMPLATE** : aucun format n'est confirmé (BP §2 : « des pistes
> commerciales vérifiées publiquement, pas des partenariats acquis »).

## Inventaire

| Fichier | Fournisseur | Statut | Usage |
|---|---|---|---|
| `generic.yaml` | Modèle générique | TEMPLATE | Point de départ d'un nouveau fournisseur |
| `asmodee_fr.yaml` | Asmodee France (priorité 1) | TEMPLATE | À compléter à réception d'un fichier réel |
| `matoo_miao.yaml` | Matoo et Miao (priorité 1) | TEMPLATE | idem |
| `tcg_distribution.yaml` | TCG Distribution (priorité 1) | TEMPLATE | idem |
| `otakuworld.yaml` | OtakuWorld (priorité 2) | TEMPLATE | idem |
| `cardcosmos.yaml` | CardCosmos (priorité 2) | TEMPLATE | idem |
| `fictif_grossiste_a.yaml` | FICTIF (CSV) | FICTIF | Jeux d'essai `data/samples/` |
| `fictif_grossiste_b.yaml` | FICTIF (Excel) | FICTIF | idem |
| `fictif_grossiste_c.yaml` | FICTIF (XML) | FICTIF | idem |

## Statuts

| Statut | Signification | Import réel (`dry_run=False`) |
|---|---|---|
| `TEMPLATE` | Aucun format confirmé ; en-têtes proposés | Refusé (`MappingError`) |
| `FICTIF` | Jeux d'essai ; `supplier_id` commence par `fictif_` | Refusé |
| `VALIDE` | Vérifié sur un fichier réel : `validated_by`, `validated_at`, `validated_on_sample_sha256` obligatoires | Autorisé (selon le niveau d'autonomie, SPEC §0.6) |

## Champs du dictionnaire

| Clé | Rôle | Exemple |
|---|---|---|
| `file_format` | `csv`, `xlsx` ou `xml` | `csv` |
| `csv` | `delimiter`, `quotechar`, `encoding`, `skip_rows` | `delimiter: ";"` |
| `xlsx` | `sheet`, `header_row`, `source_ts_cell` (date d'export) | `header_row: 4`, `source_ts_cell: "B2"` |
| `xml` | `record_path`, `source_ts_attribute`, `namespaces` | `record_path: "./offre"` |
| `numbers` | `decimal_separator` (`,` ou `.`), `thousands_separators` | `decimal_separator: ","` |
| `dates` | `formats`, `timezone` (horodatages sans fuseau) | `timezone: "Europe/Zurich"` |
| `columns` | champ normalisé -> en-têtes acceptés (XML : `@attribut`, `parent/enfant`, `palier[2]/@qte`) | `price: [prix, prix_net]` |
| `required_fields` | colonnes obligatoires (sinon import `FAILED` / `MAPPING_MISMATCH`) | `[supplier_sku, price]` |
| `tiers` | paliers : `min_qty` ou `min_qty_column` + `price_column` ou `discount_pct_column` | voir `fictif_grossiste_a.yaml` |
| `quantities` | base `UNIT` ou `PACK` du stock, du MOQ, des paliers, de l'allocation | `moq: PACK` |
| `defaults` | valeurs si la colonne manque — **confirmées par écrit uniquement** | `currency: EUR` |
| `value_maps` | libellés propres au fournisseur -> valeur canonique | `price_basis: {"prix pro": HT}` |
| `allowed_currencies` | devises acceptées (autres => quarantaine) | `[CHF, EUR]` |
| `allocation_is_firm` / `allocation_evidence` | allocation ferme (accord écrit) ; sinon l'allocation est ignorée | `false` |
| `extension_tables` | tables d'alias supplémentaires — FICTIF seulement | `data/samples/FICTIF_extensions_aliases.yaml` |
| `notes` | points à confirmer (texte libre) | — |

Champs normalisés disponibles : `supplier_sku`, `gtin`, `designation`, `language`, `extension`,
`format`, `content`, `sealed`, `price`, `currency`, `price_basis`, `vat_rate`, `unit_basis`,
`units_per_pack`, `carton_qty`, `moq`, `availability`, `available_qty`, `allocation_qty`,
`release_date`, `incoterm`, `ship_from_country`, `vat_country`, `stock_pool_id`, `source_ts`, `fictif`.

## Ce que l'importeur décide seul (et ce qu'il ne devine jamais)

| Situation | Résultat |
|---|---|
| Devise absente, symbole `$`, devise hors liste, `€` dans un tarif CHF | Quarantaine (`UNKNOWN_CURRENCY` / `CURRENCY_CONFLICT`) |
| HT/TTC absent, ou « net » seul | Quarantaine (`UNKNOWN_VAT_BASIS`) |
| « palette », « display », « boîte » comme unité de prix ; carton sans nombre d'unités | Quarantaine (`UNKNOWN_UNIT_BASIS`) |
| Prix « à l'unité » avec 6 unités par colis | Quarantaine (`UNIT_CONFLICT`) |
| `12.50` dans un fichier à virgule décimale | Quarantaine (`UNPARSEABLE_PRICE`) |
| Prix 0 ou négatif ; ×10 ou ÷10 vs dernier import ; devise ou HT/TTC changés | Quarantaine |
| GTIN au checksum faux ; langue inconnue ou multiple | Quarantaine |
| GTIN absent, format/extension/contenu inconnus, TVA facturée inconnue | Offre acceptée **en brouillon** (anomalie) |
| Capture > 24 h, import < 80 % des lignes précédentes (hypothèse), import vide | Import entier en quarantaine ; offres précédentes conservées ; stock local intact |

## Procédure à réception du premier fichier réel (BP §13 « La première action concrète »)

1. Archiver le fichier hors dépôt (`POKESHOP_DOCS_PRIVES`) et noter son sha256.
2. Copier le TEMPLATE du fournisseur ; remplacer les en-têtes par ceux du fichier, ligne par ligne.
3. Ne remplir un `default` que s'il est écrit par le fournisseur (email, conditions) ; citer la preuve dans `notes`.
4. Lancer l'import en simulation (`run_import(..., dry_run=True)`), lire le rapport (`report_markdown()`).
5. Corriger jusqu'à zéro anomalie critique due au dictionnaire ; les anomalies de données vont au fournisseur.
6. Faire valider par une personne : statut `VALIDE`, `validated_by`, `validated_at`, `validated_on_sample_sha256`.

## Validation humaine requise

- [ ] Fournir, fournisseur par fournisseur, l'exemple de fichier prix/stock et l'accord écrit sur l'usage automatisé.
- [ ] Confirmer par écrit chaque valeur par défaut (devise, HT/TTC, unité/carton, langue, TVA facturée, pays d'expédition).
- [ ] Valider le seuil « import incomplet » (80 % des lignes précédentes) et le seuil d'escalade (20 % de lignes en quarantaine) — hypothèses.
- [ ] Signer le passage au statut `VALIDE` de chaque dictionnaire (nom, date, sha256 du fichier de référence).
