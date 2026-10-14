# Backup and Restore Specification

## Purpose
Recoverable data with explicit handling of the encryption keys that make it readable.

## Requirements

### Requirement: Scheduled database dump
The `backup` service MUST write `pg_dump -Fc` files with timestamps on a schedule (`FORGE_BACKUP_CRON`, default nightly) and prune beyond `FORGE_BACKUP_KEEP` (default 14), using a read-only role.

#### Scenario: Dump created
- GIVEN a running stack
- WHEN `backup run-once` executes
- THEN a non-empty dump exists and `pg_restore --list` succeeds

#### Scenario: Retention
- GIVEN KEEP=2 and 3 dumps
- WHEN pruning runs
- THEN only the newest 2 remain

### Requirement: Restore
`deploy/backup/restore.sh <file>` MUST restore into an empty database and refuse a non-empty target.

#### Scenario: Round trip
- GIVEN a dump from a seeded DB
- WHEN restored into a fresh volume
- THEN `migrate` is a no-op and readiness attests

### Requirement: Key custody runbook
The runbook MUST state that loss of the gateway/delivery Fernet keys makes stored gateway keys and queued messages unrecoverable, and MUST define a separate, offline backup of `deploy/secrets/`.

#### Scenario: Doc check
- GIVEN `docs/deploy.md`
- WHEN the doc test runs
- THEN it contains the key-loss warning and secrets-backup procedure

### Requirement: Dumps never contain env secrets
Backups MUST NOT include `deploy/secrets/` or `.env`.

#### Scenario: Archive content
- GIVEN a dump directory
- WHEN listed
- THEN no secret file is present
