"""Explicit owned-harness connections and fixtures; never ambient PG defaults."""
import os
from pathlib import Path
import secrets
import time
from uuid import UUID

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('identities', 'organizations', 'memberships', 'configuration_revisions')
KEYS = ('organization', 'provider', 'issuer', 'subject')
ORG_A, ORG_B = UUID(int=1), UUID(int=2)
ALICE, BOB, CAROL, SUSPENDED, ARCHIVED = (UUID(int=n) for n in range(11, 16))
MEMBER_A, MEMBER_B = UUID(int=21), UUID(int=22)


def settings():
    if os.environ.get('FORGE_PG_HARNESS') != 'owned-disposable-v1':
        raise RuntimeError('Real PostgreSQL required: run scripts/test-postgres.ps1')
    port = os.environ.get('FORGE_PG_PORT', '')
    password = os.environ.get('FORGE_PG_PASSWORD', '')
    if not port.isdecimal() or not 1 <= int(port) <= 65535 or not password:
        raise RuntimeError('Owned PostgreSQL harness settings are incomplete')
    return dict(host='127.0.0.1', port=int(port), dbname='forge_test',
                user='postgres', password=password, connect_timeout=2,
                options='-c statement_timeout=5000', autocommit=True)


def connect(user='postgres', password=None):
    kwargs = settings()
    kwargs['user'] = user
    if password is not None:
        kwargs['password'] = password
    return psycopg.connect(**kwargs)


def wait_ready():
    settings()  # Validate before a bounded connection-readiness wait.
    for _ in range(30):
        try:
            with connect() as conn:
                conn.execute('SELECT 1')
            return
        except psycopg.OperationalError:
            time.sleep(0.5)
    raise RuntimeError('Owned local PostgreSQL did not become ready within 15 seconds')


def set_context(conn, organization=ORG_A, provider='test', issuer='issuer', subject='alice'):
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS:
        raise RuntimeError('Context requires an outer transaction')
    for key, value in zip(KEYS, (organization, provider, issuer, subject)):
        conn.execute('SELECT set_config(%s, %s, true)',
                     ('forge.' + key, '' if value is None else str(value)))


def rows(conn, table):
    if table not in TABLES:
        raise ValueError('Unknown fixture table')
    return conn.execute(sql.SQL('SELECT * FROM forge.{}').format(
        sql.Identifier(table))).fetchall()



def migration_probe(*, populated=False, rollback=False, failure=False):
    """Exact migration scripts against a separate DB inside this owned cluster.

    Invoked before shared fixture roles exist. Drop only the created DB and its
    reserved roles; never an existing deployment. Each case owns a random name.
    """
    from uuid import uuid4
    name = 'forge_migration_' + uuid4().hex
    evidence = None
    failure_state = None
    with connect() as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        kwargs = settings()
        kwargs['dbname'] = name
        with psycopg.connect(**kwargs) as conn:
            conn.execute((ROOT / 'migrations/0001_bootstrap.sql').read_text('utf-8'))
            generic, entra = UUID(int=801), UUID(int=802)
            tid, oid = UUID(int=803), UUID(int=804)
            if populated:
                with conn.transaction():
                    conn.execute('INSERT INTO forge.identities (id,provider,issuer,subject) '
                                 'VALUES (%s,%s,%s,%s),(%s,%s,%s,%s)',
                                 (generic, 'test', 'issuer', 'existing', entra, 'entra',
                                  'https://login.microsoftonline.com/' + str(tid) + '/v2.0', str(oid)))
                    conn.execute('INSERT INTO forge.organizations VALUES (%s,%s,%s,true,1)',
                                 (ORG_A, 'upgrade', 'Upgrade'))
                    conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,1)', (ORG_A,))
                    conn.execute('INSERT INTO forge.memberships VALUES (%s,%s,%s,%s)',
                                 (ORG_A, MEMBER_A, entra, 'active'))
            before = {table: conn.execute(sql.SQL('SELECT * FROM forge.{} ORDER BY 1').format(
                sql.Identifier(table))).fetchall() for table in TABLES}
            policy_sql = (
                "SELECT p.polname,p.polrelid,pg_get_expr(p.polqual,p.polrelid),"
                "pg_get_expr(p.polwithcheck,p.polrelid),p.polroles FROM pg_policy p "
                "JOIN pg_class c ON c.oid=p.polrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='forge' "
                "ORDER BY p.polname,p.polrelid")
            function_sql = (
                "SELECT p.proname,p.proowner,p.prosecdef,p.proacl::text FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='forge' ORDER BY p.proname")
            policies_before = conn.execute(policy_sql).fetchall()
            functions_before = conn.execute(function_sql).fetchall()
            migration = (ROOT / 'migrations/0002_entra_identity_binding.sql').read_text('utf-8')
            if rollback or failure:
                if not migration.endswith('COMMIT;\n'):
                    raise RuntimeError('Unexpected migration transaction boundary')
                if rollback:
                    # Explicit rollback is distinct from a failed transaction.
                    migration = migration[:-len('COMMIT;\n')] + 'ROLLBACK;\n'
                else:
                    # All original DDL/grants execute; fail before original COMMIT.
                    migration = migration[:-len('COMMIT;\n')] + 'SELECT 1 / 0;\nCOMMIT;\n'
            if failure:
                try:
                    conn.execute(migration)
                except psycopg.errors.DivisionByZero as error:
                    aborted = conn.info.transaction_status is psycopg.pq.TransactionStatus.INERROR
                    failure_state = (error.sqlstate, aborted)
                    if failure_state != ('22012', True):
                        raise RuntimeError('Expected migration failure was not observed')
                    conn.execute('ROLLBACK')
                    if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                        raise RuntimeError('Failed migration rollback did not restore idle state')
                else:
                    raise RuntimeError('Injected migration failure did not occur')
            else:
                conn.execute(migration)
            reverted = rollback or failure
            if reverted:
                if (conn.execute(policy_sql).fetchall() != policies_before
                    or conn.execute(function_sql).fetchall() != functions_before):
                    raise RuntimeError('Migration rollback changed policies or functions')
            columns = conn.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='forge' AND table_name='identities' "
                "AND column_name IN ('entra_tenant_id','entra_object_id')").fetchall()
            if len(columns) != (0 if reverted else 2):
                raise RuntimeError('Migration column proof failed')
            for table in TABLES:
                after = conn.execute(sql.SQL('SELECT * FROM forge.{} ORDER BY 1').format(
                    sql.Identifier(table))).fetchall()
                expected = ([row + (None, None) for row in before[table]]
                            if table == 'identities' and not reverted else before[table])
                if after != expected:
                    raise RuntimeError('Migration changed existing records')
            role = conn.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_identity_binder'").fetchone()[0]
            if role != (0 if reverted else 1):
                raise RuntimeError('Migration role rollback proof failed')
            rls = conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity").fetchone()[0]
            if rls != 4:
                raise RuntimeError('Migration RLS proof failed')
            evidence = (len(columns), len(before['identities']), len(before['memberships']), rls, role)
            if failure:
                evidence += failure_state + (conn.info.transaction_status is psycopg.pq.TransactionStatus.IDLE,)
    finally:
        # Database removal has its own finite budget, not a product-query override.
        cleanup_settings = settings()
        cleanup_settings['options'] = '-c statement_timeout=30000 -c lock_timeout=2000'
        with psycopg.connect(**cleanup_settings) as admin:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
            # These roles were created only by this case in the owned ephemeral cluster.
            for role in ('forge_identity_binder', 'forge_runtime', 'forge_migrator'):
                admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
    return evidence



