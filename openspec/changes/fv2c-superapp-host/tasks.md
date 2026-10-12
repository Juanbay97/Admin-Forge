# Tasks: fv2c-superapp-host

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1.6k |
| 400-line budget risk | High (budget in use: 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | 2 slices, one stack, FOURTH (last) in client queue |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units (branch prefix `fv2c-sa-`)

| Unit | Goal | Base | Est. lines |
|------|------|------|-----------|
| X1 | Manifest + validator + integrity + bridge router + permission/storage logic (pure) + hello fixture | last `fv2c-cc-` slice (K5) | ~750 |
| X2 | ExtensionHost/PermissionPrompt/AppCatalog UI, worker delivery route, e2e isolation spec, bundle check | X1 | ~850 (split catalog UI to X3 if >800 at apply) |

## Phase 1: Pure logic (X1)
- [ ] 1.1 RED `forge-extensions-manifest.spec.ts`: valid, hostile table (traversal, extra keys, reserved perms, size), sha mismatch, policy pin mismatch
- [ ] 1.2 `manifest.ts`, `validate.ts`; GREEN
- [ ] 1.3 RED `forge-extensions-bridge.spec.ts`: foreign source, schema, size cap, rate limit, unknown method, repeated-violation termination
- [ ] 1.4 `bridge.ts`, `permissions.ts` (default deny, cooldown, policy override), `storage.ts` (quota, namespace); hello fixture

## Phase 2: Host UI + delivery (X2)
- [ ] 2.1 RED `tests/test_forge_extensions.py`: delivery route traversal, hash mismatch, resolver-disabled -> refused
- [ ] 2.2 `forge_extensions.py` route + router allow-list entry
- [ ] 2.3 RED UI spec `forge-extension-hello.spec.ts` (Playwright, production CSP): iframe attributes, isolation attempts fail, prompt/grant/deny, teardown on org switch
- [ ] 2.4 `ExtensionHost.tsx`, `PermissionPrompt.tsx`, `AppCatalog.tsx`
- [ ] 2.5 node test: `hello` fixture absent from production bundle; docs `docs/extensions.md`

## Verification commands
- frontend: `cd frontend; npm run test:unit; npx tsc --noEmit`
- py (from `clients/openyak/tests`): `..\backend\.venv\Scripts\python.exe -m unittest test_forge_extensions -v`
- e2e: `npx playwright test -c playwright.forge-extensions.config.ts` (needs installed browsers; verify availability at apply)
- Not verifiable: Tauri webview behaviour of sandboxed `srcdoc` (WebView2) without a built desktop app.
