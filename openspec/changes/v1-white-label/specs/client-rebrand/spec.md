# Delta for Client Rebrand

## MODIFIED Requirements

### Requirement: Brand seam

A `brand.ts` module MUST be the single source of the default product name, wordmark and tokens; the logo component MUST be renamed `BrandMark`. Per-company theming MUST flow only through the typed branding loader (see `client-branding`), never through bootstrap.
(Previously: "Per-company theming MUST NOT be implemented.")

#### Scenario: Single source
- GIVEN visible components
- WHEN grepping for the literal product name
- THEN it appears only in `brand.ts` and i18n resources

#### Scenario: Bootstrap brand field ignored
- GIVEN a bootstrap payload with a brand field
- WHEN the client loads
- THEN it is ignored; only the validated branding endpoint can change the theme
