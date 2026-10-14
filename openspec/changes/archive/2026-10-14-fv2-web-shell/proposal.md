# Proposal: fv2-web-shell (design system, router, role areas, port existing pages)

> Change 7 of the forge-v2 program (`openspec/changes/forge-v2-program/exploration.md`, Engram `sdd/forge-v2-program/explore` #3371).
> Track W (SPA). **No backend dependency: can start now.** `fv2-web-platform-console` and `fv2-web-company-portal` build on it.

## Intent

The admin SPA (`admin/`, ~34 files, hand-rolled components, no router, one view-switch in `components/Console.tsx`) can only serve one
role: the organisation administrator. forge-v2 needs ONE SPA with three role areas (Platform console, Company admin, Member portal)
and a modern, accessible UX. This change builds the shared foundation once, so the two area changes only add screens.

## Scope

### In Scope
- Design system: shadcn/ui-style components (copy-in, CVA variants) on Radix-compatible primitives, mapped onto the existing 26
  `--brand-*` tokens through a semantic `--ui-*` layer; Montserrat (titles) + Inter (body); light theme for branded areas,
  fixed Prometheon light+dark for the platform area.
- **CSP-safe by construction** (`style-src 'self'` stays): primitives that inject `<style>` at runtime are excluded; a Playwright
  fixture fails any test that emits a `securitypolicyviolation`.
- CSP-safe chart kit (hand-rolled SVG: sparkline, area/line, bars, donut) with accessible data-table fallback.
- App shell: React Router 7 (library mode), TanStack Query provider, session guard, role-based area registry with lazy chunks,
  sidebar + topbar + user menu + breadcrumbs, responsive drawer, toasts, command palette scaffold, empty/skeleton/error states.
- Port the five existing pages (Overview, Members, Gateway, Catalog, Branding) + Login into the new kit under the Company area;
  all existing tests (158 unit/ui + 2 e2e) stay green, DOM roles/labels stable.
- Test infrastructure: `@axe-core/playwright` helper, CSP-violation fixture, responsive + visual-quality assertions, e2e harness
  extensions (area-aware login helpers).

### Out of Scope
- Platform and portal screens (changes 8 and 9); only registered stubs/route manifests ship here.
- Any control-plane change (the SPA history fallback under `/admin/*` already exists in `admin_mount.py`).
- Storybook, i18n, mobile-native, light/dark for branded company areas (company themes are light only to keep palette contrast guarantees).

## Capabilities

### New Capabilities
- `admin-design-system`: tokens (semantic layer, dark mode), components, a11y + CSP rules, responsive and visual-quality bar.
- `admin-app-shell`: router, providers, session/role guard, area registry, shell chrome, notifications, command palette scaffold.
- `admin-chart-kit`: CSP-safe SVG charts with accessible fallbacks and pure scale/format utilities.

### Modified Capabilities
- (none in `openspec/specs/`; the existing admin pages keep their behaviour — covered by `admin-app-shell` port requirements)

## Approach

1. Foundation slice first: pinned deps + semantic tokens + CSP-violation fixture, so every later slice is gated by it.
2. Kit in two slices (core inputs/surfaces; overlays/feedback/data), charts in one, shell in one, then page ports behind the new
   shell. During S5 the shell mounts the *legacy* pages unchanged, so each slice leaves `main` green and deployable.
3. Dialogs/sheets/confirm use native `<dialog>.showModal()` (focus trap, inert background, Esc for free) because
   `react-remove-scroll`/`react-style-singleton` (used by Radix Dialog/Select modal) and Sonner/ScrollArea inject `<style>`.
   Allow-list of Radix primitives is validated by the CSP fixture in slice 1 (spike) and recorded in design.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `admin/package.json`, lockfile | Modified | pinned: react-router, @tanstack/react-query, react-hook-form, zod, @hookform/resolvers, selected @radix-ui/react-*, cmdk, class-variance-authority, clsx, tailwind-merge, lucide-react, @axe-core/playwright |
| `admin/src/ui/**` | New | design-system components |
| `admin/src/charts/**` | New | SVG chart kit + scale/format utils |
| `admin/src/shell/**`, `admin/src/areas/**` | New | router, providers, guards, chrome, area registry |
| `admin/src/brand/tokens.css` | Modified | semantic `--ui-*` layer + dark mode |
| `admin/src/pages/**`, `components/Console.tsx` | Modified/Removed | ported to kit; Console view-switch replaced by router |
| `admin/tests/**`, `admin/e2e/**` | Modified/New | axe, CSP, responsive, kit gallery, ported suites |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| A dependency injects `<style>` → CSP violation only visible at runtime | High | slice-1 CSP-violation fixture on every UI test + a "kit gallery" test that opens every overlay |
| Port regresses the 158 existing tests | Med | port page-by-page, keep roles/labels, tests move with the page in the same commit |
| Dark mode vs. brand variables (inline `setProperty` outranks stylesheet) | Med | dark overrides only `--ui-*`; brand vars untouched; platform applies fixed theme via the same applier |
| Bundle growth | Low | route-level lazy chunks per area; size budget check in build (warn > 250 kB gz initial) |
| Dependency supply chain | Low | exact pins, lockfile, `npm audit` in slice 1, official registry only |

## Rollback Plan

Slices are additive until S5. Revert order is the reverse stack; S5 is the only slice replacing `App.tsx`/`Console.tsx`
(single revert restores the legacy shell because S6/S7 depend on it). `src/forge/web/admin` build output is gitignored.

## Dependencies / Contract (this change)

| ID | Assumption | Status |
|----|------------|--------|
| SC1 | `GET /forge/v1/platform/me` → `{role, mfa}` (from `fv2-platform-core`); 403/404 ⇒ "not a platform account" | tolerated absent |
| SC2 | `GET /forge/v1/accounts/me` unchanged | exists |
| SC3 | `/admin/*` serves `index.html` for extension-less paths | exists (`admin_mount.py`) |
| SC4 | CSP unchanged (`style-src 'self'`) | exists |

## Success Criteria

- [ ] `npm run test:unit`, `npm run typecheck`, `npm run build`, `npm run test:e2e` (via `scripts\admin-e2e.ps1`) green at every slice.
- [ ] axe: zero serious/critical violations on every shell route in light (and dark for platform) at 375/768/1280.
- [ ] Zero `securitypolicyviolation` events across the kit gallery and all routes.
- [ ] Existing 158 tests + 2 e2e green after S7 with DOM roles unchanged.
