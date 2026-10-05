# Base de données — PostgreSQL 16 (compatible Supabase)

Schéma du moteur {{NOM_BOUTIQUE}} : offres fournisseurs, catalogue, coûts, prix, stock local,
commandes, incidents, journal. Propriété : agent data-pipeline (SPEC §3). Référence : 4 octobre 2026.

> Aucune base n'est déployée. Tout ce qui suit se teste en local ; un déploiement (Supabase ou
> autre) exige un compte et une décision de la propriétaire.

## Contenu

| Fichier | Rôle |
|---|---|
| `migrations/001_init.sql` | Schémas `pokeshop` (interne), énumérations, 26 tables, contraintes, index |
| `migrations/002_integrity.sql` | Rôles, journaux append-only, `audit_log` chaîné sha256, clé d'identité produit, commande figée, règles figées, idempotence |
| `migrations/003_public_catalog.sql` | Schéma `storefront`, vue `public_catalog` (sans coût ni fournisseur), vue `current_autonomy`, droits |
| `migrations/004_persistance_etats.sql` | Journal d'état `engine_state_journal` (états de sécurité de l'API, ajout seul, chaîné par flux), référence d'incident unique, hausse d'autonomie vérifiée par la base (`raise_autonomy`, `owner_token_fingerprint`) |
| `migrations/005_vue_publique_sans_fictif.sql` | `storefront.public_catalog` sans aucun produit FICTIF (plus de réglage de session) ; vue d'essai interne `pokeshop.public_catalog_test` (FICTIFS compris) lisible par le moteur seulement |
| `seeds/reference_seed.sql` | Données réelles sourcées : 6 extensions (copie de `data/extensions_aliases.yaml`), 5 pistes fournisseurs du BP §2 (statut PISTE) |
| `seeds/fictif_seed.sql` | Scénario FICTIF complet (fournisseurs `fictif_*`, GTIN `200…`, prix et coûts inventés) ; décisions de prix, commande et proposition rattachées à la version **réelle** des règles qui les a calculées (`v1-2026-10-04`, contenu complet et sha256 du fichier) |
| `seeds/regles_seed.py` | Régénère les blocs `genere:*` du seed FICTIF depuis `config/pricing_rules.v1.yaml` et le moteur (`--check` : seed aligné sur les règles) |
| `apply.sh` | Applique les migrations dans l'ordre (saute celles déjà enregistrées) puis les seeds demandés |
| `engine_login.sh` | Crée ou met à jour le compte de connexion du moteur (`api_moteur` par défaut), membre de `pokeshop_engine` (docker compose : service `db-migrate`) |
| `backup.sh` | Sauvegarde `pg_dump` + **test de restauration** dans une base jetable ; restauration réelle ; boucle quotidienne (service `db-backup`) |

## Appliquer

### En local (PostgreSQL 16)

```bash
sudo service postgresql start                  # ou : pg_ctlcluster 16 main start
sudo -u postgres createdb pokeshop
DATABASE_URL=postgresql:///pokeshop sudo -E -u postgres db/apply.sh all     # migrations + seeds
DATABASE_URL=postgresql:///pokeshop sudo -E -u postgres db/apply.sh         # relance : tout est « déjà appliqué »
```

Sans le script : `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f db/migrations/001_init.sql` puis 002, 003, 004, 005, puis les seeds.
Chaque fichier est une transaction : en cas d'erreur, rien n'est appliqué de ce fichier.

### Supabase

1. Créer un projet (action de la propriétaire : compte, région, facturation).
2. Copier les migrations dans `supabase/migrations/` avec un préfixe horodaté
   (`20261004000001_init.sql`, `…02_integrity.sql`, `…03_public_catalog.sql`, `…04_persistance_etats.sql`,
   `…05_vue_publique_sans_fictif.sql`) puis `supabase db push` ;
   ou les coller dans l'éditeur SQL dans l'ordre. Les `BEGIN/COMMIT` des fichiers sont compatibles ;
   si l'outil encapsule déjà la migration dans une transaction, PostgreSQL émet seulement un avertissement.
