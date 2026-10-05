# Forge administration: scoped membership authorization

## Current outcome and gate

**F07b1 read-model delivery is closed; local coherent commit authorized.** Parent
mirror2534/topic odd/forge-administration/tasks and exact14581-character plan
readback preceded source. Writer211 and rebuilt wheel passed. Independent corrected
108DB+6policy plus applicable prior97=211 passed, wheel verified, no finding.
Parent spot108DB/18.864s, PostgreSQL17.11, exact-ID cleanup passed. Commit identity
and observed stats are recorded below after the operation, never inferred.
Parent owns refreshed full mirrors; no administration API/bootstrap is delivered.

Baseline 48785aeb1d41958c227b8e80cc66dc0ac95d177c, clean
feat/forge-tenant-storage in N:/Proyects/forge/.worktrees/tenant-storage.
Inherited184 =28runtime+87DB+38Entra+13domain+18HTTP is historical proof, not a new run.
F08a behavior211b501383ea048d4691d5b591acce3b6ddefbb0 and task follow-up48785aeb...
closed the local status shell; C10b network/screen-reader/loading evidence remains
pending there. Parent feature: odd/tasks/forge-identity.md, mirror2468.
New mirror topic odd/forge-administration/tasks is parent-owned; worker checkpoint
memory is separate. Gentle GLOBALOFF: disabled/unmanaged, no calls or native approval.

## Objective and boundaries

Add organization-scoped persistent membership roles, a revision and a fresh
internal authorization snapshot before member administration mutations. PF-02
defines organization roles; PF-10 specifies membership revision and administrator
member endpoints. Authentication, persistent identity binding and organization
membership remain distinct from authorization.

One closed local work unit; future administration slices remain unreleased:
- [x] **F07b1 — Membership authorization read model.** Additive schema, immutable
  snapshot/pure default-deny policy, restricted fresh PostgreSQL read and extended
  runtime readiness. No administration endpoints or writes.
  Route: delegated direct; migration/security/readiness plus multiple non-trivial
  source/test files require a bounded writer and independent verification.
- [ ] **F07b2 — Member administration/bootstrap decisions (future, not released).**
  Trusted first-administrator designation/recovery and last-administrator policy
  need product decisions before mutations. No default/admin seed is inferred.
- [ ] **F07b3 — Invitations/provisioning/audit/outbox (future, not released).**
  Identity object confirmation, invitation states, transactional writes and
  idempotent provisioning/outbox require separate bounded scope.
F07b remains unfinished in the identity feature; F09 remains separately unreleased.

## Accepted design

| Area | F07b1 decision |
|---|---|
| Organization roles | Exact organization_admin, department_manager, skill_reviewer, member; platform_operator is NOT an organization role |
| Policy | Only organization_admin permits exact members.invite, members.update, members.suspend; everything else denies |
| Unknown values | Unknown/malformed action, empty roles or any unknown role (even mixed with organization_admin) deny; no coercion, aliases or implicit grant engine |
| Trusted source | Internal authenticated identity port after validation; never JWT/request/header/body-claimed roles, email matching or arbitrary dataclass construction as proof |
| Freshness | One parameterized business SELECT statement snapshot per read; no authorization cache and no reusable write capability |
| Schema | New membership_roles(organization_id,membership_id,role), composite PK/FK and exact role CHECK; memberships.revision bigint NOT NULL DEFAULT1 CHECK revision>0 |
| Scope | Bound canonical Entra identity plus active requested organization and active owned membership; preserve generic trusted test-provider fixtures |
| Database privileges | Runtime SELECT only, five ENABLE/FORCE RLS tables; binder gets zero access to new role table/revision, existing pair-column permissions unchanged |
| Future writes | Revalidate identity/org/membership/roles/revision inside the mutation transaction with audit/outbox; this snapshot does not reserve permissions |

