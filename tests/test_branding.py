"""Pure branding validators: colors, vetted fonts, plain text, WCAG contrast and exact-key parsing.

No database and no network: the server decides feasibility, the clients re-derive the palette.
"""
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import branding
from forge.branding import BrandingInvalid

VECTORS = json.loads((ROOT/'contract'/'branding-palette.vectors.json').read_text('utf-8'))
SHA = 'a' * 64
VALID = {'name': 'Acme Labs', 'loginCopy': 'Sign in to the Acme workspace.',
         'theme': {'primary': '#0B1D26', 'accent': '#E07A2D', 'tint': '#E8DCC1', 'heading': 'montserrat', 'body': 'inter'},
         'assets': {}}


def payload(**changes):
    document = json.loads(json.dumps(VALID))
    for key, value in changes.items():
        if key in document['theme']:
            document['theme'][key] = value
        else:
            document[key] = value
    return document


def reason(call, *args):
    try:
        call(*args)
    except BrandingInvalid as error:
        return error.reason
    raise AssertionError('accepted: %r' % (args,))


class ColorTests(unittest.TestCase):
    def test_accepts_only_six_digit_hex_and_normalizes_case(self):
        self.assertEqual(branding.validate_color('#0b1d26'), '#0B1D26')
        self.assertEqual(branding.validate_color('#E07A2D'), '#E07A2D')

    def test_refuses_names_short_forms_alpha_functions_and_non_strings(self):
        for value in ('red', '#12', '#123', '#12345', '#1234567', '#GGGGGG', '0B1D26', 'rgb(1,2,3)', '#0B1D26ff',
                      ' #0B1D26', '#0B1D26\n', '#0B1D26;', 'url(#0B1D26)', '', None, 12, True, ['#0B1D26']):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_color, value), 'color')

    def test_unicode_digits_and_lookalikes_are_not_hex(self):
        for value in ('#\u0661\u0662\u0663\u0664\u0665\u0666', '#\uff10\uff11\uff12\uff13\uff14\uff15'):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_color, value), 'color')


class FontTests(unittest.TestCase):
    def test_the_vetted_list_is_exactly_six_ids(self):
        self.assertEqual(branding.FONT_IDS, ('inter', 'montserrat', 'source-sans-3', 'ibm-plex-sans', 'nunito-sans', 'roboto'))
        for font in branding.FONT_IDS:
            self.assertEqual(branding.validate_font(font), font)

    def test_unknown_fonts_urls_and_css_are_refused(self):
        for value in ('Comic', 'Inter', 'comic-sans', 'inter, serif', 'https://evil.test/f.woff2', 'inter;color:red',
                      '"Inter"', '', None, 3):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_font, value), 'font')


class TextTests(unittest.TestCase):
    def test_plain_text_is_trimmed_nfc_normalized_and_length_bounded(self):
        self.assertEqual(branding.validate_name('  Acme   Labs '), 'Acme   Labs')
        self.assertEqual(branding.validate_name('Cafe\u0301'), 'Caf\u00e9')
        self.assertEqual(len(branding.validate_name('a' * 40)), 40)
        self.assertEqual(reason(branding.validate_name, 'a' * 41), 'name')
        self.assertEqual(len(branding.validate_login_copy('b' * 280)), 280)
        self.assertEqual(reason(branding.validate_login_copy, 'b' * 281), 'login_copy')

    def test_name_is_required_but_login_copy_may_be_empty(self):
        for value in ('', '   ', '\u00a0'):
            self.assertEqual(reason(branding.validate_name, value), 'name')
        self.assertEqual(branding.validate_login_copy(''), '')

    def test_control_format_and_exotic_separator_characters_are_refused(self):
        for value in ('a\x00b', 'a\nb', 'a\tb', 'a\x7fb', 'a\x85b', 'a\u202eb', 'a\u2066b', 'a\u200bb', 'a\ufeffb',
                      'a\u2028b', 'a\u2029b', 'a\u00a0b', 'a\ue000b', 'a\ud800b', 'a\U000e0041b'):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_name, value), 'name')
                self.assertEqual(reason(branding.validate_login_copy, value), 'login_copy')

    def test_non_strings_are_refused(self):
        for value in (None, 7, b'Acme', ['Acme'], {'a': 1}):
            self.assertEqual(reason(branding.validate_name, value), 'name')

    def test_markup_and_css_structure_characters_never_enter_storage(self):
        hostile = ('}</style><script>alert(1)</script>', 'Acme {color:red}', '<img src=x onerror=alert(1)>',
                   'a\\00003c script', 'x`y', 'p{background:url(//evil.test/x)}', '</title><svg/onload=alert(1)>')
        for value in hostile:
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_name, value), 'name')
                self.assertEqual(reason(branding.validate_login_copy, value), 'login_copy')

    def test_inert_lookalikes_are_stored_verbatim_and_never_become_markup(self):
        for value in ('x;background:url(//evil.test/a)', "Acme's \"best\" & more", 'a/*b*/c', 'expression(alert(1))',
                      '\u00c5ngstr\u00f6m \u2014 \u65e5\u672c\u8a9e'):
            with self.subTest(value=value):
                self.assertEqual(branding.validate_name(value), value[:40])
                self.assertEqual(branding.validate_login_copy(value), value)
                self.assertFalse(set('<>{}`\\') & set(value))


