"""Explicit existing-identity binding; never login, onboarding or authorization."""
from dataclasses import dataclass, field
from math import isfinite
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from forge.entra import VerifiedPrincipal


@dataclass(frozen=True)
class IdentityBinding:
    """Successful internal binding. Deliberately no token or profile claims."""
    identity_id: UUID = field(repr=False)


class IdentityBindingUnavailable(RuntimeError):
    """Redacted operational failure; does not disclose database diagnostics."""


_ROLE_CHECK = """
SELECT current_user = 'forge_identity_binder' AND session_user = current_user
    AND NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication)
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member = r.oid)
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class t
        JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='forge' AND t.relowner=r.oid)
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname IN ('forge','public') AND nspowner=r.oid)
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='forge' AND p.proowner=r.oid)
    AND (SELECT count(*)=4 AND bool_and(t.relrowsecurity AND t.relforcerowsecurity)
        FROM pg_catalog.pg_class t JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='forge' AND t.relkind='r'
        AND t.relname IN ('identities','organizations','memberships','configuration_revisions'))
    AND NOT has_schema_privilege(current_user,'forge','CREATE')
    AND NOT has_schema_privilege(current_user,'public','CREATE')
    AND NOT has_database_privilege(current_user,current_database(),'CREATE')
    AND NOT has_database_privilege(current_user,current_database(),'TEMP')
    AND current_setting('row_security')='on'
    AND has_table_privilege(current_user,'forge.identities','SELECT')
    AND has_column_privilege(current_user,'forge.identities','entra_tenant_id','UPDATE')
    AND has_column_privilege(current_user,'forge.identities','entra_object_id','UPDATE')
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class t JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='forge' AND t.relkind='r'
        AND (has_table_privilege(current_user,t.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          OR has_any_column_privilege(current_user,t.oid,'INSERT,REFERENCES')
          OR (t.relname <> 'identities' AND
              has_any_column_privilege(current_user,t.oid,'SELECT,UPDATE'))))
    AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
        WHERE a.attrelid='forge.identities'::regclass AND a.attnum>0 AND NOT a.attisdropped
          AND a.attname NOT IN ('entra_tenant_id','entra_object_id')
          AND has_column_privilege(current_user,a.attrelid,a.attnum,'UPDATE'))
FROM pg_catalog.pg_roles r WHERE r.rolname=current_user
"""

_BIND = """
UPDATE forge.identities AS i SET entra_tenant_id=%s, entra_object_id=%s
WHERE i.id=%s AND i.provider='entra' AND i.issuer=%s AND i.subject=%s
  AND ((i.entra_tenant_id IS NULL AND i.entra_object_id IS NULL)
       OR (i.entra_tenant_id=%s AND i.entra_object_id=%s))
RETURNING i.id
"""


def _canonical_guid(value: object) -> UUID | None:
    if type(value) is not str or len(value) != 36:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value else None


class PostgresIdentityBinder:
    """Borrow an external restricted pool; bind only a trusted existing identity.

    VerifiedPrincipal is an internal trusted port produced after token validation,
    not cryptographic proof merely by constructing it. A trusted caller separately
    authorizes selection of the existing UUID. No public endpoint or bind-on-read.
    Connections must be idle autocommit. Acquisition is bounded; each transaction
    sets local lock/statement timeouts and local self-context. Pool ownership,
    connect timeout, credentials and LOGIN provisioning belong to composition.
    """

    def __init__(self, pool: ConnectionPool, *, acquisition_timeout: float = 1.0):
        if (type(acquisition_timeout) not in (int, float)
            or not 0 < acquisition_timeout <= 30 or not isfinite(acquisition_timeout)):
            raise ValueError('Acquisition timeout must be finite and within (0, 30] seconds')
        self._pool = pool
        self._acquisition_timeout = float(acquisition_timeout)

    def bind_existing(
        self, identity_id: UUID, principal: VerifiedPrincipal,
    ) -> IdentityBinding | None:
        # Validate shape at the internal boundary, not a substitute for verification.
        if type(identity_id) is not UUID or type(principal) is not VerifiedPrincipal:
            return None
        tid, oid = _canonical_guid(principal.tid), _canonical_guid(principal.oid)
        if (tid is None or oid is None or type(principal.issuer) is not str
            or principal.issuer != 'https://login.microsoftonline.com/' + str(tid) + '/v2.0'
            or type(principal.sub) is not str or not principal.sub.strip()
            or len(principal.sub) > 1024):
            return None
        try:
            with self._pool.connection(timeout=self._acquisition_timeout) as conn:
                if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                    raise IdentityBindingUnavailable('Identity binding unavailable')
                with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '1s'")
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
                    cursor.execute(_ROLE_CHECK)
                    role = cursor.fetchone()
                    if role is None or role[0] is not True:
                        raise IdentityBindingUnavailable('Identity binding unavailable')
                    for key, value in (
                        ('identity', str(identity_id)), ('issuer', principal.issuer),
                        ('tenant', str(tid)), ('object', str(oid)),
                    ):
                        cursor.execute('SELECT set_config(%s,%s,true)',
                                       ('forge.binding_' + key, value))
                    cursor.execute(_BIND, (tid, oid, identity_id, principal.issuer,
                                           str(oid), tid, oid))
                    record = cursor.fetchone()
                    if record is None:
                        return None
                    if record != (identity_id,):
                        raise IdentityBindingUnavailable('Identity binding unavailable')
                    return IdentityBinding(identity_id)
        except Exception:
            raise IdentityBindingUnavailable('Identity binding unavailable') from None
