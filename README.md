# Prometheon Forge

An organization-aware agent platform with executable domain contracts and a
**default-deny HTTP bootstrap**. Scoped PostgreSQL storage, strict Entra v2 token
adapters, explicit existing-identity binding and opt-in local runtime composition
have local/offline proof. A read-only runtime status screen is available; live
corporate enrollment, desktop sign-in, administration and effective capabilities
are not integrated.

## Local setup and checks

Requires Python 3.12 or newer. Use a repository-local virtual environment; do not
modify a shared runtime. Runtime pins are FastAPI 0.142.2 and uvicorn 0.54.0;
the test extra pins httpx 0.28.1 and psycopg[binary] 3.3.6. Tests use unittest.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-input --keyring-provider disabled ".[test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_foundation.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py -v
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pip check
```

For local process-liveness and default-denial smoke:

```powershell
.\.venv\Scripts\python.exe -m uvicorn forge.api:create_app --factory --app-dir src --host 127.0.0.1 --port 8765
```

`GET /healthz` returns `{"status":"ok"}`. It is not readiness. Anonymous requests
and every bearer token are rejected by the default application with structured
401 `UNAUTHENTICATED` and `WWW-Authenticate: Bearer`. Stop the server after checks.
OpenAPI is available at `/openapi.json`; bootstrap requires an organization UUID.

## Trusted integration boundary

`forge.api.create_app(token_validator=..., bootstrap_reader=...)` accepts typed
synchronous ports executed in FastAPI's worker pool, not on the event loop:

- `validate(token)` returns a genuinely validated `AuthenticatedIdentity` or None
  for rejection; operational exceptions become redacted 503 errors.
- `read(identity, organization_id)` reloads scoped records for every request;
  missing/inconsistent/foreign context is hidden as 404. Only correctly scoped,
  owned suspended membership can return `MEMBERSHIP_SUSPENDED` 403.

Injection is not authentication. A real corporate adapter must validate the
provider signature, algorithm, issuer, Forge audience, validity, allowed tenant
and scopes. Identity headers/cookies, fixture data and fake-auth switches are not
supported. Internal configuration is never expanded into the public response.

The transport reuses `forge.foundation.build_public_bootstrap`: schema version,
public organization fields, membership ID and configuration revision only. No
secrets, costs, admin settings or invented capabilities. Domain tests do not prove
JWT validation or PostgreSQL/RLS. No production, provider or upstream state changes.

## Delivery and evidence

See `docs/sprints.md`, `docs/changes/foundation.md`,
`docs/changes/api-bootstrap.md` and `odd/tasks/forge-foundation.md`.
The HTTP unit passed local, independent and parent functional checks (31 tests).
Local commit evidence is recorded in the task document. No native review approval
is claimed. That historical HTTP unit had no screen; current F08a status UI checks are separate.

Starlette 1.7.0 emits an httpx TestClient deprecation warning; the pinned test extra
currently passes the entire suite. Do not silence this warning or add unapproved
dependencies to imply future compatibility.

## Mandatory local PostgreSQL proof

The two explicit unittest patterns above run 13 domain and 18 HTTP tests without
a database. Unqualified discovery also includes the mandatory real-DB suite and
requires the disposable harness; it never substitutes SQLite/mocks or silently skips.

After installing the test extra, with Docker Desktop's local Linux engine running:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-postgres.ps1
```

The pinned official PostgreSQL image must already exist locally; normal tests use
`--pull=never`, private empty Docker config and explicit local named pipe. For an
explicitly authorized initial image acquisition, use a private empty config and
that local pipe to pull the exact reference in `scripts/postgres-image.txt`, not a
floating tag. No ambient Docker credentials/contexts or existing databases are used.
Each run creates a unique owned container with loopback-only dynamic port and tmpfs,
then removes only its captured ID/storage in finally. Passwords are random/in-memory.
Missing dependencies/image/harness settings fail clearly; no network auto-recovery.

