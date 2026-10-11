"""Owned PG17 upgrade preservation and recover-forward journal; no providers."""
from pathlib import Path
import hashlib
import json
import sys
import unittest
from threading import Event
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from postgres_support import settings,wait_ready
import psycopg
from fastapi.testclient import TestClient
from forge.dev_accounts import install_and_seed,compose,FRONTEND_ORIGIN
from forge.dev_accounts_persistent import DurableWorkspace,DEMOS_ROOT,migration_hashes,KIND
from forge.dev_accounts_gateway import (ADDITIONS,CHECKPOINTS,migrate_gateway,compose_gateway,
    gateway_secrets,gateway_hashes,gateway_hashes_v1,admit_resume,database_checkpoint)
from forge.account_readiness import catalog_fingerprint
from forge.invitations import capability_digest

class PostgresGatewayUpgradeTests(unittest.TestCase):
    def test_reviewed_checkpoint_upgrade_preserves_accounts_and_recovers(self):
        # The harness owns container startup; direct tests must await its actual
        # bounded database readiness just like AccountDatabaseFixture does.
        wait_ready()
        identifier=uuid4()
        workspace=DurableWorkspace(DEMOS_ROOT/('forge-owned-accounts-'+identifier.hex),create=True)
        workspace.acquire()
        class Database:
            def settings(self):return settings()
        database=Database()
        state=dict(version=1,kind=KIND,instance_id=str(identifier),directory=str(workspace.directory),
            repository=str(ROOT),image=(ROOT/'scripts/postgres-image.txt').read_text('ascii').strip(),
            migration_hashes=migration_hashes(),container_name='forge-durable-accounts-'+identifier.hex,
            container_id='a'*64,volume_name='forge-durable-accounts-data-'+identifier.hex,phase='ready')
        pools=[]
        try:
            from cryptography.fernet import Fernet
            roles=install_and_seed(database,workspace,Event())
            legacy={'postgres_password':'A'*43,'roles':roles,'delivery_key':Fernet.generate_key().decode('ascii')}
            workspace.save('runtime-secrets.json',legacy)
            workspace.save('ownership.json',state)
            # Capture only reviewed pristine schema. This branch never blesses runtime state.
            if None in CHECKPOINTS:
                with psycopg.connect(**settings()) as connection:
                    actual=[]
                    with connection.cursor() as cursor:actual.append(catalog_fingerprint(cursor))
                    for migration in ADDITIONS:
                        connection.execute((ROOT/'migrations'/migration).read_text('utf-8'))
                        with connection.cursor() as cursor:actual.append(catalog_fingerprint(cursor))
                    print('Reviewed PG17 upgrade checkpoint build artifact:',json.dumps(actual))
                self.fail('Static reviewed checkpoint artifact not yet authored.')
            app=compose(database,workspace,roles,pools,delivery_key=legacy['delivery_key'].encode('ascii'))
            credentials=workspace.read('admin-credentials.json')
            def login(client,credentials):
                result=client.post('/forge/v1/accounts/login',json=credentials)
                self.assertEqual(result.status_code,200)
                return result.json()['access_token']
            with TestClient(app,raise_server_exceptions=False) as client:
                admin_token=login(client,credentials)
                context=workspace.read('context.json')
                bootstrap='/forge/v1/bootstrap?organization_id='+context['organization_id']
                admin_id=client.get(bootstrap,headers={'Authorization':'Bearer '+admin_token}).json()['membership']['id']
                response=client.post('/forge/v1/accounts/invitations',
                    headers={'Authorization':'Bearer '+admin_token},json={
                    'organization_id':context['organization_id'],'department_id':context['department_id'],
                    'email':'preserved@forge.local.test','name':'Preserved recipient'})
                self.assertEqual(response.status_code,201)
                from email import policy
                from email.parser import BytesParser
                from urllib.parse import urlsplit,parse_qs
                letter=BytesParser(policy=policy.default).parsebytes(next((workspace.directory/'mailbox').glob('*.eml')).read_bytes())
                text=letter.get_body(preferencelist=('plain',)).get_content()
                link=next(line for line in text.splitlines() if line.startswith(FRONTEND_ORIGIN+'/onboarding#'))
                token=parse_qs(urlsplit(link).fragment)
                recipient={'email':'preserved@forge.local.test','password':'preserved recipient long password'}
                result=client.post('/forge/v1/accounts/invitations/accept',json={
                    'invitation_id':token['invitation_id'][0],'capability':token['capability'][0],
                    'password':recipient['password']})
                self.assertEqual(result.status_code,201)
                recipient_id=result.json()['membership_id']
                recipient_token=login(client,recipient)
            for pool in pools:pool.close(timeout=5)
            pools.clear()
            preserved_files={name:hashlib.sha256((workspace.directory/name).read_bytes()).digest()
                for name in ('runtime-secrets.json','admin-credentials.json')}
            def rows():
                tables=('owned_accounts','identities','organizations','memberships','membership_roles',
                    'departments','membership_departments','account_invitations','account_sessions',
                    'account_message_delivery','account_enrollment_audit','account_login_buckets',
                    'account_password_resets','configuration_revisions')
                # Hash exact existing rows; never expose hashes/password/session records in assertions.
                with psycopg.connect(**settings()) as connection:
                    queries=[]
                    for table in tables:
                        if connection.execute("SELECT to_regclass(%s)",('forge.'+table,)).fetchone()[0]:
                            values=connection.execute('SELECT row_to_json(t)::text FROM forge.'+table+' t ORDER BY row_to_json(t)::text').fetchall()
                            queries.append((table,values))
                    queries.append(('old_role_passwords',connection.execute(
                        "SELECT rolname,rolpassword FROM pg_authid WHERE rolname IN "
                        "('forge_account_service','forge_enrollment','forge_runtime') ORDER BY rolname").fetchall()))
                    return hashlib.sha256(repr(queries).encode()).digest()
            before=rows()
            mailbox_before={path.name:hashlib.sha256(path.read_bytes()).digest()
                for path in (workspace.directory/'mailbox').glob('*.eml')}
            class InjectedFailure(Exception):pass
            def fail_at(stage):
                def observe(actual):
                    if actual==stage:raise InjectedFailure()
                return observe
            with self.assertRaises(InjectedFailure):
                migrate_gateway(database,workspace,state,observe=fail_at('before_migration:1'))
            self.assertTrue(rows()==before)
            self.assertTrue(workspace.read('ownership.json')==state)
            key_before=hashlib.sha256((workspace.directory/'gateway-secrets.json').read_bytes()).digest()
            previous_journal=None
            old_cipher=None
            for stage in [*('after_commit:'+str(n) for n in range(1,len(ADDITIONS)+1)),
                          'after_role_commit','before_manifest','after_manifest']:
                with self.subTest(stage=stage),self.assertRaises(InjectedFailure):
                    migrate_gateway(database,workspace,workspace.read('ownership.json'),observe=fail_at(stage))
                self.assertTrue(rows()==before,'Upgrade changed preserved business rows.')
                if stage=='after_commit:7':
                    # Actual reviewed0017 install is promoted as a historical v1
                    # demo, then explicitly advanced to0018. No new key generated.
                    journal=workspace.read('gateway-upgrade.json')
                    previous_journal={'version':1,'instance_id':state['instance_id'],
                        'source_hashes':migration_hashes(),'target_hashes':gateway_hashes_v1(),
                        'checkpoint':7,'phase':'complete'}
                    private=gateway_secrets(workspace)
                    from psycopg import sql
                    with psycopg.connect(**settings()) as connection:
                        connection.execute(sql.SQL('ALTER ROLE forge_gateway_service LOGIN PASSWORD {}').format(
                            sql.Literal(private['roles']['forge_gateway_service'])))
                    workspace.save('ownership.json',dict(state,migration_hashes=gateway_hashes_v1()))
                    old_context=workspace.read('context.json')
                    old_context.update(schema_profile='0001-0005+0010-0017/PG17',central_gateway_available=True)
                    workspace.save('context.json',old_context)
                    workspace.save('gateway-upgrade.json',previous_journal)
                    admit_resume(workspace,workspace.read('ownership.json'))
                    old_app=compose_gateway(database,workspace,legacy,pools)
                    with TestClient(old_app,raise_server_exceptions=False) as client:
                        response=client.put('/forge/v1/orgs/'+context['organization_id']+'/gateway',
                            headers={'Authorization':'Bearer '+admin_token},json={'expected_revision':0,'api_key':'preserved-cipher-fixture-only'})
                        self.assertEqual(response.status_code,200)
                    for pool in pools:pool.close(timeout=5)
                    pools.clear()
                    with psycopg.connect(**settings()) as connection:
                        old_cipher=hashlib.sha256(repr(connection.execute('SELECT encrypted_key FROM forge.organization_gateways').fetchall()).encode()).digest()
                if stage=='after_commit:7':
                    # A completed old profile can resume unchanged until explicit upgrade.
                    continue

                with self.assertRaises(Exception):admit_resume(workspace,workspace.read('ownership.json'))
            migrate_gateway(database,workspace,workspace.read('ownership.json'))
            admit_resume(workspace,workspace.read('ownership.json'))
            self.assertTrue(rows()==before)
            self.assertEqual(workspace.read('gateway-upgrade.json')['previous'],previous_journal)
            with psycopg.connect(**settings()) as connection:
                self.assertTrue(hashlib.sha256(repr(connection.execute('SELECT encrypted_key FROM forge.organization_gateways').fetchall()).encode()).digest()==old_cipher)
            self.assertTrue(hashlib.sha256((workspace.directory/'gateway-secrets.json').read_bytes()).digest()==key_before)
            for name,digest in preserved_files.items():
                self.assertTrue(hashlib.sha256((workspace.directory/name).read_bytes()).digest()==digest)
            self.assertEqual(workspace.read('ownership.json')['migration_hashes'],gateway_hashes())
            self.assertTrue({path.name:hashlib.sha256(path.read_bytes()).digest()
                for path in (workspace.directory/'mailbox').glob('*.eml')}==mailbox_before)
            app=compose_gateway(database,workspace,legacy,pools)
            from forge.gateway_configuration import GatewayCipher
            from forge.gateway_configuration_store import PostgresGatewayStore
            from uuid import UUID
            record=PostgresGatewayStore(pools[-1]).read(capability_digest(admin_token),UUID(context['organization_id']))
            self.assertTrue(GatewayCipher(gateway_secrets(workspace)['gateway_key'].encode('ascii')).open_key(UUID(context['organization_id']),record)=='preserved-cipher-fixture-only')
            org=context['organization_id']
            headers={'Authorization':'Bearer '+admin_token}
            with TestClient(app,raise_server_exceptions=False) as client:
                self.assertEqual(client.get('/forge/v1/orgs/'+org+'/gateway/catalogue/status',headers=headers).json(),
                    {'catalogue_revision':0,'default_model':None,'publication_state':'UNPUBLISHED'})
                self.assertEqual(client.get(bootstrap,headers=headers).json()['membership']['id'],admin_id)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+recipient_token}).json()['membership']['id'],recipient_id)
                self.assertEqual(client.get('/forge/v1/orgs/'+org+'/gateway',headers=headers).json()['status'],'SAVED_UNVERIFIED')
                response=client.put('/forge/v1/orgs/'+org+'/gateway',headers=headers,
                    json={'expected_revision':1,'api_key':'fixture-protected-key-not-a-provider'})
                self.assertEqual(response.status_code,200)
                self.assertNotIn('fixture-protected',response.text)
                preflight=client.options('/forge/v1/orgs/'+org+'/gateway',headers={
                    'Origin':FRONTEND_ORIGIN,'Access-Control-Request-Method':'PUT',
                    'Access-Control-Request-Headers':'Authorization,Content-Type'})
                self.assertEqual(preflight.status_code,200)
            for pool in pools:pool.close(timeout=5)
            pools.clear()
            app=compose_gateway(database,workspace,legacy,pools)
            with TestClient(app,raise_server_exceptions=False) as client:
                new_admin=login(client,credentials)
                new_recipient=login(client,recipient)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+new_admin}).json()['membership']['id'],admin_id)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+new_recipient}).json()['membership']['id'],recipient_id)
            from forge.gateway_configuration import GatewayCipher
            from forge.gateway_configuration_store import PostgresGatewayStore
            from uuid import UUID
            record=PostgresGatewayStore(pools[-1]).read(capability_digest(new_admin),UUID(org))
            self.assertTrue(GatewayCipher(gateway_secrets(workspace)['gateway_key'].encode('ascii')).open_key(UUID(org),record)=='fixture-protected-key-not-a-provider')
            # Missing key after committed cipher state must not regenerate.
            path=workspace.directory/'gateway-secrets.json'
            saved=path.read_bytes()
            path.unlink()
            try:
                with self.assertRaises(Exception):migrate_gateway(database,workspace,workspace.read('ownership.json'))
                self.assertFalse(path.exists())
            finally:path.write_bytes(saved)
            print('Actual upgrade account preservation, independent commits/journal/promotion recovery, same-key reopen: PASS')
        finally:
            for pool in pools:pool.close(timeout=5)
            workspace.close()
            print('Retained private verification directory:',workspace.directory)
