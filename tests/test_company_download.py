"""The company-stamped installer download: the published installer bytes, named for the member's company, behind a member session."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.capability_api import mount_effective
from forge.capability_effective import EffectivePolicy
from forge.capability_installer import InstallerConfig
from forge.company_download import PublishedInstaller
from test_capability_effective import HEADERS, NOW, ORG, SIGNER, Ready, Sessions, store

PATH = '/forge/v1/downloads/company'
ORIGIN = 'https://forge.example.test'
PAYLOAD = b'MZ forge installer \x00\xff' * 4096
NAME = 'Prometheon-Forge-Setup.exe'


def publish(directory, *, payload=PAYLOAD, url='/downloads/' + NAME, sha256=None, size=None, manifest=None, name=NAME):
    root = Path(directory)
    root.mkdir(exist_ok=True)
    if name is not None:
        (root/name).write_bytes(payload)
    document = manifest if manifest is not None else {'version': '1.0.0', 'released_at': '2026-10-01T00:00:00Z', 'platforms': {'windows': {
        'url': url, 'sha256': hashlib.sha256(payload).hexdigest() if sha256 is None else sha256, 'size_bytes': len(payload) if size is None else size}}}
    (root/'latest.json').write_text(json.dumps(document), encoding='utf-8')
    return root


def client(directory, code='org-a', organizations=None, downloads=True):
    policy = EffectivePolicy(store(), SIGNER, clock=lambda: NOW)
    app = create_account_app(sessions=None)
    mount_effective(app, policy=policy, sessions=Sessions(), readiness=Ready(), organizations=organizations or (lambda token: [ORG]),
                    installer=InstallerConfig(policy, ORIGIN, lambda token, org: code), downloads=PublishedInstaller(directory) if downloads else None)
    return TestClient(app, raise_server_exceptions=False), app


class Case(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = publish(Path(self.directory.name)/'downloads')


class PublishedTests(Case):
    def test_the_published_installer_is_the_file_the_manifest_names_with_its_digest_and_size(self):
        published = PublishedInstaller(self.root).published()
        self.assertEqual((published.path.name, published.size, published.sha256), (NAME, len(PAYLOAD), hashlib.sha256(PAYLOAD).hexdigest()))

    def test_a_missing_or_unverifiable_publication_is_unavailable_without_saying_why(self):
        digest = hashlib.sha256(PAYLOAD).hexdigest()
        wrong = {
            'no manifest': lambda root: (root/'latest.json').unlink(),
            'not json': lambda root: (root/'latest.json').write_text('{', encoding='utf-8'),
            'not an object': lambda root: (root/'latest.json').write_text('[1]', encoding='utf-8'),
            'no windows entry': lambda root: publish(root, manifest={'version': '1', 'platforms': {}}),
            'external url': lambda root: publish(root, url='https://evil.test/' + NAME),
            'traversal': lambda root: publish(root, url='/downloads/../latest.json'),
            'nested': lambda root: publish(root, url='/downloads/a/' + NAME),
            'backslash': lambda root: publish(root, url='/downloads/..\\' + NAME),
            'hidden file': lambda root: publish(root, url='/downloads/.hidden.exe', name='.hidden.exe'),
            'not an exe': lambda root: publish(root, url='/downloads/latest.json'),
            'missing file': lambda root: (root/NAME).unlink(),
            'digest mismatch': lambda root: publish(root, sha256='0' * 64),
            'bad digest': lambda root: publish(root, sha256='xyz'),
            'size mismatch': lambda root: publish(root, size=len(PAYLOAD) + 1),
            'file replaced': lambda root: (root/NAME).write_bytes(PAYLOAD + b'x'),
        }
        for name, change in wrong.items():
            with self.subTest(name):
                change(self.root)
                with self.assertRaises(LookupError):
                    PublishedInstaller(self.root).published()
                publish(self.root)  # restore
                self.assertEqual(PublishedInstaller(self.root).published().sha256, digest)


class RouteTests(Case):
    def test_a_member_downloads_the_published_bytes_named_for_their_company(self):
        http, app = client(self.root)
        response = http.get(PATH, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PAYLOAD, 'identical bytes: the digest matches latest.json')
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), json.loads((self.root/'latest.json').read_text('utf-8'))['platforms']['windows']['sha256'])
        self.assertEqual(response.headers['content-disposition'], 'attachment; filename="Prometheon-Forge-Setup-org-a.exe"')
        self.assertEqual(response.headers['content-type'], 'application/octet-stream')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(response.headers['content-length'], str(len(PAYLOAD)))
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))), 'hidden: outside the contract pin')

    def test_each_company_gets_its_own_name_and_the_same_bytes(self):
        first = client(self.root, code='org-a')[0].get(PATH, headers=HEADERS)
        second = client(self.root, code='globex-2')[0].get(PATH, headers=HEADERS)
        self.assertEqual(second.headers['content-disposition'], 'attachment; filename="Prometheon-Forge-Setup-globex-2.exe"')
        self.assertEqual(first.content, second.content)

    def test_a_stranger_is_401_and_a_foreign_company_is_the_same_404(self):
        http, _ = client(self.root)
        self.assertEqual(http.get(PATH).status_code, 401)
        self.assertEqual(http.get(PATH, headers={'Authorization': 'Bearer ' + 'z' * 43}).status_code, 401)
        foreign = http.get(PATH + '?org=' + str(uuid4()), headers=HEADERS)
        self.assertEqual((foreign.status_code, foreign.json()['error']['code']), (404, 'NOT_FOUND'))
        several, _ = client(self.root, organizations=lambda token: [ORG, uuid4()])
        self.assertEqual(several.get(PATH, headers=HEADERS).status_code, 422)
        chosen = several.get(PATH + '?org=' + str(ORG), headers=HEADERS)
        self.assertEqual((chosen.status_code, chosen.content), (200, PAYLOAD))
        self.assertEqual(client(self.root, organizations=lambda token: [])[0].get(PATH, headers=HEADERS).status_code, 404)

    def test_unknown_parameters_and_a_company_without_a_valid_code_are_refused(self):
        http, _ = client(self.root)
        self.assertEqual(http.get(PATH + '?x=1', headers=HEADERS).status_code, 422)
        for code in (None, '', 'Acme', '../x', 'a"b', 'a' * 64):
            with self.subTest(code=code):
                self.assertEqual(client(self.root, code=code)[0].get(PATH, headers=HEADERS).status_code, 404)

    def test_an_unpublished_or_inconsistent_installer_is_a_plain_503_that_names_nothing(self):
        (self.root/'latest.json').unlink()
        response = client(self.root)[0].get(PATH, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'))
        self.assertNotIn(str(self.root), response.text)
        publish(self.root, sha256='0' * 64)
        self.assertEqual(client(self.root)[0].get(PATH, headers=HEADERS).status_code, 503, 'bytes that do not match latest.json are never served')

    def test_there_is_no_public_per_code_download_and_no_route_without_a_downloads_directory(self):
        http, _ = client(self.root)
        for path in (PATH + '/org-a', '/forge/v1/downloads/org-a', '/forge/v1/downloads'):
            with self.subTest(path=path):
                self.assertEqual(http.get(path).status_code, 404)
                self.assertEqual(http.get(path, headers=HEADERS).status_code, 404)
        self.assertEqual(http.get(PATH + '/').status_code, 401, 'a trailing slash redirects to the same guarded route')
        self.assertEqual(http.post(PATH, headers=HEADERS).status_code, 405)
        self.assertEqual(client(self.root, downloads=False)[0].get(PATH, headers=HEADERS).status_code, 404)

    def test_a_range_request_resumes_the_same_bytes(self):
        response = client(self.root)[0].get(PATH, headers={**HEADERS, 'Range': 'bytes=10-19'})
        self.assertEqual((response.status_code, response.content), (206, PAYLOAD[10:20]))


if __name__ == '__main__':
    unittest.main()