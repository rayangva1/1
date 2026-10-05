#!/usr/bin/env bash
# Sauvegarde et test de restauration de la base du moteur (BP §6 « sauvegardes et test de restauration »).
#
# Usage :
#   DATABASE_URL=postgresql://admin:…@hote:5432/pokeshop db/backup.sh sauvegarde
#   DATABASE_URL=… db/backup.sh verifier [FICHIER]      # défaut : dernière sauvegarde du dossier
#   DATABASE_URL=… db/backup.sh restaurer FICHIER URL_CIBLE
#   DATABASE_URL=… db/backup.sh boucle                  # service docker compose « db-backup »
#   db/backup.sh etat                                   # contrôle R-I04 : dernière restauration vérifiée récente ?
#
# sauvegarde : pg_dump au format personnalisé (-Fc) dans POKESHOP_BACKUP_DIR (défaut
#   ~/pokeshop-sauvegardes, JAMAIS dans le dépôt : la base contient prix B2B, coûts et marges), fichiers en
#   mode 600, empreinte sha256 et manifeste (migrations, nombre de lignes des journaux en ajout seul au
#   début de la sauvegarde). Chiffrement facultatif : POKESHOP_BACKUP_AGE_RECIPIENT (clé publique age) ;
#   chiffrement demandé mais impossible => échec, jamais de copie en clair. Rétention :
#   POKESHOP_BACKUP_KEEP sauvegardes (défaut 30).
# verifier : contrôle l'empreinte, restaure dans une base JETABLE du même serveur (créée puis supprimée),
#   puis échoue si : une table restaurée n'a pas exactement le nombre de lignes contenu dans la sauvegarde,
#   un journal en ajout seul a moins de lignes qu'au manifeste, la chaîne sha256 du journal d'audit ou des
#   journaux d'état est rompue, ou les migrations diffèrent du manifeste. Sauvegarde chiffrée :
#   POKESHOP_BACKUP_AGE_IDENTITY (fichier de clé privée de la propriétaire).
# restaurer : restauration réelle dans une base cible VIDE (jamais la base source), avec propriétaires et
#   droits (compte superutilisateur ou membre des rôles pokeshop_*), puis les mêmes contrôles.
# etat : lit la trace écrite par `verifier` après une restauration conforme (POKESHOP_BACKUP_DIR/
#   derniere-verification.tsv : époque, date, fichier, sha256) ; code 0 seulement si elle date de moins de
#   POKESHOP_BACKUP_MAX_AGE_HOURS (défaut : 1,5 × POKESHOP_BACKUP_INTERVAL_HOURS, soit 36 h). Sans trace, trace
#   illisible ou trop ancienne : code 1 (fermé par défaut). Contrôle de recette R-I04 et healthcheck du service
#   db-backup (docker compose ps : « unhealthy » tant qu'aucune restauration n'a été vérifiée). Pas de base requise.
#
# Base jetable de `verifier` : nommée POKESHOP_VERIF_PREFIX + date + pid + aléa (préfixe par défaut
#   « pokeshop_verif_ » ; minuscules, chiffres et « _ », 40 caractères au plus, commençant par « pokeshop_verif_ »).
#   Un test ou une exécution parallèle passe son propre préfixe et ne touche qu'à ses bases (revue R5, R4-NEW-03).
#
# Le compte de DATABASE_URL doit pouvoir tout lire (y compris owner_token_fingerprint) et créer une base
# (verifier) : compte administrateur, jamais le compte de l'API. Aucun mot de passe n'est affiché.
set -euo pipefail
umask 077

if [ "${1:-}" != "etat" ]; then
    : "${DATABASE_URL:?Définir DATABASE_URL (compte administrateur de la base du moteur)}"
fi
BACKUP_DIR="${POKESHOP_BACKUP_DIR:-$HOME/pokeshop-sauvegardes}"
STATE_FILE="$BACKUP_DIR/derniere-verification.tsv"
KEEP="${POKESHOP_BACKUP_KEEP:-30}"
APPEND_ONLY="audit_log engine_state_journal stock_movements price_events price_decisions supplier_offers autonomy_levels"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "ÉCHEC : $*" >&2; exit 1; }
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# URL de la même instance, autre base (paramètres de requête conservés).
url_for_db() {
    local url="$1" db="$2" base query=""
    base="${url%%\?*}"
    if [[ "$url" == *\?* ]]; then query="?${url#*\?}"; fi
    printf '%s/%s%s' "${base%/*}" "$db" "$query"
}

