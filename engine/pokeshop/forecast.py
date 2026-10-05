"""Prévisions mensuelles, seuil de rentabilité, sensibilité, besoin en stock et étoile polaire.

Couvre BP §3, §4, §10 et la métrique unique de pilotage décidée par la propriétaire :
la **contribution nette cumulée** (ventes nettes HT − coût historique − paiement −
logistique − SAV − acquisition − charges fixes), suivie chaque semaine, avec une
**approximation** du stop-loss global.

**Définition unique du stop-loss global** (celle de ``pokeshop.stoploss``, qui fait foi) : perte de
**valeur nette** (cash + stock prudent + créances − dettes) ≥ 20 % du **capital engagé de
référence** (apports − retraits, ou point zéro posé par la propriétaire + apports ultérieurs −
retraits). La projection ne connaît pas la valeur nette : elle l'approche par la contribution
cumulée, ce qui n'est cohérent qu'une fois les coûts de lancement assumés par le point zéro.
Par défaut, :func:`north_star` applique cette définition avec ``capital_engaged=BP_STOPLOSS_REFERENCE``
(point zéro recommandé, option A de ``STOP_LOSS.md`` §5 : 4 200 CHF, **seuil 840 CHF** ; gel projeté en
semaine 13 au rythme du jalon). L'ancienne approximation (8 000 CHF de capital littéral, seuil
1 600 CHF, semaine 28) est **caduque** (revue COH-01) : elle sous-estimait la prudence du moteur d'un
facteur ≈ 2 ; ``capital_engaged=BP_CAPITAL_ENGAGED`` ne sert plus qu'à une comparaison explicite.

Module autonome de l'agent finance : il ne dépend ni de ``pokeshop.pricing`` ni de
``pokeshop.stoploss`` (agent gouvernance, qui fait foi pour l'application des stop-loss).
Tous les montants sont des ``decimal.Decimal`` exacts ; l'arrondi n'intervient
qu'à la présentation (``round_chf``) ou lorsqu'une convention d'arrondi est
explicitement demandée (``unit_rounding``), afin de pouvoir reproduire au centime
les chiffres publiés dans le BP *et* d'en documenter les écarts d'arrondi.

Toutes les valeurs par défaut sont des **hypothèses du BP** (version du
4 octobre 2026), pas des devis : à remplacer par des données réelles avant achat.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Iterable, Sequence

__all__ = [
    "BP_AFTER_SALES_PER_ORDER",
    "BP_BASKET_TTC",
    "BP_CAPITAL_ENGAGED",
    "BP_STOPLOSS_REFERENCE",
    "global_stoploss_threshold",
    "BP_CONTRIBUTION_RATE",
    "BP_FIXED_COSTS",
    "BP_HARD_FLOOR_CHF_PER_ORDER",
    "BP_HARD_FLOOR_PCT",
    "BP_INITIAL_BUDGET",
    "BP_INITIAL_STOCK",
    "BP_MONTHLY_FIXED",
    "BP_PAYMENT_FIXED",
    "BP_PAYMENT_PCT",
    "BP_PRICE_EXAMPLE",
    "BP_PRODUCT_COST_RATIO",
    "BP_REMUNERATION",
    "BP_SALES_OPENING_WEEK",
    "BP_VALIDATION_DAYS",
    "BP_VALIDATION_ORDERS",
    "CENT",
    "CHF",
    "DAYS_PER_MONTH",
    "GLOBAL_STOPLOSS_PCT",
    "VAT_RATE_CH_STANDARD",
    "VAT_REGISTRATION_THRESHOLD",
    "WEEKS_PER_MONTH",
    "WEEKS_PER_YEAR",
    "BpCheck",
    "BreakEven",
    "CheckStatus",
    "ForecastError",
    "NorthStarReport",
    "NorthStarRow",
    "NorthStarWeek",
    "PriceCheck",
    "ScenarioAssumptions",
    "ScenarioResult",
    "SensitivityCell",
    "StockNeed",
    "TimeValuation",
    "ValidationCheck",
    "VatThresholdCheck",
    "WorkingCapitalAssumptions",
    "WorkingCapitalNeed",
    "basket_ht",
    "break_even",
    "bp_scenarios",
    "ceil_int",
    "contribution_at_price",
    "floor_price_crosscheck",
    "net_of_vat",
    "north_star",
    "project_north_star",
    "round_chf",
    "round_up_to_ending",
    "run_bp_scenarios",
    "run_scenario",
    "sensitivity_grid",
    "stock_need",
    "summarize_checks",
    "time_valuation",
    "to_decimal",
    "vat_threshold_check",
    "verify_against_bp",
    "working_capital_need",
]

# ---------------------------------------------------------------------------
# Constantes (hypothèses BP, versionnées avec le code)
# ---------------------------------------------------------------------------

CHF = Decimal("1")
CENT = Decimal("0.01")

#: Taux normal suisse au 4.10.2026 (BP §4, source S6 AFC).
VAT_RATE_CH_STANDARD = Decimal("0.081")
#: Seuil général d'assujettissement TVA, CHF de CA déterminant / an (BP §4, S6).
VAT_REGISTRATION_THRESHOLD = Decimal("100000")
#: Panier produits moyen TTC (BP §10, hypothèse).
BP_BASKET_TTC = Decimal("95")
#: Contribution produit avant acquisition, % du CA HT (BP §10, hypothèse).
BP_CONTRIBUTION_RATE = Decimal("0.22")
#: Charges fixes mensuelles hors publicité et rémunération (BP §3).
BP_FIXED_COSTS = Decimal("400")
#: Rémunération budgétée utilisée pour le second seuil (BP §10).
BP_REMUNERATION = Decimal("2000")
#: Coût produit en % du CA net (BP §10, « par hypothèse »).
BP_PRODUCT_COST_RATIO = Decimal("0.70")
#: Stock initial acheté rendu Suisse (BP §3).
BP_INITIAL_STOCK = Decimal("3000")
#: Plancher dur de contribution (BP §5) : 12 % et 8 CHF par commande.
BP_HARD_FLOOR_PCT = Decimal("0.12")
BP_HARD_FLOOR_CHF_PER_ORDER = Decimal("8")
#: Convention de calcul : mois de 30 jours, 52/12 semaines par mois.
DAYS_PER_MONTH = 30
WEEKS_PER_YEAR = 52
WEEKS_PER_MONTH = Decimal(WEEKS_PER_YEAR) / Decimal(12)
#: Frais de paiement et provision SAV de l'exemple BP §4 (hypothèses, pas un contrat PSP).
BP_PAYMENT_PCT = Decimal("0.025")
BP_PAYMENT_FIXED = Decimal("0.30")
BP_AFTER_SALES_PER_ORDER = Decimal("1")
#: Apports du budget initial BP §3 (hypothèse à confirmer) : capital engagé **littéral**, sans point zéro.
BP_CAPITAL_ENGAGED = Decimal("8000")
#: Référence du stop-loss global avec le point zéro recommandé (STOP_LOSS.md §5, option A, à J3 avec C03) :
#: 8 000 − 2 900 de lancement − 900 de décote prudente du stock = 4 200 CHF => seuil 840 CHF.
BP_STOPLOSS_REFERENCE = Decimal("4200")
#: Stop-loss global du mandat : perte cumulée ≥ 20 % du capital engagé ⇒ tout gelé.
GLOBAL_STOPLOSS_PCT = Decimal("0.20")
#: Plan 90 jours BP §9 : ouverture douce aux jours 31 à 45 ⇒ ventes dès la semaine 5.
BP_SALES_OPENING_WEEK = 5
#: Jalons de validation BP §1 : 30 commandes payées sur les 60 premiers jours de vente.
BP_VALIDATION_DAYS = 60
BP_VALIDATION_ORDERS = 30


class ForecastError(ValueError):
    """Entrée invalide ou calcul impossible (ex. contribution par commande ≤ 0)."""


# ---------------------------------------------------------------------------
# Utilitaires Decimal
# ---------------------------------------------------------------------------


def to_decimal(value: Decimal | int | str, name: str = "valeur") -> Decimal:
    """Convertit en Decimal en refusant les float (non déterministes)."""
    if isinstance(value, bool):
        raise ForecastError(f"{name} : booléen refusé")
    if isinstance(value, float):
        raise ForecastError(f"{name} : float refusé, utiliser Decimal ou str")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ForecastError(f"{name} : valeur non finie")
        return value
    if isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except Exception as exc:  # decimal.InvalidOperation
            raise ForecastError(f"{name} : {value!r} n'est pas un nombre") from exc
        if not result.is_finite():
            raise ForecastError(f"{name} : valeur non finie")
        return result
    raise ForecastError(f"{name} : type {type(value).__name__} non supporté")


def round_chf(amount: Decimal, quantum: Decimal = CENT) -> Decimal:
    """Arrondi commercial (demi supérieur) au quantum donné (CHF ou centime)."""
    return amount.quantize(quantum, rounding=ROUND_HALF_UP)


def ceil_int(value: Decimal) -> int:
    """Arrondi à l'entier supérieur (nombre de commandes nécessaires)."""
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def net_of_vat(amount_ttc: Decimal, vat_rate: Decimal) -> Decimal:
    """Montant hors TVA à partir d'un montant TTC : ``TTC / (1 + t)``."""
    return amount_ttc / (Decimal(1) + vat_rate)


