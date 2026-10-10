"""Prévisionnel de trésorerie glissant sur 13 semaines (BP §3 « Gestion de trésorerie »).

Le BP demande de distinguer ventes, résultat et cash : solde disponible, achats
engagés, TVA, livraisons, remboursements, publicité et versements des paiements,
avec une réserve pour les précommandes. Ce module calcule semaine par semaine :

* les versements PSP (ventes TTC − frais), décalés du délai de versement ;
* les décaissements par nature (achats engagés / prévus, TVA, livraisons, ...) ;
* la réserve précommandes (encaissé non livré), qui n'est pas disponible pour acheter ;
* une alerte dès que le solde passe sous la réserve minimale ;
* le **stop-loss cash** du mandat : la réserve minimale vaut par défaut la réserve de
  trésorerie du budget initial (1 600 CHF, BP §3). Dès qu'en début de semaine le cash
  disponible (solde − précommandes encaissées non livrées) est sous ce seuil, plus aucun
  achat de stock prévu ni aucune dépense publicitaire n'est autorisé. Les achats déjà
  engagés (commande ferme signée) restent dus. ``pokeshop.stoploss`` (agent gouvernance)
  fait foi pour l'application ; ce module en donne la projection sur 13 semaines.

Module autonome (Decimal uniquement, aucune écriture externe). Les valeurs par
défaut des frais PSP reprennent l'exemple du BP §4 ; le délai de versement est
une HYPOTHÈSE à remplacer par le contrat du prestataire de paiement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Mapping, Sequence

__all__ = [
    "CASH_STOPLOSS_RESERVE",
    "HORIZON_WEEKS",
    "INITIAL_BUDGET_TOTAL",
    "STOPLOSS_BLOCKED_FLOWS",
    "Alert",
    "AlertCode",
    "BudgetLine",
    "CashMovement",
    "Flow",
    "PreorderFulfilment",
    "PspTerms",
    "SaleBatch",
    "TreasuryError",
    "TreasuryForecast",
    "TreasuryPlan",
    "WeekRow",
    "WeeklyInput",
    "build_forecast",
    "initial_budget",
    "initial_budget_movements",
    "plan_from_weekly_inputs",
    "vat_payable",
]

HORIZON_WEEKS = 13
_ZERO = Decimal(0)
_CENT = Decimal("0.01")
#: Réserve de trésorerie du budget initial (BP §3) = seuil du stop-loss cash du mandat.
CASH_STOPLOSS_RESERVE = Decimal("1600")


class TreasuryError(ValueError):
    """Plan de trésorerie incohérent (date hors horizon, montant négatif, ...)."""


def _dec(value: Decimal | int | str, name: str) -> Decimal:
    """Convertit en Decimal en refusant float et booléens."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TreasuryError(f"{name} : type {type(value).__name__} refusé (utiliser Decimal ou str)")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(value)
        except Exception as exc:  # decimal.InvalidOperation
            raise TreasuryError(f"{name} : {value!r} n'est pas un nombre") from exc
    else:
        raise TreasuryError(f"{name} : type {type(value).__name__} non supporté")
    if not result.is_finite():
        raise TreasuryError(f"{name} : valeur non finie")
    return result


def _non_negative(value: Decimal | int | str, name: str) -> Decimal:
    result = _dec(value, name)
    if result < 0:
        raise TreasuryError(f"{name} ne peut pas être négatif (reçu {result})")
    return result


