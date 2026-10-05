-- fictif_seed.sql — jeu de données FICTIF pour essais (aucune donnée réelle).
--
-- Fournisseurs « fictif_* », extensions « FICTIF_* », GTIN de test 200… (SPEC §0.7),
-- prix, coûts, taux de change et commandes INVENTÉS. Toutes les lignes portent fictif = true :
-- jamais visibles dans storefront.public_catalog (migration 005) ; vue d'essai du moteur :
-- pokeshop.public_catalog_test. Les décisions de prix, la commande et la proposition référencent la
-- version RÉELLE des règles qui les a calculées (config/pricing_rules.v1.yaml, contenu complet et sha256) :
-- blocs « genere:* » produits par python db/seeds/regles_seed.py (vérifiés par tests/test_seed_fictif.py).
-- À appliquer après les migrations (et après reference_seed.sql si souhaité).

BEGIN;

-- ------------------------------------------------------------ référentiels
INSERT INTO pokeshop.suppliers (supplier_id, name, country, priority, status, access_mode, access_agreement_ref, mapping_version, source_ref, fictif) VALUES
    ('fictif_grossiste_a', 'FICTIF Grossiste A', 'FR', 1, 'ACCEPTE', 'FICHIER', NULL, 'fictif_grossiste_a-v1', 'FICTIF', true),
    ('fictif_grossiste_b', 'FICTIF Grossiste B', 'CH', 2, 'ACCEPTE', 'FICHIER', NULL, 'fictif_grossiste_b-v1', 'FICTIF', true),
    ('fictif_grossiste_c', 'FICTIF Grossiste C', 'FR', 1, 'ACCEPTE', 'API', 'FICTIF-accord-usage-0001', 'fictif_grossiste_c-v1', 'FICTIF', true),
    ('fictif_grossiste_d', 'FICTIF Grossiste D', 'FR', 3, 'EN_DISCUSSION', 'EMAIL_PDF', NULL, NULL, 'FICTIF', true);

INSERT INTO pokeshop.supplier_contacts (supplier_id, role, channel, value, is_personal_data, source_ref, collected_at, fictif) VALUES
    ('fictif_grossiste_a', 'service commercial (adresse générique)', 'EMAIL', 'commandes@grossiste-a.fictif.invalid', false, 'FICTIF', '2026-10-04', true),
    ('fictif_grossiste_c', 'support technique API (adresse générique)', 'EMAIL', 'api@grossiste-c.fictif.invalid', false, 'FICTIF', '2026-10-04', true);

INSERT INTO pokeshop.extensions (code, name_fr, fictif) VALUES
    ('FICTIF_ALPHA', 'Extension Fictive Alpha', true),
    ('FICTIF_BETA', 'Extension Fictive Bêta', true),
    ('FICTIF_GAMMA', 'Extension Fictive Gamma', true);

INSERT INTO pokeshop.fx_rates (currency, rate_to_chf, source, rate_date, fictif) VALUES
    ('EUR', 0.94000000, 'FICTIF (taux inventé pour essais, pas une cotation)', '2026-10-04', true),
    ('CHF', 1, 'CHF', '2026-10-04', true);

