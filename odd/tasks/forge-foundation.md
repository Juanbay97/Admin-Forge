# Forge foundation delivery

## Authorized outcome

Plan the generic Prometheon Forge MVP sprints, then begin local implementation using ODD and specification-driven development (SDD) where useful. Preserve the functioning hotel deployment, credentials, and both upstream snapshots. No remote operations, spending, publishing or production migration.

## Baseline and scope

Source of truth: outputs/prometheon-forge/specs (PF-00 through PF-12). Canonical product directory: N:/Proyects/forge/. Original workspace remains a preserved checkpoint; edit only the canonical product directory. Python/FastAPI control plane with PostgreSQL later; retain OpenYak agent core and OmniRoute routing. Historical 'Promtheon Forge' memory concerns a different own-agent-loop MVP whose recorded local directory is absent.

## Sprint plan

| Sprint | Outcome | Exit condition |
|---|---|---|
| S1 | Executable contracts and membership policy | Cross-organization and suspended-member denials tested; bootstrap exposes no secrets; DB/RLS separately proven before claiming isolation |
| S2 | Corporate sign-in and client spike | Entra PKCE and Forge session validated; no manual provider keys; test-only identity never enabled in runtime |
| S3 | Organization administration and branding | Provisioning, revocation, versioned config; two organizations use one client build |
| S4 | OmniRoute and budgets | Per-organization routing, capabilities, atomic reservations, truthful retry/limit UX |
| S5 | Image tools | Owned idempotent jobs, references/editing, authorized download; costs hidden from end users |
| S6 | Skills and audit | Draft backup distinct from reviewed publication; grants, restore, redacted event trail |
| S7 | Packaging and pilot | Signed Windows updater, clean installation, restore drill, hotel pilot and second-organization checks |

These are ordered delivery increments, not calendar commitments. Refine after measuring S1 throughput and receiving integration prerequisites.

## First work units and routing

- [x] F00 — Read-only explorer verified current specs and upstream commits; historical implementation absent locally. Delegated due repository mapping.
- [ ] F01 — Establish isolated repository and readable sprint/spec plan. Delegated writer; pass exact edit surfaces. No source implementation before plan is read back and mirrored in Engram.
- [ ] F02 — Observe failing deterministic membership/bootstrap tests, implement the bounded domain policy, and rerun. No database or provider access. One coherent feature commit with tests/docs.
- [x] F03 — Independent verification and parent spot check passed; native review and commits remain separately pending. Local task updated and mirrored in Engram.

## Acceptance for initial delivery

An authenticated subject supplied by a trusted future adapter can receive only their active organization's allowed public bootstrap. Missing context, foreign organization, suspended membership and unknown subject deny. Never trust request headers to create identity. Never include provider/router keys, costs or admin-only data in bootstrap. Pure-domain proof is not HTTP authentication or PostgreSQL RLS proof.

## Workflow and constraints

Route: delegated direct (multi-file implementation). Generic helpers/code/tests in English; extend user-facing Spanish planning docs in neutral Spanish. Skills: cognitive-doc-design and work-unit-commits resolved from installed Codex paths. No installed SDD-specific skill; use existing PF specs with one small change spec and traceable tests rather than install unknown tooling.

Default test-first: RED → GREEN → refactor when meaningful. Python 3.12.14 is available but pytest is not installed; parent approved standard-library unittest (`python -m unittest discover -s tests -v`) instead, avoiding downloads and new dependencies. Backend tests must run; real PostgreSQL tests remain pending until a local database is available. Never substitute SQLite as RLS evidence.

Delivery strategy: user-approved feature-branch-chain, local only, with small coherent work-unit commits. One development branch is the default; independent agent branches may be used when useful, without concurrent writes to the same checkout. The first coherent foundation unit is approximately 400 authored lines including tests and tracking; this is an explained heuristic overage, not a reason to compress code or documentation. Sprints beyond this unit remain backlog, not an oversized implementation commit. No push/PR/merge. Conventional commits, no AI attribution. Parent owns native review state and exact lifecycle; workers do not invoke it or toggle it.

## Memory and next step

Engram project: prometheon-forge. Authoritative runtime session ID unavailable; omit session_id. Save a full recovery mirror under odd/forge-foundation/tasks after reading this file. No claim that a memory write is user delivery.

Plan written: docs/sprints.md and docs/changes/foundation.md. Parent readback and mirror completed before source implementation. Git author identity now resolves through git var GIT_AUTHOR_IDENT in the authorized execution context; no identity override or global configuration change is made by this worker.


## Current checkpoint

F01 isolated repository, sprint plan and SDD document are ready; parent readback/mirror completed. F02 behavior is implemented and locally verified. Local root and feature commits are now authorized; exact commit evidence will be recorded after creation.
F03 verification passed: independent verifier ran 13 unit tests plus 26 adversarial checks; parent reran all 13 tests successfully. No native review verdict is claimed.

Canonical verification on 2026-10-03 used
`C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`:
- `-m unittest discover -s tests -v`: RED 13 methods, 23 NotImplementedError subcase errors; GREEN 13 methods passed.
- `-m compileall -q src tests`: exit 0.
- Git initially failed after relocation because empty metadata directories were absent; parent restored them. Final git and source-whitespace checks are recorded by the worker handoff.

Branch: `feat/forge-foundation`. Commit identities are recorded below when observed.
No auth adapter, HTTP endpoints, live provider, or PostgreSQL/RLS proof exists yet.
Identity and delivery-strategy blockers are resolved. Preserve the original checkpoint. Next: create the authorized local commits, then parent re-enters native review on the committed candidate; no approval is implied by committing.

## Parent verification and review checkpoint

Independent checks covered all 16 two-organization ID combinations, identity/status denials, secret exclusion and response independence. Parent spot check: 13/13 unit tests, exit 0. Writer checked whitespace in all nine authored files; git diff --check alone is not proof for untracked files.

Native RDD mode is on (global). Assessment is unassessable until the nine new files are explicitly selected. Selectorless STATUS at N:/Proyects/forge returned collect/intended_untracked_selection_required, horizon partial, step 1 collect: intended untracked selection required. No START, candidate freeze, consent, reviewer or approval occurred. The external.select_intended_untracked host operation is not exposed in this session; do not invent its schema-bound submission. Re-enter through the documented provider integration after restoring that selection capability or after ordinary authorized Git tracking establishes the candidate. Do not toggle RDD or claim an approval.

Plan, code and tests are local only. Login, HTTP contracts and PostgreSQL/RLS are pending; Sprint 1 is not complete.


## Progressive UI verification

Test real UI flows progressively as executable screens become available; retain
observed evidence and disclose gaps. Unit tests alone do not certify UI behavior
or guarantee zero errors. This pure-domain unit has no UI: UI verification is N/A,
not PASS. This preference authorizes no production access, authentication or spending.


## Local commit evidence

Empty root baseline: `5aa398bf80c44083a7f9ef7ac1066a33bd4cf9e9`.
The feature candidate contains only the nine explicitly authorized files.
Runtime harness and UI: N/A, no transport or executable screen exists.
Rollback boundary: this foundation module, tests and accompanying project documents;
no upstream snapshot, hotel deployment or external service belongs to this unit.