def authorization_migration_probe(*, populated=False, failure=False):
    """Separate exact0003 cases; original0002 probes/evidence stay unchanged."""
    from uuid import uuid4
    name = "forge_authorization_" + uuid4().hex
    created_roles = False
    with connect() as admin:
        if admin.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN "
                "('forge_runtime','forge_migrator','forge_identity_binder'))").fetchone()[0]:
            raise RuntimeError("Authorization probe requires its own role lifecycle")
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        kwargs = settings() | {"dbname": name}
        with psycopg.connect(**kwargs) as conn:
            conn.execute((ROOT/"migrations/0001_bootstrap.sql").read_text("utf-8"))
            created_roles = True
            conn.execute((ROOT/"migrations/0002_entra_identity_binding.sql").read_text("utf-8"))
            if populated:
                with conn.transaction():
                    conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) "
                        "VALUES (%s,'test','issuer','existing')", (ALICE,))
                    conn.execute("INSERT INTO forge.organizations VALUES (%s,'upgrade','Upgrade',true,1)",
                        (ORG_A,))
                    conn.execute("INSERT INTO forge.configuration_revisions VALUES (%s,1)", (ORG_A,))
                    conn.execute("INSERT INTO forge.memberships VALUES (%s,%s,%s,'active')",
                        (ORG_A, MEMBER_A, ALICE))
                    for identity,member,status in ((CAROL,UUID(int=903),"suspended"),
                            (SUSPENDED,UUID(int=904),"archived")):
                        conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) "
                            "VALUES (%s,'test','issuer',%s)",(identity,"existing-"+status))
                        conn.execute("INSERT INTO forge.memberships VALUES (%s,%s,%s,%s)",
                            (ORG_A,member,identity,status))
            rows_before = {table: conn.execute(sql.SQL("SELECT * FROM forge.{} ORDER BY 1").format(
                sql.Identifier(table))).fetchall() for table in TABLES}
            metadata = """
SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text,c.relowner
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='forge' AND c.relkind='r' ORDER BY c.relname
"""
            policies = """
SELECT p.polname,p.polrelid,p.polcmd,p.polroles,p.polqual::text,p.polwithcheck::text
FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='forge'
ORDER BY p.polname,p.polrelid
"""
            functions = """
SELECT p.proname,p.proowner,p.prosecdef,p.proacl::text,p.prosrc
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='forge' ORDER BY p.proname
"""
            before = [conn.execute(query).fetchall() for query in (metadata,policies,functions)]
            migration = (ROOT/"migrations/0003_membership_authorization.sql").read_text("utf-8")
            if not migration.endswith("COMMIT;\n"):
                raise RuntimeError("Unexpected authorization migration boundary")
            state = None
            if failure:
                injected = migration[:-len("COMMIT;\n")] + "SELECT 1 / 0;\nCOMMIT;\n"
                try:
                    conn.execute(injected)
                except psycopg.errors.DivisionByZero as error:
                    state = (error.sqlstate,
                        conn.info.transaction_status is psycopg.pq.TransactionStatus.INERROR)
                    if state != ("22012",True):
                        raise RuntimeError("Authorization migration failure not observed")
                    conn.execute("ROLLBACK")
                else:
                    raise RuntimeError("Authorization failure injection did not fail")
                if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                    raise RuntimeError("Authorization rollback did not restore idle")
                if [conn.execute(q).fetchall() for q in (metadata,policies,functions)] != before:
                    raise RuntimeError("Authorization rollback changed prior metadata/ACL/RLS")
            else:
                conn.execute(migration)
            table = conn.execute("SELECT to_regclass('forge.membership_roles') IS NOT NULL").fetchone()[0]
            revision = conn.execute("SELECT EXISTS(SELECT 1 FROM pg_attribute "
                "WHERE attrelid='forge.memberships'::regclass AND attname='revision' "
                "AND NOT attisdropped)").fetchone()[0]
            if table is not (not failure) or revision is not (not failure):
                raise RuntimeError("Authorization migration object proof failed")
            for key in TABLES:
                after = conn.execute(sql.SQL("SELECT * FROM forge.{} ORDER BY 1").format(
                    sql.Identifier(key))).fetchall()
                expected = ([row+(1,) for row in rows_before[key]]
                    if key == "memberships" and not failure else rows_before[key])
                if after != expected:
                    raise RuntimeError("Authorization migration changed prior records")
            if not failure and conn.execute("SELECT count(*) FROM forge.membership_roles").fetchone()[0] != 0:
                raise RuntimeError("Authorization migration seeded roles")
            rls = conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname='forge' AND c.relkind='r' "
                "AND c.relrowsecurity AND c.relforcerowsecurity").fetchone()[0]
            if rls != (4 if failure else 5):
                raise RuntimeError("Authorization RLS migration proof failed")
            return (table,revision,len(rows_before["memberships"]),rls,state,
                    conn.info.transaction_status is psycopg.pq.TransactionStatus.IDLE)
    finally:
        with connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            if created_roles:
                for role in ("forge_identity_binder","forge_runtime","forge_migrator"):
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def designation_migration_probe(*, populated=False, failure=False):
    """Separate exact0004 cases; original0002/0003 probes are immutable."""
    from uuid import uuid4
    name="forge_designation_"+uuid4().hex
    created_roles=False
    with connect() as admin:
        if admin.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN "
                "('forge_runtime','forge_migrator','forge_identity_binder','forge_designator'))").fetchone()[0]:
            raise RuntimeError("Designation probe requires its own role lifecycle")
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(**(settings()|{"dbname":name})) as conn:
            for filename in ("0001_bootstrap.sql","0002_entra_identity_binding.sql",
                             "0003_membership_authorization.sql"):
                conn.execute((ROOT/"migrations"/filename).read_text("utf-8"))
                created_roles=True
            if populated:
                with conn.transaction():
                    conn.execute("INSERT INTO forge.organizations VALUES(%s,'upgrade','Upgrade',false,1)",(ORG_A,))
                    conn.execute("INSERT INTO forge.configuration_revisions VALUES(%s,1)",(ORG_A,))
                    for identity,member,status in ((ALICE,MEMBER_A,"active"),
                            (CAROL,UUID(int=903),"suspended"),(SUSPENDED,UUID(int=904),"archived")):
                        conn.execute("INSERT INTO forge.identities(id,provider,issuer,subject) "
                            "VALUES(%s,'test','issuer',%s)",(identity,"existing-"+status))
                        conn.execute("INSERT INTO forge.memberships VALUES(%s,%s,%s,%s,3)",
                            (ORG_A,member,identity,status))
                    conn.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'member')",(ORG_A,MEMBER_A))
            tables=TABLES+("membership_roles",)
            records={t:conn.execute(sql.SQL("SELECT * FROM forge.{} ORDER BY 1,2").format(
                sql.Identifier(t))).fetchall() for t in tables}
            queries=(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relowner,c.relacl::text "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' ORDER BY c.relname",
                "SELECT p.polname,p.polrelid,p.polcmd,p.polpermissive,p.polroles,p.polqual::text,p.polwithcheck::text "
                "FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname='forge' ORDER BY p.polname",
                "SELECT p.proname,p.proowner,p.prosecdef,p.proacl::text,p.prosrc,p.proconfig "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='forge' ORDER BY p.proname",
                "SELECT k.conname,k.conrelid,k.convalidated,pg_get_constraintdef(k.oid) "
                "FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace "
                "WHERE n.nspname='forge' ORDER BY k.conname",
                "SELECT a.attrelid,a.attname,a.attacl::text FROM pg_attribute a JOIN pg_class c "
                "ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' AND a.attnum>0 ORDER BY a.attrelid,a.attnum",
            )
            before=[conn.execute(q).fetchall() for q in queries]
            migration=(ROOT/"migrations/0004_initial_admin_designation.sql").read_text("utf-8")
            if not migration.endswith("COMMIT;\n"):
                raise RuntimeError("Unexpected designation migration boundary")
            state=None
            if failure:
                script=migration[:-len("COMMIT;\n")]+"SELECT 1/0;\nCOMMIT;\n"
                try:conn.execute(script)
                except psycopg.errors.DivisionByZero as error:
                    state=(error.sqlstate,conn.info.transaction_status is psycopg.pq.TransactionStatus.INERROR)
                    if state!=("22012",True):raise RuntimeError("Designation failure not observed")
                    conn.execute("ROLLBACK")
                else:raise RuntimeError("Designation failure injection did not fail")
                if [conn.execute(q).fetchall() for q in queries]!=before:
                    raise RuntimeError("Designation rollback changed prior metadata")
            else:conn.execute(migration)
            for t in tables:
                after=conn.execute(sql.SQL("SELECT * FROM forge.{} ORDER BY 1,2").format(sql.Identifier(t))).fetchall()
                if after!=records[t]:raise RuntimeError("Designation migration changed prior records")
            present=conn.execute("SELECT to_regclass('forge.initial_admin_designations') IS NOT NULL "
                "AND to_regclass('forge.initial_admin_outbox') IS NOT NULL").fetchone()[0]
            role=conn.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='forge_designator')").fetchone()[0]
            if present is not (not failure) or role is not (not failure):
                raise RuntimeError("Designation object/role transaction proof failed")
            if not failure:
                for t in ("initial_admin_designations","initial_admin_outbox"):
                    if conn.execute(sql.SQL("SELECT count(*) FROM forge.{}").format(sql.Identifier(t))).fetchone()[0]:
                        raise RuntimeError("Designation migration seeded operational records")
            rls=conn.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='forge' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity").fetchone()[0]
            if rls!=(5 if failure else 7):raise RuntimeError("Designation RLS proof failed")
            return (present,role,len(records["memberships"]),rls,state,
                    conn.info.transaction_status is psycopg.pq.TransactionStatus.IDLE)
    finally:
        with connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            if created_roles:
                for role in ("forge_designator","forge_identity_binder","forge_runtime","forge_migrator"):
                    if admin.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)",(role,)).fetchone()[0]:
                        admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def seed_outbox_migration_legacy(conn):
    """Commit a coherent legacy designation only inside the migration probe."""
    tenant, target, actor, request, event = (UUID(int=n) for n in range(701, 706))
    with conn.transaction():
        conn.execute(
            "UPDATE forge.identities SET provider='entra',issuer=%s,subject=%s,"
            "entra_tenant_id=%s,entra_object_id=%s WHERE id=%s",
            (f"https://login.microsoftonline.com/{tenant}/v2.0",
             str(target), tenant, target, ALICE),
        )
        conn.execute("UPDATE forge.memberships SET revision=2 WHERE organization_id=%s AND id=%s",
                     (ORG_A, MEMBER_A))
        conn.execute("INSERT INTO forge.membership_roles VALUES (%s,%s,'organization_admin')",
                     (ORG_A, MEMBER_A))
        conn.execute(
            "INSERT INTO forge.initial_admin_designations "
            "(organization_id,membership_id,request_id,actor_id,target_tenant_id,"
            "expected_revision,revision,event_id) VALUES (%s,%s,%s,%s,%s,1,2,%s)",
            (ORG_A, MEMBER_A, request, actor, tenant, event),
        )
        conn.execute(
            "INSERT INTO forge.initial_admin_outbox "
            "(event_id,schema_version,organization_id,actor_id,actor_type,source,"
            "event_type,request_id,resource_type,resource_id,outcome,"
            "previous_revision,revision,metadata) VALUES "
            "(%s,1,%s,%s,'deployment_operator','server','membership.initial_admin_designated',"
            "%s,'membership',%s,'succeeded',1,2,"
            "jsonb_build_object('role','organization_admin','previous_revision',1,'revision',2))",
            (event, ORG_A, actor, request, MEMBER_A),
        )
        # The marker's deferred FK must resolve to its actual matching event.
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
        raise RuntimeError('Legacy migration seed did not commit')