Observed local proof: PostgreSQL 17.11, F05a RLS RED then 22/22 GREEN; F05b
reader-stub RED then 44/44 DB GREEN (22 RLS, 14 reader, 8 DB-backed HTTP), plus
13 foundation and 18 HTTP regressions unchanged. Migration is one-shot for a
pristine dedicated Forge DB with
reserved roles, not an upgrade runner for shared/production databases. Default API
still denies all real tokens. F05a independent verification and parent spot check passed;
F05a local commit evidence is recorded in the task. F05b writer and independent
checks passed (44 DB +13 foundation +18 HTTP); parent repeated all 44 DB tests with
PostgreSQL 17.11 and confirmed owned-container cleanup. The coherent local behavior commit completed;
its observed identity and authored count are recorded in the task.
GentleAI verification is explicitly disabled (GLOBALOFF): ordinary checks only,
disabled/unmanaged, no native approval.
See `docs/changes/postgres-bootstrap.md` and `odd/tasks/forge-foundation.md` for
exact pins, recovery failures, command results and remaining scope.

## PostgreSQL bootstrap reader

`forge.postgres.PostgresBootstrapReader` implements the existing synchronous port.
Composition injects an externally managed `psycopg_pool.ConnectionPool`; the reader
never reads a DSN/environment, provisions credentials, opens or closes that pool.
Connections must be idle and `autocommit=True`, use the migration's SELECT-only
`forge_runtime` role and have bounded connection/statement timeouts set by the
trusted deployment. The reader checks live role attributes/ownership/RLS/grants,
uses one outer transaction, parameterized transaction-local identity/org settings
and one joined snapshot. It rejects dirty transactions rather than using savepoints.
Acquisition defaults to one second and permits a finite override in (0, 30].

```python
from forge.api import create_app
from forge.postgres import PostgresBootstrapReader

# Trusted composition supplies an already configured/opened pool and real validator.
app = create_app(
    token_validator=corporate_validator,
    bootstrap_reader=PostgresBootstrapReader(managed_pool),
)
```

Composition owns pool open/wait/close and credentials; this example does not supply
corporate sign-in or production wiring. The default app still rejects every token.
Records are reread for every request; archived/foreign/missing context stays 404,
owned suspension is 403 only after existing consistency checks, operational failures
remain redacted 503. Public bootstrap fields are unchanged. Test fixtures/synthetic
validation live only under tests and are never imported by the runtime reader.

Runtime pins: psycopg/binary 3.3.6 and psycopg-pool 3.3.3; httpx is test-only.
The owned harness runs all `test_postgres_*.py` modules in one child process, not
only RLS. Direct DB discovery without explicit owned-harness configuration fails
clearly when the owned harness is not configured, rather than silently skip.
Real size-one pool tests cover same backend reuse after success/error, concurrent
serialization, fresh revocation/configuration, role misconfiguration and DB HTTP.

## Offline-proven Entra v2 access-token adapter

F06 supplies an explicit trusted adapter, not live corporate sign-in. Runtime pins:
PyJWT[crypto] 2.15.1 and cryptography 50.0.2. Run its real-RSA/JWKS/transport/HTTP
tests without an account or network:

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_entra.py -v

Trusted composition constructs EntraConfiguration with allowed_tenants, audience
(the Forge resource API GUID), allowed_clients (public-client GUIDs), and
required_scopes; all nonempty allowlists are bounded. EntraTokenValidator accepts
that configuration plus optional trusted fetcher/clock/ValidationLimits injections.
Pass it to create_app(token_validator=..., bootstrap_reader=...) only through trusted
composition. No environment token, fake identity, client secret or email linking.

The immutable verified principal preserves actual sub, tid and oid separately.
Domain identity is provider entra + exact validated tenant-v2 issuer + canonical
oid GUID: subject means the Forge provider principal, NOT raw OIDC sub.
This intentionally links one tenant object across client-specific subjects without
joining objects from different tenants or guest home identity providers.
F07a provides the internal bind-existing boundary below; explicit authorized
binding and future onboarding remain necessary before real enrollment.

