"""PostgreSQL adapter for the platform reads: migration 0043 (and later) functions on the dedicated platform pool."""
import json
from uuid import UUID

from forge.directory import Department
from forge.platform_reads import PlatformMember
from forge.platform_store import PlatformConnection


def _departments(value):
    items = json.loads(value) if type(value) is str else value
    return tuple(Department(UUID(item['id']), item['name']) for item in items)


class PostgresPlatformReadsStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def members(self, digest, organization_id, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_members(%s,%s,%s,%s)', (digest, organization_id, after, page))
            return [PlatformMember(row[0], row[1], row[2], row[3], tuple(row[4]), _departments(row[5])) for row in cursor.fetchall()]
