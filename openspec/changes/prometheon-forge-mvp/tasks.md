# Tasks: Prometheon Forge functional MVP

Two stacked-to-main chains, local only (no push/PR/merge). Strict TDD: every slice = RED (observe failing test) -> GREEN -> REFACTOR, one work-unit commit (tests + docs with code), conventional commits, no AI attribution.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~10,400 total (CP ~6,300 / CL ~4,100), 25 slices after splits |
| 400-line budget risk | High (review_budget_lines = 800 per slice) |
| Chained PRs recommended | Yes |
| Suggested split | A2->A2a/A2b, A5->A5a/A5b, C2->C2a/C2b, A0->A0/A0b (see table) |
| Delivery strategy | auto-chain (force-chained) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Per-slice estimate (additions + deletions; tests/docs included; lockfiles/binary assets/fonts excluded and reported)

| Slice | Est. | Over 800? |
|-------|------|-----------|
| 0 setup | ~0 (git only) | no |
| A0 docs (exploration, proposal, design, tasks, stub, .gitignore) | ~540 | no |
| A0b specs (8 spec.md) | ~540 | no (was A0 ~1,080: split) |
| A1 fake gateway | ~450 | no |
| A2a policy+adapters | ~480 | no |
| A2b 0019 + mvp_profile + PG gate | ~420 | no (A2 whole ~900: split) |
| A3 me+departments | ~700 | no |
| A4 members | ~700 | no |
| A5a provisioning+contract | ~520 | no |
| A5b mvp_local+admin_mount+readiness+script | ~650 | no (A5 whole ~1,170: split; STOP if >800) |
| A6 API isolation E2E | ~350 | no |
| B1 admin scaffold/login | ~700 | borderline; lockfile+fonts excluded |
| B2 members UI | ~600 | no |
| B3 gateway+catalog UI | ~600 | no |
| B4 Playwright admin | ~300 | no |
| C1 remove key flow | ~500 (mostly deletions) | no |
| C2a launcher+verifier | ~450 | no |
| C2b me-context+contract pin | ~450 | no (C2 whole ~900: split) |
| C3a tokens/assets | ~450 | no (binary icons excluded) |
| C3b strings/BrandMark | ~700 | borderline |
| C4 client E2E | ~350 | no |
| Final smoke+docs | ~300 | no |

Rule: if any slice measures >800 at apply time, STOP, report, split by work unit; never compress code/tests/docs. One honest slicing pass; otherwise recommend `size:exception`.

### Stacks (base = previous branch; A0 base = `main`)

- CP (`.worktrees/mvp`): `feat/mvp-a0-docs` -> `a0b-specs` -> `a1-fake-gateway` -> `a2a-origin-policy` -> `a2b-origin-migration` -> `a3-me-departments` -> `a4-members` -> `a5a-provisioning-contract` -> `a5b-mvp-local` -> `a6-api-isolation` -> `b1-admin-scaffold` -> `b2-admin-members` -> `b3-admin-gateway` -> `b4-admin-e2e` -> `feat/mvp-final-smoke` (all prefixed `feat/mvp-`).
- CL (`clients/openyak`): `feat/mvp-c1-remove-key-flow` -> `c2a-managed-launcher` -> `c2b-me-context-contract` -> `c3a-brand-tokens` -> `c3b-brand-strings` -> `c4-client-e2e`.
- Dependencies: A1->A6 linear; B1 after A5b (needs mounted admin) but B2 after A4, B3 after A2b; C1 independent; C2a after A3; C2b after A5a (pin fixture until Final); C3/C4 after C2b; Final needs all.

## Slice 0: Setup (no source edits)

