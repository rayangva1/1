#!/usr/bin/env python3
"""Contrôles automatiques de docs/06-contenu.

1. Documents .md : dernière section « Validation humaine requise ».
2. Calendrier : synchronisé avec le générateur ; colonnes Notion ; dates dans les 90 jours ; aucune
   « nouveauté » ni alerte de stock avant l'ouverture ; 1 guide + 1 nouveauté + 1 preuve de service par
   semaine après l'ouverture (hors semaine de Noël) ; au plus un récapitulatif email par semaine ;
   les 15 sujets planifiés ; aucune accroche avec prix, urgence ou promesse interdite.
3. 15 sujets : S01 à S15, chacun avec angle, hook, plan, format, visuels réels, CTA.
4. Scripts vidéo : 8 scripts, plans contigus depuis 0 s, durée annoncée = durée des plans, 20 à 45 s.
5. Emails : synchronisés avec la source ; HTML bien formé, sans script/style/var() ; aucun terme interne,
   EAN, prix en dur, urgence ou promesse ; mention d'indépendance et identité dans chaque pied ;
   préférences et désinscription dans chaque email marketing ; champs {{CHAMP}} connus du registre ;
   syntaxe propre au canal (n8n ou Liquid).
6. Publicité, créateurs, SEO : éléments obligatoires présents ; aucun volume de recherche chiffré.

Usage : python docs/06-contenu/outils/verifier_contenu.py   (code 1 si erreur)
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

OUTILS = Path(__file__).resolve().parent
RACINE = OUTILS.parent
REPO = RACINE.parents[1]
sys.path.insert(0, str(OUTILS))
sys.path.insert(0, str(REPO / "site" / "outils"))

import generer_calendrier as gc  # noqa: E402
import generer_emails as ge  # noqa: E402
import yaml  # noqa: E402
from verifier_site import EAN_RE, PROMESSES_RE, TERMES_INTERNES, URGENCE_RE, analyser  # noqa: E402

PRIX_EN_DUR_RE = re.compile(r"CHF\s*\d|\d+[.,]\d{2}\s*CHF")
CHAMPS_HORS_REGISTRE = {"URL_LOGO_PNG"}
MENTION_COURTE = "Boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus."
CHAMPS_SUJET = ("**Angle**", "**Hook**", "**Plan**", "**Format**", "**Visuels réels nécessaires**", "**CTA**")
VOLUME_RE = re.compile(r"\d[\d'  ]*\s*(recherches|requêtes|searches)\b|volume\s*(mensuel)?\s*:\s*\d", re.IGNORECASE)


# ----------------------------------------------------------------------------- documents
def verifier_docs(racine: Path = RACINE) -> list[str]:
    """Chaque .md se termine par « Validation humaine requise »."""
    erreurs = []
    for p in sorted(racine.rglob("*.md")):
        titres = re.findall(r"^#{1,3} .*$", p.read_text(encoding="utf-8"), re.MULTILINE)
        if not titres or "Validation humaine requise" not in titres[-1]:
            erreurs.append(f"{p.relative_to(REPO).as_posix()} : dernière section ≠ « Validation humaine requise »")
    return erreurs


# ----------------------------------------------------------------------------- calendrier
def lire_calendrier(texte: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(texte)))


def verifier_calendrier(texte: str | None = None, *, controler_synchro: bool = True) -> list[str]:
    """Invariants du calendrier (texte CSV, par défaut le fichier livré)."""
    chemin = gc.SORTIE
    if texte is None:
        if not chemin.exists():
            return ["CALENDRIER_90J.csv absent"]
        texte = chemin.read_text(encoding="utf-8")
    erreurs: list[str] = []
    if controler_synchro and texte != gc.contenu_csv():
        erreurs.append("CALENDRIER_90J.csv désynchronisé du générateur (relancer generer_calendrier.py)")
    lignes = lire_calendrier(texte)
    if not lignes or tuple(lignes[0].keys()) != gc.COLONNES:
        return erreurs + ["colonnes du calendrier inattendues (import Notion)"]
    debut, fin = gc.J1_DEFAUT, date(2027, 1, 2)
    recap_par_semaine: Counter[str] = Counter()
    piliers: dict[str, list[str]] = {}
    sujets: set[str] = set()
    for i, lg in enumerate(lignes, start=2):
        jour = date.fromisoformat(lg["Date"])
        j = int(lg["J"][1:])
        if not debut <= jour <= fin:
            erreurs.append(f"ligne {i} : date hors des 90 jours ({lg['Date']})")
        if gc.JOURS[jour.weekday()] != lg["Jour"]:
            erreurs.append(f"ligne {i} : jour de la semaine incohérent")
        if lg["Type"] not in gc.TYPES or lg["Pilier"] not in gc.PILIERS:
            erreurs.append(f"ligne {i} : type ou pilier inconnu")
        texte_public = f"{lg['Nom']} {lg['Accroche']}"
        for motif, libelle in ((PRIX_EN_DUR_RE, "prix"), (URGENCE_RE, "fausse urgence"), (PROMESSES_RE, "promesse interdite"),
                               (TERMES_INTERNES, "terme interne")):
            m = motif.search(texte_public)
            if m:
                erreurs.append(f"ligne {i} : {libelle} « {m.group(0)} »")
        stock = lg["Pilier"] == "Nouveauté accessible" or lg["Format"].startswith(("Email 03", "Email 04"))
        if stock and j < gc.J_OUVERTURE:
            erreurs.append(f"ligne {i} : contenu de stock avant l'ouverture (J{j})")
        if stock and "stock local" not in lg["Condition de publication"].lower():
            erreurs.append(f"ligne {i} : contenu de stock sans condition de stock local réel")
        if lg["Type"] == "Email" and lg["Format"].startswith("Email 05"):
            recap_par_semaine[lg["Semaine"]] += 1
        if lg["Type"] == "Publication":
            piliers.setdefault(lg["Semaine"], []).append(lg["Pilier"])
            sujets.update(s.strip() for s in lg["Sujet"].split(",") if s.strip().startswith("S"))
    erreurs += [f"{s} : {n} récapitulatifs (1 au plus)" for s, n in recap_par_semaine.items() if n > 1]
    semaine_ouverture = (gc.J_OUVERTURE - 1) // 7 + 1
    for numero in range(semaine_ouverture, 14):
        s = f"S{numero}"
        liste = piliers.get(s, [])
        if numero == 12:  # semaine de Noël : rythme réduit annoncé
            if len(liste) < 2:
                erreurs.append(f"{s} : moins de 2 publications")
            continue
        for pilier in ("Guide", "Nouveauté accessible", "Preuve de service"):
            if pilier not in liste:
                erreurs.append(f"{s} : pilier « {pilier} » absent")
        if len(liste) != 3:
            erreurs.append(f"{s} : {len(liste)} publications (3 attendues)")
    manquants = sorted({f"S{n:02d}" for n in range(1, 16)} - sujets)
    if manquants:
        erreurs.append(f"sujets jamais planifiés : {manquants}")
    return erreurs


# ----------------------------------------------------------------------------- sujets et scripts
def verifier_sujets(texte: str | None = None) -> list[str]:
    texte = texte if texte is not None else (RACINE / "15_SUJETS.md").read_text(encoding="utf-8")
    erreurs = []
    sections = re.split(r"^### (S\d{2}) ", texte, flags=re.MULTILINE)
    trouves = {sections[i]: sections[i + 1] for i in range(1, len(sections) - 1, 2)}
    for n in range(1, 16):
        cle = f"S{n:02d}"
        if cle not in trouves:
            erreurs.append(f"15_SUJETS.md : fiche {cle} absente")
            continue
        for champ in CHAMPS_SUJET:
            if champ not in trouves[cle]:
                erreurs.append(f"15_SUJETS.md : {cle} sans {champ.strip('*')}")
    return erreurs


def plans_script(bloc: str) -> list[tuple[int, int]]:
    """(début, fin) en secondes de chaque plan d'un script."""
    return [(int(a), int(b)) for a, b in re.findall(r"^\| \d+ \| (\d+)-(\d+) s \|", bloc, re.MULTILINE)]


