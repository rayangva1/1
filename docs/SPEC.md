# SPEC technique commune — Boutique Pokémon FR Suisse

> Contrat partagé par tous les agents de build. Source de vérité métier :
> `docs/business-plan/business_plan_extrait.txt` (texte du BP du 4 octobre 2026).
> En cas de conflit, le BP gagne ; signaler l'écart dans `docs/00-pilotage/ECARTS_BP.md`.

## 0. Principes non négociables (tirés du BP)

1. Calcul financier **déterministe, vérifiable, versionné**. `decimal.Decimal` partout, jamais `float`.
   L'IA extrait/rédige, elle ne décide jamais d'une TVA, d'un taux de change ou d'un montant.
2. **Aucun coût interne, prix B2B, marge ou donnée personnelle** dans le HTML public, les payloads
   Shopify publics, les prompts marketing ou les visuels.
3. **Aucun faux stock**. Stock fournisseur ≠ stock boutique. Pas de précommande sans allocation ferme (pré-drop :
   §2.11 ; l'argent encaissé avant réception est une **dette** jusqu'à l'expédition).
4. Donnée amont > 24 h ⇒ bloque achats et nouvelles promesses de dispo, **n'empêche pas** de vendre le stock local réel.
5. Champ inconnu (frais, taxe, langue, conditionnement) ⇒ fiche en **brouillon**, aucun nouveau prix public.
6. Tout tourne en **mode simulation (dry-run) par défaut**. Les écritures réelles exigent un flag explicite
   et le niveau d'autonomie adéquat (1 à 4, cf. BP §13).
7. Aucune donnée fournisseur réelle n'existe encore : tous les jeux d'essai sont **FICTIFS** et marqués comme tels
   (préfixe `FICTIF_` ou colonne `fictif=true`). Aucun EAN réel inventé présenté comme vrai : utiliser des GTIN
   de test au checksum valide commençant par `200` (plage interne GS1 « restricted circulation »).
8. Pas d'usage du logo/personnages Pokémon dans la DA. « Pokémon » sert uniquement à désigner les produits.
9. Pas de scraping de portails, pas de contournement CAPTCHA/contrôle d'accès.
10. Français (Suisse romande) partout côté docs et UI. Montants en CHF. Code et identifiants en anglais.
11. **Fermé par défaut.** En cas de doute, d'état illisible ou de donnée non vérifiable, un garde-fou **bloque** ou renvoie à la
    propriétaire (`NEEDS_HUMAN_APPROVAL`) ; il n'approuve jamais. Aucune valeur décisive (trésorerie, solde, taux de change,
    plafond, seuil, résultat de test, référence de réarmement) n'est **auto-déclarée** par l'agent qui en bénéficie : elle vient
    des registres du moteur, d'un autre jeton nommé, ou de la propriétaire avec son jeton. L'acteur est déduit du jeton.
12. **Secrets hors de portée de la flotte.** Les secrets vivent au coffre et dans l'environnement des conteneurs, hors de
    l'arborescence où travaillent les agents ; `.claude/settings.json` ne contient que des règles `deny` qui les rendent
    illisibles (aucune règle `allow`). Seules des empreintes sha256 des jetons sont configurées ; les secrets des passerelles
    n8n (un par webhook et par agent appelant) ne vivent que dans n8n et au coffre, et l'administration de n8n reste à la propriétaire.

## 1. Stack

- Python 3.11, package `pokeshop` dans `engine/pokeshop/`, tests `pytest` dans `tests/`.
- Dépendances autorisées : stdlib, `pydantic>=2`, `fastapi`, `uvicorn`, `httpx`, `openpyxl`, `pyyaml`, `jinja2`.
  Pilote PostgreSQL `psycopg` (3) : optionnel, importé seulement si `POKESHOP_DATABASE_URL` est fourni (image Docker).
  Rien d'autre sans justification dans le README du module.
- Base : PostgreSQL 16 (compatible Supabase). Migrations SQL brutes dans `db/migrations/NNN_nom.sql`.
- Orchestrateur : n8n (exports JSON dans `orchestration/n8n/`), qui appelle l'API HTTP du moteur.
- Boutique : Shopify (Admin GraphQL API, `productSet`, `inventorySetQuantities`). Client avec transport mockable.
- `docker-compose.yml` à la racine : postgres + n8n + api moteur (pour plus tard ; pas lancé ici).
- Lancer les tests : `scripts/run_all_tests.sh` (toutes les suites : `tests/` et les outils des dossiers `docs/` et `site/`,
  chacune dans son processus) ; `python -m pytest -q` ne lance que `tests/` (le `conftest.py` racine ajoute `engine/` au path).

## 2. Modules du package `pokeshop` (propriétaires et signatures)

Chaque module est propriété d'UN agent. Les autres l'importent, ne le modifient pas.
Les types partagés vivent dans `pokeshop/models.py` (propriété : agent `core-engine`).

### 2.1 `pokeshop/models.py` (core-engine)
Dataclasses `frozen=True` ou modèles pydantic. Minimum :
- `VatMode` (Enum) : `EFFECTIVE` (assujetti méthode effective, TVA récupérable) | `NOT_REGISTERED` (non assujetti, TVA non récupérable dans le coût).
- `PricingParams` : `vat_rate_sales: Decimal` (t ; 0 si NOT_REGISTERED), `payment_pct: Decimal` (r), `payment_fixed: Decimal` (b),
  `logistics_cost: Decimal` (L), `after_sales_provision: Decimal` (R), `acquisition_cost: Decimal` (A),
  `target_margin: Decimal` (m), `hard_floor_margin: Decimal` (=0.12), `hard_floor_chf_per_order: Decimal` (=8),
  `rules_version: str`.
