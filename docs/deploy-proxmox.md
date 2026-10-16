# Deploy Forge on a Proxmox VM with your own domain

This guide takes you from a bare Proxmox host to a working company: a Forge control plane at `https://forge.prometheonlab.com`, mail sent
through Resend, your OmniRoute gateway behind it, a first company, and the Windows client installed on another PC. It is the step-by-step
companion to the runbook [deploy.md](deploy.md), which stays the reference for every setting.

The host name is configurable: `forge.prometheonlab.com` is the example used throughout, so use any host name you control by changing
`FORGE_DOMAIN` (and the origin you give the Windows installer). OmniRoute already lives at `ia.prometheonlab.com`; Forge only calls it.

## Quick path

Everything below happens on the Ubuntu VM once Docker is installed ([steps 1 to 3](#1-prepare-the-vm)). Replace the values in `.env` with
your own, then:

```bash
git clone <repository-url> /opt/forge && cd /opt/forge/deploy
cp .env.example .env && nano .env                  # step 4: FORGE_DOMAIN, FORGE_TLS, FORGE_ACME_EMAIL, FORGE_SMTP_*, FORGE_GATEWAY_ORIGINS
printf 'FORGE_UID=%s\nFORGE_GID=%s\n' "$(id -u)" "$(id -g)" >> .env
mkdir -p backups credentials
../scripts/deploy-secrets.sh                       # creates deploy/secrets/ once, never overwrites
read -rs P && printf '%s' "$P" > secrets/smtp_password && unset P   # your Resend API key
docker compose up -d --build --wait
curl -fsS https://forge.prometheonlab.com/status   # {"status":"ready", ...}
docker compose --profile tools run --rm platform bootstrap-owner --email you@prometheonlab.com --name "Platform Owner" \
  --link-file /credentials/owner-link.txt --smtp
```

Then sign in at `https://forge.prometheonlab.com/admin/platform`, enrol the authenticator, add the OmniRoute key, create a company, publish
the installer and install it on a PC. Each of those is one numbered step below.

## Before you start

| You need | Why |
|----------|-----|
| A Proxmox VE host with free capacity: 2 vCPU, 4 GB RAM, 40 GB disk | The stack is PostgreSQL, the control plane, Caddy and a backup job |
| Control of the `prometheonlab.com` DNS zone | One `A` record for the Forge host, plus the mail records for Resend |
| A way to reach the VM from the internet on `80/tcp` and `443/tcp` (and `443/udp`) | Let's Encrypt validates over port 80 and members connect over 443 |
| A Resend account with the domain verified (step 5) | Invitations and password resets are email; the control plane refuses to start without a relay |
| OmniRoute reachable over HTTPS from the VM, and its API key | The model gateway Forge meters |
| A Windows PC (build and test machine) | The installer is Windows only, built from the client repository |

Decide two things now: the Forge host name (`forge.prometheonlab.com`) and the sender address (`forge@prometheonlab.com`). Both are only
names you type into `.env`; nothing in the repository contains them.

## 1. Prepare the VM

1. In Proxmox create a VM from the Ubuntu Server 24.04 (or 22.04) ISO: **System** tick *Qemu Agent*; **Disks** 40 GB on VirtIO SCSI with
   *Discard*; **CPU** 2 cores, type `host`; **Memory** 4096 MB with ballooning off; **Network** a VirtIO NIC on the bridged `vmbr0`.
2. Install Ubuntu with OpenSSH. Give the VM a fixed address: a DHCP reservation on your router, or a static `netplan` entry. The
   port forwards in step 2 point at this address, so it must not change.
3. Update and enable the guest agent so Proxmox can shut the VM down cleanly and take consistent snapshots:

```bash
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y qemu-guest-agent git
sudo systemctl enable --now qemu-guest-agent
timedatectl                                        # "System clock synchronized: yes" is required (certificates depend on it)
```

4. Take a Proxmox **snapshot** before you install anything (`qm snapshot <vmid> clean-ubuntu` on the Proxmox host, or *Snapshots* in the
   web UI). If a step goes wrong you return to a clean server in seconds.

## 2. DNS and ports

1. Create an `A` record `forge` in the `prometheonlab.com` zone pointing at the public address of the network the VM sits behind (add an
   `AAAA` record only if the VM has public IPv6). `ia` already exists for OmniRoute.
2. Forward the ports from your router or firewall to the VM's fixed address:

| Port | Use | Needed when |
|------|-----|-------------|
| 80/tcp | Let's Encrypt validation and the redirect to HTTPS | `FORGE_TLS=acme` |
| 443/tcp and 443/udp | HTTPS (HTTP/3 uses udp) | always |
| 22/tcp | Administration | restrict to your admin addresses; never forward it to the internet |

3. Check from outside the network (a phone on mobile data is enough) that the name resolves to your public address:
   `dig +short forge.prometheonlab.com`.
4. Open the same ports on the VM:

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443 && sudo ufw enable
```

Docker publishes ports through its own iptables rules, so `ufw` does not hide what Docker publishes. That is fine here: only Caddy
publishes ports; PostgreSQL and the control plane have none.

> **Behind CGNAT or a provider that blocks port 80?** Let's Encrypt cannot reach you. Use `FORGE_TLS=internal` (Caddy's own certificate
> authority, see [deploy.md](deploy.md#choose-the-tls-mode)) while you sort it out, or terminate on a small public server. Do not fight
> it by repeating `acme` attempts: Let's Encrypt rate-limits failures.

> **Members inside your LAN can't open the name?** Some routers do not loop a public address back inside. Add a DNS override for
> `forge.prometheonlab.com` pointing at the VM's LAN address on your internal resolver.

## 3. Install Docker

Install Docker Engine and the Compose plugin from Docker's official apt repository:

```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER" && newgrp docker
docker compose version                             # 2.24 or newer
```

## 4. Configure Forge

```bash
sudo git clone <repository-url> /opt/forge && sudo chown -R "$USER": /opt/forge
cd /opt/forge/deploy
cp .env.example .env && nano .env
```

Set these values (everything else in `.env` can keep its default):

| Setting | Value for this guide | Notes |
|---------|----------------------|-------|
| `FORGE_DOMAIN=forge.prometheonlab.com` | Your Forge host | Must resolve to the VM's public address before `acme` can issue |
| `FORGE_TLS=acme` | Public certificate from Let's Encrypt | `FORGE_TLS=internal` is the fallback for a private network |
| `FORGE_ACME_EMAIL=you@prometheonlab.com` | Expiry notices | A real mailbox |
| `FORGE_GATEWAY_ORIGINS=https://ia.prometheonlab.com` | OmniRoute | The only origin a gateway key may be created for. A publicly trusted OmniRoute certificate needs nothing more. For a private CA, copy its PEM certificate to `deploy/gateway-ca/ca.pem`, add `FORGE_GATEWAY_CA_FILE=/run/gateway-ca/ca.pem` to `.env` and run `docker compose up -d control-plane` |
| `FORGE_SMTP_HOST`, `FORGE_SMTP_PORT`, `FORGE_SMTP_SECURITY`, `FORGE_SMTP_USER`, `FORGE_SMTP_FROM`, `FORGE_SMTP_PASSWORD_FILE` | See step 5 | Required |
| `FORGE_UID`, `FORGE_GID` | Your user | Appended below so `backups/` and `credentials/` stay yours |

```bash
printf 'FORGE_UID=%s\nFORGE_GID=%s\n' "$(id -u)" "$(id -g)" >> .env
mkdir -p backups credentials
../scripts/deploy-secrets.sh
```

`deploy-secrets.sh` creates `deploy/secrets/` with a strong random value for every credential (database roles, the three Fernet keys,
the policy signing key). It never overwrites an existing file and prints names only.

> **Back up `deploy/secrets/` offline now**, to an encrypted USB stick or a password-manager vault, *not* only on the VM. Losing
> `delivery_key` and `gateway_key` makes every stored gateway key and queued message unrecoverable; a database dump cannot be read
> without them.

## 5. Mail through Resend

Forge sends invitations and password resets over SMTP. Resend works with the standard settings:

1. In Resend, add the domain `prometheonlab.com` (or a subdomain such as `mail.prometheonlab.com`) and publish the **SPF** and **DKIM**
   DNS records it shows. Wait until the dashboard says *Verified*; an unverified sender domain is refused (`SMTP_SENDER`).
2. Create an API key with sending access only. Treat it as a password: it goes into `secrets/smtp_password` and nowhere else.
3. Edit `.env`:

```bash
FORGE_SMTP_HOST=smtp.resend.com
FORGE_SMTP_PORT=587
FORGE_SMTP_SECURITY=starttls
FORGE_SMTP_USER=resend
FORGE_SMTP_FROM=forge@prometheonlab.com
FORGE_SMTP_PASSWORD_FILE=/run/secrets/smtp_password
```

4. Store the key without leaving it in your shell history, and keep the file readable by the containers:

```bash
read -rs P && printf '%s' "$P" > secrets/smtp_password && unset P
chmod 644 secrets/smtp_password
```

Port 465 with `FORGE_SMTP_SECURITY=tls` also works; `starttls` on 587 is the default. **Amazon SES later:** only the values change
(`FORGE_SMTP_HOST=email-smtp.<region>.amazonaws.com`, the SES SMTP user name and the SES SMTP password in `secrets/smtp_password`);
nothing else in this guide does. Send a test message and read the failure categories in [deploy.md](deploy.md#email-delivery-smtp)
once the stack is up.

## 6. Start the stack

```bash
cd /opt/forge/deploy
docker compose up -d --build --wait                # postgres -> migrate -> control-plane -> caddy
docker compose ps                                  # postgres, control-plane, caddy, backup healthy; migrate exited (0)
curl -fsS https://forge.prometheonlab.com/status   # {"status":"ready", ...}
```

Open `https://forge.prometheonlab.com/` in a browser: it shows the public landing page (the brand, a **Sign in** button that leads to
`/admin`, and the Windows download). It is part of the admin web, so the same build serves it and no extra setting exists. The first build downloads images and compiles the admin web, so allow several minutes. The first start asks Let's Encrypt for a
certificate; if `/status` fails, read `docker compose logs caddy` before changing anything (the table in [Troubleshooting](#troubleshooting)
has the usual causes). The migration job also seeds the capability catalog on a fresh install, so a new server is usable straight away.

## 7. First platform owner

The platform owner is an account that belongs to no company; it creates companies and manages the gateway. It is created on the server,
never over HTTP, and the command prints no password:

```bash
docker compose --profile tools run --rm platform bootstrap-owner \
  --email you@prometheonlab.com --name "Platform Owner" --link-file /credentials/owner-link.txt --smtp
```

Expected: `{"status": "created", "link_file": "/credentials/owner-link.txt", "delivery": "delivered"}`.

1. Open the mailed link (or the one in `deploy/credentials/owner-link.txt`, which is created owner-only and never overwritten). It works once and
   expires after 24 hours. Choose a password of at least 15 characters, then delete the file.
2. Go to `https://forge.prometheonlab.com/admin/platform` and sign in. The second factor is mandatory: scan the QR code with an
   authenticator app (the TOTP secret), confirm with a code, and save the **ten recovery codes** shown once. Store them offline.
3. Later sign-ins ask for a 6-digit code or one recovery code (each works once). Thirty idle minutes sign you out.

If the link was lost, use *Forgot password?* on the sign-in page ([Reset a password](#reset-a-password)). Running the command again does nothing
(`"status": "exists"`).

## 8. Connect OmniRoute

The OmniRoute API key is entered only in the platform console. It is sealed in the database, shown as its last four characters from then on, and never
returned.

1. In the console open **Keys** (`/platform/keys`) and add a key: a label such as `omniroute`, the origin `https://ia.prometheonlab.com`
   (it must match `FORGE_GATEWAY_ORIGINS` exactly, with no path), and the real OmniRoute key.
2. Open **Prices** (`/platform/prices`) and set the price per million input and output tokens for each model you will allow. A model
   without a price is counted as *unpriced*, never as free.
3. The key becomes usable for a company when you assign it in the next step. Rotate or disable it later from the same page; in-flight
   chats finish on the old value.

If saving the key fails with an origin error, the origin is not in `FORGE_GATEWAY_ORIGINS`: fix `.env` and run
`docker compose up -d control-plane`. From the VM, `curl -sI https://ia.prometheonlab.com` should complete a TLS handshake.

## 9. Create the first company

In the console choose **Companies, New** (`/platform/companies/new`). The wizard walks through: the company (its **code** is the short
name employees will see, for example `acme`), optional branding, the first administrator (name and email), the gateway key and the models the
company may use, then a review. A failed step is named and retried on its own.

Expected: the administrator receives an invitation email whose link opens the join page for that company; the company page shows a
checklist that turns green as keys and models are assigned. If delivery says `failed`, the company exists: fix the mail relay and use the
check in [deploy.md](deploy.md#email-delivery-smtp). The administrator signs in at `https://forge.prometheonlab.com/admin/`, invites the
people, and each person lands on a download page.

**Choose the models a company can use.** After the company has one or more gateway keys assigned (its **Keys** tab), open its **Models**
tab as platform owner:

1. **Discover models** asks every active key of the company, through OmniRoute's `/v1/models`, what it can reach. Each key shows its own state
   (*Reachable*, *Not reachable*, *No key stored*, *Disabled* or *Assigned but off*) and when the last discovery succeeded; one broken key
   does not hide the models of the others.
2. Search the list, tick the models or combos the company may use, give each an **alias** (the name members see), and pick the **default**.
3. **Publish catalog**. The published models become exactly the company's allowed models. Company administrators keep their own **Catalog** page,
   but they can only publish models inside that allowed set (they can narrow your catalog, never widen it). Publishing needs one person in the company who has already
   joined (the event is recorded against an administrator of the company); every discover and publish is in the platform **Audit log**.

## 10. Publish the installer

The Windows installer is built once, from the client repository on a Windows machine, **for your control plane's origin**. The origin and the
policy public keys are compiled in, so the person who installs it needs nothing but the one file. Build it with your host name and let the
build read the keys from the running server (a TLS request to `GET /forge/v1/capabilities/pinning`, so run it from your own machine once the
stack is up):

```powershell
cd clients\openyak       # the client repository; see its docs/desktop-installer.md
npm run build:desktop -- --origins https://forge.prometheonlab.com --policy-keys-from-origin
```

The build refuses to start without keys (`--policy-keys <file>` takes a saved pinning document instead; `--allow-unpinned-dev` is for development
only). The result is `Prometheon Forge_<version>_x64-setup.exe` and `SHA256SUMS.md`. The installer is unsigned, so Windows SmartScreen will
warn on first run ("More info", then "Run anyway").

Copy it to the downloads volume and describe it in `latest.json`, which the download pages read and which the server checks before it streams the
company download (the URL must be on the same origin, a plain `*.exe` name without spaces, and the hash and size must be the real ones). Rename the
file first: the build's name has a space.

```bash
scp "Prometheon Forge_1.5.0_x64-setup.exe" you@forge-vm:/opt/forge/deploy/downloads/Prometheon-Forge_1.5.0_x64-setup.exe
ssh you@forge-vm
cd /opt/forge/deploy/downloads
F=Prometheon-Forge_1.5.0_x64-setup.exe
printf '{"version":"1.5.0","released_at":"%s","platforms":{"windows":{"url":"/downloads/%s","sha256":"%s","size_bytes":%s}}}\n' \
  "$(date -u +%FT%TZ)" "$F" "$(sha256sum "$F" | cut -d' ' -f1)" "$(stat -c %s "$F")" > latest.json
curl -fsS https://forge.prometheonlab.com/downloads/latest.json
```
Caddy serves `deploy/downloads/` read-only and the control plane mounts the same directory read-only (`FORGE_INSTALLER_DIR`); no restart is needed and `latest.json` is never cached, so a new release shows up at once.

**The company download.** A signed-in member or company administrator who presses **Download Prometheon Forge** gets the published installer, byte for
byte (its SHA-256 matches `latest.json`), named `Prometheon-Forge-Setup-<company code>.exe` by `GET /forge/v1/downloads/company` (a member session,
never public). The installer reads the company code from that file name (a browser's ` (1)` suffix is fine), so nothing else has to be handed over.
The landing page, where no company is known, keeps offering the plain installer. If the file does not match `latest.json` (a half-copied upload)
the route answers 503 instead of streaming it.

**What `latest.json` says.** It is the only thing the web reads to decide what to offer; the installer file itself is never inspected.

| Field | Meaning | Rule |
|-------|---------|------|
| `"version"` | The version people see (`v1.5.0`) | Any non-empty text |
| `"released_at"` | When it was published | An ISO 8601 UTC time, shown as a date |
| `"platforms"` then `"windows"` | The installer for Windows, the only platform for now | Without it nobody is offered a download |
| `"url"` | Where the file is | Must be `/downloads/<file name>` on this origin: a manifest can never send people to another site |
| `"sha256"` | The file's SHA-256 in lowercase hex | Shown next to the button so people can verify the file; `sha256sum` prints it |
| `"size_bytes"` | The file size in bytes | Shown as MB |

It appears in three places, all reading `/downloads/latest.json` (the landing links the plain file; the two signed-in pages use the company download): the **Download for Windows** section of the public landing page at `/`,
the **Download Prometheon Forge** page every signed-in person finds in the navigation (company administrators at `/admin/company/download`,
members at `/admin/portal/download`), and the card on each dashboard. While no `latest.json` exists (or it is not valid) all three say that the
installer is not published yet, and nothing else breaks. To publish a new version, copy the new file, rewrite `latest.json` with the commands
above, and leave the old file in place for people who are mid-download.

## 11. Install the client on another PC

Each person does this from the download page after accepting their invitation; an administrator can do the same silently.

1. Open the invitation link, choose a password, and the **Download Prometheon Forge** page opens at `https://forge.prometheonlab.com/admin/portal/download` (administrators find the same page
   in their navigation at `/admin/company/download`).
2. Press the one big **Download Prometheon Forge** button. The file is named for the company (`Prometheon-Forge-Setup-<code>.exe`); keep that name.
3. Run it. Nothing else is needed: the control plane origin and the policy public keys are compiled into the installer, and it binds to the
   company from its own file name. For a scripted install an explicit `/CODE=<code>` or `/CONFIG=` still wins over the file name:

```powershell
.\Prometheon-Forge-Setup-acme.exe /S
```

4. Start *Prometheon Forge* and sign in with the account from the invitation. (The page's **Open Forge** button, `prometheon-forge://join?cp=...&code=...`,
   only proposes the company to an installed app and asks for confirmation.) After sign-in the organization comes from the account; a member of
   several organizations gets the picker. Models appear and a chat answers through OmniRoute.

*Advanced.* Under **Advanced** on the same page, **Download configuration (forge-install.json)** saves the optional company configuration (company
code, control plane origin and the public policy keys). It is only needed for a managed install that must pin different keys; `/CONFIG="C:\path\forge-install.json"`
hands it to the installer, which finds a `forge-install.json` next to itself too. It holds no secret.
The client repository's `docs/policy-key-pinning.md` has the rules and limits; its `docs/desktop-installer.md` covers building.

## Reset a password

Every account (a member, a company administrator or the platform owner) resets its own password by mail. Nobody, including the platform owner,
can read or set anyone else's password.

1. On the sign-in page choose **Forgot password?** (`https://forge.prometheonlab.com/admin/forgot-password`), type the account's email and
   send. The page always answers with the same message, whether the address has an account or not, so it cannot be used to find out who
   has one.
2. The mail from step 5 carries a link to `/reset-password`. It is single-use and valid for **30 minutes**; asking again replaces the previous
   link, and a new request is accepted once a minute. The link opens the set-password page, where the new password needs at least 15 characters.
3. Setting the password signs the account out everywhere. A sign-in with a password shorter than 15 characters, or a wrong one, says
   *Email or password is incorrect.* and never reveals the length rule.

The browser calls `POST /forge/v1/accounts/password-reset/request` with the email only; the reply is the same `202` for every address.

**The platform owner** uses exactly the same page. The authenticator is not touched by a password reset: after the new password the console still
asks for a 6-digit code, or one of the ten recovery codes from step 7 if the phone is gone. There is no command that re-issues an owner link
(`bootstrap-owner` does nothing once an owner exists), so the mail relay must work: if a reset message does not arrive, run the SMTP check in
[deploy.md](deploy.md#email-delivery-smtp) before anything else.

## Backups and restore

The `backup` service writes a verified PostgreSQL dump every night (02:30 UTC) into `deploy/backups/` and keeps the newest 14.

| Task | Command |
|------|---------|
| Dump now | `docker compose exec backup /opt/forge/backup.sh run-once` |
| Check one is readable | `docker compose exec backup pg_restore --list /backups/forge-<stamp>.dump` |
| Restore into a fresh, migrated database | `docker compose --profile tools run --rm restore /backups/forge-<stamp>.dump` |

Two layers, because they protect different things:

1. **VM level.** In Proxmox schedule a backup job (*Datacenter, Backup*) or run `vzdump <vmid> --mode snapshot --compress zstd --storage <storage>`.
   It saves the whole server, but a running database is only crash-consistent, so it is the safety net, not the data copy.
2. **Application level.** Copy `deploy/backups/` to another machine regularly (`rsync -a /opt/forge/deploy/backups/ backup-host:/srv/forge-backups/`),
   and keep the **offline copy** of `deploy/secrets/` from step 4 refreshed. A dump on the same disk does not survive the disk.

To restore on a new VM: repeat steps 1 to 4, put `deploy/secrets/` back from the offline copy, run `FORGE_MIGRATE_SEED=0 docker compose up -d --wait`
(the dump carries the catalog, so the empty tables must stay empty), `docker compose stop control-plane caddy`, run the `restore` command above,
then `docker compose up -d --wait`. [deploy.md](deploy.md#backup-and-restore) lists the exit codes `restore` can answer and what each means.

## Update the server

Do this on the VM each time you want a newer Forge. Nothing is lost: the data lives in the `pgdata` volume, the secrets in `deploy/secrets/`.

```bash
cd /opt/forge && git pull                                      # 1. the new code and migrations
cd deploy
docker compose exec backup /opt/forge/backup.sh run-once       # 2. a fresh dump first
docker tag forge-control-plane:local forge-control-plane:previous   # keeps the running image for a code rollback
docker compose build                                           # 3. builds the control plane (and the admin web with the landing)
docker compose up -d --wait                                    # 4. migrate runs first; a failure stops the rollout
docker compose logs migrate                                    # 5. the migration result: the JSON lines name what was applied
curl -fsS https://forge.prometheonlab.com/status               # {"status":"ready", ...}
```

`migrate` is a one-shot service that `up` runs before the control plane starts: it applies every new file in `migrations/` once, in order,
then exits (0). Run it by itself with `docker compose run --rm migrate` if you want to see it work before the rollout. Migrations only move
forward, and an applied file must never be edited (`MIGRATION_CHECKSUM_MISMATCH` otherwise). A release that adds a migration changes the
schema the server attests, so the old control plane image stops being ready against the migrated database: roll back with a snapshot or the dump
from step 2, not with the old image.

Take a Proxmox snapshot before a major upgrade. A code-only problem (no new migration) is rolled back with
`FORGE_IMAGE=forge-control-plane:previous docker compose up -d --wait`; a migration cannot be undone, so you return to the snapshot or restore
the pre-upgrade dump (see [deploy.md](deploy.md#upgrade-and-roll-back)). Publish a new installer by repeating step 10 with the new version.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `curl` to `/status` fails or the browser warns about the certificate | DNS does not point at the VM yet, port 80 is not reachable, or issuance is rate limited | `dig +short forge.prometheonlab.com`; test port 80 from outside; read `docker compose logs caddy`; use `FORGE_TLS=internal` meanwhile |
| `421 Misdirected request` | The request used a name other than `FORGE_DOMAIN` (an IP address counts) | Use the configured name |
| `up` stops with `service "migrate" didn't complete successfully` | A setting or secret is missing | `docker compose logs migrate`; the JSON `code` names it, for example `CONFIG_INVALID:FORGE_SMTP_HOST` |
| Owner or invitation `delivery: failed` | Resend refused the message | Run the check in [deploy.md](deploy.md#email-delivery-smtp): `SMTP_AUTH` means a wrong key or a user other than `resend`; `SMTP_SENDER` means the domain is not verified |
| The OmniRoute key is refused | The origin is not in `FORGE_GATEWAY_ORIGINS`, or it has a path or a different scheme | Use exactly `https://ia.prometheonlab.com`, then `docker compose up -d control-plane` |
| Chats say models are unavailable | No key assigned to the company, no model access, or OmniRoute unreachable from the VM | Check the company's Keys and Models tabs; `curl -sI https://ia.prometheonlab.com` from the VM |
| The installer shows a company or origin error | It was built for another origin, or `forge-install.json` belongs to a different company | Rebuild with `--origins` set to your origin (step 10); download the installer again |
| Certificates fail after a power cut | The VM clock is wrong | `timedatectl`, then restart `chrony` or `systemd-timesyncd` |
| Docker does not start | The service failed | `journalctl -u docker --since "10 minutes ago"` |
| `permission denied` writing `backups/` | `FORGE_UID` and `FORGE_GID` do not match the directory owner | Set them to `id -u` and `id -g` and recreate the service |

Logs: `docker compose logs -f control-plane` for the API and admin, `docker compose logs migrate` for the last migration run. Every line is
JSON with a request id and route, never an identifier or a secret.

## Checklist

- [ ] The VM has a fixed address, the guest agent runs and a clean-install snapshot exists
- [ ] `dig +short forge.prometheonlab.com` returns your public address and ports 80 and 443 reach the VM from outside
- [ ] `docker compose ps` shows every service healthy and `migrate` exited (0)
- [ ] `https://forge.prometheonlab.com/status` answers `ready` with a trusted certificate
- [ ] An offline copy of `deploy/secrets/` exists away from the VM and the dumps
- [ ] The test message and the owner link arrived through Resend
- [ ] The platform owner has the authenticator enrolled and the ten recovery codes stored offline
- [ ] The OmniRoute key is added, models are priced and the first company has the key and its models assigned
- [ ] `latest.json` and the installer open from `https://forge.prometheonlab.com/downloads/`
- [ ] `https://forge.prometheonlab.com/` shows the landing page and its Sign in button opens `/admin`
- [ ] The company's Models tab discovered models through OmniRoute and a catalog is published
- [ ] *Forgot password?* sends a reset mail that arrives and works
- [ ] A second PC installed from the company download (`Prometheon-Forge-Setup-<code>.exe`), signed in and received a chat answer
- [ ] A dump exists, `pg_restore --list` reads it, and `deploy/backups/` is copied off the VM
