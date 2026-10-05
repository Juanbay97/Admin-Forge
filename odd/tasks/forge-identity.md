# Forge identity delivery

## Current outcome and gate

F06/F07a are locally committed. **F08a local operational-shell delivery is closed
with explicit UI evidence limits.** Writer184, independent original181 plus focused
28runtime+18API correction retest (138 other applicable proof), corrected wheel,
and parent28 spot passed. Parent accepted available browser functional proof, not
full network/screen-reader/loading certification. C10b remains follow-up evidence;
F07b/F09 remain unfinished. Local behavior commit211b501383ea048d4691d5b591acce3b6ddefbb0
completed; identity and exact stats recorded below.
Parent full mirror2468/readback preceded source; refreshed mirror is parent-owned.
No server/browser launched by this writer. Exact released scope is below.
Gentle GLOBALOFF: disabled/unmanaged, no calls, consent or native approval.
No live enrollment, login, onboarding, administrative client or deployment is enabled.

## Objective and inherited evidence

Build trustworthy identity foundations, then deliberately compose the existing
validator/reader with a truthful read-only status UI. Preserve default-deny API,
organization/membership checks and separation of authentication from enrollment.
PF-02/PF-10/PF-12 constrain identity/contracts/proof; PF-03/PF-09/PF-11 inform status,
configuration and UI without authorizing administration. English technical/UI
artifacts; current SDD docs/changes/runtime-status.md is neutral Spanish.
Completed SDDs: docs/changes/entra-token-validation.md and
docs/changes/entra-identity-binding.md.

Closed foundation: odd/tasks/forge-foundation.md, mirror 2374/topic
odd/forge-foundation/tasks. F05b behavior 279905eae2113c40749d5ac6fa9358cdce1b85d8;
historical 44 PostgreSQL+13 foundation+18 HTTP tests and exact owned-container cleanup.
Historical F06 baseline f44032ea175c9197eb8cdca1f28348ce4fc6bd44.
Historical evidence is not a new run or live Entra proof.

## Work units and delivery strategy

- [x] **F06 — Backend Entra v2 validator.** Explicit trusted configuration,
  verified principal, bounded discovery/JWKS and real RS256. Writer 113,
  independent P2 correction/retest and parent 38 passed; commits below.
  Route: delegated direct, preparation reading/multiple non-trivial files.
- [x] **F07a — Bind existing Entra identities.** Immutable persistent tid/oid,
  restricted internal binder and Entra-only reader gating. Writer/independent 142
  applicable checks, parent 73 DB passed; commits below. No login wiring.
  Route: delegated direct, migration/adapter/real-DB tests.
- [x] **F08a — Explicit runtime composition and truthful local status UI.**
  Compose existing Entra/reader ports; lifecycle, restricted-role/schema readiness,
  real local HTML/CSS/JS status only. Corrected writer184 and rebuilt wheel passed;
  independent focused retest and parent28 passed; local delivery accepted with C10b evidence limits.
  Route: delegated direct, lifecycle/security/UI and tests cross non-trivial files.
- [ ] **F07b — Creation, invitations and provisioning (future; not released).**
  Child F07b1 authorization read-model plan: [forge-administration](forge-administration.md);
  completed internal read model, writer/independent211 and parent108DB spot passed; local commit acf7a9e1415e91290ad9829b789669574b6675e0. F07b remains unfinished.
  Scope object/invitation confirmation, creation and idempotent outbox separately.
  No email matching, automatic membership/admin assignment or tenant signup.
- [ ] **F08 — Remaining deployment/runtime readiness work (future).**
  Production connection/TLS profile, migration runner and deployment refinement
  remain separate; F08a does not claim production or live identity readiness.
- [ ] **F09 — Desktop PKCE, protected storage and live enrollment spike (future).**
  Requires separate platform/client/account/tenant/app-registration/staging scope.
  Public client has no secret; no plaintext corporate token files.

User-approved local feature-branch-chain on feat/forge-tenant-storage; no default
branch mutation, remote, push, PR or merge. One coherent behavior/test/docs commit
per released unit, Conventional Commits without AI attribution. Parent independent
verification plus spot precede separately authorized commit. About 400 authored
changed lines is advisory only: preserve full clear tests/docs, no code-golf or
artificial file-type splits. F06 forecast 700–1100, candidate 1480 / final 1490;
F07a forecast 1000–1600, initial snapshot 1249 / final 1366. F08a forecast 1800–2600
additions+deletions including task consolidation/UI/full tests/docs, generated
outputs excluded; estimate, not observed. Proposed boundary is coherent runtime/
status behavior with tests/docs. Checkboxes track evidence, not implementation authority.

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

