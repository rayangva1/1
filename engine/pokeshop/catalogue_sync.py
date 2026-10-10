"""Registres de la synchronisation fournisseur → site : catalogue validé, frais connus, cycles exécutés.

Pourquoi (revue E2E-07) : le workflow n8n 01 lançait ``POST /sync/run`` sans catalogue ni frais ; le
moteur rapprochait alors 0 offre, n'en évaluait aucune et déclarait pourtant le cycle « propre ». Le
critère de recette « 20 synchronisations sans erreur critique » (BP §13, gate 3.6) se remplissait
sans qu'aucun prix ne soit jamais calculé. Ce module fournit :

* :class:`CatalogRegistry` — catalogue validé (produit, liens fournisseur, fiche) et frais connus par
  fournisseur, **persistés** (journaux d'état ``sync_catalog`` et ``sync_cost_inputs``), lus par
  ``/sync/run`` quand le corps n'en fournit pas. Aucun taux de change n'y est déclaré : il vient du
  registre des taux de la propriétaire (``POST /fx/rates``) au moment du cycle, sinon le coût reste
  incomplet (brouillon, fermé par défaut).
* :class:`SyncRunLog` — résumé persisté de chaque cycle (journal ``sync_runs``) et compteur
  :meth:`SyncRunLog.consecutive_clean_runs` : un cycle n'est **PROPRE** que sans erreur critique **et**
  avec au moins une offre rapprochée dont le coût rendu a été calculé ; un cycle **VIDE** (rien évalué)
  ne compte pas et n'interrompt pas la série ; un cycle **ANOMALIES** sur des données réelles la remet à zéro.

Critère de recette (revue E2E-07, 2ᵉ passe) : seuls les cycles **réels** comptent — données non FICTIVES
(fournisseur et catalogue), catalogue lu dans le registre du moteur (jamais fourni dans le corps), source
fournisseur datée, et **un seul cycle par contenu de source distinct** (même fichier rejoué, même
horodatage de source : compté une fois). Vingt appels identiques ne remplissent donc plus le critère.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from .audit import StateJournal, StateStoreError
from .catalog import SupplierLink
from .errors import PokeshopError
from .models import FrozenModel
from .northstar import is_unresolved_key
from .publish import ENGINE_OWNED_LISTING_FIELDS, HUMAN_VALIDATION_FIELDS, CatalogListing
from .sync import OfferCostInputs, SyncReport, SyncStep

__all__ = [
    "CatalogEntry",
    "SupplierCostEntry",
    "CatalogRegistry",
    "SyncRunSummary",
    "SyncRunLog",
    "SyncRegistryError",
    "SyncRegistryPersistenceError",
    "CycleStatus",
    "cycle_status",
    "CLEAN_RUNS_TARGET",
    "ACCEPTANCE_DEFINITION",
]

CLEAN_RUNS_TARGET = 20
"""Critère de recette BP §13 : 20 cycles réels consécutifs sans erreur critique (gate 3.6)."""

ACCEPTANCE_DEFINITION = (
    "Compte : cycles PROPRES (aucune erreur critique et au moins une offre au coût rendu calculé) sur des "
    "données réelles (ni fournisseur ni catalogue FICTIF), catalogue lu dans le registre du moteur (POST "
    "/catalog/items, jamais le corps), source fournisseur datée ; un seul cycle par contenu de source distinct "
    "(même fichier ou même horodatage rejoué : compté une fois). VIDE et cycles non admissibles : ignorés ; "
    "ANOMALIES sur données réelles : remise à zéro."
)
"""Définition affichée par ``GET /sync/history`` (et lue par la gate 3.6)."""

CycleStatus = Literal["PROPRE", "VIDE", "ANOMALIES"]


class SyncRegistryError(PokeshopError, ValueError):
    """Entrée refusée (contenu incohérent avec le registre)."""


class SyncRegistryPersistenceError(SyncRegistryError, StateStoreError):
    """Journal illisible ou écriture refusée : rien n'est appliqué (fermé par défaut)."""


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} doit porter un fuseau horaire")
    return value


