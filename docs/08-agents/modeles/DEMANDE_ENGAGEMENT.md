# Demande d'engagement de dépense {{DEM-AAAAMMJJ-NN}}

> Gabarit unique pour toute dépense demandée par un agent (`docs/08-agents/BRIEF_COMMUN.md` §8). L'agent demandeur remplit la partie 1 ; l'agent 05 (finance et pricing) fait le contrôle de la partie 2 et, si tout est vert, exécute le paiement par la passerelle `CONN-PAYPAL`. Sinon, il ouvre une fiche d'exception E2. Le résultat est inscrit dans `docs/08-agents/modeles/REGISTRE_MANDAT.csv` (ou le registre défini par `docs/00-pilotage/DELEGATION_AUTONOMIE.md`).

## 1. Demande (agent demandeur)

| Champ | Valeur |
|---|---|
| Agent demandeur | {{slug}} (A-{{NN}}) |
| Objet | {{ex. 200 étuis de protection pour colis}} |
| Bénéficiaire | {{raison sociale}} — identifiant au mandat : {{…}} |
| Catégorie du mandat | {{emballages / DA et contenus / site et outils / échantillons / autre}} |
| Montant | {{montant}} {{devise}} TTC ; en CHF : {{calcul A-05 par le moteur, source du taux et date}} |
| Source du montant | {{devis n°…, page consultée le … (URL)}} — **jamais un montant supposé** |
| Pourquoi maintenant (lien avec l'étoile polaire) | {{…}} |
| Alternative moins chère ou différable | {{…}} |
| Moyen de paiement prévu | {{PayPal (API Payouts) / autre : hors mandat → propriétaire}} |

## 2. Contrôle (agent 05)

| Contrôle | Résultat |
|---|---|
| Mandat signé et en vigueur | {{oui / non}} |
| Bénéficiaire dans la liste autorisée | {{oui / non}} |
| Montant ≤ plafond par transaction | {{oui / non}} ({{plafond}} CHF) |
| Cumul de la catégorie ≤ plafond mensuel ou enveloppe BP §3 | {{oui / non}} (reste avant : {{…}} CHF) |
| Stop-loss cash inactif (cash disponible − montant ≥ 1 600 CHF) | {{oui / non}} |
| Stop-loss global inactif | {{oui / non}} |
| Niveau d'autonomie suffisant | {{oui / non}} |
| Pas de doublon (clé d'idempotence = `sender_batch_id`) | {{oui / non}} |
| Coordonnées de paiement identiques à celles du mandat (aucun changement reçu par email) | {{oui / non → E3 fraude}} |

**Décision :** {{AUTO_MANDAT (tout est oui) / E2 → fiche EXC-… / REFUSÉ (motif)}}

## 3. Exécution

| Champ | Valeur |
|---|---|
| Date d'exécution | {{AAAA-MM-JJ HH:MM}} |
| Référence de paiement | {{identifiant du lot PayPal, sans donnée sensible}} |
| Ligne du registre | {{n°}} |
| Rapprochement A-12 | {{date, OK / écart}} |

## Validation humaine requise

- [ ] {{Si E2 : décision de la propriétaire sur la fiche EXC-… ; sinon « aucune, dépense dans le mandat »}}
