"""Contrôles de cohérence des livrables legal-ops (docs/04-legal et docs/07-ops).

Contrôles : fichiers attendus ; bandeau « juriste » ; section finale « Validation humaine
requise » ; blocs publics bien formés ; champs ``{{…}}`` tous déclarés et aucun champ orphelin ;
aucune valeur proposée pour un tarif ou un montant non devisé ; hygiène des textes publics
(aucune donnée interne, aucun fournisseur, aucune fausse urgence, aucune adresse réelle) ;
clauses obligatoires des CGV et des autres textes ; checklist LCD ; recette (identifiants,
aucun résultat pré-rempli, synthèse exacte) ; matrice SAV ; catalogue d'incidents ; renvois
entre identifiants ; seuils de stop-loss alignés sur la configuration du moteur ; pré-drop aligné sur le
moteur (phrases de garantie mot pour mot, plafond du supplément, limite par client et fenêtre prioritaire des
paramètres signés) ; chiffres annoncés dans les README ; aperçus à jour.

Usage ::

    python docs/04-legal/outils/verifier_legal_ops.py      # code retour 1 si une anomalie
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import registre_champs as rc
import rendre_textes as rt
import yaml

LEGAL_FILES = (
    "README.md",
    "CGV.md",
    "LIVRAISON_RETOURS.md",
    "PRECOMMANDES.md",
    "CONFIDENTIALITE.md",
    "CONFIDENTIALITE_LANDING.md",
    "MENTIONS_LEGALES.md",
    "COOKIES.md",
    "USAGE_MARQUES.md",
    "CHECKLIST_LCD_ECOMMERCE.md",
)
OPS_FILES = (
    "README.md",
    "SOP_RECEPTION_STOCK.md",
    "SOP_PREPARATION_COLIS.md",
    "SOP_SAV_RETOURS.md",
    "SOP_INCIDENTS.md",
    "ROUTINES_PILOTAGE.md",
    "RECETTE_AVANT_OUVERTURE.md",
    "FAQ_CLIENTS.md",
)
BANNER = "À FAIRE REVOIR PAR UN JURISTE AVANT PUBLICATION"
FINAL_SECTION = "## Validation humaine requise"

#: Champs pour lesquels un agent ne propose jamais de valeur (tarifs, montants à deviser).
NO_PROPOSAL_FIELDS = frozenset(
    {"FRAIS_LIVRAISON", "SEUIL_PORT_OFFERT", "SEUIL_ENVOI_SIGNATURE", "TAUX_HORAIRE_VALORISATION", "DELAI_ACHEMINEMENT"}
)

#: Termes interdits dans les textes publics (données internes, fournisseurs, fausse urgence).
FORBIDDEN_PUBLIC = (
    (re.compile(r"\bmarges?\b", re.I), "terme interne « marge »"),
    (re.compile(r"\bcontribution\b", re.I), "terme interne « contribution »"),
    (re.compile(r"stop-?loss", re.I), "terme interne « stop-loss »"),
    (re.compile(r"\bagents?\b", re.I), "terme interne « agent »"),
    (re.compile(r"co[uû]t (de revient|rendu|historique|de remplacement)", re.I), "coût interne"),
    (re.compile(r"prix d'achat|prix B2B|\bB2B\b", re.I), "prix interne"),
    (re.compile(r"asmodee|matoo|miao|tcg ?distribution|otaku ?world|cardcosmos|carletto", re.I), "nom de fournisseur"),
    (re.compile(r"\bFICTIF", re.I), "donnée fictive"),
    (re.compile(r"\bTODO\b|\bXXX\b|\bTBD\b"), "marqueur de travail"),
    (
        re.compile(
            r"dépêchez|dernière chance|ne ratez pas|à ne pas manquer|valeur sûre|rendement|pépite|plus-value", re.I
        ),
        "fausse urgence ou promesse de valeur",
    ),
    (
        re.compile(r"revendeur (officiel|agréé)|partenaire officiel|distributeur (officiel|agréé)", re.I),
        "revendication d'un statut officiel",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "adresse email en clair (utiliser un champ du registre)"),
    (re.compile(r"\+41\s?\d|\b0\d{2}\s\d{3}\s\d{2}\s\d{2}\b"), "numéro de téléphone en clair"),
    (re.compile(r"\[[A-Z][A-Z0-9_]+\]"), "variable de cas non remplie"),
    (
        re.compile(r"\b(?:une|un)\s+(?:vraie\s+)?(?:personne|humain)\s+(?:vous\s+)?r[ée]pond", re.I),
        "affirmation inexacte sur le service client (réponses courantes automatisées)",
    ),
    (re.compile(r"⟦"), "marque d'aperçu dans un texte source"),
)

#: Phrases ou références obligatoires dans le texte public de chaque document.
REQUIRED_PUBLIC = {
    "CGV.md": (
        "art. 197 ss du Code des obligations",
        "art. 210 CO",
        "droit général de rétractation",
        "uniquement à des adresses en Suisse",
        "francs suisses (CHF)",
        "toutes taxes comprises",
        "Erreur de prix manifeste",
        "Quantités limitées",
        "confirmé par écrit une quantité ferme",
        "Contenu aléatoire",
        "Aucune promesse de valeur",
        "scellé",
        "Le for est à Genève",
        "art. 32 et 35 du Code de procédure civile",
        "CVIM",
        "boutique indépendante",
        "Étapes de la commande",
        "{{MENTION_TVA}}",
        "Annulation de votre part avant préparation",
        "Pré-drop (réservation garantie)",
        "supplément compris",
    ),
    "LIVRAISON_RETOURS.md": (
        "Uniquement en Suisse",
        "art. 197 ss du Code des obligations",
        "droit général de rétractation",
        "non ouvert",
        "{{DELAI_SIGNALEMENT}}",
        "{{FRAIS_LIVRAISON}}",
    ),
    "PRECOMMANDES.md": (
        "par écrit",
        "date estimée",
        "dans l'ordre de leur paiement",
        "remboursé",
        "débité",
        "Pré-drop : la réservation garantie",
        "servies **en premier**",
        "supplément compris",
        "{{LIMITE_RESERVATION_PREDROP}}",
        "{{FENETRE_PRIORITAIRE_PREDROP}}",
    ),
    "CONFIDENTIALITE.md": (
        "LPD",
        "{{RAISON_SOCIALE}}",
        "{{EMAIL_DONNEES}}",
        "art. 16 LPD",
        "art. 21 LPD",
        "art. 24 LPD",
        "art. 25 LPD",
        "PFPDT",
        "désinscription",
        "Communication à l'étranger",
        "Durée de conservation",
        "Réponses facultatives",
        "Panier non finalisé",
        "passage en caisse",
        "{{DUREE_CONSERVATION_PANIER}}",
    ),
    "CONFIDENTIALITE_LANDING.md": (
        "LPD",
        "{{RAISON_SOCIALE}}",
        "{{EMAIL_DONNEES}}",
        "{{DATE_VERSION_LANDING}}",
        "art. 16 LPD",
        "art. 21 LPD",
        "art. 25 LPD",
        "PFPDT",
        "désinscription",
        "Prénom",
        "budget",
        "canton",
        "utm",
        "agrégée",
        "Durée de conservation",
        "aucun cookie",
    ),
    "MENTIONS_LEGALES.md": (
        "{{RAISON_SOCIALE}}",
        "{{ADRESSE_POSTALE}}",
        "{{EMAIL_SUPPORT}}",
        "{{NUMERO_IDE}}",
        "boutique indépendante",
    ),
    "COOKIES.md": ("Refuser", "Paramètres des cookies", "Nécessaires"),
    "USAGE_MARQUES.md": ("Boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus.",),
    "FAQ_CLIENTS.md": ("boutique indépendante", "aléatoire", "uniquement en Suisse", "{{EMAIL_SUPPORT}}"),
}

LCD_OBLIGATIONS = (
    "LCD art. 3 al. 1 let. s ch. 1",
    "LCD art. 3 al. 1 let. s ch. 2",
    "LCD art. 3 al. 1 let. s ch. 3",
    "LCD art. 3 al. 1 let. s ch. 4",
)
S11_URL = "https://www.kmu.admin.ch/fr/obligations-legales-les-lois-suisses-et-europeennes-sur-le-e-commerce"

RECETTE_SECTIONS = "ABCDEFGHIJK"
RECETTE_HEADER = (
    "ID",
    "Bloquant",
    "Appareil",
    "Préconditions",
    "Étapes",
    "Résultat attendu",
    "Résultat obtenu",
    "Statut",
    "Preuve",
)
#: Thèmes du BP §7 qui doivent être couverts par au moins un cas de recette.
RECETTE_TOPICS = {
    "mobile": r"\bMobile\b",
    "ordinateur": r"\bOrdinateur\b",
    "stock simultané": r"en même temps",
    "remise": r"remise",
    "port gratuit": r"Livraison à 0 CHF|livraison offerte",
    "rupture pendant paiement": r"page de paiement",
    "commande mixte": r"stock local \+ précommande",
    "paiement réussi": r"commande créée",
    "paiement refusé": r"refusée",
    "doublon": r"double",
    "remboursement": r"Remboursement",
    "versement": r"versement",
    "emails exacts": r"email de confirmation",
}

SAV_TOPICS = (
    "Perte confirmée",
    "endommagé",
    "Erreur de préparation",
    "Retour volontaire",
    "garantie légale",
    "fraude",
    "Rétrofacturation",
    "contrefaçon",
    "données",
)
INCIDENT_TOPICS = (
    "Prix anormal",
    "Langue ou identité ambiguë",
    "Flux fournisseur absent",
    "Échec de paiement",
    "Marge sous seuil",
    "Survente",
)
INCIDENT_STEPS = ("Détection", "Confinement", "Notification", "Correction", "Test", "Reprise")

ID_PATTERNS = {
    "SAV": re.compile(r"\bSAV-(\d{2})\b"),
    "SAV-M": re.compile(r"\bSAV-M(\d{2})\b"),
    "INC": re.compile(r"\bINC-(\d{2})\b"),
    "R": re.compile(r"\bR-([A-K]\d{2})\b"),
    "L": re.compile(r"\bL-(\d{2})\b"),
}
ID_PREFIXES = {"SAV": "SAV-", "SAV-M": "SAV-M", "INC": "INC-", "R": "R-", "L": "L-"}


@dataclass(frozen=True)
class Context:
    """Emplacements contrôlés (le dépôt réel, ou une copie dans un dossier de test)."""

    root: Path

    @classmethod
    def default(cls) -> Context:
        """Contexte du dépôt."""
        return cls(rc.REPO)

    @property
    def legal(self) -> Path:
        return self.root / "docs" / "04-legal"

    @property
    def ops(self) -> Path:
        return self.root / "docs" / "07-ops"

    @property
    def registry_path(self) -> Path:
        return self.legal / "champs_a_remplir.yaml"

    @property
    def apercu(self) -> Path:
        return self.legal / "apercu"

    @property
    def da_note(self) -> Path:
        return self.root / "docs" / "05-da" / "packaging" / "NOTE_CHIFFRAGE.md"

    @property
    def pricing_config(self) -> Path:
        return self.root / "config" / "pricing_rules.v1.yaml"

    @property
    def predrop_config(self) -> Path:
        return self.root / "config" / "predrop.v1.yaml"

    def owned_docs(self) -> list[Path]:
        """Documents Markdown du périmètre (aperçus générés exclus)."""
        return [self.legal / n for n in LEGAL_FILES] + [self.ops / n for n in OPS_FILES]

    def public_docs(self) -> list[Path]:
        """Documents contenant un bloc public, dans l'ordre du rendu."""
        return [self.root / p.relative_to(rc.REPO) for p in rt.PUBLIC_DOCS]

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")