def _load(store: StateJournal, what: str) -> list[dict[str, Any]]:
    try:
        return list(store.load())
    except StateStoreError as exc:
        raise SyncRegistryPersistenceError(f"{what} : {exc}") from exc


def _append(store: StateJournal | None, record: dict[str, Any], what: str) -> None:
    if store is None:
        return
    try:
        store.append(record)
    except StateStoreError as exc:
        raise SyncRegistryPersistenceError(f"{what} non enregistré ({exc})") from exc


# ----------------------------------------------------------------------------- catalogue


def _without_declared(item: Any) -> Any:
    """Enregistrement ancien : retire les champs du moteur et validations humaines déclarés (jamais crus).

    Avant la revue R3, une fiche pouvait porter ``approved``, ``shopify_product_id``, ``current_price_chf``…
    déclarés par l'appelant ; ils ne font plus foi (registres du moteur et de la propriétaire) : ignorés.
    """
    if isinstance(item, dict) and isinstance(item.get("listing"), dict):
        listing = {k: v for k, v in item["listing"].items()
                   if k not in ENGINE_OWNED_LISTING_FIELDS and k not in HUMAN_VALIDATION_FIELDS}  # fmt: skip
        return {**item, "listing": listing}
    return item


class CatalogEntry(FrozenModel):
    """Produit du catalogue validé : identité (fiche), liens fournisseur, fiche publiable.

    Revue R4 (R3-NEW-01) : **clé produit unique** — ``product_id`` = ``listing.product_key`` (quarantaine,
    stop-loss produit, publication, coûts et validations portent sur la même clé). Une entrée ancienne
    incohérente reste lisible (:meth:`canonical`) mais aucune nouvelle ne l'est (:meth:`CatalogRegistry.upsert`).
    """

    product_id: str = Field(min_length=1, max_length=120)
    supplier_links: tuple[SupplierLink, ...] = ()
    listing: CatalogListing
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "recorded_at")

    @property
    def canonical(self) -> bool:
        """Vrai si ``product_id`` = ``listing.product_key`` (clé produit unique)."""
        return self.product_id == self.listing.product_key

    @property
    def keys(self) -> frozenset[str]:
        """Toutes les clés sous lesquelles la référence peut être désignée (``product_id``, ``listing.product_key``)."""
        return frozenset({self.product_id, self.listing.product_key})

    @property
    def handle(self) -> str | None:
        """Handle boutique explicite de la fiche (None : dérivé du titre et du SKU, donc unique avec lui)."""
        return self.listing.handle


class SupplierCostEntry(FrozenModel):
    """Frais connus d'un fournisseur (CHF par unité retail) ; ``None`` = inconnu => fiche en brouillon.

    ``currency`` : devise de facturation du fournisseur ; si elle n'est pas le CHF, le taux est lu au
    cycle dans le registre des taux de la propriétaire (jamais déclaré ici).
    """

    supplier_id: str = Field(min_length=2, max_length=64)
    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    inbound_freight_alloc: Decimal | None = Field(default=None, ge=0)
    customs_and_fees: Decimal | None = Field(default=None, ge=0)
    import_vat: Decimal | None = Field(default=None, ge=0)
    order_qty: int | None = Field(default=None, ge=1)
    source: str = Field(min_length=3, max_length=300)
    """Justificatif des frais (devis transporteur, simulation de dédouanement…)."""
    recorded_by: str = Field(min_length=2)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return _aware(v, "recorded_at")

    def to_offer_inputs(
        self, *, allowed_currencies: tuple[str, ...], fx_rate: Decimal | None, fx_source: str | None, fx_date: date | None
    ) -> OfferCostInputs:
        """Frais pour le moteur de prix ; taux seulement si toutes les devises admises sont CHF ou ``currency``."""
        single = set(allowed_currencies) <= {"CHF", self.currency}
        use_fx = self.currency != "CHF" and single and fx_rate is not None
        return OfferCostInputs(
            inbound_freight_alloc=self.inbound_freight_alloc,
            customs_and_fees=self.customs_and_fees,
            import_vat=self.import_vat,
            fx_rate_to_chf=fx_rate if use_fx else None,
            fx_source=fx_source if use_fx else None,
            fx_date=fx_date if use_fx else None,
            order_qty=self.order_qty,
        )


