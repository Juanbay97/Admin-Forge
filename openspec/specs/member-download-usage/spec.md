# Member Download and Usage Specification (new)

## Requirements

### Requirement: Download page
`/portal/download` MUST show a 3-step guide (Download, Install, Open Forge and enter your company code), the **company code** prominently with copy button,
the installer button from `GET /downloads/latest.json` (version, size, release date, sha256 with "Verify" instructions), an "Open Forge" button using
`prometheon-forge://join?cp=<origin>&code=<slug>`, platform detection (Windows supported; other OS shows "Windows only for now"), and an SmartScreen note
(unsigned installer: "More info → Run anyway").

#### Scenario: Installer available
- GIVEN the manifest lists a Windows installer
- THEN the primary button links to its URL (same-origin), shows `v1.2.3 · 86 MB`, and the sha256 is selectable/copyable

#### Scenario: Installer not published
- GIVEN the manifest is 404 or empty
- THEN an Alert says the installer is not available yet and to contact the administrator; the company code is still shown

#### Scenario: Deep link
- WHEN the user clicks "Open Forge"
- THEN navigation to the custom scheme is attempted and a fallback hint "Not opening? Enter code ACME manually" is visible

### Requirement: Own usage
`/portal/usage` MUST show the signed-in member's tokens and cost for 7/30/90d (cost visible only if the contract exposes it), a daily chart, per-model
share, empty and error states; it MUST NOT expose other members' data.

#### Scenario: Usage present
- THEN KPIs, chart and accessible table render for the selected range (URL-synced)

#### Scenario: No usage
- THEN EmptyState suggests downloading the app and links to the download page

### Requirement: Portal home and navigation
`/portal` MUST show a welcome card (name, company, branded), "Get the app" card, a usage summary (7d sparkline) and the account menu (change password link, sign out).
Members have no access to company or platform areas.

#### Scenario: Home
- GIVEN a plain member
- THEN `/admin` redirects to `/admin/portal` and the nav contains only Home, Download, My usage

### Requirement: Control-plane hosting pieces
The control plane MUST serve `/downloads/*` read-only from a configured directory (traversal-safe like `_file`, `nosniff`, long cache for versioned files,
`no-cache` for `latest.json`) and redirect `GET /join` to `/admin/join` preserving the query (fragments survive redirects in browsers).

#### Scenario: Path traversal
- WHEN a request uses `../` or an encoded variant
- THEN the control plane returns 404 and serves nothing outside the directory

#### Scenario: Join redirect
- WHEN `/join?c=acme` is requested
- THEN the response is 307 to `/admin/join?c=acme`
