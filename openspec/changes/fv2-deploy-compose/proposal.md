# Proposal: Docker Compose Deployment with Caddy TLS

## Intent

There is no Dockerfile, compose file, reverse proxy, backup or runbook (`git ls-files` clean). The target is an Ubuntu server (user's Proxmox VM) running Docker Compose. The public domain is unconfirmed (`prometeonlab.com` typed vs `prometheonlab.com` in OmniRoute `ia.prometheonlab.com`) and public DNS/80/443 reachability is unknown, so the domain and TLS mode MUST be pure configuration.

## Scope

### In Scope
- `Dockerfile` (multi-stage: pinned Node builds the admin SPA, pinned Python builds the wheel; final non-root, read-only rootfs, tmpfs `/tmp`).
- `deploy/compose.yml`: `postgres` (digest from `scripts/postgres-image.txt`), one-shot `migrate`, `control-plane` (healthcheck, single worker), `caddy`, `backup`; internal network, only Caddy publishes ports.
- `deploy/Caddyfile`: `FORGE_DOMAIN`, `FORGE_TLS` = ACME (Let's Encrypt) or `internal` (Caddy local CA), reverse proxy, security headers, `/downloads/*` installer hosting with `latest.json`.
- Secrets via Docker secrets/env files (`deploy/secrets/`, gitignored) + generator script; `deploy/.env.example`.
- `deploy/compose.dev.yml` overlay: fake gateway, `tls internal`, alternate host ports for local proof.
- Backup service (`pg_dump` custom format + retention) + restore script; Fernet-key backup runbook.
- `docs/deploy.md` runbook (DNS, firewall, LE vs internal, first org via tools profile, upgrade, rollback, single-worker rationale).
- Local Docker acceptance smoke script + opt-in test.

### Out of Scope
- Real DNS/TLS/OmniRoute verification (user only); SMTP (fv2-smtp-delivery); first-admin bootstrap UX (fv2-platform-core); installer build (fv2-release); multi-host/HA.

## Capabilities

### New Capabilities
- `compose-deployment`: images, services, health ordering, secrets, network exposure.
- `edge-tls-proxy`: Caddy TLS modes, headers, downloads hosting, domain configurability.
- `backup-restore`: scheduled dump, retention, restore, key-backup procedure.

### Modified Capabilities
None.

## Approach

Compose services consume `fv2-prod-runtime` (`serve_prod migrate|serve|healthcheck`). Ordering: postgres healthy → migrate completed → control-plane healthy → caddy. Public origin = `https://${FORGE_DOMAIN}${FORGE_PORT_SUFFIX}`, passed once as `FORGE_PUBLIC_ORIGIN`. Local proof runs the real stack with `FORGE_DOMAIN=localhost`, internal CA, host ports 8080/8443, verified against the extracted Caddy root cert. A `tools` profile `provision` service shares postgres' network namespace to reuse the loopback-only operator CLI until platform-core.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `Dockerfile`, `.dockerignore` | New | Image |
| `deploy/compose.yml`, `compose.dev.yml`, `Caddyfile`, `.env.example`, `backup/*` | New | Stack |
| `scripts/deploy-secrets.{sh,ps1}`, `scripts/deploy-smoke.ps1` | New | Ops/proof |
| `docs/deploy.md` | New | Runbook |
| `.gitignore` | Modified | `deploy/secrets/`, `deploy/downloads/*` |
| `tests/test_deploy_artifacts.py` | New | Static policy tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Let's Encrypt impossible without public 80/443 | Med | `FORGE_TLS=internal` fallback documented |
| Losing Fernet keys makes stored gateway keys unrecoverable | Med | Runbook + backup script bundles key export separately from DB dump |
| Image digests drift/unavailable | Low | Pin at apply time from official registries; static test enforces digests |
| Host guard rejects proxied Host with port | Med | Origin includes port suffix; covered by smoke |
| Windows host for local proof | Low | PowerShell smoke; Linux `.sh` twin |

## Rollback Plan

All artifacts are additive files. Server rollback: `docker compose down` (volumes kept), redeploy the previous image tag, restore `pg_dump` if a migration must be reverted (forward-only migrations, never edit applied files).

## Dependencies
- fv2-prod-runtime merged (CLI + health). Docker 28 local; official registries for images.

## Success Criteria
- [ ] `compose up` locally: all services healthy, `schema_migrations` populated, `/status` ready through Caddy.
- [ ] `https://localhost:8443/admin/` serves the SPA with trusted internal CA; `/forge/v1/*` default-deny intact.
- [ ] No secret in repo/image layers/`compose config` output; teardown leaves no containers/volumes.
- [ ] One backup + `pg_restore --list` verified.
