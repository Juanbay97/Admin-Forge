#!/bin/sh
# Restore the DATA of a Forge dump into an empty, freshly migrated database (runs inside the `restore` compose
# service, profile `tools`).
#
#   FORGE_MIGRATE_SEED=0 docker compose up -d --wait              # migrate builds the reviewed schema (empty: no catalog seed)
#   docker compose stop control-plane caddy                       # nothing may write while restoring
#   docker compose --profile tools run --rm restore /backups/forge-<stamp>.dump
#   docker compose up -d --wait
#
# Only rows are restored. The schema must always be the one `migrate` built: the schema attestation hashes deparsed
# expressions that a full dump/restore round trip rewrites, so a restored schema would never attest. Therefore:
#   * TARGET_NOT_EMPTY (exit 3)           some Forge table already has rows; nothing was changed.
#   * SCHEMA_VERSION_MISMATCH (exit 4)    the migration ledger differs from the dump's (run the same code version that
#                                         took the dump, and `docker compose up -d --wait` first); nothing was changed.
# The dump is applied in ONE transaction, so a failure leaves the database empty.
set -eu

dump=${1:-}
if [ -z "$dump" ] || [ ! -r "$dump" ]; then
    echo "usage: restore.sh <dump file>" >&2
    exit 2
fi
pg_restore --list "$dump" > /dev/null || { echo "DUMP_INVALID: pg_restore cannot read $dump" >&2; exit 2; }

PGPASSWORD=$(cat /run/secrets/pg_superuser)
export PGPASSWORD
export PGHOST="${FORGE_DB_HOST:-postgres}" PGUSER=postgres PGDATABASE="${FORGE_DB_NAME:-forge}"
export PGCONNECT_TIMEOUT=10 PGSSLMODE=disable
tab=$(printf '\t')

# 1. Same schema version: the ledger forge_ops.schema_migrations (version, name, sha256) must be identical.
in_dump=$(pg_restore --data-only --schema=forge_ops --table=schema_migrations --file=- "$dump" \
    | awk -F'\t' '/^COPY /{ inside = 1; next } /^\\\./{ inside = 0 } inside { print $1 "\t" $2 "\t" $3 }' | sort -n)
in_database=$(psql -X -tA -F "$tab" -c 'SELECT version, name, sha256 FROM forge_ops.schema_migrations ORDER BY version' 2>/dev/null | sort -n || true)
if [ -z "$in_dump" ] || [ "$in_dump" != "$in_database" ]; then
    echo "SCHEMA_VERSION_MISMATCH: the database was not migrated to the dump's schema version; nothing was changed" >&2
    exit 4
fi

# 2. Empty: no Forge table holds a row (a freshly migrated database has none).
rows=$(psql -X -tA -c "SELECT coalesce(sum((xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', schemaname, tablename), false, true, '')))[1]::text::bigint), 0) FROM pg_tables WHERE schemaname = 'forge'")
if [ "$rows" != "0" ]; then
    echo "TARGET_NOT_EMPTY: the Forge tables already hold data; nothing was changed" >&2
    exit 3
fi

pg_restore --data-only --disable-triggers --exclude-schema=forge_ops --single-transaction --exit-on-error \
    --no-password --dbname="$PGDATABASE" "$dump"
echo "RESTORED: data of $(basename "$dump"); now run: docker compose up -d --wait"
