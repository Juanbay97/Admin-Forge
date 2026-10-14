# Proposal: fv2-connector-broker

## Intent

OpenYak ships 46 connectors (43 remote, 3 stdio) whose MCP tokens are stored plaintext on the laptop. Forge must keep remote connector OAuth/secrets **server-side** and proxy MCP calls so credentials never reach the client. Per-user tokens for local stdio connectors stay client-side (DPAPI, client track).

Security/tenant/cost impact: new highest-value secret store; own role pair, own cipher key, SSRF-hardened egress, RLS per org/member; no content logged.

## Scope

### In Scope
- `ConnectorCipher` (sealed like gateway keys, bound to org/scope/subject/capability/revision).
- Org-level credentials (API keys, OAuth client apps) and per-user OAuth grants for remote connectors.
- OAuth start/callback/refresh (PKCE, single-use state), public callback origin configurable.
- MCP broker proxy `POST /forge/v1/mcp/{connector}` authorized by effective policy; header scrub; limits.
- Egress guard: per-connector host allow-list, SSRF/DNS-rebind defense.
- Admin/member status APIs, disconnect/revoke, metadata-only call log.
- Fixture OAuth provider + fixture MCP server for local tests.

### Out of Scope
- Client DPAPI vault / stdio connectors / broker client (fv2c-capabilities-client).
- Real provider registrations, TLS/DNS (user verifies).
- Server-initiated MCP requests (sampling/elicitation); stdio on server.

## Capabilities

### New Capabilities
- `connector-secrets`: sealed storage, scopes, write-only admin entry.
- `connector-oauth`: authorization-code+PKCE flow, refresh, revoke.
- `mcp-broker`: authorized JSON-RPC/MCP proxy, credential injection.
- `connector-egress`: allow-list and SSRF guard.

### Modified Capabilities
None (additive; hidden routes, MVP contract pin unchanged).

## Approach

Catalog `connector` entries (from fv2-capability-governance) carry transport, auth type, OAuth endpoints, MCP URL, egress hosts, `credential_locus`. Broker calls resolve effective policy fresh per call (force-off is immediate). Pure domain + ports; PG store behind new `forge_broker_authority/_service`; httpx transport with IP-pinned connect.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `migrations/00NN_connector_*.sql` | New | credentials, grants, oauth_states |
| `src/forge/connector_*.py`, `mcp_broker.py`, `egress_guard.py` | New | domain/store/api |
| `tests/fixtures/fake_oauth_provider.py`, `fake_mcp_server.py` | New | local fixtures |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py` | Modified | 8th pool, fingerprint |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Broker is a token honeypot | Med | Separate role+key, per-call authz, no logs of secrets |
| SSRF via connector URLs/redirects | High | Guard, no redirect follow, IP pinning |
| Refresh races/provider quirks | Med | Per-grant advisory lock, single-flight |
| Cipher key loss | Med | Backup runbook; reconnect flow |
| Provider ToS for central OAuth apps | Med | Org-owned OAuth app override |

## Rollback Plan

Additive migrations; disable via governance force-off or unmounting routes; sealed rows ignorable. Clients fall back to no remote connectors.

## Dependencies

fv2-capability-governance (catalog, resolver); platform-core (platform write pattern); soft: fv2-prod-runtime public origin (injected explicitly). Migrations after governance (indicative 0037–0038).

## Success Criteria

- [ ] E2E vs fixture OAuth+MCP: connect, call, refresh, revoke.
- [ ] Credentials absent from every response/log in leak tests.
- [ ] SSRF/redirect/rebind attempts denied; cross-org denied.
