## Exploration: prometheon-forge-v1 (multi-user, capabilities+sandbox, white-label)

Read-only. Evidence: CP = `.worktrees/mvp` (feat/mvp-final-smoke), CL = `clients/openyak` (feat/mvp-c4-client-e2e). Paths below are relative to those roots.

### Current State

**Managed client is NOT the OpenYak app.** It is a purpose-built bridge `backend/app/forge_workspace.py` (676 lines) that re-uses only the sessions/messages/chat routers and hides everything else. The full app (`backend/app/main.py`) is source-quarantined (`main.py:5-7 require_isolation()`; `forge_runtime.py:8`).

What managed mode disables, and where:
- Agent has zero tools: `forge_workspace.py:348-349` ("No tools are available"); `ToolRegistry()` empty at `:353`; skills/plugins/connectors/FTS never created (`:354`).
- Limits: `max_steps=1`, no continuation/compaction/FTS, `max_concurrent_generations=1` (`:164-168`); prompt <=4096 chars, no attachments/format/execution_mode/surface (`:449-459`).
- Route allow-list (`forge_workspace.py:250-257`, `frontend/src/middleware.ts:4-47`); settings = "general" tab only (`settings-tabs.ts:31`); everything else 403/503 (`forge_workspace.py:642-644`).
- Why: MVP security priority (no provider keys on client, no host exec before isolation was verified). Nothing was *removed* from the codebase; it is gated.

**One profile per process (goal 1).** `ProfileStorage.bind` rejects a different (org,member) forever (`forge_workspace.py:117-120`, `selected` set at `:141`, never cleared; `close_locked` `:176-195` disposes engine but keeps `selected`). Root causes are deeper than that flag:
- Process-global singletons: `forge_runtime._paths` "once per process" (`forge_runtime.py:5-21`); `dependencies.py` module-level `_session_factory/_settings/registries` (`dependencies.py:35-239`); `ForgePaths.process_id`; `get_settings()` mutated in place (`forge_workspace.py:163-168`); `mcp/token_store.py:11` and `forge_settings.py:9` call `get_paths()`; `dependency_overrides` closed over the single `storage` (`:313-334`).
- Per-profile layout already exists: `profiles/<sha256(org,member)>/{artifacts/database/forge.db, workspace, credentials}` (`forge_paths.py:92-155`, `forge_workspace.py:127-129`). Data isolation on disk is solid; the process model is the blocker.
- Auth: bearer per request, re-validated against CP (`forge_workspace.py:396-420`, monitor `:377-394`); lock serializes all requests (`:529-533`).

**CP reusable pieces.** `migrations/0001..0023`; org-scoped RLS + service roles (0015 pattern); Fernet sealed, record-bound secrets `src/forge/gateway_configuration.py:48-140`; per-change audit tables (`gateway_configuration_audit` 0015:23, `account_enrollment_audit` 0013:63); outbox (0005, `outbox.py`); `configuration_revisions` (0001) / `OrganizationConfiguration.revision` (`foundation.py:44`) feeding `config_revision` in bootstrap; strict contract pin (`contract.py`, `contract/forge-mvp.contract.json`, F20-F23 fingerprint gates); admin mount with strict CSP (`admin_mount.py:15-16`).

### OpenYak capability inventory (what ships; all in `backend/app`)

