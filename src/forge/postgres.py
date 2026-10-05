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
    AND (SELECT count(*) = 5 AND bool_and(t.relrowsecurity AND t.relforcerowsecurity)
        FROM pg_catalog.pg_class AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'forge' AND t.relkind = 'r'
          AND t.relname IN ('identities','organizations','memberships','configuration_revisions','membership_roles'))
    AND NOT has_schema_privilege(current_user, 'forge', 'CREATE')
    AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
    AND NOT has_database_privilege(current_user, current_database(), 'CREATE')
    AND NOT has_database_privilege(current_user, current_database(), 'TEMP')
    AND current_setting('row_security') = 'on'
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'forge' AND t.relkind = 'r'
          AND (has_table_privilege(current_user,t.oid,'SELECT') IS DISTINCT FROM
                   (t.relname IN ('identities','organizations','memberships','configuration_revisions','membership_roles'))
               OR has_table_privilege(current_user,t.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_any_column_privilege(current_user,t.oid,'INSERT,UPDATE,REFERENCES')
               OR (t.relname NOT IN ('identities','organizations','memberships','configuration_revisions','membership_roles')
                   AND has_any_column_privilege(current_user,t.oid,'SELECT'))))
    AND NOT EXISTS (
        SELECT 1 FROM unnest(ARRAY['forge.designation_organization',
            'forge.designation_member','forge.designation_identity',
            'forge.designation_actor','forge.designation_request']) AS k
        WHERE coalesce(current_setting(k,true),'')<>'')
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
        'forge.binding_tenant','forge.binding_object','forge.designation_organization',
        'forge.designation_member','forge.designation_identity','forge.designation_actor','forge.designation_request']) AS k
    WHERE coalesce(current_setting(k,true),'') <> '')
