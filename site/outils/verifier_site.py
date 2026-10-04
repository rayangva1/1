#!/usr/bin/env python3
"""Contrôles automatiques du périmètre site/ (landing, snippets Shopify, documents).

Contrôles :
1. HTML bien formé (balises équilibrées, identifiants uniques), en-tête complet (langue, titre, description,
   viewport), SEO de base (canonical, Open Graph) sur la page principale.
2. Ressources : relatives existantes ; externes limitées à Google Fonts ; liens et ancres valides.
3. Contenu public : aucun terme interne (coût, marge, fournisseur…), aucun prix, aucun EAN, aucune fausse
   urgence, aucune promesse de rareté ou de valeur, aucun bouton d'achat ou de précommande.
4. Formulaire : libellé pour chaque champ, consentement obligatoire et non pré-coché, champ piège, champs
   conformes à inscription.schema.json, bouton désactivé dans la source.
5. Mention d'indépendance identique à docs/04-legal/USAGE_MARQUES.md sur chaque page ; lien confidentialité.
6. Typographie française (espaces insécables) ; CSS sans couleur en dur ; JS sans URL en dur.
7. Synchronisation : copies DA (empreintes), pages secondaires générées.
8. Snippets Liquid : balises équilibrées, rendus existants, libellés de statut figés, aucun terme interdit.
9. Documents .md : dernière section « Validation humaine requise ».

Usage :
    python site/outils/verifier_site.py                         # dépôt
    python site/outils/verifier_site.py --dossier site/dist/landing   # dossier construit
Code de sortie 1 si une erreur est trouvée.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

OUTILS = Path(__file__).resolve().parent
sys.path.insert(0, str(OUTILS))

import da_sync  # noqa: E402
import publication  # noqa: E402
from typo import fautes  # noqa: E402

REPO = OUTILS.parents[1]
SITE = REPO / "site"
LANDING = SITE / "landing"
SNIPPETS = SITE / "shopify" / "snippets"
SCHEMA = LANDING / "inscription.schema.json"
USAGE_MARQUES = REPO / "docs" / "04-legal" / "USAGE_MARQUES.md"

HOTES_AUTORISES = {"fonts.googleapis.com", "fonts.gstatic.com"}
VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
TERMES_INTERNES = re.compile(
    r"\b(co[uû]ts?|marges?|margins?|costs?|prix d['’]achat|fournisseurs?|suppliers?|b2b|grossistes?|stock amont)\b",
    re.IGNORECASE,
)
PRIX_RE = re.compile(r"CHF\s*\d|\d+[.,]\d{2}\s*(CHF|\.-|fr\.)|\b\d+\.-", re.IGNORECASE)
EAN_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")
URGENCE_RE = re.compile(
    r"derni[eè]res?\s+pi[eè]ces|bient[ôo]t\s+[ée]puis|plus\s+que\s+\d|compte\s+[àa]\s+rebours|"
    r"offre\s+limit[ée]e|d[ée]p[êe]chez|stock\s+limit[ée]",
    re.IGNORECASE,
)
PROMESSES_RE = re.compile(
    r"investissement|prendra\s+de\s+la\s+valeur|rare\s+garanti|garanti[e]?s?\s+rares?|hits?\s+garantis?|"
    r"revendeur\s+agr[ée]{2}|partenaire\s+officiel|distributeur\s+officiel|produits?\s+officiels?",
    re.IGNORECASE,
)
ACHAT_RE = re.compile(r"\b(acheter|ajouter au panier|pr[ée]commander|r[ée]server|payer)\b", re.IGNORECASE)
ENCADRE_NEGATIONS_RE = re.compile(r'<div class="lp-encadre">.*?</div>', re.DOTALL)
COULEUR_EN_DUR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
COMMENTAIRE_CSS_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
PAGES_TOUJOURS_NOINDEX = {"merci.html", "inscription-confirmee.html", "desinscription.html"}
PAGES_TEXTE_LEGAL = {"confidentialite.html"}
LIBELLES_STATUT = ("Stock local", "Précommande (allocation confirmée)", "Rupture – alerte")


# ------------------------------------------------------------------------- analyse HTML
class Analyse(HTMLParser):
    """Collecte la structure utile d'une page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pile: list[str] = []
        self.erreurs: list[str] = []
        self.ids: list[str] = []
        self.ressources: list[tuple[str, str]] = []
        self.liens: list[str] = []
        self.meta: dict[str, str] = {}
        self.liens_head: dict[str, str] = {}
        self.html_attrs: dict[str, str] = {}
        self.titre = ""
        self.h1 = 0
        self.champs: list[dict[str, str]] = []
        self.labels_for: set[str] = set()
        self.dans_label = 0
        self.dans_piege = 0
        self.describedby: list[str] = []
        self.actions: list[tuple[str, str]] = []  # (balise, texte) des boutons et liens
        self._action_courante: list[str] | None = None
        self._dans_titre = False
        self.formulaires: list[dict[str, str]] = []
        self.imgs_sans_alt = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag not in VIDES:
            self.pile.append(tag)
        if "id" in a:
            self.ids.append(a["id"])
        if a.get("aria-describedby"):
            self.describedby.extend(a["aria-describedby"].split())
        if tag == "html":
            self.html_attrs = a
        elif tag == "title":
            self._dans_titre = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "meta":
            cle = a.get("name") or a.get("property") or ("charset" if "charset" in a else "")
            if cle:
                self.meta[cle] = a.get("content", a.get("charset", ""))
        elif tag == "link":
            rel = a.get("rel", "")
            if rel in ("canonical",):
                self.liens_head[rel] = a.get("href", "")
            elif a.get("href"):
                self.ressources.append((f"link[{rel}]", a["href"]))
        elif tag in ("img", "script", "source", "iframe", "embed", "audio", "video") and a.get("src"):
            self.ressources.append((tag, a["src"]))
            if tag == "img" and "alt" not in a:
                self.imgs_sans_alt += 1
        elif tag == "img":
            if "alt" not in a:
                self.imgs_sans_alt += 1
        if tag == "a" and a.get("href"):
            self.liens.append(a["href"])
        if tag == "label":
            self.dans_label += 1
            if a.get("for"):
                self.labels_for.add(a["for"])
        if tag == "div" and "lp-piege" in a.get("class", "").split():
            self.dans_piege += 1
            self.pile[-1] = "div#piege"
        if tag in ("input", "select", "textarea"):
            self.champs.append({**a, "_balise": tag, "_dans_label": str(self.dans_label > 0), "_piege": str(self.dans_piege > 0)})
        if tag == "form":
            self.formulaires.append(a)
        if tag in ("button", "a"):
            self._action_courante = [tag, ""]  # type: ignore[list-item]

    def handle_endtag(self, tag: str) -> None:
        if tag in VIDES:
            return
        if tag == "title":
            self._dans_titre = False
        if tag == "label":
            self.dans_label = max(0, self.dans_label - 1)
        if tag in ("button", "a") and self._action_courante is not None:
            self.actions.append((self._action_courante[0], self._action_courante[1].strip()))
            self._action_courante = None
        if not self.pile:
            self.erreurs.append(f"balise fermante </{tag}> sans ouverture")
            return
        haut = self.pile.pop()
        if haut == "div#piege":
            self.dans_piege -= 1
            haut = "div"
        if haut != tag:
            self.erreurs.append(f"balises imbriquées incorrectement : <{haut}> fermée par </{tag}>")

    def handle_data(self, data: str) -> None:
        if self._dans_titre:
            self.titre += data
        if self._action_courante is not None:
            self._action_courante[1] += data

    def close(self) -> None:
        super().close()
        if self.pile:
            self.erreurs.append(f"balises non fermées : {', '.join(self.pile)}")


