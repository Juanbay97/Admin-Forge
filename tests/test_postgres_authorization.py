"""Mandatory owned PostgreSQL membership authorization proof."""
from pathlib import Path
import sys
import unittest
import psycopg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from forge.authorization import permits
from forge.authorization_store import PostgresAuthorizationReader,AuthorizationStoreUnavailable
from forge.foundation import AuthenticatedIdentity
from postgres_support import DatabaseFixture,ORG_A,ORG_B,MEMBER_A,MEMBER_B,ALICE,connect

class PostgresAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.db=DatabaseFixture()
    def setUp(self):
        self.db.reset();self.pool=self.db.pool();self.addCleanup(self.pool.close,timeout=5)
        self.reader=PostgresAuthorizationReader(self.pool)
    def test_active_owned_membership_is_read_fresh_without_roles(self):
        value=self.reader.read(AuthenticatedIdentity('test','issuer','alice'),str(ORG_A))
        self.assertIsNotNone(value)
        self.assertEqual(value.revision,1)
        self.assertEqual(value.roles,frozenset())
        self.assertFalse(permits(value,'members.invite'))

    def test_authorization_metadata_is_required_for_readiness(self):
        from forge.postgres import (PostgresReadinessProbe,_AUTHORIZATION_SCHEMA,
            _ROLE_VALUES_CHECK,_ROLE_SCOPE_CHECK)
        with self.pool.connection() as conn:
            shapes=conn.execute("SELECT conname,pg_get_constraintdef(oid),"
                "CASE WHEN contype='c' THEN pg_get_expr(conbin,conrelid) END "
                "FROM pg_constraint WHERE conrelid IN ('forge.memberships'::regclass,"
                "'forge.membership_roles'::regclass) ORDER BY conname").fetchall()
            policies=conn.execute("SELECT pg_get_expr(polqual,polrelid) FROM pg_policy "
                "WHERE polrelid='forge.membership_roles'::regclass").fetchall()
            defaults=conn.execute("SELECT pg_get_expr(adbin,adrelid) FROM pg_attrdef "
                "WHERE adrelid='forge.memberships'::regclass").fetchall()
            self.assertTrue(conn.execute(_AUTHORIZATION_SCHEMA,
                (_ROLE_VALUES_CHECK,_ROLE_SCOPE_CHECK)).fetchone()[0],
                str((shapes,policies,defaults)))
        self.assertTrue(PostgresReadinessProbe(self.pool).check())

    def assign(self, member=None, role="organization_admin", org=None):
        with connect() as conn:
            conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,%s)",
                (org or ORG_A,member or MEMBER_A,role))

    def test_distinct_fresh_populated_and_real_failed_migration_evidence(self):
        fresh,populated,failed=self.db.authorization_migration_evidence
        self.assertEqual(fresh,(True,True,0,5,None,True))
        self.assertEqual(populated,(True,True,3,5,None,True))
        self.assertEqual(failed,(False,False,3,4,("22012",True),True))
        self.assertEqual(len(self.db.migration_evidence),4)
        self.assertTrue(all(e[3]==4 for e in self.db.migration_evidence))

    def test_fresh_roles_revision_and_lifecycle_not_cached(self):
        self.assign()
        identity=AuthenticatedIdentity("test","issuer","alice")
        first=self.reader.read(identity,str(ORG_A))
        self.assertTrue(permits(first,"members.invite"))
        with connect() as conn,conn.transaction():
            conn.execute("DELETE FROM forge.membership_roles")
            conn.execute("UPDATE forge.memberships SET revision=2 WHERE id=%s",(MEMBER_A,))
        latest=self.reader.read(identity,str(ORG_A))
        self.assertEqual(latest.revision,2)
        self.assertFalse(permits(latest,"members.invite"))
        self.assertEqual(first.roles,frozenset({"organization_admin"}))
        for status in ("suspended","archived"):
            with connect() as conn:
                conn.execute("UPDATE forge.memberships SET status=%s WHERE id=%s",(status,MEMBER_A))
            self.assertIsNone(self.reader.read(identity,str(ORG_A)))
        with connect() as conn:
            conn.execute("UPDATE forge.memberships SET status='active' WHERE id=%s",(MEMBER_A,))
            conn.execute("UPDATE forge.organizations SET active=false WHERE id=%s",(ORG_A,))
        self.assertIsNone(self.reader.read(identity,str(ORG_A)))

    def test_roles_are_self_only_and_cross_org_membership_is_not_authority(self):
        from uuid import UUID
        self.assign();self.assign(UUID(int=23),"member")
        self.assign(MEMBER_B,org=ORG_B)
        own=self.reader.read(AuthenticatedIdentity("test","issuer","carol"),str(ORG_A))
        self.assertEqual(own.roles,frozenset({"member"}))
        self.assertFalse(permits(own,"members.update"))
        for subject,org in (("alice",ORG_B),("bob",ORG_A),("missing",ORG_A)):
            self.assertIsNone(self.reader.read(AuthenticatedIdentity("test","issuer",subject),str(org)))

    def test_entra_requires_canonical_persisted_binding_and_resource_tenant(self):
        from uuid import UUID
        from test_entra import TENANT,OID,issuer
        identity=AuthenticatedIdentity("entra",issuer(),OID)
        with connect() as conn:
            conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s "
                "WHERE id=%s",(identity.issuer,identity.subject,ALICE))
        self.assign()
        self.assertIsNone(self.reader.read(identity,str(ORG_A)))
        with connect() as conn:
            conn.execute("UPDATE forge.identities SET entra_tenant_id=%s,entra_object_id=%s "
                "WHERE id=%s",(UUID(TENANT),UUID(OID),ALICE))
        self.assertTrue(permits(self.reader.read(identity,str(ORG_A)),"members.suspend"))
        for wrong in (AuthenticatedIdentity("entra",issuer(str(UUID(int=999))),OID),
                AuthenticatedIdentity("entra",issuer(),"guest-sub"),
                AuthenticatedIdentity("test","issuer",OID)):
            self.assertIsNone(self.reader.read(wrong,str(ORG_A)))

    def test_invalid_input_rejects_before_borrow_and_timeout_range_is_safe(self):
        from unittest.mock import patch
        with patch.object(self.pool,"connection",side_effect=AssertionError("No borrow")) as borrow:
            for identity,org in ((None,str(ORG_A)),(AuthenticatedIdentity("test","issuer",""),str(ORG_A)),
                    (AuthenticatedIdentity("test","issuer","alice"),"' OR true --"),
                    (AuthenticatedIdentity("test","issuer","alice"),None)):
                self.assertIsNone(self.reader.read(identity,org))
            borrow.assert_not_called()
        for value in (True,0,-1,31,float("inf"),float("nan"),10**400,"1",None):
            with self.subTest(type=type(value)),self.assertRaises(ValueError):
                PostgresAuthorizationReader(self.pool,acquisition_timeout=value)

    def test_nonruntime_and_closed_pool_fail_with_redacted_operational_error(self):
        pool=self.db.pool(user="postgres")
        try:
            with self.assertRaises(AuthorizationStoreUnavailable) as raised:
                PostgresAuthorizationReader(pool).read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
            self.assertEqual(str(raised.exception),"Authorization storage unavailable.")
        finally:pool.close(timeout=5)
        self.pool.close(timeout=5)
        with self.assertRaises(AuthorizationStoreUnavailable) as raised:
            self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
        self.assertEqual(str(raised.exception),"Authorization storage unavailable.")
        self.assertTrue(self.pool.closed)

    def test_same_backend_context_limits_and_search_path_restore(self):
        with self.pool.connection() as conn:
            before=(conn.info.backend_pid,conn.execute("SHOW statement_timeout").fetchone(),
                conn.execute("SHOW lock_timeout").fetchone(),conn.execute("SHOW search_path").fetchone())
        self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
        with self.pool.connection() as conn:
            after=(conn.info.backend_pid,conn.execute("SHOW statement_timeout").fetchone(),
                conn.execute("SHOW lock_timeout").fetchone(),conn.execute("SHOW search_path").fetchone())
            self.assertEqual(before,after)
            self.assertIs(conn.info.transaction_status,psycopg.pq.TransactionStatus.IDLE)
            for key in ("organization","provider","issuer","subject","binding_identity"):
                self.assertIn(conn.execute("SELECT current_setting(%s,true)",("forge."+key,)).fetchone()[0],(None,""))

    def test_dirty_context_and_nonidle_connections_do_not_leak_or_nest(self):
        from unittest.mock import patch
        from contextlib import nullcontext
        with self.pool.connection() as conn:
            conn.execute("SELECT set_config('forge.organization',%s,false)",(str(ORG_B),))
            try:
                with patch.object(self.pool,"connection",return_value=nullcontext(conn)):
                    with self.assertRaises(AuthorizationStoreUnavailable):
                        self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
                self.assertEqual(conn.execute("SELECT current_setting('forge.organization')").fetchone()[0],str(ORG_B))
            finally:conn.execute("SELECT set_config('forge.organization','',false)")
            with conn.transaction():
                with patch.object(self.pool,"connection",return_value=nullcontext(conn)):
                    with self.assertRaises(AuthorizationStoreUnavailable):
                        self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
                self.assertIs(conn.info.transaction_status,psycopg.pq.TransactionStatus.INTRANS)
            conn.autocommit=False
            try:
                with patch.object(self.pool,"connection",return_value=nullcontext(conn)):
                    with self.assertRaises(AuthorizationStoreUnavailable):
                        self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
                self.assertIs(conn.info.transaction_status,psycopg.pq.TransactionStatus.IDLE)
            finally:conn.autocommit=True

    def test_one_parameterized_business_snapshot_and_cleanup_after_failure(self):
        queries=[];fail=[False]
        class Cursor(psycopg.Cursor):
            def execute(self,query,params=None,**kwargs):
                if "FROM forge.identities AS i" in str(query):
                    queries.append((str(query),params))
                    if fail[0]:raise RuntimeError("PRIVATE_SQL_DSN_IDENTITY_TOKEN")
                return super().execute(query,params,**kwargs)
        class Connection(psycopg.Connection):
            def cursor(self,*args,**kwargs):
                return Cursor(self,row_factory=kwargs.get("row_factory"))
        pool=self.db.pool(connection_class=Connection);self.addCleanup(pool.close,timeout=5)
        reader=PostgresAuthorizationReader(pool)
        identity=AuthenticatedIdentity("test","issuer","alice")
        self.assertIsNotNone(reader.read(identity,str(ORG_A)))
        self.assertEqual(len(queries),1);self.assertEqual(queries[0][1],("test","issuer","alice",ORG_A))
        self.assertIn("LEFT JOIN forge.membership_roles",queries[0][0])
        fail[0]=True
        with self.assertRaises(AuthorizationStoreUnavailable) as raised:reader.read(identity,str(ORG_A))
        self.assertEqual(str(raised.exception),"Authorization storage unavailable.")
        self.assertTrue(raised.exception.__suppress_context__)
        with pool.connection() as conn:
            self.assertIs(conn.info.transaction_status,psycopg.pq.TransactionStatus.IDLE)
            self.assertIn(conn.execute("SELECT current_setting('forge.subject',true)").fetchone()[0],(None,""))

    def test_pool_acquisition_is_bounded_with_no_hidden_retry(self):
        from threading import Thread
        from time import monotonic
        reader=PostgresAuthorizationReader(self.pool,acquisition_timeout=0.1)
        errors=[]
        def attempt():
            try:reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
            except AuthorizationStoreUnavailable as error:errors.append(str(error))
        with self.pool.connection():
            start=monotonic();thread=Thread(target=attempt);thread.start();thread.join(timeout=3)
            self.assertFalse(thread.is_alive());self.assertLess(monotonic()-start,3)
        self.assertEqual(errors,["Authorization storage unavailable."])

    def test_constraints_preserve_roles_revision_and_composite_scope(self):
        for role in ("platform_operator","unknown","organization_admin ",""):
            with connect() as conn,self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,%s)",(ORG_A,MEMBER_A,role))
        self.assign()
        with connect() as conn:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,'organization_admin')",(ORG_A,MEMBER_A))
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,'member')",(ORG_B,MEMBER_A))
            for revision in (0,-1):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute("UPDATE forge.memberships SET revision=%s WHERE id=%s",(revision,MEMBER_A))
            self.assertEqual(conn.execute("SELECT revision FROM forge.memberships WHERE id=%s",(MEMBER_A,)).fetchone()[0],1)

    def test_runtime_and_binder_cannot_mutate_or_read_other_storage(self):
        self.assign()
        for factory in (self.db.runtime,self.db.binder):
            with factory() as conn:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,'member')",(ORG_A,MEMBER_A))
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute("UPDATE forge.memberships SET revision=2")
        with self.db.binder() as conn:
            for query in ("SELECT * FROM forge.membership_roles","SELECT revision FROM forge.memberships"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):conn.execute(query)

    def test_revision_and_roles_are_consistent_under_concurrent_commits(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.assign();barrier=Barrier(2)
        def writer():
            barrier.wait(timeout=5)
            with connect() as conn:
                for n in range(20):
                    revision=2 if n%2==0 else 1
                    role="member" if revision==2 else "organization_admin"
                    with conn.transaction():
                        conn.execute("DELETE FROM forge.membership_roles")
                        conn.execute("UPDATE forge.memberships SET revision=%s WHERE id=%s",(revision,MEMBER_A))
                        conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,%s)",(ORG_A,MEMBER_A,role))
        def reader():
            barrier.wait(timeout=5)
            observations=[]
            for _ in range(30):
                value=self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
                observations.append((value.revision,value.roles))
            return observations
        with ThreadPoolExecutor(max_workers=2) as executor:
            write=executor.submit(writer);read=executor.submit(reader)
            observations=read.result(timeout=15);write.result(timeout=15)
        allowed={(1,frozenset({"organization_admin"})),(2,frozenset({"member"}))}
        self.assertTrue(observations);self.assertTrue(all(x in allowed for x in observations))

    def test_actual_relation_lock_timeout_is_bounded_and_pool_recovers(self):
        from time import monotonic
        with connect() as admin,admin.transaction():
            admin.execute("LOCK TABLE forge.membership_roles IN ACCESS EXCLUSIVE MODE")
            start=monotonic()
            with self.assertRaises(AuthorizationStoreUnavailable) as raised:
                self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A))
            self.assertEqual(str(raised.exception),"Authorization storage unavailable.")
            self.assertLess(monotonic()-start,3)
        self.assertIsNotNone(self.reader.read(AuthenticatedIdentity("test","issuer","alice"),str(ORG_A)))
