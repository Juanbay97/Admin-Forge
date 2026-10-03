"""HTTP contract tests use injected ports; no live corporate identity or database."""

from dataclasses import replace
from itertools import product
from pathlib import Path
import sys
from threading import get_ident
import unittest
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from forge.api import BootstrapRecords, create_app
from forge.foundation import (
    AuthenticatedIdentity, Membership, MembershipStatus, Organization,
    OrganizationConfiguration,
)


ORG_A = "00000000-0000-0000-0000-000000000001"
ORG_B = "00000000-0000-0000-0000-000000000002"
MEMBER_ID = "00000000-0000-0000-0000-000000000003"
IDENTITY = AuthenticatedIdentity("entra", "https://issuer.example", "subject-1")
SECRET = "SECRET_TOKEN_ROUTER_COST_MARKER"


def records(org_id=ORG_A):
    return BootstrapRecords(
        Membership(MEMBER_ID, org_id, IDENTITY, MembershipStatus.ACTIVE),
        Organization(org_id, "example", "Example", True),
        OrganizationConfiguration(org_id, 12, {"router_key": SECRET, "cost": SECRET}),
    )


class Validator:
    def __init__(self, result=IDENTITY, error=None):
        self.result, self.error, self.calls = result, error, []

    def validate(self, token):
        self.calls.append(token)
        if self.error:
            raise self.error
        return self.result


class Reader:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else records()
        self.error, self.calls = error, []

    def read(self, identity, organization_id):
        self.calls.append((identity, organization_id))
        if self.error:
            raise self.error
        return self.result