- [x] 0.1 CP: `git -C N:\Proyects\forge branch main 7e4a149` (verify `git rev-parse main` = 7e4a149)
- [x] 0.2 CL: `git -C clients\openyak branch main acdb53b`; `git tag upstream-v1.5.0-rc.3 a9adf9f` (verify both)
- [x] 0.3 `git worktree add .worktrees\mvp -b feat/mvp-a0-docs main`; link `.venv` junction to `tenant-storage\.venv` (fallback: fresh venv, authorize install first)
- [x] 0.4 Copy `openspec/changes/prometheon-forge-mvp/*` from tenant-storage into `.worktrees\mvp\openspec\changes\prometheon-forge-mvp\`
- [x] 0.5 Verify: `git -C .worktrees\mvp status`, `.venv\Scripts\python.exe -m unittest discover -s tests -p test_fake_gateway.py` N/A yet; baseline `-p test_dev_accounts_gateway.py -v` green

## A0 docs (branch `feat/mvp-a0-docs`)
Files: `openspec/changes/prometheon-forge-mvp/{exploration,proposal,design,tasks}.md`, `docs/mvp-local.md` (stub), `.gitignore` (+`src/forge/web/admin/`). No source.
- [x] A0.1 Commit docs + stub + gitignore as `docs(mvp): add Forge MVP SDD artifacts`
- [x] A0.2 Verify: `git diff --stat main` only allowed files; `git check-ignore src/forge/web/admin/x`

## A0b specs (`a0b-specs`)
Files: `openspec/changes/prometheon-forge-mvp/specs/*/spec.md` only.
- [x] A0b.1 Commit 8 specs as `docs(mvp): add MVP capability specs`

## A1 fake gateway (`a1-fake-gateway`)
Files: `src/forge/fake_gateway.py`, `tests/test_fake_gateway.py`. Deps: A0b.
- [x] A1.1 RED: tests for models list, streamed chat (role chunk, deltas, stop, `[DONE]`, no content-encoding), non-loopback bind refusal (fake-gateway: Models, Streamed chat, Non-loopback bind)
- [x] A1.2 RED: bad key 401, key recording/custody proof, no echo, `fake-error`/`fake-malformed`/`fake-slow`, reset isolation
- [x] A1.3 GREEN: implement `fake_gateway.py`; REFACTOR
- [x] A1.4 RED/GREEN: existing adapters (`gateway_catalog_adapter`, `gateway_inference_adapter`) parse fake output (16 KiB/event limit) within same test file
- [x] A1.5 Verify: `.venv\Scripts\python.exe -m unittest discover -s tests -p test_fake_gateway.py -v`

## A2a origin policy (`a2a-origin-policy`)
Files: `src/forge/gateway_origins.py`; Modify `gateway_configuration.py`, `gateway_catalog_adapter.py`, `gateway_inference_adapter.py`, `account_api.py` (GatewayBody/Response +`endpoint`, `allowed_endpoints`), `gateway_configuration_store.py`; `tests/test_gateway_origins.py`. Deps: A1.
- [x] A2a.1 RED: allow-listed accepted, non-listed/look-alike denied, dev-vs-prod loopback http, cross-origin redirect refused, 422 on bad `endpoint`, record endpoint re-checked at call time (gateway-origin-policy)
- [x] A2a.2 GREEN: policy + injected `frozenset` allow-list; cipher payload binds endpoint; origin change without key rejected
- [x] A2a.3 Verify: `-p test_gateway_origins.py -v` plus `test_gateway_configuration*.py`, `test_gateway_catalog_adapter*.py`, `test_gateway_inference_adapter*.py` unchanged-green

## A2b migration 0019 (`a2b-origin-migration`)
Files: `migrations/0019_gateway_origin.sql`, `src/forge/mvp_profile.py`, `tests/test_postgres_gateway_origin.py`. Deps: A2a. Must NOT mutate `dev_accounts_gateway` ADDITIONS/PROFILE.
- [x] A2b.1 RED: widened CHECK, new `gateway_save(..., endpoint)`, existing rows survive, tenant isolation of origin
- [x] A2b.2 GREEN: 0019 SQL + `MVP_ADDITIONS`/`MVP_CHECKPOINTS`
- [x] A2b.3 GATE: fresh-apply 0001-5+0010-19 vs upgrade-from-0018 yield identical `catalog_fingerprint`; pin F19. FAIL or Docker down => STOP; fall back to B2 (fixed origin, no 0019)
- [x] A2b.4 Verify: `scripts\test-postgres.ps1 -TestPattern test_postgres_gateway_origin.py`; then `scripts\test-postgres.ps1` full (old upgrade/dev_accounts tests stay green)

## A3 me + departments (`a3-me-departments`)
Files: `migrations/0020_directory_identity.sql`, `src/forge/directory.py`, `directory_store.py`, Modify `account_api.py`, `mvp_profile.py` (F20); `tests/test_directory*.py`, `tests/test_postgres_directory.py`. Deps: A2b.
- [ ] A3.1 RED: me for admin/multi-org/member, 401 no/invalid/logged-out session, 403 `MEMBERSHIP_SUSPENDED`, caller never supplies org id; departments list/create/duplicate/cross-org 404 (identity-discovery, member-administration)
- [ ] A3.2 GREEN: 0020 (`forge_directory_authority` NOLOGIN, narrow RLS, EXECUTE to `forge_gateway_service`) + store + routes; pin F20 by fresh==upgrade rule
- [ ] A3.3 Verify: `-p test_directory*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_directory.py`

## A4 members (`a4-members`)
Files: `migrations/0021_member_administration.sql`, Modify `directory.py`, `directory_store.py`, `account_api.py`, `mvp_profile.py` (F21); `tests/test_member_administration*.py`, `tests/test_postgres_member_administration.py`. Deps: A3.
- [ ] A4.1 RED: admin list, non-admin 403, cross-org 404, suspend/reactivate, 409 `LAST_ADMIN`, unknown/foreign id 404, concurrent suspend (row lock)
- [ ] A4.2 GREEN: 0021 SQL (last-admin + role checks inside function) + store/routes; pin F21
- [ ] A4.3 Verify: `-p test_member_administration*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_member_administration.py`

## A5a provisioning + contract (`a5a-provisioning-contract`)
Files: `src/forge/provisioning.py`, `contract.py`, `contract/forge-mvp.contract.json`; Modify `account_api.py` (`GET /forge/v1/contract`); tests `test_provisioning.py`, `test_contract.py`. Deps: A4.
- [ ] A5a.1 RED: provision org, idempotent rerun, two-org seed; contract drift test (regenerate == committed, `contract_version: forge-mvp/1`, sha endpoint)
- [ ] A5a.2 GREEN: `python -m forge.provision`; contract generator + route
- [ ] A5a.3 Verify: `-p test_provisioning.py -v`, `-p test_contract.py -v`

## A5b mvp_local runtime (`a5b-mvp-local`)
Files: `src/forge/mvp_local.py`, `mvp_readiness.py` (pins F21), `admin_mount.py`, `scripts/mvp-local.ps1`, Modify `pyproject.toml` (package-data), `docs/mvp-local.md`; tests `test_mvp_local.py`, `test_admin_mount.py`. Deps: A5a. STOP and report if >800.
- [ ] A5b.1 RED: valid/missing/malformed config, env ignored, port occupied, foreign Origin/Host rejected, CORS only 3411, startup fails if admin build missing, CSP + SPA fallback, invite `.eml` mailbox (mvp-local-runtime)
- [ ] A5b.2 GREEN: ports from single `mvp_ports`; `DeliveryCoordinator(origin=http://127.0.0.1:3411)`; PG17 readiness
- [ ] A5b.3 Verify: `-p test_mvp_local.py -v`, `-p test_admin_mount.py -v`, `scripts\test-postgres.ps1`

## A6 API isolation E2E (`a6-api-isolation`)
Files: `tests/test_mvp_api_isolation.py` only. Deps: A5b.
- [ ] A6.1 RED/GREEN: 2 orgs cross-org 404, key absent from responses/logs/stream, `fake-slow` suspend mid-stream denied, logout revokes, member sees only published aliases
- [ ] A6.2 Verify: `scripts\test-postgres.ps1 -TestPattern test_mvp_api_isolation.py`; full `.venv\Scripts\python.exe -m unittest discover -s tests -v`

## B1 admin scaffold/login (`b1-admin-scaffold`)
Files (in `admin/`): `package.json`, lockfile, `vite.config.ts` (base `/admin/`), `tsconfig.json`, `index.html`, `src/{main,App}.tsx`, `api/client.ts`, `auth/session.ts`, `brand/{theme.ts,tokens.css}`, `pages/Login.tsx`, `public/fonts/*`+licenses, `playwright.unit.config.ts`, unit tests. Deps: A5b. Pins read from client lockfile; `npm ci` needs authorization.
- [ ] B1.1 RED: login admin/member, org switch clears state, 404 rendering, memory-only token, no storage, offline assets (admin-web)
- [ ] B1.2 GREEN: implement; REFACTOR
- [ ] B1.3 Verify (cwd `admin`): `npm run test:unit`, `npx tsc --noEmit`, `npm run build` (output gitignored)

## B2 members UI (`b2-admin-members`)
Files: `admin/src/pages/Members.tsx`, `api/members.ts`, `components/{InviteDialog,MemberTable}.tsx`, tests. Deps: B1, A4.
- [ ] B2.1 RED: invite, suspend, last-admin error, keyboard/reduced-motion; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit`

## B3 gateway + catalog UI (`b3-admin-gateway`)
Files: `admin/src/pages/{Gateway,Catalog}.tsx`, `api/gateway.ts`, tests. Deps: B2, A2b.
- [ ] B3.1 RED: save key (allow-listed endpoint select, key never rendered), revision conflict, publish catalog; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit`

## B4 admin Playwright (`b4-admin-e2e`)
Files: `admin/playwright.config.ts`, `admin/e2e/admin-flow.spec.ts`, `scripts/admin-e2e.ps1`. Deps: B3.
- [ ] B4.1 RED/GREEN: invite->gateway->publish flow against `mvp_local`+fake gateway. Verify: `scripts\admin-e2e.ps1`

## C1 remove key flow (`feat/mvp-c1-remove-key-flow`, CL)
Files: Delete `backend/app/forge_managed.py`, `scripts/forge-gateway-dev.ps1`, `GatewayAdminView`+tests; Modify `scripts/forge-workspace-dev.mjs` (drop `--gateway-stdin`), `backend/app/forge_workspace_dev.py`, i18n, tests. Deps: Slice 0.
- [ ] C1.1 RED: no key surface, admin route absent (managed-client-launch); GREEN by deletion. Verify: backend `pytest backend/tests -q -k forge`, `npm run test:unit`, `npx tsc --noEmit` (cwd `frontend`)

## C2a launcher + verifier (`c2a-managed-launcher`)
Files: `scripts/forge-managed.mjs`, `scripts/forge-isolation.mjs` (-> `verifyIsolation()`), `package.json` scripts, tests; remove `forge-managed-web/accounts-dev/prelogin-dev/workspace-dev.mjs`. Deps: C1, A3.
- [ ] C2a.1 RED: one test per refusal (non-loopback origin, legacy ports 3319/3320/3331/3332, port busy, env allow-list, `.env`, relative/in-repo/real-OpenYak data dir, pin mismatch); valid launch OK
- [ ] C2a.2 GREEN; Verify: `npm run test:unit`, `npx tsc --noEmit`

## C2b me-context + contract pin (`c2b-me-context-contract`)
Files: `frontend/src/lib/forge-context.ts`, `contract/forge-contract.pin.json`, `backend/app/forge_workspace.py`, `forge_contract.py`, Modify `forge-accounts.ts`; tests. Deps: C2a, A5a (fixture).
- [ ] C2b.1 RED: login+discovery, suspended/invalid, logout, mid-stream stop, over-limit, unpublished alias; backend fails closed on sha mismatch
- [ ] C2b.2 GREEN; Verify: backend `pytest backend/tests -q -k forge`, `npm run test:unit`, `npx tsc --noEmit`

## C3a tokens/assets (`c3a-brand-tokens`)
Files: `frontend/src/lib/brand.ts`, `public/{fonts/*,favicon.svg,manifest.json}`, `globals.css`, Tauri icons. Deps: C2b.
- [ ] C3a.1 RED: tokens, contrast, local fonts only, single-source theme, manifest; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit`

## C3b strings (`c3b-brand-strings`)
Files: `components/brand/BrandMark.tsx` (replaces `OpenYakLogo`, 7 usages), splash, title bar, `locales/{en,zh}`, `(mobile)/layout.tsx` notFound, `docs` tech-debt note, visible-string sweep test. Deps: C3a.
- [ ] C3b.1 RED: rendered-text scan has no "OpenYak", mobile `/m` 404, attribution/legal kept; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit`, `npm run lint`

## C4 client E2E (`c4-client-e2e`)
Files: `frontend/tests/ui/forge-managed-flow.spec.ts`, Playwright config. Deps: C3b.
- [ ] C4.1 RED/GREEN: `next build && next start`; member login -> published models -> streamed chat. Verify: `npm run test:ui -- forge-managed-flow`

## Final smoke (`feat/mvp-final-smoke`, CP + CL)
Files: `docs/mvp-local.md`, `scripts/mvp-smoke.ps1`, contract equality check. Deps: B4, C4.
- [ ] F.1 RED: contract file equality (CP vs CL pin byte-identical); GREEN: smoke script boots CP+fake gateway+client, runs acceptance flow
- [ ] F.2 Verify: `scripts\mvp-smoke.ps1`; full control-plane suite + `scripts\test-postgres.ps1`; client `npm run test:unit`, `npx tsc --noEmit`
- [ ] F.3 Verify success criteria: key absent everywhere, no visible "OpenYak", all slices <=800
