"""Orchestration « fournisseur → site » en 8 étapes (BP §12) et synchronisation du stock local.

Cycle fournisseur → site (:meth:`SyncService.run_supplier_cycle`), **en simulation par défaut** :

1. récupérer le flux autorisé et dater la source (:func:`pokeshop.importers.run_import`) ;
2. valider devise, TVA, unité, langue et quantité (quarantaine de l'import) ;
3. rapprocher la référence exacte (:func:`pokeshop.catalog.match_offer_to_product`) ;
4. évaluer l'offre et le coût rendu (frais connus seulement : rien n'est inventé) ;
5. calculer le prix et tester les seuils (:func:`pokeshop.pricing.evaluate_offer`) ;
6. générer ou actualiser la fiche (:func:`pokeshop.publish.build_publication`) ;
7. publier uniquement si les données, le stock et la gouvernance le permettent
   (:class:`pokeshop.autonomy.GovernanceGate` puis ``productSet``) ;
8. vérifier l'état réel sur le site et journaliser la décision.

Chaque anomalie ouvre un incident (quarantaine de la référence ou suspension de la source).
Une offre périmée ne change jamais un prix public ; une panne de flux ne touche jamais au stock
local confirmé (ce module ne modifie aucun stock à partir d'une offre fournisseur).

Stock local (:meth:`SyncService.push_stock`) : **Shopify reste l'autorité des réservations de
vente** (BP §6). Le service pousse ``available = physique − max(réservé service, engagé
Shopify) − endommagé − sécurité`` avec ``changeFromQuantity`` (compare-and-swap), conserve les
mouvements et **signale** les écarts de réservation au lieu de les écraser. Référence bloquée
par le stop-loss produit ou en quarantaine : 0 publié (vente bloquée, aucun faux stock).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .audit import ActorKind, AuditLog
from .autonomy import GateDecision, GovernanceGate, WriteAction
from .catalog import CatalogIndex, CatalogProduct, ExtensionTable, MatchStatus, expected_language_for, match_offer_to_product
from .costs import PriceHistory, ReplacementCostBook
from .errors import PokeshopError, PricingError
from .importers import ImportBaseline, ImportResult, ImportStatus, MappingError, SupplierMapping, run_import
from .incidents import IncidentCode, IncidentManager, IncidentScope, Severity, codes_for_reasons
from .models import FrozenModel, PriceDecision, PriceEventKind, Reason, ReplacementCost, StockLevel, SupplierOffer
from .pricing import evaluate_offer
from .publish import CatalogListing, PlanOutcome, PriceValidation, PublicationPlan, build_publication, sensitive_violations
from .rules import RuleSet
from .shopify_client import (
    InventoryChange,
    RemoteInventoryLevel,
    ShopifyAccessDeniedError,
    ShopifyClient,
    ShopifyError,
    derive_idempotency_key,
)

__all__ = [
    "WORKFLOW_SUPPLIER_TO_SHOP",
    "WORKFLOW_STOCK",
    "SyncError",
    "SyncStep",
    "STEP_LABELS_FR",
    "StepResult",
    "OfferCostInputs",
    "SyncContext",
    "SyncItem",
    "SyncReport",
    "StockTarget",
    "StockPushLine",
    "StockSyncReport",
    "price_reference_24h",
    "stock_target",
    "consecutive_clean_runs",
    "SyncService",
]

WORKFLOW_SUPPLIER_TO_SHOP = "fournisseur-site"
WORKFLOW_STOCK = "stock-local"


class SyncError(PokeshopError, ValueError):
    """Entrée de synchronisation invalide."""


class SyncStep(str, Enum):
    """Les 8 étapes du workflow BP §12."""

    FETCH = "1_RECUPERER"
    VALIDATE = "2_VALIDER"
    MATCH = "3_RAPPROCHER"
    COST = "4_COUT_RENDU"
    PRICE = "5_PRIX_SEUILS"
    LISTING = "6_FICHE"
    PUBLISH = "7_PUBLIER"
    VERIFY = "8_VERIFIER_JOURNALISER"


STEP_LABELS_FR: dict[SyncStep, str] = {
    SyncStep.FETCH: "Récupérer le flux autorisé et dater la source",
    SyncStep.VALIDATE: "Valider devise, TVA, unité, langue et quantité",
    SyncStep.MATCH: "Rapprocher la référence exacte",
    SyncStep.COST: "Évaluer l'offre et le coût rendu",
    SyncStep.PRICE: "Calculer le prix et tester les seuils",
    SyncStep.LISTING: "Générer ou actualiser la fiche",
    SyncStep.PUBLISH: "Publier si les données et le stock vendable le permettent",
    SyncStep.VERIFY: "Vérifier l'état réel sur le site et journaliser",
}

StepStatus = Literal["OK", "AVERTISSEMENT", "ECHEC", "IGNORE"]


class StepResult(FrozenModel):
    """Résultat d'une étape."""

    step: SyncStep
    status: StepStatus
    detail: str
    count: int = 0


class OfferCostInputs(FrozenModel):
    """Frais connus d'une source (par unité retail, CHF). ``None`` = inconnu => fiche en brouillon."""

    inbound_freight_alloc: Decimal | None = Field(default=None, ge=0)
    customs_and_fees: Decimal | None = Field(default=None, ge=0)
    import_vat: Decimal | None = Field(default=None, ge=0)
    fx_rate_to_chf: Decimal | None = Field(default=None, gt=0)
    fx_source: str | None = None
    fx_date: date | None = None
    order_qty: int | None = Field(default=None, ge=1)


