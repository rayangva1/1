#!/usr/bin/env python3
"""Prépare la landing : pages secondaires, aperçu, ou dossier de publication.

Modes (SPEC §0.6 : simulation par défaut) :

* ``source``      régénère dans ``site/landing/`` les pages secondaires (merci, confirmation,
                  désinscription, confidentialité) ; les champs ``{{…}}`` restent visibles.
* ``apercu``      construit un dossier d'aperçu (défaut ``site/dist/apercu/``) : valeurs connues
                  remplies, ``⟦À REMPLIR⟧`` / ``⟦à valider⟧`` sinon ; bandeau d'aperçu et ``noindex`` gardés.
* ``publication`` construit le dossier à déposer (défaut ``site/dist/landing/``). **Refuse**
                  (code 1) tant qu'un champ utilisé n'est pas ``valide``, que le nom n'est pas validé,
                  que l'URL du webhook ou de la landing est invalide, ou que les visuels de la marque ne sont
                  pas tous servis en local, présents, en WebP et dans leur budget de poids (import local :
                  ``site/outils/rapatrier_visuels.py --importer <dossier>`` ; la page publiée ne charge aucune
                  image d'un tiers, un visuel distant est toujours refusé).
* ``etat``        liste les champs requis, leur statut, leur nature (définitif ou provisoire) et le décideur.

Les champs viennent du registre légal (``docs/04-legal/champs_a_remplir.yaml``, source unique de
l'identité) et de ``site/config/publication_landing.yaml`` (URL, mois d'ouverture, webhook).

La page de confidentialité est générée depuis ``docs/04-legal/CONFIDENTIALITE_LANDING.md`` : une notice limitée
aux traitements réels de la landing, publiable à J10 (BL-032), et non depuis la déclaration complète de la
boutique (qui exige le prestataire de paiement, le transporteur, la boutique et la relecture complète, J21-J28).
Les champs exigés forment une **liste fermée** (``CHAMPS_LANDING``) : une page qui utiliserait un autre champ fait
échouer la publication tant que la liste n'a pas été revue (fail-closed).
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

OUTILS = Path(__file__).resolve().parent
REPO = OUTILS.parents[1]
sys.path.insert(0, str(OUTILS))
sys.path.insert(0, str(REPO / "docs" / "04-legal" / "outils"))

import registre_champs as rc  # noqa: E402
import visuels  # noqa: E402
from markdown_mini import convertir  # noqa: E402
from renard_svg import RENARD_ASSIS  # noqa: E402
from typo import typographier  # noqa: E402

LANDING = REPO / "site" / "landing"
CONFIG_SITE = REPO / "site" / "config" / "publication_landing.yaml"
CONFIDENTIALITE_MD = REPO / "docs" / "04-legal" / "CONFIDENTIALITE_LANDING.md"
DIST = REPO / "site" / "dist"
NOM_DE_TRAVAIL = "Quai des Cartes"
APERCU_RE = re.compile(r"[ \t]*<!-- APERCU:DEBUT -->.*?<!-- APERCU:FIN -->[ \t]*\n?", re.DOTALL)
WEBHOOK_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?/[^\s<>\"']*$")
GOOGLE_FONTS_LIGNES_RE = re.compile(r"[ \t]*<link[^>]+(fonts\.googleapis\.com|fonts\.gstatic\.com)[^>]*>[ \t]*\n?")
MARQUEUR_RE = re.compile(r"⟦[^⟧]*⟧")
EXCLUS_COPIE = {"README.md", "inscription.schema.json", "manifeste.json"}
FONTS_CSP = ("https://fonts.googleapis.com", "https://fonts.gstatic.com")
#: Message sans JavaScript de la page publiée (revue NEW-04) : en publication, le formulaire porte l'URL du
#: webhook dans ``action`` et fonctionne sans script (redirection 303 vers merci.html, README §4). Le message
#: d'aperçu (« n'envoie rien ») est entre marqueurs APERCU et n'est jamais publié.
NOSCRIPT_MARQUEUR_RE = re.compile(r"[ \t]*<!-- PUBLICATION:NOSCRIPT -->[ \t]*\n?")
NOSCRIPT_PUBLICATION = (
    '<noscript><p class="lp-statut lp-statut--info">Sans JavaScript, le formulaire fonctionne aussi\u00a0: après '
    "l'envoi, une page de confirmation s'affiche.</p></noscript>"
)

DEFINITIF = "définitif"
PROVISOIRE = "provisoire autorisé"
#: Champs exigés pour publier la landing à J10 (BL-032) : (nature, acte qui fournit la valeur).
#: « provisoire autorisé » = valeur validée mais appelée à changer (republier après changement) ; jamais un
#: statut « a_valider » : chaque champ doit être « valide » pour publier. Aucun champ ne dépend de la boutique
#: Shopify (B15), du paiement (B16), du transporteur (B17), de l'hébergement complet (B23, J26) ni de la
#: relecture complète des textes (C11) : chaque acte cité tombe au plus tard à J9 (INTERVENTIONS_HUMAINES.md,
#: BACKLOG.csv : BL-186 hébergement de n8n à J8, BL-187 workflow d'inscription à J9, BL-185 / C26 à J9).
CHAMPS_LANDING: dict[str, tuple[str, str]] = {
    "NOM_BOUTIQUE": (DEFINITIF, "C06 (J7)"),
    "RAISON_SOCIALE": (DEFINITIF, "B07 (J7)"),
    "ADRESSE_POSTALE": (DEFINITIF, "B07 (J7)"),
    "NOM_RESPONSABLE": (DEFINITIF, "B07 (J7)"),
    "EMAIL_SUPPORT": (DEFINITIF, "B02 (J1)"),
    "EMAIL_DONNEES": (DEFINITIF, "B02 (J1)"),
    "WEBHOOK_INSCRIPTION": (DEFINITIF, "B27 (J8) : n8n en HTTPS, puis BL-187 (J9) : workflow d'inscription recetté"),
    "DUREE_CONSERVATION_ALERTES": (DEFINITIF, "C26 (J9) : validée par la propriétaire après relecture express"),
    "DUREE_CONSERVATION_SAV": (DEFINITIF, "C26 (J9) : validée par la propriétaire après relecture express"),
    "ST_HEBERGEMENT_LANDING": (DEFINITIF, "B08 (J8) : compte d'hébergement"),
    "ST_HEBERGEMENT_LANDING_PAYS": (DEFINITIF, "B08 (J8) : contrat de l'hébergeur"),
    "ST_POLICES": (DEFINITIF, "C26 (J9) : Google Fonts ou polices du système"),
    "ST_POLICES_PAYS": (DEFINITIF, "C26 (J9) : choix des polices"),
    "ST_BASE": (DEFINITIF, "B27 (J8) : hébergeur de n8n"),
    "ST_BASE_PAYS": (DEFINITIF, "B27 (J8) : contrat de l'hébergeur de n8n"),
    "ST_EMAILING": (DEFINITIF, "B04 (J3)"),
    "ST_EMAILING_PAYS": (DEFINITIF, "B04 (J3) : contrat de l'outil d'envoi"),
    "ST_MESSAGERIE": (DEFINITIF, "B02 (J1)"),
    "ST_MESSAGERIE_PAYS": (DEFINITIF, "B02 (J1) : contrat de la messagerie"),
    "ST_IA": (DEFINITIF, "C26 (J9) : fournisseur d'IA accepté par la propriétaire"),
    "ST_IA_PAYS": (DEFINITIF, "C26 (J9) : contrat du fournisseur d'IA (agent 12, juriste)"),
    "URL_LANDING": (PROVISOIRE, "B08 (J8) : adresse de l'hébergeur, puis domaine"),
    "MOIS_OUVERTURE": (PROVISOIRE, "C07 (J10) : mois visé, jamais une date ferme"),
    "DATE_VERSION_LANDING": (PROVISOIRE, "C26 (J9) : relecture express du juriste, remplacée à l'ouverture"),
}


class PublicationError(RuntimeError):
    """Préparation refusée ; ``erreurs`` liste les causes."""

    def __init__(self, erreurs: list[str]) -> None:
        self.erreurs = erreurs
        super().__init__("; ".join(erreurs))


@dataclass
class Rapport:
    """Résultat d'une préparation."""

    mode: str
    sortie: Path
    fichiers: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- champs
