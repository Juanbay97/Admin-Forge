# Tasks: Prometheon Forge functional MVP

Two stacked-to-main chains, local only (no push/PR/merge). Strict TDD: every slice = RED (observe failing test) -> GREEN -> REFACTOR, one work-unit commit (tests + docs with code), conventional commits, no AI attribution.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~10,400 total (CP ~6,300 / CL ~4,100), 25 slices after splits |
| 400-line budget risk | High (review_budget_lines = 800 per slice) |
| Chained PRs recommended | Yes |
| Suggested split | A2->A2a/A2b, A3->A3a/A3b, A4->A4a/A4b, A5->A5a/A5b, C2->C2a/C2b, A0->A0/A0b (see table) |
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
| A3a me | ~490 | no (A3 whole 976: split at apply) |
| A3b departments | ~490 | no |
| A4a member list | ~470 | no (A4 whole 863: split at apply) |
| A4b member lifecycle | ~400 | no |
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

- CP (`.worktrees/mvp`): `feat/mvp-a0-docs` -> `a0b-specs` -> `a1-fake-gateway` -> `a2a-origin-policy` -> `a2b-origin-migration` -> `a3-me-departments` (A3a) -> `a3b-departments` -> `a4-members` (A4a) -> `a4b-member-lifecycle` -> `a5a-provisioning-contract` -> `a5a2-contract` -> `a5b-mvp-local` -> `a5b2-serve-composition` -> `a5b3-local-supervisor` -> `a6-api-isolation` -> `b1-admin-scaffold` (B1a) -> `b1b-admin-login` -> `b2-admin-members` -> `b3-admin-gateway` (B3a) -> `b3b-admin-catalog` -> `b4-admin-e2e` -> `feat/mvp-final-smoke` (all prefixed `feat/mvp-`).
- CL (`clients/openyak`): `feat/mvp-c1-remove-key-flow` -> `c2a-managed-launcher` -> `c2b-me-context-contract` -> `c3a-brand-tokens` -> `c3b-brand-strings` -> `c4-client-e2e`.
- Dependencies: A1->A6 linear; B1 after A5b (needs mounted admin) but B2 after A4b, B3 after A2b; C1 independent; C2a after A3a; C2b after A5a (pin fixture until Final); C3/C4 after C2b; Final needs all.

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

## A3a me (`a3-me-departments`, branch name retained; A3 split into A3a/A3b at apply time: 976 authored lines > 800)
Files: `migrations/0020_directory_identity.sql` (role, narrow RLS, `directory_account`, `directory_me`), `src/forge/directory.py`, `directory_store.py`, Modify `account_api.py` (`GET /forge/v1/accounts/me`), `mvp_profile.py` (F20); `tests/test_directory.py`, `tests/test_directory_api.py`, `tests/test_postgres_directory.py`. Deps: A2b.
- [x] A3a.1 RED: me for admin/multi-org/member, 401 no/invalid/logged-out session, 403 `MEMBERSHIP_SUSPENDED`, caller never supplies org id (identity-discovery)
- [x] A3a.2 GREEN: 0020 (`forge_directory_authority` NOLOGIN, narrow RLS, EXECUTE to `forge_gateway_service`) + store + route; pin F20 by fresh==upgrade rule (F20 = `eb61cb72...befe672`)
- [x] A3a.3 Verify: `-p test_directory*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_directory.py`

## A3b departments (`feat/mvp-a3b-departments`, stacked on A3a)
Files: `migrations/0021_department_directory.sql` (`directory_admin`, department list/create, case-insensitive unique name index, org-wide read + insert policies), Modify `directory.py`, `directory_store.py`, `account_api.py` (`GET|POST /forge/v1/orgs/{id}/departments`), `mvp_profile.py` (F21); extend the three `tests/test_directory*.py`/`test_postgres_directory.py` files. Deps: A3a. Departments get their own migration so reviewed 0020 bytes (and F20) stay immutable; consequently A4 moves to migrations 0022/0023 (F22/F23, see A4a/A4b) and A5b pins F23.
- [x] A3b.1 RED: departments list/create/duplicate/cross-org+non-admin uniform 404, 409 `DEPARTMENT_EXISTS`, invalid name 422 (member-administration)
- [x] A3b.2 GREEN: 0021 + store + routes; pin F21 by fresh(0001-0005+0010-0021)==upgrade-from-0020 (F21 = `bcb3ce1d...faaaeb`)
- [x] A3b.3 Verify: `-p test_directory*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_directory.py`

