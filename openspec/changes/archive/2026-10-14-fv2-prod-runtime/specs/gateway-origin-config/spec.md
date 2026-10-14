# Gateway Origin Configuration Specification

## Purpose
The gateway origin allow-list is deployment configuration, not a hard-coded spelling.

## Requirements

### Requirement: Env-driven allow-list
Production composition MUST build `OriginPolicy` from `FORGE_GATEWAY_ORIGINS` (comma-separated canonical https origins, `dev=False`). When unset, it MUST default to `DEFAULT_ENDPOINT` only.

#### Scenario: Custom origin
- GIVEN `FORGE_GATEWAY_ORIGINS=https://ia.example.test`
- WHEN an admin saves that endpoint
- THEN it is accepted and any other origin is `OriginDenied`

#### Scenario: Plain http refused
- GIVEN `FORGE_GATEWAY_ORIGINS=http://127.0.0.1:3413`
- WHEN the config loads
- THEN it fails `CONFIG_INVALID:FORGE_GATEWAY_ORIGINS`

### Requirement: Database pin relaxed
After 0027 the database MUST accept any canonical https origin (or dev loopback) in `organization_gateways.endpoint` and `gateway_save`, keeping defense in depth; the application allow-list remains the authority.

#### Scenario: Non-default origin persisted
- GIVEN migration 0027 applied
- WHEN `gateway_save` receives `https://ia.example.test`
- THEN the row is stored

#### Scenario: Non-origin rejected
- GIVEN 0027 applied
- WHEN the endpoint has a path or userinfo
- THEN `GATEWAY_INVALID`

### Requirement: Upgrade safety
0027 MUST leave existing rows and ciphertexts valid and MUST be fingerprint-pinned as F27 for fresh apply and upgrade.

#### Scenario: Upgrade equals fresh
- GIVEN a database at F26
- WHEN 0027 applies
- THEN its fingerprint equals a fresh 0001–0027 apply