def analyser(texte: str) -> Analyse:
    """Analyse un document HTML."""
    a = Analyse()
    a.feed(texte)
    a.close()
    return a


def _normaliser(texte: str) -> str:
    return re.sub(r"[\s  ]+", " ", texte).strip()


def _texte_visible(html: str) -> str:
    sans_commentaires = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    sans_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", sans_commentaires, flags=re.DOTALL)
    return _normaliser(re.sub(r"<[^>]+>", " ", sans_scripts))


def mention_reference() -> str:
    """Mention complète de USAGE_MARQUES.md, sans le nom (à partir de « est une boutique indépendante »)."""
    texte = USAGE_MARQUES.read_text(encoding="utf-8")
    m = re.search(r"\{\{NOM_BOUTIQUE\}\} (est une boutique indépendante\..*?revendons\.)", texte, re.DOTALL)
    if not m:
        raise ValueError("mention complète introuvable dans USAGE_MARQUES.md")
    return _normaliser(m.group(1))


# ------------------------------------------------------------------------- contrôles
def verifier_page(chemin: Path, racine: Path, *, publication_mode: bool = False) -> list[str]:
    """Toutes les vérifications d'une page HTML ; retourne les erreurs préfixées du nom du fichier."""
    nom = chemin.name
    texte = chemin.read_text(encoding="utf-8")
    a = analyser(texte)
    err = [f"{nom} : {e}" for e in a.erreurs]
    doublons = sorted({i for i in a.ids if a.ids.count(i) > 1})
    err += [f"{nom} : identifiant en double « {i} »" for i in doublons]

    # En-tête et SEO
    if a.html_attrs.get("lang") != "fr-CH":
        err.append(f"{nom} : <html lang=\"fr-CH\"> attendu")
    if a.html_attrs.get("data-da") not in ("a", "b"):
        err.append(f"{nom} : data-da absent sur <html>")
    for cle in ("charset", "viewport", "description"):
        if not a.meta.get(cle):
            err.append(f"{nom} : meta {cle} absente")
    if not a.titre.strip():
        err.append(f"{nom} : <title> vide")
    if a.h1 != 1:
        err.append(f"{nom} : {a.h1} titre(s) h1 (1 attendu)")
    if a.imgs_sans_alt:
        err.append(f"{nom} : {a.imgs_sans_alt} image(s) sans attribut alt")
    noindex = "noindex" in a.meta.get("robots", "")
    if nom in PAGES_TOUJOURS_NOINDEX and not noindex:
        err.append(f"{nom} : page de service sans noindex")
    if publication_mode and nom not in PAGES_TOUJOURS_NOINDEX and noindex:
        err.append(f"{nom} : noindex resté dans un dossier de publication")
    if nom == "index.html":
        for cle in ("og:title", "og:description", "og:image", "og:url", "og:type", "twitter:card"):
            if not a.meta.get(cle):
                err.append(f"{nom} : meta {cle} absente")
        if not a.liens_head.get("canonical"):
            err.append(f"{nom} : lien canonical absent")

    # Ressources et liens
    for balise, url in a.ressources:
        if "{{" in url or "⟦" in url or url.startswith("data:"):
            continue
        u = urlparse(url)
        if u.scheme in ("http", "https"):
            if u.hostname not in HOTES_AUTORISES:
                err.append(f"{nom} : ressource externe non autorisée {balise} {url}")
        elif u.scheme == "" and not (chemin.parent / u.path).exists():
            err.append(f"{nom} : ressource introuvable {url}")
    for url in a.liens:
        if "{{" in url or "⟦" in url:
            continue
        u = urlparse(url)
        if u.scheme in ("mailto",):
            continue
        if u.scheme == "http":
            err.append(f"{nom} : lien non sécurisé {url}")
            continue
        if u.scheme == "https":
            continue
        cible = chemin if not u.path else chemin.parent / u.path
        if cible.is_dir():
            cible = cible / "index.html"
        if not cible.exists():
            err.append(f"{nom} : lien relatif cassé {url}")
        elif u.fragment:
            ids_cible = a.ids if cible.resolve() == chemin.resolve() else analyser(cible.read_text(encoding="utf-8")).ids
            if u.fragment not in ids_cible:
                err.append(f"{nom} : ancre introuvable {url}")
    if "confidentialite.html" not in a.liens:
        err.append(f"{nom} : lien vers confidentialite.html absent")
    err += [f"{nom} : aria-describedby vers un identifiant absent « {i} »" for i in a.describedby if i not in a.ids]

    # Contenu public
    visible = _texte_visible(texte)
    scan = _texte_visible(ENCADRE_NEGATIONS_RE.sub(" ", texte))
    for motif, libelle in (
        # Le texte légal (confidentialite.html) emploie « fournisseur » au sens de prestataire (IA, paiement) :
        # il est rédigé et relu dans docs/04-legal ; seuls prix, EAN, urgence et promesses y sont contrôlés ici.
        (TERMES_INTERNES if nom not in PAGES_TEXTE_LEGAL else None, "terme interne"),
        (PRIX_RE, "prix"),
        (EAN_RE, "nombre à 13 chiffres (EAN ?)"),
        (URGENCE_RE, "fausse urgence"),
        (PROMESSES_RE, "promesse interdite"),
    ):
        if motif is None:
            continue
        m = motif.search(scan if motif in (URGENCE_RE,) else visible)
        if m:
            err.append(f"{nom} : {libelle} « {m.group(0)} »")
    for balise, libelle in a.actions:
        if ACHAT_RE.search(libelle):
            err.append(f"{nom} : action d'achat ou de précommande « {libelle} » sur la landing")
    reference = mention_reference()
    mentions = re.findall(r'id="mention-independance">(.*?)</p>', texte, re.DOTALL)
    if not mentions or not _normaliser(re.sub(r"<[^>]+>", "", mentions[0])).endswith(reference):
        err.append(f"{nom} : mention d'indépendance absente ou différente de USAGE_MARQUES.md")
    if "Exploitant" not in visible:
        err.append(f"{nom} : identité de l'exploitant absente du pied de page")
    err += [f"{nom} : espace insécable manquante « {f} »" for f in fautes(texte)]
    if publication_mode:
        for motif, libelle in (("{{", "champ {{…}} non rempli"), ("⟦", "marque ⟦…⟧"), ("APERCU:", "bloc d'aperçu")):
            if motif in texte:
                err.append(f"{nom} : {libelle}")

    # Formulaire (page principale)
    if nom == "index.html":
        err += [f"{nom} : {e}" for e in verifier_formulaire(a, publication_mode=publication_mode)]
    return err


