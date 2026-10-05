# Forge initial administrator HTTP adapter

## Outcome and gate

F07b2a-http exposes the existing authenticated initial-only designation service
through an explicitly injected HTTP adapter. Parent refreshed/read back the full
parent and child mirrors and released implementation. The local candidate has
passed writer and independent checks. Parent spot check passed; the authorized
local work-unit commit is recorded below. H1-H4 are closed for this HTTP unit only.

Parent: odd/tasks/forge-administration.md (Engram 2534).
Baseline: 6a15710d30ae64b15051d8467747ab063794d0f2 on feat/forge-tenant-storage
in N:/Proyects/forge/.worktrees/tenant-storage. Historical 266 passing tests are
inherited evidence, not a new run. RDD remains OFF, disabled/unmanaged.

## Problem, objective and scope

The internal F07b2a service has verified authority and atomic persistence, but no
HTTP adapter. Add only POST /forge/v1/organizations/{organization_id}/initial-administrator.
Do not infer removal, recovery, reassignment, provisioning, deployment or public
exposure policy. Existing bootstrap and runtime composition stay unchanged.

## Accepted contract

| Boundary | Requirement |
|---|---|
| Composition | Keyword-only initial_administrator_service: InitialAdministratorService or None in create_app, default None; no create_runtime_app auto-wiring |
| Credential syntax | Exactly one valid Bearer Authorization header; reject missing/duplicate/comma-bearing/empty/whitespace-token values as 401 UNAUTHENTICATED |
| Authority | Call injected service.designate(raw_token, typed DesignationRequest) exactly once per valid attempt including replay; never bootstrap validator/principal, client roles or inferred operator |
| Unconfigured | Valid bearer with absent injection returns 503 SERVICE_UNAVAILABLE without authority or DB access |
| Request | UUID organization path; extra-forbid body with UUID membership_id, UUID operation_id and strict integer expected_revision from 1 through 2**63-2; reject bool/float/string |
| Result | Exact DesignationResult shape and UUID types; correlated org/member/operation; strict integer revision=expected+1 and literal pending publication; malformed result returns 503 without coercion |
| Public success | 200 with only organization_id, membership_id, operation_id, event_id, revision, audit_publication |
| Failures | DesignationDenied always 403 DESIGNATION_DENIED; conflict 409 DESIGNATION_CONFLICT; unavailable/unknown exception 503 SERVICE_UNAVAILABLE; validation 422 INVALID_REQUEST |
| Redaction | Existing fixed envelope, new request UUID, no credential/PII/config/exception details; 401 Bearer challenge and only 503 retryable |
| Execution | Synchronous route/dependencies use worker pool; preserve telemetry disabled and no global logging |

Service denial intentionally conflates invalid token and unprivileged operator;
the adapter must not invent a 401 distinction after service authentication.
JSON body parsing remains framework-owned. Authentication dependency precedes
ordinary field/path validation; do not promise syntax-error precedence for malformed JSON.

## Tasks and acceptance

- [x] H1 — Establish bounded English design and recovery checkpoint. Read existing
  API/service/real-RSA and owned-PostgreSQL fixtures; write this document and SDD,
  add parent child link, persist full child mirror and read back before release.
  Route: delegated direct, preparation for API/security writes exceeds mechanical work.
  Evidence: clean baseline HEAD observed; structural documentation readback only.
  Commit: 9539d621bc67b839772336f004f6b529c87b1a1f (shared coherent work unit).
- [x] H2 — Implement adapter with meaningful test-first HTTP proof.
  Route: delegated direct, API plus two non-trivial new test files.
  Observe assertion-based RED against current importable API before API edits.
  Cover injection/default deny, strict bearer/body/path, one call/replay, exact
  responses/correlations, all error mappings, redaction and worker-thread execution.
  Use genuine RSA Entra validation; no caller-built principal as authority.
