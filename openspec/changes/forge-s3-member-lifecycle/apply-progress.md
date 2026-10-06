# Apply progress: P1a verified and delivered locally

## Current closure scope

P1a populated-legacy proof closure and its local Git delivery are complete.
The prior generic recorder is implemented, not currently RED. RDD is user-disabled;
historical references to native review or prior blocking gates below do not apply
to this closure. The user authorized only the two local delivery units below;
P1b bridge, worker and lifecycle work remain unreleased.
Current proof and local delivery results are appended below; recovery task:
odd/tasks/forge-p1a-closure.md. Full Engram2679 retains additional original evidence
and must not be overwritten with a shorter disk copy.

## Historical P1a implementation result

Parent approved P1a/P1b with the existing child for recording and future child
`feat/forge-s3-legacy-outbox-bridge`. P1a implements the generic transaction-bound
recorder, INSERT-only scoped writer, exact readiness and migration/rollback proof.
No bridge, legacy import, worker or new SECURITY DEFINER function is installed.
O2/O3 remain incomplete; the original legacy table remains its source of truth.

| Task | Safety net | RED | GREEN | Triangulate / refactor |
|---|---|---|---|---|
| 1.1a P1a | Original 156 PG tests | U1 3 errors; PG 162 tests: 1 missing-table failure + 5 recorder errors | U1 3 passed; PG 165 passed (33.087s) | Commit/rollback/duplicate/tenant paths; frozen old readiness; diagnostics simplified |
| Writer CONNECT attestation | P1a GREEN above | PG 165 tests: revoked CONNECT still reported ready (33.201s) | Final rerun recorded in Engram2679 | Added exact CONNECT requirement, retaining all old queries |
| FK enforcement attestation | Same safety net | PG 165 tests: disabled FK triggers still reported ready (33.418s) | Final rerun recorded in Engram2679 | Require internal constraint triggers enabled; no application trigger added |

Readiness/migration RED also observed 14 errors across 164 tests before those APIs
existed. Intermediate GREEN attempts exposed existing PUBLIC invoker permissions
and an automatically named check; both were corrected without changing legacy SQL.
All owned harness runs confirmed exact-ID cleanup. Final post-normalization unit,
PG, seven-module regression, compileall and pip-check results are persisted in
Engram2679 after the candidate freeze; no file edits follow that verification.
Review/commit are pending, not inferred from tests. No staging or remote operations.

## Historical pre-split continuation: test surface resolved, size gate active

Read full Engram2679 and preserved all prior evidence below. Parent now authorizes
the exact `tests/test_postgres_rls.py` amendment, including singleton bridge signature
and rejection of any unexpected privileged function. The former surface gate is closed.
No new product/test edits or test executions occurred in this continuation.
Complete P1 forecasts 880–1,125 authored lines; see implementation-plan.md for the
per-surface calculation and one precise P1a/P1b split (550–750 / 650–780).
The split and new bridge migration/test/doc paths require parent handoff; no size
exception, branch operation, incomplete bridge or omitted security proof is assumed.
Current source state remains RED, as verified in the prior frozen handoff (Engram2679):
U1 1 error; PG 156 passed/1 missing-destination failure; regression 140 passed;
compileall/pip check passed. These are retained results, not newly executed tests.
All implementation tasks, native review and commit remain pending.

## Historical resumed attempt (cumulative update)

Parent approved atomic migration backfill plus a narrow AFTER INSERT SECURITY DEFINER
bridge (Engram2694), resolving the historical importer design gate below. Updated
design.md, implementation-plan.md and tasks.md accordingly; original legacy metadata
and readiness remain unchanged. This approval is not verified bridge behavior.

New execution gate: `tests/test_postgres_rls.py:158` requires exactly seven tables,
and `:172-176` requires zero SECURITY DEFINER functions across the entire forge schema.
The mandatory harness cannot accept the new destination and approved bridge without
updating this test, which is outside the nine allowed P1 product surfaces. No test
was skipped, filtered, patched indirectly or weakened. Request a bounded surface
amendment for that file: exact expected table set plus the one fully attested bridge
exception; keep all prior FORCE RLS/ownership and invoker assertions intact.

| Cycle | Command | Observed result |
|---|---|---|
| Unit initial attempt | U1 command below | 1 error: missing forge import path; corrected test setup, not production |
| Unit RED | U1 | 1 error: missing forge.outbox |
| PG behavioral RED | PG command below | 157 tests, 35.902s: 156 passed, new destination test failed (absent table) |
| Unit provisional GREEN | U1 | 1 passed, 0.004s with minimal frozen Event skeleton |
| PG attempted GREEN | PG | 157 tests, 36.548s: 156 passed; new RLS destination assertion passed, existing table-count assertion failed (8 != 7) |

