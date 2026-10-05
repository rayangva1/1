"""Couverture du relevé de prix marché : aucune référence achetée sans relevé prévu (BP §1, §5).

BP §1 : « N'acheter que les références dont le prix rentable reste compatible avec le marché observé ».
Chaque référence STOCK du panier pilote doit donc avoir ses lignes de relevé dans la grille concurrence
(au moins 3 boutiques, pour qu'une médiane existe) ; sinon 30 % du budget reposait sur la seule
validation de repli (revue CON-04 : REF-16, REF-17, REF-19, REF-20 absentes de la grille).
Lancer : ``python -m pytest -q docs/02-sourcing/outils``.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GRILLE = REPO / "docs" / "01-marche" / "GRILLE_CONCURRENCE.csv"
PANIER = REPO / "docs" / "02-sourcing" / "PANIER_PILOTE.csv"
ASSORTIMENT = REPO / "docs" / "01-marche" / "ASSORTIMENT_PILOTE.md"
MIN_LIGNES = 3
# « Alternative à REF-04 », « remplace REF-04 », « (ou REF-05 selon la marge) » : une substitution d'achat.
ALTERNATIVE_RE = re.compile(r"(?i)(?:alternative à|remplace|en remplacement de|\(ou)\s+(REF-\d{2})")


def _lire(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def references_stock_sans_releve(grille: list[dict[str, str]], panier: list[dict[str, str]]) -> list[str]:
    """Références STOCK du panier qui ont moins de MIN_LIGNES lignes de relevé dans la grille."""
    lignes = Counter(r["ref_id"] for r in grille)
    return sorted(r["ref_id"] for r in panier if r["statut_vise"] == "STOCK" and lignes[r["ref_id"]] < MIN_LIGNES)


def alternatives_sans_releve(
    grille: list[dict[str, str]], panier: list[dict[str, str]], assortiment: str = ""
) -> list[str]:
    """Substitutions d'achat déclarées sans relevé marché (revue CON-04, round 2).

    Une référence déclarée comme alternative d'une référence STOCK (colonne ``remarque`` du panier : « Alternative
    à REF-04 » ; ou désignation de l'assortiment : « REF-04 … (ou REF-05 selon la marge) ») peut être achetée à sa
    place : elle doit donc avoir, elle aussi, au moins MIN_LIGNES lignes de relevé dans la grille.
    """
    lignes = Counter(r["ref_id"] for r in grille)
    stock = {r["ref_id"] for r in panier if r["statut_vise"] == "STOCK"}
    problemes: set[str] = set()
    for r in panier:
        for cible in ALTERNATIVE_RE.findall(r.get("remarque", "")):
            if cible in stock and lignes[r["ref_id"]] < MIN_LIGNES:
                problemes.add(f"{r['ref_id']} (alternative à {cible})")
    for ligne in assortiment.splitlines():
        match = re.match(r"^\| (REF-\d{2}) \|", ligne)
        if not match or match.group(1) not in stock:
            continue
        for alternative in ALTERNATIVE_RE.findall(ligne):
            if alternative != match.group(1) and lignes[alternative] < MIN_LIGNES:
                problemes.add(f"{alternative} (alternative à {match.group(1)})")
    return sorted(problemes)


def test_chaque_reference_stock_a_un_releve_marche_prevu() -> None:
    assert references_stock_sans_releve(_lire(GRILLE), _lire(PANIER)) == []


def test_aucune_alternative_d_achat_sans_releve() -> None:
    texte = ASSORTIMENT.read_text(encoding="utf-8")
    assert alternatives_sans_releve(_lire(GRILLE), _lire(PANIER), texte) == []


def test_controle_detecte_une_alternative_sans_releve() -> None:
    panier = [
        {"ref_id": "REF-04", "statut_vise": "STOCK", "remarque": ""},
        {"ref_id": "REF-05", "statut_vise": "ALERTE", "remarque": "Alternative à REF-04"},
    ]
    grille = [{"ref_id": "REF-04"}] * 5
    assert alternatives_sans_releve(grille, panier) == ["REF-05 (alternative à REF-04)"]
    texte = "| REF-04 | Coffret Nymphali-ex – FR (ou REF-05 selon la marge) | Coffrets | E1 | STOCK | 250 | A |"
    panier[1]["remarque"] = ""
    assert alternatives_sans_releve(grille, panier, texte) == ["REF-05 (alternative à REF-04)"]
    assert alternatives_sans_releve(grille + [{"ref_id": "REF-05"}] * 3, panier, texte) == []


def test_grille_reste_dans_la_fourchette_du_bp() -> None:
    grille = _lire(GRILLE)
    refs = {r["ref_id"] for r in grille}
    assert 10 <= len(refs) <= 15  # BP §1 : 10 à 15 références identiques
    assert all(n == 5 for n in Counter(r["ref_id"] for r in grille).values())  # 5 boutiques par référence


def test_controle_detecte_une_reference_stock_sans_releve() -> None:
    panier = [{"ref_id": "REF-16", "statut_vise": "STOCK"}, {"ref_id": "REF-03", "statut_vise": "ALERTE"}]
    grille = [{"ref_id": "REF-03"}] * 5
    assert references_stock_sans_releve(grille, panier) == ["REF-16"]
