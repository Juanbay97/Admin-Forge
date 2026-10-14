# Extension Manifest Specification

## Purpose
Describe and integrity-check an embeddable extension before any code runs.

## Requirements

### Requirement: Strict manifest

A manifest MUST be JSON with exactly `id` (reverse-dns slug), `version` (semver), `publisher`, `entry` (relative single-file `.html`), `permissions` (subset of the known list), `sha256` (hex of entry bytes) and optional `signature`. Unknown keys, path traversal in `entry`, duplicate or unknown permissions, and oversize files MUST be rejected.

#### Scenario: Valid
- GIVEN the hello manifest
- WHEN validated
- THEN it passes and yields a typed object

#### Scenario: Hostile
- GIVEN `entry: "../../x.html"`, extra key `scripts`, or permission `fs.write`
- WHEN validated
- THEN it fails with a specific error and nothing loads

### Requirement: Integrity

Before load, the entry bytes' sha256 MUST equal the manifest `sha256`; when the effective policy carries `manifest_sha256` for the app it MUST match too; a `signature`, when present and a pinned key exists, MUST verify.

#### Scenario: Tampered entry
- GIVEN entry bytes differ from `sha256`
- WHEN loaded
- THEN loading is refused and an error state is shown

#### Scenario: Policy pin mismatch
- GIVEN policy `manifest_sha256` differs from the manifest hash
- WHEN loaded
- THEN refused with reason `policy_mismatch`

### Requirement: Known permission list

Permissions known in v1: `ui.title`, `storage.local`. Future names (`network`, `fs`, `tools`) MUST be reserved and rejected at validation until a later change enables them.

#### Scenario: Reserved permission
- GIVEN `permissions: ["network"]`
- WHEN validated
- THEN it fails as `reserved_permission`
