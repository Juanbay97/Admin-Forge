# Forge server-owned model catalog

## Outcome and current boundary

Define a pure immutable organization-bound alias catalog using PF-05 and PF-10.
M1/A/B/C1/C2 are independently verified: immutable catalog storage, scoped
transaction authority and the internal authenticated atomic publisher are complete. Inference, public API,
profile projection and coordinated runtime rollout remain pending.
Current bootstrap remains unchanged. Dedicated catalog snapshots and an active
catalog pointer exist; configuration revisions do not yet expose that publication.
Private catalog data and internal_settings must never leak into public projection.

## Tasks

- [x] M1 — Catalog domain and trusted-input validation (independently verified).
  Route: delegated direct; new domain, fixture tests and recovery doc. Forecast
  350–650 authored lines, <=800 unit. Immutable UUID-bound routes and aliases,
  verified capability evidence, conservative fallback intersection and exact alias
  lookup. No URL, API key, employee-supplied route or physical-model mapping input.
- [ ] M2 — Verified router adapter input.
  Route: delegated direct when separately released; actual authorized router
  inspection must supply evidence. Constructing a VERIFIED fixture proves nothing
  about OmniRoute and does not authenticate the publisher.
- [x] M3 — Internal scoped publication and immutable storage.
  Route: delegated direct; A/B/C1/C2 implement versioned immutable payloads,
  locked organization_admin authority, replay/CAS and atomic pointer/event/ledger.
  Production composition, exact readiness and the scoped HTTP route remain pending.
- [ ] M4 — PostgreSQL read projection and bootstrap integration.
  Route: delegated direct after publication contract; no private settings leak.
- [ ] M5 — Forge-bearer inference enforcement.
  Route: delegated direct; validate exact published alias and member authority,
  enforce modality and policy across every eligible fallback. No bypass by physical
  model names. This unit's exact lookup is not member authorization.

## M1 field contract and acceptance

UUID organization_id/router_binding_id correlate every evidence route to its
snapshot. Each alias has a nonempty tuple of uniquely identified fallback routes.
Evidence carries route_id/evidence_id and explicit Verification.VERIFIED, never
inferred from model names. Current modality vocabulary is text/image for inputs
and outputs. Capabilities require immutable nonempty frozensets, explicit boolean
tools/streaming and positive strict integer context/output limits (output <= context).
Unknown capability values cannot become advertised support.

Alias capabilities are the intersection of all represented fallback modalities,
all-route tools/streaming support and minimum limits. Empty common modalities
reject the alias. Alias identifiers are exact lowercase stable names; snapshots
require a nonempty immutable tuple with unique names and a positive revision.
All construction boundaries validate types without coercion; all errors are fixed
messages. Public projection contains only organization_id, revision and explicit
alias capability fields. No binding, routes, evidence, secrets or invented policy,
brand or skill revisions. Projection is a pure data contract, not a deployed JSON API.

## M1 exact allowed surface (historical)

- src/forge/model_catalog.py
- tests/test_model_catalog.py
- odd/tasks/forge-model-catalog.md

## M1 delivery and verification (historical)

Backend root: N:/Proyects/forge/.worktrees/tenant-storage; existing local feature
chain feat/forge-s3-outbox-recording at ac16a217. Client is read-only and untouched.
Preexisting dirty documents/specs/.gitignore remain; dynamic CodeGraph index is
excluded from byte baselines. CodeGraph and current foundation/API fixtures were
inspected before implementation. RDD disabled/unmanaged. No DB/network/remote,
staging, commits, dependency installation or publication storage. Migration slots
0006–0009 are reserved elsewhere and are not used. Identity configuration remains
commit-pending; do not invent it.

Test first; new-module absence alone is not meaningful behavioral RED. Run actual
stdlib domain fixtures, then existing foundation and injected-transport API tests:
- .venv/Scripts/python.exe -B -m unittest discover -s tests -p test_model_catalog.py -v
- .venv/Scripts/python.exe -B -m unittest discover -s tests -p test_foundation.py -v
- .venv/Scripts/python.exe -B -m unittest discover -s tests -p test_api.py -v
- git diff --check

M1 closed: independent 48 passed (17/0.012s, 13/0.004s, 18/0.838s),
parent domain17 passed0.009s; sandbox API needed a narrow elevated retry.
C2 independent closure is recorded below; no next source unit is released here.
HTTP, projection and matching runtime rollout remain pending.

## M1 observed proof

