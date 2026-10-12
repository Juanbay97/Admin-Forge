# Proposal: fv2-usage-metering

## Intent

No usage data exists. The adapter sends no `stream_options` and its strict parser REJECTS the final usage chunk (`choices: []` → `len(choices)!=1`, `gateway_inference_adapter.py`); `fake_gateway._stream` never emits usage. The platform owner needs consumption per company/model/total and cost; company admins need per-person usage. Security: no prompt/response content stored; tenant isolation preserved; cost impact: enables price-based reporting and a future quota.

## Scope

### In Scope
- Adapter sends `stream_options:{include_usage:true}`; parser accepts exactly one terminal usage chunk (strict ints, no unknown fields), emits a `usage` event; fuzz tests.
- Fake gateway emits usage chunk by default + a `no-usage` mode (model id driven).
- `usage_events` (org, membership, model alias, upstream id, key id, prompt/completion tokens, latency, ttfb, status, error code, `usage_source` gateway|estimated, price id, cost micros) written per inference, including cancel/failure (`estimated` = chars/4).
- `usage_daily` rollup upserted in the same transaction.
- Versioned `model_prices` (platform-editable; cost snapshotted at write).
- APIs (hidden platform): per-company, per-model, totals, time range; company admin: per-person for own company.
- `quota_check` hook in `GatewayInference.prepare`: no-op now.
- Audit of price edits (platform-audit).

### Out of Scope
- Quotas/limits, billing/invoices, SPA dashboards, member self-usage, export, retention jobs, non-text tokens.

## Capabilities

### New Capabilities
- `usage-capture`: adapter/parser/fake usage contract and event recording.
- `usage-reporting`: rollup, prices, platform and company-admin read APIs.

### Modified Capabilities
- None at spec level (no baseline specs); the parser acceptance change is specified in `usage-capture`.

## Approach

Meter at the `GatewayInference` seam (the only caller of the adapter). Write through a narrow DEFINER function on the existing `forge_gateway_service` pool (record only, never read). Reads via platform functions (all orgs, MFA-gated) and an org-scoped admin function. Additive migrations 0034–0036 (provisional).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gateway_inference_adapter.py`, `gateway_inference.py`, `fake_gateway.py` | Modified | usage event, recording, no-usage mode |
| `migrations/0034..0036` | New | tables, record fn, prices, read fns |
| `src/forge/usage*.py` | New | domain, store, APIs |
| `mvp_*.py`, `tests/**` | Modified | F34–F36 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Relaxed parser opens "unknown field" door | Med | exact-shape usage chunk only; fuzz suite |
| Event lost on client cancel | High | shielded record in `finally`; estimated flag |
| Record failure breaks streaming | Med | best-effort, finite error counter, never alters stream |
| Double counting on failover | Low | one event per request, `key_id` = key that served |
| Cost drift on price edit | Low | snapshot price id + cost at write |

## Rollback Plan

Revert slices; record call is the single hook, removable without schema change; tables additive. Adapter revert restores old request shape.

## Dependencies

- fv2-gateway-keys (key_id, candidates) and fv2-platform-core (platform pool, MFA, audit); prod-runtime/deploy/smtp land earlier.

## Success Criteria

- [ ] A streamed request yields one `gateway` event with tokens+latency; cancel yields `estimated`.
- [ ] Platform sees per-company/model/total for a date range; admin sees per-person own company only.
- [ ] No content columns exist; cross-org read denied; fresh==upgrade F34–F36.
