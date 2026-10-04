# Forge foundation delivery

## Current decision and next action

**GentleAI verification is disabled by explicit user request: parent observed GLOBALOFF.**
Current work uses available ordinary tests, independent verification and parent spot
checks only: disabled/unmanaged, not native approval. Never assess, start, retry,
request review consent or reactivate review. Historical review records below remain
unchanged; they do not block ordinary authorized development.

F05a is committed and functionally verified. F05b reader/DB-backed HTTP is
**functionally complete**: writer, independent verification and parent spot check
passed. Parent read both preparation docs/full mirror 2374, released F05b and now
authorized the coherent local work-unit commit. Record its actual identity after
Git succeeds, then parent refreshes/readbacks the consolidated-task mirror.

Active checkout: `N:/Proyects/forge/.worktrees/tenant-storage`, branch
`feat/forge-tenant-storage`, HEAD/base for F05b
`f79ad38ceda4588f3da7b6d69bfc79e860a3b070`. Preserve original and API checkouts.

## Authorized outcome and boundaries

Build generic Prometheon Forge MVP incrementally using ODD and small SDD change specs.
Source of truth: PF-00–PF-12 in external `outputs/prometheon-forge/specs/`; retain
OpenYak agent core and OmniRoute routing, Python/FastAPI control plane and PostgreSQL.
Historical 'Promtheon Forge' own-agent-loop memory names a different absent directory,
not implementation evidence for this project. Preserve functioning hotel deployment,
credentials, upstream snapshots and original workspace checkpoint.

No remote operations, ambient credentials/sessions, spending, production migration,
production composition, push, PR, merge, destructive recovery or unrelated checkout
writes. Product root `N:/Proyects/forge` has a stopped original frozen review after
operation_timeout; do not edit/abandon/retry/reset its authority. New worktree does
not approve/close it. Test validators are synthetic only under tests; runtime default
accepts no tokens. No Entra/client UI/product-wide schema or invented capabilities
in the current slice. Workers never invoke or toggle native review.

## Sprint roadmap

| Sprint | Outcome | Exit condition |
|---|---|---|
| S1 | Executable contracts and membership policy | Domain/HTTP denials tested; public bootstrap only; DB/RLS separately proven before isolation claim |
| S2 | Corporate sign-in and client spike | Entra PKCE and Forge token validation integrated; no runtime test identity |
| S3 | Organization administration and branding | Provisioning/revocation and versioned configuration; one client build for two organizations |
| S4 | OmniRoute and budgets | Scoped routing/capabilities, atomic reservations and truthful retry/limit UX |
| S5 | Image tools | Owned idempotent jobs, references/editing and authorized downloads |
| S6 | Skills and audit | Draft backup distinct from reviewed publication; grants/restore and redacted events |
| S7 | Packaging and pilot | Signed Windows updater, restore drill and two-organization pilot checks |

Ordered delivery increments, not calendar commitments. F05b functional checks
passed; local delivery evidence is recorded below. Corporate login, real UI and
production remain unimplemented. Parent owns formal sprint closure and next scope.

## Work units and observed status

- [x] F00 — Read-only delegated exploration mapped specs/upstreams; historical implementation absent locally.
- [x] F01 — Isolated repository, sprint plan and foundation spec; parent full readback/mirror before source. Delegated multi-file docs; included in foundation commit below.
- [x] F02 — Trusted identity/membership authorization and allowlisted bootstrap; delegated behavior, observed RED→GREEN, tests/docs in foundation commit.
- [ ] F03 — Historical independent/parent checks passed, native original review stopped without completion or approved receipt. Preserve historical gap, never restart old authority automatically.
- [x] F04 — Delegated default-deny FastAPI bootstrap transport; seven checkpoints below passed with writer/independent/parent proof and local commit. Native candidate explicitly declined, not approved.
- [x] F05a — Delegated minimal migration, real RLS/role/constraint proof and harness; seven checkpoints passed with real RED→GREEN, independent/parent checks and local commit. No native approval.
- [x] F05b — Delegated synchronous pooled reader and real DB-backed HTTP; functionally complete with writer/independent/parent checks. Local commit authorized; identity recorded after Git succeeds. No broader authentication/UI/schema.

