# Design: fv2-usage-metering

## Technical Approach

Meter inside `GatewayInference.stream` (`gateway_inference.py`), the only consumer of `HttpxTextAdapter.events`. The adapter yields a new `('usage', {...})` event; the stream accumulates it plus timings and records once in `finally`. Writes go through a DEFINER function on the existing gateway pool pattern (`gateway_inference_store.py`, `GatewayConnection`); reads through platform functions (fv2-platform-core) and one org-scoped admin function. Specs: usage-capture, usage-reporting.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Metering point | `GatewayInference.stream` finally block, shielded task | adapter-level; separate proxy | has org/member/key context + cancel handling |
| Missing usage | `estimated` = ceil(chars/4) for prompt (request messages) and completion (emitted chars) | skip event | cancel/old gateway still cost money |
| Parser | extend state machine: after `finish`, allow one `choices:[]` + `usage` object, strict `type is int`, then require `[DONE]` | permissive `.get('usage')` anywhere | fuzz-safe; keeps "unknown field" door closed |
| Write path | `forge.usage_record(digest,org,…)` DEFINER on `forge_gateway_authority`, EXECUTE to `forge_gateway_service`; validates session→membership, price lookup, insert event + upsert daily in one tx | direct INSERT grant | no read grants on pool |
| Event identity | client-generated `event_id uuid` (stream id) PK → idempotent | serial | retry-safe |
| Prices | `model_prices(upstream_id, version, in_micros, out_micros, currency, effective_from, set_by)`; cost = tokens×price/1e6 stored as `cost_micros bigint` + `price_id` | float cost; recompute on read | auditable snapshot |
| Rollup | `usage_daily` PK(day, org, membership, upstream_id, key_id) upsert | on-demand aggregate | cheap reads |
| Reads | platform fns (all orgs, ranged, paged ≤ 366 days) + `usage_company_members(digest,org,from,to)` admin-only | views | RLS via functions as elsewhere |
| Quota | `QuotaPolicy.check(org, membership)` port, default `AllowAll`, called in `prepare` | none | hook only |

## Data Flow

    prepare ─► quota_check ─► stream ─► adapter(include_usage) ─► text…, finish, usage, [DONE]
        │                         └ t0, ttfb, chars, status
        └ finally(shield) ─► usage_record(…) ─► usage_events + usage_daily (same tx)
    Platform ─► platform_usage_*(digest, range) ──► aggregates
    Company admin ─► usage_company_members(digest, org, range)

## File Changes

| File | Action | Description |
|---|---|---|
| `src/forge/gateway_inference_adapter.py` | Modify | request body, usage chunk, `usage` event |
| `src/forge/gateway_inference.py` | Modify | accumulate, record in finally, quota hook, `RouteContext.key_id/membership_id` |
| `src/forge/gateway_inference_store.py` | Modify | route returns membership/key ids |
| `src/forge/fake_gateway.py` | Modify | usage chunk, `fake-nousage` model |
| `src/forge/usage.py`, `usage_store.py`, `usage_api.py` | Create | domain, store, hidden platform + admin routes |
| `migrations/0034_usage_events.sql`, `0035_model_prices.sql`, `0036_usage_reads.sql` | Create | tables, record, prices, reads |
| `mvp_profile.py`, `mvp_readiness.py`, `mvp_up.py`, `tests/**` | Modify/Create | F34–F36 |

## Interfaces / Contracts

    UsageEvent(event_id, org, membership, alias, upstream_id, key_id, prompt, completion,
               latency_ms, ttfb_ms, status, error_code, source)  # no content fields
    QuotaPolicy.check(org: UUID, membership: UUID) -> None  # raises GatewayDenied to refuse (future)

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | parser fuzz, estimate, event on cancel/error | unittest, fake transports |
| Integration | record fn authority, rollup==sum, price versions, cross-org denial, pool cannot SELECT | PG harness |
| Smoke | fake gateway default vs no-usage through mvp stack | extend `mvp-smoke` |

## Migration / Rollout

Additive; adapter slice has no migration. Numbers provisional after upstream changes and gateway-keys.

## Open Questions

- [ ] Member self-usage endpoint: deferred (proposed).
- [ ] Retention/partitioning for `usage_events`: out now; flag volume at scale.
- [ ] `ttfb` semantics under failover: measured from the serving key's request.
