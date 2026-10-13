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
- [x] 1.1 RED/GREEN: `usage_member_me` database function + PG gate + readiness F pin
- [x] 1.2 RED/GREEN: service, route `GET /orgs/{id}/usage/me` (hidden), contract pin unchanged
- [x] 1.3 RED/GREEN: portal "My usage" live (fixtures, unit, UI), docs PC-5 closed

## G2 Platform company members (migration 0043)
- [x] 2.1 RED/GREEN: `platform_company_members` function + route + pin
- [x] 2.2 RED/GREEN: console Members tab (task 7.2) + docs

## G3 Platform overview and series (migration 0044)
- [x] 3.1 RED/GREEN: `platform_overview` (companies, active users, tokens, cost, previous) and `platform_usage_days` + routes
- [x] 3.2 RED/GREEN: console overview charts on real data

## G4 Department assignment (migration 0045)
- [x] 4.1 RED/GREEN: `directory_member_department` function + route
- [x] 4.2 RED/GREEN: company Members UI assignment

## G5 Invitations (migration 0046)
- [x] 5.1 RED/GREEN: admin invitations mail `?c=<code>`
- [x] 5.2 RED/GREEN: `invitation_identity` function + hidden route; join page uses it; one generic unusable-link message

## G6 Edge forwards
- [x] 6.1 RED/GREEN: Caddyfile forwards + static policy tests

## G7 Client attestation (migration 0047)
- [x] 7.1 RED/GREEN: table + ingest function + route `POST /client/attestation`, audited
- [x] 7.2 RED/GREEN: effective policy uses the latest attestation

## G8 Signing key rotation
- [x] 8.1 RED/GREEN: retired public keys through `FORGE_POLICY_RETIRED_KEYS_FILE` (prod_config, mvp_local) + runbook

## G9 Verification
- [x] 9.1 admin unit/ui, admin-e2e full, mvp-smoke, deploy-smoke, branding-smoke; apply-progress

## H1 Real OmniRoute usage compatibility
- [x] H1.1 RED/GREEN: the streaming adapter tolerates the OpenAI usage and chunk extras (details, cost, `usage: null`, obfuscation, refusal/logprobs null) with exact counters, bounded details, seeded fuzz and golden SSE fixtures
- [x] H1.2 RED/GREEN: fake gateway `openai_realistic` mode (`--openai-realistic`), used by the dev overlay of the deploy smoke

## H2 Effective policy on an empty catalog
- [x] H2.1 RED/GREEN: an empty catalog is a signed empty policy (epochs 1), never a 503; PG proof
- [x] H2.2 RED/GREEN: `forge.migrate` seeds the catalog idempotently (`--no-seed`, `SEED_FAILED`, `FORGE_MIGRATE_SEED=0` for a restore), the local stack seeds it too; smoke adjusted (restore round trip)

## H3 Policy key distribution
- [x] H3.1 RED/GREEN: rotation statements (`forge.policy-key-rotation.v1`, signed by the OLD key), `GET /forge/v1/capabilities/pinning`, `FORGE_POLICY_ROTATIONS[_FILE]`, signing CLI, contract vectors, runbook
- [x] H3.2 RED/GREEN: `GET /forge/v1/capabilities/installer-config` (`forge.installer-config.v1`) and the portal "Download configuration"; smoke proof

## H4 Smoke stability
- [x] H4.1 RED/GREEN: e2e API sessions reused per account and released after each journey (production limits untouched)
- [ ] H4.2 BLOCKED (not ours): `forge-multiuser-flow` fails identically at the baseline 10b5509 (org-B chat gets no reply, composer says "Models unavailable"); client side to diagnose