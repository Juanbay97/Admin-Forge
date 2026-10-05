# Forge administration: scoped membership authorization

## Current outcome and gate

**F07b1 and F07b2a are locally committed; initial-only internal designation delivery is closed.**
Parent released source after full mirror2534 normalized readback matched; baseline
96e29200460df7b6f3f220c24f7f3064bac5ab71. User-confirmed central first designation
(memory2549; technical2553/explorer2550) is implemented internally, not self-signup.
Observed266 tests pass; independent266 plus parent147DB30.482s/17.11 exact-ID
cleanup passed with no concrete defect. Commit identities are recorded at closure
below. No live operator configuration, HTTP/UI/production wiring or publication claim.
F07b1 behavioracf7a9e1415e91290ad9829b789669574b6675e0 and documentation follow-up
96e29200460df7b6f3f220c24f7f3064bac5ab71 closed only the internal read model.
Parent owns refreshed mirrors; Gentle GLOBALOFF remains disabled/unmanaged.

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

One closed unit and one current plan checkpoint; future slices remain unreleased:
- [x] **F07b1 — Membership authorization read model.** Additive schema, immutable
  snapshot/pure default-deny policy, restricted fresh PostgreSQL read and extended
  runtime readiness. No administration endpoints or writes.
  Route: delegated direct; migration/security/readiness plus multiple non-trivial
  source/test files require a bounded writer and independent verification.
- [ ] **F07b2 — Central designation and future member administration.**
  - [x] **F07b2a — Authenticated initial-only designation (locally committed).**
    Real Entra operator validation, deployment-owned authorization and one atomic
    existing-member grant/revision/audit-outbox transaction; E1–E12 below.
    Route: delegated direct; security/migration/transaction plus multiple source
    files require bounded writer and independent verification.
  - [ ] **F07b2b — Recovery/removal/member mutations (future, not released).**
    Last-administrator/removal/recovery policy still needs a human decision.
    No automatic administrator seed, self-registration or activation is inferred.
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
Historical F07b1 read slice needed no bootstrap decision. Central initial designation
is now user-confirmed; recovery/last-admin policy remains outside F07b2a.


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

## Local work-unit delivery

Behavior commit acf7a9e1415e91290ad9829b789669574b6675e0:
`feat(authz): enforce scoped membership roles`.
Exact13 approved authored files, +1438/-9=1447 authored changed lines; no ignored
runtime/venv files staged. Nine verified migration/source/test blobs were identical
before staging, in index, in behavior commit and worktree. Cached diffcheck passed;
clean status observed immediately after behavior commit. No mutating hook/source
normalization, AI attribution, new dependency or remote operation.
Git's inherited automatic committer-identity and LF/CRLF warnings were retained;
no global identity/EOL changes or amend. Historical proof/failures above remain.
Small documentation follow-up records this actual behavior hash and updates only
current closure pointers; parent owns full refreshed administration/identity mirrors.
F07b2 first-admin designation/recovery and last-admin policy require human product
decisions before mutations. No automatic answer, seed, API or provisioning delivery.

## F07b2a: authenticated initial-only designation

Plan checkpoint writes ONLY this task and docs/changes/initial-admin-designation.md.
No source/test/build/install/container/commit occurs before parent full mirror gate.
Keep F07b1 IDs/proofs/RED/fixes/hash/stats above; no old feature history rewrite.

### Security and transaction contract

