# Proposal: Generic SMTP Invitation Delivery

## Intent

Invitations and password resets are delivered only by `LocalTestMailbox` (writes `.eml`; "no SMTP claim"). `account_api.py` hard-codes `delivery_channel: 'local_test_mailbox'`, and the `MessageDelivery` port returns a file `Path`. Employees cannot receive real email. Decision: SMTP via Resend now (`smtp.resend.com`), Amazon SES later → one generic configurable adapter, no credentials in the repo.

## Scope

### In Scope
- `forge.smtp_delivery.SmtpDelivery` (stdlib `smtplib`): security `starttls` (default) | `tls` | `none`, host/port/user/password-file/from, hostname-verified TLS, timeouts, finite non-secret failures.
- `SmtpSettings` parsed from `FORGE_SMTP_*` (`FORGE_SMTP_PASSWORD_FILE`); documented presets: Resend 465 tls / 587 starttls (user `resend`), SES `email-smtp.<region>.amazonaws.com:587`.
- Port widening: `MessageDelivery.deliver` returns an opaque receipt; `DeliveryCoordinator.channel` from adapter; API reports `smtp` or `local_test_mailbox`.
- Shared message builder extracted from `LocalTestMailbox` (links only, never passwords).
- Optional `company_code` query param on `onboarding_link` (default unchanged).
- Wiring in `serve_prod`; `LocalTestMailbox` retained for dev; Mailpit in `compose.dev.yml` for the Docker proof.
- Test fixture: `aiosmtpd` fake server (STARTTLS + implicit TLS + AUTH).

### Out of Scope
- Async retry worker/outbox daemon, bounce webhooks, DKIM/SPF setup (user's DNS), `/join` portal route and link path change (fv2-web-company-portal), email templates/branding, SES specifics beyond docs.

## Capabilities

### New Capabilities
- `smtp-delivery`: configuration, transport security, message content and failure semantics.
- `delivery-channel-reporting`: truthful channel name and widened delivery port.

### Modified Capabilities
None (no pre-existing specs).

## Approach

Extract `build_message()` from `LocalTestMailbox.deliver`; `SmtpDelivery.deliver` builds the same message and sends with `smtplib.SMTP`/`SMTP_SSL` under `ssl.create_default_context()` (optional `FORGE_SMTP_CA_FILE` for tests/internal relays). Credentials are refused with `none`. Failures raise a finite error that the existing `DeliveryCoordinator.dispatch` already converts to `FAILED` without diagnostics. Dev adds `aiosmtpd==1.4.6` (+ pinned `atpublic`, `attrs`) to `[project.optional-dependencies].test`; fallback: asyncio stdlib fake.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/forge/smtp_delivery.py` | New | Adapter + settings |
| `src/forge/invitation_delivery.py` | Modified | builder, receipt, `channel`, link param |
| `src/forge/account_api.py` | Modified | channel from coordinator (lines ~589, ~608) |
| `src/forge/serve_prod.py`, `composition.py` | Modified | choose adapter |
| `deploy/compose.yml`, `compose.dev.yml`, `.env.example`, `docs/deploy.md` | Modified | SMTP env, Mailpit |
| `pyproject.toml` | Modified | pinned test deps |
| `tests/` | New | unit + fake SMTP + PG |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Dispatch is synchronous in the request; slow relay blocks it | Med | 10 s connect/op timeout; FAILED state; async worker deferred |
| `aiosmtpd` incompatibility on Python 3.12 | Low | Verify at apply; stdlib fake fallback |
| Provider rejects `From` domain unverified | Med | Runbook: verify domain; failure surfaces as FAILED |
| Contract pin | Low | Only `delivery_channel` value changes; field unchanged |

## Rollback Plan

Select `LocalTestMailbox` again via `FORGE_DELIVERY=local` (dev) or revert the slices; no schema change, no data migration.

## Dependencies
- `fv2-prod-runtime` (serve_prod wiring) and `fv2-deploy-compose` (compose proof) merged first; adapter itself is independent.

## Success Criteria
- [ ] Fake SMTP server receives invitation + reset over STARTTLS and TLS with AUTH.
- [ ] Failure paths yield `FAILED` with no password/recipient in logs or exceptions.
- [ ] Compose proof: invite via API → message visible in Mailpit with working link.
- [ ] All existing tests green; `LocalTestMailbox` unchanged for dev.