- Test-first exception: the initial command failed with ModuleNotFoundError for the
  new module (1 loader error, 0.001s). This is not behavioral RED; no existing
  catalog implementation or relevant runnable behavior existed before this unit.
- Catalog: 17 passed in 0.013s; foundation: 13 passed in 0.004s.
- API: sandbox attempt stalled on its first TestClient case and was interrupted
  (exit 1); the same narrow command elevated passed 18 in 0.564s. Total completed
  suites: 48 passed, zero skipped. Existing Starlette/httpx deprecation warning
  remains a dependency follow-up, not a reason to upgrade in this unit.
- git diff --check passed; its existing .gitignore LF/CRLF warning is unchanged.
- All 75 preexisting protected backend files matched SHA256 byte-for-byte:
  b0576ca3ed5dd6f668ef7f49b6438528b4cf5010448c636d371fad873d09ae9d.
  All 1439 captured client files matched their unchanged aggregate:
  a0ee62561f8d435d4de5756b04db2035ed8330899ffc9c845bb92447d07983d9.
- No router inspection, real credentials, DB, HTTP catalog, publication, inference,
  app run or remote checks occurred. Runtime harness is N/A for this pure domain.
  Bootstrap and existing source/tests remain byte-identical.
- Rollback boundary is only the three named new files; no existing behavior needs
  rollback. No stage/commit was attempted. Parent independent review is next.

## A — Immutable unpublished persistence (verified)

- [x] A1: versioned canonical private codec and transaction-bound insert/read.
- [x] A2: additive0010 schema and actual owned PostgreSQL migration/storage proof.
- [x] A3: regression, preservation, full mirror and independent handoff.
Route: delegated direct, multi-file behavior/tests. Forecast <=800 authored lines.
Existing feature-branch-chain; no staging/commits, identity remains pending.

Exact A surfaces:
- migrations/0010_model_catalog_snapshots.sql
- src/forge/model_catalog_store.py
- tests/test_model_catalog_store.py
- tests/test_postgres_model_catalog.py
- tests/postgres_support.py
- odd/tasks/forge-model-catalog.md

The immutable row key is organization/binding/catalog revision. Payload is canonical
UTF-8 JSON text with schema_version=1 and SHA256; reads check hash, canonical bytes,
exact field sets and reconstruct the strict domain with correlated row identifiers.
Write boundary accepts CatalogSnapshot only, not caller blobs. Duplicate keys always
conflict without overwriting. Internal writer has SELECT/INSERT only, FORCE RLS by
explicit organization context; no member/runtime/designator access or role inheritance.
Database owner/administrator corruption is outside immutability claims, but reads
must reject malformed stored payload. No URLs/secrets, publisher grants, active
pointer, configuration revision change, bootstrap integration or actual router proof.

Migration0010 is applied and removed only by catalog-specific owned fixtures, not
by default DatabaseFixture setup. Prior migrations/readiness remain unchanged.
Populated upgrade and injected rollback snapshot legacy records and policies.
Caller owns the explicit transaction; storage never commits or authenticates.

Checks: pure test_model_catalog_store.py, domain test_model_catalog.py, full owned
scripts/test-postgres.ps1 (cached image, --pull=never, loopback, exact-ID cleanup),
git diff --check and protected backend/client hashes. Initial missing-module errors
are test-first exceptions, not behavioral RED. B/C require a separate release and
coordinated new outbox schema/runtime rollout; no publication is authorized here.

### A observed proof and handoff

- Codec8 passed0.010s; domain17 passed0.069s. Final normalized owned PostgreSQL
  suite175 passed39.956s (including9 new catalog cases), zero failures/skips,
  PostgreSQL17.11. Total final commands:200 passed. Exact-ID cleanup confirmed.
- First codec command had one missing-module loader error0.001s: test-first
  exception, not behavioral RED. First full PG run175/41.061s had10 fixture errors
  because the new migration had an extra terminal newline. Strict fixture check
  was preserved; corrected0010 passed175/41.761s before final normalization/rerun.
  All three completed harness runs confirmed exact-ID container removal.
- An intentional interruption happened before the first correction/retry. Read-only
  reconciliation found no active owned harness; old Oct3 scratch directories were
  untouched. Initial sandbox doc/Git/process-access failures required narrow
  escalation, not ownership/configuration changes. Existing httpx deprecation and
  Git LF/CRLF warnings remain. New fixture EOF blank line was corrected before the
  final full run; final diff check passed.
