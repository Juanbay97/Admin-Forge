# Organization Departments Specification

## Purpose
Provide organization-scoped areas and assignments.

## Requirements

### Requirement: D1 Administrative lifecycle
Only active organization administrators MUST be allowed to create, rename or archive departments; assignments MUST reference active departments in the same organization.

#### Scenario: Lifecycle
- GIVEN an active administrator and an empty department
- WHEN creating, renaming, assigning then unassigning a member, and archiving
- THEN each accepted change advances its resource revision and records one event.

#### Scenario: Invalid assignment
- GIVEN an archived or foreign department
- WHEN an administrator assigns a member
- THEN assignment is denied without mutation or event.

### Requirement: D2 Scoped reads
Department managers MUST have read-only access within their current authorized department set, never other departments or organizations. Association alone MUST NOT grant administrative privileges. Projections MUST hide a shared member's associations outside that set.

#### Scenario: Manager boundary
- GIVEN a department manager
- WHEN reading own-area members or requesting another area or any mutation
- THEN only the own-area read succeeds.

#### Scenario: Shared member projection
- GIVEN a manager authorized in A and a member linked to A and B
- WHEN the manager reads the member through A
- THEN B is not exposed; an unassigned manager or ordinary member gains no management access.

### Requirement: D3 Multiple department associations
A member MAY belong to zero or multiple departments. Associations MUST be unique organization/member/department triples with same-organization references. Replacement MUST validate the complete set and atomically update the membership revision and one event; unchanged sets MUST NOT create events.

#### Scenario: Cross-functional assignment
- GIVEN an administrator, a current member revision and active departments A and B in the same organization
- WHEN assigning both and later unlinking A
- THEN both links first exist without role changes, and the later change retains B.

#### Scenario: Invalid set
- GIVEN a requested set containing duplicates, a foreign department or an archived department
- WHEN replacing associations
- THEN the whole request fails with no partial link, revision change or event.

### Requirement: D4 Occupied archive and concurrent safety
Archive MUST fail while any member is linked, including suspended members. Members MUST first be reassigned or unlinked; automatic detachment is forbidden. Archive, assignment and invitation activation MUST serialize and recheck current state in the same transaction.

#### Scenario: Occupied archive
- GIVEN a department linked to an active or suspended member
- WHEN an administrator archives it
- THEN conflict is returned without changes; archive succeeds only after all links are removed.

#### Scenario: Archive races with assignment or activation
- GIVEN an empty active department and two synchronized database sessions
- WHEN one archives while the other assigns a member or activates an invitation targeting it
- THEN either linking commits and archive fails, or archive commits and linking fails; no archived department has a newly materialized link.