def basket_ht(basket_ttc: Decimal = BP_BASKET_TTC, vat_rate: Decimal = VAT_RATE_CH_STANDARD) -> Decimal:
    """Panier moyen HT exact (95 TTC à 8,1 % ⇒ 87,8816 HT)."""
    return net_of_vat(to_decimal(basket_ttc, "basket_ttc"), to_decimal(vat_rate, "vat_rate"))


def _check_rate(value: Decimal, name: str, *, upper_inclusive: bool = True) -> None:
    if value < 0 or value > 1 or (not upper_inclusive and value == 1):
        raise ForecastError(f"{name} doit être compris entre 0 et 1 (reçu {value})")


def _check_non_negative(value: Decimal, name: str) -> None:
    if value < 0:
        raise ForecastError(f"{name} ne peut pas être négatif (reçu {value})")


def _check_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ForecastError(f"{name} doit être un entier")


# ---------------------------------------------------------------------------
# Scénarios mensuels (BP §10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioAssumptions:
    """Hypothèses d'un scénario mensuel (entité assujettie, méthode effective).

    ``vat_rate`` = 0 permet de simuler une entité non assujettie, à condition de
    fournir un ``contribution_rate`` recalculé (TVA d'achat non récupérable).
    """

    name: str
    orders_per_month: int
    cac: Decimal
    basket_ttc: Decimal = BP_BASKET_TTC
    vat_rate: Decimal = VAT_RATE_CH_STANDARD
    contribution_rate: Decimal = BP_CONTRIBUTION_RATE
    fixed_costs: Decimal = BP_FIXED_COSTS
    remuneration: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.name:
            raise ForecastError("name obligatoire")
        if isinstance(self.orders_per_month, bool) or not isinstance(self.orders_per_month, int):
            raise ForecastError("orders_per_month doit être un entier")
        if self.orders_per_month < 0:
            raise ForecastError("orders_per_month ne peut pas être négatif")
        for attr in ("cac", "basket_ttc", "vat_rate", "contribution_rate", "fixed_costs", "remuneration"):
            object.__setattr__(self, attr, to_decimal(getattr(self, attr), attr))
        if self.basket_ttc <= 0:
            raise ForecastError("basket_ttc doit être > 0")
        _check_rate(self.vat_rate, "vat_rate", upper_inclusive=False)
        _check_rate(self.contribution_rate, "contribution_rate")
        _check_non_negative(self.cac, "cac")
        _check_non_negative(self.fixed_costs, "fixed_costs")
        _check_non_negative(self.remuneration, "remuneration")


@dataclass(frozen=True)
class ScenarioResult:
    """Résultat exact d'un scénario mensuel ; ``rounded()`` pour l'affichage BP."""

    assumptions: ScenarioAssumptions
    basket_ht: Decimal
    revenue_ttc: Decimal
    revenue_ht: Decimal
    vat_collected: Decimal
    contribution_before_acquisition: Decimal
    acquisition_total: Decimal
    fixed_costs: Decimal
    result_before_remuneration: Decimal
    remuneration: Decimal
    result_after_remuneration: Decimal
    contribution_per_order: Decimal
    contribution_per_order_after_cac: Decimal
    contribution_after_cac_pct: Decimal
    annual_revenue_ttc: Decimal
    annual_revenue_ht: Decimal

    def rounded(self) -> dict[str, Decimal]:
        """Valeurs arrondies comme dans le BP : CHF entiers, centimes par commande."""
        return {
            "orders": Decimal(self.assumptions.orders_per_month),
            "basket_ht": round_chf(self.basket_ht, CENT),
            "revenue_ttc": round_chf(self.revenue_ttc, CHF),
            "revenue_ht": round_chf(self.revenue_ht, CHF),
            "vat_collected": round_chf(self.vat_collected, CHF),
            "contribution_before_acquisition": round_chf(self.contribution_before_acquisition, CHF),
            "cac": round_chf(self.assumptions.cac, CENT),
            "acquisition_total": round_chf(self.acquisition_total, CHF),
            "fixed_costs": round_chf(self.fixed_costs, CHF),
            "result_before_remuneration": round_chf(self.result_before_remuneration, CHF),
            "remuneration": round_chf(self.remuneration, CHF),
            "result_after_remuneration": round_chf(self.result_after_remuneration, CHF),
            "contribution_per_order": round_chf(self.contribution_per_order, CENT),
            "contribution_per_order_after_cac": round_chf(self.contribution_per_order_after_cac, CENT),
            "contribution_after_cac_pct": round_chf(self.contribution_after_cac_pct, Decimal("0.0001")),
            "annual_revenue_ttc": round_chf(self.annual_revenue_ttc, CHF),
            "annual_revenue_ht": round_chf(self.annual_revenue_ht, CHF),
        }


