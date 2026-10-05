"""Génère les workflows n8n importables ``orchestration/n8n/NN_*.json`` (BP §5, §9, §12).

Pourquoi un générateur : huit workflows partagent les mêmes briques (paramètres, appel du moteur
avec identifiant n8n, garde de suspension, notification désactivée) ; les produire depuis une
seule source garantit des identifiants stables, des connexions valides et les mêmes garde-fous
partout. Les fichiers JSON sont **committés** : n8n les importe tels quels (aucun Python requis
côté n8n). ``tests/test_n8n_workflows.py`` vérifie qu'ils sont à jour.

Règles appliquées à chaque workflow :

* **inactif** à l'import (``active: false``) ; aucun déclencheur ne tourne avant activation ;
* **aucune écriture externe active** : envoi d'email, Slack, Shopify, PayPal, plateforme publicitaire,
  outil d'emailing, flux fournisseur — nœuds **désactivés** (``disabled: true``) jusqu'à la recette ;
* le moteur est appelé **en simulation** (``dry_run: true`` explicite pour ``/sync/run``) ; les
  seules écritures actives sont internes au moteur et protectrices ou journalisées (incident,
  gel, registre du mandat, étoile polaire) ;
* identifiants **par référence** (``credentials: {type: {id, name}}``), jamais de secret dans
  l'export ; l'URL de l'API se règle dans le nœud « Paramètres » (n8n 2.x bloque ``$env`` par défaut) ;
* le workflow d'erreur de tous les workflows est ``04`` (déclencheur « Error Trigger ») ;
* un workflow qui reçoit un **webhook authentifié** (en-tête secret : passerelles des agents, notifications du
  moteur) ne conserve **jamais** une exécution réussie ni une exécution manuelle (revue R6, R5C-DOC-05 : n8n garde
  les en-têtes reçus en clair dans les données d'exécution ; retirer l'en-tête dans un nœud suivant ne suffit pas, la
  sortie du nœud webhook est elle-même conservée). Les exécutions en échec restent conservées pour le diagnostic,
  purgées par n8n après 7 jours (``EXECUTIONS_DATA_MAX_AGE`` du compose).

Usage ::

    python orchestration/build_workflows.py                 # écrit orchestration/n8n/*.json
    python orchestration/build_workflows.py --check         # échoue si un fichier n'est pas à jour
    python orchestration/build_workflows.py --credentials-map ids.json --out /tmp/n8n-import
        # copie prête à importer avec les identifiants de VOS credentials n8n (ids seulement, aucun secret)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "orchestration" / "n8n"
NAMESPACE = uuid.UUID("6f1c1d7e-3c1e-4a8e-9a7b-70c5e0b1f001")
ERROR_WORKFLOW_ID = "pkshp04Incidents"
API_DEFAULT_URL = "http://api:8000"
OWNER_EMAIL_PLACEHOLDER = "REMPLACER-responsable@exemple.invalid"
AGENTS_EMAIL_PLACEHOLDER = "agents@REMPLACER-domaine.invalid"
SHOPIFY_GRAPHQL_PLACEHOLDER = "https://REMPLACER-boutique.myshopify.com/admin/api/2026-10/graphql.json"
LANDING_PLACEHOLDER = "https://REMPLACER-URL-LANDING.exemple.invalid"
SUPPORT_EMAIL_PLACEHOLDER = "REMPLACER-email-support@exemple.invalid"
EMAILING_PLACEHOLDER = "https://REMPLACER-outil-emailing.exemple.invalid/api"

# ------------------------------------------------------------------ noms et clés des workflows

WORKFLOW_NAMES: dict[str, str] = {
    "01": "Pokeshop 01 — Fournisseur vers site (simulation)",
    "02": "Pokeshop 02 — Commande vers livraison",
    "03": "Pokeshop 03 — Facture vers marge réelle",
    "04": "Pokeshop 04 — Incidents et erreurs",
    "05": "Pokeshop 05 — Digest quotidien",
    "06": "Pokeshop 06 — Automatisations marketing",
    "07": "Pokeshop 07 — Surveillance du stop-loss",
    "08": "Pokeshop 08 — Mandat de dépense",
}
"""Nom affiché de chaque workflow (unique)."""

WORKFLOW_IDS: dict[str, str] = {
    "01": "pkshp01FournSite",
    "02": "pkshp02CmdLivrai",
    "03": "pkshp03FactMarge",
    "04": "pkshp04Incidents",
    "05": "pkshp05DigestJou",
    "06": "pkshp06Marketing",
    "07": "pkshp07StopLossW",
    "08": "pkshp08MandatDep",
}

WORKFLOW_KEYS: dict[str, str] = {
    "01": "fournisseur-site",
    "02": "commande-livraison",
    "03": "facture-marge",
    "04": "incident",
    "05": "digest",
    "06": "marketing",
    "07": "stoploss-watch",
    "08": "mandat-depenses",
}
"""Clé CANONIQUE de chaque workflow : nœud « Paramètres », incidents ouverts par n8n (y compris par le
workflow d'erreur 04), suspensions lues par les gardes, et moteur (``pokeshop.api.WORKFLOW_KEYS`` ;
``fournisseur-site`` = ``pokeshop.sync.WORKFLOW_SUPPLIER_TO_SHOP``). Une seule clé par workflow : une
suspension posée par le moteur ou par 04 arrête bien le workflow concerné (revue E2E-10)."""

# --------------------------------------------------------------------- identifiants (références)

CREDENTIALS: dict[str, tuple[str, str, str]] = {
    # clé logique -> (type n8n, id de référence, nom exact à créer dans n8n)
    # Moteur : UN jeton NOMMÉ PAR RÔLE (revue R3, matrice engine/pokeshop/authz.py ; empreinte dans
    # POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>). Le jeton commun (lecture seule) n'est jamais confié à n8n.
    "api_01": ("httpHeaderAuth", "pkshpApiN8n01Syn", "Pokeshop API — jeton nommé n8n-01-sync"),
    "api_02": ("httpHeaderAuth", "pkshpApiN8n02Cmd", "Pokeshop API — jeton nommé n8n-02-commandes"),
    "api_03": ("httpHeaderAuth", "pkshpApiN8n03Fac", "Pokeshop API — jeton nommé n8n-03-factures"),
    "api_04": ("httpHeaderAuth", "pkshpApiN8n04Inc", "Pokeshop API — jeton nommé n8n-04-incidents"),
    "api_05": ("httpHeaderAuth", "pkshpApiN8n05Dig", "Pokeshop API — jeton nommé n8n-05-digest"),
    "api_06": ("httpHeaderAuth", "pkshpApiN8n06Mkt", "Pokeshop API — jeton nommé n8n-06-marketing"),
    # Passerelle 06 « pokeshop-stock-recu » : réception physique déclarée au nom de l'agent 11 (SOP E2), jamais
    # avec le jeton commun (revue SEC-16).
    "api_stock": ("httpHeaderAuth", "pkshpApiOpsSav11", "Pokeshop API — jeton nommé operations-sav"),
    # Photo du stop-loss (refresh, état, gel) : un autre jeton que celui des relevés de cash et des demandes.
    "api_photo": ("httpHeaderAuth", "pkshpApiPhoto007", "Pokeshop API — jeton nommé n8n-07-stoploss"),
    "api_tresorerie": ("httpHeaderAuth", "pkshpApiTresor01", "Pokeshop API — jeton nommé connecteur-tresorerie"),
    "api_08": ("httpHeaderAuth", "pkshpApiN8n08Man", "Pokeshop API — jeton nommé n8n-08-mandat"),
    # Passerelles des agents (revue R4, SEC-16 / R2-NEW-01) : UN SECRET PAR WEBHOOK ET PAR AGENT APPELANT, jamais un
    # secret partagé entre rôles. 03 : agent 05 seul ; 04 (reprise) : agent 12 seul ; 06 (réception) : agent 11 seul ;
    # 08 (dépense) : un webhook et un secret par agent qui dépense (le demandeur est fixé par le webhook, pas le corps).
    "gateway_03": ("httpHeaderAuth", "pkshpGw03Factu05", "Passerelle 03 factures — secret de l'agent 05 (finance-pricing)"),
    "gateway_04": ("httpHeaderAuth", "pkshpGw04Repri12", "Passerelle 04 reprise — secret de l'agent 12 (qa-conformite)"),
    "gateway_06": ("httpHeaderAuth", "pkshpGw06Recep11", "Passerelle 06 réception — secret de l'agent 11 (operations-sav)"),
    **{
        f"gateway_08_{role}": ("httpHeaderAuth", cid, f"Passerelle 08 dépense — secret de l'agent {num} ({role})")
        for role, num, cid in (
            ("chef-de-projet", "01", "pkshpGw08Chef001"),
            ("sourcing", "02", "pkshpGw08Sourc02"),
            ("direction-artistique", "06", "pkshpGw08DirAr06"),
            ("site-integrations", "07", "pkshpGw08SiteI07"),
            ("communication", "09", "pkshpGw08Commu09"),
            ("acquisition", "10", "pkshpGw08Acqui10"),
            ("operations-sav", "11", "pkshpGw08OpSav11"),
        )
    },
    # Revue R6 (R5C-DOC-07) : notifications du moteur vers 04 (webhook « pokeshop-incidents ») authentifiées par un
    # secret DÉDIÉ du moteur (POKESHOP_N8N_WEBHOOK_SECRET, en-tête X-Pokeshop-Notify), distinct de toute passerelle.
    "notify_04": ("httpHeaderAuth", "pkshpNotif04Mote", "Notification moteur → 04 — secret du moteur (POKESHOP_N8N_WEBHOOK_SECRET)"),
    "owner_form": ("httpBasicAuth", "pkshpOwnerForm01", "Formulaires propriétaire — Basic Auth"),
    "smtp": ("smtp", "pkshpSmtpAgents1", "SMTP boîte des agents"),
    "slack": ("slackApi", "pkshpSlackAlert1", "Slack alertes propriétaire"),
    "shopify": ("shopifyAccessTokenApi", "pkshpShopifyAdm1", "Shopify Admin — app personnalisée"),
    "emailing": ("httpHeaderAuth", "pkshpEmailing001", "Outil d'emailing — jeton API"),
    "ads": ("httpHeaderAuth", "pkshpAdsPlatfm01", "Plateforme publicitaire — jeton API"),
    "paypal": ("oAuth2Api", "pkshpPaypalOAuth", "PayPal compte dédié — OAuth2 client credentials"),
    # Revue R5 (R4-DOC-07) : lecture des soldes avec un credential DISTINCT de celui des paiements (application PayPal
    # en lecture seule, scope reporting) — jamais le credential de paiement de 08 sur la lecture de 07.
    "paypal_read": ("oAuth2Api", "pkshpPaypalLect1", "PayPal compte dédié — lecture des soldes (lecture seule)"),
    "supplier": ("httpHeaderAuth", "pkshpSupplier001", "Flux fournisseur — accès autorisé"),
    "bank": ("httpHeaderAuth", "pkshpBanqueSolde", "Banque — relevé de solde (lecture seule)"),
}

GATEWAY_HOLDERS: dict[str, str] = {
    "gateway_03": "finance-pricing",
    "gateway_04": "qa-conformite",
    "gateway_06": "operations-sav",
    **{key: key.removeprefix("gateway_08_") for key in CREDENTIALS if key.startswith("gateway_08_")},
}
"""Credential de passerelle -> SEUL rôle d'agent qui en détient le secret (vérifié par les tests : un secret par webhook)."""

ENGINE_NOTIFY_CREDENTIAL = "notify_04"
"""Credential du webhook des notifications du moteur (04) ; son secret n'est détenu que par le moteur."""

ENGINE_NOTIFY_HEADER = "X-Pokeshop-Notify"
"""Nom d'en-tête du credential :data:`ENGINE_NOTIFY_CREDENTIAL` (= ``pokeshop.incidents.NOTIFY_SECRET_HEADER``)."""

INBOUND_SECRET_HOLDERS: dict[str, str] = {**GATEWAY_HOLDERS, ENGINE_NOTIFY_CREDENTIAL: "moteur"}
"""Tout credential de webhook authentifié -> SEUL détenteur de son secret (agents des passerelles, ou le moteur)."""

SPEND_RELAY_ROLES: tuple[str, ...] = tuple(sorted(GATEWAY_HOLDERS[k] for k in GATEWAY_HOLDERS if k.startswith("gateway_08_")))
"""Agents qui demandent une dépense par la passerelle 08 (un webhook chacun) = agents de ``authz.RELAYED_SPENDERS``."""

CREDENTIAL_ROLES: dict[str, str] = {
    "api_01": "n8n-01-sync",
    "api_02": "n8n-02-commandes",
    "api_03": "n8n-03-factures",
    "api_04": "n8n-04-incidents",
    "api_05": "n8n-05-digest",
    "api_06": "n8n-06-marketing",
    "api_stock": "operations-sav",
    "api_photo": "n8n-07-stoploss",
    "api_tresorerie": "connecteur-tresorerie",
    "api_08": "n8n-08-mandat",
}
"""Credential moteur -> rôle de la matrice d'autorisations (nom du jeton nommé) ; vérifié par les tests."""

WRITE_NODE_TYPES = frozenset(
    {"n8n-nodes-base.emailSend", "n8n-nodes-base.slack", "n8n-nodes-base.payPal", "n8n-nodes-base.shopify"}
)
"""Types de nœuds qui écrivent toujours vers l'extérieur : désactivés à l'import."""


def wf_id_prefix(filename: str) -> str:
    """Préfixe numérique d'un export (``07_stoploss_watch.json`` -> ``07``)."""
    return filename.split("_", 1)[0]


def credential(key: str, mapping: Mapping[str, str] | None = None) -> dict[str, dict[str, str]]:
    """Référence de credential n8n (type -> {id, name}) ; aucun secret."""
    ctype, cid, name = CREDENTIALS[key]
    return {ctype: {"id": (mapping or {}).get(key, cid), "name": name}}


def ref(node: str) -> str:
    """Accès à la sortie d'un nœud nommé dans une expression n8n."""
    if "'" in node:
        raise ValueError(f"nom de nœud référencé avec apostrophe droite : {node!r}")
    return f"$('{node}')"


# ------------------------------------------------------------------------------------ modèle


class Workflow:
    """Workflow n8n en construction (identifiants déterministes)."""

    def __init__(
        self,
        wf_id: str,
        name: str,
        filename: str,
        *,
        error_workflow: bool = True,
        keep_success_data: bool = True,
        credentials_map: Mapping[str, str] | None = None,
        api_cred: str | None = None,
    ) -> None:
        self.api_cred = api_cred or f"api_{wf_id_prefix(filename)}"
        """Credential moteur par défaut du workflow (jeton nommé de son rôle)."""
        if self.api_cred not in CREDENTIAL_ROLES:
            raise ValueError(f"{filename} : credential moteur inconnu {self.api_cred!r}")
        self.wf_id = wf_id
        self.name = name
        self.filename = filename
        self.error_workflow = error_workflow
        self.keep_success_data = keep_success_data
        self.cmap = credentials_map or {}
        self.nodes: list[dict[str, Any]] = []
        self.connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}

    def _uid(self, label: str) -> str:
        return str(uuid.uuid5(NAMESPACE, f"{self.wf_id}:{label}"))

    def add(
        self,
        name: str,
        node_type: str,
        version: float,
        parameters: dict[str, Any],
        position: tuple[float, float],
        *,
        disabled: bool = False,
        credentials: str | None = None,
        notes: str | None = None,
        webhook: bool = False,
        **extra: Any,
    ) -> str:
        """Ajoute un nœud ; ``position`` en cases de grille (colonne, ligne)."""
        if any(n["name"] == name for n in self.nodes):
            raise ValueError(f"{self.filename} : nœud en double {name!r}")
        node: dict[str, Any] = {
            "parameters": parameters,
            "id": self._uid(name),
            "name": name,
            "type": node_type,
            "typeVersion": version,
            "position": [int(position[0] * 280), int(position[1] * 200)],
        }
        if webhook:
            node["webhookId"] = self._uid(f"webhook:{name}")
        if credentials:
            node["credentials"] = credential(credentials, self.cmap)
        if disabled:
            node["disabled"] = True
        if notes:
            node["notes"] = notes
            node["notesInFlow"] = True
        node.update(extra)
        self.nodes.append(node)
        return name

    def link(self, src: str, dst: str, output: int = 0, input_index: int = 0) -> None:
        """Connexion principale ``src[output] -> dst[input]``."""
        outs = self.connections.setdefault(src, {"main": []})["main"]
        while len(outs) <= output:
            outs.append([])
        outs[output].append({"node": dst, "type": "main", "index": input_index})

    def chain(self, *names: str) -> None:
        """Connexions successives (sortie 0)."""
        for a, b in zip(names, names[1:], strict=False):
            self.link(a, b)

    def receives_secret_header(self) -> bool:
        """Vrai si un déclencheur webhook du workflow est authentifié par un en-tête secret."""
        return any(
            n["type"] == "n8n-nodes-base.webhook" and n["parameters"].get("authentication") == "headerAuth"
            for n in self.nodes
        )

    def export(self) -> dict[str, Any]:
        """Format d'export n8n (importable par l'interface ou ``n8n import:workflow``)."""
        # Revue R6 (R5C-DOC-05) : un webhook authentifié => en-tête secret dans la sortie du nœud webhook => aucune
        # exécution réussie ni manuelle conservée (une exécution en attente d'un formulaire l'est jusqu'à sa fin).
        carries_secret = self.receives_secret_header()
        settings: dict[str, Any] = {
            "executionOrder": "v1",
            "timezone": "Europe/Zurich",
            "saveManualExecutions": not carries_secret,
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all" if self.keep_success_data and not carries_secret else "none",
            "saveExecutionProgress": False,
            "callerPolicy": "workflowsFromSameOwner",
        }
        if self.error_workflow:
            settings["errorWorkflow"] = ERROR_WORKFLOW_ID
        return {
            "id": self.wf_id,
            "name": self.name,
            "active": False,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": settings,
            "pinData": {},
            "staticData": None,
            "tags": [],
            "versionId": self._uid("version"),
            "meta": {"templateCredsSetupCompleted": False},
        }


# ------------------------------------------------------------------------------- briques


def _assign(name: str, value: Any, kind: str) -> dict[str, Any]:
    return {"id": str(uuid.uuid5(NAMESPACE, f"assign:{name}:{value}")), "name": name, "value": value, "type": kind}


def set_node(
    wf: Workflow,
    name: str,
    pos: tuple[float, float],
    fields: Sequence[tuple[str, Any, str]],
    *,
    include_other: bool = True,
    notes: str | None = None,
) -> str:
    """Nœud « Edit Fields (Set) » v3.4, affectations manuelles."""
    return wf.add(
        name,
        "n8n-nodes-base.set",
        3.4,
        {
            "assignments": {"assignments": [_assign(n, v, k) for n, v, k in fields]},
            "includeOtherFields": include_other,
            "options": {},
        },
        pos,
        notes=notes,
    )


def params_node(
    wf: Workflow, name: str, pos: tuple[float, float], workflow_key: str, *extra: tuple[str, Any, str]
) -> str:
    """Nœud « Paramètres » : seul endroit à modifier après import (URL de l'API, simulation…)."""
    return set_node(
        wf,
        name,
        pos,
        [
            ("api_base_url", API_DEFAULT_URL, "string"),
            ("simulation", True, "boolean"),
            ("workflow", workflow_key, "string"),
            ("responsable_email", OWNER_EMAIL_PLACEHOLDER, "string"),
            *extra,
        ],
        notes="À régler après import : URL de l'API du moteur (docker compose : http://api:8000). "
        "simulation = true tant que le niveau d'autonomie 2 n'est pas décidé.",
    )


def engine(
    wf: Workflow,
    name: str,
    method: str,
    path: str,
    pos: tuple[float, float],
    *,
    params: str = "Paramètres",
    body: str | None = None,
    disabled: bool = False,
    notes: str | None = None,
    on_error: str | None = None,
    cred: str | None = None,
) -> str:
    """Appel HTTP de l'API du moteur avec le credential « Pokeshop API » **nommé par rôle** (en-tête X-Pokeshop-Token).

    ``cred`` : défaut = credential du workflow (``wf.api_cred``) ; ``api_photo`` (n8n-07-stoploss),
    ``api_tresorerie`` (connecteur-tresorerie), ``api_stock`` (operations-sav)… — jamais le jeton commun.
    """
    cred = cred or wf.api_cred
    if cred not in CREDENTIAL_ROLES or not CREDENTIALS[cred][2].startswith("Pokeshop API"):
        raise ValueError(f"credential non moteur : {cred}")
    parameters: dict[str, Any] = {
        "method": method,
        "url": f"={{{{ {ref(params)}.first().json.api_base_url }}}}{path}",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": 30000},
    }
    if body is not None:
        parameters.update({"sendBody": True, "specifyBody": "json", "jsonBody": f"={{{{ JSON.stringify({body}) }}}}"})
    extra: dict[str, Any] = {} if method != "GET" and on_error else {}
    if on_error:
        extra["onError"] = on_error
    else:
        extra.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})
    return wf.add(
        name,
        "n8n-nodes-base.httpRequest",
        4.2,
        parameters,
        pos,
        disabled=disabled,
        credentials=cred,
        notes=notes,
        **extra,
    )


