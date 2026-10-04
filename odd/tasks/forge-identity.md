# Forge identity delivery

## Current outcome and release gate

F07a functional closure passed: writer142, independent142 applicable checks and
parent73 DB spot. Local coherent behavior/test/docs commit8183b8d completed;
actual identity/stats are recorded below. No onboarding/login wiring.
Source release followed parent full mirror2468/exact readback.
F06 completed: writer 113, independent/P2 retest and parent spot passed; actual
commits and historical proof remain below. F07a starting baseline was4ab2d40.
No live tenant enrollment, desktop sign-in, UI or runtime composition is enabled.
Gentle AI review GLOBALOFF: disabled/unmanaged, no calls or consent prompt.

## Objective, problem and inherited evidence

Provide the missing trusted token validator without weakening default-deny API
or organization/membership checks. PF-02/PF-10/PF-12 constrain identity, HTTP/data
contracts and proof. Completed F06 SDD: docs/changes/entra-token-validation.md.
Current F07a SDD: docs/changes/entra-identity-binding.md.
Closed foundation remains in odd/tasks/forge-foundation.md; recovery mirror topic
odd/forge-foundation/tasks, observation 2374. F05b behavior commit:
279905eae2113c40749d5ac6fa9358cdce1b85d8. Historical F06 baseline:
f44032ea175c9197eb8cdca1f28348ce4fc6bd44. Recorded independent/parent proof:
44 PostgreSQL +13 foundation +18 HTTP tests, exact owned-container cleanup.
This is historical evidence, not a new run or proof of Entra.

## Work units

- [x] **F06 — Backend Entra v2 validator (completed).**
  Explicit trusted config, immutable verified principal, bounded discovery/JWKS,
  real RS256, offline cryptographic/HTTP tests and docs.
  Route: delegated direct; preparation reading and multiple non-trivial files.
  Closure: writer/independent/parent proof passed; local coherent commit authorized.
- [x] **F07a — Bind existing Entra identities (functional closure complete).**
  Add explicit immutable tid/oid metadata, restricted internal binder and Entra-only
  reader gating. Accepted design2485/source release; writer/independent142 and
  parent73 passed. Coherent local commit8183b8d completed; actual evidence below.
  Route: delegated direct; migration, adapter and real-DB tests are non-trivial.
- [ ] **F07b — Creation, invitations and provisioning (future; not released).**
  Refine object/invitation confirmation, identity creation and idempotent outbox
  separately. No automatic email matching, membership/admin assignment or signup.
- [ ] **F08 — Configured runtime composition and readiness UI (future; not released).**
  Refine trusted deployment inputs and truthful readiness independently of liveness.
  Default application remains deny-all until deliberately composed.
- [ ] **F09 — Desktop PKCE, protected storage and enrollment spike
  (future; not released).** Refine platform/client scope; obtain explicit account,
  tenant, application-registration and staging authorization before live work.
  Public client has no secret; no plaintext corporate token files.

Checkpoints record progress only, never authorize unreleased implementation.

## F06 acceptance checkpoints (10)

- [x] A1: Nonempty bounded tenant/client/scope allowlists and API audience GUID;
  trusted explicit configuration rejects malformed values at construction.
- [x] A2: Library RS256 with configured algorithm only; malformed, tampered,
  wrong-key, unsupported-algorithm and oversize tokens reject.
- [x] A3: Exact issuer/audience/allowed tid, ver=2.0, authorized azp and complete
  exact space-delimited delegated scopes; Graph, ID and app-only tokens reject.
- [x] A4: Strict nonempty sub and GUID oid; finite typed exp/nbf/iat, valid chronology
  and bounded skew; no missing values or string/boolean coercion.
- [x] A5: Frozen principal retains actual sub, tid, oid separately; output is entra
  + exact validated tenant-v2 issuer + canonical verified oid GUID. Same tenant/oid
  with different sub intentionally has the same identity; different tenants remain
  distinct. Guest idp/email never substitute or merge.
- [x] A6: Configured tenant-only discovery, exact metadata issuer, official HTTPS
  tenant/common v2 keys URLs only. No redirects, credentials, fragments, unexpected
  ports/query/host/path or token jku/x5u fetch authority.
