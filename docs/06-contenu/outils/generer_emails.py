#!/usr/bin/env python3
"""Génère les emails (HTML + texte) depuis docs/06-contenu/EMAILS/source/emails.yaml.

Sorties (FICHIERS GÉNÉRÉS, ne pas modifier à la main) :
* ``EMAILS/html/<id>.html``   modèle HTML : tableaux, styles en ligne, couleurs de la DA (direction A, clair) ;
* ``EMAILS/texte/<id>.txt``   version texte ;
* ``EMAILS/apercu.html``      tous les emails remplis avec des données FICTIVES, pour relecture ;
* tableau récapitulatif injecté dans ``EMAILS/README.md`` (entre les marqueurs TABLEAU).

Variables : ``[[var]]`` → ``{{ $json.var }}`` (n8n) ou ``{{ var }}`` (Liquid Shopify) ; ``{{CHAMP}}`` = champ
fixe du registre légal, rempli à l'intégration. Usage : ``python docs/06-contenu/outils/generer_emails.py [--verifier]``.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RACINE = Path(__file__).resolve().parents[1]
REPO = RACINE.parents[1]
EMAILS = RACINE / "EMAILS"
SOURCE = EMAILS / "source" / "emails.yaml"
TOKENS = REPO / "docs" / "05-da" / "tokens" / "tokens.json"
README = EMAILS / "README.md"
MARQUE_DEBUT = "<!-- TABLEAU:DEBUT (généré par docs/06-contenu/outils/generer_emails.py) -->"
MARQUE_FIN = "<!-- TABLEAU:FIN -->"
NOM_DE_TRAVAIL = "Quai des Cartes"

POLICE = "Arial, Helvetica, sans-serif"
POLICE_PRIX = "'Courier New', Courier, monospace"
VAR_RE = re.compile(r"\[\[\s*([^\[\]]+?)\s*\]\]")
LIEN_RE = re.compile(r"\[([^\[\]]+)\]\((\[\[[^\]]+\]\]|\{\{[A-Z0-9_]+\}\}|https?://[^)\s]+)\)")
GRAS_RE = re.compile(r"\*\*(.+?)\*\*")
CHAMP_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
CANAUX = ("n8n", "shopify")
CATEGORIES = ("inscription", "marketing", "transactionnel", "avis", "desinscription")
TYPES_BLOCS = ("titre", "sous_titre", "p", "liste", "encadre", "bouton", "produit", "lignes_produits", "faits", "commande_shopify", "suivi_shopify")


class EmailError(ValueError):
    """Source d'email invalide."""


def couleurs() -> dict[str, str]:
    """Couleurs de la direction A (clair) depuis tokens.json : la DA reste la source."""
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    return {k: v["$value"] for k, v in tokens["directions"]["a"]["color"]["light"].items()}


C = couleurs()


# ----------------------------------------------------------------------------- texte en ligne
@dataclass(frozen=True)
class Rendu:
    """Mode de rendu : canal (n8n|shopify) ; ``exemples`` non vide => aperçu avec données FICTIVES."""

    canal: str
    exemples: dict[str, str]
    champs: dict[str, str]

    @property
    def apercu(self) -> bool:
        return bool(self.exemples)


def _salutation(r: Rendu) -> str:
    if r.apercu:
        return r.exemples.get("salutation", "Bonjour Léa,")
    if r.canal == "shopify":
        return "Bonjour{% if customer.first_name %} {{ customer.first_name }}{% endif %},"
    return "{{ $json.salutation }}"


def variable(expr: str, r: Rendu) -> str:
    """Expression d'une variable selon le canal (ou sa valeur d'exemple en aperçu)."""
    nom = expr.split("|")[0].strip()
    if nom == "salutation":
        return _salutation(r)
    if r.apercu:
        return r.exemples.get(nom, f"⟦{nom}⟧")
    if r.canal == "n8n":
        if "|" in expr:
            raise EmailError(f"filtre interdit dans une variable n8n : {expr}")
        return "{{ $json." + nom + " }}"
    return "{{ " + expr.strip() + " }}"


def _champs_fixes(texte: str, r: Rendu) -> str:
    if not r.apercu:
        return texte
    return CHAMP_RE.sub(lambda m: r.champs.get(m.group(1), f"⟦{m.group(1)}⟧"), texte)


def en_html(texte: str, r: Rendu) -> str:
    """Texte source → HTML (échappé, variables, liens, gras)."""
    t = html.escape(str(texte), quote=False)

    def lien(m: re.Match[str]) -> str:
        url = m.group(2)
        url = VAR_RE.sub(lambda v: variable(v.group(1), r), url)
        return f'<a href="{html.escape(_champs_fixes(url, r), quote=True)}" style="color:{C["accent-text"]};">{m.group(1)}</a>'

    t = LIEN_RE.sub(lien, t)
    t = VAR_RE.sub(lambda v: variable(v.group(1), r), t)
    t = GRAS_RE.sub(r"<strong>\1</strong>", t)
    return _champs_fixes(t, r)


EXPRESSION_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\[\[.*?\]\]|⟦.*?⟧", re.DOTALL)


def majuscules_hors_expressions(texte: str) -> str:
    """Met le texte en majuscules sans toucher aux expressions ({{ $json.x }}, {% … %}, {{CHAMP}}, [[var]], ⟦…⟧).

    Les expressions n8n et Liquid sont sensibles à la casse : « {{ $JSON.X }} » n'existe pas.
    """
    morceaux: list[str] = []
    fin = 0
    for m in EXPRESSION_RE.finditer(texte):
        morceaux.append(texte[fin : m.start()].upper())
        morceaux.append(m.group(0))
        fin = m.end()
    morceaux.append(texte[fin:].upper())
    return "".join(morceaux)


