# Company dashboard and member portal

Two areas of the admin web serve the people of a company:

- **Company area** (`/admin/company`, organization administrators): a usage dashboard with per-person usage, members and departments,
  catalog, branding and a read-only gateway status.
- **Member portal** (`/admin/portal`, everyone with a company): home, the download page and "My usage". Both wear the company's branding.

Plus the **public join page** (`/admin/join`) that the invitation email leads to, and the set-password page (`/admin/reset-password`)
used by the platform owner's bootstrap link (see `docs/platform-console.md`).

## The invitation journey

1. An administrator (or the platform owner, for a company's first administrator) invites someone. The control plane mails
   `<public origin>/onboarding?c=<company code>#invitation_id=<uuid>&capability=<token>` (the company code is on every invitation since
   `fv2-gap-closure` G5, so the join page is branded for invited members too; if the code cannot be read the link simply has no hint).
2. The control plane answers `GET /onboarding` (and `/join`) with a 307 to `/admin/join` keeping the query; browsers keep the fragment.
   `/reset-password` is redirected to `/admin/reset-password` the same way.
3. The join page resolves the company's public branding (`GET /forge/v1/branding?org=<code>`) before showing the form: a skeleton for at most
   800 ms, then the Prometheon default, re-themed if the branding arrives late. It reads the fragment once into memory and removes it from the
   address bar; nothing is stored or logged. It never calls an authenticated endpoint.
4. The page asks the server who the invitation is for (`POST /forge/v1/accounts/invitations/preview`, hidden and outside the contract) and says
   "You are joining as <email>"; the person only chooses a password (at least 15 characters; the server's rule). If the server cannot answer in
   three seconds, or is an older one without the route, the page asks for the email as before. The page accepts the invitation, signs in with
   that address and lands on `/portal/download`.
5. The download page shows the company code with a copy button, the installer from `/downloads/latest.json` (version, size, date, SHA-256 and
   how to verify it), an "Open Forge" button using `prometheon-forge://join?cp=<origin>&code=<code>` with a manual fallback, and the SmartScreen note.
   Non-Windows systems are told "Windows only for now".

Failure states: an expired, used, withdrawn, wrong or unknown invitation (the server folds all of them into one 404, for the preview and for accept, so
nothing can be enumerated; the page shows one generic message, "This invitation can no longer be used", before anything is typed), an incomplete link, an existing account
that must sign in first (409), a refused password, throttling, an outage and being offline each have their own friendly state with the next
step. A signed-in visitor is not auto-accepted; they are offered to sign out first.

## Contract (PC-1 to PC-9) against the real server

| ID | Plan | Reality and what the SPA does |
|----|------|------------------------------|
| PC-1 | link `/admin/join?c=&#...` | The mailed link is `/onboarding?c=<code>#invitation_id&capability` on the public origin, for every issuer. `admin_mount` redirects `/onboarding` and `/join` to `/admin/join`. The edge proxy forwards `/onboarding`, `/join`, `/reset-password` and `/downloads/*` to the control plane (`deploy/Caddyfile`, `fv2-gap-closure` G6). |
| PC-2 | public branding by code | As planned (`GET /forge/v1/branding?org=<code>`, 404 when unknown, rate limited). |
| PC-3 | accept returns `account_email`; distinct error codes | The accept response is part of the pinned contract, so it is **unchanged** (no pin impact). The address comes from the hidden `POST /forge/v1/accounts/invitations/preview` `{invitation_id, capability}` -> `{account_email, display_name}` (migration 0046, non-contract): it answers only the holder of a pending, unexpired invitation of an active company, repeatably and without consuming it; everything else is the same `404 NOT_FOUND`. Distinct error codes stay refused on purpose (no enumeration). An existing account is `409 EXISTING_ACCOUNT_AUTH_REQUIRED`, a short password `422`. |
| PC-4 | `GET /orgs/{id}/usage?group=member\|day\|model` | The real route is `GET /orgs/{id}/usage/members?from&to&after&page` (administrators only), one row per person with counters (requests, prompt/completion tokens, estimated/error/unpriced requests, cost in micro-USD) and the person's email, name and state. There is no per-day series and no per-model split, so the dashboard has KPIs with the change against the previous period, top people and a sortable person table, but no area chart. Department comes from the member list (matched by email). |
| PC-5 | `GET /orgs/{id}/usage/me` | **Live** (`fv2-gap-closure` G1, migration 0042). Any active member (administrators too) reads their own counters for `?from&to` (UTC days, at most 366): `{requests, prompt_tokens, completion_tokens, estimated_requests, error_requests, cost_micros, unpriced_requests}`. The database function derives the membership from the live session, so there is no way to ask for someone else; a stranger, another company, a suspended member and a stale session are the same 404. Hidden from OpenAPI (the contract pin is unchanged). A zero range is one row of zeros ("No usage yet"); an older server without the route still gets "not available yet". |
| PC-6 | gateway read fields with last-4, models, ceiling | The company gateway read returns `status`, `revision` (the number of usable platform keys) and the endpoint. The Gateway page shows exactly that, read-only; there is no key list for company administrators. |
| PC-7 | `/downloads/latest.json` + file | Served by Caddy in production and by `downloads_mount.py` locally (`mvp_up` stages a manifest and a stand-in installer). The SPA requires the installer URL to be `/downloads/<file>` (same origin) and the hash to be 64 hex characters. |
| PC-8 | `accounts/me` for plain members | As planned: the portal uses the member's organizations and roles. |
| PC-9 | department assignment endpoint | **Live** (`fv2-gap-closure` G4, migration 0045): `PUT /orgs/{id}/members/{member}/department` with `{department_id}` (administrators only, hidden from OpenAPI) makes that the member's one department and answers with the updated member. The Members page offers "Change department" on each person. A foreign or unknown member or department, a member asking and a stale session are the same 404. Renaming and removing departments are still not offered. |

## Company dashboard

`/company` shows the company at a glance (departments) and, below it, the usage section for 7, 30 or 90 days (`?days=`): people using Forge,
tokens and cost with the change against the previous period, requests, top people by tokens and the person table (search, department filter,
sort, share of tokens). Every query is keyed by the organization, so switching company discards the previous one. A server without the
usage route says so instead of showing an error.

## Quality gates

Every portal and company route has axe checks (no serious or critical findings) at 375, 768 and 1280 px, no horizontal scroll and zero CSP
violations. The join page's fragment is asserted absent from the URL, storage and cookies.

## Tests

- Unit and mocked UI: `cd admin && npm run test:unit` (`tests/ui/portalSupport.ts` is the double; fixtures are in `tests/fixtures/portal/`).
- Python: `tests/test_portal_hosting.py` (downloads traversal and headers, link redirects, the staged manifest).
- Real stack: `scripts\admin-e2e.ps1 -Spec "[123]0-"` runs the platform owner journeys and then `30-portal-journey.spec.ts`: the company's first
  administrator joins from the mailed link, downloads (hash verified against the served file), invites a person, the person joins and finds
  their usage page, and the dashboard shows that person's metered usage. Screenshots go to `%TEMP%\opencode\forge-ui\portal`.