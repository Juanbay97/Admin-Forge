"""End-to-end API isolation proof over real HTTP: two organizations, two keys, the real fake gateway.

The real mvp_local composition runs on a real socket against owned PostgreSQL and streams through the
fake gateway server. Nothing is mocked: sessions, row-level security, key custody and revocation are the
production code paths.
"""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import httpx
from cryptography.fernet import Fernet
from pool_support import assign_key
from forge.fake_gateway import REPLY, FakeGatewayConfiguration, serve as serve_gateway
from forge.mvp_local import serve
from forge.mvp_profile import MVP_PROFILE
from forge.provisioning import SEED, provision
from mvp_support import mvp_database

ORG_PATH = '/forge/v1/orgs/%s'


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def events(text):
    """Decoded ``data:`` documents of an SSE body, ``[DONE]`` kept as the string."""
    items = [block[len('data: '):] for block in text.split('\n\n') if block.startswith('data: ')]
    return [item if item == '[DONE]' else json.loads(item) for item in items]


def joined(lines):
    """Rebuild an SSE body from ``iter_lines`` output (blank lines are the event separators)."""
    return '\n'.join(lines) + '\n\n'


def words(stream_events):
    return ''.join(e['choices'][0]['delta'].get('content', '') for e in stream_events
                   if e != '[DONE]' and 'choices' in e)


class Stack:
    def __init__(self, db, results, gateway, base, secrets, logs, output):
        self.db, self.results, self.gateway, self.base = db, results, gateway, base
        self.secrets, self.logs, self.output = secrets, logs, output
        self.client = httpx.Client(base_url=base, timeout=20)
        self.transcript = []
        self.keys = {r.slug: r.gateway_key for r in results}

    def call(self, method, path, token=None, **kwargs):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        response = self.client.request(method, path, headers=headers, **kwargs)
        if not path.endswith('/accounts/login'):
            self.transcript.append(response.text + json.dumps(dict(response.headers)))
        return response

    def login(self, index, role):
        account = self.results[index].accounts[role]
        response = self.call('POST', '/forge/v1/accounts/login', json={'email': account.email, 'password': account.password})
        assert response.status_code == 200, response.text
        return response.json()['access_token']

    def org(self, index):
        return ORG_PATH % self.results[index].organization_id

    def configure(self, index, aliases):
        """What the admin does: save the key, discover the models, publish aliases."""
        token = self.login(index, 0)
        # A company's key is the platform's: created, assigned and bounded by the owner, never saved by the admin.
        assign_key(self.db, self.secrets['gateway_cipher_key'], self.gateway, self.results[index].organization_id,
                   self.keys[self.results[index].slug], ('fake-fast', 'fake-slow', 'fake-nousage'))
        assert self.call('POST', self.org(index) + '/gateway/catalogue/refresh', token).status_code == 200
        published = self.call('POST', self.org(index) + '/models/publish', token, json={
            'operation_id': str(uuid4()), 'expected_catalogue_revision': 0, 'expected_gateway_revision': 1,
            'aliases': aliases, 'default_alias': next(iter(aliases))})
        assert published.status_code == 200, published.text
        return token

    def chat(self, index, token, model, **kwargs):
        return self.call('POST', self.org(index) + '/chat/completions', token, json={
            'model': model, 'messages': [{'role': 'user', 'content': 'Hello'}], 'stream': True}, **kwargs)

    def gateway_digests(self):
        records = httpx.get(self.gateway + '/__fake/requests').json()['requests']
        return {r['authorization_sha256'] for r in records if r['authorization_sha256']}

    def digest(self, index):
        return hashlib.sha256(('Bearer ' + self.keys[self.results[index].slug]).encode()).hexdigest()

    def stream(self, index, token, model):
        """Read a chat stream in a thread; ``first`` is set at the first text chunk."""
        state = {'lines': [], 'first': threading.Event(), 'status': None}

        def read():
            with httpx.Client(base_url=self.base, timeout=30) as client:
                with client.stream('POST', self.org(index) + '/chat/completions', headers={'Authorization': 'Bearer ' + token},
                                   json={'model': model, 'messages': [{'role': 'user', 'content': 'Hello'}], 'stream': True}) as response:
                    state['status'] = response.status_code
                    for line in response.iter_lines():
                        state['lines'].append(line)
                        if '"content":"' in line:
                            state['first'].set()
            state['first'].set()
        state['thread'] = threading.Thread(target=read, daemon=True)
        state['thread'].start()
        return state

    def assert_no_secret(self, *extra):
        everything = '\n'.join(['\n'.join(self.logs.lines), self.output.getvalue(), *self.transcript, *extra])
        leaked = [name for name, value in self.secrets.items() if value in everything]
        assert not leaked, 'leaked: %s' % leaked


