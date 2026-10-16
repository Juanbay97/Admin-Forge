"""Platform-owned gateway key pool: sealed write-only keys, assignment with priority and the per-company model ceiling.

Authority is the database (a fresh verified platform owner on every call); this service only seals the key text
before any store call (format v2, bound to the key id, revision and origin), checks the origin against the deployment
allow-list, bounds the arguments and returns metadata that never includes key text.
"""
from dataclasses import dataclass
import re
from typing import Protocol
from uuid import UUID, uuid4

from forge.gateway_configuration import GatewayCipher, MAX_REVISION
from forge.invitations import capability_digest
from forge.platform import PlatformInvalid

LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}')
MODEL = re.compile(r'[!-~]{1,255}')
MAX_ASSIGNMENTS = 16
MAX_MODELS = 500
MAX_PRIORITY = 1000


class DiscoveryRequired(PlatformInvalid):
    """The ceiling is chosen from discovered models, and the company has no current discovery yet."""
    code = 'DISCOVERY_REQUIRED'
    message = 'Discover the models of the company keys before choosing the allowed ones.'


class ModelNotDiscovered(PlatformInvalid):
    """A ceiling entry is not among the models the company's keys were discovered to reach."""
    code = 'MODEL_NOT_DISCOVERED'
    message = 'A selected model was not discovered for this company.'


@dataclass(frozen=True)
class GatewayKeyInfo:
    """What a platform caller may see of a key; the sealed value and the key text never appear here."""
    id: UUID
    label: str
    origin: str
    revision: int
    status: str
    has_key: bool
    hint: str | None
    companies: int


@dataclass(frozen=True)
class KeyAssignment:
    key_id: UUID
    label: str
    origin: str
    priority: int
    active: bool
    key_status: str
    has_key: bool


class KeyStore(Protocol):
    def create(self, digest, key_id, label, origin, sealed, hint) -> GatewayKeyInfo: ...
    def keys(self, digest) -> list: ...
    def rotate(self, digest, key_id, expected, sealed, hint) -> GatewayKeyInfo: ...
    def set_status(self, digest, key_id, active) -> GatewayKeyInfo: ...
    def assignments(self, digest, org) -> list: ...
    def assign(self, digest, org, entries) -> list: ...
    def ceiling(self, digest, org) -> list | None: ...
    def discovered(self, digest, org) -> list | None: ...
    def set_ceiling(self, digest, org, models) -> list: ...


class GatewayKeys:
    def __init__(self, store: KeyStore, cipher: GatewayCipher):
        self._store, self._cipher = store, cipher

    @property
    def allowed_origins(self):
        return tuple(sorted(self._cipher.policy.allowed))

    def create(self, token, label, origin, key):
        """``key`` is write-only and optional: None stores a placeholder that is never routed."""
        if type(label) is not str or not LABEL.fullmatch(label) or (key is not None and type(key) is not str):
            raise PlatformInvalid()
        key_id = uuid4()
        sealed = hint = None
        try:
            if key is not None:
                sealed = self._cipher.seal_pooled(key_id, 1, key, origin)
                hint = key[-4:]
            else:
                self._cipher.policy.require(origin)
        except ValueError:
            raise PlatformInvalid() from None  # a rejected origin or credential is never echoed
        return self._store.create(capability_digest(token), key_id, label, origin, sealed, hint)

    def keys(self, token):
        return self._store.keys(capability_digest(token))

    def rotate(self, token, key_id, expected, key):
        if (type(key_id) is not UUID or type(expected) is not int or not 1 <= expected <= MAX_REVISION
                or type(key) is not str):
            raise PlatformInvalid()
        digest = capability_digest(token)
        known = next((item for item in self._store.keys(digest) if item.id == key_id), None)
        if known is None:
            raise PlatformInvalid()
        try:
            sealed = self._cipher.seal_pooled(key_id, expected + 1, key, known.origin)
        except ValueError:
            raise PlatformInvalid() from None
        return self._store.rotate(digest, key_id, expected, sealed, key[-4:])

    def set_status(self, token, key_id, active):
        if type(key_id) is not UUID or type(active) is not bool:
            raise PlatformInvalid()
        return self._store.set_status(capability_digest(token), key_id, active)

    def assignments(self, token, org):
        self._org(org)
        return self._store.assignments(capability_digest(token), org)

    def assign(self, token, org, entries):
        """Replace the company's whole assignment list: ``(key_id, priority, active)`` with unique priorities."""
        self._org(org)
        if type(entries) is not list or len(entries) > MAX_ASSIGNMENTS:
            raise PlatformInvalid()
        for entry in entries:
            if (type(entry) is not tuple or len(entry) != 3 or type(entry[0]) is not UUID or type(entry[1]) is not int
                    or not 1 <= entry[1] <= MAX_PRIORITY or type(entry[2]) is not bool):
                raise PlatformInvalid()
        if len({entry[0] for entry in entries}) != len(entries) or len({entry[1] for entry in entries}) != len(entries):
            raise PlatformInvalid()
        return self._store.assign(capability_digest(token), org, entries)

    def ceiling(self, token, org):
        self._org(org)
        return self._store.ceiling(capability_digest(token), org)

    def set_ceiling(self, token, org, models):
        """The ceiling is never free text: every entry must be among the models discovered for the company (migration 0049)."""
        self._org(org)
        if (type(models) is not list or len(models) > MAX_MODELS or len(set(models)) != len(models)
                or any(type(model) is not str or not MODEL.fullmatch(model) for model in models)):
            raise PlatformInvalid()
        digest = capability_digest(token)
        if models:  # the empty ceiling denies everything and so needs no discovery
            found = self._store.discovered(digest, org)
            if found is None:
                raise DiscoveryRequired()
            if not set(models) <= set(found):
                raise ModelNotDiscovered()
        return self._store.set_ceiling(digest, org, models)

    @staticmethod
    def _org(org):
        if type(org) is not UUID:
            raise PlatformInvalid()
