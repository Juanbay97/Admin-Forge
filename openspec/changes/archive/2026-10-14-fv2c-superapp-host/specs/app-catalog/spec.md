# App Catalog Specification

## Purpose
Show and launch only the apps the effective policy enables.

## Requirements

### Requirement: Catalog from policy

The catalog MUST list `kind=app` items from the capability resolver; only enabled items are launchable; disabled items show their reason; with no policy or no apps the section is empty and says so.

#### Scenario: Enabled app
- GIVEN policy enables app `hello`
- WHEN the catalog renders
- THEN `hello` appears launchable

#### Scenario: Not enabled
- GIVEN `hello` is absent/denied
- WHEN a launch is attempted (UI or direct)
- THEN it is refused and nothing renders

### Requirement: Sample extension for tests only

A `hello` fixture extension MUST exist under test fixtures, MUST NOT be in the base catalog nor in production bundles.

#### Scenario: Bundle check
- GIVEN the production frontend build
- WHEN scanned
- THEN `hello` fixture is absent

### Requirement: Delivery route

The worker MUST serve extension entries read-only from the profile's extensions directory, by id, hash-verified, jail-validated, and only for items enabled by the resolver.

#### Scenario: Traversal
- GIVEN id `..%2f..%2fx`
- WHEN requested
- THEN 400/404, no file read
