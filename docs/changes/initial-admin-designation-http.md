# Initial administrator designation HTTP adapter

## Decision and status

Add an opt-in synchronous HTTP adapter over the existing InitialAdministratorService.
The bounded F07b2a-http adapter is implemented and independently verified locally;
the parent authorized its local work-unit commit. It does not make Forge publicly deployed or admin-ready.

Task: odd/tasks/forge-initial-admin-http.md.
Parent: odd/tasks/forge-administration.md.
Existing service: src/forge/administration.py and administration_store.py.

## Request and successful response

POST /forge/v1/organizations/{organization_id}/initial-administrator

Trusted application composition explicitly supplies the keyword-only
initial_administrator_service to create_app. The default is None; create_runtime_app
does not acquire a pool, load operators or auto-wire this service.

The path organization_id is a UUID. JSON accepts exactly membership_id and
operation_id UUIDs plus expected_revision, an integer from 1 through 2**63-2.
Booleans, floats and strings are not revisions; extra fields are rejected.

Accept exactly one Bearer header and a nonempty token without whitespace or comma.
Missing, duplicate, malformed or comma-combined headers return401. No credentials
are accepted from query/body or interpreted as roles, actors or a bootstrap principal.

The route calls service.designate once with the raw token and a typed
DesignationRequest. Service authority is unchanged: actual Entra authentication and
deployment-owned operator/tenant configuration run for every valid attempt, even
an exact replay. No adapter cache, validator shortcut or write retry is introduced.

A 200 response contains only four UUID fields organization_id, membership_id,
operation_id and event_id, the integer revision=expected_revision+1, and
audit_publication="pending". Check exact service result/type/correlation before
serialization; do not coerce strings/bools/dicts or accept a mismatched result.
Pending means the existing transaction committed an outbox intent, not publication.

## Failure contract

| Condition | HTTP | Fixed code |
|---|---:|---|
| Missing/malformed credential syntax | 401 | UNAUTHENTICATED |
| Body/path validation failure | 422 | INVALID_REQUEST |
| Service authentication or authorization denial | 403 | DESIGNATION_DENIED |
| Service revision/permanence/replay conflict | 409 | DESIGNATION_CONFLICT |
| Absent injection, unavailable service, malformed result or unknown exception | 503 | SERVICE_UNAVAILABLE |

Use the existing redacted ErrorEnvelope and fresh request UUID. Never return
validation diagnostics, supplied values, exception details, tokens, claims, PII or
configuration. 401 includes WWW-Authenticate: Bearer; only 503 is retryable.
Service denial deliberately conflates invalid authentication and missing operator
authority, so the adapter does not invent a second parsing or authentication pass.
Valid bearer without configured injection cannot borrow a database connection.

## Isolation and non-goals

Keep the route and credential dependency synchronous to avoid blocking the event
loop with crypto or DB calls. Preserve existing bootstrap semantics and explicitly
disabled telemetry; add no global logging or tracing. Existing SQL service owns
atomic grant/revision/outbox and replay guarantees.

No changes to migrations, service/store, runtime, Entra, old tests or fixtures.
No removals, reassignment, last-administrator recovery, activation, self-signup,
provisioning, outbox consumer, browser UI, production credentials or public exposure.

## Evidence plan

1. Add new HTTP tests and observe assertion-based RED before editing the API.
2. Verify strict request/result types, header matrix, redacted errors, per-attempt
   service call count and execution outside the event-loop thread.
3. Use actual RSA-signed Entra tokens and the existing owned PostgreSQL harness
   through HTTP for atomic success, exact replay, conflict, authority failures and
   rollback; inspect resulting rows and no second event/revision.
4. Run protected regression suites, compileall, pip check and diff check; perform
   existing-tools-only offline wheel/fresh-import checks where supported.
5. Independent verification and parent spot check precede separate local commit
   authority. Preserve historical 266 proof as history, not a new test result.

Rely only on cached ephemeral local resources with exact owned-ID cleanup.
RDD remains OFF; no native review, remote operation or deployment is implied.

OpenAPI numeric maximum passes through a floating-point framework schema model;
the field description states the exact integer maximum, while runtime validation
enforces the precise strict bigint bound. Header parsing uses the raw value because
HTTPBearer may normalize surrounding whitespace before returning credentials.

## Local candidate evidence

Writer checks passed 296 tests: 266 rerun baseline plus 21 HTTP and nine real
PostgreSQL HTTP tests. Exact counts, durations, intermediate failures and cleanup
are recorded in the child task. Offline wheel/fresh-import/resource/route checks
passed without installation or download. Independent verification also passed 296
tests without concrete defects; parent spot passed 21 HTTP tests. Local commit is
authorized, not deployment. Starlette's httpx TestClient deprecation warning is a
nonblocking follow-up; no dependency upgrade is included.
