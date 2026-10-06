# Outbox Publication Specification

## Purpose
Record committed changes and publish operational notifications.

## Delivery slices
P1a delivers only the generic transaction-bound recorder, scoped INSERT role and destination readiness/migration proof. Callers remain responsible for authorizing resource mutations and supplying trusted tenant context; no public API or consumer is enabled. P1b owns atomic legacy backfill/mirroring and all corresponding compatibility/security proofs. Until P1b installs, the untouched legacy outbox remains its source of truth. O2 delivery and O3 sink behavior remain pending P1b/P2; recording alone does not complete them.

## Requirements

### Requirement: O1 Atomic recording
Each committed mutation MUST record exactly one stable event; failed mutations MUST record none.

#### Scenario: Commit or rollback
- GIVEN an authorized mutation
- WHEN its transaction commits or fails
- THEN state, revision and event commit together or all remain unchanged.

### Requirement: O2 Recoverable delivery
Publication MUST support concurrent workers, bounded retries and crash recovery, including initial-administrator events; delivery is at-least-once, not exactly-once.

#### Scenario: Concurrent claims
- GIVEN pending generic and initial-administrator events
- WHEN two workers claim concurrently
- THEN live claims do not overlap and both sources remain deliverable.

#### Scenario: Retry after crash
- GIVEN a failed delivery or expired claim after delivery
- WHEN retry becomes eligible
- THEN the same event ID is retried; stale acknowledgments cannot complete newer claims.

### Requirement: O3 Redacted sink
Until S6, publication MUST use redacted logs, MUST NOT claim durable audit proof, and MUST NOT expose tokens, identity claims, credentials or arbitrary metadata.

#### Scenario: Sensitive failure
- GIVEN sensitive markers in payloads and exceptions
- WHEN publishing fails
- THEN logs contain only approved fields and the event remains retryable.
