"""Branding HTTP surface over the contract-tested fake store: public lookup, assets, member and admin routes."""
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import unittest
import zlib
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from branding_support import FakeBrandingStore
from forge import contract
from forge.account_api import create_account_app
from forge.accounts import ACCOUNT_ISSUER
from forge.branding import DEFAULT
from forge.branding_api import RateLimiter, mount_branding
from forge.branding_store import BrandingUnavailable
from forge.foundation import AuthenticatedIdentity
from forge.invitations import capability_digest

SIGNATURE = b'\x89PNG\r\n\x1a\n'
PUBLIC_KEYS = {'revision', 'name', 'loginCopy', 'theme', 'assets'}
BRANDING = {'name': 'Acme Labs', 'loginCopy': 'Welcome to Acme.',
            'theme': {'primary': '#0B1D26', 'accent': '#E07A2D', 'tint': '#E8DCC1', 'heading': 'montserrat', 'body': 'inter'},
            'assets': {}}


def chunk(kind, data=b''):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(width=64, height=48, *, extra=()):
    header = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    rows = zlib.compress((b'\x00' + bytes(4 * width)) * height)
    return SIGNATURE + header + b''.join(extra) + chunk(b'IDAT', rows) + chunk(b'IEND')


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class World:
    def __init__(self, *, limiter=None, ready=True, store=None):
        self.store = store or FakeBrandingStore()
        self.org_a, self.org_b = self.store.add_org('acme'), self.store.add_org('globex')
        self.tokens = {name: secrets.token_urlsafe(32) for name in ('admin_a', 'member_a', 'admin_b', 'stranger', 'revoked')}
        for name, org, role in (('admin_a', self.org_a, 'admin'), ('member_a', self.org_a, 'member'), ('admin_b', self.org_b, 'admin')):
            self.store.add_actor(capability_digest(self.tokens[name]), org, role)
        self.sessions = MagicMock()
        self.sessions.validate.side_effect = lambda token: (
            AuthenticatedIdentity('forge', ACCOUNT_ISSUER, str(uuid4())) if token in self.tokens.values() and token != self.tokens['revoked'] else None)
        self.readiness = MagicMock()
        self.readiness.check.return_value = ready
        self.clock = FakeClock()
        self.limiter = limiter or RateLimiter(clock=self.clock)
        self.app = create_account_app(sessions=self.sessions, readiness=self.readiness)
        mount_branding(self.app, store=self.store, sessions=self.sessions, readiness=self.readiness, limiter=self.limiter)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def auth(self, who):
        return {'Authorization': 'Bearer ' + self.tokens[who]}

    def put(self, who, org, expected, document=None, *, raw=None, headers=None):
        body = raw if raw is not None else json.dumps({'expectedRevision': expected, 'branding': document or BRANDING})
        return self.client.put('/forge/v1/orgs/%s/branding' % org, content=body,
                               headers={**self.auth(who), 'Content-Type': 'application/json', **(headers or {})})

    def upload(self, who, org, data, *, kind='logoLight', content_type='image/png', headers=None):
        return self.client.post('/forge/v1/orgs/%s/branding/assets?kind=%s' % (org, kind), content=data,
                                headers={**self.auth(who), 'Content-Type': content_type, **(headers or {})})


def publish(world, data=None):
    """Upload a logo as org A's admin and publish it; returns (sha, bytes served)."""
    data = data or png()
    sha = world.upload('admin_a', world.org_a, data).json()['sha256']
    saved = world.put('admin_a', world.org_a, 0, {**BRANDING, 'assets': {'logoLight': sha}})
    assert saved.status_code == 200, saved.text
    return sha