class CatalogRegistry:
    """Catalogue validé et frais connus, persistés (dernier enregistrement par clé = en vigueur)."""

    CATALOG_STREAM = "sync_catalog"
    COSTS_STREAM = "sync_cost_inputs"

    def __init__(self, *, catalog_store: StateJournal | None = None, costs_store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, CatalogEntry] = {}
        self._costs: dict[str, SupplierCostEntry] = {}
        self._catalog_store = catalog_store
        self._costs_store = costs_store
        self._sku_holders: dict[str, set[str]] = {}
        """Revue R6 (R5-NEW-02) : SKU boutique -> clés qui l'ont **porté** (historique relu du journal ``sync_catalog``,
        ajout seul) ; un SKU corrigé reste rattaché à sa clé pour les commandes payées avant la correction."""

    def _remember(self, entry: CatalogEntry) -> None:
        self._sku_holders.setdefault(entry.listing.public_sku, set()).add(entry.product_id)

    @classmethod
    def restore(cls, catalog_store: StateJournal, costs_store: StateJournal) -> CatalogRegistry:
        """Relit les deux journaux (:class:`SyncRegistryPersistenceError` si l'un est illisible)."""
        registry = cls()
        for n, record in enumerate(_load(catalog_store, "catalogue de synchronisation"), start=1):
            try:
                batch = [CatalogEntry.model_validate(_without_declared(item)) for item in record["entries"]]
            except (KeyError, TypeError, ValidationError) as exc:
                raise SyncRegistryPersistenceError(f"catalogue de synchronisation : enregistrement {n} illisible") from exc
            for entry in batch:
                registry._entries[entry.product_id] = entry
                registry._remember(entry)  # revue R6 (R5-NEW-02) : alias de SKU historiques persistés (journal)
        for n, record in enumerate(_load(costs_store, "frais fournisseurs"), start=1):
            try:
                cost = SupplierCostEntry.model_validate(record["costs"])
            except (KeyError, TypeError, ValidationError) as exc:
                raise SyncRegistryPersistenceError(f"frais fournisseurs : enregistrement {n} illisible") from exc
            registry._costs[cost.supplier_id] = cost
        registry._catalog_store, registry._costs_store = catalog_store, costs_store
        return registry

    def upsert(self, entries: list[CatalogEntry]) -> int:
        """Enregistre un lot (atomique en mémoire : écrit d'abord, appliqué ensuite) ; renvoie les changements.

        Revue R4 (R3-NEW-01) : chaque entrée doit être canonique (``product_id`` = ``listing.product_key``) et,
        après le lot, un SKU boutique ou un handle explicite n'appartient qu'à une seule référence (409 sinon).
        """
        with self._lock:
            ids = [e.product_id for e in entries]
            if len(set(ids)) != len(ids):
                raise SyncRegistryError("product_id en double dans le lot")
            bad = [e.product_id for e in entries if not e.canonical]
            if bad:
                raise SyncRegistryError(
                    f"clé produit incohérente ({', '.join(bad)}) : product_id doit être égal à listing.product_key"
                )
            reserved = [e.product_id for e in entries if is_unresolved_key(e.product_id)]
            if reserved:  # revue R6 (R5-NEW-02) : clé des lignes de commande non rattachées, réservée au moteur
                raise SyncRegistryError(f"clé produit réservée au moteur ({', '.join(reserved)}) : refusée")
            after = {**self._entries, **{e.product_id: e for e in entries}}
            for label, attr in (("SKU boutique", "public_sku"), ("handle", "handle")):
                owners: dict[str, str] = {}
                for pid in sorted(after):
                    value = getattr(after[pid].listing, attr)
                    if value is None:
                        continue
                    if value in owners and owners[value] != pid:
                        raise SyncRegistryError(
                            f"{label} {value} déjà porté par {owners[value]} : une référence = une clé produit "
                            f"(refusé pour {pid})"
                        )
                    owners[value] = pid
            changed = [
                e
                for e in entries
                if e.product_id not in self._entries
                or self._entries[e.product_id].model_dump(exclude={"recorded_by", "recorded_at"})
                != e.model_dump(exclude={"recorded_by", "recorded_at"})
            ]
            if changed:
                # Un lot = un enregistrement : tout ou rien.
                _append(
                    self._catalog_store,
                    {"entries": [e.model_dump(mode="json") for e in changed]},
                    "catalogue de synchronisation",
                )
                for e in changed:
                    self._entries[e.product_id] = e
                    self._remember(e)
            return len(changed)

    def set_costs(self, entry: SupplierCostEntry) -> bool:
        """Enregistre les frais d'un fournisseur ; False si identiques aux frais en vigueur."""
        with self._lock:
            current = self._costs.get(entry.supplier_id)
            same = current is not None and current.model_dump(exclude={"recorded_by", "recorded_at"}) == entry.model_dump(
                exclude={"recorded_by", "recorded_at"}
            )
            if same:
                return False
            _append(self._costs_store, {"costs": entry.model_dump(mode="json")}, "frais fournisseurs")
            self._costs[entry.supplier_id] = entry
            return True

    def entries(self) -> tuple[CatalogEntry, ...]:
        """Produits du catalogue validé, par identifiant."""
        with self._lock:
            return tuple(self._entries[k] for k in sorted(self._entries))

    def costs(self, supplier_id: str) -> SupplierCostEntry | None:
        """Frais en vigueur d'un fournisseur."""
        with self._lock:
            return self._costs.get(supplier_id)

    def all_costs(self) -> tuple[SupplierCostEntry, ...]:
        """Frais en vigueur de tous les fournisseurs."""
        with self._lock:
            return tuple(self._costs[k] for k in sorted(self._costs))

    def entry_for(self, key: str) -> CatalogEntry | None:
        """Fiche désignée par sa clé canonique (``product_id``) ; None si inconnue.

        Une clé qui ne désigne une fiche que par ``listing.product_key`` (entrée ancienne incohérente) n'est
        pas résolue : l'appelant refuse (fermé par défaut, revue R4 R3-NEW-01).
        """
        with self._lock:
            return self._entries.get(key)

    def by_sku(self, public_sku: str) -> CatalogEntry | None:
        """Fiche dont le SKU boutique **actuel** est ``public_sku`` (unique par construction), None sinon."""
        with self._lock:
            return next((e for e in self._entries.values() if e.listing.public_sku == public_sku), None)

    def sku_holders(self, public_sku: str) -> tuple[str, ...]:
        """Clés qui ont porté ``public_sku`` (historique du journal + fiche actuelle), triées."""
        with self._lock:
            holders = set(self._sku_holders.get(public_sku, ()))
            current = self.by_sku(public_sku)
            if current is not None:
                holders.add(current.product_id)
            return tuple(sorted(holders))

    def resolve_sku(self, public_sku: str) -> tuple[CatalogEntry | None, tuple[str, ...]]:
        """Fiche canonique d'un SKU de commande, **historique compris** ; (fiche ou None, clés candidates).

        Revue R6 (R5-NEW-02) : une commande payée avant une correction de SKU porte l'ancien SKU ; il reste rattaché
        à sa clé (alias historique relu du journal). Résolu seulement si **une seule** clé a jamais porté le SKU et
        que sa fiche actuelle est canonique ; sinon (SKU inconnu, ou porté au fil du temps par plusieurs clés :
        ambigu) None — l'appelant enregistre la ligne non rattachée (coût des ventes en attente, incomplet), jamais
        une clé devinée.
        """
        with self._lock:
            holders = self.sku_holders(public_sku)
            if len(holders) == 1:
                entry = self._entries.get(holders[0])
                if entry is not None and entry.canonical:
                    return entry, holders
            return None, holders

    def incoherent(self) -> tuple[str, ...]:
        """Entrées anciennes dont ``product_id`` ≠ ``listing.product_key`` (à ré-enregistrer)."""
        with self._lock:
            return tuple(sorted(pid for pid, e in self._entries.items() if not e.canonical))

    def extension_of(self, key: str) -> str | None:
        """Extension d'un produit, par ``product_id`` ou ``listing.product_key`` (None si inconnu)."""
        with self._lock:
            for entry in self._entries.values():
                if key in (entry.product_id, entry.listing.product_key):
                    ext = entry.listing.identity.extension
                    return str(ext) if ext else None
        return None


