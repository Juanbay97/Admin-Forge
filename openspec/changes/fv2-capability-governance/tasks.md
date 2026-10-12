# Tasks: fv2-capability-governance

> **Migration renumber (decided 2026-10-12).** `fv2-prod-runtime` slice S5 owns `0027_gateway_origin_config.sql` (pinned F27, relaxes the hard-coded gateway origin spelling in the 0015/0019 CHECKs and `gateway_save`). Every migration number and `F` pin in this file shifts by +1 (any `F27` fingerprint reference becomes the value after the preceding changes in the final chain: check the live `MVP_CHECKPOINTS` tail before pinning).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4.1k (6 slices, 450–780 each) |
| 400-line budget risk | High (800-line slice budget respected) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 → S4 → S5 → S6 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | Pure resolver + manifest validator (no DB) | PR 1 (~650) | independent of siblings |
| S2 | Schema, RLS, roles, DEFINER fns, store | PR 2 (~780) | after platform-core/usage-metering migrations |
| S3 | Hidden platform/org/member APIs + change audit | PR 3 (~750) | |
| S4 | Signer, effective endpoint, contract vectors, pin test | PR 4 (~700) | |
| S5 | Invocation ingest + log migration | PR 5 (~600) | |
| S6 | Seed + sync CLI + readiness/profile + runbook | PR 6 (~600) | |

## S1 Resolver (TDD)
- [ ] 1.1 RED `tests/test_capability_policy.py`: precedence, unknown→off, force-off, gate, level default 0
- [ ] 1.2 GREEN `src/forge/capability_policy.py` (frozen dataclasses, `resolve`)
- [ ] 1.3 RED→GREEN `tests/test_app_manifest.py` + `src/forge/app_manifest.py` (traversal, wildcard host, unknown key, canonical sha)

## S2 Schema/store
- [ ] 2.1 Migration catalog/platform policy/epoch/roles; RLS tests (PG)
- [ ] 2.2 Migration org policy + change audit + DEFINER fns (`cap_set_*`, `cap_read_layers`), lock + epoch++ atomic
- [ ] 2.3 `capability_store.py` port + PG adapter; ripple `mvp_local.py` ROLES, F27 fingerprint, readiness
- [ ] 2.4 Tests: cross-org denied, audit immutability, platform-only catalog write

## S3 APIs
- [ ] 3.1 RED→GREEN `capability_api.py` platform routes via `platform_lock_owner`
- [ ] 3.2 Company-admin enable/disable + audit read; `LOCKED` rejection
- [ ] 3.3 Hidden-route test + MVP contract pin unchanged

## S4 Effective policy
- [ ] 4.1 `capability_signing.py` Ed25519, kid, canonical JSON; vectors
- [ ] 4.2 `GET /forge/v1/capabilities/effective` + `/keys`; 503 w/o key
- [ ] 4.3 `contract/forge-capability-policy.v1.json` + tamper/expiry/epoch tests

## S5 Invocation log
- [ ] 5.1 Migration + ingest fn (dedupe event_id)
- [ ] 5.2 `POST /capabilities/audit` strict allow-list; 422 on content fields; ≤100 batch

## S6 Seed/ops
- [ ] 6.1 `capability_seed.py` JSONL (compact) + idempotent sync CLI; count test vs inventory
- [ ] 6.2 Readiness/profile wiring; `docs/capability-governance.md` (key runbook, attestation levels)