def run_scenario(assumptions: ScenarioAssumptions) -> ScenarioResult:
    """Calcule un scénario mensuel selon la mécanique du BP §10 (valeurs exactes)."""
    a = assumptions
    orders = Decimal(a.orders_per_month)
    b_ht = net_of_vat(a.basket_ttc, a.vat_rate)
    revenue_ttc = orders * a.basket_ttc
    revenue_ht = net_of_vat(revenue_ttc, a.vat_rate)
    contribution = revenue_ht * a.contribution_rate
    acquisition = orders * a.cac
    result = contribution - acquisition - a.fixed_costs
    per_order = b_ht * a.contribution_rate
    per_order_after_cac = per_order - a.cac
    return ScenarioResult(
        assumptions=a,
        basket_ht=b_ht,
        revenue_ttc=revenue_ttc,
        revenue_ht=revenue_ht,
        vat_collected=revenue_ttc - revenue_ht,
        contribution_before_acquisition=contribution,
        acquisition_total=acquisition,
        fixed_costs=a.fixed_costs,
        result_before_remuneration=result,
        remuneration=a.remuneration,
        result_after_remuneration=result - a.remuneration,
        contribution_per_order=per_order,
        contribution_per_order_after_cac=per_order_after_cac,
        contribution_after_cac_pct=per_order_after_cac / b_ht,
        annual_revenue_ttc=revenue_ttc * 12,
        annual_revenue_ht=revenue_ht * 12,
    )


def bp_scenarios(remuneration: Decimal = Decimal(0)) -> tuple[ScenarioAssumptions, ...]:
    """Les trois scénarios du BP §10 : prudent 40/8, central 100/6, développement 200/5."""
    return (
        ScenarioAssumptions("prudent", 40, Decimal("8"), remuneration=remuneration),
        ScenarioAssumptions("central", 100, Decimal("6"), remuneration=remuneration),
        ScenarioAssumptions("developpement", 200, Decimal("5"), remuneration=remuneration),
    )


def run_bp_scenarios(remuneration: Decimal = Decimal(0)) -> dict[str, ScenarioResult]:
    """Exécute les trois scénarios BP, indexés par nom."""
    return {a.name: run_scenario(a) for a in bp_scenarios(remuneration)}


# ---------------------------------------------------------------------------
# Seuil de rentabilité et sensibilité (BP §10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakEven:
    """Seuil de rentabilité mensuel en commandes."""

    amount_to_cover: Decimal
    contribution_per_order: Decimal
    contribution_per_order_after_cac: Decimal
    orders_exact: Decimal
    orders_required: int
    unit_rounding: Decimal | None
    surplus_at_required: Decimal

    @property
    def is_fragile(self) -> bool:
        """Vrai si le seuil entier ne couvre les charges qu'à moins de 1 CHF près."""
        return self.surplus_at_required < CHF


def break_even(
    *,
    fixed_costs: Decimal = BP_FIXED_COSTS,
    remuneration: Decimal = Decimal(0),
    basket_ttc: Decimal = BP_BASKET_TTC,
    vat_rate: Decimal = VAT_RATE_CH_STANDARD,
    contribution_rate: Decimal = BP_CONTRIBUTION_RATE,
    cac: Decimal = Decimal("6"),
    unit_rounding: Decimal | None = None,
) -> BreakEven:
    """Nombre de commandes/mois couvrant fixes (+ rémunération).

    ``unit_rounding=CENT`` reproduit la méthode du BP (contribution par commande
    arrondie au centime avant division : 400 / 13,33 ⇒ 31). Sans arrondi, la
    valeur exacte 13,33395 donne 29,9986 ⇒ 30 commandes.
    """
    fixed = to_decimal(fixed_costs, "fixed_costs")
    rem = to_decimal(remuneration, "remuneration")
    rate = to_decimal(contribution_rate, "contribution_rate")
    cac_d = to_decimal(cac, "cac")
    _check_non_negative(fixed, "fixed_costs")
    _check_non_negative(rem, "remuneration")
    _check_non_negative(cac_d, "cac")
    _check_rate(rate, "contribution_rate")
    per_order = basket_ht(basket_ttc, vat_rate) * rate
    after_cac = per_order - cac_d
    if unit_rounding is not None:
        after_cac = round_chf(after_cac, to_decimal(unit_rounding, "unit_rounding"))
    if after_cac <= 0:
        raise ForecastError(
            f"contribution après CAC ≤ 0 ({after_cac} CHF/commande) : aucun volume ne couvre les charges"
        )
    amount = fixed + rem
    exact = amount / after_cac
    required = ceil_int(exact)
    return BreakEven(
        amount_to_cover=amount,
        contribution_per_order=per_order,
        contribution_per_order_after_cac=after_cac,
        orders_exact=exact,
        orders_required=required,
        unit_rounding=unit_rounding,
        surplus_at_required=Decimal(required) * after_cac - amount,
    )


@dataclass(frozen=True)
class SensitivityCell:
    """Une case de la grille de sensibilité (taux de contribution × CAC)."""

    contribution_rate: Decimal
    cac: Decimal
    contribution_per_order: Decimal
    contribution_per_order_after_cac: Decimal
    orders_required: int | None
    below_hard_floor: bool

    @property
    def reachable(self) -> bool:
        """Faux si la contribution après CAC est ≤ 0 (jamais rentable)."""
        return self.orders_required is not None


