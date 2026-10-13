"""Owned PostgreSQL 0032 gateway key pool: the platform owns sealed keys and assigns them to companies with a priority.

The database never sees key text (only an opaque sealed value and a last-4 hint) and never pins a single origin; the
deployment allow-list in the application is the origin authority. Every function re-validates a fresh verified owner.
"""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F31, F32, GATEWAY_KEY_POOL_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS, MVP_PROFILE
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles

SEALED = 'sealed-fixture-' + 'x' * 120
ORIGIN = 'https://gateway.fixture.example'


class KeyPoolProfileTests(unittest.TestCase):
    def test_0032_follows_0031_with_its_own_pinned_checkpoint(self):
        self.assertEqual(GATEWAY_KEY_POOL_MIGRATION, '0032_gateway_key_pool.sql')
        self.assertEqual(MVP_ADDITIONS[at(GATEWAY_KEY_POOL_MIGRATION) - 1], '0031_platform_company_operations.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(GATEWAY_KEY_POOL_MIGRATION):at(GATEWAY_KEY_POOL_MIGRATION) + 2], (F31, F32))
        self.assertRegex(F32 or '', r'^[0-9a-f]{64}$', 'F32 must be pinned')
        self.assertNotEqual(F32, F31)
        self.assertEqual(len(MVP_CHECKPOINTS), len(MVP_ADDITIONS) + 1)
        self.assertTrue(MVP_PROFILE.startswith('0001-0005+0010-00'))


class KeyPoolFingerprintGateTests(unittest.TestCase):
    """Fresh apply of 0032 == upgrade from the 0031 profile, pinned as F32; the upgrade keeps companies and legacy gateways."""
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0031_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(GATEWAY_KEY_POOL_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, GATEWAY_KEY_POOL_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F31)
            result = provision(conn, SEED[:1], lambda created: None)[0]
            conn.execute(migration_text(GATEWAY_KEY_POOL_MIGRATION))
            self.assertEqual(conn.execute('SELECT slug FROM forge.organizations').fetchall(), [(result.slug,)])
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0032 gateway key pool checkpoint F32:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0031 must be identical')
        self.assertEqual(fresh, F32, 'F32 must be pinned to the reviewed value')


class PoolWorld(unittest.TestCase):
    def build(self, db, *, mfa=True):
        self.db = db
        results = provision(db.admin, SEED, lambda created: None)
        self.orgs = {result.slug: result.organization_id for result in results}
        self.admins = {result.slug: result.accounts[0] for result in results}
        self.owner = add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=mfa)

    def create(self, label='primary', origin=ORIGIN, sealed=SEALED, hint='abcd', key=None, digest=None):
        key = key or uuid4()
        rows = call(self.db, 'SELECT * FROM forge.platform_gateway_key_create(%s,%s,%s,%s,%s,%s)',
                    (digest or self.digest, key, label, origin, sealed, hint))
        return key, rows

    def assign(self, org, *entries, digest=None):
        import json
        return call(self.db, 'SELECT * FROM forge.platform_company_gateway_set(%s,%s,%s::jsonb)',
                    (digest or self.digest, org, json.dumps([{'key_id': str(k), 'priority': p, 'active': a} for k, p, a in entries])))

    def audit(self):
        return self.db.admin.execute('SELECT action,organization_id,subject_id FROM forge.platform_audit_log ORDER BY id').fetchall()


class KeyLifecycleTests(PoolWorld):
    def test_creating_and_listing_a_key_exposes_label_origin_hint_and_never_the_sealed_value(self):
        with mvp_database() as db:
            self.build(db)
            key, rows = self.create()
            self.assertEqual(rows[0][:7], (key, 'primary', ORIGIN, 1, 'active', True, 'abcd'))
            placeholder, _ = self.create('spare', sealed=None, hint=None)
            listed = call(db, 'SELECT * FROM forge.platform_gateway_key_list(%s)', (self.digest,))
            self.assertEqual({(row[0], row[1], row[5]) for row in listed}, {(key, 'primary', True), (placeholder, 'spare', False)})
            self.assertNotIn(SEALED, repr(listed), 'no list column carries the sealed value')
            self.assertEqual(self.audit(), [('gateway_key.created', None, key), ('gateway_key.created', None, placeholder)])

    def test_the_database_accepts_any_canonical_https_origin_and_refuses_malformed_ones(self):
        with mvp_database() as db:
            self.build(db)
            self.create('other', origin='https://another-gateway.example:8443')
            for bad in ('http://gateway.example', 'https://gateway.example/path', 'https://127.0.0.1', 'ftp://x.example', 'HTTPS://X.EXAMPLE'):
                with self.subTest(origin=bad):
                    self.assertEqual(refusal(self, lambda: self.create('bad', origin=bad)), 'PLATFORM_INVALID')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (1,))

    def test_rotation_is_compare_and_swap_on_the_revision_and_disabling_is_idempotent(self):
        with mvp_database() as db:
            self.build(db)
            key, _ = self.create()
            rotated = call(db, 'SELECT * FROM forge.platform_gateway_key_rotate(%s,%s,%s,%s,%s)', (self.digest, key, 1, SEALED + 'y', 'wxyz'))
            self.assertEqual((rotated[0][3], rotated[0][6]), (2, 'wxyz'))
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_gateway_key_rotate(%s,%s,%s,%s,%s)',
                                                        (self.digest, key, 1, SEALED, 'zzzz'))), 'REVISION_CONFLICT')
            self.assertEqual(db.admin.execute('SELECT revision,last4 FROM forge.gateway_keys WHERE id=%s', (key,)).fetchone(), (2, 'wxyz'))
            for _ in range(2):
                self.assertEqual(call(db, 'SELECT * FROM forge.platform_gateway_key_set_status(%s,%s,%s)', (self.digest, key, False))[0][4], 'disabled')
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_gateway_key_set_status(%s,%s,%s)', (self.digest, key, True))[0][4], 'active')
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_gateway_key_set_status(%s,%s,%s)',
                                                        (self.digest, uuid4(), False))), 'PLATFORM_NOT_FOUND')

    def test_only_a_fresh_verified_owner_may_call_and_an_unverified_session_changes_nothing(self):
        with mvp_database() as db:
            self.build(db, mfa=False)
            self.assertEqual(refusal(self, lambda: self.create()), 'MFA_REQUIRED')
            self.assertEqual(refusal(self, lambda: self.create(digest='0' * 64)), 'PLATFORM_DENIED')
            _, admin_digest = sign_in(db, self.admins['org-a'].email, self.admins['org-a'].password)
            self.assertEqual(refusal(self, lambda: self.create(digest=admin_digest)), 'PLATFORM_DENIED')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.gateway_keys').fetchone(), (0,))
            self.assertEqual(self.audit(), [])


