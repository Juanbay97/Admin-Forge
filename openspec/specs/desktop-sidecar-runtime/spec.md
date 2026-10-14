# Desktop Sidecar Runtime Specification

## Purpose
The Tauri shell launches the bundled backend as a profile router sidecar with the same contract as `scripts/forge-managed.mjs`.

## Requirements

### Requirement: Router sidecar lifecycle

Rust MUST spawn the bundled backend in router mode on a validated loopback port with explicit arguments and a scrubbed environment, MUST wait for `/forge/health`, and MUST stop router and workers when the app exits (graceful CTRL_BREAK, then process-tree kill).

#### Scenario: Start
- GIVEN the app launches
- WHEN the guard passes
- THEN the router answers `/forge/health` and no worker exists until sign-in

#### Scenario: Exit
- GIVEN a running router with workers
- WHEN the app quits or crashes
- THEN no router/worker process remains (kill-on-close)

#### Scenario: Port conflict
- GIVEN the configured port is taken
- WHEN the app starts
- THEN it picks a free loopback port or shows an error; it never binds a non-loopback address

### Requirement: Quarantine replaced by a build-attested guard

The unconditional startup panic MUST be replaced by a guard that passes only when the build embeds an attestation produced by the isolation verifier, MUST fail closed otherwise, and MUST have no environment or CLI bypass.

#### Scenario: Attested build
- GIVEN a build whose verifier passed
- WHEN the app starts
- THEN startup continues

#### Scenario: Unattested build
- GIVEN a build without attestation or with a tampered one
- WHEN the app starts
- THEN it exits with a clear message and starts nothing

### Requirement: Parity with the web launcher

Arguments, environment keys and port semantics passed to the router MUST equal those of `forge-managed.mjs` (checked by a parity test).

#### Scenario: Parity
- GIVEN the same configuration
- WHEN both launchers build a command
- THEN argument lists and allowed env keys are equal
