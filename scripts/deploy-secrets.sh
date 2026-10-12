#!/bin/sh
# Generate the deployment secrets once. Usage: scripts/deploy-secrets.sh [directory]
#
# * Idempotent: an existing file is NEVER overwritten (rotating a Fernet key would orphan stored data).
# * Prints names only, never values.
# * The directory is the access boundary (0700, owner only). Files are 0644 on purpose: Docker bind-mounts
#   them as Docker secrets and the unprivileged container users (uid 10001, postgres) must be able to read them.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dir=${1:-"$here/../deploy/secrets"}

mkdir -p "$dir"
chmod 700 "$dir"

password() { head -c 48 /dev/urandom | base64 | tr -d '=+/\n' | cut -c1-40; }
# A Fernet key is 32 random bytes, urlsafe base64 (44 characters with padding).
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '\n'; }

create() {
    name=$1
    generator=$2
    target="$dir/$name"
    if [ -e "$target" ]; then
        echo "kept     $name"
        return 0
    fi
    temporary="$target.partial"
    ( umask 077; "$generator" > "$temporary"; printf '\n' >> "$temporary" )
    chmod 644 "$temporary"
    mv "$temporary" "$target"
    echo "created  $name"
}

for name in pg_superuser \
    role_forge_account_service role_forge_enrollment role_forge_runtime role_forge_gateway_service \
    role_forge_branding_service role_backup; do
    create "$name" password
done
create delivery_key fernet
create gateway_key fernet

echo "secrets directory: $dir"
echo "Back it up OFFLINE: losing delivery_key/gateway_key makes stored gateway keys and queued messages unrecoverable."
