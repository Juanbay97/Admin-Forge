"""Fixture verifier/reader/port boundaries; not live Entra authentication."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.catalog_publication import (
    CatalogPublisher, PublicationRequest, PublicationResult,
    PublicationDenied, PublicationConflict, PublicationUnavailable,
)
from forge.entra import VerifiedPrincipal
from test_authorization import snapshot

ORG, BINDING, OP, MEMBER, EVENT = (UUID(int=n) for n in (1, 2, 3, 21, 4))
TENANT, OBJECT = UUID(int=950), UUID(int=951)
PRINCIPAL = VerifiedPrincipal("fixture-sub", str(TENANT), str(OBJECT),
                             "https://login.microsoftonline.com/" + str(TENANT) + "/v2.0")
REQUEST = PublicationRequest(ORG, BINDING, OP, 0, "a"*64)


class Verifier:
    def __init__(self):
        self.calls = []
        self.principal = PRINCIPAL

    def validate_principal(self, token):
        self.calls.append(token)
        return self.principal


class Reader:
    def read(self, identity, org):
        assert identity == PRINCIPAL.identity and org == str(ORG)
        return snapshot(identity=identity)


class Port:
    def _publish(self, principal, member, request):
        assert principal is PRINCIPAL and member == MEMBER
        return PublicationResult(ORG, BINDING, OP, EVENT, 1)


class CatalogPublisherTests(unittest.TestCase):
    def setUp(self):
        self.verifier = Verifier()
        self.service = CatalogPublisher(self.verifier, Reader(), Port())

    def test_every_attempt_including_replay_verifies_again(self):
        self.assertEqual(self.service.publish("fixture-token", REQUEST),
                         self.service.publish("fixture-token", REQUEST))
        self.assertEqual(len(self.verifier.calls), 2)
        self.verifier.principal = None
        with self.assertRaises(PublicationDenied):
            self.service.publish("fixture-token", REQUEST)
        self.assertEqual(len(self.verifier.calls), 3)

    def test_request_types_limits_and_actor_injection_deny(self):
        for change in (dict(expected_revision=True), dict(expected_revision=-1),
                       dict(expected_revision=2**63-1), dict(organization_id="bad"),
                       dict(payload_sha256="BAD"), dict(operation_id=None)):
            with self.subTest(change=change), self.assertRaises(PublicationDenied):
                self.service.publish("fixture-token", replace(REQUEST, **change))
        with self.assertRaises(TypeError):
            PublicationRequest(ORG, BINDING, OP, 0, "a"*64, actor_id=MEMBER)
        with self.assertRaises(FrozenInstanceError):
            REQUEST.operation_id = EVENT

    def test_malformed_principal_or_discovery_is_not_authority(self):
        for principal in ({}, replace(PRINCIPAL, tid="bad"), replace(PRINCIPAL, issuer="bad")):
            self.verifier.principal = principal
            with self.assertRaises(PublicationDenied):
                self.service.publish("fixture-token", REQUEST)
        self.verifier.principal = PRINCIPAL
        class WrongReader:
            def read(self, identity, org):
                return snapshot(organization_id=BINDING)
        with self.assertRaises(PublicationDenied):
            CatalogPublisher(self.verifier, WrongReader(), Port()).publish("fixture-token", REQUEST)

    def test_fixed_errors_suppress_raw_provider_and_port_details(self):
        class Broken:
            def validate_principal(self, token):
                raise RuntimeError("PRIVATE_TOKEN_AND_URL")
        class BrokenPort:
            def _publish(self, *args):
                raise RuntimeError("PRIVATE_DATABASE")
        for service in (CatalogPublisher(Broken(), Reader(), Port()),
                        CatalogPublisher(self.verifier, Reader(), BrokenPort())):
            with self.assertRaises(PublicationUnavailable) as caught:
                service.publish("fixture-token", REQUEST)
            self.assertNotIn("PRIVATE", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)
            self.assertTrue(caught.exception.__suppress_context__)

    def test_malformed_result_is_not_coerced(self):
        class BadPort:
            def _publish(self, *args):
                return PublicationResult(ORG, BINDING, OP, EVENT, True)
        with self.assertRaises(PublicationUnavailable):
            CatalogPublisher(self.verifier, Reader(), BadPort()).publish("fixture-token", REQUEST)

    def test_conflict_is_fixed_and_non_authorizing(self):
        class ConflictPort:
            def _publish(self, *args):
                raise PublicationConflict()
        with self.assertRaises(PublicationConflict):
            CatalogPublisher(self.verifier, Reader(), ConflictPort()).publish("fixture-token", REQUEST)

    def test_timeout_configuration_rejects_unbounded_and_untyped_values(self):
        from forge.catalog_publication_store import PostgresCatalogPublisher
        for value in (True, 0, -1, 31, float("nan"), float("inf"), 10**400, "1"):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                PostgresCatalogPublisher(None, acquisition_timeout=value)
