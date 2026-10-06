"""Pré-drop (décision de la propriétaire du 6.10.2026) : réservation GARANTIE avant réception.

Couvre le moteur (:mod:`pokeshop.predrop`) et l'API :

* prix : prix drop du moteur inchangé, supplément, arrondi retail, plafond 10 % (configuré et effectif), plafond de la
  référence marché, marge revérifiée ;
* paramètres signés (empreinte au coffre) : non signés, modifiés ou hors bornes => pré-drop désactivé ;
* éligibilité : chaque condition (signature, allocation ferme, quota, demande, fiche validée, coût, prix, marché,
  stop-loss, quarantaine) ;
* quotas, course concurrente sur la dernière unité, limite par client (identifiant haché), fenêtre prioritaire,
  idempotence, persistance au redémarrage ;
* réduction d'allocation (pré-drop servi en premier, quota drop réduit d'abord, remboursements des dernières
  réservations, validation de la propriétaire selon le niveau d'autonomie) ;
* dettes dérivées dans la photo du stop-loss, chiffre d'affaires reconnu à l'expédition ;
* matrice d'autorisations (jeton commun refusé, rôles), aucune donnée personnelle, aucune fausse urgence.

Données, jetons, montants et identifiants FICTIFS.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import jetons_roles as JR
import pytest
import test_orchestration_f4 as F
import yaml
from pokeshop import authz
from pokeshop.api import OWNER_TOKEN_HEADER
from pokeshop.audit import InMemoryStateJournal
from pokeshop.models import ReplacementCost
from pokeshop.predrop import (
    AUTO_REFUND_MIN_LEVEL,
    DEFAULT_PREDROP_PATH,
    GUARANTEE_TEXT_FR,
    MAX_PREMIUM_PCT,
    NO_DIFFERENCE_REFUND_FR,
    PUBLIC_OFFER_FIELDS,
    STATUS_CLOSED_FR,
    STATUS_OPEN_FR,
    DemandSignal,
    FirmAllocation,
    Predrop,
    PredropError,
    PredropPersistenceError,
    PredropRegistry,
    compute_prices,
    evaluate_eligibility,
    load_predrop_config,
    main,
    parse_predrop_config,
    plan_service,
    predrop_fingerprint,
    public_offer,
    reserve_units,
    round_down_retail,
    split_quota,
    validate_predrop_data,
)
from pokeshop.pricing import decide_price, price_floor_violations, round_up_retail
from pokeshop.rules import load_rules

NOW = F.NOW
TZ = F.TZ
H = F.H  # jeton commun
OWNER = {OWNER_TOKEN_HEADER: F.OWNER_TOKEN}
HO = F.HO
P1 = "FICTIF-P1"
SUPPLIER = "fictif_grossiste_a"
DROP = date(2026, 10, 20)
PID = f"PD-{P1}-20261020"
PARAMS = load_rules().pricing
RAW = yaml.safe_load(DEFAULT_PREDROP_PATH.read_text(encoding="utf-8"))


def body(resp: Any) -> Any:
    return json.loads(resp.content)


def cref(name: str) -> str:
    """Identifiant client haché par la boutique (FICTIF) : jamais l'email."""
    return hashlib.sha256(f"FICTIF-client-{name}".encode()).hexdigest()


def write_config(tmp_path: Path, **overrides: Any) -> tuple[Path, str]:
    data = {**RAW, **overrides}
    path = tmp_path / "predrop.test.yaml"
    tmp_path.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    try:
        return path, predrop_fingerprint(data)
    except PredropError:  # contenu non canonisable (flottant YAML) : aucune empreinte possible
        return path, "0" * 64


def boot(tmp_path: Path, *, signed: bool = True, clock: F.Clock | None = None, **overrides: Any) -> tuple[Any, Any, F.Clock]:
    """API FICTIVE ; paramètres du pré-drop signés (fenêtre prioritaire 0 h par défaut dans ces tests)."""
    overrides.setdefault("priority_window_hours", 0)
    path, fingerprint = write_config(tmp_path, **overrides)
    env = {"POKESHOP_PREDROP_PATH": str(path)}
    if signed:
        env["POKESHOP_PREDROP_FINGERPRINT"] = fingerprint
    return F.boot(tmp_path, clock, **env)


def offer_cost(svc: Any, unit_cost: str = "140", *, age: timedelta = timedelta(hours=1)) -> None:
    """Coût rendu évalué par le moteur (comme après un cycle 01) pour le fournisseur de l'allocation."""
    svc.sync.replacement_costs.update(ReplacementCost(
        product_key=P1, supplier_id=SUPPLIER, unit_cost=D(unit_cost), source_ts=NOW - age,
        offer_ref="FICTIF-OFFRE-PD", fees_recorded_by="propriétaire"))  # fmt: skip


def catalog(client: Any, *, approve: bool = True) -> None:
    item = {"product_id": P1, "listing": F.LISTING, "supplier_links": [{"supplier_id": SUPPLIER, "supplier_sku": "FICTIF-SKU-1"}]}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [item]}).status_code == 200
    if approve:
        ok = client.post("/catalog/approvals", headers=OWNER,
                         json={"product_id": P1, "approved": True, "reason": "fiche FICTIVE relue par la propriétaire"})
        assert ok.status_code == 201, ok.text


def allocation(client: Any, qty: int = 10, ref: str = "FICTIF-CONF-1", headers: dict[str, str] | None = None) -> Any:
    payload = {"product_key": P1, "supplier_id": SUPPLIER, "qty": qty, "supplier_confirmation_ref": ref,
               "expected_delivery": "2026-10-15", "source": "confirmation fournisseur FICTIVE validée (workflow 03)"}
    return client.post("/predrop/allocations", headers=headers or JR.headers("n8n-03-factures"), json=payload)


def demand(client: Any, count: int = 10, at: datetime | None = None) -> Any:
    payload = {"product_key": P1, "interested_consenting_subscribers": count, "as_of": (at or NOW - timedelta(hours=1)).isoformat(),
               "source": "liste d'alertes FICTIVE (consentement explicite)"}
    return client.post("/predrop/demand", headers=JR.headers("n8n-06-marketing"), json=payload)


def photo(client: Any, at: datetime | None = None, *, capital: bool = True, bank: str = "2000.00") -> Any:
    """Photo du stop-loss construite par le moteur (apport, soldes, dettes déclarées hors pré-drop).

    ``bank`` : solde bancaire relevé — l'argent encaissé en pré-drop y est (et reste une dette jusqu'à l'expédition).
    """
    at = at or NOW
    if capital:
        movement = {"movement_id": "FICTIF-APPORT-1", "at": (NOW - timedelta(days=30)).isoformat(), "kind": "CONTRIBUTION",
                    "amount": "4200", "ref": "virement FICTIF"}
        assert client.post("/capital/movements", headers=HO, json=movement).status_code in (200, 201)
    for route, value in (("/treasury/paypal-balance", "1500"), ("/treasury/bank-balance", bank)):
        reading = {"as_of": (at - timedelta(minutes=10)).isoformat(), "balance_chf": value, "source": "relevé FICTIF"}
        assert client.post(route, headers=JR.HTRES, json=reading).status_code == 200
    balances = {"as_of": (at - timedelta(minutes=5)).isoformat(), "preorders_collected_chf": "0", "debts": [],
                "source": "agent finance FICTIF : aucune précommande hors pré-drop"}
    assert client.post("/treasury/balance-items", headers=JR.HTRES, json=balances).status_code == 200
    resp = client.post("/stoploss/state/refresh", headers=JR.HPHOTO)
    assert resp.status_code == 200, resp.text
    return body(resp)


def ready(tmp_path: Path, *, signed: bool = True, alloc: int = 10, interested: int = 10, **overrides: Any) -> tuple[Any, Any, F.Clock]:
    """Boutique FICTIVE prête pour un pré-drop : fiche validée, coût du moteur, allocation ferme, demande, photo."""
    client, svc, clock = boot(tmp_path, signed=signed, **overrides)
    catalog(client)
    offer_cost(svc)
    assert allocation(client, alloc).status_code == 201
    assert demand(client, interested).status_code == 201
    photo(client)
    return client, svc, clock


