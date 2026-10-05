# Orchestration n8n — {{NOM_BOUTIQUE}}

> Version du 5.10.2026, agent « orchestration-dashboard ». Sources : BP §5 (synchronisation), §9 (automatisations marketing), §12 (workflows et tableau de bord), §13 (niveaux d'autonomie) ; `docs/00-pilotage/STOP_LOSS.md`, `DELEGATION_AUTONOMIE.md`, `ETOILE_POLAIRE.md` ; `docs/07-ops/SOP_INCIDENTS.md`, `ROUTINES_PILOTAGE.md` ; `docs/06-contenu/EMAILS/README.md`.
> **Statut : prêt à importer, rien d'actif.** Les 8 workflows arrivent **inactifs**, toutes les écritures externes **désactivées**, le moteur appelé **en simulation**. Aucun compte, aucune boutique, aucun envoi n'existe au 5.10.2026.
> Révision F4 (revue adverse, 5.10.2026) : clé canonique par workflow (suspensions effectives), photo du stop-loss construite par le moteur (07), alerte au **changement** (07), catalogue et frais lus dans le moteur et cycle « propre » seulement s'il évalue une offre (01), stock amont sans réévaluation des prix (01), liens des emails implémentés et confirmation de désinscription **après** traitement (06), trésorerie jamais envoyée par 08.

## 1. Les huit workflows

| Fichier | Déclencheur | Ce qu'il fait | Appels du moteur (actifs) | Écritures externes (désactivées) | Niveau d'activation |
|---|---|---|---|---|---|
| `n8n/01_fournisseur_vers_site.json` | Toutes les 6 h (prix, offres) ; toutes les 45 min (stock amont : **import seul**, aucun prix réévalué) | Import en simulation, cycle fournisseur → site **dry-run** sur le catalogue validé et les frais **enregistrés dans le moteur**, incident de flux INC-03 | `GET /incidents`, `POST /imports/{fournisseur}/run`, `POST /sync/run` (`dry_run: true`), `POST /incidents` | Lecture du flux fournisseur, dépôt du fichier | 1 (simulation) ; écriture réelle : décision C14 |
| `n8n/02_commande_vers_livraison.json` | Shopify `orders/paid` ; chaque jour ouvré 07:30 ; lundi 06:30 | Contrôle doublon (idempotence), anomalies (CHF, Suisse, payée), bon de préparation, **tâche colis HUMAINE**, colis en retard, rapprochement des frais PSP réels | `POST /incidents`, `POST /northstar/entries` | Réservation (route moteur attendue), emails à la responsable, lectures Shopify | 2 |
| `n8n/03_facture_vers_marge_reelle.json` | Passerelle agent 05 (`/webhook/pokeshop-facture`) | Contrôles déterministes en centimes, **validation humaine** de l'extraction (formulaire 72 h), écarts > 2 % | `POST /incidents` | Enregistrement du coût historique (route attendue), emails | 1 (contrôles) |
| `n8n/04_incident.json` | Moteur (`/webhook/pokeshop-incidents`) ; passerelle (`/webhook/pokeshop-incident-reprise`) ; **Error Trigger** | Notification cause + action (S1 immédiat, S2 dans l'heure, S3 digest) ; reprise après **lecture** du test enregistré (par l'agent 12 QA avec son jeton nommé, ou la propriétaire) et validation ; incident pour toute exécution en échec, **sur la clé canonique du workflow en échec** (sa suspension l'arrête vraiment) | `POST /incidents`, `GET /incidents`, `POST /incidents/{id}/resume` | Emails, Slack | **1, en premier** |
| `n8n/05_digest_quotidien.json` | Chaque jour 07:45 | Digest : **1. étoile polaire** (`GET /northstar`), **2. stop-loss** (avec l'avertissement « alertes temps réel inactives » tant que le moteur simule ses notifications), puis KPI du jour, cycles de synchronisation propres et décisions attendues | `GET /northstar`, `GET /stoploss/status`, `GET /dashboard/daily`, `GET /sync/history`, `GET /health` | Email, Slack | 1 |
| `n8n/06_marketing_automations.json` | Passerelle agent 11 (réception contrôlée) ; Shopify `orders/fulfilled`, `fulfillment_events/create`, `customers/update` ; **liens des emails** (`alertes-desinscrire`, `avis-refus`, `alertes-preferences`, `alertes-confirmer`) | Réception en stock local puis alerte « nouveau stock local » aux inscrits consentants (**garde-fous** : incident ouvert, stock sous le seuil, marge insuffisante, gel), suivi d'expédition, demande d'avis J+7, **désinscription et refus d'avis propagés, page affichée après traitement**, préférences, double opt-in | `POST /stock/receive`, `GET /incidents`, `GET /stoploss/status`, `POST /stock/sellable`, `POST /incidents` | Outil d'emailing, Shopify | Liens des emails : dès l'outil d'emailing ; envois : 3 |
| `n8n/07_stoploss_watch.json` | Toutes les heures (:10) ; relevés de trésorerie (:05, déclencheur désactivé) | **Photo d'activité construite par le moteur** à partir de ses registres, puis si l'état **change** : **gel via API**, coupure des campagnes, **notification immédiate** (cause, chiffres, action, comment réarmer) ; relevés des soldes PayPal et banque | `POST /stoploss/state/refresh`, `GET /stoploss/status`, `POST /stoploss/freeze` (jeton `n8n-07-stoploss`) ; `POST /treasury/paypal-balance`, `POST /treasury/bank-balance` (jeton `connecteur-tresorerie`) | Lectures PayPal et banque, plateforme publicitaire, email, Slack | 1, juste après 04 |
| `n8n/08_mandat_depenses.json` | Passerelle agents (`/webhook/pokeshop-depense`) | `POST /mandate/check` (sans trésorerie : le moteur lit ses registres) → APPROVED (préparer, journaliser) / NEEDS_HUMAN_APPROVAL (**validation 1 clic**, formulaire 24 h) / REJECTED ; contrôle impossible ou dépenses suspendues = refus | `GET /incidents`, `POST /mandate/check` (`record: true`) | Paiement PayPal, emails, routes d'exécution attendues | 1 (contrôle) ; exécution : mandat signé + recette |

Les exports sont générés par `orchestration/build_workflows.py` (source unique, identifiants stables) : ne pas les éditer à la main, modifier le générateur puis `python orchestration/build_workflows.py`.

## 2. Garde-fous intégrés

| Garde-fou | Comment |
|---|---|
| Rien ne tourne à l'import | `active: false` ; un déclencheur Shopify ne s'inscrit chez Shopify qu'à l'activation |
| Aucune écriture externe | Emails, Slack, PayPal, Shopify (écriture et lecture), outil d'emailing, plateforme publicitaire, flux fournisseur : nœuds **désactivés** (n8n laisse alors passer les données sans rien envoyer) |
| Simulation | `POST /sync/run` avec `dry_run: true` explicite ; le nœud « Paramètres » porte `simulation = true` (incidents tracés « [SIMULATION] », sans confinement) |
| Aucun secret dans un export | Identifiants **par référence** (`credentials: {id, name}`) ; jamais d'en-tête en clair ; `$env` non utilisé (bloqué par défaut en n8n 2.x) |
| Données personnelles | 02 et 06 ne conservent pas les exécutions réussies ; la commande est normalisée sans nom, adresse ni email ; journal de désinscription sans adresse |
| Montants | Calculs en centimes entiers dans les nœuds Code (aucun `parseFloat`) ; le moteur reste seul juge (Decimal) |
| Idempotence | Doublons Shopify écartés (« Remove Duplicates » sur l'identifiant de commande) ; écritures de l'étoile polaire et du mandat idempotentes par clé |
| Statu quo sûr | Formulaire sans réponse dans le délai (24 h dépense, 48 h reprise, 72 h facture) = branche « non » |
| Clé canonique | Une seule clé par workflow (`fournisseur-site`, `commande-livraison`, `facture-marge`, `incident`, `digest`, `marketing`, `stoploss-watch`, `mandat-depenses`) : nœud « Paramètres », incidents ouverts par n8n et par 04 (table identifiant/nom → clé générée au build), moteur (`pokeshop.api.WORKFLOW_KEYS`, `fournisseur-site` = clé des incidents du cycle de synchronisation) |
| Suspension | 01, 06 (envois) et 08 lisent `GET /incidents` : workflow suspendu = rien ne part ; 06 et 08 s'arrêtent aussi sur suspension globale (`*`) ; le moteur refuse lui-même `/mandate/check` (423) si « mandat-depenses » est suspendu |
| Stop-loss | 07 fait **construire la photo par le moteur** (registres), gèle et notifie **à chaque changement d'état** (empreinte mémorisée, un état qui revient est re-signalé) ; 06 coupe une campagne si stock vendable < seuil, référence sous stop-loss produit, gel global ou stop-loss non évaluable ; **aucun workflow ne réarme** |
| Liens des emails | Réponse **après** les appels aux outils et un bilan honnête (outil non branché, erreur ou réponse non conforme = non confirmé) ; non confirmé = incident S2 (traitement manuel) ; lien invalide = page d'erreur 400 + incident S2, jamais ignoré en silence. Hors simulation, ces incidents suspendent les envois marketing (clé « marketing ») jusqu'à la reprise : des liens cassés ou un outil en panne empêcheraient d'honorer les oppositions (fermé par défaut, y compris face à des liens forgés) |
| Erreurs | Le workflow d'erreur de 01-03 et 05-08 est 04 (Error Trigger) : toute exécution en échec ouvre un incident |

## 3. Prérequis

- [ ] L'API du moteur tourne (`scripts/compose.sh up -d db db-migrate db-backup api n8n`, ou `uvicorn pokeshop.api:create_app --factory` en local) avec les empreintes des jetons par rôle `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` configurées (sinon 503).
- [ ] n8n tourne (service `n8n` de la même commande `scripts/compose.sh`). **Version testée : n8n 2.41.6** (import, exécution, webhooks, formulaire ; §10). Épingler cette version dans `N8N_IMAGE` après votre propre test.
- [ ] **Authentification : un jeton par rôle, refus par défaut.** Chaque route du moteur déclare les rôles admis dans la matrice versionnée `engine/pokeshop/authz.py` (table : `docs/08-agents/MATRICE_API.md`) ; une route absente est refusée. n8n n'utilise **jamais** le jeton commun (lecture et aperçus seulement : toute écriture lui répond 403) ni le jeton propriétaire : chaque workflow a son credential nommé du rôle de son jeton (§4), dont l'empreinte est dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` (ex. `n8n-01-sync` → `POKESHOP_ROLE_TOKEN_SHA256_N8N_01_SYNC`). Les credentials ne sont que des **références** dans les exports ; les jetons en clair ne vivent que dans n8n (chiffrés par `N8N_ENCRYPTION_KEY`) et au coffre.
- [ ] Séparation des rôles : la photo du stop-loss est construite par `n8n-07-stoploss`, les soldes relevés par `connecteur-tresorerie`, la dépense demandée par un autre rôle (`n8n-08-mandat` n'est qu'un relais : trésorerie toujours non vérifiée, validation humaine) ; la réception physique (06, passerelle `pokeshop-stock-recu`) est déclarée avec le jeton `operations-sav`.
- [ ] Jeton de l'agent 12 QA (`qa-conformite`, hors n8n) : lui seul (ou la propriétaire) enregistre un test de correction **réussi** (`POST /incidents/{id}/test`), avec un `test_ref` = `run_id` d'un cycle `/sync/run` **PROPRE** en simulation, catalogue du registre, postérieur à l'ouverture, **lancé par un autre principal** (ex. `n8n-01-sync`), sur le fournisseur et la référence de l'incident ; tout autre jeton reçoit 403. La passerelle de 04 (`n8n-04-incidents`) ne fait que **lire** ce test, puis reprend un incident non critique.
- [ ] Moteur alimenté : fiches (`POST /catalog/items`, jeton `catalogue`) **validées par la propriétaire** (`POST /catalog/approvals`, son jeton) et frais par fournisseur (`POST /catalog/cost-inputs`, jeton `finance-pricing`), taux de change du jour par la propriétaire (`POST /fx/rates`, **seule source de taux** : aucun `fx_*` accepté ailleurs, 422) ; apports et retraits de capital par la propriétaire (`POST /capital/movements`, son jeton, **seule source** : une photo qui déclare des `capital_movements` est refusée, 422) ; dettes et créances déclarées chaque jour par l'agent finance avec son jeton `finance-pricing` (`POST /treasury/balance-items` : précommandes encaissées non livrées, factures non payées, TVA due, versements en transit ; listes vides **attestées** s'il n'y en a pas) ; sinon 01 répond 409 « catalogue requis » et 07 « sources manquantes ». La photo est datée de sa source **la plus ancienne** : le stop-loss l'accepte jusqu'à 24 h, mais une dépense n'est approuvée sans vous que si relevés et déclaration ont moins d'une heure (fraîcheur du mandat).
- [ ] Pour les déclencheurs Shopify, les liens des emails et les formulaires : une **URL publique HTTPS** de n8n (`N8N_WEBHOOK_URL` dans le fichier de variables **hors du dépôt** `/etc/pokeshop/api.env`, lu par `scripts/compose.sh`, transmise à n8n comme `WEBHOOK_URL` par le compose) — n8n est exposé en HTTPS public **dès J8 (B27)**, avant la landing (webhook d'inscription et liens des emails seulement), puis pour les webhooks Shopify et les formulaires à J26 (B23) ; le compose publie n8n sur 127.0.0.1, le proxy inverse limite les chemins exposés (§11).
- [ ] Moteur : `POKESHOP_NOTIFY_DRY_RUN=false` (valeur de `.env.example` et du compose) : les incidents partent vers 04 ; `true` les simule (alertes temps réel inactives, signalé par `/health` et le digest).

## 4. Créer les identifiants (credentials) — avant l'import

Dans n8n : **Credentials → Create credential**, avec **exactement** ces noms (n8n rattache les nœuds par identifiant ; si le rattachement échoue, on choisit le credential du même nom dans chaque nœud signalé en rouge).

| Nom exact | Type n8n | Contenu | Utilisé par | Quand |
|---|---|---|---|---|
| `Pokeshop API — jeton nommé n8n-01-sync` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-01-sync` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_01_SYNC`) | 01 (import, cycle `/sync/run`, incidents) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-02-commandes` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-02-commandes` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_02_COMMANDES`) | 02 (commandes expédiées, avoirs, étoile polaire) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-03-factures` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-03-factures` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_03_FACTURES`) | 03 (factures, incidents) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-04-incidents` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-04-incidents` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_04_INCIDENTS`) | 04 (lecture du test, reprise et clôture d'un incident non critique) | Dès J8 (B27, 04 actif avant la landing) |
| `Pokeshop API — jeton nommé n8n-05-digest` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-05-digest` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_05_DIGEST`) | 05 (lectures du digest) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-06-marketing` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-06-marketing` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_06_MARKETING`) | 06 (stock vendable, incidents des liens des emails) | Dès J8 (B27) |
| `Pokeshop API — jeton nommé operations-sav` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `operations-sav` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_OPERATIONS_SAV`) | 06 (passerelle `pokeshop-stock-recu` : réception contrôlée) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-07-stoploss` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-07-stoploss` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS`) | 07 (photo `/stoploss/state/refresh`, gel) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé connecteur-tresorerie` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `connecteur-tresorerie` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_CONNECTEUR_TRESORERIE`) | 07 (relevés de soldes PayPal et banque, désactivés) | Dès le niveau 1 |
| `Pokeshop API — jeton nommé n8n-08-mandat` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton du rôle `n8n-08-mandat` (empreinte : `POKESHOP_ROLE_TOKEN_SHA256_N8N_08_MANDAT`) | 08 (relais `POST /mandate/check`, révocation) | Dès le niveau 1 |
| `Passerelle agents — X-Pokeshop-Gateway` | Header Auth | Name `X-Pokeshop-Gateway`, Value = secret aléatoire (coffre), donné aux seuls agents | Webhooks 03, 04 (reprise), 06 (réception), 08 | Dès J8 (04 et 06 actifs) |
| `Formulaires propriétaire — Basic Auth` | Basic Auth | Utilisateur et mot de passe connus de la **propriétaire seule** | Formulaires de validation (03, 04, 08) | Dès le niveau 1 |
| `SMTP boîte des agents` | SMTP | Serveur, port, compte de la boîte dédiée aux agents | Emails à la responsable | Après test d'envoi |
| `Slack alertes propriétaire` | Slack API | Jeton du canal d'alerte (facultatif) | 04, 05, 07 | Si ce canal est choisi |
| `Shopify Admin — app personnalisée` | Shopify Access Token API | Sous-domaine, jeton d'accès, **clé secrète de l'app** (vérification HMAC des webhooks) | Déclencheurs et lectures Shopify (02, 06) | Niveau 2 |
| `Outil d'emailing — jeton API` | Header Auth | Selon l'outil retenu (B04) | 06 | Avec l'outil d'emailing |
| `Plateforme publicitaire — jeton API` | Header Auth | Selon la plateforme (CONN-PUB) | 07 (coupure) | Après recette du connecteur |
| `PayPal compte dédié — OAuth2 client credentials` | OAuth2 API (grant « Client Credentials ») | Client ID / secret de l'app du compte PayPal dédié ; URL du jeton à reprendre de la documentation PayPal | 08 (paiement) | Mandat signé + recette CONN-PAYPAL |
| `Flux fournisseur — accès autorisé` | Header Auth | Selon l'accès écrit du fournisseur | 01 | Accès fournisseur obtenu |
| `Banque — relevé de solde (lecture seule)` | Header Auth | Selon le connecteur bancaire retenu (lecture seule du compte de l'activité) | 07 (relevés) | Connecteur choisi et recetté |

## 5. Importer pas à pas (sans code)

**Par l'interface n8n**

1. Ouvrir n8n (`http://127.0.0.1:5678`), créer le compte propriétaire n8n.
2. Créer les credentials du §4 (au minimum les dix credentials « Pokeshop API — jeton nommé … », la passerelle et le Basic Auth).
3. **Workflows → Create workflow → menu « … » → Import from File…** : importer `04_incident.json` en premier, puis 07, 05, 08, 01, 03, 02, 06 (un workflow par import). Enregistrer. **Ne pas renommer les workflows** : le workflow d'erreur 04 retrouve la clé canonique d'un workflow en échec par son identifiant, à défaut par son nom (sinon l'incident ne suspend pas le bon workflow).
4. Dans chaque workflow, ouvrir le nœud **« Paramètres »** (ou « Paramètres — … ») : vérifier `api_base_url` (docker compose : `http://api:8000`), remplacer `responsable_email`, laisser `simulation = true`.
5. Ouvrir chaque nœud marqué en rouge (credential introuvable) et choisir le credential du même nom.
6. **Workflow settings → Error workflow** : choisir « Pokeshop 04 — Incidents et erreurs » pour 01, 02, 03, 05, 06, 07, 08 (l'import par l'interface peut changer les identifiants).
7. Tester : bouton **Execute workflow** sur 05, puis 07, puis 01 ; lire le résultat de chaque nœud (aucun email ne part : nœuds désactivés).
8. Activer selon le §7 : n8n 2.x → bouton **Publish** ; n8n 1.x → interrupteur **Active**.

**Par la ligne de commande** — le compose monte `./orchestration/n8n` en lecture seule sur `/workflows` ; toujours passer par `scripts/compose.sh` (un `docker compose` nu n'a pas le fichier de variables et échoue sur la première variable obligatoire) :

```bash
scripts/compose.sh exec n8n n8n import:workflow --separate --input=/workflows
scripts/compose.sh exec n8n n8n publish:workflow --id=pkshp04Incidents   # n8n 2.x ; puis scripts/compose.sh restart n8n
```

Les identifiants des workflows sont conservés : le workflow d'erreur (04) est déjà relié. Pour relier aussi les credentials sans clic, créer une table `{clé: id}` (ids lus dans l'URL de chaque credential, **aucun secret**) puis :

```bash
python orchestration/build_workflows.py --credentials-map ids.json --out /chemin/hors-depot
```

Clés : `api_01` à `api_06` et `api_08` (credential du rôle de chaque workflow), `api_stock` (`operations-sav`, passerelle de réception de 06), `api_photo` (`n8n-07-stoploss`), `api_tresorerie` (`connecteur-tresorerie`), `gateway`, `owner_form`, `smtp`, `slack`, `shopify`, `emailing`, `ads`, `paypal`, `supplier`, `bank`.

## 6. Nœuds désactivés : quand les activer

| Workflow | Nœud | Condition d'activation |
|---|---|---|
| 01 | Récupérer le flux autorisé ; Déposer le fichier | Accès **écrit** du fournisseur (API, fichier fourni ou export approuvé) ; volume `imports` du compose monté sur `/data/imports` (n8n en écriture, API en lecture, `N8N_RESTRICT_FILE_ACCESS_TO=/data/imports` déjà câblé) : `POKESHOP_IMPORTS_DIR=/data/imports` côté moteur, et donner le dossier à l'utilisateur `node` (`scripts/compose.sh run --rm --no-deps --user root --entrypoint chown n8n node:node /data/imports`) |
| 01 | Alerter la responsable (email) | Credential SMTP testé |
| 02 | Réserver le stock local — route moteur attendue | Route `POST /orders/paid` livrée par l'agent integrations et recettée |
| 02 | Tâche colis HUMAINE, Colis en retard, Résumé du rapprochement (emails) | Credential SMTP testé |
| 02 | Lectures Shopify (commandes, versements) | Credential Shopify (niveau 2) ; champs GraphQL 2026-10 revérifiés |
| 03 | Enregistrer le coût historique — route moteur attendue | Route `POST /costs/invoices` livrée et recettée |
| 04, 05, 07 | Emails et Slack à la propriétaire | Canal choisi (SOP_INCIDENTS §1) et testé ; permis dès le niveau 1 (information de la seule propriétaire) |
| 06 | Inscrits, envois 04 et 11 (outil d'emailing) | Outil choisi (B04), notes juristes C2-C4, **liens des emails actifs d'abord**, niveau 3 |
| 06 | Liens des emails : désinscription, refus d'avis, préférences, confirmation (outil d'emailing, Shopify) | En même temps que l'outil d'emailing, **avant tout envoi** ; contrat de réponse de chaque nœud (ex. `{ unsubscribed: true, shopify_customer_id }`) adapté à l'outil ; mutations Shopify validées par l'agent integrations ; adresse de support (`REMPLACER-email-support@exemple.invalid`) remplacée |
| 07 | Relevés de trésorerie (déclencheur :05, lecture PayPal, connecteur bancaire) | Recette CONN-PAYPAL (scope de lecture des soldes) et connecteur bancaire en lecture seule ; sans eux, la photo du stop-loss reste « non évaluable » (fermé par défaut) |
| 07 | Couper les campagnes | Recette du connecteur publicitaire ; action protectrice (niveau 1 admis) |
| 08 | Exécuter le paiement PayPal ; Marquer exécuté ; Enregistrer la validation / le refus | Mandat **signé** (B01) et empreinte au coffre ; recette CONN-PAYPAL ; routes `POST /mandate/executed` et `POST /mandate/human-decision` livrées |

## 7. Ordre d'activation par niveau d'autonomie (BP §13)

**J8, avant la landing (B27, BL-186, BL-187) — pile interne, seuls l'inscription et les liens des emails sont publics**
- [ ] Pile lancée par `scripts/compose.sh up -d db db-migrate db-backup api n8n` (README « Démarrage ») : base et API en simulation, internes (127.0.0.1, réseau du compose) ; le proxy HTTPS n'expose que le webhook d'inscription et les chemins `alertes-confirmer`, `alertes-preferences`, `alertes-desinscrire`, `avis-refus`.
- [ ] Credentials : `Pokeshop API — jeton nommé n8n-04-incidents`, `… n8n-06-marketing`, `SMTP boîte des agents` (boîte B02), `Passerelle agents — X-Pokeshop-Gateway`, outil d'emailing (B04) ; ouvrir chaque nœud marqué en rouge (§5).
- [ ] 04 importé et activé **en premier**, avec ses emails à la propriétaire (`responsable_email`, nœuds email de 04 activés, dont « Alerte : moteur injoignable ») ; vérifier qu'un incident FICTIF (`POST /incidents`, jeton `n8n-06-marketing`, `simulation: true`) arrive par email.
- [ ] Workflow d'inscription (BL-187) : workflow d'erreur = 04, aucune exécution conservée ; 06 activé pour les seuls liens des emails, ses trois déclencheurs Shopify **désactivés** jusqu'au niveau 2 (ils s'inscriraient chez Shopify à l'activation). Les incidents de ces chemins partent vers l'API interne (`n8n-06-marketing`).

**Niveau 1 — tout en simulation et brouillons** (workflows 01 à 08, à partir de la mise en service de J26, B23)
- [ ] 04 Incidents (premier : c'est le workflow d'erreur de tous les autres). Côté moteur : `POKESHOP_NOTIFY_DRY_RUN=false` (défaut documenté ; avec `true`, aucune notification n'est envoyée à 04), puis ouvrir un incident FICTIF (`POST /incidents`, `simulation: true`) et vérifier qu'il arrive dans 04 ; `GET /health` → `notifications.real_time_alerts: true`.
- [ ] 07 Surveillance du stop-loss (photo construite par le moteur, gel par API actif ; relevés de trésorerie et coupure publicitaire désactivés jusqu'à recette des connecteurs).
- [ ] 05 Digest quotidien (activer l'email après le test SMTP : il ne va qu'à la responsable).
- [ ] 08 Mandat de dépense (contrôle et validation 1 clic ; aucun paiement exécuté).
- [ ] 01 Fournisseur vers site en **dry-run**, après l'enregistrement du catalogue validé et des frais dans le moteur. Critère de recette BP §13 : **20 cycles PROPRES consécutifs** lus dans `GET /sync/history` (`consecutive_clean_runs`, persistant). Ne comptent que des cycles **réels** : PROPRES (aucune erreur critique et au moins une offre au coût rendu complet), sur des données **non FICTIVES** (fournisseur et catalogue), avec le catalogue du **registre** du moteur (jamais fourni dans le corps), une source fournisseur **datée**, et **une seule fois par livraison** (même contenu ou même horodatage de source rejoué : ignoré). Un cycle VIDE ou non admissible est ignoré ; une anomalie sur données réelles remet à zéro. Chaque cycle de `runs` porte `counted_for_acceptance` et `acceptance_exclusion` (motif).
- [ ] 03 Facture vers marge réelle (contrôles et validation ; enregistrement quand la route existe).

**Niveau 2 — prix et stock des références approuvées synchronisés dans des seuils** (décision C14 de la propriétaire)
- [ ] 02 Commande vers livraison (l'activation inscrit le webhook `orders/paid` chez Shopify).
- [ ] 01 en écriture réelle : `dry_run: false` dans le nœud « Cycle fournisseur vers site » **et** `POKESHOP_DRY_RUN=false` côté moteur ; la porte de gouvernance vérifie encore le niveau, le stop-loss et le mandat.

**Niveau 3 — nouveaux produits publiés, campagnes selon règles**
- [ ] 06 envois (alerte stock local, demande d'avis) — liens des emails (désinscription, refus d'avis, préférences, confirmation) déjà actifs et recettés.
- [ ] 07 coupure publicitaire automatique (si pas déjà fait).

**Niveau 4 — réassorts automatiques avec budgets, allocations et trésorerie contrôlés**
- [ ] 08 exécution PayPal dans le mandat ; réassort automatique (route moteur à créer).

**Incident critique** : le moteur rétablit le niveau précédent et refuse les écritures du niveau perdu ; désactiver aussi dans n8n les nœuds d'écriture de ce niveau jusqu'à la nouvelle recette.

## 8. Valeurs à régler

| Où | Valeur | Défaut | Source |
|---|---|---|---|
| Nœuds « Paramètres » | `api_base_url` | `http://api:8000` | docker-compose.yml |
| Nœuds « Paramètres » | `simulation` | `true` | SPEC §0.6 |
| Nœuds « Paramètres » | `responsable_email` | `REMPLACER-responsable@exemple.invalid` | à remplir |
| 01 « Paramètres » | `fournisseurs` (fournisseur + fichier) | 3 fournisseurs FICTIFS de `data/samples` | remplacer par les flux réels autorisés |
| 02 « Paramètres » | `delai_expedition_jours_ouvres` | 3 | hypothèse `DELAI_EXPEDITION` (`docs/04-legal/champs_a_remplir.yaml`) |
| 06 « Paramètres — alertes stock » | `seuil_stock_alerte` | 3 unités | **hypothèse** à valider |
| 06 « Attendre 7 jours » | délai de la demande d'avis | 7 jours | hypothèse EMAILS §6 |
| 05 déclencheur | heure du digest | 07:45 | `HEURE_DIGEST` à valider |
| 06 pages de retour | `https://REMPLACER-URL-LANDING.exemple.invalid/desinscription.html`, `…/inscription-confirmee.html` | — | `URL_LANDING` |
| 06 pages d'erreur et de préférences | `REMPLACER-email-support@exemple.invalid` | — | `EMAIL_SUPPORT` |
| 06 outil d'emailing | `https://REMPLACER-outil-emailing.exemple.invalid/api/…` | — | outil retenu (B04) |
| Nœuds Shopify | `https://REMPLACER-boutique.myshopify.com/admin/api/2026-10/graphql.json` | — | domaine de la boutique (B15) |
| Variables n8n (compose) | `WEBHOOK_URL` (depuis `N8N_WEBHOOK_URL` de `/etc/pokeshop/api.env`, hors du dépôt), `N8N_ENCRYPTION_KEY`, `GENERIC_TIMEZONE=Europe/Zurich`, `N8N_RESTRICT_FILE_ACCESS_TO=/data/imports` | câblées dans `docker-compose.yml` ; n8n ne reçoit **aucun** jeton du moteur ni mot de passe de base | coffre (B03) |

Ne pas désactiver le blocage de `$env` (`N8N_BLOCK_ENV_ACCESS_IN_NODE`, vrai par défaut en n8n 2.x) : aucun workflow n'en a besoin.

## 9. Contrat avec le moteur

| Route | Workflow | État au 5.10.2026 |
|---|---|---|
| `GET /incidents`, `POST /incidents`, `POST /incidents/{id}/resume` | 01, 02, 03, 04, 06, 08 | Existe |
| `POST /incidents/{id}/test` | agent 12 QA (`qa-conformite`, ≠ ouvreur) ou propriétaire ; **jamais** la passerelle n8n pour un test réussi | Existe : test réussi = cycle `/sync/run` PROPRE du journal persisté, catalogue du registre, lancé par un autre principal, sur le fournisseur et la référence de l'incident ; autre rôle, ouvreur ou jeton commun : 403 ; test échoué : tout rôle nommé |
| `POST /imports/{supplier}/run`, `POST /sync/run` | 01 | Existe (simulation ; sans catalogue : 409 ; `clean` = cycle PROPRE ; `cost_inputs` du corps sans aucun `fx_*` (422) et en simulation seulement (écriture réelle : 409)) |
| `POST /catalog/items`, `POST /catalog/cost-inputs`, `GET /catalog` | agents `catalogue` et `finance-pricing` (pas de workflow) | Existe : registre persisté lu par `/sync/run` ; validations humaines, identifiants Shopify et prix publié refusés (422) ; taux de change jamais déclarés ici (`POST /fx/rates`, propriétaire) |
| `POST /catalog/approvals`, `GET /catalog/approvals` | propriétaire (écriture, son jeton) ; jamais n8n | Existe : validations humaines liées au contenu de la fiche, lues par `/sync/run` |
| `GET /sync/history` | 05 ; gate 3.6 | Existe : cycles persistés, `consecutive_clean_runs` (cycles réels et distincts seulement), `counted_run_ids`, motif d'exclusion par cycle |
| `GET /northstar`, `POST /northstar/entries` | 02 (`n8n-02-commandes` : montants positifs de paiement, SAV, acquisition, frais fixes), 05 (lecture) | Existe : ventes, avoirs et montants négatifs réservés à la propriétaire |
| `POST /orders/shipped`, `POST /orders/{order_id}/refunds` | 02 (`n8n-02-commandes`) ; avoirs : aussi agent 11 | Existe : seule source des ventes et avoirs de l'étoile polaire ; coût transporteur **réel** (> 0) et référence d'étiquette exigés ; nœud de 02 à câbler sur l'étiquette réelle |
| `POST /stoploss/state/refresh` | 07 | Existe : photo construite par le moteur (apports, soldes, dettes et créances déclarées, stock au coût, catalogue, prix, publicité) ; source manquante ou périmée : 409 |
| `POST /treasury/balance-items` | agent finance (`finance-pricing`) ou `connecteur-tresorerie`, chaque jour | Existe : dettes et créances à date, jamais supposées nulles ; précommandes encaissées déduites du cash disponible ; jeton commun : 403 |
| `POST /stoploss/state` | aucun workflow (07 utilise `/refresh`) ; `n8n-07-stoploss` seulement | Existe : photo déposée, **sans** `capital_movements` (422), apports lus au registre de la propriétaire ; jeton commun : 403 |
| `GET /stoploss/status`, `POST /stoploss/freeze` | 05, 06, 07 | Existe |
| `POST /treasury/paypal-balance`, `POST /treasury/bank-balance` | 07 (relevés, désactivés ; jeton `connecteur-tresorerie`) | Existe (acteur déduit du jeton ; jeton commun : 403 ; relevé plus ancien que l'actuel refusé) |
| `POST /capital/movements` | propriétaire (son jeton), jamais n8n | Existe : apports et retraits en ajout seul ; **seule** source des mouvements de capital du stop-loss |
| `POST /ads/activity` | connecteur publicitaire (à construire, jeton `connecteur-publicite`, jamais `acquisition`) | Existe : dépenses pub (registre en ajout seul) et commandes attribuées (existantes au registre des commandes) ; photo : MAX(déclaration, paiements pub exécutés du mandat) |
| `POST /stock/receive`, `POST /stock/sellable` | 06 (réception contrôlée : jeton `operations-sav` ; stock vendable : `n8n-06-marketing`) | Existe |
| `POST /mandate/check` | 08 (`n8n-08-mandat`, relais : trésorerie non vérifiée) | Existe (423 si « mandat-depenses » ou toutes les écritures sont suspendues hors gel) |
| `GET /dashboard/daily`, `GET /health` | 05 | Existe (tableau de bord : jeton commun ou de rôle, lecture seule ; journal non relu => KPI « indisponible », jamais zéro) |
| `POST /orders/paid` (réservation, survente INC-06, ventes nettes de l'étoile polaire) | 02 | **Attendue** (nœud désactivé) |
| `POST /costs/invoices` (ventilation, coût historique, écarts) | 03 | **Attendue** |
| `POST /mandate/executed`, `POST /mandate/human-decision` (registre du mandat) | 08 | **Attendue** |
| En-tête secret sur le webhook d'incident du moteur | 04 | **Attendu** (le moteur n'envoie aucun en-tête : webhook limité au réseau interne docker) |

`tests/test_n8n_workflows.py` échoue si un nœud actif appelle une route qui n'existe pas, ou si un nœud « route moteur attendue » reste désactivé alors que la route existe.

## 10. Vérifications faites (5.10.2026, données FICTIVES, environnement local isolé)

| Contrôle | Résultat |
|---|---|
| `python -m pytest -q tests/test_n8n_workflows.py` | Structure, connexions, credentials par référence, écritures désactivées, routes du moteur, syntaxe et comportement des nœuds Code ; F4 : clé canonique (incident d'échec de 08 rejoué sur l'API => `/mandate/check` 423), alerte au changement (A → rien → A re-signalé), stock amont sans `/sync/run`, liens des emails, réponse de désinscription après bilan, digest |
| `python -m pytest -q tests/test_orchestration_f4.py` | Corps exact du nœud 01 rejoué sur l'API : 409 sans catalogue, PROPRE avec registres, VIDE sans offre évaluée, compteur persistant ; photo du stop-loss depuis les registres ; suspension du mandat ; notification livrée seulement si envoyée |
| Import des 8 exports dans **n8n 2.41.6** (`n8n import:workflow --separate`) | 8 importés, identifiants et workflow d'erreur conservés, tous inactifs |
| 05 exécuté contre l'API locale | Digest composé : étoile polaire, puis stop-loss (cash et produit), puis KPI ; email et Slack non envoyés |
| 07 exécuté deux fois (version antérieure à F4 : déduplication « jamais vu ») | 1re : notification préparée ; 2e : rien. Perte FICTIVE ≥ 20 % : `POST /stoploss/freeze` appelé, autonomie ramenée au niveau 1. **À refaire** dans n8n avec F4 (photo construite par le moteur, alerte au changement) |
| 01 exécuté (version antérieure à F4) | 3 imports FICTIFS en simulation, 3 cycles `/sync/run` déclarés propres **sans aucune offre évaluée** (défaut E2E-07 corrigé : ils sont désormais refusés ou VIDES). **À refaire** dans n8n avec le catalogue enregistré |
| 08 via webhook | Sans en-tête : 403 ; sans photo stop-loss : 503 « refus par défaut » ; mandat non signé : 202 NEEDS_HUMAN_APPROVAL ; grading : REJECTED ; formulaire de validation : 401 sans Basic Auth, refus enregistré, aucun paiement atteint |
| 04 via webhook | Notification S1 composée et routée vers l'alerte immédiate |

Sources consultées le 5.10.2026 : définitions des nœuds n8n (`https://raw.githubusercontent.com/n8n-io/n8n/master/packages/nodes-base/nodes/` : Webhook, Wait, HttpRequest V3, If V2, Set V2, Switch V3, RemoveDuplicates V2, ShopifyTrigger, ScheduleTrigger, RespondToWebhook, EmailSend V2, Slack V2) ; changements n8n 2.0 (blocage de `$env`, publication au lieu de l'activation) via l'index de recherche de `https://docs.n8n.io/2-0-breaking-changes/` (page bloquée par le proxy de l'environnement : à relire) ; paquet npm `n8n` 2.41.6 (`npm view n8n version`).

## 11. Points ouverts

- **Accès public de n8n** : n8n est public en HTTPS **dès J8 (B27)**, avant la landing, limité au webhook d'inscription et aux liens des emails ; à J26 (B23), le proxy ouvre aussi les webhooks Shopify et les formulaires (`WEBHOOK_URL`). Le compose publie n8n et l'API sur 127.0.0.1 : le proxy inverse (ou le tunnel) choisi à B27 est le seul accès public, et l'API n'est jamais exposée. Dès J8, la pile interne tourne en simulation : un échec du workflow d'inscription ou d'un lien d'email ouvre un incident dans l'API (`n8n-06-marketing`), notifié par 04 ; API injoignable : alerte « moteur injoignable » de 04 par email (`site/landing/README.md` §4). Limite connue : les nœuds « Incident : … » de 06 continuent sur leur sortie d'erreur (page « traitement manuel ») sans autre alerte si l'API ne répond pas ; surveiller `GET /health` (digest 05 dès J26).
- **Déclencheur Shopify de n8n** : il inscrit les webhooks via l'API REST de Shopify ; vérifier sa compatibilité avec l'app personnalisée et la version d'API retenue avant le niveau 2 (sinon : webhooks créés dans l'admin Shopify + nœud Webhook avec vérification HMAC côté moteur).
- **Inscription aux alertes** de la landing (réception du formulaire, envoi de l'email 01) : contrat dans `site/landing/README.md` §4 ; à construire avec l'outil d'emailing (B04). Le lien de **confirmation** (`alertes-confirmer`), les **préférences**, la **désinscription** et le **refus d'avis** existent dans 06 (contrats de réponse de l'outil à adapter).
- **Dettes et créances de la photo du stop-loss** : déclarées par l'agent finance (`POST /treasury/balance-items`) tant que `POST /orders/paid` et `POST /costs/invoices` ne sont pas livrées pour les calculer ; sans déclaration de moins de 24 h, pas de photo (fermé par défaut).
- **Connecteurs de trésorerie** (PayPal, banque) et **publicitaire** (`POST /ads/activity`) : à recetter ; sans soldes récents, la photo est refusée (stop-loss non évaluable, dépenses refusées) ; aucune campagne publicitaire ne doit tourner sans le connecteur publicitaire (sinon le stop-loss pub ne voit pas les dépenses).

## Validation humaine requise

- [ ] Choisir et créer le canal d'alerte immédiate (email, Slack, SMS) et les credentials du §4 ; ranger chaque secret au coffre (B03).
- [ ] Exposer n8n en HTTPS public dès J8 (B27, webhook d'inscription et liens des emails seulement, pile interne lancée par `scripts/compose.sh`), puis ouvrir les webhooks Shopify et les formulaires à J26 (B23).
- [ ] Valider les hypothèses : délai d'expédition 3 jours ouvrés, seuil d'alerte stock 3 unités, demande d'avis à J+7, digest à 07:45.
- [ ] Activer les workflows dans l'ordre du §7, niveau par niveau, après chaque recette ; décider C14 avant toute écriture réelle.
- [ ] Signer le mandat (B01) et recetter CONN-PAYPAL avant d'activer un nœud de paiement.
- [ ] Enregistrer vos apports de capital avec votre jeton (`POST /capital/movements`) : sans eux, la photo du stop-loss n'est jamais construite.
- [ ] Générer un jeton par rôle du §4 (`openssl rand -hex 32`), reporter chaque empreinte dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` et créer le credential n8n du même nom ; ne jamais confier le jeton commun ni le jeton propriétaire à n8n.
- [ ] Générer le jeton nommé `qa-conformite` (tests de correction des incidents) et le remettre au seul agent QA ; sans lui, seule la propriétaire peut attester un test réussi.
- [ ] Après l'activation de 04, vérifier la réception d'un incident FICTIF (`POKESHOP_NOTIFY_DRY_RUN=false`).
- [ ] Faire livrer par l'agent integrations les routes attendues du §9, l'en-tête secret du webhook d'incident et le nœud `POST /orders/shipped` de 02 (coût transporteur réel).
