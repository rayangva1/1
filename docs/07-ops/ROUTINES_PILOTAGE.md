# Routines de pilotage — quotidien, hebdomadaire, mensuel

> Version v0.1 du 4.10.2026, rédigée par l'agent legal-ops.
> Sources : BP §12 « Tableau de bord à consulter » (chaque jour / chaque semaine / chaque mois), §3 (6 à 10 h de supervision hebdomadaire au lancement, plus la préparation des colis ; valoriser le temps dans un second compte de résultat ; 13 semaines de trésorerie), §9 (CAC sur commandes payées après annulations et remboursements), §4 (seuil TVA). Modèle d'opération : la flotte d'agents produit les chiffres et prépare les décisions ; la propriétaire lit, décide et fait le physique.
> Ce document est aussi la **spécification fonctionnelle** du tableau de bord interne (`dashboard/`, BL-091, agent 07) : chaque indicateur du §6 doit y figurer, en lecture seule, sans jamais exposer un coût ou une marge hors de l'espace interne (BP §7).

## 1. La seule métrique de décision : l'étoile polaire

**Contribution nette cumulée** = Σ (ventes nettes HT − coût historique des unités vendues − frais de paiement − logistique − SAV − acquisition) − charges fixes.

- « Ventes nettes HT » : hors TVA si l'entité est assujettie ; égales aux ventes TTC si elle ne l'est pas (t = 0, BP §4).
- Coût **historique** (lot reçu, facture réelle), jamais le coût de remplacement.
- Charges fixes : 400 CHF par mois (hypothèse BP §3), réparties par semaine pour le suivi hebdomadaire.
- Ni le chiffre d'affaires ni les followers ne servent de critère (`docs/00-pilotage/GATES_GO_NO_GO.md` §1).

Affichage : cumul depuis S1, valeur de la semaine, moyenne des 4 dernières semaines, et tendance.

## 2. Budget temps de la propriétaire

Le BP prévoit 6 à 10 h de supervision par semaine au lancement, **plus** la préparation des colis. Avec la flotte d'agents, la supervision se réduit à la lecture et aux décisions ; le reste du temps est physique. Cible au volume pilote (environ 5 à 10 colis par semaine, hypothèse) : **rester dans l'enveloppe de 6 à 10 h par semaine, colis compris**.

| Activité | Fréquence | Durée (estimation, à mesurer : BL-171) | Par semaine |
|---|---|---|---|
| Lire le digest et répondre aux décisions | 5 jours ouvrés | 10 à 15 min | 1 h à 1 h 15 |
| Sessions colis (préparation, dépôt) | {{JOURS_EXPEDITION}} | 15 min par session + 10 à 15 min par colis | 1 h 35 à 3 h 15 |
| Réception, authenticité, rangement | 1 livraison toutes les 1 à 2 semaines | 30 à 60 min + 15 min par lot | 0 h 30 à 1 h 15 |
| Photos et vidéos réelles | à chaque arrivage | 2 à 3 h | 1 h à 1 h 30 |
| Revue hebdomadaire | lundi | 45 min | 0 h 45 |
| Escalades SAV, contrôle des retours | au besoin | — | 0 h 30 |
| Revue mensuelle et inventaire, rapportés à la semaine | mensuel | 2 h 30 par mois | 0 h 35 |
| **Total** | | | **≈ 5 h 55 à 9 h 05** |

**Alerte** : plus de 10 h deux semaines de suite (R19) → l'agent 01 propose de regrouper les dépôts, de réduire le rythme ou de chiffrer un prestataire logistique (BL-055). Au scénario central du BP (100 commandes par mois, soit environ 23 colis par semaine), les colis seuls prennent 4 à 6 h : l'enveloppe ne tient plus sans prestataire.

## 3. Routine quotidienne

### 3.1 Ce que font les agents (automatique)

| Heure | Tâche | Agent |
|---|---|---|
| Nuit | Imports fournisseurs, contrôle de fraîcheur (> 24 h = blocage des achats et promesses), recalcul des prix en simulation | 03, 05 |
| Nuit | Rapprochement Shopify / moteur (stock, commandes), contrôle des stop-loss | 07, gouvernance |
| {{HEURE_DIGEST}} | **Digest quotidien** envoyé à la propriétaire (§3.2) | 01 |
| Journée | Boîte du service client : réponse dans un délai de {{DELAI_REPONSE_SUPPORT}} (SOP SAV) | 11 |
| Veille d'un jour de dépôt | Liste des colis, bons de préparation, étiquettes (SOP colis) | 11 |

### 3.2 Contenu du digest (BP §12 « chaque jour »)

