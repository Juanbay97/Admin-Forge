"""Owned PostgreSQL: the key service over the platform pool seals before the database, never returns key text and keeps the
pool's metadata, rotation compare-and-swap, label uniqueness and owner-only access."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher, GatewayRecord
from forge.gateway_keys import GatewayKeys
from forge.gateway_keys_store import PostgresGatewayKeyStore
from forge.gateway_origins import DEFAULT_ENDPOINT, OriginPolicy
from forge.platform import KeyConflict, MfaRequired, PlatformDenied, PlatformInvalid, PlatformNotFound, RevisionConflict
from forge.provisioning import SEED, provision
from mvp_support import mvp_database, seed_discovery
from platform_support import add_owner, sign_in

KEY = 'pool-fixture-key-ABCD'
ORIGIN = 'https://gateway.fixture.example'


class PostgresKeyServiceTests(unittest.TestCase):
    def build(self, db, *, mfa=True):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.admin = results[0].accounts[0]
        self.org = results[0].organization_id
        self.cipher = GatewayCipher(Fernet.generate_key(), policy=OriginPolicy(frozenset({DEFAULT_ENDPOINT, ORIGIN})))
        self.service = GatewayKeys(PostgresGatewayKeyStore(db.pool('forge_platform_service')), self.cipher)
        add_owner(db.admin)
        self.token, _ = sign_in(db, mfa=mfa)

    def test_a_created_key_is_stored_sealed_opens_with_its_binding_and_is_never_echoed(self):
        with mvp_database() as db:
            self.build(db)
            info = self.service.create(self.token, 'primary', ORIGIN, KEY)
            self.assertEqual((info.label, info.origin, info.revision, info.status, info.has_key, info.hint, info.companies),
                             ('primary', ORIGIN, 1, 'active', True, 'ABCD', 0))
            sealed = db.admin.execute('SELECT encrypted_key FROM forge.gateway_keys WHERE id=%s', (info.id,)).fetchone()[0]
            self.assertEqual(self.cipher.open_key(self.org, GatewayRecord(1, uuid4(), ORIGIN, sealed, info.id, 1)), KEY)
            for table in ('gateway_keys', 'platform_audit_log'):
                self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.%s t WHERE t::text LIKE %%s' % table, ('%' + KEY + '%',)).fetchone(), (0,))
            self.assertNotIn(KEY, repr(self.service.keys(self.token)))
            with self.assertRaises(KeyConflict):
                self.service.create(self.token, 'primary', ORIGIN, KEY)

    def test_rotation_swaps_on_the_revision_and_the_new_value_opens_only_at_the_new_revision(self):
        with mvp_database() as db:
            self.build(db)
            info = self.service.create(self.token, 'primary', ORIGIN, KEY)
            rotated = self.service.rotate(self.token, info.id, 1, 'second-fixture-key-WXYZ')
            self.assertEqual((rotated.revision, rotated.hint), (2, 'WXYZ'))
            sealed = db.admin.execute('SELECT encrypted_key FROM forge.gateway_keys WHERE id=%s', (info.id,)).fetchone()[0]
            self.assertEqual(self.cipher.open_key(self.org, GatewayRecord(1, uuid4(), ORIGIN, sealed, info.id, 2)), 'second-fixture-key-WXYZ')
            with self.assertRaises(RevisionConflict):
                self.service.rotate(self.token, info.id, 1, KEY)
            self.assertEqual(self.service.set_status(self.token, info.id, False).status, 'disabled')
            with self.assertRaises(PlatformInvalid):
                self.service.create(self.token, 'bad origin', 'https://evil.example', KEY)

    def test_assignment_and_ceiling_round_trip_and_unknown_company_is_not_found(self):
        with mvp_database() as db:
            self.build(db)
            first = self.service.create(self.token, 'one', ORIGIN, KEY)
            second = self.service.create(self.token, 'two', ORIGIN, None)
            saved = self.service.assign(self.token, self.org, [(first.id, 2, True), (second.id, 1, False)])
            self.assertEqual([(item.key_id, item.priority, item.active, item.has_key) for item in saved],
                             [(second.id, 1, False, False), (first.id, 2, True, True)])
            self.assertEqual(self.service.assignments(self.token, self.org), saved)
            self.assertEqual(self.service.ceiling(self.token, self.org), [], 'a new profile allows no model until the platform sets one')
            other = db.admin.execute("SELECT id FROM forge.organizations WHERE id<>%s", (self.org,)).fetchone()[0]
            self.assertIsNone(self.service.ceiling(self.token, other), 'no profile row is read as nothing configured')
            seed_discovery(db.admin, self.org, ['gpt-a', 'gpt-b'])
            self.assertEqual(self.service.set_ceiling(self.token, self.org, ['gpt-a']), ['gpt-a'])
            self.assertEqual(self.service.ceiling(self.token, self.org), ['gpt-a'])
            with self.assertRaises(PlatformNotFound):
                self.service.assign(self.token, uuid4(), [])
            self.assertEqual(self.service.keys(self.token)[0].companies, 1)

    def test_a_password_only_session_and_a_company_administrator_are_refused(self):
        with mvp_database() as db:
            self.build(db, mfa=False)
            with self.assertRaises(MfaRequired):
                self.service.create(self.token, 'primary', ORIGIN, KEY)
            admin, _ = sign_in(db, self.admin.email, self.admin.password)
            for run in (lambda: self.service.create(admin, 'x', ORIGIN, KEY), lambda: self.service.keys(admin),
                        lambda: self.service.set_ceiling(admin, self.org, ['gpt-a'])):
                with self.assertRaises(PlatformDenied):
                    run()
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
