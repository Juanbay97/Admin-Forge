# Central gateway configuration and owned-account catalogue (Units1–2)

Organization administrators can store a gateway credential through the genuine Forge account API. Configuration is encrypted, revision-controlled and redacted. **SAVED_UNVERIFIED does not mean the credential works.** Unit1 performs no network request. Unit2 adds bounded server-side model discovery and owned-account catalogue publication, not inference. The running durable demo is unchanged.

## API contract

| Operation | Contract |
| --- | --- |
| GET `/forge/v1/orgs/{organization_id}/gateway` | Genuine session, current active same-org administrator; returns status, revision and fixed endpoint only. |
| PUT same path | Strict `expected_revision` and write-only ASCII `api_key` (1–4096 characters), bounded body. Expected0 creates; subsequent writes compare the observed revision. |
| Redacted state | NOT_CONFIGURED/revision0 or SAVED_UNVERIFIED/currentrevision, endpoint `https://ia.prometheonlab.com`. |
| Denial | Missing/revoked session401; unrelated/nonadmin/inactive scope404; stale revision409; invalid request422; missing composition/readiness/encryption failure503. No private diagnostics. |

## Explicit opt-in composition

Apply reviewed0001–0004 and0013–0015 only through an authorized installer in a new/explicitly upgraded account deployment. Supply distinct restricted account/bootstrap/gateway pools, `GatewayAccountReadiness`, actual `SessionService`, `PostgresGatewayStore`, `GatewayConfiguration` and `PostgresAuthorizationReader` to `create_account_app`. The gateway Fernet key must be explicitly supplied and separate from invitation-delivery encryption. The factory's optional gateway service defaults unavailable; no environment/key discovery, network fallback or fixture identity exists.

Do not append0015 to the current persistent demo or alter its private state shape/migration manifest. Its exact legacy account readiness intentionally rejects the new profile. Durable upgrade/composition and central inference belong to later feature units.

## Security boundary

- Separate `forge_gateway_service` can execute only gateway read/save functions, not directly inspect configuration or business tables. Internal owners remain NOLOGIN/nonbypass; new tables use FORCE RLS and organization scope.
- Existing session/account/organization/member/identity/administrator locks are freshly revalidated within the transaction. Python authorization snapshots are fast-deny observations, not mutation capabilities. Logout, credential revocation and role removal are not replaced with request claims.
- A narrow resolver owned by the established enrollment authority avoids expanding new authority access to baseline identity tables. Public-policy ACL dependencies remain intact.
- Fernet ciphertext binds organization, random bindingID, revision and fixed endpoint. Wrong encryption key, substituted binding/revision/org or malformed ciphertext fails closed. No key/cipher in public response, object repr, generic error or audit. Audit contains organization/revision/internal actorID only.
- CAS and audit update share one transaction. Rollback preserves previous configuration; concurrent same-revision writers produce one success/one conflict.
- Separate PostgreSQL17 exact catalog fingerprint attests functions, schemas, grants, role edges, constraints, indexes, policies and authority NOLOGIN. It is a reviewed build/test artifact, never runtime learned. Legitimate service/bootstrap LOGIN provisioning remains supported.

## Verification

Use the worktree-local Python and the existing owned PostgreSQL runner, not the running demo:

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_gateway_configuration.py -v
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_gateway_configuration_api.py -v
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_account_api.py -v
& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_configuration.py
```

The focused PostgreSQL fixture applies actual migrations, provisions generated restricted-role credentials in an owned digest-pinned pullnever cluster, and unwinds only its0015 dependencies before existing account cleanup. No remote credentials or active users are adopted. Full baseline regression and live gateway/UI proof are not claimed.

## Next unit

Unit2 now reuses existing catalogue snapshots, pointer, ledger and outbox for genuine owned accounts without fabricating an Entra Principal. Discovered IDs remain unknown/unverified capabilities. Central inference, durable upgrade, administrator/client bridge and prebuilt E2E remain pending in `odd/tasks/forge-central-gateway.md`.


## Unit2: truthful discovery and stable aliases

The new optional `GatewayCatalog` composition is unavailable by default. An active genuine Forge administrator can refresh private model IDs from the fixed `https://ia.prometheonlab.com/v1/models` endpoint, then publish a bounded alias-to-discovered-ID mapping and one selected default. Employees read stable aliases, catalogue revision, default and explicit unknown capability state. They cannot read gateway credentials, private upstream IDs, binding/route/evidence IDs or private selection tables. Bootstrap response shape is unchanged.

