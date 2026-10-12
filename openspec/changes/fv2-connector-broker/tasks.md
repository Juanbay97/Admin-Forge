# Tasks: fv2-connector-broker

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4.3k (6 slices, 500–800 each) |
| 400-line budget risk | High (800-line slice budget respected) |
| Chained PRs recommended | Yes |
| Suggested split | B1 → B2 → B3 → B4 → B5 → B6 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| B1 | Cipher + egress guard (pure) | PR 1 (~650) | needs only governance S1 types |
| B2 | Schema, roles, store, ripple | PR 2 (~780) | after governance S5 migrations |
| B3 | OAuth flow + fixture provider | PR 3 (~800) | |
| B4 | MCP proxy + fixture MCP server | PR 4 (~800) | |
| B5 | Admin/member APIs, revoke hooks, audit | PR 5 (~700) | |
| B6 | Leak/hardening suite, readiness, runbook | PR 6 (~500) | |

## B1 Pure core
- [ ] 1.1 RED `tests/test_connector_cipher.py` (binding drift, missing key, rotation); GREEN `connector_cipher.py`
- [ ] 1.2 RED `tests/test_egress_guard.py` (private IP, redirect, rebind, allow-list); GREEN `egress_guard.py`

## B2 Schema/store
- [ ] 2.1 Migration credentials/grants/oauth_states, broker role pair, RLS + DEFINER fns
- [ ] 2.2 `connector_store.py` port + PG adapter; ripple ROLES, F fingerprint, readiness
- [ ] 2.3 PG tests: cross-org, revision `CONFLICT`, advisory lock

## B3 OAuth
- [ ] 3.1 `tests/fixtures/fake_oauth_provider.py` (loopback authorize/token/refresh)
- [ ] 3.2 RED→GREEN `connector_oauth.py` state/PKCE/callback/exchange/refresh single-flight
- [ ] 3.3 Replay, expired state, disabled-connector, concurrent-refresh tests

## B4 MCP proxy
- [ ] 4.1 `tests/fixtures/fake_mcp_server.py` (initialize, tools/list, tools/call, header echo)
- [ ] 4.2 RED→GREEN `mcp_broker.py`: authz per call, inject/scrub, method filter, caps, SSE pass-through
- [ ] 4.3 Metadata log via governance ingest fn (source=broker)

## B5 APIs
- [ ] 5.1 `connector_api.py` hidden routes (start, callback, status, disconnect, credential PUT)
- [ ] 5.2 Revoke on member removal (hook into lifecycle) + governance audit rows
- [ ] 5.3 Hidden-OpenAPI + MVP pin unchanged test

## B6 Hardening
- [ ] 6.1 Leak scan: responses/logs/errors contain no secret (E2E)
- [ ] 6.2 Readiness probe + `docs/connector-broker.md` (key backup, public origin)
