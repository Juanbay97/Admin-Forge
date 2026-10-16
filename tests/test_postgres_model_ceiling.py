"""Owned PostgreSQL 0049: the model ceiling is chosen from discovered models and a refusal says the ceiling is the reason.

The platform owner may only set a ceiling inside the company's current discovery (no discovery: PLATFORM_INVALID; a model
outside it: MODEL_NOT_DISCOVERED; the empty list still denies everything). A company administrator publishing outside the
ceiling gets GATEWAY_OUTSIDE_CEILING, and the administrator's refresh can read the ceiling to list only publishable models.
"""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.gateway_catalog import publication_material
from forge.gateway_configuration import GatewayOutsideCeiling
from forge.gateway_keys import DiscoveryRequired, GatewayKeys, ModelNotDiscovered
from forge.gateway_keys_store import PostgresGatewayKeyStore
from forge.gateway_pool_store import PostgresPoolCatalogStore
from forge.provisioning import SEED
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F48, F49, MODEL_CEILING_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS
from mvp_support import at, mvp_database
from platform_support import call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_catalog import SchemaWorld
from test_postgres_platform_schema import drop_platform_roles

SET = 'SELECT * FROM forge.platform_company_model_access_set(%s,%s,%s)'
HELPERS = {'forge.gateway_discovered_models(uuid)': ('forge_gateway_authority', {'forge_platform_authority': True, 'forge_gateway_service': False,
                                                                                  'forge_platform_service': False, 'public': False}),
           'forge.gateway_catalog_ceiling(text,uuid)': ('forge_gateway_authority', {'forge_gateway_service': True, 'forge_platform_authority': False,
                                                                                    'forge_platform_service': False, 'public': False}),
           'forge.platform_company_model_access_set(text,uuid,text[])': ('forge_platform_authority', {'forge_platform_service': True,
                                                                                                      'forge_gateway_service': False, 'public': False})}


class CeilingProfileTests(unittest.TestCase):
    def test_0049_is_part_of_the_registered_profile_right_after_0048_with_its_own_pinned_checkpoint(self):
        self.assertEqual(MODEL_CEILING_MIGRATION, '0049_model_ceiling_validation.sql')
        self.assertEqual(MVP_ADDITIONS[at(MODEL_CEILING_MIGRATION) - 1], '0048_platform_catalog.sql')
        self.assertEqual(MVP_ADDITIONS[-1], MODEL_CEILING_MIGRATION)
        self.assertEqual(MVP_CHECKPOINTS[at(MODEL_CEILING_MIGRATION):at(MODEL_CEILING_MIGRATION) + 2], (F48, F49))
        self.assertRegex(F49 or '', r'^[0-9a-f]{64}$', 'F49 must be pinned')
        self.assertNotEqual(F49, F48)


class CeilingFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0048_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(MODEL_CEILING_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, MODEL_CEILING_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F48)
            conn.execute(migration_text(MODEL_CEILING_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0049 model ceiling validation checkpoint F49:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0048 must be identical')
        self.assertEqual(fresh, F49, 'F49 must be pinned to the reviewed value')


class CeilingWorld(SchemaWorld):
    def ceiling(self):
        return self.db.admin.execute('SELECT ceiling FROM forge.organization_gateway_profiles WHERE organization_id=%s', (self.org,)).fetchone()[0]

    def set_ceiling(self, models):
        return call(self.db, SET, (self.digest, self.org, models))

    def admin_session(self):
        admin = self.admins[SEED[0].slug]
        return sign_in(self.db, admin.email, admin.password)[1]


class CeilingFunctionTests(CeilingWorld):
    def test_the_helpers_are_owned_by_the_authority_that_may_read_their_tables_and_executable_only_by_their_caller(self):
        with mvp_database() as db:
            owner = 'SELECT pg_get_userbyid(p.proowner),p.prosecdef,p.proconfig FROM pg_proc p WHERE p.oid=%s::regprocedure'
            execute = "SELECT has_function_privilege(%s,%s::regprocedure,'EXECUTE')"
            for signature, (role_owner, grants) in HELPERS.items():
                with self.subTest(signature=signature):
                    self.assertEqual(db.admin.execute(owner, (signature,)).fetchone(), (role_owner, True, ['search_path=pg_catalog']))
                    for role, allowed in grants.items():
                        self.assertEqual(db.admin.execute(execute, (role, signature)).fetchone(), (allowed,), role)
            for role in ('forge_platform_authority', 'forge_gateway_authority'):
                self.assertEqual(db.admin.execute("SELECT has_schema_privilege(%s,'forge','CREATE')", (role,)).fetchone(), (False,))

    def test_a_ceiling_needs_a_current_discovery_and_a_refusal_changes_and_audits_nothing(self):
        with mvp_database() as db:
            self.build(db)
            before, audited = self.ceiling(), self.audit()
            self.assertEqual(refusal(self, lambda: self.set_ceiling(['gpt-a'])), 'PLATFORM_INVALID', 'nothing was discovered yet')
            self.assertEqual((self.ceiling(), self.audit()), (before, audited))

    def test_a_model_outside_the_discovery_is_refused_with_its_own_message_and_the_ceiling_stays(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a', 'gpt-b'])
            self.set_ceiling(['gpt-a'])
            audited = self.audit()
            for models in (['Deepseek'], ['gpt-a', 'Deepseek'], ['GPT-A']):
                with self.subTest(models=models):
                    self.assertEqual(refusal(self, lambda: self.set_ceiling(models)), 'MODEL_NOT_DISCOVERED')
            self.assertEqual((self.ceiling(), self.audit()), (['gpt-a'], audited))
            for bad in (['has space'], ['gpt-a', 'gpt-a'], ['']):
                with self.subTest(shape=bad):
                    self.assertEqual(refusal(self, lambda: self.set_ceiling(bad)), 'PLATFORM_INVALID', 'the shape checks still come first')

    def test_a_discovered_subset_is_set_whole_audited_and_the_empty_list_needs_no_discovery(self):
        with mvp_database() as db:
            self.build(db)
            self.assertEqual(self.set_ceiling([]), [([],)], 'denying everything needs no discovery')
            self.save(['gpt-a', 'gpt-b', 'gpt-c'])
            self.assertEqual(self.set_ceiling(['gpt-c', 'gpt-a']), [(['gpt-c', 'gpt-a'],)])
            self.assertEqual(self.ceiling(), ['gpt-c', 'gpt-a'])
            self.assertEqual(self.set_ceiling(['gpt-a', 'gpt-b', 'gpt-c']), [(['gpt-a', 'gpt-b', 'gpt-c'],)])
            self.assertEqual(self.audit().count('company.model_access_set'), 3)

    def test_a_discovery_of_an_older_profile_revision_no_longer_counts(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a'])
            db.admin.execute('UPDATE forge.organization_gateway_profiles SET revision=2 WHERE organization_id=%s', (self.org,))
            self.assertEqual(refusal(self, lambda: self.set_ceiling(['gpt-a'])), 'PLATFORM_INVALID', 'the discovery belongs to revision 1')
            self.save(['gpt-a'], revision=2)
            self.assertEqual(self.set_ceiling(['gpt-a']), [(['gpt-a'],)])

    def test_only_a_fresh_verified_owner_can_set_a_ceiling(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a'])
            for digest, code in ((self.admin_session(), 'PLATFORM_DENIED'), ('0' * 64, 'PLATFORM_DENIED'), (sign_in(db, mfa=False)[1], 'MFA_REQUIRED')):
                self.assertEqual(refusal(self, lambda: call(db, SET, (digest, self.org, ['gpt-a']))), code)
            self.assertEqual(refusal(self, lambda: call(db, SET, (self.digest, uuid4(), []))), 'PLATFORM_NOT_FOUND')
            self.assertEqual(self.ceiling(), [])


class AdministratorCeilingTests(CeilingWorld):
    PUBLISH = 'SELECT forge.gateway_catalog_publish(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)'

    def publish_as_admin(self, mapping, default, *, expected=0):
        import json
        binding = self.db.admin.execute('SELECT binding_id FROM forge.organization_gateway_profiles WHERE organization_id=%s', (self.org,)).fetchone()[0]
        payload, checksum, selection = publication_material(self.org, binding, expected, 1, mapping, default)
        return call(self.db, self.PUBLISH, (self.admin_session(), self.org, uuid4(), expected, 1, binding, json.dumps(mapping), default,
                                            payload, checksum, selection), role='forge_gateway_service')

    def test_publishing_outside_the_ceiling_is_refused_with_its_own_message_and_nothing_is_written(self):
        with mvp_database() as db:
            self.build(db)
            self.save(['gpt-a', 'gpt-b'])
            self.set_ceiling(['gpt-a'])
            self.assertEqual(refusal(self, lambda: self.publish_as_admin({'fast': 'gpt-b'}, 'fast')), 'GATEWAY_OUTSIDE_CEILING')
            self.assertEqual(refusal(self, lambda: self.publish_as_admin({'fast': 'gpt-a', 'deep': 'gpt-b'}, 'fast')), 'GATEWAY_OUTSIDE_CEILING')
            self.assertEqual(refusal(self, lambda: self.publish_as_admin({'fast': 'not-discovered'}, 'fast')), 'GATEWAY_INVALID',
                             'an undiscovered model is still an invalid selection, not a ceiling refusal')
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_catalog_snapshots').fetchone(), (0,))
            self.assertEqual(self.publish_as_admin({'fast': 'gpt-a'}, 'fast'), [(1,)])

    def test_the_administrator_can_read_the_ceiling_to_list_only_what_it_can_publish(self):
        with mvp_database() as db:
            self.build(db)
            read = 'SELECT forge.gateway_catalog_ceiling(%s,%s)'
            admin = self.admin_session()
            self.assertEqual(call(db, read, (admin, self.org), role='forge_gateway_service'), [([],)], 'a new profile allows no model')
            self.save(['gpt-a', 'gpt-b'])
            self.set_ceiling(['gpt-b'])
            self.assertEqual(call(db, read, (admin, self.org), role='forge_gateway_service'), [(['gpt-b'],)])
            other = db.admin.execute('SELECT id FROM forge.organizations WHERE id<>%s', (self.org,)).fetchone()[0]
            for digest, org in ((admin, other), ('0' * 64, self.org), (self.digest, self.org)):
                self.assertEqual(refusal(self, lambda: call(db, read, (digest, org), role='forge_gateway_service')), 'GATEWAY_DENIED')

    def test_the_services_surface_both_rules_as_typed_errors(self):
        with mvp_database() as db:
            self.build(db)
            store = PostgresGatewayKeyStore(db.pool('forge_platform_service'))
            self.assertIsNone(store.discovered(self.digest, self.org))
            self.save(['gpt-a', 'gpt-b'])
            self.assertEqual(store.discovered(self.digest, self.org), ['gpt-a', 'gpt-b'])
            with self.assertRaises(ModelNotDiscovered):  # the database rule, reached without the service pre-check
                store.set_ceiling(self.digest, self.org, ['Deepseek'])
            self.assertEqual(store.set_ceiling(self.digest, self.org, ['gpt-b']), ['gpt-b'])
            pool = PostgresPoolCatalogStore(db.pool('forge_gateway_service'))
            self.assertEqual(pool.ceiling(self.admin_session(), self.org), ['gpt-b'])
            self.assertIsNone(PostgresGatewayKeyStore(db.pool('forge_platform_service')).discovered(self.digest, self.orgs[SEED[1].slug]),
                              'a company without an assignment has no discovery')

    def test_the_service_pre_check_names_the_rule_before_the_database_is_asked(self):
        with mvp_database() as db:
            self.build(db)
            service = GatewayKeys(PostgresGatewayKeyStore(db.pool('forge_platform_service')), cipher=None)
            with self.assertRaises(DiscoveryRequired):
                service.set_ceiling(self.token, self.org, ['gpt-a'])
            self.save(['gpt-a'])
            with self.assertRaises(ModelNotDiscovered):
                service.set_ceiling(self.token, self.org, ['gpt-a', 'Deepseek'])
            self.assertEqual(service.set_ceiling(self.token, self.org, ['gpt-a']), ['gpt-a'])
            self.assertEqual(self.audit().count('company.model_access_set'), 1, 'refused attempts are not audited')


class OutsideCeilingErrorTests(unittest.TestCase):
    def test_the_error_carries_the_finite_code_the_api_returns(self):
        self.assertEqual(GatewayOutsideCeiling().code, 'MODEL_NOT_ALLOWED')


if __name__ == '__main__':
    unittest.main()
