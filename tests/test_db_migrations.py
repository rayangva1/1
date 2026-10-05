"""Tests des migrations PostgreSQL : base jetable, migrations + seeds, garanties d'intégrité.

Le serveur local est démarré si nécessaire (``service postgresql start`` puis
``pg_ctlcluster 16 main start``). ``POKESHOP_TEST_PG_ADMIN_URL`` permet de viser un autre
serveur (compte superutilisateur). Sans serveur joignable, les tests sont ignorés avec la
raison exacte. Toutes les données sont FICTIVES.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from pokeshop.catalog import ExtensionTable, Language, ProductFormat, product_identity_key
from pokeshop.importers.base import ImportStatus, SourceKind
from pokeshop.models import AvailabilityStatus, DecisionStatus, MovementKind, PriceEventKind, ReservationStatus, VatMode

ROOT = Path(__file__).resolve().parents[1]
DB_DIR = ROOT / "db"
MIGRATIONS = sorted((DB_DIR / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
SEEDS = [DB_DIR / "seeds" / "reference_seed.sql", DB_DIR / "seeds" / "fictif_seed.sql"]
ADMIN_URL_ENV = "POKESHOP_TEST_PG_ADMIN_URL"

SPEC_TABLES = {
    "suppliers", "supplier_contacts", "raw_snapshots", "supplier_offers", "products", "product_supplier_links",
    "fx_rates", "cost_lots", "replacement_costs", "pricing_rules", "price_decisions", "stock_movements",
    "reservations", "preorder_allocations", "purchase_proposals", "orders", "order_lines", "incidents",
    "audit_log", "idempotency_keys", "autonomy_levels",
}
PUBLIC_COLUMNS = [
    "public_sku", "title", "description", "gtin", "language", "format", "extension_name", "content", "price_chf",
    "availability", "max_order_qty", "release_date", "release_date_confirmed", "image_urls", "updated_at",
]
FORBIDDEN_WORDS = (
    "cost", "cout", "coût", "margin", "marge", "contribution", "supplier", "fournisseur", "b2b", "purchase", "achat",
    "landed", "fx", "invoice", "facture", "customer", "client", "email", "phone", "address", "adresse", "floor",
    "plancher", "offer", "lot", "allocation", "reserved", "damaged", "safety", "on_hand",
)


# ----------------------------------------------------------------- serveur


class Postgres:
    """Exécute psql en superutilisateur (compte postgres local ou URL d'administration)."""

    def __init__(self) -> None:
        self.psql = shutil.which("psql")
        self.admin_url = os.environ.get(ADMIN_URL_ENV)
        self.prefix: list[str] = []
        if not self.admin_url and hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser"):
            self.prefix = ["runuser", "-u", "postgres", "--"]

    def _target(self, db: str) -> list[str]:
        if self.admin_url:
            url = re.sub(r"/[^/?]*(\?|$)", rf"/{db}\1", self.admin_url, count=1) if "://" in self.admin_url else self.admin_url
            return [url]
        return ["-d", db]

    def run(self, sql: str, db: str = "postgres", *, tuples: bool = True) -> subprocess.CompletedProcess[str]:
        assert self.psql is not None
        args = [*self.prefix, self.psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", *self._target(db)]
        if tuples:
            args += ["-A", "-t", "-F", "\t"]
        return subprocess.run(args + ["-f", "-"], input=sql, capture_output=True, text=True, timeout=120, check=False)

    def ready(self) -> bool:
        if self.psql is None:
            return False
        try:
            return self.run("SELECT 1;").returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def start(self) -> str:
        """Démarre le serveur local si possible ; renvoie un diagnostic."""
        attempts = []
        for cmd in (["service", "postgresql", "start"], ["pg_ctlcluster", "16", "main", "start"]):
            if shutil.which(cmd[0]) is None:
                attempts.append(f"{cmd[0]} absent")
                continue
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
                attempts.append(f"{' '.join(cmd)} -> {out.returncode} {out.stderr.strip()[:200]}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                attempts.append(f"{' '.join(cmd)} -> {exc}")
            for _ in range(30):
                if self.ready():
                    return "démarré"
                time.sleep(0.5)
        return " ; ".join(attempts)


@pytest.fixture(scope="module")
def pg() -> Postgres:
    server = Postgres()
    if server.psql is None:
        pytest.skip("psql introuvable : installer le client PostgreSQL 16")
    if not server.ready():
        diagnostic = server.start()
        if not server.ready():
            pytest.skip(f"PostgreSQL injoignable après tentative de démarrage : {diagnostic}")
    return server


def _apply(pg: Postgres, db: str, files: list[Path]) -> None:
    for path in files:
        out = pg.run(path.read_text(encoding="utf-8"), db, tuples=False)
        assert out.returncode == 0, f"{path.name} : {out.stderr}"


@pytest.fixture(scope="module")
def db(pg: Postgres) -> Iterator[str]:
    name = f"pokeshop_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    created = pg.run(f'CREATE DATABASE "{name}";')
    assert created.returncode == 0, created.stderr
    try:
        _apply(pg, name, MIGRATIONS + SEEDS)
        yield name
    finally:
        pg.run(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')


class Sql:
    """Petit client de test : requêtes en texte, erreurs attendues explicites."""

    def __init__(self, pg: Postgres, db: str) -> None:
        self.pg = pg
        self.db = db

    def __call__(self, query: str, *, role: str | None = None, fictif: bool = False) -> list[list[str]]:
        out = self.pg.run(self._wrap(query, role, fictif), self.db)
        assert out.returncode == 0, out.stderr
        return [line.split("\t") for line in out.stdout.splitlines() if line]

    def value(self, query: str, **kwargs: object) -> str:
        rows = self(query, **kwargs)  # type: ignore[arg-type]
        assert len(rows) == 1 and len(rows[0]) == 1, rows
        return rows[0][0]

    def error(self, query: str, *, role: str | None = None) -> str:
        out = self.pg.run(self._wrap(query, role, False), self.db)
        assert out.returncode != 0, f"erreur attendue, sortie : {out.stdout}"
        return out.stderr

    @staticmethod
    def _wrap(query: str, role: str | None, fictif: bool) -> str:
        head = ""
        if fictif:
            head += "SET pokeshop.include_fictif = 'on';\n"
        if role:
            head += f"SET ROLE {role};\n"
        return head + query


@pytest.fixture(scope="module")
def sql(pg: Postgres, db: str) -> Sql:
    return Sql(pg, db)


# ------------------------------------------------------------------- schéma


def _registered_name(path: Path) -> list[str]:
    match = re.search(r"INSERT INTO pokeshop\.schema_migrations \(version, name\) VALUES \('(\d{3})', '([a-z_]+)'\)",
                      path.read_text(encoding="utf-8"))
    assert match, path.name
    return [match.group(1), match.group(2)]


def test_migration_files_are_numbered_and_transactional() -> None:
    assert [p.name[:3] for p in MIGRATIONS] == [f"{i:03d}" for i in range(1, len(MIGRATIONS) + 1)]
    assert len(MIGRATIONS) >= 4  # 004 : persistance des états de sécurité
    for path in MIGRATIONS + SEEDS:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"^BEGIN;$", text, re.M) and re.search(r"^COMMIT;$", text, re.M), path.name
    for path in MIGRATIONS:
        assert f"VALUES ('{path.name[:3]}'," in path.read_text(encoding="utf-8")


def test_migrations_registered(sql: Sql) -> None:
    expected = [_registered_name(p) for p in MIGRATIONS]
    assert expected[:4] == [["001", "init"], ["002", "integrity"], ["003", "public_catalog"], ["004", "persistance_etats"]]
    assert sql("SELECT version, name FROM pokeshop.schema_migrations ORDER BY 1") == expected


def test_spec_tables_exist(sql: Sql) -> None:
    rows = sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'pokeshop' AND table_type = 'BASE TABLE'")
    tables = {r[0] for r in rows}
    assert SPEC_TABLES <= tables, SPEC_TABLES - tables
    assert {"schema_migrations", "extensions", "stock_levels", "price_events", "purchase_proposal_lines"} <= tables


@pytest.mark.parametrize(
    ("type_name", "python_values"),
    [
        ("language_code", [x.value for x in Language]),
        ("product_format", [x.value for x in ProductFormat]),
        ("availability_status", [x.value for x in AvailabilityStatus]),
        ("decision_status", [x.value for x in DecisionStatus]),
        ("movement_kind", [x.value for x in MovementKind]),
        ("reservation_status", [x.value for x in ReservationStatus]),
        ("price_event_kind", [x.value for x in PriceEventKind]),
        ("source_kind", [x.value for x in SourceKind]),
        ("import_status", [x.value for x in ImportStatus]),
        ("vat_mode", [x.value for x in VatMode]),
    ],
)
def test_enums_match_python(sql: Sql, type_name: str, python_values: list[str]) -> None:
    rows = sql(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid JOIN pg_namespace n ON n.oid = t.typnamespace "
        f"WHERE n.nspname = 'pokeshop' AND t.typname = '{type_name}' ORDER BY e.enumsortorder"
    )
    assert [r[0] for r in rows] == python_values


def test_reapplying_a_migration_fails_cleanly(pg: Postgres, db: str, sql: Sql) -> None:
    out = pg.run(MIGRATIONS[1].read_text(encoding="utf-8"), db, tuples=False)
    assert out.returncode != 0
    assert sql("SELECT count(*) FROM pokeshop.schema_migrations") == [[str(len(MIGRATIONS))]]


# --------------------------------------------------------------- append-only


def test_audit_log_append_only(sql: Sql) -> None:
    rows = sql(
        "BEGIN;"
        "INSERT INTO pokeshop.audit_log (actor, actor_kind, action, entity, payload) VALUES ('test', 'AGENT', 'test.insert', 'tests', '{\"fictif\": true}');"
        "SELECT count(*) FROM pokeshop.audit_log; ROLLBACK;"
    )
    assert rows == [["4"]]
    for stmt in (
        "UPDATE pokeshop.audit_log SET actor = 'pirate'",
        "DELETE FROM pokeshop.audit_log",
        "TRUNCATE pokeshop.audit_log",
        "TRUNCATE pokeshop.audit_log CASCADE",
    ):
        assert "append-only" in sql.error(stmt)


@pytest.mark.parametrize("table", ["stock_movements", "price_events", "price_decisions", "supplier_offers", "autonomy_levels"])
def test_other_journals_append_only(sql: Sql, table: str) -> None:
    assert "append-only" in sql.error(f"DELETE FROM pokeshop.{table}")
    assert "append-only" in sql.error(f"TRUNCATE pokeshop.{table} CASCADE")  # sans CASCADE : refus par clé étrangère
    col = {"stock_movements": "ref = 'x'", "price_events": "note = 'x'", "price_decisions": "actor = 'x'",
           "supplier_offers": "raw_ref = 'x'", "autonomy_levels": "reason = 'x'"}[table]
    assert "append-only" in sql.error(f"UPDATE pokeshop.{table} SET {col}")


def test_audit_chain_links_and_verifies(sql: Sql) -> None:
    rows = sql("SELECT chain_seq, prev_hash, row_hash FROM pokeshop.audit_log ORDER BY chain_seq")
    assert [r[0] for r in rows] == ["1", "2", "3"]
    assert rows[0][1] == ""  # NULL
    assert rows[1][1] == rows[0][2] and rows[2][1] == rows[1][2]
    assert sql("SELECT * FROM pokeshop.verify_audit_chain()") == []
    forged = sql(
        "BEGIN; INSERT INTO pokeshop.audit_log (actor, actor_kind, action, entity, chain_seq, prev_hash, row_hash, at) "
        "VALUES ('x', 'AGENT', 'a', 'e', 99, repeat('0', 64), repeat('f', 64), '2000-01-01');"
        "SELECT chain_seq, prev_hash = (SELECT row_hash FROM pokeshop.audit_log WHERE chain_seq = 3), at > '2026-01-01' "
        "FROM pokeshop.audit_log WHERE actor = 'x'; ROLLBACK;"
    )
    assert forged == [["4", "t", "t"]]  # séquence, chaînage et horodatage imposés par la base


def test_audit_chain_detects_tampering_by_superuser(sql: Sql) -> None:
    modified = sql(
        "BEGIN; SET LOCAL session_replication_role = replica;"
        "UPDATE pokeshop.audit_log SET payload = '{\"price_ttc_chf\": \"1.00\"}' WHERE chain_seq = 2;"
        "SELECT seq, problem FROM pokeshop.verify_audit_chain(); ROLLBACK;"
    )
    assert modified == [["2", "empreinte invalide (ligne modifiée)"]]
    deleted = sql(
        "BEGIN; SET LOCAL session_replication_role = replica; DELETE FROM pokeshop.audit_log WHERE chain_seq = 2;"
        "SELECT seq FROM pokeshop.verify_audit_chain(); ROLLBACK;"
    )
    assert deleted and all(r[0] == "3" for r in deleted)


# ----------------------------------------------------------------- vue publique


def test_public_view_exposes_only_public_columns(sql: Sql) -> None:
    rows = sql(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'storefront' AND table_name = 'public_catalog' "
        "ORDER BY ordinal_position"
    )
    columns = [r[0] for r in rows]
    assert columns == PUBLIC_COLUMNS
    for column in columns:
        for word in FORBIDDEN_WORDS:
            assert word not in column.lower(), (column, word)


def test_public_view_definition_reads_no_sensitive_source(sql: Sql) -> None:
    definition = " ".join(r[0] for r in sql("SELECT pg_get_viewdef('storefront.public_catalog'::regclass, true)")).lower()
    sensitive_tables = ("cost_lots", "supplier_offers", "price_decisions", "replacement_costs", "suppliers",
                        "supplier_contacts", "orders", "order_lines", "raw_snapshots", "fx_rates", "purchase_proposals")
    used = {r[0] for r in sql(
        "SELECT table_schema || '.' || table_name FROM information_schema.view_table_usage "
        "WHERE view_schema = 'storefront' AND view_name = 'public_catalog'"
    )}
    assert used == {f"pokeshop.{t}" for t in ("price_events", "preorder_allocations", "products", "stock_levels", "extensions")}
    used = {u.split(".", 1)[1] for u in used}
    assert not used & set(sensitive_tables)
    for word in ("unit_cost", "landed", "contribution", "margin", "price_b2b"):
        assert word not in definition, word
    assert "storefront" in sql.value("SELECT string_agg(nspname, ',') FROM pg_namespace WHERE nspname = 'storefront'")


def test_public_view_content(sql: Sql) -> None:
    assert sql("SELECT count(*) FROM storefront.public_catalog") == [["0"]]  # FICTIF jamais public
    # 005 : le réglage de session ne rouvre plus la vue publique (SEC-21) ; essais via la vue interne.
    assert sql("SELECT count(*) FROM storefront.public_catalog", fictif=True) == [["0"]]
    rows = sql(
        "SELECT public_sku, price_chf, availability, max_order_qty, language, extension_name FROM pokeshop.public_catalog_test ORDER BY 1",
    )
    assert rows == [
        ["FICTIF-DSP-ALPHA", "154.90", "LOCAL_STOCK", "2", "FR", "Extension Fictive Alpha"],
        ["FICTIF-DSP-GAMMA", "154.90", "PREORDER", "5", "FR", "Extension Fictive Gamma"],
        ["FICTIF-ETB-ALPHA", "69.90", "LOCAL_STOCK", "5", "FR", "Extension Fictive Alpha"],
        ["FICTIF-SLV-65", "7.90", "LOCAL_STOCK", "10", "NA", ""],
    ]


def test_supplier_stock_never_becomes_public_availability(sql: Sql) -> None:
    rows = sql(
        "BEGIN;"
        "INSERT INTO pokeshop.price_events (product_id, kind, price_ttc_chf, validated, actor, fictif) "
        "SELECT product_id, 'PUBLISHED', 13.90, true, 'test', true FROM pokeshop.products WHERE public_sku = 'FICTIF-TRI-BETA';"
        "INSERT INTO pokeshop.stock_levels (product_id) SELECT product_id FROM pokeshop.products WHERE public_sku = 'FICTIF-TRI-BETA';"
        "INSERT INTO pokeshop.preorder_allocations (product_id, supplier_id, firm_allocation_qty, fictif) "
        "SELECT product_id, 'fictif_grossiste_a', 500, true FROM pokeshop.products WHERE public_sku = 'FICTIF-TRI-BETA';"
        "SELECT availability, max_order_qty FROM pokeshop.public_catalog_test WHERE public_sku = 'FICTIF-TRI-BETA';"
        "ROLLBACK;",
    )
    assert rows == [["UNAVAILABLE", "0"]]  # stock local nul + allocation non écrite => indisponible


def test_rollback_price_is_the_displayed_price(sql: Sql) -> None:
    rows = sql(
        "SELECT kind, price_ttc_chf FROM pokeshop.price_events e JOIN pokeshop.products p USING (product_id) "
        "WHERE p.public_sku = 'FICTIF-DSP-ALPHA' ORDER BY event_id"
    )
    assert rows == [["PUBLISHED", "154.90"], ["PUBLISHED", "164.90"], ["ROLLED_BACK", "154.90"]]


# --------------------------------------------------------------------- rôles


def test_storefront_reader_sees_only_the_view(sql: Sql) -> None:
    # SEC-21 : même en posant pokeshop.include_fictif = 'on', le site public ne voit aucun produit FICTIF.
    assert sql("SELECT count(*) FROM storefront.public_catalog", role="storefront_reader", fictif=True) == [["0"]]
    assert "permission denied" in sql.error("SELECT * FROM pokeshop.public_catalog_test", role="storefront_reader")
    assert sql("SELECT count(*) FROM pokeshop.public_catalog_test", role="pokeshop_engine") == [["4"]]
    for table in ("supplier_offers", "cost_lots", "price_decisions", "suppliers", "supplier_contacts", "orders",
                  "products", "audit_log", "raw_snapshots"):
        assert "permission denied" in sql.error(f"SELECT * FROM pokeshop.{table} LIMIT 1", role="storefront_reader")
    assert "permission denied" in sql.error("SELECT * FROM pokeshop.verify_audit_chain()", role="storefront_reader")
    err = sql.error("INSERT INTO storefront.public_catalog (public_sku) VALUES ('X')", role="storefront_reader")
    assert "permission denied" in err or "cannot insert" in err


def test_engine_role_permissions(sql: Sql) -> None:
    assert sql("SELECT count(*) > 0 FROM pokeshop.supplier_offers", role="pokeshop_engine") == [["t"]]
    assert sql(
        "BEGIN; INSERT INTO pokeshop.audit_log (actor, actor_kind, action, entity) VALUES ('engine', 'SYSTEME', 'x', 'y');"
        "SELECT count(*) FROM pokeshop.audit_log; ROLLBACK;",
        role="pokeshop_engine",
    ) == [["4"]]
    assert "permission denied" in sql.error("UPDATE pokeshop.audit_log SET actor = 'x'", role="pokeshop_engine")
    assert "permission denied" in sql.error(
        "INSERT INTO pokeshop.schema_migrations (version, name) VALUES ('999', 'x')", role="pokeshop_engine"
    )


def test_only_owner_can_raise_autonomy(sql: Sql) -> None:
    raise_by_agent = "INSERT INTO pokeshop.autonomy_levels (level, changed_by, changed_by_role, reason) VALUES (2, 'agent', 'AGENT', 'x')"
    assert "autonomy_raise_by_owner_only" in sql.error(raise_by_agent)
    fake_owner = "INSERT INTO pokeshop.autonomy_levels (level, changed_by, changed_by_role, reason) VALUES (2, 'agent', 'PROPRIETAIRE', 'x')"
    assert "pokeshop_owner" in sql.error(fake_owner, role="pokeshop_engine")
    rows = sql(
        "BEGIN;"
        "INSERT INTO pokeshop.autonomy_levels (level, changed_by, changed_by_role, reason) VALUES (2, 'proprietaire', 'PROPRIETAIRE', 'recette OK');"
        "INSERT INTO pokeshop.autonomy_levels (level, changed_by, changed_by_role, reason) VALUES (1, 'stoploss', 'SYSTEME', 'stop-loss global');"
        "SELECT level, previous_level FROM pokeshop.autonomy_levels ORDER BY change_id;"
        "SELECT level FROM pokeshop.current_autonomy WHERE scope = 'global'; ROLLBACK;"
    )
    assert rows == [["1", ""], ["2", "1"], ["1", "2"], ["1"]]


def test_only_owner_can_validate_rules(sql: Sql) -> None:
    validate = (
        "UPDATE pokeshop.pricing_rules SET status = 'VALIDE', validated_by = 'x', validated_at = now() "
        "WHERE rules_version = 'v1-2026-10-04'"
    )
    assert "propriétaire" in sql.error(validate, role="pokeshop_engine")
    assert sql(f"BEGIN; {validate}; SELECT status FROM pokeshop.pricing_rules; ROLLBACK;") == [["VALIDE"]]
    assert "figé" in sql.error("UPDATE pokeshop.pricing_rules SET content = '{}'")
    assert "suppression interdite" in sql.error("DELETE FROM pokeshop.pricing_rules")


# --------------------------------------------------------------- contraintes


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, status, quarantine_reasons, price, source_ts, raw_ref) "
         "SELECT snapshot_id, 'fictif_grossiste_a', 'QUARANTAINE', '{X}', -1, now(), 'r' FROM pokeshop.raw_snapshots LIMIT 1", "check"),
        ("INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, status, supplier_sku, price, currency, price_includes_vat, "
         "units_per_pack, language, source_ts, raw_ref) SELECT snapshot_id, 'fictif_grossiste_a', 'VALIDE', 'S', 10, NULL, false, 1, 'FR', "
         "now(), 'r' FROM pokeshop.raw_snapshots LIMIT 1", "supplier_offers_valid_complete"),
        ("INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, status, supplier_sku, price, currency, price_includes_vat, "
         "units_per_pack, language, source_ts, raw_ref) SELECT snapshot_id, 'fictif_grossiste_a', 'VALIDE', 'S', 10, 'EUR', false, 1, "
         "'UNKNOWN', now(), 'r' FROM pokeshop.raw_snapshots LIMIT 1", "supplier_offers_valid_complete"),
        ("INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, status, source_ts, raw_ref) "
         "SELECT snapshot_id, 'fictif_grossiste_a', 'QUARANTAINE', now(), 'r' FROM pokeshop.raw_snapshots LIMIT 1",
         "supplier_offers_quarantine_reasons"),
        ("INSERT INTO pokeshop.supplier_offers (snapshot_id, supplier_id, status, quarantine_reasons, source_ts, raw_ref) "
         "VALUES (1, 'inconnu', 'QUARANTAINE', '{X}', now(), 'r')", "foreign key"),
        ("INSERT INTO pokeshop.products (language) VALUES ('XX')", "invalid input value for enum"),
        ("INSERT INTO pokeshop.products (gtin) VALUES ('123')", "check"),
        ("INSERT INTO pokeshop.products (status, language, format) VALUES ('PUBLIE', 'FR', 'DISPLAY')", "products_publishable"),
        ("INSERT INTO pokeshop.products (language, format) VALUES ('FR', 'SLEEVES')", "products_accessory_language"),
        ("INSERT INTO pokeshop.products (language, format) VALUES ('NA', 'DISPLAY')", "products_accessory_language"),
        ("INSERT INTO pokeshop.products (language, format, extension) VALUES ('FR', 'DISPLAY', 'SANS_EXTENSION')",
         "products_no_extension_only_accessories"),
        ("INSERT INTO pokeshop.products (gtin, language, extension, format, content, sealed, fictif) "
         "VALUES ('2000000005010', 'FR', 'FICTIF_ALPHA', 'DISPLAY', ' 36  boosters ', true, true)", "products_identity_key_complete"),
        ("INSERT INTO pokeshop.suppliers (supplier_id, name) VALUES ('fictif_x', 'X')", "suppliers_fictif_prefix"),
        ("INSERT INTO pokeshop.suppliers (supplier_id, name, access_mode) VALUES ('reel_x', 'X', 'API')", "suppliers_access_agreement"),
        ("INSERT INTO pokeshop.extensions (code, name_fr) VALUES ('ME99', 'Inventée')", "extensions_sourced"),
        ("INSERT INTO pokeshop.fx_rates (currency, rate_to_chf, source, rate_date) VALUES ('CHF', 1.1, 's', '2026-10-04')",
         "fx_rates_chf_is_one"),
        ("INSERT INTO pokeshop.fx_rates (currency, rate_to_chf, source, rate_date) VALUES ('EUR', 0, 's', '2026-10-04')", "check"),
        ("INSERT INTO pokeshop.preorder_allocations (product_id, supplier_id, firm_allocation_qty, committed_preorders) "
         "SELECT product_id, 'fictif_grossiste_a', 10, 2 FROM pokeshop.products LIMIT 1", "allocations_no_preorder_without_firm"),
        ("INSERT INTO pokeshop.preorder_allocations (product_id, supplier_id, firm_allocation_qty, confirmed_in_writing) "
         "SELECT product_id, 'fictif_grossiste_a', 10, true FROM pokeshop.products LIMIT 1", "allocations_evidence"),
        ("UPDATE pokeshop.stock_levels SET reserved = on_hand + 1", "stock_levels_physical"),
        ("INSERT INTO pokeshop.orders (shop_order_ref, paid_at, goods_ttc_chf, total_paid_ttc_chf) VALUES ('X', now(), 10, 12)",
         "orders_total"),
        ("INSERT INTO pokeshop.orders (shop_order_ref, paid_at, goods_ttc_chf, total_paid_ttc_chf, ship_to_country) "
         "VALUES ('X', now(), 10, 10, 'FR')", "check"),
        ("INSERT INTO pokeshop.orders (shop_order_ref, paid_at, goods_ttc_chf, total_paid_ttc_chf, currency) "
         "VALUES ('X', now(), 10, 10, 'EUR')", "check"),
        ("UPDATE pokeshop.purchase_proposals SET status = 'VALIDEE'", "proposals_validation"),
        ("UPDATE pokeshop.purchase_proposals SET requires_human_validation = false", "check"),
        ("UPDATE pokeshop.purchase_proposals SET total_cost_chf = budget_available_chf + 1", "proposals_within_budget"),
        ("INSERT INTO pokeshop.cost_lots (lot_id, product_id, received_at, qty, qty_remaining, unit_cost_chf, cost_basis) "
         "SELECT 'L', product_id, now(), 1, 2, 1, 'ESTIMATE' FROM pokeshop.products LIMIT 1", "cost_lots_remaining"),
        ("INSERT INTO pokeshop.cost_lots (lot_id, product_id, received_at, qty, qty_remaining, unit_cost_chf, cost_basis) "
         "SELECT 'L', product_id, now(), 1, 1, 1, 'INVOICE' FROM pokeshop.products LIMIT 1", "cost_lots_invoice"),
        ("INSERT INTO pokeshop.price_events (product_id, kind, price_ttc_chf, actor) "
         "SELECT product_id, 'PUBLISHED', 10, 'agent' FROM pokeshop.products LIMIT 1", "price_events_published_source"),
        ("INSERT INTO pokeshop.price_events (product_id, kind, price_ttc_chf, validated, actor) "
         "SELECT product_id, 'PUBLISHED', 0, true, 'agent' FROM pokeshop.products LIMIT 1", "check"),
        ("INSERT INTO pokeshop.incidents (kind, severity, scope, status, cause, proposed_action) "
         "VALUES ('X', 'MAJEUR', 'GLOBAL', 'RESOLU', 'c', 'a')", "incidents_resolution"),
        ("INSERT INTO pokeshop.product_supplier_links (product_id, supplier_id, supplier_sku, match_status) "
         "SELECT product_id, 'fictif_grossiste_a', 'NEW', 'CONFIRMED_BY_HUMAN' FROM pokeshop.products LIMIT 1", "links_human_confirmation"),
        ("INSERT INTO pokeshop.product_supplier_links (product_id, supplier_id, supplier_sku, match_status) "
         "SELECT product_id, 'fictif_grossiste_a', 'FICTIF-A-001', 'MATCHED' FROM pokeshop.products LIMIT 1", "duplicate key"),
        ("INSERT INTO pokeshop.reservations (reservation_id, product_id, order_id, qty, refunded_qty) "
         "SELECT 'R2', product_id, (SELECT order_id FROM pokeshop.orders LIMIT 1), 1, 2 FROM pokeshop.products "
         "WHERE public_sku = 'FICTIF-SLV-65'", "reservations_refund"),
        ("INSERT INTO pokeshop.raw_snapshots (supplier_id, source_kind, source_uri, fetched_at, checksum_sha256, byte_size, content) "
         "VALUES ('fictif_grossiste_a', 'CSV', 'x', now(), repeat('a', 64), 3, 'abc'::bytea)", "raw_snapshots_content_hash"),
    ],
)
def test_constraints(sql: Sql, statement: str, expected: str) -> None:
    err = sql.error(f"BEGIN; {statement}; ROLLBACK;")
    assert expected in err.lower() or expected in err, err


