# Usage Capture Specification

## Purpose

Capture token usage and timing for every inference without storing content.

## Requirements

### Requirement: Request usage from gateway
The adapter MUST send `stream_options.include_usage=true`.

#### Scenario: Request shape
- WHEN the adapter streams
- THEN the upstream body contains `stream_options:{include_usage:true}`

### Requirement: Strict usage chunk
The parser MUST accept at most one terminal chunk with `choices: []` and `usage` of non-negative integers `prompt_tokens`, `completion_tokens` (optional `total_tokens`) after the finish chunk and before `[DONE]`. Any other extra field, second usage chunk, negative/float/bool value or usage before finish MUST be rejected as `GatewayUnavailable`.

#### Scenario: Valid usage chunk
- GIVEN stop chunk then `choices:[]` with usage then `[DONE]`
- WHEN parsed
- THEN a `usage` event is emitted and the stream succeeds

#### Scenario: Fuzzed shapes
- GIVEN usage with unknown keys, negatives, huge ints, strings, duplicates
- THEN the stream fails closed

#### Scenario: Gateway without usage
- GIVEN no usage chunk
- THEN the stream still succeeds and no `usage` event is emitted

### Requirement: Event per inference
The system MUST record one `usage_events` row per inference attempt that reached the gateway: org, membership, model alias, upstream id, key id, tokens, latency, ttfb, status, error code, `usage_source`. Rows MUST NOT contain prompt/response text.

#### Scenario: Success with usage
- THEN `usage_source=gateway` with gateway tokens

#### Scenario: Cancel or missing usage
- GIVEN client disconnect or gateway omitted usage
- THEN a row is written with `usage_source=estimated` (chars/4), status reflecting cancel

#### Scenario: Recording failure
- WHEN the store is unavailable
- THEN the member stream is unaffected and a finite error counter increments

### Requirement: Fake gateway
The fake gateway MUST emit a usage chunk by default and omit it in a `no-usage` model mode.

#### Scenario: Modes
- WHEN model `fake-nousage` is used
- THEN no usage chunk is sent

### Requirement: Quota hook
`GatewayInference.prepare` MUST call `quota_check(org, membership)`; the default is a no-op that never denies.

#### Scenario: Default
- THEN requests are never denied by quota