- Protected backend76 aggregate remained
  d4e5498bc3ff98cd658033aa6025ef3615cbd4952d799d9e0cea9fff2e1eae94.
  All original35420 postgres_support.py bytes remain an exact prefix (SHA256
  9fe8837c48ab2eae11855e84a92c4e9c2f0d449bf4b4febae1f08f1dc64fe103).
- This writer made no client writes. Client1439 aggregate changed across the long
  interruption from a0ee6256... to a10ac02094ea2dc4dd38ef6b7905390b6b02a8b3fdcfbfa6a68bf4a8bd9e99f9;
  first11 retained chunks match, final chunk differs. Parent reports authorized
  managed-profile/native-readiness task bookkeeping; both current task hashes match
  that report. Chunk-only baseline cannot independently prove these are the only
  changed files, so whole-client byte identity is not claimed for A.
- SQL checks row correlation, hash and envelope; the typed adapter revalidates the
  complete domain and canonical bytes. A privileged raw SQL writer can damage
  deeper payload structure; read denial is tested, not database-level full-schema
  enforcement. SHA256 is integrity detection, not authenticity or encryption.
- Independent verification pending. No publication, member grants, live router
  verification, pointer changes, stage/commit or B/C implementation occurred.

### A independent closure

Independent verification passed200 checks: codec8/0.018s, domain17/0.022s,
PostgreSQL175/39.737s on17.11 with exact-ID cleanup. Parent codec8 passed0.020s.
Six candidate hashes and protected76 matched. Coverage limitation: A populated
upgrade seeded initial-administration data but generic outbox_events stayed empty;
A does not prove preservation of populated generic outbox rows.

## B — Publication storage security (verified)

- [x] B1: dedicated publisher role, correlated pointer and event-type separation.
- [x] B2: actual PostgreSQL isolation, privilege, migration and rollback proof.
- [x] B3: regressions, preservation, full mirror and independent handoff.
Route: delegated direct; schema/security and multi-file tests. Forecast600–780
authored lines, <=800 unit; local feature-branch-chain, commits pending identity.
RDD disabled/unmanaged; no staging, commit, live DB, remote, provider or client edits.

Exact B surfaces:
- migrations/0011_model_catalog_publication.sql
- src/forge/outbox.py
- src/forge/postgres.py
- tests/test_outbox.py
- tests/test_postgres_catalog_publication_schema.py
- tests/postgres_support.py
- tests/test_postgres_runtime.py
- tests/test_postgres_rls.py
- odd/tasks/forge-model-catalog.md

0011 follows explicit0010; default fixtures remain0001–0005. A NOLOGIN/NOINHERIT,
nonowner, nonbypass forge_config_publisher gets only scoped private snapshot reads,
active-pointer SELECT/INSERT/UPDATE and publication-event INSERT. No role membership,
human publication permission or deployment-operator authority is derived.
Pointer binds organization/router/catalog revision to an immutable snapshot and a
matching model_catalog.published event. Catalog revision is not a fabricated
configuration, brand or policy revision. Existing event writer cannot insert the
new event type; publisher cannot insert old event types or modify snapshot bytes.

Coordinated rollout is required: existing exact readiness must reject0011, with
no auto-detection or relaxed constraint acceptance. No new positive runtime
attestation or composition opt-in is implemented in B; that matching runtime is a
separate prerequisite before deployment. Existing0005 readiness stays exact.
The feature remains inactive until C supplies explicitly authorized transactional
publisher behavior; raw fixture SQL is not a production operation or public API.

Tests first: runnable event acceptance and migration-contract assertions must fail
before implementation. Actual owned PostgreSQL tests cover cross-org/context/FK,
roles and drift, unchanged old readiness and safe new-schema denial, caller rollback
and populated migration upgrade/injected failure including a nonempty generic outbox.
Run test_outbox.py plus full scripts/test-postgres.ps1 (--pull=never pinned image,
loopback, exact owned-ID cleanup), and git diff --check. No dependencies installed.

### B observed proof and handoff

- Behavioral RED: the new publication Event failed in the existing validator;
  test_outbox.py ran4 with1 error/0.024s. Final GREEN4 passed0.006s.
- Final real PostgreSQL suite187 passed44.116s, PostgreSQL17.11, no failures/skips;
  includes12 new publication cases. Combined final commands:191 passed,13 new.
  Earlier complete runs passed186/41.485s and187/43.399s as coverage was extended.
  All three owned harness runs confirmed exact-ID container removal.
