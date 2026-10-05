# Étoile polaire — contribution nette cumulée — {{NOM_BOUTIQUE}}

> Décision de la propriétaire (4.10.2026) : **gagner de l'argent avec les cartes Pokémon**. Une seule métrique pilote tout le projet.
> Calcul : `engine/pokeshop/northstar.py` (réalisé). Projection : `pokeshop.forecast.north_star` (agent finance). Stop-loss : `docs/00-pilotage/STOP_LOSS.md`.

## 1. Définition

**Contribution nette cumulée** = somme, depuis le lancement, de :

```
ventes nettes HT
− coût historique des unités vendues
− frais de paiement
− logistique
− SAV
− acquisition
− charges fixes
```

Elle répond à une seule question : **l'activité a-t-elle, à date, rapporté plus qu'elle n'a coûté ?** Elle se lit chaque semaine, en niveau (cumul) et en tendance (delta d'une semaine sur l'autre).

## 2. Chaque poste, sa source, son piège

| Poste | Ce qu'on compte | Source dans le système | Piège évité |
|---|---|---|---|
| Ventes nettes HT | Montant payé (produits + port facturé) − remises, hors TVA (TTC si l'entité n'est pas assujettie) ; remboursements en négatif | `record_order` / `record_basket`, `record_refund` | Une **précommande encaissée** n'est pas une vente tant qu'elle n'est pas livrée : c'est du cash, pas de la contribution |
| Coût historique | Coût rendu des unités vendues au CMP, retours remis en stock déduits (au coût de la vente d'origine), casse, écart de facture sur unités déjà vendues | **Uniquement** le registre de coûts interne du moteur : `POST /costs/movements` (réception d'un lot au coût rendu, vente, retour, casse, facture) → `HistoricalCostLedger` → `sync_cost_ledger`. Une sortie n'a **jamais** de coût déclaré : le moteur la sort au CMP. `POST /northstar/entries` (et `NorthStarLedger.record` / `add_entries`) **refuse** tout coût historique et toute source `HistoricalCostLedger` : l'étiquette n'est pas déclarable | Jamais le **coût de remplacement** : une offre moins chère ne change pas le coût des unités déjà achetées (BP §4) ; jamais un « avoir » inventé |
| Paiement | Frais PSP réels (r × montant + b), frais remboursés seulement s'ils le sont vraiment | Commande, remboursement, abonnement PSP | — |
| Logistique | Préparation, emballage, port réel des commandes | Commande ou dépense | Le port facturé n'est pas une marge (BP §3) : il est dans les ventes, le port réel ici |
| SAV | Dépenses réelles : port retour, geste commercial, remplacement | `record_expense(…, Post.AFTER_SALES, …)` | La provision R du moteur de prix sert à fixer les prix, pas à remplir ce poste (sinon double compte) |
| Acquisition | Publicité réellement dépensée, créateurs (produits offerts et commissions compris, BP §9) | `record_expense(…, Post.ACQUISITION, …)` | Le CAC attribué A du moteur de prix est une hypothèse, pas une dépense |
| Charges fixes | Site, apps, comptabilité, assurance, stockage (400 CHF/mois au BP §3) | `accrue_fixed_costs` (réparti au jour, somme exacte au centime) | Les compter dès la semaine 1, même sans vente |

Montants au centime exact (un montant à 3 décimales est refusé), écritures idempotentes (aucun double comptage si un import est rejoué), semaines du lundi au dimanche, fuseau Europe/Zurich. Un lot d'écritures (`POST /northstar/entries`) est **atomique** : une écriture refusée et rien n'est enregistré ; chaque lot accepté est journalisé avec l'acteur déduit du jeton.

## 3. Exemple chiffré (FICTIF, calculé à la main et vérifié par les tests)

Produits FICTIFS : un display (coût historique 140,00 CHF) et un ETB (60,00 CHF). Ventes nettes HT de l'exemple BP §4 : display 199,90 TTC ⇒ 184,92 HT ; ETB 95,00 TTC ⇒ 87,88 HT. Charges fixes : 400 × 12 / 52 = 92,31 CHF par semaine.

**Semaine 2026-W45** : commandes A (display) et B (ETB) ; 20,00 CHF de publicité.

