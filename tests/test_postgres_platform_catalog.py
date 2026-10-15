"""Owned PostgreSQL 0048 platform catalog: a fresh verified platform owner discovers the models of a company's assigned keys,
selects aliases and a default and publishes the company catalog, reusing the company snapshot, selection and rebinding tables.

Every function re-validates the owner; a company administrator, a member and a password-only owner are denied; the ceiling
becomes the selected upstream models in the same transaction; the member read model and the administrator status stay as they were.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
import httpx
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.gateway_catalog import publication_material
from forge.gateway_catalog_adapter import HttpxModelsAdapter
from forge.mvp_profile import F47, F48, MVP_ADDITIONS, MVP_CHECKPOINTS, PLATFORM_CATALOG_MIGRATION
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import OWNER_EMAIL, PASSWORD, add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import GATEWAY, login, stack
from test_postgres_platform_http import BASE, Person, code_for
from test_postgres_platform_schema import drop_platform_roles

SEALED = 'sealed-fixture-' + 'x' * 120
ORIGIN = 'https://gateway.fixture.example'
KEY, SECOND = 'pool-fixture-key-ABCD', 'pool-fixture-key-WXYZ'
SERVED = {KEY: ['gpt-a', 'gpt-b', 'shared'], SECOND: ['claude-c', 'shared']}


class CatalogProfileTests(unittest.TestCase):
    def test_0048_follows_0047_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_CATALOG_MIGRATION, '0048_platform_catalog.sql')
        self.assertEqual(MVP_ADDITIONS[at(PLATFORM_CATALOG_MIGRATION) - 1], '0047_client_attestation.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(PLATFORM_CATALOG_MIGRATION):at(PLATFORM_CATALOG_MIGRATION) + 2], (F47, F48))
        self.assertRegex(F48 or '', r'^[0-9a-f]{64}$', 'F48 must be pinned')
        self.assertNotEqual(F48, F47)


class CatalogFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0047_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(PLATFORM_CATALOG_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_CATALOG_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F47)
            result = provision(conn, SEED[:1], lambda created: None)[0]
            conn.execute(migration_text(PLATFORM_CATALOG_MIGRATION))
            self.assertEqual(conn.execute('SELECT slug FROM forge.organizations').fetchall(), [(result.slug,)])
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0048 platform catalog checkpoint F48:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0047 must be identical')
        self.assertEqual(fresh, F48, 'F48 must be pinned to the reviewed value')


CATALOG_FUNCTIONS = ('forge.platform_catalog_keys(text,uuid)', 'forge.platform_catalog_discovery_save(text,uuid,bigint,uuid,jsonb)',
                     'forge.platform_catalog_status(text,uuid)',
                     'forge.platform_catalog_publish(text,uuid,uuid,bigint,bigint,uuid,jsonb,text,text,text,text)')
HELPERS = ('forge.platform_catalog_authorize(text,uuid,boolean)', 'forge.platform_catalog_record(uuid,uuid,text,text[])')


class SchemaWorld(unittest.TestCase):
    def build(self, db, *, mfa=True):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.admins = {result.slug: result.accounts[0] for result in results}
        self.org = results[0].organization_id
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=mfa)
        self.key_ids = []
        for label, hint in (('primary', 'ABCD'), ('backup', 'WXYZ')):
            key = uuid4()
            call(db, 'SELECT * FROM forge.platform_gateway_key_create(%s,%s,%s,%s,%s,%s)', (self.digest, key, label, ORIGIN, SEALED + label, hint))
            self.key_ids.append(key)
        call(db, 'SELECT * FROM forge.platform_company_gateway_set(%s,%s,%s::jsonb)', (self.digest, self.org, json.dumps(
            [{'key_id': str(self.key_ids[0]), 'priority': 1, 'active': True}, {'key_id': str(self.key_ids[1]), 'priority': 2, 'active': False}])))

    def audit(self):
        return [row[0] for row in self.db.admin.execute('SELECT action FROM forge.platform_audit_log ORDER BY id').fetchall()]

    def save(self, ids, *, revision=1, binding=None, digest=None, org=None):
        binding = binding or self.db.admin.execute('SELECT binding_id FROM forge.organization_gateway_profiles WHERE organization_id=%s',
                                                   (org or self.org,)).fetchone()[0]
        return call(self.db, 'SELECT forge.platform_catalog_discovery_save(%s,%s,%s,%s,%s::jsonb)',
                    (digest or self.digest, org or self.org, revision, binding, json.dumps(ids)))

    def publish(self, mapping, default, *, expected=0, revision=1, operation=None, digest=None, org=None):
        org = org or self.org
        binding = self.db.admin.execute('SELECT binding_id FROM forge.organization_gateway_profiles WHERE organization_id=%s', (org,)).fetchone()[0]
        payload, checksum, selection = publication_material(org, binding, expected, revision, mapping, default)
        return call(self.db, 'SELECT forge.platform_catalog_publish(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)',
                    (digest or self.digest, org, operation or uuid4(), expected, revision, binding, json.dumps(mapping), default,
                     payload, checksum, selection))


class CatalogFunctionTests(SchemaWorld):
    def test_the_functions_are_owned_by_the_gateway_authority_and_only_the_service_can_run_them(self):
        with mvp_database() as db:
            owner = 'SELECT pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig FROM pg_proc p WHERE p.oid=%s::regprocedure'
            execute = "SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')"
            for signature in CATALOG_FUNCTIONS:
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute(owner, (signature,)).fetchone(), ('forge_gateway_authority', True, ['search_path=pg_catalog']))
                    for role, allowed in (('forge_platform_service', True), ('public', False), ('forge_gateway_service', False),
                                          ('forge_account_service', False), ('forge_runtime', False), ('forge_branding_service', False)):
                        self.assertEqual(db.admin.execute(execute, (role, signature)).fetchone(), (allowed,), role)
            for signature in HELPERS:
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute(owner, (signature,)).fetchone(), ('forge_platform_authority', True, ['search_path=pg_catalog']))
                    for role, allowed in (('forge_gateway_authority', True), ('forge_platform_service', False), ('public', False),
                                          ('forge_gateway_service', False)):
                        self.assertEqual(db.admin.execute(execute, (role, signature)).fetchone(), (allowed,), role)
            for role in ('forge_platform_authority', 'forge_gateway_authority'):
                self.assertEqual(db.admin.execute("SELECT has_schema_privilege(%s,'forge','CREATE')", (role,)).fetchone(), (False,))

    def test_keys_returns_the_assignment_in_priority_order_with_the_sealed_value_and_audits_the_read(self):
        with mvp_database() as db:
            self.build(db)
            rows = call(db, 'SELECT * FROM forge.platform_catalog_keys(%s,%s)', (self.digest, self.org))
            binding = db.admin.execute('SELECT binding_id FROM forge.organization_gateway_profiles').fetchone()[0]
            self.assertEqual([(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]) for row in rows],
                             [(1, binding, self.key_ids[0], 'primary', ORIGIN, 1, True, 'active', 1),
                              (1, binding, self.key_ids[1], 'backup', ORIGIN, 2, False, 'active', 1)])
            self.assertEqual([row[9] for row in rows], [SEALED + 'primary', SEALED + 'backup'])
            self.assertEqual(self.audit()[-1], 'company.models_discovered')
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_catalog_keys(%s,%s)', (self.digest, self.orgs[SEED[1].slug])), [],
                             'a company without an assignment has no rows')

    def test_discovery_is_stored_for_the_profile_and_refused_for_a_stale_revision_or_a_bad_list(self):
        with mvp_database() as db:
            self.build(db)
            stamp = self.save(['gpt-a', 'gpt-b'])[0][0]
            self.assertIsNotNone(stamp)
            self.assertEqual(db.admin.execute('SELECT model_ids FROM forge.gateway_model_discoveries').fetchone(), (['gpt-a', 'gpt-b'],))
            self.assertEqual(refusal(self, lambda: self.save(['gpt-a'], revision=2)), 'REVISION_CONFLICT')
            self.assertEqual(refusal(self, lambda: self.save(['gpt-a'], binding=uuid4())), 'REVISION_CONFLICT')
            for bad in ([], ['a', 'a'], ['has space'], [1], ['x' * 256]):
                with self.subTest(ids=bad):
                    self.assertEqual(refusal(self, lambda: self.save(bad)), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: self.save(['gpt-a'], org=uuid4(), binding=uuid4())), 'PLATFORM_NOT_FOUND')
            self.assertEqual(db.admin.execute('SELECT model_ids FROM forge.gateway_model_discoveries').fetchone(), (['gpt-a', 'gpt-b'],))

    def test_status_reports_the_profile_the_discovery_and_the_published_selection(self):
        with mvp_database() as db:
            self.build(db)
            status = 'SELECT * FROM forge.platform_catalog_status(%s,%s)'
            self.assertEqual(call(db, status, (self.digest, self.orgs[SEED[1].slug])), [], 'no profile, no row')
            first = call(db, status, (self.digest, self.org))[0]
            self.assertEqual((first[0], first[2], first[3], first[4], first[5], first[6], first[7], first[8]),
                             (1, [], None, None, 0, None, 'UNPUBLISHED', None))
            self.save(['gpt-a', 'gpt-b'])
            self.assertEqual(self.publish({'fast': 'gpt-a', 'deep': 'gpt-b'}, 'fast'), [(1,)])
            after = call(db, status, (self.digest, self.org))[0]
            self.assertEqual((after[2], after[3], after[5], after[6], after[7], after[8]),
                             (['gpt-a', 'gpt-b'], ['gpt-a', 'gpt-b'], 1, 'fast', 'CURRENT', {'fast': 'gpt-a', 'deep': 'gpt-b'}))

    def test_publish_writes_the_company_catalog_sets_the_ceiling_and_leaves_the_member_and_admin_reads_unchanged(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a', 'gpt-b', 'gpt-c'])
            self.assertEqual(self.publish({'fast': 'gpt-a', 'deep': 'gpt-c'}, 'deep'), [(1,)])
            self.assertEqual(db.admin.execute('SELECT ceiling FROM forge.organization_gateway_profiles').fetchone(), (['gpt-a', 'gpt-c'],))
            self.assertEqual(db.admin.execute('SELECT catalog_revision FROM forge.active_model_catalogs WHERE organization_id=%s', (self.org,)).fetchone(), (1,))
            self.assertEqual(db.admin.execute('SELECT default_alias,private_mapping FROM forge.gateway_catalog_selections').fetchone(),
                             ('deep', {'fast': 'gpt-a', 'deep': 'gpt-c'}))
            member = db.admin.execute('SELECT actor_id FROM forge.catalog_publication_operations').fetchone()[0]
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.membership_roles WHERE membership_id=%s AND role=%s',
                                              (member, 'organization_admin')).fetchone(), (1,), 'the event names an administrator of the company')
            self.assertEqual(self.audit()[-1], 'company.catalog_published')
            # The administrator's read model (0033) and the member read are the ones the company flow always served.
            admin = self.admins[SEED[0].slug]
            _, admin_digest = sign_in(db, admin.email, admin.password)
            self.assertEqual(call(db, 'SELECT * FROM forge.gateway_catalog_admin_status(%s,%s)', (admin_digest, self.org), role='forge_gateway_service'),
                             [(1, 'deep', 'CURRENT')])
            member_row = call(db, 'SELECT default_alias FROM forge.gateway_catalog_member(%s,%s)', (admin_digest, self.org), role='forge_gateway_service')
            self.assertEqual(member_row, [('deep',)])

    def test_publish_is_replay_safe_and_a_stale_or_unknown_selection_changes_nothing(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a', 'gpt-b'])
            operation = uuid4()
            self.assertEqual(self.publish({'fast': 'gpt-a'}, 'fast', operation=operation), [(1,)])
            self.assertEqual(self.publish({'fast': 'gpt-a'}, 'fast', operation=operation), [(1,)], 'the same operation is replayed, not repeated')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(), (1,))
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'gpt-b'}, 'fast', operation=operation)), 'REVISION_CONFLICT')
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'gpt-b'}, 'fast', expected=0)), 'REVISION_CONFLICT')
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'not-discovered'}, 'fast', expected=1)), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'gpt-b'}, 'fast', expected=1, revision=2)), 'REVISION_CONFLICT')
            self.assertEqual(db.admin.execute('SELECT ceiling FROM forge.organization_gateway_profiles').fetchone(), (['gpt-a'],),
                             'a refused publication leaves the ceiling as it was')
            self.assertEqual(self.audit().count('company.catalog_published'), 1, 'a replay and a refusal write no second audit row')
            self.assertEqual(self.publish({'fast': 'gpt-b', 'other': 'gpt-a'}, 'fast', expected=1), [(2,)])
            self.assertEqual(db.admin.execute('SELECT ceiling FROM forge.organization_gateway_profiles').fetchone(), (['gpt-a', 'gpt-b'],))

    def test_a_company_without_an_active_member_and_a_suspended_company_cannot_publish(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a'])
            db.admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s", (self.org,))
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'gpt-a'}, 'fast')), 'CATALOG_NO_MEMBER')
            db.admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s", (self.org,))
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org,))
            self.assertEqual(refusal(self, lambda: self.publish({'fast': 'gpt-a'}, 'fast')), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: self.save(['gpt-a'])), 'PLATFORM_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(), (0,))

    def test_a_company_admin_a_member_and_a_password_only_owner_are_denied_everywhere(self):
        with mvp_database() as db:
            self.build(db)
            admin = self.admins[SEED[0].slug]
            _, admin_digest = sign_in(db, admin.email, admin.password)
            calls = (lambda digest: call(db, 'SELECT * FROM forge.platform_catalog_keys(%s,%s)', (digest, self.org)),
                     lambda digest: call(db, 'SELECT * FROM forge.platform_catalog_status(%s,%s)', (digest, self.org)),
                     lambda digest: self.save(['gpt-a'], digest=digest),
                     lambda digest: self.publish({'fast': 'gpt-a'}, 'fast', digest=digest))
            for run in calls:
                self.assertEqual(refusal(self, lambda: run(admin_digest)), 'PLATFORM_DENIED')
                self.assertEqual(refusal(self, lambda: run('0' * 64)), 'PLATFORM_DENIED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_model_discoveries').fetchone(), (0,))
            self.assertNotIn('company.models_discovered', self.audit())


class CatalogMfaTests(SchemaWorld):
    def test_a_password_only_owner_session_cannot_read_keys_discover_or_publish(self):
        with mvp_database() as db:
            self.build(db)
            _, weak = sign_in(db, mfa=False)  # a second session of the same owner that never passed the code step
            for run in (lambda: call(db, 'SELECT * FROM forge.platform_catalog_keys(%s,%s)', (weak, self.org)),
                        lambda: call(db, 'SELECT * FROM forge.platform_catalog_status(%s,%s)', (weak, self.org)),
                        lambda: self.save(['gpt-a'], digest=weak), lambda: self.publish({'fast': 'gpt-a'}, 'fast', digest=weak)):
                self.assertEqual(refusal(self, run), 'MFA_REQUIRED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_model_discoveries').fetchone(), (0,))
            self.assertNotIn('company.models_discovered', self.audit())


def models_handler(request):
    key = request.headers.get('authorization', '')[len('Bearer '):]
    if key not in SERVED:
        return httpx.Response(401, json={'error': 'denied'})
    return httpx.Response(200, json={'data': [{'id': model} for model in SERVED[key]]})


def mocked_adapter(**keywords):
    return HttpxModelsAdapter(transport=httpx.MockTransport(models_handler), **keywords)


class PostgresPlatformCatalogHttpTests(unittest.TestCase):
    def verified_owner(self, db, client):
        add_owner(db.admin)
        headers = login(client, Person(OWNER_EMAIL, PASSWORD))
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers).json()
        self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
        return headers

    def keys(self, client, owner, org, *pairs):
        ids = []
        for label, key in pairs:
            created = client.post(BASE + '/gateway-keys', headers=owner, json={'label': label, 'origin': GATEWAY, **({} if key is None else {'key': key})})
            self.assertEqual(created.status_code, 201, created.text)
            ids.append(created.json()['id'])
        assigned = client.put(BASE + '/companies/%s/gateway-keys' % org, headers=owner,
                              json={'keys': [{'key_id': key_id, 'priority': index + 1, 'active': True} for index, key_id in enumerate(ids)]})
        self.assertEqual(assigned.status_code, 200, assigned.text)
        return ids

    def test_the_owner_discovers_selects_and_publishes_and_the_company_reads_the_published_catalog_without_any_key_text(self):
        with patch('forge.gateway_catalog_adapter.HttpxModelsAdapter', mocked_adapter), stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            path = BASE + '/companies/%s/catalog' % org
            self.assertEqual(client.get(path, headers=owner).json(), {'configured': False})
            ids = self.keys(client, owner, org, ('primary', KEY), ('backup', SECOND), ('spare', None))
            seen = []
            first = client.get(path, headers=owner).json()
            self.assertEqual((first['configured'], first['discovered'], first['catalogue']['state'], first['ceiling']), (True, None, 'UNPUBLISHED', []))
            discovered = client.post(path + '/discover', headers=owner, json={})
            seen.append(discovered.text)
            self.assertEqual(discovered.status_code, 200, discovered.text)
            body = discovered.json()
            self.assertEqual(body['model_ids'], ['claude-c', 'gpt-a', 'gpt-b', 'shared'])
            self.assertEqual([(item['label'], item['state'], item['model_count']) for item in body['keys']],
                             [('primary', 'ok', 3), ('backup', 'ok', 2), ('spare', 'no_key', 0)])
            self.assertEqual([item['key_id'] for item in body['keys']], ids)
            published = client.put(path, headers=owner, json={'expected_catalogue_revision': 0, 'expected_gateway_revision': first['gateway_revision'],
                                                              'aliases': {'fast': 'gpt-a', 'deep': 'claude-c'}, 'default_alias': 'deep'})
            seen.append(published.text)
            self.assertEqual((published.status_code, published.json()), (200, {'revision': 1, 'default_model': 'deep', 'models': ['deep', 'fast']}))
            after = client.get(path, headers=owner).json()
            seen.append(json.dumps(after))
            self.assertEqual((after['catalogue'], after['ceiling']), ({'revision': 1, 'default_model': 'deep', 'state': 'CURRENT',
                                                                       'aliases': {'deep': 'claude-c', 'fast': 'gpt-a'}}, ['claude-c', 'gpt-a']))
            self.assertEqual(after['discovered']['model_ids'], body['model_ids'])
            admin_headers = login(client, results[0].accounts[0])
            status = client.get('/forge/v1/orgs/%s/gateway/catalogue/status' % org, headers=admin_headers).json()
            self.assertEqual(status, {'catalogue_revision': 1, 'default_model': 'deep', 'publication_state': 'CURRENT'})
            listed = client.get('/forge/v1/orgs/%s/models' % org, headers=admin_headers).json()
            self.assertEqual(sorted(model['id'] for model in listed['models']), ['deep', 'fast'])
            actions = [entry['action'] for entry in client.get(BASE + '/audit', headers=owner).json()['entries']]
            self.assertEqual(actions[:2], ['company.catalog_published', 'company.models_discovered'])
            everything = ' '.join(seen) + repr(db.admin.execute('SELECT * FROM forge.platform_audit_log').fetchall())
            self.assertFalse([value for value in (KEY, SECOND) if value in everything])

    def test_a_key_the_gateway_refuses_is_reported_unreachable_and_the_others_still_count(self):
        with patch('forge.gateway_catalog_adapter.HttpxModelsAdapter', mocked_adapter), stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            self.keys(client, owner, org, ('primary', KEY), ('wrong', 'unknown-key-VALUE'))
            body = client.post(BASE + '/companies/%s/catalog/discover' % org, headers=owner, json={}).json()
            self.assertEqual([(item['label'], item['state']) for item in body['keys']], [('primary', 'ok'), ('wrong', 'unreachable')])
            self.assertEqual(body['model_ids'], ['gpt-a', 'gpt-b', 'shared'])
            self.assertNotIn('denied', json.dumps(body), 'the upstream message is never echoed')

    def test_discovery_with_no_assignment_and_publishing_before_discovery_or_outside_it_are_refused(self):
        with patch('forge.gateway_catalog_adapter.HttpxModelsAdapter', mocked_adapter), stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            path = BASE + '/companies/%s/catalog' % org
            self.assertEqual(client.post(path + '/discover', headers=owner, json={}).json(), {'keys': [], 'model_ids': [], 'discovered_at': None})
            self.keys(client, owner, org, ('primary', KEY))
            body = {'expected_catalogue_revision': 0, 'expected_gateway_revision': 1, 'aliases': {'fast': 'gpt-a'}, 'default_alias': 'fast'}
            self.assertEqual(client.put(path, headers=owner, json=body).status_code, 422, 'nothing was discovered yet')
            client.post(path + '/discover', headers=owner, json={})
            self.assertEqual(client.put(path, headers=owner, json={**body, 'aliases': {'fast': 'nope'}}).status_code, 422)
            self.assertEqual(client.put(path, headers=owner, json={**body, 'expected_catalogue_revision': 4}).status_code, 409)
            self.assertEqual(client.put(path, headers=owner, json={**body, 'expected_gateway_revision': 9}).status_code, 409)
            self.assertEqual(client.put(path, headers=owner, json=body).status_code, 200)
            self.assertEqual(client.put(path, headers=owner, json=body).status_code, 409, 'the revision moved on')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(), (1,))

    def test_company_administrators_and_members_are_denied_on_every_catalog_route(self):
        with patch('forge.gateway_catalog_adapter.HttpxModelsAdapter', mocked_adapter), stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            org = results[0].organization_id
            self.keys(client, owner, org, ('primary', KEY))
            path = BASE + '/companies/%s/catalog' % org
            body = {'expected_catalogue_revision': 0, 'expected_gateway_revision': 1, 'aliases': {'fast': 'gpt-a'}, 'default_alias': 'fast'}
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                headers = login(client, account)
                for method, route, payload in (('GET', path, None), ('POST', path + '/discover', {}), ('PUT', path, body)):
                    with self.subTest(account=account.email, route=route):
                        response = client.request(method, route, headers=headers, json=payload)
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_model_discoveries').fetchone(), (0,))

    def test_a_password_only_owner_session_cannot_discover_or_publish(self):
        with patch('forge.gateway_catalog_adapter.HttpxModelsAdapter', mocked_adapter), stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            headers = login(client, Person(OWNER_EMAIL, PASSWORD))
            path = BASE + '/companies/%s/catalog' % results[0].organization_id
            for method, route, payload in (('GET', path, None), ('POST', path + '/discover', {}),
                                           ('PUT', path, {'expected_catalogue_revision': 0, 'expected_gateway_revision': 1,
                                                          'aliases': {'a': 'm'}, 'default_alias': 'a'})):
                response = client.request(method, route, headers=headers, json=payload)
                self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'MFA_REQUIRED'))


if __name__ == '__main__':
    unittest.main()
