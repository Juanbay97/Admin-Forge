# Forge foundation delivery

## Current decision and next action

Continue the next local work unit in the isolated checkout
`N:/Proyects/forge/.worktrees/api-bootstrap`, branch `feat/forge-api-bootstrap`.
This document is reconciled against Git and source evidence on 2026-10-03.
F01/F02 are implemented and committed; F03 has historical functional proof but no
completed native review. F04 transport is implemented, functionally verified and locally committed; not integrated.
Parent readback/full mirror released the source-write gate; independent verification
and parent spot check passed; local behavior commit evidence is recorded below.

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
- [ ] F05 — PostgreSQL schema and real two-organization RLS proof. Separate pending unit; derive exact scope/tests after F04. No database, SQL, Entra integration or production work is authorized by this F04 task.

## F04 acceptance checkpoints

- [x] F04.1 — Parent reads this document and `docs/changes/api-bootstrap.md`, mirrors the full task document under `odd/forge-foundation/tasks`, and explicitly releases the source-write gate.
- [x] F04.2 — Resolve compatible exact FastAPI/uvicorn runtime and httpx test pins in a worktree-local virtual environment. Do not alter bundled Codex Python or add pytest. Record dependency/runner evidence; unavailable dependencies are a blocker, not RED.
- [x] F04.3 — Observe meaningful failing HTTP tests against an importable stub before implementation. The HTTP contract covers auth before organization lookup, missing/malformed/rejected auth, spoofed identity headers/cookies, UUID query validation and default-deny configuration.
- [x] F04.4 — Implement injected trusted token-validator and scoped bootstrap-reader ports with production default accepting no bearer token. Read fresh data per request, verify identity and all organization IDs before revealing owned suspended membership, and reuse the existing domain allowlist unchanged. No runtime fixtures or fake-auth environment switch.
- [x] F04.5 — Observe passing HTTP tests for allowed projection/no secrets, missing/inconsistent/wrong-identity and cross-organization records (including foreign suspended membership), live suspension reread, secret-rich provider exceptions, PF-10 envelopes and OpenAPI security/response contracts. Health is process-only liveness; capabilities beyond the domain subset remain deferred.
- [x] F04.6 — Entire unittest suite GREEN, compileall, pip check, whitespace check and loopback-only uvicorn smoke are observed and recorded. UI: N/A (no screen). Writer, independent and parent checks passed. Native review remains pending, not approved.
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
Parent readback/full mirror of preparation completed (observation 2374); source gate
released. Mirror refresh for implementation evidence is pending and parent-owned.
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
remain unimplemented. Native review remains pending, not approved.

## F04 local commit evidence

Behavior/tests/spec: `34009c465aca6a64e67479d144755f024262a004`
(`feat(api): expose authorized bootstrap transport`), observed on
`feat/forge-api-bootstrap`. Exactly eight approved files staged; `.venv` excluded.
Cached whitespace check passed. Numstat: 841 additions, 104 deletions, 945 authored
lines; this final precommit count supersedes the earlier 933-line writer snapshot.
No push, PR, merge or native review action occurred. Native review is pending, NOT
approved; original F03 remains incomplete and DB/RLS/Entra/UI are still pending.

This documentation-only evidence follow-up records the observed behavior hash,
without trying to store its own future hash. Its identity and final clean checkout
proof are supplied in the worker handoff for the parent recovery mirror.
Next: parent refreshes the full task mirror and decides the next bounded unit;
no unfinished F04 functional check is hidden by the commit.