class PublicLookupTests(unittest.TestCase):
    def test_a_branded_organization_returns_exactly_the_public_fields_with_an_etag(self):
        world = World()
        publish(world)
        response = world.client.get('/forge/v1/branding', params={'org': 'acme'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), PUBLIC_KEYS)
        self.assertEqual((body['revision'], body['name'], body['loginCopy']), (1, 'Acme Labs', 'Welcome to Acme.'))
        self.assertEqual(set(body['theme']), {'primary', 'accent', 'tint', 'heading', 'body'})
        self.assertEqual(list(body['assets']), ['logoLight'])
        self.assertTrue(body['assets']['logoLight'].startswith('/forge/v1/branding/assets/'))
        self.assertEqual(response.headers['etag'], '"1"')
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertTrue(response.headers['content-type'].startswith('application/json'))
        self.assertNotIn('set-cookie', response.headers)
        for leaked in (str(world.org_a), 'organization_id', 'member', 'updated_by', 'actor', 'password', 'token'):
            self.assertNotIn(leaked, response.text)

    def test_an_unbranded_active_organization_serves_the_prometheon_default_at_revision_zero(self):
        world = World()
        body = world.client.get('/forge/v1/branding', params={'org': 'globex'}).json()
        self.assertEqual((body['revision'], body['name']), (0, DEFAULT.name))
        self.assertEqual(body['theme']['primary'], DEFAULT.primary)
        self.assertEqual(body['assets'], {})

    def test_if_none_match_returns_304_without_a_body_and_a_stale_tag_returns_200(self):
        world = World()
        publish(world)
        for header in ('"1"', 'W/"1"', '"0", "1"', '*'):
            with self.subTest(header=header):
                response = world.client.get('/forge/v1/branding', params={'org': 'acme'}, headers={'If-None-Match': header})
                self.assertEqual((response.status_code, response.content), (304, b''))
                self.assertEqual(response.headers['etag'], '"1"')
        for header in ('"0"', '"2"', '1', '', 'garbage'):
            with self.subTest(header=header):
                self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'},
                                                  headers={'If-None-Match': header}).status_code, 200)

    def test_unknown_inactive_and_malformed_codes_return_one_identical_404(self):
        world = World()
        world.store.add_org('closed', active=False)
        urls = ['/forge/v1/branding?org=nope', '/forge/v1/branding?org=closed', '/forge/v1/branding?org=ACME',
                '/forge/v1/branding?org=' + 'a' * 70, "/forge/v1/branding?org=x'--", '/forge/v1/branding?org=%00',
                '/forge/v1/branding?org=..%2F..%2Fetc%2Fpasswd', '/forge/v1/branding?org=', '/forge/v1/branding',
                '/forge/v1/branding?org=acme&org=globex', '/forge/v1/branding?org=%E2%80%AEacme']
        seen = set()
        for url in urls:
            with self.subTest(url=url):
                response = world.client.get(url, headers={'Authorization': 'Bearer ' + world.tokens['admin_a']})
                self.assertEqual(response.status_code, 404)
                seen.add((response.content, response.headers['content-type'], response.headers['cache-control']))
        self.assertEqual(len(seen), 1, 'one body, one content type, one cache policy for every miss')
        error = json.loads(seen.copy().pop()[0])['error']
        self.assertEqual(error['code'], 'NOT_FOUND')
        for hint in ('acme', 'closed', 'globex', 'org'):
            self.assertNotIn(hint, json.dumps(error).lower().replace('organization', ''))

    def test_the_lookup_needs_no_session_and_never_touches_the_session_store(self):
        world = World()
        self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 200)
        world.sessions.validate.assert_not_called()
        world.readiness.check.assert_not_called()

    def test_a_store_outage_is_a_uniform_503_without_detail(self):
        world = World()
        world.store.public = MagicMock(side_effect=BrandingUnavailable())
        response = world.client.get('/forge/v1/branding', params={'org': 'acme'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'SERVICE_UNAVAILABLE')
        self.assertEqual(response.headers['cache-control'], 'no-store')


class RateLimitTests(unittest.TestCase):
    def test_a_client_over_its_budget_gets_429_with_retry_after_and_the_store_is_not_consulted(self):
        world = World(limiter=RateLimiter(per_client=(5, 1.0), overall=(500, 50.0), clock=FakeClock()))
        for _ in range(5):
            self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 200)
        calls = len(world.store.calls)
        response = world.client.get('/forge/v1/branding', params={'org': 'acme'})
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers['retry-after']), 1)
        error = response.json()['error']
        self.assertEqual((error['code'], error['retryable']), ('RATE_LIMITED', True))
        self.assertEqual(error['retry_after_seconds'], int(response.headers['retry-after']))
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(len(world.store.calls), calls)

    def test_misses_and_asset_requests_spend_the_same_budget_so_enumeration_is_throttled(self):
        limiter = RateLimiter(per_client=(4, 1.0), overall=(500, 50.0), clock=FakeClock())
        world = World(limiter=limiter)
        for index in range(2):
            self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'guess-%d' % index}).status_code, 404)
        for _ in range(2):
            self.assertEqual(world.client.get('/forge/v1/branding/assets/' + 'a' * 64).status_code, 404)
        self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'guess-9'}).status_code, 429)
        self.assertEqual(world.client.get('/forge/v1/branding/assets/' + 'a' * 64).status_code, 429)

    def test_the_budget_refills_over_time(self):
        clock = FakeClock()
        world = World(limiter=RateLimiter(per_client=(2, 1.0), overall=(500, 50.0), clock=clock))
        for _ in range(2):
            world.client.get('/forge/v1/branding', params={'org': 'acme'})
        self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 429)
        clock.now += 1.0
        self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 200)
        self.assertEqual(world.client.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 429)

    def test_a_global_cap_protects_the_service_from_many_clients_and_x_forwarded_for_buys_nothing(self):
        world = World(limiter=RateLimiter(per_client=(50, 1.0), overall=(6, 1.0), clock=FakeClock()))
        statuses = []
        for index in range(10):
            client = TestClient(world.app, client=('10.0.0.%d' % index, 5000), raise_server_exceptions=False)
            statuses.append(client.get('/forge/v1/branding', params={'org': 'acme'},
                                       headers={'X-Forwarded-For': '203.0.113.%d' % index}).status_code)
        self.assertEqual(statuses, [200] * 6 + [429] * 4)

    def test_one_client_cannot_exhaust_the_global_budget_for_everyone_else(self):
        world = World(limiter=RateLimiter(per_client=(3, 0.1), overall=(100, 10.0), clock=FakeClock()))
        for _ in range(20):
            world.client.get('/forge/v1/branding', params={'org': 'acme'})
        other = TestClient(world.app, client=('10.9.9.9', 1), raise_server_exceptions=False)
        self.assertEqual(other.get('/forge/v1/branding', params={'org': 'acme'}).status_code, 200)

    def test_tracked_clients_are_bounded(self):
        limiter = RateLimiter(per_client=(1, 0.001), overall=(10 ** 6, 10 ** 6), max_clients=8, clock=FakeClock())
        for index in range(500):
            limiter.admit('client-%d' % index)
        self.assertLessEqual(limiter.tracked, 9)
        retry = limiter.admit('client-0')
        self.assertTrue(retry is None or retry > 0)