def verifier_formulaire(a: Analyse, *, publication_mode: bool) -> list[str]:
    """Règles du formulaire d'inscription (protocole landing §3, BP §7 consentement)."""
    err: list[str] = []
    if len(a.formulaires) != 1:
        return [f"{len(a.formulaires)} formulaire(s) (1 attendu)"]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    proprietes = set(schema["properties"])
    noms = {c.get("name", "") for c in a.champs if c.get("name")}
    hors_schema = sorted(n for n in noms if n not in proprietes)
    if hors_schema:
        err.append(f"champs absents de inscription.schema.json : {hors_schema}")
    manquants = sorted(set(schema["required"]) - noms)
    if manquants:
        err.append(f"champs obligatoires du schéma absents du formulaire : {manquants}")
    for c in a.champs:
        if c.get("type") == "hidden" or c["_piege"] == "True":
            continue
        if c.get("id") not in a.labels_for and c["_dans_label"] != "True":
            err.append(f"champ sans libellé : {c.get('name') or c.get('id')}")
    consentement = [c for c in a.champs if c.get("name") == "consentement"]
    if len(consentement) != 1:
        err.append("case de consentement absente")
    else:
        c = consentement[0]
        if c.get("type") != "checkbox":
            err.append("le consentement doit être une case à cocher")
        if "checked" in c:
            err.append("case de consentement pré-cochée")
        if "required" not in c:
            err.append("case de consentement non obligatoire")
    email = [c for c in a.champs if c.get("name") == "email"]
    if not email or email[0].get("type") != "email" or "required" not in email[0]:
        err.append("champ email obligatoire de type email attendu")
    if not any(c["_piege"] == "True" and c.get("tabindex") == "-1" for c in a.champs):
        err.append("champ piège (anti-robots) absent")
    form = a.formulaires[0]
    if publication_mode:
        if not publication.webhook_valide(form.get("action")):
            err.append("formulaire publié sans action vers le webhook")
    elif form.get("action"):
        err.append("la source ne doit pas contenir d'URL d'envoi (elle est posée à la publication)")
    return err


