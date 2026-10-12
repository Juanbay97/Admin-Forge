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
- [ ] 1.1 RED `test_forge_capabilities_resolver`: precedence table (base default, deny, enable, kill switch, not_approved, attestation, expiry, unknown kinds)
- [ ] 1.2 `catalog.py`, `base_catalog.json` (generated from inventory, high-risk excluded), `resolver.py`; GREEN

## Phase 2: Policy client (K2)
- [ ] 2.1 RED `test_forge_capabilities_policy`: valid, tampered, other org, rollback, key expiry, expired, offline grace
- [ ] 2.2 `verify.py` (canonical JSON + Ed25519), `store.py` (atomic, last-known-good), `policy.py` fetch via router relay with ETag
- [ ] 2.3 `audit.py` bounded no-content queue

## Phase 3: Vault (K3)
- [ ] 3.1 RED `test_forge_vault`: roundtrip, wrong entropy, plaintext migration + secure delete, non-Windows refusal
- [ ] 3.2 `forge_vault.py`; adapt `McpTokenStore`; stdio launch via `ToolRunner` with only own token

## Phase 4: Enforcement (K4)
- [ ] 4.1 RED integration: disabled capability refused at load and call; remote connector -> broker mock only; direct remote denied; exec needs `exec_allowed`
- [ ] 4.2 Modify `mcp/manager`, `tool_wrapper`, skill/tool registries, `forge_workspace` (tools from resolver instead of `[]`)

## Phase 5: UI (K5)
- [ ] 5.1 RED worker route test (401 unauth, no secrets) + router allow-list
- [ ] 5.2 RED frontend unit: list/stale/invalid/error states
- [ ] 5.3 Implement route, `forge-capabilities.ts`, `CapabilitiesPanel.tsx`; settings entry

## Verification commands
- py (from `clients/openyak/tests`): `..\backend\.venv\Scripts\python.exe -m unittest test_forge_capabilities_resolver test_forge_capabilities_policy test_forge_vault test_forge_capabilities_enforcement test_forge_capabilities_api -v` + existing `test_forge_router_pool test_forge_router_cli`
- frontend: `cd frontend; npm run test:unit; npx tsc --noEmit`
- node (explicit list): launcher/packaging tests unchanged must stay green.
- Not verifiable here: real CP policy/broker/signing keys; DPAPI on other user contexts.
