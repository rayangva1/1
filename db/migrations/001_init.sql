-- 001_init.sql — schéma initial du moteur {{NOM_BOUTIQUE}} (PostgreSQL 15+ / 16, compatible Supabase)
-- Propriété : agent data-pipeline (SPEC §3). Migrations « vers l'avant » uniquement :
-- une erreur => la transaction entière est annulée (psql -v ON_ERROR_STOP=1).
--
-- Schémas
--   pokeshop   : données internes (offres, coûts, marges, commandes, journal). Jamais exposé.
--   storefront : vues publiques sans coût ni fournisseur (003_public_catalog.sql).
-- Montants : numeric (jamais float). Horodatages : timestamptz. Données FICTIVES : fictif = true.

BEGIN;

CREATE SCHEMA pokeshop;
COMMENT ON SCHEMA pokeshop IS 'Données internes (coûts, marges, fournisseurs, commandes). Ne jamais exposer via API publique.';

CREATE TABLE pokeshop.schema_migrations (
    version    text PRIMARY KEY,
    name       text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ énumérations
-- Valeurs identiques aux enums Python (vérifié par tests/test_db_migrations.py).

CREATE TYPE pokeshop.language_code AS ENUM ('FR', 'EN', 'JP', 'DE', 'IT', 'NA', 'UNKNOWN');
CREATE TYPE pokeshop.product_format AS ENUM (
    'DISPLAY', 'HALF_DISPLAY', 'ETB', 'BUNDLE', 'TRIPACK', 'COLLECTION_BOX', 'TIN', 'BOOSTER',
    'SLEEVES', 'BINDER', 'DECK_BOX', 'PLAYMAT', 'ACCESSORY', 'UNKNOWN'
);
CREATE TYPE pokeshop.availability_status AS ENUM (
    'IN_STOCK', 'LOW_STOCK', 'OUT_OF_STOCK', 'PREORDER', 'ALLOCATION', 'DISCONTINUED', 'UNKNOWN'
);
CREATE TYPE pokeshop.decision_status AS ENUM ('OK', 'REVIEW', 'DRAFT', 'BLOCKED');
CREATE TYPE pokeshop.movement_kind AS ENUM (
    'RECEIPT', 'RESERVE', 'CANCEL', 'FULFILL', 'REFUND_NO_RETURN', 'RETURN_RESTOCK', 'RETURN_DAMAGED',
    'MARK_DAMAGED', 'WRITE_OFF', 'SET_SAFETY'
);
CREATE TYPE pokeshop.reservation_status AS ENUM ('ACTIVE', 'CANCELLED', 'FULFILLED');
CREATE TYPE pokeshop.price_event_kind AS ENUM ('PROPOSED', 'PUBLISHED', 'VALIDATED', 'ROLLED_BACK');
CREATE TYPE pokeshop.source_kind AS ENUM ('API', 'CSV', 'XLSX', 'XML', 'EMAIL', 'PDF', 'MANUAL');
CREATE TYPE pokeshop.import_status AS ENUM ('ACCEPTED', 'PARTIAL', 'QUARANTINED', 'FAILED');
CREATE TYPE pokeshop.vat_mode AS ENUM ('EFFECTIVE', 'NOT_REGISTERED');

-- -------------------------------------------------------------- référentiels

CREATE TABLE pokeshop.suppliers (
    supplier_id      text PRIMARY KEY CHECK (supplier_id ~ '^[a-z0-9_]{2,64}$'),
    name             text NOT NULL CHECK (length(name) > 0),
    country          char(2) CHECK (country ~ '^[A-Z]{2}$'),
    website          text CHECK (website IS NULL OR website ~ '^https://'),
    priority         smallint CHECK (priority BETWEEN 1 AND 3),
    status           text NOT NULL DEFAULT 'PISTE'
                     CHECK (status IN ('PISTE', 'CONTACTE', 'EN_DISCUSSION', 'ACCEPTE', 'REFUSE', 'SUSPENDU')),
    access_mode      text NOT NULL DEFAULT 'AUCUN'
                     CHECK (access_mode IN ('AUCUN', 'API', 'FICHIER', 'EMAIL_PDF', 'PORTAIL_AUTORISE')),
    access_agreement_ref text,
    mapping_version  text,
    source_ref       text,
    fictif           boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT suppliers_fictif_prefix CHECK (fictif = (supplier_id LIKE 'fictif\_%')),
    -- BP §6 : pas d'accès automatisé (API, portail) sans accord écrit sur l'usage.
    CONSTRAINT suppliers_access_agreement CHECK (access_mode NOT IN ('API', 'PORTAIL_AUTORISE') OR access_agreement_ref IS NOT NULL)
);
COMMENT ON TABLE pokeshop.suppliers IS 'Fournisseurs et pistes (BP §2). Statut PISTE = aucun partenariat acquis.';

CREATE TABLE pokeshop.supplier_contacts (
    contact_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id      text NOT NULL REFERENCES pokeshop.suppliers ON DELETE CASCADE,
    role             text NOT NULL CHECK (length(role) > 0),
    channel          text NOT NULL CHECK (channel IN ('EMAIL', 'TELEPHONE', 'FORMULAIRE', 'PORTAIL', 'COURRIER')),
    value            text NOT NULL CHECK (length(value) > 0),
    is_personal_data boolean NOT NULL DEFAULT true,
    source_ref       text NOT NULL CHECK (length(source_ref) > 0),
    collected_at     date NOT NULL,
    notes            text,
    fictif           boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (supplier_id, channel, value)
);
COMMENT ON TABLE pokeshop.supplier_contacts IS 'Contacts fournisseurs : préférer les adresses génériques ; donnée personnelle si nominative (LPD).';

CREATE TABLE pokeshop.extensions (
    code             text PRIMARY KEY CHECK (code ~ '^[A-Z0-9][A-Z0-9_.\-]{1,31}$'),
    name_fr          text NOT NULL CHECK (length(name_fr) > 0),
    release_date_fr  date,
    official_code    boolean NOT NULL DEFAULT false,
    source_urls      text[] NOT NULL DEFAULT '{}',
    fictif           boolean NOT NULL DEFAULT false,
    CONSTRAINT extensions_fictif_prefix CHECK (fictif = (code LIKE 'FICTIF\_%')),
    -- Aucune extension réelle sans source datée (data/extensions_aliases.yaml).
    CONSTRAINT extensions_sourced CHECK (fictif OR code = 'SANS_EXTENSION' OR cardinality(source_urls) > 0)
);
INSERT INTO pokeshop.extensions (code, name_fr, official_code) VALUES ('SANS_EXTENSION', 'Sans extension (accessoire)', false);

CREATE TABLE pokeshop.fx_rates (
    fx_rate_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency         char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    rate_to_chf      numeric(18, 8) NOT NULL CHECK (rate_to_chf > 0),
    source           text NOT NULL CHECK (length(source) > 0),
    rate_date        date NOT NULL,
    fetched_at       timestamptz NOT NULL DEFAULT now(),
    fictif           boolean NOT NULL DEFAULT false,
    UNIQUE (currency, source, rate_date),
    CONSTRAINT fx_rates_chf_is_one CHECK (currency <> 'CHF' OR rate_to_chf = 1)
);
COMMENT ON TABLE pokeshop.fx_rates IS 'Taux de change avec source et date (BP §4 : l''IA ne choisit jamais un taux).';

CREATE TABLE pokeshop.pricing_rules (
    rules_version    text PRIMARY KEY CHECK (rules_version ~ '^\S{1,64}$'),
    status           text NOT NULL DEFAULT 'PROPOSITION' CHECK (status IN ('PROPOSITION', 'VALIDE', 'RETIRE')),
    vat_mode         pokeshop.vat_mode,
    effective_date   date NOT NULL,
    content_sha256   char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    content          jsonb NOT NULL,
    source_path      text NOT NULL,
    validated_by     text,
    validated_at     timestamptz,
    fictif           boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pricing_rules_validation CHECK (status <> 'VALIDE' OR (validated_by IS NOT NULL AND validated_at IS NOT NULL))
);
COMMENT ON TABLE pokeshop.pricing_rules IS 'Règles versionnées (config/pricing_rules.vN.yaml) ; contenu figé (002).';

-- ------------------------------------------------------- imports fournisseurs

CREATE TABLE pokeshop.raw_snapshots (
    snapshot_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id       text NOT NULL REFERENCES pokeshop.suppliers,
    source_kind       pokeshop.source_kind NOT NULL,
    source_uri        text NOT NULL,
    fetched_at        timestamptz NOT NULL,
    source_ts         timestamptz,
    checksum_sha256   char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size         bigint NOT NULL CHECK (byte_size >= 0),
    storage_ref       text,
    content           bytea,
    mapping_version   text,
    import_status     pokeshop.import_status,
    rows_read         integer CHECK (rows_read >= 0),
    accepted_count    integer CHECK (accepted_count >= 0),
    quarantined_count integer CHECK (quarantined_count >= 0),
    dry_run           boolean NOT NULL DEFAULT true,
    report_md         text,
    fictif            boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (supplier_id, checksum_sha256),
    CONSTRAINT raw_snapshots_content_size CHECK (content IS NULL OR octet_length(content) = byte_size),
    CONSTRAINT raw_snapshots_content_hash CHECK (content IS NULL OR encode(sha256(content), 'hex') = checksum_sha256)
);
COMMENT ON TABLE pokeshop.raw_snapshots IS 'Captures brutes datées (BP §6) ; contenu et empreinte immuables (002). Contient des prix B2B : interne.';

CREATE TABLE pokeshop.supplier_offers (
    offer_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id         bigint NOT NULL REFERENCES pokeshop.raw_snapshots ON DELETE RESTRICT,
    supplier_id         text NOT NULL REFERENCES pokeshop.suppliers,
    line_no             integer,
    status              text NOT NULL CHECK (status IN ('VALIDE', 'QUARANTAINE')),
    quarantine_reasons  text[] NOT NULL DEFAULT '{}',
    supplier_sku        text,
    gtin                text CHECK (gtin IS NULL OR gtin ~ '^([0-9]{8}|[0-9]{13}|[0-9]{14})$'),
    language            pokeshop.language_code,
    extension           text REFERENCES pokeshop.extensions (code),
    format              pokeshop.product_format,
    content             text,
    sealed              boolean,
    units_per_pack      integer CHECK (units_per_pack >= 1),
    price               numeric(14, 4) CHECK (price >= 0),
    currency            char(3) CHECK (currency ~ '^[A-Z]{3}$'),
    price_includes_vat  boolean,
    vat_rate            numeric(6, 5) CHECK (vat_rate >= 0 AND vat_rate < 1),
    tier_discounts      jsonb NOT NULL DEFAULT '[]',
    moq                 integer CHECK (moq >= 1),
    carton_qty          integer CHECK (carton_qty >= 1),
    availability_status pokeshop.availability_status NOT NULL DEFAULT 'UNKNOWN',
    available_qty       integer CHECK (available_qty >= 0),
    allocation_qty      integer CHECK (allocation_qty >= 0),
    release_date        date,
    incoterm            text,
    ship_from_country   char(2) CHECK (ship_from_country ~ '^[A-Z]{2}$'),
    vat_country         char(2) CHECK (vat_country ~ '^[A-Z]{2}$'),
    stock_pool_id       text,
    source_ts           timestamptz NOT NULL,
    raw_ref             text NOT NULL,
    raw                 jsonb NOT NULL DEFAULT '{}',
    anomalies           jsonb NOT NULL DEFAULT '[]',
    fictif              boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    -- Une offre VALIDE est complète sur les champs critiques (SPEC §2.5) ; sinon QUARANTAINE motivée.
    CONSTRAINT supplier_offers_valid_complete CHECK (
        status = 'QUARANTAINE' OR (
            supplier_sku IS NOT NULL AND price > 0 AND currency IS NOT NULL AND price_includes_vat IS NOT NULL
            AND units_per_pack IS NOT NULL AND language IS NOT NULL AND language <> 'UNKNOWN'
        )
    ),
    CONSTRAINT supplier_offers_quarantine_reasons CHECK (status = 'VALIDE' OR cardinality(quarantine_reasons) > 0)
);
CREATE UNIQUE INDEX supplier_offers_valid_sku_per_snapshot
    ON pokeshop.supplier_offers (snapshot_id, supplier_sku) WHERE status = 'VALIDE';
CREATE INDEX supplier_offers_sku_recent ON pokeshop.supplier_offers (supplier_id, supplier_sku, source_ts DESC);
CREATE INDEX supplier_offers_gtin ON pokeshop.supplier_offers (gtin) WHERE gtin IS NOT NULL;
CREATE INDEX supplier_offers_quarantine ON pokeshop.supplier_offers (supplier_id, created_at) WHERE status = 'QUARANTAINE';
COMMENT ON TABLE pokeshop.supplier_offers IS 'Offres normalisées et lignes en quarantaine. Prix B2B : interne, jamais public.';

-- ------------------------------------------------------------------- catalogue

CREATE TABLE pokeshop.products (
    product_id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_sku             text UNIQUE CHECK (public_sku ~ '^[A-Z0-9][A-Z0-9\-]{2,40}$'),
    identity_key           text NOT NULL,
    identity_complete      boolean NOT NULL DEFAULT false,
    gtin                   text CHECK (gtin IS NULL OR gtin ~ '^([0-9]{8}|[0-9]{13}|[0-9]{14})$'),
    language               pokeshop.language_code NOT NULL DEFAULT 'UNKNOWN',
    extension              text REFERENCES pokeshop.extensions (code),
    format                 pokeshop.product_format NOT NULL DEFAULT 'UNKNOWN',
    content                text,
    sealed                 boolean,
    status                 text NOT NULL DEFAULT 'BROUILLON'
                           CHECK (status IN ('BROUILLON', 'A_VALIDER', 'PUBLIE', 'SUSPENDU', 'ARCHIVE')),
    title_fr               text,
    description_fr         text,
    image_urls             text[] NOT NULL DEFAULT '{}',
    image_rights_ok        boolean NOT NULL DEFAULT false,
    max_qty_per_order      integer NOT NULL DEFAULT 5 CHECK (max_qty_per_order >= 1),
    release_date           date,
    release_date_confirmed boolean NOT NULL DEFAULT false,
    fictif                 boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    -- Accessoire <=> langue « NA » (sans objet) ; produit de cartes : jamais « NA ».
    CONSTRAINT products_accessory_language CHECK (
        (language = 'NA') = (format IN ('SLEEVES', 'BINDER', 'DECK_BOX', 'PLAYMAT', 'ACCESSORY'))
    ),
    CONSTRAINT products_no_extension_only_accessories CHECK (
        extension IS DISTINCT FROM 'SANS_EXTENSION' OR format IN ('SLEEVES', 'BINDER', 'DECK_BOX', 'PLAYMAT', 'ACCESSORY')
    ),
    -- BP §6/§11 : identité ambiguë = brouillon ; publication = identité complète, scellé, droits d'image.
    CONSTRAINT products_publishable CHECK (
        status <> 'PUBLIE' OR (
            identity_complete AND sealed AND image_rights_ok AND title_fr IS NOT NULL AND public_sku IS NOT NULL
        )
    )
);
CREATE UNIQUE INDEX products_identity_key_complete ON pokeshop.products (identity_key) WHERE identity_complete;
CREATE INDEX products_gtin ON pokeshop.products (gtin) WHERE gtin IS NOT NULL;
CREATE INDEX products_status ON pokeshop.products (status);
COMMENT ON COLUMN pokeshop.products.identity_key IS 'GTIN|LANGUE|EXTENSION|FORMAT|CONTENU|SCELLÉ, calculé par trigger (même règle que pokeshop.catalog).';

CREATE TABLE pokeshop.product_supplier_links (
    link_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id     bigint NOT NULL REFERENCES pokeshop.products ON DELETE CASCADE,
    supplier_id    text NOT NULL REFERENCES pokeshop.suppliers,
    supplier_sku   text NOT NULL CHECK (length(supplier_sku) > 0),
    match_status   text NOT NULL CHECK (match_status IN ('MATCHED', 'NEW_DRAFT', 'AMBIGUOUS', 'CONFIRMED_BY_HUMAN')),
    match_reasons  text[] NOT NULL DEFAULT '{}',
    shop_variant_id text,
    validated_by   text,
    validated_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (supplier_id, supplier_sku),
    CONSTRAINT links_human_confirmation CHECK (
        match_status <> 'CONFIRMED_BY_HUMAN' OR (validated_by IS NOT NULL AND validated_at IS NOT NULL)
    )
);
CREATE INDEX product_supplier_links_product ON pokeshop.product_supplier_links (product_id);

-- ------------------------------------------------------------------- achats

CREATE TABLE pokeshop.purchase_proposals (
    proposal_id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    generated_at              timestamptz NOT NULL,
    status                    text NOT NULL DEFAULT 'PROPOSITION_A_VALIDER'
                              CHECK (status IN ('PROPOSITION_A_VALIDER', 'VALIDEE', 'REFUSEE', 'EXPIREE', 'COMMANDEE')),
    requires_human_validation boolean NOT NULL DEFAULT true CHECK (requires_human_validation),
    supplier_id               text REFERENCES pokeshop.suppliers,
    total_cost_chf            numeric(12, 2) NOT NULL CHECK (total_cost_chf >= 0),
    budget_available_chf      numeric(12, 2) NOT NULL CHECK (budget_available_chf >= 0),
    budget_remaining_chf      numeric(12, 2) NOT NULL CHECK (budget_remaining_chf >= 0),
    rules_version             text NOT NULL REFERENCES pokeshop.pricing_rules,
    inputs_hash               char(64) NOT NULL CHECK (inputs_hash ~ '^[0-9a-f]{64}$'),
    skipped                   jsonb NOT NULL DEFAULT '[]',
    validated_by              text,
    validated_at              timestamptz,
    fictif                    boolean NOT NULL DEFAULT false,
    created_at                timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT proposals_validation CHECK (
        status NOT IN ('VALIDEE', 'COMMANDEE') OR (validated_by IS NOT NULL AND validated_at IS NOT NULL)
    ),
    CONSTRAINT proposals_within_budget CHECK (total_cost_chf <= budget_available_chf)
);
COMMENT ON TABLE pokeshop.purchase_proposals IS 'Paniers fournisseurs proposés (BP §5) : jamais une commande sans validation.';

CREATE TABLE pokeshop.purchase_proposal_lines (
    proposal_line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id      bigint NOT NULL REFERENCES pokeshop.purchase_proposals ON DELETE CASCADE,
    product_id       bigint NOT NULL REFERENCES pokeshop.products,
    supplier_id      text NOT NULL REFERENCES pokeshop.suppliers,
    supplier_sku     text NOT NULL,
    extension        text REFERENCES pokeshop.extensions (code),
    qty              integer NOT NULL CHECK (qty >= 1),
    unit_cost_chf    numeric(14, 4) NOT NULL CHECK (unit_cost_chf > 0),
    line_cost_chf    numeric(12, 2) NOT NULL CHECK (line_cost_chf >= 0),
    position         integer,
    notes            text[] NOT NULL DEFAULT '{}',
    UNIQUE (proposal_id, product_id, supplier_id)
);

-- ------------------------------------------------------------- coûts et prix

CREATE TABLE pokeshop.cost_lots (
    lot_id                text PRIMARY KEY CHECK (length(lot_id) > 0),
    product_id            bigint NOT NULL REFERENCES pokeshop.products,
    supplier_id           text REFERENCES pokeshop.suppliers,
    purchase_proposal_id  bigint REFERENCES pokeshop.purchase_proposals,
    received_at           timestamptz NOT NULL,
    qty                   integer NOT NULL CHECK (qty >= 1),
    qty_remaining         integer NOT NULL CHECK (qty_remaining >= 0),
    unit_cost_chf         numeric(14, 4) NOT NULL CHECK (unit_cost_chf > 0),
    cost_basis            text NOT NULL DEFAULT 'ESTIMATE' CHECK (cost_basis IN ('ESTIMATE', 'INVOICE')),
    invoice_ref           text,
    fx_rate_id            bigint REFERENCES pokeshop.fx_rates,
    landed_cost_breakdown jsonb,
    fictif                boolean NOT NULL DEFAULT false,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT cost_lots_remaining CHECK (qty_remaining <= qty),
    CONSTRAINT cost_lots_invoice CHECK (cost_basis <> 'INVOICE' OR invoice_ref IS NOT NULL)
);
CREATE INDEX cost_lots_product ON pokeshop.cost_lots (product_id, received_at);
COMMENT ON TABLE pokeshop.cost_lots IS 'Coût comptable historique par réception (BP §4) : une baisse de tarif ne le modifie pas.';

CREATE TABLE pokeshop.replacement_costs (
    replacement_cost_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id          bigint NOT NULL REFERENCES pokeshop.products,
    supplier_id         text NOT NULL REFERENCES pokeshop.suppliers,
    offer_id            bigint REFERENCES pokeshop.supplier_offers,
    unit_cost_chf       numeric(14, 4) NOT NULL CHECK (unit_cost_chf > 0),
    source_ts           timestamptz NOT NULL,
    rules_version       text REFERENCES pokeshop.pricing_rules,
    computed_at         timestamptz NOT NULL DEFAULT now(),
    fictif              boolean NOT NULL DEFAULT false
);
CREATE INDEX replacement_costs_recent ON pokeshop.replacement_costs (product_id, source_ts DESC);

CREATE TABLE pokeshop.price_decisions (
    decision_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id            bigint NOT NULL REFERENCES pokeshop.products,
    offer_id              bigint REFERENCES pokeshop.supplier_offers,
    rules_version         text NOT NULL REFERENCES pokeshop.pricing_rules,
    inputs_hash           char(64) NOT NULL CHECK (inputs_hash ~ '^[0-9a-f]{64}$'),
    status                pokeshop.decision_status NOT NULL,
    reasons               text[] NOT NULL DEFAULT '{}',
    landed_cost_chf       numeric(14, 4) CHECK (landed_cost_chf >= 0),
    floor_price_chf       numeric(12, 2) CHECK (floor_price_chf >= 0),
    profitable_price_chf  numeric(12, 2) CHECK (profitable_price_chf >= 0),
    recommended_price_chf numeric(12, 2) CHECK (recommended_price_chf >= 0),
    evaluated_price_chf   numeric(12, 2) CHECK (evaluated_price_chf >= 0),
    contribution_chf      numeric(12, 2),
    contribution_pct      numeric(8, 4),
    restock_eligible      boolean NOT NULL DEFAULT true,
    decided_at            timestamptz NOT NULL DEFAULT now(),
    actor                 text NOT NULL DEFAULT 'engine',
    fictif                boolean NOT NULL DEFAULT false,
    UNIQUE (product_id, inputs_hash)
);
COMMENT ON TABLE pokeshop.price_decisions IS 'Décisions du moteur (coût, plancher, contribution) : interne.';

CREATE TABLE pokeshop.price_events (
    event_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id    bigint NOT NULL REFERENCES pokeshop.products,
    kind          pokeshop.price_event_kind NOT NULL,
    price_ttc_chf numeric(12, 2) CHECK (price_ttc_chf > 0),
    decision_id   bigint REFERENCES pokeshop.price_decisions,
    validated     boolean NOT NULL DEFAULT false,
    actor         text NOT NULL CHECK (length(actor) > 0),
    note          text NOT NULL DEFAULT '',
    at            timestamptz NOT NULL DEFAULT now(),
    fictif        boolean NOT NULL DEFAULT false,
    CONSTRAINT price_events_price CHECK (kind = 'VALIDATED' OR price_ttc_chf IS NOT NULL),
    -- Un prix publié vient d'une décision du moteur ou d'une validation humaine.
    CONSTRAINT price_events_published_source CHECK (kind <> 'PUBLISHED' OR validated OR decision_id IS NOT NULL)
);
CREATE INDEX price_events_product ON pokeshop.price_events (product_id, event_id DESC);
COMMENT ON TABLE pokeshop.price_events IS 'Historique append-only des prix publics (dernier PUBLISHED/ROLLED_BACK = prix affiché).';

-- -------------------------------------------------------------------- stock

CREATE TABLE pokeshop.stock_levels (
    product_id bigint PRIMARY KEY REFERENCES pokeshop.products,
    on_hand    integer NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
    reserved   integer NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    damaged    integer NOT NULL DEFAULT 0 CHECK (damaged >= 0),
    safety     integer NOT NULL DEFAULT 0 CHECK (safety >= 0),
    version    bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT stock_levels_physical CHECK (reserved + damaged <= on_hand)
);
COMMENT ON TABLE pokeshop.stock_levels IS 'Stock LOCAL réel (Genève). Le stock fournisseur n''est jamais ici. Version incrémentée à chaque écriture (CAS).';

CREATE TABLE pokeshop.stock_movements (
    movement_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      bigint NOT NULL REFERENCES pokeshop.products,
    kind            pokeshop.movement_kind NOT NULL,
    qty             integer NOT NULL,
    ref             text NOT NULL CHECK (length(ref) > 0),
    at              timestamptz NOT NULL DEFAULT now(),
    version_after   bigint NOT NULL CHECK (version_after >= 0),
    idempotency_key text UNIQUE,
    fictif          boolean NOT NULL DEFAULT false
);
CREATE INDEX stock_movements_product ON pokeshop.stock_movements (product_id, movement_id);

-- ---------------------------------------------------------------- commandes

CREATE TABLE pokeshop.orders (
    order_id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_order_ref           text NOT NULL UNIQUE,
    status                   text NOT NULL DEFAULT 'PAYEE' CHECK (status IN (
                                 'PAYEE', 'EN_PREPARATION', 'EXPEDIEE', 'LIVREE', 'ANNULEE', 'REMBOURSEE',
                                 'REMBOURSEE_PARTIELLEMENT')),
    currency                 char(3) NOT NULL DEFAULT 'CHF' CHECK (currency = 'CHF'),
    ship_to_country          char(2) NOT NULL DEFAULT 'CH' CHECK (ship_to_country = 'CH'),
    paid_at                  timestamptz NOT NULL,
    goods_ttc_chf            numeric(12, 2) NOT NULL CHECK (goods_ttc_chf >= 0),
    discount_ttc_chf         numeric(12, 2) NOT NULL DEFAULT 0 CHECK (discount_ttc_chf >= 0),
    shipping_charged_ttc_chf numeric(12, 2) NOT NULL DEFAULT 0 CHECK (shipping_charged_ttc_chf >= 0),
    total_paid_ttc_chf       numeric(12, 2) NOT NULL CHECK (total_paid_ttc_chf >= 0),
    customer_ref             text,
    contribution_chf         numeric(12, 2),
    rules_version            text REFERENCES pokeshop.pricing_rules,
    inputs_hash              char(64) CHECK (inputs_hash ~ '^[0-9a-f]{64}$'),
    fictif                   boolean NOT NULL DEFAULT false,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT orders_total CHECK (total_paid_ttc_chf = goods_ttc_chf - discount_ttc_chf + shipping_charged_ttc_chf)
);
COMMENT ON COLUMN pokeshop.orders.customer_ref IS 'Référence pseudonyme (ID boutique) : aucune donnée personnelle ici.';

CREATE TABLE pokeshop.order_lines (
    order_line_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id           bigint NOT NULL REFERENCES pokeshop.orders ON DELETE RESTRICT,
    product_id         bigint NOT NULL REFERENCES pokeshop.products,
    qty                integer NOT NULL CHECK (qty >= 1),
    unit_price_ttc_chf numeric(12, 2) NOT NULL CHECK (unit_price_ttc_chf > 0),
    unit_cost_chf      numeric(14, 4) CHECK (unit_cost_chf >= 0),
    UNIQUE (order_id, product_id)
);
COMMENT ON TABLE pokeshop.order_lines IS 'Prix figé à la commande (BP §5 : ne jamais changer le prix d''une commande conclue).';

CREATE TABLE pokeshop.reservations (
    reservation_id text PRIMARY KEY CHECK (length(reservation_id) > 0),
    product_id     bigint NOT NULL REFERENCES pokeshop.products,
    order_id       bigint NOT NULL REFERENCES pokeshop.orders,
    qty            integer NOT NULL CHECK (qty >= 1),
    status         pokeshop.reservation_status NOT NULL DEFAULT 'ACTIVE',
    refunded_qty   integer NOT NULL DEFAULT 0 CHECK (refunded_qty >= 0),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, product_id),
    CONSTRAINT reservations_refund CHECK (refunded_qty <= qty)
);