def en_texte(texte: str, r: Rendu) -> str:
    """Texte source → texte brut (liens « libellé : url »)."""
    t = LIEN_RE.sub(lambda m: f"{m.group(1)} : {m.group(2)}", str(texte))
    t = VAR_RE.sub(lambda v: variable(v.group(1), r), t)
    t = GRAS_RE.sub(r"\1", t)
    return _champs_fixes(t, r)


# ----------------------------------------------------------------------------- blocs HTML
def _ligne(contenu: str, padding: str = "0 24px 12px 24px") -> str:
    return f'          <tr>\n            <td style="padding:{padding};font-family:{POLICE};">\n{contenu}\n            </td>\n          </tr>'


#: Statut d'une ligne produit -> (libellé du badge, paire de couleurs de la DA, contour plein). « Réservation
#: garantie » (pré-drop) reprend la paire précommande avec un contour plein, comme ``.da-badge--reservation``.
BADGES: dict[str, tuple[str, str, bool]] = {
    "stock_local": ("STOCK LOCAL", "status-local", False),
    "precommande": ("PRÉCOMMANDE", "status-preorder", False),
    "reservation": ("RÉSERVATION GARANTIE", "status-preorder", True),
}
LIBELLES_TEXTE = {"stock_local": "Stock local", "precommande": "Précommande", "reservation": "Réservation garantie"}


def _badge(statut: str) -> str:
    texte, cle, contour = BADGES[statut]
    bord = f"border:2px solid {C[cle + '-fg']};" if contour else ""
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:3px;background:{C[cle + "-bg"]};{bord}'
        f'color:{C[cle + "-fg"]};font-family:{POLICE};font-size:12px;font-weight:bold;">{texte}</span>'
    )


def _p(contenu: str, taille: int = 15, couleur: str | None = None, marge: str = "0 0 12px 0") -> str:
    return f'              <p style="margin:{marge};font-size:{taille}px;line-height:{taille + 7}px;color:{couleur or C["ink"]};word-break:break-word;">{contenu}</p>'


def _bouton(texte: str, url: str, style: str) -> str:
    if style == "secondaire":
        cellule = f"border:2px solid {C['ink']};border-radius:4px;"
        lien = f"color:{C['ink']};"
    else:
        cellule = f"background:{C['ink']};border-radius:4px;"
        lien = f"color:{C['on-ink']};"
    return (
        '              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 16px 0;"><tr>'
        f'<td style="{cellule}"><a href="{url}" style="display:inline-block;padding:13px 22px;font-family:{POLICE};'
        f'font-size:15px;font-weight:bold;{lien}text-decoration:none;">{texte}</a></td></tr></table>'
    )


def _produit_html(titre: str, statut: str, detail: str, prix: str, limite: str, url: str | None = None) -> str:
    titre_html = f'<a href="{url}" style="color:{C["ink"]};text-decoration:none;">{titre}</a>' if url else titre
    lignes = [
        f'<strong style="font-size:15px;line-height:21px;color:{C["ink"]};">{titre_html}</strong>',
        f'<div style="margin-top:6px;">{_badge(statut)} <span style="font-size:13px;color:{C["ink-muted"]};">{detail}</span></div>',
    ]
    if prix:
        lignes.append(f'<div style="margin-top:8px;font-family:{POLICE_PRIX};font-size:17px;font-weight:bold;color:{C["ink"]};">CHF {prix}</div>')
    if limite:
        lignes.append(f'<div style="margin-top:4px;font-size:13px;color:{C["ink-muted"]};">{limite}</div>')
    return (
        f'              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 14px 0;'
        f'border:1px solid {C["line"]};border-top:4px solid {C["ink"]};"><tr><td style="padding:14px;font-family:{POLICE};">'
        + "".join(lignes)
        + "</td></tr></table>"
    )


