# Tasks: S3 member lifecycle

P1a generic recording and populated-legacy proof closure are verified and delivered locally. All later implementation remains unchecked. Exact paths, branch bases, commands and acceptance matrices: [implementation-plan.md](implementation-plan.md).

Parent approved P1a recording / P1b complete legacy bridge. P1a implementation is GREEN; independent verification and authorized local delivery are complete. RDD is user-disabled, so no native review is scheduled. P1b and O2/O3 remain incomplete. Prior RED evidence is preserved in [apply-progress.md](apply-progress.md).

## Review Workload Forecast

Budget: 800 authored additions + deletions per slice, including tests/docs. Delivery: force-chained mapped to auto-chain. Feature Branch Chain confirmed. One revised slicing pass separates department lifecycle, associations and scoped reads, plus invitation persistence from HTTP composition.

| Unit | Deliverable | Lines |
|---|---|---|
| P0 | Reconciled planning | 450–700 |
| P1a | Generic transactional recording | 807 actual; explicit one-unit exception |
| P1b | Complete legacy backfill/mirror bridge | 650–780 |
| P2 | Lease worker/redacted sink | 450–750 |
| P3a | Department lifecycle/store | 400–650 |
| P3b | Multi-area associations/archive races | 450–750 |
| P3c | Scoped reads/department HTTP | 400–650 |
| P4a | Invitation reservation/store | 400–650 |
| P4b | Invitation HTTP/composition | 300–500 |
| P5 | Validated activation | 500–750 |
| P6 | Member transitions/last-admin guard | 600–780 |

Ten implementation units (P1a through P6, excluding P0). Historical pre-split aggregate: implementation 3,950–6,180; including P0 4,400–6,880. Revised P1a/P1b forecasts are above; actual P1a behavior/test/evidence count is 807, explicitly authorized as a one-unit exception; see [apply-progress.md](apply-progress.md). Whole-change risk High. Stop on overage; no blanket exception, omitted tests or code compression.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
800-line budget risk: High

P1a base=tracker; P1b base=P1a; P2 base=P1b. Each later child targets its predecessor. Only tracker eventually targets main. P1a local commits are authorized; no P1b, push, PR, merge or other remote actions are authorized.

## Phase 1: Events

- [x] 1.1a P1a RED recording/atomicity/isolation failures; GREEN `0005_transactional_outbox.sql`, recorder and exact readiness; latest U1 3 + PG 166 + regression 140 passed; nonempty legacy preservation proved; independent 309 passed (PG 166 in 37.054s), parent outbox 3 passed (0.005s); behavior commit e8c489f8a0c7bcb5f614f8f7fa62dfb879d14c16; local delivery complete.
- [ ] 1.1b P1b `0006_legacy_outbox_bridge.sql` atomic legacy backfill/mirror with full migration, privilege, concurrency and old-runtime proof; no consumer before this slice.
- [ ] 1.2 P2 RED lease/crash/redaction in `tests/test_outbox_worker.py`; GREEN `src/forge/outbox_worker.py`; REFACTOR, U2+PG.

## Phase 2: Departments

- [ ] 2.1 P3a RED D1 lifecycle/RLS in `tests/test_postgres_departments.py`; GREEN `migrations/0007_organization_departments.sql` and store; REFACTOR, U3a+PG.
- [ ] 2.2 P3b RED D3/D4 many-to-many/archive races in `tests/test_postgres_department_assignments.py`; GREEN `src/forge/department_store.py`; REFACTOR, U3b+PG.
- [ ] 2.3 P3c RED D2 scoped projections/no implicit privilege in `tests/test_departments_api.py`; GREEN `src/forge/lifecycle_api.py`; REFACTOR, U3c+PG.

## Phase 3: Members

- [ ] 3.1 P4a RED M1/M2 reservation/tenant/atomicity in `tests/test_postgres_members.py`; GREEN `migrations/0008_member_invitations.sql` and store; REFACTOR, U4a+PG.
- [ ] 3.2 P4b RED denied/invited HTTP in `tests/test_members_api.py`; GREEN `src/forge/lifecycle_api.py` composition; REFACTOR, U4b+PG.
- [ ] 3.3 P5 RED concurrent/multi-area activation in `tests/test_postgres_enrollment.py`; GREEN `src/forge/enrollment_store.py`; REFACTOR, U5+PG.
- [ ] 3.4 P6 RED M2/M3 direct-writer/last-admin races in `tests/test_postgres_member_mutations.py`; GREEN `migrations/0009_member_mutations.sql` and transitions; REFACTOR, U6+PG.

## Phase 4: Evidence per slice

- [ ] 4.1 Run plan regression/compile/dependency commands; record RED/GREEN counts, PG cleanup, readiness/rollback and redaction in each named proof document.
- [ ] 4.2 Verify parent-relative size and opt-in-disabled compatibility before advancing; recovery, budget attribution and S4–S7 stay excluded.