CREATE TABLE pokeshop.preorder_allocations (
    allocation_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id           bigint NOT NULL REFERENCES pokeshop.products,
    supplier_id          text NOT NULL REFERENCES pokeshop.suppliers,
    firm_allocation_qty  integer NOT NULL CHECK (firm_allocation_qty >= 0),
    committed_preorders  integer NOT NULL DEFAULT 0 CHECK (committed_preorders >= 0),
    safety               integer NOT NULL DEFAULT 0 CHECK (safety >= 0),
    confirmed_in_writing boolean NOT NULL DEFAULT false,
    evidence_ref         text,
    confirmed_at         timestamptz,
    expected_date        date,
    status               text NOT NULL DEFAULT 'OUVERTE' CHECK (status IN ('OUVERTE', 'CLOSE', 'ANNULEE')),
    fictif               boolean NOT NULL DEFAULT false,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT allocations_evidence CHECK (NOT confirmed_in_writing OR (evidence_ref IS NOT NULL AND confirmed_at IS NOT NULL)),
    -- SPEC §0.3 : pas de précommande sans allocation ferme écrite.
    CONSTRAINT allocations_no_preorder_without_firm CHECK (committed_preorders = 0 OR confirmed_in_writing),
    CONSTRAINT allocations_not_oversold CHECK (committed_preorders <= firm_allocation_qty)
);

