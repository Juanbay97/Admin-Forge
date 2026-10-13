"""Owned PostgreSQL 0046 invitation preview: the holder of a pending invitation's link learns the invited email (so the join page need not ask
for it) without the pinned accept response changing; every unusable invitation (unknown, wrong capability, expired, used, withdrawn, suspended
company) is the same uniform 404 so nothing can be enumerated."""
import email
from email import policy
from pathlib import Path
import secrets as token_source
import sys
import unittest
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge import contract
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.invitations import capability_digest
from forge.mvp_profile import F45, F46, INVITATION_PREVIEW_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import call, refusal
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_schema import drop_platform_roles

PREVIEW = 'SELECT * FROM forge.account_invitation_preview(%s,%s)'
INVITE = '/forge/v1/accounts/invitations'
ROUTE = INVITE + '/preview'


class PreviewProfileTests(unittest.TestCase):
    def test_0046_follows_0045_with_its_own_pinned_checkpoint(self):
        self.assertEqual(INVITATION_PREVIEW_MIGRATION, '0046_invitation_preview.sql')
        self.assertEqual(MVP_ADDITIONS[at(INVITATION_PREVIEW_MIGRATION) - 1], '0045_directory_member_department.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(INVITATION_PREVIEW_MIGRATION):at(INVITATION_PREVIEW_MIGRATION) + 2], (F45, F46))
        self.assertRegex(F46 or '', r'^[0-9a-f]{64}$', 'F46 must be pinned')
        self.assertNotEqual(F46, F45)


class PreviewFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0045_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(INVITATION_PREVIEW_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, INVITATION_PREVIEW_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F45)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(INVITATION_PREVIEW_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0046 invitation preview checkpoint F46:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0045 must be identical')
        self.assertEqual(fresh, F46, 'F46 must be pinned to the reviewed value')


def issue(client, result, address='new.person@a.test'):
    body = {'organization_id': str(result.organization_id), 'department_id': str(result.department_id), 'email': address, 'name': 'New Person'}
    response = client.post(INVITE, headers=login(client, result.accounts[0]), json=body)
    assert response.status_code == 201, response.text
    return response.json()['invitation_id']


def mailed(root):
    (path,) = sorted((root/'mailbox').glob('*.eml'))
    message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    link = next(line for line in message.get_body(('plain',)).get_content().splitlines() if line.startswith('http'))
    fragment = parse_qs(urlsplit(link).fragment)
    return fragment['invitation_id'][0], fragment['capability'][0]


class PreviewFunctionTests(unittest.TestCase):
    def preview(self, db, invitation, capability):
        return call(db, PREVIEW, (invitation, capability_digest(capability)), role='forge_enrollment')

    def test_a_pending_invitation_names_the_invited_person_and_changes_nothing(self):
        with stack() as (db, client, results, root, secrets):
            issue(client, results[0], 'New.Person@A.test')
            invitation, capability = mailed(root)
            before = db.admin.execute('SELECT state,consumed_at,expires_at FROM forge.account_invitations').fetchall()
            self.assertEqual(self.preview(db, invitation, capability), [('new.person@a.test', 'New Person')])
            self.assertEqual(self.preview(db, invitation, capability), [('new.person@a.test', 'New Person')], 'peeking is repeatable')
            self.assertEqual(db.admin.execute('SELECT state,consumed_at,expires_at FROM forge.account_invitations').fetchall(), before)

    def test_every_unusable_invitation_is_the_same_denial(self):
        with stack() as (db, client, results, root, secrets):
            issue(client, results[0])
            invitation, capability = mailed(root)
            other = token_source.token_urlsafe(32)
            for arguments in ((invitation, other), (str(uuid4()), capability), (None, capability)):
                with self.subTest(arguments=str(arguments)[:50]):
                    digest = capability_digest(arguments[1])
                    self.assertEqual(refusal(self, lambda: call(db, PREVIEW, (arguments[0], digest), role='forge_enrollment')), 'INVITATION_DENIED')
            for digest in (None, 'x', 'A' * 64):
                self.assertEqual(refusal(self, lambda: call(db, PREVIEW, (invitation, digest), role='forge_enrollment')), 'INVITATION_DENIED')
            db.admin.execute("UPDATE forge.account_invitations SET expires_at=clock_timestamp()-interval '1 second'")
            self.assertEqual(refusal(self, lambda: self.preview(db, invitation, capability)), 'INVITATION_DENIED')
            db.admin.execute("UPDATE forge.account_invitations SET expires_at=clock_timestamp()+interval '1 day'")
            self.assertEqual(len(self.preview(db, invitation, capability)), 1)
            db.admin.execute("UPDATE forge.account_invitations SET state='revoked'")
            self.assertEqual(refusal(self, lambda: self.preview(db, invitation, capability)), 'INVITATION_DENIED')
            db.admin.execute("UPDATE forge.account_invitations SET state='pending'")
            db.admin.execute('UPDATE forge.organizations SET active=false')
            self.assertEqual(refusal(self, lambda: self.preview(db, invitation, capability)), 'INVITATION_DENIED', 'a suspended company')

    def test_only_the_enrollment_pool_may_execute_it(self):
        with mvp_database() as db:
            signature = 'forge.account_invitation_preview(uuid,text)'
            for role, expected in (('forge_enrollment', True), ('forge_account_service', False), ('forge_gateway_service', False),
                                   ('forge_platform_service', False), ('forge_runtime', False), ('public', False)):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', (role, signature, 'EXECUTE')).fetchone(), (expected,), role)


class PreviewHttpTests(unittest.TestCase):
    def test_the_route_is_hidden_names_the_person_before_accepting_and_answers_the_same_404_afterwards(self):
        with stack() as (db, client, results, root, secrets):
            issue(client, results[0])
            invitation, capability = mailed(root)
            self.assertEqual(contract.canonical_sha256(contract.build(client.app)), contract.canonical_sha256(__import__('json').loads(contract.COMMITTED_PATH.read_text('utf-8'))))
            seen = client.post(ROUTE, json={'invitation_id': invitation, 'capability': capability})
            self.assertEqual((seen.status_code, seen.json(), seen.headers['cache-control']), (200, {'account_email': 'new.person@a.test', 'display_name': 'New Person'}, 'no-store'))
            accepted = client.post(INVITE + '/accept', json={'invitation_id': invitation, 'capability': capability, 'password': 'a long enough passphrase 123'})
            self.assertEqual(accepted.status_code, 201, accepted.text)
            self.assertEqual(set(accepted.json()), {'account_id', 'organization_id', 'membership_id', 'department_id'}, 'the pinned accept response is untouched')
            used = client.post(ROUTE, json={'invitation_id': invitation, 'capability': capability})
            unknown = client.post(ROUTE, json={'invitation_id': str(uuid4()), 'capability': token_source.token_urlsafe(32)})
            self.assertEqual((used.status_code, used.json()['error']['code']), (404, 'NOT_FOUND'))
            self.assertEqual((unknown.status_code, unknown.json()['error']['code']), (404, 'NOT_FOUND'))
            self.assertEqual({key: used.json()['error'][key] for key in ('message', 'retryable')}, {key: unknown.json()['error'][key] for key in ('message', 'retryable')},
                             'a used and an unknown invitation cannot be told apart')

    def test_malformed_requests_are_422_and_nothing_is_stored(self):
        with stack() as (db, client, results, root, secrets):
            for body in ({}, {'invitation_id': 'nope', 'capability': 'x' * 43}, {'invitation_id': str(uuid4()), 'capability': 'short'},
                         {'invitation_id': str(uuid4()), 'capability': 'x' * 43, 'extra': 1}):
                self.assertEqual(client.post(ROUTE, json=body).status_code, 422, str(body)[:40])
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.account_invitations').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