def _commande_shopify(r: Rendu) -> str:
    """Lignes de commande, totaux, mention TVA et note de commande mixte (Liquid Shopify)."""
    td_g = f'style="padding:14px 0;border-top:1px solid {C["line"]};font-family:{POLICE};font-size:15px;line-height:21px;color:{C["ink"]};word-break:break-word;"'
    td_d = f'align="right" valign="top" style="padding:14px 0 14px 12px;border-top:1px solid {C["line"]};font-family:{POLICE_PRIX};font-size:15px;line-height:21px;color:{C["ink"]};white-space:nowrap;"'
    detail = f'style="font-size:13px;color:{C["ink-muted"]};"'
    if r.apercu:
        exemples = [
            ("Display 36 boosters — Extension Exemple — FR (FICTIF)", "stock_local", "1", "209.90", "209.90"),
            ("Protège-cartes ×100 — exemple (FICTIF)", "stock_local", "2", "9.90", "19.80"),
            ("Coffret — Extension Exemple 2 — FR — Précommande (FICTIF)", "precommande", "1", "59.90", "59.90"),
        ]
        lignes = ""
        infos = {"stock_local": f"Expédition sous {r.champs.get('DELAI_EXPEDITION', '⟦DELAI_EXPEDITION⟧')}",
                 "precommande": "Expédiée à part, dès réception", "reservation": INFO_RESERVATION}
        for titre, statut, qte, pu, total in exemples:
            info = infos[statut]
            lignes += (
                f"<tr><td {td_g}><strong>{titre}</strong><br>{_badge(statut)} <span {detail}>&nbsp;{info}</span></td>"
                f"<td {td_d}>{qte} × {pu}<br><strong>CHF {total}</strong></td></tr>"
            )
        sous_total, port, total, preco, adresse = "CHF 289.60", "CHF 9.00", "CHF 298.60", True, "Léa Exemple<br>Rue Fictive 1<br>1200 Genève"
        reductions = ""
    else:
        lignes = (
            "{% assign a_precommande = false %}"
            "{% for line in subtotal_line_items %}"
            f"<tr><td {td_g}><strong>{{{{ line.title }}}}</strong><br>"
            "{% if line.sku contains '-RESA-' %}{% assign a_precommande = true %}"
            f"{_badge('reservation')} <span {detail}>&nbsp;{INFO_RESERVATION}</span>"
            "{% elsif line.title contains 'Précommande' %}{% assign a_precommande = true %}"
            f"{_badge('precommande')} <span {detail}>&nbsp;Expédiée à part, dès réception</span>"
            f"{{% else %}}{_badge('stock_local')} <span {detail}>&nbsp;Expédition sous {{{{DELAI_EXPEDITION}}}}</span>{{% endif %}}</td>"
            f"<td {td_d}>{{{{ line.quantity }}}} × {{{{ line.final_price | money }}}}<br><strong>{{{{ line.final_line_price | money }}}}</strong></td></tr>"
            "{% endfor %}"
        )
        sous_total, port, total, preco = "{{ subtotal_price | money }}", "{{ shipping_price | money }}", "{{ total_price | money }}", False
        adresse = (
            "{{ shipping_address.name }}<br>{{ shipping_address.address1 }}"
            "{% if shipping_address.address2 %}<br>{{ shipping_address.address2 }}{% endif %}"
            "<br>{{ shipping_address.zip }} {{ shipping_address.city }}"
        )
        reductions = (
            "{% if discounts_amount > 0 %}"
            f'<tr><td style="padding:4px 0;font-family:{POLICE};font-size:15px;color:{C["ink"]};">Réductions</td>'
            f'<td align="right" style="padding:4px 0;font-family:{POLICE_PRIX};font-size:15px;color:{C["ink"]};">− {{{{ discounts_amount | money }}}}</td></tr>'
            "{% endif %}"
        )
    td_tot_g = f'style="padding:4px 0;font-family:{POLICE};font-size:15px;color:{C["ink"]};"'
    td_tot_d = f'align="right" style="padding:4px 0;font-family:{POLICE_PRIX};font-size:15px;color:{C["ink"]};white-space:nowrap;"'
    mention_tva = _champs_fixes("{{MENTION_TVA}}", r)
    tableau = (
        '              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        + lignes
        + f'<tr><td style="padding:12px 0 4px 0;border-top:2px solid {C["ink"]};font-family:{POLICE};font-size:15px;color:{C["ink"]};">Sous-total articles</td>'
        f'<td align="right" style="padding:12px 0 4px 0;border-top:2px solid {C["ink"]};font-family:{POLICE_PRIX};font-size:15px;color:{C["ink"]};white-space:nowrap;">{sous_total}</td></tr>'
        + reductions
        + f"<tr><td {td_tot_g}>Livraison</td><td {td_tot_d}>{port}</td></tr>"
        f'<tr><td style="padding:8px 0 4px 0;font-family:{POLICE};font-size:18px;font-weight:bold;color:{C["ink"]};">Total payé</td>'
        f'<td align="right" style="padding:8px 0 4px 0;font-family:{POLICE_PRIX};font-size:18px;font-weight:bold;color:{C["ink"]};white-space:nowrap;">{total}</td></tr>'
        f'<tr><td colspan="2" style="padding:0 0 4px 0;font-family:{POLICE};font-size:13px;color:{C["ink-muted"]};">{mention_tva}</td></tr>'
        "</table>"
    )
    note_mixte = (
        "<strong>Commande mixte :</strong> les articles en stock local partent dès qu'ils sont prêts ; la précommande ou la "
        "réservation garantie est expédiée séparément, dès sa réception. La livraison n'est facturée qu'une fois. Nous vous "
        "écrivons si une date change."
    )
    encadre = _encadre_html([note_mixte])
    bloc_mixte = encadre if preco else "{% if a_precommande %}" + encadre + "{% endif %}"
    livraison = _p(f"<strong>Livraison</strong> (Suisse uniquement) :<br>{adresse}", taille=14, marge="12px 0 12px 0")
    return tableau + "\n" + bloc_mixte + "\n" + livraison


