# Orchestration n8n — {{NOM_BOUTIQUE}}

> Version du 5.10.2026, agent « orchestration-dashboard ». Sources : BP §5 (synchronisation), §9 (automatisations marketing), §12 (workflows et tableau de bord), §13 (niveaux d'autonomie) ; `docs/00-pilotage/STOP_LOSS.md`, `DELEGATION_AUTONOMIE.md`, `ETOILE_POLAIRE.md` ; `docs/07-ops/SOP_INCIDENTS.md`, `ROUTINES_PILOTAGE.md` ; `docs/06-contenu/EMAILS/README.md`.
> **Statut : prêt à importer, rien d'actif.** Les 8 workflows arrivent **inactifs**, toutes les écritures externes **désactivées**, le moteur appelé **en simulation**. Aucun compte, aucune boutique, aucun envoi n'existe au 5.10.2026.

## 1. Les huit workflows

| Fichier | Déclencheur | Ce qu'il fait | Appels du moteur (actifs) | Écritures externes (désactivées) | Niveau d'activation |
|---|---|---|---|---|---|
| `n8n/01_fournisseur_vers_site.json` | Toutes les 6 h (prix, offres) ; toutes les 45 min (stock amont) | Import en simulation, cycle fournisseur → site **dry-run**, incident de flux INC-03 | `GET /incidents`, `POST /imports/{fournisseur}/run`, `POST /sync/run` (`dry_run: true`), `POST /incidents` | Lecture du flux fournisseur, dépôt du fichier | 1 (simulation) ; écriture réelle : décision C14 |
| `n8n/02_commande_vers_livraison.json` | Shopify `orders/paid` ; chaque jour ouvré 07:30 ; lundi 06:30 | Contrôle doublon (idempotence), anomalies (CHF, Suisse, payée), bon de préparation, **tâche colis HUMAINE**, colis en retard, rapprochement des frais PSP réels | `POST /incidents`, `POST /northstar/entries` | Réservation (route moteur attendue), emails à la responsable, lectures Shopify | 2 |
| `n8n/03_facture_vers_marge_reelle.json` | Passerelle agent 05 (`/webhook/pokeshop-facture`) | Contrôles déterministes en centimes, **validation humaine** de l'extraction (formulaire 72 h), écarts > 2 % | `POST /incidents` | Enregistrement du coût historique (route attendue), emails | 1 (contrôles) |
| `n8n/04_incident.json` | Moteur (`/webhook/pokeshop-incidents`) ; passerelle (`/webhook/pokeshop-incident-reprise`) ; **Error Trigger** | Notification cause + action (S1 immédiat, S2 dans l'heure, S3 digest) ; reprise après test et validation ; incident pour toute exécution en échec | `POST /incidents`, `POST /incidents/{id}/test`, `POST /incidents/{id}/resume` | Emails, Slack | **1, en premier** |
| `n8n/05_digest_quotidien.json` | Chaque jour 07:45 | Digest : **1. étoile polaire** (`GET /northstar`), **2. stop-loss**, puis KPI du jour et décisions attendues | `GET /northstar`, `GET /stoploss/status`, `GET /dashboard/daily` | Email, Slack | 1 |
| `n8n/06_marketing_automations.json` | Passerelle agent 11 (réception contrôlée) ; Shopify `orders/fulfilled`, `fulfillment_events/create`, `customers/update` ; lien de désinscription | Alerte « nouveau stock local » aux inscrits consentants (**garde-fous** : stock sous le seuil, marge insuffisante, gel), suivi d'expédition, demande d'avis J+7, **désinscription propagée** | `GET /stoploss/status`, `POST /stock/sellable` | Outil d'emailing, Shopify | Désinscription : dès l'outil d'emailing ; envois : 3 |
| `n8n/07_stoploss_watch.json` | Toutes les heures (:10) | Si un déclencheur change : **gel via API**, coupure des campagnes, **notification immédiate** (cause, chiffres, action, comment réarmer) | `GET /stoploss/status`, `POST /stoploss/freeze` | Plateforme publicitaire, email, Slack | 1, juste après 04 |
| `n8n/08_mandat_depenses.json` | Passerelle agents (`/webhook/pokeshop-depense`) | `POST /mandate/check` → APPROVED (préparer, journaliser) / NEEDS_HUMAN_APPROVAL (**validation 1 clic**, formulaire 24 h) / REJECTED ; contrôle impossible = refus | `GET /incidents`, `POST /mandate/check` (`record: true`) | Paiement PayPal, emails, routes d'exécution attendues | 1 (contrôle) ; exécution : mandat signé + recette |

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
| Suspension | 01 et 08 lisent `GET /incidents` : workflow suspendu = rien ne part ; 08 s'arrête aussi sur suspension globale (`*`) |
| Stop-loss | 06 coupe une campagne si stock vendable < seuil, référence sous stop-loss produit, gel global ou stop-loss non évaluable ; 07 gèle et notifie ; **aucun workflow ne réarme** |
| Erreurs | Le workflow d'erreur de 01-03 et 05-08 est 04 (Error Trigger) : toute exécution en échec ouvre un incident |

## 3. Prérequis

- [ ] L'API du moteur tourne (docker compose `api`, ou `uvicorn pokeshop.api:create_app --factory`) avec `POKESHOP_API_TOKEN_SHA256` configuré (sinon 503).
- [ ] n8n tourne (docker compose `n8n`). **Version testée : n8n 2.41.6** (import, exécution, webhooks, formulaire ; §10). Épingler cette version dans `N8N_IMAGE` après votre propre test.
- [ ] Jeton d'API en main (celui dont l'empreinte est `POKESHOP_API_TOKEN_SHA256`). **Jamais** le jeton propriétaire dans n8n.
- [ ] Pour les déclencheurs Shopify et les liens de formulaire envoyés par email : une **URL publique HTTPS** de n8n (`WEBHOOK_URL`) — le compose publie n8n sur 127.0.0.1 seulement (décision §11).

## 4. Créer les identifiants (credentials) — avant l'import

Dans n8n : **Credentials → Create credential**, avec **exactement** ces noms (n8n rattache les nœuds par identifiant ; si le rattachement échoue, on choisit le credential du même nom dans chaque nœud signalé en rouge).

| Nom exact | Type n8n | Contenu | Utilisé par | Quand |
|---|---|---|---|---|
| `Pokeshop API — X-Pokeshop-Token` | Header Auth | Name `X-Pokeshop-Token`, Value = jeton d'API | Tous les appels du moteur | Dès le niveau 1 |
| `Passerelle agents — X-Pokeshop-Gateway` | Header Auth | Name `X-Pokeshop-Gateway`, Value = secret aléatoire (coffre), donné aux seuls agents | Webhooks 03, 04 (reprise), 06 (réception), 08 | Dès le niveau 1 |
| `Formulaires propriétaire — Basic Auth` | Basic Auth | Utilisateur et mot de passe connus de la **propriétaire seule** | Formulaires de validation (03, 04, 08) | Dès le niveau 1 |
| `SMTP boîte des agents` | SMTP | Serveur, port, compte de la boîte dédiée aux agents | Emails à la responsable | Après test d'envoi |
| `Slack alertes propriétaire` | Slack API | Jeton du canal d'alerte (facultatif) | 04, 05, 07 | Si ce canal est choisi |
| `Shopify Admin — app personnalisée` | Shopify Access Token API | Sous-domaine, jeton d'accès, **clé secrète de l'app** (vérification HMAC des webhooks) | Déclencheurs et lectures Shopify (02, 06) | Niveau 2 |
| `Outil d'emailing — jeton API` | Header Auth | Selon l'outil retenu (B04) | 06 | Avec l'outil d'emailing |
| `Plateforme publicitaire — jeton API` | Header Auth | Selon la plateforme (CONN-PUB) | 07 (coupure) | Après recette du connecteur |
| `PayPal compte dédié — OAuth2 client credentials` | OAuth2 API (grant « Client Credentials ») | Client ID / secret de l'app du compte PayPal dédié ; URL du jeton à reprendre de la documentation PayPal | 08 (paiement) | Mandat signé + recette CONN-PAYPAL |
| `Flux fournisseur — accès autorisé` | Header Auth | Selon l'accès écrit du fournisseur | 01 | Accès fournisseur obtenu |

## 5. Importer pas à pas (sans code)

**Par l'interface n8n**

1. Ouvrir n8n (`http://127.0.0.1:5678`), créer le compte propriétaire n8n.
2. Créer les credentials du §4 (au minimum les trois premiers).
3. **Workflows → Create workflow → menu « … » → Import from File…** : importer `04_incident.json` en premier, puis 07, 05, 08, 01, 03, 02, 06 (un workflow par import). Enregistrer.
4. Dans chaque workflow, ouvrir le nœud **« Paramètres »** (ou « Paramètres — … ») : vérifier `api_base_url` (docker compose : `http://api:8000`), remplacer `responsable_email`, laisser `simulation = true`.
5. Ouvrir chaque nœud marqué en rouge (credential introuvable) et choisir le credential du même nom.
6. **Workflow settings → Error workflow** : choisir « Pokeshop 04 — Incidents et erreurs » pour 01, 02, 03, 05, 06, 07, 08 (l'import par l'interface peut changer les identifiants).
7. Tester : bouton **Execute workflow** sur 05, puis 07, puis 01 ; lire le résultat de chaque nœud (aucun email ne part : nœuds désactivés).
8. Activer selon le §7 : n8n 2.x → bouton **Publish** ; n8n 1.x → interrupteur **Active**.

**Par la ligne de commande (docker compose)** — le compose monte `./orchestration/n8n` en lecture seule sur `/workflows` :

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
docker compose exec n8n n8n publish:workflow --id=pkshp04Incidents   # n8n 2.x ; puis redémarrer n8n
```

Les identifiants des workflows sont conservés : le workflow d'erreur (04) est déjà relié. Pour relier aussi les credentials sans clic, créer une table `{clé: id}` (ids lus dans l'URL de chaque credential, **aucun secret**) puis :

```bash
python orchestration/build_workflows.py --credentials-map ids.json --out /chemin/hors-depot
```

Clés : `api`, `gateway`, `owner_form`, `smtp`, `slack`, `shopify`, `emailing`, `ads`, `paypal`, `supplier`.

## 6. Nœuds désactivés : quand les activer

| Workflow | Nœud | Condition d'activation |
|---|---|---|
| 01 | Récupérer le flux autorisé ; Déposer le fichier | Accès **écrit** du fournisseur (API, fichier fourni ou export approuvé) ; volume partagé `POKESHOP_IMPORTS_DIR` ; `N8N_RESTRICT_FILE_ACCESS_TO` réglé |
| 01 | Alerter la responsable (email) | Credential SMTP testé |
| 02 | Réserver le stock local — route moteur attendue | Route `POST /orders/paid` livrée par l'agent integrations et recettée |
| 02 | Tâche colis HUMAINE, Colis en retard, Résumé du rapprochement (emails) | Credential SMTP testé |
| 02 | Lectures Shopify (commandes, versements) | Credential Shopify (niveau 2) ; champs GraphQL 2026-10 revérifiés |
| 03 | Enregistrer le coût historique — route moteur attendue | Route `POST /costs/invoices` livrée et recettée |
| 04, 05, 07 | Emails et Slack à la propriétaire | Canal choisi (SOP_INCIDENTS §1) et testé ; permis dès le niveau 1 (information de la seule propriétaire) |
| 06 | Inscrits, envois 04 et 11 (outil d'emailing) | Outil choisi (B04), notes juristes C2-C4, **désinscription active d'abord**, niveau 3 |
| 06 | Désinscription (outil d'emailing, Shopify) | En même temps que l'outil d'emailing, **avant tout envoi** ; mutation Shopify validée par l'agent integrations |
| 07 | Couper les campagnes | Recette du connecteur publicitaire ; action protectrice (niveau 1 admis) |
| 08 | Exécuter le paiement PayPal ; Marquer exécuté ; Enregistrer la validation / le refus | Mandat **signé** (B01) et empreinte au coffre ; recette CONN-PAYPAL ; routes `POST /mandate/executed` et `POST /mandate/human-decision` livrées |

## 7. Ordre d'activation par niveau d'autonomie (BP §13)

**Niveau 1 — tout en simulation et brouillons**
- [ ] 04 Incidents (premier : c'est le workflow d'erreur de tous les autres).
- [ ] 07 Surveillance du stop-loss (le gel par API est actif ; la coupure publicitaire reste désactivée).
- [ ] 05 Digest quotidien (activer l'email après le test SMTP : il ne va qu'à la responsable).
- [ ] 08 Mandat de dépense (contrôle et validation 1 clic ; aucun paiement exécuté).
- [ ] 01 Fournisseur vers site en **dry-run** (20 cycles sans erreur critique = critère de recette BP §13).
- [ ] 03 Facture vers marge réelle (contrôles et validation ; enregistrement quand la route existe).

**Niveau 2 — prix et stock des références approuvées synchronisés dans des seuils** (décision C14 de la propriétaire)
- [ ] 02 Commande vers livraison (l'activation inscrit le webhook `orders/paid` chez Shopify).
- [ ] 01 en écriture réelle : `dry_run: false` dans le nœud « Cycle fournisseur vers site » **et** `POKESHOP_DRY_RUN=false` côté moteur ; la porte de gouvernance vérifie encore le niveau, le stop-loss et le mandat.

**Niveau 3 — nouveaux produits publiés, campagnes selon règles**
- [ ] 06 envois (alerte stock local, demande d'avis) — désinscription déjà active.
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
| 06 page de désinscription | `https://REMPLACER-URL-LANDING.exemple.invalid/desinscription.html` | — | `URL_LANDING` |
| Nœuds Shopify | `https://REMPLACER-boutique.myshopify.com/admin/api/2026-10/graphql.json` | — | domaine de la boutique (B15) |
| Variables n8n (compose) | `WEBHOOK_URL`, `N8N_ENCRYPTION_KEY`, `GENERIC_TIMEZONE=Europe/Zurich`, `N8N_RESTRICT_FILE_ACCESS_TO` | — | coffre (B03) |

Ne pas désactiver le blocage de `$env` (`N8N_BLOCK_ENV_ACCESS_IN_NODE`, vrai par défaut en n8n 2.x) : aucun workflow n'en a besoin.

## 9. Contrat avec le moteur

| Route | Workflow | État au 5.10.2026 |
|---|---|---|
| `GET /incidents`, `POST /incidents`, `POST /incidents/{id}/test`, `POST /incidents/{id}/resume` | 01, 02, 03, 04, 08 | Existe |
| `POST /imports/{supplier}/run`, `POST /sync/run` | 01 | Existe (simulation) |
| `GET /northstar`, `POST /northstar/entries` | 02, 05 | Existe |
| `GET /stoploss/status`, `POST /stoploss/freeze` | 05, 06, 07 | Existe |
| `POST /stock/sellable` | 06 | Existe |
| `POST /mandate/check` | 08 | Existe |
| `GET /dashboard/daily` | 05 | Existe (routeur du tableau de bord) |
| `POST /orders/paid` (réservation, survente INC-06, ventes nettes de l'étoile polaire) | 02 | **Attendue** (nœud désactivé) |
| `POST /costs/invoices` (ventilation, coût historique, écarts) | 03 | **Attendue** |
| `POST /mandate/executed`, `POST /mandate/human-decision` (registre du mandat) | 08 | **Attendue** |
| En-tête secret sur le webhook d'incident du moteur | 04 | **Attendu** (le moteur n'envoie aucun en-tête : webhook limité au réseau interne docker) |

`tests/test_n8n_workflows.py` échoue si un nœud actif appelle une route qui n'existe pas, ou si un nœud « route moteur attendue » reste désactivé alors que la route existe.

## 10. Vérifications faites (5.10.2026, données FICTIVES, environnement local isolé)

| Contrôle | Résultat |
|---|---|
| `python -m pytest -q tests/test_n8n_workflows.py` | Structure, connexions, credentials par référence, écritures désactivées, routes du moteur, syntaxe et comportement des nœuds Code |
| Import des 8 exports dans **n8n 2.41.6** (`n8n import:workflow --separate`) | 8 importés, identifiants et workflow d'erreur conservés, tous inactifs |
| 05 exécuté contre l'API locale | Digest composé : étoile polaire, puis stop-loss (cash et produit), puis KPI ; email et Slack non envoyés |
| 07 exécuté deux fois | 1re : notification préparée ; 2e : rien (une alerte par changement). Perte FICTIVE ≥ 20 % : `POST /stoploss/freeze` appelé, autonomie ramenée au niveau 1 |
| 01 exécuté | 3 imports FICTIFS en simulation (quarantaines attendues), 3 cycles `/sync/run` en dry-run, propres |
| 08 via webhook | Sans en-tête : 403 ; sans photo stop-loss : 503 « refus par défaut » ; mandat non signé : 202 NEEDS_HUMAN_APPROVAL ; grading : REJECTED ; formulaire de validation : 401 sans Basic Auth, refus enregistré, aucun paiement atteint |
| 04 via webhook | Notification S1 composée et routée vers l'alerte immédiate |

Sources consultées le 5.10.2026 : définitions des nœuds n8n (`https://raw.githubusercontent.com/n8n-io/n8n/master/packages/nodes-base/nodes/` : Webhook, Wait, HttpRequest V3, If V2, Set V2, Switch V3, RemoveDuplicates V2, ShopifyTrigger, ScheduleTrigger, RespondToWebhook, EmailSend V2, Slack V2) ; changements n8n 2.0 (blocage de `$env`, publication au lieu de l'activation) via l'index de recherche de `https://docs.n8n.io/2-0-breaking-changes/` (page bloquée par le proxy de l'environnement : à relire) ; paquet npm `n8n` 2.41.6 (`npm view n8n version`).

## 11. Points ouverts

- **Accès public de n8n** : les webhooks Shopify et les liens de formulaire exigent une URL HTTPS publique (`WEBHOOK_URL`), alors que le compose publie n8n sur 127.0.0.1. Proxy inverse ou tunnel : décision et compte à ouvrir.
- **Déclencheur Shopify de n8n** : il inscrit les webhooks via l'API REST de Shopify ; vérifier sa compatibilité avec l'app personnalisée et la version d'API retenue avant le niveau 2 (sinon : webhooks créés dans l'admin Shopify + nœud Webhook avec vérification HMAC côté moteur).
- **Dossier d'import partagé** n8n ↔ API (01) : volume à ajouter au compose (agent integrations).
- **Inscription aux alertes (double opt-in)** de la landing : contrat dans `site/landing/README.md` §4 ; workflow à construire quand l'outil d'emailing (B04) sera choisi (stockage des inscrits).

## Validation humaine requise

- [ ] Choisir et créer le canal d'alerte immédiate (email, Slack, SMS) et les credentials du §4 ; ranger chaque secret au coffre (B03).
- [ ] Décider l'exposition publique de n8n (`WEBHOOK_URL`, proxy inverse ou tunnel) avant le niveau 2.
- [ ] Valider les hypothèses : délai d'expédition 3 jours ouvrés, seuil d'alerte stock 3 unités, demande d'avis à J+7, digest à 07:45.
- [ ] Activer les workflows dans l'ordre du §7, niveau par niveau, après chaque recette ; décider C14 avant toute écriture réelle.
- [ ] Signer le mandat (B01) et recetter CONN-PAYPAL avant d'activer un nœud de paiement.
- [ ] Faire livrer par l'agent integrations les routes attendues du §9 et l'en-tête secret du webhook d'incident.