def charger_champs(chemin_site: Path = CONFIG_SITE, chemin_registre: Path = rc.REGISTRY_PATH) -> dict[str, rc.Field]:
    """Registre légal + champs de la landing ; un nom ne peut être défini qu'une fois."""
    legal = rc.load_registry(chemin_registre)
    site = rc.parse_registry(yaml.safe_load(chemin_site.read_text(encoding="utf-8")))
    doublons = sorted(set(legal) & set(site))
    if doublons:
        raise PublicationError([f"champ défini deux fois (registre légal et landing) : {n}" for n in doublons])
    return {**legal, **site}


def valeur(champs: dict[str, rc.Field], nom: str, publication: bool) -> str | None:
    """Valeur utilisable d'un champ : validée en publication ; validée ou proposée en aperçu."""
    f = champs.get(nom)
    if f is None or f.value is None:
        return None
    if publication and f.status is not rc.Status.VALIDE:
        return None
    return f.value


def webhook_valide(url: str | None) -> bool:
    """Même règle que ``LandingCore.webhookValide`` (js/landing.js)."""
    return bool(url) and "{{" not in str(url) and WEBHOOK_RE.match(str(url)) is not None


# --------------------------------------------------------------------- pages secondaires
def _tete(titre: str, description: str, indexable: bool) -> str:
    robots = (
        '  <!-- APERCU:DEBUT -->\n  <meta name="robots" content="noindex, nofollow">\n  <!-- APERCU:FIN -->\n'
        if indexable
        else '  <meta name="robots" content="noindex, nofollow">\n'
    )
    return f"""<!DOCTYPE html>
<html lang="fr-CH" data-da="a">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- FICHIER GÉNÉRÉ par site/outils/publication.py (mode source) : modifier le générateur, pas ce fichier.
       Nom de travail NON VALIDÉ : « {NOM_DE_TRAVAIL} ». -->
{robots}  <title>{titre} — {NOM_DE_TRAVAIL}</title>
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta name="color-scheme" content="light dark">
  <link rel="icon" href="assets/da/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="assets/da/favicon-32.png" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="assets/da/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&amp;family=Inter:opsz,wght@14..32,400..700&amp;family=IBM+Plex+Mono:wght@500;600&amp;display=swap">
  <link rel="stylesheet" href="assets/da/tokens.css">
  <link rel="stylesheet" href="assets/da/components.css">
  <link rel="stylesheet" href="css/landing.css">
  <script src="js/theme.js"></script>
  <script src="js/atelier.js" defer></script>
</head>
"""
# Direction, ambiance (feuille assets/da/ambiance.css, data-ambiance) et URL Google Fonts sont posées ensuite par
# da_sync.aligner_html selon le manifeste de la DA (même transformation pour l'écriture et la vérification).


