"""MCP broker pure parts: the method allow-list and size cap, the rate limiter and the chunk-boundary-safe secret redaction."""
import itertools
import json
from pathlib import Path
import random
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.connector_model import BrokerInvalid, BrokerRateLimited, BrokerTooLarge
from forge.mcp_broker import REQUEST_LIMIT, BrokerMethodBlocked, RateLimiter, Redactor, parse_request


def request(method, **extra):
    return json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, **extra}).encode()


class MethodFilterTests(unittest.TestCase):
    def test_the_allow_listed_methods_pass_and_the_tool_name_is_extracted(self):
        for method in ('initialize', 'ping', 'notifications/initialized', 'notifications/cancelled', 'tools/list', 'tools/call', 'resources/list', 'resources/read',
                       'resources/templates/list', 'resources/subscribe', 'prompts/list', 'prompts/get'):
            with self.subTest(method=method):
                self.assertEqual(parse_request(request(method))[0], method)
        self.assertEqual(parse_request(request('tools/call', params={'name': 'create_issue', 'arguments': {'a': 1}})), ('tools/call', 'create_issue'))
        self.assertEqual(parse_request(request('tools/call', params={'name': 'bad name!'})), ('tools/call', None))
        self.assertEqual(parse_request(request('tools/call', params={'name': 5})), ('tools/call', None))

    def test_server_to_client_requests_and_everything_else_are_blocked(self):
        for method in ('sampling/createMessage', 'elicitation/create', 'roots/list', 'logging/setLevel', 'completion/complete', 'tools', 'toolsx/list', 'x/tools/list',
                       'Tools/list', '', 'tools/../x', 'initialize2', 'notifications/roots/list_changed', 'a' * 100):
            with self.subTest(method=method), self.assertRaises(BrokerMethodBlocked):
                parse_request(request(method))

    def test_batches_non_objects_and_malformed_json_are_invalid(self):
        for body in (b'[]', b'[{"jsonrpc":"2.0","method":"ping"}]', b'"ping"', b'5', b'null', b'{not json', b'', b'{"jsonrpc":"1.0","method":"ping"}', b'{"method":"ping"}',
                     b'{"jsonrpc":"2.0","method":5}', b'{"jsonrpc":"2.0"}'):
            with self.subTest(body=body[:30]), self.assertRaises(BrokerInvalid):
                parse_request(body)

    def test_an_oversized_body_is_refused_before_it_is_even_parsed(self):
        with self.assertRaises(BrokerTooLarge):
            parse_request(b'x' * (REQUEST_LIMIT + 1))
        with self.assertRaises(BrokerTooLarge):
            parse_request('not bytes')
        self.assertEqual(parse_request(request('ping') + b' ' * 100)[0], 'ping')


class RateLimiterTests(unittest.TestCase):
    def test_the_limit_applies_per_key_within_a_minute_and_then_resets(self):
        now = [0.0]
        limiter = RateLimiter(3, clock=lambda: now[0])
        for _ in range(3):
            limiter.check('a')
        with self.assertRaises(BrokerRateLimited):
            limiter.check('a')
        limiter.check('b')
        now[0] = 61
        limiter.check('a')


class RedactorTests(unittest.TestCase):
    SECRET = 'at-SECRET_token-0123456789'

    def run_chunks(self, chunks, secrets=None):
        redactor = Redactor(secrets or [self.SECRET])
        return b''.join(redactor.feed(chunk) for chunk in chunks) + redactor.flush()

    def test_every_split_point_of_a_stream_gives_the_same_scrubbed_output(self):
        text = ('prefix {"authorization":"Bearer %s"} middle %s end' % (self.SECRET, self.SECRET)).encode()
        expected = text.replace(self.SECRET.encode(), b'[redacted]')
        for first, second in itertools.combinations(range(1, len(text)), 2):
            chunks = [text[:first], text[first:second], text[second:]]
            self.assertEqual(self.run_chunks(chunks), expected, (first, second))
        self.assertNotIn(self.SECRET.encode(), expected)

    def test_a_json_escaped_form_is_scrubbed_too(self):
        secret = 'tok"with\\odd/chars'
        text = json.dumps({'echo': secret}).encode()
        for cut in range(1, len(text)):
            out = self.run_chunks([text[:cut], text[cut:]], [secret])
            self.assertNotIn(json.dumps(secret)[1:-1].encode(), out)
            self.assertIn(b'[redacted]', out)

    def test_random_chunking_never_leaks_and_never_corrupts_other_bytes(self):
        rng = random.Random(11)
        for _ in range(300):
            filler = bytes(rng.choice(b'abcdefgh {}":,') for _ in range(rng.randint(0, 80)))
            text = filler + self.SECRET.encode() + filler + self.SECRET.encode()[:7] + filler
            cuts = sorted(rng.sample(range(len(text) + 1), rng.randint(0, 5)))
            chunks = [text[i:j] for i, j in zip([0, *cuts], [*cuts, len(text)])]
            out = self.run_chunks(chunks)
            self.assertEqual(out, text.replace(self.SECRET.encode(), b'[redacted]'))

    def test_no_secrets_and_empty_secrets_pass_everything_through(self):
        self.assertEqual(self.run_chunks([b'abc', b'def'], []), b'abcdef')
        self.assertEqual(self.run_chunks([b'abc', b'def'], ['']), b'abcdef')

    def test_several_secrets_and_a_short_secret(self):
        out = self.run_chunks([b'one KEY-AAAA-1 two ', b'KEY-BBBB-2 three X'], ['KEY-AAAA-1', 'KEY-BBBB-2', 'X'])
        self.assertEqual(out, b'one [redacted] two [redacted] three [redacted]')


if __name__ == '__main__':
    unittest.main()
