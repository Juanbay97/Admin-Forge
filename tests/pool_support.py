"""Owned-PostgreSQL fixture: give a company a platform gateway key through the real platform services.

Since 0034 a company administrator can no longer store a key, so every end-to-end test (and the supervised local stack)
configures a company the way production does: the platform owner creates a key, assigns it and sets the model ceiling.
"""
from cryptography.fernet import Fernet

from forge.gateway_configuration import GatewayCipher
from forge.gateway_keys import GatewayKeys
from forge.gateway_keys_store import PostgresGatewayKeyStore
from forge.gateway_origins import OriginPolicy
from mvp_support import seed_discovery
from platform_support import OWNER_EMAIL, add_owner, sign_in


def platform_keys(db, gateway_secret, origins):
    """A key service sharing the application's sealing key and allow-list, plus a verified owner session token."""
    secret = gateway_secret.encode() if isinstance(gateway_secret, str) else gateway_secret
    cipher = GatewayCipher(secret, policy=OriginPolicy(frozenset(origins), dev=True))
    if not db.admin.execute('SELECT 1 FROM forge.owned_accounts WHERE canonical_email=%s', (OWNER_EMAIL,)).fetchone():
        add_owner(db.admin)
    token, _ = sign_in(db, mfa=True)
    return GatewayKeys(PostgresGatewayKeyStore(db.pool('forge_platform_service')), cipher), token


def assign_key(db, gateway_secret, origin, organization_id, key, models, *, label=None, priority=1):
    """Create a pool key for ``origin``, assign it to the company, record the models its discovery would report and set the
    ceiling to them (the platform chooses a ceiling among discovered models, never free text); returns the key id."""
    keys, token = platform_keys(db, gateway_secret, (origin,))
    info = keys.create(token, label or 'key-%s' % str(organization_id)[:8], origin, key)
    keys.assign(token, organization_id, [(info.id, priority, True)])
    seed_discovery(db.admin, organization_id, models)
    keys.set_ceiling(token, organization_id, list(models))
    return info.id