def sensitivity_grid(
    contribution_rates: Sequence[Decimal],
    cacs: Sequence[Decimal],
    *,
    fixed_costs: Decimal = BP_FIXED_COSTS,
    remuneration: Decimal = Decimal(0),
    basket_ttc: Decimal = BP_BASKET_TTC,
    vat_rate: Decimal = VAT_RATE_CH_STANDARD,
    unit_rounding: Decimal | None = None,
    hard_floor_chf: Decimal = BP_HARD_FLOOR_CHF_PER_ORDER,
    hard_floor_pct: Decimal = BP_HARD_FLOOR_PCT,
) -> tuple[SensitivityCell, ...]:
    """Grille seuil de rentabilité ; signale les cases sous le plancher dur BP §5."""
    if not contribution_rates or not cacs:
        raise ForecastError("contribution_rates et cacs ne peuvent pas être vides")
    amount = to_decimal(fixed_costs, "fixed_costs") + to_decimal(remuneration, "remuneration")
    _check_non_negative(amount, "fixed_costs + remuneration")
    floor_chf = to_decimal(hard_floor_chf, "hard_floor_chf")
    floor_pct = to_decimal(hard_floor_pct, "hard_floor_pct")
    b_ht = basket_ht(basket_ttc, vat_rate)
    cells: list[SensitivityCell] = []
    for raw_rate in contribution_rates:
        rate = to_decimal(raw_rate, "contribution_rate")
        _check_rate(rate, "contribution_rate")
        for raw_cac in cacs:
            cac = to_decimal(raw_cac, "cac")
            _check_non_negative(cac, "cac")
            per_order = b_ht * rate
            after = per_order - cac
            if unit_rounding is not None:
                after = round_chf(after, unit_rounding)
            orders = ceil_int(amount / after) if after > 0 else None
            below = after < floor_chf or after / b_ht < floor_pct
            cells.append(SensitivityCell(rate, cac, per_order, after, orders, below))
    return tuple(cells)


# ---------------------------------------------------------------------------
# Stock, fonds de roulement, TVA, temps (BP §3, §10, §12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StockNeed:
    """Achats consommés mensuels vs stock initial (BP §10 « Stock nécessaire »)."""

    orders_per_month: int
    revenue_ht: Decimal
    product_cost_ratio: Decimal
    monthly_cogs_ht: Decimal
    initial_stock: Decimal
    coverage_ratio: Decimal
    coverage_days: Decimal
    shortfall_one_month: Decimal


def stock_need(
    orders_per_month: int = 100,
    *,
    basket_ttc: Decimal = BP_BASKET_TTC,
    vat_rate: Decimal = VAT_RATE_CH_STANDARD,
    product_cost_ratio: Decimal = BP_PRODUCT_COST_RATIO,
    initial_stock: Decimal = BP_INITIAL_STOCK,
    days_per_month: int = DAYS_PER_MONTH,
) -> StockNeed:
    """100 commandes × 95 TTC, 70 % de coût ⇒ 6 152 CHF HT d'achats consommés / mois."""
    _check_int(orders_per_month, "orders_per_month")
    if orders_per_month <= 0:
        raise ForecastError("orders_per_month doit être > 0")
    ratio = to_decimal(product_cost_ratio, "product_cost_ratio")
    _check_rate(ratio, "product_cost_ratio")
    stock = to_decimal(initial_stock, "initial_stock")
    _check_non_negative(stock, "initial_stock")
    if days_per_month <= 0:
        raise ForecastError("days_per_month doit être > 0")
    revenue_ht = Decimal(orders_per_month) * basket_ht(basket_ttc, vat_rate)
    cogs = revenue_ht * ratio
    if cogs <= 0:
        raise ForecastError("achats consommés nuls : product_cost_ratio doit être > 0")
    coverage = stock / cogs
    return StockNeed(
        orders_per_month=orders_per_month,
        revenue_ht=revenue_ht,
        product_cost_ratio=ratio,
        monthly_cogs_ht=cogs,
        initial_stock=stock,
        coverage_ratio=coverage,
        coverage_days=coverage * days_per_month,
        shortfall_one_month=max(Decimal(0), cogs - stock),
    )


@dataclass(frozen=True)
class WorkingCapitalAssumptions:
    """Délais du cycle cash (jours calendaires). Valeurs par défaut = HYPOTHÈSES FICTIVES.

    * ``supplier_prepayment_days`` : paiement fournisseur → réception (prépaiement) ;
    * ``stock_cover_days`` : jours de ventes détenus en stock en moyenne ;
    * ``supplier_credit_days`` : délai de paiement accordé après réception (0 si prépayé) ;
    * ``psp_payout_delay_days`` : encaissement client → versement PSP sur le compte.
    """

    supplier_prepayment_days: int = 14
    stock_cover_days: int = 30
    supplier_credit_days: int = 0
    psp_payout_delay_days: int = 7

    def __post_init__(self) -> None:
        for attr in ("supplier_prepayment_days", "stock_cover_days", "supplier_credit_days", "psp_payout_delay_days"):
            value = getattr(self, attr)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ForecastError(f"{attr} doit être un entier ≥ 0")


@dataclass(frozen=True)
class WorkingCapitalNeed:
    """Besoin en fonds de roulement (BFR) d'exploitation, CHF."""

    daily_cogs_ht: Decimal
    daily_revenue_ttc: Decimal
    stock_component: Decimal
    psp_component: Decimal
    supplier_credit_component: Decimal
    total: Decimal


def working_capital_need(
    orders_per_month: int = 100,
    assumptions: WorkingCapitalAssumptions | None = None,
    *,
    basket_ttc: Decimal = BP_BASKET_TTC,
    vat_rate: Decimal = VAT_RATE_CH_STANDARD,
    product_cost_ratio: Decimal = BP_PRODUCT_COST_RATIO,
    days_per_month: int = DAYS_PER_MONTH,
) -> WorkingCapitalNeed:
    """BFR = achats/jour × (prépaiement + jours de stock − crédit fournisseur) + CA TTC/jour × délai PSP.

    La TVA collectée conservée jusqu'au décompte n'est volontairement pas comptée
    comme ressource (prudence) ; la TVA d'achat préfinancée non plus (à affiner
    avec la fiduciaire).
    """
    wc = assumptions or WorkingCapitalAssumptions()
    need = stock_need(
        orders_per_month,
        basket_ttc=basket_ttc,
        vat_rate=vat_rate,
        product_cost_ratio=product_cost_ratio,
        initial_stock=Decimal(0),
        days_per_month=days_per_month,
    )
    days = Decimal(days_per_month)
    daily_cogs = need.monthly_cogs_ht / days
    daily_revenue_ttc = Decimal(orders_per_month) * to_decimal(basket_ttc, "basket_ttc") / days
    stock_part = daily_cogs * (wc.supplier_prepayment_days + wc.stock_cover_days)
    psp_part = daily_revenue_ttc * wc.psp_payout_delay_days
    credit_part = daily_cogs * wc.supplier_credit_days
    return WorkingCapitalNeed(
        daily_cogs_ht=daily_cogs,
        daily_revenue_ttc=daily_revenue_ttc,
        stock_component=stock_part,
        psp_component=psp_part,
        supplier_credit_component=credit_part,
        total=stock_part + psp_part - credit_part,
    )


@dataclass(frozen=True)
class VatThresholdCheck:
    """Position d'un chiffre d'affaires annuel face au seuil TVA (BP §4, §10)."""

    annual_turnover: Decimal
    threshold: Decimal
    ratio: Decimal
    exceeds: bool