def _existing(ctx: Context) -> list[Path]:
    return [p for p in ctx.owned_docs() if p.exists()]


def _rel(ctx: Context, path: Path) -> str:
    try:
        return path.relative_to(ctx.root).as_posix()
    except ValueError:
        return str(path)


def _public_text(ctx: Context, path: Path) -> str:
    return "\n".join(rc.public_blocks(ctx.read(path)))


def _table_rows(text: str, first_cell: re.Pattern[str]) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and first_cell.fullmatch(cells[0]):
            rows.append(cells)
    return rows


def _section(text: str, heading_prefix: str) -> str:
    """Texte d'une section ``##`` (jusqu'à la section ``##`` suivante)."""
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.startswith(heading_prefix)
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------- contrôles
def check_expected_files(ctx: Context) -> list[str]:
    """Tous les livrables attendus existent, ainsi que le registre."""
    missing = [_rel(ctx, p) for p in ctx.owned_docs() if not p.exists()]
    if not ctx.registry_path.exists():
        missing.append(_rel(ctx, ctx.registry_path))
    return [f"fichier manquant : {m}" for m in missing]


def check_registry_schema(ctx: Context) -> list[str]:
    """Le registre des champs respecte son schéma."""
    try:
        rc.load_registry(ctx.registry_path)
    except rc.RegistryError as exc:
        return [f"registre : {e}" for e in exc.errors]
    except (OSError, yaml.YAMLError) as exc:
        return [f"registre illisible : {exc}"]
    return []


