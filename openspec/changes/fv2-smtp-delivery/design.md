# Design: SMTP Invitation Delivery

## Technical Approach
Keep the existing `DeliveryCoordinator` (encrypted retry payload, lease/finish state machine, finite `FAILED`) untouched; add a second `MessageDelivery` adapter. Extract the MIME construction from `LocalTestMailbox.deliver` into `build_message(sender, recipient, name, link, purpose, message_id)` so both adapters emit identical content and the injection/escaping tests keep applying.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Client | stdlib `smtplib` | `aiosmtplib`, vendor HTTP APIs | Zero new runtime dep; any provider (Resend, SES) via SMTP; dispatch is already sync in a threadpool |
| Security modes | `starttls` default, `tls`, `none` (no creds) | allow opportunistic | Prevent silent downgrade and cleartext passwords |
| TLS trust | `create_default_context()` + optional `CA_FILE` | disable verify for tests | Fake server uses generated cert injected via CA_FILE |
| Port change | `deliver -> object` receipt; `channel` attr | keep `Path` | `Path` leaks the file-adapter shape |
| Channel field | from coordinator | hard-coded string | Contract only pins the field name |
| Test server | `aiosmtpd==1.4.6` pinned in test extras | `smtpd` (removed in 3.12), mocks | Real protocol (STARTTLS/AUTH) proof; stdlib asyncio fake as fallback |
| Compose proof | Mailpit (plain SMTP, `none`) | real relay | No remote calls; link retrievable via Mailpit API |
| Prod fallback | None: SMTP required | fall back to local | Silent file drop = lost invitations |

## Data Flow
    POST /accounts/invitations ─► InvitationService ─► DeliveryCoordinator.queue_invitation
        ─► dispatch(claim lease) ─► SmtpDelivery.deliver ─► relay (STARTTLS/TLS+AUTH)
        └► finish(delivered|failed) ─► 201 {delivery_state, delivery_channel:"smtp"}

## File Changes

| File | Action | Description |
|---|---|---|
| `src/forge/smtp_delivery.py` | Create | `SmtpSettings`, `SmtpDelivery`, `SmtpDeliveryError` |
| `src/forge/invitation_delivery.py` | Modify | `build_message`, port return type, `channel`, link `company_code` |
| `src/forge/account_api.py` | Modify | `delivery.channel` in 2 responses |
| `src/forge/composition.py` / `serve_prod.py` | Modify | adapter selection |
| `pyproject.toml` | Modify | `test` extras pins |
| `deploy/compose.yml`, `compose.dev.yml`, `.env.example`, `docs/deploy.md` | Modify | env, Mailpit, provider notes |
| `tests/smtp_support.py` | Create | aiosmtpd fixture (STARTTLS/TLS/AUTH, in-memory certs via `cryptography`) |
| `tests/test_smtp_delivery.py`, `test_smtp_config.py` | Create | TDD |
| `tests/test_invitation_delivery.py`, `test_account_api.py` | Modify | channel/receipt |

## Interfaces / Contracts
```python
@dataclass(frozen=True)
class SmtpSettings:
    host: str; port: int; security: Literal['starttls','tls','none']
    user: str | None; password: str | None = field(repr=False); sender: str; ca_file: str | None
class SmtpDelivery:
    channel = 'smtp'
    def deliver(self, message_id, recipient, name, link, *, purpose='invitation') -> DeliveryReceipt
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | settings validation, builder equality with local adapter, injection | unittest |
| Integration | STARTTLS+AUTH, implicit TLS, downgrade refusal, bad auth, timeout, no secret in logs | aiosmtpd fixture |
| PG/API | `delivery_channel`, FAILED persisted, contract test | harness + TestClient |
| E2E | compose.dev + Mailpit: provision → login → invite → message + link in Mailpit → down -v | extend `deploy-smoke.ps1` |

## Migration / Rollout
No migration. Real Resend/SES verification only by the user (no remote calls by agents).

## Open Questions
- [ ] Async dispatch worker needed before >~50 invites/min? (deferred)
- [ ] Final sender address/domain (SPF/DKIM done by user).
