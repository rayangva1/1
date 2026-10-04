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

## 1. Stack

- Python 3.11, package `pokeshop` dans `engine/pokeshop/`, tests `pytest` dans `tests/`.
- Dépendances autorisées : stdlib, `pydantic>=2`, `fastapi`, `uvicorn`, `httpx`, `openpyxl`, `pyyaml`, `jinja2`.
  Rien d'autre sans justification dans le README du module.
- Base : PostgreSQL 16 (compatible Supabase). Migrations SQL brutes dans `db/migrations/NNN_nom.sql`.
- Orchestrateur : n8n (exports JSON dans `orchestration/n8n/`), qui appelle l'API HTTP du moteur.
- Boutique : Shopify (Admin GraphQL API, `productSet`, `inventorySetQuantities`). Client avec transport mockable.
- `docker-compose.yml` à la racine : postgres + n8n + api moteur (pour plus tard ; pas lancé ici).
- Lancer les tests : `cd /home/user/1 && python -m pytest -q` (le `conftest.py` racine ajoute `engine/` au path).

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
- `normalize_language(raw) -> "FR"|"EN"|"JP"|"DE"|"IT"|"UNKNOWN"`, `normalize_format(raw)` (display, etb, bundle, tripack, coffret, booster, accessoire…),
  `validate_gtin(code) -> bool` (checksum GS1), `match_offer_to_product(...)` ⇒ identité ambiguë = brouillon.

### 2.5 `pokeshop/importers/` (data-pipeline)
- `base.py` : interface `SupplierConnector.fetch() -> RawSnapshot` (contenu brut + horodatage + source), `parse(snapshot) -> list[SupplierOffer]`.
- `csv_importer.py`, `xlsx_importer.py`, `xml_importer.py` pilotés par un **dictionnaire de champs** YAML par fournisseur
  (`data/supplier_mappings/<fournisseur>.yaml`).
- Validations : devise, HT/TTC, unité vs carton, paliers de remise, prix 0, prix ×10 vs dernier import, doublons, import incomplet ⇒ **quarantaine**.
- Jeux d'essai FICTIFS dans `data/samples/`.

### 2.6 `pokeshop/shopify_client.py` + `pokeshop/publish.py` (integrations)
- Client GraphQL Admin avec transport injectable (mock en test), `dry_run=True` par défaut, clés d'idempotence,
  journal des écritures, retry/backoff, respect du `compareQuantity`/contrôle de concurrence pour l'inventaire.
- `publish.py` : construit les payloads `productSet` à partir du catalogue validé — **filtre strict des champs publics**
  (test qui échoue si un champ coût/marge/fournisseur fuit).

### 2.7 `pokeshop/api.py` (integrations)
FastAPI : `/health`, `/pricing/quote`, `/pricing/basket`, `/stock/sellable`, `/stock/reorder-proposal`,
`/imports/{supplier}/run` (dry-run), `/publish/preview`, `/incidents`. Appelé par n8n.

### 2.8 `pokeshop/treasury.py` + `pokeshop/forecast.py` (finance)
- Prévisionnel glissant **13 semaines** (solde, achats engagés, TVA, livraisons, remboursements, pub, versements PSP).
- Scénarios BP §10 (prudent/central/développement), seuil de rentabilité, sensibilité. Doit reproduire les chiffres du BP
  (53 / 933 / 2 467 CHF ; ≈31 commandes ; ≈181 commandes avec 2 000 CHF de rémunération ; 56 ; 93).

### 2.9 `pokeshop/incidents.py` + `pokeshop/audit.py` (integrations)
- Quarantaine d'une référence, suspension d'un workflow, notification (cause + action proposée), reprise ; journal append-only.

## 3. Base de données (agent `data-pipeline` écrit `db/migrations/`)
Tables minimum : `suppliers`, `supplier_contacts`, `raw_snapshots`, `supplier_offers`, `products`, `product_supplier_links`,
`fx_rates`, `cost_lots` (coût historique par réception), `replacement_costs`, `pricing_rules` (versionnées),
`price_decisions`, `stock_movements`, `reservations`, `preorder_allocations`, `purchase_proposals`, `orders`, `order_lines`,
`incidents`, `audit_log` (append-only), `idempotency_keys`, `autonomy_levels`.
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
site/landing/         page de présentation + inscription alertes (statique, sans faux stock)
orchestration/n8n/    4 workflows BP §12
dashboard/            tableau de bord interne (lecture seule)
```

## 5. Conventions
- Toute hypothèse chiffrée porte la mention « hypothèse » + source BP (§).
- Chaque document se termine par une section **« Validation humaine requise »** listant ce qu'une personne doit décider.
- Pas de nom de boutique définitif : utiliser le placeholder `{{NOM_BOUTIQUE}}` tant que le naming n'est pas validé.
- Dates : référence du BP = 4 octobre 2026.
