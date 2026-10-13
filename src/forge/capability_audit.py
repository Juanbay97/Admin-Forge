"""Tool-invocation metadata ingestion: a strict allow-list, validated before the store and again by the database.

The device reports who/what/when/outcome/duration/attestation level, never content. Any key outside the allow-list
(``arguments``, ``output``, a prompt, an error text) rejects the whole batch with no partial write.
"""
import re
from uuid import UUID

from forge.capability_model import CapabilityInvalid
from forge.invitations import capability_digest

MAX_BATCH = 100
MAX_DURATION_MS = 86_400_000
OUTCOMES = ('ok', 'error', 'denied', 'cancelled', 'timeout')
_REQUIRED = {'event_id', 'capability_id', 'at', 'outcome', 'duration_ms'}
_ALLOWED = _REQUIRED | {'sandbox_level'}
_CAPABILITY = re.compile(r'([a-z]+:)?[a-z0-9][a-z0-9._-]{0,127}')
_AT = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z')


def _int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise CapabilityInvalid()
    return value


def _event(item):
    if type(item) is not dict or set(item) - _ALLOWED or _REQUIRED - set(item):
        raise CapabilityInvalid()
    try:
        event_id = str(UUID(item['event_id'])) if type(item['event_id']) is str else None
    except ValueError:
        event_id = None
    capability, at, outcome = item['capability_id'], item['at'], item['outcome']
    if (event_id is None or type(capability) is not str or not _CAPABILITY.fullmatch(capability) or type(at) is not str
            or not _AT.fullmatch(at) or outcome not in OUTCOMES):
        raise CapabilityInvalid()
    normalized = {'event_id': event_id, 'capability_id': capability, 'at': at, 'outcome': outcome,
                  'duration_ms': _int(item['duration_ms'], 0, MAX_DURATION_MS)}
    if 'sandbox_level' in item:
        normalized['sandbox_level'] = _int(item['sandbox_level'], 0, 4)
    return normalized


class InvocationLog:
    def __init__(self, store):
        self._store = store

    def record(self, token, org, events):
        """The number of events stored (a replayed event id is not stored twice)."""
        if type(org) is not UUID or type(events) is not list or not 1 <= len(events) <= MAX_BATCH:
            raise CapabilityInvalid()
        return self._store.ingest(capability_digest(token), org, [_event(item) for item in events])
