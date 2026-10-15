"""Wiring shared by the dev (``forge.mvp_local``) and production (``forge.serve_prod``) profiles.

Only the profile-independent part lives here: eight independent restricted pools, the schema
attestation that must pass before anything is served, and the account/branding/gateway
application over them. Everything profile-specific stays with the profile: how settings are
obtained, which delivery channel and onboarding origin are used, and the status route, admin
mount and host guard around the returned application.
"""
from pathlib import Path
from typing import NamedTuple

from fastapi.responses import JSONResponse

from forge.mvp_local import ConfigError, ROLES
from forge.mvp_profile import MVP_PROFILE


class RolePools(NamedTuple):
    accounts: object
    enrollment: object
    bootstrap: object
    gateway: object
    branding: object
    platform: object
    capability: object
    broker: object


# Two connections per role and a one second wait, as before. What changed is how many callers may wait: a burst of members
# (several workspaces opening or prompts sent at once) used to be refused at once beyond four waiters. A transaction takes tens of
# milliseconds, so this queue drains well inside the one second timeout, which still bounds every wait.
BURST_QUEUE = 32


def open_pools(settings_for, owned, *, pool_factory=None):
    """Open one bounded pool per service role, in ``ROLES`` order.

    Every pool is appended to ``owned`` as soon as it exists, so a failure part-way still leaves
    the caller holding everything it must close.
    """
    if pool_factory is None:
        from psycopg_pool import ConnectionPool as pool_factory
    created = []
    for role in ROLES:
        pool = pool_factory('', kwargs=settings_for(role), min_size=1, max_size=2, timeout=1, max_waiting=BURST_QUEUE,
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


def add_status(app, readiness, admin_dir):
    """``/status``: schema-attested readiness (503 when not ready) and whether the admin build exists."""
    built = (Path(admin_dir)/'index.html').is_file()

    @app.get('/status', include_in_schema=False)
    def status():
        ready = readiness.check()
        return JSONResponse({'status': 'ready' if ready else 'not_ready', 'profile': MVP_PROFILE,
                             'admin': 'ready' if built else 'missing'},
                            status_code=200 if ready else 503, headers={'Cache-Control': 'no-store'})


def build_app(pools, *, readiness, delivery_adapter, onboarding_origin, delivery_key, gateway_key, platform_key,
              gateway_policy, gateway_ca_file=None, policy_key=None, connector_key=None, connector_fixtures=None, public_origin=None, policy_retired_keys=(), policy_rotations=()):
    import ssl
    from forge.account_api import create_account_app
    from forge.account_sessions import PostgresSessionStore, SessionService
    from forge.account_store import PostgresEnrollmentStore
    from forge.authorization_store import PostgresAuthorizationReader
    from forge.branding_api import mount_branding
    from forge.branding_store import PostgresBrandingStore
    from forge.capability_api import mount_client_attestation, mount_company_capabilities, mount_effective, mount_invocation_audit
    from forge.capability_attestation import AttestationReports
    from forge.capability_audit import InvocationLog
    from forge.capability_effective import EffectivePolicy
    from forge.capability_installer import InstallerConfig
    from forge.capability_signing import load_signer
    from forge.connector_api import mount_connectors
    from forge.connector_cipher import ConnectorCipher
    from forge.connector_oauth import ConnectorOAuth
    from forge.connector_service import Connectors
    from forge.connector_store import PostgresConnectorStore
    from forge.egress_guard import EgressGuard, GuardedClient
    from forge.mcp_broker import McpBroker
    from forge.capability_service import Capabilities
    from forge.capability_store import PostgresCapabilityStore
    from forge.directory import DirectoryDenied, DirectoryService, DirectorySuspended
    from forge.directory_api import mount_member_department
    from forge.directory_store import PostgresDirectoryStore
    from forge.gateway_catalog import GatewayCatalog
    from forge.gateway_catalog_adapter import HttpxModelsAdapter
    from forge.gateway_configuration import GatewayCipher
    from forge.gateway_inference import GatewayInference
    from forge.gateway_inference_adapter import HttpxTextAdapter
    from forge.gateway_pool_store import (PoolGatewayConfiguration, PostgresPoolCatalogStore, PostgresPoolInferenceStore,
                                          PostgresPoolStatusStore)
    from forge.gateway_keys import GatewayKeys
    from forge.gateway_keys_store import PostgresGatewayKeyStore
    from forge.usage_api import mount_company_usage
    from forge.usage_company import CompanyUsage
    from forge.usage_company_store import PostgresCompanyUsageStore
    from forge.usage_platform import PlatformUsage
    from forge.usage_platform_store import PostgresPlatformUsageStore
    from forge.usage_store import PostgresUsageStore
    from forge.invitation_delivery import DeliveryCoordinator, PostgresDeliveryStore
    from forge.invitation_store import PostgresInvitationStore
    from forge.invitations import InvitationService, capability_digest
    from forge.platform import PlatformService
    from forge.platform_catalog import PlatformCatalog
    from forge.platform_catalog_store import PostgresPlatformCatalogStore
    from forge.platform_api import mount_platform
    from forge.platform_reads import PlatformReads
    from forge.platform_reads_store import PostgresPlatformReadsStore
    from forge.platform_store import PostgresPlatformStore
    from forge.platform_totp import SecretSealer
    from forge.postgres import PostgresBootstrapReader
    accounts, enrollment, bootstrap, gateway, branding, platform, capability, broker = pools  # capability: mounted by the capability API
    verify = ssl.create_default_context(cafile=gateway_ca_file) if gateway_ca_file else True  # a private gateway CA, else the system store
    cipher = GatewayCipher(gateway_key, policy=gateway_policy)
    sessions = SessionService(PostgresSessionStore(accounts))
    branding_store = PostgresBrandingStore(gateway, branding)
    directory = DirectoryService(PostgresDirectoryStore(gateway))
    delivery = DeliveryCoordinator(PostgresDeliveryStore(accounts), delivery_adapter, origin=onboarding_origin,
                                   encryption_key=delivery_key)  # one coordinator: member invitations, resets and first admins
    app = create_account_app(
        sessions=sessions,
        invitations=InvitationService(PostgresInvitationStore(enrollment), PostgresEnrollmentStore(enrollment)),
        delivery=delivery,
        bootstrap_reader=PostgresBootstrapReader(bootstrap), authorization_reader=PostgresAuthorizationReader(bootstrap),
        readiness=readiness, gateway_configuration=PoolGatewayConfiguration(PostgresPoolStatusStore(gateway), gateway_policy.allowed),
        gateway_catalog=GatewayCatalog(PostgresPoolCatalogStore(gateway), cipher, HttpxModelsAdapter(policy=gateway_policy, verify=verify)),
        gateway_inference=GatewayInference(PostgresPoolInferenceStore(gateway), cipher, HttpxTextAdapter(policy=gateway_policy, verify=verify),
                                           usage=PostgresUsageStore(gateway)),
        directory=directory, company_code=lambda token, organization: branding_store.read(capability_digest(token), organization).code)
    mount_member_department(app, directory=directory, sessions=sessions, readiness=readiness)
    mount_branding(app, store=branding_store, sessions=sessions, readiness=readiness)
    capabilities = Capabilities(PostgresCapabilityStore(capability))
    # The connector broker: its own sealing key, its own pool, its own egress guard. Without the key every connector route answers 503.
    connectors = oauth = broker_proxy = None
    if connector_key is not None:
        if public_origin is None:
            raise ConfigError('CONFIG_INVALID:public_origin')
        connector_store = PostgresConnectorStore(broker)
        if not connector_store.ready():
            raise ConfigError('CONNECTOR_BROKER_UNAVAILABLE')  # fail closed: never serve a broker whose role cannot be attested
        connector_cipher = ConnectorCipher(connector_key, distinct_from=[delivery_key, gateway_key, platform_key, *([policy_key] if policy_key else [])])
        guarded_client = GuardedClient(EgressGuard(fixtures=connector_fixtures))
        connectors = Connectors(connector_store, connector_cipher)
        oauth = ConnectorOAuth(connector_store, connector_cipher, guarded_client, public_origin=public_origin)
        broker_proxy = McpBroker(connector_store, oauth, connector_cipher, guarded_client)
    mount_platform(app, service=PlatformService(PostgresPlatformStore(platform), SecretSealer(platform_key), delivery=delivery),
                   sessions=sessions, readiness=readiness, keys=GatewayKeys(PostgresGatewayKeyStore(platform), cipher),
                   usage=PlatformUsage(PostgresPlatformUsageStore(platform)), capabilities=capabilities, connectors=connectors,
                   reads=PlatformReads(PostgresPlatformReadsStore(platform)),
                   catalog=PlatformCatalog(PostgresPlatformCatalogStore(platform), cipher, HttpxModelsAdapter(policy=gateway_policy, verify=verify)))
    mount_company_capabilities(app, capabilities=capabilities, sessions=sessions, readiness=readiness)
    signer = None if policy_key is None else load_signer(policy_key, retired=policy_retired_keys, rotations=policy_rotations)  # absent: the effective-policy routes answer 503
    def companies(token):
        try:
            return [item.id for item in directory.me(token).organizations if item.status == 'active']
        except (DirectoryDenied, DirectorySuspended):
            return []  # a stale, suspended or unknown member has no company: the route answers the same 404
    effective = EffectivePolicy(PostgresCapabilityStore(capability), signer)
    # The per-company installer configuration needs the public origin the desktop client will talk to; without it the route is not mounted.
    installer = None if public_origin is None else InstallerConfig(effective, public_origin, lambda token, organization: branding_store.read(capability_digest(token), organization).code)
    mount_effective(app, policy=effective, sessions=sessions, readiness=readiness, organizations=companies, installer=installer)
    mount_invocation_audit(app, log=InvocationLog(PostgresCapabilityStore(capability)), sessions=sessions, readiness=readiness, organizations=companies)
    mount_client_attestation(app, reports=AttestationReports(PostgresCapabilityStore(capability)), sessions=sessions, readiness=readiness, organizations=companies)
    mount_connectors(app, service=connectors, oauth=oauth, broker=broker_proxy, sessions=sessions, readiness=readiness, organizations=companies)
    mount_company_usage(app, usage=CompanyUsage(PostgresCompanyUsageStore(gateway)), sessions=sessions,
                        authorization_reader=PostgresAuthorizationReader(bootstrap), readiness=readiness)
    return app
