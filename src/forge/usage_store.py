"""Function-only usage recording on the gateway pool (migration 0035): the store never reads and never raises a database detail."""
from forge.gateway_configuration import GatewayUnavailable
from forge.gateway_configuration_store import GatewayConnection


class PostgresUsageStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = GatewayConnection(pool, acquisition_timeout=acquisition_timeout)

    def record(self, event):
        """True when the event was stored, False when its id was already recorded (an idempotent retry)."""
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.usage_record(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (event.organization_id, event.membership_id, event.event_id, event.alias, event.upstream_id,
                            event.key_id, event.prompt_tokens, event.completion_tokens, event.latency_ms, event.ttfb_ms,
                            event.status, event.error_code, event.source))
            row = cursor.fetchone()
        if row is None or type(row[0]) is not bool:
            raise GatewayUnavailable()
        return row[0]
