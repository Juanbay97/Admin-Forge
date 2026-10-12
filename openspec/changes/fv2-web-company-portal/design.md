# Design: fv2-web-company-portal

## Technical Approach

Fill the `company` and `portal` area manifests registered by `fv2-web-shell`. Company dashboard and member usage share one `usage` API module and the shell chart kit.
The member journey is a public route group (`/admin/join`) outside `RequireSession`, a signed-in portal group inside it. Small, test-covered control-plane additions host
the installer and normalise the invitation URL. Spec refs: `company-dashboard`, `member-onboarding`, `member-download-usage`.

## Architecture Decisions

### Decision: Join page as an isolated public route with in-memory capability
**Choice**: `useInvitationFragment()` reads `location.hash` once (lazy `useState` initialiser), calls `history.replaceState(null,'',pathname+search)`, keeps `{invitationId, capability}`
in a ref/state; submit uses them; unmount clears. **Alternatives**: keep hash in URL (leaks into history/screenshots); sessionStorage (persists secret).
**Rationale**: matches the fragment design in `invitation_delivery.py` (secret never hits server logs) and removes the remaining browser-side exposure; test asserts `location.hash === ""` and no storage keys.

### Decision: Branding before form, bounded wait
`usePublicBranding(slug)` resolves `GET /forge/v1/branding?org=<slug>` (existing client `api/branding.ts`), applies through `applyBrandTheme`; UI shows a skeleton up to
800 ms, then falls back to Prometheon (and re-themes if branding arrives late). Unknown slug ⇒ default theme, no error.

### Decision: Auto sign-in after accept
Accept returns no token. Preferred: additive `account_email` in the accept response, then `POST /accounts/login` with the chosen password (never stored). Fallback if absent:
the page asks for email once (prefilled hint from nothing). **Alternative**: server returns token on accept (rejected: widens the one-time capability's authority and changes the pinned contract more).

### Decision: Installer hosting via CP static mount + manifest
`mount_downloads(app, directory)` in a new `downloads_mount.py` mirroring `_file` traversal rules; in production Caddy (change 2) serves `/downloads` first, the CP mount is the
local/dev/e2e implementation and a safe fallback. Page fetches `/downloads/latest.json` (same-origin, `connect-src 'self'`); download is a plain `<a href download>` navigation.
**Alternative**: API endpoint returning the URL (extra auth surface, no benefit).

### Decision: Role home
`homeFor(identity)` from shell: platform > company(admin) > portal. Portal routes require only an account with ≥1 org membership; usage endpoints use the member's own org id
(`organizations[0]`, picker if several, same switcher as company area).

### Decision: Read-only Gateway page
Existing form removed; component renders contract PC-6 fields only. No secret inputs remain in the bundle for company area (test greps DOM for `type=password` on page).

## Data Flow

    Email link /join?c=acme#invitation_id&capability
        └─(CP 307 /admin/join, query kept)→ SPA /admin/join
           → scrub hash → GET /forge/v1/branding?org=acme → themed page
           → POST /accounts/invitations/accept → POST /accounts/login → session.set
           → /portal/download → GET /downloads/latest.json → installer link + code + deep link
    Member: /portal/usage → GET /orgs/{id}/usage/me?days
    Admin:  /company/dashboard → GET /orgs/{id}/usage?days&group=member|day|model ; /company/gateway → GET /orgs/{id}/gateway

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `admin/src/api/{usage,downloads,invitations}.ts` | Create | zod clients (usage org/me, manifest, accept + errors) |
| `admin/src/areas/company/dashboard/*` | Create | KPIs, charts, PersonTable |
| `admin/src/areas/company/members/*` | Modify | department filter, Departments tab |
| `admin/src/areas/company/gateway/Gateway.tsx` | Modify | read-only status |
| `admin/src/areas/portal/{manifest.ts,Home,Download,Usage}.tsx` | Create | portal pages |
| `admin/src/areas/portal/join/{Join,useInvitationFragment,usePublicBranding,errors}.tsx` | Create | onboarding |
| `admin/tests/fixtures/{usage,downloads,invitations}/*.json` | Create | contract fixtures |
| `admin/tests/unit/*` | Create | fragment parser, usage schemas, share/delta math, manifest picking, password policy hints |
| `admin/tests/ui/{dashboard,join,download,member-usage,company-gating}.spec.ts` | Create | mocked UI |
| `admin/e2e/{company-dashboard,portal-journey}.spec.ts` | Create | real stack |
| `src/forge/downloads_mount.py` | Create | traversal-safe static `/downloads` |
| `src/forge/admin_mount.py` | Modify | `GET /join` → 307 `/admin/join` |
| `src/forge/account_api.py` | Modify | accept response `account_email` (additive) |
| `src/forge/mvp_local.py` (composition) | Modify | pass downloads dir; e2e fixture installer |
| `tests/test_downloads_mount.py`, `tests/test_join_redirect.py` | Create | pytest (traversal, headers, redirect, additive field) |
| `scripts/admin-e2e.ps1` | Modify | create downloads dir + fixture `latest.json`, read invitation .eml |

## Interfaces / Contracts

```ts
export const UsageTotals = z.object({ tokens: z.number().int(), cost_micros: z.number().int(), requests: z.number().int() });
export const MemberUsage = z.object({ member_id: z.string(), display_name: z.string(), department: z.string().nullable(),
  tokens: z.number().int(), cost_micros: z.number().int(), last_active: z.string().nullable() });
export const OrgUsage = z.object({ totals: UsageTotals, previous: UsageTotals, series: z.array(DayPoint), members: z.array(MemberUsage), models: z.array(ModelShare) });
export const InstallerManifest = z.object({ version: z.string(), released_at: z.string(),
  platforms: z.object({ windows: z.object({ url: z.string().startsWith("/downloads/"), sha256: z.string().regex(/^[a-f0-9]{64}$/), size_bytes: z.number().int() }).optional() }) });
export type JoinState = "loading" | "ready" | "expired" | "used" | "invalid" | "missing" | "existing_account" | "offline";
```
The manifest `url` MUST be same-origin path (schema-enforced; also CSP-safe for navigation).

## Testing Strategy (strict TDD)

| Layer | What | Approach |
|-------|------|----------|
| Unit | fragment parse/scrub (pure fn + `replaceState` spy), error-code→JoinState, usage/manifest schemas vs fixtures, share/delta math, password hints | RED first |
| Python | downloads traversal (`..`, `%2e%2e`, backslash, symlink), `nosniff`/cache headers, 404 outside root, redirect keeps query, accept additive field and pin tests untouched | pytest |
| UI (mocked) | dashboard states + sorting + multi-org switch; join (branded, each error, policy error, double submit, hash scrub, signed-in visitor); download (available/missing/deep link/OS); usage; gating redirects; axe/CSP/viewports | `page.route` |
| e2e (real stack) | admin dashboard shows seeded usage; invite → .eml link → join → password → login → download page → my usage; gateway read-only | `admin-e2e.ps1`, system Chrome |

## Migration / Rollout
Order: CP additions (S1) first, safe alone. SPA pages ship behind role gating. Feature works with stubs before `fv2c-desktop-owned-auth` publishes an installer ("not published yet" state).
`fv2-release-e2e` re-runs the same journey against compose + Mailpit.

## Open Questions
- [ ] Does `fv2-smtp-delivery` emit `/admin/join` or `/join`? (redirect makes both work; drop redirect if the former.)
- [ ] Is cost visible to members (PC-5) or tokens only? (default: tokens only unless contract exposes cost.)
- [ ] Member department assignment endpoint exists? (PC-9; else read-only.)