def external(
    wf: Workflow,
    name: str,
    method: str,
    url: str,
    pos: tuple[float, float],
    cred: str,
    *,
    body: str | None = None,
    predefined: bool = False,
    notes: str,
    on_error: str | None = None,
) -> str:
    """Appel d'un service externe : **toujours désactivé** à l'import (écriture ou accès non encore autorisé).

    ``on_error="continueErrorOutput"`` : un échec suit la sortie 1 (bilan honnête) au lieu d'arrêter le workflow.
    """
    ctype = CREDENTIALS[cred][0]
    parameters: dict[str, Any] = {"method": method, "url": url}
    if predefined:
        parameters.update({"authentication": "predefinedCredentialType", "nodeCredentialType": ctype})
    else:
        parameters.update({"authentication": "genericCredentialType", "genericAuthType": ctype})
    if body is not None:
        parameters.update({"sendBody": True, "specifyBody": "json", "jsonBody": f"={{{{ JSON.stringify({body}) }}}}"})
    parameters["options"] = {"timeout": 30000}
    extra: dict[str, Any] = {}
    if on_error:
        extra.update({"onError": on_error, "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})
    return wf.add(
        name, "n8n-nodes-base.httpRequest", 4.2, parameters, pos, disabled=True, credentials=cred, notes=notes, **extra
    )


def email(
    wf: Workflow,
    name: str,
    pos: tuple[float, float],
    *,
    params: str = "Paramètres",
    subject: str = "={{ $json.sujet }}",
    text: str = "={{ $json.texte }}",
    notes: str | None = None,
) -> str:
    """Email (SMTP de la boîte des agents) à la responsable — désactivé jusqu'à la recette du canal."""
    return wf.add(
        name,
        "n8n-nodes-base.emailSend",
        2.1,
        {
            "fromEmail": AGENTS_EMAIL_PLACEHOLDER,
            "toEmail": f"={{{{ {ref(params)}.first().json.responsable_email }}}}",
            "subject": subject,
            "emailFormat": "text",
            "text": text,
            "options": {"appendAttribution": False},
        },
        pos,
        disabled=True,
        credentials="smtp",
        notes=notes or "Activer après création du credential SMTP et test d'envoi à la responsable (niveau 1 admis).",
    )


def slack(wf: Workflow, name: str, pos: tuple[float, float], *, text: str = "={{ $json.texte }}") -> str:
    """Message Slack (canal d'alerte de la propriétaire) — désactivé, canal à choisir (SOP_INCIDENTS §1)."""
    return wf.add(
        name,
        "n8n-nodes-base.slack",
        2.2,
        {
            "select": "channel",
            "channelId": {"__rl": True, "value": "#pokeshop-alertes", "mode": "name"},
            "text": text,
            "otherOptions": {},
        },
        pos,
        disabled=True,
        credentials="slack",
        notes="Canal facultatif : la propriétaire choisit le canal d'alerte immédiate (SOP_INCIDENTS.md §1).",
    )


def condition(left: str, op_type: str, operation: str, right: Any = None) -> dict[str, Any]:
    """Condition de filtre n8n (IF v2 / Switch v3)."""
    operator: dict[str, Any] = {"type": op_type, "operation": operation}
    single = operation in {"true", "false", "exists", "notExists", "empty", "notEmpty"}
    if single:
        operator["singleValue"] = True
    cond: dict[str, Any] = {
        "id": str(uuid.uuid5(NAMESPACE, f"cond:{left}:{operation}:{right}")),
        "leftValue": left,
        "operator": operator,
    }
    cond["rightValue"] = "" if right is None else right
    return cond


def _filter(conditions: Sequence[dict[str, Any]], combinator: str = "and") -> dict[str, Any]:
    return {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
        "conditions": list(conditions),
        "combinator": combinator,
    }


def if_node(
    wf: Workflow,
    name: str,
    pos: tuple[float, float],
    conditions: Sequence[dict[str, Any]],
    combinator: str = "and",
    notes: str | None = None,
) -> str:
    """IF v2.2 (sortie 0 = vrai, sortie 1 = faux), validation de type souple."""
    return wf.add(
        name,
        "n8n-nodes-base.if",
        2.2,
        {"conditions": _filter(conditions, combinator), "looseTypeValidation": True, "options": {}},
        pos,
        notes=notes,
    )


def switch_node(
    wf: Workflow, name: str, pos: tuple[float, float], left: str, outputs: Sequence[str], fallback: str
) -> str:
    """Switch v3.2 : une sortie par valeur exacte de ``left`` + une sortie de repli."""
    rules = [
        {"conditions": _filter([condition(left, "string", "equals", value)]), "renameOutput": True, "outputKey": value}
        for value in outputs
    ]
    return wf.add(
        name,
        "n8n-nodes-base.switch",
        3.2,
        {
            "rules": {"values": rules},
            "looseTypeValidation": True,
            "options": {"fallbackOutput": "extra", "renameFallbackOutput": fallback},
        },
        pos,
    )


def code_node(wf: Workflow, name: str, pos: tuple[float, float], js: str, notes: str | None = None) -> str:
    """Code JavaScript (transformation locale, aucun accès réseau, aucun secret)."""
    return wf.add(name, "n8n-nodes-base.code", 2, {"jsCode": js.strip() + "\n"}, pos, notes=notes)


def noop(wf: Workflow, name: str, pos: tuple[float, float], notes: str | None = None) -> str:
    """Fin de branche explicite (journal d'exécution n8n)."""
    return wf.add(name, "n8n-nodes-base.noOp", 1, {}, pos, notes=notes)


def cron(wf: Workflow, name: str, pos: tuple[float, float], expression: str) -> str:
    """Déclencheur planifié (fuseau du workflow : Europe/Zurich)."""
    return wf.add(
        name,
        "n8n-nodes-base.scheduleTrigger",
        1.2,
        {"rule": {"interval": [{"field": "cronExpression", "expression": expression}]}},
        pos,
    )


def webhook(
    wf: Workflow,
    name: str,
    pos: tuple[float, float],
    path: str,
    *,
    method: str = "POST",
    auth: str = "headerAuth",
    response_mode: str = "onReceived",
    notes: str | None = None,
    gateway: str | None = None,
) -> str:
    """Déclencheur webhook (passerelle d'un agent : en-tête secret par credential, **un secret par webhook**).

    ``gateway`` : clé du credential propre à ce webhook (:data:`INBOUND_SECRET_HOLDERS` : passerelle d'un agent ou
    notification du moteur), obligatoire pour un webhook authentifié (revue R4, SEC-16 : jamais un secret commun à
    plusieurs rôles).
    """
    params: dict[str, Any] = {"httpMethod": method, "path": path, "responseMode": response_mode, "options": {}}
    params["authentication"] = auth
    if auth == "headerAuth" and gateway not in INBOUND_SECRET_HOLDERS:
        raise ValueError(f"{name} : passerelle authentifiée sans credential propre (gateway={gateway!r})")
    return wf.add(
        name,
        "n8n-nodes-base.webhook",
        2,
        params,
        pos,
        webhook=True,
        credentials=gateway if auth == "headerAuth" else None,
        notes=notes,
    )


def shopify_trigger(wf: Workflow, name: str, pos: tuple[float, float], topic: str) -> str:
    """Déclencheur Shopify (signature HMAC vérifiée par n8n) ; l'activation crée l'abonnement chez Shopify."""
    return wf.add(
        name,
        "n8n-nodes-base.shopifyTrigger",
        1,
        {"authentication": "accessToken", "topic": topic},
        pos,
        webhook=True,
        credentials="shopify",
        notes="L'activation du workflow inscrit ce webhook chez Shopify (écriture) : activer au niveau 2 seulement.",
    )


def dedupe(wf: Workflow, name: str, pos: tuple[float, float], value: str, notes: str | None = None) -> str:
    """Supprime les éléments déjà vus lors d'exécutions précédentes (idempotence, n8n Remove Duplicates v2)."""
    return wf.add(
        name,
        "n8n-nodes-base.removeDuplicates",
        2,
        {
            "operation": "removeItemsSeenInPreviousExecutions",
            "logic": "removeItemsWithAlreadySeenKeyValues",
            "dedupeValue": value,
            "options": {"scope": "workflow", "historySize": 10000},
        },
        pos,
        notes=notes,
    )


def wait_form(
    wf: Workflow,
    name: str,
    pos: tuple[float, float],
    *,
    title: str,
    description: str,
    choices: Sequence[str],
    hours: int,
) -> str:
    """Attente d'une décision humaine par formulaire n8n protégé (Basic Auth), limitée dans le temps."""
    return wf.add(
        name,
        "n8n-nodes-base.wait",
        1.1,
        {
            "resume": "form",
            "incomingAuthentication": "basicAuth",
            "formTitle": title,
            "formDescription": description,
            "formFields": {
                "values": [
                    {
                        "fieldLabel": "Décision",
                        "fieldType": "dropdown",
                        "fieldOptions": {"values": [{"option": c} for c in choices]},
                        "requiredField": True,
                    },
                    {"fieldLabel": "Motif", "fieldType": "textarea", "requiredField": True},
                ]
            },
            "limitWaitTime": True,
            "limitType": "afterTimeInterval",
            "resumeAmount": hours,
            "resumeUnit": "hours",
            "options": {},
        },
        pos,
        webhook=True,
        credentials="owner_form",
        notes=f"Sans réponse sous {hours} h : la branche « non » s'applique (statu quo sûr).",
    )


def respond(wf: Workflow, name: str, pos: tuple[float, float], body: str, code: int) -> str:
    """Réponse JSON au demandeur d'un webhook en mode « Respond to Webhook »."""
    return wf.add(
        name,
        "n8n-nodes-base.respondToWebhook",
        1.1,
        {
            "respondWith": "json",
            "responseBody": f"={{{{ JSON.stringify({body}) }}}}",
            "options": {"responseCode": code},
        },
        pos,
    )


def respond_redirect(wf: Workflow, name: str, pos: tuple[float, float], url: str) -> str:
    """Réponse d'un webhook public par redirection (page du site)."""
    return wf.add(
        name,
        "n8n-nodes-base.respondToWebhook",
        1.1,
        {"respondWith": "redirect", "redirectURL": url, "options": {}},
        pos,
    )


def respond_html(wf: Workflow, name: str, pos: tuple[float, float], html: str, code: int) -> str:
    """Réponse HTML autonome (sans JavaScript ni ressource externe) d'un lien public des emails."""
    return wf.add(
        name,
        "n8n-nodes-base.respondToWebhook",
        1.1,
        {
            "respondWith": "text",
            "responseBody": html,
            "options": {
                "responseCode": code,
                "responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]},
            },
        },
        pos,
    )


def merge_node(wf: Workflow, name: str, pos: tuple[float, float], notes: str | None = None) -> str:
    """Merge v3 « append » : sorties de l'entrée 1 puis de l'entrée 2 (attend les deux branches)."""
    return wf.add(name, "n8n-nodes-base.merge", 3, {"mode": "append"}, pos, notes=notes)


def html_page(title: str, *paragraphs: str) -> str:
    """Page HTML minimale, accessible, sans script, sans ressource externe, non indexée."""
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return (
        '<!DOCTYPE html><html lang="fr-CH"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex, nofollow">'
        f"<title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "</style></head>"
        f"<body><main><h1>{title}</h1>{body}"
        f'<p><a href="{LANDING_PLACEHOLDER}/">Retour à l\'accueil</a></p></main></body></html>'
    )


def sticky(wf: Workflow, name: str, pos: tuple[float, float], content: str, width: int = 520, height: int = 420) -> str:
    """Note affichée sur le canevas (objectif, garde-fous, activation, validation humaine)."""
    return wf.add(
        name,
        "n8n-nodes-base.stickyNote",
        1,
        {"content": content.strip(), "height": height, "width": width, "color": 4},
        pos,
    )


def suspension_guard(
    wf: Workflow,
    col: float,
    row: float,
    *,
    params: str = "Paramètres",
    include_global: bool = True,
    suffix: str = "",
) -> tuple[str, str]:
    """Lit les incidents ouverts : si le workflow (ou, pour une dépense, toutes les écritures) est suspendu, on s'arrête.

    La clé comparée est la clé **canonique** du nœud « Paramètres » (:data:`WORKFLOW_KEYS`), la même que celle
    des incidents ouverts par le moteur et par le workflow d'erreur 04.
    ``include_global=False`` pour un cycle en simulation : la surveillance continue pendant un gel global
    (aucune écriture ; la porte de gouvernance du moteur refuse de toute façon les écritures réelles).
    ``suffix`` distingue plusieurs gardes d'un même workflow.
    """
    read = engine(
        wf, f"Garde : incidents ouverts{suffix}", "GET", "/incidents?open_only=true", (col, row), params=params
    )
    scope = " || t === '*'" if include_global else ""
    guard = if_node(
        wf,
        f"Workflow suspendu ?{suffix}",
        (col + 1, row),
        [
            condition(
                f"={{{{ Object.keys($json.suspended || {{}}).some(t => t === {ref(params)}.first().json.workflow"
                f"{scope}) }}}}",
                "boolean",
                "true",
            )
        ],
        notes="Suspension = incident ouvert sur ce workflow"
        + (
            " ou suspension globale de toutes les écritures (SOP_INCIDENTS §2)."
            if include_global
            else " (un gel global n'arrête pas une simulation : le moteur refuse toute écriture réelle)."
        ),
    )
    wf.link(read, guard)
    return read, guard


# ---------------------------------------------------------------------------- code JavaScript

JS_CENTS = r"""
// Montants décimaux en centimes entiers (aucun float pour un montant ; arrondi interdit).
function cents(value) {
  const text = String(value === undefined || value === null ? '' : value).trim();
  if (!/^-?\d+(\.\d{1,2})?$/.test(text)) throw new Error(`montant non décimal ou plus de 2 décimales : ${text}`);
  const negative = text.startsWith('-');
  const [intPart, frac = ''] = text.replace('-', '').split('.');
  const total = Number(intPart) * 100 + Number((frac + '00').slice(0, 2));
  return negative ? -total : total;
}
function chf(c) {
  const sign = c < 0 ? '-' : '';
  const a = Math.abs(c);
  return `${sign}${Math.trunc(a / 100)}.${String(a % 100).padStart(2, '0')}`;
}
"""

JS_FORMAT_CHF = r"""
// Affichage CHF suisse romand à partir d'une chaîne décimale du moteur (aucun float).
function fmt(value) {
  if (value === undefined || value === null || value === '') return '—';
  const text = String(value);
  const negative = text.startsWith('-');
  const [intPart, frac = ''] = text.replace('-', '').split('.');
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${negative ? '−' : ''}${grouped},${(frac + '00').slice(0, 2)} CHF`;
}
"""

JS_NORMALIZE_ORDER = (
    JS_CENTS
    + r"""
// Commande Shopify payée -> données utiles à la préparation, SANS donnée personnelle (ni nom, ni adresse,
// ni email : seul le code pays est lu pour vérifier « livraison Suisse uniquement »).
const out = [];
for (const item of $input.all()) {
  const o = item.json;
  const anomalies = [];
  const currency = o.currency || o.presentment_currency || null;
  if (currency !== 'CHF') anomalies.push(`devise ${currency} (CHF attendu)`);
  const country = o.shipping_address && o.shipping_address.country_code ? o.shipping_address.country_code : null;
  if (country !== 'CH') anomalies.push(`livraison hors Suisse ou pays inconnu (${country})`);
  if (o.financial_status !== 'paid') anomalies.push(`statut de paiement ${o.financial_status}`);
  if (o.test === true) anomalies.push('commande de test Shopify');
  const lines = (o.line_items || []).map((l) => ({ sku: l.sku || null, quantity: l.quantity, title: l.title }));
  if (!lines.length) anomalies.push('commande sans ligne');
  if (lines.some((l) => !l.sku)) anomalies.push('ligne sans SKU (identité produit inconnue)');
  const tags = String(o.tags || '').split(',').map((t) => t.trim().toLowerCase());
  let total = 0;
  let tax = 0;
  try {
    total = cents(o.current_total_price !== undefined ? o.current_total_price : o.total_price);
    tax = cents(o.current_total_tax !== undefined ? o.current_total_tax : o.total_tax);
  } catch (error) {
    anomalies.push(error.message);
  }
  out.push({
    json: {
      order_id: String(o.id),
      order_name: o.name,
      paid_at: o.processed_at || o.created_at,
      currency,
      preorder: tags.includes('precommande'),
      lines,
      lines_count: lines.length,
      total_ttc: chf(total),
      tax: chf(tax),
      net_ht: chf(total - tax),
      anomalies,
      anomalies_count: anomalies.length,
    },
  });
}
return out;
"""
)

JS_LATE_PARCELS = r"""
// Commandes payées non expédiées au-delà du délai annoncé (jours ouvrés, jours fériés non comptés).
const params = $('Paramètres — suivi').first().json;
const data = $input.first().json;
const nodes = data && data.data && data.data.orders ? data.data.orders.nodes : null;
if (!Array.isArray(nodes)) return []; // lecture Shopify non configurée : rien à signaler
function businessDays(fromIso, to) {
  const day = new Date(fromIso);
  day.setUTCHours(12, 0, 0, 0);
  const end = new Date(to);
  end.setUTCHours(12, 0, 0, 0);
  let count = 0;
  while (day < end) {
    day.setUTCDate(day.getUTCDate() + 1);
    const w = day.getUTCDay();
    if (w !== 0 && w !== 6) count += 1;
  }
  return count;
}
const now = new Date();
const late = nodes
  .map((o) => ({ order_name: o.name, paid_at: o.processedAt || o.createdAt, age: businessDays(o.processedAt || o.createdAt, now) }))
  .filter((o) => o.age > Number(params.delai_expedition_jours_ouvres));
if (!late.length) return [];
const lines = late.map((o) => `- ${o.order_name} : payée le ${o.paid_at}, ${o.age} jours ouvrés`);
return [{ json: {
  sujet: `[COLIS] ${late.length} commande(s) au-delà du délai d'expédition`,
  texte: `Commandes payées non remises au transporteur :\n${lines.join('\n')}\n\nAction : préparer et déposer (SOP_PREPARATION_COLIS.md) ou informer le client du délai réel.`,
} }];
"""

JS_PSP_FEES = r"""
// Frais réels du prestataire de paiement -> écritures PAYMENT de l'étoile polaire (montants en chaînes).
const data = $input.first().json;
const account = data && data.data ? data.data.shopifyPaymentsAccount : null;
const txs = account && account.balanceTransactions ? account.balanceTransactions.nodes : null;
if (!Array.isArray(txs)) return []; // lecture non configurée : aucune écriture
const entries = txs
  // Frais positifs seulement (revue R3) : un rôle ne déclare jamais un montant négatif ; un remboursement de
  // frais passe par l'avoir de la commande (POST /orders/{id}/refunds) ou par la propriétaire.
  // Revue R4 (R3-DOC-03) : UNE SEULE SOURCE PAR FRAIS — les frais d'une commande sont portés par POST /orders/shipped
  // (payment_fees) ; ici, seulement les frais sans commande (abonnement, frais de versement). Le moteur refuse en
  // plus tout PAYMENT portant l'order_id d'une commande enregistrée.
  .filter((t) => !t.associatedOrder)
  .filter((t) => t.fee && t.fee.currencyCode === 'CHF' && /^\d+(\.\d{1,2})?$/.test(String(t.fee.amount)) && !/^0+(\.0+)?$/.test(String(t.fee.amount)))
  .map((t) => ({
    entry_id: `psp:${t.id}:PAYMENT`,
    at: t.transactionDate,
    post: 'PAYMENT',
    amount: String(t.fee.amount),
    ref: String(t.id),
    source: 'psp',
    order_id: t.associatedOrder ? String(t.associatedOrder.id) : null,
  }));
if (!entries.length) return [];
return [{ json: { entries, count: entries.length } }];
"""

JS_SPEND_REQUESTER = r"""
// Passerelle 08 (revue R4) : le demandeur est celui du webhook appelé (secret propre à l'agent), jamais le corps.
const body = $input.first().json.body || {};
const request = Object.assign({}, body.request || {}, { requested_by: '__ROLE__' });
return [{ json: { body: Object.assign({}, body, { request }), demandeur: '__ROLE__' } }];
"""

JS_INVOICE_FOR_ENGINE = (
    JS_CENTS
    + r"""
// Facture validée par la propriétaire -> registre des factures du moteur (POST /costs/invoices), revues R4 et R5.
// Coût rendu unitaire ventilé : prix facturé HT + fret et douane répartis au prorata de la valeur. La TVA d'import est
// ventilée À PART (import_vat_unit_chf) : le moteur la compte au coût selon SON profil TVA (méthode effective :
// récupérable, hors coût ; non assujettie : coût) — jamais décidé ici (revue R5, R4-DOC-02).
const body = $('Facture extraite par l’agent 05 (passerelle)').first().json.body || {};
const lines = Array.isArray(body.lines) ? body.lines : [];
const fees = body.fees_chf || {};
const costFees = ['freight', 'customs'].reduce((sum, k) => sum + (fees[k] ? cents(fees[k]) : 0), 0);
const vatCents = fees.import_vat ? cents(fees.import_vat) : 0;
const goods = lines.reduce((sum, l) => sum + cents(l.invoice_unit_cost_chf) * l.qty, 0);
if (goods <= 0) throw new Error('facture sans valeur marchandise : rien à enregistrer');
const allocate = (total) => {
  let allocated = 0;
  return lines.map((l, i) => {
    const value = cents(l.invoice_unit_cost_chf) * l.qty;
    const share = i === lines.length - 1 ? total - allocated : Math.floor((total * value) / goods);
    allocated += share;
    return share;
  });
};
const feeShares = allocate(costFees);
const vatShares = allocate(vatCents);
const out = lines.map((l, i) => ({
  product_key: String(l.product_key),
  qty: l.qty,
  unit_cost_chf: chf(Math.round((cents(l.invoice_unit_cost_chf) * l.qty + feeShares[i]) / l.qty)),
  import_vat_unit_chf: chf(Math.round(vatShares[i] / l.qty)),
}));
// Date d'émission jamais dans le futur (revue R5, R4-DOC-08) : minuit UTC du jour de la facture, ou maintenant si
// la facture est validée avant cette heure (le moteur refuse une facture datée de plus de 5 min dans le futur).
const day = Date.parse(`${body.invoice_date}T00:00:00Z`);
if (Number.isNaN(day)) throw new Error(`date de facture illisible : ${body.invoice_date}`);
return [{ json: {
  invoice_ref: String(body.invoice_ref),
  supplier_id: String(body.supplier_id),
  issued_at: new Date(Math.min(day, Date.now())).toISOString(),
  total_chf: chf(goods + costFees + vatCents),
  lines: out,
  source: `facture ${body.invoice_ref} extraite par l'agent 05, validée par la propriétaire (formulaire 03)`,
} }];
"""
)

JS_INVOICE_CHECKS = (
    JS_CENTS
    + r"""
// Contrôles déterministes de la facture extraite par l'agent 05 (l'IA extrait, elle ne décide pas).
// Entrée : { invoice_ref, supplier_id, invoice_date, currency, fx: {rate, source, date}, goods_total_chf,
//            lines: [{ lot_id, product_key, qty, unit_basis, estimated_unit_cost_chf, invoice_unit_cost_chf }],
//            fees_chf: { freight, customs, import_vat }, documents: [...] }
// Revue R5 (R2-NEW-01 c) : quantités et coûts PAR UNITÉ DE VENTE (unit_basis « unité ») ; une ligne facturée au
// carton est convertie avant l'envoi (qty × contenu, coût ÷ contenu) — sinon anomalie, rien n'est enregistré.
const body = $input.first().json.body || {};
const anomalies = [];
for (const field of ['invoice_ref', 'supplier_id', 'invoice_date']) if (!body[field]) anomalies.push(`champ manquant : ${field}`);
if (body.currency !== 'CHF') {
  const fx = body.fx || {};
  if (!fx.rate || !fx.source || !fx.date) anomalies.push('devise étrangère : taux, source et date obligatoires (aucun taux choisi par une IA)');
}
const lines = Array.isArray(body.lines) ? body.lines : [];
if (!lines.length) anomalies.push('aucune ligne de facture');
let goods = 0;
const variances = [];
lines.forEach((line, i) => {
  if (!line.lot_id || !line.product_key) anomalies.push(`ligne ${i + 1} : lot ou référence manquant`);
  if (!Number.isInteger(line.qty) || line.qty <= 0) anomalies.push(`ligne ${i + 1} : quantité invalide`);
  const basis = line.unit_basis === undefined ? 'unité' : String(line.unit_basis);
  if (basis !== 'unité') anomalies.push(`ligne ${i + 1} : facturée « ${basis} » — convertir en unités de vente (quantité × contenu, coût ÷ contenu)`);
  let est;
  let act;
  try {
    est = cents(line.estimated_unit_cost_chf);
    act = cents(line.invoice_unit_cost_chf);
  } catch (error) {
    anomalies.push(`ligne ${i + 1} : ${error.message}`);
    return;
  }
  if (act <= 0) anomalies.push(`ligne ${i + 1} : coût facturé nul ou négatif`);
  const qty = Number.isInteger(line.qty) ? line.qty : 0;
  goods += act * qty;
  // Écart > 2 % : comparaison entière exacte |réel − estimé| × 50 > estimé.
  const flagged = est > 0 && Math.abs(act - est) * 50 > est;
  variances.push({ lot_id: line.lot_id, product_key: line.product_key, qty, basis, estimated: chf(est), invoice: chf(act), value: act * qty, flagged });
});
if (body.goods_total_chf !== undefined) {
  try {
    if (cents(body.goods_total_chf) !== goods) anomalies.push(`total des lignes ${chf(goods)} ≠ total marchandise ${body.goods_total_chf}`);
  } catch (error) {
    anomalies.push(`total marchandise : ${error.message}`);
  }
} else {
  anomalies.push('total marchandise absent : contrôle du total impossible');
}
// Frais affichés à la propriétaire (fret, douane, TVA d'import) et coût rendu unitaire calculé (hors TVA d'import).
const fees = body.fees_chf || {};
const feeOf = (k) => { try { return fees[k] ? cents(fees[k]) : 0; } catch (error) { anomalies.push(`frais ${k} : ${error.message}`); return 0; } };
const freight = feeOf('freight');
const customs = feeOf('customs');
const importVat = feeOf('import_vat');
const landed = (v) => (goods > 0 && v.qty > 0 ? chf(Math.round((v.value + Math.floor(((freight + customs) * v.value) / goods)) / v.qty)) : '?');
const flaggedLines = variances.filter((v) => v.flagged);
return [{ json: {
  invoice_ref: body.invoice_ref || null,
  supplier_id: body.supplier_id || null,
  goods_total_chf: chf(goods),
  lines: lines.length,
  variances: variances.map(({ value, ...v }) => v),
  flagged_count: flaggedLines.length,
  anomalies,
  anomalies_count: anomalies.length,
  fees_resume: `fret ${chf(freight)} CHF, douane ${chf(customs)} CHF, TVA d'import ${chf(importVat)} CHF (ventilée à part : comptée au coût selon le profil TVA du moteur)`,
  resume: variances.map((v) => `${v.lot_id} ${v.product_key} : ${v.qty} × ${v.basis} — facturé ${v.invoice} CHF/unité (estimé ${v.estimated}), coût rendu ${landed(v)} CHF/unité hors TVA d'import${v.flagged ? ' (ÉCART > 2 %)' : ''}`).join('\n'),
} }];
"""
)

JS_DIGEST = (
    JS_FORMAT_CHF
    + r"""
// Digest quotidien : 1. étoile polaire (GET /northstar), 2. stop-loss (GET /stoploss/status), puis le jour.
const ns = $('Étoile polaire (GET /northstar)').first().json;
const sl = $('État du stop-loss (GET /stoploss/status)').first().json;
const db = ($('Tableau de bord du jour (GET /dashboard/daily)').first().json || {}).report || {};
const hist = $('Cycles de synchronisation (GET /sync/history)').first().json || {};
const health = $('État du moteur (GET /health)').first().json || {};
const rows = Array.isArray(ns.rows) ? ns.rows : [];
const last = rows.length ? rows[rows.length - 1] : null;
const north = db.north_star || {};
const out = [];
out.push(`1. ÉTOILE POLAIRE — contribution nette cumulée : ${fmt(ns.cumulative)}`);
if (last) {
  out.push(`   Semaine ${last.iso_week} : ${fmt(last.net_contribution)} (delta vs semaine précédente : ${fmt(last.delta_vs_previous_week)})`);
} else {
  out.push('   Aucune écriture enregistrée (aucune vente ni charge).');
}
if (north.average_4_weeks !== undefined && north.average_4_weeks !== null) {
  out.push(`   Moyenne des ${north.average_weeks_count} dernière(s) semaine(s) close(s) : ${fmt(north.average_4_weeks)} ; tendance ${String(north.trend || '').toLowerCase()}`);
}
const LEVELS = { PRODUCT: 'produit', EXTENSION: 'extension', ADS: 'pub', CASH: 'cash', GLOBAL: 'GLOBAL', TIME: 'temps' };
const triggers = Array.isArray(sl.triggers) ? sl.triggers : [];
if (!sl.available) {
  out.push(`2. STOP-LOSS : NON ÉVALUÉ (${sl.error || 'photo absente'}) — dépenses refusées par défaut.${sl.global_frozen ? ' GEL GLOBAL VERROUILLÉ.' : ''}`);
} else if (sl.global_frozen) {
  out.push('2. STOP-LOSS : GEL GLOBAL — tout est gelé, autonomie niveau 1 ; réarmement par vous seule (POST /stoploss/rearm, votre jeton).');
} else if (triggers.length) {
  out.push(`2. STOP-LOSS : ${triggers.length} déclencheur(s)`);
  triggers.forEach((t) => out.push(`   - ${LEVELS[t.level] || t.level} / ${t.scope} : ${t.reason}`));
} else {
  out.push('2. STOP-LOSS : aucun déclencheur.');
}
const notif = health.notifications || {};
if (notif.real_time_alerts !== true) {
  const why = !notif.webhook_configured ? 'webhook n8n non configuré'
    : notif.webhook_dry_run ? 'POKESHOP_NOTIFY_DRY_RUN=true'
    : notif.webhook_secret_configured === false ? 'secret des notifications absent : POKESHOP_N8N_WEBHOOK_SECRET'
    : 'état inconnu';
  out.push(`   ALERTES TEMPS RÉEL INACTIVES (${why}) : un incident critique ne vous parvient que par ce digest.`);
} else if (notif.last_delivery && notif.last_delivery.delivered === false && notif.last_delivery.dry_run === false) {
  out.push(`   DERNIÈRE ALERTE NON LIVRÉE À 04 (${notif.last_delivery.detail || 'motif inconnu'}) : vérifier que 04 est actif et que son credential « Notification moteur → 04 » a la valeur de POKESHOP_N8N_WEBHOOK_SECRET (rotation faite des deux côtés), puis ouvrir un incident FICTIF.`);
}
const unreadable = (health.persistence || {}).unreadable;
if (Array.isArray(unreadable) && unreadable.length) out.push(`   JOURNAUX D'ÉTAT ILLISIBLES (${unreadable.join(', ')}) : service gelé jusqu'à réparation.`);
const kpis = {};
(db.kpis || []).forEach((k) => { kpis[k.key] = k; });
const order = ['ventes_payees', 'contribution_jour', 'cash_disponible', 'commandes_a_preparer', 'ruptures_locales', 'offres_perimees', 'incidents_ouverts'];
let n = 3;
order.forEach((key) => {
  const k = kpis[key];
  if (!k) return;
  out.push(`${n}. ${k.label} : ${k.display} [${k.status}]${k.detail ? ' — ' + k.detail : ''}`);
  n += 1;
});
const runs = Array.isArray(hist.runs) ? hist.runs : [];
const lastRun = runs.length ? runs[runs.length - 1] : null;
out.push(`${n}. Synchronisation fournisseurs : ${hist.consecutive_clean_runs === undefined ? '—' : hist.consecutive_clean_runs} cycle(s) propre(s) consécutif(s) sur ${hist.target || 20} visés`
  + (lastRun ? ` ; dernier cycle ${lastRun.status} (${lastRun.supplier_id}, ${lastRun.offers_costed} offre(s) évaluée(s))` : ' ; aucun cycle'));
n += 1;
const decisions = Array.isArray(db.decisions) ? db.decisions : [];
out.push(`${n}. DÉCISIONS ATTENDUES (oui / non, avant l'échéance ; sans réponse : statu quo sûr) :`);
if (!decisions.length) out.push('   aucune');
decisions.forEach((d, i) => out.push(`   ${String.fromCharCode(97 + (i % 26))}) ${d.label}${d.due ? ' — avant le ' + d.due : ''}`));
if (Array.isArray(db.unavailable) && db.unavailable.length) out.push(`Sources non branchées : ${db.unavailable.join(' ; ')}`);
out.push('');
out.push('INTERNE — contient coûts et marges : ne jamais transférer ni publier.');
const day = db.period_label || '';
return [{ json: { sujet: `DIGEST {{NOM_BOUTIQUE}} — ${day} — cumul ${fmt(ns.cumulative)}`, texte: out.join('\n') } }];
"""
)

JS_STOPLOSS_ANALYSIS = r"""
// Analyse de GET /stoploss/status : cause, chiffres, action, comment réarmer ; empreinte pour n'alerter qu'au changement.
const s = $input.first().json;
const refresh = $('Construire la photo (POST /stoploss/state/refresh)').first().json || {};
const built = refresh.origin === 'registres du moteur';
const refreshNote = built
  ? `photo construite par le moteur à partir de ses registres (relevés du ${(refresh.sources || {}).as_of || '?'})`
  : `photo NON construite : ${refresh.erreur || (refresh.error && (refresh.error.description || refresh.error.message)) || 'erreur inconnue'}`;
const triggers = Array.isArray(s.triggers) ? s.triggers : [];
const status = s.status || {};
const freeze = s.global_frozen === true || triggers.some((t) => t.action === 'FREEZE_ALL');
const cut = Array.isArray(status.cut_campaigns) ? status.cut_campaigns : [];
const LEVELS = { PRODUCT: 'Produit', EXTENSION: 'Extension', ADS: 'Publicité', CASH: 'Trésorerie', GLOBAL: 'Global', TIME: 'Temps' };
const ACTIONS = {
  BLOCK_SALE: 'vente et promotion bloquées', NO_REORDER: 'plus de réassort', PROPOSE_MARKDOWN: 'démarque proposée (à valider)',
  CUT_CAMPAIGN: 'campagne coupée', FREEZE_PURCHASES_AND_ADS: "plus d'achat ni de publicité",
  FREEZE_ALL: 'TOUT GELÉ, autonomie ramenée au niveau 1', DECISION_REPORT: 'dossier continuer / ajuster / arrêter',
};
const lines = triggers.map((t) => `- [${LEVELS[t.level] || t.level}] ${t.scope} — cause : ${t.reason} | mesure : ${t.value === null || t.value === undefined ? '—' : t.value} ; seuil : ${t.threshold === null || t.threshold === undefined ? '—' : t.threshold} | action : ${ACTIONS[t.action] || t.action}`);
const text = [];
if (!s.available) text.push(`Stop-loss NON ÉVALUABLE : ${s.error || 'photo absente'}. Le mandat refuse toute dépense tant que la photo d'activité manque.`,
  `Photo d'activité : ${refreshNote}. Sources : apports (POST /capital/movements, votre jeton), soldes PayPal et banque (connecteurs), stock au coût (POST /costs/movements).`);
if (freeze) text.push('GEL GLOBAL : tout est gelé, autonomie au niveau 1. Ce workflow a appliqué le gel (POST /stoploss/freeze).');
if (lines.length) text.push('Déclencheurs :', ...lines);
if (cut.length || status.ads_globally_cut) text.push(`Campagnes à couper : ${status.ads_globally_cut ? 'toutes' : cut.join(', ')} (nœud de coupure : à activer après recette).`);
if (freeze) {
  text.push('', 'Comment réarmer (vous seule) :',
    '1. Lire GET /stoploss/status : la cause, rearm_reference.net_worth_chf (valeur nette) et rearm_reference.photo_sha256 ; écrire votre motif (docs/00-pilotage/STOP_LOSS.md §5).',
    '2. Depuis votre terminal : POST /stoploss/rearm avec les en-têtes X-Pokeshop-Token et X-Pokeshop-Owner-Token (votre jeton, jamais transmis à un agent) et le corps {"reason": "…", "rebase": true, "reference_chf": "<rearm_reference.net_worth_chf>", "photo_sha256": "<rearm_reference.photo_sha256>"} : vous attestez la valeur nette (écart > 1 CHF ou photo remplacée => refus 409).',
    "3. L'autonomie reste au niveau 1 : la remonter est une décision distincte (POST /autonomy).");
}
if (s.report_markdown) text.push('', s.report_markdown);
text.push('', 'INTERNE — contient coûts et marges : ne jamais transférer ni publier.');
const fingerprint = [status.triggers_hash || '', s.available ? 'ok' : `ko:${s.error || ''}`, freeze ? 'gel' : 'libre'].join('|');
return [{ json: {
  available: s.available === true,
  photo_built: built,
  global_frozen: freeze,
  has_triggers: triggers.length > 0,
  has_freeze_all: freeze,
  cut_campaigns: status.ads_globally_cut ? ['*'] : cut,
  must_cut: cut.length > 0 || status.ads_globally_cut === true,
  blocked_products: status.blocked_products || [],
  fingerprint,
  freeze_reason: freeze ? `Stop-loss global constaté par n8n:07 (${triggers.filter((t) => t.action === 'FREEZE_ALL').map((t) => t.reason).join(' ; ') || 'gel verrouillé'})` : '',
  sujet: `[STOP-LOSS] ${freeze ? 'GEL GLOBAL' : !s.available ? 'NON ÉVALUABLE' : `${triggers.length} déclencheur(s)`}`,
  texte: text.join('\n'),
} }];
"""

JS_ON_CHANGE = r"""
// Une alerte par CHANGEMENT d'état (et non « jamais vu ») : l'empreinte est comparée à la dernière signalée,
// mémorisée dans les données statiques du workflow (exécutions de production ; une exécution manuelle ne les
// conserve pas). Un état qui disparaît puis réapparaît est donc de nouveau signalé, gel et coupure compris.
const memo = $getWorkflowStaticData('global');
const item = $input.first();
if (memo.dernier_etat === item.json.fingerprint) return [];
memo.dernier_etat = item.json.fingerprint;
return [item];
"""

JS_FORGET_STATE = r"""
// Aucun déclencheur : l'état signalé est oublié, pour qu'une réapparition (même empreinte) soit de nouveau alertée.
const memo = $getWorkflowStaticData('global');
memo.dernier_etat = 'aucun';
return $input.all();
"""

JS_FIND_INCIDENT = r"""
// Retrouve l'incident de la demande de reprise dans GET /incidents (test enregistré par l'agent 12 QA
// avec SON jeton nommé, ou par la propriétaire : la passerelle n'enregistre jamais un test réussi).
const wanted = $('Demande de reprise (passerelle agents)').first().json.body.incident_id;
const all = ($input.first().json.incidents || []);
const incident = all.find((i) => i.incident_id === wanted);
if (!incident) {
  return [{ json: { incident: { incident_id: wanted, test_passed: false, test_ref: null, title: 'incident inconnu', cause: 'incident introuvable' } } }];
}
return [{ json: { incident } }];
"""

JS_PAYPAL_BALANCE = r"""
// Réponse PayPal « List all balances » (GET v1/reporting/balances) -> relevé CHF du compte dédié.
// Aucun montant inventé : sans réponse, sans solde CHF ou sans date du relevé, rien n'est déposé.
const data = $input.first().json || {};
const balances = Array.isArray(data.balances) ? data.balances : null;
if (!balances || !data.as_of_time) return [];
const chf = balances.find((b) => b.currency === 'CHF' || (b.total_balance || {}).currency_code === 'CHF');
const amount = chf && chf.available_balance ? String(chf.available_balance.value) : '';
if (!/^\d+(\.\d{1,2})?$/.test(amount)) return [];
return [{ json: { as_of: data.as_of_time, balance_chf: amount, source: 'API PayPal v1/reporting/balances (compte dédié)' } }];
"""

JS_BANK_BALANCE = r"""
// Connecteur bancaire (contrat à adapter à la banque retenue) : { currency: 'CHF', balance_chf: '1234.56', as_of: ISO }.
// Aucun montant inventé : réponse absente, devise autre que CHF ou date manquante => rien n'est déposé.
const data = $input.first().json || {};
const amount = String(data.balance_chf === undefined || data.balance_chf === null ? '' : data.balance_chf);
if (data.currency !== 'CHF' || !data.as_of || !/^-?\d+(\.\d{1,2})?$/.test(amount)) return [];
return [{ json: { as_of: data.as_of, balance_chf: amount, source: 'connecteur bancaire (compte de l’activité)' } }];
"""

JS_SUBSCRIBERS = r"""
// Inscrits consentants pour l'alerte « nouveau stock local » (email 04) : statut confirmé, non désinscrit,
// alerte demandée sur ce produit ou préférence de format correspondante. Aucune adresse n'est manipulée ici :
// l'outil d'emailing envoie à partir de l'identifiant d'inscrit.
const reception = $('Réception contrôlée (passerelle agent 11)').first().json.body || {};
const data = $input.first().json;
const subscribers = data && Array.isArray(data.subscribers) ? data.subscribers : null;
if (!subscribers) return []; // outil d'emailing non branché : aucun envoi
const format = String(reception.format_preference || '').toLowerCase();
return subscribers
  .filter((s) => s.status === 'confirme' && s.unsubscribed !== true)
  .filter((s) => (Array.isArray(s.alert_products) && s.alert_products.includes(reception.product_key))
    || (format && Array.isArray(s.formats) && s.formats.includes(format)))
  .map((s) => ({ json: { subscriber_id: String(s.id), product_key: reception.product_key, public_title: reception.public_title, public_url: reception.public_url } }));
"""

JS_REVIEW_ELIGIBILITY = r"""
// Demande d'avis (email 11) : une seule par commande, aucune réclamation ouverte, client non opposé (note C3).
const data = $input.first().json;
const order = data && data.data ? data.data.order : null;
if (!order) return []; // lecture Shopify non configurée : aucun envoi
const tags = (order.tags || []).map((t) => String(t).toLowerCase());
if (tags.includes('reclamation') || tags.includes('avis-refus')) return [];
if (!order.customer || !order.customer.id) return [];
return [{ json: { customer_id: String(order.customer.id), order_name: order.name } }];
"""

JS_LINK_TOKEN = r"""
// Lien public d'un email (jeton unique, EMAILS §4 règle 7). Jeton absent ou mal formé : la demande ne peut pas être
// identifiée — elle n'est JAMAIS ignorée en silence (page d'erreur honnête et, pour une opposition, incident).
const item = $input.first().json;
const token = item.query && item.query.jeton ? String(item.query.jeton) : '';
const valide = /^[A-Za-z0-9_-]{16,128}$/.test(token);
return [{ json: { etape: 'normalise', valide, jeton: valide ? token : null, received_at: new Date().toISOString() } }];
"""


def js_prepare_shopify(link_node: str, ok_field: str) -> str:
    """Résultat de l'outil d'emailing (succès, erreur ou nœud désactivé) -> étape Shopify éventuelle."""
    return (
        r"""
// Résultat de l'outil d'emailing -> préparation de l'étape Shopify (client lié au jeton, s'il existe).
// Nœud désactivé (outil non branché) : la donnée normalisée passe telle quelle => « non branché », jamais « confirmé ».
const j = $input.first().json || {};
const lien = $('LINK_NODE').first().json;
let emailing;
if (j.error) emailing = `échec (${(j.error && j.error.message) || 'erreur'})`;
else if (j.etape === 'normalise') emailing = 'non branché (nœud désactivé)';
else emailing = j.OK_FIELD === true ? 'confirmé' : 'réponse non conforme';
const customer = emailing === 'confirmé' && j.shopify_customer_id ? String(j.shopify_customer_id).replace(/\D/g, '') : '';
return [{ json: { etape: 'prepare', jeton: lien.jeton, emailing, shopify_customer_id: customer || null,
  shopify_applicable: customer !== '' } }];
"""
        .replace("LINK_NODE", link_node)
        .replace("OK_FIELD", ok_field)
    )


def js_bilan(prepare_node: str, mutation: str) -> str:
    """Bilan honnête : seul un retrait CONFIRMÉ par chaque outil compte."""
    return (
        r"""
// Bilan : seul un résultat CONFIRMÉ par chaque outil compte ; nœud désactivé, erreur ou réponse non conforme => non
// confirmé (incident pour un traitement manuel sans délai, envois marketing suspendus jusqu'à la reprise).
const prep = $('PREPARE_NODE').first().json;
const j = $input.first().json || {};
let shopify;
if (!prep.shopify_applicable) shopify = prep.emailing === 'confirmé' ? 'sans objet (aucun client Shopify lié)' : 'non vérifié';
else if (j.error) shopify = `échec (${(j.error && j.error.message) || 'erreur'})`;
else if (j.etape === 'prepare') shopify = 'non branché (nœud désactivé)';
else {
  const r = j.data && j.data.MUTATION;
  shopify = r && Array.isArray(r.userErrors) && r.userErrors.length === 0 ? 'confirmé' : 'réponse non conforme';
}
const ok = prep.emailing === 'confirmé' && (!prep.shopify_applicable || shopify === 'confirmé');
return [{ json: { tous_confirmes: ok, jeton: prep.jeton, resume: `outil d’emailing : ${prep.emailing} ; Shopify : ${shopify}` } }];
"""
        .replace("PREPARE_NODE", prepare_node)
        .replace("MUTATION", mutation)
    )


JS_SHOPIFY_UNSUBSCRIBE = r"""
// Consentement marketing retiré dans Shopify : à propager à l'outil d'emailing. Journal sans adresse.
const item = $input.first().json;
return [{ json: { etape: 'normalise', shopify_customer_id: String(item.id || ''), received_at: new Date().toISOString() } }];
"""

JS_SHOPIFY_UNSUBSCRIBE_BILAN = r"""
// Bilan de la propagation Shopify -> outil d'emailing : seul un retrait confirmé par l'outil compte.
const j = $input.first().json || {};
let emailing;
if (j.error) emailing = `échec (${(j.error && j.error.message) || 'erreur'})`;
else if (j.etape === 'normalise') emailing = 'non branché (nœud désactivé)';
else emailing = j.unsubscribed === true ? 'confirmé' : 'réponse non conforme';
return [{ json: { tous_confirmes: emailing === 'confirmé', resume: `outil d’emailing : ${emailing} ; Shopify : retrait déjà fait (origine)` } }];
"""

JS_CONFIRM_ANSWER = r"""
// Double opt-in : seule une confirmation explicite de l'outil d'emailing ({ confirmed: true }) active les alertes.
const j = $input.first().json || {};
return [{ json: { confirmed: !j.error && j.etape !== 'normalise' && j.confirmed === true } }];
"""


def js_preferences_answer(link_node: str, page: str) -> str:
    """Adresse https de la page de préférences fournie par l'outil, sinon page honnête (désinscription possible)."""
    return (
        r"""
// Page de préférences : adresse https fournie par l'outil d'emailing ; sinon page honnête qui offre la désinscription.
const j = $input.first().json || {};
const lien = $('LINK_NODE').first().json;
const url = !j.error && j.etape !== 'normalise' && typeof j.preferences_url === 'string' && /^https:\/\//.test(j.preferences_url)
  ? j.preferences_url : null;
return [{ json: { preferences_url: url, html: PAGE.replace('__JETON__', lien.jeton) } }];
"""
        .replace("LINK_NODE", link_node)
        .replace("PAGE", json.dumps(page, ensure_ascii=False))
    )



# -------------------------------------------------------------------------------- workflows


def wf01(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Fournisseur -> site (BP §5 « Synchronisation proposée », §12) : prix 6 h, stock amont 45 min, simulation."""
    wf = Workflow(WORKFLOW_IDS["01"], WORKFLOW_NAMES["01"], "01_fournisseur_vers_site.json", credentials_map=cmap)
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.2),
        """
## 01 — Fournisseur vers site (BP §5, §12)
Prix et offres **toutes les 6 h** : import puis cycle complet. Stock amont **toutes les 45 min** : import seul
(disponibilité amont et âge de la source), **sans** réévaluer les prix (BP §5).
1. Récupérer le flux autorisé et le déposer dans le dossier d'import (nœuds désactivés : aucun accès fournisseur n'existe).
2. `POST /imports/{fournisseur}/run` — **simulation**, quarantaine des anomalies.
3. `POST /sync/run` avec **dry_run: true** : 8 étapes du BP §12 sur le **catalogue validé et les frais enregistrés
   dans le moteur** (`POST /catalog/items`, `/catalog/cost-inputs`, taux `POST /fx/rates`) ; sans catalogue : 409.
   Un cycle n'est **propre** que s'il évalue au moins une offre (`GET /sync/history` : cycles propres consécutifs).
Import rejeté (> 24 h, incomplet, ×10…) => incident **INC-03** (achats et promesses bloqués ; le stock local se vend).
**Activation** : niveau 1 (simulation). Passer `dry_run` à false = décision C14 (niveau 2) + `POKESHOP_DRY_RUN=false`.
**Validation humaine requise** : accès autorisé à chaque flux (B-xx), liste des fournisseurs du nœud Paramètres, catalogue validé.
""",
        width=680,
        height=440,
    )
    t1 = cron(wf, "Toutes les 6 h — prix et offres", (0, 0), "5 */6 * * *")
    t2 = wf.add(
        "Toutes les 45 min — stock amont",
        "n8n-nodes-base.scheduleTrigger",
        1.2,
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": 45}]}},
        (0, 1),
    )
    c1 = set_node(wf, "Cycle : prix et offres", (1, 0), [("cycle", "prix_offres", "string")])
    c2 = set_node(wf, "Cycle : stock amont", (1, 1), [("cycle", "stock_amont", "string")])
    p = params_node(
        wf,
        "Paramètres",
        (2, 0.5),
        WORKFLOW_KEYS["01"],
        (
            "fournisseurs",
            '={{ [{"supplier": "fictif_grossiste_a", "source_path": "FICTIF_offres_grossiste_a.csv"}, '
            '{"supplier": "fictif_grossiste_b", "source_path": "FICTIF_tarif_grossiste_b.xlsx"}, '
            '{"supplier": "fictif_grossiste_c", "source_path": "FICTIF_flux_grossiste_c.xml"}] }}',
            "array",
        ),
    )
    wf.chain(t1, c1, p)
    wf.chain(t2, c2, p)
    read, guard = suspension_guard(wf, 3, 0.5, include_global=False)
    wf.link(p, read)
    stop = noop(wf, "Workflow suspendu : cycle ignoré", (5, -0.5))
    wf.link(guard, stop, 0)
    lst = set_node(
        wf,
        "Liste des fournisseurs",
        (5, 0.5),
        [("fournisseurs", f"={{{{ {ref('Paramètres')}.first().json.fournisseurs }}}}", "array")],
        include_other=False,
    )
    wf.link(guard, lst, 1)
    split = wf.add(
        "Un élément par fournisseur",
        "n8n-nodes-base.splitOut",
        1,
        {"fieldToSplitOut": "fournisseurs", "options": {}},
        (6, 0.5),
    )
    wf.link(lst, split)
    item = f"{ref('Un élément par fournisseur')}.item.json"
    fetch = external(
        wf,
        "Récupérer le flux autorisé — À CONFIGURER (désactivé)",
        "GET",
        f"=https://REMPLACER-flux-autorise.exemple.invalid/{{{{ {item}.supplier }}}}/export",
        (7, 0.5),
        "supplier",
        notes="Priorité 1 : API ou flux documenté ; 2 : fichier fourni ; 3 : import assisté. Jamais de scraping ni de "
        "contournement d'un contrôle d'accès (BP §6). Activer seulement avec un accès écrit du fournisseur.",
    )
    drop = wf.add(
        "Déposer le fichier dans le dossier d'import — À CONFIGURER (désactivé)",
        "n8n-nodes-base.readWriteFile",
        1,
        {
            "operation": "write",
            "fileName": f"=/data/imports/{{{{ {item}.source_path }}}}",
            "dataPropertyName": "data",
            "options": {},
        },
        (8, 0.5),
        disabled=True,
        notes="Dossier partagé avec l'API (POKESHOP_IMPORTS_DIR) : volume à ajouter au docker-compose (intégrations).",
    )
    imp = engine(
        wf,
        "Import (simulation)",
        "POST",
        f"/imports/{{{{ {item}.supplier }}}}/run",
        (9, 0.5),
        body=f"{{ source_path: {item}.source_path }}",
    )
    ok_import = if_node(
        wf,
        "Import exploitable ?",
        (10, 0.5),
        [
            condition("={{ $json.status }}", "string", "equals", "ACCEPTED"),
            condition("={{ $json.status }}", "string", "equals", "PARTIAL"),
        ],
        combinator="or",
    )
    stock_only = if_node(
        wf,
        "Cycle stock amont ?",
        (11, 0),
        [condition(f"={{{{ {ref('Paramètres')}.first().json.cycle }}}}", "string", "equals", "stock_amont")],
        notes="Stock amont (45 min) : import seul, aucun prix réévalué ; prix et offres (6 h) : cycle complet.",
    )
    stock_done = noop(wf, "Stock amont : import seul (prix non réévalués)", (12, -0.8))
    sync = engine(
        wf,
        "Cycle fournisseur vers site (dry-run)",
        "POST",
        "/sync/run",
        (12, 0),
        body=f"{{ supplier: {item}.supplier, source_path: {item}.source_path, dry_run: true }}",
        notes="dry_run: true explicite. Catalogue validé et frais : registres du moteur (sans catalogue : 409). "
        "Le moteur ouvre lui-même les incidents d'anomalie (simulation).",
    )
    clean = if_node(wf, "Cycle propre ?", (13, 0), [condition("={{ $json.clean }}", "boolean", "true")])
    ok = noop(wf, "Journal : cycle propre", (14, -0.5))
    alert = set_node(
        wf,
        "Préparer l'alerte de cycle",
        (14, 0.5),
        [
            ("sujet", f"=[SYNC] Cycle {{{{ $json.cycle_status }}}} : {{{{ {item}.supplier }}}}", "string"),
            (
                "texte",
                "={{ $json.report_markdown }}\n\nINTERNE — contient coûts et marges : ne jamais transférer ni publier.",
                "string",
            ),
        ],
    )
    mail = email(wf, "Alerter la responsable (email, désactivé)", (15, 0.5))
    incident = engine(
        wf,
        "Ouvrir un incident de flux (INC-03)",
        "POST",
        "/incidents",
        (11, 1.2),
        body=(
            f"{{ cause: 'Import ' + $json.status + ' pour ' + {item}.supplier + ' (simulation)', code: 'INC-03', "
            f"supplier_id: {item}.supplier, workflow: {ref('Paramètres')}.first().json.workflow, "
            f"actor: 'n8n:01-fournisseur-site', simulation: {ref('Paramètres')}.first().json.simulation, "
            "details: { status: $json.status, reason_counts: $json.reason_counts, escalation: $json.escalation } }"
        ),
        notes="Le stock local confirmé n'est jamais touché par une panne de flux (BP §12).",
    )
    wf.chain(split, fetch, drop, imp, ok_import)
    wf.link(ok_import, stock_only, 0)
    wf.link(ok_import, incident, 1)
    wf.link(stock_only, stock_done, 0)
    wf.link(stock_only, sync, 1)
    wf.link(sync, clean)
    wf.link(clean, ok, 0)
    wf.link(clean, alert, 1)
    wf.link(alert, mail)
    return wf


def wf02(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Commande -> livraison (BP §12) : paiement confirmé, doublon, réservation, bon, tâche colis HUMAINE, suivi, rapprochement."""
    wf = Workflow(
        WORKFLOW_IDS["02"],
        WORKFLOW_NAMES["02"],
        "02_commande_vers_livraison.json",
        keep_success_data=False,
        credentials_map=cmap,
    )
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.4),
        """
## 02 — Commande vers livraison (BP §12)
Paiement confirmé (webhook Shopify **orders/paid**, signature vérifiée) → **contrôle de doublon** (idempotence n8n)
→ anomalies (CHF, Suisse, payée) → réservation (route moteur attendue) → **bon de préparation**
→ **tâche colis HUMAINE** : un robot ne prépare pas un colis (picking, emballage, scan, dépôt : la propriétaire).
Suivi : la propriétaire saisit le numéro dans Shopify, qui envoie l'email 07 ; colis en retard signalés chaque matin.
Rapprochement hebdomadaire : frais PSP réels **sans commande** (abonnement, versement) → étoile polaire
(`POST /northstar/entries`) ; les frais d'une commande viennent de `POST /orders/shipped` (`payment_fees`, BL-199) :
jamais comptés deux fois (le moteur refuse un PAYMENT portant l'`order_id` d'une commande enregistrée).
Données personnelles : aucune conservée (exécutions réussies non sauvegardées).
**Activation** : niveau 2 (l'activation inscrit le webhook chez Shopify).
**Validation humaine requise** : délai d'expédition (DELAI_EXPEDITION), jours de dépôt, route moteur de réservation.
""",
        width=640,
        height=400,
    )
    trigger = shopify_trigger(wf, "Shopify : commande payée (orders/paid)", (0, 0), "orders/paid")
    pa = params_node(
        wf, "Paramètres — commande", (1, 0), WORKFLOW_KEYS["02"], ("delai_expedition_jours_ouvres", 3, "number")
    )
    dup = dedupe(
        wf,
        "Contrôle doublon (idempotence)",
        (2, 0),
        "={{ $json.id }}",
        notes="Shopify peut livrer un webhook plusieurs fois : une commande n'est traitée qu'une fois.",
    )
    norm = code_node(wf, "Normaliser la commande (centimes, sans donnée personnelle)", (3, 0), JS_NORMALIZE_ORDER)
    anomaly = if_node(wf, "Anomalie ?", (4, 0), [condition("={{ $json.anomalies_count }}", "number", "gt", 0)])
    inc = engine(
        wf,
        "Ouvrir un incident commande",
        "POST",
        "/incidents",
        (5, -0.6),
        params="Paramètres — commande",
        body=(
            f"{{ cause: 'Commande ' + $json.order_name + ' : ' + $json.anomalies.join(' ; '), kind: 'COMMANDE_ANOMALIE', "
            "severity: 'MAJEUR', scope: 'WORKFLOW', workflow: '02-commande:' + $json.order_name, "
            "proposed_action: 'Vérifier la commande dans Shopify (pays, devise, paiement) ; aucune préparation tant que "
            "l’anomalie n’est pas levée ; ne jamais modifier le prix d’une commande conclue.', "
            f"actor: 'n8n:02-commande-livraison', simulation: {ref('Paramètres — commande')}.first().json.simulation, "
            "details: { order_ref: $json.order_name, anomalies: $json.anomalies } }"
        ),
    )
    reserve = engine(
        wf,
        "Réserver le stock local — route moteur attendue (désactivé)",
        "POST",
        "/orders/paid",
        (5, 0.4),
        params="Paramètres — commande",
        disabled=True,
        body="{ order_id: $json.order_id, order_ref: $json.order_name, paid_at: $json.paid_at, lines: $json.lines, "
        "net_ht: $json.net_ht }",
        notes="Route à créer (agent integrations) : StockRegistry.reserve (contrôle de concurrence), survente => INC-06, "
        "écriture NET_SALES de l'étoile polaire. Ne pas activer avant.",
    )
    slip = set_node(
        wf,
        "Bon de préparation",
        (6, 0.4),
        [
            ("sujet", "=[COLIS] {{ $json.order_name }}{{ $json.preorder ? ' — PRÉCOMMANDE' : '' }}", "string"),
            (
                "texte",
                "=Commande {{ $json.order_name }} payée le {{ $json.paid_at }}.\n"
                "{{ $json.lines.map(l => '- ' + l.quantity + ' × ' + l.sku + ' — ' + l.title).join('\\n') }}\n\n"
                "{{ $json.preorder ? 'PRÉCOMMANDE : ne pas préparer avant réception du stock alloué.' : 'Remise au transporteur sous ' + "
                "$('Paramètres — commande').first().json.delai_expedition_jours_ouvres + ' jours ouvrés (hypothèse DELAI_EXPEDITION).' }}\n"
                "Tâche HUMAINE (SOP_PREPARATION_COLIS.md) : picking, contrôle langue et scellé, scan, emballage, étiquette, dépôt ; "
                "puis « Traiter la commande » dans Shopify avec le numéro de suivi (Shopify envoie l'email 07).",
                "string",
            ),
        ],
    )
    task = email(
        wf, "Tâche colis HUMAINE — notifier la responsable (email, désactivé)", (7, 0.4), params="Paramètres — commande"
    )
    done = noop(wf, "Journal : commande prise en charge", (8, 0.4))
    wf.chain(trigger, pa, dup, norm, anomaly)
    wf.link(anomaly, inc, 0)
    wf.link(anomaly, reserve, 1)
    wf.chain(reserve, slip, task, done)
    # Suivi quotidien des colis.
    t2 = cron(wf, "Chaque jour ouvré 07:30 — colis à remettre", (0, 2), "30 7 * * 1-5")
    pb = params_node(
        wf, "Paramètres — suivi", (1, 2), WORKFLOW_KEYS["02"], ("delai_expedition_jours_ouvres", 3, "number")
    )
    read = external(
        wf,
        "Lire les commandes payées non expédiées — Shopify (désactivé)",
        "POST",
        SHOPIFY_GRAPHQL_PLACEHOLDER,
        (2, 2),
        "shopify",
        predefined=True,
        body='{ query: \'query { orders(first: 100, query: "financial_status:paid fulfillment_status:unfulfilled") '
        "{ nodes { name processedAt createdAt } } }' }",
        notes="Lecture seule (Admin GraphQL). Activer avec le credential Shopify, après recette.",
    )
    late = code_node(wf, "Colis en retard ?", (3, 2), JS_LATE_PARCELS)
    late_mail = email(wf, "Alerter : colis en retard (email, désactivé)", (4, 2), params="Paramètres — suivi")
    wf.chain(t2, pb, read, late, late_mail)
    # Rapprochement hebdomadaire des versements.
    t3 = cron(wf, "Chaque lundi 06:30 — rapprochement des versements", (0, 3.2), "30 6 * * 1")
    pc = params_node(wf, "Paramètres — rapprochement", (1, 3.2), WORKFLOW_KEYS["02"])
    tx = external(
        wf,
        "Lire les transactions de versement — Shopify Payments (désactivé)",
        "POST",
        SHOPIFY_GRAPHQL_PLACEHOLDER,
        (2, 3.2),
        "shopify",
        predefined=True,
        body="{ query: 'query { shopifyPaymentsAccount { balanceTransactions(first: 100) { nodes { id type transactionDate "
        "fee { amount currencyCode } associatedOrder { id } } } } }' }",
        notes="Lecture seule ; champs GraphQL à revérifier sur la version 2026-10 avant activation.",
    )
    fees = code_node(wf, "Frais de paiement réels vers écritures", (3, 3.2), JS_PSP_FEES)
    record = engine(
        wf,
        "Enregistrer les frais réels (étoile polaire)",
        "POST",
        "/northstar/entries",
        (4, 3.2),
        params="Paramètres — rapprochement",
        body="{ entries: $json.entries }",
        notes="Écritures idempotentes (entry_id psp:<transaction>) : un rejeu ne double rien. Identifiants order:, "
        "refund:, cost: réservés au moteur ; frais d'une commande : POST /orders/shipped seulement.",
    )
    summary = set_node(
        wf,
        "Résumé du rapprochement",
        (5, 3.2),
        [
            ("sujet", "=[RAPPROCHEMENT] {{ $json.added }} écriture(s) de frais PSP ajoutée(s)", "string"),
            (
                "texte",
                "=Frais PSP réels enregistrés : {{ $json.added }} nouvelle(s) sur {{ $json.received }} reçue(s).\n"
                "Écart paiement / versement : à expliquer dans la revue hebdomadaire (BL-166).",
                "string",
            ),
        ],
    )
    summary_mail = email(
        wf, "Envoyer le résumé du rapprochement (email, désactivé)", (6, 3.2), params="Paramètres — rapprochement"
    )
    wf.chain(t3, pc, tx, fees, record, summary, summary_mail)
    return wf


