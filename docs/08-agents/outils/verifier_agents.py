"""Vérificateur de la flotte d'agents (``docs/08-agents/`` et ``.claude/agents/``).

Contrôles (chacun renvoie la liste des erreurs, vide si tout va bien) :

1. ``check_agent_frontmatter`` : 12 fichiers ``.claude/agents/<agent>.md`` ; frontmatter YAML lisible par
   ``yaml.safe_load`` ; champs ``name``, ``description``, ``tools`` ; nom en kebab-case égal au nom du fichier ;
   description qui dit quand utiliser l'agent ; outils = liste attendue (moindre privilège).
2. ``check_agent_prompts`` : sections obligatoires du prompt, dans l'ordre ; règles clés présentes ; renvoi au brief.
3. ``check_briefs`` : 12 briefs ``NN_<agent>.md`` avec les 9 rubriques du BP §11 + outils, routines, modèle de
   rapport ; outils du brief = outils de l'agent exécutable.
4. ``check_readme_tools`` : tableau des agents du README = outils des agents exécutables.
5. ``check_validation_sections`` : chaque document se termine par « ## Validation humaine requise » avec une case.
6. ``check_raci`` : codes valides, un seul A et au moins un R par ligne ; décomptes cités dans le texte exacts.
7. ``check_autonomy_matrix`` : une fiche par agent (seul / pour validation / interdit / connecteurs).
8. ``check_repo_paths`` : chaque chemin cité existe ou figure « attendu » dans ``CARTE_REPO.md`` ;
   ``check_repo_map_current`` : aucun chemin « attendu » de la carte n'est déjà livré (statut périmé = erreur).
9. ``check_no_secrets`` et ``check_no_fake_identifiers`` : pas de secret, pas d'EAN ni d'email réels.
10. ``check_stoploss_thresholds`` : seuils des six stop-loss présents.
11. ``check_templates`` : gabarit de rapport conforme au brief commun ; registre sans ligne réelle ; modèles
    d'emails tous dotés de la phrase de non-engagement.
12. ``check_secret_permissions`` : ``.claude/settings.json`` existe, ne contient **que** des règles ``deny``
    (aucune règle ``allow`` ni ``ask``), bien formées, dont les règles minimales qui rendent les secrets
    (``.env``, ``secrets/``, coffre local, environnement des processus) illisibles par la flotte, sans bloquer
    ``.env.example`` ; chaque agent porte la règle « Secrets jamais lus ».
13. ``check_qa_read_only`` : le QA n'exécute aucun générateur qui écrit dans le dépôt (seulement via
    ``docs/08-agents/outils/controle_generateurs.py``, qui travaille dans un dossier temporaire).
14. ``check_stale_guidance`` : aucune consigne périmée (statut « attendu » d'un fichier livré, contrôle global
    par ``forecast.north_star(...).frozen``, seuil de gel global à −1 600 CHF, délai de 48 h pour une dépense
    hors mandat que le workflow 08 fait expirer à 24 h, date de G5 réduite à J60).
15. ``check_secret_file_guidance`` : aucun document du dépôt ne fait créer le fichier de secrets **dans** le dépôt
    (``cp .env.example .env``, « Copier en .env », ``--env-file .env``…) : il vit hors du dépôt
    (``/etc/pokeshop/api.env``, ``scripts/compose.sh``), revue SEC-13.
16. ``check_api_routes_documented`` : chaque route de ``engine/pokeshop/api.py`` et ``api_dashboard.py`` est citée
    dans ``docs/SPEC.md`` §2.7 et dans ``BRIEF_COMMUN.md`` §10 (revue NEW-02) ; chaque route réservée à la
    propriétaire figure dans ``INTERVENTIONS_HUMAINES.md``.
17. ``check_role_writes_documented`` : le tableau « Qui détient quel jeton » de ``BRIEF_COMMUN.md`` §10 a une ligne par
    rôle de la matrice (``engine/pokeshop/authz.py``) et ses écritures propres sont exactement celles de la matrice ;
    chaque agent qui a ``CONN-API-MOTEUR`` cite le nom de son jeton (revue R3). Les anciens noms de jeton
    (``agent-12-qa``, ``n8n-NN-…``) et un jeton commun qui « dépose » une valeur sont des consignes périmées (14).

Usage ::

    python docs/08-agents/outils/verifier_agents.py
"""

from __future__ import annotations

import csv
import fnmatch
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]

AGENTS_DIR = Path(".claude") / "agents"
DOCS_DIR = Path("docs") / "08-agents"

BASE_TOOLS = ("Read", "Grep", "Glob")
WRITE_TOOLS = ("Write", "Edit")

