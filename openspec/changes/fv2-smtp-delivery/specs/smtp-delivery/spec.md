# SMTP Delivery Specification

## Purpose
Deliver invitation and password-reset links by email through any standards-compliant SMTP relay.

## Requirements

### Requirement: Configuration
Settings MUST come from `FORGE_SMTP_HOST`, `PORT`, `SECURITY` (`starttls|tls|none`, default `starttls`), `USER`, `PASSWORD_FILE`, `FROM`, optional `CA_FILE`; unknown/invalid values MUST fail with `CONFIG_INVALID:<key>`. Credentials MUST NOT be accepted with `SECURITY=none`.

#### Scenario: Resend preset
- GIVEN host `smtp.resend.com`, port 465, security `tls`, user `resend`
- WHEN settings load
- THEN they are valid

#### Scenario: Cleartext with password
- GIVEN security `none` and a password file
- WHEN settings load
- THEN `CONFIG_INVALID:FORGE_SMTP_SECURITY`

### Requirement: Transport security
With `starttls` the adapter MUST upgrade before AUTH and MUST refuse to send if the server lacks STARTTLS; with `tls` it MUST use implicit TLS; certificates and hostnames MUST be verified.

#### Scenario: STARTTLS delivery
- GIVEN a fake server offering STARTTLS and AUTH
- WHEN an invitation is delivered
- THEN the server receives one authenticated, encrypted message

#### Scenario: Downgrade
- GIVEN a server without STARTTLS and mode `starttls`
- WHEN delivery runs
- THEN nothing is sent and the message state is `FAILED`

### Requirement: Message content
The message MUST contain only the recipient name and the onboarding/reset link; it MUST NOT contain passwords or secrets, and headers MUST reject injection.

#### Scenario: Link only
- GIVEN an invitation to `a@example.test`
- WHEN captured by the fake server
- THEN text and HTML parts contain the link and no password text; From equals `FORGE_SMTP_FROM`

#### Scenario: Header injection
- GIVEN a name containing CRLF
- WHEN delivered
- THEN the name is rejected

### Requirement: Failure semantics
Failures (connect, TLS, auth, rejected recipient, timeout) MUST map to the existing `FAILED` delivery state and MUST NOT expose host credentials, recipients or links in exceptions or logs.

#### Scenario: Bad credentials
- GIVEN the server rejects AUTH
- WHEN delivery runs
- THEN state `FAILED` and captured logs contain no password

#### Scenario: Timeout
- GIVEN a server that stalls
- WHEN 10 s elapse
- THEN the attempt aborts and `FAILED` is stored
