-- 003_public_catalog.sql — vue publique du catalogue et droits d'accès.
--
-- storefront.public_catalog : SEULEMENT les champs publics (BP §6 « Publication » ; SPEC §0.2) :
-- aucune colonne de coût, de prix B2B, de marge, de contribution, de fournisseur ni de
-- donnée personnelle. Le stock fournisseur n'y entre jamais : disponibilité = stock LOCAL
-- vendable, ou précommande sur allocation ferme écrite (SPEC §0.3).
--
-- Rôles : storefront_reader ne voit QUE cette vue ; pokeshop_engine lit/écrit le schéma
-- interne sans pouvoir réécrire les journaux ; pokeshop_owner = la propriétaire.

BEGIN;

CREATE SCHEMA storefront;
COMMENT ON SCHEMA storefront IS 'Vues publiques sans coût ni fournisseur. Seul schéma exposable à la boutique.';

-- La vue s'exécute avec les droits de son propriétaire (comportement par défaut, pas de
-- security_invoker) : c'est ce qui permet à storefront_reader de la lire SANS aucun droit
-- sur les tables internes. security_barrier empêche de faire fuiter des lignes filtrées.
CREATE VIEW storefront.public_catalog WITH (security_barrier = true) AS
WITH latest_price AS (
    SELECT DISTINCT ON (e.product_id) e.product_id, e.price_ttc_chf, e.at
      FROM pokeshop.price_events e
     WHERE e.kind IN ('PUBLISHED', 'ROLLED_BACK') AND e.price_ttc_chf IS NOT NULL
     ORDER BY e.product_id, e.event_id DESC
),
preorder AS (
    SELECT a.product_id, sum(GREATEST(0, a.firm_allocation_qty - a.committed_preorders - a.safety))::integer AS quota
      FROM pokeshop.preorder_allocations a
     WHERE a.confirmed_in_writing AND a.status = 'OUVERTE'
     GROUP BY a.product_id
),
availability AS (
    SELECT p.product_id,
           GREATEST(0, coalesce(s.on_hand - s.reserved - s.damaged - s.safety, 0)) AS sellable,
           coalesce(po.quota, 0) AS quota
      FROM pokeshop.products p
      LEFT JOIN pokeshop.stock_levels s ON s.product_id = p.product_id
      LEFT JOIN preorder po ON po.product_id = p.product_id
)
SELECT
    p.public_sku,
    p.title_fr                       AS title,
    p.description_fr                 AS description,
    p.gtin,
    p.language::text                 AS language,
    p.format::text                   AS format,
    x.name_fr                        AS extension_name,
    p.content,
    lp.price_ttc_chf                 AS price_chf,
    CASE WHEN av.sellable > 0 THEN 'LOCAL_STOCK'
         WHEN av.quota > 0 THEN 'PREORDER'
         ELSE 'UNAVAILABLE' END      AS availability,
    LEAST(p.max_qty_per_order,
          CASE WHEN av.sellable > 0 THEN av.sellable ELSE av.quota END) AS max_order_qty,
    p.release_date,
    p.release_date_confirmed,
    p.image_urls,
    GREATEST(p.updated_at, lp.at)    AS updated_at
FROM pokeshop.products p
JOIN latest_price lp ON lp.product_id = p.product_id
JOIN availability av ON av.product_id = p.product_id
LEFT JOIN pokeshop.extensions x ON x.code = p.extension AND p.extension <> 'SANS_EXTENSION'
WHERE p.status = 'PUBLIE'
  AND p.image_rights_ok
  -- Données FICTIVES jamais visibles en production ; visibles en essai avec SET pokeshop.include_fictif = 'on'.
  AND (NOT p.fictif OR current_setting('pokeshop.include_fictif', true) = 'on');

COMMENT ON VIEW storefront.public_catalog IS
    'Catalogue public : aucune donnée de coût, fournisseur, marge ou personne. Stock fournisseur jamais affiché.';

CREATE VIEW pokeshop.current_autonomy AS
SELECT DISTINCT ON (scope) scope, level, changed_by, changed_by_role, reason, at
  FROM pokeshop.autonomy_levels
 ORDER BY scope, change_id DESC;
COMMENT ON VIEW pokeshop.current_autonomy IS 'Niveau d''autonomie en vigueur par périmètre (BP §13).';

-- ------------------------------------------------------------------ droits

REVOKE ALL ON SCHEMA pokeshop FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA pokeshop FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pokeshop FROM PUBLIC;
REVOKE ALL ON SCHEMA storefront FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA storefront FROM PUBLIC;

-- Lecteur boutique : la vue publique, rien d'autre.
GRANT USAGE ON SCHEMA storefront TO storefront_reader;
GRANT SELECT ON storefront.public_catalog TO storefront_reader;

-- Moteur (API, n8n) : lecture/écriture interne, journaux en ajout seul.
GRANT USAGE ON SCHEMA pokeshop, storefront TO pokeshop_engine;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA pokeshop TO pokeshop_engine;
REVOKE UPDATE, DELETE, TRUNCATE ON pokeshop.audit_log, pokeshop.stock_movements, pokeshop.price_events,
    pokeshop.price_decisions, pokeshop.supplier_offers, pokeshop.autonomy_levels FROM pokeshop_engine;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON pokeshop.schema_migrations FROM pokeshop_engine;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pokeshop TO pokeshop_engine;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pokeshop TO pokeshop_engine;
GRANT SELECT ON storefront.public_catalog TO pokeshop_engine;

-- Propriétaire : tout ce que fait le moteur (les journaux restent en ajout seul par trigger).
DO $$
BEGIN
    IF NOT pg_has_role('pokeshop_owner', 'pokeshop_engine', 'MEMBER') THEN
        GRANT pokeshop_engine TO pokeshop_owner;
    END IF;
END $$;

INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('003', 'public_catalog');

COMMIT;
