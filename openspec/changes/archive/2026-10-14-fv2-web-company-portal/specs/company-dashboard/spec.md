# Company Dashboard Specification (new)

## Requirements

### Requirement: Org usage dashboard
`/company/dashboard` (home for org admins) MUST show KPI cards (active members, tokens, cost for range 7/30/90d, delta vs previous), an area chart by day,
model share bars, and a per-person table (name, department, tokens, cost, share bar, last active) sortable and filterable by department, plus
a top-5 people bar. Range and sort are URL-synced. Admins see usage only for their organisation.

#### Scenario: Per-person usage
- GIVEN usage for 12 members
- THEN the table lists them sorted by cost desc with share bars; sorting by name works; keyboard operable

#### Scenario: No usage yet
- THEN EmptyState "No usage yet" explains usage appears after the first chat and links to the download/invite guide

#### Scenario: Multi-org admin
- GIVEN an admin of two organisations
- WHEN they switch company in the topbar
- THEN all dashboard queries re-key to the new organisation and previous data is not shown

### Requirement: Members and departments
Members page MUST keep existing behaviour (invite, suspend/reactivate, roles) in the kit DataTable and add department filter and a Departments
tab (list, create). Assigning a member's department MUST use the contract assignment endpoint when present (PC-9), otherwise show departments read-only.

#### Scenario: Create department
- WHEN the admin creates "Finance"
- THEN it appears in the list and in the member filter without reload

### Requirement: Gateway status is read-only
The Gateway page MUST show connection health, number of assigned keys (label + last-4 only), allowed models, ceiling model, and "Managed by Prometheon"
text; it MUST NOT offer key entry or removal.

#### Scenario: Read-only
- THEN no password/secret input exists on the page and a help text explains who to contact to change keys

### Requirement: Branding retained
The branding editor MUST continue to work unchanged (existing branding suite green) with the kit's ThemeEditor.

#### Scenario: Save branding
- WHEN the admin saves a new primary colour
- THEN the company area re-themes immediately and the portal for that company code serves the new branding

### Requirement: Admin gating
Only `organization_admin` MAY open `/company/*`; members are redirected to `/portal`.

#### Scenario: Member opens company URL
- THEN they land on `/portal` with no company-area API calls made
