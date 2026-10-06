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
* **Espace de noms du moteur** (revue R4, R3-NEW-04) : les identifiants ``order:``, ``refund:``, ``cost:``,
  ``expense:``, ``fixed:`` et les sources ``commande``, ``remboursement`` sont réservés aux écritures
  **dérivées** par le moteur ; une écriture externe qui les emprunte est refusée (422). Une commande est
  enregistrée **atomiquement** : ses écritures dérivées et sa sortie de stock sont contrôlées avant
  l'écriture de la commande ; au redémarrage, un conflit sur une écriture dérivée est signalé (étoile polaire
  « incomplète ») sans bloquer le registre.
* **Coût des ventes dérivé** (revue R4, R3-NEW-05) : une commande expédiée porte ses lignes (SKU × quantité) ;
  le moteur en dérive la sortie au CMP (``ISSUE`` du registre de coûts, référence ``order:<id>``), jamais
  une déclaration de l'agent finance.
* **Frais de paiement comptés une fois** (revue R4, R3-DOC-03) : un PAYMENT externe portant l'``order_id``
  d'une commande enregistrée est refusé ; une commande enregistrée après des frais externes de la même
  commande n'en dérive que le complément.
* **Contribution d'une commande attribuée** (revue R6, R5-NEW-01) : dérivée des registres
  (:meth:`OrderRegister.derived_contribution` : ventes nettes − avoirs − frais − logistique réelle − coût des ventes
  net du :class:`CostRegister`), jamais la valeur de conversion transmise par le connecteur publicitaire.
* **Commande jamais perdue pour un SKU** (revue R6, R5-NEW-02) : ancien SKU d'une clé rattaché par l'historique du
  catalogue ; SKU inconnu ou ambigu : ligne non rattachée (:data:`UNRESOLVED_KEY_PREFIX`), coût des ventes en
  attente, rattachée par la propriétaire (:meth:`OrderRegister.resolve_line`).
