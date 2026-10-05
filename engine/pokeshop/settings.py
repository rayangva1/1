"""Configuration du service d'intégration lue dans les variables d'environnement (agent integrations).

* **Aucun secret en dur** : jetons et URL de base viennent du coffre via l'environnement du conteneur
  (fichier ``/etc/pokeshop/api.env`` hors du dépôt, lu par ``scripts/compose.sh`` ; ``.env.example``
  n'en documente que les noms). Les secrets sont des :class:`pydantic.SecretStr` : jamais affichés par
  ``repr`` ni journalisés.
* Les jetons d'API et de la propriétaire ne sont **jamais** stockés en clair : seule leur
  empreinte sha256 est configurée (``POKESHOP_API_TOKEN_SHA256``,
  ``POKESHOP_OWNER_TOKEN_SHA256``). Les deux empreintes doivent différer (jetons distincts).
  **Jetons nommés par rôle** (``POKESHOP_AGENT_TOKENS_SHA256`` = ``rôle:empreinte,rôle2:empreinte``) : le
  nom est un **rôle** de la matrice d'autorisations (:mod:`pokeshop.authz` : les 12 agents de
  ``.claude/agents/`` et les connecteurs/workflows n8n) ; un nom inconnu est refusé au démarrage. L'acteur
  est déduit du jeton (jamais auto-déclaré). Le **jeton commun** (``POKESHOP_API_TOKEN_SHA256``,
  facultatif) n'a que la lecture et les aperçus en simulation.
* **Empreintes signées par la propriétaire** (coffre) : mandat (``POKESHOP_MANDATE_FINGERPRINT``,
  obligatoire pour un mandat actif), seuils du stop-loss (``POKESHOP_STOPLOSS_FINGERPRINT``) et
  règles de prix (``POKESHOP_RULES_FINGERPRINT``) ; absentes => seuils les plus stricts, et
  :meth:`Settings.real_write_blockers` les liste.
* **Simulation par défaut** (SPEC §0.6) : ``POKESHOP_DRY_RUN`` vaut ``true`` tant qu'il n'est
  pas explicitement mis à ``false`` ; une écriture réelle exige en plus le niveau d'autonomie
  adéquat (:mod:`pokeshop.autonomy`).
* **États de sécurité persistés** (verrou et journal du stop-loss, dernière photo valide, registre
  du mandat, étoile polaire, incidents et confinements, historique des prix, niveau d'autonomie) :
  table ``pokeshop.engine_state_journal`` si ``POKESHOP_DATABASE_URL`` est fourni, sinon fichiers
  JSON Lines en ajout seul dans ``POKESHOP_STATE_DIR`` (défaut : :func:`default_state_dir`).
  ``POKESHOP_STATE_DIR=:memory:`` (tests) est refusé en production.
* Dépendances : stdlib + pydantic (SPEC §1). ``pydantic-settings`` n'est pas requis : la
  lecture de ``os.environ`` est faite ici, variable par variable (:data:`ENV_VARIABLES`).

Le fichier ``.env.example`` à la racine documente chaque variable (sans valeur réelle).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator

from .authz import AUTHZ_VERSION, KNOWN_ROLES
from .errors import PokeshopError
from .models import FrozenModel, VatMode

__all__ = [
    "REPO_ROOT",
    "DEFAULT_SHOPIFY_API_VERSION",
    "ENV_VARIABLES",
    "ROLE_TOKEN_PREFIX",
    "ROLE_TOKEN_VARIABLES",
    "SettingsError",
    "Settings",
    "load_settings",
    "get_settings",
    "sha256_hex",
    "is_owner_like",
    "STATE_DIR_MEMORY",
    "default_state_dir",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHOPIFY_API_VERSION = "2026-10"
"""Version stable de l'Admin API publiée le 1.10.2026 (index de recherche shopify.dev, consulté le 4.10.2026)."""

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$")
_API_VERSION_RE = re.compile(r"^(\d{4}-(01|04|07|10)|unstable)$")
_LOCATION_RE = re.compile(r"^gid://shopify/Location/\d+$")
_PRINCIPAL_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,63}$")
_OWNER_LIKE = ("propri", "owner", "proprio")
STATE_DIR_MEMORY = ":memory:"
"""Valeur de ``POKESHOP_STATE_DIR`` qui garde les états en mémoire (tests, jamais en production)."""


