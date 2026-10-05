# Matrice d'autorisations de l'API du moteur

> Générée depuis `engine/pokeshop/authz.py` (version `2026-10-05.r6`) — ne pas modifier à la main :
> `python -m pokeshop.authz > docs/08-agents/MATRICE_API.md`. Refus par défaut : une route absente
> de la matrice est refusée (403). Le **jeton commun** n'a que la lecture et les aperçus en simulation.
> Nom d'un jeton nommé = rôle ; son empreinte sha256 va dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (une variable
> par rôle, ex. `POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS`) ou dans la liste `POKESHOP_AGENT_TOKENS_SHA256=rôle:empreinte,…` ;
> propriétaire = en-tête `X-Pokeshop-Owner-Token` valide, distinct du jeton d'API, **suffisant seul** sur toute
> route qui admet la propriétaire (aucun jeton d'API requis : revue R4, R3-DOC-01).

| Méthode | Route | Nature | Jeton commun | Rôles nommés admis | Propriétaire | Note |
|---|---|---|---|---|---|---|
| POST | `/ads/activity` | WRITE | **non** | connecteur-publicite | oui | ajout seul par (campagne, jour) ; commandes attribuées = commandes connues du moteur (inconnue ou en conflit : écartée seule, les dépenses du lot sont enregistrées) |
| GET | `/autonomy` | READ | oui | tous | oui |  |
| POST | `/autonomy` | WRITE | **non** | tous les rôles nommés | oui | baisser : tout rôle ; relever : propriétaire |
| GET | `/capital/movements` | READ | oui | tous | oui |  |
| POST | `/capital/movements` | WRITE | **non** | aucun | oui |  |
| GET | `/catalog` | READ | oui | tous | oui |  |
| GET | `/catalog/approvals` | READ | oui | tous | oui |  |
| POST | `/catalog/approvals` | WRITE | **non** | aucun | oui | fiche approuvée, contenu validé, règle de catégorie : propriétaire seule |
| POST | `/catalog/cost-inputs` | WRITE | **non** | finance-pricing | oui | fret, douane, TVA import |
| POST | `/catalog/items` | WRITE | **non** | catalogue | oui | fiches sans champ moteur ni validation humaine (422) |
| POST | `/costs/invoices` | WRITE | **non** | n8n-03-factures | oui | facture fournisseur validée par la propriétaire (workflow 03) : lignes au coût rendu, dette jusqu'au paiement |
| POST | `/costs/invoices/{invoice_ref}/payments` | WRITE | **non** | connecteur-tresorerie | oui | paiement relevé sur le compte (cumul ≤ montant de la facture) : seule baisse de la dette d'une facture |
| POST | `/costs/movements` | WRITE | **non** | finance-pricing | oui | réception adossée à /stock/receive (autre jeton), coût ≤ 2 % d'une référence du moteur (facture enregistrée ou offre) sinon propriétaire ; sortie de vente (ISSUE) : dérivée des commandes ; retour : avoir à lignes ≥ coût des unités retournées et retour physique d'un autre jeton (return:<avoir>) |
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
| POST | `/mandate/check` | WRITE | **non** | acquisition, chef-de-projet, communication, direction-artistique, n8n-08-mandat, operations-sav, site-integrations, sourcing | non | requested_by = rôle du jeton ; relais n8n-08-mandat : requested_by parmi les agents qui dépensent, trésorerie non vérifiable (validation humaine) |
| POST | `/mandate/human-decision` | WRITE | **non** | aucun | oui | validation ou refus d'une dépense en attente (24 h) : seule voie de HUMAN_APPROVED, comptée au stop-loss pub |
| POST | `/mandate/revoke` | WRITE | **non** | tous les rôles nommés | oui | acte protecteur |
| GET | `/northstar` | READ | oui | tous | oui |  |
| POST | `/northstar/entries` | WRITE | **non** | finance-pricing, n8n-02-commandes | oui | rôles : coûts positifs (PAYMENT, SAV, acquisition, charges fixes) ; propriétaire : écriture manuelle ; identifiants order:/refund:/cost: réservés au moteur ; frais d'une commande enregistrée : jamais deux fois |
| POST | `/orders/shipped` | WRITE | **non** | n8n-02-commandes | oui | vente dérivée d'une commande (lignes SKU × quantité), coût transporteur réel ; sortie de stock et coût des ventes dérivés au CMP ; enregistrement atomique ; jamais refusée faute de stock valorisé (coût des ventes en attente, étoile polaire incomplète) ni pour un SKU (ancien SKU d'une clé : rattaché ; inconnu ou ambigu : ligne non rattachée, incomplète) |
| POST | `/orders/{order_id}/lines/resolve` | WRITE | **non** | aucun | oui | rattache une ligne non rattachée (SKU inconnu ou porté par plusieurs clés) à une fiche canonique ; sortie au CMP dérivée ensuite |
| POST | `/orders/{order_id}/refunds` | WRITE | **non** | n8n-02-commandes, operations-sav | oui | avoir sur une commande enregistrée ; lignes = unités retournées (≤ vendues − déjà retournées) |
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
| POST | `/stoploss/state` | WRITE | **non** | aucun | oui | photo déposée (relevé propriétaire) : cash recoupé avec les relevés du connecteur, écart => 409 |
| POST | `/stoploss/state/refresh` | WRITE | **non** | n8n-07-stoploss | oui | photo construite par le moteur depuis ses registres |
| GET | `/stoploss/status` | READ | oui | tous | oui | évalue le stop-loss (verrouillage protecteur possible) |
| GET | `/sync/history` | READ | oui | tous | oui |  |
| POST | `/sync/run` | WRITE | **non** | n8n-01-sync, site-integrations | oui | simulation par défaut ; écriture réelle : porte de gouvernance |
| POST | `/treasury/balance-items` | WRITE | **non** | connecteur-tresorerie, finance-pricing | oui | dettes à date (finance-pricing : hausse seulement) ; créances : propriétaire seule ; plancher : factures enregistrées non payées |
| POST | `/treasury/bank-balance` | WRITE | **non** | connecteur-tresorerie | oui |  |
| POST | `/treasury/paypal-balance` | WRITE | **non** | connecteur-tresorerie | oui |  |