def vat_threshold_check(
    annual_turnover: Decimal, threshold: Decimal = VAT_REGISTRATION_THRESHOLD
) -> VatThresholdCheck:
    """Compare un CA annuel au seuil (l'analyse finale reste celle de la fiduciaire)."""
    turnover = to_decimal(annual_turnover, "annual_turnover")
    limit = to_decimal(threshold, "threshold")
    _check_non_negative(turnover, "annual_turnover")
    if limit <= 0:
        raise ForecastError("threshold doit être > 0")
    return VatThresholdCheck(turnover, limit, turnover / limit, turnover >= limit)


@dataclass(frozen=True)
class TimeValuation:
    """Valorisation du temps (BP §3 : « une activité cash positive peut rémunérer très peu »)."""

    hours_per_month: Decimal
    implicit_hourly_rate: Decimal | None


def time_valuation(
    monthly_result: Decimal,
    *,
    supervision_hours_per_week: Decimal,
    orders_per_month: int = 0,
    prep_minutes_per_order: Decimal = Decimal(0),
) -> TimeValuation:
    """Heures mensuelles (supervision × 52/12 + préparation) et taux horaire implicite."""
    hours_week = to_decimal(supervision_hours_per_week, "supervision_hours_per_week")
    prep = to_decimal(prep_minutes_per_order, "prep_minutes_per_order")
    _check_non_negative(hours_week, "supervision_hours_per_week")
    _check_non_negative(prep, "prep_minutes_per_order")
    _check_int(orders_per_month, "orders_per_month")
    if orders_per_month < 0:
        raise ForecastError("orders_per_month ne peut pas être négatif")
    hours = hours_week * WEEKS_PER_MONTH + Decimal(orders_per_month) * prep / Decimal(60)
    rate = to_decimal(monthly_result, "monthly_result") / hours if hours > 0 else None
    return TimeValuation(hours, rate)


# ---------------------------------------------------------------------------
# Étoile polaire : contribution nette cumulée hebdomadaire + stop-loss global
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NorthStarWeek:
    """Composantes d'une semaine de la métrique étoile polaire (CHF HT).

    ``net_sales_ht`` (après remises et remboursements) et ``historical_cost``
    (coût historique des unités vendues, retours remis en stock déduits) peuvent
    être négatifs une semaine de retours ; les autres composantes sont ≥ 0.
    ``orders`` est un Decimal pour accepter les volumes fractionnaires d'une projection.
    """

    week: int
    orders: Decimal
    net_sales_ht: Decimal
    historical_cost: Decimal
    payment_fees: Decimal
    logistics: Decimal
    after_sales: Decimal
    acquisition: Decimal
    fixed_costs: Decimal

    def __post_init__(self) -> None:
        _check_int(self.week, "week")
        if self.week < 1:
            raise ForecastError("week doit être ≥ 1")
        for attr in ("orders", "net_sales_ht", "historical_cost", "payment_fees", "logistics", "after_sales",
                     "acquisition", "fixed_costs"):
            object.__setattr__(self, attr, to_decimal(getattr(self, attr), attr))
        for attr in ("orders", "payment_fees", "logistics", "after_sales", "acquisition", "fixed_costs"):
            _check_non_negative(getattr(self, attr), attr)

    @property
    def contribution_before_acquisition(self) -> Decimal:
        """Ventes nettes HT − coût historique − paiement − logistique − SAV."""
        return self.net_sales_ht - self.historical_cost - self.payment_fees - self.logistics - self.after_sales

    @property
    def contribution_after_acquisition(self) -> Decimal:
        """Contribution après publicité, avant charges fixes (jalon BP §1)."""
        return self.contribution_before_acquisition - self.acquisition

    @property
    def net_contribution(self) -> Decimal:
        """Contribution nette de la semaine = métrique étoile polaire hebdomadaire."""
        return self.contribution_after_acquisition - self.fixed_costs


@dataclass(frozen=True)
class NorthStarRow:
    """Une semaine du suivi : contribution nette, cumul et état du stop-loss global."""

    week: NorthStarWeek
    net_contribution: Decimal
    cumulative: Decimal
    global_stoploss: bool


@dataclass(frozen=True)
class ValidationCheck:
    """Jalons BP §1 sur la fenêtre de validation (semaines pleines après l'ouverture)."""

    first_week: int
    last_week: int
    complete: bool
    orders: Decimal
    target_orders: int
    contribution_after_acquisition: Decimal

    @property
    def orders_ok(self) -> bool:
        """Vrai si le nombre de commandes payées atteint la cible (30 au BP)."""
        return self.orders >= self.target_orders

    @property
    def contribution_ok(self) -> bool:
        """Vrai si la contribution après publicité est strictement positive."""
        return self.contribution_after_acquisition > 0

    @property
    def passed(self) -> bool:
        """Les deux jalons chiffrés sont atteints (survente et écoulement : hors de ce calcul)."""
        return self.orders_ok and self.contribution_ok


@dataclass(frozen=True)
class NorthStarReport:
    """Suivi hebdomadaire de la contribution nette cumulée depuis le lancement."""

    rows: tuple[NorthStarRow, ...]
    capital_engaged: Decimal
    global_stoploss_pct: Decimal

    @property
    def max_cumulative_loss(self) -> Decimal:
        """Perte cumulée qui déclenche le stop-loss global (20 % × capital = 1 600 CHF au BP)."""
        return self.capital_engaged * self.global_stoploss_pct

    @property
    def cumulative(self) -> Decimal:
        """Contribution nette cumulée à la dernière semaine (la métrique étoile polaire)."""
        return self.rows[-1].cumulative

    @property
    def lowest(self) -> NorthStarRow:
        """Semaine au cumul le plus bas (la première en cas d'égalité)."""
        return min(self.rows, key=lambda r: (r.cumulative, r.week.week))

    @property
    def first_global_stoploss_week(self) -> int | None:
        """Première semaine où la perte cumulée atteint le seuil, ``None`` sinon."""
        return next((r.week.week for r in self.rows if r.global_stoploss), None)

    @property
    def frozen(self) -> bool:
        """Vrai si le stop-loss global a été déclenché (réarmement : propriétaire uniquement)."""
        return self.first_global_stoploss_week is not None

    @property
    def recovery_week(self) -> int | None:
        """Première semaine après le creux où le cumul redevient > 0 (``None`` si jamais)."""
        trough = self.lowest.week.week
        return next((r.week.week for r in self.rows if r.week.week > trough and r.cumulative > 0), None)

    def validation(
        self,
        opening_week: int = BP_SALES_OPENING_WEEK,
        *,
        days: int = BP_VALIDATION_DAYS,
        target_orders: int = BP_VALIDATION_ORDERS,
    ) -> ValidationCheck:
        """Jalons BP §1 sur ``days // 7`` semaines pleines dès l'ouverture (60 j ⇒ 8 sem., prudent)."""
        _check_int(opening_week, "opening_week")
        _check_int(days, "days")
        _check_int(target_orders, "target_orders")
        if opening_week < 1 or days < 7 or target_orders < 0:
            raise ForecastError("opening_week ≥ 1, days ≥ 7 et target_orders ≥ 0 requis")
        first, last = opening_week, opening_week + days // 7 - 1
        window = [r.week for r in self.rows if first <= r.week.week <= last]
        return ValidationCheck(
            first_week=first,
            last_week=last,
            complete=self.rows[-1].week.week >= last,
            orders=sum((w.orders for w in window), Decimal(0)),
            target_orders=target_orders,
            contribution_after_acquisition=sum((w.contribution_after_acquisition for w in window), Decimal(0)),
        )


