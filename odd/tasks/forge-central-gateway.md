# Central organization gateway configuration

## Outcome and boundary
Forge administrators configure an organization gateway centrally so employees ultimately need only genuine Forge login. This new feature does not activate the running durable demo or change its schema, data, key shape, migration manifest, default/native guards, or account readiness fingerprint. Unit1 is protected configuration/API only: no remote calls, credential validation, catalogue publication, inference, browser UI, installs, commits or review lifecycle. Saved means SAVED_UNVERIFIED, never gateway-working.

Route: delegated direct, single writer; multiple non-trivial security/store/API/test files require bounded implementation. Five units preserve a recoverable feature identity. Local feature-branch-chain is the previously approved strategy; no push/merge. Author identity remains unresolved, so commits are explicitly deferred. Forecast full feature5000–8000 authored lines, Unit1 approximately1000–1500;400lines is advisory, not code-golf.

## Contract
- GET/PUT `/forge/v1/orgs/{organization_id}/gateway` require genuine live Forge session and freshly locked active same-org administrator. Request role/header claims never authorize.
- Optional unconfigured service fails503. Fixed deployment endpoint is `https://ia.prometheonlab.com`; clients cannot submit arbitrary origins. Bounded write-only key and expected_revision support CAS; redacted response exposes only status/revision/endpoint, no token/cipher/diagnostics.
- Separate explicit Fernet key binds ciphertext to organization, generated bindingID, revision and endpoint. No defaults, ambient key discovery, repr/log/audit secrets, remote verification, or employee cipher access.
- Additive0015 uses dedicated function-only nonbypass service role and NOLOGIN authority, FORCE RLS, transactional fresh session/admin locks and minimal grants. Logout/suspension/role revocation cannot be bypassed by a prior Python snapshot.
- New opt-in gateway account readiness attests reviewed0001–4+0013–15 exactly using a static build/test artifact, never runtime trust-on-first-use. Legacy AccountReadiness remains unchanged and failsclosed for the additive profile.

## Stable units
- [x] CG1 Protected configuration/domain/encryption, restricted PostgreSQL store/migration, exact readiness, genuine account app GET/PUT API.
- [x] CG2 Owned-account catalogue publication reusing existing catalogue semantics; do not forge Entra Principal.
- [ ] CG3 Central Forge-bearer text inference and explicit durable composition/upgrade (complete only after CG3a and CG3b).
  - [x] CG3a Protected central text-stream API/service and new exact schema profile.
  - [ ] CG3b Explicit durable deployment composition/upgrade implemented and self-verified; independent retained-container lifecycle remains partial/pending.
- [ ] CG4 Real administrator setup and login-only client bridge.
- [ ] CG5 Prebuilt launch and actual end-to-end proof.

## CG1 acceptance/checks
- [x] CG1.1 Meaningful runnable authenticated HTTP RED→GREEN plus key protection/CAS coverage.
- [x] CG1.2 Genuine PostgreSQL account composition: save/redacted/reopen, member/crossorg/suspended/revoked-session denial, staleCAS/race/rollback, wrongkey/binding substitution rejection.
- [x] CG1.3 Function-only role isolation; employee/directtable denial; exact ACL/RLS/function/authority drift failsclosed; owned fixture cleanup.
- [x] CG1.4 Pure gateway/config/API tests, existing accountAPI regression, focused owned digestpinned pullnever PostgreSQL runner, syntax/diff/whitespace observed.

Authorized Unit1 surfaces: migrations/0015_gateway_configuration.sql; src/forge/gateway_configuration.py; src/forge/gateway_configuration_store.py; src/forge/gateway_configuration_readiness.py; src/forge/account_api.py; tests/test_gateway_configuration.py; tests/test_gateway_configuration_api.py; tests/test_postgres_gateway_configuration.py; tests/postgres_support.py (new opt-in helper only); docs/changes/central-gateway.md; this task.

## Progress and next step
CG1 implemented and self-verified, not integrated/deployed or committed. CodeGraph returned the actual account/session/admin lock flow. Existing account_store role whitelist, legacy readiness profile and running durable demo are unchanged. Parent reports independent CG1 verification30checks PASS and parent6 domain tests PASS. CG2 implemented and independently verified after deadline correction; CG3a is implemented/self-verified with independent checking pending. CG3b–CG5 remain pending.


## CG1 observed verification and frozen handoff