MENTION_INDEPENDANCE = (
    f"{NOM_DE_TRAVAIL} est une boutique indépendante. Elle n'est ni affiliée, ni sponsorisée, ni approuvée par "
    "The Pokémon Company, Nintendo, Creatures Inc. ou GAME FREAK inc. Pokémon et les noms associés sont des "
    "marques de leurs titulaires respectifs ; nous les utilisons uniquement pour désigner les produits "
    "authentiques que nous revendons."
)


#: Illustration de chaque page secondaire (DIRECTION_ATELIER.md §9) : Braise (nom provisoire) couché ou assis, à côté
#: du texte, avec sa silhouette SVG en décor de secours si l'illustration ne charge pas (renard_svg.py). Balises
#: data-visuel synchronisées par site/outils/visuels.py (adresses et texte alternatif du manifeste).
ILLUSTRATIONS: dict[str, str] = {
    "merci.html": "renard-couche",
    "inscription-confirmee.html": "renard-assis",
    "desinscription.html": "renard-couche",
    "confidentialite.html": "renard-assis",
}


def _figure(nom: str) -> str:
    """Figure illustrée d'une page secondaire (image principale, sauf la vignette de la notice)."""
    ident = ILLUSTRATIONS[nom]
    if nom == "confidentialite.html":
        return (
            '      <figure class="lp-media lp-page__vignette">\n'
            f'        <span class="lp-secours" aria-hidden="true">{RENARD_ASSIS}</span>\n'
            f'        <img alt="" sizes="15rem" loading="lazy" decoding="async" data-visuel="{ident}" src="">\n'
            "      </figure>\n"
        )
    return (
        '      <figure class="lp-media lp-page__figure">\n'
        f'        <span class="lp-secours" aria-hidden="true">{RENARD_ASSIS}</span>\n'
        f'        <img alt="" sizes="(min-width: 900px) 34vw, 92vw" fetchpriority="high" decoding="async" data-visuel="{ident}" src="">\n'
        "      </figure>\n"
    )


