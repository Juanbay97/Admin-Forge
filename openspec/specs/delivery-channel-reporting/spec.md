# Delivery Channel Reporting Specification

## Purpose
The API and port report the real delivery channel; dev behaviour is preserved.

## Requirements

### Requirement: Widened delivery port
`MessageDelivery.deliver` MUST return an opaque non-secret receipt and the coordinator MUST NOT depend on a filesystem path.

#### Scenario: Local mailbox unchanged
- GIVEN `LocalTestMailbox`
- WHEN a message is delivered
- THEN the `.eml` is written exactly as before

### Requirement: Truthful channel
`delivery_channel` in invitation and password-reset responses MUST be `smtp` for SMTP and `local_test_mailbox` for the local adapter; the response field set MUST stay identical to the contract pin.

#### Scenario: SMTP channel
- GIVEN the coordinator uses `SmtpDelivery`
- WHEN an invitation is issued
- THEN the 201 body has `delivery_channel: "smtp"` and the contract test passes

### Requirement: Company-code hint
`onboarding_link` MAY accept a public `company_code`, adding `c=<slug>` before the fragment; absent, the link MUST be unchanged and the capability MUST stay in the fragment.

#### Scenario: Link with code
- GIVEN company code `acme`
- WHEN the link is built
- THEN `…?c=acme#invitation_id=…&capability=…`

#### Scenario: Default link
- GIVEN no code
- WHEN the link is built
- THEN it equals the previous `/onboarding#…` form

### Requirement: Adapter selection
`serve_prod` MUST use SMTP when `FORGE_SMTP_HOST` is set and fail closed otherwise (no silent local fallback in production).

#### Scenario: No SMTP in prod
- GIVEN prod profile without SMTP settings
- WHEN the app starts
- THEN `CONFIG_INVALID:FORGE_SMTP_HOST`
