"""Function-only directory access through the existing gateway service pool.

No table grant reaches this pool: every call is a SECURITY DEFINER function owned
by the NOLOGIN ``forge_directory_authority`` that re-validates the live session.
"""
from contextlib import contextmanager
import json
import math
from uuid import UUID
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from forge.account_store import _ROLE, _KEYS
from forge.directory import Department, MemberRow, DirectoryDenied, DirectoryUnavailable


class DirectoryConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid directory pool timeout.')
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise DirectoryUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'forge_gateway_service'"))
                    if cursor.fetchone() != (True,):
                        raise DirectoryUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except (DirectoryDenied, DirectoryUnavailable, ValueError):
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message == 'DIRECTORY_DENIED':
                    raise DirectoryDenied() from None
            raise DirectoryUnavailable() from None


def _departments(value):
    items = json.loads(value) if type(value) is str else value
    return tuple(Department(UUID(item['id']), item['name']) for item in items)


class PostgresDirectoryStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = DirectoryConnection(pool, acquisition_timeout=acquisition_timeout)

    def me(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.directory_me(%s)', (digest,))
            return [MemberRow(account, email, name, org, org_name, status, tuple(roles), _departments(departments))
                    for account, email, name, org, org_name, status, roles, departments in cursor.fetchall()]
