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
Dettes et créances         :class:`BalanceStatementBook` (journal ``balance_statements``, revue R5) —
                           ``POST /treasury/balance-items`` : **dettes** (précommandes encaissées non livrées,
                           déduites du cash disponible, TVA due, remboursements promis ; listes vides
                           **attestées** ; âge accepté explicite, 24 h) et **créances** de la propriétaire seule :
                           deux registres séparés et persistés (une déclaration de dettes n'efface jamais les
                           créances ; le plancher des dettes survit au redémarrage). Revue R4 (R3-NEW-02) :
                           **plancher** des factures fournisseur enregistrées non payées (:mod:`pokeshop.invoices`,
                           ``n8n-03-factures`` ; paiement relevé par ``connecteur-tresorerie``) ajouté aux dettes
Réservations pré-drop      :class:`pokeshop.predrop.PredropRegistry` — argent encaissé en pré-drop ni expédié ni
                           remboursé : dette **dérivée** du registre (``POST /predrop/reservations``, workflow 02),
                           **ajoutée** aux précommandes déclarées (qui ne comptent que les précommandes hors pré-drop)
                           et déduite du cash disponible ; jamais déclarée par un agent
Stock au coût historique   :class:`pokeshop.northstar.CostRegister` (``POST /costs/movements``)
Exposition par extension   même registre, extension lue dans le catalogue validé (``POST /catalog/items``)
Marges produit             prix public en vigueur (historique des prix) et coût du stock (CMP) ou coût
                           de remplacement frais, avec les règles de prix signées
