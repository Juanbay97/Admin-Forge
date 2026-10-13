"""Owned PostgreSQL: bootstrap-owner creates the owner (no membership, unusable password), one single-use set-password
link, is a no-op on rerun and rolls everything back when the link cannot be stored."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.account_sessions import PostgresSessionStore, SessionDenied, SessionService
from forge.invitations import capability_digest
from forge.platform import PlatformService
from forge.platform_cli import BootstrapRefused, bootstrap_owner, write_private_file
from forge.platform_store import PostgresPlatformStore
from mvp_support import mvp_database
from platform_support import add_account

ORIGIN = 'https://forge.example.test'
EMAIL = 'owner@example.test'
NEW_PASSWORD = 'a-brand-new-owner-passphrase'


def counts(db):
    return {table: db.admin.execute('SELECT count(*) FROM forge.' + table).fetchone()[0]
            for table in ('identities', 'owned_accounts', 'platform_roles', 'account_password_resets', 'memberships')}


def capability_of(link):
    return parse_qs(urlsplit(link).fragment)['capability'][0]


class BootstrapOwnerTests(unittest.TestCase):
    def bootstrap(self, db, directory, email=EMAIL, ttl=3600, name='Platform Owner'):
        path = Path(directory)/'owner-link.txt'
        outcome = bootstrap_owner(db.admin, email=email, name=name, origin=ORIGIN, ttl_seconds=ttl,
                                  write_link=lambda link: write_private_file(path, link + '\n'))
        return outcome, path

    def test_it_creates_an_owner_without_any_membership_and_stores_only_the_digest_of_the_link(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            outcome, path = self.bootstrap(db, directory)
            self.assertTrue(outcome.created)
            self.assertEqual(path.read_text('utf-8'), outcome.link + '\n')
            self.assertEqual(counts(db), {'identities': 1, 'owned_accounts': 1, 'platform_roles': 1,
                                          'account_password_resets': 1, 'memberships': 0})
            self.assertEqual(db.admin.execute('SELECT a.canonical_email,a.display_name,a.active,r.role FROM forge.owned_accounts a '
                                              'JOIN forge.platform_roles r ON r.account_id=a.id').fetchall(),
                             [(EMAIL, 'Platform Owner', True, 'platform_owner')])
            capability = capability_of(outcome.link)
            self.assertEqual(db.admin.execute('SELECT capability_hash,credential_revision,consumed FROM forge.account_password_resets').fetchall(),
                             [(capability_digest(capability), 1, False)])
            everything = ' '.join(db.admin.execute('SELECT a::text FROM forge.owned_accounts a').fetchone()
                                  + db.admin.execute('SELECT r::text FROM forge.account_password_resets r').fetchone())
            self.assertNotIn(capability, everything, 'the raw capability is never stored')
            self.assertEqual(urlsplit(outcome.link)._replace(fragment='').geturl(), ORIGIN + '/reset-password')

    def test_the_link_sets_the_password_exactly_once_then_the_owner_is_a_platform_identity(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            outcome, _ = self.bootstrap(db, directory)
            capability = capability_of(outcome.link)
            sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
            self.assertIs(sessions.reset(capability, NEW_PASSWORD), True)
            self.assertIs(sessions.reset(capability, 'another-owner-passphrase-2'), False, 'the second use is rejected')
            with self.assertRaises(SessionDenied):
                sessions.login(EMAIL, 'another-owner-passphrase-2')
            token = sessions.login(EMAIL, NEW_PASSWORD).capability
            identity = PlatformService(PostgresPlatformStore(db.pool('forge_platform_service'))).me(token)
            self.assertEqual((identity.role,), ('platform_owner',))

    def test_nobody_can_sign_in_before_the_link_is_used(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            self.bootstrap(db, directory)
            sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
            for guess in ('', 'x' * 15, 'password-password', 'forge-owner-passphrase'):
                with self.subTest(guess=guess), self.assertRaises(SessionDenied):
                    sessions.login(EMAIL, guess)

    def test_an_expired_link_is_rejected(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            outcome, _ = self.bootstrap(db, directory, ttl=60)
            db.admin.execute("UPDATE forge.account_password_resets SET expires_at=clock_timestamp()-interval '1 second'")
            sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
            self.assertIs(sessions.reset(capability_of(outcome.link), NEW_PASSWORD), False)

    def test_the_link_lifetime_follows_the_requested_ttl(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            self.bootstrap(db, directory, ttl=7200)
            seconds = db.admin.execute('SELECT extract(epoch FROM expires_at-clock_timestamp()) FROM forge.account_password_resets').fetchone()[0]
            self.assertTrue(7100 < float(seconds) <= 7200, seconds)

    def test_a_rerun_is_a_no_op_even_with_another_address_and_never_rewrites_the_file(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            first, path = self.bootstrap(db, directory)
            before, content = counts(db), path.read_text('utf-8')
            for email in (EMAIL, 'someone-else@example.test'):
                with self.subTest(email=email):
                    outcome = bootstrap_owner(db.admin, email=email, name='Other', origin=ORIGIN, ttl_seconds=60,
                                              write_link=lambda link: self.fail('a no-op must not write a link'))
                    self.assertEqual((outcome.created, outcome.link), (False, None))
            self.assertEqual(counts(db), before)
            self.assertEqual(path.read_text('utf-8'), content)

    def test_an_existing_account_with_that_address_is_refused_and_never_promoted(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            add_account(db.admin, EMAIL)
            before = counts(db)
            with self.assertRaises(BootstrapRefused) as caught:
                self.bootstrap(db, directory)
            self.assertEqual(caught.exception.code, 'OWNER_ACCOUNT_EXISTS')
            self.assertEqual(counts(db), before)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_a_link_that_cannot_be_stored_rolls_every_row_back(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'owner-link.txt'
            path.write_text('earlier\n', 'utf-8')
            before = counts(db)
            with self.assertRaises(FileExistsError):
                bootstrap_owner(db.admin, email=EMAIL, name='Platform Owner', origin=ORIGIN, ttl_seconds=60,
                                write_link=lambda link: write_private_file(path, link + '\n'))
            self.assertEqual(counts(db), before)
            self.assertEqual(path.read_text('utf-8'), 'earlier\n')

    def test_the_stored_password_is_a_valid_unusable_scrypt_record_never_derived_from_anything_printed(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            first, _ = self.bootstrap(db, directory)
            stored = db.admin.execute('SELECT password_hash FROM forge.owned_accounts').fetchone()[0]
            self.assertRegex(stored, r'^forge\$scrypt\$v1\$131072\$8\$1\$[A-Za-z0-9_-]{22}\$[A-Za-z0-9_-]{43}$')
            self.assertNotIn(hashlib.sha256(capability_of(first.link).encode()).hexdigest(), stored)


if __name__ == '__main__':
    unittest.main()
