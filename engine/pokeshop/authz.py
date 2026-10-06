"""Matrice d'autorisations de l'API du moteur : **refus par défaut**, versionnée, lisible (revue R3).

Pourquoi : jusqu'à la revue de 3ᵉ passe, la plupart des routes d'écriture n'appelaient que
``require_api`` ; le **jeton commun** (non attribuable) et n'importe quel jeton nommé pouvaient donc
poster des coûts, une activité publicitaire, des ventes, des fiches « approuvées » ou des réceptions de
stock, c'est-à-dire des **valeurs décisives** (gel du stop-loss, prix publié, étoile polaire).

Principes (``docs/08-agents/MATRICE_API.md`` est généré depuis ce module) :

* **Refus par défaut** : chaque route de l'application FastAPI a une entrée ici ; une route absente
  de la matrice est refusée (403) avant d'atteindre son code. Un test parcourt toutes les routes.
* **Jeton commun = lecture et aperçus en simulation seulement** (``READ``, ``PREVIEW``) ; toute route
  d'écriture (``WRITE``) le refuse (403, journalisé).
* **Jetons nommés par rôle** : le nom du jeton (``POKESHOP_AGENT_TOKENS_SHA256`` = ``rôle:empreinte``)
  est son **rôle** — un des 12 agents de ``.claude/agents/`` ou un connecteur/workflow n8n — et devient
  l'acteur journalisé. Un nom inconnu de cette matrice est refusé au démarrage.
* **Propriétaire** : en-tête ``X-Pokeshop-Owner-Token`` valide (distinct du jeton d'API) ; seule voie
  des actes ``OWNER`` (approbations, capital, taux, réarmement, point zéro, photo déposée…). Revue R4
  (R3-DOC-01) : le jeton propriétaire **seul** suffit sur toute route qui l'admet (aucun jeton d'API requis).
* **Séparation des rôles** : l'agent qui bénéficie d'une valeur ne la déclare pas. Exemples :
  ``acquisition`` (qui dépense en publicité) ne déclare pas l'activité publicitaire (connecteur
  ``connecteur-publicite`` ; et le moteur retient le MAX entre la déclaration et les paiements pub
  **engagés** — approuvés ou exécutés — du registre du mandat) ; ``catalogue`` dépose les fiches mais ne
  les approuve pas (propriétaire, ``POST /catalog/approvals``) ; les relevés de cash viennent du
  ``connecteur-tresorerie``, la photo du stop-loss est **construite par le moteur** (``n8n-07-stoploss``
  ne fait que la demander ; une photo déposée : propriétaire seule) ; les coûts historiques de
  ``finance-pricing`` adossés à une réception physique déclarée par ``operations-sav`` et bornés par une
  référence du moteur (facture enregistrée par ``n8n-03-factures`` ou coût rendu de l'offre) ; les créances
  de la photo : propriétaire seule ; les dettes : plancher des factures enregistrées non payées.

Pré-drop (6.10.2026) : l'allocation ferme vient de la propriétaire ou de ``n8n-03-factures`` (confirmation fournisseur
validée par elle), jamais d'un agent qui bénéficie du pré-drop ; la demande est un compte agrégé (``n8n-06-marketing``) ;
la référence marché et la validation d'un pré-drop en attente ou d'un remboursement préparé : propriétaire ; les
réservations payées et les remboursements exécutés : ``n8n-02-commandes`` ; la fiche « Réservation garantie »
(construite par le moteur) : ``n8n-01-sync`` ou ``site-integrations`` ; la fermeture protectrice dès l'annonce d'une
réduction d'allocation : aussi ``n8n-03-factures``.

Les contrôles fins restent dans les routes (ex. test d'incident réussi : ``qa-conformite`` ou
propriétaire ; hausse d'autonomie : propriétaire) : la matrice dit **qui peut appeler** la route.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "AUTHZ_VERSION",
    "OWNER",
    "COMMON",
    "AGENT_ROLES",
    "CONNECTOR_ROLES",
    "KNOWN_ROLES",
    "INCIDENT_TEST_ATTESTERS",
    "RELAY_ROLES",
    "RELAYED_SPENDERS",
    "SPENDING_ROLES",
    "Kind",
    "RouteRule",
    "ROUTE_MATRIX",
    "rule_for",
    "allowed",
    "matrix_markdown",
]

AUTHZ_VERSION = "2026-10-06.predrop-boutique"
"""Version de la matrice (à changer à chaque modification ; citée par ``/health`` et la doc générée)."""

OWNER = "propriétaire"
"""Acteur journalisé d'un acte authentifié par le jeton de la propriétaire."""
COMMON = "api"
"""Acteur du jeton commun (non attribuable) : lecture et aperçus seulement."""