def global_stoploss_threshold(
    reference: Decimal = BP_STOPLOSS_REFERENCE, pct: Decimal = GLOBAL_STOPLOSS_PCT
) -> Decimal:
    """Perte de valeur nette qui déclenche le gel global : ``pct`` × capital engagé de référence (840 CHF au BP)."""
    reference = to_decimal(reference, "reference")
    pct = to_decimal(pct, "pct")
    if reference <= 0:
        raise ForecastError("référence du stop-loss > 0 requise")
    _check_rate(pct, "pct")
    return reference * pct


def north_star(
    weeks: Sequence[NorthStarWeek],
    *,
    capital_engaged: Decimal = BP_STOPLOSS_REFERENCE,
    global_stoploss_pct: Decimal = GLOBAL_STOPLOSS_PCT,
) -> NorthStarReport:
    """Cumule la contribution nette semaine par semaine depuis la semaine 1 du lancement.

    Le stop-loss global est *collant* : une fois la perte cumulée ≥ seuil, il reste
    actif même si le cumul remonte (seule la propriétaire peut le réarmer).
    ``capital_engaged`` = capital engagé **de référence** (voir l'en-tête du module) : par défaut
    :data:`BP_STOPLOSS_REFERENCE`, la définition du moteur (point zéro 4 200 CHF, seuil 840 CHF).
    """
    if not weeks:
        raise ForecastError("au moins une semaine est requise")
    capital = to_decimal(capital_engaged, "capital_engaged")
    pct = to_decimal(global_stoploss_pct, "global_stoploss_pct")
    if capital <= 0:
        raise ForecastError("capital_engaged doit être > 0")
    _check_rate(pct, "global_stoploss_pct")
    threshold = -(capital * pct)
    rows: list[NorthStarRow] = []
    cumulative = Decimal(0)
    tripped = False
    for expected, week in enumerate(weeks, start=1):
        if not isinstance(week, NorthStarWeek):
            raise ForecastError("chaque semaine doit être un NorthStarWeek")
        if week.week != expected:
            raise ForecastError(f"semaines non consécutives depuis 1 : attendu {expected}, reçu {week.week}")
        cumulative += week.net_contribution
        tripped = tripped or cumulative <= threshold
        rows.append(NorthStarRow(week, week.net_contribution, cumulative, tripped))
    return NorthStarReport(tuple(rows), capital, pct)


def project_north_star(
    assumptions: ScenarioAssumptions,
    *,
    weeks: int = WEEKS_PER_YEAR,
    opening_week: int = 1,
    product_cost_ratio: Decimal = BP_PRODUCT_COST_RATIO,
    payment_pct: Decimal = BP_PAYMENT_PCT,
    payment_fixed: Decimal = BP_PAYMENT_FIXED,
    after_sales_per_order: Decimal = BP_AFTER_SALES_PER_ORDER,
) -> tuple[NorthStarWeek, ...]:
    """Projette un scénario mensuel en semaines (volumes × 12/52, charges fixes dès la semaine 1).

    Ventilation des 78 % de coûts variables du BP §10 : coût historique = 70 % du CA HT,
    paiement = r × panier TTC + b par commande, SAV = R par commande ; la logistique nette
    (emballage, le port étant refacturé) est le solde implicite. Un solde négatif signale
    des hypothèses incompatibles et lève ``ForecastError``. Le cumul mensuel égale le
    « résultat avant rémunération » du scénario.
    """
    _check_int(weeks, "weeks")
    _check_int(opening_week, "opening_week")
    if weeks < 1 or opening_week < 1:
        raise ForecastError("weeks et opening_week doivent être ≥ 1")
    a = assumptions
    ratio = to_decimal(product_cost_ratio, "product_cost_ratio")
    _check_rate(ratio, "product_cost_ratio")
    r = to_decimal(payment_pct, "payment_pct")
    b = to_decimal(payment_fixed, "payment_fixed")
    sav = to_decimal(after_sales_per_order, "after_sales_per_order")
    for value, label in ((r, "payment_pct"), (b, "payment_fixed"), (sav, "after_sales_per_order")):
        _check_non_negative(value, label)
    per_week = Decimal(12) / Decimal(WEEKS_PER_YEAR)
    b_ht = net_of_vat(a.basket_ttc, a.vat_rate)
    implied_logistics_per_order = b_ht * (Decimal(1) - a.contribution_rate - ratio) - (r * a.basket_ttc + b) - sav
    if implied_logistics_per_order < 0:
        raise ForecastError(
            f"hypothèses incompatibles : logistique implicite {round_chf(implied_logistics_per_order)} CHF/commande "
            "< 0 (contribution + coût produit + paiement + SAV dépassent le CA HT)"
        )
    fixed = a.fixed_costs * per_week
    result: list[NorthStarWeek] = []
    for n in range(1, weeks + 1):
        orders = Decimal(a.orders_per_month) * per_week if n >= opening_week else Decimal(0)
        net = orders * b_ht
        result.append(
            NorthStarWeek(
                week=n,
                orders=orders,
                net_sales_ht=net,
                historical_cost=net * ratio,
                payment_fees=orders * (r * a.basket_ttc + b),
                logistics=orders * implied_logistics_per_order,
                after_sales=orders * sav,
                acquisition=orders * a.cac,
                fixed_costs=fixed,
            )
        )
    return tuple(result)


# ---------------------------------------------------------------------------
# Contre-vérification indépendante de la formule de prix (BP §4)
# ---------------------------------------------------------------------------


def floor_price_crosscheck(
    cost: Decimal,
    *,
    payment_pct: Decimal,
    payment_fixed: Decimal,
    logistics: Decimal,
    after_sales: Decimal,
    acquisition: Decimal,
    target_margin: Decimal,
    vat_rate: Decimal,
) -> Decimal:
    """``P = (C + b + L + R + A) / ((1 − m)/(1 + t) − r)`` — double contrôle QA.

    Réimplémentation indépendante servant à vérifier le BP et le moteur prix ;
    le prix de production reste calculé par ``pokeshop.pricing``.
    """
    c = to_decimal(cost, "cost")
    r = to_decimal(payment_pct, "payment_pct")
    m = to_decimal(target_margin, "target_margin")
    t = to_decimal(vat_rate, "vat_rate")
    numerator = (
        c
        + to_decimal(payment_fixed, "payment_fixed")
        + to_decimal(logistics, "logistics")
        + to_decimal(after_sales, "after_sales")
        + to_decimal(acquisition, "acquisition")
    )
    denominator = (Decimal(1) - m) / (Decimal(1) + t) - r
    if denominator <= 0:
        raise ForecastError(f"dénominateur ≤ 0 ({denominator}) : marge/frais incompatibles")
    return numerator / denominator


