"""Pure per-organization branding rules: colors, vetted fonts, plain text, contrast and projection.

Nothing here touches a database or the network. Servers never emit CSS: they store and serve these
typed values, and every client re-validates and applies them with ``style.setProperty``. The
palette expansion lives in the clients; the server only decides whether the three color knobs are
feasible (``branding_palette`` runs the same generator and refuses what it refuses: a primary or accent under
3:1 against white, a tint that cannot carry dark text) and which text and fonts are acceptable.
Reasons are finite codes, never echoes of the submitted value.
"""
from dataclasses import dataclass, field
import re
import unicodedata

from forge import branding_palette

FONT_IDS = ('inter', 'montserrat', 'source-sans-3', 'ibm-plex-sans', 'nunito-sans', 'roboto')
ASSET_KINDS = ('logoLight', 'logoDark', 'isotipo')
MAX_NAME = 40
MAX_LOGIN_COPY = 280
MIN_PRIMARY_CONTRAST = 3.0
ASSET_URL_PREFIX = '/forge/v1/branding/assets/'
THEME_KEYS = frozenset({'primary', 'accent', 'tint', 'heading', 'body'})
DOCUMENT_KEYS = frozenset({'name', 'loginCopy', 'theme', 'assets'})

_HEX = re.compile(r'#[0-9A-Fa-f]{6}')
_SHA256 = re.compile(r'[0-9a-f]{64}')
# Never legitimate in a product name or login line, and the whole HTML/CSS injection alphabet.
_STRUCTURAL = frozenset('<>{}`\\')
# Control, format (bidi, zero width), surrogate, private use, unassigned and line/paragraph separators.
_REFUSED_CATEGORIES = frozenset({'Cc', 'Cf', 'Cs', 'Co', 'Cn', 'Zl', 'Zp'})


class BrandingInvalid(ValueError):
    """``reason`` is one of a finite set of codes: color, font, name, login_copy, contrast, unreadable, asset,
    type, unknown_key, missing_key."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class BrandingInput:
    """A validated, normalized save request (no revision: the store assigns it)."""
    name: str
    login_copy: str
    primary: str
    accent: str
    tint: str
    heading: str
    body: str
    assets: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Branding:
    revision: int
    name: str
    login_copy: str
    primary: str
    accent: str
    tint: str
    heading: str
    body: str
    assets: dict = field(default_factory=dict)


DEFAULT = Branding(0, 'Prometheon Forge', 'Sign in to your Forge workspace.', '#0B1D26', '#E07A2D', '#E8DCC1',
                   'montserrat', 'inter', {})

DEFAULT_INPUT = BrandingInput(DEFAULT.name, DEFAULT.login_copy, DEFAULT.primary, DEFAULT.accent, DEFAULT.tint,
                              DEFAULT.heading, DEFAULT.body, {})


def validate_color(value):
    if type(value) is not str or not _HEX.fullmatch(value):
        raise BrandingInvalid('color')
    return value.upper()


def validate_font(value):
    if type(value) is not str or value not in FONT_IDS:
        raise BrandingInvalid('font')
    return value


def _text(value, limit, reason, *, required):
    if type(value) is not str:
        raise BrandingInvalid(reason)
    text = unicodedata.normalize('NFC', value).strip(' ')
    if (required and not text) or len(text) > limit:
        raise BrandingInvalid(reason)
    for character in text:
        if character in _STRUCTURAL or (character != ' ' and (
                unicodedata.category(character) in _REFUSED_CATEGORIES
                or unicodedata.category(character).startswith('Z'))):
            raise BrandingInvalid(reason)
    return text


def validate_name(value):
    return _text(value, MAX_NAME, 'name', required=True)


def validate_login_copy(value):
    return _text(value, MAX_LOGIN_COPY, 'login_copy', required=False)


def validate_asset_hash(value):
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise BrandingInvalid('asset')
    return value


def _linear(channel):
    channel /= 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(first, second):
    """WCAG 2.x contrast of two ``#RRGGBB`` colors, symmetric, from 1 to 21."""
    lighter, darker = sorted((relative_luminance(validate_color(first)), relative_luminance(validate_color(second))),
                             reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def validate_primary(value):
    color = validate_color(value)
    if contrast_ratio(color, '#FFFFFF') < MIN_PRIMARY_CONTRAST:
        raise BrandingInvalid('contrast')
    return color


def _exact(value, allowed, required=None):
    if type(value) is not dict:
        raise BrandingInvalid('type')
    if set(value) - allowed:
        raise BrandingInvalid('unknown_key')
    if (required or allowed) - set(value):
        raise BrandingInvalid('missing_key')
    return value


def parse(document):
    """Exact-key validation of a save document; the first problem found decides the reason."""
    document = _exact(document, DOCUMENT_KEYS, DOCUMENT_KEYS - {'assets'})
    theme = _exact(document['theme'], THEME_KEYS)
    assets = document.get('assets', {})
    if type(assets) is not dict:
        raise BrandingInvalid('type')
    if set(assets) - set(ASSET_KINDS):
        raise BrandingInvalid('unknown_key')
    parsed = BrandingInput(
        name=validate_name(document['name']), login_copy=validate_login_copy(document['loginCopy']),
        primary=validate_primary(theme['primary']), accent=validate_color(theme['accent']),
        tint=validate_color(theme['tint']), heading=validate_font(theme['heading']), body=validate_font(theme['body']),
        assets={kind: validate_asset_hash(assets[kind]) for kind in ASSET_KINDS if kind in assets})
    if branding_palette.generate(parsed.primary, parsed.accent, parsed.tint, parsed.heading, parsed.body) is None:
        raise BrandingInvalid('unreadable')
    return parsed


def public_view(value):
    """Exactly the public fields; asset hashes become same-origin content-addressed URLs."""
    return {'revision': value.revision, 'name': value.name, 'loginCopy': value.login_copy,
            'theme': {'primary': value.primary, 'accent': value.accent, 'tint': value.tint,
                      'heading': value.heading, 'body': value.body},
            'assets': {kind: ASSET_URL_PREFIX + value.assets[kind] for kind in ASSET_KINDS if kind in value.assets}}