# Ordre = numérotation du BP §11. Outils attendus = moindre privilège (README, MATRICE_AUTONOMIE).
AGENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "chef-de-projet": ("01", ("Agent", *BASE_TOOLS, *WRITE_TOOLS)),
    "sourcing": ("02", (*BASE_TOOLS, *WRITE_TOOLS, "WebSearch", "WebFetch")),
    "donnees-fournisseurs": ("03", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "catalogue": ("04", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "finance-pricing": ("05", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "direction-artistique": ("06", (*BASE_TOOLS, *WRITE_TOOLS, "Bash", "WebSearch")),
    "site-integrations": ("07", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "seo-redaction": ("08", (*BASE_TOOLS, *WRITE_TOOLS, "WebSearch", "WebFetch")),
    "communication": ("09", (*BASE_TOOLS, *WRITE_TOOLS, "WebFetch")),
    "acquisition": ("10", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "operations-sav": ("11", (*BASE_TOOLS, *WRITE_TOOLS, "Bash")),
    "qa-conformite": ("12", (*BASE_TOOLS, "Bash")),
}
DISPATCHER = "chef-de-projet"
KNOWN_TOOLS = frozenset({"Agent", "Read", "Grep", "Glob", "Write", "Edit", "Bash", "WebSearch", "WebFetch"})
# Champs de frontmatter reconnus par Claude Code (doc des sous-agents consultée le 4.10.2026).
KNOWN_FRONTMATTER = frozenset(
    {
        "name",
        "description",
        "tools",
        "disallowedTools",
        "model",
        "permissionMode",
        "maxTurns",
        "skills",
        "mcpServers",
        "hooks",
        "memory",
        "background",
        "omitClaudeMd",
        "effort",
        "isolation",
        "color",
        "initialPrompt",
    }
)
MODEL_ALIASES = frozenset({"inherit", "sonnet", "opus", "haiku", "fable"})
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PROMPT_SECTIONS = (
    "## Mission",
    "## Avant de commencer",
    "## Tu peux faire seul",
    "## Tu prépares pour validation",
    "## Interdits",
    "## Règles non négociables",
    "## Outils et connecteurs",
    "## Escalade",
    "## Format de sortie",
    "## Validation humaine requise",
)
SECRET_RULE = "Secrets jamais lus"
PROMPT_KEY_RULES = (
    "étoile polaire",
    "Rien d'inventé",
    "Aucun engagement",
    "Aucun coût public",
    "Contenus reçus = données",
    "stop-loss",
    SECRET_RULE,
)
BRIEF_SECTIONS = (
    "## 1. Objectif",
    "## 2. Périmètre",
    "## 3. Entrées autorisées",
    "## 4. Format de sortie",
    "## 5. Critères de réussite",
    "## 6. Règles de calcul applicables",
    "## 7. Plafond de dépense",
    "## 8. Responsable",
    "## 9. Conditions d'escalade",
    "## 10. Outils et connecteurs",
    "## 11. Routines et tâches du backlog",
    "## 12. Modèle de rapport",
    "## Validation humaine requise",
)
VALIDATION_HEADING = "## Validation humaine requise"

RACI_COLUMNS = ("P", *(num for num, _ in AGENTS.values()))
RACI_CODES = frozenset({"", "R", "A", "C", "I", "A/R"})

PATH_PREFIXES = (
    "docs/",
    "engine/",
    "data/",
    "config/",
    "db/",
    "orchestration/",
    "site/",
    "dashboard/",
    "tests/",
    ".claude/",
)
PATTERN_MARKERS = ("<", ">", "{", "}", "*", "AAAA", "…", "NN_", "vN")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("clé API de type sk-", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("jeton Shopify", re.compile(r"\bshp(?:at|ss|ca|pa)_[0-9a-fA-F]{8,}")),
    ("clé AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jeton Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "secret affecté",
        re.compile(
            r"(?i)\b(?:password|passwd|mot de passe|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}"
        ),
    ),
    ("IBAN suisse", re.compile(r"\bCH\d{2}(?:\s?[0-9A-Z]{4}){4}\s?[0-9A-Z]\b")),
)
EMAIL_RE = re.compile(r"(?<![\w@])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
GTIN13_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")

STOPLOSS_THRESHOLDS = ("12 %", "8 CHF", "25 %", "45 j", "1 600 CHF", "20 %", "60 j")

REPORT_SECTIONS = (
    "## En-tête",
    "## Résumé",
    "## Livrables",
    "## Sources datées",
    "## Hypothèses",
    "## Anomalies",
    "## Contrôles",
    "## Actions externes et dépenses",
    "## Impact sur l'étoile polaire",
    "## Exceptions ouvertes",
    "## Validation humaine requise",
)
REGISTRY_REQUIRED = (
    "date",
    "agent_demandeur",
    "beneficiaire_id",
    "categorie_mandat",
    "montant_chf",
    "plafond_transaction_chf",
    "stoploss_cash_ok",
    "stoploss_global_ok",
    "decision",
    "ref_paiement",
    "cle_idempotence",
    "fictif",
)
NON_ENGAGEMENT_PLACEHOLDER = "{{PHRASE_NON_ENGAGEMENT}}"

# Permissions Claude Code du projet (SEC-13) : uniquement des règles « deny » qui rendent les secrets illisibles.
SETTINGS_FILE = Path(".claude") / "settings.json"
REQUIRED_DENY = (
    "Read(./.env)",
    "Read(**/.env)",
    "Read(**/*.env)",
    "Read(**/secrets/**)",
    "Read(//etc/pokeshop/**)",
    "Read(//proc/*/environ)",
    # Jetons et secrets en clair générés sur l'ordinateur de la propriétaire (revue R6, R5C-DOC-10).
    "Read(~/pokeshop-jetons/**)",
    "Edit(~/pokeshop-jetons/**)",
    "Edit(**/.env)",
    "Edit(**/secrets/**)",
    "Bash(env)",
    "Bash(printenv:*)",
    "Bash(cat .env:*)",
    "Bash(docker compose config:*)",
    "Bash(docker inspect:*)",
)
PERMISSION_RULE_RE = re.compile(r"^(Read|Edit|Bash|WebFetch)\((.+)\)$")
# Fichier sans secret que les agents doivent pouvoir lire (noms des variables).
READABLE_EXAMPLES = (".env.example",)

# QA en lecture seule (COH-08) : générateurs seulement via l'outil de contrôle en dossier temporaire.
QA_FILES = (AGENTS_DIR / "qa-conformite.md", DOCS_DIR / "12_qa-conformite.md")
GENERATOR_RE = re.compile(r"generer_[a-z_]+\.py")
QA_CONTROL_TOOL = "docs/08-agents/outils/controle_generateurs.py"

# Consignes périmées (COH-12, MOT-25, COH-01, COH-13) : motif → correction attendue.
STALE_GUIDANCE: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"north_star\(\.\.\.\)\.frozen"),
        "contrôle global obsolète : le gel global se lit dans pokeshop.stoploss (GET /stoploss/status)",
    ),
    (
        re.compile(r"(?i)stoploss\.py[^\n]{0,60}(?:en attendant|dès (?:sa|leur) livraison|dès qu'ils existent)"),
        "pokeshop.stoploss est livré : plus de contrôle provisoire « en attendant »",
    ),
    (
        re.compile(r"(?i)(?:gel|stop-loss) global[^\n]{0,100}?−\s?1 600"),
        "seuil du gel global obsolète : 20 % du capital engagé de référence (840 CHF avec le point zéro, "
        "STOP_LOSS.md §3)",
    ),
    (
        re.compile(
            r"24 h (?:pour un gate ou (?:un achat|une décision d'achat)|si gate/achat|gate ou achat|achat de stock"
            r"|si achat de stock)"
        ),
        "délai d'une dépense hors mandat : 24 h (expiration du workflow 08, DELEGATION_AUTONOMIE.md §2)",
    ),
    (
        re.compile(r"G5 \(J60\)"),
        "date de G5 incomplète : J60 (option B) / J64 (option A, recommandée), GATES_GO_NO_GO.md G5",
    ),
    (
        re.compile(r"(?i)générateurs en mode contrôle"),
        "les générateurs n'ont pas de mode contrôle : passer par docs/08-agents/outils/controle_generateurs.py",
    ),
    (
        re.compile(r"\bagent-\d{2}-[a-z]|\bn8n-NN-|\bn8n:0\d-"),
        "ancien nom de jeton : le nom d'un jeton est son rôle de la matrice (`qa-conformite`, `n8n-07-stoploss`…, "
        "docs/08-agents/MATRICE_API.md)",
    ),
    (
        re.compile(r"(?i)(?:jeton commun|credential commun)[^\n]{0,80}(?:dépose|déclare|écrit|poste)(?![^\n]{0,40}(?:403|jamais|refus))"),
        "le jeton commun ne fait que lire et simuler : toute écriture lui répond 403 (MATRICE_API.md)",
    ),
)
ATTENDU_RE = re.compile(r"`([^`\n]+)`\s*[,(]?\s*\(?attendu\b")

# Fichier de secrets prescrit DANS le dépôt (SEC-13) : le fichier de variables vit hors du dépôt.
SECRET_FILE_IN_REPO: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcp\s+\.env\.example\s+\.env\b"),
    re.compile(r"(?i)\bcopier en \.env\b"),
    re.compile(r"--env-file[ =]+\.?/?\.env\b"),
    re.compile(r"\benv_file:\s*\.?/?\.env\b"),
    re.compile(r"(?i)\b(?:remplir|renseigner|mettre|placer|ajouter|définir|definir)\b[^\n]{0,60}\bdans\s+`?\.env`?(?![.\w/])"),
)
SECRET_GUIDANCE_GLOBS = ("*.md", "*.yml", "*.yaml", "*.example", "*.sh")
SECRET_GUIDANCE_SKIP = (".git", "tests", "node_modules", "__pycache__", "dist")

# Routes de l'API (NEW-02) : toutes documentées dans SPEC §2.7 et BRIEF_COMMUN §10.
API_FILES = (Path("engine") / "pokeshop" / "api.py", Path("engine") / "pokeshop" / "api_dashboard.py")
ROUTE_DECORATOR_RE = re.compile(r"@(app|router)\.(get|post|put|patch|delete)\(\s*\"([^\"]+)\"")
DASHBOARD_PREFIX = "/dashboard"
SPEC_FILE = Path("docs") / "SPEC.md"
BRIEF_FILE = DOCS_DIR / "BRIEF_COMMUN.md"
INTERVENTIONS_FILE = Path("docs") / "00-pilotage" / "INTERVENTIONS_HUMAINES.md"
# Routes (ou paramètres) réservées au jeton de la propriétaire : chacune a sa fiche dans la checklist maîtresse.
OWNER_ROUTES = (
    "POST /pricing/approvals",
    "POST /catalog/approvals",
    "POST /capital/movements",
    "POST /fx/rates",
    "POST /stoploss/rearm",
    "POST /stoploss/baseline",
    "POST /stoploss/capital-memory/reset",
    "POST /autonomy",
    "POST /incidents/{id}/resume",
    "cap_exceptions",
)


# Matrice d'autorisations (revue R3) : le tableau « Qui détient quel jeton » de BRIEF_COMMUN §10 suit authz.py.
AUTHZ_FILE = Path("engine") / "pokeshop" / "authz.py"
ROLE_TABLE_HEADER = "| Rôle (nom du jeton) | Détenu par | Écritures propres |"
ROUTE_CITE_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9_{}/.-]+)")
NO_TOKEN_MARK = "pas de jeton émis"