AGENT_ROLES: dict[str, str] = {
    "chef-de-projet": "Agent 01 — chef de projet (dispatch, revue des exceptions)",
    "sourcing": "Agent 02 — sourcing (fournisseurs, devis)",
    "donnees-fournisseurs": "Agent 03 — données fournisseurs (imports en simulation)",
    "catalogue": "Agent 04 — catalogue (fiches en brouillon, jamais approuvées par lui)",
    "finance-pricing": "Agent 05 — finance et pricing (coûts bornés par une référence du moteur, frais, dettes)",
    "direction-artistique": "Agent 06 — direction artistique",
    "site-integrations": "Agent 07 — site et intégrations (cycles de synchronisation)",
    "seo-redaction": "Agent 08 — SEO et rédaction",
    "communication": "Agent 09 — communication",
    "acquisition": "Agent 10 — acquisition (dépense pub : ne déclare jamais l'activité pub)",
    "operations-sav": "Agent 11 — opérations et SAV (réceptions physiques de stock)",
    "qa-conformite": "Agent 12 — QA et conformité (atteste les tests d'incident, peut geler)",
}
"""Les 12 agents de ``.claude/agents/`` (même nom que le fichier) : nom du jeton = rôle."""

CONNECTOR_ROLES: dict[str, str] = {
    "n8n-01-sync": "Workflow n8n 01 — fournisseur vers site (imports, cycles en simulation)",
    "n8n-02-commandes": "Workflow n8n 02 — commandes (frais PSP réels, commandes expédiées)",
    "n8n-03-factures": "Workflow n8n 03 — factures fournisseur validées par la propriétaire (registre, écarts)",
    "n8n-04-incidents": "Workflow n8n 04 — incidents (ouverture, reprise après test attesté)",
    "n8n-05-digest": "Workflow n8n 05 — digest quotidien (lecture)",
    "n8n-06-marketing": "Workflow n8n 06 — automatisations marketing (incidents)",
    "n8n-07-stoploss": "Workflow n8n 07 — demande la photo du stop-loss construite par le moteur, gel",
    "n8n-08-mandat": "Workflow n8n 08 — passerelle du mandat (relais d'un rôle qui dépense : jamais vérifiable)",
    "connecteur-tresorerie": "Connecteur banque et PayPal en lecture seule (soldes, paiements de factures)",
    "connecteur-publicite": "Connecteur de la plateforme publicitaire (dépenses, commandes attribuées)",
}
"""Connecteurs et workflows : jamais un agent qui bénéficie de la valeur qu'il dépose."""

KNOWN_ROLES: frozenset[str] = frozenset(AGENT_ROLES) | frozenset(CONNECTOR_ROLES)
"""Seuls noms admis pour un jeton nommé (refus au démarrage sinon)."""

ALL_NAMED: frozenset[str] = KNOWN_ROLES

INCIDENT_TEST_ATTESTERS: frozenset[str] = frozenset({"qa-conformite"})
"""Liste fermée des rôles qui attestent un test de correction d'incident **réussi** (sinon propriétaire)."""

RELAY_ROLES: frozenset[str] = frozenset({"n8n-08-mandat"})
"""Relais d'une demande d'agent : le demandeur déclaré n'est pas authentifié, trésorerie jamais vérifiable."""

SPENDING_ROLES: frozenset[str] = frozenset(
    {"chef-de-projet", "sourcing", "direction-artistique", "site-integrations", "communication",
     "acquisition", "operations-sav", "n8n-08-mandat"}
)  # fmt: skip
"""Rôles qui peuvent soumettre une demande de dépense au mandat (jamais ``qa-conformite`` ni ``catalogue``).

Revue R5 (R4-DOC-11) : ni ``finance-pricing`` — l'agent 05 contrôle et **paie** les dépenses de la flotte et dépose
les coûts et les dettes de la photo ; il ne demande jamais une dépense à son nom (ni en direct, ni par le relais 08).
"""

