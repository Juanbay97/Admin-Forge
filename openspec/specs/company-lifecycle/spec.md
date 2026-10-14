# Company Lifecycle Specification

## Purpose

Platform-controlled creation, suspension and branding of companies, including the first-admin invitation.

## Requirements

### Requirement: Create company
The platform MUST create organization, unique slug (company code), default department and a first-admin invitation atomically. The invitation MUST carry `initial_role=organization_admin` and a platform issuer instead of an administrator membership. The raw capability MUST NOT be stored or audited.

#### Scenario: Happy path
- GIVEN an authenticated MFA-verified owner
- WHEN it creates company `acme` with admin email
- THEN org, department and pending invitation exist and one audit row is written

#### Scenario: Duplicate slug
- WHEN `acme` already exists
- THEN `COMPANY_CONFLICT`, nothing is created

### Requirement: Accept first-admin invitation
Accepting MUST create the account, membership with role `organization_admin` and department; member invitations MUST behave as before.

#### Scenario: First admin signs in
- GIVEN an accepted first-admin invitation
- WHEN the admin lists company members
- THEN the admin sees itself as `organization_admin`

#### Scenario: Suspended company
- GIVEN the company was suspended before accept
- WHEN accept is attempted
- THEN `INVITATION_DENIED`

### Requirement: Suspend and reactivate
Suspension MUST deny all member, admin and inference authority for that company within one request; reactivation MUST restore it. Other companies MUST be unaffected.

#### Scenario: Suspended member
- GIVEN an active member session
- WHEN the company is suspended
- THEN member routes are denied and inference stops

### Requirement: Platform branding edit
The platform MAY edit any company's branding via a platform function reusing branding validation; company admins keep editing their own.

#### Scenario: Cross-company edit scoped
- WHEN the owner edits company A branding
- THEN company B branding revision is unchanged
