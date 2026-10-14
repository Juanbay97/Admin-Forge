# Schema Migration Runner Specification

## Purpose
Apply the reviewed migrations to a deployment database safely, repeatably and verifiably.

## Requirements

### Requirement: Ordered, recorded application
The runner MUST apply pending migrations in canonical order under a session advisory lock, recording `(version, name, sha256, applied_at)` in `forge.schema_migrations`.

#### Scenario: Fresh database
- GIVEN an empty PG17 cluster
- WHEN `migrate` runs
- THEN all migrations are recorded and readiness attests the latest checkpoint

#### Scenario: Concurrent runners
- GIVEN two runners start together
- WHEN both acquire the lock in turn
- THEN migrations apply once and the second is a no-op

### Requirement: Idempotence
Re-running with nothing pending MUST change no schema and exit 0.

#### Scenario: Rerun
- GIVEN a fully migrated database
- WHEN `migrate` runs again
- THEN no script executes

### Requirement: Checksum integrity
If an applied migration's file hash differs from its record, the runner MUST abort with `MIGRATION_CHECKSUM_MISMATCH` before applying anything.

#### Scenario: Edited migration
- GIVEN a recorded 0010 whose file changed
- WHEN `migrate` runs
- THEN it exits non-zero and applies nothing

### Requirement: Fingerprint verification and adoption
After applying, the catalog fingerprint MUST equal the latest checkpoint, else `SCHEMA_FINGERPRINT_MISMATCH`. A database with the `forge` schema but no records MUST be adopted only when its fingerprint equals a known checkpoint; otherwise refused.

#### Scenario: Crash between script and record
- GIVEN a migration applied but unrecorded
- WHEN `migrate` runs
- THEN it records it without re-executing

#### Scenario: Unknown legacy schema
- GIVEN a `forge` schema with an unknown fingerprint
- WHEN `migrate` runs
- THEN `UNKNOWN_SCHEMA` and nothing changes

### Requirement: Service role passwords
The runner MUST set LOGIN passwords for the service roles from secret files on every run and MUST NOT print them.

#### Scenario: Rotation
- GIVEN a changed password file
- WHEN `migrate` runs
- THEN the role accepts only the new password