- Meaningful HTTP RED: actual existing create_account_app returned404 instead of required401 for missing-auth GET/PUT (2failures,2.519s). Domain cipher/CAS tests subsequently passed; no separate cipherRED is claimed. Initial task print hit console cp1252 after successful UTF8 write; actual file/full mirror3170 matched.
- Final pure commands (local `.venv/Scripts/python.exe -B -m unittest discover -s tests`): `-p test_gateway_configuration.py -v`6pass0.005s; `-p test_gateway_configuration_api.py -v`7pass0.893s; `-p test_account_api.py -v`10pass0.374s. No new installation; Starlette/httpx deprecation warning retained, no dependency change.
- Final actual `& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_configuration.py`:7pass13.596s,exit0,PostgreSQL17.11; digestpinned pullnever owned container removed with exact-ID absence readback. Real HTTP includes genuine SessionService/accountAPI redacted save/get, member/crossorg/suspended denials, bootstrap200, stale409, logout204 then revoked401. Store tests cover role revocation/account session revalidation, CAS concurrent one-success/one-conflict, transactional rollback, wrongkey/binding substitution, direct-table/wrongrole denial, migration rollback and ACL/RLS/function/authorityLOGIN drift. Reopened service uses the same durable PostgreSQL row/key; no active demo access or network request.
- Earlier PostgreSQL failures preserved: first7errors from installer grant on an existing authority-owned function; corrected only exact trusted-installer grants. Subsequent42501 came from baseline PUBLIC membership policy's identity-table ACL dependency. New authority's broad lookup was replaced with narrow gateway_resolve_admin under established enrollment authority, with no new identity/business-table grants. One rollback test initially expected raw RuntimeError although the store deliberately sanitizes it; corrected to GatewayUnavailable while preserving rollback assertions. Readiness intentionally stayedfalse before static final-profile capture, causing three expected pending-artifact failures. Final GREEN replaces those incomplete proofs, not their history.
- Reviewed static PostgreSQL17 exact profile: `5c5e2af1c728874e1478c5bb3c7d969f599908d75fad3f35fcd78bdfb25e68c7`, derived only from pristine owned reviewed0001–4+0013–15 fixture, never runtime learned. Legacy AccountReadiness still rejects0015; protected profile/source unchanged.
- Check-only Python compile (no pyc writes), diffcheck and explicit authored whitespace across all11surfaces pass. Existing dirty work preserved; HEAD numstat includes earlier work, so no misleading whole-file attribution. New surfaces about700lines plus bounded accountAPI/helper additions; forecast remains advisory. Accounts3320 stillPID23940; no migration/restart/data changes to it.
- Historical CG1 frozen handoff: independent verification was pending then and subsequently passed30checks as recorded above. Commits (identity unresolved), whole baseline regression, central inference, durable upgrade, real administrator/clientbridge and prebuilt/browser E2E remain pending. Saved configuration is SAVED_UNVERIFIED only.

## Next-unit candidate seams (read-only locator, not write authority)
CG2 will need exact mapping of `src/forge/catalog_publication.py`, `src/forge/catalog_publication_store.py`, `src/forge/model_catalog.py` and `src/forge/model_catalog_store.py`, existing SQL0010–0012 catalogue authority and genuine owned-account identity routing. Derive additional exact surfaces after inspection; do not mutate existing Entra-only Principal contracts or reserved/previous migrations implicitly.


## CG2 authorized discovery and catalogue publication

Route: delegated direct, one writer. Reuse actual snapshots, active pointer, publication operation ledger and outbox; no Entra identity fabrication or alternate silo. This coherent unit includes additive0016, runtime HTTPX dependency declaration (installed version unchanged), genuine account API/service, unknown/unverified capability codec v2 and bounded adapter/real PostgreSQL tests. Forecast CG2 approximately1400–2200 authored lines; full feature revised5000–8000 for the real atomic publication/security/verification closure.400lines remains advisory, no artificial split or minification.

- [x] CG2.1 Meaningful RED→GREEN; preserve verified v1 encoding while adding explicit unknown/unverified v2 capability roundtrip. IDs-only discovery must not invent modalities/context/tools/vision/streaming.
- [x] CG2.2 Admin-only refresh: bound-key decrypt, fixed HTTPS /v1/models, trust_envFalse/no redirects, finite connect/read/write/pool/total time, byte/model-ID bounds and redacted errors. No network call under database locks; current session/admin/gateway revision+binding revalidated after fetch.
- [x] CG2.3 Genuine admin publish alias→discovered upstream mapping and default, catalogue/gateway CAS, fresh authority before replay, atomic snapshot/private routes/default/event/pointer/ledger. Rotation invalidates prior publication; rollback and race/replay verified.
- [x] CG2.4 Active genuine member projection: stable alias IDs/default/revision/unknown state only; no upstream IDs/routes/cipher/evidenceIDs. Suspension/crossorg/revoked-session denied. Bootstrap shape unchanged.
- [x] CG2.5 Separate reviewed static readiness for actual0001–5+0010–16; preserve CG1/legacy exact profiles. Pure gateway_catalog*, model_catalog*, gateway_configuration*, accountAPI plus focused ownedPG gateway_catalog harness, syntax/diff/whitespace and exact cleanup observed.

