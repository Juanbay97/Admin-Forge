# Platform Admin Specification

## Purpose

A platform owner identity with authority over companies, isolated from tenant data by DB functions, not by privileged roles.

## Requirements

### Requirement: Platform owner identity
The owner MUST be an owned account with no membership and a `platform_roles` row. The platform pool MUST NOT have BYPASSRLS nor direct table grants on org-scoped tables.

#### Scenario: Direct table access denied
- GIVEN a connection as `forge_platform_service`
- WHEN it selects from `forge.memberships`
- THEN permission is denied

#### Scenario: Org member is not platform
- GIVEN an `organization_admin` account without `platform_roles`
- WHEN it calls any `platform_*` function
- THEN `PLATFORM_DENIED`

### Requirement: Operator bootstrap
`bootstrap-owner` MUST be CLI-only, MUST write a one-time set-password link to a private file, MUST NOT print or store a password, and MUST be a no-op on rerun.

#### Scenario: Link consumed once
- GIVEN a bootstrapped owner link
- WHEN the link is used twice
- THEN the second use is rejected

### Requirement: Mandatory TOTP
Platform functions MUST require a verified MFA state for the current session. Enrollment is mandatory for `platform_owner`. A TOTP step MUST NOT be accepted twice; recovery codes are single-use and stored hashed.

#### Scenario: Password only
- GIVEN a session without MFA verification
- WHEN any platform function is called
- THEN `MFA_REQUIRED`

#### Scenario: Replay
- GIVEN a code accepted at step N
- WHEN the same code is resubmitted
- THEN it is rejected

### Requirement: Hidden platform routes
Platform routes MUST use `include_in_schema=False`; `GET /forge/v1/platform/me` MUST NOT widen `MeResponse`.

#### Scenario: Contract unchanged
- WHEN the contract pin test runs
- THEN the pin is identical to before