def outbox_migration_probe(conn, seed):
    """Exercise the actual one-shot script, never change older migration probes."""
    migration = (ROOT / 'migrations/0005_transactional_outbox.sql').read_text('utf-8')
    if not migration.endswith('COMMIT;\n'):
        raise RuntimeError('Unexpected outbox migration boundary')
    evidence = []
    tables = TABLES + ('membership_roles', 'initial_admin_designations', 'initial_admin_outbox')
    metadata = ("SELECT polname,polrelid,polroles,polqual::text,polwithcheck::text "
                "FROM pg_policy ORDER BY polrelid,polname")
    for populated, failure in ((False, False), (True, False), (True, True)):
        if populated:
            seed()
            seed_outbox_migration_legacy(conn)
        records = {t: conn.execute(sql.SQL('SELECT * FROM forge.{} ORDER BY 1,2').format(
            sql.Identifier(t))).fetchall() for t in tables}
        policies = conn.execute(metadata).fetchall()
        if failure:
            try:
                conn.execute(migration[:-len('COMMIT;\n')] + 'SELECT 1/0;\nCOMMIT;\n')
            except psycopg.errors.DivisionByZero:
                if conn.info.transaction_status is not psycopg.pq.TransactionStatus.INERROR:
                    raise RuntimeError('Expected aborted migration')
                conn.execute('ROLLBACK')
                if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                    raise RuntimeError('Failed migration did not return to idle')
            else:
                raise RuntimeError('Migration failure was not observed')
            if conn.execute("SELECT to_regclass('forge.outbox_events')").fetchone()[0] is not None:
                raise RuntimeError('Failed migration retained destination')
            if conn.execute("SELECT count(*) FROM pg_roles WHERE rolname='forge_outbox_writer'").fetchone()[0]:
                raise RuntimeError('Failed migration retained role')
        else:
            conn.execute(migration)
            if conn.execute('SELECT count(*) FROM forge.outbox_events').fetchone()[0] != 0:
                raise RuntimeError('P1a must not import legacy events')
            conn.execute('DROP TABLE forge.outbox_events')
            conn.execute('DROP OWNED BY forge_outbox_writer')
            conn.execute('DROP ROLE forge_outbox_writer')
        for table in tables:
            if conn.execute(sql.SQL('SELECT * FROM forge.{} ORDER BY 1,2').format(
                    sql.Identifier(table))).fetchall() != records[table]:
                raise RuntimeError('Outbox migration changed prior records')
        if conn.execute(metadata).fetchall() != policies:
            raise RuntimeError('Outbox migration changed prior policies')
        legacy_counts = tuple(len(records[table]) for table in
                              ('membership_roles', 'initial_admin_designations', 'initial_admin_outbox'))
        evidence.append((populated, failure, len(records['organizations']), legacy_counts))
    return evidence