Authorized CG2 surfaces: migrations/0016_owned_gateway_catalog.sql; src/forge/gateway_configuration.py; gateway_catalog.py; gateway_catalog_adapter.py; gateway_catalog_store.py; gateway_catalog_readiness.py; model_catalog.py; model_catalog_store.py; account_api.py; pyproject.toml; tests/test_gateway_configuration.py; test_gateway_catalog.py; test_gateway_catalog_adapter.py; test_gateway_catalog_api.py; test_postgres_gateway_catalog.py; test_model_catalog.py; test_model_catalog_store.py; tests/postgres_support.py; docs/changes/central-gateway.md; this task. No actual provider key/network call, active demo/schema/user change, install, commit, native/RDD or browser operation.

CodeGraph successfully mapped actual catalogue contracts. Existing VERIFIED capabilities remain strict; v2 unknown is explicit and cannot become verified by alias naming. Reuse gateway's function-only role and NOLOGIN authority with scoped grants for publication tables; established enrollment helper owns fresh member resolution. Old migrations/functions/contracts remain unchanged. CG2 implemented and self-verified; independent review and integration remain pending.


## CG2 observed verification and handoff

- Meaningful codec RED: existing canonical decoder rejected an actual v2 unknown/unverified payload with CatalogStorageError (1test,0.013s); now roundtrips without fabricated capabilities. The first invocation lacked PYTHONPATH and failed import; that environment failure is not RED. Tests now resolve the repository src path explicitly.
- Meaningful HTTP RED: missing-auth refresh returned404 instead of401 (1test0.229s); all three new routes now enforce401 before validation. An added configured/unconfigured boundary test observed500 instead of503 from evaluating a missing optional service before its guard; corrected ordering, default remains unavailable.
- Final local `.venv/Scripts/python.exe -B -m unittest discover -s tests`: gateway_catalog*.py21pass1.350s; model_catalog*.py25pass0.033s (verified v1 behavior/encoding preserved); gateway_configuration*.py13pass0.605s; test_account_api.py10pass0.381s. All exit0. A compressed-response test initially failed during eager fixture construction, not product dispatch; corrected to an explicit unopened HTTPX ByteStream, then passed. Starlette/httpx deprecation warning remains; no install.
- Final actual `& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_catalog.py`:8pass19.615s,exit0,PostgreSQL17.11; exact-ID cleanup confirms owned container absence. Actual new fixture applies0001–5+0010–16; old fixture behavior and rollback probe are unchanged. Genuine SessionService/create_account_app proof refresh200→publish200→same-org employee models200/public aliases/default/nullcapabilities→bootstrap200; foreign scope404, nonadmin mutation404, replay200, reopened store identical, logout then401. No live gateway call: HTTPX transport is explicitly labelled fixture-only.
- Store proofs: selection/default validity, gateway/catalogue CAS, identity-bound replay and changed-default conflict; concurrent writers yield one success/one conflict; current administrator revoked before replay/discovery denies; current organization/member suspension and session logout deny; keyrotation during outbound discovery proves no held DB locks and refuses stale save; rotation before publish refuses stale binding; previous employee publication becomes unavailable. A late ledger trigger failure rolls back snapshot/private mapping/default/event/pointer/ledger together. Wrongkey never saves discovery; logout between fetch and save denies. Service/account/bootstrap roles cannot read private tables. Extra policy, changedACL, NOFORCERLS, SECURITYINVOKER and authorityLOGIN all fail exact readiness.
- Historical PG outcomes retained: initial7tests had4pass3fail while static artifact was intentionally absent (expectedNone plus HTTP503/readinessfalse). After a narrow SQL unknown-capability consistency check, capture8tests had5pass3fail for the same absent artifact; static final reviewed SHA authored from the pristine owned capture. First pinned8tests had7pass1fail: positive employee fixture mistakenly used baselineBOB/ORG_B while publishingORG_A, correctly returning404. Read-only reset() evidence confirmed this; changed only the new fixture to actualCAROL/ORG_A member23 and added real foreignBOB denial. No authorization weakening. Final8GREEN supersedes incomplete proof, not its history.
- Separate static PostgreSQL17 profile SHA256 `771721e4c57685611bbd3a456ee318fe0433c5f37c4130fe7c559ebfb67ced8c`, from actual reviewed new fixture only; never runtime learned. CG1/legacy pins and old migrations remain unchanged. `httpx==0.28.1` moved from optional test declaration to runtime dependency without any installation.
- No active demo/schema/account/user changes, provider credentials/remote call, inference, browser, install, commit or native/RDD operation. Independent CG2 verification and CG3–CG5 remain pending. Source handoff is not production readiness or deployment authorization.