def check_banner(ctx: Context) -> list[str]:
    """Bandeau « juriste » en tête de chaque document légal et de la FAQ."""
    targets = [ctx.legal / n for n in LEGAL_FILES] + [ctx.ops / "FAQ_CLIENTS.md"]
    errors: list[str] = []
    for path in targets:
        if path.exists() and BANNER not in "\n".join(ctx.read(path).splitlines()[:8]):
            errors.append(f"{_rel(ctx, path)} : bandeau « {BANNER} » absent des 8 premières lignes")
    return errors


def check_final_validation_section(ctx: Context) -> list[str]:
    """La dernière section de chaque document est « Validation humaine requise » avec des cases."""
    errors: list[str] = []
    for path in _existing(ctx):
        text = ctx.read(path)
        headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
        if not headings or headings[-1] != FINAL_SECTION:
            errors.append(f"{_rel(ctx, path)} : la dernière section doit être « {FINAL_SECTION} »")
            continue
        tail = text.split(FINAL_SECTION, 1)[1]
        if "- [ ]" not in tail:
            errors.append(f"{_rel(ctx, path)} : « {FINAL_SECTION} » sans case à cocher")
    return errors


def check_public_blocks(ctx: Context) -> list[str]:
    """Un seul bloc public bien formé dans les documents publiés ; aucun ailleurs."""
    errors: list[str] = []
    for path in _existing(ctx):
        try:
            blocks = rc.public_blocks(ctx.read(path))
        except rc.BlockError as exc:
            errors.append(f"{_rel(ctx, path)} : {exc}")
            continue
        expected = path in ctx.public_docs()
        if expected and len(blocks) != 1:
            errors.append(f"{_rel(ctx, path)} : {len(blocks)} bloc(s) public(s), 1 attendu")
        if not expected and blocks:
            errors.append(f"{_rel(ctx, path)} : bloc public inattendu")
    return errors


