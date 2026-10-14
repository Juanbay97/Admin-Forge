# Connector Secrets Client Specification

## Purpose
Per-user connector credentials never sit in plaintext; remote connectors go through the control-plane broker.

## Requirements

### Requirement: DPAPI vault for stdio connector tokens

Tokens for stdio connectors MUST be stored encrypted with Windows DPAPI (current-user scope) with entropy bound to the profile id, in the profile directory; the plaintext `McpTokenStore` JSON MUST NOT be written.

#### Scenario: Store and read
- GIVEN a token for server `s`
- WHEN stored then read in the same Windows user and profile
- THEN the same value is returned and the file contains no plaintext

#### Scenario: Other profile
- GIVEN the vault file of profile A opened under profile B entropy
- WHEN read
- THEN decryption fails closed

#### Scenario: Migration
- GIVEN an existing plaintext token file
- WHEN the client starts
- THEN tokens are migrated to the vault, verified, and the plaintext file is securely deleted

#### Scenario: Non-Windows
- GIVEN a platform without DPAPI
- WHEN the vault is requested
- THEN storing connector tokens is refused (no plaintext fallback)

### Requirement: Remote MCP via broker

Connectors with `transport=remote` MUST be invoked through the CP broker using the member session; the client MUST NOT hold third-party remote tokens nor connect directly to remote MCP hosts.

#### Scenario: Remote call
- GIVEN an enabled remote connector
- WHEN a tool call is made
- THEN the request goes to the broker endpoint and the response is returned; no direct egress occurs

#### Scenario: Broker unavailable
- GIVEN the broker is unreachable
- WHEN invoked
- THEN a clear error is returned; no fallback to direct connection

### Requirement: stdio connectors under the runner

stdio connector processes MUST be launched through the `ToolRunner` (scrubbed env, jail, limits) with only their own token injected.

#### Scenario: Token injection
- GIVEN connector `s` with a vault token
- WHEN launched
- THEN only `s`'s token is in its env; no other secrets