- Actual cases prove scoped reads/inserts/updates, composite snapshot/event
  correlation, separate writer event types, restricted role attributes/ownership
  and privileges, no role inheritance, caller rollback, and exact old readiness
  positive before/after0011 fixtures but false on0011 and tested drift.
  No new-runtime positive readiness is claimed or enabled.
- Populated upgrade and injected migration failure retain initial-administration,
  generic outbox and private snapshot records; failure leaves no pointer/role.
  The fixture restores only its own0011 changes, then removes its owned0010 objects.
- Source postgres.py and existing runtime/RLS tests are byte-unchanged.
  The pre-B37391-byte helper prefix was restored and matches its prior SHA256
  6e0d5f2123f0277c3c9d0704371c0ecc0702ce21644eef2ce904ba3520bd3331.
  A whole-file newline rewrite was detected during preservation checking, corrected
  to the proven original bytes, and the full suite rerun on the final bytes.
- Sandbox new-file access and an overlong command failed before source creation;
  bounded elevated writes succeeded. Existing httpx deprecation and Git CRLF
  notices remain nonblocking. No ownership/configuration changes were made.
- Protected backend75 raw hashes remain at
  9aff5d54b8d6ff5445475b46979a64a36a08f4b934adeb7de3d1d0cfc076c741.
  Frozen client1435 protected hashes plus all5 C3c1 candidate hashes match exactly.
  Independent verification and parent spot check are pending.
- No service authorizes a human publisher yet. Pointer and event must match, but
  schema alone does not supply concurrency/monotonic publication policy, guarantee
  an event always has a pointer, or verify actual router evidence. C must own those
  operation semantics. No existing configuration/brand/policy revisions changed.
  Migration0011 must not be deployed independently of matching runtime rollout.


### B independent closure

Independent191 passed (outbox4/0.005s, PostgreSQL187/43.294s on17.11,
exact-ID cleanup); parent outbox4/0.006s passed. Six candidate and75 protected
hashes plus helper prefix matched. B nonempty generic-outbox upgrade coverage
closes A's P3 coverage limitation; A historical evidence above remains unchanged.

## C1 — Authority locking and immutable operation ledger (independently verified)

- [x] C1a: additive0012 hardened fixed authority helper and bound replay ledger.
- [x] C1b: real PostgreSQL ACL/RLS, populated migration/rollback and lock ordering.
- [x] C1c: full owned regression, preservation, mirror and independent handoff.
Route: delegated direct; SQL security, fixtures and recovery documentation.
Forecast550–800 authored lines; existing local feature-branch-chain, no Git writes.
Exact surfaces:
- migrations/0012_catalog_publication_authority.sql
- tests/test_postgres_catalog_publication_authority.py
- tests/postgres_support.py
- odd/tasks/forge-model-catalog.md

0012 follows0011;0006–0009 remain reserved. No prior migration is edited. A dedicated
NOLOGIN/NOINHERIT/nonbypass helper owner has only scoped authority-table access,
no table ownership or caller role membership. Fixed fully qualified SQL under
pg_catalog search_path, PUBLIC execution revoked, publisher-only execution.
Helper locks organization, membership, canonical Entra identity and organization_admin
grant in that order, reloading active state; locks last through the caller transaction.
Bearer provenance belongs to the future trusted service, never to caller UUIDs/GUCs.
Publication must lock authority before operation/pointer and commit all effects
atomically; whichever transaction obtains conflicting authority locks first defines
revocation/publication order. No deployment-operator grant or fake authentication.

Append-only ledger binds global operation UUID, organization, actor membership,
router binding, expected/target catalog revisions, canonical snapshot checksum and
resulting publication event. Scoped reads/inserts only; no mutation/event-read grants.
No arbitrary blob, member permission, runtime readiness or HTTP endpoint is added.
Existing old-runtime readiness must remain fail-closed on the opt-in new schema.
Migration is not independently deployable; C2 must implement trusted authentication,
transactional authorization, replay comparison, CAS/pointer/event/ledger writes and
error redaction. C3 read projection and later rollout remain separately pending.

Run actual owned scripts/test-postgres.ps1 with cached pinned image, --pull=never,
loopback and exact-ID cleanup; no ambient/live DB. Observe a meaningful absent-helper
contract RED before migration, then real positive/negative identities, role attributes,
ACL/search-path/ownership/RLS, immutable ledger correlations, populated upgrade and
injected rollback. Two-connection tests prove blocking/revocation for organization,
membership, identity and role deletion. Preserve old fixtures/helper prefix and all
unrelated raw hashes. Final diff check, full mirror/readback and independent handoff.


