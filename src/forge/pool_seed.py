"""Operator seeding of the platform key pool for the supervised local stack.

The production path is the platform API (an owner with a verified second factor). The local stack has no owner session, so,
like the provisioning that created the companies, this trusted operator step writes the same rows directly: a key sealed in
the v2 format, one assignment per company, and the model ceiling. Nothing here is reachable from the application.
"""
from uuid import uuid4

from forge.gateway_configuration import GatewayCipher
from forge.gateway_origins import OriginPolicy


def seed_gateway_pool(connection, gateway_secret, origin, results, models):
    """Give every provisioned company that was issued a gateway key a pool key for ``origin``, priority 1, with ``models`` as ceiling."""
    cipher = GatewayCipher(gateway_secret, policy=OriginPolicy(frozenset({origin}), dev=True))
    models = list(models)
    seeded = []
    with connection.transaction():
        for result in results:
            if not result.gateway_key:
                continue
            key_id = uuid4()
            connection.execute('INSERT INTO forge.gateway_keys(id,label,origin,encrypted_key,last4) VALUES(%s,%s,%s,%s,%s)',
                               (key_id, 'seed-' + str(result.organization_id)[:8], origin,
                                cipher.seal_pooled(key_id, 1, result.gateway_key, origin), result.gateway_key[-4:]))
            connection.execute('INSERT INTO forge.organization_gateway_profiles(organization_id,revision,binding_id,ceiling) '
                               'VALUES(%s,1,gen_random_uuid(),%s)', (result.organization_id, models))
            connection.execute('INSERT INTO forge.organization_gateway_keys(organization_id,key_id,priority,active) VALUES(%s,%s,1,true)',
                               (result.organization_id, key_id))
            seeded.append((result.organization_id, key_id))
    return seeded
