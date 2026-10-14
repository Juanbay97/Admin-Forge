# Gateway Key Pool Specification

## Purpose

Platform-owned sealed gateway keys, assigned to companies with priority and used for routing with failover.

## Requirements

### Requirement: Sealed write-only keys
Key text MUST be accepted only on create/rotate, sealed with AAD binding key id, revision and origin, and MUST NOT be returned by any API, log or audit row. Reads expose label, origin, status, last4 hint, revision.

#### Scenario: Create and read
- GIVEN an MFA-verified owner
- WHEN it creates a key then lists keys
- THEN the list shows label/last4 and never key text

#### Scenario: Tampered ciphertext
- GIVEN a sealed row moved to another key id
- WHEN it is opened
- THEN `GatewayUnavailable` and no network call

### Requirement: Origin allow-list
A key origin MUST be in the deployment allow-list; the database MUST NOT pin a single origin.

#### Scenario: Disallowed origin
- WHEN a key is created for `https://evil.example`
- THEN it is rejected and nothing is stored

### Requirement: Assignment with priority
A company MAY have many active keys with unique priority. Platform only may assign, unassign, reorder, disable.

#### Scenario: Company admin
- WHEN a company admin calls an assignment or key route
- THEN denied

### Requirement: Priority routing and failover
Inference MUST use the lowest-priority active key and MUST fail over to the next on 401/429/5xx/connect error only before any byte was streamed to the member. Each key is tried at most once per request.

#### Scenario: Primary rate-limited
- GIVEN keys K1 (429) and K2 (ok)
- WHEN a member streams
- THEN K2 serves and the member sees one normal stream

#### Scenario: Failure mid-stream
- WHEN K1 fails after the first chunk
- THEN no failover; the stream ends with the finite error

#### Scenario: All keys down
- THEN `INFERENCE_UNAVAILABLE` finite error

### Requirement: Rotation
Rotating a key MUST bump revision and take effect for new requests; in-flight streams finish on the old value.

#### Scenario: Revoked key
- WHEN a key is disabled
- THEN it is never selected