def default_state_dir() -> Path:
    """Dossier d'état par défaut : ``$XDG_STATE_HOME/pokeshop`` sinon ``~/.local/state/pokeshop``.

    Hors du dépôt (rien à ignorer dans git) ; lu à chaque construction de :class:`Settings`.
    """
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".local" / "state") / "pokeshop"

ENV_VARIABLES: dict[str, tuple[str, ...]] = {
    "env": ("POKESHOP_ENV",),
    "dry_run": ("POKESHOP_DRY_RUN",),
    "vat_profile": ("POKESHOP_VAT_PROFILE",),
    "timezone": ("POKESHOP_TIMEZONE",),
    "rules_path": ("POKESHOP_RULES_PATH",),
    "stoploss_path": ("POKESHOP_STOPLOSS_PATH",),
    "mandate_path": ("POKESHOP_MANDATE_PATH",),
    "mandate_fingerprint": ("POKESHOP_MANDATE_FINGERPRINT",),
    "stoploss_fingerprint": ("POKESHOP_STOPLOSS_FINGERPRINT",),
    "rules_fingerprint": ("POKESHOP_RULES_FINGERPRINT",),
    "owner_token_sha256": ("POKESHOP_OWNER_TOKEN_SHA256",),
    "api_token_sha256": ("POKESHOP_API_TOKEN_SHA256",),
    "agent_tokens_sha256": ("POKESHOP_AGENT_TOKENS_SHA256",),
    "shopify_shop_domain": ("POKESHOP_SHOPIFY_SHOP_DOMAIN",),
    "shopify_api_version": ("POKESHOP_SHOPIFY_API_VERSION",),
    "shopify_admin_token": ("POKESHOP_SHOPIFY_ADMIN_TOKEN", "SHOPIFY_ADMIN_TOKEN"),
    "shopify_location_id": ("POKESHOP_SHOPIFY_LOCATION_ID",),
    "shopify_test_store": ("POKESHOP_SHOPIFY_TEST_STORE",),
    "shopify_timeout_seconds": ("POKESHOP_SHOPIFY_TIMEOUT_SECONDS",),
    "shopify_max_retries": ("POKESHOP_SHOPIFY_MAX_RETRIES",),
    "shopify_backoff_base_ms": ("POKESHOP_SHOPIFY_BACKOFF_BASE_MS",),
    "shopify_backoff_max_ms": ("POKESHOP_SHOPIFY_BACKOFF_MAX_MS",),
    "stale_claim_minutes": ("POKESHOP_STALE_CLAIM_MINUTES",),
    "database_url": ("POKESHOP_DATABASE_URL",),
    "n8n_webhook_url": ("POKESHOP_N8N_WEBHOOK_URL",),
    "notify_dry_run": ("POKESHOP_NOTIFY_DRY_RUN",),
    "autonomy_level": ("POKESHOP_AUTONOMY_LEVEL",),
    "autonomy_state_path": ("POKESHOP_AUTONOMY_STATE_PATH",),
    "state_dir": ("POKESHOP_STATE_DIR",),
    "imports_dir": ("POKESHOP_IMPORTS_DIR",),
}
"""Champ de :class:`Settings` -> variables d'environnement acceptées (la première présente gagne)."""

ROLE_TOKEN_PREFIX = "POKESHOP_ROLE_TOKEN_SHA256_"
ROLE_TOKEN_VARIABLES: dict[str, str] = {
    role: ROLE_TOKEN_PREFIX + role.upper().replace("-", "_") for role in sorted(KNOWN_ROLES)
}
"""Rôle de la matrice -> variable de son empreinte de jeton (une ligne par rôle dans ``/etc/pokeshop/api.env``).

Fusionnées avec ``POKESHOP_AGENT_TOKENS_SHA256`` (``rôle:empreinte,…``) ; un rôle défini deux fois est refusé."""


