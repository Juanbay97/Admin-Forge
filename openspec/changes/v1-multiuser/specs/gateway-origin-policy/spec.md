# Delta for Gateway Origin Policy

## MODIFIED Requirements

### Requirement: Key custody bound to origin

The encrypted key MUST be bound to organization, revision and origin; changing the origin MUST require a new write-only key. Adapters MUST call only the stored, policy-validated origin of the acting organization. Migration 0019 is forward-only: restoring the fixed-endpoint CHECK is a documented manual precondition (no non-default origin rows) and is not enforced by a mechanism.
(Previously: "downgrade is refused if any non-default origin row exists", with no mechanism or test.)

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
- THEN they remain valid and decryptable
