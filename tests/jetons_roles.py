"""Jetons FICTIFS par rôle de la matrice d'autorisations (:mod:`pokeshop.authz`) pour les tests de l'API.

Un jeton par rôle (agents de ``.claude/agents/`` et connecteurs/workflows n8n) ; le nom du jeton est le rôle.
"""

from __future__ import annotations

from pokeshop.api import API_TOKEN_HEADER
from pokeshop.authz import KNOWN_ROLES
from pokeshop.settings import sha256_hex

ROLE_TOKENS: dict[str, str] = {role: f"FICTIF-jeton-{role}-0000000001" for role in sorted(KNOWN_ROLES)}
"""Rôle -> jeton en clair (FICTIF)."""


def headers(role: str) -> dict[str, str]:
    """En-têtes d'un appel avec le jeton nommé du rôle."""
    return {API_TOKEN_HEADER: ROLE_TOKENS[role]}


def agent_tokens_env(roles: tuple[str, ...] | None = None) -> str:
    """Valeur de ``POKESHOP_AGENT_TOKENS_SHA256`` (``rôle:empreinte,…``) pour ``roles`` (défaut : tous)."""
    selected = sorted(KNOWN_ROLES) if roles is None else roles
    return ",".join(f"{role}:{sha256_hex(ROLE_TOKENS[role])}" for role in selected)


HF = headers("finance-pricing")
HQA = headers("qa-conformite")
HOPS = headers("operations-sav")
HCAT = headers("catalogue")
HDATA = headers("donnees-fournisseurs")
HSITE = headers("site-integrations")
HACQ = headers("acquisition")
HCHEF = headers("chef-de-projet")
HSYNC = headers("n8n-01-sync")
HORDERS = headers("n8n-02-commandes")
HINC = headers("n8n-04-incidents")
HPHOTO = headers("n8n-07-stoploss")
HMANDAT = headers("n8n-08-mandat")
HTRES = headers("connecteur-tresorerie")
HADS = headers("connecteur-publicite")