class BootstrapHttpTests(unittest.TestCase):
    def setUp(self):
        self.validator, self.reader = Validator(), Reader()
        self.client = TestClient(create_app(self.validator, self.reader))

    def get(self, client=None, org=ORG_A, headers=None):
        return (client or self.client).get(
            "/forge/v1/bootstrap", params={"organization_id": org},
            headers=headers if headers is not None else {"Authorization": "Bearer valid-token"},
        )

    def assert_error(self, response, status, code, retryable=False):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(set(error), {
            "code", "message", "request_id", "retryable", "retry_after_seconds", "reset_at",
        })
        self.assertEqual(error["code"], code)
        self.assertIs(error["retryable"], retryable)
        self.assertIsNone(error["retry_after_seconds"])
        self.assertIsNone(error["reset_at"])
        self.assertEqual(str(UUID(error["request_id"])), error["request_id"])
        self.assertNotIn(SECRET, response.text)
        return error

    def test_default_runtime_denies_every_bearer(self):
        self.assert_error(self.get(TestClient(create_app())), 401, "UNAUTHENTICATED")

    def test_authentication_precedes_query_errors_and_reader(self):
        for query in ("", "?organization_id=invalid", f"?organization_id={ORG_A}"):
            with self.subTest(query=query):
                response = self.client.get("/forge/v1/bootstrap" + query)
                self.assert_error(response, 401, "UNAUTHENTICATED")
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(self.reader.calls, [])
        self.assertEqual(self.validator.calls, [])

    def test_malformed_and_rejected_auth(self):
        for header in ("", "Bearer", "Basic abc", "Bearer a b", "Bearer   "):
            with self.subTest(header=header):
                response = self.get(headers={"Authorization": header})
                self.assert_error(response, 401, "UNAUTHENTICATED")
        self.assertEqual(self.validator.calls, [])
        self.validator.result = None
        self.assert_error(self.get(), 401, "UNAUTHENTICATED")
        self.assertEqual(self.reader.calls, [])

    def test_duplicate_authorization_rejected(self):
        response = self.get(headers=[("Authorization", "Bearer first"), ("Authorization", "Bearer second")])
        self.assert_error(response, 401, "UNAUTHENTICATED")
        self.assertEqual(self.validator.calls, [])

    def test_client_identity_headers_and_cookies_are_not_identity(self):
        response = self.get(headers={
            "X-Subject": IDENTITY.subject, "X-Organization-ID": ORG_A,
            "X-Provider": "entra", "Cookie": "forge_session=valid-token",
        })
        self.assert_error(response, 401, "UNAUTHENTICATED")
        self.assertEqual(self.reader.calls, [])

    def test_invalid_validator_output_never_reaches_reader(self):
        for identity in (None, "subject-1", {}, AuthenticatedIdentity("", "iss", "sub"),
                         AuthenticatedIdentity("entra", None, "sub"),
                         AuthenticatedIdentity("entra", "iss", " ")):
            with self.subTest(identity=identity):
                self.validator.result = identity
                self.assert_error(self.get(), 401, "UNAUTHENTICATED")
        self.assertEqual(self.reader.calls, [])

    def test_allowlisted_response_and_scoped_reader(self):
        response = self.get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "schema_version": "1.0",
            "organization": {"id": ORG_A, "slug": "example", "display_name": "Example"},
            "membership": {"id": MEMBER_ID}, "config_revision": 12,
        })
        self.assertNotIn(SECRET, response.text)
        self.assertEqual(self.reader.calls, [(IDENTITY, ORG_A)])
        self.assertEqual(self.validator.calls, ["valid-token"])

    def test_all_sixteen_organization_combinations(self):
        for requested, member_org, org, config_org in product((ORG_A, ORG_B), repeat=4):
            with self.subTest(ids=(requested, member_org, org, config_org)):
                current = records(org)
                self.reader.result = replace(
                    current, membership=replace(current.membership, organization_id=member_org),
                    configuration=replace(current.configuration, organization_id=config_org),
                )
                response = self.get(org=requested)
                if requested == member_org == org == config_org:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assert_error(response, 404, "NOT_FOUND")

    def test_missing_wrong_identity_inactive_and_archived_hidden(self):
        current = records()
        for result in (
            None, replace(current, membership=None), replace(current, organization=None),
            replace(current, configuration=None),
            replace(current, membership=replace(current.membership, identity=replace(IDENTITY, subject="foreign"))),
            replace(current, organization=replace(current.organization, active=False)),
            replace(current, membership=replace(current.membership, status=MembershipStatus.ARCHIVED)),
        ):
            with self.subTest(result=result):
                self.reader.result = result
                self.assert_error(self.get(), 404, "NOT_FOUND")

    def test_foreign_suspended_membership_remains_hidden(self):
        current = records()
        suspended = replace(current.membership, status=MembershipStatus.SUSPENDED)
        for result in (
            replace(current, membership=replace(suspended, organization_id=ORG_B)),
            replace(current, membership=replace(suspended, identity=replace(IDENTITY, subject="foreign"))),
            replace(current, membership=suspended, configuration=replace(current.configuration, organization_id=ORG_B)),
            replace(current, membership=suspended, organization=replace(current.organization, id=ORG_B)),
            replace(current, membership=suspended, organization=replace(current.organization, active=False)),
        ):
            with self.subTest(result=result):
                self.reader.result = result
                self.assert_error(self.get(), 404, "NOT_FOUND")

    def test_owned_suspension_is_reloaded_each_request(self):
        self.assertEqual(self.get().status_code, 200)
        current = self.reader.result
        self.reader.result = replace(current, membership=replace(current.membership, status=MembershipStatus.SUSPENDED))
        self.assert_error(self.get(), 403, "MEMBERSHIP_SUSPENDED")
        self.assertEqual(len(self.reader.calls), 2)

    def test_both_port_operational_errors_are_redacted(self):
        self.validator.error = RuntimeError(SECRET)
        self.assert_error(self.get(), 503, "SERVICE_UNAVAILABLE", True)
        self.assertEqual(self.reader.calls, [])
        self.validator.error = None
        self.reader.error = RuntimeError(SECRET)
        self.assert_error(self.get(), 503, "SERVICE_UNAVAILABLE", True)

    def test_query_validation_is_structured(self):
        for query in ("", "?organization_id=invalid"):
            with self.subTest(query=query):
                response = self.client.get("/forge/v1/bootstrap" + query, headers={"Authorization": "Bearer token"})
                self.assert_error(response, 422, "INVALID_REQUEST")
        self.assertEqual(self.reader.calls, [])

    def test_request_ids_are_fresh_and_client_id_ignored(self):
        first = self.assert_error(self.get(headers={"X-Request-ID": SECRET}), 401, "UNAUTHENTICATED")
        second = self.assert_error(self.get(headers={}), 401, "UNAUTHENTICATED")
        self.assertNotEqual(first["request_id"], second["request_id"])

    def test_framework_not_found_and_method_denied_are_structured(self):
        self.assert_error(self.client.get("/missing?secret=" + SECRET), 404, "NOT_FOUND")
        self.assert_error(self.client.post("/forge/v1/bootstrap"), 405, "METHOD_NOT_ALLOWED")

    def test_health_is_process_liveness_only(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(self.validator.calls, [])
        self.assertEqual(self.reader.calls, [])

    def test_openapi_security_and_allowlisted_schemas(self):
        schema = self.client.get("/openapi.json").json()
        operation = schema["paths"]["/forge/v1/bootstrap"]["get"]
        self.assertEqual(set(operation["responses"]), {"200", "401", "403", "404", "422", "503"})
        self.assertEqual(operation["security"], [{"ForgeBearer": []}])
        self.assertEqual(schema["components"]["securitySchemes"]["ForgeBearer"]["scheme"], "bearer")
        parameter = operation["parameters"][0]
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["format"], "uuid")
        public = schema["components"]["schemas"]["PublicBootstrap"]["properties"]
        self.assertEqual(set(public), {"schema_version", "organization", "membership", "config_revision"})
        self.assertNotIn("security", schema["paths"]["/healthz"]["get"])

    def test_sync_ports_do_not_execute_on_event_loop_thread(self):
        class ThreadValidator(Validator):
            def validate(inner, token):
                inner.thread_id = get_ident()
                return super().validate(token)

        class ThreadReader(Reader):
            def read(inner, identity, organization_id):
                inner.thread_id = get_ident()
                return super().read(identity, organization_id)

        validator, reader = ThreadValidator(), ThreadReader()
        with TestClient(create_app(validator, reader)) as client:
            async def event_loop_thread():
                return get_ident()
            loop_thread = client.portal.call(event_loop_thread)
            self.assertEqual(self.get(client).status_code, 200)
            self.assertNotEqual(validator.thread_id, loop_thread)
            self.assertNotEqual(reader.thread_id, loop_thread)


if __name__ == "__main__":
    unittest.main()
