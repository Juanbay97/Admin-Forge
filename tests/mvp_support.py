"""Owned-harness fixture: a throwaway database holding the complete MVP schema (0001-0023).

Only for tests run through scripts/test-postgres.ps1; the database and the cluster-global
roles it creates are removed on exit, and nothing outside the owned cluster is touched.
"""
from contextlib import ExitStack, contextmanager
import secrets

from psycopg import sql
from psycopg_pool import ConnectionPool

from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import MVP_ADDITIONS
from postgres_support import connect, settings
from test_postgres_gateway_origin import migration_text, separate_database

LOGIN_ROLES = ('forge_account_service', 'forge_enrollment', 'forge_runtime', 'forge_gateway_service',
               'forge_branding_service')


class MvpDatabase:
    def __init__(self, admin, stack):
        self.admin, self._stack = admin, stack
        self.passwords = {role: secrets.token_urlsafe(32) for role in LOGIN_ROLES}
        self._pools = {}
        for role, password in self.passwords.items():
            admin.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))

    def connection_settings(self, **change):
        return {**settings(), 'dbname': self.admin.info.dbname, **change}

    def pool(self, role):
        if role not in self._pools:
            pool = ConnectionPool('', kwargs=self.connection_settings(user=role, password=self.passwords[role]),
                                  min_size=1, max_size=4, timeout=2, open=False)
            self._stack.callback(pool.close, timeout=5)
            pool.open(wait=True, timeout=5)
            self._pools[role] = pool
        return self._pools[role]


@contextmanager
def mvp_database(*, migrations=(*MIGRATIONS, *MVP_ADDITIONS)):
    try:
        with separate_database() as admin:
            for name in migrations:
                admin.execute(migration_text(name))
            with ExitStack() as stack:
                yield MvpDatabase(admin, stack)
    finally:
        # Not in separate_database's list; created by 0020/0025 and cluster-global.
        with connect() as cleanup:
            for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service'):
                cleanup.execute('DROP ROLE IF EXISTS ' + role)
