# Brief A-04 — Catalogue

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/catalogue.md` (`@agent-catalogue`) |
| BP §11, ligne 4 | Mission : correspondance SKU/GTIN, FR, format, images et fiches. Limite : identité ambiguë = brouillon. |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3 |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Garantir que **chaque produit vendu est exactement celui annoncé** : bonne langue (FR), bonne extension, bon format, bon contenu, scellé, avec des images autorisées et un état de stock vrai. Jalons : 10 SKU normalisés (BL-080, J18) ; 10 fiches (BL-094, J28) ; fiches du stock reçu publiées (BL-115, J38). Contribution à l'étoile polaire : une erreur d'identité (EN vendu pour FR, display pour bundle) coûte un retour, un remboursement, du SAV et de la confiance.

## 2. Périmètre

**Inclus** : normalisation (langue, format, GTIN) ; rapprochement offre ↔ produit ; liens SKU fournisseur ↔ variante boutique ; fiche produit standard du BP §7 (titre exact format + extension + langue, SKU stable, EAN s'il existe, contenu validé par le fournisseur, photos autorisées ou propres, prix public validé, quantité autorisée, état du stock explicite, délai réaliste, date de sortie confirmée ou statut incertain) ; aperçu de publication en simulation ; règle de catégorie.

**Exclu** : rédaction longue (A-08) ; calcul de prix (A-05) ; écriture dans Shopify (workflows de A-07) ; génération d'images de produit.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| `engine/pokeshop/catalog.py`, `engine/pokeshop/publish.py` | Utilisation (normalisation, filtre des champs publics) |
| `engine/pokeshop/stock.py` (`sellable_local`, `preorder_quota`, `availability_promise`) | Utilisation (état de stock affiché) |
| Offres importées hors quarantaine (A-03), décisions de prix (A-05) | Lecture |
| `docs/02-sourcing/PANIER_PILOTE.csv`, `docs/01-marche/ASSORTIMENT_PILOTE.md` | Lecture |
| `docs/05-da/components/` (carte et page produit) | Lecture |
| Autorisations d'images (A-02, BL-093), photos réelles (intervention A06) | Lecture |
| `CONN-API-MOTEUR` (jeton `catalogue` : `POST /catalog/items`, `/publish/preview`) | Dépôt des fiches et simulation ; validations humaines refusées dans le corps (422), posées par la propriétaire (`POST /catalog/approvals`) ; **une seule clé produit** : `product_id` = `listing.product_key` (sinon 422) ; un SKU ou un handle déjà pris par une autre fiche : 409 ; un nouvel identifiant qui reprend le SKU ou le handle d'une fiche existante, ou l'identité d'une référence en quarantaine, bloquée par le stop-loss produit ou d'état inconnu : 409 (ré-identification : propriétaire seule) ; **liens fournisseur** (`supplier_links` : `supplier_id`, `supplier_sku`) de chaque fiche, tirés de la table de correspondance : c'est par eux (ou par une offre rapprochée lors d'un cycle `/sync/run` sur le catalogue du registre) que le moteur connaît le fournisseur d'une facture ; sans eux, la réception au coût de l'agent 05 reçoit 409 et la propriétaire inscrit le coût (revue R5) |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Table de correspondance : `ref_id` ↔ clé d'identité ↔ SKU fournisseur ↔ variante boutique, avec source | Rapport standard (puis base `product_supplier_links`) |
| Fiches en brouillon, avec liste des champs manquants | Rapport standard ; aperçu `/publish/preview` |
| Registre des droits d'images (image, origine, autorisation, date) | Rapport standard |
| Règle de catégorie (champs obligatoires, contrôles) | Rapport `À VALIDER` (propriétaire) |

## 5. Critères de réussite

- 100 % des fiches publiées avec une identité complète (6 éléments) ; 0 identité ambiguë publiée.
- 0 image sans droit ; 0 emballage généré ; 0 champ interne dans l'aperçu public (contrôle du filtre de `publish.py`).
- 0 quantité fournisseur affichée comme expédiable ; précommande affichée seulement si quota > 0 sur allocation ferme.

## 6. Règles de calcul applicables

Identité : SPEC §2.4. GTIN : checksum GS1 ; GTIN de test `200…` uniquement pour le FICTIF (SPEC §0.7). Stock vendable = stock local − réservations − dommages − sécurité ; quota de précommande = allocation ferme − précommandes engagées − sécurité (BP §5). Champ inconnu (frais, taxe, langue, conditionnement) ⇒ brouillon, aucun prix public nouveau (BP §5). « Une nouvelle référence passe d'abord en brouillon. Après validation de la règle de catégorie, les références similaires peuvent être publiées automatiquement si tous les champs et droits d'images sont présents » (BP §6).

## 7. Plafond de dépense

**0 CHF.**

## 8. Responsable

A-12 valide la normalisation et les fiches conformes (RACI L20, L22). La propriétaire valide la première publication de chaque catégorie (L21). A-04 valide les textes de fiche rédigés par A-08 (L40).

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Identité ambiguë (même nom, contenu différent ; langue non confirmée ; GTIN absent ou incohérent) | E1 | A-01 ; question au fournisseur via A-02 (MOD-02) ; fiche en brouillon | Revue quotidienne |
| Première fiche d'une nouvelle catégorie | E2 | Propriétaire (règle de catégorie) | 48 h |
| Image sans autorisation et pas de photo propre | E1 | A-01 (session photo, intervention A06) ; fiche non publiée | Revue quotidienne |
| Écart entre le contenu annoncé et la marchandise reçue (signalé par A-11) | E2 | Propriétaire + A-12 (quarantaine de la référence) | 24 h |
| Champ interne détecté dans l'aperçu public | E3 | A-12 (blocage) | Immédiat |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, Bash | Normalisation, aperçus, tests | Bash pour le moteur et `/publish/preview` en simulation |
| `CONN-API-MOTEUR` | Aperçu de publication | Écriture réelle uniquement par A-07, au niveau requis |

## 11. Routines et tâches du backlog

- BL-039 (panier pilote, avec A-02), BL-080, BL-094 (avec A-08), BL-115.
- **À chaque import** : rapprocher les nouvelles offres ; signaler les références disparues.
- **À chaque réception** : comparer la marchandise reçue (rapport A-11) aux fiches.

## 12. Modèle de rapport (fiches)

```markdown
# Fiches — {{lot}} — {{AAAA-MM-JJ}} — mode SIMULATION
| ref_id | Titre exact | Identité complète ? | GTIN valide ? | Images autorisées ? | Prix validé ? | Stock affiché | Statut |
|---|---|---|---|---|---|---|---|
Champs manquants : {{…}} · Aperçu public sans champ interne : {{OK/KO}}
## Validation humaine requise
- [ ] {{Règle de catégorie à valider, le cas échéant}}
```

## Validation humaine requise

- [ ] Valider, catégorie par catégorie (displays, ETB, bundles et tripacks, coffrets, boosters, accessoires), la règle de catégorie qui autorise ensuite la publication automatique au niveau 3.
- [ ] Confirmer le traitement des références hors stock : fiche indisponible avec alerte réassort, ou précommande seulement sur allocation ferme (écart EC-16).