| Operation | Boundary |
| --- | --- |
| POST `/forge/v1/orgs/{organization_id}/gateway/catalogue/refresh` | Fresh live administrator; decrypted bound key stays server-side. Returns private discovered IDs to the administrator only, not capability claims. |
| POST `/forge/v1/orgs/{organization_id}/models/publish` | Strict operationID, expected catalogue/gateway revisions, aliases mapping and default. Selections must exist in trusted server discovery. |
| GET `/forge/v1/orgs/{organization_id}/models` | Fresh genuine active same-org member. Stable alias IDs and explicit unknown/null capability values only. |

Refresh closes its initial short authorization transaction before outbound HTTP. The HTTPX adapter disables environment proxy discovery and redirects; finite connect2s/read5s/write2s/pool1s bounds and an outer10s cancellable total request timeout apply. Response acceptance is bounded to1MiB,500 unique printable-ASCII IDs of at most255 characters; compressed responses are rejected before decoding. The store revalidates current session, administrator, organization and exact gateway revision/binding after the request. No provider error or key is relayed to the caller.

Publication locks genuine current account/session/member/administrator, gateway and active pointer. Snapshot, private mapping/default, outbox event, pointer and operation ledger commit atomically. Mapping, default and gateway revision participate in replay identity; replay never bypasses fresh authority. Current trusted discovery is required for selected IDs, including replay. Gateway key rotation changes the binding and makes old publication unavailable until fresh discovery/publication. Catalogue CAS remains organization-wide across bindings.

The immutable codec preserves canonical verified v1 bytes. Explicit v2 unknown/unverified routes use null modalities, context/output limits, tools and streaming: a model ID alone cannot establish support. An unverified route with known claimed capabilities is still rejected. Alias names cannot establish capabilities.

Apply actual reviewed0001–0005 and0010–0016 only in an explicitly authorized new/upgraded deployment. `GatewayCatalogReadiness` attests this separate PostgreSQL17 profile with reviewed static SHA256 `771721e4c57685611bbd3a456ee318fe0433c5f37c4130fe7c559ebfb67ced8c`; neither legacy nor CG1 readiness is relaxed. `PostgresGatewayCatalogStore` reuses the function-only gateway pool; no account-store role whitelist expansion exists. Runtime dependency `httpx==0.28.1` is now declared; its installed version did not change and no install ran.