def verifier_bouton_source(texte: str) -> list[str]:
    """Dans la source, le bouton d'envoi est désactivé (le script l'active si le webhook est valide)."""
    m = re.search(r'<button[^>]*id="lp-envoyer"[^>]*>', texte)
    if not m:
        return ["index.html : bouton d'envoi lp-envoyer absent"]
    if " disabled" not in m.group(0):
        return ["index.html : bouton d'envoi actif dans la source (doit être disabled)"]
    return []


def verifier_css_js(racine: Path, *, publication_mode: bool = False) -> list[str]:
    """CSS sans couleur en dur ; JS sans URL en dur ; configuration source sans webhook."""
    err: list[str] = []
    for css in sorted((racine / "css").glob("*.css")):
        code = COMMENTAIRE_CSS_RE.sub("", css.read_text(encoding="utf-8"))
        m = COULEUR_EN_DUR_RE.search(code)
        if m:
            err.append(f"css/{css.name} : couleur en dur « {m.group(0)} » (utiliser les variables --da-*)")
    for js in sorted((racine / "js").glob("*.js")):
        code = js.read_text(encoding="utf-8")
        if js.name != "config.js" and re.search(r"https?://", code):
            err.append(f"js/{js.name} : URL en dur")
        if "localStorage" in code and "try" not in code:
            err.append(f"js/{js.name} : accès au stockage local sans try/catch")
    config = (racine / "js" / "config.js").read_text(encoding="utf-8")
    m = re.search(r'webhookUrl:\s*"([^"]*)"', config)
    if not m:
        err.append("js/config.js : webhookUrl introuvable")
    elif not publication_mode and m.group(1):
        err.append("js/config.js : la source ne doit pas contenir d'URL de webhook")
    elif publication_mode and not publication.webhook_valide(m.group(1)):
        err.append("js/config.js : webhook absent ou invalide dans un dossier de publication")
    return err


