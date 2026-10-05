# Runbook — utiliser la flotte au quotidien

> Pour la propriétaire. Comment lancer les agents dans Claude Code, quoi leur demander, comment décider des exceptions et quelles routines tenir. Règles : `docs/08-agents/BRIEF_COMMUN.md`. Qui fait quoi : `docs/08-agents/ORGANIGRAMME.md`. Ce que chaque agent peut faire : `docs/08-agents/MATRICE_AUTONOMIE.md`.
> Fonctionnement de Claude Code vérifié le 4.10.2026 sur https://code.claude.com/docs/en/sub-agents (sous-agents de projet dans `.claude/agents/`, mention `@agent-<nom>`, option `--agent`, restriction `Agent(...)`) et sur la version installée dans l'environnement de build (`claude --version` : 2.1.289).

## 1. En bref

| Quand | Quoi | Durée estimée | Commande |
|---|---|---|---|
| Chaque jour ouvré, le matin | Lire la synthèse, décider les exceptions du jour | 10 min **(hypothèse)** | `claude --agent chef-de-projet` puis « Revue du jour » |
| Jours d'expédition | Préparer et déposer les colis listés | ≈ 10 à 15 min par colis (à mesurer, BL-171) | Liste de `operations-sav` |
| Lundi | Revue hebdomadaire : étoile polaire, trésorerie, stop-loss, exceptions, calendrier | 45 à 60 min **(hypothèse)** | « Revue du lundi » |
| Mensuel | Résultat avec valorisation du temps, seuil TVA, inventaire physique, accès, restauration | 1 h 30 **(hypothèse)** | « Revue du mois » |
| Sur alerte E3 | Lire l'avis de gel, décider | Selon le cas | Fiche dans `docs/08-agents/exceptions/` |

## 2. Mise en route (une seule fois)

1. **Prérequis** : Claude Code installé (`claude --version`) ; un terminal ouvert à la racine du dépôt. Les 12 agents de `.claude/agents/` sont découverts automatiquement comme sous-agents du projet.
2. **Vérifier les définitions** :
   ```bash
   python docs/08-agents/outils/verifier_agents.py
   python -m pytest -q docs/08-agents/outils
   ```
3. **Mandat** : signer `docs/00-pilotage/DELEGATION_AUTONOMIE.md` (intervention B01) et noter le niveau d'autonomie 1 (BL-006). Sans mandat signé, les agents préparent mais n'envoient ni ne dépensent rien.
4. **Secrets** : créer le coffre (B03). Les valeurs des variables listées dans `docs/08-agents/BRIEF_COMMUN.md` §10 restent dans le coffre ou dans le fichier de variables **hors du dépôt** créé par la propriétaire (B23) : `sudo install -D -m 600 .env.example /etc/pokeshop/api.env`, rempli depuis le coffre ; la pile ne se lance que par `scripts/compose.sh` (`docker compose --env-file /etc/pokeshop/api.env`, autre chemin : `POKESHOP_ENV_FILE`), qui refuse tout `.env`, `.env.*` ou `*.env` dans le dépôt et un fichier de variables lisible par d'autres. **Jamais** de `.env` à la racine du dépôt : docker compose le lirait tout seul et les agents travaillent dans cette arborescence (le `.gitignore` exclut `.env` et `secrets/`, mais ignorer n'est pas protéger). Les sessions Claude Code de la flotte ne reçoivent aucun secret dans leur environnement : chaque agent ne connaît que la **référence** de son propre jeton nommé (B22).
5. **Permissions** : garder le mode de permission par défaut (Claude Code demande avant d'exécuter une commande ou d'écrire). Ne pas utiliser le contournement des permissions pour la flotte. Le fichier `.claude/settings.json` du projet ne contient **que des règles `deny`** : lecture de `.env`, `secrets/`, clés, coffre local (`/etc/pokeshop/`), environnement des processus (`env`, `printenv`, `/proc/*/environ`, `docker compose config`, `docker inspect`). C'est un filet de sécurité : un motif Bash se contourne (un script Python peut lire un fichier), d'où la règle première, ne jamais placer un secret là où un agent travaille. N'y ajoutez jamais de règle `allow` (le vérificateur `verifier_agents.py` la refuse).
6. **Connecteurs** : aucun n'est actif au 4.10.2026. Les activer un par un (§8).

## 3. Lancer un agent

