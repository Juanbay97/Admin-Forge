# Egress Guard Specification

## Purpose
Network access of tools happens in the host through a guard that denies internal targets and enforces a per-policy allow-list.

## Requirements

### Requirement: Deny internal destinations

The guard MUST deny, after DNS resolution and for every redirect hop: loopback (127/8, ::1), link-local incl. cloud metadata (169.254.0.0/16, fe80::/10, fd00:ec2::254), RFC1918, CGNAT 100.64/10, unspecified, multicast, IPv4-mapped IPv6 forms, and non-http(s) schemes. The connection MUST be made to the validated IP (pinned) with the original Host/SNI.

#### Scenario: Metadata fetch
- GIVEN a tool fetches `http://169.254.169.254/latest/meta-data/`
- WHEN executed
- THEN it is denied and audited

#### Scenario: DNS rebinding
- GIVEN a hostname that resolves first to a public IP then to 127.0.0.1
- WHEN fetched
- THEN the connection uses the pinned validated IP only

#### Scenario: Redirect to private
- GIVEN a public URL redirecting to `http://10.0.0.5/`
- WHEN followed
- THEN the redirect is denied

### Requirement: Policy allow-list

When the effective policy supplies a host allow-list, only matching hosts MUST be reachable; with no list, only public destinations pass the deny rules above. The policy source is a parameter (assumed from the signed effective policy; see contract items).

#### Scenario: Allow-list
- GIVEN allow-list `["api.example.com"]`
- WHEN a tool fetches `other.example.com`
- THEN it is denied

### Requirement: Local forward proxy

A loopback forward proxy MAY be exposed to the container runner only; it MUST apply the same rules, bind a random loopback port, require a per-run token, and shut down with the run.

#### Scenario: Proxy without token
- GIVEN a request without the run token
- WHEN received
- THEN it is rejected

### Requirement: Limits

Responses MUST be size-capped and time-limited; bodies are never executed or written outside the jail.

#### Scenario: Huge body
- GIVEN a 2 GiB response
- WHEN fetched
- THEN reading stops at the cap with a truncation flag
