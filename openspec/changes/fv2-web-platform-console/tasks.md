# Tasks: fv2-web-platform-console

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~6,400 (≈4,700 source + ≈1,700 tests/fixtures) |
| 400-line budget risk | High (single PR) / Medium per slice at 800 |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR9 (stacked, each ≤ 800) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

> Program estimate was XL 5.5k / 7 slices; honest forecast 6.4k / 9 slices (tests + wizard saga + QR). Prerequisites merged: fv2-web-shell (all), fv2-platform-core, fv2-gateway-keys, fv2-usage-metering.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | API layer + fixtures + platform area skeleton/guard/theme/dark/idle | PR 1 (~700) | needs shell + platform-core contract |
| 2 | TOTP: MFA step, enrollment, QR, recovery codes | PR 2 (~750) | needs PR1 |
| 3 | Overview dashboard | PR 3 (~750) | needs PR1 + usage-metering |
| 4 | Companies list + detail frame (Overview tab, suspend/reactivate) | PR 4 (~780) | needs PR1 |
| 5 | Create wizard + saga | PR 5 (~790) | needs PR4, keys pool read (PC6) |
| 6 | Detail tabs: Branding, Keys, Models | PR 6 (~780) | needs PR4 + gateway-keys |
| 7 | Detail tabs: Usage charts, Members | PR 7 (~700) | needs PR6 + usage-metering |
| 8 | Key pool + Model prices | PR 8 (~780) | needs PR1 |
| 9 | Audit log + command palette company search + sweep + full e2e journey + README | PR 9 (~700) | needs all |

## Phase 1 — API layer & area skeleton (PR 1)
- [x] 1.1 RED: fixtures + schema specs for PC1, PC3, PC10, errors (each fails on missing/extra field)
- [x] 1.2 GREEN: `api/platform/*` modules, error-code map (`MFA_REQUIRED`, `CODE_TAKEN`, `KEY_IN_USE`…)
- [x] 1.3 Platform manifest (nav: Overview, Companies, Keys, Prices, Audit), `requires` guard, fixed theme + dark toggle, badge, owner email
- [x] 1.4 `useIdleTimeout` (fake timers unit) + cache clear on sign-out/401
- [x] 1.5 UI spec: guard (org admin denied, platform allowed), branding isolation, dark axe
- [x] 1.6 Contract reconcile task: diff fixtures vs sibling specs (platform-core, gateway-keys, usage-metering) → update PC table + fixtures

## Phase 2 — TOTP (PR 2)
- [x] 2.1 RED unit: `e2e/support/totp.ts` RFC 6238 vectors; QR matrix → path builder
- [x] 2.2 `MfaStep` (code + recovery alt, lockout), `Enroll` (QR SVG, manual secret, confirm), `RecoveryCodes` (once, copy/download, gate)
- [x] 2.3 Redirect logic: owner unenrolled → Enroll; enrolled/none → MfaStep; `MFA_REQUIRED` → MfaStep(return URL)
- [x] 2.4 UI: secret hygiene (not in DOM after Continue, not in URL/storage), axe, CSP
- [x] 2.5 e2e: bootstrap link → password → enroll → logout → login with computed code (real stack; extend `admin-e2e.ps1` seeding)

## Phase 3 — Overview (PR 3)
- [ ] 3.1 RED→GREEN unit: range parser, delta calc, KPI formatting
- [ ] 3.2 KPI cards, AreaChart (tokens/cost), top companies BarChart, KeyPoolHealth, audit tail
- [ ] 3.3 Skeleton/empty/error states, range URL sync; UI spec; e2e smoke with seeded usage

## Phase 4 — Companies list & detail frame (PR 4)
- [ ] 4.1 RED→GREEN: URL param schema, list table (search debounce, status filter, pagination)
- [ ] 4.2 Detail frame: header, tabs (URL-synced), Overview tab + setup checklist, suspended banner
- [ ] 4.3 Suspend (typed code) / reactivate; UI + e2e (suspend then member login denied is asserted in release-e2e, not here)

## Phase 5 — Create wizard (PR 5)
- [ ] 5.1 RED unit: slug rules, per-step schemas, `saga.ts` (success, fail at each of 4 steps, retry idempotent)
- [ ] 5.2 Steps 1–3 (company + availability, branding via ThemeEditor, first admin)
- [ ] 5.3 Step 4 (key picker last-4, model allow-list/ceiling), Step 5 review + progress view + success
- [ ] 5.4 UI: happy path, code taken, partial failure + "Finish setup"; keyboard-only run; axe
- [ ] 5.5 e2e: create company on real stack, invitation `.eml` recorded (path from stack)

## Phase 6 — Detail tabs I (PR 6)
- [ ] 6.1 Branding tab (ThemeEditor + publish), isolation test
- [ ] 6.2 Keys tab (assign/unassign, last-4, last-key warning)
- [ ] 6.3 Models tab (allow-list, ceiling, price display); UI + e2e for assign flow

## Phase 7 — Detail tabs II (PR 7)
- [ ] 7.1 Usage tab (range, AreaChart, StackedBars by model, BarChart top members; a11y tables)
- [ ] 7.2 Members tab read-only DataTable; no keys/PII beyond contract
- [ ] 7.3 UI + e2e with metered usage seeded by the stack's fake gateway

## Phase 8 — Key pool & prices (PR 8)
- [ ] 8.1 Key pool table + add (write-only `KeyField`, cleared after submit) + rename + retire (`KEY_IN_USE` handling)
- [ ] 8.2 Prices: decimal string → micros math (unit, no float), edit dialog, history drawer, effective-date rule
- [ ] 8.3 UI + e2e (add key, price edit round-trip)

## Phase 9 — Audit, palette, sweep, closeout (PR 9)
- [ ] 9.1 Audit table + filters + load more (URL-synced)
- [ ] 9.2 Command palette entries (pages + company search via cached list)
- [ ] 9.3 `ui/platform-sweep.spec.ts` (all routes × light/dark × 375/768/1280: axe + CSP + no horizontal scroll)
- [ ] 9.4 e2e `platform-journey.spec.ts` full owner journey; assert audit shows the actions
- [ ] 9.5 README/section in `docs/`: console guide, contract table, threat notes