@dataclass(frozen=True)
class SyncContext:
    """Données d'un cycle : règles versionnées, catalogue validé, frais connus, références marché."""

    rules: RuleSet
    catalog_products: Sequence[CatalogProduct]
    listings: Mapping[str, CatalogListing]
    """Fiches publiables par ``product_id`` du catalogue."""
    table: ExtensionTable | None = None
    cost_inputs: Mapping[str, OfferCostInputs] = field(default_factory=dict)
    """Frais par ``supplier_id``."""
    market_refs: Mapping[str, Decimal] = field(default_factory=dict)
    price_validations: Mapping[str, PriceValidation] = field(default_factory=dict)
    sensitive_terms: Collection[str] = ()


class SyncItem(FrozenModel):
    """Traitement d'une offre (aucun coût ni marge : seulement statuts, motifs et prix public)."""

    offer_ref: str
    product_id: str | None = None
    match_status: str
    decision_status: str | None = None
    decision_reasons: tuple[str, ...] = ()
    plan_outcome: str | None = None
    action: str | None = None
    price_chf: Decimal | None = None
    gate_allowed: bool | None = None
    gate_reasons: tuple[str, ...] = ()
    written: bool = False
    replayed: bool = False
    verified: bool | None = None
    incident_ids: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


class SyncReport(FrozenModel):
    """Compte rendu d'un cycle (interne)."""

    run_id: str
    supplier_id: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    rules_version: str
    import_status: str | None = None
    source_ts: datetime | None = None
    rows_read: int = 0
    offers_accepted: int = 0
    rows_quarantined: int = 0
    steps: tuple[StepResult, ...] = ()
    items: tuple[SyncItem, ...] = ()
    incident_ids: tuple[str, ...] = ()
    critical_errors: tuple[str, ...] = ()
    fictif: bool = False

    @property
    def clean(self) -> bool:
        """Vrai si aucune « erreur critique » (``GATES_GO_NO_GO.md`` §1) n'a été détectée."""
        return not self.critical_errors

    def step(self, step: SyncStep) -> StepResult:
        """Résultat d'une étape."""
        return next(s for s in self.steps if s.step is step)

    def render_markdown(self) -> str:
        """Rapport interne (Markdown, français)."""
        mode = "SIMULATION" if self.dry_run else "RÉEL"
        lines = [
            f"# Synchronisation fournisseur → site — {self.supplier_id} — {self.started_at:%Y-%m-%d %H:%M} — {mode}",
            "",
            f"Règles {self.rules_version} · import {self.import_status or '—'} · lignes {self.rows_read} · "
            f"offres {self.offers_accepted} · quarantaine {self.rows_quarantined}" + (" · **FICTIF**" if self.fictif else ""),
            f"Erreurs critiques : **{len(self.critical_errors)}**",
            "",
            "| Étape | Statut | Détail |",
            "|---|---|---|",
        ]
        for s in self.steps:
            lines.append(f"| {STEP_LABELS_FR[s.step]} | {s.status} | {s.detail.replace('|', '/')} |")
        if self.items:
            lines += ["", "| Offre | Produit | Rapprochement | Décision | Fiche | Prix public | Écrit |", "|---|---|---|---|---|---:|---|"]
            for i in self.items:
                price = f"{i.price_chf}" if i.price_chf is not None else "—"
                written = "oui" if i.written else ("simulé" if self.dry_run and i.gate_allowed else "non")
                lines.append(
                    f"| {i.offer_ref} | {i.product_id or '—'} | {i.match_status} | {i.decision_status or '—'} | "
                    f"{i.plan_outcome or '—'} | {price} | {written} |"
                )
        lines += ["", "## Validation humaine requise", ""]
        checks = [f"- [ ] Erreur critique : {e}" for e in self.critical_errors]
        if self.incident_ids:
            checks.append(f"- [ ] Traiter les incidents : {', '.join(self.incident_ids)}")
        reviews = [i for i in self.items if i.plan_outcome == PlanOutcome.NOT_SENT.value and i.product_id]
        if reviews:
            checks.append(f"- [ ] {len(reviews)} fiche(s) non publiée(s) : motifs dans le détail des items.")
        lines += checks or ["- [ ] Aucune action bloquante : contrôle par sondage."]
        return "\n".join(lines) + "\n"


class StockTarget(FrozenModel):
    """Quantité ``available`` cible d'un SKU et écarts de rapprochement."""

    target_available: int = Field(ge=0)
    reserved_effective: int = Field(ge=0)
    discrepancies: tuple[str, ...] = ()
    oversell: bool = False


class StockPushLine(FrozenModel):
    """Ligne de synchronisation du stock."""

    sku: str
    product_key: str
    inventory_item_id: str
    local_on_hand: int
    local_sellable: int
    remote_available: int
    remote_committed: int
    remote_assumed: bool
    target_available: int
    action: Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR"]
    written: bool = False
    replayed: bool = False
    reasons: tuple[str, ...] = ()
    discrepancies: tuple[str, ...] = ()
    incident_ids: tuple[str, ...] = ()


