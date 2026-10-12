# Capabilities UI Specification

## Purpose
Members can see what is enabled and why.

## Requirements

### Requirement: Capabilities panel

A read-only panel MUST list skills, connectors, tools (and apps when present) grouped by kind with enabled/disabled state, source (`platform`, `company`, `base_default`, `attestation`, `kill_switch`), human-readable reason, policy revision, last sync time and attestation level. It MUST carry no admin controls.

#### Scenario: List
- GIVEN a resolved policy
- WHEN the member opens Capabilities
- THEN each item shows state and reason; exec tools show the attestation reason when pending

#### Scenario: Stale or invalid
- GIVEN the policy is stale/invalid/expired
- WHEN opened
- THEN a banner states the condition and that only base-safe items are active

#### Scenario: Empty / error
- GIVEN the endpoint fails
- WHEN opened
- THEN an honest error state is shown with retry; no fake data

### Requirement: Local read-only API

The worker MUST expose `GET /forge/v1/capabilities` (loopback, session-bound, in the router route allow-list) returning resolver output; it MUST NOT include secrets or raw policy signatures.

#### Scenario: Unauthenticated
- GIVEN no valid session
- WHEN requested
- THEN 401
