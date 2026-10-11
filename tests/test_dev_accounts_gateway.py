"""Explicit gateway profile manifest admission and journal recovery contracts."""
from pathlib import Path
import hashlib
import json
import sys
import unittest
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from forge.dev_accounts_persistent import validated_state,DEMOS_ROOT,KIND
from forge.dev_accounts import MIGRATIONS

ADDITIONS=('0005_transactional_outbox.sql','0010_model_catalog_snapshots.sql',
    '0011_model_catalog_publication.sql','0012_catalog_publication_authority.sql',
    '0015_gateway_configuration.sql','0016_owned_gateway_catalog.sql',
    '0017_owned_gateway_inference.sql','0018_gateway_catalog_admin_status.sql')


class GatewayDemoContractTests(unittest.TestCase):
    def test_explicit_gateway_ready_manifest_is_accepted(self):
        identifier=uuid4()
        class Workspace:
            directory=DEMOS_ROOT/('forge-owned-accounts-'+identifier.hex)
            def read(self,name):
                return dict(version=1,kind=KIND,instance_id=str(identifier),
                    directory=str(self.directory),repository=str(ROOT),
                    image=(ROOT/'scripts/postgres-image.txt').read_text('ascii').strip(),
                    migration_hashes={n:hashlib.sha256((ROOT/'migrations'/n).read_bytes()).hexdigest()
                        for n in (*MIGRATIONS,*ADDITIONS)},phase='ready',
                    container_name='forge-durable-accounts-'+identifier.hex,
                    volume_name='forge-durable-accounts-data-'+identifier.hex,container_id='a'*64)
        self.assertEqual(validated_state(Workspace())['phase'],'ready')

from unittest.mock import patch,MagicMock
from forge.dev_accounts import LocalFixtureError
from forge.dev_accounts_gateway import upgrade_gateway,admit_resume,gateway_hashes

