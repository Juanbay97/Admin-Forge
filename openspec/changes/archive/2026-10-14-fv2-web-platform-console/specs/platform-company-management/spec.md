# Platform Company Management Specification (new)

## Requirements

### Requirement: Company list
`/platform/companies` MUST list companies (name, code, status badge, members, 30d tokens, 30d cost, created) with search, status filter,
cursor pagination, URL-synced filters (`?q=&status=`), skeleton, EmptyState with "Create company", and row click → detail.

#### Scenario: Filter by status
- WHEN the owner selects "Suspended"
- THEN the URL has `status=suspended` and only suspended companies are listed; reload preserves it

### Requirement: Create-company wizard
The wizard MUST have steps: 1 Company (name, code with debounced availability check, slug rules `[a-z0-9-]{3,32}`), 2 Branding
(theme editor + live preview, optional → default Prometheon), 3 First admin (email, display name), 4 Keys & models (select ≥1 key from
the pool, model allow-list, ceiling), 5 Review & create. Steps validate with zod, are navigable backwards without data loss, keyboard
accessible, with a stepper that exposes `aria-current="step"`.

#### Scenario: Happy path
- GIVEN valid data in all steps
- WHEN the owner confirms
- THEN the company is created, branding/keys/models are applied, a success view shows the company code, "invitation sent to <email>" and a link to the detail

#### Scenario: Code taken
- WHEN the code is already used
- THEN step 1 shows "Code is taken" and Next is disabled

#### Scenario: Partial failure resumes
- GIVEN company creation succeeded but assigning keys failed
- THEN the review shows which steps are done/failed, offers "Retry failed steps", and the company detail shows "Finish setup" until all steps succeed

### Requirement: Company detail
`/platform/companies/:id` MUST present tabs (URL-synced) Overview (status, code, KPIs, setup checklist), Branding (reuse theme editor, publish),
Keys (assign/unassign from pool, shows last-4 only), Models (allow-list + ceiling, price shown per model), Usage (charts: tokens/cost by day,
share by model, top members; range 7/30/90), Members (read-only table: name, role, department, status).

#### Scenario: Assign key
- WHEN the owner assigns a pool key to the company
- THEN `PUT /companies/{id}/keys` is sent, the list updates, a toast confirms; removing the last key warns the company will lose gateway access

#### Scenario: Usage charts
- GIVEN 30 days of usage
- THEN the Usage tab shows area chart, model share bars, top members, each with accessible summaries and data tables

### Requirement: Suspend / reactivate
Suspend MUST require typing the company code in an AlertDialog, show the effect ("members lose access immediately"), and record success via toast;
reactivate uses a simple confirm. A suspended company MUST show a banner and read-only tabs except reactivate.

#### Scenario: Typed confirmation
- GIVEN the suspend dialog is open
- THEN the confirm button stays disabled until the exact code is typed

### Requirement: Safe handling of secrets and tenant data
Key material MUST never be rendered; pool key selection uses label + last-4. Member emails are shown only in the Members tab.

#### Scenario: Key list
- THEN no element contains more than the last 4 characters of any key