class AssetDeliveryTests(unittest.TestCase):
    def test_a_published_asset_is_served_immutable_with_its_stored_type_and_hardening_headers(self):
        world = World()
        data = png()
        sha = publish(world, data)
        response = world.client.get('/forge/v1/branding/assets/' + sha)
        self.assertEqual(response.status_code, 200)
        stored = world.store.asset(sha)
        self.assertEqual(response.content, stored.data)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertEqual(response.headers['cache-control'], 'public, max-age=31536000, immutable')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(response.headers['content-security-policy'], "default-src 'none'; sandbox")
        self.assertEqual(response.headers['etag'], '"%s"' % sha)
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), sha)
        again = world.client.get('/forge/v1/branding/assets/' + sha, headers={'If-None-Match': '"%s"' % sha})
        self.assertEqual((again.status_code, again.content), (304, b''))

    def test_unpublished_unknown_and_malformed_hashes_return_one_identical_404(self):
        world = World()
        sha = world.upload('admin_a', world.org_a, png()).json()['sha256']
        hostile = [sha, 'f' * 64, 'A' * 64, 'short', '..%2F..%2Fsecret', '%00', 'a' * 65, sha + '%0A', sha + '.png']
        seen = set()
        for value in hostile:
            with self.subTest(value=value):
                response = world.client.get('/forge/v1/branding/assets/' + value)
                self.assertEqual(response.status_code, 404)
                seen.add((response.content, response.headers['content-type'], response.headers['cache-control']))
        self.assertEqual(len(seen), 1)

    def test_a_replaced_asset_stops_being_served(self):
        world = World()
        first = publish(world)
        second = world.upload('admin_a', world.org_a, png(80, 80)).json()['sha256']
        world.put('admin_a', world.org_a, 1, {**BRANDING, 'assets': {'logoLight': second}})
        self.assertEqual(world.client.get('/forge/v1/branding/assets/' + first).status_code, 404)
        self.assertEqual(world.client.get('/forge/v1/branding/assets/' + second).status_code, 200)


