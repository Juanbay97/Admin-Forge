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
        with connect() as admin:
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
            conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA forge TO forge_test_writer')
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