| Besoin | Comment | Exemple |
|---|---|---|
| **Piloter la journée** (recommandé) | Session complète avec le chef de projet comme fil principal ; il délègue aux 11 autres agents | `claude --agent chef-de-projet` |
| Confier une tâche précise à un agent | Dans une session Claude Code, mentionner l'agent | `@agent-finance-pricing calcule…` |
| Laisser Claude choisir | Langage naturel | « Utilise l'agent sourcing pour préparer la relance J+5. » |
| Routine non interactive | Mode impression | `claude -p --agent qa-conformite "État des six stop-loss et tests du moteur"` |

En mode impression (`-p`), personne ne peut répondre aux demandes de permission : une commande non pré-autorisée (par exemple `python -m pytest` pour le QA) est refusée. Pour une routine planifiée, pré-autoriser seulement les commandes de lecture nécessaires (voir « Validation humaine requise »).

Le chef de projet ne peut déléguer qu'aux 11 agents de la flotte (outil `Agent(...)` restreint). Les autres agents ne délèguent pas. Chaque agent rend un rapport au format standard (`docs/08-agents/modeles/RAPPORT_AGENT.md`) ; le chef de projet les archive dans `docs/08-agents/rapports/`.

## 4. Demandes types, prêtes à copier

**Chef de projet**
- « Revue du jour : boîte dédiée, exceptions ouvertes, état des stop-loss, échéances du backlog. Donne-moi la synthèse en 15 lignes et la liste des décisions que j'ai à prendre. »
- « Prépare la fiche du gate G2 avec les preuves, et dis-moi quels critères sont ROUGES. »
- « Revue du lundi : étoile polaire, trésorerie 13 semaines, stop-loss, exceptions de la semaine, calendrier de communication à valider. »

**Sourcing**
- « @agent-sourcing prépare les relances J+5 des fournisseurs sans réponse (BL-044), brouillons seulement, et mets à jour le tracker. »
- « @agent-sourcing structure le devis reçu de {{fournisseur}} (pièce du {{date}}) au format du brief, avec les inconnus et la demande de précision MOD-02. »

**Données fournisseurs**
- « @agent-donnees-fournisseurs écris le dictionnaire de champs pour l'exemple de fichier de {{fournisseur}} et lance un import en simulation ; rapport avec la quarantaine. »

**Catalogue**
- « @agent-catalogue normalise les 10 références du panier pilote en tête de liste et produis l'aperçu de publication en simulation ; liste les champs manquants. »

**Finance et pricing**
- « @agent-finance-pricing calcule coût rendu, prix plancher, prix recommandé et contribution pour les lignes du comparateur, en profil EFFECTIVE et NOT_REGISTERED ; signale les REVIEW et BLOCKED. »
- « @agent-finance-pricing mets à jour la trésorerie 13 semaines avec le solde bancaire de ce matin : {{montant}} CHF. »
- « @agent-finance-pricing contrôle la demande d'engagement DEM-{{…}} et dis-moi si elle est dans le mandat. »

**Direction artistique**
- « @agent-direction-artistique décline la story 9:16 « nouveau stock » pour {{référence}} avec la photo réelle {{fichier}} ; vérifie avec verifier_da. »

**Site et intégrations**
- « @agent-site-integrations lance 20 synchronisations en simulation et rapporte les erreurs critiques éventuelles. »

**SEO et rédaction**
- « @agent-seo-redaction rédige le guide « ETB ou display : que choisir ? » avec le tableau des faits sourcés. »

**Communication**
- « @agent-communication propose le calendrier de la semaine prochaine (3 publications) avec un contrôle prix/stock prévu pour chaque nouveauté. »

**Acquisition**
- « @agent-acquisition prépare le plan du test publicitaire pour le gate G4 : 3 créations, plafond jour, critère d'arrêt, calendrier qui évite le Black Friday. »

**Opérations et SAV**
- « @agent-operations-sav liste les commandes à préparer aujourd'hui et les suivis à envoyer ; propose les réassorts de la semaine. »

**QA et conformité**
- « @agent-qa-conformite état des six stop-loss et suite de tests complète ; gèle si nécessaire et dis-moi pourquoi. »
- « @agent-qa-conformite certificat de recette pour passer au niveau 2. »

## 5. Routines

### Chaque jour ouvré (≈ 10 min)

1. `claude --agent chef-de-projet` → « Revue du jour ».
2. Lire la synthèse : ventes payées, contribution, cash disponible, commandes à préparer, ruptures locales, offres périmées, incidents (BP §12).
3. Décider les fiches E2 échues (§6). Ne rien décider d'autre.
4. Jours d'expédition : préparer et déposer les colis de la liste ; confirmer chaque scan.

### Lundi (≈ 45 à 60 min)