class MemberProjectionTests(unittest.TestCase):
    def test_members_read_their_organization_branding_with_no_store(self):
        world = World()
        world.put('admin_a', world.org_a, 0)
        for who in ('member_a', 'admin_a'):
            response = world.client.get('/forge/v1/orgs/%s/branding' % world.org_a, headers=world.auth(who))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), PUBLIC_KEYS)
            self.assertEqual(response.json()['revision'], 1)
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_missing_malformed_and_revoked_sessions_are_401_and_foreign_or_unknown_orgs_are_404(self):
        world = World()
        url = '/forge/v1/orgs/%s/branding' % world.org_a
        for headers in ({}, {'Authorization': 'Bearer short'}, {'Authorization': 'Basic ' + world.tokens['admin_a']},
                        {'Authorization': 'Bearer ' + secrets.token_urlsafe(32)}):
            with self.subTest(headers=headers):
                response = world.client.get(url, headers=headers)
                self.assertEqual((response.status_code, response.json()['error']['code']), (401, 'UNAUTHENTICATED'))
        for who, org in (('admin_b', world.org_a), ('member_a', world.org_b), ('member_a', uuid4())):
            self.assertEqual(world.client.get('/forge/v1/orgs/%s/branding' % org, headers=world.auth(who)).status_code, 404)

    def test_an_unready_service_is_503(self):
        world = World(ready=False)
        self.assertEqual(world.client.get('/forge/v1/orgs/%s/branding' % world.org_a, headers=world.auth('admin_a')).status_code, 503)


