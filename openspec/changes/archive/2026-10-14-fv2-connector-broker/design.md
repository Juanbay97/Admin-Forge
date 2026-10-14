# Design: fv2-connector-broker

## Technical Approach

Pure domain (cipher, egress guard, OAuth state/PKCE, JSON-RPC filter) behind typed ports; PG store via NOLOGIN `forge_broker_authority` owning SECURITY DEFINER functions, LOGIN `forge_broker_service` EXECUTE-only (pattern of `0015`). Mirrors `GatewayCipher` (`gateway_configuration.py`). Governance supplies catalog + `resolve()`.

## Architecture Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Cipher | `ConnectorCipher` Fernet/MultiFernet, own key; payload binds `{v,org,scope,subject,capability,binding,revision}` | Reuse gateway key | Blast-radius separation; rotation via MultiFernet |
| DB isolation | Dedicated role pair (8th pool) | Share capability role | Secrets never reachable by policy code paths |
| Credential scopes | `org` (API keys, OAuth client apps; platform-registered default + org override) and `user` (token bundle) | user-only | Matches 43 remote connectors' mix |
| Policy check | Fresh `resolve()` per call (no cache) | 15s cache | Force-off immediate; cost acceptable |
| Transport | httpx with custom connect to pinned IP, redirects off, TLS verify on | follow redirects / proxy | SSRF/rebind control |
| MCP shape | Request/response + SSE pass-through for client-initiated calls; server→client requests blocked | full bidirectional | Bounded v1; sampling is risk |
| OAuth callback | Public route on injected `public_origin`; state hash stored, PKCE verifier sealed | client-side callback | Tokens never touch laptop |
| Refresh | Per-grant `pg_advisory_xact_lock` single-flight | optimistic retry | Provider rotates refresh tokens |
| Stdio | Catalog `credential_locus=client`; broker refuses | server stdio | Out of scope; client DPAPI |
| Logs | Reuse governance `tool_invocation_log` (source=broker) | new table | Single audit surface, metadata only |

## Data Flow

    client ──start──▶ API ─▶ state+PKCE ─▶ authorize_url ──▶ browser ──▶ provider
    provider ──code,state──▶ /oauth/callback (public origin) ─▶ token exchange (egress guard)
              ─▶ seal ─▶ connector_user_grants
    client ──MCP call + session──▶ broker ─▶ resolve(policy) ─▶ open secret (memory only)
              ─▶ egress guard ─▶ upstream MCP ─▶ scrub ─▶ client  (+metadata log)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `migrations/00NN_connector_secrets.sql` | Create | credentials, grants, oauth_states, roles, fns |
| `src/forge/connector_cipher.py`, `egress_guard.py` | Create | sealing, SSRF guard |
| `src/forge/connector_oauth.py`, `connector_store.py` | Create | flow, PG port/adapter |
| `src/forge/mcp_broker.py`, `connector_api.py` | Create | proxy, hidden routes |
| `tests/fixtures/fake_oauth_provider.py`, `fake_mcp_server.py` | Create | loopback fixtures |
| `src/forge/mvp_local.py`, `mvp_profile.py`, `mvp_readiness.py` | Modify | pool, fingerprint |
| `docs/connector-broker.md` | Create | key backup, public origin, runbook |

## Interfaces / Contracts

Hidden routes: `POST /forge/v1/connectors/{id}/oauth/start`, `GET /forge/v1/connectors/oauth/callback`, `GET /forge/v1/connectors` (status), `DELETE /forge/v1/connectors/{id}/grant`, `PUT /forge/v1/connectors/{id}/credential` (admin, write-only), `POST /forge/v1/mcp/{id}`. Statuses: `not_connected|connected|reauth_required|disabled`. Contract pin impact: none (`include_in_schema=False`).

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | cipher binding, guard (IP/redirect/rebind), PKCE/state, method filter | unittest, TDD |
| Integration | RLS, revision conflict, single-flight refresh | PG harness |
| E2E | start→callback→call→refresh→revoke vs fixtures; leak scan of responses/logs | httpx + loopback fixtures |

## Migration / Rollout

Additive; numbering after governance (indicative 0037–0038; renumber at rebase). `public_origin` injected at composition (prod: `FORGE_PUBLIC_ORIGIN` via fv2-prod-runtime). Cipher key in secret file; backup runbook (loss ⇒ users reconnect, org creds re-entered).

## Open Questions

- [ ] Platform-registered vs org-owned OAuth apps default (assumed platform default, org override).
- [ ] Which of the 46 connectors are remote-OAuth vs API-key (seed attributes from governance S6).
- [ ] Rate-limit store: process-local acceptable (single worker).

## Decisions at apply (2026-10-12)

| Topic | Decision | Why |
|---|---|---|
| Migration | one migration `0041_connector_secrets.sql` (F41), after governance `0038-0040` | the chain ended at `0037`; all broker storage is one reviewable unit |
| Refresh single-flight | the broker's own in-process lock per grant plus a compare-and-swap on the grant revision (`BROKER_CONFLICT`), not `pg_advisory_xact_lock` | an advisory transaction lock cannot span the provider round trip under the 5 s statement timeout; a second refresher that read the old revision loses and re-reads the winner's token. Single worker is already a deployment rule |
| Platform default OAuth app | credential rows with a NULL organization, written by the platform owner (`PUT /forge/v1/platform/connectors/{id}/credential`); a company credential overrides it | resolves the open question (platform default, org override) |
| OAuth callback | two functions without a session, `broker_oauth_take` (consumes the state, returns the sealed PKCE verifier) then `broker_oauth_complete` (stores the grant only for a taken, uncompleted state); the unguessable hashed state is the capability | replay and expiry are the same refusal; a failed exchange burns the state |
| Revoke hook | an `AFTER UPDATE OF status ON memberships` trigger deletes the member's grants and pending states; disconnect deletes the grant and revokes at the provider when the connector declares a revocation endpoint | removal is immediate and independent of any application path |
| Audit | the governance `capability_change_audit` action list is widened (`connector.credential_set/cleared`, `connector.connected/disconnected`); calls are metadata rows in `tool_invocation_log` with `source='broker'` (`method`, `tool_name`, status, bytes) | one audit surface; no secret or body is ever written |
| Fixtures | `src/forge/fake_connectors.py` (a loopback OAuth provider and MCP server, stdlib only) with thin `tests/fixtures/` entry points; the egress guard reaches them only through explicit `Fixture` hosts a test or the dev overlay injects (`FORGE_CONNECTOR_TEST_FIXTURES_FILE`, never set in production) | they must run inside the smoke's compose network as well as in unit tests |
| MCP methods | `initialize`, `ping`, `tools/*`, `resources/*`, `prompts/*` plus the client notifications `notifications/initialized` and `notifications/cancelled`; JSON-RPC batches are refused | the protocol handshake needs the initialized notification; batches are not needed in v1 |
| Echoed credentials | the response body is scrubbed of the injected credential (raw and JSON-escaped) across chunk boundaries, besides dropping `Set-Cookie`/auth headers | a connector that echoes request headers must not hand the credential to the member |