"""


# Exact new metadata is checked separately so all existing schema proof stays intact.
_AUTHORIZATION_SCHEMA = """
WITH expected(table_name,column_name,type_name) AS (
    VALUES ('memberships','revision','int8'),
           ('membership_roles','organization_id','uuid'),
           ('membership_roles','membership_id','uuid'),('membership_roles','role','text')
)
SELECT NOT EXISTS (
    SELECT 1 FROM expected e
    LEFT JOIN pg_namespace n ON n.nspname='forge'
    LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.table_name
    LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attname=e.column_name
    LEFT JOIN pg_type y ON y.oid=a.atttypid
    WHERE a.attnum IS NULL OR a.attisdropped OR NOT a.attnotnull OR y.typname<>e.type_name
) AND EXISTS (
    SELECT 1 FROM pg_attrdef d JOIN pg_attribute a ON a.attrelid=d.adrelid AND a.attnum=d.adnum
    WHERE d.adrelid='forge.memberships'::regclass AND a.attname='revision'
      AND pg_get_expr(d.adbin,d.adrelid)='1'
) AND EXISTS (
    SELECT 1 FROM pg_constraint c WHERE c.conrelid='forge.memberships'::regclass
      AND c.conname='membership_revision_positive' AND c.contype='c' AND c.convalidated
      AND regexp_replace(pg_get_expr(c.conbin,c.conrelid),'[[:space:]]','','g')='(revision>0)'
) AND EXISTS (
    SELECT 1 FROM pg_constraint c WHERE c.conrelid='forge.membership_roles'::regclass
      AND c.conname='membership_roles_known' AND c.contype='c' AND c.convalidated
      AND regexp_replace(pg_get_expr(c.conbin,c.conrelid),'[[:space:]]','','g')=%s
) AND EXISTS (
    SELECT 1 FROM pg_constraint c WHERE c.conrelid='forge.membership_roles'::regclass
      AND c.conname='membership_roles_primary' AND c.contype='p'
      AND c.conkey=ARRAY[
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='organization_id'),
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='membership_id'),
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='role')]::smallint[]
) AND EXISTS (
    SELECT 1 FROM pg_constraint c WHERE c.conrelid='forge.membership_roles'::regclass
      AND c.conname='membership_roles_membership' AND c.contype='f' AND c.convalidated
      AND c.confrelid='forge.memberships'::regclass AND NOT c.condeferrable
      AND c.confdeltype='a' AND c.confupdtype='a'
      AND c.conkey=ARRAY[
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='organization_id'),
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='membership_id')]::smallint[]
      AND c.confkey=ARRAY[
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.confrelid AND attname='organization_id'),
        (SELECT attnum FROM pg_attribute WHERE attrelid=c.confrelid AND attname='id')]::smallint[]
) AND EXISTS (
    SELECT 1 FROM pg_class t WHERE t.oid='forge.membership_roles'::regclass
      AND t.relowner=(SELECT oid FROM pg_roles WHERE rolname='forge_migrator')
      AND NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(t.relacl,acldefault('r',t.relowner)))
                      WHERE grantee=0)
) AND (SELECT count(*)=1 FROM pg_policy WHERE polrelid='forge.membership_roles'::regclass
    AND ((SELECT oid FROM pg_roles WHERE rolname='forge_runtime')=ANY(polroles) OR 0=ANY(polroles)))
  AND EXISTS (
    SELECT 1 FROM pg_policy p WHERE p.polrelid='forge.membership_roles'::regclass
      AND p.polname='membership_role_scope' AND p.polcmd='r' AND p.polpermissive
      AND p.polroles=ARRAY[(SELECT oid FROM pg_roles WHERE rolname='forge_runtime')]
      AND p.polwithcheck IS NULL
      AND regexp_replace(pg_get_expr(p.polqual,p.polrelid),'[[:space:]]','','g')=%s
) AND NOT has_table_privilege('forge_identity_binder','forge.membership_roles',
    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
  AND NOT has_any_column_privilege('forge_identity_binder','forge.membership_roles',
    'SELECT,INSERT,UPDATE,REFERENCES')
  AND NOT has_column_privilege('forge_identity_binder','forge.memberships','revision',
    'SELECT,INSERT,UPDATE,REFERENCES')
"""
_ROLE_VALUES_CHECK = """(role = ANY (ARRAY['organization_admin'::text,
'department_manager'::text,'skill_reviewer'::text,'member'::text]))"""
_ROLE_VALUES_CHECK = ''.join(_ROLE_VALUES_CHECK.split())
_ROLE_SCOPE_CHECK = """((organization_id = forge.context_organization())
AND (EXISTS ( SELECT 1 FROM ((forge.memberships m JOIN forge.organizations o
ON ((o.id = m.organization_id))) JOIN forge.identities i ON ((i.id = m.identity_id)))
WHERE ((m.organization_id = membership_roles.organization_id)
AND (m.id = membership_roles.membership_id) AND (m.status = 'active'::text)
AND o.active AND ((i.provider <> 'entra'::text) OR ((i.entra_tenant_id IS NOT NULL)
AND (i.entra_object_id IS NOT NULL) AND (i.issuer =
(('https://login.microsoftonline.com/'::text || (i.entra_tenant_id)::text) || '/v2.0'::text))
AND (i.subject = (i.entra_object_id)::text)))))))"""
_ROLE_SCOPE_CHECK = ''.join(_ROLE_SCOPE_CHECK.split())


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
                    # Stabilize catalog expression rendering across supplied search paths.
                    cursor.execute("SET LOCAL search_path = pg_catalog")
                    for query, params in ((_EMPTY_CONTEXT, None), (_ROLE_CHECK, None),
                                          (_SCHEMA_CHECK, (_BINDING_CHECK,)),
                                          (_AUTHORIZATION_SCHEMA, (_ROLE_VALUES_CHECK, _ROLE_SCOPE_CHECK)),
                                          (_DESIGNATION_SCHEMA, _DESIGNATION_FUNCTION_SOURCES)):
                        cursor.execute(query, params)
                        result = cursor.fetchone()
                        if result is None or result[0] is not True:
                            return False
                    return True
        except Exception:
            return False


# Dedicated write role: never accepted by ordinary runtime readers.
_DESIGNATOR_CHECK = """
SELECT current_user='forge_designator' AND session_user=current_user
AND NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication)
AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid)
AND NOT EXISTS(SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='forge' AND t.relowner=r.oid)
AND NOT has_schema_privilege(current_user,'forge','CREATE')
AND NOT has_schema_privilege(current_user,'public','CREATE')
AND NOT has_database_privilege(current_user,current_database(),'CREATE,TEMP')
AND current_setting('row_security')='on'
AND NOT EXISTS(
 SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
 WHERE n.nspname='forge' AND t.relkind='r' AND (
 has_table_privilege(current_user,t.oid,'SELECT') IS DISTINCT FROM
     (t.relname IN ('identities','organizations','memberships','membership_roles','initial_admin_designations','initial_admin_outbox'))
 OR has_table_privilege(current_user,t.oid,'INSERT') IS DISTINCT FROM
     (t.relname IN ('membership_roles','initial_admin_designations','initial_admin_outbox'))
 OR has_table_privilege(current_user,t.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
 OR has_any_column_privilege(current_user,t.oid,'REFERENCES')
 OR EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped
     AND (has_column_privilege(current_user,t.oid,a.attnum,'UPDATE') IS DISTINCT FROM
             (t.relname='memberships' AND a.attname='revision')
          OR (t.relname NOT IN ('membership_roles','initial_admin_designations','initial_admin_outbox')
              AND has_column_privilege(current_user,t.oid,a.attnum,'INSERT'))
          OR (t.relname NOT IN ('identities','organizations','memberships','membership_roles','initial_admin_designations','initial_admin_outbox')
              AND has_column_privilege(current_user,t.oid,a.attnum,'SELECT'))))))
