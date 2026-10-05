# 00-pilotage — plan, backlog, gates, interventions humaines

Dossier du chef de projet (BP §11, agent 01). Source métier : BP du 4.10.2026 (`docs/business-plan/business_plan_extrait.txt`). Contrat technique : `docs/SPEC.md`.

**Étoile polaire :** contribution nette cumulée (ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes). Ni CA ni followers.

## Contenu

| Fichier | Rôle | Propriétaire |
|---|---|---|
| `PLAN_90_JOURS.md` | Plan au jour (J1-J15), puis à la semaine (S3-S13) ; responsables humain/agent ; critères de passage BP §9 et §13 | Agent pilotage |
| `BACKLOG.csv` | 181 tâches sur tout le BP, importables dans Notion ; dépendances vérifiées sans cycle | Agent pilotage |
| `GATES_GO_NO_GO.md` | Gates G0 à G7, seuils chiffrés, décideur, modèle de fiche | Agent pilotage |
| `INTERVENTIONS_HUMAINES.md` | Checklist maîtresse et exhaustive de ce qui exige une personne (A physique, B légal une fois, C validations, signatures et réarmement), chaque fiche reliée à ses tâches du backlog | Agent pilotage |
| `REGISTRE_RISQUES.md` | 31 risques : probabilité, impact, mitigation, déclencheur, stop-loss lié | Agent pilotage |
| `REVUE_SECURITE.md` | Revue adverse de sécurité : historique des 5 rounds, catégories et correctifs, **risques résiduels connus** (impact, mitigation, niveau d'autonomie avant lequel les traiter), procédure à relancer avant chaque passage aux niveaux 2, 3 et 4 | Agent 12 (contenu, par rapport), agent 01 (écriture), propriétaire (acceptation) |
| `ECARTS_BP.md` | Écarts et ambiguïtés du BP, consolidés pour les 11 domaines du build (ID par domaine, gravité, traitement provisoire, décision attendue) | Partagé |
| `DELEGATION_AUTONOMIE.md`, `ETOILE_POLAIRE.md`, `STOP_LOSS.md` | Mandat, métrique, stop-loss | Agent gouvernance (non modifiés ici) |
| `outils/verifier_livrables.py` | Contrôle de cohérence des dossiers 00, 01 et 02 | Agent pilotage |

## Importer le backlog dans Notion

1. Notion → *Importer* → *CSV* → `BACKLOG.csv` (UTF-8, séparateur virgule).
2. Après l'import, convertir les colonnes : `Phase`, `Agent/rôle`, `Priorité`, `Statut`, `Validation humaine (O/N)` en *Sélection* ; `Dépendances` en *Sélection multiple* (valeurs séparées par des virgules) ou en *Relation* vers la même base.
3. Vues utiles : *Tableau* par `Statut` ; *Filtre* `Validation humaine = O` (ce que la propriétaire doit faire) ; *Tri* par `Échéance`.

Dans Excel : *Données → À partir d'un fichier texte/CSV*, encodage UTF-8 (65001).

## Vérifier

```bash
python docs/00-pilotage/outils/verifier_livrables.py          # 18 contrôles de cohérence
python -m pytest -q docs/00-pilotage/outils docs/02-sourcing/outils
```

Le vérificateur contrôle notamment :

- le backlog : dépendances existantes et sans cycle, valeurs autorisées, toute tâche de la propriétaire marquée O ;
- le tracker : aucun contact marqué établi ;
- la grille : aucun prix sans lecture datée de la page ;
- le panier : 15 à 25 références, dont 8 à 12 en stock ;
- l'assortiment : plafond de 750 CHF par extension ;
- les emails : liste complète du BP §2, relances J+5 et J+12 ;
- les interventions humaines : toute tâche de la propriétaire du backlog y figure, à la même échéance que dans le backlog et le plan ;
- les gates : une même date par gate partout, calendrier de contenu compris (G5 : J60 avec l'option B, J64 avec l'option A) ;
- les échéances : aucune tâche n'échoit avant l'une de ses dépendances ;
- les compteurs : items par catégorie d'`INTERVENTIONS_HUMAINES.md` et nombre de tâches du backlog ;
- les écarts du BP : identifiant par domaine, gravité, traitement provisoire et décision attendue sur chaque ligne ;
- les documents : aucun livrable livré annoncé « attendu » ; section finale « Validation humaine requise ».

## Validation humaine requise

- [ ] Valider le plan, les gates et la date de J1 (BL-016), puis la checklist `INTERVENTIONS_HUMAINES.md`.
- [ ] Lire `REVUE_SECURITE.md` §4 (risques résiduels) et décider, pour chacun, correction ou acceptation écrite avant le niveau indiqué.
- [ ] Trancher les écarts **bloquants** de `ECARTS_BP.md` (EC-01, EC-07, EC-F-06, EC-G-01, EC-S-02).
