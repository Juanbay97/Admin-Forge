"""The member's signed effective policy: the layers of the member's company, resolved with the reported attestation level.

The database proves the session and the active membership of exactly that company on every call (``cap_read_layers``); this
service resolves the layers with the pure resolver and signs the result. Without a configured signing key nothing is issued
and the store is not even consulted (the routes answer 503).
"""
import time

from forge.capability_model import CapabilityInvalid, CapabilityUnavailable
from forge.capability_policy import MAX_LEVEL, resolve
from forge.capability_signing import LIFETIME_SECONDS, SCHEMA, timestamp
from forge.invitations import capability_digest


class EffectivePolicy:
    def __init__(self, store, signer=None, *, clock=time.time):
        self._store, self._signer, self._clock = store, signer, clock

    @property
    def configured(self):
        return self._signer is not None

    def keys(self):
        if self._signer is None:
            raise CapabilityUnavailable()
        return self._signer.keyset()

    def document(self, token, org, level):
        """``level`` is the client-reported attestation level: None (not reported) is 0; anything else must be an int in 0..4."""
        if self._signer is None:
            raise CapabilityUnavailable()
        if level is not None and (type(level) is not int or not 0 <= level <= MAX_LEVEL):
            raise CapabilityInvalid()
        reported = 0 if level is None else level
        snapshot = self._store.snapshot(capability_digest(token), org)
        now = self._clock()
        items = resolve(snapshot.entries, snapshot.platform, snapshot.company, snapshot.org, reported)
        return self._signer.sign({
            'schema': SCHEMA, 'org': str(org), 'platform_epoch': snapshot.platform_epoch, 'org_epoch': snapshot.org_epoch,
            'issued_at': timestamp(now), 'expires_at': timestamp(now + LIFETIME_SECONDS), 'reported_level': reported,
            'capabilities': [item.view() for item in items]})
