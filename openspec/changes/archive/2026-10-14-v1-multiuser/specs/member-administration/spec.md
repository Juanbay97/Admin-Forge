# Delta for Member Administration

## MODIFIED Requirements

### Requirement: Suspend and reactivate with last-admin guard

Admins MUST be able to suspend and reactivate members of their own org. Suspension MUST deny in-flight streaming and MUST revoke the account's sessions only when the account has no other active membership; otherwise sessions MUST stay valid and every route of the suspended org MUST deny. The system MUST refuse suspending the last active admin. Role edits and department reassignment are NOT supported.
(Previously: suspension always revoked all of the account's sessions, logging multi-org members out of other orgs.)

#### Scenario: Suspend member
- GIVEN an active member with an open session and no other membership
- WHEN the admin suspends them
- THEN status is suspended, sessions are revoked, and the member's next `/accounts/me`, catalog or chat call is denied

#### Scenario: Multi-org member
- GIVEN an account active in orgs A and B with one session
- WHEN org A's admin suspends it
- THEN the session stays valid for org B and org A's bootstrap, catalog and chat are denied

#### Scenario: Reactivate
- GIVEN a suspended member
- WHEN the admin reactivates them
- THEN they can log in again and see only published aliases

#### Scenario: Last admin
- GIVEN org A has a single active admin
- WHEN that admin (or any actor) tries to suspend them
- THEN the request is refused with a redacted error and the status is unchanged
