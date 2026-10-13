# Tasks: fv2-gateway-keys

> **Migration renumber (decided 2026-10-12).** `fv2-prod-runtime` slice S5 owns `0027_gateway_origin_config.sql` (pinned F27, relaxes the hard-coded gateway origin spelling in the 0015/0019 CHECKs and `gateway_save`). Every migration number and `F` pin in this file shifts by +1 (`0031_gateway_key_pool` -> `0032`, F31 -> F32; `0032` routing -> `0033`, F33; `0033` ceiling -> `0034`, F34). It also follows platform-core's shift.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3,800 (5 slices, 650–800 each) |
| 800-line budget risk | High (S4 rebinding) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S5 stacked |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | schema 0031 + F31 | PR 1 | after fv2-platform-core |
| S2 | cipher v2 + key service/store | PR 2 | on S1 |
| S3 | assignment + platform routes + audit | PR 3 | on S2 |
| S4 | routing failover + catalog rebinding (0032, F32) | PR 4 | on S3 |
| S5 | ceiling + admin read-only (0033, F33) + SPA tweak | PR 5 | on S4 |

## Phase 1: Foundation
- [x] 1.1 RED `tests/test_postgres_gateway_keys_schema.py`; GREEN `0031_gateway_key_pool.sql` (keys, assignment, profile, backfill)
- [x] 1.2 F31 pin + readiness/up/profile ripple + `mvp_support` previous-profile test
## Phase 2: Keys
- [x] 2.1 RED cipher v1/v2 tamper tests; GREEN `gateway_configuration.py` dispatch
- [x] 2.2 RED/GREEN `gateway_keys.py` + `gateway_keys_store.py` (create/rotate/disable, last4, no key echo)
- [ ] 2.3 RED/GREEN `platform_keys_api.py` hidden routes, assignment/priority, audit rows; company-admin denial
## Phase 3: Routing
- [ ] 3.1 RED adapter `RetryableUpstream` table tests; GREEN `gateway_inference_adapter.py`
- [ ] 3.2 RED failover/pre-byte/all-down in `test_gateway_inference.py`; GREEN `gateway_inference.py` candidates
- [ ] 3.3 RED/GREEN `0032` route fn + catalog rebinding; PG upgrade with existing snapshots (F32)
## Phase 4: Access + admin
- [ ] 4.1 RED/GREEN ceiling set/shrink + publication check (`catalog_publication*.py`)
- [ ] 4.2 RED/GREEN `0033` revoke `gateway_save`, `PUT` → 403, status GET (F33)
- [ ] 4.3 Admin Gateway view read-only; keep roles/labels; run admin 142 tests
- [ ] 4.4 extend `mvp-smoke`: two keys, failover via fake gateway; docs