def wf03(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Facture -> marge réelle (BP §12) : import assisté, contrôles, validation humaine, coût historique, écarts."""
    wf = Workflow(WORKFLOW_IDS["03"], WORKFLOW_NAMES["03"], "03_facture_vers_marge_reelle.json", credentials_map=cmap)
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.2),
        """
## 03 — Facture vers marge réelle (BP §12)
L'agent 05 extrait la facture et le justificatif d'import (PDF/email) et l'envoie à **sa** passerelle (secret de l'agent 05 seul).
**Contrôles déterministes** (centimes, total des lignes, devise + taux sourcé) → **validation humaine** de l'extraction
(formulaire protégé, 72 h) → frais ventilés au coût rendu unitaire → **facture enregistrée au moteur**
(`POST /costs/invoices`, jeton `n8n-03-factures`) : référence du coût d'une réception (± 2 %, sinon propriétaire) et dette
de la photo du stop-loss jusqu'au paiement relevé (`POST /costs/invoices/{ref}/payments`, connecteur-tresorerie ou
propriétaire) → **écarts > 2 %** signalés. Jamais de modification d'une commande client déjà conclue.
**Activation** : niveau 1 (contrôles, validation, enregistrement de la facture).
**Validation humaine requise** : chaque extraction (A_VALIDER_HUMAINEMENT), seuil d'écart de 2 %.
""",
        width=640,
        height=340,
    )
    hook = webhook(
        wf, "Facture extraite par l’agent 05 (passerelle)", (0, 0), "pokeshop-facture", gateway="gateway_03",
        notes="Secret remis au seul agent 05 (credential « Passerelle 03 factures »).",
    )
    p = params_node(wf, "Paramètres", (1, 0), WORKFLOW_KEYS["03"])
    checks = code_node(wf, "Contrôles déterministes (centimes)", (2, 0), JS_INVOICE_CHECKS)
    coherent = if_node(
        wf, "Extraction cohérente ?", (3, 0), [condition("={{ $json.anomalies_count }}", "number", "equals", 0)]
    )
    ask = set_node(
        wf,
        "Préparer la demande de validation",
        (4, -0.5),
        [
            ("sujet", "=[FACTURE] Valider l'extraction {{ $json.invoice_ref }} ({{ $json.supplier_id }})", "string"),
            (
                "texte",
                "=Lignes extraites (quantité × unité de vente, coût facturé et coût rendu par unité) :\n{{ $json.resume }}\n"
                "Total marchandise : {{ $json.goods_total_chf }} CHF. Frais : {{ $json.fees_resume }}.\n"
                "Vérifier au PDF les QUANTITÉS (unités, jamais des cartons) et les montants, puis répondre : "
                "{{ $execution.resumeFormUrl }}\n"
                "INTERNE — contient coûts et marges : ne jamais transférer ni publier.",
                "string",
            ),
        ],
    )
    mail = email(wf, "Demander la validation de l’extraction (email, désactivé)", (5, -0.5))
    wait = wait_form(
        wf,
        "Validation humaine de l’extraction (formulaire, 72 h)",
        (6, -0.5),
        title="Validation d'une facture fournisseur",
        description="=Facture {{ $('Contrôles déterministes (centimes)').first().json.invoice_ref }} : les quantités "
        "(unités de vente) et les montants extraits correspondent-ils au justificatif ? (aucune commande client ne sera "
        "modifiée)\n{{ $('Contrôles déterministes (centimes)').first().json.resume }}\n"
        "Frais : {{ $('Contrôles déterministes (centimes)').first().json.fees_resume }}",
        choices=("Conforme au justificatif", "Non conforme"),
        hours=72,
    )
    valid = if_node(
        wf,
        "Extraction validée ?",
        (7, -0.5),
        [condition("={{ $json['Décision'] }}", "string", "equals", "Conforme au justificatif")],
    )
    prepare = code_node(
        wf,
        "Préparer la facture validée (coût rendu ventilé)",
        (7.5, -1),
        JS_INVOICE_FOR_ENGINE,
        notes="Lignes au coût rendu unitaire (fret et douane ventilés au prorata de la valeur), TVA d'import ventilée à "
        "part (le moteur la compte selon son profil TVA) ; total dû = marchandise + frais ; date d'émission jamais future.",
    )
    record = engine(
        wf,
        "Enregistrer la facture validée (POST /costs/invoices)",
        "POST",
        "/costs/invoices",
        (8, -1),
        body="$json",
        notes="Registre des factures du moteur (revue R4) : référence du coût d'une réception (± 2 %, sinon propriétaire) "
        "et dette de la photo du stop-loss jusqu'au paiement relevé par connecteur-tresorerie. Jeton nommé "
        "n8n-03-factures, jamais l'agent 05 qui valorise les réceptions. Idempotente par facture (autre contenu : 409).",
    )
    gap = if_node(
        wf,
        "Écart > 2 % ?",
        (9, -1),
        [condition("={{ $('Contrôles déterministes (centimes)').first().json.flagged_count }}", "number", "gt", 0)],
    )
    gap_msg = set_node(
        wf,
        "Préparer le signalement d’écart",
        (10, -1.5),
        [
            (
                "sujet",
                "=[ÉCART DE COÛT] {{ $('Contrôles déterministes (centimes)').first().json.invoice_ref }}",
                "string",
            ),
            (
                "texte",
                "=Écarts facture / estimation :\n{{ $('Contrôles déterministes (centimes)').first().json.resume }}\n"
                "À expliquer dans la revue hebdomadaire ; répercuter sur le coût de remplacement et la décision de prix.",
                "string",
            ),
        ],
    )
    gap_mail = email(wf, "Signaler les écarts (email, désactivé)", (11, -1.5))
    up_to_date = noop(wf, "Journal : coût historique à jour", (10, -0.4))
    refused = engine(
        wf,
        "Extraction refusée : incident",
        "POST",
        "/incidents",
        (8, 0.2),
        body=(
            "{ cause: 'Facture ' + $('Contrôles déterministes (centimes)').first().json.invoice_ref + ' jugée non conforme : ' "
            "+ ($json['Motif'] || 'sans réponse sous 72 h'), kind: 'FACTURE_NON_CONFORME', severity: 'MAJEUR', scope: 'WORKFLOW', "
            "workflow: '03-facture:' + $('Contrôles déterministes (centimes)').first().json.invoice_ref, "
            "proposed_action: 'Corriger l’extraction ou demander une facture rectificative ; aucun coût enregistré.', "
            "actor: 'n8n:03-facture-marge', simulation: $('Paramètres').first().json.simulation }"
        ),
    )
    anomaly_inc = engine(
        wf,
        "Ouvrir un incident facture",
        "POST",
        "/incidents",
        (4, 0.7),
        body=(
            "{ cause: 'Facture ' + ($json.invoice_ref || '?') + ' : ' + $json.anomalies.join(' ; '), kind: 'FACTURE_ANOMALIE', "
            "severity: 'MAJEUR', scope: 'WORKFLOW', workflow: '03-facture:' + ($json.invoice_ref || 'inconnue'), "
            "proposed_action: 'Reprendre l’extraction (unités, total, devise et taux sourcé) puis renvoyer.', "
            "actor: 'n8n:03-facture-marge', simulation: $('Paramètres').first().json.simulation, details: { anomalies: $json.anomalies } }"
        ),
    )
    wf.chain(hook, p, checks, coherent)
    wf.link(coherent, ask, 0)
    wf.link(coherent, anomaly_inc, 1)
    wf.chain(ask, mail, wait, valid)
    wf.link(valid, prepare, 0)
    wf.link(prepare, record)
    wf.link(valid, refused, 1)
    wf.link(record, gap)
    wf.link(gap, gap_msg, 0)
    wf.link(gap, up_to_date, 1)
    wf.link(gap_msg, gap_mail)
    return wf


def wf04(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Incident (BP §12) : notification cause + action, reprise après validation, échecs d'exécution (Error Trigger)."""
    wf = Workflow(
        WORKFLOW_IDS["04"], WORKFLOW_NAMES["04"], "04_incident.json", error_workflow=False, credentials_map=cmap
    )
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.4),
        """
## 04 — Incident (BP §12, SOP_INCIDENTS.md)
Le moteur met en **quarantaine** la référence ou **suspend** le workflow, puis notifie ce webhook (cause + action proposée),
avec son **secret dédié** (en-tête `X-Pokeshop-Notify`, credential « Notification moteur → 04 ») : sans lui, 403.
S1 : alerte immédiate ; S2 : dans l'heure ; S3/INFO : digest. **Reprise** : test enregistré → validation par formulaire
→ `POST /incidents/{id}/resume`. Un **S1** ne se reprend que par la propriétaire (son jeton, depuis son terminal).
**Workflow d'erreur** de tous les autres workflows : toute exécution en échec ouvre un incident.
**Activation** : en PREMIER, dès le niveau 1.
**Validation humaine requise** : canal d'alerte S1 (SMS, notification, appel), reprise de chaque S1.
""",
        width=640,
        height=380,
    )
    hook = webhook(
        wf,
        "Notification d’incident du moteur",
        (0, 0),
        "pokeshop-incidents",
        gateway=ENGINE_NOTIFY_CREDENTIAL,
        notes="Appelé par le moteur (POKESHOP_N8N_WEBHOOK_URL=http://n8n:5678/webhook/pokeshop-incidents) avec l'en-tête "
        "X-Pokeshop-Notify = POKESHOP_N8N_WEBHOOK_SECRET (revue R6) : joignable depuis le réseau du compose et la boucle "
        "locale de l'hôte (127.0.0.1:5678), toute requête sans ce secret est refusée (403).",
    )
    pa = params_node(wf, "Paramètres — incidents", (1, 0), WORKFLOW_KEYS["04"])
    valid = if_node(
        wf,
        "Charge valide ?",
        (2, 0),
        [
            condition("={{ $json.body.incident_id }}", "string", "notEmpty"),
            condition("={{ $json.body.sop }}", "string", "notEmpty"),
        ],
    )
    ignored = noop(wf, "Charge invalide : ignorée", (3, 0.8))
    msg = set_node(
        wf,
        "Composer la notification (SOP §4)",
        (3, -0.2),
        [
            ("sop", "={{ $json.body.sop }}", "string"),
            (
                "sujet",
                "=[INCIDENT {{ $json.body.sop }}] {{ $json.body.code || '' }} — {{ $json.body.title }}",
                "string",
            ),
            (
                "texte",
                "={{ $json.body.text }}\n\nReprise : corriger, tester (POST /incidents/{{ $json.body.incident_id }}/test), "
                "puis valider la reprise. Un S1 ne se reprend que par la propriétaire.\n"
                "INTERNE — ne jamais transférer ni publier.",
                "string",
            ),
        ],
    )
    gravity = switch_node(wf, "Gravité", (4, -0.2), "={{ $json.sop }}", ("S1", "S2"), "S3 et INFO : digest")
    s1_mail = email(wf, "Alerte immédiate S1 (email, désactivé)", (5, -1), params="Paramètres — incidents")
    s1_slack = slack(wf, "Alerte immédiate S1 (Slack, désactivé)", (5, -0.4))
    s2_mail = email(wf, "Notification S2 dans l’heure (email, désactivé)", (5, 0.2), params="Paramètres — incidents")
    digest = noop(wf, "Reporté au digest quotidien", (5, 0.8))
    wf.chain(hook, pa, valid)
    wf.link(valid, msg, 0)
    wf.link(valid, ignored, 1)
    wf.link(msg, gravity)
    wf.link(gravity, s1_mail, 0)
    wf.link(gravity, s1_slack, 0)
    wf.link(gravity, s2_mail, 1)
    wf.link(gravity, digest, 2)
    # Reprise après validation.
    rh = webhook(
        wf,
        "Demande de reprise (passerelle agents)",
        (0, 2.2),
        "pokeshop-incident-reprise",
        gateway="gateway_04",
        notes='Secret remis au seul agent 12. Corps : {"incident_id": "..."}. Le test réussi est enregistré AVANT, par '
        "le rôle qa-conformite avec SON jeton nommé (POST /incidents/{id}/test, différent de l'ouvreur, cycle réel "
        "lancé par un autre principal) ou par la propriétaire : le workflow 04 (n8n-04-incidents) ne peut pas "
        "l'attester (403, revue NEW-01) ; il ne fait que reprendre.",
    )
    pb = params_node(wf, "Paramètres — reprise", (1, 2.2), WORKFLOW_KEYS["04"])
    body_ref = f"{ref('Demande de reprise (passerelle agents)')}.first().json.body"
    read = engine(
        wf,
        "Lire le test enregistré (GET /incidents)",
        "GET",
        "/incidents?open_only=true",
        (2, 2.2),
        params="Paramètres — reprise",
        notes="Lecture seule : le test de correction est enregistré par l'agent 12 QA (jeton nommé) ou la propriétaire.",
    )
    test = code_node(wf, "Retrouver l’incident et son test", (2.5, 2.2), JS_FIND_INCIDENT)
    passed = if_node(wf, "Test réussi ?", (3, 2.2), [condition("={{ $json.incident.test_passed }}", "boolean", "true")])
    fail_msg = set_node(
        wf,
        "Préparer l’avis d’échec du test",
        (4, 3),
        [
            ("sujet", "=[INCIDENT] Test en échec : {{ $json.incident.incident_id }}", "string"),
            (
                "texte",
                "=Aucun test réussi enregistré pour {{ $json.incident.incident_id }} (test {{ $json.incident.test_ref || 'absent' }}) : "
                "confinement maintenu. L'agent 12 QA enregistre le test avec SON jeton nommé (POST /incidents/{id}/test, "
                "cycle /sync/run PROPRE sur la référence), ou la propriétaire l'atteste.",
                "string",
            ),
        ],
    )
    fail_mail = email(wf, "Test en échec : notification (email, désactivé)", (5, 3), params="Paramètres — reprise")
    ask = set_node(
        wf,
        "Préparer la demande de reprise",
        (4, 1.8),
        [
            (
                "sujet",
                "=[REPRISE] Valider la reprise de {{ $json.incident.incident_id }} ({{ $json.incident.title }})",
                "string",
            ),
            (
                "texte",
                "=Cause : {{ $json.incident.cause }}\nTest : {{ $json.incident.test_ref }} réussi.\n"
                "Décider la reprise : {{ $execution.resumeFormUrl }}",
                "string",
            ),
        ],
    )
    ask_mail = email(
        wf, "Demander la validation de reprise (email, désactivé)", (5, 1.8), params="Paramètres — reprise"
    )
    wait = wait_form(
        wf,
        "Validation de la reprise (formulaire, 48 h)",
        (6, 1.8),
        title="Reprise après incident",
        description="=Incident {{ $('Retrouver l’incident et son test').first().json.incident.incident_id }} : "
        "test réussi. Reprendre depuis le dernier état vérifié ?",
        choices=("Reprendre", "Maintenir le confinement"),
        hours=48,
    )
    approved = if_node(
        wf, "Reprise validée ?", (7, 1.8), [condition("={{ $json['Décision'] }}", "string", "equals", "Reprendre")]
    )
    resume = engine(
        wf,
        "Reprendre (POST /incidents/{id}/resume)",
        "POST",
        f"/incidents/{{{{ {body_ref}.incident_id }}}}/resume",
        (8, 1.4),
        params="Paramètres — reprise",
        body=f"{{ actor: {body_ref}.actor }}",
        on_error="continueErrorOutput",
        notes="Sans jeton propriétaire : un incident S1 est refusé (erreur => instructions à la propriétaire).",
    )
    resumed = noop(wf, "Journal : reprise effectuée", (9, 1))
    s1_msg = set_node(
        wf,
        "Préparer les instructions S1 (propriétaire)",
        (9, 1.8),
        [
            (
                "sujet",
                "=[S1] Reprise réservée à la propriétaire : {{ $('Demande de reprise (passerelle agents)').first().json.body.incident_id }}",
                "string",
            ),
            (
                "texte",
                "=Depuis votre terminal : POST /incidents/<id>/resume avec X-Pokeshop-Token et X-Pokeshop-Owner-Token "
                '(votre jeton, jamais transmis à un agent), corps {"actor": "propriétaire"}.',
                "string",
            ),
        ],
    )
    s1_mail2 = email(
        wf, "Reprise S1 : instructions à la propriétaire (email, désactivé)", (10, 1.8), params="Paramètres — reprise"
    )
    kept = noop(wf, "Reprise refusée : confinement maintenu", (8, 2.4))
    wf.chain(rh, pb, read, test, passed)
    wf.link(passed, ask, 0)
    wf.link(passed, fail_msg, 1)
    wf.link(fail_msg, fail_mail)
    wf.chain(ask, ask_mail, wait, approved)
    wf.link(approved, resume, 0)
    wf.link(approved, kept, 1)
    wf.link(resume, resumed, 0)
    wf.link(resume, s1_msg, 1)
    wf.link(s1_msg, s1_mail2)
    # Erreurs d'exécution de tous les workflows.
    et = wf.add("Échec d’exécution d’un workflow", "n8n-nodes-base.errorTrigger", 1, {}, (0, 4.2))
    pc = params_node(wf, "Paramètres — erreurs", (1, 4.2), WORKFLOW_KEYS["04"])
    err = f"{ref('Échec d’exécution d’un workflow')}.first().json"
    # Clé canonique du workflow en échec (connue au build : identifiant puis nom affiché) => la suspension
    # posée par l'incident arrête bien ce workflow (garde « Workflow suspendu ? ») et, pour 08, le moteur.
    by_id = json.dumps({WORKFLOW_IDS[k]: WORKFLOW_KEYS[k] for k in WORKFLOW_IDS}, ensure_ascii=False)
    by_name = json.dumps({WORKFLOW_NAMES[k]: WORKFLOW_KEYS[k] for k in WORKFLOW_NAMES}, ensure_ascii=False)
    failed_key = (
        f"({by_id})[({err}.workflow || {{}}).id] || ({by_name})[({err}.workflow || {{}}).name] "
        f"|| ({err}.workflow || {{}}).name || 'inconnu'"
    )
    inc = engine(
        wf,
        "Ouvrir un incident d’exécution",
        "POST",
        "/incidents",
        (2, 4.2),
        params="Paramètres — erreurs",
        body=(
            f"{{ cause: 'Exécution ' + ({err}.execution.id || '?') + ' en échec au nœud ' + ({err}.execution.lastNodeExecuted || '?') "
            f"+ ' : ' + (({err}.execution.error || {{}}).message || 'erreur inconnue'), kind: 'WORKFLOW_EN_ECHEC', "
            f"severity: 'MAJEUR', scope: 'WORKFLOW', workflow: {failed_key}, "
            "proposed_action: 'Corriger puis relancer depuis la file de reprise avec les mêmes clés d’idempotence ; "
            "vérifier l’état réel sur le site.', actor: 'n8n:04-incident', "
            f"simulation: {ref('Paramètres — erreurs')}.first().json.simulation, "
            f"details: {{ execution_url: {err}.execution.url || null }} }}"
        ),
        on_error="continueErrorOutput",
    )
    opened = noop(wf, "Journal : incident ouvert (notifié par le moteur)", (3, 3.8))
    down_msg = set_node(
        wf,
        "Préparer l’alerte moteur injoignable",
        (3, 4.6),
        [
            (
                "sujet",
                "=[CRITIQUE] Moteur injoignable pendant un échec de {{ ($('Échec d’exécution d’un workflow').first().json.workflow || {}).name }}",
                "string",
            ),
            (
                "texte",
                "=L'API du moteur ne répond pas : aucune écriture ne doit reprendre avant vérification (BP §6 « arrêt des écritures »).",
                "string",
            ),
        ],
    )
    down_mail = email(wf, "Alerte : moteur injoignable (email, désactivé)", (4, 4.6), params="Paramètres — erreurs")
    wf.chain(et, pc, inc)
    wf.link(inc, opened, 0)
    wf.link(inc, down_msg, 1)
    wf.link(down_msg, down_mail)
    return wf