| Class | Where | Count / notes | Risk today |
|---|---|---|---|
| Built-in tools | `main.py:548-596`, `tool/builtin/*` | read, write, edit, apply_patch, bash, code_execute, glob, grep, question, todo, task, swarm, web_fetch, web_search, plan, submit_plan, artifact, present_file, skill, search(FTS), computer, browser | see below |
| Skills | `data/skills/` (25), loader `skill/registry.py`, install-from-store `api/skills.py:266` | docx/pdf/pptx/xlsx/webapp-testing/mcp-builder/skill-creator/github-deep-research have `scripts/` run via bash | store install = remote code |
| Plugins | `data/plugins/` (15 verticals: sales, legal, finance, HR, eng...), `plugin/{loader,manager,parser}.py`, `main.py:359-391` | skills+agents+MCP bundles | bring MCP stdio commands |
| Connectors | `data/connectors.json` (46: 43 remote HTTP/OAuth, 3 local stdio: google-workspace, ms365, pubmed), `connector/registry.py` | custom connector registration `registry.py:119`; `POST /connectors` `api/connectors.py:90` | custom stdio = arbitrary host exec |
| MCP | `mcp/client.py:75-96` (stdio spawn `uvx/npx`), `mcp/oauth.py`, `mcp/token_store.py` | tokens in **plaintext JSON** (`token_store.py:20` says so); Google client secret in settings.json (`forge_settings.py:22-24`) | secrets on disk |
| Providers | BYOK 20+, Ollama, rapid-mlx, OpenAI OAuth, custom endpoints `main.py:134-333` | unneeded in managed (central gateway) | keep OFF |
| Channels | `channels/*` (telegram, discord, slack, email, feishu, matrix, wecom, weixin, whatsapp, dingtalk, qq, mochat, websocket) `main.py:450+` | inbound exposure | keep OFF v1 |
| Remote/tunnel | `api/remote.py`, `auth/tunnel.py`, `main.py:429` | exposes backend publicly | keep OFF |
| Automations | `scheduler/*`, `api/automations.py`, `main.py:444` | unattended execution | later, as own capability |
| Computer/Browser use | `tool/builtin/computer.py`, `browser.py`, `computer_runtime/{windows,macos}.py` | whole-desktop control | OFF v1 (cannot be jailed on host) |
| Memory/Files/Artifacts | `memory/*`, `api/files.py`, `api/artifacts.py`, `api/workspace_memory.py` | per-profile DB | fine once per-profile process |
| Permission engine | `agent/permission.py` (allow/deny/ask, last-match-wins, 4 layers), session-level `permission_rules` | reusable as the enforcement point for org policy |  |

**Sandbox reality check (the headline finding):**
- `code_execute` = in-process `exec()` with full `__builtins__` inside the backend interpreter (`tool/builtin/code_execute.py:157-169`). It can read the process memory/env (session bearer in `storage.token`, DB, other files). Zero isolation; the 120s timeout cannot kill the thread.
- `bash` = `subprocess.run(..., env={**os.environ})` (`bash.py:99-108`): full host env leak; only `cwd` is validated (`tool/workspace.py:93-115`), the command itself is unconstrained (`cd ..`, absolute paths, network).
- `resolve_and_validate` is a no-op when `workspace` is falsy (`workspace.py:35-36`); `read.py:243-244` falls back to any absolute path for "attachments"; resolve()+relative_to is TOCTOU-prone and does not reject junctions/reparse points (forge_paths.py does, but tools do not use it).
- `web_fetch` follows redirects with no private-IP/metadata block (`web_fetch.py:56-57`).
- MCP stdio spawn uses user-supplied command (`mcp/client.py:76-92`).
- Threat model note: on a local desktop deployment the employee owns the machine, so tool policy is a guardrail against prompt-injected/LLM-misbehaving actions and accidents, not a boundary against the employee. Anything that must hold against the employee (secrets, quotas, audit, model access) must live server-side. The sandbox protects the machine/company data from the *model*.

### Goal 1 - Multi-user: approaches

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| A. Multiplex profiles inside one process (dict of ProfileStorage + contextvar) | one process, low RAM | requires un-globalising paths/settings/registries/dependencies in an upstream fork (merge debt, high leak risk), tool execution shares an address space | High / risky |
| **B. Supervisor + one backend process per profile (recommended)** | reuses "once-per-process" design unchanged; hard isolation of memory/paths/settings; per-process OS limits (Job Object) or container; idle reaping; same shape works desktop and server | ~150-300 MB per active profile; spawn latency; needs a front router | Medium |
| C. Restart on switch (today) | zero work | not multi-user | none |