```
DIGEST {{NOM_BOUTIQUE}} — jj.mm.aaaa
1. Étoile polaire : cumul … CHF | semaine en cours … CHF | 4 dernières semaines (moyenne) … CHF/sem.
2. Ventes payées hier : … commandes | ventes nettes … CHF | contribution … CHF (… %)
3. Cash disponible : … CHF (réserve 1 600 CHF ; précommandes encaissées non livrées exclues)
4. Commandes à préparer : … (dont … précommandes reçues) | prochain dépôt : …
5. Ruptures locales : … références | alertes réassort ouvertes : …
6. Offres fournisseurs périmées (> 24 h) : … | flux en panne : …
7. Incidents ouverts : S1 … | S2 … | S3 … (détail en annexe)
8. Stop-loss actifs : aucun / produit … / extension … / pub … / cash … / global … / temps …
9. DÉCISIONS ATTENDUES (oui/non, échéance) :
   a) …
10. Fait par les agents hier (dans le mandat) : … remboursements (… CHF), … emails SAV, … fiches mises à jour
```

### 3.3 Ce que fait la propriétaire (10 à 15 min)

- [ ] Lire les lignes 1, 3, 7, 8 et 9 du digest.
- [ ] Répondre à chaque décision attendue (oui / non / question), avant l'échéance indiquée.
- [ ] Un incident S1 ou un stop-loss global : appliquer `SOP_INCIDENTS.md` ; seul le réarmement du stop-loss global lui revient.
- [ ] Jour de dépôt : session colis (`SOP_PREPARATION_COLIS.md`).

## 4. Routine hebdomadaire (lundi)

### 4.1 Rapport préparé par les agents (BP §12 « chaque semaine »)

| Rubrique | Contenu | Agent |
|---|---|---|
| Étoile polaire | Semaine, cumul, moyenne sur 4 semaines, détail des postes | 05 |
| Trésorerie 13 semaines | Solde, achats engagés, TVA, livraisons, remboursements, publicité, versements ; semaines sous la réserve de 1 600 CHF (`engine/pokeshop/treasury.py`) | 05 |
| Rotation par extension | Ventes au coût, stock au coût, jours de couverture, part du budget stock (plafond 25 %) | 05 |
| Produits sans vente | Références sans vente depuis 14, 30 et 45 jours (45 j = stop-loss extension) | 05 |
| CAC | Dépenses d'acquisition (publicité, produits offerts, commissions) / commandes payées nettes d'annulations et de remboursements ; comparaison à la contribution sur 7 jours glissants | 10 |
| Réachat | Part des commandes de clients ayant déjà commandé | 09 |
| Écarts de coûts | Facture réelle contre estimation, par lot (> 2 % expliqué) | 05 |
| Litiges et remboursements | Nombre et montant par cas SAV ; coût SAV par commande contre la provision de 1 CHF (hypothèse BP §4) | 11 |
| Commandes proposées | Propositions de réassort (MOQ, cartons, budget, plafond) : **à valider**, jamais passées automatiquement avant le niveau 4 | 11, 05 |
| Temps | Heures de la propriétaire par activité (§2) | 01 |
| Rapprochement | Paiements, remboursements et versements PSP (écart 0 ou expliqué, BL-166) | 05 |

### 4.2 Revue de la propriétaire (45 min)

- [ ] Étoile polaire : la tendance des 4 dernières semaines est-elle positive ?
- [ ] Trésorerie : une semaine passe-t-elle sous 1 600 CHF ?
- [ ] Valider ou refuser chaque réassort proposé.
- [ ] Décider des démarques proposées (stop-loss extension).
- [ ] Lire le bilan CAC : poursuivre, réduire ou couper la publicité (gate G5).
- [ ] Noter ses heures de la semaine.

## 5. Routine mensuelle (premier lundi du mois)

| Rubrique (BP §12 « chaque mois ») | Contenu | Agent | Décision de la propriétaire |
|---|---|---|---|
| Résultat avec valorisation du temps | Étoile polaire du mois ; second compte de résultat : heures × {{TAUX_HORAIRE_VALORISATION}} ; taux horaire implicite | 05 | Continuer au même rythme ? |
| Seuil TVA | Chiffre d'affaires déterminant des 12 derniers mois de **toute l'entité** et projection annuelle, contre le seuil de 100 000 CHF (BP §4) ; alerte dès que la projection dépasse 70 % du seuil (hypothèse) | 05 | Saisir la fiduciaire |
| Capacité stock | Valeur du stock au coût, place disponible au lieu de stockage, budget restant par extension | 05, 11 | — |
| Dépenses outils | Abonnements réels contre l'enveloppe de 180 CHF par mois (BP §3) | 01 | Résilier un outil inutile |
| Inventaire physique | Comptage complet, écarts expliqués (A08, BL-167) | Propriétaire, 11 | — |
| Niveau d'autonomie | Incidents du mois ; proposition de passage au niveau supérieur ou maintien | 01, 12 | Activer ou non |
| Données personnelles | Purges selon les durées de conservation (`docs/04-legal/CONFIDENTIALITE.md`) ; liste des demandes LPD du mois | 12 | — |
| Sauvegarde | Test de restauration (BP §6), au moins une fois par trimestre | 07, 12 | — |

