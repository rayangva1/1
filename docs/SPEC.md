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
    illisibles (aucune règle `allow`). Seules des empreintes sha256 des jetons sont configurées.

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

Jetons (empreintes sha256 seulement dans l'environnement ; acteur journalisé **déduit du jeton**, jamais déclaré) :
- **API** = en-tête `X-Pokeshop-Token` : jeton **commun** (`POKESHOP_API_TOKEN_SHA256`, acteur « api », attribuable
  à personne) ou jeton **nommé** (`POKESHOP_AGENT_TOKENS_SHA256`, `nom:empreinte`, acteur = nom du jeton). Aucune
  empreinte configurée : 503 ; jeton absent ou faux : 401.
- **NOMMÉ** = jeton nommé obligatoire (valeur décisive) ; le jeton commun reçoit 403, journalisé.
- **PROPRIO** = en plus, `X-Pokeshop-Owner-Token` valide (`POKESHOP_OWNER_TOKEN_SHA256`), distinct du jeton d'API.
  Partout, un acteur « propriétaire » déclaré sans ce jeton est refusé (403, journalisé).

| Route | Jeton | Appelant (rôle) |
|---|---|---|
| `GET /health` | aucun (public, sans secret) | tous ; workflow 05 |
| `POST /pricing/quote`, `POST /pricing/basket` | API | agents 04, 05 |
| `POST /pricing/approvals` | API + PROPRIO (motif ≥ 10 caractères, `valid_hours` 1-168, 48 par défaut ; `floor_exception_ref` sous plancher) | propriétaire (C27) |
| `GET /pricing/approvals` | API | agents 04, 05, 12 |
| `POST /pricing/approvals/{approval_id}/revoke` | API (acte protecteur, tout jeton) | agent 12, propriétaire |
| `POST /stock/sellable` | API | agent 11 ; workflow 06 |
| `POST /stock/receive` | API (jeton nommé `agent-11-operations` recommandé) | agent 11 ; workflow 06 (passerelle `pokeshop-stock-recu`) |
| `POST /stock/reorder-proposal` | API ; `cap_exceptions` non vide : + PROPRIO | agent 11 ; exceptions de plafond : propriétaire (C18) |
| `POST /imports/{supplier}/run` | API (toujours en simulation) | agent 03 ; workflow 01 |
| `POST /publish/preview` | API (aperçu) | agents 04, 07 |
| `POST /catalog/items`, `POST /catalog/cost-inputs` | API (aucun champ `fx_*` : 422) | agent 04 (catalogue validé) ; agent 05 (frais) |
| `GET /catalog` | API | agents 04, 05, 07 |
| `POST /sync/run` | API ; simulation par défaut ; `dry_run:false` : porte de gouvernance + `POKESHOP_DRY_RUN=false` ; `cost_inputs` du corps sans `fx_*`, simulation seulement | workflow 01 ; agents 07, 12 |
| `GET /sync/history` | API (`consecutive_clean_runs` : cycles réels et distincts seulement) | agent 12 (gate 3.6) ; workflow 05 |
| `GET /incidents`, `POST /incidents` | API | workflows 01 à 04, 06, 08 ; agent 12 |
| `POST /incidents/{incident_id}/test` | API ; `passed:true` : PROPRIO, ou NOMMÉ différent de l'ouvreur avec `test_ref` = `run_id` d'un cycle PROPRE en simulation, postérieur à l'ouverture, sur la cible ; jeton commun ou ouvreur : 403 | agent 12 (`agent-12-qa`) ; propriétaire |
| `POST /incidents/{incident_id}/resume` | API ; incident critique : + PROPRIO | workflow 04 ; propriétaire (critique) |
| `POST /incidents/{incident_id}/close` | API | agent 12 ; workflow 04 |
| `GET /autonomy`, `POST /autonomy` | API ; hausse de niveau : + PROPRIO | tous (lecture, baisse) ; propriétaire (hausse) |
| `POST /stoploss/state` | NOMMÉ ; `capital_movements` non vide : 422 (apports lus au registre) | aucun workflow (07 utilise `/refresh`) |
| `POST /stoploss/state/refresh` | API (photo construite par le moteur à partir des registres) | workflow 07 (`n8n-07-stoploss`) |
| `GET /stoploss/status`, `POST /stoploss/freeze` | API (geler : acte protecteur) | tous ; workflows 05, 06, 07 ; agent 12 |
| `POST /stoploss/rearm` | API + PROPRIO (`reference_chf` attestée ; sans elle, 409 avec `rearm_reference`) | propriétaire (C18) |
| `POST /stoploss/baseline` | API + PROPRIO (photo acceptée requise, sinon 409) | propriétaire (C19) |
| `POST /stoploss/capital-memory/reset` | API + PROPRIO | propriétaire (C23) |
| `POST /mandate/check` | API ; jeton nommé : `requested_by` = nom du jeton ; jeton commun : `TREASURY_UNVERIFIED` | agents demandeurs (07, 10, 11) ; workflow 08 |
| `POST /mandate/revoke` | API (acte protecteur, tout jeton) | agent 12 ; propriétaire |
| `POST /treasury/paypal-balance`, `POST /treasury/bank-balance` | NOMMÉ | workflow 07 (`n8n-07-stoploss`, connecteurs en lecture seule, B26) |
| `POST /treasury/balance-items` | NOMMÉ | agent 05 (`agent-05-finance`), chaque jour |
| `POST /capital/movements` | API + PROPRIO (seule source des apports et retraits) | propriétaire (B25) |
| `GET /capital/movements` | API | agents 05, 12 |
| `POST /ads/activity` | API | connecteur publicitaire (agent 10) |
| `POST /fx/rates` | API + PROPRIO (seule source des taux) | propriétaire (C23) |
| `GET /northstar` | API (journal illisible : 503) | agent 05 ; workflow 05 |
| `POST /northstar/entries`, `POST /costs/movements` | API (coût historique déclaré : refusé) | agent 05 ; workflows 02, 03 |
| `GET /dashboard/daily`, `GET /dashboard/weekly`, `GET /dashboard/monthly` | API (journal non relu : KPI indisponibles, statut CRITIQUE) | tableau de bord (`dashboard/build.py`) ; workflow 05 |

Tout refus est journalisé (jamais le jeton). Répartition par agent et actes réservés : `docs/08-agents/BRIEF_COMMUN.md` §10 ;
actes de la propriétaire : `docs/00-pilotage/INTERVENTIONS_HUMAINES.md` (B25, C18, C19, C23, C27).

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
