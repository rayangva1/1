# Tableau de bord interne — {{NOM_BOUTIQUE}}

> **INTERNE — contient coûts et marges, ne jamais publier** (BP §7 : coût et marge visibles exclusivement dans le tableau de bord interne).
> Version du 5.10.2026, agent « orchestration-dashboard ». Spécification : `docs/07-ops/ROUTINES_PILOTAGE.md` §3.2, §4, §5 et §6 ; BP §12 « Tableau de bord à consulter ».

## 1. Ce que montre chaque vue (dans cet ordre)

| Bloc | Jour | Semaine | Mois |
|---|---|---|---|
| 1. **Étoile polaire** | Contribution nette cumulée, dernière semaine close et son delta, semaine en cours, moyenne des 4 dernières semaines closes, tendance, graphique hebdomadaire | Idem, arrêtée à la fin de la semaine | Idem, arrêtée à la fin du mois |
| 2. **Stop-loss** | Six niveaux (produit, extension, pub, cash, global, temps) : déclencheurs avec mesure, seuil, action, cause ; en cas de gel global, **comment réarmer** (propriétaire seule) | Idem | Idem |
| 3. Décisions attendues | Gels, démarques, dépenses hors mandat (échéance 24 h), réassorts à valider, incidents à décision | Idem | Idem |
| 4. Indicateurs | Ventes payées, contribution du jour, cash disponible (réserve 1 600 CHF), commandes à préparer (délai d'expédition), ruptures locales, offres périmées (> 24 h) et flux en panne, incidents ouverts | Contribution nette, CAC (commandes payées nettes), réachat, rotation et exposition par extension (plafond 25 %), produits sans vente (14 / 30 / 45 j), écarts de coûts (> 2 %), litiges, remboursements, coût SAV par commande (provision 1 CHF), réassorts proposés, heures de la propriétaire | Résultat (contribution nette du mois), heures, taux horaire implicite, résultat après valorisation du temps, seuil TVA (12 mois glissants de **toute l'entité** / 100 000 CHF, alerte à 70 %), budget stock restant, marge sous le plafond par extension, dépenses outils (enveloppe 180 CHF) |

Un indicateur « Indisponible » signale une **source non branchée**, jamais un zéro inventé ; la liste des sources manquantes est affichée en bas de chaque vue.

## 2. Utiliser

| Besoin | Commande |
|---|---|
| Régénérer l'exemple de démonstration (données **FICTIVES**) | `python dashboard/build.py` |
| Vérifier que l'exemple committé est à jour | `python dashboard/build.py --check` |
| Tableau de bord réel depuis l'API (lecture seule) | `POKESHOP_API_TOKEN=… python dashboard/build.py --api http://127.0.0.1:8000 --out ~/pokeshop/tableau.html` (sans `--out` : `~/.pokeshop/tableau_de_bord.html`) |
| Une période précise | `--day 2026-11-13`, `--week 2026-11-10` (un jour de la semaine), `--month 2026-11` |
| JSON brut | `GET /dashboard/daily?day=…`, `GET /dashboard/weekly?week=…`, `GET /dashboard/monthly?month=…` avec l'en-tête `X-Pokeshop-Token` |

Le jeton se lit **uniquement** dans la variable d'environnement `POKESHOP_API_TOKEN` (jamais en argument : il resterait dans l'historique). Le fichier produit depuis l'API contient des coûts réels : `build.py` **refuse** toute sortie située dans le dépôt (code 2, liens symboliques résolus) — y compris l'exemple FICTIF `dashboard/out/index.html` suivi par git —, écrit par défaut hors du dépôt et en mode 600 ; `.gitignore` ignore toute autre page de `dashboard/out/`. Le garder hors de tout partage.

## 3. Fichiers

| Chemin | Rôle |
|---|---|
| `engine/pokeshop/dashboard.py` | Calcul des indicateurs (Decimal, déterministe) et jeu de démonstration FICTIF `demo_inputs()` |
| `engine/pokeshop/api_dashboard.py` | Routes `GET /dashboard/daily|weekly|monthly` (même authentification que l'API, lecture ouverte par la matrice `docs/08-agents/MATRICE_API.md` : jeton commun **ou jeton d'un rôle** ; `Cache-Control: no-store`, `noindex`) ; journal d'état non relu au démarrage => KPI « indisponible » (étoile polaire « journal non relu », jamais « aucune écriture » ni 0) ; sources branchables via `app.state.dashboard_provider` |
| `dashboard/build.py` | Page HTML autonome (aucune ressource externe, clair/sombre, mobile, lisible sans JavaScript) |
| `dashboard/out/index.html` | Exemple généré sur les données FICTIVES (photo du lundi 16.11.2026 07:30) |
| `tests/test_dashboard.py` | Valeurs calculées à la main, routes, page |

## 4. Sources aujourd'hui branchées dans l'API

Étoile polaire (journal du moteur), stop-loss (photo d'activité **construite par le moteur** à partir de ses registres par `POST /stoploss/state/refresh`, workflow 07 ; ou déposée par `POST /stoploss/state` avec un jeton nommé, sans mouvement de capital), cash et exposition par extension (même photo), incidents, registre du mandat, niveau d'autonomie, registre de stock local (alimenté par `POST /stock/receive`, workflow 06). La photo n'existe que si ses sources sont présentes et récentes : apports de capital (`POST /capital/movements`, jeton de la propriétaire), soldes PayPal et banque de moins de 24 h (connecteurs, `/treasury/*-balance`), dettes et créances déclarées (`POST /treasury/balance-items`, jamais supposées nulles), stock au coût historique (`POST /costs/movements`) ; sinon le stop-loss reste « non évaluable » (dépenses refusées) et le bloc 2 l'affiche. **À brancher** (agent integrations, base PostgreSQL) : commandes Shopify non expédiées, offres importées, ventes au coût historique, propositions de réassort, écarts de facture, journal SAV, heures, CA de l'entité, dépenses outils ; calcul des dettes (précommandes encaissées, factures non payées) à partir des commandes et factures.

## Validation humaine requise

- [ ] Fixer le taux horaire de valorisation du temps (`TAUX_HORAIRE_VALORISATION`) : sans lui, le résultat après valorisation reste « Indisponible ».
- [ ] Valider avec la fiduciaire le seuil d'alerte TVA à 70 % et la source du CA déterminant de toute l'entité.
- [ ] Valider le délai d'expédition (3 jours ouvrés, hypothèse) qui déclenche l'alerte « commandes en retard ».
- [ ] Décider où le tableau de bord réel est consulté (poste local ou accès protégé) : jamais sur le site public ni un partage ouvert.