def verifier_landing(racine: Path = LANDING, *, publication_mode: bool = False) -> list[str]:
    """Toutes les pages + CSS/JS d'un dossier de landing."""
    pages = sorted(racine.glob("*.html"))
    if not (racine / "index.html").exists():
        return [f"{racine} : index.html absent"]
    err: list[str] = []
    for p in pages:
        err += verifier_page(p, racine, publication_mode=publication_mode)
    if not publication_mode:
        err += verifier_bouton_source((racine / "index.html").read_text(encoding="utf-8"))
    err += verifier_css_js(racine, publication_mode=publication_mode)
    if publication_mode and not (racine / "_headers").exists():
        err.append("_headers absent du dossier de publication")
    return err


def verifier_generes(racine: Path = LANDING) -> list[str]:
    """Pages secondaires identiques à ce que produit publication.py (mode source)."""
    direction = json.loads((racine / "assets" / "da" / "manifeste.json").read_text(encoding="utf-8"))["direction"]
    url_fonts = da_sync.google_fonts(direction).replace("&", "&amp;")
    err = []
    for nom, attendu in publication.pages_secondaires().items():
        attendu = attendu.replace('data-da="a"', f'data-da="{direction}"', 1)
        attendu = da_sync.GOOGLE_FONTS_RE.sub(f'href="{url_fonts}"', attendu)
        chemin = racine / nom
        if not chemin.exists():
            err.append(f"{nom} absent (lancer publication.py source)")
        elif chemin.read_text(encoding="utf-8") != attendu:
            err.append(f"{nom} désynchronisé du générateur ou de docs/04-legal (lancer publication.py source)")
    return err


# ------------------------------------------------------------------------- Liquid
BALISES_BLOC = {"if": "endif", "unless": "endunless", "case": "endcase", "for": "endfor", "capture": "endcapture",
                "form": "endform", "comment": "endcomment", "raw": "endraw", "paginate": "endpaginate", "tablerow": "endtablerow"}
TAG_LIQUID_RE = re.compile(r"\{%-?\s*(\w+)(.*?)-?%\}", re.DOTALL)