def open_predrop(client: Any, *, market: str | None = "250", headers: dict[str, str] | None = None) -> Any:
    payload: dict[str, Any] = {"product_key": P1, "drop_date": DROP.isoformat()}
    if market is not None:
        payload["market_ref_chf"] = market
    return client.post("/predrop/open", headers=headers or OWNER, json=payload)


def reserve(client: Any, order_id: str, customer: str = "a", *, qty: int = 1, amount: str | None = None,
            paid_at: datetime | None = None, priority: bool = False, pid: str = PID) -> Any:
    payload = {"predrop_id": pid, "order_id": order_id, "customer_ref": cref(customer), "qty": qty,
               "amount_paid_ttc": amount or str(D("229.90") * qty), "paid_at": (paid_at or NOW).isoformat(),
               "priority_access": priority}
    return client.post("/predrop/reservations", headers=JR.HORDERS, json=payload)


def signed_config(**overrides: Any) -> Any:
    return parse_predrop_config({**RAW, **overrides})


# =============================================================================================== prix


def test_prices_drop_is_the_engine_price_and_predrop_is_rounded_up_then_rechecked() -> None:
    config = signed_config()
    prices = compute_prices(D("140"), PARAMS, config, market_ref=D("250"))
    assert prices.drop_price == decide_price(D("140"), PARAMS).recommended_price == D("209.90")  # BP : 208.79 → 209.90
    # 209.90 × 1.08 = 226.692 → prochain point de la grille ≥ : 229.90 (X4.90 / X9.90 au-dessus de 100 CHF).
    assert prices.predrop_price == D("229.90") and prices.effective_premium_pct == D("0.0953")
    assert prices.ok and prices.problems == () and prices.needs_owner == () and prices.capped_by == ()
    assert price_floor_violations(prices.predrop_price, D("140"), PARAMS) == []
    assert round_up_retail(prices.predrop_price, tiers=PARAMS.rounding_tiers) == prices.predrop_price  # sur la grille
    # Supplément nul : un seul prix (le pré-drop reste la garantie d'être servi en premier).
    zero = compute_prices(D("140"), PARAMS, signed_config(premium_pct="0"), market_ref=D("250"))
    assert zero.predrop_price == zero.drop_price == D("209.90") and zero.effective_premium_pct == D("0")
    # Petit prix : 23.90 × 1.08 = 25.812 → 25.90.
    small = compute_prices(D("3.79"), PARAMS, config, market_ref=D("40"))
    assert (small.drop_price, small.predrop_price) == (D("23.90"), D("25.90"))


def test_premium_is_capped_at_ten_percent_by_the_code_configured_and_effective() -> None:
    # Configuré : au-delà de 10 %, le fichier est refusé (pré-drop désactivé).
    assert any("premium_pct" in e for e in validate_predrop_data({**RAW, "premium_pct": "0.11"}))
    with pytest.raises(PredropError):
        parse_predrop_config({**RAW, "premium_pct": "0.15"})
    # Effectif : 209.90 × 1.10 = 230.89 → arrondi 234.90 > plafond → plus grand point de grille ≤ 230.89 = 229.90.
    capped = compute_prices(D("140"), PARAMS, signed_config(premium_pct="0.10"), market_ref=D("300"))
    assert capped.predrop_price == D("229.90") and "PLAFOND_10_POURCENT" in capped.capped_by
    assert capped.effective_premium_pct <= MAX_PREMIUM_PCT
    # 9.90 × 1.10 = 10.89 → arrondi 10.90 > plafond → 9.90 (jamais sous le prix drop, jamais au-dessus de 10 %).
    tiny = compute_prices(D("1.20"), PARAMS, signed_config(premium_pct="0.10"), market_ref=D("50"))
    assert tiny.drop_price is not None and tiny.predrop_price is not None
    assert tiny.drop_price <= tiny.predrop_price <= tiny.drop_price * D("1.10")
    for cost in ("3.79", "8", "15", "60", "91.06", "140", "151.34", "420"):
        p = compute_prices(D(cost), PARAMS, signed_config(premium_pct="0.10"), market_ref=D("100000"))
        assert p.drop_price <= p.predrop_price <= p.drop_price * D("1.10"), cost
        assert p.effective_premium_pct <= MAX_PREMIUM_PCT and p.ok, cost


def test_predrop_price_never_exceeds_the_known_market_reference() -> None:
    config = signed_config()
    below = compute_prices(D("140"), PARAMS, config, market_ref=D("220"))
    assert below.predrop_price == D("219.90") and below.capped_by == ("REFERENCE_MARCHE",) and below.ok
    exact = compute_prices(D("140"), PARAMS, config, market_ref=D("229.90"))
    assert exact.predrop_price == D("229.90") and exact.capped_by == ()
    # Prix drop déjà au-dessus du marché : pas de pré-drop.
    above = compute_prices(D("140"), PARAMS, config, market_ref=D("200"))
    assert "ABOVE_MARKET" in above.problems and not above.ok
    # Référence inconnue : validation de la propriétaire.
    unknown = compute_prices(D("140"), PARAMS, config)
    assert unknown.needs_owner == ("MARKET_REF_UNKNOWN",) and unknown.ok
    with pytest.raises(PredropError):
        compute_prices(D("140"), PARAMS, config, market_ref=D("0"))


def test_margin_is_rechecked_and_a_blocked_drop_price_means_no_predrop(monkeypatch: pytest.MonkeyPatch) -> None:
    import pokeshop.predrop as PD

    config = signed_config()
    blocked = compute_prices(D("0"), PARAMS, config, market_ref=D("250"))
    assert blocked.problems == ("DROP_PRICE_BLOCKED",) and blocked.predrop_price is None and not blocked.ok
    for prices in (compute_prices(D(c), PARAMS, config, market_ref=D("100000")) for c in ("15", "91.06", "140")):
        assert price_floor_violations(prices.predrop_price, prices.landed_cost, PARAMS) == []
    # Revérification effective : un prix drop qui passerait sous les planchers (décision altérée) est refusé, et le
    # prix pré-drop qui en découle aussi (marge revérifiée après arrondi, jamais supposée).
    real = PD.decide_price
    monkeypatch.setattr(PD, "decide_price", lambda c, p, m=None: real(c, p, m).replace(recommended_price=D("150.00")))
    low = compute_prices(D("140"), PARAMS, config, market_ref=D("400"))
    assert {"DROP_BELOW_FLOOR", "PREDROP_BELOW_FLOOR"} <= set(low.problems) and not low.ok
    review = real(D("140"), PARAMS).replace(status=PD.DecisionStatus.REVIEW)
    monkeypatch.setattr(PD, "decide_price", lambda c, p, m=None: review)
    assert compute_prices(D("140"), PARAMS, config, market_ref=D("250")).needs_owner == ("DROP_PRICE_REVIEW",)
    draft = real(D("140"), PARAMS).replace(status=PD.DecisionStatus.DRAFT)
    monkeypatch.setattr(PD, "decide_price", lambda c, p, m=None: draft)
    assert "DROP_PRICE" in _eligibility().failed()


def test_round_down_retail_is_the_mirror_of_round_up() -> None:
    tiers = PARAMS.rounding_tiers
    for raw in ("0.49", "0.50", "1.00", "9.49", "9.99", "10.00", "10.89", "99.99", "100.00", "104.89", "230.89", "1000.00"):
        x = D(raw)
        down = round_down_retail(x, tiers=tiers)
        if down is None:
            assert x < D("0.50")
            continue
        assert down <= x and round_up_retail(down, tiers=tiers) == down
        assert round_up_retail(down + D("0.01"), tiers=tiers) > x  # aucun point de grille entre down et x
    assert round_down_retail(D("230.89"), tiers=tiers) == D("229.90")
    assert round_down_retail(D("10.89"), tiers=tiers) == D("9.90")


