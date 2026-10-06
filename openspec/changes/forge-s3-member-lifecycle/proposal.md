# Proposal: S3 closure — departments, member lifecycle, outbox worker

## Intent

S4 budgets and alias catalogs need areas and a real member lifecycle; today only the initial admin exists, `members.*` permissions have no endpoints, and `initial_admin_outbox` is never published. Close these S3 gaps so S4+ build on real data.

## Scope

### In Scope
- Generic transactional recording (0005, P1a), separate complete legacy bridge (0006, P1b), then worker (P2: `SKIP LOCKED`, retry/backoff, sink port). Only the completed later bridge/worker drains `initial_admin_outbox`; P1a does not import or publish it.
- Departments/areas: table + RLS, admin create/rename/archive, many-to-many member/department associations; reject archive while any member remains linked.
- Invite: admin pre-provisions a membership by Entra `tenant_id + object_id` (no email matching); bound on first validated login.
- Update (roles, department associations) and suspend/reactivate with `If-Match` revision, race-safe last-admin guard, one outbox event per state-changing mutation.

### Out of Scope
- **F09 desktop PKCE / client session / token storage** → OpenYak fork (S7 decision).
- Grants with deny precedence (introduced by S5/S6 consumers).
- Policy/brand revisions, publish, discovery endpoint (not required by S4).
- Audit read APIs, `audit_events` (S6); admin UI (`forge-admin-ui`).
- Removal/archival of members, admin recovery.
- Later department budget/cost attribution: multi-area membership does not choose a billing allocation policy.
- S7 domain naming and packaging: domain exists, name pending; Windows signing deferred for manual MVP installation only. Never unsigned automatic updates or verification bypass.

## Capabilities

### New Capabilities
- `outbox-publication`: durable event recording, claiming, delivery, retry.
- `organization-departments`: area lifecycle and membership assignment.
- `member-lifecycle`: invite, update, suspend/reactivate under admin authorization.

### Modified Capabilities
- None (no `openspec/specs/` baseline yet).

## Approach

Existing patterns: pure policy → typed ports → RLS-forced stores → redacted FastAPI routes. Mutations commit row + revision + outbox event atomically; readiness probe extended per migration.

## Affected Areas

| Area | Impact |
|------|--------|
| `migrations/0005–0009*.sql` | New; exact paths in implementation-plan.md |
| `src/forge/outbox.py`, `departments.py`, `members.py` (+ stores) | New |
| `src/forge/authorization.py`, `api.py`, `runtime.py`, `postgres.py` | Modified |
| `tests/` (unit + real PG) | New |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cross-org leak via new tables | Med | RLS FORCE + cross-org/suspended denial tests on real PG |
| Last-admin lockout | Med | DB-enforced serialization/guard; recovery explicitly deferred outside MVP, central designation is NOT recovery |
| Duplicate/lost events | Med | Idempotent `event_id`, at-least-once + consumer dedupe |
| No durable audit sink yet | High | Approved redacted log sink until S6; never durable audit proof |

Cost impact: none (no model calls). Security: default-deny unchanged; only `organization_admin` mutates.

## Rollback Plan

Each slice is an isolated commit; revert in reverse order. Migrations are additive (no destructive downgrade); disable routes via composition flag; worker is a separate entrypoint and can stay stopped.

## Dependencies

- Decisions confirmed: recovery excluded; last active admin protected; many-to-many departments with no implicit privilege; occupied archive blocked; managers read-only within authorized departments; Entra tenant/object invite binding; redacted logs until S6.
- Feature Branch Chain confirmed: first child targets tracker, later children target predecessor; only tracker eventually targets main. No branch changes, push, PR or merge authorized in planning.

## Success Criteria

- [ ] Admin invites, updates, suspends members; other roles/orgs denied (403/404) on real PG.
- [ ] Last admin cannot be suspended/demoted.
- [ ] Every mutation yields exactly one outbox event; worker publishes pending events, including the initial-admin event.
- [ ] Ten implementation units remain below the 800-line forecast ceiling, including tests/docs; see tasks.md and implementation-plan.md.

## Planning history

The original 2.4–3k/four-slice forecast, then six-slice forecast, underestimated security/readiness tests and multi-area associations. The current forecast supersedes them without discarding prior evidence. Resolved product questions are no longer apply gates; external identity loss remains an accepted MVP recovery limitation.
