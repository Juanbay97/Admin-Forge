"""Owned real PostgreSQL initial designation atomicity and isolation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import unittest
from uuid import UUID,uuid4
from forge.administration import *
from forge.administration_store import PostgresInitialAdministratorStore
from postgres_support import DatabaseFixture,connect,ORG_A,MEMBER_A,ALICE
import test_administration as crypto_tests
from test_entra import TENANT,OID,issuer

class PostgresAdministrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=DatabaseFixture()
        cls.crypto=crypto_tests.AdministrationTests();cls.crypto.setUpClass()
    def setUp(self):
        self.db.reset()
        self.crypto.setUp()
        with connect() as conn:
            conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                (issuer(),str(UUID(int=800)),UUID(TENANT),UUID(int=800),ALICE))
        self.pool=self.db.pool(user='forge_designator');self.addCleanup(self.pool.close,timeout=5)
        self.store=PostgresInitialAdministratorStore(self.pool)
        self.initial_service=InitialAdministratorService(self.crypto.validator,self.store,self.crypto.configuration)
        self.request=DesignationRequest(ORG_A,MEMBER_A,uuid4(),1)
    def test_real_atomic_designation_has_role_revision_and_event(self):
        try:self.initial_service.designate(self.crypto.token(),self.request)
        except (DesignationDenied,DesignationUnavailable):pass
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT role FROM forge.membership_roles "
                "WHERE organization_id=%s AND membership_id=%s",(ORG_A,MEMBER_A)).fetchall(),
                [("organization_admin",)])
            self.assertEqual(conn.execute("SELECT revision FROM forge.memberships WHERE id=%s",
                (MEMBER_A,)).fetchone()[0],2)

    def test_new_schema_metadata_and_policy_shapes(self):
        import json
        from forge.postgres import PostgresReadinessProbe
        with connect() as conn:
            conn.execute("SET search_path=pg_catalog")
            shapes={
                "columns":conn.execute("SELECT c.relname,a.attname,a.atttypid::regtype::text,a.attnotnull,"
                    "coalesce(pg_get_expr(d.adbin,d.adrelid),'') FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid "
                    "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
                    "WHERE n.nspname='forge' AND c.relname IN ('initial_admin_designations','initial_admin_outbox') "
                    "AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum").fetchall(),
                "constraints":conn.execute("SELECT c.relname,k.conname,pg_get_constraintdef(k.oid),k.convalidated "
                    "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND c.relname IN "
                    "('initial_admin_designations','initial_admin_outbox') ORDER BY c.relname,k.conname").fetchall(),
                "policies":conn.execute("SELECT c.relname,p.polname,p.polcmd,p.polpermissive,"
                    "coalesce(pg_get_expr(p.polqual,p.polrelid),''),"
                    "coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'') "
                    "FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND p.polname LIKE 'designation_%' "
                    "ORDER BY c.relname,p.polname").fetchall()}
        Path('.local/runtime-test/f07b2a-catalog-shapes.json').write_text(json.dumps(shapes),encoding='utf-8')
        pool=self.db.pool();self.addCleanup(pool.close,timeout=5)
        self.assertTrue(PostgresReadinessProbe(pool).check())

    def bind(self, identity, oid, tenant=TENANT):
        with connect() as conn:
            conn.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
                "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
                (issuer(tenant),str(oid),UUID(tenant),oid,identity))

    def service(self,pool=None,configuration=None):
        return InitialAdministratorService(self.crypto.validator,
            PostgresInitialAdministratorStore(pool or self.pool),
            configuration or self.crypto.configuration)

    def state(self):
        with connect() as conn:
            return (conn.execute("SELECT organization_id,membership_id,role FROM forge.membership_roles ORDER BY 1,2").fetchall(),
                    conn.execute("SELECT * FROM forge.initial_admin_designations ORDER BY 1").fetchall(),
                    conn.execute("SELECT event_id,organization_id,actor_id,request_id,resource_id,previous_revision,revision,"
                        "metadata,actor_type,source,event_type,schema_version,resource_type,outcome,occurred_at,received_at "
                        "FROM forge.initial_admin_outbox ORDER BY 1").fetchall(),
                    conn.execute("SELECT revision FROM forge.memberships WHERE id=%s",(MEMBER_A,)).fetchone()[0])

    def context(self,conn,request=None,identity=ALICE,actor=None):
        from test_administration import ACTOR
        req=request or self.request
        for key,value in (("organization",req.organization_id),("member",req.membership_id),
                ("identity",identity),("actor",actor or ACTOR),("request",req.operation_id)):
            conn.execute("SELECT set_config(%s,%s,true)",("forge.designation_"+key,str(value)))

    def test_migration_fresh_populated_and_actual_failure_are_distinct(self):
        self.assertEqual(self.db.designation_migration_evidence,
            ((True,True,0,7,None,True),(True,True,3,7,None,True),(False,False,3,5,("22012",True),True)))
        self.assertEqual(len(self.db.migration_evidence),4)
        self.assertEqual(len(self.db.authorization_migration_evidence),3)

    def test_event_is_fixed_server_derived_and_original_result_is_immutable(self):
        from dataclasses import FrozenInstanceError
        from test_administration import ACTOR
        result=self.service().designate(self.crypto.token(email="PRIVATE_EMAIL_MARKER"),self.request)
        roles,records,events,revision=self.state()
        self.assertEqual(len(records),1);self.assertEqual(len(events),1)
        event=events[0]
        self.assertEqual(event[:7],(result.event_id,ORG_A,ACTOR,self.request.operation_id,MEMBER_A,1,2))
        self.assertEqual(event[7],{"role":"organization_admin","previous_revision":1,"revision":2})
        self.assertEqual(event[8:14],("deployment_operator","server","membership.initial_admin_designated",1,"membership","succeeded"))
        self.assertEqual(event[14],event[15])
        self.assertNotIn("PRIVATE",str(event))
        self.assertEqual(result.audit_publication,"pending")
        with self.assertRaises(FrozenInstanceError):result.revision=3

    def test_response_loss_replay_returns_same_result_without_second_write(self):
        first=self.service().designate(self.crypto.token(),self.request)
        before=self.state()
        second=self.service().designate(self.crypto.token(sub="other-sub"),self.request)
        self.assertEqual(first,second);self.assertEqual(before,self.state())

    def test_replay_after_status_or_role_removal_does_not_regrant(self):
        first=self.service().designate(self.crypto.token(),self.request)
        with connect() as conn:
            conn.execute("DELETE FROM forge.membership_roles")
            conn.execute("UPDATE forge.memberships SET status='archived',revision=3 WHERE id=%s",(MEMBER_A,))
        before=self.state()
        self.assertEqual(self.service().designate(self.crypto.token(),self.request),first)
        self.assertEqual(self.state(),before)

    def test_permanent_marker_prevents_later_initial_designation(self):
        from dataclasses import replace
        from postgres_support import CAROL
        self.service().designate(self.crypto.token(),self.request)
        with connect() as conn:conn.execute("DELETE FROM forge.membership_roles")
        self.bind(CAROL,UUID(int=801))
        before=self.state()
        with self.assertRaises(DesignationConflict):
            self.service().designate(self.crypto.token(),replace(self.request,membership_id=UUID(int=23),operation_id=uuid4()))
        self.assertEqual(self.state(),before)

    def test_changed_payload_actor_and_revision_replays_conflict(self):
        from dataclasses import replace
        from postgres_support import CAROL
        self.bind(CAROL,UUID(int=801))
        self.service().designate(self.crypto.token(),self.request);before=self.state()
        requests=(replace(self.request,expected_revision=2),replace(self.request,membership_id=UUID(int=23)),
                  replace(self.request,operation_id=uuid4()))
        for request in requests:
            with self.subTest(request=request),self.assertRaises(DesignationConflict):
                self.service().designate(self.crypto.token(),request)
        operator=replace(self.crypto.operator,actor_id=UUID(int=701))
        cfg=DesignationConfiguration((operator,),self.crypto.configuration.organization_tenants)
        with self.assertRaises(DesignationConflict):self.service(configuration=cfg).designate(self.crypto.token(),self.request)
        self.assertEqual(self.state(),before)

    def test_replay_requires_current_operator_token_and_target_tenant_mapping(self):
        self.service().designate(self.crypto.token(),self.request);before=self.state()
        from test_entra import OTHER_TENANT
        for token,cfg in ((self.crypto.token(exp=crypto_tests.NOW-90,nbf=crypto_tests.NOW-200,iat=crypto_tests.NOW-200),None),
                (self.crypto.token(),DesignationConfiguration((),{})),
                (self.crypto.token(),DesignationConfiguration((self.crypto.operator,),{ORG_A:{UUID(OTHER_TENANT)}}))):
            with self.subTest(configured=cfg is not None),self.assertRaises(DesignationDenied):
                self.service(configuration=cfg).designate(token,self.request)
        self.assertEqual(self.state(),before)

    def test_stale_revision_and_any_preexisting_admin_roll_back_claim(self):
        from dataclasses import replace
        with self.assertRaises(DesignationConflict):
            self.service().designate(self.crypto.token(),replace(self.request,expected_revision=2))
        self.assertEqual(self.state(),([],[],[],1))
        # Even an existing admin on a different suspended membership blocks this initial-only operation.
        with connect() as conn:
            conn.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",(ORG_A,UUID(int=24)))
        before=self.state()
        with self.assertRaises(DesignationConflict):self.service().designate(self.crypto.token(),self.request)
        self.assertEqual(self.state(),before)

    def test_missing_unbound_generic_nonactive_crossorg_and_wrongtenant_targets_deny(self):
        from dataclasses import replace
        from postgres_support import ORG_B
        from test_entra import OTHER_TENANT
        for target in (UUID(int=999),UUID(int=23),UUID(int=24),UUID(int=25),UUID(int=22)):
            with self.subTest(member=target),self.assertRaises(DesignationDenied):
                self.service().designate(self.crypto.token(),replace(self.request,membership_id=target))
        cfg=DesignationConfiguration((self.crypto.operator,),{ORG_A:{UUID(OTHER_TENANT)}})
        with self.assertRaises(DesignationDenied):self.service(configuration=cfg).designate(self.crypto.token(),self.request)
        self.assertEqual(self.state(),([],[],[],1))

    def test_inactive_organization_remains_inactive_and_runtime_access_denied(self):
        from forge.authorization_store import PostgresAuthorizationReader
        from forge.foundation import AuthenticatedIdentity
        with connect() as conn:conn.execute("UPDATE forge.organizations SET active=false WHERE id=%s",(ORG_A,))
        result=self.service().designate(self.crypto.token(),self.request)
        self.assertEqual(result.revision,2)
        with connect() as conn:
            self.assertFalse(conn.execute("SELECT active FROM forge.organizations WHERE id=%s",(ORG_A,)).fetchone()[0])
        pool=self.db.pool();self.addCleanup(pool.close,timeout=5)
        self.assertIsNone(PostgresAuthorizationReader(pool).read(
            AuthenticatedIdentity("entra",issuer(),str(UUID(int=800))),str(ORG_A)))

    def test_actual_outbox_sql_failure_after_grant_and_revision_rolls_back_everything(self):
        import psycopg
        observed=[]
        class Cursor(psycopg.Cursor):
            def execute(inner,query,params=None,**kwargs):
                if str(query).startswith("INSERT INTO forge.initial_admin_outbox"):
                    super(Cursor,inner).execute("SELECT (SELECT count(*) FROM forge.membership_roles),"
                        "(SELECT revision FROM forge.memberships LIMIT 1),"
                        "(SELECT count(*) FROM forge.initial_admin_designations)")
                    observed.append(inner.fetchone())
                    return super(Cursor,inner).execute("SELECT 1/0")
                return super(Cursor,inner).execute(query,params,**kwargs)
        class Connection(psycopg.Connection):
            def cursor(inner,*args,**kwargs):return Cursor(inner,row_factory=kwargs.get("row_factory"))
        pool=self.db.pool(user="forge_designator",connection_class=Connection)
        self.addCleanup(pool.close,timeout=5)
        with self.assertRaises(DesignationUnavailable):self.service(pool=pool).designate(self.crypto.token(),self.request)
        self.assertEqual(observed,[(1,2,1)])
        self.assertEqual(self.state(),([],[],[],1))
        self.assertEqual(self.service().designate(self.crypto.token(),self.request).revision,2)

    def test_marker_without_event_cannot_commit(self):
        import psycopg
        from test_administration import ACTOR
        with self.pool.connection() as conn:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation),conn.transaction():
                self.context(conn)
                conn.execute("INSERT INTO forge.initial_admin_designations VALUES(%s,%s,%s,%s,%s,1,2,%s)",
                    (ORG_A,MEMBER_A,self.request.operation_id,ACTOR,UUID(TENANT),uuid4()))
        self.assertEqual(self.state(),([],[],[],1))

    def test_global_operation_reuse_in_another_organization_conflicts(self):
        from dataclasses import replace
        from postgres_support import BOB,ORG_B,MEMBER_B
        self.bind(BOB,UUID(int=802))
        cfg=DesignationConfiguration((self.crypto.operator,),{ORG_A:{UUID(TENANT)},ORG_B:{UUID(TENANT)}})
        self.service(configuration=cfg).designate(self.crypto.token(),self.request)
        before=self.state()
        with self.assertRaises(DesignationConflict):
            self.service(configuration=cfg).designate(self.crypto.token(),
                replace(self.request,organization_id=ORG_B,membership_id=MEMBER_B))
        self.assertEqual(self.state(),before)

    def test_designation_restores_context_timeouts_search_path_on_same_backend(self):
        keys=("organization","member","identity","actor","request")
        with self.pool.connection() as conn:
            pid=conn.execute("SELECT pg_backend_pid()").fetchone()[0]
            before=conn.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),"
                "current_setting('search_path')").fetchone()
        self.service().designate(self.crypto.token(),self.request)
        with self.pool.connection() as conn:
            self.assertEqual(pid,conn.execute("SELECT pg_backend_pid()").fetchone()[0])
            self.assertEqual(before,conn.execute("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),"
                "current_setting('search_path')").fetchone())
            for key in keys:
                self.assertIn(conn.execute("SELECT current_setting(%s,true)",("forge.designation_"+key,)).fetchone()[0],(None,""))

    def test_runtime_binder_and_wrong_pool_cannot_designate(self):
        for role in ("forge_runtime","forge_identity_binder","postgres"):
            pool=self.db.pool(user=role);self.addCleanup(pool.close,timeout=5)
            with self.subTest(role=role),self.assertRaises(DesignationUnavailable):
                self.service(pool=pool).designate(self.crypto.token(),self.request)
        self.assertEqual(self.state(),([],[],[],1))

    def test_dirty_context_outer_transaction_and_non_autocommit_deny(self):
        from contextlib import contextmanager
        class Borrowed:
            def __init__(inner,conn):inner.conn=conn
            @contextmanager
            def connection(inner,**kwargs):yield inner.conn
        with self.pool.connection() as conn:
            with conn.transaction():
                self.context(conn)
                with self.assertRaises(DesignationUnavailable):
                    self.service(pool=Borrowed(conn)).designate(self.crypto.token(),self.request)
            conn.execute("SET forge.designation_actor='PRIVATE_INVALID_CONTEXT'")
            try:
                with self.assertRaises(DesignationUnavailable):
                    self.service(pool=Borrowed(conn)).designate(self.crypto.token(),self.request)
            finally:conn.execute("RESET forge.designation_actor")
            conn.autocommit=False
            try:
                with self.assertRaises(DesignationUnavailable):
                    self.service(pool=Borrowed(conn)).designate(self.crypto.token(),self.request)
            finally:conn.autocommit=True
        self.assertEqual(self.state(),([],[],[],1))

    def test_closed_and_exhausted_pool_errors_are_bounded_redacted(self):
        from concurrent.futures import ThreadPoolExecutor
        pool=self.db.pool(user="forge_designator");pool.close(timeout=5)
        with self.assertRaises(DesignationUnavailable) as error:
            self.service(pool=pool).designate(self.crypto.token(),self.request)
        self.assertEqual(str(error.exception),"Initial designation unavailable.")
        service=InitialAdministratorService(self.crypto.validator,
            PostgresInitialAdministratorStore(self.pool,acquisition_timeout=.1),self.crypto.configuration)
        with self.pool.connection():
            with ThreadPoolExecutor(max_workers=1) as workers:
                future=workers.submit(service.designate,self.crypto.token(),self.request)
                with self.assertRaises(DesignationUnavailable):future.result(timeout=2)
        self.assertEqual(self.state(),([],[],[],1))

    def test_actual_membership_lock_timeout_rolls_back_claim_then_recovers(self):
        from concurrent.futures import ThreadPoolExecutor
        with connect() as admin,admin.transaction():
            admin.execute("SELECT id FROM forge.memberships WHERE id=%s FOR UPDATE",(MEMBER_A,))
            with ThreadPoolExecutor(max_workers=1) as workers:
                future=workers.submit(self.service().designate,self.crypto.token(),self.request)
                with self.assertRaises(DesignationUnavailable):future.result(timeout=4)
        self.assertEqual(self.state(),([],[],[],1))
        self.assertEqual(self.service().designate(self.crypto.token(),self.request).revision,2)

    def concurrent(self,requests,configuration=None):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        import psycopg
        barrier=Barrier(len(requests))
        class Cursor(psycopg.Cursor):
            def execute(inner,query,params=None,**kwargs):
                if str(query).startswith("INSERT INTO forge.initial_admin_designations"):
                    barrier.wait(timeout=5)
                return super(Cursor,inner).execute(query,params,**kwargs)
        class Connection(psycopg.Connection):
            def cursor(inner,*args,**kwargs):return Cursor(inner,row_factory=kwargs.get("row_factory"))
        pools=[self.db.pool(user="forge_designator",connection_class=Connection) for _ in requests]
        for pool in pools:self.addCleanup(pool.close,timeout=5)
        def invoke(pair):
            pool,request=pair
            try:return self.service(pool=pool,configuration=configuration).designate(self.crypto.token(),request)
            except (DesignationConflict,DesignationDenied) as error:return type(error)
        with ThreadPoolExecutor(max_workers=len(requests)) as workers:
            return list(workers.map(invoke,zip(pools,requests)))

    def test_concurrent_exact_replay_has_one_event_and_original_result(self):
        results=self.concurrent([self.request,self.request])
        self.assertEqual(results[0],results[1])
        roles,markers,events,revision=self.state()
        self.assertEqual((len(roles),len(markers),len(events),revision),(1,1,1,2))

    def test_concurrent_distinct_targets_in_one_org_have_one_winner(self):
        from dataclasses import replace
        from postgres_support import CAROL
        self.bind(CAROL,UUID(int=801))
        results=self.concurrent([self.request,replace(self.request,membership_id=UUID(int=23),operation_id=uuid4())])
        self.assertEqual(sum(type(v) is DesignationResult for v in results),1)
        self.assertEqual(sum(v is DesignationConflict for v in results),1)
        roles,markers,events,revision=self.state()
        self.assertEqual((len(roles),len(markers),len(events)),(1,1,1))
        with connect() as conn:
            self.assertEqual(sum(r[0]-1 for r in conn.execute("SELECT revision FROM forge.memberships").fetchall()),1)

    def test_different_organizations_concurrently_commit_independently(self):
        from dataclasses import replace
        from postgres_support import BOB,ORG_B,MEMBER_B
        self.bind(BOB,UUID(int=802))
        cfg=DesignationConfiguration((self.crypto.operator,),{ORG_A:{UUID(TENANT)},ORG_B:{UUID(TENANT)}})
        requests=[self.request,replace(self.request,organization_id=ORG_B,membership_id=MEMBER_B,operation_id=uuid4())]
        results=self.concurrent(requests,cfg)
        self.assertTrue(all(type(v) is DesignationResult for v in results))
        self.assertEqual(len(self.state()[1]),2)
        self.assertEqual(len(self.state()[2]),2)

    def test_target_suspension_race_reloads_locked_state_and_rolls_back(self):
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        from dataclasses import replace
        import psycopg
        ready=Event()
        class Cursor(psycopg.Cursor):
            def execute(inner,query,params=None,**kwargs):
                if "FOR UPDATE OF m" in str(query):ready.set()
                return super(Cursor,inner).execute(query,params,**kwargs)
        class Connection(psycopg.Connection):
            def cursor(inner,*args,**kwargs):return Cursor(inner,row_factory=kwargs.get("row_factory"))
        pool=self.db.pool(user="forge_designator",connection_class=Connection)
        self.addCleanup(pool.close,timeout=5)
        with ThreadPoolExecutor(max_workers=1) as workers:
            with connect() as admin,admin.transaction():
                admin.execute("UPDATE forge.memberships SET status='suspended' WHERE id=%s",(MEMBER_A,))
                future=workers.submit(self.service(pool=pool).designate,self.crypto.token(),self.request)
                self.assertTrue(ready.wait(timeout=2))
            with self.assertRaises(DesignationDenied):future.result(timeout=3)
        self.assertEqual(self.state(),([],[],[],1))

    def test_revision_bigint_boundary(self):
        from dataclasses import replace
        with connect() as conn:conn.execute("UPDATE forge.memberships SET revision=%s WHERE id=%s",(2**63-2,MEMBER_A))
        result=self.service().designate(self.crypto.token(),replace(self.request,expected_revision=2**63-2))
        self.assertEqual(result.revision,2**63-1)

    def test_timeout_values_are_safe_before_numeric_conversion(self):
        for value in (True,0,-1,31,float("inf"),float("nan"),10**400,"1"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                PostgresInitialAdministratorStore(self.pool,acquisition_timeout=value)

    def test_designator_restrictive_scope_blocks_old_public_context_expansion(self):
        from postgres_support import ORG_B,set_context
        with connect() as admin:
            admin.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,'active',1)",
                (ORG_B,UUID(int=909),ALICE))
        with self.pool.connection() as conn,conn.transaction():
            self.context(conn)
            # Existing PUBLIC policies can see the same identity's other-org row,
            # but the new role-specific restrictive policy must still hide it.
            set_context(conn,organization=ORG_B,provider="entra",issuer=issuer(),subject=str(UUID(int=800)))
            self.assertEqual(conn.execute("SELECT organization_id,id FROM forge.memberships").fetchall(),
                [(ORG_A,MEMBER_A)])
            self.assertEqual(conn.execute("SELECT id FROM forge.organizations").fetchall(),[(ORG_A,)])
            self.assertEqual(conn.execute("SELECT id FROM forge.identities").fetchall(),[(ALICE,)])

    def test_designator_has_no_default_context_access_and_cannot_broaden_actor_replay(self):
        first=self.service().designate(self.crypto.token(),self.request)
        with self.pool.connection() as conn:
            for table in ("identities","organizations","memberships","membership_roles",
                          "initial_admin_designations","initial_admin_outbox"):
                self.assertEqual(conn.execute("SELECT * FROM forge."+table).fetchall(),[])
            for changed in ("actor","request","member","organization"):
                with conn.transaction():
                    self.context(conn)
                    conn.execute("SELECT set_config(%s,%s,true)",
                        ("forge.designation_"+changed,str(uuid4())))
                    self.assertEqual(conn.execute("SELECT * FROM forge.initial_admin_designations").fetchall(),[])
                    self.assertEqual(conn.execute("SELECT * FROM forge.initial_admin_outbox").fetchall(),[])

    def test_runtime_and_binder_have_zero_operational_table_and_column_privileges(self):
        import psycopg
        for role in ("forge_runtime","forge_identity_binder"):
            pool=self.db.pool(user=role);self.addCleanup(pool.close,timeout=5)
            with pool.connection() as conn:
                for table in ("initial_admin_designations","initial_admin_outbox"):
                    self.assertFalse(conn.execute("SELECT has_table_privilege(current_user,%s,"
                        "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),"
                        "has_any_column_privilege(current_user,%s,'SELECT,INSERT,UPDATE,REFERENCES')",
                        ("forge."+table,"forge."+table)).fetchone()[0])
                    self.assertEqual(conn.execute("SELECT has_any_column_privilege(current_user,%s,"
                        "'SELECT,INSERT,UPDATE,REFERENCES')",("forge."+table,)).fetchone(),(False,))
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege),conn.transaction():
                        conn.execute("SELECT * FROM forge."+table)

    def test_designator_column_matrix_cannot_write_identity_status_org_or_audit(self):
        import psycopg
        with self.pool.connection() as conn:
            attempts=("UPDATE forge.identities SET subject=subject",
                "UPDATE forge.organizations SET active=true",
                "UPDATE forge.memberships SET status='active'",
                "INSERT INTO forge.memberships VALUES(NULL,NULL,NULL,'active',1)",
                "DELETE FROM forge.initial_admin_designations",
                "UPDATE forge.initial_admin_outbox SET outcome=outcome",
                "DELETE FROM forge.initial_admin_outbox",
                "SELECT * FROM forge.configuration_revisions",
                "CREATE TABLE forge.not_permitted(id integer)",
                "SET ROLE forge_migrator")
            for query in attempts:
                with self.subTest(query=query),self.assertRaises(psycopg.errors.InsufficientPrivilege),conn.transaction():
                    self.context(conn);conn.execute(query)
            for role in ("member","platform_operator"):
                with self.subTest(role=role),self.assertRaises((psycopg.errors.InsufficientPrivilege,
                        psycopg.errors.CheckViolation)),conn.transaction():
                    self.context(conn)
                    conn.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,%s)",(ORG_A,MEMBER_A,role))
        self.assertEqual(self.state(),([],[],[],1))

    def test_schema_privilege_policy_tampering_fails_closed_and_recovers(self):
        from forge.postgres import PostgresReadinessProbe
        runtime=self.db.pool();self.addCleanup(runtime.close,timeout=5)
        probe=PostgresReadinessProbe(runtime)
        pairs=(
            ("GRANT SELECT ON forge.initial_admin_outbox TO forge_runtime",
             "REVOKE SELECT ON forge.initial_admin_outbox FROM forge_runtime"),
            ("GRANT SELECT(event_id) ON forge.initial_admin_outbox TO forge_runtime",
             "REVOKE SELECT(event_id) ON forge.initial_admin_outbox FROM forge_runtime"),
            ("GRANT SELECT ON forge.initial_admin_designations TO forge_identity_binder",
             "REVOKE SELECT ON forge.initial_admin_designations FROM forge_identity_binder"),
            ("GRANT UPDATE(status) ON forge.memberships TO forge_designator",
             "REVOKE UPDATE(status) ON forge.memberships FROM forge_designator"),
            ("GRANT UPDATE ON forge.memberships TO forge_designator",
             "REVOKE UPDATE ON forge.memberships FROM forge_designator; "
             "GRANT UPDATE(revision) ON forge.memberships TO forge_designator"),
            ("GRANT REFERENCES(revision) ON forge.memberships TO forge_designator",
             "REVOKE REFERENCES(revision) ON forge.memberships FROM forge_designator"),
            ("ALTER TABLE forge.initial_admin_outbox DISABLE ROW LEVEL SECURITY",
             "ALTER TABLE forge.initial_admin_outbox ENABLE ROW LEVEL SECURITY"),
            ("ALTER TABLE forge.initial_admin_designations NO FORCE ROW LEVEL SECURITY",
             "ALTER TABLE forge.initial_admin_designations FORCE ROW LEVEL SECURITY"),
            ("ALTER POLICY designation_member_limit ON forge.memberships USING(true) WITH CHECK(true)",
             None),
            ("ALTER POLICY designation_record_insert ON forge.initial_admin_designations TO PUBLIC",
             "ALTER POLICY designation_record_insert ON forge.initial_admin_designations TO forge_designator"),
            ("ALTER FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) RESET ALL",
             "ALTER FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) SET search_path=pg_catalog"),
            ("ALTER FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) SECURITY DEFINER",
             "ALTER FUNCTION forge.designation_scope(uuid,uuid,uuid,uuid) SECURITY INVOKER"),
        )
        with connect() as admin:
            original=admin.execute("SELECT pg_get_expr(polqual,polrelid),pg_get_expr(polwithcheck,polrelid) "
                "FROM pg_policy WHERE polname='designation_member_limit'").fetchone()
            for corrupt,restore in pairs:
                with self.subTest(corrupt=corrupt):
                    admin.execute(corrupt)
                    try:
                        self.assertFalse(probe.check())
                        with self.assertRaises(DesignationUnavailable):
                            self.service().designate(self.crypto.token(),self.request)
                    finally:
                        admin.execute(restore or ("ALTER POLICY designation_member_limit ON forge.memberships "
                            "USING("+original[0]+") WITH CHECK("+original[1]+")"))
                    self.assertTrue(probe.check())
        self.assertEqual(self.state(),([],[],[],1))

    def test_unknown_table_zero_access_matrix_not_blind_select_grant(self):
        from forge.postgres import PostgresReadinessProbe
        runtime=self.db.pool();self.addCleanup(runtime.close,timeout=5)
        probe=PostgresReadinessProbe(runtime)
        with connect() as admin:
            admin.execute("CREATE TABLE forge.future_private_probe(value text)")
            try:
                self.assertTrue(probe.check())
                for grant,revoke in (
                        ("GRANT SELECT ON forge.future_private_probe TO forge_runtime",
                         "REVOKE SELECT ON forge.future_private_probe FROM forge_runtime"),
                        ("GRANT SELECT(value) ON forge.future_private_probe TO forge_runtime",
                         "REVOKE SELECT(value) ON forge.future_private_probe FROM forge_runtime"),
                        ("GRANT SELECT ON forge.future_private_probe TO forge_designator",
                         "REVOKE SELECT ON forge.future_private_probe FROM forge_designator")):
                    admin.execute(grant)
                    try:self.assertFalse(probe.check())
                    finally:admin.execute(revoke)
                    self.assertTrue(probe.check())
            finally:admin.execute("DROP TABLE forge.future_private_probe")

    def test_exact_constraints_and_extra_policies_cannot_report_ready(self):
        from forge.postgres import PostgresReadinessProbe
        runtime=self.db.pool();self.addCleanup(runtime.close,timeout=5)
        probe=PostgresReadinessProbe(runtime)
        with connect() as admin:
            definition=admin.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname='designation_committed_event'").fetchone()[0]
            pairs=(
                ("ALTER TABLE forge.initial_admin_designations DROP CONSTRAINT designation_committed_event",
                 "ALTER TABLE forge.initial_admin_designations ADD CONSTRAINT designation_committed_event "+definition),
                ("ALTER TABLE forge.initial_admin_outbox ALTER COLUMN occurred_at DROP DEFAULT",
                 "ALTER TABLE forge.initial_admin_outbox ALTER COLUMN occurred_at SET DEFAULT transaction_timestamp()"),
                ("CREATE POLICY designation_unwanted ON forge.memberships TO forge_designator USING(true)",
                 "DROP POLICY designation_unwanted ON forge.memberships"),
                ("CREATE POLICY runtime_unwanted ON forge.initial_admin_outbox TO forge_runtime USING(true)",
                 "DROP POLICY runtime_unwanted ON forge.initial_admin_outbox"),
            )
            for corrupt,restore in pairs:
                with self.subTest(change=corrupt):
                    admin.execute(corrupt)
                    try:self.assertFalse(probe.check())
                    finally:admin.execute(restore)
                    self.assertTrue(probe.check())

    def test_target_tenant_map_is_independent_of_operator_resource_tenant(self):
        from postgres_support import CAROL
        from test_entra import OTHER_TENANT
        from dataclasses import replace
        self.bind(CAROL,UUID(int=801),OTHER_TENANT)
        cfg=DesignationConfiguration((self.crypto.operator,),{ORG_A:{UUID(OTHER_TENANT)}})
        result=self.service(configuration=cfg).designate(self.crypto.token(),
            replace(self.request,membership_id=UUID(int=23)))
        self.assertEqual(result.revision,2)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT target_tenant_id FROM forge.initial_admin_designations").fetchone(),
                (UUID(OTHER_TENANT),))

    def test_unbound_entra_identity_not_just_generic_provider_is_denied(self):
        from postgres_support import CAROL
        from dataclasses import replace
        with connect() as admin:
            admin.execute("UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s WHERE id=%s",
                (issuer(),str(UUID(int=801)),CAROL))
        with self.assertRaises(DesignationDenied):
            self.service().designate(self.crypto.token(),replace(self.request,membership_id=UUID(int=23)))
        self.assertEqual(self.state(),([],[],[],1))

    def test_event_metadata_extra_keys_and_payload_mismatch_cannot_commit(self):
        import psycopg
        from forge.administration_store import _EVENT
        from test_administration import ACTOR
        event=uuid4()
        with connect() as admin:
            for actor,metadata in ((UUID(int=701),None),(ACTOR,{"extra":"not-allowed"})):
                with self.subTest(actor=actor),self.assertRaises((psycopg.errors.ForeignKeyViolation,
                        psycopg.errors.CheckViolation)),admin.transaction():
                    admin.execute("INSERT INTO forge.initial_admin_designations VALUES(%s,%s,%s,%s,%s,1,2,%s)",
                        (ORG_A,MEMBER_A,self.request.operation_id,ACTOR,UUID(TENANT),event))
                    if metadata is None:
                        admin.execute(_EVENT,(event,ORG_A,actor,self.request.operation_id,MEMBER_A,1,2,1,2))
                    else:
                        from psycopg.types.json import Jsonb
                        admin.execute("INSERT INTO forge.initial_admin_outbox "
                            "(event_id,schema_version,organization_id,actor_id,actor_type,source,event_type,"
                            "request_id,resource_type,resource_id,outcome,previous_revision,revision,metadata) "
                            "VALUES(%s,1,%s,%s,'deployment_operator','server','membership.initial_admin_designated',"
                            "%s,'membership',%s,'succeeded',1,2,%s)",
                            (event,ORG_A,actor,self.request.operation_id,MEMBER_A,Jsonb(metadata)))
        self.assertEqual(self.state(),([],[],[],1))


    def test_schema_attestation_preserves_security_literal_whitespace(self):
        from forge.postgres import PostgresReadinessProbe
        pool=self.db.pool();self.addCleanup(pool.close,timeout=5)
        probe=PostgresReadinessProbe(pool)
        with connect() as admin:
            definition=admin.execute("SELECT pg_get_functiondef('forge.designation_scope(uuid,uuid,uuid,uuid)'::regprocedure)").fetchone()[0]
            policy=admin.execute("SELECT pg_get_expr(polqual,polrelid) FROM pg_policy WHERE polname='designation_identity'").fetchone()[0]
            constraint=admin.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='initial_admin_outbox_actor_type_check'").fetchone()[0]
            cases=(
                (definition.replace("'organization'","'organi zation'"),definition),
                ("ALTER POLICY designation_identity ON forge.identities USING("+policy.replace("'entra'","'en tra'")+")",
                 "ALTER POLICY designation_identity ON forge.identities USING("+policy+")"),
                ("ALTER TABLE forge.initial_admin_outbox DROP CONSTRAINT initial_admin_outbox_actor_type_check; "
                 "ALTER TABLE forge.initial_admin_outbox ADD CONSTRAINT initial_admin_outbox_actor_type_check "+constraint.replace("'deployment_operator'","'deployment_ operator'"),
                 "ALTER TABLE forge.initial_admin_outbox DROP CONSTRAINT initial_admin_outbox_actor_type_check; "
                 "ALTER TABLE forge.initial_admin_outbox ADD CONSTRAINT initial_admin_outbox_actor_type_check "+constraint),
            )
            for corrupt,restore in cases:
                with self.subTest(shape=corrupt.splitlines()[0]):
                    admin.execute(corrupt)
                    try:
                        self.assertFalse(probe.check())
                        with self.assertRaises(DesignationUnavailable):
                            self.service().designate(self.crypto.token(),self.request)
                    finally:
                        admin.execute(restore)
                    self.assertTrue(probe.check())
        self.assertEqual(self.state(),([],[],[],1))

if __name__=="__main__":
    unittest.main()
