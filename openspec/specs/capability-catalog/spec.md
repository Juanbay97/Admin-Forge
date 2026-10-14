# Capability Catalog Specification

## Purpose
Platform-wide registry of governable capabilities.

## Requirements

### Requirement: Catalog entries
Each entry MUST have id `<kind>:<slug>`, kind ∈ tool|skill|connector|plugin|app, version, risk (low|medium|high), `is_base`, `default_state` (on|off), `min_sandbox_level` (0–3), `manifest_sha256`. Only a platform owner MAY create/modify entries; the CP MUST reject duplicates and unknown kinds.

#### Scenario: Seed is idempotent
- GIVEN the seed is applied
- WHEN it is applied again
- THEN no entry changes and revision does not bump

#### Scenario: Non-platform write denied
- GIVEN a company admin session
- WHEN it attempts catalog create
- THEN the request is denied and nothing is written

### Requirement: Base defaults
Base skills and connectors MUST default ON. Execution tools (`bash`,`powershell`,`code_execute`) MUST default ON with `min_sandbox_level`=3. Plugins, computer/browser/channels/remote/automation tools MUST default OFF.

#### Scenario: Seed matches inventory
- GIVEN the seed file
- WHEN parsed
- THEN ids are unique and counts cover 25 skills, 46 connectors, 15 plugins, ≥22 tools
