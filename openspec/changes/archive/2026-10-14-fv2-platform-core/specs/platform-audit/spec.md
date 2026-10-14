# Platform Audit Specification

## Purpose

Tamper-evident record of platform actions.

## Requirements

### Requirement: Append-only audit
Every platform mutation MUST insert one `platform_audit_log` row (actor, action, target org, at) in the same transaction. The table MUST reject UPDATE/DELETE for all runtime roles. Rows MUST NOT contain secrets, emails or capabilities.

#### Scenario: Mutation audited
- WHEN the owner suspends a company
- THEN exactly one `company.suspended` row exists

#### Scenario: Failed action
- WHEN a platform function is denied
- THEN no mutation and no success audit row exist

#### Scenario: Immutable
- WHEN any role attempts UPDATE on the audit table
- THEN permission is denied

### Requirement: Audit read
The owner MAY page the audit log, newest first, bounded page size.

#### Scenario: Non-owner
- WHEN a company admin requests it
- THEN `PLATFORM_DENIED`
