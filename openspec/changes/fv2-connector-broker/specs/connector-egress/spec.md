# Connector Egress Specification

## Purpose
Constrain where the broker connects.

## Requirements

### Requirement: Allow-list and SSRF guard
Upstream requests MUST use https on 443 to hosts in the connector's allow-list. The guard MUST resolve once, reject loopback/link-local/RFC1918/metadata/ULA addresses, and connect to the pinned IP. Redirects MUST NOT be followed. Test composition MAY permit loopback only for explicitly injected fixture hosts.

#### Scenario: Private IP
- GIVEN allowed host resolving to 10.0.0.5
- WHEN called
- THEN denied

#### Scenario: Redirect
- GIVEN upstream 302 to another host
- WHEN received
- THEN not followed, error returned

#### Scenario: Rebind
- GIVEN DNS answering public then private
- WHEN connecting
- THEN pinned first-checked IP is used