def _int_non_negative(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TreasuryError(f"{name} doit être un entier ≥ 0")
    return value


# ---------------------------------------------------------------------------
# Flux et paramètres
# ---------------------------------------------------------------------------


class Flow(str, Enum):
    """Nature d'un flux de trésorerie (ordre = ordre d'affichage)."""

    PSP_PAYOUT = "versements_psp"
    OTHER_INFLOW = "autres_encaissements"
    PURCHASE_COMMITTED = "achats_engages"
    PURCHASE_PLANNED = "achats_prevus"
    VAT = "tva"
    SHIPPING = "livraisons"
    REFUND = "remboursements"
    PREORDER_REFUND = "remboursements_precommandes"
    ADVERTISING = "publicite"
    FIXED_COSTS = "charges_fixes"
    SETUP = "depenses_lancement"
    OTHER_OUTFLOW = "autres_decaissements"

    @property
    def is_inflow(self) -> bool:
        """Vrai pour les encaissements."""
        return self in (Flow.PSP_PAYOUT, Flow.OTHER_INFLOW)

    @property
    def label_fr(self) -> str:
        """Libellé français pour tableaux et tableaux de bord."""
        return _FLOW_LABELS[self]


#: Flux interdits tant que le stop-loss cash est actif (« plus d'achat ni de pub »).
STOPLOSS_BLOCKED_FLOWS: tuple[Flow, ...] = (Flow.PURCHASE_PLANNED, Flow.ADVERTISING)

_FLOW_LABELS: dict[Flow, str] = {
    Flow.PSP_PAYOUT: "Versements PSP (carte, TWINT)",
    Flow.OTHER_INFLOW: "Autres encaissements (apport, prêt)",
    Flow.PURCHASE_COMMITTED: "Achats de stock engagés (commandes fermes)",
    Flow.PURCHASE_PLANNED: "Achats de stock prévus (non engagés)",
    Flow.VAT: "TVA (décompte AFC)",
    Flow.SHIPPING: "Livraisons (transporteur, étiquettes)",
    Flow.REFUND: "Remboursements clients",
    Flow.PREORDER_REFUND: "Remboursements de précommandes",
    Flow.ADVERTISING: "Publicité",
    Flow.FIXED_COSTS: "Charges fixes (site, compta, divers)",
    Flow.SETUP: "Dépenses de lancement (budget initial)",
    Flow.OTHER_OUTFLOW: "Autres décaissements",
}


@dataclass(frozen=True)
class PspTerms:
    """Conditions du prestataire de paiement.

    ``pct_fee`` et ``fixed_fee`` = r et b de l'exemple BP §4 (hypothèses) ;
    ``payout_delay_days`` = HYPOTHÈSE FICTIVE (à remplacer par le contrat PSP).
    """

    pct_fee: Decimal = Decimal("0.025")
    fixed_fee: Decimal = Decimal("0.30")
    payout_delay_days: int = 7

    def __post_init__(self) -> None:
        pct = _non_negative(self.pct_fee, "pct_fee")
        if pct >= 1:
            raise TreasuryError("pct_fee doit être < 1")
        object.__setattr__(self, "pct_fee", pct)
        object.__setattr__(self, "fixed_fee", _non_negative(self.fixed_fee, "fixed_fee"))
        _int_non_negative(self.payout_delay_days, "payout_delay_days")

    def fees(self, gross_ttc: Decimal, orders: int) -> Decimal:
        """Frais PSP = r × montant encaissé + b × nombre de transactions."""
        return gross_ttc * self.pct_fee + self.fixed_fee * orders

    def payout_day(self, sale_day: date) -> date:
        """Date de versement sur le compte bancaire."""
        return sale_day + timedelta(days=self.payout_delay_days)


@dataclass(frozen=True)
class SaleBatch:
    """Ventes encaissées un jour donné (montant TTC payé par les clients)."""

    day: date
    gross_ttc: Decimal
    orders: int
    preorder: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "gross_ttc", _non_negative(self.gross_ttc, "gross_ttc"))
        _int_non_negative(self.orders, "orders")
        if self.gross_ttc > 0 and self.orders == 0:
            raise TreasuryError("une vente non nulle doit compter au moins une commande")


@dataclass(frozen=True)
class CashMovement:
    """Mouvement de trésorerie daté (montant toujours positif, sens donné par ``flow``)."""

    day: date
    flow: Flow
    amount: Decimal
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.flow, Flow):
            raise TreasuryError("flow doit être un membre de Flow")
        object.__setattr__(self, "amount", _non_negative(self.amount, "amount"))


@dataclass(frozen=True)
class PreorderFulfilment:
    """Précommandes livrées : libère la réserve à hauteur du montant TTC encaissé."""

    day: date
    amount_ttc: Decimal
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount_ttc", _non_negative(self.amount_ttc, "amount_ttc"))


