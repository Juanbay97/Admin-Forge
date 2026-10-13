# Deploy Forge on an Ubuntu server (Docker Compose)

This runbook takes a fresh Ubuntu 22.04/24.04 server (for example a Proxmox VM) to a running Forge control plane:
PostgreSQL 17, one-shot migrations, the API and admin web, and Caddy for HTTPS. Everything is configured by
environment variables and Docker secrets; the domain name is never written into a file other than `deploy/.env`.

## Quick path

Replace `forge.example.test` with your real name. Run everything as a user who can run `docker`.

```bash
git clone <repository-url> /opt/forge && cd /opt/forge/deploy
cp .env.example .env                      # set FORGE_DOMAIN, FORGE_TLS, FORGE_ACME_EMAIL and the FORGE_SMTP_* mail relay
printf 'FORGE_UID=%s\nFORGE_GID=%s\n' "$(id -u)" "$(id -g)" >> .env
mkdir -p backups credentials              # owned by you: backups and first-company credentials land here
../scripts/deploy-secrets.sh              # creates deploy/secrets/ (once; never overwritten)
docker compose up -d --build --wait       # postgres -> migrate -> control-plane -> caddy
curl -fsS "https://forge.example.test/status"   # {"status":"ready", ...}
```

Expected result: `docker compose ps` shows `postgres`, `control-plane`, `caddy` and `backup` healthy and `migrate`
exited (0). Then back up `deploy/secrets/` offline ([Backup and restore](#backup-and-restore)) and
[provision the first company](#provision-the-first-company).

## Prerequisites

| Need | Detail |
|------|--------|
| Server | Ubuntu 22.04 or 24.04, 2 vCPU, 4 GB RAM, 20 GB disk (database and dumps grow with use) |
| Docker | Docker Engine 25+ with the Compose plugin 2.24+ (`docker compose version`). Install from the official Docker documentation (docs.docker.com/engine/install/ubuntu) |
| Network | Outbound HTTPS (image pulls, the gateway, Let's Encrypt) and, for `FORGE_TLS=acme`, inbound 80 and 443 from the internet |
| Name | A DNS name you control (this guide uses `forge.example.test`) |
| Time | The server clock must be synchronised (`timedatectl` shows `System clock synchronized: yes`); certificates and tokens depend on it |

On a Proxmox VM: give it a bridged network interface, enable the QEMU guest agent, and snapshot the VM before the
first deployment so you can return to a clean server.

## DNS and firewall

1. Create an `A` record (and `AAAA` if the server has IPv6) for your name pointing at the server's public address.
2. Open the firewall for the services Caddy publishes (nothing else is published):

| Port | Use | Needed when |
|------|-----|-------------|
| 80/tcp | ACME HTTP challenge and redirect to HTTPS | `FORGE_TLS=acme` |
| 443/tcp and 443/udp | HTTPS (HTTP/3 over udp) | always |
| 22/tcp | Administration | restrict to your admin addresses |

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443 && sudo ufw enable
```

Docker publishes ports through its own iptables rules, so `ufw` does not hide them: this stack relies on publishing
only Caddy. PostgreSQL and the control plane have no published port and live on a Docker network with no route out
(`data`).

## Configuration and secrets

`deploy/.env` (copied from `.env.example`) holds placeholders only; `deploy/secrets/` holds every credential.

| Setting | Meaning |
|---------|---------|
| `FORGE_DOMAIN` | Public name; also the value Caddy serves and the control plane accepts as `Host` |
| `FORGE_PORT_SUFFIX` | Empty in production; `:8443` only when HTTPS is published on a non-standard port |
| `FORGE_TLS` | `acme` or `internal` ([Choose the TLS mode](#choose-the-tls-mode)); anything else stops Caddy |
| `FORGE_ACME_EMAIL` | Contact address Let's Encrypt uses for expiry notices (`acme` only) |
| `FORGE_SMTP_*` | The mail relay for invitations and password resets ([Email delivery](#email-delivery-smtp)); required |
| `FORGE_GATEWAY_ORIGINS` | Comma-separated https origins of your model gateway; empty keeps the built-in default. It is the only origin authority: a gateway key can only be created for an origin listed here |
| `FORGE_GATEWAY_CA_FILE` | Optional absolute path of an extra CA certificate for a private gateway (the allow-list stays https-only); unset means the system trust store |
| `FORGE_BACKUP_CRON`, `FORGE_BACKUP_KEEP` | Backup schedule (UTC, 5 fields) and how many dumps to keep (default 14) |
| `FORGE_UID`, `FORGE_GID` | Your user, so `backups/` and `credentials/` stay readable by you |

`scripts/deploy-secrets.sh` writes twelve files: the PostgreSQL administrator password, one password per service role
(six), the backup role password, three Fernet keys (`delivery_key` for queued messages, `gateway_key` for stored
gateway keys, `platform_key` for the platform owner's authenticator secret) and an empty `smtp_password` for you to fill in. It never overwrites an existing file, prints names only, and makes the directory owner-only (0700).
The files themselves are world-readable inside that directory because the unprivileged containers read them as
Docker secrets.

Check the result without exposing a secret: `docker compose config | grep -c -i password` must not print a password
value (secrets appear only as file references).

## Choose the TLS mode

| | `FORGE_TLS=acme` | `FORGE_TLS=internal` |
|---|---|---|
| Certificate | Let's Encrypt, trusted by every browser | Caddy's own CA, trusted only after you install its root |
| Needs | Public DNS name, ports 80 and 443 reachable from the internet | Nothing public |
| Use for | An internet-facing server | A private network, a lab, a local proof |

For `internal`, export the root certificate once and install it on each client machine that opens the admin web:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

Switching modes later is a `.env` edit and `docker compose up -d`; no file changes. If you start with `acme` and
issuance fails (for example port 80 is not reachable), set `FORGE_TLS=internal` to keep working while you fix DNS.

## Email delivery (SMTP)

Forge emails invitations and password resets through any standard SMTP relay. There is no fallback: the control plane
refuses to start without one (`CONFIG_INVALID:FORGE_SMTP_HOST`), because a message that goes nowhere is a lost invitation.
The message holds only the person's name and a private one-time link, never a password.

| Setting | Meaning |
|---------|---------|
| `FORGE_SMTP_HOST` / `FORGE_SMTP_PORT` | Relay and port (587 by default for `starttls`, 465 for `tls`) |
| `FORGE_SMTP_SECURITY` | `starttls` (default: upgrades before logging in, refuses a relay without STARTTLS), `tls` (implicit TLS) or `none` (cleartext, never with credentials) |
| `FORGE_SMTP_USER` + `FORGE_SMTP_PASSWORD_FILE` | Relay credentials; the password is read from `deploy/secrets/smtp_password` |
| `FORGE_SMTP_FROM` | Sender address, on a domain the relay has verified |
| `FORGE_SMTP_CA_FILE` | Optional CA bundle for a private relay (certificates are always verified) |

| Provider | `.env` values | `smtp_password` holds |
|----------|---------------|------------------------|
| Resend, implicit TLS | `FORGE_SMTP_HOST=smtp.resend.com`, `FORGE_SMTP_PORT=465`, `FORGE_SMTP_SECURITY=tls`, `FORGE_SMTP_USER=resend` | Your Resend API key |
| Resend, STARTTLS | same host, `FORGE_SMTP_PORT=587`, `FORGE_SMTP_SECURITY=starttls`, `FORGE_SMTP_USER=resend` | Your Resend API key |
| Amazon SES | `FORGE_SMTP_HOST=email-smtp.<region>.amazonaws.com`, `FORGE_SMTP_PORT=587`, `FORGE_SMTP_SECURITY=starttls`, `FORGE_SMTP_USER=<SES SMTP user name>` | The SES SMTP password (not an IAM secret key) |

Set it up:

1. Verify the sending domain with the provider: publish the SPF and DKIM DNS records it gives you and wait until it
   shows the domain as verified. Set `FORGE_SMTP_FROM` to an address on that domain.
2. Put the relay password in the secret file without leaving it in your shell history, then keep the permissions:
   `read -rs P && printf '%s' "$P" > secrets/smtp_password && unset P`.
3. Add `FORGE_SMTP_PASSWORD_FILE=/run/secrets/smtp_password` and the values above to `.env`, then `docker compose up -d`.
4. Send a test message (it prints one word: `sent` or the failure category):

```bash
docker compose exec -T -e TO=you@example.test control-plane python - <<'PY'
import os, uuid
from forge.smtp_delivery import SmtpDelivery, SmtpDeliveryError, load_smtp_settings
try:
    SmtpDelivery(load_smtp_settings(os.environ)).deliver(
        uuid.uuid4(), os.environ['TO'], 'Smoke test', os.environ['FORGE_PUBLIC_ORIGIN'] + '/onboarding#smtp-check')
    print('sent')
except SmtpDeliveryError as error:
    print(error)
PY
```

When an invitation answers `delivery_state: failed`, nothing is written to the logs (a relay's answer could name the
recipient or the account), so run the check above and read the category:

| Category | Meaning | Fix |
|----------|---------|-----|
| `SMTP_AUTH` | The relay refused the credentials, or wants them and none were sent | Check `FORGE_SMTP_USER` and `smtp_password`; for Resend the user is exactly `resend` |
| `SMTP_TLS` | Certificate not trusted, name mismatch, or `tls` on a port that is not implicit TLS | Match port and mode (465 + `tls`, 587 + `starttls`); use `FORGE_SMTP_CA_FILE` for a private relay |
| `SMTP_STARTTLS_REQUIRED` | `starttls` on a relay that does not offer it; nothing was sent | Use the TLS port, or `FORGE_SMTP_SECURITY=tls` |
| `SMTP_RECIPIENT` / `SMTP_SENDER` | The relay refused the address, or the `From` domain is not verified | Verify the sending domain; check the address |
| `SMTP_TIMEOUT` / `SMTP_CONNECT` | No answer within 10 s, or the connection failed | The server must reach the relay outbound on 465/587; check the firewall and DNS |
| `SMTP_REJECTED` / `SMTP_UNAVAILABLE` | The relay refused the message or answered unexpectedly | Read your provider's sending dashboard |

Delivery is synchronous: a slow relay delays the request that sends the invitation by up to 10 seconds, then it is
recorded as failed (invite again once the relay is fixed).

## First platform owner

The platform owner is a Forge account that belongs to no company. It is created once, on the server, by the `platform`
service (profile `tools`, so `up` never starts it). The command never prints or stores a password and cannot be reached
over HTTP: it writes a **single-use set-password link** to a new private file in `deploy/credentials/` (an existing
file is never overwritten) and can mail the same link through the relay you configured.

```bash
docker compose --profile tools run --rm platform bootstrap-owner \
  --email owner@example.test --name "Platform Owner" --link-file /credentials/owner-link.txt --smtp
```

Expected: `{"status": "created", "link_file": "/credentials/owner-link.txt", "delivery": "delivered"}`.

1. `--smtp` mails the link through `FORGE_SMTP_*`; leave it out to use the file alone. `"delivery": "failed"` means the
   relay refused or did not answer: the file still holds the link (run the one-command check in
   [Email delivery](#email-delivery-smtp) to see why).
2. Open the link, set a password, then delete `deploy/credentials/owner-link.txt`. The link works once and expires after
   24 hours (`--ttl-hours`, 1 to 168); only a digest of it is stored in the database.
3. Running the command again is a no-op (`{"status": "exists"}`): once an owner exists nothing is created and no file
   is written. If the link was lost or expired before use, use the owner's normal forgot-password flow on the sign-in page.
4. For local testing without a relay, `--mailbox-dir <private folder>` writes the message as an `.eml` file instead.
5. Next: sign in, enrol the mandatory second factor and create companies ([Platform sign-in and companies](#platform-sign-in-and-companies)).

## Platform sign-in and companies

The platform API lives under `/forge/v1/platform/` and is deliberately absent from the published API contract. It
authenticates with the owner's normal Forge session (`POST /forge/v1/accounts/login`) and then REQUIRES a second factor
for that very session: until the TOTP step below passes, every call except `GET me`, `POST mfa/enroll` and
`POST login/mfa` answers `MFA_REQUIRED`. Changes (creating, suspending or editing a company) additionally need a TOTP
check from the last 30 minutes. Replace `forge.example.test` and `$TOKEN` (the `access_token` of the login reply).

```bash
curl -fsS https://forge.example.test/forge/v1/accounts/login -H 'Content-Type: application/json' \
  -d '{"email":"owner@example.test","password":"<the password you set>"}'

# Once: enrol an authenticator app. The reply holds the secret, an otpauth:// URI and ten single-use recovery codes.
curl -fsS -X POST https://forge.example.test/forge/v1/platform/mfa/enroll -H "Authorization: Bearer $TOKEN"
curl -fsS https://forge.example.test/forge/v1/platform/login/mfa -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"code":"123456"}'
```

* Store the recovery codes offline: they are shown once and kept only as hashes. A new sign-in (a new session) must pass
  the factor again, with `{"code":"123456"}` or `{"recovery_code":"ABCD-EFGH-IJKL-MNOP"}` (each recovery code works once).
* A TOTP step is accepted once; five wrong attempts lock the factor for 15 minutes (`MFA_LOCKED`, `Retry-After`).
* The factor cannot be replaced through the API once active. If the authenticator is lost and the recovery codes too,
  the operator removes it in the database (delete the owner's rows in `forge.platform_totp`, `forge.platform_recovery_codes`
  and `forge.platform_mfa_sessions`) and the owner enrols again.

Create a company: its code is the slug employees type, and the first administrator receives an invitation email whose
link also carries the code (the invitation lasts seven days).

```bash
curl -fsS https://forge.example.test/forge/v1/platform/companies -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme","display_name":"Acme Corporation","department":"Operations","admin_email":"admin@example.test","admin_name":"Acme Admin"}'
```

Expected: `201` with the company and `"invitation": {"delivery_state": "delivered", "delivery_channel": "smtp", ...}`. A taken
code is `409 COMPANY_CONFLICT` and creates nothing. If delivery says `failed`, the company exists: fix the relay and see
[Email delivery](#email-delivery-smtp) (the invitation cannot be re-sent yet).

| Call | What it does |
|------|--------------|
| `GET /forge/v1/platform/me` | Your identity and second-factor state |
| `GET /forge/v1/platform/companies?after=<code>&page=<1-100>` | Page through every company, ordered by code |
| `GET /forge/v1/platform/companies/<id>` | One company |
| `POST /forge/v1/platform/companies/<id>/suspend` | Deny the company's members, administrators and inference at once; nothing is deleted |
| `POST /forge/v1/platform/companies/<id>/reactivate` | Restore access immediately |
| `GET`/`PUT /forge/v1/platform/companies/<id>/branding`, `POST .../branding/reset` | Read or edit a company's branding (`expectedRevision` as in the company admin API; logos are uploaded by the company) |
| `GET /forge/v1/platform/audit?before=<id>&page=<1-100>` | The append-only audit log, newest first |

Every change writes one audit row (who, what, which company, when; never an email or a secret). Company administrators
keep editing their own branding; they are never platform identities (`PLATFORM_DENIED`).

## Gateway keys and usage

Gateway keys belong to the platform, not to a company. The platform owner (a verified second factor, as above) creates keys,
assigns them to companies with a priority, sets which upstream models each company may use and the price of each model. Company
administrators see only whether a gateway is usable; they cannot read or write a key (`PUT /forge/v1/orgs/<id>/gateway` is
`403 GATEWAY_MANAGED_BY_PLATFORM`, and the status is `revision` = number of usable keys, no origin, label or key data).

| Call (platform owner) | What it does |
|-----------------------|--------------|
| `POST /forge/v1/platform/gateway-keys` `{"label","origin","key"}` | Create a key. `origin` must be in `FORGE_GATEWAY_ORIGINS`; `key` is optional (a placeholder is never routed). The key text is write-only: it is sealed (bound to the key id, its revision and the origin) and only a last-4 hint is ever shown |
| `GET /forge/v1/platform/gateway-keys` | Labels, origins, hints, revisions, status and how many companies use each key; never key text |
| `POST /forge/v1/platform/gateway-keys/<id>/rotate` `{"expected_revision","key"}` | New key text, same id; takes effect for new requests, in-flight streams finish on the old value |
| `POST /forge/v1/platform/gateway-keys/<id>/disable`, `.../enable` | A disabled key is never selected |
| `PUT /forge/v1/platform/companies/<id>/gateway-keys` `{"keys":[{"key_id","priority","active"}]}` | The company's whole key list; the lowest priority number serves first |
| `PUT /forge/v1/platform/companies/<id>/model-access` `{"models":["upstream-id"]}` | The upstream models the company may publish and use (an empty list denies everything; a shrink applies on the next request) |
| `POST /forge/v1/platform/prices` `{"upstream_id","input_micros","output_micros","effective_from"}` | A new price version, integer micro-USD per million tokens; `GET /forge/v1/platform/prices?upstream_id=` lists versions |

Routing tries the active keys in priority order and moves to the next only when the gateway answers 401, 429, 5xx or cannot be
reached *before the first byte* reached the member; each key is tried at most once per request. Rotating, reordering or disabling keys
never stales a company's published catalogue. Losing `gateway_key` makes every stored key unrecoverable ([Backup and restore](#backup-and-restore)).

Every inference that reaches the gateway writes one usage row (company, member, model, serving key, token counts, timings,
status; no prompt or response text). Token counts come from the gateway's final usage chunk; when it is missing (cancelled
stream, failure, an older gateway) they are estimated at four characters per token and marked `estimated`. Cost is snapshotted from the
price in force when the row is written; a model without a price is counted as `unpriced_requests`, never as free. Reports (UTC days,
at most 366 per request, `page` 1-100):

| Call | Who | What |
|------|-----|------|
| `GET /forge/v1/platform/usage/companies?from=YYYY-MM-DD&to=YYYY-MM-DD&after=<company id>&page=` | platform owner | usage per company |
| `GET /forge/v1/platform/usage/models?from=&to=&after=<upstream id>&page=` | platform owner | usage per upstream model |
| `GET /forge/v1/platform/usage/totals?from=&to=` | platform owner | totals and the number of companies |
| `GET /forge/v1/orgs/<id>/usage/members?from=&to=&after=<member id>&page=` | that company's administrator | per-person usage, suspended members included |

**The local proof meters real inference.** `scripts/deploy-smoke.ps1` generates a throwaway certificate for a fake gateway
(`python -m forge.fake_gateway --make-cert DIR --name fake-gateway`), serves it over https from the dev-only `fake-gateway` service in
`deploy/compose.dev.yml` and points `FORGE_GATEWAY_ORIGINS=https://fake-gateway:3413` and `FORGE_GATEWAY_CA_FILE` at it, because the
production allow-list refuses plain http. The proof then assigns a rejected key as the primary and a good key second, chats as a member
(the request fails over), and reads the usage as the owner and as the company administrator.

The smoke gateway runs with `--openai-realistic`: it streams what OpenAI and OpenAI-compatible gateways really send (`"usage": null`
on every content chunk, `system_fingerprint`, `service_tier`, `obfuscation`, `refusal`/`logprobs` null, and a terminal usage chunk with
`prompt_tokens_details`, `completion_tokens_details` and `cost`). The streaming adapter keeps exact validation of what it uses (token
counts are non-negative integers and a `total_tokens` must add up) and ignores those known optional extras, which are bounded in depth
(3), entries (16) and text (256 characters). Output carriers stay refused: a non-null `refusal`, `tool_calls`, `logprobs`,
`function_call` or any other delta key still fails the stream closed.

## Provision the first company

Companies are normally created through the platform API above; the `provision` tool remains for the very first
company and for recovery. The `provision` service is in the `tools` profile, so `up` never starts it. It reaches the database through
the PostgreSQL container's own loopback and writes the new administrator's initial password to a new file in
`deploy/credentials/` (an existing file is never overwritten; running it again creates nothing).

```bash
docker compose --profile tools run --rm provision org \
  --slug acme --name "Acme Corporation" --department Operations \
  --admin-email admin@example.test --admin-name "Acme Admin"
```

Expected: `{"status": "provisioned", "credentials_file": "...", "organizations": [{"slug": "acme", "created": true}]}`.

1. Read the password from `deploy/credentials/credentials-<timestamp>.json` and hand it over through a private channel.
2. Delete the file once delivered; it is the only copy.
3. The administrator signs in at `https://forge.example.test/admin/` and invites members from there.

## Rotate the policy signing key

The capability policy (`GET /forge/v1/capabilities/effective`) is signed with the Ed25519 seed in `deploy/secrets/policy_key`; clients verify it
against the published key set (`GET /forge/v1/capabilities/keys`, public). A document signed before a rotation stays valid for its 24 hours, so
the old *public* key must stay in the published set as `retired` until then. Rotation is configuration, not code:

1. **Record the current public key.** `curl -s https://forge.example.test/forge/v1/capabilities/keys` and copy the `public_key` of the entry with
   `"status": "active"` (and its `kid`). It is public; nothing secret is copied.
2. **Back up the old seed offline**, then create the new one (`head -c 32 /dev/urandom | basenc --base64url | tr -d '='`, or the
   `scripts/deploy-secrets.*` generator into a scratch directory) into a scratch file.
   **Sign the rotation statement with the OLD key before replacing the secret** (one line of JSON on stdout, public data):
   `docker compose run --rm --entrypoint python -v <dir>:/keys:ro control-plane -m forge.capability_rotation sign --old-seed-file /keys/policy_key.old --new-seed-file /keys/policy_key.new`
   (`--new-public-key <key>` instead of the seed file, `--issued-at 2026-10-13T00:00:00Z` to fix the date). The statement is
   `{"schema": "forge.policy-key-rotation.v1", "old_kid", "new_kid", "new_public_key", "issued_at", "sig"}`; `sig` is Ed25519 by the old key
   over the canonical JSON (sorted keys, no whitespace) of the other fields. Then install the new seed as `deploy/secrets/policy_key`.
3. **List the old public key as retired** in `deploy/.env` (space or comma separated, at most 8; keep the previous rotation's keys while their
   documents could still be alive, then drop them): `FORGE_POLICY_RETIRED_KEYS=<old public_key>`. A file works too:
   `FORGE_POLICY_RETIRED_KEYS_FILE=/run/secrets/...` (one key per line, `#` comments allowed). Setting both is refused. **Add the statement** to
   `FORGE_POLICY_ROTATIONS` (a JSON list, oldest first, one statement per retired key; `FORGE_POLICY_ROTATIONS_FILE` works too).
4. **Restart the control plane** (`docker compose up -d control-plane`). It refuses to start (`CONFIG_INVALID:FORGE_POLICY_RETIRED_KEYS`) when a key is
   not 32 bytes of base64url, is repeated, is the new active key, or when there is no signing key at all, and
   (`CONFIG_INVALID:FORGE_POLICY_ROTATIONS`) when a statement is not signed by one of the retired keys, names a key that is neither retired nor
   the active one, repeats a signer or is not valid JSON.
5. **Check** `GET /forge/v1/capabilities/keys`: the new key is `active` and the old `kid` is `retired`; `GET /forge/v1/capabilities/pinning`
   (public, hidden) returns `{"schema": "forge.policy-pinning.v1", "keys": [...], "rotations": [...]}`. Members' devices keep verifying documents
   signed by the old key until they expire and fetch signed-by-new documents on their next refresh.
6. After 24 hours (plus the clients' refresh interval) the retired key can be removed from `FORGE_POLICY_RETIRED_KEYS`. Keep its statement in
   `FORGE_POLICY_ROTATIONS` while a device may still pin only that key (a device that was offline during several rotations walks the whole chain).

Rotating does not change what is signed: epochs and the schema stay, only `kid` and `sig` differ.

**How a client follows a rotation.** The desktop client pins the keys it received in the installer configuration (a TLS download from its own
control plane) and learns a new key only from a statement signed by a key it has already pinned:

* it fetches `/forge/v1/capabilities/pinning` over TLS from the pinned control-plane origin and applies each statement whose `old_kid` is pinned
  and not retired: the signature must verify with that key, `new_kid` must be the first 16 hex characters of the SHA-256 of `new_public_key`
  (32 raw bytes), and `issued_at` must be a `YYYY-MM-DDTHH:MM:SSZ` time; it then pins the new key;
* the old key is retired at the statement's `issued_at` and signs nothing else; a policy document it signed is accepted only when its
  `issued_at` is earlier than that time;
* statements from keys it has not pinned, replays and forgeries change nothing, and a chain of several rotations may arrive in any order;
* the keys in the published set that no statement leads to are never trusted: a leaked database or a proxy cannot add a key.

The reference is `forge.capability_rotation` (`apply_rotations`, `key_usable`); test vectors are `contract/forge-policy-rotation.v1.json`.

## What the edge forwards

Caddy answers only these paths; everything else on the public host is a `404` and an unknown `Host` is a `421`:

| Path | Where it goes |
|------|---------------|
| `/admin`, `/admin/*`, `/status`, `/livez`, `/forge/*` | the control plane |
| `/onboarding`, `/join`, `/reset-password` (exactly these three) | the control plane, which redirects them (307, query kept, fragment untouched) into the admin SPA. These are the links Forge mails on the public origin: the member invitation (`/onboarding?c=<company code>#invitation_id=...&capability=...`, `/join` is its alias) and the platform owner's set-password link (`/reset-password#capability=...`). Without this forward the links 404 at the edge. |
| `/downloads/*` | Caddy itself, from the read-only `deploy/downloads/` volume (below) |

`tests/test_deploy_artifacts.py` pins the three link paths against the control plane's own redirect table, and `scripts/deploy-smoke.ps1`
requests each through the real proxy.

## Publish installers

Copy release files into `deploy/downloads/` on the server. Caddy serves that directory read-only at
`https://forge.example.test/downloads/<file>`. Directory listing is off, dotfiles are hidden, and
`/downloads/latest.json` (the version manifest the clients read) is sent with `Cache-Control: no-cache` so a new
release is seen immediately.

```bash
scp Forge-Setup-1.4.0.exe latest.json you@server:/opt/forge/deploy/downloads/
```

## Backup and restore

The `backup` service writes a verified dump on `FORGE_BACKUP_CRON` (default `30 2 * * *`, UTC) into
`deploy/backups/` and keeps the newest `FORGE_BACKUP_KEEP`. Each run produces one file, `forge-<UTC stamp>.dump` (the database, read through
the read-only `backup_reader` role). Dumps never contain `deploy/secrets/` or `.env`.

> **Warning: losing `delivery_key` and `gateway_key` makes every stored gateway key and every queued message unrecoverable.**
> The database dump alone cannot be read without them. They are not in the dumps, by design. Losing `platform_key`
> only makes the platform owner's authenticator unreadable: sign in with a recovery code and enrol TOTP again.

Keep an offline copy of `deploy/secrets/` separate from the dumps (encrypted USB, password manager vault or an offline
archive), refreshed whenever you regenerate a file, and test that you can read it. Anyone holding the keys and a dump
can read everything, so protect both.

| Task | Command |
|------|---------|
| Dump now | `docker compose exec backup /opt/forge/backup.sh run-once` |
| List dumps | `ls -lh backups/` |
| Check one is readable | `docker compose exec backup pg_restore --list /backups/forge-<stamp>.dump` |
| Restore into a fresh, migrated database | `docker compose --profile tools run --rm restore /backups/forge-<stamp>.dump` |

Restore procedure (new server, or after loss of the data volume). Only rows are restored: the schema is always the
one `migrate` builds, because the schema attestation would reject a restored copy of it.

1. Put `deploy/secrets/` back from the offline copy, check out the same release that took the dump, set `.env`, and
   start the stack on an empty database: `docker compose up -d --wait` (`migrate` builds the reviewed schema).
2. Stop writers: `docker compose stop control-plane caddy`.
3. Restore: `docker compose --profile tools run --rm restore /backups/forge-<stamp>.dump`.
4. Start everything: `docker compose up -d --wait`. `migrate` finds every migration recorded (a no-op) and the control
   plane starts once readiness attests.

`restore.sh` changes nothing and exits with a code when a precondition fails:

| Code | Meaning | What to do |
|------|---------|------------|
| `TARGET_NOT_EMPTY` (3) | Some Forge table already holds rows | Restore only into a new database: `docker compose down -v` deletes the data, so be sure first |
| `SCHEMA_VERSION_MISMATCH` (4) | The migrated schema is not the dump's version | Check out the release that took the dump and run `docker compose up -d --wait` again |
| `DUMP_INVALID` (2) | `pg_restore --list` cannot read the file | Use another dump |

Copy `backups/` to another machine regularly: a dump on the same disk does not survive the disk.

## Upgrade and roll back

```bash
cd /opt/forge && git pull
cd deploy
docker compose exec backup /opt/forge/backup.sh run-once      # a fresh dump first
docker tag forge-control-plane:local forge-control-plane:previous
docker compose up -d --build --wait                            # migrate runs first; a failure stops the rollout
```

Migrations only move forward, and applied files must never be edited (`MIGRATION_CHECKSUM_MISMATCH` otherwise).

After the migrations the same job seeds the capability catalog (114 entries on a fresh install) with an idempotent sync: it creates
only what is missing and never overwrites what a platform owner changed, so every deploy is safe to repeat (`--no-seed` skips it, a
failure is `SEED_FAILED`). Before any catalog exists the effective policy is a signed, empty one rather than a 503.

| Situation | Action |
|-----------|--------|
| Code problem, schema unchanged | `FORGE_IMAGE=forge-control-plane:previous docker compose up -d --wait` |
| A migration must be undone | Check out the previous release, `docker compose down -v` (deletes the data), `docker compose up -d --wait`, then restore the pre-upgrade dump ([restore procedure](#backup-and-restore)) |

## Logs

Every line is JSON with a request id, the route template and the status; no query string, identifier or secret.

```bash
docker compose logs -f control-plane     # API and admin
docker compose logs migrate              # last migration run
docker compose logs caddy                # TLS and access
docker compose logs backup               # schedule and results
```

Container logs rotate at 10 MB x 5 files per service.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `up` stops with `service "migrate" didn't complete successfully` | Migration or configuration failed | `docker compose logs migrate`; the JSON `code` names the cause |
| `CONFIG_INVALID:<NAME>` | A setting or secret is missing or malformed | Fix `<NAME>` in `.env` or `deploy/secrets/`; no value is ever printed |
| `MIGRATION_CHECKSUM_MISMATCH` | An applied migration file was edited | Restore the original file (`git checkout -- migrations/`) |
| `SCHEMA_ATTESTATION_FAILED` or `/status` returns 503 | Database schema differs from the reviewed one | Do not hand-edit the database; rebuild it with `migrate` and restore the latest dump |
| `ADMIN_BUILD_MISSING` | Image built without the admin web | `docker compose build --no-cache control-plane` |
| `bind: address already in use` | Another service uses 80/443 | Stop it, or change `FORGE_HTTP_PORT`/`FORGE_HTTPS_PORT` and set `FORGE_PORT_SUFFIX=:<port>` |
| Browser shows a certificate warning | `FORGE_TLS=internal` without the root installed, or issuance failed | Install the root ([Choose the TLS mode](#choose-the-tls-mode)); for `acme` read `docker compose logs caddy` |
| `421 Misdirected request` | Request used a name other than `FORGE_DOMAIN` | Use the configured name; an IP address is refused on purpose |
| Healthcheck unhealthy right after start | Control plane waiting for the database | Wait for `start_period` (30 s); then `docker compose logs control-plane` |
| `permission denied` writing `backups/` | `FORGE_UID`/`FORGE_GID` do not match the directory owner | Set them to `id -u` / `id -g` and recreate the service |

## Why one worker

The control plane runs exactly one process (`FORGE_WORKERS` other than 1 is refused at start-up). Its database
connections are sized for a single process (two per service role), and its readiness cache and rate-limit counters
live in memory; several workers would multiply the connection count and split that state. Scaling out is
unverified, so the supported way to handle more load today is a larger server.

## Checklist

- [ ] `docker compose ps` shows every long-running service healthy and `migrate` exited (0)
- [ ] `https://forge.example.test/status` answers `ready` from outside the server
- [ ] `deploy/secrets/` has an offline copy stored away from the server and the dumps
- [ ] One dump exists and `pg_restore --list` reads it
- [ ] Only ports 22, 80 and 443 are open on the firewall

## Next step

Local rehearsal on a workstation with Docker: `scripts/deploy-smoke.ps1` runs this same stack with
`deploy/compose.dev.yml` (internal CA, loopback ports, Mailpit as the mail relay), proves it - including an invitation email and its link - and removes everything it created.
