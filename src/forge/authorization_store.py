"""Fresh organization-scoped authorization over an externally owned sync pool."""
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from forge.authorization import AuthorizationSnapshot, valid_identity, valid_snapshot
from forge.foundation import AuthenticatedIdentity, MembershipStatus
from forge.postgres import _EMPTY_CONTEXT, _ROLE_CHECK

# One statement observes identity, activity, revision and roles under one snapshot.
# Parameters and explicit composite joins complement (never replace) self-only RLS.
_SNAPSHOT = """
SELECT i.provider, i.issuer, i.subject, o.id, m.id, m.revision, m.status, o.active,
       coalesce(array_agg(r.role ORDER BY r.role) FILTER (WHERE r.role IS NOT NULL),
                ARRAY[]::text[])
FROM forge.identities AS i
JOIN forge.memberships AS m ON m.identity_id = i.id
JOIN forge.organizations AS o ON o.id = m.organization_id
LEFT JOIN forge.membership_roles AS r
  ON r.organization_id = m.organization_id AND r.membership_id = m.id
WHERE i.provider = %s AND i.issuer = %s AND i.subject = %s AND o.id = %s
  AND o.active AND m.status = 'active'
  AND (i.provider <> 'entra' OR (i.entra_tenant_id IS NOT NULL
       AND i.entra_object_id IS NOT NULL
       AND i.issuer = 'https://login.microsoftonline.com/' || i.entra_tenant_id::text || '/v2.0'
       AND i.subject = i.entra_object_id::text))
GROUP BY i.provider,i.issuer,i.subject,o.id,m.id,m.revision,m.status,o.active
"""


class AuthorizationStoreUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Authorization storage unavailable.")


class PostgresAuthorizationReader:
    """Read fresh trusted internal data, never raw client identity/roles.

    No credentials, owned pool, HTTP wiring, cache or mutation capability.
    Future writes must revalidate authority in their own audited transaction.
    """
    def __init__(self, pool: ConnectionPool, *, acquisition_timeout: float = 1.0):
        if (type(acquisition_timeout) not in (int, float)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError("Authorization acquisition timeout is invalid.")
        self._pool = pool
        self._acquisition_timeout = float(acquisition_timeout)

    def read(
        self, identity: AuthenticatedIdentity, organization_id: str,
    ) -> AuthorizationSnapshot | None:
        if not valid_identity(identity) or type(organization_id) is not str:
            return None
        try:
            requested = UUID(organization_id)
        except ValueError:
            return None
        try:
            with self._pool.connection(timeout=self._acquisition_timeout) as conn:
                # Before SQL: a nested savepoint would leak context into a caller.
                if (not conn.autocommit
                        or conn.info.transaction_status is not TransactionStatus.IDLE):
                    raise AuthorizationStoreUnavailable()
                with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '3s'")
                    cursor.execute("SET LOCAL lock_timeout = '1s'")
                    cursor.execute("SET LOCAL search_path = pg_catalog")
                    for query in (_EMPTY_CONTEXT, _ROLE_CHECK):
                        cursor.execute(query)
                        result = cursor.fetchone()
                        if result is None or result[0] is not True:
                            raise AuthorizationStoreUnavailable()
                    for key, value in (
                        ("organization", str(requested)), ("provider", identity.provider),
                        ("issuer", identity.issuer), ("subject", identity.subject),
                    ):
                        cursor.execute("SELECT set_config(%s,%s,true)", ("forge."+key, value))
                    cursor.execute(_SNAPSHOT, (identity.provider, identity.issuer,
                                               identity.subject, requested))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    provider, issuer, subject, org, member, revision, status, active, roles = row
                    if (AuthenticatedIdentity(provider, issuer, subject) != identity
                            or org != requested or type(roles) is not list):
                        return None
                    snapshot = AuthorizationSnapshot(identity, org, member, revision,
                        frozenset(roles), MembershipStatus(status), active)
                    return snapshot if valid_snapshot(snapshot) else None
        except Exception:
            # Do not preserve DB/DSN/identity text in error messages or causes.
            raise AuthorizationStoreUnavailable() from None
