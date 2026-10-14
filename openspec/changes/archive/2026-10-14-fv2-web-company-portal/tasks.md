# Tasks: fv2-web-company-portal

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4,600 (≈3,300 source/CP + ≈1,300 tests/fixtures) |
| 400-line budget risk | High (single PR) / Medium per slice at 800 |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR6 (stacked, each ≤ 800) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

> Program estimate L 4k / 5 slices; forecast 4.6k / 6 slices (CP pieces + e2e journey). Prerequisites merged: fv2-web-shell, fv2-usage-metering, fv2-smtp-delivery, fv2-gateway-keys.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | CP hosting pieces: `/downloads`, `/join` redirect, accept `account_email` + pytest | PR 1 (~450) | Python only, independent of SPA; first in stack |
| 2 | Join/onboarding flow (public, branded) | PR 2 (~780) | needs shell + PR1 |
| 3 | Download page + deep link + manifest | PR 3 (~650) | needs PR2 |
| 4 | Portal home + My usage + portal gating | PR 4 (~700) | needs PR3 + usage-metering |
| 5 | Company dashboard (per-person) + departments + read-only gateway | PR 5 (~800) | needs PR4 (shared usage module) |
| 6 | Real-stack journeys, sweeps, responsive/a11y, docs | PR 6 (~650) | needs all |

## Phase 1 — Control-plane hosting (PR 1)
- [x] 1.1 RED pytest: `/downloads` traversal (`..`, encoded, backslash, symlink), headers, 404; `/join` 307 keeps query; accept returns `account_email`
- [x] 1.2 GREEN: `downloads_mount.py`, `admin_mount.py` redirect, `account_api.py` additive field; run contract pin tests (must stay green)
- [x] 1.3 Composition: optional downloads dir in `mvp_local.py`; fixture installer + `latest.json` created by `scripts/admin-e2e.ps1`
- [x] 1.4 Contract reconcile: confirm link format with smtp-delivery, usage shapes with usage-metering, gateway read fields with gateway-keys (update fixtures/PC table) (recorded in docs/portal.md)

## Phase 2 — Join / onboarding (PR 2)
- [x] 2.1 RED unit: `parseFragment`/scrub, error-code→`JoinState`, password hint rules, invitations schema
- [x] 2.2 `usePublicBranding(slug)` (800 ms bound, fallback), `useInvitationFragment`
- [x] 2.3 `Join` page: branded form (rhf+zod), submit once, auto sign-in (email fallback), error states, existing-account state, signed-in visitor notice
- [x] 2.4 UI spec: branded, hash scrubbed + no storage, each error state, policy error, double submit, mobile 375, axe/CSP
- [x] 2.5 Route `/admin/join` public (outside `RequireSession`), shell registration

## Phase 3 — Download page (PR 3)
- [x] 3.1 RED unit: manifest schema (same-origin url, sha256 format), platform picker, size/date formatters
- [x] 3.2 `Download` page (steps, code + copy, installer, sha256, deep link, OS note, SmartScreen note, not-published state)
- [x] 3.3 UI spec (available / 404 / empty / non-Windows / deep link attempt), axe/CSP

## Phase 4 — Portal home & my usage (PR 4)
- [x] 4.1 RED→GREEN unit: usage schemas vs fixtures, delta/share math
- [x] 4.2 Portal manifest (Home, Download, My usage), home welcome + sparkline, role redirect for members, company-area denial for members
- [x] 4.3 `Usage` page (range URL-synced, AreaChart, model share, empty/error); org picker for multi-org members
- [x] 4.4 UI specs: gating redirects, own-data-only, axe/CSP

## Phase 5 — Company dashboard (PR 5)
- [x] 5.1 Dashboard (KPIs, daily chart, model share, `PersonTable` sortable/filterable, top-5 bar); URL-synced range/sort
- [x] 5.2 Members: department filter + Departments tab (create; assign if PC-9 exists)
- [x] 5.3 Gateway read-only status (remove key form; assert no password inputs); keep existing members/gateway/catalog/branding specs green
- [x] 5.4 UI specs: states, multi-org re-key, sorting, axe/CSP/viewports

## Phase 6 — Journeys & closeout (PR 6)
- [x] 6.1 e2e `portal-journey.spec.ts`: admin invites → read link from recorded .eml → branded join → password → download page (company code, installer link) → my usage
- [x] 6.2 e2e `company-dashboard.spec.ts`: admin sees that person's usage after a metered request through the fake gateway
- [x] 6.3 Sweep spec: all company/portal routes × 375/768/1280 × axe + CSP + no horizontal scroll
- [x] 6.4 Docs: portal guide, invitation link contract, installer hosting notes in `docs/` + admin README


## Apply notes (Track B, real-contract reconciliation)

Strict TDD; stacked local branches `feat/fv2-web-portal-s1..s6` (S1 python first, S2 to S6 after the platform console stack). Size `exception`
accepted by the orchestrator for the test-heavy slices.

- Python (S1) is limited to the three agreed items plus what the e2e stack needs: `downloads_mount.py`, the `/join`, `/onboarding` and
  `/reset-password` redirects in `admin_mount.py`, `mvp_local.assemble` mounting `<workspace>/downloads`, and `mvp_up` staging the manifest and a stand-in
  installer and bootstrapping the platform owner (link file). `tests/test_portal_hosting.py`.
- **Not done: `account_email` on accept** (1.2). The accept response is in the pinned contract, so the field would change the pin; the join page asks for
  the email once (the design's own fallback).
- PC-5 `usage/me` does not exist on the server: "My usage" is built to the documented contract and says "not available yet" on 404 (the real e2e asserts it).
- PC-9 department assignment does not exist: departments are listed and created; the member list filters by department.
- Admin-issued invitations carry no `c=<company code>` hint (only the platform owner's first-admin invitation does), so a person invited by an
  administrator sees the join page unbranded until they sign in. Fix on the server: pass `company_code` in the invite route.
- The edge `Caddyfile` does not forward `/onboarding`, `/join` or `/reset-password` to the control plane (only `/admin*`, `/status`, `/livez`, `/forge/*`).
- The old `company-config` gateway-writes specs and the legacy "plain member is denied" / "platform not found" specs were realigned to the shipped behaviour
  (read-only gateway, member lands in the portal, platform area denied).