def _suivi_shopify(r: Rendu) -> str:
    """Articles de l'envoi et numéros de suivi (Liquid Shopify)."""
    if r.apercu:
        articles = "<li>Display 36 boosters — Extension Exemple — FR (FICTIF) × 1</li><li>Protège-cartes ×100 — exemple (FICTIF) × 2</li>"
        suivi = "Transporteur (FICTIF) · n° 99.00.000000.00000000 (FICTIF)"
        bouton = _bouton("Suivre mon colis", "https://exemple.invalid/suivi-fictif", "principal")
        return (
            f'              <ul style="margin:0 0 12px 20px;padding:0;font-size:15px;line-height:22px;color:{C["ink"]};">{articles}</ul>\n'
            + _p(f"<strong>Suivi :</strong> {suivi}")
            + "\n"
            + bouton
            + "\n"
            + _p(NOTE_ENVOI_SEPARE, taille=14, couleur=C["ink-muted"])
        )
    articles = "{% for line in fulfillment.fulfillment_line_items %}<li>{{ line.line_item.title }} × {{ line.quantity }}</li>{% endfor %}"
    return (
        f'              <ul style="margin:0 0 12px 20px;padding:0;font-size:15px;line-height:22px;color:{C["ink"]};">{articles}</ul>\n'
        "{% if fulfillment.tracking_numbers.size > 0 %}\n"
        + _p("<strong>Suivi :</strong> {{ fulfillment.tracking_company }} · n° {{ fulfillment.tracking_numbers | join: ', ' }}")
        + "\n"
        + _bouton("Suivre mon colis", "{{ fulfillment.tracking_urls.first }}", "principal")
        + "\n{% endif %}\n"
        + _p(NOTE_ENVOI_SEPARE, taille=14, couleur=C["ink-muted"])
    )


INFO_RESERVATION = "Servie en premier, expédiée à part dès réception"
NOTE_ENVOI_SEPARE = (
    "Si votre commande contient une précommande ou une réservation garantie, elle fait l'objet d'un envoi séparé, dès sa "
    "réception."
)


def _encadre_html(paragraphes: list[str]) -> str:
    corps = "<br><br>".join(paragraphes)
    return (
        f'              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 14px 0;background:{C["surface-alt"]};">'
        f'<tr><td style="padding:16px;font-family:{POLICE};font-size:14px;line-height:21px;color:{C["ink"]};word-break:break-word;">{corps}</td></tr></table>'
    )


def bloc_html(bloc: dict[str, Any], r: Rendu, email: dict[str, Any]) -> str:
    """Rendu HTML d'un bloc."""
    (type_bloc, valeur), = bloc.items()
    if type_bloc == "titre":
        return _ligne(
            f'              <h1 style="margin:0 0 12px 0;font-size:22px;line-height:28px;font-weight:bold;text-transform:uppercase;color:{C["ink"]};word-break:break-word;">{en_html(valeur, r)}</h1>',
            "20px 24px 4px 24px",
        )
    if type_bloc == "sous_titre":
        return _ligne(f'              <h2 style="margin:8px 0 8px 0;font-size:17px;line-height:23px;font-weight:bold;color:{C["ink"]};">{en_html(valeur, r)}</h2>')
    if type_bloc == "p":
        return _ligne(_p(en_html(valeur, r)))
    if type_bloc == "liste":
        items = "".join(f'<li style="margin:0 0 6px 0;">{en_html(i, r)}</li>' for i in valeur)
        return _ligne(f'              <ul style="margin:0 0 12px 20px;padding:0;font-size:15px;line-height:22px;color:{C["ink"]};">{items}</ul>')
    if type_bloc == "encadre":
        return _ligne(_encadre_html([en_html(v, r) for v in valeur]))
    if type_bloc == "bouton":
        url = en_html(valeur["url"], r)
        return _ligne(_bouton(en_html(valeur["texte"], r), url, valeur.get("style", "principal")))
    if type_bloc == "produit":
        return _ligne(
            _produit_html(
                en_html(valeur["titre"], r), valeur["statut"], en_html(valeur.get("detail", ""), r),
                en_html(valeur.get("prix", ""), r), en_html(valeur.get("limite", ""), r),
            )
        )
    if type_bloc == "lignes_produits":
        if r.apercu:
            return _ligne(lignes_produits_exemple(r))
        return _ligne("              " + variable(valeur["variable"], r))
    if type_bloc == "faits":
        lignes = "".join(
            f'<tr><td style="padding:6px 12px 6px 0;font-family:{POLICE};font-size:14px;font-weight:bold;color:{C["ink"]};vertical-align:top;">{en_html(a, r)}</td>'
            f'<td style="padding:6px 0;font-family:{POLICE};font-size:14px;color:{C["ink"]};">{en_html(b, r)}</td></tr>'
            for a, b in valeur
        )
        return _ligne(f'              <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0;">{lignes}</table>')
    if type_bloc == "commande_shopify":
        return _ligne(_commande_shopify(r))
    if type_bloc == "suivi_shopify":
        return _ligne(_suivi_shopify(r))
    raise EmailError(f"{email['id']} : bloc inconnu {type_bloc}")


def lignes_produits_exemple(r: Rendu) -> str:
    """Deux lignes FICTIVES pour l'aperçu, rendues avec les gabarits partiels."""
    exemples = {p["id"]: {v[0]: str(v[2]) for v in p["variables"]} for p in charger_source()["partiels"]}
    return "\n".join(
        partiel_html(p, Rendu("n8n", exemples[p["id"]], r.champs)) for p in charger_source()["partiels"]
    )


def partiel_html(partiel: dict[str, Any], r: Rendu) -> str:
    """Gabarit d'une ligne produit (variables n8n : {{ $json.titre }}…)."""
    return _produit_html(
        en_html("[[titre]]", r), partiel["statut"], en_html(partiel["detail"], r), en_html("[[prix]]", r), "", url=en_html("[[url]]", r)
    )


