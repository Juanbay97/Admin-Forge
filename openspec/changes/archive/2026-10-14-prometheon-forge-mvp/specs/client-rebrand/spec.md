# Delta for Client Rebrand

## ADDED Requirements

### Requirement: Visible identity is Prometheon Forge

All user-visible surfaces (window/page titles, splash, title bar, onboarding, notifications, about, i18n en+zh strings, favicon, manifest, README/FORGE top-level docs, Tauri window/icon strings) MUST show "Prometheon Forge" and MUST NOT show "OpenYak".

#### Scenario: Rendered text scan
- GIVEN the production build
- WHEN Playwright visits splash, login, workspace, onboarding, settings and about
- THEN no visible text or document title matches `/openyak|yakagent/i`

#### Scenario: Static assets
- GIVEN `public/manifest.json`, favicon and icon set
- WHEN inspected
- THEN names and images are Prometheon assets derived from `Marca/`

#### Scenario: Mobile PWA pages
- GIVEN `(mobile)/m/*` pages
- WHEN built
- THEN they are hidden or renamed; none shows OpenYak branding

### Requirement: Brand tokens, assets and fonts

Theme tokens MUST follow the brand manual (Azul Profundo `#0B1D26`, Teal `#0F6B6D`, Cobre `#E07A2D` accent only, Arena `#E8DCC1`, Carbon `#1A1A1A`; never `#000`), light and dark. Montserrat (titles) and Inter (body) MUST be bundled as local files. Teal→Cobre gradients and Cobre-on-Teal text MUST NOT be used.

#### Scenario: Tokens
- GIVEN light and dark themes
- WHEN reading computed CSS variables
- THEN primary/background/accent equal the manual values and no `#339CFF` remains

#### Scenario: Local fonts
- GIVEN network restricted to the app origin
- WHEN loading the app
- THEN fonts load from local files with no third-party font request

#### Scenario: Contrast
- GIVEN primary text/background pairs
- WHEN checked
- THEN contrast meets WCAG AA

### Requirement: Brand seam

A `brand.ts` module MUST be the single source of product name, wordmark and tokens; the logo component MUST be renamed `BrandMark`. Per-company theming MUST NOT be implemented.

#### Scenario: Single source
- GIVEN visible components
- WHEN grepping for the literal product name
- THEN it appears only in `brand.ts` and i18n resources

#### Scenario: No tenant theming
- GIVEN a bootstrap payload with a brand field
- WHEN the client loads
- THEN it is ignored and defaults apply

### Requirement: Internals and legal preserved

Internal identifiers (`openyak-*` storage keys, token prefixes, crate/package ids, provider id) MAY remain and MUST be recorded as tech-debt; Apache-2.0 LICENSE/NOTICE attribution MUST remain intact.

#### Scenario: Attribution
- GIVEN the repository
- WHEN checking LICENSE and NOTICE
- THEN they are unmodified in content and still reference upstream

#### Scenario: Tech-debt record
- GIVEN deferred internal renames
- WHEN reading change docs
- THEN each category is listed as deferred, none user-visible

#### Scenario: Persisted settings
- GIVEN existing localStorage `openyak-*` keys
- WHEN the rebranded client loads
- THEN settings still apply (no silent reset)