def _corps(nom: str, contenu: str) -> str:
    legal = nom == "confidentialite.html"
    return f"""<body class="da-root lp-atelier lp-page-simple">
  <a class="lp-evitement" href="#contenu">Aller au contenu</a>
  <header class="lp-entete" id="entete">
    <div class="lp-cadre lp-entete__inner">
      <a class="lp-logo" href="./"><img class="lp-logo__img" src="assets/da/logo-horizontal.svg" alt="{NOM_DE_TRAVAIL}" width="1083" height="140"></a>
      <a class="da-btn lp-btn lp-btn--plein lp-entete__cta" href="./">Accueil</a>
    </div>
  </header>
  <main id="contenu" class="lp-page{' lp-page__legal' if legal else ''}">
    <div class="lp-cadre lp-grille lp-page__grille">
{_figure(nom)}      <div class="lp-page__texte">
{contenu}
      </div>
    </div>
  </main>
  <footer class="lp-pied lp-pied--simple">
    <div class="lp-pied__charbon">
      <div class="lp-cadre lp-pied__legal">
        <p class="lp-pied__mention" id="mention-independance">{MENTION_INDEPENDANCE}</p>
        <p>Exploitant : {{{{RAISON_SOCIALE}}}}, {{{{ADRESSE_POSTALE}}}}, Suisse. Contact : <a href="mailto:{{{{EMAIL_SUPPORT}}}}">{{{{EMAIL_SUPPORT}}}}</a></p>
        <p><a href="./">Accueil</a> · <a href="confidentialite.html">Déclaration de confidentialité</a></p>
        <p class="lp-pied__credits">Braise, notre renard mascotte (nom provisoire) : création originale de la boutique, sans lien avec Pokémon.</p>
      </div>
    </div>
  </footer>
</body>
</html>
"""


PAGES_SIMPLES: dict[str, tuple[str, str, str]] = {
    "merci.html": (
        "Inscription reçue",
        "Votre inscription aux alertes est reçue : confirmez-la depuis l'email que nous venons de vous envoyer.",
        """      <h1 class="da-title">Merci, vérifiez votre boîte mail.</h1>
      <p>Nous venons de vous envoyer un email de confirmation. Cliquez sur son lien pour activer vos alertes : sans confirmation, nous ne vous écrirons pas.</p>
      <p>Rien reçu d'ici quelques minutes ? Regardez dans les courriers indésirables, puis réessayez depuis la <a href="./#alertes">page d'accueil</a>.</p>
      <p class="lp-signature">Braise (nom provisoire) attend votre clic, l'œil en coin.</p>
      <p class="lp-note">Cette inscription ne réserve aucun produit et n'engage aucun paiement.</p>""",
    ),
    "inscription-confirmee.html": (
        "Inscription confirmée",
        "Votre inscription aux alertes est confirmée.",
        """      <h1 class="da-title">C'est confirmé.</h1>
      <p>Vous recevrez l'alerte d'ouverture, puis les alertes de stock correspondant à vos choix et, au plus, un email récapitulatif par semaine.</p>
      <p>Chaque email contient un lien pour modifier vos préférences ou vous désinscrire en un clic.</p>
      <p class="lp-signature">Braise (nom provisoire) dresse l'oreille jusqu'à l'ouverture.</p>
      <p><a class="da-btn lp-btn lp-btn--plein" href="./">Retour à l'accueil</a></p>""",
    ),
    "desinscription.html": (
        # Page affichée par le workflow n8n 06 APRÈS les appels de retrait (outil d'emailing, Shopify) et
        # seulement pour un lien valide : elle confirme la réception, pas un traitement qu'elle ne peut pas voir.
        "Demande de désinscription reçue",
        "Votre demande de désinscription est reçue.",
        """      <h1 class="da-title">Demande de désinscription reçue.</h1>
      <p>Nous avons bien reçu votre demande. Elle a été transmise à chacun de nos outils d'envoi : vous ne devez plus recevoir d'alerte ni d'email récapitulatif.</p>
      <p>Si un outil n'a pas confirmé le retrait, nous le faisons à la main sans délai. Vous recevez encore une alerte ? Écrivez-nous à <a href="mailto:{{EMAIL_SUPPORT}}">{{EMAIL_SUPPORT}}</a> : nous vous retirons et vous confirmons la désinscription par écrit.</p>
      <p>Nous conservons uniquement votre adresse dans une liste d'exclusion, pour être sûrs de ne plus vous écrire. Les emails liés à une commande (confirmation, expédition) restent envoyés si vous commandez.</p>
      <p>Une erreur ? Vous pouvez vous réinscrire depuis la <a href="./#alertes">page d'accueil</a>.</p>""",
    ),
}