def verifier_scripts(texte: str | None = None) -> list[str]:
    texte = texte if texte is not None else (RACINE / "SCRIPTS_VIDEO.md").read_text(encoding="utf-8")
    erreurs = []
    scripts = re.findall(r"^### (V\d) — .*?\((\d+) s\)(.*?)(?=^### |^## )", texte, re.MULTILINE | re.DOTALL)
    if len(scripts) != 8:
        erreurs.append(f"SCRIPTS_VIDEO.md : {len(scripts)} scripts (8 attendus)")
    for nom, duree, bloc in scripts:
        plans = plans_script(bloc)
        if not plans:
            erreurs.append(f"{nom} : aucun plan minuté")
            continue
        if plans[0][0] != 0 or any(plans[k][1] != plans[k + 1][0] for k in range(len(plans) - 1)):
            erreurs.append(f"{nom} : plans non contigus")
        if plans[-1][1] != int(duree):
            erreurs.append(f"{nom} : durée annoncée {duree} s ≠ fin du dernier plan {plans[-1][1]} s")
        if not 20 <= int(duree) <= 45:
            erreurs.append(f"{nom} : durée {duree} s hors de 20-45 s")
        if "Légende" not in bloc:
            erreurs.append(f"{nom} : légende absente")
    return erreurs


# ----------------------------------------------------------------------------- emails
def champs_registre() -> set[str]:
    registre = yaml.safe_load((REPO / "docs" / "04-legal" / "champs_a_remplir.yaml").read_text(encoding="utf-8"))
    return set(registre["champs"])