def wf05(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Digest quotidien (ROUTINES_PILOTAGE §3.2) : étoile polaire puis stop-loss en tête, KPI du jour, décisions."""
    wf = Workflow(WORKFLOW_IDS["05"], WORKFLOW_NAMES["05"], "05_digest_quotidien.json", credentials_map=cmap)
    sticky(
        wf,
        "Note — à lire",
        (-1, -2),
        """
## 05 — Digest quotidien (BP §12, ROUTINES_PILOTAGE.md §3.2)
Chaque matin : **1. étoile polaire** (`GET /northstar` : contribution nette cumulée, delta de la semaine),
**2. état du stop-loss** (`GET /stoploss/status`), puis ventes payées, contribution, cash, commandes à préparer,
ruptures, offres périmées, incidents et **décisions attendues** (`GET /dashboard/daily`).
Lecture seule. **INTERNE** : contient coûts et marges.
**Activation** : niveau 1 (envoi à la seule responsable).
**Validation humaine requise** : heure du digest (HEURE_DIGEST, ici 07:45) et canal.
""",
        width=640,
        height=320,
    )
    t = cron(wf, "Chaque jour 07:45 — digest", (0, 0), "45 7 * * *")
    p = params_node(wf, "Paramètres", (1, 0), WORKFLOW_KEYS["05"])
    ns = engine(wf, "Étoile polaire (GET /northstar)", "GET", "/northstar", (2, 0))
    sl = engine(wf, "État du stop-loss (GET /stoploss/status)", "GET", "/stoploss/status", (3, 0))
    db = engine(wf, "Tableau de bord du jour (GET /dashboard/daily)", "GET", "/dashboard/daily", (4, 0))
    hist = engine(wf, "Cycles de synchronisation (GET /sync/history)", "GET", "/sync/history?limit=5", (5, 0))
    health = engine(wf, "État du moteur (GET /health)", "GET", "/health", (6, 0))
    cmp = code_node(wf, "Composer le digest (étoile polaire en premier)", (7, 0), JS_DIGEST)
    mail = email(wf, "Envoyer le digest à la responsable (email, désactivé)", (8, -0.4))
    sk = slack(wf, "Envoyer le digest (Slack, désactivé)", (8, 0.4))
    wf.chain(t, p, ns, sl, db, hist, health, cmp, mail)
    wf.link(cmp, sk)
    return wf


def wf06(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Automatisations marketing (BP §9) avec garde-fous ; liens publics des emails traités avant toute confirmation."""
    wf = Workflow(
        WORKFLOW_IDS["06"],
        WORKFLOW_NAMES["06"],
        "06_marketing_automations.json",
        keep_success_data=False,
        credentials_map=cmap,
    )
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.8),
        """
## 06 — Automatisations marketing (BP §9, docs/06-contenu/EMAILS)
- **Réception contrôlée** (passerelle de l'agent 11 seul, son secret) → `POST /stock/receive` (stock local réel), puis alerte « nouveau stock local » aux inscrits
  **consentants** (email 04). **Garde-fous** : incident ouvert sur « marketing », stock vendable < seuil, référence sous
  stop-loss produit (marge insuffisante), gel global ou stop-loss non évaluable.
- **Commande expédiée** → suivi (email 07 envoyé par Shopify ; alerte si aucun numéro de suivi).
- **Livraison** → demande d'avis (email 11) **7 jours** après (hypothèse), une seule, sans réclamation ni opposition.
- **Liens des emails** (jeton) : désinscription `alertes-desinscrire`, refus d'avis `avis-refus`, préférences
  `alertes-preferences`, confirmation `alertes-confirmer`. La page de confirmation ne s'affiche **qu'après** les appels
  aux outils ; lien invalide = page d'erreur honnête ; retrait non confirmé par un outil = incident (traitement manuel
  sans délai, envois marketing suspendus jusqu'à la reprise).
Aucun prix ni donnée interne dans un email : titre, statut et prix lus sur la page publique au moment de l'envoi.
**Activation** : liens des emails AVANT tout envoi ; envois au niveau 3. Pas de SMS ni d'email non sollicité.
**Validation humaine requise** : outil d'emailing (B04), seuil de stock d'alerte, délai d'avis, notes juristes C2-C4.
""",
        width=720,
        height=480,
    )
    # A. Réception contrôlée -> stock local -> alerte.
    hook = webhook(
        wf,
        "Réception contrôlée (passerelle agent 11)",
        (0, 0),
        "pokeshop-stock-recu",
        gateway="gateway_06",
        notes='Secret remis au SEUL agent 11 (credential « Passerelle 06 réception ») : aucun autre agent ne peut '
        'déclarer une réception au nom d\'operations-sav (revue R4, R2-NEW-01). Corps : {"product_key", "sku", "qty", '
        '"ref" (bon de livraison), "public_title", "public_url", "format_preference"} — aucun prix.',
    )
    pa = params_node(wf, "Paramètres — alertes stock", (1, 0), WORKFLOW_KEYS["06"], ("seuil_stock_alerte", 3, "number"))
    body = f"{ref('Réception contrôlée (passerelle agent 11)')}.first().json.body"
    receive = engine(
        wf,
        "Enregistrer la réception (POST /stock/receive)",
        "POST",
        "/stock/receive",
        (2, 0),
        params="Paramètres — alertes stock",
        body=f"{{ sku: {body}.sku, qty: {body}.qty, ref: {body}.ref }}",
        notes="Registre du stock local (idempotent par SKU + bon de livraison) : sans lui, la fiche reste en rupture. "
        "Jeton nommé operations-sav (agent 11), jamais le jeton commun (SOP_RECEPTION_STOCK E2).",
        cred="api_stock",
    )
    read_a, guard_a = suspension_guard(wf, 3, 0.8, params="Paramètres — alertes stock", suffix=" (alertes stock)")
    held_a = noop(wf, "Alertes suspendues (incident ouvert)", (5, 1.4))
    guard = engine(
        wf, "Garde : état du stop-loss", "GET", "/stoploss/status", (3, 0), params="Paramètres — alertes stock"
    )
    stock = engine(
        wf,
        "Stock vendable local",
        "POST",
        "/stock/sellable",
        (4, 0),
        params="Paramètres — alertes stock",
        body=f"{{ sku: {body}.sku }}",
    )
    sl = f"{ref('Garde : état du stop-loss')}.first().json"
    rails = if_node(
        wf,
        "Garde-fous campagne (stock, marge, gel)",
        (5, 0),
        [
            condition(f"={{{{ {sl}.available }}}}", "boolean", "true"),
            condition(f"={{{{ {sl}.global_frozen }}}}", "boolean", "false"),
            condition(
                f"={{{{ ({sl}.status || {{}}).blocked_products || [] }}}}",
                "array",
                "notContains",
                f"={{{{ {body}.product_key }}}}",
            ),
            condition(
                "={{ $json.sellable }}",
                "number",
                "gte",
                f"={{{{ {ref('Paramètres — alertes stock')}.first().json.seuil_stock_alerte }}}}",
            ),
        ],
        notes="Une campagne s'arrête si le stock passe sous le seuil ou si la marge est insuffisante (BP §9).",
    )
    stopped = set_node(
        wf,
        "Campagne stoppée (motif)",
        (6, 0.7),
        [
            (
                "motif",
                f"={{{{ !{sl}.available ? 'stop-loss non évaluable' : {sl}.global_frozen ? 'gel global' : "
                f"(({sl}.status || {{}}).blocked_products || []).includes({body}.product_key) ? 'marge insuffisante (stop-loss produit)' "
                ": 'stock vendable sous le seuil' }}",
                "string",
            ),
        ],
    )
    stopped_log = noop(wf, "Journal : alerte non envoyée", (7, 0.7))
    subs = external(
        wf,
        "Lire les inscrits consentants — outil d’emailing (désactivé)",
        "GET",
        f"{EMAILING_PLACEHOLDER}/subscribers?status=confirme",
        (6, -0.4),
        "emailing",
        notes="Outil d'emailing à choisir (B04) ; lecture des inscrits confirmés seulement.",
    )
    filt = code_node(wf, "Filtrer : consentement confirmé et préférence", (7, -0.4), JS_SUBSCRIBERS)
    one = dedupe(
        wf, "Une alerte par produit et par personne", (8, -0.4), "={{ $json.product_key }}|{{ $json.subscriber_id }}"
    )
    comp = set_node(
        wf,
        "Composer l’email 04 (alerte stock local)",
        (9, -0.4),
        [
            ("modele", "04-alerte-stock-local", "string"),
            ("produit_titre", "={{ $json.public_title }}", "string"),
            ("url_produit", "={{ $json.public_url }}", "string"),
        ],
    )
    send04 = external(
        wf,
        "Envoyer l’email 04 — outil d’emailing (désactivé)",
        "POST",
        f"{EMAILING_PLACEHOLDER}/send",
        (10, -0.4),
        "emailing",
        body="{ template: $json.modele, subscriber_id: $json.subscriber_id, variables: { produit_titre: $json.produit_titre, url_produit: $json.url_produit } }",
        notes="Niveau 3 seulement. Prix et statut relus sur la page publique au moment de l'envoi (EMAILS §4).",
    )
    wf.chain(hook, pa, receive, read_a)
    wf.link(guard_a, held_a, 0)
    wf.link(guard_a, guard, 1)
    wf.chain(guard, stock, rails)
    wf.link(rails, subs, 0)
    wf.link(rails, stopped, 1)
    wf.link(stopped, stopped_log)
    wf.chain(subs, filt, one, comp, send04)
    # B. Commande expédiée -> suivi.
    shipped = shopify_trigger(wf, "Shopify : commande expédiée (orders/fulfilled)", (0, 2), "orders/fulfilled")
    tracking = if_node(
        wf,
        "Numéro de suivi présent ?",
        (1, 2),
        [
            condition(
                "={{ ($json.fulfillments || []).some(f => (f.tracking_numbers || []).length > 0) }}", "boolean", "true"
            )
        ],
    )
    tracked = noop(wf, "Suivi envoyé au client par Shopify (email 07)", (2, 1.6))
    pt = params_node(wf, "Paramètres — suivi", (2, 2.4), WORKFLOW_KEYS["06"])
    no_track = set_node(
        wf,
        "Préparer l’alerte sans suivi",
        (3, 2.4),
        [
            (
                "sujet",
                f"=[SUIVI] Commande {{{{ {ref('Shopify : commande expédiée (orders/fulfilled)')}.first().json.name }}}} expédiée sans numéro de suivi",
                "string",
            ),
            ("texte", "=Ajouter le numéro de suivi dans Shopify (le client reçoit alors l'email 07).", "string"),
        ],
    )
    no_track_mail = email(
        wf, "Alerte : expédition sans numéro de suivi (email, désactivé)", (4, 2.4), params="Paramètres — suivi"
    )
    wf.chain(shipped, tracking)
    wf.link(tracking, tracked, 0)
    wf.link(tracking, pt, 1)
    wf.chain(pt, no_track, no_track_mail)
    # C. Livraison -> demande d'avis.
    delivered = shopify_trigger(
        wf, "Shopify : événement de livraison (fulfillment_events/create)", (0, 3.4), "fulfillment_events/create"
    )
    is_delivered = if_node(wf, "Livré ?", (1, 3.4), [condition("={{ $json.status }}", "string", "equals", "delivered")])
    once = dedupe(wf, "Une seule demande par commande", (2, 3.4), "={{ $json.order_id }}")
    wait7 = wf.add(
        "Attendre 7 jours après livraison (hypothèse)",
        "n8n-nodes-base.wait",
        1.1,
        {"resume": "timeInterval", "amount": 7, "unit": "days"},
        (3, 3.4),
        webhook=True,
    )
    pd = params_node(wf, "Paramètres — avis", (4, 3.4), WORKFLOW_KEYS["06"])
    read_c, guard_c = suspension_guard(wf, 5, 4.2, params="Paramètres — avis", suffix=" (avis)")
    held_c = noop(wf, "Avis suspendus (incident ouvert)", (7, 4.6))
    guard2 = engine(wf, "Garde : gel global (avis)", "GET", "/stoploss/status", (5, 3.4), params="Paramètres — avis")
    allowed = if_node(
        wf,
        "Envoi autorisé ?",
        (6, 3.4),
        [
            condition("={{ $json.available }}", "boolean", "true"),
            condition("={{ $json.global_frozen }}", "boolean", "false"),
        ],
    )
    order = external(
        wf,
        "Lire la commande : réclamation ou opposition ? — Shopify (désactivé)",
        "POST",
        SHOPIFY_GRAPHQL_PLACEHOLDER,
        (7, 3.2),
        "shopify",
        predefined=True,
        body=f"{{ query: 'query($id: ID!) {{ order(id: $id) {{ name tags customer {{ id }} }} }}', variables: {{ id: 'gid://shopify/Order/' + {ref('Une seule demande par commande')}.first().json.order_id }} }}",
        notes="Lecture seule. L'opposition (case au checkout, note C3 du juriste) est portée par une étiquette « avis-refus ».",
    )
    elig = code_node(wf, "Éligible à la demande d’avis ?", (8, 3.2), JS_REVIEW_ELIGIBILITY)
    comp11 = set_node(
        wf,
        "Composer l’email 11 (demande d’avis)",
        (9, 3.2),
        [
            ("modele", "11-demande-avis", "string"),
            ("numero_commande", "={{ $json.order_name }}", "string"),
        ],
    )
    send11 = external(
        wf,
        "Envoyer l’email 11 — outil d’emailing (désactivé)",
        "POST",
        "https://REMPLACER-outil-emailing.exemple.invalid/api/send",
        (10, 3.2),
        "emailing",
        body="{ template: $json.modele, shopify_customer_id: $json.customer_id, variables: { numero_commande: $json.numero_commande } }",
        notes="Un seul email, avec lien de refus (note C3 du juriste à obtenir avant activation).",
    )
    frozen_log = noop(wf, "Journal : avis non envoyé (gel ou stop-loss indisponible)", (7, 4))
    wf.chain(delivered, is_delivered)
    wf.link(is_delivered, once, 0)
    wf.chain(once, wait7, pd, read_c)
    wf.link(guard_c, held_c, 0)
    wf.link(guard_c, guard2, 1)
    wf.link(guard2, allowed)
    wf.link(allowed, order, 0)
    wf.link(allowed, frozen_log, 1)
    wf.chain(order, elig, comp11, send11)
    # D. Désinscription (lien des emails) : confirmation APRÈS les retraits, jamais avant (CON-05).
    _optout_flow(
        wf,
        row=5.4,
        path="alertes-desinscrire",
        label="désinscription",
        params_name="Paramètres — désinscription",
        emailing_name="Désinscrire dans l’outil d’emailing (désactivé)",
        emailing_url=f"{EMAILING_PLACEHOLDER}/unsubscribe",
        emailing_ok_field="unsubscribed",
        shopify_name="Retirer le consentement marketing dans Shopify (désactivé)",
        shopify_body="{ query: 'mutation($input: CustomerEmailMarketingConsentUpdateInput!) { customerEmailMarketingConsentUpdate(input: $input) { userErrors { field message } } }', variables: { input: { customerId: 'gid://shopify/Customer/' + $json.shopify_customer_id, emailMarketingConsent: { marketingState: 'UNSUBSCRIBED' } } } }",
        shopify_mutation="customerEmailMarketingConsentUpdate",
        success_page_redirect=f"{LANDING_PLACEHOLDER}/desinscription.html",
        success_html=None,
        invalid_html=html_page(
            "Lien de désinscription invalide",
            "Votre lien de désinscription est incomplet ou invalide : nous n'avons pas pu identifier votre adresse, "
            "et votre désinscription n'est <strong>pas</strong> enregistrée.",
            f"Pour vous désinscrire, répondez « STOP » à l'email reçu ou écrivez à {SUPPORT_EMAIL_PLACEHOLDER} : "
            "nous vous retirons à la main de tous nos outils et vous le confirmons par écrit.",
        ),
        kind="DESINSCRIPTION",
        cause_unconfirmed="Désinscription non confirmée par tous les outils",
        cause_invalid="Lien de désinscription invalide ou incomplet (jeton absent ou mal formé)",
        action="Retirer à la main la personne de chaque outil (emailing, Shopify) sans délai et vérifier qu’aucun envoi "
        "ne part ; les envois marketing restent suspendus jusqu’à la reprise.",
    )
    # Consentement retiré directement dans Shopify -> outil d'emailing.
    cust = shopify_trigger(wf, "Shopify : client mis à jour (customers/update)", (0, 8.2), "customers/update")
    is_unsub = if_node(
        wf,
        "Désinscrit dans Shopify ?",
        (1, 8.2),
        [condition("={{ ($json.email_marketing_consent || {}).state }}", "string", "equals", "unsubscribed")],
    )
    ps = params_node(wf, "Paramètres — désinscription Shopify", (2, 8), WORKFLOW_KEYS["06"])
    norm_s = code_node(wf, "Normaliser la désinscription Shopify", (3, 8), JS_SHOPIFY_UNSUBSCRIBE)
    u1s = external(
        wf,
        "Désinscrire dans l’outil d’emailing — depuis Shopify (désactivé)",
        "POST",
        f"{EMAILING_PLACEHOLDER}/unsubscribe",
        (4, 8),
        "emailing",
        body="{ shopify_customer_id: $json.shopify_customer_id, source: 'shopify' }",
        notes="Réponse attendue de l'outil : { unsubscribed: true } (contrat à adapter à l'outil retenu, B04).",
        on_error="continueErrorOutput",
    )
    bilan_s = code_node(wf, "Bilan du retrait (origine Shopify)", (5, 8), JS_SHOPIFY_UNSUBSCRIBE_BILAN)
    ok_s = if_node(
        wf, "Retrait confirmé (origine Shopify) ?", (6, 8), [condition("={{ $json.tous_confirmes }}", "boolean", "true")]
    )
    done_s = noop(wf, "Journal de désinscription Shopify (sans adresse)", (7, 7.6))
    inc_s = _optout_incident(
        wf, "Incident : retrait Shopify non propagé", (7, 8.4), "Paramètres — désinscription Shopify",
        "DESINSCRIPTION_NON_CONFIRME", "Désinscription Shopify non propagée à l’outil d’emailing",
        "Retirer à la main la personne de l’outil d’emailing sans délai ; envois marketing suspendus jusqu’à la reprise.",
    )  # fmt: skip
    after_s = noop(wf, "Journal : retrait manuel demandé", (8, 8.4))
    wf.chain(cust, is_unsub)
    wf.link(is_unsub, ps, 0)
    wf.chain(ps, norm_s, u1s)
    wf.link(u1s, bilan_s, 0)
    wf.link(u1s, bilan_s, 1)
    wf.chain(bilan_s, ok_s)
    wf.link(ok_s, done_s, 0)
    wf.link(ok_s, inc_s, 1)
    wf.link(inc_s, after_s, 0)
    wf.link(inc_s, after_s, 1)
    # E. Refus des demandes d'avis (email 11, note C3).
    _optout_flow(
        wf,
        row=9.6,
        path="avis-refus",
        label="refus d’avis",
        params_name="Paramètres — refus d’avis",
        emailing_name="Enregistrer le refus d’avis — outil d’emailing (désactivé)",
        emailing_url=f"{EMAILING_PLACEHOLDER}/review-opt-out",
        emailing_ok_field="opted_out",
        shopify_name="Poser l’étiquette avis-refus — Shopify (désactivé)",
        shopify_body="{ query: 'mutation($id: ID!, $tags: [String!]!) { tagsAdd(id: $id, tags: $tags) { userErrors { field message } } }', variables: { id: 'gid://shopify/Customer/' + $json.shopify_customer_id, tags: ['avis-refus'] } }",
        shopify_mutation="tagsAdd",
        success_page_redirect=None,
        success_html=html_page(
            "Demande reçue",
            "Nous avons bien reçu votre demande : elle a été transmise à nos outils et vous ne recevrez plus de "
            "demande d'avis.",
            "Si un outil n'a pas confirmé, nous le faisons à la main sans délai. Vous en recevez encore une ? "
            f"Écrivez-nous à {SUPPORT_EMAIL_PLACEHOLDER}.",
        ),
        invalid_html=html_page(
            "Lien invalide",
            "Votre lien est incomplet ou invalide : nous n'avons pas pu identifier votre demande, et elle n'est "
            "<strong>pas</strong> enregistrée.",
            f"Pour ne plus recevoir de demande d'avis, écrivez à {SUPPORT_EMAIL_PLACEHOLDER} : nous l'enregistrons à la "
            "main et vous le confirmons.",
        ),
        kind="REFUS_AVIS",
        cause_unconfirmed="Refus des demandes d’avis non confirmé par tous les outils",
        cause_invalid="Lien de refus des demandes d’avis invalide ou incomplet (jeton absent ou mal formé)",
        action="Enregistrer à la main l’opposition (étiquette avis-refus du client Shopify, outil d’emailing) sans "
        "délai ; aucune demande d’avis à cette personne.",
    )
    # F. Préférences (emails 02 à 05, 12, 13).
    hp = webhook(
        wf,
        "Lien des préférences (emails)",
        (0, 12.4),
        "alertes-preferences",
        method="GET",
        auth="none",
        response_mode="responseNode",
        notes="Jeton unique par lien ; page de préférences de l'outil d'emailing, sinon page honnête.",
    )
    pp = params_node(wf, "Paramètres — préférences", (1, 12.4), WORKFLOW_KEYS["06"])
    np = code_node(wf, "Normaliser le lien de préférences", (2, 12.4), JS_LINK_TOKEN)
    vp = if_node(wf, "Lien de préférences valide ?", (3, 12.4), [condition("={{ $json.valide }}", "boolean", "true")])
    bad_p = respond_html(
        wf,
        "Répondre : lien de préférences invalide",
        (4, 13),
        html_page(
            "Lien invalide",
            "Votre lien de préférences est incomplet ou invalide.",
            "Pour ne plus rien recevoir, utilisez le lien « se désinscrire » de l'email ou écrivez à "
            f"{SUPPORT_EMAIL_PLACEHOLDER}.",
        ),
        400,
    )
    gp = external(
        wf,
        "Obtenir la page de préférences — outil d’emailing (désactivé)",
        "POST",
        f"{EMAILING_PLACEHOLDER}/preferences-link",
        (4, 12),
        "emailing",
        body="{ token: $json.jeton }",
        notes="Réponse attendue : { preferences_url: 'https://…' } (contrat à adapter à l'outil retenu, B04).",
        on_error="continueErrorOutput",
    )
    ap = code_node(
        wf,
        "Choisir la réponse (préférences)",
        (5, 12),
        js_preferences_answer(
            "Normaliser le lien de préférences",
            html_page(
                "Vos préférences",
                "La page de préférences n'est pas disponible pour le moment.",
                'Pour ne plus recevoir aucun email : <a href="alertes-desinscrire?jeton=__JETON__">se désinscrire</a>. '
                f"Pour modifier vos choix, écrivez à {SUPPORT_EMAIL_PLACEHOLDER}.",
            ),
        ),
    )
    hasp = if_node(
        wf,
        "Page de l’outil disponible ?",
        (6, 12),
        [condition("={{ $json.preferences_url }}", "string", "notEmpty")],
    )
    go_p = respond_redirect(wf, "Répondre : page de préférences de l’outil", (7, 11.6), "={{ $json.preferences_url }}")
    page_p = wf.add(
        "Répondre : préférences par écrit",
        "n8n-nodes-base.respondToWebhook",
        1.1,
        {
            "respondWith": "text",
            "responseBody": "={{ $json.html }}",
            "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}},
        },
        (7, 12.4),
    )
    wf.chain(hp, pp, np, vp)
    wf.link(vp, gp, 0)
    wf.link(vp, bad_p, 1)
    wf.link(gp, ap, 0)
    wf.link(gp, ap, 1)
    wf.link(ap, hasp)
    wf.link(hasp, go_p, 0)
    wf.link(hasp, page_p, 1)
    # G. Confirmation d'inscription (double opt-in, email 01).
    hc = webhook(
        wf,
        "Lien de confirmation (email 01)",
        (0, 14.4),
        "alertes-confirmer",
        method="GET",
        auth="none",
        response_mode="responseNode",
        notes="Double opt-in : seule une confirmation explicite de l'outil active les alertes (puis email 02 par l'outil).",
    )
    pc = params_node(wf, "Paramètres — confirmation", (1, 14.4), WORKFLOW_KEYS["06"])
    nc = code_node(wf, "Normaliser le lien de confirmation", (2, 14.4), JS_LINK_TOKEN)
    vc = if_node(wf, "Lien de confirmation valide ?", (3, 14.4), [condition("={{ $json.valide }}", "boolean", "true")])
    confirm = external(
        wf,
        "Confirmer l’inscription — outil d’emailing (désactivé)",
        "POST",
        f"{EMAILING_PLACEHOLDER}/confirm",
        (4, 14),
        "emailing",
        body="{ token: $json.jeton }",
        notes="Réponse attendue : { confirmed: true } ; l'outil envoie ensuite l'email 02 (bienvenue et préférences).",
        on_error="continueErrorOutput",
    )
    ac = code_node(wf, "Bilan de la confirmation", (5, 14), JS_CONFIRM_ANSWER)
    okc = if_node(wf, "Inscription confirmée ?", (6, 14), [condition("={{ $json.confirmed }}", "boolean", "true")])
    go_c = respond_redirect(
        wf, "Répondre : inscription confirmée", (7, 13.6), f"{LANDING_PLACEHOLDER}/inscription-confirmee.html"
    )
    not_c = respond_html(
        wf,
        "Répondre : confirmation non enregistrée",
        (7, 14.4),
        html_page(
            "Confirmation non enregistrée",
            "Votre confirmation n'a pas pu être enregistrée (lien expiré ou service momentanément indisponible) : "
            "vos alertes ne sont <strong>pas</strong> activées.",
            "Réessayez dans quelques minutes, ou réinscrivez-vous depuis la page d'accueil.",
        ),
        200,
    )
    bad_c = respond_html(
        wf,
        "Répondre : lien de confirmation invalide",
        (4, 15),
        html_page(
            "Lien invalide",
            "Votre lien de confirmation est incomplet ou invalide : vos alertes ne sont <strong>pas</strong> activées.",
            "Réinscrivez-vous depuis la page d'accueil pour recevoir un nouveau lien.",
        ),
        400,
    )
    wf.chain(hc, pc, nc, vc)
    wf.link(vc, confirm, 0)
    wf.link(vc, bad_c, 1)
    wf.link(confirm, ac, 0)
    wf.link(confirm, ac, 1)
    wf.link(ac, okc)
    wf.link(okc, go_c, 0)
    wf.link(okc, not_c, 1)
    return wf


