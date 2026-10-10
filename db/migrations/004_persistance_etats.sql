-- 004_persistance_etats.sql — états de sécurité persistés, incidents sans collision, hausse d'autonomie
-- vérifiée par la base (corrections de la revue adverse : MOT-01, SEC-01, E2E-01/02/03/06, SEC-02,
-- SEC-14, E2E-05, E2E-14, SEC-19). Référence : 5 octobre 2026.
--
-- * pokeshop.engine_state_journal : journal d'état **en ajout seul** de l'API du moteur, un flux par
--   composant (stoploss = verrou + journal + point zéro, stoploss_photo = dernière photo acceptée,
--   mandate_ledger = registre du mandat, northstar = étoile polaire, incidents = incidents et
--   confinements, price_history = historique des prix). La base impose la séquence continue et le
--   chaînage sha256 par flux et refuse UPDATE/DELETE/TRUNCATE : un redémarrage relit tout, un second
--   écrivain concurrent est refusé. Le moteur relit ces flux au démarrage (Services.build) ; un flux
--   illisible gèle le service (fermé par défaut).
-- * pokeshop.incidents : une référence d'incident (details->>'ref') est unique ; l'API refuse d'écraser
--   la ligne d'un autre incident.
-- * pokeshop.raise_autonomy : hausse du niveau d'autonomie par la propriétaire, utilisable avec le compte
--   de production (membre de pokeshop_engine) : SECURITY DEFINER (propriétaire pokeshop_owner), jeton
--   revérifié contre l'empreinte enregistrée par la propriétaire elle-même (pokeshop.owner_token_fingerprint),
--   un niveau à la fois.

BEGIN;

-- ------------------------------------------------------------ journal d'état

