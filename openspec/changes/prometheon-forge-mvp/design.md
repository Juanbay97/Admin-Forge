# Design: Prometheon Forge functional MVP

## Technical Approach

Extend the existing owned-account control plane (`create_account_app`, Bearer sessions, per-org Fernet gateway key, catalog publish, SSE chat) with: allow-listed per-org gateway origin, `/accounts/me`, departments, member list/suspend, a fake OpenAI-compatible gateway, a supervised `mvp_local` composition serving the admin SPA same-origin, and a productized client launcher. Default-deny, explicit trusted composition, no env discovery, no fake identity (config rules). Specs: gateway-origin-policy, identity-discovery, member-administration, mvp-local-runtime, fake-gateway, admin-web, managed-client-launch, client-rebrand.

Findings that shape this design (from code):
- Every schema profile has its own pinned fingerprint (`*_readiness.py`) plus a `CHECKPOINTS` journal in `dev_accounts_gateway.py`. `gateway_save` (0015) and the CHECK on `organization_gateways.endpoint` hardcode the origin; `GatewayRecord.endpoint` already exists and is returned by 0016/0017 functions.
- No SQL exists for member list/suspend/me/departments, so A3/A4 also need additive migrations (0020, 0021), not just 0019.
- Invitation link = `{DeliveryCoordinator origin}/onboarding#invitation_id&capability`; `trusted_origin` allows plain HTTP only for an explicit loopback origin. Client already has `/onboarding`.
- Client `AccountsController` talks to the control plane directly from the browser (CORS), bearer in memory only.

## Architecture Decisions

