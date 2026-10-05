# Demande d'engagement de dépense {{DEM-AAAAMMJJ-NN}}

> Gabarit unique pour toute dépense demandée par un agent (`docs/08-agents/BRIEF_COMMUN.md` §8). L'agent demandeur remplit la partie 1 et soumet la demande au moteur (`POST /mandate/check`) **avec son propre jeton nommé** (ou par le workflow 08 s'il n'a pas accès à l'API). La partie 2 recopie la décision du moteur, qui lit lui-même mandat, trésorerie, solde PayPal, taux de change et proposition de réassort dans ses registres : aucun de ces chiffres n'est saisi par un agent. L'agent 05 exécute le paiement par la passerelle `CONN-PAYPAL` seulement si la décision est `APPROVED_WITHIN_MANDATE` et payable (moins d'une heure) ; sinon, fiche d'exception E2 (24 h, puis expiration). Le résultat est inscrit dans `docs/08-agents/modeles/REGISTRE_MANDAT.csv` (ou le registre défini par `docs/00-pilotage/DELEGATION_AUTONOMIE.md`).

## 1. Demande (agent demandeur)

| Champ | Valeur |
|---|---|
| Agent demandeur | {{slug}} (A-{{NN}}) |
| Objet | {{ex. 200 étuis de protection pour colis}} |
| Bénéficiaire | {{raison sociale}} — identifiant au mandat : {{…}} |
| Catégorie du mandat | {{emballages / DA et contenus / site et outils / échantillons / autre}} |
| Montant | {{montant}} {{devise}} TTC ; en CHF : {{calculé par le moteur au taux de référence du registre (`POST /fx/rates`, saisi par la propriétaire) ; sans taux frais : validation humaine}} |
| Source du montant | {{devis n°…, page consultée le … (URL)}} — **jamais un montant supposé** |
| Pourquoi maintenant (lien avec l'étoile polaire) | {{…}} |
| Alternative moins chère ou différable | {{…}} |
| Moyen de paiement prévu | {{PayPal (API Payouts) / autre : hors mandat → propriétaire}} |

## 2. Décision du moteur (`POST /mandate/check`), recopiée telle quelle

| Élément | Valeur (réponse du moteur) |
|---|---|
| Demandé par (déduit du jeton) | {{agent-NN-… ou n8n-08-…}} |
| Décision | {{APPROVED_WITHIN_MANDATE / NEEDS_HUMAN_APPROVAL / REJECTED}} |
| Motifs (codes stables) | {{ex. ABOVE_TRANSACTION_CAP, TREASURY_UNVERIFIED, FX_RATE_UNVERIFIED, NO_ENGINE_PROPOSAL…}} |
| Mandat actif (empreinte au coffre), bénéficiaire autorisé, plafonds, enveloppe restante | {{chiffres du moteur}} |
| Trésorerie : source et déposant (photo stop-loss acceptée, solde PayPal relevé) | {{treasury_source ; déposé par un autre jeton que le demandeur : oui / non → validation humaine}} |
| Stop-loss (cash, global, extension, produit, pub) et niveau d'autonomie | {{état lu par le moteur}} |
| Clé d'idempotence (= `sender_batch_id`) | {{…}} |
| Coordonnées de paiement identiques à celles du coffre (aucun changement reçu par email) — contrôle de l'agent 05 | {{oui / non → E3 fraude}} |

**Suite :** {{payée par l'agent 05 (APPROVED) / E2 → fiche EXC-… (NEEDS_HUMAN_APPROVAL, 24 h) / refus journalisé (REJECTED)}}

## 3. Exécution

| Champ | Valeur |
|---|---|
| Date d'exécution | {{AAAA-MM-JJ HH:MM}} |
| Référence de paiement | {{identifiant du lot PayPal, sans donnée sensible}} |
| Ligne du registre | {{n°}} |
| Rapprochement A-12 | {{date, OK / écart}} |

## Validation humaine requise

- [ ] {{Si E2 : décision de la propriétaire sur la fiche EXC-… ; sinon « aucune, dépense dans le mandat »}}
