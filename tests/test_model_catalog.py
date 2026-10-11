"""Pure catalog contracts; all evidence is synthetic, not router inspection."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import traceback
import unittest
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forge.model_catalog import (
    AliasSnapshot, Capabilities, CatalogDenied, CatalogInvalid, CatalogSnapshot,
    Modality, RouteEvidence, Verification,
)


ORG = UUID("00000000-0000-4000-8000-000000000001")
BINDING = UUID("00000000-0000-4000-8000-000000000002")
OTHER = UUID("00000000-0000-4000-8000-000000000003")
TEXT = frozenset({Modality.TEXT})
BOTH = frozenset({Modality.TEXT, Modality.IMAGE})


def capabilities(**changes):
    fields = dict(input_modalities=BOTH, output_modalities=TEXT,
                  tools=True, streaming=True, max_context_tokens=8192,
                  max_output_tokens=2048)
    fields.update(changes)
    return Capabilities(**fields)


def route(number=10, **changes):
    fields = dict(organization_id=ORG, router_binding_id=BINDING,
                  route_id=UUID(int=number), evidence_id=UUID(int=number + 100),
                  verification=Verification.VERIFIED, capabilities=capabilities())
    fields.update(changes)
    return RouteEvidence(**fields)


def alias(name="smart", routes=None):
    return AliasSnapshot(name, (route(),) if routes is None else routes)


def catalog(aliases=None, **changes):
    fields = dict(organization_id=ORG, router_binding_id=BINDING, revision=1,
                  aliases=(alias(),) if aliases is None else aliases)
    fields.update(changes)
    return CatalogSnapshot(**fields)


class ModelCatalogTests(unittest.TestCase):
    def test_verified_alias_keeps_explicit_capabilities(self):
        selected = catalog().select_alias(ORG, "smart")
        self.assertEqual(selected.capabilities, capabilities())
        self.assertEqual(selected.name, "smart")

    def test_all_fallbacks_limit_advertised_capabilities(self):
        restrictive = capabilities(input_modalities=TEXT, tools=False,
                                   streaming=False, max_context_tokens=4096,
                                   max_output_tokens=512)
        result = alias(routes=(route(), route(11, capabilities=restrictive)))
        self.assertEqual(result.capabilities, restrictive)
        reversed_routes = alias(routes=tuple(reversed(result.routes)))
        self.assertEqual(result.capabilities, reversed_routes.capabilities)

    def test_output_modalities_are_also_intersected(self):
        result = alias(routes=(route(capabilities=capabilities(output_modalities=BOTH)),
                               route(11)))
        self.assertEqual(result.capabilities.output_modalities, TEXT)

    def test_disjoint_fallback_modalities_are_rejected(self):
        for field in ("input_modalities", "output_modalities"):
            first = route(capabilities=capabilities(**{field: TEXT}))
            second = route(11, capabilities=capabilities(
                **{field: frozenset({Modality.IMAGE})}))
            with self.subTest(field=field), self.assertRaises(CatalogInvalid):
                alias(routes=(first, second))

    def test_unverified_or_untyped_evidence_is_rejected(self):
        for value in (Verification.UNVERIFIED, "verified", True, None):
            with self.subTest(value=value), self.assertRaises(CatalogInvalid):
                alias(routes=(route(verification=value),))

    def test_cross_organization_and_binding_routes_are_rejected(self):
        for field in ("organization_id", "router_binding_id"):
            foreign = route(11, **{field: OTHER})
            with self.subTest(field=field), self.assertRaises(CatalogInvalid):
                alias(routes=(route(), foreign))
            with self.subTest(root=field), self.assertRaises(CatalogInvalid):
                catalog(aliases=(alias(routes=(foreign,)),))

    def test_duplicate_routes_and_aliases_are_rejected(self):
        with self.assertRaises(CatalogInvalid):
            alias(routes=(route(), route()))
        with self.assertRaises(CatalogInvalid):
            catalog(aliases=(alias(), alias()))

    def test_collections_are_nonempty_strictly_immutable(self):
        for value in ([], [route()], (), None):
            with self.subTest(routes=type(value)), self.assertRaises(CatalogInvalid):
                alias(routes=value) if value is not None else AliasSnapshot("smart", None)
        for value in ([], [alias()], (), None):
            with self.subTest(aliases=type(value)), self.assertRaises(CatalogInvalid):
                CatalogSnapshot(ORG, BINDING, 1, value)
        for value in (set(TEXT), [Modality.TEXT], frozenset(), None,
                      frozenset({"text"}), frozenset({"audio"})):
            with self.subTest(modalities=value), self.assertRaises(CatalogInvalid):
                capabilities(input_modalities=value)

    def test_nested_values_have_exact_domain_types(self):
        with self.assertRaises(CatalogInvalid):
            route(capabilities={"tools": True})
        with self.assertRaises(CatalogInvalid):
            alias(routes=({},))
        with self.assertRaises(CatalogInvalid):
            catalog(aliases=({},))

    def test_limits_are_positive_integers_without_coercion(self):
        for field in ("max_context_tokens", "max_output_tokens"):
            for value in (0, -1, True, 1.0, "8192", None):
                with self.subTest(field=field, value=value), self.assertRaises(CatalogInvalid):
                    capabilities(**{field: value})
        with self.assertRaises(CatalogInvalid):
            capabilities(max_context_tokens=100, max_output_tokens=101)
        self.assertEqual(capabilities(max_context_tokens=1, max_output_tokens=1)
                         .max_output_tokens, 1)

    def test_unknown_support_is_not_advertised(self):
        for field in ("tools", "streaming"):
            for value in (None, 0, 1, "true"):
                with self.subTest(field=field, value=value), self.assertRaises(CatalogInvalid):
                    capabilities(**{field: value})

    def test_identifiers_require_uuid_objects(self):
        for field in ("organization_id", "router_binding_id", "route_id", "evidence_id"):
            for value in (str(ORG), None, "../secret"):
                with self.subTest(field=field), self.assertRaises(CatalogInvalid):
                    route(**{field: value})
        for field in ("organization_id", "router_binding_id"):
            with self.subTest(field=field), self.assertRaises(CatalogInvalid):
                catalog(**{field: str(ORG)})

    def test_aliases_and_revisions_are_strict(self):
        for name in ("", "Smart", " smart", "smart ", "provider/model",
                     "a\n", "a" * 65, 1, None):
            with self.subTest(name=name), self.assertRaises(CatalogInvalid):
                alias(name)
        for revision in (0, -1, True, 1.0, "1", None):
            with self.subTest(revision=revision), self.assertRaises(CatalogInvalid):
                catalog(revision=revision)
        self.assertEqual(alias("fast-v2_1").name, "fast-v2_1")

    def test_exact_lookup_denies_physical_names_and_cross_org(self):
        snapshot = catalog()
        for name in ("gpt-4o", "provider/model", "SMART", "smart ", "", None):
            with self.subTest(name=name), self.assertRaises(CatalogDenied):
                snapshot.select_alias(ORG, name)
        for organization in (OTHER, str(ORG), None):
            with self.subTest(organization=organization), self.assertRaises(CatalogDenied):
                snapshot.select_alias(organization, "smart")

    def test_public_projection_is_explicit_and_detached(self):
        snapshot = catalog()
        public = snapshot.public_projection()
        self.assertEqual(public, {
            "organization_id": str(ORG), "revision": 1,
            "models": [{"id": "smart", "input_modalities": ["image", "text"],
                        "output_modalities": ["text"], "tools": True,
                        "streaming": True, "max_context_tokens": 8192,
                        "max_output_tokens": 2048}],
        })
        serialized = json.dumps(public)
        for private in (str(BINDING), str(route().route_id),
                        str(route().evidence_id), "verified", "internal_settings"):
            self.assertNotIn(private, serialized)
        public["models"][0]["input_modalities"].clear()
        self.assertEqual(snapshot.public_projection()["models"][0]["input_modalities"],
                         ["image", "text"])

    def test_snapshot_and_nested_values_are_frozen(self):
        snapshot = catalog()
        for obj, field, value in (
            (snapshot, "revision", 2), (snapshot.aliases[0], "name", "other"),
            (route(), "verification", Verification.UNVERIFIED),
            (capabilities(), "tools", False),
        ):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(obj, field, value)
        with self.assertRaises(CatalogInvalid):
            replace(snapshot, aliases=[])

    def test_errors_do_not_include_supplied_input(self):
        marker = "SECRET_RAW_INPUT"
        for operation in (lambda: alias(marker),
                          lambda: route(organization_id=marker),
                          lambda: catalog().select_alias(ORG, marker)):
            try:
                operation()
            except (CatalogInvalid, CatalogDenied):
                formatted = traceback.format_exc()
                self.assertNotIn(marker, formatted)
            else:
                self.fail("Invalid input was accepted")


if __name__ == "__main__":
    unittest.main()

