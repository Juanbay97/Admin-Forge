# Member Onboarding Specification (new)

## Requirements

### Requirement: Branded join entry
`/admin/join?c=<slug>#invitation_id=<uuid>&capability=<token>` MUST resolve public branding for `<slug>` before showing the form (skeleton, then themed page
with company name/mark/login copy); unknown or missing `c` MUST fall back to the Prometheon theme. The page MUST work signed-out and MUST NOT call authenticated endpoints.

#### Scenario: Branded
- GIVEN company `acme` has branding
- WHEN the invitee opens the link
- THEN the page shows Acme's mark, name and palette, and a "Create your password" form

#### Scenario: Fragment hygiene
- WHEN the page first renders
- THEN `location.hash` is empty (replaceState), the capability exists only in memory, and is never written to storage or logged

### Requirement: Accept invitation with password
The form (rhf+zod) MUST collect password + confirmation with live policy hints (length ≥ 12 and server policy codes), show/hide toggle, strength-neutral copy,
`autocomplete="new-password"`, and submit once (button loading, double-submit guarded). Success signs in and routes to `/portal/download`.

#### Scenario: Success
- GIVEN a valid invitation
- WHEN the user submits a valid password
- THEN `POST /accounts/invitations/accept` is sent, the user is signed in (email from `account_email`, else asked once), and lands on the download page

#### Scenario: Policy rejection
- WHEN the server returns `PASSWORD_POLICY`
- THEN the field shows the mapped message and the form stays editable

### Requirement: Invitation error states
`INVITATION_EXPIRED`, `INVITATION_USED`, `INVITATION_INVALID`, missing fragment, and network failure MUST each render a distinct, friendly state with
the next action (ask admin for a new invite / sign in / retry) and no technical codes. `EXISTING_ACCOUNT_AUTH_REQUIRED` MUST offer sign-in and explain the limitation.

#### Scenario: Expired
- THEN the page says the invitation expired and to ask the company administrator for a new one; no form is shown

### Requirement: Post-accept sign-in and gating
After onboarding, members land in the portal area; org admins keep `/company` as home; the join page for an already signed-in session MUST not auto-accept.

#### Scenario: Signed-in visitor
- GIVEN a signed-in user opens a join link
- THEN a notice offers to sign out first or continue to their home

### Requirement: Quality
Join and portal pages MUST pass axe at 375/768/1280, have visible focus order, and zero CSP violations.

#### Scenario: Mobile join
- GIVEN 375px
- THEN the form is usable without horizontal scroll and targets ≥ 44px