class DatabaseFixture:
    # Only this owned harness process shares initialization, never external DB state.
    _credentials = None
    migration_evidence = None
    authorization_migration_evidence = None
    designation_migration_evidence = None

    def __init__(self):
        if self._credentials is not None:
            self.runtime_password, self.writer_password, self.binder_password, self.designator_password = self._credentials
            return
        wait_ready()
        DatabaseFixture.migration_evidence = (
            migration_probe(),
            migration_probe(populated=True),
            migration_probe(populated=True, rollback=True),
            migration_probe(populated=True, failure=True),
        )
        DatabaseFixture.authorization_migration_evidence = (
            authorization_migration_probe(),
            authorization_migration_probe(populated=True),
            authorization_migration_probe(populated=True,failure=True),
        )
        DatabaseFixture.designation_migration_evidence = (
            designation_migration_probe(),
            designation_migration_probe(populated=True),
            designation_migration_probe(populated=True,failure=True),
        )
        self.runtime_password = secrets.token_urlsafe(32)
        self.writer_password = secrets.token_urlsafe(32)
        self.binder_password = secrets.token_urlsafe(32)
        self.designator_password = secrets.token_urlsafe(32)
        with connect() as conn:
            for migration in ('0001_bootstrap.sql', '0002_entra_identity_binding.sql',
                              '0003_membership_authorization.sql','0004_initial_admin_designation.sql'):
                conn.execute((ROOT / 'migrations' / migration).read_text('utf-8'))
            DatabaseFixture.outbox_migration_evidence = outbox_migration_probe(conn, self.reset)
            conn.execute((ROOT / 'migrations/0005_transactional_outbox.sql').read_text('utf-8'))
            conn.execute(sql.SQL('ALTER ROLE forge_designator LOGIN PASSWORD {}').format(sql.Literal(self.designator_password)))
            conn.execute(sql.SQL('ALTER ROLE forge_identity_binder LOGIN PASSWORD {}').format(
                sql.Literal(self.binder_password)))
            # The harness alone provisions LOGIN and a restricted policy-test writer.
            conn.execute(sql.SQL('ALTER ROLE forge_runtime LOGIN PASSWORD {}').format(
                sql.Literal(self.runtime_password)))
            conn.execute(sql.SQL('CREATE ROLE forge_test_writer LOGIN PASSWORD {} '
                'NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION').format(
                sql.Literal(self.writer_password)))
            conn.execute('ALTER POLICY identity_scope ON forge.identities '
                         'TO forge_runtime, forge_migrator, forge_test_writer')
            conn.execute('GRANT CONNECT ON DATABASE forge_test TO forge_test_writer')
            conn.execute('GRANT USAGE ON SCHEMA forge TO forge_test_writer')
            for table in TABLES + ('membership_roles', 'initial_admin_designations', 'initial_admin_outbox'):
                conn.execute(sql.SQL('GRANT SELECT ON forge.{} TO forge_test_writer').format(sql.Identifier(table)))
            conn.execute('GRANT INSERT, UPDATE, DELETE ON forge.configuration_revisions '
                         'TO forge_test_writer')
            conn.execute('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA forge TO forge_test_writer')
            version = conn.execute('SHOW server_version').fetchone()[0]
            print('Real PostgreSQL server:', version)
        DatabaseFixture._credentials = (self.runtime_password, self.writer_password, self.binder_password, self.designator_password)
        self.reset()

    def pool(self, *, user='forge_runtime', pool_class=None, connection_class=psycopg.Connection, **overrides):
        from psycopg_pool import ConnectionPool
        kwargs = settings()
        kwargs['user'] = user
        if user == 'forge_runtime':
            kwargs['password'] = self.runtime_password
        elif user == 'forge_identity_binder':
            kwargs['password'] = self.binder_password
        elif user == 'forge_designator':
            kwargs['password'] = self.designator_password
        elif user == 'forge_test_writer':
            kwargs['password'] = self.writer_password
        kwargs.update(overrides)
        pool = (pool_class or ConnectionPool)(
            conninfo='', kwargs=kwargs, connection_class=connection_class, min_size=1, max_size=1,
            timeout=1, max_waiting=4, reconnect_timeout=1, open=False,
        )
        try:
            pool.open(wait=True, timeout=5)
        except Exception:
            pool.close(timeout=5)
            raise
        return pool

    def runtime(self):
        return connect('forge_runtime', self.runtime_password)

    def writer(self):
        return connect('forge_test_writer', self.writer_password)

    def binder(self):
        return connect('forge_identity_binder', self.binder_password)

    def reset(self):
        with connect() as conn, conn.transaction():
            conn.execute('TRUNCATE forge.organizations, forge.identities CASCADE')
            for identity, subject in ((ALICE, 'alice'), (BOB, 'bob'), (CAROL, 'carol'),
                                      (SUSPENDED, 'suspended'), (ARCHIVED, 'archived')):
                conn.execute('INSERT INTO forge.identities (id,provider,issuer,subject) VALUES (%s,%s,%s,%s)',
                             (identity, 'test', 'issuer', subject))
            for org, slug, revision in ((ORG_A, 'org-a', 1), (ORG_B, 'org-b', 2)):
                conn.execute('INSERT INTO forge.organizations VALUES (%s,%s,%s,true,%s)',
                             (org, slug, slug.upper(), revision))
                conn.execute('INSERT INTO forge.configuration_revisions VALUES (%s,%s)',
                             (org, revision))
            for org, mid, identity, status in (
                (ORG_A, MEMBER_A, ALICE, 'active'), (ORG_B, MEMBER_B, BOB, 'active'),
                (ORG_A, UUID(int=23), CAROL, 'active'),
                (ORG_A, UUID(int=24), SUSPENDED, 'suspended'),
                (ORG_A, UUID(int=25), ARCHIVED, 'archived')):
                conn.execute('INSERT INTO forge.memberships VALUES (%s,%s,%s,%s)',
                             (org, mid, identity, status))