* **Chiffre d'affaires reconnu à l'expédition, jamais à l'encaissement** (pré-drop, 6.10.2026) : l'argent d'une
  réservation pré-drop reste une **dette** (:class:`pokeshop.predrop.PredropRegistry`) jusqu'à la commande expédiée ;
  ses ventes et sa sortie au CMP sont datées de l'expédition (:attr:`ShippedOrder.recognized_at`, posée par le
  moteur), jamais de la date de paiement. Aucune écriture de l'étoile polaire n'est dérivée d'une réservation.
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
    "RESERVED_ENTRY_PREFIXES",
    "RESERVED_SOURCES",
    "ROLE_POSTS",
    "OrderLine",
    "OrderRegister",
    "UNRESOLVED_KEY_PREFIX",
    "unresolved_key",
    "is_unresolved_key",
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
RESERVED_ENTRY_PREFIXES: tuple[str, ...] = ("order:", "refund:", "cost:", "expense:", "fixed:")
"""Identifiants des écritures **dérivées** par le moteur : jamais acceptés d'une écriture externe (R3-NEW-04)."""
RESERVED_SOURCES: frozenset[str] = frozenset({"commande", "remboursement", "depense", "charges_fixes", COST_LEDGER_SOURCE.lower()})
"""Sources des écritures dérivées : jamais déclarables par une écriture externe."""
ORDER_SOURCE = "commande"
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
            for e in fresh:  # rejouer à l'identique une écriture existante reste sans effet (idempotence)
                self._check_namespace(e)
            for e in fresh:
                if e.post is Post.PAYMENT and e.order_id and self._order_recorded(e.order_id):
                    raise NorthStarError(
                        f"écriture {e.entry_id} : frais de paiement de la commande {e.order_id} déjà inscrits par la "
                        "commande enregistrée (POST /orders/shipped) — jamais comptés deux fois"
                    )
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

    @staticmethod
    def _check_namespace(entry: ContributionEntry) -> None:
        """Écriture externe : identifiants et sources des écritures dérivées réservés au moteur (revue R4)."""
        entry_id = entry.entry_id.strip().lower()
        if any(entry_id.startswith(prefix) for prefix in RESERVED_ENTRY_PREFIXES):
            raise NorthStarError(
                f"écriture {entry.entry_id} : identifiant réservé au moteur ({', '.join(RESERVED_ENTRY_PREFIXES)} : "
                "écritures dérivées des commandes, avoirs et coûts) — choisir un autre entry_id (ex. psp:<transaction>)"
            )
        if entry.source.strip().lower() in RESERVED_SOURCES:
            raise NorthStarError(f"écriture {entry.entry_id} : source « {entry.source} » réservée au moteur")

    def _order_recorded(self, order_id: str) -> bool:
        with self._lock:
            return any(e.source == ORDER_SOURCE and e.order_id == order_id for e in self._entries.values())

    def external_payment(self, order_id: str) -> Decimal:
        """Frais de paiement **externes** (rapprochement PSP) déjà inscrits pour une commande."""
        with self._lock:
            return sum(
                (e.amount for e in self._entries.values()
                 if e.post is Post.PAYMENT and e.order_id == order_id and e.source not in (ORDER_SOURCE, "remboursement")),
                ZERO,
            )  # fmt: skip

    def check_new(self, entries: Sequence[ContributionEntry]) -> None:
        """Contrôle à blanc : lève :class:`NorthStarError` si une écriture contredit une écriture existante."""
        with self._lock:
            seen: dict[str, ContributionEntry] = {}
            for e in entries:
                existing = self._entries.get(e.entry_id) or seen.get(e.entry_id)
                if existing is not None and existing != e:
                    raise NorthStarError(f"écriture {e.entry_id} déjà enregistrée avec un autre contenu")
                seen[e.entry_id] = e

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
        entries = self.order_entries(
            order_id, at, net_sales_ht=net_sales_ht, payment_fees=payment_fees, logistics=logistics,
            after_sales=after_sales, label_ref=label_ref,
        )  # fmt: skip
        self._add(entries)
        return tuple(entries)

    def order_entries(
        self,
        order_id: str,
        at: datetime,
        *,
        net_sales_ht: Decimal | int | str,
        payment_fees: Decimal | int | str,
        logistics: Decimal | int | str | None,
        after_sales: Decimal | int | str = ZERO,
        label_ref: str | None = None,
    ) -> list[ContributionEntry]:
        """Écritures dérivées d'une commande, **sans les enregistrer** (contrôle à blanc, :meth:`check_new`).

        Frais de paiement : seulement le complément des frais externes déjà inscrits pour la même commande
        (rapprochement PSP du workflow 02) — jamais comptés deux fois (revue R4, R3-DOC-03).
        """
        sales = _cents(net_sales_ht, "net_sales_ht")
        if sales <= 0:
            raise NorthStarError("ventes nettes d'une commande ≤ 0")
        fees = _cents(payment_fees, "payment_fees")
        if fees < 0:
            raise NorthStarError("frais de paiement négatifs")
        fees = max(ZERO, fees - self.external_payment(order_id))
        items = [(Post.NET_SALES, sales), (Post.PAYMENT, fees)]
        items.append((Post.LOGISTICS, require_actual_logistics(order_id, logistics, label_ref)))
        items.append((Post.AFTER_SALES, _cents(after_sales, "after_sales")))
        return [
            ContributionEntry(
                entry_id=f"order:{order_id}:{post.value}", at=at, post=post, amount=amount, ref=order_id,
                source=ORDER_SOURCE, order_id=order_id,
            )
            for post, amount in items
            if amount != 0 or post is Post.NET_SALES
        ]  # fmt: skip

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
    sku: str | None = None
    """RECEIPT / RETURN : SKU boutique **au moment du mouvement**, inscrit par le moteur depuis le catalogue (jamais
    déclaré). Revue R5 (R2-NEW-01 d) : « réception déjà valorisée » se juge sur (SKU à la réception, bon), pas sur le
    SKU actuel de la fiche (un SKU déplacé puis repris ne revalorise pas la même réception physique)."""

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

    def check(self, movements: Sequence[CostMovement]) -> None:
        """Contrôle **à blanc** d'une suite de mouvements (rien n'est écrit) ; lève l'erreur du premier refus.

        Erreurs du registre (stock valorisé insuffisant, lot inconnu…) converties en :class:`NorthStarError`.
        """
        with self._lock:
            keys = {m.product_key for m in movements}
            trial: dict[str, HistoricalCostLedger] = {}
            trial_returned: dict[tuple[str, str], int] = {}
            try:
                for m in self._movements:
                    if m.product_key in keys:
                        self._apply(trial, trial_returned, m)
                for m in movements:
                    self._apply(trial, trial_returned, m)
            except CostError as exc:
                raise NorthStarError(str(exc)) from exc

    def has_issue(self, product_key: str, ref: str) -> bool:
        """Vrai si une sortie (ISSUE) de référence ``ref`` existe déjà pour le produit."""
        with self._lock:
            return any(m.kind == "ISSUE" and m.product_key == product_key and m.ref == ref for m in self._movements)

    def issued_qty(self, product_key: str, ref: str) -> int:
        """Unités déjà sorties (ISSUE) sous la référence ``ref`` pour le produit (sorties partielles cumulées)."""
        with self._lock:
            return sum(m.qty or 0 for m in self._movements if m.kind == "ISSUE" and m.product_key == product_key and m.ref == ref)

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

    def order_cogs(self, sale_ref: str) -> Decimal | None:
        """Coût des ventes **net** d'une commande : Σ coût des sorties (ISSUE ``sale_ref``) − Σ retours en stock au coût.

        Revue R6 (R5-NEW-01) : base de la contribution d'une commande attribuée (jamais une valeur déclarée). Un retour
        est rattaché à sa vente par son **mouvement** (``sale_ref``), jamais par sa référence libre : deux retours de
        même ``ref`` sur deux commandes ne se confondent pas (le k-ième mouvement RETURN d'une référence produit = la
        k-ième écriture RETURN de son registre). Incohérence entre mouvements et registre : None (inconnu, fermé).
        """
        with self._lock:
            total = ZERO
            for key, ledger in self._ledgers.items():
                journal = ledger.journal()
                total += sum((e.cogs for e in journal if e.kind == "ISSUE" and e.ref == sale_ref), ZERO)
                booked = [e for e in journal if e.kind == "RETURN"]
                moves = [m for m in self._movements if m.kind == "RETURN" and m.product_key == key]
                if len(booked) != len(moves):
                    return None
                # écriture RETURN : cogs = −montant remis en stock au coût de la vente d'origine
                total += sum((e.cogs for e, m in zip(booked, moves, strict=True) if m.sale_ref == sale_ref), ZERO)
            return total


