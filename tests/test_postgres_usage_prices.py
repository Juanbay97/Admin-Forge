"""Owned PostgreSQL 0036 versioned model prices: an edit is a new audited version, the cost is snapshotted on each event when it
is written (old events keep their price), an unpriced model is flagged not free, and only a fresh verified owner may write."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS
from forge.mvp_profile import F35, F36, MODEL_PRICES_MIGRATION, MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.provisioning import SEED, provision
from mvp_support import at, mvp_database
from platform_support import add_owner, call, refusal, sign_in
from test_postgres_gateway_origin import migration_text, separate_database
from test_postgres_platform_schema import drop_platform_roles
from test_postgres_usage_events import RECORD, UsageWorld

SET = 'SELECT * FROM forge.platform_price_set(%s,%s,%s,%s,%s)'


class PriceProfileTests(unittest.TestCase):
    def test_0036_follows_0035_with_its_own_pinned_checkpoint(self):
        self.assertEqual(MODEL_PRICES_MIGRATION, '0036_model_prices.sql')
        self.assertEqual(MVP_ADDITIONS[at(MODEL_PRICES_MIGRATION) - 1], '0035_usage_events.sql')
        self.assertEqual(MVP_CHECKPOINTS[at(MODEL_PRICES_MIGRATION):at(MODEL_PRICES_MIGRATION) + 2], (F35, F36))
        self.assertRegex(F36 or '', r'^[0-9a-f]{64}$', 'F36 must be pinned')
        self.assertNotEqual(F36, F35)


class PriceFingerprintGateTests(unittest.TestCase):
    def fingerprint(self, conn):
        with conn.cursor() as cursor:
            return catalog_fingerprint(cursor)

    def test_fresh_apply_and_upgrade_from_0035_share_the_pinned_fingerprint(self):
        previous = (*MIGRATIONS, *MVP_ADDITIONS[:at(MODEL_PRICES_MIGRATION)])
        with separate_database() as conn:
            for name in (*previous, MODEL_PRICES_MIGRATION):
                conn.execute(migration_text(name))
            fresh = self.fingerprint(conn)
        drop_platform_roles()
        with separate_database() as conn:
            for name in previous:
                conn.execute(migration_text(name))
            self.assertEqual(self.fingerprint(conn), F35)
            provision(conn, SEED[:1], lambda created: None)
            conn.execute(migration_text(MODEL_PRICES_MIGRATION))
            upgraded = self.fingerprint(conn)
        drop_platform_roles()
        print('Reviewed PG17 0036 model prices checkpoint F36:', fresh)
        self.assertEqual(fresh, upgraded, 'fresh apply and upgrade-from-0035 must be identical')
        self.assertEqual(fresh, F36, 'F36 must be pinned to the reviewed value')


class PriceTests(UsageWorld):
    def owner(self, db, *, mfa=True):
        add_owner(db.admin)
        self.token, self.digest = sign_in(db, mfa=mfa)

    def price(self, upstream, inp, out, starts=None):
        return call(self.db, SET, (self.digest, upstream, inp, out, starts))[0]

    def costs(self):
        return self.db.admin.execute('SELECT upstream_id,price_id,cost_micros FROM forge.usage_events ORDER BY recorded_at').fetchall()

    def test_a_change_is_a_new_version_and_old_events_keep_the_price_they_were_written_under(self):
        with mvp_database() as db:
            self.build(db)
            self.owner(db)
            member = self.members[self.org_a][0]
            v1 = self.price('up/model-a', 2_000_000, 8_000_000)  # $2 and $8 per million tokens, in micro-USD
            self.assertEqual((v1[2], v1[3], v1[4], v1[5]), (1, 2_000_000, 8_000_000, 'USD'))
            self.record(self.org_a, member, prompt=1000, completion=500)  # 1000*2 + 500*8 = 6000 micro-USD
            v2 = self.price('up/model-a', 3_000_000, 9_000_000)
            self.assertEqual(v2[2], 2)
            self.record(self.org_a, member, prompt=1000, completion=500)  # 3000 + 4500
            rows = self.costs()
            self.assertEqual([(row[1], row[2]) for row in rows], [(v1[0], 6000), (v2[0], 7500)])
            self.assertEqual(self.db.admin.execute('SELECT cost_micros,unpriced_requests FROM forge.usage_daily').fetchone(), (13500, 0))
            self.assertEqual([row[2] for row in call(db, 'SELECT * FROM forge.platform_price_list(%s,%s)', (self.digest, 'up/model-a'))], [2, 1])

    def test_a_future_version_is_not_applied_yet_and_rounding_is_half_up_on_integers(self):
        with mvp_database() as db:
            self.build(db)
            self.owner(db)
            member = self.members[self.org_a][0]
            self.price('up/model-a', 1_000_000, 1_000_000)
            self.price('up/model-a', 5_000_000, 5_000_000, '2099-01-01T00:00:00+00:00')
            self.record(self.org_a, member, prompt=1, completion=0)  # 1 token at $1 per million: 1 micro-USD
            self.record(self.org_a, member, prompt=0, completion=1)
            self.record(self.org_a, member, prompt=3, completion=0)
            self.assertEqual([row[2] for row in self.costs()], [1, 1, 3])
            self.price('up/model-b', 500_000, 0)
            self.record(self.org_a, member, upstream='up/model-b', prompt=1, completion=0)  # 0.5 rounds up
            self.assertEqual(self.costs()[-1][2], 1)

    def test_an_unpriced_model_has_no_cost_and_is_flagged_in_the_rollup(self):
        with mvp_database() as db:
            self.build(db)
            member = self.members[self.org_a][0]
            self.record(self.org_a, member, upstream='up/never-priced', prompt=100, completion=50)
            self.assertEqual(self.costs(), [('up/never-priced', None, None)])
            self.assertEqual(db.admin.execute('SELECT cost_micros,unpriced_requests,requests FROM forge.usage_daily').fetchone(), (0, 1, 1))

    def test_only_a_fresh_verified_owner_sets_prices_each_change_is_audited_and_values_are_bounded(self):
        with mvp_database() as db:
            self.build(db)
            self.owner(db, mfa=False)
            self.assertEqual(refusal(self, lambda: self.price('up/model-a', 1, 1)), 'MFA_REQUIRED')
            token, self.digest = sign_in(db, mfa=True)
            self.price('up/model-a', 1, 1)
            for bad in (('up/model-a', -1, 1), ('up/model-a', 1, 10 ** 10), ('bad id', 1, 1), (None, 1, 1)):
                with self.subTest(bad=str(bad)):
                    self.assertEqual(refusal(self, lambda: self.price(*bad)), 'PLATFORM_INVALID')
            self.assertEqual(db.admin.execute("SELECT count(*) FROM forge.model_prices").fetchone(), (1,))
            self.assertEqual([row[0] for row in db.admin.execute('SELECT action FROM forge.platform_audit_log ORDER BY id')], ['model_price.set'])
            for role in ('forge_gateway_service', 'forge_platform_service', 'forge_account_service'):
                self.assertEqual(db.admin.execute("SELECT has_table_privilege(%s,'forge.model_prices','SELECT,INSERT,UPDATE,DELETE')", (role,)).fetchone(), (False,))
            self.assertEqual(db.admin.execute("SELECT has_table_privilege('forge_gateway_authority','forge.model_prices','INSERT,UPDATE')").fetchone(), (False,))


if __name__ == '__main__':
    unittest.main()
