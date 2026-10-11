"""Separate static owned-gateway administrator catalogue status profile; never trust-on-first-use."""
from forge.account_readiness import catalog_fingerprint, _SERVICE_PRIVILEGES
from forge.account_store import EnrollmentConnection
from forge.gateway_configuration_store import GatewayConnection
from forge.postgres import _ROLE_CHECK
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

# Authored build artifact from reviewed0001-5+0010-18 in owned PostgreSQL17.
# Captured from the owned PostgreSQL17.11 reviewed profile; never runtime learned.
_EXPECTED_SHA256 = '0b2ca67e63355d71f94961c85675375d962abf438c859b22dadbfde269c9a16a'


class GatewayCatalogAdminReadiness:
    def __init__(self, account_pool, bootstrap_pool, gateway_pool, *, acquisition_timeout=1.0):
        self._accounts = EnrollmentConnection(account_pool, acquisition_timeout=acquisition_timeout, role='forge_account_service')
        self._gateway = GatewayConnection(gateway_pool, acquisition_timeout=acquisition_timeout)
        self._bootstrap, self._timeout = bootstrap_pool, acquisition_timeout

    def check(self):
        if _EXPECTED_SHA256 is None:
            return False
        try:
            for connection in (self._accounts, self._gateway):
                with connection.cursor() as cursor:
                    cursor.execute(_SERVICE_PRIVILEGES + " AND current_setting('server_version_num')::integer BETWEEN 170000 AND 179999 AND (SELECT count(*)=2 AND bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname IN ('forge_gateway_authority','forge_catalog_authority'))")
                    if cursor.fetchone() != (True,) or catalog_fingerprint(cursor) != _EXPECTED_SHA256:
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
