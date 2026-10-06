"""Orchestration « fournisseur → site » en 8 étapes (BP §12) et synchronisation du stock local.

Cycle fournisseur → site (:meth:`SyncService.run_supplier_cycle`), **en simulation par défaut** :

1. récupérer le flux autorisé et dater la source (:func:`pokeshop.importers.run_import`) ;
2. valider devise, TVA, unité, langue et quantité, **comparé au dernier import** du fournisseur
   (référence persistée :class:`ImportBaselineStore` : ×10, import incomplet, devise, HT/TTC ;
   première écriture réelle d'un fournisseur refusée sans import précédent) ;
3. rapprocher la référence exacte (:func:`pokeshop.catalog.match_offer_to_product`) ;
4. évaluer l'offre et le coût rendu (frais connus seulement : rien n'est inventé) ;
5. calculer le prix et tester les seuils (:func:`pokeshop.pricing.evaluate_offer`) ;
6. générer ou actualiser la fiche (:func:`pokeshop.publish.build_publication`) : statut public
   **recalculé** depuis le registre du stock local et l'allocation ferme, approbations de prix de
   la propriétaire lues dans le registre du moteur (jamais sous le plancher dur sans C18),
   noms des fournisseurs ajoutés aux termes interdits dans la charge publique ;
7. publier uniquement si les données, le stock et la gouvernance le permettent
   (:class:`pokeshop.autonomy.GovernanceGate` puis ``productSet``) ;
8. vérifier l'état réel sur le site et journaliser la décision.

Chaque anomalie ouvre un incident (quarantaine de la référence ou suspension de la source).
Une offre périmée ne change jamais un prix public ; une panne de flux ne touche jamais au stock
local confirmé (ce module ne modifie aucun stock à partir d'une offre fournisseur).

Pré-drop (:meth:`SyncService.publish_predrop`, décision de la propriétaire du 6.10.2026) : fiche jumelle
« Réservation garantie » (:func:`pokeshop.publish.build_predrop_publication`) publiée, vérifiée et retirée au drop ;
son inventaire = réservations encore ouvertes du registre du moteur, diminué des commandes Shopify pas encore
enregistrées (:func:`predrop_inventory_target`), écrit en compare-and-swap ; une baisse est protectrice. La fiche
normale ne reçoit que les métachamps d'information du pré-drop (``predrop_lookup``), jamais une variante.

Stock local (:meth:`SyncService.push_stock`) : **Shopify reste l'autorité des réservations de
vente** (BP §6). Le service pousse ``available = physique − max(réservé service, engagé
Shopify) − endommagé − sécurité`` avec ``changeFromQuantity`` (compare-and-swap), conserve les
mouvements et **signale** les écarts de réservation au lieu de les écraser. Référence bloquée
par le stop-loss produit ou en quarantaine : 0 publié (vente bloquée, aucun faux stock).
"""

from __future__ import annotations

import re
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

from .audit import ActorKind, AuditLog, StateJournal, StateStoreError
from .autonomy import GateDecision, GovernanceGate, WriteAction
from .catalog import (
    CatalogIndex,
    CatalogProduct,
    ExtensionTable,
    MatchStatus,
    expected_language_for,
    match_offer_to_product,
)
from .costs import PriceHistory, ReplacementCostBook
from .errors import PokeshopError, PricingError
from .importers import (
    ImportBaseline,
    ImportResult,
    ImportStatus,
    MappingError,
    SupplierMapping,
    load_mapping,
    next_baseline,
    run_import,
)
from .incidents import IncidentCode, IncidentManager, IncidentScope, Severity, codes_for_reasons
from .models import (
    FrozenModel,
    PriceDecision,
    PriceEventKind,
    PricingParams,
    Reason,
    ReplacementCost,
    StockLevel,
    SupplierOffer,
)
from .pricing import evaluate_offer
from .publish import (
    HARD_BLOCKER_CODES,
    CatalogListing,
    ListingApproval,
    PlanOutcome,
    PredropPublication,
    PriceValidation,
    PublicationPlan,
    PublishedState,
    SensitiveFieldError,
    ShopStatus,
    StockStatus,
    _fold,
    assert_protective_payload,
    build_predrop_publication,
    build_publication,
    predrop_reservation_sku,
    reservation_publication_key,
    sensitive_violations,
    stock_status_for,
)
from .rules import RuleSet
from .stock import StockRegistry, availability_promise
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
    "PredropPublishReport",
    "predrop_inventory_target",
    "ImportBaselineStore",
    "BaselinePersistenceError",
    "ShopPublication",
    "ShopPublicationBook",
    "ShopStatePersistenceError",
    "supplier_terms",
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
    """Approbations de prix de la propriétaire **lues dans le registre du moteur**
    (:class:`pokeshop.publish.PriceApprovalBook`), jamais reçues dans un corps de requête."""
    validations: Mapping[str, ListingApproval] = field(default_factory=dict)
    """Validations de fiches de la propriétaire (registre ``catalog_approvals``) par ``product_id`` ;
    appliquées seulement au contenu exact de fiche validé (jamais un champ de la fiche)."""
    sensitive_terms: Collection[str] = ()
    record_replacement_costs: bool = True
    """Revue R5 (R4-DOC-09, R2-NEW-01 b) : faux pour un cycle qui lit un catalogue ou des frais **du corps**
    (simulation) — il évalue les offres mais n'inscrit jamais de coût de remplacement (référence du moteur)."""
    cost_inputs_recorded_by: Mapping[str, str] = field(default_factory=dict)
    """Par ``supplier_id`` : acteur qui a posé au registre les frais utilisés (provenance inscrite avec le coût
    de remplacement, :attr:`pokeshop.models.ReplacementCost.fees_recorded_by`)."""


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
    source_sha256: str | None = None
    """Empreinte du contenu de la source importée (None si la source n'a pas été lue)."""

    @property
    def offers_costed(self) -> int:
        """Offres rapprochées dont le coût rendu a été calculé (étape 4)."""
        return next((s.count for s in self.steps if s.step is SyncStep.COST), 0)

    @property
    def clean(self) -> bool:
        """Cycle **PROPRE** : aucune « erreur critique » (``GATES_GO_NO_GO.md`` §1) **et** au moins une
        offre au coût rendu calculé. Un cycle qui n'a rien évalué (VIDE) n'est pas propre (revue E2E-07)."""
        return not self.critical_errors and self.offers_costed > 0

    @property
    def empty(self) -> bool:
        """Cycle **VIDE** : aucune erreur critique mais aucune offre évaluée (ni compté, ni remis à zéro)."""
        return not self.critical_errors and self.offers_costed == 0

    @property
    def product_ids(self) -> tuple[str, ...]:
        """Produits du catalogue rapprochés dans ce cycle (cible d'un test de correction d'incident)."""
        return tuple(sorted({i.product_id for i in self.items if i.product_id}))

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
            f"offres {self.offers_accepted} · quarantaine {self.rows_quarantined}"
            + (" · **FICTIF**" if self.fictif else ""),
            f"Erreurs critiques : **{len(self.critical_errors)}**",
            "",
            "| Étape | Statut | Détail |",
            "|---|---|---|",
        ]
        for s in self.steps:
            lines.append(f"| {STEP_LABELS_FR[s.step]} | {s.status} | {s.detail.replace('|', '/')} |")
        if self.items:
            lines += [
                "",
                "| Offre | Produit | Rapprochement | Décision | Fiche | Prix public | Écrit |",
                "|---|---|---|---|---|---:|---|",
            ]
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


