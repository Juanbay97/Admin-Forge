# Tasks: fv2c-capabilities-client

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3.7k |
| 400-line budget risk | High (budget in use: 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | 5 slices, one stack, THIRD in client queue |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Apply gate: contract items (see design) must be reconciled with `fv2-capability-governance` / `fv2-connector-broker` before slice K2 is merged; K1 (resolver + fixtures) is CP-independent.

### Suggested Work Units (branch prefix `fv2c-cc-`)

| Unit | Goal | Base | Est. lines |
|------|------|------|-----------|
| K1 | Base catalog + pure resolver + shared fixtures | last `fv2c-sr-` slice (S9) | ~700 |
| K2 | Policy client: fetch via relay, Ed25519 verify, store/expiry, audit queue | K1 | ~800 |
| K3 | DPAPI vault + migration + stdio via runner | K2 | ~700 |
| K4 | Broker client for remote MCP; deny direct remote; registries consult resolver; gated tools in bridge | K3 | ~800 |
| K5 | `/forge/v1/capabilities` route + frontend panel + tests | K4 | ~700 |

## Phase 1: Resolver (K1)
- [x] 1.1 RED `test_forge_capabilities_resolver`: precedence table (base default, deny, enable, kill switch, not_approved, attestation, expiry, unknown kinds)
  - Evidence: client `5b25df9` (`tests/test_forge_capabilities_resolver.py`)
- [x] 1.2 `catalog.py`, `base_catalog.json` (generated from inventory, high-risk excluded), `resolver.py`; GREEN
  - Evidence: client `5b25df9` (`catalog.py`, `base_catalog.json`, `resolver.py`)

## Phase 2: Policy client (K2)
- [x] 2.1 RED `test_forge_capabilities_policy`: valid, tampered, other org, rollback, key expiry, expired, offline grace
  - Evidence: client `154153e` (`tests/test_forge_capabilities_policy.py`)
- [x] 2.2 `verify.py` (canonical JSON + Ed25519), `store.py` (atomic, last-known-good), `policy.py` fetch via router relay with ETag
  - Evidence: client `154153e` (`verify.py`, `store.py`, `policy.py`)
- [x] 2.3 `audit.py` bounded no-content queue
  - Evidence: client `154153e` (`audit.py`)

## Phase 3: Vault (K3)
- [x] 3.1 RED `test_forge_vault`: roundtrip, wrong entropy, plaintext migration + secure delete, non-Windows refusal
  - Evidence: client `e755a2c` (`tests/test_forge_vault.py`)
- [x] 3.2 `forge_vault.py`; adapt `McpTokenStore`; stdio launch via `ToolRunner` with only own token
  - Evidence: client `e755a2c` (`forge_vault.py`, token migration); stdio launch through the sandbox runner completed by `0216db3`, `87f79b3`, `4739317` (`stdio_host.py`)

## Phase 4: Enforcement (K4)
- [x] 4.1 RED integration: disabled capability refused at load and call; remote connector -> broker mock only; direct remote denied; exec needs `exec_allowed`
  - Evidence: client `02c21be` (`tests/test_forge_capabilities_enforcement.py`)
- [x] 4.2 Modify `mcp/manager`, `tool_wrapper`, skill/tool registries, `forge_workspace` (tools from resolver instead of `[]`)
  - Evidence: client `02c21be`, `081282a`, `75e83f7` (`enforce.py`, `broker.py`, `forge_workspace.py` tools from the resolver)

## Phase 5: UI (K5)
- [x] 5.1 RED worker route test (401 unauth, no secrets) + router allow-list
  - Evidence: client `1862c5d` (`tests/test_forge_capabilities_api.py`, router allow-list); `e734076` (allow-list fix)
- [x] 5.2 RED frontend unit: list/stale/invalid/error states
  - Evidence: client `c49432b` (`frontend/tests/unit/forge-capabilities.spec.ts`)
- [x] 5.3 Implement route, `forge-capabilities.ts`, `CapabilitiesPanel.tsx`; settings entry
  - Evidence: client `1862c5d`, `c49432b`, `37cad52` (route, `forge-capabilities.ts`, `CapabilitiesPanel.tsx`, settings entry)

## Verification commands
- py (from `clients/openyak/tests`): `..\backend\.venv\Scripts\python.exe -m unittest test_forge_capabilities_resolver test_forge_capabilities_policy test_forge_vault test_forge_capabilities_enforcement test_forge_capabilities_api -v` + existing `test_forge_router_pool test_forge_router_cli`
- frontend: `cd frontend; npm run test:unit; npx tsc --noEmit`
- node (explicit list): launcher/packaging tests unchanged must stay green.
- Not verifiable here: real CP policy/broker/signing keys; DPAPI on other user contexts.

## Client slices K1-K5d and I1-I5 (reconciliation, evidence from the client repo `git log`)
- [x] K1 `5b25df9` resolver | K2 `154153e` policy client | K3 `e755a2c` vault | K4a `02c21be` enforcement, K4b `081282a` text tool calls, K4c `75e83f7` workspace wiring | K5a `1862c5d` route, K5b `c49432b` panel, K5c `45edd58` broker connected-only, K5d `e734076` route allow-list
- [x] I1 `5392fb7` onboarding link | I2 `a6918dd` live attestation | I3 `9f52617` container shells | I4 `72e12e2` governed skills | I5 `fdbffab`, `2103dcd`, `f90bd4e`, `1f65297` policy key pinning from the installer configuration, reproducible release build