def contenu_confidentialite(texte_md: str) -> str:
    """Bloc public de CONFIDENTIALITE_LANDING.md converti en HTML (titres ## → h1, ### → h2)."""
    blocs = rc.public_blocks(texte_md)
    if not blocs:
        raise PublicationError(["CONFIDENTIALITE_LANDING.md : aucun bloc public"])
    corps = convertir("\n\n".join(blocs), decalage_titres=1)
    corps = corps.replace("<h1>", '<h1 class="da-title">', 1)
    avis = (
        "      <!-- APERCU:DEBUT -->\n"
        '      <p class="lp-note lp-a-remplir">Brouillon repris de docs/04-legal/CONFIDENTIALITE_LANDING.md : '
        "relecture express du juriste requise avant publication.</p>\n"
        "      <!-- APERCU:FIN -->\n"
    )
    retrait = "\n".join("      " + ligne for ligne in corps.splitlines())
    return avis + f'      <div class="lp-texte-legal">\n{retrait}\n      </div>'


def pages_secondaires(texte_confidentialite: str | None = None) -> dict[str, str]:
    """Contenu source (champs ``{{…}}`` non remplis) de chaque page secondaire."""
    pages = {
        nom: typographier(_tete(titre, desc, indexable=False) + _corps(nom, contenu))
        for nom, (titre, desc, contenu) in PAGES_SIMPLES.items()
    }
    md = texte_confidentialite if texte_confidentialite is not None else CONFIDENTIALITE_MD.read_text(encoding="utf-8")
    pages["confidentialite.html"] = typographier(
        _tete(
            "Déclaration de confidentialité",
            "Inscription aux alertes : quelles données nous traitons, pourquoi, combien de temps, et vos droits (LPD).",
            indexable=True,
        )
        + _corps("confidentialite.html", contenu_confidentialite(md))
    )
    m = visuels.charger()
    return {nom: visuels.appliquer_texte(texte, m, LANDING / nom) for nom, texte in pages.items()}


def ecrire_pages_source(racine: Path = LANDING) -> list[str]:
    """Écrit les pages secondaires dans le dossier source de la landing (direction et ambiance DA conservées)."""
    from da_sync import aligner_html, lire_manifeste  # import tardif : évite une dépendance circulaire

    direction, ambiance = lire_manifeste(racine / "assets" / "da")
    ecrits = []
    for nom, contenu in pages_secondaires().items():
        (racine / nom).write_text(aligner_html(contenu, direction, ambiance), encoding="utf-8")
        ecrits.append(nom)
    return ecrits


