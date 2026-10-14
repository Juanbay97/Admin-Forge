## Exploration: forge-v2 program (super admin, metering, capabilities+sandbox, portal+installer, production deploy)

Read-only. Paths are relative to `.worktrees/mvp` (CP = control plane, tip `feat/v1wl-v3d-openspec-artifacts` 93c49a2) or `clients/openyak` (CL, tip `feat/mvp-v1-wl-c4c-client-branding-e2e`). CodeGraph index absent for both repos; evidence gathered with grep/read.

### Current State (what exists vs gaps, per step)

**Foundations that are reusable (do not redo)**
- Authority pattern: NOLOGIN `*_authority` roles own SECURITY DEFINER functions, LOGIN `*_service` pools only EXECUTE them (`migrations/0015_gateway_configuration.sql:41-75`, `0025_org_branding.sql:11-13`). Session capability is validated inside the DB (`forge.account_validate_session`). Pools composed in `src/forge/mvp_local.py:125-172` (5 roles, `ROLES` at :35).
- Owned accounts + scrypt (`accounts.py:14-15,95`), sessions (`account_sessions.py`, table `0014:38`), one-time invitation capability hash + email-fragment link (`invitation_delivery.py:57-62`), delivery outbox with leases/3 attempts (`0014:54`, `DeliveryCoordinator` :113+), org branding + public lookup `GET /forge/v1/branding?org=slug` (`branding_api.py:204`), company code = org slug (admin shows it, 0026).
- Admin SPA: `admin/src` ~34 files / ~2.4k lines, Vite 7 + React 19.2 + Tailwind 4.2, hand-rolled components, no router/query/form lib, token in memory only (`auth/session.ts`), org-admin-only gate (`auth/access.ts:6-16`), views Overview/Members/Gateway/Catalog/Branding (`components/Console.tsx:15`). Strict CSP `style-src 'self'` (`admin_mount.py` ADMIN_CSP).
- Client (CL): purpose-built managed bridge `backend/app/forge_workspace.py` (agent `tools=[]` :348), router/pool `forge_router.py`, owned-account web flow `frontend/src/lib/forge-accounts.ts`, company-code gate + brand provider, multi-org picker. Tauri shell exists (`desktop-tauri/src-tauri`, NSIS target, `bundle.resources` backend+nodejs) but `lib.rs:41` calls `forge_build_guard::require_runtime_quarantine()` which **unconditionally panics**; Entra PKCE modules still compiled (`entra_*.rs`, lib.rs:9-12); upstream macOS signing identity remnant in `tauri.conf.json`.

**Step 1 — Super admin console: ~0% built**
- Org creation exists only as trusted CLI (`provisioning.py:1-8,95-217`; "never reachable over HTTP"); initial admin only via Entra `DeploymentOperator` (`administration.py:16`, `api.py:245`).
- No platform scope anywhere: `membership_roles.role` CHECK = organization_admin|department_manager|skill_reviewer|member (`0003:20`); `authorization.permits` is org-only (`authorization.py:42-48`).
- Gateway = ONE key per org: `organization_gateways` PK organization_id (`0015:14`), cipher AAD binds org+binding+revision (`gateway_configuration.py:81-90`); endpoint CHECK pinned to `https://ia.prometheonlab.com` or loopback (`0015`, `0019:10-13`, `gateway_origins.py:12`). Key is set by the **org admin** (`account_api.py:405-426`). Catalog selection/publication per org exists (0010-0012, 0016).
- Invitations require an existing org admin as issuer (`account_invitations.administrator_membership_id NOT NULL`, `0013:34`) → cannot issue the first-admin invitation of a new org. Existing account cannot join a second org via invite (`EXISTING_ACCOUNT_AUTH_REQUIRED`).
- No suspend-org operation (only `organizations.active` flag, no API). No MFA.

**Step 2 — Metering: 0%**
- `GatewayInference` streams normalized chunks only (`gateway_inference.py:99-202`); adapter sends `{model,messages,max_tokens,stream}` with no `stream_options` (`gateway_inference_adapter.py:59-62`) and its strict parser REJECTS the final usage chunk (`choices: []` ⇒ `len(choices)!=1` → GatewayUnavailable, :~128). `fake_gateway.py:_stream` (:105-118) never emits usage. No usage/price tables, no latency capture, no per-person data.

