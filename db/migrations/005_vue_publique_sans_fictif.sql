-- 005_vue_publique_sans_fictif.sql — vue publique sans aucune donnée FICTIVE, vue d'essai réservée au moteur.
--
-- Avant : storefront.public_catalog montrait les produits FICTIFS dès que la session posait
-- `SET pokeshop.include_fictif = 'on'`. Un paramètre de session personnalisé est réglable par
-- N'IMPORTE QUEL rôle, y compris storefront_reader (site public) : le filtre ne protégeait rien.
--
-- Après :
--   * storefront.public_catalog : `AND NOT p.fictif`, sans condition de session (fermé par défaut) ;
--   * pokeshop.public_catalog_test : même définition, FICTIFS inclus, dans le schéma INTERNE (jamais
--     exposé, aucun droit pour storefront_reader) ; lecture accordée à pokeshop_engine seulement
--     (essais du moteur, recette avec le jeu FICTIF).
-- Mêmes colonnes publiques qu'en 003 (aucun coût, fournisseur, marge ni donnée personnelle).

BEGIN;

CREATE VIEW pokeshop.public_catalog_test WITH (security_barrier = true) AS
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
  AND p.image_rights_ok;

COMMENT ON VIEW pokeshop.public_catalog_test IS
    'Essais du moteur : même contenu que storefront.public_catalog, produits FICTIFS compris. Jamais exposée.';

CREATE OR REPLACE VIEW storefront.public_catalog WITH (security_barrier = true) AS
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
  -- Données FICTIVES jamais visibles ici, quel que soit le réglage de session (vue d'essai : pokeshop.public_catalog_test).
  AND NOT p.fictif;

COMMENT ON VIEW storefront.public_catalog IS
    'Catalogue public : aucune donnée de coût, fournisseur, marge ou personne ; aucun produit FICTIF. Stock fournisseur jamais affiché.';

-- Droits : la vue d'essai n'est lisible que par le moteur (et la propriétaire, membre de pokeshop_engine).
REVOKE ALL ON pokeshop.public_catalog_test FROM PUBLIC;
REVOKE ALL ON pokeshop.public_catalog_test FROM storefront_reader;
GRANT SELECT ON pokeshop.public_catalog_test TO pokeshop_engine;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON pokeshop.public_catalog_test FROM pokeshop_engine;

INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('005', 'vue_publique_sans_fictif');

COMMIT;