Both PG runs confirmed exact-ID container cleanup. The SECURITY DEFINER-count
conflict is source evidence, not an executed failure (bridge was not implemented).
Removed the provisional Event and migration skeleton and restored the harness
migration list before handoff. Only initial RED tests and planning evidence remain;
no incomplete production behavior is left enabled. Unit GREEN was provisional and
does not describe the handoff tree. Triangulation/refactor and all remaining bridge,
backfill, authority, concurrency, old-runtime and tamper proofs remain pending.
Original baseline/history below is retained, not claimed as current candidate proof.

## Historical attempt: before parent bridge approval

Status: blocked. Strict TDD remains active; no implementation task is complete.
No previous apply-progress was found in files or Engram. Review and commit remain pending.

## Execution boundary

- Worktree: `N:/Proyects/forge/.worktrees/tenant-storage` only.
- Base and current HEAD: `48c3e8eaf14fe22073775fd60d18c3f26f34df71`.
- Created tracker `feat/forge-s3-member-lifecycle` at that base.
- Created and selected child `feat/forge-s3-outbox-recording` at that base.
- Chain: tracker -> **P1 (current, blocked)** -> P2 -> remaining approved slices.
- No staging, commits, remote operations, dependencies, keys or review lifecycle.
- Existing `.gitignore` diff and unrelated proof documents remain untouched.
- Required CodeGraph initialization created local untracked `.codegraph/`; it is tooling output, not P1 source or a commit candidate.

## Blocking contract

The separate restricted importer needs permission to read committed legacy events.
`migrations/0004_initial_admin_designation.sql:53-64,146-152` grants legacy access
only to the designator and forces RLS. In `src/forge/postgres.py:491-503`, the
existing readiness query fixes both policy role lists to `forge_designator` and
requires exactly two policies on `initial_admin_outbox`.

A new importer SELECT policy, or adding its role to an existing policy, therefore
invalidates the old readiness query. Updating the new query does not make the old
binary accept the retained schema after code rollback, as design.md requires.
Reusing designator authority conflicts with the separate least-privilege worker;
a SECURITY DEFINER bridge requires separate review under the implementation plan.

This is a source-verified design conflict, not a reproduced migration failure.
No candidate migration or importer was written. Parent reconciliation is needed:
prefer an explicit rollback compatibility floor retaining the extended readiness
check, with exact additional-role attestation and no runtime data grants. This
changes the rollback promise and is a recommendation, not an approved decision.
If old-binary rollback is mandatory, separately design/review a bridge first.

## TDD Cycle Evidence

| Task | Layer | Safety net | RED | GREEN | Triangulation | Refactor |
|---|---|---|---|---|---|---|
| 1.1 P1 recording/import | PostgreSQL + unit planned | 156 existing PG tests passed | Not started: design gate | Not started | Not started | Not started |

## Commands and results

| Command | Result |
|---|---|
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1` | Baseline exit 0; 156 tests, 32.562s; PostgreSQL 17.11; exact-ID container removal/readback confirmed |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_outbox.py -v` | Not run: no P1 tests written; zero tests is not GREEN |
| Plan's seven-module regression loop | Not run: stopped before product changes |
| `.\.venv\Scripts\python.exe -m compileall -q src tests` | Not run: stopped before product changes |
| `.\.venv\Scripts\python.exe -m pip check` | Not run: stopped before product changes |

No final candidate verification, atomicity/import proof or approval is claimed.
Baseline emitted the existing Starlette/httpx deprecation warning; no dependency changes made.

## Handoff

All implementation checkboxes remain unchecked, including 1.1 and cross-slice 4.1/4.2.
Resume at P1 RED only after reconciling the importer/rollback authority contract.
No P2 worker, lifecycle endpoints, recovery or later-slice behavior was implemented.
Skill resolution: paths-injected (work-unit-commits, chained-pr, cognitive-doc-design),
plus sdd-apply, strict-tdd and shared SDD protocols. CodeGraph used for source inspection;
Graphify skill loaded contextually, but its generation/delegation workflow was not run.


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
Parent verification and local commit authorization are complete; P1b/O2/O3 and
all later slices remain unreleased. Engram2679 was read in full and not overwritten.

## Authorized local delivery

Behavior commit: e8c489f8a0c7bcb5f614f8f7fa62dfb879d14c16.
The user explicitly granted this complete 807-authored-line exception (804 added,
3 deleted) on 2026-10-06. All 12 authorized behavior/test/evidence paths were
committed unchanged after an empty-index check and all 68 frozen hash matches.
The follow-up documentation unit reconciles seven S3 planning files and closure
bookkeeping only; it adds no runtime behavior. Local delivery is complete.

Independent verification observed 309 passes with no failures/skips, including
166 PostgreSQL tests in 37.054s and exact owned-container cleanup. Protection
readback matched 61 files plus 11 unchanged helper definitions. Parent spot:
3 outbox tests passed in 0.005s. These are separate from the writer timings above.
No tests rerun at commit time; exact verified source/migration/test bytes remain.
Delivery checks cover staged paths/counts, hashes, links, numbering and diff checks.
RDD remains disabled/unmanaged, with no pending native approval.
All P1b/O2/O3 and later work stays pending; no remote/deployment action occurred.
