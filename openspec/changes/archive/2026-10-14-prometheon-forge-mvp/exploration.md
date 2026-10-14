## Exploration: Prometheon Forge functional MVP (client + admin web + OmniRoute-backed gateway)

Date: 2026-10-11. Read-only. Control plane = `.worktrees/tenant-storage` (branch `feat/forge-s3-outbox-recording`, tip `7e4a149`, clean). Client = `clients/openyak` (separate repo, `feat/forge-client-shell`, tip `acdb53b`). Paths below are repo-relative to each repo.

MVP definition used: local end-to-end flow (a) org admin logs into admin web for one company, (b) invites/manages members, (c) configures gateway (base URL + key encrypted server-side) and publishes a model catalog, (d) member logs into rebranded Prometheon Forge client, sees only published aliases, chats with streaming through Forge backend -> gateway, no key in client, (e) tenant isolation holds. Proof gateway = local fake OpenAI-compatible server; live OmniRoute is a configurable slot.

### Current State

**Control plane already delivers most of the server side of (a)(c)(d)(e)** (owned-account auth, per-org encrypted gateway key, catalog discovery/publish, member catalog, streaming proxy) as an opt-in composition. Everything is verified with unit + real PostgreSQL 17 tests (103 tracked files in src/tests/migrations; migrations 0001-0005, 0010-0018).

Reusable pieces (control plane):
- `src/forge/account_api.py:219` `create_account_app(...)` single composition point; `:414` login, `:427` logout, `:437` invite (admin-only, needs `department_id`), `:453` accept, `:461/:472` password reset.
- `:326/:333` GET/PUT `/forge/v1/orgs/{org}/gateway` (CAS `expected_revision`, write-only `api_key`); `:354` catalogue status; `:361` refresh (discovery); `:377` publish aliases->upstream ids + default; `:386` member catalog (public aliases only, unknown capabilities); `:393` streaming chat (`text/event-stream`, `stream:true` mandatory).
- Admin gate: `account_api.py:314` `gateway_actor` + `:341` `catalog_actor` (fresh `organization_admin` snapshot, then store re-locks session+admin in-transaction); hidden as 404 for foreign orgs.
- Key custody: `src/forge/gateway_configuration.py:44` `GatewayCipher` (Fernet; ciphertext binds org/binding/revision/endpoint), `:72` `open_key` server-side only; inference `gateway_inference.py:~95` `prepare` decrypts after authz; adapters `gateway_inference_adapter.py:44` (strict SSE normalizer + private-echo guard) and `gateway_catalog_adapter.py:46` (bounded `/v1/models`).
- Tenant isolation: RLS FORCE + function-only roles (`migrations/0013..0018`), `tests/test_postgres_gateway_*.py`, `test_postgres_rls.py`.
- Bootstrap read: `src/forge/api.py:204` `GET /forge/v1/bootstrap?organization_id=`.
- Runnable composition (Windows/Docker only): `src/forge/dev_accounts_gateway.py:255` `compose_gateway`, `dev_accounts_persistent.py` (`--create/--resume/--upgrade-gateway`), `dev_accounts.py:274` `install_and_seed` (the only way an org/admin is created today). Fixed ports 3319 (UI) / 3320 (API), CORS pinned to 3319 (`dev_accounts_gateway.py:309`).
- Roles vocabulary `src/forge/authorization.py:8`; `departments`, `membership_departments`, `memberships.status` already exist (`migrations/0013`).
- Brand-ish asset precedent: `src/forge/web/status.{html,css,js}` (vanilla, packaged via `pyproject.toml` package-data, same-origin CSP).

