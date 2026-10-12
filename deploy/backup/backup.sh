#!/bin/sh
# Forge database backups (runs inside the `backup` compose service, PostgreSQL client tools only).
#
#   backup.sh loop                         run on the FORGE_BACKUP_CRON schedule (UTC) forever
#   backup.sh run-once                     one verified dump now, then prune
#   backup.sh prune                        keep only the newest FORGE_BACKUP_KEEP dumps
#   backup.sh cron-match "<cron>" "<m h dom mon dow>"   exit 0 match, 1 no match, 2 malformed (used by tests)
#
# Each run writes one file into the backup directory: forge-<UTC stamp>.dump, the pg_dump custom format of the Forge
# database taken as the read-only backup_reader role. Roles are not dumped: the migrations create them.
# A dump only counts once `pg_restore --list` can read it. Neither the secret files nor the environment file are ever copied here.
# The schedule is a 5-field cron expression: lists, ranges, `*` and `*/n` are supported; day-of-month and
# day-of-week must both match when both are restricted.
set -eu
umask 077

dir=${FORGE_BACKUP_DIR:-/backups}
keep=${FORGE_BACKUP_KEEP:-14}
cron=${FORGE_BACKUP_CRON:-30 2 * * *}

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*"; }

cron_match() {
    awk -v cron="$1" -v now="$2" '
    function field(spec, value, low, high,    n, parts, i, part, step, bounds) {
        n = split(spec, parts, ",")
        hit = 0
        for (i = 1; i <= n; i++) {
            part = parts[i]; step = 1
            if (part ~ /\//) {
                split(part, bounds, "/")
                if (bounds[2] !~ /^[0-9]+$/ || bounds[2] + 0 < 1) { invalid = 1; return 0 }
                part = bounds[1]; step = bounds[2] + 0
            }
            if (part == "*") { lo = low; hi = high }
            else if (part ~ /^[0-9]+-[0-9]+$/) { split(part, bounds, "-"); lo = bounds[1] + 0; hi = bounds[2] + 0 }
            else if (part ~ /^[0-9]+$/) { lo = part + 0; hi = (step > 1) ? high : lo }
            else { invalid = 1; return 0 }
            if (lo < low || hi > high || lo > hi) { invalid = 1; return 0 }
            if (value >= lo && value <= hi && (value - lo) % step == 0) hit = 1
        }
        return hit
    }
    BEGIN {
        if (split(cron, c, " ") != 5 || split(now, t, " ") != 5) exit 2
        minute = field(c[1], t[1] + 0, 0, 59)
        hour = field(c[2], t[2] + 0, 0, 23)
        day = field(c[3], t[3] + 0, 1, 31)
        month = field(c[4], t[4] + 0, 1, 12)
        weekday = field(c[5], t[5] % 7, 0, 7)
        if (!weekday && t[5] % 7 == 0) weekday = field(c[5], 7, 0, 7)   # Sunday is 0 or 7
        if (invalid) exit 2
        exit (minute && hour && day && month && weekday) ? 0 : 1
    }'
}

prune() {
    case $keep in ''|*[!0-9]*) log "FORGE_BACKUP_KEEP must be a positive integer" >&2; exit 2 ;; esac
    [ "$keep" -ge 1 ] || { log "FORGE_BACKUP_KEEP must be a positive integer" >&2; exit 2; }
    ls -1 "$dir"/forge-*.dump 2>/dev/null | sort -r | awk -v keep="$keep" 'NR > keep' | while IFS= read -r old; do
        rm -f -- "$old"
        log "pruned $(basename "$old")"
    done
}

connect() {
    password_file=${FORGE_BACKUP_PASSWORD_FILE:-/run/secrets/backup_reader}
    [ -r "$password_file" ] || { log "BACKUP_PASSWORD_FILE_MISSING" >&2; exit 1; }
    PGPASSWORD=$(cat "$password_file")
    export PGPASSWORD
    export PGHOST="${FORGE_DB_HOST:-postgres}" PGDATABASE="${FORGE_DB_NAME:-forge}" PGUSER="${FORGE_BACKUP_USER:-backup_reader}"
    export PGCONNECT_TIMEOUT=10 PGSSLMODE=disable
}

run_once() {
    connect
    mkdir -p "$dir"
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    dump="$dir/forge-$stamp.dump"
    trap 'rm -f -- "$dump.partial"' EXIT
    pg_dump --format=custom --file="$dump.partial"
    pg_restore --list "$dump.partial" > /dev/null
    mv "$dump.partial" "$dump"
    trap - EXIT
    log "wrote $(basename "$dump") ($(wc -c < "$dump" | tr -d ' ') bytes)"
}

loop() {
    rc=0
    cron_match "$cron" "0 0 1 1 0" || rc=$?
    [ "$rc" -ne 2 ] || { log "FORGE_BACKUP_CRON is not a valid 5-field schedule" >&2; exit 2; }
    log "scheduled: $cron (UTC), keeping $keep"
    last=
    while :; do
        minute=$(date -u +%Y%m%d%H%M)
        now=$(date -u '+%M %H %d %m %w' | awk '{ print $1 + 0, $2 + 0, $3 + 0, $4 + 0, $5 + 0 }')
        if [ "$minute" != "$last" ] && cron_match "$cron" "$now"; then
            last=$minute
            if ( run_once ); then prune; else log "FAILED (the previous dumps are untouched)" >&2; fi
        fi
        sleep 20
    done
}

case "${1:-}" in
    run-once) run_once; prune ;;
    prune) prune ;;
    loop) loop ;;
    cron-match) [ "$#" -eq 3 ] || exit 2; cron_match "$2" "$3" ;;
    *) echo "usage: backup.sh loop | run-once | prune | cron-match <cron> <now>" >&2; exit 2 ;;
esac
