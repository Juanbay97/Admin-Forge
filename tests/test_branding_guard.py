"""The loopback guard that wraps the composed app also protects the branding routes."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from forge.mvp_local import assemble, load_config
from test_branding_api import BRANDING, World, png
from test_mvp_local import Workspace

CLIENT = 'http://127.0.0.1:3411'


class BrandingGuardTests(unittest.TestCase):
    def build(self, workspace):
        config = load_config(workspace.path())
        world = World()
        readiness = MagicMock()
        readiness.check.return_value = True
        assemble(world.app, config, readiness)
        return world, TestClient(world.app, base_url=config.admin_origin, raise_server_exceptions=False), config

    def calls(self, world, org):
        headers = {**world.auth('admin_a'), 'Content-Type': 'application/json'}
        body = json.dumps({'expectedRevision': 0, 'branding': BRANDING})
        return (('PUT', '/forge/v1/orgs/%s/branding' % org, {'content': body, 'headers': headers}),
                ('POST', '/forge/v1/orgs/%s/branding/reset' % org, {'content': '{"expectedRevision":0}', 'headers': headers}),
                ('POST', '/forge/v1/orgs/%s/branding/assets?kind=isotipo' % org,
                 {'content': png(), 'headers': {**world.auth('admin_a'), 'Content-Type': 'image/png'}}))

    def test_a_foreign_browser_origin_cannot_mutate_branding(self):
        with Workspace() as workspace:
            world, client, config = self.build(workspace)
            for method, url, options in self.calls(world, world.org_a):
                with self.subTest(url=url):
                    options = {**options, 'headers': {**options['headers'], 'Origin': 'http://evil.test'}}
                    response = client.request(method, url, **options)
                    self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'FORBIDDEN_ORIGIN'))
            self.assertIsNone(world.store.orgs[world.org_a]['current'])
            self.assertEqual(world.store.orgs[world.org_a]['assets'], {})

    def test_a_foreign_host_is_refused_for_every_branding_route_including_the_public_ones(self):
        with Workspace() as workspace:
            world, client, config = self.build(workspace)
            for method, url, options in self.calls(world, world.org_a):
                options = {**options, 'headers': {**options['headers'], 'Host': 'evil.test:3410'}}
                self.assertEqual(client.request(method, url, **options).status_code, 403)
            for url in ('/forge/v1/branding?org=acme', '/forge/v1/branding/assets/' + 'a' * 64):
                self.assertEqual(client.get(url, headers={'Host': 'rebind.test:3410'}).status_code, 403)
            self.assertEqual(client.get('/forge/v1/branding?org=acme').status_code, 200)

    def test_the_allow_listed_origin_and_server_side_callers_without_an_origin_are_accepted(self):
        with Workspace() as workspace:
            world, client, config = self.build(workspace)
            method, url, options = self.calls(world, world.org_a)[0]
            self.assertEqual(client.request(method, url, **{**options, 'headers': {**options['headers'], 'Origin': config.admin_origin}}).status_code, 200)
            method, url, options = self.calls(world, world.org_a)[1]
            self.assertEqual(client.request(method, url, **{**options, 'headers': {**options['headers'], 'Origin': CLIENT}}).status_code, 409)
            self.assertEqual(client.request(*self.calls(world, world.org_a)[2][:2], **self.calls(world, world.org_a)[2][2]).status_code, 201)

    def test_public_reads_set_cors_only_for_the_allow_listed_client_origin(self):
        with Workspace() as workspace:
            world, client, config = self.build(workspace)
            allowed = client.get('/forge/v1/branding?org=acme', headers={'Origin': CLIENT})
            self.assertEqual(allowed.headers['access-control-allow-origin'], CLIENT)
            foreign = client.get('/forge/v1/branding?org=acme', headers={'Origin': 'http://evil.test'})
            self.assertNotIn('access-control-allow-origin', foreign.headers)
            self.assertNotIn('access-control-allow-credentials', allowed.headers)


if __name__ == '__main__':
    unittest.main()
