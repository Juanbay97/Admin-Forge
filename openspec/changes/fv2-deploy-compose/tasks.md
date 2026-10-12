# Tasks: Docker Compose Deployment

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2,300 (4 slices, 400–650 each) |
| 400-line budget risk | High (800-line/slice budget: Medium) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 → S4 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | Dockerfile + secrets generator (~450) | PR 1 | base: fv2-prod-runtime tip |
| S2 | compose.yml + Caddyfile + env + policy tests (~600) | PR 2 | base PR1 |
| S3 | compose.dev + local smoke proof + provision tool (~650) | PR 3 | base PR2; Docker proof |
| S4 | backup/restore + runbook (~600) | PR 4 | base PR3 |

## Phase 1: Image (S1)
- [ ] 1.1 RED `tests/test_deploy_artifacts.py`: Dockerfile has pinned digests, non-root `USER`, no secret ARG/ENV.
- [ ] 1.2 GREEN `Dockerfile` (node stage builds `admin/`; python stage `pip wheel`; final copies wheel+SPA), `.dockerignore`.
- [ ] 1.3 `scripts/deploy-secrets.sh|.ps1` (idempotent, never overwrite, 0600) + `.gitignore`; test: second run changes nothing.
- [ ] 1.4 Verify: `docker build`, `docker run --rm img id -u` ≠ 0, `serve_prod --help`.

## Phase 2: Stack (S2)
- [ ] 2.1 RED static tests: only caddy publishes, `read_only`, `cap_drop`, digests, depends_on conditions, no concrete domain outside `.env.example`.
- [ ] 2.2 GREEN `deploy/compose.yml` (postgres, migrate, control-plane, caddy) + `deploy/.env.example`.
- [ ] 2.3 GREEN `deploy/Caddyfile` (TLS env switch, proxy, headers, `/downloads`, no listing, `latest.json` no-cache).
- [ ] 2.4 Verify `docker compose config` exits 0 and contains no secret values.

## Phase 3: Local proof (S3)
- [ ] 3.1 `deploy/compose.dev.yml` (fake gateway, `internal`, ports 8080/8443, `tools` provision service).
- [ ] 3.2 RED `tests/test_deploy_smoke.py` (opt-in): up --wait, `/status` ready via Caddy with extracted root cert, migrations count, `/admin/` 200, `/forge/v1/accounts/me` 401, wrong Host refused, tampered-migration blocks control-plane.
- [ ] 3.3 GREEN `scripts/deploy-smoke.ps1` incl. `down -v` and absent-containers assertion.
- [ ] 3.4 Run it on this machine; record exact output in the PR.

## Phase 4: Backup + docs (S4)
- [ ] 4.1 RED backup tests in smoke: run-once dump, `pg_restore --list`, retention KEEP=2, restore refuses non-empty DB.
- [ ] 4.2 GREEN `deploy/backup/backup.sh`, `restore.sh`, compose `backup` service.
- [ ] 4.3 `docs/deploy.md`: DNS/firewall, LE vs internal, first org, upgrade/rollback, Fernet-key loss + offline secrets backup, single-worker why, installer upload; doc test for key-loss warning.
- [ ] 4.4 Final: full unittest + smoke + `compileall`.
