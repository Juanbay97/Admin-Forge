# Proposal: fv2-platform-core (super admin / platform scope)

## Intent

Forge has no platform scope: companies exist only via a trusted CLI, the first admin of a company cannot be invited (`account_invitations.administrator_membership_id NOT NULL`, 0013), there is no suspend operation, no MFA. The platform owner (the user) must create and operate companies from a console API. Security: platform authority MUST NOT weaken tenant isolation; cost: none directly (enables keys/metering).

## Scope

### In Scope
- Platform owner = `owned_accounts` identity with NO membership; `forge.platform_roles`, NOLOGIN `forge_platform_authority`, LOGIN `forge_platform_service` (6th pool). Never BYPASSRLS.
- All platform ops = SECURITY DEFINER functions starting `platform_lock_owner(digest)` then `set_config('forge.organization', …)`.
- Operator CLI `python -m forge.platform bootstrap-owner` issuing a one-time set-password link (no password, never HTTP).
- TOTP MFA (sealed secret, recovery-code hashes), mandatory for `platform_owner`.
- Create company (org + slug/company code + default department + first-admin invitation; schema fix for platform-issued invitations with `initial_role`), suspend/reactivate, edit any company branding, list/get companies.
- Append-only `platform_audit_log`; audit read.
- Platform routes `include_in_schema=False` (`/forge/v1/platform/*`); contract pin unchanged.

### Out of Scope
- Gateway keys/assignment (fv2-gateway-keys), metering (fv2-usage-metering), SPA console (fv2-web-platform-console), SMTP (fv2-smtp-delivery), capabilities.
- Existing-account-into-second-org invites; platform_viewer UI.

## Capabilities

### New Capabilities
- `platform-admin`: owner identity, authority roles/pool, bootstrap CLI, MFA session, `/platform/me`.
- `company-lifecycle`: create company + first-admin invite, suspend/reactivate, platform branding edit.
- `platform-audit`: append-only audit of platform actions.

### Modified Capabilities
- None at spec level (no `openspec/specs/` baseline exists); invitation behavior change is specified inside `company-lifecycle`.

## Approach

Clone the proven authority pattern (0015 `gateway_lock_admin`, 0025 branding authority). Additive migrations 0027–0030 (provisional; renumber after fv2-prod-runtime/deploy/smtp land). Each migration ripples pin F27–F30 (`mvp_profile`, `mvp_readiness`, `mvp_up`, `mvp_local`, `tests/mvp_support`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/0027..0030` | New | platform scope, MFA, company lifecycle, branding fn |
| `src/forge/platform*.py` | New | domain, store, api, cli, totp |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py`, `mvp_up.py` | Modified | 6th pool, F27–F30 |
| `src/forge/invitation_store.py`, `account_store.py` | Modified | platform-issued invitation accept |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Platform authority leaks cross-tenant | Med | per-fn org ctx, RLS denial matrix tests, no table grants |
| Invitation schema change regresses accept | Med | keep member path byte-identical; PG upgrade tests |
| Pin ripple / pre-migration role test (v1-white-label W2b regression) | High | update `LOGIN_ROLES` previous-profile test per migration |
| TOTP replay/lockout | Med | last-step guard, recovery codes, CLI reset |

## Rollback Plan

Each migration is a slice; revert slice commits; DB: drop new objects (migrations are additive, no data rewrite except invitation column relax — nullable only).

## Dependencies

- fv2-prod-runtime, fv2-deploy-compose, fv2-smtp-delivery land first (same stack); take migration numbers after theirs.

## Success Criteria

- [ ] Owner bootstraps via CLI, sets password, enrolls TOTP, creates a company; first admin accepts invite and logs into company admin.
- [ ] Platform pool cannot read org tables directly; cross-org denial tests pass; fresh == upgrade fingerprints.
- [ ] Contract pin test unchanged; all platform actions audited.
