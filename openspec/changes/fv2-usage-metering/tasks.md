# Tasks: fv2-usage-metering

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4,400 (6 slices, 600–800 each) |
| 800-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S6 stacked |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | adapter usage + fake gateway + fuzz (no migration) | PR 1 | after fv2-gateway-keys |
| S2 | 0034 events+daily+record fn (F34) | PR 2 | on S1 |
| S3 | metering in GatewayInference + quota hook | PR 3 | on S2 |
| S4 | 0035 prices + platform price API | PR 4 | on S3 |
| S5 | 0036 platform reports | PR 5 | on S4 |
| S6 | company per-person report + smoke + docs | PR 6 | on S5 |

## Phase 1: Wire contract (S1)
- [ ] 1.1 RED fuzz `tests/test_gateway_inference_adapter.py` (usage shapes); GREEN parser + `stream_options`
- [ ] 1.2 RED/GREEN `fake_gateway.py` usage default + `fake-nousage`; `test_fake_gateway.py`
## Phase 2: Storage (S2)
- [ ] 2.1 RED `tests/test_postgres_usage_events.py` (record auth, rollup==sum, pool no SELECT); GREEN `0034_usage_events.sql`
- [ ] 2.2 F34 pin + readiness/up/profile ripple + previous-profile test
## Phase 3: Capture (S3)
- [ ] 3.1 RED `test_gateway_inference.py`: event on success/cancel/failure/estimated; GREEN `gateway_inference.py`, `usage_store.py`
- [ ] 3.2 RED recording-failure-doesn't-break-stream; GREEN shielded best-effort
- [ ] 3.3 Quota port default AllowAll, called in `prepare`
## Phase 4: Prices + reads (S4–S6)
- [ ] 4.1 RED/GREEN `0035` model_prices versions, cost snapshot, audit (F35)
- [ ] 4.2 RED/GREEN `0036` platform per-company/model/totals/range (F36), MFA gate, non-owner denied
- [ ] 4.3 RED/GREEN `usage_api.py` company per-person; cross-company denial
- [ ] 4.4 extend `mvp-smoke` with metered request; docs
