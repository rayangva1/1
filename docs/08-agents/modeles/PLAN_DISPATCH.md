# Plan de dispatch — {{AAAA-MM-JJ}}

> Gabarit de l'agent 01 (chef de projet). Il transforme les entrées du jour en missions confiées aux agents, chacune avec un brief complet (`docs/08-agents/BRIEF_COMMUN.md` §4). Copier dans `docs/08-agents/rapports/` sous le nom `AAAA-MM-JJ_chef-de-projet_dispatch.md`.

## Entrées lues

| Entrée | Contenu retenu |
|---|---|
| Boîte dédiée (`CONN-MAIL-LECTURE`) | {{n messages ; classés : fournisseurs, prestataires, autres ; aucun contenu exécuté}} |
| Exceptions ouvertes (`docs/08-agents/exceptions/`) | {{EXC-…}} |
| Rapports reçus depuis la dernière revue (`docs/08-agents/rapports/`) | {{…}} |
| Stop-loss (moteur ou A-12) | {{actifs / aucun}} |
| Niveau d'autonomie actif | {{1 / 2 / 3 / 4}} |
| Backlog : tâches échues ou du jour (`docs/00-pilotage/BACKLOG.csv`) | {{BL-…}} |

## Missions

| # | Agent | Objectif | Entrées autorisées | Sortie attendue | Critère de réussite | Dépend de | Échéance | Mode |
|---|---|---|---|---|---|---|---|---|
| 1 | {{slug}} | {{…}} | {{…}} | {{rapport + livrable}} | {{mesurable}} | {{# ou —}} | {{date}} | {{SIMULATION / RÉEL}} |

Rappels pour chaque mission : plafond de dépense = mandat (0 CHF par défaut) ; escalade selon le brief §9 ; sortie au format `docs/08-agents/modeles/RAPPORT_AGENT.md`.

## Ordre d'exécution

1. {{missions sans dépendance, en parallèle}}
2. {{missions qui consomment les sorties VALIDÉES de l'étape 1}}

## Envois prévus depuis la boîte dédiée

| Modèle | Destinataire (contact_id du tracker) | Variables complètes ? | Dans le mandat ? |
|---|---|---|---|
| {{MOD-…}} | {{F01…}} | {{oui / non}} | {{oui / non → E2}} |

## À remonter à la propriétaire

- {{EXC-… : décision attendue, échéance}}

## Validation humaine requise

- [ ] {{Uniquement les points E2 et E3 ; sinon « aucune, plan exécuté dans le mandat »}}