- `LandedCostInput` : `purchase_net: Decimal`, `currency: str`, `fx_rate_to_chf: Decimal`, `fx_source: str`, `fx_date: date`,
  `price_includes_vat: bool`, `supplier_vat_rate: Decimal`, `units_per_pack: int`, `inbound_freight_alloc: Decimal`,
  `customs_and_fees: Decimal`, `import_vat: Decimal`, `vat_mode: VatMode`.
- `PriceDecision` : `floor_price`, `recommended_price` (arrondi .90 vers le haut), `contribution_chf`, `contribution_pct`,
  `status` (`OK` | `REVIEW` | `BLOCKED` | `DRAFT`), `reasons: list[str]`, `rules_version`, `inputs_hash`.

### 2.2 `pokeshop/pricing.py` (core-engine)
- `landed_unit_cost(inp: LandedCostInput) -> Decimal` — BP §4 « Coût rendu par unité ».
- `floor_price(C, params) -> Decimal` — `P = (C + b + L + R + A) / ((1 − m)/(1 + t) − r)` ; lève `PricingError` si dénominateur ≤ 0.
- `round_up_retail(p, ending=Decimal("0.90")) -> Decimal` — arrondi au prochain X.90 ≥ p, puis **revérifier la marge**.
  Le prix public par défaut suit la grille par paliers `rounding_tiers` des règles (X4,90 / X9,90 au-dessus de 100 CHF), qui
  reproduit le cas BP 208,79 → 209,90 (écart EC-F-03 de `docs/00-pilotage/ECARTS_BP.md`).
- `contribution(price_ttc, C, params) -> (chf, pct_of_net)` — vérif : 199.90 ⇒ net 184.92 ; paiement 5.30 ; contribution 30.62 ; 16.56 %.
- `decide_price(C, params, market_ref: Decimal|None, current_public: Decimal|None, unknown_fields: list[str]) -> PriceDecision`
  appliquant la table de règles BP §5 (cible 20 %, plancher dur 12 % & 8 CHF/commande, >10 % au-dessus marché ⇒ REVIEW,
  variation >5 %/jour ⇒ REVIEW, champs inconnus ⇒ DRAFT).
- `basket_contribution(lines, params, shipping_charged, discount) -> ...` — frais fixes **une seule fois** par commande.
- Cas de référence obligatoires en test : 208.79 → 209.90 (assujetti) ; 207.28 (t=0, C=151.34).

### 2.3 `pokeshop/stock.py` (core-engine)
- `sellable_local(on_hand, reserved, damaged, safety) -> int` (jamais < 0).
- `preorder_quota(firm_allocation, committed_preorders, safety) -> int`.
- `is_stale(source_ts, now, max_age=timedelta(hours=24)) -> bool`.
- `availability_promise(...)` — refuse toute promesse basée sur stock amont périmé ou non alloué.
- `reorder_point(avg_daily_sales, lead_time_days, safety) -> Decimal` ;
  `propose_reorder(...)` respectant MOQ, cartons, budget dispo, plafond 25 % par extension → **proposition à valider**, jamais commande.

### 2.4 `pokeshop/catalog.py` (data-pipeline)
- Clé d'identité produit : `GTIN + langue + extension + format + contenu + état(scellé)`.
- `normalize_language(raw) -> "FR"|"EN"|"JP"|"DE"|"IT"|"NA"|"UNKNOWN"` (`NA` : accessoire sans texte, écart EC-D-04), `normalize_format(raw)` (display, etb, bundle, tripack, coffret, booster, accessoire…),
  `validate_gtin(code) -> bool` (checksum GS1), `match_offer_to_product(...)` ⇒ identité ambiguë = brouillon.

### 2.5 `pokeshop/importers/` (data-pipeline)
- `base.py` : interface `SupplierConnector.fetch() -> RawSnapshot` (contenu brut + horodatage + source), `parse(snapshot) -> list[SupplierOffer]`.
- `csv_importer.py`, `xlsx_importer.py`, `xml_importer.py` pilotés par un **dictionnaire de champs** YAML par fournisseur
  (`data/supplier_mappings/<fournisseur>.yaml`).
- Validations : devise, HT/TTC, unité vs carton, paliers de remise, prix 0, prix ×10 vs dernier import, doublons, import incomplet ⇒ **quarantaine**.
- Jeux d'essai FICTIFS dans `data/samples/`.

### 2.6 `pokeshop/shopify_client.py` + `pokeshop/publish.py` (integrations)
- Client GraphQL Admin avec transport injectable (mock en test), `dry_run=True` par défaut, clés d'idempotence,
  journal des écritures, retry/backoff, contrôle de concurrence pour l'inventaire par `changeFromQuantity` et `@idempotent`
  (API 2026-10 ; `compareQuantity` est supprimé depuis 2026-04, écart EC-I-05).
- `publish.py` : construit les payloads `productSet` à partir du catalogue validé — **filtre strict des champs publics**
  (test qui échoue si un champ coût/marge/fournisseur fuit).

### 2.7 `pokeshop/api.py` (integrations)
FastAPI, appelée par n8n, le tableau de bord et les agents. Liste **exhaustive** des routes (`engine/pokeshop/api.py`
et `api_dashboard.py`), contrôlée par `docs/08-agents/outils/verifier_agents.py` (`check_api_routes_documented`).