Reusable pieces (client):
- Rebrand foundation already done in C1: `desktop-tauri/src-tauri/tauri.conf.json` productName `Prometheon Forge`, identifier `com.prometheon.forge`, updater disabled; `frontend/src/app/layout.tsx:8-9` titles; `package.json` name `prometheon-forge`.
- Central login-only path already exists and is the default mode of the managed workspace: `backend/app/provider/forge_central.py:23` `CentralGateway` (member bearer -> Forge `/models`, `/chat/completions`, strict chunk validator `:102`), `backend/app/forge_workspace_dev.py:221` `create_workspace_app` (bootstrap-gated, per-profile SQLite, chat router with no tools), `frontend/src/lib/forge-accounts.ts` (`AccountsController`), `frontend/src/components/forge/{prelogin-view,accounts-view,managed-workspace-gate}.tsx`, `frontend/src/lib/forge-workspace-session.ts`, 52 frontend spec files, `tests/test_forge_*.py`.
- Hosted-admin pieces that can be lifted into the admin web: `frontend/src/lib/forge-gateway-admin.ts` (controller: load/save/refresh/publish with retry-identical-operation) and `components/forge/gateway-admin-view.tsx`, plus invite flow in `accounts-view.tsx`.
- Brand assets verified: `Marca/Logos/*` (isotipo claro/oscuro, lockups, resumido) + manual. Extracted tokens: Azul Profundo `#0B1D26` (primary bg), Teal Profundo `#0F6B6D` (secondary), Cobre Igneo `#E07A2D` (accent, 10-15%), Arena `#E8DCC1`, Carbon `#1A1A1A` (never `#000`), grays `#6B7280`/`#E5E7EB`, error `#991B1B`. Fonts: Montserrat (titles; wordmark Montserrat ExtraBold), Inter (body). No gradients Teal->Cobre; Cobre on Teal text fails AA.

### Gaps per front

**Control plane / admin API**
1. **No identity discovery**: no `GET /accounts/me` (orgs + roles). Both admin web (org picker) and client (today org id comes from a fixture `/forge/dev/context` file) need it. Bootstrap requires the org id up front.
2. **No member/department management API**: no list members, list/create departments, suspend/reactivate (invite exists but needs a `department_id` nobody can list). S3 member-lifecycle plan (P3/P4/P6, branch `feat/forge-s3-member-lifecycle`) is unimplemented and was planned as Feature Branch Chain, 10 slices; MVP needs only a narrow subset.
3. **Gateway base URL is not configurable**: `GATEWAY_ENDPOINT='https://ia.prometheonlab.com'` constant (`gateway_configuration.py:10`), bound into ciphertext (`:62/:76`), hard URL in both adapters (`gateway_inference_adapter.py:8`, `gateway_catalog_adapter.py:58`), `GatewayResponse.endpoint: Literal[...]` (`account_api.py:58`), DB `CHECK(endpoint='https://ia.prometheonlab.com')` (`migrations/0015:18`, literal also at `:100`). Requirement (c) "OmniRoute base URL" and the local fake gateway both need this to change. Any new migration also forces a new reviewed static readiness checkpoint (`dev_accounts_gateway.py` CHECKPOINTS/PROFILE) and upgrade path.
4. **No platform provisioning**: orgs/admins exist only via `install_and_seed` on a disposable DB. Need a trusted CLI to create org + first admin + department (and a 2nd org for the isolation proof).
5. **No fake gateway** in repo (tests use `MockTransport`, labelled fixture only). Adapters are strict (single choice, `delta` keys only `role/content`, `finish_reason` then `[DONE]`), so the fake must conform exactly; it should also record received `Authorization` to prove key custody.
6. **No generic serve composition**: only Windows/Docker retained-demo launcher with fixed ports; no config-file serve, no static admin mount, CORS pinned to 3319 (PUT only in gateway compose).
7. Chat is deliberately narrow: <=16 messages, <=4096 chars each, <=16 KiB input, last role `user`, max 2048 output tokens, text only, no tools (`account_api.py:107-123`, `gateway_inference.py:15-20`). Long conversations will fail in MVP.
8. Invitation delivery is `LocalTestMailbox` (.eml files), link origin fixed `FRONTEND_ORIGIN` (`dev_accounts.py:22`). No SMTP (fine for MVP).

**Admin web** — does not exist. Only `/status` vanilla page. `forge-roadmap-s4-s7` exploration listed "admin panel" as change `forge-admin-ui`, stack undecided (open question 3).

