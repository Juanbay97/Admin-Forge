# Platform console

The platform console is the area of the admin web a **platform owner** uses to run companies end to end: create and brand them,
assign gateway keys, choose their models, watch usage and cost, set prices, suspend and audit. It lives at `/admin/platform` and is
absent for everyone else (a company administrator sees "Access denied"). It always wears the fixed Prometheon theme, offers dark
mode and shows a persistent "Platform console" badge.

## Signing in

1. The owner is created once by the operator (`python -m forge.platform bootstrap-owner`, see `docs/deploy.md`); the command mails
   (or writes to a private file) a one-time link `https://<host>/reset-password#capability=...`. The control plane redirects it to
   `/admin/reset-password`, where the owner sets the first password. The capability stays in the URL fragment, is read once into memory
   and removed from the address bar.
2. Signing in with email and password opens the **second-factor gate**. Nothing else renders (and no platform data is requested)
   until this session has passed it.
3. First time: enrollment is mandatory. Start setup, scan the QR code (or type the secret), confirm with a code, then save the
   ten recovery codes. They are shown once; the secret and the codes live only in component state and are gone after "Continue".
4. Afterwards: a 6-digit code (or a recovery code) on every sign-in. Each code step is accepted once and the server allows one step
   either side of its clock. After 15 minutes of failed attempts the form disables itself.
5. The server treats a verification older than 30 minutes as stale for changes (`fresh`); the console re-reads it every minute and on
   any `MFA_REQUIRED`, and returns the owner to the code step on the same URL.
6. 30 idle minutes sign the owner out ("Signed out for inactivity").

## Pages