class PredropPublishReport(FrozenModel):
    """Compte rendu de la publication d'une fiche de réservation pré-drop (interne : contient la cible d'inventaire)."""

    run_id: str
    at: datetime
    dry_run: bool
    predrop_id: str
    product_key: str
    handle: str
    phase: str
    plan_outcome: str
    action: str | None = None
    price_chf: Decimal | None = None
    blockers: tuple[str, ...] = ()
    reviews: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    gate_allowed: bool | None = None
    gate_reasons: tuple[str, ...] = ()
    written: bool = False
    replayed: bool = False
    verified: bool | None = None
    inventory_action: Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR", "SKIPPED"] = "SKIPPED"
    inventory_target: int | None = None
    inventory_written: bool = False
    inventory_reasons: tuple[str, ...] = ()
    incident_ids: tuple[str, ...] = ()
    critical_errors: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        """Vrai sans erreur critique."""
        return not self.critical_errors


def predrop_inventory_target(predrop: PredropPublication, remote: RemoteInventoryLevel) -> int:
    """Inventaire ``available`` de la fiche de réservation (jamais publié en texte) — fermé par défaut.

    Réservations fermées ou retirées : 0. Sinon réservations encore ouvertes du registre du moteur, diminuées des
    unités engagées sur Shopify au-delà des réservations confirmées enregistrées (commandes payées pas encore
    relevées par le workflow 02, ou non servies en attente de remboursement) : jamais une promesse au-delà du quota.
    """
    if not predrop.accepting:
        return 0
    excess = max(0, remote.committed - predrop.reservations_committed)
    return max(0, predrop.reservations_available - excess)


# ---------------------------------------------------------------- références d'import


class BaselinePersistenceError(SyncError, StateStoreError):
    """Référence « dernier import » non enregistrée ou non relue : contrôles vs dernier import impossibles."""


class ImportBaselineStore:
    """Référence « dernier import » par fournisseur (journal d'état ``import_baselines``).

    Elle porte les prix unitaires, le nombre de lignes et le sha256 du dernier import ACCEPTED ou
    PARTIAL ; :func:`pokeshop.importers.run_import` la compare au nouvel import (prix ×10 ou ÷10,
    devise ou HT/TTC changés, import incomplet, contenu identique non daté). Écriture d'abord,
    application ensuite ; un import rejeté ne la modifie jamais.
    """

    STREAM = "import_baselines"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, ImportBaseline] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> ImportBaselineStore:
        """Relit les références (:class:`BaselinePersistenceError` si illisible)."""
        book = cls()
        try:
            records = store.load()
        except StateStoreError as exc:
            raise BaselinePersistenceError(f"références d'import : {exc}") from exc
        for n, record in enumerate(records, start=1):
            try:
                item = ImportBaseline.model_validate(record["baseline"])
            except (KeyError, TypeError, ValueError) as exc:
                raise BaselinePersistenceError(f"références d'import : enregistrement {n} illisible") from exc
            book._items[item.supplier_id] = item
        book._store = store
        return book

    def get(self, supplier_id: str) -> ImportBaseline | None:
        """Référence du fournisseur (None = jamais importé)."""
        with self._lock:
            return self._items.get(supplier_id)

    def suppliers(self) -> tuple[str, ...]:
        """Fournisseurs ayant une référence."""
        with self._lock:
            return tuple(sorted(self._items))

    def update(self, result: ImportResult) -> ImportBaseline | None:
        """Applique un import (inchangée s'il est rejeté) ; persistée avant d'être retenue."""
        with self._lock:
            current = self._items.get(result.supplier_id)
            updated = next_baseline(current, result)
            if updated is None or updated == current:
                return current
            if self._store is not None:
                try:
                    self._store.append({"baseline": updated.model_dump(mode="json")})
                except StateStoreError as exc:
                    raise BaselinePersistenceError(f"référence d'import non enregistrée ({exc})") from exc
            self._items[result.supplier_id] = updated
            return updated


class ShopStatePersistenceError(SyncError, StateStoreError):
    """État publié non enregistré ou non relu : dépublication protectrice par le registre impossible."""


class ShopPublication(FrozenModel):
    """État d'une fiche **réellement écrit et vérifié** sur la boutique (aucun coût, aucun fournisseur)."""

    product_id: str = Field(min_length=1)
    shopify_product_id: str = Field(pattern=r"^gid://shopify/Product/\d+$")
    status: Literal["DRAFT", "ACTIVE"]
    handle: str = Field(min_length=1)
    run_id: str
    recorded_at: datetime
    price_chf: Decimal | None = Field(default=None, gt=0)
    """Dernier prix réellement écrit et vérifié (None : enregistrement ancien ou dépublication sans prix connu)."""

    def state(self) -> PublishedState:
        """État publié pour :func:`pokeshop.publish.build_publication` (seule source d'identifiant et de prix)."""
        return PublishedState(
            shopify_product_id=self.shopify_product_id, status=ShopStatus(self.status), price_chf=self.price_chf
        )


