"""Registre des champs ``{{…}}`` des textes légaux et des SOP, et rendu des blocs publics.

Un champ est déclaré une seule fois dans ``docs/04-legal/champs_a_remplir.yaml`` avec un
statut (``a_remplir``, ``a_valider``, ``valide``). Les documents ne contiennent que des
``{{CHAMP}}`` ; ce module les remplace :

* mode *aperçu* : valeur validée telle quelle, valeur proposée suivie de ``⟦à valider⟧``,
  champ sans valeur remplacé par ``⟦À REMPLIR : CHAMP⟧`` ;
* mode *publication* : refuse (``RenderError``) tant qu'un champ utilisé n'est pas ``valide``.

Seul le texte situé entre ``<!-- TEXTE_PUBLIC:DEBUT -->`` et ``<!-- TEXTE_PUBLIC:FIN -->``
est destiné au site.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
LEGAL_DIR = REPO / "docs" / "04-legal"
OPS_DIR = REPO / "docs" / "07-ops"
REGISTRY_PATH = LEGAL_DIR / "champs_a_remplir.yaml"

PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+)\}\}")
FIELD_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PUBLIC_START = "<!-- TEXTE_PUBLIC:DEBUT -->"
PUBLIC_END = "<!-- TEXTE_PUBLIC:FIN -->"
MARK_TO_VALIDATE = "⟦à valider⟧"
MAX_NESTING = 5
PROSE_ELLIPSIS = "…"

ALLOWED_KEYS = frozenset(
    {"description", "statut", "valeur_proposee", "valeur", "valide_par", "decideur", "source", "alias_de"}
)


class RegistryError(ValueError):
    """Registre invalide (schéma, statut, alias)."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class RenderError(ValueError):
    """Rendu impossible (champ inconnu, non validé en publication, imbrication cyclique)."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = sorted(set(errors))
        super().__init__("; ".join(self.errors))


class BlockError(ValueError):
    """Balises de bloc public absentes, imbriquées ou déséquilibrées."""


class Status(StrEnum):
    """Statut d'un champ du registre."""

    A_REMPLIR = "a_remplir"
    A_VALIDER = "a_valider"
    VALIDE = "valide"


class Mode(StrEnum):
    """Mode de rendu."""

    APERCU = "apercu"
    PUBLICATION = "publication"


@dataclass(frozen=True)
class Field:
    """Un champ du registre."""

    name: str
    description: str
    status: Status
    value: str | None
    decideur: str
    source: str
    alias_of: str | None = None
    validated_by: str | None = None


def _parse_field(name: str, raw: Any) -> tuple[Field | None, list[str]]:
    errors: list[str] = []
    if not FIELD_NAME_RE.match(name):
        errors.append(f"{name} : nom invalide (majuscules, chiffres et _ uniquement)")
    if not isinstance(raw, dict):
        return None, [*errors, f"{name} : la définition doit être un dictionnaire"]
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        errors.append(f"{name} : clés inconnues {unknown}")
    for key in ("description", "decideur", "source"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            errors.append(f"{name} : « {key} » manquant ou vide")
    proposed, final = raw.get("valeur_proposee"), raw.get("valeur")
    for key, val in (("valeur_proposee", proposed), ("valeur", final)):
        if val is not None and (not isinstance(val, str) or not val.strip()):
            errors.append(f"{name} : « {key} » doit être un texte non vide")
    alias = raw.get("alias_de")
    if alias is not None:
        # Un alias reprend la valeur et le statut de sa cible : il n'en porte aucun.
        if not isinstance(alias, str) or not alias.strip():
            errors.append(f"{name} : « alias_de » doit être un nom de champ")
        for key in ("statut", "valeur_proposee", "valeur", "valide_par"):
            if key in raw:
                errors.append(f"{name} : un alias ne porte pas de « {key} »")
        status = Status.A_REMPLIR  # remplacé par le statut de la cible dans parse_registry
        value: str | None = None
    else:
        if "statut" not in raw:
            return None, [*errors, f"{name} : « statut » manquant"]
        try:
            status = Status(str(raw["statut"]))
        except ValueError:
            return None, [*errors, f"{name} : statut « {raw.get('statut')} » inconnu"]
        value = None
        if status is Status.A_REMPLIR:
            if proposed is not None or final is not None:
                errors.append(f"{name} : statut a_remplir sans valeur (sinon a_valider)")
        elif status is Status.A_VALIDER:
            if proposed is None:
                errors.append(f"{name} : statut a_valider sans valeur_proposee")
            if final is not None:
                errors.append(f"{name} : « valeur » réservée au statut valide")
            value = proposed
        else:
            if final is None:
                errors.append(f"{name} : statut valide sans « valeur »")
            if not isinstance(raw.get("valide_par"), str) or not raw["valide_par"].strip():
                errors.append(f"{name} : statut valide sans « valide_par » (qui, quand)")
            value = final
    if errors:
        return None, errors
    return (
        Field(
            name=name,
            description=raw["description"].strip(),
            status=status,
            value=value.strip() if value else None,
            decideur=raw["decideur"].strip(),
            source=raw["source"].strip(),
            alias_of=alias.strip() if alias else None,
            validated_by=raw.get("valide_par"),
        ),
        [],
    )


def parse_registry(data: Any) -> dict[str, Field]:
    """Valide le contenu YAML déjà chargé et renvoie les champs par nom."""
    if not isinstance(data, dict) or not isinstance(data.get("champs"), dict) or not data["champs"]:
        raise RegistryError(["le registre doit contenir une section « champs » non vide"])
    fields: dict[str, Field] = {}
    errors: list[str] = []
    for name, raw in data["champs"].items():
        field, errs = _parse_field(str(name), raw)
        errors.extend(errs)
        if field is not None:
            fields[field.name] = field
    for field in fields.values():
        if field.alias_of is None:
            continue
        target = fields.get(field.alias_of)
        if target is None:
            errors.append(f"{field.name} : alias vers un champ inconnu « {field.alias_of} »")
        elif target.alias_of is not None:
            errors.append(f"{field.name} : alias d'un alias interdit")
        else:
            fields[field.name] = replace(field, status=target.status, value=target.value)
    if errors:
        raise RegistryError(errors)
    return fields


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Field]:
    """Charge et valide le registre YAML."""
    with path.open(encoding="utf-8") as fh:
        return parse_registry(yaml.safe_load(fh))


