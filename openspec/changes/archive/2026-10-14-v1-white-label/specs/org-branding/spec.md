# Org Branding Specification

## Purpose

Per-organization, revisioned, validated branding served safely to pre-login and authenticated clients.

## Requirements

### Requirement: Validated storage and revisions

The system MUST store per org: primary/accent/tint (`#RRGGBB`), heading/body font id from the vetted list, product name (<=40 plain chars), login copy (<=280 plain chars) and up to three asset hashes. Saves MUST be admin-only, compare-and-swap on revision, append an audit/history row, and reject unknown keys.

#### Scenario: Save
- GIVEN an admin of org A at revision 2
- WHEN saving valid branding with expected revision 2
- THEN revision 3 is current and an audit row names the actor

#### Scenario: Conflict and invalid input
- GIVEN a stale expected revision, or a color `red`, `#12`, font `Comic`, or name with control characters
- WHEN saving
- THEN the request is refused (409/422) and nothing changes

#### Scenario: Contrast
- GIVEN a primary color below 3:1 against white
- WHEN saving
- THEN it is refused with a contrast reason

#### Scenario: Cross-org
- GIVEN an admin of A
- WHEN saving or uploading for org B
- THEN 404

### Requirement: Safe assets

Uploads MUST be PNG or WebP only, <=256 KB, 16-1024 px per side, verified by magic bytes and header dimensions, rewritten with ancillary/metadata chunks removed, and stored content-addressed (sha256). SVG, other types, truncated or oversize files MUST be refused.

#### Scenario: Valid PNG
- GIVEN a 300x200 PNG with an EXIF/text chunk
- WHEN uploaded
- THEN stored bytes contain no metadata chunks and the sha256 of the stored bytes is returned

#### Scenario: Rejections
- GIVEN an SVG, a PNG renamed `.webp`, a 2000 px image, or a 300 KB file
- WHEN uploaded
- THEN 415/413/422 and nothing is stored

### Requirement: Public branding endpoint

`GET /forge/v1/branding?org=<slug>` MUST be unauthenticated, rate-limited, ETag by revision, and return only name, login copy, theme tokens, font ids, asset URLs and revision. Unknown or inactive slugs MUST return an identical 404. An org without branding MUST return the Prometheon default at revision 0.

#### Scenario: Known org
- GIVEN org `acme` with branding revision 3
- WHEN requesting with `If-None-Match: "3"`
- THEN 304; without it, 200 with exactly the public fields

#### Scenario: No leakage
- GIVEN unknown, inactive and malformed slugs
- WHEN requesting
- THEN identical 404/422 bodies and no member, id or secret data

#### Scenario: Rate limit
- GIVEN more requests than the per-IP budget
- WHEN requesting again
- THEN 429 with Retry-After

### Requirement: Content-addressed delivery

`GET /forge/v1/branding/assets/{sha256}` MUST serve only assets referenced by a current revision, with `Cache-Control: immutable`, `X-Content-Type-Options: nosniff`, and the stored image type.

#### Scenario: Serving
- GIVEN a published asset hash
- WHEN fetched
- THEN 200 with matching bytes; an uploaded-but-unpublished or unknown hash returns 404

### Requirement: Authenticated projection and reset

Members MUST read their org's branding at `GET /forge/v1/orgs/{o}/branding`; admins MUST reset to default as a new revision. `bootstrap` shape MUST NOT change.

#### Scenario: Reset
- GIVEN customized branding
- WHEN an admin resets
- THEN a new revision serves the default theme and history is kept
