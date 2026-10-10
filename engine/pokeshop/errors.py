"""Exceptions du moteur pokeshop.

Toutes les erreurs métier héritent de :class:`PokeshopError` pour qu'un appelant
(API, workflow n8n) puisse les intercepter d'un bloc et les transformer en incident.
Les erreurs de validation de données héritent aussi de :class:`ValueError`.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "PokeshopError",
    "PricingError",
    "IncompleteDataError",
    "RulesError",
    "CostError",
    "StockError",
    "InsufficientStockError",
    "ConcurrencyError",
    "ReservationNotFoundError",
    "InvalidStateError",
]


class PokeshopError(Exception):
    """Racine de toutes les erreurs métier du moteur."""


class PricingError(PokeshopError, ValueError):
    """Calcul de coût/prix impossible ou entrée invalide (ex. dénominateur <= 0, prix zéro)."""


class IncompleteDataError(PricingError):
    """Champs obligatoires inconnus : la fiche doit rester en brouillon (BP §5)."""

    def __init__(self, fields: Sequence[str], message: str | None = None) -> None:
        self.fields: tuple[str, ...] = tuple(fields)
        super().__init__(message or f"Champs inconnus : {', '.join(self.fields)}")


class RulesError(PokeshopError, ValueError):
    """Fichier de règles versionné absent, illisible ou invalide."""

    def __init__(self, errors: Sequence[str] | str) -> None:
        self.errors: tuple[str, ...] = (errors,) if isinstance(errors, str) else tuple(errors)
        super().__init__("Règles invalides : " + " ; ".join(self.errors))


class CostError(PokeshopError, ValueError):
    """Opération invalide sur le coût historique (lot inconnu, sortie > stock, etc.)."""


class StockError(PokeshopError, ValueError):
    """Opération de stock invalide."""


class InsufficientStockError(StockError):
    """Stock vendable insuffisant pour la réservation demandée."""


class ConcurrencyError(StockError):
    """Version attendue différente de la version courante (compare-and-set refusé)."""


class ReservationNotFoundError(StockError, KeyError):
    """Identifiant de réservation inconnu."""

    def __str__(self) -> str:  # KeyError ajoute des guillemets sinon
        return str(self.args[0]) if self.args else "Réservation inconnue"


class InvalidStateError(StockError):
    """Transition d'état interdite (ex. annuler une réservation déjà expédiée)."""
