"""Executable foundation acceptance cases, runnable without package installation."""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.foundation import (
    AuthenticatedIdentity,
    AuthorizationDenied,
    Membership,
    MembershipStatus,
    Organization,
    OrganizationConfiguration,
    build_public_bootstrap,
)


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.identity = AuthenticatedIdentity("entra", "issuer-a", "subject-a")
        self.organization = Organization("org-a", "company-a", "Company A", True)
        self.membership = Membership(
            "member-a", "org-a", self.identity, MembershipStatus.ACTIVE
        )
        self.configuration = OrganizationConfiguration(
            "org-a", 7,
            {"provider_key": "secret", "router_key": "secret",
             "costs": 50, "admin_fields": {"billing": "private"}},
        )

    def bootstrap(self, **overrides):
        arguments = {
            "identity": self.identity,
            "requested_organization_id": "org-a",
            "membership": self.membership,
            "organization": self.organization,
            "configuration": self.configuration,
        }
        arguments.update(overrides)
        return build_public_bootstrap(**arguments)

    def test_missing_identity_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(identity=None)

    def test_unknown_membership_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(membership=None)

    def test_wrong_requested_organization_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(requested_organization_id="org-b")

    def test_inactive_membership_denied(self):
        for status in (MembershipStatus.SUSPENDED, MembershipStatus.ARCHIVED):
            with self.subTest(status=status), self.assertRaises(AuthorizationDenied):
                self.bootstrap(membership=replace(self.membership, status=status))

    def test_inactive_organization_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(organization=replace(self.organization, active=False))

    def test_active_member_receives_public_bootstrap(self):
        self.assertEqual(self.bootstrap(), {
            "schema_version": "1.0",
            "organization": {
                "id": "org-a", "slug": "company-a", "display_name": "Company A"
            },
            "membership": {"id": "member-a"},
            "config_revision": 7,
        })

    def test_bootstrap_is_allowlisted(self):
        self.configuration.internal_settings["unexpected_secret"] = "must-not-leak"
        result = self.bootstrap()
        self.assertEqual(set(result), {
            "schema_version", "organization", "membership", "config_revision"
        })
        self.assertEqual(set(result["organization"]), {"id", "slug", "display_name"})
        self.assertEqual(set(result["membership"]), {"id"})
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("costs", repr(result))
        self.assertNotIn("admin_fields", repr(result))

    def test_other_subject_denied(self):
        for field in ("provider", "issuer", "subject"):
            with self.subTest(field=field), self.assertRaises(AuthorizationDenied):
                self.bootstrap(identity=replace(self.identity, **{field: "other"}))

    def test_foreign_configuration_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(configuration=replace(self.configuration, organization_id="org-b"))

    def test_foreign_organization_record_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(organization=replace(self.organization, id="org-b"))

    def test_foreign_membership_record_denied(self):
        with self.assertRaises(AuthorizationDenied):
            self.bootstrap(membership=replace(self.membership, organization_id="org-b"))

    def test_empty_identity_fields_denied(self):
        for field in ("provider", "issuer", "subject"):
            for value in (None, "", " "):
                with self.subTest(field=field, value=value):
                    identity = replace(self.identity, **{field: value})
                    with self.assertRaises(AuthorizationDenied):
                        self.bootstrap(identity=identity, membership=replace(
                            self.membership, identity=identity
                        ))

    def test_identity_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            self.identity.subject = "other"


if __name__ == "__main__":
    unittest.main()
