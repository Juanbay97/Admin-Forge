"""Static MVP readiness: attests exactly the reviewed 0001-0005+0010-0027 profile (F27).

Same shape as the retained 0018 profile checks, pinned to the latest MVP checkpoint
from ``forge.mvp_profile``; nothing is learned at runtime and any drift is not ready.
"""
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_readiness import catalog_fingerprint, _SERVICE_PRIVILEGES
from forge.account_store import EnrollmentConnection
from forge.gateway_configuration_store import GatewayConnection
from forge.mvp_profile import F27
from forge.postgres import _ROLE_CHECK

_AUTHORITIES = ("SELECT count(*)=4 AND bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN "
                "('forge_gateway_authority','forge_catalog_authority','forge_directory_authority','forge_branding_authority')")


class MvpReadiness:
    def __init__(self, account_pool, bootstrap_pool, gateway_pool, *, acquisition_timeout=1.0):
        self._accounts = EnrollmentConnection(account_pool, acquisition_timeout=acquisition_timeout,
                                              role='forge_account_service')
        self._gateway = GatewayConnection(gateway_pool, acquisition_timeout=acquisition_timeout)
        self._bootstrap, self._timeout = bootstrap_pool, acquisition_timeout

    def check(self):
        try:
            for connection in (self._accounts, self._gateway):
                with connection.cursor() as cursor:
                    cursor.execute(_SERVICE_PRIVILEGES + " AND current_setting('server_version_num')::integer "
                                   "BETWEEN 170000 AND 179999 AND (" + _AUTHORITIES + ")")
                    if cursor.fetchone() != (True,) or catalog_fingerprint(cursor) != F27:
                        return False
            with self._bootstrap.connection(timeout=self._timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    return False
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE_CHECK)
                    return cursor.fetchone() == (True,)
        except Exception:
            return False
