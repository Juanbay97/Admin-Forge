"""Opt-in retained local gateway composition and recover-forward migration.

Never seed, adopt arbitrary data, auto-stop an active demo or learn trust at
runtime. The versioned SQL scripts each own BEGIN/COMMIT; journal checkpoints are
schema-only build artifacts authored from reviewed migration bytes on PG17.
"""
import hashlib
import secrets
from threading import Event
from forge.dev_accounts import ROOT,MIGRATIONS,FRONTEND_ORIGIN,LocalFixtureError

ADDITIONS=('0005_transactional_outbox.sql','0010_model_catalog_snapshots.sql',
    '0011_model_catalog_publication.sql','0012_catalog_publication_authority.sql',
    '0015_gateway_configuration.sql','0016_owned_gateway_catalog.sql',
    '0017_owned_gateway_inference.sql','0018_gateway_catalog_admin_status.sql')
LEGACY_PROFILE='0001-0005+0010-0017/PG17'
PROFILE='0001-0005+0010-0018/PG17'
# Static reviewed schema checkpoints, never runtime learned or journal supplied.
CHECKPOINTS=(
    '713d5fd1851f911ab12ec3dbb1a813b4ec3f549aa27940902b9881a1d50e297c',
    '2e7f77ccd986c34753cdcee97a778cfbde0d7393f94d358356f514dd3cc4706c',
    'ee2eba298fef4dc0be98d59a8305a066ba38fe2759357d1dbdd17fa4baef748d',
    '06c267c4735cc4e2934d23516dd05e421648b48c6959e595f61d1132fa21d065',
    '67bd60af952cb1cbc1793d3aec6751c48ffa2b399bdbfb2eb7a0b4ec7c25827f',
    '15c70eba60a3620a21afbfff4a34fb127e1ef4afd067a625836d4213d3fde2c3',
    '771721e4c57685611bbd3a456ee318fe0433c5f37c4130fe7c559ebfb67ced8c',
    '0544327eb3719aff43676332c84489fa759a71fe3fa10b38fbf36a99c1c52614',
    '0b2ca67e63355d71f94961c85675375d962abf438c859b22dadbfde269c9a16a',
)


def gateway_hashes():
    return {name:hashlib.sha256((ROOT/'migrations'/name).read_bytes()).hexdigest()
            for name in (*MIGRATIONS,*ADDITIONS)}


def gateway_hashes_v1():
    return {name:hashlib.sha256((ROOT/'migrations'/name).read_bytes()).hexdigest()
            for name in (*MIGRATIONS,*ADDITIONS[:-1])}


def is_gateway_state(state):
    return state['migration_hashes'] in (gateway_hashes_v1(),gateway_hashes())


def gateway_secrets(workspace):
    from cryptography.fernet import Fernet
    from forge.dev_accounts_persistent import CAPABILITY
    try:
        value=workspace.read('gateway-secrets.json')
    except FileNotFoundError:
        raise LocalFixtureError('GATEWAY_KEY_MISSING_RECOVERY_REFUSED') from None
    state=workspace.read('ownership.json')
    if (set(value)!={'version','instance_id','gateway_key','roles'}
            or value['version']!=1 or value['instance_id']!=state['instance_id']
            or type(value['roles']) is not dict or set(value['roles'])!={'forge_gateway_service'}
            or not CAPABILITY.fullmatch(value['roles']['forge_gateway_service'])):
        raise LocalFixtureError('INVALID_GATEWAY_PRIVATE_STATE')
    try:
        Fernet(value['gateway_key'].encode('ascii'))
    except Exception:
        raise LocalFixtureError('INVALID_GATEWAY_PRIVATE_STATE') from None
    if value['gateway_key']==workspace.read('runtime-secrets.json')['delivery_key']:
        raise LocalFixtureError('SEPARATE_GATEWAY_KEY_REQUIRED')
    return value


def _validated_v1(value,state):
    from forge.dev_accounts_persistent import migration_hashes
    expected={'version','instance_id','source_hashes','target_hashes','checkpoint','phase'}
    if (type(value) is not dict or set(value)!=expected or type(value['version']) is not int or value['version']!=1
            or value['instance_id']!=state['instance_id']
            or value['source_hashes']!=migration_hashes()
            or value['target_hashes']!=gateway_hashes_v1()
            or type(value['checkpoint']) is not int or not 0<=value['checkpoint']<=7
            or value['phase'] not in ('migrating','promoting','complete')
            or (value['phase']!='migrating' and value['checkpoint']!=7)):
        raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    return value