-- --------------------------------------------------------------- pilotage

CREATE TABLE pokeshop.incidents (
    incident_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text NOT NULL CHECK (length(kind) BETWEEN 1 AND 64),
    severity         text NOT NULL CHECK (severity IN ('INFO', 'MINEUR', 'MAJEUR', 'CRITIQUE')),
    scope            text NOT NULL CHECK (scope IN ('REFERENCE', 'WORKFLOW', 'SOURCE', 'GLOBAL')),
    status           text NOT NULL DEFAULT 'OUVERT' CHECK (status IN ('OUVERT', 'EN_COURS', 'RESOLU', 'CLOS')),
    escalation_level text CHECK (escalation_level IN ('E1', 'E2', 'E3')),
    product_id       bigint REFERENCES pokeshop.products,
    supplier_id      text REFERENCES pokeshop.suppliers,
    snapshot_id      bigint REFERENCES pokeshop.raw_snapshots,
    workflow         text,
    cause            text NOT NULL CHECK (length(cause) > 0),
    proposed_action  text NOT NULL CHECK (length(proposed_action) > 0),
    details          jsonb NOT NULL DEFAULT '{}',
    opened_at        timestamptz NOT NULL DEFAULT now(),
    resolved_at      timestamptz,
    resolved_by      text,
    fictif           boolean NOT NULL DEFAULT false,
    CONSTRAINT incidents_resolution CHECK ((status IN ('RESOLU', 'CLOS')) = (resolved_at IS NOT NULL))
);
CREATE INDEX incidents_open ON pokeshop.incidents (opened_at) WHERE status IN ('OUVERT', 'EN_COURS');
COMMENT ON TABLE pokeshop.incidents IS 'Workflow incident BP §12 : quarantaine, suspension, cause et action proposée, reprise.';