def placeholders(text: str) -> list[str]:
    """Noms des champs ``{{…}}`` d'un texte, dans l'ordre d'apparition (doublons inclus).

    ``{{…}}`` (points de suspension) désigne les champs en général dans la prose : ignoré.
    """
    names = (m.group(1).strip() for m in PLACEHOLDER_RE.finditer(text))
    return [n for n in names if n != PROSE_ELLIPSIS]


def public_blocks(text: str) -> list[str]:
    """Blocs publics d'un document ; lève ``BlockError`` si les balises sont mal formées."""
    blocks: list[str] = []
    pos = 0
    while True:
        start = text.find(PUBLIC_START, pos)
        end = text.find(PUBLIC_END, pos)
        if start == -1 and end == -1:
            return blocks
        if start == -1 or (end != -1 and end < start):
            raise BlockError("balise de fin sans balise de début")
        body_start = start + len(PUBLIC_START)
        end = text.find(PUBLIC_END, body_start)
        if end == -1:
            raise BlockError("balise de début sans balise de fin")
        nested = text.find(PUBLIC_START, body_start)
        if nested != -1 and nested < end:
            raise BlockError("blocs publics imbriqués")
        blocks.append(text[body_start:end].strip("\n"))
        pos = end + len(PUBLIC_END)


def _field_value(field: Field, fields: Mapping[str, Field]) -> Field:
    return fields[field.alias_of] if field.alias_of else field


def render(text: str, fields: Mapping[str, Field], mode: Mode = Mode.APERCU) -> str:
    """Remplace les champs d'un texte selon le mode ; lève ``RenderError`` en cas de problème."""
    errors: list[str] = []

    def expand(segment: str, depth: int, chain: tuple[str, ...]) -> str:
        def repl(match: re.Match[str]) -> str:
            name = match.group(1).strip()
            if name == PROSE_ELLIPSIS:
                return match.group(0)
            field = fields.get(name)
            if field is None:
                errors.append(f"champ inconnu : {name}")
                return match.group(0)
            if name in chain or depth >= MAX_NESTING:
                errors.append(f"imbrication cyclique ou trop profonde : {' > '.join((*chain, name))}")
                return match.group(0)
            source = _field_value(field, fields)
            if source.value is None:
                if mode is Mode.PUBLICATION:
                    errors.append(f"champ non validé : {name}")
                    return match.group(0)
                return f"⟦À REMPLIR : {name}⟧"
            if mode is Mode.PUBLICATION and source.status is not Status.VALIDE:
                errors.append(f"champ non validé : {name}")
                return match.group(0)
            inner = expand(source.value, depth + 1, (*chain, name))
            if source.status is Status.A_VALIDER:
                return f"{inner} {MARK_TO_VALIDATE}"
            return inner

        return PLACEHOLDER_RE.sub(repl, segment)

    result = expand(text, 0, ())
    if errors:
        raise RenderError(errors)
    return result


def render_public(text: str, fields: Mapping[str, Field], mode: Mode = Mode.APERCU) -> str:
    """Rend uniquement les blocs publics d'un document (séparés par une ligne vide)."""
    blocks = public_blocks(text)
    if not blocks:
        raise BlockError("aucun bloc public")
    return "\n\n".join(render(block, fields, mode) for block in blocks) + "\n"
