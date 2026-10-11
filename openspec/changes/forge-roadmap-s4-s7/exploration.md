## Exploration: Forge roadmap S4–S7 (routing & budgets, images, skills & audit, packaging & pilot) + UI/interface audit

Worktree: `.worktrees/tenant-storage`, branch `feat/forge-tenant-storage`, HEAD `48c3e8e`.
Sources read: `src/forge/**`, `migrations/0001–0004`, `tests/**`, `docs/sprints.md`, `docs/changes/*`,
`odd/tasks/*`, README, original product specs PF-00…PF-12 + ADR-001…007 at
`C:/Users/JuanpabloBayona/Documents/Codex/2026-09-28/referenced-chatgpt-conversation-this-is-an/outputs/prometheon-forge/`,
upstream snapshots `work/openyak` (tag v1.5.0-rc.3) and `work/omniroute` (tag v3.8.50) in that same folder,
and Engram projects `prometheon-forge` / `forge`.

### Current State

**Implemented (all local commits, verified with real PostgreSQL 17 harness):**

| Area | Files | What it does |
|---|---|---|
| Domain bootstrap policy (S1) | `foundation.py` | Pure membership/org deny-by-default + allowlisted public bootstrap |
| HTTP transport | `api.py` | `GET /healthz`, `GET /forge/v1/bootstrap`, opt-in `POST /forge/v1/organizations/{id}/initial-administrator`; fixed redacted error envelopes |
| Entra token validation | `entra.py` | RS256 access-token validation, bounded discovery/JWKS, tenant/audience/client/scope allowlists |
| Storage / RLS | `postgres.py`, `identity_store.py`, `authorization_store.py`, `administration_store.py` | Restricted roles (`forge_runtime`, binder, `forge_designator`), RLS FORCE, catalog readiness probe |
| Authorization read model | `authorization.py` | Roles `organization_admin`, `department_manager`, `skill_reviewer`, `member`; only admin permits `members.invite/update/suspend` (no endpoints use it yet) |
| Initial admin designation | `administration.py` | Central operator designation + `initial_admin_outbox` (publication still `pending`) |
| Runtime shell | `runtime.py`, `web/status.{html,css,js}` | Loopback `/status` read-only diagnostics page; 7 fixed fields |
| Migrations | `0001`–`0004` | identities, organizations, memberships, configuration_revisions, membership_roles, initial_admin_designations, initial_admin_outbox |

~2.2k lines product source, ~4.8k lines tests (≈2:1 test:code ratio — use this for forecasts).

**NOT implemented — S2/S3 are open, not closed** (critical for "implement S4–S7"):
- S2: F09 desktop PKCE / protected token storage / live enrollment (odd/tasks/forge-identity.md:57). No Forge session, no client login.
- S3: member invite/update/suspend endpoints (F07b2/F07b3), departments/areas, policy & brand revisions + publish, discovery endpoint, last-admin/recovery policy, outbox publisher/worker.
- No departments table, no grants table, no worker process, no blob store, no secret encryption, no OpenAPI contract tests.

**Upstreams (read-only references, not vendored in this repo):**
- OpenYak v1.5.0-rc.3: Python backend + Next.js 15/React 19 frontend (Radix UI, MUI, framer-motion, next-themes, i18next) packaged with Tauri 2 (NSIS, own updater plugin, `openyak://` deep link). PF-03 explicitly plans a **fork** with Forge modules (`settings-tabs.ts`, `api/config.py`, `provider/generic_openai.py`, `provider/registry.py`, `mcp/token_store.py`, `skill/registry.py`, `tauri.conf.json`).
- OmniRoute v3.8.50 (Next.js/TS): already provides API keys with model/combo restriction (`/api/keys`), combos, usage/budget/token-limits/analytics, quota, rate-limits, pricing, compression (RTK/Caveman), skills, MCP. Known gap: Anthropic rejects OpenYak's Edit tool root `oneOf` schema through OmniRoute (Engram #2573) — blocks real chat via Claude until fixed upstream or sanitized.
- Hotel image service: `outputs/hotel-areas-0.3.0/server.mjs` (+ `chat-gateway.mjs`, `limites.mjs`) — prefix-based auth, in-memory state, hotel hardcodes; PF-07 says generalize, not reuse as-is.

**What Forge must build vs reuse:**

| Need | OmniRoute/OpenYak provides | Forge builds |
|---|---|---|
| Model routing, fallback, combos | OmniRoute combos/fallback | Per-org `router_binding`, published alias catalog (`fast`/`smart`) per role/area, capability validation |
| Per-user keys | OmniRoute `/api/keys` + restrictions | RouterAdapter, credential lifecycle state machine, encrypted secret refs, revocation outbox, reconciliation |
| Cost control | OmniRoute per-key usage/limits (second defense) | Aggregate `micro_usd` ledger: windows, atomic reservations, settlement, `BUDGET_EXHAUSTED`/`RATE_LIMITED` |
| Inference endpoint | OmniRoute `/v1/chat/completions` | Forge gateway `/v1/chat/completions`, `/v1/models` that authorizes per request + reserves + forwards stream |
| Images | hotel service (to generalize) | `/forge/v1/images/jobs` + MCP `/mcp/images`, idempotent jobs, owner auth, blob store, TTL |
| Skills | OpenYak skill registry (local) | Org skill bank: drafts, review, immutable versions, grants, signed packages, catalog |
| Audit | — | Generic `audit_events` + outbox worker, usage/audit read APIs |
| Packaging | Tauri NSIS + updater plugin | Forge client fork build, own signing key, update manifest feed, server image/compose, backup/restore runbook |

