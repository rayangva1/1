# Exception {{EXC-AAAAMMJJ-NN}} — {{objet court}}

> Gabarit d'escalade (`docs/08-agents/BRIEF_COMMUN.md` §7, flux `docs/08-agents/ORGANIGRAMME.md` §3). Copier dans `docs/08-agents/exceptions/` sous le nom `EXC-AAAAMMJJ-NN_<agent>.md`. Une fiche par décision. Ne jamais y mettre de secret ni de donnée personnelle de client.

## Identification

| Champ | Valeur |
|---|---|
| Ouverte par | {{agent}} (A-{{NN}}) |
| Date et heure | {{AAAA-MM-JJ HH:MM}} |
| Niveau proposé | {{E1 / E2 / E3}} |
| Déclencheur | {{référence : brief NN §9, ligne n — ou BRIEF_COMMUN §7}} |
| Gel appliqué | {{non / oui : quoi, par qui, à quelle heure}} |
| Statut | {{OUVERTE / TRIÉE / EN DÉCISION / DÉCIDÉE / CLOSE / EXPIRÉE}} |
| Échéance de décision | {{AAAA-MM-JJ HH:MM}} (48 h ; 24 h pour un gate ou un achat ; immédiat pour E3) |

## Faits

- {{Fait observé}} — source : {{fichier, URL, email (date), journal}}.

## Impact

| Mesure | Valeur | Source |
|---|---|---|
| Étoile polaire (CHF) | {{montant du moteur ou « non chiffrable »}} | {{module, fonction}} |
| Cash disponible après décision | {{CHF}} | `pokeshop.treasury` |
| Risque | {{description}} | `docs/00-pilotage/REGISTRE_RISQUES.md` R{{nn}} |

## Options

| Option | Effet | Coût CHF | Risque | Dans le mandat ? |
|---|---|---|---|---|
| A — {{statu quo sûr}} | {{…}} | {{…}} | {{…}} | oui |
| B — {{…}} | {{…}} | {{…}} | {{…}} | {{oui / non}} |
| C — {{…}} | {{…}} | {{…}} | {{…}} | {{oui / non}} |

**Recommandation de l'agent :** {{option}} — parce que {{raison reliée à l'étoile polaire}}.

## Triage (A-01)

- Niveau confirmé : {{E1 / E2 / E3}} — destinataire : {{A-01 / propriétaire}} — date : {{…}}.

## Décision

| Champ | Valeur |
|---|---|
| Décidé par | {{A-01 / propriétaire}} |
| Date | {{AAAA-MM-JJ HH:MM}} |
| Décision | {{APPROUVÉ / APPROUVÉ SOUS CONDITIONS / REFUSÉ / REPORTÉ}} — option {{A/B/C}} |
| Conditions | {{plafond, durée, contrôle}} |

## Exécution et clôture

- Exécuté par {{agent}} le {{date}} — référence : {{journal, rapport}}.
- Vérifié par A-12 le {{date}} — {{test ou contrôle}}.

## Validation humaine requise

- [ ] {{Décision attendue de la propriétaire, ou « aucune (E1) »}}
