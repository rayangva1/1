"""Coût rendu, prix plancher, arrondi retail, contribution et décision de prix (BP §4-5).

Règles de calcul (déterministes, versionnées par ``PricingParams.rules_version``) :

* Calculs intermédiaires en ``Decimal`` à 34 chiffres significatifs (contexte local fixe,
  indépendant du contexte global de l'appelant).
* **Arrondis monétaires : ROUND_HALF_UP à 0.01 CHF** sur chaque montant restitué
  (coûts, prix plancher, contributions). Coûts unitaires intermédiaires (ventilation,
  détail du coût rendu) : HALF_UP à 0.0001. Pourcentages : fraction HALF_UP à 0.0001
  (0.1656 = 16.56 %).
* **Exception : l'arrondi retail est toujours vers le haut** (prochain point de la grille
  ≥ prix rentable exact), puis la marge est **revérifiée** (BP §5).
* Contribution affichée = CA net arrondi − coût produit arrondi − frais variables arrondis
  (somme des frais de paiement, logistique, SAV, acquisition calculée exactement puis
  arrondie une fois). Le pourcentage est calculé sur ces montants arrondis.

Notation BP §4 : P prix public TTC, t TVA ventes, r frais paiement %, b frais paiement fixes,
L logistique nette, R provision SAV, A acquisition, m contribution cible, C coût rendu.
``P = (C + b + L + R + A) / ((1 − m)/(1 + t) − r)``.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Literal, ParamSpec, TypeVar

from .errors import IncompleteDataError, PricingError
from .models import (
    DEFAULT_ROUNDING_TIERS,
    AllocatedCost,
    AllocationLine,
    BasketLine,
    BasketLineResult,
    BasketResult,
    ContributionBreakdown,
    DecisionStatus,
    Discount,
    LandedCostBreakdown,
    LandedCostInput,
    PriceDecision,
    PricingParams,
    Reason,
    RoundingTier,
    SupplierOffer,
    TierDiscount,
    VatMode,
    canonical_hash,
)
from .stock import is_stale

__all__ = [
    "as_decimal",
    "q2",
    "q4",
    "select_tier",
    "apply_tier_discount",
    "landed_cost_breakdown",
    "landed_unit_cost",
    "estimate_import_vat",
    "allocate_amount",
    "allocate_inbound_costs",
    "floor_price_exact",
    "floor_price",
    "order_floor_price_exact",
    "round_up_retail",
    "contribution_breakdown",
    "contribution",
    "is_price_anomaly",
    "decide_price",
    "offer_unknown_fields",
    "landed_input_from_offer",
    "evaluate_offer",
    "basket_contribution",
]

P = ParamSpec("P")
T = TypeVar("T")

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")
BASIS_POINT = Decimal("0.0001")
_EXACT_TOLERANCE = Decimal("1E-12")
_MAX_RECHECK_STEPS = 20
_CTX = Context(prec=34, rounding=ROUND_HALF_EVEN)


def _deterministic(fn: Callable[P, T]) -> Callable[P, T]:
    """Exécute ``fn`` dans un contexte Decimal fixe (précision 34)."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with localcontext(_CTX):
            return fn(*args, **kwargs)

    return wrapper


