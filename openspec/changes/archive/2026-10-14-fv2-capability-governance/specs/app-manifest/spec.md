# App Manifest Specification

## Purpose
Extension contract for future embedded apps; schema and governance only.

## Requirements

### Requirement: Manifest schema
A manifest MUST contain id (reverse-DNS), semver version, publisher, relative `entry`, `permissions[]` from a closed vocabulary, `sha256`, `signature`. Validator MUST reject unknown keys, absolute/traversal entry paths, unknown permissions, and wildcard network hosts.

#### Scenario: Valid
- GIVEN a conformant manifest
- WHEN validated
- THEN it is accepted and `manifest_sha256` is canonical-JSON stable

#### Scenario: Traversal
- GIVEN entry `../x`
- WHEN validated
- THEN rejected

### Requirement: Permission governance
An app catalog entry MUST list granted permissions approved by a platform owner; effective policy MUST expose only granted ⊆ declared permissions. Apps follow the same policy layers as other capabilities, default OFF.

#### Scenario: Over-declared
- GIVEN declared permissions exceed granted
- WHEN effective policy resolves
- THEN only granted are listed

### Requirement: No app runtime
This change MUST NOT ship an app host or executable apps.

#### Scenario: Scope
- GIVEN the change diff
- WHEN reviewed
- THEN no iframe/host-bridge code exists
