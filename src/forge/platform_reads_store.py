"""PostgreSQL adapter for the platform reads: migration 0043 (and later) functions on the dedicated platform pool."""
import json
from uuid import UUID

from forge.directory import Department
from forge.platform import PlatformUnavailable
from forge.platform_reads import DayUsage, Overview, PlatformMember, Previous
from forge.platform_store import PlatformConnection
from forge.usage_platform import Counters


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

    def overview(self, digest, first_day, last_day):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_overview(%s,%s,%s)', (digest, first_day, last_day))
            row = cursor.fetchone()
        if row is None:
            raise PlatformUnavailable()
        # (active companies, suspended, active people, 7 counters, then the previous period's 5 figures)
        return Overview(row[0], row[1], row[2], Counters(*row[3:10]), Previous(*row[10:15]))

    def days(self, digest, first_day, last_day):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_usage_days(%s,%s,%s)', (digest, first_day, last_day))
            return [DayUsage(row[0], Counters(*row[1:8]), row[8]) for row in cursor.fetchall()]
