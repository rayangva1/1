"""Couverture du relevé de prix marché : aucune référence achetée sans relevé prévu (BP §1, §5).

BP §1 : « N'acheter que les références dont le prix rentable reste compatible avec le marché observé ».
Chaque référence STOCK du panier pilote doit donc avoir ses lignes de relevé dans la grille concurrence
(au moins 3 boutiques, pour qu'une médiane existe) ; sinon 30 % du budget reposait sur la seule
validation de repli (revue CON-04 : REF-16, REF-17, REF-19, REF-20 absentes de la grille).
Lancer : ``python -m pytest -q docs/02-sourcing/outils``.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GRILLE = REPO / "docs" / "01-marche" / "GRILLE_CONCURRENCE.csv"
PANIER = REPO / "docs" / "02-sourcing" / "PANIER_PILOTE.csv"
MIN_LIGNES = 3


def _lire(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def references_stock_sans_releve(grille: list[dict[str, str]], panier: list[dict[str, str]]) -> list[str]:
    """Références STOCK du panier qui ont moins de MIN_LIGNES lignes de relevé dans la grille."""
    lignes = Counter(r["ref_id"] for r in grille)
    return sorted(r["ref_id"] for r in panier if r["statut_vise"] == "STOCK" and lignes[r["ref_id"]] < MIN_LIGNES)


def test_chaque_reference_stock_a_un_releve_marche_prevu() -> None:
    assert references_stock_sans_releve(_lire(GRILLE), _lire(PANIER)) == []


def test_grille_reste_dans_la_fourchette_du_bp() -> None:
    grille = _lire(GRILLE)
    refs = {r["ref_id"] for r in grille}
    assert 10 <= len(refs) <= 15  # BP §1 : 10 à 15 références identiques
    assert all(n == 5 for n in Counter(r["ref_id"] for r in grille).values())  # 5 boutiques par référence


def test_controle_detecte_une_reference_stock_sans_releve() -> None:
    panier = [{"ref_id": "REF-16", "statut_vise": "STOCK"}, {"ref_id": "REF-03", "statut_vise": "ALERTE"}]
    grille = [{"ref_id": "REF-03"}] * 5
    assert references_stock_sans_releve(grille, panier) == ["REF-16"]