def test_identity_key_matches_python(sql: Sql) -> None:
    table = ExtensionTable.load([ROOT / "data" / "extensions_aliases.yaml", ROOT / "data" / "samples" / "FICTIF_extensions_aliases.yaml"])
    rows = sql(
        "SELECT coalesce(gtin, ''), language, coalesce(extension, ''), format, coalesce(content, ''), "
        "coalesce(sealed::text, ''), identity_key, identity_complete FROM pokeshop.products ORDER BY product_id"
    )
    assert len(rows) == 8
    for gtin, language, extension, fmt, content, sealed, key, complete in rows:
        python_key = product_identity_key(
            {"gtin": gtin or None, "language": language, "extension": extension or None, "format": fmt,
             "content": content or None, "sealed": {"true": True, "false": False}.get(sealed)},
            table,
        )
        assert key == python_key
        assert (complete == "t") == ("?" not in key and "|UNKNOWN|" not in key)


def test_identity_key_cannot_be_forged(sql: Sql) -> None:
    rows = sql(
        "BEGIN; INSERT INTO pokeshop.products (identity_key, language, format, fictif) VALUES ('forgé', 'FR', 'ETB', true) "
        "RETURNING identity_key, identity_complete; ROLLBACK;"
    )
    assert rows == [["?|FR|?|ETB|?|?", "f"]]