def check_placeholders_declared(ctx: Context) -> list[str]:
    """Chaque ``{{CHAMP}}`` utilisé est déclaré dans le registre."""
    try:
        fields = rc.load_registry(ctx.registry_path)
    except (rc.RegistryError, OSError, yaml.YAMLError):
        return ["registre invalide : contrôle des champs impossible"]
    errors: list[str] = []
    for path in _existing(ctx):
        for name in sorted(set(rc.placeholders(ctx.read(path)))):
            if name not in fields:
                errors.append(f"{_rel(ctx, path)} : champ non déclaré {{{{{name}}}}}")
    return errors


def check_registry_fields_used(ctx: Context) -> list[str]:
    """Aucun champ orphelin : chaque champ sert dans un document ou dans un fichier DA."""
    try:
        fields = rc.load_registry(ctx.registry_path)
    except (rc.RegistryError, OSError, yaml.YAMLError):
        return ["registre invalide : contrôle des champs impossible"]
    used: set[str] = set()
    for path in _existing(ctx):
        used.update(rc.placeholders(ctx.read(path)))
    if ctx.da_note.exists():
        used.update(rc.placeholders(ctx.read(ctx.da_note)))
    return [f"champ orphelin (jamais utilisé) : {name}" for name in sorted(set(fields) - used)]


def check_no_invented_amounts(ctx: Context) -> list[str]:
    """Aucune valeur proposée pour un tarif, un seuil de port ou un taux à deviser."""
    try:
        with ctx.registry_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        return [f"registre illisible : {exc}"]
    errors: list[str] = []
    for name in sorted(NO_PROPOSAL_FIELDS):
        raw = (data.get("champs") or {}).get(name)
        if raw is None:
            errors.append(f"{name} : champ attendu absent du registre")
        elif raw.get("valeur_proposee") is not None:
            errors.append(f"{name} : aucune valeur ne doit être proposée (devis ou contrat requis)")
    return errors


def check_da_fields_declared(ctx: Context) -> list[str]:
    """Les champs que la DA attend de l'agent légal sont déclarés dans le registre."""
    if not ctx.da_note.exists():
        return []
    try:
        fields = rc.load_registry(ctx.registry_path)
    except (rc.RegistryError, OSError, yaml.YAMLError):
        return ["registre invalide : contrôle des champs DA impossible"]
    names = set(rc.placeholders(ctx.read(ctx.da_note))) - {"NOM_BOUTIQUE"}
    return [f"champ DA non déclaré dans le registre : {n}" for n in sorted(names - set(fields))]


def check_public_hygiene(ctx: Context) -> list[str]:
    """Textes publics sans donnée interne, fournisseur, fausse urgence ni coordonnée en clair."""
    errors: list[str] = []
    for path in ctx.public_docs():
        if not path.exists():
            continue
        try:
            text = _public_text(ctx, path)
        except rc.BlockError:
            continue
        for pattern, label in FORBIDDEN_PUBLIC:
            for match in pattern.finditer(text):
                errors.append(f"{_rel(ctx, path)} : {label} — « {match.group(0)} »")
    return errors


def check_required_public_clauses(ctx: Context) -> list[str]:
    """Clauses et références obligatoires présentes dans chaque texte public."""
    errors: list[str] = []
    by_name = {p.name: p for p in ctx.public_docs()}
    for name, needles in REQUIRED_PUBLIC.items():
        path = by_name[name]
        if not path.exists():
            continue
        try:
            text = _public_text(ctx, path)
        except rc.BlockError:
            continue
        for needle in needles:
            if needle not in text:
                errors.append(f"{_rel(ctx, path)} : mention obligatoire absente « {needle} »")
    return errors