class StockSyncReport(FrozenModel):
    """Compte rendu d'une synchronisation de stock."""

    run_id: str
    at: datetime
    dry_run: bool
    location_id: str
    lines: tuple[StockPushLine, ...]
    incident_ids: tuple[str, ...] = ()
    critical_errors: tuple[str, ...] = ()

    @property
    def written_count(self) -> int:
        """Écritures réellement envoyées."""
        return sum(1 for line in self.lines if line.written)

    @property
    def conflicts(self) -> tuple[StockPushLine, ...]:
        """Lignes en conflit de concurrence persistant."""
        return tuple(line for line in self.lines if line.action == "CONFLICT")

    @property
    def clean(self) -> bool:
        """Vrai sans erreur critique."""
        return not self.critical_errors


# ------------------------------------------------------------------------- utilitaires


def price_reference_24h(
    history: PriceHistory | None, product_key: str, now: datetime, fallback: Decimal | None = None
) -> Decimal | None:
    """Prix public d'il y a 24 h (base du plafond journalier de 5 %, BP §5).

    Dernier prix publié (ou rétabli) au plus tard à ``now − 24 h`` ; sinon le premier prix publié
    dans les 24 dernières heures ; sinon ``fallback`` (prix actuel de la fiche).
    """
    if history is None:
        return fallback
    cutoff = now - timedelta(hours=24)
    events = [
        e for e in history.events(product_key)
        if e.kind in (PriceEventKind.PUBLISHED, PriceEventKind.ROLLED_BACK) and e.price is not None
    ]  # fmt: skip
    before = [e for e in events if e.at <= cutoff]
    if before:
        return before[-1].price
    if events:
        return events[0].price
    return fallback


def stock_target(
    local: StockLevel, remote: RemoteInventoryLevel, *, blocked: bool = False
) -> StockTarget:
    """Cible ``available`` : physique − max(réservé service, engagé Shopify) − endommagé − sécurité (≥ 0).

    Le maximum des deux réservations évite toute promesse au-delà du stock réellement libre.
    ``blocked`` (stop-loss produit, quarantaine) : 0. Les écarts sont signalés, jamais écrasés.
    """
    reserved = max(local.reserved, remote.committed)
    target = max(0, local.on_hand - reserved - local.damaged - local.safety)
    discrepancies: list[str] = []
    if local.reserved != remote.committed:
        discrepancies.append(
            f"ECART_RESERVATIONS : service {local.reserved}, Shopify {remote.committed} (rapprocher les commandes)"
        )
    if remote.on_hand is not None and not remote.assumed and remote.on_hand != local.on_hand - local.damaged:
        discrepancies.append(
            f"ECART_PHYSIQUE : service {local.on_hand - local.damaged} vendable physique, Shopify {remote.on_hand}"
        )
    oversell = remote.committed > local.on_hand - local.damaged
    return StockTarget(
        target_available=0 if blocked else target,
        reserved_effective=reserved,
        discrepancies=tuple(discrepancies),
        oversell=oversell,
    )


def consecutive_clean_runs(reports: Sequence[SyncReport | StockSyncReport]) -> int:
    """Nombre de synchronisations consécutives sans erreur critique, en partant de la plus récente.

    Critère de recette BP §13 (semaines 3-4) : 20 synchronisations sans erreur critique.
    """
    count = 0
    for report in reversed(reports):
        if not report.clean:
            break
        count += 1
    return count


def _offer_ref(offer: SupplierOffer) -> str:
    return f"{offer.supplier_id}/{offer.supplier_sku}"


def _best(candidates: list[tuple[SupplierOffer, PriceDecision]]) -> tuple[SupplierOffer, PriceDecision]:
    """Offre retenue pour un produit : décision publiable d'abord, puis coût rendu le plus bas."""

    def key(item: tuple[SupplierOffer, PriceDecision]) -> tuple[int, Decimal, str]:
        offer, decision = item
        cost = decision.landed_cost if decision.landed_cost is not None else Decimal("Infinity")
        return (decision.status.severity, cost, _offer_ref(offer))

    return sorted(candidates, key=key)[0]


# ---------------------------------------------------------------------------- service


