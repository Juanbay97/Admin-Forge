"""Server-side port of the shared palette generator, used only to decide feasibility.

The admin SPA and the client expand three colors into the 26 colors of both modes (see the golden vectors in
``contract/branding-palette.vectors.json``). A palette the generators cannot build is silently ignored by
every app, so the server refuses to store it: ``generate`` is the same integer algorithm and must reproduce
the vectors exactly. The server still never emits CSS; callers only use the result as a yes/no answer.
"""
import re

FONT_FAMILIES = {'inter': 'Inter', 'montserrat': 'Montserrat', 'source-sans-3': 'Source Sans 3',
                 'ibm-plex-sans': 'IBM Plex Sans', 'nunito-sans': 'Nunito Sans', 'roboto': 'Roboto'}
COLOR_TOKENS = (
    '--surface-primary', '--surface-secondary', '--surface-tertiary', '--surface-selected', '--surface-raised',
    '--surface-chat', '--text-primary', '--text-secondary', '--text-tertiary', '--text-quaternary',
    '--border-default', '--border-heavy', '--border-subtle', '--brand-primary', '--brand-primary-hover',
    '--brand-primary-text', '--ring', '--brand-accent', '--ink-solid', '--ink-solid-hover', '--ink-solid-text',
    '--sidebar-bg', '--sidebar-hover', '--sidebar-active', '--user-bubble-bg', '--conversation-body-color')

_HEX = re.compile(r'#[0-9A-Fa-f]{6}')
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
CHARCOAL = (0x1A, 0x1A, 0x1A)


def _parse(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _hex(color):
    return '#' + ''.join('%02X' % channel for channel in color)


def _rgba(color, alpha):
    return 'rgba(%d, %d, %d, %s)' % (*color, alpha)


def _mix(first, second, pct):
    """Per channel round-half-up of a + (b - a) * pct / 100, on integers only."""
    return tuple((2 * (x * (100 - pct) + y * pct) + 100) // 200 for x, y in zip(first, second))


def _luminance(color):
    red, green, blue = ((value / 255 / 12.92) if value / 255 <= 0.03928 else (((value / 255) + 0.055) / 1.055) ** 2.4
                        for value in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first, second):
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _search(color, toward, against, target):
    """The first 5% step from ``color`` toward ``toward`` that reaches ``target`` contrast on ``against``."""
    for pct in range(0, 101, 5):
        candidate = _mix(color, toward, pct)
        if _contrast(candidate, against) >= target:
            return candidate
    return None


def _readable(text, surface, ratio):
    return _contrast(text, surface) >= ratio


def _stack(font):
    return '"%s", "Segoe UI", system-ui, -apple-system, sans-serif' % FONT_FAMILIES[font]


def _tokens(values):
    return dict(zip(COLOR_TOKENS, values))


def _is_hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def generate(primary, accent, tint, heading, body):
    """The light and dark tokens and font stacks for the knobs, or ``None`` when they cannot be readable."""
    if not all(_is_hex(color) for color in (primary, accent, tint)):
        return None
    if heading not in FONT_FAMILIES or body not in FONT_FAMILIES:
        return None
    p, a, t = _parse(primary), _parse(accent), _parse(tint)
    if _contrast(p, WHITE) < 3 or _contrast(a, WHITE) < 3 or _contrast(CHARCOAL, t) < 7:
        return None

    light_secondary, light_tertiary = _mix(WHITE, t, 20), _mix(WHITE, t, 40)
    text2, text3, text4 = _parse('#4A4F52'), _parse('#656A6D'), _parse('#8A8E90')
    if _contrast(text3, light_tertiary) < 4.5:
        return None
    light_brand = _search(p, BLACK, light_tertiary, 4.5)
    if light_brand is None:
        return None
    light_ink = _mix(light_brand, BLACK, 70)
    for surface in (WHITE, light_secondary):
        if not (_readable(CHARCOAL, surface, 7) and _readable(text2, surface, 4.5) and _readable(text3, surface, 4.5)
                and _readable(light_brand, surface, 4.5)):
            return None
    if not (_readable(WHITE, light_brand, 4.5) and _readable(WHITE, light_ink, 7)):
        return None

    light = _tokens((
        '#FFFFFF', _hex(light_secondary), _hex(light_tertiary), _hex(t), _hex(_mix(WHITE, t, 30)), '#FFFFFF',
        _hex(CHARCOAL), _hex(text2), _hex(text3), _hex(text4),
        _hex(_mix(WHITE, t, 60)), _hex(_mix(t, BLACK, 8)), 'rgba(26, 26, 26, 0.08)',
        _hex(light_brand), _hex(_mix(light_brand, BLACK, 20)), '#FFFFFF', _hex(light_brand), _hex(a),
        _hex(light_ink), _hex(_mix(light_brand, BLACK, 50)), '#FFFFFF',
        _hex(_mix(WHITE, t, 25)), _hex(_mix(WHITE, t, 50)), _hex(t), _hex(_mix(WHITE, t, 22)), _hex(CHARCOAL)))

    base = _mix(p, BLACK, 85)
    dark_secondary, dark_tertiary = _mix(p, BLACK, 78), _mix(p, BLACK, 72)
    dark_text = _mix(t, WHITE, 30)
    dark_text2, dark_text3, dark_text4 = (_mix(dark_text, base, pct) for pct in (25, 45, 60))
    dark_brand = _search(p, WHITE, dark_tertiary, 4.5)
    dark_accent = _search(a, WHITE, base, 3)
    if dark_brand is None or dark_accent is None:
        return None
    for surface in (base, dark_secondary):
        if not (_readable(dark_text, surface, 7) and _readable(dark_text2, surface, 4.5)
                and _readable(dark_text3, surface, 4.5) and _readable(dark_brand, surface, 4.5)):
            return None
    if not (_readable(base, dark_brand, 4.5) and _readable(base, dark_text, 7)):
        return None

    dark = _tokens((
        _hex(base), _hex(dark_secondary), _hex(dark_tertiary), _hex(_mix(p, BLACK, 62)), _hex(_mix(p, BLACK, 75)),
        _hex(base), _hex(dark_text), _hex(dark_text2), _hex(dark_text3), _hex(dark_text4),
        _hex(_mix(dark_tertiary, dark_text, 12)), _hex(_mix(dark_tertiary, dark_text, 22)), _rgba(t, '0.08'),
        _hex(dark_brand), _hex(_mix(dark_brand, WHITE, 20)), _hex(base), _hex(dark_brand), _hex(dark_accent),
        _hex(dark_text), _hex(_mix(dark_text, WHITE, 30)), _hex(base),
        _hex(_mix(p, BLACK, 90)), _rgba(t, '0.06'), _rgba(t, '0.10'), _hex(dark_secondary), _hex(dark_text)))

    return {'light': light, 'dark': dark, 'fonts': {'--font-heading': _stack(heading), '--font-body': _stack(body)}}