- Final check-only Python syntax, authored whitespace across all17 changed surfaces and git diff --check passed. Existing line-ending warnings are retained. Full-file2994lines include earlier/unrelated baseline content and are not a CG2 authored-diff count; nine new CG2 behavior/test surfaces941lines plus bounded existing-file additions. No code-size-only split or minification. Task/doc UTF8 readback corrected a locale cp1252 misdecode in historical Unicode punctuation without changing evidence.


## CG2 independent deadline correction (authorized)

Independent verification reran21+25+13+10 pure and8PostgreSQL checks successfully but found a deterministic total-deadline blocker: synchronous iter_bytes(chunk_size65536) buffers fragmented trickles before the next clock check.100 one-byte chunks can consume100 simulated seconds despite the nominal10second budget. CG2.2/CG2.5 and overall CG2 are reopened; prior functional proof remains historical, not complete independent approval.

Bounded correction surfaces: src/forge/gateway_catalog_adapter.py; tests/test_gateway_catalog_adapter.py; optional already-authorized gateway_catalog/accountAPI and focused tests only if actual composition requires them; this task. No schema/readiness pin/active demo/key/provider/installation changes. Observe fragmented-body RED, replace observational-only deadline with actual cancellable headers/body timeout and unbuffered chunk checks, then exercise fragmented trickle, slow headers/send cancellation, no pending request tasks/abandoned request threads, safe synchronous composition and full focused pure/PG regression. No unbounded executor or nested event loop. Parent independent fix verification remains pending.


### Deadline correction observed closure

- Meaningful RED: adapter7existing tests passed but new fragmented trickle test failed100consumed versus<=10 (8tests0.014s). This confirms the actual buffering defect, not an import/environment error.
- Corrected AsyncHTTPX outer asyncio.timeout covers awaited request send, headers and body; each unbuffered fragment is also checked against the observed budget. Default10s ceiling cannot be increased; labelled tests can select a smaller positive deadline. Compressed/body/ID limits and fixed-origin/no-environment/no-redirect/redaction guards remain.
- Actual HTTP refresh is now async and awaits GatewayCatalog.refresh_async on the server's existing loop. Short store/authorization calls use AnyIO's framework-bounded worker limiter with abandon_on_cancelFalse; outbound IO never holds database row locks or runs as a detached request thread. Synchronous direct refresh remains available outside running loops; sync facade explicitly failsclosed in an existing loop, which uses discover_async instead. No nested event loop or unbounded request executor.
- Labelled awaited send and header stalls are cancelled, transportclosed and no pending asyncio request task remains; actual fragmented slow body is cancelled/closed and adds no request threads. Real API/service/adapter fixture dispatch reaches the stalled header stage, returns redacted503 promptly and never saves discovery. External/live provider calls are not claimed.
- Final local pure commands: gateway_catalog*.py27pass0.574s; model_catalog*.py25pass0.023s; gateway_configuration*.py13pass0.374s; test_account_api.py10pass0.318s, all exit0. Actual `& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_catalog.py`:8pass46.342s,exit0,PostgreSQL17.11, exact-ID container absence confirmed. Genuine async accountAPI discovery/publication/member projection and rotation/no-network-lock checks passed. Static profile SHA and schema unchanged.
- Earlier independent result remains PARTIAL due to the now self-corrected deadline blocker. Independent fix verification is still pending; selfGREEN does not grant independent approval. No active demo, provider key, installation, schema, commit, native/RDD or browser change. Source frozen for parent verification.


## CG3a authorized central text inference

Parent reports CG2 independent corrected deadline PASS27catalogue+10accountAPI+8PostgreSQL; original fragment repro stops10 and closes. This supersedes the deadline PARTIAL only after that observed independent proof. CG3a is authorized now; CG3b running-demo upgrade is explicitly not authorized/complete.

Route: delegated direct single writer. Forecast CG3a approximately1200–1800 authored lines, advisory only. Exact POST `/forge/v1/orgs/{org}/chat/completions` accepts bounded text messages and published stable alias only, never upstream IDs/tools/images/attachments/raw generation parameters. Unknown capabilities remain unknown. Normalized OpenAI-style SSE subset is a bridge contract, not full OpenAI compatibility.

