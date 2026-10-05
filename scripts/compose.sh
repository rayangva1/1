#!/usr/bin/env bash
# Lance docker compose avec le fichier de secrets HORS du dépôt (revue SEC-13).
#
# Usage :
#   scripts/compose.sh config --quiet                       # vérification, rien n'est lancé
#   scripts/compose.sh up -d db db-migrate db-backup api n8n
#   POKESHOP_ENV_FILE=/autre/chemin/api.env scripts/compose.sh ps
#
# Le fichier de variables (POSTGRES_PASSWORD, N8N_ENCRYPTION_KEY, POKESHOP_DB_PASSWORD, empreintes des jetons…)
# vit hors de l'arborescence où travaillent les agents : défaut /etc/pokeshop/api.env, créé par la
# propriétaire (B23) avec `sudo install -D -m 600 .env.example /etc/pokeshop/api.env` puis rempli depuis le coffre.
# Refus (fermé par défaut, rien n'est lancé) :
#   - un fichier .env (ou *.env) existe à la racine du dépôt : docker compose le lirait tout seul ;
#   - le fichier de variables est absent, dans le dépôt, lisible par d'autres que son propriétaire
#     (mode autre que 600 ou 400), ou est un lien symbolique vers le dépôt.
# Aucun secret n'est affiché. Docker Compose reçoit le fichier par --env-file (interpolation seulement :
# aucun service ne charge le fichier en entier, voir docker-compose.yml).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd -P)"
env_file="${POKESHOP_ENV_FILE:-/etc/pokeshop/api.env}"
docker_bin="${POKESHOP_DOCKER_BIN:-docker}"

die() { echo "ÉCHEC : $*" >&2; exit 1; }

shopt -s nullglob
stray=("$repo"/.env "$repo"/.env.* "$repo"/*.env)
shopt -u nullglob
for f in "${stray[@]}"; do
    [ "$(basename "$f")" = ".env.example" ] && continue
    [ -e "$f" ] && die "fichier de secrets dans le dépôt ($f) : le déplacer hors du dépôt (ex. /etc/pokeshop/api.env), docker compose le lirait sinon"
done

[ -f "$env_file" ] || die "fichier de variables introuvable : $env_file (créer avec : sudo install -D -m 600 .env.example $env_file, puis le remplir depuis le coffre)"
real="$(cd "$(dirname "$env_file")" && pwd -P)/$(basename "$env_file")"
if [ -L "$env_file" ]; then
    target="$(readlink -f "$env_file")"
    real="$target"
fi
case "$real" in
    "$repo"/*) die "fichier de variables dans le dépôt ($real) : le ranger hors du dépôt (ex. /etc/pokeshop/api.env)" ;;
esac
mode="$(stat -c '%a' "$real")"
case "$mode" in
    600|400) ;;
    *) die "fichier de variables en mode $mode : 600 attendu (lisible par son seul propriétaire) — chmod 600 $env_file" ;;
esac

exec "$docker_bin" compose --project-directory "$repo" -f "$repo/docker-compose.yml" --env-file "$real" "$@"
