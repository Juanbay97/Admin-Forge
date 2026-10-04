# Forge identity delivery

## Current outcome and release gate

F06 completed: writer 113 tests, independent checks/P2 retest and parent spot check
passed. Parent-authorized local behavior/test/docs commit identity and exact stats are
recorded below. Source release followed mirror 2468/readback.
No live tenant enrollment, desktop sign-in, UI or runtime composition is enabled.
Gentle AI review GLOBALOFF: disabled/unmanaged, no calls or consent prompt.

## Objective, problem and inherited evidence

Provide the missing trusted token validator without weakening default-deny API
or organization/membership checks. PF-02/PF-10/PF-12 constrain identity, HTTP/data
contracts and proof. Current-unit Spanish SDD: docs/changes/entra-token-validation.md.
Closed foundation remains in odd/tasks/forge-foundation.md; recovery mirror topic
odd/forge-foundation/tasks, observation 2374. F05b behavior commit:
279905eae2113c40749d5ac6fa9358cdce1b85d8. Current baseline:
f44032ea175c9197eb8cdca1f28348ce4fc6bd44. Recorded independent/parent proof:
44 PostgreSQL +13 foundation +18 HTTP tests, exact owned-container cleanup.
This is historical evidence, not a new run or proof of Entra.

## Work units

- [x] **F06 — Backend Entra v2 validator (current authorized unit).**
  Explicit trusted config, immutable verified principal, bounded discovery/JWKS,
  real RS256, offline cryptographic/HTTP tests and docs.
  Route: delegated direct; preparation reading and multiple non-trivial files.
  Closure: writer/independent/parent proof passed; local coherent commit authorized.
- [ ] **F07 — Persistent identity binding and provisioning (future; not released).**
  Refine migration/service scope before edits: explicit tid/oid persistence,
  canonical provider linking, object/invitation confirmation and idempotent outbox.
  No automatic email matching, membership/admin assignment or tenant signup.
- [ ] **F08 — Configured runtime composition and readiness UI (future; not released).**
  Refine trusted deployment inputs and truthful readiness independently of liveness.
  Default application remains deny-all until deliberately composed.
- [ ] **F09 — Desktop PKCE, protected storage and enrollment spike
  (future; not released).** Refine platform/client scope; obtain explicit account,
  tenant, application-registration and staging authorization before live work.
  Public client has no secret; no plaintext corporate token files.

Future checkboxes preserve sequence only, never authorize implementation.

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

## Exact allowed edit surfaces after parent release

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

## Test-first policy and exact checks

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
never code-golf or omit evidence. F07-F09 forecasts await bounded scoping.
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

## Local delivery evidence

Observed behavior commit: 279fef10e248d25e72bb943ff08348600d4b6231
(feat(auth): validate Entra access tokens), existing feat/forge-tenant-storage branch.
Exactly six approved files:1488 additions +2 deletions =1490 authored lines.
No source bytes changed during final documentation closure or commit; source/test/
manifest blobs match the independent accepted candidate. Protected surfaces unchanged.
No active commit hooks; clean checkout observed immediately after behavior commit.
Git emitted existing automatic-identity notice; no config change/amend or AI attribution.
This small task-only follow-up records the actual hash without future self-reference.
No push, PR, merge, remote/production/account action or Gentle AI operation.

## Recovery and next step

Engram project prometheon-forge; no authoritative session ID, omit session_id.
Parent owns final full mirror topic odd/forge-identity/tasks and readback.
F07 remains future/not released: explicit persistent tid/oid linkage is required
before live enrollment. Scope migrations/service binding and provisioning separately
after bounded exploration; this closure does not authorize either implementation.
F08 runtime composition/readiness UI and F09 desktop PKCE/protected storage/live
enrollment stay pending. Preserve closed foundation proof and current branch chain.