## 6. Dictionnaire des indicateurs (spécification du tableau de bord)

| Indicateur | Définition | Source | Fréquence | Seuil ou alerte |
|---|---|---|---|---|
| Étoile polaire | §1 | Moteur (coûts historiques, commandes, SAV, acquisition) + charges fixes | Jour, semaine, cumul | Moyenne sur 4 semaines < 0 : alerte ; perte cumulée = 20 % du capital engagé : stop-loss global |
| Ventes payées | Commandes payées, nettes d'annulations | Shopify | Jour | — |
| Contribution par commande | Ventes nettes − coût historique − paiement − logistique − SAV − acquisition | `pokeshop.pricing.basket_contribution` | Jour | < 12 % ou < 8 CHF : stop-loss produit |
| Cash disponible | Solde − précommandes encaissées non livrées | `pokeshop.treasury` | Jour | < 1 600 CHF : stop-loss cash |
| Commandes à préparer | Payées, réservées, non expédiées | Shopify | Jour | Âge > {{DELAI_EXPEDITION}} : alerte |
| Ruptures locales | Références publiées avec stock vendable local = 0 | Moteur stock | Jour | — |
| Offres périmées | Offres fournisseurs de plus de 24 h | Imports | Jour | Toute offre utilisée pour une promesse : erreur critique |
| Incidents ouverts | Par gravité | `audit_log`, incidents | Jour | Un S1 ouvert : alerte immédiate |
| Rotation par extension | Coût des ventes / stock moyen au coût ; jours de couverture | Moteur | Semaine | — |
| Exposition par extension | Stock au coût de l'extension / budget stock | Moteur | Semaine | > 25 % : stop-loss extension |
| Produits sans vente | Jours depuis la dernière vente | Moteur | Semaine | 45 j : stop-loss extension |
| CAC | Dépenses d'acquisition / commandes payées nettes (BP §9) | Plateformes pub, codes et liens dédiés, Shopify | Semaine (7 j glissants) | CAC > contribution avant acquisition : stop-loss pub |
| Réachat | Part des commandes de clients existants | Shopify | Semaine | — |
| Écart de coût | (Facture − estimation) / estimation par lot | Workflow facture → marge | Semaine | > 2 % : explication |
| Coût SAV par commande | (Remboursements non récupérés + renvois + étiquettes) / commandes | Journal SAV | Semaine | > 1 CHF (provision R) : revue |
| Délai de première réponse SAV | Médiane | Messagerie | Semaine | > {{DELAI_REPONSE_SUPPORT}} : alerte |
| Remboursements | Nombre, montant, motif | PSP, journal SAV | Semaine | — |
| Réassorts proposés | Lignes, montant, budget restant | `propose_reorder` | Semaine | Sans réponse 24 h : expire |
| Seuil TVA | CA déterminant 12 mois glissants de l'entité / 100 000 CHF | Comptabilité, `vat_threshold_check` | Mois | Projection > 70 % : fiduciaire |
| Temps de la propriétaire | Heures par activité | Saisie hebdomadaire | Semaine | > 10 h deux semaines de suite |
| Dépenses outils | Abonnements payés | Comptabilité | Mois | > 180 CHF : revue |
| Jours depuis l'ouverture sans seuils de validation | Selon `GATES_GO_NO_GO.md` | Agent 01 | Semaine | 60 j : stop-loss temps (dossier) |

## Validation humaine requise

- [ ] Propriétaire : valider l'heure du digest (`HEURE_DIGEST`) et les jours de dépôt.
- [ ] Propriétaire : fixer le taux horaire de valorisation du temps (`TAUX_HORAIRE_VALORISATION`).
- [ ] Propriétaire : valider le seuil d'alerte TVA à 70 % du seuil (hypothèse) avec la fiduciaire.
- [ ] Agent 07 : construire le tableau de bord à partir du §6 (BL-091), en lecture seule.
