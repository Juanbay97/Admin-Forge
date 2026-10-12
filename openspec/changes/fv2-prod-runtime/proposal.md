# Proposal: Production Runtime for the Control Plane

## Intent

The only runtime today is the loopback-only dev composition (`mvp_local.py`: DB host 127.0.0.1, `OriginPolicy(dev=True)`, `LocalTestMailbox`, Host guard pinned to `127.0.0.1:port`, JSON config + `secrets.json`). `runtime.py` rejects every `PG*` env var. Migrations are raw SQL applied once by an operator (`mvp_up.install_schema`): no runner, no upgrade path. The gateway origin spelling (`ia.prometheonlab.com`) is hard-coded in `gateway_origins.DEFAULT_ENDPOINT` and in DB CHECKs (0015, 0019). Deployment on an Ubuntu server behind Caddy is impossible until a production profile exists.

## Scope

### In Scope
- `forge.prod_config`: env + `*_FILE` secret loader (role passwords, delivery/gateway Fernet keys), `FORGE_PUBLIC_ORIGIN`, DB host/port/name/sslmode, `FORGE_GATEWAY_ORIGINS` allow-list (prod `OriginPolicy`, no dev http).
- `forge.migrate`: idempotent runner (`forge.schema_migrations`, sha256 per file, advisory lock, ordered list, final fingerprint check vs latest checkpoint, idempotent LOGIN passwords from secret files).
- `forge.composition` shared builder extracted from `mvp_local.compose`; `apply_guard` accepts a trusted-host set.
- `python -m forge.serve_prod {migrate,serve,healthcheck}`: non-loopback bind, JSON logs with request id (no tokens/PII), `/livez` + existing `/status`, graceful stop, single worker (documented).
- Migration 0027: relax DB gateway-origin CHECK to any canonical https origin (app allow-list stays authority); F27 ripple.

### Out of Scope
- Docker/Caddy/compose (fv2-deploy-compose), SMTP (fv2-smtp-delivery), platform scope/key pool (fv2-platform-core/gateway-keys).
- Changing `mvp_local` behaviour (stays the dev profile).

## Capabilities

### New Capabilities
- `prod-runtime`: env/secret-file configuration, trusted-host guard, serve/health/logging contract.
- `schema-migration-runner`: ordered, checksummed, locked, fingerprint-verified migration application.
- `gateway-origin-config`: deployment-configurable gateway origin allow-list without code or DB spelling coupling.

### Modified Capabilities
None (no pre-existing specs in `openspec/specs/`).

## Approach

Add new modules beside the dev ones; extract the pure wiring (`compose`) into `forge.composition` so both profiles share it, guarded by existing `test_mvp_local`. Strict TDD: unittest + owned PG17 harness. Runner reuses `catalog_fingerprint` + `MVP_CHECKPOINTS`. Slices: config → runner → composition/guard → serve_prod/logs → 0027.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/forge/prod_config.py`, `migrate.py`, `composition.py`, `serve_prod.py`, `logging_json.py` | New | Runtime |
| `src/forge/mvp_local.py`, `admin_mount.py` | Modified | Use composition; host set |
| `src/forge/gateway_origins.py` | Modified | `DEFAULT_POLICY` stays; env-driven policy factory |
| `migrations/0027_*.sql`, `mvp_profile.py`, `mvp_readiness.py` | New/Modified | F27 ripple |
| `tests/` | New | unit + PG tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Crash between script and record row re-applies a non-idempotent migration | Med | Fingerprint pre-check per checkpoint; scripts are single-transaction |
| 0027 number collides with fv2-gateway-keys | Med | Orchestrator assigns; slice 5 is conditional |
| F27 ripple across pinned hash tests | Med | One slice, ~150 lines of ripple |
| Superuser DB credential in migrate job | Med | Only the one-shot `migrate` service holds it |

## Rollback Plan

All new modules are additive; revert the slice commits. `mvp_local` keeps its public API (composition extraction is behaviour-preserving). 0027 is additive/relaxing: roll back by restoring the 0019 CHECK via a forward migration, never by editing applied files (checksum mismatch fails loudly).

## Dependencies
- Base `feat/v1wl-v3d-openspec-artifacts` (93c49a2); PG17 digest in `scripts/postgres-image.txt`; Docker local.

## Success Criteria
- [ ] Fresh PG: `migrate` applies 0001–0026(+0027), rerun is a no-op, tampered file fails.
- [ ] `serve_prod` serves on a non-loopback bind with env/secret-file config only; foreign Host refused.
- [ ] No DOMAIN/gateway spelling hard-coded outside defaults; allow-list env drives policy.
- [ ] Full existing unittest + PG suites green.