def _optout_incident(
    wf: Workflow, name: str, pos: tuple[float, float], params: str, kind: str, cause: str, action: str
) -> str:
    """Incident S2 (MAJEUR) sur la clé « marketing » : traitement manuel, envois marketing suspendus (hors simulation)."""
    return engine(
        wf,
        name,
        "POST",
        "/incidents",
        pos,
        params=params,
        body=(
            f"{{ cause: '{cause} : ' + ($json.resume || 'lien invalide'), kind: '{kind}', severity: 'MAJEUR', "
            f"scope: 'WORKFLOW', workflow: {ref(params)}.first().json.workflow, proposed_action: '{action}', "
            f"actor: 'n8n:06-marketing', simulation: {ref(params)}.first().json.simulation, "
            "details: { jeton: $json.jeton || null, bilan: $json.resume || null } }"
        ),
        on_error="continueErrorOutput",
        notes="Toujours suivi de la réponse à la personne, même si le moteur ne répond pas (sortie d'erreur).",
    )


def _optout_flow(
    wf: Workflow,
    *,
    row: float,
    path: str,
    label: str,
    params_name: str,
    emailing_name: str,
    emailing_url: str,
    emailing_ok_field: str,
    shopify_name: str,
    shopify_body: str,
    shopify_mutation: str,
    success_page_redirect: str | None,
    success_html: str | None,
    invalid_html: str,
    kind: str,
    cause_unconfirmed: str,
    cause_invalid: str,
    action: str,
) -> None:
    """Lien d'opposition d'un email (désinscription, refus d'avis) : réponse APRÈS les appels aux outils.

    Webhook GET public (jeton) → jeton valide ? → outil d'emailing → (client Shopify lié ?) Shopify → bilan honnête →
    confirmé partout : page de confirmation ; sinon incident S2 puis la même page (« demande reçue », traitement
    manuel annoncé) ; lien invalide : incident S2 puis page d'erreur (400). Aucun appel n'en bloque un autre
    (sorties d'erreur), aucune réponse de succès n'est envoyée avant le bilan.
    """
    norm_name = f"Normaliser le lien de {label}"
    prep_name = f"Préparer l’étape Shopify ({label})"

    def respond_success(name: str, pos: tuple[float, float]) -> str:
        if success_page_redirect is not None:
            return respond_redirect(wf, name, pos, success_page_redirect)
        assert success_html is not None
        return respond_html(wf, name, pos, success_html, 200)

    hook = webhook(
        wf,
        f"Lien de {label} (emails)",
        (0, row),
        path,
        method="GET",
        auth="none",
        response_mode="responseNode",
        notes="Jeton unique par lien (EMAILS §4 règle 7) ; la réponse attend le bilan des outils (CON-05).",
    )
    params = params_node(wf, params_name, (1, row), WORKFLOW_KEYS["06"])
    norm = code_node(wf, norm_name, (2, row), JS_LINK_TOKEN)
    valid = if_node(wf, f"Lien de {label} valide ?", (3, row), [condition("={{ $json.valide }}", "boolean", "true")])
    mail_tool = external(
        wf,
        emailing_name,
        "POST",
        emailing_url,
        (4, row - 0.4),
        "emailing",
        body="{ token: $json.jeton, source: 'lien' }",
        notes=f"Réponse attendue : {{ {emailing_ok_field}: true, shopify_customer_id?: … }} (contrat à adapter à l'outil "
        "retenu, B04). À activer AVANT tout envoi.",
        on_error="continueErrorOutput",
    )
    prep = code_node(wf, prep_name, (5, row - 0.4), js_prepare_shopify(norm_name, emailing_ok_field))
    linked = if_node(
        wf, f"Client Shopify lié ({label}) ?", (6, row - 0.4), [condition("={{ $json.shopify_applicable }}", "boolean", "true")]
    )
    shop = external(
        wf,
        shopify_name,
        "POST",
        SHOPIFY_GRAPHQL_PLACEHOLDER,
        (7, row - 0.8),
        "shopify",
        predefined=True,
        body=shopify_body,
        notes="Mutation hors liste blanche du client du moteur : à valider (agent integrations) avant activation.",
        on_error="continueErrorOutput",
    )
    bilan = code_node(wf, f"Bilan ({label})", (8, row - 0.4), js_bilan(prep_name, shopify_mutation))
    ok = if_node(
        wf, f"Confirmé par tous les outils ({label}) ?", (9, row - 0.4), [condition("={{ $json.tous_confirmes }}", "boolean", "true")]
    )
    page_ok = respond_success(f"Répondre : demande de {label} traitée", (10, row - 0.8))
    inc = _optout_incident(
        wf, f"Incident : demande de {label} non confirmée", (10, row), params_name, f"{kind}_NON_CONFIRME",
        cause_unconfirmed, action,
    )  # fmt: skip
    page_manual = respond_success(f"Répondre : demande de {label} reçue (traitement manuel)", (11, row))
    inc_bad = _optout_incident(
        wf, f"Incident : lien de {label} invalide", (4, row + 0.6), params_name, f"{kind}_LIEN_INVALIDE",
        cause_invalid,
        "Vérifier les liens générés par l’outil d’emailing ; traiter à la main toute demande reçue par email.",
    )  # fmt: skip
    page_bad = respond_html(wf, f"Répondre : lien de {label} invalide", (5, row + 0.6), invalid_html, 400)
    wf.chain(hook, params, norm, valid)
    wf.link(valid, mail_tool, 0)
    wf.link(valid, inc_bad, 1)
    wf.link(inc_bad, page_bad, 0)
    wf.link(inc_bad, page_bad, 1)
    wf.link(mail_tool, prep, 0)
    wf.link(mail_tool, prep, 1)
    wf.link(prep, linked)
    wf.link(linked, shop, 0)
    wf.link(linked, bilan, 1)
    wf.link(shop, bilan, 0)
    wf.link(shop, bilan, 1)
    wf.link(bilan, ok)
    wf.link(ok, page_ok, 0)
    wf.link(ok, inc, 1)
    wf.link(inc, page_manual, 0)
    wf.link(inc, page_manual, 1)


