"""PostgreSQL adapter for ``forge.platform_catalog``: migration 0048 functions on the dedicated platform pool."""
import json

from forge.platform import PlatformUnavailable
from forge.platform_catalog import CatalogKey, CatalogStatus
from forge.platform_store import PlatformConnection


class PostgresPlatformCatalogStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def keys(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_catalog_keys(%s,%s)', (digest, org))
            return [CatalogKey(*row) for row in cursor.fetchall()]

    def save_discovery(self, digest, org, revision, binding, ids):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_catalog_discovery_save(%s,%s,%s,%s,%s::jsonb)',
                           (digest, org, revision, binding, json.dumps(ids)))
            row = cursor.fetchone()
        if row is None or row[0] is None:
            raise PlatformUnavailable()
        return row[0]

    def status(self, digest, org):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_catalog_status(%s,%s)', (digest, org))
            row = cursor.fetchone()
        return None if row is None else CatalogStatus(*row)

    def publish(self, digest, org, operation, expected, gateway_revision, binding, mapping, default, payload, checksum, selection_sha):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_catalog_publish(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)',
                           (digest, org, operation, expected, gateway_revision, binding, json.dumps(mapping), default,
                            payload, checksum, selection_sha))
            row = cursor.fetchone()
        if row is None or type(row[0]) is not int:
            raise PlatformUnavailable()
        return row[0]