**Step 3 — Capabilities + sandbox: 0% (client is deliberately tool-less)**
- Inventory (from #3350, spot re-verified): `code_execute` in-process `exec()` full builtins (`CL/backend/app/tool/builtin/code_execute.py:169`); bash passes full env, validates only cwd (`bash.py:22,76`); `resolve_and_validate` no-op without workspace (`tool/workspace.py`); `web_fetch` no SSRF guard; MCP tokens plaintext JSON (`mcp/token_store.py:17-20`). 22+ tools, 25 skills, 46 connectors (43 remote), 15 plugins.
- No capability catalog / org policy / audit-log tables in CP. No runner interface, jail, egress guard.

**Step 4 — Email/portal/installer: 25%**
- `MessageDelivery` port exists but returns a file `Path` and the only adapter writes `.eml` (`invitation_delivery.py:27-30,60+`); link is `origin+'/onboarding#invitation_id&capability'` served by the CLIENT web UI, not a company portal. No SMTP. Link does not carry the company code (portal cannot brand before accept without an extra non-secret `c=<slug>`).
- Desktop: Entra not owned accounts; quarantine panic; no sidecar launch of the router (web launcher `scripts/forge-launch.mjs`/`forge_launch.py` only); CSP allows loopback only; no deep-link join; no installer hosting/manifest; `createUpdaterArtifacts:false`.

**Step 5 — Production deployment: 0%**
- No Dockerfile/compose/Caddy anywhere (`git ls-files` clean). The only runtime is the **loopback-only dev composition**: `mvp_local.py` hard-validates `database.host == 127.0.0.1`, `http://127.0.0.1:<port>` origins, `OriginPolicy(dev=True)`, `LocalTestMailbox`, binds `LOOPBACK` (:36-38,76-112,232) and `apply_guard` requires `Host == 127.0.0.1:port` (`admin_mount.py:apply_guard`). `runtime.py:31-35` refuses any `PG*` env var. Config is JSON + `secrets.json` (no env/docker secrets).
- Migrations are raw SQL scripts run once by an operator on a fresh DB (`mvp_up.install_schema` :32-41; `0001` header); no runner, no `schema_migrations`, no upgrade path; LOGIN passwords set ad hoc; every migration ripples a pinned hash (F26 in `mvp_profile.py`, `mvp_readiness.py`).
- Rate limiter process-local (single worker only), uvicorn `log_config=None, access_log=False` (no operational logs).

### Recommended architecture

**Roles / RLS (platform scope)** — Platform owner is an `owned_accounts` identity with NO membership. New migration (additive): `forge.platform_roles(account_id PK→owned_accounts, role CHECK in ('platform_owner','platform_viewer'))`, NOLOGIN `forge_platform_authority`, LOGIN `forge_platform_service` (6th pool; `ROLES`/secrets/readiness ripple). All platform operations are SECURITY DEFINER functions beginning with `platform_lock_owner(digest)` (clone of `gateway_lock_admin`, `0015:59`), then `set_config('forge.organization', …)` to reach org-scoped tables exactly like `gateway_resolve_admin` — **never BYPASSRLS, never a role that sees all rows by policy**. Platform HTTP surface mounted like `mount_branding` (`include_in_schema=False`) so the contract pin (`contract/forge-mvp.contract.json`) stays unchanged; `GET /forge/v1/platform/me` instead of widening `MeResponse`. Super-admin bootstrap = trusted operator CLI (`python -m forge.platform bootstrap-owner`) issuing a one-time set-password link (never a password, never HTTP). MFA: TOTP secret sealed with a Fernet key (reuse `GatewayCipher` style) + recovery-code hashes; session gets `mfa_level`; platform functions require it when enrolled, enrollment mandatory for `platform_owner` (default).

| Capability | Super admin | Company admin (`organization_admin`) | Member |
|---|---|---|---|
| Create/suspend company, first-admin invite | yes (platform fn) | no | no |
| Gateway keys (N per company) | owns pool + assignment; key text write-only | none (status hidden) | no |
| Model allow-list per company | sets ceiling | publishes subset within ceiling | sees published |
| Branding | edit any (audited) | edit own (kept; v1-white-label) | read |
| Members/departments | support-read only | full | self |
| Price table, global policy | yes | no | no |
| Usage | all companies/models/totals | own company per-person | own (optional) |
| Capabilities | global catalog + kill-switch | enable/disable within platform-allowed | use |

**Keys**: platform-owned `gateway_keys(id, label, origin, sealed_key, revision, status)` + `organization_gateway_keys(org, key_id, priority, weight)`; cipher AAD rebinds to `key_id` (replaces org binding); routing = priority + failover on 401/429/5xx; origin ceiling moves from DB CHECK to deployment allow-list (drop pin in migration). Existing `organization_gateways` rows migrated to keys.

**Metering**: append-only `usage_events(id, at, org, membership, model_alias, upstream_id, key_id, prompt_tokens, completion_tokens, usage_source 'gateway'|'estimated', latency_ms, ttfb_ms, status, error_code, price_id, cost_micros)` — no prompt content. `usage_daily` upsert in the same transaction (key: day, org, membership, model, key). `model_prices(upstream_id, input/output per Mtok micros, currency, effective_from, set_by)` versioned; cost snapshotted at write. Adapter adds `stream_options.include_usage`, parser accepts one terminal `choices: []` usage chunk, fake gateway emits it; when missing (cancel/revocation/old gateway) record `estimated` (chars/4) + flag in `finally`. Write path through a narrow DEFINER function on the existing gateway service pool; reads: platform fns (all) and org-scoped fn (per person). Quota hook: single `quota_check(org, membership)` call in `GatewayInference.prepare` (no-op now).

**Capabilities/sandbox**: CP tables `capability_catalog(id, kind skill|connector|tool|app, version, default_enabled, risk, manifest_sha256)`, `platform_capability_policy`, `org_capability_policy`; effective = platform_allowed ∧ org_enabled, served by an additive hidden endpoint with revision; append-only `audit_log` (actor, scope, action, target, at). Client: `ToolRunner` port (`LocalRunner` now; `RemoteRunner`/`DockerRunner` later), tool-class gating re-enabled only as layers pass. Honest sandbox finding: a Windows **Job Object limits CPU/mem/process-count/kill-on-close but does NOT restrict filesystem or network**; the escape suite's workspace-jail and egress tests will fail with Job Object + env scrub alone. To meet the "default-ON only if suite passes" rule use **AppContainer/low-IL process (no network capability, ACL-granted workspace only) + Job Object + local egress proxy for allowed fetches (SSRF/metadata/loopback/RFC1918/DNS-rebind pinned)**; Docker/WSL2 runner optional per org for bash/PowerShell. Connector secrets: org-level sealed in CP, per-user tokens sealed server-side (broker) or DPAPI on client; MCP broker = CP proxy with per-connector egress allow-list. Super-app: manifest (`id, version, publisher, entry, permissions[], sha256, signature`), sandboxed iframe on a distinct origin/custom scheme with strict CSP + typed postMessage host bridge, distribution = `capability_catalog kind=app` + org policy; build only schema + validator + empty host bridge.

**Portal/installer**: `SmtpDelivery` implements `MessageDelivery` (port return type widened to a receipt), stdlib `smtplib`, config `FORGE_SMTP_HOST/PORT/USER/PASSWORD_FILE/FROM/STARTTLS` (Resend `smtp.resend.com` 465/587, user `resend`; SES `email-smtp.<region>.amazonaws.com:587`). Link: `https://<host>/join?c=<slug>#invitation_id&capability` (fragment keeps the secret out of logs; `c` is public) → branded pre-login page (public branding endpoint) → set password → download page showing company code + `prometheon-forge://join?cp=<origin>&code=<slug>` deep link. Single unsigned NSIS installer, runtime branding by company code (user decision); installer served from `/downloads/` (Caddy volume) with `latest.json` (version, sha256, size). Desktop: delete Entra, lift quarantine behind C2 verification, spawn PyInstaller `forge-backend` sidecar in router mode, CP origin from build config/deep link, Tauri CSP allow-list = CP origin + loopback.

**Deployment**: compose services `postgres` (17, pinned digest from `scripts/postgres-image.txt`), one-shot `migrate` (new runner: `schema_migrations` + checksums + advisory lock + idempotent role passwords from secret files), `control-plane` (non-root, read-only fs, healthcheck `/status`, single worker), `caddy` (TLS, reverse proxy, `/downloads`), `backup` (nightly `pg_dump` + retention; secrets backed up separately — loss of the Fernet keys makes stored gateway keys unrecoverable). New `forge.prod_config` + `serve_prod` (env/`*_FILE` secrets, `FORGE_PUBLIC_ORIGIN`, trusted-proxy host allow-list); leave `mvp_local` untouched as the dev profile. Local: `compose.dev.yml` adds fake gateway + Mailpit + `tls internal`; agent runs Playwright against compose. JSON logs w/ request id, no tokens/PII.

### SPA evolution
One Vite SPA with role-based areas (`areas/company`, `areas/platform`, `areas/portal`), route-level lazy chunks, post-login redirect by `/platform/me` vs `/accounts/me`; shared brand/palette/api/session code. Platform area always renders the fixed Prometheon theme (company theme must never restyle the owner console); company/portal areas keep runtime branding. Stack: keep Vite/React 19/Tailwind 4; add React Router 7 (library mode), TanStack Query, react-hook-form + zod, **shadcn/ui (Radix + CVA, copy-in)** mapped onto the existing 26 brand CSS variables (`brand/tokens.css`) so white-label keeps working; lucide icons. UX: left-sidebar app shell, company switcher/command palette (⌘K) for the owner, data tables with filters, honest empty/loading/error states, toasts, destructive-action confirm dialogs, key entry as write-only field with last-4 display, charts as hand-rolled SVG/uPlot (Recharts injects `<style>` → blocked by CSP `style-src 'self'`; verify any lib against CSP). Mitigation for same-origin blast radius (public portal + owner console): in-memory token already; add optional separate host for `/platform` at the proxy layer later. Existing 158 unit/ui tests pin DOM roles: migrate page by page, keep roles/labels stable.

### Approaches (key forks)
1. **Platform scope** — (a) separate platform DB roles+functions [recommended]; (b) `platform_owner` as a membership role in a hidden "platform org" (pros: no new pool; cons: weakens tenant isolation, leaks into every org policy, anti-pattern). (a) Effort High.
2. **Keys** — (a) platform-owned pool + assignment [recommended: one OmniRoute key can serve many companies, rotation in one place]; (b) keys owned per org (matches current table, but duplicates entry and blocks rotation). Medium.
3. **SPA** — (a) one SPA, role areas [recommended]; (b) three apps (platform/company/portal): stronger isolation, 3× build/test/design-system drift. Medium vs High.
4. **Sandbox** — (a) AppContainer+Job+egress proxy local, Docker optional [recommended]; (b) Job Object only (fails escape suite); (c) server-side execution only (cost, latency, contradicts user decision). High.

### Recommended split into SDD changes (stacked-to-main, ≤800 lines/slice, strict TDD)
Sizes = authored lines incl. tests/docs; "sl" = slices. Total ≈ 58k lines / ~75 slices.

| # | Change | Repo | Size | Depends |
|---|---|---|---|---|
| 1 | `fv2-prod-runtime` prod config + migration runner + serve_prod + logs/health | CP | L 4k/5sl | — |
| 2 | `fv2-deploy-compose` Dockerfile, compose(+dev), Caddy, secrets, backup, runbook, compose smoke | CP | M 2.5k/3sl | 1 |
| 3 | `fv2-smtp-delivery` SMTP adapter, port widening, company-code link, Mailpit test | CP | S 1.2k/2sl | — |
| 4 | `fv2-platform-core` platform role/pool/CLI bootstrap, org create+first-admin invite, suspend, audit, TOTP MFA | CP | XL 6k/8sl | — |
| 5 | `fv2-gateway-keys` key pool+assignment, multi-key routing, model ceiling, org-admin key removal | CP | M 3.5k/5sl | 4 |
| 6 | `fv2-usage-metering` adapter/fake usage, events+daily+prices, estimate flag, read APIs | CP | L 4.5k/6sl | 5 (key_id), 4 |
| 7 | `fv2-web-shell` design system, router, areas, port existing pages | SPA | L 4k/5sl | — (parallel) |
| 8 | `fv2-web-platform-console` companies, keys, catalog, prices, owner dashboards | SPA | XL 5.5k/7sl | 4,5,6,7 |
| 9 | `fv2-web-company-portal` company dashboard (per-person usage), invite portal (/join), download page | SPA+CP | L 4k/5sl | 3,6,7,12 |
| 10 | `fv2-capability-governance` catalog/policy/audit tables+API, effective-policy endpoint, app manifest schema | CP | L 3.5k/5sl | 4 |
| 11 | `fv2-connector-broker` sealed secrets, MCP broker, egress allow-list | CP | L 4k/5sl | 10 |
| 12 | `fv2c-desktop-owned-auth` drop Entra, lift quarantine, sidecar router, deep link join, CP config, installer(NSIS) + hosting manifest | CL | XL 6.5k/8sl | portal contract from 9 (can start with stubs) |
| 13 | `fv2c-sandbox-runner` ToolRunner, jail, env scrub, AppContainer+Job, egress proxy, adversarial suite, tool re-enable | CL | XL 7k/9sl | — (fully parallel) |
| 14 | `fv2c-capabilities-client` effective-policy consume, defaults ON, tool gating, DPAPI vault, broker client, audit emit | CL | L 3.5k/5sl | 10,11,13 |
| 15 | `fv2c-superapp-host` manifest validator + sandboxed iframe bridge stub | CL | S 1.5k/2sl | 10 |
| 16 | `fv2-release-e2e` compose-level Playwright: owner→company→invite→Mailpit→portal→password→installer→login | both | M 2.5k/3sl | 2,9,12 |

Order/parallel tracks: Track A (CP) 1→2 ∥ 3 ∥ 4→5→6; Track W (SPA) 7 (starts now, no backend dependency) →8→9; Track C (client) 13 (starts now) ∥ 12 → 14 → 15; Track G 10→11. Critical path: 4→5→6→8→9→16. Minimum "deployable end-to-end MVP" cut: 1,2,3,4,5,6,7,8,9,12,16 with capabilities defaults shipped read-only (10,13,14 follow, tool execution stays OFF until 13 passes — consistent with the "only when suite passes" rule).

### Real decisions needed from the user
1. **Domain**: `prometeonlab.com` (typed) vs `prometheonlab.com` (OmniRoute is `ia.prometheonlab.com`; DB CHECK/`DEFAULT_ENDPOINT` hard-code the latter). Keep `FORGE_PUBLIC_HOST` configurable; confirm spelling and that 80/443 + DNS A record reach the Proxmox VM (decides Let's Encrypt HTTP-01 vs `tls internal`/DNS-01).
2. **Default-ON execution**: accept that bash/PowerShell stay opt-in (Docker/WSL runner) and only `code_execute` (AppContainer, no network) can become default-ON after the suite passes — Job Object alone cannot satisfy the stated gate.
3. Everything else defaulted: single host path-based routing, TOTP mandatory for platform owner, company admin keeps own branding but loses keys, platform-owned key pool, 1 worker.

### Risks
- Every new migration ripples the pinned schema hash (F26 → F27…) across `mvp_profile/readiness/up/local` + PG tests; budget ~150 lines per migration slice.
- Contract pin: new routes must stay `include_in_schema=False` (branding pattern) or bump the pin deliberately; the client fails closed on drift.
- Invitation model needs a schema change (platform-issued first-admin invite; existing-account-into-second-org still unsupported).
- Adapter strict parser: relaxing it for the usage chunk must not open the "unknown field" door; fuzz tests required (branding assets precedent).
- Desktop quarantine lift is gated on C2 isolation proof that is still "pending"; Tauri build/CSP never exercised; unsigned NSIS triggers SmartScreen (accepted by user).
- Single-worker limit (process-local rate limiter, 15s membership cache) caps horizontal scaling; document.
- CSP `style-src 'self'` may break chart/UI libs that inject styles.
- Pending/flaky: PG tests need Docker image digest warm; mvp-smoke had a cold-start flake; `docker` availability on the user's server is assumed.
- Keys/Fernet secrets are single points of loss → backup runbook mandatory.
- No remote operations by agents: TLS/DNS/SMTP/real OmniRoute verified only by the user.

### Ready for Proposal
Yes — start proposals for changes 1, 4, 7 and 13 in parallel (independent roots), after the user confirms the two decisions above (domain spelling/reachability; execution default).