-- >>> genere:regles (python db/seeds/regles_seed.py — ne pas éditer à la main)
-- Règles appliquées par le moteur aux décisions FICTIVES ci-dessous : contenu COMPLET du fichier
-- config/pricing_rules.v1.yaml (JSON) et sha256 du fichier brut (même valeur que RuleSet.content_sha256).
INSERT INTO pokeshop.pricing_rules (rules_version, status, vat_mode, effective_date, content_sha256, content, source_path, fictif)
VALUES ('v1-2026-10-04', 'PROPOSITION', NULL, '2026-10-04', 'bf09f2fdafc95d069b54d179794f4dd3fbf31b07e9e1d221de82593b39553a3d',
        '{"effective_date":"2026-10-04","pricing":{"acquisition_cost":"5.00","after_sales_provision":"1.00","hard_floor_chf_per_order":"8.00","hard_floor_margin":"0.12","logistics_cost":"3.00","market_review_threshold":"0.10","max_daily_price_change":"0.05","payment_fixed":"0.30","payment_pct":"0.025","price_anomaly_factor":"10","rounding_tiers":[{"endings":["0.50","0.90"],"min_price":"0","step":"1.00"},{"endings":["0.90"],"min_price":"10","step":"1.00"},{"endings":["4.90","9.90"],"min_price":"100","step":"10.00"}],"small_product_max_cost":"15.00","small_product_max_shipping_ttc":null,"small_product_min_order_ttc":null,"target_margin":"0.20"},"profiles":{"EFFECTIVE":{"description":"Assujetti méthode effective : TVA suisse récupérable, ventes HT, t = 8,1 %","vat_rate_sales":"0.081"},"NOT_REGISTERED":{"description":"Non assujetti : TVA non récupérable dans C, t = 0 ; saisir L, R, A TTC","vat_rate_sales":"0"}},"rules_version":"v1-2026-10-04","source":"docs/business-plan/business_plan_extrait.txt §4 (formule, exemple) et §5 (table de règles)","status":"hypotheses BP §4-5, à confirmer par devis","stock":{"extension_budget_cap":"0.25","future_skew_minutes":5,"reorder_coverage_days":14,"staleness_hours":24,"stock_budget_chf":"3000"}}'::jsonb,
        'config/pricing_rules.v1.yaml', true);
-- <<< genere:regles

-- ---------------------------------------------------------------- import
WITH c AS (SELECT convert_to('sku;prix;devise' || chr(10) || 'FICTIF-A-001;95,00;EUR' || chr(10), 'UTF8') AS b)
INSERT INTO pokeshop.raw_snapshots (supplier_id, source_kind, source_uri, fetched_at, source_ts, checksum_sha256, byte_size,
                                    content, mapping_version, import_status, rows_read, accepted_count, quarantined_count, fictif)
SELECT 'fictif_grossiste_a', 'CSV', 'data/samples/FICTIF_offres_grossiste_a.csv', '2026-10-04 08:00+02', '2026-10-04 06:00+02',
       encode(sha256(b), 'hex'), octet_length(b), b, 'fictif_grossiste_a-v1', 'PARTIAL', 4, 3, 1, true
  FROM c;

INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, line_no, status, quarantine_reasons, supplier_sku, gtin, language,
    extension, format, content, sealed, units_per_pack, price, currency, price_includes_vat, vat_rate, tier_discounts, moq, carton_qty,
    availability_status, available_qty, ship_from_country, vat_country, source_ts, raw_ref, raw, fictif)
SELECT s.snapshot_id, 'fictif_grossiste_a', v.line_no, v.status, v.reasons, v.sku, v.gtin, v.lang::pokeshop.language_code,
       v.ext, v.fmt::pokeshop.product_format, v.content, true, 1, v.price, 'EUR', false, 0, v.tiers::jsonb, v.moq, v.carton,
       'IN_STOCK', v.qty, 'FR', 'FR', '2026-10-04 06:00+02', 'fictif_grossiste_a:seed#L' || v.line_no, '{"fictif":"true"}', true
  FROM pokeshop.raw_snapshots s,
       (VALUES
           (2, 'VALIDE', '{}'::text[], 'FICTIF-A-001', '2000000005010', 'FR', 'FICTIF_ALPHA', 'DISPLAY', '36 BOOSTERS', 95.0000::numeric,
            '[{"min_qty": 12, "price": "92.00"}]', 6, 6, 24),
           (3, 'VALIDE', '{}'::text[], 'FICTIF-A-002', '2000000005027', 'FR', 'FICTIF_ALPHA', 'ETB', '9 BOOSTERS', 38.5000::numeric, '[]', 10, 10, 40),
           (4, 'VALIDE', '{}'::text[], 'FICTIF-A-008', '2000000005034', 'NA', 'SANS_EXTENSION', 'SLEEVES', '65 PROTEGE CARTES', 4.2000::numeric, '[]', 20, 20, 200),
           (5, 'QUARANTAINE', '{NON_POSITIVE_PRICE}'::text[], 'FICTIF-A-014', NULL, 'FR', 'FICTIF_BETA', 'BUNDLE', '6 BOOSTERS', 0::numeric, '[]', 12, 12, 36)
       ) AS v(line_no, status, reasons, sku, gtin, lang, ext, fmt, content, price, tiers, moq, carton, qty)
 WHERE s.checksum_sha256 IS NOT NULL AND s.supplier_id = 'fictif_grossiste_a';