| Route | What it does |
|-------|--------------|
| `/platform` | Overview: companies, requests, tokens, cost for 7/30/90 days with the change against the previous period, top companies by cost, tokens by model, key pool health, recent activity. |
| `/platform/companies` | Search, status filter (both in the URL), cost and tokens for 30 days. |
| `/platform/companies/new` | Wizard: company, branding (optional), first administrator, gateway keys, review. The wizard never touches models (they are chosen from the company's Models tab after creation). A resumable saga: a failed step is named and retried alone. |
| `/platform/companies/:id` | Tabs (in the URL): Overview with the setup checklist, Branding, Keys, Models, Members (read-only), Usage. Suspend needs the company code typed; suspended companies are read-only. |
| `/platform/keys` | The key pool: add (write-only), rotate, disable/enable. Only label and last four characters are ever shown. |
| `/platform/prices` | Versioned USD-per-million-token prices with history; an edit appends a version. |
| `/platform/audit` | Read-only audit trail with action, company and date filters and "Load more". |

Ctrl+K searches pages and companies.

## Contract this console consumes

Everything is under `/forge/v1/platform` (hidden from OpenAPI, so the contract pin is unchanged). The console parses every response
with a strict zod schema (`admin/src/api/platform/schemas.ts`); the same JSON lives in `admin/tests/fixtures/platform/` and is what the
mocked UI tests serve. A server-side change of shape fails a unit test with the field path.

| Console need | Endpoint | Notes |
|--------------|----------|-------|
| Identity | `GET /me` | `{account_id, role, mfa:{state: none\|pending\|active, verified, fresh}}`. A platform owner has no company membership, so `GET /accounts/me` answers 404 and the console builds the identity from this plus the email typed at sign-in. |
| Second factor | `POST /mfa/enroll`, `POST /login/mfa` | `{code}` or `{recovery_code}`; the first successful code activates a pending factor. |
| Companies | `GET /companies?after=<slug>&page=`, `GET /companies/{id}`, `POST /companies`, `POST /companies/{id}/suspend\|reactivate` | Cursor is the company code; the server has no search or status filter, so the console loads every page and filters locally. Create takes `{slug, display_name, department, admin_email, admin_name}` and returns the invitation's `delivery_state`. |
| Members | `GET /companies/{id}/members?after=<membership id>&page=` | Read-only list in the company directory shape `{id, email, display_name, status, roles, departments[{id,name}]}` plus `next_after`; suspended members included, no secret column exists (migration 0043). An unknown company is 404. |
| Branding | `GET\|PUT /companies/{id}/branding`, `POST .../branding/reset` | Same body as the company's own branding; no logo upload. |
| Keys | `GET\|POST /gateway-keys`, `POST /gateway-keys/{id}/rotate\|enable\|disable` | Key text is accepted only on create and rotate; responses carry `hint` (last four). |
| Assignments | `GET\|PUT /companies/{id}/gateway-keys` | Ordered `{key_id, priority, active}`. |
| Models | `GET\|PUT /companies/{id}/model-access` | `{models: [...]}` is the ceiling for what the company can publish. |
| Prices | `GET\|POST /prices` | Integer micro-USD per million tokens, capped at 1000 USD. |
| Usage | `GET /usage/totals\|companies\|models?from&to` | Inclusive UTC days, at most 366. |
| Overview | `GET /overview?from&to` | `{companies:{active,suspended}, active_users, requests, prompt_tokens, completion_tokens, estimated_requests, error_requests, cost_micros, unpriced_requests, previous:{active_users, requests, prompt_tokens, completion_tokens, cost_micros}}`. `previous` is the same number of days immediately before the range, so the console makes one call for the change figures (migration 0044). |
| Daily series | `GET /usage/days?from&to` | `{days:[{day, <the seven counters>, active_users}]}`: every UTC day of the range in order, zeros included, so the charts need no gap filling. |
| Audit | `GET /audit?before=&page=` | Entries have the actor, action, company id and time. |

**The model ceiling is chosen, never typed.** `PUT /companies/{id}/model-access` accepts only models the company's keys were discovered to reach (migration 0049): `422 DISCOVERY_REQUIRED` while the company has no current discovery, `422 MODEL_NOT_DISCOVERED` for any model outside it, and the empty list still denies everything. The Models tab therefore offers a checklist of the discovered models, and the usual way to set the ceiling is the platform catalog publish, which sets it to exactly the selected models. A company administrator can only narrow the published catalog inside the ceiling: the catalogue refresh lists just the models inside it, and a publication outside it answers `409 MODEL_NOT_ALLOWED`, shown as a message that names the platform ceiling as the reason.

### Differences from the original plan (PC1 to PC11)

The sibling changes landed with a smaller surface than the plan assumed, so some screens are narrower:

- `GET /overview` and `GET /usage/days` are now served (`fv2-gap-closure` G3, migration 0044): the dashboard makes one overview call (with the
  previous period and active people), draws tokens and cost per day as area charts, and still composes `usage/companies`, `usage/models`,
  the key list and the audit tail.
- Company members (PC10) is now served (`fv2-gap-closure` G2, migration 0043): the Members tab is read-only. The overview shows active people (distinct members with usage in the range).
- No code-availability endpoint: availability is checked against the loaded company list, and `COMPANY_CONFLICT` covers the race.
- No audit filters: the server pages by id only, so actor/action/company/date filters apply to the loaded entries.
- No key "retire", "rename" or `KEY_IN_USE`: a key is disabled (companies fall back to their other keys), and rotated for new text.
- Prices are `POST /prices`, not `PUT /models/{id}/price`.
- No `setup` flags on a company: the checklist is derived from the branding revision, the assignments and the model access.

## Threat notes

- The bearer token lives in memory only (a reload signs in again). No secret, recovery code or key text is written to storage, cookies or the URL.
- The page is served under `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'`. The QR is one SVG
  path (no data URI), downloads use a `blob:` anchor that the policy allows, and every UI test fails on a CSP violation.
- The query cache is cleared on sign-out and on any 401 (company data is sensitive).
- The console shares its origin with the public join page. Hardening it behind its own host or an IP allow-list is left to the edge
  proxy (see `docs/deploy.md`).
- Each change re-validates a fresh verified owner in the database; the console never decides authority.

## Tests

- Unit and mocked-UI: `cd admin && npm run test:unit` (UI specs run the production bundle in the system Chrome against `tests/ui/platformSupport.ts`).
- Real stack: `scripts\admin-e2e.ps1` boots the owned local stack (it seeds the owner link), then runs `admin/e2e/10-platform-owner.spec.ts`
  and `20-platform-console.spec.ts` (bootstrap link, enrollment, TOTP sign-in, metered usage, suspend/reactivate, wizard, tabs, key pool,
  prices, audit). Use `-Spec platform-` to run only these. Screenshots go to `%TEMP%\opencode\forge-ui\console`.