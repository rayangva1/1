# Quai des Cartes · boutique Pokémon JCC FR en Suisse

> Nom de travail **provisoire** (non validé, domaine et marque non vérifiés).
> Source : `docs/business-plan/Business_plan_Pokemon_FR_Suisse.docx` (BP du 4 octobre 2026).
> Statut : **tout est construit, rien n'est en ligne.** Aucun compte ouvert, aucun email envoyé, aucun achat. Toutes les données d'exemple sont **FICTIVES**.

## 🎯 Étoile polaire

**Gagner de l'argent avec les cartes Pokémon**, mesuré par un seul chiffre : la **contribution nette cumulée**
(ventes nettes HT − coût historique − paiement − logistique − SAV − acquisition − charges fixes).
Ni le CA ni les followers ne comptent. Définition : `docs/00-pilotage/ETOILE_POLAIRE.md`.

## Modèle d'opération

La flotte d'agents gère tout **dans un mandat écrit** (email dédié, PayPal dédié, plafonds, fournisseurs autorisés, journal).
La propriétaire intervient seulement pour :

| Type | Exemples | Fréquence |
|---|---|---|
| A. Physique | réception du stock, contrôle d'authenticité, colis, photos et vidéos réelles | récurrent après ouverture |
| B. Légal et identité | KYC, ouverture de comptes, signatures, statut TVA, jetons (le tien et un par rôle utilisé), secrets des passerelles n8n (un par agent) et empreintes au coffre, hébergement (n8n et pile interne dès J8, mise en service complète à J26), accès en lecture seule banque et PayPal, enregistrement des apports de capital | une seule fois |
| C. Hors mandat | dépense au-delà des plafonds, signature des seuils, point zéro, approbation d'un prix hors règles, **validation de chaque fiche produit**, taux de change du jour, recette signée, **réarmement du stop-loss global** | ponctuel |

👉 La checklist ordonnée et exhaustive (chaque acte relié à sa tâche du backlog et à son échéance) : `docs/00-pilotage/INTERVENTIONS_HUMAINES.md`.
👉 Le mandat à remplir et signer : `docs/00-pilotage/DELEGATION_AUTONOMIE.md` + `config/mandate.v1.yaml`.

## Garde-fous (non négociables)

