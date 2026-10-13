# Connector broker

Remote connectors (the 43 OAuth/MCP connectors of the catalog) are used **through the control plane**: the OAuth tokens and API keys live
sealed on the server and are injected into each upstream MCP request, so no credential ever reaches a member's device. The 3 local
(stdio) connectors keep their credentials in the client vault; the broker refuses them.

## How a call goes

1. The member's device posts a JSON-RPC message to `POST /forge/v1/mcp/{connector}` with the Forge session.
2. The control plane checks, **fresh on every call**: the live session, the active membership and company, and the connector's effective
   state from governance (so a platform force-off or an administrator disabling it stops the next call, with no upstream traffic).
3. Only `initialize`, `ping`, `tools/*`, `resources/*`, `prompts/*` and the client notifications `notifications/initialized` and
   `notifications/cancelled` pass. Server-to-client requests (`sampling`, `elicitation`, `roots`) and JSON-RPC batches are refused.
4. The credential is opened in memory (an OAuth access token is refreshed single-flight when it is about to expire) and injected;
   everything the client sent as `Authorization` or `Cookie` is dropped.
5. The **egress guard** connects: `https` on 443 only, to a host in the connector's allow-list, resolved once, refusing loopback,
   link-local/metadata, RFC 1918, CGNAT, ULA and every other non-public address, pinned to the address it checked; redirects are never followed.
6. The answer is relayed with a header allow-list (`Content-Type`, `Mcp-Session-Id`, `MCP-Protocol-Version`; no `Set-Cookie`, no auth
   headers), a size cap (request 1 MiB, response 8 MiB), a 30 s deadline and a per-member rate of 60/min. Any occurrence of the injected
   credential in the body (also JSON-escaped, also across stream chunks) is replaced with `[redacted]`, so a connector that echoes request
   headers cannot hand the credential back.
7. One metadata row is logged (`tool_invocation_log`, source `broker`): connector, method, tool name, status, latency, byte counts. Never a body or a header.

## Setting a connector up

| Step | Who | How |
|---|---|---|
| Register the connector | platform owner | the catalog seed already holds the 46 OpenYak connectors; the OAuth endpoints are NOT in it: `PUT /forge/v1/platform/capabilities/connector:<id>` with `attributes.oauth = {authorize_url, token_url, scopes, revocation_url?, token_auth?}` and `attributes.egress_hosts` |
| Register the OAuth app | platform owner (default for every company) or company administrator (own app) | `PUT /forge/v1/platform/connectors/{id}/credential` or `PUT /forge/v1/connectors/{id}/credential` with `{expected_revision, kind, client_id, client_secret}` (or `kind: api_key` with `api_key`); **write-only**: reads return status, the last four characters and the revision |
| Connect | member | `POST /forge/v1/connectors/{id}/oauth/start` returns the authorize URL; the provider redirects to the callback on the public origin |
| Disconnect | member | `DELETE /forge/v1/connectors/{id}/grant` destroys the grant and revokes at the provider when `revocation_url` is set |

Real provider registrations, DNS and TLS are yours to verify: nothing in this repository talks to a real provider.

### Public origin and the callback

The redirect URI is always `<public origin>/forge/v1/connectors/oauth/callback`, taken from configuration (`FORGE_PUBLIC_ORIGIN` in
production), never from a request. Register exactly that URI with each provider. The callback is public by design: the single-use,
10-minute, hashed state is the capability, and every bad, replayed or expired state gets the same page.

## Keys and backup

`scripts/deploy-secrets.(sh|ps1)` creates `connector_key` (a Fernet key of its own: it must differ from the delivery, gateway, platform and
policy keys, and the process refuses to start otherwise). It is read from `FORGE_CONNECTOR_KEY_FILE`. **Back it up offline.** Losing it
makes every sealed token and credential unreadable: members reconnect and company administrators re-enter their credentials; nothing else
is lost. Without the key every connector route answers `503`. (`ConnectorCipher` supports a rotation list; the deployment
configuration takes a single key for now.)

Every sealed value is bound to its company, scope, member, connector and revision, so a value copied to another row does not open.

## What stops brokering at once

* a platform force-off or an administrator disabling the connector (resolved per call, never cached);
* disconnect, or a membership leaving `active` (a database trigger deletes that member's grants and pending states in the same transaction);
* a refused refresh (`reauth_required`), an upstream `401/403`, a suspended company.

## Local proof and tests

`src/forge/fake_connectors.py` is a loopback OAuth 2.0 provider (PKCE, rotating refresh tokens, revocation) and a fake MCP server (header
echo, cookies, SSE, slow and redirecting tools). The egress guard reaches them only through explicit fixture hosts a test injects, or the
dev overlay's `FORGE_CONNECTOR_TEST_FIXTURES_FILE`; the production stack never sets it. `scripts/deploy-smoke.ps1` connects a fixture
connector end to end through Caddy.

## Limits worth knowing

* Rate limits and the refresh lock are per process (single worker is a deployment rule).
* No server-initiated MCP requests, no stdio on the server, no bidirectional SSE.
* The 46 catalog connectors ship without OAuth endpoints; which ones are OAuth versus API-key is decided when each is registered.