def check_lcd_checklist(ctx: Context) -> list[str]:
    """Checklist LCD : quatre obligations de l'art. 3 al. 1 let. s, source S11 datée, IDs suivis."""
    path = ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md"
    if not path.exists():
        return []
    text = ctx.read(path)
    errors = [f"checklist : obligation absente « {o} »" for o in LCD_OBLIGATIONS if o not in text]
    if S11_URL not in text:
        errors.append("checklist : URL de la source S11 absente")
    if "4.10.2026" not in text:
        errors.append("checklist : date de consultation (4.10.2026) absente")
    rows = _table_rows(text, re.compile(r"L-\d{2}"))
    ids = [r[0] for r in rows]
    expected = [f"L-{i:02d}" for i in range(1, len(ids) + 1)]
    if ids != expected:
        errors.append(f"checklist : identifiants L-nn non consécutifs ou dupliqués ({ids})")
    for row in rows:
        if row[6] not in {"O", "N"}:
            errors.append(f"checklist : {row[0]} « Bloquant » doit valoir O ou N")
    return errors


def recette_rows(ctx: Context) -> list[list[str]]:
    """Lignes de cas de la recette (cellules nettoyées)."""
    return _table_rows(ctx.read(ctx.ops / "RECETTE_AVANT_OUVERTURE.md"), re.compile(r"R-[A-K]\d{2}"))


def check_recette(ctx: Context) -> list[str]:
    """Recette : identifiants uniques, en-têtes, aucun résultat pré-rempli, synthèse exacte, thèmes BP."""
    path = ctx.ops / "RECETTE_AVANT_OUVERTURE.md"
    if not path.exists():
        return []
    text = ctx.read(path)
    errors: list[str] = []
    header = "| " + " | ".join(RECETTE_HEADER) + " |"
    sections = re.findall(r"^### ([A-K])\. ", text, flags=re.M)
    if sections != list(RECETTE_SECTIONS):
        errors.append(f"recette : sections A à K attendues dans l'ordre ({sections})")
    if text.count(header) != len(RECETTE_SECTIONS):
        errors.append("recette : chaque section doit avoir l'en-tête complet (dont « Résultat obtenu »)")
    rows = recette_rows(ctx)
    ids = [r[0] for r in rows]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        errors.append(f"recette : identifiants dupliqués {dupes}")
    blocking: Counter[str] = Counter()
    for row in rows:
        if len(row) != len(RECETTE_HEADER):
            errors.append(f"recette : {row[0]} a {len(row)} colonnes au lieu de {len(RECETTE_HEADER)}")
            continue
        if row[1] not in {"O", "N"}:
            errors.append(f"recette : {row[0]} « Bloquant » doit valoir O ou N")
        if any(row[6:9]):
            errors.append(f"recette : {row[0]} a un résultat pré-rempli (interdit avant la campagne)")
        if row[1] == "O":
            blocking[row[0][2]] += 1
    for letter in RECETTE_SECTIONS:
        per_section = [i for i in ids if i[2] == letter]
        expected = [f"R-{letter}{n:02d}" for n in range(1, len(per_section) + 1)]
        if per_section != expected:
            errors.append(f"recette : section {letter} non numérotée en continu ({per_section})")
    synth = _table_rows(text, re.compile(r"[A-K]\. .+|\*\*Total\*\*"))
    declared = {r[0][0]: r[1] for r in synth if r[0][0] in RECETTE_SECTIONS and r[0][1] == "."}
    for letter in RECETTE_SECTIONS:
        if declared.get(letter) != str(blocking[letter]):
            errors.append(
                f"recette : synthèse section {letter} = {declared.get(letter)} cas bloquants, "
                f"{blocking[letter]} dans le tableau"
            )
    total = [r for r in synth if r[0] == "**Total**"]
    if not total or total[0][1] != f"**{sum(blocking.values())}**":
        errors.append(f"recette : total de la synthèse différent de {sum(blocking.values())}")
    body = "\n".join(" | ".join(r) for r in rows)
    for topic, pattern in RECETTE_TOPICS.items():
        if not re.search(pattern, body):
            errors.append(f"recette : thème BP §7 non couvert « {topic} »")
    return errors