FROM pg_roles r WHERE r.rolname=current_user
"""


# Exact observed PostgreSQL17 deparse of the reviewed0004 schema, not ambient metadata.
_DESIGNATION_FUNCTION_SOURCES = (
    """
    SELECT CASE WHEN key IN ('organization','member','identity','actor','request')
        AND current_setting('forge.designation_' || key, true) ~
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('forge.designation_' || key, true)::uuid ELSE NULL END
""",
    """
    SELECT organization = forge.designation_uuid('organization')
        AND (member IS NULL OR member = forge.designation_uuid('member'))
        AND (actor IS NULL OR actor = forge.designation_uuid('actor'))
        AND (request IS NULL OR request = forge.designation_uuid('request'))
""",
    """
    SELECT EXISTS (SELECT 1 FROM forge.memberships AS m
        JOIN forge.identities AS i ON i.id=m.identity_id
        WHERE m.organization_id=organization AND m.id=member AND m.status='active'
          AND i.provider='entra' AND i.entra_tenant_id IS NOT NULL
          AND i.entra_object_id IS NOT NULL
          AND i.issuer='https://login.microsoftonline.com/' || i.entra_tenant_id::text || '/v2.0'
          AND i.subject=i.entra_object_id::text)
""",
)

_DESIGNATION_SCHEMA = """
WITH columns_expected(table_name,column_name,type_name,not_null,default_expr) AS (VALUES
        ('initial_admin_designations','organization_id','uuid',true,''),
        ('initial_admin_designations','membership_id','uuid',true,''),
        ('initial_admin_designations','request_id','uuid',true,''),
        ('initial_admin_designations','actor_id','uuid',true,''),
        ('initial_admin_designations','target_tenant_id','uuid',true,''),
        ('initial_admin_designations','expected_revision','bigint',true,''),
        ('initial_admin_designations','revision','bigint',true,''),
        ('initial_admin_designations','event_id','uuid',true,''),
        ('initial_admin_outbox','event_id','uuid',true,''),
        ('initial_admin_outbox','schema_version','integer',true,''),
        ('initial_admin_outbox','organization_id','uuid',true,''),
        ('initial_admin_outbox','actor_id','uuid',true,''),
        ('initial_admin_outbox','actor_type','text',true,''),
        ('initial_admin_outbox','source','text',true,''),
        ('initial_admin_outbox','event_type','text',true,''),
        ('initial_admin_outbox','occurred_at','timestamp with time zone',true,'transaction_timestamp()'),
        ('initial_admin_outbox','received_at','timestamp with time zone',true,'transaction_timestamp()'),
        ('initial_admin_outbox','request_id','uuid',true,''),
        ('initial_admin_outbox','resource_type','text',true,''),
        ('initial_admin_outbox','resource_id','uuid',true,''),
        ('initial_admin_outbox','outcome','text',true,''),
        ('initial_admin_outbox','previous_revision','bigint',true,''),
        ('initial_admin_outbox','revision','bigint',true,''),
        ('initial_admin_outbox','metadata','jsonb',true,'')),
