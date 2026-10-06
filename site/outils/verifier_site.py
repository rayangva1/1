#!/usr/bin/env python3
"""Contrôles automatiques du périmètre site/ (landing, snippets Shopify, documents).

Contrôles :
1. HTML bien formé (balises équilibrées, identifiants uniques), en-tête complet (langue, titre, description,
   viewport), SEO de base (canonical, Open Graph) sur la page principale.
2. Ressources : relatives existantes ; externes limitées à Google Fonts ; liens et ancres valides. Visuels de la
   marque (balises ``data-visuel``) : adresse distante de ``site/config/visuels.json`` admise en source et en aperçu
   seulement, jamais dans un dossier de publication ; balises synchronisées avec le manifeste. Images : ``width`` et
   ``height`` (pas de décalage de mise en page), ``loading="lazy"`` sauf l'image principale (``fetchpriority="high"``).
3. Contenu public : aucun terme interne (coût, marge, fournisseur…), aucun prix, aucun EAN, aucune fausse
   urgence, aucune promesse de rareté ou de valeur, aucun bouton d'achat ou de précommande.
4. Formulaire : libellé pour chaque champ, consentement obligatoire et non pré-coché, champ piège, champs
   conformes à inscription.schema.json, bouton désactivé dans la source.
5. Mention d'indépendance identique à docs/04-legal/USAGE_MARQUES.md sur chaque page ; lien confidentialité.
6. Typographie française (espaces insécables) ; CSS sans couleur en dur ; JS sans URL en dur.
7. Synchronisation : copies DA (empreintes), pages secondaires générées.
8. Snippets Liquid : balises équilibrées, rendus existants, libellés de statut figés, aucun terme interdit.
9. Documents .md : dernière section « Validation humaine requise ».
10. Affirmations inexactes : « une personne vous répond » (les réponses courantes sont automatisées),
    « le contenu de chaque boîte est vérifié » (les produits ne sont jamais ouverts), exclusivité de finalité
    (« servent uniquement à ces envois ») alors que le formulaire collecte des réponses facultatives.
11. Notice de confidentialité : chaque champ du formulaire d'inscription y est déclaré (liste fermée
    CHAMPS_NOTICE : un nouveau champ sans entrée fait échouer le contrôle).
12. Nom de travail : jamais dans un modèle Shopify (fiches, snippets) hors des notes d'en-tête.
13. Message sans JavaScript exact (revue NEW-04) : la page publiée ne dit jamais que le formulaire « nécessite
    JavaScript » (il fonctionne sans script, redirection 303).
14. Landing publiable à J10 (revue CON-06) : chaque champ de ``CHAMPS_LANDING`` est fourni par une intervention
    ou une tâche planifiée au plus tard à J10 (``INTERVENTIONS_HUMAINES.md``, ``BACKLOG.csv``).
15. Workflow d'inscription (revue NEW-05) : dès que son export existe dans ``orchestration/n8n/``, il ne conserve
    aucune exécution (``saveDataSuccessExecution`` et ``saveDataErrorExecution`` = ``none``), condition de la
    promesse de la notice sur l'adresse IP (« effacées après le contrôle »).
16. Maquettes (``site/maquettes/``, jamais publiées) : page non indexée et bandeau « Maquette FICTIVE » ; chaque
    prix et chaque date suivis de la mention FICTIF (ou, pour une date, « date estimée ») ; textes de garantie du
    pré-drop repris mot pour mot du moteur (``GUARANTEE_TEXT_FR``, ``NO_DIFFERENCE_REFUND_FR``) ; statut limité à
    « Réservations ouvertes / fermées » ; aucune fausse urgence, promesse interdite, terme interne ni affirmation
    inexacte ; mention d'indépendance ; aucun formulaire qui envoie ; ressources, liens et typographie contrôlés.

Usage :
    python site/outils/verifier_site.py                         # dépôt
    python site/outils/verifier_site.py --dossier site/dist/landing   # dossier construit
Code de sortie 1 si une erreur est trouvée.
"""

from __future__ import annotations

import argparse
import csv
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
import visuels  # noqa: E402
from typo import fautes  # noqa: E402