CREATE TABLE pokeshop.audit_log (
    audit_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chain_seq       bigint NOT NULL UNIQUE,
    at              timestamptz NOT NULL DEFAULT clock_timestamp(),
    actor           text NOT NULL CHECK (length(actor) > 0),
    actor_kind      text NOT NULL CHECK (actor_kind IN ('AGENT', 'SYSTEME', 'PROPRIETAIRE', 'PRESTATAIRE')),
    action          text NOT NULL CHECK (length(action) > 0),
    entity          text NOT NULL CHECK (length(entity) > 0),
    entity_id       text,
    dry_run         boolean NOT NULL DEFAULT true,
    autonomy_level  smallint CHECK (autonomy_level BETWEEN 1 AND 4),
    payload         jsonb NOT NULL DEFAULT '{}',
    idempotency_key text,
    prev_hash       char(64) CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
    row_hash        char(64) NOT NULL CHECK (row_hash ~ '^[0-9a-f]{64}$')
);
CREATE INDEX audit_log_entity ON pokeshop.audit_log (entity, entity_id);
COMMENT ON TABLE pokeshop.audit_log IS 'Journal append-only chaîné (sha256) : aucune mise à jour ni suppression (002).';

CREATE TABLE pokeshop.idempotency_keys (
    scope           text NOT NULL CHECK (length(scope) > 0),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 200),
    request_sha256  char(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    status          text NOT NULL DEFAULT 'EN_COURS' CHECK (status IN ('EN_COURS', 'TERMINE', 'ECHEC')),
    response        jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    expires_at      timestamptz,
    PRIMARY KEY (scope, idempotency_key),
    CONSTRAINT idempotency_completion CHECK ((status = 'EN_COURS') = (completed_at IS NULL))
);
COMMENT ON TABLE pokeshop.idempotency_keys IS 'Reprise sans double écriture (BP §6, §13) : même clé + autre requête = conflit.';

CREATE TABLE pokeshop.autonomy_levels (
    change_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope           text NOT NULL DEFAULT 'global' CHECK (length(scope) > 0),
    level           smallint NOT NULL CHECK (level BETWEEN 1 AND 4),
    previous_level  smallint CHECK (previous_level BETWEEN 1 AND 4),
    changed_by      text NOT NULL CHECK (length(changed_by) > 0),
    changed_by_role text NOT NULL CHECK (changed_by_role IN ('PROPRIETAIRE', 'AGENT', 'SYSTEME')),
    reason          text NOT NULL CHECK (length(reason) > 0),
    at              timestamptz NOT NULL DEFAULT now(),
    -- BP §13 + stop-loss global : agents et système peuvent seulement abaisser le niveau ;
    -- le relever (réarmement) est réservé à la propriétaire (contrôle de rôle SQL en 002).
    CONSTRAINT autonomy_raise_by_owner_only CHECK (changed_by_role = 'PROPRIETAIRE' OR level <= coalesce(previous_level, 1))
);
CREATE INDEX autonomy_levels_scope ON pokeshop.autonomy_levels (scope, change_id DESC);

INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('001', 'init');

COMMIT;
