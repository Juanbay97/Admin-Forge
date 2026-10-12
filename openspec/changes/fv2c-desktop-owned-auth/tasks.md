# Tasks: fv2c-desktop-owned-auth

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~6.5k (incl. ~2.1k pure deletions) |
| 400-line budget risk | High (budget in use: 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | 8 slices, one stack, FIRST in client queue |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units (branch prefix `fv2c-da-`)

| Unit | Goal | Base | Est. lines |
|------|------|------|-----------|
| D1 | Delete entra_store + IPC/wiring, Entra-absence test (initial, allow-listing remaining) | `feat/mvp-v1-wl-c4c-client-branding-e2e` | ~700 |
| D2 | Delete entra_transport + entra_session (pure deletion) | D1 | ~900 (size:exception recommended: deletion only) |
| D3 | Delete entra_pkce, Cargo deps, frontend callers; Entra-absence test strict | D2 | ~700 |
| D4 | `forge_origin.py` https allow-listed CP origin in router/workers | D3 | ~650 |
| D5 | Attested guard replaces quarantine panic; build.rs, verifier attestation | D4 | ~700 |
| D6 | Rust router sidecar launcher (backend.rs), parity test | D5 | ~800 |
| D7 | config.rs + deep_link.rs + frontend desktop gate/change-company | D6 | ~850 -> split if >800 at apply |
| D8 | NSIS config/hook, scheme, tauri.conf cleanup, verify-bundle, update hook, docs | D7 | ~800 |

## Phase 1: Entra removal (D1-D3)
- [ ] 1.1 RED `tests/forge-desktop-no-entra.test.mjs` scanning desktop-tauri, frontend/src, tauri.conf for `entra|microsoftonline|msal` (expects failures)
- [ ] 1.2 D1: delete `entra_store.rs`; remove its IPC commands in `commands.rs`/`lib.rs` mods; `cargo test` baseline recorded first
- [ ] 1.3 D2: delete `entra_transport.rs`, `entra_session.rs` and callers
- [ ] 1.4 D3: delete `entra_pkce.rs`, prune Cargo deps used only by Entra, delete frontend Entra bridge calls; test green

## Phase 2: Remote origin policy (D4)
- [ ] 2.1 RED `backend/tests/test_forge_origin.py`: loopback ok; allow-listed https ok; not-listed/IP literal/userinfo/path/port/redirect rejected
- [ ] 2.2 `app/forge_origin.py`; swap into `WorkspaceConfig`/`RouterConfig`; `--allow-origin` arg; httpx `follow_redirects=False`
- [ ] 2.3 Keep `test_forge_router_pool`, `test_forge_router_cli`, `test_forge_launch` green

## Phase 3: Guard + sidecar (D5-D6)
- [ ] 3.1 RED Rust test: guard fails closed without/with tampered attestation; passes with valid; no env bypass
- [ ] 3.2 Verifier writes attestation; `build.rs` embeds; replace `lib.rs:41` call
- [ ] 3.3 RED Rust + node parity test (router argv/env vs `forge-managed.mjs`); implement `backend.rs` router spawn/stop/health-wait/kill-on-close
- [ ] 3.4 `build:backend` PyInstaller spec runs in router mode; `verify-bundle` check

## Phase 4: Config, deep link, UI (D7)
- [ ] 4.1 RED `config.rs` precedence + hostile-link table tests; implement `config.rs`, `deep_link.rs`, atomic `company.json`
- [ ] 4.2 RED frontend unit: configured code satisfies gate, brand fetched pre-login, change-company confirm discards state
- [ ] 4.3 Implement `forge-desktop.ts` + gate wiring; `npx tsc --noEmit`

## Phase 5: Installer + docs (D8)
- [ ] 5.1 RED packaging test: single nsis target, no signingIdentity, deep-link scheme, CSP loopback-only, sidecar resource
- [ ] 5.2 `installer.nsh` (`/CODE=`,`/CP=` -> `forge-company.json`), tauri.conf cleanup, checksums
- [ ] 5.3 `updater_hook.rs` off by default; sha256 + monotonic version tests
- [ ] 5.4 Docs: build, config precedence, user-run smoke checklist

## Verification commands (record exact result per slice)
- py: `cd clients/openyak/tests; ..\backend\.venv\Scripts\python.exe -m unittest <explicit modules>`
- node: `node --test tests/forge-desktop-*.test.mjs tests/forge-packaging.test.mjs tests/forge-managed-launcher.test.mjs`
- frontend: `cd frontend; npm run test:unit; npx tsc --noEmit`
- rust: `cd desktop-tauri/src-tauri; cargo test`