Defaults: 16 tenant/32 client/16 scope entries, 16 KiB JWT, 128-character kid,
256 KiB discovery/JWKS response, 64 keys, 1-hour tenant cache, 60-second refresh
cooldown (also after failure), two concurrent fetches, 3-second socket/lock admission
timeout and 60-second clock skew. Fetch reads check a 6-second deadline before/after
each bounded read; DNS scheduling follows the OS, not a claimed end-to-end SLA.
Transport disables ambient proxies, redirects and credentials; only exact configured
Microsoft tenant metadata and official tenant/common v2 keys URLs are fetched.
Expired cache never becomes a fallback; unavailable metadata yields redacted 503.
Unknown kid refresh is cooldown-limited; invalid tokens yield 401 before reader calls.
A valid cached key may remain usable through a refresh failure only until its TTL.

Scopes, audience, tenant, issuer, authorized client and real fixed-RS256 signature
must all match; ID/Graph/app-only tokens never replace a Forge delegated access token.
The resource registration later needs requestedAccessTokenVersion=2.
The default factory remains unconfigured/deny-all; /healthz is still liveness only.
No tenant enrollment, PKCE client, refresh-token storage, provisioning, production
or staging account activity is implemented by F06. F08a status composition is below.

See docs/changes/entra-token-validation.md and odd/tasks/forge-identity.md.

F06 functional closure: writer 113 tests (38 Entra +13 domain +18 HTTP +44 DB);
independent original 111 plus P2 retest (38 and six oversized-date cases); parent
38-test spot check. The NumericDate P2 is closed; no live sign-in or native approval.
Local delivery evidence is recorded in odd/tasks/forge-identity.md.

## Explicit persistent Entra binding (F07a)

The additive `migrations/0002_entra_identity_binding.sql` follows the unchanged
0001 bootstrap. Nullable UUID `entra_tenant_id`/`entra_object_id` must be absent
together or present together with exact canonical Entra provider/issuer/subject.
An explicit unique pair and SECURITY INVOKER write-once trigger protect bound
metadata and identity fields. Existing generic identities and membership UUIDs
are unchanged; existing Entra rows are not automatically backfilled.

`forge.identity_store.PostgresIdentityBinder` exposes only
`bind_existing(existing_identity_uuid, verified_principal)`. It returns an immutable
`IdentityBinding` or None for an absent/mismatched identity; operational failures are
typed/redacted `IdentityBindingUnavailable`. It never inserts or relinks identities,
creates memberships, grants access, or matches email/raw sub. Repeated same-pair
bindings are idempotent, including concurrent calls. Guest objects remain scoped
to their resource tenant. Constructing VerifiedPrincipal is NOT authentication:
the trusted internal caller must validate the token and separately authorize
selection of the existing identity UUID.

A separate externally managed idle/autocommit pool must use
`forge_identity_binder`, not forge_runtime. The migration creates that restricted
NOLOGIN role with SELECT on identities and column UPDATE on the pair only;
credentials/LOGIN and pool lifecycle belong to future trusted composition.
Role/session/ownership/grant/RLS guards run on each borrow. Self-only RLS uses
transaction-local identity/principal context, not invented organization membership.
Acquisition defaults to1s within (0,30]; local lock1s/statement5s bounds are restored
on transaction exit. No public binder endpoint, bind-on-login or bind-on-read.

The reader now requires coherent persisted metadata for Entra only, still enforces
organization/membership/configuration checks, and rejects effective column-level
mutation privileges as well as table grants. Binding alone cannot create access.
The original identity policy is scoped to runtime/migrator roles; the binder has
its own self policy. The policy-test writer is explicitly added by tests only.

0002 uses a transaction, lock_timeout2s and statement_timeout10s. These bounds do
not implement deployment orchestration, migration history/version tracking or
safe downgrade of already persisted bindings. Run migrations only through a
trusted administrator in a dedicated Forge database with reserved roles;
deployment migration runner, onboarding/invitations/provisioning (F07b), production
TLS, PKCE/protected storage and live enrollment remain pending; F08a local status
composition is described below.

