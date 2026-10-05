"""Tableau de bord interne : KPI du BP §12 (jour, semaine, mois), étoile polaire et stop-loss en tête.

**INTERNE — contient coûts et marges, ne jamais publier** (BP §7 : « coût et marge sont visibles
exclusivement dans le tableau de bord interne »). Spécification fonctionnelle :
``docs/07-ops/ROUTINES_PILOTAGE.md`` §3.2 (digest), §4 (revue hebdomadaire), §5 (revue mensuelle)
et §6 (dictionnaire des indicateurs).

Principes :

* **Calcul pur et déterministe** à partir des structures du moteur (``ContributionEntry``,
  ``Trigger``/``StopLossStatus``, ``Incident``, ``SpendEntry``, ``ReorderProposal``,
  ``StockLevel``, ``SupplierOffer``, ``CostVariance``, ``ExtensionExposure``…). ``Decimal``
  partout, ``float`` et ``bool`` refusés pour un montant ; arrondi HALF_UP à 0,01 à l'affichage.
* **Étoile polaire d'abord** : contribution nette cumulée (``pokeshop.northstar``, seule source),
  puis l'état du stop-loss (évalué par le moteur ; ce module ne le recalcule jamais, sauf
  :meth:`StopLossView.evaluate` pour la démonstration et les tests).
* **Aucun chiffre inventé** : une source absente (``None``) rend le KPI ``INDISPONIBLE`` avec la
  source à brancher ; une source vide (tuple vide) vaut zéro.
* Ni CA ni followers ne pilotent : le CA n'apparaît que comme contexte (ventes nettes, seuil TVA).
* Données de démonstration : :func:`demo_inputs`, **FICTIVES** (préfixe ``FICTIF``), calculées
  avec les fonctions du moteur ; l'exemple de l'étoile polaire reprend
  ``docs/00-pilotage/ETOILE_POLAIRE.md`` §3 (W45 −53,49 ; W46 −81,17 ; cumul −134,66).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BeforeValidator, Field, field_validator, model_validator

from .forecast import VAT_REGISTRATION_THRESHOLD, vat_threshold_check
from .incidents import Incident, Notification, NotificationReceipt, Severity
from .mandate import SpendEntry, SpendStatus
from .models import (
    AvailabilityStatus,
    CostVariance,
    FrozenModel,
    ReorderProposal,
    StockLevel,
    SupplierOffer,
)
from .northstar import POST_LABELS_FR, ContributionEntry, NorthStarLedger, Post, PostBreakdown, week_start
from .rules import RuleSet
from .stock import is_stale
from .stoploss import (
    ACTION_LABELS_FR,
    LEVEL_LABELS_FR,
    AdSpend,
    AttributedOrder,
    CapitalBaseline,
    ExtensionExposure,
    StopLossAction,
    StopLossConfig,
    StopLossEngine,
    StopLossError,
    StopLossLevel,
    StopLossState,
    StopLossStatus,
    Trigger,
    evaluate_levels,
    format_chf,
)
from .treasury import CASH_STOPLOSS_RESERVE

__all__ = [
    "INTERNAL_BANNER",
    "KpiStatus",
    "DashboardError",
    "DashboardConfig",
    "OpenOrder",
    "SaleLine",
    "ProductStock",
    "AfterSalesCase",
    "TimeEntry",
    "MonthlyTurnover",
    "ToolExpense",
    "CashPosition",
    "StopLossView",
    "DashboardInputs",
    "Kpi",
    "Table",
    "Decision",
    "PostLine",
    "WeekPoint",
    "NorthStarBlock",
    "TriggerLine",
    "LevelCount",
    "StopLossBlock",
    "DashboardReport",
    "DashboardBundle",
    "north_star_block",
    "stoploss_block",
    "pending_decisions",
    "daily_report",
    "weekly_report",
    "monthly_report",
    "build_reports",
    "business_days_between",
    "fmt_pct",
    "fmt_chf",
    "DEMO_AS_OF",
    "demo_inputs",
]

INTERNAL_BANNER = "INTERNE — contient coûts et marges, ne jamais publier"
"""Bandeau obligatoire de toute sortie du tableau de bord (API, HTML, digest)."""

KpiStatus = Literal["OK", "INFO", "ALERTE", "CRITIQUE", "INDISPONIBLE"]
Unit = Literal["CHF", "%", "nombre", "jours", "heures", "CHF/h", "texte"]
ReportKind = Literal["daily", "weekly", "monthly"]

ZERO = Decimal("0")
CENT = Decimal("0.01")
HUNDRED = Decimal("100")
_STATUS_RANK: dict[str, int] = {"OK": 0, "INFO": 1, "INDISPONIBLE": 2, "ALERTE": 3, "CRITIQUE": 4}

_MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_DAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


class DashboardError(ValueError):
    """Entrée ou période invalide pour le tableau de bord."""


# ------------------------------------------------------------------------- types stricts


def _strict_decimal(value: Any) -> Any:
    """Refuse float et bool (non déterministes) ; convertit int/str en Decimal fini."""
    if isinstance(value, (bool, float)):
        raise ValueError(f"{type(value).__name__} interdit : utiliser Decimal, int ou str")
    if isinstance(value, (int, str)):
        try:
            value = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"valeur décimale invalide {value!r}") from exc
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("valeur non finie interdite")
    return value


StrictDecimal = Annotated[Decimal, BeforeValidator(_strict_decimal)]


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire (datetime naïf refusé)")
    return value


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------------------ formats


def fmt_chf(value: Decimal | None) -> str:
    """``1 600,00 CHF`` (format suisse romand du moteur ; ``—`` si inconnu)."""
    return format_chf(value)


def fmt_pct(fraction: Decimal | None) -> str:
    """Fraction -> ``16,56 %`` (``—`` si inconnue)."""
    if fraction is None:
        return "—"
    q = _q2(fraction * HUNDRED)
    sign = "−" if q < 0 else ""
    return f"{sign}{abs(q):.2f} %".replace(".", ",")


def _fmt_dec(value: Decimal, places: str = "0.1") -> str:
    q = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    sign = "−" if q < 0 else ""
    return f"{sign}{abs(q)}".replace(".", ",")


def _fmt_signed_chf(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return ("+" if value > 0 else "") + fmt_chf(value)


def _fmt_date(day: date) -> str:
    return f"{day.day} {_MONTHS_FR[day.month - 1]} {day.year}"


def _fmt_day_long(day: date) -> str:
    return f"{_DAYS_FR[day.weekday()]} {_fmt_date(day)}"


def _fmt_dt(at: datetime, tz: ZoneInfo) -> str:
    local = at.astimezone(tz)
    return f"{local.day:02d}.{local.month:02d}.{local.year} {local.hour:02d}:{local.minute:02d}"


def _display(value: Decimal | int | str | None, unit: Unit) -> str:
    if value is None:
        return "—"
    if unit == "texte" or isinstance(value, str):
        return str(value)
    if unit == "CHF":
        return fmt_chf(Decimal(value))
    if unit == "CHF/h":
        return fmt_chf(Decimal(value)) + "/h"
    if unit == "%":
        return fmt_pct(Decimal(value))
    if unit == "jours":
        return f"{value} j"
    if unit == "heures":
        return _fmt_dec(Decimal(value)) + " h"
    return str(value)


def _worst(statuses: Iterable[str]) -> KpiStatus:
    worst: KpiStatus = "OK"
    for s in statuses:
        if _STATUS_RANK[s] > _STATUS_RANK[worst]:
            worst = s  # type: ignore[assignment]
    return worst


# -------------------------------------------------------------------------- configuration


class DashboardConfig(FrozenModel):
    """Seuils d'affichage ; chacun cite sa source (BP ou hypothèse à valider)."""

    timezone: str = "Europe/Zurich"
    cash_reserve_chf: StrictDecimal = Field(default=CASH_STOPLOSS_RESERVE, ge=0)
    """BP §3 réserve de trésorerie = seuil du stop-loss cash."""
    stock_budget_chf: StrictDecimal = Field(default=Decimal("3000"), ge=0)
    """BP §3 stock acheté rendu Suisse."""
    extension_cap_share: StrictDecimal = Field(default=Decimal("0.25"), gt=0, le=1)
    """BP §1 : pas plus de 25 % du budget stock dans une extension."""
    monthly_fixed_costs_chf: StrictDecimal = Field(default=Decimal("400"), ge=0)
    """BP §3 charges fixes hors publicité et rémunération."""
    tools_monthly_envelope_chf: StrictDecimal = Field(default=Decimal("180"), ge=0)
    """BP §3 « Site, apps, hébergement et automatisation » (enveloppe, pas un tarif)."""
    after_sales_provision_chf: StrictDecimal = Field(default=Decimal("1.00"), ge=0)
    """BP §4 provision SAV R par commande."""
    vat_threshold_chf: StrictDecimal = Field(default=VAT_REGISTRATION_THRESHOLD, gt=0)
    """BP §4 [S6] seuil général d'assujettissement (CA déterminant de toute l'entité)."""
    vat_alert_share: StrictDecimal = Field(default=Decimal("0.70"), gt=0, le=1)
    """Hypothèse ROUTINES_PILOTAGE §5 : alerte dès 70 % du seuil (à valider avec la fiduciaire)."""
    max_offer_age_hours: int = Field(default=24, ge=1, le=168)
    """BP §5 : donnée amont > 24 h = périmée."""
    shipping_delay_business_days: int = Field(default=3, ge=1, le=30)
    """Hypothèse ``DELAI_EXPEDITION`` (« 3 jours ouvrés », champs_a_remplir.yaml, à valider)."""
    cost_variance_alert_share: StrictDecimal = Field(default=Decimal("0.02"), gt=0, lt=1)
    """ROUTINES_PILOTAGE §4.1 : écart de coût > 2 % à expliquer."""
    no_sale_days: tuple[int, int, int] = (14, 30, 45)
    """ROUTINES_PILOTAGE §4.1 : 14, 30 et 45 jours (45 = stop-loss extension)."""
    owner_hours_alert_per_week: StrictDecimal = Field(default=Decimal("10"), gt=0)
    """BP §3 : 6 à 10 h de supervision hebdomadaire ; > 10 h = alerte (R19)."""
    hourly_rate_chf: StrictDecimal | None = Field(default=None, ge=0)
    """``TAUX_HORAIRE_VALORISATION`` : à fixer par la propriétaire (None = non valorisé)."""
    storage_capacity_units: int | None = Field(default=None, ge=1)
    """Places disponibles au lieu de stockage (None = non renseigné)."""
    history_weeks: int = Field(default=12, ge=1, le=104)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {v!r}") from exc
        return v

    @field_validator("no_sale_days")
    @classmethod
    def _buckets(cls, v: tuple[int, int, int]) -> tuple[int, int, int]:
        if not 0 < v[0] < v[1] < v[2]:
            raise ValueError("no_sale_days : trois seuils strictement croissants attendus")
        return v

    @property
    def tz(self) -> ZoneInfo:
        """Fuseau des jours civils (Europe/Zurich)."""
        return ZoneInfo(self.timezone)

    @property
    def max_offer_age(self) -> timedelta:
        """Âge maximal d'une offre fournisseur."""
        return timedelta(hours=self.max_offer_age_hours)

    @classmethod
    def from_engine(
        cls, *, rules: RuleSet | None = None, stoploss: StopLossConfig | None = None, **overrides: Any
    ) -> DashboardConfig:
        """Reprend les seuils versionnés du moteur (une seule valeur par règle dans le dépôt)."""
        data: dict[str, Any] = {}
        if rules is not None:
            data.update(
                stock_budget_chf=rules.stock.stock_budget_chf,
                extension_cap_share=rules.stock.extension_budget_cap,
                after_sales_provision_chf=rules.pricing.after_sales_provision,
                max_offer_age_hours=rules.stock.staleness_hours,
            )
        if stoploss is not None:
            first, second, _ = cls.model_fields["no_sale_days"].default
            data.update(
                timezone=stoploss.timezone,
                cash_reserve_chf=stoploss.cash.reserve_chf,
                no_sale_days=(first, second, stoploss.extension.max_days_without_sale),
            )
            if rules is None:
                data["extension_cap_share"] = stoploss.extension.max_share_of_stock_budget
        data.update(overrides)
        return cls(**data)


# ------------------------------------------------------------------------------- entrées


