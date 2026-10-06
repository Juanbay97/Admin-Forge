# Execution reference: S3 prerequisite

Parent authorized P1a implementation on the existing child; P1b remains a future slice. All paths below are relative to `N:/Proyects/forge/.worktrees/tenant-storage`. P1a evidence is in apply-progress.md and member-outbox-recording.md. No commits, staging, remote operations, upstream edits or keys are authorized.

## Approved scope and resolved gates

- Approved: protect the last active administrator; redacted-log delivery until S6, not durable audit; manager read-only own area; Entra tenant/object invitations and validated first-login binding.
- **Recovery deferred:** migration0004 is initial-only with a permanent designation, active-only policies and existing-admin rejection. It is NOT recovery. External identity loss may still prevent login; the user explicitly accepts recovery outside MVP. No designation deletion or last-admin bypass.
- **Departments confirmed:** members may belong to multiple departments; membership never implies admin privilege. Reject archive while any member remains linked, including suspended members, until reassigned/unlinked. No automatic detachment. Later budget attribution is excluded.
- **Chain confirmed:** force-chained maps to auto-chain for slicing; feature-branch-chain is explicitly selected. P1a targets tracker, P1b targets P1a, subsequent children their immediate predecessor; only tracker eventually targets main. No branch changes, commits, push, PR or merge authorized here.
- Domain exists but its name is unspecified. This prerequisite does not need it. Public Windows signing is deferred for MVP; any unsigned manual-install instructions must warn users. Automatic updates remain signature-gated. No signing secrets or updater-verification changes are needed here.
- Proposal is reconciled with the approved decisions; prior evidence is retained in design.md. Historical four- and six-slice estimates are superseded by ten implementation units in tasks.md, preserving tests and readiness work. P1 has no unresolved product gate.

## Exact proposed edit surfaces

Legend: N=new, M=modify. Tests/docs belong to their behavior slice. There are no deletions. No blanket `src/**` authorization is implied. Any additional surface requires an explicit plan amendment.

Shared migration slices P1/P3a/P4a/P6 also modify exactly `src/forge/postgres.py`, `tests/postgres_support.py`, `tests/test_postgres_runtime.py`: extend catalog checks, owned fixtures and readiness-tamper tests without relaxing old role contracts.

Parent additionally authorizes P1 edits to `tests/test_postgres_rls.py`: exact table inventory and exact singleton privileged-function signature; preserve every other invoker/RLS/ownership assertion and reject unexpected privileged functions. This historical surface amendment enabled the approved split below; it does not authorize new P1b work in this closure.

### Approved P1a/P1b split

One revised forecast includes all approved bridge safety proof; no code compression or omitted tests. Figures are estimates for complete behavior, not measured unimplemented source. The original P1 450–700 estimate no longer covers the reviewed bridge contract.

| Complete P1 surface | Forecast additions + deletions |
|---|---:|
| Migration: destination, role, guarded bridge, atomic backfill | 95–120 |
| Event command and transaction-bound recorder | 70–90 |
| Exact destination/bridge/role/ACL readiness | 150–190 |
| Fresh/populated/failed/visibility migration fixtures | 80–110 |
| New unit and PG behavior/security/concurrency tests | 250–310 |
| Runtime/RLS inventory and tamper regressions | 60–90 |
| Behavior proof document | 25–35 |
| Cumulative planning/progress, including retained evidence | 150–180 |
| **Total** | **880–1,125** |

Approved chain: tracker -> **P1a recording** -> **P1b legacy bridge** -> P2 -> remaining slices. Only the existing P1a child is used in this batch.

