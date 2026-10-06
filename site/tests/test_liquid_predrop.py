"""Pré-drop côté boutique : rendu des snippets « Réservation garantie » avec python-liquid (facultatif) et contrôles
statiques (textes de garantie identiques au moteur, aucune fausse urgence).

Décision de la propriétaire du 6.10.2026 : fiche jumelle de type « Réservation garantie » (prix pré-drop, inventaire =
réservations encore ouvertes) liée à la fiche normale (prix du drop) par le métachamp ``boutique.fiche_liee``.
Les dates de drop des tests sont loin dans le futur (2099) ou dans le passé (2020) : le rendu dépend du jour courant.
Données FICTIVES.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNIPPETS = ROOT / "site" / "shopify" / "snippets"
PREDROP_PY = ROOT / "engine" / "pokeshop" / "predrop.py"
PUBLISH_PY = ROOT / "engine" / "pokeshop" / "publish.py"
FUTUR = "2099-10-20"
PASSE = "2020-01-01"
NORMAL = "display-alpha-fictif-dsp-fictif-alpha-fr"
RESA = f"{NORMAL}-reservation-garantie"


def _constant(path: Path, name: str) -> str:
    """Valeur d'une constante texte du moteur (concaténation de littéraux), lue sans importer le moteur."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^{name} = \(\n(.*?)\n\)", text, re.MULTILINE | re.DOTALL)
    assert match is not None, name
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1)))


