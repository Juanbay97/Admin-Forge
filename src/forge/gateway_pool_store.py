"""Pool-aware gateway stores for the MVP schema (migration 0033): routing candidates, the catalogue key and the status.

The retained 0015-0018 stores stay as they are for the retained demo profile; the composed MVP application uses these.
"""
from forge.gateway_catalog import Discovery
from forge.gateway_catalog_store import PostgresGatewayCatalogStore
from forge.gateway_configuration import GatewayDenied, GatewayRecord, GatewayUnavailable
from forge.gateway_configuration_store import GatewayConnection
from forge.gateway_inference import RouteContext


class PostgresPoolInferenceStore:
    """Resolves the route and every candidate key (lowest priority first) in one short transaction."""
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = GatewayConnection(pool, acquisition_timeout=acquisition_timeout)

    def resolve(self, digest, organization_id, alias):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_inference_candidates(%s,%s,%s)', (digest, organization_id, alias))
            rows = cursor.fetchall()
        if not rows:
            raise GatewayDenied()
        if any(len(row) != 8 or row[:4] != rows[0][:4] for row in rows):
            raise GatewayUnavailable()
        revision, upstream = rows[0][:2]
        records = [GatewayRecord(row[2], row[3], row[4], row[5], row[6], row[7]) for row in rows]
        return RouteContext(organization_id, alias, revision, upstream, records[0], tuple(records[1:]))


class PostgresPoolCatalogStore(PostgresGatewayCatalogStore):
    """Catalogue refresh and publish against the company profile and its top-priority usable key."""
    def gateway(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_key(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else GatewayRecord(*row)

    def discovery(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_discovery(%s,%s)', (digest, org))
            row = cursor.fetchone()
        if row is None:
            raise GatewayUnavailable()
        revision, binding, endpoint, cipher, key_id, key_revision, ids = row
        return Discovery(GatewayRecord(revision, binding, endpoint, cipher, key_id, key_revision), tuple(ids))