class ContrastTests(unittest.TestCase):
    def test_wcag_ratios_match_the_published_extremes(self):
        self.assertAlmostEqual(branding.contrast_ratio('#000000', '#FFFFFF'), 21.0, places=9)
        self.assertAlmostEqual(branding.contrast_ratio('#FFFFFF', '#FFFFFF'), 1.0, places=9)
        self.assertAlmostEqual(branding.contrast_ratio('#767676', '#FFFFFF'), 4.54, places=2)
        self.assertEqual(branding.contrast_ratio('#123456', '#FEDCBA'), branding.contrast_ratio('#FEDCBA', '#123456'))

    def test_primary_below_three_to_one_against_white_is_refused_with_a_contrast_reason(self):
        for value in ('#FFFFFF', '#FFFF00', '#E8DCC1', '#CCCCCC', '#959595'):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_primary, value), 'contrast')

    def test_primary_at_or_above_three_to_one_is_accepted(self):
        for value in ('#0B1D26', '#949494', '#767676', '#000000'):
            self.assertEqual(branding.validate_primary(value), value)

    def test_golden_vectors_are_reproduced(self):
        self.assertEqual(VECTORS['version'], 1)
        self.assertEqual(VECTORS['minPrimaryContrast'], branding.MIN_PRIMARY_CONTRAST)
        for item in VECTORS['contrast']:
            with self.subTest(item=item):
                self.assertAlmostEqual(branding.contrast_ratio(item['a'], item['b']), item['ratio'], places=9)
        for item in VECTORS['primary']:
            with self.subTest(item=item):
                if item['ok']:
                    self.assertEqual(branding.validate_primary(item['value']), item['value'].upper())
                else:
                    self.assertEqual(reason(branding.validate_primary, item['value']), item['reason'])
        for item in VECTORS['hex']:
            with self.subTest(item=item):
                if item['normalized'] is None:
                    self.assertEqual(reason(branding.validate_color, item['input']), 'color')
                else:
                    self.assertEqual(branding.validate_color(item['input']), item['normalized'])