REPO = OUTILS.parents[1]
SITE = REPO / "site"
LANDING = SITE / "landing"
MAQUETTES = SITE / "maquettes"
PREDROP_MOTEUR = REPO / "engine" / "pokeshop" / "predrop.py"
SNIPPETS = SITE / "shopify" / "snippets"
SCHEMA = LANDING / "inscription.schema.json"
USAGE_MARQUES = REPO / "docs" / "04-legal" / "USAGE_MARQUES.md"
INTERVENTIONS = REPO / "docs" / "00-pilotage" / "INTERVENTIONS_HUMAINES.md"
BACKLOG = REPO / "docs" / "00-pilotage" / "BACKLOG.csv"
WORKFLOWS_N8N = REPO / "orchestration" / "n8n"
JOUR_PUBLICATION_LANDING = 10

HOTES_AUTORISES = {"fonts.googleapis.com", "fonts.gstatic.com"}
VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
TERMES_INTERNES = re.compile(
    r"\b(co[uû]ts?|marges?|margins?(?![-:\w])|costs?|prix d['’]achat|fournisseurs?|suppliers?|b2b|grossistes?|stock amont)\b",
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
    r"investissement|prendra\s+de\s+la\s+valeur|rares?\s+garanti(?:es?|s)?\b(?![\s\u00a0\u202f]*\?)|garanti[e]?s?\s+rares?|hits?\s+garantis?|"
    r"revendeur\s+agr[ée]{2}|partenaire\s+officiel|distributeur\s+officiel|produits?\s+officiels?",
    re.IGNORECASE,
)
ACHAT_RE = re.compile(r"\b(acheter|ajouter au panier|pr[ée]commander|r[ée]server|payer)\b", re.IGNORECASE)
#: Affirmations publiques inexactes au regard du modèle d'opération (LCD art. 3 al. 1 let. b).
AFFIRMATIONS_INEXACTES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:une|un)[\s\u00a0\u202f]+(?:vraie[\s\u00a0\u202f]+)?(?:personne|humain)[\s\u00a0\u202f]+(?:vous[\s\u00a0\u202f]+)?r[ée]pond", re.IGNORECASE),
        "affirmation inexacte sur le service client (réponses courantes automatisées)",
    ),
    (
        re.compile(r"contenu[\s\u00a0\u202f]+(?:de[\s\u00a0\u202f]+chaque|des|de[\s\u00a0\u202f]+la)[\s\u00a0\u202f]+bo[iî]tes?[\s\u00a0\u202f]+(?:est|sont)[\s\u00a0\u202f]+(?:v[ée]rifi|contr[ôo]l)", re.IGNORECASE),
        "sur-promesse de contrôle (seul le contenu annoncé sur l'emballage est vérifié, sans ouvrir)",
    ),
    (
        re.compile(r"servent[\s\u00a0\u202f]+uniquement|uniquement[\s\u00a0\u202f]+(?:pour|à)[\s\u00a0\u202f]+(?:ces|les)[\s\u00a0\u202f]+envois", re.IGNORECASE),
        "exclusivité de finalité inexacte (réponses facultatives et origine aussi utilisées, en agrégé)",
    ),
    (
        re.compile(
            r"(?:\{\{\s*qmax\s*\}\}|\blimite\b[^.\n<]{0,40}?|\bmax(?:imum\b|\.|\b))[\s\u00a0\u202f]*par[\s\u00a0\u202f]+commande\b",
            re.IGNORECASE,
        ),
        "limite de quantité exprimée « par commande » (CGV ch. 4.4 : par référence et par foyer, toutes commandes confondues)",
    ),
)
#: Champs du formulaire d'inscription → terme qui doit figurer dans la notice de confidentialité publiée
#: (None : champ technique sans donnée personnelle). Un champ absent de cette liste fait échouer le contrôle.
CHAMPS_NOTICE: dict[str, str | None] = {
    "email": "email",
    "prenom": "prénom",
    "formats": "formats",
    "budget": "budget",
    "pour_qui": "pour qui",
    "canton": "canton",
    "consentement": "consentement",
    "consentement_texte": "consentement",
    "consentement_version": "consentement",
    "horodatage_client": "date",
    "page": "page d'inscription",
    "utm_source": "utm",
    "utm_medium": "utm",
    "utm_campaign": "utm",
    "source": None,
    "site_web": None,
}
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
        self.imgs: list[dict[str, str]] = []
        self.ressources_visuels: list[tuple[str, str]] = []

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
            elif a.get("href") and "data-visuel" in a:
                self.ressources_visuels.append((f"link[{rel}]", a["href"]))
            elif a.get("href"):
                self.ressources.append((f"link[{rel}]", a["href"]))
        elif tag in ("img", "source") and "data-visuel" in a:
            for cle in ("src", "srcset"):
                for morceau in (a.get(cle) or "").split(","):
                    if morceau.strip():
                        self.ressources_visuels.append((tag, morceau.split()[0]))
            if tag == "img":
                self.imgs.append(a)
                if "alt" not in a:
                    self.imgs_sans_alt += 1
        elif tag in ("img", "script", "source", "iframe", "embed", "audio", "video") and a.get("src"):
            self.ressources.append((tag, a["src"]))
            if tag == "img":
                self.imgs.append(a)
                if "alt" not in a:
                    self.imgs_sans_alt += 1
        elif tag == "img":
            self.imgs.append(a)
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
    err += [f"{nom} : {e}" for e in verifier_visuels_page(a, chemin, publication_mode=publication_mode)]
    err += [f"{nom} : {e}" for e in verifier_images(a)]
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
    for motif, libelle in AFFIRMATIONS_INEXACTES:
        m = motif.search(visible)
        if m:
            err.append(f"{nom} : {libelle} « {m.group(0)} »")
    if nom not in PAGES_TEXTE_LEGAL:
        err += [f"{nom} : {e}" for e in verifier_textes_garantie(visible)]
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
        for residu, libelle in (("{{", "champ {{…}} non rempli"), ("⟦", "marque ⟦…⟧"), ("APERCU:", "bloc d'aperçu")):
            if residu in texte:
                err.append(f"{nom} : {libelle}")

    # Formulaire (page principale)
    if nom == "index.html":
        err += [f"{nom} : {e}" for e in verifier_formulaire(a, publication_mode=publication_mode)]
        err += [f"{nom} : {e}" for e in verifier_noscript(texte, publication_mode=publication_mode)]
    return err


