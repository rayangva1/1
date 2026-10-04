"""Coût comptable historique, coût de remplacement et historique des prix validés (BP §4, §12).

Deux valeurs de coût coexistent (BP §4) :

* **Coût historique** (:class:`HistoricalCostLedger`) : lots de réception + **coût moyen
  pondéré mobile (CMP)**. Choix documenté : le CMP est simple à auditer, stable pour la marge
  réalisée et adapté à des produits scellés fongibles d'une même référence ; chaque lot est
  conservé pour la traçabilité et le rapprochement facture. Méthode admise en pratique pour
  l'évaluation au coût d'acquisition — **à confirmer par la fiduciaire** (FIFO possible).
  Montants comptabilisés à 0.01 HALF_UP ; la valeur du stock est la somme exacte des
  écritures ; la dernière sortie vide aussi la valeur résiduelle (pas de « poussière »).
* **Coût de remplacement** (:class:`ReplacementCostBook`) : coût rendu à la dernière offre
  fournisseur valide (fraîche). Une offre moins chère ne modifie **jamais** le coût historique.

:class:`PriceHistory` garde l'historique append-only des décisions et publications de prix,
et permet le **retour au dernier prix validé**. Il ne touche jamais une commande conclue :
le prix d'une commande est figé dans ses lignes (``BasketLine.unit_price_ttc``).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import Field

from .errors import CostError, PricingError
from .models import (
    CostLot,
    CostVariance,
    DecisionStatus,
    FrozenModel,
    InventoryValuation,
    PriceDecision,
    PriceEvent,
    PriceEventKind,
    ReplacementCost,
)
from .pricing import as_decimal
from .stock import DEFAULT_MAX_AGE, is_stale

__all__ = [
    "CostEntryKind",
    "CostEntry",
    "HistoricalCostLedger",
    "ReplacementCostBook",
    "PriceHistory",
]

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _aware(ts: datetime, name: str) -> datetime:
    if not isinstance(ts, datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise CostError(f"{name} doit être un datetime avec fuseau horaire")
    return ts


def _money(value: Decimal | int | str, name: str) -> Decimal:
    """Montant fini > 0 converti par :func:`pokeshop.pricing.as_decimal` (``float``/``bool`` : TypeError)."""
    try:
        result = as_decimal(value, name)
    except PricingError as exc:
        raise CostError(str(exc)) from exc
    if result <= 0:
        raise CostError(f"{name} doit être un montant fini > 0 (reçu {result})")
    return result


CostEntryKind = Literal["RECEIPT", "ISSUE", "RETURN", "WRITE_OFF", "INVOICE_ADJUSTMENT"]


class CostEntry(FrozenModel):
    """Écriture du journal de coût historique (append-only)."""

    seq: int
    kind: CostEntryKind
    qty: int
    amount: Decimal = Field(description="Montant CHF signé porté sur la valeur du stock")
    cogs: Decimal = ZERO
    ref: str
    at: datetime


class HistoricalCostLedger:
    """Coût historique d'un produit : lots de réception + CMP mobile, thread-safe."""

    def __init__(
        self,
        product_key: str,
        *,
        variance_tolerance_pct: Decimal = Decimal("0.005"),
        variance_tolerance_chf: Decimal = Decimal("0.05"),
    ) -> None:
        if not product_key:
            raise CostError("product_key vide")
        if variance_tolerance_pct < 0 or variance_tolerance_chf < 0:
            raise CostError("tolérances négatives")
        self.product_key = product_key
        self._tol_pct = variance_tolerance_pct
        self._tol_chf = variance_tolerance_chf
        self._lock = threading.RLock()
        self._lots: dict[str, CostLot] = {}
        self._variances: dict[str, CostVariance] = {}
        self._journal: list[CostEntry] = []
        self._qty = 0
        self._value = ZERO

    # -- lecture ------------------------------------------------------------
    @property
    def qty_on_hand(self) -> int:
        """Unités valorisées en stock."""
        return self._qty

    @property
    def total_value(self) -> Decimal:
        """Valeur comptable du stock (CHF, 0.01)."""
        return self._value

    @property
    def average_unit_cost(self) -> Decimal | None:
        """CMP courant à 0.0001 (None si stock nul)."""
        with self._lock:
            if self._qty == 0:
                return None
            return (self._value / Decimal(self._qty)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def valuation(self) -> InventoryValuation:
        """Photo de la valorisation courante."""
        with self._lock:
            return InventoryValuation(
                product_key=self.product_key,
                qty_on_hand=self._qty,
                total_value=self._value,
                average_unit_cost=self.average_unit_cost,
            )

    def lot(self, lot_id: str) -> CostLot:
        """Lot par identifiant (CostError si inconnu)."""
        try:
            return self._lots[lot_id]
        except KeyError:
            raise CostError(f"lot inconnu : {lot_id}") from None

    def lots(self) -> tuple[CostLot, ...]:
        """Lots dans l'ordre de réception."""
        return tuple(self._lots.values())

    def variances(self) -> tuple[CostVariance, ...]:
        """Écarts estimation/facture enregistrés."""
        return tuple(self._variances.values())

    def journal(self) -> tuple[CostEntry, ...]:
        """Journal append-only des écritures."""
        return tuple(self._journal)

    # -- interne ------------------------------------------------------------
    def _book(
        self, kind: CostEntryKind, qty: int, amount: Decimal, ref: str, at: datetime, cogs: Decimal = ZERO
    ) -> None:
        self._journal.append(
            CostEntry(seq=len(self._journal) + 1, kind=kind, qty=qty, amount=amount, cogs=cogs, ref=ref, at=at)
        )

    def _take_out(self, qty: int) -> Decimal:
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise CostError("quantité de sortie invalide")
        if qty > self._qty:
            raise CostError(f"sortie {qty} > stock valorisé {self._qty}")
        amount = self._value if qty == self._qty else _q2(self._value * Decimal(qty) / Decimal(self._qty))
        self._qty -= qty
        self._value -= amount
        return amount

    # -- mutations ----------------------------------------------------------
    def receive(self, lot: CostLot) -> InventoryValuation:
        """Entrée d'un lot de réception au coût rendu estimé (ou facturé) ; recalcule le CMP."""
        if lot.product_key != self.product_key:
            raise CostError(f"lot {lot.lot_id} : produit {lot.product_key} ≠ {self.product_key}")
        _aware(lot.received_at, "received_at")
        with self._lock:
            if lot.lot_id in self._lots:
                raise CostError(f"lot déjà reçu : {lot.lot_id}")
            amount = _q2(Decimal(lot.qty) * lot.unit_cost)
            self._lots[lot.lot_id] = lot
            self._qty += lot.qty
            self._value += amount
            self._book("RECEIPT", lot.qty, amount, lot.lot_id, lot.received_at)
            return self.valuation()

    def issue(self, qty: int, ref: str, at: datetime) -> Decimal:
        """Sortie pour vente au CMP ; renvoie le coût des ventes (CHF, 0.01)."""
        _aware(at, "at")
        with self._lock:
            amount = self._take_out(qty)
            self._book("ISSUE", qty, -amount, ref, at, cogs=amount)
            return amount

    def return_units(self, qty: int, unit_cost: Decimal, ref: str, at: datetime) -> InventoryValuation:
        """Retour client remis en stock au coût unitaire enregistré lors de la vente."""
        _aware(at, "at")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise CostError("quantité de retour invalide")
        unit_cost = _money(unit_cost, "unit_cost")
        with self._lock:
            amount = _q2(Decimal(qty) * unit_cost)
            self._qty += qty
            self._value += amount
            self._book("RETURN", qty, amount, ref, at, cogs=-amount)
            return self.valuation()

    def write_off(self, qty: int, ref: str, at: datetime) -> Decimal:
        """Sortie d'unités endommagées/détruites au CMP ; renvoie la perte (CHF)."""
        _aware(at, "at")
        with self._lock:
            amount = self._take_out(qty)
            self._book("WRITE_OFF", qty, -amount, ref, at)
            return amount

    def apply_invoice(self, lot_id: str, actual_unit_cost: Decimal, invoice_ref: str, at: datetime) -> CostVariance:
        """Rapproche la facture réelle d'un lot et enregistre l'écart (BP §12, idempotent par facture).

        L'écart total est porté sur le stock pour les unités du lot supposées encore en main
        (min(qty du lot, stock valorisé) — approximation CMP documentée, la valeur du stock ne
        devient jamais négative) et le solde en coût des ventes. ``flagged`` si l'écart dépasse
        à la fois la tolérance en % et en CHF : à signaler et à répercuter sur le coût de
        remplacement / la décision de prix. Ne modifie aucune commande conclue.
        """
        _aware(at, "at")
        actual_unit_cost = _money(actual_unit_cost, "actual_unit_cost")
        if not invoice_ref:
            raise CostError("référence de facture obligatoire")
        with self._lock:
            lot = self.lot(lot_id)
            previous = self._variances.get(lot_id)
            if previous is not None:
                if previous.invoice_ref == invoice_ref and previous.actual_unit_cost == actual_unit_cost:
                    return previous
                raise CostError(f"lot {lot_id} déjà rapproché avec la facture {previous.invoice_ref}")
            estimated = lot.unit_cost
            delta_unit = actual_unit_cost - estimated
            delta_total = _q2(Decimal(lot.qty) * actual_unit_cost) - _q2(Decimal(lot.qty) * estimated)
            in_stock = min(lot.qty, self._qty)
            inventory_adj = _q2(delta_total * Decimal(in_stock) / Decimal(lot.qty))
            if self._value + inventory_adj < 0:
                inventory_adj = -self._value
            cogs_adj = delta_total - inventory_adj
            self._value += inventory_adj
            pct = (delta_unit / estimated).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            direction: Literal["HIGHER", "LOWER", "EQUAL"] = (
                "HIGHER" if delta_unit > 0 else "LOWER" if delta_unit < 0 else "EQUAL"
            )
            flagged = abs(delta_total) >= self._tol_chf and abs(pct) >= self._tol_pct
            variance = CostVariance(
                lot_id=lot_id,
                product_key=self.product_key,
                qty=lot.qty,
                estimated_unit_cost=estimated,
                actual_unit_cost=actual_unit_cost,
                delta_unit=delta_unit,
                delta_total=delta_total,
                delta_pct=pct,
                inventory_adjustment=inventory_adj,
                cogs_adjustment=cogs_adj,
                direction=direction,
                flagged=flagged,
                invoice_ref=invoice_ref,
                at=at,
            )
            self._variances[lot_id] = variance
            self._lots[lot_id] = lot.replace(unit_cost=actual_unit_cost, cost_basis="INVOICE", ref=invoice_ref)
            self._book("INVOICE_ADJUSTMENT", 0, inventory_adj, invoice_ref, at, cogs=cogs_adj)
            return variance


class ReplacementCostBook:
    """Coûts de remplacement par produit et fournisseur (dernière offre valide)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._latest: dict[tuple[str, str], ReplacementCost] = {}
        self._history: list[ReplacementCost] = []

    def update(self, rc: ReplacementCost) -> bool:
        """Enregistre une offre ; ignorée (False) si plus ancienne que la dernière connue du fournisseur."""
        with self._lock:
            key = (rc.product_key, rc.supplier_id)
            current = self._latest.get(key)
            self._history.append(rc)
            if current is not None and rc.source_ts < current.source_ts:
                return False
            self._latest[key] = rc
            return True

    def latest(self, product_key: str, supplier_id: str | None = None) -> ReplacementCost | None:
        """Dernière offre connue (même périmée), d'un fournisseur ou la plus récente tous fournisseurs."""
        with self._lock:
            items = [
                rc
                for (pk, sid), rc in self._latest.items()
                if pk == product_key and (supplier_id is None or sid == supplier_id)
            ]
        return max(items, key=lambda rc: rc.source_ts) if items else None

    def current(self, product_key: str, now: datetime, max_age: timedelta = DEFAULT_MAX_AGE) -> ReplacementCost | None:
        """Coût de remplacement **valide** : la moins chère des dernières offres fraîches (None sinon)."""
        with self._lock:
            fresh = [
                rc
                for (pk, _), rc in self._latest.items()
                if pk == product_key and not is_stale(rc.source_ts, now, max_age)
            ]
        if not fresh:
            return None
        return min(fresh, key=lambda rc: (rc.unit_cost, rc.supplier_id))

    def history(self, product_key: str) -> tuple[ReplacementCost, ...]:
        """Toutes les offres reçues pour le produit, dans l'ordre d'arrivée."""
        with self._lock:
            return tuple(rc for rc in self._history if rc.product_key == product_key)


class PriceHistory:
    """Historique append-only des prix publics, avec retour au dernier prix validé.

    Une publication ``validated=True`` correspond à une décision OK appliquée dans les seuils
    (niveau d'autonomie ≥ 2) ou à une validation humaine. :meth:`rollback` annule la
    publication courante et republie le dernier prix validé qui la précède.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[PriceEvent] = []
        self._stacks: dict[str, list[tuple[Decimal, bool]]] = {}

    def _append(
        self,
        product_key: str,
        kind: PriceEventKind,
        price: Decimal | None,
        at: datetime,
        actor: str,
        *,
        status: DecisionStatus | None = None,
        inputs_hash: str | None = None,
        rules_version: str | None = None,
        note: str = "",
    ) -> PriceEvent:
        _aware(at, "at")
        event = PriceEvent(
            seq=len(self._events) + 1,
            product_key=product_key,
            kind=kind,
            price=price,
            at=at,
            actor=actor,
            status=status,
            inputs_hash=inputs_hash,
            rules_version=rules_version,
            note=note,
        )
        self._events.append(event)
        return event

    def record_decision(
        self, product_key: str, decision: PriceDecision, at: datetime, actor: str = "engine"
    ) -> PriceEvent:
        """Trace une décision du moteur (tous statuts) sans rien publier."""
        with self._lock:
            return self._append(
                product_key,
                PriceEventKind.PROPOSED,
                decision.evaluated_price or decision.recommended_price,
                at,
                actor,
                status=decision.status,
                inputs_hash=decision.inputs_hash,
                rules_version=decision.rules_version,
                note=",".join(decision.reasons),
            )

    def publish(
        self,
        product_key: str,
        price: Decimal,
        at: datetime,
        actor: str,
        *,
        validated: bool,
        decision: PriceDecision | None = None,
        note: str = "",
    ) -> PriceEvent:
        """Publie un prix public. DRAFT/BLOCKED interdits ; REVIEW exige ``validated=True`` (humain).

        Sans validation humaine, le prix publié doit être exactement celui évalué par la
        décision du moteur (pas de prix « à la main » hors moteur, BP §5).
        """
        price = as_decimal(price, "price")
        if price <= 0:
            raise PricingError("prix public ≤ 0")
        if not product_key:
            raise PricingError("product_key vide")
        if decision is not None:
            if decision.status in (DecisionStatus.DRAFT, DecisionStatus.BLOCKED):
                raise PricingError(f"décision {decision.status.value} : publication interdite")
            if decision.status is DecisionStatus.REVIEW and not validated:
                raise PricingError("décision REVIEW : validation humaine requise avant publication")
            engine_price = decision.evaluated_price or decision.recommended_price
            if not validated and engine_price is not None and price != engine_price:
                raise PricingError(f"prix {price} ≠ prix de la décision {engine_price} : validation humaine requise")
        with self._lock:
            self._stacks.setdefault(product_key, []).append((price, validated))
            return self._append(
                product_key,
                PriceEventKind.PUBLISHED,
                price,
                at,
                actor,
                status=decision.status if decision else None,
                inputs_hash=decision.inputs_hash if decision else None,
                rules_version=decision.rules_version if decision else None,
                note=note or ("validé" if validated else "non validé"),
            )

    def validate(self, product_key: str, at: datetime, actor: str, note: str = "") -> PriceEvent:
        """Valide (humain) le prix publié courant."""
        with self._lock:
            stack = self._stacks.get(product_key)
            if not stack:
                raise PricingError(f"aucun prix publié pour {product_key}")
            price, _ = stack[-1]
            stack[-1] = (price, True)
            return self._append(product_key, PriceEventKind.VALIDATED, price, at, actor, note=note)

    def current_price(self, product_key: str) -> Decimal | None:
        """Prix public courant (None si jamais publié)."""
        with self._lock:
            stack = self._stacks.get(product_key)
            return stack[-1][0] if stack else None

    def last_validated_price(self, product_key: str) -> Decimal | None:
        """Prix validé le plus récent encore dans l'historique actif (peut être le courant)."""
        with self._lock:
            for price, ok in reversed(self._stacks.get(product_key, [])):
                if ok:
                    return price
            return None

    def rollback(self, product_key: str, at: datetime, actor: str, reason: str) -> PriceEvent:
        """Annule la publication courante et revient au dernier prix validé antérieur."""
        if not reason:
            raise PricingError("motif de retour arrière obligatoire")
        with self._lock:
            stack = self._stacks.get(product_key, [])
            idx = next((i for i in range(len(stack) - 2, -1, -1) if stack[i][1]), None)
            if idx is None:
                raise PricingError(f"{product_key} : aucun prix validé antérieur")
            del stack[idx + 1 :]
            return self._append(product_key, PriceEventKind.ROLLED_BACK, stack[-1][0], at, actor, note=reason)

    def events(self, product_key: str | None = None) -> tuple[PriceEvent, ...]:
        """Journal complet (ou d'un produit)."""
        with self._lock:
            return tuple(e for e in self._events if product_key is None or e.product_key == product_key)
