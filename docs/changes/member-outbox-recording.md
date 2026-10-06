# P1a: transactional event recording

An internal recorder now appends one stable event in the caller's transaction. It never commits, borrows a pool or authorizes a user. Trusted mutation services must supply authorization and transaction-local organization context; none are enabled here.

## Review boundary

Tracker -> **P1a recording (current)** -> P1b legacy bridge -> P2 worker.
Migration0005 adds a FORCE RLS destination and NOINHERIT, INSERT-only writer. Exact catalog/ACL readiness detects shape, grant, owner, role-membership and policy tampering. Runtime, binder and designator gain no destination access. No new functions or SECURITY DEFINER exception; original readiness constants are hash-frozen and executed against the retained schema.

The current event allowlist is `membership.updated` / `department.created`; later slices extend it with their behavior and tests. No arbitrary metadata is accepted. Duplicate event IDs or organization/resource revisions abort insertion; database errors are redacted. Original legacy events remain untouched and authoritative until P1b backfills/mirrors them. No worker, import or durable-audit claim exists.

## Historical implementation TDD evidence

| Cycle | Result |
|---|---|
| RED | U1: 3 missing-module errors; PG: 162 tests, 1 missing-table failure + 5 missing-recorder errors |
| Readiness/migration RED | PG: 164 tests, 14 errors (missing attestation/probe evidence) |
| GREEN | U1: 3 passed; PG: 165 passed in 33.087s; exact-ID container cleanup confirmed |
| Refactor | Removed temporary clause diagnostics without changing assertions; final rerun recorded in Engram apply-progress2679 |

Tests cover commit, failure after resource/event writes, duplicate conflicts, invalid shapes, absent/malformed/foreign tenant context, same-connection context cleanup, restricted direct access, fresh/populated/injected-failure migrations and readiness tampering. Original PUBLIC invoker helper permissions remain unchanged; the new role has no underlying membership SELECT authority.

## Verification and rollback

Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_outbox.py -v` and `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1`; then the plan's seven-module regression, compileall and pip check. Frozen rerun counts are persisted in apply-progress2679; no approval is inferred from passing tests.
Disable future consumers before code rollback; retain the additive table/data. The frozen old readiness query accepts this schema. P1b must ship its entire guarded bridge and proofs before P2 launches any consumer. Parent verification and commit remain pending. RDD is user-disabled; no native review is scheduled.


## Current populated-legacy closure proof

The new assertion first failed with empty legacy counts in both populated cases:
166 PG tests, one assertion failure, 38.414s. No import/setup error was the RED.
After the fixture-only correction, 166 PG tests passed in 36.681s on PostgreSQL
17.11; both harness runs confirmed exact owned-container removal and absence.

Each populated probe now commits one administrator role, matching designation
marker and initial-admin event with coherent Entra target binding and revision.
The marker/event pair is created in one transaction; SET CONSTRAINTS ALL IMMEDIATE
proves its deferred FK before commit. Full prior-row and policy snapshots remain
identical after both successful 0005 upgrade and injected SQL division failure.
Legacy counts are (0,0,0), (1,1,1), (1,1,1) for fresh/success/rollback respectively.
The successful generic destination stays empty (no bridge/import); rollback leaves
no destination or writer role and returns the connection to IDLE.

Current total: 309 tests passed, zero skips/failures: outbox 3 (0.020s), PG 166
(36.681s), foundation 13 (0.001s), authorization 6 (0.003s), administration 16
(0.110s), administration_api 21 (1.301s), api 18 (0.494s), Entra 38 (0.914s),
runtime 28 (14.033s). compileall, pip check and git diff --check passed.
The old 308-test result is preserved as historical evidence, not reused as this run.

Only the authorized migration-probe helper/assertions and documentation changed.
Shared DatabaseFixture/reset and every older top-level probe definition are exact
against the captured preexisting P1a bytes. All 61 protected files, including
production modules/migrations and unrelated uncommitted artifacts, remain exact.
A read-only combined baseline comparison hit Windows command-line length limits;
per-file in-memory comparisons succeeded without scratch writes.
Existing Starlette/httpx deprecation warning is nonblocking; no upgrade performed.

Numbering is reconciled: 0005 recording, 0006 future bridge, 0007 departments,
0008 invitations, 0009 mutations; ten implementation units excluding planning P0.
Historical RED/gate evidence remains labelled historical. RDD stays disabled.
Parent verification and commit authorization remain pending; P1b/O2/O3 and all
later slices remain unreleased. Engram2679 was read in full and not overwritten.