# Faults/probes below wrap real connections, never substitute a database or auth.
SECRET_MARKER = 'PRIVATE_DSN_PASSWORD_TOKEN_MARKER'


class ProbeCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        if 'FROM forge.identities AS i' in str(query):
            from threading import get_ident
            conn = self.connection
            conn.data_threads.append(get_ident())
            conn.observed_context = tuple(conn.execute(
                'SELECT current_setting(%s,true)', ('forge.' + key,)
            ).fetchone()[0] for key in KEYS)
            mode, conn.fail_data = conn.fail_data, None
            if mode:
                try:
                    super().execute('SELECT 1 / 0')  # Real server failure after GUCs.
                except psycopg.errors.DivisionByZero:
                    if mode == 'secret':
                        raise RuntimeError(SECRET_MARKER) from None
                    raise
        return super().execute(query, params, **kwargs)


class ProbeConnection(psycopg.Connection):
    fail_data = None
    observed_context = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_threads = []

    def cursor(self, name='', *, binary=False, row_factory=None,
               scrollable=None, withhold=False):
        if name or binary or scrollable is not None or withhold:
            return super().cursor(name, binary=binary, row_factory=row_factory,
                                  scrollable=scrollable, withhold=withhold)
        return ProbeCursor(self, row_factory=row_factory)


# Catalog0010 is deliberately opt-in: legacy/default fixtures stay at0005.
from contextlib import contextmanager


@contextmanager
def catalog_schema(*, fail_migration=False):
    """Own only the new table/role, never change the default schema inventory."""
    with connect() as conn:
        if conn.execute("SELECT to_regclass('forge.model_catalog_snapshots')").fetchone()[0]:
            raise RuntimeError("Catalog fixture requires absent destination")
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='forge_catalog_writer'").fetchone():
            raise RuntimeError("Catalog fixture requires absent role")
        migration = (ROOT / "migrations/0010_model_catalog_snapshots.sql").read_text("utf-8")
        if not migration.endswith("COMMIT;\n"):
            raise RuntimeError("Unexpected catalog migration boundary")
        applied = False
        try:
            if fail_migration:
                try:
                    conn.execute(migration[:-len("COMMIT;\n")] + "SELECT 1/0;\nCOMMIT;\n")
                except psycopg.errors.DivisionByZero:
                    if conn.info.transaction_status is not psycopg.pq.TransactionStatus.INERROR:
                        raise RuntimeError("Catalog failure was not transactional")
                    conn.execute("ROLLBACK")
                else:
                    raise RuntimeError("Catalog migration failure not observed")
            else:
                conn.execute(migration)
                applied = True
            yield conn
        finally:
            if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                conn.execute("ROLLBACK")
            if applied:
                conn.execute("DROP TABLE forge.model_catalog_snapshots")
                # Own this role only after the earlier absence check and commit.
                conn.execute("DROP OWNED BY forge_catalog_writer")
                conn.execute("DROP ROLE forge_catalog_writer")


