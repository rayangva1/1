"""Rendu des snippets Liquid avec python-liquid (outil de test local, facultatif).

python-liquid n'est pas une dépendance du projet : sans lui, ces tests sont ignorés et seul le
contrôle statique (test_site.py) s'exécute. Les balises propres à Shopify ({% form %},
``form.posted_successfully?``, filtre ``default_errors``) sont remplacées par des équivalents neutres.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

liquid = pytest.importorskip("liquid")

SNIPPETS = Path(__file__).resolve().parents[1] / "shopify" / "snippets"
USAGE_MARQUES = Path(__file__).resolve().parents[2] / "docs" / "04-legal" / "USAGE_MARQUES.md"
REGLAGES = {"delai_expedition_local": "2 jours ouvrés", "url_page_precommandes": "/pages/precommandes", "url_confidentialite": "/policies/privacy-policy"}


def _env() -> Any:
    sources = {}
    for p in SNIPPETS.glob("*.liquid"):
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"\{%-?\s*form\b[^%]*-?%\}", "<form>", t)
        t = re.sub(r"\{%-?\s*endform\s*-?%\}", "</form>", t)
        sources[p.stem] = t.replace("form.posted_successfully?", "form.posted_successfully")
    env = liquid.Environment(loader=liquid.DictLoader(sources))
    env.filters["default_errors"] = lambda valeur: "Erreur de saisie."
    return env


ENV = _env()


def produit(statut: str | None = "stock_local", disponible: bool = True, tags: tuple[str, ...] = (), **meta: Any) -> dict[str, Any]:
    """Produit FICTIF au format attendu par les snippets."""
    champs = {cle: {"value": val} for cle, val in meta.items()}
    if statut is not None:
        champs["statut_stock"] = {"value": statut}
    return {"available": disponible, "tags": list(tags), "handle": "display-exemple-fictif", "id": 42, "metafields": {"boutique": champs}}


def rendre(nom: str, **contexte: Any) -> str:
    sortie = ENV.get_template(nom).render(settings=REGLAGES, **contexte)
    sortie = re.sub(r"<svg.*?</svg>", "", sortie, flags=re.DOTALL)
    return re.sub(r"\s+", " ", sortie).strip()


@pytest.mark.parametrize(
    ("p", "libelle", "detail"),
    [
        (produit("stock_local"), "Stock local", "Expédié depuis Genève sous 2 jours ouvrés."),
        (produit("precommande", date_sortie="2026-11-06", date_sortie_statut="confirmee"), "Précommande (allocation confirmée)", "Sortie le 06.11.2026 · expédition dès réception."),
        (produit("precommande", date_sortie="2026-11-06", date_sortie_statut="estimee"), "Précommande (allocation confirmée)", "Sortie estimée au 06.11.2026 (peut changer)"),
        (produit("precommande"), "Précommande (allocation confirmée)", "Date de sortie non confirmée"),
        (produit("stock_local", disponible=False, alerte_reassort=True), "Rupture – alerte", "sans date promise"),
        (produit("rupture", disponible=False, fin_de_serie=True, alerte_reassort=True), "Rupture", "Fin de série"),
        (produit("rupture", disponible=False), "Rupture", "Plus d'unité disponible."),
        (produit(None), "Disponibilité à confirmer", "Écrivez-nous"),
        (produit("rupture", disponible=True), "Disponibilité à confirmer", "Écrivez-nous"),
    ],
)
def test_statut_stock(p: dict[str, Any], libelle: str, detail: str) -> None:
    html = rendre("da-statut-stock", product=p)
    assert f"<span>{libelle}" in html and detail in html
    assert not re.search(r"\d+ (en stock|unités?|pièces?)", html)


def test_statut_stock_mode_carte_sans_detail() -> None:
    html = rendre("da-statut-stock", product=produit("stock_local"), contexte="carte")
    assert "Stock local" in html and "da-stock__detail" not in html


def test_inventaire_shopify_prime_sur_le_metachamp() -> None:
    html = rendre("da-statut-stock", product=produit("stock_local", disponible=False))
    assert 'data-statut="rupture"' in html and "Stock local" not in html


@pytest.mark.parametrize(
    ("p", "attendus", "absents"),
    [
        (produit("stock_local", langue="FR", tags=("nouveaute",)), ["FR", "Stock local", "Nouveauté"], ["Précommande", "Rupture"]),
        (produit("precommande", langue="FR"), ["FR", "Précommande"], ["Stock local", "Rupture"]),
        (produit("stock_local", disponible=False, langue="FR", alerte_reassort=True, tags=("nouveaute",)), ["FR", "Rupture", "Alerte réassort"], ["Nouveauté", "Stock local"]),
        (produit("rupture", disponible=False, alerte_reassort=True, fin_de_serie=True), ["Rupture"], ["Alerte réassort"]),
        (produit(None, langue="EN"), [], ["FR", "Stock local", "Précommande", "Rupture"]),
    ],
)
def test_badges(p: dict[str, Any], attendus: list[str], absents: list[str]) -> None:
    html = rendre("da-badges", product=p)
    badges = re.findall(r'role="listitem">([^<]*)</span>', html)
    assert badges == attendus
    for a in absents:
        assert a not in badges
    assert len(badges) <= 3


def test_badges_jamais_stock_local_et_precommande() -> None:
    for statut in ("stock_local", "precommande", "rupture", None):
        for dispo in (True, False):
            html = rendre("da-badges", product=produit(statut, disponible=dispo, langue="FR", tags=("nouveaute",), alerte_reassort=True))
            assert not ("Stock local" in html and "Précommande" in html)


def test_bloc_delai_et_sortie() -> None:
    local = rendre("da-delai-sortie", product=produit("stock_local", quantite_max=2))
    assert "Depuis Genève, sous 2 jours ouvrés." in local and "2 par commande" in local and "Date de sortie" not in local
    assert "En Suisse uniquement." in local and "Commande mixte" not in local
    preco = rendre("da-delai-sortie", product=produit("precommande", date_sortie="2026-11-06", date_sortie_statut="estimee"))
    assert "06.11.2026 (estimée, peut changer)" in preco and "Commande mixte" in preco
    assert "Pas de garantie de livraison le jour de la sortie." in preco and 'href="/pages/precommandes"' in preco
    preco_sans_date = rendre("da-delai-sortie", product=produit("precommande"))
    assert "Non confirmée" in preco_sans_date
    rupture = rendre("da-delai-sortie", product=produit("stock_local", disponible=False))
    assert "Aucune expédition possible pour le moment." in rupture


def test_mention_independance() -> None:
    courte = rendre("da-mention-independance", shop={"name": "Quai des Cartes"})
    assert "Boutique indépendante, sans lien officiel avec les éditeurs des jeux vendus." in courte
    complete = rendre("da-mention-independance", version="complete", shop={"name": "Quai des Cartes"})
    reference = re.search(r"\{\{NOM_BOUTIQUE\}\} (est une boutique indépendante\..*?revendons\.)", USAGE_MARQUES.read_text(encoding="utf-8"), re.DOTALL)
    assert reference is not None
    attendu = re.sub(r"\s+", " ", reference.group(1)).replace(" ;", "&#8239;;")
    assert f"Quai des Cartes {attendu}" in complete


def test_formulaire_alertes() -> None:
    reassort = rendre("da-formulaire-alertes", contexte="reassort", product=produit("rupture", disponible=False), form={})
    assert 'value="alerte-reassort, alerte-produit:display-exemple-fictif"' in reassort
    assert re.search(r'<input id="alerte-reassort-42-consentement" type="checkbox" required>', reassort)
    assert "checked" not in reassort and 'href="/policies/privacy-policy"' in reassort
    assert "M'alerter du retour en stock" in reassort
    ouverture = rendre("da-formulaire-alertes", form={})
    assert 'value="alerte-ouverture"' in ouverture and "M'inscrire aux alertes" in ouverture
    merci = rendre("da-formulaire-alertes", form={"posted_successfully": True})
    assert "Confirmez votre inscription" in merci and "contact[email]" not in merci
    erreur = rendre("da-formulaire-alertes", form={"errors": ["email"]})
    assert 'role="alert"' in erreur
