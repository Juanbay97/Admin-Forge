# Proposal: fv2-web-platform-console (super-admin console)

> Change 8 of the forge-v2 program. Track W after `fv2-web-shell` (#7). **Backend-dependent**: `fv2-platform-core` (4),
> `fv2-gateway-keys` (5), `fv2-usage-metering` (6) land first in the same stack. Source: Engram #3371, #3369 (product vision v2).

## Intent

Today a company can only be created by a trusted CLI and the org admin sets the gateway key. The platform owner (the user) needs a
web console to create and run companies end-to-end: brand them, assign keys from a platform-owned pool, choose their models,
watch tokens/cost, and suspend them — protected by TOTP, in a fixed Prometheon theme that company branding can never restyle.

## Scope

### In Scope (area `/admin/platform/*`)
- Platform sign-in with TOTP challenge; TOTP enrollment (QR as SVG + manual secret + one-time recovery codes).
- Overview dashboard: companies, active users, tokens, cost (range 7/30/90d), usage series, top companies, key-pool health.
- Companies: searchable/filterable list; **create wizard** (company → branding → first admin → keys & models → review) with partial-failure resume;
  detail with tabs Overview, Branding, Keys, Models/Catalog, Usage (charts), Members (read-only); suspend/reactivate with typed confirmation.
- Key pool: add (write-only secret, last-4), label, retire, see assignments/health.
- Model prices: per-model input/output price with effective date history.
- Audit log: filterable, paginated, read-only.
- Dark mode, command palette (jump to company/page), keyboard + axe + CSP gates, Playwright e2e on the real stack.

### Out of Scope
- Control-plane endpoints (changes 4/5/6) — consumed through the contract below; capability governance UI (change 10).
- Billing/invoicing, per-user drill-down across companies, email template editing, impersonation.
- Separate host for `/platform` (proxy-level hardening deferred).

## Capabilities

### New Capabilities
- `platform-console-access`: sign-in + TOTP login/enrollment, platform guard, fixed theme/dark mode, session rules.
- `platform-company-management`: list, create wizard, detail tabs, branding/keys/models assignment, usage, members view, suspend.
- `platform-operations`: overview dashboard, key pool, model prices, audit log.

### Modified Capabilities
- `admin-app-shell` (from fv2-web-shell): platform area manifest + nav + command-palette company search registered (no requirement change).

## Approach

Typed zod API modules under `src/api/platform/*` with shared JSON fixtures (`tests/fixtures/platform/*.json`) that double as the
contract record the control-plane tests assert against. Screens use shell kit/charts/TanStack Query. Wizard state lives in one
react-hook-form instance across steps (zod schema per step) and submits as an explicit saga: create company → apply branding →
assign keys → set models; progress is persisted server-side (the company exists as `draft`/pending-setup) so a failed step can resume
from the detail page ("Finish setup" banner). Branding editor is the extracted `ThemeEditor` from the shell port.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `admin/src/areas/platform/**` | New | pages, hooks, wizard |
| `admin/src/api/platform/*.ts` | New | zod-typed clients |
| `admin/src/components/qr/*` | New | SVG QR renderer (`qrcode-generator` pinned) |
| `admin/tests/{unit,ui}`, `tests/fixtures/platform` | New | logic, mocked-UI, contract fixtures |
| `admin/e2e/platform-*.spec.ts` | New | real-stack journeys |
| `scripts/admin-e2e.ps1` | Modify | seed platform owner via `python -m forge.platform bootstrap-owner`, export credentials |

## Contract (assumptions — reconcile with sibling designs; owner = providing change)

All under `/forge/v1/platform`, bearer, hidden from OpenAPI (`include_in_schema=False`), POST/PUT/GET only (matches `apply_guard` CORS list).
Money = integer micro-USD (`*_micros`); tokens = integers; times ISO-8601 UTC; list endpoints = `{items, next_cursor}`.

| ID | Endpoint | Shape (essential) | Owner |
|----|----------|-------------------|-------|
| PC1 | `GET /me` | `{account_id, role, mfa:{enrolled, level}}` | platform-core |
| PC2 | `POST /totp/enroll` → `{secret_base32, otpauth_uri, recovery_codes[]}`; `POST /totp/confirm {code}`; `POST /mfa/verify {code}` or `{recovery_code}` → upgrades session; platform calls without MFA ⇒ `403 MFA_REQUIRED` | platform-core |
| PC3 | `GET /companies?query&status&cursor`; `POST /companies {name, code, first_admin:{email, display_name}}` → `{company, invitation:{delivery_state}}`; `GET /companies/{id}`; `POST /companies/{id}/suspend|reactivate`; `GET /companies/code-available?code` | platform-core |
| PC4 | `GET|PUT /companies/{id}/branding` (same body as org branding, platform authority) | platform-core |
| PC5 | `GET|PUT /companies/{id}/keys {key_ids[]}`; `GET|PUT /companies/{id}/models {model_ids[], ceiling_model_id?}` | gateway-keys |
| PC6 | `GET /keys`; `POST /keys {label, secret}` (secret never returned; `last4`); `POST /keys/{id}/retire`; `PUT /keys/{id} {label}` | gateway-keys |
| PC7 | `GET /overview?days` ; `GET /companies/{id}/usage?days&group=day|model|member` | usage-metering |
| PC8 | `GET /models/prices`; `PUT /models/{id}/price {input_micros_per_mtok, output_micros_per_mtok, effective_from}` | usage-metering |
| PC9 | `GET /audit?actor&action&target&from&to&cursor` → `{items:[{id, at, actor, action, target, summary}], next_cursor}` | platform-core |
| PC10 | `GET /companies/{id}/members` (read-only list, no emails beyond display) | platform-core |
| PC11 | Error codes: `MFA_REQUIRED`, `MFA_INVALID`, `CODE_TAKEN`, `KEY_IN_USE`, `COMPANY_SUSPENDED` | platform-core |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Sibling designs diverge from PC1–PC11 | High | adapter layer + fixtures isolate shape; slice 1 ends with a "contract reconcile" task that diffs fixtures vs sibling specs |
| TOTP e2e needs valid codes | Med | RFC 6238 helper in `e2e/support/totp.ts` (unit-tested vs RFC vectors) reading secret from enroll response |
| Blob download of recovery codes blocked by CSP | Low | verify in e2e; fallback copy-to-clipboard + print |
| Wizard half-created company | Med | server draft state + resume banner; tests for each failure step |
| Owner console shares origin with public portal | Med | in-memory token, no third-party code (CSP gate), documented hardening follow-up |
| Slice count above program estimate (7 → 9) | Med | each slice self-contained; orchestrator informed in tasks forecast |

## Rollback Plan

Platform routes are gated by the platform guard and are absent for non-platform accounts; revert the stack top-down. No data
migrations in this change; CLI bootstrap remains the recovery path.

## Success Criteria
- [ ] Owner journey on the real stack: bootstrap link → set password → TOTP enroll → login with code → create company → branded → first admin invited → keys + models → usage visible → suspend/reactivate.
- [ ] axe 0 serious/critical on every platform route, light + dark, 375/768/1280; 0 CSP violations.
- [ ] Secrets (key material, TOTP secret, recovery codes) never in URL, storage, logs, or DOM after dismissal.
