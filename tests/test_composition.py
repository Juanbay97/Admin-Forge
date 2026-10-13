"""composition: the wiring shared by the dev (mvp_local) and production profiles; no database."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cryptography.fernet import Fernet
from fastapi import FastAPI
from forge import contract
from forge.composition import RolePools, attest, build_app, open_pools
from forge.gateway_origins import OriginPolicy
from forge.mvp_local import ConfigError, ROLES

ORIGIN = 'https://forge.example.test'


class FakePool:
    created = []

    def __init__(self, conninfo, *, kwargs, **options):
        self.conninfo, self.kwargs, self.options, self.opened = conninfo, kwargs, options, None
        FakePool.created.append(self)

    def open(self, wait=False, timeout=None):
        self.opened = (wait, timeout)


class FailingPool(FakePool):
    def open(self, wait=False, timeout=None):
        if len(FakePool.created) == 3:
            raise RuntimeError('database unavailable')
        super().open(wait, timeout)


class OpenPoolsTests(unittest.TestCase):
    def setUp(self):
        FakePool.created = []

    def test_one_bounded_pool_per_role_in_the_fixed_order_with_the_roles_own_settings(self):
        owned = []
        pools = open_pools(lambda role: {'user': role, 'tag': 'x'}, owned, pool_factory=FakePool)
        self.assertEqual(owned, FakePool.created)
        self.assertEqual([pool.kwargs['user'] for pool in owned], list(ROLES))
        self.assertEqual(pools, RolePools(*owned))
        self.assertEqual((pools.accounts.kwargs['user'], pools.enrollment.kwargs['user'], pools.bootstrap.kwargs['user'],
                          pools.gateway.kwargs['user'], pools.branding.kwargs['user'], pools.platform.kwargs['user']), ROLES)
        for pool in owned:
            self.assertEqual((pool.conninfo, pool.opened), ('', (True, 5)))
            self.assertEqual(pool.options, dict(min_size=1, max_size=2, timeout=1, max_waiting=4, reconnect_timeout=1, open=False))

    def test_a_failure_leaves_every_pool_created_so_far_with_the_caller_to_close(self):
        owned = []
        with self.assertRaises(RuntimeError):
            open_pools(lambda role: {'user': role}, owned, pool_factory=FailingPool)
        self.assertEqual(len(owned), 3)
        self.assertEqual([pool.opened is not None for pool in owned], [True, True, False])


class Ready:
    def __init__(self, value):
        self.value = value

    def check(self):
        return self.value


class AttestTests(unittest.TestCase):
    def pools(self):
        return RolePools(*[object() for _ in ROLES])

    def test_a_ready_schema_returns_the_readiness(self):
        ready = Ready(True)
        self.assertIs(attest(self.pools(), readiness_factory=lambda *pools: ready), ready)

    def test_the_readiness_uses_the_account_bootstrap_and_gateway_pools(self):
        pools, seen = self.pools(), []
        attest(pools, readiness_factory=lambda *given: seen.append(given) or Ready(True))
        self.assertEqual(seen, [(pools.accounts, pools.bootstrap, pools.gateway)])

    def test_a_schema_that_is_not_attested_is_refused_with_the_finite_code(self):
        with self.assertRaises(ConfigError) as caught:
            attest(self.pools(), readiness_factory=lambda *pools: Ready(False))
        self.assertEqual(str(caught.exception), 'SCHEMA_ATTESTATION_FAILED')

    def test_unusable_pools_are_not_ready_with_the_real_readiness(self):
        with self.assertRaises(ConfigError):
            attest(self.pools())


class Channel:
    def deliver(self, message_id, recipient, name, link, *, purpose='invitation'):
        raise AssertionError('not used')


class BuildAppTests(unittest.TestCase):
    def build(self, **change):
        arguments = dict(readiness=Ready(True), delivery_adapter=Channel(), onboarding_origin=ORIGIN,
                         delivery_key=Fernet.generate_key(), gateway_key=Fernet.generate_key(), platform_key=Fernet.generate_key(),
                         gateway_policy=OriginPolicy(frozenset({'https://ia.example.test'})))
        arguments.update(change)
        return build_app(RolePools(*[object() for _ in ROLES]), **arguments)

    def test_the_account_branding_and_gateway_routes_are_wired(self):
        app = self.build()
        self.assertIsInstance(app, FastAPI)
        paths = {route.path for route in app.routes}
        for expected in ('/forge/v1/accounts/login', '/forge/v1/bootstrap', '/forge/v1/contract',
                         '/forge/v1/orgs/{organization_id}/gateway', '/forge/v1/orgs/{organization_id}/members'):
            self.assertIn(expected, paths)
        self.assertTrue(any(path.startswith('/forge/v1/') and 'branding' in path for path in paths), paths)

    def test_the_served_contract_is_exactly_the_committed_pin(self):
        committed = json.loads(contract.COMMITTED_PATH.read_text('utf-8'))
        self.assertEqual(contract.build(self.build()), committed)

    def test_the_composition_owns_no_status_admin_or_host_guard(self):
        paths = {route.path for route in self.build().routes}
        self.assertNotIn('/status', paths)
        self.assertFalse([path for path in paths if path.startswith('/admin')])

    def test_the_delivery_channel_origin_and_key_are_the_ones_supplied(self):
        channel, key = Channel(), Fernet.generate_key()
        delivery = self.build(delivery_adapter=channel, delivery_key=key, onboarding_origin='https://other.example.test')
        coordinators = [route.endpoint for route in delivery.routes if getattr(route, 'endpoint', None)]
        self.assertTrue(coordinators)
        # The coordinator is closed over by the routes: reach it through the app's invitation delivery closure.
        found = [cell.cell_contents for endpoint in coordinators for cell in (endpoint.__closure__ or ())
                 if type(cell.cell_contents).__name__ == 'DeliveryCoordinator']
        self.assertTrue(found)
        self.assertTrue(all(item.adapter is channel and item.origin == 'https://other.example.test' for item in found))


if __name__ == '__main__':
    unittest.main()
