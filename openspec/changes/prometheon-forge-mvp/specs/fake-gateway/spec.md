# Delta for Fake Gateway

## ADDED Requirements

### Requirement: Contract-exact OpenAI-compatible surface

The fake gateway (test/dev only) MUST expose `GET /v1/models` and streaming `POST /v1/chat/completions` in the exact shape the strict adapters accept: single choice, delta keys limited to `role`/`content`, a `finish_reason` chunk, then `data: [DONE]`. It MUST bind to loopback only.

#### Scenario: Models
- GIVEN a valid bearer key
- WHEN calling `/v1/models`
- THEN a bounded list of model ids is returned and the catalog adapter accepts it

#### Scenario: Streamed chat
- GIVEN a valid key and `stream:true`
- WHEN calling chat completions
- THEN SSE chunks conform, end with `finish_reason` then `[DONE]`, and the inference adapter normalizes them

#### Scenario: Non-loopback bind
- GIVEN a config requesting a non-loopback host
- WHEN starting
- THEN it refuses to start

### Requirement: Authorization recording and key rejection

The fake MUST record the `Authorization` header of every request (retrievable by tests via a control endpoint/API) and MUST reject missing or wrong keys with 401. Recorded values MUST never be echoed in any response body.

#### Scenario: Bad key
- GIVEN the fake expects key K
- WHEN a request arrives with key K2 or none
- THEN 401 and the attempt is recorded

#### Scenario: Custody proof
- GIVEN org A stored key K_A and org B stored K_B
- WHEN each org's member chats
- THEN recorded headers show only `Bearer K_A` for A's calls and `Bearer K_B` for B's

#### Scenario: No echo
- GIVEN any request
- WHEN the response is inspected
- THEN it contains no part of the bearer value

### Requirement: Fault injection for adapter strictness

The fake SHOULD support deterministic modes (extra delta keys, missing `[DONE]`, oversized chunk, slow stream, redirect, 5xx) to prove adapters fail closed with redacted errors.

#### Scenario: Malformed stream
- GIVEN mode "extra-delta-key"
- WHEN a member chats
- THEN the stream aborts with a redacted error and no upstream text is shown

#### Scenario: Slow stream and suspension
- GIVEN mode "slow"
- WHEN the member is suspended mid-stream
- THEN the Forge stream terminates and no further chunks are delivered

#### Scenario: Reset isolation
- GIVEN recorded state from a previous test
- WHEN the reset control is called
- THEN records and modes are cleared