def wf07(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Surveillance horaire du stop-loss : photo construite par le moteur, gel et coupure via API, notification au changement."""
    wf = Workflow(WORKFLOW_IDS["07"], WORKFLOW_NAMES["07"], "07_stoploss_watch.json", credentials_map=cmap,
                  api_cred="api_photo")
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.6),
        """
## 07 — Surveillance du stop-loss (toutes les heures)
`POST /stoploss/state/refresh` : le **moteur construit la photo d'activité** à partir de ses registres (apports
attestés par la propriétaire, soldes PayPal et banque relevés par les connecteurs, stock au coût historique,
catalogue, prix publics, publicité) ; puis `GET /stoploss/status` → si l'état **change** :
- gel global → **`POST /stoploss/freeze`** (action protectrice : autonomie niveau 1, incident INC-09) ;
- campagnes à couper → plateforme publicitaire (nœud désactivé tant que le connecteur n'est pas recetté) ;
- **notification immédiate** à la propriétaire : cause, chiffres (mesure / seuil), action, **comment réarmer**.
Une alerte par changement (empreinte mémorisée ; un état qui revient est de nouveau signalé).
Branche « relevés de trésorerie » (désactivée) : PayPal et banque → `/treasury/*-balance` (connecteurs à recetter).
Jetons **nommés** : photo `n8n-07-stoploss` ; soldes `connecteur-tresorerie` — jamais le jeton qui demande une dépense.
Aucun réarmement ici : seule la propriétaire réarme, avec son jeton, depuis son terminal.
**Activation** : niveau 1, **après C19** (BL-191, J27 : point zéro posé avec la première photo, `with_photo: true`),
jamais avant — une première photo sans point zéro gèlerait tout. Avant C19, les soldes de B26 sont déposés par la
propriétaire avec son jeton (`/treasury/*-balance`), ou par une exécution manuelle de la seule branche :05.
**Validation humaine requise** : canal d'alerte immédiate ; apports déclarés (votre jeton) ; point zéro C19 ; recette des connecteurs PayPal, banque et publicité.
""",
        width=700,
        height=460,
    )
    t = wf.add(
        "Toutes les heures — stop-loss",
        "n8n-nodes-base.scheduleTrigger",
        1.2,
        {"rule": {"interval": [{"field": "hours", "hoursInterval": 1, "triggerAtMinute": 10}]}},
        (0, 0),
    )
    p = params_node(wf, "Paramètres", (1, 0), WORKFLOW_KEYS["07"])
    refresh = engine(
        wf,
        "Construire la photo (POST /stoploss/state/refresh)",
        "POST",
        "/stoploss/state/refresh",
        (2, 0),
        on_error="continueRegularOutput",
        cred="api_photo",
        notes="Photo tirée des registres du moteur. Source manquante ou périmée : 409 (la photo précédente reste et se "
        "périme) ; l'état est quand même lu et signalé « non évaluable ».",
    )
    st = engine(wf, "État du stop-loss (GET /stoploss/status)", "GET", "/stoploss/status", (3, 0), cred="api_photo")
    an = code_node(wf, "Analyser l’état (cause, chiffres, action, réarmement)", (4, 0), JS_STOPLOSS_ANALYSIS)
    report = if_node(
        wf,
        "À signaler ?",
        (5, 0),
        [
            condition("={{ $json.has_triggers }}", "boolean", "true"),
            condition("={{ $json.global_frozen }}", "boolean", "true"),
            condition("={{ $json.available }}", "boolean", "false"),
        ],
        combinator="or",
    )
    forget = code_node(wf, "Aucun déclencheur : oublier l’état signalé", (6, 0.8), JS_FORGET_STATE)
    quiet = noop(wf, "Aucun déclencheur : rien à faire", (7, 0.8))
    changed = code_node(
        wf,
        "Nouvel état ? (une alerte par changement)",
        (6, -0.2),
        JS_ON_CHANGE,
        notes="Compare l'empreinte à la dernière signalée (données statiques du workflow) : alerte au changement, "
        "pas seulement à la première apparition.",
    )
    freeze_if = if_node(
        wf, "Gel global à appliquer ?", (7, -1), [condition("={{ $json.has_freeze_all }}", "boolean", "true")]
    )
    freeze = engine(
        wf,
        "Appliquer le gel global (POST /stoploss/freeze)",
        "POST",
        "/stoploss/freeze",
        (8, -1),
        body="{ actor: 'n8n:07-stoploss-watch', reason: $json.freeze_reason || 'Gel global constaté par n8n:07' }",
        notes="Action protectrice ouverte à tous ; le réarmement reste réservé à la propriétaire.",
        cred="api_photo",
    )
    cut_if = if_node(wf, "Campagnes à couper ?", (7, -0.2), [condition("={{ $json.must_cut }}", "boolean", "true")])
    cut = external(
        wf,
        "Couper les campagnes — plateforme publicitaire (désactivé)",
        "POST",
        "https://REMPLACER-plateforme-publicitaire.exemple.invalid/campaigns/pause",
        (8, -0.2),
        "ads",
        body="{ campaigns: $json.cut_campaigns, reason: 'stop-loss pub (CAC > contribution 7 j ou plafond jour)' }",
        notes="Protecteur (niveau 1 admis) mais externe : activer après recette du connecteur CONN-PUB.",
    )
    mail = email(wf, "Notification immédiate à la propriétaire (email, désactivé)", (7, 0.6))
    sk = slack(wf, "Notification immédiate (Slack, désactivé)", (7, 1.2))
    wf.chain(t, p, refresh, st, an, report)
    wf.link(report, changed, 0)
    wf.link(report, forget, 1)
    wf.link(forget, quiet)
    wf.link(changed, freeze_if)
    wf.link(changed, cut_if)
    wf.link(changed, mail)
    wf.link(changed, sk)
    wf.link(freeze_if, freeze, 0)
    wf.link(cut_if, cut, 0)
    # Relevés de trésorerie (connecteurs) : déclencheur désactivé tant que les connecteurs ne sont pas recettés.
    t2 = wf.add(
        "Toutes les heures (:05) — relevés de trésorerie (désactivé)",
        "n8n-nodes-base.scheduleTrigger",
        1.2,
        {"rule": {"interval": [{"field": "hours", "hoursInterval": 1, "triggerAtMinute": 5}]}},
        (0, 2.4),
        disabled=True,
        notes="Activer avec les connecteurs PayPal et banque recettés (CONN-PAYPAL, connecteur bancaire) : la photo "
        "du stop-loss exige des soldes de moins de 24 h, et le mandat de moins de 60 min.",
    )
    pt = params_node(wf, "Paramètres — trésorerie", (1, 2.4), WORKFLOW_KEYS["07"])
    pp_read = external(
        wf,
        "Lire le solde PayPal — API PayPal (désactivé)",
        "GET",
        "https://api-m.paypal.com/v1/reporting/balances?currency_code=CHF",
        (2, 2),
        "paypal_read",
        notes="Lecture seule du compte PayPal dédié (scope reporting) avec le credential « PayPal compte dédié — lecture "
        "des soldes », distinct du credential de paiement de 08 ; activer après recette CONN-PAYPAL.",
    )
    pp_norm = code_node(wf, "Normaliser le solde PayPal", (3, 2), JS_PAYPAL_BALANCE)
    pp_post = engine(
        wf,
        "Déposer le solde PayPal (POST /treasury/paypal-balance)",
        "POST",
        "/treasury/paypal-balance",
        (4, 2),
        params="Paramètres — trésorerie",
        body="{ as_of: $json.as_of, balance_chf: $json.balance_chf, source: $json.source }",
        cred="api_tresorerie",
    )
    bk_read = external(
        wf,
        "Lire le solde bancaire — connecteur bancaire (désactivé)",
        "GET",
        "https://REMPLACER-connecteur-bancaire.exemple.invalid/solde",
        (2, 2.8),
        "bank",
        notes="Connecteur en lecture seule du compte de l'activité (banque à choisir) ; contrat de réponse dans le nœud suivant.",
    )
    bk_norm = code_node(wf, "Normaliser le solde bancaire", (3, 2.8), JS_BANK_BALANCE)
    bk_post = engine(
        wf,
        "Déposer le solde bancaire (POST /treasury/bank-balance)",
        "POST",
        "/treasury/bank-balance",
        (4, 2.8),
        params="Paramètres — trésorerie",
        body="{ as_of: $json.as_of, balance_chf: $json.balance_chf, source: $json.source }",
        cred="api_tresorerie",
    )
    wf.chain(t2, pt, pp_read, pp_norm, pp_post)
    wf.chain(pt, bk_read, bk_norm, bk_post)
    return wf


def wf08(cmap: Mapping[str, str] | None = None) -> Workflow:
    """Mandat de dépense : POST /mandate/check -> approuvée (préparer, journaliser) / validation 1 clic / refusée."""
    wf = Workflow(WORKFLOW_IDS["08"], WORKFLOW_NAMES["08"], "08_mandat_depenses.json", credentials_map=cmap)
    sticky(
        wf,
        "Note — à lire",
        (-1, -2.6),
        """
## 08 — Mandat de dépense (passerelle CONN-PAYPAL, DELEGATION_AUTONOMIE.md)
Toute demande d'achat ou de paiement d'un agent arrive ici par **son** webhook (`pokeshop-depense-<rôle>`, un secret par
agent : le demandeur est fixé par le webhook, jamais par le corps) → **`POST /mandate/check`** (enregistrée au
registre, idempotente par clé) :
- **APPROVED_WITHIN_MANDATE** → réponse à l'agent, paiement PayPal **préparé** (nœud d'exécution désactivé), journal ;
- **NEEDS_HUMAN_APPROVAL** → email de **validation en 1 clic** (formulaire protégé, 24 h ; sans réponse : refus = statu quo) ;
  un virement est **préparé**, la propriétaire le signe dans son e-banking ;
