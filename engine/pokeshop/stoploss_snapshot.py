"""Photo d'activité du stop-loss construite **par le moteur** à partir de ses registres (revue E2E-08).

Avant : la seule entrée de la photo était ``POST /stoploss/state`` (photo entière postée par un
workflow), et aucun workflow ni module ne la construisait. Le stop-loss restait « non évaluable » en
permanence : dépenses et écritures réelles refusées sans que les six niveaux ne soient jamais évalués.

Ici, ``POST /stoploss/state/refresh`` (workflow n8n 07, toutes les heures) assemble la photo à partir
de registres dont aucune valeur décisive n'est déclarée par l'agent qui en profite :

=========================  ===========================================================================
Élément de la photo        Registre (qui l'alimente)
=========================  ===========================================================================
Apports et retraits        :class:`CapitalRegister` — ``POST /capital/movements``, **jeton propriétaire**
Cash (banque + PayPal)     derniers relevés ``POST /treasury/bank-balance`` et ``/treasury/paypal-balance``
                           (connecteurs, acteur déduit du jeton ; la photo est datée du plus ancien relevé)
Dettes et créances         :class:`BalanceStatement` — ``POST /treasury/balance-items`` : précommandes
                           encaissées non livrées (déduites du cash disponible), factures reçues non payées,
                           TVA due, versements en transit ; listes vides **attestées** si aucune
Stock au coût historique   :class:`pokeshop.northstar.CostRegister` (``POST /costs/movements``)
Exposition par extension   même registre, extension lue dans le catalogue validé (``POST /catalog/items``)
Marges produit             prix public en vigueur (historique des prix) et coût du stock (CMP) ou coût
                           de remplacement frais, avec les règles de prix signées
Publicité                  :class:`AdsActivityRegister` — ``POST /ads/activity`` (connecteur publicitaire)
Plafond pub, budget stock  mandat signé actif et règles (jamais la photo)
=========================  ===========================================================================

Fermé par défaut : une source manquante, périmée ou datée du futur => :class:`PhotoSourcesError`
(409, la photo précédente reste en vigueur et se périme seule) ; les dettes et créances ne sont jamais
supposées nulles : sans déclaration récente, pas de photo. Le mandat ne tient pour vérifiables que les
relevés et déclarations déposés par un **autre** jeton nommé que celui qui demande la dépense. Limite
connue (``orchestration/README.md``) : l'activité publicitaire n'est connue que par le connecteur
(``POST /ads/activity``) ; aucune campagne ne doit tourner sans lui.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from .audit import StateJournal, StateStoreError
from .catalogue_sync import CatalogRegistry
from .costs import PriceHistory, ReplacementCostBook
from .errors import PokeshopError
from .mandate import PayPalBalanceReading
from .models import FrozenModel, PricingParams
from .northstar import CostRegister
from .pricing import contribution, small_product_rule_active
from .stoploss import (
    AdSpend,
    AttributedOrder,
    BalanceItem,
    CapitalMovement,
    ExtensionExposure,
    NetWorthSnapshot,
    ProductMargin,
    StockValuationLine,
    StopLossState,
)

__all__ = [
    "CapitalRegister",
    "CapitalRecord",
    "BankBalanceReading",
    "BalanceStatement",
    "AdsActivityRegister",
    "ActivityRegisterError",
    "ActivityRegisterPersistenceError",
    "PhotoSourcesError",
    "build_activity_photo",
    "UNKNOWN_EXTENSION",
    "FUTURE_SKEW",
]

UNKNOWN_EXTENSION = "INCONNUE"
"""Extension d'un stock absent du catalogue validé : comptée à part (jamais ignorée)."""
FUTURE_SKEW = timedelta(minutes=5)


class ActivityRegisterError(PokeshopError, ValueError):
    """Entrée refusée (conflit avec le registre, date incohérente)."""


class ActivityRegisterPersistenceError(ActivityRegisterError, StateStoreError):
    """Journal illisible ou écriture refusée : rien n'est appliqué (fermé par défaut)."""