def test_order_is_frozen(sql: Sql) -> None:
    assert "figés" in sql.error("UPDATE pokeshop.order_lines SET unit_price_ttc_chf = 1")
    assert "figés" in sql.error("UPDATE pokeshop.order_lines SET qty = 2")
    assert "suppression interdite" in sql.error("DELETE FROM pokeshop.order_lines")
    assert "figés" in sql.error("UPDATE pokeshop.orders SET total_paid_ttc_chf = 1, goods_ttc_chf = 1, shipping_charged_ttc_chf = 0")
    assert "suppression interdite" in sql.error("DELETE FROM pokeshop.orders")
    rows = sql(
        "BEGIN; UPDATE pokeshop.order_lines SET unit_cost_chf = 103.5000; UPDATE pokeshop.orders SET status = 'EXPEDIEE';"
        "SELECT o.status, l.unit_cost_chf FROM pokeshop.orders o JOIN pokeshop.order_lines l USING (order_id); ROLLBACK;"
    )
    assert rows == [["EXPEDIEE", "103.5000"]]


def test_stock_version_compare_and_set(sql: Sql) -> None:
    rows = sql(
        "BEGIN;"
        "SELECT version FROM pokeshop.stock_levels s JOIN pokeshop.products p USING (product_id) WHERE public_sku = 'FICTIF-SLV-65';"
        "UPDATE pokeshop.stock_levels SET on_hand = on_hand - 1 WHERE version = 0 AND product_id = "
        "(SELECT product_id FROM pokeshop.products WHERE public_sku = 'FICTIF-SLV-65');"
        "SELECT version, on_hand FROM pokeshop.stock_levels s JOIN pokeshop.products p USING (product_id) WHERE public_sku = 'FICTIF-SLV-65';"
        "WITH u AS (UPDATE pokeshop.stock_levels SET on_hand = on_hand - 1 WHERE version = 0 AND product_id = "
        "(SELECT product_id FROM pokeshop.products WHERE public_sku = 'FICTIF-SLV-65') RETURNING 1) SELECT count(*) FROM u;"
        "ROLLBACK;"
    )
    assert rows == [["0"], ["1", "39"], ["0"]]  # la 2e écriture avec l'ancienne version ne touche rien


