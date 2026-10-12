# Design: fv2-gateway-keys

## Technical Approach

Keys become platform data; companies reach them through assignment. Reuse `GatewayCipher` mechanics (`gateway_configuration.py`) with a v2 payload bound to `key_id`; reuse the dedicated `forge_gateway_service` pool + `forge_gateway_authority` functions for the member-path route, and the platform pool (fv2-platform-core) for management. Specs: gateway-key-pool, company-model-access.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| AAD | v2 `{v:2,key_id,revision,endpoint,key}`; `open_key(record)` dispatches v1 (org-bound legacy) / v2 | re-seal in SQL | SQL cannot hold Fernet key; legacy rows stay readable |
| Legacy rows | untouched `organization_gateways`; route fn prefers assignments, falls back to legacy row; CLI `reseal-legacy` optional | drop table now | zero-risk upgrade; drop is follow-up |
| Catalog binding | new `organization_gateway_profiles(organization_id PK, revision, binding_id, ceiling text[], …)`; snapshots/selections rebound to profile `binding_id` on first assignment (migration copies legacy `binding_id`) | bind snapshots to key | rotation/reorder must not stale catalogs |
| Origin | DB CHECK dropped for pool keys (new table has format check only); `OriginPolicy` allow-list in config is the ceiling | keep pin | multi-origin, deployment-controlled |
| Failover | `RouteContext.candidates: tuple[(key_id, GatewayRecord)]` ordered; `GatewayInference.stream` tries next only if adapter raises a pre-first-byte `RetryableUpstream` (401/429/5xx/connect) | retry after bytes; weighted LB | no duplicate content; simple |
| Adapter signal | adapter distinguishes `RetryableUpstream` (subclass of `GatewayUnavailable`) for status before body | status-blind | needed for correctness |
| Admin removal | 0033 revokes EXECUTE on `gateway_save` from `forge_gateway_service`; `PUT /orgs/{id}/gateway` returns 403 `GATEWAY_MANAGED_BY_PLATFORM`; GET returns status only | keep PUT | binding decision |

## Data Flow

    Platform ──► gateway_key_create(digest,label,origin,sealed) ──► gateway_keys
    Platform ──► assign(org,key,priority) ──► organization_gateway_keys ──► audit
    Member ──► route fn (session, org, alias) ──► ceiling check ► active catalog ► ordered candidates
        ──► cipher.open(v2) ──► adapter K1 ──(401/429/5xx pre-byte)──► K2 ──► stream
    Admin refresh ──► catalog discovery with top-priority active key

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/0031_gateway_key_pool.sql` | Create | keys, assignment, profile, platform fns, audit hooks |
| `migrations/0032_gateway_key_routing.sql` | Create | route fn w/ candidates + ceiling; catalog rebinding |
| `migrations/0033_gateway_admin_readonly.sql` | Create | revoke `gateway_save`; status fn |
| `src/forge/gateway_keys.py`, `gateway_keys_store.py`, `platform_keys_api.py` | Create | service, store, hidden routes |
| `src/forge/gateway_configuration.py` | Modify | cipher v2 + dispatch |
| `src/forge/gateway_inference.py`, `gateway_inference_adapter.py`, `gateway_inference_store.py` | Modify | candidates, failover, RetryableUpstream |
| `src/forge/gateway_catalog*.py`, `catalog_publication*.py` | Modify | ceiling + profile binding |
| `src/forge/account_api.py`, `admin/src/**/Gateway*` | Modify | read-only status |
| `mvp_*.py`, `tests/**` | Modify/Create | F31–F33, RED tests |

## Interfaces / Contracts

`RouteContext(organization_id, alias, catalog_revision, upstream_id, candidates=((key_id, GatewayRecord),…))` (breaking internal change; legacy single gateway = one candidate). Hidden routes: `/forge/v1/platform/gateway-keys` (POST/GET), `…/{id}/rotate|disable`, `/platform/companies/{id}/gateway-keys` (PUT list w/ priority), `…/model-access` (PUT ceiling).

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | cipher v1/v2 tamper, failover ordering, pre-byte rule | unittest + fake adapter |
| Integration | cross-company denial, ceiling shrink, rotation keeps catalog CURRENT, upgrade with existing snapshots | PG harness, fake gateway key custody records |
| Fuzz | status/body combos for retry classification | table-driven |

## Migration / Rollout

Additive; backfill profile from legacy rows; route fn dual-read. F31–F33 fresh==upgrade; numbers provisional after upstream changes.

## Open Questions

- [ ] Catalog discovery with multiple keys: top-priority only (proposed) vs any?
- [ ] Is admin SPA Gateway view change in this change or fv2-web-shell (proposed: minimal read-only here)?
