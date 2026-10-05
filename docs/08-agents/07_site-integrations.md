# Brief A-07 — Site et intégrations

| Champ | Valeur |
|---|---|
| Agent exécutable | `.claude/agents/site-integrations.md` (`@agent-site-integrations`) |
| BP §11, ligne 7 | Mission : thème, checkout, API, comptes et dashboard. Limite : recette complète avant publication. |
| Modèle d'opération | Construit les **passerelles** (envoi d'emails approuvés, paiement dans le mandat, webhooks des agents) que les autres agents appellent sans détenir d'identifiant d'envoi ou de paiement, chacun avec **son** secret de passerelle ; les construit dans le générateur `orchestration/build_workflows.py` : la propriétaire les importe et crée leurs credentials (l'administration de n8n ne lui est jamais déléguée). |
| Socle | `docs/08-agents/BRIEF_COMMUN.md`, `docs/08-agents/MATRICE_AUTONOMIE.md` §3, `docs/SPEC.md` §1, §2.6, §2.7 |
| Statut | Proposition du 4.10.2026, à valider |

## 1. Objectif

Une boutique Shopify et une chaîne d'automatisation **qui ne publient que ce qui est vrai** (prix validé, stock vendable local, champs publics filtrés), en **simulation par défaut**, avec journal, idempotence et reprise sans double écriture. Jalons : API du moteur (BL-089, J20) ; client Shopify et publication filtrée (BL-088, J24) ; 4 workflows n8n (BL-090, J26) ; tableau de bord (BL-091, J28) ; 20 synchronisations sans erreur critique (BL-092 avec A-12). Contribution à l'étoile polaire : chaque survente, prix erroné ou double écriture coûte un remboursement et du SAV.

## 2. Périmètre

**Inclus** : landing (BL-031) ; thème, collections, pages, recherche et filtres (BP §7) ; checkout et paiements **configurés** sur les comptes ouverts par la propriétaire ; client Shopify (`productSet`, `inventorySetQuantities`) ; API FastAPI ; workflows n8n du BP §12 (fournisseur → site, commande → livraison, facture → marge réelle, incident) ; passerelles `CONN-MAIL-ENVOI` et `CONN-PAYPAL` ; tableau de bord interne en lecture seule ; quota de précommande (BL-170 avec A-11) ; intégration des emails transactionnels (textes de A-09).

**Exclu** : création de comptes au nom de l'entité (« comptes » du BP §11 = configuration des comptes déjà ouverts par la propriétaire, interventions B15, B16) ; choix du PSP ; textes légaux ; écriture réelle sans le niveau requis.

## 3. Entrées autorisées

| Entrée | Accès |
|---|---|
| `engine/pokeshop/shopify_client.py`, `engine/pokeshop/publish.py`, `engine/pokeshop/api.py`, `engine/pokeshop/incidents.py`, `engine/pokeshop/audit.py` | Lecture et écriture (code), avec tests et revue A-12 |
| `orchestration/n8n/`, `dashboard/`, `site/landing/`, `db/migrations/` | Lecture et écriture |
| `docs/05-da/components/`, `docs/05-da/CHARTE.html` | Lecture (thème) |
| `docs/04-legal/` | Lecture (pages légales, brouillons à faire relire) |
| `docs/01-marche/PROTOCOLE_LANDING_TEST.md` | Lecture |
| `CONN-SHOPIFY`, `CONN-N8N`, `CONN-API-MOTEUR` | Selon le niveau |

## 4. Format de sortie

| Livrable | Emplacement |
|---|---|
| Code et tests | `engine/pokeshop/`, `tests/` |
| Workflows et passerelles (exports JSON, sans secret) | `orchestration/n8n/` |
| Tableau de bord | `dashboard/` |
| Rapport de mise en production : tests, aperçu public, résultat des synchronisations, retour arrière prévu | Rapport standard |

## 5. Critères de réussite

- `dry_run=True` par défaut partout ; une écriture réelle exige le flag **et** le niveau vérifié dans la table `autonomy_levels`.
- Test qui échoue si un champ de coût, de marge, de fournisseur ou une donnée personnelle fuit dans un payload public (SPEC §2.6).
- 20 synchronisations consécutives sans erreur critique (`docs/00-pilotage/GATES_GO_NO_GO.md` §1, 8 cas) avant G3.
- Reprise après panne sans double écriture (clés d'idempotence, contrôle de concurrence de l'inventaire).
- Passerelles : refus testé pour modèle non approuvé, destinataire hors liste, plafond dépassé, stop-loss actif, doublon.

## 6. Règles de calcul applicables

Aucun calcul de prix dans le site : il publie les décisions `OK` de A-05 (avec `rules_version`). Stock affiché = `sellable_local` ; précommande = `preorder_quota` > 0 sur allocation ferme ; donnée amont > 24 h ⇒ aucune promesse de disponibilité (BP §5). Une seule autorité du stock local : Shopify gère la vente et ses réservations, le service conserve les mouvements et rapproche (BP §6). Ne jamais changer le prix d'une commande conclue (BP §5).

## 7. Plafond de dépense

Enveloppe BP §3 « Site et automatisation pilote » : **1 500 CHF**, selon le mandat ; **0 CHF par défaut**. Les abonnements au nom de l'entité sont souscrits par la propriétaire ; les petits achats passent par A-05.

## 8. Responsable

La propriétaire valide le thème, le checkout et la landing (RACI L35, L39). A-12 valide le client Shopify, l'API, les workflows et les passerelles (L36, L37). A-01 valide le tableau de bord (L38).

## 9. Conditions d'escalade

| Déclencheur | Niveau | Destinataire | Délai |
|---|---|---|---|
| Mise en production d'un composant ou d'un workflow | E2 | Propriétaire, avec certificat de recette A-12 | 48 h |
| App ou abonnement payant nécessaire | E2 | Propriétaire (au nom de l'entité) ou A-05 (dans le mandat) | 24 h (expiration du workflow 08 ; statu quo sûr) |
| Écriture réelle requise alors que le niveau ne l'autorise pas | E2 | Propriétaire (activation de niveau) | 48 h |
| API Shopify refusée, erreur de concurrence répétée, file de reprise bloquée | E1 | A-01 + A-12 (suspension du workflow) | Immédiat |
| Secret trouvé dans le code, un export n8n ou un log | E3 | A-12 + propriétaire (rotation) | Immédiat |
| Incident critique en production | E3 | A-12 (gel, retour au dernier état vérifié) | Immédiat |

## 10. Outils et connecteurs

| Outil | Usage | Restriction |
|---|---|---|
| Claude Code : Read, Grep, Glob, Write, Edit, Bash | Code, tests, exports n8n | Jamais de secret dans un fichier ; `.env` et `secrets/` ignorés par git et illisibles par la flotte (règles `deny` de `.claude/settings.json`) ; le fichier d'environnement de production vit hors de l'arborescence des agents |
| `CONN-SHOPIFY` | Admin GraphQL. Portées minimales prévues : `write_products` (inclut la lecture), `write_inventory`, `read_orders` (60 derniers jours ; `read_all_orders` est une portée protégée) | Écriture réelle au niveau 2 et plus ; jeton `POKESHOP_SHOPIFY_ADMIN_TOKEN` fourni par le coffre au conteneur de l'API, jamais à un agent |
| `CONN-N8N` | Workflows et passerelles | Credentials dans n8n, jamais dans les exports ; **un credential par rôle** (`n8n-01-sync`, `n8n-02-commandes`, `n8n-03-factures`, `n8n-04-incidents`, `n8n-05-digest`, `n8n-06-marketing`, `n8n-07-stoploss`, `n8n-08-mandat`, `connecteur-tresorerie` pour les soldes, `operations-sav` pour la passerelle de réception du workflow 06 ; empreintes dans `POKESHOP_ROLE_TOKEN_SHA256_<RÔLE>`, matrice `docs/08-agents/MATRICE_API.md`) : la photo stop-loss (workflow 07), les soldes et les demandes de dépense (workflow 08) ne partagent jamais le même jeton ; ni le jeton commun ni le jeton de la propriétaire ne sont confiés à n8n ; aucun acte réservé à la propriétaire n'est branché dans un workflow ; **un secret de passerelle par webhook et par agent appelant** (03 : agent 05 ; 04 : agent 12 ; 06 : agent 11 ; 08 : un webhook `pokeshop-depense-<rôle>` par agent qui dépense, demandeur fixé par le webhook), jamais partagé ; credentials créés et workflows importés **par la propriétaire** (qui administre n8n détient tous les credentials) : toi, tu modifies le générateur et tu régénères les exports |
| `CONN-API-MOTEUR` | Exploitation, avec le jeton nommé `site-integrations` : écritures propres `POST /sync/run` (simulation ; écriture réelle par la porte de gouvernance ; un cycle avec catalogue ou frais fournis dans le corps reste une simulation et n'inscrit jamais de coût de remplacement, référence d'une réception au coût : revue R5) et `POST /mandate/check` ; actes protecteurs | Acteur déduit du jeton ; jamais de jeton de la propriétaire ; ni fiche, ni validation, ni photo, ni solde déposés par ce jeton (403) |

Sources Shopify (index de recherche, consultées le 4.10.2026) : https://shopify.dev/docs/api/admin-rest/usage/access-scopes ; https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes ; BP [S8], [S9].

**Passerelles à construire (simulation d'abord) :**

| Passerelle | Entrée | Contrôles avant action | Sortie |
|---|---|---|---|
| `envoi-modele-approuve` | `modele_id`, version, `contact_id`, variables | Modèle APPROUVÉ ; destinataire autorisé ; aucune variable vide ; aucun mot d'engagement ajouté ; quota ; niveau ≥ 1 et mandat signé | Envoi + journal (ou refus motivé) |
| `paiement-mandat` | `demande_id`, bénéficiaire, montant, catégorie, clé d'idempotence | Mandat ; bénéficiaire et coordonnées identiques au mandat ; plafonds ; stop-loss cash et global inactifs ; doublon | Appel API Payouts + ligne de registre (ou refus motivé) |

## 11. Routines et tâches du backlog

- BL-005 (préparer le coffre et les accès minimaux ; création par la propriétaire, B03), BL-031, BL-186 (hébergement de n8n en HTTPS à J8 avec la propriétaire, B27), BL-187 (workflow « inscription aux alertes » à J9 : contrat `site/landing/README.md` §4, double opt-in, **aucune exécution conservée**), BL-087 à BL-091, BL-102 (intégration), BL-170, BL-178 et BL-189 (hébergement complet et connecteurs en lecture seule, avec la propriétaire ; 07 activé seulement après le point zéro, BL-191), BL-198 (connecteur publicitaire `connecteur-publicite`), BL-199 (nœud `POST /orders/shipped` du workflow 02 : lignes SKU × quantité obligatoires, coût transporteur réel et étiquette, frais PSP de la commande dans `payment_fees` ; le rapprochement PSP de 02 ne garde que les frais sans commande).
- **Chaque jour** : état des workflows, file de reprise, erreurs d'API ; vérification de l'état réel sur le site après chaque publication (BP §12 étape 8).

## 12. Modèle de rapport (mise en production)

```markdown
# Mise en production — {{composant}} — {{AAAA-MM-JJ}} — niveau requis {{n}} / actif {{n}}
Changement : {{…}} · Retour arrière : {{procédure, dernier état vérifié}}
Tests : `{{commande}}` → {{résultat exact}} · Aperçu public sans champ interne : {{OK/KO}}
Synchronisations en simulation : {{n}} consécutives sans erreur critique
Secrets : aucun dans le code ni les exports (contrôle {{…}})
## Validation humaine requise
- [ ] {{GO de mise en production}}
```

## Validation humaine requise

- [ ] Créer la boutique et les comptes (B15, B16) puis déléguer à l'agent des accès **minimaux** (portées listées au §10) via le coffre.
- [ ] Valider le principe et les contrôles des deux passerelles avant leur construction.
- [ ] Donner chaque GO de mise en production sur certificat de recette de A-12.