| Poste | Calcul | CHF |
|---|---|---:|
| Ventes nettes HT | 184,92 + 87,88 | 272,80 |
| Coût historique | 140,00 + 60,00 | − 200,00 |
| Paiement | 5,30 + 2,68 | − 7,98 |
| Logistique | 3,00 + 3,00 | − 6,00 |
| SAV | — | 0,00 |
| Acquisition | publicité | − 20,00 |
| Charges fixes | 400 × 12 / 52 | − 92,31 |
| **Contribution nette** | | **− 53,49** |

**Semaine 2026-W46** : commandes C (display), D et E (ETB) ; remboursement de B avec retour en stock et 7,00 CHF de port retour ; 35,00 CHF de publicité.

| Poste | Calcul | CHF |
|---|---|---:|
| Ventes nettes HT | 184,92 + 87,88 + 87,88 − 87,88 | 272,80 |
| Coût historique | 140,00 + 60,00 + 60,00 − 60,00 | − 200,00 |
| Paiement | 5,30 + 2,68 + 2,68 (non remboursés) | − 10,66 |
| Logistique | 3 × 3,00 | − 9,00 |
| SAV | port retour | − 7,00 |
| Acquisition | publicité | − 35,00 |
| Charges fixes | | − 92,31 |
| **Contribution nette** | | **− 81,17** |

| Semaine | Contribution nette | Delta vs semaine précédente | **Cumul** |
|---|---:|---:|---:|
| 2026-W45 | − 53,49 | − 53,49 | **− 53,49** |
| 2026-W46 | − 81,17 | − 27,68 | **− 134,66** |

Lecture : la contribution **avant charges fixes** est positive en W46 (11,14 CHF après publicité), mais trop faible pour couvrir 92,31 CHF de charges fixes. Au rythme de 3 commandes par semaine, l'activité perd de l'argent ; il faut plus de volume à marge égale, ou moins de publicité par commande. Le delta de − 27,68 s'explique poste par poste : + 2,68 de paiement, + 3,00 de logistique, + 7,00 de SAV, + 15,00 de publicité, ventes et coût inchangés.

## 4. Revue hebdomadaire (lundi, 15 minutes)

**Préparée par l'agent 05, lue par la propriétaire.**

1. Vérifier que le registre de coûts interne a reçu les mouvements de la semaine close (`POST /costs/movements` : réceptions au coût rendu, ventes, retours, casse, factures ; le moteur synchronise lui-même le coût des ventes), puis les commandes, remboursements et dépenses (`POST /northstar/entries`, sans coût historique). Une commande n'entre qu'avec sa **logistique réelle** (coût transporteur) : jamais l'hypothèse L du BP.
2. Produire le tableau : `NorthStarLedger.weekly_report(...).render_markdown()`.
3. Répondre par écrit aux quatre questions :

| Question | Où regarder |
|---|---|
| Le cumul monte-t-il ? | Colonne « Cumul », tendance sur 4 semaines |
| Quel poste explique le delta ? | `delta_by_post` (écart poste par poste) |
| La publicité paie-t-elle ? | Contribution après acquisition > 0 ; stop-loss publicité |
| Le rythme couvre-t-il les charges fixes ? | Contribution avant charges fixes vs 92,31 CHF par semaine |

4. Décider une seule action pour la semaine (prix, assortiment, publicité, réassort), avec son effet attendu en CHF sur la contribution nette.

**Gabarit à coller dans le rapport de l'agent 05 :**

```
Semaine : AAAA-Wss | Contribution nette : … CHF | Delta : … CHF | Cumul : … CHF
Poste principal du delta : …
Contribution après pub : … CHF | Contribution avant charges fixes : … CHF
Stop-loss actifs : …
Action décidée : … | Effet attendu : … CHF/semaine | Revue : semaine suivante
```

## 5. Ce qui ne compte pas