Focused verification commands:

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_gateway_catalog*.py' -v
.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_model_catalog*.py' -v
.venv/Scripts/python.exe -B -m unittest discover -s tests -p 'test_gateway_configuration*.py' -v
.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_account_api.py -v
& scripts/test-postgres.ps1 -TestPattern test_postgres_gateway_catalog.py
```

Observed final results after deadline correction:27+25+13+10 pure tests passed;8 real PostgreSQL tests passed46.342s with exact owned-container cleanup. PostgreSQL proof includes genuine HTTP discovery/publication/member read/reopen, same-org positive access, foreign/suspended/revoked denial, race/CAS/replay, rotation during fetch/publication, all-object rollback, cipher failure and ACL/RLS/function/authority drift rejection. HTTPX discovery is a labelled fixture transport, not a live provider validation. Independent Unit2 review, whole baseline regression, active-demo migration, real gateway call, inference and UI remain pending.


### Deadline correction

Independent trickle verification found that the initial synchronous64KiB body buffering could postpone total-time observations. The corrected adapter awaits AsyncHTTPX under `asyncio.timeout`, checking every unbuffered body fragment. Actual account refresh awaits this on the existing server event loop; short PostgreSQL operations use the framework's bounded worker limiter without abandoning them on cancellation. The direct synchronous convenience facade owns its loop only outside an existing loop; async consumers await `discover_async` instead. Tests prove cancellation during labelled send/header stages and fragmented body, closed transport/stream, no pending request task, and redacted API503 without discovery persistence. No background request executor or schema/profile change was introduced.

## CG3a central member text stream (implemented, not deployed)

POST `/forge/v1/orgs/{organization_id}/chat/completions` reuses genuine Forge
bearer validation. Its optional inference service is absent by default (503).
No employee gateway key or administrator claim is accepted. The function-only
server pool resolves a current active account/session/member, current published
stable alias, exact private route, and current gateway revision/binding in one
short transaction. A bound ciphertext is decrypted only after that resolution.
Wrong organization, unknown alias, missing/stale publication, suspended member,
logout/reset/disabled account, wrong key or ciphertext substitution deny before
an outbound request.

### Client bridge contract

This is a normalized OpenAI-style **text streaming subset**, not complete OpenAI
compatibility or a claim that discovered models support streaming. Unknown model
capabilities remain unknown; an actual unsupported upstream request fails closed.

```json
{
  "model": "assistant",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true,
  "max_output_tokens": 512
}
```

The model is a published stable alias, never an upstream ID. Strict text roles
are system/user/assistant, with a final user message. At most16 messages,
4096 characters per content and16384 total UTF8 content bytes are accepted.
The HTTP body is bounded to32768 bytes. Optional max_output_tokens is a local
policy budget1–2048 (default512), not a discovered model capability. Images,
tools, attachments, arbitrary generation parameters and non-stream requests
are rejected. No token counts, cost estimates or invented capabilities appear.

Success uses `data: {JSON}\n\n` SSE records with a server-generated id,
object `chat.completion.chunk`, public model alias, and one choice
`{"index":0,"delta":{"content":"text"},"finish_reason":null}`.
The final choice has empty delta and finish_reason stop/length, followed by
`data: [DONE]\n\n`. Provider IDs, headers, usage, raw documents and diagnostics
are not forwarded. Known private key/route echoes are guarded across fragments.
Authorization/input/optional-service failures before streaming use existing
401/404/422/503 envelopes. A failure **after HTTP200** is a redacted SSE
error with code INFERENCE_UNAVAILABLE, fixed message, server request_id and
retryable false, followed by DONE; consumers must handle this as failure,
not a successful assistant completion.

### Transport and revocation bounds

The only outbound route is fixed HTTPS
`https://ia.prometheonlab.com/v1/chat/completions`; environment discovery,
redirects and retries are disabled. TLS verification remains enabled.
Connect3s, pool1s, read/write5s bounds plus a cancellable60s whole request
deadline apply. A producer owns the request across all fragments and bounded
queue backpressure. Additional local limits are5s fragment-idle,1MiB raw body,
16KiB event,1024 events and32768 output characters. Compressed, malformed,
tool/function/audio/refusal or unsupported finish records fail closed.
An explicit upstream finish and DONE are required.

Fresh session/member/publication/binding checks run every0.5s plus pool,
database and scheduler latency. Output waits while a check is pending; storage
failure closes the provider. Each check ends its transaction before waiting
for network IO. A bounded synchronous database operation is settled during
cancellation rather than abandoned. Disconnect, caller cancellation, rotation,
revocation and limits close owned transport/tasks. Revocation is not instant:
previously delivered text and already incurred provider work/cost cannot be
undone. This is not a production distributed concurrency/quota guarantee.

### Separate schema admission and proof

Additive0017 exposes only the restricted member-route function, without
employee direct-table or cipher access. `GatewayInferenceReadiness` attests
actual0001–0005+0010–0017 on PostgreSQL17 using authored static SHA256
`0544327eb3719aff43676332c84489fa759a71fe3fa10b38fbf36a99c1c52614`.
Prior readiness profiles/pins remain unchanged and reject this additive
profile. No running durable demo or migration manifest was upgraded.

Focused final proof:27 pure inference/domain/adapter/API tests passed4.495s,
10 existing accountAPI tests passed0.611s,6 real owned PostgreSQL tests
passed16.501s with exact-ID container cleanup. HTTPX inference is an explicitly
labelled fixture transport, not a live gateway/key/model validation.
Independent CG3a checking, CG3b deployment composition/upgrade, CG4 bridge,
CG5 browser/prebuilt E2E and full baseline regression remain pending.