class AssignmentTests(PoolWorld):
    def test_a_company_gets_many_keys_ordered_by_priority_and_a_default_deny_ceiling(self):
        with mvp_database() as db:
            self.build(db)
            k1, _ = self.create('one')
            k2, _ = self.create('two', hint='efgh')
            org = self.orgs['org-a']
            rows = self.assign(org, (k1, 2, True), (k2, 1, True))
            self.assertEqual([(row[0], row[3], row[4]) for row in rows], [(k2, 1, True), (k1, 2, True)])
            profile = db.admin.execute('SELECT revision,ceiling FROM forge.organization_gateway_profiles WHERE organization_id=%s', (org,)).fetchone()
            self.assertEqual(profile, (1, []), 'a new profile allows no model until the platform sets the ceiling')
            reordered = self.assign(org, (k1, 1, True), (k2, 2, False))
            self.assertEqual([(row[0], row[3], row[4]) for row in reordered], [(k1, 1, True), (k2, 2, False)])
            self.assertEqual(db.admin.execute('SELECT revision FROM forge.organization_gateway_profiles WHERE organization_id=%s', (org,)).fetchone(), (1,),
                             'reordering never changes the catalog binding revision')
            self.assertEqual([row[0] for row in self.audit()].count('company.gateway_assigned'), 2)
            self.assertEqual(self.audit()[-1][1:], (org, None))

    def test_invalid_assignments_change_nothing(self):
        with mvp_database() as db:
            self.build(db)
            key, _ = self.create()
            org = self.orgs['org-a']
            self.assign(org, (key, 1, True))
            other, _ = self.create('other')
            for entries in (((key, 1, True), (other, 1, True)), ((uuid4(), 1, True),), ((key, 0, True),), ((key, 1, True), (key, 2, True))):
                with self.subTest(entries=len(entries)):
                    self.assertEqual(refusal(self, lambda: self.assign(org, *entries)), 'PLATFORM_INVALID')
            self.assertEqual(refusal(self, lambda: self.assign(uuid4(), (key, 1, True))), 'PLATFORM_NOT_FOUND')
            self.assertEqual(db.admin.execute('SELECT key_id,priority FROM forge.organization_gateway_keys').fetchall(), [(key, 1)])

    def test_the_ceiling_is_set_whole_and_audited_and_an_empty_list_denies_everything(self):
        with mvp_database() as db:
            self.build(db)
            org = self.orgs['org-b']
            call(db, 'SELECT * FROM forge.platform_company_model_access_set(%s,%s,%s)', (self.digest, org, ['gpt-a', 'gpt-b']))
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_company_model_access_get(%s,%s)', (self.digest, org)), [(['gpt-a', 'gpt-b'],)])
            call(db, 'SELECT * FROM forge.platform_company_model_access_set(%s,%s,%s)', (self.digest, org, []))
            self.assertEqual(call(db, 'SELECT * FROM forge.platform_company_model_access_get(%s,%s)', (self.digest, org)), [([],)])
            self.assertEqual(refusal(self, lambda: call(db, 'SELECT * FROM forge.platform_company_model_access_set(%s,%s,%s)',
                                                        (self.digest, org, ['has space']))), 'PLATFORM_INVALID')
            self.assertEqual([row[0] for row in self.audit()], ['company.model_access_set'] * 2)


class IsolationTests(PoolWorld):
    def test_no_service_role_holds_any_privilege_on_the_pool_tables_and_row_security_is_forced(self):
        with mvp_database() as db:
            for table in ('gateway_keys', 'organization_gateway_keys', 'organization_gateway_profiles'):
                self.assertEqual(db.admin.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',
                                                  ('forge.' + table,)).fetchone(), (True, True), table)
                for role in ('forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'forge_runtime', 'forge_branding_service'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, 'forge.' + table)).fetchone(),
                                     (False,), (role, table))
            self.assertEqual(db.admin.execute("SELECT has_column_privilege('forge_gateway_authority','forge.gateway_keys','encrypted_key','INSERT')").fetchone(),
                             (False,), 'the member-route authority only reads the pool')


if __name__ == '__main__':
    unittest.main()
