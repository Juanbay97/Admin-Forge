"""Installer hosting (read-only, traversal-safe, manifest never cached) and the invitation/reset link redirects."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from forge.admin_mount import mount_admin
from forge.downloads_mount import mount_downloads

HOST = 'http://127.0.0.1:3410'
MANIFEST = '{"version":"1.0.0","released_at":"2026-10-12T00:00:00Z","platforms":{}}'


def stage(directory):
    root = Path(directory)/'downloads'
    root.mkdir()
    (root/'latest.json').write_text(MANIFEST, 'utf-8')
    (root/'Forge-Setup-1.0.0.exe').write_bytes(b'MZ-installer')
    (root/'.hidden').write_text('dotfile', 'utf-8')
    (Path(directory)/'secret.txt').write_text('outside', 'utf-8')
    return root


class DownloadsMountTests(unittest.TestCase):
    def client(self, directory):
        app = FastAPI()
        mount_downloads(app, stage(directory))
        return TestClient(app, base_url=HOST, follow_redirects=False)

    def test_manifest_is_never_cached_and_versioned_files_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            manifest = client.get('/downloads/latest.json')
            self.assertEqual((manifest.status_code, manifest.text), (200, MANIFEST))
            self.assertEqual(manifest.headers['cache-control'], 'no-cache')
            self.assertTrue(manifest.headers['content-type'].startswith('application/json'))
            installer = client.get('/downloads/Forge-Setup-1.0.0.exe')
            self.assertEqual((installer.status_code, installer.content), (200, b'MZ-installer'))
            self.assertEqual(installer.headers['cache-control'], 'public, max-age=31536000, immutable')
            self.assertEqual(installer.headers['content-type'], 'application/octet-stream')
            for response in (manifest, installer):
                self.assertEqual(response.headers['x-content-type-options'], 'nosniff')

    def test_traversal_dotfiles_directories_and_writes_are_refused(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            for path in ('/downloads/../secret.txt', '/downloads/%2e%2e/secret.txt', '/downloads/..%2fsecret.txt',
                         '/downloads/%2e%2e%2fsecret.txt', '/downloads/..%5csecret.txt', '/downloads/.hidden',
                         '/downloads/', '/downloads/missing.exe', '/downloads/%00', '/downloads/a//b'):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 404)
            for method in ('post', 'put', 'delete'):
                self.assertEqual(getattr(client, method)('/downloads/latest.json').status_code, 405)

    def test_a_link_pointing_outside_the_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            link = Path(directory)/'downloads'/'escape.txt'
            try:
                os.symlink(Path(directory)/'secret.txt', link)
            except (OSError, NotImplementedError):
                self.skipTest('symbolic links are not available')
            self.assertEqual(client.get('/downloads/escape.txt').status_code, 404)


class LinkRedirectTests(unittest.TestCase):
    def client(self, directory):
        root = Path(directory)/'admin'
        root.mkdir()
        (root/'index.html').write_text('<title>x</title>', 'utf-8')
        app = FastAPI()
        mount_admin(app, root, required=True)
        return TestClient(app, base_url=HOST, follow_redirects=False)

    def test_invitation_links_land_on_the_spa_with_the_query_kept(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            for path in ('/join', '/onboarding'):
                with self.subTest(path=path):
                    response = client.get(path + '?c=acme')
                    self.assertEqual((response.status_code, response.headers['location']), (307, '/admin/join?c=acme'))
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertEqual(client.get(path).headers['location'], '/admin/join')

    def test_the_owner_set_password_link_lands_on_the_spa(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            response = client.get('/reset-password')
            self.assertEqual((response.status_code, response.headers['location']), (307, '/admin/reset-password'))

    def test_a_query_cannot_inject_another_location(self):
        with tempfile.TemporaryDirectory() as directory, self.client(directory) as client:
            location = client.get('/join?c=a%0d%0aLocation:%20http://evil.test').headers['location']
            self.assertTrue(location.startswith('/admin/join?c='))
            self.assertNotIn('\n', location)
            self.assertNotIn('\r', location)


class StagedDownloadsTests(unittest.TestCase):
    def test_the_local_stack_stages_a_manifest_that_matches_its_installer(self):
        import hashlib
        import json
        from forge.mvp_up import INSTALLER, stage_downloads
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'downloads'
            stage_downloads(root)
            windows = json.loads((root/'latest.json').read_text('utf-8'))['platforms']['windows']
            payload = (root/INSTALLER).read_bytes()
            self.assertEqual(windows, {'url': '/downloads/' + INSTALLER, 'sha256': hashlib.sha256(payload).hexdigest(), 'size_bytes': len(payload)})


if __name__ == '__main__':
    unittest.main()