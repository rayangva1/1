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
  écarts de facture sur unités vendues), **côté moteur** (:meth:`NorthStarLedger.sync_cost_ledger`,
  :class:`CostRegister`). L'étiquette de source n'est pas déclarable : :meth:`NorthStarLedger.record`
  et :meth:`NorthStarLedger.add_entries` (écritures externes, API) refusent tout ``HISTORICAL_COST``
  et toute source ``HistoricalCostLedger``. Le coût de remplacement n'entre jamais ici ; le coût
  porté par un panier (``BasketResult.product_cost``) est ignoré.
* Montants **nets de TVA récupérable** : HT en méthode effective ; TTC si l'entité n'est pas
  assujettie (TVA non récupérable = coût), comme le moteur de prix.
* SAV et acquisition = **dépenses réelles** (port retour, geste, publicité, créateurs). Les
  provisions R et A du moteur de prix servent à fixer les prix ; les compter ici en plus des
  dépenses réelles ferait un double compte.
* Semaine = lundi-dimanche ISO, fuseau ``Europe/Zurich``. Delta = contribution nette de la
  semaine − celle de la semaine précédente (et poste par poste).
* **Aucune valeur décisive déclarée** (revue R3, R2-NEW-04 et MOT-18) : les **ventes et avoirs** ne
  viennent que de commandes enregistrées par le moteur (:class:`OrderRegister`, ``POST /orders/shipped``
  et ``POST /orders/{id}/refunds``) avec le **coût réel du transporteur** (logistique supposée refusée
  sur ce chemin réel) ; une écriture déclarée par un rôle (``POST /northstar/entries``) n'est qu'un coût
  **positif** (paiement, SAV, acquisition, charges fixes) ; seule la propriétaire écrit manuellement les
  autres postes, et un montant négatif doit annuler (en tout ou partie) une écriture positive existante
  du même poste (``ref`` = son ``entry_id``).
"""

from __future__ import annotations

import calendar
import threading
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, ValidationError, field_validator

from .audit import StateJournal, StateStoreError
from .costs import CostEntry, HistoricalCostLedger
from .errors import CostError
from .models import CostLot
from .errors import PokeshopError
from .forecast import NorthStarWeek
from .models import BasketResult, FrozenModel
from .pricing import allocate_amount, as_decimal

__all__ = [
    "COST_LEDGER_SOURCE",
    "ROLE_POSTS",
    "OrderRegister",
    "ShippedOrder",
    "OrderRefund",
    "require_actual_logistics",
    "CostRegister",
    "CostMovement",
    "NorthStarError",
    "NorthStarPersistenceError",
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


class NorthStarPersistenceError(NorthStarError, StateStoreError):
    """Journal de l'étoile polaire non enregistré ou non relu : écriture refusée (fermé par défaut)."""


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
ROLE_POSTS: frozenset[Post] = frozenset({Post.PAYMENT, Post.AFTER_SALES, Post.ACQUISITION, Post.FIXED_COSTS})
"""Postes qu'un rôle nommé peut déclarer (``POST /northstar/entries``), en montant **positif** seulement :
ventes et logistique viennent des commandes enregistrées (``POST /orders/shipped``)."""


