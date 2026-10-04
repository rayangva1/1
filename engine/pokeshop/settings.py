"""Configuration du service d'intégration lue dans les variables d'environnement (agent integrations).

* **Aucun secret en dur** : jetons et URL de base viennent du coffre via l'environnement
  (fichier ``.env`` local ignoré par git, ou variables du conteneur). Les secrets sont des
  :class:`pydantic.SecretStr` : jamais affichés par ``repr`` ni journalisés.
* Les jetons d'API et de la propriétaire ne sont **jamais** stockés en clair : seule leur
  empreinte sha256 est configurée (``POKESHOP_API_TOKEN_SHA256``,
  ``POKESHOP_OWNER_TOKEN_SHA256``). Les deux empreintes doivent différer (jetons distincts).
* **Simulation par défaut** (SPEC §0.6) : ``POKESHOP_DRY_RUN`` vaut ``true`` tant qu'il n'est
  pas explicitement mis à ``false`` ; une écriture réelle exige en plus le niveau d'autonomie
  adéquat (:mod:`pokeshop.autonomy`).
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

from .errors import PokeshopError
from .models import FrozenModel, VatMode

__all__ = [
    "REPO_ROOT",
    "DEFAULT_SHOPIFY_API_VERSION",
    "ENV_VARIABLES",
    "SettingsError",
    "Settings",
    "load_settings",
    "get_settings",
    "sha256_hex",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHOPIFY_API_VERSION = "2026-10"
"""Version stable de l'Admin API publiée le 1.10.2026 (index de recherche shopify.dev, consulté le 4.10.2026)."""

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$")
_API_VERSION_RE = re.compile(r"^(\d{4}-(01|04|07|10)|unstable)$")
_LOCATION_RE = re.compile(r"^gid://shopify/Location/\d+$")

ENV_VARIABLES: dict[str, tuple[str, ...]] = {
    "env": ("POKESHOP_ENV",),
    "dry_run": ("POKESHOP_DRY_RUN",),
    "vat_profile": ("POKESHOP_VAT_PROFILE",),
    "timezone": ("POKESHOP_TIMEZONE",),
    "rules_path": ("POKESHOP_RULES_PATH",),
    "stoploss_path": ("POKESHOP_STOPLOSS_PATH",),
    "mandate_path": ("POKESHOP_MANDATE_PATH",),
    "mandate_fingerprint": ("POKESHOP_MANDATE_FINGERPRINT",),
    "owner_token_sha256": ("POKESHOP_OWNER_TOKEN_SHA256",),
    "api_token_sha256": ("POKESHOP_API_TOKEN_SHA256",),
    "shopify_shop_domain": ("POKESHOP_SHOPIFY_SHOP_DOMAIN",),
    "shopify_api_version": ("POKESHOP_SHOPIFY_API_VERSION",),
    "shopify_admin_token": ("POKESHOP_SHOPIFY_ADMIN_TOKEN", "SHOPIFY_ADMIN_TOKEN"),
    "shopify_location_id": ("POKESHOP_SHOPIFY_LOCATION_ID",),
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
    "imports_dir": ("POKESHOP_IMPORTS_DIR",),
}
"""Champ de :class:`Settings` -> variables d'environnement acceptées (la première présente gagne)."""


class SettingsError(PokeshopError, ValueError):
    """Configuration invalide : le message cite les variables d'environnement concernées."""


def sha256_hex(value: str) -> str:
    """Empreinte sha256 hexadécimale d'un jeton (comparée en temps constant par l'appelant)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    owner_token_sha256: str | None = None
    api_token_sha256: str | None = None
    shopify_shop_domain: str | None = None
    shopify_api_version: str = DEFAULT_SHOPIFY_API_VERSION
    shopify_admin_token: SecretStr | None = None
    shopify_location_id: str | None = None
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
    imports_dir: Path = REPO_ROOT / "data" / "samples"
    """Seul dossier lisible par la route ``/imports/{supplier}/run`` (pas de chemin arbitraire)."""

    @field_validator("owner_token_sha256", "api_token_sha256", "mandate_fingerprint")
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
        if self.shopify_backoff_max_ms < self.shopify_backoff_base_ms:
            raise ValueError("POKESHOP_SHOPIFY_BACKOFF_MAX_MS < POKESHOP_SHOPIFY_BACKOFF_BASE_MS")
        return self

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
        if self.api_token_sha256 is None:
            out.append("POKESHOP_API_TOKEN_SHA256 absent")
        if self.owner_token_sha256 is None:
            out.append("POKESHOP_OWNER_TOKEN_SHA256 absent")
        return out

    def public_summary(self) -> dict[str, object]:
        """Résumé sans secret (route ``/health``)."""
        return {
            "env": self.env,
            "dry_run": self.dry_run,
            "vat_profile": self.vat_profile.value,
            "shopify_api_version": self.shopify_api_version,
            "shopify_configured": self.shopify_configured,
            "database_configured": self.database_url is not None,
            "notifications_webhook": self.n8n_webhook_url is not None,
            "notify_dry_run": self.notify_dry_run,
            "api_token_configured": self.api_token_sha256 is not None,
            "owner_token_configured": self.owner_token_sha256 is not None,
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
