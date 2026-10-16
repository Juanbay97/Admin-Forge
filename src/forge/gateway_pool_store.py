"""Pool-aware gateway stores for the MVP schema (migration 0033): routing candidates, the catalogue key and the status.

The retained 0015-0018 stores stay as they are for the retained demo profile; the composed MVP application uses these.
"""
from forge.gateway_catalog import Discovery
from forge.gateway_catalog_store import PostgresGatewayCatalogStore
from forge.gateway_configuration import GatewayDenied, GatewayManaged, GatewayRecord, GatewayStatus, GatewayUnavailable
from forge.gateway_configuration_store import GatewayConnection
from forge.gateway_inference import RouteContext
from forge.invitations import capability_digest

__all__ = ('GatewayManaged', 'PoolGatewayConfiguration', 'PostgresPoolCatalogStore', 'PostgresPoolInferenceStore',
           'PostgresPoolStatusStore')


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
        if any(len(row) != 9 or row[:4] != rows[0][:4] or row[8] != rows[0][8] for row in rows):
            raise GatewayUnavailable()
        revision, upstream = rows[0][:2]
        records = [GatewayRecord(row[2], row[3], row[4], row[5], row[6], row[7]) for row in rows]
        return RouteContext(organization_id, alias, revision, upstream, records[0], tuple(records[1:]), rows[0][8])


class PostgresPoolCatalogStore(PostgresGatewayCatalogStore):
    """Catalogue refresh and publish against the company profile and its top-priority usable key."""
    def gateway(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_key(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else GatewayRecord(*row)

    def ceiling(self, digest, org):
        """The platform ceiling of the administrator's company (migration 0049); ``None`` means unrestricted."""
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.gateway_catalog_ceiling(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else row[0]

    def discovery(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_catalog_discovery(%s,%s)', (digest, org))
            row = cursor.fetchone()
        if row is None:
            raise GatewayUnavailable()
        revision, binding, endpoint, cipher, key_id, key_revision, ids = row
        return Discovery(GatewayRecord(revision, binding, endpoint, cipher, key_id, key_revision), tuple(ids))


class PostgresPoolStatusStore:
    """The administrator's status: configured or not and how many platform keys are usable; nothing else."""
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = GatewayConnection(pool, acquisition_timeout=acquisition_timeout)

    def status(self, digest, organization_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.gateway_status(%s,%s)', (digest, organization_id))
            row = cursor.fetchone()
        if row is None or type(row[0]) is not bool or type(row[1]) is not int:
            raise GatewayUnavailable()
        return row


class PoolGatewayConfiguration:
    """Read-only ``GatewayConfiguration`` for the composed MVP application (same port the admin routes call).

    The pinned response shape is kept: ``revision`` carries the number of usable platform keys, ``endpoint`` is empty and
    no allow-list is offered, so an administrator learns nothing about origins, labels or key material. Saving is refused.
    """
    def __init__(self, store, allowed=frozenset()):
        self._store, self._allowed = store, allowed

    @property
    def allowed_endpoints(self):
        # Only what the route needs to decide that a PUT is well formed before refusing it; never shown to an administrator.
        return self._allowed

    def read(self, token, organization_id):
        configured, active = self._store.status(capability_digest(token), organization_id)
        return GatewayStatus('SAVED_UNVERIFIED' if configured else 'NOT_CONFIGURED', active, '')

    def save(self, token, organization_id, expected_revision, key, endpoint=None):
        raise GatewayManaged()
