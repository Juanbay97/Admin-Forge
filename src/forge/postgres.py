"""Transaction-scoped PostgreSQL bootstrap over an externally managed sync pool."""
from math import isfinite
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from forge.api import BootstrapRecords, valid_identity
from forge.foundation import (
    AuthenticatedIdentity, Membership, MembershipStatus, Organization,
    OrganizationConfiguration,
)

# Inspect live attributes on each borrow, not a cached role name alone. Restrict
# deployments to the role supplied by the one-shot bootstrap migration.
_ROLE_CHECK = """
SELECT current_user = 'forge_runtime' AND session_user = current_user
    AND NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole
             OR r.rolreplication)
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member = r.oid)
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'forge' AND t.relowner = r.oid)
    AND (SELECT count(*) = 4 AND bool_and(t.relrowsecurity AND t.relforcerowsecurity)
        FROM pg_catalog.pg_class AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'forge' AND t.relkind = 'r'
          AND t.relname IN ('identities','organizations','memberships','configuration_revisions'))
    AND NOT has_schema_privilege(current_user, 'forge', 'CREATE')
    AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
    AND NOT has_database_privilege(current_user, current_database(), 'CREATE')
    AND NOT has_database_privilege(current_user, current_database(), 'TEMP')
    AND current_setting('row_security') = 'on'
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'forge' AND t.relkind = 'r'
          AND (NOT has_table_privilege(current_user,t.oid,'SELECT')
               OR has_table_privilege(current_user,t.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')))
FROM pg_catalog.pg_roles AS r WHERE r.rolname = current_user
"""

# One statement snapshot prevents torn membership/config records. Explicit joins
# and parameters complement RLS; GUCs never substitute for validated identity.
_BOOTSTRAP = """
SELECT i.provider, i.issuer, i.subject, m.id, m.organization_id, m.status,
       o.id, o.slug, o.display_name, o.active, c.organization_id, c.revision
FROM forge.identities AS i
JOIN forge.memberships AS m ON m.identity_id = i.id
JOIN forge.organizations AS o ON o.id = m.organization_id
JOIN forge.configuration_revisions AS c
  ON c.organization_id = o.id AND c.revision = o.selected_config_revision
WHERE i.provider = %s AND i.issuer = %s AND i.subject = %s AND o.id = %s
  AND m.status IN ('active', 'suspended')
"""


class PostgresBootstrapReader:
    """Read fresh records; composition owns pool credentials, open/wait/close.

    Supply a synchronous pool whose connections are idle and autocommit=True.
    Every read borrows exactly one connection for an explicit outer transaction;
    no DSN, environment discovery, persistent session SET, cache or pool ownership.
    Caller supplies validated identity, not raw client identity fields. The DB
    deployment must also set bounded connection/statement timeouts; this adapter
    bounds acquisition, not an administrator's PostgreSQL execution policies.
    """
    def __init__(self, pool: ConnectionPool, *, acquisition_timeout: float = 1.0):
        if (isinstance(acquisition_timeout, bool)
            or not isinstance(acquisition_timeout, (int, float))
            or not isfinite(acquisition_timeout)
            or not 0 < acquisition_timeout <= 30):
            raise ValueError('Acquisition timeout must be finite and within (0, 30] seconds')
        self._pool = pool
        self._acquisition_timeout = float(acquisition_timeout)

    def read(
        self, identity: AuthenticatedIdentity, organization_id: str,
    ) -> BootstrapRecords | None:
        if not valid_identity(identity) or not isinstance(organization_id, str):
            return None
        try:
            requested = UUID(organization_id)
        except ValueError:
            return None

        with self._pool.connection(timeout=self._acquisition_timeout) as conn:
            # Must precede SQL: psycopg's implicit BEGIN can make transaction()
            # create only a SAVEPOINT and leave local GUCs in a parent's context.
            if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                raise RuntimeError('Bootstrap requires an idle autocommit connection')
            with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(_ROLE_CHECK)
                role = cursor.fetchone()
                if role is None or role[0] is not True:
                    raise RuntimeError('Bootstrap requires the restricted runtime role')
                for key, value in (
                    ('organization', str(requested)), ('provider', identity.provider),
                    ('issuer', identity.issuer), ('subject', identity.subject),
                ):
                    cursor.execute('SELECT set_config(%s, %s, true)', ('forge.' + key, value))
                cursor.execute(_BOOTSTRAP, (identity.provider, identity.issuer,
                                            identity.subject, requested))
                record = cursor.fetchone()
                if record is None:
                    return None
                (provider, issuer, subject, member_id, member_org, status, org_id,
                 slug, display_name, active, config_org, revision) = record
                stored_identity = AuthenticatedIdentity(provider, issuer, subject)
                if (stored_identity != identity or member_org != requested
                    or org_id != requested or config_org != requested
                    or not isinstance(revision, int) or revision <= 0):
                    return None
                return BootstrapRecords(
                    Membership(str(member_id), str(member_org), stored_identity,
                               MembershipStatus(status)),
                    Organization(str(org_id), slug, display_name, active),
                    OrganizationConfiguration(str(config_org), revision),
                )