| Boundary | Accepted implementation plan |
|---|---|
| Entry | Internal service receives raw Entra access token plus typed org/member/operation UUID and expected revision; service itself calls actual EntraTokenValidator.validate_principal every attempt, including replay |
| Operator | Deployment-owned immutable exact issuer/tid/oid allowlist; each entry maps to one trusted internal actor UUID. Missing/empty configuration or no match denies before DB; no request actor, email, JWT roles, tenant-admin or first-login inference |
| Target tenant | Explicit immutable org→allowed target Entra tenant mapping, independently of global token tenant allowlist; missing organization mapping denies before DB. Existing membership identity must match its mapped tenant and exact canonical persisted pair |
| Target | Existing active membership in exact requested org and coherent bound Entra identity only. No identity/member creation, binding, membership status update, org activation or implicit credentials |
| Organization activity | An existing inactive org may receive the initial designation intent but remains inactive. Runtime access still denies; designation never activates it |
| Permanence | One append-only initial_admin_designations marker per org plus globally unique operation UUID; later role removal cannot reopen bootstrap |
| Replay | Fresh token/config authorization on every attempt. Same validated actor + operation + exact original org/member/expected revision returns stored original result even after response loss or later target changes, without new grant/revision/event; changed actor/payload or reused operation conflicts |
| Atomicity | First write is org/operation claim after scoped metadata lookup if required; unique constraints serialize competing initial designations. Lock/reload target membership with FOR UPDATE using only permitted revision UPDATE, validate binding/tenant/activity/revision and absence of ANY existing organization_admin role in org; insert admin role, increment revision, insert real audit-publication outbox in one transaction |
| Failure | Stale expected revision, already-designated org, existing admin, absent/nonactive/unbound/wrong-tenant target or event failure rolls back claim/grant/revision/outbox. No reopening, partial result, silent retry or fake publication |
| Audit | Fixed server-derived PF09 base event with actor_id from validated allowlist→internal UUID, actor_type deployment_operator, source server, event_type membership.initial_admin_designated, schema_version1, org/request/member resource IDs, success outcome, server timestamps and exact allowlisted metadata; no token/sub/email/raw claims |
| Result/errors | Frozen redacted result with org/member/operation/event UUID and committed revision, audit_publication pending. Fixed typed denied/conflict/unavailable errors, no PII/raw network/SQL exceptions or token logging |

Service configuration copies/freeze inputs; max64 operator entries, max256 org mappings,
max64 target tenants per mapping. Exact GUID/canonical issuer validation, duplicate
operator identities/ambiguous actor mappings rejected; one actor per verified tuple.
Empty/missing operator or tenant mapping denies before DB, without defaults. Request
UUID/type and positive integer expected revision validate before borrow; bool/noninteger/
nonfinite/oversized revision denied, max2**63-2 so increment remains positive bigint.
No API/user-supplied actor parameter or caller-constructed VerifiedPrincipal authority.
Actual validator is trusted composition; tests use real cryptography, not stub authority.

Permanent marker stores immutable original actor/request/target/targettenant/expected+result revision
and event reference; unique org and operation. Replay checks current orgtenant mapping
against stored server-derived targettenant before returning the original result.
Any preliminary target metadata read is reloaded under membership lock before grant.
Outbox uses fixed PF09 columns plus
bounded exact metadata shape and unique event/operation. Referential/deferrable
commit checks tie marker and event so a marker-only commit is not accepted. Outbox
publication/consumer/delivery state is future; INSERT is not claimed as publication,
provisioning or authorization of an external account. No UPDATE/DELETE or repair path.

### Database role/RLS and readiness

New0004 additive migration only; preserve0001–0003 file bytes. New NOLOGIN
forge_designator is not an owner/member/migrator/superuser/BYPASSRLS/DDL role.
Deployment owns LOGIN credentials/external pool. Strict live role/session/ownership/
membership/schema/ACL/column-ACL/context/autocommit checks on each borrow; no caches.

Exact privilege matrix: runtime SELECT on the existing five business tables only;
ZERO table/column privileges on designation/outbox and unknown Forge tables. Binder
keeps identities SELECT and existing pair-column UPDATE only, zero new access.
Designator SELECT on scoped org/target membership/target bound identity/admin-role
metadata; UPDATE(revision) only; INSERT organization_admin role only; INSERT marker/
outbox and SELECT exact actor/request replay only. No configuration-revision access,
identity/member creation, status/org mutation, UPDATE/DELETE audit or table-wide UPDATE.
Unknown/elevated grants fail closed; never grant runtime SELECT on all new tables.

Add role-specific designator policies plus restrictive designator scope where legacy
PUBLIC membership/org policies could otherwise OR-expand access; do not alter old
policy bodies/runtime semantics. Minimal existing invoker helper EXECUTE as required
by applicable old policies, no SECURITY DEFINER. Target-identity context is derived
from locked membership, so new identity policy need not query memberships and create
RLS recursion. Admin-role SELECT is org-scoped; INSERT only target/admin. Operational
RLS is exact org/actor/request/target with no context→no rows. Generic runtime fixtures,
prior restricted-writer probes and binder policies must preserve their semantics.

