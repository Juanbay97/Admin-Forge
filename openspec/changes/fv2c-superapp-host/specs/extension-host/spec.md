# Extension Host Specification

## Purpose
Run extensions in a sandboxed iframe behind a typed message bridge with user-granted permissions.

## Requirements

### Requirement: Sandboxed frame

The host MUST render the verified entry in `<iframe sandbox="allow-scripts">` without `allow-same-origin`, `allow-top-navigation`, `allow-popups`, `allow-forms`, `allow-downloads` or `allow-modals`, with an injected CSP `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:`; the extension MUST NOT access the parent DOM, cookies, storage or network.

#### Scenario: Isolation
- GIVEN the hello extension tries `parent.document`, `localStorage`, `fetch('/forge/health')`
- WHEN it runs
- THEN each attempt fails and the parent is unaffected

### Requirement: Typed bridge

The bridge MUST accept only messages from the host-created frame (`event.source` identity), shaped `{v:1, id, method, params}` validated by schema, size-capped (64 KiB) and rate-limited, and MUST answer `{id, ok|error}` via the frame's window. Unknown methods fail; no object references or functions cross the boundary.

#### Scenario: Foreign sender
- GIVEN a message from another window/frame
- WHEN received
- THEN it is ignored

#### Scenario: Oversize / malformed
- GIVEN a 1 MiB or schema-invalid message
- WHEN received
- THEN an error is returned and the frame may be terminated after repeated violations

### Requirement: Permission prompts

Methods needing a permission MUST trigger a host-owned prompt (outside the iframe, unforgeable by it) naming extension, publisher and permission; decisions are stored per profile and extension, revocable, default deny; a policy deny overrides user grant.

#### Scenario: Prompt and grant
- GIVEN hello calls `storage.set` without grant
- WHEN the member allows
- THEN the call succeeds and the grant persists

#### Scenario: Deny
- GIVEN the member denies
- WHEN the call repeats
- THEN it fails with `permission_denied`, no repeated prompt flooding (cooldown)

### Requirement: Namespaced storage with quota

`storage.*` MUST be namespaced per profile+extension, quota 256 KiB, cleared on uninstall/profile switch.

#### Scenario: Quota
- GIVEN usage at the quota
- WHEN another write arrives
- THEN `quota_exceeded`

### Requirement: Teardown

Switching profile/company or disabling the app by policy MUST destroy the frame and clear its state.

#### Scenario: Profile switch
- GIVEN a running extension
- WHEN the member switches organization
- THEN the frame is removed and storage namespace unreachable