## CG3b explicit retained local composition (implementation only)

The retained wrapper now offers -UpgradeGateway -DemoDirectory as a separate
stopped-owner-only operation. It does not launch the API or call install_and_seed.
Completed explicit upgrade selects separate central gateway composition on
Resume; ordinary Resume never migrates or repairs unfinished journals. Current
running a23d user demo is not upgraded. Legacy defaults, constants and readiness
pins remain unchanged.

Actual0005 and0010–0012+0015–0017 scripts commit independently. Eight authored
static PG17 schema checkpoint hashes plus authority NOLOGIN checks verify each
step. A private phase journal permits at most one committed migration ahead of
the journal, never runtime trust-on-first-use. Old files stay unchanged before
first DB commit. Context and ownership are individually atomically promoted;
a crash between them requires explicit recover-forward UpgradeGateway, never
reset/reseed/downgrade. No fictitious enclosing migration transaction exists.

A separate protected gateway-secrets.json persists one generated Fernet key
and only the new restricted gateway service-role credential, bound to the
instance. Existing role passwords/delivery key stay unchanged. Missing key
after progress/cipher state refuses regeneration. Upgrade never supplies a
real provider key: initial configuration stays NOT_CONFIGURED and later API
save is SAVED_UNVERIFIED. Trusted CORS remains127.0.0.1:3319, allowing only
GET/POST/PUT/OPTIONS and Authorization/Content-Type. No wildcard origin.

Only after separate authorization and explicit stop of the selected owned demo:

```powershell
& scripts/dev-accounts-persistent.ps1 -UpgradeGateway -DemoDirectory '<exact owned private directory>'
& scripts/dev-accounts-persistent.ps1 -Resume -DemoDirectory '<same exact owned private directory>'
```

Private ACL, exact directory/container/image/named-volume ownership and exclusive
instance lock are verified. Running or locked instances refuse without automatic
stop. Upgrade starts only its previously stopped owned DB and stops it again;
data/volume remain. This is local development composition, not production upgrade
tooling or authorization for the current user demo.

Observed final proof:5 retained tests passed48.124s, actual upgrade child and
same named-volume DB stop/start preserve real admin/recipient identities,
passwords/old sessions and gateway-key decrypt after restart. Owned PG1
comprehensive test passed16.288s with injected seven commit/journal/promotion
failures, preserved row/credential/mailbox hashes and missing-key refusal; exact
harness container cleanup. Existing persistent2pass1skip0.001s; fixed3320 old
listener lifecycle was not rerun because user service must remain untouched.
New tests use actual FastAPI ASGI composition without replacing3320.
Python/PowerShell syntax, whitespace and diff passed. Independent CG3b checking,
actual user upgrade, live provider/browser proof and later units remain pending.

## Administrator publication status (additive0018)

`GET /forge/v1/orgs/{organization_id}/gateway/catalogue/status` is administrator-only and returns `catalogue_revision`, nullable `default_model`, and `publication_state`: UNPUBLISHED only when the actual active pointer does not exist; CURRENT when its binding/revision match the current gateway; STALE_GATEWAY after rotation. The prior revision/default remain authoritative for deliberate CAS republishing, independent of employee models404. No cipher, upstream ID, route, binding or capability evidence is returned.

This requires the separate reviewed PostgreSQL17 `GatewayCatalogAdminReadiness` profile through0018. Prior exact profiles remain unchanged. Explicit stopped-owner gateway upgrade advances to0018; normal resume never migrates. Known complete0017/v1 demos continue their exact0017 runtime until explicit upgrade. New v2 journals retain the validated old v1 journal as `previous`; interrupted commits recover forward, preserving existing identities, hashes, credentials, mailbox and separate gateway key. No active user demo has been upgraded by this implementation.

Client administration integration must consume this protected status rather than infer zero from an unavailable employee projection. First setup, rotation and client bridge/E2E remain unverified until that next client hook and authorized runtime proof.
