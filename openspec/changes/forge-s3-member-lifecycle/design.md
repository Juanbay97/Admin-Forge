# Design: Safe S3 lifecycle prerequisite

**P1a recording is implemented; review remains pending. P1b bridge is not implemented.** Three specs define O1–O3, D1–D4 and M1–M3. No recovery implementation, UI, S4–S7 implementation, budget attribution, dependencies or signing changes are included.

P1a's internal recorder accepts a caller-owned transaction and never commits or borrows a pool. The trusted caller authorizes the resource mutation and sets organization context. `forge_outbox_writer` has INSERT only, no resource read/write authority; FORCE RLS checks that context. Event IDs and organization/resource revisions are unique. No routes, worker, legacy import or publication are composed. P1b must precede any worker rollout; legacy events remain preserved in the original table meanwhile.

## Verified evidence

| Source | Consequence |
|---|---|
| `migrations/0004_initial_admin_designation.sql:1–15,114–126`; `src/forge/administration_store.py:87–104` | Permanent per-organization designation, active-only targets, existing-admin rejection: central designation is NOT recovery. |
| `src/forge/identity_store.py:62–68,81–89`; `src/forge/postgres.py:64–69` | Binder updates existing identities only; bootstrap requires bound Entra IDs. Authentication is not enrollment. |
| `src/forge/authorization_store.py:38–43`; `src/forge/postgres.py:17–51` | Authorization snapshots are not write authority; runtime ACL checks reject write grants. |
| `src/forge/runtime.py:140–152,230–232` | Only bootstrap pool/reader are composed today. New services need explicit composition. |
| `tests/postgres_support.py:364–419` | Migration list and role lifecycle are explicit, not auto-discovered. |

Evidence above is retained from the prior planning inspection, not new runtime proof. This reconciliation's CodeGraph query found no index; no index was created and no product sources needed reopening.

## Architecture decisions

| Choice | Alternative / tradeoff | Rationale |
|---|---|---|
| Separate restricted writer, enrollment and worker pools; keep runtime read-only | Broaden runtime grants: simpler, violates current checks | Preserve least privilege, FORCE RLS and explicit trusted composition. |
| Pure policies, frozen commands, synchronous ports and stores | Route-owned SQL: fewer files, weaker boundaries | Match existing adapters and redaction. |
| Organization serialization plus database last-admin guard | Application count alone races | Lock before fresh authority/count reads; guard all permitted role/status write paths; bounded timeout fails closed. |
| Pending invite reserves membership UUID and tenant/object tuple; materialize identity/membership on validated activation | New membership status changes existing consumers | No access or administrator count before binding; unique organization/tenant/object reservation. |
| Generic event plus later delivery-state sidecar; atomic backfill and AFTER INSERT legacy mirror | Recurring importer requires incompatible legacy read policies | Preserve stable IDs and every legacy grant/policy; worker reads only the destination. |
| Lease claims, fencing token, capped backoff | Hold transaction through sink: simpler, locks during I/O | Crash recovery and stale-worker exclusion without claiming exactly-once delivery. |
| Many-to-many association keyed by organization/member/department | Single nullable department rejects cross-functional members | Composite same-org foreign keys and unique triples; no association implies administrative privilege. |
| Reject occupied archive, never detach automatically | Automatic detachment silently changes access | Count all links, including suspended members, under the same organization lock as assignment and activation. |

## Interfaces and flow

Proposed ports: `DepartmentStore.mutate/read`, `MemberStore.invite/mutate/read`, `EnrollmentStore.activate(VerifiedPrincipal, organization_id)`, `OutboxStore.claim/ack/retry`, `EventSink.publish`.

```text
Client -> API: bearer + organization + command + If-Match
API -> validator: validate once
API -> service -> store: trusted identity, typed command
store -> DB: BEGIN; organization lock; reload actor; check revision
store -> DB: resource + revision + event; COMMIT
API -> Client: allowlisted projection + ETag

Bootstrap -> validator: validated principal (not client claims)
Bootstrap -> enrollment: matching pending invite, atomic activation/event
Bootstrap -> existing reader: bound identity; normal access checks

Migration -> DB: verify complete RLS visibility; lock legacy writes; install mirror + backfill; COMMIT
Legacy designation -> DB: AFTER INSERT mirror; failure aborts the entire transaction
Worker -> DB: claim destination SKIP LOCKED; lease/token; COMMIT
Worker -> redacted log: allowlisted event projection
Worker -> DB: fenced acknowledgment OR scheduled retry
```