Extend clean-context checks for new designation GUCs. All local contexts/timeouts/
search_path restore after commit/rollback/error; no dirty outer transaction/savepoint,
autocommit false, pool reopening or process-global environment changes. Acquisition1s
(optional finite(0,30]), transaction statement3s/lock1s, migration lock2s/statement10s.
Bound checks precede float conversion; no giant-int OverflowError. Actual client18.4/
server17.11 remains owned-test evidence, not production TLS/compatibility readiness.

Runtime _ROLE_CHECK changes from all-table SELECT requirement to explicit five-table
positive and all other table/column zero-access matrix. Catalog-only readiness attests
exact new tables/constraints/owner/role/RLS/policy counts/role applicability/expressions,
plus marker-event linkage, designator privileges and binder zero access; extend role
policy-count checks deliberately without weakening existing checks or querying rows.
No service/pool/operator wiring added to runtime or HTTP; readiness is storage metadata,
not evidence that live operator configuration or admin UI exists.

### Acceptance (E1–E12 observed; F07b2a local delivery closed)

- [x] E1: Actual RS256 token validation each attempt, exact deployment operator→actor
  and org→targettenant configuration; empty/missing/invalid/unauthorized deny before DB.
- [x] E2: Existing active bound target only; exactorg/canonical pair/tenant, no fallback,
  creation/activation/status mutation. Inactive org stays inactive after valid intent.
- [x] E3: Permanent org+uniqueoperation marker, original-result replay with freshauth;
  changed actor/payload/operation reuse, stale revision and existing admin conflict.
- [x] E4: Claim/lock/reload/validate/grant/revision/event atomic; response-loss replay,
  audit failure rollback and no marker-only commit or partial writes.
- [x] E5: Concurrent different-target/same-org claim, exact replay race, suspension race
  and independent different-org operations produce only serial valid outcomes.
- [x] E6: Strict dedicated role/column matrix, narrow permissive+restrictive RLS,
  old PUBLIC context cannot broaden designator, no recursion/owner/DDL/membership.
- [x] E7: Runtime SELECT five tables/zero operational+unknown privileges; binder unchanged;
  readiness attests exact policies/schema/linkage/ACLs and fails weakened shapes.
- [x] E8: Fixed PF09 event actor/server timestamps/resource/metadata from verified config;
  no token/claims/email/privatekey/log leaks; publisher explicitly pending.
- [x] E9: Separate0004 fresh/populated/actual injected failure transaction probes;
  old0002/0003 probes byte-preserved and old data/constraints/policies/ACLs unchanged
  on rollback. Four migrations explicitly ordered in disposable fixture only.
- [x] E10: Meaningful real-RSA service and real-DB atomicity RED→GREEN; all211 baseline
  plus new applicable tests, compileall/pipcheck/diffcheck, no silent skips.
- [x] E11: Offline existing-tools wheel exactnewmodules/currentpostgres/staticassets,
  fresh import/resources proof, audit0004 source separately; no deps/install/network.
- [x] E12: README/neutralSpanishSDD/task correspondence, full parent mirror/readback
  before source; independent verification+parent spot before separate local commit
  authorization; actual commit/hash/stats and clean/protected-source proof afterward.

### Exact released edit surfaces