def require_actual_logistics(order_id: str, shipping_cost_actual: Any, label_ref: str | None) -> Decimal:
    """Coût logistique **réel** d'une commande (revue MOT-18), sur tout chemin qui inscrit une vente.

    Refuse un coût absent, nul ou négatif (hypothèse L du BP, port offert sans coût) et une commande sans
    référence d'étiquette achetée : l'étoile polaire n'enregistre jamais une hypothèse comme une dépense.
    """
    if shipping_cost_actual is None:
        raise NorthStarError(
            f"commande {order_id} : coût réel du transporteur (shipping_cost_actual) obligatoire — "
            "une logistique supposée n'est jamais inscrite comme réalisée"
        )
    amount = _cents(shipping_cost_actual, "shipping_cost_actual")
    if amount <= 0:
        raise NorthStarError(f"commande {order_id} : coût transporteur réel > 0 attendu (étiquette achetée)")
    if label_ref is not None and len(label_ref.strip()) < 3:
        raise NorthStarError(f"commande {order_id} : référence de l'étiquette achetée obligatoire")
    return amount


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
    """Journal des écritures de contribution réalisée (append-only, idempotent, thread-safe).

    ``store`` (journal d'état ``northstar``) reçoit chaque lot de nouvelles écritures **avant**
    qu'elles ne comptent : la contribution nette cumulée survit au redémarrage (:meth:`restore`).
    """

    STREAM = "northstar"

    def __init__(self, *, timezone: str = "Europe/Zurich", store: StateJournal | None = None) -> None:
        self._tz = ZoneInfo(timezone)
        self._lock = threading.RLock()
        self._entries: dict[str, ContributionEntry] = {}
        self._store = store

    @classmethod
    def from_entries(cls, entries: Iterable[ContributionEntry], *, timezone: str = "Europe/Zurich") -> NorthStarLedger:
        """Restaure un journal persistant (écritures déjà acceptées, coût historique interne compris)."""
        ledger = cls(timezone=timezone)
        for e in entries:
            ledger._add([e], internal=True)
        return ledger

    @classmethod
    def restore(cls, store: StateJournal, *, timezone: str = "Europe/Zurich") -> NorthStarLedger:
        """Relit le journal d'état ; :class:`NorthStarPersistenceError` s'il est illisible ou contradictoire."""
        try:
            records = store.load()
        except StateStoreError as exc:
            raise NorthStarPersistenceError(str(exc)) from exc
        entries: list[ContributionEntry] = []
        for n, record in enumerate(records, start=1):
            try:
                entries.extend(ContributionEntry.model_validate(item) for item in record["entries"])
            except (KeyError, TypeError, ValidationError) as exc:
                raise NorthStarPersistenceError(f"étoile polaire : enregistrement {n} illisible") from exc
        try:
            ledger = cls.from_entries(entries, timezone=timezone)
        except NorthStarError as exc:
            raise NorthStarPersistenceError(f"étoile polaire : journal incohérent ({exc})") from exc
        ledger._store = store
        return ledger

    def _persist(self, entries: Sequence[ContributionEntry]) -> None:
        if self._store is None or not entries:
            return
        try:
            self._store.append({"entries": [e.model_dump(mode="json") for e in entries]})
        except StateStoreError as exc:
            raise NorthStarPersistenceError(f"étoile polaire : écriture non enregistrée ({exc})") from exc

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
    @staticmethod
    def _check_external(entry: ContributionEntry) -> None:
        """Écriture externe : le coût historique et son étiquette de source sont réservés au moteur."""
        if entry.post is Post.HISTORICAL_COST or entry.source == COST_LEDGER_SOURCE:
            raise NorthStarError(
                "coût historique : alimenté uniquement par le registre de coûts historiques interne du moteur "
                "(HistoricalCostLedger, POST /costs/movements), jamais par une écriture déclarée"
            )

    def record(self, entry: ContributionEntry, *, owner: bool = False) -> bool:
        """Ajoute une écriture externe ; ``False`` si déjà présente à l'identique ; erreur si contradictoire."""
        return bool(self.add_entries([entry], owner=owner))

    def add_entries(self, entries: Sequence[ContributionEntry], *, owner: bool = False) -> tuple[ContributionEntry, ...]:
        """Lot d'écritures externes, **atomique** (tout est contrôlé avant le moindre enregistrement).

        ``owner=False`` (rôle nommé) : seulement des coûts **positifs** des postes :data:`ROLE_POSTS`.
        ``owner=True`` (jeton propriétaire vérifié) : écriture manuelle de tout poste sauf le coût
        historique ; un montant négatif annule une écriture positive existante du même poste (``ref`` =
        son ``entry_id``, cumul des annulations ≤ montant d'origine) ; une vente positive exige un
        ``order_id`` et une logistique réelle (> 0) de la même commande (revue MOT-18).
        Renvoie les écritures nouvelles (les doublons identiques sont ignorés, idempotence par ``entry_id``).
        """
        for e in entries:
            self._check_external(e)
        with self._lock:
            fresh = [e for e in entries if self._entries.get(e.entry_id) != e]
            if owner:
                self._check_owner_batch(fresh)
            else:
                for e in fresh:
                    if e.post not in ROLE_POSTS or e.amount <= 0:
                        raise NorthStarError(
                            f"écriture {e.entry_id} : un rôle ne déclare que des coûts positifs "
                            f"({', '.join(sorted(p.value for p in ROLE_POSTS))}) ; ventes et avoirs : commandes "
                            "enregistrées (POST /orders/shipped, /orders/{id}/refunds) ; écriture manuelle : propriétaire"
                        )
            return self._add(entries)

    def _check_owner_batch(self, fresh: Sequence[ContributionEntry]) -> None:
        """Écriture manuelle de la propriétaire : aucune valeur négative arbitraire, aucune vente sans logistique réelle."""
        pool = {**self._entries, **{e.entry_id: e for e in fresh}}
        cancelled: dict[str, Decimal] = {}
        for e in pool.values():
            if e.amount < 0 and e.ref in pool:
                cancelled[e.ref] = cancelled.get(e.ref, ZERO) + (-e.amount)
        for e in fresh:
            if e.amount < 0:
                target = pool.get(e.ref)
                if target is None or target.post is not e.post or target.amount <= 0:
                    raise NorthStarError(
                        f"écriture {e.entry_id} : montant négatif sans écriture positive existante du même poste "
                        "(ref = entry_id de l'écriture annulée)"
                    )
                if cancelled.get(e.ref, ZERO) > target.amount:
                    raise NorthStarError(f"écriture {e.entry_id} : annulations > montant de {e.ref} ({target.amount})")
            elif e.post is Post.NET_SALES and e.amount > 0:
                if not e.order_id:
                    raise NorthStarError(f"vente {e.entry_id} : order_id obligatoire (commande réelle)")
                if not any(o.post is Post.LOGISTICS and o.order_id == e.order_id and o.amount > 0 for o in pool.values()):
                    raise NorthStarError(
                        f"vente {e.entry_id} : logistique réelle de la commande {e.order_id} absente — une logistique "
                        "supposée n'est jamais inscrite comme réalisée (écriture LOGISTICS > 0 de la même commande)"
                    )

    def _add(self, entries: Sequence[ContributionEntry], *, internal: bool = False) -> tuple[ContributionEntry, ...]:
        with self._lock:
            fresh: dict[str, ContributionEntry] = {}
            for e in entries:  # contrôle complet avant toute écriture (atomicité)
                if e.post is Post.HISTORICAL_COST and e.source != COST_LEDGER_SOURCE:
                    raise NorthStarError(
                        "coût historique : HistoricalCostLedger uniquement (jamais le coût de remplacement)"
                    )
                if not internal:
                    self._check_external(e)
                existing = self._entries.get(e.entry_id) or fresh.get(e.entry_id)
                if existing is not None and existing != e:
                    raise NorthStarError(f"écriture {e.entry_id} déjà enregistrée avec un autre contenu")
                if existing is None:
                    fresh[e.entry_id] = e
            self._persist(list(fresh.values()))  # un seul enregistrement pour le lot (tout ou rien)
            self._entries.update(fresh)
        return tuple(fresh.values())

    def record_order(
        self,
        order_id: str,
        at: datetime,
        *,
        net_sales_ht: Decimal | int | str,
        payment_fees: Decimal | int | str,
        logistics: Decimal | int | str | None,
        after_sales: Decimal | int | str = ZERO,
        label_ref: str | None = None,
    ) -> tuple[ContributionEntry, ...]:
        """Commande payée et expédiée : ventes nettes HT (port facturé HT inclus, remises déduites), frais réels.

        ``logistics`` : coût **réel** du transporteur, obligatoire et > 0 (:func:`require_actual_logistics`).
        Le coût des unités vient du coût historique (:meth:`sync_cost_ledger`), pas d'ici.
        """
        sales = _cents(net_sales_ht, "net_sales_ht")
        if sales <= 0:
            raise NorthStarError("ventes nettes d'une commande ≤ 0")
        fees = _cents(payment_fees, "payment_fees")
        if fees < 0:
            raise NorthStarError("frais de paiement négatifs")
        items = [(Post.NET_SALES, sales), (Post.PAYMENT, fees)]
        items.append((Post.LOGISTICS, require_actual_logistics(order_id, logistics, label_ref)))
        items.append((Post.AFTER_SALES, _cents(after_sales, "after_sales")))
        entries = [
            ContributionEntry(
                entry_id=f"order:{order_id}:{post.value}", at=at, post=post, amount=amount, ref=order_id,
                source="commande", order_id=order_id,
            )
            for post, amount in items
            if amount != 0 or post is Post.NET_SALES
        ]  # fmt: skip
        self._add(entries)
        return tuple(entries)

    def record_basket(self, order_id: str, at: datetime, basket: BasketResult) -> tuple[ContributionEntry, ...]:
        """Commande à partir d'un :class:`~pokeshop.models.BasketResult` du moteur de prix.

        Repris : CA net (produits + port HT − remise), frais de paiement, logistique. Ignorés :
        ``product_cost`` (le coût vient du coût historique), provisions SAV et acquisition
        (remplacées par les dépenses réelles).

        Logistique **réelle** obligatoire (revue MOT-18) : un panier calculé sans coût logistique réel
        (motifs ``SHIPPING_COST_ASSUMED`` ou ``SHIPPING_COST_UNKNOWN`` : hypothèse L du BP, ou port
        offert sans coût) est refusé — l'étoile polaire n'enregistre jamais une hypothèse comme une
        dépense réalisée. Recalculer le panier avec ``shipping_cost_actual``.
        """
        assumed = sorted(
            r.value if hasattr(r, "value") else str(r)
            for r in basket.reasons
            if (r.value if hasattr(r, "value") else str(r)) in ("SHIPPING_COST_ASSUMED", "SHIPPING_COST_UNKNOWN")
        )
        if assumed:
            raise NorthStarError(
                f"commande {order_id} : coût logistique non réel ({', '.join(assumed)}) — recalculer le panier avec "
                "shipping_cost_actual (coût réel du transporteur) avant de l'inscrire dans l'étoile polaire"
            )
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
        self._add(entries)
        return tuple(entries)

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
        self._add([converted], internal=True)
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
        self._add(entries)
        return tuple(entries)

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


