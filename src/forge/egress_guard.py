"""Where the connector broker may connect: https on 443 to allow-listed hosts, resolved once, pinned, never redirected.

``EgressGuard.plan`` turns an upstream URL into a ``Target`` or raises ``EgressDenied`` with one finite code (``scheme``, ``userinfo``,
``host``, ``port``, ``allow_list``, ``resolve``, ``address``). It refuses every address that is not globally routable (loopback,
link-local and cloud metadata, RFC 1918, shared/CGNAT, ULA, multicast, reserved, and the IPv6 forms that embed an IPv4 address), judges
the WHOLE answer (one private address among public ones refuses the lot) and resolves exactly once: the connection is made to the
address that was checked, so a rebinding DNS answer cannot redirect it. ``GuardedClient`` sends the request to that pinned IP with the
original ``Host`` and SNI, follows no redirect, ignores proxy environment variables and bounds size and time.

Fixtures are the only way to reach loopback or plain http: a test composition passes ``fixtures={host: Fixture(...)}`` explicitly, and a
fixture host still has to be in the connector's allow-list. Production composition passes none.
"""
from dataclasses import dataclass
import ipaddress
import logging
import re
import socket
import time
from urllib.parse import urlsplit

import httpx

_HOST = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*')
_BAD_URL_CHARS = re.compile(r'[\s\\\x00-\x1f\x7f]')
_BLOCKED_V6 = tuple(ipaddress.ip_network(net) for net in ('2002::/16', '64:ff9b::/96', '64:ff9b:1::/48', '2001::/32'))
USER_AGENT = 'forge-connector-broker/1'
# The HTTP libraries log every request URL (pinned addresses, query strings) at INFO/DEBUG: the broker never wants those in a log.
for _library in ('httpx', 'httpcore'):
    logging.getLogger(_library).setLevel(logging.WARNING)


class EgressDenied(Exception):
    """The message is one stable code; it never carries a URL, an address or upstream text."""


@dataclass(frozen=True)
class Fixture:
    connect_host: str
    port: int
    tls: bool = False


@dataclass(frozen=True)
class Target:
    host: str
    ip: str
    port: int
    tls: bool
    path: str

    @property
    def url(self):
        literal = '[%s]' % self.ip if ':' in self.ip else self.ip
        return '%s://%s:%d%s' % ('https' if self.tls else 'http', literal, self.port, self.path)

    @property
    def host_header(self):
        default = 443 if self.tls else 80
        return self.host if self.port == default else '%s:%d' % (self.host, self.port)


def load_fixtures(path):
    """Explicit test/dev fixture hosts from a JSON file ``{host: {connect_host, port, tls?}}``; ValueError on anything else."""
    from pathlib import Path
    document = __import__('json').loads(Path(path).read_text('utf-8'))
    if type(document) is not dict:
        raise ValueError('fixtures')
    fixtures = {}
    for host, item in document.items():
        if (type(host) is not str or not _HOST.fullmatch(host) or type(item) is not dict or not {'connect_host', 'port'} <= set(item) <= {'connect_host', 'port', 'tls'}
                or type(item['connect_host']) is not str or not item['connect_host'] or type(item['port']) is not int or not 1 <= item['port'] <= 65535
                or type(item.get('tls', False)) is not bool):
            raise ValueError('fixtures')
        fixtures[host] = Fixture(item['connect_host'], item['port'], item.get('tls', False))
    return fixtures


def system_resolver(host):
    return [item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]


def public_address(text) -> bool:
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if address.version == 6:
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        elif any(address in network for network in _BLOCKED_V6):
            return False
    return address.is_global and not address.is_multicast


def _normalize(host):
    return host.lower().rstrip('.')