@contextmanager
def catalog_publication_schema(*, fail_migration=False, before_migration=None):
    """Opt-in0010/0011; restore only owned schema changes after each case."""
    with catalog_schema() as conn:
        if conn.execute("SELECT to_regclass('forge.active_model_catalogs')").fetchone()[0]:
            raise RuntimeError("Publication fixture requires absent destination")
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='forge_config_publisher'").fetchone():
            raise RuntimeError("Publication fixture requires absent role")
        original_check = conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
            "conrelid='forge.outbox_events'::regclass AND conname='outbox_events_event_type_check'"
        ).fetchone()[0]
        original_policy = conn.execute(
            "SELECT pg_get_expr(polwithcheck,polrelid) FROM pg_policy WHERE "
            "polrelid='forge.outbox_events'::regclass AND polname='outbox_record'"
        ).fetchone()[0]
        if before_migration is not None:
            with conn.transaction():
                before_migration(conn)
        migration = (ROOT / "migrations/0011_model_catalog_publication.sql").read_text("utf-8")
        if not migration.endswith("COMMIT;\n"):
            raise RuntimeError("Unexpected publication migration boundary")
        applied = False
        try:
            if fail_migration:
                try:
                    conn.execute(migration[:-len("COMMIT;\n")] + "SELECT 1/0;\nCOMMIT;\n")
                except psycopg.errors.DivisionByZero:
                    if conn.info.transaction_status is not psycopg.pq.TransactionStatus.INERROR:
                        raise RuntimeError("Publication failure was not transactional")
                    conn.execute("ROLLBACK")
                else:
                    raise RuntimeError("Publication migration failure not observed")
            else:
                conn.execute(migration)
                applied = True
            yield conn
        finally:
            if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                conn.execute("ROLLBACK")
            if applied:
                with conn.transaction():
                    conn.execute("DROP TABLE forge.active_model_catalogs")
                    conn.execute("DROP POLICY catalog_publisher_read ON forge.model_catalog_snapshots")
                    conn.execute("DROP POLICY catalog_event ON forge.outbox_events")
                    conn.execute("ALTER POLICY outbox_record ON forge.outbox_events WITH CHECK "
                                 + original_policy)
                    conn.execute("ALTER TABLE forge.outbox_events DROP CONSTRAINT catalog_publication_event_identity")
                    # Tests may have inserted publication fixtures; remove exactly that new type.
                    conn.execute("DELETE FROM forge.outbox_events WHERE event_type='model_catalog.published'")
                    conn.execute("ALTER TABLE forge.outbox_events DROP CONSTRAINT outbox_events_event_type_check")
                    conn.execute("ALTER TABLE forge.outbox_events ADD CONSTRAINT outbox_events_event_type_check "
                                 + original_check)
                    conn.execute("DROP OWNED BY forge_config_publisher")
                    conn.execute("DROP ROLE forge_config_publisher")


@contextmanager
def catalog_authority_schema(*, fail_migration=False, before_migration=None):
    """Own0012 only inside the already isolated0010/0011 fixture."""
    with catalog_publication_schema() as conn:
        if conn.execute("SELECT to_regclass('forge.catalog_publication_operations')").fetchone()[0]:
            raise RuntimeError("Authority fixture requires absent ledger")
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='forge_catalog_authority'").fetchone():
            raise RuntimeError("Authority fixture requires absent owner")
        if before_migration is not None:
            with conn.transaction():
                before_migration(conn)
        migration = (ROOT / "migrations/0012_catalog_publication_authority.sql").read_text("utf-8")
        if not migration.endswith("COMMIT;\n"):
            raise RuntimeError("Unexpected authority migration boundary")
        applied = False
        try:
            if fail_migration:
                try:
                    conn.execute(migration[:-len("COMMIT;\n")] + "SELECT 1/0;\nCOMMIT;\n")
                except psycopg.errors.DivisionByZero:
                    if conn.info.transaction_status is not psycopg.pq.TransactionStatus.INERROR:
                        raise RuntimeError("Authority failure was not transactional")
                    conn.execute("ROLLBACK")
                else:
                    raise RuntimeError("Authority migration failure not observed")
            else:
                conn.execute(migration)
                applied = True
            yield conn
        finally:
            if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                conn.execute("ROLLBACK")
            if applied:
                with conn.transaction():
                    conn.execute("DROP TABLE forge.catalog_publication_operations")
                    conn.execute("DROP FUNCTION forge.lock_catalog_authority(uuid,uuid,uuid,uuid)")
                    for table in ("organizations", "memberships", "identities", "membership_roles"):
                        for policy in ("catalog_authority_allow", "catalog_authority_limit"):
                            conn.execute(sql.SQL("DROP POLICY {} ON forge.{}").format(
                                sql.Identifier(policy), sql.Identifier(table)))
                    conn.execute("ALTER TABLE forge.model_catalog_snapshots DROP CONSTRAINT catalog_replay_snapshot")
                    conn.execute("ALTER TABLE forge.outbox_events DROP CONSTRAINT catalog_replay_event")
                    conn.execute("DROP OWNED BY forge_catalog_authority")
                    conn.execute("DROP ROLE forge_catalog_authority")


@contextmanager
def owned_enrollment_schema(*, fail_migration=False):
    """Add0013 only inside the owned cluster; preserve existing dirty fixture code."""
    with connect() as conn:
        if conn.execute("SELECT to_regclass('forge.owned_accounts')").fetchone()[0]:
            raise RuntimeError("Enrollment fixture requires absent schema")
        migration = (ROOT / 'migrations/0013_owned_account_enrollment.sql').read_text('utf-8')
        if not migration.endswith('COMMIT;\n'):
            raise RuntimeError('Unexpected enrollment migration boundary')
        applied = False
        try:
            if fail_migration:
                try:
                    conn.execute(migration[:-len('COMMIT;\n')]+'SELECT 1/0;\nCOMMIT;\n')
                except psycopg.errors.DivisionByZero:
                    conn.execute('ROLLBACK')
                else:
                    raise RuntimeError('Enrollment migration rollback not observed')
            else:
                conn.execute(migration)
                applied = True
            yield conn
        finally:
            if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                conn.execute('ROLLBACK')
            if applied:
                with conn.transaction():
                    # Only new enrolled identities are removed; original members remain.
                    created_accounts = [row[0] for row in conn.execute('SELECT id FROM forge.owned_accounts').fetchall()]
                    conn.execute('DELETE FROM forge.membership_roles WHERE (organization_id,membership_id) '
                        'IN (SELECT organization_id,membership_id FROM forge.membership_departments)')
                    conn.execute('DELETE FROM forge.membership_departments')
                    conn.execute('DELETE FROM forge.memberships WHERE identity_id IN (SELECT id FROM forge.owned_accounts)')
                    for table in ('account_enrollment_audit','membership_departments','account_invitations','owned_accounts','departments'):
                        conn.execute(sql.SQL('DROP TABLE forge.{}').format(sql.Identifier(table)))
                    conn.execute('DELETE FROM forge.identities WHERE id=ANY(%s::uuid[])', (created_accounts,))
                    for table in ('organizations','memberships','identities','membership_roles'):
                        for policy in ('enrollment_authority','enrollment_limit'):
                            conn.execute(sql.SQL('DROP POLICY {} ON forge.{}').format(
                                sql.Identifier(policy),sql.Identifier(table)))
                    for signature in (
                        'issue_account_invitation(uuid,uuid,text,text,text,uuid,uuid,uuid,text,text,text,integer)',
                        'revoke_account_invitation(uuid,uuid,text,text,text,uuid)',
                        'accept_account_invitation(uuid,text,uuid,text)',
                        'enrollment_lock_admin(uuid,uuid,text,text,text)', 'enrollment_uuid(text)',
                    ):
                        conn.execute('DROP FUNCTION forge.'+signature)
                    for role in ('forge_enrollment','forge_enrollment_authority'):
                        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@contextmanager
