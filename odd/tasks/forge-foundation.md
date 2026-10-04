# Forge foundation delivery

## Current decision and next action

F05a is functionally complete and committed in the isolated checkout
`N:/Proyects/forge/.worktrees/tenant-storage`, branch
`feat/forge-tenant-storage`, from `1e2592193e29d87e0becb6d704c2913768ae5f8b`.
F04 remains functionally verified and locally committed, not integrated. The user
selected choice 2 for its native review: `declined_this_candidate`, target
`da5a138a`; this is not approval. Preserve the API checkout and frozen original.
Parent read both full documents, refreshed/read back mirror 2374 and explicitly
released F05a. Writer, independent verification and parent spot check pass; local
commit is recorded below. F05a native review remains pending, not approved.
F05b is not implemented. Parent owns post-commit mirror/native assessment.

## Authorized outcome and boundaries

Build the generic Prometheon Forge MVP incrementally, using ODD and small SDD
change specs where useful. Preserve the functioning hotel deployment, credentials,
upstream snapshots and the original workspace checkpoint. No remote operations,
credential/session reuse, spending, production migration, push, PR or merge.

Product root: `N:/Proyects/forge`. Its original checkout has a frozen native review
whose bound operation failed with `operation_timeout`; the user chose to stop that
review. Do not edit, abandon, retry, reset or otherwise mutate that checkout or its
review authority. The isolated F04 branch does not approve or close the old review.
Workers must not invoke or toggle the native review lifecycle.

Source of truth: PF-00 through PF-12 under external
`outputs/prometheon-forge/specs/`. Retain OpenYak agent core and OmniRoute routing;
implement Python/FastAPI control plane, with PostgreSQL/RLS as a later separate
proof. Historical 'Promtheon Forge' own-agent-loop memory describes a different
MVP whose recorded directory is absent; it is not implementation evidence here.

## Sprint plan

| Sprint | Outcome | Exit condition |
|---|---|---|
| S1 | Executable contracts and membership policy | Domain/HTTP denials tested; public bootstrap only; DB/RLS separately proven before isolation claim |
| S2 | Corporate sign-in and client spike | Entra PKCE and Forge token validation integrated; no runtime test identity |
| S3 | Organization administration and branding | Provisioning/revocation and versioned configuration; one client build for two organizations |
| S4 | OmniRoute and budgets | Scoped routing/capabilities, atomic reservations and truthful retry/limit UX |
| S5 | Image tools | Owned idempotent jobs, references/editing and authorized downloads |
| S6 | Skills and audit | Draft backup distinct from reviewed publication; grants/restore and redacted events |
| S7 | Packaging and pilot | Signed Windows updater, restore drill and two-organization pilot checks |

These are ordered delivery increments, not calendar commitments. S1 is NOT complete.

## Work units and observed status

- [x] F00 — Read-only explorer mapped specs/upstreams; historical implementation absent locally. Route: delegated (repository mapping).
- [x] F01 — Isolated repository, sprint plan and foundation change spec. Parent readback/mirror completed before implementation. Route: delegated (preparation and multi-file documents). Included in `4281b990f90ba9708e2ec82caf1fdf7b9c390bfb`.
- [x] F02 — Pure-domain trusted identity/membership authorization and allowlisted bootstrap. Observed RED then GREEN; tests/docs in `4281b990f90ba9708e2ec82caf1fdf7b9c390bfb`. Route: delegated (multi-file behavior).
- [ ] F03 — Historical independent verification and parent spot check passed, but native review did not complete. No approved verdict or receipt is claimed; retain this historical gap without restarting old authority.
- [x] F04 — Bounded FastAPI bootstrap transport. Route: delegated (new transport, HTTP tests, dependency metadata and accompanying spec). See seven acceptance checkpoints below. Self-verification, independent verification and parent spot check passed; local commit recorded below. Native review is NOT approved.
- [x] F05a — Minimal PostgreSQL migration and genuine RLS/role/constraint proof. Route: delegated (multi-file SQL, local harness and integration tests). Implemented with observed real DB RED/GREEN and writer checks; independent and parent verification passed; local behavior commit recorded below. No runtime database reader.
- [ ] F05b — Synchronous pooled bootstrap reader and database-backed HTTP proof. Route: delegated (adapter, pool and HTTP integration tests). Pending separate unit after F05a; no Entra, UI or wider product schema.