q() { psql "$1" -X -q -A -t -F $'\t' -v ON_ERROR_STOP=1 -c "$2"; }

refuse_repo_dir() {
    local repo dir
    repo="$(cd "$here/.." && pwd -P)"
    mkdir -p "$BACKUP_DIR"
    dir="$(cd "$BACKUP_DIR" && pwd -P)"
    case "$dir/" in
        "$repo"/*) die "POKESHOP_BACKUP_DIR est dans le dépôt ($dir) : la sauvegarde contient coûts et marges, la ranger hors du dépôt" ;;
    esac
}

table_counts() {  # schéma.table<TAB>lignes, pour toutes les tables des schémas du moteur
    psql "$1" -X -q -A -t -F $'\t' -v ON_ERROR_STOP=1 <<'SQL'
SELECT format('SELECT %L, count(*) FROM %I.%I', n.nspname || '.' || c.relname, n.nspname, c.relname)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind IN ('r', 'p') AND n.nspname IN ('pokeshop', 'storefront')
 ORDER BY 1 \gexec
SQL
}

migrations() { q "$1" "SELECT string_agg(version || ':' || name, ',' ORDER BY version) FROM pokeshop.schema_migrations"; }

latest_backup() {
    { ls -1 "$BACKUP_DIR"/pokeshop-*.dump "$BACKUP_DIR"/pokeshop-*.dump.age 2>/dev/null || true; } | sort | tail -n 1
}

cmd_sauvegarde() {
    refuse_repo_dir
    command -v pg_dump >/dev/null || die "pg_dump absent (client PostgreSQL 16)"
    local stamp base dump manifest
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    base="$BACKUP_DIR/pokeshop-$stamp"
    manifest="$base.manifest"
    log "manifeste (journaux en ajout seul, migrations)"
    {
        echo "cree_le	$stamp"
        echo "migrations	$(migrations "$DATABASE_URL")"
        for t in $APPEND_ONLY; do
            echo "ajout_seul	pokeshop.$t	$(q "$DATABASE_URL" "SELECT count(*) FROM pokeshop.$t")"
        done
    } > "$manifest.partial"
    log "pg_dump (format personnalisé)"
    pg_dump "$DATABASE_URL" --format=custom --compress=6 --no-password --file "$base.dump.partial"
    dump="$base.dump"
    if [ -n "${POKESHOP_BACKUP_AGE_RECIPIENT:-}" ]; then
        command -v age >/dev/null || { rm -f "$base.dump.partial" "$manifest.partial"; die "chiffrement demandé mais age absent : aucune copie en clair n'est conservée"; }
        age --encrypt --recipient "$POKESHOP_BACKUP_AGE_RECIPIENT" --output "$base.dump.age.partial" "$base.dump.partial" \
            || { rm -f "$base.dump.partial" "$base.dump.age.partial" "$manifest.partial"; die "chiffrement age impossible"; }
        rm -f "$base.dump.partial"
        mv "$base.dump.age.partial" "$base.dump.age"
        dump="$base.dump.age"
    else
        mv "$base.dump.partial" "$dump"
    fi
    echo "fichier	$(basename "$dump")" >> "$manifest.partial"
    echo "sha256	$(sha256sum "$dump" | cut -d' ' -f1)" >> "$manifest.partial"
    mv "$manifest.partial" "$manifest"
    chmod 600 "$dump" "$manifest"
    log "sauvegarde écrite : $dump"
    # Rétention : les KEEP plus récentes (sauvegarde + manifeste).
    local old
    { ls -1 "$BACKUP_DIR"/pokeshop-*.manifest 2>/dev/null || true; } | sort | head -n "-$KEEP" | while read -r old; do
        rm -f "${old%.manifest}.dump" "${old%.manifest}.dump.age" "$old"
    done
    echo "$dump"
}

plain_dump() {  # fichier -> chemin d'un dump en clair (déchiffré dans un dossier temporaire si besoin)
    local file="$1" work="$2"
    case "$file" in
        *.age)
            [ -n "${POKESHOP_BACKUP_AGE_IDENTITY:-}" ] || die "sauvegarde chiffrée : définir POKESHOP_BACKUP_AGE_IDENTITY (clé privée)"
            age --decrypt --identity "$POKESHOP_BACKUP_AGE_IDENTITY" --output "$work/clair.dump" "$file" || die "déchiffrement impossible"
            echo "$work/clair.dump" ;;
        *) echo "$file" ;;
    esac
}

check_restored() {  # dump_en_clair url_restauree manifeste
    local dump="$1" url="$2" manifest="$3" errors=0 expected got table count want
    declare -A restored=()
    while IFS=$'\t' read -r table count; do
        [ -n "$table" ] && restored["$table"]="$count"
    done < <(table_counts "$url")
    # Lignes réellement contenues dans la sauvegarde (une ligne COPY = une ligne de table).
    while IFS=$'\t' read -r table count; do
        table="${table//\"/}"
        got="${restored[$table]:-absente}"
        if [ "$got" != "$count" ]; then
            echo "  table $table : $got ligne(s) restaurée(s), $count dans la sauvegarde" >&2
            errors=$((errors + 1))
        fi
    done < <(pg_restore --data-only --file=- "$dump" | awk '
        /^COPY [^ ]+ / && /FROM stdin;$/ { t = $2; n = 0; inside = 1; next }
        inside && $0 == "\\." { print t "\t" n; inside = 0; next }
        inside { n++ }')
    expected="$(awk -F'\t' '$1 == "migrations" { print $2 }' "$manifest")"
    got="$(migrations "$url")"
    if [ "$expected" != "$got" ]; then
        echo "  migrations restaurées « $got » ≠ manifeste « $expected »" >&2
        errors=$((errors + 1))
    fi
    while IFS=$'\t' read -r _ table want; do
        got="${restored[$table]:-0}"
        if [ "$got" -lt "$want" ]; then
            echo "  journal en ajout seul $table : $got ligne(s) < $want au début de la sauvegarde" >&2
            errors=$((errors + 1))
        fi
    done < <(awk -F'\t' '$1 == "ajout_seul"' "$manifest")
    for check in verify_audit_chain verify_engine_state_journal; do
        got="$(q "$url" "SELECT count(*) FROM pokeshop.$check()")"
        if [ "$got" != "0" ]; then
            echo "  pokeshop.$check() : $got anomalie(s) dans la base restaurée" >&2
            errors=$((errors + 1))
        fi
    done
    return "$errors"
}

check_file() {  # fichier manifeste
    local file="$1" manifest="$2" want got
    [ -f "$file" ] || die "sauvegarde introuvable : $file"
    [ -f "$manifest" ] || die "manifeste introuvable : $manifest"
    want="$(awk -F'\t' '$1 == "sha256" { print $2 }' "$manifest")"
    got="$(sha256sum "$file" | cut -d' ' -f1)"
    [ -n "$want" ] && [ "$want" = "$got" ] || die "empreinte sha256 différente du manifeste (fichier altéré ou incomplet) : $file"
}

manifest_for() { local f="${1%.age}"; echo "${f%.dump}.manifest"; }

SCRATCH=""
WORK=""
cleanup() {  # base jetable et fichiers déchiffrés supprimés quoi qu'il arrive
    if [ -n "$SCRATCH" ]; then
        q "$DATABASE_URL" "DROP DATABASE IF EXISTS \"$SCRATCH\" WITH (FORCE)" >/dev/null 2>&1 || true
    fi
    if [ -n "$WORK" ]; then rm -rf "$WORK"; fi
}
trap cleanup EXIT

cmd_verifier() {
    local file="${1:-}" manifest dump url status=0 prefix="${POKESHOP_VERIF_PREFIX:-pokeshop_verif_}"
    # Préfixe de la base jetable contrôlé AVANT tout accès (revue R5, R4-NEW-03 : un test ne touche qu'à ses bases).
    [[ "$prefix" =~ ^pokeshop_verif_[a-z0-9_]{0,25}$ ]] \
        || die "POKESHOP_VERIF_PREFIX invalide ($prefix) : « pokeshop_verif_ » suivi de minuscules, chiffres ou « _ »"
    [ -n "$file" ] || file="$(latest_backup)"
    [ -n "$file" ] || die "aucune sauvegarde dans $BACKUP_DIR"
    manifest="$(manifest_for "$file")"
    check_file "$file" "$manifest"
    WORK="$(mktemp -d)"
    SCRATCH="${prefix}$(date -u +%Y%m%d%H%M%S)_$$_${RANDOM}"
    echo "base jetable : $SCRATCH" >&2
    url="$(url_for_db "$DATABASE_URL" "$SCRATCH")"
    dump="$(plain_dump "$file" "$WORK")"
    log "restauration de $(basename "$file") dans la base jetable $SCRATCH"
    q "$DATABASE_URL" "CREATE DATABASE \"$SCRATCH\"" >/dev/null
    pg_restore --exit-on-error --no-password --dbname="$url" "$dump" || die "pg_restore en échec"
    check_restored "$dump" "$url" "$manifest" || status=$?
    if [ "$status" -ne 0 ]; then
        die "restauration NON conforme ($status anomalie(s)) : sauvegarde inutilisable, en refaire une et ouvrir un incident"
    fi
    log "restauration vérifiée : $(basename "$file") (lignes, migrations, chaînes sha256)"
    # Trace lue par `etat` (R-I04, healthcheck) : écrite seulement après une restauration conforme.
    printf '%s\t%s\t%s\t%s\n' "$(date -u +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "$file")" \
        "$(awk -F'\t' '$1 == "sha256" { print $2 }' "$manifest")" > "$STATE_FILE.partial"
    chmod 600 "$STATE_FILE.partial"
    mv "$STATE_FILE.partial" "$STATE_FILE"
    cleanup
    SCRATCH=""
    WORK=""
}

cmd_restaurer() {
    local file="${1:?fichier de sauvegarde}" target="${2:?URL de la base cible (vide)}" manifest dump tables status=0
    [ "$target" != "$DATABASE_URL" ] || die "la base cible doit différer de la base source"
    manifest="$(manifest_for "$file")"
    check_file "$file" "$manifest"
    tables="$(q "$target" "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname IN ('pokeshop', 'storefront')")"
    [ "$tables" = "0" ] || die "base cible non vide (schémas pokeshop/storefront présents) : restaurer dans une base neuve"
    WORK="$(mktemp -d)"
    dump="$(plain_dump "$file" "$WORK")"
    pg_restore --exit-on-error --no-password --dbname="$target" "$dump" || die "pg_restore en échec"
    check_restored "$dump" "$target" "$manifest" || status=$?
    [ "$status" -eq 0 ] || die "restauration NON conforme ($status anomalie(s))"
    log "base restaurée et vérifiée"
}

cmd_etat() {
    local interval max_age epoch stamp file now age
    interval="${POKESHOP_BACKUP_INTERVAL_HOURS:-24}"
    max_age="${POKESHOP_BACKUP_MAX_AGE_HOURS:-$(( interval * 3 / 2 ))}"
    [[ "$max_age" =~ ^[0-9]+$ ]] && [ "$max_age" -gt 0 ] || die "POKESHOP_BACKUP_MAX_AGE_HOURS : entier > 0 attendu"
    [ -f "$STATE_FILE" ] || die "aucune restauration vérifiée dans $BACKUP_DIR (lancer db/backup.sh verifier) : R-I04 non satisfait"
    IFS=$'\t' read -r epoch stamp file _ < "$STATE_FILE" || true
    [[ "${epoch:-}" =~ ^[0-9]+$ ]] || die "trace de vérification illisible ($STATE_FILE) : R-I04 non satisfait"
    now="$(date -u +%s)"
    age=$(( (now - epoch) / 3600 ))
    if [ "$epoch" -gt "$(( now + 300 ))" ]; then
        die "trace de vérification datée du futur ($stamp) : horloge ou trace non fiable"
    fi
    if [ "$(( now - epoch ))" -gt "$(( max_age * 3600 ))" ]; then
        die "dernière restauration vérifiée le $stamp ($file), il y a ${age} h > ${max_age} h : R-I04 non satisfait"
    fi
    echo "OK : restauration vérifiée le $stamp ($file), il y a ${age} h (≤ ${max_age} h)"
}

cmd_boucle() {
    local hours="${POKESHOP_BACKUP_INTERVAL_HOURS:-24}" file
    while true; do
        # Un processus par étape : un échec (die) n'arrête pas la boucle et la base jetable est toujours supprimée.
        if file="$(bash "${BASH_SOURCE[0]}" sauvegarde | tail -n 1)" && bash "${BASH_SOURCE[0]}" verifier "$file"; then
            log "sauvegarde et restauration vérifiées"
        else
            log "ÉCHEC de la sauvegarde ou du test de restauration : intervention requise"
        fi
        sleep "$((hours * 3600))"
    done
}

case "${1:-}" in
    sauvegarde) cmd_sauvegarde ;;
    verifier) shift; cmd_verifier "${1:-}" ;;
    restaurer) shift; cmd_restaurer "$@" ;;
    boucle) cmd_boucle ;;
    etat) cmd_etat ;;
    *) echo "usage : db/backup.sh sauvegarde | verifier [FICHIER] | restaurer FICHIER URL_CIBLE | boucle | etat" >&2; exit 2 ;;
esac
