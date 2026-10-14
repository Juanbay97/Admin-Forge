# Delta for Gateway Origin Policy

## ADDED Requirements

### Requirement: Deployment allow-list is the only origin source

The system MUST accept a per-organization gateway base URL only if it exactly matches an entry in the deployment allow-list supplied by trusted composition. Free-form URLs MUST be rejected. Clients and members MUST NOT be able to submit or read origins other than via the admin gateway API.

#### Scenario: Allow-listed origin accepted
- GIVEN the allow-list contains `https://gw.example.com` and an authenticated org admin
- WHEN the admin PUTs gateway config with that base URL and a write-only `api_key`
- THEN the request succeeds and the response echoes the origin but never the key

#### Scenario: Non-listed origin denied
- GIVEN the allow-list does not contain `https://evil.example.net`
- WHEN the admin PUTs that base URL
- THEN the response is a redacted validation error and no row, ciphertext or outbound call is created

#### Scenario: Look-alike origins denied
- GIVEN the allow-list contains `https://gw.example.com`
- WHEN the admin submits `https://gw.example.com.evil.net`, `https://gw.example.com@evil.net`, a path/query variant, or a different port
- THEN each is rejected without any network request

### Requirement: Scheme restrictions

Origins MUST use `https`. `http` MUST be accepted only for loopback hosts and only when the explicit dev profile is composed. Credentials in URL, fragments, and redirects to other origins MUST be refused.

#### Scenario: Loopback http under dev profile
- GIVEN the dev profile and allow-list entry `http://127.0.0.1:<port>`
- WHEN the admin saves it
- THEN it is accepted

#### Scenario: Loopback http under production profile
- GIVEN no dev profile and the same entry in the allow-list
- WHEN composition starts
- THEN startup fails closed (or the entry is rejected) and no request is ever sent over `http`

#### Scenario: Cross-origin redirect
- GIVEN a configured origin whose gateway answers 302 to another host
- WHEN a catalog refresh or chat runs
- THEN the redirect is not followed and a redacted upstream error is returned

### Requirement: Key custody bound to origin

The encrypted key MUST be bound to organization, revision and origin; changing the origin MUST require a new write-only key. Adapters MUST call only the stored, policy-validated origin of the acting organization.

#### Scenario: Origin change without key
- GIVEN org A has an origin and stored key
- WHEN the admin changes only the origin
- THEN the request is rejected and the stored config is unchanged

#### Scenario: Tenant isolation of origin
- GIVEN org A and org B have different allow-listed origins
- WHEN org A's member chats
- THEN the outbound request targets only A's origin and uses only A's key

#### Scenario: Existing rows survive migration
- GIVEN rows configured with the legacy fixed endpoint before migration 0019
- WHEN 0019 is applied
- THEN they remain valid and decryptable; downgrade is refused if any non-default origin row exists
