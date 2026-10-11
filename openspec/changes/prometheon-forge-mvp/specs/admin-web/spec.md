# Delta for Admin Web

## ADDED Requirements

### Requirement: Same-origin SPA with strict delivery

The admin SPA (`admin/`, Vite + React + TS + Tailwind) MUST be built into the control-plane package and served same-origin at `/admin`. It MUST NOT load remote scripts, fonts or styles, and MUST NOT persist credentials or keys in localStorage/sessionStorage/IndexedDB or URLs.

#### Scenario: Offline assets
- GIVEN the built bundle
- WHEN loading `/admin` with network blocked except same origin
- THEN the page renders with local Montserrat/Inter fonts and no blocked requests

#### Scenario: No storage
- GIVEN a completed login and key save
- WHEN inspecting browser storage and URL history
- THEN no password, session token or gateway key is present

### Requirement: Login and per-company partition

The SPA MUST authenticate via owned-account login, discover orgs from `/accounts/me`, show an org picker only for orgs where the user is admin, and scope every screen to the selected org. Non-admin users MUST be denied.

#### Scenario: Admin login
- GIVEN an org A admin
- WHEN logging in
- THEN org A is shown (auto-selected if single) and only A's data is rendered

#### Scenario: Member login
- GIVEN a plain member
- WHEN logging in to the admin web
- THEN an access-denied screen appears and no admin API data is fetched

#### Scenario: Org switch clears state
- GIVEN an admin of A and B
- WHEN switching from A to B
- THEN A's members, gateway and catalog data are cleared before B's load

#### Scenario: Cross-org 404 rendering
- GIVEN a stale org id returns 404
- WHEN a screen loads
- THEN a generic "not found" is shown without leaking org existence

### Requirement: Members and departments screens

The SPA MUST list members/departments, invite (with department), and suspend/reactivate, showing last-admin refusal as a clear redacted message.

#### Scenario: Invite
- GIVEN departments exist
- WHEN the admin invites an email to a department
- THEN the member appears as invited/pending

#### Scenario: Suspend last admin
- GIVEN a single admin
- WHEN trying to suspend self
- THEN the action is blocked with an explanatory message and list unchanged

### Requirement: Gateway and catalog screens

The SPA MUST let admins select an allow-listed base URL, submit a write-only key (never displayed, cleared after submit), handle CAS revision conflicts, refresh discovery, map aliases to upstream ids, publish, and view status.

#### Scenario: Save key
- GIVEN a base URL and typed key
- WHEN saved
- THEN the field is cleared, UI shows only "configured" and revision, and the key is absent from DOM and network responses

#### Scenario: Revision conflict
- GIVEN another admin updated the config
- WHEN saving with a stale revision
- THEN a conflict message prompts reload and nothing is overwritten

#### Scenario: Publish catalog
- GIVEN refreshed upstream models
- WHEN the admin maps aliases and publishes with a default
- THEN status shows published aliases and a member then sees exactly those

### Requirement: Accessibility

The SPA MUST be keyboard operable, label all inputs, and honor `prefers-reduced-motion`.

#### Scenario: Keyboard and motion
- GIVEN reduced-motion is set
- WHEN completing login via keyboard only
- THEN it succeeds with no non-essential animation
