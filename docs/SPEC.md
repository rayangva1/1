# SPEC technique commune — Boutique Pokémon FR Suisse

> Contrat partagé par tous les agents de build. Source de vérité métier :
> `docs/business-plan/business_plan_extrait.txt` (texte du BP du 4 octobre 2026).
> En cas de conflit, le BP gagne ; signaler l'écart dans `docs/00-pilotage/ECARTS_BP.md`.

## 0. Principes non négociables (tirés du BP)

1. Calcul financier **déterministe, vérifiable, versionné**. `decimal.Decimal` partout, jamais `float`.
   L'IA extrait/rédige, elle ne décide jamais d'une TVA, d'un taux de change ou d'un montant.
2. **Aucun coût interne, prix B2B, marge ou donnée personnelle** dans le HTML public, les payloads
   Shopify publics, les prompts marketing ou les visuels.
3. **Aucun faux stock**. Stock fournisseur ≠ stock boutique. Pas de précommande sans allocation ferme.
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
| `GET /pricing/approvals`, `GET /catalog`, `GET /catalog/approvals`, `GET /sync/history`, `GET /incidents`, `GET /autonomy`, `GET /stoploss/status`, `GET /capital/movements`, `GET /northstar` | COMMUN (lecture) | `consecutive_clean_runs` : cycles réels distincts ; `GET /northstar` : `incomplete` et `derivation_errors` quand une écriture dérivée d'une commande est impossible, `cost_of_sales_pending` quand le coût des ventes d'une commande attend l'inscription du coût de réception (gates : critère ROUGE) ; journal illisible : 503 |
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
| `POST /stoploss/state/refresh` | `n8n-07-stoploss` | photo construite par le moteur, datée par le plus ancien relevé de cash ; source manquante ou périmée (soldes, apports, déclaration des dettes de plus de 24 h) : 409 nommant la source ; dettes = déclarées + factures enregistrées non payées ; créances : relevé PROPRIO seulement ; `sources.complete` / `sources.incomplete` (coût des ventes en attente) ; publicité = MAX(déclaration, paiements pub **engagés** — approuvés ou exécutés — du mandat) |
| `POST /stoploss/state` | PROPRIO seul | photo déposée (relevé de la propriétaire) : cash ≠ relevés du connecteur de trésorerie : 409 ; `capital_movements` du corps : 422 |
| `POST /stoploss/freeze` | tous les rôles nommés | acte protecteur |
| `POST /stoploss/rearm` | PROPRIO seul | `reference_chf` attestée (C18) |
| `POST /stoploss/baseline` | PROPRIO seul | `with_photo:true` : premier point zéro posé atomiquement avec la première photo (C19) ; sinon photo acceptée requise |
| `POST /stoploss/capital-memory/reset` | PROPRIO seul | C23 |
| `POST /mandate/check` | `chef-de-projet`, `sourcing`, `direction-artistique`, `site-integrations`, `communication`, `acquisition`, `operations-sav`, `n8n-08-mandat` (PROPRIO **non** ; `finance-pricing` **non** : il paie, revue R5 R4-DOC-11) | `requested_by` = nom du jeton ; relais `n8n-08-mandat` : `requested_by` parmi les agents qui dépensent (sinon 403), trésorerie non vérifiée ; tout poste du stop-loss non attesté par son rôle, ou étoile polaire incomplète (coût des ventes en attente) : `TREASURY_UNVERIFIED` ; dépense pub sans relevé de `connecteur-publicite` de moins de 24 h : `TREASURY_UNVERIFIED` |
| `POST /mandate/human-decision` | PROPRIO seul | `APPROVE` / `REFUSE` d'une dépense `PENDING_HUMAN` (24 h, sinon expirée : 409) : seule voie de `HUMAN_APPROVED`, comptée au stop-loss pub à sa date (revue R5, R4-DOC-03) |
| `POST /mandate/revoke` | tous les rôles nommés | acte protecteur |
| `POST /treasury/paypal-balance`, `POST /treasury/bank-balance` | `connecteur-tresorerie` | connecteurs en lecture seule (B26) |
| `POST /treasury/balance-items` | `finance-pricing`, `connecteur-tresorerie` | deux registres **séparés et persistés** (revue R5) : dettes (`preorders_collected_chf` + `debts`, âge accepté 24 h) et créances (`receivables` : PROPRIO seule, rôle : 403 ; jamais effacées par une déclaration de dettes) ; `finance-pricing` ne baisse jamais dettes ni précommandes (403), même après un redémarrage |
| `POST /capital/movements` | PROPRIO seul | seule source des apports et retraits (B25) |
| `POST /ads/activity` | `connecteur-publicite` (jamais `acquisition`) | registre en ajout seul (baisse : 409) ; commandes attribuées : existantes au registre des commandes — sinon écartées seules (`attributed_orders_set_aside`), les dépenses du lot sont enregistrées (revue R5, R4-NEW-01) |
| `POST /fx/rates` | PROPRIO seul | seule source des taux (C23) |
| `POST /orders/shipped` | `n8n-02-commandes` | coût transporteur réel > 0 et référence d'étiquette ; **lignes** (SKU × quantité) obligatoires, SKU du catalogue validé (inconnu : 409) ; écrit ventes, frais (complément des frais externes de la commande), logistique, et la sortie au CMP (coût des ventes) ; conflit d'écriture dérivée : 409, rien d'écrit ; **jamais refusée faute de stock valorisé** (revue R5, R4-NEW-01) : coût des ventes **en attente** (`cost_of_sales_pending`), dérivé dès l'inscription du coût et au démarrage ; étoile polaire et photo incomplètes, dépenses en validation humaine d'ici là |
| `POST /orders/{order_id}/refunds` | `n8n-02-commandes`, `operations-sav` | avoir cumulé ≤ ventes de la commande enregistrée ; `lines` = unités retournées (≤ vendues − déjà retournées), vide pour un geste commercial (rien ne revient en stock au coût) |
| `POST /northstar/entries` | `n8n-02-commandes`, `finance-pricing` | rôle : montants positifs sur paiement, SAV, acquisition, frais fixes ; ventes, avoirs et montants négatifs (référencés) : PROPRIO ; identifiants `order:`, `refund:`, `cost:`, `expense:`, `fixed:` réservés au moteur (422) ; PAYMENT portant l'`order_id` d'une commande enregistrée : 422 |
| `POST /costs/movements` | `finance-pricing` | réception adossée à `POST /stock/receive` (autre jeton), une fois par réception, une fois par réception physique (SKU **à la réception**, bon), coût unitaire à ± 2 % de la ligne de facture enregistrée (référence prioritaire ; unités reçues au coût ≤ quantité facturée, fournisseur connu du moteur pour la référence — lien du catalogue ou offre rapprochée sur le catalogue du registre — : sinon 409 ; `return:` réservé aux retours) ou du coût rendu de l'offre évaluée avec des frais posés par PROPRIO — jamais des frais posés par `finance-pricing` (sinon, ou sans référence : PROPRIO) ; TVA d'import de la ligne comptée selon le profil TVA du moteur ; sortie de vente (ISSUE) : dérivée des commandes (rôle : 403) ; retour (RETURN) : commande enregistrée, avoir **à lignes** (unités retournées) d'un montant ≥ coût des unités retournées et retour physique `return:<avoir>` déclaré par un autre jeton (`operations-sav`), sinon 403 (coût des ventes encore en attente : 409) ; écart de facture > 2 % : PROPRIO |
| `POST /costs/invoices` | `n8n-03-factures` | facture validée par la propriétaire (workflow 03) : lignes au coût rendu ventilé sur clés canoniques (TVA d'import à part, `import_vat_unit_chf`) ; Σ quantité × coût des lignes ≤ montant dû (sinon 409) ; dette de la photo jusqu'au paiement ; idempotente (autre contenu : 409) |
| `POST /costs/invoices/{invoice_ref}/payments` | `connecteur-tresorerie` | paiement relevé (cumul ≤ montant) : seule baisse de la dette d'une facture |

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
- `northstar.py` : registre de l'étoile polaire (contribution nette cumulée). `autonomy.py` : niveaux 1 à 4 et porte de
  gouvernance (niveau + mandat + stop-loss) devant toute écriture réelle.

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
docs/04-legal/        CGV, livraison/retours, confidentialité, mentions légales, précommandes — BROUILLONS à faire revoir
docs/05-da/           naming, 2 directions, logo SVG, mini-charte HTML, composants, templates sociaux, packaging
docs/06-contenu/      15 sujets, calendrier 90 j, emails transactionnels/automations, scripts vidéo, ton
docs/07-ops/          SOP réception, préparation colis, SAV, retours, incidents, dashboard
docs/08-agents/       12 briefs de mission + brief commun
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