@contextmanager
def stack(slow_delay=1.0):
    collector, output = Collector(), StringIO()
    root_logger = logging.getLogger()
    previous = root_logger.level
    root_logger.addHandler(collector)
    root_logger.setLevel(logging.DEBUG)
    try:
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            cleanup.enter_context(redirect_stdout(output))
            cleanup.enter_context(redirect_stderr(output))
            results = provision(db.admin, SEED, lambda created: None)
            gateway_port, control_port, client_port = free_port(), free_port(), free_port()
            gateway_stop, control_stop, failures = threading.Event(), threading.Event(), []

            def guarded(target, *args, **kwargs):
                try:
                    target(*args, **kwargs)
                except Exception as error:
                    failures.append(error)
            gateway = threading.Thread(target=guarded, daemon=True, args=(
                serve_gateway, FakeGatewayConfiguration(keys=tuple(r.gateway_key for r in results), port=gateway_port,
                                                        slow_delay_seconds=slow_delay)), kwargs={'stopping': gateway_stop})
            gateway.start()
            root = Path(directory)
            (root/'mailbox').mkdir()
            (root/'admin').mkdir()
            secrets = {'roles': dict(db.passwords), 'delivery_key': Fernet.generate_key().decode(),
                       'gateway_key': Fernet.generate_key().decode(), 'platform_key': Fernet.generate_key().decode()}
            (root/'secrets.json').write_text(json.dumps(secrets), 'utf-8')
            values = db.connection_settings()
            gateway_origin = 'http://127.0.0.1:%d' % gateway_port
            (root/'config.json').write_text(json.dumps({
                'version': 1, 'profile': MVP_PROFILE, 'database': {k: values[k] for k in ('host', 'port', 'dbname')},
                'secrets_file': str(root/'secrets.json'), 'mailbox_dir': str(root/'mailbox'), 'admin_dir': str(root/'admin'),
                'require_admin_build': False, 'control_plane_port': control_port,
                'client_origin': 'http://127.0.0.1:%d' % client_port, 'cors_origins': ['http://127.0.0.1:%d' % client_port],
                'gateway_allowed_endpoints': [gateway_origin]}), 'utf-8')
            control = threading.Thread(target=guarded, daemon=True, args=(serve, str(root/'config.json')),
                                       kwargs={'stopping': control_stop})
            control.start()
            cleanup.callback(lambda: (control_stop.set(), control.join(20), gateway_stop.set(), gateway.join(10)))
            base = 'http://127.0.0.1:%d' % control_port
            for _ in range(150):
                try:
                    if httpx.get(base + '/status', timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise AssertionError('control plane did not become ready: %r' % failures)
            flat = {'db_' + role: password for role, password in secrets['roles'].items()}
            flat.update(delivery_key=secrets['delivery_key'], gateway_cipher_key=secrets['gateway_key'])
            for result in results:
                flat['gateway_key_' + result.slug] = result.gateway_key
                for account in result.accounts:
                    flat['password_' + account.email] = account.password
            yield Stack(db, results, gateway_origin, base, flat, collector, output)
            assert not failures, failures
    finally:
        root_logger.removeHandler(collector)
        root_logger.setLevel(previous)


@unittest.skipUnless(os.environ.get('FORGE_PG_HARNESS') == 'owned-disposable-v1',
                     'Needs the owned PostgreSQL harness: scripts/test-postgres.ps1 -TestPattern test_mvp_api_isolation.py')
class ApiIsolationTests(unittest.TestCase):
    def test_every_cross_organization_request_is_the_same_404_in_both_directions(self):
        with stack() as s:
            tokens = {0: s.configure(0, {'assistant': 'fake-fast'}), 1: s.configure(1, {'helper': 'fake-fast'})}
            members = {i: s.login(i, 1) for i in (0, 1)}
            unknown = ORG_PATH % uuid4()
            member_ids = {i: next(m['id'] for m in s.call('GET', s.org(i) + '/members', tokens[i]).json()['members']
                                  if m['email'] == s.results[i].accounts[1].email) for i in (0, 1)}
            publish = {'operation_id': str(uuid4()), 'expected_catalogue_revision': 1, 'expected_gateway_revision': 1,
                       'aliases': {'x': 'fake-fast'}, 'default_alias': 'x'}

            def requests(prefix, member_id):
                return [('GET', prefix + '/gateway', None), ('PUT', prefix + '/gateway', {'expected_revision': 1, 'api_key': 'stolen'}),
                        ('GET', prefix + '/gateway/catalogue/status', None), ('POST', prefix + '/gateway/catalogue/refresh', None),
                        ('POST', prefix + '/models/publish', publish), ('GET', prefix + '/models', None),
                        ('GET', prefix + '/members', None), ('GET', prefix + '/departments', None),
                        ('POST', prefix + '/departments', {'name': 'Intruders'}),
                        ('POST', prefix + '/members/%s/suspend' % member_id, None),
                        ('POST', prefix + '/members/%s/reactivate' % member_id, None),
                        ('POST', prefix + '/chat/completions', {'model': 'helper', 'stream': True,
                                                                'messages': [{'role': 'user', 'content': 'x'}]})]
            seen = 0
            for actor, foreign in ((0, 1), (1, 0)):
                for method, path, body in requests(s.org(foreign), member_ids[foreign]):
                    with self.subTest(actor=actor, request=method + ' ' + path.replace(s.org(foreign), '<org>')):
                        response = s.call(method, path, tokens[actor], **({} if body is None else {'json': body}))
                        reference = s.call(method, path.replace(s.org(foreign), unknown), tokens[actor],
                                           **({} if body is None else {'json': body}))
                        self.assertEqual((response.status_code, response.json()['error']['code']), (404, 'NOT_FOUND'))
                        self.assertEqual((response.status_code, response.json()['error']['code']),
                                         (reference.status_code, reference.json()['error']['code']))
                        seen += 1
            self.assertEqual(seen, 24)
            invite = s.call('POST', '/forge/v1/accounts/invitations', tokens[0], json={
                'organization_id': str(s.results[1].organization_id), 'department_id': str(s.results[1].department_id),
                'email': 'spy@example.com', 'name': 'Spy'})
            self.assertEqual(invite.status_code, 404)
            # A plain member is no administrator of their own organization either.
            for method, path in (('GET', '/members'), ('GET', '/gateway'), ('POST', '/gateway/catalogue/refresh')):
                self.assertEqual(s.call(method, s.org(0) + path, members[0]).status_code, 404, path)
            # Nothing of organization B changed, and its administrator still sees exactly their own data.
            self.assertEqual(sorted(m['status'] for m in s.call('GET', s.org(1) + '/members', tokens[1]).json()['members']),
                             ['active', 'active'])
            self.assertEqual([d['name'] for d in s.call('GET', s.org(1) + '/departments', tokens[1]).json()['departments']],
                             ['Finance'])

    def test_the_provider_key_is_absent_from_responses_logs_storage_and_streams_and_stays_per_organization(self):
        with stack(slow_delay=0.0) as s:
            admin_a, admin_b = s.configure(0, {'assistant': 'fake-fast'}), s.configure(1, {'helper': 'fake-fast'})
            self.assertEqual(s.gateway_digests(), {s.digest(0), s.digest(1)})
            httpx.post(s.gateway + '/__fake/reset')
            member_a, member_b = s.login(0, 1), s.login(1, 1)
            reply_a = s.chat(0, member_a, 'assistant')
            self.assertEqual(s.gateway_digests(), {s.digest(0)}, 'organization A traffic must carry only key A')
            httpx.post(s.gateway + '/__fake/reset')
            reply_b = s.chat(1, member_b, 'helper')
            self.assertEqual(s.gateway_digests(), {s.digest(1)}, 'organization B traffic must carry only key B')
            for reply in (reply_a, reply_b):
                documents = events(reply.text)
                self.assertEqual((reply.status_code, documents[-1], words(documents)), (200, '[DONE]', REPLY))
                self.assertEqual(documents[-2]['choices'][0]['finish_reason'], 'stop')
            for index, token in ((0, admin_a), (1, admin_b)):
                status = s.call('GET', s.org(index) + '/gateway', token).json()
                self.assertEqual(set(status), {'status', 'revision', 'endpoint', 'allowed_endpoints'})
            stored = ' '.join(row[0] for row in s.db.admin.execute('SELECT row_to_json(g)::text FROM forge.gateway_keys g'))
            self.assertEqual(s.db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (2,))
            s.assert_no_secret(stored, reply_a.text, reply_b.text)
            self.assertEqual(len(set(s.keys.values())), 2)

    def test_a_member_sees_and_uses_only_the_aliases_published_for_their_organization(self):
        with stack(slow_delay=0.0) as s:
            s.configure(0, {'assistant': 'fake-fast', 'slow': 'fake-slow'})
            s.configure(1, {'helper': 'fake-fast'})
            member_a, member_b = s.login(0, 1), s.login(1, 1)
            catalog_a = s.call('GET', s.org(0) + '/models', member_a).json()
            self.assertEqual((sorted(m['id'] for m in catalog_a['models']), catalog_a['default_model']),
                             (['assistant', 'slow'], 'assistant'))
            self.assertEqual([m['id'] for m in s.call('GET', s.org(1) + '/models', member_b).json()['models']], ['helper'])
            for model in ('fake-fast', 'fake-error', 'helper'):
                with self.subTest(model=model):
                    self.assertEqual(s.chat(0, member_a, model).status_code, 404)
            self.assertEqual(s.chat(1, member_b, 'assistant').status_code, 404)
            self.assertEqual(s.call('GET', s.org(1) + '/models', member_a).status_code, 404)
            self.assertEqual(s.call('GET', s.org(0) + '/models', member_b).status_code, 404)
            for text in (s.chat(0, member_a, 'assistant').text, s.chat(1, member_b, 'helper').text):
                self.assertEqual(words(events(text)), REPLY)
            s.assert_no_secret()

    def test_a_metered_chat_records_usage_for_the_right_company_member_and_key_and_nothing_else(self):
        with stack(slow_delay=0.0) as s:
            s.configure(0, {'assistant': 'fake-fast', 'quiet': 'fake-nousage'})
            s.configure(1, {'helper': 'fake-fast'})
            member_a, member_b = s.login(0, 1), s.login(1, 1)

            def wait_for(count, org):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    rows = s.db.admin.execute('SELECT usage_source,status,prompt_tokens,completion_tokens,upstream_id,key_id IS NOT NULL,error_code '
                                              'FROM forge.usage_events WHERE organization_id=%s ORDER BY recorded_at', (org,)).fetchall()
                    if len(rows) >= count:
                        return rows
                    time.sleep(0.1)
                return rows
            self.assertEqual(s.chat(0, member_a, 'assistant').status_code, 200)
            self.assertEqual(wait_for(1, s.results[0].organization_id), [('gateway', 'ok', 2, 6, 'fake-fast', True, None)])
            self.assertEqual(s.chat(0, member_a, 'quiet').status_code, 200)
            rows = wait_for(2, s.results[0].organization_id)
            self.assertEqual(rows[1], ('estimated', 'ok', 2, 8, 'fake-nousage', True, None), 'no usage chunk: estimated from characters')
            self.assertEqual(s.chat(1, member_b, 'helper').status_code, 200)
            self.assertEqual(len(wait_for(1, s.results[1].organization_id)), 1)
            daily = s.db.admin.execute('SELECT organization_id,sum(requests),sum(prompt_tokens),sum(completion_tokens),sum(estimated_requests) '
                                       'FROM forge.usage_daily GROUP BY 1 ORDER BY 2 DESC').fetchall()
            self.assertEqual(daily, [(s.results[0].organization_id, 2, 4, 14, 1), (s.results[1].organization_id, 1, 2, 6, 0)])
            members = {row[0] for row in s.db.admin.execute('SELECT membership_id FROM forge.usage_events WHERE organization_id=%s', (s.results[0].organization_id,))}
            self.assertEqual(len(members), 1)
            self.assertEqual(s.chat(0, member_a, 'fake-fast').status_code, 404, 'a refused alias reaches no gateway and records nothing')
            time.sleep(0.3)
            self.assertEqual(s.db.admin.execute('SELECT count(*) FROM forge.usage_events').fetchone(), (3,))
            dump = repr(s.db.admin.execute('SELECT * FROM forge.usage_events').fetchall())
            s.assert_no_secret(dump)

    def test_suspending_a_member_mid_stream_stops_the_stream_and_denies_everything_after(self):
        with stack(slow_delay=1.0) as s:
            admin = s.configure(0, {'slow': 'fake-slow', 'assistant': 'fake-fast'})
            s.configure(1, {'helper': 'fake-fast'})
            member, other = s.login(0, 1), s.login(1, 1)
            member_id = next(m['id'] for m in s.call('GET', s.org(0) + '/members', admin).json()['members']
                             if m['email'] == s.results[0].accounts[1].email)
            state = s.stream(0, member, 'slow')
            self.assertTrue(state['first'].wait(15), state['lines'])
            suspended = s.call('POST', s.org(0) + '/members/%s/suspend' % member_id, admin)
            self.assertEqual((suspended.status_code, suspended.json()['status']), (200, 'suspended'))
            state['thread'].join(20)
            self.assertFalse(state['thread'].is_alive())
            documents = events(joined(state['lines']))
            self.assertEqual(state['status'], 200)
            self.assertEqual(documents[-2]['error']['code'], 'INFERENCE_UNAVAILABLE')
            self.assertFalse(any(d != '[DONE]' and 'choices' in d and d['choices'][0]['finish_reason'] == 'stop' for d in documents))
            self.assertLess(len(words(documents)), len(REPLY))
            # The revoked session is dead everywhere; a fresh login is refused as suspended, not empty.
            self.assertEqual(s.call('GET', '/forge/v1/accounts/me', member).status_code, 401)
            self.assertEqual(s.chat(0, member, 'assistant').status_code, 401)
            again = s.login(0, 1)
            me = s.call('GET', '/forge/v1/accounts/me', again)
            self.assertEqual((me.status_code, me.json()['error']['code']), (403, 'MEMBERSHIP_SUSPENDED'))
            self.assertNotEqual(s.chat(0, again, 'assistant').status_code, 200)
            # Organization B is untouched by A's suspension.
            self.assertEqual(words(events(s.chat(1, other, 'helper').text)), REPLY)
            # Reactivation restores access for a new session.
            self.assertEqual(s.call('POST', s.org(0) + '/members/%s/reactivate' % member_id, admin).json()['status'], 'active')
            restored = s.login(0, 1)
            self.assertEqual(words(events(s.chat(0, restored, 'assistant').text)), REPLY)
            s.assert_no_secret()

    def test_logout_revokes_only_that_session_including_an_open_stream(self):
        with stack(slow_delay=1.0) as s:
            s.configure(0, {'slow': 'fake-slow', 'assistant': 'fake-fast'})
            first, second = s.login(0, 1), s.login(0, 1)
            state = s.stream(0, first, 'slow')
            self.assertTrue(state['first'].wait(15), state['lines'])
            self.assertEqual(s.call('POST', '/forge/v1/accounts/logout', first).status_code, 204)
            state['thread'].join(20)
            self.assertFalse(state['thread'].is_alive())
            documents = events(joined(state['lines']))
            self.assertEqual(documents[-2]['error']['code'], 'INFERENCE_UNAVAILABLE')
            self.assertLess(len(words(documents)), len(REPLY))
            for method, path in (('GET', '/forge/v1/accounts/me'), ('GET', s.org(0) + '/models')):
                self.assertEqual(s.call(method, path, first).status_code, 401, path)
            self.assertEqual(s.chat(0, first, 'assistant').status_code, 401)
            self.assertEqual(s.call('POST', '/forge/v1/accounts/logout', first).status_code, 401)
            self.assertEqual(s.call('GET', '/forge/v1/accounts/me', second).status_code, 200)
            self.assertEqual(words(events(s.chat(0, second, 'assistant').text)), REPLY)


if __name__ == '__main__':
    unittest.main()
