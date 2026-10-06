"""Append to the caller's authorized transaction; never borrow or commit a pool."""
from psycopg.pq import TransactionStatus
from forge.outbox import Event


class OutboxUnavailable(Exception):
    """Fixed operational error; database diagnostics are never public."""


def record_event(connection, event: Event) -> None:
    """INSERT only, with no conflict suppression or RETURNING privilege requirement.

    Trusted composition supplies tenant context and the transaction that mutates
    the resource. No routes or consumers are enabled by this primitive.
    """
    try:
        if type(event) is not Event or connection.info.transaction_status is not TransactionStatus.INTRANS:
            raise ValueError('Transaction and event required')
        connection.execute('INSERT INTO forge.outbox_events '
            '(event_id,organization_id,actor_id,request_id,resource_id,event_type,previous_revision,revision) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (event.event_id, event.organization_id, event.actor_id, event.request_id,
             event.resource_id, event.event_type, event.previous_revision, event.revision))
    except Exception:
        raise OutboxUnavailable('Outbox recording unavailable') from None