- [x] CG3a.1 Meaningful runnable RED→GREEN for authenticated/default-deny contract and bounded text input/output normalization.
- [x] CG3a.2 Genuine session/account/active member/current publication/private selected route/current gateway binding resolver; deny invalid scope/alias/stale/cipher before outbound. Additive0017 and separate static profile preserve0015/16.
- [x] CG3a.3 Fixed HTTPS async no-environment/no-redirect/no-retry transport, whole/event/read/byte bounds, normalized text/finish/error SSE only. Explicit fragment/slowheader/cancel/close/tool/malformed/oversize tests.
- [x] CG3a.4 Fresh authority/publication monitoring during stream, close on disconnect/rotation/revocation/limit without locks held awaiting provider. Document recheck interval/storage failure latency and irreversible in-flight cost.
- [x] CG3a.5 Pure gateway_inference* +accountAPI and owned realPG focused harness, syntax/diff/cleanup; genuine member/nonadmin resolution, denied cases and exact role/RLS/function drift. No live provider proof.

Authorized surfaces: migrations/0017_owned_gateway_inference.sql; src/forge/gateway_inference.py; gateway_inference_store.py; gateway_inference_adapter.py; gateway_inference_readiness.py; gateway_configuration.py; account_api.py; tests/test_gateway_inference.py; test_gateway_inference_adapter.py; test_gateway_inference_api.py; test_postgres_gateway_inference.py; tests/postgres_support.py (new opt-in helper only); docs/changes/central-gateway.md; this task. No services, demo state, remote/key access, installs, commits or native/RDD. Existing keys are never read.

## CG3a observed implementation and frozen handoff

CG3a implemented and self-verified; independent checking remains pending. CG3
overall remains unchecked because CG3b composition/upgrade is not implemented
or authorized in this unit. No running demo, existing private key, production,
remote provider, client source, installer, Git or native review was accessed.

- RED: actual account application missing-bearer chat endpoint returned404
  instead of required401;1 test failed0.651s before implementation.
- Final `.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_gateway_inference*.py' -v`:
  27pass4.495s. Includes direct async fragmented transport cancellation/close,
  slow headers/trickle/idle/byte/event/output limits, tool/malformed/redirect
  rejection, private echo guard, logout/rotation/disconnect monitoring, genuine
  typed text input and normalized public alias/error SSE. Tests are labelled
  fixture HTTP, not actual gateway inference.
- Final existing `test_account_api.py -v`:10pass0.611s.
- Final `& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_inference.py`:
  6pass16.501s,exit0,actualPostgreSQL17.11, exact owned container removed and
  absence read back. Genuine non-admin account API streams only published
  route; foreign/unpublished/suspended/orginactive/logout/reset/accountdisable
  failclosed. Wrongkey/substituted binding and current publication/gateway
  rotation deny before outbound; rotation while body waits closes transport.
  Real SQL mutation during provider wait succeeds without held org locks.
  Direct table/account/bootstrap role function denial, wrong connection role,
  ACL/FORCERLS/function/authorityLOGIN drift and previous profile rejection pass.
- Authored static inference profile SHA256
  `0544327eb3719aff43676332c84489fa759a71fe3fa10b38fbf36a99c1c52614`;
  previous migration/profile bytes remain unchanged.
- Check-only AST11files and authored source/test/SQL whitespace12files PASS;
  git diff --check PASS (existing LF/CRLF warning only). New CG3 inference
  files total1125 lines; shared composition/docs/tracking additions are extra.
- Historical checks retained: first owned profile capture intentionally kept
  expected pin unset:3pass3fail17.325s; subsequent run5pass1fail31.743s exposed
  prebuffered HTTPX test response, corrected to actual AsyncByteStream fixture.
  Each failed run cleaned exact owned container. Additional lifecycle test
  margins were corrected; meaningful backpressure RED exposed internally
  deadline-cancelled producer being treated as client cancellation. One task
  now owns producer deadline/queue and normalizes only its internal timeout;
  explicit caller cancellation remains cancellation. Final27/10/6 passed.
- Current API bridge subset/limits/revocation latency are documented in
  docs/changes/central-gateway.md. Recheck0.5s plus bounded database/pool and
  scheduler latency is not instant revocation; already incurred cost/text
  cannot be undone. Streaming failures after200 are in-band redacted errors.
- Next boundary: parent independent CG3a verification, then separately
  authorize CG3b explicit durable composition/upgrade. No readiness fiction,
  active demo upgrade, live gateway claim, commit or full baseline PASS.

## CG3b authorized explicit stopped-demo composition/upgrade implementation

CG3a independent verification reported27 inference,10 accountAPI and6 realPG
PASS. Parent elevated accountAPI spot check90400 remains pending; CG3b does
not edit account_api.py. CG3b is source/composition implementation only:
the current running a23d demo and its users/schema/private material must not
be accessed or upgraded. Real-user migration needs separate authorization.

Route: delegated direct, single writer. Preserve legacy create/default resume,
all real account/password/membership/invitation/session/mailbox rows, old role
credentials and delivery key. Explicit -UpgradeGateway -DemoDirectory accepts
only exact stopped owned legacy state/volume/container/lock. It never seeds,
resets, silently migrates on Resume or automatically stops an active owner.
Separate gateway composition/key/profile; optional gateway starts unconfigured.