## Delivery strategy, commits and rollback

User-approved **feature-branch-chain, local only**. Keep tests and docs with coherent
behavior; no push/PR/merge authorized. Advisory 400 authored-line heuristic is not a
cap: do not compress code, omit tests, delete explanations or split by file type.
Slices: foundation F01/F02, API F04, PostgreSQL/RLS F05a, pooled reader F05b. No PRs exist.

| Boundary | Identity and purpose | Observed authored lines |
|---|---|---|
| Root | `5aa398bf80c44083a7f9ef7ac1066a33bd4cf9e9` | Baseline |
| F01/F02 | `4281b990f90ba9708e2ec82caf1fdf7b9c390bfb`, feat(auth): authorize organization bootstrap | 434 additions, 0 deletions; 9 files |
| F04 behavior | `34009c465aca6a64e67479d144755f024262a004`, feat(api): expose authorized bootstrap transport | 841 additions +104 deletions =945; 8 files |
| F04 evidence / F05a branch point | `1e2592193e29d87e0becb6d704c2913768ae5f8b` | Documentation evidence |
| F05a behavior | `e346a1edb21785de4723bff879089124819ec020`, feat(storage): enforce PostgreSQL tenant isolation | 1049 additions +17 deletions =1066; 10 files |
| F05a evidence / F05b base | `f79ad38ceda4588f3da7b6d69bfc79e860a3b070` | Documentation evidence |
| F05b | Uncommitted writer candidate | Forecast 550–800; final count in evidence below |

Conventional commits only, no AI attribution/Co-Authored-By. Existing Git identity,
no global configuration changes. Prior commits staged only approved authored files;
ignored venv/config/credentials/logs stayed out; hooks did not mutate candidate bytes.
Historical preliminary snapshots (F04 933, F05a 1046) are superseded by commit counts.

Rollback F04 removes its API/tests/deps/spec without foundation or upstream changes.
Rollback F05a removes only migration/harness/tests/test deps/docs, preserving F04 and
frozen original; no production data. Rollback F05b removes reader/new DB-HTTP/tests
and its support/harness/runtime-dependency/docs changes, preserving F05a migration/RLS
and F04 API/domain. No changed bytes in original/API checkout are authorized.

## Preserved foundation/API proof and review history

F02 Python 3.12.14: 13-method RED/23 NotImplementedError subcase errors, then
13/13 GREEN +compileall. Independent 13 tests/26 adversarial checks (all 16 org-ID
combinations, identity/status denial/secret exclusion); parent 13/13. Git relocation
lost empty metadata directories; parent restored them and existing author identity.

F04 pins: FastAPI 0.142.2/uvicorn 0.54.0/httpx 0.28.1; resolved Starlette 1.7.0/
Pydantic 2.13.5 compatible. Stub RED: 18 methods, 55 assertion failures +1 missing OpenAPI
error, exit 1; GREEN 31/31, compileall/pipcheck/untracked-whitespace pass. Owned localhost
uvicorn: /healthz 200, default bootstrap 401 +Bearer; stopped. Independent/parent pass.
Expected 18 error UUIDs versus 17 unique observed was diagnostic count mismatch, not
behavior error. Starlette warns httpx TestClient deprecated; current pins work only.

Original native review: frozen then operation_timeout, user stopped it. F04 choice 2:
action declined, consent declined_this_candidate, target `da5a138a`, not approval.
F05a review never completed before GLOBALOFF. No approved receipt; no restarting
old authority. Current ordinary checks/delivery disabled/unmanaged. Long details
retained in Engram 2374 (full task), 2437 (F05a recovery), 2442 (F05a finalization), 2448–2449
(F05b planning), specs/Git. Consolidation removes repeated narratives, not stable IDs,
commit hashes/proof/constraints. Unit/API proof never certified auth, DB or real UI.

## F04 acceptance checkpoints (completed historical behavior)