class GatewayLifecycleGuardTests(unittest.TestCase):
    def test_active_owned_database_refuses_without_stopping(self):
        workspace=MagicMock()
        database=MagicMock()
        database.verify.return_value={'State':{'Running':True}}
        with patch('forge.dev_accounts_persistent.DurableWorkspace',return_value=workspace),\
             patch('forge.dev_accounts_persistent.validated_state',return_value={}),\
             patch('forge.dev_accounts_persistent.validated_secrets',return_value={'postgres_password':'fixture'}),\
             patch('forge.dev_accounts_persistent.RetainedPostgres',return_value=database):
            with self.assertRaisesRegex(LocalFixtureError,'STOPPED_DURABLE_DEMO_REQUIRED'):
                upgrade_gateway('owned-fixture')
        database.start.assert_not_called()
        database.close.assert_not_called()
        workspace.close.assert_called_once()

    def test_locked_instance_refuses_before_database_use(self):
        workspace=MagicMock()
        workspace.acquire.side_effect=LocalFixtureError('DURABLE_INSTANCE_BUSY')
        with patch('forge.dev_accounts_persistent.DurableWorkspace',return_value=workspace),\
             patch('forge.dev_accounts_persistent.RetainedPostgres') as constructor:
            with self.assertRaisesRegex(LocalFixtureError,'DURABLE_INSTANCE_BUSY'):
                upgrade_gateway('owned-fixture')
            constructor.assert_not_called()
        workspace.close.assert_called_once()

    def test_resume_never_repairs_incomplete_upgrade(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as path:
            class Workspace:directory=Path(path)
            (Path(path)/'gateway-upgrade.json').write_text('{}',encoding='utf-8')
            legacy={'migration_hashes':{}}
            with self.assertRaisesRegex(LocalFixtureError,'EXPLICIT_GATEWAY_RECOVERY_REQUIRED'):
                admit_resume(Workspace(),legacy)

import os
import subprocess
from threading import Event
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from forge.dev_accounts import install_and_seed,compose,isolated_environment,FRONTEND_ORIGIN
from forge.dev_accounts_persistent import (DurableWorkspace,RetainedPostgres,
    validated_secrets,migration_hashes)
from forge.dev_accounts_gateway import compose_gateway,gateway_secrets

@unittest.skipUnless(os.environ.get('FORGE_RUN_GATEWAY_DEMO_INTEGRATION')=='1',
    'Explicit separate owned retained gateway lifecycle required.')
class RetainedGatewayLifecycleTests(unittest.TestCase):
    def test_stopped_upgrade_child_restart_preserves_real_users_and_key(self):
        import secrets
        from uuid import UUID
        identifier=uuid4()
        workspace=DurableWorkspace(DEMOS_ROOT/('forge-owned-accounts-'+identifier.hex),create=True)
        state=dict(version=1,kind=KIND,instance_id=str(identifier),directory=str(workspace.directory),
            repository=str(ROOT),image=(ROOT/'scripts/postgres-image.txt').read_text('ascii').strip(),
            migration_hashes=migration_hashes(),container_name='forge-durable-accounts-'+identifier.hex,
            container_id=None,volume_name='forge-durable-accounts-data-'+identifier.hex,phase='initializing')
        legacy={'postgres_password':secrets.token_urlsafe(32),'roles':{},
                'delivery_key':Fernet.generate_key().decode('ascii')}
        workspace.save('ownership.json',state);workspace.save('runtime-secrets.json',legacy)
        database=RetainedPostgres(workspace,state,legacy['postgres_password'])
        pools=[]
        created=False
        def close_pools():
            for pool in pools:pool.close(timeout=5)
            pools.clear()
        def login(client,credentials):
            response=client.post('/forge/v1/accounts/login',json=credentials)
            self.assertEqual(response.status_code,200,'Actual retained password login failed.')
            return response.json()['access_token']
        try:
            workspace.acquire()
            database.create();created=True;database.start(Event())
            legacy['roles']=install_and_seed(database,workspace,Event())
            workspace.save('runtime-secrets.json',legacy)
            app=compose(database,workspace,legacy['roles'],pools,delivery_key=legacy['delivery_key'].encode('ascii'))
            state['phase']='ready';workspace.save('ownership.json',state)
            credentials=workspace.read('admin-credentials.json');context=workspace.read('context.json')
            bootstrap='/forge/v1/bootstrap?organization_id='+context['organization_id']
            recipient={'email':'retained-upgrade@forge.local.test','password':secrets.token_urlsafe(32)}
            with TestClient(app,raise_server_exceptions=False) as client:
                admin=login(client,credentials)
                headers={'Authorization':'Bearer '+admin}
                admin_id=client.get(bootstrap,headers=headers).json()['membership']['id']
                response=client.post('/forge/v1/accounts/invitations',headers=headers,json={
                    'organization_id':context['organization_id'],'department_id':context['department_id'],
                    'email':recipient['email'],'name':'Retained upgrade recipient'})
                self.assertEqual(response.status_code,201)
                from email import policy
                from email.parser import BytesParser
                from urllib.parse import urlsplit,parse_qs
                letter=BytesParser(policy=policy.default).parsebytes(next((workspace.directory/'mailbox').glob('*.eml')).read_bytes())
                link=next(line for line in letter.get_body(preferencelist=('plain',)).get_content().splitlines()
                          if line.startswith(FRONTEND_ORIGIN+'/onboarding#'))
                invitation=parse_qs(urlsplit(link).fragment)
                response=client.post('/forge/v1/accounts/invitations/accept',json={
                    'invitation_id':invitation['invitation_id'][0],
                    'capability':invitation['capability'][0],'password':recipient['password']})
                self.assertEqual(response.status_code,201)
                recipient_id=response.json()['membership_id']
                old_recipient=login(client,recipient)
            close_pools()
            private_before={name:hashlib.sha256((workspace.directory/name).read_bytes()).digest()
                for name in ('runtime-secrets.json','admin-credentials.json')}
            database.close();self.assertFalse(database.verify()['State']['Running'])
            workspace.close()
            pwsh='C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
            command=[pwsh,'-NoProfile','-NonInteractive','-File',
                str(ROOT/'scripts/dev-accounts-persistent.ps1'),'-UpgradeGateway',
                '-DemoDirectory',str(workspace.directory)]
            result=subprocess.run(command,cwd=ROOT,env=isolated_environment(os.environ),
                capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode,0,'Explicit owned child upgrade failed; private diagnostics suppressed.')
            self.assertTrue(any(json.loads(line).get('status')=='upgraded' for line in result.stdout.splitlines()))
            self.assertFalse(database.verify()['State']['Running'])
            for name,digest in private_before.items():
                self.assertTrue(hashlib.sha256((workspace.directory/name).read_bytes()).digest()==digest)
            database.start(Event())
            with self.assertRaisesRegex(LocalFixtureError,'STOPPED_DURABLE_DEMO_REQUIRED'):
                upgrade_gateway(workspace.directory)
            self.assertTrue(database.verify()['State']['Running'],'Refusal stopped an active owner.')
            app=compose_gateway(database,workspace,legacy,pools)
            with TestClient(app,raise_server_exceptions=False) as client:
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+admin}).json()['membership']['id'],admin_id)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+old_recipient}).json()['membership']['id'],recipient_id)
                new_admin=login(client,credentials);new_recipient=login(client,recipient)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+new_recipient}).json()['membership']['id'],recipient_id)
                response=client.put('/forge/v1/orgs/'+context['organization_id']+'/gateway',
                    headers={'Authorization':'Bearer '+new_admin},
                    json={'expected_revision':0,'api_key':'retained-fixture-private-gateway'})
                self.assertEqual(response.status_code,200)
            key_before=(workspace.directory/'gateway-secrets.json').read_bytes()
            close_pools();database.close()
            database.start(Event())
            app=compose_gateway(database,workspace,legacy,pools)
            with TestClient(app,raise_server_exceptions=False) as client:
                admin=login(client,credentials)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+admin}).json()['membership']['id'],admin_id)
                self.assertEqual(client.get(bootstrap,headers={'Authorization':'Bearer '+login(client,recipient)}).json()['membership']['id'],recipient_id)
            from forge.gateway_configuration import GatewayCipher
            from forge.gateway_configuration_store import PostgresGatewayStore
            from forge.invitations import capability_digest
            record=PostgresGatewayStore(pools[-1]).read(capability_digest(admin),UUID(context['organization_id']))
            self.assertTrue(GatewayCipher(gateway_secrets(workspace)['gateway_key'].encode('ascii')).open_key(UUID(context['organization_id']),record)=='retained-fixture-private-gateway')
            self.assertTrue((workspace.directory/'gateway-secrets.json').read_bytes()==key_before)
            close_pools();database.close()
            self.assertFalse(database.verify()['State']['Running'])
            print('NEW retained gateway lifecycle PASS; directory:',workspace.directory)
            print('Retained STOPPED test container:',database.container_id)
            print('Retained test volume:',database.volume)
        finally:
            close_pools()
            try:
                if created:database.close()
            finally:
                workspace.close()
                print('Owned retained verification directory:',workspace.directory)
                if created:
                    print('Owned retained STOPPED container:',database.container_id)
                    print('Owned retained volume:',database.volume)

