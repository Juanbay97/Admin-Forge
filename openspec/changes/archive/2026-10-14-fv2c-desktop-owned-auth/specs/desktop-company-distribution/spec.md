# Desktop Company Distribution Specification

## Purpose
One unsigned Windows installer serves every company; company binding and control-plane origin come from configuration resolved at install/launch.

## Requirements

### Requirement: Configuration precedence

The app MUST resolve `{cp_origin, company_code}` with precedence: (1) deep link `prometheon-forge://join?cp=<origin>&code=<slug>`, (2) installer-written per-company config file, (3) build default. Values MUST be validated: `cp` is an https origin (http loopback only in dev builds) present in the build's allow-list; `code` matches the slug grammar; unknown query keys are rejected; secrets are never accepted.

#### Scenario: Deep link
- GIVEN the app is running or launched via a valid join link
- WHEN the link is received
- THEN the user confirms the displayed company/origin, then configuration is stored

#### Scenario: Hostile link
- GIVEN a link with an origin outside the allow-list, `javascript:`/`file:` scheme, path traversal or extra keys
- WHEN received
- THEN it is rejected with no state change and no network call

#### Scenario: Installer config
- GIVEN the installer wrote a valid config file
- WHEN the app first starts with no deep link
- THEN the config is used; a malformed file falls back to the build default and is reported

### Requirement: Single NSIS installer

The build MUST produce one NSIS installer, unsigned, with deep-link scheme registration, no upstream signing identity, bundling the sidecar and its resources, and checksums generated.

#### Scenario: Bundle verification
- GIVEN a built installer
- WHEN `verify-bundle` runs
- THEN sidecar, scheme registration, absence of Entra/signing remnants and checksum file are confirmed

### Requirement: Optional update-check hook

An update check MAY be enabled; when enabled it MUST fetch `latest.json` only from the configured CP origin, verify sha256 and version monotonicity, and only notify (no silent install). It MUST be disabled by default.

#### Scenario: Newer version available
- GIVEN the hook is enabled and `latest.json` has a higher version
- WHEN the app checks
- THEN it shows a notice with the download link; nothing is installed

### Requirement: Remote control-plane origin accepted by router and workers

The router and workers (today restricted to `http://127.0.0.1:<port>` by `LOOPBACK_ORIGIN`, forge_workspace.py:31) MUST accept an https production origin when it is in an explicit allow-list passed at launch, MUST verify TLS with the system trust store, MUST refuse redirects to other origins, and MUST keep rejecting any other non-loopback origin.

#### Scenario: Production origin
- GIVEN allow-list `https://forge.example.com` and `--control-plane-origin https://forge.example.com`
- WHEN the router starts
- THEN it validates and relays to that origin only

#### Scenario: Rejected origin
- GIVEN an https origin outside the allow-list, an IP literal, userinfo, or a port/path component
- WHEN the router starts
- THEN it exits with a validation error

### Requirement: CSP stays loopback-only

All CP traffic MUST be relayed by the router, so the Tauri CSP `connect-src` MUST contain only `self`, IPC and loopback; no remote host (including the CP origin) is added.

#### Scenario: CSP test
- GIVEN `tauri.conf.json`
- WHEN the packaging test parses the CSP
- THEN no `https:` wildcard or remote host is present
