# Matrice d'autorisations de l'API du moteur

> Générée depuis `engine/pokeshop/authz.py` (version `2026-10-05.r3`) — ne pas modifier à la main :
> `python -m pokeshop.authz > docs/08-agents/MATRICE_API.md`. Refus par défaut : une route absente
> de la matrice est refusée (403). Le **jeton commun** n'a que la lecture et les aperçus en simulation.
> Nom d'un jeton nommé = rôle ; son empreinte sha256 va dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (une variable
> par rôle, ex. `POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS`) ou dans la liste `POKESHOP_AGENT_TOKENS_SHA256=rôle:empreinte,…` ;
> propriétaire = en-tête `X-Pokeshop-Owner-Token` valide, distinct du jeton d'API.

| Méthode | Route | Nature | Jeton commun | Rôles nommés admis | Propriétaire | Note |
|---|---|---|---|---|---|---|
| POST | `/ads/activity` | WRITE | **non** | connecteur-publicite | oui | ajout seul par (campagne, jour) ; commandes attribuées = commandes connues du moteur |
| GET | `/autonomy` | READ | oui | tous | oui |  |
| POST | `/autonomy` | WRITE | **non** | tous les rôles nommés | oui | baisser : tout rôle ; relever : propriétaire |
| GET | `/capital/movements` | READ | oui | tous | oui |  |
| POST | `/capital/movements` | WRITE | **non** | aucun | oui |  |
| GET | `/catalog` | READ | oui | tous | oui |  |
| GET | `/catalog/approvals` | READ | oui | tous | oui |  |
| POST | `/catalog/approvals` | WRITE | **non** | aucun | oui | fiche approuvée, contenu validé, règle de catégorie : propriétaire seule |
| POST | `/catalog/cost-inputs` | WRITE | **non** | finance-pricing | oui | fret, douane, TVA import |
| POST | `/catalog/items` | WRITE | **non** | catalogue | oui | fiches sans champ moteur ni validation humaine (422) |
| POST | `/costs/movements` | WRITE | **non** | finance-pricing | oui | réception adossée à /stock/receive ; écart de facture > 2 % : propriétaire |
| GET | `/dashboard/daily` | READ | oui | tous | oui |  |
| GET | `/dashboard/monthly` | READ | oui | tous | oui |  |
| GET | `/dashboard/weekly` | READ | oui | tous | oui |  |
| POST | `/fx/rates` | WRITE | **non** | aucun | oui |  |
| GET | `/health` | PUBLIC | — | sans jeton | — | état sans secret |
| POST | `/imports/{supplier}/run` | WRITE | **non** | donnees-fournisseurs, n8n-01-sync | oui | simulation ; met à jour la référence « dernier import » |
| GET | `/incidents` | READ | oui | tous | oui |  |
| POST | `/incidents` | WRITE | **non** | tous les rôles nommés | oui | signalement protecteur, tout rôle nommé |
| POST | `/incidents/{incident_id}/close` | WRITE | **non** | chef-de-projet, n8n-04-incidents, qa-conformite | oui |  |
| POST | `/incidents/{incident_id}/resume` | WRITE | **non** | chef-de-projet, n8n-04-incidents, qa-conformite | oui | après test réussi attesté ; incident critique : propriétaire |
| POST | `/incidents/{incident_id}/test` | WRITE | **non** | tous les rôles nommés | oui | passed:true : qa-conformite (≠ ouvreur, cycle réel lancé par un autre principal) ou propriétaire |
| POST | `/mandate/check` | WRITE | **non** | acquisition, chef-de-projet, communication, direction-artistique, finance-pricing, n8n-08-mandat, operations-sav, site-integrations, sourcing | non | requested_by = rôle du jeton ; relais n8n-08-mandat : trésorerie non vérifiable (validation humaine) |
| POST | `/mandate/revoke` | WRITE | **non** | tous les rôles nommés | oui | acte protecteur |
| GET | `/northstar` | READ | oui | tous | oui |  |
| POST | `/northstar/entries` | WRITE | **non** | finance-pricing, n8n-02-commandes | oui | rôles : coûts positifs (PAYMENT, SAV, acquisition, charges fixes) ; propriétaire : écriture manuelle |
| POST | `/orders/shipped` | WRITE | **non** | n8n-02-commandes | oui | vente dérivée d'une commande, coût transporteur réel exigé |
| POST | `/orders/{order_id}/refunds` | WRITE | **non** | n8n-02-commandes, operations-sav | oui | avoir sur une commande enregistrée |
| GET | `/pricing/approvals` | READ | oui | tous | oui |  |
| POST | `/pricing/approvals` | WRITE | **non** | aucun | oui | approbation d'un prix public |
| POST | `/pricing/approvals/{approval_id}/revoke` | WRITE | **non** | chef-de-projet, finance-pricing, qa-conformite | oui | acte protecteur (retour au prix du moteur) |
| POST | `/pricing/basket` | PREVIEW | oui | tous | oui | calcul, aucun état |
| POST | `/pricing/quote` | PREVIEW | oui | tous | oui | calcul, aucun état |
| POST | `/publish/preview` | PREVIEW | oui | tous | oui | aperçu : fiche, registres d'approbation et de publication |
| POST | `/stock/receive` | WRITE | **non** | operations-sav | oui | réception physique contrôlée (passerelle 06 : jeton operations-sav) |
| POST | `/stock/reorder-proposal` | WRITE | **non** | finance-pricing, operations-sav | oui | cap_exceptions : propriétaire |
| POST | `/stock/sellable` | PREVIEW | oui | tous | oui | lecture du registre ou calcul |
| POST | `/stoploss/baseline` | WRITE | **non** | aucun | oui | point zéro, avec la première photo de façon atomique |
| POST | `/stoploss/capital-memory/reset` | WRITE | **non** | aucun | oui |  |
| POST | `/stoploss/freeze` | WRITE | **non** | tous les rôles nommés | oui | gel manuel protecteur |
| POST | `/stoploss/rearm` | WRITE | **non** | aucun | oui |  |
| POST | `/stoploss/state` | WRITE | **non** | n8n-07-stoploss | oui | photo déposée (valeurs décisives) |
| POST | `/stoploss/state/refresh` | WRITE | **non** | n8n-07-stoploss | oui | photo construite par le moteur depuis ses registres |
| GET | `/stoploss/status` | READ | oui | tous | oui | évalue le stop-loss (verrouillage protecteur possible) |
| GET | `/sync/history` | READ | oui | tous | oui |  |
| POST | `/sync/run` | WRITE | **non** | n8n-01-sync, site-integrations | oui | simulation par défaut ; écriture réelle : porte de gouvernance |
| POST | `/treasury/balance-items` | WRITE | **non** | connecteur-tresorerie, finance-pricing | oui | dettes et créances à date |
| POST | `/treasury/bank-balance` | WRITE | **non** | connecteur-tresorerie | oui |  |
| POST | `/treasury/paypal-balance` | WRITE | **non** | connecteur-tresorerie | oui |  |