- [x] H3 — Verify owned real PostgreSQL HTTP transaction and regressions.
  Route: delegated direct, bounded writer verification plus independent verifier.
  Cover success/replay single persistent grant/revision/event, changed payload 409,
  invalid/unauthorized tokens without DB mutation, missing injection, service outage
  and transactional failure with no partial write. Preserve old tests and fixtures.
  Run all commands below, offline wheel/fresh-import if existing tooling permits,
  document exact counts, failures, skips, cleanup and protected-path evidence.
- [x] H4 — Reconcile README/SDD/task proof and return verified local candidate.
  Route: delegated direct; parent independent verification and one spot check.
  No commit until separately authorized; then record exact hash/stats in this task.
  No push, PR, merge, deployment, overall F07b or product completion.

H1 checkbox describes the planning artifact, not implementation or delivery approval.
All remaining checkpoints require observed proof; mirrors are not approval receipts.

## Allowed edit surfaces

- src/forge/api.py
- tests/test_administration_api.py
- tests/test_postgres_administration_api.py
- README.md
- docs/changes/initial-admin-designation-http.md
- odd/tasks/forge-initial-admin-http.md
- odd/tasks/forge-administration.md (child link/progress only)
- .local/postgres-test/**
- .local/runtime-test/**

Protect migrations 0001–0004, administration service/store, authorization, Entra,
runtime, old tests/fixtures, harness script, UI/assets and dependency files.
No install/upgrade, remote/network/live credentials, ownership or RDD changes.
Only existing venv and cached Docker owned ephemeral harness with exact-ID cleanup.

## Verification after release

Run from the worktree root, recording actual results rather than inherited proof:

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_administration_api.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_administration.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_authorization.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

Offline package staging and child TMP/TEMP stay under .local/runtime-test.
Use existing tools only with --isolated --no-index --no-deps --no-build-isolation
--no-cache-dir; inspect wheel bytes and fresh import/route proof, no download/install.
No UI change, so browser proof is not applicable; inherited C10b gaps stay open.

## Delivery, rollback and progress

Forecast 650–1000 authored changed lines; 400 is advisory, never code-golf or an
artificial file-type split. Existing local feature-branch-chain strategy continues.
One coherent adapter/test/docs work unit, separately authorized commit after checks.
Rollback is removal of this adapter/test/docs unit, not prior service/migrations.
Expected verification cost: a few local minutes, no external spending.
Current proof: writer, independent and parent spot passed; local commit observed.
Next: parent refreshes its full administration mirror and selects separately scoped work.
H4 is closed for this adapter only; no remote/deployment operation.
Child mirror: topic odd/forge-initial-admin-http/tasks, full file content plus locator.

## Observed writer candidate evidence

All 296 applicable tests passed with zero skips/failures in final runs:
156 PostgreSQL (147 inherited + 9 new) in 37.622s, 21 new HTTP in 0.731s,
16 service in 0.179s, 18 prior HTTP in 0.823s, 28 runtime in 18.073s,
38 Entra in 1.214s, 6 authorization in 0.002s and 13 foundation in 0.003s.
The 266 baseline tests were actually rerun; 30 new tests exercise this adapter.
Final compileall, pip check and diff check passed. Owned server 17.11; both
container-bearing runs confirmed exact-ID cleanup and absence. No live credentials.

Meaningful RED: 19 methods, 55 assertion failures (absent route/contract) and
one expected missing-keyword TypeError, 2.745s. The temporary pre-implementation
factory fallback was removed. First implementation run: 19 tests, four failures,
0.774s. Two raw whitespace-header cases were normalized by HTTPBearer; raw header
syntax now validates before accepting its credentials. The fourth failure was
OpenAPI's floating-point bigint maximum representation; runtime exact integer
limits are tested, and the schema description provides the precise bound.
Initial corrected GREEN: 19 tests, 0.610s; two runtime/telemetry cases brought final
new HTTP coverage to 21. No existing tests were changed.

First DB command could not access the Docker named pipe under the sandbox;
it created no container. Approved narrow escalation ran the unchanged cached
owned harness. First real DB run: 156 tests, one failure, 42.594s. The changed-target
replay fixture selected an unbound generic identity, correctly returning 403 before
conflict; the new test now binds that second existing target coherently, as the
old service tests do. No service/store policy was changed. Full rerun passed above.
Actual injected outbox SQL division failure observed own-transaction claim/role/
revision (1,2,1), then HTTP 503 and exact pre-attempt persistent state; retry succeeds.

Offline staged wheel using existing tools and no index/deps/build-isolation/cache/
install/download passed: all 11 modules and three static assets are byte-identical,
fresh isolated wheel imports/resources, configured synthetic adapter 200, default
runtime designation 503 and existing status routes passed.
Wheel SHA256: 1c23252a6c55c69ed8ee60fb4e25a0ba29c81779eca81d732944e86cb0bf2e38.
Build/fresh-import script, logs and proof JSON are in ignored .local/runtime-test
with f07b2a-http-* names. The packaging synthetic port verifies packaging only;
separate real RSA and PostgreSQL tests establish authentication/persistence proof.

Protected migrations, administration service/store, runtime, Entra, old tests,
fixtures and harness are unchanged. Seven authored paths are changed/new; ignored
logs, package staging and Docker config artifacts are not delivery files.
No browser run applies: UI unchanged, inherited C10b limits remain unresolved.
RDD remains OFF, disabled/unmanaged. Independent verification and parent spot
passed; no native review approval or deployment authorization is implied.

Final read-only candidate-stat collection first failed decoding UTF-8 as Windows
cp1252. Inspection also identified mojibake from prior documentation read/write
helpers using the platform default. Explicit UTF-8 repair restored exact historical
parent content and the two unchanged README Unicode passages; parent prefix equality
against HEAD is asserted. No Python source/test behavior changed. Packaging was
rerun afterward so the final wheel includes the repaired README metadata.

## Independent verification and local commit authorization

Parent reports independent forge_http_verify: 296 passed with zero skips/failures
and no concrete defect. Its 156 PostgreSQL tests took 53.974s on server 17.11;
exact owned-ID cleanup passed. All 46 protected Git blobs matched; wheel contents
matched all 11 modules and three assets, with the recorded SHA256 above.
Parent separately ran 21 HTTP tests in 4.638s, exit 0, plus diff check, and confirmed
the exact API and both new test hashes. No source/test bytes changed afterward.
Historical sandbox stalls were resolved through narrowly approved escalation.
Starlette's httpx TestClient deprecation warning remains a nonblocking follow-up;
no dependency upgrade, installation or warning suppression is part of this unit.

The parent authorized one local coherent behavior/test/docs commit, message
feat(admin): expose initial administrator designation endpoint, followed by a small
task-only actual-identity record. Existing feature-branch-chain strategy applies;
the approximately 900-line security/verification unit is not artificially split.
Only seven approved authored paths may be staged. No .local artifacts or AI
attribution, push, PR, merge, public exposure or UI completion claim.

## Local work-unit delivery

Behavior commit: 9539d621bc67b839772336f004f6b529c87b1a1f.
Message: feat(admin): expose initial administrator designation endpoint.
Exactly seven approved authored paths, +922/-4 (926 authored changed lines).
All seven staged blobs matched the worktree before commit; API and both new test
SHA256 values matched independent verification. Clean worktree observed immediately
after the behavior commit. This task-only follow-up records the observed identity
and H4 closure without altering behavior, tests or historical parent content.

The initial staging command could not create index.lock despite turn Git metadata
permission. Narrow approved escalation staged only the exact paths and committed;
no ownership/configuration changes or broad cleanup. Git's automatic committer
identity warning was retained without global identity edits or amend.

Rollback boundary is the exact adapter/test/docs behavior unit above, not prior
service or migrations. Independent 296 tests and parent 21-HTTP spot remain the
verification of record; documentation-only closure adds structural readback.
No source-mutating hooks or verified-byte drift observed. RDD remains OFF,
disabled/unmanaged; no native approval, push, PR, merge, deployment or UI claim.

A raw commit/worktree byte comparison initially failed on inherited CRLF/LF
normalization. All three verified raw SHA256 values stayed exact; Git clean-filter
object equality and explicit CRLF-to-LF readback confirmed committed correspondence.
No source bytes, EOL configuration or hooks were changed to satisfy that check.