| # | Topic | Decision | Rejected | Why |
|---|-------|----------|----------|-----|
| 1 | Invitation origin | Client UI origin `http://127.0.0.1:3411` passed explicitly to `DeliveryCoordinator(origin=)` by `mvp_local`; mailbox = local `.eml` dir in private workspace | Admin origin (3410); env/Host-derived origin | Onboarding page lives in the client; Host-derived links are injectable; `trusted_origin` already enforces explicit loopback |
| 2 | Gateway origin (0019) | Deployment allow-list `frozenset[str]` injected into `GatewayConfiguration`/adapters; admin picks one on PUT (`endpoint`, default = ia.prometheonlab.com). Allow-list is authority; DB CHECK widened to `https://ia.prometheonlab.com` OR `http://127.0.0.1:<port>` as defense-in-depth; new `gateway_save(..., endpoint)` (old kept, additive). Cipher payload binds the record endpoint; adapters re-check record endpoint ∈ allow-list at call time; no redirects (already off) | Free-text URL; per-request URL | SSRF/key-exfil: a key is only ever sent to an operator-approved origin |
| 3 | 0019 readiness checkpoint | New `forge/mvp_profile.py` (`MVP_ADDITIONS`, `MVP_CHECKPOINTS`) - does NOT mutate `ADDITIONS/PROFILE` of `dev_accounts_gateway` (retained demos keep working). Gate in A2 before merge: on owned PG17 harness fresh-apply 0001-5+0010-19 and upgrade-from-0018 yield the same `catalog_fingerprint`; value pinned as F19. 0020/0021 each append F20/F21 under the same rule. A5 adds `MvpReadiness` pinning F21 | Runtime-learned hash; one readiness class per migration | Matches repo pattern (static, authored from reviewed bytes); avoids 3 throwaway readiness classes. If gate fails or Docker unavailable: STOP, fall back to B2 (single deployment-fixed origin through trusted transport; DB CHECK unchanged, no 0019) |
| 4 | Contract pin | Control plane commits `contract/forge-mvp.contract.json` (`contract_version: "forge-mvp/1"`, routes with request/response key sets, error codes) and serves `GET /forge/v1/contract` -> `{contract_version, schema_sha256}`. Drift test regenerates it from app routes. Client commits byte-identical `contract/forge-contract.pin.json`; its backend fetches the endpoint at startup and **fails closed** on sha mismatch. Final slice compares both files | Shared package; runtime OpenAPI diff; no pin | No cross-repo tooling, tamper/drift visible in tests, client knows exact shape |
| 5 | Replace `forge-isolation.mjs` | Throw guard becomes verifier `scripts/forge-isolation.mjs` exporting `verifyIsolation()`; launcher `scripts/forge-managed.mjs` (replaces forge-managed-web/workspace-dev/accounts-dev/gateway-dev.ps1) refuses to start unless all pass: explicit loopback control-plane origin, forbidden legacy ports {3319,3320,3331,3332}, ports free, clean env allow-list (`childEnvironment`), no `.env` (`refuseDotenv`), data dir absolute, outside repo and not the user's real OpenYak dir, contract pin matches, prod `next build/start` (no dev compile). npm scripts call verifier (non-zero on failure). Tests assert each refusal | Env switch to bypass; delete guard | Quarantine lift must be earned by checks, never a toggle |
| 6 | Mobile PWA `/m` | **Hidden**, not renamed: `(mobile)/layout.tsx` calls `notFound()` in managed mode; manifest rebranded (name/short_name/theme `#0B1D26`, `start_url:/c/new`) | Rename/rebrand remote-control pages | Remote-desktop feature is out of MVP; hiding is smaller, reversible, no dead UI |
| 7 | Ports | Control plane+admin **3410**, client UI **3411**, client workspace backend **3412**, fake gateway **3413**, PG random loopback. Single `mvp_ports` constants; launcher refuses legacy four | Reuse 3319/3320/3331/3332 | Existing demo (PID 23940) may own them |
| 8 | Admin SPA serve/auth | Vite base `/admin/`, build to `src/forge/web/admin` (gitignored, not committed); `mvp_local` mounts it (startup fails if missing); SPA fallback to `index.html` (no-store), hashed assets immutable. CSP `default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'`. Auth = existing login -> Bearer, **memory only** (reload = re-login; same as client). Bearer header, no cookies => CSRF not applicable; middleware still rejects `/forge/v1` mutations whose `Origin` is not {3410, 3411} and Host != `127.0.0.1:3410` (DNS-rebinding). CORS allows only 3411 | Cookie sessions; sessionStorage token | No new session mechanism; smaller XSS blast radius |
| 9 | Fake gateway | `forge/fake_gateway.py` FastAPI, loopback-only bind (rejects others), exact Bearer key required, never echoes key. `GET /v1/models` -> OpenAI list; `POST /v1/chat/completions` `stream:true` -> `text/event-stream`, no content-encoding, role chunk, word-delta `chat.completion.chunk`s, final `finish_reason:"stop"`, `data: [DONE]`, within adapter limits (16 KiB/event). Model-id behaviours: `fake-fast`, `fake-slow` (delay, mid-stream suspend proof), `fake-error` (500), `fake-malformed`. Proves contract only; real OmniRoute strictness unverified | Mock transport only | Real HTTP+SSE path exercised by E2E |
| 10 | Brand seam | Tokens as CSS vars + typed theme object: `BrandTheme{name,colors{primary #0B1D26, teal #0F6B6D, accent #E07A2D (<=15%), sand #E8DCC1, carbon #1A1A1A},fonts{title Montserrat, body Inter},assets}`. Client `frontend/src/lib/brand.ts` + `applyBrandTheme()` writing `--brand-*` on `:root`, Tailwind 4 `@theme` reads vars; admin `admin/src/brand/{theme.ts,tokens.css}` same shape. Fonts self-hosted woff2 (+licenses), no runtime remote fetch. No Teal->Cobre gradients | Hardcoded hex in components | Per-company theme later = swap object, no component edits |
| 11 | Branching | See Rollout | - | - |

## Data Flow

    Admin SPA(/admin,3410) -login-> accounts/login -> Bearer(mem)
       |-- /accounts/me, members, departments, invitations --> account_api --> SECURITY DEFINER fns (RLS)
       |-- PUT gateway{endpoint,key} --> allow-list check --> Fernet(bind endpoint) --> organization_gateways
       |-- catalogue refresh/publish --> fake gateway(3413) /v1/models
    Client UI(3411) -login-> control plane; /me -> org context; /models (published only)
       |-> workspace backend(3412) CentralGateway --Bearer--> /orgs/{id}/chat/completions
              --> route revalidated per chunk (suspend => stop) --> key opened server-side --> fake gateway SSE

