# Proposal: fv2c-desktop-owned-auth

Repo: `clients/openyak` (CL). Base: `feat/mvp-v1-wl-c4c-client-branding-e2e` (9235518). Program: forge-v2 change #12 (`sdd/forge-v2-program/explore` #3371). Position in client queue: **1st** (single writer per repo).

## Intent

The Tauri desktop shell is still the upstream shape: Microsoft Entra PKCE (`entra_*.rs`, ~2.1k lines), an unconditional quarantine panic (`lib.rs:41` -> `forge_build_guard::require_runtime_quarantine()`), no sidecar launch of the profile router, no company binding, CSP loopback-only, `createUpdaterArtifacts:false`, upstream macOS `signingIdentity` remnant. Product vision v2: employee installs ONE Windows installer, the app already knows the company (code embedded at download), signs in with the owned account (set via invitation link) and runs through the same router + per-profile worker architecture the web client proved in v1-multiuser. This change makes the desktop app that product.

## Scope

### In Scope
- Delete the Entra code path (Rust modules, IPC commands, frontend callers, CSP/tauri.conf entries) with a regression test that nothing Entra-related ships.
- Replace the unconditional quarantine panic with a build-attested guard (no env bypass) so the shell can run once the existing isolation verifier (`scripts/forge-isolation.mjs`) passes at build time.
- Bundle the backend as a PyInstaller sidecar started by Rust in **router mode** (`python -m app.forge_router` equivalent: same 4 args as `forge_workspace`), router owns `FORGE_BACKEND_PORT`, stopped with the app (CTRL_BREAK then taskkill /T, per v1-multiuser gotcha 7).
- Control-plane origin + company code resolution: precedence deep link `prometheon-forge://join?cp=<https-origin>&code=<slug>` > per-company installer config file > build default (production domain, configurable at build). Origin allow-list from build config, https only (loopback only in dev builds), explicit confirm on change.
- Router/worker accept an https production CP origin from an explicit allow-list (today `forge_workspace.LOOPBACK_ORIGIN` accepts only `http://127.0.0.1:<port>`); TLS verified, no cross-origin redirects.
- Frontend desktop mode uses the existing owned-account flow (`forge-accounts.ts` uses same-origin relative paths through the router); Tauri CSP stays loopback-only because the router relays all CP traffic.
- Single unsigned NSIS installer (`bundle.targets=["nsis"]`), deep-link scheme registered, per-company config hook (installer arg and/or sidecar file written by the portal download), `latest.json`-style optional update check hook (off by default, verifies sha256).
- Remove `signingIdentity` remnant; docs/runbook for building the installer.

### Out of Scope
- Code signing / SmartScreen reputation (user accepted unsigned).
- Portal/download page and `latest.json` hosting (CP changes `fv2-web-company-portal`, `fv2-deploy-compose`); this change consumes them via contract items and stubs.
- Sandbox/tool execution (`fv2c-sandbox-runner`), capability policy (`fv2c-capabilities-client`), super-app (`fv2c-superapp-host`).
- macOS/Linux bundles; auto-install of updates.

## Capabilities

### New Capabilities
- `desktop-owned-login`: desktop sign-in with owned accounts only; Entra removed; company code prefilled/locked from configuration.
- `desktop-sidecar-runtime`: Rust launches/stops the bundled router sidecar; quarantine replaced by build-attested guard.
- `desktop-company-distribution`: CP origin + company code from deep link / installer config / build default; NSIS installer; update-check hook.

### Modified Capabilities
- `managed-client-launch` (from v1-multiuser delta, not yet in main specs): the Rust sidecar launcher becomes a second launcher with the same router/argument/scrub contract as `forge-managed.mjs`.

## Approach

Reuse, don't redo: router (`forge_router.py`), workers (`forge_workspace.py`), launcher contract (`scripts/forge-managed.mjs`, `forge-launch.mjs`), branding gate and web account flow are unchanged. New Rust code is small: `config.rs` (origin/code resolution + validation), `deep_link.rs` handler, `backend.rs` modified to spawn the router with scrubbed env/explicit args. Entra deletion lands first (pure deletion, lowers risk), then config, sidecar, frontend, installer, smoke.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `desktop-tauri/src-tauri/src/entra_*.rs`, `commands.rs`, `lib.rs` | Removed/Modified | Entra gone; quarantine panic -> guard |
| `desktop-tauri/src-tauri/forge_build_guard.rs` | Modified | attested guard |
| `desktop-tauri/src-tauri/src/backend.rs` (879 lines) | Modified | spawn router sidecar |
| `desktop-tauri/src-tauri/src/config.rs`, `deep_link.rs` | New | CP origin + company code |
| `desktop-tauri/src-tauri/tauri.conf.json` | Modified | CSP, nsis, resources, deep-link, drop signingIdentity |
| `frontend/src/lib/*` (desktop auth wiring, tauri bridge) | Modified | owned-account flow in desktop, remove Entra calls |
| `scripts/verify-bundle.mjs`, `build:backend` | Modified | sidecar bundle verification |
| `tests/forge-*.test.mjs`, `backend/tests/test_forge_*` | New/Modified | packaging/Entra-absence/launcher parity |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Tauri/Rust never built in this repo setup (no `target/`, cold toolchain) | High | Slice D4 starts with `cargo test` baseline; Rust logic kept pure (config/deep-link parsing) so unit-testable without GUI |
| Quarantine lift weakens C2 isolation | Med | Guard passes only when build-time verifier attested; no runtime env/flag bypass; test asserts guard fails closed |
| Malicious deep link points app at attacker origin (phishing) | Med | https + build allow-list, confirm dialog, wipe profiles on origin change, deep link never carries secrets |
| PyInstaller sidecar differs from venv worker behaviour (shim, spawn of workers) | Med | Router spawns workers via same sys.executable semantics; smoke on built exe (user-run if CI absent) |
| Pure-deletion slice D2 (~900 lines) exceeds 800 | Low | one honest slicing pass done; recommend `size:exception` for deletion-only |
| CP portal contract not yet built | Med | contract items + stub config fixtures; e2e joins in `fv2-release-e2e` |

## Rollback Plan

Each slice is a stacked PR; revert in reverse order. Entra removal is revertible from git; sidecar/guard changes are behind the existing build, web launcher path untouched so the web/dev client keeps working.

## Success Criteria

- [ ] No `entra` identifier remains in desktop-tauri or frontend (test-enforced).
- [ ] Installed app (built NSIS) starts the router sidecar and logs in an owned account against a configured CP; company code shown pre-filled.
- [ ] Deep link and installer-config resolution covered by unit tests incl. hostile inputs.
- [ ] `cargo test`, node tests, frontend unit + tsc, client py tests green.