Writer follow-up proof: 73 PostgreSQL tests (25 binding/migration,17 reader,9 DB HTTP,22 RLS)
plus unchanged38 Entra+13 domain+18 HTTP =142, no skips. Real PostgreSQL17.11
fresh/populated upgrades, explicit rollback and an actual injected pre-COMMIT SQL
failure/aborted-transaction rollback used separately owned temporary databases in
the disposable cluster. Failed-migration readback preserves rows/RLS/policies and
leaves no new columns or binder role. No harness-script changes or dependencies.
HTTP binding tests use a test-only trusted identity port and real DB reader;
F06 continues to prove actual JWT crypto separately. Independent142 applicable
checks and parent73 DB spot passed. Local work-unit commit is authorized; actual
evidence is recorded in the task. Optional independent probe was blocked before SQL
by its15s readiness wait, not a defect verdict; see task history. No native approval
(GLOBALOFF).

See `docs/changes/entra-identity-binding.md` and `odd/tasks/forge-identity.md`.


## Explicit local runtime and read-only status (F08a)

Run the unconfigured, zero-storage/IDP-network status shell:
    ./.venv/Scripts/python.exe -m uvicorn forge.runtime:create_runtime_app --factory --app-dir src --host 127.0.0.1 --port 8765 --no-access-log

Open /status on that own loopback server. Local packaged HTML/CSS/JS have no CDN,
login, token input/storage, user administration or access controls. /forge/v1/status
publishes only seven fixed state fields; /healthz remains process liveness.
Unconfigured runtime does not inspect PG environment names, construct a pool or
validator, connect, resolve DNS or fetch signing metadata. Every token still rejects.
Stop only your own server after local checks.

Trusted deployment code may deliberately construct:
    from forge.entra import EntraConfiguration
    from forge.runtime import LocalDatabaseConfiguration, RuntimeConfiguration, create_runtime_app

    app = create_runtime_app(RuntimeConfiguration(
        entra=EntraConfiguration(
            allowed_tenants=provided_tenant_guids, audience=provided_api_guid,
            allowed_clients=provided_public_client_guids,
            required_scopes=provided_delegated_scopes),
        database=LocalDatabaseConfiguration(
            host="127.0.0.1", port=provided_port, dbname=provided_database_name,
            password=provided_runtime_password),
    ))

The provided variables above are explicit trusted values, NOT environment loaders
or default credentials. Only numeric canonical loopback, a bounded identifier DB
name, valid explicit port and nonempty bounded password are accepted. The database
role must be exactly forge_runtime, separately provisioned as restricted LOGIN.
Migrations 0001/0002/0003/0004 are applied externally by a trusted administrator; this factory
does not run migrations or bind/create identities or memberships.

Configured mode rejects presence of any PG* variable without reading its value,
both before pool creation and on connections, rather than letting libpq discover
services/password files. It never clears global environment state. Explicit password,
host/hostaddr, database/user, options, client encoding, auth and transport controls
are supplied. Supported linked client is libpq18+ (observed18.4 from psycopg-binary),
distinct from owned test server17.11. Fixed SCRAM-only auth, sslcertmode/channel
binding/SSL/GSS/load-balancing disabled and numeric host apply to this LOCAL profile
only; production TLS/remote profiles are not implemented.

The application owns an idle/autocommit sync pool min0/max2, maxwaiting4/workers2,
reconnect1s, connect2s, acquisition1s, open/wait5s and close5s. Lifespan and blocking
readiness work are off the event loop. Partial failures clean up; cleanup errors
are redacted and observable, not silently reported as success. Connection/rollback
exceptions and pool connection repr are redacted without global logging changes.
Queries use statement3s/lock1s. CacheTTL5s, single-flight refresh and completion-based
failure cooldown5s prevent probe floods; a positive result is valid only until TTL.
These finite library bounds are not a hard OS/DNS/request SLA.

Readiness checks actual restricted role/column privileges/RLS and catalog structure
for0001/0002/0003/0004, including nullable UUID pair, exact pair CHECK, uniqueness, enabled
invoker trigger, policy/helper prerequisites and selected-revision FK. No business
rows/counts or organization context are queried. This structural probe is not a
complete migration-byte/policy-body audit or a deployment migration-history runner.
Every bootstrap still independently validates its token and reloads membership.
Ready means local config+storage role/schema only: identity_provider stays
configured_unverified, onboarding not_implemented, user_access not_evaluated.
It does not establish live Entra connectivity, enrollment, admin readiness or access.

