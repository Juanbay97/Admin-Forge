# Design: fv2-capability-governance

## Technical Approach

DB stores *layers*; a pure Python resolver (`capability_policy.py`) computes effective state; an app-layer signer produces the document. Follows existing patterns: NOLOGIN authority owns SECURITY DEFINER functions, LOGIN service pool only EXECUTEs (`0015`), `include_in_schema=False` routes (`branding_api.py`), explicit composition, frozen dataclasses, redacted errors.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Resolution locus | Pure Python over DB-read layers | SQL view / client-side | Unit-testable, strict TDD, one source of truth; DB enforces write authz only |
| Org seeding | Absence of org row = inherit | Seed rows per company | New company is correct on creation; no lifecycle hook |
| Policy shape | Platform `default_state` + `lock` (none/forced_off); company override same shape; org setting bool | Tri-state matrix | Matches binding: admin can disable, super admin force-disables |
| Roles | One pair `forge_capability_authority/_service` (7th pool); platform writes via platform-core `platform_lock_owner` | Reuse account pool / BYPASSRLS | Keep tenant isolation; one ripple |
| Audit | Own `capability_change_audit` (org RLS, readable by company admin) + `tool_invocation_log` | Reuse platform-core audit_log | Different scoping/volume/retention; avoids coupling to a parallel change |
| Attestation | Client-reported level in query; echoed in signed doc; gate always applied; level semantics: 0 none,1 jail+env scrub,2 isolated process,3 =2+egress guard+escape suite passed | Server-verified | Local-machine threat model; CP cannot verify; record in audit |
| Signing | Ed25519 (`cryptography` already pinned), deployment key file, `kid`, canonical JSON (sorted, no spaces) | HMAC / JWS lib | Client verifies offline with public key; no new dep |
| Contract | Hidden routes + `contract/forge-capability-policy.v1.json` (schema+vectors) | Widen MeResponse | MVP pin stays byte-identical; client fails closed only on its own schema |
| App manifest | Pure validator + closed permission vocabulary + canonical sha | Build host bridge | Binding: schema/permission/catalog only |

## Data Flow

    member ──GET effective?sandbox_level──▶ capability_api ─▶ account_validate_session
         ▲                                        │
         │ signed doc                  cap_read_layers(org) (DEFINER, RLS)
       Signer ◀── resolve(layers, level) ◀────────┘
    admin/platform ──PUT policy──▶ cap_set_* (DEFINER: lock check, epoch++, audit row, one tx)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/00NN_capability_catalog.sql` | Create | catalog, platform policy, epoch, roles |
| `migrations/00NN+1_capability_policy.sql` | Create | org policy, change audit, DEFINER fns |
| `migrations/00NN+2_tool_invocation_log.sql` | Create | invocation log + ingest fn |
| `src/forge/capability_policy.py` | Create | states, resolver, gate |
| `src/forge/app_manifest.py` | Create | schema, validator, permissions |
| `src/forge/capability_store.py`, `capability_api.py`, `capability_signing.py`, `capability_seed.py` | Create | store port/PG adapter, hidden routes, signer, seed+sync CLI |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py`, `mvp_up.py` | Modify | pool, fingerprint, readiness |
| `contract/forge-capability-policy.v1.json`, `docs/capability-governance.md` | Create | contract+vectors, runbook |

## Interfaces / Contracts

```python
State = Literal['on','off','forced_off','blocked_attestation']
def resolve(entries, platform, company, org, reported_level:int) -> tuple[Effective,...]
```
Document: `{schema:'forge.capability-policy.v1', org, platform_epoch, org_epoch, issued_at, expires_at(24h), reported_level, capabilities:[{id,kind,state,min_sandbox_level,version,manifest_sha256,credential_locus,granted_permissions?}], kid, sig}`. Client rejects lower epochs and expired docs.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | resolver precedence, gate, manifest fuzz, signer vectors, no-content schema | unittest, TDD |
| Integration | RLS cross-org, lock enforcement, audit atomicity, role grants | PG harness (`test-postgres.ps1`) |
| HTTP | auth, hidden OpenAPI, MVP pin unchanged | httpx TestClient |

## Migration / Rollout

Additive. Seed via trusted CLI `python -m forge.capability_seed sync`. Numbering follows platform-core/gateway-keys/usage-metering (indicative 0034–0036; renumber at rebase; each ripples fingerprint F27+). Signing key supplied through composition (secret file), absent ⇒ endpoint 503.

## Open Questions

- [ ] Client key pinning/rotation rule (TOFU at join vs build-pinned) — decide with fv2c-capabilities-client.
- [ ] Plugins default OFF confirmed? (assumed).
- [ ] Exact platform-core function names for owner lock/audit.
