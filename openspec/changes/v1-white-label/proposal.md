# Proposal: v1 White-label (per-company look & feel)

## Intent

Each company must see its own identity (logo, isotipo/favicon, palette, font, product name, login copy) in BOTH the admin panel and the client, editable by its admin without a rebuild. Today branding is compiled (`admin/src/brand/theme.ts`, client `theme/brand.ts`), the MVP explicitly forbade tenant theming, there is no pre-login org discovery, and client `applyTheme` writes raw `style.textContent` (CSS injection if a server value ever reaches it); the client has no CSP.

## Scope

### In Scope
- CP: `organization_branding` + revision/audit history + `branding_assets` (migration, RLS, SECURITY DEFINER functions, same pattern as 0015).
- Validation: hex colors, WCAG contrast, vetted self-hosted font list, name <=40, login copy <=280 plain text; assets PNG/WebP only (no SVG), <=256 KB, <=1024 px, header-parsed, metadata chunks stripped.
- API: public `GET /forge/v1/branding?org=<slug>` (rate-limited, ETag, public fields only); content-addressed `GET /forge/v1/branding/assets/{sha256}`; admin read/save(CAS)/upload/reset; member projection `GET /forge/v1/orgs/{o}/branding`.
- Admin: Branding page, live preview, reset to Prometheon default; admin themed per org.
- Client: company-code first launch, cached branding (presentation dir), typed-token theme applier (no raw CSS), client CSP, runtime title/logo/favicon, Tauri icons replaced with Prometheon art.
- E2E: two orgs with different branding visible in admin and client.

### Out of Scope
- Per-company installers/icons, custom domains, custom font upload, SVG, draft/approval workflow, dark/light per-company overrides beyond generated palette.

## Capabilities

### New Capabilities
- `org-branding`: storage, validation, assets, revisioning, audit, public/admin/member endpoints.
- `admin-branding`: admin Branding page, live preview, themed admin shell.
- `client-branding`: company-code launch, cache, safe theme application, CSP, icons.

### Modified Capabilities
- `client-rebrand` (mvp change): "Brand seam" no longer forbids tenant theming; bootstrap payload stays unchanged and branding rides its own endpoint.

## Approach

Compact brand input (primary, accent, tint, heading/body font, name, copy, 3 assets) stored per org; a deterministic palette generator (golden vectors shared by both repos) expands it to full light/dark tokens and enforces contrast. Servers never send CSS: clients apply typed tokens via `style.setProperty`. Public branding is fetched through the local bridge (same-origin, CSP-compatible) and cached.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/NNNN_org_branding.sql` | New | tables, roles, functions |
| `src/forge/branding*.py`, `api` wiring | New | validators, store, routes |
| `admin/src/{brand,api,pages,components}` | Modified/New | applier, Branding page |
| client `frontend/src/theme`, `components/forge`, `next.config.ts` | Modified/New | applier, gate, CSP |
| client `backend/app/forge_branding.py` | New | proxy + cache |
| `src-tauri/icons/` | Modified | Prometheon art |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Stacks on v1-multiuser (routing/worker, middleware, smoke script) | High | Apply after it; new modules, one-line mounts; re-read its final routing first |
| Image parsing attack surface | Med | No decode; chunk allow-list rewrite; fuzz tests |
| Next needs inline scripts under CSP | Med | `unsafe-inline` scripts only, everything else strict |
| Source isotipo 241x329 is low-res for icons | High | Pad/upscale or request vector source |

## Rollback Plan

Forward-only migration adds tables only; revert slices in reverse order. Without a row every surface falls back to the Prometheon default theme.

## Dependencies

- `v1-multiuser` applied FIRST: CP slices stack after its last CP slice; client slices after its last client slice. Migration number = next free after multiuser's.

## Success Criteria

- [ ] Two orgs show distinct branding in admin and client (E2E).
- [ ] No server-supplied CSS reaches the DOM; client CSP active.
- [ ] Reset restores Prometheon default; Apache-2.0 LICENSE/NOTICE unchanged.