- **REJECTED** → réponse avec les motifs (interdits, stop-loss, réserve cash…).
Contrôle impossible (mandat illisible, stop-loss non évalué) → **refus par défaut**.
**Activation** : niveau 1 (contrôle et validation) ; exécution PayPal après mandat signé et recette CONN-PAYPAL.
**Validation humaine requise** : signature du mandat (B01), empreinte au coffre, recette PayPal, routes moteur d'exécution.
""",
        width=700,
        height=430,
    )
    # Revue R4 (SEC-16, R3-NEW-06) : un webhook et un secret PAR AGENT qui dépense ; le demandeur (requested_by) est
    # fixé par le webhook appelé, jamais lu dans le corps ; le moteur n'admet en relais que ces agents.
    hook = noop(
        wf,
        "Demande de dépense (passerelle agents)",
        (0, 0),
        notes="Point de jonction des webhooks par agent : corps {request} avec requested_by imposé par le webhook.",
    )
    for i, role in enumerate(SPEND_RELAY_ROLES):
        row = -3.2 + 0.8 * i
        gate = webhook(
            wf,
            f"Demande de dépense — {role} (passerelle)",
            (-2, row),
            f"pokeshop-depense-{role}",
            response_mode="responseNode",
            gateway=f"gateway_08_{role}",
            notes=f'Secret remis au seul agent « {role} ». Corps : {{"request": SpendRequest}} — montants en chaînes ; '
            "aucune trésorerie (le moteur la lit dans ses registres).",
        )
        tag = code_node(
            wf,
            f"Demandeur imposé : {role}",
            (-1, row),
            JS_SPEND_REQUESTER.replace("__ROLE__", role),
            notes="requested_by = rôle du webhook (secret propre à l'agent), jamais celui déclaré dans le corps.",
        )
        wf.chain(gate, tag, hook)
    p = params_node(wf, "Paramètres", (1, 0), WORKFLOW_KEYS["08"])
    read, guard = suspension_guard(wf, 2, 0)
    wf.chain(hook, p, read)
    suspended = respond(
        wf,
        "Répondre : dépenses suspendues",
        (4, -0.8),
        "{ outcome: 'REJECTED', motif: 'Workflow de dépense suspendu par un incident ouvert : aucune dépense.' }",
        423,
    )
    wf.link(guard, suspended, 0)
    req = f"{ref('Demande de dépense (passerelle agents)')}.first().json.body"
    check = engine(
        wf,
        "Contrôle du mandat (POST /mandate/check)",
        "POST",
        "/mandate/check",
        (4, 0.2),
        body=f"{{ request: {req}.request, record: true }}",
        on_error="continueErrorOutput",
        notes="Décision tracée au registre (record: true), idempotente par clé ; aucune exécution ici. Jeton nommé "
        "n8n-08-mandat (relais) : requested_by = rôle de l'agent (.claude/agents), non authentifié => trésorerie "
        "jamais vérifiable, validation humaine (TREASURY_UNVERIFIED) ; incident ouvert sur « mandat-depenses » => "
        "423 (refus).",
    )
    wf.link(guard, check, 1)
    cannot = respond(
        wf,
        "Répondre : contrôle impossible (refus par défaut)",
        (5, 1.4),
        "{ outcome: 'REJECTED', motif: 'Contrôle du mandat impossible (mandat illisible, stop-loss non évalué ou demande invalide) : refus par défaut.' }",
        503,
    )
    cannot_msg = set_node(
        wf,
        "Préparer l’alerte contrôle impossible",
        (6, 1.4),
        [
            (
                "sujet",
                "=[MANDAT] Contrôle impossible : {{ $('Demande de dépense (passerelle agents)').first().json.body.request.idempotency_key }}",
                "string",
            ),
            (
                "texte",
                "=La demande a été refusée par défaut. Vérifier le mandat (signature, empreinte) et la photo du stop-loss.",
                "string",
            ),
        ],
    )
    cannot_mail = email(wf, "Alerte : contrôle du mandat impossible (email, désactivé)", (7, 1.4))
    wf.link(check, cannot, 1)
    wf.chain(cannot, cannot_msg, cannot_mail)
    outcome = switch_node(
        wf,
        "Issue de la décision",
        (5, 0.2),
        "={{ $json.decision.outcome }}",
        ("APPROVED_WITHIN_MANDATE", "NEEDS_HUMAN_APPROVAL", "REJECTED"),
        "Issue inconnue",
    )
    wf.link(check, outcome, 0)
    # Approuvée dans le mandat.
    ok_resp = respond(
        wf,
        "Répondre : approuvée dans le mandat",
        (6, -1.2),
        "{ outcome: $json.decision.outcome, decision_ref: $json.decision.idempotency_key, montant_chf: $json.decision.amount_chf, cout_effectif_chf: $json.decision.effective_cost_chf }",
        200,
    )
    prep = set_node(
        wf,
        "Préparer le paiement PayPal (Payouts)",
        (7, -1.2),
        [
            ("sender_batch_id", f"={{{{ {req}.request.idempotency_key }}}}", "string"),
            ("montant", f"={{{{ {req}.request.amount }}}}", "string"),
            ("devise", f"={{{{ {req}.request.currency }}}}", "string"),
            ("beneficiaire_ref", f"={{{{ {req}.request.supplier_id }}}}", "string"),
        ],
        notes="Coordonnées du bénéficiaire : référence au coffre (payee_ref du mandat), jamais dans ce workflow.",
    )
    pay = external(
        wf,
        "Exécuter le paiement PayPal — DÉSACTIVÉ",
        "POST",
        "https://api-m.paypal.com/v1/payments/payouts",
        (8, -1.2),
        "paypal",
        body="{ sender_batch_header: { sender_batch_id: $json.sender_batch_id, email_subject: 'Paiement fournisseur' }, items: [ { recipient_type: 'PAYPAL_ID', amount: { value: $json.montant, currency: $json.devise }, receiver: 'REMPLACER-par-la-reference-du-coffre', sender_item_id: $json.sender_batch_id } ] }",
        notes="Activer seulement : mandat signé (B01), empreinte au coffre, recette CONN-PAYPAL. sender_batch_id = clé d'idempotence.",
    )
    executed = engine(
        wf,
        "Marquer exécuté — route moteur attendue (désactivé)",
        "POST",
        "/mandate/executed",
        (9, -1.2),
        disabled=True,
        body=f"{{ idempotency_key: {req}.request.idempotency_key }}",
        notes="Route à créer : SpendLedger.mark_executed (idempotent) puis rapprochement du relevé.",
    )
    ok_log = noop(wf, "Journal : dépense approuvée", (10, -1.2))
    wf.link(outcome, ok_resp, 0)
    wf.chain(ok_resp, prep, pay, executed, ok_log)
    # Validation humaine en 1 clic.
    human_resp = respond(
        wf,
        "Répondre : en attente de validation humaine",
        (6, -0.2),
        "{ outcome: $json.decision.outcome, motifs: $json.labels_fr, statut: 'en attente de la propriétaire (24 h)' }",
        202,
    )
    human_msg = set_node(
        wf,
        "Préparer l’email de validation 1 clic",
        (7, -0.2),
        [
            (
                "sujet",
                f"=[À VALIDER] {{{{ {req}.request.purpose }}}} — {{{{ $('Contrôle du mandat (POST /mandate/check)').first().json.decision.amount_chf }}}} CHF",
                "string",
            ),
            (
                "texte",
                f"=Demande de {{{{ {req}.request.requested_by }}}} : {{{{ {req}.request.purpose }}}}\n"
                f"Bénéficiaire : {{{{ {req}.request.supplier_id }}}} ; source du montant : {{{{ {req}.request.amount_source }}}}\n"
                "Montant : {{ $('Contrôle du mandat (POST /mandate/check)').first().json.decision.amount_chf }} CHF "
                "(coût effectif {{ $('Contrôle du mandat (POST /mandate/check)').first().json.decision.effective_cost_chf }} CHF)\n"
                "Motifs : {{ $('Contrôle du mandat (POST /mandate/check)').first().json.labels_fr.join(' ; ') }}\n"
                "Virement préparé : {{ $('Contrôle du mandat (POST /mandate/check)').first().json.decision.transfer_draft ? 'oui, à signer dans votre e-banking (aucune coordonnée ici)' : 'non' }}\n\n"
                "Décider en 1 clic : {{ $execution.resumeFormUrl }}\nSans réponse sous 24 h : refus (statu quo sûr).\n"
                "INTERNE — ne jamais transférer.",
                "string",
            ),
        ],
    )
    human_mail = email(wf, "Email de validation 1 clic à la propriétaire (désactivé)", (8, -0.2))
    wait = wait_form(
        wf,
        "Validation de la propriétaire (formulaire, 24 h)",
        (9, -0.2),
        title="Validation d'une dépense hors mandat",
        description=f"={{{{ {req}.request.purpose }}}} — montant et motifs dans l'email ; aucune coordonnée bancaire ici.",
        choices=("Approuver", "Refuser"),
        hours=24,
    )
    decided = if_node(
        wf,
        "Approuvée par la propriétaire ?",
        (10, -0.2),
        [condition("={{ $json['Décision'] }}", "string", "equals", "Approuver")],
    )
    # Revue R5 (R4-DOC-03) : POST /mandate/human-decision existe et exige le JETON PROPRIÉTAIRE, jamais détenu par n8n.
    # Le formulaire ne fait que guider le parcours ; la propriétaire enregistre sa décision au moteur depuis son
    # terminal (sans cela : ni payable — can_execute —, ni comptée au stop-loss pub ; expirée après 24 h).
    record_ok = set_node(
        wf,
        "Rappel : enregistrer la validation au moteur (propriétaire, son jeton)",
        (11, -0.6),
        [
            ("sujet", f"=[À ENREGISTRER] Validation de {{{{ {req}.request.idempotency_key }}}}", "string"),
            (
                "texte",
                f"=Depuis votre terminal (jeton propriétaire, jamais dans n8n) : POST /mandate/human-decision avec "
                f"idempotency_key = {{{{ {req}.request.idempotency_key }}}} et decision = APPROVE, en-tête "
                "X-Pokeshop-Owner-Token, dans les 24 h. Sans cet enregistrement, la dépense n'est ni payable ni comptée "
                "dans le stop-loss pub.",
                "string",
            ),
        ],
        notes="POST /mandate/human-decision : jeton propriétaire seul (matrice authz) — n8n ne le détient pas.",
    )
    exec_h = external(
        wf,
        "Exécuter : PayPal ou virement signé dans l’e-banking (désactivé)",
        "POST",
        "https://api-m.paypal.com/v1/payments/payouts",
        (12, -0.6),
        "paypal",
        body=f"{{ sender_batch_header: {{ sender_batch_id: {req}.request.idempotency_key }}, items: [] }}",
        notes="Virement : la propriétaire signe l'ordre préparé dans son e-banking ; PayPal : après recette et "
        "enregistrement de la validation au moteur (HUMAN_APPROVED, moins d'une heure).",
    )
    ok_h = noop(wf, "Journal : validée par la propriétaire", (13, -0.6))
    record_no = noop(
        wf,
        "Refus ou expiration : rien à payer (statu quo sûr)",
        (11, 0.2),
        notes="Facultatif : la propriétaire peut enregistrer le refus (POST /mandate/human-decision, decision REFUSE, son "
        "jeton) ; sinon la demande expire au registre après 24 h et n'est jamais engagée.",
    )
    no_h = noop(wf, "Journal : refus ou expiration (statu quo sûr)", (12, 0.2))
    wf.link(outcome, human_resp, 1)
    wf.chain(human_resp, human_msg, human_mail, wait, decided)
    wf.link(decided, record_ok, 0)
    wf.link(decided, record_no, 1)
    wf.chain(record_ok, exec_h, ok_h)
    wf.link(record_no, no_h)
    # Refusée.
    rejected = respond(
        wf,
        "Répondre : refusée (motifs)",
        (6, 0.6),
        "{ outcome: $json.decision.outcome, motifs: $json.labels_fr, codes: $json.decision.reasons }",
        200,
    )
    rejected_log = noop(wf, "Journal : refus du mandat", (7, 0.6))
    unknown = respond(
        wf,
        "Répondre : issue inconnue (refus par défaut)",
        (6, 1.0),
        "{ outcome: 'REJECTED', motif: 'Issue de contrôle inconnue : refus par défaut.' }",
        500,
    )
    wf.link(outcome, rejected, 2)
    wf.link(rejected, rejected_log)
    wf.link(outcome, unknown, 3)
    return wf


BUILDERS: tuple[Callable[[Mapping[str, str] | None], Workflow], ...] = (wf01, wf02, wf03, wf04, wf05, wf06, wf07, wf08)


# ------------------------------------------------------------------------------- contrôles

_EXPR_SEGMENT = re.compile(r"\{\{(.*?)\}\}", re.S)


def expression_errors(value: str) -> list[str]:
    """Erreurs de gabarit d'une expression n8n (``{{ … }}`` imbriqués ou non fermés)."""
    errors: list[str] = []
    for segment in _EXPR_SEGMENT.findall(value):
        if "{{" in segment:
            errors.append(f"segment imbriqué : {segment[:60]!r}")
    rest = _EXPR_SEGMENT.sub("", value)
    if "}}" in rest or "{{" in rest:
        errors.append(f"accolades doubles non appariées : {value[:80]!r}")
    return errors


