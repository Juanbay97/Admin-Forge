# Design: fv2c-superapp-host

## Technical Approach
Frontend-only host plus one read-only worker route. Pure TS modules (validator, bridge router, permission store) are unit-tested with the existing Playwright-unit runner; one real-browser spec proves isolation on the production CSP.

## Architecture Decisions

### Decision: Opaque-origin iframe via `sandbox="allow-scripts"` + host-verified `srcdoc`
**Choice**: host fetches entry bytes, verifies sha256, builds `srcdoc` with injected CSP meta; no `allow-same-origin`.
**Alternatives**: separate origin per extension (needs host/port management, loopback tricks, distinct CSP); Web Worker only (no UI); Tauri secondary webviews (desktop-only, heavy).
**Rationale**: smallest viable boundary that works in web + Tauri; parent CSP already allows inline scripts (`next.config.ts:21`) — if `srcdoc` is blocked by parent `frame-src`/inheritance, e2e (slice X2) decides fallback to blob URL; no production behaviour is shipped before that proof.

### Decision: Single-file HTML entries in v1
Removes asset-path resolution and multi-file integrity; future formats extend the manifest `v`.

### Decision: Permissions list is deliberately tiny; dangerous names reserved
`network`, `fs`, `tools` rejected until a later change designs them with the runner/egress guard.

### Decision: Catalog authority = capability resolver
No second source of truth; `kind=app` already in the policy contract of `fv2c-capabilities-client`.

## Data Flow
```
resolver(kind=app, enabled) -> AppCatalog -> launch(id)
  -> GET /forge/v1/extensions/{id}/entry (worker: jail + resolver check) -> bytes
  -> validate manifest + sha256 (+ policy pin) -> ExtensionHost builds srcdoc + sandbox iframe
iframe --postMessage{v,id,method,params}--> BridgeRouter(source check, schema, size/rate)
   -> method handler -> PermissionStore? -> host prompt -> result/error --> iframe
```

## File Changes
| File | Action | Description |
|------|--------|-------------|
| `frontend/src/lib/forge-extensions/{manifest,validate,bridge,permissions,storage}.ts` | Create | pure logic |
| `frontend/src/components/forge/extensions/{ExtensionHost,PermissionPrompt,AppCatalog}.tsx` | Create | UI |
| `backend/app/forge_extensions.py` + route registration in `forge_workspace.py`/router allow-list | Create/Modify | delivery |
| `frontend/tests/fixtures/extensions/hello/{manifest.json,index.html}` | Create | test-only |
| tests listed in proposal | Create | |

## Interfaces / Contracts
```ts
type Manifest = { id: string; version: string; publisher: string; entry: string; permissions: ("ui.title"|"storage.local")[]; sha256: string; signature?: string };
type Msg = { v: 1; id: string; method: "host.ready"|"host.getInfo"|"ui.setTitle"|"storage.get"|"storage.set"|"capability.request"; params: unknown };
type Reply = { id: string; ok: true; result: unknown } | { id: string; ok: false; error: string };
```
CP contract assumption (from `fv2-capability-governance`): policy item `{kind:"app", id, enabled, manifest_sha256}`; app bytes are delivered to the profile's extensions dir by a later distribution mechanism (out of scope); this change reads from that dir only.

## Testing Strategy (strict TDD)
| Layer | What | Approach |
|---|---|---|
| Unit TS | validator table (valid/hostile), bridge router (foreign source, schema, size, rate), permission store, storage quota | `cd frontend; npm run test:unit` + `npx tsc --noEmit` |
| Python | delivery route traversal/hash/resolver gate | `cd tests; ..\backend\.venv\Scripts\python.exe -m unittest test_forge_extensions` |
| UI/e2e | hello in iframe: isolation, prompt, grant, teardown on org switch, production CSP | Playwright config like `playwright.forge-*.config.ts` (browser needed; run here if browsers installed) |
| Bundle | `hello` absent from production build | node test (explicit file list) |

## Migration / Rollout
Additive and inert without `kind=app` items; no flag needed.

## Open Questions
- Does Chromium apply the parent CSP to `srcdoc` iframes such that the injected meta can only tighten (expected: yes, intersection) — confirm in e2e.
