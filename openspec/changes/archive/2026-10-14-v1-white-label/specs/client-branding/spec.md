# Client Branding Specification

## Purpose

The client shows the company's identity from first launch, applied safely.

## Requirements

### Requirement: Company code and cache

On first launch the client MUST ask for a company code (org slug), fetch public branding through the local bridge, and cache the last valid payload and assets; later launches MUST apply the cache immediately and revalidate by ETag.

#### Scenario: First launch
- GIVEN no stored company code
- WHEN the client starts
- THEN a code screen with Prometheon default look appears and, after a valid code, the company theme applies before login

#### Scenario: Unknown code
- GIVEN an unknown code
- WHEN submitted
- THEN a generic "company not found" message appears and the default theme stays

#### Scenario: Offline
- GIVEN a cached payload and an unreachable control plane
- WHEN the client starts
- THEN the cached branding applies

### Requirement: Safe theme application

The client MUST validate payloads against an exact-key typed schema (hex colors, font ids from the bundled list, plain text, asset URLs of the form `/forge/v1/branding/assets/<sha256>`), and MUST apply them only via `style.setProperty` and React text; it MUST NOT inject server-provided CSS, HTML or URLs elsewhere.

#### Scenario: Hostile payload
- GIVEN a payload with `red; } body{display:none` as a color, an extra key, or an external asset URL
- WHEN received
- THEN it is rejected whole and the previous or default theme remains

#### Scenario: Palette parity
- GIVEN the shared golden vectors
- WHEN generating light/dark tokens
- THEN the client output equals the admin and vector expectations

### Requirement: Content Security Policy

The managed client MUST send a CSP restricting `default-src`, `connect-src`, `img-src`, `font-src`, `object-src 'none'`, `base-uri` and `frame-ancestors` to same origin (plus data/blob images), with no remote origins.

#### Scenario: Branded assets
- GIVEN branded logos served same-origin
- WHEN rendering
- THEN no CSP violation and no third-party request occurs

### Requirement: Runtime identity and icons

Window/page title, logo, favicon and login copy MUST come from branding with Prometheon fallback; shipped Tauri icons MUST be Prometheon art and Apache-2.0 LICENSE/NOTICE MUST remain unmodified.

#### Scenario: Two companies
- GIVEN orgs acme and globex with different branding
- WHEN each member signs in
- THEN each sees its own name, logo and palette, and never the other's
