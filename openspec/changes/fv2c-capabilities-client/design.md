# Design: fv2c-capabilities-client

## Technical Approach
A pure resolver at the core, three thin seams around it: **PolicyClient** (fetch/verify/cache), **registries** (skills/tools/connectors consult resolver), **Vault/Broker** (secrets and remote MCP). The worker serves a read-only `/forge/v1/capabilities` for the UI. All CP-facing shapes are in the contract section and fixture-tested so the parallel CP planner can diff against them.

## Architecture Decisions

### Decision: Resolver is pure and total
**Choice**: `resolve(base_catalog, policy|None, attestation, now) -> list[Decision{kind,id,enabled,source,reason}]`; unknown kinds/ids ignored + logged; precedence: kill_switch > explicit deny > explicit enable > base_default (if in base catalog) > not_approved.
**Alternatives**: scatter checks in each registry (drift, bypass).
**Rationale**: table-driven TDD; one place to audit.

### Decision: Signed policy verified client-side (Ed25519, pinned key list)
**Choice**: canonical JSON (RFC 8785 style, sorted keys, no floats) + detached signature; keys pinned in build (`policy_keys.json`) with `kid` and `not_after`; reject lower revision; bind `organization_id`.
**Alternatives**: TLS-only trust (a compromised relay/proxy could widen capabilities); HMAC (needs shared secret on client).
**Rationale**: policy widening is the dangerous direction; client must not trust transport alone. Uses `cryptography` already present? (confirm at apply; else `PyNaCl`-free fallback via `cryptography` Ed25519).

### Decision: Base catalog is a reviewed allow-list shipped in the client
**Choice**: `base_catalog.json` (ids + kind + transport + risk) generated from inventory (22+ tools, 25 skills, 46 connectors) with high-risk items (computer, browser, channels, remote tunnel, automations) excluded permanently in this change.
**Rationale**: "default ON for base" without "everything ON".

### Decision: DPAPI via ctypes, entropy = profile id; no plaintext fallback
`CryptProtectData/CryptUnprotectData`, current-user scope. Honest limit: same-user processes can decrypt.

### Decision: Remote MCP only through the CP broker
Client holds no remote third-party token; broker path `POST {cp}/forge/v1/broker/{connector_id}/call` relayed by the router. Direct remote egress denied by the resolver (`transport=remote` requires broker availability) and by the sandbox egress guard.

## Data Flow
```
CP effective-policy (signed) --relay--> PolicyClient --verify--> store(last-known-good, expires)
base_catalog.json + policy + exec_allowed() ──> resolver ──> Decisions
   ├─> tool/skill/connector registries (load + per call)
   ├─> GET /forge/v1/capabilities ─> UI panel
   └─> audit queue ─> CP (when available)
stdio connector: vault(DPAPI) -> ToolRunner(env: own token only)
remote connector: tool call -> router -> CP broker
```

## File Changes
| File | Action | Description |
|------|--------|-------------|
| `backend/app/forge_capabilities/{resolver,policy,verify,store,catalog,audit}.py` | Create | engine |
| `backend/app/forge_capabilities/base_catalog.json`, `policy_keys.json` | Create | shipped data |
| `backend/app/forge_vault.py` | Create | DPAPI vault + migration |
| `backend/app/mcp/{token_store,manager,tool_wrapper}.py` | Modify | vault, broker, deny remote direct |
| `backend/app/forge_workspace.py`, `forge_router.py` | Modify | gated tools, `/forge/v1/capabilities` route + allow-list, policy relay |
| `backend/app/skill/registry.py`, tool registry | Modify | resolver checks |
| `frontend/src/lib/forge-capabilities.ts`, `components/forge/capabilities/CapabilitiesPanel.tsx` | Create | UI |
| `tests/test_forge_capabilities_*.py`, `tests/fixtures/policy/*.json`, `frontend/tests/unit/forge-capabilities.spec.ts` | Create | |

## Interfaces / Contracts (CP assumptions — to reconcile with `fv2-capability-governance`/`fv2-connector-broker`)
```jsonc
// GET {cp}/forge/v1/capabilities/effective?organization_id=<id>   (hidden route, member session; ETag = revision)
{ "v":1, "organization_id":"…", "revision": 17, "issued_at":"…", "expires_at":"…", "kid":"k1",
  "kill_switch":["skill:x"],
  "items":[{"kind":"skill|connector|tool|app","id":"pdf","enabled":true,"source":"platform|company",
            "transport":"stdio|remote","risk":"low|med|high","manifest_sha256":"…"}],
  "sandbox":{"runner":"local|docker","egress_allow":["host"],"min_level":3},
  "signature":"<base64 ed25519 over canonical JSON without signature>" }
// POST {cp}/forge/v1/broker/{connector_id}/call  body {tool, arguments}  -> {result|error}
// POST {cp}/forge/v1/audit/client-events  [{capability,action,at,result}]
```
Assumptions flagged: signature scheme and key distribution; revision monotonic per org; `expires_at` ≤ 24h; endpoints may not exist yet (client degrades to base-safe + local-only).

## Testing Strategy (strict TDD)
| Layer | What | Approach |
|---|---|---|
| Unit | resolver table (≥25 rows), verifier (tamper/org/rollback/kid expiry), store expiry | `cd tests; ..\backend\.venv\Scripts\python.exe -m unittest test_forge_capabilities_resolver test_forge_capabilities_policy ...` |
| Vault | roundtrip, wrong entropy, migration, non-Windows refusal | win32-only real DPAPI; skip elsewhere |
| Integration | worker route auth, router allow-list, gated tool registry, remote connector -> broker mock transport | httpx MockTransport / raw ASGI (gotchas 3,4) |
| Frontend | panel states list/stale/error | `npm run test:unit`; `npx tsc --noEmit` |
| Contract | fixtures validate against shared JSON schema copy | unit |

## Migration / Rollout
Engine inert until wiring slice. First launch: no policy -> base-safe set until first fetch. Plaintext tokens migrated then deleted. Feature flag not needed (fail-closed defaults).

## Open Questions
- Final signing/key distribution from CP; whether policy is per-org only or per-membership.
- Does the base catalog include any stdio connector needing a runner level < L3? (default: connectors run under runner; if attestation < L3 stdio connectors disabled, reason `attestation_pending`.)