class ParseTests(unittest.TestCase):
    def test_a_valid_document_parses_to_a_normalized_value(self):
        parsed = branding.parse(payload(primary='#0b1d26'))
        self.assertEqual((parsed.name, parsed.login_copy, parsed.primary, parsed.accent, parsed.tint),
                         ('Acme Labs', 'Sign in to the Acme workspace.', '#0B1D26', '#E07A2D', '#E8DCC1'))
        self.assertEqual((parsed.heading, parsed.body), ('montserrat', 'inter'))
        self.assertEqual(parsed.assets, {})

    def test_assets_are_optional_and_limited_to_three_content_hashes(self):
        parsed = branding.parse(payload(assets={'logoLight': SHA, 'isotipo': 'b' * 64}))
        self.assertEqual(parsed.assets, {'logoLight': SHA, 'isotipo': 'b' * 64})
        document = payload()
        del document['assets']
        self.assertEqual(branding.parse(document).assets, {})
        for assets in ({'logoLight': SHA.upper()}, {'logoLight': 'abc'}, {'logoLight': 7}, {'logoLight': '../' + 'a' * 61}):
            with self.subTest(assets=assets):
                self.assertEqual(reason(branding.parse, payload(assets=assets)), 'asset')
        for assets in ({'logo': SHA}, {'favicon': SHA}, {'logoLight': SHA, 'logoDark': SHA, 'isotipo': SHA, 'extra': SHA}):
            with self.subTest(assets=assets):
                self.assertEqual(reason(branding.parse, payload(assets=assets)), 'unknown_key')
        self.assertEqual(reason(branding.parse, payload(assets=[SHA])), 'type')

    def test_unknown_missing_and_mistyped_keys_are_refused(self):
        document = payload()
        document['bonus'] = 1
        self.assertEqual(reason(branding.parse, document), 'unknown_key')
        document = payload()
        document['theme']['secondary'] = '#000000'
        self.assertEqual(reason(branding.parse, document), 'unknown_key')
        document = payload()
        del document['name']
        self.assertEqual(reason(branding.parse, document), 'missing_key')
        document = payload()
        del document['theme']['tint']
        self.assertEqual(reason(branding.parse, document), 'missing_key')
        for value in (None, [], 'x', 3):
            self.assertEqual(reason(branding.parse, value), 'type')
            self.assertEqual(reason(branding.parse, payload(theme=value)), 'type')

    def test_each_field_reports_its_own_reason(self):
        self.assertEqual(reason(branding.parse, payload(primary='red')), 'color')
        self.assertEqual(reason(branding.parse, payload(accent='#12')), 'color')
        self.assertEqual(reason(branding.parse, payload(tint='')), 'color')
        self.assertEqual(reason(branding.parse, payload(heading='Comic')), 'font')
        self.assertEqual(reason(branding.parse, payload(body='x')), 'font')
        self.assertEqual(reason(branding.parse, payload(name='a\x00')), 'name')
        self.assertEqual(reason(branding.parse, payload(loginCopy='x' * 281)), 'login_copy')
        self.assertEqual(reason(branding.parse, payload(primary='#FFFF00')), 'contrast')


class DefaultAndPublicTests(unittest.TestCase):
    def test_the_default_is_the_valid_prometheon_theme_at_revision_zero(self):
        default = branding.DEFAULT
        self.assertEqual((default.revision, default.name), (0, 'Prometheon Forge'))
        self.assertEqual((default.primary, default.accent, default.tint), ('#0B1D26', '#E07A2D', '#E8DCC1'))
        self.assertEqual((default.heading, default.body, default.assets), ('montserrat', 'inter', {}))
        self.assertEqual(branding.validate_primary(default.primary), default.primary)
        self.assertEqual(branding.validate_name(default.name), default.name)
        self.assertEqual(branding.validate_login_copy(default.login_copy), default.login_copy)

    def test_public_projection_has_exactly_the_public_fields_and_asset_urls(self):
        parsed = branding.parse(payload(assets={'logoDark': SHA}))
        view = branding.public_view(branding.Branding(3, parsed.name, parsed.login_copy, parsed.primary, parsed.accent,
                                                      parsed.tint, parsed.heading, parsed.body, parsed.assets))
        self.assertEqual(view, {
            'revision': 3, 'name': 'Acme Labs', 'loginCopy': 'Sign in to the Acme workspace.',
            'theme': {'primary': '#0B1D26', 'accent': '#E07A2D', 'tint': '#E8DCC1', 'heading': 'montserrat', 'body': 'inter'},
            'assets': {'logoDark': '/forge/v1/branding/assets/' + SHA}})
        self.assertEqual(json.loads(json.dumps(view)), view)
        self.assertEqual(branding.public_view(branding.DEFAULT)['assets'], {})

    def test_asset_hash_validation_is_lowercase_sha256_only(self):
        self.assertEqual(branding.validate_asset_hash(SHA), SHA)
        for value in ('A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, '', None, 5, ('a' * 64) + '\n'):
            with self.subTest(value=value):
                self.assertEqual(reason(branding.validate_asset_hash, value), 'asset')


if __name__ == '__main__':
    unittest.main()
