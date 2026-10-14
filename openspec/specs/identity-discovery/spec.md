# Identity Discovery Specification

## Purpose

Source of truth for identity-discovery, established by change `prometheon-forge-mvp`.

## Requirements

### Requirement: `GET /forge/v1/accounts/me`

The system MUST return, for the authenticated owned-account session only, the caller's identity and the active memberships (organization id/name, role, membership status). It MUST NOT return other users' data, other organizations, secrets, session tokens or gateway details.

#### Scenario: Admin of one org
- GIVEN a valid session for a user who is `organization_admin` of org A
- WHEN calling `/accounts/me`
- THEN the response lists exactly org A with role `organization_admin`

#### Scenario: Multi-org user
- GIVEN a user with active memberships in orgs A (admin) and B (member)
- WHEN calling `/accounts/me`
- THEN both are listed with their own roles, and nothing from any third org

#### Scenario: Member role
- GIVEN a plain member session
- WHEN calling `/accounts/me`
- THEN role is the member role and the admin UI/API remains unavailable to that identity

### Requirement: Default deny for unknown, expired or suspended identity

The endpoint MUST answer 401 for missing, malformed, expired or revoked sessions, and MUST omit or deny memberships whose status is not active. Errors MUST be redacted and indistinguishable between unknown and revoked.

#### Scenario: No or invalid session
- GIVEN no cookie/bearer, or a tampered one
- WHEN calling `/accounts/me`
- THEN 401 with a generic body

#### Scenario: Suspended membership
- GIVEN a user suspended in org A and active in org B
- WHEN calling `/accounts/me`
- THEN only org B is listed; if no active membership remains, the response denies access

#### Scenario: After logout
- GIVEN a session that was logged out
- WHEN calling `/accounts/me` with it
- THEN 401

### Requirement: Server-discovered context

Clients MUST obtain organization context from this endpoint instead of fixtures or user input.

#### Scenario: Org id not supplied by caller
- GIVEN a client that knows only its credentials
- WHEN it needs the organization id for bootstrap or catalog calls
- THEN it uses an id returned by `/accounts/me`; a different id yields 404 on org-scoped routes