## F04 acceptance checkpoints

- [x] F04.1 — Parent reads this document and `docs/changes/api-bootstrap.md`, mirrors the full task document under `odd/forge-foundation/tasks`, and explicitly releases the source-write gate.
- [x] F04.2 — Resolve compatible exact FastAPI/uvicorn runtime and httpx test pins in a worktree-local virtual environment. Do not alter bundled Codex Python or add pytest. Record dependency/runner evidence; unavailable dependencies are a blocker, not RED.
- [x] F04.3 — Observe meaningful failing HTTP tests against an importable stub before implementation. The HTTP contract covers auth before organization lookup, missing/malformed/rejected auth, spoofed identity headers/cookies, UUID query validation and default-deny configuration.
- [x] F04.4 — Implement injected trusted token-validator and scoped bootstrap-reader ports with production default accepting no bearer token. Read fresh data per request, verify identity and all organization IDs before revealing owned suspended membership, and reuse the existing domain allowlist unchanged. No runtime fixtures or fake-auth environment switch.
- [x] F04.5 — Observe passing HTTP tests for allowed projection/no secrets, missing/inconsistent/wrong-identity and cross-organization records (including foreign suspended membership), live suspension reread, secret-rich provider exceptions, PF-10 envelopes and OpenAPI security/response contracts. Health is process-only liveness; capabilities beyond the domain subset remain deferred.
- [x] F04.6 — Entire unittest suite GREEN, compileall, pip check, whitespace check and loopback-only uvicorn smoke are observed and recorded. UI: N/A (no screen). Writer, independent and parent checks passed. Native review was explicitly declined for this candidate, not approved.
- [x] F04.7 — One coherent behavior/tests/spec work-unit commit on `feat/forge-api-bootstrap`, after parent authorization. Record commit identity, exact results and authored lines. Local feature-branch-chain only; no push/PR/merge. Do not infer native review completion from functional verification or Git commit.

## F04 exact checks and runtime evidence

Run from the isolated worktree after dependency resolution, using its own Python:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
.\.venv\Scripts\python.exe -m uvicorn forge.api:create_app --factory --app-dir src --host 127.0.0.1 --port 8765
```

First command supplies observed RED against the stub, then GREEN. In the last
command, verify `GET http://127.0.0.1:8765/healthz` returns process-liveness 200 and
`GET http://127.0.0.1:8765/forge/v1/bootstrap?organization_id=00000000-0000-0000-0000-000000000001`
with no Authorization returns structured 401 plus `WWW-Authenticate: Bearer`.
Stop the local server afterward. Parent spot check reruns the full unittest command.
Check untracked authored files for whitespace too; `git diff --check` alone does not
cover untracked files. Writer results below are observed F04 proof; parent/independent results are recorded below.

## Delivery strategy and rollback

User-approved feature-branch-chain, local only. Baseline/root commit:
`5aa398bf80c44083a7f9ef7ac1066a33bd4cf9e9`. F01/F02 commit and isolated branch point:
`4281b990f90ba9708e2ec82caf1fdf7b9c390bfb` (`feat(auth): authorize organization bootstrap`).
Its observed Git numstat is 434 additions, 0 deletions across nine authored files.
F04 original forecast: approximately 500–750 authored added/deleted lines including
transport, HTTP tests, dependency metadata and documentation. Actual authored count
will be recorded after the final documentation snapshot; do not hide any overage.
The coherent security/transport contract can exceed the advisory 400-line budget;
do not omit tests, compress code or split by file type. F04 is its own local chain
slice after the foundation branch point. Future PR boundaries remain uncreated.

