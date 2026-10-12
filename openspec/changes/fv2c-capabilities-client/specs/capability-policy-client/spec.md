# Capability Policy Client Specification

## Purpose
Enable base OpenYak skills, connectors and tools per the control plane's signed effective policy, fail-closed.

## Requirements

### Requirement: Signed effective policy

The client MUST fetch the effective policy through the router relay, MUST verify an Ed25519 signature against a pinned key set (key id + rotation list shipped in the build), MUST check `organization_id` equals the profile's org, and MUST reject non-monotonic revisions. Unsigned, malformed or foreign policies MUST be ignored.

#### Scenario: Valid policy
- GIVEN a policy signed by a pinned key for the member's org with higher revision
- WHEN fetched
- THEN it is stored as last-known-good and applied

#### Scenario: Bad signature or org
- GIVEN a tampered or other-org policy
- WHEN fetched
- THEN it is rejected, the previous policy stays, and the UI shows `policy_invalid`

#### Scenario: Rollback attempt
- GIVEN a validly signed policy with a lower revision
- WHEN fetched
- THEN it is rejected

### Requirement: Base capabilities default ON

The shipped base catalog (explicit reviewed list of skills, connectors, tools) MUST be enabled by default when the policy does not mention an item; policy entries override defaults; explicit deny and platform `kill_switch` MUST win over any enable.

#### Scenario: Silent policy
- GIVEN a valid policy with no entry for base skill `pdf`
- WHEN resolved
- THEN `pdf` is enabled with source `base_default`

#### Scenario: Company deny
- GIVEN policy denies connector `github`
- WHEN resolved
- THEN it is disabled with source `company_policy`

#### Scenario: Kill switch
- GIVEN the platform kills `skill:x`
- WHEN the next policy sync arrives
- THEN `x` is disabled at once, including running sessions at next call

#### Scenario: Not in catalog
- GIVEN an item outside the base catalog and not approved by policy
- WHEN resolved
- THEN it is disabled with reason `not_approved`

### Requirement: Fail closed and offline grace

When no valid policy exists or the last-known-good is past `expires_at` (+ grace), only the base-safe subset (no exec, no remote connectors) MUST be enabled, with reason `policy_unavailable`/`policy_expired`.

#### Scenario: CP unreachable
- GIVEN a valid cached policy within expiry
- WHEN the CP is unreachable
- THEN the cached policy is applied and staleness is shown

#### Scenario: Expired
- GIVEN the cached policy has expired
- WHEN resolved
- THEN base-safe subset only

### Requirement: Exec tools require attestation

Exec-class tools MUST be enabled only when policy allows AND `exec_allowed()` from the sandbox runner returns allowed.

#### Scenario: Attestation pending
- GIVEN policy enables `code_execute` but attestation is pending
- WHEN resolved
- THEN disabled with reason `attestation_pending`

### Requirement: Audit emit

Capability enable/denied-use events MUST be queued without content (ids, action, time, result) and sent to the CP when its endpoint exists.

#### Scenario: Denied call
- GIVEN a tool call to a disabled capability
- WHEN attempted
- THEN it is refused, one audit event queued, no payload recorded