class PhotoSourcesError(PokeshopError, ValueError):
    """Photo impossible : sources manquantes, périmées ou datées du futur (liste en français)."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("photo d'activité impossible : " + " ; ".join(problems))


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


def _load(store: StateJournal, what: str) -> list[dict[str, Any]]:
    try:
        return list(store.load())
    except StateStoreError as exc:
        raise ActivityRegisterPersistenceError(f"{what} : {exc}") from exc


def _append(store: StateJournal | None, record: dict[str, Any], what: str) -> None:
    if store is None:
        return
    try:
        store.append(record)
    except StateStoreError as exc:
        raise ActivityRegisterPersistenceError(f"{what} non enregistré ({exc})") from exc


# --------------------------------------------------------------------------- capital


class CapitalRecord(FrozenModel):
    """Mouvement de capital attesté par la propriétaire (jeton propriétaire vérifié par l'API)."""

    movement: CapitalMovement
    recorded_by: Literal["propriétaire"] = "propriétaire"
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "recorded_at")


class CapitalRegister:
    """Apports et retraits de capital (journal ``capital_movements``, ajout seul, propriétaire seule).

    Idempotent par ``movement_id`` : même contenu => sans effet ; contenu différent => refus (une
    correction s'écrit comme un nouveau mouvement, jamais en réécrivant l'ancien).
    """

    STREAM = "capital_movements"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, CapitalRecord] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> CapitalRegister:
        """Relit le registre (:class:`ActivityRegisterPersistenceError` s'il est illisible)."""
        register = cls()
        for n, record in enumerate(_load(store, "mouvements de capital"), start=1):
            try:
                item = CapitalRecord.model_validate(record["capital"])
            except (KeyError, TypeError, ValidationError) as exc:
                raise ActivityRegisterPersistenceError(f"mouvements de capital : enregistrement {n} illisible") from exc
            register._items[item.movement.movement_id] = item
        register._store = store
        return register

    def record(self, movement: CapitalMovement, *, now: datetime) -> tuple[CapitalRecord, bool]:
        """Enregistre un mouvement ; (enregistrement, nouveau ?)."""
        if movement.at - now > FUTURE_SKEW:
            raise ActivityRegisterError("mouvement de capital daté du futur")
        with self._lock:
            current = self._items.get(movement.movement_id)
            if current is not None:
                if current.movement != movement:
                    raise ActivityRegisterError(
                        f"mouvement {movement.movement_id} déjà enregistré avec un autre contenu : "
                        "écrire un nouveau mouvement (correction), jamais réécrire l'ancien"
                    )
                return current, False
            item = CapitalRecord(movement=movement, recorded_at=now)
            _append(self._store, {"capital": item.model_dump(mode="json")}, "mouvement de capital")
            self._items[movement.movement_id] = item
            return item, True

    def movements(self, *, until: datetime | None = None) -> tuple[CapitalMovement, ...]:
        """Mouvements (antérieurs ou égaux à ``until``), par date."""
        with self._lock:
            items = [i.movement for i in self._items.values() if until is None or i.movement.at <= until]
        return tuple(sorted(items, key=lambda m: (m.at, m.movement_id)))


# ------------------------------------------------------------------------- trésorerie


class BankBalanceReading(FrozenModel):
    """Solde du compte bancaire de l'activité relevé par un connecteur (acteur déduit du jeton)."""

    as_of: datetime
    balance_chf: Decimal
    source: str = Field(min_length=3)
    recorded_by: str = Field(min_length=2)

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")


class BalanceStatement(FrozenModel):
    """Dettes et créances à date (déclarées par un jeton nommé, jamais supposées nulles).

    ``preorders_collected_chf`` : précommandes encaissées non livrées (dette envers les clients, déduite du
    cash disponible) ; ``debts`` : factures reçues non payées, TVA due, remboursements promis… ;
    ``receivables`` : versements PSP en transit, TVA à récupérer, stock payé en transit (au coût).
    """

    as_of: datetime
    preorders_collected_chf: Decimal = Field(ge=0)
    debts: tuple[BalanceItem, ...] = ()
    receivables: tuple[BalanceItem, ...] = ()
    source: str = Field(min_length=3)
    recorded_by: str = Field(min_length=2)

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")


# --------------------------------------------------------------------------- publicité