# --------------------------------------------------------------------------- contrôles
def controles_polices(champs: dict[str, rc.Field], sans_google_fonts: bool) -> list[str]:
    """La notice déclare exactement le choix de polices fait à la publication (Google Fonts ou polices du système)."""
    polices = valeur(champs, "ST_POLICES", True)
    if not polices:
        return []  # absence déjà signalée par le contrôle des champs
    declare_google = "google" in polices.lower()
    if declare_google and sans_google_fonts:
        return ["ST_POLICES déclare Google Fonts alors que la page est publiée sans (--sans-google-fonts)"]
    if not declare_google and not sans_google_fonts:
        return ["ST_POLICES ne déclare pas Google Fonts alors que la page les charge (publier avec --sans-google-fonts ou corriger la notice)"]
    return []


def champs_utilises(source: Path = LANDING, texte_confidentialite: str | None = None) -> set[str]:
    """Champs utilisés par les pages de la landing (source), la notice et la configuration."""
    noms: set[str] = {"NOM_BOUTIQUE", "WEBHOOK_INSCRIPTION", "URL_LANDING", "EMAIL_SUPPORT"}
    for page in source.glob("*.html"):
        noms.update(rc.placeholders(page.read_text(encoding="utf-8")))
    md = texte_confidentialite if texte_confidentialite is not None else CONFIDENTIALITE_MD.read_text(encoding="utf-8")
    noms.update(rc.placeholders("\n".join(rc.public_blocks(md))))
    return noms


def controles_publication(
    champs: dict[str, rc.Field],
    sans_google_fonts: bool = False,
    source: Path = LANDING,
    visuels_manifeste: dict | None = None,
) -> list[str]:
    """Préconditions de publication indépendantes du rendu des pages."""
    erreurs: list[str] = [
        f"champ hors de la liste de publication de la landing (CHAMPS_LANDING) : {n} — revoir la liste avant de publier"
        for n in sorted(champs_utilises(source) - set(CHAMPS_LANDING))
    ]
    erreurs += [
        f"{n} non validé (statut requis : valide ; nature : {CHAMPS_LANDING[n][0]})"
        for n in sorted(CHAMPS_LANDING)
        if (champs.get(n) is None or champs[n].status is not rc.Status.VALIDE) and not (champs.get(n) and champs[n].alias_of)
    ]
    erreurs += controles_polices(champs, sans_google_fonts)
    nom = champs.get("NOM_BOUTIQUE")
    if nom is None or nom.status is not rc.Status.VALIDE:
        erreurs.append("NOM_BOUTIQUE non validé (décision C06) : le nom de travail ne se publie pas")
    elif nom.value and nom.value != NOM_DE_TRAVAIL:
        titre_logo = (LANDING / "assets" / "da" / "logo-horizontal.svg").read_text(encoding="utf-8")
        if f"<title id=\"titre\">{nom.value}" not in titre_logo:
            erreurs.append(f"le logo DA porte encore le nom de travail : logo à refaire pour « {nom.value} » (C10)")
    webhook = valeur(champs, "WEBHOOK_INSCRIPTION", True)
    if not webhook_valide(webhook):
        erreurs.append("WEBHOOK_INSCRIPTION absent, non validé ou invalide (https://hôte/chemin attendu)")
    url = valeur(champs, "URL_LANDING", True)
    if not url or not url.startswith("https://") or not url.endswith("/") or "{{" in url:
        erreurs.append("URL_LANDING absente, non validée ou invalide (https://…/ attendu)")
    erreurs += visuels.erreurs_publication(visuels_manifeste, racine=source)
    return erreurs


def _remplir(texte: str, champs: dict[str, rc.Field], publication: bool) -> str:
    mode = rc.Mode.PUBLICATION if publication else rc.Mode.APERCU
    return rc.render(texte, champs, mode)


