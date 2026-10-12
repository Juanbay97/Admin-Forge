# Tasks: SMTP Invitation Delivery

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,500 (3 slices, 350–700 each) |
| 400-line budget risk | High (800-line/slice budget: Low–Medium) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | SmtpSettings + SmtpDelivery + fake SMTP fixture (~700) | PR 1 | base: fv2-deploy-compose tip (adapter is code-independent) |
| S2 | Port widening, channel reporting, link param, serve_prod wiring (~450) | PR 2 | base PR1 |
| S3 | Compose Mailpit + env + docs + Docker proof (~350) | PR 3 | base PR2 |

## Phase 1: Adapter (S1)
- [ ] 1.1 Pin `aiosmtpd==1.4.6` (+`atpublic`,`attrs`) in `pyproject.toml` test extras; `pip check`; fallback stdlib fake if unusable.
- [ ] 1.2 RED `tests/test_smtp_config.py`: presets, `none`+password refused, bad port/from, `_FILE` read.
- [ ] 1.3 RED `tests/smtp_support.py` + `test_smtp_delivery.py`: STARTTLS+AUTH, TLS, downgrade refused, bad AUTH, rejected rcpt, stall→timeout, no password in logs/exception.
- [ ] 1.4 GREEN extract `build_message` in `invitation_delivery.py`; `src/forge/smtp_delivery.py`.

## Phase 2: Port + API (S2)
- [ ] 2.1 RED: receipt/`channel` tests in `test_invitation_delivery.py`; `delivery_channel` in `test_account_api.py`; `company_code` link cases.
- [ ] 2.2 GREEN widen `MessageDelivery`, coordinator `channel`, `onboarding_link(company_code=None)`, `account_api.py` lines ~589/~608.
- [ ] 2.3 Contract test stays green (`test_contract.py`).
- [ ] 2.4 RED/GREEN `serve_prod` selects SMTP; no SMTP → `CONFIG_INVALID:FORGE_SMTP_HOST`.

## Phase 3: Deploy proof (S3)
- [ ] 3.1 `deploy/compose.yml` SMTP env/secrets; `compose.dev.yml` Mailpit (digest-pinned) with `FORGE_SMTP_SECURITY=none`.
- [ ] 3.2 Extend `scripts/deploy-smoke.ps1`: provision → login → POST invitation → Mailpit API shows message with link → `down -v`.
- [ ] 3.3 `docs/deploy.md`: Resend (465/587, user `resend`), SES (587), domain verification, failure triage.
- [ ] 3.4 Full unittest + PG suites + smoke recorded in PR.
