# Proposal: v1-multiuser

## Intent

The MVP client binds ONE (org, member) profile per process forever (`ProfileStorage.selected`, `forge_workspace.py:117`): a second member gets 403 until restart. v1 goal 1 requires several members and organizations served correctly by one client run, with per-user data isolation. The MVP verify-report also left five warnings (flake, scoped revocation, downgrade clause, dirty build tree, no multi-user e2e) that this change closes.

## Scope

### In Scope
- Loopback **profile router** (`clients/openyak/backend/app/forge_router.py`): authenticates each bearer against the control plane (CP), resolves (org, membership), lazily spawns/reuses ONE unchanged `forge_workspace` worker per profile, reaps idle/logged-out/suspended workers, caps worker count.
- Launcher starts the router in place of the single backend; frontend sends the active org and gains an org picker/switcher.
- CP: suspension revokes sessions only when the account has no other active membership (migration 0024 + F24 fingerprint).
- Fold-ins: deflake `test_postgres_directory.py` (repro first); amend downgrade clause to forward-only; stop `next build` dirtying tracked files; multi-user e2e in `scripts/mvp-smoke.ps1`.

### Out of Scope
- Un-globalising the OpenYak fork (multiplexing profiles in one process).
- Capabilities/sandbox, white-label, Tauri icons, remote/server deployment (containers), per-user quotas.

## Capabilities

### New Capabilities
- `profile-router`: per-bearer authentication, per-profile worker lifecycle, isolation and failure behaviour of the loopback router.

### Modified Capabilities
- `managed-client-launch`: launcher runs the router; login handles members of several orgs (picker/switch).
- `member-administration`: suspension revokes sessions only without another active membership.
- `gateway-origin-policy`: downgrade clause becomes forward-only (documented precondition, no mechanism).
- `mvp-local-runtime`: smoke proves concurrent multi-user isolation and a clean tracked tree.

## Approach

Exploration approach B: router + process-per-profile. The worker keeps its one-profile invariant as defence in depth (403 on mismatch). Unscoped routes (login, me, accept, health) are served by a storage-less in-process `create_workspace_app` gate; org-scoped routes (bootstrap, models, `/api/*`) are proxied to the profile worker. Active org travels in `X-Forge-Organization` (UUID only) on `/api/*`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `clients/openyak/backend/app/forge_router.py` | New | Router, worker pool, reaper |
| `clients/openyak/scripts/forge-managed.mjs`, `forge-isolation.mjs` | Modified | Spawn router; worker arg plan |
| `clients/openyak/frontend/src/lib/forge-accounts.ts`, `forge-context.ts`, gate, `middleware.ts` | Modified | Org header, picker, keyed remount |
| `clients/openyak/.gitignore`, `frontend/tsconfig.json` | Modified | Build hygiene |
| `migrations/0024_*.sql`, `src/forge/mvp_profile.py` | New/Modified | Scoped revocation, F24 |
| `tests/test_postgres_directory.py` | Modified | Flake fix |
| `scripts/mvp-smoke.ps1`, `docs/mvp-local.md` | Modified | Multi-user e2e |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cross-profile UI state leaks on org switch (global zustand) | Med | Keyed remount + store resets; e2e asserts |
| Worker RAM/spawn latency | Med | Cap (default 8), idle TTL, LRU reap, spawn lock |
| Shared data root races between workers | Low | Test concurrent first-bind |
| Migration 0024 changes pinned fingerprint | Med | New F24 gate; PG tests one module at a time |
| Local process can call a worker directly | Low | Needs valid bearer + Host/Origin; same as MVP |

Security: no new secret surface; tenant isolation by process + path; no cost impact.

## Rollback Plan

Per-slice revert on stacked branches. Router is additive: restoring the launcher line re-runs the single worker. 0024 only replaces a function body (CREATE OR REPLACE); revert by re-applying 0023's body in a forward migration (migrations are forward-only).

## Dependencies

Branch bases: CP `feat/mvp-final-smoke`; client `feat/mvp-c4-client-e2e`. PG harness (Docker).

## Success Criteria

- [ ] Two members of one org and one of another chat concurrently in one client run, each seeing only own data.
- [ ] Suspending in org A keeps the account's org B session valid; org A routes deny.
- [ ] `test_postgres_directory.py` passes 10 consecutive runs.
- [ ] `mvp-smoke.ps1` PASS and `git status` clean in both repos afterwards.