# ------------------------------------------------------------------------------ cycles


def cycle_status(report: SyncReport) -> tuple[CycleStatus, int]:
    """(statut, offres au coût rendu calculé) d'un cycle.

    PROPRE : aucune erreur critique et au moins une offre rapprochée au coût rendu complet ;
    VIDE : aucune offre évaluée (catalogue absent, rien rapproché, import refusé) — ne compte pas ;
    ANOMALIES : au moins une erreur critique (``GATES_GO_NO_GO.md`` §1).
    """
    costed = next((s.count for s in report.steps if s.step is SyncStep.COST), 0)
    if report.critical_errors:
        return "ANOMALIES", costed
    return ("PROPRE" if costed > 0 else "VIDE"), costed


class SyncRunSummary(FrozenModel):
    """Résumé persisté d'un cycle (aucun coût ni prix B2B)."""

    run_id: str
    supplier_id: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    status: CycleStatus
    offers_costed: int = Field(ge=0)
    items: int = Field(ge=0)
    critical_errors: tuple[str, ...] = ()
    incident_ids: tuple[str, ...] = ()
    catalog_source: Literal["corps", "registre"]
    recorded_by: str = Field(min_length=2)
    fictif: bool = True
    """Données FICTIVES (fournisseur ou catalogue) ; défaut prudent pour un enregistrement ancien : vrai."""
    source_sha256: str | None = None
    """Empreinte du contenu de la source ; None (ancien enregistrement, source illisible) : jamais compté."""
    source_ts: datetime | None = None
    """Horodatage effectif de la source (fournisseur, ou première capture du contenu)."""
    product_ids: tuple[str, ...] = ()
    """Produits du catalogue rapprochés (cible d'un test de correction d'incident)."""

    @classmethod
    def from_report(
        cls,
        report: SyncReport,
        *,
        catalog_source: Literal["corps", "registre"],
        recorded_by: str,
        fictif: bool | None = None,
    ) -> SyncRunSummary:
        status, costed = cycle_status(report)
        return cls(
            run_id=report.run_id,
            supplier_id=report.supplier_id,
            dry_run=report.dry_run,
            started_at=report.started_at,
            finished_at=report.finished_at,
            status=status,
            offers_costed=costed,
            items=len(report.items),
            critical_errors=report.critical_errors,
            incident_ids=report.incident_ids,
            catalog_source=catalog_source,
            recorded_by=recorded_by,
            fictif=report.fictif if fictif is None else (fictif or report.fictif),
            source_sha256=report.source_sha256,
            source_ts=report.source_ts,
            product_ids=report.product_ids,
        )

    def acceptance_exclusion(self) -> str | None:
        """Motif pour lequel ce cycle ne compte pas pour la recette (None = cycle réel admissible)."""
        if self.fictif:
            return "données FICTIVES"
        if self.catalog_source != "registre":
            return "catalogue fourni dans le corps de la requête (registre du moteur exigé)"
        if self.source_sha256 is None:
            return "contenu de la source inconnu"
        if self.source_ts is None:
            return "source non datée"
        return None