class AdminSaveTests(unittest.TestCase):
    def test_an_administrator_saves_with_compare_and_swap_and_gets_the_new_revision(self):
        world = World()
        first = world.put('admin_a', world.org_a, 0)
        self.assertEqual((first.status_code, first.json()['revision'], first.json()['name']), (200, 1, 'Acme Labs'))
        second = world.put('admin_a', world.org_a, 1, {**BRANDING, 'name': 'Acme Two'})
        self.assertEqual((second.status_code, second.json()['revision']), (200, 2))
        self.assertEqual(second.headers['cache-control'], 'no-store')
        stale = world.put('admin_a', world.org_a, 1, {**BRANDING, 'name': 'Lost update'})
        self.assertEqual((stale.status_code, stale.json()['error']['code']), (409, 'REVISION_CONFLICT'))
        self.assertEqual(world.client.get('/forge/v1/orgs/%s/branding' % world.org_a, headers=world.auth('member_a')).json()['name'], 'Acme Two')

    def test_members_foreign_administrators_and_unknown_orgs_get_404_and_nothing_changes(self):
        world = World()
        for who, org in (('member_a', world.org_a), ('admin_b', world.org_a), ('admin_a', world.org_b), ('admin_a', uuid4())):
            with self.subTest(who=who):
                self.assertEqual(world.put(who, org, 0).status_code, 404)
                self.assertEqual(world.client.post('/forge/v1/orgs/%s/branding/reset' % org, headers=world.auth(who),
                                                   json={'expectedRevision': 0}).status_code, 404)
        self.assertEqual(world.store.public('acme'), DEFAULT)
        self.assertEqual(world.put('stranger', world.org_a, 0).status_code, 404, 'a valid session without membership')
        self.assertEqual(world.put('revoked', world.org_a, 0).status_code, 401)
        self.assertEqual(world.client.put('/forge/v1/orgs/%s/branding' % world.org_a, json={}).status_code, 401)

    def test_invalid_documents_are_422_with_a_fixed_message_that_never_echoes_the_input(self):
        world = World()
        bad = {
            'color': {**BRANDING, 'theme': {**BRANDING['theme'], 'accent': 'red'}},
            'short color': {**BRANDING, 'theme': {**BRANDING['theme'], 'tint': '#12'}},
            'font': {**BRANDING, 'theme': {**BRANDING['theme'], 'heading': 'Comic'}},
            'contrast': {**BRANDING, 'theme': {**BRANDING['theme'], 'primary': '#FFFF00'}},
            'unreadable accent': {**BRANDING, 'theme': {**BRANDING['theme'], 'accent': '#FFEB3B'}},
            'unreadable tint': {**BRANDING, 'theme': {**BRANDING['theme'], 'tint': '#000000'}},
            'control chars': {**BRANDING, 'name': 'Acme\x00Labs'},
            'long name': {**BRANDING, 'name': 'x' * 41},
            'long copy': {**BRANDING, 'loginCopy': 'x' * 281},
            'html in name': {**BRANDING, 'name': '</title><script>alert(1)</script>'},
            'css in name': {**BRANDING, 'name': 'a}body{background:url(//evil.test)}'},
            'css in copy': {**BRANDING, 'loginCopy': 'x{}</style><img src=x onerror=alert(1)>'},
            'unknown key': {**BRANDING, 'css': 'body{display:none}'},
            'unknown theme key': {**BRANDING, 'theme': {**BRANDING['theme'], 'font': 'x'}},
            'missing key': {k: v for k, v in BRANDING.items() if k != 'loginCopy'},
            'unknown asset hash': {**BRANDING, 'assets': {'logoLight': 'e' * 64}},
            'asset not a hash': {**BRANDING, 'assets': {'logoLight': 'https://evil.test/x.png'}},
            'unknown asset kind': {**BRANDING, 'assets': {'favicon': 'e' * 64}},
        }
        for name, document in bad.items():
            with self.subTest(case=name):
                response = world.put('admin_a', world.org_a, 0, document)
                self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))
                for echoed in ('script', 'evil.test', 'Comic', 'onerror', 'body{'):
                    self.assertNotIn(echoed, response.text)
        self.assertEqual(world.store.public('acme'), DEFAULT)

    def test_an_unreadable_palette_is_refused_with_its_own_message_and_nothing_is_stored(self):
        world = World()
        for color in ({'accent': '#FFEB3B'}, {'tint': '#4A5568'}):
            response = world.put('admin_a', world.org_a, 0, {**BRANDING, 'theme': {**BRANDING['theme'], **color}})
            self.assertEqual(response.status_code, 422)
            self.assertIn('readable theme', response.json()['error']['message'])
        self.assertEqual(world.store.public('acme'), DEFAULT)

    def test_malformed_envelopes_and_transports_are_refused(self):
        world = World()
        url = '/forge/v1/orgs/%s/branding' % world.org_a
        headers = {**world.auth('admin_a'), 'Content-Type': 'application/json'}
        for body in ('', 'not json', '[]', '{}', '{"expectedRevision":0}', '{"branding":%s}' % json.dumps(BRANDING),
                     json.dumps({'expectedRevision': '0', 'branding': BRANDING}), json.dumps({'expectedRevision': True, 'branding': BRANDING}),
                     json.dumps({'expectedRevision': -1, 'branding': BRANDING}), json.dumps({'expectedRevision': 2 ** 63, 'branding': BRANDING}),
                     json.dumps({'expectedRevision': 0, 'branding': BRANDING, 'extra': 1}),
                     '{"expectedRevision":0,"expectedRevision":1,"branding":%s}' % json.dumps(BRANDING)):
            with self.subTest(body=body[:40]):
                self.assertEqual(world.client.put(url, content=body, headers=headers).status_code, 422)
        self.assertEqual(world.client.put(url, content=json.dumps({'expectedRevision': 0, 'branding': BRANDING}),
                                          headers={**world.auth('admin_a'), 'Content-Type': 'text/plain'}).status_code, 415)
        huge = json.dumps({'expectedRevision': 0, 'branding': {**BRANDING, 'name': 'x' * 20000}})
        self.assertEqual(world.client.put(url, content=huge, headers=headers).status_code, 413)
        self.assertEqual(world.store.public('acme'), DEFAULT)

    def test_reset_is_a_new_default_revision_and_conflicts_on_a_stale_one(self):
        world = World()
        world.put('admin_a', world.org_a, 0, {**BRANDING, 'name': 'Custom'})
        url = '/forge/v1/orgs/%s/branding/reset' % world.org_a
        stale = world.client.post(url, headers=world.auth('admin_a'), json={'expectedRevision': 0})
        self.assertEqual((stale.status_code, stale.json()['error']['code']), (409, 'REVISION_CONFLICT'))
        reset = world.client.post(url, headers=world.auth('admin_a'), json={'expectedRevision': 1})
        self.assertEqual((reset.status_code, reset.json()['revision'], reset.json()['name']), (200, 2, DEFAULT.name))
        for body in ({}, {'expectedRevision': 'x'}, {'expectedRevision': 2, 'extra': 1}, []):
            self.assertEqual(world.client.post(url, headers=world.auth('admin_a'), json=body).status_code, 422)

    def test_a_store_outage_is_503_and_a_full_asset_quota_is_a_422(self):
        world = World()
        world.store.save = MagicMock(side_effect=BrandingUnavailable())
        self.assertEqual(world.put('admin_a', world.org_a, 0).status_code, 503)


