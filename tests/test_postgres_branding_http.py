"""Owned PostgreSQL: branding through the real composed control plane (dedicated public role, guard, two orgs)."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge import contract
from forge.branding import DEFAULT
from test_branding_api import BRANDING, chunk, png
from test_postgres_mvp_local import ADMIN, CLIENT, login, stack

ACME = {**BRANDING, 'name': 'Acme Labs'}
GLOBEX = {'name': 'Globex', 'loginCopy': 'Globex portal.', 'assets': {},
          'theme': {'primary': '#123456', 'accent': '#ABCDEF', 'tint': '#FEDCBA', 'heading': 'roboto', 'body': 'nunito-sans'}}


def save(client, headers, org, expected, document):
    return client.put('/forge/v1/orgs/%s/branding' % org.organization_id, headers=headers,
                      json={'expectedRevision': expected, 'branding': document})


class PostgresBrandingHttpTests(unittest.TestCase):
    def test_two_organizations_serve_different_branding_publicly_and_to_their_members(self):
        with stack() as (db, client, results, root, secrets):
            org_a, org_b = results
            admin_a, admin_b = login(client, org_a.accounts[0]), login(client, org_b.accounts[0])
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}).json()['name'], DEFAULT.name)
            self.assertEqual(save(client, admin_a, org_a, 0, ACME).json()['revision'], 1)
            self.assertEqual(save(client, admin_b, org_b, 0, GLOBEX).json()['revision'], 1)
            a = client.get('/forge/v1/branding', params={'org': 'org-a'})
            b = client.get('/forge/v1/branding', params={'org': 'org-b'})
            self.assertEqual((a.json()['name'], b.json()['name']), ('Acme Labs', 'Globex'))
            self.assertEqual((b.json()['theme']['primary'], b.json()['theme']['heading']), ('#123456', 'roboto'))
            self.assertEqual((a.headers['etag'], a.headers['cache-control']), ('"1"', 'no-cache'))
            self.assertEqual(client.get('/forge/v1/branding', params={'org': 'org-a'}, headers={'If-None-Match': '"1"'}).status_code, 304)
            member = login(client, org_a.accounts[1])
            projected = client.get('/forge/v1/orgs/%s/branding' % org_a.organization_id, headers=member)
            self.assertEqual((projected.status_code, projected.json()['name']), (200, 'Acme Labs'))
            for leaked in (str(org_a.organization_id), str(org_b.organization_id), 'forge.local.test', 'gateway'):
                self.assertNotIn(leaked, a.text + b.text)

    def test_the_contract_pin_served_by_the_composed_app_is_unchanged_by_branding(self):
        with stack() as (db, client, results, root, secrets):
            served = client.get('/forge/v1/contract').json()
            self.assertEqual(served['schema_sha256'], contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            self.assertFalse([path for path in client.get('/openapi.json').json()['paths'] if 'branding' in path])

    def test_admin_only_cross_org_and_guard_rules_hold_end_to_end(self):
        with stack() as (db, client, results, root, secrets):
            org_a, org_b = results
            admin_a, member_a = login(client, org_a.accounts[0]), login(client, org_a.accounts[1])
            self.assertEqual(save(client, member_a, org_a, 0, ACME).status_code, 404)
            self.assertEqual(save(client, admin_a, org_b, 0, ACME).status_code, 404)
            self.assertEqual(client.get('/forge/v1/orgs/%s/branding' % org_b.organization_id, headers=admin_a).status_code, 404)
            foreign = client.put('/forge/v1/orgs/%s/branding' % org_a.organization_id, headers={**admin_a, 'Origin': 'http://evil.test'},
                                 json={'expectedRevision': 0, 'branding': ACME})
            self.assertEqual((foreign.status_code, foreign.json()['error']['code']), (403, 'FORBIDDEN_ORIGIN'))
            self.assertEqual(client.get('/forge/v1/branding?org=org-a', headers={'Host': 'evil.test:3410'}).status_code, 403)
            self.assertEqual(save(client, admin_a, org_a, 0, ACME).status_code, 200)
            stale = save(client, admin_a, org_a, 0, {**ACME, 'name': 'Lost'})
            self.assertEqual((stale.status_code, stale.json()['error']['code']), (409, 'REVISION_CONFLICT'))
            reset = client.post('/forge/v1/orgs/%s/branding/reset' % org_a.organization_id, headers=admin_a, json={'expectedRevision': 1})
            self.assertEqual((reset.status_code, reset.json()['revision'], reset.json()['name']), (200, 2, DEFAULT.name))
            history = db.admin.execute('SELECT revision,action FROM forge.organization_branding_revisions ORDER BY revision').fetchall()
            self.assertEqual(history, [(1, 'save'), (2, 'reset')])

    def test_logos_are_uploaded_stripped_published_and_served_by_content_hash(self):
        with stack() as (db, client, results, root, secrets):
            org_a = results[0]
            admin_a = login(client, org_a.accounts[0])
            original = png(extra=(chunk(b'tEXt', b'Author\x00someone'), chunk(b'eXIf', b'GPS')))
            uploaded = client.post('/forge/v1/orgs/%s/branding/assets?kind=logoLight' % org_a.organization_id,
                                   headers={**admin_a, 'Content-Type': 'image/png'}, content=original)
            self.assertEqual(uploaded.status_code, 201)
            sha = uploaded.json()['sha256']
            self.assertEqual(client.get('/forge/v1/branding/assets/' + sha).status_code, 404, 'uploaded but not published')
            saved = save(client, admin_a, org_a, 0, {**ACME, 'assets': {'logoLight': sha}})
            self.assertEqual(saved.json()['assets'], {'logoLight': '/forge/v1/branding/assets/' + sha})
            served = client.get('/forge/v1/branding/assets/' + sha)
            self.assertEqual((served.status_code, served.headers['content-type']), (200, 'image/png'))
            self.assertEqual(served.headers['cache-control'], 'public, max-age=31536000, immutable')
            for secret in (b'tEXt', b'eXIf', b'someone', b'GPS'):
                self.assertNotIn(secret, served.content)
            self.assertEqual(client.get('/forge/v1/branding/assets/' + 'f' * 64).status_code, 404)
            self.assertEqual(client.post('/forge/v1/orgs/%s/branding/assets?kind=isotipo' % org_a.organization_id,
                                         headers={**admin_a, 'Content-Type': 'image/png'}, content=b'<svg/>').status_code, 415)

    def test_the_public_endpoints_run_on_the_dedicated_role_and_fail_closed_without_it(self):
        with stack() as (db, client, results, root, secrets):
            org_a = results[0]
            admin_a = login(client, org_a.accounts[0])
            self.assertEqual(client.get('/forge/v1/branding?org=org-a').status_code, 200)
            db.admin.execute('REVOKE EXECUTE ON FUNCTION forge.branding_public_read(text) FROM forge_branding_service')
            response = client.get('/forge/v1/branding?org=org-a')
            self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'))
            self.assertEqual(client.get('/forge/v1/orgs/%s/branding' % org_a.organization_id, headers=admin_a).status_code, 503,
                             'the grant drift also breaks the F25 attestation, so authenticated routes fail closed too')

    def test_an_inactive_organization_is_indistinguishable_from_an_unknown_one(self):
        with stack() as (db, client, results, root, secrets):
            db.admin.execute("UPDATE forge.organizations SET active=false WHERE slug='org-b'")
            closed = client.get('/forge/v1/branding?org=org-b')
            unknown = client.get('/forge/v1/branding?org=nope')
            self.assertEqual((closed.status_code, closed.content), (404, unknown.content))
            self.assertEqual(unknown.status_code, 404)


if __name__ == '__main__':
    unittest.main()