class AdsActivityRegister:
    """Dépenses publicitaires par campagne et par jour, commandes attribuées (journal ``ads_activity``).

    Dernière valeur connue par (campagne, jour) et par commande (statut payée, annulée, remboursée).
    """

    STREAM = "ads_activity"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._spends: dict[tuple[str, date], AdSpend] = {}
        self._orders: dict[str, AttributedOrder] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> AdsActivityRegister:
        """Relit le registre (:class:`ActivityRegisterPersistenceError` s'il est illisible)."""
        register = cls()
        for n, record in enumerate(_load(store, "activité publicitaire"), start=1):
            try:
                spends = [AdSpend.model_validate(s) for s in record["ad_spends"]]
                orders = [AttributedOrder.model_validate(o) for o in record["attributed_orders"]]
            except (KeyError, TypeError, ValidationError) as exc:
                raise ActivityRegisterPersistenceError(f"activité publicitaire : enregistrement {n} illisible") from exc
            register._apply(spends, orders)
        register._store = store
        return register

    def _apply(self, spends: Iterable[AdSpend], orders: Iterable[AttributedOrder]) -> None:
        for s in spends:
            self._spends[(s.campaign_id, s.day)] = s
        for o in orders:
            self._orders[o.order_id] = o

    def record(self, spends: list[AdSpend], orders: list[AttributedOrder], *, today: date) -> int:
        """Enregistre un lot (écrit d'abord) ; renvoie le nombre d'éléments reçus."""
        if any(s.day > today for s in spends):
            raise ActivityRegisterError("dépense publicitaire datée du futur")
        with self._lock:
            _append(
                self._store,
                {"ad_spends": [s.model_dump(mode="json") for s in spends],
                 "attributed_orders": [o.model_dump(mode="json") for o in orders]},
                "activité publicitaire",
            )  # fmt: skip
            self._apply(spends, orders)
        return len(spends) + len(orders)

    def window(self, since: date) -> tuple[tuple[AdSpend, ...], tuple[AttributedOrder, ...]]:
        """Dépenses et commandes depuis ``since`` (jour civil inclus)."""
        with self._lock:
            spends = tuple(s for (_, d), s in sorted(self._spends.items()) if d >= since)
            orders = tuple(o for _, o in sorted(self._orders.items()) if o.paid_at.date() >= since)
        return spends, orders


# ------------------------------------------------------------------------------ photo


def _product_keys(costs: CostRegister) -> list[str]:
    return sorted({m.product_key for m in costs.movements()})