def round_up_to_ending(
    price: Decimal, *, step: Decimal = Decimal("10"), ending: Decimal = Decimal("9.90")
) -> Decimal:
    """Plus petit prix de la forme ``k × step + ending`` ≥ ``price``.

    ``step=10, ending=9.90`` reproduit le BP (208,79 → 209,90) ;
    ``step=1, ending=0.90`` donne la lecture « X,90 » (208,79 → 208,90).
    """
    p = to_decimal(price, "price")
    s = to_decimal(step, "step")
    e = to_decimal(ending, "ending")
    if s <= 0:
        raise ForecastError("step doit être > 0")
    if e < 0 or e >= s:
        raise ForecastError("ending doit être dans [0, step[")
    k = ((p - e) / s).to_integral_value(rounding=ROUND_CEILING)
    return k * s + e


@dataclass(frozen=True)
class PriceCheck:
    """Décomposition de la contribution d'une vente unitaire à un prix TTC donné."""

    price_ttc: Decimal
    net_sales: Decimal
    payment_fees: Decimal
    contribution: Decimal
    contribution_pct: Decimal


def contribution_at_price(
    price_ttc: Decimal,
    cost: Decimal,
    *,
    payment_pct: Decimal,
    payment_fixed: Decimal,
    logistics: Decimal,
    after_sales: Decimal,
    acquisition: Decimal,
    vat_rate: Decimal,
) -> PriceCheck:
    """Contribution = P/(1+t) − C − (r·P + b) − L − R − A ; % du CA net."""
    p = to_decimal(price_ttc, "price_ttc")
    if p <= 0:
        raise ForecastError("price_ttc doit être > 0")
    net = net_of_vat(p, to_decimal(vat_rate, "vat_rate"))
    fees = p * to_decimal(payment_pct, "payment_pct") + to_decimal(payment_fixed, "payment_fixed")
    contribution = (
        net
        - to_decimal(cost, "cost")
        - fees
        - to_decimal(logistics, "logistics")
        - to_decimal(after_sales, "after_sales")
        - to_decimal(acquisition, "acquisition")
    )
    return PriceCheck(p, net, fees, contribution, contribution / net)


# ---------------------------------------------------------------------------
# Vérification chiffre par chiffre du BP
# ---------------------------------------------------------------------------


class CheckStatus(str, Enum):
    """Statut d'un chiffre du BP après recalcul."""

    OK = "OK"
    ROUNDING_GAP = "ECART_ARRONDI"
    GAP = "ECART"


@dataclass(frozen=True)
class BpCheck:
    """Un chiffre publié dans le BP confronté au recalcul exact."""

    ref: str
    section: str
    label: str
    bp_value: Decimal
    exact: Decimal
    recomputed: Decimal
    status: CheckStatus
    comment: str = ""

    @property
    def delta(self) -> Decimal:
        """Recalcul arrondi − valeur BP."""
        return self.recomputed - self.bp_value


#: Exemple fictif BP §4 (assujetti, méthode effective).
BP_PRICE_EXAMPLE: dict[str, Decimal] = {
    "cost": Decimal("140"),
    "payment_pct": Decimal("0.025"),
    "payment_fixed": Decimal("0.30"),
    "logistics": Decimal("3"),
    "after_sales": Decimal("1"),
    "acquisition": Decimal("5"),
    "target_margin": Decimal("0.20"),
    "vat_rate": VAT_RATE_CH_STANDARD,
}

#: Lignes du budget initial BP §3 (CHF).
BP_INITIAL_BUDGET: tuple[tuple[str, Decimal], ...] = (
    ("Stock acheté rendu Suisse", Decimal("3000")),
    ("Site et automatisation pilote", Decimal("1500")),
    ("DA et contenus de lancement", Decimal("400")),
    ("Administration et revue des documents", Decimal("700")),
    ("Emballages et matériel", Decimal("300")),
    ("Test acquisition", Decimal("500")),
    ("Réserve de trésorerie", Decimal("1600")),
)

#: Charges mensuelles de simulation BP §3 (CHF/mois).
BP_MONTHLY_FIXED: tuple[tuple[str, Decimal], ...] = (
    ("Site, apps, hébergement et automatisation", Decimal("180")),
    ("Comptabilité et administration", Decimal("120")),
    ("Divers, assurance et petit stockage", Decimal("100")),
)


def _check(
    ref: str,
    section: str,
    label: str,
    bp_value: str,
    exact: Decimal,
    quantum: Decimal,
    *,
    bp_method: Decimal | None = None,
    comment: str = "",
) -> BpCheck:
    """Construit un contrôle ; ``bp_method`` = valeur selon la convention d'arrondi du BP."""
    bp = Decimal(bp_value)
    recomputed = round_chf(exact, quantum) if quantum != Decimal(0) else exact
    if recomputed == bp:
        status = CheckStatus.OK
    elif bp_method is not None and bp_method == bp:
        status = CheckStatus.ROUNDING_GAP
    else:
        status = CheckStatus.GAP
    return BpCheck(ref, section, label, bp, exact, recomputed, status, comment)


