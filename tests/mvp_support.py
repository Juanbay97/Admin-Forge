"""Owned-harness fixture: a throwaway database holding the complete MVP schema (the full reviewed profile).

Only for tests run through scripts/test-postgres.ps1; the database and the cluster-global
roles it creates are removed on exit, and nothing outside the owned cluster is touched.
"""
from contextlib import ExitStack, contextmanager
import json
import secrets

from psycopg import sql
from psycopg_pool import ConnectionPool

from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import MVP_ADDITIONS
from postgres_support import connect, settings
from test_postgres_gateway_origin import migration_text, separate_database


def seed_discovery(admin, organization_id, models):
    """Record the discovery the platform owner's refresh would store for the company's current profile (superuser, no HTTP)."""
    admin.execute('INSERT INTO forge.gateway_model_discoveries(organization_id,gateway_revision,binding_id,model_ids) '
                  'SELECT organization_id,revision,binding_id,%s::jsonb FROM forge.organization_gateway_profiles WHERE organization_id=%s '
                  'ON CONFLICT(organization_id) DO UPDATE SET gateway_revision=excluded.gateway_revision,binding_id=excluded.binding_id,'
                  'model_ids=excluded.model_ids', (json.dumps(list(models)), organization_id))


def at(name):
    """Position of a migration in the profile, so tail pins never shift when a later migration is appended."""
    return MVP_ADDITIONS.index(name)


LOGIN_ROLES = ('forge_account_service', 'forge_enrollment', 'forge_runtime', 'forge_gateway_service',
               'forge_branding_service', 'forge_platform_service', 'forge_capability_service', 'forge_broker_service')


class MvpDatabase:
    def __init__(self, admin, stack):
        self.admin, self._stack = admin, stack
        # A deliberately older profile (e.g. without 0025) lacks the later roles; configure only those built.
        built = {row[0] for row in admin.execute('SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)', [list(LOGIN_ROLES)])}
        self.passwords = {role: secrets.token_urlsafe(32) for role in LOGIN_ROLES if role in built}
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
            for role in ('forge_directory_authority', 'forge_branding_authority', 'forge_branding_service',
                         'forge_platform_authority', 'forge_platform_service', 'forge_capability_authority', 'forge_capability_service', 'forge_broker_authority', 'forge_broker_service'):
                cleanup.execute('DROP ROLE IF EXISTS ' + role)