All runtime routes receive no-store, restrictive same-origin CSP, nosniff and
no-referrer headers. Fixed assets render fixed English labels with semantic
landmarks/live status, keyboard focus and responsive layout; unexpected status/fetch
failure cannot render raw errors or preserve a stale "ready" label.
The neutral-Spanish design and task record exact scope/proof/pending steps:
docs/changes/runtime-status.md and odd/tasks/forge-identity.md.

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/test-postgres.ps1

Build tools are development-only, not new runtime dependencies. Explicit setuptools
backend/package-data includes the three assets. The staged offline wheel command
uses --no-index --no-deps --no-build-isolation --no-cache-dir under ignored
.local/runtime-test; ZIP/importlib.resources proof is recorded in the task.
Both API factories explicitly disable native FastAPI tracing, metrics, logs,
operation spans and environment auto-configuration. Existing global telemetry
providers are neither inherited nor modified; raw query/validation input is not
sent to those providers by Forge native instrumentation. External middleware or
host instrumentation is outside this guarantee.

Available browser functional proof is accepted for this LOCAL operational shell;
full network capture, actual screen-reader announcement and transient-loading
certification remain explicit follow-up evidence, not delivery claims. Independent
telemetry correction retest and parent spot passed. No live accounts, production, binder/login
wiring, F07b invitations/outbox publication or F09 PKCE/protected storage/enrollment are implemented.


## Internal membership authorization read model

Migration0003 follows0001/0002 externally: positive membership revision default1
and organization-scoped membership_roles with composite PK/FK, four exact role
values and ENABLE/FORCE RLS. New role-row RLS also requires complete coherent
persisted Entra tenant/object binding; generic providers and older policies are
unchanged. It seeds no roles or administrator. Runtime remains
SELECT-only on all five tables including column-grant restrictions; the identity
binder receives no role/revision access. Runtime readiness now requires0003 and
checks its metadata/privileges without organization context or business rows.
No migration runner is provided; deployment must apply the ordered migrations.

AuthorizationSnapshot and permits are internal trusted-data policy, not token
validation or a reusable write capability. Only organization_admin permits exact
members.invite/update/suspend; missing/unknown actions or any unknown mixed role
deny. platform_operator is not an organization role. Frozen snapshots copy role
sets without coercing their values; revision is a positive bigint observation,
not an implemented mutation/If-Match guarantee.

PostgresAuthorizationReader uses an externally owned restricted sync pool and one
parameterized business SELECT for canonical bound Entra identity, active owned
membership/organization, current revision and roles. No authorization cache,
email/sub fallback, claimed JWT/request roles, HTTP endpoint or login wiring.
Operational errors are fixed/redacted; idle-autocommit/clean-context guards and
local search_path/statement3s/lock1s restore after each transaction; acquire1s
(default, finite override within(0,30]). Future writes must revalidate inside the
same audited transaction/outbox, not trust an old snapshot.

Run tests/test_authorization.py and the unchanged scripts/test-postgres.ps1 owned
harness. Exact task/proof: odd/tasks/forge-administration.md; neutral-Spanish SDD:
docs/changes/membership-authorization.md. First-administrator recovery,
last-administrator policy, member mutations and invitations/provisioning remain
separately scoped future work; no administrative permissions are granted here.
F07b1 closes only this internal read model, not an administration API or bootstrap.


## Internal initial-administrator designation

Migration0004 follows0001–0003 externally. It adds a permanent per-organization
initial_admin_designations marker and real initial_admin_outbox audit records;
there is no role backfill or administrator seed. Runtime SELECT is explicit on
five business tables only, with zero table/column access to operational or unknown
Forge tables. Binder has no new access. Catalog-only readiness attests the new
role, exact constraints/helper/policy shapes, restrictive scope and privilege
matrix; this does not configure a live operator or authorize deployment.