constraints_expected(table_name,constraint_name,definition,validated) AS (VALUES
        ('initial_admin_designations','designation_committed_event','FOREIGN KEY (event_id) REFERENCES forge.initial_admin_outbox(event_id) DEFERRABLE INITIALLY DEFERRED',true),
        ('initial_admin_designations','designation_event_payload','UNIQUE (organization_id, request_id, event_id, actor_id, membership_id, expected_revision, revision)',true),
        ('initial_admin_designations','designation_member','FOREIGN KEY (organization_id, membership_id) REFERENCES forge.memberships(organization_id, id)',true),
        ('initial_admin_designations','initial_admin_designations_check','CHECK ((revision = (expected_revision + 1)))',true),
        ('initial_admin_designations','initial_admin_designations_event_id_key','UNIQUE (event_id)',true),
        ('initial_admin_designations','initial_admin_designations_expected_revision_check','CHECK (((expected_revision > 0) AND (expected_revision < ''9223372036854775807''::bigint)))',true),
        ('initial_admin_designations','initial_admin_designations_organization_id_fkey','FOREIGN KEY (organization_id) REFERENCES forge.organizations(id)',true),
        ('initial_admin_designations','initial_admin_designations_pkey','PRIMARY KEY (organization_id)',true),
        ('initial_admin_designations','initial_admin_designations_request_id_key','UNIQUE (request_id)',true),
        ('initial_admin_outbox','designation_event_record','FOREIGN KEY (organization_id, request_id, event_id, actor_id, resource_id, previous_revision, revision) REFERENCES forge.initial_admin_designations(organization_id, request_id, event_id, actor_id, membership_id, expected_revision, revision)',true),
        ('initial_admin_outbox','initial_admin_outbox_actor_type_check','CHECK ((actor_type = ''deployment_operator''::text))',true),
        ('initial_admin_outbox','initial_admin_outbox_check','CHECK ((metadata = jsonb_build_object(''role'', ''organization_admin'', ''previous_revision'', previous_revision, ''revision'', revision)))',true),
        ('initial_admin_outbox','initial_admin_outbox_event_type_check','CHECK ((event_type = ''membership.initial_admin_designated''::text))',true),
        ('initial_admin_outbox','initial_admin_outbox_outcome_check','CHECK ((outcome = ''succeeded''::text))',true),
        ('initial_admin_outbox','initial_admin_outbox_pkey','PRIMARY KEY (event_id)',true),
        ('initial_admin_outbox','initial_admin_outbox_request_id_key','UNIQUE (request_id)',true),
        ('initial_admin_outbox','initial_admin_outbox_resource_type_check','CHECK ((resource_type = ''membership''::text))',true),
        ('initial_admin_outbox','initial_admin_outbox_schema_version_check','CHECK ((schema_version = 1))',true),
        ('initial_admin_outbox','initial_admin_outbox_source_check','CHECK ((source = ''server''::text))',true)),
policies_expected(table_name,policy_name,command,permissive,using_expr,check_expr) AS (VALUES
        ('identities','designation_identity','r',true,'((id = forge.designation_uuid(''identity''::text)) AND (provider = ''entra''::text) AND (entra_tenant_id IS NOT NULL) AND (entra_object_id IS NOT NULL) AND (issuer = ((''https://login.microsoftonline.com/''::text || (entra_tenant_id)::text) || ''/v2.0''::text)) AND (subject = (entra_object_id)::text))',''),
        ('initial_admin_designations','designation_record_insert','a',true,'','forge.designation_scope(organization_id, membership_id, actor_id, request_id)'),
        ('initial_admin_designations','designation_record_read','r',true,'forge.designation_scope(organization_id, membership_id, actor_id, request_id)',''),
        ('initial_admin_outbox','designation_event_insert','a',true,'','forge.designation_scope(organization_id, resource_id, actor_id, request_id)'),
        ('initial_admin_outbox','designation_event_read','r',true,'forge.designation_scope(organization_id, resource_id, actor_id, request_id)',''),
        ('membership_roles','designation_admin_insert','a',true,'','(forge.designation_scope(organization_id, membership_id, NULL::uuid, NULL::uuid) AND (role = ''organization_admin''::text) AND forge.designation_bound_member(organization_id, membership_id))'),
        ('membership_roles','designation_admin_read','r',true,'(forge.designation_scope(organization_id, NULL::uuid, NULL::uuid, NULL::uuid) AND (role = ''organization_admin''::text))',''),
        ('memberships','designation_member_allow','r',true,'(forge.designation_scope(organization_id, id, NULL::uuid, NULL::uuid) AND (status = ''active''::text))',''),
        ('memberships','designation_member_limit','*',false,'(forge.designation_scope(organization_id, id, NULL::uuid, NULL::uuid) AND (status = ''active''::text))','(forge.designation_scope(organization_id, id, NULL::uuid, NULL::uuid) AND (status = ''active''::text))'),
        ('memberships','designation_revision','w',true,'(forge.designation_scope(organization_id, id, NULL::uuid, NULL::uuid) AND (status = ''active''::text))','(forge.designation_scope(organization_id, id, NULL::uuid, NULL::uuid) AND (status = ''active''::text) AND forge.designation_bound_member(organization_id, id))'),
        ('organizations','designation_org_allow','r',true,'forge.designation_scope(id, NULL::uuid, NULL::uuid, NULL::uuid)',''),
        ('organizations','designation_org_limit','r',false,'forge.designation_scope(id, NULL::uuid, NULL::uuid, NULL::uuid)','')),