class EgressGuard:
    def __init__(self, resolver=system_resolver, *, fixtures=None):
        self._resolver, self._fixtures = resolver, dict(fixtures or {})

    def _resolve(self, host):
        try:
            answers = list(self._resolver(host))
        except Exception:
            raise EgressDenied('resolve') from None
        if not answers:
            raise EgressDenied('resolve')
        return answers

    def plan(self, url, allowed_hosts) -> Target:
        text = url if type(url) is str else ''
        try:
            parts = urlsplit(text)
        except ValueError:
            raise EgressDenied('scheme') from None
        if parts.scheme not in ('http', 'https'):
            raise EgressDenied('scheme')
        if _BAD_URL_CHARS.search(text):
            raise EgressDenied('host')
        if parts.username is not None or parts.password is not None:
            raise EgressDenied('userinfo')
        host = _normalize(parts.hostname or '')
        if not host or not _HOST.fullmatch(host):
            raise EgressDenied('host')
        try:
            ipaddress.ip_address(host)
            raise EgressDenied('host')  # an address literal is never a connector host
        except ValueError:
            pass
        try:
            port = parts.port
        except ValueError:
            raise EgressDenied('port') from None
        fixture = self._fixtures.get(host)
        if fixture is None and parts.scheme != 'https':
            raise EgressDenied('scheme')
        if port not in (None, 443) or (fixture is not None and port is not None):
            raise EgressDenied('port')
        if host not in {_normalize(name) for name in allowed_hosts}:
            raise EgressDenied('allow_list')
        path = (parts.path or '/') + ('?' + parts.query if parts.query else '')
        if fixture is not None:
            if parts.scheme != ('https' if fixture.tls else 'http'):
                raise EgressDenied('scheme')
            return Target(host, self._resolve(fixture.connect_host)[0], fixture.port, fixture.tls, path)
        answers = self._resolve(host)
        if not all(public_address(answer) for answer in answers):
            raise EgressDenied('address')
        return Target(host, str(ipaddress.ip_address(answers[0])), 443, True, path)


class Upstream:
    """A streamed upstream response: status and headers now, the body in bounded chunks."""

    def __init__(self, response):
        self._response = response
        self.status = response.status_code
        self.headers = response.headers

    def iter_bytes(self, max_bytes, deadline=None):
        total = 0
        try:
            for chunk in self._response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise EgressDenied('too_large')
                yield chunk
                if deadline is not None and time.monotonic() > deadline:
                    raise EgressDenied('timeout')
        except httpx.TimeoutException:
            raise EgressDenied('timeout') from None
        except httpx.HTTPError:
            raise EgressDenied('upstream') from None
        finally:
            self.close()

    def read(self, max_bytes):
        return b''.join(self.iter_bytes(max_bytes))

    def close(self):
        self._response.close()


class GuardedClient:
    def __init__(self, guard, *, transport=None, verify=True, timeout=15.0):
        self._guard = guard
        self._client = httpx.Client(transport=transport, verify=verify, follow_redirects=False, trust_env=False,
                                    timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)))

    @property
    def follow_redirects(self):
        return self._client.follow_redirects

    @property
    def trust_env(self):
        return self._client.trust_env

    def request(self, method, url, allowed_hosts, *, headers, content=None, timeout=None) -> Upstream:
        target = self._guard.plan(url, allowed_hosts)
        sent = {name: value for name, value in headers.items() if name.lower() not in ('host', 'accept-encoding', 'user-agent')}
        sent.update({'Host': target.host_header, 'Accept-Encoding': 'identity', 'User-Agent': USER_AGENT})
        extensions = {'sni_hostname': target.host} if target.tls else {}
        try:
            built = self._client.build_request(method, target.url, headers=sent, content=content, extensions=extensions,
                                               timeout=httpx.USE_CLIENT_DEFAULT if timeout is None else httpx.Timeout(timeout))
            response = self._client.send(built, stream=True)
        except httpx.TimeoutException:
            raise EgressDenied('timeout') from None
        except httpx.ConnectError:
            raise EgressDenied('connect') from None
        except httpx.HTTPError:
            raise EgressDenied('upstream') from None
        if 300 <= response.status_code < 400:
            response.close()
            raise EgressDenied('redirect')
        return Upstream(response)

    def close(self):
        self._client.close()
