# Tasks: fv2-platform-core

> **Migration renumber (decided 2026-10-12).** `fv2-prod-runtime` slice S5 owns `0027_gateway_origin_config.sql` (pinned F27, relaxes the hard-coded gateway origin spelling in the 0015/0019 CHECKs and `gateway_save`). Every migration number and `F` pin in this file shifts by +1 (`0027_platform_scope` -> `0028`, F27 -> F28; `0028` TOTP -> `0029`, F29; `0029` create company -> `0030`, F30; `0030` branding -> `0031`, F31).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~5,900 (8 slices, 600–800 each) |
| 800-line budget risk | High (migration + pin ripple + tests per slice) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S8 stacked |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | platform schema, roles, 6th pool, F27 | PR 1 | base main after prod-runtime/deploy/smtp |
| S2 | platform session/lock service + RLS matrix | PR 2 | on S1 |
| S3 | bootstrap-owner CLI | PR 3 | on S2 |
| S4 | TOTP MFA (0028, F28) | PR 4 | on S2 |
| S5 | platform HTTP API + `/me` + pin check | PR 5 | on S3,S4 |
| S6 | create company + first-admin invite (0029, F29) | PR 6 | on S5 |
| S7 | suspend/reactivate + branding (0030, F30) | PR 7 | on S6 |
| S8 | audit read + smoke + docs | PR 8 | on S7 |

Strict TDD each task: RED → GREEN → REFACTOR; module-at-a-time unittest + PG harness.

## Phase 1: Foundation (S1–S2)
- [x] 1.1 RED `tests/test_postgres_platform_schema.py`: roles NOLOGIN/NOBYPASSRLS, denied direct selects; GREEN `migrations/0027_platform_scope.sql`
- [x] 1.2 Pin F27 fresh==upgrade in `mvp_profile.py`; update `mvp_readiness.py`, `mvp_up.py`, `mvp_local.py` ROLES/secrets, `tests/mvp_support.py` (+ previous-profile test)
- [x] 1.3 RED/GREEN `platform_store.py` + `platform.py`: `platform_lock_owner`, validate session; cross-org denial matrix
## Phase 2: Identity (S3–S4)
- [ ] 2.1 RED/GREEN `platform_cli.py bootstrap-owner`: link file 0600, rerun no-op, link single-use
- [ ] 2.2 RED RFC 6238 vectors, replay, recovery codes (`platform_totp.py`); GREEN 0028 + F28
## Phase 3: API + lifecycle (S5–S7)
- [ ] 3.1 RED/GREEN `platform_api.py` routes `include_in_schema=False`; `test_contract.py` unchanged
- [ ] 3.2 RED/GREEN 0029 invitation relax + create_company + accept branch; member accept regression (F29)
- [ ] 3.3 RED/GREEN suspend/reactivate across member/admin/inference paths
- [ ] 3.4 RED/GREEN 0030 platform branding edit + other-company-unchanged (F30)
## Phase 4: Verify (S8)
- [ ] 4.1 audit read API + append-only denial tests
- [ ] 4.2 extend `scripts/mvp-smoke.ps1`: owner→company→invite→admin; docs
