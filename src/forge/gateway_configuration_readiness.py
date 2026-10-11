"""Separate reviewed gateway-account schema profile; legacy pins remain unchanged."""
from forge.account_readiness import catalog_fingerprint,_SERVICE_PRIVILEGES
from forge.gateway_configuration_store import GatewayConnection
from forge.account_store import EnrollmentConnection
from forge.postgres import _ROLE_CHECK
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

# PostgreSQL17 normalized catalog, authored once from reviewed owned migration bytes.
# Captured from reviewed0001–4+0013–15 in owned PostgreSQL17.11; never runtime learned.
_EXPECTED_SHA256='5c5e2af1c728874e1478c5bb3c7d969f599908d75fad3f35fcd78bdfb25e68c7'

class GatewayAccountReadiness:
    def __init__(self,account_pool,bootstrap_pool,gateway_pool,*,acquisition_timeout=1.0):
        self._accounts=EnrollmentConnection(account_pool,acquisition_timeout=acquisition_timeout,role='forge_account_service')
        self._gateway=GatewayConnection(gateway_pool,acquisition_timeout=acquisition_timeout)
        self._bootstrap,self._timeout=bootstrap_pool,acquisition_timeout

    def check(self):
        if _EXPECTED_SHA256 is None: return False
        try:
            for connection in (self._accounts,self._gateway):
                with connection.cursor() as cursor:
                    cursor.execute(_SERVICE_PRIVILEGES+" AND (SELECT count(*)=1 AND bool_and(NOT rolcanlogin) FROM pg_roles WHERE rolname='forge_gateway_authority')")
                    if cursor.fetchone()!=(True,) or catalog_fingerprint(cursor)!=_EXPECTED_SHA256:
                        return False
            with self._bootstrap.connection(timeout=self._timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    return False
                with connection.transaction(),connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE_CHECK)
                    return cursor.fetchone()==(True,)
        except Exception: return False