# ----------------------------------------------------------------------------- pied de page
#: Motif d'envoi affiché dans le pied d'un email marketing (clé ``motif_pied`` de la source, obligatoire pour
#: cette catégorie) : il doit décrire la base réelle du segment, jamais une inscription que la personne n'a pas faite.
MOTIFS_PIED: dict[str, tuple[str, str]] = {
    "alertes": (
        "Vous recevez cet email parce que cette adresse est inscrite à nos alertes (inscription confirmée le [[date_consentement]]).",
        "[Modifier mes préférences]([[url_preferences]]) · [Me désinscrire en un clic]([[url_desinscription]])",
    ),
    "client": (
        "Vous recevez cet email parce que vous avez commandé chez nous et avez accepté nos emails, ou ne vous y êtes pas "
        "opposé lors de votre commande.",
        "[Me désinscrire en un clic]([[url_desinscription]])",
    ),
    "checkout": (
        "Vous recevez cet email parce que vous avez accepté nos emails lors de votre passage en caisse le [[date_consentement]].",
        "[Me désinscrire en un clic]([[url_desinscription]])",
    ),
}


def pied(categorie: str, r: Rendu, mode_texte: bool = False, motif: str | None = None) -> list[str]:
    """Lignes du pied de page selon la catégorie (texte source, converti ensuite).

    Pour un email marketing, ``motif`` (clé de :data:`MOTIFS_PIED`) est obligatoire : sans motif connu, refus.
    """
    identite = "{{RAISON_SOCIALE}} · {{ADRESSE_POSTALE}}"
    mention = "Boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus."
    contact = "Une question ? Répondez à cet email ou écrivez à {{EMAIL_SUPPORT}}."
    if categorie == "transactionnel":
        return [contact, "Conditions de vente : {{URL_CGV}} · Livraison et retours : {{URL_RETOURS}}", identite, mention,
                "Vous recevez cet email parce que vous avez passé commande ; il ne contient aucune publicité."]
    if categorie == "marketing":
        if motif not in MOTIFS_PIED:
            raise EmailError(f"motif de pied inconnu ou absent pour un email marketing : {motif!r}")
        raison, liens = MOTIFS_PIED[motif]
        return [contact, identite, mention, raison, liens, "Confidentialité : {{URL_CONFIDENTIALITE}}"]
    if categorie == "avis":
        return [identite, mention,
                "Vous recevez cet email parce que vous avez commandé chez nous, sans opposition de votre part à ce type de message. "
                "Une seule demande par commande.",
                "[Ne plus recevoir de demande d'avis]([[url_refus_avis]]) · Confidentialité : {{URL_CONFIDENTIALITE}}"]
    if categorie == "inscription":
        return [identite, mention,
                "Vous recevez cet email unique parce que cette adresse a été saisie sur notre page d'inscription.",
                "Confidentialité : {{URL_CONFIDENTIALITE}}"]
    if categorie == "desinscription":
        return [identite, mention, "Confidentialité : {{URL_CONFIDENTIALITE}}"]
    raise EmailError(f"catégorie inconnue : {categorie}")