def verify_against_bp() -> tuple[BpCheck, ...]:
    """Recalcule chaque chiffre du BP (§3, §4, §10) et qualifie l'écart éventuel."""
    checks: list[BpCheck] = []
    total_budget = sum((amount for _, amount in BP_INITIAL_BUDGET), Decimal(0))
    checks.append(_check("B1", "§3", "Budget initial total", "8000", total_budget, CHF))
    total_fixed = sum((amount for _, amount in BP_MONTHLY_FIXED), Decimal(0))
    checks.append(_check("B2", "§3", "Charges fixes mensuelles", "400", total_fixed, CHF))

    results = run_bp_scenarios()
    pru, cen, dev = results["prudent"], results["central"], results["developpement"]
    checks.append(_check("S0", "§10", "Panier HT (95 TTC)", "87.88", cen.basket_ht, CENT))
    bp_table = {
        "prudent": ("3800", "3515", "773", "320", "53"),
        "central": ("9500", "8788", "1933", "600", "933"),
        "developpement": ("19000", "17577", "3867", "1000", "2467"),
    }
    labels = ("CA produits TTC", "CA produits HT", "Contribution avant acquisition", "Acquisition totale",
              "Résultat avant rémunération")
    for idx, (name, res) in enumerate((("prudent", pru), ("central", cen), ("developpement", dev)), start=1):
        values = (res.revenue_ttc, res.revenue_ht, res.contribution_before_acquisition,
                  res.acquisition_total, res.result_before_remuneration)
        for jdx, (label, bp_value, exact) in enumerate(zip(labels, bp_table[name], values), start=1):
            comment = ""
            if name == "developpement" and jdx == 2:
                comment = (
                    "19 000 / 1,081 = 17 576,32 ⇒ 17 576. Aucun arrondi n'explique 17 577 "
                    "(200 × 87,88 = 17 576). Écart de 1 CHF sans effet : contribution et résultat "
                    "du BP sont cohérents avec la valeur exacte."
                )
            checks.append(_check(f"S{idx}.{jdx}", "§10", f"{label} — {name}", bp_value, exact, CHF,
                                 comment=comment))

    checks.append(_check("U1", "§10", "Contribution/commande avant acquisition (central)", "19.33",
                         cen.contribution_per_order, CENT))
    checks.append(_check("U2", "§10", "Contribution/commande après CAC 6 (central)", "13.33",
                         cen.contribution_per_order_after_cac, CENT))

    be_exact = break_even()
    be_bp = break_even(unit_rounding=CENT)
    checks.append(_check(
        "T1", "§10", "Seuil cash d'exploitation (commandes/mois)", "31",
        Decimal(be_exact.orders_required), CHF, bp_method=Decimal(be_bp.orders_required),
        comment=(f"Exact : 400 / {round_chf(be_exact.contribution_per_order_after_cac, Decimal('0.0001'))} = "
                 f"{round_chf(be_exact.orders_exact, CENT)} ⇒ 30 (couvre 400 CHF à "
                 f"{round_chf(be_exact.surplus_at_required, CENT)} CHF près). BP : 400 / 13,33 = 30,01 ⇒ 31. "
                 "Garder 31, plus prudent."),
    ))
    rem_exact = break_even(remuneration=BP_REMUNERATION)
    rem_bp = break_even(remuneration=BP_REMUNERATION, unit_rounding=CENT)
    checks.append(_check(
        "T2", "§10", "Seuil avec 2 000 CHF de rémunération (commandes/mois)", "181",
        Decimal(rem_exact.orders_required), CHF, bp_method=Decimal(rem_bp.orders_required),
        comment=(f"Exact : 2 400 / 13,33395 = {round_chf(rem_exact.orders_exact, CENT)} ⇒ 180. "
                 "BP : 2 400 / 13,33 = 180,05 ⇒ 181. Hors cotisations sociales (à ajouter)."),
    ))
    checks.append(_check("T3", "§10", "CA TTC annualisé (central)", "114000", cen.annual_revenue_ttc, CHF))

    s15 = break_even(contribution_rate=Decimal("0.15"))
    checks.append(_check("V1", "§10", "Contribution/commande à 15 %", "13.18", s15.contribution_per_order, CENT))
    checks.append(_check("V2", "§10", "Après CAC 6 à 15 %", "7.18", s15.contribution_per_order_after_cac, CENT))
    checks.append(_check("V3", "§10", "Seuil à 15 % (commandes)", "56", Decimal(s15.orders_required), CHF))
    c15 = break_even(cac=Decimal("15"))
    checks.append(_check("V4", "§10", "Contribution après CAC 15 (22 %)", "4.33",
                         c15.contribution_per_order_after_cac, CENT))
    checks.append(_check("V5", "§10", "Seuil avec CAC 15 (commandes)", "93", Decimal(c15.orders_required), CHF))

    need = stock_need(100)
    checks.append(_check("K1", "§10", "CA net à 100 commandes", "8788", need.revenue_ht, CHF))
    checks.append(_check("K2", "§10", "Achats consommés HT/mois (70 %)", "6152", need.monthly_cogs_ht, CHF))

    ex = BP_PRICE_EXAMPLE
    floor = floor_price_crosscheck(ex["cost"], payment_pct=ex["payment_pct"], payment_fixed=ex["payment_fixed"],
                                   logistics=ex["logistics"], after_sales=ex["after_sales"],
                                   acquisition=ex["acquisition"], target_margin=ex["target_margin"],
                                   vat_rate=ex["vat_rate"])
    checks.append(_check("P1", "§4", "Prix plancher (assujetti)", "208.79", floor, CENT,
                         comment="Valeur exacte 208,79498 : l'arrondi au centime tient à 0,00002 CHF près."))
    rounded = round_up_to_ending(floor)
    checks.append(_check(
        "P2", "§4", "Prix public arrondi", "209.90", rounded, CENT,
        comment=("Conforme avec la règle « terminaison 9,90, pas de 10 CHF ». La lecture « prochain X,90 » "
                 f"donnerait {round_up_to_ending(floor, step=Decimal('1'), ending=Decimal('0.90'))} : "
                 "règle d'arrondi à préciser (ambiguïté BP/SPEC)."),
    ))
    common = {k: ex[k] for k in ("payment_pct", "payment_fixed", "logistics", "after_sales", "acquisition",
                                 "vat_rate")}
    at_199 = contribution_at_price(Decimal("199.90"), ex["cost"], **common)
    checks.append(_check("P3", "§4", "Vente nette à 199,90", "184.92", at_199.net_sales, CENT))
    checks.append(_check("P4", "§4", "Frais de paiement à 199,90", "5.30", at_199.payment_fees, CENT))
    checks.append(_check("P5", "§4", "Contribution à 199,90", "30.62", at_199.contribution, CENT))
    checks.append(_check("P6", "§4", "Contribution % CA net à 199,90", "0.1656", at_199.contribution_pct,
                         Decimal("0.0001")))
    cost_nr = ex["cost"] * (Decimal(1) + VAT_RATE_CH_STANDARD)
    checks.append(_check("P7", "§4", "C non assujetti (140 + 8,1 %)", "151.34", cost_nr, CENT))
    floor_nr = floor_price_crosscheck(round_chf(cost_nr, CENT), payment_pct=ex["payment_pct"],
                                      payment_fixed=ex["payment_fixed"], logistics=ex["logistics"],
                                      after_sales=ex["after_sales"], acquisition=ex["acquisition"],
                                      target_margin=ex["target_margin"], vat_rate=Decimal(0))
    checks.append(_check("P8", "§4", "Prix plancher non assujetti (t = 0)", "207.28", floor_nr, CENT))
    return tuple(checks)


def summarize_checks(checks: Iterable[BpCheck]) -> dict[CheckStatus, int]:
    """Compte les contrôles par statut."""
    summary = {status: 0 for status in CheckStatus}
    for check in checks:
        summary[check.status] += 1
    return summary
