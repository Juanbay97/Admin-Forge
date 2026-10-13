"""Owned PostgreSQL 0029 mandatory TOTP: enrollment, activation, replay guard, attempt budget, recovery codes, per-session
verification and freshness, with the sealed secret and hashed codes as the only stored material."""
import base64
from pathlib import Path
import sys
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptography.fernet import Fernet
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F28, F29, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE, PLATFORM_MFA_MIGRATION
from forge.platform import (MfaEnrolled, MfaInvalid, MfaLocked, MfaRequired, PlatformDenied, PlatformService)
from forge.platform_store import PostgresPlatformStore
from forge.platform_totp import SecretSealer, hash_recovery_code, totp
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

SERVICE_FUNCTIONS = ('forge.platform_mfa_status(text)', 'forge.platform_mfa_enroll(text,text,text[])',
                     'forge.platform_mfa_begin(text)', 'forge.platform_mfa_confirm(text,bigint)',
                     'forge.platform_mfa_recover(text,text)')
TABLES = ('platform_totp', 'platform_recovery_codes', 'platform_mfa_sessions')


class MfaProfileTests(unittest.TestCase):
    def test_0029_follows_0028_with_its_own_pinned_checkpoint(self):
        self.assertEqual(PLATFORM_MFA_MIGRATION, '0029_platform_mfa.sql')
        self.assertEqual(MVP_ADDITIONS[at(PLATFORM_MFA_MIGRATION) - 1:at(PLATFORM_MFA_MIGRATION) + 1], ('0028_platform_scope.sql', PLATFORM_MFA_MIGRATION))
        self.assertEqual(MVP_CHECKPOINTS[at(PLATFORM_MFA_MIGRATION):at(PLATFORM_MFA_MIGRATION) + 2], (F28, F29))
        self.assertRegex(F29 or '', r'^[0-9a-f]{64}$', 'F29 must be pinned')
        self.assertNotEqual(F29, F28)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class MfaFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0029 == upgrade from the 0028 profile, pinned as F29; the upgrade keeps the owner and its audit."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0028_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(PLATFORM_MFA_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, PLATFORM_MFA_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F28)
            owner = add_owner(conn)
            conn.execute("SELECT forge.platform_audit_write(%s,'company.created',NULL)", (owner,))
            conn.execute(migration_text(PLATFORM_MFA_MIGRATION))
            self.assertEqual(conn.execute('SELECT count(*) FROM forge.platform_audit_log').fetchone(), (1,))
            self.assertEqual(conn.execute('SELECT role FROM forge.platform_roles').fetchall(), [('platform_owner',)])
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0029 platform MFA checkpoint F29:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0028 must be identical')
        self.assertEqual(fresh, F29, 'F29 must be pinned to the reviewed value')
        self.assertNotEqual(fresh, F28)


class MfaSchemaTests(unittest.TestCase):
    def test_only_the_authority_holds_privileges_and_each_function_is_definer_owned_by_it(self):
        with mvp_database() as db:
            privilege = 'SELECT has_table_privilege(%s,%s,%s)'
            for table in TABLES:
                for role in ('public', 'forge_platform_service', 'forge_runtime', 'forge_account_service', 'forge_enrollment',
                             'forge_gateway_service', 'forge_branding_service'):
                    for action in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'):
                        self.assertFalse(db.admin.execute(privilege, (role, 'forge.' + table, action)).fetchone()[0], (table, role, action))
                self.assertEqual(db.admin.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass",
                                                  ('forge.' + table,)).fetchone(), (True, True))
            for signature in (*SERVICE_FUNCTIONS, 'forge.platform_session_owner(text)'):
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute('SELECT pg_get_userbyid(proowner),prosecdef,proconfig FROM pg_proc '
                                                      'WHERE oid=%s::regprocedure', (signature,)).fetchone(),
                                     ('forge_platform_authority', True, ['search_path=pg_catalog']))
                    expected = signature in SERVICE_FUNCTIONS
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege('forge_platform_service',%s::regprocedure,'EXECUTE')",
                                                      (signature,)).fetchone(), (expected,))
                    self.assertEqual(db.admin.execute("SELECT has_function_privilege('public',%s::regprocedure,'EXECUTE')",
                                                      (signature,)).fetchone(), (False,))