# ----------------------------------------------------------------------------- documents
def document_html(email: dict[str, Any], r: Rendu) -> str:
    """Email complet en HTML (modèle ou aperçu)."""
    objet = en_texte(email["objet"], r)
    pre = en_texte(email["pre_entete"], r)
    nom = _champs_fixes("{{NOM_BOUTIQUE}}", r)
    logo = _champs_fixes("{{URL_LOGO_PNG}}", r)
    blocs = "\n".join(bloc_html(b, r, email) for b in email["blocs"])
    lignes_pied = "<br>".join(en_html(ligne, r) for ligne in pied(email["categorie"], r, motif=email.get("motif_pied")))
    variables = "\n".join(f"      - {v[0]} : {v[1]}" for v in email["variables"])
    entete = (
        f"  <!--\n    FICHIER GÉNÉRÉ par docs/06-contenu/outils/generer_emails.py depuis EMAILS/source/emails.yaml — ne pas modifier.\n"
        f"    Email {email['id']} — {email['nom']} — canal : {email['canal']}\n"
        f"    Objet : {email['objet']}\n    Pré-en-tête : {email['pre_entete']}\n"
        f"    Déclencheur : {email['declencheur']}\n    Segment : {email['segment']}\n    Base : {email['base']}\n"
        f"    Fréquence : {email['frequence']}\n    Variables :\n{variables}\n"
        "    Champs fixes (MAJUSCULES entre doubles accolades) : registre docs/04-legal/champs_a_remplir.yaml, plus URL_LOGO_PNG\n"
        "    (PNG du logo hébergé, docs/05-da/logo/png/). Pour Shopify, coller la copie produite par --integration, jamais ce fichier.\n"
        "    Règles : aucune donnée interne ; prix publics relus à l'envoi ; aucune fausse urgence.\n  -->\n"
    ) if not r.apercu else ""
    return f"""<!DOCTYPE html>
<html lang="fr-CH">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{html.escape(objet)}</title>
{entete}</head>
<body style="margin:0;padding:0;background:{C['bg']};">
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{html.escape(pre)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{C['bg']};">
    <tr>
      <td align="center" style="padding:16px 8px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:{C['surface']};">
          <tr>
            <td style="padding:24px 24px 8px 24px;">
              <img src="{html.escape(logo, quote=True)}" width="200" alt="{html.escape(nom, quote=True)}" style="display:block;border:0;outline:none;text-decoration:none;height:auto;font-family:{POLICE};font-size:18px;font-weight:bold;color:{C['ink']};">
            </td>
          </tr>
          <tr><td style="padding:0 24px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td height="6" style="height:6px;line-height:6px;font-size:0;background:{C['accent']};">&nbsp;</td></tr></table></td></tr>
{blocs}
          <tr>
            <td style="padding:16px 24px 24px 24px;border-top:1px solid {C['line']};font-family:{POLICE};font-size:12px;line-height:18px;color:{C['ink-muted']};word-break:break-word;">
              {lignes_pied}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def bloc_texte(bloc: dict[str, Any], r: Rendu) -> list[str]:
    """Rendu texte d'un bloc (liste de paragraphes)."""
    (type_bloc, valeur), = bloc.items()
    if type_bloc == "titre":
        return [majuscules_hors_expressions(en_texte(valeur, r))]
    if type_bloc == "sous_titre":
        return [en_texte(valeur, r)]
    if type_bloc == "p":
        return [en_texte(valeur, r)]
    if type_bloc == "liste":
        return ["\n".join(f"- {en_texte(i, r)}" for i in valeur)]
    if type_bloc == "encadre":
        return ["\n".join(f"> {en_texte(v, r)}" for v in valeur)]
    if type_bloc == "bouton":
        return [f"{en_texte(valeur['texte'], r)} : {en_texte(valeur['url'], r)}"]
    if type_bloc == "produit":
        lignes = [en_texte(valeur["titre"], r), f"{LIBELLES_TEXTE[valeur['statut']]} · {en_texte(valeur.get('detail', ''), r)}"]
        if valeur.get("prix"):
            lignes.append(f"CHF {en_texte(valeur['prix'], r)}")
        if valeur.get("limite"):
            lignes.append(en_texte(valeur["limite"], r))
        return ["\n".join(lignes)]
    if type_bloc == "lignes_produits":
        if r.apercu:
            return ["Display 36 boosters — Extension Exemple — FR (FICTIF) · Stock local · CHF 209.90 (FICTIF)\n"
                    "Coffret — Extension Exemple 2 — FR (FICTIF) · Précommande · CHF 59.90 (FICTIF)"]
        return [variable(valeur["variable"].replace("_html", "_texte"), r)]
    if type_bloc == "faits":
        return ["\n".join(f"{en_texte(a, r)} : {en_texte(b, r)}" for a, b in valeur)]
    if type_bloc == "commande_shopify":
        return [
            "{% for line in subtotal_line_items %}- {{ line.title }} × {{ line.quantity }} : {{ line.final_line_price | money }}"
            "{% if line.sku contains '-RESA-' %} (réservation garantie : servie en premier, expédiée à part dès réception)"
            "{% elsif line.title contains 'Précommande' %} (précommande, expédiée à part){% endif %}\n{% endfor %}"
            "Sous-total : {{ subtotal_price | money }}\n{% if discounts_amount > 0 %}Réductions : − {{ discounts_amount | money }}\n{% endif %}"
            "Livraison : {{ shipping_price | money }}\nTotal payé : {{ total_price | money }}\n{{MENTION_TVA}}",
            "Livraison (Suisse uniquement) : {{ shipping_address.name }}, {{ shipping_address.address1 }}, {{ shipping_address.zip }} {{ shipping_address.city }}",
        ]
    if type_bloc == "suivi_shopify":
        return [
            "{% for line in fulfillment.fulfillment_line_items %}- {{ line.line_item.title }} × {{ line.quantity }}\n{% endfor %}"
            "{% if fulfillment.tracking_numbers.size > 0 %}Suivi : {{ fulfillment.tracking_company }} · n° {{ fulfillment.tracking_numbers | join: ', ' }}\n"
            "Suivre mon colis : {{ fulfillment.tracking_urls.first }}{% endif %}",
            NOTE_ENVOI_SEPARE,
        ]
    raise EmailError(f"bloc inconnu {type_bloc}")


def document_texte(email: dict[str, Any], r: Rendu) -> str:
    """Version texte d'un email."""
    paragraphes = [p for b in email["blocs"] for p in bloc_texte(b, r)]
    pied_txt = [en_texte(ligne, r) for ligne in pied(email["categorie"], r, motif=email.get("motif_pied"))]
    return f"Objet : {en_texte(email['objet'], r)}\n\n" + "\n\n".join(paragraphes) + "\n\n--\n" + "\n".join(pied_txt) + "\n"