def owned_account_session_schema():
    """Own0013/0014 data and unwind their complete FK graph without baseline loss.

    Test credential rows may point at an existing baseline identity (administrator).
    The shared enrollment fixture assumes its remaining owned_accounts are newly
    enrolled identities. Remove only those test credential rows before handing
    control back, so the shared cleanup never deletes baseline members/identities.
    """
    identity_query = ('SELECT id,provider,issuer,subject,entra_tenant_id,entra_object_id '
                      'FROM forge.identities ORDER BY id')
    membership_query = ('SELECT organization_id,id,identity_id,status FROM '
                        'forge.memberships ORDER BY organization_id,id')
    role_query = ('SELECT organization_id,membership_id,role FROM '
                  'forge.membership_roles ORDER BY organization_id,membership_id,role')
    with connect() as observer:
        original_identities = observer.execute(identity_query).fetchall()
        original_memberships = observer.execute(membership_query).fetchall()
        original_roles = observer.execute(role_query).fetchall()
    original_identity_ids = [row[0] for row in original_identities]
    with owned_enrollment_schema() as conn:
        # These tables were just created by this fixture; no external enrollment
        # or invitation data can be adopted, removed or restored implicitly.
        for table in ('owned_accounts','account_invitations','account_enrollment_audit',
                      'membership_departments'):
            if conn.execute(sql.SQL('SELECT count(*) FROM forge.{}').format(
                    sql.Identifier(table))).fetchone()[0] != 0:
                raise RuntimeError('Account fixture requires empty owned enrollment tables')
        migration = (ROOT/'migrations/0014_owned_account_sessions.sql').read_text('utf-8')
        conn.execute(migration)
        try:
            yield conn
        finally:
            if conn.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                conn.execute('ROLLBACK')
            with conn.transaction():
                # Leaf0014 tables are entirely fixture-created. Retain all real
                # FK constraints and remove dependants in reverse dependency order.
                for table in ('account_message_delivery','account_password_resets',
                              'account_sessions','account_login_buckets'):
                    conn.execute(sql.SQL('DROP TABLE forge.{}').format(sql.Identifier(table)))
                invite_ids = [row[0] for row in conn.execute(
                    'SELECT id FROM forge.account_invitations').fetchall()]
                conn.execute('DELETE FROM forge.account_enrollment_audit '
                             'WHERE invitation_id=ANY(%s::uuid[])',(invite_ids,))
                conn.execute('DELETE FROM forge.account_invitations '
                             'WHERE id=ANY(%s::uuid[])',(invite_ids,))
                # Only new test credentials attached to original identities are
                # removed here. New enrollment credentials remain for shared cleanup.
                conn.execute('DELETE FROM forge.owned_accounts WHERE id=ANY(%s::uuid[])',
                             (original_identity_ids,))
                for identity,provider,issuer,subject,tenant,object_id in original_identities:
                    conn.execute('UPDATE forge.identities SET provider=%s,issuer=%s,'
                                 'subject=%s,entra_tenant_id=%s,entra_object_id=%s WHERE id=%s',
                                 (provider,issuer,subject,tenant,object_id,identity))
                for organization,member,identity,status in original_memberships:
                    conn.execute('UPDATE forge.memberships SET identity_id=%s,status=%s '
                                 'WHERE organization_id=%s AND id=%s',
                                 (identity,status,organization,member))
                signatures = conn.execute("SELECT p.oid::regprocedure::text FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge' "
                    "AND p.proname LIKE 'account_%'").fetchall()
                for signature, in signatures:
                    # Catalog-returned function signatures, never request input.
                    conn.execute('DROP FUNCTION '+signature)
                conn.execute('DROP POLICY account_identity_scope ON forge.owned_accounts')
                conn.execute('DROP OWNED BY forge_account_service')
                conn.execute('DROP ROLE forge_account_service')
    with connect() as observer:
        for query, expected in ((identity_query,original_identities),
                                (membership_query,original_memberships),
                                (role_query,original_roles)):
            if observer.execute(query).fetchall() != expected:
                raise RuntimeError('Account fixture failed to preserve baseline rows')
        if observer.execute("SELECT to_regclass('forge.owned_accounts')").fetchone()[0]:
            raise RuntimeError('Account fixture retained owned schema')


class AccountDatabaseFixture(DatabaseFixture):
    """Fresh owned accounts fixture, without unrelated baseline rollback probes.

    Only real0001–0004 migrations and runtime LOGIN provisioning are applied.
    Enrollment/session migrations remain scoped to each owned test context.
    Legacy DatabaseFixture and its rollback coverage are deliberately unchanged.
    """
    def __init__(self):
        wait_ready()
        self.runtime_password = secrets.token_urlsafe(32)
        with connect() as conn:
            if conn.execute("SELECT to_regnamespace('forge')").fetchone()[0]:
                raise RuntimeError("Account fixture requires a pristine owned database")
            for name in ('0001_bootstrap.sql', '0002_entra_identity_binding.sql',
                         '0003_membership_authorization.sql',
                         '0004_initial_admin_designation.sql'):
                conn.execute((ROOT / 'migrations' / name).read_text('utf-8'))
            conn.execute(sql.SQL('ALTER ROLE forge_runtime LOGIN PASSWORD {}').format(
                sql.Literal(self.runtime_password)))
            print('Owned accounts PostgreSQL server:',
                  conn.execute('SHOW server_version').fetchone()[0])
        self.reset()


