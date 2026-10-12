# Design: fv2-platform-core

## Technical Approach

Clone the existing authority pattern: NOLOGIN `forge_platform_authority` owns SECURITY DEFINER functions; LOGIN `forge_platform_service` only has EXECUTE (compare `0015_gateway_configuration.sql`, `0025_org_branding.sql`, pools in `mvp_local.py:125-172`). Platform = account + `platform_roles`; tenant tables reached only inside functions via `set_config('forge.organization', org, true)`, exactly as `gateway_resolve_admin`. Spec: platform-admin, company-lifecycle, platform-audit.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Platform scope | separate roles + DEFINER fns | hidden "platform org" membership; BYPASSRLS role | keeps RLS default-deny; no leak into org policies |
| Session | reuse `account_sessions` (password step) + new `platform_mfa_sessions(capability_hash FK, verified_at, ttl)` | new session table; widen account_sessions | zero change to account policies/pin; MFA is additive |
| First-admin invite | `account_invitations`: relax `administrator_*` to NULL, add `issuer_platform_id`, `initial_role`; CHECK(exactly one issuer kind; org_admin role only platform-issued) | new invitation table | reuses accept/outbox/delivery, hash capability, email fragment link |
| Accept path | `accept_account_invitation` branches: platform-issued skips `enrollment_lock_admin`, verifies issuer still `platform_owner` + org active; role from invitation; enrollment policy for `membership_roles` allows `organization_admin` only when `forge.enrollment_role` set by this branch | second accept function | member path stays byte-identical |
| TOTP | stdlib `hmac` RFC 6238, ±1 step, `last_step` replay guard, secret sealed with Fernet (GatewayCipher style, separate `platform_key`), 10 recovery codes (scrypt-free sha256 of 80-bit codes) | external lib | no new dependency |
| Bootstrap | CLI inserts identity+account (unusable random hash) + reset-capability row; link written to private file | HTTP bootstrap, password in CLI output | never password, never HTTP |
| Suspend | `organizations.active=false` + `suspended_at`; `enrollment_lock_admin` and member helpers already return NULL when inactive; add test matrix; sessions untouched | revoke sessions | immediate and reversible |

## Data Flow

    CLI bootstrap ──► owned_account + reset link ──► owner sets password (existing reset route)
    owner login ──► account session ──► TOTP verify ──► platform_mfa_sessions
    HTTP /platform/* ──► PlatformService ──► platform_service pool
        └► platform_<op>(digest, …): validate session ► lock owner ► require MFA
            ► set org ctx ► mutate ► INSERT platform_audit_log (same tx)
    create_company ──► org + dept + invitation(initial_role=org_admin) ──► outbox ──► accept (member path unchanged)

## File Changes

| File | Action | Description |
|---|---|---|
| `migrations/0027_platform_scope.sql` | Create | roles, `platform_roles`, `platform_audit_log`, lock/validate fns |
| `migrations/0028_platform_mfa.sql` | Create | `platform_totp`, recovery codes, `platform_mfa_sessions` |
| `migrations/0029_company_lifecycle.sql` | Create | invitation relax, create/suspend/reactivate fns, accept branch |
| `migrations/0030_platform_branding.sql` | Create | `platform_branding_save` wrapper |
| `src/forge/platform.py`, `platform_store.py`, `platform_api.py`, `platform_totp.py`, `platform_cli.py` | Create | domain, store, routes, TOTP, CLI |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py`, `mvp_up.py` | Modify | `ROLES`, secrets (`platform_key`), F27–F30, MVP_ADDITIONS |
| `tests/test_platform_*.py`, `tests/test_postgres_platform_*.py`, `tests/mvp_support.py` | Create/Modify | TDD per module |

## Interfaces / Contracts

`POST /forge/v1/platform/login/mfa {code}`, `GET /platform/me`, `GET|POST /platform/companies`, `POST /platform/companies/{id}/suspend|reactivate`, `PUT /platform/companies/{id}/branding`, `GET /platform/audit`. Errors finite codes: `PLATFORM_DENIED`, `MFA_REQUIRED`, `COMPANY_CONFLICT`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | TOTP vectors (RFC 6238), CLI, service error mapping | unittest, fakes |
| Integration | RLS denial matrix, cross-org, fresh==upgrade F27..F30 | PG harness one module at a time |
| Smoke | owner→company→invite→accept→admin login | extend mvp-smoke |

## Migration / Rollout

Additive; pin ripples per migration; previous-profile readiness test updated each slice (W2b lesson). Numbers provisional.

## Open Questions

- [ ] Does fv2-prod-runtime's migration runner change how `MVP_ADDITIONS`/pins are declared?
- [ ] Platform session TTL (proposal: 12h absolute, 30min MFA freshness for destructive ops)?