def check_sav_matrix(ctx: Context) -> list[str]:
    """Matrice SAV : cas consécutifs, modèles existants et tous utilisés, situations du BP couvertes."""
    path = ctx.ops / "SOP_SAV_RETOURS.md"
    if not path.exists():
        return []
    text = ctx.read(path)
    errors: list[str] = []
    rows = _table_rows(text, re.compile(r"SAV-\d{2}"))
    ids = [r[0] for r in rows]
    if ids != [f"SAV-{i:02d}" for i in range(1, len(ids) + 1)]:
        errors.append(f"SAV : cas non consécutifs ({ids})")
    models = re.findall(r"^\*\*(SAV-M\d{2}) ", text, flags=re.M)
    if models != [f"SAV-M{i:02d}" for i in range(1, len(models) + 1)]:
        errors.append(f"SAV : modèles non consécutifs ({models})")
    used = {m for r in rows for m in re.findall(r"SAV-M\d{2}", r[-1])}
    for model in sorted(set(models) - used):
        errors.append(f"SAV : modèle {model} jamais utilisé dans la matrice")
    for model in sorted(used - set(models)):
        errors.append(f"SAV : modèle {model} cité mais non rédigé")
    matrix = "\n".join(" | ".join(r) for r in rows)
    for topic in SAV_TOPICS:
        if topic not in matrix:
            errors.append(f"SAV : situation non couverte « {topic} »")
    return errors


def check_incidents(ctx: Context) -> list[str]:
    """Catalogue d'incidents : codes consécutifs, six types du BP §12, six étapes du workflow."""
    path = ctx.ops / "SOP_INCIDENTS.md"
    if not path.exists():
        return []
    text = ctx.read(path)
    errors: list[str] = []
    rows = _table_rows(text, re.compile(r"INC-\d{2}"))
    ids = [r[0] for r in rows]
    if ids != [f"INC-{i:02d}" for i in range(1, len(ids) + 1)]:
        errors.append(f"incidents : codes non consécutifs ({ids})")
    catalogue = "\n".join(" | ".join(r) for r in rows)
    for topic in INCIDENT_TOPICS:
        if topic not in catalogue:
            errors.append(f"incidents : type BP §12 absent « {topic} »")
    steps = _table_rows(_section(text, "## 2."), re.compile(r"\d\. .+"))
    names = [r[0].split(". ", 1)[1] for r in steps]
    if names != list(INCIDENT_STEPS):
        errors.append(f"incidents : étapes attendues {list(INCIDENT_STEPS)}, trouvées {names}")
    return errors


def _defined_ids(ctx: Context) -> dict[str, set[str]]:
    defined: dict[str, set[str]] = {k: set() for k in ID_PATTERNS}
    sav = ctx.ops / "SOP_SAV_RETOURS.md"
    if sav.exists():
        text = ctx.read(sav)
        defined["SAV"] = {r[0][4:] for r in _table_rows(text, re.compile(r"SAV-\d{2}"))}
        defined["SAV-M"] = set(re.findall(r"^\*\*SAV-M(\d{2}) ", text, flags=re.M))
    inc = ctx.ops / "SOP_INCIDENTS.md"
    if inc.exists():
        defined["INC"] = {r[0][4:] for r in _table_rows(ctx.read(inc), re.compile(r"INC-\d{2}"))}
    if (ctx.ops / "RECETTE_AVANT_OUVERTURE.md").exists():
        defined["R"] = {r[0][2:] for r in recette_rows(ctx)}
    chk = ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md"
    if chk.exists():
        defined["L"] = {r[0][2:] for r in _table_rows(ctx.read(chk), re.compile(r"L-\d{2}"))}
    return defined


def check_cross_references(ctx: Context) -> list[str]:
    """Chaque identifiant cité (SAV, modèle, INC, cas de recette, ligne LCD) existe."""
    defined = _defined_ids(ctx)
    errors: list[str] = []
    for path in _existing(ctx):
        text = ctx.read(path)
        for kind, pattern in ID_PATTERNS.items():
            for ref in sorted(set(pattern.findall(text))):
                if ref not in defined[kind]:
                    errors.append(f"{_rel(ctx, path)} : renvoi vers {ID_PREFIXES[kind]}{ref} introuvable")
    return errors


def check_internal_paths(ctx: Context) -> list[str]:
    """Les chemins cités vers docs/04-legal et docs/07-ops existent."""
    errors: list[str] = []
    pattern = re.compile(r"`(docs/0[47]-[a-z]+/[^`#\s]+)")
    for path in _existing(ctx):
        for ref in sorted(set(pattern.findall(ctx.read(path)))):
            target = ctx.root / ref.rstrip("/")
            if not target.exists():
                errors.append(f"{_rel(ctx, path)} : chemin introuvable `{ref}`")
    return errors


def _pct(value: str) -> str:
    return f"{(Decimal(value) * 100).normalize():f} %"


