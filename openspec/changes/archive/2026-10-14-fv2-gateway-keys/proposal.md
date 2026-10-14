# Proposal: fv2-gateway-keys (platform key pool + per-company assignment)

## Intent

Today one gateway key per org (`organization_gateways` PK org, 0015), entered by the company admin; endpoint pinned by DB CHECK to `ia.prometheonlab.com`/loopback (0015, 0019). The platform owner must own keys (OmniRoute), assign one or more per company with priority, and choose each company's model catalog; company admins must stop managing keys. Security: key text write-only, sealed; cost: enables rotation in one place and failover.

## Scope

### In Scope
- `gateway_keys` (platform-owned pool: label, origin, sealed key, revision, status, last4 hint) and `organization_gateway_keys` (org, key, priority, active); org `gateway_profile` (binding id, model ceiling = allowed upstream ids, catalog choice).
- New sealing format v2: AAD binds `key_id`+revision+origin (not org). Real key entered later via platform UI (write-only; placeholder/unset keys allowed).
- Origin ceiling moves from DB CHECK to deployment allow-list (`gateway_allowed_endpoints`, already configurable).
- Platform APIs (hidden): key CRUD/rotate/disable, assign/unassign/reorder, set ceiling/catalog.
- Routing: priority order, failover on 401/429/5xx before first streamed byte only.
- Company admin: key management removed; read-only status (configured/active count only).
- Audit via platform-audit (fv2-platform-core).

### Out of Scope
- Usage/cost (fv2-usage-metering), SPA console, weighted/load balancing, per-user keys, key health probes.
- Dropping legacy `organization_gateways` table (follow-up).

## Capabilities

### New Capabilities
- `gateway-key-pool`: platform-owned sealed keys, assignment, priority, rotation.
- `company-model-access`: per-company ceiling/catalog chosen by platform; admin read-only.

### Modified Capabilities
- None at spec level (no baseline specs); gateway routing/failover behavior specified in `gateway-key-pool`.

## Approach

Additive migrations 0031–0033 (provisional). Legacy `organization_gateways` rows keep working through a fallback in the route function until re-entered; catalog snapshots rebind to the org profile `binding_id` (stable across key rotation). Slices follow strict TDD with PG harness.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/0031..0033` | New | pool, assignment, profile, route fn, removal of admin grant |
| `src/forge/gateway_keys*.py` | New | cipher v2, store, service, platform API |
| `gateway_inference*.py`, `gateway_catalog*.py` | Modified | candidate keys, failover, rebinding |
| `account_api.py`, `admin/src` Gateway view | Modified | read-only status |
| `mvp_profile.py` etc. | Modified | F31–F33 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Catalog rebinding breaks publication/stale detection | High | dedicated slice, PG tests on upgrade with existing snapshots |
| Failover leaks key or duplicates billing | Med | only pre-first-byte; redacted errors; one attempt per key |
| Admin SPA breaks (142 tests) | Med | minimal read-only view in same slice, keep roles/labels |
| Lost Fernet key = unrecoverable keys | Med | backup runbook (deploy change) |

## Rollback Plan

Revert slice commits; migrations additive; legacy table untouched so route fallback restores old behavior; re-grant `gateway_save` if 0033 reverted.

## Dependencies

- fv2-platform-core (platform pool, audit, MFA) must land first; plus prod-runtime/deploy-compose/smtp ahead of it.

## Success Criteria

- [ ] Owner adds two keys, assigns both with priorities; inference uses primary, fails over on 429 before first byte.
- [ ] Company admin PUT gateway is refused; status read-only.
- [ ] No endpoint returns key text; fake-gateway records show bearer by key custody tests; fresh==upgrade F31–F33.
