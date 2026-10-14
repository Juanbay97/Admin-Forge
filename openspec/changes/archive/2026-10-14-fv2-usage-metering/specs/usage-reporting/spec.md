# Usage Reporting Specification

## Purpose

Rollups, prices and read APIs for platform owner and company admins.

## Requirements

### Requirement: Daily rollup
Each event insert MUST upsert `usage_daily` (UTC day, org, membership, model, key) in the same transaction; totals MUST equal the sum of events.

#### Scenario: Consistency
- GIVEN N events in a day
- THEN rollup tokens and request count equal their sums

### Requirement: Versioned prices
Platform MAY set `model_prices` per upstream id with input/output micros per Mtok, currency and `effective_from`; edits MUST create a new version and be audited. Cost MUST be snapshotted on the event; no price → cost null and flagged.

#### Scenario: Price change
- GIVEN events at price v1
- WHEN v2 is set
- THEN old events keep v1 cost, new events use v2

#### Scenario: Unpriced model
- THEN event cost is null and report marks it unpriced

### Requirement: Platform reports
The MFA-verified owner MUST query per-company, per-model and totals over a bounded time range with pagination.

#### Scenario: Range
- WHEN range spans two days
- THEN only those days' rows aggregate

#### Scenario: Not owner
- WHEN a company admin calls a platform report
- THEN `PLATFORM_DENIED`

### Requirement: Company per-person report
A company admin MUST see per-member usage for the own company only; members and other companies MUST be denied. Responses MUST NOT include other tenants' data or content.

#### Scenario: Cross-company
- WHEN admin of A requests B
- THEN denied

#### Scenario: Suspended member's history
- THEN past usage remains visible

### Requirement: Write isolation
The inference pool MUST only EXECUTE the record function; it MUST NOT read events or prices directly.

#### Scenario: Read attempt
- WHEN `forge_gateway_service` selects `usage_events`
- THEN permission denied