## Interfaces / Contracts

    GET  /forge/v1/contract                  {contract_version, schema_sha256}
    GET  /forge/v1/accounts/me               {account{id,email,display_name}, organizations[{id,display_name,roles[],status,departments[{id,name}]}]}
    GET|POST /forge/v1/orgs/{o}/departments  admin; list/create
    GET  /forge/v1/orgs/{o}/members          admin; [{id,email,display_name,roles,status,departments}]
    POST /forge/v1/orgs/{o}/members/{m}/suspend   admin; 409 LAST_ADMIN; suspended member -> 403 MEMBERSHIP_SUSPENDED
    PUT  /forge/v1/orgs/{o}/gateway          + optional `endpoint` (must be in allow-list, else 422); GET adds `allowed_endpoints`

Non-members/other orgs: uniform 404 (existing). Last-admin guard and role checks are enforced inside the SQL function under row lock, not only in Python. New NOLOGIN `forge_directory_authority` with narrow RLS policies; EXECUTE granted to the existing `forge_gateway_service` pool (no new LOGIN role).

## File Changes by Slice

Repos: CP = control plane (`.worktrees/mvp`), CL = `clients/openyak`. Python tests in `tests/`.

| Slice | Files (Create unless noted) |
|-------|-----------------------------|
| A0 docs (CP) | `openspec/changes/prometheon-forge-mvp/*` (commit), `docs/mvp-local.md` (stub), `.gitignore` (+`src/forge/web/admin/`) |
| A1 fake gateway (CP) | `src/forge/fake_gateway.py`, `tests/test_fake_gateway.py` |
| A2 origin policy (CP) | `migrations/0019_gateway_origin.sql`, `src/forge/gateway_origins.py` (policy+allow-list), `src/forge/mvp_profile.py`; Modify `gateway_configuration.py`, `gateway_catalog_adapter.py`, `gateway_inference_adapter.py`, `account_api.py` (GatewayBody/Response), `gateway_configuration_store.py`; `tests/test_gateway_origins.py`, `tests/test_postgres_gateway_origin.py` |
| A3 me+departments (CP) | `migrations/0020_directory_identity.sql`, `src/forge/directory.py`, `src/forge/directory_store.py`; Modify `account_api.py`, `mvp_profile.py`; `tests/test_directory*.py`, `tests/test_postgres_directory.py` |
| A4 members (CP) | `migrations/0021_member_administration.sql`; Modify `directory.py`, `directory_store.py`, `account_api.py`, `mvp_profile.py`; `tests/test_member_administration*.py`, `tests/test_postgres_member_administration.py` |
| A5 provisioning+runtime (CP) | `src/forge/provisioning.py` (`python -m forge.provision`), `src/forge/mvp_local.py` (supervised, uses `OwnedPostgres`/retained workspace), `src/forge/mvp_readiness.py`, `src/forge/admin_mount.py` (CSP/fallback/Origin+Host middleware), `src/forge/contract.py`, `contract/forge-mvp.contract.json`, `scripts/mvp-local.ps1`; Modify `pyproject.toml` (package-data); tests `test_provisioning.py`, `test_mvp_local.py`, `test_admin_mount.py`, `test_contract.py` (**~800: stop and report if over**) |
| A6 API isolation E2E (CP) | `tests/test_mvp_api_isolation.py` (2 orgs, cross-org 404, key never in responses/logs/stream, suspended denied mid-stream via `fake-slow`, logout) |
| B1 scaffold/login (CP) | `admin/package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/{main,App}.tsx`, `src/api/client.ts`, `src/auth/session.ts`, `src/brand/{theme.ts,tokens.css}`, `src/pages/Login.tsx`, `public/fonts/*` + licenses, `playwright.unit.config.ts`, unit tests |
| B2 members | `admin/src/pages/Members.tsx`, `src/api/members.ts`, `src/components/{InviteDialog,MemberTable}.tsx`, tests |
| B3 gateway+catalog | `admin/src/pages/{Gateway,Catalog}.tsx`, `src/api/gateway.ts`, tests |
| B4 Playwright | `admin/playwright.config.ts`, `admin/e2e/admin-flow.spec.ts`, `scripts/admin-e2e.ps1` |
| C1 remove key flow (CL) | Delete `backend/app/forge_managed.py`(ManagedGateway), `scripts/forge-gateway-dev.ps1`, `frontend/.../GatewayAdminView` + its tests; Modify `forge-workspace-dev.mjs` (drop `--gateway-stdin`), `forge_workspace_dev.py`, i18n, tests |
| C2 launcher (CL) | `scripts/forge-managed.mjs`, `scripts/forge-isolation.mjs` (Modify -> verifier), `backend/app/forge_workspace.py` (de-fixtured from `forge_workspace_dev.py`), `frontend/src/lib/forge-context.ts` (me-based; replaces `fixtureContext`), `contract/forge-contract.pin.json`, `backend/app/forge_contract.py`; Modify `package.json` scripts, `forge-accounts.ts` (origins from config); tests; remove `forge-managed-web/accounts-dev/prelogin-dev/workspace-dev.mjs` |
| C3a tokens/assets (CL) | `frontend/src/lib/brand.ts`, `public/fonts/*`, `public/favicon.svg`, `public/manifest.json` (Modify), `globals.css` (Modify: `--brand-primary #339CFF` -> tokens), Tauri icons |
| C3b strings (CL) | `components/brand/BrandMark.tsx` (replaces `OpenYakLogo` + 7 usages), splash, title bar, `locales/{en,zh}` (~28), `(mobile)/layout.tsx` notFound in managed mode; tests/ui visible-string sweep |
| C4 client E2E (CL) | `frontend/tests/ui/forge-managed-flow.spec.ts`, Playwright config |
| Final (CP+CL) | `docs/mvp-local.md`, `scripts/mvp-smoke.ps1`, contract-file equality check |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | policies, fake gateway SSE, contract hash, launcher refusals, brand theme | unittest / client Playwright-unit; RED first |
| Integration | 0019-0021 fresh vs upgrade fingerprint, RLS, last-admin, cross-org | owned PG17 harness (`scripts/test-postgres.ps1`); existing `test_postgres_gateway_upgrade`/`test_dev_accounts_gateway` must stay green (no change to old `ADDITIONS`) |
| E2E | admin invite->gateway->publish->member chat | Playwright (B4, C4), A6 API proof, Final smoke |

