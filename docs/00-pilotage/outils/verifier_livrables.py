"""Vérifie la cohérence des livrables de pilotage, marché et sourcing (docs/00 à 02).

Contrôles : schéma et intégrité du backlog (dépendances existantes, sans cycle), tracker de
contacts (aucun contact marqué établi), grille concurrence (aucun prix sans lecture datée),
panier pilote (15-25 références, 8-12 en stock), enveloppes d'assortiment (plafond 25 % par
extension), emails fournisseurs (liste BP §2 complète, relances J+5 et J+12), gates G0-G7,
références croisées BL-nnn, et section finale « Validation humaine requise » de chaque document.

Usage ::

    python docs/00-pilotage/outils/verifier_livrables.py      # code retour 1 si une anomalie
"""

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Iterable, Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PILOTAGE = REPO / "docs" / "00-pilotage"
MARCHE = REPO / "docs" / "01-marche"
SOURCING = REPO / "docs" / "02-sourcing"
OWNED_DIRS = (PILOTAGE, MARCHE, SOURCING)
# Documents Markdown de ce périmètre. Les autres fichiers des mêmes dossiers (par exemple ceux de
# l'agent gouvernance : DELEGATION_AUTONOMIE.md, ETOILE_POLAIRE.md, STOP_LOSS.md) ne sont pas contrôlés ici.
OWNED_MD = {
    "PILOTAGE": (
        "PLAN_90_JOURS.md",
        "GATES_GO_NO_GO.md",
        "INTERVENTIONS_HUMAINES.md",
        "REGISTRE_RISQUES.md",
        "ECARTS_BP.md",
        "README.md",
    ),
    "MARCHE": (
        "PROTOCOLE_CONCURRENCE.md",
        "GUIDE_ENTRETIENS.md",
        "QUESTIONNAIRE.md",
        "PROTOCOLE_LANDING_TEST.md",
        "ASSORTIMENT_PILOTE.md",
        "README.md",
    ),
    "SOURCING": ("DOSSIER_B2B.md", "EMAILS_FOURNISSEURS.md", "CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md", "README.md"),
}
FOREIGN_DOCS = {"DELEGATION_AUTONOMIE.md", "ETOILE_POLAIRE.md", "STOP_LOSS.md"}

BACKLOG_HEADER = [
    "ID",
    "Titre",
    "Phase",
    "Agent/rôle",
    "Dépendances",
    "Priorité",
    "Statut",
    "Critère de done",
    "Validation humaine (O/N)",
    "Section BP",
    "Échéance",
    "Livrable",
]
BACKLOG_STATUSES = {"À faire", "En cours", "Préparé – à valider", "Bloqué", "Terminé"}
BACKLOG_PRIORITIES = {"P1", "P2", "P3"}
BACKLOG_PHASE_RE = re.compile(r"^(P[0-6] .+|Transverse)$")
BL_RE = re.compile(r"\bBL-\d{3}\b")

BP_SUPPLIERS = ("Asmodee France", "Matoo et Miao", "TCG Distribution", "OtakuWorld", "CardCosmos")
TRACKER_CATEGORIES = {
    "fournisseur",
    "fiduciaire",
    "banque",
    "psp",
    "transporteur",
    "logisticien",
    "juriste",
    "createur",
}
TRACKER_OPEN_STATUS = "non contacté"

GRILLE_PRICE_FIELDS = (
    "prix_produit_chf",
    "frais_livraison_chf",
    "seuil_port_gratuit_chf",
    "frais_paiement_chf",
    "prix_total_livre_chf",
)
PANIER_CATEGORIES = {"displays", "etb", "bundles_tripacks", "coffrets", "accessoires"}
PANIER_STATUSES = {"STOCK", "ALERTE", "COND"}

# BP §2 : chaque élément de la demande commerciale et technique (motif recherché, insensible à la casse)
BLOC_A_TERMS = (
    "SKU",
    "EAN",
    "langue",
    "extension",
    "conditionnement",
    "unités par carton",
    "HT",
    "TTC",
    "devise",
    "remises",
    "quantité minimale",
    "disponibilité",
    "allocation",
    "date de sortie",
    "frais de port",
    "Incoterm",
    "pays d'expédition",
    "paiement",
    "SAV",
    "images",
)
BLOC_B_TERMS = (
    "API",
    "CSV",
    "XML",
    "Excel",
    "téléchargement authentifié",
    "envoi périodique",
    "fréquence",
    "identifiants",
    "quantifié",
    "accusés de réception",
    "limites d'usage",
    "exemple de fichier",
)
EMAIL_SECTIONS = {
    "Asmodee France": "## 3. Asmodee France",
    "Matoo et Miao": "## 4. Matoo et Miao",
    "TCG Distribution": "## 5. TCG Distribution",
    "OtakuWorld": "## 6. OtakuWorld",
    "CardCosmos": "## 7. CardCosmos",
}