class SyncService:
    """Workflow « fournisseur → site » et synchronisation du stock local (simulation par défaut)."""

    def __init__(
        self,
        *,
        client: ShopifyClient,
        gate: GovernanceGate,
        incidents: IncidentManager,
        audit: AuditLog,
        price_history: PriceHistory | None = None,
        replacement_costs: ReplacementCostBook | None = None,
        clock: Callable[[], datetime] | None = None,
        actor: str = "agent-07-integrations",
    ) -> None:
        self.client = client
        self.gate = gate
        self.incidents = incidents
        self.audit = audit
        self.price_history = price_history if price_history is not None else PriceHistory()
        self.replacement_costs = replacement_costs if replacement_costs is not None else ReplacementCostBook()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.actor = actor
        self._lock = threading.Lock()
        self.history: list[SyncReport | StockSyncReport] = []

    # -- incidents -------------------------------------------------------------------
    def _incident(self, simulation: bool, out: list[str], **kwargs: Any) -> str:
        incident = self.incidents.open(actor=self.actor, actor_kind=ActorKind.AGENT, simulation=simulation, **kwargs)
        if incident.incident_id not in out:
            out.append(incident.incident_id)
        return incident.incident_id

    # -- cycle fournisseur → site ------------------------------------------------------
    def run_supplier_cycle(
        self,
        mapping: SupplierMapping | str | Path,
        source: Any,
        ctx: SyncContext,
        *,
        now: datetime | None = None,
        dry_run: bool = True,
        baseline: ImportBaseline | None = None,
        source_ts: datetime | None = None,
        run_id: str | None = None,
    ) -> SyncReport:
        """Exécute les 8 étapes BP §12 ; ``dry_run=True`` par défaut (aucune écriture externe)."""
        at = now or self._clock()
        if at.tzinfo is None or at.utcoffset() is None:
            raise SyncError("now doit porter un fuseau horaire")
        rid = run_id or f"SYNC-{at:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
        steps: list[StepResult] = []
        items: list[SyncItem] = []
        incidents: list[str] = []
        critical: list[str] = []
        params = ctx.rules.pricing
        supplier_id = mapping.supplier_id if isinstance(mapping, SupplierMapping) else str(mapping)
        if isinstance(mapping, Path) or (isinstance(mapping, str) and mapping.endswith((".yaml", ".yml"))):
            supplier_id = Path(str(mapping)).stem

        def finish(result: ImportResult | None) -> SyncReport:
            done = [s.step for s in steps]
            for step in SyncStep:
                if step not in done:
                    steps.append(StepResult(step=step, status="IGNORE", detail="étape non atteinte"))
            report = SyncReport(
                run_id=rid,
                supplier_id=result.supplier_id if result else supplier_id,
                dry_run=dry_run,
                started_at=at,
                finished_at=self._clock(),
                rules_version=ctx.rules.rules_version,
                import_status=result.status.value if result else None,
                source_ts=result.effective_source_ts if result else None,
                rows_read=result.rows_read if result else 0,
                offers_accepted=result.accepted_count if result else 0,
                rows_quarantined=result.quarantined_count if result else 0,
                steps=tuple(sorted(steps, key=lambda s: list(SyncStep).index(s.step))),
                items=tuple(items),
                incident_ids=tuple(incidents),
                critical_errors=tuple(critical),
                fictif=bool(result and result.fictif),
            )
            self.audit.append(
                actor=self.actor, actor_kind=ActorKind.AGENT, action="sync.cycle", entity="sync_run", entity_id=rid,
                dry_run=dry_run, autonomy_level=int(self.gate.autonomy.level),
                payload={
                    "supplier_id": report.supplier_id, "import_status": report.import_status,
                    "items": len(items), "incidents": list(incidents), "critical_errors": list(critical),
                    "steps": {s.step.value: s.status for s in report.steps},
                },
            )  # fmt: skip
            with self._lock:
                self.history.append(report)
            return report

        # 1. récupérer
        try:
            result = run_import(mapping, source, now=at, baseline=baseline, dry_run=dry_run, source_ts=source_ts)
        except MappingError as exc:
            steps.append(StepResult(step=SyncStep.FETCH, status="ECHEC", detail=str(exc)))
            self._incident(
                dry_run, incidents, code=IncidentCode.INC_03, supplier_id=supplier_id,
                cause=f"Dictionnaire de champs inutilisable : {exc}",
            )  # fmt: skip
            return finish(None)
        supplier_id = result.supplier_id
        steps.append(
            StepResult(
                step=SyncStep.FETCH,
                status="ECHEC" if result.status is ImportStatus.FAILED else "OK",
                detail=f"source {result.snapshot.source_kind.value} datée "
                f"{result.effective_source_ts.isoformat() if result.effective_source_ts else 'inconnue'}",
                count=result.rows_read,
            )
        )
        # 2. valider
        if result.status in (ImportStatus.FAILED, ImportStatus.QUARANTINED):
            steps.append(
                StepResult(
                    step=SyncStep.VALIDATE, status="ECHEC",
                    detail=f"import {result.status.value} : offres précédentes conservées ; motifs {result.reason_counts()}",
                )  # fmt: skip
            )
            self._incident(
                dry_run, incidents, code=IncidentCode.INC_03, supplier_id=supplier_id, fictif=result.fictif,
                cause=f"Import {result.status.value} ({', '.join(result.reason_counts()) or 'source illisible'}) : "
                "achats et nouvelles promesses bloqués pour cette source.",
                details={"run_id": rid, "escalation": result.escalation},
            )  # fmt: skip
            return finish(result)
        steps.append(
            StepResult(
                step=SyncStep.VALIDATE,
                status="AVERTISSEMENT" if result.quarantined else "OK",
                detail=f"{result.accepted_count} offre(s) valide(s), {result.quarantined_count} en quarantaine"
                + (f" (escalade {result.escalation})" if result.escalation else ""),
                count=result.accepted_count,
            )
        )
        if result.escalation:
            self._incident(
                dry_run, incidents, code=IncidentCode.INC_01, scope=IncidentScope.SOURCE, supplier_id=supplier_id,
                fictif=result.fictif, cause=f"Import avec anomalies de prix, devise ou base TVA : {result.reason_counts()}",
                details={"run_id": rid},
            )  # fmt: skip

        terms = set(ctx.sensitive_terms) | {supplier_id}
        for product in ctx.catalog_products:
            for link in product.supplier_links:
                terms.update({link.supplier_id, link.supplier_sku})
        for offer in result.offers:
            terms.update({offer.supplier_id, offer.supplier_sku})

        # 3. rapprocher
        index = CatalogIndex(ctx.catalog_products, ctx.table)
        matched: dict[str, list[tuple[SupplierOffer, Any]]] = {}
        match_counts = {s.value: 0 for s in MatchStatus}
        for offer in result.offers:
            match = match_offer_to_product(offer, index, table=ctx.table)
            match_counts[match.status.value] += 1
            if match.status is MatchStatus.MATCHED and match.product_id is not None:
                matched.setdefault(match.product_id, []).append((offer, match))
                continue
            inc_ids: list[str] = []
            if match.status is MatchStatus.AMBIGUOUS:
                self._incident(
                    dry_run, inc_ids, code=IncidentCode.INC_02, product_key=_offer_ref(offer), fictif=result.fictif,
                    cause=f"Identité ambiguë ({', '.join(match.reasons)}) ; candidats {', '.join(match.candidates)}",
                    details={"run_id": rid},
                )  # fmt: skip
                incidents.extend(i for i in inc_ids if i not in incidents)
            items.append(
                SyncItem(
                    offer_ref=_offer_ref(offer), match_status=match.status.value, plan_outcome=PlanOutcome.NOT_SENT.value,
                    incident_ids=tuple(inc_ids),
                    messages=("Nouvelle référence : brouillon interne, validation de la fiche requise."
                              if match.status is MatchStatus.NEW_DRAFT else "Identité ambiguë : brouillon, jamais publiée.",),
                )  # fmt: skip
            )
        steps.append(
            StepResult(
                step=SyncStep.MATCH,
                status="AVERTISSEMENT" if match_counts[MatchStatus.AMBIGUOUS.value] else "OK",
                detail=", ".join(f"{k} {v}" for k, v in match_counts.items()),
                count=match_counts[MatchStatus.MATCHED.value],
            )
        )

        # 4-5. coût rendu, prix et seuils
        decisions: dict[str, tuple[SupplierOffer, PriceDecision]] = {}
        stale_sources: set[str] = set()
        cost_unknown = 0
        price_counts: dict[str, int] = {}
        for pid, pairs in matched.items():
            listing = ctx.listings.get(pid)
            reference = price_reference_24h(
                self.price_history, pid, at, listing.current_price_chf if listing else None
            )
            evaluated: list[tuple[SupplierOffer, PriceDecision]] = []
            for offer, _match in pairs:
                ci = ctx.cost_inputs.get(offer.supplier_id, OfferCostInputs())
                previous = self.replacement_costs.latest(pid, offer.supplier_id)
                decision = evaluate_offer(
                    offer, params, now=at, fx_rate_to_chf=ci.fx_rate_to_chf, fx_source=ci.fx_source,
                    fx_date=ci.fx_date, inbound_freight_alloc=ci.inbound_freight_alloc,
                    customs_and_fees=ci.customs_and_fees, import_vat=ci.import_vat, order_qty=ci.order_qty,
                    market_ref=ctx.market_refs.get(pid), current_public=reference,
                    previous_cost=previous.unit_cost if previous else None,
                    expected_language=expected_language_for(offer.format),
                    max_age=ctx.rules.stock.max_age,
                )  # fmt: skip
                if decision.landed_cost is None:
                    cost_unknown += 1
                elif decision.restock_eligible and decision.landed_cost > 0 and not decision.has(Reason.PRICE_ANOMALY):
                    self.replacement_costs.update(
                        ReplacementCost(
                            product_key=pid, supplier_id=offer.supplier_id, unit_cost=decision.landed_cost,
                            source_ts=offer.source_ts, offer_ref=offer.raw_ref,
                        )  # fmt: skip
                    )
                if decision.has(Reason.STALE_OFFER):
                    stale_sources.add(offer.supplier_id)
                self.price_history.record_decision(pid, decision, at, actor=self.actor)
                evaluated.append((offer, decision))
                price_counts[decision.status.value] = price_counts.get(decision.status.value, 0) + 1
            decisions[pid] = _best(evaluated)
        steps.append(
            StepResult(
                step=SyncStep.COST,
                status="AVERTISSEMENT" if cost_unknown else "OK",
                detail=f"{sum(len(p) for p in matched.values())} offre(s) évaluée(s), {cost_unknown} coût(s) incomplet(s) "
                "(frais inconnus => brouillon)",
                count=sum(len(p) for p in matched.values()) - cost_unknown,
            )
        )
        steps.append(
            StepResult(
                step=SyncStep.PRICE,
                status="AVERTISSEMENT" if set(price_counts) - {"OK"} else "OK",
                detail=", ".join(f"{k} {v}" for k, v in sorted(price_counts.items())) or "aucune décision",
                count=price_counts.get("OK", 0),
            )
        )
        for sid in sorted(stale_sources):
            self._incident(
                dry_run, incidents, code=IncidentCode.INC_03, supplier_id=sid, fictif=result.fictif,
                cause="Offre(s) de plus de 24 h : aucun nouveau prix, achat ni promesse ; le stock local reste vendable.",
                details={"run_id": rid},
            )  # fmt: skip

        # 6-8. fiche, publication, vérification
        status, _triggers = self.gate.stoploss_status(at)
        blocked_products = set(status.blocked_products) if status is not None else set()
        listing_counts: dict[str, int] = {}
        written = refused = 0
        api_refused = False
        verify_ok = verify_ko = 0
        for pid, (offer, decision) in sorted(decisions.items()):
            listing = ctx.listings.get(pid)
            item_incidents: list[str] = []
            if listing is None:
                items.append(
                    SyncItem(
                        offer_ref=_offer_ref(offer), product_id=pid, match_status=MatchStatus.MATCHED.value,
                        decision_status=decision.status.value, decision_reasons=decision.reasons,
                        plan_outcome=PlanOutcome.NOT_SENT.value, messages=("Produit sans fiche validée : rien à publier.",),
                    )  # fmt: skip
                )
                continue
            for code in codes_for_reasons(decision.reasons):
                if code is IncidentCode.INC_03:
                    continue  # signalé une fois par source
                self._incident(
                    dry_run, item_incidents, code=code, product_key=pid, fictif=result.fictif or listing.fictif,
                    cause=f"Décision {decision.status.value} pour {_offer_ref(offer)} : {', '.join(decision.reasons)}",
                    details={"run_id": rid, "rules_version": decision.rules_version, "inputs_hash": decision.inputs_hash},
                )  # fmt: skip
            usable = None if decision.has(Reason.STALE_OFFER) else decision
            reference = price_reference_24h(self.price_history, pid, at, listing.current_price_chf)
            plan = build_publication(
                listing, usable, max_daily_change=params.max_daily_price_change, reference_price_24h=reference,
                price_validation=ctx.price_validations.get(pid), stoploss_blocked=pid in blocked_products,
                quarantined=self.incidents.is_quarantined(pid), sensitive_terms=sorted(terms), table=ctx.table,
                real_shop=not dry_run,
            )  # fmt: skip
            listing_counts[plan.outcome.value] = listing_counts.get(plan.outcome.value, 0) + 1
            if plan.violations:
                critical.append(f"{pid} : champ interne détecté dans la charge publique ({'; '.join(plan.violations)})")
                self._incident(
                    dry_run, item_incidents, code=IncidentCode.INC_07, product_key=pid,
                    cause="Champ interne ou donnée personnelle dans la charge publique (envoi bloqué).",
                    details={"run_id": rid, "violations": list(plan.violations)},
                )  # fmt: skip
            gate: GateDecision | None = None
            written_flag = replayed = False
            verified: bool | None = None
            messages = list(plan.messages)
            if plan.send and plan.action is not None and not api_refused:
                gate = self.gate.authorize(
                    WriteAction(plan.action), dry_run=dry_run, actor=self.actor, product_key=pid,
                    workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                )  # fmt: skip
                if gate.allowed:
                    try:
                        resp = self.client.product_set(
                            plan.product_input or {}, identifier=plan.identifier,
                            idempotency_key=derive_idempotency_key("productSet", plan.identifier, plan.product_input),
                            dry_run=dry_run, autonomy_level=gate.current_level,
                        )  # fmt: skip
                    except ShopifyAccessDeniedError as exc:
                        api_refused = True
                        refused += 1
                        messages.append(str(exc))
                        self._incident(
                            dry_run, item_incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                            cause=f"API boutique refusée : {exc}", details={"run_id": rid},
                        )  # fmt: skip
                    except ShopifyError as exc:
                        refused += 1
                        messages.append(f"{type(exc).__name__} : {exc}")
                        self._incident(
                            dry_run, item_incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                            cause=f"Écriture productSet en échec ({type(exc).__name__}) : {exc}", details={"run_id": rid},
                        )  # fmt: skip
                    else:
                        replayed = resp.replayed
                        if not resp.ok:
                            refused += 1
                            messages.extend(f"userError {e.code or ''} : {e.message}" for e in resp.user_errors)
                            self._incident(
                                dry_run, item_incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                                cause=f"productSet refusé pour {pid} : "
                                + "; ".join(e.message for e in resp.user_errors),
                                details={"run_id": rid},
                            )  # fmt: skip
                        else:
                            written_flag = not resp.dry_run
                            written += 1 if written_flag else 0
                            verified = self._verify(plan, pid, decision, at, dry_run, critical, item_incidents, rid)
                            if verified:
                                verify_ok += 1
                            else:
                                verify_ko += 1
                else:
                    messages.extend(gate.messages)
            elif api_refused and plan.send:
                messages.append("Non envoyé : API boutique refusée plus tôt dans ce cycle (workflow suspendu).")
            incidents.extend(i for i in item_incidents if i not in incidents)
            items.append(
                SyncItem(
                    offer_ref=_offer_ref(offer), product_id=pid, match_status=MatchStatus.MATCHED.value,
                    decision_status=decision.status.value, decision_reasons=decision.reasons,
                    plan_outcome=plan.outcome.value, action=plan.action, price_chf=plan.price_chf,
                    gate_allowed=gate.allowed if gate else None, gate_reasons=gate.reasons if gate else (),
                    written=written_flag, replayed=replayed, verified=verified, incident_ids=tuple(item_incidents),
                    messages=tuple(dict.fromkeys(messages)),
                )  # fmt: skip
            )
        steps.append(
            StepResult(
                step=SyncStep.LISTING,
                status="OK",
                detail=", ".join(f"{k} {v}" for k, v in sorted(listing_counts.items())) or "aucune fiche",
                count=sum(listing_counts.values()),
            )
        )
        steps.append(
            StepResult(
                step=SyncStep.PUBLISH,
                status="ECHEC" if api_refused else ("AVERTISSEMENT" if refused else "OK"),
                detail=("simulation : charges journalisées, rien envoyé" if dry_run else f"{written} écriture(s) réelle(s)")
                + (f", {refused} refus" if refused else "")
                + (" ; API boutique refusée : workflow suspendu" if api_refused else ""),
                count=written,
            )
        )
        steps.append(
            StepResult(
                step=SyncStep.VERIFY,
                status="ECHEC" if verify_ko else "OK",
                detail=f"{verify_ok} fiche(s) vérifiée(s), {verify_ko} écart(s) ; décisions journalisées",
                count=verify_ok,
            )
        )
        return finish(result)

    def _verify(
        self,
        plan: PublicationPlan,
        pid: str,
        decision: PriceDecision,
        at: datetime,
        dry_run: bool,
        critical: list[str],
        incidents: list[str],
        rid: str,
    ) -> bool:
        """Étape 8 : état réel (lecture Shopify) ou cohérence de la charge simulée ; prix journalisé."""
        problems: list[str] = []
        if plan.product_input is None or plan.price_chf is None:
            problems.append("charge absente")
        else:
            problems.extend(sensitive_violations(plan.product_input))
            variant_price = Decimal(plan.product_input["variants"][0]["price"])
            if variant_price != plan.price_chf:
                problems.append(f"prix de la charge {variant_price} ≠ prix du plan {plan.price_chf}")
            if not dry_run:
                try:
                    remote = self.client.product_by_handle(plan.handle)
                except ShopifyError as exc:
                    remote = None
                    problems.append(f"lecture de vérification impossible : {exc}")
                if remote is None and not problems:
                    problems.append("fiche introuvable après publication")
                elif remote is not None:
                    if plan.target_status is not None and remote.status != plan.target_status.value:
                        problems.append(f"statut boutique {remote.status} ≠ {plan.target_status.value}")
                    prices = {v.price for v in remote.variants if v.price is not None}
                    if prices != {plan.price_chf}:
                        problems.append(f"prix boutique {sorted(prices)} ≠ prix validé {plan.price_chf}")
        if problems:
            critical.append(f"{pid} : vérification après publication en échec ({'; '.join(problems)})")
            self._incident(
                dry_run, incidents, code=IncidentCode.INC_01, severity=Severity.CRITIQUE, product_key=pid,
                cause="Prix ou statut public différent de la décision validée : " + "; ".join(problems),
                details={"run_id": rid},
            )  # fmt: skip
            return False
        if not dry_run and plan.price_changed and plan.price_chf is not None:
            try:
                self.price_history.publish(
                    pid, plan.price_chf, at, self.actor, validated=plan.price_source == "HUMAN_VALIDATED",
                    decision=decision if plan.price_source == "ENGINE" else None,
                    note=f"sync {rid}",
                )  # fmt: skip
            except PricingError as exc:
                critical.append(f"{pid} : prix publié hors décision du moteur ({exc})")
                return False
        self.audit.append(
            actor=self.actor, actor_kind=ActorKind.AGENT, action="sync.verify", entity="product", entity_id=pid,
            dry_run=dry_run,
            payload={"run_id": rid, "outcome": plan.outcome.value, "price_chf": plan.price_chf,
                     "rules_version": plan.rules_version, "inputs_hash": plan.inputs_hash},
        )  # fmt: skip
        return True

    # -- stock local -------------------------------------------------------------------
    def push_stock(
        self,
        entries: Sequence[tuple[CatalogListing, StockLevel]],
        *,
        location_id: str,
        remote_levels: Mapping[str, RemoteInventoryLevel] | None = None,
        now: datetime | None = None,
        dry_run: bool = True,
        run_id: str | None = None,
        max_conflict_retries: int = 1,
    ) -> StockSyncReport:
        """Pousse le stock local vendable vers Shopify avec compare-and-swap (simulation par défaut).

        ``remote_levels`` : quantités Shopify lues juste avant (sinon lues par le client si
        configuré ; en simulation sans lecture, supposées nulles et signalées ``assumed``).
        """
        at = now or self._clock()
        rid = run_id or f"STOCK-{at:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
        incidents: list[str] = []
        critical: list[str] = []
        lines: list[StockPushLine] = []
        items = [(listing, level) for listing, level in entries]
        for listing, level in items:
            if listing.shopify_inventory_item_id is None:
                raise SyncError(f"{listing.product_key} : shopify_inventory_item_id absent")
            if listing.public_sku != level.sku:
                raise SyncError(f"{listing.product_key} : SKU fiche {listing.public_sku} ≠ SKU stock {level.sku}")
        remote = dict(remote_levels or {})
        missing = [l.shopify_inventory_item_id for l, _ in items if l.shopify_inventory_item_id not in remote]
        if missing and self.client.configured:
            remote.update(self.client.inventory_levels([m for m in missing if m], location_id))
        status, _ = self.gate.stoploss_status(at)
        blocked_products = set(status.blocked_products) if status is not None else set()
        for listing, level in items:
            item_id = listing.shopify_inventory_item_id or ""
            pid = listing.product_key
            rem = remote.get(item_id)
            if rem is None:
                if not dry_run:
                    raise SyncError(f"{pid} : quantité Shopify inconnue, écriture réelle impossible sans lecture")
                rem = RemoteInventoryLevel(inventory_item_id=item_id, available=0, committed=0, assumed=True)
            blocked = pid in blocked_products or self.incidents.is_quarantined(pid)
            target = stock_target(level, rem, blocked=blocked)
            reasons: list[str] = []
            line_incidents: list[str] = []
            if blocked:
                reasons.append("BLOQUE_STOPLOSS_OU_QUARANTAINE : 0 publié (vente bloquée)")
            if target.oversell and not rem.assumed:
                critical.append(f"{pid} : survente (engagé Shopify {rem.committed} > stock physique vendable)")
                self._incident(
                    dry_run, line_incidents, code=IncidentCode.INC_06, product_key=pid,
                    cause=f"Survente : {rem.committed} unité(s) engagée(s) sur Shopify pour "
                    f"{level.on_hand - level.damaged} en stock physique vendable.",
                    details={"run_id": rid, "sku": level.sku},
                )  # fmt: skip
            if target.target_available > level.sellable and not blocked:
                critical.append(f"{pid} : cible {target.target_available} > vendable local {level.sellable}")
            action: Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR"] = "NONE"
            written = replayed = False
            if target.target_available != rem.available:
                # Bloquer la vente (0 publié) est protecteur ; toute autre écriture de stock exige le niveau 2.
                protective = blocked and target.target_available < rem.available
                gate = self.gate.authorize(
                    WriteAction.UNPUBLISH_PRODUCT if protective else WriteAction.SYNC_STOCK, dry_run=dry_run,
                    actor=self.actor, product_key=pid, workflow=WORKFLOW_STOCK,
                )  # fmt: skip
                if not gate.allowed:
                    action = "REFUSED"
                    reasons.extend(gate.reasons)
                else:
                    action, written, replayed, rem = self._set_inventory(
                        listing, level, rem, target, location_id, dry_run, gate.current_level, max_conflict_retries,
                        reasons, blocked=blocked,
                    )  # fmt: skip
                    if action == "CONFLICT":
                        self._incident(
                            dry_run, line_incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_STOCK,
                            cause=f"Conflit de concurrence répété sur {level.sku} : quantité Shopify modifiée pendant "
                            "la synchronisation.",
                            details={"run_id": rid},
                        )  # fmt: skip
                    elif action == "ERROR":
                        self._incident(
                            dry_run, line_incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_STOCK,
                            cause=f"Écriture de stock {level.sku} refusée : {'; '.join(reasons[-1:])}",
                            details={"run_id": rid},
                        )  # fmt: skip
            incidents.extend(i for i in line_incidents if i not in incidents)
            lines.append(
                StockPushLine(
                    sku=level.sku, product_key=pid, inventory_item_id=item_id, local_on_hand=level.on_hand,
                    local_sellable=level.sellable, remote_available=rem.available, remote_committed=rem.committed,
                    remote_assumed=rem.assumed, target_available=target.target_available, action=action,
                    written=written, replayed=replayed, reasons=tuple(reasons), discrepancies=target.discrepancies,
                    incident_ids=tuple(line_incidents),
                )  # fmt: skip
            )
        report = StockSyncReport(
            run_id=rid, at=at, dry_run=dry_run, location_id=location_id, lines=tuple(lines),
            incident_ids=tuple(incidents), critical_errors=tuple(critical),
        )  # fmt: skip
        self.audit.append(
            actor=self.actor, actor_kind=ActorKind.AGENT, action="sync.stock", entity="sync_run", entity_id=rid,
            dry_run=dry_run, autonomy_level=int(self.gate.autonomy.level),
            payload={
                "lines": len(lines), "written": report.written_count, "conflicts": len(report.conflicts),
                "discrepancies": sum(len(line.discrepancies) for line in lines), "critical_errors": list(critical),
            },
        )  # fmt: skip
        with self._lock:
            self.history.append(report)
        return report

    def _set_inventory(
        self,
        listing: CatalogListing,
        level: StockLevel,
        rem: RemoteInventoryLevel,
        target: StockTarget,
        location_id: str,
        dry_run: bool,
        autonomy_level: int,
        retries: int,
        reasons: list[str],
        *,
        blocked: bool,
    ) -> tuple[Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR"], bool, bool, RemoteInventoryLevel]:
        """Écriture CAS ; en cas de conflit, relit Shopify, recalcule et réessaie (``retries`` fois)."""
        item_id = listing.shopify_inventory_item_id or ""
        current = rem
        for attempt in range(retries + 1):
            change = InventoryChange(
                inventory_item_id=item_id, location_id=location_id, quantity=target.target_available,
                change_from_quantity=current.available,
            )  # fmt: skip
            uri = f"pokeshop://stock-sync/{level.sku}/v{level.version}"
            key = derive_idempotency_key("inventorySetQuantities", change, uri)
            try:
                resp = self.client.inventory_set_quantities(
                    [change], reason="correction", reference_document_uri=uri, idempotency_key=key,
                    dry_run=dry_run, autonomy_level=autonomy_level,
                )  # fmt: skip
            except ShopifyError as exc:
                reasons.append(f"{type(exc).__name__} : {exc}")
                return "ERROR", False, False, current
            if resp.ok:
                return "SET", not resp.dry_run, resp.replayed, current
            if not resp.concurrency_conflict:
                reasons.append("; ".join(f"{e.code or ''} {e.message}" for e in resp.user_errors))
                return "ERROR", False, resp.replayed, current
            reasons.append(f"conflit de concurrence (essai {attempt + 1})")
            if dry_run or not self.client.configured:
                return "CONFLICT", False, False, current
            fresh = self.client.inventory_levels([item_id], location_id).get(item_id)
            if fresh is None:
                return "CONFLICT", False, False, current
            current = fresh
            target = stock_target(level, fresh, blocked=blocked)
            if target.target_available == current.available:
                return "NONE", False, False, current
        return "CONFLICT", False, False, current