## Rôles

| Rôle (nom du jeton) | Description |
|---|---|
| `chef-de-projet` | Agent 01 — chef de projet (dispatch, revue des exceptions) |
| `sourcing` | Agent 02 — sourcing (fournisseurs, devis) |
| `donnees-fournisseurs` | Agent 03 — données fournisseurs (imports en simulation) |
| `catalogue` | Agent 04 — catalogue (fiches en brouillon, jamais approuvées par lui) |
| `finance-pricing` | Agent 05 — finance et pricing (coûts, frais, dettes et créances) |
| `direction-artistique` | Agent 06 — direction artistique |
| `site-integrations` | Agent 07 — site et intégrations (cycles de synchronisation) |
| `seo-redaction` | Agent 08 — SEO et rédaction |
| `communication` | Agent 09 — communication |
| `acquisition` | Agent 10 — acquisition (dépense pub : ne déclare jamais l'activité pub) |
| `operations-sav` | Agent 11 — opérations et SAV (réceptions physiques de stock) |
| `qa-conformite` | Agent 12 — QA et conformité (atteste les tests d'incident, peut geler) |
| `n8n-01-sync` | Workflow n8n 01 — fournisseur vers site (imports, cycles en simulation) |
| `n8n-02-commandes` | Workflow n8n 02 — commandes (frais PSP réels, commandes expédiées) |
| `n8n-03-factures` | Workflow n8n 03 — factures (signalement d'écarts) |
| `n8n-04-incidents` | Workflow n8n 04 — incidents (ouverture, reprise après test attesté) |
| `n8n-05-digest` | Workflow n8n 05 — digest quotidien (lecture) |
| `n8n-06-marketing` | Workflow n8n 06 — automatisations marketing (incidents) |
| `n8n-07-stoploss` | Workflow n8n 07 — photo du stop-loss construite par le moteur, gel |
| `n8n-08-mandat` | Workflow n8n 08 — passerelle du mandat de dépense (relais : trésorerie jamais vérifiable) |
| `connecteur-tresorerie` | Connecteur banque et PayPal en lecture seule (soldes relevés) |
| `connecteur-publicite` | Connecteur de la plateforme publicitaire (dépenses, commandes attribuées) |

## Écritures par rôle

Écritures **propres** à chaque rôle (hors actes ouverts à tout rôle nommé). Tout rôle nommé peut en plus :
POST `/autonomy`, POST `/incidents/{incident_id}/test`, POST `/incidents`, POST `/mandate/revoke`, POST `/stoploss/freeze` (signalement, gel, baisse de niveau, révocation ; test réussi : voir la note).
Propriétaire seule : POST `/capital/movements`, POST `/catalog/approvals`, POST `/fx/rates`, POST `/pricing/approvals`, POST `/stoploss/baseline`, POST `/stoploss/capital-memory/reset`, POST `/stoploss/rearm`.

| Rôle (nom du jeton) | Écritures propres |
|---|---|
| `chef-de-projet` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume`, POST `/mandate/check`, POST `/pricing/approvals/{approval_id}/revoke` |
| `sourcing` | POST `/mandate/check` |
| `donnees-fournisseurs` | POST `/imports/{supplier}/run` |
| `catalogue` | POST `/catalog/items` |
| `finance-pricing` | POST `/catalog/cost-inputs`, POST `/costs/movements`, POST `/mandate/check`, POST `/northstar/entries`, POST `/pricing/approvals/{approval_id}/revoke`, POST `/stock/reorder-proposal`, POST `/treasury/balance-items` |
| `direction-artistique` | POST `/mandate/check` |
| `site-integrations` | POST `/mandate/check`, POST `/sync/run` |
| `seo-redaction` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `communication` | POST `/mandate/check` |
| `acquisition` | POST `/mandate/check` |
| `operations-sav` | POST `/mandate/check`, POST `/orders/{order_id}/refunds`, POST `/stock/receive`, POST `/stock/reorder-proposal` |
| `qa-conformite` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume`, POST `/pricing/approvals/{approval_id}/revoke` |
| `n8n-01-sync` | POST `/imports/{supplier}/run`, POST `/sync/run` |
| `n8n-02-commandes` | POST `/northstar/entries`, POST `/orders/shipped`, POST `/orders/{order_id}/refunds` |
| `n8n-03-factures` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `n8n-04-incidents` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume` |
| `n8n-05-digest` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `n8n-06-marketing` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `n8n-07-stoploss` | POST `/stoploss/state/refresh`, POST `/stoploss/state` |
| `n8n-08-mandat` | POST `/mandate/check` |
| `connecteur-tresorerie` | POST `/treasury/balance-items`, POST `/treasury/bank-balance`, POST `/treasury/paypal-balance` |
| `connecteur-publicite` | POST `/ads/activity` |

## Séparation des rôles (aucune valeur décisive déclarée par son bénéficiaire)

- Activité publicitaire : `connecteur-publicite`, jamais `acquisition` ; dépense retenue par (campagne, jour) =
  MAX(déclaration, paiements pub exécutés du registre du mandat) ; registre en ajout seul (baisse refusée).
- Fiches : `catalogue` les dépose ; `approved`, `content_validated`, `category_rule_validated` : propriétaire
  (`POST /catalog/approvals`, liée au contenu de la fiche).
- Coûts historiques : `finance-pricing`, réception adossée à `POST /stock/receive` (`operations-sav`, autre jeton) ;
  écart de facture > 2 % : propriétaire.
- Étoile polaire : ventes et avoirs dérivés de commandes enregistrées (`POST /orders/shipped`, coût transporteur
  réel) ; écritures manuelles et montants négatifs (référencés) : propriétaire.
- Test d'incident réussi : `qa-conformite` (≠ ouvreur, cycle réel lancé par un autre principal) ou propriétaire.

## Validation humaine requise

- [ ] Générer un jeton par rôle (`openssl rand -hex 32`), en reporter l'empreinte SHA-256 dans
      `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` de `/etc/pokeshop/api.env` et le jeton en clair dans l'identifiant
      n8n du même nom (jamais dans le dépôt) ; le jeton propriétaire reste hors de n8n et des agents.
- [ ] Relire cette matrice avant chaque nouvelle route d'écriture : une route absente est refusée.