Paths use existing `/forge/v1/organizations/{organization_id}`: departments GET/POST/PATCH, members GET/POST/PATCH, and member suspend/reactivate POST. Reads expose IDs, roles, status, authorized department_ids and revision only; no email/claims. Manager projections intersect member associations with the manager's current authorized department set; a shared member never exposes other departments. Strong revision ETag; absent If-Match 428, stale 412, invariant/duplicate conflict 409, invalid input 422, unauthenticated 401, same-org forbidden 403, concealed foreign/missing 404, storage failure 503. Extend fixed error envelopes, never diagnostics.

Association replacement uses the membership revision, validates the entire requested set, and changes links/revision/event atomically. Empty sets unlink all; duplicates are rejected; unchanged sets are no-ops. Archive checks all committed member links, not just active members. Invite intent is stored separately as a same-org department set; it grants no association/access, and activation revalidates every department before materializing all links. Concurrent archive versus assignment/activation must either preserve a linked active department or reject linking to the archived one.

All permitted writers acquire the organization lock before fresh authority, revision and last-admin reads (READ COMMITTED statement after lock acquisition); snapshot-based stale counts are not allowed. Database guards enforce the same serialization for direct granted SQL role/status paths, not only service calls. Pending, unbound and suspended administrator records never count. No recovery bypass or designation-marker deletion is permitted.

## Migration and rollout

Add `0005_transactional_outbox.sql` (P1a), then `0006_legacy_outbox_bridge.sql` (P1b), `0007_organization_departments.sql`, `0008_member_invitations.sql`, `0009_member_mutations.sql`; preserve 0001–0004. Departments carry revision/status; assignments use organization-composite references. Every migration includes catalog/ACL/RLS readiness and populated-upgrade/failure rollback proof. Worker acknowledges log delivery only, never durable audit publication; retain events for S6.

Opt-in composition stays disabled until the full chain passes. Stop worker/disable services before reverse-order code rollback; retain additive schema/data AND the functioning bridge dependencies. Prove old runtime checks still accept retained schema. Exact per-slice surfaces, tests and rollback boundaries: [implementation-plan.md](implementation-plan.md).

### Approved future P1b security exception (premise review, not behavior verification)

Use a dedicated NOLOGIN/NOSUPERUSER/NOBYPASSRLS/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOINHERIT function owner with no membership edges, application SET ROLE path, or table/schema ownership. It receives schema USAGE and destination INSERT only (no SELECT/RETURNING). Destination FORCE RLS admits only the bounded legacy event shape. The zero-argument SECURITY DEFINER trigger checks exact source relation OID and INSERT/AFTER/ROW/zero-argument context; uses static qualified SQL, explicit NEW projection, and `search_path=pg_catalog,pg_temp`. No dynamic SQL, arbitrary metadata or silent conflict ignore. Revoke PUBLIC/application EXECUTE after trusted installation; prove PG17 still fires the installed trigger for the unchanged designator. Function name must remain outside `designation_%`. The migration verifies administrator visibility before its bounded write-conflicting lock; schema, trigger and full backfill commit together. Preserve legacy columns, ownership, grants, helpers and policies exactly.

## Confirmed decisions and remaining limitations

Recovery is explicitly outside MVP; existing central designation is not recovery. Many-to-many membership and occupied-archive rejection are approved. Department managers remain read-only within their authorized department set; membership alone grants no admin role. Feature Branch Chain is confirmed, mapped from force-chained to auto-chain for slicing. No product decision blocks P1.

The S7 domain exists but its name is pending; Windows signing is deferred for manual MVP installation, never unsigned automatic updates or bypassed verification. These are not S3 gates. Later budget attribution is explicitly excluded.

## Verification

Strict RED/GREEN/REFACTOR, module unittest plus owned PostgreSQL harness. Cover real concurrent locks, authority revocation, last-admin races, activation uniqueness, cross-org RLS, readiness tampering, failure atomicity, lease expiry and secret-marker redaction. No browser/client proof claimed; first-login integration is server-side bootstrap, not desktop PKCE.