# ======================================================================================== paramètres signés


def test_unsigned_tampered_or_out_of_bounds_parameters_disable_the_predrop(tmp_path: Path) -> None:
    unsigned = load_predrop_config(DEFAULT_PREDROP_PATH, expected_fingerprint="")
    assert unsigned.enabled is False and unsigned.signature == "UNSIGNED" and unsigned.config is not None
    fingerprint = unsigned.fingerprint
    signed = load_predrop_config(DEFAULT_PREDROP_PATH, expected_fingerprint=fingerprint)
    assert signed.enabled and signed.signature == "SIGNED"
    # Fichier modifié après signature : désactivé (jamais les nouvelles valeurs).
    path, _ = write_config(tmp_path, per_customer_limit=2)
    tampered = load_predrop_config(path, expected_fingerprint=fingerprint)
    assert tampered.enabled is False and tampered.signature == "TAMPERED"
    # Empreinte recopiée dans le fichier différente du coffre : désactivé.
    data = {**RAW, "approval": {"approved_by": "FICTIVE", "approved_at": None, "fingerprint_sha256": "a" * 64}}
    path2 = tmp_path / "decl.yaml"
    path2.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    assert load_predrop_config(path2, expected_fingerprint=predrop_fingerprint(data)).signature == "TAMPERED"
    # L'empreinte ignore approval.fingerprint_sha256 mais pas le signataire.
    assert predrop_fingerprint({**RAW, "approval": {**RAW["approval"], "fingerprint_sha256": "b" * 64}}) == fingerprint
    assert predrop_fingerprint({**RAW, "approval": {**RAW["approval"], "approved_by": "X"}}) != fingerprint
    for bad in ({"premium_pct": "0.101"}, {"premium_pct": "-0.01"}, {"per_customer_limit": 3}, {"per_customer_limit": 0},
                {"safety_reserve_share": "0.05"}, {"safety_reserve_min_units": 0}, {"predrop_share_of_allocation": "0"},
                {"predrop_share_of_allocation": "1.5"}, {"priority_window_hours": 200}, {"demand_threshold": "0"},
                {"premium_pct": 0.08}, {"inconnu": 1}, {"per_customer_limit": True}):  # fmt: skip
        path3, fp3 = write_config(tmp_path, **bad)
        status = load_predrop_config(path3, expected_fingerprint=fp3)
        assert status.enabled is False and status.signature == "INVALID", bad
    missing = tmp_path / "absent.yaml"
    assert load_predrop_config(missing, expected_fingerprint=fingerprint).signature == "INVALID"


