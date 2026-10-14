# Platform Operations Specification (new)

## Requirements

### Requirement: Overview dashboard
`/platform/overview` MUST show KPI cards (companies active/suspended, active users, tokens, cost for the selected 7/30/90d range with delta vs previous
period), a daily tokens+cost chart, top-10 companies bar by cost, key-pool health (available/degraded/retired), and recent audit events (5).
Range is URL-synced. Each card/chart has skeleton, empty ("No usage yet") and error states.

#### Scenario: Range change
- WHEN the owner selects 90d
- THEN `GET /overview?days=90` is requested and charts update; the URL has `days=90`

#### Scenario: Fresh platform
- GIVEN no companies
- THEN the dashboard shows the EmptyState "Create your first company" linking to the wizard

### Requirement: Key pool
`/platform/keys` MUST list pool keys (label, provider endpoint host, last-4, status active/retired, companies assigned, last used), allow adding a key through
a write-only field (never echoed, cleared after submit), renaming, and retiring with AlertDialog. Retiring a key still assigned MUST show
`KEY_IN_USE` guidance with the list of affected companies.

#### Scenario: Add key
- WHEN the owner submits label and secret
- THEN POST `/keys` is sent once, the secret input is emptied, the new row shows only last-4

#### Scenario: Retire in use
- GIVEN the API returns `KEY_IN_USE`
- THEN the dialog stays open and shows the affected companies

### Requirement: Model prices
`/platform/prices` MUST list models with input/output price per 1M tokens (USD), effective date, history drawer; editing validates non-negative
numbers (≤ 6 decimals), converts to micro-USD integers, and requires an effective date ≥ today.

#### Scenario: Edit price
- WHEN the owner sets input 3.00 and output 15.00 USD/M
- THEN the request sends `input_micros_per_mtok: 3000000`, `output_micros_per_mtok: 15000000`

### Requirement: Audit log
`/platform/audit` MUST show a read-only, newest-first table (time, actor, action, target, summary) with filters (actor, action, date range), cursor "Load more",
URL-synced filters, and relative+absolute times.

#### Scenario: Filter
- WHEN the owner filters action = `company.suspend`
- THEN only matching events are listed and the filter survives reload

### Requirement: Quality gates
Every platform route MUST pass axe (light+dark, 3 viewports), zero CSP violations, and have a Playwright real-stack journey.

#### Scenario: Sweep
- WHEN the sweep test visits all platform routes
- THEN no serious/critical axe violations and no CSP violations are reported
