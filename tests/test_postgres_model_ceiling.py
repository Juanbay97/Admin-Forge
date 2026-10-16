"""Owned PostgreSQL 0049: the model ceiling is chosen from discovered models and a refusal says the ceiling is the reason.

The platform owner may only set a ceiling inside the company's current discovery (no discovery: PLATFORM_INVALID; a model
outside it: MODEL_NOT_DISCOVERED; the empty list still denies everything). A company administrator publishing outside the
ceiling gets GATEWAY_OUTSIDE_CEILING, and the administrator's refresh can read the ceiling to list only publishable models.
These tests apply 0049 on top of the reviewed profile explicitly, so they hold both before and after 0049 joins the profile.
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
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import MVP_ADDITIONS
from mvp_support import CEILING_MIGRATION, WITH_CEILING, mvp_database
from platform_support import call, refusal, sign_in
from test_postgres_platform_catalog import SchemaWorld

SET = 'SELECT * FROM forge.platform_company_model_access_set(%s,%s,%s)'
HELPERS = {'forge.gateway_discovered_models(uuid)': ('forge_gateway_authority', {'forge_platform_authority': True, 'forge_gateway_service': False,
                                                                                  'forge_platform_service': False, 'public': False}),
           'forge.gateway_catalog_ceiling(text,uuid)': ('forge_gateway_authority', {'forge_gateway_service': True, 'forge_platform_authority': False,
                                                                                    'forge_platform_service': False, 'public': False}),
           'forge.platform_company_model_access_set(text,uuid,text[])': ('forge_platform_authority', {'forge_platform_service': True,
                                                                                                      'forge_gateway_service': False, 'public': False})}


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
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
            self.build(db)
            before, audited = self.ceiling(), self.audit()
            self.assertEqual(refusal(self, lambda: self.set_ceiling(['gpt-a'])), 'PLATFORM_INVALID', 'nothing was discovered yet')
            self.assertEqual((self.ceiling(), self.audit()), (before, audited))

    def test_a_model_outside_the_discovery_is_refused_with_its_own_message_and_the_ceiling_stays(self):
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
            self.build(db)
            self.assertEqual(self.set_ceiling([]), [([],)], 'denying everything needs no discovery')
            self.save(['gpt-a', 'gpt-b', 'gpt-c'])
            self.assertEqual(self.set_ceiling(['gpt-c', 'gpt-a']), [(['gpt-c', 'gpt-a'],)])
            self.assertEqual(self.ceiling(), ['gpt-c', 'gpt-a'])
            self.assertEqual(self.set_ceiling(['gpt-a', 'gpt-b', 'gpt-c']), [(['gpt-a', 'gpt-b', 'gpt-c'],)])
            self.assertEqual(self.audit().count('company.model_access_set'), 3)

    def test_a_discovery_of_an_older_profile_revision_no_longer_counts(self):
        with mvp_database(migrations=WITH_CEILING) as db:
            self.build(db)
            self.save(['gpt-a'])
            db.admin.execute('UPDATE forge.organization_gateway_profiles SET revision=2 WHERE organization_id=%s', (self.org,))
            self.assertEqual(refusal(self, lambda: self.set_ceiling(['gpt-a'])), 'PLATFORM_INVALID', 'the discovery belongs to revision 1')
            self.save(['gpt-a'], revision=2)
            self.assertEqual(self.set_ceiling(['gpt-a']), [(['gpt-a'],)])

    def test_only_a_fresh_verified_owner_can_set_a_ceiling(self):
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
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
        with mvp_database(migrations=WITH_CEILING) as db:
            self.build(db)
            service = GatewayKeys(PostgresGatewayKeyStore(db.pool('forge_platform_service')), cipher=None)
            with self.assertRaises(DiscoveryRequired):
                service.set_ceiling(self.token, self.org, ['gpt-a'])
            self.save(['gpt-a'])
            with self.assertRaises(ModelNotDiscovered):
                service.set_ceiling(self.token, self.org, ['gpt-a', 'Deepseek'])
            self.assertEqual(service.set_ceiling(self.token, self.org, ['gpt-a']), ['gpt-a'])
            self.assertEqual(self.audit().count('company.model_access_set'), 1, 'refused attempts are not audited')


class WithoutTheMigrationTests(CeilingWorld):
    def test_a_schema_without_0049_keeps_listing_every_discovered_model(self):
        """The refresh helper is optional: until a database carries 0049, the administrator's list is not narrowed."""
        before = (*MIGRATIONS, *(name for name in MVP_ADDITIONS if name != CEILING_MIGRATION))
        with mvp_database(migrations=before) as db:
            self.build(db)
            self.assertIsNone(PostgresPoolCatalogStore(db.pool('forge_gateway_service')).ceiling(self.admin_session(), self.org))


class OutsideCeilingErrorTests(unittest.TestCase):
    def test_the_error_carries_the_finite_code_the_api_returns(self):
        self.assertEqual(GatewayOutsideCeiling().code, 'MODEL_NOT_ALLOWED')


if __name__ == '__main__':
    unittest.main()
