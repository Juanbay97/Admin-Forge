"""HTTP initial designation: strict adapter boundary and genuine RSA authority."""
from dataclasses import replace
import inspect
from pathlib import Path
import sys
from threading import get_ident
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from forge.api import create_app
from forge.administration import (
    DesignationConflict, DesignationDenied, DesignationRequest, DesignationResult,
    DesignationUnavailable, InitialAdministratorService,
)
import test_administration as crypto_tests
from test_entra import NOW

ORG = UUID(int=1)
MEMBER = UUID(int=21)
SECRET = "PRIVATE_HTTP_CREDENTIAL_CONFIG"
PATH = f"/forge/v1/organizations/{ORG}/initial-administrator"


def body(**changes):
    return dict(membership_id=str(MEMBER), operation_id=str(uuid4()),
                expected_revision=1) | changes


def app_with(service):
    return create_app(initial_administrator_service=service)


class ServiceProbe:
    """Adapter-only fault injection; real authentication is tested separately."""

    def __init__(self):
        self.calls = []
        self.error = None
        self.transform = lambda value: value

    def designate(self, token, request):
        self.calls.append((token, request, get_ident()))
        if self.error is not None:
            raise self.error
        result = DesignationResult(
            request.organization_id, request.membership_id, request.operation_id,
            UUID(int=900), request.expected_revision + 1,
        )
        return self.transform(result)


class HttpAssertions:
    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(set(error), {
            "code", "message", "request_id", "retryable",
            "retry_after_seconds", "reset_at",
        })
        self.assertEqual(error["code"], code)
        self.assertIs(error["retryable"], status == 503)
        self.assertIsNone(error["retry_after_seconds"])
        self.assertIsNone(error["reset_at"])
        self.assertEqual(str(UUID(error["request_id"])), error["request_id"])
        self.assertNotIn(SECRET, response.text)
        if status == 401:
            self.assertEqual(response.headers["www-authenticate"], "Bearer")
        else:
            self.assertNotIn("www-authenticate", response.headers)
        return error

    def post(self, payload=None, headers=None, path=PATH, client=None):
        return (client or self.client).post(
            path, json=payload if payload is not None else body(),
            headers=headers if headers is not None else
            {"Authorization": "Bearer " + SECRET},
        )


