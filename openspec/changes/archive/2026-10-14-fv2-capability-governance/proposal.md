# Proposal: fv2-capability-governance

## Intent

Forge's client is deliberately tool-less; the control plane (CP) has no capability catalog, policy or audit. v2 must ship base OpenYak skills/connectors ON per company, let company admins disable them, let the super admin govern (platform default + per-company overrides + force-disable), and gate execution tools on a client-reported sandbox attestation. The client (fv2c-capabilities-client) needs a **signed effective-policy** to consume. Also prepares super-app extension (app manifests) without building apps.

Security/tenant/cost impact: default-deny for unknown ids; org RLS on org policy; execution tools never ON without attestation; audit stores metadata only (no content).

## Scope

### In Scope
- Catalog (`tool|skill|connector|plugin|app`), seeded from OpenYak inventory (22+ tools, 25 skills, 15 plugins, 46 connectors).
- Platform default policy, per-company override, org-admin setting, force-off lock; pure resolver incl. sandbox-attestation gate.
- Hidden HTTP APIs: platform (catalog/policy), company admin (enable/disable), member (effective policy).
- Signed (Ed25519) effective-policy document + public key set + contract vectors.
- Append-only change audit + tool-invocation metadata ingestion.
- App manifest schema, permission vocabulary, validator, catalog `app` entries.

### Out of Scope
- Platform console UI (fv2-web-platform-console), client enforcement (fv2c-*), real apps, sandbox runner.
- Connector secrets/OAuth/MCP proxy (fv2-connector-broker).
- Audit retention/export UI.

## Capabilities

### New Capabilities
- `capability-catalog`: catalog entries, seed, kinds, risk, base flag.
- `capability-policy`: layered policy + resolution + sandbox gate.
- `effective-policy`: signed per-member document endpoint, key set.
- `capability-audit`: change audit + invocation metadata log.
- `app-manifest`: manifest schema, permissions, validator.

### Modified Capabilities
None (additive; `contract/forge-mvp.contract.json` pin unchanged — routes `include_in_schema=False`).

## Approach

Pure resolver (`capability_policy.py`) over layers read via SECURITY DEFINER functions; new NOLOGIN `forge_capability_authority` + LOGIN `forge_capability_service` pool; platform writes through platform-core's `platform_lock_owner`. No per-org seeding: absence of org row = inherit. Separate versioned contract `forge.capability-policy.v1` with signature test vectors.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/00NN_capability_*.sql` | New | tables, RLS, roles, functions |
| `src/forge/capability_*.py`, `app_manifest.py` | New | domain, store, API, signer |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py` | Modified | 7th pool, schema fingerprint |
| `contract/forge-capability-policy.v1.json` | New | document schema + vectors |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Attestation is client-reported/spoofable | High | Advisory by design; audited; threat model documented |
| Schema-hash/role ripple | High | ≤150 lines/migration, one role pair |
| Platform-core API drift | Med | Depend only on `platform_lock_owner` + pool; adapt on rebase |
| Signing-key loss/rotation | Med | `kid` + overlapping keys; runbook |

## Rollback Plan

Migrations additive; revert slices in reverse; routes hidden, client ignores absent endpoint (defaults stay as shipped, exec OFF).

## Dependencies

After fv2-platform-core (platform pool, audit pattern), gateway-keys, usage-metering in the same stack; migrations numbered after theirs (indicative 0034–0036).

## Success Criteria

- [ ] Base set ON for new company with zero rows; force-off beats org enable.
- [ ] Exec tools resolve `blocked_attestation` below min level.
- [ ] Policy signature verifies against published vectors; MVP contract pin unchanged.
- [ ] Cross-org RLS and no-content audit tests pass.
