"""Local-stack branding for the two seeded organizations, so a fresh stack shows two different companies.

Everything here is data plus a tiny deterministic PNG drawer: the values pass the same validators and palette
gate as an administrator's save, and the marks pass the same sanitizer as an upload. The operator's
provisioning step writes them directly (revision 1); an administrator edits them afterwards through the API.
"""
from dataclasses import dataclass
import struct
import zlib

SIDE = 128
_SHAPES = ('ring', 'diamond')


def _chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))


def _rgba(color):
    return bytes(int(color[index:index + 2], 16) for index in (1, 3, 5)) + b'\xff'


def mark(primary, accent, shape):
    """A 128x128 transparent isotipo: an outer shape in the primary color with a smaller accent core."""
    if shape not in _SHAPES:
        raise ValueError('Unknown mark shape.')
    outer, inner, clear = _rgba(primary), _rgba(accent), b'\x00\x00\x00\x00'
    center = (SIDE - 1) / 2
    rows = []
    for y in range(SIDE):
        row = bytearray(b'\x00')
        for x in range(SIDE):
            dx, dy = abs(x - center), abs(y - center)
            distance = (dx * dx + dy * dy) ** 0.5 if shape == 'ring' else dx + dy
            row += inner if distance <= 26 else outer if distance <= 60 else clear
        rows.append(bytes(row))
    header = struct.pack('>IIBBBBB', SIDE, SIDE, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
            + _chunk(b'IEND', b''))


@dataclass(frozen=True)
class SeedBranding:
    name: str
    login_copy: str
    primary: str
    accent: str
    tint: str
    heading: str
    body: str
    mark_png: bytes

    def document(self, assets):
        """The administrator save document for these values, with the given asset hashes."""
        return {'name': self.name, 'loginCopy': self.login_copy, 'assets': dict(assets),
                'theme': {'primary': self.primary, 'accent': self.accent, 'tint': self.tint,
                          'heading': self.heading, 'body': self.body}}


SEED_BRANDING = {
    'org-a': SeedBranding('Northwind Logistics', 'Sign in to the Northwind operations workspace.', '#1D4ED8',
                          '#B45309', '#E5E7EB', 'source-sans-3', 'roboto', mark('#1D4ED8', '#B45309', 'ring')),
    'org-b': SeedBranding('Lumen Finance', 'Welcome back. Sign in to the Lumen finance workspace.', '#7C3AED',
                          '#D97706', '#FAE8D0', 'ibm-plex-sans', 'nunito-sans', mark('#7C3AED', '#D97706', 'diamond')),
}
