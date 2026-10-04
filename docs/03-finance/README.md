# 03-finance — modèle financier, trésorerie 13 semaines, vérification du BP

Dossier de l'agent « Finance et pricing » (BP §11, mission 5). Toutes les valeurs sont des **hypothèses du BP du 4 octobre 2026** ou des **exemples FICTIFS**. Aucune n'est un devis, un tarif fournisseur ou une prévision de demande.

## Contenu

| Fichier | Rôle | Qui l'utilise |
|---|---|---|
| `modele_financier.xlsx` | Modèle à formules vivantes : hypothèses, budget initial, charges, scénarios, seuil et sensibilité, prix plancher, stock et BFR | Responsable, fiduciaire, banque |
| `tresorerie_13_semaines.xlsx` | Prévisionnel de trésorerie glissant : mode d'emploi, exemple FICTIF, modèle à remplir | Responsable (chaque lundi) |
| `NOTE_VERIFICATION_BP.md` | Recalcul chiffre par chiffre du BP, écarts, risques | Décision go/no-go |
| `generer_classeurs.py` | Régénère les deux classeurs, les recalcule avec LibreOffice et contrôle l'absence d'erreur | Agent finance / QA |
| `../../engine/pokeshop/forecast.py` | Moteur Python des scénarios, seuils, sensibilité, stock, BFR et vérification du BP | Tableau de bord, API, tests |
| `../../engine/pokeshop/treasury.py` | Moteur Python du prévisionnel 13 semaines (mêmes règles que le classeur) | Tableau de bord, n8n, tests |

## Démarrage rapide

### Modèle financier (`modele_financier.xlsx`)

1. Ouvrir la feuille **Hypothèses**. Ne modifier que les **cellules jaunes à texte bleu**. Le texte noir contient des formules, le vert des liens vers une autre feuille, le gris italique les valeurs publiées dans le BP (références de contrôle).
2. Les feuilles **Budget initial** et **Charges mensuelles** ont leurs propres cellules jaunes. Les totaux alimentent les hypothèses.
3. Lire le résultat dans **Scénarios** (lignes 15 à 25), **Seuil & sensibilité** et **Stock & BFR**. La colonne « Statut » compare automatiquement au BP. Une valeur modifiée fait logiquement apparaître « ÉCART » : c'est voulu.
4. **Prix plancher** : saisir C, r, b, L, R, A, m (et t) d'une référence réelle pour obtenir le plancher, le prix public arrondi et la contribution à un prix testé. Le moteur de production reste `pokeshop.pricing`. Cette feuille sert au contrôle.

### Trésorerie 13 semaines (`tresorerie_13_semaines.xlsx`)

1. Chaque lundi, dupliquer **À remplir** (ou la feuille de la semaine précédente). Saisir la date du lundi (B5) et le **solde bancaire réel** (B6).
2. Saisir les ventes encaissées et le nombre de commandes, les précommandes (**uniquement sur allocation ferme**), les achats **engagés** (commande signée) et **prévus**, TVA, livraisons, remboursements, publicité, charges fixes.
3. Les versements PSP, la réserve précommandes, le disponible pour achats et l'alerte (ligne 49) se calculent seuls.
4. **Règle :** si une semaine est en alerte, les achats « prévus » sont suspendus jusqu'à arbitrage de la responsable.

### Moteur Python

```python
from datetime import date
from decimal import Decimal
from pokeshop import forecast, treasury

forecast.run_bp_scenarios()["central"].rounded()   # 8 788 HT, 1 933, 933…
forecast.break_even(unit_rounding=forecast.CENT)   # 31 commandes (méthode BP)
forecast.verify_against_bp()                        # 38 contrôles, statut par chiffre

plan = treasury.plan_from_weekly_inputs(
    start=date(2026, 10, 5), opening_balance=Decimal("8000"), minimum_reserve=Decimal("500"),
    weeks=[treasury.WeeklyInput(sales_ttc=Decimal("950"), orders=10)],
)
treasury.build_forecast(plan).as_rows()             # lignes prêtes pour le tableau de bord
```

### Régénérer et vérifier

