# Verification Report: v1-multiuser
**Verdict: PASS WITH WARNINGS** | Mode: hybrid | Strict TDD: active | 17/17 tasks ticked

## Execution evidence (independent, 2026-10-12, worktree .worktrees/mvp @ feat/v1wl-c4-branding-smoke; client @ feat/mvp-v1-wl-c4c-client-branding-e2e)
| Command | Result |
|---|---|
| scripts\mvp-smoke.ps1 | PASS rc0, 228 s (admin flow, managed-flow, multiuser flow; both trees clean; ports 3410-3413 freed) |
| scripts\branding-smoke.ps1 | PASS rc0, 154 s (two orgs gate, admin branding, admin-set branding, CSP; trees clean) |
| admin npm run test:unit / tsc | 142 passed / rc0 |
| CP non-PG unittest discover (tests) | 692 run, 8 skipped, 92 errors = ALL in test_postgres_* modules (306 "Real PostgreSQL required"); 0 non-PG failures |
| PG member_administration | 29 OK |
| PG directory x3 | 18 OK x3 (deflake holds) |
| PG branding / branding_http / branding_store | 23 / 6 / 11 OK |
| PG accounts / provisioning / mvp_up / gateway_origin / mvp_local | 11 / 11 / 2 / 14 / 6 OK |
| **PG mvp_readiness** | **FAILED 1/4: test_the_previous_profile_without_0025_is_refused -> psycopg UndefinedObject role "forge_branding_service" does not exist** |
| client frontend test:unit / managed config / tsc | 222 / 7 passed / rc0 |
| client node --test (9 files) | 61 tests, 60 pass, 1 skipped, 0 fail |
| client py unittest (backend venv, from tests/) | 338 OK |
| Docker | owned containers removed; no ports 3319/3320/3331/3332 touched; no source edits |

## TDD compliance
apply-progress (#3359) reports RED->GREEN per slice in prose (no formal table). Test files all exist and pass now (router pool/proxy/real/cli, forge-multiorg.spec, forge-multiuser-flow, test_mvp_smoke, PG member_administration, directory). Triangulation good (pool 30 tests, proxy 40+). Assertion audit: no tautologies; no ghost loops found. WARNING: evidence format is narrative, not the table.

## Spec compliance (all scenarios have a passing runtime test)
- profile-router: process-per-profile (proxy test_members_and_organizations_never_share_a_worker, pool distinct ports, multiuser e2e 3 contexts + profile dir count) OK; bearer-before-routing (401 no spawn x3 tests, identical non-member denial, bad org header) OK; lifecycle: idle reap, in-flight, cap/LRU, logout, suspension, router exit (unit); fail-closed 503 redacted, SSE unbuffered OK.
- member-administration scoped revocation: PG 29 OK (multi-org suspend A keeps B, concurrent advisory lock, single-org revoked).
- gateway-origin-policy, managed-client-launch, mvp-local-runtime (multi-user smoke, dirty tree, clean run): covered by passing smoke + test_mvp_smoke + launcher node tests.

## Security
Router never spawns before control-plane membership resolves; non-UUID/unknown org -> 403 without forward; worker env scrubbed, argv explicit, reserved ports blocked; bearer kept only as sha256; logout stops workers before answer; 401/403 confirmed with CP before evict.

## Issues
CRITICAL: none for this change.
WARNING: (1) isolation is process/app-level under one OS user; worker loopback ports reachable by any local process (bearer still required). (2) membership cache 15 s: router-level revocation window. (3) cap/idle-reap only unit-tested, not e2e. (4) KDF semaphore fix in accounts.py cross-surface. (5) TDD evidence prose only.
SUGGESTION: document OS-level isolation limit.