class AdministrationHttpTests(HttpAssertions, unittest.TestCase):
    def setUp(self):
        self.service = ServiceProbe()
        self.app = app_with(self.service)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_default_injection_is_keyword_only_and_unavailable(self):
        parameter = inspect.signature(create_app).parameters.get("initial_administrator_service")
        self.assertIsNotNone(parameter)
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)
        with TestClient(create_app()) as client:
            self.assert_error(self.post(client=client), 503, "SERVICE_UNAVAILABLE")
            self.assert_error(self.post(client=client, headers={}), 401, "UNAUTHENTICATED")

    def test_success_is_exact_typed_correlated_and_once_per_attempt(self):
        payload = body()
        first = self.post(payload)
        second = self.post(payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json(), {
            "organization_id": str(ORG), "membership_id": str(MEMBER),
            "operation_id": payload["operation_id"], "event_id": str(UUID(int=900)),
            "revision": 2, "audit_publication": "pending",
        })
        self.assertEqual(len(self.service.calls), 2)
        for token, request, _ in self.service.calls:
            self.assertEqual(token, SECRET)
            self.assertIs(type(request), DesignationRequest)
            self.assertIs(type(request.organization_id), UUID)
            self.assertIs(type(request.membership_id), UUID)
            self.assertIs(type(request.operation_id), UUID)
            self.assertIs(type(request.expected_revision), int)

    def test_header_matrix_rejects_without_service(self):
        values = ["", "Basic " + SECRET, "Bearer", "Bearer ", "Bearer  " + SECRET,
                  "Bearer\t" + SECRET, "Bearer a b", "Bearer a\tb", "Bearer a,b",
                  "Bearer a, Bearer b", " Bearer token", "Bearer token "]
        headers = [{}, *({"Authorization": value} for value in values),
                   [("Authorization", "Bearer a"), ("authorization", "Bearer b")],
                   [("Authorization", "Bearer a"), ("Authorization", "Bearer a")]]
        for header in headers:
            with self.subTest(header_shape=str(header)[:25]):
                self.assert_error(self.post(headers=header), 401, "UNAUTHENTICATED")
        self.assertEqual(self.service.calls, [])

    def test_bearer_scheme_is_case_insensitive(self):
        response = self.post(headers={"Authorization": "bEaReR " + SECRET})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.service.calls), 1)

    def test_missing_header_precedes_field_and_path_validation(self):
        response = self.post({"private": SECRET}, headers={},
                             path=PATH.replace(str(ORG), "invalid"))
        self.assert_error(response, 401, "UNAUTHENTICATED")
        self.assertEqual(self.service.calls, [])

    def test_revision_is_strict_bounded_integer(self):
        for value in (True, False, 0, -1, 1.0, "1", None, 2**63-1, 10**100):
            with self.subTest(value=value):
                self.assert_error(self.post(body(expected_revision=value)), 422, "INVALID_REQUEST")
        self.assertEqual(self.service.calls, [])
        response = self.post(body(expected_revision=2**63-2))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["revision"], 2**63-1)

    def test_extra_missing_uuid_and_nonobject_body_are_invalid(self):
        payloads = [body(actor_id=SECRET), body(roles=["organization_admin"]),
                    body(membership_id=SECRET), body(operation_id=123),
                    body(membership_id=None), [], "private-" + SECRET]
        for field in ("membership_id", "operation_id", "expected_revision"):
            value = body()
            del value[field]
            payloads.append(value)
        for payload in payloads:
            with self.subTest(shape=type(payload).__name__):
                self.assert_error(self.post(payload), 422, "INVALID_REQUEST")
        self.assert_error(self.post(path=PATH.replace(str(ORG), SECRET)), 422, "INVALID_REQUEST")
        self.assertEqual(self.service.calls, [])

    def test_malformed_json_is_redacted(self):
        response = self.client.post(PATH, content='{"private":"' + SECRET,
                                    headers={"Authorization": "Bearer " + SECRET,
                                             "Content-Type": "application/json"})
        self.assert_error(response, 422, "INVALID_REQUEST")
        self.assertEqual(self.service.calls, [])

    def test_typed_and_unknown_errors_have_fixed_envelopes(self):
        for error, status, code in (
            (DesignationDenied(), 403, "DESIGNATION_DENIED"),
            (DesignationConflict(), 409, "DESIGNATION_CONFLICT"),
            (DesignationUnavailable(), 503, "SERVICE_UNAVAILABLE"),
            (RuntimeError(SECRET), 503, "SERVICE_UNAVAILABLE"),
        ):
            self.service.error = error
            with self.subTest(code=code):
                self.assert_error(self.post(), status, code)
        self.assertEqual(len(self.service.calls), 4)

    def test_error_request_ids_are_fresh_and_messages_fixed(self):
        self.service.error = RuntimeError(SECRET)
        one = self.assert_error(self.post(), 503, "SERVICE_UNAVAILABLE")
        two = self.assert_error(self.post(), 503, "SERVICE_UNAVAILABLE")
        self.assertNotEqual(one["request_id"], two["request_id"])
        self.assertEqual(one["message"], "The service is temporarily unavailable.")

    def test_malformed_port_results_never_coerce_or_leak(self):
        transforms = [
            lambda value: None, lambda value: value.__dict__, lambda value: object(),
            lambda value: replace(value, organization_id=uuid4()),
            lambda value: replace(value, membership_id=uuid4()),
            lambda value: replace(value, operation_id=uuid4()),
            lambda value: replace(value, organization_id=str(value.organization_id)),
            lambda value: replace(value, membership_id=str(value.membership_id)),
            lambda value: replace(value, operation_id=str(value.operation_id)),
            lambda value: replace(value, event_id=str(value.event_id)),
            lambda value: replace(value, event_id=None),
            lambda value: replace(value, revision=True),
            lambda value: replace(value, revision=2.0),
            lambda value: replace(value, revision="2"),
            lambda value: replace(value, revision=3),
            lambda value: replace(value, audit_publication=SECRET),
        ]
        class ResultSubclass(DesignationResult):
            pass
        transforms.append(lambda value: ResultSubclass(**value.__dict__))
        for transform in transforms:
            self.service.transform = transform
            self.assert_error(self.post(), 503, "SERVICE_UNAVAILABLE")

    def test_handler_runs_outside_event_loop(self):
        loop_threads = []
        @self.app.middleware("http")
        async def capture_thread(request, call_next):
            loop_threads.append(get_ident())
            return await call_next(request)
        self.assertEqual(self.post().status_code, 200)
        self.assertNotEqual(self.service.calls[0][2], loop_threads[0])

    def test_bootstrap_ports_are_never_consulted(self):
        class Forbidden:
            def validate(self, token):
                raise AssertionError("Bootstrap validator must not run.")
            def read(self, *args):
                raise AssertionError("Bootstrap reader must not run.")
        with TestClient(create_app(Forbidden(), Forbidden(),
                                  initial_administrator_service=self.service)) as client:
            self.assertEqual(self.post(client=client).status_code, 200)
        self.assertEqual(len(self.service.calls), 1)

    def test_runtime_factory_does_not_auto_wire_service(self):
        from forge.runtime import create_runtime_app
        with TestClient(create_runtime_app()) as client:
            self.assert_error(self.post(client=client), 503, "SERVICE_UNAVAILABLE")
            self.assert_error(self.post(client=client, headers={}), 401, "UNAUTHENTICATED")

    def test_injected_route_keeps_native_telemetry_disabled(self):
        for signal in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"):
            self.assertIs(self.app._telemetry[signal], False)
        self.assertEqual(self.post().status_code, 200)

    def test_openapi_declares_closed_request_and_fixed_errors(self):
        schema = self.client.get("/openapi.json").json()
        route = schema["paths"].get(
            "/forge/v1/organizations/{organization_id}/initial-administrator", {})
        self.assertIn("post", route)
        operation = route["post"]
        self.assertEqual(set(operation["responses"]), {"200", "401", "403", "409", "422", "503"})
        model = schema["components"]["schemas"]["InitialAdministratorBody"]
        self.assertIs(model["additionalProperties"], False)
        self.assertEqual(set(model["required"]), {"membership_id", "operation_id", "expected_revision"})
        self.assertEqual(model["properties"]["expected_revision"]["maximum"], float(2**63-2))
        self.assertIn("9223372036854775806", model["properties"]["expected_revision"]["description"])


