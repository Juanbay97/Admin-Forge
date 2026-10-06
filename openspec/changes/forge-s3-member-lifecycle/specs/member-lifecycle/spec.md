# Member Lifecycle Specification

## Purpose
Administer pre-provisioned members without email-based enrollment.

## Requirements

### Requirement: M1 Validated activation
Invitations MUST identify Entra tenant/object IDs, MUST NOT match email, and MUST confer no access until validated first-login binding.

#### Scenario: First login
- GIVEN a pre-provisioned invitation
- WHEN its matching validated principal first logs in
- THEN exactly one membership activates; repeated/concurrent logins do not duplicate activation.

#### Scenario: Untrusted identity
- GIVEN an unknown, mismatched or invalid principal, including matching email
- WHEN login is attempted
- THEN no invitation binds and no access is granted.

#### Scenario: Multi-area activation
- GIVEN an invitation reserving same-org departments A and B without access
- WHEN a validated matching principal activates it
- THEN all current active targets bind atomically with one activation event; an archived/foreign target or identity mismatch binds nothing, including under concurrent archive.

### Requirement: M2 Authorized revisioned changes
Only active administrators MUST invite, update roles/department associations, suspend or reactivate; changes MUST use current authority, and updates MUST require matching If-Match revisions. Department associations MUST be many-to-many and MUST NOT imply role grants.

#### Scenario: Successful changes
- GIVEN an authorized administrator and current revision
- WHEN updating, suspending or reactivating a member
- THEN the accepted transition advances revision once and records one event.

#### Scenario: Rejected writes
- GIVEN missing/stale If-Match, foreign organization, suspended/unknown actor or revoked authority
- WHEN mutation is attempted
- THEN no mutation/event occurs and errors reveal no secrets or foreign records.

### Requirement: M3 Last administrator
The last active, bound administrator MUST NOT be suspended or demoted, including concurrent requests. Recovery is excluded.

#### Scenario: Competing removals
- GIVEN one or two active administrators
- WHEN requests attempt to remove all active administrators
- THEN at least one remains and rejected requests produce no event.

#### Scenario: Direct writer and stale authority
- GIVEN two bound active administrators and independently connected permitted writers
- WHEN concurrent SQL/service paths demote or suspend them, including authority revoked while waiting
- THEN the database guard serializes fresh post-lock authority/count checks; at least one remains and stale authority cannot commit.

#### Scenario: Recovery excluded
- GIVEN the permanent initial-administrator designation and an administrator who loses external identity access
- WHEN attempting to reuse central designation as recovery
- THEN no recovery behavior or last-admin bypass is introduced; recovery remains explicitly outside MVP.