class SyncRunLog:
    """Journal persisté des cycles (``sync_runs``) et compteur de cycles propres consécutifs."""

    STREAM = "sync_runs"

    def __init__(self, *, store: StateJournal | None = None) -> None:
        self._lock = threading.RLock()
        self._runs: list[SyncRunSummary] = []
        self._store = store

    @classmethod
    def restore(cls, store: StateJournal) -> SyncRunLog:
        """Relit le journal (:class:`SyncRegistryPersistenceError` s'il est illisible)."""
        log = cls()
        for n, record in enumerate(_load(store, "cycles de synchronisation"), start=1):
            try:
                log._runs.append(SyncRunSummary.model_validate(record["run"]))
            except (KeyError, TypeError, ValidationError) as exc:
                raise SyncRegistryPersistenceError(f"cycles de synchronisation : enregistrement {n} illisible") from exc
        log._store = store
        return log

    def record(self, summary: SyncRunSummary) -> SyncRunSummary:
        """Ajoute un cycle (écrit d'abord)."""
        with self._lock:
            _append(self._store, {"run": summary.model_dump(mode="json")}, "cycle de synchronisation")
            self._runs.append(summary)
            return summary

    def runs(self, limit: int | None = None) -> tuple[SyncRunSummary, ...]:
        """Cycles du plus ancien au plus récent (les ``limit`` derniers)."""
        with self._lock:
            items = self._runs[-limit:] if limit else self._runs
            return tuple(items)

    def get(self, run_id: str) -> SyncRunSummary | None:
        """Cycle persisté par identifiant (None si inconnu)."""
        with self._lock:
            return next((r for r in reversed(self._runs) if r.run_id == run_id), None)

    def acceptance(self) -> dict[str, str | None]:
        """Pour chaque cycle : None s'il compte pour le critère de recette, sinon le motif (en français).

        Une source n'est « nouvelle » que si son contenu (empreinte) **et** son horodatage n'ont jamais été
        vus dans un cycle antérieur du même fournisseur : un fichier rejoué ou ré-horodaté ne compte jamais.
        En partant du plus récent, une anomalie sur des données réelles arrête la série.
        """
        with self._lock:
            runs = list(self._runs)
        fresh: dict[str, bool] = {}
        contents: set[tuple[str, str]] = set()
        stamps: set[tuple[str, datetime]] = set()
        for run in runs:  # du plus ancien au plus récent
            content = (run.supplier_id, run.source_sha256) if run.source_sha256 else None
            stamp = (run.supplier_id, run.source_ts) if run.source_ts else None
            fresh[run.run_id] = content is not None and stamp is not None and content not in contents and stamp not in stamps
            if content is not None:
                contents.add(content)
            if stamp is not None:
                stamps.add(stamp)
        out: dict[str, str | None] = {}
        broken = False
        for run in reversed(runs):
            if broken:
                out[run.run_id] = "antérieur à la dernière anomalie sur données réelles"
            elif run.status == "ANOMALIES":
                out[run.run_id] = "anomalies (erreur critique)"
                broken = not run.fictif
            elif run.status != "PROPRE":
                out[run.run_id] = "cycle VIDE (aucune offre au coût rendu calculé)"
            else:
                reason = run.acceptance_exclusion()
                if reason is None and not fresh[run.run_id]:
                    reason = "source déjà vue (même contenu ou même horodatage) : un seul cycle par livraison"
                out[run.run_id] = reason
        return out

    def counted_runs(self) -> tuple[SyncRunSummary, ...]:
        """Cycles retenus pour le critère de recette, du plus récent au plus ancien (voir :meth:`acceptance`)."""
        verdict = self.acceptance()
        with self._lock:
            return tuple(r for r in reversed(self._runs) if verdict.get(r.run_id, "?") is None)

    def consecutive_clean_runs(self) -> int:
        """Cycles PROPRES **réels et distincts** consécutifs depuis la dernière anomalie (critère de recette)."""
        return len(self.counted_runs())