def stoploss_expectations(ctx: Context) -> list[str]:
    """Seuils de stop-loss attendus, tirés de la configuration du moteur et du module trésorerie."""
    with ctx.pricing_config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    floor_chf = Decimal(cfg["pricing"]["hard_floor_chf_per_order"]).normalize()
    expected = [
        _pct(cfg["pricing"]["hard_floor_margin"]),
        f"{floor_chf:f} CHF",
        _pct(cfg["stock"]["extension_budget_cap"]),
    ]
    engine = str(rc.REPO / "engine")
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from pokeshop.treasury import CASH_STOPLOSS_RESERVE

    reserve = f"{int(CASH_STOPLOSS_RESERVE):,}".replace(",", " ")
    expected.append(f"{reserve} CHF")
    return expected


def check_stoploss_alignment(ctx: Context) -> list[str]:
    """Les seuils de stop-loss cités sont ceux du moteur (12 %, 8 CHF, 25 %, 1 600 CHF) et du mandat."""
    path = ctx.ops / "SOP_INCIDENTS.md"
    if not path.exists():
        return []
    try:
        expected = stoploss_expectations(ctx)
    except (OSError, KeyError, ImportError, yaml.YAMLError) as exc:
        return [f"stop-loss : configuration du moteur illisible ({exc})"]
    table = _section(ctx.read(path), "## 6.")
    errors = [f"SOP_INCIDENTS §6 : seuil « {v} » absent" for v in expected if v not in table]
    for mandate_value in ("45 jours", "20 % du capital engagé", "60 jours", "7 jours glissants"):
        if mandate_value not in table:
            errors.append(f"SOP_INCIDENTS §6 : seuil du mandat « {mandate_value} » absent")
    routines = ctx.ops / "ROUTINES_PILOTAGE.md"
    if routines.exists() and expected[-1] not in ctx.read(routines):
        errors.append(f"ROUTINES_PILOTAGE : réserve « {expected[-1]} » absente")
    return errors


#: Textes publics qui expliquent le pré-drop (garantie mot pour mot, plafond du supplément, statuts sans compte à rebours).
PREDROP_DOCS = ("PRECOMMANDES.md", "CGV.md", "FAQ_CLIENTS.md")
#: Champs du registre alignés sur les paramètres signés du pré-drop : (champ, clé de ``config/predrop.v1.yaml``, gabarit).
PREDROP_FIELDS = (
    ("LIMITE_RESERVATION_PREDROP", "per_customer_limit", "{n} réservation"),
    ("FENETRE_PRIORITAIRE_PREDROP", "priority_window_hours", "{n} heures"),
    ("DELAI_ANNULATION_PREDROP", "free_cancellation_days_before_drop", "jusqu'à {n} jours avant la date du drop"),
)


def predrop_expectations() -> tuple[str, str, str]:
    """(garantie, absence de remboursement de la différence, plafond du supplément « 10 % ») tirés du moteur."""
    engine = str(rc.REPO / "engine")
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from pokeshop.predrop import GUARANTEE_TEXT_FR, MAX_PREMIUM_PCT, NO_DIFFERENCE_REFUND_FR

    return GUARANTEE_TEXT_FR, NO_DIFFERENCE_REFUND_FR, _pct(str(MAX_PREMIUM_PCT))