def _hote_visuels() -> str | None:
    try:
        return urlparse(visuels.charger()["base_distante"]).hostname
    except (OSError, ValueError, KeyError):
        return None


def verifier_visuels_page(a: Analyse, chemin: Path, *, publication_mode: bool) -> list[str]:
    """Adresses des balises data-visuel : distantes (hôte du manifeste) en aperçu seulement, locales existantes."""
    err: list[str] = []
    hote = _hote_visuels()
    for balise, url in a.ressources_visuels:
        if "{{" in url or url.startswith("data:"):
            continue
        u = urlparse(url)
        if u.scheme in ("http", "https"):
            if publication_mode:
                err.append(f"visuel distant dans un dossier de publication {balise} {url} "
                           "(lancer site/outils/rapatrier_visuels.py avant de publier)")
            elif u.scheme != "https" or u.hostname != hote:
                err.append(f"ressource externe non autorisée {balise} {url} (hôte hors de site/config/visuels.json)")
        elif u.scheme == "" and not (chemin.parent / u.path).exists():
            err.append(f"visuel introuvable {url}")
    return err


def verifier_images(a: Analyse) -> list[str]:
    """Images : dimensions déclarées ; chargement paresseux sauf l'image principale (au plus une par page)."""
    err: list[str] = []
    prioritaires = [i for i in a.imgs if i.get("fetchpriority") == "high"]
    if len(prioritaires) > 1:
        err.append(f"{len(prioritaires)} images en fetchpriority=\"high\" (une seule image principale attendue)")
    for i in a.imgs:
        nom = i.get("data-visuel") or i.get("src", "?")
        if not i.get("width") or not i.get("height"):
            err.append(f"image sans width/height (décalage de mise en page) : {nom}")
        if "data-visuel" in i and i.get("fetchpriority") != "high" and i.get("loading") != "lazy":
            err.append(f"visuel sans loading=\"lazy\" (seule l'image principale se charge d'emblée) : {nom}")
    return err


