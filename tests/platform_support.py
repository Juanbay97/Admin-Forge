"""Owned-PostgreSQL fixtures shared by the platform tests: accounts with live sessions, a platform owner, raw calls.

Only for tests run through scripts/test-postgres.ps1. The owner is created the way the bootstrap does it (an owned
account plus a ``platform_roles`` row), here directly through the superuser connection of the throwaway database.
"""
from functools import lru_cache
from uuid import uuid4

from psycopg import errors

from forge.account_sessions import PostgresSessionStore, SessionService
from forge.accounts import ACCOUNT_ISSUER, PasswordHasher
from forge.invitations import capability_digest

PASSWORD = 'fixture-only-platform-passphrase'
OWNER_EMAIL = 'owner@platform.test'
PLATFORM_ROLES = ('forge_platform_authority', 'forge_platform_service')


@lru_cache(maxsize=1)
def password_hash():
    """One scrypt derivation per process: every fixture account shares the same password."""
    return PasswordHasher().hash(PASSWORD)


def add_account(admin, email, name='Fixture Account'):
    identity = uuid4()
    admin.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'forge',%s,%s)",
                  (identity, ACCOUNT_ISSUER, str(identity)))
    admin.execute('INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) VALUES(%s,%s,%s,%s)',
                  (identity, email, name, password_hash()))
    return identity


def add_owner(admin, email=OWNER_EMAIL, role='platform_owner'):
    account = add_account(admin, email, 'Platform Owner')
    admin.execute('INSERT INTO forge.platform_roles(account_id,role) VALUES(%s,%s)', (account, role))
    return account


def sign_in(db, email=OWNER_EMAIL, password=PASSWORD):
    """A password-only account session: (bearer capability, its digest)."""
    sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
    token = sessions.login(email, password).capability
    return token, capability_digest(token)


def call(db, text, params=(), role='forge_platform_service'):
    """One statement on the dedicated platform pool, exactly as the application connects."""
    with db.pool(role).connection() as connection:
        return connection.execute(text, params).fetchall()


def refusal(test, run):
    """The finite code of the P0001 exception that ``run`` must raise."""
    with test.assertRaises(errors.RaiseException) as caught:
        run()
    return caught.exception.diag.message_primary