GARANTIE = _constant(PREDROP_PY, "GUARANTEE_TEXT_FR")
DIFFERENCE = _constant(PREDROP_PY, "NO_DIFFERENCE_REFUND_FR")
URGENCE = re.compile(
    r"plus que|derni[eè]re|restant|il reste \d|vite|compte à rebours|minuteur|jusqu'à \d|\d+ (unités?|places?|pièces?)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------------------------- statique


def test_les_textes_de_garantie_sont_ceux_du_moteur() -> None:
    assert "pas le produit" in GARANTIE and "Aucun remboursement de la différence" in DIFFERENCE
    encart = (SNIPPETS / "da-reservation-garantie.liquid").read_text(encoding="utf-8")
    assert f'<p class="da-note">{GARANTIE}</p>' in encart
    assert f'<p class="da-note">{DIFFERENCE}</p>' in encart
    assert "nous vous remboursons intégralement, supplément compris" in encart


def test_type_et_metachamps_du_snippet_sont_ceux_de_la_publication() -> None:
    publish = PUBLISH_PY.read_text(encoding="utf-8")
    assert 'PREDROP_PRODUCT_TYPE = "Réservation garantie"' in publish
    for key in ("date_drop", "reservation_statut", "fiche_liee"):
        assert f'"{key}":' in publish, key
    for nom in ("da-reservation-garantie", "da-reservation-acces", "da-badges", "da-statut-stock", "da-delai-sortie"):
        source = (SNIPPETS / f"{nom}.liquid").read_text(encoding="utf-8")
        assert "'Réservation garantie'" in source, nom
    acces = (SNIPPETS / "da-reservation-acces.liquid").read_text(encoding="utf-8")
    # Fenêtre prioritaire : étiquette des alertes de la fiche normale ET consentement confirmé (même critère que n8n 02).
    assert "'alerte-produit:' | append: fiche_liee" in acces and "customer.accepts_marketing == true" in acces


def test_aucune_fausse_urgence_dans_les_snippets_du_pre_drop() -> None:
    for nom in ("da-reservation-garantie", "da-reservation-acces"):
        source = (SNIPPETS / f"{nom}.liquid").read_text(encoding="utf-8")
        visible = re.sub(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", "", source, flags=re.DOTALL)
        assert not URGENCE.search(visible), nom
        for interne in ("quota", "inventory_quantity", "closes_at", "opens_at", "cout", "coût", "marge"):
            assert interne not in visible, (nom, interne)


# --------------------------------------------------------------------------------------------- rendu

liquid = pytest.importorskip("liquid")


def _env() -> Any:
    sources = {}
    for p in SNIPPETS.glob("*.liquid"):
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"\{%-?\s*form\b[^%]*-?%\}", "<form>", t)
        t = re.sub(r"\{%-?\s*endform\s*-?%\}", "</form>", t)
        sources[p.stem] = t.replace("form.posted_successfully?", "form.posted_successfully")
    env = liquid.Environment(loader=liquid.DictLoader(sources))
    env.filters["default_errors"] = lambda valeur: "Erreur de saisie."
    env.filters["money"] = lambda centimes: f"CHF {int(centimes) // 100}.{int(centimes) % 100:02d}"
    return env


ENV = _env()
REGLAGES = {"delai_expedition_local": "2 jours ouvrés", "url_page_precommandes": "/pages/precommandes"}


def fiche(
    *,
    reservation: bool = True,
    statut_resa: str | None = "ouvertes",
    date_drop: str | None = FUTUR,
    disponible: bool = True,
    statut: str | None = None,
    prix: int | None = None,
    **meta: Any,
) -> dict[str, Any]:
    """Fiche FICTIVE : de réservation (prix pré-drop) ou normale (prix du drop), métachamps du moteur."""
    champs: dict[str, Any] = {k: {"value": v} for k, v in meta.items()}
    if statut is None:
        statut = ("precommande" if statut_resa in ("ouvertes", "prioritaire") else "rupture") if reservation else "precommande"
    champs["statut_stock"] = {"value": statut}
    if statut_resa is not None:
        champs["reservation_statut"] = {"value": statut_resa}
    if date_drop is not None:
        champs["date_drop"] = {"value": date_drop}
    champs["fiche_liee"] = {"value": NORMAL if reservation else RESA}
    if reservation:
        champs.setdefault("quantite_max", {"value": 1})
    return {
        "id": 77 if reservation else 42,
        "type": "Réservation garantie" if reservation else "Display",
        "handle": RESA if reservation else NORMAL,
        "url": f"/products/{RESA if reservation else NORMAL}",
        "available": disponible,
        "price": prix if prix is not None else (22990 if reservation else 20990),
        "tags": ["precommande", "reservation-garantie"] if reservation and statut_resa != "fermees" else [],
        "metafields": {"boutique": champs},
    }


def rendre(nom: str, **contexte: Any) -> str:
    sortie = ENV.get_template(nom).render(settings=REGLAGES, **contexte)
    sortie = re.sub(r"<svg.*?</svg>", "", sortie, flags=re.DOTALL)
    return re.sub(r"\s+", " ", sortie).strip()


def badges(product: dict[str, Any]) -> list[str]:
    return re.findall(r'role="listitem">([^<]*)</span>', rendre("da-badges", product=product))


def paire(**kw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    resa = fiche(reservation=True, **kw)
    normale = fiche(reservation=False, statut_resa=kw.get("statut_resa", "ouvertes"), date_drop=kw.get("date_drop", FUTUR))
    return resa, normale


@pytest.mark.parametrize(
    ("product", "attendus"),
    [
        (fiche(langue="FR"), ["FR", "Réservation garantie", "Drop le 20.10"]),
        (fiche(statut_resa="prioritaire"), ["Réservation garantie", "Drop le 20.10"]),
        # Réservations fermées (quota épuisé : inventaire 0) : jamais « Réservation garantie », la date reste.
        (fiche(statut_resa="fermees", disponible=False), ["Rupture", "Drop le 20.10"]),
        (fiche(statut_resa="fermees", statut="precommande"), ["Rupture", "Drop le 20.10"]),
        # Fiche de réservation achetable malgré un statut fermé : le statut du moteur l'emporte sur l'inventaire.
        (fiche(statut_resa="ouvertes", disponible=False), ["Rupture", "Drop le 20.10"]),
        # Drop passé : plus de badge « Drop le ».
        (fiche(date_drop=PASSE), ["Réservation garantie"]),
        # Fiche normale pendant le pré-drop : badge de date, jamais « Réservation garantie ».
        (fiche(reservation=False, statut="precommande"), ["Précommande", "Drop le 20.10"]),
        # Fiche normale en stock local : la date du drop ne s'affiche plus.
        (fiche(reservation=False, statut="stock_local"), ["Stock local"]),
    ],
)
def test_badges_pre_drop(product: dict[str, Any], attendus: list[str]) -> None:
    found = badges(product)
    assert found == attendus
    assert len(found) <= 3 and not ("Stock local" in found and "Réservation garantie" in found)


def test_badge_drop_prime_sur_nouveaute_et_jamais_trois_statuts() -> None:
    p = fiche(langue="FR")
    p["tags"].append("nouveaute")
    assert badges(p) == ["FR", "Réservation garantie", "Drop le 20.10"]


def test_encart_sur_la_fiche_de_reservation_ouverte() -> None:
    resa, normale = paire()
    html = rendre("da-reservation-garantie", product=resa, all_products={NORMAL: normale, RESA: resa})
    assert 'data-reservation="ouvertes"' in html and "Réservations ouvertes." in html
    assert "<dd>20.10.2099</dd>" in html
    assert "CHF 229.90" in html and "CHF 209.90" in html  # prix natifs des deux fiches, jamais en dur
    assert "1 réservation garantie par foyer (toutes commandes confondues)." in html
    assert GARANTIE.replace("'", "&#39;") in html or GARANTIE in html
    assert DIFFERENCE.replace("'", "&#39;") in html or DIFFERENCE in html
    assert f'href="/products/{NORMAL}"' in html and "Voir le produit au prix du drop" in html
    assert "Réserver avec garantie" not in html
    assert not URGENCE.search(re.sub(r"<[^>]+>", " ", html))


def test_encart_fenetre_prioritaire_et_limite_de_deux() -> None:
    resa, normale = paire(statut_resa="prioritaire")
    resa["metafields"]["boutique"]["quantite_max"] = {"value": 2}
    html = rendre("da-reservation-garantie", product=resa, all_products={NORMAL: normale})
    assert "Réservations ouvertes, d&#39;abord aux inscrits aux alertes de ce produit, puis à tous." in html or (
        "Réservations ouvertes, d'abord aux inscrits aux alertes de ce produit, puis à tous." in html
    )
    assert "2 réservations garanties par foyer" in html


def test_encart_sur_la_fiche_normale_renvoie_vers_la_reservation() -> None:
    resa, normale = paire()
    html = rendre("da-reservation-garantie", product=normale, all_products={RESA: resa})
    assert f'href="/products/{RESA}"' in html and "Réserver avec garantie" in html
    assert "CHF 229.90" in html and "CHF 209.90" in html and "1 réservation garantie par foyer" in html


def test_encart_ferme_sur_la_fiche_normale_disparait_mais_reste_sur_la_reservation() -> None:
    resa, normale = paire(statut_resa="fermees")
    assert rendre("da-reservation-garantie", product=normale, all_products={RESA: resa}) == ""
    html = rendre("da-reservation-garantie", product={**resa, "available": False}, all_products={NORMAL: normale})
    assert "Réservations fermées." in html and "Réserver avec garantie" not in html
    assert "Voir le produit au prix du drop" in html


@pytest.mark.parametrize(
    "product",
    [
        fiche(statut_resa=None),  # aucun métachamp de pré-drop
        fiche(date_drop=None),
        fiche(date_drop=PASSE),  # drop passé : plus rien (la fiche de réservation est retirée par le moteur)
        {"id": 1, "type": "Display", "available": True, "price": 100, "tags": [], "metafields": {"boutique": {}}},
    ],
)
def test_encart_absent_sans_pre_drop_a_venir(product: dict[str, Any]) -> None:
    assert rendre("da-reservation-garantie", product=product, all_products={}) == ""


def test_encart_sans_fiche_jumelle_n_invente_aucun_prix() -> None:
    resa = fiche()
    html = rendre("da-reservation-garantie", product=resa, all_products={})
    assert "CHF 229.90" in html and "Au drop" not in html and "href=" not in html


def client(*tags: str, consent: bool = True) -> dict[str, Any]:
    return {"id": 9, "tags": list(tags), "accepts_marketing": consent}


@pytest.mark.parametrize(
    ("product", "customer", "attendu"),
    [
        (fiche(reservation=False), None, "oui"),  # fiche normale : l'inventaire Shopify décide
        (fiche(statut_resa="ouvertes"), None, "oui"),
        (fiche(statut_resa="ouvertes", disponible=False), None, "non"),
        (fiche(statut_resa="fermees"), None, "non"),
        (fiche(statut_resa="fermees"), client(f"alerte-produit:{NORMAL}"), "non"),
        (fiche(statut_resa=None), None, "non"),  # statut inconnu : fermé par défaut
        (fiche(statut_resa="prioritaire"), None, "non"),
        (fiche(statut_resa="prioritaire"), client(f"alerte-produit:{NORMAL}"), "oui"),
        (fiche(statut_resa="prioritaire"), client(f"alerte-produit:{NORMAL}", consent=False), "non"),
        (fiche(statut_resa="prioritaire"), client("alerte-produit:autre-produit"), "non"),
        (fiche(statut_resa="prioritaire"), client("alerte-reassort"), "non"),
        (fiche(statut_resa="prioritaire", disponible=False), client(f"alerte-produit:{NORMAL}"), "non"),
    ],
)
def test_acces_au_bouton_de_reservation(product: dict[str, Any], customer: dict[str, Any] | None, attendu: str) -> None:
    contexte: dict[str, Any] = {"product": product}
    if customer is not None:
        contexte["customer"] = customer
    assert rendre("da-reservation-acces", **contexte) == attendu


@pytest.mark.parametrize(
    ("product", "libelle", "detail"),
    [
        (fiche(), "Réservations ouvertes", "Drop le 20.10.2099 · servie en premier, expédiée dès réception du stock."),
        (fiche(statut_resa="prioritaire"), "Réservations ouvertes aux inscrits aux alertes", "Drop le 20.10.2099"),
        (fiche(statut_resa="fermees", disponible=False), "Réservations fermées", "Drop le 20.10.2099."),
        (fiche(statut_resa="ouvertes", disponible=False), "Réservations fermées", "Drop le 20.10.2099."),
    ],
)
def test_statut_stock_de_la_fiche_de_reservation(product: dict[str, Any], libelle: str, detail: str) -> None:
    html = rendre("da-statut-stock", product=product)
    assert f"<span>{libelle}" in html and detail in html
    assert not re.search(r"\d+ (en stock|unités?|pièces?|places?)", html)


def test_delai_de_la_fiche_de_reservation() -> None:
    html = rendre("da-delai-sortie", product=fiche())
    assert "Réservation garantie : expédiée en premier, dès réception du stock (dans l&#39;ordre des paiements)" in html or (
        "Réservation garantie : expédiée en premier, dès réception du stock (dans l'ordre des paiements)" in html
    )
    assert "<dt>Drop</dt> <dd>20.10.2099</dd>" in html or "<dt>Drop</dt><dd>20.10.2099</dd>" in html
    assert "la réservation garantie est expédiée séparément, dès réception" in html
    assert "Date de sortie" not in html  # la date du drop suffit ; aucune « date non confirmée » ambiguë
    avec_sortie = rendre("da-delai-sortie", product=fiche(date_sortie="2099-10-01", date_sortie_statut="confirmee"))
    assert "01.10.2099 (confirmée)" in avec_sortie
    normale = rendre("da-delai-sortie", product=fiche(reservation=False))
    assert "<dt>Drop</dt>" not in normale and "la précommande est expédiée séparément" in normale
    assert "Date de sortie" in normale and "Non confirmée" in normale