NOSCRIPT_RE = re.compile(r"<noscript>(.*?)</noscript>", re.DOTALL)
FORM_ACTION_RE = re.compile(r'<form[^>]*\saction="([^"]*)"')


def verifier_noscript(texte: str, *, publication_mode: bool) -> list[str]:
    """Le message sans JavaScript dit vrai (revue NEW-04).

    Page publiée (``action`` du formulaire renseignée) : le formulaire fonctionne sans script, donc aucun
    message « nécessite JavaScript » ni « n'envoie rien », et aucun marqueur de publication restant. Source et
    aperçu : le message d'aperçu est entre marqueurs APERCU (jamais publié).
    """
    err: list[str] = []
    messages = [m.lower() for m in NOSCRIPT_RE.findall(texte)]
    action = FORM_ACTION_RE.search(texte)
    if publication_mode or (action and action.group(1).strip()):
        for m in messages:
            if "nécessite javascript" in m or "n'envoie rien" in m or "n’envoie rien" in m:
                err.append("message sans JavaScript faux : le formulaire publié fonctionne sans script")
        if "PUBLICATION:NOSCRIPT" in texte:
            err.append("marqueur PUBLICATION:NOSCRIPT resté dans la page publiée")
        if not messages:
            err.append("message sans JavaScript absent de la page publiée")
    else:
        for bloc in NOSCRIPT_RE.finditer(texte):
            if "nécessite javascript" in bloc.group(1).lower():
                err.append("message « nécessite JavaScript » hors aperçu : il serait publié alors que le formulaire "
                           "publié fonctionne sans script")
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


