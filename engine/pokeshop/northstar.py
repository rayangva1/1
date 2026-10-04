"""Étoile polaire : **contribution nette cumulée** réalisée, par semaine et cumulée (gouvernance).

Métrique unique de pilotage décidée par la propriétaire (ni chiffre d'affaires, ni followers) ::

    contribution nette = ventes nettes HT
                         − coût historique des unités vendues
                         − frais de paiement − logistique − SAV − acquisition − charges fixes

Conventions :

* **Réalisé**, pas prévisionnel (la projection est dans :func:`pokeshop.forecast.north_star`).
  Chaque montant est une écriture datée, idempotente (``entry_id``), en CHF au centime.
* **Coût historique uniquement** : le poste ``HISTORICAL_COST`` n'est alimenté que par le
  journal de :class:`pokeshop.costs.HistoricalCostLedger` (sorties au CMP, retours, casse,
  écarts de facture sur unités vendues). Le coût de remplacement n'entre jamais ici ; le coût
  porté par un panier (``BasketResult.product_cost``) est ignoré.
* Montants **nets de TVA récupérable** : HT en méthode effective ; TTC si l'entité n'est pas
  assujettie (TVA non récupérable = coût), comme le moteur de prix.
* SAV et acquisition = **dépenses réelles** (port retour, geste, publicité, créateurs). Les
  provisions R et A du moteur de prix servent à fixer les prix ; les compter ici en plus des
  dépenses réelles ferait un double compte.
* Semaine = lundi-dimanche ISO, fuseau ``Europe/Zurich``. Delta = contribution nette de la
  semaine − celle de la semaine précédente (et poste par poste).
"""

from __future__ import annotations

import calendar
import threading
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator

from .costs import CostEntry, HistoricalCostLedger
from .errors import PokeshopError
from .forecast import NorthStarWeek
from .models import BasketResult, FrozenModel
from .pricing import allocate_amount, as_decimal

__all__ = [
    "COST_LEDGER_SOURCE",
    "NorthStarError",
    "Post",
    "POST_LABELS_FR",
    "ContributionEntry",
    "PostBreakdown",
    "NorthStarWeekLine",
    "NorthStarReport",
    "NorthStarLedger",
    "week_start",
    "iso_week_label",
]

COST_LEDGER_SOURCE = "HistoricalCostLedger"
"""Seule source admise pour le poste coût historique."""
ZERO = Decimal("0")
CENT = Decimal("0.01")


class NorthStarError(PokeshopError, ValueError):
    """Écriture invalide (montant hors centime, doublon contradictoire, poste interdit)."""


class Post(str, Enum):
    """Postes de la contribution nette (ordre d'affichage)."""

    NET_SALES = "NET_SALES"
    HISTORICAL_COST = "HISTORICAL_COST"
    PAYMENT = "PAYMENT"
    LOGISTICS = "LOGISTICS"
    AFTER_SALES = "AFTER_SALES"
    ACQUISITION = "ACQUISITION"
    FIXED_COSTS = "FIXED_COSTS"


POST_LABELS_FR: dict[Post, str] = {
    Post.NET_SALES: "Ventes nettes HT",
    Post.HISTORICAL_COST: "Coût historique",
    Post.PAYMENT: "Paiement",
    Post.LOGISTICS: "Logistique",
    Post.AFTER_SALES: "SAV",
    Post.ACQUISITION: "Acquisition",
    Post.FIXED_COSTS: "Charges fixes",
}

_FIELD = {
    Post.NET_SALES: "net_sales_ht",
    Post.HISTORICAL_COST: "historical_cost",
    Post.PAYMENT: "payment",
    Post.LOGISTICS: "logistics",
    Post.AFTER_SALES: "after_sales",
    Post.ACQUISITION: "acquisition",
    Post.FIXED_COSTS: "fixed_costs",
}
_EXPENSE_POSTS = frozenset({Post.PAYMENT, Post.LOGISTICS, Post.AFTER_SALES, Post.ACQUISITION, Post.FIXED_COSTS})


def _cents(value: Decimal | int | str, name: str) -> Decimal:
    """Montant au centime exact (float refusé ; plus de 2 décimales refusé : aucun centime inexpliqué)."""
    amount = as_decimal(value, name)
    if amount != amount.quantize(CENT):
        raise NorthStarError(f"{name} : {amount} n'est pas un montant au centime")
    return amount.quantize(CENT)