RELAYED_SPENDERS: frozenset[str] = (SPENDING_ROLES & frozenset(AGENT_ROLES)) - RELAY_ROLES
"""Demandeurs qu'un relais (``n8n-08-mandat``) peut porter : agents qui dépensent (revue R4, R3-NEW-06)."""


class Kind(str, Enum):
    """Nature d'une route."""

    PUBLIC = "PUBLIC"
    """Sans jeton (``/health`` : aucune donnée interne)."""
    READ = "READ"
    """Lecture : tout jeton valide, jeton commun compris."""
    PREVIEW = "PREVIEW"
    """Calcul ou aperçu en simulation, sans écriture d'état : tout jeton valide, jeton commun compris."""
    WRITE = "WRITE"
    """Écriture d'un registre ou acte : rôles listés et/ou propriétaire ; **jamais** le jeton commun."""


@dataclass(frozen=True)
class RouteRule:
    """Qui peut appeler une route."""

    kind: Kind
    audit: str
    """Préfixe des événements d'audit (refus : ``<audit>.common_token_refused`` …)."""
    roles: frozenset[str] = frozenset()
    """Rôles nommés admis (``WRITE``) ; ignoré pour ``READ``/``PREVIEW`` (tout jeton valide)."""
    owner: bool = False
    """Propriétaire admise (jeton propriétaire vérifié)."""
    note: str = ""

    @property
    def common(self) -> bool:
        """Vrai si le jeton commun est admis (lecture et aperçus seulement)."""
        return self.kind in (Kind.READ, Kind.PREVIEW)

    @property
    def owner_only(self) -> bool:
        """Vrai si seule la propriétaire peut appeler la route."""
        return self.kind is Kind.WRITE and self.owner and not self.roles


def _read(audit: str, note: str = "") -> RouteRule:
    return RouteRule(Kind.READ, audit, owner=True, note=note)


def _preview(audit: str, note: str = "") -> RouteRule:
    return RouteRule(Kind.PREVIEW, audit, owner=True, note=note)


def _write(audit: str, roles: Iterable[str] = (), *, owner: bool = True, note: str = "") -> RouteRule:
    roles = frozenset(roles)
    unknown = roles - KNOWN_ROLES
    if unknown:
        raise ValueError(f"rôles inconnus dans la matrice : {sorted(unknown)}")
    return RouteRule(Kind.WRITE, audit, roles=roles, owner=owner, note=note)


def _owner(audit: str, note: str = "") -> RouteRule:
    return RouteRule(Kind.WRITE, audit, owner=True, note=note)