-- -------------------------------------------------------------- catalogue
INSERT INTO pokeshop.products (public_sku, gtin, language, extension, format, content, sealed, status, title_fr, description_fr,
                               image_urls, image_rights_ok, max_qty_per_order, release_date, release_date_confirmed, fictif) VALUES
    ('FICTIF-DSP-ALPHA', '2000000005010', 'FR', 'FICTIF_ALPHA', 'DISPLAY', '36 BOOSTERS', true, 'PUBLIE',
     'Display Extension Fictive Alpha – FR', 'FICTIF : display de 36 boosters.', '{https://exemple.invalid/fictif/display-alpha.jpg}', true, 2,
     '2026-07-17', true, true),
    ('FICTIF-ETB-ALPHA', '2000000005027', 'FR', 'FICTIF_ALPHA', 'ETB', '9 BOOSTERS', true, 'PUBLIE',
     'Coffret Dresseur d''Élite (ETB) Extension Fictive Alpha – FR', 'FICTIF : ETB 9 boosters.', '{https://exemple.invalid/fictif/etb-alpha.jpg}', true, 5,
     NULL, false, true),
    ('FICTIF-SLV-65', '2000000005034', 'NA', 'SANS_EXTENSION', 'SLEEVES', '65 PROTEGE CARTES', true, 'PUBLIE',
     'Protège-cartes', 'FICTIF : paquet de 65 protège-cartes.', '{https://exemple.invalid/fictif/sleeves.jpg}', true, 10, NULL, false, true),
    ('FICTIF-DSP-GAMMA', '2000000005041', 'FR', 'FICTIF_GAMMA', 'DISPLAY', '36 BOOSTERS', true, 'PUBLIE',
     'Display Extension Fictive Gamma – FR', 'FICTIF : précommande sur allocation ferme.', '{https://exemple.invalid/fictif/display-gamma.jpg}', true, 5,
     '2026-11-06', true, true),
    ('FICTIF-ETB-BETA', NULL, 'FR', 'FICTIF_BETA', 'ETB', '9 BOOSTERS', true, 'BROUILLON',
     NULL, NULL, '{}', false, 5, NULL, false, true),
    ('FICTIF-DSP-BETA', '2000000005065', 'UNKNOWN', 'FICTIF_BETA', 'DISPLAY', '36 BOOSTERS', true, 'BROUILLON',
     NULL, NULL, '{}', false, 5, NULL, false, true),
    ('FICTIF-TRI-BETA', '2000000005072', 'FR', 'FICTIF_BETA', 'TRIPACK', '3 BOOSTERS', true, 'PUBLIE',
     'Tripack Extension Fictive Bêta – FR', 'FICTIF : publié mais sans prix => absent de la vue.', '{}', true, 5, NULL, false, true),
    ('FICTIF-BND-BETA', '2000000005089', 'FR', 'FICTIF_BETA', 'BUNDLE', '6 BOOSTERS', true, 'A_VALIDER',
     'Bundle Extension Fictive Bêta – FR', 'FICTIF : en attente de validation => absent de la vue.', '{}', true, 5, NULL, false, true);

