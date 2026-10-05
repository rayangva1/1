"""Registre des factures fournisseur **enregistrées** (revue R4 : R2-NEW-01, R3-NEW-02, R3-DOC-02).

Pourquoi : jusqu'ici, le coût unitaire d'une réception (``POST /costs/movements`` RECEIPT) était déclaré par
l'agent finance seul, et les dettes de la photo du stop-loss (factures reçues non payées) n'étaient connues que
par sa déclaration (``POST /treasury/balance-items``). Les deux sont des valeurs décisives (valeur nette, gel
global, étoile polaire) déclarées par l'agent qui en profite.

Ce registre est adossé à des **événements** :

* une facture est enregistrée par le workflow n8n 03 (jeton ``n8n-03-factures``) **après** la validation de
  l'extraction par la propriétaire (formulaire protégé du workflow 03), ou par la propriétaire elle-même ;
  elle porte des lignes au **coût rendu unitaire ventilé** (CHF) qui servent de référence au coût d'une
  réception (écart > 2 % : propriétaire) ;
* tant qu'elle n'est pas payée, son solde est une **dette** de la photo du stop-loss (plancher que la
  déclaration de l'agent finance peut relever, jamais abaisser) ;
* un paiement n'est inscrit que par le connecteur de trésorerie (``connecteur-tresorerie``, débit relevé sur
  le compte) ou la propriétaire : c'est la seule voie qui abaisse la dette d'une facture.

Une facture gonflée gonfle d'autant la dette tant qu'elle n'est pas payée (valeur nette inchangée), et son
paiement baisse le cash du même montant : aucune perte ne peut être masquée par ce registre.
Registre en ajout seul, idempotent (même contenu : sans effet ; autre contenu : refus), persisté
(journal ``supplier_invoices``) ; illisible au démarrage => service gelé (fermé par défaut).
"""

from __future__ import annotations

import threading
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from .audit import StateJournal, StateStoreError
from .errors import PokeshopError
from .models import FrozenModel

__all__ = [
    "InvoiceError",
    "InvoicePersistenceError",
    "InvoiceLine",
    "SupplierInvoice",
    "InvoicePayment",
    "SupplierInvoiceBook",
]

ZERO = Decimal("0")


class InvoiceError(PokeshopError, ValueError):
    """Facture ou paiement refusé (contenu contradictoire, facture inconnue, cumul > montant)."""


class InvoicePersistenceError(InvoiceError, StateStoreError):
    """Journal illisible ou écriture refusée : rien n'est appliqué (fermé par défaut)."""


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


class InvoiceLine(FrozenModel):
    """Ligne de facture : référence (clé produit canonique), quantité, coût rendu unitaire ventilé en CHF."""

    product_key: str = Field(min_length=1, max_length=120)
    qty: int = Field(ge=1, le=100_000)
    unit_cost_chf: Decimal = Field(gt=0)


