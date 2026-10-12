# Capability Policy Specification

## Purpose
Layered enable/disable with super-admin authority.

## Requirements

### Requirement: Resolution precedence
Resolution MUST apply, in order: (1) force-off lock at platform or company-override level → `forced_off`; (2) org-admin setting; (3) company override default; (4) platform default; (5) catalog default. Unknown ids MUST resolve `off`.

#### Scenario: New company inherits
- GIVEN a company with no policy rows
- WHEN effective policy is resolved
- THEN base skills/connectors are `on`

#### Scenario: Force-off wins
- GIVEN the super admin force-offs connector X for company C
- WHEN C's admin enables X
- THEN the write is rejected `LOCKED` and X stays `forced_off`

### Requirement: Org admin limits
A company admin MUST be able to enable/disable only unlocked capabilities of their own company; members MUST NOT write policy.

#### Scenario: Cross-org denied
- GIVEN admin of company A
- WHEN targeting company B's policy
- THEN denied, no existence leak

### Requirement: Sandbox attestation gate
For entries with `min_sandbox_level`>0 whose resolved state is on, the state MUST be `on` only if reported level ≥ minimum, else `blocked_attestation`. The gate MUST NOT be overridable by any admin.

#### Scenario: Below level
- GIVEN `code_execute` enabled and reported level 2, min 3
- WHEN resolved
- THEN state is `blocked_attestation`

#### Scenario: Missing report
- GIVEN no level reported
- WHEN resolved
- THEN level is treated as 0
