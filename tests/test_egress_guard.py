"""Connector egress: https/443 to allow-listed hosts only, resolve once, refuse non-public addresses, pin the connection, never follow redirects."""
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import httpx
from forge.egress_guard import EgressDenied, EgressGuard, Fixture, GuardedClient

ALLOWED = ['mcp.example.com', 'api.example.com']


def resolver(*answers, calls=None):
    """A resolver returning the given answers in order (the last one repeats) and recording how often it is asked."""
    sequence = list(answers)

    def resolve(host):
        if calls is not None:
            calls.append(host)
        return list(sequence.pop(0) if len(sequence) > 1 else sequence[0])
    return resolve


def code(call):
    try:
        call()
    except EgressDenied as error:
        return str(error)
    return None


class PlanTests(unittest.TestCase):
    def test_a_public_allow_listed_https_host_is_planned_and_pinned_to_the_resolved_address(self):
        calls = []
        guard = EgressGuard(resolver(['93.184.216.34'], calls=calls))
        target = guard.plan('https://MCP.Example.com./mcp/v1?x=1#frag', ALLOWED)
        self.assertEqual((target.host, target.ip, target.port, target.tls, target.path), ('mcp.example.com', '93.184.216.34', 443, True, '/mcp/v1?x=1'))
        self.assertEqual(calls, ['mcp.example.com'], 'resolved exactly once')

    def test_a_host_outside_the_allow_list_is_refused_before_any_lookup(self):
        calls = []
        guard = EgressGuard(resolver(['93.184.216.34'], calls=calls))
        for url in ('https://evil.example.org/', 'https://example.com/', 'https://sub.mcp.example.com/', 'https://mcp.example.com.evil.org/'):
            self.assertEqual(code(lambda: guard.plan(url, ALLOWED)), 'allow_list', url)
        self.assertEqual(calls, [])

    def test_schemes_ports_credentials_and_literals_are_refused(self):
        guard = EgressGuard(resolver(['93.184.216.34']))
        cases = {'http://mcp.example.com/': 'scheme', 'ftp://mcp.example.com/': 'scheme', 'https://mcp.example.com:8443/': 'port', 'https://mcp.example.com:80/': 'port',
                 'https://user:pw@mcp.example.com/': 'userinfo', 'https://user@mcp.example.com/': 'userinfo', 'https://93.184.216.34/': 'host',
                 'https://[2606:4700::1111]/': 'host', 'https:///path': 'host', 'https://mcp.example.com\\@evil.org/': 'host', 'not a url': 'scheme', '': 'scheme'}
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(code(lambda: guard.plan(url, ALLOWED + ['93.184.216.34'])), expected)

    def test_every_non_public_address_is_refused(self):
        private = ('10.0.0.5', '172.16.0.1', '192.168.1.1', '127.0.0.1', '169.254.169.254', '0.0.0.0', '100.64.0.1', '224.0.0.1', '198.18.0.1', '255.255.255.255',
                   '::1', '::', 'fe80::1', 'fc00::1', 'fd00:ec2::254', '::ffff:10.0.0.1', '::ffff:127.0.0.1', '2002:a00:1::1', '64:ff9b::a00:1', 'ff02::1')
        for address in private:
            with self.subTest(address=address):
                self.assertEqual(code(lambda: EgressGuard(resolver([address])).plan('https://mcp.example.com/', ALLOWED)), 'address')

    def test_a_mixed_answer_is_refused_as_a_whole_and_an_empty_or_failing_lookup_is_refused(self):
        self.assertEqual(code(lambda: EgressGuard(resolver(['93.184.216.34', '10.0.0.5'])).plan('https://mcp.example.com/', ALLOWED)), 'address')
        self.assertEqual(code(lambda: EgressGuard(resolver([])).plan('https://mcp.example.com/', ALLOWED)), 'resolve')

        def failing(host):
            raise OSError('no dns')
        self.assertEqual(code(lambda: EgressGuard(failing).plan('https://mcp.example.com/', ALLOWED)), 'resolve')

    def test_dns_that_answers_public_then_private_is_pinned_to_the_first_checked_address(self):
        calls = []
        guard = EgressGuard(resolver(['93.184.216.34'], ['10.0.0.5'], calls=calls))
        first = guard.plan('https://mcp.example.com/', ALLOWED)
        self.assertEqual((first.ip, len(calls)), ('93.184.216.34', 1), 'the connection uses the address that was checked, not a second lookup')
        self.assertEqual(code(lambda: guard.plan('https://mcp.example.com/', ALLOWED)), 'address', 'a later plan sees the private answer and is refused')

    def test_fixture_hosts_are_the_only_way_to_reach_loopback_and_still_need_the_allow_list(self):
        fixtures = {'oauth.fixture.test': Fixture('127.0.0.1', 4545)}
        guard = EgressGuard(resolver(['127.0.0.1']), fixtures=fixtures)
        target = guard.plan('http://oauth.fixture.test/token', ['oauth.fixture.test'])
        self.assertEqual((target.ip, target.port, target.tls, target.path), ('127.0.0.1', 4545, False, '/token'))
        self.assertEqual(code(lambda: guard.plan('http://oauth.fixture.test/token', ALLOWED)), 'allow_list')
        self.assertEqual(code(lambda: EgressGuard(resolver(['127.0.0.1'])).plan('http://oauth.fixture.test/token', ['oauth.fixture.test'])), 'scheme',
                         'without the explicit fixture the same URL is just a refused http URL')
        self.assertEqual(code(lambda: EgressGuard(resolver(['127.0.0.1'])).plan('https://oauth.fixture.test/token', ['oauth.fixture.test'])), 'address')