Publicité                  :class:`AdsActivityRegister` — ``POST /ads/activity`` (``connecteur-publicite``,
                           jamais l'agent acquisition) ; ajout seul par (campagne, jour) ; dépense retenue =
                           MAX(déclaration, paiements pub **engagés** du registre du mandat : approuvés à
                           leur date de décision, exécutés à leur date d'exécution — revue R4, R2-NEW-03) ;
                           commandes attribuées = commandes enregistrées par le moteur (contribution plafonnée)
Stock au coût historique   réceptions adossées à ``POST /stock/receive`` (autre jeton), coût à ± 2 % d'une
                           référence du moteur (facture enregistrée aux quantités rapprochées, sinon coût rendu de
                           l'offre avec des frais de la propriétaire), sinon propriétaire ; sorties de vente
                           dérivées des commandes enregistrées (CMP ; en attente sans stock valorisé : photo
                           signalée incomplète, revue R5) ; retours : lignes d'avoir + retour physique
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
from collections.abc import Callable, Iterable, Mapping
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
from .predrop import PREDROP_DEBT_LABEL
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
    "BalanceStatementBook",
    "ReceivablesStatement",
    "AdsActivityRegister",
    "ActivityRegisterError",
    "ActivityRegisterPersistenceError",
    "PhotoSourcesError",
    "build_activity_photo",
    "derive_attributed",
    "executed_ad_payments",
    "committed_ad_payments",
    "merge_ad_spends",
    "UNASSIGNED_CAMPAIGN",
    "UNKNOWN_EXTENSION",
    "FUTURE_SKEW",
]

UNKNOWN_EXTENSION = "INCONNUE"
"""Extension d'un stock absent du catalogue validé : comptée à part (jamais ignorée)."""
FUTURE_SKEW = timedelta(minutes=5)
OWNER_ACTOR = "propriétaire"
"""Acteur journalisé d'un relevé de la propriétaire (seul à faire compter des créances)."""
UNASSIGNED_CAMPAIGN = "paiement-pub-sans-campagne"
"""Campagne d'un paiement pub exécuté sans ``campaign_id`` (compté à part, jamais ignoré)."""


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

    ``preorders_collected_chf`` : précommandes encaissées non livrées **hors réservations pré-drop** (dette envers les
    clients, déduite du cash disponible ; les réservations pré-drop sont dérivées du registre du moteur et ajoutées
    par la photo, :mod:`pokeshop.predrop`) ; ``debts`` : factures reçues non payées, TVA due, remboursements promis… ;
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


class ReceivablesStatement(FrozenModel):
    """Créances à date relevées par la **propriétaire** seule (revue R5, R4-NEW-02 / R4-DOC-01).

    Registre **distinct** de la déclaration des dettes : une déclaration de dettes d'un rôle (agent 05, connecteur de
    trésorerie) ne les efface jamais ; elles restent en vigueur jusqu'au prochain relevé de créances de la
    propriétaire (``receivables: []`` les retire). Versements PSP en transit, TVA à récupérer, stock payé en transit
    (au coût, à retirer dès sa réception au coût).
    """

    as_of: datetime
    receivables: tuple[BalanceItem, ...] = ()
    source: str = Field(min_length=3)
    recorded_by: Literal["propriétaire"] = "propriétaire"

    @field_validator("as_of")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "as_of")


class BalanceStatementBook:
    """Déclaration des dettes et relevé des créances en vigueur (journal ``balance_statements``, ajout seul).

    Revue R5 (R3-NEW-02 partiel, R4-NEW-02, R4-DOC-01) : deux registres **séparés et persistés** — dettes et
    précommandes (rôles ``finance-pricing``, ``connecteur-tresorerie`` ou propriétaire) ; créances (propriétaire
    seule). Relus au démarrage : le **plancher des dettes** (un rôle ne les abaisse jamais) survit au redémarrage.
    Journal illisible => service gelé (fermé par défaut).
    """

    STREAM = "balance_statements"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._debts: BalanceStatement | None = None
        self._receivables: ReceivablesStatement | None = None
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> BalanceStatementBook:
        """Relit le registre (:class:`ActivityRegisterPersistenceError` s'il est illisible)."""
        book = cls()
        for n, record in enumerate(_load(store, "dettes et créances"), start=1):
            try:
                if record.get("debts") is not None:
                    book._debts = BalanceStatement.model_validate(record["debts"])
                if record.get("receivables") is not None:
                    book._receivables = ReceivablesStatement.model_validate(record["receivables"])
                if record.get("debts") is None and record.get("receivables") is None:
                    raise KeyError("debts/receivables")
            except (KeyError, TypeError, AttributeError, ValidationError) as exc:
                raise ActivityRegisterPersistenceError(f"dettes et créances : enregistrement {n} illisible") from exc
        book._store = store
        return book

    @property
    def debts(self) -> BalanceStatement | None:
        """Déclaration des dettes et précommandes en vigueur (None : jamais déclarée)."""
        with self._lock:
            return self._debts

    @property
    def receivables(self) -> ReceivablesStatement | None:
        """Relevé des créances de la propriétaire en vigueur (None : aucune créance relevée)."""
        with self._lock:
            return self._receivables

    def record(self, *, debts: BalanceStatement | None = None, receivables: ReceivablesStatement | None = None) -> None:
        """Enregistre (un seul enregistrement, écrit d'abord) puis met en vigueur la ou les déclarations fournies."""
        if debts is None and receivables is None:
            raise ActivityRegisterError("rien à enregistrer : dettes ou créances attendues")
        with self._lock:
            _append(
                self._store,
                {"debts": None if debts is None else debts.model_dump(mode="json"),
                 "receivables": None if receivables is None else receivables.model_dump(mode="json")},
                "dettes et créances",
            )  # fmt: skip
            if debts is not None:
                self._debts = debts
            if receivables is not None:
                self._receivables = receivables


# --------------------------------------------------------------------------- publicité


class AdsActivityRegister:
    """Dépenses publicitaires par campagne et par jour, commandes attribuées (journal ``ads_activity``).

    Revue R3 (R2-NEW-03) : **ajout seul** — une dépense déjà relevée pour (campagne, jour) ne baisse jamais
    (409) ; une hausse (correction du connecteur) est admise. Une commande attribuée doit être une commande
    **enregistrée par le moteur** (:class:`pokeshop.northstar.OrderRegister`) : statut et contribution sont
    plafonnés par ses données (jamais une contribution déclarée plus favorable) ; une commande ne redevient
    jamais « payée » après annulation ou remboursement. Le déposant (déduit du jeton) est journalisé. Revue R6
    (R5-NEW-01) : le plafond retire le **coût des ventes** du registre de coûts du moteur, et la photo re-dérive la
    contribution à chaque fois (:func:`derive_attributed` ; coût des ventes inconnu : 0).
    """

    STREAM = "ads_activity"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._spends: dict[tuple[str, date], AdSpend] = {}
        self._orders: dict[str, AttributedOrder] = {}
        self._posters: set[str] = set()
        self._last: dict[str, datetime] = {}
        self._store = store
        self.last_set_aside: dict[str, str] = {}
        """Commandes attribuées écartées du dernier lot -> motif (revue R5 : jamais les dépenses du lot)."""

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
            poster = record.get("recorded_by")
            name = poster if isinstance(poster, str) else "inconnu"
            register._posters.add(name)
            try:
                at = datetime.fromisoformat(record["recorded_at"]) if record.get("recorded_at") else None
            except (TypeError, ValueError):
                at = None
            if at is not None and at.tzinfo is not None:
                register._last[name] = max(register._last.get(name, at), at)
        register._store = store
        return register

    def _apply(self, spends: Iterable[AdSpend], orders: Iterable[AttributedOrder]) -> None:
        for s in spends:
            current = self._spends.get((s.campaign_id, s.day))
            if current is None or s.amount >= current.amount:  # ajout seul : jamais de baisse
                self._spends[(s.campaign_id, s.day)] = s
        for o in orders:
            self._orders[o.order_id] = o

    def _checked_orders(
        self, orders: list[AttributedOrder], order_book: Any, costs: Any = None
    ) -> tuple[list[AttributedOrder], dict[str, str]]:
        """Commandes attribuées admises (plafonnées par le registre des commandes) et commandes **écartées** -> motif.

        Revue R5 (R4-NEW-01) : une commande inconnue du moteur (pas encore enregistrée par ``POST /orders/shipped``)
        ou en conflit est écartée **seule** — jamais les dépenses du lot (le stop-loss pub ne perd aucune dépense) ;
        le connecteur la renvoie à son prochain relevé.

        Revue R6 (R5-NEW-01) : contribution retenue = min(déclarée, **dérivée** : ventes nettes − avoirs − frais −
        logistique réelle − coût des ventes du registre de coûts ``costs``). Coût des ventes encore inconnu (en
        attente) : plafond hors coût des ventes ici, et la photo re-dérive à chaque fois (:func:`derive_attributed`).
        """
        out: list[AttributedOrder] = []
        aside: dict[str, str] = {}
        for o in orders:
            known = order_book.get(o.order_id) if order_book is not None else None
            if known is None:
                aside[o.order_id] = (
                    "inconnue du moteur : seules les commandes enregistrées (POST /orders/shipped) sont attribuées à une "
                    "campagne — à renvoyer au prochain relevé"
                )
                continue
            status = o.status
            if order_book.status(o.order_id) == "REFUNDED":
                status = "REFUNDED"
            bound = order_book.contribution_bound(o.order_id)
            cogs = order_book.order_cogs(o.order_id, costs) if costs is not None and bound is not None else None
            if cogs is not None:  # revue R6 (R5-NEW-01) : coût des ventes du moteur, jamais ignoré
                bound = min(bound - cogs, bound)
            contribution = min(o.contribution_before_acquisition, bound) if bound is not None else Decimal("0")
            previous = self._orders.get(o.order_id)
            if previous is not None:
                if previous.status != "PAID" and status == "PAID":
                    aside[o.order_id] = f"redevient « payée » après {previous.status} (refusé)"
                    continue
                if previous.campaign_id != o.campaign_id:
                    aside[o.order_id] = f"déjà attribuée à {previous.campaign_id}"
                    continue
                contribution = min(contribution, previous.contribution_before_acquisition)
            out.append(o.model_copy(update={"status": status, "contribution_before_acquisition": contribution}))
        return out, aside

    def record(
        self,
        spends: list[AdSpend],
        orders: list[AttributedOrder],
        *,
        today: date,
        recorded_by: str = "inconnu",
        order_book: Any = None,
        recorded_at: datetime | None = None,
        costs: Any = None,
    ) -> int:
        """Enregistre un lot (contrôlé, écrit d'abord) ; renvoie le nombre d'éléments reçus.

        ``order_book`` : registre des commandes du moteur (``get``, ``status``, ``contribution_bound``,
        ``order_cogs``) ; sans lui, aucune commande attribuée n'est admise. ``costs`` : registre de coûts du moteur
        (coût des ventes de la commande, revue R6). Commandes écartées : :attr:`last_set_aside`.
        """
        if any(s.day > today for s in spends):
            raise ActivityRegisterError("dépense publicitaire datée du futur")
        keys = [(s.campaign_id, s.day) for s in spends]
        if len(set(keys)) != len(keys):
            raise ActivityRegisterError("dépense publicitaire en double (campagne, jour) dans le lot")
        with self._lock:
            for s in spends:
                current = self._spends.get((s.campaign_id, s.day))
                if current is not None and s.amount < current.amount:
                    raise ActivityRegisterError(
                        f"dépense {s.campaign_id} du {s.day} déjà relevée à {current.amount} CHF : une baisse "
                        f"({s.amount}) est refusée (registre en ajout seul ; correction : la propriétaire)"
                    )
            checked, aside = self._checked_orders(list(orders), order_book, costs)
            self.last_set_aside = aside
            _append(
                self._store,
                {"ad_spends": [s.model_dump(mode="json") for s in spends],
                 "attributed_orders": [o.model_dump(mode="json") for o in checked],
                 "recorded_by": recorded_by,
                 "recorded_at": recorded_at.isoformat() if recorded_at is not None else None},
                "activité publicitaire",
            )  # fmt: skip
            self._apply(spends, checked)
            self._posters.add(recorded_by)
            if recorded_at is not None:
                self._last[recorded_by] = max(self._last.get(recorded_by, recorded_at), recorded_at)
        return len(spends) + len(checked)

    def posters(self) -> frozenset[str]:
        """Déposants (déduits du jeton) de l'activité publicitaire."""
        with self._lock:
            return frozenset(self._posters)

    def last_recorded_at(self, poster: str) -> datetime | None:
        """Dernier relevé déposé par ``poster`` (None si jamais) : fraîcheur du connecteur publicitaire."""
        with self._lock:
            return self._last.get(poster)

    def window(self, since: date) -> tuple[tuple[AdSpend, ...], tuple[AttributedOrder, ...]]:
        """Dépenses et commandes depuis ``since`` (jour civil inclus)."""
        with self._lock:
            spends = tuple(s for (_, d), s in sorted(self._spends.items()) if d >= since)
            orders = tuple(o for _, o in sorted(self._orders.items()) if o.paid_at.date() >= since)
        return spends, orders


def derive_attributed(
    orders: Iterable[AttributedOrder], order_book: Any, costs: Any
) -> tuple[tuple[AttributedOrder, ...], tuple[str, ...]]:
    """Commandes attribuées **re-dérivées des registres du moteur** à chaque photo ; (commandes, coût inconnu).

    Revue R6 (R5-NEW-01) : contribution = min(valeur relevée, contribution dérivée du registre des commandes et du
    registre de coûts : ventes nettes − avoirs − frais − logistique réelle − coût des ventes net). Coût des ventes
    inconnu (en attente, ligne non rattachée) : **0** et commande listée (photo incomplète par ailleurs) ; commande
    remboursée en totalité depuis le relevé : ``REFUNDED``. Sans registre des commandes : contribution 0 (fermé).
    """
    out: list[AttributedOrder] = []
    unknown_cogs: list[str] = []
    for o in orders:
        derived = order_book.derived_contribution(o.order_id, costs) if order_book is not None else None
        status = o.status
        if order_book is not None and status == "PAID" and order_book.status(o.order_id) == "REFUNDED":
            status = "REFUNDED"
        cogs_known = order_book is not None and order_book.order_cogs(o.order_id, costs) is not None
        if not cogs_known:
            unknown_cogs.append(o.order_id)
        contribution = min(o.contribution_before_acquisition, derived) if derived is not None else Decimal("0")
        out.append(o.model_copy(update={"status": status, "contribution_before_acquisition": contribution}))
    return tuple(out), tuple(sorted(unknown_cogs))


def executed_ad_payments(entries: Iterable[Any], tz: Any) -> dict[tuple[str, date], Decimal]:
    """Paiements publicitaires **exécutés** du registre du mandat, par (campagne, jour civil dans ``tz``).

    ``entries`` : :class:`pokeshop.mandate.SpendEntry` ; seules les dépenses ``ADVERTISING`` au statut
    ``EXECUTED`` avec montant et date d'exécution comptent ; sans campagne : :data:`UNASSIGNED_CAMPAIGN`.
    """
    out: dict[tuple[str, date], Decimal] = {}
    for e in entries:
        request = getattr(e, "request", None)
        status = getattr(getattr(e, "status", None), "value", getattr(e, "status", None))
        category = getattr(getattr(request, "category", None), "value", None)
        if status != "EXECUTED" or category != "ADVERTISING":
            continue
        at, amount = getattr(e, "executed_at", None), getattr(e, "executed_amount_chf", None)
        if at is None or amount is None:
            continue
        key = (getattr(request, "campaign_id", None) or UNASSIGNED_CAMPAIGN, at.astimezone(tz).date())
        out[key] = out.get(key, Decimal("0")) + Decimal(amount)
    return out


def committed_ad_payments(entries: Iterable[Any], tz: Any) -> dict[tuple[str, date], Decimal]:
    """Paiements publicitaires **engagés** du registre du mandat, par (campagne, jour civil dans ``tz``).

    Revue R4 (R2-NEW-03) : aucune route ne marque encore un paiement « exécuté » ; ne compter que les
    exécutés laissait le stop-loss pub aveugle. Comptent donc (fermé par défaut) :

    * ``EXECUTED`` : montant et date d'exécution ;
    * ``APPROVED`` (dans le mandat) et ``HUMAN_APPROVED`` (validé par la propriétaire) : montant de la
      demande en CHF, à la date de la décision (validation humaine si elle existe) — un engagement compte
      dès qu'il est pris.

    Sans campagne : :data:`UNASSIGNED_CAMPAIGN`. Refusé, en attente, annulé ou expiré : ne compte pas.
    """
    entries = tuple(entries)  # parcouru deux fois (exécutés, puis engagés non exécutés)
    out = executed_ad_payments(entries, tz)
    for e in entries:
        request = getattr(e, "request", None)
        status = getattr(getattr(e, "status", None), "value", getattr(e, "status", None))
        category = getattr(getattr(request, "category", None), "value", None)
        if status not in ("APPROVED", "HUMAN_APPROVED") or category != "ADVERTISING":
            continue
        decision = getattr(e, "decision", None)
        at = getattr(e, "human_decided_at", None) or getattr(decision, "decided_at", None)
        amount = getattr(decision, "amount_chf", None)
        if at is None or amount is None:
            continue
        key = (getattr(request, "campaign_id", None) or UNASSIGNED_CAMPAIGN, at.astimezone(tz).date())
        out[key] = out.get(key, Decimal("0")) + Decimal(amount)
    return out


def merge_ad_spends(
    spends: Iterable[AdSpend], executed: dict[tuple[str, date], Decimal], *, until: date
) -> tuple[AdSpend, ...]:
    """Dépense retenue par (campagne, jour) = MAX(déclaration du connecteur, paiements engagés du mandat).

    L'agent qui dépense ne peut donc jamais faire baisser la dépense prise en compte par le stop-loss pub
    sous ce qui a réellement été payé (séparation des rôles, revue R3).
    """
    merged: dict[tuple[str, date], Decimal] = {}
    for s in spends:
        key = (s.campaign_id, s.day)
        merged[key] = max(merged.get(key, Decimal("0")), s.amount)
    for key, amount in executed.items():
        if key[1] <= until:
            merged[key] = max(merged.get(key, Decimal("0")), amount)
    return tuple(AdSpend(campaign_id=c, day=d, amount=a) for (c, d), a in sorted(merged.items()))


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
    invoices: Any = None,
    receivables: ReceivablesStatement | None = None,
    balances_max_age: timedelta | None = None,
    incomplete: Mapping[str, str] | None = None,
    order_book: Any = None,
    predrop_debts: Callable[[datetime], Any] | None = None,
) -> tuple[StopLossState, dict[str, Any]]:
    """Photo d'activité tirée des registres ; :class:`PhotoSourcesError` si une source manque ou est périmée.

    ``as_of`` de la photo = date du **plus ancien relevé de cash** (PayPal, banque, relevés horaires du connecteur) :
    une photo n'est jamais plus fraîche que son cash, et le mandat (< 60 min) juge la fraîcheur sur elle.

    Revue R5 (R4-DOC-10) : la déclaration des **dettes** (quotidienne, agent 05) a son **âge accepté explicite**
    ``balances_max_age`` (défaut : ``max_age``, soit ``state_max_age_hours`` du stop-loss signé, 24 h) et n'entre pas
    dans la date de la photo ; plus ancienne : pas de photo. Le plancher des factures enregistrées non payées est,
    lui, toujours à jour. Revue R4 (R3-NEW-02) et R5 (R4-NEW-02, R4-DOC-01) : dettes = dettes déclarées + factures
    enregistrées non payées ; créances = relevé **distinct** de la propriétaire (``receivables``), jamais effacé par
    une déclaration de dettes d'un rôle. ``incomplete`` : motifs d'étoile polaire incomplète (coût des ventes en
    attente, revue R5, R4-NEW-01), reportés dans les sources (dépenses : validation humaine). ``order_book`` :
    registre des commandes du moteur — contribution des commandes attribuées re-dérivée avec le coût des ventes du
    registre de coûts (revue R6, R5-NEW-01) ; absent : contribution 0 (fermé par défaut).

    Pré-drop (6.10.2026) : ``predrop_debts(as_of)`` renvoie l'argent encaissé en pré-drop (payé au plus tard à la date de
    la photo) ni expédié ni remboursé (:meth:`pokeshop.predrop.PredropRegistry.outstanding_debt`) ; il est **dérivé** du
    registre, ajouté aux précommandes déclarées (``preorders_collected_chf`` = précommandes **hors** pré-drop) dans les
    dettes, et déduit du cash disponible.
    """
    _aware(now, "now")
    problems: list[str] = []
    readings: list[tuple[str, datetime]] = []
    for label, reading, route in (
        ("solde PayPal", paypal, "POST /treasury/paypal-balance, connecteur"),
        ("solde bancaire", bank, "POST /treasury/bank-balance, connecteur"),
    ):
        if reading is None:
            problems.append(f"{label} non relevé ({route})")
            continue
        if reading.as_of - now > FUTURE_SKEW:
            problems.append(f"{label} : daté du futur ({reading.as_of.isoformat()})")
        elif now - reading.as_of > max_age:
            problems.append(f"{label} : périmé, du {reading.as_of.isoformat()} (> {max_age})")
        readings.append((label, reading.as_of))
    debts_age = max_age if balances_max_age is None else balances_max_age
    if balances is None:
        problems.append(
            "déclaration des dettes et créances absente (POST /treasury/balance-items : précommandes encaissées, "
            "factures non payées, TVA… ; listes vides si aucune)"
        )
    elif balances.as_of - now > FUTURE_SKEW:
        problems.append(f"déclaration des dettes : datée du futur ({balances.as_of.isoformat()})")
    elif now - balances.as_of > debts_age:
        problems.append(
            f"déclaration des dettes et créances : périmée, du {balances.as_of.isoformat()} (âge accepté {debts_age}, "
            "déclaration quotidienne de l'agent 05)"
        )
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
    predrop = predrop_debts(as_of) if predrop_debts is not None else None
    predrop_total = Decimal(getattr(predrop, "total_chf", Decimal("0"))) if predrop is not None else Decimal("0")
    if predrop_total > 0:  # dette dérivée du registre du pré-drop, jamais déclarée
        debts = (*debts, BalanceItem(label=PREDROP_DEBT_LABEL, amount=predrop_total))
    preorders = balances.preorders_collected_chf + predrop_total
    unpaid = invoices.unpaid(paid_until=as_of) if invoices is not None else ()  # paiement compté si le cash l'a vu
    debts = (
        *debts,
        *(BalanceItem(label=f"Facture fournisseur {inv.invoice_ref} non payée (registre du moteur)", amount=remaining)
          for inv, remaining in unpaid),
    )  # fmt: skip
    owner_statement = balances.recorded_by == OWNER_ACTOR
    if receivables is not None:  # registre distinct de la propriétaire (revue R5)
        counted = receivables.receivables if receivables.recorded_by == OWNER_ACTOR else ()
        ignored = len(balances.receivables) if not owner_statement else 0
    else:  # appel sans registre distinct : créances de la déclaration seulement si elle vient de la propriétaire
        counted = balances.receivables if owner_statement else ()
        ignored = 0 if owner_statement else len(balances.receivables)
    receivable_items = counted

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
        # Revue R4 (R3-NEW-01) : marge émise sous **toutes** les clés de la référence (entrée ancienne incohérente :
        # product_id ≠ listing.product_key) ; le blocage du stop-loss produit vaut ainsi pour chacune.
        for k in sorted({key, entry.product_id} - seen):
            margins.append(
                ProductMargin(product_key=k, extension=str(listing_ext) if listing_ext else None, contribution_chf=chf,
                              contribution_pct=pct, small_product=small)
            )  # fmt: skip
            seen.add(k)

    spends, attributed = ads.window(as_of.date() - timedelta(days=ads_window_days))
    # Revue R6 (R5-NEW-01) : contribution de chaque commande attribuée re-dérivée des registres du moteur.
    attributed, attributed_cogs_unknown = derive_attributed(
        (o for o in attributed if o.paid_at <= as_of), order_book, costs
    )
    state = StopLossState(
        as_of=as_of,
        products=tuple(margins),
        extensions=extensions,
        stock_budget_chf=stock_budget_chf,
        ad_spends=tuple(s for s in spends if s.day <= as_of.date()),
        attributed_orders=attributed,
        ads_daily_cap_chf=ads_daily_cap_chf,
        cash_available_chf=cash - preorders,
        capital_movements=movements,
        net_worth=NetWorthSnapshot(
            as_of=as_of, cash_chf=cash, stock=tuple(stock), receivables=receivable_items, debts=debts
        ),
    )
    reasons = dict(incomplete or {})
    for oid in attributed_cogs_unknown:  # revue R6 (R5-NEW-01) : fermé par défaut, jamais silencieux
        reasons.setdefault(
            f"commande {oid}",
            "commande attribuée à une campagne sans coût des ventes connu au registre du moteur : contribution 0",
        )
    sources = {
        "as_of": as_of,
        "cash": {"paypal": {"as_of": paypal.as_of, "recorded_by": paypal.recorded_by},
                 "banque": {"as_of": bank.as_of, "recorded_by": bank.recorded_by}},
        "dettes_creances": {"as_of": balances.as_of, "recorded_by": balances.recorded_by,
                            "age_minutes": int((now - balances.as_of).total_seconds() // 60),
                            "max_age_minutes": int(debts_age.total_seconds() // 60),
                            "debts": len(debts), "receivables": len(receivable_items),
                            "receivables_as_of": receivables.as_of if receivables is not None else None,
                            "receivables_recorded_by": receivables.recorded_by if receivables is not None else None,
                            "receivables_ignored": ignored,
                            "unpaid_invoices": [inv.invoice_ref for inv, _ in unpaid]},
        # Revue R5 (R4-NEW-01) : coût des ventes en attente => étoile polaire et photo incomplètes (dépenses : humain).
        "complete": not reasons,
        "incomplete": reasons,
        # Pré-drop : précommandes déclarées (hors pré-drop) + réservations pré-drop dérivées du registre du moteur.
        "precommandes": {"declarees_chf": balances.preorders_collected_chf, "predrop_derivees_chf": predrop_total,
                         "predrop_reservations": int(getattr(predrop, "reservations", 0) or 0),
                         "total_chf": preorders},
        "capital_movements": len(movements),
        "stock_lines": len(stock),
        "extensions": [e.extension for e in extensions],
        "product_margins": len(margins),
        "ad_spends": len(state.ad_spends),
        "attributed_orders": len(state.attributed_orders),
        # Revue R6 (R5-NEW-01) : commandes attribuées dont le coût des ventes est inconnu (contribution retenue : 0).
        "attributed_orders_cost_of_sales_unknown": list(attributed_cogs_unknown),
    }  # fmt: skip
    return state, sources