def test_fingerprint_cli_prints_the_value_to_copy_into_the_vault(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fingerprint", str(DEFAULT_PREDROP_PATH)]) == 0
    out = capsys.readouterr().out
    assert load_predrop_config(DEFAULT_PREDROP_PATH, expected_fingerprint="").fingerprint in out and "UNSIGNED" in out


def test_unsigned_parameters_close_the_predrop_in_the_api_and_a_paid_order_is_never_lost(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path, signed=False)
    health = body(client.get("/health"))
    assert health["signatures"]["predrop"] == "UNSIGNED" and health["predrop"]["enabled"] is False
    refused = open_predrop(client)
    assert refused.status_code == 409 and "CONFIG_SIGNED" in body(refused)["erreur"]
    assert svc.predrop.predrops() == ()
    # Pré-drop ouvert puis paramètres non signés au redémarrage : réservation payée enregistrée, remboursement préparé.
    client2, svc2, _ = ready(tmp_path / "b")
    assert open_predrop(client2).status_code == 201
    client3, svc3, _ = boot(tmp_path / "b", signed=False)
    resp = reserve(client3, "FICTIF-CMD-1")
    data = body(resp)
    assert resp.status_code == 201 and data["reservation"]["status"] == "NOT_SERVED"
    assert data["reservation"]["not_served_reason"] == "DISABLED" and data["refund"]["amount_ttc"] == "229.90"
    offers = body(client3.get("/predrop/offers", headers=H))
    assert offers["enabled"] is False and offers["offers"][0]["statut"] == STATUS_CLOSED_FR


# ============================================================================================== éligibilité


def _eligibility(**changes: Any) -> Any:
    status = load_predrop_config(DEFAULT_PREDROP_PATH, expected_fingerprint=load_predrop_config(
        DEFAULT_PREDROP_PATH, expected_fingerprint="").fingerprint)  # fmt: skip
    alloc = FirmAllocation(product_key=P1, supplier_id=SUPPLIER, qty=10, supplier_confirmation_ref="FICTIF-CONF-1",
                           source="confirmation FICTIVE", recorded_by="n8n-03-factures", recorded_at=NOW)  # fmt: skip
    signal = DemandSignal(product_key=P1, interested_consenting_subscribers=10, as_of=NOW - timedelta(hours=1),
                          source="alertes FICTIVES", recorded_by="n8n-06-marketing", recorded_at=NOW)  # fmt: skip
    kwargs: dict[str, Any] = dict(product_key=P1, config_status=status, allocation=alloc, demand=signal, now=NOW,
                                  listing_known=True, listing_approved=True, cost=D("140"), params=PARAMS,
                                  market_ref=D("250"), stoploss_problem=None, quarantined=False)  # fmt: skip
    kwargs.update(changes)
    return evaluate_eligibility(**kwargs)


def test_eligibility_requires_every_condition() -> None:
    ok = _eligibility()
    assert ok.eligible and ok.failed() == () and ok.demand_score == D("1.0000") and ok.quota.predrop_remaining == 4
    unsigned = load_predrop_config(DEFAULT_PREDROP_PATH, expected_fingerprint="")
    low = DemandSignal(product_key=P1, interested_consenting_subscribers=4, as_of=NOW, source="alertes FICTIVES",
                       recorded_by="n8n-06-marketing", recorded_at=NOW)  # fmt: skip
    stale = low.model_copy(update={"interested_consenting_subscribers": 50, "as_of": NOW - timedelta(days=8)})
    tiny = FirmAllocation(product_key=P1, supplier_id=SUPPLIER, qty=1, supplier_confirmation_ref="FICTIF-CONF-1",
                          source="FICTIF", recorded_by="propriétaire", recorded_at=NOW)  # fmt: skip
    cases = {
        "CONFIG_SIGNED": {"config_status": unsigned},
        "FIRM_ALLOCATION": {"allocation": None},
        "QUOTA": {"allocation": tiny, "demand": low},  # 1 unité : réserve 1, quota 0
        "DEMAND": {"demand": low},  # 4 / 10 = 0.4 < 0.5
        "LISTING_APPROVED": {"listing_approved": False},
        "COST_KNOWN": {"cost": None},
        "MARKET": {"market_ref": D("200")},
        "STOPLOSS": {"stoploss_problem": "gel global du stop-loss"},
        "QUARANTINE": {"quarantined": True},
        "SINGLE_PREDROP": {"open_predrop": "PD-AUTRE"},
    }
    for code, change in cases.items():
        result = _eligibility(**change)
        assert not result.eligible and code in result.failed(), (code, result.failed())
    assert "DEMAND" in _eligibility(demand=None).failed() and "DEMAND" in _eligibility(demand=stale).failed()
    assert "LISTING_APPROVED" in _eligibility(listing_known=False).failed()
    # Demande exactement au seuil : éligible (5 / 10 = 0.5).
    assert _eligibility(demand=low.model_copy(update={"interested_consenting_subscribers": 5})).eligible
    # Référence marché inconnue : éligible mais validation de la propriétaire.
    unknown = _eligibility(market_ref=None)
    assert unknown.eligible and unknown.needs_owner == ("MARKET_REF_UNKNOWN",)


def test_eligibility_through_the_api_reads_only_engine_registers(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    view = body(client.get(f"/predrop/eligibility/{P1}", headers=H))["eligibility"]
    assert not view["eligible"] and {"LISTING_APPROVED", "FIRM_ALLOCATION", "DEMAND", "COST_KNOWN", "STOPLOSS"} <= set(view["failed"])
    catalog(client, approve=False)
    offer_cost(svc)
    assert allocation(client).status_code == 201
    assert demand(client).status_code == 201
    view = body(client.get(f"/predrop/eligibility/{P1}", headers=H))["eligibility"]
    assert set(view["failed"]) == {"LISTING_APPROVED", "STOPLOSS"}  # fiche non validée, état du stop-loss inconnu
    catalog(client)  # validation de la propriétaire
    photo(client)
    view = body(client.get(f"/predrop/eligibility/{P1}", headers=H))["eligibility"]
    assert view["eligible"] and view["prix_drop_chf"] == "209.90" and view["prix_predrop_chf"] == "229.90"
    assert view["needs_owner"] == ["MARKET_REF_UNKNOWN"]
    text = json.dumps(view, ensure_ascii=False)
    assert "landed_cost" not in text and "contribution" not in text  # ni coût ni marge
    # Fiche modifiée après validation : plus validée (contenu en vigueur).
    changed = {**F.LISTING, "content_text": "36 boosters (contenu modifié FICTIF)"}
    item = {"product_id": P1, "listing": changed, "supplier_links": [{"supplier_id": SUPPLIER, "supplier_sku": "FICTIF-SKU-1"}]}
    assert client.post("/catalog/items", headers=JR.HCAT, json={"items": [item]}).status_code == 200
    assert "LISTING_APPROVED" in body(client.get(f"/predrop/eligibility/{P1}", headers=H))["eligibility"]["failed"]


def test_stale_offer_cost_or_open_incident_or_frozen_stoploss_refuse_the_opening(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    svc.sync.replacement_costs._latest.clear()
    offer_cost(svc, age=timedelta(hours=30))  # offre de plus de 24 h : nouvelle promesse refusée
    resp = open_predrop(client)
    assert resp.status_code == 409 and "COST_KNOWN" in body(resp)["erreur"]
    offer_cost(svc)
    client.post("/incidents", headers=JR.HINC, json={"code": "INC-01", "product_key": P1, "cause": "prix anormal FICTIF"})
    assert svc.incidents.is_quarantined(P1)
    resp = open_predrop(client)
    assert resp.status_code == 409 and "QUARANTINE" in body(resp)["erreur"]
    client2, svc2, _ = ready(tmp_path / "gel")
    assert client2.post("/stoploss/freeze", headers=JR.HQA, json={"actor": "agent-12", "reason": "gel FICTIF"}).status_code == 200
    resp = open_predrop(client2)
    assert resp.status_code == 409 and "STOPLOSS" in body(resp)["erreur"]


# ===================================================================================== ouverture, validation


def test_role_opening_without_market_reference_waits_for_the_owner_one_click(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    forged = open_predrop(client, headers=JR.headers("chef-de-projet"), market="400")
    assert forged.status_code == 403 and svc.predrop.predrops() == ()  # référence marché : propriétaire seule
    pending = open_predrop(client, headers=JR.HF, market=None)
    assert pending.status_code == 201 and body(pending)["predrop"]["status"] == "PENDING_OWNER"
    assert body(pending)["offer"] is None
    # En attente : aucune réservation servie.
    data = body(reserve(client, "FICTIF-CMD-0"))
    assert data["reservation"]["not_served_reason"] == "CLOSED"
    assert open_predrop(client, headers=JR.HF, market=None).status_code == 409  # un seul à la fois
    assert client.post(f"/predrop/{PID}/approve", headers=JR.HCHEF, json={"reason": "validation FICTIVE"}).status_code == 403
    approved = client.post(f"/predrop/{PID}/approve", headers=OWNER,
                           json={"market_ref_chf": "220", "reason": "référence marché relevée FICTIVE"})
    assert approved.status_code == 200, approved.text
    view = body(approved)["predrop"]
    assert view["status"] == "OPEN" and view["prix_predrop_chf"] == "219.90" and view["validated_by"] == "propriétaire"
    assert client.post(f"/predrop/{PID}/approve", headers=OWNER, json={"reason": "deuxième clic FICTIF"}).status_code == 409


def test_owner_opening_validates_and_freezes_prices_and_parameters(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    resp = open_predrop(client, market=None)
    assert resp.status_code == 201, resp.text
    data = body(resp)
    assert data["predrop"]["status"] == "OPEN" and data["predrop"]["validated_by"] == "propriétaire"
    predrop = svc.predrop.get(PID)
    assert predrop.prices.predrop_price == D("229.90") and predrop.per_customer_limit == 1
    assert predrop.config_fingerprint == svc.predrop_config.fingerprint
    # Prix figés : un coût qui change ensuite ne change pas le prix promis.
    offer_cost(svc, "150")
    assert svc.predrop.get(PID).prices.predrop_price == D("229.90")
    for bad in ({"drop_date": "2026-10-04"}, {"drop_date": DROP.isoformat(), "closes_at": "2026-10-21T00:00:00+02:00"}):
        assert client.post("/predrop/open", headers=OWNER, json={"product_key": P1, **bad}).status_code == 422, bad


# ===================================================================================== offre publique


def test_public_offer_has_no_false_urgency_no_cost_no_margin_and_states_the_guarantee(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path, priority_window_hours=24)
    assert open_predrop(client).status_code == 201
    data = body(client.get("/predrop/offers", headers=H))
    offer = data["offers"][0]
    assert tuple(offer) == PUBLIC_OFFER_FIELDS and data["simulation"] is True
    assert offer["statut"] == STATUS_OPEN_FR and offer["date_drop"] == "2026-10-20"
    assert offer["prix_predrop_chf"] == "229.90" and offer["prix_drop_chf"] == "209.90"
    assert offer["garantie"] == GUARANTEE_TEXT_FR and "pas le produit" in offer["garantie"]
    assert offer["difference"] == NO_DIFFERENCE_REFUND_FR and "Aucun remboursement de la différence" in offer["difference"]
    text = json.dumps(offer, ensure_ascii=False).lower()
    for forbidden in ("coût", "cost", "marge", "margin", "contribution", "quota", "allocation", "restant", "remaining",
                      "plus que", "dernière", "vite", "compte à rebours", "closes_at", "opens_at", "jusqu'à"):
        assert forbidden not in text, forbidden
    # Quota épuisé : « Réservations fermées », jamais « plus que N ».
    for i in range(4):
        assert body(reserve(client, f"FICTIF-CMD-{i}", f"c{i}", priority=True))["reservation"]["status"] == "CONFIRMED"
    closed = body(client.get("/predrop/offers", headers=H))["offers"][0]
    assert closed["statut"] == STATUS_CLOSED_FR and closed["reservations_ouvertes"] is False
    assert public_offer(svc.predrop.get(PID), accepting=False)["statut"] == STATUS_CLOSED_FR


# ===================================================================================== réservations et quotas


def test_quota_split_reserve_and_drop_share() -> None:
    assert reserve_units(10, min_units=1, share=D("0.10")) == 1
    assert reserve_units(25, min_units=1, share=D("0.10")) == 3  # ⌈2.5⌉
    assert reserve_units(3, min_units=1, share=D("0.05")) == 1  # jamais moins de 10 % ni d'une unité
    split = split_quota(10, 0, share=D("0.5"), reserve_min_units=1, reserve_share=D("0.10"))
    assert (split.safety_reserve, split.sellable, split.predrop_cap, split.predrop_remaining, split.drop_quota) == (1, 9, 4, 4, 5)
    after = split_quota(10, 3, share=D("0.5"), reserve_min_units=1, reserve_share=D("0.10"))
    assert (after.predrop_remaining, after.drop_quota) == (1, 5)
    closed = split_quota(10, 3, share=D("0.5"), reserve_min_units=1, reserve_share=D("0.10"), predrop_open=False)
    assert (closed.predrop_remaining, closed.drop_quota) == (0, 6)  # unités non réservées : au drop
    short = split_quota(3, 4, share=D("0.5"), reserve_min_units=1, reserve_share=D("0.10"))
    assert short.shortfall == 2 and short.predrop_remaining == 0 and short.drop_quota == 0


def test_reservations_fill_the_quota_then_are_refunded_never_lost(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    for i in range(4):
        resp = reserve(client, f"FICTIF-CMD-{i}", f"c{i}")
        assert resp.status_code == 201 and body(resp)["reservation"]["status"] == "CONFIRMED", resp.text
        assert "customer_ref" not in body(resp)["reservation"]
    late = body(reserve(client, "FICTIF-CMD-9", "c9"))
    assert late["reservation"]["status"] == "NOT_SERVED" and late["reservation"]["not_served_reason"] == "QUOTA_EXHAUSTED"
    assert late["refund"]["status"] == "PENDING_OWNER" and late["refund"]["amount_ttc"] == "229.90"
    assert "remboursons intégralement 229.90 CHF" in late["refund"]["email_draft"] and "@" not in late["refund"]["email_draft"]
    quota = svc.predrop.quota(PID, at=NOW)
    assert quota.predrop_committed == 4 and quota.predrop_remaining == 0 and quota.drop_quota == 5
    # Montant différent du prix pré-drop du moteur : non servie, remboursée.
    client2, svc2, _ = ready(tmp_path / "prix")
    assert open_predrop(client2).status_code == 201
    cheap = body(reserve(client2, "FICTIF-CMD-P", amount="209.90"))
    assert cheap["reservation"]["not_served_reason"] == "AMOUNT_MISMATCH" and cheap["refund"]["amount_ttc"] == "209.90"
    # Paiement avant l'ouverture : non servi.
    early = body(reserve(client2, "FICTIF-CMD-E", "e", paid_at=NOW - timedelta(hours=2)))
    assert early["reservation"]["not_served_reason"] == "CLOSED"
    # Pré-drop inconnu : rien à rattacher (409, n8n alerte).
    assert reserve(client2, "FICTIF-CMD-X", pid="PD-INCONNU").status_code == 409


def test_concurrent_payments_on_the_last_unit_confirm_exactly_one() -> None:
    registry = PredropRegistry(store=InMemoryStateJournal("predrop"))
    registry.set_allocation(FirmAllocation(product_key=P1, supplier_id=SUPPLIER, qty=4, supplier_confirmation_ref="FICTIF-CONF-1",
                                           source="FICTIF", recorded_by="propriétaire", recorded_at=NOW))  # fmt: skip
    prices = compute_prices(D("140"), PARAMS, signed_config(), market_ref=D("250"))
    registry.open(_predrop(prices))
    # Allocation 4, réserve 1, vendable 3, part 50 % : 1 seule unité en pré-drop.
    assert registry.quota(PID, at=NOW).predrop_remaining == 1
    results: list[str] = []
    barrier = threading.Barrier(12)

    def pay(i: int) -> None:
        barrier.wait()
        res, _, _ = registry.record_reservation(
            predrop_id=PID, order_id=f"FICTIF-CMD-{i}", customer_ref=cref(str(i)), qty=1, amount_paid_ttc=D("229.90"),
            paid_at=NOW, priority_access=True, recorded_by="n8n-02-commandes", at=NOW, enabled=True,
            blocked_reason=None, autonomy_level=1)  # fmt: skip
        results.append(res.status)

    threads = [threading.Thread(target=pay, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results).count("CONFIRMED") == 1 and results.count("NOT_SERVED") == 11
    assert len(registry.refunds("PENDING_OWNER")) == 11 and registry.committed_units(PID) == 1


def _predrop(prices: Any, **changes: Any) -> Predrop:
    data: dict[str, Any] = dict(
        predrop_id=PID, product_key=P1, public_sku="DSP-FICTIF_ALPHA-FR", allocation_ref="FICTIF-CONF-1", drop_date=DROP,
        opens_at=NOW - timedelta(minutes=1), closes_at=datetime(2026, 10, 20, tzinfo=TZ), status="OPEN", prices=prices,
        config_version="predrop-v1", config_fingerprint="0" * 64, premium_pct=D("0.08"), predrop_share=D("0.5"),
        reserve_min_units=1, reserve_share=D("0.10"), per_customer_limit=1, priority_window_hours=0,
        demand_threshold=D("0.5"), demand_interested=10, demand_allocation=10, demand_score=D("1"),
        requested_by="propriétaire", requested_at=NOW,
    )  # fmt: skip
    data.update(changes)
    return Predrop(**data)


def test_customer_limit_uses_the_hashed_customer_id(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    assert body(reserve(client, "FICTIF-CMD-1", "alice"))["reservation"]["status"] == "CONFIRMED"
    second = body(reserve(client, "FICTIF-CMD-2", "alice"))
    assert second["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT" and second["refund"] is not None
    two = body(reserve(client, "FICTIF-CMD-3", "bob", qty=2))  # 2 unités > limite 1
    assert two["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT" and two["refund"]["amount_ttc"] == "459.80"
    assert body(reserve(client, "FICTIF-CMD-4", "bob"))["reservation"]["status"] == "CONFIRMED"
    # Limite 2 (borne du code) : deux unités admises, pas trois.
    client2, _, _ = ready(tmp_path / "deux", per_customer_limit=2)
    assert open_predrop(client2).status_code == 201
    assert body(reserve(client2, "FICTIF-CMD-1", "alice", qty=2))["reservation"]["status"] == "CONFIRMED"
    assert body(reserve(client2, "FICTIF-CMD-2", "alice"))["reservation"]["not_served_reason"] == "CUSTOMER_LIMIT"
    # Jamais un email ni un identifiant en clair.
    bad = {"predrop_id": PID, "order_id": "FICTIF-CMD-9", "customer_ref": "alice@example.org", "qty": 1,
           "amount_paid_ttc": "229.90", "paid_at": NOW.isoformat()}
    assert client.post("/predrop/reservations", headers=JR.HORDERS, json=bad).status_code == 422
    listing = json.dumps(body(client.get("/predrop/reservations", headers=H)), ensure_ascii=False)
    assert cref("alice") not in listing and "customer_ref" not in listing


def test_priority_window_serves_alert_subscribers_first(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path, priority_window_hours=24)
    assert open_predrop(client).status_code == 201
    outsider = body(reserve(client, "FICTIF-CMD-1", "a"))
    assert outsider["reservation"]["not_served_reason"] == "PRIORITY_WINDOW"
    assert body(reserve(client, "FICTIF-CMD-2", "b", priority=True))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(hours=25)
    # Photo fraîche après la fenêtre ; l'argent encaissé (2 × 229.90, dont un remboursement en attente) est sur le
    # compte et compté en dette.
    fresh = photo(client, NOW + timedelta(hours=25), capital=False, bank="2459.80")
    assert fresh["sources"]["precommandes"]["predrop_derivees_chf"] == "459.80"
    after = body(reserve(client, "FICTIF-CMD-3", "c", paid_at=NOW + timedelta(hours=24, minutes=30)))
    assert after["reservation"]["status"] == "CONFIRMED"


def test_reservation_is_idempotent_by_order(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    first = reserve(client, "FICTIF-CMD-1")
    again = reserve(client, "FICTIF-CMD-1")
    assert first.status_code == 201 and again.status_code == 200 and body(again)["created"] is False
    assert len(svc.predrop.reservations()) == 1
    other = reserve(client, "FICTIF-CMD-1", "z")
    assert other.status_code == 409 and len(svc.predrop.reservations()) == 1
    future = reserve(client, "FICTIF-CMD-2", paid_at=NOW + timedelta(hours=1))
    assert future.status_code == 409


def test_registry_state_survives_a_restart_and_a_corrupt_journal_freezes(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    for i in range(5):
        reserve(client, f"FICTIF-CMD-{i}", f"c{i}")
    client2, svc2, _ = boot(tmp_path)
    assert svc2.predrop.get(PID).status == "OPEN" and len(svc2.predrop.reservations()) == 5
    assert svc2.predrop.committed_units(PID) == 4 and len(svc2.predrop.refunds()) == 1
    assert svc2.predrop.allocation(P1).qty == 10 and svc2.predrop.demand(P1).interested_consenting_subscribers == 10
    # Après redémarrage, le quota reste épuisé : jamais une 5ᵉ unité confirmée.
    assert body(reserve(client2, "FICTIF-CMD-7", "c7"))["reservation"]["not_served_reason"] == "QUOTA_EXHAUSTED"
    journal = tmp_path / "etat" / "predrop.jsonl"
    lines = journal.read_text(encoding="utf-8").splitlines()
    journal.write_text("\n".join([*lines[:-1], lines[-1].replace("CONFIRMED", "CONFIRMEE").replace("NOT_SERVED", "SERVIE")]) + "\n",
                       encoding="utf-8")  # fmt: skip
    client3, svc3, _ = boot(tmp_path)
    assert "predrop" in svc3.restore_errors
    assert client3.get("/predrop/offers", headers=H).status_code == 503
    assert reserve(client3, "FICTIF-CMD-8", "c8").status_code == 503
    assert client3.post("/stoploss/state/refresh", headers=JR.HPHOTO).status_code == 503
    with pytest.raises(PredropPersistenceError):
        PredropRegistry.restore(svc3.predrop._store)


# ===================================================================================== réduction d'allocation


def test_allocation_reduction_serves_predrop_first_cuts_the_drop_then_refunds_the_latest(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    for i in range(4):  # 4 réservations confirmées, payées dans l'ordre 0 à 3
        assert body(reserve(client, f"FICTIF-CMD-{i}", f"c{i}", paid_at=NOW + timedelta(minutes=i)))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(minutes=10)
    # Réduction 10 → 6 : réserve 1, servable 5 ≥ 4 réservées : tout le pré-drop est servi, le drop perd 4 unités.
    cut = client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                      json={"new_qty": 6, "supplier_confirmation_ref": "FICTIF-REDUC-1", "reason": "livraison partielle FICTIVE"})
    assert cut.status_code == 200, cut.text
    plan = body(cut)["plan"]
    assert plan["kept"] == [f"FICTIF-CMD-{i}" for i in range(4)] and plan["refunded"] == []
    assert (plan["drop_quota_before"], plan["drop_quota_after"]) == (5, 1)
    # Réduction 6 → 3 : servable 2 : les deux premières payées servies, les deux dernières remboursées intégralement.
    cut2 = client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.headers("n8n-03-factures"),
                       json={"new_qty": 3, "supplier_confirmation_ref": "FICTIF-REDUC-2", "reason": "seconde réduction FICTIVE"})
    data = body(cut2)
    assert data["plan"]["kept"] == ["FICTIF-CMD-0", "FICTIF-CMD-1"] and data["plan"]["refunded"] == ["FICTIF-CMD-2", "FICTIF-CMD-3"]
    assert data["plan"]["drop_quota_after"] == 0
    refunds = data["refunds"]
    assert [r["order_id"] for r in refunds] == ["FICTIF-CMD-2", "FICTIF-CMD-3"]
    assert all(r["reason"] == "ALLOCATION_REDUCED" and r["status"] == "PENDING_OWNER" and r["amount_ttc"] == "229.90" for r in refunds)
    assert "le fournisseur a réduit" in refunds[0]["email_draft"] and "{{NOM_BOUTIQUE}}" in refunds[0]["email_draft"]
    assert svc.predrop.committed_units(PID) == 2
    # Rejeu identique : sans effet ; même référence, autre quantité : 409 ; hausse par réduction : 409.
    replay = client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.headers("n8n-03-factures"),
                         json={"new_qty": 3, "supplier_confirmation_ref": "FICTIF-REDUC-2", "reason": "seconde réduction FICTIVE"})
    assert body(replay)["created"] is False and body(replay)["plan"]["refunded"] == ["FICTIF-CMD-2", "FICTIF-CMD-3"]
    assert client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                       json={"new_qty": 2, "supplier_confirmation_ref": "FICTIF-REDUC-2", "reason": "conflit FICTIF xxxx"}).status_code == 409
    assert client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                       json={"new_qty": 8, "supplier_confirmation_ref": "FICTIF-REDUC-3", "reason": "hausse FICTIVE xxxxx"}).status_code == 409
    # Une baisse par une « nouvelle allocation » est refusée (elle contournerait le plan de service).
    assert allocation(client, 2, ref="FICTIF-CONF-2").status_code == 409
    # Rejeu de l'allocation d'origine après réduction : sans effet, l'allocation réduite reste en vigueur.
    replay_alloc = allocation(client, 10, ref="FICTIF-CONF-1")
    assert replay_alloc.status_code == 200 and svc.predrop.allocation(P1).qty == 3
    # Persisté : le plan et les remboursements survivent au redémarrage.
    _, svc2, _ = boot(tmp_path)
    assert svc2.predrop.allocation(P1).qty == 3 and len(svc2.predrop.refunds("PENDING_OWNER")) == 2


def test_plan_service_is_strict_payment_order() -> None:
    registry = PredropRegistry()
    prices = compute_prices(D("140"), PARAMS, signed_config(per_customer_limit=2), market_ref=D("250"))
    registry.set_allocation(FirmAllocation(product_key=P1, supplier_id=SUPPLIER, qty=20, supplier_confirmation_ref="FICTIF-CONF-1",
                                           source="FICTIF", recorded_by="propriétaire", recorded_at=NOW))  # fmt: skip
    registry.open(_predrop(prices, per_customer_limit=2))
    for i, qty in enumerate((1, 2, 1)):
        registry.record_reservation(predrop_id=PID, order_id=f"FICTIF-CMD-{i}", customer_ref=cref(str(i)), qty=qty,
                                    amount_paid_ttc=D("229.90") * qty, paid_at=NOW + timedelta(minutes=i),
                                    priority_access=True, recorded_by="n8n-02-commandes", at=NOW, enabled=True,
                                    blocked_reason=None, autonomy_level=1)  # fmt: skip
    confirmed = [r for r in registry.reservations() if r.status == "CONFIRMED"]
    # Allocation 4 : réserve 1, servable 3 → 1 + 2 servies ; la 3ᵉ (payée en dernier) remboursée.
    plan = plan_service(confirmed, 4, reserve_min_units=1, reserve_share=D("0.10"))
    assert plan.kept == ("FICTIF-CMD-0", "FICTIF-CMD-1") and plan.refunded == ("FICTIF-CMD-2",)
    # Allocation 3 : servable 2 → la 2ᵉ (2 unités) ne tient plus : elle et toutes les suivantes sont remboursées.
    plan = plan_service(confirmed, 3, reserve_min_units=1, reserve_share=D("0.10"))
    assert plan.kept == ("FICTIF-CMD-0",) and plan.refunded == ("FICTIF-CMD-1", "FICTIF-CMD-2")
    assert plan_service(confirmed, 0, reserve_min_units=1, reserve_share=D("0.10")).refunded == tuple(r.order_id for r in confirmed)


def test_refund_execution_follows_the_autonomy_level_and_owner_one_click(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    for i in range(5):
        reserve(client, f"FICTIF-CMD-{i}", f"c{i}")
    refund_id = "pdr:FICTIF-CMD-4"
    pending = svc.predrop.refund(refund_id)
    assert pending.status == "PENDING_OWNER" and pending.autonomy_level == 1
    executed = {"executed_at": NOW.isoformat(), "psp_refund_ref": "FICTIF-PSP-1"}
    early = client.post(f"/predrop/refunds/{refund_id}/executed", headers=JR.HORDERS, json=executed)
    assert early.status_code == 409 and "validation de la propriétaire" in body(early)["erreur"]
    assert client.post(f"/predrop/refunds/{refund_id}/approve", headers=JR.HORDERS, json={}).status_code == 403
    one_click = client.post(f"/predrop/refunds/{refund_id}/approve", headers=OWNER)  # corps vide : un clic
    assert one_click.status_code == 200 and body(one_click)["refund"]["status"] == "APPROVED"
    assert body(client.post(f"/predrop/refunds/{refund_id}/approve", headers=OWNER))["changed"] is False
    assert client.post(f"/predrop/refunds/{refund_id}/executed", headers=JR.HF, json=executed).status_code == 403
    done = client.post(f"/predrop/refunds/{refund_id}/executed", headers=JR.HORDERS, json=executed)
    assert done.status_code == 200 and body(done)["refund"]["status"] == "EXECUTED"
    again = client.post(f"/predrop/refunds/{refund_id}/executed", headers=JR.HORDERS, json=executed)
    assert again.status_code == 200 and body(again)["changed"] is False
    other = client.post(f"/predrop/refunds/{refund_id}/executed", headers=JR.HORDERS, json={**executed, "psp_refund_ref": "FICTIF-PSP-2"})
    assert other.status_code == 409
    # Niveau d'autonomie ≥ 3 : remboursement approuvé par le moteur (exécution par le workflow 02).
    for level in (2, 3):
        raised = client.post("/autonomy", headers=HO, json={"level": level, "reason": "recette FICTIVE OK", "actor": "propriétaire"})
        assert raised.status_code == 200, raised.text
    auto = body(reserve(client, "FICTIF-CMD-9", "c9"))["refund"]
    assert AUTO_REFUND_MIN_LEVEL == 3 and auto["status"] == "APPROVED" and auto["approved_by"].startswith("moteur")


# ======================================================================== dette, photo, étoile polaire


def test_collected_money_is_a_derived_debt_in_the_stoploss_photo_until_shipped_or_refunded(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    before = photo(client, capital=False)
    assert before["cash_available_chf"] == "3500.00" and before["sources"]["precommandes"]["predrop_derivees_chf"] == "0.00"
    assert open_predrop(client).status_code == 201
    clock.now = NOW + timedelta(minutes=30)
    for i in range(5):  # 4 confirmées + 1 non servie (remboursement en attente) : 5 × 229.90 encaissés
        reserve(client, f"FICTIF-CMD-{i}", f"c{i}", paid_at=NOW + timedelta(minutes=i))
    clock.now = NOW + timedelta(hours=1)
    data = photo(client, clock.now, capital=False, bank="3149.50")  # l'argent encaissé est sur le compte
    pre = data["sources"]["precommandes"]
    assert pre == {"declarees_chf": "0", "predrop_derivees_chf": "1149.50", "predrop_reservations": 5, "total_chf": "1149.50"}
    # Cash relevé 4 649.50 − dette dérivée 1 149.50 : le cash disponible ne gonfle pas avec l'argent encaissé.
    assert data["cash_available_chf"] == "3500.00" and data["status"]["global_frozen"] is False
    # Sans le relevé de l'encaissement (cash inchangé), la même dette fait baisser la valeur nette (fermé par défaut).
    debts = svc.stoploss_state.net_worth.debts
    assert [(d.label, d.amount) for d in debts if "pré-drop" in d.label] == [
        ("Réservations pré-drop encaissées non livrées (registre du moteur)", D("1149.50"))]
    # Une déclaration de l'agent finance ne peut pas effacer la dette dérivée (elle s'y ajoute).
    assert svc.predrop.outstanding_debt(as_of=clock.now, shipped=lambda _: False).total_chf == D("1149.50")
    assert svc.predrop.outstanding_debt(as_of=NOW, shipped=lambda _: False).total_chf == D("229.90")  # payé ≤ date
    # Expédition d'une commande pré-drop : la dette sort, la vente est reconnue.
    shipped = {"order_id": "FICTIF-CMD-0", "paid_at": NOW.isoformat(), "net_sales_ht": "212.67",
               "payment_fees": "6.05", "shipping_cost_actual": "7.40", "shipping_label_ref": "FICTIF-ETIQ-0",
               "source": "webhook Shopify FICTIF", "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=shipped).status_code == 201
    # Remboursement exécuté de la réservation non servie : la dette sort aussi.
    assert client.post("/predrop/refunds/pdr:FICTIF-CMD-4/approve", headers=OWNER).status_code == 200
    assert client.post("/predrop/refunds/pdr:FICTIF-CMD-4/executed", headers=JR.HORDERS,
                       json={"executed_at": (clock.now - timedelta(minutes=5)).isoformat(), "psp_refund_ref": "FICTIF-PSP-4"}).status_code == 200
    clock.now = NOW + timedelta(hours=2)
    after = photo(client, clock.now, capital=False, bank="2919.60")  # remboursement sorti du compte
    assert after["sources"]["precommandes"]["predrop_derivees_chf"] == "689.70"  # 3 × 229.90
    states = {r["order_id"]: r["state"] for r in body(client.get("/predrop/reservations", headers=H))["reservations"]}
    assert states["FICTIF-CMD-0"] == "SHIPPED" and states["FICTIF-CMD-4"] == "REFUNDED" and states["FICTIF-CMD-1"] == "CONFIRMED"


def test_revenue_is_recognized_at_shipment_never_at_collection(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    paid = NOW
    assert body(reserve(client, "FICTIF-CMD-1", paid_at=paid))["reservation"]["status"] == "CONFIRMED"
    report = body(client.get("/northstar", headers=H))
    assert report["cumulative"] == "0.00" and svc.northstar.entries() == ()  # encaissement : aucune vente
    clock.now = NOW + timedelta(days=12)  # réception puis expédition dès réception
    shipped = {"order_id": "FICTIF-CMD-1", "paid_at": paid.isoformat(), "net_sales_ht": "212.67", "payment_fees": "6.05",
               "shipping_cost_actual": "7.40", "shipping_label_ref": "FICTIF-ETIQ-1", "source": "webhook Shopify FICTIF",
               "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    resp = client.post("/orders/shipped", headers=JR.HORDERS, json=shipped)
    assert resp.status_code == 201, resp.text
    sales = [e for e in svc.northstar.entries() if e.entry_id == "order:FICTIF-CMD-1:NET_SALES"]
    assert sales and sales[0].at == NOW + timedelta(days=12)  # date de l'expédition, pas du paiement
    assert svc.orders.get("FICTIF-CMD-1").recognized_at == NOW + timedelta(days=12)
    # Rejeu de la commande expédiée plus tard : idempotent (la date de reconnaissance ne change pas).
    clock.now = NOW + timedelta(days=13)
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=shipped).status_code == 200
    assert svc.orders.get("FICTIF-CMD-1").recognized_at == NOW + timedelta(days=12)
    # Commande ordinaire (hors pré-drop) : inchangée, datée du paiement.
    ordinary = {**shipped, "order_id": "FICTIF-CMD-ORD", "shipping_label_ref": "FICTIF-ETIQ-ORD"}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=ordinary).status_code == 201
    assert svc.orders.get("FICTIF-CMD-ORD").recognized_at is None
    # Redémarrage : la date de reconnaissance est relue telle quelle.
    _, svc2, _ = boot(tmp_path, clock=F.Clock(NOW + timedelta(days=14)))
    assert [e.at for e in svc2.northstar.entries() if e.entry_id == "order:FICTIF-CMD-1:NET_SALES"] == [NOW + timedelta(days=12)]


# =============================================================================== autorisations, données personnelles


def test_matrix_roles_and_common_token(tmp_path: Path) -> None:
    client, svc, _ = ready(tmp_path)
    writes = [(m, p) for (m, p), r in authz.ROUTE_MATRIX.items() if p.startswith("/predrop") and r.kind is authz.Kind.WRITE]
    assert len(writes) == 9
    for method, path in writes:
        concrete = path.replace("{product_key}", P1).replace("{predrop_id}", PID).replace("{refund_id}", "pdr:X")
        assert client.request(method, concrete, headers=H, json={}).status_code == 403, path  # jeton commun
    rule = authz.rule_for("POST", "/predrop/allocations")
    assert rule.roles == {"n8n-03-factures"} and rule.owner  # jamais un agent qui bénéficie du pré-drop
    for role in ("acquisition", "communication", "catalogue", "sourcing", "chef-de-projet", "finance-pricing"):
        assert allocation(client, 12, ref=f"FICTIF-{role}", headers=JR.headers(role)).status_code == 403, role
    assert authz.rule_for("POST", "/predrop/demand").roles == {"n8n-06-marketing"}
    for role in ("acquisition", "communication", "chef-de-projet"):
        payload = {"product_key": P1, "interested_consenting_subscribers": 999, "as_of": NOW.isoformat(), "source": "FICTIF"}
        assert client.post("/predrop/demand", headers=JR.headers(role), json=payload).status_code == 403, role
    assert authz.rule_for("POST", "/predrop/reservations").roles == {"n8n-02-commandes"}
    assert authz.rule_for("POST", "/predrop/refunds/{refund_id}/approve").owner_only
    assert authz.rule_for("POST", "/predrop/{predrop_id}/approve").owner_only
    for path in ("/predrop/offers", "/predrop/reservations", "/predrop/refunds", f"/predrop/eligibility/{P1}"):
        assert client.get(path, headers=H).status_code == 200, path  # lectures : jeton commun admis
    # Allocation posée par n8n-03 pour un fournisseur inconnu du moteur : refusée (propriétaire seule).
    unknown = {"product_key": P1, "supplier_id": "fictif_inconnu", "qty": 5, "supplier_confirmation_ref": "FICTIF-X-1",
               "source": "confirmation FICTIVE"}
    assert client.post("/predrop/allocations", headers=JR.headers("n8n-03-factures"), json=unknown).status_code == 409
    assert client.post("/predrop/allocations", headers=OWNER, json={**unknown, "qty": 12}).status_code == 201


def test_demand_signal_is_aggregate_only_no_personal_data(tmp_path: Path) -> None:
    client, svc, _ = boot(tmp_path)
    base = {"product_key": P1, "interested_consenting_subscribers": 12, "as_of": NOW.isoformat(), "source": "liste FICTIVE"}
    hm = JR.headers("n8n-06-marketing")
    for extra in ({"emails": ["a@example.org"]}, {"subscribers": [{"email": "a@example.org"}]}, {"names": ["FICTIF"]}):
        assert client.post("/predrop/demand", headers=hm, json={**base, **extra}).status_code == 422, extra
    assert client.post("/predrop/demand", headers=hm, json={**base, "source": "export de a@example.org"}).status_code == 422
    assert client.post("/predrop/demand", headers=hm, json=base).status_code == 201
    older = {**base, "as_of": (NOW - timedelta(days=1)).isoformat()}
    assert client.post("/predrop/demand", headers=hm, json=older).status_code == 409  # jamais de retour en arrière
    assert client.post("/predrop/demand", headers=hm, json={**base, "as_of": (NOW + timedelta(hours=1)).isoformat()}).status_code == 409
    stored = json.dumps(svc.predrop.demand(P1).model_dump(mode="json"))
    assert "@" not in stored


def test_close_is_protective_and_stops_new_reservations(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    assert body(reserve(client, "FICTIF-CMD-1", "a"))["reservation"]["status"] == "CONFIRMED"
    clock.now = NOW + timedelta(minutes=10)
    assert client.post(f"/predrop/{PID}/close", headers=JR.HACQ, json={"reason": "fermeture FICTIVE xx"}).status_code == 403
    closed = client.post(f"/predrop/{PID}/close", headers=JR.HQA, json={"reason": "fermeture conservatoire FICTIVE"})
    assert closed.status_code == 200 and body(closed)["predrop"]["status"] == "CLOSED"
    clock.now = NOW + timedelta(minutes=15)
    late = body(reserve(client, "FICTIF-CMD-2", "b", paid_at=NOW + timedelta(minutes=11)))
    assert late["reservation"]["not_served_reason"] == "CLOSED" and late["refund"] is not None
    # Paiement antérieur à la fermeture, reçu après : servi (le pré-drop était ouvert au paiement).
    inflight = body(reserve(client, "FICTIF-CMD-3", "c", paid_at=NOW + timedelta(minutes=5)))
    assert inflight["reservation"]["status"] == "CONFIRMED"
    quota = svc.predrop.quota(PID, at=clock.now)
    assert quota.predrop_remaining == 0 and quota.drop_quota == 9 - 2  # unités non réservées : au drop
    assert body(client.get("/predrop/offers", headers=H))["offers"][0]["statut"] == STATUS_CLOSED_FR
    assert body(client.post(f"/predrop/{PID}/close", headers=JR.HCHEF, json={"reason": "deuxième fermeture"}))["changed"] is False


def test_one_predrop_per_firm_allocation_and_a_new_one_only_once_the_previous_is_settled(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    assert body(reserve(client, "FICTIF-CMD-1", "a"))["reservation"]["status"] == "CONFIRMED"
    assert client.post(f"/predrop/{PID}/close", headers=JR.HQA, json={"reason": "fermeture FICTIVE avant drop"}).status_code == 200
    # Même allocation ferme : jamais un second quota sur les mêmes unités.
    again = client.post("/predrop/open", headers=OWNER, json={"product_key": P1, "drop_date": "2026-10-27", "market_ref_chf": "250"})
    assert again.status_code == 409 and "SINGLE_PREDROP" in body(again)["erreur"]
    # Nouvelle allocation ferme, mais réservation précédente ni expédiée ni remboursée : toujours refusé.
    assert allocation(client, 20, ref="FICTIF-CONF-2").status_code == 201
    again = client.post("/predrop/open", headers=OWNER, json={"product_key": P1, "drop_date": "2026-10-27", "market_ref_chf": "250"})
    assert again.status_code == 409 and "SINGLE_PREDROP" in body(again)["erreur"]
    # Réservation expédiée (précédent soldé) : nouveau pré-drop admis sur la nouvelle allocation.
    shipped = {"order_id": "FICTIF-CMD-1", "paid_at": NOW.isoformat(), "net_sales_ht": "212.67", "payment_fees": "6.05",
               "shipping_cost_actual": "7.40", "shipping_label_ref": "FICTIF-ETIQ-1", "source": "webhook Shopify FICTIF",
               "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=shipped).status_code == 201
    second = client.post("/predrop/open", headers=OWNER, json={"product_key": P1, "drop_date": "2026-10-27", "market_ref_chf": "250"})
    assert second.status_code == 201, second.text
    assert body(second)["predrop"]["quota"]["predrop_remaining"] == 9  # 20 − réserve 2 = 18 vendables, 50 %


def test_reduction_never_refunds_an_already_shipped_reservation(tmp_path: Path) -> None:
    client, svc, clock = ready(tmp_path)
    assert open_predrop(client).status_code == 201
    for i in range(3):
        reserve(client, f"FICTIF-CMD-{i}", f"c{i}", paid_at=NOW + timedelta(minutes=i))
    clock.now = NOW + timedelta(minutes=10)
    # La dernière payée a déjà été expédiée (arrivage partiel) : elle est servie, jamais remboursée.
    shipped = {"order_id": "FICTIF-CMD-2", "paid_at": (NOW + timedelta(minutes=2)).isoformat(), "net_sales_ht": "212.67",
               "payment_fees": "6.05", "shipping_cost_actual": "7.40", "shipping_label_ref": "FICTIF-ETIQ-2",
               "source": "webhook Shopify FICTIF", "lines": [{"public_sku": "DSP-FICTIF_ALPHA-FR", "qty": 1}]}
    assert client.post("/orders/shipped", headers=JR.HORDERS, json=shipped).status_code == 201
    cut = client.post(f"/predrop/allocations/{P1}/reduce", headers=JR.HOPS,
                      json={"new_qty": 3, "supplier_confirmation_ref": "FICTIF-REDUC-1", "reason": "livraison partielle FICTIVE"})
    plan = body(cut)["plan"]
    assert plan["kept"] == ["FICTIF-CMD-2", "FICTIF-CMD-0"] and plan["refunded"] == ["FICTIF-CMD-1"]
