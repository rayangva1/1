#!/usr/bin/env bash
# Crée (ou met à jour le mot de passe de) le compte de connexion du moteur, membre de pokeshop_engine.
#
# Usage : DATABASE_URL=postgresql://admin@hote:5432/pokeshop POKESHOP_DB_USER=api_moteur \
#         POKESHOP_DB_PASSWORD=<coffre> db/engine_login.sh
#
# L'API se connecte avec ce compte (jamais avec l'administrateur) : lecture/écriture du schéma interne,
# journaux en ajout seul, aucune lecture de l'empreinte du jeton propriétaire (db/README.md « Rôles »).
# Le mot de passe passe par une variable psql (jamais dans la ligne de commande ni dans un journal).
# À lancer APRÈS db/apply.sh (le rôle pokeshop_engine doit exister). Idempotent.
set -euo pipefail

: "${DATABASE_URL:?Définir DATABASE_URL (compte administrateur)}"
: "${POKESHOP_DB_PASSWORD:?Définir POKESHOP_DB_PASSWORD (coffre)}"
login="${POKESHOP_DB_USER:-api_moteur}"

if [ "${#POKESHOP_DB_PASSWORD}" -lt 16 ]; then
    echo "POKESHOP_DB_PASSWORD trop court (16 caractères aléatoires ou plus)" >&2
    exit 2
fi
case "$login" in
    *[!a-z0-9_]*|"") echo "POKESHOP_DB_USER invalide (minuscules, chiffres, _)" >&2; exit 2 ;;
esac

psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1 -v login="$login" -v pwd="$POKESHOP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN IN ROLE pokeshop_engine', :'login')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'login') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L', :'login', :'pwd') \gexec
SELECT format('GRANT pokeshop_engine TO %I', :'login') \gexec
SQL
echo "compte du moteur prêt : $login (membre de pokeshop_engine)"