- **P1a (550–750):** existing child `feat/forge-s3-outbox-recording` targets tracker. Keep `0005_transactional_outbox.sql`, `outbox.py`, `outbox_store.py`, their two existing RED test files, shared readiness/fixture/runtime/RLS test surfaces and `member-outbox-recording.md`. Finish generic caller-transaction recording with duplicate/rollback proof, exact destination ACL/RLS/constraints readiness and migration safety. Legacy objects remain untouched; all functions remain invokers. No worker or bridge is installed. Revert consumers/code, retain additive destination.
- **P1b (650–780):** future child `feat/forge-s3-legacy-outbox-bridge` targets P1a. New `migrations/0006_legacy_outbox_bridge.sql`, `tests/test_postgres_outbox_bridge.py`, `docs/changes/member-outbox-bridge.md`; modify shared readiness/fixture/runtime/RLS tests only. Backfill, locking, restricted function owner, trigger context validation and complete security/old-runtime/concurrency/tamper proof ship together. No weaker intermediate bridge. Revert consumers only; retain functioning bridge dependencies and data.
- P2 then targets P1b; later unimplemented department/invitation/member migrations become 0007/0008/0009. No P1b files are written in P1a; no consumer launches until the entire bridge slice passes.
- Run U1, owned PG harness, seven-module regression, compileall and pip check per slice; bridge behavior is tested through PG discovery. No security proof moves to a later slice than its behavior. Measure each actual parent-relative diff before review; estimates are not size exceptions.

Parent approved this re-slice without a size exception. P1a retains zero SECURITY DEFINER assertions and only extends the exact table inventory. Legacy events stay in the original source-of-truth table until P1b; P1a does not complete O2 or publish anything.

### P0 — Planning boundary

Surfaces: this change's `proposal.md`, `specs/outbox-publication/spec.md`, `specs/organization-departments/spec.md`, `specs/member-lifecycle/spec.md`, `design.md`, `tasks.md`, `implementation-plan.md`. Reconcile existing artifacts, not new product files.

Start: prior planning and approved decisions. Finish: consistent specs and bounded execution plan. Runtime harness: N/A, documentation only. Rollback: restore prior planning content only; preserve unrelated worktree files and evidence.

### P1a — Generic transactional recording

- N: `migrations/0005_transactional_outbox.sql`, `src/forge/outbox.py`, `src/forge/outbox_store.py`, `tests/test_outbox.py`, `tests/test_postgres_outbox.py`, `docs/changes/member-outbox-recording.md`.
- M: shared migration surfaces above.
- Start: reconciled P0 and existing migrations0001–0004. Finish: generic transaction-bound recorder, scoped writer, exact readiness and migration/rollback/security tests. No bridge, import, lifecycle API, worker or budget attribution in P1a.
- Verify: U1 + PG and regression commands; O1 recording proof only. Rollback: disable consumers and revert P1a code after dependent slices; retain destination and untouched legacy rows. Frozen old readiness must accept retained0005; bridge/capture proof belongs entirely to P1b.

### P2 — Worker with redacted sink

- N: `src/forge/outbox_worker.py`, `tests/test_outbox_worker.py`, `tests/test_postgres_outbox_worker.py`, `docs/changes/member-outbox-worker.md`.
- M: `src/forge/outbox.py`, `src/forge/outbox_store.py`, `src/forge/runtime.py`, `tests/test_runtime.py`.
- Start: P1a durable events AND completed P1b legacy bridge. Finish: explicitly configured worker entry function/loop, bounded lifecycle and redacted sink; never auto-start inside HTTP requests.
- Verify: U2 + PG; O2/O3 lease/crash matrix. Rollback: stop owned worker, remove only P2 composition/worker changes; events stay pending or reclaimable.

### P3a — Department lifecycle persistence

- N: `migrations/0007_organization_departments.sql`, `src/forge/departments.py`, `src/forge/department_store.py`, `tests/test_departments.py`, `tests/test_postgres_departments.py`, `docs/changes/member-departments.md`.
- M: shared migration surfaces.
- Start: P2. Finish: create/rename/archive store, many-to-many join schema with composite foreign keys, RLS and archive guard; assignment writes remain unavailable. Include seeded occupied-archive tests now, not deferred tests.
- Verify: U3a+PG, D1/D4/readiness. Rollback: disable store and revert P3a code after dependents; retain schema/data and archive protection.