```bash
python docs/03-finance/generer_classeurs.py          # génère, recalcule (LibreOffice), contrôle les erreurs
python -m pytest -q tests/test_forecast.py tests/test_treasury.py
```

Le recalcul exige LibreOffice **avec le module Calc** (paquet `libreoffice-calc`). Avec seulement `libreoffice-core`, la conversion échoue (« source file could not be loaded ») et les tests de classeur sont ignorés (skip).

## Quoi remplacer par des données réelles (avant tout achat significatif)

| Hypothèse actuelle | Où | Source BP | Remplacer par | Responsable |
|---|---|---|---|---|
| Stock 3 000 CHF rendu Suisse | Budget initial B5 | §3 | Devis fournisseur du panier pilote (transport, douane, TVA import) | Sourcing + responsable |
| Site et automatisation 1 500 | Budget initial B6 | §3 | Devis ou abonnements réels (boutique, apps, hébergement) | Site |
| Administration 700, DA 400, emballages 300 | Budget initial B7 à B9 | §3 | Offres fiduciaire et juriste, devis emballage | Responsable |
| Charges fixes 180 / 120 / 100 par mois | Charges mensuelles B4 à B6 | §3 | Tarifs réels ; ajouter les mois sans ventes au budget | Responsable |
| TVA 8,1 %, statut assujetti (méthode effective) | Hypothèses B7 | §4 [S6] | Statut TVA confirmé par la fiduciaire (toute l'entité) | Fiduciaire |
| Panier 95 TTC, contribution 22 %, coût produit 70 % | Hypothèses B9, B11, B14 | §10 | Mesures des 30 premières commandes, marges réelles par facture | Finance |
| Commandes 40 / 100 / 200, CAC 8 / 6 / 5 | Hypothèses B27 à D28 | §10 | Résultats du test publicité (jours 46 à 60) | Acquisition |
| Frais PSP 2,5 % + 0,30 | Prix plancher B8-B9 ; trésorerie B8-B9 | §4 | Contrat PSP (carte, TWINT) | Responsable |
| Délai de versement PSP 7 jours | Hypothèses B40 ; trésorerie B10 | — (FICTIF) | Délai constaté lors des paiements tests | Site |
| Prépaiement fournisseur 14 j, stock 30 j, crédit 0 j | Hypothèses B37 à B39 | — (FICTIF) | Conditions de paiement et délais réels du fournisseur | Sourcing |
| Préparation 15 min/colis | Hypothèses B22 | — (FICTIF) | Temps mesuré lors des commandes tests | Opérations |
| Réserve minimale 500 CHF (exemple) | Trésorerie B7 | — (FICTIF) | Décision de la responsable | Responsable |
| Pas d'arrondi 10 CHF, terminaison 9,90 | Prix plancher B19-B20 | §4 (ambigu) | Règle d'arrondi validée, par tranche de prix | Responsable |

## Limites connues

- Le BFR ne compte ni la TVA collectée conservée jusqu'au décompte (ressource) ni la TVA d'import préfinancée (emploi). Choix prudent, à affiner avec la fiduciaire.
- Le classeur 13 semaines date chaque flux du lundi de sa semaine et décale les versements PSP de semaines entières. Le moteur Python accepte des dates et des délais au jour près.
- Les scénarios supposent une entité assujettie (BP §10). Pour simuler une entité non assujettie : `ScenarioAssumptions(vat_rate=Decimal(0), contribution_rate=<taux recalculé avec la TVA d'achat dans le coût>)`.
- `forecast.floor_price_crosscheck` est une **contre-vérification indépendante** de la formule du BP §4. Elle ne remplace pas `pokeshop.pricing`.

## Validation humaine requise

- [ ] Remplacer chaque hypothèse du tableau ci-dessus par un devis, un contrat ou une mesure, puis relancer `generer_classeurs.py`.
- [ ] Fixer la réserve minimale de trésorerie et la règle d'arbitrage en cas d'alerte.
- [ ] Faire confirmer par la fiduciaire le statut TVA, la méthode et l'échéancier des décomptes.
- [ ] Valider la règle d'arrondi du prix public (voir `NOTE_VERIFICATION_BP.md` §4.4).
- [ ] Décider du financement du besoin en fonds de roulement avant de viser le scénario central.
