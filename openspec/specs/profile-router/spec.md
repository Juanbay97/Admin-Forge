# Profile Router Specification

## Purpose

One loopback entry point serves many members and organizations; each (organization, membership) profile runs in its own worker process with its own data directory.

## Requirements

### Requirement: Process-per-profile isolation

The router MUST serve each (organization, membership) profile from a dedicated worker process and data directory, and MUST NOT route a request to a worker of another profile.

#### Scenario: Concurrent members
- GIVEN members M1, M2 of org A and M3 of org B signed in
- WHEN all three chat concurrently
- THEN three workers and three profile directories exist and each member lists only their own sessions

#### Scenario: Same account, two orgs
- GIVEN one account that is an active member of orgs A and B
- WHEN it uses each org
- THEN each org uses a distinct worker and data directory

#### Scenario: Worker invariant
- GIVEN a worker bound to profile P
- WHEN a request for another profile reaches it directly
- THEN the worker answers 403

### Requirement: Bearer authentication before routing

The router MUST validate every bearer against the control plane before it spawns or reaches a worker. The organization MUST come from `X-Forge-Organization` or the org-scoped URL and MUST be a UUID.

#### Scenario: Missing or invalid bearer
- GIVEN no bearer, a malformed bearer or a revoked session
- WHEN calling an org-scoped route
- THEN 401 and no worker is spawned

#### Scenario: Non-member organization
- GIVEN a valid bearer for org A only
- WHEN requesting org B
- THEN an identical redacted denial as for a nonexistent org and no worker is spawned

#### Scenario: Missing or malformed organization
- GIVEN a valid bearer
- WHEN `/api/*` is called without a UUID organization header
- THEN 403 and nothing is forwarded

### Requirement: Worker lifecycle

The router MUST reap workers idle beyond a TTL, MUST NOT reap a worker with an in-flight request or stream, MUST cap concurrent workers, and MUST stop a profile's workers on logout, on suspension of that membership and on router shutdown. Profile data MUST survive reaping.

#### Scenario: Idle reap and respawn
- GIVEN an idle worker past its TTL
- WHEN the reaper runs and the member returns
- THEN the process was stopped, a new one starts and earlier sessions are still listed

#### Scenario: Active stream
- GIVEN an open SSE stream past the idle TTL
- WHEN the reaper runs
- THEN the worker keeps running

#### Scenario: Cap reached
- GIVEN the cap with every worker busy
- WHEN a new profile is requested
- THEN 503 with a redacted body; with an idle worker present the least recently used is stopped instead

#### Scenario: Logout and suspension
- GIVEN a member with a running worker
- WHEN the member logs out, or is suspended in that org
- THEN that profile's worker stops and its streams end; other profiles are unaffected

#### Scenario: Router exit
- WHEN the router stops
- THEN no worker process it started remains

### Requirement: Fail closed and transparent proxy

Spawn or readiness failure MUST yield 503 without detail. SSE bodies MUST be streamed unbuffered. Host, Origin and cookie policies of the worker MUST still hold.

#### Scenario: Worker fails to start
- GIVEN a worker that never reports healthy
- WHEN a profile is first requested
- THEN 503, the process is stopped and a later request may retry

#### Scenario: Streamed chat
- GIVEN a published alias
- WHEN a member sends a prompt through the router
- THEN tokens arrive incrementally
