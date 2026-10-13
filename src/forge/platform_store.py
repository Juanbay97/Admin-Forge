"""Platform persistence: the PostgreSQL adapter for ``forge.platform``.

Every call is a SECURITY DEFINER function of migration 0028 and later, run on the dedicated
``forge_platform_service`` pool, which holds no table or sequence privilege. Callers pass the session *digest*, never
the capability. The pool's role is checked on every borrow; every failure is one of the finite platform codes.
"""
from contextlib import contextmanager
import math

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_store import _KEYS, _ROLE
from forge.platform import (AuditEntry, Company, PlatformDenied, PlatformError, PlatformIdentity, PlatformInvalid,
                            PlatformUnavailable)

ROLE = 'forge_platform_service'
_MESSAGES = {'PLATFORM_DENIED': PlatformDenied, 'PLATFORM_INVALID': PlatformInvalid}


class PlatformConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid platform pool timeout.')
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise PlatformUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'%s'" % ROLE))
                    if cursor.fetchone() != (True,):
                        raise PlatformUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except PlatformError:
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message in _MESSAGES:
                    raise _MESSAGES[message]() from None
            raise PlatformUnavailable() from None


class PostgresPlatformStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def me(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_me(%s)', (digest,))
            row = cursor.fetchone()
            if row is None:
                raise PlatformUnavailable()
            return PlatformIdentity(*row)

    def companies(self, digest, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_list(%s,%s,%s)', (digest, after, page))
            return [Company(*row) for row in cursor.fetchall()]

    def company(self, digest, organization_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_get(%s,%s)', (digest, organization_id))
            row = cursor.fetchone()
            return None if row is None else Company(*row)

    def audit(self, digest, before, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_audit_page(%s,%s,%s)', (digest, before, page))
            return [AuditEntry(*row) for row in cursor.fetchall()]
