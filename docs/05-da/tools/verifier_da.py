#!/usr/bin/env python3
"""Vérifications automatiques des livrables DA (docs/05-da).

Contrôles :
1. Tous les SVG sont du XML bien formé, avec viewBox, dimensions et <title>.
2. Logos : contours uniquement (pas de <text>, pas de police, pas d'image), aucun terme « Poké ».
3. Gabarits sociaux aux bonnes dimensions ; packaging en millimètres.
4. Contrastes WCAG de toutes les paires déclarées (tokens.json) >= seuil, clair ET sombre.
5. Les ratios annoncés dans DIRECTION_A.md / DIRECTION_B.md / DIRECTION_NUIT.md sont exacts (recalculés).
   Ambiances (tokens.json > ambiances, ex. « nuit ») : toujours sombres, mêmes clés de couleur que les
   directions (et plus), polices chargées par leur URL, paires communes + paires d'ambiance ≥ seuil.
6. Fichiers générés synchronisés avec tokens.json et le générateur.
7. HTML : ressources relatives existantes ; ressources externes limitées à Google Fonts.
8. Fichiers publics : aucun terme de donnée interne (coût, marge, fournisseur…), aucun EAN.
9. Chaque document .md se termine par « Validation humaine requise ».
10. Champs ``{{MAJUSCULES}}`` des fichiers publics : déclarés dans le registre légal
    (docs/04-legal/champs_a_remplir.yaml), dans les champs de la landing (site/config/publication_landing.yaml)
    ou dans la liste fermée VARIABLES_DA (valeurs propres à un produit ou à une commande, jamais une règle) ;
    une limite « par commande » (les CGV fixent une limite par foyer) est refusée.

Usage : python docs/05-da/tools/verifier_da.py   (code de sortie 1 si erreur)
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from contraste import est_hex, ratio, ratio_affiche  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"
HOTES_AUTORISES = {"fonts.googleapis.com", "fonts.gstatic.com"}
TERMES_INTERNES = re.compile(
    r"\b(co[uû]ts?|marges?|margins?(?![-:\w])|costs?|prix d['’]achat|fournisseurs?|suppliers?|b2b|grossiste)\b",
    re.IGNORECASE,
)
EAN_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")
REPO = RACINE.parents[1]
REGISTRES_CHAMPS = (
    REPO / "docs" / "04-legal" / "champs_a_remplir.yaml",
    REPO / "site" / "config" / "publication_landing.yaml",
)
CHAMP_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
#: Variables des gabarits DA qui ne sont pas des champs du registre : valeurs d'un produit (catalogue validé),
#: d'une commande (Shopify), d'une collection ou paramètre du thème. Une règle (limite, délai, TVA…) n'y entre
#: jamais : elle vient du registre légal, une valeur à un seul endroit.
VARIABLES_DA = frozenset({
    "CHAMPS",  # mention générique dans les notes des gabarits
    "EXTENSION", "PRIX_VALIDE", "DATE_SORTIE", "DATE_SORTIE_CONFIRMEE", "CONTENU_VALIDE", "SKU", "EAN_SI_EXISTANT",
    "N_REFERENCES", "N_JOURS_NOUVEAUTE",
    "N_COMMANDE", "NUMERO_COMMANDE", "DATE_COMMANDE", "PRENOM", "ADRESSE_LIVRAISON", "MOYEN_PAIEMENT", "TOTAL_PAYE",
    "URL_SUIVI_COMMANDE", "URL_LOGO_PNG",
})
LIMITE_PAR_COMMANDE_RE = re.compile(
    r"(?:\blimite\b[^.\n<]{0,40}?|\bmax(?:imum\b|\.|\b))[\s\u00a0\u202f]*par[\s\u00a0\u202f]+commande\b", re.IGNORECASE
)
DIMENSIONS_SOCIAL = {"1x1": (1080, 1080), "4x5": (1080, 1350), "9x16": (1080, 1920)}


def charger_tokens(racine: Path = RACINE) -> dict:
    """Charge tokens/tokens.json."""
    return json.loads((racine / "tokens" / "tokens.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1–3 SVG
# ---------------------------------------------------------------------------
def fichiers_svg(racine: Path = RACINE) -> list[Path]:
    """Tous les SVG livrés (hors outils et tests)."""
    return sorted(p for p in racine.rglob("*.svg") if "tools" not in p.parts and "tests" not in p.parts)


def verifier_svgs(racine: Path = RACINE) -> list[str]:
    """Erreurs de forme, de dimensions et de contenu des SVG."""
    erreurs: list[str] = []
    svgs = fichiers_svg(racine)
    if not svgs:
        return ["Aucun SVG trouvé"]
    for p in svgs:
        rel = p.relative_to(racine).as_posix()
        try:
            arbre = ET.parse(p)
        except ET.ParseError as exc:
            erreurs.append(f"{rel} : XML mal formé ({exc})")
            continue
        svg = arbre.getroot()
        if svg.tag != f"{SVG_NS}svg":
            erreurs.append(f"{rel} : racine non <svg> ou espace de noms SVG absent")
            continue
        for attr in ("viewBox", "width", "height"):
            if not svg.get(attr):
                erreurs.append(f"{rel} : attribut {attr} manquant")
        if svg.find(f"{SVG_NS}title") is None or not (svg.findtext(f"{SVG_NS}title") or "").strip():
            erreurs.append(f"{rel} : <title> manquant")
        vb = [float(v) for v in (svg.get("viewBox") or "0 0 0 0").split()]
        contenu = p.read_text(encoding="utf-8")
        if rel.startswith("logo/"):
            if any(True for _ in svg.iter(f"{SVG_NS}text")):
                erreurs.append(f"{rel} : un logo ne doit contenir aucun <text> (contours uniquement)")
            if "font-family" in contenu or "<image" in contenu or "href=" in contenu:
                erreurs.append(f"{rel} : police, image ou lien externe interdit dans un logo")
            if re.search(r"pok[eé]", contenu, re.IGNORECASE):
                erreurs.append(f"{rel} : terme « Poké » interdit dans un logo")
            if not any(True for _ in svg.iter(f"{SVG_NS}path")):
                erreurs.append(f"{rel} : aucun tracé")
        if rel.startswith("social/") and "guides" not in rel:
            m = re.search(r"(1x1|4x5|9x16)", p.name)
            if not m:
                erreurs.append(f"{rel} : format absent du nom de fichier")
            else:
                attendu = DIMENSIONS_SOCIAL[m.group(1)]
                if (vb[2], vb[3]) != attendu or svg.get("width") != str(attendu[0]) or svg.get("height") != str(attendu[1]):
                    erreurs.append(f"{rel} : dimensions {vb[2:]} ≠ {attendu}")
            besoin_photo = "couverture" in p.name or "story" in p.name or p.name.endswith("-1.svg")
            if besoin_photo and 'id="ZONE_PHOTO' not in contenu:
                erreurs.append(f"{rel} : zone photo produit réelle absente")
        if rel.startswith("packaging/"):
            if not (svg.get("width", "").endswith("mm") and svg.get("height", "").endswith("mm")):
                erreurs.append(f"{rel} : un fichier d'impression doit être dimensionné en mm")
            if 'id="DECOUPE_ne_pas_imprimer"' not in contenu:
                erreurs.append(f"{rel} : calque de découpe absent")
    return erreurs


# ---------------------------------------------------------------------------
# 4–5 Contrastes
# ---------------------------------------------------------------------------
def lignes_contraste(tokens: dict) -> list[dict]:
    """Toutes les paires (direction × mode) avec ratio calculé."""
    lignes = []
    for da, d in tokens["directions"].items():
        for mode in ("light", "dark"):
            cols = {k: v["$value"] for k, v in d["color"][mode].items()}
            for paire in tokens["contrastPairs"]:
                fg, bg = cols[paire["fg"]], cols[paire["bg"]]
                lignes.append(
                    {
                        "da": da, "mode": mode, "fg": paire["fg"], "bg": paire["bg"],
                        "fg_hex": fg, "bg_hex": bg, "ratio": ratio(fg, bg),
                        "affiche": ratio_affiche(fg, bg), "min": paire["min"], "usage": paire["usage"],
                    }
                )
    return lignes


def lignes_contraste_ambiances(tokens: dict) -> list[dict]:
    """Paires de chaque ambiance (mode sombre unique) : paires communes + ``ambianceContrastPairs``."""
    lignes = []
    paires = list(tokens["contrastPairs"]) + list(tokens.get("ambianceContrastPairs", []))
    for nom, amb in tokens.get("ambiances", {}).items():
        cols = {k: v["$value"] for k, v in amb["color"]["dark"].items()}
        for paire in paires:
            if paire["fg"] not in cols or paire["bg"] not in cols:
                continue  # signalé par verifier_tokens
            fg, bg = cols[paire["fg"]], cols[paire["bg"]]
            lignes.append(
                {
                    "da": nom, "mode": "dark", "fg": paire["fg"], "bg": paire["bg"],
                    "fg_hex": fg, "bg_hex": bg, "ratio": ratio(fg, bg),
                    "affiche": ratio_affiche(fg, bg), "min": paire["min"], "usage": paire["usage"],
                }
            )
    return lignes


def verifier_ambiances(tokens: dict) -> list[str]:
    """Structure des ambiances : base existante, sombre seulement, couleurs complètes et valides, polices chargées."""
    erreurs: list[str] = []
    reference = set(next(iter(tokens["directions"].values()))["color"]["light"])
    paires = list(tokens["contrastPairs"]) + list(tokens.get("ambianceContrastPairs", []))
    for nom, amb in tokens.get("ambiances", {}).items():
        if amb.get("base") not in tokens["directions"]:
            erreurs.append(f"ambiance {nom} : direction de base inconnue {amb.get('base')!r}")
        if set(amb.get("color", {})) != {"dark"}:
            erreurs.append(f"ambiance {nom} : une ambiance est toujours sombre (clé color.dark seule attendue)")
            continue
        cles = set(amb["color"]["dark"])
        if not reference <= cles:
            erreurs.append(f"ambiance {nom} : couleurs manquantes {sorted(reference - cles)}")
        for k, v in amb["color"]["dark"].items():
            if not est_hex(v["$value"]):
                erreurs.append(f"ambiance {nom}/{k} : couleur invalide {v['$value']}")
        for paire in paires:
            for cle in (paire["fg"], paire["bg"]):
                if cle not in cles:
                    erreurs.append(f"ambiance {nom} : paire de contraste vers un token inconnu {cle}")
        url = amb.get("googleFonts", "")
        if not url.startswith("https://fonts.googleapis.com/css2?"):
            erreurs.append(f"ambiance {nom} : URL Google Fonts manquante")
        for role, police in amb.get("font", {}).items():
            famille = police["$value"].split(",")[0].strip().strip('"')
            if famille.replace(" ", "+") not in url:
                erreurs.append(f"ambiance {nom} : la police {famille} ({role}) n'est pas chargée par l'URL Google Fonts")
    return erreurs


def verifier_tokens(tokens: dict) -> list[str]:
    """Structure des tokens : mêmes clés partout, couleurs hexadécimales valides."""
    erreurs = []
    reference: set[str] | None = None
    for da, d in tokens["directions"].items():
        for mode in ("light", "dark"):
            cles = set(d["color"][mode])
            if reference is None:
                reference = cles
            elif cles != reference:
                erreurs.append(f"{da}/{mode} : jeu de couleurs différent ({sorted(cles ^ reference)})")
            for k, v in d["color"][mode].items():
                if not est_hex(v["$value"]):
                    erreurs.append(f"{da}/{mode}/{k} : couleur invalide {v['$value']}")
        for role in ("display", "text", "price"):
            if role not in d["font"]:
                erreurs.append(f"{da} : police {role} manquante")
        if not d.get("googleFonts", "").startswith("https://fonts.googleapis.com/css2?"):
            erreurs.append(f"{da} : URL Google Fonts manquante")
        else:
            for role in ("display", "text", "price"):
                famille = d["font"][role]["$value"].split(",")[0].strip().strip('"')
                if famille.replace(" ", "+") not in d["googleFonts"]:
                    erreurs.append(f"{da} : la police {famille} n'est pas chargée par l'URL Google Fonts")
    for paire in tokens["contrastPairs"]:
        for cle in (paire["fg"], paire["bg"]):
            if reference is not None and cle not in reference:
                erreurs.append(f"Paire de contraste : token inconnu {cle}")
    return erreurs


def verifier_contrastes(tokens: dict) -> list[str]:
    """Toute paire déclarée doit atteindre son seuil dans les 2 directions et les 2 modes."""
    return [
        f"{lc['da']}/{lc['mode']} {lc['fg']} sur {lc['bg']} : {lc['ratio']:.2f} < {lc['min']}"
        for lc in lignes_contraste(tokens) + lignes_contraste_ambiances(tokens)
        if lc["ratio"] < lc["min"]
    ]


TABLE_RE = re.compile(
    r"^\|\s*(?P<mode>Clair|Sombre)\s*\|[^|]*\|\s*`(?P<fg>#[0-9A-Fa-f]{6})`[^|]*\|\s*`(?P<bg>#[0-9A-Fa-f]{6})`[^|]*\|\s*\*{0,2}(?P<r>\d+\.\d{2}):1",
    re.MULTILINE,
)


CITATION_RE = re.compile(r"(\d+\.\d{2}):1[^`\n]{0,40}entre `(#[0-9A-Fa-f]{6})` et `(#[0-9A-Fa-f]{6})`")


def verifier_citations(racine: Path = RACINE) -> list[str]:
    """Ratios cités dans le texte (« X:1 … entre `#A` et `#B` ») : recalculés pour tous les .md et le HTML."""
    erreurs = []
    for p in sorted(list(racine.rglob("*.md")) + list(racine.rglob("*.html"))):
        if "tools" in p.parts or "tests" in p.parts:
            continue
        for m in CITATION_RE.finditer(p.read_text(encoding="utf-8")):
            calcule = ratio_affiche(m.group(2), m.group(3))
            if calcule != m.group(1):
                erreurs.append(f"{p.relative_to(racine).as_posix()} : {m.group(2)}/{m.group(3)} cité {m.group(1)}:1, calculé {calcule}:1")
    return erreurs


def verifier_docs_contrastes(racine: Path, tokens: dict) -> list[str]:
    """Les ratios publiés dans DIRECTION_A/B.md sont exacts et couvrent toutes les paires."""
    erreurs = verifier_citations(racine)
    for da in ("a", "b"):
        doc = racine / f"DIRECTION_{da.upper()}.md"
        if not doc.exists():
            erreurs.append(f"{doc.name} absent")
            continue
        texte = doc.read_text(encoding="utf-8")
        trouves = list(TABLE_RE.finditer(texte))
        attendues = [lc for lc in lignes_contraste(tokens) if lc["da"] == da]
        if len(trouves) < len(attendues):
            erreurs.append(f"{doc.name} : {len(trouves)} lignes de contraste publiées pour {len(attendues)} paires")
        for m in trouves:
            calcule = ratio_affiche(m["fg"], m["bg"])
            if calcule != m["r"]:
                erreurs.append(f"{doc.name} : {m['fg']} sur {m['bg']} annoncé {m['r']}:1, calculé {calcule}:1")
        publies = {(m["mode"], m["fg"].upper(), m["bg"].upper()) for m in trouves}
        for lc in attendues:
            cle = ("Clair" if lc["mode"] == "light" else "Sombre", lc["fg_hex"].upper(), lc["bg_hex"].upper())
            if cle not in publies:
                erreurs.append(f"{doc.name} : paire non publiée {lc['mode']} {lc['fg']}/{lc['bg']}")
    for nom in tokens.get("ambiances", {}):
        doc = racine / f"DIRECTION_{nom.upper()}.md"
        if not doc.exists():
            erreurs.append(f"{doc.name} absent (documentation de l'ambiance {nom})")
            continue
        trouves = list(TABLE_RE.finditer(doc.read_text(encoding="utf-8")))
        for m in trouves:
            calcule = ratio_affiche(m["fg"], m["bg"])
            if calcule != m["r"]:
                erreurs.append(f"{doc.name} : {m['fg']} sur {m['bg']} annoncé {m['r']}:1, calculé {calcule}:1")
        publies = {(m["fg"].upper(), m["bg"].upper()) for m in trouves}
        for lc in lignes_contraste_ambiances(tokens):
            if lc["da"] == nom and (lc["fg_hex"].upper(), lc["bg_hex"].upper()) not in publies:
                erreurs.append(f"{doc.name} : paire non publiée {lc['fg']}/{lc['bg']}")
    return erreurs


# ---------------------------------------------------------------------------
# 6 Synchronisation des fichiers générés
# ---------------------------------------------------------------------------
def verifier_synchro(racine: Path = RACINE) -> list[str]:
    """Chaque fichier généré sur disque est identique à la sortie du générateur."""
    import generer_da  # import tardif : le générateur lit tokens.json au chargement

    erreurs = []
    for rel, contenu in generer_da.tous_les_fichiers().items():
        chemin = racine / rel
        if not chemin.exists():
            erreurs.append(f"{rel} : absent (lancer tools/generer_da.py)")
        elif chemin.read_text(encoding="utf-8") != contenu:
            erreurs.append(f"{rel} : désynchronisé (lancer tools/generer_da.py)")
    for da in ("a", "b"):
        doc = racine / f"DIRECTION_{da.upper()}.md"
        if doc.exists() and generer_da.tableau_contrastes_md(da) not in doc.read_text(encoding="utf-8"):
            erreurs.append(f"{doc.name} : tableau de contrastes désynchronisé (lancer tools/generer_da.py)")
    for nom in generer_da.AMBIANCES:
        doc = racine / f"DIRECTION_{nom.upper()}.md"
        if doc.exists() and generer_da.tableau_contrastes_ambiance_md(nom) not in doc.read_text(encoding="utf-8"):
            erreurs.append(f"{doc.name} : tableau de contrastes désynchronisé (lancer tools/generer_da.py)")
    return erreurs


# ---------------------------------------------------------------------------
# 7 HTML
# ---------------------------------------------------------------------------
class _Ressources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ressources: list[tuple[str, str]] = []
        self.liens: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in ("img", "script", "source", "iframe", "embed", "audio", "video") and a.get("src"):
            self.ressources.append((tag, a["src"]))
        if tag == "link" and a.get("href"):
            self.ressources.append((tag, a["href"]))
        if tag == "object" and a.get("data"):
            self.ressources.append((tag, a["data"]))
        if tag == "a" and a.get("href"):
            self.liens.append(a["href"])


def fichiers_html(racine: Path = RACINE) -> list[Path]:
    return sorted(p for p in racine.rglob("*.html") if "tools" not in p.parts and "tests" not in p.parts)


def verifier_html(racine: Path = RACINE) -> list[str]:
    """Ressources relatives existantes ; ressources externes = Google Fonts uniquement."""
    erreurs = []
    for p in fichiers_html(racine):
        rel = p.relative_to(racine).as_posix()
        texte = p.read_text(encoding="utf-8")
        parseur = _Ressources()
        parseur.feed(texte)
        for tag, url in parseur.ressources:
            if "{{" in url or url.startswith("data:"):
                continue
            u = urlparse(url)
            if u.scheme in ("http", "https"):
                if u.hostname not in HOTES_AUTORISES:
                    erreurs.append(f"{rel} : ressource externe non autorisée <{tag}> {url}")
            elif u.scheme == "" and not url.startswith("#"):
                cible = (p.parent / u.path).resolve()
                if not cible.exists():
                    erreurs.append(f"{rel} : ressource introuvable {url}")
        for url in parseur.liens:
            u = urlparse(url)
            if u.scheme == "" and u.path and "{{" not in url and not url.startswith("#"):
                if not (p.parent / u.path).resolve().exists():
                    erreurs.append(f"{rel} : lien relatif cassé {url}")
        if "email-transactionnel" in p.name:
            if "<script" in texte or "var(--" in texte or "<style" in texte:
                erreurs.append(f"{rel} : un email doit utiliser des styles en ligne (pas de script, var() ni <style>)")
    return erreurs


# ---------------------------------------------------------------------------
# 8 Données internes dans les fichiers publics
# ---------------------------------------------------------------------------
def fichiers_publics(racine: Path = RACINE) -> list[Path]:
    """Fichiers destinés au public (site, emails, réseaux, impression)."""
    motifs = ["components/*.html", "social/**/*.svg", "packaging/**/*.svg", "logo/**/*.svg"]
    out: list[Path] = []
    for m in motifs:
        out += list(racine.glob(m))
    return sorted(set(out))


def champs_declares(registres: tuple[Path, ...] = REGISTRES_CHAMPS) -> set[str]:
    """Noms des champs déclarés dans les registres (légal et landing)."""
    import yaml

    noms: set[str] = set()
    for chemin in registres:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        noms |= set((donnees.get("champs") or {}).keys())
    return noms


def verifier_champs(racine: Path = RACINE, declares: set[str] | None = None) -> list[str]:
    """Champs des fichiers publics déclarés (registre, landing ou VARIABLES_DA) ; aucune limite « par commande »."""
    declares = champs_declares() if declares is None else declares
    erreurs = []
    for p in fichiers_publics(racine) + ([racine / "CHARTE.html"] if (racine / "CHARTE.html").exists() else []):
        rel = p.relative_to(racine).as_posix()
        texte = p.read_text(encoding="utf-8")
        for nom in sorted(set(CHAMP_RE.findall(texte)) - declares - VARIABLES_DA):
            erreurs.append(f"{rel} : champ {{{{{nom}}}}} absent du registre légal et des champs de la landing")
        m = LIMITE_PAR_COMMANDE_RE.search(texte)
        if m:
            erreurs.append(f"{rel} : limite exprimée « par commande » (« {m.group(0)} ») : les CGV fixent une limite par foyer")
    return erreurs


def verifier_termes_publics(racine: Path = RACINE) -> list[str]:
    """Aucun terme de donnée interne ni EAN dans les fichiers publics ; exemples marqués FICTIF."""
    erreurs = []
    for p in fichiers_publics(racine):
        rel = p.relative_to(racine).as_posix()
        texte = p.read_text(encoding="utf-8")
        m = TERMES_INTERNES.search(texte)
        if m:
            erreurs.append(f"{rel} : terme interne « {m.group(0)} » dans un fichier public")
        if EAN_RE.search(texte):
            erreurs.append(f"{rel} : nombre à 13 chiffres (EAN ?) dans un fichier public")
        if p.suffix == ".html" and re.search(r"CHF\s*\d", texte) and "FICTIF" not in texte:
            erreurs.append(f"{rel} : montant d'exemple sans mention FICTIF")
    return erreurs


# ---------------------------------------------------------------------------
# 9 Documents
# ---------------------------------------------------------------------------
def verifier_docs(racine: Path = RACINE) -> list[str]:
    """Chaque .md se termine par une section « Validation humaine requise »."""
    erreurs = []
    for p in sorted(racine.rglob("*.md")):
        if "tools" in p.parts or "tests" in p.parts:
            continue
        titres = re.findall(r"^#{1,3} .*$", p.read_text(encoding="utf-8"), re.MULTILINE)
        if not titres or "Validation humaine requise" not in titres[-1]:
            erreurs.append(f"{p.relative_to(racine).as_posix()} : dernière section ≠ « Validation humaine requise »")
    charte = racine / "CHARTE.html"
    if charte.exists() and "Validation humaine requise" not in charte.read_text(encoding="utf-8"):
        erreurs.append("CHARTE.html : section « Validation humaine requise » absente")
    return erreurs


def tout_verifier(racine: Path = RACINE) -> dict[str, list[str]]:
    """Exécute tous les contrôles ; {nom du contrôle: erreurs}."""
    tokens = charger_tokens(racine)
    return {
        "svg": verifier_svgs(racine),
        "tokens": verifier_tokens(tokens) + verifier_ambiances(tokens),
        "contrastes": verifier_contrastes(tokens),
        "contrastes_docs": verifier_docs_contrastes(racine, tokens),
        "synchro": verifier_synchro(racine),
        "html": verifier_html(racine),
        "termes_publics": verifier_termes_publics(racine),
        "champs": verifier_champs(racine),
        "docs": verifier_docs(racine),
    }


def main() -> int:
    resultats = tout_verifier()
    total = 0
    for nom, erreurs in resultats.items():
        statut = "OK" if not erreurs else f"{len(erreurs)} erreur(s)"
        print(f"[{statut:>12}] {nom}")
        for e in erreurs:
            print(f"    - {e}")
        total += len(erreurs)
    tokens = charger_tokens()
    total_paires = len(lignes_contraste(tokens)) + len(lignes_contraste_ambiances(tokens))
    print(f"{len(fichiers_svg())} SVG analysés, {total_paires} paires de contraste calculées.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