- migrations/0004_initial_admin_designation.sql
- src/forge/administration.py
- src/forge/administration_store.py
- src/forge/postgres.py
- tests/test_administration.py
- tests/test_postgres_administration.py
- tests/postgres_support.py
- tests/test_postgres_runtime.py
- tests/test_postgres_rls.py
- README.md
- docs/changes/initial-admin-designation.md
- odd/tasks/forge-administration.md
- .local/postgres-test/**
- .local/runtime-test/**

Twelve authored paths/two ignored outputs; no extra helpers, dependencies or .venv
writes. Protect migrations0001–0003, foundation/authentication/binder/authorization
readmodel/API/runtime/UI/manifest/harness script and prior proof. Test support may
add separate probe/fixture/context/owned designator LOGIN only after release; prior
probe functions must remain exact. No existing/external/production database access.

### Exact verification commands and original forecast

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_administration.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_authorization.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_foundation.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    ./.venv/Scripts/python.exe -m compileall -q src tests
    ./.venv/Scripts/python.exe -m pip check
    git diff --check

Use genuine ephemeral RSA signed tokens/public JWKS fake transport in-process,
including invalid signature/claims/expired/operator mismatch/replay reauthentication,
not mocked VerifiedPrincipal/authority. Owned cached Docker harness only, --pull=never,
exact own-ID cleanup; no external DB/pull/prune. Add durable actual SQL failure before
0004 COMMIT, prove INERROR→ROLLBACK/IDLE and complete prior rows/metadata/RLS equality.
Inject event INSERT failure after grant/revision then prove every write rolled back.
Exercise old readers/status after new migration and grants to operational/unknown
and column privilege contamination; old probes/scripts and actual API deny semantics
remain unchanged. Test invalid-token never borrows DB, down IDP typedredacted error,
concurrent response-loss/replay, target suspend ordering and no second event/revision.

Existing tools only offline staging under .local/runtime-test/package-src and child
TMP/TEMP=.local/runtime-test/tmp, explicit SystemRoot/PATH; copy source/manifest/README
without caches, then:

    ./.venv/Scripts/python.exe -m pip --isolated wheel --no-index --no-deps --no-build-isolation --no-cache-dir --wheel-dir .local/runtime-test/wheels .local/runtime-test/package-src

ZIP/importlib.resources/fresh child import verifies administration.py/store/current
postgres and three unchanged assets. Audit0004 separately (not packaged SQL claim).
No UI change/browser run expected; existing C10b certification limitations remain.

Forecast1800–2600 authored changed lines, 30–60 new meaningful tests estimated,
dominated by cryptographic/atomicity/concurrency/privilege/failure proof; exact counts
only after execution. ~400 is advisory, no code-golf/artificial file-type splits.
Existing feature-branch-chain local strategy: one coherent behavior/test/docs unit,
then small actual-hash documentation follow-up only after parent commit authority.
Verification roughly2–4minutes local resources, no external spending/download.
Rollback boundary is future F07b2a source/test/docs commit; DB recovery is separately
governed, no destructive downgrade/removal/last-admin policy supplied.

Next: parent refreshes its full current task mirror after local commit readback, then
selects future bounded work. No recovery/removal/last-admin decision is inferred.
No operator IDs/configuration credentials are requested at this internal test slice.
Later deployment owner supplies real allowlist/actor mapping/orgtenant config/pool;
HTTP/UI/consumer/recovery/last-admin/member lifecycle stay separately scoped.


### F07b2a observed writer proof (not delivery approval)

-266 applicable tests:147DB29.983s +16administration0.175s +6authorization0.003s
 +28runtime11.725s +38Entra0.995s +13domain0.001s +18HTTP0.492s; zero skips/failures
 in final runs. Baseline211 retained plus55 new tests. compileall and pipcheck exit0;
 diffcheck exit0 after final documentation readback. No source changes after
 these passing checks. Gentle remains disabled/unmanaged, no native approval.
- Owned cached server17.11; every harness run exact-ID cleanup confirmed. Separate
 0004 fresh/populated/failure evidence: (True,True,0,7,None,True),
 (True,True,3,7,None,True), (False,False,3,5,("22012",True),True). Actual failure
 before COMMIT proves INERROR→ROLLBACK/IDLE, no new role/tables and exact old rows,
 metadata/constraints/policies/ACL equality. Original0002/0003 probe function text
 and37 protected tracked Git blobs match baseline (Git clean-filter line endings).
- Real RSA service RED against deny-all, then realDB role/revision RED with actual
 authenticated service and deny-all store (109tests/1failure19.720s); initial
 GREEN109/19.901s. All authority/replay tests use actual Entra validator. Final DB
 includes response-loss and exact replay races, competing targets/orgs, target
 suspension, actual lock timeout, outbox SQL failure after visible own-transaction
 role/revision/claim writes, deferred marker-only rejection and rollback/recovery.
- Additional durable RED146/2failures28.071s exposed nullable helper proconfig
 comparison and new designation-GUC contamination accepted by ordinary runtime
 borrower. Corrected IS DISTINCT FROM and shared runtime guard;146GREEN29.231s.
 Literal-preserving exact helper sources/signatures/policy/constraint expressions
 now reject changed string whitespace; final147GREEN includes these controls.
- Intermediate nonpasses retained, not relabeled GREEN: first110RED also included
 accidental duplicate imported service-test discovery; initial30/1failure7errors
 came from generated SQL-string syntax plus expanded RLS metadata expectations;
 16service/3failures used exp NOW-1 inside existing30s skew (fixed test to valid
 expired chronology, no validator weakening);134DB/28errors was helper-name shadow;
 141DB/33failures1error came from test table UPDATE revoke also removing revision
 column grant (recovery now explicitly regrants it);146DB/1error held the sole pool
 borrow during context proof (released it before real probe);146/47failures24errors
 followed parameterization without escaping literal LIKE percent (fixed %%);
 111DB/1importerror placed a new method after main guard (moved guard). All corrected
 and complete final suites rerun. Initial wheel fresh-HTTP probe used nonexistent
 /api/runtime/status and got404; corrected existing /forge/v1/status passed.
- Offline staged wheel (no index/deps/build isolation/cache/install/download), exact
 all11 source modules +3 unchanged assets ZIP bytes and isolated fresh imports,
 importlib.resources and unconfigured /status +/forge/v1/status HTTP passed.
 Wheel SHA256 c7568016ff9a83fdb99cd5eccc257f760accb83c16e0afe4fb37b9c4dc1f3992;
 0004 separate source SHA256 4c458728d8b1cff92f2a449e5b128d7ac49c4f3a322d252bd47f7e04bcbf87d0.
 SQL is not claimed packaged. Existing TestClient httpx deprecation warning is
 historical library evidence, not a failure or authorization to install dependencies.
- Evidence logs/proof JSON are ignored under .local/runtime-test/f07b2a-*;
 final DB f07b2a-db-complete-fixed.log, six *-final.log files and wheel-proof.json.
 No running UI server launched; unchanged UI requires no new browser run. Existing
 C10b limits remain. README/neutral-Spanish SDD describe authority/privileges/pending
 publication and no admin-ready claim. Parent owns full mirror. Independent266+wheel passed without concrete defect;
 parent147DB30.482s/17.11 exact-ID cleanup passed. E12 commit/hash/stats/clean and
 protected-candidate confirmation are observed in local delivery below.


### F07b2a local work-unit delivery

Behavior commit885a940bcac4e87d8748069db32d3c01906478d3:
`feat(admin): designate initial organization administrator`.
Exact12 approved paths,2090 additions/27 deletions (2117 authored changed lines).
Independent266 tests + exact11module/3asset wheel/protected37/probes passed without
concrete defect; parent147DB30.482s, server17.11 exact-ID cleanup passed. All staged
blobs matched current files and behavior commit; nine verified behavior/test/migration
SHA256 values unchanged, no mutating hook drift. Behavior commit had clean status.
This small task-only follow-up records the actual hash/closure; parent receives
its own final hash and clean/protected readback separately. No source bytes changed.
Local feature-branch-chain strategy remains approved;400 advisory, no artificial
file-type split/code-golf. Rollback boundary is this exact work unit, not old
migrations/domain/API/authentication; DB recovery/downgrade policy is NOT provided.
E12/F07b2a close only internal initial designation. F07b2b/F07b3/F07b overall andF09
remain unfinished: no HTTP/UI/live operator wiring, publication/provisioning,
removal/recovery/last-admin assumption. Parent full mirror refresh follows readback.
Gentle remains disabled/unmanaged, no native approval; no remote/push/PR/merge.


## F07b2a-http child checkpoint

Initial-only HTTP adapter is tracked in odd/tasks/forge-initial-admin-http.md
with docs/changes/initial-admin-designation-http.md. Parent mirror readback released
implementation; writer candidate passed 296 tests (266 rerun baseline plus 30 new).
Independent 296-test verification and parent 21-HTTP spot passed; local work-unit
commit is authorized. Exact identity/closure is recorded in the child task.
This does not release recovery, removal or reassignment policy. Existing F07b2a
history and proof remain unchanged; parent owns the full mirror refresh.
