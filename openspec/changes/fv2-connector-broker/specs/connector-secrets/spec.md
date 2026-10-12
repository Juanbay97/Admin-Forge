# Connector Secrets Specification

## Purpose
Server-side sealed storage of connector credentials.

## Requirements

### Requirement: Sealing and binding
Secrets MUST be sealed with a dedicated deployment key (separate from gateway and policy keys); ciphertext MUST bind org, scope (org|user), subject, capability id, revision. Any binding drift MUST fail to open.

#### Scenario: Substitution
- GIVEN user A's sealed token moved to user B's row
- WHEN opened
- THEN it fails

#### Scenario: Missing key
- GIVEN no cipher key at composition
- WHEN the broker is built
- THEN construction fails closed

### Requirement: Write-only entry
Company admins MUST set org-level credentials write-only; reads MUST return status, last-4 hint and revision only. Plaintext MUST NOT appear in any response, error or log.

#### Scenario: Read back
- GIVEN a saved API key
- WHEN admin reads status
- THEN no secret material is returned

### Requirement: Revision conflict
Writes MUST use expected revision; stale writes MUST fail `CONFLICT`.

#### Scenario: Stale
- GIVEN revision 3
- WHEN write expects 2
- THEN `CONFLICT`, row unchanged

### Requirement: Tenant isolation
Credentials MUST be reachable only via the broker role under org RLS.

#### Scenario: Cross-org
- GIVEN admin of A
- WHEN reading B's connector
- THEN denied