def test_idempotency_keys(sql: Sql) -> None:
    h1, h2 = "a" * 64, "b" * 64
    rows = sql(
        "BEGIN;"
        f"SELECT pokeshop.claim_idempotency_key('shopify.publish', 'FICTIF-key-0001', '{h1}');"
        f"SELECT pokeshop.claim_idempotency_key('shopify.publish', 'FICTIF-key-0001', '{h1}');"
        f"SELECT pokeshop.claim_idempotency_key('shopify.publish', 'FICTIF-key-0001', '{h2}');"
        "UPDATE pokeshop.idempotency_keys SET status = 'TERMINE', completed_at = now() WHERE idempotency_key = 'FICTIF-key-0001';"
        f"SELECT pokeshop.claim_idempotency_key('shopify.publish', 'FICTIF-key-0001', '{h1}');"
        "ROLLBACK;"
    )
    assert rows == [["NEW"], ["DUPLICATE_EN_COURS"], ["CONFLICT"], ["DUPLICATE_TERMINE"]]
    assert "figées" in sql.error(f"UPDATE pokeshop.idempotency_keys SET request_sha256 = '{h2}'")
    assert "statut final" in sql.error("UPDATE pokeshop.idempotency_keys SET status = 'ECHEC'")
    assert "idempotency_completion" in sql.error(
        f"BEGIN; INSERT INTO pokeshop.idempotency_keys (scope, idempotency_key, request_sha256, status) "
        f"VALUES ('s', 'FICTIF-key-0002', '{h1}', 'TERMINE'); ROLLBACK;"
    )


