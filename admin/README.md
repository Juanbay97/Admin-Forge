# Prometheon Forge Admin

Same-origin administration SPA (Vite + React + TypeScript + Tailwind 4) served by the
control plane at `/admin`. The bearer token lives in memory only; nothing is written to
storage, cookies or URLs, and no remote script, font or style is loaded.

## Quick path

1. `npm ci` (versions are pinned; React, TypeScript, Tailwind and Playwright match the client lockfile).
2. `npm run build` writes the bundle to `../src/forge/web/admin` (gitignored, never committed).
3. Start the control plane (`scripts\mvp-local.ps1`) and open `http://127.0.0.1:3410/admin/`.

## Checks

| Command | What it proves |
|---------|----------------|
| `npm run test:unit` | Logic units (`unit` project) and the production bundle in system Chrome against a mocked same-origin API (`ui` project) |
| `npm run test:e2e` | Real flow in system Chrome against the running local stack; start it through `scripts\admin-e2e.ps1` (builds, starts the owned stack, runs, stops, confirms cleanup) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run build` | Production bundle |

The `ui` tests build into `.test-dist` (ignored) and serve it with the exact CSP the control
plane sends; `tests/csp.ts` is checked against `src/forge/admin_mount.py` so they cannot drift.

## Theming

`src/brand/theme.ts` is the single source of colours, fonts and marks. `applyBrandTheme()` writes
`--brand-*` variables that Tailwind reads through `src/brand/tokens.css`; a per-company theme is
another `BrandTheme` object (`themeFromBranding`, `createTheme`), not a component edit. Values only
reach the page through `src/brand/applier.ts` (`style.setProperty`, validated, all-or-nothing), never as
CSS text, so the CSP stays `style-src 'self'`.

The Branding page (`src/pages/Branding.tsx`) edits an organization's branding and previews it in two
isolated containers (`src/components/BrandPreview.tsx`) driven by `src/brand/palette.ts`. That generator
reproduces `contract/branding-palette.vectors.json`, shared with the Python validators and the client;
`tests/unit/palette.spec.ts` compares the client's copy with line endings normalised. An uploaded logo is
previewed from a locally decoded canvas because the CSP forbids `blob:` and `data:` images.

Fonts: the six vetted typefaces (Inter, Montserrat, Source Sans 3, IBM Plex Sans, Nunito Sans, Roboto;
latin subset) are self-hosted in `public/fonts` under the SIL Open Font License; the licences and the
source of each file (`SOURCES.md`) ship next to them and a face only downloads when a theme uses it.

## UI foundation (fv2-web-shell)

Exact pins, resolved from the official registry at apply time (`npm audit`: 0 vulnerabilities):

| Package | Version | Use |
|---------|---------|-----|
| `react-router` | 7.18.4 | router (library mode); v8 needs React >= 19.2.7 |
| `@tanstack/react-query` | 5.104.2 | server state |
| `react-hook-form`, `@hookform/resolvers`, `zod` | 7.90.0, 5.9.1, 4.6.7 | forms and response parsing |
| `@radix-ui/react-{tabs,tooltip,popover,dropdown-menu,switch,checkbox,radio-group,label,slot}` | see `package.json` | non-modal primitives |
| `cmdk`, `lucide-react` | 1.1.1, 1.55.0 | command palette list, SVG icons |
| `class-variance-authority`, `clsx`, `tailwind-merge` | 0.7.1, 2.1.1, 3.7.0 | variants and class merging |
| `@axe-core/playwright` (dev) | 4.13.0 | accessibility gate |

### CSP rules for the kit

The CSP is `style-src 'self'` and stays that way. Anything that injects a `<style>` element, sets the `style`
attribute through `setAttribute`/`innerHTML`, uses `eval`/`new Function`, or loads a remote resource is out.
Styling is by class names and CSSOM (`element.style.x`, the React `style` prop) only.

Allow-listed primitives, each proven by `tests/ui/primitives-csp.spec.ts` (slice-1 spike, all passed):
Radix Tabs, Tooltip, Popover, DropdownMenu (`modal={false}`), Switch, Checkbox, RadioGroup, Label, Slot; `cmdk`;
`lucide-react`. Dialog, AlertDialog, Sheet and the command palette use the native `<dialog>`; Radix Dialog/Select/
ScrollArea (`react-remove-scroll` / `react-style-singleton` inject `<style>`) and Sonner are not used.

zod compiles validators with `new Function` unless told not to, and under `script-src 'self'` the probe itself is
reported as a `securitypolicyviolation`. `src/ui/form.ts` calls `config({ jitless: true })`; use `useZodForm` (or import
that module) before running any schema.

### Quality gates

Every UI spec runs with an automatic CSP watch (`tests/ui/support.ts`): any `securitypolicyviolation` or CSP console
error fails the test. `tests/ui/quality.ts` adds `expectAccessible` (axe, WCAG 2.0/2.1 A/AA, serious and critical
fail), `expectNoHorizontalScroll` and the `viewports` (375, 768, 1280). The kit gallery (`/admin/?kit=<name>`)
exists only in the UI-test build (`VITE_KIT=1`); production builds drop it at compile time.

Tokens: components style only through the semantic `--ui-*` layer in `src/brand/tokens.css`, derived from the
`--brand-*` variables; dark mode (`data-mode="dark"`, platform area only) overrides `--ui-*` and nothing else.

`tokens.css` writes the fixed status colours and white as `rgb()`/named colours: `unit/theme.spec.ts` keeps the stylesheet free of `#RRGGBB` literals so brand colours stay single-sourced in `brand/theme.ts`.
