"""PostgreSQL adapter for ``forge.gateway_keys``: migration 0032 functions on the dedicated platform pool."""
import json

from psycopg import Error

from forge.gateway_keys import GatewayKeyInfo, KeyAssignment, ModelNotDiscovered
from forge.platform import PlatformUnavailable
from forge.platform_store import PlatformConnection


class PostgresGatewayKeyStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def _one(self, query, values):
        with self.connection.cursor() as cursor:
            cursor.execute(query, values)
            row = cursor.fetchone()
        if row is None:
            raise PlatformUnavailable()
        return GatewayKeyInfo(*row)

    def create(self, digest, key_id, label, origin, sealed, hint):
        return self._one('SELECT * FROM forge.platform_gateway_key_create(%s,%s,%s,%s,%s,%s)',
                         (digest, key_id, label, origin, sealed, hint))

    def keys(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_gateway_key_list(%s)', (digest,))
            return [GatewayKeyInfo(*row) for row in cursor.fetchall()]

    def rotate(self, digest, key_id, expected, sealed, hint):
        return self._one('SELECT * FROM forge.platform_gateway_key_rotate(%s,%s,%s,%s,%s)',
                         (digest, key_id, expected, sealed, hint))

    def set_status(self, digest, key_id, active):
        return self._one('SELECT * FROM forge.platform_gateway_key_set_status(%s,%s,%s)', (digest, key_id, active))

    def assignments(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_gateway_get(%s,%s)', (digest, org))
            return [KeyAssignment(*row) for row in cursor.fetchall()]

    def assign(self, digest, org, entries):
        document = json.dumps([{'key_id': str(key_id), 'priority': priority, 'active': active}
                               for key_id, priority, active in entries])
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_gateway_set(%s,%s,%s::jsonb)', (digest, org, document))
            return [KeyAssignment(*row) for row in cursor.fetchall()]

    def ceiling(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_model_access_get(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else row[0]

    def discovered(self, digest, org):
        """The current discovery of the company (the one matching its profile), or ``None`` while there is none."""
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_catalog_status(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else row[3]

    def set_ceiling(self, digest, org, models):
        with self.connection.cursor() as cursor:
            try:
                cursor.execute('SELECT forge.platform_company_model_access_set(%s,%s,%s)', (digest, org, models))
            except Error as error:
                if (getattr(error, 'sqlstate', None) == 'P0001'
                        and getattr(getattr(error, 'diag', None), 'message_primary', None) == 'MODEL_NOT_DISCOVERED'):
                    raise ModelNotDiscovered() from None
                raise
            return cursor.fetchone()[0]
