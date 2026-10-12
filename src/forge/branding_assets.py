"""PNG/WebP sanitizer for organization logos: header parsing and a chunk allow-list rewrite.

Pixels are never decoded, so decompression bombs and decoder bugs are out of reach: the type comes
from the magic bytes, the dimensions from the headers, and the stored file is rebuilt from the
allow-listed chunks only (no text, EXIF, XMP, ICC, animation or trailing data). The sha256 returned
is the hash of the stored bytes. Rejections carry a finite HTTP status and reason, never the input.
"""
from dataclasses import dataclass
import hashlib
import struct
import zlib

MAX_BYTES = 256 * 1024
MIN_SIDE = 16
MAX_SIDE = 1024
ALLOWED_TYPES = ('image/png', 'image/webp')
REJECTION_STATUSES = frozenset({413, 415, 422})

_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_PNG_KEEP = frozenset({b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'})
_PNG_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
_WEBP_ANIMATION = frozenset({b'ANIM', b'ANMF'})
_WEBP_ALPHA_FLAG = 0x10
_WEBP_ANIMATION_FLAG = 0x02
# Markup a browser could be tricked into running if the bytes were ever sniffed as HTML or SVG.
_MARKUP = (b'<svg', b'<script', b'<html', b'<?xml', b'<!doctype', b'javascript:')


class AssetRejected(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status, self.reason = status, reason


@dataclass(frozen=True)
class Asset:
    content_type: str
    data: bytes
    sha256: str
    width: int
    height: int


def _malformed():
    return AssetRejected(422, 'malformed')


def _check_dimensions(width, height):
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise AssetRejected(422, 'dimensions')


def _png(data):
    position, kept, seen = len(_PNG_SIGNATURE), [], []
    width = height = color = depth = None
    palette_entries = 0
    idat_state = 0  # 0 not yet, 1 inside the IDAT run, 2 the run ended
    ended = False
    while position < len(data):
        if ended:
            raise AssetRejected(422, 'trailing_data')
        if position + 12 > len(data):
            raise _malformed()
        length = struct.unpack('>I', data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        end = position + 12 + length
        if end > len(data) or not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in kind) or kind[2] & 0x20:
            raise _malformed()
        body = data[position + 8:position + 8 + length]
        if struct.unpack('>I', data[end - 4:end])[0] != zlib.crc32(kind + body):
            raise _malformed()
        if not seen and kind != b'IHDR':
            raise _malformed()
        if kind != b'IDAT' and idat_state == 1:
            idat_state = 2
        if kind not in _PNG_KEEP:
            if not kind[0] & 0x20:  # critical chunk we do not know: refuse instead of guessing
                raise _malformed()
            position = end
            continue
        if kind == b'IHDR':
            if seen or length != 13:
                raise _malformed()
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            _check_dimensions(width, height)
            if depth not in _PNG_DEPTHS.get(color, ()) or compression or filtering or interlace not in (0, 1):
                raise _malformed()
        elif kind == b'PLTE':
            entries = length // 3
            if (b'PLTE' in seen or idat_state or color in (0, 4) or length % 3
                    or not 1 <= entries <= (2 ** depth if color == 3 else 256)):
                raise _malformed()
            palette_entries = entries
        elif kind == b'tRNS':
            expected_ok = ((color == 0 and length == 2) or (color == 2 and length == 6)
                           or (color == 3 and b'PLTE' in seen and 1 <= length <= palette_entries))
            if b'tRNS' in seen or idat_state or not expected_ok:
                raise _malformed()
        elif kind == b'IDAT':
            if idat_state == 2 or not length:
                raise _malformed()
            idat_state = 1
        elif kind == b'IEND':
            if length or idat_state == 0:
                raise _malformed()
            ended = True
        seen.append(kind)
        kept.append(data[position:end])
        position = end
    if not ended or (color == 3 and b'PLTE' not in seen):
        raise _malformed()
    return width, height, _PNG_SIGNATURE + b''.join(kept)


def _vp8_size(payload):
    if len(payload) < 10 or payload[0] & 1 or payload[3:6] != b'\x9d\x01\x2a':
        raise _malformed()
    width, height = struct.unpack('<HH', payload[6:10])
    return width & 0x3fff, height & 0x3fff


def _vp8l_size(payload):
    if len(payload) < 5 or payload[0] != 0x2f:
        raise _malformed()
    bits = struct.unpack('<I', payload[1:5])[0]
    if bits >> 29:
        raise _malformed()
    return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1


def _webp_chunk(fourcc, payload):
    return fourcc + struct.pack('<I', len(payload)) + payload + (b'\x00' if len(payload) & 1 else b'')


def _webp(data):
    if len(data) < 12 or struct.unpack('<I', data[4:8])[0] != len(data) - 8:
        raise _malformed()
    position, chunks = 12, []
    while position < len(data):
        if position + 8 > len(data):
            raise _malformed()
        fourcc, size = data[position:position + 4], struct.unpack('<I', data[position + 4:position + 8])[0]
        end = position + 8 + size + (size & 1)
        if end > len(data) or not all(32 <= byte <= 126 for byte in fourcc):
            raise _malformed()
        chunks.append((fourcc, data[position + 8:position + 8 + size]))
        position = end
    names = [fourcc for fourcc, _ in chunks]
    if _WEBP_ANIMATION & set(names):
        raise AssetRejected(422, 'animated')
    extended = b'VP8X' in names
    if extended and (names[0] != b'VP8X' or names.count(b'VP8X') != 1):
        raise _malformed()
    images = [item for item in chunks if item[0] in (b'VP8 ', b'VP8L')]
    alpha = [item for item in chunks if item[0] == b'ALPH']
    if len(images) != 1 or len(alpha) > 1 or (alpha and (not extended or images[0][0] != b'VP8 ')):
        raise _malformed()
    width, height = (_vp8_size if images[0][0] == b'VP8 ' else _vp8l_size)(images[0][1])
    _check_dimensions(width, height)
    kept = []
    if extended:
        header = chunks[0][1]
        if len(header) != 10:
            raise _malformed()
        if header[0] & _WEBP_ANIMATION_FLAG:
            raise AssetRejected(422, 'animated')
        canvas = (int.from_bytes(header[4:7], 'little') + 1, int.from_bytes(header[7:10], 'little') + 1)
        _check_dimensions(*canvas)
        if canvas != (width, height):
            raise _malformed()
        kept.append(_webp_chunk(b'VP8X', bytes([header[0] & _WEBP_ALPHA_FLAG]) + b'\x00\x00\x00' + header[4:10]))
        kept.extend(_webp_chunk(*item) for item in alpha)
    kept.append(_webp_chunk(*images[0]))
    body = b'WEBP' + b''.join(kept)
    return width, height, b'RIFF' + struct.pack('<I', len(body)) + body


def sanitize(data, declared_type=None):
    """Validate and rewrite one upload; ``declared_type`` is the caller's claim, never trusted."""
    if type(data) is not bytes:
        raise AssetRejected(415, 'unsupported_type')
    if len(data) > MAX_BYTES:
        raise AssetRejected(413, 'too_large')
    if declared_type is not None and declared_type not in ALLOWED_TYPES:
        raise AssetRejected(415, 'unsupported_type')
    if data.startswith(_PNG_SIGNATURE):
        content_type, parse = 'image/png', _png
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        content_type, parse = 'image/webp', _webp
    else:
        raise AssetRejected(415, 'unsupported_type')
    if declared_type is not None and declared_type != content_type:
        raise AssetRejected(415, 'type_mismatch')
    width, height, stored = parse(data)
    lowered = stored.lower()
    if any(marker in lowered for marker in _MARKUP):
        raise AssetRejected(422, 'embedded_markup')
    return Asset(content_type, stored, hashlib.sha256(stored).hexdigest(), width, height)
