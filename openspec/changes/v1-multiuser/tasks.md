# Tasks: v1-multiuser

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3.4k (CP ~0.9k, client ~2.5k) |
| 400-line budget risk | High (budget in use: 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | 9 slices, two stacks |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Base | Est. lines |
|------|------|------|-----------|
| CP1 | Deflake PG directory + downgrade spec amendment | `feat/mvp-final-smoke` | ~200 |
| CP2 | Scoped session revocation (0024, F24) | CP1 | ~450 |
| C1 | Build hygiene (next-env/tsconfig) | `feat/mvp-c4-client-e2e` | ~40 |
| C2 | Router core: WorkerPool, reaper | C1 | ~700 |
| C3 | Router proxy, auth, logout/suspension | C2 | ~750 |
| C4 | Launcher runs router | C3 | ~350 |
| C5 | Frontend org header, picker, switch | C4 | ~600 |
| C6 | Multi-user e2e spec | C5 | ~350 |
| CP3 | mvp-smoke multi-user + clean tree, docs | CP2 + C6 | ~300 |

Strict TDD: every unit is RED (observe failing) -> GREEN -> REFACTOR. Commands: CP `.venv\Scripts\python.exe -m unittest discover -s tests -p test_<module>.py -v`; PG via `scripts\test-postgres.ps1`, one module at a time; client py `backend\.venv\Scripts\python.exe -m unittest discover -s tests -p test_forge_router*.py -v`; node `node --test <explicit files>`; frontend `npm run test:unit`, `npx tsc --noEmit`.

## Phase 1: CP1 Warnings cleanup

- [x] 1.1 Repro: loop `test-postgres.ps1` for `test_postgres_directory.py` x10 capturing stderr; record failing assertion in the commit message
- [x] 1.2 RED/GREEN: `separate_database` waits for the final server (observed cause: gate tests connected to a fresh container before its final server was up; roles/DB drop order was NOT the cause); 10 consecutive passes
- [x] 1.3 Amend `specs/gateway-origin-policy` (done in this change) and `docs/` note: 0019 forward-only precondition

## Phase 2: CP2 Scoped revocation

- [x] 2.1 RED: PG test in `tests/test_postgres_member_administration.py`: multi-org account, suspend org A -> session valid for B; A bootstrap/models/chat denied; single-org still revoked
- [x] 2.2 GREEN: `migrations/0024_scoped_session_revocation.sql`; register in `src/forge/mvp_profile.py`; pin F24 (fresh == upgrade-from-0023); mvp_readiness/tests follow F24; per-account advisory lock for concurrent cross-org suspension
- [x] 2.3 Audit: assert every org-scoped route denies suspended membership (`api.py:234` path) in a PG API test

## Phase 3: Client foundation (C1-C3)

- [ ] 3.1 C1: untrack/ignore `frontend/next-env.d.ts`; commit `tsconfig.json` as Next rewrites; node test: build leaves tree clean
- [ ] 3.2 C2 RED: `tests/test_forge_router_pool.py` (spawn lock, reuse, idle reap, in-flight guard, cap/LRU, spawn failure, shutdown, concurrent first bind)
- [ ] 3.3 C2 GREEN: `backend/app/forge_router.py` `RouterConfig`, `WorkerPool`, reaper
- [ ] 3.4 C3 RED: `tests/test_forge_router_proxy.py` (no bearer -> 401 no spawn; non-member identical denial; bad org header; SSE unbuffered; logout stops workers; 401/403 evicts)
- [ ] 3.5 C3 GREEN: gate mount + scoped proxy + token-digest registry; one real-worker test

## Phase 4: Launcher and frontend (C4-C5)

- [ ] 4.1 C4: `forge-managed.mjs` spawns router with worker plan; update `tests/forge-managed-launcher.test.mjs`, `forge-isolation*.test.mjs`
- [ ] 4.2 C5 RED: `frontend/tests/unit` controller specs: org list, pick, switch clears state, header set
- [ ] 4.3 C5 GREEN: `forge-accounts.ts`, `forge-context.ts`, gate + picker, keyed remount, store resets

## Phase 5: E2E and smoke

- [ ] 5.1 C6: `forge-multiuser-flow.spec.ts` (+ config): 3 contexts, concurrent chat, isolation, profile dir count
- [ ] 5.2 CP3: extend `scripts/mvp-smoke.ps1` (run C6; `git status --porcelain` both repos); update `docs/mvp-local.md`
- [ ] 5.3 Full run: `scripts\mvp-smoke.ps1` PASS; record evidence for verify
