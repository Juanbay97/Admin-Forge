# Admin Chart Kit Specification (new)

## Requirements

### Requirement: CSP-safe rendering
Charts MUST be React-rendered SVG using presentation attributes and class names; no chart library that injects `<style>`
(Recharts-class) and no canvas-as-image data URIs. Colours MUST come from `--ui-chart-1..5` so branded and platform themes apply.

#### Scenario: No violations
- WHEN every chart renders with data, empty and error states
- THEN no CSP violation is recorded

### Requirement: Chart set
The kit MUST provide `Sparkline`, `AreaChart`/`LineChart` (time series, 1–5 series), `BarChart` (horizontal ranked, value labels),
`StackedBars` (per-model share) and `Donut` (≤6 segments + "other"). All accept `loading`, `empty` and `format` props.

#### Scenario: Time series
- GIVEN 30 daily points
- THEN the chart draws a path, ≤6 x ticks with date labels, nice y ticks, and a hover/focus crosshair with tooltip

### Requirement: Accessibility
Each chart MUST expose `role="img"` with an `aria-label` summary (title, range, total, peak) and a visually-hidden
`<table>` of the same data reachable by screen readers; points are keyboard-focusable with ArrowLeft/Right and announce values.
Colour MUST NOT be the only encoding (patterns/direct labels for >1 series; legend with markers).

#### Scenario: Keyboard
- WHEN the chart is focused and ArrowRight is pressed
- THEN the tooltip moves to the next point and its text is exposed through `aria-live="polite"`

### Requirement: Pure scale and format utilities
`niceTicks(min,max,count)`, `linearScale`, `timeTicks`, `buildLinePath`, `formatTokens` (1.2K, 3.4M), `formatCostMicros`
(`$0.0042`, `$1,234.56`; input integer micro-USD), `formatPercent` MUST be pure and unit-tested; zero/flat/NaN input MUST not throw.

#### Scenario: Formatting
- GIVEN 1_234_567 tokens and 4_200 micro-USD
- THEN `formatTokens` → `1.2M` and `formatCostMicros` → `$0.0042`

### Requirement: Responsive
Charts MUST size from container width via `ResizeObserver` (no inline style injection) with min height 160px, and degrade to
sparkline + table under 360px.

#### Scenario: Resize
- WHEN the viewport changes 1280 → 375
- THEN the chart re-renders within the container without horizontal page scroll
