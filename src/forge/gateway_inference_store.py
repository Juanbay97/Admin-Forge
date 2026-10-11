"""Function-only current member route resolution; transactions end before IO."""
from forge.gateway_configuration import GatewayRecord
from forge.gateway_configuration_store import GatewayConnection
from forge.gateway_inference import RouteContext


class PostgresGatewayInferenceStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = GatewayConnection(pool, acquisition_timeout=acquisition_timeout)

    def resolve(self, digest, organization_id, alias):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM forge.gateway_inference_route(%s,%s,%s)",
                           (digest, organization_id, alias))
            row = cursor.fetchone()
        if row is None or len(row) != 6:
            from forge.gateway_configuration import GatewayDenied
            raise GatewayDenied()
        revision, upstream, gateway_revision, binding, endpoint, cipher = row
        return RouteContext(organization_id, alias, revision, upstream,
                            GatewayRecord(gateway_revision, binding, endpoint, cipher))