## Rôles

| Rôle (nom du jeton) | Description |
|---|---|
| `chef-de-projet` | Agent 01 — chef de projet (dispatch, revue des exceptions) |
| `sourcing` | Agent 02 — sourcing (fournisseurs, devis) |
| `donnees-fournisseurs` | Agent 03 — données fournisseurs (imports en simulation) |
| `catalogue` | Agent 04 — catalogue (fiches en brouillon, jamais approuvées par lui) |
| `finance-pricing` | Agent 05 — finance et pricing (coûts bornés par une référence du moteur, frais, dettes) |
| `direction-artistique` | Agent 06 — direction artistique |
| `site-integrations` | Agent 07 — site et intégrations (cycles de synchronisation) |
| `seo-redaction` | Agent 08 — SEO et rédaction |
| `communication` | Agent 09 — communication |
| `acquisition` | Agent 10 — acquisition (dépense pub : ne déclare jamais l'activité pub) |
| `operations-sav` | Agent 11 — opérations et SAV (réceptions physiques de stock) |
| `qa-conformite` | Agent 12 — QA et conformité (atteste les tests d'incident, peut geler) |
| `n8n-01-sync` | Workflow n8n 01 — fournisseur vers site (imports, cycles en simulation) |
| `n8n-02-commandes` | Workflow n8n 02 — commandes (frais PSP réels, commandes expédiées) |
| `n8n-03-factures` | Workflow n8n 03 — factures fournisseur validées par la propriétaire (registre, écarts) |
| `n8n-04-incidents` | Workflow n8n 04 — incidents (ouverture, reprise après test attesté) |
| `n8n-05-digest` | Workflow n8n 05 — digest quotidien (lecture) |
| `n8n-06-marketing` | Workflow n8n 06 — automatisations marketing (incidents) |
| `n8n-07-stoploss` | Workflow n8n 07 — demande la photo du stop-loss construite par le moteur, gel |
| `n8n-08-mandat` | Workflow n8n 08 — passerelle du mandat (relais d'un rôle qui dépense : jamais vérifiable) |
| `connecteur-tresorerie` | Connecteur banque et PayPal en lecture seule (soldes, paiements de factures) |
| `connecteur-publicite` | Connecteur de la plateforme publicitaire (dépenses, commandes attribuées) |

## Écritures par rôle

Écritures **propres** à chaque rôle (hors actes ouverts à tout rôle nommé). Tout rôle nommé peut en plus :
POST `/autonomy`, POST `/incidents/{incident_id}/test`, POST `/incidents`, POST `/mandate/revoke`, POST `/stoploss/freeze` (signalement, gel, baisse de niveau, révocation ; test réussi : voir la note).
Propriétaire seule : POST `/capital/movements`, POST `/catalog/approvals`, POST `/fx/rates`, POST `/mandate/human-decision`, POST `/orders/{order_id}/lines/resolve`, POST `/pricing/approvals`, POST `/stoploss/baseline`, POST `/stoploss/capital-memory/reset`, POST `/stoploss/rearm`, POST `/stoploss/state`.

| Rôle (nom du jeton) | Écritures propres |
|---|---|
| `chef-de-projet` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume`, POST `/mandate/check`, POST `/pricing/approvals/{approval_id}/revoke` |
| `sourcing` | POST `/mandate/check` |
| `donnees-fournisseurs` | POST `/imports/{supplier}/run` |
| `catalogue` | POST `/catalog/items` |
| `finance-pricing` | POST `/catalog/cost-inputs`, POST `/costs/movements`, POST `/northstar/entries`, POST `/pricing/approvals/{approval_id}/revoke`, POST `/stock/reorder-proposal`, POST `/treasury/balance-items` |
| `direction-artistique` | POST `/mandate/check` |
| `site-integrations` | POST `/mandate/check`, POST `/sync/run` |
| `seo-redaction` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `communication` | POST `/mandate/check` |
| `acquisition` | POST `/mandate/check` |
| `operations-sav` | POST `/mandate/check`, POST `/orders/{order_id}/refunds`, POST `/stock/receive`, POST `/stock/reorder-proposal` |
| `qa-conformite` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume`, POST `/pricing/approvals/{approval_id}/revoke` |
| `n8n-01-sync` | POST `/imports/{supplier}/run`, POST `/sync/run` |
| `n8n-02-commandes` | POST `/northstar/entries`, POST `/orders/shipped`, POST `/orders/{order_id}/refunds` |
| `n8n-03-factures` | POST `/costs/invoices` |
| `n8n-04-incidents` | POST `/incidents/{incident_id}/close`, POST `/incidents/{incident_id}/resume` |
| `n8n-05-digest` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `n8n-06-marketing` | aucune (lecture, aperçus et actes protecteurs seulement) |
| `n8n-07-stoploss` | POST `/stoploss/state/refresh` |
| `n8n-08-mandat` | POST `/mandate/check` |
| `connecteur-tresorerie` | POST `/costs/invoices/{invoice_ref}/payments`, POST `/treasury/balance-items`, POST `/treasury/bank-balance`, POST `/treasury/paypal-balance` |
| `connecteur-publicite` | POST `/ads/activity` |

## Séparation des rôles (aucune valeur décisive déclarée par son bénéficiaire)

- Activité publicitaire : `connecteur-publicite`, jamais `acquisition` ; dépense retenue par (campagne, jour) =
  MAX(déclaration, paiements pub **engagés** du registre du mandat : approuvés à leur date de décision, exécutés à
  leur date d'exécution) ; registre en ajout seul (baisse refusée) ; demande de dépense pub sans relevé du
  connecteur de moins de 24 h : non vérifiable (validation humaine). Sans connecteur, une pub payée hors du mandat
  (moyen de paiement du compte publicitaire) reste invisible : aucune campagne sans connecteur.
- Fiches : `catalogue` les dépose ; `approved`, `content_validated`, `category_rule_validated` : propriétaire
  (`POST /catalog/approvals`, liée au contenu de la fiche).
- Coûts historiques : `finance-pricing`, réception adossée à `POST /stock/receive` (`operations-sav`, autre jeton),
  coût unitaire à ± 2 % d'une référence du moteur : ligne de la facture enregistrée par `n8n-03-factures` (quantités
  reçues au coût ≤ quantité facturée, lignes ≤ montant dû, fournisseur connu du moteur pour la référence — lien du
  catalogue ou offre rapprochée sur le catalogue du registre ; inconnu : 409), sinon coût rendu de la
  dernière offre évaluée avec des frais posés par la propriétaire (jamais des frais posés par `finance-pricing`,
  jamais un cycle avec catalogue ou frais du corps) ; sans référence ou au-delà : propriétaire ; une réception
  (SKU **à la réception**, bon) n'est valorisée qu'une fois ; écart de facture > 2 % : propriétaire ; retour en stock
  au coût : lignes de l'avoir (unités retournées), avoir ≥ coût des unités retournées et retour physique déclaré par
  `operations-sav` (`return:<avoir>`, jamais cité par une réception au coût).
- Clé produit unique : `product_id` = `listing.product_key` (422 sinon) ; SKU ou handle en double : 409 ; un nouvel
  identifiant ne reprend jamais le SKU ou le handle d'une fiche existante, ni l'identité produit (GTIN, langue, scellé,
  extension, format, contenu) d'une référence en quarantaine, bloquée ou d'état stop-loss inconnu (409, sauf propriétaire).
- Photo du stop-loss : construite par le moteur (`POST /stoploss/state/refresh`) ; photo déposée : propriétaire
  seule, cash recoupé avec les relevés du connecteur ; créances : registre distinct de la propriétaire, jamais effacé
  par une déclaration de dettes ; dettes : registre persisté (plancher valable après un redémarrage) + factures
  enregistrées non payées (paiement relevé par `connecteur-tresorerie`).
- Étoile polaire : ventes, avoirs, coût des ventes et sortie de stock dérivés de commandes enregistrées
  (`POST /orders/shipped` avec lignes, coût transporteur réel ; jamais refusée faute de coût : coût des ventes en
  attente, étoile et photo incomplètes, dépenses en validation humaine ; jamais refusée pour un SKU : ancien SKU
  d'une clé rattaché par l'historique du catalogue, SKU inconnu ou ambigu en ligne non rattachée, rattachée par la
  propriétaire) ; contribution d'une commande attribuée dérivée avec le coût des ventes ; identifiants `order:`/`refund:`/`cost:`/
  `expense:`/`fixed:` réservés au moteur ; frais PSP d'une commande comptés une fois ; écritures manuelles et
  montants négatifs (référencés) : propriétaire.
- Test d'incident réussi : `qa-conformite` (≠ ouvreur, cycle réel lancé par un autre principal ; cycle FICTIF admis
  seulement pour un incident sur données FICTIVES, ou déclaré `simulation: true` alors que le moteur est en
  simulation) ou propriétaire.
- Relais `n8n-08-mandat` : `requested_by` parmi les agents qui dépensent (jamais `qa-conformite`, `catalogue` ni
  `finance-pricing`, qui paie) ; décision humaine d'une dépense en attente : propriétaire (`POST /mandate/human-decision`).

## Validation humaine requise

- [ ] Générer un jeton par rôle (`openssl rand -hex 32`, sur l'ordinateur de la propriétaire :
      `docs/00-pilotage/DELEGATION_AUTONOMIE.md` §10 étape 6), en reporter l'empreinte SHA-256 dans
      `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` de `/etc/pokeshop/api.env` (copie `scp`, contrôle, ajout, `shred -u`) et le
      jeton en clair dans l'identifiant n8n du même nom (jamais dans le dépôt) ; le jeton propriétaire reste hors
      de n8n et des agents.
- [ ] Relire cette matrice avant chaque nouvelle route d'écriture : une route absente est refusée.