- [x] F04.1 — Parent full task/spec readback, Engram mirror and explicit source-write release observed.
- [x] F04.2 — Isolated exact FastAPI/uvicorn runtime and httpx test pins resolved; imports/pip check passed; no global runtime or pytest change.
- [x] F04.3 — Meaningful importable-stub HTTP RED observed, including auth before org validation, malformed/rejected/spoofed auth and OpenAPI/default-deny.
- [x] F04.4 — Trusted injected sync validator/reader ports, fresh consistent identity/org checks before owned-suspension disclosure, existing domain allowlist unchanged; no runtime fixture identity.
- [x] F04.5 — Public projection, wrong/foreign/inconsistent records, live suspension/config, operational/validation redaction, PF-10 envelopes and OpenAPI/security GREEN.
- [x] F04.6 — 31/31, compileall/pip check/whitespace and owned-loopback smoke passed; independent/parent checks passed. UI N/A; native review declined, not approved.
- [x] F04.7 — Coherent local behavior/tests/spec commit 34009c465aca6a64e67479d144755f024262a004 on feat/forge-api-bootstrap; count/rollback recorded; no push/PR/merge.

## F05a acceptance checkpoints (completed historical behavior)

- [x] F05a.1 — Parent full task/PostgreSQL-spec readback, mirror and explicit F05a release observed; separate from historical F04 gate.
- [x] F05a.2 — Narrow artifact ignores before creation; isolated venv/compatible driver pin and actual official image digest resolved; setup failures not labeled RED.
- [x] F05a.3 — Real connected four-table/grants scaffold RED exposed missing RLS across two orgs/multiple subjects; not import/image/engine failure.
- [x] F05a.4 — Only identities/orgs/memberships/config revisions; full identity triple uniqueness, nonempty/status/positive constraints, org-scoped keys and deferrable composite selected-config FK.
- [x] F05a.5 — Nonowner SELECT-only runtime; ENABLE/FORCE, self/full-org scope, nonrecursive invoker policies; owned suspension internally visible, archived/foreign hidden. No org-only authorization.
- [x] F05a.6 — 22/22 real role/grant/owner/RLS/constraint proof, independent USING/WITH CHECK with FK-valid test writer, malformed/missing context and same-PID commit/rollback cleanup; error details private.
- [x] F05a.7 — 22 DB +13 domain +18 HTTP, compileall/pip check/whitespace, owned cleanup, independent and parent checks passed; local commit recorded. Native approval not claimed.

## F05a PostgreSQL evidence and recovered failures

One-shot migration for pristine dedicated Forge cluster/DB with reserved roles, not
shared/production/upgrade/replay runner. Only four bootstrap tables; composite
selected-config FK deferrable. Nonowner SELECT runtime; FORCE/ENABLE/nonrecursive
invoker RLS. Own suspension readable, archived/foreign hidden. Fixture alone provides
LOGIN/password and restricted writer. RLS never authenticates or prevents compromised
app SQL overwriting GUCs; FK errors private. Application authorization still required.

Initial isolated PyPI: JSONDecodeError Unterminated string (line 1, column 481448,
char 481447), no install/DB/RED. Generator also FileNotFoundError: scripts directory
not created first. Parent authorized one no-cache recovery (timeout 30/retries 1,
180 seconds): driver/binary 3.3.6 installed. JSON cause unproven, not evidence of cache
corruption. Directory created separately; harness regenerated. One authorized image
pull within 6 min pinned actual official digest:
`postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652`.
Actual PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2); normal runs --pull=never.

Connected no-RLS scaffold RED: 21 methods, 109 assertion failures +1 missing-policy
error; GREEN 21/21 then 22/22 including owner-FORCE/invoker and FK-valid USING/WITH CHECK
INSERT/UPDATE. Runtime DML/DDL/role/grants/constraints and same-PID commit/rollback
cleanup pass. Existing 13+18, compileall/pipcheck/whitespace pass; independent 22+13+18
and parent full DB repeat pass. Owned cleanup/absence confirmed.

Harness corrections: ID captured before start for failure cleanup; tmpfs in
HostConfig.Tmpfs, not Mounts (which must be empty); expected post-rm stderr under
PowerShell 5.1 requires restored bounded error handling. Every owned container removed
by exact ID/readback. Setup/diagnostic failures are not fabricated behavioral RED.