CREATE FUNCTION pokeshop.state_row_digest(p_prev text, p_seq bigint, p_body text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    -- Même formule que pokeshop.audit.state_row_digest : sha256(prev ␟ seq ␟ corps JSON canonique).
    SELECT encode(sha256(convert_to(concat_ws(E'\x1f', coalesce(p_prev, ''), p_seq::text, p_body), 'UTF8')), 'hex')
$$;

CREATE TABLE pokeshop.engine_state_journal (
    stream      text NOT NULL CHECK (stream ~ '^[a-z][a-z0-9_]{0,63}$'),
    seq         bigint NOT NULL CHECK (seq >= 1),
    prev_hash   char(64) CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
    row_hash    char(64) NOT NULL CHECK (row_hash ~ '^[0-9a-f]{64}$'),
    body        text NOT NULL CHECK (length(body) > 1),
    record      jsonb GENERATED ALWAYS AS (body::jsonb) STORED,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (stream, seq)
);
COMMENT ON TABLE pokeshop.engine_state_journal IS
    'États de sécurité du moteur (stop-loss, photo, mandat, étoile polaire, incidents, prix) : ajout seul, chaîné par flux.';

CREATE FUNCTION pokeshop.engine_state_journal_chain() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    last_seq  bigint;
    last_hash text;
BEGIN
    -- Un écrivain à la fois par flux : la ligne doit suivre exactement la précédente.
    PERFORM pg_advisory_xact_lock(hashtext('pokeshop.engine_state_journal:' || NEW.stream));
    SELECT j.seq, j.row_hash INTO last_seq, last_hash
      FROM pokeshop.engine_state_journal j WHERE j.stream = NEW.stream ORDER BY j.seq DESC LIMIT 1;
    IF NEW.seq <> coalesce(last_seq, 0) + 1 THEN
        RAISE EXCEPTION 'journal d''état % : séquence % refusée (% attendue) — autre écrivain ?', NEW.stream, NEW.seq,
            coalesce(last_seq, 0) + 1 USING ERRCODE = 'unique_violation';
    END IF;
    IF NEW.prev_hash IS DISTINCT FROM last_hash THEN
        RAISE EXCEPTION 'journal d''état % : chaînage rompu en %', NEW.stream, NEW.seq USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.row_hash <> pokeshop.state_row_digest(NEW.prev_hash, NEW.seq, NEW.body) THEN
        RAISE EXCEPTION 'journal d''état % : empreinte invalide en %', NEW.stream, NEW.seq USING ERRCODE = 'check_violation';
    END IF;
    NEW.recorded_at := clock_timestamp();
    RETURN NEW;
END $$;

CREATE TRIGGER engine_state_journal_chain BEFORE INSERT ON pokeshop.engine_state_journal
    FOR EACH ROW EXECUTE FUNCTION pokeshop.engine_state_journal_chain();
CREATE TRIGGER engine_state_journal_append_only BEFORE UPDATE OR DELETE ON pokeshop.engine_state_journal
    FOR EACH ROW EXECUTE FUNCTION pokeshop.forbid_change();
CREATE TRIGGER engine_state_journal_no_truncate BEFORE TRUNCATE ON pokeshop.engine_state_journal
    FOR EACH STATEMENT EXECUTE FUNCTION pokeshop.forbid_change();

CREATE FUNCTION pokeshop.verify_engine_state_journal() RETURNS TABLE (stream text, seq bigint, problem text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r        pokeshop.engine_state_journal%ROWTYPE;
    cur      text := NULL;
    prev     text := NULL;
    expected bigint := 1;
BEGIN
    FOR r IN SELECT * FROM pokeshop.engine_state_journal j ORDER BY j.stream, j.seq LOOP
        IF r.stream IS DISTINCT FROM cur THEN
            cur := r.stream; prev := NULL; expected := 1;
        END IF;
        IF r.seq <> expected THEN
            stream := r.stream; seq := r.seq; problem := format('séquence rompue : %s attendu', expected); RETURN NEXT;
        END IF;
        IF r.prev_hash IS DISTINCT FROM prev THEN
            stream := r.stream; seq := r.seq; problem := 'prev_hash incohérent'; RETURN NEXT;
        END IF;
        IF r.row_hash <> pokeshop.state_row_digest(r.prev_hash, r.seq, r.body) THEN
            stream := r.stream; seq := r.seq; problem := 'empreinte invalide (ligne modifiée)'; RETURN NEXT;
        END IF;
        prev := r.row_hash;
        expected := r.seq + 1;
    END LOOP;
END $$;
COMMENT ON FUNCTION pokeshop.verify_engine_state_journal() IS 'Aucune ligne renvoyée = journaux d''état intacts.';

-- --------------------------------------------------------------- incidents

-- Une référence INC-AAAAMMJJ-XXXXXXXX désigne un seul incident (les lignes sans référence restent admises).
CREATE UNIQUE INDEX incidents_ref_uq ON pokeshop.incidents ((details->>'ref'));

-- ------------------------------------------------- hausse d'autonomie vérifiée

CREATE TABLE pokeshop.owner_token_fingerprint (
    fingerprint_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_sha256   char(64) NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    set_by         text NOT NULL DEFAULT current_user,
    set_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE pokeshop.owner_token_fingerprint IS
    'Empreinte sha256 du jeton de la propriétaire, enregistrée par elle seule (compte membre de pokeshop_owner). Dernière ligne = en vigueur.';

CREATE FUNCTION pokeshop.owner_token_fingerprint_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT pokeshop.is_owner() THEN
        RAISE EXCEPTION 'empreinte du jeton propriétaire : enregistrement réservé à la propriétaire (pokeshop_owner)'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    NEW.set_by := current_user;
    NEW.set_at := clock_timestamp();
    RETURN NEW;
END $$;

CREATE TRIGGER owner_token_fingerprint_guard BEFORE INSERT ON pokeshop.owner_token_fingerprint
    FOR EACH ROW EXECUTE FUNCTION pokeshop.owner_token_fingerprint_guard();
CREATE TRIGGER owner_token_fingerprint_append_only BEFORE UPDATE OR DELETE ON pokeshop.owner_token_fingerprint
    FOR EACH ROW EXECUTE FUNCTION pokeshop.forbid_change();
CREATE TRIGGER owner_token_fingerprint_no_truncate BEFORE TRUNCATE ON pokeshop.owner_token_fingerprint
    FOR EACH STATEMENT EXECUTE FUNCTION pokeshop.forbid_change();

CREATE FUNCTION pokeshop.raise_autonomy(p_scope text, p_level integer, p_actor text, p_reason text, p_owner_token text)
RETURNS TABLE (previous_level smallint, at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pokeshop AS $$
DECLARE
    expected text;
    current_level integer;
BEGIN
    SELECT f.token_sha256 INTO expected FROM pokeshop.owner_token_fingerprint f ORDER BY f.fingerprint_id DESC LIMIT 1;
    IF expected IS NULL THEN
        RAISE EXCEPTION 'empreinte du jeton propriétaire non enregistrée en base (intervention de la propriétaire)'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_owner_token IS NULL OR length(p_owner_token) < 16
       OR encode(sha256(convert_to(p_owner_token, 'UTF8')), 'hex') <> expected THEN
        RAISE EXCEPTION 'jeton propriétaire refusé par la base' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0 OR p_actor IS NULL OR length(btrim(p_actor)) = 0 THEN
        RAISE EXCEPTION 'auteur et motif obligatoires' USING ERRCODE = 'check_violation';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('pokeshop.autonomy_levels:' || p_scope));
    SELECT a.level INTO current_level
      FROM pokeshop.autonomy_levels a WHERE a.scope = p_scope ORDER BY a.change_id DESC LIMIT 1;
    IF p_level <> coalesce(current_level, 1) + 1 THEN
        RAISE EXCEPTION 'niveau d''autonomie : un niveau à la fois (% -> % refusé)', coalesce(current_level, 1), p_level
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN QUERY
        INSERT INTO pokeshop.autonomy_levels AS a (scope, level, changed_by, changed_by_role, reason)
        VALUES (p_scope, p_level, p_actor, 'PROPRIETAIRE', p_reason)
        RETURNING a.previous_level, a.at;
END $$;
COMMENT ON FUNCTION pokeshop.raise_autonomy(text, integer, text, text, text) IS
    'Hausse d''un niveau par la propriétaire : jeton revérifié contre pokeshop.owner_token_fingerprint (jamais stocké).';

-- La fonction agit comme la propriétaire (current_user = pokeshop_owner => trigger autonomy_levels_guard satisfait).
ALTER FUNCTION pokeshop.raise_autonomy(text, integer, text, text, text) OWNER TO pokeshop_owner;

-- ------------------------------------------------------------------- droits

REVOKE ALL ON pokeshop.engine_state_journal, pokeshop.owner_token_fingerprint FROM PUBLIC;
REVOKE ALL ON FUNCTION pokeshop.state_row_digest(text, bigint, text), pokeshop.engine_state_journal_chain(),
    pokeshop.verify_engine_state_journal(), pokeshop.owner_token_fingerprint_guard(),
    pokeshop.raise_autonomy(text, integer, text, text, text) FROM PUBLIC;

-- Moteur : lecture et ajout du journal d'état (jamais de modification) ; aucune lecture de l'empreinte.
GRANT SELECT, INSERT ON pokeshop.engine_state_journal TO pokeshop_engine;
GRANT EXECUTE ON FUNCTION pokeshop.state_row_digest(text, bigint, text), pokeshop.verify_engine_state_journal(),
    pokeshop.raise_autonomy(text, integer, text, text, text) TO pokeshop_engine;

-- Propriétaire : enregistre son empreinte (ajout seul) ; la fonction de hausse la lit avec ses droits.
GRANT SELECT, INSERT ON pokeshop.owner_token_fingerprint TO pokeshop_owner;

INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('004', 'persistance_etats');

COMMIT;
