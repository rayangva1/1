"""Routes du tableau de bord interne, **lecture seule** : ``GET /dashboard/daily|weekly|monthly``.

**INTERNE — contient coûts et marges, ne jamais publier.** Mêmes règles que le reste de l'API
(:mod:`pokeshop.api`), avec **la même fonction d'authentification** (revue NEW-03) : en-tête
``X-Pokeshop-Token`` = jeton commun ou jeton d'un rôle (lecture : matrice ``pokeshop.authz``) ; 503
si aucune empreinte n'est configurée, 401 si absent ou faux. Montants en chaînes, aucun ``float``.
Réponses marquées ``Cache-Control: no-store`` et ``X-Robots-Tag: noindex, nofollow``.

Restauration (revue NEW-03) : un journal d'état non relu au démarrage (``Services.restore_errors``) rend
ses KPI **indisponibles** (étoile polaire « indisponible (journal non relu) », jamais « aucune
écriture » ni un cumul à 0) et figure dans ``unavailable``.

Sources lues dans les :class:`~pokeshop.api.Services` : journal de l'étoile polaire, stop-loss
évalué par la porte de gouvernance (verrou global compris), dernière photo d'activité (cash,
extensions, publicité), incidents, registre du mandat, niveau d'autonomie et registre de stock
local. Les autres sources (commandes Shopify, offres importées, ventes au coût, SAV, heures,
CA de l'entité, dépenses outils) restent « non branchées » — KPI ``INDISPONIBLE``, jamais un
chiffre inventé — tant qu'un fournisseur de données ne les transmet pas : affecter
``app.state.dashboard_provider`` (``(Services, now) -> DashboardInputs``) suffit à les brancher.

L'appel évalue le stop-loss comme ``GET /stoploss/status`` (journal ``EVALUATION`` du moteur ; un
seuil global atteint verrouille le gel, action protectrice) ; aucune autre écriture.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Request

from .api import HTTPProblem, PokeshopJSONResponse, Services
from .incidents import IncidentManager
from .mandate import SpendLedger
from .northstar import NorthStarLedger
from .stock import PersistentStockRegistry
from .dashboard import (
    INTERNAL_BANNER,
    CashPosition,
    DashboardConfig,
    DashboardError,
    DashboardInputs,
    DashboardReport,
    StopLossView,
    daily_report,
    monthly_report,
    weekly_report,
)

__all__ = ["DashboardProvider", "inputs_from_services", "build_dashboard_router", "NO_STORE_HEADERS"]

DashboardProvider = Callable[[Services, datetime], DashboardInputs]
"""Fournisseur des entrées du tableau de bord (remplaçable via ``app.state.dashboard_provider``)."""

NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Pokeshop-Interne": "couts-et-marges",
}
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def inputs_from_services(svc: Services, now: datetime) -> DashboardInputs:
    """Entrées disponibles dans le service ; les sources absentes restent ``None`` (non branchées)."""
    status, triggers = svc.gate.stoploss_status(now)
    view = (
        StopLossView.from_engine(svc.stoploss_engine, status, triggers, svc.gate.last_stoploss_error)
        if svc.stoploss_engine is not None
        else None
    )
    state = svc.stoploss_state
    unreadable = set(svc.restore_errors)
    skus = sorted({m.sku for m in svc.stock.movements()}) if PersistentStockRegistry.STREAM not in unreadable else []
    return DashboardInputs(
        as_of=now,
        autonomy_level=int(svc.autonomy.level),
        # Journal non relu au démarrage : source indisponible (None), jamais vide ni zéro (revue NEW-03).
        entries=svc.northstar.entries() if NorthStarLedger.STREAM not in unreadable else None,
        stoploss=view,
        cash=CashPosition(as_of=state.as_of, cash_available_chf=state.cash_available_chf) if state else None,
        stock_levels=tuple(svc.stock.level(s) for s in skus) if skus else None,
        incidents=svc.incidents.list() if IncidentManager.STREAM not in unreadable else None,
        spend_entries=svc.spend_ledger.entries() if SpendLedger.STREAM not in unreadable else None,
        extensions=state.extensions if state else None,
        ad_spends=state.ad_spends if state else None,
        attributed_orders=state.attributed_orders if state else None,
        unreadable=tuple(sorted(unreadable)),
    )


def _parse_date(text: str | None, name: str) -> date | None:
    if text is None or text == "":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPProblem(422, f"{name} : date AAAA-MM-JJ attendue (reçu {text!r})") from None


def build_dashboard_router(svc: Services, *, require_api: Callable[[Request], Any]) -> APIRouter:
    """Routeur ``/dashboard`` (GET uniquement) ; inclus par :func:`pokeshop.api.create_app`.

    ``require_api`` : **la** fonction d'authentification de l'API (jeton commun ou nommé, 503/401),
    passée par :func:`pokeshop.api.create_app` pour qu'aucune route n'ait sa propre règle.
    """
    router = APIRouter(prefix="/dashboard", tags=["tableau de bord interne"])
    cfg = svc.settings

    def config() -> DashboardConfig:
        return DashboardConfig.from_engine(rules=svc.rules, stoploss=svc.stoploss_config, timezone=cfg.timezone)

    def inputs(request: Request, now: datetime) -> DashboardInputs:
        provider: DashboardProvider = getattr(request.app.state, "dashboard_provider", None) or inputs_from_services
        return provider(svc, now)

    def respond(report: DashboardReport) -> PokeshopJSONResponse:
        payload = {"interne": INTERNAL_BANNER, "status": report.status, "report": report}
        response = PokeshopJSONResponse(content=payload)
        response.headers.update(NO_STORE_HEADERS)
        return response

    def run(build: Callable[[], DashboardReport]) -> PokeshopJSONResponse:
        try:
            return respond(build())
        except DashboardError as exc:
            raise HTTPProblem(422, str(exc)) from None

    @router.get("/daily")
    def dashboard_daily(request: Request, day: str | None = None) -> PokeshopJSONResponse:
        """Vue du jour (défaut : la veille) — étoile polaire et stop-loss en tête."""
        require_api(request)
        target = _parse_date(day, "day")
        now = svc.clock()
        data = inputs(request, now)
        return run(lambda: daily_report(data, config(), day=target, now=now))

    @router.get("/weekly")
    def dashboard_weekly(request: Request, week: str | None = None) -> PokeshopJSONResponse:
        """Vue de la semaine contenant ``week`` (défaut : dernière semaine close)."""
        require_api(request)
        target = _parse_date(week, "week")
        now = svc.clock()
        data = inputs(request, now)
        return run(lambda: weekly_report(data, config(), week=target, now=now))

    @router.get("/monthly")
    def dashboard_monthly(request: Request, month: str | None = None) -> PokeshopJSONResponse:
        """Vue du mois ``AAAA-MM`` (défaut : mois précédent)."""
        require_api(request)
        if month and not _MONTH_RE.match(month):
            raise HTTPProblem(422, f"month : AAAA-MM attendu (reçu {month!r})")
        now = svc.clock()
        data = inputs(request, now)
        return run(lambda: monthly_report(data, config(), month=month or None, now=now))

    return router