def validated_journal(workspace,state):
    from forge.dev_accounts_persistent import migration_hashes
    value=workspace.read('gateway-upgrade.json')
    if type(value) is not dict:
        raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    if type(value.get('version')) is not int:
        raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    if value.get('version')==1:
        return _validated_v1(value,state)
    expected={'version','instance_id','source_hashes','target_hashes','checkpoint','phase','previous'}
    if (set(value)!=expected or value['version']!=2
            or value['instance_id']!=state['instance_id']
            or value['source_hashes'] not in (migration_hashes(),gateway_hashes_v1())
            or value['target_hashes']!=gateway_hashes()
            or type(value['checkpoint']) is not int or not 0<=value['checkpoint']<=len(ADDITIONS)
            or value['phase'] not in ('migrating','promoting','complete')
            or (value['phase']!='migrating' and value['checkpoint']!=len(ADDITIONS))):
        raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    if value['previous'] is not None:
        _validated_v1(value['previous'],state)
        if value['checkpoint']<value['previous']['checkpoint']:
            raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    if value['source_hashes']==gateway_hashes_v1() and (
            value['checkpoint']<7 or value['previous'] is None or value['previous']['phase']!='complete'):
        raise LocalFixtureError('INVALID_GATEWAY_UPGRADE_JOURNAL')
    return value


def admit_resume(workspace,state):
    journal=workspace.directory/'gateway-upgrade.json'
    if is_gateway_state(state):
        if not journal.is_file():
            raise LocalFixtureError('EXPLICIT_GATEWAY_RECOVERY_REQUIRED')
        value=validated_journal(workspace,state)
        if value['phase']!='complete' or value['target_hashes']!=state['migration_hashes']:
            raise LocalFixtureError('EXPLICIT_GATEWAY_RECOVERY_REQUIRED')
        gateway_secrets(workspace)
    elif journal.exists():
        raise LocalFixtureError('EXPLICIT_GATEWAY_RECOVERY_REQUIRED')


def database_checkpoint(connection):
    from forge.account_readiness import catalog_fingerprint
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*)>=2 AND bool_and(NOT rolcanlogin) FROM pg_roles "
            "WHERE rolname IN ('forge_migrator','forge_enrollment_authority',"
            "'forge_gateway_authority','forge_catalog_authority')")
        if cursor.fetchone()!=(True,):
            raise LocalFixtureError('GATEWAY_AUTHORITY_PROFILE_MISMATCH')
        actual=catalog_fingerprint(cursor)
    if actual not in CHECKPOINTS or actual is None:
        raise LocalFixtureError('GATEWAY_SCHEMA_CHECKPOINT_MISMATCH')
    return CHECKPOINTS.index(actual)