class SettingsError(PokeshopError, ValueError):
    """Configuration invalide : le message cite les variables d'environnement concernées."""


def sha256_hex(value: str) -> str:
    """Empreinte sha256 hexadécimale d'un jeton (comparée en temps constant par l'appelant)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_owner_like(name: str) -> bool:
    """Vrai si un nom d'acteur se fait passer pour la propriétaire (comparaison sans accents ni casse)."""
    import unicodedata

    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return any(word in plain for word in _OWNER_LIKE)


class Settings(FrozenModel):
    """Paramètres du service ; voir ``.env.example`` pour la documentation de chaque variable."""

    env: Literal["dev", "test", "prod"] = "dev"
    dry_run: bool = True
    """Simulation par défaut : aucune écriture Shopify ni notification externe réelle."""
    vat_profile: VatMode = VatMode.EFFECTIVE
    """Profil TVA des règles de prix ; décision de la fiduciaire (intervention B10) à reporter ici."""
    timezone: str = "Europe/Zurich"
    rules_path: Path | None = None
    stoploss_path: Path | None = None
    mandate_path: Path | None = None
    mandate_fingerprint: str | None = None
    stoploss_fingerprint: str | None = None
    rules_fingerprint: str | None = None
    owner_token_sha256: str | None = None
    api_token_sha256: str | None = None
    agent_tokens_sha256: dict[str, str] = Field(default_factory=dict)
    """Jetons nommés : nom de l'agent -> empreinte sha256 (``nom:empreinte,…``) ; l'acteur est déduit du jeton."""
    shopify_shop_domain: str | None = None
    shopify_api_version: str = DEFAULT_SHOPIFY_API_VERSION
    shopify_admin_token: SecretStr | None = None
    shopify_location_id: str | None = None
    shopify_test_store: bool = False
    """Vrai seulement pour une boutique de développement Shopify (recette) : données FICTIVES admises."""
    shopify_timeout_seconds: int = Field(default=30, ge=1, le=120)
    shopify_max_retries: int = Field(default=5, ge=0, le=10)
    shopify_backoff_base_ms: int = Field(default=500, ge=1, le=60_000)
    shopify_backoff_max_ms: int = Field(default=30_000, ge=1, le=300_000)
    stale_claim_minutes: int = Field(default=10, ge=1, le=1440)
    database_url: SecretStr | None = None
    n8n_webhook_url: str | None = None
    notify_dry_run: bool = True
    autonomy_level: int = Field(default=1, ge=1, le=4)
    """Niveau initial si aucun niveau n'est encore stocké (BP §13 : 1 = simulation)."""
    autonomy_state_path: Path | None = None
    """Historique du niveau sans base ; vide = ``<state_dir>/autonomy.jsonl``."""
    state_dir: Path | None = Field(default_factory=default_state_dir)
    """Dossier des journaux d'état JSON Lines (sans base) ; ``None`` = mémoire (``:memory:``, hors prod)."""
    imports_dir: Path = REPO_ROOT / "data" / "samples"
    """Seul dossier lisible par la route ``/imports/{supplier}/run`` (pas de chemin arbitraire)."""

    @field_validator("state_dir", mode="before")
    @classmethod
    def _state_dir(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == STATE_DIR_MEMORY:
            return None
        return v

    @field_validator("agent_tokens_sha256", mode="before")
    @classmethod
    def _agents(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        out: dict[str, str] = {}
        for item in (part.strip() for part in v.split(",")):
            if not item:
                continue
            name, sep, digest = item.partition(":")
            if not sep:
                raise ValueError("format attendu nom:empreinte_sha256, séparés par des virgules")
            name, digest = name.strip().lower(), digest.strip().lower()
            if name in out:
                raise ValueError(f"jeton nommé en double : {name}")
            out[name] = digest
        return out

    @field_validator("agent_tokens_sha256")
    @classmethod
    def _agents_valid(cls, v: dict[str, str]) -> dict[str, str]:
        for name, digest in v.items():
            if not _PRINCIPAL_RE.match(name) or name == "api":
                raise ValueError(f"nom de jeton invalide : {name!r} ([a-z0-9_.-], 2 à 64 caractères, pas « api »)")
            if is_owner_like(name):
                raise ValueError(f"nom de jeton réservé à la propriétaire : {name!r}")
            if name not in KNOWN_ROLES:
                raise ValueError(
                    f"nom de jeton inconnu de la matrice d'autorisations : {name!r} (rôles admis : "
                    f"{', '.join(sorted(KNOWN_ROLES))} ; engine/pokeshop/authz.py)"
                )
            if not _SHA256_RE.match(digest):
                raise ValueError(f"empreinte sha256 attendue pour {name}")
        if len(set(v.values())) != len(v):
            raise ValueError("deux jetons nommés ont la même empreinte : un jeton par agent")
        return v

    @field_validator("owner_token_sha256", "api_token_sha256", "mandate_fingerprint", "stoploss_fingerprint",
                     "rules_fingerprint")
    @classmethod
    def _sha(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not _SHA256_RE.match(v):
            raise ValueError("empreinte sha256 hexadécimale (64 caractères) attendue")
        return v

    @field_validator("shopify_shop_domain")
    @classmethod
    def _shop(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not _SHOP_RE.match(v):
            raise ValueError("domaine attendu de la forme <boutique>.myshopify.com")
        return v

    @field_validator("shopify_api_version")
    @classmethod
    def _version(cls, v: str) -> str:
        if not _API_VERSION_RE.match(v.strip()):
            raise ValueError("version d'API attendue AAAA-MM (01, 04, 07 ou 10) ou 'unstable'")
        return v.strip()

    @field_validator("shopify_location_id")
    @classmethod
    def _location(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _LOCATION_RE.match(v.strip()):
            raise ValueError("identifiant attendu gid://shopify/Location/<nombre>")
        return v.strip()

    @field_validator("n8n_webhook_url")
    @classmethod
    def _webhook(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("URL http(s) attendue")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if (
            self.api_token_sha256 is not None
            and self.owner_token_sha256 is not None
            and self.api_token_sha256 == self.owner_token_sha256
        ):
            raise ValueError("jeton d'API et jeton de la propriétaire identiques : deux jetons distincts exigés")
        reserved = {h for h in (self.api_token_sha256, self.owner_token_sha256) if h is not None}
        if reserved & set(self.agent_tokens_sha256.values()):
            raise ValueError("un jeton nommé reprend le jeton d'API ou celui de la propriétaire : jetons distincts exigés")
        if self.shopify_backoff_max_ms < self.shopify_backoff_base_ms:
            raise ValueError("POKESHOP_SHOPIFY_BACKOFF_MAX_MS < POKESHOP_SHOPIFY_BACKOFF_BASE_MS")
        if self.env == "prod" and self.database_url is None and self.state_dir is None:
            raise ValueError(
                "POKESHOP_STATE_DIR=:memory: interdit en production : les états de sécurité doivent survivre "
                "au redémarrage (dossier d'état ou POKESHOP_DATABASE_URL)"
            )
        return self

    @property
    def state_backend(self) -> str:
        """Stockage des états de sécurité : ``postgres``, ``fichier`` ou ``memoire``."""
        if self.database_url is not None:
            return "postgres"
        return "fichier" if self.state_dir is not None else "memoire"

    # -- dérivés -----------------------------------------------------------------
    @property
    def shopify_configured(self) -> bool:
        """Vrai si domaine et jeton Shopify sont fournis (lecture/écriture possibles)."""
        return self.shopify_shop_domain is not None and self.shopify_admin_token is not None

    @property
    def real_writes_enabled(self) -> bool:
        """Drapeau explicite du service : ``POKESHOP_DRY_RUN=false`` (le niveau reste contrôlé à part)."""
        return not self.dry_run

    def real_write_blockers(self) -> list[str]:
        """Ce qui manque pour une écriture réelle (liste vide = configuration complète)."""
        out: list[str] = []
        if self.dry_run:
            out.append("POKESHOP_DRY_RUN=true (simulation)")
        if self.shopify_shop_domain is None:
            out.append("POKESHOP_SHOPIFY_SHOP_DOMAIN absent")
        if self.shopify_admin_token is None:
            out.append("POKESHOP_SHOPIFY_ADMIN_TOKEN absent (coffre)")
        if self.shopify_location_id is None:
            out.append("POKESHOP_SHOPIFY_LOCATION_ID absent")
        if not self.agent_tokens_sha256:
            out.append(
                "aucun jeton nommé par rôle (POKESHOP_ROLE_TOKEN_SHA256_<RÔLE> ou POKESHOP_AGENT_TOKENS_SHA256) : "
                "aucune écriture possible"
            )
        if self.owner_token_sha256 is None:
            out.append("POKESHOP_OWNER_TOKEN_SHA256 absent")
        if self.mandate_fingerprint is None:
            out.append("POKESHOP_MANDATE_FINGERPRINT absent (coffre) : mandat inactif, aucune dépense autonome")
        if self.stoploss_fingerprint is None:
            out.append("POKESHOP_STOPLOSS_FINGERPRINT absent (coffre) : seuils du stop-loss non signés")
        if self.rules_fingerprint is None:
            out.append("POKESHOP_RULES_FINGERPRINT absent (coffre) : règles de prix non signées")
        return out

    def public_summary(self) -> dict[str, object]:
        """Résumé sans secret (route ``/health``)."""
        return {
            "env": self.env,
            "dry_run": self.dry_run,
            "vat_profile": self.vat_profile.value,
            "shopify_api_version": self.shopify_api_version,
            "shopify_configured": self.shopify_configured,
            "shopify_test_store": self.shopify_test_store,
            "database_configured": self.database_url is not None,
            "state_backend": self.state_backend,
            "notifications_webhook": self.n8n_webhook_url is not None,
            "notify_dry_run": self.notify_dry_run,
            "api_token_configured": self.api_token_sha256 is not None,
            "owner_token_configured": self.owner_token_sha256 is not None,
            "named_agent_tokens": sorted(self.agent_tokens_sha256),
            "authz_version": AUTHZ_VERSION,
            "mandate_fingerprint_configured": self.mandate_fingerprint is not None,
            "stoploss_fingerprint_configured": self.stoploss_fingerprint is not None,
            "rules_fingerprint_configured": self.rules_fingerprint is not None,
        }


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Construit :class:`Settings` depuis ``environ`` (défaut : ``os.environ``). Valeur vide = absente."""
    env = os.environ if environ is None else environ
    data: dict[str, str] = {}
    origin: dict[str, str] = {}
    for field, names in ENV_VARIABLES.items():
        for name in names:
            raw = env.get(name)
            if raw is not None and raw.strip() != "":
                data[field] = raw.strip()
                origin[field] = name
                break
    per_role = [
        f"{role}:{raw.strip()}" for role, var in ROLE_TOKEN_VARIABLES.items() if (raw := env.get(var)) and raw.strip()
    ]
    if per_role:  # une variable par rôle (documentée dans .env.example), fusionnée avec la liste combinée
        data["agent_tokens_sha256"] = ",".join(filter(None, [data.get("agent_tokens_sha256", ""), *per_role]))
        origin["agent_tokens_sha256"] = "POKESHOP_AGENT_TOKENS_SHA256 / POKESHOP_ROLE_TOKEN_SHA256_*"
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        parts = []
        for err in exc.errors():
            field = str(err["loc"][0]) if err["loc"] else ""
            var = origin.get(field) or (ENV_VARIABLES.get(field, (field,))[0] if field else "configuration")
            parts.append(f"{var} : {err['msg']}")
        raise SettingsError("configuration invalide — " + " ; ".join(parts)) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Configuration du processus (mise en cache ; ``get_settings.cache_clear()`` après changement)."""
    return load_settings()
