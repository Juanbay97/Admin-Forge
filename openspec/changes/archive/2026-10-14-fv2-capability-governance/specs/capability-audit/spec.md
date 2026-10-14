# Capability Audit Specification

## Purpose
Append-only record of governance changes and tool-invocation metadata.

## Requirements

### Requirement: Change audit
Every catalog/policy write MUST append (actor, scope platform|org, org, action, target, before→after state, at) in the same transaction. Rows MUST NOT be updatable or deletable by any service role.

#### Scenario: Atomic
- GIVEN a policy write fails
- WHEN the transaction rolls back
- THEN no audit row remains

#### Scenario: Org visibility
- GIVEN a company admin
- WHEN reading audit
- THEN only own-company rows are returned

### Requirement: Invocation metadata
`POST /forge/v1/capabilities/audit` MUST accept batches ≤100 of {event_id, capability_id, at, outcome, duration_ms, sandbox_level}. Payload MUST be allow-listed fields only; unknown/free-text fields MUST be rejected. Dedupe by event_id.

#### Scenario: Content rejected
- GIVEN an event with `arguments` or `output`
- WHEN posted
- THEN 422 and nothing stored

#### Scenario: Replay
- GIVEN the same event_id twice
- WHEN posted
- THEN one row exists
