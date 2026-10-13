"""The connector broker's application service: the member's status, the administrators' write-only credentials and the platform default.

Authority is the database (the live session, the active membership of exactly that company, an administrator or a fresh verified
platform owner, on every call). This service bounds arguments, seals secrets bound to company/scope/connector/revision before any store
call, and returns only metadata: a credential's status, last-four hint and revision, never its value.
"""
from dataclasses import dataclass
import re
from uuid import UUID

from forge.connector_cipher import Binding, hint
from forge.connector_model import BrokerInvalid
from forge.connector_oauth import PLATFORM
from forge.invitations import capability_digest

_CONNECTOR = re.compile(r'connector:[a-z0-9][a-z0-9._-]{0,127}')
MAX_REVISION = 2 ** 63 - 3
_FIELDS = {'api_key': ({'api_key'}, {'api_key'}), 'oauth_client': ({'client_id'}, {'client_id', 'client_secret'})}


@dataclass(frozen=True)
class MemberConnector:
    """One connector as the member sees it. ``status`` is ``not_connected``, ``connected``, ``reauth_required``, ``disabled`` or
    ``client_side`` (a stdio connector whose credentials never leave the device)."""
    id: str
    name: str
    category: str
    transport: str
    auth: str
    state: str
    status: str
    configured: bool


def connector_id(value):
    if type(value) is not str or not _CONNECTOR.fullmatch(value):
        raise BrokerInvalid()
    return value


def _org(org):
    if type(org) is not UUID:
        raise BrokerInvalid()
    return org


def _secret(kind, fields):
    """The sealed payload for a credential kind from the request fields (exact keys, non-empty strings)."""
    if kind not in _FIELDS or type(fields) is not dict:
        raise BrokerInvalid()
    required, allowed = _FIELDS[kind]
    if not required <= set(fields) or set(fields) - allowed or any(type(value) is not str or not 1 <= len(value) <= 2048 for value in fields.values()):
        raise BrokerInvalid()
    return dict(fields)


class Connectors:
    def __init__(self, store, cipher):
        self._store, self._cipher = store, cipher

    def status(self, token, org):
        items = []
        for item in self._store.status(capability_digest(token), _org(org)):
            attributes = item.attributes
            if item.credential_locus != 'server':
                status = 'client_side'
            elif item.state != 'on':
                status = 'disabled'
            else:
                status = item.grant_status or 'not_connected'
            configured = item.credential_locus == 'server' and (attributes.get('auth') == 'oauth' and item.credential_kind == 'oauth_client'
                                                                or attributes.get('auth') == 'api_key' and item.credential_kind == 'api_key')
            items.append(MemberConnector(item.id, str(attributes.get('name', item.id)), str(attributes.get('category', '')), str(attributes.get('transport', '')),
                                         str(attributes.get('auth', '')), item.state, status, bool(configured)))
        return items

    # -- company administrator: write-only credentials ---------------------------------------------------------------------------
    def credential_set(self, token, org, identifier, kind, fields, expected):
        """Seal the secret for the NEXT revision and store it; the response is the revision, the hint and the kind."""
        digest, org, identifier = capability_digest(token), _org(org), connector_id(identifier)
        if type(expected) is not int or not 0 <= expected <= MAX_REVISION:
            raise BrokerInvalid()
        secret = _secret(kind, fields)
        sealed = self._cipher.seal(Binding(org, 'org', '', identifier, expected + 1), secret)
        return self._store.credential_save(digest, org, identifier, kind, expected, sealed, hint(secret.get('api_key') or secret.get('client_secret')))

    def credential_clear(self, token, org, identifier, expected):
        if type(expected) is not int or not 1 <= expected <= MAX_REVISION:
            raise BrokerInvalid()
        return self._store.credential_clear(capability_digest(token), _org(org), connector_id(identifier), expected)

    def credential_status(self, token, org):
        return self._store.credential_status(capability_digest(token), _org(org))

    # -- platform owner: the default OAuth app -----------------------------------------------------------------------------------
    def platform_credential_set(self, token, identifier, kind, fields, expected):
        digest, identifier = capability_digest(token), connector_id(identifier)
        if kind != 'oauth_client' or type(expected) is not int or not 0 <= expected <= MAX_REVISION:
            raise BrokerInvalid()
        secret = _secret(kind, fields)
        sealed = self._cipher.seal(Binding(PLATFORM, 'org', '', identifier, expected + 1), secret)
        return self._store.platform_credential_save(digest, identifier, kind, expected, sealed, hint(secret.get('client_secret')))