Migration0003 is additive and transactional; 0001/0002 bytes remain unchanged.
Existing membership composite PK(organization_id,id) already supports the new
composite FK. Preserve active/suspended/archived exactly. Existing rows receive
revision1 through the schema default, but no role rows/backfill, administrator
designation, identity creation or membership grant. No automatic revision-bump
or mutation/If-Match guarantee is claimed in this read-only unit.

New table owned by forge_migrator; revoke PUBLIC and grant only runtime SELECT.
SELECT RLS is organization-local/self-only through existing canonical identity and
membership scope, additionally active membership/organization and complete coherent
persisted Entra tenant/object binding (generic providers unchanged); no SECURITY DEFINER
escape, platform operator inheritance or visibility of peers' role rows.
PK(org,member,role) prevents duplicates; FK(org,member) prevents cross-org linkage.
No cascade-delete/history behavior is introduced; preserve lifecycle constraints.

AuthorizationSnapshot is frozen, uses immutable copied roles and canonical UUID
organization/membership identifiers plus exact trusted identity, revision, lifecycle
and organization-active state. Pure policy validates its complete shape, exact
known roles/action, positive typed bigint revision (bool excluded), active status
and org. Empty/unavailable/malformed snapshots deny. Unknown mixed roles fail closed.

PostgresAuthorizationReader takes an externally owned restricted synchronous pool,
validated identity and requested org UUID. Reject invalid inputs before borrowing;
operational failures use a fixed redacted typed internal exception, never raw DB/
DSN/token/PII text. Entra issuer/subject must match verified persisted tid/oid; no
sub/email/idp fallback. Other trusted provider fixtures preserve existing behavior.
Borrow one idle autocommit connection, inspect actual role/ACL/RLS, require clean
canonical/binder context, set only transaction-local identity/org GUCs and use one
parameterized joined SELECT for membership revision+roles. No torn multi-query
role snapshot, public role response, HTTP route, pool creation or login wiring.

Bound planned limits: migration lock2s/statement10s; reader acquire1s (optional
finite (0,30] override), SET LOCAL statement3s/lock1s. Validate numeric bounds
before float conversion, reject bool/oversized values. Exceptions/normal returns
restore transaction/context/timeouts and return borrowed connections; no silent
pool reopen or global environment changes. Actual client libpq18.4/server17.11
are inherited verified versions, not a new deployment compatibility claim.

Extend existing _ROLE_CHECK's required-RLS count from four to five and retain its
all-forge-table SELECT-only guard, including column INSERT/UPDATE/REFERENCES and
ownership/session/membership/elevation checks. Extend catalog-only readiness with
new columns/type/default/revision CHECK, PK/FK/role CHECK, self-only SELECT policy,
ENABLE/FORCE RLS and runtime grant; do not weaken existing Entra/schema checks or
query business data/counts. Missing/weak migrated shape or expanded privileges
must make readiness unavailable. Binder access must remain denied independently.

## Acceptance checkpoints (D1–D10 observed)

- [x] D1: Additive bounded0003 preserves0001/0002, existing rows/lifecycle/RLS;
  revision positive default1, scoped role PK/composite FK/exact four-role CHECK,
  no role/admin seed/backfill; five ENABLE/FORCE RLS tables.
- [x] D2: Frozen immutable snapshot and pure exact-action/default-deny policy;
  administrator allows only three member actions; other known roles/platform
  operator/unknown actions/unknown mixed roles/invalid types deny.
- [x] D3: Real PostgreSQL single parameterized business SELECT from canonical
  identity + active requested org/owned active membership/revision/roles; exact
  Entra bound metadata, generic fixtures preserved; no cache or claimed roles.
- [x] D4: Runtime-only read privileges, binder zero new access, self-only RLS and
  cross-org/peer denial; no writes, privilege escalation or protected-source change.
- [x] D5: Reader role/ownership/session/clean-context/idle-autocommit/timeouts/
  acquisition and transaction cleanup pass; fixed redacted operational errors.