@dataclass(frozen=True)
class TreasuryPlan:
    """Entrées du prévisionnel. ``start`` = premier jour de la semaine 1.

    ``minimum_reserve`` = seuil du stop-loss cash (1 600 CHF par défaut, BP §3).
    ``enforce_cash_stoploss`` : si vrai, les achats prévus et la publicité d'une semaine
    ouverte en stop-loss sont retirés de la projection (montants dans ``blocked_outflows``) ;
    sinon ils restent projetés et sont signalés comme à bloquer.
    """

    start: date
    opening_balance: Decimal
    minimum_reserve: Decimal = CASH_STOPLOSS_RESERVE
    psp: PspTerms = field(default_factory=PspTerms)
    sales: tuple[SaleBatch, ...] = ()
    movements: tuple[CashMovement, ...] = ()
    fulfilments: tuple[PreorderFulfilment, ...] = ()
    opening_preorder_reserve: Decimal = _ZERO
    weeks: int = HORIZON_WEEKS
    enforce_cash_stoploss: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enforce_cash_stoploss, bool):
            raise TreasuryError("enforce_cash_stoploss doit être un booléen")
        object.__setattr__(self, "opening_balance", _dec(self.opening_balance, "opening_balance"))
        object.__setattr__(self, "minimum_reserve", _non_negative(self.minimum_reserve, "minimum_reserve"))
        object.__setattr__(
            self, "opening_preorder_reserve", _non_negative(self.opening_preorder_reserve, "opening_preorder_reserve")
        )
        object.__setattr__(self, "sales", tuple(self.sales))
        object.__setattr__(self, "movements", tuple(self.movements))
        object.__setattr__(self, "fulfilments", tuple(self.fulfilments))
        if isinstance(self.weeks, bool) or not isinstance(self.weeks, int) or self.weeks < 1:
            raise TreasuryError("weeks doit être un entier ≥ 1")

    @property
    def end(self) -> date:
        """Dernier jour de l'horizon (inclus)."""
        return self.start + timedelta(days=7 * self.weeks - 1)

    def week_of(self, day: date) -> int | None:
        """Numéro de semaine (1..weeks) d'une date, ``None`` hors horizon."""
        if day < self.start or day > self.end:
            return None
        return (day - self.start).days // 7 + 1


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------


class AlertCode(str, Enum):
    """Alertes de trésorerie, de la plus grave à la moins grave."""

    NEGATIVE_BALANCE = "SOLDE_NEGATIF"
    BELOW_MINIMUM_RESERVE = "SOUS_RESERVE_MINI"
    PREORDER_RESERVE_UNCOVERED = "PRECOMMANDES_NON_COUVERTES"


_STOPLOSS_SUFFIX = " — stop-loss cash : plus d'achat prévu ni de publicité"
_ALERT_MESSAGES: dict[AlertCode, str] = {
    AlertCode.NEGATIVE_BALANCE: "Solde bancaire négatif" + _STOPLOSS_SUFFIX,
    AlertCode.BELOW_MINIMUM_RESERVE: "Solde sous la réserve minimale" + _STOPLOSS_SUFFIX,
    AlertCode.PREORDER_RESERVE_UNCOVERED: (
        "Solde insuffisant pour couvrir réserve minimale + précommandes encaissées" + _STOPLOSS_SUFFIX
    ),
}


@dataclass(frozen=True)
class Alert:
    """Alerte d'une semaine ; ``shortfall`` = montant à trouver ou à décaler (CHF)."""

    week: int
    week_start: date
    code: AlertCode
    shortfall: Decimal
    message: str


@dataclass(frozen=True)
class WeekRow:
    """Une semaine du prévisionnel (montants exacts, positifs par nature de flux)."""

    index: int
    start: date
    end: date
    opening_balance: Decimal
    flows: Mapping[Flow, Decimal]
    gross_sales_ttc: Decimal
    preorder_sales_ttc: Decimal
    orders: int
    psp_fees: Decimal
    total_inflows: Decimal
    total_outflows: Decimal
    closing_balance: Decimal
    preorder_reserve: Decimal
    minimum_reserve: Decimal
    available_for_purchases: Decimal
    status: AlertCode | None
    cash_stoploss_at_open: bool = False
    blocked_outflows: Decimal = _ZERO

    def flow(self, flow: Flow) -> Decimal:
        """Montant de la semaine pour une nature de flux."""
        return self.flows[flow]


