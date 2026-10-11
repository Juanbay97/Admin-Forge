"""Admin static mount (CSP, SPA fallback, caching, degradation) and the loopback request guard."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from forge.admin_mount import ADMIN_CSP, AdminBuildMissing, apply_guard, mount_admin

HOST, ADMIN, CLIENT = '127.0.0.1:3410', 'http://127.0.0.1:3410', 'http://127.0.0.1:3411'
INDEX = '<!doctype html><title>Forge admin</title><script type="module" src="/admin/assets/app.abc123.js"></script>'


def build(directory):
    root = Path(directory)/'admin'
    (root/'assets').mkdir(parents=True)
    (root/'index.html').write_text(INDEX, 'utf-8')
    (root/'assets'/'app.abc123.js').write_text('console.log(1)', 'utf-8')
    (root/'favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', 'utf-8')
    (Path(directory)/'secret.txt').write_text('outside the build', 'utf-8')
    return root


class AdminMountTests(unittest.TestCase):
    def client(self, directory, **kwargs):
        app = FastAPI()
        mount_admin(app, build(directory), **kwargs)
        return TestClient(app, base_url=ADMIN, follow_redirects=False)

    def test_index_is_served_with_a_strict_csp_and_no_caching(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory, required=True) as client:
            response = client.get('/admin/')
            self.assertEqual((response.status_code, response.text), (200, INDEX))
            self.assertTrue(response.headers['content-type'].startswith('text/html'))
            self.assertEqual(response.headers['content-security-policy'], ADMIN_CSP)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            for forbidden in ('unsafe-inline', 'unsafe-eval', 'http:', 'https:', '*', 'data:'):
                self.assertNotIn(forbidden, ADMIN_CSP)
            self.assertIn("script-src 'self'", ADMIN_CSP)
            self.assertIn("frame-ancestors 'none'", ADMIN_CSP)
            redirect = client.get('/admin')
            self.assertEqual((redirect.status_code, redirect.headers['location']), (307, '/admin/'))

    def test_client_routes_fall_back_to_the_index_but_missing_files_are_404(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory, required=True) as client:
            for path in ('/admin/members', '/admin/members/42/edit', '/admin/login'):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual((response.status_code, response.text), (200, INDEX))
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertEqual(response.headers['content-security-policy'], ADMIN_CSP)
            for path in ('/admin/assets/missing.js', '/admin/nothing.png', '/admin/assets/gone.css'):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 404)

    def test_hashed_assets_are_immutable_and_other_files_are_revalidated(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory, required=True) as client:
            asset = client.get('/admin/assets/app.abc123.js')
            self.assertEqual((asset.status_code, asset.text), (200, 'console.log(1)'))
            self.assertIn('javascript', asset.headers['content-type'])
            self.assertEqual(asset.headers['cache-control'], 'public, max-age=31536000, immutable')
            icon = client.get('/admin/favicon.svg')
            self.assertEqual((icon.status_code, icon.headers['content-type']), (200, 'image/svg+xml'))
            self.assertEqual(icon.headers['cache-control'], 'no-cache')
            self.assertEqual(asset.headers['content-security-policy'], ADMIN_CSP)

    def test_path_traversal_and_siblings_of_the_build_are_never_served(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory, required=True) as client:
            for path in ('/admin/..%2fsecret.txt', '/admin/%2e%2e/secret.txt', '/admin/assets/..%2f..%2fsecret.txt',
                         '/admin/..\\secret.txt', '/admin/%00', '/admin//etc/passwd'):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertNotIn('outside the build', response.text)
                    self.assertIn(response.status_code, (200, 400, 404))
                    if response.status_code == 200:
                        self.assertEqual(response.text, INDEX)

    def test_a_missing_build_stops_startup_when_required_and_never_leaks_the_path(self):
        with tempfile.TemporaryDirectory() as directory:
            for target in (Path(directory)/'absent', Path(directory)):
                with self.subTest(target=target.name), self.assertRaises(AdminBuildMissing) as caught:
                    mount_admin(FastAPI(), target, required=True)
                self.assertEqual(str(caught.exception), 'ADMIN_BUILD_MISSING')

    def test_a_missing_build_degrades_to_a_clear_message_when_not_required(self):
        with tempfile.TemporaryDirectory() as directory:
            app = FastAPI()
            mount_admin(app, Path(directory)/'absent', required=False)
            with TestClient(app, base_url=ADMIN, follow_redirects=False) as client:
                for path in ('/admin/', '/admin/members'):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn('Admin web build is missing', response.text)
                    self.assertIn('npm run build', response.text)
                    self.assertNotIn(directory, response.text)
                    self.assertEqual(response.headers['content-security-policy'], ADMIN_CSP)
                    self.assertEqual(response.headers['cache-control'], 'no-store')


def guarded_client(**kwargs):
    app = FastAPI()

    @app.api_route('/forge/v1/probe', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    def probe():
        return {'ok': True}

    @app.get('/admin/')
    def page():
        return {'page': True}
    apply_guard(app, host=HOST, origins=(ADMIN, CLIENT), cors_origins=(CLIENT,))
    return TestClient(app, base_url=ADMIN)


class GuardTests(unittest.TestCase):
    def test_mutations_with_a_foreign_origin_are_rejected_before_the_route(self):
        with guarded_client() as client:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                for origin in ('http://evil.test', 'http://127.0.0.1:3412', 'null', 'http://127.0.0.1:3410.evil.test'):
                    with self.subTest(method=method, origin=origin):
                        response = client.request(method, '/forge/v1/probe', headers={'Origin': origin})
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'FORBIDDEN_ORIGIN'))

    def test_configured_origins_and_origin_less_server_calls_reach_the_route(self):
        with guarded_client() as client:
            for headers in ({'Origin': ADMIN}, {'Origin': CLIENT}, {}):
                for method in ('POST', 'PUT', 'DELETE'):
                    with self.subTest(method=method, headers=headers):
                        response = client.request(method, '/forge/v1/probe', headers=headers)
                        self.assertEqual((response.status_code, response.json()), (200, {'ok': True}))
            self.assertEqual(client.get('/forge/v1/probe', headers={'Origin': 'http://evil.test'}).status_code, 200)

    def test_any_request_with_a_foreign_host_is_rejected_whatever_its_origin(self):
        with guarded_client() as client:
            for host in ('evil.test:3410', 'localhost:3410', '127.0.0.1:3411', '127.0.0.1', '127.0.0.1:3410.evil.test'):
                for path in ('/forge/v1/probe', '/admin/'):
                    with self.subTest(host=host, path=path):
                        response = client.get(path, headers={'Host': host})
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'FORBIDDEN_HOST'))
            self.assertEqual(client.get('/admin/').json(), {'page': True})

    def test_cors_is_granted_only_to_the_configured_client_origin(self):
        with guarded_client() as client:
            allowed = client.options('/forge/v1/probe', headers={
                'Origin': CLIENT, 'Access-Control-Request-Method': 'PUT', 'Access-Control-Request-Headers': 'Authorization'})
            self.assertEqual((allowed.status_code, allowed.headers['access-control-allow-origin']), (200, CLIENT))
            self.assertNotIn('access-control-allow-credentials', allowed.headers)
            for origin in ('http://evil.test', ADMIN, 'http://127.0.0.1:3412'):
                with self.subTest(origin=origin):
                    denied = client.options('/forge/v1/probe', headers={'Origin': origin, 'Access-Control-Request-Method': 'PUT'})
                    self.assertNotIn('access-control-allow-origin', denied.headers)
                    actual = client.get('/forge/v1/probe', headers={'Origin': origin})
                    self.assertNotIn('access-control-allow-origin', actual.headers)
            self.assertEqual(client.get('/forge/v1/probe', headers={'Origin': CLIENT}).headers['access-control-allow-origin'], CLIENT)


if __name__ == '__main__':
    unittest.main()
