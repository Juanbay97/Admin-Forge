# Company Model Access Specification

## Purpose

The platform decides which upstream models a company may use; the company admin keeps publishing within that ceiling.

## Requirements

### Requirement: Platform-set ceiling
The platform MUST set per-company allowed upstream models (ceiling). Publication by the company admin MUST NOT exceed it; aliases outside it MUST NOT resolve for members.

#### Scenario: Within ceiling
- GIVEN ceiling {m1,m2}
- WHEN the admin publishes m1
- THEN members resolve m1

#### Scenario: Outside ceiling
- WHEN the admin publishes m3
- THEN denied; existing snapshot unchanged

### Requirement: Ceiling shrink applies immediately
Removing a model from the ceiling MUST stop member inference on it on the next request.

#### Scenario: Shrink
- WHEN m1 is removed while published
- THEN the next request for m1 is denied

### Requirement: Admin read-only gateway status
The company admin MUST see only status (configured, active key count) and MUST NOT write, read key data or origin details of platform keys. Catalog refresh MAY remain admin-initiated using the assigned key.

#### Scenario: Admin write refused
- WHEN a company admin PUTs a gateway key
- THEN refused, nothing stored

#### Scenario: Cross-company
- WHEN admin of A queries status of B
- THEN denied

### Requirement: Catalog binding stable across rotation
Catalog snapshots MUST stay valid when keys rotate or reorder within the same profile.

#### Scenario: Rotation
- WHEN K1 is rotated
- THEN the published catalog stays `CURRENT`
