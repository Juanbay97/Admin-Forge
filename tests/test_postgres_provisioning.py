"""Owned PostgreSQL provisioning: real rows, real login, idempotence, atomicity, no secret in output."""
import json
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.account_sessions import PostgresSessionStore, SessionService
from forge.branding_seed import SEED_BRANDING
from forge.branding_store import PostgresBrandingStore
from forge.directory import DirectoryService
from forge.directory_store import PostgresDirectoryStore
from forge.provisioning import MULTIUSER_SEED, OrganizationSpec, SEED, main, provision
from mvp_support import mvp_database
from postgres_support import settings

SPEC = OrganizationSpec(slug='org-a', display_name='Organization A', department='Operations',
                        admin_email='admin@example.com', admin_name='Ada Admin')


def count(db, table):
    return db.admin.execute('SELECT count(*) FROM forge.' + table).fetchone()[0]


def services(db):
    sessions = SessionService(PostgresSessionStore(db.pool('forge_account_service')))
    return sessions, DirectoryService(PostgresDirectoryStore(db.pool('forge_gateway_service')))


class PostgresProvisioningTests(unittest.TestCase):
    def test_provisioned_admin_logs_in_and_discovers_only_that_organization(self):
        with mvp_database() as db:
            delivered = []
            (result,) = provision(db.admin, (SPEC,), delivered.append)
            self.assertEqual(delivered, [(result,)])
            self.assertEqual([(a.email, a.role) for a in result.accounts], [('admin@example.com', 'organization_admin')])
            self.assertIsNone(result.gateway_key)
            sessions, directory = services(db)
            me = directory.me(sessions.login('admin@example.com', result.accounts[0].password).capability)
            self.assertEqual((me.account.email, me.account.display_name), ('admin@example.com', 'Ada Admin'))
            (organization,) = me.organizations
            self.assertEqual((organization.id, organization.display_name, organization.roles),
                             (result.organization_id, 'Organization A', ('organization_admin',)))
            self.assertEqual([(d.id, d.name) for d in organization.departments], [(result.department_id, 'Operations')])

    def test_rerun_creates_nothing_and_resets_no_password(self):
        with mvp_database() as db:
            (first,) = provision(db.admin, (SPEC,), lambda results: None)
            tables = ('organizations', 'identities', 'owned_accounts', 'memberships', 'membership_roles',
                      'departments', 'membership_departments', 'configuration_revisions')
            before = {t: count(db, t) for t in tables}
            hashes = db.admin.execute('SELECT canonical_email,password_hash FROM forge.owned_accounts').fetchall()
            self.assertEqual(before['owned_accounts'], 1)
            delivered = []
            self.assertEqual(provision(db.admin, (SPEC,), delivered.append), ())
            self.assertEqual(delivered, [])
            self.assertEqual({t: count(db, t) for t in tables}, before)
            self.assertEqual(db.admin.execute('SELECT canonical_email,password_hash FROM forge.owned_accounts').fetchall(), hashes)
            sessions, _ = services(db)
            self.assertTrue(sessions.login('admin@example.com', first.accounts[0].password).capability)

    def test_two_organization_seed_has_admin_department_member_and_distinct_secrets(self):
        with mvp_database() as db:
            results = provision(db.admin, SEED, lambda results: None)
            self.assertEqual([r.slug for r in results], ['org-a', 'org-b'])
            self.assertEqual([[a.role for a in r.accounts] for r in results],
                             [['organization_admin', 'member']] * 2)
            passwords = [a.password for r in results for a in r.accounts]
            keys = [r.gateway_key for r in results]
            self.assertEqual((len(set(passwords)), len(set(keys)), None in keys), (4, 2, False))
            self.assertEqual((count(db, 'organizations'), count(db, 'departments'), count(db, 'memberships')), (2, 2, 4))
            sessions, directory = services(db)
            for result in results:
                admin, member = result.accounts
                token = sessions.login(admin.email, admin.password).capability
                self.assertEqual([m.email for m in directory.members(token, result.organization_id)],
                                 sorted([admin.email, member.email]))
                me = directory.me(sessions.login(member.email, member.password).capability)
                self.assertEqual([(o.id, o.roles) for o in me.organizations], [(result.organization_id, ('member',))])
                self.assertEqual([d.id for d in me.organizations[0].departments], [result.department_id])

    def test_the_multi_user_seed_gives_one_account_two_active_memberships_and_one_password(self):
        with mvp_database() as db:
            results = provision(db.admin, MULTIUSER_SEED, lambda results: None)
            org_a, org_b = results
            self.assertEqual([a.role for a in org_a.accounts], ['organization_admin', 'member', 'member'])
            # The account exists after the first organization: the second reuses it and issues no credential.
            self.assertEqual([a.role for a in org_b.accounts], ['organization_admin', 'member'])
            shared = org_a.accounts[2]
            self.assertNotIn(shared.email, [a.email for a in org_b.accounts])
            self.assertEqual((count(db, 'organizations'), count(db, 'owned_accounts'), count(db, 'memberships')), (2, 5, 6))
            sessions, directory = services(db)
            me = directory.me(sessions.login(shared.email, shared.password).capability)
            self.assertEqual(sorted((o.id, o.status) for o in me.organizations),
                             sorted([(org_a.organization_id, 'active'), (org_b.organization_id, 'active')]))
            self.assertEqual({o.id: o.roles for o in me.organizations},
                             {org_a.organization_id: ('member',), org_b.organization_id: ('member',)})
            single = directory.me(sessions.login(org_b.accounts[1].email, org_b.accounts[1].password).capability)
            self.assertEqual([o.id for o in single.organizations], [org_b.organization_id])

    def test_the_multi_user_seed_publishes_distinct_branding_and_a_logo_per_organization(self):
        with mvp_database() as db:
            results = provision(db.admin, MULTIUSER_SEED, lambda results: None)
            store = PostgresBrandingStore(db.pool('forge_gateway_service'), db.pool('forge_branding_service'))
            published = {slug: store.public(slug) for slug in ('org-a', 'org-b')}
            self.assertEqual([(slug, item.revision, item.name) for slug, item in published.items()],
                             [('org-a', 1, 'Northwind Logistics'), ('org-b', 1, 'Lumen Finance')])
            self.assertNotEqual(published['org-a'].primary, published['org-b'].primary)
            for slug, item in published.items():
                asset = store.asset(item.assets['isotipo'])
                self.assertEqual((asset.content_type, asset.data), ('image/png', SEED_BRANDING[slug].mark_png))
            history = db.admin.execute('SELECT organization_id,revision,action,actor_id FROM '
                                       'forge.organization_branding_revisions').fetchall()
            admins = {r.organization_id: db.admin.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s',
                                                          (r.accounts[0].email,)).fetchone()[0] for r in results}
            self.assertEqual(sorted(history), sorted((o, 1, 'save', admins[o]) for o in admins))
            self.assertEqual(provision(db.admin, MULTIUSER_SEED, lambda results: None), ())
            self.assertEqual(count(db, 'organization_branding_revisions'), 2)
            self.assertEqual(store.public('org-a').revision, 1)

    def test_the_plain_seed_leaves_both_organizations_on_the_default(self):
        with mvp_database() as db:
            provision(db.admin, SEED, lambda results: None)
            store = PostgresBrandingStore(db.pool('forge_gateway_service'), db.pool('forge_branding_service'))
            self.assertEqual([store.public(slug).revision for slug in ('org-a', 'org-b')], [0, 0])
            self.assertEqual(count(db, 'organization_branding'), 0)

    def test_a_partial_seed_only_creates_the_missing_organization(self):
        with mvp_database() as db:
            (first,) = provision(db.admin, SEED[:1], lambda results: None)
            delivered = []
            (second,) = provision(db.admin, SEED, delivered.append)
            self.assertEqual((second.slug, len(delivered[0])), ('org-b', 1))
            self.assertNotEqual(second.organization_id, first.organization_id)
            self.assertEqual((count(db, 'organizations'), count(db, 'owned_accounts')), (2, 4))

    def test_an_existing_account_is_reused_without_a_new_password(self):
        with mvp_database() as db:
            (first,) = provision(db.admin, (SPEC,), lambda results: None)
            other = OrganizationSpec(slug='org-c', display_name='Organization C', department='Legal',
                                     admin_email='ADMIN@example.com', admin_name='Someone Else')
            (second,) = provision(db.admin, (other,), lambda results: None)
            self.assertEqual(second.accounts, ())
            self.assertEqual(count(db, 'owned_accounts'), 1)
            sessions, directory = services(db)
            me = directory.me(sessions.login('admin@example.com', first.accounts[0].password).capability)
            self.assertEqual(sorted(o.display_name for o in me.organizations), ['Organization A', 'Organization C'])

    def test_a_failed_delivery_rolls_back_every_row(self):
        with mvp_database() as db:
            def refuse(results):
                raise FileExistsError('credentials file exists')
            with self.assertRaises(FileExistsError):
                provision(db.admin, SEED, refuse)
            for table in ('organizations', 'identities', 'owned_accounts', 'memberships', 'departments'):
                self.assertEqual(count(db, table), 0, table)
            self.assertEqual(len(provision(db.admin, SEED, lambda results: None)), 2)

    def test_the_cli_prints_no_secret_and_keeps_credentials_in_a_private_file(self):
        with mvp_database() as db, tempfile.TemporaryDirectory() as directory:
            operator = Path(directory)/'operator.json'
            values = {**settings(), 'dbname': db.admin.info.dbname}
            operator.write_text(json.dumps({k: values[k] for k in ('host', 'port', 'dbname', 'user', 'password')}), 'utf-8')
            credentials = Path(directory)/'credentials.json'
            argv = ['--operator-file', str(operator), '--credentials-file', str(credentials), 'seed']
            out = StringIO()
            self.assertEqual(main(argv, out=out, environ={}), 0)
            report = json.loads(out.getvalue())
            self.assertEqual([(o['slug'], o['created']) for o in report['organizations']], [('org-a', True), ('org-b', True)])
            secrets_text = credentials.read_text('utf-8')
            document = json.loads(secrets_text)
            leaked = [a['password'] for o in document['organizations'] for a in o['accounts']]
            leaked += [o['gateway_key'] for o in document['organizations']] + [values['password']]
            self.assertEqual(len(leaked), 7)
            self.assertFalse([s for s in leaked if s in out.getvalue()])
            self.assertEqual(db.admin.execute("SELECT count(*) FROM forge.owned_accounts WHERE password_hash LIKE 'forge$scrypt$%'")
                             .fetchone()[0], 4)
            self.assertNotIn('forge$scrypt', out.getvalue())
            rerun = StringIO()
            self.assertEqual(main(argv, out=rerun, environ={}), 0)
            self.assertEqual([o['created'] for o in json.loads(rerun.getvalue())['organizations']], [False, False])
            self.assertEqual(credentials.read_text('utf-8'), secrets_text)

    def test_provisioning_is_not_reachable_over_http(self):
        from forge.account_api import create_account_app
        paths = {(method, path) for path, item in create_account_app().openapi()['paths'].items() for method in item}
        self.assertEqual({p for _, p in paths if 'provision' in p or p.rstrip('/') == '/forge/v1/orgs'}, set())
        self.assertNotIn(('post', '/forge/v1/orgs'), paths)


if __name__ == '__main__':
    unittest.main()
