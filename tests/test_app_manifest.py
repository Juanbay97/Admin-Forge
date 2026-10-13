"""App manifest validator: the same grammar and finite codes as the client host (forge-extensions/validate.ts)."""
import hashlib
import json
from pathlib import Path
import random
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge.app_manifest import (MANIFEST_MAX_BYTES, PERMISSIONS, ManifestError, canonical_json, manifest_digest, parse_manifest,
                                validate_manifest)

SHA = hashlib.sha256(b'<html></html>').hexdigest()
VALID = {'id': 'acme.hello', 'version': '1.2.3', 'publisher': 'Acme Corp', 'entry': 'index.html', 'permissions': ['ui.title'], 'sha256': SHA}


def code(raw):
    try:
        validate_manifest(raw)
    except ManifestError as error:
        return str(error)
    return None


class ValidManifestTests(unittest.TestCase):
    def test_a_conformant_manifest_is_accepted_with_its_fields(self):
        manifest = validate_manifest({**VALID, 'permissions': ['ui.title', 'storage.local'], 'signature': 'abc123=='})
        self.assertEqual((manifest.id, manifest.version, manifest.entry, manifest.permissions, manifest.sha256, manifest.signature),
                         ('acme.hello', '1.2.3', 'index.html', ('ui.title', 'storage.local'), SHA, 'abc123=='))

    def test_the_vocabulary_is_the_one_the_client_implements(self):
        self.assertEqual(PERMISSIONS, ('ui.title', 'storage.local'))

    def test_the_canonical_digest_is_stable_across_key_order_and_ignores_the_signature(self):
        first = validate_manifest({**VALID, 'signature': 'aaaa'})
        shuffled = validate_manifest(dict(reversed(list({**VALID, 'signature': 'bbbb'}.items()))))
        self.assertEqual(manifest_digest(first), manifest_digest(shuffled))
        self.assertEqual(canonical_json(first), json.dumps({k: VALID[k] for k in sorted(VALID)}, sort_keys=True, separators=(',', ':')).encode())
        self.assertNotEqual(manifest_digest(first), manifest_digest(validate_manifest({**VALID, 'version': '1.2.4'})))

    def test_the_text_is_size_checked_before_it_is_parsed(self):
        self.assertEqual(parse_manifest(json.dumps(VALID)).id, 'acme.hello')
        with self.assertRaises(ManifestError) as caught:
            parse_manifest(' ' * (MANIFEST_MAX_BYTES + 1))
        self.assertEqual(str(caught.exception), 'oversize')
        with self.assertRaises(ManifestError) as caught:
            parse_manifest('{not json')
        self.assertEqual(str(caught.exception), 'shape')


class RefusalTests(unittest.TestCase):
    def test_path_traversal_and_non_file_entries_are_refused(self):
        for entry in ('../x.html', '..', 'a/b.html', '/abs.html', 'C:\\x.html', 'x.js', 'a..b.html', 'https://x/y.html', '.hidden.html', ''):
            with self.subTest(entry=entry):
                self.assertEqual(code({**VALID, 'entry': entry}), 'bad_entry')

    def test_unknown_and_missing_keys(self):
        self.assertEqual(code({**VALID, 'extra': 1}), 'unknown_key')
        self.assertEqual(code({**VALID, '__proto__': {}}), 'unknown_key')
        for key in ('id', 'version', 'publisher', 'entry', 'permissions', 'sha256'):
            self.assertEqual(code({k: v for k, v in VALID.items() if k != key}), 'missing_key')

    def test_permissions_unknown_reserved_wildcard_and_duplicate(self):
        self.assertEqual(code({**VALID, 'permissions': ['camera']}), 'unknown_permission')
        for reserved in ('network', 'network.*', 'network.example.com', '*.example.com', 'fs.read', 'tools.bash'):
            with self.subTest(permission=reserved):
                self.assertIn(code({**VALID, 'permissions': [reserved]}), ('reserved_permission', 'unknown_permission'))
        self.assertEqual(code({**VALID, 'permissions': ['network.*']}), 'reserved_permission')
        self.assertEqual(code({**VALID, 'permissions': ['ui.title', 'ui.title']}), 'duplicate_permission')
        self.assertEqual(code({**VALID, 'permissions': 'ui.title'}), 'bad_permissions')
        self.assertEqual(code({**VALID, 'permissions': [1]}), 'bad_permissions')

    def test_field_grammar(self):
        cases = (('id', 'Hello', 'bad_id'), ('id', 'nodots', 'bad_id'), ('id', 'a..b', 'bad_id'), ('id', 'a.b' + 'c' * 130, 'bad_id'),
                 ('version', '1.2', 'bad_version'), ('version', 'v1.2.3', 'bad_version'), ('publisher', '  ', 'bad_publisher'),
                 ('publisher', 'x\ny', 'bad_publisher'), ('publisher', 'p' * 81, 'bad_publisher'), ('sha256', 'AB' * 32, 'bad_sha256'),
                 ('sha256', 'ab', 'bad_sha256'), ('signature', 'not base64!', 'bad_signature'), ('signature', 5, 'bad_signature'))
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                self.assertEqual(code({**VALID, key: value}), expected)

    def test_non_objects_are_a_shape_error(self):
        for raw in (None, [], 'x', 3, [VALID]):
            self.assertEqual(code(raw), 'shape')

    def test_a_fuzz_of_mutated_manifests_never_raises_anything_but_a_manifest_error(self):
        rng = random.Random(7)
        junk = (None, True, 0, -1, 1.5, '', ' ', '\x00', '../..', [], {}, ['ui.title'], 'a' * 300, '\u202e')
        for _ in range(400):
            raw = dict(VALID)
            for key in rng.sample(sorted(VALID), rng.randint(1, 3)):
                raw[key] = rng.choice(junk)
            if rng.random() < .3:
                raw.pop(rng.choice(sorted(raw)), None)
            try:
                validate_manifest(raw)
            except ManifestError:
                pass


if __name__ == '__main__':
    unittest.main()
