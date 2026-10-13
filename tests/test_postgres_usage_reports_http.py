"""Owned PostgreSQL through the composed app: the owner sets a price over HTTP, usage recorded afterwards is priced, and the three
platform reports show it; company administrators and members are denied on every usage route."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from platform_support import OWNER_EMAIL, PASSWORD, add_owner
from test_postgres_mvp_local import login, stack
from test_postgres_platform_http import BASE, Person, code_for

TODAY = datetime.now(timezone.utc).date().isoformat()
RANGE = {'from': TODAY, 'to': TODAY}


def record(db, org, member, upstream, prompt, completion):
    db.admin.execute('SELECT forge.usage_record(%s,%s,%s,%s,%s,NULL,%s,%s,100,10,%s,NULL,%s)',
                     (org, member, uuid4(), 'assistant', upstream, prompt, completion, 'ok', 'gateway'))


class PostgresUsageReportsHttpTests(unittest.TestCase):
    def verified_owner(self, db, client):
        add_owner(db.admin)
        headers = login(client, Person(OWNER_EMAIL, PASSWORD))
        enrollment = client.post(BASE + '/mfa/enroll', headers=headers).json()
        self.assertEqual(client.post(BASE + '/login/mfa', headers=headers, json={'code': code_for(enrollment['secret'])}).status_code, 200)
        return headers

    def test_a_price_set_over_http_prices_later_usage_and_the_reports_show_it_per_company_model_and_total(self):
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            created = client.post(BASE + '/prices', headers=owner, json={'upstream_id': 'up/model-a', 'input_micros': 1_000_000, 'output_micros': 2_000_000})
            self.assertEqual((created.status_code, created.json()['version'], created.json()['currency']), (201, 1, 'USD'))
            again = client.post(BASE + '/prices', headers=owner, json={'upstream_id': 'up/model-a', 'input_micros': 2_000_000, 'output_micros': 4_000_000})
            self.assertEqual(again.json()['version'], 2)
            self.assertEqual([item['version'] for item in client.get(BASE + '/prices', headers=owner, params={'upstream_id': 'up/model-a'}).json()['prices']], [2, 1])
            members = {r.slug: db.admin.execute('SELECT id FROM forge.memberships WHERE organization_id=%s ORDER BY id', (r.organization_id,)).fetchone()[0] for r in results}
            record(db, results[0].organization_id, members['org-a'], 'up/model-a', 1000, 500)   # (1000*2 + 500*4) = 4000 micro-USD at v2
            record(db, results[1].organization_id, members['org-b'], 'up/model-z', 10, 10)       # unpriced
            companies = client.get(BASE + '/usage/companies', headers=owner, params=RANGE).json()['companies']
            by_slug = {row['slug']: row for row in companies}
            self.assertEqual((by_slug['org-a']['requests'], by_slug['org-a']['cost_micros'], by_slug['org-a']['unpriced_requests']), (1, 4000, 0))
            self.assertEqual((by_slug['org-b']['cost_micros'], by_slug['org-b']['unpriced_requests']), (0, 1))
            models = {row['upstream_id']: row for row in client.get(BASE + '/usage/models', headers=owner, params=RANGE).json()['models']}
            self.assertEqual((models['up/model-a']['prompt_tokens'], models['up/model-z']['unpriced_requests']), (1000, 1))
            totals = client.get(BASE + '/usage/totals', headers=owner, params=RANGE).json()
            self.assertEqual((totals['companies'], totals['requests'], totals['cost_micros'], totals['unpriced_requests']), (2, 2, 4000, 1))
            actions = [entry['action'] for entry in client.get(BASE + '/audit', headers=owner).json()['entries']]
            self.assertEqual(actions[:2], ['model_price.set', 'model_price.set'])
            self.assertNotIn('content', repr(totals) + repr(models))

    def test_company_administrators_and_members_are_denied_on_every_platform_usage_route(self):
        with stack() as (db, client, results, root, secrets):
            self.verified_owner(db, client)
            routes = (('GET', '/usage/companies', None), ('GET', '/usage/models', None), ('GET', '/usage/totals', None),
                      ('GET', '/prices', None), ('POST', '/prices', {'upstream_id': 'up/m', 'input_micros': 1, 'output_micros': 1}))
            for account in (results[0].accounts[0], results[0].accounts[1], results[1].accounts[0]):
                headers = login(client, account)
                for method, path, body in routes:
                    with self.subTest(account=account.email, path=path):
                        response = client.request(method, BASE + path, headers=headers, params=RANGE if path.startswith('/usage') else None, json=body)
                        self.assertEqual((response.status_code, response.json()['error']['code']), (403, 'PLATFORM_DENIED'))
            self.assertEqual(db.admin.execute('SELECT count(*) FROM forge.model_prices').fetchone(), (0,))

    def test_a_password_only_owner_session_can_neither_read_nor_write_and_bad_ranges_are_refused(self):
        with stack() as (db, client, results, root, secrets):
            add_owner(db.admin)
            headers = login(client, Person(OWNER_EMAIL, PASSWORD))
            self.assertEqual(client.get(BASE + '/usage/totals', headers=headers, params=RANGE).json()['error']['code'], 'MFA_REQUIRED')
        with stack() as (db, client, results, root, secrets):
            owner = self.verified_owner(db, client)
            for params in ({'from': TODAY, 'to': '2025-01-01'}, {'from': '2020-01-01', 'to': TODAY}, {'from': TODAY}):
                self.assertEqual(client.get(BASE + '/usage/totals', headers=owner, params=params).status_code, 422)


if __name__ == '__main__':
    unittest.main()
