# Proposal: fv2c-superapp-host

Repo: `clients/openyak` (CL). Position in client queue: **4th/last** (after `fv2c-capabilities-client`). Program: forge-v2 change #15 (S, ~1.5k/2 slices). CP dependency: app manifest schema + `capability_catalog kind=app` from `fv2-capability-governance` (#10) — contract items, stubbed with fixtures.

## Intent

Vision v2: Forge must be a strong sandbox that can **grow into a super-app** (future embedded apps; do not build them). This change builds only the hooks: an extension manifest + validator, a sandboxed host (iframe in the web frontend) with a typed postMessage bridge and permission prompts, and an app catalog driven by effective policy. One sample "hello" extension exists purely for tests.

## Scope

### In Scope
- Manifest schema `{id, version, publisher, entry, permissions[], sha256, signature?}` + validator (strict, unknown keys rejected, id/version grammars, permission whitelist, entry must be a single self-contained HTML asset in v1).
- Sandboxed host: `<iframe sandbox="allow-scripts">` (no `allow-same-origin`, no top-nav, no popups/forms/downloads), content delivered as host-verified `srcdoc` (sha256 checked against manifest) with an injected restrictive CSP meta; typed `postMessage` bridge with origin/source/channel checks, request ids, schema validation, rate and size limits; v1 bridge methods: `host.ready`, `host.getInfo`, `ui.setTitle`, `storage.get/set` (namespaced, quota), `capability.request` (permission prompt).
- Permission prompts: every non-trivial permission requires explicit user consent per (extension, permission), persisted per profile, revocable; denied by default; policy may pre-deny.
- Catalog from policy: lists `kind=app` items from the effective policy (via `fv2c-capabilities-client` resolver); an app is launchable only if resolver says enabled.
- Sample `hello` extension (fixture, tests only, never in the base catalog).

### Out of Scope
- Real apps, extension store UX, signing infrastructure and key distribution (validator verifies signature only if present and a pinned key exists; otherwise requires policy `manifest_sha256`).
- Network/filesystem/tool access for extensions (no such bridge methods in v1: defined as future permission names, always rejected).
- Packaging format beyond single-file HTML; Tauri-native windows.

## Capabilities

### New Capabilities
- `extension-manifest`: manifest schema, validation, integrity (sha256 / policy pin).
- `extension-host`: sandboxed iframe host, bridge protocol, permission prompts, namespaced storage.
- `app-catalog`: catalog from effective policy, launch gating, "hello" sample for tests.

### Modified Capabilities
- None.

## Approach

Everything lives in the frontend (`frontend/src/lib/forge-extensions/`, `components/forge/extensions/`) plus a tiny worker route to deliver verified bytes from the profile's extensions dir (`GET /forge/v1/extensions/{id}/entry`, read-only, hash-pinned). Pure-TS validator and bridge router are table-testable under the existing Playwright-unit runner; a single browser e2e proves the iframe really cannot reach parent storage/network.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/lib/forge-extensions/` | New | manifest, validator, bridge, permissions, storage |
| `frontend/src/components/forge/extensions/` | New | `ExtensionHost`, `PermissionPrompt`, `AppCatalog` |
| `backend/app/forge_extensions.py` | New | read-only hash-pinned delivery route |
| `frontend/tests/unit/forge-extensions-*.spec.ts`, `frontend/tests/ui/forge-extension-hello.spec.ts`, `tests/test_forge_extensions.py` | New | |
| `frontend/tests/fixtures/extensions/hello/` | New | sample |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Parent CSP (`script-src 'self' 'unsafe-inline'`, default `self` frame-src) interacts with `srcdoc` | Med | Playwright e2e on the real CSP; fallback to blob/dedicated route decided in test |
| Sandbox escapes via bridge bugs | Med | schema-validated messages, no object references, no eval, fuzz tests; v1 bridge deliberately tiny |
| Scope creep into real apps | Med | hooks only, hello is test fixture; no catalog entries by default |
| Policy kind `app` shape changes in CP | Med | contract fixture + tolerant parsing |

## Rollback Plan

Pure additive; feature is inert unless policy lists an app. Revert both PRs; nothing else depends on it.

## Success Criteria

- [ ] Validator rejects malformed/hostile manifests (table test).
- [ ] hello extension runs in the iframe, calls `host.getInfo`, is denied `storage` until prompted, cannot read parent DOM/cookies/storage or fetch (e2e).
- [ ] App not enabled by policy never renders.