def migrate_gateway(database,workspace,state,*,stopping=None,observe=None):
    """Only called under exact owned instance lock after a stopped-container check.

    observe is a local deterministic test failure hook, not a CLI/environment
    switch. Old ownership/secrets remain unchanged until atomic final promotion.
    """
    import psycopg
    from psycopg import sql
    from cryptography.fernet import Fernet
    from forge.dev_accounts_persistent import migration_hashes
    if None in CHECKPOINTS:
        raise LocalFixtureError('REVIEWED_GATEWAY_CHECKPOINTS_REQUIRED')
    stopping=stopping or Event()
    observe=observe or (lambda stage:None)
    path=workspace.directory/'gateway-upgrade.json'
    with psycopg.connect(**database.settings()) as connection:
        actual=database_checkpoint(connection)
        if path.exists():
            journal=validated_journal(workspace,state)
            if journal['phase']=='complete' and state['migration_hashes']!=journal['target_hashes']:
                raise LocalFixtureError('GATEWAY_SCHEMA_JOURNAL_MISMATCH')
            if actual<journal['checkpoint'] or actual>journal['checkpoint']+1:
                raise LocalFixtureError('GATEWAY_SCHEMA_JOURNAL_MISMATCH')
        else:
            if actual!=0 or is_gateway_state(state):
                raise LocalFixtureError('EXPLICIT_LEGACY_GATEWAY_SOURCE_REQUIRED')
            journal={'version':2,'instance_id':state['instance_id'],
                'source_hashes':migration_hashes(),'target_hashes':gateway_hashes(),
                'checkpoint':0,'phase':'migrating','previous':None}
            workspace.save('gateway-upgrade.json',journal)
        if journal['version']==1:
            # Preserve the validated0017 journal verbatim inside the new phase.
            # Explicit upgrade may recover an interrupted v1, never normal Resume.
            prior=dict(journal)
            source=state['migration_hashes'] if prior['phase']=='complete' else prior['source_hashes']
            journal={'version':2,'instance_id':state['instance_id'],'source_hashes':source,
                'target_hashes':gateway_hashes(),'checkpoint':actual,'phase':'migrating','previous':prior}
            workspace.save('gateway-upgrade.json',journal)
        key_file=workspace.directory/'gateway-secrets.json'
        if not key_file.exists():
            if actual!=0 or journal['checkpoint']!=0:
                raise LocalFixtureError('GATEWAY_KEY_MISSING_RECOVERY_REFUSED')
            # Persist once under inherited verified private ACL before first DB commit.
            workspace.save('gateway-secrets.json',{'version':1,'instance_id':state['instance_id'],
                'gateway_key':Fernet.generate_key().decode('ascii'),
                'roles':{'forge_gateway_service':secrets.token_urlsafe(32)}})
        secret=gateway_secrets(workspace)
        if journal['phase']=='complete':
            if actual!=len(ADDITIONS) or state['migration_hashes']!=journal['target_hashes']:
                raise LocalFixtureError('GATEWAY_SCHEMA_JOURNAL_MISMATCH')
            return
        # At most one commit can precede its journal update. Verify, never rerun it.
        journal['checkpoint']=actual
        workspace.save('gateway-upgrade.json',journal)
        for index in range(actual,len(ADDITIONS)):
            if stopping.is_set():
                raise LocalFixtureError('STOP_REQUESTED')
            observe('before_migration:'+str(index+1))
            connection.execute((ROOT/'migrations'/ADDITIONS[index]).read_text('utf-8'))
            observe('after_commit:'+str(index+1))
            if database_checkpoint(connection)!=index+1:
                raise LocalFixtureError('GATEWAY_SCHEMA_CHECKPOINT_MISMATCH')
            observe('before_journal:'+str(index+1))
            journal['checkpoint']=index+1
            workspace.save('gateway-upgrade.json',journal)
            observe('after_journal:'+str(index+1))
        # Only the new restricted service role is provisioned; old passwords untouched.
        with connection.transaction():
            connection.execute(sql.SQL('ALTER ROLE forge_gateway_service LOGIN PASSWORD {}').format(
                sql.Literal(secret['roles']['forge_gateway_service'])))
        observe('after_role_commit')
    legacy=workspace.read('runtime-secrets.json')
    pools=[]
    try:
        compose_gateway(database,workspace,legacy,pools,secret=secret,schema_profile=PROFILE)
    finally:
        for pool in reversed(pools):pool.close(timeout=5)
    journal['phase']='promoting'
    workspace.save('gateway-upgrade.json',journal)
    observe('before_context')
    context=workspace.read('context.json')
    context['schema_profile']=PROFILE
    context['central_gateway_available']=True
    workspace.save('context.json',context)
    observe('after_context')
    observe('before_manifest')
    upgraded=dict(state,migration_hashes=gateway_hashes())
    workspace.save('ownership.json',upgraded)
    observe('after_manifest')
    journal['phase']='complete'
    workspace.save('gateway-upgrade.json',journal)
    observe('complete')


def upgrade_gateway(directory,*,stopping=None):
    from forge.dev_accounts_persistent import (DurableWorkspace,RetainedPostgres,
        validated_state,validated_secrets)
    stopping=stopping or Event()
    workspace=DurableWorkspace(directory)
    database=None
    started=False
    try:
        workspace.acquire()  # A running API keeps this lock; no PID trust.
        state=validated_state(workspace)
        legacy=validated_secrets(workspace)
        database=RetainedPostgres(workspace,state,legacy['postgres_password'])
        if database.verify()['State']['Running']:
            raise LocalFixtureError('STOPPED_DURABLE_DEMO_REQUIRED')
        started=True
        database.start(stopping)
        migrate_gateway(database,workspace,state,stopping=stopping)
    finally:
        try:
            if started:database.close()
        finally:
            workspace.close()