def _walk_strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _walk_strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _walk_strings(v)]
    return []


def validate(export: Mapping[str, Any]) -> list[str]:
    """Contrôles structurels minimaux (les tests en ajoutent d'autres)."""
    errors: list[str] = []
    names = [n["name"] for n in export["nodes"]]
    if len(set(names)) != len(names):
        errors.append("noms de nœuds en double")
    for src, outs in export["connections"].items():
        if src not in names:
            errors.append(f"connexion depuis un nœud inconnu : {src}")
        for branch in outs["main"]:
            for link in branch:
                if link["node"] not in names:
                    errors.append(f"connexion vers un nœud inconnu : {src} -> {link['node']}")
    for node in export["nodes"]:
        if node["type"] == "n8n-nodes-base.code":
            continue
        for text in _walk_strings(node["parameters"]):
            if text.startswith("="):
                errors.extend(f"{node['name']} : {e}" for e in expression_errors(text))
    return errors


def build_all(credentials_map: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Construit les huit exports (nom de fichier -> JSON)."""
    out: dict[str, dict[str, Any]] = {}
    for builder in BUILDERS:
        wf = builder(credentials_map)
        export = wf.export()
        errors = validate(export)
        if errors:
            raise ValueError(f"{wf.filename} : " + " ; ".join(errors))
        out[wf.filename] = export
    return out


def render(export: Mapping[str, Any]) -> str:
    """Sérialisation stable (UTF-8, indentation 2)."""
    return json.dumps(export, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(description="Workflows n8n de {{NOM_BOUTIQUE}} (inactifs, écritures désactivées).")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="dossier de sortie")
    parser.add_argument("--check", action="store_true", help="vérifie que les fichiers committés sont à jour")
    parser.add_argument(
        "--credentials-map",
        type=Path,
        help="JSON {clé logique: id du credential dans VOTRE n8n} (ids seulement, aucun secret)",
    )
    args = parser.parse_args(argv)
    cmap: dict[str, str] | None = None
    if args.credentials_map is not None:
        cmap = json.loads(args.credentials_map.read_text(encoding="utf-8"))
        unknown = set(cmap) - set(CREDENTIALS)
        if unknown:
            print(f"clés inconnues dans la table des credentials : {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        if args.out.resolve() == OUT_DIR.resolve():
            print(
                "--credentials-map exige --out vers un autre dossier (les exports committés restent génériques).",
                file=sys.stderr,
            )
            return 2
    exports = build_all(cmap)
    if args.check:
        stale = [
            name
            for name, data in exports.items()
            if not (args.out / name).exists() or (args.out / name).read_text(encoding="utf-8") != render(data)
        ]
        extra = sorted(p.name for p in args.out.glob("*.json") if p.name not in exports)
        if stale or extra:
            print(f"À régénérer : {', '.join(stale) or '—'} ; fichiers inattendus : {', '.join(extra) or '—'}")
            return 1
        print(f"{len(exports)} workflows à jour.")
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in exports.items():
        (args.out / name).write_text(render(data), encoding="utf-8")
    print(f"{len(exports)} workflows écrits dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