Trusted deployment code must explicitly compose InitialAdministratorService with
the actual EntraTokenValidator, an immutable DesignationConfiguration and a
PostgresInitialAdministratorStore over a separately provisioned forge_designator
LOGIN pool. Configuration requires exact validated issuer/tenant/object operator
allowlist entries mapped to trusted internal actor UUIDs and an explicit
organization→allowed target-tenant mapping. No defaults, environment discovery,
request actor, JWT/email/tenant-admin roles or first-login inference are accepted.
Every attempt, including replay, validates its raw token before database access;
missing/empty authority or missing organization mapping denies before borrowing.
Constructing DeploymentOperator or VerifiedPrincipal is not authentication.

DesignationRequest contains organization/membership/operation UUIDs and a positive
expected revision (maximum2**63-2). Only an existing active, coherently bound Entra
membership in that exact organization and mapped tenant may receive the initial
organization_admin role. A claim plus locked reload atomically commits role,
revision increment, marker and fixed server-derived PF09 event. Existing admins,
stale revision, changed replay payload, missing/wrong target or event failure
cannot leave partial writes. Exact authorized replay returns the original result
without regranting or incrementing; the permanent marker prevents reopening after
later role removal. An inactive organization remains inactive and runtime access
continues to deny.

The dedicated non-owner, non-member, non-bypass designator can only read scoped
metadata, UPDATE membership revision, INSERT the scoped administrator role and
INSERT/replay-SELECT its operational records. Restrictive role policies prevent
legacy PUBLIC policy OR-expansion. No identity/member creation, status/org change,
audit UPDATE/DELETE, DDL or table-wide UPDATE. Idle/autocommit/clean-context and
live role/column guards apply on each borrow; acquisition1s (finite override within
(0,30]), statement3s/lock1s and local contexts restore on completion or rollback.
Migration lock2s/statement10s are bounds, not an implemented migration runner.

Frozen DesignationResult reports audit_publication="pending": outbox INSERT is
NOT publication, enrollment or external provisioning. The internal service does not
wire HTTP/UI/operator runtime configuration. The opt-in HTTP adapter below is
separate; real operator configuration, consumer, removal/recovery/last-administrator
policy and production readiness remain outside both units.
Run tests/test_administration.py and the existing owned PostgreSQL harness.
Task/proof: odd/tasks/forge-administration.md; neutral-Spanish design:
docs/changes/initial-admin-designation.md.


## Opt-in initial-administrator HTTP adapter

Trusted composition may explicitly pass
`initial_administrator_service=service` to `create_app`. The parameter is
keyword-only and defaults to `None`; `create_runtime_app` does not auto-wire it,
discover operators, create a designator pool or enable public deployment.

`POST /forge/v1/organizations/{organization_id}/initial-administrator` accepts
one Bearer header and a closed JSON body containing UUID `membership_id`,
UUID `operation_id` and strict integer `expected_revision` (1 through
9223372036854775806). Extra fields and coerced revisions are rejected. Every
valid attempt, including replay, calls the existing service with the raw token.
Only its genuine Entra validation and deployment-owned configuration authorize
the operation; bootstrap identity, client roles and claimed actor fields do not.

The 200 response contains only organization/member/operation/event UUIDs,
committed revision and `audit_publication="pending"`. Malformed service results
fail closed without coercion. Header syntax errors return 401; service denial
(including bad authentication or unauthorized operators) returns 403; conflicts
return 409; request validation returns 422; absent injection, service outages and
unknown failures return 503. All errors use fixed redacted envelopes with fresh
request UUIDs. The sync adapter preserves disabled telemetry and existing bootstrap.

This is initial designation only, not removal, reassignment, recovery, provisioning,
outbox publication, UI or production readiness. Run
`tests/test_administration_api.py` and the unchanged owned PostgreSQL harness
(which discovers `tests/test_postgres_administration_api.py`).
Design: `docs/changes/initial-admin-designation-http.md`.
Recovery/proof: `odd/tasks/forge-initial-admin-http.md`.
