# Verification Report: v1-white-label
**Verdict: FAIL (one test-only regression; trivial fix) -> PASS WITH WARNINGS once fixed** | Mode: hybrid | Strict TDD: active | 14/14 tasks ticked

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

## CRITICAL
C1. tests/test_postgres_mvp_readiness.py::test_the_previous_profile_without_0025_is_refused fails at stack head: tests/mvp_support.py LOGIN_ROLES gained forge_branding_service (W2b 9e05867) but this test builds a DB without 0025, so ALTER ROLE fails. Production code unaffected, but the "profile missing 0025 is refused" behavior is currently untested and the apply report claimed readiness OK. Fix: make MvpDatabase tolerate absent roles (only roles that exist) or skip branding role for pre-0025 profile.

## TDD compliance
Tables present for batches 1-2; batch 3 narrative. Honest admissions: theme.spec pinning tests and W5b e2e not RED-first; W3b branding_guard characterization. No tautology found; palette vector loops iterate non-empty golden data.

## Spec compliance
- org-branding (validated storage/CAS/contrast/cross-org, safe assets, public endpoint no-leak/rate-limit, content-addressed delivery, reset): PG branding 23 + branding_http 6 + store 11, test_branding_api 34, assets 28 fuzz (every truncation + byte flip) OK.
- admin-branding (preview, validation, conflict, reset, themed shell, strict CSP): UI 13 + e2e in branding-smoke OK.
- client-branding / client-rebrand (code gate, offline cache, hostile payload, palette parity, CSP, icons, brand seam): unit 222, py 338, node 60, branding-smoke OK.

## Security assessment
Sanitizer: rebuilds PNG/WebP from allow-listed chunks, strips text/EXIF/ICC/trailing, rejects SVG/animated/markup/oversize, hash of stored bytes; assets served nosniff + CSP sandbox + immutable, only if in current revision. Public endpoint: uniform constant 404, rate limit 30/s per peer + global bucket, XFF ignored. No raw CSS: typed tokens only, exact-key schema, setProperty; admin CSP strict (no inline). Brand-follows-org: client holds 'Preparing your workspace', falls back to default, never another org's look (G2 tests + smoke). Client bridge re-validates and sha-checks cache.

## WARNING
1. Admin never shows the company code (slug) employees must type (grep: no slug/company code in admin/src); only docs mention it. Real usability gap.
2. Client CSP keeps script-src 'unsafe-inline' (Next hydration); Tauri CSP/desktop build not exercised.
3. Rate limiter process-local, keyed on socket peer: behind a reverse proxy all users share one bucket (self-DoS); org codes guessable (public by design).
4. react artifact preview (CDN scripts) blocked by CSP (functional regression, documented).
5. Unreadable-palette error surfaces only after Save (server round trip); preview flags it.
6. Brand/seed fixes in other slices (G1 server gate) good, but docs/mvp-local.md still Spanish.
SUGGESTION: add copyable company code + invite link in Branding page; preview client login screen and tab icon.

## Product quality
Genuinely easy for the core: name, login copy, 3 colors, 2 fonts, 3 logos, live preview, reset with history, conflict reload, contrast feedback. Gaps: company code discoverability, no template/preset, no client login preview. Overall good, not yet turnkey.

## Follow-up after verification

Resolved on the stacked branches after this report (see apply-progress, batches 4 and 5):

- CRITICAL fixture regression: `tests/mvp_support.py` now configures only the login roles the built schema created; the previous-profile refusal tests pass (mvp_readiness, mvp_up, mvp_local and the branding PG modules).
- Admin never showed the company code: migration 0026 returns the code from `branding_member_read` (F26), the authenticated branding read exposes it (not the public read, save or reset), and the Branding page shows it with a copy button. Live palette readability and the sign-in and browser-tab preview were added to the page.
- `mvp-smoke` and `branding-smoke` pass on the final branch.