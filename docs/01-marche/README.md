# 01-marche — validation du marché avant de commander

BP §1 « Validation avant de commander » : concurrence, entretiens, page de présentation, assortiment pilote. Toutes les recherches web du build ont été faites **le 4.10.2026 via index de recherche** : l'accès direct aux sites était bloqué par le proxy de l'environnement (écart EC-05). Aucun prix n'a été relevé.

## Contenu

| Fichier | Rôle | Tâches |
|---|---|---|
| `PROTOCOLE_CONCURRENCE.md` | 5 boutiques suisses (+ 3 remplaçants), 15 références, procédure de relevé, calcul de la référence marché | BL-020 à BL-022 |
| `GRILLE_CONCURRENCE.csv` | 75 lignes (15 × 5) pré-structurées, dont les 12 références STOCK du panier pilote ; prix vides tant qu'ils n'ont pas été lus sur la page (relevé à faire avant tout achat) | BL-020 |
| `GUIDE_ENTRETIENS.md` | Script de 20-25 min, consentement, 23 questions, grille de synthèse | BL-024 à BL-027 |
| `QUESTIONNAIRE.md` | Version formulaire en ligne (mêmes codes de questions) | BL-023 |
| `PROTOCOLE_LANDING_TEST.md` | Page de présentation sans faux stock ni précommande ; KPI et seuils de signal | BL-031 à BL-034 |
| `ASSORTIMENT_PILOTE.md` | Calendrier des sorties FR, enveloppes budget × extension (plafond 750 CHF), 20 références dont 12 en stock | BL-039, BL-107 |

Les identifiants de références (`REF-01` à `REF-20`) sont communs à la grille, à l'assortiment, au panier fournisseur et au comparateur.

## Validation humaine requise

- [ ] Désigner qui fait le relevé de prix si aucun agent n'a d'accès web (≈ 4 à 5 h).
- [ ] Valider l'assortiment (enveloppes et liste en STOCK) au gate G3.
