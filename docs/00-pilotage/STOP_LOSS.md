# Stop-loss — six niveaux — {{NOM_BOUTIQUE}}

> **Statut : seuils = hypothèses à confirmer par la propriétaire** (modèle d'opération du 4.10.2026, BP §1, §3, §5, §9, §13).
> Seuils versionnés : `config/stoploss.v1.yaml` (`stoploss-v1-2026-10-04`). Calcul : `engine/pokeshop/stoploss.py`.
> Mandat de dépense : `docs/00-pilotage/DELEGATION_AUTONOMIE.md`. Métrique unique : `docs/00-pilotage/ETOILE_POLAIRE.md`.

## 1. Principe

- Les stop-loss **priment** sur tout planning, gate ou demande. Aucun agent ne lève ni ne contourne un stop-loss.
- Le calcul est **déterministe** (Decimal, aucune IA dans la décision) et **daté** : une photo de l'activité de plus de 24 h, ou datée du futur, est refusée (il faut recalculer avant de décider).
- Une même règle n'a **qu'une valeur** dans le dépôt : planchers produit = planchers durs de `config/pricing_rules.v1.yaml` ; 25 % = `extension_budget_cap` ; 1 600 CHF = `pokeshop.treasury.CASH_STOPLOSS_RESERVE` = réserve du mandat ; 20 % = part de la projection (`pokeshop.forecast.GLOBAL_STOPLOSS_PCT`) ; budget stock du mandat signé = budget stock des règles. Un test échoue si ces valeurs divergent, et **l'API démarre gelée** (`CONFIG_UNSIGNED`) si elle constate un écart (`consistency_errors`).
- **Plafond jour pub et budget stock ne sont jamais lus dans la photo postée** : l'API les remplace par ceux du mandat signé actif (sans mandat actif : aucun plafond, toute dépense pub du jour coupe les campagnes) et le plus petit des budgets stock (mandat, règles). La réponse de `POST /stoploss/state` liste les valeurs remplacées (`overridden`).
- **Apports et retraits : votre registre seulement.** Les mouvements de capital du stop-loss global viennent **uniquement** de `POST /capital/movements` (votre jeton, registre en ajout seul) ; une photo qui déclare des `capital_movements` est refusée (422) et l'API lit votre registre à la date de la photo. Un faux retrait ne peut donc plus réduire le capital de référence ni taire le gel.
- **Photo et relevés de trésorerie : jeton du rôle, refus par défaut.** La matrice d'autorisations (`engine/pokeshop/authz.py`, `docs/08-agents/MATRICE_API.md`) n'ouvre `POST /stoploss/state` et `/stoploss/state/refresh` qu'à `n8n-07-stoploss`, `/treasury/paypal-balance` et `/treasury/bank-balance` qu'à `connecteur-tresorerie`, `/treasury/balance-items` qu'à `finance-pricing` et `connecteur-tresorerie` ; le jeton commun et tout autre rôle reçoivent 403 (journalisé). Le workflow 07 utilise `POST /stoploss/state/refresh` (photo construite par le moteur à partir de ses registres).
- **Publicité : jamais déclarée par qui dépense.** L'activité pub vient du seul `connecteur-publicite` (`POST /ads/activity`, jamais l'agent 10 `acquisition`), dans un registre en ajout seul (une baisse est refusée, 409) ; la dépense retenue par campagne et par jour est le **MAX** de la déclaration et des paiements publicitaires **exécutés** du registre du mandat ; une commande attribuée doit exister au registre des commandes (`POST /orders/shipped`). Une dépense pub exécutée sans déclaration compte donc quand même.
- **Stock au coût historique : adossé à une réception.** `POST /costs/movements` (`finance-pricing` seul) n'enregistre une réception que si elle correspond à une réception déclarée par un **autre** jeton (`POST /stock/receive`, `operations-sav`) et à une facture ; un écart de facture de plus de 2 % exige votre jeton. Un poste de la photo déposé par le rôle qui demande la dépense la rend non vérifiée (`TREASURY_UNVERIFIED`).
- **Seuils signés par vous** : `config/stoploss.v1.yaml` porte une empreinte (`python -m pokeshop.stoploss fingerprint`) que vous seule reportez dans le coffre (`POKESHOP_STOPLOSS_FINGERPRINT`). Empreinte du coffre différente du fichier (fichier modifié par un agent ou pointé ailleurs par `POKESHOP_STOPLOSS_PATH`) : le stop-loss **n'est pas chargé**, toute écriture et toute dépense sont refusées. Aucune empreinte au coffre : chaque seuil vaut **le plus strict** entre le fichier et la référence du code (`REFERENCE_THRESHOLDS`, BP) — éditer le fichier sans signature ne peut que durcir. Même règle pour les seuils de prix (`POKESHOP_RULES_FINGERPRINT`, planchers 12 % / 8 CHF, 5 %/jour, 25 %, budget 3 000 CHF…).
- Le moteur **déclenche** ; les workflows **appliquent** (blocage de la vente, panier de réassort, coupure de campagne, refus des dépenses).

