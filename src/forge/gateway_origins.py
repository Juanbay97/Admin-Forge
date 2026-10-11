"""Deployment allow-list of gateway origins; the only source of outbound gateway URLs.

Trusted composition supplies a frozenset of canonical origins. Anything else is
denied by exact string membership, so look-alikes (suffixes, userinfo, paths,
ports, case, whitespace) never match. Plain ``http`` is accepted only for numeric
loopback and only when the dev profile is composed explicitly.
"""
from ipaddress import ip_address
import re
from urllib.parse import urlsplit

DEFAULT_ENDPOINT = 'https://ia.prometheonlab.com'
MAX_ORIGIN = 255
_HOST = re.compile(r'[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*')


class OriginDenied(ValueError):
    """Redacted on purpose: the rejected value is never echoed."""
    def __init__(self):
        super().__init__('Gateway origin not allowed.')


def _canonical(entry, dev):
    """Return ``entry`` unchanged when it is a canonical origin, else raise ValueError."""
    if type(entry) is not str or not 1 <= len(entry) <= MAX_ORIGIN or not entry.isascii():
        raise ValueError('Invalid gateway origin.')
    try:
        parts = urlsplit(entry)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise ValueError('Invalid gateway origin.') from None
    if (parts.scheme not in ('http', 'https') or not host or parts.username is not None
            or parts.password is not None or parts.path or parts.query or parts.fragment
            or entry != parts.scheme + '://' + (host if port is None else '%s:%d' % (host, port))
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError('Invalid gateway origin.')
    if parts.scheme == 'http':
        # Mirrors the database check: numeric 127.0.0.1 with an explicit port only.
        if not dev or host != '127.0.0.1' or port is None:
            raise ValueError('Plain http is limited to the dev loopback profile.')
        return entry
    try:
        ip_address(host)
    except ValueError:
        if not _HOST.fullmatch(host):
            raise ValueError('Invalid gateway origin.') from None
        return entry
    raise ValueError('Numeric https origins are not accepted.')


class OriginPolicy:
    """Immutable allow-list. Construction fails closed on any unsafe entry."""
    def __init__(self, allowed, *, dev=False):
        if type(allowed) is not frozenset or not allowed or type(dev) is not bool:
            raise ValueError('Explicit non-empty gateway origin allow-list required.')
        for entry in allowed:
            _canonical(entry, dev)
        self._allowed = allowed

    @property
    def allowed(self):
        return self._allowed

    def permits(self, value):
        return type(value) is str and value in self._allowed

    def require(self, value):
        if not self.permits(value):
            raise OriginDenied()
        return value

    def __repr__(self):
        return 'OriginPolicy(%d origins)' % len(self._allowed)


DEFAULT_POLICY = OriginPolicy(frozenset({DEFAULT_ENDPOINT}))
