# Rapport — {{AGENT}} — {{SUJET}}

> Gabarit standard de sortie de tous les agents (`docs/08-agents/BRIEF_COMMUN.md` §6). Copier dans `docs/08-agents/rapports/` sous le nom `AAAA-MM-JJ_<agent>_<sujet>.md`. Ne jamais y mettre de secret ni de donnée personnelle de client (citer le numéro de commande, pas le nom).

## En-tête

| Champ | Valeur |
|---|---|
| Agent | {{slug, ex. finance-pricing}} (A-{{NN}}) |
| Brief | `docs/08-agents/{{NN}}_{{slug}}.md` + demande du {{date}} par {{demandeur}} |
| Date et heure | {{AAAA-MM-JJ HH:MM}} (Europe/Zurich) |
| Niveau d'autonomie actif | {{1 / 2 / 3 / 4}} |
| Mode | {{SIMULATION / RÉEL}} |
| Version des règles | {{rules_version, ex. v1-2026-10-04}} |
| Statut du rapport | {{BROUILLON / À VALIDER / VALIDÉ}} |

## Résumé

1. Fait : {{…}}
2. Bloque : {{… ou « rien »}}
3. Demandé : {{décision attendue, à qui, avant quand ; ou « rien »}}

## Livrables

| Livrable | Chemin ou référence | Statut |
|---|---|---|
| {{…}} | `{{chemin}}` | {{BROUILLON / À VALIDER / VALIDÉ / PUBLIÉ / QUARANTAINE / BLOQUÉ}} |

## Sources datées

| Source | URL ou fichier | Consultée le | Remarque |
|---|---|---|---|
| {{…}} | {{…}} | {{AAAA-MM-JJ}} | {{page ouverte / index de recherche / pièce reçue}} |

## Hypothèses

- {{Hypothèse}} — **hypothèse**, source : BP §{{n}} / {{autre}}.

## Anomalies

- {{Anomalie constatée, ou « aucune »}}

## Contrôles

| Contrôle | Résultat |
|---|---|
| Stop-loss vérifiés (produit, extension, pub, cash, global, temps) | {{actif / inactif, source}} |
| Tests lancés | `{{commande}}` → {{résultat exact, ex. 84 passed}} |
| Aucune donnée interne ni personnelle dans une sortie publique | {{OK / KO + détail}} |
| Donnée amont < 24 h | {{OK / KO}} |

## Actions externes et dépenses

| Date | Action | Destinataire ou bénéficiaire | Montant CHF | Plafond restant | Référence journal |
|---|---|---|---|---|---|
| {{…}} | {{… ou « aucune »}} | {{…}} | {{…}} | {{…}} | {{…}} |

## Impact sur l'étoile polaire

{{Montant CHF calculé par le moteur (module, fonction, entrées) — ou « non chiffrable » + raison.}}

## Exceptions ouvertes

- {{EXC-AAAAMMJJ-NN : objet, niveau, échéance — ou « aucune »}}

## Validation humaine requise

- [ ] {{Décision attendue, valideur (A-01 / A-12 / propriétaire), délai}}