def verifier_notice_formulaire(racine: Path = LANDING) -> list[str]:
    """Chaque champ du formulaire (et du contrat inscription.schema.json) est déclaré dans la notice publiée."""
    index, notice = racine / "index.html", racine / "confidentialite.html"
    if not index.exists() or not notice.exists():
        return ["index.html ou confidentialite.html absent : contrôle de la notice impossible"]
    noms = {c.get("name", "") for c in analyser(index.read_text(encoding="utf-8")).champs if c.get("name")}
    noms |= set(json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"])
    texte = _texte_visible(notice.read_text(encoding="utf-8")).lower()
    err: list[str] = []
    for nom in sorted(noms):
        if nom not in CHAMPS_NOTICE:
            err.append(f"champ « {nom} » collecté sans entrée dans CHAMPS_NOTICE : le déclarer dans la notice puis ici")
        elif CHAMPS_NOTICE[nom] and CHAMPS_NOTICE[nom] not in texte:
            err.append(f"champ « {nom} » collecté mais absent de la notice de confidentialité (« {CHAMPS_NOTICE[nom]} »)")
    return err


def verifier_nom_de_travail(dossier: Path = SITE / "shopify") -> list[str]:
    """Le nom de travail n'apparaît dans aucun modèle Shopify publiable (seulement dans les notes d'en-tête « > »)."""
    err: list[str] = []
    nom = publication.NOM_DE_TRAVAIL

    def rel(p: Path) -> str:
        return p.relative_to(REPO).as_posix() if p.is_relative_to(REPO) else p.relative_to(dossier).as_posix()

    for p in sorted(dossier.rglob("*.md")):
        for i, ligne in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if nom in ligne and not ligne.lstrip().startswith(">"):
                err.append(f"{rel(p)}:{i} : nom de travail « {nom} » dans un modèle ({{{{NOM_BOUTIQUE}}}} attendu)")
    for p in sorted(dossier.rglob("*.liquid")):
        sortie = re.sub(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", " ", p.read_text(encoding="utf-8"), flags=re.DOTALL)
        if nom in sortie:
            err.append(f"{rel(p)} : nom de travail « {nom} » dans un snippet")
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
    err += verifier_notice_formulaire(racine)
    if publication_mode and not (racine / "_headers").exists():
        err.append("_headers absent du dossier de publication")
    return err


def verifier_generes(racine: Path = LANDING) -> list[str]:
    """Pages secondaires identiques à ce que produit publication.py (mode source)."""
    direction, ambiance = da_sync.lire_manifeste(racine / "assets" / "da")
    err = []
    for nom, attendu in publication.pages_secondaires().items():
        attendu = da_sync.aligner_html(attendu, direction, ambiance)
        chemin = racine / nom
        if not chemin.exists():
            err.append(f"{nom} absent (lancer publication.py source)")
        elif chemin.read_text(encoding="utf-8") != attendu:
            err.append(f"{nom} désynchronisé du générateur ou de docs/04-legal (lancer publication.py source)")
    return err


# ------------------------------------------------------------------------- maquettes
DATE_RE = re.compile(r"(?<![\d.])\d{2}\.\d{2}(?:\.\d{4})?(?![\d.])")
#: Statuts publics du pré-drop : « Réservations ouvertes » ou « Réservations fermées », rien d'autre (moteur,
#: STATUS_OPEN_FR / STATUS_CLOSED_FR) ; jamais un état qui presse (« bientôt complètes », « dernières »…).
STATUT_RESA_INTERDIT_RE = re.compile(
    r"r[ée]servations?[\s\u00a0\u202f]+(?:presque|bient[ôo]t|derni[eè]res?|limit[ée]es?|compl[eè]tes?|[ée]puis[ée]es?|restantes?)",
    re.IGNORECASE,
)


def textes_garantie_moteur(chemin: Path = PREDROP_MOTEUR) -> tuple[str, str]:
    """(GUARANTEE_TEXT_FR, NO_DIFFERENCE_REFUND_FR) lus dans le moteur sans l'importer (source unique)."""
    import ast

    valeurs: dict[str, str] = {}
    for noeud in ast.parse(chemin.read_text(encoding="utf-8")).body:
        if isinstance(noeud, ast.Assign) and len(noeud.targets) == 1 and isinstance(noeud.targets[0], ast.Name):
            nom = noeud.targets[0].id
            if nom in ("GUARANTEE_TEXT_FR", "NO_DIFFERENCE_REFUND_FR"):
                valeurs[nom] = str(ast.literal_eval(noeud.value))
    return valeurs["GUARANTEE_TEXT_FR"], valeurs["NO_DIFFERENCE_REFUND_FR"]


def verifier_textes_garantie(visible: str) -> list[str]:
    """Une page qui parle de réservation garantie reprend mot pour mot les deux phrases du moteur."""
    if "servation garantie" not in visible:
        return []
    garantie, difference = (_normaliser(x) for x in textes_garantie_moteur())
    return [
        f"texte de garantie du moteur absent ou modifié ({libelle})"
        for phrase, libelle in ((garantie, "GUARANTEE_TEXT_FR"), (difference, "NO_DIFFERENCE_REFUND_FR"))
        if phrase not in visible
    ]


def _sans_fictif_proche(visible: str, motif: re.Pattern[str], autorises: tuple[str, ...], fenetre: int = 48) -> list[str]:
    manquants = []
    for m in motif.finditer(visible):
        apres = visible[m.end() : m.end() + fenetre]
        if not any(a in apres for a in autorises):
            manquants.append(m.group(0))
    return manquants


def verifier_maquette(chemin: Path) -> list[str]:
    """Contrôles d'une maquette (page de démonstration FICTIVE, jamais publiée)."""
    nom = f"maquettes/{chemin.name}"
    texte = chemin.read_text(encoding="utf-8")
    a = analyser(texte)
    err = [f"{nom} : {e}" for e in a.erreurs]
    err += [f"{nom} : identifiant en double « {i} »" for i in sorted({i for i in a.ids if a.ids.count(i) > 1})]
    if a.html_attrs.get("lang") != "fr-CH":
        err.append(f"{nom} : <html lang=\"fr-CH\"> attendu")
    for cle in ("charset", "viewport", "description"):
        if not a.meta.get(cle):
            err.append(f"{nom} : meta {cle} absente")
    if a.h1 != 1:
        err.append(f"{nom} : {a.h1} titre(s) h1 (1 attendu)")
    if a.imgs_sans_alt:
        err.append(f"{nom} : {a.imgs_sans_alt} image(s) sans attribut alt")
    if "noindex" not in a.meta.get("robots", ""):
        err.append(f"{nom} : maquette sans noindex")
    for balise, url in a.ressources:
        u = urlparse(url)
        if u.scheme in ("http", "https"):
            if u.hostname not in HOTES_AUTORISES:
                err.append(f"{nom} : ressource externe non autorisée {balise} {url}")
        elif u.scheme == "" and not (chemin.parent / u.path).exists():
            err.append(f"{nom} : ressource introuvable {url}")
    for url in a.liens:
        u = urlparse(url)
        if u.scheme in ("mailto", "https"):
            continue
        if u.scheme == "http":
            err.append(f"{nom} : lien non sécurisé {url}")
            continue
        cible = chemin if not u.path else chemin.parent / u.path
        if not cible.exists():
            err.append(f"{nom} : lien relatif cassé {url}")
        elif u.fragment:
            ids = a.ids if cible.resolve() == chemin.resolve() else analyser(cible.read_text(encoding="utf-8")).ids
            if u.fragment not in ids:
                err.append(f"{nom} : ancre introuvable {url}")
    err += [f"{nom} : {e}" for e in verifier_visuels_page(a, chemin, publication_mode=False)]
    err += [f"{nom} : {e}" for e in verifier_images(a)]
    if any(f.get("action") for f in a.formulaires):
        err.append(f"{nom} : formulaire avec une adresse d'envoi dans une maquette")
    visible = _texte_visible(texte)
    if not re.search(r'<aside class="lp-apercu[^"]*"[^>]*>\s*<p><strong>Maquette FICTIVE', texte):
        err.append(f"{nom} : bandeau « Maquette FICTIVE » absent")
    err += [f"{nom} : prix sans mention FICTIF « {p} »" for p in _sans_fictif_proche(visible, PRIX_RE, ("FICTIF",), 40)]
    err += [f"{nom} : date sans mention FICTIF ni « date estimée » « {d} »"
            for d in _sans_fictif_proche(visible, DATE_RE, ("FICTIF", "date estimée"), 60)]
    err += [f"{nom} : {e}" for e in verifier_textes_garantie(visible)]
    m = STATUT_RESA_INTERDIT_RE.search(visible)
    if m:
        err.append(f"{nom} : statut de réservation non admis « {m.group(0)} » (ouvertes ou fermées seulement)")
    for motif, libelle in ((TERMES_INTERNES, "terme interne"), (URGENCE_RE, "fausse urgence"), (PROMESSES_RE, "promesse interdite"),
                           *AFFIRMATIONS_INEXACTES):
        m = motif.search(visible)
        if m:
            err.append(f"{nom} : {libelle} « {m.group(0)} »")
    reference = mention_reference()
    mentions = re.findall(r'id="mention-independance">(.*?)</p>', texte, re.DOTALL)
    if not mentions or not _normaliser(re.sub(r"<[^>]+>", "", mentions[0])).endswith(reference):
        err.append(f"{nom} : mention d'indépendance absente ou différente de USAGE_MARQUES.md")
    err += [f"{nom} : espace insécable manquante « {f} »" for f in fautes(texte)]
    return err


def verifier_maquettes(dossier: Path = MAQUETTES) -> list[str]:
    """Toutes les maquettes ; aucune ne doit se trouver dans la landing (elle serait publiée)."""
    err: list[str] = []
    for chemin in sorted(dossier.glob("*.html")) if dossier.is_dir() else []:
        err += verifier_maquette(chemin)
    for page in sorted(LANDING.glob("*.html")):
        if "Maquette FICTIVE" in page.read_text(encoding="utf-8"):
            err.append(f"landing/{page.name} : maquette dans le dossier publié (la déplacer dans site/maquettes/)")
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
                               (URGENCE_RE, "fausse urgence"), (PROMESSES_RE, "promesse interdite"), *AFFIRMATIONS_INEXACTES):
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


# ------------------------------------------------------------------------- planification et workflow
def _jours(texte: str) -> set[int]:
    return {int(n) for n in re.findall(r"\bJ(\d+)\b", texte)}


def verifier_champs_landing_planifies(
    interventions: Path = INTERVENTIONS, backlog: Path = BACKLOG, champs: dict[str, tuple[str, str]] | None = None
) -> list[str]:
    """Chaque champ exigé pour publier la landing vient d'un acte planifié au plus tard à J10 (revue CON-06).

    L'acte de ``CHAMPS_LANDING`` cite une intervention (« B27 », « C26 »…) ou une tâche (« BL-187 ») : sa date
    est lue dans la checklist chronologique d'``INTERVENTIONS_HUMAINES.md`` ou l'échéance de ``BACKLOG.csv``.
    Un acte sans identifiant, inconnu ou planifié après J10 rend la publication de J10 irréalisable.
    """
    champs = publication.CHAMPS_LANDING if champs is None else champs
    texte = interventions.read_text(encoding="utf-8")
    chrono = texte.split("## 1.", 1)[-1].split("## 2.", 1)[0]
    jours: dict[str, set[int]] = {}
    for ligne in chrono.splitlines():
        if not ligne.startswith("| ☐ |"):
            continue
        cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
        for ident in re.findall(r"\b([ABC]\d{2})\b", cellules[2]):
            jours.setdefault(ident, set()).update(_jours(cellules[1]))
    with backlog.open(encoding="utf-8", newline="") as fh:
        echeances = {r["ID"]: _jours(r["Échéance"]) for r in csv.DictReader(fh)}
    err: list[str] = []
    for nom, (_nature, acte) in sorted(champs.items()):
        refs = [(r, jours.get(r), "INTERVENTIONS_HUMAINES.md") for r in re.findall(r"\b([ABC]\d{2})\b", acte)]
        refs += [(r, echeances.get(r), "BACKLOG.csv") for r in re.findall(r"\bBL-\d{3}\b", acte)]
        if not refs:
            err.append(f"{nom} : acte sans intervention ni tâche identifiée (« {acte} »)")
        for ref, dates, source in refs:
            if not dates:
                err.append(f"{nom} : {ref} sans date dans {source}")
            elif min(dates) > JOUR_PUBLICATION_LANDING:
                err.append(f"{nom} : {ref} planifié à J{min(dates)}, après la publication de la landing (J10)")
    return err


def verifier_workflow_inscription(dossier: Path = WORKFLOWS_N8N) -> list[str]:
    """Export du workflow d'inscription aux alertes : aucune exécution conservée (revue NEW-05).

    La notice promet que l'adresse IP du formulaire n'est pas enregistrée et qu'elle est effacée après le
    contrôle ; une exécution n8n conservée garderait les en-têtes (``x-forwarded-for``) et le corps. Contrat :
    ``site/landing/README.md`` §4. Tant que l'export n'est pas livré (BL-187), il n'y a rien à contrôler ici :
    la publication exige de toute façon ``WEBHOOK_INSCRIPTION`` validé après la recette du workflow.
    """
    err: list[str] = []
    for chemin in sorted(dossier.glob("*.json")) if dossier.is_dir() else []:
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        nom = str(donnees.get("name", "")) if isinstance(donnees, dict) else ""
        if "inscription" not in (chemin.name + " " + nom).lower():
            continue
        reglages = donnees.get("settings") or {}
        for cle in ("saveDataSuccessExecution", "saveDataErrorExecution"):
            if reglages.get(cle) != "none":
                err.append(f"{chemin.name} : {cle} = {reglages.get(cle)!r} (attendu « none » : aucune exécution conservée)")
        if reglages.get("saveManualExecutions") not in (False, None):
            err.append(f"{chemin.name} : saveManualExecutions doit être false")
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
        "visuels (site/config/visuels.json)": visuels.verifier(),
        "maquettes (site/maquettes)": verifier_maquettes(),
        "snippets Liquid": verifier_liquid(SNIPPETS),
        "nom de travail (Shopify)": verifier_nom_de_travail(SITE / "shopify"),
        "documents": verifier_docs(SITE),
        "landing publiable à J10": verifier_champs_landing_planifies(),
        "workflow d'inscription (contrat §4)": verifier_workflow_inscription(),
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
