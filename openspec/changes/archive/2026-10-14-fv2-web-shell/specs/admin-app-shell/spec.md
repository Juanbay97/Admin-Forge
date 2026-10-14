# Admin App Shell Specification (new)

## Requirements

### Requirement: Router and URL layout
The SPA MUST use React Router 7 (library mode, `createBrowserRouter`) under `/admin`. Route tree:
`/admin/login`, `/admin/join` (public, owned by change 9), `/admin/platform/*`, `/admin/company/*`, `/admin/portal/*`, `/admin` (role redirect).
Area bundles MUST be lazy chunks. Unknown paths render NotFound inside the shell.

#### Scenario: Deep link survives login
- GIVEN a signed-out user opens `/admin/company/members`
- WHEN they sign in
- THEN they land on `/admin/company/members` (the URL is the return target; nothing is stored)

### Requirement: Role-based home and guards
After sign-in the shell MUST resolve the home area from `GET /forge/v1/platform/me` (SC1) and `GET /forge/v1/accounts/me`:
platform role ⇒ `/platform`; `organization_admin` in ≥1 org ⇒ `/company`; otherwise a member ⇒ `/portal`. Area routes MUST guard by
capability: a user opening a forbidden area sees AccessDenied (403 page) with a link to their home. 403/404 from `platform/me`
MUST mean "not platform", never an error page.

#### Scenario: Org admin cannot see platform
- GIVEN an org admin
- WHEN they open `/admin/platform`
- THEN AccessDenied renders, no platform API call other than `platform/me` is made

#### Scenario: Multi-role
- GIVEN an account that is platform owner and org admin
- THEN home is `/platform` and the user menu offers "Switch to Company area"

### Requirement: Session handling
The bearer token stays in memory only (existing `auth/session.ts`). A `401` from any call MUST clear the session, clear the TanStack
Query cache, and redirect to login preserving the current path. Sign-out MUST clear the cache and the applied company theme.

#### Scenario: Expired token
- GIVEN an open page
- WHEN an API call returns 401
- THEN the user sees the login page with a "Your session expired" notice and, after signing in, returns to the same URL

### Requirement: Shell chrome
The shell MUST provide a left sidebar (collapsible ≥1024px, drawer <1024px), topbar (breadcrumbs, company switcher when the user
has several organisations, command palette trigger ⌘K/Ctrl+K, user menu with sign out and theme toggle in platform), a skip-link,
`<main id="main">` landmark, and an `aria-live` toast region. Each area declares a nav manifest (`label, to, icon, requires`).

#### Scenario: Keyboard navigation
- WHEN the user presses Tab once on a fresh page
- THEN the skip link is focused; activating it moves focus to `<main>`

#### Scenario: Command palette
- WHEN the user presses Ctrl+K
- THEN a dialog lists nav entries of the current area (filterable); Enter navigates; Esc closes and restores focus

### Requirement: Data layer conventions
Server state MUST use TanStack Query with typed API modules (zod-parsed responses in new modules), query keys namespaced
`[area, resource, params]`, `staleTime` 30s, retry off for 4xx. Mutations MUST invalidate by key and surface errors as toasts
or inline Alerts using the error `code` → message map.

#### Scenario: Error mapping
- GIVEN an API error `{error:{code:"MFA_REQUIRED"}}`
- THEN the shell routes to the MFA step instead of showing a generic error

### Requirement: Port of existing pages
Overview, Members, Gateway, Catalog, Branding and Login MUST be migrated to the kit under `/admin/company/*` with identical
accessible roles/names so existing tests keep passing; behaviours (invite, suspend/reactivate, branding preview, catalogue
refresh/publish, org choice) MUST be unchanged.

#### Scenario: Existing suites
- WHEN `npm run test:unit` and `scripts\admin-e2e.ps1` run after the port
- THEN all pre-existing tests pass without weakening any assertion

### Requirement: Quality gates harness
`tests/ui/support.ts` MUST expose `expectNoCspViolations`, `expectAccessible(page)` (axe, wcag2a/2aa/21aa, fails on serious+critical)
and viewport helpers; each routed page's UI test MUST call them.

#### Scenario: Gate fails on violation
- GIVEN a component injecting a `<style>` element
- THEN the UI test fails with the CSP violation message