def check_predrop_alignment(ctx: Context) -> list[str]:
    """Pré-drop : phrases de garantie du moteur mot pour mot, plafond du supplément, champs = paramètres signés."""
    try:
        guarantee, no_difference, cap = predrop_expectations()
    except ImportError as exc:  # pragma: no cover - moteur toujours présent dans le dépôt
        return [f"pré-drop : moteur illisible ({exc})"]
    errors: list[str] = []
    by_name = {p.name: p for p in ctx.public_docs()}
    for name in PREDROP_DOCS:
        path = by_name.get(name)
        if path is None or not path.exists():
            continue
        try:
            text = _public_text(ctx, path)
        except rc.BlockError:
            continue
        for phrase, label in ((guarantee, "garantie"), (no_difference, "aucun remboursement de la différence")):
            if phrase not in text:
                errors.append(f"{_rel(ctx, path)} : phrase du moteur ({label}) absente ou modifiée : « {phrase} »")
        if f"{cap} au plus" not in text and f"plus de {cap}" not in text:
            errors.append(f"{_rel(ctx, path)} : plafond du supplément du moteur ({cap}) absent")
        if re.search(r"compte à rebours|minuteur (?:de|avant)|plus que \d", text, re.I):
            errors.append(f"{_rel(ctx, path)} : fausse urgence dans la présentation du pré-drop")
    precommandes = by_name.get("PRECOMMANDES.md")
    if precommandes is not None and precommandes.exists():
        text = _public_text(ctx, precommandes)
        for status in ("Réservations ouvertes", "Réservations fermées"):
            if status not in text:
                errors.append(f"{_rel(ctx, precommandes)} : statut public « {status} » absent")
    try:
        with ctx.predrop_config.open(encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        fields = rc.load_registry(ctx.registry_path)
    except (OSError, yaml.YAMLError, rc.RegistryError) as exc:
        return errors + [f"pré-drop : paramètres ou registre illisibles ({exc})"]
    for field, key, template in PREDROP_FIELDS:
        spec = fields.get(field)
        value = spec.value if spec is not None else None
        expected = template.format(n=cfg.get(key))
        if not value or not str(value).startswith(expected):
            errors.append(
                f"registre : {field} = {value!r} ne commence pas par « {expected} » (config/predrop.v1.yaml {key} = "
                f"{cfg.get(key)!r}) : aligner puis signer à nouveau les paramètres"
            )
    return errors


def check_readme_counts(ctx: Context) -> list[str]:
    """Les chiffres annoncés dans les README correspondent aux documents."""
    errors: list[str] = []
    readme = ctx.ops / "README.md"
    if readme.exists():
        text = ctx.read(readme)
        sav = ctx.ops / "SOP_SAV_RETOURS.md"
        if sav.exists():
            sav_text = ctx.read(sav)
            n_cases = len(_table_rows(sav_text, re.compile(r"SAV-\d{2}")))
            n_models = len(re.findall(r"^\*\*SAV-M\d{2} ", sav_text, flags=re.M))
            if f"Matrice de {n_cases} cas" not in text:
                errors.append(f"07-ops/README : nombre de cas SAV différent de {n_cases}")
            if f"{n_models} modèles de réponse" not in text:
                errors.append(f"07-ops/README : nombre de modèles différent de {n_models}")
        inc = ctx.ops / "SOP_INCIDENTS.md"
        if inc.exists():
            n_inc = len(_table_rows(ctx.read(inc), re.compile(r"INC-\d{2}")))
            if f"INC-01 à INC-{n_inc:02d}" not in text:
                errors.append(f"07-ops/README : catalogue différent de INC-01 à INC-{n_inc:02d}")
        if (ctx.ops / "RECETTE_AVANT_OUVERTURE.md").exists():
            rows = recette_rows(ctx)
            n_block = sum(1 for r in rows if len(r) > 1 and r[1] == "O")
            if f"{len(rows)} cas de test ({n_block} bloquants)" not in text:
                errors.append(f"07-ops/README : recette différente de {len(rows)} cas ({n_block} bloquants)")
    legal_readme = ctx.legal / "README.md"
    chk = ctx.legal / "CHECKLIST_LCD_ECOMMERCE.md"
    if legal_readme.exists() and chk.exists():
        n_lcd = len(_table_rows(ctx.read(chk), re.compile(r"L-\d{2}")))
        if f"{n_lcd} obligations" not in ctx.read(legal_readme):
            errors.append(f"04-legal/README : nombre d'obligations différent de {n_lcd}")
    return errors


def check_previews_up_to_date(ctx: Context) -> list[str]:
    """Les aperçus générés correspondent aux sources et au registre."""
    docs = [p for p in ctx.public_docs() if p.exists()]
    if len(docs) != len(rt.PUBLIC_DOCS):
        return []
    try:
        fields = rc.load_registry(ctx.registry_path)
        previews = rt.build_previews(docs, fields, rt.registry_version(ctx.registry_path), repo=ctx.root)
    except (rc.RegistryError, rc.RenderError, rc.BlockError, OSError, yaml.YAMLError) as exc:
        return [f"aperçus : rendu impossible ({exc})"]
    return rt.stale_previews(previews, ctx.apercu)


ALL_CHECKS: tuple[Callable[[Context], list[str]], ...] = (
    check_expected_files,
    check_registry_schema,
    check_banner,
    check_final_validation_section,
    check_public_blocks,
    check_placeholders_declared,
    check_registry_fields_used,
    check_no_invented_amounts,
    check_da_fields_declared,
    check_public_hygiene,
    check_required_public_clauses,
    check_lcd_checklist,
    check_recette,
    check_sav_matrix,
    check_incidents,
    check_cross_references,
    check_internal_paths,
    check_stoploss_alignment,
    check_predrop_alignment,
    check_readme_counts,
    check_previews_up_to_date,
)


def run_all(ctx: Context | None = None, checks: Iterable[Callable[[Context], list[str]]] = ALL_CHECKS) -> list[str]:
    """Exécute les contrôles et renvoie toutes les anomalies, préfixées par le contrôle."""
    ctx = ctx or Context.default()
    errors: list[str] = []
    for check in checks:
        errors.extend(f"[{check.__name__}] {e}" for e in check(ctx))
    return errors


def main() -> int:
    """Point d'entrée : affiche les anomalies, code 1 s'il y en a."""
    errors = run_all()
    for err in errors:
        print(err)
    print(f"OK : {len(ALL_CHECKS)} contrôles passés" if not errors else f"{len(errors)} anomalie(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
