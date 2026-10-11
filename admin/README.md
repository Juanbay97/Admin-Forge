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
| `npm run typecheck` | `tsc --noEmit` |
| `npm run build` | Production bundle |

The `ui` tests build into `.test-dist` (ignored) and serve it with the exact CSP the control
plane sends; `tests/csp.ts` is checked against `src/forge/admin_mount.py` so they cannot drift.

## Theming

`src/brand/theme.ts` is the single source of colours, fonts and marks. `applyBrandTheme()` writes
`--brand-*` variables that Tailwind reads through `src/brand/tokens.css`; a per-company theme is
another `BrandTheme` object (`createTheme`), not a component edit.

Fonts (Montserrat, Inter; latin subset) are self-hosted in `public/fonts` under the SIL Open
Font License; the licences ship next to the files.
