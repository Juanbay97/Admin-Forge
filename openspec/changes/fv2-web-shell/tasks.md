# Tasks: fv2-web-shell

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~5,000 (≈4,100 source + ≈900 net tests; lockfile excluded as generated) |
| 400-line budget risk | High (single PR) / Medium per slice at 800 |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR7 (stacked, each ≤ 800) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

> Forecast vs. program estimate (L, ~4k/5sl): 7 slices ~5.0k. Lockfile is generated and excluded from the budget (flag `size:exception` for `package-lock.json` only).

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation: deps, semantic tokens, CSP/axe fixtures, primitive spike | PR 1 (~650) | base `main`; nothing user-visible |
| 2 | Kit core: Button…Field/Form, Card, Badge, Alert, Skeleton, EmptyState | PR 2 (~780) | needs PR1 |
| 3 | Kit overlays/data: Dialog/Sheet/AlertDialog, Tabs, Tooltip, Menu, Toast, DataTable, KeyField | PR 3 (~790) | needs PR2 |
| 4 | Chart kit (SVG) | PR 4 (~650) | needs PR1 only (parallelisable with 2–3) |
| 5 | Router, providers, shell chrome, area registry; legacy pages mounted unchanged | PR 5 (~780) | needs PR3 |
| 6 | Port Overview + Members + Login to kit | PR 6 (~780) | needs PR5 |
| 7 | Port Gateway + Catalog + Branding; delete legacy Console; e2e + README | PR 7 (~780) | needs PR6 |

## Phase 1 — Foundation (PR 1)
- [x] 1.1 RED: `tests/ui/support.ts` `expectNoCspViolations` (listens `securitypolicyviolation` + console), `expectAccessible` (axe), `viewports`; failing self-test that injects a `<style>` and must be reported
- [x] 1.2 GREEN: add pinned deps (`@axe-core/playwright`, router, query, rhf, zod, resolvers, class-variance-authority, clsx, tailwind-merge, lucide-react, cmdk, selected `@radix-ui/react-*`); `npm audit`; README version table
- [x] 1.3 RED→GREEN: `brand/platformTheme.ts` (+ `unit/platform-theme.spec.ts`: values pass contrast, no company asset)
- [x] 1.4 `tokens.css`: `--ui-*` layer, dark overrides, type scale, focus ring; unit test mapping every `--ui-*` to a brand var
- [x] 1.5 Spike test `ui/primitives-csp.spec.ts`: mount each allow-listed Radix primitive in the test build; record pass/fail → update design allow-list
- [x] 1.6 `lib/cn.ts`, `lib/format.ts` (+ unit)

## Phase 2 — Kit core (PR 2)
- [x] 2.1 RED: gallery spec (variants, disabled, loading, focus ring, 40px targets, axe) → GREEN: Button, Input, Textarea, Select, Checkbox, Switch, RadioGroup, Label
- [x] 2.2 RED: Field/Form (aria-invalid/describedby/live) → GREEN: Field, `useZodForm`, FormError
- [x] 2.3 Card, Badge, Alert, Separator, Skeleton, Spinner, EmptyState (+ kit gallery route `?kit` in test build only via `VITE_KIT`)

## Phase 3 — Kit overlays & data (PR 3)
- [x] 3.1 RED: dialog a11y (focus trap/Esc/return focus) → GREEN: Dialog, AlertDialog, Sheet on native `<dialog>`
- [x] 3.2 Toast store (unit) + region (`aria-live`), Tabs, Tooltip, DropdownMenu (non-modal)
- [x] 3.3 DataTable (sort, filter slot, pagination, sticky header, empty/skeleton), Pagination, CopyButton, KeyField (write-only, last-4)
- [x] 3.4 Gallery opens every overlay under `expectNoCspViolations`

## Phase 4 — Charts (PR 4)
- [ ] 4.1 RED→GREEN unit: `niceTicks`, `linearScale`, `timeTicks`, `buildLinePath`, formatters (zero/flat/NaN cases)
- [ ] 4.2 ChartFrame (ResizeObserver, a11y table, legend), Sparkline, AreaChart/LineChart (crosshair, keyboard)
- [ ] 4.3 BarChart, StackedBars, Donut; empty/loading/error variants
- [ ] 4.4 `ui/charts.spec.ts`: aria summary, keyboard, resize 1280→375, CSP, axe

## Phase 5 — Router & shell (PR 5)
- [ ] 5.1 RED→GREEN unit: `homeFor(identity)`, error-code map, `useIdentity` tolerance of 403/404 platform/me
- [ ] 5.2 Providers (Query + Services + Toasts), `RequireSession`, `AreaGate`, 401 handler
- [ ] 5.3 AppShell, Sidebar (collapse/drawer), Topbar, Breadcrumbs, UserMenu, CommandPalette, skip-link
- [ ] 5.4 Area manifests (platform/portal stubs → NotFound-in-shell "coming soon" hidden from nav), company area mounting legacy pages unchanged
- [ ] 5.5 `ui/shell.spec.ts`: deep link after login, 401 expiry, forbidden area, Ctrl+K, responsive nav, axe
- [ ] 5.6 e2e `shell.spec.ts` + adapt `admin-flow.spec.ts` URLs (real stack)

## Phase 6 — Port I (PR 6)
- [ ] 6.1 Login (branded, RHF+zod) — existing `login.spec.ts` untouched + new states
- [ ] 6.2 Overview (cards + skeleton) and Members (DataTable, invite dialog, suspend AlertDialog) — move tests with code, keep roles/labels
- [ ] 6.3 `members.spec.ts`/`hardening.spec.ts` green; axe at 3 viewports

## Phase 7 — Port II + closeout (PR 7)
- [ ] 7.1 Gateway (read-only-ready layout; key form kept until `fv2-gateway-keys` changes it), Catalog, Branding (extract `ThemeEditor`/`BrandPreview` for reuse by console wizard)
- [ ] 7.2 Delete `components/Console.tsx`, dead styles; assert no `<style>` in built `index.html`/assets (unit on dist)
- [ ] 7.3 Full `npm run test:unit`, `typecheck`, `build`, `scripts\admin-e2e.ps1` (all pre-existing specs unchanged)
- [ ] 7.4 README: stack, allow-list, how to add a component under CSP, a11y/CSP gates, visual QA checklist; screenshots as PR artifact