- [x] A7: Finite timeout/body/key-count/tenant limits; safe public RSA signing keys
  with matching issuer, including tenant-template substitution; no private keys.
- [x] A8: Per-tenant finite TTL, bounded synchronized fetch concurrency, rotation
  refresh and unknown-kid cooldown/backoff EVEN AFTER failure. No forever per-key
  cache or accepting expired cache material during outage.
- [x] A9: Invalid token returns None; discovery/JWKS failure raises typed redacted
  operational error. No logs/token/PII/private-key/raw-network diagnostics.
- [x] A10: Actual adapter through unchanged create_app proves 401 vs 503 and zero
  reader calls for rejected tokens; valid identity still uses membership checks.
  Focused tests, inherited 75-test regression, compile/dependency/whitespace checks,
  independent verification and parent spot check have observed results.

## Historical F06 released edit surfaces

- src/forge/entra.py
- tests/test_entra.py
- pyproject.toml
- README.md
- docs/changes/entra-token-validation.md
- odd/tasks/forge-identity.md
- .venv/**
- .local/postgres-test/**

Ignored surfaces mean isolated dependency runtime and existing disposable harness
output only. One adapter module and one test module suffice; no helper path requested.
Protected: API/domain/PostgreSQL source, migrations, existing tests/harness, upstream,
closed foundation task and product specs. If another path becomes necessary, stop
and return the exact derived path before writing.

## Historical F06 test-first policy and checks

Unittest; ephemeral RSA keys generated inside tests, synthetic public JWKS and fake
bounded HTTP transport. No private key file is written or committed. First verify
compatible exact PyJWT/cryptography pins and install into existing local venv; then
observe behavioral assertion RED against an importable minimal adapter before GREEN.
Import failure alone is not behavioral RED. Refactor while GREEN.

Commands from N:/Proyects/forge/.worktrees/tenant-storage after release:

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

Public isolated no-cache dependency acquisition only after compatible pins verified;
no ambient index/keyring/credentials, unrelated upgrades or retry loops. Installation
wall-time bound: 180 seconds. HTTP integration stays in test_entra with real RSA/JWKS
validator and in-memory reader doubles; no network account or runtime composition.
PostgreSQL uses existing pinned local image/named pipe, unique owned disposable
container and exact-ID cleanup; no pull, ambient credentials or existing DB.
Missing prerequisites fail, never silently skip. Independent verifier reruns
focused/full applicable checks; parent repeats one reported command.
Baseline known warning: TestClient/httpx deprecation, not a failed test.

## Delivery, forecast and rollback

User-approved local-only feature-branch-chain on existing nondefault
feat/forge-tenant-storage. No default-branch mutation, push, PR, merge or remote work.
F06 forecast: 700-1100 authored additions/deletions, generated files excluded.
Full security/rotation/concurrency tests can exceed 400; preserve clarity/tests/docs,
never code-golf or omit evidence. F07a forecast appears below; F07b-F09 remain unscoped.
Original corrected candidate snapshot: 1480 authored additions/deletions.
Final commit line count and identity are observed below, generated files excluded.
One coherent F06 behavior/test/docs commit is the rollback boundary; no migration
or stored identity change. Conventional Commit, no AI attribution.
Functional and independent proof remain required with GLOBALOFF; no native review.

## F06 writer evidence and chosen numeric policy

Source release: parent full mirror observation 2468/readback confirmed.
PyJWT[crypto]==2.15.1 + cryptography==50.0.2 public isolated dry-run/install succeeded
on Python 3.12.14 within 180 seconds; cffi 2.1.1 / pycparser 3.0 transitively resolved.
No project build metadata generated. Exact approved adjusted installation:

    ./.venv/Scripts/python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir --no-input --keyring-provider disabled --timeout 15 --retries 1 "PyJWT[crypto]==2.15.1" "cryptography==50.0.2"

Observed RED: 24 methods, 62 assertion failures, no errors against importable None
skeleton. First fixture attempt: 62 failures +2 errors because library encoder guards
rejected malformed header/issuer before reaching validator. Fixture now signs explicit
JSON with cryptography RSA, ephemeral private keys remain exclusively in memory.
Initial implementation 23/24: TTL test advanced 3600s while retaining expired token;
refreshing that test token isolates rotation and produced 24/24 GREEN.
Official common-JWKS mixed consumer/template issuer regression observed RED
(one operational error), then GREEN after key-level scope filtering. Expanded
pre-independent focused proof: 36/36, including bounded transport/TLS/redirects/size/deadline,
same/different tenant identity, guests, full allowlists, weak RSA, concurrency,
rotation/failure cooldown, time after discovery and actual API 401/503/403/404.

Chosen defaults (configurable only within enforced finite bounds):
16 tenants /32 clients /16 scopes; scope identifier <=128; sub <=1024; scp <=4096.
JWT ASCII <=16384 bytes (range 1024-65536); kid <=128 (1-256); each response <=262144
bytes (1024-1048576); <=64 keys (1-128); RSA public 2048-4096 bits/exponent 65537.
Tenant TTL 3600s (1-86400); refresh cooldown 60s (1-3600); fetch/lock/slot timeout 3s
(0.1-10); concurrent fetch slots 2 (1-4); clock skew 60s (0-300).
Read deadline 2x socket timeout checked before/after bounded read1; DNS follows OS
scheduling, not a claimed end-to-end request SLA. NumericDate nonboolean finite
0..2^53 with chronology/skew rechecked after signature. Valid unexpired cached keys
can still work after a refresh failure; expired keys never do. Cooldown starts again
at attempt completion, including malformed metadata or capacity/transport failure.

## Independent P2 NumericDate correction

Independent verifier found exp/nbf/iat=10**400 reaches math.isfinite before range
validation: implicit integer-to-float conversion raises OverflowError. An invalid
.AAA signature therefore produced redacted 503 instead of required 401, with zero
fetch/reader calls. This was input-rejection classification, NOT an auth bypass;
parent reported all other independent checks passed.
Added direct-validator and actual create_app regressions for each of the three claims:
observed RED 38 methods /6 assertion failures, then GREEN 38/38.
Correction checks exact int/float type and finite policy range BEFORE math.isfinite;
same helper protects configured numeric limits and injected wall clock.
Post-correction full rerun: 38 Entra +13 domain +18 HTTP +44 PostgreSQL, no skips,
all exit 0. PostgreSQL17.11 owned container removed and exact-ID absence confirmed.
compileall/pip check/git diff --check exit 0; warning unchanged.

## Final functional closure

- Writer after P2 correction: 38 Entra +13 domain +18 HTTP +44 PostgreSQL
  =113 tests, no skips, all exit 0.
- Independent original proof: 111 tests (36 Entra +75 unchanged regressions), plus
  compiled/dependency/whitespace/protected-surface checks; found one concrete P2.
- Independent retest closed P2: 38 tests pass, plus six adversarial exp/nbf/iat
  cases using +10**400 and -10**400. Direct None and API401; fetch=reader=0;
  protected source unchanged. No authentication bypass was observed.
- Parent spot check: 38 Entra tests, exit 0. Functional verification complete,
  not native approval. Gentle AI GLOBALOFF remains disabled/unmanaged.
- PostgreSQL17.11 owned disposable container removed; exact-ID absence confirmed.
  compileall/pip check/git diff --check and six-file UTF8/noBOM/whitespace/
  no-persisted-private-key readback passed. Existing TestClient/httpx warning stays.
- README and neutral-Spanish SDD match adapter/default-deny/runtime limitations.

## F06 local delivery evidence

Observed behavior commit: 279fef10e248d25e72bb943ff08348600d4b6231
(feat(auth): validate Entra access tokens), existing feat/forge-tenant-storage branch.
Exactly six approved files:1488 additions +2 deletions =1490 authored lines.
No source bytes changed during final documentation closure or commit; source/test/
manifest blobs match the independent accepted candidate. Protected surfaces unchanged.
No active commit hooks; clean checkout observed immediately after behavior commit.
Git emitted existing automatic-identity notice; no config change/amend or AI attribution.
This small task-only follow-up records the actual hash without future self-reference.
No push, PR, merge, remote/production/account action or Gentle AI operation.

## F07a plan checkpoint and source release gate

Current unit: **F07a — Bind existing Entra identities**; source released by parent.
Writer/independent/parent closure and local commit are observed below.
Explorer handoff 2483 and parent acceptance 2485 were read with the full
task 2468/file. Baseline 4ab2d40c8c3a1e80cbb0106c917804fed949e881 was clean.
Current-unit neutral-Spanish SDD: docs/changes/entra-identity-binding.md.

Route: delegated direct; additive migration, trusted internal adapter, reader
hardening and real-DB tests cross multiple non-trivial files. No unresolved product
choice blocks this bounded design. VerifiedPrincipal is a trusted internal port,
not proof of authentication merely by constructing its dataclass; no public
endpoint, login wiring or runtime composition is authorized.

### F07a acceptance checkpoints (10; completed)

- [x] B1: Additive 0002 preserves0001 and existing identity/member UUIDs; nullable
  UUID tid/oid pair has explicit both-null/both-present CHECK branches.
- [x] B2: Present pair requires entra provider, exact tenant-v2 issuer and canonical
  oid subject; unique pair and invoker write-once guard prevent clearing/rebinding
  or changing canonical identity fields after binding. No email/sub/idp fallback.
- [x] B3: Internal bind_existing(existing identity UUID, VerifiedPrincipal) accepts
  only an existing exact canonical match; immutable outcomes and redacted typed
  errors. No insert, relink, signup, membership/admin or invitation mutation.
- [x] B4: Repeated/concurrent identical bindings are idempotent; conflicts never
  overwrite existing metadata. Same oid in different tenants remains distinct;
  guests retain resource-tenant objects.
- [x] B5: Separate forge_identity_binder NOLOGIN role/pool contract permits only
  identities SELECT and UPDATE of pair columns; no role inheritance/membership,
  ownership, administrative powers or unrelated table mutation.
- [x] B6: Binder enforces effective role/session, privileges, schema/RLS and idle
  autocommit safeguards; explicit transaction and self-only RLS use local identity/
  verified-principal context, not fabricated organizational membership. External
  pool ownership, finite acquisition and success/failure cleanup are preserved.
- [x] B7: Reader requires coherent bound metadata only for Entra; generic identities
  and existing org/member/configuration policy remain intact. Runtime SELECT-only
  guard detects column-level mutation grants as well as table grants.
- [x] B8: Real-DB reader/API tests deny before binding and still enforce membership
  after binding. Mutation privileges, constraints, unsafe pools/roles, concurrency,
  cleanup and no-automatic-membership have behavioral coverage.
- [x] B9: Fixture applies explicit ordered 0001/0002 and explicit identity INSERT
  columns; random disposable binder login only. Fresh installation, populated
  upgrade and migration transaction rollback preserve existing rows/RLS.
- [x] B10: Observed meaningful PostgreSQL RED → GREEN, all baseline 113 plus new
  tests, compileall/pipcheck/diffcheck, independent verification and parent spot
  precede any authorized coherent work-unit commit.

### Exact F07a surfaces

Exact surfaces released by the parent after full updated mirror/readback:

- migrations/0002_entra_identity_binding.sql
- src/forge/identity_store.py
- src/forge/postgres.py
- tests/test_postgres_identity.py
- tests/postgres_support.py
- tests/test_postgres_reader.py
- tests/test_postgres_api.py
- tests/test_postgres_rls.py
- README.md
- odd/tasks/forge-identity.md
- docs/changes/entra-identity-binding.md
- .local/postgres-test/**

No new dependencies, harness-script edits, migration0001 edits, Entra/API/domain
source changes or extra helper files. The ignored path is owned disposable harness
output only. Stop for parent scope input if another exact path becomes necessary.

### Required verification and delivery

Commands from N:/Proyects/forge/.worktrees/tenant-storage (released):

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

The existing harness discovers test_postgres_*.py, including the new binding tests.
First behavioral RED must demonstrate the absent binding/reader safeguard against
real PostgreSQL, not missing-module errors. Then GREEN/refactor and full regressions.
Baseline 113 =38 Entra+13 domain+18 HTTP+44 PostgreSQL; observed final
count 142 includes 29 new methods. Owned pinned cached image/disposable container
only; no pull or existing
DB. Record actual command results, counts, failures/skips and exact-ID cleanup.

F07a forecast 1000–1600 authored additions/deletions including complete real-DB
tests/docs. Local feature-branch-chain remains approved; 400 is advisory only.
One coherent migration/binder/reader/test/docs work unit is the proposed boundary;
no artificial file-type split or code-golf. Migration failure rollback is tested
transactionally; destructive downgrade of persisted binding data is not authorized.
Parent independent verification+spot check precede a separately authorized local
Conventional Commit. Source/tests and owned-container proof are observed below;
no dependency installation. Independent/parent closure and local commit completed;
GLOBALOFF means disabled/unmanaged, never native approval.

## F07a original writer evidence (141 before proof extension)

Parent source release followed the full updated mirror2468 and exact normalized
readback (19755 characters). Baseline4ab2d40 remains HEAD; no commit yet.
Writer implemented only the exact released surfaces;0001,domain,API,F06 source/
tests,manifest,harness script,closed foundation and product specs are unchanged.

Meaningful real PostgreSQL RED before source implementation:46 methods /4 assertion
failures, no errors. Existing reader returned unbound Entra records and failed to
reject column-only UPDATE/INSERT/REFERENCES grants; all inherited44 tests passed.
Initial GREEN46/46; expanded binding/migration proof67/67; final DB72/72.
No additional intermediate failures or skipped prerequisites occurred.

Final exact required command results:
- Existing powershell scripts/test-postgres.ps1:72 tests, exit0, no skips.
  PostgreSQL17.11;24 binding/migration+17 reader+9 DB HTTP+22 RLS.
  Exact owned-container removal/absence readback succeeded on every RED/GREEN run.
- test_entra.py:38, exit0; test_foundation.py:13, exit0; test_api.py:18, exit0.
- compileall -q src tests:exit0; pip check:exit0/no broken requirements;
  git diff --check:exit0. Existing TestClient/httpx warning remains unsilenced.
Total141 = baseline113+28 new methods. Tests prove no automatic identity/membership
creation, privileged write-once rejection, cross-tenant separation, repeated/concurrent
binding, role/session/ownership/effective ACL/RLS safeguards, bounded lock/pool failure,
post-UPDATE rollback and clean same-backend context/timeout restoration.

Migration probes execute exact0001 and0002 scripts in three separately named owned
ephemeral databases before fixture role initialization: fresh, populated generic+
Entra+membership upgrade, and populated transaction rollback. Rollback probe changes
only final COMMIT to ROLLBACK in memory, executes all DDL/grants, and verifies no new
columns/binder role while previous rows and four ENABLE+FORCE RLS tables persist.
Successful upgrade preserves existing rows/UUIDs with null metadata, not backfill.
Each probe removes only its captured random DB and its case-created reserved roles.
Fixture then applies explicit ordered0001/0002 in the owned test DB. No existing DB,
script change, dependency acquisition, deployment runner or downgrade is involved.

Chosen finite policy: migration lock2s/statement10s; binder acquisition1s override
(0,30], local lock1s/statement5s, fixture connect2s/statement5s and pool min/max1,
waiting4/reconnect1s/open5s. Test separate pools prove real row-lock idempotency.
Limits reset after transaction; they are not an end-to-end deployment SLA.

Original public identity policy is scoped to runtime/migrator so organization GUCs
cannot broaden binder RLS; test-only writer is explicitly included by the fixture.
Binder self context contains existing UUID, verified issuer/tid/oid only; never
raw JWTsub/email. The principal dataclass remains a trusted internal port, not an
authentication proof. No endpoint or login wiring was added.

At the original writer checkpoint B1-B9 were observed; B10 awaited independent
verification and parent spot. Final closure is recorded below. README/Spanish SDD describe the exact
internal boundary and deployment/migration-runner gap. Parent owns refreshed full
task mirror; no native approval or remote/account activity.

## F07a durable failed-migration proof extension

Independent required checks passed the original141 candidate with no concrete
defect; parent spot72 DB passed on PostgreSQL17.11 (13.668s), exact-ID cleanup.
Independent optional combined in-memory probe was blocked by a15s readiness wait
before SQL; it supplied no verdict. No unknown wrapper was repeated.

Parent requested durable failure proof within B9: an explicit ROLLBACK alone is
not evidence of a mid-migration failure. Added one new test method,
test_failed_migration_rolls_back_ddl_policies_role_and_existing_data. The fourth
separately owned migration case executes the exact0002 statements with an in-memory
SELECT1/0 inserted before original COMMIT. It observes DivisionByZero/SQLSTATE22012,
INERROR, then explicit ROLLBACK/IDLE. Readback checks no binding columns or binder
role, unchanged policies/functions, existing generic/Entra/member rows and four
ENABLE+FORCE RLS tables. The original explicit rollback case remains distinct.

Expanded existing runtime and binder guard regressions with REFERENCES granted
to both pair columns; no table REFERENCES grant, both guards reject. Existing
durable self-only/malformed/partial/foreign/org-spoofing binder-RLS tests already
cover that optional premise. Production migration/adapter/reader bytes are unchanged.

Writer follow-up using only the existing harness:73 DB (25 binding/migration+
17 reader+9 DB HTTP+22 RLS), PostgreSQL17.11,14.420s, exit0/no skips and exact-ID
cleanup. Unchanged38 Entra+13 domain+18 HTTP passed; total142, previous141 retained.
compileall/pipcheck/diffcheck exit0. This tests-only proof improvement needs no new
production behavior RED; the deterministic SQL failure itself is asserted, not
misreported as an unexpected test failure. That writer checkpoint awaited focused
independent/new-test parent spot; both are now observed in final closure below.

## F07a final functional closure and local delivery

Writer142 =73 DB+38 Entra+13 domain+18 HTTP, all required checks exit0/no skips.
Independent original141 passed with no concrete defect; durable focused73 DB
plus previous69 offline =142 applicable checks passed. Parent latest73 DB spot
passed on PostgreSQL17.11 in13.492s; exact-ID owned-container cleanup confirmed.
All B1-B10 acceptance criteria are observed. Functional proof is not native
approval: GLOBALOFF remains disabled/unmanaged, without Gentle operations.

Optional independent pre-SQL readiness block is retained above as historical
unavailable proof, not PASS. New durable tests independently prove failure rollback
and paired REFERENCES guards; no production correction was needed. Behavior,
tests and docs form one coherent local-only work unit on feat/forge-tenant-storage.
Parent authorized feat(identity): persist verified Entra bindings for exactly the
eleven authored surfaces. Actual commit identity/stats are recorded below; no
remote action, F07b source, deployment runner or live enrollment.

## F07a observed local delivery evidence

Behavior commit:8183b8dd00503dda9e504f8c7a473b9ed936b0d9
(feat(identity): persist verified Entra bindings), existing local feature branch.
Exactly eleven approved files:1337 additions+29 deletions =1366 authored lines;
generated/ignored outputs excluded. Eight behavior/migration/test blobs match the
independent verified candidate before staging and after commit. No mutating hooks;
clean checkout observed immediately after behavior commit. Protected surfaces
remain unchanged against starting4ab2d40. No remote action or AI attribution.
Git emitted the existing automatic-identity notice; no config edit/amend.
This small task-only follow-up records the actual behavior hash/stats; parent owns
the final full task mirror/readback. F07b-F09 remain pending, not released.

## Recovery and next step

Engram project prometheon-forge; no authoritative session ID, omit session_id.
Parent owns final full mirror topic odd/forge-identity/tasks and readback.
Parent owns refreshed final full mirror/readback after local delivery evidence.
F07a functional closure and local work-unit commit completed; actual Git
hash/stats are recorded above. F07b remains unreleased.
The eleven authored paths match released scope; ignored local logs are not delivery.
F07b creation/invitations/provisioning remains future and requires separate scoping.
Explicit persistent tid/oid linkage is required before live enrollment.
F08 runtime composition/readiness UI and F09 desktop PKCE/protected storage/live
enrollment stay pending. Preserve closed foundation proof and current branch chain.
