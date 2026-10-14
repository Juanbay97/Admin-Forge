# Edge TLS Proxy Specification

## Purpose
Caddy terminates TLS, proxies the control plane and hosts installer downloads.

## Requirements

### Requirement: TLS modes
Caddy MUST obtain certificates via ACME when `FORGE_TLS=acme` (with `FORGE_ACME_EMAIL`) and via its internal CA when `FORGE_TLS=internal`; the mode MUST be selected only by env.

#### Scenario: Internal CA
- GIVEN `FORGE_TLS=internal`, `FORGE_DOMAIN=localhost`
- WHEN `https://localhost:8443/status` is requested with the extracted CA root
- THEN the TLS handshake verifies and the response is 200 ready

#### Scenario: Invalid mode
- GIVEN `FORGE_TLS=bogus`
- WHEN the stack starts
- THEN Caddy refuses to start with a clear error

### Requirement: Reverse proxy and headers
Caddy MUST proxy `/admin/*`, `/status`, `/livez`, `/forge/*` to `control-plane:3410`, preserving Host, and MUST add HSTS, `X-Content-Type-Options`, `Referrer-Policy`; the app's CSP MUST NOT be overridden.

#### Scenario: Admin via proxy
- GIVEN the stack is up
- WHEN `GET /admin/` is requested
- THEN 200 `text/html` with the app CSP

### Requirement: Installer hosting
`/downloads/*` MUST serve files from a read-only volume without directory listing; `latest.json` MUST be served `no-cache`.

#### Scenario: Download
- GIVEN `downloads/latest.json` exists
- WHEN requested
- THEN 200 with `Cache-Control: no-cache`; `/downloads/` lists nothing (404)

### Requirement: Unknown host
Requests for an unconfigured Host MUST NOT reach the control plane.

#### Scenario: Wrong SNI/Host
- GIVEN domain `localhost`
- WHEN `Host: evil.test`
- THEN no upstream response is proxied