## F05b acceptance checkpoints and observed writer status

- [x] F05b.1 — Parent read both full docs, refreshed/readback mirror 2374 and explicitly released these exact paths on 2026-10-04; commit authorization remains parent-owned.
- [x] F05b.2 — Single bounded isolated/no-cache official PyPI install: pool 3.3.3 +existing driver/binary 3.3.6, imports/pip check pass. Both runtime; httpx test-only; no blind retry or unrelated upgrade.
- [x] F05b.3 — Importable-stub real connected RED, then 44/44 GREEN; existing 22 RLS unchanged. One owned fixture initialization per child, reset/test, in-memory credentials, closed test pools; all three DB modules mandatory.
- [x] F05b.4 — Injected managed sync pool, bounded one borrow, idle/autocommit guard before SQL/outer transaction; live restricted-role guard, parameterized local four-GUC context, one fully qualified joined snapshot, exact identity/UUID and frozen mapping. No persistent SET/cache/DSN/pool ownership/extra public keys.
- [x] F05b.5 — Mapping/full-triple/hostile values/crossed/missing/archived denials, own suspended record vs foreign denial, inactive org, fresh membership revocation/config revision; existing API yields owned 403/foreign 404/inactive 404.
- [x] F05b.6 — Real size-one same PID A→B→absence/error clears GUC/rows after commit/rollback; concurrent reads serialize. Admin/super/bypass/owner/inheritance, dirty/non-autocommit, closed/exhausted pool reject. DB HTTP validates default auth/allowlist/worker/redacted 503/recovery; managed pool remains caller-owned.
- [ ] F05b.7 — Writer and independent 44 DB +13 domain +18 HTTP, pip check/whitespace pass; parent 44 DB repeat/cleanup passed. Local commit authorized, awaiting actual hash below; parent final mirror follows. GLOBALOFF disabled/unmanaged, no native review.

## F05b released exact edit surfaces

New authored files only at the three named reader/test paths; other entries already
exist. Parent derives/releases surfaces; stop if any additional path/schema edit is
necessary. No changes to foundation.py, api.py, existing domain/API/RLS tests,
migration, image pin or ignore rules. Ignored artifacts never staged.

```text
src/forge/postgres.py
tests/test_postgres_reader.py
tests/test_postgres_api.py
tests/postgres_support.py
scripts/test-postgres.ps1
pyproject.toml
README.md
docs/changes/postgres-bootstrap.md
odd/tasks/forge-foundation.md
.venv/**
.local/postgres-test/**
```

## Exact available checks and local runtime boundary

From the active checkout with its own venv:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_foundation.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

DB-free counts are 13 foundation +18 API. Harness child discovers
`-m unittest discover -s tests -p test_postgres_*.py -v`: 22 RLS +14 reader +8 DB HTTP.
Direct same discovery without explicit owned harness must fail, never skip; observed
exit 5 with three setup errors, zero tests. Check untracked authored whitespace too.
No pytest/SQLite/mock database substitutes for real tenant-isolation proof. Runtime
F05b proof is actual DB/pool behind HTTP TestClient; real client UI is N/A.

Bundled initial Python path:
`C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
Runtime pins: FastAPI 0.142.2, uvicorn 0.54.0, psycopg/binary 3.3.6, pool 3.3.3;
httpx 0.28.1 test-only. No global Python changes. Driver/pool public resolution uses
--isolated --no-cache-dir, timeout 30/retries 1, one bounded 180-second attempt.

Harness uses absolute Docker binary
`C:/Program Files/Docker/Docker/resources/bin/docker.exe`, explicit local
`npipe:////./pipe/docker_engine`, private empty Docker config under ignored
`.local/postgres-test/`, cached digest and --pull=never. No new image pull authorized.
Fresh owned name/credentials, dynamic 127.0.0.1-only port, tmpfs data only, no host
mount/persistent volume. Capture exact ID, finally rm only that ID and its storage,
then confirm absence; no prune/resource scanning. Ambient Docker/libpq settings are
cleared for the child and restored; no password/DSN logging or credential/session reuse.

## F05b writer evidence — 2026-10-04

