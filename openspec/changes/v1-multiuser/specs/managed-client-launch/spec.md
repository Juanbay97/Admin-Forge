# Delta for Managed Client Launch

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Owned-account login with server-discovered context

The client MUST log in via owned accounts and obtain org context from `/accounts/me`; it MUST NOT rely on `disposable_local_fixture` or fixture files. A member of several active organizations MUST choose one and MUST be able to switch; switching MUST discard all state of the previous profile.
(Previously: the client used an org from `/accounts/me` with no choice or switching.)

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