@contextmanager
def owned_gateway_configuration_schema(*,fail_migration=False):
    """Opt-in0015 only; unwind its exact dependencies before shared account teardown."""
    with owned_account_session_schema() as admin:
        migration=(ROOT/'migrations/0015_gateway_configuration.sql').read_text('utf-8')
        if not migration.endswith('COMMIT;\n'):
            raise RuntimeError('Unexpected gateway migration boundary')
        if admin.execute("SELECT to_regclass('forge.organization_gateways')").fetchone()[0]:
            raise RuntimeError('Gateway fixture requires absent schema')
        applied=False
        try:
            if fail_migration:
                try:admin.execute(migration[:-len('COMMIT;\n')]+'SELECT 1/0;\nCOMMIT;\n')
                except psycopg.errors.DivisionByZero:admin.execute('ROLLBACK')
                else:raise RuntimeError('Gateway migration rollback not observed')
            else:
                admin.execute(migration);applied=True
            yield admin
        finally:
            if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                admin.execute('ROLLBACK')
            if applied:
                with admin.transaction():
                    admin.execute('DROP TABLE forge.gateway_configuration_audit')
                    admin.execute('DROP TABLE forge.organization_gateways')
                    for signature in ('gateway_read(text,uuid)',
                            'gateway_save(text,uuid,bigint,uuid,text)','gateway_lock_admin(text,uuid)',
                            'gateway_resolve_admin(uuid,uuid)'):
                        admin.execute('DROP FUNCTION forge.'+signature)
                    for role in ('forge_gateway_service','forge_gateway_authority'):
                        admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
                        admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


class GatewayCatalogDatabaseFixture(AccountDatabaseFixture):
    """Actual catalogue prerequisite migrations in a fresh owned cluster only."""
    def __init__(self):
        super().__init__()
        with connect() as admin:
            for name in ('0005_transactional_outbox.sql','0010_model_catalog_snapshots.sql',
                         '0011_model_catalog_publication.sql','0012_catalog_publication_authority.sql'):
                admin.execute((ROOT/'migrations'/name).read_text('utf-8'))


@contextmanager
def owned_gateway_catalog_schema():
    """Append0016 and unwind only its owned data/dependencies before0015 cleanup."""
    with owned_gateway_configuration_schema() as admin:
        tables=('gateway_catalog_selections','active_model_catalogs',
                'catalog_publication_operations','outbox_events','model_catalog_snapshots')
        if any(admin.execute(sql.SQL('SELECT count(*) FROM forge.{}').format(
                sql.Identifier(table))).fetchone()[0] for table in tables[1:]):
            raise RuntimeError('Owned catalogue fixture requires empty publication tables')
        version_check=admin.execute("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='forge.model_catalog_snapshots'::regclass AND contype='c' "
            "AND pg_get_constraintdef(oid) LIKE '%schema_version%'").fetchone()
        admin.execute((ROOT/'migrations/0016_owned_gateway_catalog.sql').read_text('utf-8'))
        try:
            yield admin
        finally:
            if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                admin.execute('ROLLBACK')
            with admin.transaction():
                for table in tables:
                    admin.execute(sql.SQL('DELETE FROM forge.{}').format(sql.Identifier(table)))
                admin.execute('DROP TABLE forge.gateway_catalog_selections')
                admin.execute('DROP TABLE forge.gateway_model_discoveries')
                signatures=admin.execute("SELECT p.oid::regprocedure::text FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge' "
                    "AND p.proname LIKE 'gateway_catalog_%'").fetchall()
                for signature, in signatures:
                    admin.execute('DROP FUNCTION '+signature)
                admin.execute('DROP FUNCTION forge.gateway_resolve_member(uuid,uuid)')
                for table in tables[1:]:
                    admin.execute(sql.SQL('DROP POLICY owned_catalog_scope ON forge.{}').format(sql.Identifier(table)))
                admin.execute('ALTER TABLE forge.catalog_publication_operations DROP CONSTRAINT owned_catalog_replay')
                admin.execute('ALTER TABLE forge.catalog_publication_operations DROP COLUMN gateway_revision, DROP COLUMN selection_sha256')
                admin.execute('ALTER TABLE forge.model_catalog_snapshots DROP CONSTRAINT catalog_payload_version')
                # Definition comes exclusively from the initial owned reviewed catalog.
                admin.execute(sql.SQL('ALTER TABLE forge.model_catalog_snapshots ADD CONSTRAINT {} ').format(
                    sql.Identifier(version_check[0])).as_string(admin)+version_check[1])

@contextmanager
def owned_gateway_inference_schema():
    """Actual0017, removed before its exact owned catalogue dependencies."""
    with owned_gateway_catalog_schema() as admin:
        admin.execute((ROOT/'migrations/0017_owned_gateway_inference.sql').read_text('utf-8'))
        try:
            yield admin
        finally:
            if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:
                admin.execute('ROLLBACK')
            admin.execute('DROP FUNCTION forge.gateway_inference_route(text,uuid,text)')

@contextmanager
def owned_gateway_catalog_admin_extension(admin,*,fail_migration=False):
    """Only nested in the owned0016 fixture; unwind0018 then0017 exactly."""
    if admin.execute("SELECT to_regprocedure('forge.gateway_inference_route(text,uuid,text)')").fetchone()[0]:
        raise RuntimeError('Owned status extension requires absent0017/0018')
    admin.execute((ROOT/'migrations/0017_owned_gateway_inference.sql').read_text('utf-8'))
    applied=False
    try:
        migration=(ROOT/'migrations/0018_gateway_catalog_admin_status.sql').read_text('utf-8')
        if not migration.endswith('COMMIT;\n'):raise RuntimeError('Unexpected status migration boundary')
        if fail_migration:
            try:admin.execute(migration[:-len('COMMIT;\n')]+'SELECT 1/0;\nCOMMIT;\n')
            except psycopg.errors.DivisionByZero:admin.execute('ROLLBACK')
            else:raise RuntimeError('Status rollback not observed')
        else:
            admin.execute(migration);applied=True
        yield admin
    finally:
        if admin.info.transaction_status is not psycopg.pq.TransactionStatus.IDLE:admin.execute('ROLLBACK')
        if applied:admin.execute('DROP FUNCTION forge.gateway_catalog_admin_status(text,uuid)')
        admin.execute('DROP FUNCTION forge.gateway_inference_route(text,uuid,text)')
