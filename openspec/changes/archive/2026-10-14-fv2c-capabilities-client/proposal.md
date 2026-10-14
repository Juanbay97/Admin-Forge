# Proposal: fv2c-capabilities-client

Repo: `clients/openyak` (CL). Position in client queue: **3rd** (after `fv2c-sandbox-runner`). Program: forge-v2 change #14. Control-plane dependencies (planned in parallel): `fv2-capability-governance` (#10) and `fv2-connector-broker` (#11) — consumed via **contract items** below; client slices stub them with fixtures and do not block on them.

## Intent

Vision v2: base OpenYak skills and connectors are ON by default (needed to operate); the company later restricts and approves extras; the platform can kill-switch. Today the managed bridge exposes nothing (`tools=[]`, settings=general only, tokens in plaintext `mcp/token_store.py:17-20`). The client must consume a **signed effective policy** from the control plane, enable base capabilities per policy, hold per-user stdio-connector secrets in DPAPI, reach remote MCP through the CP broker, and show the user what is enabled and why.

## Scope

### In Scope
- Policy client: fetch effective policy via router relay (revisioned, ETag), verify signature (Ed25519, pinned CP key id/rotation list), store last-known-good with expiry (offline grace), fail closed to "base-safe" set on invalid/expired.
- Capability engine: resolve `effective[kind,id] -> {enabled, source, reason}` for kinds skill | connector | tool | app; **default ON for base set** (shipped base catalog), explicit deny wins; policy `kill_switch` immediate.
- Tool gating: bridge `tools=[]` replaced by gated registry; exec-class tools additionally require `exec_allowed()` from `fv2c-sandbox-runner` (attestation >= L3); reasons surfaced (`policy_disabled`, `attestation_pending`, `kill_switch`).
- DPAPI vault (per-user, `CryptProtectData` via ctypes, entropy bound to profile id) replacing plaintext `McpTokenStore` for stdio connectors; migration deletes plaintext.
- Remote MCP via CP broker client: connectors with `transport=remote` are called through `POST {cp}/forge/v1/broker/...` (assumed) with the member session; the client never holds third-party remote tokens; direct remote egress denied.
- UI: "Capabilities" panel (settings) listing enabled/disabled items with reason, source (platform/company/base default), revision, last sync, attestation level; read-only; honest empty/error states; stable roles/labels for tests.
- Audit emit hook: queue `{capability, action, at, result}` (no content) toward CP when endpoint exists.

### Out of Scope
- CP tables/endpoints/signing service (fv2-capability-governance), broker server (fv2-connector-broker).
- Admin UI for editing policy (SPA changes).
- Sandbox layers (consumed through `exec_allowed`).
- Super-app extensions (`fv2c-superapp-host`) except kind `app` pass-through.
- Computer/browser/channels/automations remain permanently denied in this change.

## Capabilities

### New Capabilities
- `capability-policy-client`: fetch/verify/cache signed effective policy; resolve enablement with reasons; defaults ON for base.
- `connector-secrets-client`: DPAPI per-user vault for stdio connector tokens; broker client for remote MCP.
- `capabilities-ui`: user-visible panel of what is enabled and why.

### Modified Capabilities
- `managed-client-launch` / workspace bridge allow-list: routes for capabilities (read-only) added to the route allow-list.

## Approach

Policy is data; enforcement is local and fail-closed. A pure `resolver` takes `(base_catalog, policy, attestation)` -> decisions (fully table-testable). Tools/skills/connectors registries consult the resolver at load and at call time (revision change re-evaluates). Vault and broker client are separate seams. UI reads `/forge/v1/capabilities` served by the local worker.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/forge_capabilities/` | New | policy client, verifier, store, resolver, base catalog, audit queue |
| `backend/app/forge_vault.py` | New | DPAPI vault |
| `backend/app/mcp/{token_store,manager,tool_wrapper}.py` | Modified | vault, broker path, deny direct remote |
| `backend/app/forge_workspace.py`, `forge_router.py` | Modified | gated tools, route allow-list, relay of policy fetch |
| `backend/app/skill/registry.py`, `tool/registry` | Modified | consult resolver |
| `frontend/src/components/forge/capabilities/*`, `lib/forge-capabilities.ts` | New | panel |
| tests (`tests/test_forge_capabilities_*`, frontend unit) | New | |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| CP schema/signing drift (parallel planner) | High | contract items pinned as JSON schema fixture shared with CP; resolver tolerant of unknown kinds (ignored + logged) |
| "Default ON" for 25 skills/46 connectors broadens attack surface | Med | base catalog is an explicit reviewed allow-list (not "everything"); remote connectors only via broker; exec behind attestation |
| DPAPI is per-Windows-user, not per-app: other processes of same user can decrypt | Med | entropy bound to profile + documented; not claimed as isolation from same-user malware |
| Offline grace vs revocation latency | Med | short expiry (assumed 24h), kill_switch honoured on next sync; show staleness in UI |
| Existing plaintext tokens migration | Low | one-way migrate then securely delete; test with fixtures |

## Rollback Plan

Stacked PRs; engine first (inert). Wiring slice reverts to `tools=[]`. Vault migration is the only data-affecting slice: keep plaintext until vault write verified, then delete (reversible before delete).

## Success Criteria

- [ ] Resolver table tests cover base default ON, platform deny, org deny, kill switch, expiry, unknown kinds, attestation gate.
- [ ] Invalid/expired/unsigned policy -> base-safe set only; UI states why.
- [ ] No plaintext connector tokens on disk after migration; remote MCP only via broker.
- [ ] Capabilities panel shows each item with enabled/disabled + reason.