Recommendation B: a small router (Python ASGI, loopback) in front of the UI: validates bearer against CP (`/accounts/me` + `/bootstrap`), derives (org,member), lazily spawns/reuses `app.forge_workspace`-style worker with `--profile` args and own port (random loopback) + per-process token, reaps on logout/suspension/idle, serializes only per-profile. The existing worker keeps its one-profile invariant as defence in depth (it is the 403 today). Frontend needs account/org switcher (`/accounts/me` already lists orgs, `validated_me` `forge_workspace.py:218`).
Server deployment: same router, workers become containers (see goal 2 runner). Per-user quotas (disk, sessions) enforced here.
Fold in: **suspension revokes all sessions** - account sessions are account-scoped (`0023`), so suspending in org A logs the user out of org B. Fix: revoke only when the account has no other active membership, relying on per-request membership checks (client already revalidates `bootstrap` every 15 s `forge_workspace.py:381`, and CP org endpoints check membership) - verify every org-scoped route checks status before dropping revocation.

### Goal 2 - Capability governance + layered sandbox

**Governance model (CP):**
- New table `forge.org_capabilities` (org_id, capability_id, kind in {tool,skill,plugin,connector,feature}, state allow|deny, params jsonb, revision) + `org_capability_scopes` (role/department/membership overrides; narrower may only *reduce* unless admin flags explicit grant) + audit table (pattern 0015/0013). Default deny: no row = denied. Catalog of known capability ids ships with CP (generated from `data/*`, version-pinned, hash-pinned artefacts).
- Resolved server-side into an **effective policy** document per member: new endpoint `GET /forge/v1/orgs/{o}/capabilities/effective` (additive; do NOT widen `bootstrap`, whose exact-key shape is pinned `forge_profile.py:82-95` + contract hash). Include `policy_revision`, signed (HMAC/Ed25519 by CP) so a worker can refuse tampered local cache; admin SPA gets Capabilities page (like Catalog.tsx publish flow: draft -> publish revision).
- Client enforcement: effective policy -> (1) tool registry filter (only allowed ids registered, replaces `ToolRegistry()` empty at `forge_workspace.py:353`), (2) `Ruleset` fed into existing `agent/permission.py` with `ask` for risky classes, (3) skills/plugins/connectors registries load only allowed ids, (4) route allow-list in `forge_workspace.persistence_operation` / middleware.ts expanded per capability. Revalidated on the same 15 s monitor via `policy_revision`.
- Per-user "enable" = user toggles within allowed set (stored in profile settings); per-user/department override is an admin-side scope, not a client setting.
- Audit: CP `capability_audit` (admin changes: who/when/before->after) + client-reported tool-invocation events (tool id, outcome, duration, byte counts; no content by default) batched to CP via outbox-like endpoint; admin Audit page. Content logging off by default (privacy).

**Secrets:**
- Org-level shared connector credentials / search API key / OAuth client secrets: server-side only, reuse `GatewayCipher` sealed+bound pattern (`gateway_configuration.py:61-110`) -> `org_connector_secrets`.
- Preferred for the 43 remote HTTP connectors: **CP-side MCP broker** (`/forge/v1/orgs/{o}/mcp/{connector}` proxies, injects credentials, applies egress allow-list and audit). Secrets never reach laptops; central kill switch. Cost: CP becomes a streaming proxy (need OAuth redirect URIs on a public CP; out of loopback MVP -> use local fixtures for tests, as agreed).
- Per-user OAuth tokens that cannot be brokered (local stdio servers: google-workspace, ms365, pubmed): encrypted at rest (Windows DPAPI via existing "protected storage" work noted in FORGE_DEVELOPMENT.md; OS keyring elsewhere), replacing plaintext `mcp-tokens.json` (`token_store.py`) and settings.json secrets.

