"""Dedicated function-only gateway pool, never an account-store role widening."""
from contextlib import contextmanager
import math
from psycopg.rows import tuple_row
from psycopg.pq import TransactionStatus
from forge.account_store import _ROLE,_KEYS
from forge.gateway_configuration import GatewayRecord,GatewayDenied,GatewayConflict,GatewayUnavailable

class GatewayConnection:
    def __init__(self,pool,*,acquisition_timeout=1.0):
        if type(acquisition_timeout) not in (int,float) or not math.isfinite(acquisition_timeout) or not 0<acquisition_timeout<=30:
            raise ValueError('Invalid gateway pool timeout.')
        self.pool,self.timeout=pool,float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise GatewayUnavailable()
                with connection.transaction(),connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'","'forge_gateway_service'"))
                    if cursor.fetchone()!=(True,): raise GatewayUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)",('forge.'+key,))
                    yield cursor
        except (GatewayDenied,GatewayConflict,GatewayUnavailable): raise
        except Exception as error:
            if getattr(error,'sqlstate',None)=='P0001':
                message=getattr(getattr(error,'diag',None),'message_primary',None)
                if message=='GATEWAY_DENIED': raise GatewayDenied() from None
                if message=='GATEWAY_CONFLICT': raise GatewayConflict() from None
            raise GatewayUnavailable() from None

class PostgresGatewayStore:
    def __init__(self,pool,*,acquisition_timeout=1.0):
        self.connection=GatewayConnection(pool,acquisition_timeout=acquisition_timeout)

    def read(self,digest,organization_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_read(%s,%s)',(digest,organization_id))
            row=cursor.fetchone()
            return None if row is None else GatewayRecord(*row)

    def save(self,digest,organization_id,expected_revision,binding_id,encrypted_key):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_save(%s,%s,%s,%s,%s)',
                (digest,organization_id,expected_revision,binding_id,encrypted_key))
            row=cursor.fetchone()
            if row is None: raise GatewayUnavailable()
            return GatewayRecord(*row)
