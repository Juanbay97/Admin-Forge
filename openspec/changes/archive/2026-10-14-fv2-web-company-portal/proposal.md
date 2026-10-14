# Proposal: fv2-web-company-portal (company admin dashboard + member portal)

> Change 9 of the forge-v2 program. Track W after `fv2-web-shell` (#7). Depends on `fv2-usage-metering` (6, usage endpoints) and
> `fv2-smtp-delivery` (3, invitation link) and, for a real installer, `fv2c-desktop-owned-auth` (12, artifact + manifest; stubbed until then).
> Small CP piece included (static `/downloads`, `/join` redirect). Source: Engram #3371, #3369.

## Intent

The invitation email must lead to a branded company portal where the new employee sets a password, downloads the installer and sees their own
usage; and company admins need a dashboard with per-person usage plus members/departments/branding and a read-only gateway status (keys are now
platform-managed). This replaces today's flow where the link opens the *client* web UI.

## Scope

### In Scope
- **Company area** (`/admin/company/*`, branded): Dashboard (org KPIs, usage series, per-person table/bars, per-model share, range), Members + Departments
  (existing, enhanced: assign department, filter), Branding (existing), Gateway **read-only** status (assigned keys last-4 count, model allow-list, ceiling, health).
- **Member portal** (`/admin/portal/*`, branded): public `/admin/join` (invitation accept → set password → auto sign-in), Download page (company code,
  installer download from manifest, sha256, deep link `prometheon-forge://join?cp=<origin>&code=<slug>`, instructions), My usage (KPIs, daily chart, per-model).
- Branded pre-login: company code `c` from the link resolves public branding (`GET /forge/v1/branding?org=<slug>`) before any auth.
- Small control-plane additions: `mount_downloads` (static `/downloads/*`, `latest.json`), `/join` → `/admin/join` redirect keeping query+fragment, accept response additive `account_email`.
- Playwright e2e on the real stack for each area; axe/CSP/responsive gates.

### Out of Scope
- SMTP sending and installer building/hosting in production (changes 3, 12, 2); desktop deep-link handler (12).
- Org-admin key entry (removed by gateway-keys; page becomes read-only), capability governance (10), per-user billing.
- Password reset UI beyond linking the existing reset flow; MFA for company users.

## Capabilities

### New Capabilities
- `company-dashboard`: org usage dashboard with per-person usage, departments management, read-only gateway status.
- `member-onboarding`: branded join flow (accept invitation, set password, sign-in), error/expired/used states, existing-account path.
- `member-download-usage`: download page (manifest, deep link, instructions) and member's own usage.

### Modified Capabilities
- `admin-app-shell` (fv2-web-shell): registers company/portal manifests and public `/join` route (no requirement change).
- Gateway admin page behaviour: key entry removed (aligned with `fv2-gateway-keys`).

## Approach

Reuse shell kit/charts/Query. `join` parses the fragment (`#invitation_id=…&capability=…`) on first render into memory, immediately
`history.replaceState` to drop it from the URL, never logs/stores it. Public branding is applied with the existing `applyBrandTheme` before the form
shows (no flash of default theme: skeleton until resolved, fallback to Prometheon if unknown/slow). After accept the SPA signs in (email from
`account_email` or user input fallback) and routes to `/portal/download`. Usage endpoints are typed zod modules with fixtures; the manifest is
fetched same-origin (`connect-src 'self'`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `admin/src/areas/company/**` | Modified/New | dashboard, departments, gateway read-only |
| `admin/src/areas/portal/**` | New | join, download, my usage |
| `admin/src/api/{usage,downloads,invitations}.ts` | New | zod clients |
| `src/forge/admin_mount.py` (+ new `downloads_mount.py`) | Modified/New | `/downloads`, `/join` redirect; tests in `tests/` |
| `src/forge/account_api.py` | Modified | accept response `account_email` (additive; contract pin impact checked) |
| `admin/tests/**`, `admin/e2e/**`, `scripts/admin-e2e.ps1` | New/Modified | UI + real-stack journeys |

## Contract (assumptions)

| ID | Endpoint / behaviour | Owner |
|----|----------------------|-------|
| PC-1 | Invitation link = `https://<host>/admin/join?c=<slug>#invitation_id=…&capability=…` (or `/join?…` redirected here) | smtp-delivery / this |
| PC-2 | `GET /forge/v1/branding?org=<slug>` public (exists) → branding + assets; unknown slug → 404 | exists |
| PC-3 | `POST /forge/v1/accounts/invitations/accept {invitation_id, capability, password}` (exists) → add `account_email`; errors: `INVITATION_INVALID|EXPIRED|USED`, `EXISTING_ACCOUNT_AUTH_REQUIRED`, `PASSWORD_POLICY` | this (additive) + existing |
| PC-4 | `GET /forge/v1/orgs/{id}/usage?days&group=member|day|model` (org admin) → `{totals, series[], members[{member_id, display_name, department, tokens, cost_micros, last_active}], models[]}` | usage-metering |
| PC-5 | `GET /forge/v1/orgs/{id}/usage/me?days` (any member) → `{totals, series[], models[]}` | usage-metering |
| PC-6 | `GET /forge/v1/orgs/{id}/gateway` additive read fields: `keys:[{label,last4,status}]`, `allowed_models[]`, `ceiling_model_id` ; PUT key removed for org admin | gateway-keys |
| PC-7 | `GET /downloads/latest.json` → `{version, released_at, platforms:{windows:{url, sha256, size_bytes}}}` same-origin; artifact under `/downloads/<file>` | this (CP mount) + deploy-compose/desktop |
| PC-8 | `GET /forge/v1/accounts/me` shows member org roles incl. plain `member` (portal home) | exists |
| PC-9 | Departments: `POST/GET /orgs/{id}/departments` (exists); assignment endpoint for a member → `PUT /orgs/{id}/members/{mid}/department` if absent, else read-only display | CP (check) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Sibling contracts differ (usage shape, link format) | High | zod boundary + fixtures; task 1.6 reconcile; `/join` redirect covers both link formats |
| Capability in URL fragment leaks (referrer, history, analytics) | Med | parse then `replaceState`; `Referrer-Policy no-referrer` already on client; no third-party code (CSP gate); test asserts URL scrubbed |
| Branding flash / unbranded pre-login | Med | skeleton until branding resolves (≤ 800 ms) then fallback |
| Installer not available until change 12 | High | manifest-driven page with "installer not published yet" state; e2e uses test-served artifact |
| Deep link scheme unregistered (installer not installed) | Med | copyable company code fallback + clear steps |
| Existing-account-into-second-org unsupported | Med | explicit message with sign-in link; documented limitation |

## Rollback Plan

SPA slices revert top-down; CP additions (`/downloads`, redirect, additive field) are independent and removable; link format fallback keeps invitations working with the client
web UI path until `/join` is deployed.

## Success Criteria
- [ ] Real-stack journey: org admin invites → mailbox link → branded join → password → signed in → download page shows company code + installer link → my usage → admin dashboard shows that person.
- [ ] Fragment secret absent from URL after first render; no storage writes of token/capability.
- [ ] axe 0 serious/critical on company + portal routes at 375/768/1280; 0 CSP violations; existing member/branding suites still green.
