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


class DatabaseFixture:
    def __init__(self):
        wait_ready()
        self.runtime_password = secrets.token_urlsafe(32)
        self.writer_password = secrets.token_urlsafe(32)
        with connect() as conn:
            conn.execute((ROOT / 'migrations/0001_bootstrap.sql').read_text('utf-8'))
            # The harness alone provisions LOGIN and a restricted policy-test writer.
            conn.execute(sql.SQL('ALTER ROLE forge_runtime LOGIN PASSWORD {}').format(
                sql.Literal(self.runtime_password)))
            conn.execute(sql.SQL('CREATE ROLE forge_test_writer LOGIN PASSWORD {} '
                'NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION').format(
                sql.Literal(self.writer_password)))
            conn.execute('GRANT CONNECT ON DATABASE forge_test TO forge_test_writer')
            conn.execute('GRANT USAGE ON SCHEMA forge TO forge_test_writer')
            conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA forge TO forge_test_writer')
            conn.execute('GRANT INSERT, UPDATE, DELETE ON forge.configuration_revisions '
                         'TO forge_test_writer')
            conn.execute('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA forge TO forge_test_writer')
            version = conn.execute('SHOW server_version').fetchone()[0]
            print('Real PostgreSQL server:', version)
        self.reset()

    def runtime(self):
        return connect('forge_runtime', self.runtime_password)

    def writer(self):
        return connect('forge_test_writer', self.writer_password)

    def reset(self):
        with connect() as conn, conn.transaction():
            conn.execute('TRUNCATE forge.organizations, forge.identities CASCADE')
            for identity, subject in ((ALICE, 'alice'), (BOB, 'bob'), (CAROL, 'carol'),
                                      (SUSPENDED, 'suspended'), (ARCHIVED, 'archived')):
                conn.execute('INSERT INTO forge.identities VALUES (%s,%s,%s,%s)',
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
