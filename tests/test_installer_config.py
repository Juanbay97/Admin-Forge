"""The per-company installer configuration a member downloads from the portal: company code, control plane origin and the policy key set."""
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from fastapi.testclient import TestClient
from forge import contract
from forge.account_api import create_account_app
from forge.capability_api import mount_effective
from forge.capability_effective import EffectivePolicy
from forge.capability_installer import INSTALLER_SCHEMA, InstallerConfig
from forge.capability_model import CapabilityNotFound, CapabilityUnavailable
from forge.capability_signing import PolicySigner
from test_capability_effective import HEADERS, NOW, ORG, SIGNER, TOKEN, Ready, Sessions, store

ORIGIN = 'https://forge.example.test'
PATH = '/forge/v1/capabilities/installer-config'
ROTATED = PolicySigner(bytes([3]) * 32, retired=(PolicySigner(bytes([1]) * 32).public_raw(),))


def client(code='acme', signer=SIGNER, organizations=None):
    policy = EffectivePolicy(store(), signer, clock=lambda: NOW)
    app = create_account_app(sessions=None)
    mount_effective(app, policy=policy, sessions=Sessions(), readiness=Ready(), organizations=organizations or (lambda token: [ORG]),
                    installer=InstallerConfig(policy, ORIGIN, lambda token, org: code))
    return TestClient(app, raise_server_exceptions=False), app


class ServiceTests(unittest.TestCase):
    def test_the_document_has_exactly_the_documented_shape(self):
        policy = EffectivePolicy(store(), ROTATED)
        document = InstallerConfig(policy, ORIGIN, lambda token, org: 'acme-co').document(TOKEN, ORG)
        self.assertEqual(document, {'schema': INSTALLER_SCHEMA, 'company_code': 'acme-co', 'control_plane_origin': ORIGIN,
                                    'policy_keys': ROTATED.keyset()})
        self.assertEqual(INSTALLER_SCHEMA, 'forge.installer-config.v1')
        self.assertEqual([key['status'] for key in document['policy_keys']['keys']], ['active', 'retired'])

    def test_a_missing_or_malformed_company_code_is_not_found_and_no_signing_key_is_unavailable(self):
        policy = EffectivePolicy(store(), SIGNER)
        for code in (None, '', 'Acme', '-acme', 'a' * 64, 5):
            with self.subTest(code=code), self.assertRaises(CapabilityNotFound):
                InstallerConfig(policy, ORIGIN, lambda token, org, code=code: code).document(TOKEN, ORG)
        with self.assertRaises(CapabilityUnavailable):
            InstallerConfig(EffectivePolicy(store(), None), ORIGIN, lambda token, org: 'acme').document(TOKEN, ORG)

    def test_the_origin_is_a_canonical_https_or_loopback_origin(self):
        policy = EffectivePolicy(store(), SIGNER)
        for origin in ('https://forge.example.test', 'http://127.0.0.1:3410'):
            InstallerConfig(policy, origin, lambda token, org: 'acme')
        for origin in (None, '', 'ftp://x', 'https://forge.example.test/', 'https://forge.example.test/path', 'https://u:p@forge.example.test', 'forge.example.test'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                InstallerConfig(policy, origin, lambda token, org: 'acme')


class RouteTests(unittest.TestCase):
    def test_a_member_downloads_the_configuration_as_a_no_store_attachment(self):
        http, app = client()
        response = http.get(PATH, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()), (200, {'schema': INSTALLER_SCHEMA, 'company_code': 'acme',
                                                                         'control_plane_origin': ORIGIN, 'policy_keys': SIGNER.keyset()}))
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['content-disposition'], 'attachment; filename="forge-install.json"')
        self.assertEqual(contract.canonical_sha256(contract.build(app)),
                         contract.canonical_sha256(json.loads(contract.COMMITTED_PATH.read_text('utf-8'))), 'hidden: outside the contract pin')

    def test_a_stranger_is_401_and_a_foreign_company_is_the_same_404(self):
        http, _ = client()
        self.assertEqual(http.get(PATH).status_code, 401)
        self.assertEqual(http.get(PATH, headers={'Authorization': 'Bearer ' + 'z' * 43}).status_code, 401)
        foreign = http.get(PATH + '?org=' + str(uuid4()), headers=HEADERS)
        self.assertEqual((foreign.status_code, foreign.json()['error']['code']), (404, 'NOT_FOUND'))
        several, _ = client(organizations=lambda token: [ORG, uuid4()])
        self.assertEqual(several.get(PATH, headers=HEADERS).status_code, 422)
        self.assertEqual(several.get(PATH + '?org=' + str(ORG), headers=HEADERS).status_code, 200)
        self.assertEqual(client(organizations=lambda token: [])[0].get(PATH, headers=HEADERS).status_code, 404)

    def test_unknown_parameters_no_code_and_no_signing_key_are_refused(self):
        http, _ = client()
        self.assertEqual(http.get(PATH + '?x=1', headers=HEADERS).status_code, 422)
        self.assertEqual(client(code=None)[0].get(PATH, headers=HEADERS).status_code, 404)
        response = client(signer=None)[0].get(PATH, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()['error']['code']), (503, 'SERVICE_UNAVAILABLE'))

    def test_the_route_is_absent_when_no_installer_configuration_is_composed(self):
        policy = EffectivePolicy(store(), SIGNER)
        app = create_account_app(sessions=None)
        mount_effective(app, policy=policy, sessions=Sessions(), readiness=Ready(), organizations=lambda token: [ORG])
        self.assertEqual(TestClient(app, raise_server_exceptions=False).get(PATH, headers=HEADERS).status_code, 404)


if __name__ == '__main__':
    unittest.main()
