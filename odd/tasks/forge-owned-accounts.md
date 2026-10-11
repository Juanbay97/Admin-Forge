# Forge-owned account onboarding

## Outcome and current boundary

An administrator invites a person using email, name and one existing active area;
the recipient sets a password before becoming a member. Microsoft authentication
is deferred. No public registration and no activation merely by sending an invite.
U0 is complete. U1 functional enrollment proof is independently observed: real
PostgreSQL 12/12 tests passed in 12.471 s, exit 0, exact owned cleanup confirmed.
The whole-discovery regression remains pending after cleanup failures; do not
interpret focused proof as rollout readiness or a full-suite pass.
0013 is opt-in enrollment only: legacy exact readiness intentionally rejects it.
Current authorized writer scope includes bounded U2 sessions, local-test delivery
and reusable HTTP composition. Bounded U3a local developer backend composition
is now authorized; U3b real client UI/E2E remains frozen. Bounded U2
functional proof is observed after the bounded authority correction: real
PostgreSQL 11/11 in 33.891 s, exit 0, exact
cleanup; pure HTTP10/10, delivery8/8 and account13/13. Integration, full regression
and independent U2 verification remain pending; no deployment claim.

## Working state and constraints

Root: `N:/Proyects/forge/.worktrees/tenant-storage`;
branch: `feat/forge-s3-outbox-recording`. Preserve all existing dirty work and every
client/native/preview checkout. No remote access, credentials, dependency installs,
production operations, native review, staging or commits in this writer turn.
0013 is additive; 0012 and reserved 0006–0009 remain untouched. No runtime readiness
or Entra behavior changes. Existing email is a lookup, never an authorization identity.

Route: delegated direct, because persistence, crypto, migration and tests require
coordinated files. Delivery: approved local feature-branch-chain; commit identities
pending, not invented. Revised full feature forecast 5000–6500 authored additions/deletions;
U1 forecast 900–1300, advisory only: no minification, omitted tests or file-type slices.

## Work units

- [x] U0 — Reconcile S3 design, write this contract and full Engram mirror, read back both before source writes.
- [ ] U1 — Versioned memory-hard password credentials, genuine Forge identity, durable invitation and atomic enrollment with real PostgreSQL security/concurrency proof.
- [x] U2 — Add separate enrollment-aware exact catalog/ACL/RLS attestation before runtime composition; compose account sessions and HTTP; bounded KDF admission/rate limits; locally owned mail delivery with pending/delivered/failed separate from issuance. No external mail credentials inferred.
- [ ] U3a — Runnable isolated local developer account backend, private generated fixture credentials/mailbox, real HTTP verification and exact owned cleanup.
- [ ] U3b — Actual product UI and browser E2E for admin invitation/password setup/sign-in; not a demo silo. Existing clients remain frozen through U2.

## U1 acceptance

- [x] A1 — Genuine provider `forge`, fixed internal issuer and stable UUID subject; no fake Entra and no email-based authorization. Explicit ASCII email canonicalization and bounded name/password input.
- [x] A2 — Installed cryptography Scrypt, fresh salt, versioned exact n=2^17/r=8/p=1 profile, strict encoded-parameter allowlist, password byte bounds and bounded concurrent memory use; never weaken production cost for fixtures.
- [x] A3 — Creation revalidates and locks active organization/member/actual identity/admin grant inside transaction; existing active same-org department required. No raw role claims or pending membership access.
- [x] A4 — Random32-byte single-use capability with persisted hash only, bounded expiry and revocation. Atomic acceptance creates credential/identity/member/initial-area link/audit and consumes invitation; no accidental admin role.
- [x] A5 — Existing account requires separate authentication/linking and cannot have its password reset by invitation. Uniqueness/races/rollback preserve one coherent account and enrollment.
- [x] A6 — FORCE RLS and dedicated nonbypass NOLOGIN roles/function authority; runtime grants unchanged. No secrets/email/password in audit or diagnostics.
- [ ] A7 — Meaningful observed RED then GREEN; owned PostgreSQL runner once final, baseline cases retained, exact cleanup; diff whitespace and protected-file hashes checked. No skipped unavailable check called PASS.

## Exact verification and proof limits

`.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_accounts.py -v`.
Then existing `scripts/test-postgres.ps1` once final: cached official digest pinned,
`--pull=never`, generated harness-only credentials, exclusive random loopback port,
owned disposable DB/container and exact cleanup. Whole baseline PG suite is included.
`git diff --check` plus untracked authored whitespace and protected-file hashes.
No meaningful runtime HTTP/UI proof exists for U1: N/A, not PASS. Invitation issuance
is not delivered email; password enrollment is not session/sign-in integration.

## Recovery and next step

Engram project `forge`; authoritative session ID unavailable, omitted.
Historical mirror 2986 was mistakenly saved under `prometheon-forge`; retained,
not deleted. The current full mirror is explicitly scoped to `forge`.
Full mirror topic `odd/forge-owned-accounts/tasks`; parent retains full feature map.
Readback/mirror and exact observations are recorded as obtained. U2 returns to
parent before UI writes; independent U2 verification and all commits remain pending.

