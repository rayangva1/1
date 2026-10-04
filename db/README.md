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
| `seeds/reference_seed.sql` | Données réelles sourcées : 6 extensions (copie de `data/extensions_aliases.yaml`), 5 pistes fournisseurs du BP §2 (statut PISTE) |
| `seeds/fictif_seed.sql` | Scénario FICTIF complet (fournisseurs `fictif_*`, GTIN `200…`, prix et coûts inventés) |
| `apply.sh` | Applique les migrations dans l'ordre (saute celles déjà enregistrées) puis les seeds demandés |

## Appliquer

### En local (PostgreSQL 16)

```bash
sudo service postgresql start                  # ou : pg_ctlcluster 16 main start
sudo -u postgres createdb pokeshop
DATABASE_URL=postgresql:///pokeshop sudo -E -u postgres db/apply.sh all     # migrations + seeds
DATABASE_URL=postgresql:///pokeshop sudo -E -u postgres db/apply.sh         # relance : tout est « déjà appliqué »
```

Sans le script : `psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -f db/migrations/001_init.sql` puis 002, 003, puis les seeds.
Chaque fichier est une transaction : en cas d'erreur, rien n'est appliqué de ce fichier.

### Supabase

1. Créer un projet (action de la propriétaire : compte, région, facturation).
2. Copier les migrations dans `supabase/migrations/` avec un préfixe horodaté
   (`20261004000001_init.sql`, `…02_integrity.sql`, `…03_public_catalog.sql`) puis `supabase db push` ;
   ou les coller dans l'éditeur SQL dans l'ordre. Les `BEGIN/COMMIT` des fichiers sont compatibles ;
   si l'outil encapsule déjà la migration dans une transaction, PostgreSQL émet seulement un avertissement.
3. **Ne pas exposer le schéma `pokeshop`** dans *Settings → API → Exposed schemas*. Exposer au plus `storefront`.
4. Pour lire le catalogue public via l'API Supabase : ajouter `storefront` aux schémas exposés puis
   `GRANT USAGE ON SCHEMA storefront TO anon; GRANT SELECT ON storefront.public_catalog TO anon;`.
   Ne jamais accorder de droit sur `pokeshop` à `anon` ou `authenticated`.
5. Le conseiller de sécurité Supabase signalera `public_catalog` comme vue « security definer » : c'est
   **voulu** (la vue lit les tables internes avec les droits de son propriétaire et ne renvoie que des
   colonnes publiques ; l'alternative `security_invoker` obligerait à ouvrir les tables internes).
6. Les migrations n'emploient que des fonctions PostgreSQL ≥ 11 (`sha256`, identités, `EXECUTE FUNCTION`) :
   compatibles avec les versions Supabase actuelles (15 et 17).

## Rôles

| Rôle (NOLOGIN) | Droits | Qui en est membre |
|---|---|---|
| `storefront_reader` | `SELECT` sur `storefront.public_catalog` uniquement | Boutique / site public, `anon` Supabase si besoin |
| `pokeshop_engine` | Lecture/écriture du schéma `pokeshop` ; journaux en **ajout seul** ; aucune écriture de `schema_migrations` | API du moteur, n8n |
| `pokeshop_owner` | Comme le moteur + valider des règles (`pricing_rules.status = VALIDE`) + **relever** un niveau d'autonomie | La propriétaire uniquement |

Créer les comptes de connexion (mots de passe dans le coffre, jamais dans le dépôt) :

```sql
CREATE ROLE api_moteur LOGIN PASSWORD '<coffre>' IN ROLE pokeshop_engine;
CREATE ROLE site_public LOGIN PASSWORD '<coffre>' IN ROLE storefront_reader;
CREATE ROLE proprietaire LOGIN PASSWORD '<coffre>' IN ROLE pokeshop_owner;
```

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
| Réarmement réservé | `autonomy_levels` : agents et système ne peuvent qu'abaisser ; relever exige `pokeshop_owner` | BP §13, stop-loss global |
| Concurrence stock | `stock_levels.version` incrémentée à chaque écriture : `UPDATE … WHERE version = $attendue` | BP §6 |
| Données d'essai isolées | `fictif = true` ; invisibles dans la vue publique sauf `SET pokeshop.include_fictif = 'on'` | SPEC §0.7 |

Limite connue : un superutilisateur peut désactiver les triggers (`session_replication_role = replica`).
La chaîne sha256 rend alors toute modification **détectable** (`verify_audit_chain`) mais pas impossible :
sauvegardes externes et accès superutilisateur réservé à la propriétaire.

## Vérifier

```bash
python -m pytest -q tests/test_db_migrations.py   # base jetable, migrations + seeds, contrôles ci-dessus
```

Le test démarre PostgreSQL s'il est arrêté (`service postgresql start`, sinon `pg_ctlcluster 16 main start`),
crée une base `pokeshop_test_*`, la supprime à la fin. Variable `POKESHOP_TEST_PG_ADMIN_URL` pour viser
un autre serveur (compte superutilisateur, base d'administration).

## Validation humaine requise

- [ ] Choisir l'hébergement (Supabase ou PostgreSQL géré) et créer le compte : action de la propriétaire.
- [ ] Créer les comptes de connexion et ranger les mots de passe dans le coffre ; réserver `pokeshop_owner` à la propriétaire.
- [ ] Valider la rétention des captures brutes (`raw_snapshots.content` contient des prix B2B) et la politique de sauvegarde / test de restauration (BP §6).
- [ ] Valider le plafond par commande par défaut (`products.max_qty_per_order` = 5, hypothèse).
- [ ] Confirmer que seule la vue `storefront.public_catalog` sera exposée au site public.
