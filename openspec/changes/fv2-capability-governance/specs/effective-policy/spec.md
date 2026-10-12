# Effective Policy Specification

## Purpose
Signed per-member policy document for the client.

## Requirements

### Requirement: Signed document
`GET /forge/v1/capabilities/effective?sandbox_level=N` MUST require a valid member session and return `{schema,org,platform_epoch,org_epoch,issued_at,expires_at,reported_level,capabilities[],kid,sig}` signed Ed25519 over canonical JSON. The route MUST be hidden from OpenAPI.

#### Scenario: Verifies
- GIVEN a published key set
- WHEN the client verifies a response
- THEN the signature validates and tampering any field fails

#### Scenario: Unauthenticated
- GIVEN no session
- WHEN requested
- THEN 401 and no document

### Requirement: Rollback and expiry
Documents MUST carry monotonic epochs and a bounded expiry; epochs MUST bump on any change affecting the company.

#### Scenario: Epoch bump
- GIVEN a platform default change
- WHEN resolved again
- THEN `platform_epoch` is greater

### Requirement: Contract isolation
The MVP contract pin MUST remain byte-identical; the new schema MUST be pinned separately with test vectors.

#### Scenario: Pin unchanged
- GIVEN the MVP contract test
- WHEN run on this change
- THEN it passes unmodified
