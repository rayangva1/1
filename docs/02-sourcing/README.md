# 02-sourcing — dossier B2B, demandes fournisseurs, comparaison

BP §2 et §13 « La première action concrète » : préparer un dossier commun, demander à trois fournisseurs FR **le même panier pilote** avec un **exemple de fichier prix/stock**, puis comparer le coût rendu en Suisse. **Aucun contact n'a été pris, aucun compte ouvert, aucun prix réel saisi.**

## Contenu

| Fichier | Rôle | Tâches |
|---|---|---|
| `DOSSIER_B2B.md` | Présentation de l'entreprise à compléter (`{{…}}`) + notes internes + brief fiduciaire | BL-035 à BL-037 |
| `EMAILS_FOURNISSEURS.md` | Un email par fournisseur du BP (Asmodee France, Matoo et Miao, TCG Distribution, OtakuWorld, CardCosmos), relances J+5 et J+12, piste Carletto hors BP | BL-040 à BL-044 |
| `PANIER_PILOTE.csv` | 20 références, même liste pour tous les fournisseurs ; quantités indicatives pour devis | BL-038, BL-039 |
| `COMPARATEUR_OFFRES.xlsx` | Coût rendu CHF par offre (formules BP §4), prix plancher, écart au marché, classement ; 2 lignes FICTIF | BL-048, BL-050 |
| `TRACKER_CONTACTS.csv` | 24 interlocuteurs (fournisseurs, fiduciaire, banque/PSP, transporteur, logisticien, juriste, assurance, créateurs, administrations), tous « non contacté » | BL-021, BL-044 |
| `CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md` | Distribution FR, export Suisse, authenticité, allocations, flux (« un portail n'est pas une API »), score sur 72 | BL-046, BL-047 |
| `outils/generer_comparateur.py` | Régénère et recalcule le comparateur (LibreOffice) | — |

## Régénérer et vérifier le comparateur

```bash
python docs/02-sourcing/outils/generer_comparateur.py      # génère, recalcule, contrôle l'absence d'erreur
python -m pytest -q docs/02-sourcing/outils                # 22 tests, dont l'égalité avec pokeshop.pricing
```

Les paramètres r, b, L, R, A, m et t sont lus dans `config/pricing_rules.v1.yaml` : une seule source. Les tests vérifient que le coût rendu, le prix plancher et la contribution calculés par le classeur sont égaux à ceux du moteur `pokeshop.pricing`, dans les deux modes TVA (EFFECTIVE et NOT_REGISTERED).

## Validation humaine requise

- [ ] Compléter et valider le dossier B2B, les emails et le panier (C02) avant le premier envoi.
- [ ] Créer les comptes revendeurs et transmettre les pièces KYC (B11) : les agents ne le font pas.
- [ ] Autoriser chaque fournisseur retenu dans le mandat, après la due diligence (C08).
