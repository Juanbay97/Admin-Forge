"""Function-only company usage reads through the existing gateway service pool (the directory authority's function)."""
from forge.directory_store import DirectoryConnection
from forge.usage_company import MemberUsage
from forge.usage_platform import Counters


class PostgresCompanyUsageStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = DirectoryConnection(pool, acquisition_timeout=acquisition_timeout)

    def members(self, digest, organization_id, first_day, last_day, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.usage_company_members(%s,%s,%s,%s,%s,%s)',
                           (digest, organization_id, first_day, last_day, after, page))
            return [MemberUsage(row[0], row[1], row[2], row[3], Counters(*row[4:])) for row in cursor.fetchall()]
