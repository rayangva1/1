-- 002_integrity.sql — règles d'intégrité exécutées par la base (triggers, rôles, fonctions).
--
-- * Journaux append-only : audit_log, stock_movements, price_events, price_decisions,
--   supplier_offers, autonomy_levels => UPDATE, DELETE et TRUNCATE refusés.
-- * audit_log chaîné par sha256 (prev_hash -> row_hash) : toute altération, même par un
--   superutilisateur qui désactive les triggers, est détectée par pokeshop.verify_audit_chain().
-- * Clé d'identité produit calculée par la base (même règle que pokeshop.catalog).
-- * Commande conclue : quantités et prix figés (BP §5).
-- * Règles versionnées : contenu figé ; statut VALIDE et relèvement du niveau d'autonomie
--   réservés au rôle pokeshop_owner (la propriétaire).

BEGIN;

-- ------------------------------------------------------------------- rôles
-- Rôles de groupe sans connexion : les comptes de connexion en deviennent membres (db/README.md).
DO $$
BEGIN
    CREATE ROLE pokeshop_owner NOLOGIN;
EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
END $$;
DO $$
BEGIN
    CREATE ROLE pokeshop_engine NOLOGIN;
EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
END $$;
DO $$
BEGIN
    CREATE ROLE storefront_reader NOLOGIN;
EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
END $$;

CREATE FUNCTION pokeshop.is_owner() RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT pg_has_role(current_user, 'pokeshop_owner', 'MEMBER')
$$;
COMMENT ON FUNCTION pokeshop.is_owner() IS 'Vrai si l''utilisateur courant agit comme la propriétaire (membre de pokeshop_owner).';

-- ------------------------------------------------------------ append-only

CREATE FUNCTION pokeshop.forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'pokeshop.% est append-only : % interdit', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege',
              HINT = 'Ajouter une nouvelle ligne (correction, annulation) au lieu de modifier l''historique.';
END $$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['audit_log', 'stock_movements', 'price_events', 'price_decisions', 'supplier_offers', 'autonomy_levels']
    LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON pokeshop.%I FOR EACH ROW EXECUTE FUNCTION pokeshop.forbid_change()',
                       t || '_append_only', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON pokeshop.%I FOR EACH STATEMENT EXECUTE FUNCTION pokeshop.forbid_change()',
                       t || '_no_truncate', t);
    END LOOP;
END $$;

-- ------------------------------------------------------- audit_log chaîné