## A4a member list (`a4-members`, branch name retained; A4 split into A4a/A4b at apply time: 863 authored lines > 800)
Files: `migrations/0022_member_directory.sql` (renumbered from 0021 when A3b took 0021; org-scoped read policies, `directory_member_rows`, `directory_members`), Modify `directory.py`, `directory_store.py`, `account_api.py` (`GET /forge/v1/orgs/{o}/members`), `mvp_profile.py` (F22); `tests/test_member_administration.py`, `tests/test_member_administration_api.py`, `tests/test_postgres_member_administration.py`. Deps: A3b.
- [x] A4a.1 RED: admin list (all statuses, roles, departments, no secrets), non-admin/cross-org/unknown-org uniform 404, 401 before service (member-administration)
- [x] A4a.2 GREEN: 0022 SQL + store/route; pin F22 by fresh(0001-0005+0010-0022)==upgrade-from-0021 (F22 = `4df89fdf...d06f5b`)
- [x] A4a.3 Verify: `-p test_member_administration*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_member_administration.py`

## A4b member lifecycle (`feat/mvp-a4b-member-lifecycle`, stacked on A4a)
Files: `migrations/0023_member_lifecycle.sql` (`UPDATE(status)` + session-revoke grants/policies, `directory_member_status` with last-admin guard under row locks), Modify `directory.py` (`DirectoryLastAdmin`, suspend/reactivate), `directory_store.py`, `account_api.py` (`POST .../members/{m}/suspend|reactivate`, 409 `LAST_ADMIN`), `mvp_profile.py` (F23); extend the three `tests/*member_administration*.py` files. Deps: A4a. A5b therefore pins F23.
- [x] A4b.1 RED: suspend/reactivate, session revocation, 409 `LAST_ADMIN` (incl. self-suspension), unknown/foreign id 404, concurrent mutual suspension (row lock)
- [x] A4b.2 GREEN: 0023 SQL (last-admin + role checks inside function, admin rows locked FOR UPDATE; suspension revokes all of the account's sessions) + store/routes; pin F23 by fresh==upgrade-from-0022 (F23 = `e025d612...199c0d`, identical to the schema of the pre-split combined 0022 verified earlier)
- [x] A4b.3 Verify: `-p test_member_administration*.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_member_administration.py`

## A5a provisioning (`a5a-provisioning-contract`; A5a split into provisioning + contract at apply time: 842 authored lines > 800)
Files: `src/forge/provisioning.py` (+ `provision.py` entry shim for `python -m forge.provision`); tests `test_provisioning.py`, `test_postgres_provisioning.py`, `tests/mvp_support.py` (owned-PG fixture with the full 0001-0023 schema, reused by A5b/A6; provisioning is only provable on real PostgreSQL). Deps: A4b.
- [x] A5a.1 RED: provision org, idempotent rerun, two-org seed, atomic credentials delivery, redacted CLI
- [x] A5a.2 GREEN: `python -m forge.provision` (operator file, loopback only, credentials file exclusive-create)
- [x] A5a.3 Verify: `-p test_provisioning.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_provisioning.py`

## A5a2 contract pin (`feat/mvp-a5a2-contract`, stacked on A5a)
Files: `src/forge/contract.py`, `contract/forge-mvp.contract.json`; Modify `account_api.py` (`GET /forge/v1/contract`); test `test_contract.py`. Hash = sha256 of canonical JSON (never file bytes: Windows autocrlf). Deps: A5a.
- [x] A5a2.1 RED: contract drift test (regenerate == committed, `contract_version: forge-mvp/1`), served hash tracks the serving app
- [x] A5a2.2 GREEN: generator from app routes + `GET /forge/v1/contract` + `python -m forge.contract --write|--check`
- [x] A5a2.3 Verify: `-p test_contract.py -v`; account/directory/member/gateway API suites unchanged-green

## A5b mvp_local runtime (A5b was ~1,050 authored lines > 800: split at apply time into A5b1/A5b2/A5b3)
A5b1 `feat/mvp-a5b-mvp-local`: `src/forge/admin_mount.py` (CSP, SPA fallback, caching, degraded 503; Host/Origin guard + CORS), `mvp_readiness.py` (pins F23); tests `test_admin_mount.py`, `test_postgres_mvp_readiness.py`; `tests/mvp_support.py` (`migrations=` parameter). Deps: A5a2.
- [x] A5b1.1 RED: CSP + SPA fallback + traversal, build missing (required -> `ADMIN_BUILD_MISSING`, optional -> clear 503), foreign Host/Origin rejected, CORS only the client origin; MvpReadiness accepts F23 only
- [x] A5b1.2 GREEN: `admin_mount.py` + `mvp_readiness.py` (a missing build can degrade instead of failing: the admin SPA is built by B1, after this slice)
- [x] A5b1.3 Verify: `-p test_admin_mount.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_mvp_readiness.py`

A5b2 `feat/mvp-a5b2-serve-composition`: `src/forge/mvp_local.py` config-only `serve` (strict config, ports from one `MVP_PORTS`, no env discovery, secrets file, `DeliveryCoordinator(origin=client)`, `.eml` mailbox, allow-list policy, `MvpReadiness`, `/status`); test `test_mvp_local.py`, `test_postgres_mvp_local.py`. Deps: A5b1.
- [x] A5b2.1 RED: valid/missing/malformed/unknown-key config, env ignored, port occupied binds nothing, status ready, invite `.eml` with the client origin
- [x] A5b2.2 GREEN: `mvp_local.py` serve composition (`load_config`/`load_secrets`/`assemble`/`compose`/`serve`; `main` drops every PG* variable from the process)
- [x] A5b2.3 Verify: `-p test_mvp_local.py -v`; `scripts\test-postgres.ps1 -TestPattern test_postgres_mvp_local.py`

A5b3 `feat/mvp-a5b3-local-supervisor`: Modify `fake_gateway.py` (`serve()`/CLI), `mvp_local.py` (`up` subcommand; canonical-module entry point), new `mvp_up.py` (supervised owned PG17 + schema + seed + fake gateway + control plane), `scripts/mvp-local.ps1`, `pyproject.toml` (package-data), `docs/mvp-local.md`; tests `test_fake_gateway_serve.py`, `test_mvp_up.py`, `test_postgres_mvp_up.py`. Deps: A5b2.
- [x] A5b3.1 RED: fake gateway serve/CLI (keys file, loopback only, port occupied), supervisor wiring
- [x] A5b3.2 GREEN + script/docs; real owned-container smoke (full stack: login, gateway PUT, catalogue refresh via the fake gateway, publish, member stream, clean stop with container absent)
- [x] A5b3.3 Verify: `-p test_fake_gateway.py -v`, `-p test_mvp_local.py -v`, `scripts\test-postgres.ps1` modules one at a time

## A6 API isolation E2E (`a6-api-isolation`)
Files: `tests/test_mvp_api_isolation.py` only. Deps: A5b3.
- [x] A6.1 RED/GREEN (verification slice over existing code; bite proven by mutation: key logged on open, revocation interval 3600 s): 2 orgs cross-org 404, key absent from responses/logs/stream, `fake-slow` suspend mid-stream denied, logout revokes, member sees only published aliases
- [x] A6.2 Verify: `scripts\test-postgres.ps1 -TestPattern test_mvp_api_isolation.py`; full `.venv\Scripts\python.exe -m unittest discover -s tests -v`

## B1 admin scaffold/login (B1 was ~1,370 authored lines > 800: split at apply time into B1a/B1b; lockfile, fonts, PNGs and OFL licence text excluded)
Test runner: `@playwright/test` 1.59.1 (client-consistent) with two projects in `playwright.unit.config.ts`: `unit` (browser-free) and `ui` (production bundle in system Chrome against a mocked same-origin API, served with the control-plane CSP). Pins from the client lockfile (React 19.2.4, TS 5.9.3, Tailwind 4.2.1, Playwright 1.59.1); Vite 7.3.7 (max supported by `@tailwindcss/vite` 4.2.1) + `@vitejs/plugin-react` 5.2.0.

B1a `feat/mvp-b1-admin-scaffold`: `admin/{package.json,package-lock.json,tsconfig.json,vite.config.ts,playwright.unit.config.ts,.gitignore}`, `public/{fonts,brand}/*` (+OFL licences), `src/{api/client.ts,api/account.ts,auth/session.ts,auth/access.ts,brand/theme.ts,brand/tokens.css,scope/orgScope.ts}`, `tests/csp.ts`, `tests/unit/*.spec.ts`. Deps: A5b. No bundle entry yet (arrives in B1b).
- [x] B1a.1 RED: session memory-only (storage trapped), API client (bearer, no credentials/referrer, typed errors, 401 ends session), entry resolution (admin-only orgs, auto-select, denied), org-scope reducer (switch clears, stale reply ignored), brand theme/tokens (single source, self-hosted fonts), CSP drift vs `admin_mount.py` (admin-web)
- [x] B1a.2 GREEN: implement; verify (cwd `admin`): `npm run test:unit` (30 unit), `npx tsc --noEmit`

B1b `feat/mvp-b1b-admin-login`: `admin/{index.html,README.md}`, `src/{main,App}.tsx`, `src/api/runtime.ts`, `src/pages/{Login,Overview}.tsx`, `src/components/{Console,AccessDenied,NotFound}.tsx`, `tests/ui/{support,login.spec,hardening.spec}.ts`. Deps: B1a.
- [x] B1b.1 RED: login admin/member/wrong password/sign out, org picker (admin orgs only), org switch clears state + late reply ignored, 404 rendering, no storage/cookies/URL secret, reload = re-login, offline same-origin assets under CSP, keyboard-only, reduced motion (admin-web)
- [x] B1b.2 GREEN: implement; REFACTOR
- [x] B1b.3 Verify (cwd `admin`): `npm run test:unit`, `npx tsc --noEmit`, `npm run build` (output gitignored)

## B2 members UI (`b2-admin-members`)
Files: `admin/src/pages/Members.tsx`, `api/members.ts`, `components/{InviteDialog,MemberTable}.tsx`, tests. Deps: B1, A4b.
- [x] B2.1 RED: invite (pending row: the server lists members only after acceptance), suspend/reactivate, last-admin error, org-switch clears list, 404 rendering, keyboard/Escape focus return, reduced-motion (7 unit + 9 UI observed failing first); GREEN. Verify (cwd `admin`): `npm run test:unit` (59 pass), `npx tsc --noEmit`, `npm run build`. Also modified `src/api/runtime.ts`, `src/App.tsx`, `src/components/Console.tsx` (Overview/Members navigation), `src/members/model.ts` (pure helpers), `tests/ui/support.ts` (stateful members/invitations double)

## B3 gateway + catalog UI (B3 est. ~990 authored lines > 800: split at apply time into B3a gateway / B3b catalog)
B3a `feat/mvp-b3-admin-gateway`: `admin/src/{api/gateway.ts,api/services.ts,gateway/model.ts,pages/Gateway.tsx}`; Modify `api/runtime.ts` (single `services` bundle replaces per-port exports), `App.tsx`, `components/Console.tsx` (Gateway view); tests `tests/unit/gateway.spec.ts`, `tests/ui/gateway.spec.ts`, `tests/ui/support.ts` (gateway double with CAS). Deps: B2, A2b.
- [x] B3a.1 RED: save key (allow-listed base-URL select, key write-only: password field, cleared on submit, never rendered or echoed), revision conflict (409 shows reload prompt, nothing overwritten, reload then save works), rejected key (redacted 422), 404 rendering, org switch clears, keyboard, reduced motion (5 unit + 8 UI observed failing first)
- [x] B3a.2 GREEN; verify (cwd `admin`): `npm run test:unit` (72 pass), `npx tsc --noEmit`, `npm run build`

B3b `feat/mvp-b3b-admin-catalog`: `admin/src/{pages/Catalog.tsx,api/catalog.ts,catalog/model.ts}`; Modify `api/services.ts`, `api/runtime.ts`, `components/Console.tsx` (Catalog view); tests `tests/unit/catalog.spec.ts`, `tests/ui/catalog.spec.ts`, `tests/ui/support.ts` (catalogue double with CAS). Deps: B3a.
- [x] B3b.1 RED: refresh discovery, map aliases to upstream ids (suggested alias grammar, validation of invalid/duplicate/none), publish with default (expected catalogue/gateway revisions, operation id), conflict publishes nothing, unreachable gateway, status lists exactly the aliases a member sees, org switch clears, 404 rendering, keyboard, reduced motion (10 unit + 10 UI observed failing first)
- [x] B3b.2 GREEN; verify (cwd `admin`): `npm run test:unit` (92 pass), `npx tsc --noEmit`, `npm run build`

## B4 admin Playwright (`b4-admin-e2e`)
Files: `admin/playwright.config.ts`, `admin/e2e/admin-flow.spec.ts`, `scripts/admin-e2e.ps1`. Deps: B3.
- [x] B4.1 RED/GREEN: login -> members invite/suspend/reactivate -> gateway key save -> catalogue refresh/publish -> member sees published aliases, against the real `mvp_local` control plane + fake gateway, plus real-CSP mount check (no violations, own font loaded, inline script blocked, no storage/cookies). RED: stack without admin build, both specs failed (503 mount; login never rendered). GREEN: `scripts\admin-e2e.ps1` (build, owned stack, Playwright, bounded waits, confirmed container/workspace removal). Also modified `admin/package.json` (`test:e2e`), `admin/tsconfig.json`, `admin/README.md`, `docs/mvp-local.md`. Verify: `scripts\admin-e2e.ps1` (2 e2e pass), `npm run test:unit` (92 pass), `npx tsc --noEmit`

## C1 remove key flow (`feat/mvp-c1-remove-key-flow`, CL)
Files: Delete `backend/app/forge_managed.py`, `scripts/forge-gateway-dev.ps1`, `GatewayAdminView`+tests; Modify `scripts/forge-workspace-dev.mjs` (drop `--gateway-stdin`), `backend/app/forge_workspace_dev.py`, i18n, tests. Deps: Slice 0.
- [x] C1.1 RED: no key surface, admin route absent (managed-client-launch); GREEN by deletion. Verify: backend `pytest backend/tests -q -k forge`, `npm run test:unit`, `npx tsc --noEmit` (cwd `frontend`) (CL commits 323be61 key flow, 96d8bfe gateway admin)

## C2a launcher + verifier (`c2a-managed-launcher`)
Files: `scripts/forge-managed.mjs`, `scripts/forge-isolation.mjs` (-> `verifyIsolation()`), `package.json` scripts, tests; remove `forge-managed-web/accounts-dev/prelogin-dev/workspace-dev.mjs`. Deps: C1, A3.
- [x] C2a.1 RED: one test per refusal (non-loopback origin, legacy ports 3319/3320/3331/3332, port busy, env allow-list, `.env`, relative/in-repo/real-OpenYak data dir, pin mismatch); valid launch OK
- [x] C2a.2 GREEN; Verify: `npm run test:unit`, `npx tsc --noEmit` (CL ec88ac1, 6fbaaf1, 2f733cb, 8487345)

## C2b me-context + contract pin (`c2b-me-context-contract`)
Files: `frontend/src/lib/forge-context.ts`, `contract/forge-contract.pin.json`, `backend/app/forge_workspace.py`, `forge_contract.py`, Modify `forge-accounts.ts`; tests. Deps: C2a, A5a (fixture).
- [x] C2b.1 RED: login+discovery, suspended/invalid, logout, mid-stream stop, over-limit, unpublished alias; backend fails closed on sha mismatch
- [x] C2b.2 GREEN; Verify: backend `pytest backend/tests -q -k forge`, `npm run test:unit`, `npx tsc --noEmit` (CL 047b328, f4908ee, 131452a, 7951542 invitation acceptance)

## C3a tokens/assets (`c3a-brand-tokens`)
Files: `frontend/src/lib/brand.ts`, `public/{fonts/*,favicon.svg,manifest.json}`, `globals.css`, Tauri icons. Deps: C2b.
- [x] C3a.1 RED: tokens, contrast, local fonts only, single-source theme, manifest; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit` (CL 4895ebf)

## C3b strings (`c3b-brand-strings`)
Files: `components/brand/BrandMark.tsx` (replaces `OpenYakLogo`, 7 usages), splash, title bar, `locales/{en,zh}`, `(mobile)/layout.tsx` notFound, `docs` tech-debt note, visible-string sweep test. Deps: C3a.
- [x] C3b.1 RED: rendered-text scan has no "OpenYak", mobile `/m` 404, attribution/legal kept; GREEN. Verify: `npm run test:unit`, `npx tsc --noEmit`, `npm run lint` (CL d5fbe58)

## C4 client E2E (`c4-client-e2e`)
Files: `frontend/tests/ui/forge-managed-flow.spec.ts`, Playwright config. Deps: C3b.
- [x] C4.1 RED/GREEN: `next build && next start`; member login -> published models -> streamed chat. Verify: `npm run test:ui -- forge-managed-flow` Delivered as CL `feat/mvp-c4-client-e2e` 9a82f8e + 69efef3: `frontend/tests/ui/forge-managed-flow.spec.ts` with `frontend/playwright.forge-managed-flow.config.ts` (run `npx playwright test -c playwright.forge-managed-flow.config.ts`, not `npm run test:ui`, whose default config starts a dev server). RED: spec against the real stack failed on invitation activation (quoted-printable link), a second member refused by the one-profile backend, and stream chunking assumptions; GREEN: 3 e2e pass inside `scripts\mvp-smoke.ps1`. Also fixed the two stale unit failures (`playwright.unit.managed.config.ts`, layout assertion).

## Final smoke (`feat/mvp-final-smoke`, CP + CL)
Files: `docs/mvp-local.md`, `scripts/mvp-smoke.ps1`, contract equality check. Deps: B4, C4.
- [x] F.1 RED: contract file equality (CP vs CL pin byte-identical); GREEN: smoke script boots CP+fake gateway+client, runs acceptance flow RED: `tests/test_mvp_smoke.py` (4 failures: runner and docs absent); GREEN: 6 OK (pin equals contract, EOL-independent hash, runner safety, docs) and `scripts\mvp-smoke.ps1` PASS.
- [x] F.2 Verify: `scripts\mvp-smoke.ps1`; full control-plane suite + `scripts\test-postgres.ps1`; client `npm run test:unit`, `npx tsc --noEmit` Control-plane plain suite: 505 tests, only the 48 harness-less PostgreSQL errors; PostgreSQL harness not re-run (no schema or control-plane source change in the final slice). Client: node 58/58, `test:unit` 135 + managed 7, `tsc` and eslint on changed files clean.
- [x] F.3 Verify success criteria: key absent everywhere, no visible "OpenYak", all slices <=800 Key and gateway host absent from DOM, storage, cookies, network URLs/headers/bodies in the real browser; no "OpenYak" in rendered text of `/` and `/onboarding`; slices <=800 (A-series splits recorded above).
