# Design: Docker Compose Deployment

## Technical Approach
Everything lives under `deploy/` plus a root `Dockerfile`. Compose wires the `fv2-prod-runtime` CLI (`python -m forge.serve_prod migrate|serve|healthcheck`). Dev proof reuses the same files via `compose.dev.yml`, changing only: fake gateway service, `FORGE_TLS=internal`, host ports 8080/8443. The admin SPA (`admin/` Vite, `base:/admin/`, output `src/forge/web/admin`, gitignored) is built inside the image.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Proxy | Caddy | nginx+certbot, Traefik | Automatic ACME + internal CA with one env switch; tiny config |
| TLS switch | `tls {$FORGE_TLS_ARG}` (`internal` or ACME email) | two Caddyfiles | Single file, env-only mode |
| Secrets | Docker secrets → `*_FILE` | `.env` values | Not in `inspect`/`config`; matches prod_config |
| DB access | Network only; postgres unpublished | Publish 5432 | Attack surface |
| Migrate | Separate one-shot service holding superuser secret | Run in app start | App never has DDL credentials |
| Root FS | `read_only`, tmpfs `/tmp`, `cap_drop ALL`, `no-new-privileges` | default | Defense in depth |
| Provisioning | `tools` profile service with `network_mode: service:postgres` | relax loopback-only operator CLI | Keeps trusted CLI invariant; temporary until platform-core |
| Healthcheck | `serve_prod healthcheck` (sends configured Host) | curl in image | No extra binary; host guard unchanged |
| Backup | sidecar `postgres` image loop + `pg_dump -Fc` | pgBackRest | Single-host MVP; simple and testable |
| Worker | 1 worker | gunicorn N | See prod-runtime: per-process pools/caches sized for one |

## Data Flow
    Internet ─80/443─► caddy ─(compose net)─► control-plane:3410 ─► postgres:5432
                         │ /downloads/* ◄── ./downloads (ro)       ▲
    backup ──pg_dump────────────────────────────────────────────────┘
    migrate (one-shot, superuser secret) ─► postgres

## File Changes

| File | Action | Description |
|---|---|---|
| `Dockerfile`, `.dockerignore` | Create | Multi-stage, non-root |
| `deploy/compose.yml`, `compose.dev.yml` | Create | Stack + dev overlay |
| `deploy/Caddyfile` | Create | TLS/proxy/downloads |
| `deploy/.env.example` | Create | Placeholders only (`FORGE_DOMAIN=forge.example.test`) |
| `deploy/backup/{backup,restore}.sh` | Create | Dump/prune/restore |
| `scripts/deploy-secrets.sh`/`.ps1` | Create | Generate role passwords + Fernet keys (never overwrite) |
| `scripts/deploy-smoke.ps1` | Create | Up→assert→down |
| `docs/deploy.md` | Create | Runbook |
| `tests/test_deploy_artifacts.py`, `test_deploy_smoke.py` | Create | Static + opt-in `FORGE_DOCKER_SMOKE=1` |
| `.gitignore` | Modify | secrets/downloads |

## Interfaces / Contracts
Env: `FORGE_DOMAIN`, `FORGE_PORT_SUFFIX` (`:8443` local, empty prod), `FORGE_TLS` (`acme|internal`), `FORGE_ACME_EMAIL`, `FORGE_GATEWAY_ORIGINS`, `FORGE_BACKUP_CRON`, `FORGE_BACKUP_KEEP`, `POSTGRES_IMAGE`. Secrets: `pg_superuser`, `role_*` (5), `delivery_key`, `gateway_key`.
Smoke assertions: `/status` ready via Caddy; `forge.schema_migrations` count = migration count; `/admin/` 200; `/forge/v1/accounts/me` 401; wrong Host refused; no leaked secret in `docker compose config`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit/static | digests, USER, read_only, no published pg port, no concrete domain, secrets ignored | text assertions in unittest (no YAML dep) |
| Integration | `docker compose config`, image build, non-root `id` | opt-in Docker test |
| E2E | full stack up/health/migrations/Caddy TLS verify with extracted root/backup/teardown | `scripts/deploy-smoke.ps1`, Docker 28 local |

## Migration / Rollout
Server: copy repo, generate secrets, set `.env`, `compose up -d`, create first org via runbook. Rollback documented. No data migration.

## Open Questions
- [ ] Final domain spelling and public 80/443 reachability (decides `acme` vs `internal`).
- [ ] Windows `.ps1` and Linux `.sh` parity—both required, or Linux-only on server?