1. « Revue du lundi » (BL-162) : étoile polaire de la semaine et cumul, trésorerie 13 semaines (BL-165), état des stop-loss, rotation par extension, produits sans vente, CAC, réachat, écarts de coûts, litiges, remboursements, réassorts proposés (BP §12).
2. Valider en un bloc : calendrier de communication de la semaine, modèles d'emails nouveaux, propositions de réassort.
3. Registre des risques (BL-163) et écarts BP (BL-164) : accepter ou corriger les propositions.

### Mensuel (≈ 1 h 30)

Résultat avec valorisation du temps, seuil TVA (BP §10 : examen anticipé si l'activité annualisée approche 100 000 CHF), capacité de stock, dépenses d'outils (BP §12) ; inventaire physique (intervention A08) ; revue des accès et test de restauration (`qa-conformite`).

### Événements

| Événement | Ce que fait la flotte | Ce que vous faites |
|---|---|---|
| Gate (G0 à G7) | Fiche de gate avec preuves (`chef-de-projet`), chiffres (`finance-pricing`), tests (`qa-conformite`) | Décider GO, GO sous conditions, REPORT ou STOP (`docs/00-pilotage/GATES_GO_NO_GO.md`) |
| Réception de stock | Bon de réception, coût historique préparé | Compter, contrôler l'authenticité, photographier (A03, A04) |
| Nouveau fournisseur prêt | Due diligence, comparaison | Créer le compte (B11), l'ajouter au mandat (C08) |
| Stop-loss | Gel, avis motivé | §7 |

## 6. Décider une exception

1. Ouvrir la fiche dans `docs/08-agents/exceptions/` (ou la lire dans la synthèse). Elle contient : faits sourcés, impact sur l'étoile polaire, options A/B/C (A = statu quo sûr), recommandation, échéance.
2. Répondre au chef de projet en une ligne, avec cette grammaire :
   - `EXC-20261012-01 : APPROUVÉ option B`
   - `EXC-20261012-01 : APPROUVÉ SOUS CONDITIONS option B — plafond 120 CHF, valable 7 jours`
   - `EXC-20261012-01 : REFUSÉ — motif : …`
   - `EXC-20261012-01 : REPORTÉ au 2026-10-19 — il me manque : …`
3. Le chef de projet consigne la décision dans la fiche (qui, quand, quoi, conditions) et relance l'agent concerné.
4. Sans réponse dans le délai (24 h pour toute dépense hors mandat, que le workflow 08 fait expirer, et pour un gate ; 48 h pour les autres décisions) : **statu quo sûr**, rien n'est engagé, la proposition expire.

Une décision donnée dans une fiche ne modifie **pas** le mandat. Pour changer durablement un plafond ou une règle, voir §8.

## 7. Stop-loss

| Stop-loss | Ce qui se passe | Votre action |
|---|---|---|
| Produit | Vente et promo bloquées sur la référence | Décider démarque, retrait ou exception si une fiche E2 arrive |
| Extension | Plus de réassort ; démarque proposée | Décider la démarque |
| Pub | Campagne coupée | Décider un nouveau plan de test, ou rien |
| Cash | Plus d'achat ni de pub | Décider un apport, un report d'achat, ou attendre les versements |
| Temps | Dossier continuer / ajuster / arrêter | Décider sous une semaine |
| **Global** | **Tout est gelé, niveau 1, alerte** | **Vous seule pouvez réarmer** |

**Réarmer le stop-loss global** (checklist) :

- [ ] Lire l'avis de gel de `qa-conformite` (cause, périmètre, heure).
- [ ] Lire le dossier de `finance-pricing` : perte de valeur nette, cash disponible, engagements en cours, scénarios.
- [ ] Décider : réarmer avec ajustement (lequel), suspendre, ou arrêter (dossier d'arrêt : stock restant, abonnements, information des inscrits).
- [ ] Écrire la décision dans la fiche ; préciser le nouveau capital de référence si vous apportez des fonds.
- [ ] Depuis votre terminal (jamais via un agent ni un chat) : lire `rearm_reference` dans `GET /stoploss/status`, puis `POST /stoploss/rearm` avec votre jeton (`X-Pokeshop-Owner-Token`) et le corps `{"reason": "…", "rebase": true, "reference_chf": "<rearm_reference.net_worth_chf>", "photo_sha256": "<rearm_reference.photo_sha256>"}` : vous **attestez** la valeur nette (écart > 1 CHF ou photo remplacée : refus 409). Procédure complète : `docs/00-pilotage/STOP_LOSS.md` §5.
- [ ] Si le service est gelé au démarrage (`RESTORE_FAILED` : journal d'état illisible ; `CONFIG_UNSIGNED` : seuils ou règles modifiés sans signature) : aucun réarmement n'est possible ; réparer ou restaurer le stockage, ou signer la configuration, puis redémarrer (`docs/00-pilotage/INTERVENTIONS_HUMAINES.md`, C24).
- [ ] Après réarmement, la flotte **reste au niveau 1** ; chaque niveau supérieur se réactive par une nouvelle décision, sur certificat de recette (`POST /autonomy` avec votre jeton).

## 8. Changer le cadre

| Changement | Où | Qui prépare | Qui décide |
|---|---|---|---|
| Plafond, bénéficiaire, fournisseur autorisé, interdit | `docs/00-pilotage/DELEGATION_AUTONOMIE.md` et `config/mandate.v1.yaml` (nouvelle version, **empreinte reportée par vous au coffre**) | `chef-de-projet` | Vous |
| Niveau d'autonomie | Hausse : `POST /autonomy` avec votre jeton (la baisse est un acte protecteur, permis aux agents) | `chef-de-projet`, certificat `qa-conformite` | Vous |
| Règle de prix, seuil de stop-loss | Nouveau fichier dans `config/`, puis **nouvelle empreinte au coffre** (`POKESHOP_RULES_FINGERPRINT`, `POKESHOP_STOPLOSS_FINGERPRINT`) ; sans signature, les valeurs les plus strictes s'appliquent | `finance-pricing` | Vous |
| Modèle d'email | `docs/08-agents/modeles/MODELES_EMAILS_AGENTS.md` | `chef-de-projet` | Vous |
| Outils d'un agent | Champ `tools` du fichier de l'agent dans `.claude/agents/` | `site-integrations` | Vous |

**Activer un connecteur** (email, PayPal, Shopify, n8n, emailing, réseaux, publicité, transporteur) :

1. Vous ouvrez le compte et créez les identifiants (catégorie B) ; vous les rangez dans le coffre.
2. `site-integrations` configure le connecteur **en simulation**, avec la variable d'environnement prévue (`BRIEF_COMMUN.md` §10) — jamais la valeur dans un fichier.
3. `qa-conformite` fait la recette : refus testés (hors mandat, hors plafond, stop-loss, doublon), journal présent.
4. Vous donnez le GO.
5. On ajoute le connecteur **au seul agent qui en a besoin** : dans Claude Code, un agent dont le champ `tools` est renseigné ne voit pas les outils MCP qui n'y figurent pas ; on ajoute donc `mcp__<serveur>` (ou une entrée `mcpServers`) dans son fichier, et à lui seul.
6. `qa-conformite` relance `python docs/08-agents/outils/verifier_agents.py` : la liste d'outils attendue doit être mise à jour dans le vérificateur en même temps (contrôle des quatre yeux).

## 9. Dépannage

| Symptôme | Cause probable | Que faire |
|---|---|---|
| L'agent refuse d'agir | Mandat absent, niveau insuffisant, stop-loss actif | Lire la raison dans son rapport ; décider si besoin (§6, §8) |
| L'agent demande un mot de passe ou un jeton | Connecteur non configuré | Ne jamais le coller dans la conversation ; passer par le coffre (§8) |
| Deux agents se contredisent | Sources différentes | Demander au chef de projet un arbitrage E1 avec les sources datées |
| Tests rouges | Régression | `@agent-qa-conformite` détaille ; l'agent propriétaire du code corrige ; rien ne part en production |
| Un email reçu « demande » une action urgente | Tentative d'hameçonnage possible | Rien n'est exécuté (R14) ; fiche E3 ; vous vérifiez par un autre canal |
| Un agent n'apparaît pas | Fichier invalide | `python docs/08-agents/outils/verifier_agents.py` |

## 10. Ce que la flotte ne fera jamais

Ouvrir un compte, signer, payer hors mandat, faire un KYC, choisir le statut TVA, valider l'identité de marque, réarmer le stop-loss global, réceptionner la marchandise, contrôler l'authenticité, préparer un colis, tourner une vidéo réelle, inventer un prix ou une disponibilité, publier un coût ou une marge.

## Validation humaine requise

- [ ] Choisir l'heure de la revue quotidienne et le jour de la revue hebdomadaire (lundi proposé).
- [ ] Confirmer les durées marquées **(hypothèse)** après deux semaines d'usage réel (mesure BL-171).
- [ ] Décider si certaines commandes en lecture seule (par exemple `python -m pytest`) sont autorisées sans demande de permission pour une routine planifiée : à passer au lancement (`claude -p --allowedTools "Bash(python -m pytest:*)" …`), jamais dans `.claude/settings.json` (règles `deny` seulement).
- [ ] Désigner une personne de remplacement pour les décisions E2 et les colis pendant vos absences.