U0 readback: task and design verified; full Engram mirror observation 2986 read back
with matching contract before source writes. This historical mirror was corrected
to project forge in observation3010; independent focused U1 proof is recorded above.

## U1 initial historical evidence — partial, not integrated

| Check | Observed result |
|-------|-----------------|
| Dependency readiness | Installed cryptography 50.0.2 exposes maintained Scrypt; no installation or dependency edits. |
| Meaningful RED | Importable stub: 11 test methods, 37 NotImplementedError subcase errors, exit 1; test 0.036 s, wall 1.983 s. |
| Final pure GREEN | 13/13 test methods, exit 0; test 5.477 s, wall 7.859 s. Uses the real production-cost Scrypt profile. |
| Owned PostgreSQL whole suite | 0 tests executed; 14 setUpClass readiness errors; exit 5; test 211.423 s, harness wall 246.856 s. |
| Owned cleanup | Runner reported container removal and exact-ID absence readback. No retry performed. |
| Python syntax | In-memory compilation of all seven new/modified Python implementation/test files passed; no bytecode files written. |
| Whitespace | Tracked diff check and authored-file trailing-whitespace check passed. |
| Preservation | Protected-file hashes unchanged; original postgres_support.py 43509-byte prefix preserved exactly (SHA256 8feb7eb58077dd303bcdfd7b9096d24fca5977426b1a0f1822a3c5ca769a6abe). |

At the initial handoff, A1 input/identity primitives and A2 password behavior had
pure-test proof. A3–A6
have migration/store/test candidates only: no SQL ran, so durable identity, locking,
RLS, privilege isolation, rollback and concurrency are NOT verified. A7 remains
incomplete because the required real PostgreSQL check is blocked. Twelve new
PostgreSQL test methods are written, not executed. The final password input guard
was checked again with the final 13 pure tests after the unavailable DB run.

The current candidate creates pending intent, not active membership; acceptance is
intended to grant only the basic member role. Existing-account authentication/linking
is explicitly required rather than changing its password through an invitation.
The per-process KDF gate admits one full-cost operation; fleet/HTTP admission remains
U2. No public registration, session, invitation email delivery, HTTP/UI integration,
readiness change, native approval or production readiness is claimed.