- [x] CG3b.1 Meaningful legacy/gateway manifest admission REDâ†’GREEN; wrapper
  explicit switch, active/unowned/mismatch refusal and legacy regressions.
- [x] CG3b.2 Recoverable phase journal with static reviewed database checkpoint
  fingerprints around actual independently committed migration bytes; atomic
  final file-manifest promotion, no fictitious outer migration transaction.
- [x] CG3b.3 Preserve old rows/credentials/delivery material; separate protected
  gateway key and new restricted service-role credential created once, reused
  on restart; missing key after progress/cipher state refuses regeneration.
- [x] CG3b.4 Real central configuration/catalogue/inference service composition,
  exact0017 admission and fixed-origin narrow GET/POST/PUT/OPTIONS CORS.
- [x] CG3b.5 Fresh owned test legacyâ†’enrollâ†’stopâ†’upgradeâ†’restart proof, injected
  commit/journal/promotion failures recover forward with unchanged users;
  fake protected gateway key reopens/decrypts, no live provider calls.

Allowed surfaces: src/forge/dev_accounts_persistent.py; dev_accounts_gateway.py;
scripts/dev-accounts-persistent.ps1; tests/test_dev_accounts_persistent.py;
test_dev_accounts_gateway.py; test_postgres_gateway_upgrade.py; this task;
odd/tasks/forge-owned-accounts.md; docs/changes/central-gateway.md.
Forecast approximately1000â€“1600 advisory lines. Normal3320 is occupied by
user-owned account backend; tests must use new owned databases and in-process
actual FastAPI composition, never stop or replace that service. No install,
provider/key access, active demo mutation, commit or native/RDD operation.

## CG3b implemented/self-verified handoff (not a user-demo upgrade)

Parent reports independent CG3a PASS27/10/PG6. CG3b source is now frozen for
independent checking; current a23d demo/server/schema/private material were not
accessed or changed. CG3 overall is not reported integrated/deployed; CG4/CG5
and real-user migration remain pending.

- Meaningful RED: upgraded ready manifest admission raised
  INVALID_DURABLE_OWNERSHIP,1error0.224s before implementation.
- Final retained fixture command: set FORGE_RUN_GATEWAY_DEMO_INTEGRATION=1,
  run `.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_dev_accounts_gateway.py -v`,
  then remove only that owned flag.5pass48.124s,exit0. NEW owned named volume/
  container legacyseed→real invite/accept→stop→actual PowerShell upgradechild
  →same DB restart→same admin/recipient identities/passwords/old session access.
  Fake protected gateway save and another stop/start prove same-key decrypt.
  Active DB and held lock refuse without automatically stopping resources.
  It uses actual FastAPI ASGI composition, not a replacement3320 listener.
- Final actual `& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_upgrade.py`:
  1comprehensivepass16.288s,exit0, exact owned container removed/readback absent.
  Each actual migration COMMIT checkpoint is statically pinned. Injected
  before-firstcommit, seven aftercommit, role provisioning, context/manifest
  promotion failures recover forward. Hash snapshots verify old account/
  password/identity/member/dept/invite/session/audit/delivery/loginbucket/reset/
  configuration rows and PostgreSQL role passwords unchanged; mailbox bytes,
  delivery key, old secret/credential files preserved. Reopened real service
  supports genuine account login/bootstrap/configuration and trusted PUT CORS.
  Missing gateway key after cipher state refuses without recreation.
- Existing test_dev_accounts_persistent.py:2pass1skip0.001s; old fixed3320
  separate-server lifecycle intentionally skipped to preserve running user
  service. No legacy server restart/regression is invented.
- Python AST5files, PowerShell check-only parse, authored whitespace6files
  and git diff --check PASS. Three new behavior/test files624lines plus
  bounded persistent/wrapper/docs additions; no size-only splitting/minifying.
- Historical verification retained: checkpoint-build fixture1expectedfailure
  2.381s while static intermediate pins were absent; source checkpoint artifact
  authored only from that pristine owned PG17 fixture. Initial full preservation
  test1pass12.962s; final stronger16.288s includes delivery/mailbox/old role
  password preservation. First retained lifecycle4pass1error31.107s from
  missing test json import after successful child upgrade; corrected test
  import, final5GREEN. Both retained test databases are verified STOPPED.

Created NEW verification artifacts (all under the authorized physical packaged
LocalAppData demos root, never the current user demo):
- forge-owned-accounts-a593e07f6ac04ee5acf93cc2710f9214 — checkpoint capture
  private directory preserved; disposable PG harness container removed.
