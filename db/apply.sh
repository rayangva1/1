#!/usr/bin/env bash
# Applique les migrations db/migrations/NNN_*.sql dans l'ordre, puis les seeds demandés.
#
# Usage : DATABASE_URL=postgresql://utilisateur@hote:5432/base db/apply.sh [none|reference|fictif|all]
#   none      : migrations seulement (défaut)
#   reference : + db/seeds/reference_seed.sql (extensions sourcées, pistes fournisseurs du BP)
#   fictif    : + db/seeds/fictif_seed.sql (jeu d'essai FICTIF)
#   all       : reference puis fictif
#
# Une migration déjà enregistrée dans pokeshop.schema_migrations est sautée. Chaque fichier
# est transactionnel : une erreur annule le fichier entier et arrête le script.
# Les seeds ne s'appliquent qu'une fois, sur une base neuve.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${DATABASE_URL:?Définir DATABASE_URL (ex. postgresql://postgres@localhost:5432/pokeshop)}"
seeds="${1:-none}"

case "$seeds" in
    none|reference|fictif|all) ;;
    *) echo "argument inconnu : $seeds (none|reference|fictif|all)" >&2; exit 2 ;;
esac

run_file() {
    psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1 -f "$1"
}

is_applied() {
    local result
    result="$(psql "$DATABASE_URL" -X -tA -v ON_ERROR_STOP=1 \
        -c "SELECT 1 FROM pokeshop.schema_migrations WHERE version = '$1'" 2>/dev/null || true)"
    [ "$result" = "1" ]
}

for file in "$here"/migrations/[0-9][0-9][0-9]_*.sql; do
    name="$(basename "$file")"
    version="${name:0:3}"
    if is_applied "$version"; then
        echo "déjà appliquée : $name"
        continue
    fi
    echo "application : $name"
    run_file "$file"
done

if [ "$seeds" = "reference" ] || [ "$seeds" = "all" ]; then
    echo "seed : reference_seed.sql"
    run_file "$here/seeds/reference_seed.sql"
fi
if [ "$seeds" = "fictif" ] || [ "$seeds" = "all" ]; then
    echo "seed : fictif_seed.sql (FICTIF)"
    run_file "$here/seeds/fictif_seed.sql"
fi
echo "terminé"