def week_start(day: date) -> date:
    """Lundi de la semaine ISO de ``day``."""
    return day - timedelta(days=day.weekday())


def iso_week_label(monday: date) -> str:
    """Libellé ISO ``AAAA-Wss`` (ex. ``2026-W45``)."""
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


class ContributionEntry(FrozenModel):
    """Écriture de contribution. Signe naturel : ventes > 0 (remboursement < 0), coûts > 0 (avoir < 0)."""

    entry_id: str = Field(min_length=1)
    at: datetime
    post: Post
    amount: Decimal
    ref: str = ""
    source: str = "manuel"
    order_id: str | None = None

    @field_validator("at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("at doit porter un fuseau horaire")
        return v

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v: Any) -> Decimal:
        try:
            return _cents(v, "amount")
        except (TypeError, PokeshopError) as exc:
            raise ValueError(str(exc)) from exc


class PostBreakdown(FrozenModel):
    """Décomposition par poste (CHF) et contributions intermédiaires."""

    net_sales_ht: Decimal = ZERO
    historical_cost: Decimal = ZERO
    payment: Decimal = ZERO
    logistics: Decimal = ZERO
    after_sales: Decimal = ZERO
    acquisition: Decimal = ZERO
    fixed_costs: Decimal = ZERO

    @classmethod
    def of(cls, entries: Iterable[ContributionEntry]) -> PostBreakdown:
        """Somme d'écritures par poste."""
        sums = dict.fromkeys(_FIELD.values(), ZERO)
        for e in entries:
            sums[_FIELD[e.post]] += e.amount
        return cls(**sums)

    def get(self, post: Post) -> Decimal:
        """Montant d'un poste."""
        return getattr(self, _FIELD[post])  # type: ignore[no-any-return]

    def minus(self, other: PostBreakdown) -> PostBreakdown:
        """Écart poste par poste (self − other)."""
        return PostBreakdown(**{f: getattr(self, f) - getattr(other, f) for f in _FIELD.values()})

    @property
    def contribution_before_acquisition(self) -> Decimal:
        """Ventes nettes − coût historique − paiement − logistique − SAV."""
        return self.net_sales_ht - self.historical_cost - self.payment - self.logistics - self.after_sales

    @property
    def contribution_after_acquisition(self) -> Decimal:
        """Contribution après publicité, avant charges fixes (seuil de validation BP §1)."""
        return self.contribution_before_acquisition - self.acquisition

    @property
    def net_contribution(self) -> Decimal:
        """Contribution nette (étoile polaire)."""
        return self.contribution_after_acquisition - self.fixed_costs


class NorthStarWeekLine(FrozenModel):
    """Une semaine : décomposition, contribution nette, delta vs semaine précédente, cumul."""

    week_start: date
    iso_week: str
    orders: int
    breakdown: PostBreakdown
    net_contribution: Decimal
    delta_vs_previous_week: Decimal
    delta_by_post: PostBreakdown
    cumulative: Decimal


def _chf(value: Decimal) -> str:
    q = value.quantize(CENT)
    sign = "−" if q < 0 else ""
    integer, _, cents = f"{abs(q):.2f}".partition(".")
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return f"{sign}{' '.join(groups)},{cents}"


