# Production Runtime Specification

## Purpose
A non-loopback, environment-configured serving profile for the control plane, independent of the dev composition.

## Requirements

### Requirement: Environment and secret-file configuration
The system MUST read all settings from environment variables, and every secret MUST be readable from a `<NAME>_FILE` path (direct value only when no file is given). The loader MUST ignore/strip `PG*` variables, MUST reject unknown `FORGE_*` keys, and MUST fail with a finite non-secret code before binding any port.

#### Scenario: Secrets from files
- GIVEN `FORGE_ROLE_PASSWORDS_DIR` files and `FORGE_GATEWAY_KEY_FILE` exist
- WHEN the config loads
- THEN secrets are populated and absent from `repr` and logs

#### Scenario: Invalid config
- GIVEN `FORGE_PUBLIC_ORIGIN=http://example.com`
- WHEN the config loads
- THEN it fails with `CONFIG_INVALID:FORGE_PUBLIC_ORIGIN` and nothing is bound

### Requirement: Trusted public host
The system MUST derive the accepted Host set and browser Origin allow-list from `FORGE_PUBLIC_ORIGIN` only, and MUST refuse any other Host with `FORBIDDEN_HOST`.

#### Scenario: Foreign host
- GIVEN origin `https://forge.example.test`
- WHEN a request carries `Host: evil.test`
- THEN the response is 403 `FORBIDDEN_HOST`

### Requirement: Health and readiness
The system MUST expose `/livez` (process up) and `/status` (schema-attested readiness, 503 when not ready), and a `healthcheck` subcommand MUST exit 0 only when `/status` is ready.

#### Scenario: Not ready
- GIVEN the schema fingerprint drifted
- WHEN `/status` is requested
- THEN 503 `not_ready` and `healthcheck` exits non-zero

### Requirement: Structured logs
Each request MUST emit one JSON log line with `ts, level, event, request_id, method, path, status, duration_ms`; it MUST NOT contain query strings, Authorization values, bodies or emails.

#### Scenario: Token redaction
- GIVEN a request with `Authorization: Bearer secret`
- WHEN it completes
- THEN the log line does not contain `secret`

### Requirement: Single worker
`serve_prod` MUST run one uvicorn process with one worker and MUST document the reason (connection budgets and in-process caches sized for one process).

#### Scenario: Worker option refused
- GIVEN `FORGE_WORKERS=2`
- WHEN the config loads
- THEN it fails `CONFIG_INVALID:FORGE_WORKERS`