class ShopPublicationBook:
    """Fiches publiées par le moteur (journal d'état ``shop_publications``), relues au démarrage.

    Pourquoi (revue SEC-09) : avec le flux standard, le catalogue vient du registre
    (``POST /catalog/items``) sans ``shopify_product_id`` ni ``shopify_status`` ; la dépublication
    protectrice (quarantaine, stop-loss produit) n'était donc jamais atteinte et une fiche publiée
    restait achetable. Après chaque écriture **vérifiée**, le moteur inscrit ici l'identifiant
    Shopify et le statut ; une référence bloquée est alors dépubliée par son identifiant.
    """

    STREAM = "shop_publications"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, ShopPublication] = {}
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> ShopPublicationBook:
        """Relit le journal (:class:`ShopStatePersistenceError` s'il est illisible)."""
        book = cls()
        try:
            records = store.load()
        except StateStoreError as exc:
            raise ShopStatePersistenceError(f"fiches publiées : {exc}") from exc
        for n, record in enumerate(records, start=1):
            try:
                item = ShopPublication.model_validate(record["publication"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ShopStatePersistenceError(f"fiches publiées : enregistrement {n} illisible") from exc
            book._items[item.product_id] = item
        book._store = store
        return book

    def get(self, product_id: str) -> ShopPublication | None:
        """Dernier état écrit et vérifié de la fiche (None = jamais publiée par le moteur)."""
        with self._lock:
            return self._items.get(product_id)

    def all(self) -> tuple[ShopPublication, ...]:
        """Fiches connues, par produit."""
        with self._lock:
            return tuple(self._items[k] for k in sorted(self._items))

    def record(self, item: ShopPublication) -> ShopPublication:
        """Inscrit l'état publié (écrit d'abord, appliqué ensuite ; sans effet si identique)."""
        with self._lock:
            current = self._items.get(item.product_id)
            if current is not None and (current.shopify_product_id, current.status, current.handle,
                                        current.price_chf) == (
                item.shopify_product_id,
                item.status,
                item.handle,
                item.price_chf,
            ):  # fmt: skip
                return current
            if self._store is not None:
                try:
                    self._store.append({"publication": item.model_dump(mode="json")})
                except StateStoreError as exc:
                    raise ShopStatePersistenceError(f"état publié non enregistré ({exc})") from exc
            self._items[item.product_id] = item
            return item


_GENERIC_SUPPLIER_WORDS = frozenset(
    {"suisse", "schweiz", "svizzera", "swiss", "france", "europe", "sarl", "gmbh", "distribution", "fictif",
     "grossiste", "generic", "generique", "modele", "trading", "games", "store", "shop", "boutique", "essai"}
)


def supplier_terms(supplier_id: str, supplier_name: str = "") -> set[str]:
    """Termes internes d'un fournisseur (identifiant, nom, segments ≥ 4 caractères non génériques).

    Ajoutés aux termes refusés dans toute charge publique (SEC-08) : un texte public ne cite jamais
    un fournisseur (ex. « acheté chez Asmodee »).
    """
    terms = {supplier_id}
    name = re.sub(r"\(.*?\)", " ", supplier_name).strip()
    if len(name) >= 3:
        terms.add(name)
    for segment in re.split(r"[\W_]+", f"{supplier_id} {name}"):
        if len(segment) >= 4 and _fold(segment) not in _GENERIC_SUPPLIER_WORDS:
            terms.add(segment)
    return terms


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
        e
        for e in history.events(product_key)
        if e.kind in (PriceEventKind.PUBLISHED, PriceEventKind.ROLLED_BACK) and e.price is not None
    ]
    before = [e for e in events if e.at <= cutoff]
    if before:
        return before[-1].price
    if events:
        return events[0].price
    return fallback


def stock_target(local: StockLevel, remote: RemoteInventoryLevel, *, blocked: bool = False) -> StockTarget:
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
    """Synchronisations PROPRES consécutives (diagnostic en mémoire), en partant de la plus récente.

    Un cycle VIDE (rien évalué) ne compte pas et n'interrompt pas la série ; une erreur critique la
    remet à zéro. Le **critère de recette** BP §13 (20 synchronisations sans erreur critique) n'est
    pas ce diagnostic : c'est :meth:`pokeshop.catalogue_sync.SyncRunLog.consecutive_clean_runs`
    (journal persisté, cycles réels seulement : données non FICTIVES, catalogue du registre, source
    datée et de contenu distinct), exposé par ``GET /sync/history``.
    """
    count = 0
    for report in reversed(reports):
        if report.critical_errors:
            break
        if isinstance(report, SyncReport) and report.empty:
            continue
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
        test_store: bool = False,
        stock: StockRegistry | None = None,
        baselines: ImportBaselineStore | None = None,
        publications: ShopPublicationBook | None = None,
        predrop_lookup: Callable[[str, datetime], PredropPublication | None] | None = None,
    ) -> None:
        self.client = client
        self.predrop_lookup = predrop_lookup
        """Pré-drop d'une référence (registre du moteur) : métachamps d'information de la fiche normale."""
        self.publications = publications if publications is not None else ShopPublicationBook()
        """Fiches écrites et vérifiées (identifiant Shopify, statut) : base de la dépublication protectrice."""
        self.stock = stock
        """Registre du stock local (statut public recalculé) ; None = stock inconnu, donc ``rupture``."""
        self.baselines = baselines if baselines is not None else ImportBaselineStore()
        """Références « dernier import » (persistées par l'API) : contrôles ×10, incomplet, devise, HT/TTC."""
        self.test_store = test_store
        """Boutique de développement (recette) : données FICTIVES admises en écriture réelle."""
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
        """Exécute les 8 étapes BP §12 ; ``dry_run=True`` par défaut (aucune écriture externe).

        ``baseline`` absent : référence « dernier import » du registre :attr:`baselines`, mise à jour
        après chaque import ACCEPTED ou PARTIAL. Écriture réelle sans référence (premier import d'un
        fournisseur) : :class:`SyncError` (simulation obligatoire d'abord, fermé par défaut).
        """
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
        if baseline is None:
            baseline = self.baselines.get(supplier_id)
            if baseline is None and not dry_run:
                raise SyncError(
                    f"{supplier_id} : aucune référence « dernier import » — premier import en simulation obligatoire "
                    "(contrôles ×10, import incomplet, devise et HT/TTC impossibles sans elle)"
                )

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
                source_sha256=result.snapshot.checksum_sha256 if result else None,
            )
            self.audit.append(
                actor=self.actor,
                actor_kind=ActorKind.AGENT,
                action="sync.cycle",
                entity="sync_run",
                entity_id=rid,
                dry_run=dry_run,
                autonomy_level=int(self.gate.autonomy.level),
                payload={
                    "supplier_id": report.supplier_id,
                    "import_status": report.import_status,
                    "items": len(items),
                    "incidents": list(incidents),
                    "critical_errors": list(critical),
                    "steps": {s.step.value: s.status for s in report.steps},
                },
            )
            with self._lock:
                self.history.append(report)
            return report

        # 1. récupérer (import « réel » seulement vers la boutique de production : dictionnaire VALIDE exigé)
        production = not dry_run and not self.test_store
        try:
            result = run_import(
                mapping,
                source,
                now=at,
                baseline=baseline,
                dry_run=not production,
                source_ts=source_ts,
                extensions=ctx.table,
            )
        except MappingError as exc:
            steps.append(StepResult(step=SyncStep.FETCH, status="ECHEC", detail=str(exc)))
            self._incident(
                dry_run,
                incidents,
                code=IncidentCode.INC_03,
                supplier_id=supplier_id,
                cause=f"Dictionnaire de champs inutilisable : {exc}",
            )
            return finish(None)
        supplier_id = result.supplier_id
        self.baselines.update(result)  # inchangée si l'import est rejeté
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
                    step=SyncStep.VALIDATE,
                    status="ECHEC",
                    detail=f"import {result.status.value} : offres précédentes conservées ; "
                    f"motifs {result.reason_counts()}",
                )
            )
            self._incident(
                dry_run,
                incidents,
                code=IncidentCode.INC_03,
                supplier_id=supplier_id,
                fictif=result.fictif,
                cause=f"Import {result.status.value} ({', '.join(result.reason_counts()) or 'source illisible'}) : "
                "achats et nouvelles promesses bloqués pour cette source.",
                details={"run_id": rid, "escalation": result.escalation},
            )
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
                dry_run,
                incidents,
                code=IncidentCode.INC_01,
                scope=IncidentScope.SOURCE,
                supplier_id=supplier_id,
                fictif=result.fictif,
                cause=f"Import avec anomalies de prix, devise ou base TVA : {result.reason_counts()}",
                details={"run_id": rid},
                contain=False,  # lignes fautives déjà en quarantaine ; les autres offres restent exploitables
            )

        terms = set(ctx.sensitive_terms) | {supplier_id}
        try:
            mapping_obj = mapping if isinstance(mapping, SupplierMapping) else load_mapping(mapping)
            terms |= supplier_terms(mapping_obj.supplier_id, mapping_obj.supplier_name)
        except MappingError:  # pragma: no cover - déjà chargé par run_import
            pass
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
                    dry_run,
                    inc_ids,
                    code=IncidentCode.INC_02,
                    product_key=_offer_ref(offer),
                    fictif=result.fictif,
                    cause=f"Identité ambiguë ({', '.join(match.reasons)}) ; candidats {', '.join(match.candidates)}",
                    details={"run_id": rid},
                )
                incidents.extend(i for i in inc_ids if i not in incidents)
            items.append(
                SyncItem(
                    offer_ref=_offer_ref(offer),
                    match_status=match.status.value,
                    plan_outcome=PlanOutcome.NOT_SENT.value,
                    incident_ids=tuple(inc_ids),
                    messages=(
                        "Nouvelle référence : brouillon interne, validation de la fiche requise."
                        if match.status is MatchStatus.NEW_DRAFT
                        else "Identité ambiguë : brouillon, jamais publiée.",
                    ),
                )
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
            known_pub = self.publications.get(pid)
            reference = price_reference_24h(self.price_history, pid, at, known_pub.price_chf if known_pub else None)
            evaluated: list[tuple[SupplierOffer, PriceDecision]] = []
            for offer, _match in pairs:
                ci = ctx.cost_inputs.get(offer.supplier_id, OfferCostInputs())
                previous = self.replacement_costs.latest(pid, offer.supplier_id)
                decision = evaluate_offer(
                    offer,
                    params,
                    now=at,
                    fx_rate_to_chf=ci.fx_rate_to_chf,
                    fx_source=ci.fx_source,
                    fx_date=ci.fx_date,
                    inbound_freight_alloc=ci.inbound_freight_alloc,
                    customs_and_fees=ci.customs_and_fees,
                    import_vat=ci.import_vat,
                    order_qty=ci.order_qty,
                    market_ref=ctx.market_refs.get(pid),
                    current_public=reference,
                    previous_cost=previous.unit_cost if previous else None,
                    expected_language=expected_language_for(offer.format),
                    max_age=ctx.rules.stock.max_age,
                )
                if decision.landed_cost is None:
                    cost_unknown += 1
                elif (
                    ctx.record_replacement_costs
                    and decision.restock_eligible
                    and decision.landed_cost > 0
                    and not decision.has(Reason.PRICE_ANOMALY)
                ):
                    # Revue R5 (R4-DOC-09) : jamais depuis un catalogue ou des frais du corps (simulation).
                    self.replacement_costs.update(
                        ReplacementCost(
                            product_key=pid,
                            supplier_id=offer.supplier_id,
                            unit_cost=decision.landed_cost,
                            source_ts=offer.source_ts,
                            offer_ref=offer.raw_ref,
                            fees_recorded_by=ctx.cost_inputs_recorded_by.get(offer.supplier_id),
                        )
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
                detail=f"{sum(len(p) for p in matched.values())} offre(s) évaluée(s), "
                f"{cost_unknown} coût(s) incomplet(s) (frais inconnus => brouillon)",
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
                dry_run,
                incidents,
                code=IncidentCode.INC_03,
                supplier_id=sid,
                fictif=result.fictif,
                cause="Offre(s) de plus de 24 h : aucun nouveau prix, achat ni promesse ; "
                "le stock local reste vendable.",
                details={"run_id": rid},
            )

        # 6-8. fiche, publication, vérification
        status, _triggers = self.gate.stoploss_status(at)
        blocked_products = set(status.blocked_products) if status is not None else set()
        listing_counts: dict[str, int] = {}

        def keys_of(pid: str) -> set[str]:
            # Revue R4 (R3-NEW-01) : quarantaine et stop-loss produit valent pour toutes les clés de la référence
            # (product_id, listing.product_key) — une entrée ancienne incohérente n'y échappe jamais.
            listing = ctx.listings.get(pid)
            return {pid, listing.product_key} if listing is not None else {pid}

        def is_blocked(pid: str) -> bool:
            return bool(keys_of(pid) & blocked_products)

        def is_quarantined(pid: str) -> bool:
            return any(self.incidents.is_quarantined(k) for k in keys_of(pid))
        state = {"written": 0, "refused": 0, "api_refused": False, "verify_ok": 0, "verify_ko": 0}

        def plan_for(
            pid: str,
            listing: CatalogListing,
            decision: PriceDecision | None,
            published: PublishedState | None,
            reference: Decimal | None,
            stock_now: StockStatus,
        ) -> PublicationPlan:
            return build_publication(
                listing,
                decision,
                max_daily_change=params.max_daily_price_change,
                reference_price_24h=reference,
                price_validation=ctx.price_validations.get(pid),
                params=params,
                now=at,
                stoploss_blocked=is_blocked(pid),
                quarantined=is_quarantined(pid),
                sensitive_terms=sorted(terms),
                table=ctx.table,
                real_shop=production,
                stock_status=stock_now,
                published=published,  # registre du moteur, jamais la fiche (revue R3 SEC-09)
                validations=ctx.validations.get(pid),  # registre de la propriétaire (revue R2-NEW-05)
                predrop=self.predrop_lookup(pid, at) if self.predrop_lookup is not None else None,
            )

        def resolve_plan(
            pid: str,
            listing: CatalogListing,
            decision: PriceDecision | None,
            stock_now: StockStatus,
            item_incidents: list[str],
        ) -> PublicationPlan:
            """Plan avec l'état publié du **registre du moteur** ; référence bloquée inconnue du registre :
            état réel relu sur la boutique (écriture réelle) pour la dépublier (revue SEC-09)."""
            known = self.publications.get(pid)
            published = known.state() if known is not None else None
            reference = price_reference_24h(self.price_history, pid, at, published.price_chf if published else None)
            plan = plan_for(pid, listing, decision, published, reference, stock_now)
            if plan.outcome is PlanOutcome.NOT_SENT and published is None and set(plan.blockers) & HARD_BLOCKER_CODES:
                remote = self._known_shop_state(pid, plan.handle, dry_run, critical, item_incidents, rid)
                if remote is not None:
                    plan = plan_for(pid, listing, decision, remote, reference, stock_now)
            return plan

        def apply(
            pid: str,
            plan: PublicationPlan,
            decision: PriceDecision | None,
            item_incidents: list[str],
            *,
            offer_ref: str,
            match_status: str,
        ) -> None:
            listing_counts[plan.outcome.value] = listing_counts.get(plan.outcome.value, 0) + 1
            if plan.violations:
                critical.append(f"{pid} : champ interne détecté dans la charge publique ({'; '.join(plan.violations)})")
                self._incident(
                    dry_run,
                    item_incidents,
                    code=IncidentCode.INC_07,
                    product_key=pid,
                    cause="Champ interne ou donnée personnelle dans la charge publique (envoi bloqué).",
                    details={"run_id": rid, "violations": list(plan.violations)},
                )
            gate: GateDecision | None = None
            written_flag = replayed = False
            verified: bool | None = None
            messages = list(plan.messages)
            if plan.send and plan.action is not None and not state["api_refused"]:
                gate = self.gate.authorize(
                    WriteAction(plan.action),
                    dry_run=dry_run,
                    actor=self.actor,
                    product_key=pid,
                    workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                )
                if gate.allowed:
                    try:
                        protective = plan.outcome is PlanOutcome.UNPUBLISH
                        if protective:
                            assert_protective_payload(plan.product_input or {})
                        resp = self.client.product_set(
                            plan.product_input or {},
                            identifier=plan.identifier,
                            idempotency_key=derive_idempotency_key("productSet", plan.identifier, plan.product_input),
                            dry_run=dry_run,
                            autonomy_level=gate.current_level,
                            protective=protective,
                        )
                    except SensitiveFieldError as exc:
                        state["refused"] += 1
                        critical.append(f"{pid} : charge publique refusée par le client ({exc})")
                        self._incident(
                            dry_run,
                            item_incidents,
                            code=IncidentCode.INC_07,
                            product_key=pid,
                            cause="Champ interne détecté au dernier contrôle avant envoi (rien n'a été envoyé).",
                            details={"run_id": rid, "violations": list(exc.violations)},
                        )
                    except ShopifyAccessDeniedError as exc:
                        state["api_refused"] = True
                        state["refused"] += 1
                        messages.append(str(exc))
                        self._incident(
                            dry_run,
                            item_incidents,
                            code=IncidentCode.INC_08,
                            workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                            cause=f"API boutique refusée : {exc}",
                            details={"run_id": rid},
                        )
                    except ShopifyError as exc:
                        state["refused"] += 1
                        messages.append(f"{type(exc).__name__} : {exc}")
                        self._incident(
                            dry_run,
                            item_incidents,
                            code=IncidentCode.INC_08,
                            workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                            cause=f"Écriture productSet en échec ({type(exc).__name__}) : {exc}",
                            details={"run_id": rid},
                        )
                    else:
                        replayed = resp.replayed
                        if not resp.ok:
                            state["refused"] += 1
                            messages.extend(f"userError {e.code or ''} : {e.message}" for e in resp.user_errors)
                            self._incident(
                                dry_run,
                                item_incidents,
                                code=IncidentCode.INC_08,
                                workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                                cause=f"productSet refusé pour {pid} : "
                                + "; ".join(e.message for e in resp.user_errors),
                                details={"run_id": rid},
                            )
                        else:
                            written_flag = not resp.dry_run
                            state["written"] += 1 if written_flag else 0
                            # Client en simulation (POKESHOP_DRY_RUN=true) : rien n'a été écrit, vérification simulée.
                            simulated = dry_run or resp.dry_run
                            verified = self._verify(plan, pid, decision, at, simulated, critical, item_incidents, rid)
                            if verified:
                                state["verify_ok"] += 1
                                if written_flag:
                                    self._remember_publication(plan, pid, resp, at, rid, critical)
                            else:
                                state["verify_ko"] += 1
                else:
                    messages.extend(gate.messages)
            elif state["api_refused"] and plan.send:
                messages.append("Non envoyé : API boutique refusée plus tôt dans ce cycle (workflow suspendu).")
            incidents.extend(i for i in item_incidents if i not in incidents)
            items.append(
                SyncItem(
                    offer_ref=offer_ref,
                    product_id=pid,
                    match_status=match_status,
                    decision_status=decision.status.value if decision is not None else None,
                    decision_reasons=decision.reasons if decision is not None else (),
                    plan_outcome=plan.outcome.value,
                    action=plan.action,
                    price_chf=plan.price_chf,
                    gate_allowed=gate.allowed if gate else None,
                    gate_reasons=gate.reasons if gate else (),
                    written=written_flag,
                    replayed=replayed,
                    verified=verified,
                    incident_ids=tuple(item_incidents),
                    messages=tuple(dict.fromkeys(messages)),
                )
            )

        for pid, (offer, decision) in sorted(decisions.items()):
            listing = ctx.listings.get(pid)
            item_incidents: list[str] = []
            if listing is None:
                items.append(
                    SyncItem(
                        offer_ref=_offer_ref(offer),
                        product_id=pid,
                        match_status=MatchStatus.MATCHED.value,
                        decision_status=decision.status.value,
                        decision_reasons=decision.reasons,
                        plan_outcome=PlanOutcome.NOT_SENT.value,
                        messages=("Produit sans fiche validée : rien à publier.",),
                    )
                )
                continue
            for code in codes_for_reasons(decision.reasons):
                if code is IncidentCode.INC_03:
                    continue  # signalé une fois par source
                self._incident(
                    dry_run,
                    item_incidents,
                    code=code,
                    product_key=pid,
                    fictif=result.fictif or listing.fictif,
                    cause=f"Décision {decision.status.value} pour {_offer_ref(offer)} : {', '.join(decision.reasons)}",
                    details={
                        "run_id": rid,
                        "rules_version": decision.rules_version,
                        "inputs_hash": decision.inputs_hash,
                    },
                )
            usable = None if decision.has(Reason.STALE_OFFER) else decision
            stock_now = self.stock_status(listing, [o for o, _ in matched.get(pid, ())], at, ctx)
            plan = resolve_plan(pid, listing, usable, stock_now, item_incidents)
            apply(pid, plan, decision, item_incidents, offer_ref=_offer_ref(offer), match_status=MatchStatus.MATCHED.value)

        # Revue R3 SEC-09 (b) : une référence bloquée (quarantaine, stop-loss produit) dont l'offre manque dans
        # la livraison du jour est **aussi** dépubliée si le registre (ou la boutique) la dit publiée.
        for pid, listing in sorted(ctx.listings.items()):
            if pid in decisions or not (is_blocked(pid) or is_quarantined(pid)):
                continue
            item_incidents = []
            plan = resolve_plan(pid, listing, None, self.stock_status(listing, [], at, ctx), item_incidents)
            if plan.outcome is not PlanOutcome.UNPUBLISH:
                continue  # jamais publiée (ou déjà en brouillon) : rien à faire
            apply(pid, plan, None, item_incidents, offer_ref=f"{pid} (aucune offre ce jour)", match_status="SANS_OFFRE")
        written, refused = state["written"], state["refused"]
        api_refused = bool(state["api_refused"])
        verify_ok, verify_ko = state["verify_ok"], state["verify_ko"]
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
                detail=(
                    "simulation : charges journalisées, rien envoyé" if dry_run else f"{written} écriture(s) réelle(s)"
                )
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

    def _known_shop_state(
        self,
        pid: str,
        handle: str,
        dry_run: bool,
        critical: list[str],
        incidents: list[str],
        rid: str,
    ) -> PublishedState | None:
        """État publié d'une fiche bloquée : registre du moteur, sinon boutique (écriture réelle) ; jamais la fiche.

        Lecture impossible en écriture réelle : erreur critique (la fiche pourrait rester achetable).
        """
        known = self.publications.get(pid)
        if known is not None:
            return known.state()
        if dry_run:
            return None
        try:
            remote = self.client.product_by_handle(handle)
        except ShopifyError as exc:
            critical.append(f"{pid} : état réel de la fiche illisible ({exc}) : dépublication protectrice impossible")
            self._incident(
                dry_run,
                incidents,
                code=IncidentCode.INC_08,
                workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                cause=f"Lecture de la fiche {handle} impossible avant dépublication protectrice : {exc}",
                details={"run_id": rid},
            )
            return None
        if remote is None or remote.status not in ("DRAFT", "ACTIVE"):
            return None
        try:
            return PublishedState(shopify_product_id=remote.id, status=ShopStatus(remote.status))
        except ValueError:
            return None

    def _remember_publication(
        self, plan: PublicationPlan, pid: str, resp: Any, at: datetime, rid: str, critical: list[str]
    ) -> None:
        """Inscrit l'identifiant Shopify et le statut d'une écriture réelle vérifiée (revue SEC-09)."""
        gid = (plan.identifier or {}).get("id") or ((resp.root().get("product") or {}).get("id"))
        status = plan.target_status.value if plan.target_status is not None else None
        if not isinstance(gid, str) or status is None:
            return
        previous = self.publications.get(pid)
        # Prix réellement écrit et vérifié ; une dépublication (statut seul) garde le dernier prix connu.
        price = plan.price_chf if plan.price_chf is not None else (previous.price_chf if previous is not None else None)
        try:
            self.publications.record(
                ShopPublication(
                    product_id=pid, shopify_product_id=gid, status=status, handle=plan.handle, run_id=rid, recorded_at=at,
                    price_chf=price,
                )
            )  # fmt: skip
        except ShopStatePersistenceError as exc:
            critical.append(f"{pid} : état publié non enregistré ({exc}) : dépublication protectrice compromise")
        except ValueError:
            return

    def stock_status(
        self, listing: CatalogListing, offers: Sequence[SupplierOffer], at: datetime, ctx: SyncContext
    ) -> StockStatus:
        """Statut public recalculé (E2E-12) : stock local vendable du registre, allocation ferme fraîche.

        Jamais le statut déclaré par l'appelant : sans registre, le stock local est inconnu (``rupture``).
        """
        sellable = self.stock.sellable(listing.public_sku) if self.stock is not None else 0
        firm = 0
        if listing.public_sku.endswith("-PRECO") and offers:
            promise = availability_promise(
                local_sellable=0, offers=offers, now=at, preorders_enabled=True, max_age=ctx.rules.stock.max_age
            )
            firm = promise.firm_allocation
        return stock_status_for(listing, local_sellable=sellable, firm_allocation=firm)

    def _verify(
        self,
        plan: PublicationPlan,
        pid: str,
        decision: PriceDecision | None,
        at: datetime,
        dry_run: bool,
        critical: list[str],
        incidents: list[str],
        rid: str,
    ) -> bool:
        """Étape 8 : état réel (lecture Shopify) ou cohérence de la charge simulée ; prix journalisé.

        Dépublication protectrice (charge ``{"status": "DRAFT"}``) : seul le statut est vérifié.
        """
        problems: list[str] = []
        if plan.outcome is PlanOutcome.UNPUBLISH:
            if plan.product_input != {"status": "DRAFT"}:
                problems.append("dépublication : charge autre que le statut")
            elif not dry_run:
                try:
                    remote = self.client.product_by_id((plan.identifier or {}).get("id", ""))
                except ShopifyError as exc:
                    remote = None
                    problems.append(f"lecture de vérification impossible : {exc}")
                if remote is None and not problems:
                    problems.append("fiche introuvable après dépublication")
                elif remote is not None and remote.status != "DRAFT":
                    problems.append(f"statut boutique {remote.status} ≠ DRAFT")
        elif plan.product_input is None or plan.price_chf is None:
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
                dry_run,
                incidents,
                code=IncidentCode.INC_01,
                severity=Severity.CRITIQUE,
                product_key=pid,
                cause="Prix ou statut public différent de la décision validée : " + "; ".join(problems),
                details={"run_id": rid},
            )
            return False
        if not dry_run and plan.price_changed and plan.price_chf is not None:
            try:
                self.price_history.publish(
                    pid,
                    plan.price_chf,
                    at,
                    self.actor,
                    validated=plan.price_source == "HUMAN_VALIDATED",
                    decision=decision,
                    note=f"sync {rid}"
                    + (f" ; approbation {plan.price_approval_id}" if plan.price_approval_id else ""),
                )
            except PricingError as exc:
                critical.append(f"{pid} : prix publié hors décision du moteur ({exc})")
                return False
        self.audit.append(
            actor=self.actor,
            actor_kind=ActorKind.AGENT,
            action="sync.verify",
            entity="product",
            entity_id=pid,
            dry_run=dry_run,
            payload={
                "run_id": rid,
                "outcome": plan.outcome.value,
                "price_chf": plan.price_chf,
                "price_source": plan.price_source,
                "price_approval_id": plan.price_approval_id,
                "stock_status": plan.stock_status,
                "rules_version": plan.rules_version,
                "inputs_hash": plan.inputs_hash,
            },
        )
        return True

    # -- pré-drop : fiche de réservation ---------------------------------------------------
    def publish_predrop(
        self,
        listing: CatalogListing,
        predrop: PredropPublication,
        *,
        params: PricingParams,
        landed_cost: Decimal | None,
        validations: ListingApproval | None,
        table: ExtensionTable | None = None,
        sensitive_terms: Collection[str] = (),
        location_id: str | None = None,
        remote_level: RemoteInventoryLevel | None = None,
        now: datetime | None = None,
        dry_run: bool = True,
        run_id: str | None = None,
        normal_handle: str | None = None,
    ) -> PredropPublishReport:
        """Publie (ou retire) la fiche « Réservation garantie » d'un pré-drop puis fixe son inventaire.

        Simulation par défaut. Écriture : porte de gouvernance (niveau, gel, stop-loss) puis ``productSet`` contrôlé
        par la liste blanche ; vérification de l'état réel (statut, prix) ; état inscrit au registre des fiches publiées
        sous :func:`pokeshop.publish.reservation_publication_key`. Inventaire : :func:`predrop_inventory_target` en
        compare-and-swap (``changeFromQuantity``) ; une baisse est protectrice (permise pendant un gel), une hausse
        exige le niveau 2. Aucun prix n'est inscrit dans l'historique des prix de la fiche normale.
        """
        at = now or self._clock()
        if at.tzinfo is None or at.utcoffset() is None:
            raise SyncError("now doit porter un fuseau horaire")
        rid = run_id or f"PREDROP-{at:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
        pid = listing.product_key
        key = reservation_publication_key(pid)
        incidents: list[str] = []
        critical: list[str] = []
        messages: list[str] = []
        status, _triggers = self.gate.stoploss_status(at)
        blocked = pid in set(status.blocked_products) if status is not None else False
        quarantined = self.incidents.is_quarantined(pid)
        known = self.publications.get(key)
        published = known.state() if known is not None else None
        production = not dry_run and not self.test_store
        plan = build_predrop_publication(
            listing,
            predrop,
            params=params,
            landed_cost=landed_cost,
            stoploss_blocked=blocked,
            quarantined=quarantined,
            sensitive_terms=sensitive_terms,
            table=table,
            real_shop=production,
            published=published,
            validations=validations,
            normal_handle=normal_handle or (normal.handle if (normal := self.publications.get(pid)) else None),
        )
        messages.extend(plan.messages)
        if plan.violations:
            critical.append(f"{pid} : champ interne dans la charge de réservation ({'; '.join(plan.violations)})")
            self._incident(dry_run, incidents, code=IncidentCode.INC_07, product_key=pid,
                           cause="Champ interne ou donnée personnelle dans la fiche de réservation (envoi bloqué).",
                           details={"run_id": rid, "violations": list(plan.violations)})  # fmt: skip
        gate: GateDecision | None = None
        written = replayed = False
        verified: bool | None = None
        variant_item: str | None = None
        if plan.send and plan.action is not None:
            gate = self.gate.authorize(WriteAction(plan.action), dry_run=dry_run, actor=self.actor, product_key=pid,
                                       workflow=WORKFLOW_SUPPLIER_TO_SHOP)  # fmt: skip
            if not gate.allowed:
                messages.extend(gate.messages)
            else:
                protective = plan.outcome is PlanOutcome.UNPUBLISH
                resp = None
                try:
                    if protective:
                        assert_protective_payload(plan.product_input or {})
                    resp = self.client.product_set(
                        plan.product_input or {},
                        identifier=plan.identifier,
                        idempotency_key=derive_idempotency_key("productSet", plan.identifier, plan.product_input),
                        dry_run=dry_run,
                        autonomy_level=gate.current_level,
                        protective=protective,
                    )
                except SensitiveFieldError as exc:
                    critical.append(f"{pid} : fiche de réservation refusée par le client ({exc})")
                    self._incident(dry_run, incidents, code=IncidentCode.INC_07, product_key=pid,
                                   cause="Champ interne détecté au dernier contrôle avant envoi (rien n'a été envoyé).",
                                   details={"run_id": rid, "violations": list(exc.violations)})  # fmt: skip
                except ShopifyError as exc:
                    messages.append(f"{type(exc).__name__} : {exc}")
                    self._incident(dry_run, incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                                   cause=f"Fiche de réservation {plan.handle} : écriture productSet en échec ({exc})",
                                   details={"run_id": rid})  # fmt: skip
                if resp is not None and not resp.ok:
                    messages.extend(f"userError {e.code or ''} : {e.message}" for e in resp.user_errors)
                    self._incident(dry_run, incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                                   cause=f"productSet refusé pour la fiche de réservation {plan.handle} : "
                                   + "; ".join(e.message for e in resp.user_errors),
                                   details={"run_id": rid})  # fmt: skip
                elif resp is not None:
                    replayed = resp.replayed
                    written = not resp.dry_run
                    simulated = dry_run or resp.dry_run
                    verified, variant_item = self._verify_reservation(
                        plan, pid, predrop, listing, simulated, resp, critical, incidents, rid
                    )
                    if verified and written:
                        self._remember_reservation(plan, key, resp, at, rid, critical)
        inventory_action: Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR", "SKIPPED"] = "SKIPPED"
        inventory_reasons: list[str] = []
        target: int | None = None
        inventory_written = False
        written_ok = gate is not None and gate.allowed and bool(verified)
        # Fiche déjà en ligne dont la mise à jour est refusée (niveau, gel) : l'inventaire suit quand même le registre —
        # une baisse est protectrice (permise à tout niveau), une hausse reste soumise à la porte (niveau 2).
        live_unchanged = gate is not None and not gate.allowed and published is not None \
            and published.status is ShopStatus.ACTIVE
        if plan.outcome is PlanOutcome.SEND_ACTIVE and (written_ok or live_unchanged):
            (inventory_action, target, inventory_written) = self._set_reservation_inventory(
                predrop, listing, variant_item, location_id, remote_level, dry_run, at, rid, critical, incidents,
                inventory_reasons, handle=plan.handle,
            )  # fmt: skip
        elif plan.outcome is PlanOutcome.UNPUBLISH:
            inventory_reasons.append("fiche de réservation retirée (brouillon) : plus aucune réservation achetable")
        report = PredropPublishReport(
            run_id=rid,
            at=at,
            dry_run=dry_run,
            predrop_id=predrop.predrop_id,
            product_key=pid,
            handle=plan.handle,
            phase=predrop.phase,
            plan_outcome=plan.outcome.value,
            action=plan.action,
            price_chf=plan.price_chf,
            blockers=plan.blockers,
            reviews=plan.reviews,
            messages=tuple(dict.fromkeys(messages)),
            gate_allowed=gate.allowed if gate is not None else None,
            gate_reasons=gate.reasons if gate is not None else (),
            written=written,
            replayed=replayed,
            verified=verified,
            inventory_action=inventory_action,
            inventory_target=target,
            inventory_written=inventory_written,
            inventory_reasons=tuple(inventory_reasons),
            incident_ids=tuple(incidents),
            critical_errors=tuple(critical),
        )
        self.audit.append(
            actor=self.actor,
            actor_kind=ActorKind.AGENT,
            action="sync.predrop_publish",
            entity="predrop",
            entity_id=predrop.predrop_id,
            dry_run=dry_run,
            autonomy_level=int(self.gate.autonomy.level),
            payload={"run_id": rid, "outcome": report.plan_outcome, "phase": report.phase, "written": written,
                     "verified": verified, "inventory_action": inventory_action, "inventory_target": target,
                     "critical_errors": list(critical)},
        )  # fmt: skip
        return report

    def _verify_reservation(
        self,
        plan: PublicationPlan,
        pid: str,
        predrop: PredropPublication,
        listing: CatalogListing,
        dry_run: bool,
        resp: Any,
        critical: list[str],
        incidents: list[str],
        rid: str,
    ) -> tuple[bool, str | None]:
        """État réel de la fiche de réservation (statut, prix, SKU) ; renvoie (vérifiée, article d'inventaire)."""
        problems: list[str] = []
        item: str | None = None
        sku = predrop_reservation_sku(listing.public_sku, predrop.drop_date)
        if plan.outcome is PlanOutcome.UNPUBLISH:
            if plan.product_input != {"status": "DRAFT"}:
                problems.append("retrait : charge autre que le statut")
            elif not dry_run:
                try:
                    remote = self.client.product_by_id((plan.identifier or {}).get("id", ""))
                except ShopifyError as exc:
                    remote = None
                    problems.append(f"lecture de vérification impossible : {exc}")
                if remote is None and not problems:
                    problems.append("fiche de réservation introuvable après retrait")
                elif remote is not None and remote.status != "DRAFT":
                    problems.append(f"statut boutique {remote.status} ≠ DRAFT")
        elif plan.product_input is None or plan.price_chf is None:
            problems.append("charge absente")
        else:
            problems.extend(sensitive_violations(plan.product_input))
            variant = plan.product_input["variants"][0]
            if Decimal(variant["price"]) != plan.price_chf or variant["inventoryItem"]["sku"] != sku:
                problems.append("prix ou SKU de la charge ≠ plan")
            if not dry_run:
                try:
                    remote = self.client.product_by_handle(plan.handle)
                except ShopifyError as exc:
                    remote = None
                    problems.append(f"lecture de vérification impossible : {exc}")
                if remote is None and not problems:
                    problems.append("fiche de réservation introuvable après publication")
                elif remote is not None:
                    if plan.target_status is not None and remote.status != plan.target_status.value:
                        problems.append(f"statut boutique {remote.status} ≠ {plan.target_status.value}")
                    match = [v for v in remote.variants if v.sku == sku]
                    if len(remote.variants) != 1 or not match or match[0].price != plan.price_chf:
                        problems.append(f"variante boutique ≠ réservation {sku} à {plan.price_chf}")
                    else:
                        item = match[0].inventory_item_id
        if problems:
            critical.append(f"{pid} : vérification de la fiche de réservation en échec ({'; '.join(problems)})")
            self._incident(dry_run, incidents, code=IncidentCode.INC_01, severity=Severity.CRITIQUE, product_key=pid,
                           cause="Fiche de réservation pré-drop différente du plan validé : " + "; ".join(problems),
                           details={"run_id": rid, "predrop_id": predrop.predrop_id})  # fmt: skip
            return False, None
        self.audit.append(actor=self.actor, actor_kind=ActorKind.AGENT, action="sync.predrop_verify", entity="predrop",
                          entity_id=predrop.predrop_id, dry_run=dry_run,
                          payload={"run_id": rid, "outcome": plan.outcome.value, "price_chf": plan.price_chf,
                                   "phase": predrop.phase})  # fmt: skip
        return True, item

    def _remember_reservation(
        self, plan: PublicationPlan, key: str, resp: Any, at: datetime, rid: str, critical: list[str]
    ) -> None:
        """Inscrit l'identifiant Shopify et le statut de la fiche de réservation (dépublication par identifiant)."""
        gid = (plan.identifier or {}).get("id") or ((resp.root().get("product") or {}).get("id"))
        status = plan.target_status.value if plan.target_status is not None else None
        if not isinstance(gid, str) or status is None:
            return
        previous = self.publications.get(key)
        price = plan.price_chf if plan.price_chf is not None else (previous.price_chf if previous is not None else None)
        try:
            self.publications.record(ShopPublication(product_id=key, shopify_product_id=gid, status=status,
                                                     handle=plan.handle, run_id=rid, recorded_at=at, price_chf=price))  # fmt: skip
        except ShopStatePersistenceError as exc:
            critical.append(f"{key} : état publié non enregistré ({exc}) : retrait au drop compromis")
        except ValueError:
            return

    def _set_reservation_inventory(
        self,
        predrop: PredropPublication,
        listing: CatalogListing,
        item_id: str | None,
        location_id: str | None,
        remote_level: RemoteInventoryLevel | None,
        dry_run: bool,
        at: datetime,
        rid: str,
        critical: list[str],
        incidents: list[str],
        reasons: list[str],
        *,
        handle: str | None = None,
    ) -> tuple[Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR", "SKIPPED"], int | None, bool]:
        """Inventaire de la fiche de réservation en compare-and-swap ; (action, cible, écrit ?).

        Article d'inventaire : celui relu à la vérification, sinon celui de la fiche en ligne (lecture par handle,
        variante au SKU de la réservation). Inconnu en écriture réelle : rien n'est écrit (erreur critique).
        """
        item = item_id or (remote_level.inventory_item_id if remote_level is not None else None)
        if item is None and handle is not None and not dry_run and self.client.configured:
            sku = predrop_reservation_sku(listing.public_sku, predrop.drop_date)
            try:
                remote_product = self.client.product_by_handle(handle)
            except ShopifyError as exc:
                reasons.append(f"lecture de la fiche de réservation impossible : {exc}")
                remote_product = None
            if remote_product is not None:
                item = next((v.inventory_item_id for v in remote_product.variants if v.sku == sku), None)
        if location_id is None:
            reasons.append("emplacement Shopify non configuré (POKESHOP_SHOPIFY_LOCATION_ID) : inventaire non fixé")
            if not dry_run:
                critical.append(f"{listing.product_key} : inventaire de la fiche de réservation non fixé (emplacement)")
            return "SKIPPED", None, False
        remote = remote_level
        if remote is None and item is not None and self.client.configured:
            try:
                remote = self.client.inventory_levels([item], location_id).get(item)
            except ShopifyError as exc:
                reasons.append(f"lecture de l'inventaire impossible : {exc}")
                remote = None
        if remote is None:
            if not dry_run:
                critical.append(f"{listing.product_key} : quantité Shopify de la réservation inconnue, rien n'est écrit")
                return "ERROR", None, False
            assumed = RemoteInventoryLevel(inventory_item_id=item or "gid://shopify/InventoryItem/0", available=0,
                                           committed=0, assumed=True)  # fmt: skip
            target = predrop_inventory_target(predrop, assumed)
            reasons.append("simulation : article d'inventaire de la réservation inconnu (fiche pas encore créée), "
                           f"cible {target} unité(s) calculée, rien n'est écrit")  # fmt: skip
            return "SKIPPED", target, False
        target = predrop_inventory_target(predrop, remote)
        if target == remote.available:
            return "NONE", target, False
        protective = target < remote.available  # moins de réservations promises : acte protecteur
        gate = self.gate.authorize(
            WriteAction.UNPUBLISH_PRODUCT if protective else WriteAction.SYNC_STOCK,
            dry_run=dry_run, actor=self.actor, product_key=listing.product_key, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
        )  # fmt: skip
        if not gate.allowed:
            reasons.extend(gate.reasons)
            return "REFUSED", target, False
        change = InventoryChange(inventory_item_id=remote.inventory_item_id, location_id=location_id, quantity=target,
                                 change_from_quantity=remote.available)  # fmt: skip
        uri = f"pokeshop://predrop/{predrop.predrop_id}/{at:%Y%m%dT%H%M%S}"
        try:
            resp = self.client.inventory_set_quantities(
                [change], reason="correction", reference_document_uri=uri,
                idempotency_key=derive_idempotency_key("inventorySetQuantities", change, uri), dry_run=dry_run,
                autonomy_level=gate.current_level,
            )  # fmt: skip
        except ShopifyError as exc:
            reasons.append(f"{type(exc).__name__} : {exc}")
            self._incident(dry_run, incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                           cause=f"Inventaire de la réservation {predrop.predrop_id} refusé : {exc}",
                           details={"run_id": rid})  # fmt: skip
            return "ERROR", target, False
        if resp.ok:
            return "SET", target, not resp.dry_run
        if resp.concurrency_conflict:
            reasons.append("conflit de concurrence : quantité Shopify modifiée pendant l'écriture (relu au cycle suivant)")
            self._incident(dry_run, incidents, code=IncidentCode.INC_08, workflow=WORKFLOW_SUPPLIER_TO_SHOP,
                           cause=f"Conflit de concurrence sur l'inventaire de la réservation {predrop.predrop_id}",
                           details={"run_id": rid})  # fmt: skip
            return "CONFLICT", target, False
        reasons.append("; ".join(f"{e.code or ''} {e.message}" for e in resp.user_errors))
        return "ERROR", target, False

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
        missing = [li.shopify_inventory_item_id for li, _ in items if li.shopify_inventory_item_id not in remote]
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
                    dry_run,
                    line_incidents,
                    code=IncidentCode.INC_06,
                    product_key=pid,
                    cause=f"Survente : {rem.committed} unité(s) engagée(s) sur Shopify pour "
                    f"{level.on_hand - level.damaged} en stock physique vendable.",
                    details={"run_id": rid, "sku": level.sku},
                )
            if target.target_available > level.sellable and not blocked:
                critical.append(f"{pid} : cible {target.target_available} > vendable local {level.sellable}")
            action: Literal["SET", "NONE", "REFUSED", "CONFLICT", "ERROR"] = "NONE"
            written = replayed = False
            if target.target_available != rem.available:
                # Bloquer la vente (0 publié) est protecteur ; toute autre écriture de stock exige le niveau 2.
                protective = blocked and target.target_available < rem.available
                gate = self.gate.authorize(
                    WriteAction.UNPUBLISH_PRODUCT if protective else WriteAction.SYNC_STOCK,
                    dry_run=dry_run,
                    actor=self.actor,
                    product_key=pid,
                    workflow=WORKFLOW_STOCK,
                )
                if not gate.allowed:
                    action = "REFUSED"
                    reasons.extend(gate.reasons)
                else:
                    action, written, replayed, rem = self._set_inventory(
                        listing,
                        level,
                        rem,
                        target,
                        location_id,
                        dry_run,
                        gate.current_level,
                        max_conflict_retries,
                        reasons,
                        blocked=blocked,
                    )
                    if action == "CONFLICT":
                        self._incident(
                            dry_run,
                            line_incidents,
                            code=IncidentCode.INC_08,
                            workflow=WORKFLOW_STOCK,
                            cause=f"Conflit de concurrence répété sur {level.sku} : quantité Shopify modifiée pendant "
                            "la synchronisation.",
                            details={"run_id": rid},
                        )
                    elif action == "ERROR":
                        self._incident(
                            dry_run,
                            line_incidents,
                            code=IncidentCode.INC_08,
                            workflow=WORKFLOW_STOCK,
                            cause=f"Écriture de stock {level.sku} refusée : {'; '.join(reasons[-1:])}",
                            details={"run_id": rid},
                        )
            incidents.extend(i for i in line_incidents if i not in incidents)
            lines.append(
                StockPushLine(
                    sku=level.sku,
                    product_key=pid,
                    inventory_item_id=item_id,
                    local_on_hand=level.on_hand,
                    local_sellable=level.sellable,
                    remote_available=rem.available,
                    remote_committed=rem.committed,
                    remote_assumed=rem.assumed,
                    target_available=target.target_available,
                    action=action,
                    written=written,
                    replayed=replayed,
                    reasons=tuple(reasons),
                    discrepancies=target.discrepancies,
                    incident_ids=tuple(line_incidents),
                )
            )
        report = StockSyncReport(
            run_id=rid,
            at=at,
            dry_run=dry_run,
            location_id=location_id,
            lines=tuple(lines),
            incident_ids=tuple(incidents),
            critical_errors=tuple(critical),
        )
        self.audit.append(
            actor=self.actor,
            actor_kind=ActorKind.AGENT,
            action="sync.stock",
            entity="sync_run",
            entity_id=rid,
            dry_run=dry_run,
            autonomy_level=int(self.gate.autonomy.level),
            payload={
                "lines": len(lines),
                "written": report.written_count,
                "conflicts": len(report.conflicts),
                "discrepancies": sum(len(line.discrepancies) for line in lines),
                "critical_errors": list(critical),
            },
        )
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
                inventory_item_id=item_id,
                location_id=location_id,
                quantity=target.target_available,
                change_from_quantity=current.available,
            )
            uri = f"pokeshop://stock-sync/{level.sku}/v{level.version}"
            key = derive_idempotency_key("inventorySetQuantities", change, uri)
            try:
                resp = self.client.inventory_set_quantities(
                    [change],
                    reason="correction",
                    reference_document_uri=uri,
                    idempotency_key=key,
                    dry_run=dry_run,
                    autonomy_level=autonomy_level,
                )
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
