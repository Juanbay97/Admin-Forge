"""Durable demo contracts plus separately gated real process restart proof."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from forge.dev_accounts_persistent import validate_demo_directory,validate_mount
from forge.dev_accounts import LocalFixtureError

class DurableContractTests(unittest.TestCase):
    def test_arbitrary_existing_path_cannot_be_adopted(self):
        for path in (ROOT,Path('relative'),Path('C:/Windows/forge-owned-accounts-'+'a'*32)):
            with self.subTest(path=str(path)),self.assertRaises(LocalFixtureError):
                validate_demo_directory(path)

    def test_foreign_or_tmpfs_storage_is_rejected(self):
        for mounts in ([],[{'Type':'tmpfs','Destination':'/var/lib/postgresql/data'}],
                [{'Type':'volume','Name':'foreign','Destination':'/var/lib/postgresql/data','RW':True}]):
            with self.subTest(mounts=mounts),self.assertRaises(LocalFixtureError):
                validate_mount({'Mounts':mounts,'HostConfig':{'Tmpfs':{}}},'owned')


# Actual fresh retained database; deliberately never removes its directory/volume.
import hashlib
import json
import os
import queue
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit, parse_qs
from forge.dev_accounts import BACKEND_ORIGIN, FRONTEND_ORIGIN, isolated_environment
from forge.dev_accounts_persistent import DurableWorkspace, RetainedPostgres, validated_state, validated_secrets

POWERSHELL = 'C:/Users/JuanpabloBayona/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'

def launch(mode, directory=None):
    arguments = [POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
        str(ROOT/'scripts/dev-accounts-persistent.ps1'), '-'+mode]
    if directory:
        arguments += ['-DemoDirectory', str(directory)]
    return subprocess.Popen(arguments, cwd=ROOT, env=isolated_environment(os.environ),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, creationflags=subprocess.CREATE_NO_WINDOW)

@unittest.skipUnless(os.environ.get('FORGE_RUN_DURABLE_DEMO_INTEGRATION') == '1',
    'Explicit retained separate-process lifecycle required.')
class DurableLifecycleTests(unittest.TestCase):
    def test_create_onboard_stop_resume_preserves_real_accounts(self):
        directory = None
        children = []
        started = time.monotonic()
        def ready(child):
            nonlocal directory
            messages = queue.Queue()
            def collect():
                for line in child.stdout:
                    try:
                        messages.put(json.loads(line))
                    except ValueError:
                        messages.put({'status':'invalid_output'})
                messages.put({'status':'eof'})
            threading.Thread(target=collect, daemon=True).start()
            deadline = time.monotonic()+240
            while time.monotonic()<deadline:
                message = messages.get(timeout=max(.1,deadline-time.monotonic()))
                if message.get('demo_directory'):
                    directory = Path(message['demo_directory'])
                if message.get('status') == 'ready':
                    return message
                self.assertNotIn(message.get('status'),('failed','eof','invalid_output'),
                    'Durable startup failed; nonsecret status: '+str(message))
            self.fail('Finite startup deadline exceeded.')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path, body=None, token=None):
            headers={'Content-Type':'application/json'}
            if token:
                headers['Authorization']='Bearer '+token
            data=None if body is None else json.dumps(body).encode()
            try:
                with opener.open(urllib.request.Request(BACKEND_ORIGIN+path,data=data,headers=headers),timeout=15) as response:
                    raw=response.read()
                    return response.status,json.loads(raw) if raw else None
            except urllib.error.HTTPError as response:
                raw=response.read()
                return response.code,json.loads(raw) if raw else None
        def serving():
            for attempt in range(40):
                try:
                    self.assertEqual(request('/healthz')[0],200)
                    return
                except OSError:
                    time.sleep(.1)
            self.fail('Backend did not begin serving.')
        def login(credentials):
            status,payload=request('/forge/v1/accounts/login',credentials)
            self.assertEqual(status,200,'Actual password login failed.')
            return payload['access_token']
        def database():
            workspace=DurableWorkspace(directory)
            owned = RetainedPostgres(workspace,validated_state(workspace),validated_secrets(workspace)['postgres_password'])
            document = owned.verify()
            mappings = document['NetworkSettings']['Ports'].get('5432/tcp') or []
            if document['State']['Running']:
                self.assertEqual(len(mappings),1)
                self.assertEqual(mappings[0]['HostIp'],'127.0.0.1')
                owned.port = int(mappings[0]['HostPort'])
            return owned
        def stop(child):
            command=launch('Stop',directory)
            output,_=command.communicate(timeout=65)
            self.assertEqual(command.returncode,0,'Owned stop command failed.')
            self.assertTrue(any(json.loads(line).get('data_retained') for line in output.splitlines()))
            self.assertEqual(child.wait(timeout=45),0,'Owned runtime shutdown failed.')
            self.assertFalse(database().verify()['State']['Running'])
        try:
            child=launch('Create'); children.append(child)
            first=ready(child); serving()
            self.assertTrue(first['persistent_local_demo'])
            self.assertFalse(first['enterprise_profile_configured'])
            context=json.loads(Path(first['context_file']).read_text('utf-8'))
            credentials=json.loads(Path(first['credentials_file']).read_text('utf-8'))
            self.assertTrue(context['persistent_local_demo'])
            bootstrap='/forge/v1/bootstrap?organization_id='+context['organization_id']
            self.assertEqual(request(bootstrap)[0],401)
            admin=login(credentials)
            status,admin_bootstrap=request(bootstrap,token=admin)
            self.assertEqual(status,200)
            admin_membership=admin_bootstrap['membership']['id']
            # Existing active process cannot be adopted or duplicated.
            duplicate=launch('Resume',directory)
            output,_=duplicate.communicate(timeout=35)
            self.assertEqual(duplicate.returncode,1)
            self.assertIn('BACKEND_PORT_OCCUPIED',output)
            locked=DurableWorkspace(directory)
            with self.assertRaisesRegex(LocalFixtureError,'DURABLE_INSTANCE_BUSY'):
                locked.acquire()
            email='recipient@forge.local.test'
            status,issued=request('/forge/v1/accounts/invitations',{
                'organization_id':context['organization_id'],'department_id':context['department_id'],
                'email':email,'name':'Retained lifecycle recipient'},token=admin)
            self.assertEqual(status,201)
            self.assertEqual(issued['delivery_state'],'delivered')
            self.assertNotIn('capability',issued)
            letters=list(Path(first['mailbox_directory']).glob('*.eml'))
            self.assertEqual(len(letters),1)
            letter=BytesParser(policy=policy.default).parsebytes(letters[0].read_bytes())
            self.assertEqual(letter['To'],email)
            plain=letter.get_body(preferencelist=('plain',)).get_content()
            link=next(line.strip() for line in plain.splitlines() if line.startswith(FRONTEND_ORIGIN+'/onboarding#'))
            capability=parse_qs(urlsplit(link).fragment)
            password=secrets.token_urlsafe(32)
            status,enrollment=request('/forge/v1/accounts/invitations/accept',{
                'invitation_id':capability['invitation_id'][0],
                'capability':capability['capability'][0],'password':password})
            self.assertEqual(status,201,'Actual invitation acceptance failed.')
            recipient=login({'email':email,'password':password})
            self.assertEqual(request(bootstrap,token=recipient)[1]['membership']['id'],enrollment['membership_id'])
            import psycopg
            def identities():
                with psycopg.connect(**database().settings()) as connection:
                    return connection.execute('SELECT id,canonical_email FROM forge.owned_accounts ORDER BY canonical_email').fetchall()
            accounts_before=identities()
            self.assertEqual(len(accounts_before),2)
            self.assertEqual(str(next(row[0] for row in accounts_before if row[1]==email)),enrollment['account_id'])
            def stable_bytes():
                return {name:hashlib.sha256((directory/name).read_bytes()).digest() for name in
                    ('context.json','admin-credentials.json','runtime-secrets.json','ownership.json')}
            stable=stable_bytes()
            stop(child)
            self.assertTrue(directory.is_dir())
            child=launch('Resume',directory);children.append(child)
            second=ready(child);serving()
            self.assertEqual(second['container_id'],first['container_id'])
            self.assertEqual(second['volume_name'],first['volume_name'])
            self.assertEqual(stable_bytes(),stable,'Resume modified stable fixture configuration.')
            self.assertEqual(identities(),accounts_before,'Resume changed account identities.')
            self.assertEqual(request(bootstrap,token=login(credentials))[1]['membership']['id'],admin_membership)
            self.assertEqual(request(bootstrap,token=login({'email':email,'password':password}))[1]['membership']['id'],enrollment['membership_id'])
            stop(child)
            marker=directory/'ownership.json'
            original=marker.read_bytes()
            altered=json.loads(original);altered['kind']='foreign-owned-artifact'
            try:
                marker.write_text(json.dumps(altered),encoding='utf-8')
                tampered=launch('Resume',directory)
                output,_=tampered.communicate(timeout=35)
                self.assertEqual(tampered.returncode,1)
                self.assertIn('INVALID_DURABLE_OWNERSHIP',output)
            finally:
                marker.write_bytes(original)
            self.assertFalse(database().verify()['State']['Running'])
            self.assertEqual(stable_bytes(),stable)
            print('Durable lifecycle: real login/onboarding/stop/resume, same accounts/credentials/key/context, duplicate/tamper denied.')
            print('Retained test directory:',directory)
            print('Retained STOPPED test container:',first['container_id'])
            print('Retained test volume:',first['volume_name'])
            print('Lifecycle seconds:',round(time.monotonic()-started,3))
        finally:
            for child in children:
                if child.poll() is None and directory:
                    try:
                        child.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        stop(child)
                for stream in (child.stdin,child.stdout,child.stderr):
                    stream.close()
            if directory:
                print('Owned verification directory preserved:',directory)

if __name__ == "__main__":
    unittest.main()
