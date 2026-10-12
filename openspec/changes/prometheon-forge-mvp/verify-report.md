# Verification Report: prometheon-forge-mvp

Mode: Strict TDD, hybrid. Verdict: **PASS WITH WARNINGS**

## Evidence (independently run)
| Command | Result |
|---|---|
| `scripts\mvp-smoke.ps1` (mvp worktree, final-smoke branch) | PASS: admin e2e 2/2, client e2e 3/3, container/workspace/client dir removed, ports 3410-3413 free afterwards |
| `admin: npm run test:unit` / `npx tsc --noEmit` | 92 passed / exit 0 |
| client `node --test tests/*.test.mjs` | 58/58 |
| client `frontend: npm run test:unit` / `npx tsc --noEmit` | 135 passed / exit 0 |
| CP unit: gateway_origins 38, directory 12, directory_api 13, member_administration 9 + api 8, account_api 10, fake_gateway 21, contract 9, provisioning 11, admin_mount 10, mvp_local 15, mvp_up 9 (1 skip), mvp_smoke 6 | all OK |
| PG (one at a time, harness): gateway_origin OK (F19 gate), member_administration OK (F22/F23), mvp_api_isolation 5 OK, directory 18 | directory: 2 of 6 runs FAILED (errors=3, cause not captured), 4 of 6 OK |

## Spec coverage
All 8 capabilities have passing runtime evidence: origin policy (test_gateway_origins + PG origin + A6), identity-discovery (directory/API/PG), member-administration (unit + PG + concurrency, A6 mid-stream suspend), mvp-local-runtime (mvp_local/up/provisioning/admin_mount/smoke), fake-gateway (21), admin-web (92 unit/ui + e2e 2), managed-client-launch (node 58 incl. no-key-surface, e2e 3), client-rebrand (visible-string sweep + e2e no OpenYak on `/` and `/onboarding`).
Security: isolation (A6 cross-org identical 404 both ways), key absent from responses/logs/stream/DOM/storage/cookies (A6 + e2e), default deny, redacted errors, suspended-member denial + stream stop, look-alike origins (exact string membership) — all covered by passing tests.

## Issues
CRITICAL: none.
WARNING:
1. `test_postgres_directory.py` intermittent: 2 failures (errors=3) in 6 runs, then 4 consecutive passes. Cause not captured; likely timing/resource-related in a migration/role test. Needs a repro with captured log before archive.
2. Spec clause "downgrade refused if any non-default origin row exists" has no mechanism or test (migrations are forward-only; only proposal.md describes the manual rule).
3. Known limitation: client backend binds one profile per process (second member 403); acceptable for MVP, must be documented.
4. `next build` dirties tracked `frontend/next-env.d.ts` + `tsconfig.json` in clients/openyak after smoke (verified: working tree modified after the smoke run).
5. Suspension revokes ALL sessions of the account (cross-tenant effect for multi-org members); design deviation to confirm.
6. PG test files for provisioning/readiness/mvp_local/mvp_up were written pre-implementation but first run post-implementation (no separate RED run); partially compensated by mutations.
SUGGESTION: pin postgres tests to a quieter run order / add retry diagnostics; full client `npm run lint` hangs >10 min; design.md vs tasks.md numbering reconciled in A5a docs.