- forge-owned-accounts-599e8e7e8daa403fa59107c144c91cdd — first preservation
  private directory preserved; disposable PG harness container removed.
- forge-owned-accounts-c0733a2a72b74f4892d0becb3c1582b6 — final preservation
  private directory preserved; disposable PG harness container removed.
- forge-owned-accounts-c825fe64419a46ff94a142752f35a772 — first retained test,
  container988508683ff157b52f3cb8ddd8c6f6db747c6cd6555c26224fa30834518fdbe0,
  volume forge-durable-accounts-data-c825fe64419a46ff94a142752f35a772;
  exact read-only inspect confirms Runningfalse.
- forge-owned-accounts-7aa2984b769741679bc2c59e2b1099bc — final retained test,
  container6efc358205cfb17060ec4b328d07ad42cc14cd5a06d08e567f00cda2b17260f2,
  volume forge-durable-accounts-data-7aa2984b769741679bc2c59e2b1099bc;
  exact owned verification confirms STOPPED. No directory/volume was deleted.

Recovery is explicit: ordinary Resume never migrates; interrupted journal
requires UpgradeGateway on the exact stopped owned instance. Separate gateway
key/role credential persists once; completed missing-key state fails closed.
Legacy source constants/pins and current demo are unchanged. Next: parent
independent CG3b checks, then separately authorize a real user upgrade or CG4
client/admin bridge; no automatic migration, endpoint verification or release.

## CG4a backend authoritative publication status continuation

Client CG4a is frozen/self-verified32frontend+6proxy+8boundary checks, but cannot publish safely when employee models404 hides the real active-pointer revision. Parent authorizes a genuine administrator-only GET gateway/catalogue/status: actual catalogue_revision (zero only when no pointer), default_model nullable, publication_state CURRENT/UNPUBLISHED/STALE_GATEWAY. No credentials, binding, upstream IDs/routes or capability claims. Additive0018 and a separate static exact readiness profile preserve all earlier pins.

CG3b independent outcome is PARTIAL: retained lifecycle failed before service start; sequential owned PostgreSQL preservation passed. Earlier writer lifecycle GREEN remains historical, not independent completion. Parent authorized explicit0018 composition/profile upgrade, never active user demo operations. Preserve old0017 manifests/journals and private key; ordinary resume admits specific reviewed complete profiles only and never migrates. Versioned explicit upgrade journal retains prior0017 history and recovers forward after per-script commits; no reseed or key regeneration.

- [x] CG4S.1 Meaningful HTTP/SQL RED then admin authoritative none/current/stale status, fresh admin/session/org locks, function-only role isolation and redacted API.
- [x] CG4S.2 Reviewed0018 static pin, drift/rollback/denial tests; separate additive opt-in fixture and sequential owned harness.
- [x] CG4S.3 Explicit durable target0018 checkpoints and validated0017 journal compatibility/preservation; sequential fresh upgrade proof, prior pure/catalog/API regression, syntax/diff and full3170mirror.

Single delegated writer, only listed backend surfaces. No current demo/data, provider keys, remote/browser, installs, commits or review lifecycle. Forecast600–1000additional readable lines, advisory. Next client uses protected status instead of employee projection; parent will authorize that separately.

### CG4S observed proof and frozen handoff

- HTTP RED:8tests,7pass1failure5.404s; missing protected status returned404 instead401. SQL RED: actual unavailable-function path raised sanitized GatewayUnavailable; the fixture also accidentally exported an imported TestCase and caused a second pristine-schema setup error. Fixed only test discovery to import its module. Capture run4tests2pass2fail7.889s while the new static pin was deliberately absent; SQL zero/rollback already passed, HTTP correctly503. No absent artifact or fixture failure is presented as GREEN.
- Reviewed actual PG17.11 schema-only0018 artifact:0b2ca67e63355d71f94961c85675375d962abf438c859b22dadbfde269c9a16a. Authored statically in the new readiness profile/checkpoint; old exact pins/migrations unchanged. PG17-only, four NOLOGIN internal owners, restricted connection roles, ACL/RLS/functions/fingerprint failclosed; no runtime learning.
- Final .venv unittest: gateway_catalog*.py31pass11.090s; test_account_api.py10pass4.328s; test_dev_accounts_gateway.py6pass1retained-lifecycle-skip0.749s; legacy test_dev_accounts_persistent.py2pass1separate-lifecycle-skip0.003s. The retained tests were not claimed as passes; no fixed3320 startup or active demo access.
- Final owned scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_catalog_admin_status.py:4pass21.806s,exit0. Genuine sessions/admin API show actual0/null/UNPUBLISHED, published revision/default CURRENT, rotated employee404 but admin real prior revision/default STALE_GATEWAY. Direct function calls deny member/crossorg/suspended/revoked-admin/logged-out sessions; private tables and employee execution denied. PUBLICgrant, functioninvoker, NOFORCERLS and authorityLOGIN drift fail readiness;0018 rollback restores old exact profile. Earlier pinned4pass47.394s retained. Each exact owned container was removed with absence readback.
- Sequential upgrade first failed BEFORE seed/migrations: ConnectionTimeout7.523s. Unlike AccountDatabaseFixture, this direct test omitted owned harness wait_ready(). Added that existing bounded fixture call, not a product timeout change. Corrected one actual upgrade test passed70.969s,exit0, exact owned container removed. Real legacy users/hashes/sessions/memberships/invites/mailbox/role-passwords preserved through eight commits and injected journal/role/context/manifest failures. Actual0017 complete v1 profile resumes, protected fake cipher is saved there, explicit0018 recovery retains v1 history in v2 and identical key/cipher, identities and logins. Missing committed key refuses regeneration. New context/profile/status API attested; no reseed.
- New private owned fixture directories retained under the previously authorized physical packaged demos root: forge-owned-accounts-2e530527a3c44e8e8c29299219de0a5b (failed pre-seed) and forge-owned-accounts-9eb5b12c379643f184c046d97fc67bff (successful PG preservation). These are fresh test directories, not current a23d user demo; no retained volumes/current containers changed.
- Final check-only AST12, authored whitespace15 and scoped diffcheck passed; inherited LF/CRLF warning retained. No source normalizer, remote/provider/key access, install, browser, native/Git or active user operation.