### P3b — Multi-area association mutations

- N: `tests/test_department_assignments.py`, `tests/test_postgres_department_assignments.py`, `docs/changes/member-department-assignments.md`.
- M: `src/forge/departments.py`, `src/forge/department_store.py`.
- Start: P3a guarded schema. Finish: membership-revisioned replace/unlink set, atomic event, no implicit privilege; occupied-archive and assignment races proven with real connections. No routes yet.
- Verify: U3b+PG, D3/D4 matrix. Rollback: disable association service and revert P3b only after dependents; preserve links, never detach silently.

### P3c — Department HTTP and scoped reads

- N: `src/forge/lifecycle_api.py`, `tests/test_departments_api.py`, `tests/test_postgres_department_reads.py`, `docs/changes/member-department-api.md`.
- M: `src/forge/department_store.py`, `src/forge/authorization.py`, `src/forge/api.py`, `src/forge/runtime.py`, `tests/test_authorization.py`, `tests/test_runtime.py`.
- Start: P3b store operations. Finish: opt-in department routes and member association PATCH, authorized manager projections, bounded pagination, no other-area association leakage or manager mutations.
- Verify: U3c+PG, D1–D4 HTTP/RLS. Rollback: disable composition, revert P3c routing/read adapters after dependents; retain P3a/b storage.

### P4a — Invitation reservation persistence

- N: `migrations/0008_member_invitations.sql`, `src/forge/members.py`, `src/forge/member_store.py`, `tests/test_members.py`, `tests/test_postgres_members.py`, `docs/changes/member-invitations.md`.
- M: shared migration surfaces.
- Start: P3c. Finish: unique pending tenant/object reservation and reserved membership UUID plus intended same-org department set, one event and no access. Store tests cover revoked authority/concurrent duplicates.
- Verify: U4a+PG, M1/M2 reservation matrix. Rollback: disable reservation store; revert P4a after dependents, retain invitations/events.

### P4b — Invitation API composition

- N: `tests/test_members_api.py`, `docs/changes/member-invitation-api.md`.
- M: `src/forge/lifecycle_api.py`, `src/forge/api.py`, `src/forge/runtime.py`, `tests/test_runtime.py`, `tests/test_postgres_members.py`.
- Start: P4a. Finish: explicitly composed admin invitation endpoint with redacted conflict/deny responses; activation still disabled.
- Verify: U4b+PG, M1/M2 HTTP-to-store/tenant denials. Rollback: disable invite route, revert P4b after P5/P6; retain reservations.

### P5 — Validated activation

- N: `src/forge/enrollment.py`, `src/forge/enrollment_store.py`, `tests/test_enrollment.py`, `tests/test_enrollment_api.py`, `tests/test_postgres_enrollment.py`, `docs/changes/member-activation.md`.
- M: `src/forge/api.py`, `src/forge/runtime.py`, `src/forge/members.py`, `tests/test_runtime.py`, `tests/test_postgres_api.py`, `tests/postgres_support.py`.
- Start: P4b reservations and existing `EntraTokenValidator.validate_principal`. Finish: opt-in bootstrap validates once, activates matching invitation and its entire department set under the archive/assignment lock, then reads normal bootstrap. Preserve existing token-validator-only test/injection contract.
- Verify: U5 + PG; M1 activation and legacy bootstrap regression. Rollback: disable enrollment and revert P5 wiring, not existing identities/memberships. Desktop login/PKCE remains excluded.

### P6 — Safe member transitions

- N: `migrations/0009_member_mutations.sql`, `tests/test_member_mutations.py`, `tests/test_postgres_member_mutations.py`, `docs/changes/member-mutations.md`.
- M: shared migration surfaces; `src/forge/members.py`, `src/forge/member_store.py`, `src/forge/lifecycle_api.py`, `src/forge/authorization.py`, `tests/test_members_api.py`, `tests/test_authorization.py`, `tests/test_postgres_administration.py`.
- Start: P5 active members. Finish: revisioned role updates and suspend/reactivate, reusing P3b association operations, database last-admin invariant across every permitted writer; designation remains initial-only.
- Verify: U6 + PG; M2/M3 and authorization race matrix. Rollback: disable mutations, revert P6 endpoints/store changes; retain last-admin database protections and data. Do not revert protective DDL to make old code pass.

