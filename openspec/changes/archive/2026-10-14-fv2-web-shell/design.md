# Design: fv2-web-shell

## Technical Approach

Keep Vite 7 / React 19 / Tailwind 4 / Playwright; add a thin, CSP-audited layer: semantic tokens → kit (`src/ui`) → charts
(`src/charts`) → shell (`src/shell`) → areas (`src/areas/{platform,company,portal}`). `brand/*` stays the single source of company
theme; the platform area re-uses the same applier with a fixed theme. All new third-party code is vetted by one executable rule:
**no `securitypolicyviolation` in any UI test** (fixture applied globally from slice 1).

## Architecture Decisions

### Decision: Primitives allow-list under CSP
**Choice**: Radix (non-modal) for Tabs, Tooltip, Popover, DropdownMenu(`modal={false}`), Switch, Checkbox, RadioGroup, Label, Slot;
native `<dialog>` for Dialog/AlertDialog/Sheet/Command palette; native `<select>` styled; own Toast store/region; cmdk inside `<dialog>`.
**Alternatives**: Radix Dialog/Select/ScrollArea (use `react-remove-scroll` → `react-style-singleton` and ScrollArea inject `<style>`
→ violate `style-src 'self'`); Sonner (injects CSS on import); Base UI / React Aria (heavier, no accessibility gain over native dialog);
loosening CSP with a nonce (server change, weakens the platform console that holds the owner session).
**Rationale**: native `<dialog>` gives focus trap, inert background, Esc and top-layer; zero-style-injection is provable by the
fixture. Slice 1 is a spike: if any allow-listed primitive fails the fixture it moves to the "own implementation" column.

### Decision: Charts as hand-rolled SVG
**Choice**: ~600 lines of SVG components + pure scale utils. **Alternatives**: uPlot (canvas + injects a `<style>` for its base CSS unless the
stylesheet is imported manually — workable but still needs CSP verification and a11y wrapper), Recharts/visx (Recharts injects styles).
**Rationale**: five chart types, tiny data (≤90 points), full control of a11y table + tokens, no dependency risk.

### Decision: Semantic token layer with platform-only dark mode
`tokens.css` adds `--ui-*` defined from `--brand-*` (light). `:root[data-mode="dark"]` overrides only `--ui-*` (never `--brand-*`,
because `applyBrandTheme` writes those inline and inline wins). Dark applies only in `/platform` (`data-area="platform"`); leaving the
area removes `data-mode`. Company palettes were contrast-verified in light only, so branded areas stay light.

### Decision: Router layout, return target = URL
`createBrowserRouter` (basename `/admin`), `RequireSession` layout route renders `<Login>` in place when no token (URL untouched, so
sign-in returns to the same path without storage). `AreaGate` checks capability from a `useIdentity()` query (`platform/me` ∥
`accounts/me`). Area modules are `React.lazy`; manifest (`nav`, `routes`, `requires`) is eager and tiny.

### Decision: Data layer
TanStack Query v5 with a global `QueryCache.onError` → 401 handler (clear session + cache, show expired notice). New API modules parse
with zod (`api/*.ts` legacy ones keep their hand types until ported; ported pages use `useQuery` over the same `Services`).
Services stay injectable (`Services` + `ServicesProvider`) so UI tests keep the mocked same-origin API.

### Decision: Port strategy keeps `main` green
S5 mounts the new shell and renders the legacy pages unchanged inside `CompanyArea`; S6/S7 replace each page with kit versions
together with their tests. Legacy `Console.tsx` is deleted in S7 only.

