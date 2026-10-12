# Admin Design System Specification (new)

## Purpose
One accessible, brand-token-driven component set for all three SPA areas, safe under CSP `style-src 'self'`.

## Requirements

### Requirement: Semantic tokens over brand tokens
Components MUST style only through semantic `--ui-*` variables (surface, surface-raised, border, fg, fg-muted, primary, primary-fg,
accent, ring, success, warning, destructive, chart-1..5) defined in `tokens.css` from the 26 `--brand-*` variables. Company themes
MUST keep working without component edits.

#### Scenario: Company theme restyles components
- GIVEN a company branding with primary `#0B5FFF`
- WHEN the branded area renders a Button (default variant)
- THEN its computed background equals the generated palette primary and its text/background contrast is ≥ 4.5:1

#### Scenario: Platform theme is immune to company branding
- GIVEN company branding was applied earlier in the session
- WHEN the user enters the Platform area
- THEN `--brand-*` equal the fixed Prometheon theme values and no company asset is shown

### Requirement: Dark mode for the platform area only
The platform area MUST support light and dark (`data-mode` on `<html>`), defaulting to `prefers-color-scheme`, with a persisted
toggle (`localStorage` key `forge.mode`, non-sensitive). Company and portal areas MUST render light only.

#### Scenario: Toggle persists
- GIVEN the platform area in light mode
- WHEN the user toggles dark and reloads
- THEN dark mode is active after sign-in and axe reports no contrast violations

### Requirement: Typography and spacing scale
Headings MUST use Montserrat; body/table/forms Inter (self-hosted fonts already allow-listed). Scale: page title 24/32 bold,
section title 18/28 semibold, card title 16/24 semibold, body 14/20, caption 12/16; spacing on a 4px grid; radius 8 (inputs/buttons),
12 (cards, dialogs); content max-width 1280.

#### Scenario: Computed typography
- WHEN any page `<h1>` renders
- THEN computed font-family starts with the title font and font-size is 24px; body text is 14px/20px

### Requirement: CSP safety
The kit MUST NOT create `<style>` elements, set the `style` attribute through `setAttribute`/`innerHTML`, use `eval`, or load remote
resources. Styling by class names and CSSOM (`element.style.x`, React `style` prop) only.

#### Scenario: No violations
- GIVEN the kit gallery test build
- WHEN every component and overlay is opened and closed
- THEN no `securitypolicyviolation` event and no CSP console error is recorded

### Requirement: Component inventory
The kit MUST provide: Button (variants default/secondary/outline/ghost/destructive/link, sizes, loading), Input, Textarea,
Select (native, styled), Checkbox, Switch, RadioGroup, Field (label, hint, error bound via `aria-describedby`/`aria-invalid`),
Form helpers (react-hook-form + zod resolver), Card, Badge, Alert, Separator, Skeleton, Spinner, EmptyState, Tabs, Tooltip,
DropdownMenu, Dialog/AlertDialog/Sheet (native `<dialog>`), Toast, DataTable, Pagination, CopyButton, KeyField (write-only secret).

#### Scenario: Field error is announced
- GIVEN a required Input with a validation error
- THEN the input has `aria-invalid="true"`, `aria-describedby` points at the error text, and the error is in an `aria-live="polite"` region

#### Scenario: Dialog is accessible
- WHEN a Dialog opens
- THEN focus moves inside, Tab cycles within it, Esc closes it, and focus returns to the trigger

### Requirement: Loading, empty and error states
Every list/data view MUST render a Skeleton while loading, an EmptyState (icon, title, hint, primary action) when empty, and an
Alert with retry on failure. Destructive actions MUST use an AlertDialog.

#### Scenario: Empty list
- GIVEN an API returning zero items
- THEN the view shows the EmptyState with its primary action, not an empty table

### Requirement: Responsive and keyboard behaviour
Layouts MUST not scroll horizontally at 375, 768, 1280 px; interactive targets ≥ 40×40 px (44 on touch widths); visible focus ring
(2px `--ui-ring`); `prefers-reduced-motion` disables transitions.

#### Scenario: Mobile viewport
- GIVEN a 375px viewport
- THEN `document.documentElement.scrollWidth <= innerWidth` on every shell route
