"""Chargement et validation des règles de prix/stock versionnées (``config/pricing_rules.vN.yaml``).

Le fichier porte un ``rules_version`` recopié dans chaque décision, et deux profils TVA
(BP §4) : ``EFFECTIVE`` (t = 8,1 %) et ``NOT_REGISTERED`` (t = 0). Un profil peut surcharger
n'importe quelle clé de ``pricing`` (ex. L, R, A saisis TTC en non-assujetti).

La validation refuse : clé inconnue (faute de frappe), valeur non décimale ou booléenne,
taux implausible, plancher dur > cible, dénominateur ``(1 − m)/(1 + t) − r`` ≤ 0 pour un
profil, profil manquant. Les flottants YAML sont convertis via ``str`` (jamais via binaire),
mais les montants doivent être écrits entre guillemets.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import RulesError
from .models import FrozenModel, PricingParams, RoundingTier, StockParams, VatMode

__all__ = [
    "RULES_ENV_VAR",
    "DEFAULT_RULES_PATH",
    "RuleSet",
    "default_rules_path",
    "validate_rules_data",
    "parse_rules",
    "load_rules",
    "load_all_profiles",
    "pricing_params",
]

RULES_ENV_VAR = "POKESHOP_RULES_PATH"
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "pricing_rules.v1.yaml"

_VERSION_RE = re.compile(r"^\S{1,64}$")
_TOP_KEYS = {"rules_version", "status", "source", "effective_date", "profiles", "pricing", "stock"}
_PROFILE_KEYS = {"description", "vat_rate_sales"}
_REQUIRED_PRICING = (
    "payment_pct",
    "payment_fixed",
    "logistics_cost",
    "after_sales_provision",
    "acquisition_cost",
    "target_margin",
)
# clé -> (min inclus, max inclus) de plausibilité ; None = pas de borne
_PRICING_BOUNDS: dict[str, tuple[Decimal, Decimal]] = {
    "payment_pct": (Decimal("0"), Decimal("0.10")),
    "payment_fixed": (Decimal("0"), Decimal("5")),
    "logistics_cost": (Decimal("0"), Decimal("100")),
    "after_sales_provision": (Decimal("0"), Decimal("100")),
    "acquisition_cost": (Decimal("0"), Decimal("200")),
    "target_margin": (Decimal("0.01"), Decimal("0.60")),
    "hard_floor_margin": (Decimal("0"), Decimal("0.60")),
    "hard_floor_chf_per_order": (Decimal("0"), Decimal("100")),
    "market_review_threshold": (Decimal("0"), Decimal("1")),
    "max_daily_price_change": (Decimal("0.001"), Decimal("0.50")),
    "price_anomaly_factor": (Decimal("1.5"), Decimal("1000")),
    "small_product_max_cost": (Decimal("0"), Decimal("500")),
    "small_product_min_order_ttc": (Decimal("1"), Decimal("1000")),
    "small_product_max_shipping_ttc": (Decimal("0"), Decimal("100")),
}
_OPTIONAL_PRICING = set(_PRICING_BOUNDS) - set(_REQUIRED_PRICING) | {"rounding_tiers"}
_NULLABLE_PRICING = {"small_product_max_cost", "small_product_min_order_ttc", "small_product_max_shipping_ttc"}
"""Clés dont la valeur ``null`` désactive une règle (petits produits)."""
_STOCK_KEYS = set(StockParams.model_fields)
_VAT_EFFECTIVE_BOUNDS = (Decimal("0.001"), Decimal("0.20"))


class RuleSet(FrozenModel):
    """Règles chargées pour un profil TVA donné."""

    rules_version: str
    profile: VatMode
    status: str
    pricing: PricingParams
    stock: StockParams
    source_path: str
    content_sha256: str
    """sha256 du fichier brut (vide si chargé depuis la mémoire) : preuve de la version appliquée."""
    effective_date: date | None = None
    source_ref: str = ""
    """Référence documentaire des valeurs (ex. « BP §4-5 »)."""


def default_rules_path() -> Path:
    """Chemin des règles : variable ``POKESHOP_RULES_PATH`` sinon ``config/pricing_rules.v1.yaml``."""
    env = os.environ.get(RULES_ENV_VAR)
    return Path(env) if env else DEFAULT_RULES_PATH


def _dec(value: Any, where: str, errors: list[str]) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        errors.append(f"{where} : valeur décimale attendue (reçu {value!r})")
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        errors.append(f"{where} : valeur décimale invalide {value!r}")
        return None
    if not result.is_finite():
        errors.append(f"{where} : valeur non finie")
        return None
    return result


def _bounded(value: Decimal, lo: Decimal, hi: Decimal, where: str, errors: list[str]) -> None:
    if not lo <= value <= hi:
        errors.append(f"{where} = {value} hors de la plage plausible [{lo}, {hi}]")


def _profile_pricing(data: Mapping[str, Any], profile: VatMode) -> dict[str, Any]:
    base = dict(data.get("pricing") or {})
    overrides = dict((data.get("profiles") or {}).get(profile.value) or {})
    overrides.pop("description", None)
    base.update(overrides)
    return base


def _rounding(raw: Any, errors: list[str]) -> tuple[RoundingTier, ...] | None:
    if not isinstance(raw, list) or not raw:
        errors.append("pricing.rounding_tiers : liste non vide attendue")
        return None
    tiers = []
    for i, item in enumerate(raw):
        where = f"pricing.rounding_tiers[{i}]"
        if not isinstance(item, Mapping) or set(item) != {"min_price", "step", "endings"}:
            errors.append(f"{where} : clés attendues min_price, step, endings")
            return None
        mn = _dec(item["min_price"], f"{where}.min_price", errors)
        st = _dec(item["step"], f"{where}.step", errors)
        endings_raw = item["endings"]
        if not isinstance(endings_raw, list):
            errors.append(f"{where}.endings : liste attendue")
            return None
        endings = [_dec(e, f"{where}.endings", errors) for e in endings_raw]
        if mn is None or st is None or any(e is None for e in endings):
            return None
        try:
            tiers.append(RoundingTier(min_price=mn, step=st, endings=tuple(e for e in endings if e is not None)))
        except ValidationError as exc:
            errors.append(f"{where} : {exc.errors()[0]['msg']}")
            return None
    return tuple(tiers)


def _build_pricing(data: Mapping[str, Any], profile: VatMode, errors: list[str]) -> PricingParams | None:
    raw = _profile_pricing(data, profile)
    fields: dict[str, Any] = {"vat_mode": profile, "rules_version": str(data.get("rules_version", ""))}
    n_errors = len(errors)
    for key, value in raw.items():
        where = f"{profile.value}.{key}"
        if key == "rounding_tiers":
            tiers = _rounding(value, errors)
            if tiers is not None:
                fields["rounding_tiers"] = tiers
            continue
        if key in _NULLABLE_PRICING and value is None:
            fields[key] = None
            continue
        dec = _dec(value, where, errors)
        if dec is None:
            continue
        if key == "vat_rate_sales":
            if profile is VatMode.NOT_REGISTERED and dec != 0:
                errors.append(f"{where} : NOT_REGISTERED impose t = 0 (BP §4)")
            if profile is VatMode.EFFECTIVE:
                _bounded(dec, *_VAT_EFFECTIVE_BOUNDS, where, errors)
        elif key in _PRICING_BOUNDS:
            _bounded(dec, *_PRICING_BOUNDS[key], where, errors)
        fields[key] = dec
    if "vat_rate_sales" not in fields:
        errors.append(f"profiles.{profile.value}.vat_rate_sales manquant")
    if len(errors) > n_errors:
        return None
    t, m, r = fields["vat_rate_sales"], fields["target_margin"], fields["payment_pct"]
    den = (1 - m) / (1 + t) - r
    if den <= 0:
        errors.append(f"{profile.value} : dénominateur (1 − m)/(1 + t) − r = {den} ≤ 0")
        return None
    try:
        return PricingParams(**fields)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "pricing"
            errors.append(f"{profile.value}.{loc} : {err['msg']}")
        return None


def validate_rules_data(data: Any) -> list[str]:
    """Liste des erreurs (en français) d'un document de règles ; vide si valide."""
    errors: list[str] = []
    if not isinstance(data, Mapping):
        return ["document de règles : mapping YAML attendu"]
    unknown_top = set(data) - _TOP_KEYS
    if unknown_top:
        errors.append(f"clés inconnues : {', '.join(sorted(map(str, unknown_top)))}")
    version = data.get("rules_version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        errors.append("rules_version : chaîne non vide sans espace obligatoire")
    if not isinstance(data.get("status"), str) or not data.get("status"):
        errors.append("status : mention d'hypothèse obligatoire")
    if "source" in data and not isinstance(data["source"], str):
        errors.append("source : chaîne attendue")
    if "effective_date" in data:
        eff = data["effective_date"]
        if isinstance(eff, str):
            try:
                date.fromisoformat(eff)
            except ValueError:
                errors.append(f"effective_date : date ISO AAAA-MM-JJ attendue (reçu {eff!r})")
        elif not isinstance(eff, date) or isinstance(eff, datetime):
            errors.append(f"effective_date : date ISO AAAA-MM-JJ attendue (reçu {eff!r})")
    pricing = data.get("pricing")
    if not isinstance(pricing, Mapping):
        errors.append("pricing : section manquante")
    else:
        for key in _REQUIRED_PRICING:
            if key not in pricing:
                errors.append(f"pricing.{key} manquant")
        unknown = set(pricing) - set(_REQUIRED_PRICING) - _OPTIONAL_PRICING
        if unknown:
            errors.append(f"pricing : clés inconnues {', '.join(sorted(map(str, unknown)))}")
    profiles = data.get("profiles")
    if not isinstance(profiles, Mapping):
        errors.append("profiles : section manquante")
    else:
        names = set(map(str, profiles))
        expected = {m.value for m in VatMode}
        if names != expected:
            errors.append(f"profiles : attendus exactement {sorted(expected)}, reçus {sorted(names)}")
        for name, body in profiles.items():
            if not isinstance(body, Mapping):
                errors.append(f"profiles.{name} : mapping attendu")
                continue
            extra = set(body) - _PROFILE_KEYS - set(_REQUIRED_PRICING) - _OPTIONAL_PRICING
            if extra:
                errors.append(f"profiles.{name} : clés inconnues {', '.join(sorted(map(str, extra)))}")
    stock = data.get("stock", {})
    if not isinstance(stock, Mapping):
        errors.append("stock : mapping attendu")
    else:
        unknown_stock = set(stock) - _STOCK_KEYS
        if unknown_stock:
            errors.append(f"stock : clés inconnues {', '.join(sorted(map(str, unknown_stock)))}")
        for key, value in stock.items():
            if isinstance(value, bool) or value is None:
                errors.append(f"stock.{key} : valeur numérique attendue (reçu {value!r})")
        try:
            StockParams(**{k: v for k, v in stock.items() if k in _STOCK_KEYS})
        except ValidationError as exc:
            for err in exc.errors():
                errors.append(f"stock.{'.'.join(str(p) for p in err['loc'])} : {err['msg']}")
    if errors:
        return errors
    for mode in VatMode:
        _build_pricing(data, mode, errors)
    return errors


def parse_rules(
    data: Mapping[str, Any],
    profile: VatMode | str = VatMode.EFFECTIVE,
    *,
    source: str = "<memory>",
    content_sha256: str = "",
) -> RuleSet:
    """Valide puis construit le :class:`RuleSet` d'un profil ; RulesError si invalide."""
    mode = VatMode(profile)
    errors = validate_rules_data(data)
    if errors:
        raise RulesError(errors)
    pricing = _build_pricing(data, mode, errors)
    if pricing is None:  # pragma: no cover - déjà couvert par validate_rules_data
        raise RulesError(errors)
    return RuleSet(
        rules_version=str(data["rules_version"]),
        profile=mode,
        status=str(data["status"]),
        pricing=pricing,
        stock=StockParams(**dict(data.get("stock") or {})),
        source_path=source,
        content_sha256=content_sha256,
        effective_date=_as_date(data.get("effective_date")),
        source_ref=str(data.get("source") or ""),
    )


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _read(path: str | Path | None) -> tuple[Mapping[str, Any], Path, str]:
    target = Path(path) if path is not None else default_rules_path()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise RulesError(f"fichier de règles illisible : {target} ({exc.strerror})") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RulesError(f"YAML invalide : {target}") from exc
    return data, target, hashlib.sha256(raw).hexdigest()


def load_rules(path: str | Path | None = None, profile: VatMode | str = VatMode.EFFECTIVE) -> RuleSet:
    """Charge et valide le fichier de règles pour un profil TVA (EFFECTIVE par défaut)."""
    data, target, sha = _read(path)
    if not isinstance(data, Mapping):
        raise RulesError("document de règles : mapping YAML attendu")
    return parse_rules(data, profile, source=str(target), content_sha256=sha)


def load_all_profiles(path: str | Path | None = None) -> dict[VatMode, RuleSet]:
    """Charge les deux profils TVA du même fichier (même ``rules_version`` et même sha256)."""
    data, target, sha = _read(path)
    if not isinstance(data, Mapping):
        raise RulesError("document de règles : mapping YAML attendu")
    return {mode: parse_rules(data, mode, source=str(target), content_sha256=sha) for mode in VatMode}


def pricing_params(profile: VatMode | str = VatMode.EFFECTIVE, path: str | Path | None = None) -> PricingParams:
    """Raccourci : paramètres de prix du profil demandé."""
    return load_rules(path, profile).pricing
