# Admin Branding Specification

## Purpose

Let an org admin customize and preview branding, and theme the admin shell per org.

## Requirements

### Requirement: Branding page

The admin SPA MUST provide a Branding page (admin only) with inputs for the brand fields, asset upload, a live preview rendered in an isolated container with the same applier as production, a save with revision-conflict handling, and reset to Prometheon default.

#### Scenario: Live preview
- GIVEN an admin editing the primary color
- WHEN the value changes
- THEN the preview updates immediately and the page chrome does not change until saved

#### Scenario: Validation feedback
- GIVEN a low-contrast color or an SVG upload
- WHEN submitted
- THEN a clear inline error appears and nothing is saved

#### Scenario: Conflict
- GIVEN another admin saved first
- WHEN saving a stale revision
- THEN a reload prompt appears and nothing is overwritten

#### Scenario: Reset
- GIVEN customized branding
- WHEN the admin confirms reset
- THEN the default theme applies

### Requirement: Themed admin shell

The admin SPA MUST apply the selected org's branding (name, logo by color scheme, favicon, title, palette, font) using typed tokens and CSS variables only, MUST fall back to the Prometheon default, and MUST NOT relax its CSP (`style-src 'self'`, no inline).

#### Scenario: Org switch
- GIVEN an admin of A and B with different branding
- WHEN switching A to B
- THEN A's theme and assets are replaced by B's before B's data renders

#### Scenario: Strict CSP
- GIVEN a themed page
- WHEN loaded under the admin CSP
- THEN no CSP violation occurs and no inline style element is created