def test_raw_snapshot_is_frozen(sql: Sql) -> None:
    assert "figés" in sql.error("UPDATE pokeshop.raw_snapshots SET content = 'x'::bytea")
    assert "figés" in sql.error("UPDATE pokeshop.raw_snapshots SET source_ts = now()")
    assert "suppression interdite" in sql.error("DELETE FROM pokeshop.raw_snapshots")
    rows = sql(
        "BEGIN; UPDATE pokeshop.raw_snapshots SET import_status = 'ACCEPTED', report_md = '# FICTIF';"
        "SELECT import_status, encode(sha256(content), 'hex') = checksum_sha256 FROM pokeshop.raw_snapshots; ROLLBACK;"
    )
    assert rows == [["ACCEPTED", "t"]]


def test_updated_at_touch(sql: Sql) -> None:
    rows = sql(
        "BEGIN; SELECT updated_at < clock_timestamp() FROM pokeshop.suppliers WHERE supplier_id = 'fictif_grossiste_a';"
        "UPDATE pokeshop.suppliers SET status = 'SUSPENDU', updated_at = '2000-01-01' WHERE supplier_id = 'fictif_grossiste_a';"
        "SELECT updated_at > '2026-01-01' FROM pokeshop.suppliers WHERE supplier_id = 'fictif_grossiste_a'; ROLLBACK;"
    )
    assert rows == [["t"], ["t"]]


