"""Function-only genuine owned-account catalogue database boundary."""
import json
from psycopg import IntegrityError
from forge.gateway_configuration import GatewayRecord, GatewayConflict, GatewayUnavailable
from forge.gateway_configuration_store import GatewayConnection, PostgresGatewayStore
from forge.gateway_catalog import Discovery


class PostgresGatewayCatalogStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = GatewayConnection(pool, acquisition_timeout=acquisition_timeout)
        self._gateways = PostgresGatewayStore(pool, acquisition_timeout=acquisition_timeout)

    def gateway(self, digest, org):
        return self._gateways.read(digest, org)

    def save_discovery(self, digest, org, gateway, ids):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.gateway_catalog_refresh(%s,%s,%s,%s,%s::jsonb)',
                (digest, org, gateway.revision, gateway.binding_id, json.dumps(ids)))

    def discovery(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_discovery(%s,%s)', (digest, org))
            row = cursor.fetchone()
        if row is None:
            raise GatewayUnavailable()
        revision, binding, endpoint, cipher, ids = row
        return Discovery(GatewayRecord(revision, binding, endpoint, cipher), tuple(ids))

    def publish(self, digest, org, operation, expected, discovery, mapping, default,
            payload, checksum, selection_sha):
        with self.connection.cursor() as cursor:
            try:
                cursor.execute('SELECT forge.gateway_catalog_publish(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)',
                    (digest, org, operation, expected, discovery.gateway.revision,
                     discovery.gateway.binding_id, json.dumps(mapping), default, payload, checksum, selection_sha))
                return cursor.fetchone()[0]
            except IntegrityError:
                raise GatewayConflict() from None

    def member_catalog(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_member(%s,%s)', (digest, org))
            return cursor.fetchone()

    def admin_status(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_admin_status(%s,%s)', (digest, org))
            row = cursor.fetchone()
        if row is None:
            raise GatewayUnavailable()
        return row
