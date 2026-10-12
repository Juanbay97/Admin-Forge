# MCP Broker Specification

## Purpose
Proxy MCP calls so credentials never reach the laptop.

## Requirements

### Requirement: Authorization per call
Each call MUST require a valid member session, active membership, connector effective-state `on`, and a grant or org credential. Otherwise it MUST be denied before any upstream request.

#### Scenario: Forced off
- GIVEN super admin force-off
- WHEN a call arrives
- THEN denied, no upstream traffic

### Requirement: Credential injection and scrub
The broker MUST inject upstream auth server-side, MUST strip client `Authorization`/cookies, and MUST drop upstream `Set-Cookie`/auth headers. Only allow-listed JSON-RPC methods (initialize, ping, tools/*, resources/*, prompts/*) MUST pass.

#### Scenario: No leak
- GIVEN fixture MCP echoes request headers
- WHEN `tools/call` is brokered
- THEN client receives no upstream credential

#### Scenario: Blocked method
- GIVEN `sampling/createMessage`
- WHEN sent
- THEN rejected

### Requirement: Limits and metadata
Request/response size, duration and per-member rate MUST be capped. A metadata row (connector, method, tool name, status, latency, bytes) MUST be logged; bodies MUST NOT.

#### Scenario: Oversize
- GIVEN body above cap
- WHEN sent
- THEN 413, no upstream call
