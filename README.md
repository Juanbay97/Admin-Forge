# Prometheon Forge

An organization-aware agent platform with executable domain contracts and a
**default-deny HTTP bootstrap**. Corporate sign-in, real token validation adapters,
PostgreSQL/RLS, effective capabilities and the client are not integrated.

## Local setup and checks

Requires Python 3.12 or newer. Use a repository-local virtual environment; do not
modify a shared runtime. Runtime pins are FastAPI 0.142.2 and uvicorn 0.54.0;
the optional test extra pins httpx 0.28.1. Tests use standard-library unittest.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-input --keyring-provider disabled ".[test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
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