- [x] D6: Distinct new fresh0001→0002→0003, populated-upgrade and injected failure
  cases; real INERROR before rollback, no new role table/revision/policy/ACL after
  rollback, existing rows/functions/RLS identical. Original0002 probes unchanged.
- [x] D7: Runtime guard/readiness extend new storage without weakened checks;
  actual owned-PG ready after0003 and unavailable for absent/weakened schema/RLS/
  table or column mutation grants. Existing API/domain/Entra/binder/UI untouched.
- [x] D8: Meaningful policy and owned-DB RED→GREEN, all184 baseline plus new tests,
  compileall/pipcheck/diffcheck; counts/errors/skips/cleanup recorded truthfully.
- [x] D9: Existing tools build staged offline wheel including new modules and
  existing exact static assets; ZIP/fresh import/resources proof, no installation/
  new dependency/index/build isolation/ambient cache.
- [x] D10: README and neutral-Spanish SDD correspond; parent full task mirror/
  readback before source, independent verification + parent spot before separate
  local coherent commit authorization. Record actual hash/stats only after commit.

## Exact edit surfaces

Historical plan checkpoint wrote only:
- odd/tasks/forge-administration.md
- odd/tasks/forge-identity.md (one child delegation link only; history/F07b unchanged)
- docs/changes/membership-authorization.md