F04 rollback removes only its API module, HTTP tests, dependency additions and change
spec/tracking evidence; the committed foundation, upstream snapshots and frozen
original checkout remain intact. Conventional commits only; no AI attribution.

## Historical evidence retained (not fresh F04 proof)

On 2026-10-03 Python 3.12.14 at
`C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
ran foundation RED: 13 methods with 23 `NotImplementedError` subcase errors;
GREEN: 13 methods passed; compileall exit 0. Standard-library unittest avoided the
then-unavailable pytest and needed no downloads. This dependency-free exception
applies to F02, not to the proposed HTTP transport.

Independent verification ran 13 unit tests plus 26 adversarial checks, including
all 16 two-organization ID combinations, identity/status denials, secret exclusion
and response independence. Parent reran 13/13 tests, exit 0. Writer checked
whitespace in all nine authored files. Runtime/UI: N/A for that pure-domain unit.

Git relocation originally lost empty metadata directories; parent restored them.
Author identity subsequently resolved via `git var GIT_AUTHOR_IDENT`; no identity
override or global configuration mutation was made. Foundation plan/spec/source
were committed together, contrary to the earlier stale unchecked F01/F02 rows.

Earlier native review preflight required intended-untracked selection before Git
tracking; no START/consent/reviewer/approval existed then. Later parent evidence
records RDD on (global), frozen review and `operation_timeout`, not completion.
These are different historical checkpoints; neither is a current approval.
Progressive real UI testing remains required as screens appear; unit tests alone
are not UI certification and cannot guarantee zero errors.

## Memory and next step

Engram project: `prometheon-forge`. No authoritative runtime session ID was provided;
omit `session_id`. Parent owns readback/mirror under `odd/forge-foundation/tasks`.
F04 parent readback/full mirror of preparation completed (observation 2374); its source
gate was released. F05a parent readback/full mirror completed; its gate was explicitly released.
Independent verification and parent spot check passed; parent authorized local
commits. No native review operation was performed by the writer.

## F04 writer evidence — 2026-10-03

- Worktree-local venv imports succeeded; official PyPI resolution: FastAPI 0.142.2,
  uvicorn 0.54.0, httpx 0.28.1; metadata pins match installed versions. Starlette 1.7.0
  and Pydantic 2.13.5 resolved compatibly; no broken requirements.
- RED against importable no-route FastAPI stub: 18 HTTP methods, 55 assertion
  failures plus one absent OpenAPI path error; exit 1. Dependencies had imported
  successfully before RED, so this is a missing-behavior failure, not environment.
- GREEN: 18/18 HTTP methods; entire suite 31/31 (18 HTTP + 13 unchanged domain), exit 0.
  Tests include all 16 organization combinations and sync-port worker-pool execution.
- `compileall -q src tests`: exit 0; isolated `pip check`: exit 0.
- Loopback-only owned uvicorn: `/healthz` 200, default bootstrap 401 structured
  `UNAUTHENTICATED` plus Bearer challenge. Owned process terminated afterward.
- Starlette warns that httpx TestClient support is deprecated; compatibility is
  observed for the installed pins, not guaranteed for future dependencies.
- Domain source/tests unchanged. UI N/A. Independent verifier and parent spot check
  passed; local behavior commit observed. Final writer whitespace checks are recorded below.

Final writer rerun: full suite 31/31, compileall and pip check exit 0;
`git diff --check` exit 0; all eight authored files (including untracked) have
zero trailing-whitespace lines. Foundation source/tests diff is empty.
Writer-finalization snapshot: 933 authored additions plus deletions against the branch point,
including tracked documentation churn and all three new files; no generated files.
This exceeds the 500–750 forecast because reconciled historical tracking and
complete HTTP/security tests accompany the transport; no code-golf or artificial
file-type split. User-approved feature-branch-chain remains local only.

## F04 independent and parent verification

Parent-provided independent verification passed: full 31-test suite and pip check;
malformed/duplicate authorization, invalid query before lookup, live configuration
revision, owned suspension 403/foreign 404, secret-rich operational failures and
response-validation redaction, and OpenAPI. All 17 observed error UUIDs were unique;
the diagnostic script's expected count of 18 was a harness expectation mismatch,
not an implementation failure. Parent reran all 31 tests: exit 0.
Original checkout was independently confirmed clean. This is functional proof,
not native review approval. Local commit success is observed below. DB/RLS, Entra integration and real UI
remain unimplemented. Native review was explicitly declined for this candidate, not approved.

## F04 local commit evidence

Behavior/tests/spec: `34009c465aca6a64e67479d144755f024262a004`
(`feat(api): expose authorized bootstrap transport`), observed on
`feat/forge-api-bootstrap`. Exactly eight approved files staged; `.venv` excluded.
Cached whitespace check passed. Numstat: 841 additions, 104 deletions, 945 authored
lines; this final precommit count supersedes the earlier 933-line writer snapshot.
No push, PR, merge or native review action occurred. Native review was explicitly declined for this candidate, NOT
approved; original F03 remains incomplete and DB/RLS/Entra/UI are still pending.

This documentation-only evidence follow-up records the observed behavior hash,
without trying to store its own future hash. Its identity and final clean checkout
proof are supplied in the worker handoff for the parent recovery mirror.
Next: parent refreshes the full task mirror and releases only the bounded F05a unit;
no unfinished F04 functional check is hidden by the commit.

## F04 review disposition and F05 preparation

F04 behavior `34009c465aca6a64e67479d144755f024262a004` and tracking
`1e2592193e29d87e0becb6d704c2913768ae5f8b` are inherited by this new checkout.
Git readback confirms the named branch/base; no source, dependency or container
operation occurred in this planning turn. The parent's user choice 2 returned
`action: declined`, `consent: declined_this_candidate`, target `da5a138a`.
Earlier pending-review statements describe their historical checkpoints only.
No approved receipt exists; F03's stopped original review remains untouched.
The existing 31 tests were proven for F04, not rerun as PostgreSQL evidence here.

## F05a acceptance checkpoints

- [x] F05a.1 — Parent reads this task and `docs/changes/postgres-bootstrap.md`, mirrors the complete updated task under `odd/forge-foundation/tasks`, then explicitly releases implementation. Do not confuse observation 2374's F04 gate with this gate.
- [x] F05a.2 — Add the narrow local-artifact ignore before creating artifacts. Create a worktree-local venv from bundled Python, resolve exact compatible `psycopg[binary]` test pin through public PyPI, and pin the actual digest resolved once from official `postgres:17-bookworm`. Record versions/digest, never credentials. Missing dependency/image is blocked, not RED.
- [x] F05a.3 — Build runnable real-PostgreSQL tests with two organizations and multiple validated subjects; observe meaningful RED against a basic schema/grants scaffold without RLS. The database must connect and the failing assertions must expose missing behavior, not import/engine/image failures.
- [x] F05a.4 — Implement only identities, organizations, memberships and configuration_revisions. Unique nonempty provider/issuer/subject; unique org/identity and org/membership ID; constrained status; positive composite org/revision key; selected organization config uses a deferrable composite org/revision FK. No product-wide tables or secret payloads.
- [x] F05a.5 — Separate migration owner from nonowner SELECT-only runtime, enable and FORCE RLS, and prove self-identity plus org/validated-identity scope. Organization/configuration require an owned nonarchived membership; org GUC alone never authorizes. Owned suspended membership stays internally readable for F04's later 403; archived and foreign rows stay hidden. Keep policies nonrecursive.
- [x] F05a.6 — Observe GREEN for unfiltered runtime SELECT, missing/partial/empty/malformed context, crossed scope pairs, identity uniqueness and cross-org composite FK denial; inspect runtime role attributes, ownership, memberships and schema grants. Prove DML/DDL denials separately from USING/WITH CHECK via a restricted test-only writer. Parameterized set_config(..., true) must use an outer transaction; actual same-backend PID reuse after commit and rollback must have no prior context/rows. Keep FK diagnostics private; RLS never replaces application authorization or prevents malicious app SQL overwriting GUCs.
- [x] F05a.7 — Existing 31 pure-domain/HTTP tests pass, mandatory real-DB suite passes, compileall/pip check/whitespace pass, exact owned container cleanup is observed. Independent verification and parent spot check are parent-owned. Record every failed/skipped/pending check; parent owns work-unit commit and any candidate review. No source/DB/HTTP adapter completion claim from planning.

## F05a proposed exact checks

Run from this worktree after implementation; these commands are planned, not run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_foundation.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

The first two commands are the existing 13+18 tests, not DB isolation proof.
The PowerShell script is the mandatory real-PostgreSQL suite: create its owned
container, inject ephemeral test connection settings only into its child, run
`.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_postgres_rls.py -v`,
then clean up in finally. Direct DB invocation without explicit harness settings
must fail loudly, never skip. Broad unittest discovery will include the DB suite
and must not be advertised as a dependency-free run after this unit.
No pytest, SQLite or mocked database may substitute for tenant-isolation proof.

## F05a released implementation edit surfaces

The released bounded writer may touch only these exact repository-relative files:

```text
.gitignore
pyproject.toml
migrations/0001_bootstrap.sql
tests/postgres_support.py
tests/test_postgres_rls.py
scripts/test-postgres.ps1
scripts/postgres-image.txt
README.md
docs/changes/postgres-bootstrap.md
odd/tasks/forge-foundation.md
```

New files are authorized only at those listed paths. No F04/domain source edits,
Entra, pooled reader, production migration or other checkout changes belong here.
Parent also explicitly allowed ignored ephemeral `.venv/**` and
`.local/postgres-test/**`; never stage those artifacts. README was added to keep
the explicit DB-free/mandatory DB test commands accurate.

## F05a local harness and delivery boundary

Use `C:/Program Files/Docker/Docker/resources/bin/docker.exe` with explicit
`npipe:////./pipe/docker_engine` and a private empty Docker config beneath ignored
`.local/postgres-test/`; do not read ambient Docker contexts/auth/config. The
explorer observed Desktop 4.41.2 / engine 28.1.1 linux/amd64; this is readiness
history, not a test run. Only the public official PostgreSQL image may be
resolved/pulled once; record its immutable digest in `scripts/postgres-image.txt`.
Default harness uses `--pull=never`; missing image fails with a clear local action.

Each run owns a randomly named disposable container, fresh random credentials,
and dynamic `127.0.0.1`-only port. No host bind mounts, persistent volumes, existing
container/database/volume inspection or reuse. Capture the exact created ID and
remove only that ID in finally (including its own anonymous storage); no prune,
unknown-resource deletion or logging passwords/DSNs. Use only this worktree's
venv from the bundled Python path recorded above, never the global runtime.
Public PyPI resolution is isolated; no ambient credential/session reuse or spend.

Forecast: F05a approximately 900–1400 authored additions plus deletions including
migration (~180–280), test/support (~400–600), harness/pin (~140–220), metadata and
docs/tracking (~180–300). This is an estimate, not a line cap. Security proofs and
readable cleanup take priority over the advisory 400-line budget. Keep tests with
behavior; no code-golf, deleted explanations or artificial file-type split.
F05b is a separate later behavior slice, approximately 450–750 authored lines;
re-estimate from actual adapter scope before writing. Approved local
feature-branch-chain remains the delivery strategy; no PR/push/merge is authorized.
Rollback removes only this unit's migration/harness/tests/test pin and its docs
updates, preserving F04 and the frozen original; no production data exists here.

## F05b deferred acceptance

After F05a proof, derive and authorize a separate exact edit surface for a
synchronous pooled reader implementing F04's injected port. One borrowed
connection and one outer transaction per read; parameterized transaction-local
context; fresh database membership/configuration every request; return existing
immutable domain records and public projection without expanding the contract.
Prove real DB-backed HTTP allowed/foreign/archived/suspended results, live
suspension/configuration rereads, secret-rich operational redaction, worker-thread
execution and pooled connection cleanup. It remains pending and is not enabled by
F05a. No UI, corporate login, production wiring or persistent resources yet.

## Historical preparation status

F05 adds two pending work units with seven F05a acceptance checkpoints. Planning
readback/whitespace is the only applicable check in this turn; implementation,
dependency resolution, image pull, containers, RED/GREEN, commit and native review
have not run. Parent full mirror and explicit release are the next action.
## Historical F05a partial checkpoint — prerequisite/setup failure

Parent released F05a after complete readback/mirror 2374 and added README plus
ignored `.venv/**` and `.local/postgres-test/**` to the exact edit surface. F05b
stays pending. This turn did not commit, review, touch src/forge or alter existing
foundation/API tests or any other checkout.

Observed failure: isolated public PyPI dependency resolution exited 1 while parsing
an index JSON response: `JSONDecodeError: Unterminated string starting at line 1
column 481448 (char 481447)`. Psycopg 3.3.6 metadata was selected, but installation
and exact compatible pin were not established. This is an environment/prerequisite
failure, NOT a meaningful RED test. No blind retry occurred.

The queued official image pull was never reached because the dependency command
threw first. No digest, PostgreSQL version, container, database or cleanup claim
exists. No container/resources were created or inspected. Worktree-local venv and
private empty Docker config exist only beneath ignored authorized directories.

Partial writes: `.gitignore` adds only `.local/postgres-test/`; migration has the
basic four-table/grant scaffold with NO RLS yet; support/test files are unverified
provisional artifacts. Scaffold generator then failed with FileNotFoundError for
`scripts/test-postgres.ps1` because the scripts directory was queued after
prerequisites rather than created first. Harness and image pin therefore do not
exist. This setup failure is NOT RED. Preserve partial state for bounded recovery.
README now separates the existing 13+18 patterns and discloses mandatory DB tests
are incomplete. No install/container/source retry, tests, compileall or functional
proof followed either failure. All F05a checks except parent release remain pending.

Next: parent decides bounded prerequisite recovery; first establish a successful
isolated dependency resolution, explicitly create the authorized scripts directory,
inspect/correct provisional scaffold bytes, and only then execute the one allowed
image pull, real scaffold RED and complete migration GREEN. No source completion,
native approval or multiclient isolation is claimed.
## F05a recovered implementation and writer proof

The parent mirrored the partial checkpoint, then authorized exactly one bounded
no-cache public-PyPI recovery with timeout 30/retries 1 and a 180-second process
limit. Recovery exited 0; imports and pip check passed. The earlier malformed
index response's cause is unproven; success after no-cache is not proof of cache
corruption. Scripts directory was created independently and provisional artifacts
were regenerated/validated before database execution. No broader upgrade occurred.

Versions: psycopg and psycopg-binary 3.3.6 (exact test-extra pin); existing FastAPI
0.142.2, uvicorn 0.54.0, httpx 0.28.1. The original single official image pull exited
0 within its six-minute bound. Actual pin in `scripts/postgres-image.txt`:
`postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652`.
Real server: PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2). No normal-run pull occurs.

- RED: connected real four-table/grants scaffold without RLS; 21 methods, 109
  assertion failures plus one missing-policy error, exit 1. Unfiltered cross-tenant
  exposure and missing policy enforcement caused failures; dependencies and DB
  were ready. Missing policy error is behavior incompleteness, not setup RED.
- Initial GREEN: 21/21 methods, exit 0. Adding real owner-FORCE/invoker and tmpfs
  assertions produced one harness-only metadata failure before the final DB test
  run; that container was removed and exact-ID absence confirmed.
- Final GREEN: 22/22 methods, exit 0, including real USING and WITH CHECK INSERT/
  UPDATE controls, valid FK contexts, role/schema restrictions, nonrecursive scope,
  malformed/missing/partial context, suspended/archived handling and same physical
  backend PID after commit/rollback. All four tables ENABLE/FORCE; helpers invoker.
- Existing regressions: 13/13 foundation plus 18/18 HTTP, exit 0; no source/test
  changes to those modules. Default API remains deny-all; no DB reader is wired.
- `compileall -q src tests` and isolated venv `pip check`: exit 0. Direct DB suite
  without explicit owned harness fails exit 1 with a clear required-harness error;
  it never silently skips. This negative check is not an isolation RED result.
- `git diff --check` and whitespace in all ten authored files: passed. Parent still
  owns independent verification, spot check, full mirror and commit; no native
  review operation or commit ran in this worker.

Harness corrections: Docker create returns/captures the exact ID before start,
so start failure still has an owned cleanup target. PowerShell 5.1's expected
No-such-container stderr must not terminate the cleanup readback; temporary error
handling is restored. Docker tmpfs is in HostConfig.Tmpfs, ordinary Mounts must be
empty. The final harness verifies only the owned container's single rw data tmpfs
and loopback binding. All created containers were removed by exact ID; no lingering
owned resource, persistent volume or host bind mount remains. Ambient Docker/libpq
settings are cleared for the child and restored; passwords/DSNs are not logged.

This is a one-shot migration for a pristine dedicated Forge database/cluster with
reserved role names, not a production/replay migration runner. Schema/global DB
privilege changes must not be applied to an unrelated shared database. Local test
LOGIN/password provisioning and restricted writer grants exist only in fixtures.
F05b pooled reader, DB-backed HTTP, Entra, UI and production remain pending.
Final writer snapshot: 1046 authored additions plus deletions; generated artifacts excluded.
The writer checkpoint above preceded independent verification. Parent subsequently
supplied the independent and spot-check evidence below and authorized local commit.
## F05a independent verification and parent spot check

Parent reported independent verification PASS: 22 real-DB methods plus 13 foundation
and 18 HTTP, pip check and whitespace; roles, RLS, WITH CHECK and constraints were
inspected and proved. Exact owned-container cleanup and absence were confirmed.
Parent then reran `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
.\scripts\test-postgres.ps1`: 22/22, exit 0, PostgreSQL 17.11 and cleanup confirmed.
This is observed functional completion, not native review approval. F05a native
review is pending and parent-owned; F04 remains explicitly declined and the original
review remains stopped. F05b pooled reader/DB-backed HTTP, Entra and UI stay pending.

Parent authorized the coherent ten-file local work-unit commit on
`feat/forge-tenant-storage`, followed by a small documentation evidence commit. No push/PR/
merge or native lifecycle operation is authorized for this worker. Actual commit
identities and counts will be recorded only after Git reports them.
## F05a local commit evidence

Behavior/tests/spec: `e346a1edb21785de4723bff879089124819ec020`
(`feat(storage): enforce PostgreSQL tenant isolation`), observed on
`feat/forge-tenant-storage`. Exactly ten authorized authored files; no ignored venv,
local Docker config, generated credentials or logs staged. Cached whitespace and
sensible secret-literal scan passed; existing Git identity used without override,
Conventional Commit without attribution. Commit hooks made no candidate-file changes.
Numstat: 1049 additions, 17 deletions, 1066 authored lines. This final commit count
supersedes the earlier 1046-line writer snapshot; accepted local feature-branch-chain
continues without code-golf. F05a functional completion includes independent and
parent proof above. F05a native review remains pending, NOT approved; F04's review
is declined and original frozen review stopped. No native operation/push/PR/merge.

This evidence follow-up records the observed behavior hash without a self-referential
future hash. Its identity and final clean checkout proof are returned to the parent.
Next: parent refreshes the full task mirror and performs native candidate assessment;
F05b reader/DB-backed HTTP, Entra and real UI remain pending, not silently included.