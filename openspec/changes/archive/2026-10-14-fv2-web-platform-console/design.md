# Design: fv2-web-platform-console

## Technical Approach

A lazy `areas/platform` module on the shell: manifest (nav, routes, `requires = platform && mfa totp`), pages per route, hooks over
zod-typed API modules, TanStack Query for server state, rhf+zod for forms, shell kit and charts for UI. The area applies the fixed
Prometheon theme and platform dark mode on mount and restores nothing company-specific. Spec refs: `platform-console-access`,
`platform-company-management`, `platform-operations`.

## Architecture Decisions

### Decision: Contract-first adapters with shared fixtures
**Choice**: `api/platform/*.ts` export zod schemas + functions; JSON fixtures in `tests/fixtures/platform/` feed unit, UI mocks and are
referenced by the control-plane pytest of siblings (same files copied/asserted in their change). **Alternatives**: hand-typed interfaces
(drift unnoticed); OpenAPI codegen (platform routes are `include_in_schema=False` by design, contract pin must not change).
**Rationale**: parse-at-the-boundary turns contract drift into a failing unit test with a precise path.

### Decision: Wizard as a resumable saga, not a giant form submit
Single `useForm` over the merged zod schema (per-step `trigger()`), Review calls `createCompany` then `putBranding`, `putKeys`, `putModels`
sequentially, tracking `{step: pending|ok|failed}`; any failure leaves the company in server-side "setup incomplete" (derived: no key or no first-admin
accepted?—server returns `setup:{branding,keys,models}` flags in `GET /companies/{id}`; assumption added to PC3). Idempotent PUTs make retries safe.

### Decision: TOTP UI
`qrcode-generator` (pinned, no DOM/style use) produces the module matrix; React renders one `<path>` in an SVG (no `<style>`, no data URI).
Codes input is a single `inputmode="numeric" autocomplete="one-time-code"` field (6 boxes hurt a11y). Recovery codes download via `Blob` +
`<a download>`; fallback copy/print if blocked (checked in e2e).

### Decision: URL as state for filters, tabs, ranges
`useSearchParams` wrappers with zod parsing; queries keyed by parsed params; gives reload/share/back-button correctness for free.

### Decision: Money and tokens
Integer micro-USD everywhere; conversion only in `lib/format.ts` and the price form (USD string → micros via decimal string math, never float).

## Data Flow

    Login(email,password) → session.set(token) → useIdentity(platform/me)
        enrolled & level none → <MfaStep> → POST /mfa/verify → refetch identity → /platform
        not enrolled (owner)  → <Enroll> → /totp/enroll → confirm → recovery codes → /platform
    Overview ──GET /overview?days──► KPIs + AreaChart + BarChart + KeyPoolHealth + AuditTail
    Wizard ──POST /companies──► PUT branding ──► PUT keys ──► PUT models ──► Success(detail link)
    Detail tabs ──GET /companies/{id}[/branding|keys|models|usage|members]
    403 MFA_REQUIRED (any) ──► MfaStep(return=current URL)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `admin/src/api/platform/{identity,mfa,companies,keys,models,usage,audit}.ts` | Create | zod schemas + calls |
| `admin/src/areas/platform/manifest.ts` | Modify | real nav/routes (was stub) |
| `admin/src/areas/platform/mfa/{MfaStep,Enroll,RecoveryCodes}.tsx` | Create | TOTP flows |
| `admin/src/components/qr/QrCode.tsx` | Create | SVG QR from matrix |
| `admin/src/areas/platform/overview/*` | Create | dashboard |
| `admin/src/areas/platform/companies/{List,Detail,tabs/*}.tsx` | Create | list + detail |
| `admin/src/areas/platform/companies/wizard/{Wizard,steps/*,saga.ts,schema.ts}` | Create | wizard |
| `admin/src/areas/platform/keys/*`, `prices/*`, `audit/*` | Create | operations |
| `admin/src/areas/company/branding/ThemeEditor.tsx` | Reuse | extracted in shell S7 |
| `admin/src/shell/useIdleTimeout.ts` | Create | 30-min idle sign-out |
| `admin/tests/fixtures/platform/*.json` | Create | contract fixtures |
| `admin/tests/unit/platform-*.spec.ts` | Create | schemas, saga, price math, totp helper |
| `admin/tests/ui/platform-*.spec.ts` | Create | mocked UI per area + sweep |
| `admin/e2e/support/totp.ts`, `e2e/platform-*.spec.ts` | Create | real stack |
| `scripts/admin-e2e.ps1` | Modify | seed owner + export creds |

## Interfaces / Contracts

```ts
export const CompanySummary = z.object({ id: z.string().uuid(), name: z.string(), code: z.string(),
  status: z.enum(["active","suspended"]), members: z.number().int(), tokens_30d: z.number().int(), cost_micros_30d: z.number().int(),
  setup: z.object({ branding: z.boolean(), keys: z.boolean(), models: z.boolean() }), created_at: z.string() });
export const Overview = z.object({ companies: z.object({ active: z.number(), suspended: z.number() }), active_users: z.number(),
  tokens: z.number(), cost_micros: z.number(), previous: z.object({ tokens: z.number(), cost_micros: z.number() }),
  series: z.array(z.object({ day: z.string(), tokens: z.number(), cost_micros: z.number() })),
  top_companies: z.array(z.object({ id: z.string(), name: z.string(), cost_micros: z.number() })),
  key_pool: z.object({ available: z.number(), degraded: z.number(), retired: z.number() }) });
export type WizardInput = { company:{name:string;code:string}; branding?: BrandingBody; admin:{email:string;display_name:string}; keys:string[]; models:{ids:string[]; ceiling?:string} };
```
(Final shapes reconciled in task 1.6 against sibling specs.)

## Testing Strategy (strict TDD)

| Layer | What | Approach |
|-------|------|----------|
| Unit | schemas vs fixtures, saga state machine (each failure point), price USD→micros, slug rules, TOTP RFC 6238 helper, URL param parsers | RED first, table-driven |
| UI (mocked API, prod bundle) | each screen: loading/empty/error/success, dark mode, wizard steps + failures, MFA flows, typed-confirm, secret hygiene, axe, CSP, 3 viewports | `page.route` fixtures |
| e2e (real stack) | owner bootstrap→password→enroll→login code→create company→invite→keys/models→usage→suspend; key pool add/retire; price edit; audit shows events | `admin-e2e.ps1`, system Chrome |
| Sweep | all routes axe light/dark + CSP | single spec |

## Migration / Rollout
No data migration. Depends on stack order 4→5→6→7→8. Until siblings land the area is test-only against fixtures (nav hidden by
`platform/me` 404 ⇒ not platform), so merging early is safe.

## Open Questions
- [ ] PC3 `setup` flags and draft state — confirm with platform-core design.
- [ ] Does `GET /overview` include `previous` period or must the SPA request twice? (default: server-side).
- [ ] Idle timeout value (default 30 min) acceptable?
