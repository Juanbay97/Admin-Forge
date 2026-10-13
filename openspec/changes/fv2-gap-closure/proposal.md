# Proposal: fv2-gap-closure

## Intent

The web stack (shell, platform console, company portal) shipped against a control plane that is missing a handful of
small server pieces. Each was recorded as an explicit gap in `docs/portal.md` (PC-3, PC-5, PC-9), `docs/platform-console.md`
(PC10 and the overview series) and the sandbox-runner design. This change closes them on the integrated line
(governance + broker + web stack) so the UI shows real data instead of "not available yet".

## Scope

| # | Gap | Closure |
|---|-----|---------|
| G1 | No member own usage | `GET /forge/v1/orgs/{id}/usage/me?from&to` (hidden), database function scoped to the caller's own membership; "My usage" goes live |
| G2 | No platform company members read | `GET /forge/v1/platform/companies/{id}/members` (hidden); console Members tab (task 7.2) |
| G3 | No platform overview / per-day series | `GET /forge/v1/platform/overview?from&to` and `GET /forge/v1/platform/usage/days?from&to` (hidden); console charts |
| G4 | No department assignment | `PUT /forge/v1/orgs/{id}/members/{member}/department` (hidden), administrators only; company Members UI |
| G5 | Admin invitations carry no company code | the mailed link carries `?c=<code>` for every issuer; `account_email` and a branded preview through a separate hidden identity route (the pinned accept response is untouched); the join page shows one generic message for any unusable invitation |
| G6 | Edge does not forward invitation links | `deploy/Caddyfile` forwards `/onboarding`, `/join`, `/reset-password`, `/downloads/*`; static policy tests |
| G7 | No client attestation ingest | `POST /forge/v1/client/attestation` (hidden, member session, audited, append-only); the effective policy uses the latest attestation |
| G8 | Signing key rotation is documentation only | retired public keys list via env/secret (`FORGE_POLICY_RETIRED_KEYS_FILE`) + runbook in `docs/deploy.md` |

## Constraints

* The MVP contract pin (`contract/forge-mvp.contract.json` and the client pin file) must not change: every new route is
  `include_in_schema=False`, no pinned response gains a field.
* Public invitation errors stay one uniform 404 (no enumeration of invalid / expired / used); only the wording shown to the person is helpful and generic.
* Every database change is an additive migration with a fingerprint gate (fresh == upgrade) and re-pinned F value.
* Strict TDD; slices of at most 800 changed lines; stacked on the integrated web line.

## Out of scope

Company-level per-day or per-model usage splits, department removal/rename, attestation verification (the report stays advisory), client changes.

## Risks

| Risk | Mitigation |
|------|-----------|
| Invitation identity route leaks the invitee's email | requires the 256-bit capability; uniform 404 for anything else; never lists |
| Stale attestation keeps exec tools on | effective level is the lower of the queried and the latest attested level, and an attestation older than 30 days is ignored |
| Migration churn changes F pins | one gate test per migration, F values reported in the apply-progress |
