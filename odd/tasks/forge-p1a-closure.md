# P1a populated legacy migration proof closure

## Authorized outcome

Close only the generic P1a recording proof gap and reconcile its existing specs.
The worktree already contains substantial uncommitted P1a implementation and
unrelated artifacts; preserve them exactly outside the eight allowed surfaces.
HEAD 48c3e8eaf14fe22073775fd60d18c3f26f34df71,
branch feat/forge-s3-outbox-recording. No staging or commits authorized.

Full Engram observations 2679 and 2712 were read. Observation 2679 contains extra
historical evidence beyond disk; do not replace it wholesale. Current project
for this task is forge, explicitly supplied by the parent; no session ID is used.
No local or ancestor AGENTS.md file was found; supplied session instructions apply.
Read-only snapshots of 68 existing files and compressed contents of seven allowed
existing files are held in memory before any write. Initial Git sandbox lookup
failed; narrowly elevated readback succeeded without ownership/config changes.

## Tasks

- [x] C1: Observe assertion-based RED for nonempty legacy migration evidence;
  then seed valid membership_roles, initial_admin_designations and
  initial_admin_outbox rows for successful populated upgrade and injected rollback.
  Preserve old probes and shared reset semantics; prove complete row snapshots
  unchanged and destination absent after rollback.
  Route: delegated direct, nontrivial fixture and assertion changes across two files.
- [x] C2: Reconcile current spec references to 0006 bridge, 0007 departments,
  0008 invitations and 0009 mutations; ten implementation units after P1a/P1b split.
  Mark obsolete RED/gate sections historical without deleting their evidence.
  Route: delegated direct, related multi-file documentation consistency.
- [x] C3: Run full authorized verification, document exact RED/GREEN results and
  current delta against the in-memory preexisting candidate, refresh this mirror,
  then return for parent verification. No further slice, staging or commit.
  Route: delegated direct, owned PostgreSQL and focused regression verification.

## Acceptance and constraints

Both populated scenarios must begin with at least one valid row in each of the
three legacy tables; successful migration does not import legacy events.
Injected real SQL failure must reach aborted transaction state then rollback,
preserve prior rows/policies, and leave no generic destination or writer role.
Use actual deferred FK-valid marker/event pairs and isolated fixture population,
not mocked snapshots or weaker constraints. No cross-test contamination.
No production modules/migrations, old probes, RLS/ACL or harness-script changes.

RDD remains user-disabled; do not run, start or enable native review.
No installs, downloads, real credentials, remote/deployment or C10b/server changes.
Existing cached-image owned loopback PostgreSQL harness is authorized, with exact
owned-ID cleanup. Narrow escalation may resolve sandbox denial; never repair
ownership/configuration. Historical 308 passes are not newly executed evidence.
New artifacts use English and explicit UTF-8; preserve existing artifact language.

## Allowed edit surfaces

- odd/tasks/forge-p1a-closure.md
- tests/postgres_support.py
- tests/test_postgres_outbox.py
- docs/changes/member-outbox-recording.md
- openspec/changes/forge-s3-member-lifecycle/tasks.md
- openspec/changes/forge-s3-member-lifecycle/proposal.md
- openspec/changes/forge-s3-member-lifecycle/implementation-plan.md
- openspec/changes/forge-s3-member-lifecycle/apply-progress.md

No scratch-file writes are authorized beyond existing harness behavior;
baseline snapshots and command results remain in active tool memory.

## Verification

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
    .\.venv\Scripts\python.exe -m unittest discover -s tests -p test_outbox.py -v

Run existing foundation, authorization, administration, administration_api, api,
entra and runtime unittest modules separately; no zero-test or skipped passes.
Then python -m compileall -q src tests, python -m pip check, git diff --check.
Measure protected-file hashes against preexisting bytes, not HEAD alone.
No commit until parent verifies the candidate. Full mirror topic:
odd/forge-p1a-closure/tasks, project forge; parent owns other full mirrors.

## Current status

Writer proof closure is verified. Parent independent verification/delivery remains pending.
Prior empty-to-empty legacy preservation evidence is a coverage gap, not observed
data loss. Generic recording stays separate from future legacy bridge/publication.


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
