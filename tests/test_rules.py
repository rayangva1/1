"""Tests du chargement et de la validation des règles versionnées (``config/pricing_rules.vN.yaml``).

Valeurs = hypothèses BP §4-5 (FICTIVES tant que non confirmées par devis PSP/transporteur/fiduciaire).
"""

from __future__ import annotations

import copy
import hashlib
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pokeshop.errors import PokeshopError, RulesError
from pokeshop.models import DEFAULT_ROUNDING_TIERS, PricingParams, VatMode
from pokeshop.pricing import decide_price, floor_price
from pokeshop.rules import (
    DEFAULT_RULES_PATH,
    RULES_ENV_VAR,
    RuleSet,
    default_rules_path,
    load_all_profiles,
    load_rules,
    parse_rules,
    pricing_params,
    validate_rules_data,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="module")
def base_data() -> dict[str, Any]:
    with DEFAULT_RULES_PATH.open("rb") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def data(base_data) -> dict[str, Any]:
    return copy.deepcopy(base_data)


def write(tmp_path: Path, content: Any, name: str = "pricing_rules.test.yaml") -> Path:
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


# ======================================================== fichier livré


class TestShippedFile:
    def test_default_path_points_to_versioned_v1(self):
        assert DEFAULT_RULES_PATH == CONFIG_DIR / "pricing_rules.v1.yaml"
        assert DEFAULT_RULES_PATH.is_file()

    def test_every_shipped_rules_file_is_valid(self):
        files = sorted(CONFIG_DIR.glob("pricing_rules.*.yaml"))
        assert files, "aucun fichier de règles versionné"
        versions = set()
        for f in files:
            data = yaml.safe_load(f.read_bytes())
            assert validate_rules_data(data) == [], f
            versions.add(data["rules_version"])
        assert len(versions) == len(files), "deux fichiers portent le même rules_version"

    def test_shipped_file_has_no_float_literals(self):
        """Les montants et taux sont écrits entre guillemets (aucune conversion binaire)."""

        def walk(node: Any, where: str) -> None:
            assert not isinstance(node, float), f"flottant YAML non quoté : {where}"
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{where}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{where}[{i}]")

        walk(yaml.safe_load(DEFAULT_RULES_PATH.read_bytes()), "root")

    def test_metadata_marks_values_as_hypotheses(self):
        rs = load_rules()
        assert rs.rules_version == "v1-2026-10-04"
        assert "hypoth" in rs.status and "devis" in rs.status
        assert rs.effective_date == date(2026, 10, 4)
        assert "§4" in rs.source_ref
        raw = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
        assert "hypothèse BP §4" in raw

    @pytest.mark.parametrize(
        "field,expected",
        [
            ("payment_pct", D("0.025")),
            ("payment_fixed", D("0.30")),
            ("logistics_cost", D("3")),
            ("after_sales_provision", D("1")),
            ("acquisition_cost", D("5")),
            ("target_margin", D("0.20")),
            ("hard_floor_margin", D("0.12")),
            ("hard_floor_chf_per_order", D("8")),
            ("market_review_threshold", D("0.10")),
            ("max_daily_price_change", D("0.05")),
            ("price_anomaly_factor", D("10")),
        ],
    )
    def test_bp_values_identical_in_both_profiles(self, field, expected):
        profiles = load_all_profiles()
        for rs in profiles.values():
            assert getattr(rs.pricing, field) == expected

    def test_two_vat_profiles(self):
        profiles = load_all_profiles()
        assert set(profiles) == {VatMode.EFFECTIVE, VatMode.NOT_REGISTERED}
        eff, nreg = profiles[VatMode.EFFECTIVE], profiles[VatMode.NOT_REGISTERED]
        assert eff.pricing.vat_rate_sales == D("0.081") and eff.pricing.mode is VatMode.EFFECTIVE
        assert nreg.pricing.vat_rate_sales == D("0") and nreg.pricing.mode is VatMode.NOT_REGISTERED
        assert eff.profile is VatMode.EFFECTIVE and nreg.profile is VatMode.NOT_REGISTERED
        assert eff.rules_version == nreg.rules_version == eff.pricing.rules_version
        assert eff.content_sha256 == nreg.content_sha256

    def test_stock_parameters(self):
        rs = load_rules()
        assert rs.stock.staleness_hours == 24
        assert rs.stock.max_age.total_seconds() == 24 * 3600
        assert rs.stock.extension_budget_cap == D("0.25")
        assert rs.stock.stock_budget_chf == D("3000")

    def test_rounding_grid_and_small_product_rule(self):
        p = load_rules().pricing
        assert p.rounding_tiers == DEFAULT_ROUNDING_TIERS
        assert p.small_product_max_cost == D("15.00")
        # Fermé par défaut : aucun minimum de commande imposé par la boutique => règle inactive.
        assert p.small_product_min_order_ttc is None and p.small_product_max_shipping_ttc is None
        assert decide_price(D("3.79"), p).small_product is False
        assert decide_price(D("3.79"), p).recommended_price == D("23.90")

    def test_loaded_params_reproduce_bp_reference_cases(self):
        eff = pricing_params(VatMode.EFFECTIVE)
        nreg = pricing_params("NOT_REGISTERED")
        assert floor_price(D("140"), eff) == D("208.79")
        assert decide_price(D("140"), eff).recommended_price == D("209.90")
        assert floor_price(D("151.34"), nreg) == D("207.28")

    def test_content_sha256_is_file_hash(self):
        rs = load_rules()
        assert rs.content_sha256 == hashlib.sha256(DEFAULT_RULES_PATH.read_bytes()).hexdigest()
        assert rs.source_path == str(DEFAULT_RULES_PATH)

    def test_ruleset_is_frozen(self):
        rs = load_rules()
        with pytest.raises(ValidationError):
            rs.rules_version = "autre"  # type: ignore[misc]
        assert isinstance(rs, RuleSet)