INSERT INTO pokeshop.product_supplier_links (product_id, supplier_id, supplier_sku, match_status, match_reasons, validated_by, validated_at)
SELECT p.product_id, v.supplier_id, v.sku, v.status, v.reasons, v.validated_by, v.validated_at
  FROM (VALUES
          ('FICTIF-DSP-ALPHA', 'fictif_grossiste_a', 'FICTIF-A-001', 'MATCHED', '{EXACT_IDENTITY}'::text[], NULL, NULL::timestamptz),
          ('FICTIF-ETB-ALPHA', 'fictif_grossiste_a', 'FICTIF-A-002', 'CONFIRMED_BY_HUMAN', '{EXACT_IDENTITY}'::text[], 'Personne FICTIVE', '2026-10-04 09:00+02'),
          ('FICTIF-SLV-65', 'fictif_grossiste_a', 'FICTIF-A-008', 'MATCHED', '{EXACT_IDENTITY}'::text[], NULL, NULL),
          ('FICTIF-ETB-BETA', 'fictif_grossiste_b', 'FICTIF-B-099', 'AMBIGUOUS', '{MISSING_GTIN,PARTIAL_IDENTITY_MATCH}'::text[], NULL, NULL)
       ) AS v(public_sku, supplier_id, sku, status, reasons, validated_by, validated_at)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku;

-- ------------------------------------------------------------ coûts et prix
INSERT INTO pokeshop.cost_lots (lot_id, product_id, supplier_id, received_at, qty, qty_remaining, unit_cost_chf, cost_basis, invoice_ref, fx_rate_id, fictif)
SELECT v.lot_id, p.product_id, 'fictif_grossiste_a', v.received_at, v.qty, v.remaining, v.unit_cost, v.basis, v.invoice_ref,
       (SELECT fx_rate_id FROM pokeshop.fx_rates WHERE currency = 'EUR' AND fictif), true
  FROM (VALUES
          ('FICTIF-LOT-0001', 'FICTIF-DSP-ALPHA', '2026-10-01 10:00+02'::timestamptz, 6, 4, 101.2345::numeric, 'ESTIMATE', NULL),
          ('FICTIF-LOT-0002', 'FICTIF-ETB-ALPHA', '2026-10-01 10:00+02'::timestamptz, 10, 10, 41.1000::numeric, 'INVOICE', 'FICTIF-FACT-0001'),
          ('FICTIF-LOT-0003', 'FICTIF-SLV-65', '2026-10-01 10:00+02'::timestamptz, 40, 40, 4.4800::numeric, 'ESTIMATE', NULL)
       ) AS v(lot_id, public_sku, received_at, qty, remaining, unit_cost, basis, invoice_ref)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku;

-- >>> genere:decisions (python db/seeds/regles_seed.py — ne pas éditer à la main)
INSERT INTO pokeshop.replacement_costs (product_id, supplier_id, offer_id, unit_cost_chf, source_ts, rules_version, fictif)
SELECT p.product_id, 'fictif_grossiste_a', o.offer_id, 99.8000, '2026-10-04 06:00+02', 'v1-2026-10-04', true
  FROM pokeshop.products p JOIN pokeshop.supplier_offers o ON o.supplier_sku = 'FICTIF-A-001'
 WHERE p.public_sku = 'FICTIF-DSP-ALPHA';

INSERT INTO pokeshop.price_decisions (product_id, rules_version, inputs_hash, status, reasons, landed_cost_chf, floor_price_chf,
    profitable_price_chf, recommended_price_chf, evaluated_price_chf, contribution_chf, contribution_pct, fictif)
