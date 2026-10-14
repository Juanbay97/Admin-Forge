# Design: fv2c-desktop-owned-auth

## Technical Approach
Desktop = thin Rust shell + bundled PyInstaller `forge-backend` (router mode) + the existing Next static frontend. Everything the frontend does goes to the loopback router (relative paths); the router relays to the CP and spawns one worker per `(org, membership)` profile. Rust only: resolve config, validate deep links, spawn/stop the sidecar, guard startup. No business logic in Rust.

## Architecture Decisions

### Decision: Router sidecar, not in-process backend
**Choice**: Rust spawns `forge-backend[.exe] router --control-plane-origin ... --ui-origin ... --port ... --data-dir ... --allow-origin ...` with explicit args and scrubbed env (parity-tested vs `forge-managed.mjs`).
**Alternatives**: embed Python in-process (breaks process-per-profile isolation, v1-multiuser decision); keep upstream `backend.rs` fixed-port single backend.
**Rationale**: reuses the proven isolation model; Windows kill semantics already solved (CTRL_BREAK then `taskkill /T`; venv shim gotcha does not apply to PyInstaller exe but tests keep distinct-port worker counting).

### Decision: Production CP origin via explicit allow-list
**Choice**: add `ControlPlaneOrigin` policy in Python (`forge_origin.py`): loopback dev form OR https hostname-only origin present in `--allow-origin`. `WorkspaceConfig`/`RouterConfig` call it instead of `_origin_port` for the CP origin only (UI origin stays loopback). `httpx` clients get `follow_redirects=False`, `verify=True`.
**Alternatives**: free-form origin from deep link (phishing); hard-code domain (no staging/dev).
**Rationale**: the production domain is configurable at build; deep link/installer config can only select among allowed origins.

### Decision: Config resolution in a pure Rust module
**Choice**: `config.rs` (`resolve(deep_link, installer_file, build_default) -> Resolved`) and `deep_link.rs` parse with a strict grammar; stored in app data (`company.json`, atomic write) after user confirmation. Installer config file: `forge-company.json` `{"v":1,"cp":"https://...","code":"acme"}` written by the NSIS hook from `/CODE=` and `/CP=` args, or dropped next to the installer by the portal download (fallback also read from `%APPDATA%`).
**Alternatives**: per-company installer builds (rejected by user: single installer); company code only via typing.
**Rationale**: pure functions -> `cargo test` without GUI.

### Decision: Build-attested guard replaces the panic
**Choice**: `forge-isolation.mjs` (verifier) writes `forge_attestation.json` (hash of guarded files + verifier result) during `build:desktop`; `build.rs` embeds the hash; `require_runtime_attested()` recomputes/compares and exits fail-closed. No env var path.
**Alternatives**: delete the guard (loses C2 gate); keep panic (app never runs).
**Rationale**: keeps "no isolation proof -> no runtime" property while allowing a verified build to run. Exact attestation format finalised in D5 test-first; if the verifier cannot attest on this machine, build stays quarantined (accepted).

### Decision: Delete Entra wholesale, then prove absence
**Choice**: remove `entra_*.rs` (2,073 lines), IPC handlers, plugin features/deps only used by Entra (e.g. keyring/oauth crates, verified at apply), then a node test forbids reintroduction.

## Data Flow
```
installer(/CODE,/CP) -> forge-company.json ─┐
deep link prometheon-forge://join ─confirm─┼-> config.rs -> {cp,code} -> sidecar args
build default (production domain) ─────────┘
UI(Tauri webview, CSP loopback) -> router 127.0.0.1:P -> CP https (TLS verify, allow-list)
                                  └-> worker per profile
```

## File Changes
| File | Action | Description |
|------|--------|-------------|
| `desktop-tauri/src-tauri/src/entra_{pkce,session,store,transport}.rs` | Delete | Entra |
| `src/commands.rs`, `src/lib.rs`, `Cargo.toml` | Modify | drop IPC/deps, call guard, register deep link + config commands |
| `forge_build_guard.rs`, `build.rs` | Modify/Create | attested guard |
| `src/config.rs`, `src/deep_link.rs` | Create | resolution/validation |
| `src/backend.rs` | Modify | router sidecar spawn/stop, parity args |
| `src/updater_hook.rs` | Create | optional `latest.json` check (off by default) |
| `backend/app/forge_origin.py` + `forge_workspace.py`, `forge_router.py` | Create/Modify | https allow-listed CP origin |
| `scripts/forge-isolation.mjs`, `verify-bundle.mjs`, `generate-checksums.mjs` | Modify | attestation, bundle checks |
| `tauri.conf.json`, `windows/installer.nsh` | Modify/Create | nsis hook, scheme, resources, drop signingIdentity |
| `frontend/src/lib/forge-desktop.ts`, gate components | Create/Modify | read resolved config, change-company flow |
| `tests/forge-desktop-*.test.mjs`, `backend/tests/test_forge_origin.py` | Create | |

## Interfaces / Contracts
- Deep link grammar: `prometheon-forge://join?cp=<https origin>&code=<[a-z0-9][a-z0-9-]{1,62}>` exactly these keys, no fragment secrets.
- Tauri IPC: `get_company_config() -> {cp_origin, company_code, source}`, `confirm_company_config(pending_id)`, `clear_company_config()`.
- **CP contract assumptions (from fv2-web-company-portal / fv2-deploy-compose, not built yet)**: `GET /forge/v1/branding?org=<slug>` (exists); `https://<cp>/downloads/latest.json` `{version, sha256, size, url}`; portal download page emits the deep link; installer filename carries no secret. Router needs no new CP endpoint.

## Testing Strategy (strict TDD: RED test committed in same commit as GREEN code, run order recorded)
| Layer | What | Approach |
|---|---|---|
| Rust unit | config precedence, deep-link grammar incl. hostile inputs, guard fail-closed, args builder | `cargo test` in `desktop-tauri/src-tauri` (toolchain present: cargo/rustc 1.99; cold build, no `target/`) |
| Python | origin policy, router/worker accept/reject, parity arg-builder | `cd tests; ..\backend\.venv\Scripts\python.exe -m unittest test_forge_origin ...` |
| Node | Entra absence, tauri.conf/CSP/nsis/bundle checks, launcher parity | `node --test tests/forge-desktop-*.test.mjs tests/forge-packaging.test.mjs ...` (explicit list) |
| Frontend | desktop gate, change-company | `npm run test:unit` + `npx tsc --noEmit` in `frontend` |
| Smoke | built NSIS installs, router answers `/forge/health` | user-run on Windows (not agent-verifiable) |

## Migration / Rollout
No data migration (no Entra sessions persisted by design; `entra_store` data is dropped). Feature is the default desktop; web launcher unchanged. Update hook off by default.

## Open Questions
- Attestation format feasibility with `cargo tauri build` on this machine.
- Whether keeping `tauri-plugin-deep-link` single-instance forwarding works on Windows NSIS (known requirement: single-instance plugin first; already ordered in lib.rs).