### UI / Interfaces Audit

| Interface | Owner | Stack | State |
|---|---|---|---|
| `/status` diagnostics | Forge | Vanilla HTML/CSS/JS, packaged in wheel, same-origin CSP, no CDN, no build | Exists; brand palette applied, system fonts (not Montserrat/Inter), no motion, browser proof (C10b) pending |
| Admin panel (members, areas, budgets, combos publish, images, skills review, audit, brand) | Forge (PF-11: "forge-api incluye panel") | None yet | Does not exist |
| Employee chat/client | OpenYak fork (PF-03) | Next.js/React/framer-motion/Tauri | Not started; upstream is read-only → fork lives outside this repo |
| HTTP API contracts | Forge | FastAPI | 3 routes + status; no published OpenAPI artifact / contract tests; PF-10 lists ~25 target routes |
| Pending proof pages | Forge | — | `docs/changes/runtime-status-browser-proof.md`, `odd/tasks/forge-status-proof.md` (untracked): C10b browser evidence for `/status`; still relevant as UI evidence baseline, owns live PIDs that must be cleaned by owner |

"Professional, modern UI with correct animations" can only be delivered in Forge-owned surfaces here (status + new admin panel). The employee experience requires the client fork, which is a separate repository/decision. "Verify interfaces" should also cover API contracts: freeze PF-10 error codes/envelopes and add an OpenAPI snapshot test.

### Affected Areas

- `migrations/0005+` — router_bindings, credentials, departments, budget_windows, reservations, usage_entries, image_jobs/assets, skills/skill_versions/skill_grants, audit_events/outbox.
- `src/forge/api.py` / new routers — gateway, images, skills, usage/audit endpoints; error codes from PF-10.
- `src/forge/authorization.py` — action vocabulary grows (`images.*`, `skills.*`, `usage.read`, `audit.read`, `budgets.manage`); grants with deny precedence.
- `src/forge/runtime.py` — composition of new ports, worker entrypoint, readiness for new migrations (each migration also extends the catalog probe — noticeable cost per change).
- `src/forge/web/` — admin panel assets (new) and status refresh.
- `pyproject.toml` — likely new deps: HTTP client for OmniRoute (httpx promoted from test-only), Pillow for image validation, signing library (cryptography already present).
- `scripts/` — packaging, backup/restore, OpenAPI snapshot.

### Approaches

1. **Server-first, sprint-per-change, Forge-owned vanilla admin UI** — one SDD change per sprint, Forge server + admin panel in this repo (no Node build; Web Components/ES modules, CSS transitions with `prefers-reduced-motion`), client fork deferred to S7 as separate repo.
   - Pros: fits current stack, CSP and wheel packaging; testable with unittest + real PG; no new toolchain.
   - Cons: hand-rolled UI is more work for "modern" feel; employee UX unverified until fork exists.
   - Effort: High (but incremental).
2. **Server-first + React/Vite admin SPA** — same server plan, admin panel built with a Node toolchain and served as static assets.
   - Pros: richer components/animation libs (e.g. Motion), closer to OpenYak look.
   - Cons: new toolchain, supply-chain surface, CSP/bundle review, no current Node in repo; conflicts with "no new dependencies without authorization" history.
   - Effort: High+.
3. **Client-first (fork OpenYak now)** — start PF-03 fork for login + managed provider, then server features.
   - Pros: earliest end-to-end user demo.
   - Cons: blocked by S2 PKCE/session, Edit-tool schema bug, signing decisions; violates "upstream read-only" unless a separate fork repo is approved.
   - Effort: Very High, high risk.

### Recommendation

Approach 1. Insert a **prerequisite change** that finishes the S3 gaps S4 actually depends on (departments + member lifecycle + outbox worker skeleton), then one change per sprint, plus a dedicated UI change after S4 so the admin panel has real data to show. Keep the client fork as an explicit S7 decision (separate repo), not hidden inside this repo.

**Proposed change list** (forecast uses observed ≈2:1 test:code ratio; budget 800 lines/PR incl. tests+docs):