**Sandbox: feasibility (this host: Windows 11 Pro, Docker Desktop 28.1 w/ WSL2 present):**

| Mechanism | Windows local | Linux server | Verdict |
|---|---|---|---|
| Path jail in tools (realpath + reject reparse points, workspace mandatory) | yes, pure Python | yes | L1 mandatory, necessary but not sufficient |
| Out-of-process exec (subprocess, clean env allow-list, cwd jail, timeout, output cap) | yes | yes | L2 mandatory; kills code_execute in-process hole |
| Windows Job Object (mem/CPU time/process count, kill-on-close) | yes (ctypes/pywin32, no admin) | n/a (cgroups/rlimit) | L2 resource limits |
| Restricted token / Low integrity level | possible, fiddly with Python site-packages ACLs | n/a | optional hardening |
| AppContainer (no network capability, FS ACL grant on workspace only) | strongest native, but complex (grant ACLs to interpreter, quirks with child tooling) | n/a | spike, not v1 critical path |
| Windows Sandbox | Pro/Enterprise only, one VM per run, not scriptable per-command | n/a | reject |
| Docker/WSL2 container (`--network none/proxy`, `--read-only`, `--cap-drop ALL`, `--pids-limit`, `--memory`, user, bind-mount only workspace) | works here; needs Docker Desktop (licensing >250 staff, admin install) | yes (gVisor/Kata upgrade) | optional "hardened runner" tier; default for server |
| bubblewrap/nsjail/landlock+seccomp | n/a | yes, lightweight | server alternative to Docker |
| Egress control | Windows Firewall per-program rules need admin; soft proxy env bypassable | iptables/network ns/container net | hard only in container/AppContainer; elsewhere app-level policy |

**Recommended pragmatic layers for v1** (each tool class is enabled only when its layers exist):
1. L0 Policy: org allow-list (above), default deny.
2. L1 Data isolation: per-profile process + `ForgePaths` (exists) + env scrub (children get explicit minimal env, never `os.environ`, never the bearer).
3. L2 FS jail: single `WorkspaceJail` used by every file tool; workspace mandatory; reject reparse points/symlinks; per-profile quota; replace `resolve_and_validate` no-op branch.
4. L3 Exec runner interface `Runner.run(cmd|code, workspace, limits)`: v1 implementations `LocalProcessRunner` (subprocess + Job Object / rlimit, clean env, timeout, kill tree) and `ContainerRunner` (Docker, opt-in per org, mandatory on server). `code_execute` rewritten to spawn `python -I` in the runner. `bash` runs only through the runner.
5. L4 Network: `web_fetch/web_search` through one egress guard (scheme allow, DNS-resolve then block loopback/RFC1918/link-local/metadata, redirect re-check, per-org domain allow-list); container runner `--network none` by default.
6. L5 Connectors: stdio MCP only from curated catalog, spawned through the runner with scrubbed env; no custom stdio commands, no skill-store installs for members (admin-curated bundles only); remote connectors through the broker.
7. L6 Audit + kill switch: policy_revision revocation within one monitor interval.
Enablement order: read/glob/grep/todo/skill/artifact (L0-L1-L2) -> write/edit/apply_patch -> web_fetch/search (L4) -> bash/code_execute + script skills (L3) -> remote connectors via broker (L5) -> local stdio connectors/plugins -> subagents (task/swarm, inherit policy). OFF for v1: computer, browser use, channels, remote/tunnel, BYOK/Ollama/OAuth providers, automations (later).

### Goal 3 - White-label

