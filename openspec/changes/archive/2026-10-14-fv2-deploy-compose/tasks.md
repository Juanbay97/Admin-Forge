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
- [x] 1.1 RED `tests/test_deploy_artifacts.py`: Dockerfile has pinned digests, non-root `USER`, no secret ARG/ENV.
- [x] 1.2 GREEN `Dockerfile` (node stage builds `admin/`; python stage `pip wheel`; final copies wheel+SPA), `.dockerignore`.
- [x] 1.3 `scripts/deploy-secrets.sh|.ps1` (idempotent, never overwrite, 0600) + `.gitignore`; test: second run changes nothing.
- [x] 1.4 Verify: `docker build`, `docker run --rm img id -u` ≠ 0, `serve_prod --help`.

## Phase 2: Stack (S2)
- [x] 2.1 RED static tests: only caddy publishes, `read_only`, `cap_drop`, digests, depends_on conditions, no concrete domain outside `.env.example`.
- [x] 2.2 GREEN `deploy/compose.yml` (postgres, migrate, control-plane, caddy) + `deploy/.env.example`.
- [x] 2.3 GREEN `deploy/Caddyfile` (TLS env switch, proxy, headers, `/downloads`, no listing, `latest.json` no-cache).
- [x] 2.4 Verify `docker compose config` exits 0 and contains no secret values.

## Phase 3: Local proof (S3)
- [x] 3.1 `deploy/compose.dev.yml` (fake gateway, `internal`, ports 8080/8443, `tools` provision service).
- [x] 3.2 RED `tests/test_deploy_smoke.py` (opt-in): up --wait, `/status` ready via Caddy with extracted root cert, migrations count, `/admin/` 200, `/forge/v1/accounts/me` 401, wrong Host refused, tampered-migration blocks control-plane.
- [x] 3.3 GREEN `scripts/deploy-smoke.ps1` incl. `down -v` and absent-containers assertion.
- [x] 3.4 Run it on this machine; record exact output in the PR.

## Phase 4: Backup + docs (S4)
- [x] 4.1 RED backup tests in smoke: run-once dump, `pg_restore --list`, retention KEEP=2, restore refuses non-empty DB.
- [x] 4.2 GREEN `deploy/backup/backup.sh`, `restore.sh`, compose `backup` service.
- [x] 4.3 `docs/deploy.md`: DNS/firewall, LE vs internal, first org, upgrade/rollback, Fernet-key loss + offline secrets backup, single-worker why, installer upload; doc test for key-loss warning.
- [x] 4.4 Final: full unittest + smoke + `compileall`.

## Apply notes (deviations from the plan)

- Branches: `feat/fv2-deploy-compose-s1-image` -> `s2-stack` -> `s3-local-proof` -> `s4-backup-docs`, stacked on `feat/fv2-prod-runtime-s5-origin-config`.
- Secret files are 0644 inside a 0700 directory (the unprivileged container users must read bind-mounted Docker secrets); 0600 would break them.
- The fake gateway service is omitted: the production profile only accepts https gateway origins (plain http loopback is dev-only).
- The `provision` service lives in `compose.yml` (profile `tools`), not in the dev overlay, because first-company provisioning is a production step.
- Restore is DATA-ONLY into a database built by `migrate` (the schema attestation hashes deparsed expressions that a dump/restore round trip rewrites, so a restored schema never attests). Dumps are one `.dump` file; no roles file.
- The backup role is `backup_reader`, not `forge_*`: the attestation fingerprints every `forge_%` role.
- `.gitattributes` was added so Linux-executed files keep LF endings when checked out on Windows.