### C1 observed proof and handoff

- Actual RED: existing0011 fixture returned no authority helper. The full owned
  suite ran188/41.878s with exactly that new assertion failing;187 existing passed.
- Final normalized full scripts/test-postgres.ps1:201 passed44.647s on PostgreSQL17.11,
  including14 new C1 tests, no failures/skips; exact owned-ID cleanup confirmed.
- Intermediate runs200/40.268s had5 new fixture errors (missing explicit transaction,
  nested legacy seed commit, and unsupported column-ACL DELETE query). Next run
  200/44.853s had1 populated-fixture resource/revision collision. Corrected only new
  fixture boundaries/introspection/resource identity; SQL constraints and prior
  tests were not weakened. All four harness runs confirmed exact-ID removal.
- Real two-connection tests observe pg_blocking_pids, not timing-only assumptions:
  organization/member/identity/grant locks persist until transaction end; prior
  committed revocation denies. Additional NOWAIT probes prove each predecessor
  is held before waiting on the next authority row. Direct identity deletion first
  blocks, then existing membership FK denies; valid identity revocation removes
  dependent membership/grant rows within its transaction before deleting identity.
- Positive/negative Entra authority, fixed helper owner/search path/ACL, no publisher
  table mutation or event reads, restrictive owner write denial, immutable replay
  correlations/global conflicts/scoped reads, caller rollback and populated
  upgrade/injected failure passed. The last includes real nonempty generic outbox,
  snapshot and active-pointer rows. Old readiness is positive before/after fixtures
  and negative on0011/0012; no relaxed/new positive attestation was introduced.
- Protected82 backend raw hashes remained
  cbe291044f48aa1aa53c7941b84860573fd34fc22877975859cd14e428cfa03e.
  All pre-unit40805 helper bytes remain an exact prefix, SHA256
  b407c5894fddff3280378422cd67293bff724e1bdf236269b9ed3cf8c8809b52.
  Client source and docs were not written in this unit.
- Final diff check passed with preexisting LF/CRLF notices. Sandbox Git inspection
  initially could not resolve the worktree; read-only elevation succeeded. Two
  orchestration syntax errors and a truncated read-only JSON parse caused no file
  mutation. Existing Starlette/httpx deprecation warning remains nonblocking.
- C1 is a storage primitive, not a publisher operation: a trusted publisher DB role
  can still issue raw SQL without calling the helper. C2 must verify bearer identity
  on every attempt/replay, execute the ordered locked transaction, compare replay
  payloads, enforce CAS and atomically persist pointer/event/ledger with redacted
  failures. Administrative DB corruption and deadlock-free arbitrary external
  mutation ordering are not promised. Deployment/matching readiness remain pending.
  Independent verification and parent spot check are next; no stage/commit occurred.


### C1 independent closure

Independent201 passed39.684s; parent full PostgreSQL201 passed41.574s on17.11,
both exact-ID cleanup. Candidate/protected preservation confirmed; C1 is verified.

## C2 — Authenticated atomic publisher (independently verified)

- [x] C2a: exact models.publish policy and typed authenticated service boundary.
- [x] C2b: restricted transaction, authority reload, replay, CAS and atomic writes.
- [x] C2c: unit/owned PostgreSQL acceptance, preservation, independent verification
  and parent spot check.
Route: delegated direct; service/store, policy, fixtures and recovery documentation.
Forecast600–800 authored lines; local feature-branch-chain, commits pending identity.
Exact surfaces:
- src/forge/catalog_publication.py
- src/forge/catalog_publication_store.py
- src/forge/authorization.py
- tests/test_catalog_publication.py
- tests/test_authorization.py
- tests/test_postgres_catalog_publication.py
- odd/tasks/forge-model-catalog.md

Every attempt, including replay, calls the actual validate_principal -> VerifiedPrincipal
contract. Explicit injected fixture verifiers test only this boundary, not real Entra.
The existing PostgresAuthorizationReader supplies a trusted membership prelookup from
fresh principal.identity and requested organization; its roles/activity are never the
final authorization. This costs an extra read/roundtrip and requires explicit separate
readonly-reader/restricted-publisher composition. No ambient pool or request actor.
C1 revalidates exact principal/member/org/grant under locks; stale/permissive prelookup
cannot authorize. Only active organization_admin grants exact models.publish.

