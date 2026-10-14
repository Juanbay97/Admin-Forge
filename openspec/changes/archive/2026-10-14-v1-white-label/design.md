# Design: v1 White-label

## Technical Approach

Branding is a small typed record per org, validated on the server and re-validated on every client. A shared deterministic palette generator turns 3 colors into full light/dark tokens with enforced contrast. Public branding reaches the client through the local bridge (same origin), is cached in the presentation dir, and is applied only via `style.setProperty`. Follows existing patterns: SECURITY DEFINER functions + dedicated roles (0015), pure validators + store/port split, additive endpoints (bootstrap and contract pins untouched).

**Stacking**: applies AFTER `v1-multiuser`. CP chain after its last CP slice (migration number = next free after multiuser's; expected `0025`). Client chain after its last client slice. New modules only; no edit to multiuser's hot files beyond one-line mounts (see File Changes).

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Asset handling | Pure-Python header parse + chunk allow-list rewrite (PNG: IHDR/PLTE/tRNS/IDAT/IEND; WebP: VP8/VP8L/VP8X without EXIF/XMP/ICCP) | Pillow re-encode | No decoder attack surface/dependency; dimensions from headers, decompression bombs impossible (never decoded) |
| Asset storage | `bytea` in PG, key (org, sha256), served by sha only if referenced by a current revision | object store | <=256 KB, 3 per org; transactional with revision |
| Revisioning | Current row + append-only `organization_branding_revisions` (acts as audit); CAS on `expected_revision`; reset = new revision | draft/publish | Save is publish; preview is client-side |
| Palette | 3 knobs -> 27 tokens, generator in TS (admin + client), golden vectors file shared; server checks knob feasibility (primary >=3:1 vs white) in Python | server-expanded tokens | Server never emits CSS; tokens can be re-derived and verified |
| Public lookup | SECURITY DEFINER `branding_public_read(slug)` granted to dedicated `forge_branding_service`; identical 404 for unknown/inactive; unbranded active org = default rev 0 | open RLS read | No role gets table access; slug is a company code, enumeration rate-limited |
| Rate limit | In-process token bucket per client IP + global cap, 429 + Retry-After | external limiter | Matches single-process loopback CP; documented limit for multi-instance |
| Client delivery | Bridge module proxies/caches `GET /forge/v1/branding` and assets same-origin | browser fetches CP | `connect-src 'self'`, offline cache, no CORS |
| Refresh | ETag revalidate at start/login and on a 5 min timer | ride `config_revision` | Avoids changing pinned bootstrap semantics |
| Client CSP | `next.config.ts headers()`: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'` | nonce CSP | Next hydration needs inline scripts; nonce impossible in static export. Tighten Tauri CSP `https://*` after smoke |
| Fonts | Allow-list ids {inter, montserrat, source-sans-3, ibm-plex-sans, nunito-sans, roboto}, OFL woff2 bundled in admin and client | arbitrary URLs | Offline, CSP-safe |

## Data Flow

    Admin Branding page --PUT (CAS)--> CP validators --> branding_save() --> current row + revision row
    Client code screen --> bridge /forge/v1/branding?org=slug --> CP public read (rate-limited, ETag)
         bridge: validate size/JSON, fetch assets, cache in presentation/ --> renderer: parse typed schema
         --> palette generator --> style.setProperty / BrandMark / title / favicon

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/NNNN_org_branding.sql` | Create | `organization_branding`, `organization_branding_revisions`, `branding_assets`; roles `forge_branding_authority/service`; RLS; functions `branding_save/read/public_read/asset_get/reset` |
| `src/forge/branding.py` | Create | pure validators, contrast, font list, defaults |
| `src/forge/branding_assets.py` | Create | PNG/WebP sanitizer |
| `src/forge/branding_store.py` | Create | Postgres port |
| `src/forge/branding_api.py` | Create | router, rate limiter, ETag; `mvp_local.py` +1 mount |
| `contract/branding-palette.vectors.json` | Create | shared golden vectors |
| `admin/src/brand/{theme,palette}.ts`, `admin/src/api/branding.ts`, `admin/src/pages/Branding.tsx`, `admin/src/components/BrandPreview.tsx` | Create/Modify | applier, editor, preview |
| client `frontend/src/theme/{brand-input,palette,forge-theme}.ts` | Create/Modify | schema, generator, setProperty applier |
| client `frontend/src/lib/{branding-store,branding-routes}.ts`, `components/forge/{company-code-gate,brand-provider}.tsx` | Create | gate, cache, provider |
| client `backend/app/forge_branding.py` | Create | proxy + cache; mounted in whichever app owns pre-login routes after multiuser |
| client `frontend/src/middleware.ts` | Modify | +1 line calling `isBrandingRoute` (multiuser also edits; rebase) |
| client `frontend/next.config.ts`, `desktop-tauri/src-tauri/icons/*` | Modify | CSP, Prometheon icons |
| `scripts/branding-smoke.ps1` | Create | own script; `mvp-smoke.ps1` untouched |

## Interfaces / Contracts

```ts
type Branding = { revision: number; name: string; loginCopy: string;
  theme: { primary: string; accent: string; tint: string; heading: FontId; body: FontId };
  assets: { logoLight?: string; logoDark?: string; isotipo?: string }; // sha256 -> /forge/v1/branding/assets/<sha>
}
```
Admin: `GET/PUT /forge/v1/orgs/{o}/branding`, `POST .../branding/assets?kind=` (raw body, image/png|webp), `POST .../branding/reset`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | validators, contrast, sanitizer (fuzz truncated/oversize/metadata), palette vectors, schema rejection | unittest / `npm run test:unit` / `node --test <files>` |
| Integration | RLS, CAS, audit, cross-org, public read via `scripts\test-postgres.ps1` | PG modules |
| API | rate limit, ETag, headers, no leakage | unittest |
| E2E | two orgs differ in admin and client; CSP no violations | Playwright + `branding-smoke.ps1` |

## Migration / Rollout

Forward-only additive migration; no rows = default. Open items: confirm contract pin does not list endpoints; source isotipo (241x329) too small for 1024 icons.

## Open Questions

- [ ] Does multiuser's router or worker own pre-login routes? (decides mount point of `forge_branding.py`)
- [ ] Vector/higher-res isotipo source for Tauri icons?