class NorthStarReport(FrozenModel):
    """Suivi hebdomadaire de la contribution nette cumulée (revue du lundi)."""

    opening_cumulative: Decimal
    """Cumul avant la première semaine du rapport (depuis le lancement)."""
    rows: tuple[NorthStarWeekLine, ...]
    total: PostBreakdown
    """Décomposition sur les semaines du rapport."""

    @property
    def cumulative(self) -> Decimal:
        """Contribution nette cumulée depuis le lancement, à la fin de la dernière semaine."""
        return self.rows[-1].cumulative if self.rows else self.opening_cumulative

    @property
    def last(self) -> NorthStarWeekLine:
        """Dernière semaine du rapport."""
        return self.rows[-1]

    def to_forecast_weeks(self) -> tuple[NorthStarWeek, ...]:
        """Conversion vers :class:`pokeshop.forecast.NorthStarWeek` (semaines numérotées 1..n) : réel vs plan."""
        return tuple(
            NorthStarWeek(
                week=i,
                orders=Decimal(row.orders),
                net_sales_ht=row.breakdown.net_sales_ht,
                historical_cost=row.breakdown.historical_cost,
                payment_fees=row.breakdown.payment,
                logistics=row.breakdown.logistics,
                after_sales=row.breakdown.after_sales,
                acquisition=row.breakdown.acquisition,
                fixed_costs=row.breakdown.fixed_costs,
            )
            for i, row in enumerate(self.rows, start=1)
        )

    def render_markdown(self) -> str:
        """Tableau de la revue hebdomadaire (CHF), à coller dans le rapport de l'agent finance."""
        head = [POST_LABELS_FR[p] for p in Post]
        lines = [
            "| Semaine | Cmd | " + " | ".join(head) + " | Contribution nette | Δ sem. préc. | Cumul |",
            "|---|---:|" + "---:|" * (len(head) + 3),
        ]
        for r in self.rows:
            values = " | ".join(_chf(r.breakdown.get(p)) for p in Post)
            lines.append(
                f"| {r.iso_week} | {r.orders} | {values} | **{_chf(r.net_contribution)}** | "
                f"{_chf(r.delta_vs_previous_week)} | **{_chf(r.cumulative)}** |"
            )
        return "\n".join(lines) + "\n"