ROUTE_MATRIX: dict[tuple[str, str], RouteRule] = {
    ("GET", "/health"): RouteRule(Kind.PUBLIC, "health", note="état sans secret"),
    # -- prix
    ("POST", "/pricing/quote"): _preview("pricing.quote", "calcul, aucun état"),
    ("POST", "/pricing/basket"): _preview("pricing.basket", "calcul, aucun état"),
    ("POST", "/pricing/approvals"): _owner("pricing.approval", "approbation d'un prix public"),
    ("GET", "/pricing/approvals"): _read("pricing.approvals"),
    ("POST", "/pricing/approvals/{approval_id}/revoke"): _write(
        "pricing.approval.revoke", {"finance-pricing", "qa-conformite", "chef-de-projet"},
        note="acte protecteur (retour au prix du moteur)"),
    # -- stock
    ("POST", "/stock/sellable"): _preview("stock.sellable", "lecture du registre ou calcul"),
    ("POST", "/stock/receive"): _write(
        "stock.receive", {"operations-sav"}, note="réception physique contrôlée (passerelle 06 : jeton operations-sav)"),
    ("POST", "/stock/reorder-proposal"): _write(
        "reorder", {"finance-pricing", "operations-sav"}, note="cap_exceptions : propriétaire"),
    # -- imports et publication
    ("POST", "/imports/{supplier}/run"): _write(
        "import.run", {"donnees-fournisseurs", "n8n-01-sync"}, note="simulation ; met à jour la référence « dernier import »"),
    ("POST", "/publish/preview"): _preview("publish.preview", "aperçu : fiche, registres d'approbation et de publication"),
    # -- catalogue
    ("POST", "/catalog/items"): _write(
        "catalog.items", {"catalogue"}, note="fiches sans champ moteur ni validation humaine (422)"),
    ("POST", "/catalog/cost-inputs"): _write("catalog.cost_inputs", {"finance-pricing"}, note="fret, douane, TVA import"),
    ("GET", "/catalog"): _read("catalog"),
    ("POST", "/catalog/approvals"): _owner(
        "catalog.approval", "fiche approuvée, contenu validé, règle de catégorie : propriétaire seule"),
    ("GET", "/catalog/approvals"): _read("catalog.approvals"),
    # -- synchronisation
    ("POST", "/sync/run"): _write(
        "sync.run", {"n8n-01-sync", "site-integrations"}, note="simulation par défaut ; écriture réelle : porte de gouvernance"),
    ("GET", "/sync/history"): _read("sync.history"),
    # -- incidents
    ("GET", "/incidents"): _read("incidents"),
    ("POST", "/incidents"): _write("incidents.open", ALL_NAMED, note="signalement protecteur, tout rôle nommé"),
    ("POST", "/incidents/{incident_id}/test"): _write(
        "incidents.test", ALL_NAMED,
        note="passed:true : qa-conformite (≠ ouvreur, cycle réel lancé par un autre principal) ou propriétaire"),
    ("POST", "/incidents/{incident_id}/resume"): _write(
        "incidents.resume", {"qa-conformite", "chef-de-projet", "n8n-04-incidents"},
        note="après test réussi attesté ; incident critique : propriétaire"),
    ("POST", "/incidents/{incident_id}/close"): _write(
        "incidents.close", {"qa-conformite", "chef-de-projet", "n8n-04-incidents"}),
    # -- autonomie
    ("GET", "/autonomy"): _read("autonomy"),
    ("POST", "/autonomy"): _write("autonomy", ALL_NAMED, note="baisser : tout rôle ; relever : propriétaire"),
    # -- stop-loss
    ("POST", "/stoploss/state"): _owner(
        "stoploss.state", "photo déposée (relevé propriétaire) : cash recoupé avec les relevés du connecteur, écart => 409"),
    ("POST", "/stoploss/state/refresh"): _write(
        "stoploss.refresh", {"n8n-07-stoploss"}, note="photo construite par le moteur depuis ses registres"),
    ("GET", "/stoploss/status"): _read("stoploss.status", "évalue le stop-loss (verrouillage protecteur possible)"),
    ("POST", "/stoploss/freeze"): _write("stoploss.freeze", ALL_NAMED, note="gel manuel protecteur"),
    ("POST", "/stoploss/rearm"): _owner("stoploss.rearm"),
    ("POST", "/stoploss/baseline"): _owner("stoploss.baseline", "point zéro, avec la première photo de façon atomique"),
    ("POST", "/stoploss/capital-memory/reset"): _owner("stoploss.capital_reset"),
    # -- mandat et trésorerie
    ("POST", "/mandate/check"): _write(
        "mandate.check", SPENDING_ROLES, owner=False,
        note="requested_by = rôle du jeton ; relais n8n-08-mandat : requested_by parmi les agents qui dépensent, "
        "trésorerie non vérifiable (validation humaine)"),
    ("POST", "/mandate/human-decision"): _owner(
        "mandate.human_decision",
        "validation ou refus d'une dépense en attente (24 h) : seule voie de HUMAN_APPROVED, comptée au stop-loss pub"),
    ("POST", "/mandate/revoke"): _write("mandate.revoke", ALL_NAMED, note="acte protecteur"),
    ("POST", "/treasury/paypal-balance"): _write("treasury.paypal_balance", {"connecteur-tresorerie"}),
    ("POST", "/treasury/bank-balance"): _write("treasury.bank_balance", {"connecteur-tresorerie"}),
    ("POST", "/treasury/balance-items"): _write(
        "treasury.balance_items", {"finance-pricing", "connecteur-tresorerie"},
        note="dettes à date (finance-pricing : hausse seulement) ; créances : propriétaire seule ; "
        "plancher : factures enregistrées non payées"),
    ("POST", "/capital/movements"): _owner("capital.movement"),
    ("GET", "/capital/movements"): _read("capital.movements"),
    ("POST", "/ads/activity"): _write(
        "ads.activity", {"connecteur-publicite"},
        note="ajout seul par (campagne, jour) ; commandes attribuées = commandes connues du moteur (inconnue ou en "
        "conflit : écartée seule, les dépenses du lot sont enregistrées)"),
    ("POST", "/fx/rates"): _owner("fx.rates"),
    # -- étoile polaire, commandes, coûts
    ("GET", "/northstar"): _read("northstar"),
    ("POST", "/northstar/entries"): _write(
        "northstar.entries", {"n8n-02-commandes", "finance-pricing"},
        note="rôles : coûts positifs (PAYMENT, SAV, acquisition, charges fixes) ; propriétaire : écriture manuelle ; "
        "identifiants order:/refund:/cost: réservés au moteur ; frais d'une commande enregistrée : jamais deux fois"),
    ("POST", "/orders/shipped"): _write(
        "orders.shipped", {"n8n-02-commandes"},
        note="vente dérivée d'une commande (lignes SKU × quantité), coût transporteur réel ; sortie de stock et coût "
        "des ventes dérivés au CMP ; enregistrement atomique ; jamais refusée faute de stock valorisé (coût des ventes "
        "en attente, étoile polaire incomplète) ni pour un SKU (ancien SKU d'une clé : rattaché ; inconnu ou ambigu : "
        "ligne non rattachée, incomplète)"),
    ("POST", "/orders/{order_id}/refunds"): _write(
        "orders.refund", {"n8n-02-commandes", "operations-sav"},
        note="avoir sur une commande enregistrée ; lignes = unités retournées (≤ vendues − déjà retournées)"),
    ("POST", "/orders/{order_id}/lines/resolve"): _owner(
        "orders.line_resolve",
        note="rattache une ligne non rattachée (SKU inconnu ou porté par plusieurs clés) à une fiche canonique ; sortie "
        "au CMP dérivée ensuite"),
    ("POST", "/costs/movements"): _write(
        "costs.movement", {"finance-pricing"},
        note="réception adossée à /stock/receive (autre jeton), coût ≤ 2 % d'une référence du moteur (facture "
        "enregistrée ou offre) sinon propriétaire ; sortie de vente (ISSUE) : dérivée des commandes ; retour : avoir à "
        "lignes ≥ coût des unités retournées et retour physique d'un autre jeton (return:<avoir>)"),
    ("POST", "/costs/invoices"): _write(
        "costs.invoice", {"n8n-03-factures"},
        note="facture fournisseur validée par la propriétaire (workflow 03) : lignes au coût rendu, dette jusqu'au paiement"),
    ("POST", "/costs/invoices/{invoice_ref}/payments"): _write(
        "costs.invoice_payment", {"connecteur-tresorerie"},
        note="paiement relevé sur le compte (cumul ≤ montant de la facture) : seule baisse de la dette d'une facture"),
    # -- pré-drop (décision de la propriétaire du 6.10.2026) : réservation garantie avant réception
    ("POST", "/predrop/allocations"): _write(
        "predrop.allocation", {"n8n-03-factures"},
        note="allocation ferme (confirmation fournisseur validée par la propriétaire, workflow 03 ; fournisseur connu "
        "du moteur) : jamais déclarée par l'agent qui bénéficie du pré-drop ; une baisse passe par la réduction"),
    ("POST", "/predrop/allocations/{product_key}/reduce"): _write(
        "predrop.allocation_reduce", {"n8n-03-factures", "operations-sav"},
        note="réduction annoncée par le fournisseur ou constatée à la réception (acte protecteur, baisse seulement) : "
        "pré-drop servi en premier (ordre de paiement), quota drop réduit d'abord, remboursements intégraux préparés"),
    ("POST", "/predrop/demand"): _write(
        "predrop.demand", {"n8n-06-marketing"},
        note="compte agrégé d'inscrits consentants intéressés (aucune donnée personnelle : tout autre champ, 422)"),
    ("GET", "/predrop/eligibility/{product_key}"): _read(
        "predrop.eligibility", "conditions évaluées sur les registres du moteur ; deux prix, sans coût ni marge"),
    ("POST", "/predrop/open"): _write(
        "predrop.open", {"chef-de-projet", "finance-pricing"},
        note="toutes les conditions requises (sinon 409) ; référence marché : propriétaire seule (rôle : 403) ; "
        "référence inconnue ou prix drop REVIEW : en attente de la propriétaire"),
    ("POST", "/predrop/{predrop_id}/approve"): _owner(
        "predrop.approve", "validation d'un pré-drop en attente (référence marché attestée ou inconnue assumée)"),
    ("POST", "/predrop/{predrop_id}/close"): _write(
        "predrop.close", {"chef-de-projet", "finance-pricing", "qa-conformite", "n8n-03-factures"},
        note="acte protecteur (n8n-03-factures : dès qu'une réduction d'allocation est annoncée, avant sa validation)"),
    ("POST", "/predrop/{predrop_id}/publish"): _write(
        "predrop.publish", {"n8n-01-sync", "site-integrations"},
        note="fiche « Réservation garantie » construite par le moteur (registres, prix figé, planchers revérifiés), "
        "retirée au drop ou sur blocage ; simulation par défaut ; inventaire = réservations ouvertes"),
    ("GET", "/predrop/offers"): _read(
        "predrop.offers", "offres publiques (statut ouvert/fermé, date du drop, deux prix, garantie) ; quotas internes"),
    ("POST", "/predrop/reservations"): _write(
        "predrop.reservation", {"n8n-02-commandes"},
        note="réservation payée (commande Shopify, identifiant client haché) : jamais refusée pour un motif métier — "
        "hors quota, limite, fenêtre ou prix : non servie et remboursement intégral préparé ; dette jusqu'à expédition"),
    ("GET", "/predrop/reservations"): _read("predrop.reservations", "sans identifiant client"),
    ("GET", "/predrop/refunds"): _read("predrop.refunds", "remboursements préparés et brouillons d'email"),
    ("POST", "/predrop/refunds/{refund_id}/approve"): _owner(
        "predrop.refund_approve", "validation en un clic d'un remboursement préparé (niveaux d'autonomie 1 et 2)"),
    ("POST", "/predrop/refunds/{refund_id}/executed"): _write(
        "predrop.refund_executed", {"n8n-02-commandes"},
        note="remboursement PSP relevé (approuvé seulement) : seule sortie de la dette d'une réservation remboursée"),
    # -- tableau de bord (lecture)
    ("GET", "/dashboard/daily"): _read("dashboard.daily"),
    ("GET", "/dashboard/weekly"): _read("dashboard.weekly"),
    ("GET", "/dashboard/monthly"): _read("dashboard.monthly"),
}  # fmt: skip
"""(méthode, gabarit de chemin FastAPI) -> règle. Toute route absente est refusée."""