## Contracts to freeze in RED tests

- Strong ETag format: quoted positive decimal membership/department revision; reject weak, wildcard, multiple or malformed If-Match as 422; missing 428; stale 412. Check authorization before revealing revision/existence. Revision overflow rejects without mutation/event.
- POST invite uses tenant UUID + object UUID, roles and department_ids (default empty set); duplicate organization/tenant/object reservation returns 409 without another event. Existing membership also conflicts. Email is not an input. Creation starts revision1; accepted state changes advance once. Repeated no-op updates/transitions return current state without a new event, after valid If-Match and authorization. Duplicate department IDs return 422; invalid targets reject the whole set. Assignment PATCH replaces the complete set under membership If-Match, never grants roles, and emits one event, not one per link.
- Proposed item routes: `PATCH /forge/v1/organizations/{organization_id}/departments/{department_id}` and `PATCH /forge/v1/organizations/{organization_id}/members/{membership_id}`; suspend/reactivate append `/suspend` or `/reactivate`. Collection GET/POST use `/departments` or `/members`. Archive is a department PATCH status transition, not DELETE.
- GET collection pages have bounded limits (default50, max100) and stable UUID cursor ordering. Admin reads organization members/areas; manager reads the intersection with their current authorized department set, including no access when unassigned. Deduplicate shared members before pagination and filter their department_ids to that intersection. Ordinary membership alone grants no management-read authority. Never return claims, email, invitation target IDs or secret-bearing exceptions.
- Pending invitations are separate from active/suspended memberships. P3b assigns existing members; P4a reserves intended departments/roles, not actual member links. P5 rechecks organization, every department and uniqueness at activation under the same organization lock as archive. An archived intended department rejects the entire activation. If target identity already exists, verify its canonical provider/issuer/object binding before reuse; never overwrite mismatched identity. Activation event is distinct from invitation event.
- Worker log allowlist: event ID, schema version, event type, outcome and revision; exclude tenant/object/actor/resource IDs, arbitrary metadata and raw exception strings. Legacy `audit_publication="pending"` response stays compatible: no new durable-audit claim.
- Worker claims include attempt counter, due time, lease expiry and fencing token. Acknowledge/retry requires matching event+token. Use database time, bounded batch/lease/backoff; cap delay, retain retriable failures rather than silently drop. No global-order guarantee. Consumer dedupe uses stable event ID; log duplicates are acceptable.

## Security and concurrency acceptance matrix