Exact source surfaces released AFTER parent full mirror/readback:
- migrations/0003_membership_authorization.sql
- src/forge/authorization.py
- src/forge/authorization_store.py
- src/forge/postgres.py
- tests/test_authorization.py
- tests/test_postgres_authorization.py
- tests/postgres_support.py
- tests/test_postgres_rls.py
- tests/test_postgres_runtime.py
- README.md
- docs/changes/membership-authorization.md
- odd/tasks/forge-administration.md
- odd/tasks/forge-identity.md
- .local/postgres-test/**
- .local/runtime-test/**

Thirteen authored paths plus two already ignored owned-output surfaces, no broad
helper folder. Protect migrations0001/0002, foundation/domain, API, Entra validator,
binder, runtime composition/UI/static assets/manifest, existing tests except listed,
harness script, product specs and closed feature histories. No dependencies or
installer/.venv writes authorized; existing exact build tools suffice.

## Verification plan and forecast

Test-first applies: after release, observe meaningful pure-policy matrix RED
against importable deny-all skeleton, and real owned-PG behavior RED before storage/
guard implementation; no import-only RED claim. Then GREEN/refactor and full checks.
Commands below were observed at writer closure; intermediate/final evidence follows.

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_authorization.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

Owned cached-image Docker harness only; no pull/prune/external/existing DB.
New migration probes must be distinct from original0002 probes: keep original
four-table TABLES/probe scripts/evidence unchanged, run new cases before shared
fixture setup, then apply explicit ordered0001/0002/0003 to normal fixture.
New tests must not make old probes assume0003. Exact owned DB/role/container cleanup,
positive evidence for real transaction failure rather than COMMIT→ROLLBACK alone.

Policy matrix covers all four known roles, combinations, no roles, platform_operator
alone/mixed, unknown/case/whitespace actions/roles, malformed IDs/revision/status/
active state and immutable roles. Real DB covers per-org and peer isolation,
unbound/cross-tenant Entra, no email matching, inactive/suspended/archived/no membership,
fresh role/revision/removal/lifecycle changes, concurrent consistent snapshots,
constraints/ACLs/binder denial, column/table mutation privilege rejection and cleanup.

Offline packaging uses existing tools only: copy src/forge (exclude caches),
pyproject.toml and README to .local/runtime-test/package-src; execute in child with
explicit SystemRoot/PATH and TMP/TEMP under .local/runtime-test/tmp:

    ./.venv/Scripts/python.exe -m pip --isolated wheel --no-index --no-deps --no-build-isolation --no-cache-dir --wheel-dir .local/runtime-test/wheels .local/runtime-test/package-src

Inspect wheel ZIP for forge/authorization.py and forge/authorization_store.py,
byte-identical existing three assets; fresh child import from wheel (not checkout)
and importlib.resources checks. No source tree metadata/ambient cache/credentials.
UI unchanged: no new browser ceremony required, but new real readiness integration
mandatory. Existing C10b unavailable certification is not silently closed.

Forecast1100–1800 authored changed lines, dominated by complete migration/privilege/
failure/concurrency proof and focused docs; generated/runtime artifacts excluded.
About400 is advisory, not a cap or reason for code-golf/artificial file-type splitting.
Existing accepted feature-branch-chain local delivery strategy remains; one coherent
behavior/test/docs unit after independent check/parent spot and separate commit
authorization. No commit at checkpoint or source stage; no remote/push/PR/merge.
Checks should use only owned local resources, roughly1–3minutes after release;
no download/new dependency/live identity/production spend.

Rollback boundary: F07b1 local code/test/docs commit plus separately governed DB
migration rollback/recovery; no destructive schema downgrade is implemented.
Migration execution/deployment runner is not provided. A read snapshot is advisory
internal data at its observation time, not a reusable mutation capability.

## Checkpoint result and next step

D1–D10 and F07b1 are observed closed: writer, independent correction retest and
parent spot passed; local work-unit commit is authorized. No future mutation release.
Parent refreshes FULL current task mirror under odd/forge-administration/tasks.
No product choice blocks this read slice; bootstrap/last-admin decisions are future.


## Observed writer proof (verified candidate history)

- Policy meaningfulRED:6 methods/26 assertion failures against importable deny-all
  skeleton; no errors. RealDB meaningfulRED:88 methods/one assertion, all87 inherited
  DB passed, owned exact-ID cleanup. Initial policyGREEN6.
- First storage/guard implementationDB88/three failures: existing table-count test
  still expected4 and two actual runtime checks failed because pg_get_expr policy
  output depends on supplied search_path. Extended the expected migrated count to5
  and set transaction-local search_path=pg_catalog in reader/readiness; restore
  tested. New exact metadata assertion passed; firstGREEN89DB/14.662s.
- Expanded102DB passed16.656s, but structural discovery check found four newly
  appended RLS/readiness methods below existing __main__ guards (not discovered).
  Moved those methods into classes before guards; subsequent106DB passed17.568s.
  The102 pass is intermediate, not proof of those four cases. One orchestration
  JavaScript syntax error occurred before any tool/command; retried corrected call.
- Added actual relation-lock timeout recovery and populated upgrade/failed-migration
  rows for all three lifecycle states; final107DB passed18.593s, PostgreSQL17.11,
  exact-ID owned-container removal confirmed. No skips/import/setup failures final.
- Final6policy+28runtime+38Entra+13foundation+18HTTP+107DB=210;
  inherited184 plus6policy+20DB additions. compileall/pipcheck/diffcheck exit0.
  Existing TestClient deprecation and Git LF/CRLF/global-ignore permission warnings
  remain unsilenced; no global configuration changes.

Fresh0003 probe evidence:(table/revision presentTrue,0rows,5RLS,idleTrue).
Populated upgrade:three active/suspended/archived memberships preserved, revision1,
zero seeded roles,5RLS. Injected exact0003 beforeCOMMIT:22012/INERROR thenROLLBACK/
IDLE, no role table/revision, prior rows/metadata/ACL/policies/functions/fourRLS
identical. Original0002 migration_probe source segment and TABLES4 exact baseline
match verified, and original four evidence cases still assert fourRLS.

Pure matrix covers every known-role combination/three actions, unknown mixed roles,
platform operator, malformed snapshots/action/revision/types and copied frozen sets.
RealDB proves active self/org/canonical bound Entra/no fallback, noauthcache after
role/revision/lifecycle changes, peer/cross-org denial, binder/runtime mutationdenial,
constraints, one parameterized business SELECT,20concurrent transactional role/
revision transitions observed via30 consistent snapshots, dirty/nonidle/autocommit
rejection, actual1s relation lock/0.1s exhausted-acquire failure, same-backend context/
timeout/search_path restoration and redacted injected failure. No HTTP/mutations.

Readiness proves exact new CHECK/PK/FK/default/one self-only SELECT policy plus
role ownership/PUBLIC/binder restrictions; missing role table/default/FK/CHECK,
weakened/additional permissive policy, disabledRLS or column mutation grants on
roles/revision deny; existing Entra/schema checks preserved. Real runtime configured
search_pathpg_catalog,forge still becomesready through the existing crypto/storage
integration; no status/UI/source change or new browser proof.

Exact build: existing tools only, staged source/manifest/README, child TMP/TEMP,
--isolated wheel --no-index --no-deps --no-build-isolation --no-cache-dir.
Pre-correction wheel SHA256 9adeb3ebedebc1cc4821bbd411c2d02a1ad48e00222468d92e3a1c0fa4b8b8ff; ZIP new
forge/authorization.py,forge/authorization_store.py,forge/postgres.py and all three
unchanged assets byte-match. Fresh wheel import (not checkout), resource/HTTP proof
exit0, no tests/caches/private keys/download/install. Logs f07b1-*-final.log,
authorization-*.log and f07b1-wheel-proof.json under ignored .local/runtime-test.

No source release expansion/liveEntra/remote/Gentle/native approval.
F07b2/F07b3/F09 remain unreleased; local F07b1 closure is recorded below.

## Scoped role-RLS binding strengthening (parent-authorized)

Independent original210/wheel passed. A separate direct runtime SELECT showed only
an unbound Entra identity's own organization_admin row; the authorization reader
correctly returnedNone. This was a layer distinction, NOT an authorization bypass.
Parent chose defense-in-depth in NEW0003 role policy only: complete nonnull pair,
exact tenant-v2 issuer and canonical object subject; no metadata/admin autofill.
Generic providers and0001/0002 policies remain unchanged. Exact readiness policy
shape was updated, not weakened; replacing it with the previous active-self-only
body now durably denies readiness and restoration is ready.

Meaningful rawSELECT RED108DB/18.647s: exactly one unbound-row assertion failed;
readerNone assertion passed first and107 prior tests passed, exact-ID cleanup.
First strengthened GREEN108/19.168s; final108/19.918s includes bound own-row positive,
generic Carol/Bob own-row positives, peer/cross-org/wrong-tenant/raw-sub denial and
unchanged reader denial/bound permission. Both server17.11, exact-ID cleanup.
Final211=6policy+108DB+28runtime+38Entra+13foundation+18HTTP; all exit0/no skips.
Runtime10.135s; compileall/pipcheck/diffcheck0. No protected source changes.

Rebuilt staged offline wheel SHA256
06014d56d1137e20664b76aaac611bd805aea214d342739f760a3ac3c3754b43;
new modules/currentpostgres/three unchanged assets byte-identical, fresh wheel
imports/resources/fourHTTP routes exit0; no dependency/install/download.
Exact0003 readback SHA256 f1b72d96dde40e1740c4d4d59036bff61c600a5d36f508d79a16542fbaceaf94;
SQL is audited source, not claimed as a packaged wheel asset.
Proof logs f07b1-*-binding-final.log, f07b1-binding-red/green.log and
f07b1-wheel-binding-proof.json under ignored .local/runtime-test.
Independent correction retest211/wheel and parent spot108/18.864s passed;
D10/F07b1 closed with local commit authorization. No admin/API-ready claim.

Structural audit initially used a missing next-def delimiter in baseline helper
(ValueError, read-only); corrected def/class delimiter proved original probe intact.
