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
               OR has_table_privilege(current_user,t.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_any_column_privilege(current_user,t.oid,'INSERT,UPDATE,REFERENCES')))
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
  AND (i.provider <> 'entra' OR (i.entra_tenant_id IS NOT NULL
       AND i.entra_object_id IS NOT NULL
       AND i.issuer = 'https://login.microsoftonline.com/' || i.entra_tenant_id::text || '/v2.0'
       AND i.subject = i.entra_object_id::text))
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


# Catalog-only structural prerequisites, not business row/count readiness or a
# substitute for migration orchestration/administrator auditing. No org GUC set.
_SCHEMA_CHECK = """
WITH expected(table_name, column_name, type_name, required) AS (
    VALUES ('identities','id','uuid',true),
           ('identities','provider','text',true),
           ('identities','issuer','text',true),
           ('identities','subject','text',true),
           ('identities','entra_tenant_id','uuid',false),
           ('identities','entra_object_id','uuid',false),
           ('organizations','id','uuid',true),
           ('organizations','slug','text',true),
           ('organizations','display_name','text',true),
           ('organizations','active','boolean',true),
           ('organizations','selected_config_revision','bigint',true),
           ('memberships','organization_id','uuid',true),
           ('memberships','id','uuid',true),
           ('memberships','identity_id','uuid',true),
           ('memberships','status','text',true),
           ('configuration_revisions','organization_id','uuid',true),
           ('configuration_revisions','revision','bigint',true)
)
SELECT NOT EXISTS (
    SELECT 1 FROM expected AS e
    LEFT JOIN pg_catalog.pg_namespace AS n ON n.nspname = 'forge'
    LEFT JOIN pg_catalog.pg_class AS t
        ON t.relnamespace = n.oid AND t.relname = e.table_name AND t.relkind = 'r'
    LEFT JOIN pg_catalog.pg_attribute AS a
        ON a.attrelid = t.oid AND a.attname = e.column_name AND NOT a.attisdropped
    WHERE a.attname IS NULL
       OR pg_catalog.format_type(a.atttypid,a.atttypmod) <> e.type_name
       OR a.attnotnull <> e.required
) AND EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint AS c
    WHERE c.conrelid = 'forge.identities'::regclass
      AND c.conname = 'entra_binding_consistent'
      AND c.contype = 'c' AND c.convalidated
      AND regexp_replace(pg_catalog.pg_get_expr(c.conbin,c.conrelid),
                         '[[:space:]]', '', 'g') = %s
) AND EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint AS c
    WHERE c.conrelid = 'forge.identities'::regclass
      AND c.conname = 'entra_binding_unique' AND c.contype = 'u' AND c.convalidated
      AND c.conkey = ARRAY[
          (SELECT attnum FROM pg_catalog.pg_attribute
           WHERE attrelid=c.conrelid AND attname='entra_tenant_id'),
          (SELECT attnum FROM pg_catalog.pg_attribute
           WHERE attrelid=c.conrelid AND attname='entra_object_id')]::smallint[]
) AND EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger AS g
    JOIN pg_catalog.pg_proc AS p ON p.oid=g.tgfoid
    JOIN pg_catalog.pg_namespace AS n ON n.oid=p.pronamespace
    WHERE g.tgrelid='forge.identities'::regclass
      AND g.tgname='entra_binding_write_once' AND g.tgenabled='O'
      AND NOT g.tgisinternal AND g.tgtype=19
      AND n.nspname='forge' AND p.proname='guard_entra_binding'
      AND NOT p.prosecdef AND p.proconfig=ARRAY['search_path=pg_catalog']
) AND NOT EXISTS (
    SELECT 1 FROM (VALUES ('context_ready'),('context_organization'),
                         ('has_membership'),('binding_identity')) AS e(name)
    LEFT JOIN pg_catalog.pg_namespace AS n ON n.nspname='forge'
    LEFT JOIN pg_catalog.pg_proc AS p ON p.pronamespace=n.oid AND p.proname=e.name
    WHERE p.oid IS NULL OR p.prosecdef OR p.proconfig IS DISTINCT FROM
        ARRAY['search_path=pg_catalog']
        OR (e.name <> 'binding_identity' AND NOT has_function_privilege(p.oid,'EXECUTE'))
) AND EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint AS c
    WHERE c.conrelid='forge.organizations'::regclass
      AND c.conname='selected_configuration' AND c.contype='f'
      AND c.confrelid='forge.configuration_revisions'::regclass
      AND c.convalidated AND c.condeferrable AND c.condeferred
) AND NOT EXISTS (
    SELECT 1 FROM (VALUES ('identities','identity_scope'),
        ('organizations','organization_scope'),('memberships','membership_scope'),
        ('configuration_revisions','configuration_scope'),
        ('identities','identity_binding_scope')) AS e(table_name,policy_name)
    LEFT JOIN pg_catalog.pg_namespace AS n ON n.nspname='forge'
    LEFT JOIN pg_catalog.pg_class AS t
        ON t.relnamespace=n.oid AND t.relname=e.table_name
    LEFT JOIN pg_catalog.pg_policy AS p ON p.polrelid=t.oid AND p.polname=e.policy_name
    WHERE p.oid IS NULL OR p.polqual IS NULL OR p.polwithcheck IS NULL
)
"""
_BINDING_CHECK = """(((entra_tenant_id IS NULL) AND (entra_object_id IS NULL))
OR ((entra_tenant_id IS NOT NULL) AND (entra_object_id IS NOT NULL)
AND (provider = 'entra'::text)
AND (issuer = (('https://login.microsoftonline.com/'::text ||
(entra_tenant_id)::text) || '/v2.0'::text))
AND (subject = (entra_object_id)::text)))"""
_BINDING_CHECK = ''.join(_BINDING_CHECK.split())
_EMPTY_CONTEXT = """
SELECT NOT EXISTS (
    SELECT 1 FROM unnest(ARRAY['forge.organization','forge.provider','forge.issuer',
        'forge.subject','forge.binding_identity','forge.binding_issuer',
        'forge.binding_tenant','forge.binding_object']) AS k
    WHERE coalesce(current_setting(k,true),'') <> '')
"""


class PostgresReadinessProbe:
    """Restricted-role/schema metadata only; errors return false, never diagnostics."""
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def check(self) -> bool:
        try:
            with self._pool.connection(timeout=1) as conn:
                if (not conn.autocommit
                    or conn.info.transaction_status is not TransactionStatus.IDLE):
                    return False
                with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '3s'")
                    cursor.execute("SET LOCAL lock_timeout = '1s'")
                    for query, params in ((_EMPTY_CONTEXT, None), (_ROLE_CHECK, None),
                                          (_SCHEMA_CHECK, (_BINDING_CHECK,))):
                        cursor.execute(query, params)
                        result = cursor.fetchone()
                        if result is None or result[0] is not True:
                            return False
                    return True
        except Exception:
            return False