def build_activity_photo(
    *,
    now: datetime,
    capital: CapitalRegister,
    paypal: PayPalBalanceReading | None,
    bank: BankBalanceReading | None,
    balances: BalanceStatement | None,
    costs: CostRegister,
    catalog: CatalogRegistry,
    price_history: PriceHistory,
    replacement_costs: ReplacementCostBook,
    params: PricingParams,
    stock_budget_chf: Decimal,
    ads_daily_cap_chf: Decimal | None,
    ads: AdsActivityRegister,
    max_age: timedelta,
    ads_window_days: int = 30,
) -> tuple[StopLossState, dict[str, Any]]:
    """Photo d'activité tirée des registres ; :class:`PhotoSourcesError` si une source manque ou est périmée.

    ``as_of`` de la photo = date du **plus ancien** relevé de cash : une photo n'est jamais plus fraîche
    que sa donnée la plus vieille (le stop-loss et le mandat jugent la fraîcheur sur elle).
    """
    _aware(now, "now")
    problems: list[str] = []
    readings: list[tuple[str, datetime]] = []
    required: tuple[tuple[str, Any, str], ...] = (
        ("solde PayPal", paypal, "POST /treasury/paypal-balance, connecteur"),
        ("solde bancaire", bank, "POST /treasury/bank-balance, connecteur"),
        ("déclaration des dettes et créances", balances,
         "POST /treasury/balance-items : précommandes encaissées, factures non payées, TVA… ; listes vides si aucune"),
    )  # fmt: skip
    for label, reading, route in required:
        if reading is None:
            problems.append(f"{label} non relevé ({route})" if label.startswith("solde") else f"{label} absente ({route})")
            continue
        if reading.as_of - now > FUTURE_SKEW:
            problems.append(f"{label} : daté du futur ({reading.as_of.isoformat()})")
        elif now - reading.as_of > max_age:
            problems.append(f"{label} : périmé, du {reading.as_of.isoformat()} (> {max_age})")
        readings.append((label, reading.as_of))
    as_of = min((at for _, at in readings), default=now)
    movements = capital.movements(until=as_of)
    if not any(m.kind == "CONTRIBUTION" for m in movements):
        problems.append("aucun apport de capital enregistré (POST /capital/movements, jeton propriétaire)")
    if problems:
        raise PhotoSourcesError(problems)
    assert paypal is not None and bank is not None and balances is not None
    cash = paypal.balance_chf + bank.balance_chf
    debts = balances.debts
    if balances.preorders_collected_chf > 0:
        debts = (BalanceItem(label="Précommandes encaissées non livrées", amount=balances.preorders_collected_chf), *debts)

    stock: list[StockValuationLine] = []
    unit_costs: dict[str, Decimal] = {}
    first_receipt: dict[str, datetime] = {}
    last_issue: dict[str, datetime] = {}
    for m in costs.movements():
        if m.kind == "RECEIPT":
            first_receipt[m.product_key] = min(first_receipt.get(m.product_key, m.at), m.at)
        elif m.kind == "ISSUE":
            last_issue[m.product_key] = max(last_issue.get(m.product_key, m.at), m.at)
    for key in _product_keys(costs):
        ledger = costs.ledger(key)
        if ledger is None:
            continue
        valuation = ledger.valuation()
        if valuation.qty_on_hand > 0:
            stock.append(StockValuationLine.from_ledger(ledger))
            if valuation.average_unit_cost is not None:
                unit_costs[key] = valuation.average_unit_cost

    by_ext: dict[str, dict[str, Any]] = {}
    for line in stock:
        ext = catalog.extension_of(line.product_key) or UNKNOWN_EXTENSION
        slot = by_ext.setdefault(ext, {"value": Decimal("0"), "first": None, "last": None})
        slot["value"] += line.historical_value
        first = first_receipt.get(line.product_key)
        last = last_issue.get(line.product_key)
        if first is not None and (slot["first"] is None or first < slot["first"]):
            slot["first"] = first
        if last is not None and (slot["last"] is None or last > slot["last"]):
            slot["last"] = last
    extensions = tuple(
        ExtensionExposure(extension=ext, stock_value_at_cost=s["value"], first_stocked_at=s["first"], last_sale_at=s["last"])
        for ext, s in sorted(by_ext.items())
    )

    margins: list[ProductMargin] = []
    seen: set[str] = set()
    for entry in catalog.entries():
        key = entry.listing.product_key
        if key in seen:
            continue
        price = price_history.current_price(entry.product_id) or price_history.current_price(key)
        cost = unit_costs.get(key) or unit_costs.get(entry.product_id)
        if cost is None:
            rc = replacement_costs.current(entry.product_id, now) or replacement_costs.current(key, now)
            cost = rc.unit_cost if rc is not None else None
        if price is None or cost is None or price <= 0:
            continue
        small = (
            small_product_rule_active(params)
            and params.small_product_max_cost is not None
            and cost <= params.small_product_max_cost
        )
        chf, pct = contribution(price, cost, params, per_order_costs=not small)
        listing_ext = entry.listing.identity.extension
        margins.append(
            ProductMargin(product_key=key, extension=str(listing_ext) if listing_ext else None, contribution_chf=chf,
                          contribution_pct=pct, small_product=small)
        )  # fmt: skip
        seen.add(key)

    spends, orders = ads.window(as_of.date() - timedelta(days=ads_window_days))
    state = StopLossState(
        as_of=as_of,
        products=tuple(margins),
        extensions=extensions,
        stock_budget_chf=stock_budget_chf,
        ad_spends=tuple(s for s in spends if s.day <= as_of.date()),
        attributed_orders=tuple(o for o in orders if o.paid_at <= as_of),
        ads_daily_cap_chf=ads_daily_cap_chf,
        cash_available_chf=cash - balances.preorders_collected_chf,
        capital_movements=movements,
        net_worth=NetWorthSnapshot(
            as_of=as_of, cash_chf=cash, stock=tuple(stock), receivables=balances.receivables, debts=debts
        ),
    )
    sources = {
        "as_of": as_of,
        "cash": {"paypal": {"as_of": paypal.as_of, "recorded_by": paypal.recorded_by},
                 "banque": {"as_of": bank.as_of, "recorded_by": bank.recorded_by}},
        "dettes_creances": {"as_of": balances.as_of, "recorded_by": balances.recorded_by,
                            "debts": len(debts), "receivables": len(balances.receivables)},
        "capital_movements": len(movements),
        "stock_lines": len(stock),
        "extensions": [e.extension for e in extensions],
        "product_margins": len(margins),
        "ad_spends": len(state.ad_spends),
        "attributed_orders": len(state.attributed_orders),
    }  # fmt: skip
    return state, sources
