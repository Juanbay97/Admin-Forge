#!/bin/sh
# Runs the trusted provisioning CLI inside the `provision` compose service (profile `tools`).
#
# The CLI reads a private operator file with numeric-loopback connection details. This wrapper builds that file
# from the Docker secret on a tmpfs (mode 0600), removes it on exit, and never prints it. Credentials issued by the
# run go to a NEW timestamped file in /credentials: an existing file is never overwritten.
set -eu
umask 077

operator=/tmp/operator.json
python - "$operator" <<'PY'
import json
import sys

with open('/run/secrets/pg_superuser', encoding='utf-8') as secret:
    password = secret.read().rstrip('\r\n')
with open(sys.argv[1], 'w', encoding='utf-8') as output:
    json.dump({'host': '127.0.0.1', 'port': 5432, 'dbname': 'forge', 'user': 'postgres', 'password': password}, output)
PY

status=0
python -m forge.provision --operator-file "$operator" \
    --credentials-file "/credentials/credentials-$(date -u +%Y%m%dT%H%M%SZ).json" "$@" || status=$?
rm -f "$operator"
exit "$status"