Backend source is frozen for independent verification. CG4S is self-verified; this does not close independent CG3b retained-container lifecycle, CG4 client integration, CG5/E2E, deployment or actual user upgrade. Next client exact hook: protected GET /forge/v1/orgs/{org}/gateway/catalogue/status, validate catalogue_revision/default_model/publication_state, use actual revision even0, never employee404 inference. Add that GET to existing account-controller/proxy/middleware allowlists; load fresh status after save/rotation before publish. No client files changed here. Full projectforge3170mirror/readback follows.

## Parent reconciliation — 2026-10-09

- CG4S independent verification passed: catalogue 31/31, actual PostgreSQL status 4/4 (72.267s), then sequential preserving upgrade 1/1 (46.059s); exact owned containers removed. No current-user upgrade performed.
- CG4a/CG4b client implementation is recorded in clients/openyak/odd/tasks/forge-managed-workspace.md (Engram3059). Independent central processor/SQLite8/8, existing persistence13/13, admin proxy7/7 passed. Frontend28 cases passed initially; one failed before SSE due verifier missing workspace flag, then passed with the correct process-local flag. Parent proxy7/7 passed. No full29 independent rerun claimed. Semantic TypeScript120s attempt was terminated without a verdict.
- CG5 explicit isolated prebuilt-web wrapper is implemented; writer lifecycle16/16 passed. Actual strict Next15.5.12 production build reached its900s deadline while compiling: BUILD_TIMEOUT, no type/lint verdict, no promoted manifest and no successful production-start proof. Independent wrapper checks are pending. Build log: clients/openyak/frontend/.forge-managed-web/build-eb058d0f-9a42-458d-ab16-cea0423286b3/build.log.
- Product remains PARTIAL. Current durable user demo, its users and gateway credentials were not altered. Live end-to-end configuration/inference, prebuilt startup, final branding and release are not claimed. No installer, remote deployment or commits.
- Next action: diagnose the isolated production build stall before offering a user-demo upgrade/start. Do not replace strict checks with a development fallback or ask the user to repeat the old key launcher.
- Engram was temporarily unavailable during parent reconciliation; the namespace returned and the full current document is being resynchronized before delivery.

### CG5 final bounded handoff

The justified managed-only PPTX transpilation correction reduced measured icon-module spans from10613 to46 and the second strict production build compiled successfully in8.6minutes. It then reached its900s total deadline during lint/type validation: exit1 BUILD_TIMEOUT, no semantic verdict, no admitted build manifest or production startup proof. Original and changed build artifacts/logs are retained. No blind further retry or disabled checks.

Final independent wrapper32/32 passed76.209s, including fixed root/ancestor junction admission, staged runtime-config/source drift, alternate configuration denial, actual installed SWC transform, active dotenv refusal and inert-template exception. Parent targeted9/9 passed3.344s. Owned build processes were confirmed absent, source generated configs unchanged, user demo untouched.

CG1–CG4 functional implementation is present with scoped evidence above; full product acceptance remains blocked by strict prebuilt validation/startup. Do not mark CG5 or live end-to-end complete. Next work should isolate the semantic validation duration/failure rather than returning the user to the old private-key launcher. Current runtime central integration/user migration and real provider response still need explicit operational proof.
