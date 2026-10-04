# Prometheon Forge

An organization-aware agent platform with executable domain contracts and a
**default-deny HTTP bootstrap**. Corporate sign-in, real token validation adapters,
PostgreSQL/RLS, effective capabilities and the client are not integrated.

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
is claimed. UI verification is N/A because no executable screen exists.

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

Observed local proof: PostgreSQL 17.11, real RLS RED then 22/22 GREEN, existing 31
regressions unchanged. It is not a runtime DB reader or DB-backed HTTP integration;
F05b remains pending. Migration is one-shot for a pristine dedicated Forge DB with
reserved roles, not an upgrade runner for shared/production databases. Default API
still denies all real tokens. Independent verification and parent spot check passed;
local commit is authorized. F05a native review remains pending, not approved.
See `docs/changes/postgres-bootstrap.md` and `odd/tasks/forge-foundation.md` for
exact pins, recovery failures, command results and remaining scope.