Borrow must be idle/autocommit and restricted publisher role with no elevated or
unexpected grants/context. Bound local timeouts/search path and fresh principal GUCs.
After locked authority, validate canonical stored snapshot/hash and exact replay.
Replay returns its original result even after pointer advance; revocation denies first.
New operation CAS requires target=expected+1, then atomically event, pointer and ledger.
Global operation conflicts remain redacted; any failure rolls back and connection
state is reusable. No HTTP, runtime composition/readiness relaxation or schema change.

Test first: real existing permits must reject models.publish before policy change.
Absent new service is not behavioral RED. Run test_catalog_publication.py and
test_authorization.py plus full owned scripts/test-postgres.ps1 (cached pinned image,
--pull=never, loopback, exact-ID cleanup), final diff check/protected hashes/full mirror.
Cover replay/CAS/changed payload and actor/cross-org collision, revocation between
prelookup and helper, concurrency, response loss, staged SQL failure rollback,
dirty/elevated/nonidle borrows and sanitized errors. Client remains frozen.


### C2 observed proof and handoff

- Final normalized unit7 passed0.490s; authorization7 passed0.002s; complete owned
  PostgreSQL214 passed43.068s on17.11, exact-ID cleanup. Total228 checks passed,
  including21 new (7 service,1 policy,13 PostgreSQL), no final failures/skips.
- Behavioral RED: authorization7/0.002s had1 expected models.publish denial failure.
  An extreme integer timeout regression ran7/0.540s with1 OverflowError; bounds
  now precede float conversion. A real grant-option denial regression ran214/43.989s
  with1 failure; table/column delegatable privileges are now explicitly rejected.
  Initial PostgreSQL212/43.716s passed before these edge additions. All three owned
  harness runs confirmed exact-ID removal. New-module absence was not labeled RED.
- Actual restricted publisher pool plus explicit readonly authorization pool passed
  new publication, stale CAS, exact replay after pointer advance, changed actor/hash,
  global cross-org operation conflict, response loss, identical/distinct concurrent
  requests, revoked stale prelookup and revocation between discovery/locked helper.
  A real blocked concurrent grant revocation commits before the service reload denies.
- Faults after actual event/pointer/ledger INSERTs roll back all effects; the same
  physical connection is clean and reusable. Nonidle/nonautocommit, dirty context,
  elevated role, extra reads and delegatable rights deny. Corrupt canonical stored
  domain fails closed before writes. Every valid attempt/replay calls the explicit
  fixture verifier again; these are not live Microsoft authentication tests.
- The actual EntraTokenValidator.validate_principal contract is reused through a
  narrow trusted protocol; there was no existing BearerVerifier symbol. Membership
  discovery is not authorization, and the request has no actor field. Helper proof
  constructs only the locked required organization_admin grant for models.publish.
- Protected83 backend raw hashes match:
  b6db1336623f3b2afdaa73158349ed104f643b4758e46dad4a48e5a2ba0e575e.
  Existing authorization bytes match after reversing only two intended substitutions;
  the entire prior authorization test byte prefix is intact. No migration, existing
  helper, runtime/API, client or unrelated dirty-file edits. Final diff check passed;
  existing Starlette/httpx deprecation and Git CRLF notices remain nonblocking.
- C2 is not externally wired or deployable alone. Matching exact runtime readiness,
  composition/provisioning, published-profile reads, HTTP boundary and live verifier/
  router acceptance remain pending. Independent closure below completes this
  internal service/storage checkpoint, not deployment.
  No stage/commit, credentials discovery, external provider, remote or installation.

## C2 independent closure and next chain

Independent verification passed228 checks: service7/0.534s, authorization7/0.003s,
PostgreSQL214/44.851s on17.11 with exact owned-container-ID cleanup. All seven
candidate hashes and83 protected hashes matched; no blockers were found. Parent
service7 passed0.933s. Fixture verifier results are distinct from live Entra proof;
no HTTP, public projection, positive runtime attestation or live OmniRoute claim.
Commits alone remain pending configured Git identity; no identity is invented.

Next bounded units, still pending:
1. Production verifier/runtime composition, positive exact schema readiness and a
   scoped publication HTTP route; preserve fail-closed coordinated rollout.
2. Verified catalog ingestion (M2) and public effective-profile projection (M4),
   then Forge-bearer inference enforcement (M5); no invented revision values.
3. Desktop browser/callback and token exchange, lifecycle/forwarding, managed UI,
   authorized end-to-end checks and packaging; no UI or ready-installer proof yet.

This passive closure reruns no functional tests and changes no source or schema.
Historical writer/independent counts above retain their original scope.