3. **Ne pas exposer le schéma `pokeshop`** dans *Settings → API → Exposed schemas*. Exposer au plus `storefront`.
4. Pour lire le catalogue public via l'API Supabase : ajouter `storefront` aux schémas exposés puis
   `GRANT USAGE ON SCHEMA storefront TO anon; GRANT SELECT ON storefront.public_catalog TO anon;`.
   Ne jamais accorder de droit sur `pokeshop` à `anon` ou `authenticated`.
5. Le conseiller de sécurité Supabase signalera `public_catalog` comme vue « security definer » : c'est
   **voulu** (la vue lit les tables internes avec les droits de son propriétaire et ne renvoie que des
   colonnes publiques ; l'alternative `security_invoker` obligerait à ouvrir les tables internes).
6. Les migrations n'emploient que des fonctions PostgreSQL ≥ 12 (`sha256`, identités, `EXECUTE FUNCTION`,
   colonne générée de 004) : compatibles avec les versions Supabase actuelles (15 et 17).
7. 004 rend `pokeshop_owner` propriétaire de `pokeshop.raise_autonomy` (`ALTER FUNCTION … OWNER TO`) :
   le compte qui applique la migration doit être superutilisateur ou pouvoir agir comme `pokeshop_owner`
   (vérifié en local sur PostgreSQL 16 avec le superutilisateur ; à vérifier sur Supabase).

## Rôles

| Rôle (NOLOGIN) | Droits | Qui en est membre |
|---|---|---|
| `storefront_reader` | `SELECT` sur `storefront.public_catalog` uniquement | Boutique / site public, `anon` Supabase si besoin |
| `pokeshop_engine` | Lecture/écriture du schéma `pokeshop` ; journaux en **ajout seul** (dont `engine_state_journal` : lecture et ajout seulement) ; aucune écriture de `schema_migrations` ; aucune lecture de `owner_token_fingerprint` ; `EXECUTE` sur `raise_autonomy` | API du moteur, n8n |
| `pokeshop_owner` | Comme le moteur + valider des règles (`pricing_rules.status = VALIDE`) + **relever** un niveau d'autonomie + enregistrer l'empreinte de son jeton (`owner_token_fingerprint`) ; propriétaire de `raise_autonomy` | La propriétaire uniquement |

Créer les comptes de connexion (mots de passe dans le coffre, jamais dans le dépôt). Le compte du moteur
se crée aussi par script (docker compose le fait dans `db-migrate`) :
`DATABASE_URL=<admin> POKESHOP_DB_USER=api_moteur POKESHOP_DB_PASSWORD=<coffre> db/engine_login.sh`.

```sql
CREATE ROLE api_moteur LOGIN PASSWORD '<coffre>' IN ROLE pokeshop_engine;
CREATE ROLE site_public LOGIN PASSWORD '<coffre>' IN ROLE storefront_reader;
CREATE ROLE proprietaire LOGIN PASSWORD '<coffre>' IN ROLE pokeshop_owner;
```

**Hausse du niveau d'autonomie avec le compte de production.** L'API se connecte avec un compte membre
de `pokeshop_engine` (jamais `pokeshop_owner`). Une hausse validée par le jeton de la propriétaire
(`POST /autonomy`, en-tête `X-Pokeshop-Owner-Token`) passe par `pokeshop.raise_autonomy(scope, niveau,
auteur, motif, jeton)` : fonction `SECURITY DEFINER` (propriétaire `pokeshop_owner`) qui recalcule le
sha256 du jeton, le compare à l'empreinte **enregistrée par la propriétaire elle-même** et n'accepte
qu'un niveau à la fois. Le jeton n'est jamais stocké ; le compte du moteur ne peut ni lire ni écrire
l'empreinte, donc ne peut pas se relever seul. Une seule fois, connectée avec son compte `proprietaire` :

```sql
-- <empreinte> = sha256 du jeton propriétaire (même valeur que POKESHOP_OWNER_TOKEN_SHA256 du coffre)
INSERT INTO pokeshop.owner_token_fingerprint (token_sha256) VALUES ('<empreinte>');
```