# ------------------------------------------------------------------- commandes enregistrées

UNRESOLVED_KEY_PREFIX = "sku-non-rattache:"
"""Revue R6 (R5-NEW-02) : clé d'une ligne de commande dont le SKU n'a **pas** pu être rattaché à une clé produit
canonique (SKU inconnu du catalogue, ou porté au fil du temps par plusieurs références). Réservée au moteur : aucune
fiche du catalogue ne la porte ; la ligne reste en coût des ventes en attente (étoile polaire et photo incomplètes)
jusqu'au rattachement par la propriétaire (``POST /orders/{order_id}/lines/resolve``)."""


def unresolved_key(public_sku: str) -> str:
    """Clé réservée d'une ligne non rattachée (:data:`UNRESOLVED_KEY_PREFIX` + SKU)."""
    return f"{UNRESOLVED_KEY_PREFIX}{public_sku}"


def is_unresolved_key(key: str) -> bool:
    """Vrai pour une clé de ligne non rattachée (jamais une clé du catalogue)."""
    return key.startswith(UNRESOLVED_KEY_PREFIX)


class OrderLine(FrozenModel):
    """Ligne expédiée d'une commande : SKU boutique, clé produit canonique (résolue par le moteur), quantité."""

    public_sku: str = Field(min_length=3, max_length=64)
    product_key: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1, le=10_000)


def _posted_content(model: FrozenModel) -> dict[str, Any]:
    data = model.model_dump(mode="json", exclude={"recorded_by", "recorded_at", "recognized_at"})
    data["lines"] = [{"public_sku": ln["public_sku"], "qty": ln["qty"]} for ln in data.get("lines", [])]
    return data