functions_expected(function_name,source,argument_types,return_type) AS (VALUES
        ('designation_uuid',%s,'text','uuid'),
        ('designation_scope',%s,'uuid, uuid, uuid, uuid','boolean'),
        ('designation_bound_member',%s,'uuid, uuid','boolean'))
SELECT
(SELECT count(*)=7 AND bool_and(c.relrowsecurity AND c.relforcerowsecurity
    AND pg_get_userbyid(c.relowner)='forge_migrator') FROM pg_class c JOIN pg_namespace n
    ON n.oid=c.relnamespace WHERE n.nspname='forge' AND c.relname IN
    ('identities','organizations','memberships','configuration_revisions','membership_roles',
     'initial_admin_designations','initial_admin_outbox') AND c.relkind='r')
AND NOT EXISTS(
 SELECT 1 FROM columns_expected e LEFT JOIN pg_namespace n ON n.nspname='forge'
 LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.table_name
 LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attname=e.column_name AND NOT a.attisdropped
 LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum
 WHERE a.attnum IS NULL OR a.atttypid<>e.type_name::regtype OR a.attnotnull<>e.not_null
 OR coalesce(pg_get_expr(d.adbin,d.adrelid),'')<>e.default_expr)
AND (SELECT count(*)=24 FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid
 JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='forge'
 AND t.relname IN ('initial_admin_designations','initial_admin_outbox')
 AND a.attnum>0 AND NOT a.attisdropped)
AND NOT EXISTS(
 SELECT 1 FROM constraints_expected e LEFT JOIN pg_namespace n ON n.nspname='forge'
 LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.table_name
 LEFT JOIN pg_constraint k ON k.conrelid=t.oid AND k.conname=e.constraint_name
 WHERE k.oid IS NULL OR k.convalidated IS DISTINCT FROM e.validated
 OR pg_get_constraintdef(k.oid) IS DISTINCT FROM e.definition)
AND (SELECT count(*)=19 FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid
 JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='forge'
 AND t.relname IN ('initial_admin_designations','initial_admin_outbox'))
AND NOT EXISTS(
 SELECT 1 FROM policies_expected e LEFT JOIN pg_namespace n ON n.nspname='forge'
 LEFT JOIN pg_class t ON t.relnamespace=n.oid AND t.relname=e.table_name
 LEFT JOIN pg_policy p ON p.polrelid=t.oid AND p.polname=e.policy_name
 WHERE p.oid IS NULL OR p.polcmd::text<>e.command OR p.polpermissive<>e.permissive
 OR p.polroles IS DISTINCT FROM ARRAY[(SELECT oid FROM pg_roles WHERE rolname='forge_designator')]
 OR coalesce(pg_get_expr(p.polqual,p.polrelid),'') IS DISTINCT FROM e.using_expr
 OR coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'') IS DISTINCT FROM e.check_expr)
