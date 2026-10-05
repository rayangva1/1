"""Jeu FICTIF de la base : les décisions de prix portent la version RÉELLE des règles qui les a calculées (COH-21).

Avant : ``fictif_seed.sql`` insérait une version « FICTIF-seed-v1 » partielle (ni paliers d'arrondi, ni
seuil marché, ni plafond de variation) alors que les décisions avaient été calculées avec
``config/pricing_rules.v1.yaml`` : la traçabilité « rules_version recopiée dans chaque décision »
(SPEC §2.1) était fausse. Ces tests n'ont pas besoin de PostgreSQL.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from pokeshop.models import VatMode
from pokeshop.pricing import decide_price
from pokeshop.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "db" / "seeds" / "fictif_seed.sql"
RULES = ROOT / "config" / "pricing_rules.v1.yaml"


def _generator() -> Any:
    spec = importlib.util.spec_from_file_location("regles_seed", ROOT / "db" / "seeds" / "regles_seed.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_blocks_are_up_to_date_with_the_rules_file() -> None:
    assert _generator().main(["--check"]) == 0, "relancer python db/seeds/regles_seed.py"


def test_seed_rules_row_is_the_complete_versioned_file() -> None:
    text = SEED.read_text(encoding="utf-8")
    rules = load_rules(RULES, VatMode.EFFECTIVE)
    assert "FICTIF-seed-v1" not in text, "aucune version de règles inventée"
    match = re.search(
        r"INSERT INTO pokeshop\.pricing_rules .*?VALUES \('([^']+)', 'PROPOSITION', NULL, '([^']+)', '([0-9a-f]{64})',\s*'(.*?)'::jsonb,\s*'([^']+)'",
        text,
        re.S,
    )
    assert match, "ligne pricing_rules introuvable"
    version, effective, sha, content, source = match.groups()
    assert version == rules.rules_version
    assert sha == hashlib.sha256(RULES.read_bytes()).hexdigest() == rules.content_sha256
    assert json.loads(content.replace("''", "'")) == yaml.safe_load(RULES.read_text(encoding="utf-8"))
    assert source == "config/pricing_rules.v1.yaml" and effective == str(rules.effective_date)
    # Toutes les références de version du seed pointent vers cette version (décisions, coûts, commande, proposition).
    assert set(re.findall(r"'(v\d[^']*)'", text)) == {rules.rules_version}


def test_seed_decisions_are_reproduced_by_the_engine_with_the_referenced_rules() -> None:
    text = SEED.read_text(encoding="utf-8")
    rules = load_rules(RULES, VatMode.EFFECTIVE)
    rows = re.findall(
        r"\('(FICTIF-[A-Z0-9-]+)', '([0-9a-f]{64})', '(OK|REVIEW|BLOCKED)', '\{([^}]*)\}'::text\[\],\s*"
        r"([\d.]+)::numeric, ([\d.]+)::numeric, ([\d.]+)::numeric, ([\d.-]+)::numeric, ([\d.-]+)::numeric\)",
        text,
    )
    assert len(rows) == 2
    markets = {"FICTIF-DSP-ALPHA": None, "FICTIF-ETB-ALPHA": Decimal("63.90")}
    for key, digest, status, reasons, cost, floor, reco, contrib, pct in rows:
        d = decide_price(Decimal(cost), rules.pricing, markets[key], None, [])
        assert d.rules_version == rules.rules_version
        assert (d.inputs_hash, d.status.value) == (digest, status), key
        assert tuple(r for r in reasons.split(",") if r) == tuple(str(getattr(r, "value", r)) for r in d.reasons)
        assert (d.floor_price, d.recommended_price) == (Decimal(floor), Decimal(reco))
        assert (d.contribution_chf, d.contribution_pct) == (Decimal(contrib), Decimal(pct))


def test_regenerating_a_stale_seed_restores_it(tmp_path: Path, monkeypatch: Any) -> None:
    gen = _generator()
    stale = tmp_path / "fictif_seed.sql"
    stale.write_text(SEED.read_text(encoding="utf-8").replace(load_rules(RULES, VatMode.EFFECTIVE).rules_version, "v0-perime"),
                     encoding="utf-8")
    monkeypatch.setattr(gen, "SEED", stale)
    assert gen.main(["--check"]) == 1
    assert gen.main([]) == 0
    assert gen.main(["--check"]) == 0
    assert stale.read_text(encoding="utf-8") == SEED.read_text(encoding="utf-8")