## F06 retained proof and limits

Six authored surfaces were src/forge/entra.py, tests/test_entra.py, pyproject.toml,
README.md, docs/changes/entra-token-validation.md and this task; ignored .venv/**
and .local/postgres-test/** only. API/domain/PostgreSQL/migrations/existing tests/
harness/closed foundation/product specs protected. Parent mirror 2468/readback
preceded source. HTTP crypto tests remain in test_entra, synthetic public JWKS,
ephemeral RSA private keys exclusively in memory; no key file or network account.

Python 3.12.14; public isolated PyJWT[crypto] 2.15.1 + cryptography 50.0.2 dry-run/install
within 180s; transitive cffi 2.1.1 / pycparser 3.0. Direct install avoided unauthorized
project build metadata; exact approved historical command:
    ./.venv/Scripts/python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir --no-input --keyring-provider disabled --timeout 15 --retries 1 "PyJWT[crypto]==2.15.1" "cryptography==50.0.2"

Behavioral RED: 24 methods / 62 assertion failures/no errors against importable None
skeleton. Earlier fixture 62 failures+2 errors: PyJWT encoder rejected malformed
header/issuer before validator; explicit JSON cryptography signing fixed fixture.
Initial 23/24: TTL advanced 3600s with expired token; renewed token isolates rotation,
then 24 GREEN. Common-JWKS mixed consumer/template issuer regression RED with one
operational error; per-key scope filtering fixed it. Expanded 36 GREEN proves
transport/TLS/redirect/size/deadline, identity/guests, allowlists/weak RSA/concurrency,
rotation/failure cooldown/time after discovery and actual API 401/503/403/404.

Independent P2: exp/nbf/iat=10**400 reached math.isfinite before range check;
implicit float conversion OverflowError gave API 503 rather than 401 for invalid
.AAA signature, fetch=reader=0. Input classification defect, NOT authentication
bypass; other independent checks passed. Added three-claim direct/API regressions:
RED 38 methods / 6 assertion failures, then GREEN 38 by exact int/float type and range
before math.isfinite; helper also protects numeric configuration/clock.
Writer 113=38 Entra+13 domain+18 HTTP+44 DB, no skips / exit 0.
Independent original 111=36+75 regressions found P2; retest 38 plus six manual
+/-10**400 cases direct None/API 401/fetch/reader 0 closed it. Parent 38 exit 0.
compileall/pipcheck/diffcheck, UTF8/noBOM/whitespace/no persisted private keys and
protected-surface readback passed. PostgreSQL 17.11 owned exact-ID cleanup confirmed.
Existing TestClient/httpx deprecation remains unsilenced, not a failed test.
README/Spanish SDD match adapter/default-deny and runtime/live limits.

Numeric policy: tenants 16 / clients 32 / scopes 16; scope<=128/sub<=1024/scp<=4096.
JWT 16384 bytes (1024–65536), kid 128 (1–256), response 262144 (1024–1048576),
keys 64 (1–128), public RSA 2048–4096/e65537. TTL 3600s (1–86400),
cooldown 60s (1–3600), fetch/lock/slot 3s (0.1–10), concurrency 2 (1–4),
skew 60s (0–300). Nonboolean finite NumericDate 0..2^53, chronology/skew rechecked
after signature. Read deadline 2x socket checked before/after bounded read1; OS DNS
is not an end-to-end SLA. Valid unexpired cached keys may work after refresh failure;
expired never; cooldown restarts at attempt completion even malformed/capacity failure.
Canonical identity is entra+exact validated tenant-v2 issuer+canonical oid;
actual sub remains separate. Same tid/oid/different sub intentionally same identity,
other tenant distinct; guests resource-tenant objects; no email/idp/sub fallback.

### F07a acceptance checkpoints (10; completed)

- [x] B1: Additive 0002 preserves 0001 and existing identity/member UUIDs; nullable
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

## F07a retained proof and limits

Explorer 2483 / accepted 2485 / full mirror 2468 readback 19755 characters preceded source.
Starting 4ab2d40c8c3a1e80cbb0106c917804fed949e881 clean. Eleven authored surfaces:
migrations/0002_entra_identity_binding.sql, src/forge/identity_store.py,
src/forge/postgres.py, tests/test_postgres_identity.py, tests/postgres_support.py,
tests/test_postgres_reader.py, tests/test_postgres_api.py, tests/test_postgres_rls.py,
README.md, docs/changes/entra-identity-binding.md and this task; ignored
.local/postgres-test/** only. No dependency/harness-script/0001/domain/API/F06/
manifest/closed-foundation/product-spec changes.

0002 nullable paired UUIDs/canonical consistency/unique pair/invoker write-once guard.
Internal bind_existing requires an existing exact canonical identity; constructing
VerifiedPrincipal is NOT authentication proof, only a trusted internal port.
Separate NOLOGIN binder role/pool: identities SELECT+pair-column UPDATE, self RLS
with local existing UUID/verified issuer/tid/oid; no raw sub/email or membership.
Original public identity policy scoped runtime/migrator to prevent org GUCs broadening
binder RLS; fixture explicitly adds test writer. Entra reader requires bound metadata,
generic records preserved. Runtime detects column UPDATE/INSERT/REFERENCES grants.

Meaningful real-DB RED 46 methods / 4 assertion failures/no errors: unbound Entra read
and three column mutation grants; all inherited 44 passed. Initial GREEN 46,
expanded 67, original 72; no further intermediate failures/skips.
Original writer 141=72 DB(24 binding/migration+17 reader+9 DB HTTP+22 RLS)+69 offline,
all required checks exit 0. Independent original 141 no concrete defect; parent 72,
PostgreSQL 17.11/13.668s/exact-ID cleanup.
Optional independent combined in-memory probe blocked 15s readiness BEFORE SQL;
no verdict, not PASS, unknown wrapper not repeated.

B9 extension: explicit final COMMIT→ROLLBACK alone is not mid-migration failure proof.
Added test_failed_migration_rolls_back_ddl_policies_role_and_existing_data:
fourth owned temporary DB executes exact 0002 with in-memory SELECT 1/0 before original
COMMIT; DivisionByZero/SQLSTATE 22012/INERROR, then explicit ROLLBACK/IDLE.
Readback: no new columns/binder role; unchanged policies/functions/generic+Entra+
member rows/four ENABLE+FORCE RLS tables. Distinct original explicit-rollback case
retained. Fresh and populated upgrade preserve UUIDs/null metadata, no backfill.
Four exact-script probes run before fixture initialization; cleanup only captured
random DB/case-created reserved roles; fixture ordered 0001/0002, no existing DB.
Pair-column REFERENCES subtests reject runtime and binder with no table grant;
existing malformed/partial/foreign/self/org-spoof RLS tests cover optional premise.
Tests-only extension changed no production bytes; no new production RED needed.
Expected deterministic SQL failure is an assertion, not unexpected failed test.

Final writer 142=73 DB(25 binding/migration+17 reader+9 DB HTTP+22 RLS)+38 Entra+
13 domain+18 HTTP, no skips/all exit 0; DB 14.420s/PG 17.11/exact-ID cleanup.
Independent durable 73 DB+previous 69 offline=142 applicable pass.
Parent latest 73 DB/13.492s/exact-ID cleanup. All B1–B10 completed; compile/pip/diff 0.
Tests prove no automatic identity/membership, write-once privileged rejection,
cross-tenant separation/concurrency/idempotency, role/session/ownership/ACL/RLS,
bounded pool/row-lock failures, post-UPDATE rollback and same-backend timeout/context
restoration. README/Spanish SDD agree, deployment runner/login wiring absent.
Finite policy: migration lock 2s/statement 10s; binder acquisition 1s override(0,30],
local lock 1s/statement 5s; fixture connect 2s/statement 5s,pool min/max 1,waiting 4,
reconnect 1s/open 5s. Transaction restores limits; not end-to-end deployment SLA.

## Observed commit boundaries

| Unit | Full commit | Exact observed stats |
|---|---|---|
| F06 behavior: feat(auth): validate Entra access tokens | 279fef10e248d25e72bb943ff08348600d4b6231 | 6 files, +1488/-2=1490 |
| F06 task evidence: docs(auth): record Entra validation delivery | 4ab2d40c8c3a1e80cbb0106c917804fed949e881 | 1 file, +11/-6 |
| F07a behavior: feat(identity): persist verified Entra bindings | 8183b8dd00503dda9e504f8c7a473b9ed936b0d9 | 11 files, +1337/-29=1366 |
| F07a task evidence: docs(identity): record persistent binding delivery | e6d7f95875693dfccea772598a41e9f269c28613 | 1 file, +24/-11 |
| F08a behavior: feat(runtime): compose explicit service status | 211b501383ea048d4691d5b591acce3b6ddefbb0 | 14 files, +2254/-356=2610 |

Behavior blobs matched independently verified candidate before staging/after commits;
F07a eight behavior/migration/test blobs unchanged across task follow-up, protected
surfaces unchanged against 4ab2d40. Clean checkout/index observed, no mutating hooks.
Existing Git automatic identity notice: no config edit/amend or AI attribution.
Task-only follow-ups record actual behavior hash without future self-reference.
No remote, native approval, account, production, F07b or live enrollment action.

## F08a acceptance checkpoints (12 closed; C10 partial evidence follow-up explicit)

- [x] C1: Typed immutable programmatic RuntimeConfiguration; None is explicit
  unconfigured. No env/DSN/config-file discovery; no pool/connect/DNS/IDP fetch
  unconfigured. Existing create_app() default-deny and /healthz semantics preserved.
- [x] C2: Complete explicit connection fields and fixed controls reject ambient
  libpq supplementation without global env mutation/default credentials. Presence-only
  PG* contamination guard and loopback-only profile are parent-accepted for configured mode;
  synthetic polluted child-env tests prove service/passfile/connection safety.
- [x] C3: Compose real EntraTokenValidator/PostgresBootstrapReader only; optional API
  lifespan seam; bounded pool open/wait/close off event loop, partial-startup and
  shutdown cleanup. Failed DB startup keeps truthful status available, never fake-ready.
- [x] C4: Catalog-only migrated 0001/0002 schema plus actual role/privilege/RLS probe,
  no org context/business rows/counts; SELECT-only column-grant regression. Finite
  transaction timeout, TTL/single-flight/cooldown; expired positives cannot mask outage.
- [x] C5: Public GET /forge/v1/status strict allowlist: version/runtime/configuration/
  storage/identity_provider/onboarding/user_access states only. runtime ready means
  local config+DB role/schema, NOT live IDP/authentication/enrollment/admin readiness.
- [x] C6: /status with packaged status.css/status.js runs locally without CDN/logo/
  forms/token input/login/storage/admin controls. Exact navy/teal/copper/sand/charcoal
  palette; English semantic, keyboard-accessible responsive UI and read-only refresh.
- [x] C7: CSP/no-store/same-origin assets/fetch; fixed resource routes, no path traversal/
  CORS expansion. Public/log error surfaces contain no IDs/scopes/DSNs/hosts/paths/
  raw exceptions/business counts/PII; failure and malformed-status UI remain truthful.
- [x] C8: Meaningful deterministic runtime and real-DB behavioral RED→GREEN/refactor;
  real ephemeral RS256+owned PostgreSQL composed bootstrap, existing metadata/
  membership gating unchanged. No live account, migration or binder wiring.
- [x] C9: All 142 inherited tests plus new runtime/DB tests, compile/pip/diff pass with
  counts/failed/skipped prerequisites recorded; owned cached Docker exact-ID cleanup.
- [x] C10 observed: Browser skill loopback render/refresh/keyboard/360x800/error
  redaction and exact own-PID shutdown; parent accepts this available functional
  evidence for LOCAL operational-shell delivery, not blanket browser certification.
- [ ] C10b follow-up evidence (not F08a implementation scope): Full browser network
  capture, actual screen-reader announcement and transient-loading observation
  remain unavailable/unverified; DOM/static/backend proof is complementary only.
- [x] C11: Verify actual wheel includes three assets after separately released bounded build-tool
  acquisition into .venv only. Parent accepted exact-pin public PyPI acquisition;
  actual staged build remains no-index/no-build-isolation/no-deps. No runtime upgrades.
- [x] C12: README/neutral-Spanish SDD correspond to implemented bounds/limits;
  independent verification+parent spot before separately authorized coherent local
  commit. Full task mirror/readback precede source; no source at plan checkpoint.

### Exact F08a surfaces and protected boundaries

Historical plan checkpoint wrote only:
- odd/tasks/forge-identity.md
- docs/changes/runtime-status.md

Exact surfaces released AFTER parent mirror/readback:
- src/forge/runtime.py
- src/forge/api.py
- src/forge/postgres.py
- src/forge/web/status.html
- src/forge/web/status.css
- src/forge/web/status.js
- tests/test_runtime.py
- tests/test_postgres_runtime.py
- tests/test_postgres_reader.py
- pyproject.toml
- README.md
- odd/tasks/forge-identity.md
- docs/changes/runtime-status.md
- .gitignore (only `/.local/runtime-test/`; parent-authorized final checkpoint)
- .local/postgres-test/**
- .local/runtime-test/**
- .venv/**

No new runtime dependency, helper or broad folder authorization. Existing Entra/
binder/domain/migrations/tests except listed/harness script/closed foundation/
product specs protected. Ignored runtime paths only owned harness logs/staged package/
wheel/server PID outputs; .venv only explicitly pinned build tools and their pinned
build-only dependencies. No credentials/token files. Stop for exact path scope if needed.

### Planned contract and numeric limits

Factory forge.runtime.create_runtime_app(configuration=None); explicit config only.
No env loader or DSN. Parent-accepted local profile supplies numeric loopback host+hostaddr,
port, dbname, user=forge_runtime, nonempty explicit password (repr excluded), fixed
safe options/search_path/row_security/auth/transport controls, no arbitrary kwargs.
Reject PG* presence without reading/adopting values; do not call PQconndefaults
(which consults environment). Noarg mode does not inspect environment.
Local SSL/GSS-disabled profile is only for owned loopback evidence, not production.
Production TLS/remote profile deferred. Parent accepted presence-only PG* rejection
in configured mode and this explicit loopback-only profile, without global environment
mutation or ambient service-file access. This is not a production TLS claim.

Libpq 17 source calls service lookup before defaults; supplying usual fields alone
does not prevent PGSERVICE/PGSERVICEFILE and default service-file lookup. Empty
service is not assumed a disable switch. Supplied nonempty password must prevent
default passfile fallback; fixed controls and synthetic environment tests must prove
the full contract before claiming configured readiness. Never mutate global env.
Sources: https://www.postgresql.org/docs/17/libpq-connect.html ,
https://www.postgresql.org/docs/17/libpq-envars.html ,
https://raw.githubusercontent.com/postgres/postgres/REL_17_STABLE/src/interfaces/libpq/fe-connect.c .

Fixed bounds (implemented and observed below): pool min 0 / max 2, max waiting 4,
reconnect 1s, connect 2s, acquisition 1s, open-wait 5s, close 5s; probe statement 3s / lock 1s,
cache TTL 5s and one in-flight probe, failure cooldown 5s. No periodic poll/stampede;
expired positive cache never implies available storage. Blocking work off event loop;
DNS/OS scheduling not falsely described as a hard request SLA. Finite startup/failure/
cleanup tests must verify observed library behavior; record justified adjustment.

Public status schema version 1.0: runtime unconfigured/checking/ready/unavailable;
configuration missing/provided; storage not_configured/checking/ready/unavailable;
identity_provider not_configured/configured_unverified; onboarding not_implemented;
user_access not_evaluated. No tenant/client/identity IDs, scopes, DSNs, paths, counts
or raw error fields. /healthz remains liveness, not readiness.
Catalog checks establish expected table/column/type/pair constraint/trigger/RLS/
role prerequisites without organization GUC or data query. Reader still evaluates
every real bootstrap request and membership; readiness grants no authorization.

UI palette #0B1D26/#0F6B6D/#E07A2D/#E8DCC1/#1A1A1A. Semantic headings/landmarks,
visible keyboard focus, status live region, button disabled while refreshing,
text-based state labels, 360x800 layout and fetch failure/stale fallback.
Copper accent is not assumed contrast-safe body text; verify contrast.
Fixed package resources with external local CSS/JS; CSP default-src 'none',
script/style/connect/img 'self', base-uri/frame-ancestors/form-action/object-src 'none';
no inline scripts/styles. no-store status/HTML/assets; no browser token storage.

### Exact planned verification after release

From N:/Proyects/forge/.worktrees/tenant-storage:
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

The harness discovers test_postgres_*.py including test_postgres_runtime.py.
Baseline 142=73 DB+38 Entra+13 domain+18 HTTP; new counts unknown. Observe behavioral
assertion RED against an importable contract before GREEN, not import-error-only
RED. Lifecycle/cache/concurrency/role/schema/column grants/ambient pollution/security
headers/assets/redaction tests plus actual cryptographic composed bootstrap.
Owned pinned cached PostgreSQL image/container only, no pull/prune/existing DB;
exact-ID cleanup each run. Missing prerequisites do not silently skip.

Planned offline packaging command after bounded authorized build-tool acquisition:
    ./.venv/Scripts/python.exe -m pip --isolated wheel --no-index --no-deps --no-build-isolation --no-cache-dir --wheel-dir .local/runtime-test/wheels .local/runtime-test/package-src
Stage exact source/manifest/README copy in authorized ignored package-src; no original
build metadata outside allowed paths. Inspect actual wheel ZIP/importlib.resources
for all three assets; checkout existence is not packaging proof. Initial backend
absence remains historical, not a failed build or PASS. Acquisition is authorized
only AFTER source release; installation/build proof is still pending.

Browser proof after source functional checks, parent/verifier with loaded browser
skill only. Hidden owned Start-Process runs:
    ./.venv/Scripts/python.exe -m uvicorn forge.runtime:create_runtime_app --factory --app-dir src --host 127.0.0.1 --port 8765 --no-access-log
Capture own PID/logs under .local/runtime-test; if port busy, stop without probing/
killing occupant. Browser skill NodeREPL bootstrap + URL-directed getForUrl,
immediate full browser.documentation read; visit only http://127.0.0.1:8765/status.
Observe refresh, keyboard focus/live states, narrow viewport and no external requests/
leaked diagnostics. Report unavailable browser capability honestly; no standalone
automation substitute. Stop only captured own PID, confirm owned server cleanup.
Unconfigured browser run performs no account or DB probe.


### Accepted build-tool pins and planned acquisition

Official PyPI version metadata verified 2026-10-04: setuptools84.0.0 (Python>=3.10),
wheel0.48.0 (>=3.9), build1.6.1 (>=3.10); all universal Python wheels/non-yanked,
compatible with Python3.12.14. Build-only dependencies: packaging26.0 (>=3.8),
pyproject-hooks1.2.0 (>=3.7), colorama0.4.6 (>=2.7 excluding3.0–3.6).
build requires packaging>=24, pyproject_hooks and Windows colorama; wheel requires
packaging>=24. Six pins form the complete dependency set for this Python/OS without
optional extras. Historical pre-acquisition readback: all six absent. Actual installation proof below.

Primary metadata: https://pypi.org/pypi/setuptools/84.0.0/json ,
https://pypi.org/pypi/wheel/0.48.0/json ,
https://pypi.org/pypi/build/1.6.1/json ,
https://pypi.org/pypi/packaging/26.0/json ,
https://pypi.org/pypi/pyproject-hooks/1.2.0/json ,
https://pypi.org/pypi/colorama/0.4.6/json .
Earlier considered wheel0.45.1 was rejected during metadata checking: official
metadata reports CVE-2026-24049 (fixed0.46.2). Selected0.48.0 avoids that known issue;
no old pin installed. Current selected metadata reports no listed vulnerabilities,
not a guarantee that none exist.

After source release only, record existing distribution names/versions (no URLs/
environment/credentials) and enforce they remain unchanged; build tools are additions,
not runtime upgrades. Exact planned commands:
    ./.venv/Scripts/python.exe -m pip --isolated install --dry-run --index-url https://pypi.org/simple --no-cache-dir --no-input --keyring-provider disabled --timeout 15 --retries 1 --only-binary=:all: --no-deps "setuptools==84.0.0" "wheel==0.48.0" "build==1.6.1" "packaging==26.0" "pyproject-hooks==1.2.0" "colorama==0.4.6"
    ./.venv/Scripts/python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir --no-input --keyring-provider disabled --timeout 15 --retries 1 --only-binary=:all: --no-deps "setuptools==84.0.0" "wheel==0.48.0" "build==1.6.1" "packaging==26.0" "pyproject-hooks==1.2.0" "colorama==0.4.6"
    ./.venv/Scripts/python.exe -m pip check

Overall acquisition wall bound180s across dry-run/install; timeout15/retries1 per
request, public index only/no cache/keyring/ambient credentials; no retry loop or
unrelated upgrade. --no-deps with all six exact metadata-compatible pins prevents
resolver drift; verify installed versions/dependency health and preserved runtime
versions. .venv is the only installation target. Build remains isolated from network
via the no-index staged command above, with no build isolation/dependency fetching.

### Release conditions, rollback and next step

Parent resolved the local profile/ambient guard and authorized bounded build-tool
acquisition. Parent full mirror 2468/topic odd/forge-identity/tasks and exact
readback preceded source release; refreshed candidate mirror remains parent-owned.
Writer/independent/browser evidence is below; parent spot and scoped local
delivery decision completed before commit authorization. No new product decision or credentials request assumed.
Programmatic deployment prerequisites: external ordered 0001/0002 migration, supplied
restricted runtime login/pool credentials, complete allowed connection controls,
explicit Entra tenant/audience/client/scopes config and resource requestedAccessTokenVersion2.
No migration execution, binder composition, live tenant test, PKCE/token storage,
invitations/outbox, administration or automated membership. Status is not an admin client.
Rollback boundary for F08a is behavior commit211b501383ea048d4691d5b591acce3b6ddefbb0; no database
mutation/downgrade. F07b/F09 remain separately scoped and unreleased.
Engram project prometheon-forge; no authoritative session ID. Parent owns full task
mirror; worker checkpoint memory is separate. F08a observed checks below are current; F06/F07a historical evidence is not a new
claim of live enrollment. Parent owns refreshed full mirror.


## Historical F08a writer candidate and observed proof

Source release followed parent full updated mirror2468/exact normalized readback
of the accepted30892-character plan and Spanish SDD. HEAD remains
e6d7f95875693dfccea772598a41e9f269c28613, no commit. Thirteen authored surfaces
match release; no extra helper/runtime dependency/harness/migration/domain/binder/F06
edits. Parent later authorized only `/.local/runtime-test/` in .gitignore because
staged wheel/log outputs were otherwise untracked; existing patterns preserved.
Fourteen authored files now include that mechanical output-scope correction.

Behavioral RED: six runtime methods/26 assertions, no errors against importable
default-deny skeleton; owned DB76 methods/two assertions, all inherited73 passed,
exact-ID cleanup. Initial GREEN6 runtime+76 DB. Password fixture initially encoded
literal backslash-x00 rather than NUL; corrected before GREEN, not a production fix.

Expanded proof retained intermediate failures honestly:
- Non-escalated ignored-log redirection denied before tests; scoped escalation
  succeeded, no skipped prerequisite.
- Test-string quoting gave one import SyntaxError; fixture corrected.
- Expanded21 runtime then one test-double error: replacing os.environ interfered
  with FastAPI OTEL getenv. Replaced with runtime guard-call assertion; configured
  synthetic PG pollution runs only in child envs, no global env mutation.
- Expanded87 DB: two assertion failures because uncommitted trigger/function DDL
  was invisible to the probe's other connection; one attempted pair-type DDL
  blocked by policy dependency. Corrected fixtures commit owned DDL with exact
  finally restoration and alter independent slug type. Subsequent87 GREEN.
- Entra38 passed in an early command whose accidental trailing './' shell token
  failed; final exact Entra command passed exit0. Not misreported as a test failure.

Final required writer checks, no skips:
- test_runtime.py25, test_entra.py38, test_foundation.py13, test_api.py18: exit0.
- Unchanged scripts/test-postgres.ps1:87 DB, PostgreSQL17.11,14.064s, exit0;
 25 binding/migration+18 reader+9 DB HTTP+22 RLS+13 runtime. Owned cached image/
 exact-ID cleanup confirmed on every RED/GREEN/expanded/final harness run.
- Total181 =142 baseline+25 runtime+14 DB additions.
- compileall, pip check and git diff --check: exit0. Existing TestClient/httpx
 deprecation and Git LF/CRLF/global-ignore permission warnings remain unsilenced.
 No ambient configuration/permission changes to hide warnings.

Six build-tool pins dry-run/install exit0,13.625s total under180s; all prior
distribution versions preserved. Actual client libpq18.4 (180004), server17.11;
controls parsed using supplied make_conninfo only and exercised via real SCRAM
runtime connections. Clients below18 fail closed rather than silently losing controls.
Explicit host=hostaddr canonical loopback, port1..65535, DB identifier1..63,
password nonempty/<=4096 UTF8 bytes/no control/surrogate, fixed role forge_runtime.
PG* names-only rejection occurs before configured pool creation AND on connect.
No default credential/service/passfile/cert access, environment clearing or runtime
account discovery. Primary current-client evidence:
https://www.postgresql.org/docs/18/libpq-connect.html and
https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/src/interfaces/libpq/fe-connect.c .

Observed policy: poolmin0/max2, waiting4/workers2, connect2s/acquisition1s,
open-wait5s/close5s/reconnect1s, query3s/lock1s, cacheTTL5s/single-flight/completion
failure cooldown5s. Lifespan/probe threads differ from event-loop thread. Startup/
constructor failure stays publicly unavailable; cleanup/rollback/connection errors
are redacted, cleanup failure observable. Pool repr/warnings do not expose DSN,
host/password/database/raw libpq diagnostics; no global logging mutation.
Catalog-only probe checks role/column grants/RLS,17 column shapes, exact pair CHECK,
pair unique keys/enabled invoker trigger/helper/policy/FK prerequisites and absent
business context; not full policy-function-body or migration-byte attestation.
Committed schema damage, empty business tables, column-only grants, dirty pool/
context, positive-cache expiry/outage/recovery and cleanup are tested.

Real ephemeral RSA+fake public JWKS with actual composed runtime/owned PostgreSQL:
readiness makes zero IDP calls; invalidJWT401; valid-unbound404; explicit test-only
metadata binding permits200; foreign404, owned suspended403, revoked404. Status
still configured_unverified/not_implemented/not_evaluated; no login/binder wiring
or automatic identity/member creation. No persisted private keys/credential files.

Actual offline staged wheel succeeded. First approved planned command lacked
--no-cache-dir and pip reported a default local AppData wheel-cache entry; unexpected
build artifact outside intended staging, no network/dependency/account. Parent
notified; no out-of-scope cache inspection/deletion performed. Final command adds
--no-cache-dir and child-only TMP/TEMP under .local/runtime-test/tmp, preserving
global environment. Final ephemeral cache/build metadata stays in ignored staging.
Final prometheon_forge-0.1.0-py3-none-any.whl:
SHA256362da36402fb759af76eca231bccfba6b1b9ac3226aa895bbeba9f7456fe0364.
ZIP assets exactly match source: HTML2308/CSS2290/JS2588 bytes.
Fresh child imports forge directly from wheel (not checkout), reads all resources
via importlib.resources and serves three routes+unconfigured status exit0; no wheel
install/download. Test caches/private keys not included. Runtime versions preserved.

README/neutral-Spanish SDD describe actual local runtime and production gaps.
C6/C7 static/HTTP/contrast and observed browser behavior have evidence; C10 retains
capability limits rather than a blanket PASS; C10b explicitly remains follow-up.
C12 independent focused retest/parent spot and local commit authorization completed. Writer launched no server/browser and makes no native approval claim.


### Independent finding, bounded correction and browser evidence

Original independent181+wheel passed, but controlled synthetic global tracer
confirmed P1: FastAPI0.142.2 default native telemetry captured raw query token/
identity markers and endpoint names through unconfigured/status requests.
Parent authorized only shared-factory correction and durable regressions; no UI
redesign. create_app now supplies typed TelemetryConfig with tracing/metrics/logs/
operation_spans/auto_configure allFalse. Automatic setup alone would not stop
existing global providers. No host-global provider/environment/logging changes;
external middleware/host instrumentation is outside this native guarantee.

Meaningful RED28 runtime methods/4 assertion failures (three new methods; shared
factory subtests count twice),59 controlled provider calls; no errors. Child-only
positive-control trace/meter/logger providers have no SDK/exporters/network;
OTEL child environment and configuration/export-discovery hook prove native
setup cannot activate. GREEN28 and corrected full184 =28runtime+87DB+38Entra+
13domain+18HTTP, no skips; DB14.770s/server17.11/exact-ID cleanup. compileall,
pipcheck,diffcheck exit0. Logs telemetry-red/green.log and *-corrected.log under
.local/runtime-test. No dependency changes or additional source paths.

Corrected staged offline wheel command unchanged, exact source API and three
static assets ZIP byte-matches; fresh wheel import/resources/four HTTP routes exit0.
Current SHA256 8e46e0e1d6174c3535201b78f1e018896f6c49697c3a74c7d63da667d16c93bc;
previous362da364... wheel hash remains historical before API correction.

Parent-reported browser actor proof: actual unconfigured render; keyboard Tab
skip-link/Refresh and Enter;360x800 without overflow; live attributes; server-stop
Refresh shows fixed safe unavailable, clears other fields and re-enables button.
Own PID15480 stopped twice/tab closed. No blocking visual defect.
Limits: transient loading too fast (source evidence only), actual screen-reader
announcement unverified, browser performance/network capture unavailable.
DOM-local assets plus deterministic static fetch constraints/backend adapter and
native-telemetry isolation complement but do not equal full browser zero-outbound
capture. Failure focus falls to body, nonblocking observation; no requested UI fix.
Independent P1 retest closed: original synthetic positive control now zero spans/
attributes/export-discovery, global providers unchanged;28runtime+18API passed and
previous138 other proof applicable, total184. Corrected actual wheel checked.
Parent spot28 passed10.292s; parent visually inspected mobile screenshot, no issue.
Parent accepts LOCAL operational-shell delivery with C10 observed closed and C10b
follow-up limits explicit, not production readiness or full accessibility/network
certification. Coherent local commit authorized; no further source changes.


### F08a actual local commit proof

Parent-authorized behavior commit211b501383ea048d4691d5b591acce3b6ddefbb0,
feat(runtime): compose explicit service status, exactly14 files+2254/-356=2610.
Ten verified source/test/manifest blob identities matched before staging and in
commit/worktree afterward; no .local/.venv outputs staged. diff/check passed;
clean git porcelain observed immediately after behavior commit. Conventional
message has no AI attribution. Historical e6d7f95 baseline now replaced by this
local work-unit boundary; task-only evidence follow-up does not change source.
Running authored count through behavior:5518=1490+17+1366+35+2610 across recorded
F06/F07a/F08a behavior/evidence commits; generated outputs excluded, authorized
feature-branch chain unchanged. No remote publication/native approval.
C10b evidence, F07b/F09 and deployment/liveEntra/production readiness remain pending.
Parent refreshes full task mirror after final readback; worker memory is separate.