class AdministrationCryptoHttpTests(HttpAssertions, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.crypto = crypto_tests.AdministrationTests()
        cls.crypto.setUpClass()

    def setUp(self):
        self.crypto.setUp()
        self.client = TestClient(app_with(self.crypto.service))
        self.addCleanup(self.client.close)

    def signed_post(self, **claims):
        return self.post(headers={"Authorization": "Bearer " + self.crypto.token(**claims)})

    def test_actual_signed_operator_reaches_store(self):
        response = self.signed_post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.crypto.store.calls), 1)

    def test_invalid_signature_expiry_claims_and_unprivileged_operator_are_403(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        with patch.object(self.crypto, "key", rsa.generate_private_key(public_exponent=65537, key_size=2048)):
            bad_signature = self.crypto.token()
        tokens = [bad_signature, "not-a-token", self.crypto.token(exp=NOW-90, nbf=NOW-200, iat=NOW-200),
                  self.crypto.token(aud="https://graph.microsoft.com"),
                  self.crypto.token(oid=str(uuid4()), roles=["Global Administrator"], email=SECRET)]
        for token in tokens:
            self.assert_error(self.post(headers={"Authorization": "Bearer " + token}),
                              403, "DESIGNATION_DENIED")
        self.assertEqual(self.crypto.store.calls, [])

    def test_replay_authenticates_again_not_cached(self):
        payload = body()
        token = self.crypto.token()
        with patch.object(self.crypto.validator, "validate_principal",
                          wraps=self.crypto.validator.validate_principal) as validate:
            for _ in range(2):
                self.assertEqual(self.post(payload, headers={"Authorization": "Bearer " + token}).status_code, 200)
            self.assertEqual(validate.call_count, 2)
        self.assert_error(self.post(payload, headers={"Authorization": "Bearer not-a-token"}),
                          403, "DESIGNATION_DENIED")
        self.assertEqual(len(self.crypto.store.calls), 2)

    def test_real_validator_outage_is_503_without_store(self):
        self.crypto.fetcher.error = RuntimeError(SECRET)
        self.assert_error(self.signed_post(), 503, "SERVICE_UNAVAILABLE")
        self.assertEqual(self.crypto.store.calls, [])

    def test_missing_operator_configuration_is_403_without_store(self):
        service = InitialAdministratorService(self.crypto.validator, self.crypto.store)
        with TestClient(app_with(service)) as client:
            self.assert_error(self.post(client=client, headers={
                "Authorization": "Bearer " + self.crypto.token()}), 403, "DESIGNATION_DENIED")
        self.assertEqual(self.crypto.store.calls, [])


if __name__ == "__main__":
    unittest.main()