- Pool 3.3.3 isolated/no-cache public install succeeded within 180 seconds; imports
  confirm driver/binary 3.3.6, pip check passes. Runtime metadata pins are coherent;
  no unrelated upgrade or image pull.
- Importable stub returning None, real DB ready: clean RED 44 methods, 19 assertion
  failures +6 missing-record errors, exit 1; all 22 RLS tests still pass. First RED
  attempt had 20 failures/109 errors because new ownership-test cleanup lost runtime
  SELECT ACL. Restore SELECT grants after restoring owner; clean RED then precedes
  reader implementation. This was a test-side isolation error, not failing RLS.
- GREEN 44/44 (14 reader +8 DB HTTP +22 RLS), no skips, PostgreSQL 17.11. Size-one
  same PID A→B→absence/error; transaction GUCs and unfiltered rows cleared after
  success/rollback. Actual division-by-zero after GUC setup rolls back; next read
  works on same backend. Two concurrent workers serialize without scope leakage.
- Reader maps existing frozen records, reads exact triple/selected revision, rejects
  dirty transaction/non-autocommit/admin/superuser/bypass/owner/inherited-role and
  closed/exhausted pool; externally managed pool stays open after normal reads.
  Acquisition finite positive <=30 seconds; composition owns connection/statement
  timeouts and pool open/wait/close. No session-persistent SET, cache or ambient DSN.
- DB HTTP: unchanged public allowlist, fresh config/revocation, owned 403/foreign 404,
  inactive organization 404, auth/default-deny before org errors, worker thread and
  private marker redacted 503 after actual SQL failure; following request recovers.
  Test-only probes/validator never imported by runtime. No auth/UI/production claims.
- Existing 13 domain +18 HTTP, compileall, pip check passed. No-harness negative
  genuinely fails exit 5; first shell expectation of exit 1 was incorrect and reported
  failure. Diagnostics confirm required fail-not-skip; not an implementation error.
- Owned fixture migration initializes once per child, credentials shared only in
  memory; fresh data per test, pools closed in cleanup. Every created container
  removed by exact ID and absence confirmed. Final whitespace/count follow below.

Writer checkpoint above preceded independent/parent verification. Their observed
results are recorded below; local commit is now explicitly authorized. No GentleAI
operation or remote action occurred.

Final writer snapshot: 1327 authored additions plus deletions across nine approved
files (generated/ignored artifacts excluded). The 550–800 forecast was exceeded by
full real security/pool/HTTP tests and recovery-doc consolidation; no code/test golf.
Final DB rerun 44/44, exit 0; compileall/pip check/git diff --check exit 0, all nine
files including untracked whitespace clean, protected source/RLS/migration paths
unchanged. Task consolidated from ~38 KB to ~20 KB while preserving 21 checkpoints,
all work-unit IDs, commit hashes, proof/failures, seven sprints and exact commands.

## F05b independent and parent verification

Parent supplied independent PASS: 44 DB +13 foundation +18 HTTP, pip check and
whitespace; no actionable defects. Parent repeated the full real DB harness:
44/44, exit 0, PostgreSQL 17.11 and exact owned-container cleanup/absence confirmed.
This completes functional verification, not native approval. GLOBALOFF remains
explicitly disabled/unmanaged. Parent authorized the exact nine-file local behavior
commit and a small documentation evidence follow-up; no push/PR/merge/source edits.

## Recovery and next step

Engram project `prometheon-forge`; no authoritative session ID, omit session_id.
Parent owns full mirror topic `odd/forge-foundation/tasks`, observation 2374. Read
actual task plus full observation and reconcile on resume; never use newest global
memory as active feature evidence. Current consolidated task supersedes duplicate
historical narratives for readability; earlier full content remains recoverable in
Engram and ignored local backup. F05b memory evidence: 2451 pins, 2452 clean RED,
2453 implementation, 2454 no-harness/ACL lessons. No manufactured approval.

Next: record actual local commit identities, then parent mirrors/readbacks this
full consolidated task before planning the next bounded feature.
After observed closure, plan S2 corporate sign-in/client spike against product specs;
do not silently expand F05b. Preserve all current state if any required check blocks.