class SupplierInvoice(FrozenModel):
    """Facture fournisseur validée (montant dû TTC en CHF, lignes au coût rendu)."""

    invoice_ref: str = Field(min_length=3, max_length=120)
    supplier_id: str = Field(min_length=2, max_length=64)
    issued_at: datetime
    total_chf: Decimal = Field(gt=0)
    """Montant dû en CHF (taux de la propriétaire si devise étrangère) : dette jusqu'au paiement."""
    lines: tuple[InvoiceLine, ...] = Field(min_length=1, max_length=500)
    source: str = Field(min_length=3, max_length=300)
    """Justificatif (référence du PDF, validation de l'extraction par la propriétaire…)."""
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("issued_at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "horodatage")

    @model_validator(mode="after")
    def _lines(self) -> SupplierInvoice:
        keys = [line.product_key for line in self.lines]
        if len(set(keys)) != len(keys):
            raise ValueError("référence en double dans les lignes de la facture (une ligne par référence)")
        return self

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence (hors acteur et date d'enregistrement)."""
        return self.model_dump(mode="json", exclude={"recorded_by", "recorded_at"})

    def line_for(self, product_key: str) -> InvoiceLine | None:
        """Ligne de la référence (None si la facture ne la porte pas)."""
        return next((line for line in self.lines if line.product_key == product_key), None)


class InvoicePayment(FrozenModel):
    """Paiement d'une facture relevé sur le compte (connecteur de trésorerie) ou attesté par la propriétaire."""

    invoice_ref: str = Field(min_length=3, max_length=120)
    payment_ref: str = Field(min_length=3, max_length=120)
    """Référence de la transaction (relevé bancaire ou PayPal) : idempotence."""
    paid_at: datetime
    amount_chf: Decimal = Field(gt=0)
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("paid_at", "recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "horodatage")

    def content(self) -> dict[str, Any]:
        """Contenu comparé pour l'idempotence."""
        return self.model_dump(mode="json", exclude={"recorded_by", "recorded_at"})


class SupplierInvoiceBook:
    """Factures fournisseur et paiements (journal ``supplier_invoices``, ajout seul, thread-safe)."""

    STREAM = "supplier_invoices"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._invoices: dict[str, SupplierInvoice] = {}
        self._payments: dict[str, InvoicePayment] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> SupplierInvoiceBook:
        """Relit le registre (:class:`InvoicePersistenceError` s'il est illisible)."""
        try:
            records = store.load()
        except StateStoreError as exc:
            raise InvoicePersistenceError(f"factures fournisseur : {exc}") from exc
        book = cls()
        for n, record in enumerate(records, start=1):
            try:
                if "invoice" in record:
                    invoice = SupplierInvoice.model_validate(record["invoice"])
                    book._invoices[invoice.invoice_ref] = invoice
                else:
                    payment = InvoicePayment.model_validate(record["payment"])
                    book._payments[payment.payment_ref] = payment
            except (KeyError, TypeError, ValidationError) as exc:
                raise InvoicePersistenceError(f"factures fournisseur : enregistrement {n} illisible") from exc
        book._store = store
        return book

    def _append(self, record: dict[str, Any]) -> None:
        if self._store is None:
            return
        try:
            self._store.append(record)
        except StateStoreError as exc:
            raise InvoicePersistenceError(f"facture non enregistrée ({exc})") from exc

    def record(self, invoice: SupplierInvoice) -> tuple[SupplierInvoice, bool]:
        """Enregistre une facture ; (facture, nouvelle ?). Autre contenu sous la même référence : refus."""
        with self._lock:
            current = self._invoices.get(invoice.invoice_ref)
            if current is not None:
                if current.content() != invoice.content():
                    raise InvoiceError(
                        f"facture {invoice.invoice_ref} déjà enregistrée avec un autre contenu : un avoir ou une "
                        "facture rectificative porte une nouvelle référence"
                    )
                return current, False
            self._append({"invoice": invoice.model_dump(mode="json")})
            self._invoices[invoice.invoice_ref] = invoice
            return invoice, True

    def record_payment(self, payment: InvoicePayment) -> tuple[InvoicePayment, bool]:
        """Inscrit un paiement (cumul ≤ montant de la facture) ; (paiement, nouveau ?)."""
        with self._lock:
            invoice = self._invoices.get(payment.invoice_ref)
            if invoice is None:
                raise InvoiceError(f"paiement {payment.payment_ref} : facture {payment.invoice_ref} inconnue du registre")
            current = self._payments.get(payment.payment_ref)
            if current is not None:
                if current.content() != payment.content():
                    raise InvoiceError(f"paiement {payment.payment_ref} déjà inscrit avec un autre contenu")
                return current, False
            paid = self.paid(payment.invoice_ref)
            if paid + payment.amount_chf > invoice.total_chf:
                raise InvoiceError(
                    f"paiement {payment.payment_ref} : cumul {paid + payment.amount_chf} > montant de la facture "
                    f"{invoice.total_chf}"
                )
            self._append({"payment": payment.model_dump(mode="json")})
            self._payments[payment.payment_ref] = payment
            return payment, True

    def get(self, invoice_ref: str) -> SupplierInvoice | None:
        """Facture par référence (None si inconnue)."""
        with self._lock:
            return self._invoices.get(invoice_ref)

    def paid(self, invoice_ref: str, *, until: datetime | None = None) -> Decimal:
        """Montant payé sur une facture (paiements antérieurs ou égaux à ``until``)."""
        with self._lock:
            return sum(
                (p.amount_chf for p in self._payments.values()
                 if p.invoice_ref == invoice_ref and (until is None or p.paid_at <= until)),
                ZERO,
            )  # fmt: skip

    def unpaid(self, *, paid_until: datetime | None = None) -> tuple[tuple[SupplierInvoice, Decimal], ...]:
        """Factures enregistrées avec leur solde restant dû > 0, par référence (fermé par défaut).

        Toute facture enregistrée compte (même émise après la date de la photo : la dette existe) ; un paiement
        ne la réduit que s'il est antérieur ou égal à ``paid_until`` (date des relevés de cash de la photo) —
        sinon le cash relevé ne l'a pas encore déduit, et le compter masquerait une sortie de trésorerie.
        """
        with self._lock:
            invoices = sorted(self._invoices.values(), key=lambda i: i.invoice_ref)
        out = []
        for invoice in invoices:
            remaining = invoice.total_chf - self.paid(invoice.invoice_ref, until=paid_until)
            if remaining > 0:
                out.append((invoice, remaining))
        return tuple(out)

    def unpaid_total(self, *, paid_until: datetime | None = None) -> Decimal:
        """Dette des factures enregistrées non payées (plancher des dettes de la photo du stop-loss)."""
        return sum((remaining for _, remaining in self.unpaid(paid_until=paid_until)), ZERO)

    def posters(self) -> frozenset[str]:
        """Déposants (déduits du jeton) des factures et des paiements."""
        with self._lock:
            return frozenset({i.recorded_by for i in self._invoices.values()} | {p.recorded_by for p in self._payments.values()})