**Client**
1. **Runtime quarantine**: `scripts/forge-isolation.mjs:3` throws unconditionally; every `npm run dev:*`/`build:*` hits it. Only the bespoke `scripts/forge-workspace-dev.mjs` (direct spawn) runs a managed workspace; `tests/forge-isolation.test.mjs` asserts the guard.
2. **Dev/fixture gating**: `fixtureContext` requires `disposable_local_fixture===true` and fixed origins (`forge-accounts.ts:33-38`, `ACCOUNTS_API/UI` `:1-2`); `CentralGateway` `ORIGIN` const `forge_central.py:18`; `ACCOUNT_ORIGIN` `forge_workspace_dev.py:25`; middleware host pinned `127.0.0.1:3331` (`middleware.ts`); ports 3331/3332 fixed (`forge-workspace-dev.mjs:42`).
3. **Manual key flow still present** (to delete): `--gateway-stdin` (`forge_workspace_dev.py:580+`, `forge-workspace-dev.mjs:63`), `provider/forge_managed.py:20` `ManagedGateway` (direct to ia.prometheonlab.com with a user-typed key), `scripts/forge-gateway-dev.ps1` (`Read-Host` key + alias prompt), client-side `GatewayAdminView` at `/forge-accounts` (admin UI inside the employee app; fixed endpoint literal `forge-gateway-admin.ts:8`).
4. **Proof gap**: managed chat is only verified with `MockTransport`; live Edge UI proof failed (cold Turbopack compile of `/c/new` >120 s, `forge-managed-workspace.md`). ODD marks W1 and W2 unchecked.
5. **Identity mismatch**: Tauri shell is wired to Entra PKCE (`entra_*.rs` ~2k lines, needs Microsoft registration); managed workspace uses owned accounts. Desktop installer is not a viable MVP target.
6. Rebrand incomplete beyond metadata (below).

### Rebrand surface inventory
271 non-binary tracked files / 1,310 case-insensitive hits for `openyak|yakagent`.
- **Visible (MVP scope)**: `components/ui/openyak-logo.tsx` (+7 usages: activity-summary, activity-panel, reasoning-part, (main)/layout, title-bar, splash), `layout/splash-screen.tsx` ("OPENYAK" wordmark, tagline), `desktop/title-bar.tsx`, `onboarding/onboarding-screen.tsx`, `public/favicon.svg`, `public/manifest.json` (OpenYak Remote), i18n en+zh `common/chat/settings.json` (~28 strings incl. "Welcome to OpenYak", greeting, about), notification titles (`permission-dialog.tsx:264`), mobile PWA pages `(mobile)/m/*` (remote-control feature; hide or rename), `app/globals.css` tokens (`--brand-primary:#339CFF` -> teal/cobre, surfaces to Azul Profundo/Carbon/Arena; light+dark themes at lines 7-36 / 157-168), fonts (Montserrat titles / Inter body; bundle via local files, no remote font service), Tauri icon set (14 files in `desktop-tauri/src-tauri/icons`, generate from isotipo), `installer-hooks.nsh`, `desktop-tauri/src-tauri/src/lib.rs:1,133,135` strings, README/FORGE docs top-level.
- **Internal (defer, low value / breakage risk)**: localStorage keys `openyak-*` (settings-store, sidebar, appearance, drafts, language), token prefixes `openyak_st_`/`openyak_rt_` (`backend.rs:782`, backend + mobile), Rust lib `openyak_desktop_lib` (`Cargo.toml:13`, `main.rs:16`), Python package/module names, `openyak-backend` dist names in macOS/linux build json, env var names, `activeProvider==="openyak"` provider id, `OpenYak-Logo/` mascot media (remove from docs, keep LICENSE/NOTICE intact), `.github/*`, CHANGELOG, 368 hits in frontend tests + 115 in evals/backend tests (selectors/fixtures; edit only assertions on visible text). Apache-2.0 attribution must remain.
- **Seam for per-company branding (design only)**: introduce `frontend/src/lib/brand.ts` (product name, wordmark, tokens as CSS variables overridable at runtime from bootstrap `brand` revision later). Do not build tenant branding now.
- Recommendation: MVP rebrand = visible strings, logos/favicon/manifest, theme tokens, fonts, Tauri icons+window/installer strings; rename only the `OpenYakLogo` component to `BrandMark`; keep all internal ids (record as tech-debt in the change).

### Approaches

**A. Admin web stack/location**
| Option | Pros | Cons | Effort |
|---|---|---|---|
| 1. New SPA `admin/` in control-plane repo: Vite + React 19 + TS + Tailwind 4, built into `src/forge/web/admin/`, served by FastAPI at `/admin` (same origin) | Same stack as client (reuse brand tokens, controller code, Playwright knowledge); same-origin = no CORS, strict CSP, one deployable; partition per company is server-enforced, UI just reflects `me` | New Node toolchain + npm registry install in this repo (no Node today); bundle review | Medium |
| 2. Vanilla ES modules + CSS, no build (like `/status`) | Zero deps, matches current CSP/wheel packaging | Hand-rolled "modern" UI/animation, weak reuse of existing TS controllers, harder component tests | Medium (slower to polish) |
| 3. Admin routes inside client Next app (existing `/forge-accounts`) | Fastest; code exists | Ships admin code to employees, couples release/tenancy, fixture-gated, defeats "partitioned admin web" | Low but wrong |