# ======================================================== chemin / env


class TestPaths:
    def test_env_var_overrides_default_path(self, tmp_path, monkeypatch, data):
        data["rules_version"] = "v-env-test"
        path = write(tmp_path, data)
        monkeypatch.setenv(RULES_ENV_VAR, str(path))
        assert default_rules_path() == path
        assert load_rules().rules_version == "v-env-test"

    def test_without_env_var_uses_default(self, monkeypatch):
        monkeypatch.delenv(RULES_ENV_VAR, raising=False)
        assert default_rules_path() == DEFAULT_RULES_PATH

    def test_missing_file(self, tmp_path):
        with pytest.raises(RulesError, match="illisible"):
            load_rules(tmp_path / "absent.yaml")

    def test_invalid_yaml(self, tmp_path):
        path = write(tmp_path, "rules_version: [non fermé\n")
        with pytest.raises(RulesError, match="YAML invalide"):
            load_rules(path)

    @pytest.mark.parametrize("content", ["- a\n- b\n", "juste une chaîne\n", ""])
    def test_non_mapping_document(self, tmp_path, content):
        path = write(tmp_path, content)
        with pytest.raises(RulesError, match="mapping"):
            load_rules(path)
        with pytest.raises(RulesError, match="mapping"):
            load_all_profiles(path)

    def test_rules_error_is_value_error_and_pokeshop_error(self, tmp_path):
        with pytest.raises(ValueError):
            load_rules(tmp_path / "absent.yaml")
        with pytest.raises(PokeshopError):
            load_rules(tmp_path / "absent.yaml")

    def test_sha_changes_with_content(self, tmp_path, data):
        a = load_rules(write(tmp_path, data, "a.yaml"))
        data["pricing"]["acquisition_cost"] = "6.00"
        data["rules_version"] = "v1-bis"
        b = load_rules(write(tmp_path, data, "b.yaml"))
        assert a.content_sha256 != b.content_sha256
        assert b.pricing.acquisition_cost == D("6.00")


# ======================================================== validation