def _blocs_liquid(texte: str) -> list[str]:
    """Erreurs d'équilibre des balises Liquid (y compris dans {% liquid %})."""
    err: list[str] = []
    pile: list[str] = []
    jetons: list[str] = []
    for m in TAG_LIQUID_RE.finditer(texte):
        nom, reste = m.group(1), m.group(2)
        if nom == "liquid":
            jetons += [ligne.strip().split()[0] for ligne in reste.splitlines() if ligne.strip()]
        else:
            jetons.append(nom)
    for nom in jetons:
        if nom in BALISES_BLOC:
            pile.append(nom)
        elif nom in BALISES_BLOC.values():
            if not pile or BALISES_BLOC[pile[-1]] != nom:
                err.append(f"« {nom} » sans ouverture correspondante")
            else:
                pile.pop()
    if pile:
        err.append(f"blocs non fermés : {pile}")
    if texte.count("{{") != texte.count("}}"):
        err.append("accolades {{ }} déséquilibrées")
    return err


def verifier_liquid(dossier: Path = SNIPPETS) -> list[str]:
    """Contrôle statique des snippets Liquid."""
    err: list[str] = []
    snippets = sorted(dossier.glob("*.liquid"))
    if not snippets:
        return [f"{dossier} : aucun snippet"]
    noms = {p.stem for p in snippets}
    for p in snippets:
        texte = p.read_text(encoding="utf-8")
        err += [f"{p.name} : {e}" for e in _blocs_liquid(texte)]
        if not re.match(r"\{%-?\s*comment\s*-?%\}", texte):
            err.append(f"{p.name} : doit commencer par un bloc de documentation {{% comment %}}")
        sortie = re.sub(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", " ", texte, flags=re.DOTALL)
        for motif, libelle in ((TERMES_INTERNES, "terme interne"), (PRIX_RE, "prix en dur"), (EAN_RE, "EAN en dur"),
                               (URGENCE_RE, "fausse urgence"), (PROMESSES_RE, "promesse interdite")):
            m = motif.search(sortie)
            if m:
                err.append(f"{p.name} : {libelle} « {m.group(0)} »")
        for rendu in re.findall(r"render\s+'([\w-]+)'", texte):
            if rendu not in noms:
                err.append(f"{p.name} : render vers un snippet absent « {rendu} »")
        if "include " in sortie:
            err.append(f"{p.name} : « include » est obsolète, utiliser « render »")
        if "metafields" in sortie and re.search(r"metafields\.(?!boutique\.)", sortie):
            err.append(f"{p.name} : métachamp hors de l'espace public « boutique »")
    statut = dossier / "da-statut-stock.liquid"
    if statut.exists():
        t = statut.read_text(encoding="utf-8")
        err += [f"da-statut-stock.liquid : libellé « {lib} » absent" for lib in LIBELLES_STATUT if lib not in t]
    return err


# ------------------------------------------------------------------------- documents
def verifier_docs(racine: Path = SITE) -> list[str]:
    """Chaque .md de site/ se termine par « Validation humaine requise »."""
    err = []
    for p in sorted(racine.rglob("*.md")):
        if "dist" in p.relative_to(racine).parts:
            continue
        titres = re.findall(r"^#{1,3} .*$", p.read_text(encoding="utf-8"), re.MULTILINE)
        if not titres or "Validation humaine requise" not in titres[-1]:
            err.append(f"{p.relative_to(REPO).as_posix()} : dernière section ≠ « Validation humaine requise »")
    return err


def tout_verifier() -> dict[str, list[str]]:
    """Exécute tous les contrôles du dépôt ; {contrôle: erreurs}."""
    return {
        "landing": verifier_landing(LANDING),
        "pages générées": verifier_generes(LANDING),
        "copies DA": da_sync.verifier(),
        "snippets Liquid": verifier_liquid(SNIPPETS),
        "documents": verifier_docs(SITE),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dossier", type=Path, default=None, help="vérifier un dossier construit (apercu ou publication)")
    args = parser.parse_args(argv)
    if args.dossier:
        config = (args.dossier / "js" / "config.js").read_text(encoding="utf-8")
        pub = 'mode: "publication"' in config
        resultats = {f"dossier {'publication' if pub else 'apercu'}": verifier_landing(args.dossier, publication_mode=pub)}
    else:
        resultats = tout_verifier()
    total = 0
    for controle, erreurs in resultats.items():
        statut = "OK" if not erreurs else f"{len(erreurs)} erreur(s)"
        print(f"[{statut}] {controle}")
        for e in erreurs:
            print(f"    - {e}")
        total += len(erreurs)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
