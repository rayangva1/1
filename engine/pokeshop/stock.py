"""Stock vendable, précommandes, péremption, réservations et propositions de réassort (BP §5).

Principes appliqués :

* Un stock fournisseur ne devient jamais un stock boutique : seule la quantité locale
  disponible (après réservations, dommages et sécurité) est promise comme expédiable.
* Précommande = allocation **ferme** confirmée − précommandes engagées − réserve.
* Donnée amont > 24 h : bloque achats et nouvelles promesses, pas la vente du stock local.
* Offres pouvant partager le même stock amont : jamais additionnées.
* Le réassort produit une **proposition à valider**, jamais une commande.

Note d'architecture (BP §6) : Shopify reste l'autorité des réservations de vente. Le
:class:`StockRegistry` est le modèle du service (mouvements, rapprochements, tests de
concurrence) ; il applique le même contrôle compare-and-set que ``inventorySetQuantities``.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from .audit import StateJournal, StateStoreError
from .errors import ConcurrencyError, InsufficientStockError, InvalidStateError, ReservationNotFoundError, StockError
from .models import (
    AvailabilityPromise,
    AvailabilityStatus,
    MovementKind,
    PromiseKind,
    ReorderCandidate,
    ReorderLine,
    ReorderProposal,
    ReorderSkip,
    Reservation,
    ReservationStatus,
    StockLevel,
    StockMovement,
    SupplierOffer,
    canonical_hash,
)

__all__ = [
    "DEFAULT_MAX_AGE",
    "sellable_local",
    "preorder_quota",
    "is_stale",
    "pooled_quantity",
    "availability_promise",
    "StockRegistry",
    "PersistentStockRegistry",
    "StockPersistenceError",
    "reorder_point",
    "REORDER_SKIP_REASONS",
    "propose_reorder",
]

DEFAULT_MAX_AGE = timedelta(hours=24)
DEFAULT_FUTURE_SKEW = timedelta(minutes=5)
ZERO = Decimal("0")
CENT = Decimal("0.01")


def _check_count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} doit être un entier")
    if value < 0:
        raise StockError(f"{name} négatif ({value})")
    return value


def sellable_local(on_hand: int, reserved: int, damaged: int, safety: int) -> int:
    """Stock local vendable = physique − réservé − endommagé − sécurité, jamais < 0 (BP §5)."""
    total = _check_count(on_hand, "on_hand")
    out = _check_count(reserved, "reserved") + _check_count(damaged, "damaged") + _check_count(safety, "safety")
    return max(0, total - out)


def preorder_quota(firm_allocation: int, committed_preorders: int, safety: int) -> int:
    """Quota de précommande = allocation ferme − précommandes engagées − réserve, jamais < 0."""
    alloc = _check_count(firm_allocation, "firm_allocation")
    used = _check_count(committed_preorders, "committed_preorders") + _check_count(safety, "safety")
    return max(0, alloc - used)


def _require_aware(ts: datetime, name: str) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise StockError(f"{name} doit porter un fuseau horaire (datetime naïf refusé)")


def is_stale(
    source_ts: datetime,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
    *,
    future_skew: timedelta = DEFAULT_FUTURE_SKEW,
) -> bool:
    """Vrai si la donnée amont a **plus** de ``max_age`` (24 h par défaut ; exactement 24 h = fraîche).

    Un horodatage dans le futur au-delà de ``future_skew`` (5 min) est jugé non fiable,
    donc périmé. Les datetimes naïfs sont refusés.
    """
    _require_aware(source_ts, "source_ts")
    _require_aware(now, "now")
    if max_age <= timedelta(0):
        raise StockError("max_age doit être positif")
    age = now - source_ts
    if age < -future_skew:
        return True
    return age > max_age


def _upstream_qty(offer: SupplierOffer, field: str) -> int:
    value = getattr(offer, field)
    return 0 if value is None else int(value)


def pooled_quantity(offers: Sequence[SupplierOffer], field: str = "allocation_qty") -> int:
    """Quantité amont totale **sans double comptage** des stocks partagés.

    Offres d'un même ``stock_pool_id`` : on retient le maximum (même stock). Pools
    explicitement distincts : additionnés. Offres sans pool (stock potentiellement partagé
    avec n'importe quelle autre) : jamais additionnées — résultat = max(somme des pools
    déclarés, plus grande offre sans pool).
    """
    if field not in ("allocation_qty", "available_qty"):
        raise StockError(f"champ non agrégeable : {field}")
    pools: dict[str, int] = {}
    unknown = 0
    for offer in offers:
        qty = _upstream_qty(offer, field)
        if offer.stock_pool_id is None:
            unknown = max(unknown, qty)
        else:
            pools[offer.stock_pool_id] = max(pools.get(offer.stock_pool_id, 0), qty)
    return max(sum(pools.values()), unknown)


def _offer_label(offer: SupplierOffer) -> str:
    return f"{offer.supplier_id}/{offer.supplier_sku}"


def availability_promise(
    *,
    local_sellable: int,
    offers: Sequence[SupplierOffer] = (),
    now: datetime,
    committed_preorders: int = 0,
    preorder_safety: int = 0,
    preorders_enabled: bool = False,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> AvailabilityPromise:
    """Calcule la promesse de disponibilité d'un produit (BP §5).

    * Stock local vendable > 0 -> ``LOCAL_STOCK`` (seule promesse « expédié depuis Genève »).
    * Sinon, précommande seulement si activée et couverte par une allocation ferme
      d'offres **fraîches** (pools non additionnés) -> ``PREORDER``.
    * Sinon ``UNAVAILABLE``. Le stock amont non alloué ne donne qu'un ``restock_signal``
      interne ; une offre périmée est exclue (motif ``STALE_OFFER``), de même qu'une offre dont
      l'horodatage est **supposé** (source non datée : motif ``SOURCE_TS_ASSUMED``).
    """
    local = _check_count(local_sellable, "local_sellable")
    fresh: list[SupplierOffer] = []
    excluded: list[str] = []
    reasons: list[str] = []
    for offer in offers:
        if is_stale(offer.source_ts, now, max_age) or offer.source_ts_assumed:
            excluded.append(_offer_label(offer))
            code = "SOURCE_TS_ASSUMED" if offer.source_ts_assumed else "STALE_OFFER"
            if code not in reasons:
                reasons.append(code)
        else:
            fresh.append(offer)
    firm = pooled_quantity(fresh, "allocation_qty")
    unallocated = pooled_quantity(
        [o for o in fresh if o.availability_status in (AvailabilityStatus.IN_STOCK, AvailabilityStatus.LOW_STOCK)],
        "available_qty",
    )
    restock_signal = unallocated > 0 or firm > 0
    preorder_qty = preorder_quota(firm, committed_preorders, preorder_safety) if preorders_enabled else 0
    if local > 0:
        kind = PromiseKind.LOCAL_STOCK
    elif preorder_qty > 0:
        kind = PromiseKind.PREORDER
    else:
        kind = PromiseKind.UNAVAILABLE
        if unallocated > 0:
            reasons.append("UPSTREAM_STOCK_NOT_PROMISED")
        if firm > 0 and not preorders_enabled:
            reasons.append("PREORDERS_DISABLED")
        elif firm > 0:
            reasons.append("PREORDER_QUOTA_EXHAUSTED")
    return AvailabilityPromise(
        kind=kind,
        local_qty=local,
        preorder_qty=preorder_qty,
        firm_allocation=firm,
        restock_signal=restock_signal,
        reasons=tuple(reasons),
        excluded_offers=tuple(excluded),
    )


# ------------------------------------------------------------------ registry


@dataclass
class _Slot:
    on_hand: int = 0
    reserved: int = 0
    damaged: int = 0
    safety: int = 0
    version: int = 0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StockRegistry:
    """Registre en mémoire du stock local, thread-safe, avec contrôle compare-and-set.

    Chaque mutation incrémente la ``version`` du SKU. Passer ``expected_version`` (lue via
    :meth:`level`) fait échouer l'opération avec :class:`ConcurrencyError` si un autre
    acteur a modifié le SKU entre-temps : cas « dernière unité achetée simultanément ».
    Les réservations sont idempotentes par (commande, SKU) et les remboursements par
    ``refund_id`` : une reprise ne double jamais une écriture.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utcnow
        self._lock = threading.RLock()
        self._slots: dict[str, _Slot] = {}
        self._reservations: dict[str, Reservation] = {}
        self._by_order: dict[tuple[str, str], str] = {}
        self._refunds: set[str] = set()
        self._movements: list[StockMovement] = []
        self._seq = 0

    # -- lecture ------------------------------------------------------------
    def level(self, sku: str) -> StockLevel:
        """Photo courante du SKU (zéros et version 0 si inconnu)."""
        with self._lock:
            slot = self._slots.get(sku, _Slot())
            return StockLevel(
                sku=sku,
                on_hand=slot.on_hand,
                reserved=slot.reserved,
                damaged=slot.damaged,
                safety=slot.safety,
                version=slot.version,
            )

    def sellable(self, sku: str) -> int:
        """Quantité vendable locale du SKU."""
        return self.level(sku).sellable

    def reservation(self, reservation_id: str) -> Reservation:
        """Réservation par identifiant (ReservationNotFoundError si inconnue)."""
        with self._lock:
            try:
                return self._reservations[reservation_id]
            except KeyError:
                raise ReservationNotFoundError(f"Réservation inconnue : {reservation_id}") from None

    def reservations(self, order_id: str | None = None) -> tuple[Reservation, ...]:
        """Toutes les réservations (ou celles d'une commande), dans l'ordre de création."""
        with self._lock:
            items = list(self._reservations.values())
        return tuple(r for r in items if order_id is None or r.order_id == order_id)

    def movements(self, sku: str | None = None) -> tuple[StockMovement, ...]:
        """Journal append-only des mouvements (filtré par SKU si fourni)."""
        with self._lock:
            return tuple(m for m in self._movements if sku is None or m.sku == sku)

    # -- interne ------------------------------------------------------------
    def _slot(self, sku: str, expected_version: int | None) -> _Slot:
        if not sku:
            raise StockError("SKU vide")
        slot = self._slots.setdefault(sku, _Slot())
        if expected_version is not None and expected_version != slot.version:
            raise ConcurrencyError(f"{sku} : version attendue {expected_version}, courante {slot.version}")
        return slot

    def _log(self, sku: str, slot: _Slot, kind: MovementKind, qty: int, ref: str, at: datetime) -> None:
        slot.version += 1
        self._seq += 1
        self._movements.append(
            StockMovement(seq=self._seq, sku=sku, kind=kind, qty=qty, ref=ref, at=at, version_after=slot.version)
        )

    def _now(self, at: datetime | None) -> datetime:
        ts = at or self._clock()
        _require_aware(ts, "at")
        return ts

    @staticmethod
    def _positive(qty: int) -> int:
        _check_count(qty, "qty")
        if qty == 0:
            raise StockError("quantité nulle")
        return qty

    # -- mutations ----------------------------------------------------------
    def receive(
        self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None
    ) -> StockLevel:
        """Entrée en stock local (réception contrôlée physiquement)."""
        self._positive(qty)
        with self._lock:
            now = self._now(at)
            slot = self._slot(sku, expected_version)
            slot.on_hand += qty
            self._log(sku, slot, MovementKind.RECEIPT, qty, ref, now)
            return self.level(sku)

    def set_safety(
        self, sku: str, qty: int, *, ref: str = "", expected_version: int | None = None, at: datetime | None = None
    ) -> StockLevel:
        """Fixe le stock de sécurité du SKU."""
        _check_count(qty, "safety")
        with self._lock:
            now = self._now(at)
            slot = self._slot(sku, expected_version)
            slot.safety = qty
            self._log(sku, slot, MovementKind.SET_SAFETY, qty, ref, now)
            return self.level(sku)

    def reserve(
        self, sku: str, qty: int, order_id: str, *, expected_version: int | None = None, at: datetime | None = None
    ) -> Reservation:
        """Réserve ``qty`` unités pour une commande payée (atomique).

        Idempotent : une réservation ACTIVE/FULFILLED existante pour (order_id, sku) avec la
        même quantité est renvoyée telle quelle. InsufficientStockError si vendable < qty.
        """
        self._positive(qty)
        if not order_id:
            raise StockError("order_id vide")
        with self._lock:
            now = self._now(at)
            existing_id = self._by_order.get((order_id, sku))
            if existing_id is not None:
                existing = self._reservations[existing_id]
                if existing.status is not ReservationStatus.CANCELLED:
                    if existing.qty != qty:
                        raise InvalidStateError(
                            f"Commande {order_id} : réservation {existing_id} existante avec une autre quantité"
                        )
                    return existing
            slot = self._slot(sku, expected_version)
            available = max(0, slot.on_hand - slot.reserved - slot.damaged - slot.safety)
            if available < qty:
                raise InsufficientStockError(f"{sku} : vendable {available} < demandé {qty}")
            slot.reserved += qty
            res_id = f"RES-{len(self._reservations) + 1:06d}"
            reservation = Reservation(
                reservation_id=res_id,
                sku=sku,
                order_id=order_id,
                qty=qty,
                status=ReservationStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            self._reservations[res_id] = reservation
            self._by_order[(order_id, sku)] = res_id
            self._log(sku, slot, MovementKind.RESERVE, qty, f"{order_id}:{res_id}", now)
            return reservation

    def cancel(self, reservation_id: str, *, at: datetime | None = None) -> Reservation:
        """Annule une réservation active et libère le stock (idempotent si déjà annulée)."""
        with self._lock:
            now = self._now(at)
            res = self.reservation(reservation_id)
            if res.status is ReservationStatus.CANCELLED:
                return res
            if res.status is ReservationStatus.FULFILLED:
                raise InvalidStateError(f"{reservation_id} déjà expédiée : utiliser refund()")
            slot = self._slot(res.sku, None)
            slot.reserved -= res.qty
            updated = res.replace(status=ReservationStatus.CANCELLED, updated_at=now)
            self._reservations[reservation_id] = updated
            self._log(res.sku, slot, MovementKind.CANCEL, res.qty, f"{res.order_id}:{reservation_id}", now)
            return updated

    def fulfill(self, reservation_id: str, *, at: datetime | None = None) -> Reservation:
        """Sortie physique (colis remis au transporteur) : physique et réservé diminuent."""
        with self._lock:
            now = self._now(at)
            res = self.reservation(reservation_id)
            if res.status is ReservationStatus.FULFILLED:
                return res
            if res.status is ReservationStatus.CANCELLED:
                raise InvalidStateError(f"{reservation_id} annulée : expédition impossible")
            slot = self._slot(res.sku, None)
            slot.reserved -= res.qty
            slot.on_hand -= res.qty
            updated = res.replace(status=ReservationStatus.FULFILLED, updated_at=now)
            self._reservations[reservation_id] = updated
            self._log(res.sku, slot, MovementKind.FULFILL, res.qty, f"{res.order_id}:{reservation_id}", now)
            return updated

    def refund(
        self,
        reservation_id: str,
        refund_id: str,
        qty: int | None = None,
        *,
        returned: bool,
        damaged: bool = False,
        at: datetime | None = None,
    ) -> Reservation:
        """Remboursement (idempotent par ``refund_id``).

        * Réservation ACTIVE (non expédiée) : remboursement total = annulation (stock libéré).
        * FULFILLED : ``returned=True`` remet en stock ; ``damaged=True`` le compte en
          endommagé (non vendable) ; ``returned=False`` (colis perdu, geste) ne touche pas au stock.
        """
        if not refund_id:
            raise StockError("refund_id vide")
        if damaged and not returned:
            raise StockError("un article endommagé doit être retourné pour être compté")
        with self._lock:
            now = self._now(at)
            res = self.reservation(reservation_id)
            if refund_id in self._refunds:
                return res
            if res.status is ReservationStatus.CANCELLED:
                raise InvalidStateError(f"{reservation_id} déjà annulée : stock déjà libéré")
            if res.status is ReservationStatus.ACTIVE:
                if qty is not None and qty != res.qty:
                    raise InvalidStateError("remboursement partiel avant expédition : modifier la commande")
                self._refunds.add(refund_id)
                return self.cancel(reservation_id, at=now)
            n = res.qty - res.refunded_qty if qty is None else self._positive(qty)
            if n <= 0 or res.refunded_qty + n > res.qty:
                raise InvalidStateError(f"{reservation_id} : remboursement {n} > quantité restante")
            slot = self._slot(res.sku, None)
            if returned:
                slot.on_hand += n
                if damaged:
                    slot.damaged += n
                kind = MovementKind.RETURN_DAMAGED if damaged else MovementKind.RETURN_RESTOCK
            else:
                kind = MovementKind.REFUND_NO_RETURN
            updated = res.replace(refunded_qty=res.refunded_qty + n, updated_at=now)
            self._reservations[reservation_id] = updated
            self._refunds.add(refund_id)
            self._log(res.sku, slot, kind, n, f"{res.order_id}:{refund_id}", now)
            return updated

    def mark_damaged(
        self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None
    ) -> StockLevel:
        """Déclare des unités disponibles comme endommagées (retirées du vendable)."""
        self._positive(qty)
        with self._lock:
            now = self._now(at)
            slot = self._slot(sku, expected_version)
            free = slot.on_hand - slot.reserved - slot.damaged
            if qty > free:
                raise InsufficientStockError(f"{sku} : {free} unité(s) non réservée(s) seulement")
            slot.damaged += qty
            self._log(sku, slot, MovementKind.MARK_DAMAGED, qty, ref, now)
            return self.level(sku)

    def write_off_damaged(
        self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None
    ) -> StockLevel:
        """Sort définitivement des unités endommagées (destruction, retour fournisseur)."""
        self._positive(qty)
        with self._lock:
            now = self._now(at)
            slot = self._slot(sku, expected_version)
            if qty > slot.damaged:
                raise InsufficientStockError(f"{sku} : seulement {slot.damaged} unité(s) endommagée(s)")
            slot.damaged -= qty
            slot.on_hand -= qty
            self._log(sku, slot, MovementKind.WRITE_OFF, qty, ref, now)
            return self.level(sku)


class StockPersistenceError(StockError, StateStoreError):
    """Mouvement de stock non enregistré (annulé en mémoire) ou journal illisible au démarrage."""


_JOURNALED_OPS = ("receive", "set_safety", "reserve", "cancel", "fulfill", "refund", "mark_damaged", "write_off_damaged")


class PersistentStockRegistry(StockRegistry):
    """Registre du stock local dont chaque mutation est écrite dans le journal d'état ``stock_movements``.

    Chaque opération est appliquée en mémoire puis écrite ; si l'écriture échoue, l'état mémoire est
    restauré (rien n'est retenu) et :class:`StockPersistenceError` est levée. Au démarrage,
    :meth:`restore` rejoue les opérations dans l'ordre (horodatages explicites : rejeu déterministe) ;
    un journal illisible ou incohérent lève :class:`StockPersistenceError` (fermé par défaut).
    """

    STREAM = "stock_movements"

    def __init__(self, *, clock: Callable[[], datetime] | None = None, store: StateJournal | None = None) -> None:
        super().__init__(clock=clock)
        self._store = store
        self._depth = 0
        self._receipt_by: dict[tuple[str, str], str | None] = {}
        """Acteur (déduit du jeton) de chaque réception (SKU, référence) : adosse les coûts historiques (revue R3)."""

    @classmethod
    def restore(cls, store: StateJournal, *, clock: Callable[[], datetime] | None = None) -> PersistentStockRegistry:
        """Rejoue le journal (StockPersistenceError si illisible ou si une opération ne se rejoue pas)."""
        registry = cls(clock=clock)
        try:
            records = store.load()
        except StateStoreError as exc:
            raise StockPersistenceError(f"journal du stock : {exc}") from exc
        for n, record in enumerate(records, start=1):
            try:
                op = record["op"]
                if op not in _JOURNALED_OPS:
                    raise KeyError(op)
                args = dict(record["args"])
                args["at"] = datetime.fromisoformat(args["at"])
                getattr(StockRegistry, op)(registry, **args)
                if op == "receive":
                    by = record.get("by")
                    registry._receipt_by[(args["sku"], args["ref"])] = by if isinstance(by, str) else None
            except (KeyError, TypeError, ValueError, StockError) as exc:
                raise StockPersistenceError(f"journal du stock : opération {n} non rejouable ({exc})") from exc
        registry._store = store
        return registry

    def _snapshot(self) -> tuple[Any, ...]:
        return (
            copy.deepcopy(self._slots),
            dict(self._reservations),
            dict(self._by_order),
            set(self._refunds),
            len(self._movements),
            self._seq,
        )

    def _rollback(self, snap: tuple[Any, ...]) -> None:
        slots, reservations, by_order, refunds, n_movements, seq = snap
        self._slots, self._reservations, self._by_order, self._refunds = slots, reservations, by_order, refunds
        del self._movements[n_movements:]
        self._seq = seq

    def _journaled(self, op: str, args: dict[str, Any], *, by: str | None = None) -> Any:
        with self._lock:
            args["at"] = self._now(args.get("at"))
            if self._depth or self._store is None:
                self._depth += 1
                try:
                    result = getattr(StockRegistry, op)(self, **args)
                finally:
                    self._depth -= 1
                if op == "receive" and not self._depth:
                    self._receipt_by[(args["sku"], args["ref"])] = by
                return result
            snap = self._snapshot()
            self._depth += 1
            try:
                result = getattr(StockRegistry, op)(self, **args)
            finally:
                self._depth -= 1
            record: dict[str, Any] = {
                "op": op, "args": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in args.items()}
            }
            if by is not None:
                record["by"] = by
            try:
                self._store.append(record)
            except StateStoreError as exc:
                self._rollback(snap)
                raise StockPersistenceError(f"mouvement de stock non enregistré ({exc}) : rien n'est retenu") from exc
            if op == "receive":
                self._receipt_by[(args["sku"], args["ref"])] = by
            return result

    def receipt(self, sku: str, ref: str) -> tuple[int, str | None] | None:
        """Réception (SKU, référence) enregistrée : (quantité, acteur) ; None si inconnue."""
        with self._lock:
            qty = sum(m.qty for m in self._movements if m.sku == sku and m.kind is MovementKind.RECEIPT and m.ref == ref)
            if qty <= 0:
                return None
            return qty, self._receipt_by.get((sku, ref))

    def receive(self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None) -> StockLevel:
        """Voir :meth:`StockRegistry.receive` (persisté)."""
        return self._journaled("receive", {"sku": sku, "qty": qty, "ref": ref, "expected_version": expected_version, "at": at})

    def receive_once(
        self, sku: str, qty: int, ref: str, *, at: datetime | None = None, recorded_by: str | None = None
    ) -> tuple[StockLevel, bool]:
        """Réception idempotente par (SKU, référence) : (niveau, rejouée) ; autre quantité => StockError.

        ``recorded_by`` : acteur déduit du jeton, journalisé avec la réception (revue R3 : un coût historique
        de réception doit citer une réception déclarée par un **autre** jeton).
        """
        if not ref or not ref.strip():
            raise StockError("référence de réception obligatoire (bon de livraison, lot)")
        with self._lock:
            previous = [m for m in self._movements if m.sku == sku and m.kind is MovementKind.RECEIPT and m.ref == ref]
            if previous:
                if previous[0].qty != qty:
                    raise InvalidStateError(f"réception {ref} déjà enregistrée pour {sku} avec {previous[0].qty} unité(s)")
                return self.level(sku), True
            level = self._journaled(
                "receive", {"sku": sku, "qty": qty, "ref": ref, "expected_version": None, "at": at}, by=recorded_by
            )
            return level, False

    def set_safety(self, sku: str, qty: int, *, ref: str = "", expected_version: int | None = None, at: datetime | None = None) -> StockLevel:
        """Voir :meth:`StockRegistry.set_safety` (persisté)."""
        return self._journaled("set_safety", {"sku": sku, "qty": qty, "ref": ref, "expected_version": expected_version, "at": at})

    def reserve(self, sku: str, qty: int, order_id: str, *, expected_version: int | None = None, at: datetime | None = None) -> Reservation:
        """Voir :meth:`StockRegistry.reserve` (persisté)."""
        return self._journaled(
            "reserve", {"sku": sku, "qty": qty, "order_id": order_id, "expected_version": expected_version, "at": at}
        )

    def cancel(self, reservation_id: str, *, at: datetime | None = None) -> Reservation:
        """Voir :meth:`StockRegistry.cancel` (persisté)."""
        return self._journaled("cancel", {"reservation_id": reservation_id, "at": at})

    def fulfill(self, reservation_id: str, *, at: datetime | None = None) -> Reservation:
        """Voir :meth:`StockRegistry.fulfill` (persisté)."""
        return self._journaled("fulfill", {"reservation_id": reservation_id, "at": at})

    def refund(
        self,
        reservation_id: str,
        refund_id: str,
        qty: int | None = None,
        *,
        returned: bool,
        damaged: bool = False,
        at: datetime | None = None,
    ) -> Reservation:
        """Voir :meth:`StockRegistry.refund` (persisté)."""
        return self._journaled(
            "refund",
            {"reservation_id": reservation_id, "refund_id": refund_id, "qty": qty, "returned": returned,
             "damaged": damaged, "at": at},
        )  # fmt: skip

    def mark_damaged(self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None) -> StockLevel:
        """Voir :meth:`StockRegistry.mark_damaged` (persisté)."""
        return self._journaled(
            "mark_damaged", {"sku": sku, "qty": qty, "ref": ref, "expected_version": expected_version, "at": at}
        )

    def write_off_damaged(
        self, sku: str, qty: int, ref: str, *, expected_version: int | None = None, at: datetime | None = None
    ) -> StockLevel:
        """Voir :meth:`StockRegistry.write_off_damaged` (persisté)."""
        return self._journaled(
            "write_off_damaged", {"sku": sku, "qty": qty, "ref": ref, "expected_version": expected_version, "at": at}
        )


