# Carte du dépôt pour la flotte

> Les fichiers et modules du dépôt que les agents utilisent, avec leur propriétaire de construction et les agents qui s'en servent en exploitation. Statut au **5.10.2026** : « présent » (fichier livré) ou « attendu » (prévu par `docs/SPEC.md` ou par un autre agent de build, pas encore livré).
> Le vérificateur `docs/08-agents/outils/verifier_agents.py` contrôle que chaque chemin cité dans `docs/08-agents/` et `.claude/agents/` existe **ou** figure ici comme « attendu ». Un chemin « attendu » déjà livré est une **erreur** : la carte doit être mise à jour (sinon un agent croirait qu'il manque et appliquerait une consigne de repli périmée).
> Lecture seule pour la flotte, sauf mention « écriture » dans le brief de l'agent.

## 1. Sources de vérité

| Chemin | Rôle | Propriétaire (build) | Agents (exploitation) | Statut |
|---|---|---|---|---|
| `docs/business-plan/business_plan_extrait.txt` | Texte du BP, source métier de vérité | — | tous | présent |
| `docs/SPEC.md` | Contrat technique commun, principes non négociables | — | tous | présent |
| `config/pricing_rules.v1.yaml` | Règles de prix et de stock versionnées (2 profils TVA) | core-engine | 05 (propose une nouvelle version), 12, 04, 07 | présent |
| `docs/00-pilotage/DELEGATION_AUTONOMIE.md` | Mandat écrit : plafonds, fournisseurs autorisés, interdits, journal | gouvernance | tous | présent |
| `config/mandate.v1.yaml` | Mandat lu par la machine (actif seulement si son empreinte est au coffre) | gouvernance | 05, 12 (lecture) | présent |
| `config/stoploss.v1.yaml` | Seuils des six stop-loss (signés par la propriétaire au coffre) | gouvernance | 12, 05, 10 (lecture) | présent |
| `.claude/settings.json` | Permissions Claude Code du projet : règles `deny` seulement (secrets illisibles par la flotte) | flotte-agents | Claude Code | présent |
| `docs/00-pilotage/STOP_LOSS.md` | Définition des six stop-loss | gouvernance | 12, 05, 10, 01 | présent |
| `docs/00-pilotage/ETOILE_POLAIRE.md` | Définition de la métrique unique | gouvernance | 05, 01 | présent |

## 2. Moteur `engine/pokeshop/`

| Chemin | Rôle | Propriétaire (build) | Agents (exploitation) | Statut |
|---|---|---|---|---|
| `engine/pokeshop/models.py` | Types partagés (`PricingParams`, `LandedCostInput`, `PriceDecision`…) | core-engine | 05, 12 | présent |
| `engine/pokeshop/pricing.py` | Coût rendu, prix plancher, arrondi, contribution, décision, panier | core-engine | 05, 12, 10 | présent |
| `engine/pokeshop/costs.py` | Coût historique par lot, coût de remplacement, historique des prix | core-engine | 05, 11, 12 | présent |
| `engine/pokeshop/stock.py` | Stock vendable, quotas de précommande, fraîcheur, promesse, réassort | core-engine | 11, 05, 04, 12 | présent |
| `engine/pokeshop/rules.py` | Chargement et validation des règles versionnées | core-engine | 05, 12 | présent |
| `engine/pokeshop/treasury.py` | Trésorerie 13 semaines, stop-loss cash | finance | 05, 12 | présent |
| `engine/pokeshop/forecast.py` | Scénarios, seuils, sensibilité, étoile polaire, stop-loss global | finance | 05, 01, 12 | présent |
| `engine/pokeshop/errors.py` | Exceptions du moteur | core-engine | 12 | présent |
| `engine/pokeshop/stoploss.py` | Évaluation des six stop-loss, gel verrouillé, réarmement par la propriétaire ; **seule source** de l'état des stop-loss | gouvernance | 12, 05, 10 | présent |
| `engine/pokeshop/mandate.py` | Contrôle de chaque dépense (`check`), registre du mandat (`SpendLedger`), registres des taux et des révocations | gouvernance | 05, 12 | présent |
| `engine/pokeshop/northstar.py` | Registre de l'étoile polaire (`NorthStarLedger`) | gouvernance | 05, 01, 12 | présent |
| `engine/pokeshop/autonomy.py` | Niveaux d'autonomie et porte de gouvernance (niveau + mandat + stop-loss) | integrations | 12, 07 | présent |
| `engine/pokeshop/settings.py` | Variables d'environnement (noms seulement : empreintes, jetons nommés) | integrations | 07, 12 | présent |
| `engine/pokeshop/sync.py` | Cycles de synchronisation (`/sync/run`, simulation par défaut) | integrations | 07, 12 | présent |
| `engine/pokeshop/catalog.py` | Identité produit, normalisation, GTIN, rapprochement | data-pipeline | 04, 03, 12 | présent |
| `engine/pokeshop/importers/` | Connecteurs fournisseurs CSV, XLSX, XML, quarantaine | data-pipeline | 03, 12 | présent |
| `engine/pokeshop/shopify_client.py` | Client Admin GraphQL, `dry_run=True`, idempotence | integrations | 07, 12 | présent |
| `engine/pokeshop/publish.py` | Payloads `productSet` à champs publics filtrés | integrations | 07, 04, 12 | présent |
| `engine/pokeshop/api.py` | API FastAPI appelée par n8n et les agents (jeton nommé par agent ; actes réservés au jeton de la propriétaire) | integrations | 03, 04, 05, 07, 10, 11, 12 | présent |
| `engine/pokeshop/incidents.py` | Quarantaine, suspension, notification, reprise | integrations | 12, 03, 01 | présent |
| `engine/pokeshop/audit.py` | Journal append-only | integrations | 12 | présent |
| `tests/` | Tests du moteur (`python -m pytest -q`) | core-engine, finance, integrations | 12 | présent |

## 3. Données, base, orchestration, site

| Chemin | Rôle | Propriétaire (build) | Agents (exploitation) | Statut |
|---|---|---|---|---|
| `data/samples/` | Jeux d'essai FICTIFS | data-pipeline | 03, 12 | présent |
| `data/supplier_mappings/` | Dictionnaires de champs YAML par fournisseur | data-pipeline | 03 (écriture), 12 | présent |
| `db/migrations/` | Migrations SQL PostgreSQL | data-pipeline | 07, 12 | présent |
| `orchestration/n8n/` | Les 8 workflows : les 4 du BP §12, le digest, le marketing, la surveillance du stop-loss et le contrôle des dépenses | integrations | 07 (écriture), 03, 12 | présent |
| `site/landing/` | Page de présentation et inscription aux alertes | site | 07, 09, 12 | présent |
| `dashboard/` | Tableau de bord interne en lecture seule | integrations | 07, 01, 05 | présent |

## 4. Dossiers de pilotage et métier

| Chemin | Rôle | Propriétaire (build) | Agents (exploitation) | Statut |
|---|---|---|---|---|
| `docs/00-pilotage/BACKLOG.csv` | Backlog (tâches BL-nnn) | pilotage | 01 (écriture) | présent |
| `docs/00-pilotage/PLAN_90_JOURS.md` | Plan au jour puis à la semaine | pilotage | 01 | présent |
| `docs/00-pilotage/GATES_GO_NO_GO.md` | Gates G0 à G7, « erreur critique », modèle de fiche | pilotage | 01, 05, 12 | présent |
| `docs/00-pilotage/INTERVENTIONS_HUMAINES.md` | Ce qui exige la propriétaire (A, B, C) | pilotage | 01 | présent |
| `docs/00-pilotage/ECARTS_BP.md` | Registre des écarts du BP | pilotage | 01 | présent |
| `docs/00-pilotage/REGISTRE_RISQUES.md` | Registre des risques | pilotage | 01, 12 | présent |
| `docs/01-marche/GRILLE_CONCURRENCE.csv` | Relevés de prix concurrents (URL + date) | pilotage | 02, 05 | présent |
| `docs/01-marche/PROTOCOLE_CONCURRENCE.md` | Méthode de relevé et référence marché | pilotage | 02, 05 | présent |
| `docs/01-marche/PROTOCOLE_LANDING_TEST.md` | Test de la landing, KPI | pilotage | 07, 09, 10 | présent |
| `docs/01-marche/ASSORTIMENT_PILOTE.md` | Enveloppes par extension, références en stock | pilotage | 02, 05, 11 | présent |
| `docs/01-marche/GUIDE_ENTRETIENS.md` | Entretiens clients | pilotage | 09 | présent |
| `docs/01-marche/QUESTIONNAIRE.md` | Questionnaire en ligne | pilotage | 09 | présent |
| `docs/02-sourcing/DOSSIER_B2B.md` | Dossier professionnel | sourcing | 02 (écriture) | présent |
| `docs/02-sourcing/EMAILS_FOURNISSEURS.md` | Emails de premier contact et relances | sourcing | 02, 01 | présent |
| `docs/02-sourcing/PANIER_PILOTE.csv` | Panier pilote commun aux fournisseurs | sourcing | 02, 04, 05 | présent |
| `docs/02-sourcing/TRACKER_CONTACTS.csv` | Suivi des contacts | sourcing | 02 (écriture), 01 | présent |
| `docs/02-sourcing/CHECKLIST_DUE_DILIGENCE_FOURNISSEUR.md` | Due diligence fournisseur | sourcing | 02, 12 | présent |
| `docs/02-sourcing/COMPARATEUR_OFFRES.xlsx` | Comparateur de coût rendu | sourcing | 05 (écriture), 02 | présent |
| `docs/02-sourcing/outils/generer_comparateur.py` | Régénération du comparateur (réécrit le classeur du dépôt : 05 seulement ; 12 passe par `docs/08-agents/outils/controle_generateurs.py`) | sourcing | 05 | présent |
| `docs/03-finance/modele_financier.xlsx` | Modèle financier et feuille étoile polaire | finance | 05 (écriture) | présent |
| `docs/03-finance/tresorerie_13_semaines.xlsx` | Trésorerie glissante | finance | 05 (écriture) | présent |
| `docs/03-finance/NOTE_VERIFICATION_BP.md` | Vérification chiffrée du BP | finance | 05, 01 | présent |
| `docs/03-finance/generer_classeurs.py` | Régénération des classeurs (réécrit les classeurs du dépôt : 05 seulement ; 12 passe par l'outil de contrôle) | finance | 05 | présent |
| `docs/04-legal/` | Brouillons CGV, livraison et retours, confidentialité, mentions, précommandes | légal | 12, 09, 11, 07 | présent |
| `docs/05-da/NAMING.md` | Pistes de nom | da | 06 | présent |
| `docs/05-da/CHARTE.html` | Mini-charte | da | 06, 07, 09 | présent |
| `docs/05-da/components/` | Composants (badges, cartes, emails) | da | 06, 07, 09 | présent |
| `docs/05-da/social/` | Templates réseaux sociaux | da | 06, 09, 10 | présent |
| `docs/05-da/packaging/NOTE_CHIFFRAGE.md` | Packaging et devis | da | 06, 11 | présent |
| `docs/05-da/tools/generer_da.py` | Génération des fichiers DA | da | 06 | présent |
| `docs/05-da/tools/verifier_da.py` | Contrôles DA (termes internes, contrastes) | da | 06, 12 | présent |
| `docs/06-contenu/` | Sujets, calendrier, emails, scripts, ton | contenu | 08, 09 | présent |
| `docs/07-ops/` | SOP réception, colis, SAV, retours, incidents | ops | 11, 12 | présent |

## 5. Flotte d'agents

| Chemin | Rôle | Propriétaire (build) | Agents (exploitation) | Statut |
|---|---|---|---|---|
| `docs/08-agents/BRIEF_COMMUN.md` | Brief commun | flotte-agents | tous | présent |
| `docs/08-agents/ORGANIGRAMME.md` | Dépendances, flux d'exceptions, RACI | flotte-agents | tous | présent |
| `docs/08-agents/MATRICE_AUTONOMIE.md` | Autonomie par agent et par niveau | flotte-agents | tous | présent |
| `docs/08-agents/RUNBOOK.md` | Utilisation quotidienne | flotte-agents | propriétaire, 01 | présent |
| `docs/08-agents/outils/verifier_agents.py` | Vérificateur de la flotte (frontmatter, outils, permissions, consignes périmées) | flotte-agents | 12 | présent |
| `docs/08-agents/outils/controle_generateurs.py` | Contrôle en lecture seule des classeurs générés (générateurs exécutés en dossier temporaire) | flotte-agents | 12 | présent |
| `docs/08-agents/modeles/` | Gabarits (rapport, exception, dispatch, engagement, emails, registre) | flotte-agents | tous | présent |
| `docs/08-agents/rapports/` | Rapports d'agents (exploitation) | flotte-agents | tous (écriture) | présent |
| `docs/08-agents/exceptions/` | Fiches d'exception (exploitation) | flotte-agents | tous (écriture) | présent |
| `.claude/agents/` | Les 12 agents exécutables | flotte-agents | Claude Code | présent |

## Validation humaine requise

- [ ] Confirmer que les rapports et fiches d'exception peuvent vivre dans le dépôt (ils contiennent des coûts internes, jamais de données personnelles) ou désigner un autre emplacement privé.
- [ ] Désigner l'emplacement hors dépôt des pièces fournisseurs réelles (variable `POKESHOP_DOCS_PRIVES`).