# -------------------------------------------------------------------- seeds


def test_reference_seed_matches_extension_table(sql: Sql) -> None:
    data = yaml.safe_load((ROOT / "data" / "extensions_aliases.yaml").read_text(encoding="utf-8"))
    expected = {e["code"]: (e["name_fr"], str(e["release_date_fr"]), sorted(s["url"] for s in e["sources"])) for e in data["extensions"]}
    rows = sql(
        "SELECT code, name_fr, release_date_fr, array_to_string(source_urls, ' ') FROM pokeshop.extensions "
        "WHERE NOT fictif AND code <> 'SANS_EXTENSION' ORDER BY code"
    )
    got = {code: (name, rel, sorted(urls.split(" "))) for code, name, rel, urls in rows}
    assert got == expected


def test_reference_suppliers_are_unconfirmed_leads(sql: Sql) -> None:
    rows = sql("SELECT supplier_id, status, access_mode, website FROM pokeshop.suppliers WHERE NOT fictif ORDER BY 1")
    assert [r[0] for r in rows] == ["asmodee_fr", "cardcosmos", "matoo_miao", "otakuworld", "tcg_distribution"]
    assert all(r[1] == "PISTE" and r[2] == "AUCUN" and r[3].startswith("https://") for r in rows)
    assert sql("SELECT count(*) FROM pokeshop.supplier_contacts c JOIN pokeshop.suppliers s USING (supplier_id) WHERE NOT s.fictif") == [["0"]]
    for sid in (r[0] for r in rows):
        assert (ROOT / "data" / "supplier_mappings" / f"{sid}.yaml").exists()


