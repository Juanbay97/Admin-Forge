# Delta for Member Administration

## ADDED Requirements

### Requirement: Departments read and create

Org admins MUST be able to list and create departments of their own organization. Non-admins and foreign admins MUST NOT. Names MUST be validated (length, uniqueness within org) and writes MUST be idempotent-safe.

#### Scenario: Admin lists and creates
- GIVEN an admin of org A
- WHEN creating department "Legal" and then listing
- THEN the list contains "Legal" with its id and only org A departments

#### Scenario: Duplicate name
- GIVEN department "Legal" exists in org A
- WHEN the admin creates "Legal" again
- THEN a redacted conflict/validation error is returned and no duplicate exists

#### Scenario: Cross-org
- GIVEN an admin of org A
- WHEN requesting org B's departments (list or create)
- THEN 404 and org B data is unchanged

### Requirement: Member list

Org admins MUST be able to list members of their organization (email, role, department, status). The list MUST NOT expose password hashes, tokens, gateway data or other orgs' members.

#### Scenario: Admin list
- GIVEN org A has an admin, an active member and a suspended member
- WHEN the admin lists members
- THEN all three appear with correct statuses and no secret fields

#### Scenario: Non-admin denied
- GIVEN a plain member of org A
- WHEN requesting the member list
- THEN 404/403 with a redacted body

#### Scenario: Cross-org
- GIVEN admin A
- WHEN listing org B's members
- THEN 404

### Requirement: Suspend and reactivate with last-admin guard

Admins MUST be able to suspend and reactivate members of their own org. Suspension MUST revoke the member's sessions and deny in-flight streaming. The system MUST refuse suspending the last active admin. Role edits and department reassignment are NOT supported.

#### Scenario: Suspend member
- GIVEN an active member with an open session
- WHEN the admin suspends them
- THEN status is suspended, sessions are revoked, and the member's next `/accounts/me`, catalog or chat call is denied

#### Scenario: Reactivate
- GIVEN a suspended member
- WHEN the admin reactivates them
- THEN they can log in again and see only published aliases

#### Scenario: Last admin
- GIVEN org A has a single active admin
- WHEN that admin (or any actor) tries to suspend them
- THEN the request is refused with a redacted error and the status is unchanged

#### Scenario: Unknown or foreign member id
- GIVEN a member id from org B or non-existent
- WHEN admin A suspends it
- THEN 404, identical for both cases

#### Scenario: Concurrent suspend
- GIVEN two admins simultaneously suspend each other as the only two admins
- WHEN both commit
- THEN at least one active admin remains
