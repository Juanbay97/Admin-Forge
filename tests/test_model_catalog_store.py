"""Canonical private storage format; fixtures are not live router evidence."""
import hashlib
import json
import unittest
from dataclasses import replace
from test_model_catalog import catalog, alias, route, ORG, BINDING, OTHER
from forge.model_catalog_store import CatalogStorageError, encode_catalog, decode_catalog


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CatalogCodecTests(unittest.TestCase):
    def test_roundtrip_and_versioned_deterministic_hash(self):
        snapshot = catalog()
        payload, checksum = encode_catalog(snapshot)
        self.assertEqual(decode_catalog(payload, checksum), snapshot)
        self.assertEqual(checksum, digest(payload))
        self.assertEqual(json.loads(payload)["schema_version"], 1)
        self.assertEqual(encode_catalog(snapshot), (payload, checksum))

    def test_alias_and_route_order_is_canonical(self):
        first = catalog(aliases=(alias("slow", (route(12), route(11))), alias("fast")))
        second = catalog(aliases=(alias("fast"), alias("slow", (route(11), route(12)))))
        self.assertEqual(encode_catalog(first), encode_catalog(second))

    def test_rejects_unknown_fields_versions_and_bad_hash(self):
        payload, checksum = encode_catalog(catalog())
        for key, value in (("schema_version", 2), ("schema_version", True),
                           ("secret", "PRIVATE_MARKER"), ("organization_id", str(OTHER))):
            changed = json.loads(payload)
            changed[key] = value
            text = encoded(changed)
            with self.subTest(key=key), self.assertRaises(CatalogStorageError):
                decode_catalog(text, checksum if key == "organization_id" else digest(text))
        with self.assertRaises(CatalogStorageError):
            decode_catalog(payload, "0" * 64)

    def test_rejects_noncanonical_duplicate_keys_and_json_types(self):
        payload, _ = encode_catalog(catalog())
        for text in (payload + " ", '{"schema_version":1,"schema_version":1}',
                     "[]", "null", "NaN", "{", payload.replace(str(ORG), str(ORG).upper())):
            if text == payload:
                continue
            with self.subTest(text=text[:15]), self.assertRaises(CatalogStorageError):
                decode_catalog(text, digest(text))

    def test_revalidates_private_routes_and_unknown_capabilities(self):
        payload, _ = encode_catalog(catalog())
        for field, value in (("organization_id", str(OTHER)),
                             ("router_binding_id", str(OTHER)),
                             ("verification", "unverified"),
                             ("evidence_id", "../secret")):
            data = json.loads(payload)
            data["aliases"][0]["routes"][0][field] = value
            text = encoded(data)
            with self.subTest(field=field), self.assertRaises(CatalogStorageError):
                decode_catalog(text, digest(text))
        for field, value in (("tools", None), ("max_output_tokens", True),
                             ("input_modalities", ["text", "text"]), ("secret", "bad")):
            data = json.loads(payload)
            data["aliases"][0]["routes"][0]["capabilities"][field] = value
            text = encoded(data)
            with self.subTest(field=field), self.assertRaises(CatalogStorageError):
                decode_catalog(text, digest(text))

    def test_size_and_bigint_boundaries(self):
        with self.assertRaises(CatalogStorageError):
            encode_catalog(replace(catalog(), revision=2**63))
        with self.assertRaises(CatalogStorageError):
            decode_catalog("x" * (1024 * 1024 + 1), "0" * 64)

    def test_no_arbitrary_blob_write_boundary(self):
        for value in ({}, "{}", None):
            with self.assertRaisesRegex(CatalogStorageError, "^Catalog storage unavailable$"):
                encode_catalog(value)

    def test_errors_have_no_raw_payload_cause(self):
        marker = "PRIVATE_PAYLOAD"
        for payload in (marker, '{"organization_id":"' + marker + '"}'):
            with self.assertRaises(CatalogStorageError) as caught:
                decode_catalog(payload, digest(payload))
            self.assertNotIn(marker, str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)