## 2. Les six niveaux

| Niveau | Déclencheur exact (borne) | Action | Appliqué par | Levée |
|---|---|---|---|---|
| **Produit** | Contribution **< 12 %** du CA net, **ou < 8 CHF** par commande (12,00 % et 8,00 CHF = conforme). Petit produit : 12 % seulement, 8 CHF contrôlés au panier | `BLOCK_SALE` : vente et promo bloquées | Moteur de prix, publication, agent 12 | Automatique dès qu'une nouvelle décision de prix est conforme ; sinon exception écrite (C18) |
| **Extension** | Exposition (stock au coût + achats engagés non reçus) **> 25 %** du budget stock (750 CHF sur 3 000 ; 750,00 = conforme), **ou ≥ 45 jours** sans vente (depuis la dernière vente, à défaut depuis l'entrée en stock) | `NO_REORDER` + `PROPOSE_MARKDOWN` (proposition à valider) | `propose_reorder(blocked_extensions=…)`, mandat de dépense | Vous : démarque acceptée ou exception de plafond (C18) |
| **Publicité** | Sur les **7 derniers jours civils** (Zurich, aujourd'hui compris) : CAC **>** contribution moyenne avant acquisition des commandes **payées nettes d'annulations et de remboursements** ; sans commande nette : dépense ≥ 20 CHF. **Ou** dépense du jour **≥** plafond jour du mandat (mandat non signé : toute dépense) | `CUT_CAMPAIGN` (une campagne, ou toutes : périmètre `*`) | Agent 10, plateforme, mandat | Vous : nouveau plan de test. Le plafond jour se rouvre le lendemain |
| **Trésorerie** | Cash disponible (banque + PayPal − précommandes encaissées non livrées) **< 1 600 CHF** (1 600,00 = conforme) | `FREEZE_PURCHASES_AND_ADS` : plus d'achat de stock, d'accessoire, d'échantillon ni de pub (y compris le rejeu d'une approbation antérieure). Étiquettes et emballages des commandes payées restent possibles | Mandat de dépense, réassort | Automatique quand le cash repasse au-dessus ; achat : vous |
| **Global** | Perte de **valeur nette** **≥ 20 %** du capital engagé de référence (exactement 20 % = déclenché ; définition unique au §3). Photo sans apport, apports en baisse ou capital ≤ 0 : **non évaluable, refusée** | `FREEZE_ALL` : **tout gelé**, autonomie ramenée au **niveau 1**, alerte. Non évaluable : toute écriture et toute dépense refusées | Tous les workflows, mandat (refus de toute dépense) | **Propriétaire uniquement**, avec jeton (§5). Jamais automatique |
| **Temps** | **≥ 60 jours** après l'ouverture des ventes (ou la dernière décision « continuer ») sans les seuils de validation du BP §1 : 30 commandes payées nettes, contribution après pub > 0, zéro survente, ≥ 50 % du stock pilote écoulé en valeur de coût. Avant l'ouverture : 60 jours après le premier apport | `DECISION_REPORT` : dossier continuer / ajuster / arrêter (un déclencheur par seuil manqué) | Agent 01 (dossier), C16 | Vous : décision au dossier ; « continuer » ouvre une nouvelle fenêtre de 60 jours |

## 3. Définitions précises

**Global — définition unique.** C'est la seule définition du stop-loss global du projet (moteur, mandat, tableau de bord, étoile polaire, projections) : **perte = capital engagé de référence − valeur nette ; gel si perte ≥ 20 % × capital engagé de référence**. Avec le point zéro recommandé (§5, option A : 4 200 CHF), le seuil vaut **840 CHF**. Toute mention d'un gel « à −1 600 CHF de contribution nette cumulée » (ancienne approximation des livrables finance) est caduque : la projection `pokeshop.forecast.north_star` n'en est qu'une approximation et applique **par défaut** `capital_engaged=BP_STOPLOSS_REFERENCE` (4 200 CHF ⇒ 840 CHF ; au rythme du jalon BP §1, gel projeté en semaine 13, pas 28) ; le classeur `docs/03-finance/modele_financier.xlsx` (Hypothèses B44 à B46) suit la même référence.

| Terme | Définition |
|---|---|
| Capital engagé | Apports cumulés de la propriétaire − retraits, **lus dans votre registre** (`POST /capital/movements`, votre jeton), jamais dans une photo. Après un point zéro ou un réarmement « rebasé » : valeur de référence + apports ultérieurs − retraits ultérieurs |
| Données manquantes (fermé par défaut) | Photo **sans aucun apport** (et sans point zéro), apports **inférieurs** à ceux déjà constatés (mémoire persistée dans le verrou) ou au point zéro, capital de référence ≤ 0 : la photo est **refusée** (409), le stop-loss est non évaluable, toute écriture non protectrice et toute dépense sont refusées. Correction d'un apport erroné : vous seule réinitialisez la mémoire (`POST /stoploss/capital-memory/reset`, votre jeton, journalisé) |
| Valeur nette | Cash (banque + PayPal, précommandes comprises) + stock + créances − dettes |
| Stock | Ligne par ligne : **min(coût historique, valeur de liquidation prudente)**. Sans estimation : 70 % du coût historique (hypothèse, `default_liquidation_ratio`) |
| Créances | Versements PSP en transit, TVA à récupérer, stock payé en transit (au coût) |
| Dettes | Précommandes encaissées non livrées, factures fournisseurs reçues non payées, TVA due, remboursements promis |
| Perte | Capital engagé − valeur nette |

**Publicité.** Le CAC compte la dépense de la campagne sur la fenêtre, divisée par ses commandes payées nettes ; la comparaison se fait sur les totaux (dépense > contribution), sans arrondi intermédiaire. Une commande sans attribution ne compte pour aucune campagne (prudent).

**Temps.** « Contribution après pub » = ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition, sur la fenêtre (`NorthStarLedger.totals`). « Écoulé en valeur de coût » = coût historique des unités du stock pilote vendues, nettes de retours ÷ coût du stock pilote.

## 4. Exemples chiffrés (FICTIFS)

Paramètres BP §4 (r = 2,5 %, b = 0,30, L = 3, R = 1, A = 5, t = 8,1 %), budget stock 3 000 CHF, capital 8 000 CHF. Chiffres calculés par le moteur.

| # | Situation | Calcul | Résultat |
|---|---|---|---|
| 1 | Display FICTIF, coût 140 CHF, vendu 199,90 CHF | Contribution 30,62 CHF ; 16,56 % | Conforme |
| 2 | Même display en promo −10 % : 179,90 CHF | 12,62 CHF ; **7,58 %** < 12 % | **Promo bloquée** (`BLOCK_SALE`) |
| 3 | Extension FICTIF : stock 700 CHF + réassort de 80 CHF engagé | 780 > 750 | **Plus de réassort** + démarque proposée |
| 4 | Extension FICTIF : 300 CHF en stock, dernière vente il y a 45 jours | 45 ≥ 45 | **Plus de réassort** + démarque proposée |
| 5 | Campagne FICTIF : 6 × 20 = 120 CHF sur 7 jours ; 5 commandes payées dont 1 remboursée ; 19,33 CHF de contribution par commande | CAC = 120 / 4 = **30,00** > 19,33 | **Campagne coupée** |
| 6 | Plafond jour 33 CHF ; deux campagnes à 19 + 14 CHF aujourd'hui | 33 ≥ 33 | **Toutes les campagnes coupées** jusqu'à demain |
| 7 | Cash disponible 1 599,99 CHF | < 1 600 | **Plus d'achat ni de pub** |
| 8 | Cash 4 000 ; stock au coût 2 800 sans estimation (prudent : 1 960) ; PSP en transit 250 ; précommandes 180 et TVA 90 | Valeur nette = 4 000 + 1 960 + 250 − 270 = 5 940 ; perte = 2 060 ≥ 1 600 | **Gel global** (au coût, la perte n'aurait été que de 1 220 : la valorisation prudente évite de masquer la perte) |
| 9 | J+60 : 22 commandes, contribution après pub +85 CHF, 0 survente, 1 230 CHF écoulés sur 3 000 | 22 < 30 ; 41 % < 50 % | **2 dossiers** (commandes, écoulement) → décision continuer / ajuster / arrêter |

## 5. Gel global verrouillé et réarmement

**Le gel est verrouillé.** Une fois déclenché, il persiste à chaque évaluation, même si la valeur nette remonte, jusqu'au réarmement par la propriétaire. Un agent peut **geler** à tout moment par précaution (`StopLossEngine.freeze`, journalisé) ; seule la propriétaire **réarme**.

**Mise en place (une fois, ≈ 5 minutes, par vous)**

1. Générer un jeton long et le ranger dans votre gestionnaire de mots de passe :
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Calculer son empreinte (le jeton est saisi au clavier, il n'apparaît pas dans l'historique) :
   ```bash
   cd engine && python -c "from pokeshop.stoploss import hash_owner_token; print(hash_owner_token(input()))"
   ```
3. Placer l'empreinte dans le coffre, variable `POKESHOP_OWNER_TOKEN_SHA256`. Ne jamais donner le jeton à un agent ni le coller dans un chat.

Sans empreinte configurée, **aucun réarmement n'est possible** (sécurité par défaut).

**Procédure de réarmement**

| Étape | Qui | Contenu |
|---|---|---|
| 1. Alerte | Moteur → agent 01 → vous | Rapport `render_report` : perte, valeur nette, cause |
| 2. Dossier | Agent 01 (+ 05, 12) | Valeur nette détaillée, causes, options chiffrées : arrêter, ajuster, apport de capital |
| 3. Décision | **Vous** | Motif écrit (obligatoire) |
| 4. Réarmement | **Vous**, depuis un canal direct (terminal ou formulaire authentifié), jamais via le chat | Lire `rearm_reference` dans `GET /stoploss/status`, puis `POST /stoploss/rearm` avec `X-Pokeshop-Owner-Token`, corps `{"reason": "…", "rebase": true, "reference_chf": "<rearm_reference.net_worth_chf>", "photo_sha256": "<rearm_reference.photo_sha256>"}` (en Python : `StopLossEngine.rearm(jeton, motif, now=…, state=…, attested_reference_chf=…)`) ; sans `reference_chf`, la réponse 409 redonne `rearm_reference` (valeur nette, date et empreinte de la photo) à attester ; un jeton erroné ou une référence non conforme est refusé et la tentative journalisée (sans le jeton) |
| 5. Reprise | Vous | L'autonomie **reste au niveau 1** ; la remonter est une décision distincte, après recette (BP §13) |

**Réarmement « rebasé » (par défaut).** La référence devient la valeur nette au moment du réarmement. Exemple 8 du §4 : réarmement à 5 940 CHF ⇒ nouveau seuil 20 % × 5 940 = 1 188 CHF ⇒ nouveau gel si la valeur nette tombe à 4 752 CHF ou moins (sans nouvel apport). Un apport ultérieur de 1 000 CHF porte la référence à 6 940 CHF.
**Réarmement sans rebase** (`rebase=False`) : la référence reste les apports cumulés ; si la perte dépasse toujours 20 %, le gel revient dès l'évaluation suivante.
Une valeur nette ≤ 0 interdit le réarmement : un apport de capital est requis avant.

**Point zéro après le lancement (décision à prendre avant l'ouverture).** Au sens littéral (capital = apports), les investissements de lancement comptent comme une perte. Avec le budget du BP §3 (8 000 CHF apportés), dépenser site, DA, administration et emballages (2 900 CHF non récupérables) donne déjà une perte de **2 900 CHF ≥ 1 600 CHF** ; après l'achat du stock pilote (3 000 CHF, valorisé prudemment à 2 100 CHF), la perte atteint **3 800 CHF**. Le gel global se déclencherait donc **avant la première vente**. Proposition : vous **décidez** un **point zéro à J3**, avec la décision de budget (C03), puis vous le **posez avec la première photo, en un seul acte** (`POST /stoploss/baseline` avec votre jeton, corps `{"reason": "…", "reference_chf": "4200", "with_photo": true}` : le moteur construit la photo depuis ses registres, et la photo et le point zéro sont acceptés **atomiquement** ; en Python `StopLossEngine.set_baseline`, journalisé) **dès la mise en service de l'API** (B23), **avant d'activer le workflow 07** et toute dépense autonome, au plus tard avant le niveau 2 (C14). Une première photo acceptée **sans** point zéro appliquerait la définition littérale et gèlerait tout ; un point zéro déjà posé : 409 (passer par le réarmement). Sans `with_photo`, la route exige une photo déjà acceptée (sinon 409). La pose ne peut donc pas avoir lieu à J3. Ordre exact (`INTERVENTIONS_HUMAINES.md` C19, B25, B26) :

1. API en service (pile interne lancée à J8 avec B27, mise en service complète à J26 avec B23) avec votre jeton (B21) et les jetons des rôles `n8n-07-stoploss`, `connecteur-tresorerie` et `finance-pricing` (B22), workflow 07 **encore inactif** ;
2. vos apports enregistrés par **vous** (`POST /capital/movements`, votre jeton : seule source du capital, B25) ;
3. soldes banque et PayPal de moins de 24 h déposés par le connecteur en lecture seule (`POST /treasury/bank-balance`, `POST /treasury/paypal-balance`, jeton `connecteur-tresorerie`, B26) et dettes et créances déclarées par l'agent 05 (`POST /treasury/balance-items`, jeton nommé `finance-pricing`) ;
4. pose du point zéro **avec la première photo** (`POST /stoploss/baseline`, votre jeton, `with_photo: true`), J27 visé (BL-191) : `GET /stoploss/status` montre la photo acceptée et le point zéro ;
5. activation du workflow 07 (`POST /stoploss/state/refresh` toutes les heures).

Les deux options :

| Option | Quand | Référence | Effet |
|---|---|---|---|
| A (recommandée) | Décision à J3, avec la décision de budget (C03) ; pose dès la mise en service de l'API, après vos apports et les soldes, avec la première photo (`with_photo`, J27 visé) | `reference_chf` = apports − investissements de lancement assumés = 8 000 − 2 900 − 900 de décote = 4 200 CHF | Le lancement réalisé comme prévu ne déclenche rien ; un lancement qui coûte 840 CHF de plus que prévu déclenche le gel |
| B | Décision à J3 ; pose à l'ouverture (photo acceptée du jour) | Valeur nette constatée (ex. 2 100 de cash + 2 100 de stock prudent = 4 200 CHF) | Même seuil, mais le gel peut partir pendant le lancement : il faudra alors réarmer (rebasé) |

Dans les deux cas : seuil 20 % × 4 200 = **840 CHF** ⇒ gel si la valeur nette tombe à **3 360 CHF** ou moins. Sans point zéro, la définition littérale s'applique.

**Persistance.** L'état du verrou (`engine.latch`, point zéro compris) et le journal (`engine.journal`, append-only) sont écrits **avant d'être appliqués** dans un journal d'état en ajout seul chaîné sha256 (table `pokeshop.engine_state_journal`, migration 004, si `POKESHOP_DATABASE_URL` est fourni ; sinon `<POKESHOP_STATE_DIR>/stoploss.jsonl`), avec la dernière photo **acceptée** (une photo refusée ne remplace jamais la valide), puis relus au démarrage de l'API (`Services.build`) : un redémarrage ne lève jamais un gel. Un journal illisible démarre le service gelé (cause `RESTORE_FAILED`, aucun réarmement possible) jusqu'à réparation du stockage et redémarrage. Si l'écriture échoue en cours de route, un gel s'applique quand même (le service répond 503) ; un réarmement ou un point zéro non enregistré n'est jamais appliqué. Le verrou mémorise aussi les **apports déjà constatés** (une photo qui en omet est refusée) et le journal des photos l'**acteur déduit du jeton** qui les a déposées. Une configuration modifiée sans signature ou incohérente démarre aussi le service gelé (cause `CONFIG_UNSIGNED`, jamais enregistrée, aucun réarmement possible) jusqu'à signature ou correction puis redémarrage. Ces deux gels de démarrage ne sont **jamais écrits**, même quand une photo est déposée et évaluée pendant le gel : chaque ligne du journal porte le verrou **enregistré** (`engine.persisted_latch`), le gel de démarrage n'existe qu'en mémoire ; en revanche un dépassement réel du seuil ou un gel manuel survenus pendant ce temps sont enregistrés et survivent à la réparation.

## 6. Branchements

| Consommateur | Utilisation |
|---|---|
| Mandat de dépense (`pokeshop.mandate.check`) | Reçoit `StopLossStatus` : gel global ⇒ tout refusé ; trésorerie ⇒ stock, accessoires, échantillons et pub refusés ; extension, produit, campagne ⇒ refus ciblés. La fraîcheur (60 min) se juge sur la **date de la photo** (`state_as_of`), pas sur l'heure d'évaluation. La trésorerie du mandat (cash, exposition par extension) vient de cette même photo acceptée |
| Réassort (`pokeshop.stock.propose_reorder`) | `blocked_extensions = status.no_reorder_extensions`, `blocked_products = status.blocked_products`, `cash_reserve_chf = 1 600` |
| Publication et promotions | `ProductMargin.from_decision(…)` pour chaque prix et chaque promo ; `BLOCK_SALE` ⇒ pas de publication |
| Trésorerie 13 semaines (`pokeshop.treasury`) | Projection du stop-loss cash sur 13 semaines (même convention : < 1 600) |
| Projection (`pokeshop.forecast.north_star`) | Approximation du gel global sur la contribution cumulée projetée, avec par défaut `capital_engaged=BP_STOPLOSS_REFERENCE` (point zéro, seuil 840 CHF) ; **le stop-loss réel est celui de ce module** (valeur nette, définition unique du §3) |

```python
from pokeshop.stoploss import StopLossEngine, load_stoploss_config

config = load_stoploss_config()                   # signature vérifiée (coffre) ou seuils les plus stricts
engine = StopLossEngine.restore(config, store=journal)  # journal d'état « stoploss » relu (§5)
engine.validate_photo(state, now)                 # dépôt : refus d'une photo sans apport ou incomplète
triggers = engine.evaluate(state, now)            # liste triée, le plus grave d'abord
status = engine.status(triggers, as_of=now, autonomy_level=current_level, state_as_of=state.as_of)
```

## 7. Ce que les stop-loss ne font pas

- Ils ne **relancent** rien : une campagne coupée, une extension gelée ou un produit bloqué ne repart que sur décision.
- Ils ne **démarquent** pas : la démarque est une proposition, et une démarque sous le plancher produit reste bloquée.
- Ils ne remplacent ni la fiduciaire (valeur fiscale du stock), ni l'inventaire physique (A08).

## Validation humaine requise

- [ ] Confirmer chaque seuil de `config/stoploss.v1.yaml` (12 %, 8 CHF, 25 %, 45 j, 7 jours glissants, 1 600 CHF, 20 % du capital engagé, 60 j), ou demander une version `stoploss.v2.yaml`.
- [ ] **Signer les seuils** : `cd engine && python -m pokeshop.stoploss fingerprint ../config/stoploss.v1.yaml`, puis reporter l'empreinte dans le coffre (`POKESHOP_STOPLOSS_FINGERPRINT`) ; idem pour les règles de prix (`rules-fingerprint`, `POKESHOP_RULES_FINGERPRINT`). Sans signature, les valeurs les plus strictes s'appliquent ; toute modification ultérieure exige une nouvelle signature.
- [ ] Valider les deux hypothèses propres à la gouvernance : coupure d'une campagne sans commande dès 20 CHF dépensés sur 7 jours ; stock sans estimation valorisé à 70 % de son coût.
- [ ] Valider la définition du capital engagé (apports − retraits) et la liste des créances et dettes du §3.
- [ ] Générer votre jeton de réarmement et placer son empreinte dans le coffre (§5).
- [ ] Choisir la règle par défaut du réarmement : rebasé (proposé) ou non.
- [ ] Décider du **point zéro** à J3 avec C03 (§5, option A recommandée), puis le **poser avec la première photo** (`POST /stoploss/baseline`, votre jeton, `with_photo: true`) dès la mise en service de l'API (B23), après l'enregistrement de vos apports (`POST /capital/movements`) et des soldes, **avant d'activer le workflow 07**, avant toute dépense autonome et au plus tard avant C14 : sans lui, le gel global se déclenche dès que 1 600 CHF de coûts de lancement non récupérables sont dépensés.
- [ ] Valider le dossier « temps » avant ouverture : 60 jours après le premier apport (hypothèse).