# ---------------------------------------------------------------- utilitaires
def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """En-tête et lignes d'un CSV UTF-8."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def split_ids(raw: str) -> list[str]:
    """Liste d'identifiants séparés par des virgules."""
    return [x.strip() for x in raw.split(",") if x.strip()]


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Renvoie un cycle de dépendances s'il en existe un (DFS itératif), sinon None."""
    state: dict[str, int] = {}
    for start in graph:
        if state.get(start):
            continue
        stack: list[tuple[str, Iterator[str]]] = [(start, iter(graph.get(start, [])))]
        path = [start]
        state[start] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                path.pop()
                continue
            if state.get(nxt) == 1:
                return path[path.index(nxt) :] + [nxt]
            if not state.get(nxt):
                state[nxt] = 1
                stack.append((nxt, iter(graph.get(nxt, []))))
                path.append(nxt)
    return None


def to_decimal(text: str) -> Decimal | None:
    """Montant écrit « 3 000 » ou « 750 » ; None si la cellule n'est pas un nombre."""
    cleaned = text.replace(" ", "").replace("\xa0", "").replace(" ", "").replace("*", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


# ---------------------------------------------------------------- contrôles
def check_backlog(path: Path = PILOTAGE / "BACKLOG.csv") -> list[str]:
    """Schéma, unicité, dépendances existantes et acycliques, valeurs autorisées."""
    errors: list[str] = []
    header, rows = read_csv(path)
    if header != BACKLOG_HEADER:
        return [f"BACKLOG : en-tête inattendu {header}"]
    ids = [r["ID"] for r in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"BACKLOG : identifiants en double {dupes}")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    for r in rows:
        rid = r["ID"]
        if not re.fullmatch(r"BL-\d{3}", rid):
            errors.append(f"BACKLOG : identifiant invalide {rid!r}")
        deps = split_ids(r["Dépendances"])
        graph[rid] = deps
        for d in deps:
            if d not in known:
                errors.append(f"BACKLOG {rid} : dépendance inconnue {d}")
            if d == rid:
                errors.append(f"BACKLOG {rid} : dépend de lui-même")
        if r["Priorité"] not in BACKLOG_PRIORITIES:
            errors.append(f"BACKLOG {rid} : priorité {r['Priorité']!r}")
        if r["Statut"] not in BACKLOG_STATUSES:
            errors.append(f"BACKLOG {rid} : statut {r['Statut']!r}")
        if r["Validation humaine (O/N)"] not in ("O", "N"):
            errors.append(f"BACKLOG {rid} : validation {r['Validation humaine (O/N)']!r}")
        if not BACKLOG_PHASE_RE.match(r["Phase"]):
            errors.append(f"BACKLOG {rid} : phase {r['Phase']!r}")
        for field in ("Titre", "Agent/rôle", "Critère de done", "Échéance", "Livrable"):
            if not r[field].strip():
                errors.append(f"BACKLOG {rid} : champ vide {field}")
        if r["Agent/rôle"].startswith("Propriétaire") and r["Validation humaine (O/N)"] != "O":
            errors.append(f"BACKLOG {rid} : tâche de la propriétaire sans validation humaine")
    cycle = find_cycle(graph)
    if cycle:
        errors.append(f"BACKLOG : cycle de dépendances {' -> '.join(cycle)}")
    return errors


def check_tracker(path: Path = SOURCING / "TRACKER_CONTACTS.csv") -> list[str]:
    """Aucun contact établi ; fournisseurs du BP et interlocuteurs du §2 présents."""
    errors: list[str] = []
    _, rows = read_csv(path)
    ids = [r["contact_id"] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("TRACKER : identifiants en double")
    for r in rows:
        if r["statut"] != TRACKER_OPEN_STATUS:
            errors.append(f"TRACKER {r['contact_id']} : statut {r['statut']!r} (attendu « {TRACKER_OPEN_STATUS} »)")
        for field in ("date_premier_contact", "date_relance_j5", "date_relance_j12"):
            if r[field].strip():
                errors.append(f"TRACKER {r['contact_id']} : {field} renseigné alors qu'aucun contact n'a eu lieu")
        if not r["verification_statut"].strip():
            errors.append(f"TRACKER {r['contact_id']} : statut de vérification vide")
        url = r["site_web"].strip()
        if url and not url.startswith("https://"):
            errors.append(f"TRACKER {r['contact_id']} : URL non https {url}")
    orgs = " ".join(r["organisation"] for r in rows)
    for sup in BP_SUPPLIERS:
        if sup not in orgs:
            errors.append(f"TRACKER : fournisseur du BP absent : {sup}")
    missing = TRACKER_CATEGORIES - {r["categorie"] for r in rows}
    if missing:
        errors.append(f"TRACKER : catégories BP §2 absentes {sorted(missing)}")
    return errors


def check_grille(path: Path = MARCHE / "GRILLE_CONCURRENCE.csv") -> list[str]:
    """5 boutiques × 10 à 15 références ; aucun prix sans lecture de page datée."""
    errors: list[str] = []
    _, rows = read_csv(path)
    shops = {r["boutique_id"] for r in rows}
    refs = {r["ref_id"] for r in rows}
    if len(shops) != 5:
        errors.append(f"GRILLE : {len(shops)} boutiques (attendu 5)")
    if not 10 <= len(refs) <= 15:
        errors.append(f"GRILLE : {len(refs)} références (attendu 10 à 15)")
    pairs = [(r["ref_id"], r["boutique_id"]) for r in rows]
    if len(pairs) != len(set(pairs)):
        errors.append("GRILLE : couple (référence, boutique) en double")
    if len(rows) != len(shops) * len(refs):
        errors.append("GRILLE : grille incomplète (il manque des couples référence × boutique)")
    for r in rows:
        has_price = any(r[f].strip() for f in GRILLE_PRICE_FIELDS)
        if has_price and not (
            r["source_lecture"] == "page lue" and r["date_releve"].strip() and r["url_produit"].strip()
        ):
            errors.append(f"GRILLE {r['releve_id']} : prix sans lecture de page datée avec URL")
        if not r["url_boutique"].startswith("https://"):
            errors.append(f"GRILLE {r['releve_id']} : URL boutique non https")
        if r["langue_attendue"] != "FR":
            errors.append(f"GRILLE {r['releve_id']} : langue attendue {r['langue_attendue']!r}")
        if r["fictif"] not in ("true", "false"):
            errors.append(f"GRILLE {r['releve_id']} : colonne fictif {r['fictif']!r}")
    return errors


def gtin_valid(code: str) -> bool:
    """Checksum GS1 (GTIN-8/12/13/14)."""
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(d) for d in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def check_panier(path: Path = SOURCING / "PANIER_PILOTE.csv") -> list[str]:
    """15 à 25 références dont 8 à 12 visées en stock ; catégories BP §1 ; aucun EAN inventé."""
    errors: list[str] = []
    _, rows = read_csv(path)
    if not 15 <= len(rows) <= 25:
        errors.append(f"PANIER : {len(rows)} références (attendu 15 à 25)")
    stock = sum(1 for r in rows if r["statut_vise"] == "STOCK")
    if not 8 <= stock <= 12:
        errors.append(f"PANIER : {stock} références en stock (attendu 8 à 12)")
    refs = [r["ref_id"] for r in rows]
    if len(refs) != len(set(refs)):
        errors.append("PANIER : ref_id en double")
    cats = {r["categorie_budget"] for r in rows}
    if cats != PANIER_CATEGORIES:
        errors.append(f"PANIER : catégories {sorted(cats)} ≠ {sorted(PANIER_CATEGORIES)}")
    for r in rows:
        if r["statut_vise"] not in PANIER_STATUSES:
            errors.append(f"PANIER {r['ref_id']} : statut {r['statut_vise']!r}")
        if not r["quantite_indicative_devis"].isdigit() or int(r["quantite_indicative_devis"]) < 1:
            errors.append(f"PANIER {r['ref_id']} : quantité indicative invalide")
        if r["format"] != "accessoire" and r["langue"] != "FR":
            errors.append(f"PANIER {r['ref_id']} : langue {r['langue']!r} (FR attendu)")
        ean = r["ean"].strip()
        if ean and not gtin_valid(ean):
            errors.append(f"PANIER {r['ref_id']} : EAN invalide {ean}")
        if r["fictif"] != "false":
            errors.append(f"PANIER {r['ref_id']} : le panier réel ne doit pas contenir de ligne FICTIF")
    return errors


def check_assortiment_envelopes(path: Path = MARCHE / "ASSORTIMENT_PILOTE.md") -> list[str]:
    """Tableau §2 : lignes = parts du BP (750/750/600/600/300), colonnes ≤ 750 CHF, total 3 000."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    section = text.split("## 2.", 1)[-1].split("## 3.", 1)[0]
    expected_rows = {
        "Displays": Decimal(750),
        "ETB": Decimal(750),
        "Bundles": Decimal(600),
        "Coffrets": Decimal(600),
        "Accessoires": Decimal(300),
    }
    columns: list[Decimal] = []
    found: set[str] = set()
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        label = next((k for k in expected_rows if cells[0].startswith(k)), None)
        if label is None:
            continue
        values = [to_decimal(c) if c not in ("—", "") else Decimal(0) for c in cells[1:]]
        if any(v is None for v in values):
            errors.append(f"ASSORTIMENT : valeur non numérique sur la ligne {label}")
            continue
        nums = [v for v in values if v is not None]
        *cells_ext, total = nums
        found.add(label)
        if sum(cells_ext) != total or total != expected_rows[label]:
            errors.append(
                f"ASSORTIMENT : ligne {label} = {sum(cells_ext)} / total {total} (attendu {expected_rows[label]})"
            )
        columns = [a + b for a, b in zip(columns, cells_ext, strict=True)] if columns else list(cells_ext)
    if found != set(expected_rows):
        errors.append(f"ASSORTIMENT : lignes manquantes {sorted(set(expected_rows) - found)}")
    if columns:
        *extensions, hors_extension = columns
        for idx, col in enumerate(extensions, start=1):
            if col > Decimal(750):
                errors.append(f"ASSORTIMENT : extension E{idx} = {col} CHF > plafond 750 CHF")
        if sum(columns) != Decimal(3000):
            errors.append(f"ASSORTIMENT : total {sum(columns)} ≠ 3 000 CHF")
        _ = hors_extension
    return errors


def check_cross_refs() -> list[str]:
    """Références croisées : BL-nnn existants ; ref_id cohérents entre grille, panier et assortiment."""
    errors: list[str] = []
    _, backlog = read_csv(PILOTAGE / "BACKLOG.csv")
    known = {r["ID"] for r in backlog}
    for md in owned_markdown():
        for ref in sorted(set(BL_RE.findall(md.read_text(encoding="utf-8")))):
            if ref not in known:
                errors.append(f"{md.name} : {ref} absent du backlog")
    _, panier = read_csv(SOURCING / "PANIER_PILOTE.csv")
    _, grille = read_csv(MARCHE / "GRILLE_CONCURRENCE.csv")
    panier_refs = {r["ref_id"] for r in panier}
    assort_refs = set(re.findall(r"REF-\d{2}", (MARCHE / "ASSORTIMENT_PILOTE.md").read_text(encoding="utf-8")))
    if not {r["ref_id"] for r in grille} <= panier_refs:
        errors.append("Références de la grille absentes du panier")
    if panier_refs != assort_refs:
        errors.append(f"Panier ≠ assortiment : {sorted(panier_refs ^ assort_refs)}")
    return errors


def check_emails(path: Path = SOURCING / "EMAILS_FOURNISSEURS.md") -> list[str]:
    """Un email + relances J+5/J+12 par fournisseur du BP ; blocs A et B complets."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    bloc_a = text.split("### Bloc A", 1)[-1].split("### Bloc B", 1)[0]
    bloc_b = text.split("### Bloc B", 1)[-1].split("## 3.", 1)[0]
    for term in BLOC_A_TERMS:
        if term.lower() not in bloc_a.lower():
            errors.append(f"EMAILS : bloc A sans « {term} » (BP §2)")
    for term in BLOC_B_TERMS:
        if term.lower() not in bloc_b.lower():
            errors.append(f"EMAILS : bloc B sans « {term} » (BP §2)")
    titles = list(EMAIL_SECTIONS.values()) + ["## 8.", "## 9."]
    for sup, title in EMAIL_SECTIONS.items():
        if title not in text:
            errors.append(f"EMAILS : section absente pour {sup}")
            continue
        body = text.split(title, 1)[1]
        nxt = min((body.find(t) for t in titles if t != title and body.find(t) > 0), default=len(body))
        body = body[:nxt]
        for need in ("**Objet :**", "{{Bloc A}}", "{{Bloc B}}", "Relance J+5", "Relance J+12", "Madame, Monsieur"):
            if need not in body:
                errors.append(f"EMAILS {sup} : « {need} » manquant")
    return errors


def check_gates(path: Path = PILOTAGE / "GATES_GO_NO_GO.md") -> list[str]:
    """Gates G0 à G7 décrits, chacun avec un décideur."""
    text = path.read_text(encoding="utf-8")
    errors = [f"GATES : G{n} absent" for n in range(8) if f"### G{n} " not in text]
    if text.count("**Décide :**") < 7:
        errors.append("GATES : décideur non indiqué pour chaque gate")
    return errors


def check_plan(path: Path = PILOTAGE / "PLAN_90_JOURS.md") -> list[str]:
    """J1 à J15 au jour, S3 à S13 à la semaine."""
    text = path.read_text(encoding="utf-8")
    errors = [f"PLAN : J{j} absent" for j in range(1, 16) if not re.search(rf"^\| J{j}(\b|-)", text, re.M)]
    errors += [f"PLAN : S{s} absente" for s in range(3, 14) if f"| S{s} |" not in text]
    return errors


def check_interventions(path: Path = PILOTAGE / "INTERVENTIONS_HUMAINES.md") -> list[str]:
    """Catégories A, B, C ; chaque ID de la checklist chronologique est détaillé."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for cat in ("Catégorie A", "Catégorie B", "Catégorie C"):
        if cat not in text:
            errors.append(f"INTERVENTIONS : {cat} absente")
    chrono = text.split("## 1.", 1)[-1].split("## 2.", 1)[0]
    details = text.split("## 2.", 1)[-1]
    detailed = set(re.findall(r"^\| ([ABC]\d{2}) \|", details, re.M))
    for ident in sorted(set(re.findall(r"\b([ABC]\d{2})\b", chrono))):
        if ident not in detailed:
            errors.append(f"INTERVENTIONS : {ident} sans fiche détaillée")
    return errors


def owned_markdown() -> list[Path]:
    """Documents Markdown du périmètre présents sur disque (liste explicite ``OWNED_MD``)."""
    folders = {"PILOTAGE": PILOTAGE, "MARCHE": MARCHE, "SOURCING": SOURCING}
    paths = (folders[key] / name for key, names in OWNED_MD.items() for name in names)
    return sorted(p for p in paths if p.exists() and p.name not in FOREIGN_DOCS)


def check_validation_sections(paths: Iterable[Path] | None = None) -> list[str]:
    """Chaque document se termine par « ## Validation humaine requise » avec au moins une case."""
    errors: list[str] = []
    for md in paths if paths is not None else owned_markdown():
        text = md.read_text(encoding="utf-8")
        heads = re.findall(r"^## .+$", text, re.M)
        if not heads or heads[-1].strip() != "## Validation humaine requise":
            errors.append(f"{md.name} : la dernière section n'est pas « Validation humaine requise »")
            continue
        tail = text.rsplit("## Validation humaine requise", 1)[1]
        if "- [ ]" not in tail:
            errors.append(f"{md.name} : aucune case à cocher dans « Validation humaine requise »")
    return errors


ALL_CHECKS = (
    check_backlog,
    check_tracker,
    check_grille,
    check_panier,
    check_assortiment_envelopes,
    check_cross_refs,
    check_emails,
    check_gates,
    check_plan,
    check_interventions,
    check_validation_sections,
)


def run_all() -> list[str]:
    """Tous les contrôles ; liste vide si tout est cohérent."""
    errors: list[str] = []
    for check in ALL_CHECKS:
        errors.extend(check())
    return errors


def main() -> int:
    errors = run_all()
    if errors:
        print(f"{len(errors)} anomalie(s) :", *errors, sep="\n  ")
        return 1
    print(f"OK — {len(ALL_CHECKS)} contrôles sans anomalie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