| Proof | Required real-PostgreSQL observations |
|---|---|
| O1 atomicity | Fail after resource update and after event insertion; neither state/revision nor event survives rollback. Successful resource changes have one event. Import conflict produces no duplicate. |
| O2 legacy integrity | Backfill preexisting and mirror late legacy rows with identical IDs; test synchronized migration/write boundary, old readiness and unchanged designation, full-visibility rejection and mirror failure rollback; original rows and deferred designation/event FK remain intact. |
| O2 lease ownership | Two independent connections synchronize on barriers, claim disjoint live leases via SKIP LOCKED, reclaim expired leases, reject old-token ack/retry, retry after publish-before-ack crash. Sink I/O occurs outside transaction. |
| M1 uniqueness | Two concurrent invites: one reservation/event. Two validated first logins: one bound membership/activation event. Wrong tenant with same object, wrong object, uninvited identity and email-only match bind nothing. |
| M1 activation failure | Inactive organization, archived department, identity mismatch and storage failure cannot partly bind or grant roles. Repeated bootstrap preserves legacy access behavior and does not re-activate suspended members. |
| D1/D3/D4 assignment/archive | Unique organization/member/department triples, same-org composite FKs, multi-area replace/unlink, duplicate and archived-target denial, no role escalation. Occupied archive rejects active AND suspended links. Synchronized archive versus assignment/activation proves either archive fails or linking fails, never partial sets/dangling links. |
| D2/RLS | Admin own-org reads/writes; manager own-area read only; other-area/org denied. Unknown/suspended/archived actors and inactive organizations cannot write. Missing/malformed/stale local context and pooled reuse leak nothing. |
| M2 current authority | Pause one connection before lock, revoke/suspend actor on another; resumed request reloads authority and fails. Suspension becomes visible on next bootstrap/read. |
| M3 invariant | One admin self-demotion/suspension denied; two admins competing to remove themselves/each other cannot remove both. Pending/unbound/suspended admin-role records do not count. Direct SQL through every granted writer path cannot bypass the guard. |
| Readiness | Tamper one prerequisite at a time: column/type/nullability, composite FK, uniqueness, event constraints, trigger/function body/search_path, ACL, ownership, RLS ENABLE/FORCE, role membership/BYPASSRLS and context cleanup. Readiness fails closed. Restore and prove ready. |
| Role separation | Runtime retains exact read-only grants. Writer/enrollment/worker use bounded explicit pools, never owner/superuser/bypass. Worker cannot mutate memberships; enrollment cannot grant arbitrary roles or match arbitrary identities. Cross-org worker access is internal publication authority, never a public read endpoint. |
| Migration safety | Fresh and populated upgrade, injected failure before COMMIT, unchanged prior data/policies after rollback, additive-schema compatibility with disabled features. Existing0002/0003/0004 probes remain unchanged. |
| Redaction | Inject recognizable secrets in inputs, DSNs, DB failures and sink failures; inspect HTTP envelopes, logs and repr. Zero markers escape; no raw metadata. |

The organization lock must precede fresh authorization/count queries in a READ COMMITTED statement after acquiring the lock; stale pre-lock snapshots are not authority. Lock ordering is organization, actor/target membership UUID order, then department/invitation UUID order. Every granted SQL path must use the same database-enforced protocol, including role/status changes and association/activation/archive paths; permissions must deny bypass paths. Include lock timeout, deadlock/serialization failure and connection cleanup tests; bounded failure is 503 with no event. Database guard enforcement needs actual two-session proof, not just a policy-unit count.

RLS helper design must avoid membership-policy recursion and must not widen PUBLIC policies. Reuse security-invoker patterns where possible; any proposed SECURITY DEFINER exception requires separate review of owner, FORCE RLS, fixed search_path and execute grants before implementation.

P1 exception premise approved by parent security review (Engram2694): the narrowly scoped mirror described in design.md. This is implementation authorization, not verified behavior. Preserve legacy metadata/grants unchanged; prohibit all owner membership paths and direct application execution, restrict destination INSERT by FORCE RLS, verify trusted backfill visibility before a bounded lock, and fail the whole transaction on mirror conflicts. Test fresh/populated/failed migration, concurrent boundary, direct/cross-org access denial and readiness tampering. No security proof may be removed for the 800-line budget.

## Exact runnable commands

Run in this worktree only after apply authorization. Worktree `.venv` and the already-pinned local PostgreSQL image are prerequisites; do not install dependencies or pull images implicitly. Commands for proposed modules become meaningful when their RED tests exist. **Zero discovered tests is failure**, not GREEN.

```powershell
# U1
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_outbox.py -v
# U2
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_outbox_worker.py -v
# U3a
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_departments.py -v
# U3b
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_department_assignments.py -v
# U3c
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_departments_api.py -v
# U4a
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_members.py -v
# U4b
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_members_api.py -v
# U5
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_enrollment.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_enrollment_api.py -v
# U6
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_member_mutations.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_members_api.py -v
# PG: required per slice, discovers every test_postgres_*.py including new modules
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
# Regression: existing non-PG modules, no unqualified discovery
foreach ($name in @('foundation','authorization','administration','administration_api','api','entra','runtime')) {
    & .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_$name.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Failed: $name" }
}
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
```

