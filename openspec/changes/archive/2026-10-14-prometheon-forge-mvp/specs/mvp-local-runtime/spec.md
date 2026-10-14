# Delta for MVP Local Runtime

## ADDED Requirements

### Requirement: Explicit-config serve composition

`forge.mvp_local` MUST compose the app only from an explicit `--config <file>` (database, ports, CORS origins, gateway allow-list, profile, secrets paths). It MUST NOT read environment variables for discovery, MUST NOT use fake identity, and MUST fail closed on missing/invalid fields.

#### Scenario: Valid config
- GIVEN a complete config file
- WHEN `forge.mvp_local serve` starts
- THEN API and `/admin` are served on the configured ports and `/status` reports ready

#### Scenario: Missing or malformed config
- GIVEN a missing required field or unknown key
- WHEN starting
- THEN it exits non-zero with a redacted message (no secret values) and binds no port

#### Scenario: Env ignored
- GIVEN an environment variable naming a different database
- WHEN starting with a config file
- THEN the config file value is used

### Requirement: Port safety and CORS

The runtime MUST use ports distinct from 3319/3320/3331/3332, MUST NOT stop or adopt existing processes, and MUST allow only configured origins.

#### Scenario: Port occupied
- GIVEN the configured port is in use
- WHEN starting
- THEN it fails without touching the other process

#### Scenario: Foreign origin
- GIVEN a browser request from an origin not in CORS config
- WHEN calling the API
- THEN no permissive CORS headers are returned

### Requirement: Trusted provisioning CLI

A platform-operator CLI MUST create organizations, first admin and department, and seed a two-organization fixture. Provisioning MUST NOT be reachable over HTTP, MUST be idempotent, and MUST NOT print passwords, keys or hashes to logs.

#### Scenario: Provision org
- GIVEN an empty migrated database
- WHEN provisioning org "A" with an admin and department
- THEN login as that admin succeeds and `/accounts/me` lists A

#### Scenario: Rerun
- GIVEN org A already provisioned
- WHEN rerunning the same command
- THEN no duplicate rows and no password reset occurs

#### Scenario: Two-org seed
- GIVEN the seed command
- WHEN completed
- THEN orgs A and B each have an admin, a department and a member, with distinct credentials and gateway keys

### Requirement: Admin static mount and invite mailbox

`/admin` MUST serve the built SPA same-origin with a strict CSP; invitations MUST be written to a local `.eml` mailbox with a configured link origin.

#### Scenario: Admin served
- GIVEN a built SPA
- WHEN requesting `/admin/`
- THEN HTML is served with CSP forbidding inline script and third-party origins

#### Scenario: Invite mail
- GIVEN an admin invites a member
- WHEN the invite is created
- THEN an `.eml` appears in the mailbox containing a link using the configured origin and no other secrets
