"""Wiring shared by the dev (``forge.mvp_local``) and production (``forge.serve_prod``) profiles.

Only the profile-independent part lives here: five independent restricted pools, the schema
attestation that must pass before anything is served, and the account/branding/gateway
application over them. Everything profile-specific stays with the profile: how settings are
obtained, which delivery channel and onboarding origin are used, and the status route, admin
mount and host guard around the returned application.
"""
from typing import NamedTuple

from forge.mvp_local import ConfigError, ROLES


class RolePools(NamedTuple):
    accounts: object
    enrollment: object
    bootstrap: object
    gateway: object
    branding: object


def open_pools(settings_for, owned, *, pool_factory=None):
    """Open one bounded pool per service role, in ``ROLES`` order.

    Every pool is appended to ``owned`` as soon as it exists, so a failure part-way still leaves
    the caller holding everything it must close.
    """
    if pool_factory is None:
        from psycopg_pool import ConnectionPool as pool_factory
    created = []
    for role in ROLES:
        pool = pool_factory('', kwargs=settings_for(role), min_size=1, max_size=2, timeout=1, max_waiting=4,
                            reconnect_timeout=1, open=False)
        owned.append(pool)
        created.append(pool)
        pool.open(wait=True, timeout=5)
    return RolePools(*created)


def attest(pools, *, readiness_factory=None):
    """The reviewed schema profile must be attested before anything is served."""
    if readiness_factory is None:
        from forge.mvp_readiness import MvpReadiness as readiness_factory
    readiness = readiness_factory(pools.accounts, pools.bootstrap, pools.gateway)
    if not readiness.check():
        raise ConfigError('SCHEMA_ATTESTATION_FAILED')
    return readiness


def build_app(pools, *, readiness, delivery_adapter, onboarding_origin, delivery_key, gateway_key, gateway_policy):
    from forge.account_api import create_account_app
    from forge.account_sessions import PostgresSessionStore, SessionService
    from forge.account_store import PostgresEnrollmentStore
    from forge.authorization_store import PostgresAuthorizationReader
    from forge.branding_api import mount_branding
    from forge.branding_store import PostgresBrandingStore
    from forge.directory import DirectoryService
    from forge.directory_store import PostgresDirectoryStore
    from forge.gateway_catalog import GatewayCatalog
    from forge.gateway_catalog_adapter import HttpxModelsAdapter
    from forge.gateway_catalog_store import PostgresGatewayCatalogStore
    from forge.gateway_configuration import GatewayCipher, GatewayConfiguration
    from forge.gateway_configuration_store import PostgresGatewayStore
    from forge.gateway_inference import GatewayInference
    from forge.gateway_inference_adapter import HttpxTextAdapter
    from forge.gateway_inference_store import PostgresGatewayInferenceStore
    from forge.invitation_delivery import DeliveryCoordinator, PostgresDeliveryStore
    from forge.invitation_store import PostgresInvitationStore
    from forge.invitations import InvitationService
    from forge.postgres import PostgresBootstrapReader
    accounts, enrollment, bootstrap, gateway, branding = pools
    cipher = GatewayCipher(gateway_key, policy=gateway_policy)
    sessions = SessionService(PostgresSessionStore(accounts))
    app = create_account_app(
        sessions=sessions,
        invitations=InvitationService(PostgresInvitationStore(enrollment), PostgresEnrollmentStore(enrollment)),
        delivery=DeliveryCoordinator(PostgresDeliveryStore(accounts), delivery_adapter,
                                     origin=onboarding_origin, encryption_key=delivery_key),
        bootstrap_reader=PostgresBootstrapReader(bootstrap), authorization_reader=PostgresAuthorizationReader(bootstrap),
        readiness=readiness, gateway_configuration=GatewayConfiguration(PostgresGatewayStore(gateway), cipher),
        gateway_catalog=GatewayCatalog(PostgresGatewayCatalogStore(gateway), cipher, HttpxModelsAdapter(policy=gateway_policy)),
        gateway_inference=GatewayInference(PostgresGatewayInferenceStore(gateway), cipher, HttpxTextAdapter(policy=gateway_policy)),
        directory=DirectoryService(PostgresDirectoryStore(gateway)))
    mount_branding(app, store=PostgresBrandingStore(gateway, branding), sessions=sessions, readiness=readiness)
    return app
