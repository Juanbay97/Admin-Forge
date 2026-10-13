"""Owned PostgreSQL through the composed app: an invitation issued by a company administrator is mailed with the company's public code
(``?c=<code>``) before the fragment, exactly like the platform owner's first-administrator invitation, so the join page is branded."""
import email
from email import policy
from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'tests'))
from test_postgres_mvp_local import login, stack


def mailed_links(root):
    links = []
    for path in sorted((root/'mailbox').glob('*.eml')):
        message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
        links.append(next(line for line in message.get_body(('plain',)).get_content().splitlines() if line.startswith('http')))
    return links


class InvitationCodeTests(unittest.TestCase):
    def test_an_administrator_invitation_link_carries_the_company_code_and_keeps_the_capability_in_the_fragment(self):
        with stack() as (db, client, results, root, secrets):
            first = results[0]
            body = {'organization_id': str(first.organization_id), 'department_id': str(first.department_id), 'email': 'new.person@a.test', 'name': 'New Person'}
            response = client.post('/forge/v1/accounts/invitations', headers=login(client, first.accounts[0]), json=body)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(set(response.json()), {'invitation_id', 'expires_at', 'delivery_state', 'delivery_channel'})
            (link,) = mailed_links(root)
            parts = urlsplit(link)
            self.assertEqual((parts.path, parse_qs(parts.query)), ('/onboarding', {'c': ['org-a']}))
            fragment = parse_qs(parts.fragment)
            self.assertEqual((set(fragment), fragment['invitation_id'][0]), ({'invitation_id', 'capability'}, response.json()['invitation_id']))
            self.assertNotIn('capability', parts.query, 'the capability never travels in the query')

    def test_each_company_gets_its_own_code(self):
        with stack() as (db, client, results, root, secrets):
            for result in results:
                body = {'organization_id': str(result.organization_id), 'department_id': str(result.department_id), 'email': 'p-%s@x.test' % result.organization_id, 'name': 'P'}
                self.assertEqual(client.post('/forge/v1/accounts/invitations', headers=login(client, result.accounts[0]), json=body).status_code, 201)
            self.assertEqual(sorted(parse_qs(urlsplit(link).query)['c'][0] for link in mailed_links(root)), ['org-a', 'org-b'])


if __name__ == '__main__':
    unittest.main()