class AssetUploadTests(unittest.TestCase):
    def test_a_valid_png_is_stripped_stored_and_reported_by_content_hash(self):
        world = World()
        original = png(extra=(chunk(b'tEXt', b'Comment\x00<script>alert(1)</script>'), chunk(b'eXIf', b'GPS-LOCATION')))
        response = world.upload('admin_a', world.org_a, original)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body['kind'], body['contentType'], body['width'], body['height']), ('logoLight', 'image/png', 64, 48))
        self.assertEqual(body['url'], '/forge/v1/branding/assets/' + body['sha256'])
        self.assertNotEqual(body['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(world.client.get('/forge/v1/branding/assets/' + body['sha256']).status_code, 404, 'not yet published')
        stored = world.store.orgs[world.org_a]['assets'][body['sha256']][1]
        for secret in (b'tEXt', b'eXIf', b'GPS-LOCATION', b'script'):
            self.assertNotIn(secret, stored)

    def test_webp_is_accepted_and_the_declared_type_must_match_the_bytes(self):
        world = World()
        payload = b'\x2f' + struct.pack('<I', 31 | (31 << 14)) + bytes(range(11))
        webp = b'RIFF' + struct.pack('<I', 4 + 8 + len(payload) + len(payload) % 2) + b'WEBP' + b'VP8L' + struct.pack('<I', len(payload)) + payload + b'\x00' * (len(payload) % 2)
        self.assertEqual(world.upload('admin_a', world.org_a, webp, content_type='image/webp').status_code, 201)
        self.assertEqual(world.upload('admin_a', world.org_a, png(), content_type='image/webp').status_code, 415)
        self.assertEqual(world.upload('admin_a', world.org_a, webp, content_type='image/png').status_code, 415)

    def test_svg_other_types_and_hostile_files_are_refused_and_nothing_is_stored(self):
        world = World()
        cases = [(b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', 'image/svg+xml', 415),
                 (b'<svg/>', 'image/png', 415), (b'\xff\xd8\xff\xe0JFIF', 'image/jpeg', 415), (b'GIF89a', 'image/gif', 415),
                 (png(), 'application/octet-stream', 415), (png(), 'text/html', 415), (png(), 'image/png; charset=utf-8', 415),
                 (png()[:-9], 'image/png', 422), (SIGNATURE + b'\x00' * 40, 'image/png', 422),
                 (png(2000, 2000), 'image/png', 422), (png(8, 8), 'image/png', 422),
                 (png() + b'PK\x03\x04' + bytes(30), 'image/png', 422), (b'', 'image/png', 415)]
        for data, content_type, status in cases:
            with self.subTest(content_type=content_type, size=len(data), head=data[:6]):
                self.assertEqual(world.upload('admin_a', world.org_a, data, content_type=content_type).status_code, status)
        self.assertEqual(world.store.orgs[world.org_a]['assets'], {})

    def test_oversize_uploads_are_413_by_header_and_by_stream_without_reading_everything(self):
        world = World()
        big = png() + bytes(300 * 1024)
        self.assertEqual(world.upload('admin_a', world.org_a, big).status_code, 413)
        chunked = world.client.post('/forge/v1/orgs/%s/branding/assets?kind=isotipo' % world.org_a, headers={
            **world.auth('admin_a'), 'Content-Type': 'image/png'}, content=(piece for piece in (big[:100000], big[100000:200000], big[200000:])))
        self.assertEqual(chunked.status_code, 413)
        lying = world.upload('admin_a', world.org_a, png(), headers={'Content-Length': 'abc'})
        self.assertIn(lying.status_code, (400, 422))
        self.assertEqual(world.store.orgs[world.org_a]['assets'], {})

    def test_the_kind_is_required_and_limited_to_the_three_slots(self):
        world = World()
        for kind in ('logoLight', 'logoDark', 'isotipo'):
            self.assertEqual(world.upload('admin_a', world.org_a, png(), kind=kind).status_code, 201)
        for kind in ('favicon', 'LOGOLIGHT', '', 'logoLight,isotipo', '../x'):
            self.assertEqual(world.upload('admin_a', world.org_a, png(), kind=kind).status_code, 422)
        self.assertEqual(world.client.post('/forge/v1/orgs/%s/branding/assets' % world.org_a, content=png(),
                                           headers={**world.auth('admin_a'), 'Content-Type': 'image/png'}).status_code, 422)

    def test_only_an_administrator_of_that_organization_may_upload_and_auth_comes_before_the_body(self):
        world = World()
        for who, org in (('member_a', world.org_a), ('admin_b', world.org_a), ('admin_a', world.org_b), ('admin_a', uuid4())):
            self.assertEqual(world.upload(who, org, png()).status_code, 404)
        self.assertEqual(world.upload('stranger', world.org_a, png()).status_code, 404)
        self.assertEqual(world.upload('revoked', world.org_a, png()).status_code, 401)
        no_auth = world.client.post('/forge/v1/orgs/%s/branding/assets?kind=isotipo' % world.org_a, content=bytes(400 * 1024),
                                    headers={'Content-Type': 'image/png'})
        self.assertEqual(no_auth.status_code, 401)
        self.assertEqual(world.store.orgs[world.org_a]['assets'], {})

    def test_the_asset_quota_is_reported_as_422_not_as_a_server_error(self):
        world = World()
        for index in range(24):
            self.assertEqual(world.upload('admin_a', world.org_a, png(16 + index, 16)).status_code, 201)
        response = world.upload('admin_a', world.org_a, png(200, 200))
        self.assertEqual((response.status_code, response.json()['error']['code']), (422, 'INVALID_REQUEST'))


class ContractAndHeaderTests(unittest.TestCase):
    def test_branding_routes_are_outside_the_pinned_contract(self):
        world = World()
        self.assertEqual(contract.build(world.app), contract.build(create_account_app()))
        self.assertEqual(json.loads(contract.COMMITTED_PATH.read_text('utf-8')), contract.build(world.app))
        self.assertFalse([path for path in world.app.openapi()['paths'] if 'branding' in path])
        routes = {route.path for route in world.app.routes}
        for path in ('/forge/v1/branding', '/forge/v1/branding/assets/{sha256:path}', '/forge/v1/orgs/{organization_id}/branding',
                     '/forge/v1/orgs/{organization_id}/branding/reset', '/forge/v1/orgs/{organization_id}/branding/assets'):
            self.assertIn(path, routes)

    def test_every_authenticated_response_is_private_and_nosniff(self):
        world = World()
        for response in (world.put('admin_a', world.org_a, 0), world.client.get('/forge/v1/orgs/%s/branding' % world.org_a, headers=world.auth('admin_a')),
                         world.upload('admin_a', world.org_a, png()), world.put('member_a', world.org_a, 0)):
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            self.assertEqual(response.headers['referrer-policy'], 'no-referrer')

    def test_other_methods_are_not_allowed(self):
        world = World()
        for method, url in (('post', '/forge/v1/branding'), ('put', '/forge/v1/branding?org=acme'), ('delete', '/forge/v1/branding/assets/' + 'a' * 64),
                            ('post', '/forge/v1/branding/assets/' + 'a' * 64), ('delete', '/forge/v1/orgs/%s/branding' % world.org_a)):
            self.assertEqual(getattr(world.client, method)(url).status_code, 405)


if __name__ == '__main__':
    unittest.main()