CREATE FUNCTION pokeshop.audit_row_digest(
    p_prev text, p_seq bigint, p_at timestamptz, p_actor text, p_actor_kind text, p_action text,
    p_entity text, p_entity_id text, p_dry_run boolean, p_level smallint, p_payload jsonb, p_idem text
) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT encode(sha256(convert_to(concat_ws(E'\x1f',
        coalesce(p_prev, ''), p_seq::text,
        to_char(p_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
        p_actor, p_actor_kind, p_action, p_entity, coalesce(p_entity_id, ''),
        p_dry_run::text, coalesce(p_level::text, ''), p_payload::text, coalesce(p_idem, '')
    ), 'UTF8')), 'hex')
$$;

CREATE FUNCTION pokeshop.audit_log_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    last_seq  bigint;
    last_hash text;
BEGIN
    -- Sérialise les insertions : la chaîne suit l'ordre de validation, pas l'ordre des séquences.
    PERFORM pg_advisory_xact_lock(hashtext('pokeshop.audit_log'));
    SELECT a.chain_seq, a.row_hash INTO last_seq, last_hash
      FROM pokeshop.audit_log a ORDER BY a.chain_seq DESC LIMIT 1;
    NEW.chain_seq := coalesce(last_seq, 0) + 1;
    NEW.prev_hash := last_hash;
    NEW.at := clock_timestamp();  -- horodatage fixé par la base (pas d'antidatage)
    NEW.row_hash := pokeshop.audit_row_digest(
        NEW.prev_hash, NEW.chain_seq, NEW.at, NEW.actor, NEW.actor_kind, NEW.action, NEW.entity,
        NEW.entity_id, NEW.dry_run, NEW.autonomy_level, NEW.payload, NEW.idempotency_key);
    RETURN NEW;
END $$;

CREATE TRIGGER audit_log_chain BEFORE INSERT ON pokeshop.audit_log
    FOR EACH ROW EXECUTE FUNCTION pokeshop.audit_log_chain();

CREATE FUNCTION pokeshop.verify_audit_chain() RETURNS TABLE (seq bigint, problem text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r        pokeshop.audit_log%ROWTYPE;
    prev     text := NULL;
    expected bigint := 1;
BEGIN
    FOR r IN SELECT * FROM pokeshop.audit_log ORDER BY pokeshop.audit_log.chain_seq LOOP
        IF r.chain_seq <> expected THEN
            seq := r.chain_seq; problem := format('séquence rompue : %s attendu', expected); RETURN NEXT;
        END IF;
        IF r.prev_hash IS DISTINCT FROM prev THEN
            seq := r.chain_seq; problem := 'prev_hash incohérent (ligne supprimée ou insérée hors chaîne)'; RETURN NEXT;
        END IF;
        IF r.row_hash <> pokeshop.audit_row_digest(
               r.prev_hash, r.chain_seq, r.at, r.actor, r.actor_kind, r.action, r.entity, r.entity_id,
               r.dry_run, r.autonomy_level, r.payload, r.idempotency_key) THEN
            seq := r.chain_seq; problem := 'empreinte invalide (ligne modifiée)'; RETURN NEXT;
        END IF;
        prev := r.row_hash;
        expected := r.chain_seq + 1;
    END LOOP;
END $$;
COMMENT ON FUNCTION pokeshop.verify_audit_chain() IS 'Aucune ligne renvoyée = journal intact.';

-- ----------------------------------------------------------- updated_at

CREATE FUNCTION pokeshop.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['suppliers', 'products', 'orders', 'reservations', 'preorder_allocations']
    LOOP
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON pokeshop.%I FOR EACH ROW EXECUTE FUNCTION pokeshop.touch_updated_at()',
                       t || '_touch', t);
    END LOOP;
END $$;

-- ---------------------------------------------------- identité produit

CREATE FUNCTION pokeshop.products_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    norm_content text := nullif(regexp_replace(upper(btrim(coalesce(NEW.content, ''))), '\s+', ' ', 'g'), '');
BEGIN
    -- Même règle que ProductIdentity.key : GTIN|LANGUE|EXTENSION|FORMAT|CONTENU|SCELLÉ, « ? » = inconnu.
    NEW.identity_key := concat_ws('|',
        coalesce(NEW.gtin, '?'),
        NEW.language::text,
        coalesce(upper(NEW.extension), '?'),
        CASE WHEN NEW.format = 'UNKNOWN' THEN '?' ELSE NEW.format::text END,
        coalesce(norm_content, '?'),
        CASE WHEN NEW.sealed IS NULL THEN '?' WHEN NEW.sealed THEN 'SEALED' ELSE 'OPEN' END);
    NEW.identity_complete := NEW.gtin IS NOT NULL AND NEW.language <> 'UNKNOWN' AND NEW.extension IS NOT NULL
        AND NEW.format <> 'UNKNOWN' AND norm_content IS NOT NULL AND NEW.sealed IS NOT NULL;
    RETURN NEW;
END $$;

CREATE TRIGGER products_identity BEFORE INSERT OR UPDATE ON pokeshop.products
    FOR EACH ROW EXECUTE FUNCTION pokeshop.products_identity();

-- -------------------------------------------------- stock : version (CAS)

CREATE FUNCTION pokeshop.stock_levels_bump() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Écriture concurrente : UPDATE ... WHERE product_id = $1 AND version = $attendue (0 ligne = conflit).
    NEW.version := OLD.version + 1;
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE TRIGGER stock_levels_bump BEFORE UPDATE ON pokeshop.stock_levels
    FOR EACH ROW EXECUTE FUNCTION pokeshop.stock_levels_bump();

-- ------------------------------------------------ commande conclue figée

CREATE FUNCTION pokeshop.order_lines_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ligne de commande % : suppression interdite (annuler ou rembourser)', OLD.order_line_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.order_id <> OLD.order_id OR NEW.product_id <> OLD.product_id OR NEW.qty <> OLD.qty
       OR NEW.unit_price_ttc_chf <> OLD.unit_price_ttc_chf THEN
        RAISE EXCEPTION 'ligne de commande % : prix et quantités figés (BP §5)', OLD.order_line_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;  -- seul unit_cost_chf (coût historique, facture réelle) peut évoluer
END $$;

CREATE TRIGGER order_lines_frozen BEFORE UPDATE OR DELETE ON pokeshop.order_lines
    FOR EACH ROW EXECUTE FUNCTION pokeshop.order_lines_frozen();

CREATE FUNCTION pokeshop.orders_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'commande % : suppression interdite', OLD.order_id USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (NEW.goods_ttc_chf, NEW.discount_ttc_chf, NEW.shipping_charged_ttc_chf, NEW.total_paid_ttc_chf, NEW.paid_at,
        NEW.shop_order_ref, NEW.currency)
       IS DISTINCT FROM
       (OLD.goods_ttc_chf, OLD.discount_ttc_chf, OLD.shipping_charged_ttc_chf, OLD.total_paid_ttc_chf, OLD.paid_at,
        OLD.shop_order_ref, OLD.currency) THEN
        RAISE EXCEPTION 'commande % : montants figés (BP §5)', OLD.order_id USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER orders_frozen BEFORE UPDATE OR DELETE ON pokeshop.orders
    FOR EACH ROW EXECUTE FUNCTION pokeshop.orders_frozen();

-- ------------------------------------------------------ règles versionnées

CREATE FUNCTION pokeshop.pricing_rules_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'règles % : suppression interdite (passer au statut RETIRE)', OLD.rules_version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'UPDATE' AND (NEW.rules_version, NEW.content, NEW.content_sha256, NEW.effective_date, NEW.source_path, NEW.vat_mode)
       IS DISTINCT FROM (OLD.rules_version, OLD.content, OLD.content_sha256, OLD.effective_date, OLD.source_path, OLD.vat_mode) THEN
        RAISE EXCEPTION 'règles % : contenu figé, créer une nouvelle version', OLD.rules_version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status = 'VALIDE' AND (TG_OP = 'INSERT' OR OLD.status <> 'VALIDE') AND NOT pokeshop.is_owner() THEN
        RAISE EXCEPTION 'règles % : validation réservée à la propriétaire (rôle pokeshop_owner)', NEW.rules_version
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER pricing_rules_guard BEFORE INSERT OR UPDATE OR DELETE ON pokeshop.pricing_rules
    FOR EACH ROW EXECUTE FUNCTION pokeshop.pricing_rules_guard();

-- ------------------------------------------------------ captures brutes

CREATE FUNCTION pokeshop.raw_snapshots_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'capture % : suppression interdite (preuve d''import)', OLD.snapshot_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (NEW.supplier_id, NEW.source_kind, NEW.source_uri, NEW.fetched_at, NEW.source_ts, NEW.checksum_sha256, NEW.byte_size, NEW.content)
       IS DISTINCT FROM
       (OLD.supplier_id, OLD.source_kind, OLD.source_uri, OLD.fetched_at, OLD.source_ts, OLD.checksum_sha256, OLD.byte_size, OLD.content) THEN
        RAISE EXCEPTION 'capture % : contenu et métadonnées de source figés', OLD.snapshot_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;  -- seuls le statut d'import, les compteurs et le rapport évoluent
END $$;

CREATE TRIGGER raw_snapshots_guard BEFORE UPDATE OR DELETE ON pokeshop.raw_snapshots
    FOR EACH ROW EXECUTE FUNCTION pokeshop.raw_snapshots_guard();

-- --------------------------------------------------- niveaux d'autonomie

CREATE FUNCTION pokeshop.autonomy_levels_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('pokeshop.autonomy_levels:' || NEW.scope));
    SELECT a.level INTO NEW.previous_level
      FROM pokeshop.autonomy_levels a WHERE a.scope = NEW.scope ORDER BY a.change_id DESC LIMIT 1;
    IF NEW.changed_by_role = 'PROPRIETAIRE' AND NOT pokeshop.is_owner() THEN
        RAISE EXCEPTION 'niveau d''autonomie : rôle PROPRIETAIRE déclaré sans appartenance à pokeshop_owner'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;  -- la contrainte autonomy_raise_by_owner_only s'applique ensuite
END $$;

CREATE TRIGGER autonomy_levels_guard BEFORE INSERT ON pokeshop.autonomy_levels
    FOR EACH ROW EXECUTE FUNCTION pokeshop.autonomy_levels_guard();

-- --------------------------------------------------------- idempotence

CREATE FUNCTION pokeshop.idempotency_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.scope, NEW.idempotency_key, NEW.request_sha256, NEW.created_at)
       IS DISTINCT FROM (OLD.scope, OLD.idempotency_key, OLD.request_sha256, OLD.created_at) THEN
        RAISE EXCEPTION 'clé d''idempotence %/% : identité et empreinte figées', OLD.scope, OLD.idempotency_key
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status <> 'EN_COURS' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'clé d''idempotence %/% : statut final %', OLD.scope, OLD.idempotency_key, OLD.status
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER idempotency_guard BEFORE UPDATE ON pokeshop.idempotency_keys
    FOR EACH ROW EXECUTE FUNCTION pokeshop.idempotency_guard();

CREATE FUNCTION pokeshop.claim_idempotency_key(p_scope text, p_key text, p_request_sha256 text) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    existing pokeshop.idempotency_keys%ROWTYPE;
BEGIN
    INSERT INTO pokeshop.idempotency_keys (scope, idempotency_key, request_sha256)
    VALUES (p_scope, p_key, p_request_sha256)
    ON CONFLICT (scope, idempotency_key) DO NOTHING;
    IF FOUND THEN
        RETURN 'NEW';
    END IF;
    SELECT * INTO existing FROM pokeshop.idempotency_keys WHERE scope = p_scope AND idempotency_key = p_key;
    IF existing.request_sha256 <> p_request_sha256 THEN
        RETURN 'CONFLICT';
    END IF;
    RETURN 'DUPLICATE_' || existing.status;
END $$;
COMMENT ON FUNCTION pokeshop.claim_idempotency_key(text, text, text) IS
    'NEW = exécuter ; DUPLICATE_EN_COURS / DUPLICATE_TERMINE / DUPLICATE_ECHEC = ne pas réécrire ; CONFLICT = même clé, autre requête.';

INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('002', 'integrity');

COMMIT;