# ----------------------------------------------------------------------------------------- utilitaires
def agent_file(slug: str, root: Path = REPO) -> Path:
    """Chemin du fichier exécutable d'un agent."""
    return root / AGENTS_DIR / f"{slug}.md"


def brief_file(slug: str, root: Path = REPO) -> Path:
    """Chemin du brief de mission d'un agent."""
    return root / DOCS_DIR / f"{AGENTS[slug][0]}_{slug}.md"


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Sépare le frontmatter YAML (entre deux lignes ``---``) du corps ; ``None`` si absent."""
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    return (match.group(1), match.group(2)) if match else None


def load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Lit un fichier d'agent : frontmatter (``yaml.safe_load``) et corps.

    Lève ``ValueError`` si le frontmatter est absent ou illisible, ``TypeError`` s'il n'est pas un dictionnaire.
    """
    parts = split_frontmatter(path.read_text(encoding="utf-8"))
    if parts is None:
        raise ValueError("frontmatter absent (le fichier doit commencer par une ligne ---)")
    try:
        data = yaml.safe_load(parts[0])
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter YAML illisible : {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError("frontmatter YAML : un dictionnaire est attendu")
    return data, parts[1]


def split_tools(value: Any) -> list[str]:
    """Découpe le champ ``tools`` (chaîne séparée par des virgules ou liste YAML) sans couper ``Agent(a, b)``."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    items: list[str] = []
    depth, current = 0, ""
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current.strip())
    return items


def tool_name(item: str) -> str:
    """Nom de base d'un outil : ``Agent(a, b)`` → ``Agent``."""
    return item.split("(", 1)[0].strip()


def agent_targets(item: str) -> set[str]:
    """Agents autorisés dans ``Agent(a, b)`` ; ensemble vide pour ``Agent`` sans restriction."""
    match = re.fullmatch(r"Agent\((.*)\)", item.strip())
    return {name.strip() for name in match.group(1).split(",") if name.strip()} if match else set()


def strip_code_blocks(text: str) -> str:
    """Retire les blocs de code délimités par ``` (les titres qu'ils contiennent ne comptent pas)."""
    return re.sub(r"^```.*?^```[^\n]*$", "", text, flags=re.DOTALL | re.MULTILINE)


def h2_headings(text: str) -> list[str]:
    """Titres de niveau 2 hors blocs de code."""
    return [line.rstrip() for line in strip_code_blocks(text).splitlines() if line.startswith("## ")]


def markdown_files(root: Path = REPO) -> list[Path]:
    """Documents Markdown de la flotte (docs/08-agents récursif + agents exécutables)."""
    docs = sorted((root / DOCS_DIR).rglob("*.md"))
    agents = sorted((root / AGENTS_DIR).glob("*.md"))
    return docs + agents


def tools_in(segment: str) -> set[str]:
    """Noms d'outils Claude Code cités dans un segment de texte."""
    return set(re.findall(r"\b(Agent|Read|Grep|Glob|Write|Edit|Bash|WebSearch|WebFetch)\b", segment))


def expected_tool_names(slug: str) -> set[str]:
    """Noms d'outils attendus pour un agent."""
    return set(AGENTS[slug][1])


# ----------------------------------------------------------------------------------------- 1. frontmatter
def check_agent_frontmatter(root: Path = REPO) -> list[str]:
    """Frontmatter YAML de chaque agent exécutable : parsable, complet, outils minimaux."""
    errors: list[str] = []
    present = {p.stem for p in (root / AGENTS_DIR).glob("*.md")}
    for extra in sorted(present - set(AGENTS)):
        errors.append(f".claude/agents/{extra}.md : agent inconnu de la flotte")
    for slug in AGENTS:
        path = agent_file(slug, root)
        where = f".claude/agents/{slug}.md"
        if not path.is_file():
            errors.append(f"{where} : fichier manquant")
            continue
        try:
            data, _ = load_frontmatter(path)
        except (ValueError, TypeError) as exc:
            errors.append(f"{where} : {exc}")
            continue
        for key in ("name", "description", "tools"):
            if key not in data:
                errors.append(f"{where} : champ « {key} » manquant")
        for key in sorted(set(data) - KNOWN_FRONTMATTER):
            errors.append(f"{where} : champ inconnu « {key} »")
        name = data.get("name")
        if not isinstance(name, str) or not KEBAB_RE.fullmatch(name):
            errors.append(f"{where} : name « {name} » n'est pas en kebab-case")
        elif name != slug:
            errors.append(f"{where} : name « {name} » différent du nom de fichier")
        description = data.get("description")
        if not isinstance(description, str) or len(description.strip()) < 80:
            errors.append(f"{where} : description absente ou trop courte (80 caractères minimum)")
        elif "À utiliser" not in description:
            errors.append(f"{where} : la description doit dire quand utiliser l'agent (« À utiliser … »)")
        model = data.get("model")
        if model is not None and not (model in MODEL_ALIASES or str(model).startswith("claude-")):
            errors.append(f"{where} : model « {model} » non reconnu")
        if "tools" in data:
            errors.extend(_check_tools(slug, data["tools"], where))
    return errors


def _check_tools(slug: str, value: Any, where: str) -> list[str]:
    errors: list[str] = []
    items = split_tools(value)
    if not items:
        return [f"{where} : champ tools vide ou illisible"]
    names = [tool_name(item) for item in items]
    for name in names:
        if name not in KNOWN_TOOLS:
            errors.append(f"{where} : outil non autorisé « {name} »")
    if len(names) != len(set(names)):
        errors.append(f"{where} : outil en double")
    expected = expected_tool_names(slug)
    if set(names) != expected:
        missing = sorted(expected - set(names))
        surplus = sorted(set(names) - expected)
        errors.append(
            f"{where} : outils {sorted(set(names))} ≠ attendus {sorted(expected)} (manque {missing}, en trop {surplus})"
        )
    if slug == DISPATCHER:
        agent_items = [item for item in items if tool_name(item) == "Agent"]
        others = set(AGENTS) - {DISPATCHER}
        if agent_items and agent_targets(agent_items[0]) != others:
            errors.append(f"{where} : Agent(...) doit lister exactement les 11 autres agents de la flotte")
    elif "Agent" in names:
        errors.append(f"{where} : seul le chef de projet peut déléguer (outil Agent)")
    if slug in {"sourcing", "seo-redaction", "communication"} and "Bash" in names:
        errors.append(f"{where} : cet agent ne doit pas avoir Bash")
    if slug == "qa-conformite" and {"Write", "Edit"} & set(names):
        errors.append(f"{where} : le QA ne doit avoir ni Write ni Edit")
    return errors


# ----------------------------------------------------------------------------------------- 2. prompts
def check_agent_prompts(root: Path = REPO) -> list[str]:
    """Corps des agents : sections dans l'ordre, règles clés, renvois au brief et au brief commun."""
    errors: list[str] = []
    for slug, (num, _) in AGENTS.items():
        path = agent_file(slug, root)
        if not path.is_file():
            continue  # signalé par check_agent_frontmatter
        parts = split_frontmatter(path.read_text(encoding="utf-8"))
        if parts is None:
            continue
        body = parts[1]
        where = f".claude/agents/{slug}.md"
        errors.extend(_check_ordered_sections(h2_headings(body), PROMPT_SECTIONS, where))
        for rule in PROMPT_KEY_RULES:
            if rule.lower() not in body.lower():
                errors.append(f"{where} : règle clé absente « {rule} »")
        for ref in (
            f"docs/08-agents/{num}_{slug}.md",
            "docs/08-agents/BRIEF_COMMUN.md",
            "docs/08-agents/modeles/RAPPORT_AGENT.md",
        ):
            if ref not in body:
                errors.append(f"{where} : renvoi manquant vers {ref}")
    return errors


def _check_ordered_sections(headings: list[str], required: Iterable[str], where: str) -> list[str]:
    """Chaque section requise apparaît (par préfixe), dans l'ordre."""
    errors: list[str] = []
    position = -1
    for section in required:
        found = next((i for i, h in enumerate(headings) if h.startswith(section) and i > position), None)
        if found is None:
            errors.append(f"{where} : section « {section} » manquante ou hors ordre")
        else:
            position = found
    return errors


# ----------------------------------------------------------------------------------------- 3. briefs
def check_briefs(root: Path = REPO) -> list[str]:
    """Briefs de mission : rubriques du BP §11, renvoi à l'agent exécutable, outils cohérents."""
    errors: list[str] = []
    for slug in AGENTS:
        path = brief_file(slug, root)
        where = f"docs/08-agents/{path.name}"
        if not path.is_file():
            errors.append(f"{where} : brief manquant")
            continue
        text = path.read_text(encoding="utf-8")
        errors.extend(_check_ordered_sections(h2_headings(text), BRIEF_SECTIONS, where))
        if f".claude/agents/{slug}.md" not in text:
            errors.append(f"{where} : renvoi manquant vers .claude/agents/{slug}.md")
        if "docs/08-agents/BRIEF_COMMUN.md" not in text:
            errors.append(f"{where} : renvoi manquant vers le brief commun")
        line = next((ln for ln in text.splitlines() if "Claude Code :" in ln), None)
        if line is None:
            errors.append(f"{where} : ligne « Claude Code : <outils> » absente du §10")
            continue
        segment = line.split("Claude Code :", 1)[1].split("|", 1)[0]
        if tools_in(segment) != expected_tool_names(slug):
            errors.append(
                f"{where} : outils du brief {sorted(tools_in(segment))} ≠ agent {sorted(expected_tool_names(slug))}"
            )
    return errors


# ----------------------------------------------------------------------------------------- 4. README
def check_readme_tools(root: Path = REPO) -> list[str]:
    """Le tableau « Les 12 agents » du README reprend les outils exacts de chaque agent."""
    path = root / DOCS_DIR / "README.md"
    if not path.is_file():
        return ["docs/08-agents/README.md : fichier manquant"]
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| (\d{2}) \| `([a-z-]+)` \|.*\| ([^|]+) \|$", line)
        if match:
            rows[match.group(2)] = tools_in(match.group(3))
    errors = []
    for slug in AGENTS:
        if slug not in rows:
            errors.append(f"README.md : agent {slug} absent du tableau")
        elif rows[slug] != expected_tool_names(slug):
            errors.append(f"README.md : outils de {slug} {sorted(rows[slug])} ≠ {sorted(expected_tool_names(slug))}")
    return errors


# ----------------------------------------------------------------------------------------- 5. validation
def check_validation_sections(paths: Iterable[Path] | None = None, root: Path = REPO) -> list[str]:
    """Chaque document se termine par « ## Validation humaine requise » avec au moins une case."""
    errors: list[str] = []
    for path in paths if paths is not None else markdown_files(root):
        text = path.read_text(encoding="utf-8")
        headings = h2_headings(text)
        label = path.relative_to(root) if path.is_relative_to(root) else path
        if not headings or headings[-1] != VALIDATION_HEADING:
            errors.append(f"{label} : la dernière section n'est pas « Validation humaine requise »")
            continue
        tail = strip_code_blocks(text).rsplit(VALIDATION_HEADING, 1)[1]
        if "- [ ]" not in tail:
            errors.append(f"{label} : aucune case à cocher dans « Validation humaine requise »")
    return errors


# ----------------------------------------------------------------------------------------- 6. RACI
def parse_raci(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Retourne l'en-tête et les lignes du tableau RACI (lignes ``| Lnn |``)."""
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if line.startswith("| # | Livrable |"):
            header = [cell.strip() for cell in line.strip().strip("|").split("|")]
        elif re.match(r"^\| L\d{2} \|", line) and header:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(dict(zip(header, cells, strict=False)) | {"_n": str(len(cells))})
    return header, rows


def check_raci(root: Path = REPO) -> list[str]:
    """RACI : 13 colonnes P + 01..12, codes valides, un seul A et au moins un R ; décomptes cités exacts."""
    path = root / DOCS_DIR / "ORGANIGRAMME.md"
    if not path.is_file():
        return ["ORGANIGRAMME.md : fichier manquant"]
    text = path.read_text(encoding="utf-8")
    header, rows = parse_raci(text)
    errors: list[str] = []
    if tuple(header[3:]) != RACI_COLUMNS:
        errors.append(f"ORGANIGRAMME.md : colonnes RACI {header[3:]} ≠ {list(RACI_COLUMNS)}")
        return errors
    if not rows:
        return ["ORGANIGRAMME.md : tableau RACI vide"]
    owner_a = 0
    for index, row in enumerate(rows, start=1):
        rid = row["#"]
        if rid != f"L{index:02d}":
            errors.append(f"ORGANIGRAMME.md : ligne {rid} hors séquence (attendu L{index:02d})")
        if int(row["_n"]) != len(header):
            errors.append(f"ORGANIGRAMME.md : {rid} a {row['_n']} cellules au lieu de {len(header)}")
            continue
        codes = [row[col] for col in RACI_COLUMNS]
        for col, code in zip(RACI_COLUMNS, codes, strict=True):
            if code not in RACI_CODES:
                errors.append(f"ORGANIGRAMME.md : {rid} colonne {col} code invalide « {code} »")
        accountable = sum(1 for c in codes if c in {"A", "A/R"})
        responsible = sum(1 for c in codes if c in {"R", "A/R"})
        if accountable != 1:
            errors.append(f"ORGANIGRAMME.md : {rid} a {accountable} « A » (exactement 1 attendu)")
        if responsible < 1:
            errors.append(f"ORGANIGRAMME.md : {rid} n'a aucun « R »")
        if row["P"] in {"A", "A/R"}:
            owner_a += 1
    cited = re.search(r"les (\d+) lignes où la propriétaire est \*\*A\*\*", text)
    if cited is None or int(cited.group(1)) != owner_a:
        errors.append(f"ORGANIGRAMME.md : le texte doit citer « les {owner_a} lignes où la propriétaire est **A** »")
    readme = root / DOCS_DIR / "README.md"
    if readme.is_file():
        count = re.search(r"RACI agents × (\d+) livrables", readme.read_text(encoding="utf-8"))
        if count is None or int(count.group(1)) != len(rows):
            errors.append(f"README.md : le texte doit citer « RACI agents × {len(rows)} livrables »")
    return errors


# ----------------------------------------------------------------------------------------- 7. autonomie
def check_autonomy_matrix(root: Path = REPO) -> list[str]:
    """MATRICE_AUTONOMIE : une ligne par agent au §2 et une fiche complète par agent au §3."""
    path = root / DOCS_DIR / "MATRICE_AUTONOMIE.md"
    if not path.is_file():
        return ["MATRICE_AUTONOMIE.md : fichier manquant"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    sections = re.split(r"^### ", text, flags=re.MULTILINE)
    by_num = {s[:4]: s for s in sections if re.match(r"A-\d{2}", s)}
    for slug, (num, _) in AGENTS.items():
        if not re.search(rf"^\| A-{num} ", text, flags=re.MULTILINE):
            errors.append(f"MATRICE_AUTONOMIE.md : A-{num} absent du tableau par niveau (§2)")
        section = by_num.get(f"A-{num}")
        if section is None:
            errors.append(f"MATRICE_AUTONOMIE.md : fiche A-{num} ({slug}) manquante (§3)")
            continue
        for label in (
            "**Peut faire seul**",
            "**Prépare pour validation**",
            "**Interdit**",
            "**Connecteurs et plafonds**",
        ):
            if label not in section:
                errors.append(f"MATRICE_AUTONOMIE.md : fiche A-{num} sans {label}")
    for level in ("**1**", "**2**", "**3**", "**4**"):
        if f"| {level} |" not in text:
            errors.append(f"MATRICE_AUTONOMIE.md : niveau {level} absent du tableau des niveaux")
    return errors


# ----------------------------------------------------------------------------------------- 8. chemins
def parse_repo_map(root: Path = REPO) -> dict[str, str]:
    """Chemins de CARTE_REPO.md et leur statut (« présent » ou « attendu »)."""
    path = root / DOCS_DIR / "CARTE_REPO.md"
    entries: dict[str, str] = {}
    if not path.is_file():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `([^`]+)` \|.*\| (présent|attendu) \|$", line)
        if match:
            entries[match.group(1)] = match.group(2)
    return entries


def cited_paths(paths: Iterable[Path]) -> dict[str, set[str]]:
    """Chemins du dépôt cités entre accents graves, par fichier (motifs et commandes exclus)."""
    found: dict[str, set[str]] = {}
    for path in paths:
        for span in re.findall(r"`([^`\n]+)`", path.read_text(encoding="utf-8")):
            span = span.strip()
            if " " in span or not span.startswith(PATH_PREFIXES) or any(m in span for m in PATTERN_MARKERS):
                continue
            found.setdefault(span, set()).add(path.name)
    return found


def _is_expected(path: str, expected: Iterable[str]) -> bool:
    clean = path.rstrip("/")
    for item in expected:
        base = item.rstrip("/")
        if clean == base or (item.endswith("/") and clean.startswith(base + "/")):
            return True
    return False


def check_repo_paths(root: Path = REPO) -> list[str]:
    """Chaque chemin cité existe ou est « attendu » dans la carte ; chaque « présent » existe."""
    repo_map = parse_repo_map(root)
    errors: list[str] = []
    if not repo_map:
        return ["CARTE_REPO.md : carte absente ou vide"]
    for entry, status in repo_map.items():
        if status == "présent" and not (root / entry).exists():
            errors.append(f"CARTE_REPO.md : « {entry} » marqué présent mais introuvable")
    expected = [entry for entry, status in repo_map.items() if status == "attendu"]
    for path, sources in sorted(cited_paths(markdown_files(root)).items()):
        if (root / path).exists() or _is_expected(path, expected):
            continue
        errors.append(
            f"chemin introuvable et non déclaré « attendu » : {path} (cité dans {', '.join(sorted(sources))})"
        )
    return errors


def stale_expected(root: Path = REPO) -> list[str]:
    """Chemins « attendu » de la carte déjà livrés (statut périmé)."""
    return [entry for entry, status in parse_repo_map(root).items() if status == "attendu" and (root / entry).exists()]


def check_repo_map_current(root: Path = REPO) -> list[str]:
    """Un chemin « attendu » déjà présent est une erreur : la flotte croirait qu'il manque (COH-12)."""
    return [
        f"CARTE_REPO.md : « {entry} » est présent mais marqué « attendu » (passer son statut à « présent »)"
        for entry in stale_expected(root)
    ]


# ----------------------------------------------------------------------------------------- 9. secrets, données
def _flotte_files(root: Path) -> list[Path]:
    files = markdown_files(root) + sorted((root / DOCS_DIR).rglob("*.csv"))
    return files


def check_no_secrets(root: Path = REPO) -> list[str]:
    """Aucun motif de secret (clé, jeton, mot de passe affecté, IBAN) dans les fichiers de la flotte."""
    errors: list[str] = []
    for path in _flotte_files(root):
        text = path.read_text(encoding="utf-8")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path.name} : motif de secret détecté ({label})")
    return errors


def check_no_fake_identifiers(root: Path = REPO) -> list[str]:
    """Aucun EAN-13 hors plage de test 200 ; aucune adresse email réelle (seulement example.* ou {{…}})."""
    errors: list[str] = []
    for path in _flotte_files(root):
        text = path.read_text(encoding="utf-8")
        for code in GTIN13_RE.findall(text):
            if not code.startswith("200"):
                errors.append(f"{path.name} : EAN-13 « {code} » hors plage de test 200")
        for email in EMAIL_RE.findall(text):
            if ".example" not in email and "@example." not in email:
                errors.append(f"{path.name} : adresse email « {email} » (seules les adresses example.* sont admises)")
    return errors


# ----------------------------------------------------------------------------------------- 10. stop-loss
def check_stoploss_thresholds(root: Path = REPO) -> list[str]:
    """Les seuils des six stop-loss figurent dans le brief commun et dans le prompt du QA."""
    errors: list[str] = []
    for rel in (DOCS_DIR / "BRIEF_COMMUN.md", AGENTS_DIR / "qa-conformite.md", DOCS_DIR / "12_qa-conformite.md"):
        path = root / rel
        if not path.is_file():
            errors.append(f"{rel} : fichier manquant")
            continue
        text = path.read_text(encoding="utf-8")
        for threshold in STOPLOSS_THRESHOLDS:
            if threshold not in text:
                errors.append(f"{rel} : seuil de stop-loss « {threshold} » absent")
        if "réarm" not in text.lower():
            errors.append(f"{rel} : la règle de réarmement (propriétaire seule) est absente")
    return errors


# ----------------------------------------------------------------------------------------- 11. gabarits
def check_templates(root: Path = REPO) -> list[str]:
    """Gabarits : rapport conforme au §6 du brief commun, registre sans ligne réelle, emails non engageants."""
    errors: list[str] = []
    models = root / DOCS_DIR / "modeles"
    report = models / "RAPPORT_AGENT.md"
    if report.is_file():
        errors.extend(
            _check_ordered_sections(
                h2_headings(report.read_text(encoding="utf-8")), REPORT_SECTIONS, "RAPPORT_AGENT.md"
            )
        )
    else:
        errors.append("modeles/RAPPORT_AGENT.md : fichier manquant")
    for name in ("FICHE_EXCEPTION.md", "PLAN_DISPATCH.md", "DEMANDE_ENGAGEMENT.md", "MODELES_EMAILS_AGENTS.md"):
        if not (models / name).is_file():
            errors.append(f"modeles/{name} : fichier manquant")
    registry = models / "REGISTRE_MANDAT.csv"
    if registry.is_file():
        with registry.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames or []
            for col in REGISTRY_REQUIRED:
                if col not in fields:
                    errors.append(f"REGISTRE_MANDAT.csv : colonne « {col} » manquante")
            for number, row in enumerate(reader, start=2):
                if str(row.get("fictif", "")).strip().lower() != "true":
                    errors.append(f"REGISTRE_MANDAT.csv : ligne {number} non marquée fictif=true dans le gabarit")
    else:
        errors.append("modeles/REGISTRE_MANDAT.csv : fichier manquant")
    emails = models / "MODELES_EMAILS_AGENTS.md"
    if emails.is_file():
        text = emails.read_text(encoding="utf-8")
        blocks = re.split(r"^### ", text, flags=re.MULTILINE)[1:]
        mods = [b for b in blocks if b.startswith("MOD-0")]
        if len(mods) < 8:
            errors.append(f"MODELES_EMAILS_AGENTS.md : {len(mods)} modèles MOD-0x au lieu de 8")
        for block in mods:
            if NON_ENGAGEMENT_PLACEHOLDER not in block:
                errors.append(f"MODELES_EMAILS_AGENTS.md : {block.split(' ', 1)[0]} sans phrase de non-engagement")
    return errors


# ----------------------------------------------------------------------------------------- 12. permissions
def check_secret_permissions(root: Path = REPO) -> list[str]:
    """``.claude/settings.json`` : uniquement des règles ``deny`` qui rendent les secrets illisibles (SEC-13).

    Fermé par défaut : fichier absent, illisible ou contenant une règle ``allow``/``ask`` = erreur. Les règles
    minimales ``REQUIRED_DENY`` sont exigées ; ``.env.example`` (noms de variables, aucun secret) doit rester
    lisible. Chaque agent exécutable porte la règle « Secrets jamais lus » (contrôlée par ``check_agent_prompts``).
    """
    path = root / SETTINGS_FILE
    where = str(SETTINGS_FILE)
    if not path.is_file():
        return [f"{where} : fichier manquant (aucune règle deny : les secrets restent lisibles par la flotte)"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{where} : JSON illisible ({exc})"]
    if not isinstance(data, dict):
        return [f"{where} : un objet JSON est attendu"]
    errors: list[str] = []
    for key in sorted(set(data) - {"permissions"}):
        errors.append(f"{where} : clé « {key} » non admise (seules des règles permissions.deny sont autorisées)")
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        return [*errors, f"{where} : objet « permissions » absent"]
    for key in sorted(set(permissions) - {"deny"}):
        errors.append(f"{where} : permissions.{key} interdit (aucune règle allow, ask ni mode par défaut)")
    deny = permissions.get("deny")
    if not isinstance(deny, list) or not deny:
        return [*errors, f"{where} : permissions.deny vide ou absent"]
    seen: set[str] = set()
    for rule in deny:
        match = PERMISSION_RULE_RE.fullmatch(rule) if isinstance(rule, str) else None
        if match is None:
            errors.append(f"{where} : règle mal formée « {rule} » (attendu Outil(motif))")
            continue
        if rule in seen:
            errors.append(f"{where} : règle en double « {rule} »")
        seen.add(rule)
        tool, spec = match.groups()
        if tool == "Read":
            pattern = spec.removeprefix("./").removeprefix("**/")
            for name in READABLE_EXAMPLES:
                if fnmatch.fnmatch(name, pattern):
                    errors.append(f"{where} : « {rule} » bloque {name} (sans secret, lu par les agents)")
    for rule in REQUIRED_DENY:
        if rule not in seen:
            errors.append(f"{where} : règle deny minimale absente « {rule} »")
    return errors


# ----------------------------------------------------------------------------------------- 13. QA lecture seule
def check_qa_read_only(root: Path = REPO) -> list[str]:
    """Le QA ne lance aucun générateur qui écrit dans le dépôt : seulement via l'outil de contrôle (COH-08)."""
    errors: list[str] = []
    if not (root / QA_CONTROL_TOOL).is_file():
        errors.append(f"{QA_CONTROL_TOOL} : outil de contrôle des générateurs manquant")
    for rel in QA_FILES:
        path = root / rel
        if not path.is_file():
            continue  # signalé par les autres contrôles
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if GENERATOR_RE.search(line) and "controle_generateurs.py" not in line:
                errors.append(
                    f"{rel}:{number} : générateur cité sans passer par {QA_CONTROL_TOOL} "
                    "(sa sortie par défaut réécrit le dépôt)"
                )
    return errors


# ----------------------------------------------------------------------------------------- 14. consignes périmées
def check_stale_guidance(root: Path = REPO) -> list[str]:
    """Aucune consigne périmée dans la flotte : fichier livré dit « attendu », ancien contrôle ou ancien seuil."""
    errors: list[str] = []
    for path in markdown_files(root):
        label = path.relative_to(root) if path.is_relative_to(root) else path
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern, fix in STALE_GUIDANCE:
                if pattern.search(line):
                    errors.append(f"{label}:{number} : consigne périmée — {fix}")
            for cited in ATTENDU_RE.findall(line):
                if cited.startswith(PATH_PREFIXES) and (root / cited.strip()).exists():
                    errors.append(f"{label}:{number} : « {cited} » est livré mais dit « attendu »")
    return errors


# ----------------------------------------------------------------------------------------- 15. fichier de secrets
def check_secret_file_guidance(root: Path = REPO) -> list[str]:
    """Aucun document ne fait créer le fichier de secrets dans le dépôt (SEC-13).

    Les agents qui ont Bash travaillent dans le dépôt : un ``.env`` à la racine y serait lisible par un script
    (les règles ``deny`` ne sont qu'un filet). Le fichier de variables vit hors du dépôt
    (``sudo install -D -m 600 -o "$USER" .env.example /etc/pokeshop/api.env``) et la pile se lance par ``scripts/compose.sh``.
    """
    errors: list[str] = []
    for pattern_glob in SECRET_GUIDANCE_GLOBS:
        for path in sorted(root.rglob(pattern_glob)):
            rel = path.relative_to(root)
            if any(part in SECRET_GUIDANCE_SKIP for part in rel.parts) or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                for pattern in SECRET_FILE_IN_REPO:
                    if pattern.search(line):
                        errors.append(
                            f"{rel}:{number} : fichier de secrets prescrit dans le dépôt — le créer hors du dépôt "
                            "(/etc/pokeshop/api.env, scripts/compose.sh)"
                        )
    return errors


# ----------------------------------------------------------------------------------------- 16. routes de l'API
def api_routes(root: Path = REPO) -> list[str]:
    """Routes déclarées par l'API du moteur (« GET /health », « POST /pricing/approvals »…)."""
    routes: list[str] = []
    for rel in API_FILES:
        path = root / rel
        if not path.is_file():
            continue
        for kind, method, route in ROUTE_DECORATOR_RE.findall(path.read_text(encoding="utf-8")):
            full = DASHBOARD_PREFIX + route if kind == "router" else route
            routes.append(f"{method.upper()} {full}")
    return routes


def _route_cited(route: str, text: str) -> bool:
    """Route citée avec sa méthode (« POST /stock/receive ») ; un paramètre ``{x}`` peut porter un autre nom."""
    method, path = route.split(" ", 1)
    pattern = re.escape(path)
    pattern = re.sub(r"\\\{[^}]*\\\}", r"\\{[^}]+\\}", pattern)
    return re.search(rf"\b{method}\s+{pattern}(?![\w/-])", text) is not None


def check_api_routes_documented(root: Path = REPO) -> list[str]:
    """Chaque route de l'API est décrite dans SPEC §2.7 et BRIEF_COMMUN §10 ; actes propriétaire dans la checklist."""
    routes = api_routes(root)
    if not routes:
        return []
    errors: list[str] = []
    spec_path, brief_path = root / SPEC_FILE, root / BRIEF_FILE
    spec = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else ""
    spec_section = spec.split("### 2.7", 1)[-1].split("### 2.8", 1)[0]
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    brief_section = brief.split("## 10.", 1)[-1].split("## 11.", 1)[0]
    for route in routes:
        if not _route_cited(route, spec_section):
            errors.append(f"docs/SPEC.md §2.7 : route {route} absente")
        if not _route_cited(route, brief_section):
            errors.append(f"{BRIEF_FILE} §10 : route {route} absente")
    interventions_path = root / INTERVENTIONS_FILE
    if interventions_path.is_file():
        interventions = interventions_path.read_text(encoding="utf-8")
        for act in OWNER_ROUTES:
            if act not in interventions:
                errors.append(f"{INTERVENTIONS_FILE} : acte réservé à la propriétaire « {act} » sans fiche")
    return errors


# ----------------------------------------------------------------------------------------- 17. jetons par rôle
def load_authz(root: Path = REPO) -> Any | None:
    """Module ``engine/pokeshop/authz.py`` du dépôt (bibliothèque standard seulement), ou None s'il manque."""
    path = root / AUTHZ_FILE
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_pokeshop_authz_verif", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses résout les annotations par le module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _route_key(method: str, path: str) -> str:
    """Route normalisée (paramètres ``{x}`` sans nom) pour comparer documentation et matrice."""
    return f"{method} {re.sub(r'{[^}]*}', '{}', path.rstrip('.'))}"


def role_writes(authz: Any) -> dict[str, set[str]]:
    """Rôle -> écritures propres (routes WRITE où le rôle est nommé, hors actes ouverts à tout rôle nommé)."""
    out: dict[str, set[str]] = {role: set() for role in [*authz.AGENT_ROLES, *authz.CONNECTOR_ROLES]}
    for (method, path), rule in authz.ROUTE_MATRIX.items():
        if rule.kind is authz.Kind.WRITE and rule.roles != authz.KNOWN_ROLES:
            for role in rule.roles:
                out[role].add(_route_key(method, path))
    return out


def check_role_writes_documented(root: Path = REPO) -> list[str]:
    """BRIEF_COMMUN §10 : une ligne par rôle de la matrice, écritures propres identiques à ``authz.py``.

    Chaque agent qui a ``CONN-API-MOTEUR`` dans son brief ou son prompt cite aussi le nom de son jeton (`rôle`),
    et un agent marqué « pas de jeton émis » n'a pas ``CONN-API-MOTEUR``.
    """
    authz = load_authz(root)
    if authz is None:
        return []
    errors: list[str] = []
    brief_path = root / BRIEF_FILE
    brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
    section = brief.split("## 10.", 1)[-1].split("## 11.", 1)[0]
    if ROLE_TABLE_HEADER not in section:
        return [f"{BRIEF_FILE} §10 : tableau « {ROLE_TABLE_HEADER} » absent"]
    rows: dict[str, list[str]] = {}
    for line in section.split(ROLE_TABLE_HEADER, 1)[1].splitlines()[2:]:
        if not line.startswith("|"):
            break
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`([a-z0-9-]+)`", cols[0])
        if match:
            rows[match.group(1)] = cols
    expected = role_writes(authz)
    for role, routes in expected.items():
        if role not in rows:
            errors.append(f"{BRIEF_FILE} §10 : rôle `{role}` absent du tableau des jetons")
            continue
        cols = rows[role]
        documented = {_route_key(m, path) for m, path in ROUTE_CITE_RE.findall(cols[2])} if len(cols) > 2 else set()
        for route in sorted(routes - documented):
            errors.append(f"{BRIEF_FILE} §10 : `{role}` — écriture {route} de la matrice absente")
        for route in sorted(documented - routes):
            errors.append(f"{BRIEF_FILE} §10 : `{role}` — {route} citée mais refusée à ce rôle par la matrice")
    for role in sorted(set(rows) - set(expected)):
        errors.append(f"{BRIEF_FILE} §10 : rôle `{role}` inconnu de la matrice (engine/pokeshop/authz.py)")
    for slug in AGENTS:
        no_token = slug in rows and NO_TOKEN_MARK in rows[slug][1]
        for path in (brief_file(slug, root), agent_file(slug, root)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root)
            if "CONN-API-MOTEUR" in text and not no_token and f"`{slug}`" not in text:
                errors.append(f"{rel} : `CONN-API-MOTEUR` sans le nom de son jeton (`{slug}`)")
            if "CONN-API-MOTEUR" in text and no_token and re.search(r"`CONN-API-MOTEUR`[^|\n]*\|", text):
                errors.append(f"{rel} : `CONN-API-MOTEUR` listé alors que BRIEF_COMMUN §10 n'émet pas de jeton à `{slug}`")
    return errors


# ----------------------------------------------------------------------------------------- exécution
ALL_CHECKS: tuple[Callable[..., list[str]], ...] = (
    check_agent_frontmatter,
    check_agent_prompts,
    check_briefs,
    check_readme_tools,
    check_validation_sections,
    check_raci,
    check_autonomy_matrix,
    check_repo_paths,
    check_repo_map_current,
    check_no_secrets,
    check_no_fake_identifiers,
    check_stoploss_thresholds,
    check_templates,
    check_secret_permissions,
    check_qa_read_only,
    check_stale_guidance,
    check_secret_file_guidance,
    check_api_routes_documented,
    check_role_writes_documented,
)


def run_all(root: Path = REPO) -> list[str]:
    """Lance tous les contrôles et concatène les erreurs."""
    errors: list[str] = []
    for check in ALL_CHECKS:
        errors.extend(check(root=root))
    return errors


def main(root: Path = REPO) -> int:
    """Point d'entrée : affiche les erreurs (code 1) ou OK (code 0)."""
    errors = run_all(root)
    for error in errors:
        print(f"ERREUR  {error}")
    if errors:
        print(f"{len(errors)} erreur(s) sur {len(ALL_CHECKS)} contrôles")
        return 1
    print(f"OK — {len(ALL_CHECKS)} contrôles, {len(AGENTS)} agents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