class ShippedOrder(FrozenModel):
    """Commande payée et expédiée, enregistrée par le moteur (seule source des ventes de l'étoile polaire).

    Revue R4 (R3-NEW-05) : ``lines`` (SKU × quantité) — le moteur en dérive la sortie de stock et le coût des
    ventes au CMP ; une commande ancienne sans lignes reste lisible (coût des ventes non dérivé : signalé).
    """

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
    lines: tuple[OrderLine, ...] = ()
    recognized_at: datetime | None = None
    """Date de reconnaissance des ventes (et de la sortie au CMP) fixée **par le moteur** : pour une réservation
    pré-drop payée longtemps avant réception, l'expédition (date d'enregistrement de la commande expédiée) — le
    chiffre d'affaires est reconnu à l'expédition, jamais à l'encaissement (:mod:`pokeshop.predrop`). None : date
    de paiement (commande ordinaire, payée et expédiée dans la foulée)."""

    @field_validator("paid_at", "recorded_at", "recognized_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("horodatage avec fuseau horaire obligatoire")
        return v

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence : champs **postés** (hors acteur, date d'enregistrement, date de
        reconnaissance et clé produit des lignes, dérivées par le moteur — revue R6, R5-NEW-02 : une ligne rattachée
        ensuite reste la même commande)."""
        return _posted_content(self)

    @property
    def recognition_at(self) -> datetime:
        """Date des écritures de ventes et de la sortie au CMP : ``recognized_at`` sinon date de paiement."""
        return self.recognized_at if self.recognized_at is not None else self.paid_at

    @property
    def sale_ref(self) -> str:
        """Référence des sorties de stock dérivées de la commande (``sale_ref`` d'un retour)."""
        return f"order:{self.order_id}"

    def qty_by_product(self) -> dict[str, int]:
        """Unités vendues par référence (lignes cumulées)."""
        qty: dict[str, int] = {}
        for line in self.lines:
            qty[line.product_key] = qty.get(line.product_key, 0) + line.qty
        return dict(sorted(qty.items()))

    def issue_movements(self) -> tuple[CostMovement, ...]:
        """Sorties au CMP dérivées des lignes (une par référence ; quantités cumulées)."""
        return tuple(
            CostMovement(kind="ISSUE", product_key=key, at=self.recognition_at, ref=self.sale_ref, qty=n,
                         recorded_by="moteur")
            for key, n in self.qty_by_product().items()
        )  # fmt: skip


class OrderRefund(FrozenModel):
    """Avoir (remboursement) sur une commande enregistrée.

    Revue R5 (R3-NEW-05) : ``lines`` = unités **retournées** (SKU × quantité, ≤ vendues − déjà retournées) ; vide
    pour un remboursement sans retour (geste commercial). Seules ces lignes, avec la réception physique du retour
    (``POST /stock/receive``, ref ``return:<refund_id>``), permettent un retour en stock au coût (RETURN).
    """

    refund_id: str = Field(min_length=1, max_length=120)
    order_id: str = Field(min_length=1, max_length=120)
    at: datetime
    net_sales_ht: Decimal = Field(gt=0)
    payment_fees_refunded: Decimal = Field(default=ZERO, ge=0)
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime
    lines: tuple[OrderLine, ...] = ()

    @field_validator("at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("horodatage avec fuseau horaire obligatoire")
        return v

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence (champs postés, comme :meth:`ShippedOrder.content`)."""
        return _posted_content(self)


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
        self.derivation_errors: dict[str, str] = {}
        """Commande ou avoir -> motif d'une écriture dérivée impossible au rattrapage (étoile polaire incomplète)."""
        self._pending: dict[str, dict[str, int]] = {}
        """Revue R5 (R4-NEW-01) : commande -> unités vendues dont la sortie au CMP attend un stock valorisé (coût des
        ventes en attente ; étoile polaire et photo signalées incomplètes). Dérivé : recalculé au démarrage."""

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
                elif "line_resolution" in record:  # revue R6 (R5-NEW-02)
                    res = record["line_resolution"]
                    if res["order_id"] not in register._orders or is_unresolved_key(res["product_key"]):
                        raise KeyError(res["order_id"])
                    register._apply_resolution(res["order_id"], res["public_sku"], res["product_key"])
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

    def record_shipped(
        self, order: ShippedOrder, northstar: NorthStarLedger | None, costs: CostRegister | None = None
    ) -> tuple[ShippedOrder, bool]:
        """Enregistre une commande expédiée puis dérive ses écritures ; (commande, nouvelle ?).

        Revue R4 (R3-NEW-04) : les écritures dérivées de l'étoile polaire sont contrôlées à blanc **avant** l'écriture
        de la commande (identifiant déjà pris : refus, rien n'est écrit). Revue R5 (R4-NEW-01) : une commande payée
        n'est **jamais** refusée faute de coût — la sortie au CMP porte sur le stock valorisé disponible, le reste
        attend (coût des ventes en attente, :meth:`pending_cogs`) et est dérivé dès qu'un coût existe
        (:meth:`derive_pending`, et au démarrage par :meth:`sync`).
        """
        require_actual_logistics(order.order_id, order.shipping_cost_actual, order.shipping_label_ref)
        for value, name in ((order.net_sales_ht, "net_sales_ht"), (order.payment_fees, "payment_fees")):
            _cents(value, name)
        with self._lock:
            current = self._orders.get(order.order_id)
            if current is not None:
                if current.content() != order.content():
                    raise NorthStarError(f"commande {order.order_id} déjà enregistrée avec un autre contenu")
                return current, False
            entries = self._order_entries(order, northstar)
            if northstar is not None:
                northstar.check_new(entries)
            self._append({"order": order.model_dump(mode="json")})
            self._orders[order.order_id] = order
        if costs is not None:
            self._derive_issues(order, costs)
        if northstar is not None:
            northstar._add(entries)
        return order, True

    def _derive_issues(self, order: ShippedOrder, costs: CostRegister) -> int:
        """Sorties au CMP de la commande sur le stock valorisé disponible ; le reste en attente. Renvoie les sorties."""
        pending: dict[str, int] = {}
        derived = 0
        for key, qty in order.qty_by_product().items():
            if is_unresolved_key(key):  # revue R6 (R5-NEW-02) : ligne non rattachée, jamais une sortie devinée
                pending[key] = qty
                continue
            needed = qty - costs.issued_qty(key, order.sale_ref)
            if needed <= 0:
                continue
            ledger = costs.ledger(key)
            now_qty = min(needed, ledger.qty_on_hand if ledger is not None else 0)
            if now_qty > 0:
                movement = CostMovement(kind="ISSUE", product_key=key, at=order.recognition_at, ref=order.sale_ref,
                                        qty=now_qty, recorded_by="moteur")  # fmt: skip
                try:
                    costs.apply(movement)
                    derived += 1
                except NorthStarPersistenceError:
                    raise
                except (NorthStarError, CostError):
                    now_qty = 0
            if needed - now_qty > 0:
                pending[key] = needed - now_qty
        with self._lock:
            if pending:
                self._pending[order.order_id] = pending
            else:
                self._pending.pop(order.order_id, None)
        return derived

    def derive_pending(self, costs: CostRegister) -> int:
        """Dérive le coût des ventes en attente (commandes par date de paiement) ; renvoie le nombre de sorties."""
        with self._lock:
            waiting = sorted((self._orders[oid] for oid in self._pending if oid in self._orders), key=lambda o: o.paid_at)
        return sum(self._derive_issues(order, costs) for order in waiting)

    def pending_cogs(self) -> dict[str, dict[str, int]]:
        """Commandes dont le coût des ventes attend un stock valorisé : commande -> {référence: unités}."""
        with self._lock:
            return {oid: dict(p) for oid, p in sorted(self._pending.items())}

    def incomplete_reasons(self) -> dict[str, str]:
        """Motifs d'étoile polaire incomplète : écritures dérivées impossibles et coût des ventes en attente."""
        out = dict(self.derivation_errors)
        for oid, pending in self.pending_cogs().items():
            unresolved = [key.removeprefix(UNRESOLVED_KEY_PREFIX) for key in pending if is_unresolved_key(key)]
            waiting = {key: n for key, n in pending.items() if not is_unresolved_key(key)}
            parts: list[str] = []
            if unresolved:  # revue R6 (R5-NEW-02)
                parts.append(
                    f"ligne(s) {', '.join(unresolved)} non rattachée(s) à une clé produit (SKU inconnu du catalogue ou "
                    f"porté par plusieurs références) : la propriétaire rattache la ligne (POST /orders/{oid}/lines/resolve)"
                )
            if waiting:
                detail = ", ".join(f"{n} × {key}" for key, n in waiting.items())
                parts.append(
                    f"coût des ventes en attente ({detail} sans stock valorisé) : inscrire le coût de réception "
                    "(facture enregistrée, POST /costs/movements) — dérivé automatiquement ensuite"
                )
            out[f"commande {oid}"] = " ; ".join(parts)
        return out

    def unresolved_lines(self) -> dict[str, tuple[str, ...]]:
        """Commandes dont une ligne n'est pas rattachée à une clé produit : commande -> SKU (revue R6, R5-NEW-02)."""
        with self._lock:
            out = {
                oid: tuple(sorted({ln.public_sku for ln in order.lines if is_unresolved_key(ln.product_key)}))
                for oid, order in self._orders.items()
            }
        return {oid: skus for oid, skus in sorted(out.items()) if skus}

    def resolve_line(
        self,
        order_id: str,
        public_sku: str,
        product_key: str,
        *,
        recorded_by: str,
        recorded_at: datetime,
        costs: CostRegister | None = None,
    ) -> tuple[ShippedOrder, bool]:
        """Rattache une ligne non rattachée à sa clé produit canonique (propriétaire) ; (commande, nouveau ?).

        Revue R6 (R5-NEW-02) : écrit d'abord (journal ``orders``, ajout seul : ``line_resolution``), puis remplace la
        clé réservée sur les lignes de la commande **et** de ses avoirs, et dérive la sortie au CMP (coût des ventes).
        Même rattachement rejoué : sans effet ; autre clé pour une ligne déjà rattachée : refus.
        """
        if is_unresolved_key(product_key):
            raise NorthStarError(f"clé produit {product_key} réservée au moteur")
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise NorthStarError(f"commande {order_id} inconnue du moteur")
            lines = [ln for ln in order.lines if ln.public_sku == public_sku]
            if not lines:
                raise NorthStarError(f"commande {order_id} : aucune ligne {public_sku}")
            open_lines = [ln for ln in lines if is_unresolved_key(ln.product_key)]
            if not open_lines:
                done = {ln.product_key for ln in lines}
                if done == {product_key}:
                    return order, False
                raise NorthStarError(
                    f"commande {order_id} : ligne {public_sku} déjà rattachée à {', '.join(sorted(done))}"
                )
            resolution = {"order_id": order_id, "public_sku": public_sku, "product_key": product_key,
                          "recorded_by": recorded_by, "recorded_at": recorded_at.isoformat()}  # fmt: skip
            self._append({"line_resolution": resolution})
            order = self._apply_resolution(order_id, public_sku, product_key)
        if costs is not None:
            self._derive_issues(order, costs)
        return order, True

    def _apply_resolution(self, order_id: str, public_sku: str, product_key: str) -> ShippedOrder:
        old = unresolved_key(public_sku)

        def fix(lines: tuple[OrderLine, ...]) -> tuple[OrderLine, ...]:
            return tuple(
                ln.model_copy(update={"product_key": product_key})
                if ln.public_sku == public_sku and ln.product_key == old else ln
                for ln in lines
            )  # fmt: skip

        order = self._orders[order_id]
        order = order.model_copy(update={"lines": fix(order.lines)})
        self._orders[order_id] = order
        for rid, refund in list(self._refunds.items()):
            if refund.order_id == order_id:
                self._refunds[rid] = refund.model_copy(update={"lines": fix(refund.lines)})
        pending = self._pending.get(order_id)
        if pending is not None:
            pending.pop(old, None)
            if not pending:
                self._pending.pop(order_id, None)
        return order

    @staticmethod
    def _order_entries(order: ShippedOrder, northstar: NorthStarLedger | None) -> list[ContributionEntry]:
        if northstar is None:
            return []
        return northstar.order_entries(
            order.order_id,
            order.recognition_at,
            net_sales_ht=order.net_sales_ht,
            payment_fees=order.payment_fees,
            logistics=order.shipping_cost_actual,
            label_ref=order.shipping_label_ref,
        )

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
            # Revue R5 (R3-NEW-05) : unités retournées ≤ vendues − déjà retournées, par référence de la commande.
            sold = order.qty_by_product()
            returned: dict[str, int] = {}
            for r in self._refunds.values():
                if r.order_id == refund.order_id:
                    for ln in r.lines:
                        returned[ln.product_key] = returned.get(ln.product_key, 0) + ln.qty
            for ln in refund.lines:
                if ln.product_key not in sold:
                    raise NorthStarError(f"avoir {refund.refund_id} : {ln.public_sku} n'est pas une ligne de la commande")
                returned[ln.product_key] = returned.get(ln.product_key, 0) + ln.qty
                if returned[ln.product_key] > sold[ln.product_key]:
                    raise NorthStarError(
                        f"avoir {refund.refund_id} : {returned[ln.product_key]} unité(s) retournée(s) de {ln.product_key} "
                        f"> {sold[ln.product_key]} vendue(s)"
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
                order.recognition_at,
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

    def sync(self, northstar: NorthStarLedger, costs: CostRegister | None = None) -> dict[str, str]:
        """Rattrape les écritures dérivées absentes (étoile polaire, sorties de stock), idempotent.

        Revue R4 (R3-NEW-04) : un conflit sur une écriture dérivée (identifiant déjà pris par une écriture
        ancienne) ne bloque **pas** le registre : il est relevé dans :attr:`derivation_errors` (étoile polaire
        « incomplète ») et les autres commandes sont rattrapées. Renvoie ces motifs.
        """
        with self._lock:
            orders = list(self._orders.values())
            refunds = list(self._refunds.values())
        errors: dict[str, str] = {}
        for order in sorted(orders, key=lambda o: o.paid_at):
            try:
                if costs is not None:
                    self._derive_issues(order, costs)  # revue R5 : partiel, le reste en attente (jamais un refus)
                if not order.lines:
                    errors[f"commande {order.order_id}"] = "commande sans lignes : coût des ventes non dérivé"
                self._derive_order(order, northstar)
            except NorthStarPersistenceError:
                raise
            except (NorthStarError, CostError) as exc:
                errors[f"commande {order.order_id}"] = str(exc)
        for refund in refunds:
            try:
                self._derive_refund(refund, northstar)
            except NorthStarPersistenceError:
                raise
            except NorthStarError as exc:
                errors[f"avoir {refund.refund_id}"] = str(exc)
        self.derivation_errors = errors
        return errors

    def get(self, order_id: str) -> ShippedOrder | None:
        """Commande enregistrée (None si inconnue)."""
        with self._lock:
            return self._orders.get(order_id)

    def refund(self, refund_id: str) -> OrderRefund | None:
        """Avoir enregistré (None si inconnu)."""
        with self._lock:
            return self._refunds.get(refund_id)

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

    def contribution_bound(self, order_id: str) -> Decimal | None:
        """Plafond **hors coût des ventes** : ventes nettes − avoirs − frais de paiement − logistique réelle.

        Revue R6 (R5-NEW-01) : seul, ce plafond ignore le coût des ventes (≈ 4 × la contribution réelle pour un coût
        produit de 60 % du panier) ; le stop-loss pub retient :meth:`derived_contribution`.
        """
        order = self.get(order_id)
        if order is None:
            return None
        return order.net_sales_ht - self.refunded(order_id) - order.payment_fees - order.shipping_cost_actual

    def order_cogs(self, order_id: str, costs: CostRegister | None) -> Decimal | None:
        """Coût des ventes net de la commande tiré du registre de coûts du moteur ; None s'il n'est pas connu.

        Inconnu (fermé par défaut) : registre de coûts absent, commande sans lignes, coût des ventes en attente
        (:meth:`pending_cogs`, ligne non rattachée comprise : revue R6, R5-NEW-02) ou registre incohérent.
        """
        order = self.get(order_id)
        if order is None or costs is None or not order.lines:
            return None
        with self._lock:
            if order_id in self._pending:
                return None
        if any(is_unresolved_key(line.product_key) for line in order.lines):
            return None
        return costs.order_cogs(order.sale_ref)

    def derived_contribution(self, order_id: str, costs: CostRegister | None) -> Decimal | None:
        """Contribution avant acquisition **dérivée des registres** (revue R6, R5-NEW-01) ; None si commande inconnue.

        Ventes nettes − avoirs − frais de paiement − logistique réelle − coût des ventes net (ISSUE ``order:<id>``
        − RETURN), jamais une valeur déclarée. Coût des ventes inconnu (en attente, sans lignes, ligne non rattachée) :
        **0** (fermé par défaut ; l'étoile polaire et la photo sont alors signalées incomplètes).
        """
        ceiling = self.contribution_bound(order_id)
        if ceiling is None:
            return None
        cogs = self.order_cogs(order_id, costs)
        return ZERO if cogs is None else min(ceiling - cogs, ceiling)