- **Stop-loss sur 6 niveaux** : produit, extension, pub, cash, global (perte de valeur nette ≥ 20 % du capital engagé de référence, soit 840 CHF avec le point zéro recommandé ; réarmé par la propriétaire uniquement, avec son jeton), temps. Voir `docs/00-pilotage/STOP_LOSS.md`.
- **Fermé par défaut** : donnée illisible, périmée ou invérifiable ⇒ refus ou validation humaine, jamais une approbation. Aucun chiffre décisif (trésorerie, solde, taux, plafond, seuil) n'est déclaré par l'agent qui en profite : le moteur le lit dans ses registres, et l'acteur est déduit de son jeton nommé.
- **Autorisations par rôle, refus par défaut** (`engine/pokeshop/authz.py`, table générée `docs/08-agents/MATRICE_API.md`, version citée par `/health`) : chaque route de l'API déclare les rôles admis ; une route absente de la matrice est refusée (403). Un jeton par rôle utilisé (7 agents et 10 connecteurs n8n ; les agents sans accès à l'API n'en reçoivent pas) ; le **jeton commun** ne fait que lire et simuler (403 sur toute écriture) et n'est jamais confié à n8n ni à un agent ; chaque passerelle n8n (03, 04, 06, et 08 par agent qui dépense) a **son** secret, remis au seul agent nommé, et l'administration de n8n reste à toi. Séparation des rôles : la dépense pub vient du connecteur publicitaire (jamais de l'agent acquisition), comptée au MAX avec les paiements pub **engagés** du mandat (sans connecteur, aucune campagne) ; les soldes viennent du connecteur de trésorerie (ou de toi) ; la photo du stop-loss est **construite par le moteur** (le workflow 07 ne fait que la demander ; une photo déposée et les créances : toi seule) ; le coût historique d'une réception exige une réception physique déclarée par un autre jeton et reste à ± 2 % d'une référence du moteur (ligne de la facture enregistrée par le workflow 03 après ta validation, quantités et fournisseur rapprochés, ou offre évaluée avec des frais posés par toi — jamais ceux de l'agent finance ni ceux d'une simulation), sinon c'est toi qui l'inscris ; les ventes et le coût des ventes de l'étoile polaire sont dérivés des commandes expédiées (lignes, coût transporteur réel ; une commande payée n'est jamais refusée faute de coût : coût des ventes en attente, étoile polaire incomplète, dépenses en validation humaine), les frais d'une commande comptés une fois ; un retour ne revient en stock au coût qu'avec un avoir à lignes et un retour physique déclaré par un autre jeton ; dettes déclarées (l'agent finance ne peut que les relever) et créances (toi seule) sont deux registres persistés distincts ; une dépense en attente n'est validée que par toi (`POST /mandate/human-decision`, ton jeton) ; une fiche n'est validée que par toi (`POST /catalog/approvals`, liée à son contenu, une seule clé produit) ; un test de correction d'incident n'est attesté que par l'agent QA (≠ ouvreur, sur un cycle réel lancé par un autre ; cycle FICTIF admis seulement pour un incident sur données FICTIVES, ou déclaré `simulation: true` et ouvert alors que le moteur est en simulation) ou par toi ; réarmement, point zéro, apports, taux, approbations de prix et de fiches : ton jeton, **suffisant seul**, jamais dans n8n ni chez un agent.
- **Revue adverse de sécurité** (5 rounds, 124 défauts signalés au round 1) : historique, correctifs et **risques résiduels connus** dans `docs/00-pilotage/REVUE_SECURITE.md` ; elle est relancée avant chaque passage aux niveaux d'autonomie 2, 3 et 4, qui exige zéro finding critical/high ouvert.
- **Signé par la propriétaire, au coffre** : mandat, seuils du stop-loss et règles de prix ne valent que par l'empreinte qu'elle reporte au coffre ; un fichier modifié sans signature ne peut que durcir les seuils.
- **Secrets hors de portée de la flotte** : `.claude/settings.json` ne contient que des règles `deny` (`.env`, `secrets/`, coffre local, environnement des processus) ; les secrets vivent hors de l'arborescence des agents.
- **Simulation par défaut** : client Shopify en `dry_run`, workflows n8n inactifs, écritures externes désactivées.
- **Niveaux d'autonomie 1 à 4** (BP §13) : chaque écriture exige le niveau requis ; un incident critique fait redescendre d'un niveau.
- **Aucun coût interne public** : liste blanche des champs publiés, vue SQL `public_catalog` sans coûts, tests de fuite.
- **Aucun faux stock** : le stock fournisseur n'est pas le stock boutique ; pas de précommande sans allocation ferme.
- Les calculs se font en `Decimal`, de façon déterministe et versionnée. L'IA rédige et extrait ; elle ne décide ni d'une TVA ni d'un prix.

## Ce qu'il y a dans le repo

| Dossier | Contenu |
|---|---|
| `engine/pokeshop/` | Moteur Python : coût rendu, prix plancher, contribution, panier, coûts historiques, stock, réservations, réassort, trésorerie 13 semaines, prévisions, stop-loss, mandat, étoile polaire, catalogue, imports fournisseurs, client Shopify, publication, synchronisation, incidents, audit, autonomie, API FastAPI, KPI |
| `config/` | Règles versionnées : prix (`pricing_rules.v1.yaml`), stop-loss, mandat |
| `db/` | Schéma PostgreSQL 16 (compatible Supabase), journal en ajout seul, vue publique sans coûts, rôle restreint |
| `data/` | Dictionnaires de champs fournisseurs (gabarits) et échantillons FICTIFS avec anomalies |
| `orchestration/n8n/` | 8 workflows n8n importables : fournisseur → site, commande → livraison, facture → marge réelle, incident, rapport quotidien, marketing, surveillance stop-loss, contrôle des dépenses |
| `dashboard/` | Tableau de bord interne (contient coûts et marges : **ne jamais publier**) |
| `site/` | Landing d'ouverture avec alertes, structure Shopify, snippets Liquid, modèle de fiche produit |
| `docs/00-pilotage` | Plan 90 jours, backlog importable dans Notion, gates go/no-go, interventions humaines, risques, revue de sécurité et risques résiduels, écarts du BP consolidés, mandat, stop-loss |
| `docs/01-marche` | Grille concurrence, guide d'entretiens, questionnaire, protocole landing, assortiment pilote |
| `docs/02-sourcing` | Dossier B2B, emails fournisseurs prêts + relances, panier pilote, comparateur d'offres `.xlsx`, tracker contacts, due diligence |
| `docs/03-finance` | Modèle financier `.xlsx` (formules vivantes), trésorerie 13 semaines, vérification chiffre par chiffre du BP |
| `docs/04-legal` | **Brouillons** CGV, livraison et retours, précommandes, confidentialité (nLPD), mentions légales, cookies, usage des marques, checklist LCD |
| `docs/05-da` | Naming, 2 directions visuelles, logos SVG originaux, charte HTML, composants, templates sociaux, packaging |
| `docs/06-contenu` | Ton, 15 sujets, calendrier 90 jours, scripts vidéo, emails, test pub, brief créateurs, SEO |
| `docs/07-ops` | SOP réception, colis, SAV, incidents, routines, recette avant ouverture, FAQ |
| `docs/08-agents` + `.claude/agents/` | Les 12 agents du BP §11, utilisables directement comme sous-agents Claude Code (un jeton par rôle pour l'API du moteur, matrice `docs/08-agents/MATRICE_API.md`) |
| `.claude/settings.json` | Permissions du projet : uniquement des règles `deny` qui rendent les secrets illisibles par la flotte |

## Démarrage rapide

```bash
pip install -e ".[dev]"                 # dépendances
scripts/run_all_tests.sh                # toutes les suites de tests
uvicorn pokeshop.api:create_app --factory --app-dir engine --port 8000   # API du moteur (simulation)
python dashboard/build.py               # régénère dashboard/out/index.html (données FICTIVES)
```

- API sans base : les états de sécurité (gel du stop-loss, registre du mandat, incidents, étoile polaire, catalogue de synchronisation…) sont persistés par défaut dans `~/.local/state/pokeshop` (`POKESHOP_STATE_DIR`) ; sans aucune empreinte de jeton d'API (commun `POKESHOP_API_TOKEN_SHA256`, ou par rôle `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>` / `POKESHOP_AGENT_TOKENS_SHA256`), les routes internes répondent 503, sauf au jeton propriétaire valide (`X-Pokeshop-Owner-Token`, qui suffit seul sur toute route qui l'admet). Matrice d'autorisations, refus par défaut (le jeton commun ne fait que lire et simuler) : `docs/08-agents/MATRICE_API.md` ; routes : `docs/SPEC.md` §2.7.
- Tableau de bord réel (coûts et marges) : `python dashboard/build.py --api http://127.0.0.1:8000 --out ~/pokeshop/tableau.html` ; une sortie dans le dépôt est refusée.
- Landing : ouvrir `site/landing/index.html` (le formulaire reste désactivé tant que l'URL n8n n'est pas configurée).
- Charte : ouvrir `docs/05-da/CHARTE.html`.
- Plateforme complète (Postgres + n8n + API), commandes exécutables telles quelles par une propriétaire **non root** (vérifiées le 5.10.2026 avec un compte sans droits : création du fichier, saisie en place, `config` sans erreur ; un fichier créé sans `-o "$USER"` appartient à root et `docker compose` répond « permission denied » ; étape 3 rejouée le même jour : empreintes produites par la commande de J2, contrôle passé, `config` sans erreur, un fichier doublé refusé sans rien ajouter, et l'API lancée avec ce fichier accepte les 17 jetons) :

```bash
# 1. Sur le serveur : fichier de variables HORS du dépôt, à ton nom et lisible par toi seule (jamais de .env à la racine) :
sudo install -D -m 600 -o "$USER" .env.example /etc/pokeshop/api.env
# 2. Le compléter EN PLACE depuis le coffre (nano /etc/pokeshop/api.env ; pas « sed -i » : /etc/pokeshop appartient à root) :
#    POSTGRES_PASSWORD, POKESHOP_DB_PASSWORD, N8N_ENCRYPTION_KEY (chacun : openssl rand -hex 32), N8N_WEBHOOK_URL,
#    POKESHOP_OWNER_TOKEN_SHA256 (B21) — empreintes sha256, jamais les jetons.
# 3. Empreintes des rôles (B22), produites à J2 sur TON ordinateur (DELEGATION_AUTONOMIE.md §10 étape 6), dont
#    POKESHOP_ROLE_TOKEN_SHA256_N8N_07_STOPLOSS, POKESHOP_ROLE_TOKEN_SHA256_CONNECTEUR_TRESORERIE
#    et POKESHOP_ROLE_TOKEN_SHA256_FINANCE_PRICING, obligatoires. Sur ton ordinateur (« serveur » = son adresse SSH) :
scp ~/pokeshop-jetons/empreintes-roles.env serveur:~/empreintes-roles.env
#    puis sur le serveur : 17 lignes d'empreintes attendues, sinon rien n'est ajouté ; la copie est effacée :
test "$(grep -cE '^POKESHOP_ROLE_TOKEN_SHA256_[A-Z0-9_]+=[0-9a-f]{64}$' ~/empreintes-roles.env)" -eq 17 \
  && test "$(wc -l < ~/empreintes-roles.env)" -eq 17 \
  && cat ~/empreintes-roles.env >> /etc/pokeshop/api.env && shred -u ~/empreintes-roles.env
#    POKESHOP_API_TOKEN_SHA256 (jeton commun : lecture et aperçus seulement, pour dashboard/build.py) est facultatif ;
#    ton jeton (X-Pokeshop-Owner-Token) suffit seul pour tous tes actes et tes lectures.
# 4. Ton compte doit parler au démon Docker : une fois « sudo usermod -aG docker "$USER" » puis te reconnecter
#    (ce groupe équivaut à un accès root à la machine) ; sinon, préfixer chaque commande ci-dessous par sudo.
scripts/compose.sh config --quiet       # échoue en nommant la variable manquante (ou un .env dans le dépôt) ; rien n'est lancé
scripts/compose.sh up -d db db-migrate db-backup api n8n
scripts/compose.sh ps                   # db-backup « healthy » : restauration vérifiée depuis moins de 36 h (db/backup.sh etat)
```

  `scripts/compose.sh` = `docker compose --env-file /etc/pokeshop/api.env` (autre chemin : `POKESHOP_ENV_FILE`, perdu sous `sudo`) ; il refuse un `.env` dans le dépôt et un fichier de variables lisible par d'autres (mode autre que 600 ou 400). Chaque conteneur ne reçoit que ses variables (en-tête de `docker-compose.yml`). La même commande sert à J8 (B27 : pile interne en simulation, seul n8n exposé pour la landing) et à J26 (B23 : mise en service complète). Ordre d'activation des workflows : `orchestration/README.md` §7 (le workflow 07 **seulement après le point zéro**, C19) ; sauvegardes et copie chiffrée hors machine : `db/README.md`.

## Décisions qui t'attendent

1. **Nom et direction visuelle** : A « Quai » ou B « Pochette » (`docs/05-da/`), une seule validation.
2. **Mandat** : montants, fournisseurs autorisés, signature **et empreinte au coffre** (`docs/00-pilotage/DELEGATION_AUTONOMIE.md`) ; puis tes jetons à J2 (le tien, un par rôle utilisé de la matrice et un secret par passerelle n8n : une seule commande, `DELEGATION_AUTONOMIE.md` §10 étape 6, transfert au serveur à J8) et la signature des seuils.
3. **Point zéro du stop-loss global** : le décider à J3 avec le budget, puis le poser avec ton jeton à J27, après l'enregistrement de tes apports (J26), des soldes (déposés par toi avec ton jeton tant que le connecteur n'est pas recetté) et des dettes de l'agent 05, **avec la première photo** (`POST /stoploss/baseline` et `with_photo:true`, commandes prêtes dans `STOP_LOSS.md` §5), **puis seulement** activer le workflow 07 ; sans lui, le gel tombe avant la première vente (`docs/00-pilotage/STOP_LOSS.md` §5).
4. **Écarts bloquants du BP** : `docs/00-pilotage/ECARTS_BP.md` (ex. distributeur suisse Carletto AG absent du BP).
5. **Statut exploitant et TVA** avec la fiduciaire : le moteur a deux profils, il ne choisit pas.

Spécification technique commune : `docs/SPEC.md`.
