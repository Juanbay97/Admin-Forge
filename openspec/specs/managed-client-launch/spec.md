# Managed Client Launch Specification

## Purpose

Source of truth for managed-client-launch, established by change `prometheon-forge-mvp`.

## Requirements

### Requirement: Single sanctioned launcher replaces quarantine

The client MUST start only through one official launcher (explicit args: backend origin, ports, Forge API origin; supports `next build && next start`). The unconditional quarantine throw MUST be replaced by verified isolation checks (not simply removed); scripts MUST fail closed if checks fail.

#### Scenario: Launch with valid args
- GIVEN valid explicit origins and distinct ports
- WHEN running the launcher
- THEN backend and frontend start, isolation checks pass and the login screen is reachable

#### Scenario: Isolation check fails
- GIVEN a configuration that enables tools, a user-supplied provider key path or an unpinned origin
- WHEN launching
- THEN the launcher exits non-zero before binding ports

#### Scenario: Direct legacy scripts
- GIVEN the former `dev:*` or key-flow scripts
- WHEN run
- THEN they are deleted or refuse to run, with no path to a manual key flow

### Requirement: Manual key flow and in-client admin removed

The client MUST NOT contain `ManagedGateway`, `--gateway-stdin`, key prompts, `GatewayAdminView` or fixed gateway endpoints; users MUST never type, see or store a gateway key.

#### Scenario: No key surface
- GIVEN a built client
- WHEN scanning bundle, backend CLI and UI routes
- THEN no key input, gateway admin route or gateway origin literal exists

#### Scenario: Admin route absent
- GIVEN a logged-in employee
- WHEN visiting `/forge-accounts` gateway admin
- THEN a 404/not-found is shown

### Requirement: Owned-account login with server-discovered context

The client MUST log in via owned accounts and obtain org context from `/accounts/me`; it MUST NOT rely on `disposable_local_fixture` or fixture files. A member of several active organizations MUST choose one and MUST be able to switch; switching MUST discard all state of the previous profile.

#### Scenario: Login and discovery
- GIVEN a valid member
- WHEN logging in
- THEN the client uses an org from `/accounts/me` and shows only published aliases from the member catalog

#### Scenario: Suspended or invalid
- GIVEN a suspended member or wrong password
- WHEN logging in
- THEN a generic denial appears and no workspace is created

#### Scenario: Logout and mid-stream suspension
- GIVEN an active streaming chat
- WHEN the member logs out or is suspended
- THEN the stream stops, the session is revoked and the workspace gate re-locks

#### Scenario: Several organizations
- GIVEN an account active in orgs A and B
- WHEN it logs in and switches from A to B
- THEN B's catalogue and sessions load and none of A's sessions remain visible

### Requirement: Chat through Forge only, no secrets client-side

Chat MUST go to the Forge backend (no tools, text only); the browser MUST NOT be able to reach the gateway origin or any key, and the 16-message/4 KiB limits MUST surface as a clear error.

#### Scenario: Streamed chat
- GIVEN a member and a published alias
- WHEN sending a message
- THEN tokens stream from Forge, and network logs show no gateway host or `Authorization` of the gateway key

#### Scenario: Over-limit
- GIVEN a 17th message or >4096-char input
- WHEN sending
- THEN a limit message is shown and nothing is forwarded upstream

#### Scenario: Unpublished alias
- GIVEN an alias not published for the org
- WHEN requested directly
- THEN the request is denied

### Requirement: Launcher runs the profile router

The launcher MUST start the profile router (not a single bound backend) on the backend port, pass workers only explicit validated arguments and a scrubbed environment, and stop router and workers together.

#### Scenario: Launch
- GIVEN valid explicit origins and distinct ports
- WHEN the launcher runs
- THEN the router answers `/forge/health` and starts no worker until a member signs in

#### Scenario: Stop
- GIVEN running workers
- WHEN the launcher is stopped
- THEN router and all workers exit
