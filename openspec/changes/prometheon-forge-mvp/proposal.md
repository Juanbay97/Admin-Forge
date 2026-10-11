# Proposal: Prometheon Forge functional MVP

## Intent

Forge has a verified server side (owned accounts, encrypted per-org gateway key, catalog, streaming proxy, RLS) but no runnable product: no admin web, no member/identity APIs, hard-coded gateway URL, client quarantined behind `forge-isolation.mjs`, manual stdin key flow, OpenYak branding. Deliver one local end-to-end flow a company can use.

**Flow**: admin logs into admin web → manages members (invite/list/suspend) → configures gateway (allow-listed URL + encrypted key) and publishes catalog → member logs into rebranded "Prometheon Forge" client → sees only published models → streams chat via Forge backend → fake gateway; no keys client-side; tenant isolation holds.

## Scope

### In Scope
- Fake OpenAI-compatible gateway (records `Authorization`); live OmniRoute stays a configurable slot, no credentials used.
- Per-company gateway base URL from a deployment allow-list (migration 0019).
- `GET /accounts/me`, departments read/create, members list + suspend/reactivate (last-admin guard).
- Provisioning CLI + `forge.mvp_local` explicit-config serve composition + two-org seed + launcher.
- Admin SPA `admin/` (Vite + React 19 + TS + Tailwind 4, Montserrat/Inter), served at `/admin`.
- Client: lift quarantine via one productized launcher; owned-account login; delete manual key flow and in-client gateway admin; visible rebrand (Prometheon umbrella, same visual identity, assets from `Marca/`); `brand.ts` seam.
- E2E isolation proof (real PG + fake gateway), Playwright admin + client suites, `docs/mvp-local.md`.

### Out of Scope
- Per-company theming/branding (seam only), installer/Tauri/NSIS/signing, Entra, SMTP (local `.eml` mailbox), tools in chat, deep internal renames (`openyak-*` keys, tokens, crate/package ids; record as tech-debt), role edit/department reassignment, outbox worker/P1b bridge, live OmniRoute verification, push/PR/remote.

## Capabilities

### New Capabilities
- `gateway-origin-policy`: allow-listed per-org base URL (https; http loopback only in dev profile).
- `identity-discovery`: `/accounts/me` orgs + roles.
- `member-administration`: departments, member list, suspend/reactivate.
- `mvp-local-runtime`: config-driven serve, provisioning, two-org seed, admin mount.
- `fake-gateway`: contract-exact OpenAI-compatible test gateway.
- `admin-web`: partitioned per-company admin SPA.
- `managed-client-launch`: sanctioned launcher replacing quarantine; owned-account login, server-discovered context.
- `client-rebrand`: Prometheon Forge visible identity.

### Modified Capabilities
None (`openspec/specs/` is empty).

## Approach

Two stacked-to-main chains, no push. Create local `main` at `7e4a149` (control plane) and `acdb53b` (client, keep `a9adf9f` ref for upstream diff). Each slice ≤800 lines incl. tests/docs, strict TDD, stacked then fast-forwarded to `main`. Contract pin between repos (`me`/models/chat shapes). Browser-hosted client built with `next build && next start` for E2E.

| Slice | Content |
|---|---|
| A0 | Docs (exploration/proposal/spec/design/tasks) |
| A1 | Fake gateway + adapter contract tests |
| A2 | Origin policy, migration 0019, readiness checkpoint (fallback: fixed endpoint + trusted transport) |
| A3 | `/accounts/me` + departments |
| A4 | Members list + suspend/reactivate |
| A5 | Provisioning CLI, `mvp_local`, admin mount, launcher |
| A6 | API isolation E2E proof |
| B1–B4 | Admin: scaffold/login/org picker → members → gateway+catalog → Playwright |
| C1 | Remove manual key flow + in-client admin |
| C2 | Productized launcher, `me`-based context, drop fixture gating |
| C3a/C3b | Brand tokens/assets/fonts/icons; visible strings/`BrandMark` |
| C4 | Client Playwright E2E |
| Final | Cross-repo smoke + `docs/mvp-local.md` |

Order: A1→A6; B after A3/A4; C after A3; then final.

## Affected Areas

| Area | Impact |
|---|---|
| `src/forge/{gateway_*,account_api}.py`, `migrations/0019` | Modified |
| `src/forge/mvp_local*`, `admin/`, `src/forge/web/admin/`, `tests/support/fake_gateway.py` | New |
| `clients/openyak` scripts/backend/frontend (forge-isolation, `ManagedGateway`, `GatewayAdminView`, brand, i18n, icons) | Modified/Removed/New |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Real OmniRoute SSE incompatible with strict parser | Med | Fake proves contract only; live is a slot, documented |
| A2/A5 exceed 800 lines | Med | Stop and report; split, never compress |
| Migration 0019 forces checkpoint/upgrade | Med | Docker PG harness; fallback B2 |
| Quarantine lift weakens isolation | Med | Replace guard with verified isolation checks, not removal |
| Existing demo owns ports 3319/3320/3331/3332 | Med | Distinct ports; never stop/adopt |
| Cold-compile timeouts, chat limits (16 msgs/4 KiB) | High | Production build; document limit |
| npm/font supply chain | Low | Pin client-lockfile versions; local font files |

## Rollback Plan

Slices are independent commits on stacked branches; revert per slice. Migration 0019 is additive (relaxed CHECK); downgrade by restoring the fixed-endpoint CHECK only if no non-default URL rows exist. `main` branches are local-only; reset to `7e4a149`/`acdb53b`. Quarantine guard restored by reverting C2.

## Dependencies

Docker 28 + PG17 harness; Node/npm registry (authorized); `Marca/` assets; ports distinct from existing demo.

## Success Criteria

- [ ] Acceptance flow passes end to end against the fake gateway (admin + client Playwright, API proof).
- [ ] Admin A cannot read/mutate org B (404); member sees only published aliases.
- [ ] Gateway key absent from every response, log, stream and client bundle.
- [ ] Suspended member denied mid-stream; logout revokes.
- [ ] Manual key flow and in-client gateway admin deleted; no visible "OpenYak" strings.
- [ ] All slices ≤800 lines, tests green.