## Migration / Rollout

Additive migrations 0019-0021; rollback = revert slice, DB recreated (disposable/retained local PG). Never applied implicitly to existing demos.

Branches (local only, no push):
- CP: `git branch main 7e4a149`; `git worktree add .worktrees/mvp -b feat/mvp-a0-docs main` (`.venv` via junction to `tenant-storage\.venv`, fallback fresh venv). Linear stack: `feat/mvp-a0-docs` -> `a1-fake-gateway` -> `a2-origin-policy` -> `a3-me-departments` -> `a4-members` -> `a5-provisioning-runtime` -> `a6-api-isolation` -> `b1-admin-scaffold` -> `b2-admin-members` -> `b3-admin-gateway` -> `b4-admin-e2e` -> `feat/mvp-final-smoke`. A0 PR base = main; each next base = previous branch (retarget as predecessors merge; merge only with authorization).
- CL (in place, clean tree, reuses node_modules/.venv): `git branch main acdb53b`; `git tag upstream-v1.5.0-rc.3 a9adf9f`; stack `feat/mvp-c1-remove-key-flow` -> `c2-managed-launcher` -> `c3a-brand-tokens` -> `c3b-brand-strings` -> `c4-client-e2e`. C2 starts after A3 (uses pinned contract fixture until Final).
- `feat/forge-s3-member-lifecycle` and root `feat/forge-foundation` untouched.

## Open Questions

- [ ] Exact Vite/Tailwind/React pins: read from client `package-lock.json` at B1.
- [ ] Docker/owned-PG17 availability for the A2 gate (blocker -> B2 fallback).
- [ ] Whether intermediate A2-A4 branches need `MvpReadiness` locally (design: no, A5 only).
