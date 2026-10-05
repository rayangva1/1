"""Routes du tableau de bord interne, **lecture seule** : ``GET /dashboard/daily|weekly|monthly``.

**INTERNE — contient coûts et marges, ne jamais publier.** Mêmes règles que le reste de l'API
(:mod:`pokeshop.api`) : en-tête ``X-Pokeshop-Token`` obligatoire (503 si aucune empreinte n'est
configurée, 401 si absent ou faux), montants en chaînes, aucun ``float``. Réponses marquées
``Cache-Control: no-store`` et ``X-Robots-Tag: noindex, nofollow``.

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

from fastapi import APIRouter, Request

from .api import API_TOKEN_HEADER, HTTPProblem, PokeshopJSONResponse, Services, _token_ok
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
    skus = sorted({m.sku for m in svc.stock.movements()})
    return DashboardInputs(
        as_of=now,
        autonomy_level=int(svc.autonomy.level),
        entries=svc.northstar.entries(),
        stoploss=view,
        cash=CashPosition(as_of=state.as_of, cash_available_chf=state.cash_available_chf) if state else None,
        stock_levels=tuple(svc.stock.level(s) for s in skus) if skus else None,
        incidents=svc.incidents.list(),
        spend_entries=svc.spend_ledger.entries(),
        extensions=state.extensions if state else None,
        ad_spends=state.ad_spends if state else None,
        attributed_orders=state.attributed_orders if state else None,
    )


def _parse_date(text: str | None, name: str) -> date | None:
    if text is None or text == "":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPProblem(422, f"{name} : date AAAA-MM-JJ attendue (reçu {text!r})") from None


def build_dashboard_router(svc: Services) -> APIRouter:
    """Routeur ``/dashboard`` (GET uniquement) ; inclus par :func:`pokeshop.api.create_app`."""
    router = APIRouter(prefix="/dashboard", tags=["tableau de bord interne"])
    cfg = svc.settings

    def require_api(request: Request) -> None:
        if cfg.api_token_sha256 is None:
            raise HTTPProblem(503, "jeton d'API non configuré (POKESHOP_API_TOKEN_SHA256) : routes internes fermées")
        if not _token_ok(request.headers.get(API_TOKEN_HEADER), cfg.api_token_sha256):
            raise HTTPProblem(401, f"en-tête {API_TOKEN_HEADER} absent ou invalide")

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
