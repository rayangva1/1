# 03-finance — modèle financier, étoile polaire, trésorerie 13 semaines, vérification du BP

Dossier de l'agent « Finance et pricing » (BP §11, mission 5). Toutes les valeurs sont des **hypothèses du BP du 4 octobre 2026** ou des **exemples FICTIFS**. Aucune n'est un devis, un tarif fournisseur ou une prévision de demande.

**Métrique unique de pilotage (étoile polaire) :** la contribution nette cumulée = ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes. Ni le chiffre d'affaires ni les followers ne servent de critère.

## Contenu

| Fichier | Rôle | Qui l'utilise |
|---|---|---|
| `modele_financier.xlsx` | Modèle à formules vivantes : hypothèses, **étoile polaire** (suivi hebdomadaire projeté et réel, stop-loss global), budget initial, charges, scénarios, seuil et sensibilité, prix plancher, stock et BFR | Propriétaire, agents, fiduciaire, banque |
| `tresorerie_13_semaines.xlsx` | Prévisionnel de trésorerie glissant : mode d'emploi, exemple FICTIF, modèle à remplir. Réserve de 1 600 CHF = **seuil du stop-loss cash** | Agent finance (chaque lundi), propriétaire |
| `NOTE_VERIFICATION_BP.md` | Recalcul chiffre par chiffre du BP, étoile polaire et stop-loss, écarts, risques | Décision go/no-go |
| `generer_classeurs.py` | Régénère les deux classeurs, les recalcule avec LibreOffice et contrôle l'absence d'erreur | Agent finance / QA |
| `../../engine/pokeshop/forecast.py` | Moteur Python : scénarios, seuils, sensibilité, stock, BFR, étoile polaire, vérification du BP | Tableau de bord, API, tests |
| `../../engine/pokeshop/treasury.py` | Moteur Python du prévisionnel 13 semaines et du stop-loss cash (mêmes règles que le classeur) | Tableau de bord, n8n, tests |

## Démarrage rapide

### Modèle financier (`modele_financier.xlsx`)

1. Ouvrir la feuille **Hypothèses**. Ne modifier que les **cellules jaunes à texte bleu**. Le texte noir contient des formules, le vert des liens vers une autre feuille, le gris italique les valeurs publiées dans le BP (références de contrôle).
2. Les feuilles **Budget initial** et **Charges mensuelles** ont leurs propres cellules jaunes. Les totaux alimentent les hypothèses.
3. Lire le résultat dans **Scénarios** (lignes 15 à 26), **Seuil & sensibilité** et **Stock & BFR**. La colonne « Statut » compare automatiquement au BP. Une valeur modifiée fait logiquement apparaître « ÉCART » : c'est voulu.
4. **Prix plancher** : saisir C, r, b, L, R, A, m (et t) d'une référence réelle pour obtenir le plancher, le prix public arrondi et la contribution à un prix testé. Le moteur de production reste `pokeshop.pricing`. Cette feuille sert au contrôle.

### Étoile polaire (feuille du modèle financier)

1. Choisir le scénario projeté en `Hypothèses!B49` (1 prudent, 2 central, 3 développement) et la semaine d'ouverture des ventes en `B48` (5 par défaut, BP §9).
2. Chaque lundi, saisir le **réel de la semaine écoulée** dans les colonnes jaunes **M à T** (commandes payées, ventes nettes HT, coût historique, paiement, logistique, SAV, acquisition, charges fixes ; montants HT en CHF, coûts en positif). Une semaine non saisie reste vide.
3. Lire le **cumul réel** (colonne W) et la **synthèse** (lignes 18 à 28) : cumul à date, creux, retour au positif, jalons BP §1 (30 commandes et contribution positive après publicité sur 8 semaines pleines).
4. **Stop-loss global** : dès que le cumul réel atteint −1 600 CHF (20 % du capital engagé de 8 000), la colonne Y affiche « GEL GLOBAL » et le reste jusqu'au réarmement par la propriétaire. Le tableau des lignes 31 à 37 rappelle les six stop-loss du mandat et leurs seuils.