PG script currently accepts no module-selection parameter; do not invent one. It generates ephemeral database passwords (not signing keys), runs only its owned loopback PostgreSQL17 container and verifies exact-ID cleanup. No PG harness or credential generation is executed during planning. Future apply must keep cleanup output as evidence; unqualified unittest discovery outside this harness is not valid PG proof.

For every unit: write the smallest failing behavior test, run its U command or PG for database behavior, save failure reason/count, then implement only enough to pass, rerun, refactor and rerun unit+PG+regression. Import errors alone are not sufficient behavior evidence. Store command, result/count, RED cause, GREEN outcome, runtime boundary and rollback result in that unit's exact `docs/changes/member-*.md` file.

## Review and rollout boundaries

Confirmed dependency order: tracker -> P1a -> P1b -> P2 -> P3a -> P3b -> P3c -> P4a -> P4b -> P5 -> P6. P1a is independently useful for generic recording; legacy bridge proof belongs to P1b; subsequent boundaries expose only tested opt-in behavior. No half-built service is enabled by default.

| Unit | Planned branch | Immediate base |
|---|---|---|
| Tracker | `feat/forge-s3-member-lifecycle` | `feat/forge-tenant-storage` (existing prerequisites; eventual main target only after their integration) |
| P1a | `feat/forge-s3-outbox-recording` | `feat/forge-s3-member-lifecycle` |
| P1b | `feat/forge-s3-legacy-outbox-bridge` | `feat/forge-s3-outbox-recording` |
| P2 | `feat/forge-s3-outbox-worker` | `feat/forge-s3-legacy-outbox-bridge` |
| P3a | `feat/forge-s3-department-store` | `feat/forge-s3-outbox-worker` |
| P3b | `feat/forge-s3-department-associations` | `feat/forge-s3-department-store` |
| P3c | `feat/forge-s3-department-api` | `feat/forge-s3-department-associations` |
| P4a | `feat/forge-s3-invitation-store` | `feat/forge-s3-department-api` |
| P4b | `feat/forge-s3-invitation-api` | `feat/forge-s3-invitation-store` |
| P5 | `feat/forge-s3-member-activation` | `feat/forge-s3-invitation-api` |
| P6 | `feat/forge-s3-member-mutations` | `feat/forge-s3-member-activation` |

These are names/dependencies, not executed branch operations. Keep tracker draft/no-merge until integrated verification, and only tracker eventually targets main; never merge children directly to main. Each future child review includes a diagram marking its boundary (for example `tracker -> P1a -> P1b -> 📍 P2 -> P3a`). Prior-slice content in a child diff is a base bug. No push/PR/merge is authorized by this plan.

Current handoff: close only P1a nonempty legacy migration preservation evidence and reconcile these references. The exact eight closure surfaces and commands are recorded in odd/tasks/forge-p1a-closure.md. P1b and later slices remain unimplemented and unreleased. Parent verification precedes any staging/commit; RDD remains user-disabled with no native-review action.

Forecast includes source, SQL, readiness, tests and behavior docs with the exploration's approximately 2:1 test/source ratio. It is not a measured implementation diff. Measure additions+deletions against each immediate parent, including newly added files. Reserve review time under60 minutes per unit; never delete tests, compress code or hide generated changes to meet800. If actual work exceeds the best cohesive split, report the real overage and seek explicit exception/replanning rather than starting oversized apply.

Historical planning-only reconciliation: no new library documentation or product-source inspection was needed in that pass. Its repository evidence is retained, not claimed as fresh verification. Structural checks only: task word budget, local links, guard literals, slice/base mapping, first-slice paths/commands, decision consistency and unchanged protected files. That planning-only pass claimed no runtime proof; current P1a closure results are in apply-progress.md and odd/tasks/forge-p1a-closure.md.
