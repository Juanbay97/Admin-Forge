# Connector OAuth Specification

## Purpose
Per-user authorization of remote connectors, tokens held server-side.

## Requirements

### Requirement: Start and callback
Start (member session, connector enabled by effective policy) MUST create a single-use state (≤10 min, PKCE S256) and return the authorize URL. The callback MUST live on the configured public origin, accept only a valid unconsumed state, exchange the code server-side and store sealed tokens. The redirect URI MUST be derived from configuration only.

#### Scenario: Happy path (fixture)
- GIVEN fixture OAuth provider
- WHEN start, consent, callback occur
- THEN grant is `connected` and status shows no token

#### Scenario: Replay
- GIVEN a consumed state
- WHEN callback repeats
- THEN rejected, no token change

#### Scenario: Disabled connector
- GIVEN connector forced off
- WHEN start is called
- THEN denied

### Requirement: Refresh and revoke
Expired access tokens MUST be refreshed single-flight per grant; refresh failure MUST mark `reauth_required`. Disconnect, member removal or connector force-off MUST stop brokering immediately.

#### Scenario: Concurrent refresh
- GIVEN expired token and 5 parallel calls
- WHEN brokered
- THEN one refresh request reaches the provider

#### Scenario: Member removed
- GIVEN removed membership
- WHEN calling the broker
- THEN denied