| Indicateur | Pourquoi il ne pilote pas |
|---|---|
| Chiffre d'affaires | Une vente à perte augmente le CA et diminue l'étoile polaire |
| Followers, vues, inscrits | Le BP §9 : la première validation est un achat rentable et livré, pas une audience |
| Stock « valorisé » au prix public ou à la cote | Un stock invendu immobilise du cash ; seul l'écoulement à marge compte |
| Coût de remplacement | Sert à fixer les prix futurs, jamais à calculer la marge réalisée |
| Provisions du moteur de prix (R, A) | Hypothèses de calcul ; ici seules les dépenses réelles comptent |
| Précommandes encaissées non livrées | Du cash à rendre si l'allocation échoue, pas une vente |
| Allocations rares obtenues | Un produit rare à faible marge n'est pas un motif d'achat (BP §1) |

## 6. Liens avec les stop-loss et les gates

- **Stop-loss temps** : il utilise la contribution **après publicité, avant charges fixes**, sur la fenêtre de validation (`NorthStarLedger.totals(début, fin).contribution_after_acquisition`), avec le seuil « > 0 » du BP §1.
- **Stop-loss global** (définition unique : `docs/00-pilotage/STOP_LOSS.md` §3) : il ne se calcule **pas** sur la contribution cumulée mais sur la **valeur nette** (cash + stock prudent + créances − dettes) comparée au capital engagé de référence, parce que le stock acheté et non vendu est une perte potentielle que la contribution ne voit pas encore. Gel si la perte atteint 20 % de la référence : **840 CHF** avec le point zéro recommandé (option A, 4 200 CHF : décidé à J3 avec la décision de budget C03, posé dès la mise en service de l'API après vos apports et une première photo acceptée, `STOP_LOSS.md` §5). La projection de l'agent finance (`pokeshop.forecast.north_star`) et le classeur `docs/03-finance/modele_financier.xlsx` n'en sont qu'une approximation, qui exclut les coûts de lancement : ils appliquent **par défaut** `capital_engaged=BP_STOPLOSS_REFERENCE` (4 200 CHF ⇒ seuil 840 CHF ; gel projeté en semaine 13 au rythme du jalon). Un seuil « −1 600 CHF de contribution cumulée » n'est pas le stop-loss du projet. Les apports et retraits qui fixent la référence viennent **uniquement** de votre registre (`POST /capital/movements`).
- **Journal illisible** : si le journal de l'étoile polaire n'a pas pu être relu au démarrage, `GET /northstar` répond 503 et le tableau de bord (`GET /dashboard/*`) affiche l'étoile polaire « indisponible (journal non relu) », statut CRITIQUE, **jamais** « aucune écriture » ni un cumul à 0 ; réparer le stockage puis redémarrer.
- **Plan vs réalisé** : `NorthStarReport.to_forecast_weeks()` convertit le réalisé au format de la projection pour comparer semaine par semaine.

```python
from decimal import Decimal
from pokeshop.northstar import CostMovement, CostRegister, NorthStarLedger, Post

ledger = NorthStarLedger()
costs = CostRegister(ledger)                                 # registre de coûts interne (seule source du coût)
ledger.record_basket("CMD-0001", paid_at, basket)          # ventes, paiement, logistique RÉELLE
# basket = pricing.basket_contribution(..., shipping_cost_actual=coût_transporteur) : un panier calculé sur
# l'hypothèse L ou un port offert sans coût réel (SHIPPING_COST_ASSUMED / _UNKNOWN) est refusé (NorthStarError).
costs.apply(CostMovement(kind="RECEIPT", product_key="P1", at=received_at, ref="LOT-1", qty=4, unit_cost=Decimal("140")))
costs.apply(CostMovement(kind="ISSUE", product_key="P1", at=paid_at, ref="CMD-0001", qty=1))  # coût au CMP
ledger.record_expense("PUB-2026-11-08", day, Post.ACQUISITION, "20.00")
ledger.accrue_fixed_costs("400", 2026, 11)
print(ledger.weekly_report().render_markdown())
```

## Validation humaine requise

- [ ] Confirmer la définition du §1 comme métrique unique de pilotage, et l'ordre des postes.
- [ ] Confirmer les conventions : SAV et acquisition aux dépenses réelles (pas aux provisions) ; précommandes comptées à la livraison ; charges fixes réparties au jour.
- [ ] Choisir le jour et le canal de la revue hebdomadaire (proposé : lundi, rapport de l'agent 05).
- [ ] Valider avec la fiduciaire la méthode du coût historique (CMP, cf. `engine/pokeshop/costs.py`) et le traitement des montants en mode non assujetti (TTC).
