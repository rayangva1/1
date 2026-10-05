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
| B. Légal et identité | KYC, ouverture de comptes, signatures, statut TVA, jetons et empreintes au coffre, hébergement (n8n dès J8, puis API et base), accès en lecture seule banque et PayPal, enregistrement des apports de capital | une seule fois |
| C. Hors mandat | dépense au-delà des plafonds, signature des seuils, point zéro, approbation d'un prix hors règles, taux de change du jour, recette signée, **réarmement du stop-loss global** | ponctuel |

👉 La checklist ordonnée et exhaustive (chaque acte relié à sa tâche du backlog et à son échéance) : `docs/00-pilotage/INTERVENTIONS_HUMAINES.md`.
👉 Le mandat à remplir et signer : `docs/00-pilotage/DELEGATION_AUTONOMIE.md` + `config/mandate.v1.yaml`.

## Garde-fous (non négociables)

- **Stop-loss sur 6 niveaux** : produit, extension, pub, cash, global (perte de valeur nette ≥ 20 % du capital engagé de référence, soit 840 CHF avec le point zéro recommandé ; réarmé par la propriétaire uniquement, avec son jeton), temps. Voir `docs/00-pilotage/STOP_LOSS.md`.
- **Fermé par défaut** : donnée illisible, périmée ou invérifiable ⇒ refus ou validation humaine, jamais une approbation. Aucun chiffre décisif (trésorerie, solde, taux, plafond, seuil) n'est déclaré par l'agent qui en profite : le moteur le lit dans ses registres, et l'acteur est déduit de son jeton nommé.
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
| `docs/00-pilotage` | Plan 90 jours, backlog importable dans Notion, gates go/no-go, interventions humaines, risques, écarts du BP consolidés, mandat, stop-loss |
| `docs/01-marche` | Grille concurrence, guide d'entretiens, questionnaire, protocole landing, assortiment pilote |
| `docs/02-sourcing` | Dossier B2B, emails fournisseurs prêts + relances, panier pilote, comparateur d'offres `.xlsx`, tracker contacts, due diligence |
| `docs/03-finance` | Modèle financier `.xlsx` (formules vivantes), trésorerie 13 semaines, vérification chiffre par chiffre du BP |
| `docs/04-legal` | **Brouillons** CGV, livraison et retours, précommandes, confidentialité (nLPD), mentions légales, cookies, usage des marques, checklist LCD |
| `docs/05-da` | Naming, 2 directions visuelles, logos SVG originaux, charte HTML, composants, templates sociaux, packaging |
| `docs/06-contenu` | Ton, 15 sujets, calendrier 90 jours, scripts vidéo, emails, test pub, brief créateurs, SEO |
| `docs/07-ops` | SOP réception, colis, SAV, incidents, routines, recette avant ouverture, FAQ |
| `docs/08-agents` + `.claude/agents/` | Les 12 agents du BP §11, utilisables directement comme sous-agents Claude Code (un jeton nommé par agent pour l'API du moteur) |
| `.claude/settings.json` | Permissions du projet : uniquement des règles `deny` qui rendent les secrets illisibles par la flotte |

## Démarrage rapide

```bash
pip install -e ".[dev]"                 # dépendances
scripts/run_all_tests.sh                # toutes les suites de tests
uvicorn pokeshop.api:create_app --factory --app-dir engine --port 8000   # API du moteur (simulation)
python dashboard/build.py               # régénère dashboard/out/index.html (données FICTIVES)
```

- API sans base : les états de sécurité (gel du stop-loss, registre du mandat, incidents, étoile polaire, catalogue de synchronisation…) sont persistés par défaut dans `~/.local/state/pokeshop` (`POKESHOP_STATE_DIR`) ; sans aucune empreinte de jeton d'API (commun `POKESHOP_API_TOKEN_SHA256` ou nommés `POKESHOP_AGENT_TOKENS_SHA256`), les routes internes répondent 503. Routes et jetons par rôle : `docs/SPEC.md` §2.7.
- Tableau de bord réel (coûts et marges) : `python dashboard/build.py --api http://127.0.0.1:8000 --out ~/pokeshop/tableau.html` ; une sortie dans le dépôt est refusée.
- Landing : ouvrir `site/landing/index.html` (le formulaire reste désactivé tant que l'URL n8n n'est pas configurée).
- Charte : ouvrir `docs/05-da/CHARTE.html`.
- Plateforme complète (Postgres + n8n + API), commandes exécutables telles quelles :

```bash
# Fichier de variables HORS du dépôt, lisible par toi seule (jamais de .env à la racine du dépôt) :
sudo install -D -m 600 .env.example /etc/pokeshop/api.env
# Y remplir depuis le coffre : POSTGRES_PASSWORD, POKESHOP_DB_PASSWORD, N8N_ENCRYPTION_KEY,
# POKESHOP_API_TOKEN_SHA256, POKESHOP_OWNER_TOKEN_SHA256 (empreintes sha256, jamais les jetons).
scripts/compose.sh config --quiet       # échoue en nommant la variable manquante (ou un .env dans le dépôt) ; rien n'est lancé
scripts/compose.sh up -d db db-migrate db-backup api n8n
scripts/compose.sh ps                   # db-backup « healthy » : restauration vérifiée depuis moins de 36 h (db/backup.sh etat)
```

  `scripts/compose.sh` = `docker compose --env-file /etc/pokeshop/api.env` (autre chemin : `POKESHOP_ENV_FILE`) ; il refuse un `.env` dans le dépôt et un fichier de variables lisible par d'autres. Chaque conteneur ne reçoit que ses variables (en-tête de `docker-compose.yml`). Ordre d'activation des workflows : `orchestration/README.md` ; sauvegardes : `db/README.md`.

## Décisions qui t'attendent

1. **Nom et direction visuelle** : A « Quai » ou B « Pochette » (`docs/05-da/`), une seule validation.
2. **Mandat** : montants, fournisseurs autorisés, signature **et empreinte au coffre** (`docs/00-pilotage/DELEGATION_AUTONOMIE.md`) ; puis tes jetons (le tien, un par agent) et la signature des seuils.
3. **Point zéro du stop-loss global** : le décider à J3 avec le budget, puis le poser avec ton jeton dès la mise en service de l'API, après l'enregistrement de tes apports et une première photo acceptée ; sans lui, le gel tombe avant la première vente (`docs/00-pilotage/STOP_LOSS.md` §5).
4. **Écarts bloquants du BP** : `docs/00-pilotage/ECARTS_BP.md` (ex. distributeur suisse Carletto AG absent du BP).
5. **Statut exploitant et TVA** avec la fiduciaire : le moteur a deux profils, il ne choisit pas.

Spécification technique commune : `docs/SPEC.md`.