## Data Flow

    main.tsx → <Providers(QueryClient, ServicesProvider, Toasts)> → RouterProvider
      /admin/* → RequireSession ──no token──► <Login>
                    │ token
                    ▼
               useIdentity(): platform/me ∥ accounts/me ──► home area (redirect at /admin)
                    ▼
               AreaGate(requires) ──► lazy Area ──► AppShell(sidebar, topbar, <Outlet/>)
      401 anywhere ──► QueryCache.onError ──► session.clear + queryClient.clear ──► Login (same URL)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `admin/package.json`, `package-lock.json` | Modify | exact pins (registry-resolved at apply time, recorded in README table) |
| `admin/src/brand/tokens.css` | Modify | `--ui-*` layer, dark overrides, type scale, focus ring |
| `admin/src/brand/platformTheme.ts` | Create | fixed Prometheon theme + `applyPlatformTheme()` |
| `admin/src/lib/{cn,format}.ts` | Create | class merge; tokens/cost/date formatters |
| `admin/src/ui/*.tsx` (~30) | Create | components listed in spec |
| `admin/src/ui/overlay/{Dialog,Sheet,Toast,Command}.tsx` | Create | native dialog based |
| `admin/src/charts/{scale,ticks,path,Sparkline,AreaChart,BarChart,StackedBars,Donut,ChartFrame}.tsx` | Create | chart kit |
| `admin/src/shell/{router,Providers,RequireSession,AreaGate,AppShell,Sidebar,Topbar,UserMenu,Breadcrumbs,CommandPalette,identity}.tsx` | Create | shell |
| `admin/src/areas/{platform,company,portal}/manifest.ts` | Create | nav + routes + `requires` |
| `admin/src/areas/company/*` | Create | ported pages (from `pages/*`) |
| `admin/src/App.tsx`, `components/Console.tsx` | Modify/Delete | replaced by router |
| `admin/tests/ui/support.ts` | Modify | `expectNoCspViolations`, `expectAccessible`, viewport helpers |
| `admin/tests/ui/kit-gallery.spec.ts`, `shell.spec.ts`, `charts.spec.ts` | Create | UI layer |
| `admin/tests/unit/{format,ticks,scale,path,identity,cn,toast-store}.spec.ts` | Create | logic |
| `admin/e2e/shell.spec.ts` | Create | real stack: login, role redirect, deep link, 401 expiry, responsive nav |
| `admin/README.md` | Modify | stack table, primitives allow-list, CSP rules, a11y workflow |

## Interfaces / Contracts

```ts
export type AreaId = "platform" | "company" | "portal";
export interface AreaManifest {
  id: AreaId; basePath: `/${AreaId}`;
  requires: (id: Identity) => boolean;
  nav: Array<{ label: string; to: string; icon: IconName; requires?: (id: Identity) => boolean }>;
  routes: RouteObject[];            // lazy()
}
export interface Identity { account: Me["account"]; platform: { role: "platform_owner" | "platform_viewer"; mfaLevel: "none" | "totp" } | null; orgs: Organization[]; }
export function homeFor(id: Identity): AreaId;   // platform ⇒ company(admin) ⇒ portal
export const ERROR_MESSAGES: Record<string, string>; // code → user copy, shared by all areas
```

Visual quality bar (checked by tests where measurable, by `playwright --ui` screenshots attached to PR otherwise): 4px grid;
Montserrat headings / Inter body; sidebar 256px (64 collapsed); topbar 56px; cards 12px radius, 1px border, no heavy shadows; tables 14px with
44px rows and sticky header; one primary action per view; status colours always paired with icon/text; skeletons match final layout
(no layout shift).

## Testing Strategy (strict TDD: RED test first in each slice)

| Layer | What | Approach |
|-------|------|----------|
| Unit (`tests/unit`) | ticks/scales/path/format, identity→home policy, toast store, `cn`, error-code map | pure functions, table-driven |
| UI (`tests/ui`, prod bundle + mocked API, `.test-dist`) | kit gallery (all variants, overlays), charts, shell nav/guards/401, ported pages | axe + CSP + viewport helpers in every spec |
| e2e (`e2e`, real stack via `scripts\admin-e2e.ps1`) | login → role redirect, deep link, expiry, ported admin flow, branding | system Chrome; no mocks |
| Gates | `typecheck`, `build`, bundle size note | CI |

## Migration / Rollout

Static bundle, no data migration. Feature is the new shell itself; rollback = revert S5 (restores legacy `Console`).
README documents the localStorage `forge.mode` key (platform theme preference only; token still never stored).

## Open Questions
- [ ] Confirm exact versions at apply (registry resolve + `npm audit`); record in README.
- [ ] If the spike shows a Radix primitive violates CSP, swap to own implementation (tracked in slice 1 notes).