@dataclass(frozen=True)
class TreasuryForecast:
    """Résultat du prévisionnel 13 semaines."""

    plan: TreasuryPlan
    weeks: tuple[WeekRow, ...]
    alerts: tuple[Alert, ...]
    psp_in_transit_end: Decimal
    ignored_after_horizon: int

    @property
    def closing_balance(self) -> Decimal:
        """Solde de clôture de la dernière semaine."""
        return self.weeks[-1].closing_balance

    @property
    def lowest_week(self) -> WeekRow:
        """Semaine au solde de clôture le plus bas (la première en cas d'égalité)."""
        return min(self.weeks, key=lambda w: (w.closing_balance, w.index))

    @property
    def has_alerts(self) -> bool:
        """Vrai si au moins une semaine est en alerte."""
        return bool(self.alerts)

    @property
    def cash_stoploss_weeks(self) -> tuple[int, ...]:
        """Semaines ouvertes en stop-loss cash (achats prévus et publicité interdits)."""
        return tuple(w.index for w in self.weeks if w.cash_stoploss_at_open)

    @property
    def first_cash_stoploss_week(self) -> int | None:
        """Première semaine ouverte en stop-loss cash, ``None`` sinon."""
        weeks = self.cash_stoploss_weeks
        return weeks[0] if weeks else None

    @property
    def blocked_outflows_total(self) -> Decimal:
        """Total des achats prévus et de la publicité tombant en semaine de stop-loss."""
        return sum((w.blocked_outflows for w in self.weeks), _ZERO)

    def as_rows(self) -> list[dict[str, str]]:
        """Lignes à plat (montants arrondis au centime, en texte) pour CSV ou tableau de bord."""
        rows: list[dict[str, str]] = []
        for w in self.weeks:
            row = {
                "semaine": str(w.index),
                "du": w.start.isoformat(),
                "au": w.end.isoformat(),
                "solde_ouverture": _fmt(w.opening_balance),
                "ventes_ttc": _fmt(w.gross_sales_ttc),
                "precommandes_ttc": _fmt(w.preorder_sales_ttc),
                "commandes": str(w.orders),
                "frais_psp": _fmt(w.psp_fees),
            }
            for flow in Flow:
                row[flow.value] = _fmt(w.flows[flow])
            row.update(
                {
                    "total_encaissements": _fmt(w.total_inflows),
                    "total_decaissements": _fmt(w.total_outflows),
                    "solde_cloture": _fmt(w.closing_balance),
                    "reserve_precommandes": _fmt(w.preorder_reserve),
                    "reserve_minimale": _fmt(w.minimum_reserve),
                    "disponible_achats": _fmt(w.available_for_purchases),
                    "alerte": w.status.value if w.status else "OK",
                    "stop_loss_cash": "OUI" if w.cash_stoploss_at_open else "non",
                    "sorties_bloquees": _fmt(w.blocked_outflows),
                }
            )
            rows.append(row)
        return rows