| # | Change | Scope | Forecast (lines) | PR slices |
|---|---|---|---|---|
| 0 | `forge-s3-member-lifecycle` (prereq) | departments table+RLS, member invite/update/suspend with If-Match + audit outbox, generic outbox worker skeleton | 2,400–3,000 | 4: departments; invite; update/suspend; outbox worker |
| 1 | `forge-s4-routing-budgets` | router_binding + RouterAdapter (mock + contract tests vs OmniRoute 3.8.50), credential state machine + encrypted secret refs, alias catalog `/forge/v1/orgs/{org}/models`, budget windows (IANA tz, micro_usd), atomic reservations/settlement, RPM/concurrency, gateway `/v1/chat/completions` + `/v1/models` streaming proxy with PF-10 errors | 5,500–7,000 | 8: binding+adapter port; credential lifecycle; secret encryption; alias catalog; budget windows; reservation/settlement; rate/concurrency; streaming gateway |
| 2 | `forge-admin-ui` | Forge-owned admin panel shell (brand tokens, Montserrat/Inter bundled with licenses or system fallback, motion system with reduced-motion), members/areas/budgets/combos screens, status page refresh, browser/a11y evidence | 3,000–4,000 | 5: design system+shell; members/areas; budgets/combos; status refresh; a11y/browser proof |
| 3 | `forge-s5-image-tools` | image_jobs/assets, idempotency (key+org+member+op+hash), owner-scoped read/download, blob store `org/<uuid>/…`, MIME/pixel validation, SSRF guard, TTL purge, MCP `/mcp/images`, reservations via S4 | 3,000–3,800 | 5: jobs+idempotency; blob store+validation; provider adapter+unknown state; download/signed URLs; MCP+purge |
| 4 | `forge-s6-skills-audit` | skills/versions/grants, package validation (traversal, zip bomb, secret scan), draft backup with If-Match conflicts, review/approve/publish/rollback, signed manifests, catalog; audit_events + usage/audit read APIs with role scope | 4,500–5,500 | 7: skills schema+grants; package validator; drafts+conflicts; review/publish/rollback; signed catalog/download; audit events+outbox; usage/audit APIs |
| 5 | `forge-s7-packaging-pilot` | server container image + worker, backup/restore scripts + isolated restore test, update manifest feed with signature verification (OPS-02), runbook, pilot provisioning checklist; client fork packaging tracked separately | 1,800–2,600 (this repo) | 3–4: image/compose; backup/restore; update feed+signature; runbook/pilot |

Total ≈ 20k–26k lines ⇒ ~32 chained PRs. Each change needs its own chain strategy decision (force-chained; Feature Branch Chain recommended since behaviors must integrate before main).

Dependencies: 0 → 1 → {2, 3} → 4 → 5. Images (3) require S4 reservations; skills (4) need grants pattern from 3 and audit outbox from 0; packaging (5) needs everything plus signing decisions.

### Risks

- Asking for "all remaining sprints" while S2/S3 are open: S4 budgets need departments; gateway needs a real client session (PKCE) to be user-usable. Without change 0 and F09, S4 is backend-only.
- OmniRoute management API stability unverified (PF-05: endpoints observed, not contract-guaranteed); contract tests need a staging router of pinned version — no staging credentials authorized.
- Exact budget guarantee impossible without cost upper bound; needs a tolerance policy decision.
- Anthropic tool-schema incompatibility (#2573) blocks real Claude chat through OmniRoute.
- Windows code-signing certificate, update signing key custody, domain — not available; S7 cannot finish without them.
- Client fork of OpenYak conflicts with "upstream read-only" unless a separate fork repo is approved; Apache-2.0 notices must be preserved.
- Review load: ~32 PRs; readiness probe grows per migration (each change touches `postgres.py` catalog checks).
- Untracked `runtime-status-browser-proof.md` refers to live owned PIDs (20036/23936 + children); stale processes may exist — owner must clean up; do not delete files.
- New dependencies (httpx runtime, Pillow, signing) need explicit authorization per project history.

### Open Product Questions (need the user)

1. S2/S3 gaps: approve a prerequisite change (departments + member lifecycle + outbox worker) before S4, or accept S4 as backend-only on top of current state?
2. Employee client: approve a separate OpenYak fork repository (PF-03) for login/managed provider/skills sync, or limit scope to Forge server + admin panel in this repo?
3. Admin UI stack: vanilla ES modules/Web Components (no build, current CSP) or introduce a Node/Vite/React toolchain?
4. Budget enforcement when the cost upper bound is unknown: block (strict) or allow with an explicit overage tolerance?
5. Budget scopes for MVP: organization + area only, or also per-member caps?
6. OmniRoute topology: one dedicated instance per organization (ADR-002) confirmed for the pilot, and is a staging router + test budget authorized for contract tests?
7. Image provider for S5: which provider/model (via OmniRoute or direct), and default retention TTL?
8. Skills: who may author drafts (all members vs. granted authors) and are personal (non-corporate) skills allowed?
9. Audit retention defaults (spec proposes 90 days operational / 12 months admin) — accept?
10. S7: who owns the Windows code-signing certificate, update signing key and final domain; is the hotel pilot cutover in scope now or only staging?

### Ready for Proposal

Yes, conditionally. Recommend the orchestrator ask question 1 (prerequisite change) first, then question 2 (client fork), because they change the decomposition. Then start `forge-s3-member-lifecycle` (or `forge-s4-routing-budgets` if declined) proposal.
