"""Actual owned PostgreSQL admin status; no provider requests or real keys."""
from contextlib import contextmanager
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
import test_postgres_gateway_catalog as upstream
PASSWORD=upstream.PASSWORD
from postgres_support import ORG_A, ORG_B, MEMBER_A, owned_gateway_catalog_admin_extension
from forge.invitations import capability_digest

class AdminStatusTests(unittest.TestCase):
    setUpClass=classmethod(upstream.PostgresGatewayCatalogTests.setUpClass.__func__)
    setUp=upstream.PostgresGatewayCatalogTests.setUp
    catalog=upstream.PostgresGatewayCatalogTests.catalog
    prepared=upstream.PostgresGatewayCatalogTests.prepared
    @contextmanager
    def fixture(self):
        with upstream.PostgresGatewayCatalogTests.fixture(self) as values:
            with owned_gateway_catalog_admin_extension(values[0]):
                from forge.gateway_catalog_admin_readiness import GatewayCatalogAdminReadiness
                admin,pools,readers,sessions,token,store,service,_,key=values
                ready=GatewayCatalogAdminReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service'])
                yield admin,pools,readers,sessions,token,store,service,ready,key
    def test_authoritative_unpublished_revision(self):
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            with store.connection.cursor() as cursor:
                cursor.execute('SELECT * FROM forge.gateway_catalog_admin_status(%s,%s)',(capability_digest(token),ORG_A))
                self.assertEqual(cursor.fetchone(),(0,None,'UNPUBLISHED'))

    def test_reviewed_profile_drift_and_direct_role_isolation(self):
        from forge.account_readiness import catalog_fingerprint
        from forge.gateway_catalog_admin_readiness import _EXPECTED_SHA256
        from forge.gateway_inference_readiness import GatewayInferenceReadiness
        from psycopg import errors
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            with store.connection.cursor() as cursor:actual=catalog_fingerprint(cursor)
            print('Reviewed PG17.11 administrator status profile SHA256:',actual)
            self.assertEqual(actual,_EXPECTED_SHA256)
            self.assertTrue(ready.check())
            self.assertFalse(GatewayInferenceReadiness(pools['forge_account_service'],readers,pools['forge_gateway_service']).check())
            for change,restore in [
              ('GRANT EXECUTE ON FUNCTION forge.gateway_catalog_admin_status(text,uuid) TO PUBLIC','REVOKE EXECUTE ON FUNCTION forge.gateway_catalog_admin_status(text,uuid) FROM PUBLIC'),
              ('ALTER FUNCTION forge.gateway_catalog_admin_status(text,uuid) SECURITY INVOKER','ALTER FUNCTION forge.gateway_catalog_admin_status(text,uuid) SECURITY DEFINER'),
              ('ALTER TABLE forge.organization_gateways NO FORCE ROW LEVEL SECURITY','ALTER TABLE forge.organization_gateways FORCE ROW LEVEL SECURITY'),
              ('ALTER ROLE forge_gateway_authority LOGIN','ALTER ROLE forge_gateway_authority NOLOGIN')]:
                try:admin.execute(change);self.assertFalse(ready.check())
                finally:admin.execute(restore)
                self.assertTrue(ready.check())
            with pools['forge_account_service'].connection() as connection:
                with self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute('SELECT * FROM forge.gateway_catalog_admin_status(%s,%s)',(capability_digest(token),ORG_A))
                connection.rollback()
            with pools['forge_gateway_service'].connection() as connection:
                with self.assertRaises(errors.InsufficientPrivilege):connection.execute('SELECT * FROM forge.organization_gateways')
                connection.rollback()

    def test_genuine_http_none_current_rotation_status_and_authority(self):
        from forge.account_api import create_account_app
        from forge.authorization_store import PostgresAuthorizationReader
        from forge.postgres import PostgresBootstrapReader
        with self.fixture() as (admin,pools,readers,sessions,token,store,service,ready,key):
            catalog=self.catalog(pools,key)
            app=create_account_app(sessions=sessions,readiness=ready,gateway_configuration=service,
                gateway_catalog=catalog,authorization_reader=PostgresAuthorizationReader(readers),
                bootstrap_reader=PostgresBootstrapReader(readers))
            url='/forge/v1/orgs/'+str(ORG_A);headers={'Authorization':'Bearer '+token}
            with TestClient(app,raise_server_exceptions=False) as client:
                status=client.get(url+'/gateway/catalogue/status',headers=headers)
                self.assertEqual(status.status_code,200);self.assertEqual(status.json(),{'catalogue_revision':0,'default_model':None,'publication_state':'UNPUBLISHED'})
                mapping=self.prepared(service,catalog,token)
                catalog.publish(token,ORG_A,uuid4(),0,1,mapping,'assistant')
                self.assertEqual(client.get(url+'/gateway/catalogue/status',headers=headers).json(),{'catalogue_revision':1,'default_model':'assistant','publication_state':'CURRENT'})
                service.save(token,ORG_A,1,'rotated-fixture-only')
                self.assertEqual(client.get(url+'/models',headers=headers).status_code,404)
                result=client.get(url+'/gateway/catalogue/status',headers=headers)
                self.assertEqual(result.json(),{'catalogue_revision':1,'default_model':'assistant','publication_state':'STALE_GATEWAY'})
                for secret in ('rotated-fixture','upstream/private','binding_id','encrypted_key','route'):self.assertNotIn(secret,result.text)
                member=sessions.login('member@example.com',PASSWORD).capability
                from forge.gateway_configuration import GatewayDenied
                with self.assertRaises(GatewayDenied):catalog.admin_status(member,ORG_A)
                with self.assertRaises(GatewayDenied):catalog.admin_status(token,ORG_B)
                admin.execute("UPDATE forge.memberships SET status='suspended' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
                try:
                    with self.assertRaises(GatewayDenied):catalog.admin_status(token,ORG_A)
                finally:admin.execute("UPDATE forge.memberships SET status='active' WHERE organization_id=%s AND id=%s",(ORG_A,MEMBER_A))
                self.assertEqual(client.get(url+'/gateway/catalogue/status',headers={'Authorization':'Bearer '+member}).status_code,404)
                self.assertEqual(client.get('/forge/v1/orgs/'+str(ORG_B)+'/gateway/catalogue/status',headers=headers).status_code,404)
                admin.execute("DELETE FROM forge.membership_roles WHERE organization_id=%s AND membership_id=%s AND role='organization_admin'",(ORG_A,MEMBER_A))
                self.assertEqual(client.get(url+'/gateway/catalogue/status',headers=headers).status_code,404)
                with self.assertRaises(GatewayDenied):catalog.admin_status(token,ORG_A)
                admin.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
                sessions.logout(token)
                with self.assertRaises(GatewayDenied):catalog.admin_status(token,ORG_A)
                self.assertEqual(client.get(url+'/gateway/catalogue/status',headers=headers).status_code,401)

    def test_status_migration_rollback_preserves_old_profile(self):
        with upstream.PostgresGatewayCatalogTests.fixture(self) as values:
            admin=values[0]
            with owned_gateway_catalog_admin_extension(admin,fail_migration=True):
                self.assertIsNone(admin.execute("SELECT to_regprocedure('forge.gateway_catalog_admin_status(text,uuid)')").fetchone()[0])
                self.assertEqual(admin.execute("SELECT has_schema_privilege('forge_gateway_authority','forge','CREATE')").fetchone(),(False,))
            self.assertTrue(values[7].check())