def compose_gateway(database,workspace,legacy,pools,*,secret=None,schema_profile=None):
    """Explicit real central services; no ambient key or legacy readiness weakening."""
    from psycopg_pool import ConnectionPool
    from starlette.middleware.cors import CORSMiddleware
    from forge.account_api import create_account_app
    from forge.account_sessions import SessionService,PostgresSessionStore
    from forge.account_store import PostgresEnrollmentStore
    from forge.invitations import InvitationService
    from forge.invitation_store import PostgresInvitationStore
    from forge.invitation_delivery import DeliveryCoordinator,PostgresDeliveryStore,LocalTestMailbox
    from forge.postgres import PostgresBootstrapReader
    from forge.authorization_store import PostgresAuthorizationReader
    from forge.gateway_configuration import GatewayCipher,GatewayConfiguration
    from forge.gateway_configuration_store import PostgresGatewayStore
    from forge.gateway_catalog import GatewayCatalog
    from forge.gateway_catalog_store import PostgresGatewayCatalogStore
    from forge.gateway_catalog_adapter import HttpxModelsAdapter
    from forge.gateway_inference import GatewayInference
    from forge.gateway_inference_store import PostgresGatewayInferenceStore
    from forge.gateway_inference_adapter import HttpxTextAdapter
    from forge.gateway_inference_readiness import GatewayInferenceReadiness
    from forge.gateway_catalog_admin_readiness import GatewayCatalogAdminReadiness
    if schema_profile is None:
        hashes=workspace.read('ownership.json')['migration_hashes']
        schema_profile=LEGACY_PROFILE if hashes==gateway_hashes_v1() else PROFILE if hashes==gateway_hashes() else None
    if schema_profile not in (LEGACY_PROFILE,PROFILE):
        raise LocalFixtureError('GATEWAY_SCHEMA_PROFILE_MISMATCH')
    secret=secret or gateway_secrets(workspace)
    roles=dict(legacy['roles'],**secret['roles'])
    owned=[]
    for role in ('forge_account_service','forge_enrollment','forge_runtime','forge_gateway_service'):
        pool=ConnectionPool('',kwargs=dict(database.settings(),user=role,password=roles[role]),
            min_size=1,max_size=2,timeout=1,max_waiting=4,reconnect_timeout=1,open=False)
        pools.append(pool);owned.append(pool)
        pool.open(wait=True,timeout=5)
    accounts,enrollment,bootstrap,gateway=owned
    readiness_type=GatewayInferenceReadiness if schema_profile==LEGACY_PROFILE else GatewayCatalogAdminReadiness
    ready=readiness_type(accounts,bootstrap,gateway)
    if not ready.check():
        raise LocalFixtureError('GATEWAY_SCHEMA_ATTESTATION_FAILED')
    cipher=GatewayCipher(secret['gateway_key'].encode('ascii'))
    mailbox=workspace.directory/'mailbox'
    if not mailbox.is_dir():
        raise LocalFixtureError('RETAINED_MAILBOX_REQUIRED')
    app=create_account_app(sessions=SessionService(PostgresSessionStore(accounts)),
        invitations=InvitationService(PostgresInvitationStore(enrollment),PostgresEnrollmentStore(enrollment)),
        delivery=DeliveryCoordinator(PostgresDeliveryStore(accounts),
            LocalTestMailbox(mailbox,sender='forge@local.test'),origin=FRONTEND_ORIGIN,
            encryption_key=legacy['delivery_key'].encode('ascii')),
        bootstrap_reader=PostgresBootstrapReader(bootstrap),
        authorization_reader=PostgresAuthorizationReader(bootstrap),readiness=ready,
        gateway_configuration=GatewayConfiguration(PostgresGatewayStore(gateway),cipher),
        gateway_catalog=GatewayCatalog(PostgresGatewayCatalogStore(gateway),cipher,HttpxModelsAdapter()),
        gateway_inference=GatewayInference(PostgresGatewayInferenceStore(gateway),cipher,HttpxTextAdapter()))
    app.add_middleware(CORSMiddleware,allow_origins=[FRONTEND_ORIGIN],
        allow_methods=['GET','POST','PUT','OPTIONS'],allow_headers=['Authorization','Content-Type'],
        allow_credentials=False)
    return app
