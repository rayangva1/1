# Fiches d'exception

File d'attente des décisions, au format `docs/08-agents/modeles/FICHE_EXCEPTION.md`. Vide au 4.10.2026. Flux et délais : `docs/08-agents/ORGANIGRAMME.md` §3 ; manière de décider : `docs/08-agents/RUNBOOK.md` §6.

## Règles

| Règle | Détail |
|---|---|
| Nom de fichier | `EXC-AAAAMMJJ-NN_<agent>.md` (NN = numéro d'ordre du jour, à partir de 01) |
| Niveaux | E1 : le chef de projet tranche dans le mandat · E2 : la propriétaire décide (24 h pour un gate ou toute dépense hors mandat ; 48 h sinon) · E3 : gel immédiat par `qa-conformite`, alerte |
| Statuts | `OUVERTE` → `TRIÉE` → `EN DÉCISION` → `DÉCIDÉE` → `CLOSE` ; ou `EXPIRÉE` (statu quo sûr appliqué) |
| Décision | Écrite dans la fiche : qui, quand, option, conditions. Une fiche ne modifie jamais le mandat |
| Contenu interdit | Secret, identifiant, IBAN, document d'identité, donnée personnelle de client |
| Clôture | Après exécution et vérification par `qa-conformite` |

## Validation humaine requise

- [ ] Confirmer les délais de décision et le principe du statu quo sûr à l'expiration.