def mutate(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Affecte ``value`` au chemin pointé ``a.b.c`` (``__DEL__`` supprime la clé)."""
    node = data
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    if value == "__DEL__":
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return data


class TestValidation:
    def test_valid_document_has_no_errors(self, data):
        assert validate_rules_data(data) == []

    @pytest.mark.parametrize(
        "path,value,fragment",
        [
            # métadonnées
            ("rules_version", "__DEL__", "rules_version"),
            ("rules_version", "", "rules_version"),
            ("rules_version", "v 1", "rules_version"),
            ("rules_version", 1, "rules_version"),
            ("status", "__DEL__", "status"),
            ("status", "", "status"),
            ("source", 12, "source"),
            ("effective_date", "pas une date", "effective_date"),
            ("effective_date", "2026-13-01", "effective_date"),
            ("effective_date", 20261004, "effective_date"),
            ("typo_cle", "x", "clés inconnues"),
            # pricing requis / inconnus
            ("pricing.payment_pct", "__DEL__", "payment_pct manquant"),
            ("pricing.target_margin", "__DEL__", "target_margin manquant"),
            ("pricing.acquisition_cost", "__DEL__", "acquisition_cost manquant"),
            ("pricing.marge_cible", "0.2", "clés inconnues"),
            # valeurs non décimales
            ("pricing.payment_pct", "abc", "invalide"),
            ("pricing.payment_pct", True, "valeur décimale attendue"),
            ("pricing.payment_pct", None, "valeur décimale attendue"),
            ("pricing.logistics_cost", "NaN", "non finie"),
            ("pricing.logistics_cost", "Infinity", "non finie"),
            # taux / montants implausibles
            ("pricing.payment_pct", "0.25", "plage plausible"),
            ("pricing.payment_pct", "-0.01", "plage plausible"),
            ("pricing.payment_fixed", "30", "plage plausible"),
            ("pricing.target_margin", "0.9", "plage plausible"),
            ("pricing.target_margin", "0", "plage plausible"),
            ("pricing.acquisition_cost", "-1", "plage plausible"),
            ("pricing.max_daily_price_change", "0", "plage plausible"),
            ("pricing.price_anomaly_factor", "1", "plage plausible"),
            ("pricing.hard_floor_margin", "0.25", "plancher dur"),
            # profils
            ("profiles.EFFECTIVE.vat_rate_sales", "0.5", "plage plausible"),
            ("profiles.EFFECTIVE.vat_rate_sales", "0", "plage plausible"),
            ("profiles.EFFECTIVE.vat_rate_sales", "__DEL__", "vat_rate_sales manquant"),
            ("profiles.NOT_REGISTERED.vat_rate_sales", "0.081", "NOT_REGISTERED impose t = 0"),
            ("profiles.NOT_REGISTERED", "__DEL__", "profiles"),
            ("profiles.EFFECTIVE.inconnu", "1", "clés inconnues"),
            ("profiles.EFFECTIVE", "pas un mapping", "mapping attendu"),
            ("profiles", "__DEL__", "profiles"),
            ("pricing", "__DEL__", "pricing"),
            # grille d'arrondi
            ("pricing.rounding_tiers", [], "liste non vide"),
            ("pricing.rounding_tiers", "X.90", "liste non vide"),
            ("pricing.rounding_tiers", [{"min_price": "0", "step": "1"}], "clés attendues"),
            ("pricing.rounding_tiers", [{"min_price": "0", "step": "1", "endings": "0.90"}], "liste attendue"),
            ("pricing.rounding_tiers", [{"min_price": "0", "step": "1", "endings": ["1.20"]}], "terminaison"),
            ("pricing.rounding_tiers", [{"min_price": "5", "step": "1", "endings": ["0.90"]}], "commencer à 0"),
            ("pricing.rounding_tiers", [{"min_price": "0", "step": "x", "endings": ["0.90"]}], "invalide"),
            # stock
            ("stock.staleness_hours", 0, "stock.staleness_hours"),
            ("stock.staleness_hours", True, "valeur numérique attendue"),
            ("stock.extension_budget_cap", "1.5", "stock.extension_budget_cap"),
            ("stock.extension_budget_cap", None, "valeur numérique attendue"),
            ("stock.stock_budget_chf", "-1", "stock.stock_budget_chf"),
            ("stock.inconnu", 1, "clés inconnues"),
            ("stock", "pas un mapping", "stock : mapping attendu"),
        ],
    )
    def test_invalid_documents_rejected(self, data, path, value, fragment):
        mutate(data, path, value)
        errors = validate_rules_data(data)
        assert errors, f"{path}={value!r} aurait dû être refusé"
        assert any(fragment in e for e in errors), errors
        with pytest.raises(RulesError) as exc:
            parse_rules(data)
        assert exc.value.errors == tuple(errors)

    def test_non_mapping_root(self):
        assert validate_rules_data(["a"]) == ["document de règles : mapping YAML attendu"]
        assert validate_rules_data(None)

    def test_plausibility_bounds_keep_denominator_positive(self, data):
        """Pire coin des bornes : m = 60 %, t = 20 %, r = 10 % => (0.4/1.2) − 0.1 > 0 : accepté."""
        mutate(data, "pricing.target_margin", "0.60")
        mutate(data, "pricing.payment_pct", "0.10")
        mutate(data, "profiles.EFFECTIVE.vat_rate_sales", "0.20")
        assert validate_rules_data(data) == []
        rs = parse_rules(data)
        den = (1 - rs.pricing.target_margin) / (1 + rs.pricing.vat_rate_sales) - rs.pricing.payment_pct
        assert den > 0
        assert floor_price(D("100"), rs.pricing) > D("100")

    def test_denominator_check_reports_profile(self, data, monkeypatch):
        """Avec des bornes élargies, un dénominateur ≤ 0 est refusé et le profil nommé."""
        import pokeshop.rules as rules_mod

        bounds = dict(rules_mod._PRICING_BOUNDS)
        bounds["target_margin"] = (D("0.01"), D("0.99"))
        monkeypatch.setattr(rules_mod, "_PRICING_BOUNDS", bounds)
        mutate(data, "pricing.target_margin", "0.98")
        errors = validate_rules_data(data)
        assert any("EFFECTIVE : dénominateur" in e for e in errors)
        assert any("NOT_REGISTERED : dénominateur" in e for e in errors)
        with pytest.raises(RulesError, match="dénominateur"):
            parse_rules(data)

    def test_unquoted_yaml_floats_are_converted_via_str(self, tmp_path, data):
        mutate(data, "pricing.payment_pct", 0.025)
        mutate(data, "profiles.EFFECTIVE.vat_rate_sales", 0.081)
        mutate(data, "stock.extension_budget_cap", 0.1)
        rs = load_rules(write(tmp_path, data))
        assert rs.pricing.payment_pct == D("0.025")
        assert rs.pricing.vat_rate_sales == D("0.081")
        assert rs.stock.extension_budget_cap == D("0.1")

    def test_small_product_rule_activated_by_sufficient_shop_minimum(self, data):
        mutate(data, "pricing.small_product_min_order_ttc", "127.00")
        mutate(data, "pricing.small_product_max_shipping_ttc", "0")
        rs = parse_rules(data)
        assert decide_price(D("3.50"), rs.pricing).small_product is True
        mutate(data, "pricing.small_product_min_order_ttc", "60")  # minimum insuffisant : inactive
        assert decide_price(D("3.50"), parse_rules(data).pricing).small_product is False
        mutate(data, "pricing.small_product_min_order_ttc", "0.50")
        with pytest.raises(RulesError, match="small_product_min_order_ttc"):
            parse_rules(data)

    def test_small_product_rule_can_be_disabled(self, data):
        mutate(data, "pricing.small_product_max_cost", None)
        rs = parse_rules(data)
        assert rs.pricing.small_product_max_cost is None
        assert decide_price(D("3.50"), rs.pricing).small_product is False

    def test_optional_keys_take_model_defaults(self, data):
        for key in ("hard_floor_margin", "hard_floor_chf_per_order", "market_review_threshold", "rounding_tiers"):
            mutate(data, f"pricing.{key}", "__DEL__")
        rs = parse_rules(data)
        defaults = PricingParams.model_fields
        assert rs.pricing.hard_floor_margin == defaults["hard_floor_margin"].default
        assert rs.pricing.hard_floor_chf_per_order == defaults["hard_floor_chf_per_order"].default
        assert rs.pricing.rounding_tiers == DEFAULT_ROUNDING_TIERS

    def test_stock_section_optional(self, data):
        mutate(data, "stock", "__DEL__")
        rs = parse_rules(data)
        assert rs.stock.staleness_hours == 24

    def test_effective_date_as_yaml_date(self, data):
        mutate(data, "effective_date", date(2026, 10, 4))
        assert parse_rules(data).effective_date == date(2026, 10, 4)
        mutate(data, "effective_date", "__DEL__")
        assert parse_rules(data).effective_date is None


# ======================================================== profils


class TestProfiles:
    def test_profile_overrides_apply_to_one_profile_only(self, data):
        # Non assujetti : L, R, A saisis TTC (coûts supportés avec TVA non récupérable)
        data["profiles"]["NOT_REGISTERED"]["logistics_cost"] = "3.24"
        data["profiles"]["NOT_REGISTERED"]["acquisition_cost"] = "5.41"
        eff = parse_rules(data, VatMode.EFFECTIVE).pricing
        nreg = parse_rules(data, VatMode.NOT_REGISTERED).pricing
        assert eff.logistics_cost == D("3.00") and eff.acquisition_cost == D("5.00")
        assert nreg.logistics_cost == D("3.24") and nreg.acquisition_cost == D("5.41")

    def test_profile_override_is_validated(self, data):
        data["profiles"]["NOT_REGISTERED"]["payment_pct"] = "0.5"
        errors = validate_rules_data(data)
        assert any(e.startswith("NOT_REGISTERED.payment_pct") for e in errors)

    @pytest.mark.parametrize("profile", ["EFFECTIVE", "NOT_REGISTERED", VatMode.EFFECTIVE])
    def test_profile_by_name_or_enum(self, data, profile):
        assert parse_rules(data, profile).profile is VatMode(profile)

    def test_unknown_profile_name(self, data):
        with pytest.raises(ValueError):
            parse_rules(data, "FORFAIT")

    def test_description_not_leaking_into_params(self, data):
        rs = parse_rules(data, VatMode.EFFECTIVE)
        assert not hasattr(rs.pricing, "description")

    def test_rules_version_propagates_to_decisions(self, data):
        data["rules_version"] = "v2-test"
        params = parse_rules(data).pricing
        d = decide_price(D("140"), params)
        assert d.rules_version == "v2-test"
        assert params.rules_version == "v2-test"