def rule_for(method: str, path: str) -> RouteRule | None:
    """Règle d'une route (gabarit FastAPI, ex. ``/incidents/{incident_id}/test``) ; None = refus."""
    return ROUTE_MATRIX.get((method.upper(), path))


def allowed(rule: RouteRule, *, role: str | None, owner: bool) -> bool:
    """Vrai si l'appelant passe la matrice.

    ``role`` : nom du jeton nommé (None = jeton commun) ; ``owner`` : jeton propriétaire vérifié.
    """
    if rule.kind is Kind.PUBLIC:
        return True
    if owner and rule.owner:
        return True
    if rule.kind in (Kind.READ, Kind.PREVIEW):
        return True
    return role is not None and role in rule.roles


def matrix_markdown(matrix: Mapping[tuple[str, str], RouteRule] | None = None) -> str:
    """Table lisible de la matrice (``docs/08-agents/MATRICE_API.md``, régénérée et vérifiée par les tests)."""
    matrix = ROUTE_MATRIX if matrix is None else matrix
    lines = [
        "# Matrice d'autorisations de l'API du moteur",
        "",
        f"> Générée depuis `engine/pokeshop/authz.py` (version `{AUTHZ_VERSION}`) — ne pas modifier à la main :",
        "> `python -m pokeshop.authz > docs/08-agents/MATRICE_API.md`. Refus par défaut : une route absente",
        "> de la matrice est refusée (403). Le **jeton commun** n'a que la lecture et les aperçus en simulation.",
        "> Nom d'un jeton nommé = rôle ; son empreinte sha256 va dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (une variable",
        "> par rôle, ex. `POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS`) ou dans la liste `POKESHOP_AGENT_TOKENS_SHA256=rôle:empreinte,…` ;",
        "> propriétaire = en-tête `X-Pokeshop-Owner-Token` valide, distinct du jeton d'API, **suffisant seul** sur toute",
        "> route qui admet la propriétaire (aucun jeton d'API requis : revue R4, R3-DOC-01).",
        "",
        "| Méthode | Route | Nature | Jeton commun | Rôles nommés admis | Propriétaire | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for (method, path), rule in sorted(matrix.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if rule.kind is Kind.PUBLIC:
            roles, common, owner = "sans jeton", "—", "—"
        elif rule.kind in (Kind.READ, Kind.PREVIEW):
            roles, common, owner = "tous", "oui", "oui"
        else:
            roles = "tous les rôles nommés" if rule.roles == ALL_NAMED else (", ".join(sorted(rule.roles)) or "aucun")
            common, owner = "**non**", ("oui" if rule.owner else "non")
        lines.append(f"| {method} | `{path}` | {rule.kind.value} | {common} | {roles} | {owner} | {rule.note} |")
    lines += ["", "## Rôles", "", "| Rôle (nom du jeton) | Description |", "|---|---|"]
    for name, text in [*AGENT_ROLES.items(), *CONNECTOR_ROLES.items()]:
        lines.append(f"| `{name}` | {text} |")
    protective = sorted(
        f"{m} `{p}`" for (m, p), r in matrix.items() if r.kind is Kind.WRITE and r.roles == ALL_NAMED
    )
    owner_only = sorted(f"{m} `{p}`" for (m, p), r in matrix.items() if r.owner_only)
    lines += [
        "",
        "## Écritures par rôle",
        "",
        "Écritures **propres** à chaque rôle (hors actes ouverts à tout rôle nommé). Tout rôle nommé peut en plus :",
        f"{', '.join(protective)} (signalement, gel, baisse de niveau, révocation ; test réussi : voir la note).",
        f"Propriétaire seule : {', '.join(owner_only)}.",
        "",
        "| Rôle (nom du jeton) | Écritures propres |",
        "|---|---|",
    ]
    for name in [*AGENT_ROLES, *CONNECTOR_ROLES]:
        own = sorted(
            f"{m} `{p}`"
            for (m, p), r in matrix.items()
            if r.kind is Kind.WRITE and name in r.roles and r.roles != ALL_NAMED
        )
        lines.append(f"| `{name}` | {', '.join(own) or 'aucune (lecture, aperçus et actes protecteurs seulement)'} |")
    lines += [
        "",
        "## Séparation des rôles (aucune valeur décisive déclarée par son bénéficiaire)",
        "",
        "- Activité publicitaire : `connecteur-publicite`, jamais `acquisition` ; dépense retenue par (campagne, jour) =",
        "  MAX(déclaration, paiements pub **engagés** du registre du mandat : approuvés à leur date de décision, exécutés à",
        "  leur date d'exécution) ; registre en ajout seul (baisse refusée) ; demande de dépense pub sans relevé du",
        "  connecteur de moins de 24 h : non vérifiable (validation humaine). Sans connecteur, une pub payée hors du mandat",
        "  (moyen de paiement du compte publicitaire) reste invisible : aucune campagne sans connecteur.",
        "- Fiches : `catalogue` les dépose ; `approved`, `content_validated`, `category_rule_validated` : propriétaire",
        "  (`POST /catalog/approvals`, liée au contenu de la fiche).",
        "- Coûts historiques : `finance-pricing`, réception adossée à `POST /stock/receive` (`operations-sav`, autre jeton),",
        "  coût unitaire à ± 2 % d'une référence du moteur : ligne de la facture enregistrée par `n8n-03-factures` (quantités",
        "  reçues au coût ≤ quantité facturée, lignes ≤ montant dû, fournisseur connu du moteur pour la référence — lien du",
        "  catalogue ou offre rapprochée sur le catalogue du registre ; inconnu : 409), sinon coût rendu de la",
        "  dernière offre évaluée avec des frais posés par la propriétaire (jamais des frais posés par `finance-pricing`,",
        "  jamais un cycle avec catalogue ou frais du corps) ; sans référence ou au-delà : propriétaire ; une réception",
        "  (SKU **à la réception**, bon) n'est valorisée qu'une fois ; écart de facture > 2 % : propriétaire ; retour en stock",
        "  au coût : lignes de l'avoir (unités retournées), avoir ≥ coût des unités retournées et retour physique déclaré par",
        "  `operations-sav` (`return:<avoir>`, jamais cité par une réception au coût).",
        "- Clé produit unique : `product_id` = `listing.product_key` (422 sinon) ; SKU ou handle en double : 409 ; un nouvel",
        "  identifiant ne reprend jamais le SKU ou le handle d'une fiche existante, ni l'identité produit (GTIN, langue, scellé,",
        "  extension, format, contenu) d'une référence en quarantaine, bloquée ou d'état stop-loss inconnu (409, sauf propriétaire).",
        "- Photo du stop-loss : construite par le moteur (`POST /stoploss/state/refresh`) ; photo déposée : propriétaire",
        "  seule, cash recoupé avec les relevés du connecteur ; créances : registre distinct de la propriétaire, jamais effacé",
        "  par une déclaration de dettes ; dettes : registre persisté (plancher valable après un redémarrage) + factures",
        "  enregistrées non payées (paiement relevé par `connecteur-tresorerie`).",
        "- Étoile polaire : ventes, avoirs, coût des ventes et sortie de stock dérivés de commandes enregistrées",
        "  (`POST /orders/shipped` avec lignes, coût transporteur réel ; jamais refusée faute de coût : coût des ventes en",
        "  attente, étoile et photo incomplètes, dépenses en validation humaine ; jamais refusée pour un SKU : ancien SKU",
        "  d'une clé rattaché par l'historique du catalogue, SKU inconnu ou ambigu en ligne non rattachée, rattachée par la",
        "  propriétaire) ; contribution d'une commande attribuée dérivée avec le coût des ventes ; identifiants `order:`/`refund:`/`cost:`/",
        "  `expense:`/`fixed:` réservés au moteur ; frais PSP d'une commande comptés une fois ; écritures manuelles et",
        "  montants négatifs (référencés) : propriétaire.",
        "- Test d'incident réussi : `qa-conformite` (≠ ouvreur, cycle réel lancé par un autre principal ; cycle FICTIF admis",
        "  seulement pour un incident sur données FICTIVES, ou déclaré `simulation: true` alors que le moteur est en",
        "  simulation) ou propriétaire.",
        "- Relais `n8n-08-mandat` : `requested_by` parmi les agents qui dépensent (jamais `qa-conformite`, `catalogue` ni",
        "  `finance-pricing`, qui paie) ; décision humaine d'une dépense en attente : propriétaire (`POST /mandate/human-decision`).",
        "- Pré-drop : allocation ferme posée par la propriétaire ou `n8n-03-factures` (confirmation fournisseur validée),",
        "  jamais par l'agent qui bénéficie du pré-drop ; compte d'inscrits intéressés agrégé (`n8n-06-marketing`, aucune",
        "  donnée personnelle) ; référence marché et validation d'un pré-drop en attente : propriétaire ; réservations",
        "  payées et remboursements exécutés : `n8n-02-commandes` (montant comparé au prix pré-drop du moteur) ;",
        "  remboursement préparé validé par la propriétaire aux niveaux d'autonomie 1 et 2 ; argent encaissé = dette",
        "  dérivée du registre jusqu'à l'expédition (chiffre d'affaires reconnu à l'expédition, jamais à l'encaissement).",
        "",
        "## Validation humaine requise",
        "",
        "- [ ] Générer un jeton par rôle (`openssl rand -hex 32`, sur l'ordinateur de la propriétaire :",
        "      `docs/00-pilotage/DELEGATION_AUTONOMIE.md` §10 étape 6), en reporter l'empreinte SHA-256 dans",
        "      `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` de `/etc/pokeshop/api.env` (copie `scp`, contrôle, ajout, `shred -u`) et le",
        "      jeton en clair dans l'identifiant n8n du même nom (jamais dans le dépôt) ; le jeton propriétaire reste hors",
        "      de n8n et des agents.",
        "- [ ] Relire cette matrice avant chaque nouvelle route d'écriture : une route absente est refusée.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - génération de la doc
    print(matrix_markdown(), end="")
