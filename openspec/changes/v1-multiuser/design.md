# Design: v1-multiuser

## Technical Approach

Router + process-per-profile. The Next UI keeps rewriting `/forge/*` and `/api/*` to `FORGE_BACKEND_PORT`; that port now belongs to `app.forge_router` (new). The router reuses `forge_workspace` unchanged as the worker (`python -B -u -m app.forge_workspace ... --port <ephemeral>`), so the upstream-fork globals (`forge_runtime._paths`, `dependencies.py`, `get_settings()`) stay once-per-process.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Process model | One worker per (org, membership) | In-process multiplexing; restart-on-switch | Un-globalising the fork is a merge-debt/leak trap; restart is not multi-user |
| Unscoped routes | Router mounts a storage-less `create_workspace_app(config)` as gate for login, accept, `/accounts/me`, health | Re-implement validators | Existing `storage_root=None` path already does exact-projection validation |
| Scoped routes | Proxy bootstrap, `/orgs/{o}/models`, `/api/*` to worker | Gate handles them | Gate's `bound["organization"]` is process-global: two users would overwrite it |
| Profile resolution | Router calls CP `bootstrap?organization_id=` (cache key sha256(bearer)+org, TTL 15 s) to get membership id; worker still revalidates every request | Trust header only | Unauthenticated/foreign requests never spawn; worker stays the authority |
| Org selection | `X-Forge-Organization` (UUID) on `/api/*`; URL org elsewhere | Cookie / path prefix | Token is memory-only; no new storage; Next rewrite untouched |
| Worker ports | Router binds port 0, passes the number, 1 retry on start failure; never forbidden ports | Fixed range | Avoids collisions; TOCTOU window accepted on loopback |
| Reaping | Idle TTL 15 min, cap 8, LRU idle eviction, in-flight counter (streams) blocks reap | Never reap | ~150-300 MB per worker |
| Teardown | Graceful (CTRL_BREAK / SIGTERM, 5 s) then tree kill by owned PID only | Kill by name | Matches launcher rule: never touch foreign processes |
| Org switch (UI) | Keyed `Providers` remount per org id + reset of global stores | Page reload | Bearer is memory-only; reload = logout |
| Scoped revocation | Migration 0024 `CREATE OR REPLACE forge.directory_member_status`: revoke only if no other `active` membership for the identity; new F24 gate | Revoke all (MVP) | Sessions are account-scoped; per-request membership checks (`api.py:234`) deny the suspended org |
| Downgrade | Amend spec to forward-only | `assert_downgrade_safe()` | Migrations are forward-only; mechanism buys nothing |
| Build hygiene | `git rm --cached frontend/next-env.d.ts`, ignore it; commit `tsconfig.json` as Next rewrites it | Ignore tsconfig | Idempotent build; smoke asserts clean tree |

## Data Flow

    browser --Bearer + X-Forge-Organization--> Next --rewrite--> router
    router: login/me/accept ---------------> gate (in-process) --> CP
    router: bootstrap check --> CP (membership id)
    router: pool[(org,member)] --spawn/reuse--> worker --> SQLite profiles/<hash>/ , CP gateway
    reaper: idle / logout / suspension / shutdown --> stop worker

Logout: gate forwards to CP, then router stops workers recorded for that bearer digest. Suspension: worker bootstrap revalidation (per request, 15 s monitor) returns 403/401, router evicts the cache entry and stops the worker.

## File Changes

| File | Action | Description |
|---|---|---|
| `clients/openyak/backend/app/forge_router.py` | Create | Config, `WorkerPool`, reaper, proxy app |
| `clients/openyak/scripts/forge-managed.mjs` / `forge-isolation.mjs` | Modify | Spawn router, worker plan (python, args, env allow-list) |
| `clients/openyak/frontend/src/lib/forge-accounts.ts`, `forge-context.ts`, `forge-workspace-session.ts` | Modify | `selectOrganization(id)`, org header, switch |
| `.../components/forge/managed-workspace-gate.tsx` + org picker | Modify/Create | Picker, keyed remount |
| `.../frontend/src/middleware.ts` | Modify | Allow `X-Forge-Organization` (no new routes) |
| `clients/openyak/.gitignore`, `frontend/tsconfig.json`, `frontend/next-env.d.ts` | Modify/untrack | Hygiene |
| `clients/openyak/frontend/tests/ui/forge-multiuser-flow.spec.ts` + config | Create | 3-member e2e |
| `migrations/0024_scoped_session_revocation.sql`, `src/forge/mvp_profile.py` | Create/Modify | Function + F24 |
| `tests/test_postgres_directory.py`, `test_postgres_gateway_origin.py` | Modify | Flake fix |
| `scripts/mvp-smoke.ps1`, `docs/mvp-local.md` | Modify | Multi-user e2e, clean-tree assert |

## Interfaces

    RouterConfig(control_plane_origin, ui_origin, port, data_dir, python, worker_cwd, idle_ttl=900, max_workers=8)
    WorkerPool.acquire(org: UUID, member: UUID, token_digest: str) -> Worker  # spawn lock per profile
    Worker(port, process, in_flight: int, last_used: float)  # stop(), healthy()

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (client py) | Pool, reaper, cap, spawn failure, header validation, proxy denial | `unittest` in client `tests/test_forge_router*.py` with fake spawner + `httpx.MockTransport`; run `backend\.venv\Scripts\python.exe -m unittest discover -s tests -p test_forge_router*.py -v` (backend venv has no pytest) |
| Unit (node) | Launcher plan/stop | `node --test tests/forge-managed-launcher.test.mjs ...` explicit files |
| Unit (frontend) | Controller multi-org, switch resets | `npm run test:unit`, `npx tsc --noEmit` |
| PG | 0024, F24, multi-org revoke, flake loop | One module at a time via `scripts\test-postgres.ps1`; 10x loop for directory |
| Real process | Router spawns real worker | One unittest with real `forge_workspace` + CP MockTransport-free fixture server |
| E2E | 3 members concurrent | `forge-multiuser-flow.spec.ts` via mvp-smoke |

## Migration / Rollout

0024 is forward-only and additive (function body). Router ships with the launcher in the same slice that rewires it; no feature flag.

## Open Questions

- [ ] Concurrent first `ForgePaths(root).validate()` across workers: race-safe? (test in C2)
- [ ] Does the seed already contain two members in one org? (verify; extend `mvp_local` seed only if not)
- [ ] Flake root cause is a hypothesis (cluster-global role drop vs dependent DB); reproduce before fixing.