# ----------------------------------------------------------------------------- source et sorties
def charger_source(chemin: Path = SOURCE) -> dict[str, Any]:
    """Charge et valide la source YAML."""
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    erreurs: list[str] = []
    ids = [e.get("id") for e in donnees.get("emails", [])]
    if len(ids) != len(set(ids)):
        erreurs.append("identifiants d'email en double")
    for e in donnees.get("emails", []):
        for cle in ("id", "nom", "canal", "categorie", "declencheur", "segment", "base", "frequence", "objet", "pre_entete", "variables", "blocs"):
            if cle not in e:
                erreurs.append(f"{e.get('id')} : clé « {cle} » manquante")
        if e.get("canal") not in CANAUX:
            erreurs.append(f"{e.get('id')} : canal inconnu {e.get('canal')}")
        if e.get("categorie") not in CATEGORIES:
            erreurs.append(f"{e.get('id')} : catégorie inconnue {e.get('categorie')}")
        declarees = {v[0].split(".")[0] for v in e.get("variables", [])} | {"salutation"}
        texte = json.dumps(e.get("blocs", []), ensure_ascii=False) + e.get("objet", "") + e.get("pre_entete", "")
        if e.get("categorie") == "marketing" and e.get("motif_pied") not in MOTIFS_PIED:
            erreurs.append(f"{e.get('id')} : motif_pied obligatoire pour un email marketing ({sorted(MOTIFS_PIED)})")
        elif e.get("motif_pied") == "alertes" and re.search(r"checkout|client", f"{e.get('segment', '')} {e.get('base', '')}", re.I):
            # Un segment de clients ou de consentement au checkout n'est pas « inscrit à nos alertes ».
            erreurs.append(f"{e.get('id')} : motif_pied « alertes » incohérent avec le segment ou la base (clients, checkout)")
        elif e.get("categorie") != "marketing" and "motif_pied" in e:
            erreurs.append(f"{e.get('id')} : motif_pied réservé aux emails marketing")
        elif e.get("categorie") in CATEGORIES:
            texte += json.dumps(pied(e["categorie"], Rendu("n8n", {}, {}), motif=e.get("motif_pied")), ensure_ascii=False)
        for nom in VAR_RE.findall(texte):
            racine = nom.split("|")[0].strip().split(".")[0]
            if racine not in declarees:
                erreurs.append(f"{e.get('id')} : variable [[{nom}]] non déclarée")
        for b in e.get("blocs", []):
            if not isinstance(b, dict) or len(b) != 1 or next(iter(b)) not in TYPES_BLOCS:
                erreurs.append(f"{e.get('id')} : bloc invalide {b}")
    if erreurs:
        raise EmailError("; ".join(erreurs))
    return donnees


def champs_apercu() -> dict[str, str]:
    """Valeurs des champs fixes pour l'aperçu : registre légal (validées ou proposées), sinon marqueur."""
    registre = yaml.safe_load((REPO / "docs" / "04-legal" / "champs_a_remplir.yaml").read_text(encoding="utf-8"))["champs"]
    valeurs: dict[str, str] = {}
    for nom, f in registre.items():
        v = f.get("valeur") or f.get("valeur_proposee")
        if v and "{{" not in v:
            valeurs[nom] = v + (" ⟦à valider⟧" if f.get("statut") == "a_valider" else "")
    valeurs["NOM_BOUTIQUE"] = f"{NOM_DE_TRAVAIL} (nom provisoire)"
    valeurs["URL_LOGO_PNG"] = "../../05-da/logo/png/logo-a-email.png"
    return valeurs


def exemples(email: dict[str, Any]) -> dict[str, str]:
    """Valeurs FICTIVES des variables d'un email (colonne exemple)."""
    sortie = {v[0].split(".")[0]: str(v[2]) for v in email["variables"]}
    sortie.setdefault("salutation", "Bonjour Léa,")
    return sortie


def fichiers_generes() -> dict[Path, str]:
    """Tous les fichiers générés : chemin → contenu."""
    source = charger_source()
    sorties: dict[Path, str] = {}
    for e in source["emails"]:
        r = Rendu(e["canal"], {}, {})
        sorties[EMAILS / "html" / f"{e['id']}.html"] = document_html(e, r)
        sorties[EMAILS / "texte" / f"{e['id']}.txt"] = document_texte(e, r)
    for p in source["partiels"]:
        variables = "\n".join(f"  - {v[0]} : {v[1]}" for v in p["variables"])
        sorties[EMAILS / "html" / f"{p['id']}.html"] = (
            f"<!-- FICHIER GÉNÉRÉ par docs/06-contenu/outils/generer_emails.py — gabarit de ligne produit ({p['statut']}).\n"
            f"Le workflow n8n le remplit pour chaque produit puis concatène les lignes dans lignes_produits_html\n"
            f"(et une ligne « titre · statut · CHF prix » par produit dans lignes_produits_texte). Variables :\n{variables} -->\n"
            + partiel_html(p, Rendu("n8n", {}, {}))
            + "\n"
        )
    sorties[EMAILS / "apercu.html"] = page_apercu(source)
    sorties[README] = readme_avec_tableau(source)
    return sorties


def page_apercu(source: dict[str, Any]) -> str:
    """Page de relecture : chaque email rempli avec des données FICTIVES."""
    champs = champs_apercu()
    sections = []
    for e in source["emails"]:
        r = Rendu(e["canal"], exemples(e), champs)
        doc = document_html(e, r)
        corps = doc.split('<body style="margin:0;padding:0;background:' + C["bg"] + ';">', 1)[1].rsplit("</body>", 1)[0]
        meta = "".join(
            f"<tr><th scope=\"row\">{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in (("Canal", e["canal"]), ("Déclencheur", e["declencheur"]), ("Segment", e["segment"]), ("Base", e["base"]),
                         ("Fréquence", e["frequence"]), ("Objet", en_texte(e["objet"], r)), ("Pré-en-tête", en_texte(e["pre_entete"], r)))
        )
        sections.append(
            f'<section id="email-{e["id"]}"><h2>{html.escape(e["id"])} — {html.escape(e["nom"])}</h2>'
            f'<table class="meta">{meta}</table><div class="email">{corps}</div></section>'
        )
    sommaire = "".join(f'<li><a href="#email-{e["id"]}">{html.escape(e["id"])} — {html.escape(e["nom"])}</a></li>' for e in source["emails"])
    return f"""<!DOCTYPE html>
<html lang="fr-CH">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aperçu des emails — {NOM_DE_TRAVAIL} (nom provisoire)</title>
  <!-- FICHIER GÉNÉRÉ par docs/06-contenu/outils/generer_emails.py — données d'exemple FICTIVES. -->
  <style>
    body {{ margin: 0; padding: 16px; background: {C['surface-alt']}; color: {C['ink']}; font-family: {POLICE}; }}
    main {{ max-width: 760px; margin: 0 auto; }}
    section {{ margin: 32px 0; padding: 16px; background: {C['surface']}; border: 1px solid {C['line']}; }}
    .meta {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; }}
    .meta th, .meta td {{ text-align: left; vertical-align: top; padding: 4px 8px; border-bottom: 1px solid {C['line']}; }}
    .meta th {{ width: 9rem; }}
    .email {{ overflow-x: auto; }}
    .avertissement {{ padding: 12px; background: {C['status-restock-bg']}; color: {C['status-restock-fg']}; }}
  </style>
</head>
<body>
  <main>
    <h1>Aperçu des {len(source['emails'])} emails</h1>
    <p class="avertissement"><strong>Données FICTIVES.</strong> Nom de travail provisoire « {NOM_DE_TRAVAIL} ». Les valeurs marquées ⟦à valider⟧ sont des propositions du registre légal ; ⟦CHAMP⟧ = champ encore à remplir. Les emails Shopify (06, 07) sont montrés avec des lignes d'exemple à la place des boucles Liquid. Emails 15 à 19 : pré-drop (réservation garantie, décision du 6.10.2026).</p>
    <ol>{sommaire}</ol>
    {''.join(sections)}
    <h2>Validation humaine requise</h2>
    <p>Relire chaque email (objet, texte, déclencheur, segment) et valider les textes transactionnels avant intégration (RACI L44).</p>
  </main>
</body>
</html>
"""


