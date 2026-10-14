# Platform Console Access Specification (new)

## Requirements

### Requirement: Platform sign-in with TOTP
A platform account signs in with email+password on the shared login. When `platform/me` reports `mfa.enrolled` and `level != totp`,
the SPA MUST show a 6-digit code step (with "use a recovery code" alternative) before any platform screen or data call. Wrong code
MUST show an inline error without leaving the step; after the server's lockout code the form MUST disable with the retry-after.

#### Scenario: Successful challenge
- GIVEN an enrolled platform owner with valid password
- WHEN they enter a valid 6-digit code
- THEN session level becomes `totp` and `/admin/platform` (overview) renders

#### Scenario: Invalid code
- WHEN the code is wrong
- THEN an `role="alert"` message appears, input keeps focus, no platform data is requested

#### Scenario: MFA_REQUIRED mid-session
- GIVEN a platform call returns `403 MFA_REQUIRED`
- THEN the user is routed to the code step and returns to the same URL after verifying

### Requirement: Mandatory TOTP enrollment
A `platform_owner` without enrollment MUST be forced to enrollment before the console: show QR (SVG rendered from `otpauth_uri`),
manual secret (copy button), confirm with a code, then show recovery codes once with "I stored them" gate (copy + download).
The secret and codes MUST exist only in component state and be cleared on leaving the step.

#### Scenario: Enrollment
- GIVEN an owner without TOTP
- WHEN they scan/enter the secret and confirm a valid code
- THEN recovery codes are shown once; Continue stays disabled until the checkbox is ticked; after Continue no secret remains in the DOM

### Requirement: Platform guard and fixed theme
`/admin/platform/*` MUST render only for platform accounts with MFA level `totp`; others see AccessDenied. The area MUST always use the
fixed Prometheon theme (never company branding), support dark mode, and show a persistent "Platform console" badge and the owner's email.

#### Scenario: Branding isolation
- GIVEN the owner previewed a company theme in the wizard
- WHEN they navigate to any other platform page
- THEN the console chrome still uses Prometheon tokens

### Requirement: Session hygiene
Sign-out and 401 MUST clear the Query cache (company data is sensitive). Idle timeout 30 minutes MUST sign out the owner with a notice.

#### Scenario: Idle
- GIVEN 30 minutes without interaction
- THEN the session is cleared and the login page shows "Signed out for inactivity"