### Trésorerie 13 semaines (`tresorerie_13_semaines.xlsx`)

1. Chaque lundi, dupliquer **À remplir** (ou la feuille de la semaine précédente). Saisir la date du lundi (B5) et le **solde bancaire réel** (B6). La réserve B7 est préremplie à **1 600 CHF** : seule la propriétaire peut la changer.
2. Saisir les ventes encaissées et le nombre de commandes, les précommandes (**uniquement sur allocation ferme**), les achats **engagés** (commande signée) et **prévus**, TVA, livraisons, remboursements, publicité, charges fixes.
3. Les versements PSP, la réserve précommandes, le disponible pour achats et l'alerte de clôture (ligne 49) se calculent seuls.
4. **Stop-loss cash (lignes 50-51)** : une semaine qui s'ouvre avec un cash disponible (solde − précommandes) sous 1 600 CHF interdit tout achat prévu et toute publicité. La ligne 51 donne les montants à supprimer ou à décaler. Les achats déjà engagés restent dus.

### Moteur Python

```python
from datetime import date
from decimal import Decimal
from pokeshop import forecast, treasury

forecast.run_bp_scenarios()["central"].rounded()   # 8 788 HT, 1 933, 933…
forecast.break_even(unit_rounding=forecast.CENT)   # 31 commandes (méthode BP)
forecast.verify_against_bp()                        # 38 contrôles, statut par chiffre

# Étoile polaire : projection d'un scénario, puis suivi du réel
central = forecast.bp_scenarios()[1]
projection = forecast.north_star(forecast.project_north_star(central, opening_week=5))
projection.recovery_week                            # 6 : cumul redevenu positif
week1 = forecast.NorthStarWeek(1, Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0),
                               Decimal(0), Decimal(0), Decimal("400"))
report = forecast.north_star([week1])               # cumul −400 ; report.frozen = gel global ?

# Trésorerie 13 semaines avec stop-loss cash (réserve 1 600 CHF par défaut)
plan = treasury.plan_from_weekly_inputs(
    start=date(2026, 10, 5), opening_balance=Decimal("8000"),
    weeks=[treasury.WeeklyInput(sales_ttc=Decimal("950"), orders=10)],
    enforce_cash_stoploss=True,                     # simule le blocage achats prévus + pub
)
result = treasury.build_forecast(plan)
result.cash_stoploss_weeks, result.blocked_outflows_total
result.as_rows()                                    # lignes prêtes pour le tableau de bord
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
| Stock 3 000 CHF rendu Suisse | Budget initial B5 | §3 | Devis fournisseur du panier pilote (transport, douane, TVA import) | Sourcing + propriétaire |
| Site et automatisation 1 500 | Budget initial B6 | §3 | Devis ou abonnements réels (boutique, apps, hébergement) | Site |
| DA 400, administration 700, emballages 300 | Budget initial B7 à B9 | §3 | Offres fiduciaire et juriste, devis emballage | Propriétaire |
| Charges fixes 180 / 120 / 100 par mois | Charges mensuelles B4 à B6 | §3 | Tarifs réels ; ajouter les mois sans ventes au budget | Propriétaire |
| TVA 8,1 %, statut assujetti (méthode effective) | Hypothèses B7 | §4 [S6] | Statut TVA confirmé par la fiduciaire (toute l'entité) | Fiduciaire |
| Panier 95 TTC, contribution 22 %, coût produit 70 % | Hypothèses B9, B11, B14 | §10 | Mesures des 30 premières commandes, marges réelles par facture | Finance |
| Commandes 40 / 100 / 200, CAC 8 / 6 / 5 | Hypothèses B27 à D28 | §10 | Résultats du test publicité (jours 46 à 60) | Acquisition |
| Frais PSP 2,5 % + 0,30 | Hypothèses B50-B51 ; Prix plancher B8-B9 ; trésorerie B8-B9 | §4 | Contrat PSP (carte, TWINT) | Propriétaire |
| Provision SAV 1 CHF/commande | Hypothèses B52 ; Prix plancher B11 | §4 | Coût SAV constaté (retours, casse) | Opérations |
| Délai de versement PSP 7 jours | Hypothèses B40 ; trésorerie B10 | — (FICTIF) | Délai constaté lors des paiements tests | Site |
| Prépaiement fournisseur 14 j, stock 30 j, crédit 0 j | Hypothèses B37 à B39 | — (FICTIF) | Conditions de paiement et délais réels du fournisseur | Sourcing |
| Préparation 15 min/colis | Hypothèses B22 | — (FICTIF) | Temps mesuré lors des commandes tests | Opérations |
| Capital engagé 8 000 CHF (base du stop-loss global) | Hypothèses B44 | §3 | Capital réellement engagé, validé par la propriétaire | Propriétaire |
| Ouverture des ventes en semaine 5 | Hypothèses B48 | §9 | Date réelle de l'ouverture douce | Chef de projet |
| Réserve 1 600 CHF = stop-loss cash | Budget initial B11 ; trésorerie B7 | §3 + mandat | Décision de la propriétaire uniquement | Propriétaire |
| Pas d'arrondi 10 CHF, terminaison 9,90 | Prix plancher B19-B20 | §4 (ambigu) | Règle d'arrondi validée, par tranche de prix | Propriétaire |

## Limites connues

- Le BFR ne compte ni la TVA collectée conservée jusqu'au décompte (ressource) ni la TVA d'import préfinancée (emploi). Choix prudent, à affiner avec la fiduciaire.
- Le classeur 13 semaines date chaque flux du lundi de sa semaine et décale les versements PSP de semaines entières. Le moteur Python accepte des dates et des délais au jour près.
- Le stop-loss cash est évalué en début de semaine sur la clôture précédente. Une dépense prévue qui fait passer sous le seuil en cours de semaine apparaît en alerte de clôture et bloque la semaine suivante. `pokeshop.stoploss` (agent gouvernance) fait foi pour l'application réelle, au jour près.
- La projection de l'étoile polaire ventile les 78 % de coûts variables du BP (coût produit 70 %, paiement, SAV, emballage implicite 3,36 CHF/commande). Le réel doit venir du coût historique par lot (`pokeshop.costs`) et des factures, pas de cette ventilation.
- La fenêtre de validation (60 jours, BP §1) est ramenée à 8 semaines pleines (56 jours) : plus exigeant que le BP, donc prudent.
- Les scénarios supposent une entité assujettie (BP §10). Pour simuler une entité non assujettie : `ScenarioAssumptions(vat_rate=Decimal(0), contribution_rate=<taux recalculé avec la TVA d'achat dans le coût>)`.
- `forecast.floor_price_crosscheck` est une **contre-vérification indépendante** de la formule du BP §4. Elle ne remplace pas `pokeshop.pricing`.

## Validation humaine requise

- [ ] Remplacer chaque hypothèse du tableau ci-dessus par un devis, un contrat ou une mesure, puis relancer `generer_classeurs.py`.
- [ ] Confirmer la base du stop-loss global : contribution nette cumulée (hors dépenses de lancement) et capital engagé de 8 000 CHF, soit un gel à −1 600 CHF.
- [ ] Confirmer le seuil du stop-loss cash (1 600 CHF) et décider du financement des charges fixes d'avant l'ouverture, qui l'entament sinon dès la semaine 5.
- [ ] Faire confirmer par la fiduciaire le statut TVA, la méthode et l'échéancier des décomptes.
- [ ] Valider la règle d'arrondi du prix public (voir `NOTE_VERIFICATION_BP.md` §4.4).
- [ ] Décider du financement du besoin en fonds de roulement avant de viser le scénario central.