Sans cette empreinte, `POST /autonomy` (hausse) répond 403 « empreinte du jeton propriétaire non
enregistrée en base ». Changer de jeton = insérer une nouvelle ligne (la dernière fait foi ; ajout seul).

**États de sécurité de l'API (`engine_state_journal`).** Un flux par composant : `stoploss` (verrou,
point zéro, journal), `stoploss_photo` (dernière photo acceptée), `mandate_ledger` (registre du mandat,
idempotence), `northstar` (étoile polaire), `incidents` (incidents, quarantaines, suspensions),
`price_history` (historique des prix publics), et aussi : `sync_catalog` et `sync_cost_inputs`
(catalogue validé et frais lus par `/sync/run`), `sync_runs` (cycles de synchronisation : statut, données
FICTIVES ou non, empreinte et horodatage de la source, produits rapprochés ; compteur de recette et
preuves des tests de correction d'incident), `shop_publications` (identifiant Shopify et statut des fiches
écrites et vérifiées : base de la dépublication protectrice), `capital_movements` (apports et retraits
attestés par la propriétaire : **seule** source des mouvements de capital du stop-loss), `ads_activity`
(dépenses publicitaires), ainsi que les registres des lots F2 et F3 (révocations du mandat, taux,
propositions, coûts historiques, approbations de prix, références d'import, stock local). Chaque ligne : `seq` continu par flux, `prev_hash →
row_hash` = sha256(prev ␟ seq ␟ corps JSON), corps lisible en SQL via la colonne `record` (jsonb).
L'API écrit avant d'appliquer et relit tout au démarrage ; un flux illisible gèle le service. Un
second écrivain sur le même flux est refusé par la base (un seul service API par base).

## Garanties portées par la base

| Garantie | Mécanisme | Source |
|---|---|---|
| Journal infalsifiable | `audit_log` : UPDATE/DELETE/TRUNCATE refusés ; chaîne `prev_hash → row_hash` (sha256) ; `SELECT * FROM pokeshop.verify_audit_chain()` doit renvoyer 0 ligne | BP §6 « Journal de chaque changement » |
| Historique non réécrit | `stock_movements`, `price_events`, `price_decisions`, `supplier_offers`, `autonomy_levels` append-only | BP §12 |
| Aucun coût public | `storefront.public_catalog` : colonnes publiques seulement ; `storefront_reader` n'a aucun droit sur `pokeshop` | SPEC §0.2, BP §6 |
| Aucun faux stock | Disponibilité de la vue = stock local vendable, ou précommande sur allocation ferme écrite ; jamais le stock fournisseur | SPEC §0.3, BP §5 |
| Identité ambiguë = brouillon | `identity_key` calculée par trigger (même règle que `pokeshop.catalog`) ; `PUBLIE` impossible sans identité complète, scellé, titre, droits d'image | BP §6, §11 |
| Commande conclue figée | Prix, quantités et montants de `orders`/`order_lines` non modifiables ; seul le coût historique évolue | BP §5 |
| Règles versionnées | `pricing_rules` : contenu figé, validation par la propriétaire | BP §4 |
| Idempotence | `pokeshop.claim_idempotency_key(scope, clé, sha256)` → `NEW`, `DUPLICATE_*` ou `CONFLICT` | BP §6, §13 |
| Réarmement réservé | `autonomy_levels` : agents et système ne peuvent qu'abaisser ; relever exige `pokeshop_owner` ou `raise_autonomy` (jeton revérifié contre l'empreinte de la propriétaire, un niveau à la fois) | BP §13, stop-loss global |
| États de sécurité persistés | `engine_state_journal` : ajout seul, séquence continue et chaînage sha256 imposés par trigger par flux ; `SELECT * FROM pokeshop.verify_engine_state_journal()` doit renvoyer 0 ligne | Stop-loss global, mandat, étoile polaire |
| Incident jamais écrasé | Index unique sur `details->>'ref'` ; l'API ne met à jour une ligne que si type, gravité, périmètre, cause et code sont identiques | SOP incidents §1 |
| Concurrence stock | `stock_levels.version` incrémentée à chaque écriture : `UPDATE … WHERE version = $attendue` | BP §6 |
| Données d'essai isolées | `fictif = true` ; **jamais** visibles dans `storefront.public_catalog`, quel que soit le réglage de session (005) ; essais : `pokeshop.public_catalog_test`, sans droit pour `storefront_reader` | SPEC §0.7 |

Limite connue : un superutilisateur peut désactiver les triggers (`session_replication_role = replica`).
La chaîne sha256 rend alors toute modification **détectable** (`verify_audit_chain`, `verify_engine_state_journal`)
mais pas impossible : sauvegardes externes et accès superutilisateur réservé à la propriétaire. La suppression
des **dernières** lignes d'un flux d'`engine_state_journal` par un superutilisateur (triggers désactivés) n'est
pas détectable par la chaîne seule : d'où la règle de sauvegarde ci-dessous et l'accès superutilisateur réservé.

## Sauvegarde et test de restauration (BP §6)

`db/backup.sh` (client PostgreSQL 16 ; compte administrateur dans `DATABASE_URL`, jamais le compte de l'API) :

| Commande | Effet |
|---|---|
| `db/backup.sh sauvegarde` | `pg_dump -Fc` dans `POKESHOP_BACKUP_DIR` (défaut `~/pokeshop-sauvegardes`, **refusé dans le dépôt**), fichiers en mode 600, empreinte sha256 et manifeste (migrations, lignes des journaux en ajout seul) ; rétention `POKESHOP_BACKUP_KEEP` (30) ; chiffrement facultatif `POKESHOP_BACKUP_AGE_RECIPIENT` (clé publique age ; demandé mais impossible = échec, jamais de copie en clair) |
| `db/backup.sh verifier [FICHIER]` | Contrôle l'empreinte, **restaure** dans une base jetable du même serveur (supprimée ensuite) et échoue si une table n'a pas exactement les lignes de la sauvegarde, si un journal en ajout seul en a moins qu'au manifeste, si `verify_audit_chain()` ou `verify_engine_state_journal()` signale une anomalie, ou si les migrations diffèrent. Sauvegarde chiffrée : `POKESHOP_BACKUP_AGE_IDENTITY`. Nom de la base jetable : `POKESHOP_VERIF_PREFIX` (défaut `pokeshop_verif_`, contrôlé avant tout accès : « pokeshop_verif_ » suivi de minuscules, chiffres ou « _ ») + date, processus et aléa, affiché sur la sortie d'erreur (`base jetable : <nom>`) ; un test lui donne son propre préfixe et ne supprime que les bases qu'il a créées, jamais toutes les `pokeshop_verif_*` (revue R5, R4-NEW-03) |
| `db/backup.sh restaurer FICHIER URL_CIBLE` | Restauration réelle dans une base **vide** (jamais la source), propriétaires et droits compris, puis les mêmes contrôles |
| `db/backup.sh boucle` | Sauvegarde puis test de restauration toutes les `POKESHOP_BACKUP_INTERVAL_HOURS` (24) : service docker compose `db-backup` (volume `backups`) |
| `db/backup.sh etat` | Contrôle R-I04 (sans base) : code 0 seulement si la dernière restauration **vérifiée** (trace `derniere-verification.tsv` écrite par `verifier` après succès) date de moins de `POKESHOP_BACKUP_MAX_AGE_HOURS` (défaut 1,5 × intervalle = 36 h) ; sinon code 1 (aucune trace, trace illisible ou trop ancienne). C'est le **healthcheck** du service `db-backup` : `scripts/compose.sh ps` l'affiche « unhealthy » tant qu'aucune restauration récente n'est vérifiée |

Un test de restauration en échec rend la sauvegarde inutilisable : en refaire une et ouvrir un incident.

**Chiffrement : sur le serveur, en clair ; hors de la machine, chiffré.** Le service `db-backup` du compose ne reçoit pas
`POKESHOP_BACKUP_AGE_RECIPIENT` : ses sauvegardes (volume `backups`, fichiers en mode 600) sont en clair, comme la base
qu'elles copient sur la même machine, ce qui lui permet de vérifier chaque jour la restauration sans détenir de clé privée
(`db/backup.sh etat` : code 0). Chaque mois (A12, BL-195), la propriétaire copie ces sauvegardes **hors de la machine,
chiffrées pour elle seule** avec sa clé publique age (paire créée une fois : `age-keygen -o cle-privee-age.txt`, clé privée
jamais sur le serveur) :

```bash
scripts/compose.sh ps db-backup                         # « healthy » : restauration vérifiée depuis moins de 36 h
scripts/compose.sh exec -T db-backup tar -C /sauvegardes -cf - . | age -r <votre clé publique age1…> > /chemin/disque/pokeshop-$(date +%F).tar.age
age -d -i cle-privee-age.txt /chemin/disque/pokeshop-AAAA-MM-JJ.tar.age | tar -tf -   # contrôle : la copie se relit
```

(Chaîne tar → age → relecture vérifiée le 5.10.2026 sur des fichiers FICTIFS.) Pour restaurer depuis cette copie :
la déchiffrer (`age -d -i …  | tar -xf -`), puis `db/backup.sh restaurer FICHIER URL_CIBLE`. Un `db/backup.sh sauvegarde`
lancé hors du compose avec `POKESHOP_BACKUP_AGE_RECIPIENT` produit au contraire des fichiers chiffrés, que `verifier` ne
contrôle qu'avec `POKESHOP_BACKUP_AGE_IDENTITY`. Supabase :
activer en plus les sauvegardes du fournisseur (PITR) ; `backup.sh verifier` s'utilise avec un serveur local
pour tester la restauration d'un `pg_dump` du projet. `tests/test_sauvegarde_restauration.py` exécute ces
commandes contre une base jetable (empreinte altérée, lignes manquantes, chaîne d'audit rompue, chiffrement).

## Vérifier

```bash
python -m pytest -q tests/test_db_migrations.py   # base jetable, migrations + seeds, contrôles ci-dessus
python -m pytest -q tests/test_persistance_postgres.py   # 004 : journaux d'état, redémarrage de l'API, incidents, hausse d'autonomie
python -m pytest -q tests/test_sauvegarde_restauration.py  # sauvegarde, restauration dans une base jetable, compte du moteur
python -m pytest -q tests/test_seed_fictif.py           # seed FICTIF aligné sur la version réelle des règles (sans base)
```

Le test démarre PostgreSQL s'il est arrêté (`service postgresql start`, sinon `pg_ctlcluster 16 main start`),
crée une base `pokeshop_test_*`, la supprime à la fin. Variable `POKESHOP_TEST_PG_ADMIN_URL` pour viser
un autre serveur (compte superutilisateur, base d'administration).

## Validation humaine requise

- [ ] Choisir l'hébergement (Supabase ou PostgreSQL géré) et créer le compte : action de la propriétaire.
- [ ] Créer les comptes de connexion et ranger les mots de passe dans le coffre ; réserver `pokeshop_owner` à la propriétaire.
- [ ] Enregistrer une fois l'empreinte de votre jeton propriétaire en base (`owner_token_fingerprint`, compte `proprietaire`) : sans elle, aucune hausse du niveau d'autonomie n'est possible.
- [ ] Choisir où vivent les sauvegardes (`POKESHOP_BACKUP_DIR`, volume `backups`) et leur copie hors machine ; créer votre paire de clés age (clé publique pour chiffrer la copie mensuelle, clé privée chez vous seule, jamais sur le serveur).
- [ ] Vérifier chaque mois que le service `db-backup` est « healthy » (`scripts/compose.sh ps`, ou `db/backup.sh etat` : dernière restauration vérifiée depuis moins de 36 h) ; la base porte `engine_state_journal` (gel du stop-loss, registre du mandat, incidents). Recette R-I04 : bloquante tant que `etat` échoue.
- [ ] Valider la rétention des captures brutes (`raw_snapshots.content` contient des prix B2B) et celle des sauvegardes (30 par défaut).
- [ ] Valider le plafond par commande par défaut (`products.max_qty_per_order` = 5, hypothèse).
- [ ] Confirmer que seule la vue `storefront.public_catalog` sera exposée au site public.
