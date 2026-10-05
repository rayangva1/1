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
- **Photo : construite par le moteur ; photo déposée : vous seule.** La matrice d'autorisations (`engine/pokeshop/authz.py`, `docs/08-agents/MATRICE_API.md`) n'ouvre `POST /stoploss/state/refresh` (photo **construite par le moteur** à partir de ses registres, workflow 07) qu'à `n8n-07-stoploss` ; `POST /stoploss/state` (photo **déposée**, entièrement déclarée) est un acte de **la propriétaire seule** (revue R4, R3-NEW-03 : plus aucune photo déclarée par un rôle d'automatisation), et son cash est **recoupé** avec les derniers relevés du connecteur de trésorerie (PayPal + banque) : écart => 409, photo non vérifiable, la précédente reste en vigueur. `/treasury/paypal-balance` et `/treasury/bank-balance` : `connecteur-tresorerie` (ou vous) ; le jeton commun et tout autre rôle reçoivent 403 (journalisé).
- **Dettes et créances : deux registres séparés et persistés (revue R5).** Les **créances** (versements en transit, TVA à récupérer, stock payé en transit) ne comptent dans la photo que si **vous** les relevez (`POST /treasury/balance-items` avec votre jeton et le champ `receivables` **seul**) : un rôle qui en déclare reçoit 403 (une créance déclarée par un agent masquait une perte, revue R3-NEW-02). Elles forment un **registre distinct**, qui reste en vigueur jusqu'à votre prochain relevé de créances (`receivables: []` les retire ; retirez un « stock payé en transit » dès sa réception au coût) : la déclaration quotidienne des dettes de l'agent 05 ne les efface **jamais**, et votre relevé de créances ne touche pas à ses dettes (revue R5, R4-NEW-02 / R4-DOC-01 ; si vous envoyez aussi `preorders_collected_chf` et `debts`, vous remplacez la déclaration des dettes). Les **dettes** ont un **plancher du moteur** : les factures fournisseur **enregistrées** et non payées (`POST /costs/invoices`, workflow 03 après votre validation de l'extraction, jeton `n8n-03-factures`) s'ajoutent toujours aux dettes déclarées, jusqu'au paiement relevé par `connecteur-tresorerie` (`POST /costs/invoices/{réf}/payments`). L'agent finance (`finance-pricing`) déclare les autres dettes (TVA due, remboursements promis) et les précommandes encaissées ; il peut les **relever**, jamais les abaisser (403 : baisse par vous ou par `connecteur-tresorerie`) — **même après un redémarrage** de l'API : dettes et créances sont persistées (journal `balance_statements`) et relues au démarrage. Âge accepté de la déclaration des dettes : **24 h** (`state_max_age_hours`, déclaration quotidienne) ; elle ne vieillit pas la photo, datée du plus ancien relevé de cash (revue R5, R4-DOC-10).
- **Publicité : jamais déclarée par qui dépense.** L'activité pub vient du seul `connecteur-publicite` (`POST /ads/activity`, jamais l'agent 10 `acquisition`), dans un registre en ajout seul (une baisse est refusée, 409) ; la dépense retenue par campagne et par jour est le **MAX** de la déclaration et des paiements publicitaires **engagés** du registre du mandat — approuvés dans le mandat à leur date de décision, **validés par vous** à la date de votre décision **enregistrée au moteur** (`POST /mandate/human-decision`, votre jeton, depuis votre terminal : le formulaire 08 seul ne suffit pas ; revue R5, R4-DOC-03), exécutés à leur date d'exécution (revue R4, R2-NEW-03 : aucune route ne marque encore un paiement « exécuté », ne compter que ceux-là laissait le stop-loss pub aveugle) ; une commande attribuée doit exister au registre des commandes (`POST /orders/shipped`) — sinon elle est **écartée seule** et les dépenses du lot sont enregistrées (revue R5, R4-NEW-01). Sa **contribution** n'est jamais celle que déclare le connecteur : le moteur la **calcule** depuis ses registres à chaque photo (ventes nettes − avoirs − frais − logistique réelle − coût des ventes net de ses sorties et retours) et ne retient la valeur déclarée que si elle est plus basse ; coût des ventes inconnu (en attente, ligne non rattachée) : contribution **0**, commande listée et photo incomplète ; commande remboursée en totalité depuis le relevé : plus payée (revue R6, R5-NEW-01). Une dépense pub approuvée par le mandat sans déclaration du connecteur compte donc quand même. **Limite** : une pub payée par le moyen de paiement du compte publicitaire (hors mandat, B20) n'est vue que par le connecteur — **aucune campagne sans connecteur publicitaire** ; et toute demande de dépense pub sans relevé du connecteur de moins de 24 h part en validation humaine (`TREASURY_UNVERIFIED`).
- **Stock au coût historique : adossé à une réception et borné par une référence que son bénéficiaire ne nourrit jamais.** `POST /costs/movements` (`finance-pricing` seul) n'enregistre une réception que si elle correspond à une réception déclarée par un **autre** jeton (`POST /stock/receive`, `operations-sav` ; la passerelle n8n 06 a un secret remis au seul agent 11), une seule fois par réception physique (**SKU au moment de la réception** et bon, quelle que soit la clé citée ou le SKU actuel de la fiche), et si son **coût unitaire** est à ± 2 % d'une **référence du moteur** (revues R4 et R5, R2-NEW-01 / R3-DOC-02) : **en priorité** la ligne de la facture enregistrée citée (`invoice_ref`, `POST /costs/invoices`, validée par vous dans le formulaire 03), à condition que les unités reçues au coût sur cette ligne ne dépassent pas la **quantité facturée** (un carton de 6 saisi « 1 × carton » puis reçu en 6 unités : 409), que les lignes ne dépassent pas le montant dû et que le fournisseur de la facture soit **connu du moteur** pour la référence (lien fournisseur du catalogue, ou offre rapprochée par un cycle `/sync/run` sur le catalogue du registre, journal persisté ; fournisseur inconnu : 409, fermé par défaut) ; sinon le coût rendu de la dernière offre évaluée par le moteur (`/sync/run`, catalogue et frais **du registre**) **dont les frais ont été posés par vous** (`POST /catalog/cost-inputs` avec votre jeton) — jamais des frais posés par l'agent 05, qui bénéficie de la référence, ni un cycle de simulation avec catalogue ou frais dans le corps (il n'inscrit aucun coût de remplacement, revue R5, R4-DOC-09). Écart > 2 % ou aucune référence : **votre jeton**. Un écart de facture de plus de 2 % exige aussi votre jeton. TVA d'import : ventilée à part sur chaque ligne de facture (`import_vat_unit_chf`) et comptée au coût selon le profil TVA du moteur (méthode effective : récupérable, hors coût ; revue R5, R4-DOC-02). La sortie de stock d'une vente est **dérivée** des lignes de la commande expédiée (`POST /orders/shipped`) au CMP, jamais déclarée ; une commande payée n'est **jamais refusée** faute de coût : le coût des ventes reste **en attente** (étoile polaire et photo signalées incomplètes, toute dépense en validation humaine) et est dérivé dès l'inscription du coût de réception (revue R5, R4-NEW-01). Un **retour** ne remet des unités en stock au coût qu'avec les lignes de l'avoir (unités retournées) **et** la réception physique du retour par `operations-sav` (`POST /stock/receive`, ref `return:<avoir>`, jamais citée par une réception au coût d'une facture), avec un avoir au moins égal au **coût** des unités retournées (sinon geste commercial ou décote : votre jeton) : un geste commercial ne remet rien en stock, et la paire avoir + retour ne relève jamais l'étoile polaire (revue R5, R3-NEW-05). Un poste de la photo déposé par le rôle qui demande la dépense la rend non vérifiée (`TREASURY_UNVERIFIED`).
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
| Créances | Versements PSP en transit, TVA à récupérer, stock payé en transit (au coût) — **relevées par vous seule** (votre jeton, registre distinct jamais effacé par une déclaration de dettes) ; une créance déclarée par un rôle est refusée (403) |
| Dettes | Factures fournisseur **enregistrées** non payées (plancher du moteur, `POST /costs/invoices`, jusqu'au paiement relevé) + précommandes encaissées non livrées, TVA due, remboursements promis (déclarés par l'agent finance, hausse seulement, plancher persisté au redémarrage ; déclaration acceptée jusqu'à 24 h) |
| Perte | Capital engagé − valeur nette |

**Publicité.** Le CAC compte la dépense de la campagne sur la fenêtre, divisée par ses commandes payées nettes (contribution de chacune calculée par le moteur, §1) ; la comparaison se fait sur les totaux (dépense > contribution), sans arrondi intermédiaire. Une commande sans attribution ne compte pour aucune campagne (prudent).

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
| 4. Réarmement | **Vous**, depuis un canal direct (terminal ou formulaire authentifié), jamais via le chat | Lire `rearm_reference` dans `GET /stoploss/status`, puis `POST /stoploss/rearm` avec `X-Pokeshop-Owner-Token` (ce seul en-tête suffit, lecture comprise : aucun jeton d'API requis en plus), corps `{"reason": "…", "rebase": true, "reference_chf": "<rearm_reference.net_worth_chf>", "photo_sha256": "<rearm_reference.photo_sha256>"}` (en Python : `StopLossEngine.rearm(jeton, motif, now=…, state=…, attested_reference_chf=…)`) ; sans `reference_chf`, la réponse 409 redonne `rearm_reference` (valeur nette, date et empreinte de la photo) à attester ; un jeton erroné ou une référence non conforme est refusé et la tentative journalisée (sans le jeton) |
| 5. Reprise | Vous | L'autonomie **reste au niveau 1** ; la remonter est une décision distincte, après recette (BP §13) |

**Réarmement « rebasé » (par défaut).** La référence devient la valeur nette au moment du réarmement. Exemple 8 du §4 : réarmement à 5 940 CHF ⇒ nouveau seuil 20 % × 5 940 = 1 188 CHF ⇒ nouveau gel si la valeur nette tombe à 4 752 CHF ou moins (sans nouvel apport). Un apport ultérieur de 1 000 CHF porte la référence à 6 940 CHF.
**Réarmement sans rebase** (`rebase=False`) : la référence reste les apports cumulés ; si la perte dépasse toujours 20 %, le gel revient dès l'évaluation suivante.
Une valeur nette ≤ 0 interdit le réarmement : un apport de capital est requis avant.

**Point zéro après le lancement (décision à prendre avant l'ouverture).** Au sens littéral (capital = apports), les investissements de lancement comptent comme une perte. Avec le budget du BP §3 (8 000 CHF apportés), dépenser site, DA, administration et emballages (2 900 CHF non récupérables) donne déjà une perte de **2 900 CHF ≥ 1 600 CHF** ; après l'achat du stock pilote (3 000 CHF, valorisé prudemment à 2 100 CHF), la perte atteint **3 800 CHF**. Le gel global se déclencherait donc **avant la première vente**. Proposition : vous **décidez** un **point zéro à J3**, avec la décision de budget (C03), puis vous le **posez avec la première photo, en un seul acte** (`POST /stoploss/baseline` avec votre jeton, corps `{"reason": "…", "reference_chf": "4200", "with_photo": true}` : le moteur construit la photo depuis ses registres, et la photo et le point zéro sont acceptés **atomiquement** ; en Python `StopLossEngine.set_baseline`, journalisé) **dès la mise en service de l'API** (B23), **avant d'activer le workflow 07** et toute dépense autonome, au plus tard avant le niveau 2 (C14). Une première photo acceptée **sans** point zéro appliquerait la définition littérale et gèlerait tout ; un point zéro déjà posé : 409 (passer par le réarmement). Sans `with_photo`, la route exige une photo déjà acceptée (sinon 409). La pose ne peut donc pas avoir lieu à J3. Ordre exact (`INTERVENTIONS_HUMAINES.md` C19, B25, B26) :

1. API en service (pile interne lancée à J8 avec B27, mise en service complète à J26 avec B23) avec votre jeton (B21) et les jetons des rôles `n8n-07-stoploss`, `connecteur-tresorerie` et `finance-pricing` (B22), workflow 07 **encore inactif** ;
2. vos apports enregistrés par **vous** (`POST /capital/movements`, votre jeton : seule source du capital, B25) ;
3. soldes banque et PayPal de moins de 24 h déposés par **vous** avec votre jeton (commandes ci-dessous) — ou, connecteurs recettés, par une exécution manuelle de la seule branche « relevés » de 07 (jeton `connecteur-tresorerie`, B26), 07 restant **inactif** jusqu'à l'étape 5 — et dettes déclarées par l'agent 05 (`POST /treasury/balance-items`, jeton nommé `finance-pricing`, `preorders_collected_chf` et `debts`, listes vides attestées s'il n'y en a pas), créances par vous (votre jeton, même route, champ `receivables` **seul** : registre distinct que la déclaration de l'agent 05 n'efface pas) ;
4. pose du point zéro **avec la première photo** (`POST /stoploss/baseline`, votre jeton, `with_photo: true`), J27 visé (BL-191) : `GET /stoploss/status` montre la photo acceptée et le point zéro ;
5. activation du workflow 07 (`POST /stoploss/state/refresh` toutes les heures) — **jamais avant l'étape 4**, même pour un essai manuel (`orchestration/README.md` §5 et §7).

Commandes prêtes pour les étapes 3 et 4 (vérifiées le 5.10.2026 contre l'API lancée avec la configuration de B27, sans jeton commun : 200, 200, 200 ; inversées — photo de 07 avant le point zéro —, gel global puis 409 sur le point zéro). À lancer **sur le serveur** (l'API n'écoute que sur 127.0.0.1:8000 ; depuis votre ordinateur : `ssh -L 8000:127.0.0.1:8000 <serveur>` dans un autre terminal). Votre jeton est saisi sans écho et passé à `curl` par un descripteur, jamais en argument ni dans l'historique ; remplacer les dates (moins de 24 h, jamais dans le futur) et les montants par ceux de vos relevés du jour :

```bash
read -rs OWNER_TOKEN                                   # votre jeton (B21), sans écho
api() { curl -sS --fail-with-body -X "$1" "http://127.0.0.1:8000$2" -H 'Content-Type: application/json' \
          -H @<(printf 'X-Pokeshop-Owner-Token: %s\n' "$OWNER_TOKEN") ${3:+-d "$3"}; echo; }
api POST /treasury/bank-balance   '{"as_of": "AAAA-MM-JJT08:00:00+01:00", "balance_chf": "5800.00", "source": "relevé e-banking du jour (propriétaire)"}'
api POST /treasury/paypal-balance '{"as_of": "AAAA-MM-JJT08:00:00+01:00", "balance_chf": "200.00", "source": "relevé PayPal du jour (propriétaire)"}'
api GET  /stoploss/status                              # avant C19 : aucune photo, aucun gel
api POST /stoploss/baseline '{"reason": "point zéro option A décidé à J3 (C03)", "reference_chf": "4200", "with_photo": true}'
api GET  /stoploss/status                              # photo acceptée, point zéro posé, global_frozen false
unset OWNER_TOKEN
```

Un 409 « photo d'activité impossible » nomme la source manquante (`manquantes`) : apports (B25), soldes, ou déclaration des dettes de l'agent 05 (BL-190) ; la compléter puis relancer la même commande.

Les deux options :

| Option | Quand | Référence | Effet |
|---|---|---|---|
| A (recommandée) | Décision à J3, avec la décision de budget (C03) ; pose dès la mise en service de l'API, après vos apports et les soldes, avec la première photo (`with_photo`, J27 visé) | `reference_chf` = apports − investissements de lancement assumés = 8 000 − 2 900 − 900 de décote = 4 200 CHF | Le lancement réalisé comme prévu ne déclenche rien ; un lancement qui coûte 840 CHF de plus que prévu déclenche le gel |
| B | Décision à J3 ; pose à l'ouverture (photo acceptée du jour) | Valeur nette constatée (ex. 2 100 de cash + 2 100 de stock prudent = 4 200 CHF) | Même seuil, mais le gel peut partir pendant le lancement : il faudra alors réarmer (rebasé) |

Dans les deux cas : seuil 20 % × 4 200 = **840 CHF** ⇒ gel si la valeur nette tombe à **3 360 CHF** ou moins. Sans point zéro, la définition littérale s'applique.

**Persistance.** L'état du verrou (`engine.latch`, point zéro compris) et le journal (`engine.journal`, append-only) sont écrits **avant d'être appliqués** dans un journal d'état en ajout seul chaîné sha256 (table `pokeshop.engine_state_journal`, migration 004, si `POKESHOP_DATABASE_URL` est fourni ; sinon `<POKESHOP_STATE_DIR>/stoploss.jsonl`), avec la dernière photo **acceptée** (une photo refusée ne remplace jamais la valide), puis relus au démarrage de l'API (`Services.build`) : un redémarrage ne lève jamais un gel enregistré. **Limite** (revue R6, RS-16) : un superutilisateur de la base qui désactive les triggers peut supprimer les **dernières** lignes d'un flux sans que la chaîne sha256 le voie ; si elles portent le gel, il est levé au redémarrage. D'où l'accès superutilisateur réservé à la propriétaire, une flotte jamais membre du groupe `docker` (B28) et les sauvegardes comparées à leur manifeste (`db/README.md`). Un journal illisible démarre le service gelé (cause `RESTORE_FAILED`, aucun réarmement possible) jusqu'à réparation du stockage et redémarrage. Si l'écriture échoue en cours de route, un gel s'applique quand même (le service répond 503) ; un réarmement ou un point zéro non enregistré n'est jamais appliqué. Le verrou mémorise aussi les **apports déjà constatés** (une photo qui en omet est refusée) et le journal des photos l'**acteur déduit du jeton** qui les a déposées. Une configuration modifiée sans signature ferme selon son empreinte (revue R6, R5C-DOC-09) : **règles de prix** différentes de leur empreinte, ou écart entre deux sources d'une même règle (`consistency_errors`) => service démarré **gelé** (cause `CONFIG_UNSIGNED`, jamais enregistrée, aucun réarmement possible) jusqu'à signature ou correction puis redémarrage ; **seuils du stop-loss** différents de leur empreinte => stop-loss **non chargé** (routes du stop-loss en 503, écritures réelles refusées `STOPLOSS_UNAVAILABLE`, aucune dépense : plus strict qu'un gel) ; **mandat** différent de son empreinte => mandat **inactif** (`MANDATE_FINGERPRINT_MISMATCH`, aucune dépense sans vous, pas de gel). Ces deux gels de démarrage ne sont **jamais écrits**, même quand une photo est déposée et évaluée pendant le gel : chaque ligne du journal porte le verrou **enregistré** (`engine.persisted_latch`), le gel de démarrage n'existe qu'en mémoire ; en revanche un dépassement réel du seuil ou un gel manuel survenus pendant ce temps sont enregistrés et survivent à la réparation.

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