class ClientTests(unittest.TestCase):
    def client(self, handler, answers=(['93.184.216.34'],), **keywords):
        return GuardedClient(EgressGuard(resolver(*answers)), transport=httpx.MockTransport(handler), **keywords)

    def test_the_request_goes_to_the_pinned_ip_with_the_original_host_and_sni(self):
        seen = {}

        def handler(request):
            seen.update(url=str(request.url), host=request.headers['host'], sni=request.extensions.get('sni_hostname'), method=request.method, body=request.content)
            return httpx.Response(200, json={'ok': True})
        upstream = self.client(handler).request('POST', 'https://mcp.example.com/mcp', ALLOWED, headers={'content-type': 'application/json'}, content=b'{"a":1}')
        self.assertEqual((upstream.status, upstream.read(1000)), (200, b'{"ok":true}'))
        self.assertEqual(seen, {'url': 'https://93.184.216.34/mcp', 'host': 'mcp.example.com', 'sni': 'mcp.example.com', 'method': 'POST', 'body': b'{"a":1}'})

    def test_a_redirect_is_never_followed_and_is_an_error(self):
        hits = []

        def handler(request):
            hits.append(str(request.url))
            return httpx.Response(302, headers={'location': 'https://api.example.com/steal'})
        with self.assertRaises(EgressDenied) as caught:
            self.client(handler).request('GET', 'https://mcp.example.com/mcp', ALLOWED, headers={})
        self.assertEqual(str(caught.exception), 'redirect')
        self.assertEqual(len(hits), 1)

    def test_a_denied_target_makes_no_request_at_all(self):
        hits = []
        client = self.client(lambda request: hits.append(request) or httpx.Response(200), answers=(['10.0.0.5'],))
        self.assertEqual(code(lambda: client.request('GET', 'https://mcp.example.com/', ALLOWED, headers={})), 'address')
        self.assertEqual(hits, [])

    def test_the_response_is_capped_and_a_stream_stops_at_the_cap(self):
        upstream = self.client(lambda request: httpx.Response(200, content=b'x' * 5000)).request('GET', 'https://mcp.example.com/', ALLOWED, headers={})
        with self.assertRaises(EgressDenied) as caught:
            upstream.read(1000)
        self.assertEqual(str(caught.exception), 'too_large')
        upstream = self.client(lambda request: httpx.Response(200, content=b'x' * 5000)).request('GET', 'https://mcp.example.com/', ALLOWED, headers={})
        with self.assertRaises(EgressDenied):
            list(upstream.iter_bytes(1000))

    def test_an_overall_deadline_bounds_a_slow_stream(self):
        def slow():
            for _ in range(5):
                time.sleep(0.05)
                yield b'chunk'
        upstream = self.client(lambda request: httpx.Response(200, content=slow())).request('GET', 'https://mcp.example.com/', ALLOWED, headers={})
        with self.assertRaises(EgressDenied) as caught:
            list(upstream.iter_bytes(10_000, deadline=time.monotonic() + 0.08))
        self.assertEqual(str(caught.exception), 'timeout')

    def test_a_transport_failure_is_one_finite_error_without_detail(self):
        def broken(request):
            raise httpx.ConnectError('secret detail 10.0.0.9')
        with self.assertRaises(EgressDenied) as caught:
            self.client(broken).request('GET', 'https://mcp.example.com/', ALLOWED, headers={})
        self.assertEqual(str(caught.exception), 'connect')
        self.assertNotIn('secret', str(caught.exception))

    def test_trust_env_and_redirects_are_off_by_construction(self):
        client = GuardedClient(EgressGuard(resolver(['93.184.216.34'])))
        self.assertEqual((client.follow_redirects, client.trust_env), (False, False))


if __name__ == '__main__':
    unittest.main()