def as_decimal(value: Decimal | int | str, name: str = "valeur") -> Decimal:
    """Convertit int/str/Decimal en Decimal fini. ``float`` et ``bool`` sont refusés (TypeError)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{name} : {type(value).__name__} interdit, utiliser Decimal ou str")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except ArithmeticError as exc:
            raise PricingError(f"{name} : valeur décimale invalide {value!r}") from exc
    else:
        raise TypeError(f"{name} : type {type(value).__name__} non supporté")
    if not result.is_finite():
        raise PricingError(f"{name} : valeur non finie")
    return result


def q2(value: Decimal) -> Decimal:
    """Arrondi monétaire HALF_UP à 0.01."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    """Arrondi HALF_UP à 0.0001 (coûts unitaires intermédiaires, pourcentages)."""
    return value.quantize(BASIS_POINT, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------------- landed cost


def select_tier(tiers: Sequence[TierDiscount], qty: int | None) -> TierDiscount | None:
    """Palier applicable : plus grand ``min_qty`` ≤ ``qty`` (None si aucun ou qty inconnue)."""
    if qty is None:
        return None
    if qty < 1:
        raise PricingError("quantité commandée < 1")
    eligible = [t for t in tiers if t.min_qty <= qty]
    return max(eligible, key=lambda t: t.min_qty) if eligible else None


@_deterministic
def apply_tier_discount(price: Decimal, tiers: Sequence[TierDiscount], qty: int | None) -> Decimal:
    """Prix du pack après remise par palier (non cumulative ; palier le plus élevé atteint).

    Sans palier atteint (ou ``qty`` None) : prix inchangé. Un palier en prix absolu remplace
    le prix de base ; un palier en % s'applique au prix de base. Non arrondi.
    """
    base = as_decimal(price, "price")
    if base < 0:
        raise PricingError("prix négatif")
    tier = select_tier(tiers, qty)
    if tier is None:
        return base
    if tier.price is not None:
        return tier.price
    assert tier.discount_pct is not None
    return base * (ONE - tier.discount_pct)


@_deterministic
def landed_cost_breakdown(inp: LandedCostInput) -> LandedCostBreakdown:
    """Détail du coût rendu par unité retail (BP §4).

    C = achat net CHF (après remise, hors TVA récupérable) + TVA fournisseur non récupérable
    + transport amont réparti + dédouanement/frais + TVA import si NOT_REGISTERED.
    Lève :class:`PricingError` si le prix d'achat est nul (anomalie « prix zéro »).
    """
    if inp.purchase_net <= 0:
        raise PricingError("prix d'achat nul : anomalie d'import (quarantaine)")
    tier = select_tier(inp.tier_discounts, inp.order_qty)
    pack = apply_tier_discount(inp.purchase_net, inp.tier_discounts, inp.order_qty)
    rate = inp.supplier_vat_rate
    if inp.price_includes_vat:
        ex_vat = pack / (ONE + rate)
        gross = pack
    else:
        ex_vat = pack
        gross = pack * (ONE + rate)
    vat_pack = gross - ex_vat
    effective = inp.vat_mode is VatMode.EFFECTIVE
    supplier_vat_recoverable = effective and inp.supplier_vat_country == "CH" and vat_pack > 0
    units = Decimal(inp.units_per_pack)
    fx = inp.fx_rate_to_chf
    purchase_unit = ex_vat * fx / units
    supplier_vat_unit = vat_pack * fx / units
    import_vat_in_cost = ZERO if effective else inp.import_vat
    recoverable = (supplier_vat_unit if supplier_vat_recoverable else ZERO) + (inp.import_vat if effective else ZERO)
    total = (
        purchase_unit
        + (ZERO if supplier_vat_recoverable else supplier_vat_unit)
        + inp.inbound_freight_alloc
        + inp.customs_and_fees
        + import_vat_in_cost
    )
    return LandedCostBreakdown(
        pack_price_after_discount=q4(pack),
        tier_applied=tier.min_qty if tier else None,
        purchase_ex_vat_unit_chf=q4(purchase_unit),
        supplier_vat_unit_chf=q4(supplier_vat_unit),
        supplier_vat_recoverable=supplier_vat_recoverable,
        inbound_freight_unit_chf=q4(inp.inbound_freight_alloc),
        customs_and_fees_unit_chf=q4(inp.customs_and_fees),
        import_vat_in_cost_unit_chf=q4(import_vat_in_cost),
        recoverable_vat_unit_chf=q4(recoverable),
        total=q2(total),
    )


def landed_unit_cost(inp: LandedCostInput) -> Decimal:
    """Coût rendu par unité retail en CHF, arrondi HALF_UP à 0.01 (BP §4)."""
    return landed_cost_breakdown(inp).total


@_deterministic
def estimate_import_vat(taxable_base_chf: Decimal, rate: Decimal = Decimal("0.081")) -> Decimal:
    """**Estimation** de TVA à l'importation = base × taux (0.01 HALF_UP).

    La base légale (valeur marchandise + transport jusqu'à destination + droits) se
    contrôle sur le décompte OFDF [S7] : remplacer l'estimation par le justificatif réel.
    """
    base = as_decimal(taxable_base_chf, "taxable_base_chf")
    r = as_decimal(rate, "rate")
    if base < 0 or not ZERO <= r < ONE:
        raise PricingError("base ou taux de TVA import invalide")
    return q2(base * r)


@_deterministic
def allocate_amount(total: Decimal, weights: Sequence[Decimal], quantum: Decimal = CENT) -> list[Decimal]:
    """Répartit ``total`` (arrondi HALF_UP au quantum) au prorata des poids, somme exacte.

    Méthode du plus fort reste ; égalité départagée par l'ordre des lignes (déterministe).
    Poids tous nuls => répartition égale.
    """
    if not weights:
        raise PricingError("aucune ligne à ventiler")
    amount = as_decimal(total, "total").quantize(quantum, rounding=ROUND_HALF_UP)
    ws = [as_decimal(w, "poids") for w in weights]
    if any(w < 0 for w in ws):
        raise PricingError("poids négatif")
    if sum(ws) == 0:
        ws = [ONE] * len(ws)
    wsum = sum(ws)
    sign = -1 if amount < 0 else 1
    units = int(abs(amount) / quantum)
    raw = [Decimal(units) * w / wsum for w in ws]
    floors = [int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in raw]
    remainder = units - sum(floors)
    order = sorted(range(len(ws)), key=lambda i: (-(raw[i] - floors[i]), i))
    for i in order[:remainder]:
        floors[i] += 1
    return [Decimal(sign * f) * quantum for f in floors]


@_deterministic
def allocate_inbound_costs(
    total_chf: Decimal,
    lines: Sequence[AllocationLine],
    basis: Literal["value", "quantity"] = "value",
) -> tuple[AllocatedCost, ...]:
    """Ventile un transport amont / frais de dédouanement global sur les lignes d'une réception.

    ``basis="value"`` (défaut, recommandé : les frais suivent la valeur) ou ``"quantity"``.
    Retourne le total par ligne (0.01, somme exacte) et le coût unitaire (0.0001) à injecter
    dans ``LandedCostInput.inbound_freight_alloc`` / ``customs_and_fees``.
    """
    if as_decimal(total_chf, "total_chf") < 0:
        raise PricingError("montant à ventiler négatif")
    if basis not in ("value", "quantity"):
        raise PricingError(f"base de ventilation inconnue : {basis}")
    keys = [ln.key for ln in lines]
    if len(set(keys)) != len(keys):
        raise PricingError("clés de ventilation en double")
    weights = [ln.value if basis == "value" else Decimal(ln.qty) for ln in lines]
    shares = allocate_amount(total_chf, weights)
    return tuple(
        AllocatedCost(key=ln.key, qty=ln.qty, allocated_total=share, per_unit=q4(share / Decimal(ln.qty)))
        for ln, share in zip(lines, shares)
    )


# ------------------------------------------------------------------ floor price


def _denominator(params: PricingParams) -> Decimal:
    return (ONE - params.target_margin) / (ONE + params.vat_rate_sales) - params.payment_pct


def _fixed_costs(params: PricingParams, per_order_costs: bool) -> Decimal:
    return params.per_order_costs if per_order_costs else ZERO


@_deterministic
def floor_price_exact(C: Decimal, params: PricingParams, *, per_order_costs: bool = True) -> Decimal:
    """Prix plancher exact (non arrondi) à la marge cible m.

    ``per_order_costs=False`` (règle petits produits) exclut b, L, R, A, supportés une fois
    par commande et contrôlés au niveau panier. Lève PricingError si dénominateur ≤ 0.
    """
    cost = as_decimal(C, "C")
    if cost < 0:
        raise PricingError("coût rendu négatif")
    den = _denominator(params)
    if den <= 0:
        raise PricingError(f"dénominateur (1 − m)/(1 + t) − r = {den} ≤ 0 : paramètres incohérents")
    return (cost + _fixed_costs(params, per_order_costs)) / den


def floor_price(C: Decimal, params: PricingParams, *, per_order_costs: bool = True) -> Decimal:
    """Prix plancher BP §4, arrondi HALF_UP à 0.01 (ex. 208.7949… -> 208.79)."""
    return q2(floor_price_exact(C, params, per_order_costs=per_order_costs))


@_deterministic
def order_floor_price_exact(C: Decimal, params: PricingParams) -> Decimal:
    """Prix TTC minimal pour qu'une commande d'une seule unité contribue ``hard_floor_chf_per_order``."""
    cost = as_decimal(C, "C")
    den = ONE / (ONE + params.vat_rate_sales) - params.payment_pct
    if den <= 0:
        raise PricingError("dénominateur 1/(1 + t) − r ≤ 0")
    return (cost + params.per_order_costs + params.hard_floor_chf_per_order) / den


@_deterministic
def round_up_retail(
    p: Decimal,
    ending: Decimal | None = None,
    *,
    tiers: Sequence[RoundingTier] | None = None,
) -> Decimal:
    """Plus petit point de prix retail ≥ ``p`` (arrondi **vers le haut**, jamais vers le bas).

    * ``ending`` fourni : règle simple « prochain X.ending ≥ p » (pas de 1 CHF), ex.
      ``round_up_retail(208.79, Decimal("0.90")) == 208.90``.
    * sinon grille par paliers (défaut :data:`DEFAULT_ROUNDING_TIERS`, configurable) :
      < 10 CHF -> X.50/X.90 ; 10–99.99 -> X.90 ; ≥ 100 -> X4.90/X9.90, ce qui reproduit
      l'exemple BP §4 (208.79 -> 209.90).

    Un prix déjà sur la grille est conservé. ``p`` doit être > 0. L'appelant doit
    revérifier la marge après arrondi (fait par :func:`decide_price`).
    """
    price = as_decimal(p, "p")
    if price <= 0:
        raise PricingError("prix à arrondir ≤ 0")
    if ending is not None:
        tiers = (RoundingTier(min_price=ZERO, step=ONE, endings=(as_decimal(ending, "ending"),)),)
    grid = tuple(tiers) if tiers is not None else DEFAULT_ROUNDING_TIERS
    if not grid or grid[0].min_price != 0:
        raise PricingError("grille d'arrondi invalide (doit commencer à 0)")
    idx = max(i for i, t in enumerate(grid) if t.min_price <= price)
    target = price
    while True:
        tier = grid[idx]
        upper = grid[idx + 1].min_price if idx + 1 < len(grid) else None
        low = max(target, tier.min_price)
        n0 = (low / tier.step).to_integral_value(rounding=ROUND_FLOOR)
        candidates = sorted(n * tier.step + e for n in (n0, n0 + 1) for e in tier.endings)
        best = next(c for c in candidates if c >= low)
        if upper is None or best < upper:
            return best.quantize(CENT)
        idx += 1
        target = upper


# ----------------------------------------------------------------- contribution


@_deterministic
def contribution_breakdown(
    price_ttc: Decimal, C: Decimal, params: PricingParams, *, per_order_costs: bool = True
) -> ContributionBreakdown:
    """Contribution d'une vente unitaire au prix public TTC (BP §4, exemple 199.90).

    net = P/(1+t) ; paiement = P×r + b ; contribution = net − paiement − C − L − R − A.
    ``per_order_costs=False`` : petit produit additionnel (b, L, R, A exclus).
    """
    price = as_decimal(price_ttc, "price_ttc")
    cost = as_decimal(C, "C")
    if price <= 0:
        raise PricingError("prix TTC ≤ 0")
    if cost < 0:
        raise PricingError("coût rendu négatif")
    net = price / (ONE + params.vat_rate_sales)
    payment = price * params.payment_pct + (params.payment_fixed if per_order_costs else ZERO)
    other = (
        params.logistics_cost + params.after_sales_provision + params.acquisition_cost if per_order_costs else ZERO
    )
    net_q = q2(net)
    cost_q = q2(cost)
    variable_q = q2(payment + other)
    contrib = net_q - cost_q - variable_q
    pct = q4(contrib / net_q) if net_q > 0 else Decimal("-1")
    return ContributionBreakdown(
        price_ttc=q2(price),
        net_revenue=net_q,
        vat=q2(price) - net_q,
        payment_fees=q2(payment),
        product_cost=cost_q,
        per_order_costs=q2(other),
        contribution_chf=contrib,
        contribution_pct=pct,
    )


def contribution(
    price_ttc: Decimal, C: Decimal, params: PricingParams, *, per_order_costs: bool = True
) -> tuple[Decimal, Decimal]:
    """(contribution CHF, fraction du CA net) — 199.90 => (30.62, 0.1656) avec les paramètres BP."""
    b = contribution_breakdown(price_ttc, C, params, per_order_costs=per_order_costs)
    return b.contribution_chf, b.contribution_pct


@_deterministic
def _exact_contribution(price: Decimal, cost: Decimal, params: PricingParams, per_order_costs: bool) -> tuple[Decimal, Decimal]:
    net = price / (ONE + params.vat_rate_sales)
    fixed = _fixed_costs(params, per_order_costs)
    return net - price * params.payment_pct - cost - fixed, net


def is_price_anomaly(new: Decimal, reference: Decimal, factor: Decimal = Decimal("10")) -> bool:
    """Vrai si ``new`` ≥ reference × factor ou ≤ reference / factor (signal « prix ×10 »)."""
    n = as_decimal(new, "new")
    ref = as_decimal(reference, "reference")
    f = as_decimal(factor, "factor")
    if ref <= 0 or f <= 1:
        raise PricingError("référence ≤ 0 ou facteur ≤ 1")
    with localcontext(_CTX):
        return n >= ref * f or n <= ref / f


# --------------------------------------------------------------------- decision


class _Verdict:
    """Accumulateur de statut/motifs (gravité maximale retenue)."""

    def __init__(self) -> None:
        self.status = DecisionStatus.OK
        self.reasons: list[str] = []
        self.notes: list[str] = []

    def add(self, reason: Reason, status: DecisionStatus = DecisionStatus.OK, note: str | None = None) -> None:
        if reason.value not in self.reasons:
            self.reasons.append(reason.value)
        if status.severity > self.status.severity:
            self.status = status
        if note:
            self.notes.append(note)


def _meets_target(price: Decimal, cost: Decimal, params: PricingParams, small: bool) -> bool:
    exact_c, exact_net = _exact_contribution(price, cost, params, not small)
    if exact_c < params.target_margin * exact_net - _EXACT_TOLERANCE:
        return False
    if not small and exact_c < params.hard_floor_chf_per_order - _EXACT_TOLERANCE:
        return False
    chf, pct = contribution(price, cost, params, per_order_costs=not small)
    if pct < params.target_margin:
        return False
    return small or chf >= params.hard_floor_chf_per_order


def _floor_violations(chf: Decimal, pct: Decimal, params: PricingParams, small: bool) -> list[Reason]:
    out = []
    if pct < params.hard_floor_margin:
        out.append(Reason.BELOW_HARD_FLOOR)
    if not small and chf < params.hard_floor_chf_per_order:
        out.append(Reason.BELOW_ORDER_FLOOR_CHF)
    return out


def _is_small(cost: Decimal, params: PricingParams, small_product: bool | None) -> bool:
    if small_product is not None:
        return small_product
    return params.small_product_max_cost is not None and cost <= params.small_product_max_cost


@_deterministic
def decide_price(
    C: Decimal,
    params: PricingParams,
    market_ref: Decimal | None = None,
    current_public: Decimal | None = None,
    unknown_fields: Sequence[str] = (),
    *,
    candidate_price: Decimal | None = None,
    small_product: bool | None = None,
    offer_stale: bool = False,
    previous_cost: Decimal | None = None,
) -> PriceDecision:
    """Applique la table de règles BP §5 au coût rendu ``C`` et renvoie une décision tracée.

    1. C ≤ 0 -> BLOCKED ; C ≥ ×10 / ≤ ÷10 de ``previous_cost`` -> BLOCKED (anomalie).
    2. Prix rentable = max(plancher cible m, plancher 8 CHF par commande unitaire) ;
       petit produit (``small_product`` ou C ≤ ``small_product_max_cost``) : frais par
       commande exclus et plancher CHF reporté au panier.
    3. Arrondi retail vers le haut puis **revérification** (exacte et affichée) ; si échec,
       point de grille suivant.
    4. ``candidate_price`` (prix manuel/promo) : < plancher dur 12 % ou < 8 CHF -> BLOCKED ;
       < cible -> REVIEW.
    5. Prix rentable > ``market_ref`` × (1 + 10 %) -> REVIEW (le prix n'est pas baissé).
    6. Variation vs ``current_public`` (prix public d'il y a 24 h) > 5 % -> REVIEW ; ×10 -> BLOCKED.
    7. ``unknown_fields`` non vide -> DRAFT (aucun prix public nouveau).
    8. ``offer_stale`` -> ``restock_eligible=False`` (le stock local reste vendable).
    """
    cost = as_decimal(C, "C")
    unknown = sorted({f.strip() for f in unknown_fields if f and f.strip()})
    candidate = as_decimal(candidate_price, "candidate_price") if candidate_price is not None else None
    if candidate is not None and candidate <= 0:
        raise PricingError("prix candidat ≤ 0")
    prev = as_decimal(previous_cost, "previous_cost") if previous_cost is not None else None
    if prev is not None and prev <= 0:
        raise PricingError("previous_cost ≤ 0")
    market = as_decimal(market_ref, "market_ref") if market_ref is not None else None
    current = as_decimal(current_public, "current_public") if current_public is not None else None
    inputs_hash = canonical_hash(
        {
            "fn": "decide_price",
            "C": cost,
            "params": params,
            "market_ref": market,
            "current_public": current,
            "unknown_fields": unknown,
            "candidate_price": candidate,
            "small_product": small_product,
            "offer_stale": offer_stale,
            "previous_cost": prev,
        }
    )
    v = _Verdict()
    restock_eligible = not offer_stale
    if offer_stale:
        v.add(Reason.STALE_OFFER, note="Offre amont > 24 h : pas de réassort ni de nouvelle promesse de dispo.")
    if unknown:
        v.add(Reason.UNKNOWN_FIELDS, DecisionStatus.DRAFT, note="Champs inconnus : " + ", ".join(unknown))

    def bare(small: bool = False) -> PriceDecision:
        return PriceDecision(
            floor_price=None,
            recommended_price=None,
            contribution_chf=None,
            contribution_pct=None,
            status=v.status,
            reasons=tuple(v.reasons),
            rules_version=params.rules_version,
            inputs_hash=inputs_hash,
            landed_cost=cost,
            small_product=small,
            restock_eligible=restock_eligible,
            notes=tuple(v.notes),
        )

    if cost <= 0:
        v.add(Reason.ZERO_OR_NEGATIVE_COST, DecisionStatus.BLOCKED)
        return bare()
    if prev is not None and is_price_anomaly(cost, prev, params.price_anomaly_factor):
        v.add(
            Reason.PRICE_ANOMALY,
            DecisionStatus.BLOCKED,
            note=f"Coût {q2(cost)} vs référence {q2(prev)} : facteur ≥ {params.price_anomaly_factor}.",
        )
    small = _is_small(cost, params, small_product)
    if small:
        v.add(Reason.SMALL_PRODUCT_ADDON)
    try:
        floor_exact = floor_price_exact(cost, params, per_order_costs=not small)
        profitable = floor_exact
        if not small:
            order_floor = order_floor_price_exact(cost, params)
            if order_floor > floor_exact:
                profitable = order_floor
                v.add(Reason.ORDER_FLOOR_CHF_BINDING)
    except PricingError as exc:
        v.add(Reason.DENOMINATOR_NOT_POSITIVE, DecisionStatus.BLOCKED, note=str(exc))
        return bare(small)

    recommended = round_up_retail(profitable, tiers=params.rounding_tiers)
    for _ in range(_MAX_RECHECK_STEPS):
        if _meets_target(recommended, cost, params, small):
            break
        recommended = round_up_retail(recommended + CENT, tiers=params.rounding_tiers)
    else:  # pragma: no cover - mathématiquement inatteignable, garde-fou
        v.add(Reason.ROUNDING_RECHECK_FAILED, DecisionStatus.BLOCKED)

    evaluated = candidate if candidate is not None else recommended
    chf, pct = contribution(evaluated, cost, params, per_order_costs=not small)
    if candidate is not None:
        violations = _floor_violations(chf, pct, params, small)
        for reason in violations:
            v.add(reason, DecisionStatus.BLOCKED, note=f"Prix candidat {q2(candidate)} : contribution {chf} CHF ({pct}).")
        if not violations and pct < params.target_margin:
            v.add(Reason.BELOW_TARGET_MARGIN, DecisionStatus.REVIEW)

    if market is not None:
        if market <= 0:
            v.add(Reason.INVALID_MARKET_REF, DecisionStatus.REVIEW)
        elif profitable > market * (ONE + params.market_review_threshold):
            v.add(
                Reason.ABOVE_MARKET,
                DecisionStatus.REVIEW,
                note=f"Prix rentable {q2(profitable)} > marché {q2(market)} + {params.market_review_threshold}.",
            )

    if current is not None:
        if current <= 0:
            v.add(Reason.INVALID_CURRENT_PRICE, DecisionStatus.REVIEW)
        else:
            if is_price_anomaly(evaluated, current, params.price_anomaly_factor):
                v.add(Reason.PRICE_ANOMALY, DecisionStatus.BLOCKED, note=f"{evaluated} vs public {q2(current)}.")
            elif abs(evaluated - current) / current > params.max_daily_price_change:
                v.add(
                    Reason.DAILY_CHANGE_ABOVE_CAP,
                    DecisionStatus.REVIEW,
                    note=(
                        f"Variation {(abs(evaluated - current) / current).quantize(Decimal('0.000001'))}"
                        f" > plafond {params.max_daily_price_change}."
                    ),
                )
            cur_chf, cur_pct = contribution(current, cost, params, per_order_costs=not small)
            if _floor_violations(cur_chf, cur_pct, params, small):
                v.add(Reason.CURRENT_PRICE_BELOW_HARD_FLOOR, DecisionStatus.REVIEW)

    return PriceDecision(
        floor_price=q2(floor_exact),
        recommended_price=recommended,
        contribution_chf=chf,
        contribution_pct=pct,
        status=v.status,
        reasons=tuple(v.reasons),
        rules_version=params.rules_version,
        inputs_hash=inputs_hash,
        profitable_price=q2(profitable),
        evaluated_price=q2(evaluated),
        landed_cost=q2(cost),
        small_product=small,
        restock_eligible=restock_eligible,
        notes=tuple(v.notes),
    )


# ------------------------------------------------------------------- offers


_IDENTITY_FIELDS = ("gtin", "language", "extension", "format", "content", "sealed")
_COMMERCIAL_FIELDS = ("units_per_pack", "price", "currency", "price_includes_vat", "vat_rate", "ship_from_country")


def offer_unknown_fields(offer: SupplierOffer) -> list[str]:
    """Champs critiques inconnus d'une offre (identité + prix/taxe/conditionnement/origine).

    ``language`` = ``UNKNOWN`` compte comme inconnu. ``vat_rate`` est requis même pour un
    prix HT : il dit si une TVA s'ajoutera à la facture (0 = facture export HT).
    """
    missing = list(offer.identity().missing_fields())
    for name in _COMMERCIAL_FIELDS:
        if getattr(offer, name) is None:
            missing.append(name)
    return missing


def landed_input_from_offer(
    offer: SupplierOffer,
    *,
    vat_mode: VatMode,
    fx_rate_to_chf: Decimal | None = None,
    fx_source: str | None = None,
    fx_date: date | None = None,
    inbound_freight_alloc: Decimal = ZERO,
    customs_and_fees: Decimal = ZERO,
    import_vat: Decimal = ZERO,
    order_qty: int | None = None,
) -> LandedCostInput:
    """Construit un :class:`LandedCostInput` depuis une offre ; IncompleteDataError si champ manquant.

    Devise CHF : taux 1, source ``"CHF"``. Autre devise : taux, source et date obligatoires
    (l'IA ne choisit jamais un taux de change, BP §4).
    """
    missing = [
        name
        for name in ("price", "currency", "price_includes_vat", "vat_rate", "units_per_pack")
        if getattr(offer, name) is None
    ]
    if offer.currency is not None and offer.currency != "CHF":
        if fx_rate_to_chf is None or not fx_source or fx_date is None:
            missing.append("fx_rate")
    if missing:
        raise IncompleteDataError(missing)
    assert offer.price is not None and offer.currency is not None and offer.vat_rate is not None
    assert offer.price_includes_vat is not None and offer.units_per_pack is not None
    is_chf = offer.currency == "CHF"
    return LandedCostInput(
        purchase_net=offer.price,
        currency=offer.currency,
        fx_rate_to_chf=ONE if is_chf else fx_rate_to_chf,
        fx_source="CHF" if is_chf else fx_source,
        fx_date=fx_date if fx_date is not None else offer.source_ts.date(),
        price_includes_vat=offer.price_includes_vat,
        supplier_vat_rate=offer.vat_rate,
        units_per_pack=offer.units_per_pack,
        inbound_freight_alloc=inbound_freight_alloc,
        customs_and_fees=customs_and_fees,
        import_vat=import_vat,
        vat_mode=vat_mode,
        supplier_vat_country=offer.effective_vat_country,
        tier_discounts=offer.tier_discounts,
        order_qty=order_qty,
    )


@_deterministic
def evaluate_offer(
    offer: SupplierOffer,
    params: PricingParams,
    *,
    now: datetime,
    fx_rate_to_chf: Decimal | None = None,
    fx_source: str | None = None,
    fx_date: date | None = None,
    inbound_freight_alloc: Decimal | None = None,
    customs_and_fees: Decimal | None = None,
    import_vat: Decimal | None = None,
    order_qty: int | None = None,
    market_ref: Decimal | None = None,
    current_public: Decimal | None = None,
    previous_cost: Decimal | None = None,
    candidate_price: Decimal | None = None,
    small_product: bool | None = None,
    expected_language: str = "FR",
    max_age: timedelta = timedelta(hours=24),
) -> PriceDecision:
    """Décision de prix de bout en bout pour une offre fournisseur normalisée.

    Frais ``None`` = inconnus. Pour une offre expédiée de Suisse, dédouanement et TVA import
    valent 0 par défaut ; sinon ils doivent être fournis (TVA import non requise en
    EFFECTIVE car récupérable). Transport amont : toujours requis (0 explicite si franco).
    Langue différente de ``expected_language`` -> BLOCKED ; prix 0 -> BLOCKED ; champ
    inconnu -> DRAFT (le coût partiel est alors indicatif) ; offre > ``max_age`` ->
    ``restock_eligible=False``.
    """
    unknown = offer_unknown_fields(offer)
    domestic = offer.ship_from_country == "CH"
    freight = inbound_freight_alloc
    if freight is None:
        unknown.append("inbound_freight_alloc")
    customs = customs_and_fees
    if customs is None:
        if not domestic:
            unknown.append("customs_and_fees")
    ivat = import_vat
    if ivat is None:
        if not domestic and params.mode is VatMode.NOT_REGISTERED:
            unknown.append("import_vat")
    if offer.currency not in (None, "CHF") and (fx_rate_to_chf is None or not fx_source or fx_date is None):
        unknown.append("fx_rate")
    stale = is_stale(offer.source_ts, now, max_age)
    extra = _Verdict()
    language = offer.language
    if language not in (None, "UNKNOWN") and language != expected_language.upper():
        extra.add(
            Reason.LANGUAGE_MISMATCH,
            DecisionStatus.BLOCKED,
            note=f"Langue offre {language} ≠ {expected_language.upper()}.",
        )
    if offer.price is not None and offer.price == 0:
        extra.add(Reason.ZERO_PRICE, DecisionStatus.BLOCKED)
    inputs_hash = canonical_hash(
        {
            "fn": "evaluate_offer",
            "offer": offer,
            "params": params,
            "now": now,
            "fx": [fx_rate_to_chf, fx_source, fx_date],
            "costs": [inbound_freight_alloc, customs_and_fees, import_vat],
            "order_qty": order_qty,
            "market_ref": market_ref,
            "current_public": current_public,
            "previous_cost": previous_cost,
            "candidate_price": candidate_price,
            "small_product": small_product,
            "expected_language": expected_language,
            "max_age": max_age,
        }
    )
    cost: Decimal | None = None
    if offer.price is not None and offer.price > 0:
        try:
            inp = landed_input_from_offer(
                offer,
                vat_mode=params.mode,
                fx_rate_to_chf=fx_rate_to_chf,
                fx_source=fx_source,
                fx_date=fx_date,
                inbound_freight_alloc=freight if freight is not None else ZERO,
                customs_and_fees=customs if customs is not None else ZERO,
                import_vat=ivat if ivat is not None else ZERO,
                order_qty=order_qty,
            )
            cost = landed_unit_cost(inp)
        except IncompleteDataError:
            cost = None
    if cost is None:
        v = _Verdict()
        if unknown:
            v.add(Reason.UNKNOWN_FIELDS, DecisionStatus.DRAFT, note="Champs inconnus : " + ", ".join(sorted(set(unknown))))
        if stale:
            v.add(Reason.STALE_OFFER)
        for code, note in zip(extra.reasons, extra.notes + [""] * len(extra.reasons)):
            v.add(Reason(code), DecisionStatus.BLOCKED, note=note or None)
        return PriceDecision(
            floor_price=None,
            recommended_price=None,
            contribution_chf=None,
            contribution_pct=None,
            status=v.status if v.status is not DecisionStatus.OK else DecisionStatus.DRAFT,
            reasons=tuple(v.reasons),
            rules_version=params.rules_version,
            inputs_hash=inputs_hash,
            restock_eligible=not stale,
            notes=tuple(v.notes),
        )
    decision = decide_price(
        cost,
        params,
        market_ref,
        current_public,
        unknown,
        candidate_price=candidate_price,
        small_product=small_product,
        offer_stale=stale,
        previous_cost=previous_cost,
    )
    status = decision.status
    if extra.status.severity > status.severity:
        status = extra.status
    reasons = tuple(dict.fromkeys(decision.reasons + tuple(extra.reasons)))
    return decision.replace(
        status=status,
        reasons=reasons,
        notes=decision.notes + tuple(extra.notes),
        inputs_hash=inputs_hash,
    )


# ---------------------------------------------------------------------- basket


@_deterministic
def basket_contribution(
    lines: Sequence[BasketLine],
    params: PricingParams,
    shipping_charged: Decimal = ZERO,
    discount: Decimal | Discount | None = None,
    *,
    shipping_cost_actual: Decimal | None = None,
) -> BasketResult:
    """Contribution d'une commande multi-produits ; frais par commande comptés **une fois**.

    * ``shipping_charged`` : port TTC payé par le client (0 = port gratuit).
    * ``discount`` : montant TTC (Decimal) ou :class:`Discount` (% ou montant, code promo),
      appliqué aux produits, plafonné à leur montant ; même moteur pour toutes les promos.
    * ``shipping_cost_actual`` : coût logistique réel de la commande (préparation + port, HT si
      EFFECTIVE). Absent : hypothèse BP §10 « port facturé = port réel » => L + port facturé HT,
      motif SHIPPING_COST_ASSUMED. Pour un port gratuit, fournir le coût réel.
    * Statut : BLOCKED si contribution < 12 % du CA net, < 8 CHF, ou CA net ≤ 0 ; sinon OK
      (motif informatif BELOW_TARGET_MARGIN sous 20 %).
    """
    if not lines:
        raise PricingError("panier vide")
    skus = [ln.sku for ln in lines]
    if len(set(skus)) != len(skus):
        raise PricingError("SKU en double dans le panier : regrouper les quantités")
    ship = as_decimal(shipping_charged, "shipping_charged")
    if ship < 0:
        raise PricingError("port facturé négatif")
    actual = as_decimal(shipping_cost_actual, "shipping_cost_actual") if shipping_cost_actual is not None else None
    if actual is not None and actual < 0:
        raise PricingError("coût logistique réel négatif")
    v = _Verdict()
    line_goods = [Decimal(ln.qty) * ln.unit_price_ttc for ln in lines]
    goods = sum(line_goods, ZERO)
    if discount is None:
        disc_obj: Discount | None = None
        disc = ZERO
    else:
        disc_obj = discount if isinstance(discount, Discount) else Discount(kind="AMOUNT", value=as_decimal(discount, "discount"))
        disc = q2(goods * disc_obj.value) if disc_obj.kind == "PERCENT" else q2(disc_obj.value)
    if disc > goods:
        disc = goods
        v.add(Reason.DISCOUNT_CAPPED)
    total_paid = goods - disc + ship
    t = params.vat_rate_sales
    net = total_paid / (ONE + t)
    payment = total_paid * params.payment_pct + params.payment_fixed if total_paid > 0 else ZERO
    product_cost = sum((Decimal(ln.qty) * ln.unit_cost for ln in lines), ZERO)
    ship_net = ship / (ONE + t)
    if actual is None:
        logistics = params.logistics_cost + ship_net
        v.add(Reason.SHIPPING_COST_ASSUMED)
    else:
        logistics = actual
    order_costs = payment + logistics + params.after_sales_provision + params.acquisition_cost

    net_q = q2(net)
    product_q = q2(product_cost)
    order_q = q2(order_costs)
    contrib = net_q - product_q - order_q
    pct = q4(contrib / net_q) if net_q > 0 else None
    if net_q <= 0:
        v.add(Reason.NON_POSITIVE_NET_REVENUE, DecisionStatus.BLOCKED)
    else:
        assert pct is not None
        for reason in _floor_violations(contrib, pct, params, small=False):
            v.add(reason, DecisionStatus.BLOCKED)
        if pct >= params.hard_floor_margin and pct < params.target_margin:
            v.add(Reason.BELOW_TARGET_MARGIN)

    disc_lines = allocate_amount(disc, line_goods)
    after_disc = [g - d for g, d in zip(line_goods, disc_lines)]
    net_lines = allocate_amount(net_q, after_disc)
    cost_lines = allocate_amount(product_q, [Decimal(ln.qty) * ln.unit_cost for ln in lines])
    order_lines = allocate_amount(order_q, net_lines)
    results = tuple(
        BasketLineResult(
            sku=ln.sku,
            qty=ln.qty,
            goods_ttc=q2(g),
            discount_ttc=d,
            net_revenue=n,
            product_cost=c,
            allocated_order_costs=o,
            contribution_chf=n - c - o,
        )
        for ln, g, d, n, c, o in zip(lines, line_goods, disc_lines, net_lines, cost_lines, order_lines)
    )
    inputs_hash = canonical_hash(
        {
            "fn": "basket_contribution",
            "lines": list(lines),
            "params": params,
            "shipping_charged": ship,
            "discount": disc_obj,
            "shipping_cost_actual": actual,
        }
    )
    return BasketResult(
        goods_ttc=q2(goods),
        discount_ttc=q2(disc),
        shipping_charged_ttc=q2(ship),
        total_paid_ttc=q2(total_paid),
        net_revenue=net_q,
        vat=q2(total_paid) - net_q,
        payment_fees=q2(payment),
        product_cost=product_q,
        logistics_cost=q2(logistics),
        after_sales=q2(params.after_sales_provision),
        acquisition=q2(params.acquisition_cost),
        shipping_gap=q2(ship_net - logistics),
        contribution_chf=contrib,
        contribution_pct=pct,
        status=v.status,
        reasons=tuple(v.reasons),
        lines=results,
        rules_version=params.rules_version,
        inputs_hash=inputs_hash,
    )