def test_fictif_seed_is_fully_flagged(sql: Sql) -> None:
    for table in ("supplier_offers", "products", "cost_lots", "price_decisions", "price_events", "orders",
                  "preorder_allocations", "purchase_proposals", "incidents", "fx_rates", "raw_snapshots", "replacement_costs"):
        assert sql(f"SELECT count(*) FROM pokeshop.{table} WHERE NOT fictif") == [["0"]], table
    gtins = sql("SELECT gtin FROM pokeshop.products WHERE gtin IS NOT NULL UNION SELECT gtin FROM pokeshop.supplier_offers WHERE gtin IS NOT NULL")
    assert gtins and all(g[0].startswith("200") for g in gtins)
    assert sql("SELECT count(*) FROM pokeshop.supplier_contacts WHERE value NOT LIKE '%.invalid'") == [["0"]]


def test_orders_hold_no_personal_data(sql: Sql) -> None:
    rows = sql("SELECT column_name FROM information_schema.columns WHERE table_schema = 'pokeshop' AND table_name IN ('orders', 'order_lines', 'reservations')")
    for (column,) in rows:
        for word in ("name", "nom", "email", "mail", "phone", "telephone", "address", "adresse", "street", "rue", "zip", "npa"):
            assert word not in column, column


def test_apply_script(pg: Postgres) -> None:
    if pg.admin_url or not pg.prefix:
        pytest.skip("test du script réservé au serveur local (compte postgres)")
    script = DB_DIR / "apply.sh"
    if not os.access(script, os.R_OK) or subprocess.run([*pg.prefix, "test", "-r", str(script)], check=False).returncode:
        pytest.skip("db/apply.sh illisible par le compte postgres")
    name = f"pokeshop_apply_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    assert pg.run(f'CREATE DATABASE "{name}";').returncode == 0
    try:
        env = ["env", f"DATABASE_URL=postgresql:///{name}"]
        first = subprocess.run([*pg.prefix, *env, "bash", str(script), "all"], capture_output=True, text=True, timeout=120, check=False)
        assert first.returncode == 0, first.stderr
        assert first.stdout.count("application :") == len(MIGRATIONS) and "fictif_seed.sql" in first.stdout
        again = subprocess.run([*pg.prefix, *env, "bash", str(script)], capture_output=True, text=True, timeout=120, check=False)
        assert again.returncode == 0 and again.stdout.count("déjà appliquée") == len(MIGRATIONS)
        bad = subprocess.run([*pg.prefix, *env, "bash", str(script), "tout"], capture_output=True, text=True, timeout=60, check=False)
        assert bad.returncode == 2
        assert pg.run("SELECT count(*) FROM pokeshop.products;", name).stdout.strip() == "8"
    finally:
        pg.run(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);')