SELECT p.product_id, 'v1-2026-10-04', v.h, v.status::pokeshop.decision_status, v.reasons, v.cost, v.floor, v.floor, v.reco, v.reco,
       v.contrib, v.pct, true
  FROM (VALUES
          -- pokeshop.pricing.decide_price(coût, règles v1-2026-10-04 profil EFFECTIVE, marché) : coûts et marché FICTIFS.
          -- FICTIF-DSP-ALPHA : coût rendu 101.2345, sans référence marché.
          ('FICTIF-DSP-ALPHA', '9b8f534b20c6591c8a2638fc2f393d7534d1aa3af3a06c47ee2a1a0eb8ba02cc', 'OK', '{}'::text[],
           101.2345::numeric, 154.58::numeric, 154.90::numeric, 28.89::numeric, 0.2016::numeric),
          -- FICTIF-ETB-ALPHA : coût rendu 41.1000, référence marché FICTIVE 63.90.
          ('FICTIF-ETB-ALPHA', '794425e1cb738cd4c199cde83713bd1e5787726e10c68f9b5e40d6276cb39a3c', 'REVIEW', '{ABOVE_MARKET}'::text[],
           41.1000::numeric, 70.48::numeric, 70.90::numeric, 13.42::numeric, 0.2046::numeric)
       ) AS v(public_sku, h, status, reasons, cost, floor, reco, contrib, pct)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku;
-- <<< genere:decisions