Existing: admin `src/brand/theme.ts` (BrandTheme + `createTheme` overrides + `applyBrandTheme` CSS vars, `tokens.css`), `tests/unit/theme.spec.ts`; client `src/theme/forge-theme.ts` (`ForgeTheme` light/dark, `applyTheme` injects `<style id=forge-theme-overrides>`), `src/theme/brand.ts` (name + 4 image paths), fonts self-hosted (public/fonts), Tauri `productName`/`title` in `desktop-tauri/src-tauri/tauri.conf.json`. Admin CSP is strict, no inline (`admin_mount.py:15`). **Client has no CSP** (`next.config.ts` has none); `applyTheme` writes `style.textContent` from raw strings = CSS-injection if values come from a server => must validate.
Gaps: no branding storage/API; no pre-login org discovery (client learns orgs only after login via `/accounts/me`); no asset upload/serve; no live-preview editor; admin dist is org-agnostic; client branding compiled (`brand.ts`).

Recommended:
- Storage: `forge.organization_branding` (org_id PK, revision, theme jsonb, assets refs, login_copy, updated_by) + `branding_assets` (org_id, kind logo_light|logo_dark|favicon|wordmark, sha256, bytes bytea or object store key, content_type) with RLS + audit + revision, same migration pattern.
- Validation (server AND client re-validate): colors `#RRGGBB`/`#RRGGBBAA` regex only; contrast check (WCAG AA for text/brand pairs, reject otherwise); fonts = choice from a vetted self-hosted list (no arbitrary font URLs v1; custom woff2 upload later with magic-byte check, <=300 KB); product name <=40 chars, plain text; login copy <=280 chars plain text (React-escaped, no HTML/markdown links).
- Assets: PNG/WebP/ICO only (no SVG v1; optionally server-side rasterise/sanitise later), magic bytes + decoded dimensions (<=1024x1024, <=256 KB), re-encode to strip metadata, content-addressed URL `/forge/v1/branding/assets/{sha256}` with `Cache-Control: immutable`, `X-Content-Type-Options: nosniff`; both CSPs add that single origin to `img-src` (admin `img-src 'self'` already works because same origin).
- Delivery: public unauthenticated `GET /forge/v1/branding?org=<slug>` (slug-resolved; returns only theme+asset URLs+name+login copy, rate-limited, ETag by revision, no org existence oracle beyond slug) for pre-login; authenticated post-login revision rides existing `config_revision` bump (client refetches branding when it changes). Admin: same endpoint by Host/slug (`/admin/?org=slug` or `/admin/<slug>/` v1; custom domains later).
- Appliers: admin `createTheme`->`applyBrandTheme` (extend theme.ts with name/asset URLs/favicon/title); client `ForgeTheme` mapped from a compact brand input (primary, accent, surface tint, font) via a deterministic palette generator -> full `ThemeColors` light/dark (admins edit 3-5 knobs, not 27 vars); apply via CSS variables with `style.setProperty` (not raw `textContent`) and add a client CSP.
- Editor: admin Branding page with live preview pane (render the real theme into an isolated preview container using the same appliers + sample chat/login mock), draft -> save revision -> publish; reset to default.
- Client pre-login: first launch asks company code (slug) or email domain -> fetch branding; cache last branding in `presentation/` dir (`ForgePaths.presentation_directory` `forge_paths.py:108`, already designed for "prelogin display preferences only"). Tauri window title/icons are build-time: the single installer stays "Prometheon Forge" until runtime sets title via Tauri API (`setTitle`); per-company icons require per-company builds (out of v1).

