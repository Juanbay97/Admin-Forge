"""The shared palette vectors: one file for the Python validators, the admin SPA and the client.

The generators live in TypeScript (admin and client). Here the control plane proves that the vectors are
well formed, that the server accepts every `valid` input and refuses every `infeasible` one (the generator
port itself is proven against the vectors in test_branding_palette), and that the client's copy of the palette vectors has not drifted (line endings normalised).
"""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import branding
from forge.branding import BrandingInvalid

CONTRACT = ROOT/'contract'/'branding-palette.vectors.json'
CLIENT_COPY = Path('clients', 'openyak', 'frontend', 'tests', 'fixtures', 'branding-palette.vectors.json')
TOKEN_COUNT = 26
FONT_VARIABLES = {'--font-heading', '--font-body'}
FONT_FAMILIES = {'inter': 'Inter', 'montserrat': 'Montserrat', 'source-sans-3': 'Source Sans 3',
                 'ibm-plex-sans': 'IBM Plex Sans', 'nunito-sans': 'Nunito Sans', 'roboto': 'Roboto'}


def load(path):
    return json.loads(path.read_bytes().decode('utf-8').replace('\r\n', '\n'))


def client_copy():
    """The client is a separate checkout: look next to this tree and in each parent."""
    for directory in (ROOT, *ROOT.parents):
        candidate = directory/CLIENT_COPY
        if candidate.is_file():
            return candidate
    return None


def document(item):
    theme = item['input']
    return {'name': 'Vector Co', 'loginCopy': '', 'theme': dict(theme), 'assets': {}}


VECTORS = load(CONTRACT)


class VectorShapeTests(unittest.TestCase):
    def test_the_file_carries_every_section_the_generators_need(self):
        self.assertEqual(VECTORS['version'], 1)
        for section in ('algorithm', 'contrast', 'primary', 'hex', 'valid', 'infeasible'):
            self.assertIn(section, VECTORS)
        self.assertGreaterEqual(len(VECTORS['valid']), 6)
        self.assertGreaterEqual(len(VECTORS['infeasible']), 5)

    def test_every_valid_vector_expands_to_26_colors_per_mode_and_two_font_stacks(self):
        for item in VECTORS['valid']:
            with self.subTest(item=item['name']):
                self.assertEqual(len(item['light']), TOKEN_COUNT)
                self.assertEqual(set(item['light']), set(item['dark']))
                self.assertEqual(set(item['fonts']), FONT_VARIABLES)
                self.assertEqual(item['fonts']['--font-heading'].split(',')[0].strip('"'),
                                 FONT_FAMILIES[item['input']['heading']])
                self.assertEqual(item['fonts']['--font-body'].split(',')[0].strip('"'),
                                 FONT_FAMILIES[item['input']['body']])
                for value in (*item['light'].values(), *item['dark'].values()):
                    self.assertRegex(value, r'^(#[0-9A-F]{6}|rgba\(\d{1,3}, \d{1,3}, \d{1,3}, 0\.\d+\))$')

    def test_the_font_ids_used_by_the_vectors_are_the_server_list(self):
        self.assertEqual(tuple(FONT_FAMILIES), branding.FONT_IDS)


class ServerAgreementTests(unittest.TestCase):
    def test_the_server_accepts_every_valid_vector_input_verbatim(self):
        for item in VECTORS['valid']:
            with self.subTest(item=item['name']):
                parsed = branding.parse(document(item))
                theme = item['input']
                self.assertEqual((parsed.primary, parsed.accent, parsed.tint, parsed.heading, parsed.body),
                                 (theme['primary'], theme['accent'], theme['tint'], theme['heading'], theme['body']))

    def test_the_server_refuses_every_infeasible_vector_with_the_most_specific_reason(self):
        for item in VECTORS['infeasible']:
            with self.subTest(item=item['name']):
                low_primary = (branding.contrast_ratio(item['input']['primary'], '#FFFFFF')
                               < branding.MIN_PRIMARY_CONTRAST)
                with self.assertRaises(BrandingInvalid) as caught:
                    branding.parse(document(item))
                self.assertEqual(caught.exception.reason, 'contrast' if low_primary else 'unreadable')


class DriftTests(unittest.TestCase):
    def test_the_client_keeps_the_same_algorithm_and_palette_vectors(self):
        path = client_copy()
        if path is None:
            self.skipTest('the client checkout is not next to this tree')
        client = load(path)
        for section in ('algorithm', 'valid', 'infeasible'):
            with self.subTest(section=section):
                self.assertEqual(client[section], VECTORS[section])

    def test_the_comparison_ignores_line_endings(self):
        crlf = json.dumps(VECTORS, indent=2).replace('\n', '\r\n')
        scratch = ROOT/'tests'/'.crlf-probe.json'
        try:
            scratch.write_bytes(crlf.encode('utf-8'))
            self.assertEqual(load(scratch), VECTORS)
        finally:
            scratch.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