Password references: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [cryptography Scrypt](https://cryptography.io/en/46.0.3/hazmat/primitives/key-derivation-functions/).

The initial handoff requested parent diagnosis and a separately authorized database
run. The following correction preserves those failed observations rather than
rewriting them as successful proof.

## U1 first bounded correction — historical proof (2026-10-08)

Parent independent verification executed 226 PostgreSQL tests: 225 passed and one
failed because the enrollment test incorrectly expected legacy readiness true.
0013 adds scoped authority policies outside the existing exact policy counts.
Parent explicitly chose to preserve the legacy probe unchanged and fail closed.
The enrollment test now requires false while keeping its actual member-role and
cross-organization authorization-reader assertions unchanged. This opt-in migration
is NOT rollout-ready. U2 must add separate enrollment-aware exact catalog/ACL/RLS
attestation before any runtime composition; do not relax the legacy attestation.
The S3 design explicitly reconciles its earlier compatibility expectation for 0013.

The initial harness readiness failure was independently traced to null environment
assignment leaving empty PGSERVICE. The corrected harness removes literal Env items,
stores presence separately, restores absence as absence, and preserves both empty
and populated original values. No original environment values were printed.

| Correction check | Observed result |
|------------------|-----------------|
| Environment RED | Owned synthetic variable remained present after legacy null assignment; exit 1. |
| Actual harness-loop GREEN | Extracted on-disk save/clear/restore loops passed absent, empty and populated states; parser check passed. |
| Pure account rerun | 13/13 passed, exit 0; test 8.096 s, wall 23.581 s. |
| Full on-disk harness once | 0 tests executed, 14 setup errors, exit 5; test 60.994 s, wall 153.950 s. No in-memory shim. |
| New failure evidence | First migration_probe DROP DATABASE cleanup exceeded its statement timeout; later role duplicates and dependencies cascaded. Cause of the timeout is not established. |
| Owned cleanup | Exact container removal and absence readback confirmed. No further retry. |
| Preservation | Legacy postgres.py and runtime/API/domain sources unchanged; only the four authorized correction surfaces modified. Diff whitespace passed. |

Current U1 remains partial: the corrected SQL readiness expectation has independent
RED evidence but no successful final on-disk GREEN. Prior independent SQL successes
are retained, not substituted for the failed required rerun. Parent must diagnose
the fixture cleanup timeout and authorize any exact additional surface or retry.
No staging, commits, native review, U2 or UI implementation occurred.


## U1 cleanup-budget correction — current proof (2026-10-08)

Parent independently repeated the 5-second migration_probe DROP DATABASE timeout;
no lock or underlying cause was established. The authorized test-harness-only
correction opens a separate cleanup connection with statement_timeout=30000 ms
and lock_timeout=2000 ms. Default statement_timeout=5000 ms, connect_timeout=2 s,
main migration queries and product/runtime budgets remain unchanged. No retry,
forced disconnect or broad timeout change was introduced.

| Current check | Observed result |
|---------------|-----------------|
| Focused actual cleanup block | AST execution verified isolated finite cleanup settings, unchanged defaults and four exact cleanup operations without retries. |
| Pure account suite | 13/13 passed, exit 0; test 6.257 s, wall 13.890 s. |
| Actual whole on-disk harness once | 0 tests executed, 14 setup errors, exit 5; test 63.440 s, wall 106.226 s. No shim. |
| First failure | migration_probe DROP DATABASE at line 168 again raised QueryCanceled for statement timeout despite the 30-second cleanup budget. Later role duplicates/dependencies cascaded. |
| Owned cleanup | Container removed; exact-ID absence readback confirmed. No subsequent run. |
| Protected implementation | Seven hashes unchanged: legacy postgres.py, harness script, 0013 migration, authorization.py, outbox.py, api.py and runtime.py. |
| Whitespace/syntax | Diff whitespace and explicit UTF-8 cleanup-module syntax check passed. |

The initial preserved 43509-byte support prefix is historical evidence, not a
current byte-identity claim after this explicitly authorized support edit and
newline normalization. The semantic correction is limited to the cleanup block;
existing appended fixtures remain. Product and default connection budgets are
unchanged. U1 remains partial; successful full on-disk GREEN is still absent.
That historical stop boundary was subsequently released by the parent for bounded
U2 local development, as recorded below. It did not resolve whole regression or
authorize commits, native lifecycle, production or UI changes.


## Released U2 scope and test-first checkpoints

Parent independent focused enrollment run used the corrected actual harness with
only unittest argv selection changed: 12/12 in 12.471 s, exit 0, exact cleanup;
11 candidate hashes unchanged. A separate isolated migration_probe succeeded in
0.024 s. Full-discovery cleanup cause is still unknown: its failed historical
checks remain pending and are not checked off. Focused proof authorizes safe local
development only; no deployment, staging, commits or native lifecycle.

U2 is delegated direct because sessions, SQL, delivery, readiness and HTTP require
coordinated security behavior. Keep one writer; U3 actual UI remains frozen.

- [x] U2.1 — Durable opaque sessions, expiry/logout/credential-reset/self-disable revocation; real-cost password login with persistent bounded account throttling and generic errors.
- [x] U2.2 — Explicit trusted onboarding origin and private local EmailMessage delivery; durable encrypted retry payload with caller-supplied Fernet key; pending/delivered/failed separate from intent. No SMTP or mail-sent claim.
- [x] U2.3 — Strict default-deny account API factory: session-derived admin identity, invitation accept/login/logout/reset/self-disable, session-authenticated existing bootstrap; no public signup, request role claims or persistent browser tokens.
- [x] U2.4 — Separate exact owned-account catalog/RLS/function/ACL attestation including existing bootstrap prerequisites; legacy exact probe untouched; fail closed on tamper before dispatch.
- [x] U2.5 — Meaningful RED then GREEN, new pure HTTP/mail tests, focused on-disk PostgreSQL accounts and enrollment, pure account regression, syntax/diff/protected hashes. Whole discovery remains pending.

Optional runner TestPattern is restricted to test filename/glob syntax and passed
as one unittest argv value, never shell interpolation; default stays unchanged.
Global-account self-disable requires its own authenticated session, not an admin
of only one organization. Organization membership suspension remains distinct.
Reset capabilities cannot be invitation capabilities and are single-use/expiring.
Scrypt and key material are never weakened or silently generated from environment.


## U2 candidate and retained proof (2026-10-08)

The opt-in factory is reusable composition over genuine Forge sessions and the
existing PostgreSQL bootstrap/authorization readers. No fixture identities enter
runtime. HTTP supplies no roles or membership IDs; a fresh session-derived reader
observation is followed by0013's locked transactional administrator revalidation.
A single full-cost KDF slot and process-local16-per-second admission bound local
work; persistent five-attempt/15-minute hashed-email/account budgets survive
processes. Sessions expire after eight hours and are stored only as capability
hashes, revision-bound to credentials. Reset capabilities expire after30 minutes;
logout, reset and authenticated account self-disable revoke the relevant sessions.
Organization suspension remains separate from global account disable.

Local delivery is explicitly local_test_mailbox, not SMTP or sent-email proof.
Private EmailMessage files use UUID filenames, exclusive creation, escaped HTML
and no user-derived redirect/Host origin. Durable retry jobs hold encrypted Fernet
payloads under an explicitly supplied key, finite three-attempt leases and separate
pending/delivered/failed states. Tokens exist only in private encrypted payloads
and private fragment links. The caller must protect the mailbox folder ACL and
retain the encryption key separately; Windows mode0600 is not ACL attestation.
No browser persistence or fragment clearing is claimed before U3.

### Exact opt-in attestation boundary

The static manifest was captured once as a build/test artifact from actual
0001–0004+0013–0014 on owned PostgreSQL17.11. The projection includes server major,
all Forge schema relations/columns/constraints/indexes/policies/triggers, owners,
function source/security/search paths, roles, membership edges and grants. ACL and
policy principal names, not temporary OIDs, normalize ordering. No business rows,
passwords or tokens enter the fingerprint. The authored SHA256 is
713d5fd1851f911ab12ec3dbb1a813b4ec3f549aa27940902b9881a1d50e297c.
Both distinct nonbypass account-service and bootstrap connection roles are checked;
account CREATE/TEMP/public-schema privileges are denied. No runtime learning or
trust-on-first-use exists. Optional0010–0012 catalog/outbox installation profiles
are not included in this manifest and fail closed until separately attested.
Legacy readiness and legacy runtime remain unchanged; this is not rollout proof.

### Observed checks and failures

| Check | Observed result |
|-------|-----------------|
| Pure HTTP stub RED | Three methods, one assertion failure and five stub subcase errors; 7.786 s. Imports and dependencies worked. |
| Local-mail stub RED | Five methods,11 NotImplementedError subcase errors,0.018 s. |
| Initial mail candidate | Four pass/one failed expected-path normalization assertion; corrected to the resolved owned folder, not weakened behavior. |
| Final pure HTTP |10/10 passed,5.635 s, exit0; secret-rich exceptions, strict input/body bounds, spoofed/duplicate auth, fresh error UUIDs, generic retry and fail-closed readiness. |
| Final pure delivery |8/8 passed,4.301 s, exit0; encrypted token retry, state separation, tamper rejection, fragment/origin/header/path/HTML bounds and no overwrite. |
| Pure U1 regression |13/13 passed,3.069 s, exit0; production-cost Scrypt unchanged. |
| Earlier focused setup |Zero tests, one legacy migration_probe DROP timeout; exact container cleanup. This preceded the separately authorized accounts-only fixture. |
| Pristine static-pin capture |Real10 methods:9 passed and one expected absent-manifest readiness failure,37.740 s, exit1; PostgreSQL17.11 and the known pin captured; exact cleanup confirmed. |
| First final accounts run |11 errors,14.848 s, exit1. First HTTP body completed, then teardown hit membership_roles FK on test-created administrator grant; ten retained-schema cascades. No final GREEN from this run. |
| Deterministic fixture correction |Only the exact test-created org/member/admin role is removed before outer enrollment teardown. Original member-role snapshot equality is asserted; legacy DatabaseFixture and product SQL are untouched. |
| Role-only correction run |11 errors,5.944 s, exit1; administrator-role preservation passed, but invitation/audit references exposed the next teardown dependency; ten retained-schema cascades, exact container cleanup. |
| Complete cleanup correction |Owned leaves, invitation/audit rows and baseline-attached test credentials are unwound before shared cleanup. Original identities/members/statuses/roles are restored and full snapshots asserted; no production FK/RLS or legacyfixture changes. |
| Final corrected focused GREEN |11/11 passed,20.107 s, exit0; actual on-disk runner, PostgreSQL17.11, same static catalog pin, exact-ID container absence confirmed. |
| Dependency/syntax/whitespace |pip check passed; in-memory AST syntax and complete authored trailing-whitespace checks passed; git diff --check passed. |
| Protected hashes |Legacy postgres.py,api.py,runtime.py,authorization.py,outbox.py,0012,0013 and pyproject.toml match retained hashes. |

The separate accounts-only fixture applies actual base migrations into the owned
runner's fresh disposable database, not a fake database. It deliberately does not
invoke unrelated baseline migration_probe. The standard on-disk runner still uses
the cached pinned image with --pull=never, fresh generated harness credentials,
exclusive random loopback port and exact-ID cleanup. Whole-discovery/legacy
rollback regression remains separately pending and is not checked off. Accounts-only
base initialization is focused verification; default-discovery fixture composition
requires reconciliation before any whole-suite claim.

Two stalled/delayed owned pure-test sessions were stopped with exit observed;
a finite faulthandler probe passed, followed by the final complete pure GREEN.
No duplicate live test process, increased product budget or blind retry was used.
Starlette emitted its installed HTTPX deprecation warning; no installation or
upgrade was authorized or attempted.

U2 touched only0014, account_sessions.py,account_api.py,invitation_delivery.py,
account_readiness.py,account_store.py, the new HTTP/delivery/accounts PostgreSQL
tests, narrowly appended support fixture, optional validated runner TestPattern,
and this task. No staging, commits, review, SMTP, production or client UI writes.
Final cleanup/tamper proof is observed; product/test bytes are frozen. The11 real
methods cover exclusive delivery leases, generic durable known/unknown throttles,
session expiry/logout/self-disable/reset revision revocation, stale-login CAS and
single-use reset races, wrong-role/context isolation, and actual HTTP onboarding
through existing same-org bootstrap with cross-org404/live suspension403/logout401.
Exact readiness rejects extra policy, function-source mutation, extra table grant,
removed FORCE RLS and wrong pool role; restored catalog passes. No optional schema
profile, full regression, production SMTP or actual UI evidence is claimed.

The initial eight wholly new U2 implementation/migration/test files contained
1619 authored lines; the bounded authority correction brings their current count
to 1634. The earlier count is retained as historical boundary evidence.
Existing harness/support/store/task changes add necessary integration and evidence;
no committed work-unit count or identities are invented. The forecast remains
advisory; no behavior, spacing or tests were removed to fit a budget.

Next: parent independent U2 verification/readback, resolve focused/default fixture
composition and additional exact installation profiles before integration, then
separately authorize U3 actual client/UI/E2E. No further writer changes or tests
are authorized after this bounded return without a new parent task.


## Bounded independent-verification correction (2026-10-08)

Internal authority LOGIN drift is now rejected explicitly without denying intended
service or bootstrap LOGIN connections. This corrects a deployment-attestation gap;
no attacker privilege escalation was demonstrated or claimed. The static catalog
fingerprint is unchanged because the separate exact check validates the intended
NOLOGIN roles, not deployment-provisioned connection-role LOGIN attributes.

| Check | Observed result |
|-------|-----------------|
| Independent original SQL candidate | 11/11 passed in 151.985 s; all 12 candidate hashes unchanged. |
| Independent original pure candidate | Watchdog stopped the runner while importing FastAPI at 120 s; no test verdict. This is not a test assertion failure or an independent pure PASS. Historical self-verification remains 31/31 pure. |
| Deterministic finding | Catalog projection omitted rolcanlogin for SECURITY DEFINER owner forge_enrollment_authority. |
| Meaningful actual RED | Added owner/migrator LOGIN drift assertions before implementation: real 11 methods, 10 passed/one assertion failure, 57.599 s, exit 1. Readiness incorrectly returned true; exact container absence confirmed. |
| Bounded implementation | Explicit count=2 and bool_and(NOT rolcanlogin) for forge_migrator and forge_enrollment_authority. No blanket service/bootstrap NOLOGIN requirement or migration/policy change. |
| Final actual GREEN | On-disk scripts/test-postgres.ps1 -TestPattern test_postgres_accounts.py: 11/11 passed, 33.891 s, exit 0, PostgreSQL 17.11; same static pin and exact container cleanup. |
| Restored/intended states | Each internal role restored to NOLOGIN passes readiness; both legitimate connection roles remain LOGIN and pass. Other existing tamper, privilege and HTTP tests remain green. |

Only account_readiness.py, test_postgres_accounts.py and this task changed in this
single correction. Final source/test bytes are frozen; no subsequent source
normalization, migration edits, installs, Git mutations, native review or UI work.
Independent verification is still partial overall: original SQL was independently
verified, independent pure was unavailable, and corrected bytes await parent
readback. Whole regression and unsupported optional schema profiles remain pending.


## Released U3a local developer backend contract

Build an explicitly disposable local fixture launcher over the real reviewed U2
services before any frontend work. This does not configure the full enterprise
profile, chat or native application. Branding is not effective runtime integration;
all existing clients and the prior port3318 preview remain untouched.

Route: delegated direct, because owned database lifecycle, private material,
service composition and localhost HTTP checks require coordinated files. Only
src/forge/dev_accounts.py, scripts/dev-accounts.ps1, tests/test_dev_accounts.py and
this task are writable. Unit forecast700–1100 lines is advisory; the full feature
forecast rises to5000–6500, without shrinking clarity or omitting tests.

- [x] U3a.1 — Strict local profile/root/origin validation; reserve127.0.0.1:3320 before creating resources and refuse any occupant. Isolated child environment excludes ambient Docker/libpq credentials and proxies. Frontend origin fixed to http://127.0.0.1:3319.
- [x] U3a.2 — Own one cached digest-pinned --pull=never PostgreSQL17 container, loopback-only dynamic DB port and tmpfs; exact ID validation and deterministic stop/error cleanup. Never kill unrelated processes/containers or touch port3318.
- [x] U3a.3 — Apply actual0001–0004+0013–0014 into pristine owned DB; seed clearly labeled disposable organization/active area and genuine Forge administrator with real full-cost Scrypt. Separate restricted account/enrollment/bootstrap pools and exact readiness precede dispatch. No test-module imports or permissive auth.
- [x] U3a.4 — Private generated credentials and EmailMessage mailbox outside public assets, restricted Windows current-user/SYSTEM folder ACL verified before secret writes. Fresh fixture-only Fernet key remains private; no production fallback. Nonsecret context IDs/labels grant no authorization. No public mailbox/reset-token endpoint.
- [x] U3a.5 — Meaningful lifecycle RED→GREEN unittest, one actual localhost install/readiness/login/bootstrap/invite/mailbox/shutdown scenario, wrapper argument/path and occupied-port checks; exact container/process/port/private-folder absence after stop. Full current task mirror readback and next-worker launch/stop contract; no UI or whole baseline claims.

Architecture: the Python owned developer runtime handles container/private workspace,
actual SQL/pools and Uvicorn using a pre-reserved loopback socket. The small
PowerShell wrapper launches it in an allowlisted child environment, without
changing inherited process/global settings. Only explicit owned runtime material
may be read; no ambient sessions or credentials. The private workspace is an
owned random forge-owned-accounts-UUID directory under the local temporary root,
with canonical-path checks before recursive cleanup. Its context/credential/mail
locators may be reported, but never their secret contents. A private stop-request
file provides an exact-session graceful stop; resources remain caller-owned.

Verification leaves no active session unless explicitly identified for handoff.
If the verification fixture is cleaned, its paths are historical/absent, and the
next worker launches fresh through the same reproducible wrapper. Folder ACL
proof applies to the explicit Windows fixture directory, not a broad chmod claim.
No public SMTP, production deployment, native startup, Git or RDD operations.


## U3a observed result and next-worker contract

The local backend launcher is implemented and self-verified, not integrated into
OpenYak/native/company configuration. The five U3a checkpoints above have actual
contract/runtime proof. U3b frontend/onboarding/browser E2E remains pending.
Commits, independent U3a verification, native review, production deployment and
the previously failing whole legacy regression remain pending; no checkbox grants
review approval or deployment readiness.

### Verification of this exact candidate

| Check | Observed evidence |
|-------|-------------------|
| Runnable RED | Importable stub:8 errors/8 methods,0.023s,exit1. All errors were behavior NotImplementedError after correcting the subprocess mock seam; imports/dependencies available. Earlier0.082s RED had6 behavioral errors and2 mock-seam errors, retained as incomplete evidence. |
| Contract GREEN | Explicit .venv/Scripts/python.exe -B -m unittest discover -s tests -p test_dev_accounts.py -v:8/8 passed,2.565s. |
| Extended contract/wrapper checks | Same command after safe wrapper/HTTP assertions:11 passed,1 explicit integration skip,7.926s,exit0. Invalid root/origin and occupied3320 failed before creating any fixture; no occupant touched. |
| Actual local lifecycle GREEN | FORGE_RUN_DEV_ACCOUNTS_INTEGRATION=1 only for the scoped child test command; .venv/Scripts/python.exe -B -u -m unittest discover -s tests -p test_dev_accounts.py -v:12/12 passed,181.617s,exit0. One fresh cached --pull=never owned PostgreSQL17 DB installed actual0001–0004+0013–0014 and passed account-aware exact readiness before HTTP dispatch. |
| HTTP behavior | Real127.0.0.1:3320 health200, missing bootstrap auth401, generated administrator ordinary password login200, genuine bearer bootstrap200, same-org active-area invitation201 with delivered/local_test_mailbox. Response contains no invitation capability/password. Trusted3319 CORS accepted; hostile origin not allowed. |
| Private material | Current-user/SYSTEM-only protected Windows directory DACL was set/read back before credentials. One private .eml contained trusted3319/onboarding# fragment; no query token and public/mailbox404. Nonsecret context has fixture=true and enterprise_profile_configured=false, never password/auth grant. |
| Shutdown | Exact owned container29158a621c5d0eabad80a0802c5c23625377c15183744aaec7f1b24fedd1a9fe independently inspected absent. Backend PID31736 and wrapper exited, private directoryforge-owned-accounts-49720bfe60754610a01db7f36a0c3aae absent; exclusive3320 socket re-reserved successfully. No active session left. |
| Static checks | Python AST syntax, PowerShell parser, authored tracked/untracked whitespace and git diff --check passed. Protected U2/legacy/migration hashes match retained evidence. |

The real startup was slow but finite in this environment; the test uses a180s
startup deadline and bounded owned shutdown, not blind retries. Ctrl+C/parent EOF
are handled by the supervised child and wrapper finally; abrupt OS termination
and injected mid-startup Docker failure were not separately exercised. Cleanup
that cannot be confirmed retains its private ownership folder and reports a finite
OWNED_CLEANUP_PENDING failure rather than claiming success or killing unrelated
processes. SMTP remains absent: delivered means a private local .eml only.

### Fresh launch and stop

Use installed PowerShell7 and the repository-local .venv; no package install:

```powershell
& scripts/dev-accounts.ps1
# In a separate terminal, use only the exact session_directory emitted above:
& scripts/dev-accounts.ps1 -Stop -SessionDirectory '<current owned session_directory>'
```

The launch JSON reports backend_origin=http://127.0.0.1:3320,
frontend_origin=http://127.0.0.1:3319, session_directory, context_file,
credentials_file, mailbox_directory, exact container_id and owned child pid.
Only locators and nonsecret status are logged. Never print/copy the credential
contents or private mailbox links into test output, public assets or browser
persistent storage. The completed verification's locators are historical and
ABSENT, so the next worker must launch a fresh owned fixture, not reuse its session.

Under the current verified private session directory:

| File | Authorized use |
|------|----------------|
| context.json | Nonsecret org/area IDs, labels and explicit local schema/profile flags; not an auth grant. |
| admin-credentials.json | Owner-only generated fixture email/password for normal POST/forge/v1/accounts/login; never public. |
| mailbox/*.eml | Owner-only local invitation/reset messages; capabilities remain in URI fragments. No public listing endpoint. |
| ownership.json / stop.request | Exact-session ownership marker / graceful stop signal, never arbitrary process kill. |

Next frontend routes use the real account API: POST/forge/v1/accounts/login,
POST/forge/v1/accounts/invitations, POST/forge/v1/accounts/invitations/accept,
POST/forge/v1/accounts/logout, password-reset/request and password-reset/consume,
and GET/forge/v1/bootstrap?organization_id=UUID with genuine session bearer.
Only origin3319 receives CORS authorization, cookies are not credentials, and
client-supplied roles/identity headers never grant access. Initial invitations do
not reset existing accounts or grant membership before acceptance.

Rollback boundary for this uncommitted U3a unit: remove only dev_accounts.py,
dev-accounts.ps1 and test_dev_accounts.py and revert this U3a task section; existing
U1/U2 services/migrations/native runtime remain unchanged. No Git operation was
performed. Independent verification and actual frontend onboarding E2E are the
next authorized boundaries, not part of this backend-only delivery.

## Released durable NEW local demo (D1–D5)
User approved a NEW durable demo; every previous demo folder/container remains
untouched. No old-data restore or production deployment claim. This is delegated
direct because private state, Docker identity/lifecycle and real process restart
proof require coordinated files. Forecast650–1000 readable lines, advisory only.
Exact surfaces: src/forge/dev_accounts.py (optional compose inputs only),
src/forge/dev_accounts_persistent.py, scripts/dev-accounts-persistent.ps1,
tests/test_dev_accounts_persistent.py and this task. No delete/reset operation,
network/pull/install/remote/key adoption, native/Gentle/Git or client edits.

- [x] D1 — Protect a fresh owned directory under current-user LocalAppData/PrometheonForge/demos/forge-owned-accounts-NEW_UUID; verified user/SYSTEM ACL before secret writes. Hold exclusive OS file lock; never infer live ownership from old PID.
- [x] D2 — Create one fresh labelled exact named Docker volume/container, cached digest-pinned --pull=never PostgreSQL17 and loopback port. Verify ownership/image/mount/labels before start/resume/stop; old resources untouched.
- [x] D3 — Apply reviewed0001–0004+0013–0014 and seed once only; retain admin/role/PostgreSQL credentials and explicit Fernet key privately. Existing DB resume performs no migrations/reseeding and requires current exact schema readiness.
- [x] D4 — Graceful stop closes serving/pools and stops only exact owned container; retain named volume/context/mailbox/credentials. Resume after a separate process start/reboot uses validated stable state. Interrupted initialization fails closed and preserves artifacts, no destructive repair.
- [x] D5 — Meaningful RED/GREEN pure contracts plus actual separate-process create/login/invite/recipient-accept/stop/resume, stable identities/passwords/context/key/volume and duplicate/tampered rejection. Existing ephemeral regression, syntax/diff and full mirror readback. Verification demo distinct from eventual user demo; preserve test data, stop its processes. User demo launch waits for independent checks.

Persistent context remains disposable_local_fixture=true and enterprise_profile_configured=false;
persistent_local_demo=true distinguishes retention, not production readiness.
Stable gateway secrets are explicitly excluded. Windows ACL is a local protection
boundary, not encrypted backup or production secrets management. No automatic
container recreation/volume adoption if an existing state identity is missing.

### Durable verification and frozen handoff

D1–D5 are writer functional proof, not independent approval or production rollout.
Canonical approved root is
C:/Users/JuanpabloBayona/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/PrometheonForge/demos.
The packaged application virtualizes the originally proposed LocalAppData path;
the explicit canonical package directory is also addressable by an outside
PowerShell process. Reboot survival is supported; app uninstall survival is NOT
promised. Source emits the canonical context/credential/mailbox paths.

Observed checks, in order:
- Meaningful contract RED:2 methods/6 assertion failures with importable stub;
  implemented guards GREEN2/2.
- First actual lifecycle failed before database start on Windows CRLF versus LF
  private Docker config bytes. Exact normalized-text check fixes that mismatch;
  ownership/image/mount/schema checks remain intact. Initializing data retained.
- Next fresh attempt rejected packaged path redirection before creating resources;
  parent explicitly authorized the canonical physical root before continuation.
- Corrected actual run passed login/bootstrap/invite/accept, then test-only account
  identity SELECT failed because a newly reconstructed probe had no assigned
  loopback port. Probe now uses the verified owned container mapping; no default
  port is selected for a running database. Runtime was not changed for this fix.
- An accidentally concurrent ephemeral regression reported2 occupied-port errors
  while this owned durable runtime reserved3320. Final checks ran SEQUENTIALLY.
- Final `.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_dev_accounts.py -v`:
  11pass,1 explicit integration skip,9.016s,exit0. No claim that skipped ephemeral
  Docker integration executed.
- Final same unittest command with `test_dev_accounts_persistent.py`, enabled by
  explicit FORGE_RUN_DURABLE_DEMO_INTEGRATION=1:3/3pass,76.776s,exit0. Actual
  create/adminlogin/private-eml/recipientaccept/stop/separate-process-resume;
  same2 account identities and membershipIDs, both original passwords, stable
  admin/role/PostgreSQL credentials/Fernet key/context/volume; duplicate launch
  and tampered owner denied. Every verification runtime stopped, data retained.
- Python AST3files and PowerShell parser passed; scoped git diff --check and new
  authored-file trailing-whitespace scan passed. New runner/wrapper/tests759lines,
  plus narrow optional delivery-key/mailbox composition inputs and this document.
  No installers, commits, staging, native review or remote requests occurred.

Retained verification artifacts only (never the eventual user demo):
| Instance suffix | Container ID | State |
|-----------------|--------------|-------|
|03a35642b48b4f31966d329ace5890aa|5e592c37eddd268eb22b71777530ffadb7ca046687a1b9903a7549bd78f5de44|stopped, initialization incomplete|
|ed7ac3f8b431445e974c8431329707c8|efcc8e7daf920794008d972aa17dcfe03a0b93d4a86f839516d6f053d72da1cb|stopped, ready preserved|
|9eef629812a44baea7e0b1a9ff651d3e|d5c4c52294a2a8c0463ba71a8e293cf8a3a25fccc593508bca30e9b0b7a70078|stopped, complete restart proof|
Directories are canonical-root/forge-owned-accounts-SUFFIX; volumes are
forge-durable-accounts-data-SUFFIX. No directory/container/volume was removed,
no old demo resource was adopted/stopped and no gateway credential was persisted.

Copyable commands (PowerShell7, repository root):
```powershell
./scripts/dev-accounts-persistent.ps1 -Create
./scripts/dev-accounts-persistent.ps1 -Resume -DemoDirectory 'CANONICAL_READY_DEMO_DIRECTORY'
./scripts/dev-accounts-persistent.ps1 -Stop -DemoDirectory 'CANONICAL_READY_DEMO_DIRECTORY'
```
Create returns nonsecret context and private credential/mailbox locators; the
password remains in the owner-only credentials file, normal password login only.
No user demo was created by this writer. Next: independent targeted lifecycle
verification, then parent-authorized fresh user demo launch. All earlier U1/U2
whole-baseline and native/production/UI limitations remain unchanged.

### Independent proof and active USER demo handoff

Parent reported independent durable lifecycle3/3passed80.119s, plus parent pure
contracts2pass/1 explicit lifecycle skip0.001s. These are separate observations
from writer76.776s proof. No new tests ran during this documentation-only closure.

A NEW USER demo was subsequently created and intentionally remains running:
- Instance suffix:a23d454a633746a292166e42c1167d62; canonical directory under the
  exact approved package root above, named forge-owned-accounts-SUFFIX.
- Existing owner-only admin-credentials.json and nonsecret context.json remain
  private in that directory; no secret contents are recorded here.
- Parent actual backend health/login/bootstrap/logout returned200/200/200/204.
- Backend owned tool session92699, PID23940; workspace owned tool session31299,
  ownerPID26916, API12688 and Next24872. IDs are observed handoff locators,
  never authority to kill/adopt a process without exact resource validation.
- Client /c/new compiled in139.1s after an initial180s timeout. Compilation/HTTP
  availability is NOT actual UI interaction proof: parent browser control was
  blocked by URL policy, and no workaround was attempted.

Backend/client sessions were deliberately kept running for the user. Previous
artifacts and all three verification containers/volumes remain retained. This
closure changes only this document/fullforge3010mirror; no source edits, restart,
new launch, test, install, Git or native review operation. Full legacy regression,
actual UI interaction, native review and production readiness remain unclaimed.
The previous 'no user demo created by this writer' statement is historical and
still accurate; parent performed the subsequent authorized user launch.

For the active user demo, stop/resume only through the validated durable wrapper:
```powershell
./scripts/dev-accounts-persistent.ps1 -Stop -DemoDirectory 'C:/Users/JuanpabloBayona/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/PrometheonForge/demos/forge-owned-accounts-a23d454a633746a292166e42c1167d62'
./scripts/dev-accounts-persistent.ps1 -Resume -DemoDirectory 'C:/Users/JuanpabloBayona/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/PrometheonForge/demos/forge-owned-accounts-a23d454a633746a292166e42c1167d62'
```
These commands concern only the accounts backend; workspace/client resources
remain owned by the parent launch session. No automatic process-name cleanup.

## Central gateway composition follow-up (CG3b, isolated implementation only)

The central-gateway feature task `odd/tasks/forge-central-gateway.md` owns the
explicit stopped-instance UpgradeGateway implementation and recovery proof.
Legacy create/resume semantics, delivery key/old roles and current a23d USER demo
remain unchanged. Normal Resume never migrates or repairs incomplete upgrades.
A separate protected gateway key/service-role file exists only after explicit
upgrade; no gateway key was added to the current running demo.

CG3b self-proof: new retained named-volume fixture5pass48.124s with actual
upgrade child and database stop/start; focused owned PostgreSQL1comprehensive
pass16.288s verifies commit/journal/promotion recovery and preserved real
accounts/passwords/memberships/invites/sessions/mailbox/old credentials.
Existing persistent contracts2pass1skip0.001s; fixed3320 legacy runtime lifecycle
was not rerun. Independent checking and a separately authorized actual USER
upgrade remain pending. See central-gateway task for exact stopped test artifact
identities, static checkpoints, failure history and bounded launch commands.
