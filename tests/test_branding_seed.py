"""The two-organization branded seed: distinct, valid, readable branding and sanitizer-clean logos."""
from pathlib import Path
import struct
import sys
import unittest
import zlib
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import branding, branding_palette
from forge.branding_assets import sanitize
from forge.branding_seed import SEED_BRANDING, SeedBranding, mark
from forge.provisioning import MULTIUSER_SEED, SEED


def png_chunks(data):
    position, chunks = 8, []
    while position < len(data):
        length, kind = struct.unpack('>I4s', data[position:position + 8])
        chunks.append((kind, data[position + 8:position + 8 + length]))
        position += 12 + length
    return chunks


class SeedDefinitionTests(unittest.TestCase):
    def test_both_local_stack_organizations_are_branded_and_the_plain_seed_is_not(self):
        self.assertEqual(sorted(SEED_BRANDING), ['org-a', 'org-b'])
        self.assertEqual([spec.slug for spec in MULTIUSER_SEED], ['org-a', 'org-b'])
        self.assertEqual([spec.branding for spec in MULTIUSER_SEED], [SEED_BRANDING['org-a'], SEED_BRANDING['org-b']])
        self.assertEqual([spec.branding for spec in SEED], [None, None])

    def test_the_two_brandings_are_distinct_and_neither_is_the_prometheon_default(self):
        first, second = SEED_BRANDING['org-a'], SEED_BRANDING['org-b']
        for field in ('name', 'login_copy', 'primary', 'accent', 'tint', 'heading', 'body'):
            self.assertNotEqual(getattr(first, field), getattr(second, field), field)
            for item in (first, second):
                self.assertNotEqual(getattr(item, field), getattr(branding.DEFAULT, field), field)
        self.assertNotEqual(first.mark_png, second.mark_png)

    def test_each_branding_passes_the_server_validators_and_the_palette_gate(self):
        for slug, item in SEED_BRANDING.items():
            with self.subTest(slug=slug):
                self.assertIsInstance(item, SeedBranding)
                parsed = branding.parse(item.document({'isotipo': 'a' * 64}))
                self.assertEqual((parsed.name, parsed.primary), (item.name, item.primary))
                self.assertIsNotNone(branding_palette.generate(item.primary, item.accent, item.tint,
                                                               item.heading, item.body))
                self.assertGreaterEqual(branding.contrast_ratio(item.primary, '#FFFFFF'), 3)


class SeedMarkTests(unittest.TestCase):
    def test_every_mark_is_a_square_png_the_sanitizer_accepts_unchanged(self):
        for slug, item in SEED_BRANDING.items():
            with self.subTest(slug=slug):
                asset = sanitize(item.mark_png, 'image/png')
                self.assertEqual(asset.content_type, 'image/png')
                self.assertEqual((asset.width, asset.height), (128, 128))
                self.assertEqual(asset.data, item.mark_png)
                self.assertLess(len(item.mark_png), 16 * 1024)

    def test_the_mark_is_drawn_deterministically_in_the_brand_colors(self):
        self.assertEqual(mark('#1D4ED8', '#B45309', 'ring'), mark('#1D4ED8', '#B45309', 'ring'))
        self.assertNotEqual(mark('#1D4ED8', '#B45309', 'ring'), mark('#1D4ED8', '#B45309', 'diamond'))
        raw = zlib.decompress(b''.join(data for kind, data in png_chunks(mark('#1D4ED8', '#B45309', 'ring'))
                                       if kind == b'IDAT'))
        pixels = {raw[1 + row * 513 + column * 4: 1 + row * 513 + column * 4 + 4]
                  for row in range(128) for column in range(0, 128, 8)}
        self.assertIn(bytes.fromhex('1D4ED8FF'), pixels)
        self.assertIn(bytes.fromhex('B45309FF'), pixels)

    def test_an_unknown_shape_is_refused(self):
        with self.assertRaises(ValueError):
            mark('#1D4ED8', '#B45309', 'star')


if __name__ == '__main__':
    unittest.main()
