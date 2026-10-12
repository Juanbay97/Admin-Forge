"""The server-side palette feasibility gate: the same algorithm as the admin and client generators,
driven by the shared golden vectors, so the server refuses exactly what the generators refuse."""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import branding, branding_palette
from forge.branding import BrandingInvalid

VECTORS = json.loads((ROOT/'contract'/'branding-palette.vectors.json').read_bytes().decode('utf-8').replace('\r\n', '\n'))


def knobs(item):
    theme = item['input']
    return theme['primary'], theme['accent'], theme['tint'], theme['heading'], theme['body']


def payload(**theme):
    return {'name': 'Gate Co', 'loginCopy': '',
            'theme': {'primary': '#0F6B6D', 'accent': '#E07A2D', 'tint': '#E8DCC1', 'heading': 'inter', 'body': 'inter',
                      **theme}, 'assets': {}}


def reason(document):
    try:
        branding.parse(document)
    except BrandingInvalid as error:
        return error.reason
    return None


class GeneratorParityTests(unittest.TestCase):
    def test_every_valid_vector_expands_to_the_exact_golden_palette(self):
        for item in VECTORS['valid']:
            with self.subTest(item=item['name']):
                palette = branding_palette.generate(*knobs(item))
                self.assertIsNotNone(palette)
                self.assertEqual(palette['light'], item['light'])
                self.assertEqual(palette['dark'], item['dark'])
                self.assertEqual(palette['fonts'], item['fonts'])

    def test_every_infeasible_vector_yields_nothing(self):
        for item in VECTORS['infeasible']:
            with self.subTest(item=item['name']):
                self.assertIsNone(branding_palette.generate(*knobs(item)))

    def test_hostile_knobs_yield_nothing_instead_of_raising(self):
        for bad in (('red', '#E07A2D', '#E8DCC1', 'inter', 'inter'), ('#0F6B6D', None, '#E8DCC1', 'inter', 'inter'),
                    ('#0F6B6D', '#E07A2D', '#E8DCC1', 'comic', 'inter'), ('#0F6B6D', '#E07A2D', 7, 'inter', 'inter'),
                    ('#0F6B6D', '#E07A2D', '#E8DCC1\n', 'inter', 'inter')):
            with self.subTest(bad=bad):
                self.assertIsNone(branding_palette.generate(*bad))

    def test_the_default_branding_is_itself_feasible(self):
        default = branding.DEFAULT
        self.assertIsNotNone(branding_palette.generate(default.primary, default.accent, default.tint,
                                                       default.heading, default.body))

    def test_the_font_list_is_the_servers(self):
        self.assertEqual(tuple(branding_palette.FONT_FAMILIES), branding.FONT_IDS)


class ServerGateTests(unittest.TestCase):
    def test_the_server_refuses_exactly_what_the_generator_refuses(self):
        for item in (*VECTORS['valid'], *VECTORS['infeasible']):
            with self.subTest(item=item['name']):
                generator_refuses = branding_palette.generate(*knobs(item)) is None
                self.assertEqual(reason({'name': 'Vector Co', 'loginCopy': '', 'theme': dict(item['input']), 'assets': {}})
                                 is not None, generator_refuses)

    def test_an_accent_below_three_to_one_is_refused_with_a_readable_reason(self):
        self.assertEqual(reason(payload(accent='#FFEB3B')), 'unreadable')

    def test_a_tint_that_cannot_carry_dark_text_is_refused_with_a_readable_reason(self):
        for tint in ('#000000', '#4A5568'):
            with self.subTest(tint=tint):
                self.assertEqual(reason(payload(tint=tint)), 'unreadable')

    def test_syntax_and_primary_contrast_keep_their_own_more_specific_reasons(self):
        self.assertEqual(reason(payload(primary='red')), 'color')
        self.assertEqual(reason(payload(accent='#12')), 'color')
        self.assertEqual(reason(payload(heading='Comic')), 'font')
        self.assertEqual(reason(payload(primary='#FFD54F')), 'contrast')

    def test_the_refusal_never_echoes_the_submitted_value(self):
        try:
            branding.parse(payload(accent='#FFEB3B'))
        except BrandingInvalid as error:
            self.assertNotIn('FFEB3B', str(error))
            self.assertNotIn('FFEB3B', error.reason)


if __name__ == '__main__':
    unittest.main()
