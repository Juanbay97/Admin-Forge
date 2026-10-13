"""Owned-PostgreSQL fixtures for the governance tests: the capability service role, a seeded catalog, platform and company sessions.

Only for tests run through scripts/test-postgres.ps1. Until the profile's composition passwords the capability role (the 7th pool)
the fixture enables it itself, the way an operator would.
"""
import json
import secrets

import psycopg
from psycopg import errors, sql

from platform_support import OWNER_EMAIL, add_owner, sign_in
from forge.provisioning import SEED, provision

ROLE = 'forge_capability_service'


class CapabilityRole:
    """Raw statements on the dedicated capability role, exactly as the application connects (no table privilege at all)."""

    def __init__(self, db, role=ROLE):
        self.db = db
        if role in db.passwords:
            self.pool = db.pool(role)
            self.settings = None
        else:
            password = secrets.token_urlsafe(24)
            db.admin.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
            self.pool = None
            self.settings = db.connection_settings(user=role, password=password)

    def call(self, text, params=()):
        if self.pool is not None:
            with self.pool.connection() as connection:
                return connection.execute(text, params).fetchall()
        with psycopg.connect(**self.settings) as connection:
            return connection.execute(text, params).fetchall()

    def refusal(self, text, params=()):
        """The finite code of the P0001 exception the statement must raise."""
        try:
            self.call(text, params)
        except errors.RaiseException as caught:
            return caught.diag.message_primary
        raise AssertionError('expected a finite refusal')


def entry(**change):
    """A catalog entry document with sensible defaults (a base skill)."""
    document = {'version': '1.0.0', 'risk': 'low', 'is_base': True, 'default_state': 'on', 'min_sandbox_level': 0,
                'manifest_sha256': None, 'credential_locus': 'server', 'declared_permissions': [], 'granted_permissions': [],
                'attributes': {}}
    document.update(change)
    return json.dumps(document)


class GovernanceWorld:
    """Two provisioned companies, a verified platform owner and signed-in administrators and members."""

    def build(self, db):
        self.db = db
        self.role = CapabilityRole(db)
        self.broker = CapabilityRole(db, 'forge_broker_service')
        results = provision(db.admin, SEED, lambda created: None)
        self.org_a, self.org_b = results[0].organization_id, results[1].organization_id
        self.admin_a, self.member_a = results[0].accounts[0], results[0].accounts[1]
        self.admin_b, self.member_b = results[1].accounts[0], results[1].accounts[1]
        if not db.admin.execute('SELECT 1 FROM forge.owned_accounts WHERE canonical_email=%s', (OWNER_EMAIL,)).fetchone():
            add_owner(db.admin)
        self.owner = sign_in(db, mfa=True)[1]
        self.owner_password_only = sign_in(db)[1]
        self.digest = {name: sign_in(db, getattr(self, name).email, getattr(self, name).password)[1]
                       for name in ('admin_a', 'member_a', 'admin_b', 'member_b')}

    def put(self, identifier, expected=0, **change):
        return self.role.call('SELECT * FROM forge.cap_catalog_put(%s,%s,%s,%s::jsonb)', (self.owner, identifier, expected, entry(**change)))

    def epochs(self, org):
        platform = self.db.admin.execute('SELECT epoch FROM forge.capability_platform_epoch').fetchone()[0]
        company = self.db.admin.execute('SELECT epoch FROM forge.capability_org_epochs WHERE organization_id=%s', (org,)).fetchone()
        return platform, company[0] if company else 1

    def audit_count(self):
        return self.db.admin.execute('SELECT count(*) FROM forge.capability_change_audit').fetchone()[0]

    def layers(self, digest, org, function='cap_read_layers'):
        rows = self.role.call('SELECT * FROM forge.%s(%%s,%%s)' % function, (digest, org))
        names = ('id', 'kind', 'version', 'risk', 'is_base', 'default_state', 'min_sandbox_level', 'manifest_sha256', 'credential_locus',
                 'declared_permissions', 'granted_permissions', 'platform_state', 'platform_lock', 'company_state', 'company_lock',
                 'org_enabled', 'platform_epoch', 'org_epoch')
        return [dict(zip(names, row)) for row in rows]