class MfaFlowTests(unittest.TestCase):
    def world(self, db):
        self.sealer = SecretSealer(Fernet.generate_key())
        self.now = time.time()
        self.service = PlatformService(PostgresPlatformStore(db.pool('forge_platform_service')), self.sealer, clock=lambda: self.now)
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db)
        self.db = db

    def secret_of(self, enrollment):
        return base64.b32decode(enrollment.secret + '=' * (-len(enrollment.secret) % 8))

    def code(self, enrollment, offset=0):
        return totp(self.secret_of(enrollment), int(self.now) // 30 + offset)

    def activate(self):
        enrollment = self.service.enroll_mfa(self.token)
        self.service.verify_mfa(self.token, self.code(enrollment))
        return enrollment

    def state(self):
        return self.service.mfa_status(self.token)

    def test_a_password_only_session_is_denied_every_platform_call_except_identity_and_status(self):
        with mvp_database() as db:
            self.world(db)
            self.assertEqual((self.service.me(self.token).role, self.state().state, self.state().verified), ('platform_owner', 'none', False))
            for run in (lambda: self.service.companies(self.token), lambda: self.service.audit(self.token),
                        lambda: self.service.company(self.token, self.owner)):
                with self.assertRaises(MfaRequired):
                    run()

    def test_the_first_valid_code_activates_the_factor_unlocks_the_session_and_audits_once(self):
        with mvp_database() as db:
            self.world(db)
            enrollment = self.service.enroll_mfa(self.token)
            self.assertEqual((self.state().state, self.state().verified), ('pending', False))
            with self.assertRaises(MfaRequired):
                self.service.companies(self.token)
            self.service.verify_mfa(self.token, self.code(enrollment))
            status = self.state()
            self.assertEqual((status.state, status.verified, status.fresh), ('active', True, True))
            self.assertEqual(self.service.companies(self.token), [])
            self.assertEqual([entry.action for entry in self.service.audit(self.token)], ['owner.mfa_enrolled'])
            sealed, = db.admin.execute('SELECT sealed_secret FROM forge.platform_totp').fetchone()
            self.assertEqual(self.sealer.open(sealed), self.secret_of(enrollment))
            self.assertNotIn(enrollment.secret, sealed)
            stored = db.admin.execute('SELECT code_hash,used_at FROM forge.platform_recovery_codes').fetchall()
            self.assertEqual(sorted(row[0] for row in stored), sorted(hash_recovery_code(c) for c in enrollment.recovery_codes))
            self.assertEqual({row[1] for row in stored}, {None})
            self.assertNotIn(enrollment.recovery_codes[0].replace('-', ''), ' '.join(str(row) for row in stored))

    def test_a_code_cannot_be_replayed_and_an_older_step_is_refused_while_a_newer_one_is_accepted(self):
        with mvp_database() as db:
            self.world(db)
            enrollment = self.activate()
            _, other_digest = sign_in(db)
            other = self.token
            self.token = sign_in(db)[0]
            self.assertEqual(db.admin.execute('SELECT last_step FROM forge.platform_totp').fetchone(), (int(self.now) // 30,))
            with self.assertRaises(MfaInvalid):
                self.service.verify_mfa(self.token, self.code(enrollment))  # the same step: replay, even on another session
            with self.assertRaises(MfaInvalid):
                self.service.verify_mfa(self.token, self.code(enrollment, -1))  # an older step than the last accepted
            self.service.verify_mfa(self.token, self.code(enrollment, +1))
            self.assertEqual(db.admin.execute('SELECT last_step FROM forge.platform_totp').fetchone(), (int(self.now) // 30 + 1,))
            self.assertIsNotNone(other)

    def test_a_step_outside_the_database_window_is_refused_even_if_the_application_accepts_it(self):
        with mvp_database() as db:
            self.world(db)
            enrollment = self.activate()
            self.token = sign_in(db)[0]
            self.service.store.mfa_begin(self.digest)  # reserve, then confirm a step the clock never allowed
            far = int(self.now) // 30 + 10
            with self.assertRaises(MfaInvalid):
                self.service.store.mfa_confirm(self.digest, far)
            with self.assertRaises(MfaInvalid):  # the database alone also refuses the step already accepted
                self.service.store.mfa_confirm(self.digest, int(self.now) // 30)
            self.assertIsNotNone(enrollment)

    def test_five_wrong_codes_lock_even_the_right_code_until_the_window_expires(self):
        with mvp_database() as db:
            self.world(db)
            enrollment = self.service.enroll_mfa(self.token)
            for _ in range(5):
                with self.assertRaises(MfaInvalid):
                    self.service.verify_mfa(self.token, '000000')
            with self.assertRaises(MfaLocked):
                self.service.verify_mfa(self.token, self.code(enrollment))
            with self.assertRaises(MfaLocked):
                self.service.recover_mfa(self.token, enrollment.recovery_codes[0])
            db.admin.execute("UPDATE forge.platform_totp SET attempt_window=clock_timestamp()-interval '16 minutes'")
            self.service.verify_mfa(self.token, self.code(enrollment))
            self.assertEqual(self.state().state, 'active')
            self.assertEqual(db.admin.execute('SELECT failed_attempts FROM forge.platform_totp').fetchone(), (0,),
                             'a success resets the budget')

    def test_a_recovery_code_works_once_is_stored_hashed_and_is_audited(self):
        with mvp_database() as db:
            self.world(db)
            enrollment = self.activate()
            self.token = sign_in(db)[0]
            self.assertEqual(self.state().verified, False)
            code = enrollment.recovery_codes[3]
            self.service.recover_mfa(self.token, code.lower().replace('-', ' '))
            self.assertEqual(self.state().verified, True)
            self.assertEqual(self.service.companies(self.token), [])
            third = sign_in(db)[0]
            with self.assertRaises(MfaInvalid):
                self.service.recover_mfa(third, code)
            with self.assertRaises(MfaInvalid):
                self.service.recover_mfa(third, 'AAAA-AAAA-AAAA-AAAA')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_recovery_codes WHERE used_at IS NOT NULL').fetchone(), (1,))
            self.assertEqual([entry.action for entry in self.service.audit(self.token)], ['owner.mfa_recovery_used', 'owner.mfa_enrolled'])
            self.service.recover_mfa(third, enrollment.recovery_codes[4])

    def test_an_active_factor_cannot_be_enrolled_again_but_a_pending_one_can_restart_and_replaces_everything(self):
        with mvp_database() as db:
            self.world(db)
            first = self.service.enroll_mfa(self.token)
            second = self.service.enroll_mfa(self.token)
            self.assertNotEqual(first.secret, second.secret)
            with self.assertRaises(MfaInvalid):
                self.service.verify_mfa(self.token, self.code(first))
            self.service.verify_mfa(self.token, self.code(second))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_recovery_codes').fetchone(), (10,))
            with self.assertRaises(MfaEnrolled):
                self.service.enroll_mfa(self.token)
            with self.assertRaises(MfaInvalid):
                self.service.recover_mfa(sign_in(db)[0], first.recovery_codes[0])

    def test_verification_belongs_to_one_session_and_disappears_with_it(self):
        with mvp_database() as db:
            self.world(db)
            self.activate()
            second = sign_in(db)[0]
            self.assertEqual((self.state().verified, self.service.mfa_status(second).verified), (True, False))
            with self.assertRaises(MfaRequired):
                self.service.companies(second)
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_mfa_sessions').fetchone(), (1,))
            db.admin.execute("DELETE FROM forge.account_sessions WHERE capability_hash=%s", (self.digest,))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_mfa_sessions').fetchone(), (0,))

    def test_a_change_needs_a_fresh_verification_but_a_read_does_not(self):
        with mvp_database() as db:
            self.world(db)
            self.activate()
            db.admin.execute("UPDATE forge.platform_mfa_sessions SET verified_at=clock_timestamp()-interval '31 minutes'")
            self.assertEqual((self.state().verified, self.state().fresh), (True, False))
            self.assertEqual(self.service.companies(self.token), [])
            self.assertEqual(db.admin.execute('SELECT forge.platform_lock_owner(%s,false)', (self.digest,)).fetchone(), (self.owner,))
            self.assertEqual(refusal(self, lambda: db.admin.execute('SELECT forge.platform_lock_owner(%s,true)', (self.digest,))), 'MFA_REQUIRED')
            db.admin.execute("UPDATE forge.platform_mfa_sessions SET verified_at=clock_timestamp()-interval '29 minutes'")
            self.assertEqual(db.admin.execute('SELECT forge.platform_lock_owner(%s,true)', (self.digest,)).fetchone(), (self.owner,))

    def test_an_owner_whose_factor_row_is_gone_loses_access_even_with_a_session_row(self):
        with mvp_database() as db:
            self.world(db)
            self.activate()
            db.admin.execute('DELETE FROM forge.platform_totp')
            with self.assertRaises(MfaRequired):
                self.service.companies(self.token)

    def test_only_owners_may_touch_the_factor_functions(self):
        with mvp_database() as db:
            self.world(db)
            admin = provision(db.admin, SEED[:1], lambda created: None)[0].accounts[0]
            add_owner(db.admin, 'viewer@platform.test', 'platform_viewer')
            for token in (sign_in(db, admin.email, admin.password)[0], sign_in(db, 'viewer@platform.test')[0], 'A' * 43):
                with self.subTest(token=token[:4]):
                    with self.assertRaises(PlatformDenied):
                        self.service.enroll_mfa(token)
                    with self.assertRaises(PlatformDenied):
                        self.service.verify_mfa(token, '123456')
                    with self.assertRaises(PlatformDenied):
                        self.service.recover_mfa(token, 'AAAA-AAAA-AAAA-AAAA')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_totp').fetchone(), (0,))

    def test_a_malformed_enrollment_is_refused_by_the_database_whatever_the_application_sends(self):
        with mvp_database() as db:
            self.world(db)
            good = ['a' * 64] * 10
            for sealed, hashes in (('short', good), ('x' * 100, good[:9]), ('x' * 100, ['zz'] * 10), ('x' * 100, ['a' * 64] * 9 + ['b' * 64][:1] + ['c' * 64]),
                                   ('x' * 100, ['a' * 64] * 10)):
                with self.subTest(sealed=len(sealed), hashes=len(hashes)):
                    self.assertEqual(refusal(self, lambda: call(db, 'SELECT forge.platform_mfa_enroll(%s,%s,%s)', (self.digest, sealed, hashes))),
                                     'PLATFORM_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.platform_totp').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