# ------------------------------------------------------------- registre de coûts interne


class CostMovement(FrozenModel):
    """Mouvement du registre de coûts historiques (réception, vente, retour, casse, facture).

    Aucun coût n'est déclaré pour une sortie : vente et casse sortent au CMP calculé par
    :class:`pokeshop.costs.HistoricalCostLedger` ; un retour reprend le coût **de la vente d'origine**
    (``sale_ref``), jamais un coût fourni par l'appelant.
    """

    kind: Literal["RECEIPT", "ISSUE", "RETURN", "WRITE_OFF", "INVOICE_ADJUSTMENT"]
    product_key: str = Field(min_length=1)
    at: datetime
    ref: str = Field(min_length=1)
    """RECEIPT : identifiant du lot ; ISSUE : commande ; RETURN : retour ; WRITE_OFF : constat ; facture."""
    qty: int | None = Field(default=None, ge=1)
    unit_cost: Decimal | None = Field(default=None, gt=0)
    """RECEIPT : coût rendu unitaire du lot ; INVOICE_ADJUSTMENT : coût unitaire facturé."""
    lot_id: str | None = None
    """INVOICE_ADJUSTMENT : lot rapproché."""
    sale_ref: str | None = None
    """RETURN : référence de la sortie (ISSUE) d'origine."""
    stock_ref: str | None = None
    """RECEIPT : référence de la réception physique (``POST /stock/receive``) qui adosse le lot (revue R3)."""
    invoice_ref: str | None = None
    """RECEIPT / INVOICE_ADJUSTMENT : référence de la facture fournisseur (revue R3)."""
    recorded_by: str = Field(default="moteur", min_length=2)

    @field_validator("at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("at doit porter un fuseau horaire")
        return v


class CostRegister:
    """Registre **interne** des coûts historiques (journal d'état ``cost_ledger``) qui alimente l'étoile polaire.

    Chaque mouvement est rejoué à blanc (contrôle), écrit dans le journal, appliqué, puis le journal
    du :class:`HistoricalCostLedger` est synchronisé dans :class:`NorthStarLedger`
    (:meth:`NorthStarLedger.sync_cost_ledger`) : c'est la **seule** voie du poste coût historique.
    """

    STREAM = "cost_ledger"

    def __init__(self, northstar: NorthStarLedger | None = None, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._movements: list[CostMovement] = []
        self._ledgers: dict[str, HistoricalCostLedger] = {}
        self._returned: dict[tuple[str, str], int] = {}
        self._northstar = northstar
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal, northstar: NorthStarLedger | None = None) -> CostRegister:
        """Relit et rejoue le journal ; :class:`NorthStarPersistenceError` s'il est illisible ou incohérent."""
        try:
            records = store.load()
        except StateStoreError as exc:
            raise NorthStarPersistenceError(str(exc)) from exc
        register = cls(northstar)
        for n, record in enumerate(records, start=1):
            try:
                movement = CostMovement.model_validate(record["movement"])
                register._apply(register._ledgers, register._returned, movement)
            except (KeyError, TypeError, ValidationError, CostError, NorthStarError) as exc:
                raise NorthStarPersistenceError(f"registre de coûts : enregistrement {n} illisible ({exc})") from exc
            register._movements.append(movement)
        register._store = store
        return register

    @staticmethod
    def _apply(
        ledgers: dict[str, HistoricalCostLedger], returned: dict[tuple[str, str], int], movement: CostMovement
    ) -> None:
        ledger = ledgers.get(movement.product_key)
        if ledger is None:
            ledger = ledgers[movement.product_key] = HistoricalCostLedger(movement.product_key)
        kind = movement.kind
        if kind == "RECEIPT":
            if movement.qty is None or movement.unit_cost is None:
                raise NorthStarError("réception : qty et unit_cost obligatoires")
            ledger.receive(
                CostLot(
                    lot_id=movement.ref,
                    product_key=movement.product_key,
                    received_at=movement.at,
                    qty=movement.qty,
                    unit_cost=movement.unit_cost,
                )
            )
        elif kind in ("ISSUE", "WRITE_OFF"):
            if movement.qty is None or movement.unit_cost is not None:
                raise NorthStarError("sortie : qty obligatoire, coût calculé par le moteur (CMP)")
            (ledger.issue if kind == "ISSUE" else ledger.write_off)(movement.qty, movement.ref, movement.at)
        elif kind == "RETURN":
            if movement.qty is None or movement.sale_ref is None or movement.unit_cost is not None:
                raise NorthStarError("retour : qty et sale_ref obligatoires, coût repris de la vente d'origine")
            issues = [e for e in ledger.journal() if e.kind == "ISSUE" and e.ref == movement.sale_ref]
            if not issues:
                raise NorthStarError(f"retour : vente {movement.sale_ref} inconnue du registre de coûts")
            sold = sum(e.qty for e in issues)
            key = (movement.product_key, movement.sale_ref)
            already = returned.get(key, 0)
            if already + movement.qty > sold:
                raise NorthStarError(f"retour : {already + movement.qty} unités > {sold} vendues sur {movement.sale_ref}")
            unit = sum((e.cogs for e in issues), ZERO) / Decimal(sold)
            ledger.return_units(movement.qty, unit, movement.ref, movement.at)
            returned[key] = already + movement.qty
        else:  # INVOICE_ADJUSTMENT
            if movement.lot_id is None or movement.unit_cost is None:
                raise NorthStarError("facture : lot_id et unit_cost obligatoires")
            ledger.apply_invoice(movement.lot_id, movement.unit_cost, movement.ref, movement.at)

    def apply(self, movement: CostMovement) -> int:
        """Contrôle, enregistre puis applique un mouvement ; renvoie le nombre d'écritures ajoutées à l'étoile polaire."""
        with self._lock:
            trial: dict[str, HistoricalCostLedger] = {}
            trial_returned: dict[tuple[str, str], int] = {}
            for m in self._movements:
                if m.product_key == movement.product_key:
                    self._apply(trial, trial_returned, m)
            self._apply(trial, trial_returned, movement)  # contrôle à blanc : erreur => rien n'est écrit
            if self._store is not None:
                try:
                    self._store.append({"movement": movement.model_dump(mode="json")})
                except StateStoreError as exc:
                    raise NorthStarPersistenceError(f"registre de coûts : mouvement non enregistré ({exc})") from exc
            self._ledgers[movement.product_key] = trial[movement.product_key]
            self._returned.update(trial_returned)
            self._movements.append(movement)
            return self.sync(movement.product_key)

    def sync(self, product_key: str | None = None) -> int:
        """Synchronise le coût des ventes dans l'étoile polaire (idempotent) ; renvoie les nouvelles écritures."""
        if self._northstar is None:
            return 0
        keys = [product_key] if product_key is not None else sorted(self._ledgers)
        return sum(self._northstar.sync_cost_ledger(self._ledgers[k]) for k in keys if k in self._ledgers)

    def ledger(self, product_key: str) -> HistoricalCostLedger | None:
        """Coût historique d'une référence (lecture)."""
        with self._lock:
            return self._ledgers.get(product_key)

    def movements(self) -> tuple[CostMovement, ...]:
        """Mouvements dans l'ordre d'enregistrement."""
        with self._lock:
            return tuple(self._movements)

    def posters(self) -> frozenset[str]:
        """Déposants (déduits du jeton) des mouvements : contrôle « déposant ≠ demandeur » du mandat."""
        with self._lock:
            return frozenset(m.recorded_by for m in self._movements)

    def receipt_unit_cost(self, product_key: str, lot_id: str) -> Decimal | None:
        """Coût unitaire **à la réception** d'un lot (référence des écarts de facture), None si inconnu."""
        with self._lock:
            for m in self._movements:
                if m.kind == "RECEIPT" and m.product_key == product_key and m.ref == lot_id:
                    return m.unit_cost
        return None


# ------------------------------------------------------------------- commandes enregistrées


class ShippedOrder(FrozenModel):
    """Commande payée et expédiée, enregistrée par le moteur (seule source des ventes de l'étoile polaire)."""

    order_id: str = Field(min_length=1, max_length=120)
    paid_at: datetime
    net_sales_ht: Decimal = Field(gt=0)
    payment_fees: Decimal = Field(ge=0)
    shipping_cost_actual: Decimal = Field(gt=0)
    """Coût réel du transporteur (étiquette achetée), jamais l'hypothèse L du BP."""
    shipping_label_ref: str = Field(min_length=3, max_length=120)
    source: str = Field(min_length=3, max_length=200)
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("paid_at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("horodatage avec fuseau horaire obligatoire")
        return v

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence (hors acteur et date d'enregistrement)."""
        return self.model_dump(mode="json", exclude={"recorded_by", "recorded_at"})


class OrderRefund(FrozenModel):
    """Avoir (remboursement) sur une commande enregistrée."""

    refund_id: str = Field(min_length=1, max_length=120)
    order_id: str = Field(min_length=1, max_length=120)
    at: datetime
    net_sales_ht: Decimal = Field(gt=0)
    payment_fees_refunded: Decimal = Field(default=ZERO, ge=0)
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("horodatage avec fuseau horaire obligatoire")
        return v

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence."""
        return self.model_dump(mode="json", exclude={"recorded_by", "recorded_at"})


class OrderRegister:
    """Commandes expédiées et avoirs enregistrés (journal ``orders``, ajout seul) ; ventes et avoirs dérivés.

    Les écritures de l'étoile polaire (``order:<id>:<poste>``, ``refund:<id>:<poste>``) sont **dérivées**
    d'ici par le moteur (idempotentes, rattrapées au démarrage par :meth:`sync`). Une commande attribuée à une
    campagne publicitaire doit être connue ici (``POST /ads/activity``).
    """

    STREAM = "orders"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, ShippedOrder] = {}
        self._refunds: dict[str, OrderRefund] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> OrderRegister:
        """Relit le registre (:class:`NorthStarPersistenceError` s'il est illisible)."""
        try:
            records = store.load()
        except StateStoreError as exc:
            raise NorthStarPersistenceError(f"commandes : {exc}") from exc
        register = cls()
        for n, record in enumerate(records, start=1):
            try:
                if "order" in record:
                    order = ShippedOrder.model_validate(record["order"])
                    register._orders[order.order_id] = order
                else:
                    refund = OrderRefund.model_validate(record["refund"])
                    register._refunds[refund.refund_id] = refund
            except (KeyError, TypeError, ValidationError) as exc:
                raise NorthStarPersistenceError(f"commandes : enregistrement {n} illisible") from exc
        register._store = store
        return register

    def _append(self, record: dict[str, Any]) -> None:
        if self._store is None:
            return
        try:
            self._store.append(record)
        except StateStoreError as exc:
            raise NorthStarPersistenceError(f"commande non enregistrée ({exc})") from exc

    def record_shipped(self, order: ShippedOrder, northstar: NorthStarLedger | None) -> tuple[ShippedOrder, bool]:
        """Enregistre une commande expédiée puis dérive ses écritures ; (commande, nouvelle ?)."""
        require_actual_logistics(order.order_id, order.shipping_cost_actual, order.shipping_label_ref)
        for value, name in ((order.net_sales_ht, "net_sales_ht"), (order.payment_fees, "payment_fees")):
            _cents(value, name)
        with self._lock:
            current = self._orders.get(order.order_id)
            if current is not None:
                if current.content() != order.content():
                    raise NorthStarError(f"commande {order.order_id} déjà enregistrée avec un autre contenu")
                return current, False
            self._append({"order": order.model_dump(mode="json")})
            self._orders[order.order_id] = order
        self._derive_order(order, northstar)
        return order, True

    def record_refund(self, refund: OrderRefund, northstar: NorthStarLedger | None) -> tuple[OrderRefund, bool]:
        """Enregistre un avoir sur une commande connue (cumul ≤ ventes de la commande) ; (avoir, nouveau ?)."""
        _cents(refund.net_sales_ht, "net_sales_ht")
        _cents(refund.payment_fees_refunded, "payment_fees_refunded")
        with self._lock:
            order = self._orders.get(refund.order_id)
            if order is None:
                raise NorthStarError(f"avoir {refund.refund_id} : commande {refund.order_id} inconnue du moteur")
            current = self._refunds.get(refund.refund_id)
            if current is not None:
                if current.content() != refund.content():
                    raise NorthStarError(f"avoir {refund.refund_id} déjà enregistré avec un autre contenu")
                return current, False
            already = self.refunded(refund.order_id)
            if already + refund.net_sales_ht > order.net_sales_ht:
                raise NorthStarError(
                    f"avoir {refund.refund_id} : cumul {already + refund.net_sales_ht} > ventes {order.net_sales_ht}"
                )
            fees = sum((r.payment_fees_refunded for r in self._refunds.values() if r.order_id == refund.order_id), ZERO)
            if fees + refund.payment_fees_refunded > order.payment_fees:
                raise NorthStarError(f"avoir {refund.refund_id} : frais remboursés > frais de la commande")
            self._append({"refund": refund.model_dump(mode="json")})
            self._refunds[refund.refund_id] = refund
        self._derive_refund(refund, northstar)
        return refund, True

    @staticmethod
    def _derive_order(order: ShippedOrder, northstar: NorthStarLedger | None) -> None:
        if northstar is not None:
            northstar.record_order(
                order.order_id,
                order.paid_at,
                net_sales_ht=order.net_sales_ht,
                payment_fees=order.payment_fees,
                logistics=order.shipping_cost_actual,
                label_ref=order.shipping_label_ref,
            )

    @staticmethod
    def _derive_refund(refund: OrderRefund, northstar: NorthStarLedger | None) -> None:
        if northstar is not None:
            northstar.record_refund(
                refund.refund_id,
                refund.at,
                net_sales_ht=refund.net_sales_ht,
                payment_fees_refunded=refund.payment_fees_refunded,
                order_id=refund.order_id,
            )

    def sync(self, northstar: NorthStarLedger) -> None:
        """Rattrape les écritures dérivées absentes de l'étoile polaire (idempotent)."""
        with self._lock:
            orders = list(self._orders.values())
            refunds = list(self._refunds.values())
        for order in orders:
            self._derive_order(order, northstar)
        for refund in refunds:
            self._derive_refund(refund, northstar)

    def get(self, order_id: str) -> ShippedOrder | None:
        """Commande enregistrée (None si inconnue)."""
        with self._lock:
            return self._orders.get(order_id)

    def refunded(self, order_id: str) -> Decimal:
        """Ventes HT déjà remboursées sur la commande."""
        with self._lock:
            return sum((r.net_sales_ht for r in self._refunds.values() if r.order_id == order_id), ZERO)

    def status(self, order_id: str) -> Literal["PAID", "REFUNDED"] | None:
        """``PAID`` (non remboursée en totalité), ``REFUNDED`` (remboursée en totalité) ou None (inconnue)."""
        order = self.get(order_id)
        if order is None:
            return None
        return "REFUNDED" if self.refunded(order_id) >= order.net_sales_ht else "PAID"

    def contribution_bound(self, order_id: str, cogs: Decimal = ZERO) -> Decimal | None:
        """Contribution avant acquisition **maximale** que les données de la commande justifient.

        Ventes nettes − avoirs − frais de paiement − logistique réelle − coût historique connu (≥ 0 non imposé).
        """
        order = self.get(order_id)
        if order is None:
            return None
        return order.net_sales_ht - self.refunded(order_id) - order.payment_fees - order.shipping_cost_actual - cogs