def _transformer_html(texte: str, champs: dict[str, rc.Field], publication: bool, sans_google_fonts: bool) -> str:
    nom = valeur(champs, "NOM_BOUTIQUE", publication)
    texte = _remplir(texte, champs, publication)
    if nom and nom != NOM_DE_TRAVAIL:
        texte = texte.replace(NOM_DE_TRAVAIL, nom)
    if publication:
        texte = APERCU_RE.sub("", texte)
        texte = NOSCRIPT_MARQUEUR_RE.sub(lambda m: m.group(0).replace("<!-- PUBLICATION:NOSCRIPT -->", NOSCRIPT_PUBLICATION),
                                         texte)
        webhook = valeur(champs, "WEBHOOK_INSCRIPTION", True) or ""
        texte = texte.replace(
            '<form class="lp-formulaire" id="lp-formulaire" method="post" action=""',
            f'<form class="lp-formulaire" id="lp-formulaire" method="post" action="{html.escape(webhook, quote=True)}"',
        )
        texte = texte.replace('type="submit" id="lp-envoyer" disabled>', 'type="submit" id="lp-envoyer">')
    else:
        texte = NOSCRIPT_MARQUEUR_RE.sub("", texte)
    if sans_google_fonts:
        texte = GOOGLE_FONTS_LIGNES_RE.sub("", texte)
    return typographier(texte)


def config_js(mode: str, webhook: str, email_support: str) -> str:
    """Contenu de js/config.js pour un dossier construit."""

    def js(v: str) -> str:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return (
        "/* FICHIER GÉNÉRÉ par site/outils/publication.py — ne pas modifier à la main dans ce dossier. */\n"
        "window.LANDING_CONFIG = {\n"
        f"  mode: {js(mode)},\n"
        f"  webhookUrl: {js(webhook)},\n"
        f"  emailSupport: {js(email_support)},\n"
        '  consentVersion: "alertes-v1-2026-10-04",\n'
        "  timeoutMs: 15000\n"
        "};\n"
    )


def entetes_netlify(webhook: str, sans_google_fonts: bool) -> str:
    """Fichier _headers (Netlify) : politique de sécurité stricte, seul le webhook est joignable."""
    origine = "{u.scheme}://{u.netloc}".format(u=urlparse(webhook))
    style = "'self'" if sans_google_fonts else f"'self' {FONTS_CSP[0]}"
    police = "'self'" if sans_google_fonts else f"'self' {FONTS_CSP[1]}"
    csp = (
        f"default-src 'self'; script-src 'self'; style-src {style}; font-src {police}; img-src 'self' data:; "
        f"connect-src {origine}; form-action {origine}; base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
    )
    return (
        "/*\n"
        f"  Content-Security-Policy: {csp}\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
    )


def _robots_et_sitemap(url: str) -> dict[str, str]:
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{html.escape(url)}</loc></url>\n"
        f"  <url><loc>{html.escape(url)}confidentialite.html</loc></url>\n"
        "</urlset>\n"
    )
    robots = (
        "User-agent: *\nAllow: /\nDisallow: /merci.html\nDisallow: /inscription-confirmee.html\n"
        f"Disallow: /desinscription.html\nSitemap: {url}sitemap.xml\n"
    )
    return {"sitemap.xml": sitemap, "robots.txt": robots}