AND NOT EXISTS(
 SELECT 1 FROM (VALUES ('identities',3),('organizations',3),('memberships',4),
 ('configuration_revisions',1),('membership_roles',3),('initial_admin_designations',2),
 ('initial_admin_outbox',2)) e(name,policy_count)
 WHERE (SELECT count(*) FROM pg_policy p JOIN pg_class t ON t.oid=p.polrelid
 JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='forge' AND t.relname=e.name)<>e.policy_count)
AND NOT EXISTS(
 SELECT 1 FROM functions_expected e LEFT JOIN pg_namespace n ON n.nspname='forge'
 LEFT JOIN pg_proc f ON f.pronamespace=n.oid AND f.proname=e.function_name
 WHERE f.oid IS NULL OR f.prosecdef OR f.provolatile<>'s' OR f.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog']
 OR pg_get_userbyid(f.proowner)<>'forge_migrator'
 OR btrim(f.prosrc,chr(10)||chr(13)||' ') IS DISTINCT FROM btrim(e.source,chr(10)||chr(13)||' ')
 OR oidvectortypes(f.proargtypes) IS DISTINCT FROM e.argument_types
 OR format_type(f.prorettype,NULL) IS DISTINCT FROM e.return_type
 OR f.pronargdefaults<>0 OR f.provariadic<>0
 OR (SELECT lanname FROM pg_language WHERE oid=f.prolang) IS DISTINCT FROM 'sql'
 OR NOT has_function_privilege('forge_designator',f.oid,'EXECUTE')
 OR has_function_privilege('forge_runtime',f.oid,'EXECUTE')
 OR has_function_privilege('forge_identity_binder',f.oid,'EXECUTE')
 OR EXISTS(SELECT 1 FROM aclexplode(f.proacl) a WHERE a.grantee=0))
AND (SELECT count(*)=3 FROM pg_proc f JOIN pg_namespace n ON n.oid=f.pronamespace
 WHERE n.nspname='forge' AND f.proname LIKE 'designation_%%')
AND NOT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname='forge_designator'
 AND (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication))
AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname='forge_designator')
AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='forge_designator'))
AND NOT has_schema_privilege('forge_designator','forge','CREATE')
AND NOT has_schema_privilege('forge_designator','public','CREATE')
AND NOT has_database_privilege('forge_designator',current_database(),'CREATE,TEMP')
AND NOT EXISTS(SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
 WHERE n.nspname='forge' AND (t.relowner=(SELECT oid FROM pg_roles WHERE rolname='forge_designator')
 OR (t.relname IN ('initial_admin_designations','initial_admin_outbox') AND
    (has_table_privilege('forge_runtime',t.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
     OR has_any_column_privilege('forge_runtime',t.oid,'SELECT,INSERT,UPDATE,REFERENCES')
     OR has_table_privilege('forge_identity_binder',t.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
     OR has_any_column_privilege('forge_identity_binder',t.oid,'SELECT,INSERT,UPDATE,REFERENCES')
     OR EXISTS(SELECT 1 FROM aclexplode(t.relacl) a WHERE a.grantee=0)))))
AND NOT EXISTS(
 SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
 WHERE n.nspname='forge' AND t.relkind='r' AND (
 has_table_privilege('forge_designator',t.oid,'SELECT') IS DISTINCT FROM
     (t.relname IN ('identities','organizations','memberships','membership_roles','initial_admin_designations','initial_admin_outbox'))
 OR has_table_privilege('forge_designator',t.oid,'INSERT') IS DISTINCT FROM
     (t.relname IN ('membership_roles','initial_admin_designations','initial_admin_outbox'))
 OR has_table_privilege('forge_designator',t.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
 OR has_any_column_privilege('forge_designator',t.oid,'REFERENCES')
 OR EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped
     AND (has_column_privilege('forge_designator',t.oid,a.attnum,'UPDATE') IS DISTINCT FROM
             (t.relname='memberships' AND a.attname='revision')
          OR (t.relname NOT IN ('membership_roles','initial_admin_designations','initial_admin_outbox')
              AND has_column_privilege('forge_designator',t.oid,a.attnum,'INSERT'))
          OR (t.relname NOT IN ('identities','organizations','memberships','membership_roles','initial_admin_designations','initial_admin_outbox')
              AND has_column_privilege('forge_designator',t.oid,a.attnum,'SELECT'))))))
"""