**Matrice d'autorisations versionnée, refus par défaut** : `engine/pokeshop/authz.py` (`AUTHZ_VERSION`), table lisible
générée dans `docs/08-agents/MATRICE_API.md`. Chaque route y déclare sa nature (lecture, aperçu, écriture) et les rôles
admis ; une route absente de la matrice est refusée (403, `authz.route_refused`) ; un test parcourt **toutes** les routes
FastAPI et échoue si une route d'écriture n'y figure pas ou s'ouvre au jeton commun (`tests/test_revue_r3.py`).
Aucune valeur décisive n'est fournie par l'agent qui en bénéficie, ni par le jeton commun.

Jetons (empreintes sha256 seulement dans l'environnement ; acteur journalisé **déduit du jeton**, jamais déclaré) :
- **COMMUN** = `X-Pokeshop-Token` dont l'empreinte est `POKESHOP_API_TOKEN_SHA256` (facultatif) : lecture et aperçus en
  simulation **seulement** ; toute écriture : 403 journalisé (`….common_token_refused`).
- **RÔLE** = jeton nommé, nom = rôle de la matrice (agents de `.claude/agents/` et connecteurs n8n) :
  `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (une variable par rôle) ou `POKESHOP_AGENT_TOKENS_SHA256=rôle:empreinte,…` ;
  un nom inconnu de la matrice fait échouer le démarrage. Rôle non admis : 403 (`….role_refused`).
- **PROPRIO** = `X-Pokeshop-Owner-Token` valide (`POKESHOP_OWNER_TOKEN_SHA256`), distinct du jeton d'API, **suffisant
  seul** (aucun `X-Pokeshop-Token` requis, revue R4 R3-DOC-01) ; admis sur toutes les lectures et toutes les écritures
  sauf `POST /mandate/check` (la propriétaire ne dépense pas via le mandat des agents).
- Aucune empreinte de jeton d'API configurée : 503 (sauf jeton propriétaire valide, qui suffit seul) ; jeton absent ou faux : 401. Les documents `/docs` et `/openapi.json` sont fermés.

| Route | Rôles admis (en plus de PROPRIO, sauf mention) | Règles décisives |
|---|---|---|
| `GET /health` | public, sans secret | workflow 05 |
| `POST /pricing/quote`, `POST /pricing/basket`, `POST /stock/sellable`, `POST /publish/preview` | COMMUN (aperçu) | prix, publication : valeurs du moteur et des registres ; champs de validation ou d'identifiant Shopify dans la fiche : 422 |
| `GET /pricing/approvals`, `GET /catalog`, `GET /catalog/approvals`, `GET /sync/history`, `GET /incidents`, `GET /autonomy`, `GET /stoploss/status`, `GET /capital/movements`, `GET /northstar` | COMMUN (lecture) | `consecutive_clean_runs` : cycles réels distincts ; `GET /northstar` : `incomplete` et `derivation_errors` quand une écriture dérivée d'une commande est impossible, `cost_of_sales_pending` quand le coût des ventes d'une commande attend l'inscription du coût de réception (gates : critère ROUGE), `predrop_collected_not_recognized_chf` (argent encaissé en pré-drop, dette non reconnue en ventes) ; journal illisible : 503 |
| `GET /dashboard/daily`, `GET /dashboard/weekly`, `GET /dashboard/monthly` | COMMUN (lecture) | journal non relu : KPI indisponibles, statut CRITIQUE |
| `POST /pricing/approvals` | PROPRIO seul | motif ≥ 10 caractères, `valid_hours` 1-168 ; `floor_exception_ref` sous plancher (C27) |
| `POST /pricing/approvals/{approval_id}/revoke` | `finance-pricing`, `qa-conformite`, `chef-de-projet` | acte protecteur |
| `POST /stock/receive` | `operations-sav` | réceptionnaire journalisé (`by`), base des coûts historiques ; retour physique conforme : `ref` = `return:<avoir>` (base d'un RETURN au coût) |
| `POST /stock/reorder-proposal` | `finance-pricing`, `operations-sav` | `cap_exceptions` non vide : PROPRIO (C18) |
| `POST /imports/{supplier}/run` | `donnees-fournisseurs`, `n8n-01-sync` | toujours en simulation |
| `POST /catalog/items` | `catalogue` | `approved`, `content_validated`, `category_rule_validated`, identifiants Shopify, prix publié : 422 ; **clé unique** `product_id` = `listing.product_key` (422) ; SKU ou handle en double : 409 ; nouvel identifiant qui reprend le SKU ou le handle d'une fiche existante, ou l'identité d'une référence en quarantaine, bloquée par le stop-loss produit ou d'état inconnu : 409 (PROPRIO seule) |
| `POST /catalog/approvals` | PROPRIO seul | validation humaine liée au contenu (`listing_sha256`) ; fiche modifiée : `VALIDATION_OUTDATED` |
| `POST /catalog/cost-inputs` | `finance-pricing` | aucun champ `fx_*` : 422 |
| `POST /sync/run` | `n8n-01-sync`, `site-integrations` | validations lues au registre par clé canonique ; catalogue du corps : simulation seulement (`dry_run:false` : 409) ; quarantaine et stop-loss produit sur toutes les clés de la référence ; `dry_run:false` : porte de gouvernance + `POKESHOP_DRY_RUN=false` ; prix de repli = dernier prix publié du registre, sinon brouillon ; coût de remplacement (référence d'une réception) inscrit seulement par un cycle avec catalogue **et** frais du registre (provenance des frais inscrite), jamais par un cycle avec catalogue ou frais du corps (revue R5, R4-DOC-09) |
| `POST /incidents` | tous les rôles nommés | fournisseur ou fiche FICTIF : déduit du catalogue, jamais déclaré ; `simulation` admis seulement si le moteur est en simulation (`POKESHOP_DRY_RUN`), sinon incident réel |
| `POST /incidents/{incident_id}/test` | tous les rôles nommés | `passed:true` : `qa-conformite` (≠ ouvreur) ou PROPRIO ; `test_ref` = `run_id` d'un cycle PROPRE en simulation, catalogue du registre, postérieur à l'ouverture, lancé par un autre principal, sur le fournisseur et la référence de l'incident, sans source FICTIVE — sauf incident sur données FICTIVES, ou déclaré `simulation: true` et ouvert moteur en simulation (un incident sur données réelles ouvert sans ce drapeau exige un cycle réel) |
| `POST /incidents/{incident_id}/resume`, `POST /incidents/{incident_id}/close` | `qa-conformite`, `chef-de-projet`, `n8n-04-incidents` | incident critique : PROPRIO |
| `POST /autonomy` | tous les rôles nommés | hausse de niveau : PROPRIO |
| `POST /stoploss/state/refresh` | `n8n-07-stoploss` | photo construite par le moteur, datée par le plus ancien relevé de cash ; source manquante ou périmée (soldes, apports, déclaration des dettes de plus de 24 h) : 409 nommant la source ; dettes = déclarées + factures enregistrées non payées + **réservations pré-drop encaissées ni expédiées ni remboursées** (dérivées du registre du pré-drop, déduites du cash disponible, `sources.precommandes`) ; créances : relevé PROPRIO seulement ; `sources.complete` / `sources.incomplete` (coût des ventes en attente) ; publicité = MAX(déclaration, paiements pub **engagés** — approuvés ou exécutés — du mandat) |
| `POST /stoploss/state` | PROPRIO seul | photo déposée (relevé de la propriétaire) : cash ≠ relevés du connecteur de trésorerie : 409 ; `capital_movements` du corps : 422 ; dette des réservations pré-drop dérivée du registre : jamais moins (ligne ajoutée ou relevée, cash disponible diminué d'autant, `overridden`) |
| `POST /stoploss/freeze` | tous les rôles nommés | acte protecteur |
| `POST /stoploss/rearm` | PROPRIO seul | `reference_chf` attestée (C18) |
| `POST /stoploss/baseline` | PROPRIO seul | `with_photo:true` : premier point zéro posé atomiquement avec la première photo (C19) ; sinon photo acceptée requise |
| `POST /stoploss/capital-memory/reset` | PROPRIO seul | C23 |
| `POST /mandate/check` | `chef-de-projet`, `sourcing`, `direction-artistique`, `site-integrations`, `communication`, `acquisition`, `operations-sav`, `n8n-08-mandat` (PROPRIO **non** ; `finance-pricing` **non** : il paie, revue R5 R4-DOC-11) | `requested_by` = nom du jeton ; relais `n8n-08-mandat` : `requested_by` parmi les agents qui dépensent (sinon 403), trésorerie non vérifiée ; tout poste du stop-loss non attesté par son rôle, ou étoile polaire incomplète (coût des ventes en attente) : `TREASURY_UNVERIFIED` ; dépense pub sans relevé de `connecteur-publicite` de moins de 24 h : `TREASURY_UNVERIFIED` |
| `POST /mandate/human-decision` | PROPRIO seul | `APPROVE` / `REFUSE` d'une dépense `PENDING_HUMAN` (24 h, sinon expirée : 409) : seule voie de `HUMAN_APPROVED`, comptée au stop-loss pub à sa date (revue R5, R4-DOC-03) |
| `POST /mandate/revoke` | tous les rôles nommés | acte protecteur |
| `POST /treasury/paypal-balance`, `POST /treasury/bank-balance` | `connecteur-tresorerie` | connecteurs en lecture seule (B26) |
| `POST /treasury/balance-items` | `finance-pricing`, `connecteur-tresorerie` | deux registres **séparés et persistés** (revue R5) : dettes (`preorders_collected_chf` = précommandes **hors pré-drop** — les réservations pré-drop sont dérivées par le moteur et ajoutées — + `debts`, âge accepté 24 h) et créances (`receivables` : PROPRIO seule, rôle : 403 ; jamais effacées par une déclaration de dettes) ; `finance-pricing` ne baisse jamais dettes ni précommandes (403), même après un redémarrage |
| `POST /capital/movements` | PROPRIO seul | seule source des apports et retraits (B25) |
| `POST /ads/activity` | `connecteur-publicite` (jamais `acquisition`) | registre en ajout seul (baisse : 409) ; commandes attribuées : existantes au registre des commandes — sinon écartées seules (`attributed_orders_set_aside`), les dépenses du lot sont enregistrées (revue R5, R4-NEW-01) |
| `POST /fx/rates` | PROPRIO seul | seule source des taux (C23) |
| `POST /orders/shipped` | `n8n-02-commandes` | commande d'une réservation pré-drop : ventes et sortie au CMP **datées de l'expédition** par le moteur (`recognized_at`), jamais du paiement, et fin de la dette (commande à plusieurs pré-drops : entrées `<commande>`, `<commande>#2`… suivies par la commande) ; SKU d'une fiche de réservation (`<SKU>-RESA-<AAAAMMJJ>`) rattaché à la référence de son pré-drop ; coût transporteur réel > 0 et référence d'étiquette ; **lignes** (SKU × quantité) obligatoires, rattachées à la clé produit par le SKU actuel ou un **ancien SKU** de la même clé (historique du catalogue, revue R6, R5-NEW-02) ; **jamais refusée pour un SKU** : SKU inconnu ou porté par plusieurs clés = ligne **non rattachée** (`unresolved_lines`, coût des ventes en attente, `incomplete: true`) ; écrit ventes, frais (complément des frais externes de la commande), logistique, et la sortie au CMP (coût des ventes) ; conflit d'écriture dérivée : 409, rien d'écrit ; **jamais refusée faute de stock valorisé** (revue R5, R4-NEW-01) : coût des ventes **en attente** (`cost_of_sales_pending`), dérivé dès l'inscription du coût et au démarrage ; étoile polaire et photo incomplètes, dépenses en validation humaine d'ici là |
| `POST /orders/{order_id}/refunds` | `n8n-02-commandes`, `operations-sav` | avoir cumulé ≤ ventes de la commande enregistrée ; `lines` = unités retournées (≤ vendues − déjà retournées), vide pour un geste commercial (rien ne revient en stock au coût) |
| `POST /orders/{order_id}/lines/resolve` | PROPRIO seul | rattache une ligne non rattachée (`public_sku`) à une fiche canonique (`product_key`) ; sortie au CMP dérivée ensuite ; journalisé, rejoué au démarrage (revue R6, R5-NEW-02) |
| `POST /northstar/entries` | `n8n-02-commandes`, `finance-pricing` | rôle : montants positifs sur paiement, SAV, acquisition, frais fixes ; ventes, avoirs et montants négatifs (référencés) : PROPRIO ; identifiants `order:`, `refund:`, `cost:`, `expense:`, `fixed:` réservés au moteur (422) ; PAYMENT portant l'`order_id` d'une commande enregistrée : 422 |
| `POST /costs/movements` | `finance-pricing` | réception adossée à `POST /stock/receive` (autre jeton), une fois par réception, une fois par réception physique (SKU **à la réception**, bon), coût unitaire à ± 2 % de la ligne de facture enregistrée (référence prioritaire ; unités reçues au coût ≤ quantité facturée, fournisseur connu du moteur pour la référence — lien du catalogue ou offre rapprochée sur le catalogue du registre — : sinon 409 ; `return:` réservé aux retours) ou du coût rendu de l'offre évaluée avec des frais posés par PROPRIO — jamais des frais posés par `finance-pricing` (sinon, ou sans référence : PROPRIO) ; TVA d'import de la ligne comptée selon le profil TVA du moteur ; sortie de vente (ISSUE) : dérivée des commandes (rôle : 403) ; retour (RETURN) : commande enregistrée, avoir **à lignes** (unités retournées) d'un montant ≥ coût des unités retournées et retour physique `return:<avoir>` déclaré par un autre jeton (`operations-sav`), sinon 403 (coût des ventes encore en attente : 409) ; écart de facture > 2 % : PROPRIO |
| `POST /costs/invoices` | `n8n-03-factures` | facture validée par la propriétaire (workflow 03) : lignes au coût rendu ventilé sur clés canoniques (TVA d'import à part, `import_vat_unit_chf`) ; Σ quantité × coût des lignes ≤ montant dû (sinon 409) ; dette de la photo jusqu'au paiement ; idempotente (autre contenu : 409) |
| `POST /costs/invoices/{invoice_ref}/payments` | `connecteur-tresorerie` | paiement relevé (cumul ≤ montant) : seule baisse de la dette d'une facture |
| `POST /predrop/allocations` | `n8n-03-factures` | allocation **ferme** (confirmation fournisseur validée par PROPRIO dans le workflow 03), jamais par l'agent qui bénéficie du pré-drop ; fiche canonique du catalogue (409) ; fournisseur connu du moteur pour la référence (sinon 409, PROPRIO seule) ; même confirmation : idempotente (autre contenu : 409) ; baisse : 409 (réduction) |
| `POST /predrop/allocations/{product_key}/reduce` | `n8n-03-factures`, `operations-sav` | acte protecteur, baisse seulement (hausse : 409) ; pré-drop servi **en premier** (ordre de paiement), quota drop réduit d'abord, puis remboursement **intégral** des dernières réservations (préparé + brouillon d'email) ; idempotente par confirmation |
| `POST /predrop/demand` | `n8n-06-marketing` | compte **agrégé** d'inscrits consentants intéressés (aucune donnée personnelle : tout autre champ ou une adresse dans `source`, 422) ; plus ancien que celui en vigueur ou daté du futur : 409 |
| `GET /predrop/eligibility/{product_key}`, `GET /predrop/offers`, `GET /predrop/reservations`, `GET /predrop/refunds` | COMMUN (lecture) | éligibilité évaluée sur les registres (deux prix, sans coût ni marge) ; offres publiques en liste blanche (« Réservations ouvertes / fermées », date du drop, deux prix, garantie, aucune différence remboursée ; ni compte à rebours ni « plus que N ») et lecture interne (quotas) ; réservations **sans** identifiant client ; remboursements préparés et brouillons d'email |
| `POST /predrop/open` | `chef-de-projet`, `finance-pricing` | toutes les conditions du §2.11 (sinon 409 avec la liste) ; `market_ref_chf` : PROPRIO seule (rôle : 403) ; référence inconnue ou prix drop REVIEW : **en attente** de PROPRIO (aucune réservation) ; prix et paramètres figés |
| `POST /predrop/{predrop_id}/approve` | PROPRIO seul | validation d'un pré-drop en attente : conditions réévaluées, référence marché attestée (ou inconnue assumée) |
| `POST /predrop/{predrop_id}/close` | `chef-de-projet`, `finance-pricing`, `qa-conformite`, `n8n-03-factures` | acte protecteur ; unités non réservées au drop ; `n8n-03-factures` : dès l'annonce d'une réduction d'allocation, avant sa validation |
| `POST /predrop/{predrop_id}/publish` | `n8n-01-sync`, `site-integrations` | fiche jumelle « Réservation garantie » construite par le moteur (`publish.build_predrop_publication`) : fiche canonique et validations de la propriétaire, prix pré-drop **figé** (planchers revérifiés au coût rendu connu, ≥ prix drop et ≤ prix drop × 1,10 ; coût inconnu : non publiée), statut `prioritaire` / `ouvertes` / `fermees`, retrait (brouillon) au drop, à la fermeture, sur paramètres non signés, gel, stop-loss non évaluable ou quarantaine ; inventaire = réservations encore ouvertes diminuées des commandes Shopify non relevées (compare-and-swap ; baisse protectrice, appliquée même quand la mise à jour d'une fiche en ligne est refusée par le niveau ou le gel ; hausse : niveau 2) ; simulation par défaut (`dry_run: false` : porte de gouvernance, mise à jour niveau 2, création niveau 3) ; en attente de la propriétaire ou avant l'ouverture : 409 |
| `POST /predrop/reservations` | `n8n-02-commandes` | réservation **payée** (commande Shopify, `customer_ref` = sha256 de l'identifiant client, jamais l'email) ; idempotente par commande (autre contenu : 409) ; jamais refusée pour un motif métier : hors quota, limite par client, fenêtre prioritaire, montant ≠ prix pré-drop × quantité, pré-drop fermé à la date du paiement, désactivé, gel ou quarantaine => **non servie** et remboursement intégral préparé ; dette jusqu'à l'expédition |
| `POST /predrop/reservations/{order_id}/cancel` | `operations-sav` | annulation d'une réservation **confirmée** à la demande écrite du client (`reason` : `CUSTOMER_CANCELLATION` — annulation libre, refusée à partir de la date du drop —, `DATE_POSTPONED` — report au-delà du seuil des conditions —, `PRODUCT_CHANGED` — contenu modifié ; `request_ref` = référence de la demande) : remboursement **intégral** préparé, supplément compris, même circuit que les autres (validation de la propriétaire aux niveaux 1 et 2) ; l'unité revient au quota ; déjà remboursée : sans effet ; expédiée : 409 (retour volontaire) ; inconnue : 404 |
| `POST /predrop/refunds/{refund_id}/approve` | PROPRIO seul | validation en **un clic** (corps vide admis) d'un remboursement préparé (niveaux d'autonomie 1 et 2 ; à partir du niveau 3, approuvé par le moteur) |
| `POST /predrop/refunds/{refund_id}/executed` | `n8n-02-commandes` | remboursement PSP relevé : approuvé seulement (sinon 409) ; seule sortie de la dette d'une réservation remboursée ; même référence : idempotent |

Tout refus est journalisé (jamais le jeton). Écritures propres à chaque rôle : section « Écritures par rôle » de
`docs/08-agents/MATRICE_API.md` (générée) ; qui détient quel jeton (17 rôles émis : 10 connecteurs n8n, 7 agents ayant
accès à l'API) : `docs/08-agents/BRIEF_COMMUN.md` §10, tableau comparé à la matrice par `verifier_agents.py` ;
actes de la propriétaire : `docs/00-pilotage/INTERVENTIONS_HUMAINES.md` (B25, C18, C19, C23, C27, C30).

### 2.8 `pokeshop/treasury.py` + `pokeshop/forecast.py` (finance)
- Prévisionnel glissant **13 semaines** (solde, achats engagés, TVA, livraisons, remboursements, pub, versements PSP).
- Scénarios BP §10 (prudent/central/développement), seuil de rentabilité, sensibilité. Doit reproduire les chiffres du BP
  (53 / 933 / 2 467 CHF ; ≈31 commandes ; ≈181 commandes avec 2 000 CHF de rémunération ; 56 ; 93).

### 2.9 `pokeshop/incidents.py` + `pokeshop/audit.py` (integrations)
- Quarantaine d'une référence, suspension d'un workflow, notification (cause + action proposée), reprise ; journal append-only.
- Journaux d'état en ajout seul chaînés sha256 (stop-loss, photo, mandat, étoile polaire, incidents, prix) : table
  `engine_state_journal` si `POKESHOP_DATABASE_URL`, sinon fichiers JSON Lines dans `POKESHOP_STATE_DIR` ; relus au démarrage,
  un journal illisible démarre le service gelé (`RESTORE_FAILED`).

### 2.10 Gouvernance : `pokeshop/stoploss.py`, `pokeshop/mandate.py`, `pokeshop/northstar.py`, `pokeshop/autonomy.py`
- `stoploss.py` : six stop-loss, gel global verrouillé, réarmement et point zéro par la propriétaire seule ; seuils signés
  (`POKESHOP_STOPLOSS_FINGERPRINT`, sinon les plus stricts). Définition unique : `docs/00-pilotage/STOP_LOSS.md` §3.
- `mandate.py` : `check` de chaque dépense (mandat actif seulement si son empreinte est au coffre,
  `POKESHOP_MANDATE_FINGERPRINT`), registre `SpendLedger`, registres des taux de change et des révocations.
- `northstar.py` : registre de l'étoile polaire (contribution nette cumulée ; ventes d'une réservation pré-drop reconnues
  à l'expédition). `autonomy.py` : niveaux 1 à 4 et porte de gouvernance (niveau + mandat + stop-loss) devant toute
  écriture réelle. `predrop.py` : pré-drop (§2.11), paramètres signés (`POKESHOP_PREDROP_FINGERPRINT`, sinon désactivé).

### 2.11 `pokeshop/predrop.py` (gouvernance) — pré-drop
Décision de la propriétaire du 6.10.2026 : **réservation GARANTIE avant réception** du stock. Le supplément paie la
**garantie** d'être servi en premier et expédié dès réception, **pas le produit** ; **aucun remboursement de la
différence** si des unités restent au drop (textes `GUARANTEE_TEXT_FR` et `NO_DIFFERENCE_REFUND_FR`, repris sur chaque
offre publique).

- **Deux prix** par produit éligible : prix **DROP** = `decide_price` du moteur, inchangé (coût rendu du moteur :
  max(offre de moins de 24 h du fournisseur de l'allocation, CMP du stock), jamais déclaré) ; prix **PRÉ-DROP** =
  prix drop × (1 + `premium_pct`), arrondi retail **vers le haut** sur la grille des règles, puis marge **revérifiée**
  (planchers durs et marge cible). Plafonds du code : supplément configuré **et** effectif ≤ 10 % (au-delà après
  arrondi : plus grand point de grille ≤ drop × 1,10) ; prix pré-drop ≤ référence marché connue (sinon plus grand point
  de grille ≤ référence ; prix drop au-dessus du marché : pas de pré-drop) ; référence inconnue ou prix drop REVIEW :
  validation de la propriétaire.
- **Paramètres signés** `config/predrop.v1.yaml` (même mécanisme d'empreinte que les seuils du stop-loss :
  `python -m pokeshop.predrop fingerprint`, `POKESHOP_PREDROP_FINGERPRINT` au coffre) : `premium_pct` 0.08 (borne 0..0.10),
  `predrop_share_of_allocation` 0.5, réserve de sécurité ≥ 1 unité et ≥ 10 % de l'allocation, `per_customer_limit` 1
  (2 au plus), `priority_window_hours` 24, `demand_threshold` 0.5. Sans empreinte, empreinte différente ou valeur hors
  bornes : pré-drop **désactivé** (fermé par défaut ; `/health` : `signatures.predrop`).
- **Éligibilité** (toutes requises, `evaluate_eligibility`) : paramètres signés ; un seul pré-drop en cours par
  référence ; allocation **ferme** enregistrée (`POST /predrop/allocations`, propriétaire ou workflow 03, jamais
  l'agent bénéficiaire) ; quota pré-drop ≥ 1 = allocation ferme − réservations engagées − réserve
  (`stock.preorder_quota`) ; score de demande = inscrits consentants intéressés (compte **agrégé** de moins de 7 jours,
  `POST /predrop/demand`, aucune donnée personnelle) / allocation ≥ seuil ; fiche validée par la propriétaire (contenu
  en vigueur, `POST /catalog/approvals`) ; coût connu ; prix drop sans blocage ni passage sous les planchers ; marge
  pré-drop revérifiée ; prix pré-drop ≤ référence marché ; stop-loss évalué sans gel ni blocage de la référence
  (état inconnu : refus) ; aucune quarantaine.
- **Quotas** (`split_quota`) : vendable = allocation − réserve ; part pré-drop = ⌊part × vendable⌋ ; le reste au drop
  (les unités non réservées d'un pré-drop fermé reviennent au drop). Un verrou unique : deux paiements simultanés sur
  la dernière unité n'en confirment jamais qu'un.
- **Réservations payées** (`PredropRegistry`, journal d'état `predrop`, ajout seul, relu au démarrage ; illisible :
  service gelé) : idempotentes par commande ; limite par client sur l'identifiant client **haché** fourni par la
  boutique ; fenêtre prioritaire des inscrits aux alertes (accès attesté par la boutique) ; une commande payée n'est
  jamais perdue : non servie => remboursement intégral préparé.
- **Réduction d'allocation** (`plan_service`) : pré-drop servi en premier (ordre de paiement strict), quota drop réduit
  d'abord, puis remboursement intégral des **dernières** réservations + brouillon d'email (sans donnée personnelle ;
  `{{NOM_BOUTIQUE}}`). Exécution selon le niveau d'autonomie : niveaux 1 et 2, validation de la propriétaire en un
  clic ; à partir du niveau 3, approuvé par le moteur ; le remboursement PSP est relevé par le workflow 02 (le moteur
  n'écrit jamais vers un service tiers).
- **Dette jusqu'à livraison** : `outstanding_debt` (payé à la date de la photo, ni expédié — commande enregistrée par
  `POST /orders/shipped` — ni remboursé) entre dans les dettes de la photo du stop-loss et est déduit du cash
  disponible ; `preorders_collected_chf` déclaré ne compte que les précommandes **hors** pré-drop. **Étoile polaire** :
  chiffre d'affaires reconnu **à l'expédition** (`ShippedOrder.recognized_at`, posée par le moteur), jamais à
  l'encaissement ; aucune écriture de l'étoile polaire n'est dérivée d'une réservation.
- **Boutique** (étape 2, `publish.py`, `sync.py`, workflow 01) : **fiche jumelle** « Réservation garantie — <titre> » (type « Réservation garantie », SKU `<SKU>-RESA-<AAAAMMJJ>`, handle `<handle>-reservation-garantie`, une variante, `DENY`) : prix pré-drop figé, inventaire = réservations ouvertes (jamais écrit en texte), métachamps publics `boutique.date_drop`, `boutique.reservation_statut` (`prioritaire` · `ouvertes` · `fermees`), `boutique.fiche_liee`, étiquette `reservation-garantie` tant que les réservations sont ouvertes ; **retirée au drop**. La fiche normale garde sa structure (une variante, même SKU : `productSet` a une sémantique « ensemble », une variante ajoutée puis retirée recréerait la sienne le jour de la réception) et ne reçoit que les trois métachamps d'information. Snippets `da-badges` (« Réservation garantie », « Drop le JJ.MM »), `da-statut-stock`, `da-reservation-garantie` (encart : deux prix natifs, garantie, aucune différence remboursée), `da-reservation-acces` (bouton pendant la fenêtre prioritaire : client connecté, étiquette `alerte-produit:<handle>` et consentement confirmé, comme l'attestation du workflow 02). n8n : réservations payées et remboursements approuvés (02), allocation ferme et réduction validées par la propriétaire, fermeture protectrice (03), demande agrégée et annonces (06).
- **Aucune fausse urgence** : offre publique en liste blanche (`PUBLIC_OFFER_FIELDS`) : statut « Réservations ouvertes
  / fermées », date du drop, deux prix, limite par client, accès prioritaire, garantie ; ni compte à rebours, ni heure
  de fermeture, ni « plus que N », ni coût, ni marge.
- **Annulation à la demande du client** (étape 3, `cancel_reservation`, `POST /predrop/reservations/{order_id}/cancel`,
  agent 11) : sur demande écrite, motif `CUSTOMER_CANCELLATION` (refusé à partir de la date du drop), `DATE_POSTPONED`
  ou `PRODUCT_CHANGED` et référence de la demande : remboursement **intégral**, supplément compris, préparé dans le même
  circuit (validation de la propriétaire aux niveaux 1 et 2) ; l'unité revient au quota ; déjà remboursée : sans effet ;
  expédiée : refus. Chaque remboursement préparé porte son motif en français (`reason_fr`, sans terme interne : variable
  de l'email 18).
- **Légal, contenus, pilotage** (étape 3) : conditions client **brouillon** (`docs/04-legal/PRECOMMANDES.md` partie
  « Pré-drop » et §2.5, CGV ch. 7.7 à 7.12, FAQ, notes P1 à P10 pour le juriste ; champs `LIMITE_RESERVATION_PREDROP` et
  `FENETRE_PRIORITAIRE_PREDROP` alignés sur les paramètres signés, contrôle `check_predrop_alignment`) ; emails 15 à 19
  (`docs/06-contenu/EMAILS`) et plan du jour de drop (`docs/06-contenu/PLAN_JOUR_DE_DROP.md`), garantie du moteur mot pour
  mot (contrôlée) ; actes de la propriétaire C32 à C34 ; qui fait quoi : `docs/08-agents/PRE_DROP.md` ; risques RS-17 à
  RS-19 (`docs/00-pilotage/REVUE_SECURITE.md`).

## 3. Base de données (agent `data-pipeline` écrit `db/migrations/`)
Tables minimum : `suppliers`, `supplier_contacts`, `raw_snapshots`, `supplier_offers`, `products`, `product_supplier_links`,
`fx_rates`, `cost_lots` (coût historique par réception), `replacement_costs`, `pricing_rules` (versionnées),
`price_decisions`, `stock_movements`, `reservations`, `preorder_allocations`, `purchase_proposals`, `orders`, `order_lines`,
`incidents`, `audit_log` (append-only), `idempotency_keys`, `autonomy_levels`, `engine_state_journal` (journaux d'état du
moteur, ajout seul chaîné), `owner_token_fingerprint` (empreinte du jeton de la propriétaire, écrite par `pokeshop_owner`).
L'API se connecte avec un compte membre de `pokeshop_engine`, jamais en superutilisateur.
Colonnes de coût jamais exposées par une vue publique ; prévoir une vue `public_catalog` sans coûts.

## 4. Arborescence des livrables non-code
```
docs/00-pilotage/     backlog, plan 90 jours, gates go/no-go, INTERVENTIONS_HUMAINES.md, ECARTS_BP.md
docs/01-marche/       grille concurrence, guide d'entretiens, questionnaire, protocole landing
docs/02-sourcing/     dossier B2B, emails fournisseurs, panier pilote, demande technique, tracker CSV
docs/03-finance/      modèle financier .xlsx, trésorerie 13 semaines .xlsx, note de vérification
docs/04-legal/        CGV, livraison/retours, confidentialité, mentions légales, précommandes (dont le pré-drop) — BROUILLONS à faire revoir
docs/05-da/           naming, 2 directions, logo SVG, mini-charte HTML, composants, templates sociaux, packaging
docs/06-contenu/      15 sujets, calendrier 90 j, emails transactionnels/automations (dont 15 à 19 du pré-drop), plan du jour de drop, scripts vidéo, ton
docs/07-ops/          SOP réception, préparation colis, SAV, retours, incidents, dashboard
docs/08-agents/       12 briefs de mission + brief commun + qui fait quoi pour un pré-drop (PRE_DROP.md)
.claude/agents/       les 12 agents exécutables en sous-agents Claude Code
.claude/settings.json permissions du projet : règles deny seulement (secrets illisibles par la flotte)
site/landing/         page de présentation + inscription alertes (statique, sans faux stock)
orchestration/n8n/    8 workflows : les 4 du BP §12, digest, marketing, surveillance du stop-loss, contrôle des dépenses
dashboard/            tableau de bord interne (lecture seule)
```

## 5. Conventions
- Toute hypothèse chiffrée porte la mention « hypothèse » + source BP (§).
- Chaque document se termine par une section **« Validation humaine requise »** listant ce qu'une personne doit décider.
- Pas de nom de boutique définitif : utiliser le placeholder `{{NOM_BOUTIQUE}}` tant que le naming n'est pas validé.
- Dates : référence du BP = 4 octobre 2026.