class VersionedGatewayJournalTests(unittest.TestCase):
    def test_specific_v1_and_v2_history_is_validated_without_erasing_v1(self):
        from forge.dev_accounts_gateway import validated_journal,gateway_hashes_v1
        identifier=uuid4();state={'instance_id':str(identifier),'migration_hashes':gateway_hashes_v1()}
        prior={'version':1,'instance_id':str(identifier),'source_hashes':migration_hashes(),
            'target_hashes':gateway_hashes_v1(),'checkpoint':7,'phase':'complete'}
        class Workspace:
            value=prior
            def read(self,name):return self.value
        workspace=Workspace()
        self.assertEqual(validated_journal(workspace,state),prior)
        current={'version':2,'instance_id':str(identifier),'source_hashes':gateway_hashes_v1(),
            'target_hashes':gateway_hashes(),'checkpoint':7,'phase':'migrating','previous':dict(prior)}
        workspace.value=current
        self.assertEqual(validated_journal(workspace,state)['previous'],prior)
        for patch_value in ({'target_hashes':{}},{'source_hashes':{}},{'previous':None},{'checkpoint':6}):
            workspace.value=current|patch_value
            with self.assertRaises(LocalFixtureError):validated_journal(workspace,state)
        workspace.value=current|{'previous':prior|{'target_hashes':{}}}
        with self.assertRaises(LocalFixtureError):validated_journal(workspace,state)

    def test_interrupted_v1_accepts_only_matching_known_target_and_checkpoint(self):
        from forge.dev_accounts_gateway import validated_journal,gateway_hashes_v1
        identifier=uuid4();state={'instance_id':str(identifier)}
        prior={'version':1,'instance_id':str(identifier),'source_hashes':migration_hashes(),
            'target_hashes':gateway_hashes_v1(),'checkpoint':6,'phase':'migrating'}
        class Workspace:
            def read(self,name):return prior
        self.assertEqual(validated_journal(Workspace(),state),prior)
        prior['checkpoint']=8
        with self.assertRaises(LocalFixtureError):validated_journal(Workspace(),state)