### MVP warnings to fold in
1. `test_postgres_directory.py` flake: likely cause (hypothesis from reading, not reproduced): roles are cluster-global while the module drops/creates them (`forge_directory_authority`) in `separate_database()` cleanup (`test_postgres_gateway_origin.separate_database`, ROLES loop) and in `tearDownClass` `DROP ROLE` (line ~175, no IF EXISTS) while the shared-fixture database still depends on them -> "role cannot be dropped / already exists" depending on class order and leftover state after killed runs. Fix: unique role suffix per run or drop DB before role; reproduce first with `-v` in a 6x loop capturing stderr.
2. Downgrade clause: add a forward-only guard migration/`forge.assert_downgrade_safe()` function + test, or edit the spec to state "forward-only; manual precondition". Cheapest honest option: amend spec + add a pre-check script `scripts/check-downgrade.sql` tested.
3. `next build` dirtying `frontend/next-env.d.ts` + `tsconfig.json`: add `next-env.d.ts` to `.gitignore` (Next's recommendation) and commit tsconfig exactly as Next rewrites it (idempotent build), then assert clean tree in smoke script.
4. Suspension revokes all sessions: see goal 1.
5. Tauri: `tauri.conf.json` title/productName already "Prometheon Forge"; `src-tauri/icons/` still ships upstream OpenYak artwork (verify files; dir `OpenYak logo`, `icon.ico`, tray templates) and the Rust build is guard-quarantined (`forge_build_guard.rs`). Replace icons with Forge art; runtime title from branding (goal 3).

### Risks
- Un-globalising the OpenYak fork (approach A) is a trap; B keeps upstream merge debt small.
- Sandbox claims must be tested adversarially (escape tests: `..`, junction, absolute paths, env dump, loopback/metadata fetch, fork bomb, huge output); do not ship `bash/code_execute` before L3 tests pass.
- Windows AppContainer/Job Object code is ctypes-heavy, hard to test in CI; keep behind the Runner interface.
- Exact-key contract pins (bootstrap shape, contract hash, F-fingerprint gates) make every CP schema change a coordinated CP+client change; keep new endpoints additive.
- Remote connectors need public OAuth callbacks and provider app registrations; tests must use local fixtures (agreed: no live remote connectors without authorization).
- Public branding endpoint = unauthenticated surface: rate limit, size cap, no PII.
- Upstream licence (Apache 2.0) attribution must be preserved when white-labelling OpenYak assets.

### Real product decisions (only these need the user)
1. **Where do tools execute in v1?** Employee machine (desktop, local runner; default recommended, interface ready for server) vs hosted per-company workspaces (containers; needs infra + storage design).
2. **Client distribution for white-label:** one signed installer with runtime branding by company code (recommended default) vs per-company builds (own icon/installer name).
3. **Hardened tier requirement:** may customers be required to have Docker/WSL2 for bash/code_execute? Default: optional per-org; without it, those two tools stay off unless LocalProcessRunner passes the adversarial suite on the target OS.
(Defaults assumed for the rest: multi-tenant slug-based admin (no custom domains v1); members cannot install skills/plugins/custom MCP; computer/browser/channels/remote/automations/BYOK stay off; audit stores metadata not content; SVG not allowed.)

### Recommended split (stacked-to-main, 800 lines/slice)

| # | Change | Scope | Size | Depends |
|---|---|---|---|---|
| 1 | `v1-multiuser` | supervisor/router + per-profile worker, org switcher, logout/reap, scoped session revocation, fold-ins (flake, downgrade clause, next-env, Tauri icons) | ~3.5k, 5-6 slices | - |
| 2 | `v1-white-label` | branding tables+API+assets, admin editor w/ preview, client runtime theme + CSP, pre-login by slug | ~3k, 4 slices | independent of 1 (can run parallel) |
| 3 | `v1-capability-governance` | org capability tables, effective-policy endpoint, admin page, client registry/permission enforcement, audit (enable file/read tools first) | ~3k, 4 slices | 1 |
| 4 | `v1-exec-sandbox` | WorkspaceJail, Runner (local + container), egress guard, move code_execute out of process, adversarial test suite; enable write/web/bash/code_execute | ~3k, 4 slices | 3 |
| 5 | `v1-connectors-secrets` | sealed org secrets, MCP broker, DPAPI token store, curated skills/plugins/connectors enablement | ~3k, 4 slices | 3,4 |
Order: 1 -> (2 parallel) -> 3 -> 4 -> 5. Total ~15-16k lines.

### Ready for Proposal
Yes for change 1 and 2 immediately (no open product decision blocks them). Changes 3-5 need decisions 1-3 above before design (defaults may be accepted).
