# Tasks: v1 White-label

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~5.3k (10 slices, tests included; font/icon binaries excluded) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | CP W1→W6, client C1→C4 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Budget 800 lines/slice. **Dependency**: apply after `v1-multiuser`. W1 stacks on its last CP slice; C1 on its last client slice. Migration = next free number. Do not edit `mvp-smoke.ps1`; touch `forge_workspace.py`/`middleware.ts` only by one-line mounts.

### Suggested Work Units

| Unit | Goal | Notes |
|------|------|-------|
| W1 ~450 | pure validators + asset sanitizer | no DB |
| W2 ~600 | migration + store | PG tests |
| W3 ~650 | API routes, rate limit | needs W2 |
| W4 ~500 | admin applier/api/fonts | needs W3 |
| W5 ~700 | Branding page + preview | needs W4 |
| C1 ~500 | typed schema, palette, setProperty applier | independent |
| C2 ~450 | bridge proxy + cache | needs W3 |
| C3 ~650 | company-code gate, provider | needs C2, C1 |
| W6 ~300 | two-org branded seed + docs | needs W5 |
| C4 ~500 | CSP, icons, E2E | needs C3, W6 |

## Phase 1: Control plane core (W1-W3)

- [x] 1.1 RED/GREEN `src/forge/branding.py`: hex/font/length/contrast tests in `tests/test_branding.py`
- [x] 1.2 RED/GREEN `branding_assets.py`: PNG/WebP sanitizer, SVG/oversize/truncated fuzz (`test_branding_assets.py`)
- [x] 1.3 Add `contract/branding-palette.vectors.json`
- [x] 1.4 Migration `NNNN_org_branding.sql` + `tests/test_postgres_branding.py` (RLS, CAS, audit, cross-org)
- [x] 1.5 `branding_store.py` port + fake for API tests
- [x] 1.6 `branding_api.py`: public GET, assets, admin PUT/POST/reset, member projection, 429/ETag/headers tests; mount in `mvp_local.py`

## Phase 2: Admin (W4-W5)

- [x] 2.1 RED/GREEN `admin/src/brand/palette.ts` against vectors; extend `theme.ts` (name, assets, title, favicon)
- [x] 2.2 `admin/src/api/branding.ts` + model tests (`npm run test:unit`)
- [x] 2.3 Bundle 6 OFL woff2 fonts; allow-list in `tokens.css`
- [x] 2.4 `Branding.tsx` + `BrandPreview.tsx`, route in `App.tsx`; Playwright: preview, conflict, reset, CSP

## Phase 3: Client (C1-C3)

- [x] 3.1 RED/GREEN `theme/brand-input.ts` (exact-key schema, hostile payload tests)
- [x] 3.2 `theme/palette.ts` vs vectors; replace `applyTheme` `textContent` with `setProperty`; keep `themeToCss` drift test
- [x] 3.3 `backend/app/forge_branding.py` + pytest (size caps, cache, offline); `branding-routes.ts` + 1-line middleware mount
- [x] 3.4 `branding-store.ts`, `company-code-gate.tsx`, `brand-provider.tsx`; BrandMark, title, favicon, login copy
- [x] 3.5 `npm run test:unit`, `npx tsc --noEmit`

## Phase 4: Seed, security, E2E (W6, C4)

- [x] 4.1 Seed branding for org-a (Northwind Logistics) and org-b (Lumen Finance) + `docs/white-label.md`
- [x] 4.2 `next.config.ts` CSP; test header and no violation; tighten Tauri CSP after smoke
- [x] 4.3 Replace `src-tauri/icons` with Prometheon art (source from `Marca\Logos`); delete `OpenYak logo`; test LICENSE/NOTICE hashes
- [x] 4.4 `scripts/branding-smoke.ps1` + Playwright: two orgs visible in admin and client