def tableau_readme(source: dict[str, Any]) -> str:
    """Tableau récapitulatif des emails (Markdown)."""
    lignes = ["| N° | Email | Canal | Déclencheur | Segment | Base | Fréquence | Objet |", "|---|---|---|---|---|---|---|---|"]
    for e in source["emails"]:
        n, _, reste = e["id"].partition("-")
        lignes.append(
            f"| {n} | [{e['nom']}](html/{e['id']}.html) · [texte](texte/{e['id']}.txt) | {e['canal']} | {e['declencheur']} | "
            f"{e['segment']} | {e['base']} | {e['frequence']} | {e['objet'].replace('|', '/')} |"
        )
    return "\n".join(lignes)


def readme_avec_tableau(source: dict[str, Any]) -> str:
    """README.md avec le tableau injecté entre les marqueurs."""
    texte = README.read_text(encoding="utf-8")
    debut, fin = texte.index(MARQUE_DEBUT), texte.index(MARQUE_FIN)
    return texte[: debut + len(MARQUE_DEBUT)] + "\n" + tableau_readme(source) + "\n" + texte[fin:]


def valeurs_validees(chemin_registre: Path | None = None) -> dict[str, str]:
    """Champs du registre légal au statut « valide » (alias résolus)."""
    chemin = chemin_registre or REPO / "docs" / "04-legal" / "champs_a_remplir.yaml"
    registre = yaml.safe_load(chemin.read_text(encoding="utf-8"))["champs"]
    valeurs: dict[str, str] = {}
    for nom, f in registre.items():
        cible = registre.get(f["alias_de"], {}) if f.get("alias_de") else f
        if cible.get("statut") == "valide" and cible.get("valeur"):
            valeurs[nom] = str(cible["valeur"])
    return valeurs


def integrer(sortie: Path, url_logo: str, valeurs: dict[str, str] | None = None) -> list[str]:
    """Copie html/ et texte/ dans ``sortie`` avec les champs {{CHAMP}} validés ; retourne les manquants (rien n'est écrit alors)."""
    valeurs = dict(valeurs if valeurs is not None else valeurs_validees())
    if not url_logo.startswith("https://"):
        return ["URL_LOGO_PNG : URL https du logo hébergé attendue (--url-logo)"]
    valeurs["URL_LOGO_PNG"] = url_logo
    modeles = {p: c for p, c in fichiers_generes().items() if p.parent.name in ("html", "texte")}
    manquants = sorted({m for c in modeles.values() for m in CHAMP_RE.findall(c) if m not in valeurs})
    if manquants:
        return manquants
    for chemin, contenu in modeles.items():
        cible = sortie / chemin.parent.name / chemin.name
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(CHAMP_RE.sub(lambda m: valeurs[m.group(1)], contenu), encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verifier", action="store_true", help="code 1 si un fichier généré diffère")
    parser.add_argument("--integration", type=Path, default=None, help="dossier : modèles avec les champs validés (refus si un champ manque)")
    parser.add_argument("--url-logo", default="", help="URL https du PNG du logo hébergé (avec --integration)")
    args = parser.parse_args(argv)
    if args.integration:
        manquants = integrer(args.integration, args.url_logo)
        if manquants:
            print(f"REFUS : {len(manquants)} champ(s) non validé(s) ou absent(s)")
            for m in manquants:
                print(f"  - {m}")
            return 1
        print(f"Modèles prêts à intégrer dans {args.integration}")
        return 0
    sorties = fichiers_generes()
    if args.verifier:
        ecarts = [p for p, c in sorties.items() if not p.exists() or p.read_text(encoding="utf-8") != c]
        for p in ecarts:
            print(f"désynchronisé : {p.relative_to(REPO)}")
        print("Emails synchronisés." if not ecarts else "Relancer generer_emails.py.")
        return 1 if ecarts else 0
    for chemin, contenu in sorties.items():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    print(f"{len(sorties)} fichiers écrits dans {EMAILS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
