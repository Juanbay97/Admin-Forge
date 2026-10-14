# Desktop Owned Login Specification

## Purpose
The desktop app authenticates members only through the control plane's owned accounts and never through Microsoft Entra.

## Requirements

### Requirement: Entra path removed

The desktop shell MUST NOT contain Entra/OIDC/PKCE code, IPC commands, store, scopes or CSP entries for Microsoft hosts.

#### Scenario: No Entra artefacts
- GIVEN the repository at the end of this change
- WHEN the packaging test scans `desktop-tauri/`, `frontend/src` and `tauri.conf.json`
- THEN no file or identifier matches `entra`, `login.microsoftonline` or `msal`

### Requirement: Owned-account sign-in in the desktop shell

The desktop frontend MUST use the existing owned-account flow (email + password -> session -> `/accounts/me` -> org picker) against the configured control-plane origin, and MUST keep the session token in memory only.

#### Scenario: Sign in
- GIVEN a configured CP origin and a member with an owned account
- WHEN the member submits valid credentials
- THEN the router creates the profile worker and the workspace opens with the company brand

#### Scenario: Invalid credentials
- GIVEN wrong credentials
- WHEN submitted
- THEN a generic failure is shown and no worker is started

### Requirement: Company code is prefilled and not editable when configured

When a company code is present from configuration, the company-code gate MUST be satisfied automatically, branding MUST be applied before sign-in, and the code MUST NOT be editable except through the explicit "change company" action.

#### Scenario: Preconfigured code
- GIVEN configuration with code `acme`
- WHEN the app starts
- THEN `GET /forge/v1/branding?org=acme` is fetched and the Acme brand is shown pre-login

#### Scenario: Unknown code
- GIVEN configured code that the CP does not know
- WHEN the app starts
- THEN a neutral error with a "change company" action is shown and no brand is applied

### Requirement: Change of company discards state

Changing company (code or CP origin) MUST require confirmation and MUST discard all profile state and sessions of the previous company.

#### Scenario: Switch company
- GIVEN a signed-in member
- WHEN they confirm changing company
- THEN workers are stopped, profiles of the previous company are not reachable and the gate restarts
