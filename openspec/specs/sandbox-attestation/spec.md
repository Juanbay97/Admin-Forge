# Sandbox Attestation Specification

## Purpose
Prove on each machine what isolation actually works, report it, and gate exec tools on it.

## Requirements

### Requirement: Adversarial escape suite

A versioned suite MUST attempt: `..` traversal, junction and symlink escape, env dump, loopback and metadata fetch, fork bomb, long-running process, large output, registry write, user-profile write. It MUST run (a) as unit tests in CI/dev and (b) at runtime as a self-test, producing per-case pass/fail.

#### Scenario: All pass
- GIVEN a capable machine
- WHEN the self-test runs
- THEN every case is "contained" and level L3 is reported

#### Scenario: A case escapes
- GIVEN any case is not contained
- WHEN the self-test finishes
- THEN the level drops to the highest level whose cases all passed and exec tools stay OFF

### Requirement: Attestation levels

Levels: L0 none, L1 jail + env scrub + timeouts, L2 + Job Object, L3 + AppContainer + egress guard (all suite cases), L4 container runner (suite re-run in container). Exec tools MAY be default-ON only at >= L3 (or L4 when policy selects the container runner).

#### Scenario: Job Object only
- GIVEN AppContainer is unavailable
- WHEN the suite runs
- THEN the level is L2 and exec tools are not default-ON

### Requirement: Cached per machine and per build

The result MUST be cached keyed by (suite version, client build, OS build, runner config hash), re-run when any changes or after 24h on startup (non-blocking), and never trusted from a copied file (HMAC with a DPAPI-protected key).

#### Scenario: Tampered cache
- GIVEN an edited cache file claiming L3
- WHEN loaded
- THEN it is discarded and the suite re-runs

### Requirement: Report to control plane

The client MUST send `{level, suite_version, client_version, os_build, cases:[{id,passed}], at}` (no paths, no env, no user content) to the CP when the endpoint exists, queueing locally otherwise. The CP MUST treat it as advisory telemetry (client-asserted).

#### Scenario: CP unavailable
- GIVEN the CP cannot be reached
- WHEN a report is due
- THEN it is queued (bounded) and retried; tools are gated locally regardless

### Requirement: Gate API

The runner package MUST expose `exec_allowed(policy) -> Decision{allowed, level, reason}` consumed by the capability layer; with no valid attestation the decision is `allowed=false`.

#### Scenario: No attestation yet
- GIVEN first launch before the suite finishes
- WHEN a tool asks
- THEN `allowed=false, reason="attestation_pending"`