class OpenOrder(FrozenModel):
    """Commande payée non expédiée (Shopify) : référence seulement, aucune donnée personnelle."""

    order_ref: str = Field(min_length=1)
    paid_at: datetime
    preorder: bool = False
    allocation_received: bool = True
    """Précommande : stock reçu (préparable) ou en attente de l'allocation."""
    lines: int = Field(default=1, ge=1)

    @field_validator("paid_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "paid_at")


class SaleLine(FrozenModel):
    """Ligne vendue au **coût historique** ; ``customer_ref`` = pseudonyme stable, jamais l'email."""

    order_id: str = Field(min_length=1)
    sold_at: datetime
    product_key: str = Field(min_length=1)
    extension: str = Field(min_length=1)
    qty: int = Field(ge=1)
    cost_chf: StrictDecimal = Field(ge=0)
    """Coût historique total de la ligne (CMP à la sortie de stock)."""
    customer_ref: str | None = None
    status: Literal["PAID", "CANCELLED", "REFUNDED"] = "PAID"

    @field_validator("sold_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "sold_at")


class ProductStock(FrozenModel):
    """Stock d'une référence au coût historique (``HistoricalCostLedger.valuation``)."""

    product_key: str = Field(min_length=1)
    extension: str = Field(min_length=1)
    sku: str | None = None
    published: bool = True
    qty_on_hand: int = Field(ge=0)
    value_at_cost: StrictDecimal = Field(ge=0)
    first_stocked_at: datetime | None = None

    @field_validator("first_stocked_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _aware(v, "first_stocked_at")


class AfterSalesCase(FrozenModel):
    """Dossier SAV (journal SAV, ``SOP_SAV_RETOURS.md``)."""

    case_id: str = Field(min_length=1)
    opened_at: datetime
    kind: Literal["LITIGE", "RETOUR", "REMBOURSEMENT", "GESTE", "AUTRE"]
    status: Literal["OUVERT", "CLOS"] = "OUVERT"
    amount_chf: StrictDecimal = Field(default=ZERO, ge=0)

    @field_validator("opened_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "opened_at")


class TimeEntry(FrozenModel):
    """Heures de la propriétaire par activité (saisie hebdomadaire, ROUTINES §2)."""

    day: date
    activity: str = Field(min_length=1)
    hours: StrictDecimal = Field(gt=0, le=24)


class MonthlyTurnover(FrozenModel):
    """CA déterminant d'un mois pour **toute l'entité** (comptabilité, BP §4), hors TVA."""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount_chf: StrictDecimal = Field(ge=0)
    source: str = Field(default="comptabilité", min_length=1)


class ToolExpense(FrozenModel):
    """Abonnement ou outil payé (comptabilité), comparé à l'enveloppe du BP §3."""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    tool: str = Field(min_length=1)
    amount_chf: StrictDecimal = Field(ge=0)
    ref: str = ""


class CashPosition(FrozenModel):
    """Cash disponible = banque + PayPal − précommandes encaissées non livrées (``pokeshop.treasury``)."""

    as_of: datetime
    cash_available_chf: StrictDecimal
    bank_chf: StrictDecimal | None = None
    paypal_chf: StrictDecimal | None = None
    preorders_collected_chf: StrictDecimal = Field(default=ZERO, ge=0)

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")


class StopLossView(FrozenModel):
    """Résultat de l'évaluation du stop-loss **par le moteur** (jamais recalculé ici en production)."""

    available: bool
    error: str | None = None
    global_frozen: bool = False
    latch_since: datetime | None = None
    latch_cause: str | None = None
    status: StopLossStatus | None = None
    triggers: tuple[Trigger, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> StopLossView:
        if self.available and self.status is None:
            raise ValueError("état du stop-loss disponible sans statut")
        return self

    @classmethod
    def from_engine(
        cls,
        engine: StopLossEngine | None,
        status: StopLossStatus | None,
        triggers: Sequence[Trigger],
        error: str | None,
    ) -> StopLossView:
        """Vue construite depuis ``GovernanceGate.stoploss_status()`` et le verrou du moteur."""
        latch = engine.latch if engine is not None else None
        frozen = bool(latch is not None and latch.frozen) or bool(status is not None and status.global_frozen)
        return cls(
            available=status is not None,
            error=None if status is not None else (error or "état du stop-loss indisponible"),
            global_frozen=frozen,
            latch_since=latch.since if latch is not None and latch.frozen else None,
            latch_cause=latch.cause if latch is not None and latch.frozen else None,
            status=status,
            triggers=tuple(triggers),
        )

    @classmethod
    def evaluate(
        cls,
        state: StopLossState,
        now: datetime,
        config: StopLossConfig,
        *,
        baseline: CapitalBaseline | None = None,
        autonomy_level: int = 1,
    ) -> StopLossView:
        """Évaluation pure (:func:`pokeshop.stoploss.evaluate_levels`) : démonstration et tests."""
        try:
            triggers = evaluate_levels(state, now, config, baseline=baseline)
        except StopLossError as exc:
            return cls(available=False, error=str(exc))
        status = StopLossStatus.from_triggers(triggers, as_of=now, autonomy_level=autonomy_level)
        return cls(available=True, global_frozen=status.global_frozen, status=status, triggers=tuple(triggers))


class DashboardInputs(FrozenModel):
    """Photo des sources du tableau de bord. ``None`` = source non branchée (KPI indisponible)."""

    as_of: datetime
    fictif: bool = False
    autonomy_level: int | None = Field(default=None, ge=1, le=4)
    entries: tuple[ContributionEntry, ...] | None = None
    stoploss: StopLossView | None = None
    cash: CashPosition | None = None
    open_orders: tuple[OpenOrder, ...] | None = None
    stock: tuple[ProductStock, ...] | None = None
    stock_levels: tuple[StockLevel, ...] | None = None
    offers: tuple[SupplierOffer, ...] | None = None
    incidents: tuple[Incident, ...] | None = None
    spend_entries: tuple[SpendEntry, ...] | None = None
    reorder_proposals: tuple[ReorderProposal, ...] | None = None
    sales: tuple[SaleLine, ...] | None = None
    extensions: tuple[ExtensionExposure, ...] | None = None
    ad_spends: tuple[AdSpend, ...] | None = None
    attributed_orders: tuple[AttributedOrder, ...] | None = None
    cost_variances: tuple[CostVariance, ...] | None = None
    after_sales: tuple[AfterSalesCase, ...] | None = None
    time_entries: tuple[TimeEntry, ...] | None = None
    turnover: tuple[MonthlyTurnover, ...] | None = None
    tool_expenses: tuple[ToolExpense, ...] | None = None

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")

    @model_validator(mode="after")
    def _unique(self) -> DashboardInputs:
        def dupes(values: Iterable[Any]) -> Any:
            seen: set[Any] = set()
            for v in values:
                if v in seen:
                    return v
                seen.add(v)
            return None

        checks = {
            "écriture d'étoile polaire": dupes(e.entry_id for e in self.entries or ()),
            "commande ouverte": dupes(o.order_ref for o in self.open_orders or ()),
            "référence en stock": dupes(p.product_key for p in self.stock or ()),
            "niveau de stock": dupes(s.sku for s in self.stock_levels or ()),
            "dossier SAV": dupes(c.case_id for c in self.after_sales or ()),
            "mois de CA": dupes(t.month for t in self.turnover or ()),
        }
        for label, found in checks.items():
            if found is not None:
                raise ValueError(f"doublon {label} : {found!r} (import en double ?)")
        return self


# ------------------------------------------------------------------------------- sorties


class Kpi(FrozenModel):
    """Indicateur affichable : valeur brute (Decimal en chaîne dans le JSON) + rendu français."""

    key: str
    label: str
    value: Decimal | int | str | None
    unit: Unit
    display: str
    status: KpiStatus
    detail: str = ""
    source: str = ""
    threshold: str = ""


class Table(FrozenModel):
    """Tableau interne (cellules déjà formatées)."""

    key: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...] = ()
    empty_text: str = "Rien à signaler."
    note: str = ""

    @model_validator(mode="after")
    def _shape(self) -> Table:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError(f"tableau {self.key} : ligne de {len(row)} cellules pour {len(self.columns)} colonnes")
        return self


class Decision(FrozenModel):
    """Décision attendue de la propriétaire (oui/non, échéance)."""

    label: str
    source: str
    ref: str = ""
    due: datetime | None = None


class PostLine(FrozenModel):
    """Poste de la contribution nette sur la période (coûts positifs, affichés en négatif)."""

    post: Post
    label: str
    amount: Decimal
    signed_display: str


class WeekPoint(FrozenModel):
    """Semaine de l'historique (graphique) : contribution nette et cumul."""

    iso_week: str
    week_start: date
    net: Decimal
    cumulative: Decimal
    orders: int
    complete: bool


class NorthStarBlock(FrozenModel):
    """Étoile polaire : contribution nette cumulée, semaine, delta, moyenne 4 semaines, tendance."""

    available: bool
    reason: str = ""
    cumulative: Decimal = ZERO
    current_week: str = ""
    current_week_net: Decimal = ZERO
    last_closed_week: str | None = None
    last_closed_net: Decimal | None = None
    last_closed_delta: Decimal | None = None
    average_4_weeks: Decimal | None = None
    average_weeks_count: int = 0
    trend: Literal["HAUSSE", "BAISSE", "STABLE", "INCONNUE"] = "INCONNUE"
    period_label: str = ""
    period_net: Decimal = ZERO
    period_before_acquisition: Decimal = ZERO
    period_after_acquisition: Decimal = ZERO
    posts: tuple[PostLine, ...] = ()
    weeks: tuple[WeekPoint, ...] = ()
    status: KpiStatus = "INDISPONIBLE"
    headline: str = ""


class TriggerLine(FrozenModel):
    """Déclencheur de stop-loss prêt à afficher (cause, chiffres, seuil, action)."""

    level: StopLossLevel
    level_label: str
    scope: str
    metric: str
    value_display: str
    threshold_display: str
    action: StopLossAction
    action_label: str
    reason: str
    latched: bool = False


class LevelCount(FrozenModel):
    """Nombre de déclencheurs par niveau (les six niveaux, toujours listés)."""

    level: StopLossLevel
    label: str
    count: int


class StopLossBlock(FrozenModel):
    """État des six stop-loss sur la dernière photo évaluée par le moteur."""

    available: bool
    error: str | None = None
    global_frozen: bool = False
    autonomy_level: int | None = None
    status: KpiStatus = "INDISPONIBLE"
    headline: str = ""
    triggers: tuple[TriggerLine, ...] = ()
    levels: tuple[LevelCount, ...] = ()
    blocked_products: tuple[str, ...] = ()
    no_reorder_extensions: tuple[str, ...] = ()
    cut_campaigns: tuple[str, ...] = ()
    rearm_instructions: tuple[str, ...] = ()


class DashboardReport(FrozenModel):
    """Vue jour, semaine ou mois : étoile polaire et stop-loss **en tête**, puis KPI et tableaux."""

    kind: ReportKind
    title: str
    period_label: str
    period_start: date
    period_end: date
    """Exclu (lendemain du dernier jour)."""
    complete: bool
    """Vrai si la période est close à ``as_of``."""
    as_of: datetime
    generated_at: datetime
    fictif: bool
    banner: str = INTERNAL_BANNER
    north_star: NorthStarBlock
    stoploss: StopLossBlock
    kpis: tuple[Kpi, ...]
    tables: tuple[Table, ...] = ()
    decisions: tuple[Decision, ...] = ()
    unavailable: tuple[str, ...] = ()

    @property
    def status(self) -> KpiStatus:
        """Pire statut de la vue (hors INDISPONIBLE si au moins une donnée est connue)."""
        return _worst([self.north_star.status, self.stoploss.status, *(k.status for k in self.kpis)])

    def kpi(self, key: str) -> Kpi:
        """KPI par clé (KeyError si absent)."""
        for k in self.kpis:
            if k.key == key:
                return k
        raise KeyError(key)

    def table(self, key: str) -> Table:
        """Tableau par clé (KeyError si absent)."""
        for t in self.tables:
            if t.key == key:
                return t
        raise KeyError(key)


class DashboardBundle(FrozenModel):
    """Les trois vues générées ensemble (tableau de bord statique)."""

    daily: DashboardReport
    weekly: DashboardReport
    monthly: DashboardReport


# ---------------------------------------------------------------------- périodes et outils


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz)


def _month_bounds(month: str) -> tuple[date, date]:
    try:
        year, mon = (int(p) for p in month.split("-"))
        first = date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise DashboardError(f"mois invalide : {month!r} (AAAA-MM attendu)") from exc
    last = calendar.monthrange(year, mon)[1]
    return first, first + timedelta(days=last)


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _previous_month(day: date) -> str:
    first = day.replace(day=1)
    return _month_key(first - timedelta(days=1))


def _shift_month(month: str, delta: int) -> str:
    year, mon = (int(p) for p in month.split("-"))
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def business_days_between(start: date, end: date) -> int:
    """Jours ouvrés (lundi-vendredi) écoulés **après** ``start`` jusqu'à ``end`` inclus (jours fériés ignorés)."""
    if end <= start:
        return 0
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def _in(at: datetime, start: datetime, end: datetime) -> bool:
    return start <= at < end


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    return None if denominator == 0 else numerator / denominator


# --------------------------------------------------------------------------- étoile polaire


def north_star_block(
    entries: Sequence[ContributionEntry] | None,
    *,
    cutoff: datetime,
    tz: ZoneInfo,
    period_start: date,
    period_end: date,
    period_label: str,
    history_weeks: int = 12,
) -> NorthStarBlock:
    """Étoile polaire arrêtée à ``cutoff`` : cumul, semaine en cours, dernière semaine close, période détaillée.

    Les écritures postérieures à ``cutoff`` sont ignorées (aucune anticipation). Moyenne sur les
    4 dernières semaines **closes** (ROUTINES §1) ; alerte si elle est négative (ROUTINES §6).
    """
    if entries is None:
        return NorthStarBlock(
            available=False,
            reason="Source non branchée : journal de l'étoile polaire (GET /northstar, pokeshop.northstar).",
            headline="Étoile polaire indisponible : journal non transmis.",
        )
    selected = [e for e in entries if e.at <= cutoff]
    if not selected:
        return NorthStarBlock(
            available=False,
            reason="Aucune écriture à cette date : aucune vente ni charge enregistrée.",
            status="INFO",
            period_label=period_label,
            headline="Contribution nette cumulée : 0,00 CHF (aucune écriture).",
        )
    ledger = NorthStarLedger.from_entries(selected, timezone=tz.key)
    cutoff_day = cutoff.astimezone(tz).date()
    first_day = min(e.at.astimezone(tz).date() for e in selected)
    report = ledger.weekly_report(first_day, cutoff_day)
    rows = report.rows
    last_end = _local_midnight(rows[-1].week_start + timedelta(days=7), tz)
    in_progress = rows[-1] if cutoff < last_end - timedelta(microseconds=1) else None
    closed = rows[:-1] if in_progress is not None else rows
    last = closed[-1] if closed else None
    window = closed[-4:]
    average = _q2(sum((r.net_contribution for r in window), ZERO) / Decimal(len(window))) if window else None
    if len(closed) < 2 or last is None:
        trend: Literal["HAUSSE", "BAISSE", "STABLE", "INCONNUE"] = "INCONNUE"
    elif last.delta_vs_previous_week > 0:
        trend = "HAUSSE"
    elif last.delta_vs_previous_week < 0:
        trend = "BAISSE"
    else:
        trend = "STABLE"
    start_dt = _local_midnight(period_start, tz)
    end_dt = min(_local_midnight(period_end, tz), cutoff + timedelta(microseconds=1))
    period = ledger.totals(start_dt, end_dt)
    posts = tuple(
        PostLine(
            post=p,
            label=POST_LABELS_FR[p],
            amount=period.get(p),
            signed_display=fmt_chf(period.get(p) if p is Post.NET_SALES else -period.get(p)),
        )
        for p in Post
    )
    weeks = tuple(
        WeekPoint(
            iso_week=r.iso_week,
            week_start=r.week_start,
            net=r.net_contribution,
            cumulative=r.cumulative,
            orders=r.orders,
            complete=r is not in_progress,
        )
        for r in rows[-history_weeks:]
    )
    status: KpiStatus = "INFO" if average is None else ("ALERTE" if average < 0 else "OK")
    if last is not None:
        headline = (
            f"Contribution nette cumulée : {fmt_chf(report.cumulative)} ; dernière semaine close "
            f"{last.iso_week} : {fmt_chf(last.net_contribution)} (Δ {_fmt_signed_chf(last.delta_vs_previous_week)})."
        )
    else:
        assert in_progress is not None
        headline = (
            f"Contribution nette cumulée : {fmt_chf(report.cumulative)} ; première semaine en cours "
            f"({in_progress.iso_week})."
        )
    return NorthStarBlock(
        available=True,
        cumulative=report.cumulative,
        current_week=in_progress.iso_week if in_progress is not None else "",
        current_week_net=in_progress.net_contribution if in_progress is not None else ZERO,
        last_closed_week=last.iso_week if last else None,
        last_closed_net=last.net_contribution if last else None,
        last_closed_delta=last.delta_vs_previous_week if last else None,
        average_4_weeks=average,
        average_weeks_count=len(window),
        trend=trend,
        period_label=period_label,
        period_net=period.net_contribution,
        period_before_acquisition=period.contribution_before_acquisition,
        period_after_acquisition=period.contribution_after_acquisition,
        posts=posts,
        weeks=weeks,
        status=status,
        headline=headline,
    )


# ------------------------------------------------------------------------------- stop-loss


def _metric_display(metric: str, value: Decimal | None) -> str:
    if value is None:
        return "—"
    if metric.endswith("_chf"):
        return fmt_chf(value)
    if metric in ("contribution_pct", "ecoulement_stock_pilote"):
        return fmt_pct(value)
    if metric.startswith("jours"):
        return f"{_fmt_dec(value, '0.01')} j"
    return _fmt_dec(value, "1") if value == value.to_integral_value() else _fmt_dec(value, "0.01")


REARM_INSTRUCTIONS: tuple[str, ...] = (
    "Seule la propriétaire réarme, depuis un canal direct (terminal ou formulaire authentifié), jamais via un "
    "agent, un workflow ou un chat.",
    "Lire le rapport (valeur nette, cause) et GET /stoploss/status : rearm_reference.net_worth_chf (valeur nette "
    "de la photo) et rearm_reference.photo_sha256 ; décider et écrire le motif (docs/00-pilotage/STOP_LOSS.md §5).",
    "Appel : POST /stoploss/rearm avec les en-têtes X-Pokeshop-Token et X-Pokeshop-Owner-Token (votre jeton, "
    'distinct) et le corps {"reason": "…", "rebase": true, "reference_chf": "<rearm_reference.net_worth_chf>", '
    '"photo_sha256": "<rearm_reference.photo_sha256>"} : vous attestez la valeur nette (écart > 1 CHF ou photo '
    "remplacée => 409). Un jeton erroné est refusé et journalisé.",
    "L'autonomie reste au niveau 1 : la remonter est une décision distincte (POST /autonomy, un niveau à la fois).",
)


def stoploss_block(view: StopLossView | None, *, autonomy_level: int | None = None) -> StopLossBlock:
    """État des six niveaux (déclencheurs triés du plus grave au moins grave par le moteur)."""
    levels_zero = tuple(LevelCount(level=lv, label=LEVEL_LABELS_FR[lv], count=0) for lv in StopLossLevel)
    if view is None:
        return StopLossBlock(
            available=False,
            error="aucune photo d'activité transmise au moteur",
            autonomy_level=autonomy_level,
            headline="Stop-loss non évalué : source non branchée (POST /stoploss/state puis GET /stoploss/status).",
            levels=levels_zero,
        )
    lines = tuple(
        TriggerLine(
            level=t.level,
            level_label=LEVEL_LABELS_FR[t.level],
            scope=t.scope,
            metric=t.metric,
            value_display=_metric_display(t.metric, t.value),
            threshold_display=_metric_display(t.metric, t.threshold),
            action=t.action,
            action_label=ACTION_LABELS_FR[t.action] + (" (verrouillé)" if t.latched else ""),
            reason=t.reason,
            latched=t.latched,
        )
        for t in view.triggers
    )
    counts: dict[StopLossLevel, set[tuple[str, str]]] = {lv: set() for lv in StopLossLevel}
    for t in view.triggers:
        counts[t.level].add((t.scope, t.metric))
    levels = tuple(LevelCount(level=lv, label=LEVEL_LABELS_FR[lv], count=len(counts[lv])) for lv in StopLossLevel)
    status_obj = view.status
    level = status_obj.autonomy_level if status_obj is not None else autonomy_level
    frozen = view.global_frozen or (status_obj is not None and status_obj.global_frozen)
    rearm = REARM_INSTRUCTIONS if frozen else ()
    if not view.available:
        since = ""
        if view.latch_since is not None:
            since = f" depuis le {view.latch_since.isoformat(timespec='minutes')}"
        headline = (
            f"Gel global verrouillé{since} ; photo d'activité non évaluable : {view.error}."
            if frozen
            else f"Stop-loss non évaluable : {view.error}. Les dépenses sont refusées tant que l'état manque."
        )
        return StopLossBlock(
            available=False,
            error=view.error,
            global_frozen=frozen,
            autonomy_level=1 if frozen else level,
            status="CRITIQUE" if frozen else "INDISPONIBLE",
            headline=headline,
            triggers=lines,
            levels=levels,
            rearm_instructions=rearm,
        )
    critical_levels = {StopLossLevel.GLOBAL, StopLossLevel.CASH}
    if frozen or any(t.level in critical_levels for t in view.triggers):
        status: KpiStatus = "CRITIQUE"
    elif view.triggers:
        status = "ALERTE"
    else:
        status = "OK"
    active = [lc for lc in levels if lc.count]
    if frozen:
        headline = "GEL GLOBAL : tout est gelé, autonomie au niveau 1 ; réarmement par la propriétaire uniquement."
    elif active:
        headline = "Stop-loss actifs : " + " ; ".join(f"{lc.label.lower()} ({lc.count})" for lc in active) + "."
    else:
        headline = "Aucun stop-loss déclenché."
    return StopLossBlock(
        available=True,
        global_frozen=frozen,
        autonomy_level=level,
        status=status,
        headline=headline,
        triggers=lines,
        levels=levels,
        blocked_products=status_obj.blocked_products if status_obj else (),
        no_reorder_extensions=status_obj.no_reorder_extensions if status_obj else (),
        cut_campaigns=(("*",) if status_obj and status_obj.ads_globally_cut else ())
        + (status_obj.cut_campaigns if status_obj else ()),
        rearm_instructions=rearm,
    )


# ------------------------------------------------------------------------------ décisions


def pending_decisions(inputs: DashboardInputs) -> tuple[Decision, ...]:
    """Décisions attendues : gels du stop-loss, dépenses hors mandat, réassorts, incidents."""
    out: list[Decision] = []
    as_of = inputs.as_of
    view = inputs.stoploss
    status = view.status if view is not None else None
    if view is not None and (view.global_frozen or (status is not None and status.global_frozen)):
        out.append(
            Decision(
                label="Stop-loss global : réarmer ou non (propriétaire uniquement, avec jeton et motif écrit).",
                source="stop-loss",
                ref="GLOBAL",
            )
        )
    if status is not None:
        if status.decision_report_due:
            out.append(Decision(label="Dossier temps : continuer, ajuster ou arrêter.", source="stop-loss", ref="TIME"))
        for ext in status.markdown_extensions:
            out.append(
                Decision(
                    label=f"Démarque proposée pour l'extension {ext} : accepter ou refuser (jamais sous le plancher).",
                    source="stop-loss",
                    ref=ext,
                )
            )
        if status.ads_globally_cut or status.cut_campaigns:
            names = ", ".join(("toutes",) if status.ads_globally_cut else status.cut_campaigns)
            out.append(
                Decision(
                    label=f"Campagne(s) coupée(s) ({names}) : nouveau plan de test ou arrêt.",
                    source="stop-loss",
                    ref="ADS",
                )
            )
        if status.blocked_products:
            out.append(
                Decision(
                    label="Référence(s) bloquée(s) : nouveau prix rentable ou exception écrite (C18) — "
                    + ", ".join(status.blocked_products),
                    source="stop-loss",
                    ref="PRODUCT",
                )
            )
    for entry in inputs.spend_entries or ():
        if entry.status is not SpendStatus.PENDING_HUMAN:
            continue
        due = entry.recorded_at + timedelta(hours=24)
        if due <= as_of:
            continue
        req = entry.request
        draft = " (virement préparé à signer)" if entry.decision.transfer_draft is not None else ""
        out.append(
            Decision(
                label=f"Dépense à valider : {req.purpose} — {fmt_chf(entry.decision.amount_chf)} "
                f"chez {req.supplier_id}{draft}.",
                source="mandat",
                ref=entry.idempotency_key,
                due=due,
            )
        )
    for proposal in inputs.reorder_proposals or ():
        due = proposal.generated_at + timedelta(hours=24)
        if not proposal.lines or due <= as_of:
            continue
        out.append(
            Decision(
                label=f"Réassort proposé à valider : {len(proposal.lines)} ligne(s), "
                f"{fmt_chf(proposal.total_cost_chf)} (jamais passé automatiquement avant le niveau 4).",
                source="réassort",
                ref=proposal.inputs_hash[:12],
                due=due,
            )
        )
    for incident in inputs.incidents or ():
        if not incident.is_open or incident.simulation or incident.decision_expected.strip().lower() == "aucune":
            continue
        code = incident.code.value if incident.code else incident.kind
        out.append(
            Decision(
                label=f"Incident {incident.incident_id} ({code}) : {incident.decision_expected}.",
                source="incident",
                ref=incident.incident_id,
            )
        )
    return tuple(out)


# ------------------------------------------------------------------------- helpers de KPI


def _kpi(
    key: str,
    label: str,
    value: Decimal | int | str | None,
    unit: Unit,
    status: KpiStatus,
    *,
    detail: str = "",
    source: str = "",
    threshold: str = "",
) -> Kpi:
    return Kpi(
        key=key,
        label=label,
        value=value,
        unit=unit,
        display=_display(value, unit),
        status=status,
        detail=detail,
        source=source,
        threshold=threshold,
    )


def _missing(key: str, label: str, unit: Unit, source: str) -> Kpi:
    return _kpi(key, label, None, unit, "INDISPONIBLE", detail=f"Source à brancher : {source}.", source=source)


def _orders_in(entries: Sequence[ContributionEntry], start: datetime, end: datetime) -> set[str]:
    return {
        e.order_id
        for e in entries
        if e.post is Post.NET_SALES and e.amount > 0 and e.order_id and _in(e.at, start, end)
    }


def _refunds_in(entries: Sequence[ContributionEntry], start: datetime, end: datetime) -> tuple[int, Decimal]:
    refs = {e.ref for e in entries if e.post is Post.NET_SALES and e.amount < 0 and _in(e.at, start, end)}
    amount = sum(
        (-e.amount for e in entries if e.post is Post.NET_SALES and e.amount < 0 and _in(e.at, start, end)), ZERO
    )
    return len(refs), amount


def _net_orders(
    entries: Sequence[ContributionEntry],
    start: datetime,
    end: datetime,
    known: Sequence[ContributionEntry] | None = None,
) -> set[str]:
    """Commandes payées sur la période, nettes d'annulations et de remboursements complets (BP §9).

    ``known`` : écritures connues à la date de la photo (remboursements postérieurs à la période
    compris) ; défaut = ``entries``.
    """
    orders = _orders_in(entries, start, end)
    totals: dict[str, Decimal] = {}
    for e in known if known is not None else entries:
        if e.post is Post.NET_SALES and e.order_id in orders:
            totals[e.order_id] = totals.get(e.order_id, ZERO) + e.amount
    return {o for o in orders if totals.get(o, ZERO) > 0}


def _selected(entries: Sequence[ContributionEntry] | None, cutoff: datetime) -> list[ContributionEntry]:
    return [e for e in entries or () if e.at <= cutoff]


def _base_unavailable(inputs: DashboardInputs, names: Sequence[str]) -> tuple[str, ...]:
    labels = {
        "entries": "journal de l'étoile polaire (pokeshop.northstar)",
        "stoploss": "état du stop-loss (POST /stoploss/state)",
        "cash": "position de trésorerie (banque + PayPal − précommandes)",
        "open_orders": "commandes payées non expédiées (Shopify)",
        "stock_levels": "stock vendable local (registre du moteur)",
        "stock": "valorisation du stock au coût historique",
        "offers": "offres fournisseurs importées (horodatage des flux)",
        "incidents": "incidents (pokeshop.incidents)",
        "spend_entries": "registre du mandat de dépense",
        "reorder_proposals": "propositions de réassort",
        "sales": "lignes vendues au coût historique",
        "extensions": "exposition par extension",
        "ad_spends": "dépenses publicitaires par campagne",
        "cost_variances": "écarts facture / estimation (workflow facture → marge)",
        "after_sales": "journal SAV (litiges)",
        "time_entries": "heures de la propriétaire",
        "turnover": "CA déterminant mensuel de l'entité (comptabilité)",
        "tool_expenses": "dépenses outils (comptabilité)",
    }
    return tuple(labels[n] for n in names if getattr(inputs, n) is None)


# ---------------------------------------------------------------------------------- jour


def daily_report(
    inputs: DashboardInputs,
    config: DashboardConfig | None = None,
    *,
    day: date | None = None,
    now: datetime | None = None,
) -> DashboardReport:
    """Vue du jour (BP §12 « chaque jour ») ; ``day`` = veille de ``as_of`` par défaut (digest du matin)."""
    cfg = config or DashboardConfig()
    tz = cfg.tz
    as_of = inputs.as_of
    today = as_of.astimezone(tz).date()
    target = day or (today - timedelta(days=1))
    if target > today:
        raise DashboardError("jour postérieur à la date de la photo")
    start = _local_midnight(target, tz)
    end = _local_midnight(target + timedelta(days=1), tz)
    cutoff = min(as_of, end - timedelta(microseconds=1))
    label = _fmt_day_long(target)
    north = north_star_block(
        inputs.entries,
        cutoff=as_of,
        tz=tz,
        period_start=target,
        period_end=target + timedelta(days=1),
        period_label=label,
        history_weeks=cfg.history_weeks,
    )
    stop = stoploss_block(inputs.stoploss, autonomy_level=inputs.autonomy_level)
    kpis: list[Kpi] = []
    tables: list[Table] = []

    # 1-2. Ventes payées et contribution (étoile polaire, une seule source).
    if inputs.entries is None:
        kpis.append(_missing("ventes_payees", "Ventes payées", "nombre", "journal de l'étoile polaire"))
        kpis.append(_missing("contribution_jour", "Contribution du jour", "CHF", "journal de l'étoile polaire"))
    else:
        entries = _selected(inputs.entries, cutoff)
        orders = _orders_in(entries, start, end)
        totals = PostBreakdown.of(e for e in entries if _in(e.at, start, end))
        refund_count, refund_amount = _refunds_in(entries, start, end)
        detail = f"Ventes nettes HT {fmt_chf(totals.net_sales_ht)}"
        if refund_count:
            detail += f" ; {refund_count} remboursement(s) : −{fmt_chf(refund_amount)}"
        kpis.append(
            _kpi(
                "ventes_payees",
                "Ventes payées",
                len(orders),
                "nombre",
                "INFO",
                detail=detail,
                source="pokeshop.northstar (commandes payées)",
            )
        )
        after = totals.contribution_after_acquisition
        pct = _ratio(after, totals.net_sales_ht) if totals.net_sales_ht > 0 else None
        kpis.append(
            _kpi(
                "contribution_jour",
                "Contribution du jour (après acquisition, avant charges fixes)",
                after,
                "CHF",
                "ALERTE" if after < 0 else "OK",
                detail=f"{fmt_pct(pct)} des ventes nettes" if pct is not None else "Aucune vente nette ce jour.",
                source="pokeshop.northstar",
                threshold="< 0 : alerte ; par commande < 12 % ou < 8 CHF : stop-loss produit",
            )
        )

    # 3. Cash disponible (stop-loss cash).
    if inputs.cash is None:
        kpis.append(_missing("cash_disponible", "Cash disponible", "CHF", "position de trésorerie"))
    else:
        cash = inputs.cash
        margin = cash.cash_available_chf - cfg.cash_reserve_chf
        below = cash.cash_available_chf < cfg.cash_reserve_chf
        parts = [f"Réserve {fmt_chf(cfg.cash_reserve_chf)} ; écart {_fmt_signed_chf(margin)}"]
        if cash.preorders_collected_chf:
            parts.append(f"précommandes encaissées exclues : {fmt_chf(cash.preorders_collected_chf)}")
        parts.append(f"photo du {_fmt_dt(cash.as_of, tz)}")
        kpis.append(
            _kpi(
                "cash_disponible",
                "Cash disponible",
                cash.cash_available_chf,
                "CHF",
                "CRITIQUE" if below else "OK",
                detail=" ; ".join(parts),
                source="pokeshop.treasury / stop-loss cash",
                threshold=f"< {fmt_chf(cfg.cash_reserve_chf)} : plus d'achat ni de pub",
            )
        )

    # 4. Commandes à préparer.
    if inputs.open_orders is None:
        kpis.append(_missing("commandes_a_preparer", "Commandes à préparer", "nombre", "commandes Shopify"))
    else:
        rows: list[tuple[str, ...]] = []
        overdue = due_today = preorders = waiting = 0
        for order in sorted(inputs.open_orders, key=lambda o: o.paid_at):
            age = business_days_between(order.paid_at.astimezone(tz).date(), today)
            if order.preorder:
                preorders += 1
            if order.preorder and not order.allocation_received:
                waiting += 1
                state = "précommande : allocation attendue"
            elif age > cfg.shipping_delay_business_days:
                overdue += 1
                state = "EN RETARD"
            elif age == cfg.shipping_delay_business_days:
                due_today += 1
                state = "à remettre aujourd'hui"
            else:
                state = "dans le délai"
            rows.append(
                (
                    order.order_ref,
                    _fmt_dt(order.paid_at, tz),
                    f"{age} j ouvré(s)",
                    "oui" if order.preorder else "non",
                    state,
                )
            )
        to_prepare = len(inputs.open_orders) - waiting
        detail = f"Dont {preorders} précommande(s) ({waiting} en attente d'allocation)"
        if overdue:
            detail += f" ; {overdue} en retard"
        if due_today:
            detail += f" ; {due_today} à remettre aujourd'hui"
        kpis.append(
            _kpi(
                "commandes_a_preparer",
                "Commandes à préparer",
                to_prepare,
                "nombre",
                "ALERTE" if overdue else "OK",
                detail=detail,
                source="Shopify (payées, non expédiées)",
                threshold=f"> {cfg.shipping_delay_business_days} jours ouvrés après paiement : alerte "
                "(hypothèse DELAI_EXPEDITION)",
            )
        )
        tables.append(
            Table(
                key="commandes_a_preparer",
                title="Commandes à préparer (tâche humaine : SOP_PREPARATION_COLIS.md)",
                columns=("Commande", "Payée le", "Âge", "Précommande", "État"),
                rows=tuple(rows),
                empty_text="Aucune commande en attente.",
            )
        )

    # 5. Ruptures locales.
    if inputs.stock_levels is None:
        kpis.append(_missing("ruptures_locales", "Ruptures locales", "nombre", "stock vendable local"))
    else:
        published = {p.sku for p in inputs.stock or () if p.published and p.sku}
        scope = [lv for lv in inputs.stock_levels if inputs.stock is None or lv.sku in published]
        out_of_stock = sorted(lv.sku for lv in scope if lv.sellable == 0)
        kpis.append(
            _kpi(
                "ruptures_locales",
                "Ruptures locales",
                len(out_of_stock),
                "nombre",
                "INFO" if out_of_stock else "OK",
                detail=", ".join(out_of_stock) if out_of_stock else "Toutes les références publiées sont vendables.",
                source="registre de stock du moteur (vendable = physique − réservé − endommagé − sécurité)",
            )
        )

    # 6. Offres fournisseurs périmées et flux en panne.
    if inputs.offers is None:
        kpis.append(_missing("offres_perimees", "Offres fournisseurs périmées", "nombre", "imports fournisseurs"))
    else:
        stale = [o for o in inputs.offers if is_stale(o.source_ts, as_of, cfg.max_offer_age)]
        newest: dict[str, datetime] = {}
        for o in inputs.offers:
            newest[o.supplier_id] = max(newest.get(o.supplier_id, o.source_ts), o.source_ts)
        down = sorted(s for s, ts in newest.items() if is_stale(ts, as_of, cfg.max_offer_age))
        kpis.append(
            _kpi(
                "offres_perimees",
                "Offres fournisseurs périmées (> 24 h)",
                len(stale),
                "nombre",
                "ALERTE" if stale else "OK",
                detail=("Flux en panne : " + ", ".join(down)) if down else "Aucun flux en panne.",
                source="imports fournisseurs (source_ts)",
                threshold="> 24 h : achats et nouvelles promesses bloqués ; le stock local se vend",
            )
        )
        tables.append(
            Table(
                key="flux_fournisseurs",
                title="Fraîcheur des flux fournisseurs",
                columns=("Fournisseur", "Dernière donnée", "Offres", "Périmées", "État"),
                rows=tuple(
                    (
                        s,
                        _fmt_dt(newest[s], tz),
                        str(sum(1 for o in inputs.offers if o.supplier_id == s)),
                        str(sum(1 for o in stale if o.supplier_id == s)),
                        "EN PANNE" if s in down else "à jour",
                    )
                    for s in sorted(newest)
                ),
                empty_text="Aucune offre importée.",
            )
        )

    # 7. Incidents ouverts.
    if inputs.incidents is None:
        kpis.append(_missing("incidents_ouverts", "Incidents ouverts", "nombre", "pokeshop.incidents"))
    else:
        open_real = [i for i in inputs.incidents if i.is_open and not i.simulation]
        simulated = sum(1 for i in inputs.incidents if i.is_open and i.simulation)
        by_sop = {lab: sum(1 for i in open_real if i.severity.sop_label == lab) for lab in ("S1", "S2", "S3", "INFO")}
        status: KpiStatus = "CRITIQUE" if by_sop["S1"] else ("ALERTE" if by_sop["S2"] else "OK")
        detail = f"S1 {by_sop['S1']} | S2 {by_sop['S2']} | S3 {by_sop['S3']}"
        if simulated:
            detail += f" ; {simulated} en simulation (sans confinement)"
        kpis.append(
            _kpi(
                "incidents_ouverts",
                "Incidents ouverts",
                len(open_real),
                "nombre",
                status,
                detail=detail,
                source="pokeshop.incidents",
                threshold="un S1 ouvert : alerte immédiate",
            )
        )
        ordered = sorted(open_real, key=lambda i: (-i.severity.rank, i.opened_at))
        tables.append(
            Table(
                key="incidents_ouverts",
                title="Incidents ouverts (SOP_INCIDENTS.md)",
                columns=("Gravité", "Code", "Titre", "Cible", "Ouvert le", "Action proposée"),
                rows=tuple(
                    (
                        i.severity.sop_label,
                        i.code.value if i.code else i.kind,
                        i.title,
                        i.target,
                        _fmt_dt(i.opened_at, tz),
                        i.proposed_action,
                    )
                    for i in ordered
                ),
                empty_text="Aucun incident ouvert.",
            )
        )

    decisions = pending_decisions(inputs)
    kpis.append(
        _kpi(
            "decisions_attendues",
            "Décisions attendues",
            len(decisions),
            "nombre",
            "ALERTE" if decisions else "OK",
            detail="Réponse oui / non avant l'échéance (statu quo sûr sinon).",
            source="stop-loss, mandat, réassort, incidents",
        )
    )
    return DashboardReport(
        kind="daily",
        title="Tableau de bord du jour",
        period_label=label,
        period_start=target,
        period_end=target + timedelta(days=1),
        complete=as_of >= end,
        as_of=as_of,
        generated_at=now or datetime.now(UTC),
        fictif=inputs.fictif,
        north_star=north,
        stoploss=stop,
        kpis=tuple(kpis),
        tables=tuple(tables),
        decisions=decisions,
        unavailable=_base_unavailable(
            inputs, ("entries", "stoploss", "cash", "open_orders", "stock_levels", "offers", "incidents")
        ),
    )


# ------------------------------------------------------------------------------- semaine


def _week_label(monday: date) -> str:
    year, week, _ = monday.isocalendar()
    sunday = monday + timedelta(days=6)
    return f"Semaine {year}-W{week:02d} ({monday.day} {_MONTHS_FR[monday.month - 1]} – {_fmt_date(sunday)})"


def weekly_report(
    inputs: DashboardInputs,
    config: DashboardConfig | None = None,
    *,
    week: date | None = None,
    now: datetime | None = None,
) -> DashboardReport:
    """Vue de la semaine (BP §12 « chaque semaine ») ; ``week`` = lundi (défaut : dernière semaine close)."""
    cfg = config or DashboardConfig()
    tz = cfg.tz
    as_of = inputs.as_of
    today = as_of.astimezone(tz).date()
    monday = week_start(week) if week is not None else week_start(today) - timedelta(days=7)
    if monday > today:
        raise DashboardError("semaine postérieure à la date de la photo")
    sunday_end = monday + timedelta(days=7)
    start = _local_midnight(monday, tz)
    end = _local_midnight(sunday_end, tz)
    cutoff = min(as_of, end - timedelta(microseconds=1))
    label = _week_label(monday)
    north = north_star_block(
        inputs.entries,
        cutoff=cutoff,
        tz=tz,
        period_start=monday,
        period_end=sunday_end,
        period_label=label,
        history_weeks=cfg.history_weeks,
    )
    stop = stoploss_block(inputs.stoploss, autonomy_level=inputs.autonomy_level)
    kpis: list[Kpi] = []
    tables: list[Table] = []
    entries = _selected(inputs.entries, cutoff)
    totals = PostBreakdown.of(e for e in entries if _in(e.at, start, end))

    # Étoile polaire de la semaine.
    if inputs.entries is None:
        kpis.append(_missing("contribution_nette_semaine", "Contribution nette de la semaine", "CHF", "étoile polaire"))
    else:
        kpis.append(
            _kpi(
                "contribution_nette_semaine",
                "Contribution nette de la semaine",
                totals.net_contribution,
                "CHF",
                "ALERTE" if totals.net_contribution < 0 else "OK",
                detail=f"Après acquisition, avant charges fixes : {fmt_chf(totals.contribution_after_acquisition)} ; "
                f"charges fixes : {fmt_chf(totals.fixed_costs)}",
                source="pokeshop.northstar",
            )
        )

    # CAC (BP §9 : commandes payées nettes d'annulations et de remboursements).
    if inputs.entries is None:
        kpis.append(_missing("cac", "CAC de la semaine", "CHF", "étoile polaire (acquisition)"))
    else:
        net_orders = _net_orders(entries, start, end, known=_selected(inputs.entries, as_of))
        n = len(net_orders)
        spend = totals.acquisition
        contrib_per_order = _q2(totals.contribution_before_acquisition / n) if n else None
        if spend == 0:
            kpis.append(
                _kpi(
                    "cac",
                    "CAC de la semaine",
                    ZERO,
                    "CHF",
                    "INFO",
                    detail="Aucune dépense d'acquisition.",
                    source="pokeshop.northstar (acquisition réelle)",
                )
            )
        elif n == 0:
            kpis.append(
                _kpi(
                    "cac",
                    "CAC de la semaine",
                    None,
                    "CHF",
                    "ALERTE",
                    detail=f"{fmt_chf(spend)} dépensés sans commande payée nette : CAC infini.",
                    source="pokeshop.northstar (acquisition réelle)",
                )
            )
        else:
            cac = _q2(spend / Decimal(n))
            assert contrib_per_order is not None
            kpis.append(
                _kpi(
                    "cac",
                    "CAC de la semaine",
                    cac,
                    "CHF",
                    "ALERTE" if spend > totals.contribution_before_acquisition else "OK",
                    detail=f"{fmt_chf(spend)} / {n} commande(s) payée(s) nette(s) (remboursements connus déduits) ; "
                    f"contribution avant acquisition {fmt_chf(contrib_per_order)} par commande",
                    source="pokeshop.northstar (acquisition réelle)",
                    threshold="CAC > contribution avant acquisition : la pub absorbe la marge (stop-loss pub sur 7 j)",
                )
            )
    if inputs.ad_spends is not None:
        window_days = {sunday_end - timedelta(days=i + 1) for i in range(7)}
        spend_by: dict[str, Decimal] = {}
        for s in inputs.ad_spends:
            if s.day in window_days:
                spend_by[s.campaign_id] = spend_by.get(s.campaign_id, ZERO) + s.amount
        rows: list[tuple[str, ...]] = []
        for campaign in sorted(spend_by):
            paid = [
                o
                for o in inputs.attributed_orders or ()
                if o.campaign_id == campaign and o.status == "PAID" and o.paid_at.astimezone(tz).date() in window_days
            ]
            contrib = sum((o.contribution_before_acquisition for o in paid), ZERO)
            cac_c = _q2(spend_by[campaign] / Decimal(len(paid))) if paid else None
            state = (
                "à couper"
                if (paid and spend_by[campaign] > contrib) or (not paid and spend_by[campaign] > 0)
                else "rentable"
            )
            rows.append(
                (
                    campaign,
                    fmt_chf(spend_by[campaign]),
                    str(len(paid)),
                    fmt_chf(cac_c),
                    fmt_chf(_q2(contrib / Decimal(len(paid)))) if paid else "—",
                    state,
                )
            )
        tables.append(
            Table(
                key="cac_campagnes",
                title="CAC par campagne (7 jours de la semaine, commandes payées nettes)",
                columns=("Campagne", "Dépense", "Commandes", "CAC", "Contribution / commande", "Lecture"),
                rows=tuple(rows),
                empty_text="Aucune campagne active.",
                note="La coupure effective est décidée par le stop-loss pub (7 jours glissants, plafond jour).",
            )
        )

    # Réachat.
    if inputs.sales is None:
        kpis.append(_missing("reachat", "Réachat", "%", "lignes vendues (pseudonyme client)"))
    else:
        first_order: dict[str, datetime] = {}
        order_customer: dict[str, tuple[str, datetime]] = {}
        for line in inputs.sales:
            if line.status == "CANCELLED" or line.customer_ref is None or line.sold_at > cutoff:
                continue
            known = order_customer.get(line.order_id)
            if known is None or line.sold_at < known[1]:
                order_customer[line.order_id] = (line.customer_ref, line.sold_at)
        for _, (customer, at) in order_customer.items():
            if customer not in first_order or at < first_order[customer]:
                first_order[customer] = at
        week_orders = {o: v for o, v in order_customer.items() if _in(v[1], start, end)}
        returning = sum(1 for _, (c, at) in week_orders.items() if first_order[c] < at)
        share = _ratio(Decimal(returning), Decimal(len(week_orders))) if week_orders else None
        kpis.append(
            _kpi(
                "reachat",
                "Réachat (commandes de clients existants)",
                share,
                "%",
                "INFO",
                detail=f"{returning} commande(s) sur {len(week_orders)}",
                source="lignes vendues (pseudonyme client, jamais l'email)",
            )
        )

    # Rotation et exposition par extension.
    if inputs.sales is None and inputs.extensions is None and inputs.stock is None:
        kpis.append(_missing("rotation", "Rotation par extension", "texte", "ventes au coût et stock au coût"))
    else:
        cogs: dict[str, Decimal] = {}
        for line in inputs.sales or ():
            if line.status == "PAID" and _in(line.sold_at, start, end):
                cogs[line.extension] = cogs.get(line.extension, ZERO) + line.cost_chf
        stock_by: dict[str, Decimal] = {}
        for p in inputs.stock or ():
            stock_by[p.extension] = stock_by.get(p.extension, ZERO) + p.value_at_cost
        exposure: dict[str, Decimal] = {}
        for ext in inputs.extensions or ():
            exposure[ext.extension] = ext.exposure
            stock_by.setdefault(ext.extension, ext.stock_value_at_cost)
        for name, value in stock_by.items():
            exposure.setdefault(name, value)
        cap = cfg.extension_cap_share * cfg.stock_budget_chf
        rows = []
        over = 0
        for name in sorted(set(cogs) | set(stock_by) | set(exposure)):
            sold = cogs.get(name, ZERO)
            held = stock_by.get(name, ZERO)
            expo = exposure.get(name, held)
            share = _ratio(expo, cfg.stock_budget_chf)
            rotation = _ratio(sold, held) if held > 0 else None
            coverage = f"{_fmt_dec(held / (sold / Decimal(7)), '1')} j" if sold > 0 else "∞ (aucune vente)"
            flag = expo > cap
            over += 1 if flag else 0
            rows.append(
                (
                    name,
                    fmt_chf(sold),
                    fmt_chf(held),
                    fmt_pct(rotation),
                    coverage,
                    fmt_pct(share),
                    "> plafond" if flag else "ok",
                )
            )
        kpis.append(
            _kpi(
                "extensions_au_dessus_plafond",
                "Extensions au-dessus du plafond de 25 %",
                over,
                "nombre",
                "ALERTE" if over else "OK",
                detail=f"Plafond {fmt_chf(cap)} par extension (stock + engagé)",
                source="valorisation au coût historique",
                threshold="> 25 % du budget stock : stop-loss extension",
            )
        )
        tables.append(
            Table(
                key="rotation_extensions",
                title="Rotation par extension (coût des ventes de la semaine / stock au coût en fin de période)",
                columns=(
                    "Extension",
                    "Ventes au coût",
                    "Stock au coût",
                    "Rotation",
                    "Couverture",
                    "Part du budget",
                    "Plafond 25 %",
                ),
                rows=tuple(rows),
                empty_text="Aucun stock ni vente.",
            )
        )

    # Produits sans vente (14, 30, 45 jours).
    if inputs.stock is None:
        kpis.append(_missing("produits_sans_vente", "Produits sans vente", "nombre", "valorisation du stock"))
    else:
        last_sale: dict[str, datetime] = {}
        for line in inputs.sales or ():
            if line.status != "CANCELLED" and line.sold_at <= cutoff:
                last_sale[line.product_key] = max(last_sale.get(line.product_key, line.sold_at), line.sold_at)
        first, second, third = cfg.no_sale_days
        rows = []
        worst = 0
        for p in sorted(inputs.stock, key=lambda x: x.product_key):
            if p.qty_on_hand <= 0:
                continue
            reference = last_sale.get(p.product_key) or p.first_stocked_at
            if reference is None:
                continue
            days = (cutoff - reference).days
            if days < first:
                continue
            bucket = (
                f"≥ {third} j (stop-loss extension)"
                if days >= third
                else (f"≥ {second} j" if days >= second else f"≥ {first} j")
            )
            worst = max(worst, days)
            since = "dernière vente" if p.product_key in last_sale else "entrée en stock, aucune vente"
            rows.append((p.product_key, p.extension, f"{days} j", since, fmt_chf(p.value_at_cost), bucket))
        kpis.append(
            _kpi(
                "produits_sans_vente",
                f"Produits sans vente depuis {first} jours ou plus",
                len(rows),
                "nombre",
                "ALERTE" if worst >= third else ("INFO" if rows else "OK"),
                detail=f"Seuils {first} / {second} / {third} jours",
                source="ventes et stock au coût",
                threshold=f"{third} j : stop-loss extension (plus de réassort, démarque proposée)",
            )
        )
        tables.append(
            Table(
                key="produits_sans_vente",
                title="Produits sans vente",
                columns=("Référence", "Extension", "Depuis", "Repère", "Stock au coût", "Seuil"),
                rows=tuple(rows),
                empty_text=f"Toutes les références en stock se sont vendues depuis moins de {first} jours.",
            )
        )

    # Écarts de coûts (facture réelle vs estimation).
    if inputs.cost_variances is None:
        kpis.append(_missing("ecarts_couts", "Écarts de coûts", "nombre", "workflow facture → marge réelle"))
    else:
        week_var = [v for v in inputs.cost_variances if _in(v.at, start, end) and v.at <= cutoff]
        above = [v for v in week_var if abs(v.delta_pct) > cfg.cost_variance_alert_share]
        kpis.append(
            _kpi(
                "ecarts_couts",
                "Écarts de coûts > 2 %",
                len(above),
                "nombre",
                "ALERTE" if above else "OK",
                detail=f"{len(week_var)} lot(s) rapproché(s) ; écart total "
                f"{fmt_chf(sum((v.delta_total for v in week_var), ZERO))}",
                source="HistoricalCostLedger.apply_invoice",
                threshold="> 2 % : explication écrite",
            )
        )
        tables.append(
            Table(
                key="ecarts_couts",
                title="Écarts facture / estimation par lot",
                columns=("Lot", "Référence", "Estimé", "Facturé", "Écart", "Écart total", "Facture"),
                rows=tuple(
                    (
                        v.lot_id,
                        v.product_key,
                        fmt_chf(v.estimated_unit_cost),
                        fmt_chf(v.actual_unit_cost),
                        fmt_pct(v.delta_pct),
                        fmt_chf(v.delta_total),
                        v.invoice_ref,
                    )
                    for v in week_var
                ),
                empty_text="Aucune facture rapprochée cette semaine.",
            )
        )

    # Litiges, remboursements, coût SAV.
    if inputs.after_sales is None:
        kpis.append(_missing("litiges", "Litiges", "nombre", "journal SAV"))
    else:
        opened = [c for c in inputs.after_sales if c.kind == "LITIGE" and _in(c.opened_at, start, end)]
        still_open = [
            c for c in inputs.after_sales if c.kind == "LITIGE" and c.status == "OUVERT" and c.opened_at <= cutoff
        ]
        kpis.append(
            _kpi(
                "litiges",
                "Litiges ouverts dans la semaine",
                len(opened),
                "nombre",
                "ALERTE" if still_open else "OK",
                detail=f"{len(still_open)} litige(s) encore ouvert(s)",
                source="journal SAV",
                threshold="litige complexe : escalade propriétaire",
            )
        )
    if inputs.entries is None:
        kpis.append(_missing("remboursements", "Remboursements", "nombre", "étoile polaire"))
        kpis.append(_missing("cout_sav_par_commande", "Coût SAV par commande", "CHF", "étoile polaire"))
    else:
        count, amount = _refunds_in(entries, start, end)
        kpis.append(
            _kpi(
                "remboursements",
                "Remboursements",
                count,
                "nombre",
                "INFO" if count else "OK",
                detail=f"Montant (ventes nettes HT) : {fmt_chf(amount)}",
                source="pokeshop.northstar",
            )
        )
        n_orders = len(_orders_in(entries, start, end))
        per_order = _q2(totals.after_sales / Decimal(n_orders)) if n_orders else None
        if per_order is None:
            sav_status: KpiStatus = "ALERTE" if totals.after_sales > 0 else "OK"
        else:
            sav_status = "ALERTE" if per_order > cfg.after_sales_provision_chf else "OK"
        kpis.append(
            _kpi(
                "cout_sav_par_commande",
                "Coût SAV par commande",
                per_order,
                "CHF",
                sav_status,
                detail=f"SAV réel {fmt_chf(totals.after_sales)} sur {n_orders} commande(s)",
                source="pokeshop.northstar (dépenses SAV réelles)",
                threshold=f"> provision R {fmt_chf(cfg.after_sales_provision_chf)} : revue (BP §4)",
            )
        )

    # Commandes proposées (réassort à valider).
    if inputs.reorder_proposals is None:
        kpis.append(_missing("commandes_proposees", "Commandes proposées", "nombre", "propositions de réassort"))
    else:
        week_props = [
            p
            for p in inputs.reorder_proposals
            if p.generated_at <= as_of
            and (_in(p.generated_at, start, end) or p.generated_at + timedelta(hours=24) > as_of)
        ]
        lines = [ln for p in week_props for ln in p.lines]
        total = sum((p.total_cost_chf for p in week_props), ZERO)
        kpis.append(
            _kpi(
                "commandes_proposees",
                "Lignes de réassort proposées (semaine ou en attente)",
                len(lines),
                "nombre",
                "INFO" if lines else "OK",
                detail=f"Total {fmt_chf(total)} ; à valider (aucune commande automatique avant le niveau 4)",
                source="pokeshop.stock.propose_reorder",
            )
        )
        tables.append(
            Table(
                key="commandes_proposees",
                title="Réassort proposé (à valider)",
                columns=("Référence", "Extension", "Fournisseur", "Quantité", "Coût unitaire", "Total", "Notes"),
                rows=tuple(
                    (
                        ln.product_key,
                        ln.extension,
                        ln.supplier_id,
                        str(ln.qty),
                        fmt_chf(ln.unit_cost_chf),
                        fmt_chf(ln.line_cost_chf),
                        " ; ".join(ln.notes),
                    )
                    for ln in lines
                ),
                empty_text="Aucune proposition cette semaine.",
                note="Écartées : "
                + ", ".join(sorted({f"{s.product_key} ({s.reason})" for p in week_props for s in p.skipped}))
                if any(p.skipped for p in week_props)
                else "",
            )
        )

    # Temps de la propriétaire.
    if inputs.time_entries is None:
        kpis.append(_missing("heures_proprietaire", "Heures de la propriétaire", "heures", "saisie hebdomadaire"))
    else:
        hours = sum((t.hours for t in inputs.time_entries if monday <= t.day < sunday_end), ZERO)
        kpis.append(
            _kpi(
                "heures_proprietaire",
                "Heures de la propriétaire",
                hours,
                "heures",
                "ALERTE" if hours > cfg.owner_hours_alert_per_week else "OK",
                detail="Supervision et physique (colis, réception, photos)",
                source="saisie hebdomadaire",
                threshold=f"> {_fmt_dec(cfg.owner_hours_alert_per_week)} h deux semaines de suite : proposer un "
                "prestataire ou réduire le rythme",
            )
        )

    if inputs.entries is not None:
        tables.insert(
            0,
            Table(
                key="etoile_postes",
                title=f"Étoile polaire — postes de la semaine ({label})",
                columns=("Poste", "Montant"),
                rows=tuple((pl.label, pl.signed_display) for pl in north.posts)
                + (("Contribution nette", fmt_chf(totals.net_contribution)),),
            ),
        )
    return DashboardReport(
        kind="weekly",
        title="Revue hebdomadaire",
        period_label=label,
        period_start=monday,
        period_end=sunday_end,
        complete=as_of >= end,
        as_of=as_of,
        generated_at=now or datetime.now(UTC),
        fictif=inputs.fictif,
        north_star=north,
        stoploss=stop,
        kpis=tuple(kpis),
        tables=tuple(tables),
        decisions=pending_decisions(inputs),
        unavailable=_base_unavailable(
            inputs,
            (
                "entries",
                "stoploss",
                "sales",
                "stock",
                "extensions",
                "ad_spends",
                "cost_variances",
                "after_sales",
                "reorder_proposals",
                "time_entries",
            ),
        ),
    )


# --------------------------------------------------------------------------------- mois


def monthly_report(
    inputs: DashboardInputs,
    config: DashboardConfig | None = None,
    *,
    month: str | None = None,
    now: datetime | None = None,
) -> DashboardReport:
    """Vue du mois (BP §12 « chaque mois ») ; ``month`` = ``AAAA-MM`` (défaut : mois précédent)."""
    cfg = config or DashboardConfig()
    tz = cfg.tz
    as_of = inputs.as_of
    today = as_of.astimezone(tz).date()
    key = month or _previous_month(today)
    first, after = _month_bounds(key)
    if first > today:
        raise DashboardError("mois postérieur à la date de la photo")
    start = _local_midnight(first, tz)
    end = _local_midnight(after, tz)
    cutoff = min(as_of, end - timedelta(microseconds=1))
    label = f"{_MONTHS_FR[first.month - 1]} {first.year}"
    north = north_star_block(
        inputs.entries,
        cutoff=cutoff,
        tz=tz,
        period_start=first,
        period_end=after,
        period_label=label,
        history_weeks=cfg.history_weeks,
    )
    stop = stoploss_block(inputs.stoploss, autonomy_level=inputs.autonomy_level)
    kpis: list[Kpi] = []
    tables: list[Table] = []
    entries = _selected(inputs.entries, cutoff)
    totals = PostBreakdown.of(e for e in entries if _in(e.at, start, end))

    # Résultat avec valorisation du temps (BP §3 : second compte de résultat).
    result: Decimal | None = None
    if inputs.entries is None:
        kpis.append(_missing("resultat_mois", "Résultat du mois (étoile polaire)", "CHF", "étoile polaire"))
    else:
        result = totals.net_contribution
        kpis.append(
            _kpi(
                "resultat_mois",
                "Résultat du mois (contribution nette)",
                result,
                "CHF",
                "ALERTE" if result < 0 else "OK",
                detail=f"Charges fixes comptées : {fmt_chf(totals.fixed_costs)} (BP §3 : "
                f"{fmt_chf(cfg.monthly_fixed_costs_chf)} par mois)",
                source="pokeshop.northstar",
            )
        )
    hours: Decimal | None = None
    if inputs.time_entries is None:
        kpis.append(_missing("heures_mois", "Heures de la propriétaire", "heures", "saisie hebdomadaire"))
    else:
        hours = sum((t.hours for t in inputs.time_entries if first <= t.day < after), ZERO)
        kpis.append(
            _kpi("heures_mois", "Heures de la propriétaire", hours, "heures", "INFO", source="saisie hebdomadaire")
        )
    if hours is None or result is None:
        kpis.append(_missing("taux_horaire_implicite", "Taux horaire implicite", "CHF/h", "résultat et heures"))
    else:
        implicit = _q2(result / hours) if hours > 0 else None
        kpis.append(
            _kpi(
                "taux_horaire_implicite",
                "Taux horaire implicite",
                implicit,
                "CHF/h",
                "ALERTE" if implicit is not None and implicit < 0 else "INFO",
                detail="Résultat du mois / heures de la propriétaire",
                source="pokeshop.northstar + saisie",
            )
        )
        if cfg.hourly_rate_chf is None:
            kpis.append(
                _kpi(
                    "resultat_apres_temps",
                    "Résultat après valorisation du temps",
                    None,
                    "CHF",
                    "INDISPONIBLE",
                    detail="Taux horaire à fixer par la propriétaire (TAUX_HORAIRE_VALORISATION).",
                    source="ROUTINES_PILOTAGE.md §5",
                )
            )
        else:
            valuation = _q2(hours * cfg.hourly_rate_chf)
            after_time = result - valuation
            kpis.append(
                _kpi(
                    "resultat_apres_temps",
                    "Résultat après valorisation du temps",
                    after_time,
                    "CHF",
                    "ALERTE" if after_time < 0 else "OK",
                    detail=f"{_fmt_dec(hours)} h × {fmt_chf(cfg.hourly_rate_chf)}/h = {fmt_chf(valuation)}",
                    source="second compte de résultat (BP §3)",
                )
            )

    # Seuil TVA (CA déterminant de toute l'entité, 12 mois glissants).
    if inputs.turnover is None:
        kpis.append(_missing("seuil_tva", "Seuil TVA (12 mois glissants)", "%", "comptabilité de l'entité"))
    else:
        by_month = {t.month: t.amount_chf for t in inputs.turnover}
        months = [_shift_month(key, -i) for i in range(11, -1, -1)]
        known = [m for m in months if m in by_month]
        rolling = sum((by_month[m] for m in known), ZERO)
        check = vat_threshold_check(rolling, cfg.vat_threshold_chf)
        last3 = [m for m in months[-3:] if m in by_month]
        projection = _q2(sum((by_month[m] for m in last3), ZERO) * Decimal(12) / Decimal(len(last3))) if last3 else None
        alert_level = cfg.vat_alert_share * cfg.vat_threshold_chf
        if check.exceeds:
            vat_status: KpiStatus = "CRITIQUE"
        elif rolling >= alert_level or (projection is not None and projection >= alert_level):
            vat_status = "ALERTE"
        else:
            vat_status = "OK"
        detail = f"12 mois glissants : {fmt_chf(rolling)} ({len(known)} mois connus)"
        if projection is not None:
            detail += f" ; projection annuelle au rythme des {len(last3)} derniers mois : {fmt_chf(projection)}"
        kpis.append(
            _kpi(
                "seuil_tva",
                "Seuil TVA (12 mois glissants / 100 000 CHF)",
                _q4(check.ratio),
                "%",
                vat_status,
                detail=detail,
                source="comptabilité de toute l'entité (fiduciaire)",
                threshold=f"≥ {fmt_pct(cfg.vat_alert_share)} du seuil (hypothèse) : saisir la fiduciaire",
            )
        )
        tables.append(
            Table(
                key="ca_tva",
                title="CA déterminant mensuel de l'entité (hors TVA)",
                columns=("Mois", "CA déterminant", "Source"),
                rows=tuple(
                    (m, fmt_chf(by_month[m]), next(t.source for t in inputs.turnover if t.month == m)) for m in known
                ),
                empty_text="Aucun mois renseigné.",
                note="L'analyse d'assujettissement reste celle de la fiduciaire (BP §4).",
            )
        )

    # Capacité stock.
    if inputs.stock is None and inputs.extensions is None:
        kpis.append(_missing("capacite_stock", "Capacité stock", "CHF", "valorisation du stock"))
    else:
        held_by: dict[str, Decimal] = {}
        for p in inputs.stock or ():
            held_by[p.extension] = held_by.get(p.extension, ZERO) + p.value_at_cost
        engaged_by: dict[str, Decimal] = {}
        for ext in inputs.extensions or ():
            held_by.setdefault(ext.extension, ext.stock_value_at_cost)
            engaged_by[ext.extension] = ext.on_order_value
        held = sum(held_by.values(), ZERO)
        engaged = sum(engaged_by.values(), ZERO)
        remaining = cfg.stock_budget_chf - held - engaged
        kpis.append(
            _kpi(
                "capacite_stock",
                "Budget stock restant",
                remaining,
                "CHF",
                "ALERTE" if remaining < 0 else "OK",
                detail=f"Stock au coût {fmt_chf(held)} + engagé {fmt_chf(engaged)} sur {fmt_chf(cfg.stock_budget_chf)}",
                source="valorisation au coût historique (BP §3 budget stock)",
            )
        )
        cap = cfg.extension_cap_share * cfg.stock_budget_chf
        tables.append(
            Table(
                key="capacite_extensions",
                title=f"Marge sous le plafond par extension ({fmt_chf(cap)})",
                columns=("Extension", "Stock au coût", "Engagé", "Reste sous plafond"),
                rows=tuple(
                    (
                        name,
                        fmt_chf(held_by.get(name, ZERO)),
                        fmt_chf(engaged_by.get(name, ZERO)),
                        fmt_chf(cap - held_by.get(name, ZERO) - engaged_by.get(name, ZERO)),
                    )
                    for name in sorted(set(held_by) | set(engaged_by))
                ),
                empty_text="Aucun stock.",
            )
        )
        if cfg.storage_capacity_units is not None and inputs.stock is not None:
            units = sum(p.qty_on_hand for p in inputs.stock)
            share = Decimal(units) / Decimal(cfg.storage_capacity_units)
            kpis.append(
                _kpi(
                    "occupation_stockage",
                    "Occupation du lieu de stockage",
                    _q4(share),
                    "%",
                    "ALERTE" if share > 1 else "OK",
                    detail=f"{units} unité(s) pour {cfg.storage_capacity_units} places",
                    source="inventaire",
                )
            )

    # Dépenses outils.
    if inputs.tool_expenses is None:
        kpis.append(_missing("depenses_outils", "Dépenses outils", "CHF", "comptabilité"))
    else:
        items = [t for t in inputs.tool_expenses if t.month == key]
        spent = sum((t.amount_chf for t in items), ZERO)
        kpis.append(
            _kpi(
                "depenses_outils",
                "Dépenses outils du mois",
                spent,
                "CHF",
                "ALERTE" if spent > cfg.tools_monthly_envelope_chf else "OK",
                detail=f"Enveloppe BP §3 : {fmt_chf(cfg.tools_monthly_envelope_chf)} par mois",
                source="comptabilité",
                threshold="au-delà de l'enveloppe : résilier un outil inutile",
            )
        )
        tables.append(
            Table(
                key="depenses_outils",
                title="Dépenses outils du mois",
                columns=("Outil", "Montant", "Référence"),
                rows=tuple((t.tool, fmt_chf(t.amount_chf), t.ref) for t in items),
                empty_text="Aucune dépense outil ce mois.",
            )
        )

    if inputs.entries is not None:
        tables.insert(
            0,
            Table(
                key="etoile_postes",
                title=f"Étoile polaire — postes du mois ({label})",
                columns=("Poste", "Montant"),
                rows=tuple((pl.label, pl.signed_display) for pl in north.posts)
                + (("Contribution nette", fmt_chf(totals.net_contribution)),),
            ),
        )
    return DashboardReport(
        kind="monthly",
        title="Revue mensuelle",
        period_label=label,
        period_start=first,
        period_end=after,
        complete=as_of >= end,
        as_of=as_of,
        generated_at=now or datetime.now(UTC),
        fictif=inputs.fictif,
        north_star=north,
        stoploss=stop,
        kpis=tuple(kpis),
        tables=tuple(tables),
        decisions=pending_decisions(inputs),
        unavailable=_base_unavailable(
            inputs, ("entries", "stoploss", "time_entries", "turnover", "stock", "tool_expenses")
        ),
    )


def build_reports(
    inputs: DashboardInputs,
    config: DashboardConfig | None = None,
    *,
    day: date | None = None,
    week: date | None = None,
    month: str | None = None,
    now: datetime | None = None,
) -> DashboardBundle:
    """Les trois vues (jour, semaine, mois) sur la même photo ; ``now`` = horodatage de génération."""
    cfg = config or DashboardConfig()
    return DashboardBundle(
        daily=daily_report(inputs, cfg, day=day, now=now),
        weekly=weekly_report(inputs, cfg, week=week, now=now),
        monthly=monthly_report(inputs, cfg, month=month, now=now),
    )


# ------------------------------------------------------------------- démonstration FICTIVE

DEMO_TZ = ZoneInfo("Europe/Zurich")
DEMO_AS_OF = datetime(2026, 11, 16, 7, 30, tzinfo=DEMO_TZ)
"""Lundi 16 novembre 2026, 07:30 : digest du matin et revue hebdomadaire de la semaine 2026-W46."""


class _SilentNotifier:
    """Canal de démonstration : rien n'est envoyé (aucune écriture externe)."""

    channel = "demo"

    def send(self, notification: Notification) -> NotificationReceipt:
        return NotificationReceipt(channel=self.channel, delivered=False, dry_run=True, detail="démonstration")


def _demo_at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=DEMO_TZ)


def demo_inputs() -> DashboardInputs:
    """Jeu **FICTIF** complet, construit avec les fonctions du moteur (aucun prix ni EAN réel).

    Étoile polaire = exemple de ``docs/00-pilotage/ETOILE_POLAIRE.md`` §3 (W45 −53,49 ; W46 −81,17).
    Stop-loss évalué par :func:`pokeshop.stoploss.evaluate_levels` avec ``config/stoploss.v1.yaml`` et
    le point zéro de l'option A de ``STOP_LOSS.md`` §5 (4 200 CHF). Demande de dépense contrôlée par
    :func:`pokeshop.mandate.check` contre ``config/mandate.v1.yaml`` (non signé => validation humaine).
    """
    from .audit import InMemoryAuditLog
    from .costs import HistoricalCostLedger
    from .incidents import IncidentCode, IncidentManager
    from .mandate import SpendLedger, SpendRequest, TreasurySnapshot, check, load_mandate
    from .models import CostLot, ReorderCandidate
    from .pricing import contribution
    from .rules import load_rules
    from .stock import propose_reorder
    from .stoploss import (
        BalanceItem,
        CapitalMovement,
        NetWorthSnapshot,
        ProductMargin,
        StockValuationLine,
        ValidationWindow,
        load_stoploss_config,
    )

    as_of = DEMO_AS_OF
    w45 = date(2026, 11, 2)
    w46 = date(2026, 11, 9)
    rules = load_rules()

    # Coût historique (CMP) et étoile polaire : l'exemple chiffré à la main.
    display = HistoricalCostLedger("FICTIF_DISPLAY_ALPHA")
    etb = HistoricalCostLedger("FICTIF_ETB_BETA")
    booster = HistoricalCostLedger("FICTIF_BOOSTER_GAMMA")
    display.receive(
        CostLot(
            lot_id="FICTIF-LOT-DSP-01",
            product_key="FICTIF_DISPLAY_ALPHA",
            received_at=_demo_at(date(2026, 10, 29)),
            qty=5,
            unit_cost=Decimal("140.00"),
        )
    )
    etb.receive(
        CostLot(
            lot_id="FICTIF-LOT-ETB-01",
            product_key="FICTIF_ETB_BETA",
            received_at=_demo_at(date(2026, 10, 29)),
            qty=10,
            unit_cost=Decimal("60.00"),
        )
    )
    booster.receive(
        CostLot(
            lot_id="FICTIF-LOT-BST-01",
            product_key="FICTIF_BOOSTER_GAMMA",
            received_at=_demo_at(date(2026, 9, 30)),
            qty=24,
            unit_cost=Decimal("5.00"),
        )
    )
    ns = NorthStarLedger(timezone=DEMO_TZ.key)
    plan = (
        ("FICTIF-1001", w45 + timedelta(days=1), display, "184.92", "5.30"),
        ("FICTIF-1002", w45 + timedelta(days=3), etb, "87.88", "2.68"),
        ("FICTIF-1003", w46 + timedelta(days=1), display, "184.92", "5.30"),
        ("FICTIF-1004", w46 + timedelta(days=2), etb, "87.88", "2.68"),
        ("FICTIF-1005", w46 + timedelta(days=4), etb, "87.88", "2.68"),
    )
    for order_id, day, ledger, net, fee in plan:
        ns.record_order(order_id, _demo_at(day), net_sales_ht=net, payment_fees=fee, logistics="3.00")
        ledger.issue(1, order_id, _demo_at(day))
    ns.record_expense("FICTIF-pub-w45", _demo_at(w45 + timedelta(days=6)), Post.ACQUISITION, "20.00")
    ns.record_expense("FICTIF-fixes-w45", _demo_at(w45), Post.FIXED_COSTS, "92.31")
    ns.record_expense("FICTIF-fixes-w46", _demo_at(w46), Post.FIXED_COSTS, "92.31")
    refund_at = _demo_at(w46 + timedelta(days=5))
    ns.record_refund("FICTIF-R-1002", refund_at, net_sales_ht="87.88", order_id="FICTIF-1002")
    etb.return_units(1, Decimal("60.00"), "FICTIF-R-1002", refund_at)
    ns.record_expense("FICTIF-retour-1002", refund_at, Post.AFTER_SALES, "7.00")
    ns.record_expense("FICTIF-pub-w46", _demo_at(w46 + timedelta(days=6)), Post.ACQUISITION, "35.00")
    # Facture réelle du lot de boosters (+3 %) : écart porté sur le stock (aucune unité vendue).
    variance = booster.apply_invoice(
        "FICTIF-LOT-BST-01", Decimal("5.15"), "FICTIF-FACT-0042", _demo_at(w46 + timedelta(days=3))
    )
    for ledger in (display, etb, booster):
        ns.sync_cost_ledger(ledger)

    window_start = _demo_at(w45, 0)
    window = ns.totals(window_start, as_of)
    pilot_cost = sum(
        (_q2(Decimal(lot.qty) * lot.unit_cost) for lg in (display, etb, booster) for lot in lg.lots()), ZERO
    )
    sales = (
        SaleLine(
            order_id="FICTIF-1001",
            sold_at=_demo_at(w45 + timedelta(days=1)),
            product_key="FICTIF_DISPLAY_ALPHA",
            extension="FICTIF_ALPHA",
            qty=1,
            cost_chf=Decimal("140.00"),
            customer_ref="client-fictif-01",
        ),
        SaleLine(
            order_id="FICTIF-1002",
            sold_at=_demo_at(w45 + timedelta(days=3)),
            product_key="FICTIF_ETB_BETA",
            extension="FICTIF_BETA",
            qty=1,
            cost_chf=Decimal("60.00"),
            customer_ref="client-fictif-02",
            status="REFUNDED",
        ),
        SaleLine(
            order_id="FICTIF-1003",
            sold_at=_demo_at(w46 + timedelta(days=1)),
            product_key="FICTIF_DISPLAY_ALPHA",
            extension="FICTIF_ALPHA",
            qty=1,
            cost_chf=Decimal("140.00"),
            customer_ref="client-fictif-03",
        ),
        SaleLine(
            order_id="FICTIF-1004",
            sold_at=_demo_at(w46 + timedelta(days=2)),
            product_key="FICTIF_ETB_BETA",
            extension="FICTIF_BETA",
            qty=1,
            cost_chf=Decimal("60.00"),
            customer_ref="client-fictif-01",
        ),
        SaleLine(
            order_id="FICTIF-1005",
            sold_at=_demo_at(w46 + timedelta(days=4)),
            product_key="FICTIF_ETB_BETA",
            extension="FICTIF_BETA",
            qty=1,
            cost_chf=Decimal("60.00"),
            customer_ref="client-fictif-04",
        ),
    )
    stock = (
        ProductStock(
            product_key="FICTIF_DISPLAY_ALPHA",
            extension="FICTIF_ALPHA",
            sku="FICTIF-DSP-ALPHA",
            qty_on_hand=display.qty_on_hand,
            value_at_cost=display.total_value,
            first_stocked_at=_demo_at(date(2026, 10, 29)),
        ),
        ProductStock(
            product_key="FICTIF_ETB_BETA",
            extension="FICTIF_BETA",
            sku="FICTIF-ETB-BETA",
            qty_on_hand=etb.qty_on_hand,
            value_at_cost=etb.total_value,
            first_stocked_at=_demo_at(date(2026, 10, 29)),
        ),
        ProductStock(
            product_key="FICTIF_BOOSTER_GAMMA",
            extension="FICTIF_GAMMA",
            sku="FICTIF-BST-GAMMA",
            qty_on_hand=booster.qty_on_hand,
            value_at_cost=booster.total_value,
            first_stocked_at=_demo_at(date(2026, 9, 30)),
        ),
        ProductStock(
            product_key="FICTIF_TRIPACK_ALPHA",
            extension="FICTIF_ALPHA",
            sku="FICTIF-TRI-ALPHA",
            qty_on_hand=0,
            value_at_cost=ZERO,
            first_stocked_at=None,
        ),
    )
    stock_levels = (
        StockLevel(sku="FICTIF-DSP-ALPHA", on_hand=4, reserved=1, damaged=0, safety=0, version=4),
        StockLevel(sku="FICTIF-ETB-BETA", on_hand=10, reserved=2, damaged=0, safety=1, version=7),
        StockLevel(sku="FICTIF-BST-GAMMA", on_hand=24, reserved=0, damaged=0, safety=0, version=1),
        StockLevel(sku="FICTIF-TRI-ALPHA", on_hand=0, reserved=0, damaged=0, safety=0, version=2),
    )
    open_orders = (
        OpenOrder(order_ref="#FICTIF-1003", paid_at=_demo_at(w46 + timedelta(days=1))),
        OpenOrder(order_ref="#FICTIF-1004", paid_at=_demo_at(w46 + timedelta(days=2))),
        OpenOrder(order_ref="#FICTIF-1005", paid_at=_demo_at(w46 + timedelta(days=4)), lines=2),
    )
    offers = (
        SupplierOffer(
            supplier_id="fictif_grossiste_a",
            supplier_sku="FICTIF-A-TRI-01",
            source_ts=as_of - timedelta(hours=1, minutes=30),
            raw_ref="FICTIF_offres_grossiste_a.csv#2",
            price=Decimal("24.00"),
            currency="CHF",
            units_per_pack=1,
            moq=6,
            carton_qty=6,
            available_qty=60,
            availability_status=AvailabilityStatus.IN_STOCK,
        ),
        SupplierOffer(
            supplier_id="fictif_grossiste_a",
            supplier_sku="FICTIF-A-ETB-01",
            source_ts=as_of - timedelta(hours=1, minutes=30),
            raw_ref="FICTIF_offres_grossiste_a.csv#3",
        ),
        SupplierOffer(
            supplier_id="fictif_grossiste_c",
            supplier_sku="FICTIF-C-DSP-01",
            source_ts=as_of - timedelta(hours=37),
            raw_ref="FICTIF_flux_grossiste_c.xml#1",
        ),
    )
    cash = CashPosition(
        as_of=as_of - timedelta(minutes=30),
        cash_available_chf=Decimal("2650.00"),
        bank_chf=Decimal("2270.00"),
        paypal_chf=Decimal("380.00"),
    )

    # Stop-loss : photo évaluée par le moteur (seuils config/stoploss.v1.yaml).
    params = rules.pricing
    promo_chf, promo_pct = contribution(Decimal("179.90"), Decimal("140.00"), params)
    price_chf, price_pct = contribution(Decimal("199.90"), Decimal("140.00"), params)
    extensions = (
        ExtensionExposure(
            extension="FICTIF_ALPHA",
            stock_value_at_cost=display.total_value,
            first_stocked_at=_demo_at(date(2026, 10, 29)),
            last_sale_at=_demo_at(w46 + timedelta(days=1)),
        ),
        ExtensionExposure(
            extension="FICTIF_BETA",
            stock_value_at_cost=etb.total_value,
            first_stocked_at=_demo_at(date(2026, 10, 29)),
            last_sale_at=_demo_at(w46 + timedelta(days=4)),
        ),
        ExtensionExposure(
            extension="FICTIF_GAMMA",
            stock_value_at_cost=booster.total_value,
            first_stocked_at=_demo_at(date(2026, 9, 30)),
        ),
    )
    ad_spends = (AdSpend(campaign_id="FICTIF-CAMP-1", day=w46 + timedelta(days=6), amount=Decimal("35.00")),)
    attributed = (
        AttributedOrder(
            order_id="FICTIF-1004",
            campaign_id="FICTIF-CAMP-1",
            paid_at=_demo_at(w46 + timedelta(days=2)),
            contribution_before_acquisition=Decimal("22.20"),
        ),
        AttributedOrder(
            order_id="FICTIF-1005",
            campaign_id="FICTIF-CAMP-1",
            paid_at=_demo_at(w46 + timedelta(days=4)),
            contribution_before_acquisition=Decimal("22.20"),
        ),
    )
    state = StopLossState(
        as_of=as_of - timedelta(minutes=30),
        products=(
            ProductMargin(
                product_key="FICTIF_DISPLAY_ALPHA",
                extension="FICTIF_ALPHA",
                contribution_chf=price_chf,
                contribution_pct=price_pct,
            ),
            ProductMargin(
                product_key="FICTIF_DISPLAY_ALPHA",
                extension="FICTIF_ALPHA",
                contribution_chf=promo_chf,
                contribution_pct=promo_pct,
                context="PROMO",
            ),
        ),
        extensions=extensions,
        stock_budget_chf=rules.stock.stock_budget_chf,
        ad_spends=ad_spends,
        attributed_orders=attributed,
        ads_daily_cap_chf=Decimal("33"),
        cash_available_chf=cash.cash_available_chf,
        capital_movements=(
            CapitalMovement(
                movement_id="FICTIF-APPORT-1",
                at=_demo_at(date(2026, 10, 1)),
                kind="CONTRIBUTION",
                amount=Decimal("8000"),
            ),
        ),
        net_worth=NetWorthSnapshot(
            as_of=as_of - timedelta(minutes=30),
            cash_chf=cash.cash_available_chf,
            stock=tuple(StockValuationLine.from_ledger(lg) for lg in (display, etb, booster)),
            receivables=(BalanceItem(label="Versements PSP en transit (FICTIF)", amount=Decimal("180.00")),),
            debts=(BalanceItem(label="TVA due estimée (FICTIF)", amount=Decimal("25.00")),),
        ),
        validation_window=ValidationWindow(
            started_at=window_start,
            paid_orders_net=len(_net_orders(ns.entries(), window_start, as_of)),
            contribution_after_ads_chf=window.contribution_after_acquisition,
            oversells=0,
            pilot_stock_cost_chf=pilot_cost,
            sold_cost_chf=window.historical_cost,
        ),
    )
    baseline = CapitalBaseline(
        set_at=_demo_at(date(2026, 10, 1)),
        origin="POINT_ZERO",
        net_value_chf=Decimal("4200"),
        capital_total_chf=Decimal("8000"),
    )
    view = StopLossView.evaluate(state, as_of, load_stoploss_config(), baseline=baseline, autonomy_level=1)

    # Incidents tracés par le moteur (notification simulée).
    manager = IncidentManager(
        audit=InMemoryAuditLog(clock=lambda: as_of),
        notifier=_SilentNotifier(),
        clock=lambda: as_of - timedelta(hours=6),
    )
    manager.open(
        code=IncidentCode.INC_03,
        cause="Flux FICTIF du grossiste C vieux de plus de 24 h (dernier fichier : 14.11 18:30).",
        supplier_id="fictif_grossiste_c",
        workflow="01-fournisseur-site",
        actor="n8n:01-fournisseur-site",
        fictif=True,
    )
    manager.open(
        kind="IMAGE_FLOUE",
        severity=Severity.MINEUR,
        scope="REFERENCE",
        product_key="FICTIF_TRIPACK_ALPHA",
        proposed_action="Refaire la photo lors de la prochaine session (fiche non publiée entre-temps).",
        cause="Photo FICTIVE floue signalée par l'agent catalogue.",
        actor="agent-04-catalogue",
        fictif=True,
        contain=False,
    )

    # Dépense hors mandat (mandat non signé => validation humaine).
    spend_ledger = SpendLedger()
    request = SpendRequest(
        amount=Decimal("48.60"),
        currency="CHF",
        supplier_id="fictif_emballages",
        category="PACKAGING",
        payment_method="PAYPAL",
        purpose="Cartons d'expédition FICTIFS (lot de 50)",
        idempotency_key="FICTIF-DEP-0001",
        requested_by="agent-11-ops",
        requested_at=as_of - timedelta(minutes=10),
        amount_source="Devis FICTIF n° D-0001 (données d'essai)",
        fictif=True,
    )
    treasury = TreasurySnapshot(
        as_of=as_of - timedelta(minutes=30),
        cash_available_chf=cash.cash_available_chf,
        paypal_balance_chf=cash.paypal_chf,
    )
    assert view.status is not None
    decision = check(request, load_mandate(), spend_ledger, view.status, treasury, now=as_of)
    spend_ledger.record(request, decision, actor="agent-11-ops")

    # Réassort proposé (à valider) : la référence en rupture ; l'extension gelée est écartée.
    tri_offer = offers[0]
    candidates = [
        ReorderCandidate(
            product_key="FICTIF_TRIPACK_ALPHA",
            extension="FICTIF_ALPHA",
            offer=tri_offer,
            unit_cost_chf=Decimal("24.00"),
            sellable_qty=0,
            avg_daily_sales=Decimal("0.15"),
            lead_time_days=7,
            safety_stock=1,
        ),
        ReorderCandidate(
            product_key="FICTIF_BOOSTER_GAMMA",
            extension="FICTIF_GAMMA",
            offer=tri_offer.replace(supplier_sku="FICTIF-A-BST-01"),
            unit_cost_chf=Decimal("5.15"),
            sellable_qty=24,
            avg_daily_sales=Decimal("0.10"),
            lead_time_days=7,
            safety_stock=0,
        ),
    ]
    proposal = propose_reorder(
        candidates,
        budget_available=cash.cash_available_chf,
        stock_budget_total=rules.stock.stock_budget_chf,
        now=as_of - timedelta(hours=1),
        extension_exposure={e.extension: e.exposure for e in extensions},
        extension_cap_pct=rules.stock.extension_budget_cap,
        rules_version=rules.rules_version,
        blocked_extensions=view.status.no_reorder_extensions,
        blocked_products=view.status.blocked_products,
        cash_reserve_chf=Decimal("1600"),
    )

    hours = (
        (w45, "2.5"),
        (w45 + timedelta(days=2), "2.0"),
        (w45 + timedelta(days=4), "2.5"),
        (w46, "1.5"),
        (w46 + timedelta(days=1), "2.5"),
        (w46 + timedelta(days=3), "3.0"),
        (w46 + timedelta(days=5), "1.5"),
    )
    time_entries = tuple(
        TimeEntry(day=d, activity="supervision, colis et décisions (FICTIF)", hours=Decimal(h)) for d, h in hours
    )
    turnover = tuple(
        MonthlyTurnover(
            month=_shift_month("2026-11", -i),
            amount_chf=Decimal("5000.00"),
            source="autre activité de l'entité (FICTIF)",
        )
        for i in range(11, 0, -1)
    ) + (
        MonthlyTurnover(
            month="2026-11", amount_chf=Decimal("5545.60"), source="autre activité 5 000 + boutique 545,60 (FICTIF)"
        ),
    )
    tools = (
        ToolExpense(
            month="2026-11",
            tool="Boutique en ligne (abonnement) — FICTIF",
            amount_chf=Decimal("45.00"),
            ref="FICTIF-F-01",
        ),
        ToolExpense(
            month="2026-11",
            tool="Orchestrateur et hébergement — FICTIF",
            amount_chf=Decimal("25.00"),
            ref="FICTIF-F-02",
        ),
        ToolExpense(month="2026-11", tool="Outil d'emailing — FICTIF", amount_chf=Decimal("20.00"), ref="FICTIF-F-03"),
        ToolExpense(
            month="2026-11",
            tool="Nom de domaine (part mensuelle) — FICTIF",
            amount_chf=Decimal("2.00"),
            ref="FICTIF-F-04",
        ),
    )
    after_sales = (
        AfterSalesCase(
            case_id="SAV-FICTIF-01",
            opened_at=_demo_at(w46 + timedelta(days=3)),
            kind="RETOUR",
            status="CLOS",
            amount_chf=Decimal("7.00"),
        ),
        AfterSalesCase(case_id="SAV-FICTIF-02", opened_at=_demo_at(w46 + timedelta(days=4)), kind="LITIGE"),
    )
    return DashboardInputs(
        as_of=as_of,
        fictif=True,
        autonomy_level=1,
        entries=ns.entries(),
        stoploss=view,
        cash=cash,
        open_orders=open_orders,
        stock=stock,
        stock_levels=stock_levels,
        offers=offers,
        incidents=manager.list(),
        spend_entries=spend_ledger.entries(),
        reorder_proposals=(proposal,),
        sales=sales,
        extensions=extensions,
        ad_spends=ad_spends,
        attributed_orders=attributed,
        cost_variances=(variance,),
        after_sales=after_sales,
        time_entries=time_entries,
        turnover=turnover,
        tool_expenses=tools,
    )