# ------------------------------------------------------------------- reorder


def reorder_point(avg_daily_sales: Decimal, lead_time_days: int | Decimal, safety: int | Decimal) -> Decimal:
    """Point de commande = ventes journalières moyennes × délai + sécurité (BP §5)."""
    if isinstance(avg_daily_sales, float) or isinstance(lead_time_days, float) or isinstance(safety, float):
        raise TypeError("float interdit : utiliser Decimal ou int")
    avg = Decimal(avg_daily_sales)
    lead = Decimal(lead_time_days)
    sec = Decimal(safety)
    if avg < 0 or lead < 0 or sec < 0:
        raise StockError("paramètres de point de commande négatifs")
    return avg * lead + sec


def _round_down_to(qty: int, multiple: int) -> int:
    return (qty // multiple) * multiple


def _round_up_to(qty: int, multiple: int) -> int:
    return -(-qty // multiple) * multiple


_UNAVAILABLE_UPSTREAM = (AvailabilityStatus.OUT_OF_STOCK, AvailabilityStatus.DISCONTINUED)

REORDER_SKIP_REASONS: dict[str, str] = {
    "STOP_LOSS_PRODUCT": "Référence gelée par le stop-loss (gouvernance) : aucun réassort.",
    "STOP_LOSS_EXTENSION": "Extension gelée par le stop-loss (> 25 % du budget ou 45 j sans vente).",
    "CASH_RESERVE": "Budget disponible ≤ réserve de trésorerie du mandat : aucun achat.",
    "STALE_OFFER": "Offre fournisseur > 24 h : inéligible au réassort.",
    "UPSTREAM_UNAVAILABLE": "Fournisseur en rupture ou référence arrêtée.",
    "UNKNOWN_FIELDS": "MOQ, carton ou statut de disponibilité inconnu.",
    "INVALID_COST": "Coût de remplacement ≤ 0 : anomalie.",
    "ABOVE_REORDER_POINT": "Position (vendable + en commande) au-dessus du point de commande.",
    "NO_PROBABLE_SALES": "Aucune vente probable sur la période couverte.",
    "INSUFFICIENT_UPSTREAM": "Quantité amont < MOQ ou < 1 carton.",
    "BUDGET": "Budget disponible insuffisant pour le MOQ / 1 carton.",
    "EXTENSION_CAP": "Plafond par extension atteint (25 % du budget stock).",
}
"""Codes stables des motifs d'exclusion d'une référence du panier de réassort."""


def _decimal_arg(value: Decimal | int | str, name: str) -> Decimal:
    """Convertit un argument monétaire/taux en Decimal fini ; ``float``/``bool`` refusés."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{name} : {type(value).__name__} interdit, utiliser Decimal ou str")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise StockError(f"{name} : valeur décimale invalide {value!r}") from exc
    if not result.is_finite():
        raise StockError(f"{name} : valeur non finie")
    return result


def propose_reorder(
    candidates: Sequence[ReorderCandidate],
    *,
    budget_available: Decimal,
    stock_budget_total: Decimal,
    now: datetime,
    extension_exposure: Mapping[str, Decimal] | None = None,
    extension_cap_pct: Decimal = Decimal("0.25"),
    cap_exceptions: Mapping[str, Decimal] | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
    rules_version: str = "unversioned",
    blocked_extensions: Collection[str] = (),
    blocked_products: Collection[str] = (),
    cash_reserve_chf: Decimal = ZERO,
) -> ReorderProposal:
    """Prépare un **panier fournisseur à valider** (jamais une commande, BP §5).

    Pour chaque candidat (le plus urgent d'abord : jours de couverture croissants) :
    référence/extension gelée par le stop-loss -> écartée ; offre périmée / statut
    indisponible ou inconnu / MOQ ou carton inconnu -> écartée ; position (vendable + en
    commande) > point de commande -> écartée ; sinon quantité = ventes probables (délai +
    ``coverage_days``) + sécurité − position, relevée au MOQ, arrondie au carton supérieur,
    puis réduite (par cartons, sans passer sous le MOQ) par la quantité amont connue, le
    budget utilisable et le plafond par extension (``extension_cap_pct`` ×
    ``stock_budget_total``, 25 % par défaut ; exceptions documentées via ``cap_exceptions``).

    * ``extension_exposure`` : valeur au coût déjà engagée par extension.
    * ``blocked_extensions`` / ``blocked_products`` : gels décidés par le stop-loss
      (``pokeshop.stoploss``, agent gouvernance) ; motif ``STOP_LOSS_*``.
    * ``cash_reserve_chf`` : réserve de trésorerie du mandat (BP §3 : 1 600 CHF), jamais
      engagée : budget utilisable = ``budget_available`` − réserve (≤ 0 => motif
      ``CASH_RESERVE`` pour toutes les références). Défaut 0 = l'appelant a déjà déduit la
      réserve. Le stop-loss cash de la gouvernance reste l'autorité.

    Motifs d'exclusion : :data:`REORDER_SKIP_REASONS`. Montants : ``Decimal`` ou ``str``
    (``float`` refusé).
    """
    _require_aware(now, "now")
    budget = _decimal_arg(budget_available, "budget_available")
    total_budget = _decimal_arg(stock_budget_total, "stock_budget_total")
    reserve = _decimal_arg(cash_reserve_chf, "cash_reserve_chf")
    cap_pct_default = _decimal_arg(extension_cap_pct, "extension_cap_pct")
    if budget < 0 or total_budget < 0:
        raise StockError("budget négatif")
    if reserve < 0:
        raise StockError("réserve de trésorerie négative")
    if not ZERO < cap_pct_default <= 1:
        raise StockError("plafond par extension hors ]0, 1]")
    keys = [c.product_key for c in candidates]
    if len(set(keys)) != len(keys):
        raise StockError("product_key en double dans les candidats")
    if isinstance(blocked_extensions, str) or isinstance(blocked_products, str):
        raise TypeError("blocked_extensions / blocked_products : collection de chaînes attendue")
    frozen_ext = frozenset(blocked_extensions)
    frozen_products = frozenset(blocked_products)
    exposure: dict[str, Decimal] = {
        k: _decimal_arg(v, f"extension_exposure[{k}]") for k, v in (extension_exposure or {}).items()
    }
    exceptions = {k: _decimal_arg(v, f"cap_exceptions[{k}]") for k, v in (cap_exceptions or {}).items()}
    for ext, pct in exceptions.items():
        if not ZERO < pct <= 1:
            raise StockError(f"exception de plafond invalide pour {ext}")
    exposure_in = dict(exposure)
    usable = budget - reserve

    def cover_days(c: ReorderCandidate) -> Decimal:
        position = Decimal(c.sellable_qty + c.on_order_qty)
        return position / c.avg_daily_sales if c.avg_daily_sales > 0 else Decimal("Infinity")

    ordered = sorted(candidates, key=lambda c: (cover_days(c), c.product_key))
    remaining = usable if usable > 0 else ZERO
    lines: list[ReorderLine] = []
    skipped: list[ReorderSkip] = []
    for c in ordered:
        offer = c.offer
        if c.product_key in frozen_products:
            skipped.append(ReorderSkip(product_key=c.product_key, reason="STOP_LOSS_PRODUCT"))
            continue
        if c.extension in frozen_ext:
            skipped.append(ReorderSkip(product_key=c.product_key, reason="STOP_LOSS_EXTENSION", detail=c.extension))
            continue
        if usable <= 0:
            skipped.append(
                ReorderSkip(
                    product_key=c.product_key, reason="CASH_RESERVE", detail=f"budget {budget} ≤ réserve {reserve}"
                )
            )
            continue
        if is_stale(offer.source_ts, now, max_age):
            skipped.append(ReorderSkip(product_key=c.product_key, reason="STALE_OFFER", detail="offre > 24 h"))
            continue
        if offer.availability_status in _UNAVAILABLE_UPSTREAM:
            skipped.append(
                ReorderSkip(
                    product_key=c.product_key, reason="UPSTREAM_UNAVAILABLE", detail=offer.availability_status.value
                )
            )
            continue
        missing = [n for n in ("moq", "carton_qty") if getattr(offer, n) is None]
        if offer.availability_status is AvailabilityStatus.UNKNOWN:
            missing.append("availability_status")
        if missing:
            skipped.append(ReorderSkip(product_key=c.product_key, reason="UNKNOWN_FIELDS", detail=", ".join(missing)))
            continue
        if c.unit_cost_chf <= 0:
            skipped.append(ReorderSkip(product_key=c.product_key, reason="INVALID_COST"))
            continue
        assert offer.moq is not None and offer.carton_qty is not None
        moq, carton = offer.moq, offer.carton_qty
        position = c.sellable_qty + c.on_order_qty
        rp = reorder_point(c.avg_daily_sales, c.lead_time_days, c.safety_stock)
        if Decimal(position) > rp:
            skipped.append(
                ReorderSkip(product_key=c.product_key, reason="ABOVE_REORDER_POINT", detail=f"{position} > {rp}")
            )
            continue
        target = (
            c.avg_daily_sales * Decimal(c.lead_time_days + c.coverage_days)
            + Decimal(c.safety_stock)
            - Decimal(position)
        )
        need = int(target.to_integral_value(rounding=ROUND_CEILING))
        if need <= 0:
            skipped.append(ReorderSkip(product_key=c.product_key, reason="NO_PROBABLE_SALES"))
            continue
        notes: list[str] = []
        qty = _round_up_to(max(need, moq), carton)
        if qty > need:
            notes.append(f"MOQ/carton : {qty} > besoin {need}")
        upstream = offer.allocation_qty if offer.allocation_qty else offer.available_qty
        if upstream is None:
            notes.append("UPSTREAM_QTY_UNKNOWN : quantité amont à confirmer")
        elif qty > upstream:
            qty = _round_down_to(upstream, carton)
            notes.append(f"UPSTREAM_CAPPED à {qty}")
            if qty < moq or qty == 0:
                skipped.append(
                    ReorderSkip(product_key=c.product_key, reason="INSUFFICIENT_UPSTREAM", detail=f"amont {upstream}")
                )
                continue
        unit = c.unit_cost_chf
        cap_pct = exceptions.get(c.extension, cap_pct_default)
        ext_room = cap_pct * total_budget - exposure.get(c.extension, ZERO)
        max_budget = (
            _round_down_to(int((remaining / unit).to_integral_value(rounding=ROUND_FLOOR)), carton)
            if remaining > 0
            else 0
        )
        max_ext = (
            _round_down_to(int((ext_room / unit).to_integral_value(rounding=ROUND_FLOOR)), carton)
            if ext_room > 0
            else 0
        )
        limit = min(max_budget, max_ext)
        if qty > limit:
            binding = "BUDGET" if max_budget <= max_ext else "EXTENSION_CAP"
            if limit < moq or limit == 0:
                skipped.append(
                    ReorderSkip(product_key=c.product_key, reason=binding, detail=f"max {limit} < MOQ {moq}")
                )
                continue
            qty = limit
            notes.append(f"REDUCED_BY_{binding} à {qty}")
        if c.extension in exceptions:
            notes.append(f"EXTENSION_CAP_EXCEPTION {exceptions[c.extension]}")
        line_cost = (Decimal(qty) * unit).quantize(CENT, rounding=ROUND_HALF_UP)
        remaining -= line_cost
        exposure[c.extension] = exposure.get(c.extension, ZERO) + line_cost
        lines.append(
            ReorderLine(
                product_key=c.product_key,
                extension=c.extension,
                supplier_id=offer.supplier_id,
                supplier_sku=offer.supplier_sku,
                qty=qty,
                unit_cost_chf=unit,
                line_cost_chf=line_cost,
                reorder_point=rp,
                position=position,
                notes=tuple(notes),
            )
        )
    total = sum((ln.line_cost_chf for ln in lines), ZERO)
    inputs_hash = canonical_hash(
        {
            "fn": "propose_reorder",
            "candidates": list(candidates),
            "budget_available": budget,
            "stock_budget_total": total_budget,
            "now": now,
            "extension_exposure": exposure_in,
            "extension_cap_pct": cap_pct_default,
            "cap_exceptions": exceptions,
            "max_age": max_age,
            "rules_version": rules_version,
            "blocked_extensions": sorted(frozen_ext),
            "blocked_products": sorted(frozen_products),
            "cash_reserve_chf": reserve,
        }
    )
    return ReorderProposal(
        lines=tuple(lines),
        skipped=tuple(skipped),
        total_cost_chf=total,
        budget_available_chf=budget,
        budget_remaining_chf=remaining,
        extension_exposure_after=exposure,
        rules_version=rules_version,
        inputs_hash=inputs_hash,
        generated_at=now,
    )
