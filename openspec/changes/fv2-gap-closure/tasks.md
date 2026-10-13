# Tasks: fv2-gap-closure

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~5,500 (migrations, services, routes, UI wiring, tests, docs) |
| 400-line budget risk | High (single PR) / Medium per slice at 800 |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |
| Base | integrated line: governance + broker tip rebased under the web stack |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Strict TDD is active: each slice writes the failing test first (RED observed), then the code (GREEN). Migrations carry a
fingerprint gate (fresh apply equals upgrade, F pin printed then pinned).

## G1 Member own usage (migration 0042)
- [ ] 1.1 RED/GREEN: `usage_member_me` database function + PG gate + readiness F pin
- [ ] 1.2 RED/GREEN: service, route `GET /orgs/{id}/usage/me` (hidden), contract pin unchanged
- [ ] 1.3 RED/GREEN: portal "My usage" live (fixtures, unit, UI), docs PC-5 closed

## G2 Platform company members (migration 0043)
- [ ] 2.1 RED/GREEN: `platform_company_members` function + route + pin
- [ ] 2.2 RED/GREEN: console Members tab (task 7.2) + docs

## G3 Platform overview and series (migration 0044)
- [ ] 3.1 RED/GREEN: `platform_overview` (companies, active users, tokens, cost, previous) and `platform_usage_days` + routes
- [ ] 3.2 RED/GREEN: console overview charts on real data

## G4 Department assignment (migration 0045)
- [ ] 4.1 RED/GREEN: `directory_member_department` function + route
- [ ] 4.2 RED/GREEN: company Members UI assignment

## G5 Invitations (migration 0046)
- [ ] 5.1 RED/GREEN: admin invitations mail `?c=<code>`
- [ ] 5.2 RED/GREEN: `invitation_identity` function + hidden route; join page uses it; one generic unusable-link message

## G6 Edge forwards
- [ ] 6.1 RED/GREEN: Caddyfile forwards + static policy tests

## G7 Client attestation (migration 0047)
- [ ] 7.1 RED/GREEN: table + ingest function + route `POST /client/attestation`, audited
- [ ] 7.2 RED/GREEN: effective policy uses the latest attestation

## G8 Signing key rotation
- [ ] 8.1 RED/GREEN: retired public keys through `FORGE_POLICY_RETIRED_KEYS_FILE` (prod_config, mvp_local) + runbook

## G9 Verification
- [ ] 9.1 admin unit/ui, admin-e2e full, mvp-smoke, deploy-smoke, branding-smoke; apply-progress