def _fmt(amount: Decimal) -> str:
    return str(amount.quantize(_CENT, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Calcul
# ---------------------------------------------------------------------------


def _status(closing: Decimal, minimum_reserve: Decimal, available: Decimal) -> AlertCode | None:
    if closing < 0:
        return AlertCode.NEGATIVE_BALANCE
    if closing < minimum_reserve:
        return AlertCode.BELOW_MINIMUM_RESERVE
    if available < 0:
        return AlertCode.PREORDER_RESERVE_UNCOVERED
    return None


def build_forecast(plan: TreasuryPlan) -> TreasuryForecast:
    """Calcule le prévisionnel semaine par semaine.

    Règles :
    * un mouvement ou une livraison de précommande daté avant ``start`` est refusé
      (il est déjà dans le solde d'ouverture) ; après l'horizon, il est ignoré et compté ;
    * une vente antérieure à ``start`` n'apporte que son versement PSP s'il tombe dans
      l'horizon (une précommande antérieure passe par ``opening_preorder_reserve``) ;
    * les versements de ventes de l'horizon tombant après la fin sont « en transit » ;
    * réserve précommandes = ouverture + précommandes encaissées − livrées − remboursées (≥ 0) ;
    * stop-loss cash : évalué en début de semaine sur la clôture précédente
      (solde − réserve précommandes < réserve minimale). Une dépense prévue qui fait
      passer sous le seuil en cours de semaine apparaît en alerte de clôture et bloque
      la semaine suivante (granularité hebdomadaire).
    """
    n = plan.weeks
    flows: list[dict[Flow, Decimal]] = [{f: _ZERO for f in Flow} for _ in range(n)]
    gross = [_ZERO] * n
    preorder_gross = [_ZERO] * n
    orders = [0] * n
    fees = [_ZERO] * n
    released = [_ZERO] * n
    in_transit = _ZERO
    ignored = 0

    for sale in plan.sales:
        sale_week = plan.week_of(sale.day)
        if sale.day > plan.end:
            ignored += 1
            continue
        if sale_week is None and sale.preorder:
            raise TreasuryError(
                f"précommande du {sale.day} antérieure à l'horizon : utiliser opening_preorder_reserve"
            )
        fee = plan.psp.fees(sale.gross_ttc, sale.orders)
        net = sale.gross_ttc - fee
        if sale_week is not None:
            i = sale_week - 1
            gross[i] += sale.gross_ttc
            orders[i] += sale.orders
            fees[i] += fee
            if sale.preorder:
                preorder_gross[i] += sale.gross_ttc
        payout_week = plan.week_of(plan.psp.payout_day(sale.day))
        if payout_week is not None:
            flows[payout_week - 1][Flow.PSP_PAYOUT] += net
        elif plan.psp.payout_day(sale.day) > plan.end and sale_week is not None:
            in_transit += net

    for mv in plan.movements:
        if mv.day < plan.start:
            raise TreasuryError(f"mouvement « {mv.label or mv.flow.value} » du {mv.day} antérieur à l'horizon")
        week = plan.week_of(mv.day)
        if week is None:
            ignored += 1
            continue
        flows[week - 1][mv.flow] += mv.amount

    for ful in plan.fulfilments:
        if ful.day < plan.start:
            raise TreasuryError(f"livraison de précommande du {ful.day} antérieure à l'horizon")
        week = plan.week_of(ful.day)
        if week is None:
            ignored += 1
            continue
        released[week - 1] += ful.amount_ttc

    rows: list[WeekRow] = []
    alerts: list[Alert] = []
    balance = plan.opening_balance
    reserve = plan.opening_preorder_reserve
    for i in range(n):
        week_flows = flows[i]
        stoploss_at_open = balance - reserve < plan.minimum_reserve
        blocked = _ZERO
        if stoploss_at_open:
            blocked = sum((week_flows[f] for f in STOPLOSS_BLOCKED_FLOWS), _ZERO)
            if plan.enforce_cash_stoploss:
                for f in STOPLOSS_BLOCKED_FLOWS:
                    week_flows[f] = _ZERO
        inflows = sum((v for f, v in week_flows.items() if f.is_inflow), _ZERO)
        outflows = sum((v for f, v in week_flows.items() if not f.is_inflow), _ZERO)
        opening = balance
        balance = opening + inflows - outflows
        reserve = max(_ZERO, reserve + preorder_gross[i] - released[i] - week_flows[Flow.PREORDER_REFUND])
        available = balance - reserve - plan.minimum_reserve
        status = _status(balance, plan.minimum_reserve, available)
        start = plan.start + timedelta(days=7 * i)
        rows.append(
            WeekRow(
                index=i + 1,
                start=start,
                end=start + timedelta(days=6),
                opening_balance=opening,
                flows=dict(week_flows),
                gross_sales_ttc=gross[i],
                preorder_sales_ttc=preorder_gross[i],
                orders=orders[i],
                psp_fees=fees[i],
                total_inflows=inflows,
                total_outflows=outflows,
                closing_balance=balance,
                preorder_reserve=reserve,
                minimum_reserve=plan.minimum_reserve,
                available_for_purchases=available,
                status=status,
                cash_stoploss_at_open=stoploss_at_open,
                blocked_outflows=blocked,
            )
        )
        if status is not None:
            alerts.append(Alert(i + 1, start, status, -available, _ALERT_MESSAGES[status]))
    return TreasuryForecast(plan, tuple(rows), tuple(alerts), in_transit, ignored)


# ---------------------------------------------------------------------------
# Saisie hebdomadaire (même structure que tresorerie_13_semaines.xlsx)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeeklyInput:
    """Une colonne de saisie du classeur 13 semaines (montants CHF ≥ 0)."""

    sales_ttc: Decimal = _ZERO
    orders: int = 0
    preorder_sales_ttc: Decimal = _ZERO
    preorder_orders: int = 0
    psp_in_transit: Decimal = _ZERO
    other_inflows: Decimal = _ZERO
    purchases_committed: Decimal = _ZERO
    purchases_planned: Decimal = _ZERO
    vat: Decimal = _ZERO
    shipping: Decimal = _ZERO
    refunds: Decimal = _ZERO
    preorder_refunds: Decimal = _ZERO
    advertising: Decimal = _ZERO
    fixed_costs: Decimal = _ZERO
    setup_costs: Decimal = _ZERO
    other_outflows: Decimal = _ZERO
    preorders_fulfilled: Decimal = _ZERO

    def __post_init__(self) -> None:
        for name in _WEEKLY_AMOUNT_FLOWS:
            object.__setattr__(self, name, _non_negative(getattr(self, name), name))
        for name in ("sales_ttc", "preorder_sales_ttc", "preorders_fulfilled"):
            object.__setattr__(self, name, _non_negative(getattr(self, name), name))
        _int_non_negative(self.orders, "orders")
        _int_non_negative(self.preorder_orders, "preorder_orders")
        if self.sales_ttc > 0 and self.orders == 0:
            raise TreasuryError("ventes saisies sans nombre de commandes")
        if self.preorder_sales_ttc > 0 and self.preorder_orders == 0:
            raise TreasuryError("précommandes saisies sans nombre de commandes")


#: Champ de saisie → nature de flux (les ventes passent par le PSP).
_WEEKLY_AMOUNT_FLOWS: dict[str, Flow] = {
    "psp_in_transit": Flow.PSP_PAYOUT,
    "other_inflows": Flow.OTHER_INFLOW,
    "purchases_committed": Flow.PURCHASE_COMMITTED,
    "purchases_planned": Flow.PURCHASE_PLANNED,
    "vat": Flow.VAT,
    "shipping": Flow.SHIPPING,
    "refunds": Flow.REFUND,
    "preorder_refunds": Flow.PREORDER_REFUND,
    "advertising": Flow.ADVERTISING,
    "fixed_costs": Flow.FIXED_COSTS,
    "setup_costs": Flow.SETUP,
    "other_outflows": Flow.OTHER_OUTFLOW,
}


def plan_from_weekly_inputs(
    *,
    start: date,
    opening_balance: Decimal,
    weeks: Sequence[WeeklyInput],
    minimum_reserve: Decimal = CASH_STOPLOSS_RESERVE,
    psp_pct_fee: Decimal = Decimal("0.025"),
    psp_fixed_fee: Decimal = Decimal("0.30"),
    payout_delay_weeks: int = 1,
    opening_preorder_reserve: Decimal = _ZERO,
    enforce_cash_stoploss: bool = False,
) -> TreasuryPlan:
    """Construit un plan à partir de saisies hebdomadaires (chaque flux daté du 1er jour de sa semaine)."""
    if not weeks:
        raise TreasuryError("au moins une semaine de saisie est requise")
    _int_non_negative(payout_delay_weeks, "payout_delay_weeks")
    psp = PspTerms(pct_fee=psp_pct_fee, fixed_fee=psp_fixed_fee, payout_delay_days=7 * payout_delay_weeks)
    sales: list[SaleBatch] = []
    movements: list[CashMovement] = []
    fulfilments: list[PreorderFulfilment] = []
    for i, week in enumerate(weeks):
        day = start + timedelta(days=7 * i)
        if week.sales_ttc > 0 or week.orders > 0:
            sales.append(SaleBatch(day, week.sales_ttc, week.orders, label=f"S{i + 1} ventes"))
        if week.preorder_sales_ttc > 0 or week.preorder_orders > 0:
            sales.append(
                SaleBatch(day, week.preorder_sales_ttc, week.preorder_orders, preorder=True,
                          label=f"S{i + 1} précommandes")
            )
        for name, flow in _WEEKLY_AMOUNT_FLOWS.items():
            amount: Decimal = getattr(week, name)
            if amount > 0:
                movements.append(CashMovement(day, flow, amount, label=f"S{i + 1} {name}"))
        if week.preorders_fulfilled > 0:
            fulfilments.append(PreorderFulfilment(day, week.preorders_fulfilled, label=f"S{i + 1}"))
    return TreasuryPlan(
        start=start,
        opening_balance=opening_balance,
        minimum_reserve=minimum_reserve,
        psp=psp,
        sales=tuple(sales),
        movements=tuple(movements),
        fulfilments=tuple(fulfilments),
        opening_preorder_reserve=opening_preorder_reserve,
        weeks=len(weeks),
        enforce_cash_stoploss=enforce_cash_stoploss,
    )


# ---------------------------------------------------------------------------
# Budget initial (BP §3) et TVA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetLine:
    """Ligne du budget initial ; ``flow=None`` = montant conservé (réserve)."""

    key: str
    label: str
    amount: Decimal
    nature: str
    flow: Flow | None


INITIAL_BUDGET_TOTAL = Decimal("8000")


def initial_budget() -> tuple[BudgetLine, ...]:
    """Budget pilote BP §3 (8 000 CHF, aucune offre prestataire confirmée)."""
    return (
        BudgetLine("stock", "Stock acheté rendu Suisse", Decimal("3000"), "Hypothèse de coût cash",
                   Flow.PURCHASE_COMMITTED),
        BudgetLine("site", "Site et automatisation pilote", Decimal("1500"),
                   "Budget plafonné ; réalisation interne/assistée", Flow.SETUP),
        BudgetLine("da", "DA et contenus de lancement", Decimal("400"), "Dépenses cash hors temps interne",
                   Flow.SETUP),
        BudgetLine("admin", "Administration et revue des documents", Decimal("700"),
                   "Provision à confirmer par devis", Flow.SETUP),
        BudgetLine("emballages", "Emballages et matériel", Decimal("300"), "Provision", Flow.SETUP),
        BudgetLine("acquisition", "Test acquisition", Decimal("500"), "Plafond avant validation CAC",
                   Flow.ADVERTISING),
        BudgetLine("reserve", "Réserve de trésorerie", CASH_STOPLOSS_RESERVE,
                   "Réassort, versements différés, remboursement ; seuil du stop-loss cash", None),
    )


def initial_budget_movements(schedule: Mapping[str, date]) -> tuple[CashMovement, ...]:
    """Mouvements de décaissement du budget initial selon un calendrier ``{clé: date}``.

    Seules les lignes présentes dans ``schedule`` sont décaissées ; la réserve
    (sans flux) ne peut pas être planifiée.
    """
    lines = {line.key: line for line in initial_budget()}
    movements: list[CashMovement] = []
    for key, day in schedule.items():
        if key not in lines:
            raise TreasuryError(f"ligne de budget inconnue : {key}")
        line = lines[key]
        if line.flow is None:
            raise TreasuryError(f"« {line.label} » est une réserve, pas un décaissement")
        movements.append(CashMovement(day, line.flow, line.amount, label=line.label))
    return tuple(movements)


def vat_payable(
    sales_ttc: Decimal, vat_rate: Decimal = Decimal("0.081"), deductible_input_vat: Decimal = _ZERO
) -> Decimal:
    """TVA due (méthode effective) = TVA contenue dans les ventes TTC − impôt préalable.

    Négatif = créance sur l'AFC. Estimation de trésorerie uniquement : le décompte
    officiel reste établi avec la fiduciaire.
    """
    sales = _non_negative(sales_ttc, "sales_ttc")
    rate = _non_negative(vat_rate, "vat_rate")
    if rate >= 1:
        raise TreasuryError("vat_rate doit être < 1")
    output_vat = sales * rate / (Decimal(1) + rate)
    return output_vat - _non_negative(deductible_input_vat, "deductible_input_vat")