def verifier_email(nom: str, contenu: str, canal: str, categorie: str, connus: set[str]) -> list[str]:
    """Contrôles d'un modèle (HTML ou texte)."""
    erreurs = []
    corps = re.sub(r"<!--.*?-->", " ", contenu, flags=re.DOTALL)
    for motif, libelle in ((TERMES_INTERNES, "terme interne"), (EAN_RE, "EAN"), (URGENCE_RE, "fausse urgence"),
                           (PROMESSES_RE, "promesse interdite"), (PRIX_EN_DUR_RE, "prix en dur")):
        m = motif.search(corps)
        if m:
            erreurs.append(f"{nom} : {libelle} « {m.group(0)} »")
    if MENTION_COURTE not in corps:
        erreurs.append(f"{nom} : mention d'indépendance absente")
    if "{{RAISON_SOCIALE}}" not in corps or "{{ADRESSE_POSTALE}}" not in corps:
        erreurs.append(f"{nom} : identité de l'exploitant absente du pied")
    if categorie == "marketing" and ("url_desinscription" not in corps or "url_preferences" not in corps):
        erreurs.append(f"{nom} : lien de désinscription ou de préférences absent (email marketing)")
    inconnus = sorted(set(ge.CHAMP_RE.findall(contenu)) - connus - CHAMPS_HORS_REGISTRE)
    if inconnus:
        erreurs.append(f"{nom} : champs hors registre {inconnus}")
    if canal == "n8n" and "{%" in corps:
        erreurs.append(f"{nom} : balise Liquid dans un modèle n8n")
    if canal == "shopify" and "$json" in corps:
        erreurs.append(f"{nom} : variable n8n dans une notification Shopify")
    if nom.endswith(".html"):
        if re.search(r"<script|<style|var\(--", contenu):
            erreurs.append(f"{nom} : script, style ou var() interdit dans un email")
        a = analyser(contenu)
        erreurs += [f"{nom} : {e}" for e in a.erreurs]
        if a.imgs_sans_alt:
            erreurs.append(f"{nom} : image sans alt")
        if a.html_attrs.get("lang") != "fr-CH":
            erreurs.append(f"{nom} : lang=\"fr-CH\" absent")
    return erreurs


def verifier_emails() -> list[str]:
    erreurs = []
    try:
        source = ge.charger_source()
    except ge.EmailError as exc:
        return [f"source des emails invalide : {exc}"]
    attendus = ge.fichiers_generes()
    for chemin, contenu in attendus.items():
        if not chemin.exists() or chemin.read_text(encoding="utf-8") != contenu:
            erreurs.append(f"{chemin.relative_to(REPO).as_posix()} désynchronisé (relancer generer_emails.py)")
    orphelins = sorted(
        p.relative_to(REPO).as_posix()
        for d in ("html", "texte")
        for p in (ge.EMAILS / d).glob("*")
        if p not in attendus
    )
    erreurs += [f"{o} : fichier orphelin (absent de la source)" for o in orphelins]
    connus = champs_registre()
    for e in source["emails"]:
        for chemin in (ge.EMAILS / "html" / f"{e['id']}.html", ge.EMAILS / "texte" / f"{e['id']}.txt"):
            if chemin.exists():
                erreurs += verifier_email(chemin.name, chemin.read_text(encoding="utf-8"), e["canal"], e["categorie"], connus)
    if len(source["emails"]) < 13:
        erreurs.append("moins de 13 emails dans la source")
    return erreurs


# ----------------------------------------------------------------------------- publicité, créateurs, SEO
def verifier_publicite_seo() -> list[str]:
    erreurs = []
    pub = (RACINE / "PUBLICITE_TEST.md").read_text(encoding="utf-8")
    for element in ("500 CHF", "Plafond quotidien", "CAC", "commandes payées", "nettes", "Règles d'arrêt", "test-pub-c1", "test-pub-c2", "test-pub-c3"):
        if element not in pub:
            erreurs.append(f"PUBLICITE_TEST.md : « {element} » absent")
    createurs = (RACINE / "BRIEF_CREATEURS.md").read_text(encoding="utf-8")
    for element in ("Audience suisse", "exemples", "Droits d'utilisation", "code", "coût historique", "CAC"):
        if element.lower() not in createurs.lower():
            erreurs.append(f"BRIEF_CREATEURS.md : « {element} » absent")
    seo = (RACINE / "SEO.md").read_text(encoding="utf-8")
    m = VOLUME_RE.search(seo)
    if m:
        erreurs.append(f"SEO.md : volume de recherche chiffré « {m.group(0)} »")
    for element in ("PreOrder", "Page d'extension", "Méta-description"):
        if element not in seo:
            erreurs.append(f"SEO.md : « {element} » absent")
    return erreurs


def tout_verifier() -> dict[str, list[str]]:
    return {
        "documents": verifier_docs(),
        "calendrier": verifier_calendrier(),
        "15 sujets": verifier_sujets(),
        "scripts vidéo": verifier_scripts(),
        "emails": verifier_emails(),
        "publicité, créateurs, SEO": verifier_publicite_seo(),
    }


def main() -> int:
    total = 0
    for controle, erreurs in tout_verifier().items():
        print(f"[{'OK' if not erreurs else f'{len(erreurs)} erreur(s)'}] {controle}")
        for e in erreurs:
            print(f"    - {e}")
        total += len(erreurs)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
