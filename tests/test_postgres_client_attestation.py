"""Owned PostgreSQL 0047 client attestation: an append-only, member-bound log of the device's sandbox attestation reports (strict allow-list,
replay-safe, bounded per day, no content column) and the member's latest recent level that the effective policy uses."""
import json
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import CLIENT_ATTESTATION_MIGRATION, F46, F47, MVP_ADDITIONS, MVP_CHECKPOINTS
from capability_support import GovernanceWorld
from mvp_support import at, mvp_database
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_mvp_local import login, stack
from test_postgres_platform_schema import drop_platform_roles

INGEST = 'SELECT forge.cap_attestation_ingest(%s,%s,%s::jsonb)'
LATEST = 'SELECT forge.cap_latest_attestation(%s,%s)'


def report(**change):
    item = {'level': 3, 'suite_version': '1.2.0', 'client_version': '0.9.1', 'os_build': '10.0.26200',
            'cases': [{'id': 'traversal', 'passed': True}, {'id': 'env_dump', 'passed': False}], 'at': '2026-10-12T12:00:00Z'}
    item.update(change)
    return item


class AttestationProfileTests(unittest.TestCase):
    def test_0047_follows_0046_with_its_own_pinned_checkpoint(self):
        self.assertEqual(CLIENT_ATTESTATION_MIGRATION, '0047_client_attestation.sql')
        self.assertEqual(MVP_ADDITIONS[at(CLIENT_ATTESTATION_MIGRATION) - 1], '0046_invitation_preview.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(CLIENT_ATTESTATION_MIGRATION):at(CLIENT_ATTESTATION_MIGRATION) + 2], (F46, F47))
        self.assertRegex(F47 or '', r'^[0-9a-f]{64}$', 'F47 must be pinned')
        self.assertNotEqual(F47, F46)


class AttestationFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0046_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(CLIENT_ATTESTATION_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, CLIENT_ATTESTATION_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F46)
            conn.execute(migration_text(CLIENT_ATTESTATION_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0047 client attestation checkpoint F47:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0046 must be identical')
        self.assertEqual(fresh, F47, 'F47 must be pinned to the reviewed value')


class IngestTests(GovernanceWorld, unittest.TestCase):
    def ingest(self, who, org, item):
        return self.role.call(INGEST, (self.digest[who], org, json.dumps(item)))[0][0]

    def rows(self):
        return self.db.admin.execute('SELECT organization_id,level,suite_version,client_version,os_build,cases FROM forge.client_attestations ORDER BY id').fetchall()

    def test_a_report_is_stored_once_for_the_member_of_the_session_and_a_replay_stores_nothing(self):
        with mvp_database() as db:
            self.build(db)
            self.assertIs(self.ingest('member_a', self.org_a, report()), True)
            self.assertIs(self.ingest('member_a', self.org_a, report()), False, 'the same device time is a replay')
            self.assertIs(self.ingest('member_a', self.org_a, report(at='2026-10-12T12:00:01Z', level=2)), True)
            stored = self.rows()
            self.assertEqual([(row[0], row[1], row[2:5]) for row in stored], [(self.org_a, 3, ('1.2.0', '0.9.1', '10.0.26200')), (self.org_a, 2, ('1.2.0', '0.9.1', '10.0.26200'))])
            self.assertEqual(stored[0][5], [{'id': 'traversal', 'passed': True}, {'id': 'env_dump', 'passed': False}])
            member = db.admin.execute('SELECT m.id FROM forge.memberships m JOIN forge.owned_accounts a ON a.id=m.identity_id WHERE a.canonical_email=%s', (self.member_a.email,)).fetchone()[0]
            self.assertEqual(db.admin.execute('SELECT DISTINCT membership_id FROM forge.client_attestations').fetchall(), [(member,)], 'the member comes from the session, never the payload')

    def test_content_fields_and_bad_values_are_refused_and_nothing_is_stored(self):
        with mvp_database() as db:
            self.build(db)
            bad = ({**report(), 'paths': ['C:\\x']}, {**report(), 'env': {'A': 'b'}}, {**report(), 'extra': 1}, {k: v for k, v in report().items() if k != 'at'},
                   report(level=5), report(level=-1), report(level=True), report(level='3'), report(suite_version='a b'), report(client_version=''),
                   report(os_build='C:\\Windows'), report(at='yesterday'), report(at='2026-10-12 12:00:00'), report(cases='x'), report(cases=[{'id': 'a'}]),
                   report(cases=[{'id': 'a', 'passed': True, 'detail': 'x'}]), report(cases=[{'id': 'Bad Id', 'passed': True}]),
                   report(cases=[{'id': 'a', 'passed': 'yes'}]), report(cases=[{'id': 'a', 'passed': True}] * 65), 'text', 5, None, [])
            for item in bad:
                with self.subTest(item=str(item)[:70]):
                    self.assertEqual(self.role.refusal(INGEST, (self.digest['member_a'], self.org_a, json.dumps(item))), 'CAP_INVALID')
            self.assertEqual(self.rows(), [])
            self.assertIs(self.ingest('member_a', self.org_a, report(cases=[{'id': 'a', 'passed': True}] * 64)), True)

    def test_a_stranger_another_company_and_a_suspended_company_are_denied_and_store_nothing(self):
        with mvp_database() as db:
            self.build(db)
            for digest, org in ((self.digest['member_a'], self.org_b), (self.digest['member_b'], self.org_a), ('0' * 64, self.org_a), (self.digest['member_a'], uuid4()), (self.digest['member_a'], None)):
                self.assertEqual(self.role.refusal(INGEST, (digest, org, json.dumps(report()))), 'CAP_DENIED')
            db.admin.execute('UPDATE forge.organizations SET active=false WHERE id=%s', (self.org_a,))
            self.assertEqual(self.role.refusal(INGEST, (self.digest['member_a'], self.org_a, json.dumps(report()))), 'CAP_DENIED')
            self.assertEqual(self.rows(), [])

    def test_a_member_cannot_flood_the_log(self):
        with mvp_database() as db:
            self.build(db)
            results = [self.ingest('member_a', self.org_a, report(at='2026-10-12T12:%02d:00Z' % minute)) for minute in range(30)]
            self.assertEqual(results.count(True), 24, 'at most 24 reports per member per day are kept')
            self.assertEqual(len(self.rows()), 24)
            self.assertIs(self.ingest('member_b', self.org_b, report()), True, 'the bound is per member')


class LatestTests(GovernanceWorld, unittest.TestCase):
    def latest(self, who, org):
        return self.role.call(LATEST, (self.digest[who], org))[0][0]

    def test_the_latest_report_of_the_member_for_the_company_wins(self):
        with mvp_database() as db:
            self.build(db)
            self.assertIsNone(self.latest('member_a', self.org_a), 'no report: nothing to use')
            for level, minute in ((3, 1), (1, 2)):
                self.role.call(INGEST, (self.digest['member_a'], self.org_a, json.dumps(report(level=level, at='2026-10-12T12:0%d:00Z' % minute))))
            self.assertEqual(self.latest('member_a', self.org_a), 1, 'the newest report, even when lower')
            self.assertIsNone(self.latest('admin_a', self.org_a), 'another member of the company has none')
            self.role.call(INGEST, (self.digest['member_b'], self.org_b, json.dumps(report(level=4))))
            self.assertEqual(self.latest('member_b', self.org_b), 4)
            self.assertEqual(self.latest('member_a', self.org_a), 1, 'another company never mixes in')

    def test_a_report_older_than_thirty_days_is_ignored_and_strangers_are_denied(self):
        with mvp_database() as db:
            self.build(db)
            self.role.call(INGEST, (self.digest['member_a'], self.org_a, json.dumps(report(level=3))))
            self.assertEqual(self.latest('member_a', self.org_a), 3)
            db.admin.execute("UPDATE forge.client_attestations SET recorded_at=clock_timestamp()-interval '31 days'")
            self.assertIsNone(self.latest('member_a', self.org_a), 'a stale attestation proves nothing about the device now')
            for digest, org in ((self.digest['member_a'], self.org_b), ('0' * 64, self.org_a), (self.digest['member_a'], None)):
                self.assertEqual(self.role.refusal(LATEST, (digest, org)), 'CAP_DENIED')


class StorageTests(GovernanceWorld, unittest.TestCase):
    def test_no_column_holds_content_and_no_role_can_change_or_remove_a_row(self):
        with mvp_database() as db:
            columns = {row[0]: row[1] for row in db.admin.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='forge' AND table_name='client_attestations'")}
            self.assertEqual({name for name, kind in columns.items() if kind == 'text'}, {'suite_version', 'client_version', 'os_build'})
            self.assertFalse([name for name in columns if any(word in name for word in ('path', 'env', 'user', 'content', 'output', 'message'))])
            for role in ('forge_capability_authority', 'forge_capability_service', 'forge_gateway_authority', 'forge_runtime'):
                for privilege in ('UPDATE', 'DELETE', 'TRUNCATE'):
                    self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.client_attestations',%s)", (role, privilege)).fetchone(), (False,), (role, privilege))
            for role in ('forge_capability_service', 'forge_platform_service', 'forge_gateway_service', 'forge_account_service', 'public'):
                self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.client_attestations','SELECT,INSERT')", (role,)).fetchone(), (False,), role)
            self.assertEqual(db.admin.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='forge.client_attestations'::regclass").fetchone(), (True, True))
            for function, expected in (('forge.cap_attestation_ingest(text,uuid,jsonb)', True), ('forge.cap_latest_attestation(text,uuid)', True)):
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', ('forge_capability_service', function, 'EXECUTE')).fetchone(), (expected,))
                self.assertEqual(db.admin.execute('SELECT has_function_privilege(%s,%s,%s)', ('public', function, 'EXECUTE')).fetchone(), (False,))


class AttestationHttpTests(unittest.TestCase):
    def test_a_member_reports_over_http_and_the_report_is_bound_to_the_session_company(self):
        with stack() as (db, client, results, root, secrets):
            member = login(client, results[0].accounts[1])
            path = '/forge/v1/client/attestation'
            body = report()
            accepted = client.post(path, headers=member, json=body)
            self.assertEqual((accepted.status_code, accepted.json()), (202, {'level': 3, 'stored': True}))
            self.assertEqual(client.post(path, headers=member, json=body).json(), {'level': 3, 'stored': False}, 'a replay stores nothing')
            leaked = client.post(path, headers=member, json={**body, 'at': '2026-10-12T13:00:00Z', 'paths': ['C:\\Users\\x']})
            self.assertEqual((leaked.status_code, leaked.json()['error']['code']), (422, 'INVALID_REQUEST'))
            self.assertEqual(db.admin.execute('SELECT count(*),min(level) FROM forge.client_attestations').fetchone(), (1, 3))
            self.assertEqual(client.post(path, json=body).status_code, 401)
            self.assertEqual(client.post(path + '?org=%s' % results[1].organization_id, headers=member, json={**body, 'at': '2026-10-12T14:00:00Z'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