Recommend **1**; keep versions pinned to those already in the client lockfile (React 19.1, Tailwind 4.1, TS 5.7, Playwright 1.59) to minimize new supply-chain surface. Tests: Playwright (already the team's runner) + Vitest only if a unit runner is needed.

**B. Gateway base URL**
| Option | Pros | Cons | Effort |
|---|---|---|---|
| 1. Per-company URL from a deployment allow-list (migration 0019 relaxes the CHECK; `GatewayOriginPolicy`: https, or http loopback only under explicit dev profile; adapters/cipher take `origin`) | Satisfies (c) literally; SSRF-safe (no free-form URLs) | New migration => new reviewed readiness checkpoint + retained-demo upgrade; ~800 lines | Medium |
| 2. Keep fixed endpoint; deployment-level origin override via explicit composition/transport (fake gateway reached through trusted `transport=`) | No schema change, preserves "clients cannot submit origins" invariant | Admin cannot set URL (UI shows read-only), (c) only partially met | Low |

Recommend **1** in its own slice (droppable to 2 without affecting the rest).

**C. Runtime for the MVP proof**
1. Reuse `dev_accounts_persistent` (Docker owned PG, retained secrets, ports 3319/3320). Pros: already works; Cons: Windows-only, fixed ports, ceremony, CORS/origin pinned. 
2. New `forge.mvp_local`: explicit `--config <file>` composition (no env discovery, consistent with repo rule) + provisioning CLI + admin static mount, still using owned Docker PG harness for the DB. Recommend 2, delegating DB creation/migrations to existing helpers.

**D. Client delivery target**: browser-hosted local workspace (Next + Python backend, one launcher) vs Tauri installer. Recommend browser-hosted for MVP; Tauri/NSIS/Entra deferred.

### Recommendation

Control-plane stack (repo `forge`, `.worktrees/tenant-storage`), each slice <=800 lines incl. tests/docs, strict TDD:
- **A0** docs only: this exploration + proposal/spec/design/tasks for `prometheon-forge-mvp` (commit on first slice).
- **A1** Fake OmniRoute-compatible gateway (`tests/support/fake_gateway.py` + `scripts/`): `/v1/models`, `/v1/chat/completions` SSE exactly matching adapter strictness, records `Authorization`, rejects bad key; contract tests against both adapters. (~500)
- **A2** Gateway origin policy: migration 0019, cipher/adapters/store/API accept allow-listed `base_url`, readiness checkpoint, PUT body/response + tests. (~800; fallback option B2)
- **A3** `GET /forge/v1/accounts/me` + departments read/create (admin) with function-only SQL + RLS tests. (~700)
- **A4** Members list + suspend/reactivate with last-admin guard (no role edit, no department reassignment). (~800)
- **A5** Provisioning CLI + `forge.mvp_local` serve composition + admin static mount + two-org seed + launcher script. (~800)
- **A6** API-level E2E isolation proof (real PG + fake gateway): two orgs, admin A cannot read/mutate B (404), member sees only published aliases, key never appears in any response/log/stream, suspended member denied mid-stream, logout revokes. (~500)

Admin web (same repo, after A3/A4): 
- **B1** scaffold + brand tokens + shell + login + org picker + in-memory session + typed client + `/admin` mount + CSP. (~700)
- **B2** Members/departments screens (list, invite, suspend). (~700)
- **B3** Gateway + catalog screens (base URL select, write-only key, CAS revision, refresh, alias mapping, publish, status). (~800)
- **B4** Playwright E2E admin flow against launched stack + fake gateway; a11y/reduced-motion check. (~400)

Client stack (repo `clients/openyak`, parallel after A3):
- **C1** Remove manual key flow and in-client admin: `ManagedGateway`, `--gateway-stdin`, `forge-gateway-dev.ps1`, `GatewayAdminView`, related tests (net-negative lines).
- **C2** Productize managed workspace: server-discovered context via `/accounts/me` (drop `disposable_local_fixture`), configurable backend origin/ports via explicit launcher args, single official launcher (`scripts/forge-run.mjs`), replace quarantine guard with verified isolation checks, `next build && next start` option to avoid cold-compile timeouts. (~800)
- **C3a** Brand assets + tokens + fonts + icons + favicon/manifest + `brand.ts` seam. (~700)
- **C3b** Visible strings (en/zh), `BrandMark`, splash/title bar/onboarding/notifications, mobile PWA decision, assertion updates. (~700)
- **C4** Playwright E2E: member login -> only published aliases -> streamed chat through backend, assert no key/gateway URL reachable from browser. (~500)

Final: cross-repo smoke script + `docs/mvp-local.md` (control-plane repo) that boots PG, fake gateway, API+admin, client and runs both E2E suites. Order: A1 -> A2 -> A3 -> A4 -> A5 -> A6, with B1-B4 after A3/A4 and C1-C4 after A3 in parallel, then final smoke. ~15 slices, ~9-10k lines total.

**"main" for the stack.** Neither repo has a `main` (no remotes). Branches are a strictly linear chain: `5aa398b`(init) -> `4281b99` foundation -> `1e25921` api-bootstrap -> `48c3e8e` tenant-storage -> `7e4a149` s3-outbox-recording (26 commits / ~26k lines over foundation; no native review, delivered as work-unit commits before the 800 budget). Recommend creating local `main` at `7e4a149` in the control-plane repo as an adopted baseline (do not re-slice 26k lines), then `feat/mvp-a1-...` from main, each next slice stacked on the previous and retargeted to main as it lands (local fast-forward). In `clients/openyak` create `main` at `acdb53b` and keep a ref at `a9adf9f` (`upstream/v1.5.0-rc.3`) for upstream diffing. Two independent stacks with a contract pin (OpenAPI snapshot / `me` + models + chat shapes) between them. Root checkout is still on `feat/forge-foundation` (old); do not work there. Keep `feat/forge-s3-member-lifecycle` (Feature Branch Chain plan) untouched; MVP A3/A4 implement only a narrow subset, and the outbox P2 worker and P1b bridge stay deferred. This `exploration.md` is currently untracked on `feat/forge-s3-outbox-recording`; it carries over when `main` is created at the same commit.

### Risks / blocking decisions (real ones)
1. **Client quarantine lift** (blocking, needs the parent's explicit go): `forge-isolation.mjs` is a self-imposed unconditional throw guarded by tests; C2 isolation "verified" status is unresolved. MVP needs a sanctioned launch path.
2. **MVP target = local browser-hosted client with owned (email/password) accounts**, not an NSIS installer and not Entra. Confirm; Tauri+Entra+signing are post-MVP.
3. **Base URL model** (B1 vs B2 above): pick per-company allow-list (recommended) or deployment-fixed. Migration + readiness checkpoint capture needs the Docker PG harness (Docker 28.1.1 present).
4. **Authorization for registry installs** (`npm` for admin SPA; Montserrat/Inter font files): project history requires explicit approval for new deps/remote fetches. Nothing was installed here. Alternative: vanilla admin (option A2) and system-font fallback.
5. **Real OmniRoute compatibility unverified**: strict SSE parser rejects extra choice/delta keys (`reasoning_content`, `tool_calls`, usage in choices) and Anthropic tool-schema bug (#2573) exists; fake gateway proves the contract only. Live gateway stays a slot.
6. Existing durable demo may still own ports 3319/3320/3331/3332 (ODD notes PID 23940); never stop or adopt it; choose distinct ports or ask owner.
7. Client cold-compile timeouts (>120 s) broke the previous browser proof; use production build for E2E.
8. Chat narrowness (16 msgs/4 KiB) caps MVP conversation length; document as a known limit.
9. Review load: ~15 slices; A2 and A5 are the likeliest to touch 800 lines; stop and report overage rather than compress.
10. Local mailbox (`.eml`) only; invitation links need a configurable origin (admin web vs client onboarding page) - decide in design.

### Ready for Proposal
Yes, conditional on confirming decisions 1-4 (single message: lift quarantine for a productized launcher; browser-hosted owned-account MVP; allow-list base URL; authorize npm/font fetches for the admin SPA). Then proceed to `sdd-propose` for `prometheon-forge-mvp` with the slice plan above.