# --------------------------------------------------------------------------- construction
def construire(
    mode: str,
    sortie: Path,
    *,
    champs: dict[str, rc.Field] | None = None,
    sans_google_fonts: bool = False,
    source: Path = LANDING,
    visuels_manifeste: dict | None = None,
) -> Rapport:
    """Construit un dossier ``apercu`` ou ``publication`` ; lève ``PublicationError`` si refusé.

    ``visuels_manifeste`` : manifeste des visuels à contrôler (défaut : ``site/config/visuels.json``).
    """
    if mode not in ("apercu", "publication"):
        raise ValueError(f"mode inconnu : {mode}")
    publication = mode == "publication"
    champs = champs if champs is not None else charger_champs()
    erreurs = controles_publication(champs, sans_google_fonts, source, visuels_manifeste) if publication else []
    pages: dict[str, str] = {}
    for page in sorted(source.glob("*.html")):
        try:
            pages[page.name] = _transformer_html(page.read_text(encoding="utf-8"), champs, publication, sans_google_fonts)
        except rc.RenderError as exc:
            erreurs.extend(f"{page.name} : {e}" for e in exc.errors)
    if erreurs:
        raise PublicationError(sorted(set(erreurs)))

    rapport = Rapport(mode=mode, sortie=sortie)
    if sortie.exists():
        shutil.rmtree(sortie)
    for chemin in sorted(source.rglob("*")):
        if chemin.is_dir() or chemin.name in EXCLUS_COPIE or chemin.suffix == ".html":
            continue
        cible = sortie / chemin.relative_to(source)
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(chemin, cible)
        rapport.fichiers.append(chemin.relative_to(source).as_posix())
    for nom, contenu in pages.items():
        (sortie / nom).write_text(contenu, encoding="utf-8")
        rapport.fichiers.append(nom)

    webhook = valeur(champs, "WEBHOOK_INSCRIPTION", publication) or ""
    if not webhook_valide(webhook):
        webhook = ""
        rapport.avertissements.append("webhook non configuré : formulaire désactivé dans ce dossier")
    email = valeur(champs, "EMAIL_SUPPORT", publication) or ""
    (sortie / "js" / "config.js").write_text(config_js(mode, webhook, email), encoding="utf-8")
    if publication:
        (sortie / "_headers").write_text(entetes_netlify(webhook, sans_google_fonts), encoding="utf-8")
        rapport.fichiers.append("_headers")
        for nom, contenu in _robots_et_sitemap(valeur(champs, "URL_LANDING", True) or "").items():
            (sortie / nom).write_text(contenu, encoding="utf-8")
            rapport.fichiers.append(nom)
        residus = [
            f"{p.relative_to(sortie).as_posix()} : {m}"
            for p in sorted(sortie.rglob("*"))
            if p.suffix in (".html", ".txt", ".xml") or p.name == "config.js"
            for m in (["champ {{…}} non rempli"] if "{{" in p.read_text(encoding="utf-8") else [])
            + (["marque ⟦…⟧"] if MARQUEUR_RE.search(p.read_text(encoding="utf-8")) else [])
            + (["bloc d'aperçu"] if "APERCU:" in p.read_text(encoding="utf-8") else [])
        ]
        if residus:
            shutil.rmtree(sortie)
            raise PublicationError(residus)
    rapport.fichiers.sort()
    return rapport


def etat(champs: dict[str, rc.Field] | None = None, source: Path = LANDING) -> list[tuple[str, str, str]]:
    """(champ, statut, décideur) de chaque champ exigé (liste fermée) ou utilisé par les pages et la notice."""
    champs = champs if champs is not None else charger_champs()
    lignes = []
    for nom in sorted(champs_utilises(source) | set(CHAMPS_LANDING)):
        f = champs.get(nom)
        lignes.append((nom, f.status.value if f else "INCONNU", f.decideur if f else "—"))
    return lignes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("source", "apercu", "publication", "etat"))
    parser.add_argument("--sortie", type=Path, default=None, help="dossier de sortie (apercu, publication)")
    parser.add_argument("--sans-google-fonts", action="store_true", help="retire Google Fonts (polices système de secours)")
    args = parser.parse_args(argv)
    if args.mode == "source":
        for nom in ecrire_pages_source():
            print(f"écrit : site/landing/{nom}")
        return 0
    if args.mode == "etat":
        lignes = etat()
        manquants = [lg for lg in lignes if lg[1] != "valide"]
        for nom, statut, decideur in lignes:
            nature = CHAMPS_LANDING.get(nom, ("HORS LISTE", ""))[0]
            print(f"{statut:10} {nom:30} {nature:20} {decideur}")
        print(f"\n{len(lignes) - len(manquants)}/{len(lignes)} champ(s) validé(s).")
        return 0
    sortie = args.sortie or (DIST / ("landing" if args.mode == "publication" else "apercu"))
    try:
        rapport = construire(args.mode, sortie, sans_google_fonts=args.sans_google_fonts)
    except PublicationError as exc:
        print(f"REFUS ({args.mode}) : {len(exc.erreurs)} problème(s)")
        for e in exc.erreurs:
            print(f"  - {e}")
        return 1
    for a in rapport.avertissements:
        print(f"AVERTISSEMENT {a}")
    print(f"{rapport.mode} : {len(rapport.fichiers)} fichiers dans {rapport.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