-- Historique des prix publics (append-only) : le dernier PUBLISHED/ROLLED_BACK est le prix affiché.
INSERT INTO pokeshop.price_events (product_id, kind, price_ttc_chf, decision_id, validated, actor, note, at, fictif)
SELECT p.product_id, v.kind::pokeshop.price_event_kind, v.price, d.decision_id, v.validated, v.actor, v.note, v.at, true
  FROM (VALUES
          ('FICTIF-DSP-ALPHA', 'PUBLISHED', 154.90::numeric, true, false, 'engine', 'FICTIF : prix recommandé par le moteur', '2026-10-04 09:00+02'::timestamptz),
          ('FICTIF-DSP-ALPHA', 'PUBLISHED', 164.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF : essai de hausse validé', '2026-10-04 10:00+02'::timestamptz),
          ('FICTIF-DSP-ALPHA', 'ROLLED_BACK', 154.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF : retour au dernier prix validé', '2026-10-04 11:00+02'::timestamptz),
          ('FICTIF-ETB-ALPHA', 'PUBLISHED', 69.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF : REVIEW (marché) tranché à 69.90, contribution 19,35 %', '2026-10-04 09:00+02'::timestamptz),
          ('FICTIF-SLV-65', 'PUBLISHED', 7.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF', '2026-10-04 09:00+02'::timestamptz),
          ('FICTIF-DSP-GAMMA', 'PUBLISHED', 154.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF : précommande', '2026-10-04 09:00+02'::timestamptz),
          ('FICTIF-BND-BETA', 'PUBLISHED', 34.90::numeric, false, true, 'Personne FICTIVE', 'FICTIF : produit non publié', '2026-10-04 09:00+02'::timestamptz)
       ) AS v(public_sku, kind, price, use_decision, validated, actor, note, at)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku
  LEFT JOIN pokeshop.price_decisions d ON d.product_id = p.product_id AND v.use_decision
 ORDER BY v.at, v.public_sku;  -- event_id = ordre d'ajout : le dernier événement fait foi

-- ------------------------------------------------------------------- stock
INSERT INTO pokeshop.stock_levels (product_id, on_hand, reserved, damaged, safety)
SELECT p.product_id, v.on_hand, v.reserved, v.damaged, v.safety
  FROM (VALUES ('FICTIF-DSP-ALPHA', 4, 1, 0, 0), ('FICTIF-ETB-ALPHA', 10, 0, 1, 1), ('FICTIF-SLV-65', 40, 0, 0, 0),
               ('FICTIF-DSP-GAMMA', 0, 0, 0, 0)) AS v(public_sku, on_hand, reserved, damaged, safety)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku;

INSERT INTO pokeshop.stock_movements (product_id, kind, qty, ref, at, version_after, idempotency_key, fictif)
SELECT p.product_id, v.kind::pokeshop.movement_kind, v.qty, v.ref, v.at, v.version_after, v.idem, true
  FROM (VALUES
          ('FICTIF-DSP-ALPHA', 'RECEIPT', 6, 'FICTIF-LOT-0001', '2026-10-01 10:00+02'::timestamptz, 1, 'FICTIF-mvt-0001'),
          ('FICTIF-DSP-ALPHA', 'RESERVE', 1, 'FICTIF-#1000', '2026-10-02 10:00+02'::timestamptz, 2, 'FICTIF-mvt-0002'),
          ('FICTIF-DSP-ALPHA', 'FULFILL', 1, 'FICTIF-#1000', '2026-10-02 15:00+02'::timestamptz, 3, 'FICTIF-mvt-0003'),
          ('FICTIF-DSP-ALPHA', 'RESERVE', 1, 'FICTIF-#1001', '2026-10-04 12:00+02'::timestamptz, 4, 'FICTIF-mvt-0004'),
          ('FICTIF-ETB-ALPHA', 'RECEIPT', 10, 'FICTIF-LOT-0002', '2026-10-01 10:00+02'::timestamptz, 1, 'FICTIF-mvt-0005'),
          ('FICTIF-ETB-ALPHA', 'MARK_DAMAGED', 1, 'FICTIF-controle-reception', '2026-10-01 11:00+02'::timestamptz, 2, 'FICTIF-mvt-0006')
       ) AS v(public_sku, kind, qty, ref, at, version_after, idem)
  JOIN pokeshop.products p ON p.public_sku = v.public_sku
 ORDER BY v.at, v.idem;

INSERT INTO pokeshop.preorder_allocations (product_id, supplier_id, firm_allocation_qty, committed_preorders, safety,
                                           confirmed_in_writing, evidence_ref, confirmed_at, expected_date, fictif)
SELECT p.product_id, 'fictif_grossiste_c', 12, 3, 1, true, 'FICTIF-email-allocation-0001', '2026-10-03 16:00+02', '2026-11-06', true
  FROM pokeshop.products p WHERE p.public_sku = 'FICTIF-DSP-GAMMA';

-- --------------------------------------------------------------- commandes
-- >>> genere:commande (python db/seeds/regles_seed.py — ne pas éditer à la main)
INSERT INTO pokeshop.orders (shop_order_ref, status, paid_at, goods_ttc_chf, discount_ttc_chf, shipping_charged_ttc_chf,
                             total_paid_ttc_chf, customer_ref, contribution_chf, rules_version, inputs_hash, fictif) VALUES
    -- pokeshop.pricing.basket_contribution (règles v1-2026-10-04, port facturé 7.00, coût FICTIF).
    ('FICTIF-#1001', 'PAYEE', '2026-10-04 12:00+02', 154.90, 0, 7.00, 161.90, 'FICTIF-client-0001', 28.71, 'v1-2026-10-04',
     'bcc833633765709a2227eab32c13274501b1aa06dcd69e17606175add714d40f', true);
-- <<< genere:commande

INSERT INTO pokeshop.order_lines (order_id, product_id, qty, unit_price_ttc_chf, unit_cost_chf)
SELECT o.order_id, p.product_id, 1, 154.90, 101.2345
  FROM pokeshop.orders o, pokeshop.products p
 WHERE o.shop_order_ref = 'FICTIF-#1001' AND p.public_sku = 'FICTIF-DSP-ALPHA';

INSERT INTO pokeshop.reservations (reservation_id, product_id, order_id, qty, status)
SELECT 'FICTIF-RES-0001', p.product_id, o.order_id, 1, 'ACTIVE'
  FROM pokeshop.orders o, pokeshop.products p
 WHERE o.shop_order_ref = 'FICTIF-#1001' AND p.public_sku = 'FICTIF-DSP-ALPHA';

-- ------------------------------------------------------------------ achats
-- >>> genere:proposition (python db/seeds/regles_seed.py — ne pas éditer à la main)
INSERT INTO pokeshop.purchase_proposals (generated_at, status, supplier_id, total_cost_chf, budget_available_chf, budget_remaining_chf,
                                         rules_version, inputs_hash, skipped, fictif)
-- inputs_hash : identifiant FICTIF de la proposition (candidats d'essai non conservés).
VALUES ('2026-10-04 07:00+02', 'PROPOSITION_A_VALIDER', 'fictif_grossiste_a', 607.41, 2400.00, 1792.59, 'v1-2026-10-04',
        '4768b8ca1ca1b7322c1eeffa45acce7668922227efb5764b17c807a95add8a91',
        '[{"product_key": "FICTIF-ETB-BETA", "reason": "IDENTITY_INCOMPLETE"}]', true);
-- <<< genere:proposition

INSERT INTO pokeshop.purchase_proposal_lines (proposal_id, product_id, supplier_id, supplier_sku, extension, qty, unit_cost_chf, line_cost_chf, position, notes)
SELECT pp.proposal_id, p.product_id, 'fictif_grossiste_a', 'FICTIF-A-001', 'FICTIF_ALPHA', 6, 101.2345, 607.41, 1, '{FICTIF}'
  FROM pokeshop.purchase_proposals pp, pokeshop.products p
 WHERE pp.fictif AND p.public_sku = 'FICTIF-DSP-ALPHA';

-- ---------------------------------------------------------------- pilotage
INSERT INTO pokeshop.incidents (kind, severity, scope, escalation_level, supplier_id, snapshot_id, workflow, cause, proposed_action, details, fictif)
SELECT 'IMPORT_QUARANTAINE', 'MAJEUR', 'SOURCE', 'E1', 'fictif_grossiste_a', s.snapshot_id, 'import_fournisseur',
       'FICTIF : 1 ligne en quarantaine (prix nul)', 'Demander la correction au fournisseur (MOD-02) puis relancer l''import en simulation',
       '{"reasons": {"NON_POSITIVE_PRICE": 1}}', true
  FROM pokeshop.raw_snapshots s WHERE s.supplier_id = 'fictif_grossiste_a';

INSERT INTO pokeshop.autonomy_levels (scope, level, changed_by, changed_by_role, reason)
VALUES ('global', 1, 'systeme', 'SYSTEME', 'FICTIF : démarrage au niveau 1 (simulation et brouillons, BP §13)');

INSERT INTO pokeshop.idempotency_keys (scope, idempotency_key, request_sha256, status, response, completed_at, expires_at)
VALUES ('stock.reserve', 'FICTIF-#1001:FICTIF-DSP-ALPHA', 'a2427ace19626fc2104fc6ecb9d7791843e1080692be272cc97efd2b6c9ae872',
        'TERMINE', '{"reservation_id": "FICTIF-RES-0001"}', '2026-10-04 12:00+02', '2026-11-04 12:00+02');

INSERT INTO pokeshop.audit_log (actor, actor_kind, action, entity, entity_id, dry_run, autonomy_level, payload, idempotency_key) VALUES
    ('agent-donnees-fournisseurs', 'AGENT', 'import.run', 'raw_snapshots', 'fictif_grossiste_a', true, 1, '{"status": "PARTIAL", "fictif": true}', NULL),
    ('engine', 'SYSTEME', 'price.publish', 'products', 'FICTIF-DSP-ALPHA', true, 1, '{"price_ttc_chf": "154.90", "fictif": true}', NULL),
    ('engine', 'SYSTEME', 'stock.reserve', 'reservations', 'FICTIF-RES-0001', true, 1, '{"qty": 1, "fictif": true}', 'FICTIF-#1001:FICTIF-DSP-ALPHA');

COMMIT;
