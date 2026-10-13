"""PostgreSQL adapter for the platform usage service: migration 0036 (and later) functions on the dedicated platform pool."""
from forge.platform import PlatformUnavailable
from forge.platform_store import PlatformConnection
from forge.usage_platform import CompanyUsageRow, Counters, ModelPrice, ModelUsage, UsageTotals


class PostgresPlatformUsageStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def set_price(self, digest, upstream_id, input_micros, output_micros, effective_from):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_price_set(%s,%s,%s,%s,%s)',
                           (digest, upstream_id, input_micros, output_micros, effective_from))
            row = cursor.fetchone()
        if row is None:
            raise PlatformUnavailable()
        return ModelPrice(*row)

    def prices(self, digest, upstream_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_price_list(%s,%s)', (digest, upstream_id))
            return [ModelPrice(*row) for row in cursor.fetchall()]

    def by_company(self, digest, first_day, last_day, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_usage_by_company(%s,%s,%s,%s,%s)', (digest, first_day, last_day, after, page))
            return [CompanyUsageRow(row[0], row[1], row[2], Counters(*row[3:])) for row in cursor.fetchall()]

    def by_model(self, digest, first_day, last_day, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_usage_by_model(%s,%s,%s,%s,%s)', (digest, first_day, last_day, after, page))
            return [ModelUsage(row[0], Counters(*row[1:])) for row in cursor.fetchall()]

    def totals(self, digest, first_day, last_day):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_usage_totals(%s,%s,%s)', (digest, first_day, last_day))
            row = cursor.fetchone()
        if row is None:
            raise PlatformUnavailable()
        return UsageTotals(row[0], Counters(*row[1:]))