class NorthStarLedger:
    """Journal des écritures de contribution réalisée (append-only, idempotent, thread-safe)."""

    def __init__(self, *, timezone: str = "Europe/Zurich") -> None:
        self._tz = ZoneInfo(timezone)
        self._lock = threading.RLock()
        self._entries: dict[str, ContributionEntry] = {}

    @classmethod
    def from_entries(cls, entries: Iterable[ContributionEntry], *, timezone: str = "Europe/Zurich") -> NorthStarLedger:
        """Restaure un journal persistant (mêmes contrôles qu'à l'écriture)."""
        ledger = cls(timezone=timezone)
        for e in entries:
            ledger.record(e)
        return ledger

    # -- lecture ------------------------------------------------------------------
    def entries(self) -> tuple[ContributionEntry, ...]:
        """Écritures dans l'ordre d'enregistrement."""
        with self._lock:
            return tuple(self._entries.values())

    def _local(self, at: datetime) -> date:
        return at.astimezone(self._tz).date()

    def _monday_start(self, monday: date) -> datetime:
        return datetime.combine(monday, time(0), tzinfo=self._tz)

    def totals(self, start: datetime | None = None, end: datetime | None = None) -> PostBreakdown:
        """Décomposition sur la période ``[start, end[`` (bornes optionnelles, datetimes avec fuseau)."""
        with self._lock:
            return PostBreakdown.of(
                e
                for e in self._entries.values()
                if (start is None or e.at >= start) and (end is None or e.at < end)
            )

    # -- écriture -----------------------------------------------------------------
    def record(self, entry: ContributionEntry) -> bool:
        """Ajoute une écriture ; ``False`` si déjà présente à l'identique ; erreur si contradictoire."""
        if entry.post is Post.HISTORICAL_COST and entry.source != COST_LEDGER_SOURCE:
            raise NorthStarError("coût historique : HistoricalCostLedger uniquement (jamais le coût de remplacement)")
        with self._lock:
            existing = self._entries.get(entry.entry_id)
            if existing is not None:
                if existing == entry:
                    return False
                raise NorthStarError(f"écriture {entry.entry_id} déjà enregistrée avec un autre contenu")
            self._entries[entry.entry_id] = entry
            return True

    def _add(self, entries: Sequence[ContributionEntry]) -> tuple[ContributionEntry, ...]:
        with self._lock:
            for e in entries:  # contrôle complet avant toute écriture (atomicité)
                existing = self._entries.get(e.entry_id)
                if existing is not None and existing != e:
                    raise NorthStarError(f"écriture {e.entry_id} déjà enregistrée avec un autre contenu")
            for e in entries:
                self.record(e)
        return tuple(entries)

    def record_order(
        self,
        order_id: str,
        at: datetime,
        *,
        net_sales_ht: Decimal | int | str,
        payment_fees: Decimal | int | str,
        logistics: Decimal | int | str = ZERO,
        after_sales: Decimal | int | str = ZERO,
    ) -> tuple[ContributionEntry, ...]:
        """Commande payée : ventes nettes HT (port facturé HT inclus, remises déduites), frais réels.

        Le coût des unités vient du coût historique (:meth:`sync_cost_ledger`), pas d'ici.
        """
        sales = _cents(net_sales_ht, "net_sales_ht")
        if sales <= 0:
            raise NorthStarError("ventes nettes d'une commande ≤ 0")
        items = [(Post.NET_SALES, sales), (Post.PAYMENT, _cents(payment_fees, "payment_fees"))]
        items.append((Post.LOGISTICS, _cents(logistics, "logistics")))
        items.append((Post.AFTER_SALES, _cents(after_sales, "after_sales")))
        entries = [
            ContributionEntry(
                entry_id=f"order:{order_id}:{post.value}", at=at, post=post, amount=amount, ref=order_id,
                source="commande", order_id=order_id,
            )
            for post, amount in items
            if amount != 0 or post is Post.NET_SALES
        ]  # fmt: skip
        return self._add(entries)

    def record_basket(self, order_id: str, at: datetime, basket: BasketResult) -> tuple[ContributionEntry, ...]:
        """Commande à partir d'un :class:`~pokeshop.models.BasketResult` du moteur de prix.

        Repris : CA net (produits + port HT − remise), frais de paiement, logistique. Ignorés :
        ``product_cost`` (le coût vient du coût historique), provisions SAV et acquisition
        (remplacées par les dépenses réelles).
        """
        return self.record_order(
            order_id,
            at,
            net_sales_ht=basket.net_revenue,
            payment_fees=basket.payment_fees,
            logistics=basket.logistics_cost,
        )

    def record_refund(
        self,
        refund_id: str,
        at: datetime,
        *,
        net_sales_ht: Decimal | int | str,
        payment_fees_refunded: Decimal | int | str = ZERO,
        order_id: str | None = None,
    ) -> tuple[ContributionEntry, ...]:
        """Remboursement : ventes nettes négatives (frais PSP remboursés seulement s'ils le sont réellement).

        Le retour des unités en stock passe par ``HistoricalCostLedger.return_units`` puis
        :meth:`sync_cost_ledger` ; port retour et geste commercial : :meth:`record_expense` (SAV).
        """
        sales = _cents(net_sales_ht, "net_sales_ht")
        fees = _cents(payment_fees_refunded, "payment_fees_refunded")
        if sales <= 0 or fees < 0:
            raise NorthStarError("remboursement : montant > 0 attendu (frais remboursés ≥ 0)")
        entries = [
            ContributionEntry(
                entry_id=f"refund:{refund_id}:NET_SALES", at=at, post=Post.NET_SALES, amount=-sales,
                ref=refund_id, source="remboursement", order_id=order_id,
            )
        ]  # fmt: skip
        if fees:
            entries.append(
                ContributionEntry(
                    entry_id=f"refund:{refund_id}:PAYMENT", at=at, post=Post.PAYMENT, amount=-fees,
                    ref=refund_id, source="remboursement", order_id=order_id,
                )
            )  # fmt: skip
        return self._add(entries)

    def record_expense(
        self, expense_id: str, at: datetime, post: Post, amount: Decimal | int | str, *, ref: str = ""
    ) -> ContributionEntry:
        """Dépense réelle : paiement (abonnement PSP), logistique, SAV, acquisition (pub, créateur), charges fixes."""
        if post not in _EXPENSE_POSTS:
            raise NorthStarError(f"poste {post.value} interdit en dépense (ventes : record_order ; coût : sync)")
        entry = ContributionEntry(
            entry_id=f"expense:{expense_id}",
            at=at,
            post=post,
            amount=_cents(amount, "amount"),
            ref=ref,
            source="depense",
        )
        self._add([entry])
        return entry

    def record_cost_entry(self, product_key: str, entry: CostEntry) -> ContributionEntry | None:
        """Convertit une écriture de coût historique en coût des ventes (None si sans effet sur la contribution).

        ISSUE : + coût des ventes ; RETURN : − coût (retour en stock) ; WRITE_OFF : + perte (casse) ;
        INVOICE_ADJUSTMENT : + part de l'écart de facture portée sur les unités déjà vendues ;
        RECEIPT : aucun effet (le stock n'est pas un coût tant qu'il n'est pas vendu ou détruit).
        """
        if entry.kind == "RECEIPT":
            return None
        amount = -entry.amount if entry.kind == "WRITE_OFF" else entry.cogs
        if amount == 0:
            return None
        converted = ContributionEntry(
            entry_id=f"cost:{product_key}:{entry.seq}",
            at=entry.at,
            post=Post.HISTORICAL_COST,
            amount=amount,
            ref=f"{entry.kind} {entry.ref}".strip(),
            source=COST_LEDGER_SOURCE,
        )
        self._add([converted])
        return converted

    def sync_cost_ledger(self, ledger: HistoricalCostLedger) -> int:
        """Importe le journal d'un :class:`HistoricalCostLedger` ; renvoie le nombre de nouvelles écritures."""
        before = len(self._entries)
        for entry in ledger.journal():
            self.record_cost_entry(ledger.product_key, entry)
        return len(self._entries) - before

    def accrue_fixed_costs(
        self, monthly_amount: Decimal | int | str, year: int, month: int, *, label: str = "charges_fixes"
    ) -> tuple[ContributionEntry, ...]:
        """Charges fixes d'un mois réparties au jour (somme exacte), regroupées par semaine ISO."""
        total = _cents(monthly_amount, "monthly_amount")
        if total < 0:
            raise NorthStarError("charges fixes négatives")
        n_days = calendar.monthrange(year, month)[1]
        per_day = allocate_amount(total, [Decimal(1)] * n_days)
        segments: dict[date, Decimal] = {}
        first_day: dict[date, date] = {}
        for i, amount in enumerate(per_day):
            day = date(year, month, i + 1)
            monday = week_start(day)
            segments[monday] = segments.get(monday, ZERO) + amount
            first_day.setdefault(monday, day)
        entries = [
            ContributionEntry(
                entry_id=f"fixed:{label}:{year:04d}-{month:02d}:{first_day[monday].isoformat()}",
                at=datetime.combine(first_day[monday], time(12), tzinfo=self._tz),
                post=Post.FIXED_COSTS,
                amount=amount,
                ref=f"{label} {year:04d}-{month:02d}",
                source="charges_fixes",
            )
            for monday, amount in segments.items()
        ]
        return self._add(entries)

    # -- rapport ------------------------------------------------------------------
    def weekly_report(self, start: date | None = None, end: date | None = None) -> NorthStarReport:
        """Semaines ISO de ``start`` à ``end`` (incluses ; défaut : première et dernière écriture)."""
        with self._lock:
            entries = list(self._entries.values())
        if start is None or end is None:
            if not entries:
                raise NorthStarError("aucune écriture : préciser start et end")
            days = [self._local(e.at) for e in entries]
            start = start or min(days)
            end = end or max(days)
        first, last = week_start(start), week_start(end)
        if last < first:
            raise NorthStarError("end antérieur à start")
        by_week: dict[date, list[ContributionEntry]] = {}
        opening: list[ContributionEntry] = []
        for e in entries:
            monday = week_start(self._local(e.at))
            if monday < first:
                opening.append(e)
            by_week.setdefault(monday, []).append(e)
        previous = PostBreakdown.of(by_week.get(first - timedelta(days=7), []))
        cumulative = PostBreakdown.of(opening).net_contribution
        opening_cumulative = cumulative
        rows: list[NorthStarWeekLine] = []
        selected: list[ContributionEntry] = []
        monday = first
        while monday <= last:
            week_entries = by_week.get(monday, [])
            selected.extend(week_entries)
            current = PostBreakdown.of(week_entries)
            cumulative += current.net_contribution
            orders = {e.order_id for e in week_entries if e.post is Post.NET_SALES and e.amount > 0 and e.order_id}
            rows.append(
                NorthStarWeekLine(
                    week_start=monday,
                    iso_week=iso_week_label(monday),
                    orders=len(orders),
                    breakdown=current,
                    net_contribution=current.net_contribution,
                    delta_vs_previous_week=current.net_contribution - previous.net_contribution,
                    delta_by_post=current.minus(previous),
                    cumulative=cumulative,
                )
            )
            previous = current
            monday += timedelta(days=7)
        return NorthStarReport(
            opening_cumulative=opening_cumulative, rows=tuple(rows), total=PostBreakdown.of(selected)
        )
