"""PNG/WebP asset sanitizer: header parsing, chunk allow-list rewrite, caps and hostile-input fuzz.

Nothing is ever decoded: dimensions come from headers and only allow-listed chunks survive.
"""
import hashlib
from pathlib import Path
import random
import struct
import sys
import unittest
import zlib
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from forge import branding_assets as assets
from forge.branding_assets import AssetRejected

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunk(kind, data=b''):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def ihdr(width, height, depth=8, color=6, interlace=0):
    return chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, interlace))


def idat(width, height, color=6):
    row = b'\x00' + bytes(width * {6: 4, 2: 3, 0: 1}[color])
    return chunk(b'IDAT', zlib.compress(row * height))


def png(width=300, height=200, *, before=(), after=(), color=6, tail=b''):
    """``before``/``after`` are chunks placed around IDAT (ancillary metadata, palette...)."""
    return SIGNATURE + ihdr(width, height, color=color) + b''.join(before) + idat(width, height, color) + b''.join(after) + chunk(b'IEND') + tail


METADATA = (chunk(b'tEXt', b'Comment\x00<script>alert(1)</script>'), chunk(b'eXIf', b'MM\x00*GPS-LOCATION'),
            chunk(b'iCCP', b'icc\x00\x00' + zlib.compress(b'profile')), chunk(b'gAMA', struct.pack('>I', 45455)),
            chunk(b'pHYs', struct.pack('>IIB', 2835, 2835, 1)), chunk(b'tIME', struct.pack('>HBBBBB', 2026, 10, 11, 1, 2, 3)),
            chunk(b'iTXt', b'XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta/>'), chunk(b'zTXt', b'k\x00\x00' + zlib.compress(b'v')))


def chunk_names(data):
    names, position = [], 8
    while position < len(data):
        length = struct.unpack('>I', data[position:position + 4])[0]
        names.append(data[position + 4:position + 8])
        position += 12 + length
    return names


def riff(*chunks, size=None, kind=b'WEBP'):
    body = kind + b''.join(chunks)
    return b'RIFF' + struct.pack('<I', len(body) if size is None else size) + body


def webp_chunk(fourcc, payload):
    return fourcc + struct.pack('<I', len(payload)) + payload + (b'\x00' if len(payload) % 2 else b'')


def vp8l(width, height, alpha=False):
    bits = ((width - 1) & 0x3fff) | (((height - 1) & 0x3fff) << 14) | (int(alpha) << 28)
    return webp_chunk(b'VP8L', b'\x2f' + struct.pack('<I', bits) + bytes(range(11)))


def vp8(width, height, *, keyframe=True, start=b'\x9d\x01\x2a'):
    tag = b'\x50\x00\x00' if keyframe else b'\x51\x00\x00'
    return webp_chunk(b'VP8 ', tag + start + struct.pack('<HH', width, height) + bytes(range(13)))


def vp8x(width, height, flags=0x10):
    return webp_chunk(b'VP8X', bytes([flags]) + b'\x00\x00\x00' + (width - 1).to_bytes(3, 'little') + (height - 1).to_bytes(3, 'little'))


def webp_names(data):
    names, position = [], 12
    while position < len(data):
        names.append(data[position:position + 4])
        position += 8 + struct.unpack('<I', data[position + 4:position + 8])[0] + (struct.unpack('<I', data[position + 4:position + 8])[0] & 1)
    return names


def rejected(data, declared=None):
    try:
        assets.sanitize(data, declared)
    except AssetRejected as error:
        return error.status, error.reason
    raise AssertionError('accepted')


class PngTests(unittest.TestCase):
    def test_metadata_chunks_are_removed_and_the_hash_covers_the_stored_bytes(self):
        original = png(before=METADATA[:3], after=METADATA[3:])
        stored = assets.sanitize(original, 'image/png')
        self.assertEqual((stored.content_type, stored.width, stored.height), ('image/png', 300, 200))
        self.assertEqual(chunk_names(stored.data), [b'IHDR', b'IDAT', b'IEND'])
        self.assertEqual(stored.sha256, hashlib.sha256(stored.data).hexdigest())
        for secret in (b'tEXt', b'eXIf', b'iCCP', b'GPS-LOCATION', b'script', b'xmpmeta', b'gAMA'):
            self.assertNotIn(secret, stored.data)
        self.assertNotEqual(stored.sha256, hashlib.sha256(original).hexdigest())

    def test_rewriting_is_idempotent_and_deterministic(self):
        first = assets.sanitize(png(before=METADATA))
        again = assets.sanitize(first.data)
        self.assertEqual((again.data, again.sha256), (first.data, first.sha256))
        self.assertEqual(assets.sanitize(png(before=METADATA[::-1])).data, first.data)

    def test_palette_and_transparency_chunks_survive_in_order(self):
        palette = chunk(b'PLTE', bytes(range(12)))
        transparency = chunk(b'tRNS', b'\xff\x80')
        data = SIGNATURE + ihdr(32, 32, depth=2, color=3) + METADATA[0] + palette + transparency + METADATA[3] \
            + chunk(b'IDAT', zlib.compress(b'\x00\x00' * 32)) + chunk(b'IEND')
        self.assertEqual(chunk_names(assets.sanitize(data).data), [b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'])

    def test_multiple_contiguous_idat_chunks_and_interlace_are_kept(self):
        body = zlib.compress(bytes(40))
        data = SIGNATURE + ihdr(16, 16, interlace=1) + chunk(b'IDAT', body[:5]) + chunk(b'IDAT', body[5:]) + chunk(b'IEND')
        self.assertEqual(chunk_names(assets.sanitize(data).data), [b'IHDR', b'IDAT', b'IDAT', b'IEND'])

    def test_apng_animation_chunks_are_dropped(self):
        data = png(before=(chunk(b'acTL', struct.pack('>II', 2, 0)), chunk(b'fcTL', bytes(26))),
                   after=(chunk(b'fdAT', bytes(8)),))
        self.assertEqual(chunk_names(assets.sanitize(data).data), [b'IHDR', b'IDAT', b'IEND'])

    def test_dimension_caps_are_header_checked_without_decoding(self):
        self.assertEqual(assets.sanitize(png(16, 16)).width, 16)
        self.assertEqual(assets.sanitize(png(1024, 1024)).height, 1024)
        for width, height in ((15, 16), (16, 15), (1025, 16), (16, 1025), (2000, 2000), (0, 16), (16, 0), (2 ** 31 - 1, 16)):
            with self.subTest(size=(width, height)):
                data = SIGNATURE + ihdr(width, height) + chunk(b'IDAT', zlib.compress(b'\x00' * 8)) + chunk(b'IEND')
                self.assertEqual(rejected(data), (422, 'dimensions'))

    def test_size_cap_counts_the_uploaded_bytes_not_the_rewritten_ones(self):
        filler = random.Random(7).randbytes(assets.MAX_BYTES - 8 - 25 - 12 - 12)
        exact = SIGNATURE + ihdr(32, 32) + chunk(b'IDAT', filler) + chunk(b'IEND')
        self.assertEqual(len(exact), assets.MAX_BYTES)
        self.assertEqual(assets.sanitize(exact).width, 32)
        self.assertEqual(rejected(exact + b'\x00'), (413, 'too_large'))
        padded = png(before=(chunk(b'tEXt', b'k\x00' + b'v' * assets.MAX_BYTES),))
        self.assertEqual(rejected(padded), (413, 'too_large'))
        self.assertEqual(rejected(b'\x00' * (300 * 1024)), (413, 'too_large'))

    def test_non_images_and_other_formats_are_refused_by_magic_bytes(self):
        hostile = (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', b'<?xml version="1.0"?><svg/>',
                   b'\xef\xbb\xbf<svg/>', b'\xff\xd8\xff\xe0JFIF', b'GIF89a\x01\x00\x01\x00', b'<html><script>1</script>',
                   b'BM' + bytes(60), b'%PDF-1.7', b'', b'\x89PNG', b'RIFF\x04\x00\x00\x00WAVE', b'PK\x03\x04' + bytes(40),
                   b'MZ' + bytes(40), b'#!/bin/sh\n', b'\x89PNG\r\n\x1a')
        for data in hostile:
            with self.subTest(data=data[:16]):
                self.assertEqual(rejected(data), (415, 'unsupported_type'))

    def test_declared_type_must_match_the_magic_bytes(self):
        self.assertEqual(rejected(png(), 'image/webp'), (415, 'type_mismatch'))
        self.assertEqual(rejected(riff(vp8l(32, 32)), 'image/png'), (415, 'type_mismatch'))
        for declared in ('image/svg+xml', 'image/jpeg', 'text/html', 'application/octet-stream', 'image/PNG', ''):
            with self.subTest(declared=declared):
                self.assertEqual(rejected(png(), declared), (415, 'unsupported_type'))
        self.assertEqual(assets.sanitize(png(), None).content_type, 'image/png')

    def test_svg_hidden_behind_a_png_extension_or_header_is_refused(self):
        self.assertEqual(rejected(b'<svg/>', 'image/png'), (415, 'unsupported_type'))
        self.assertEqual(rejected(SIGNATURE + b'<svg onload=alert(1)>'), (422, 'malformed'))

    def test_polyglots_are_refused(self):
        for tail in (b'PK\x03\x04' + bytes(30), b'<script>alert(1)</script>', b'GIF89a;', b'\x00'):
            with self.subTest(tail=tail[:8]):
                self.assertEqual(rejected(png(tail=tail)), (422, 'trailing_data'))
        for payload in (b'<svg onload=alert(1)>', b'<SCRIPT src=//evil>', b'x<html>', b'<?xml version="1.0"?>', b'<!DOCTYPE html>',
                        b'javascript:alert(1)'):
            with self.subTest(payload=payload):
                data = SIGNATURE + ihdr(32, 32) + chunk(b'IDAT', payload + zlib.compress(bytes(8))) + chunk(b'IEND')
                self.assertEqual(rejected(data), (422, 'embedded_markup'))

    def test_structure_violations_are_malformed(self):
        good_idat, end = idat(32, 32), chunk(b'IEND')
        cases = {
            'no ihdr first': SIGNATURE + good_idat + end,
            'no idat': SIGNATURE + ihdr(32, 32) + end,
            'no iend': SIGNATURE + ihdr(32, 32) + good_idat,
            'duplicate ihdr': SIGNATURE + ihdr(32, 32) + ihdr(32, 32) + good_idat + end,
            'split idat': SIGNATURE + ihdr(32, 32) + good_idat + METADATA[0] + good_idat + end,
            'idat after iend': SIGNATURE + ihdr(32, 32) + good_idat + end + good_idat,
            'short ihdr': SIGNATURE + chunk(b'IHDR', bytes(12)) + good_idat + end,
            'unknown critical chunk': SIGNATURE + ihdr(32, 32) + chunk(b'ABCD', b'x') + good_idat + end,
            'bad chunk name': SIGNATURE + ihdr(32, 32) + chunk(b'a1cd', b'x') + good_idat + end,
            'reserved bit set': SIGNATURE + ihdr(32, 32) + chunk(b'tExt', b'x') + good_idat + end,
            'plte for gray': SIGNATURE + ihdr(32, 32, color=0) + chunk(b'PLTE', bytes(3)) + good_idat + end,
            'palette missing': SIGNATURE + ihdr(32, 32, depth=8, color=3) + good_idat + end,
            'plte after idat': SIGNATURE + ihdr(32, 32) + good_idat + chunk(b'PLTE', bytes(3)) + end,
            'bad plte length': SIGNATURE + ihdr(32, 32, depth=8, color=3) + chunk(b'PLTE', bytes(4)) + good_idat + end,
            'depth/color combo': SIGNATURE + ihdr(32, 32, depth=4, color=6) + good_idat + end,
            'bad interlace': SIGNATURE + ihdr(32, 32, interlace=2) + good_idat + end,
            'iend with data': SIGNATURE + ihdr(32, 32) + good_idat + chunk(b'IEND', b'x'),
            'empty idat': SIGNATURE + ihdr(32, 32) + chunk(b'IDAT', b'') + end,
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.assertEqual(rejected(data)[0], 422)

    def test_crc_errors_and_lying_lengths_are_rejected_without_large_allocations(self):
        good = png()
        flipped = bytearray(good)
        flipped[20] ^= 0xFF
        self.assertEqual(rejected(bytes(flipped)), (422, 'malformed'))
        for length in (2 ** 31 - 1, 2 ** 32 - 1, len(good), 12):
            with self.subTest(length=length):
                lying = SIGNATURE + struct.pack('>I', length) + b'IHDR' + bytes(13)
                self.assertEqual(rejected(lying), (422, 'malformed'))

    def test_every_truncation_is_refused_and_never_crashes(self):
        good = png(32, 32, before=METADATA[:2])
        self.assertEqual(assets.sanitize(good).width, 32)
        for cut in range(len(good)):
            with self.subTest(cut=cut):
                self.assertIn(rejected(good[:cut])[0], (415, 422))

    def test_single_byte_corruption_is_refused_or_yields_a_clean_image(self):
        good = png(32, 32, before=METADATA[:2])
        for position in range(len(good)):
            for value in (0x00, 0xFF, good[position] ^ 0x01):
                mutated = good[:position] + bytes([value]) + good[position + 1:]
                try:
                    stored = assets.sanitize(mutated)
                except AssetRejected as error:
                    self.assertIn(error.status, (413, 415, 422))
                else:
                    self.assertLessEqual(set(chunk_names(stored.data)), {b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'})

    def test_random_garbage_with_a_valid_signature_is_refused(self):
        generator = random.Random(2026)
        for _ in range(300):
            data = SIGNATURE + generator.randbytes(generator.randrange(0, 200))
            self.assertIn(rejected(data)[0], (415, 422))


class WebpTests(unittest.TestCase):
    def test_simple_lossless_and_lossy_files_are_accepted(self):
        lossless = assets.sanitize(riff(vp8l(300, 200, alpha=True)), 'image/webp')
        self.assertEqual((lossless.content_type, lossless.width, lossless.height), ('image/webp', 300, 200))
        self.assertEqual(lossless.sha256, hashlib.sha256(lossless.data).hexdigest())
        lossy = assets.sanitize(riff(vp8(64, 48)))
        self.assertEqual((lossy.width, lossy.height), (64, 48))
        self.assertEqual(webp_names(lossy.data), [b'VP8 '])

    def test_extended_metadata_is_removed_and_flags_are_cleaned(self):
        original = riff(vp8x(40, 30, flags=0x10 | 0x20 | 0x08 | 0x04), webp_chunk(b'ICCP', b'icc-profile'),
                        webp_chunk(b'ALPH', bytes(9)), vp8(40, 30), webp_chunk(b'EXIF', b'Exif\x00\x00GPS-LOCATION'),
                        webp_chunk(b'XMP ', b'<x:xmpmeta/>'), webp_chunk(b'JUNK', b'unknown'))
        stored = assets.sanitize(original)
        self.assertEqual(webp_names(stored.data), [b'VP8X', b'ALPH', b'VP8 '])
        for secret in (b'icc-profile', b'GPS-LOCATION', b'xmpmeta', b'unknown', b'ICCP', b'EXIF', b'XMP '):
            self.assertNotIn(secret, stored.data)
        self.assertEqual(stored.data[20], 0x10)
        self.assertEqual(struct.unpack('<I', stored.data[4:8])[0], len(stored.data) - 8)
        self.assertEqual(assets.sanitize(stored.data).data, stored.data)

    def test_odd_sized_chunks_are_padded(self):
        stored = assets.sanitize(riff(vp8l(20, 20)))
        self.assertEqual(len(stored.data) % 2, 0)

    def test_animation_is_refused_by_flag_or_chunk(self):
        self.assertEqual(rejected(riff(vp8x(40, 30, flags=0x02), vp8(40, 30))), (422, 'animated'))
        self.assertEqual(rejected(riff(vp8x(40, 30), webp_chunk(b'ANIM', bytes(6)), vp8(40, 30))), (422, 'animated'))
        self.assertEqual(rejected(riff(vp8x(40, 30), webp_chunk(b'ANMF', bytes(16)))), (422, 'animated'))

    def test_dimension_caps_apply_to_the_bitstream_and_the_canvas(self):
        self.assertEqual(assets.sanitize(riff(vp8l(1024, 1024))).width, 1024)
        self.assertEqual(assets.sanitize(riff(vp8l(16, 16))).height, 16)
        for width, height in ((15, 16), (16, 1025), (2000, 2000), (16384, 16)):
            with self.subTest(size=(width, height)):
                self.assertEqual(rejected(riff(vp8l(width, height))), (422, 'dimensions'))
                self.assertEqual(rejected(riff(vp8(width, height))), (422, 'dimensions'))
        self.assertEqual(rejected(riff(vp8x(2000, 2000), vp8(32, 32))), (422, 'dimensions'))
        self.assertEqual(rejected(riff(vp8x(64, 64), vp8(32, 32))), (422, 'malformed'))

    def test_riff_size_must_match_the_file_exactly(self):
        good = riff(vp8l(32, 32))
        self.assertEqual(rejected(good + b'PK\x03\x04'), (422, 'malformed'))
        self.assertEqual(rejected(good[:-1]), (422, 'malformed'))
        self.assertEqual(rejected(riff(vp8l(32, 32), size=2 ** 32 - 1)), (422, 'malformed'))
        self.assertEqual(rejected(riff(vp8l(32, 32), kind=b'WAVE')), (415, 'unsupported_type'))

    def test_structure_violations_are_malformed(self):
        cases = {
            'no image': riff(vp8x(32, 32)),
            'two images': riff(vp8l(32, 32), vp8l(32, 32)),
            'vp8x not first': riff(vp8l(32, 32), vp8x(32, 32)),
            'alpha with lossless': riff(vp8x(32, 32), webp_chunk(b'ALPH', bytes(4)), vp8l(32, 32)),
            'alpha without vp8x': riff(webp_chunk(b'ALPH', bytes(4)), vp8(32, 32)),
            'inter-frame vp8': riff(vp8(32, 32, keyframe=False)),
            'bad start code': riff(vp8(32, 32, start=b'\x00\x00\x00')),
            'short vp8': riff(webp_chunk(b'VP8 ', bytes(5))),
            'short vp8l': riff(webp_chunk(b'VP8L', b'\x2f\x00')),
            'bad vp8l signature': riff(webp_chunk(b'VP8L', b'\x00' + bytes(10))),
            'vp8l version': riff(webp_chunk(b'VP8L', b'\x2f' + struct.pack('<I', (1 << 29) | 31 | (31 << 14)) + bytes(4))),
            'short vp8x': riff(webp_chunk(b'VP8X', bytes(5)), vp8(32, 32)),
            'chunk overruns file': b'RIFF' + struct.pack('<I', 20) + b'WEBP' + b'VP8L' + struct.pack('<I', 9999) + bytes(8),
            'riff too short': b'RIFF\x04\x00\x00\x00WEBP',
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.assertEqual(rejected(data)[0], 422)

    def test_embedded_markup_in_the_bitstream_is_refused(self):
        self.assertEqual(rejected(riff(webp_chunk(b'VP8L', b'\x2f' + struct.pack('<I', 31 | (31 << 14)) + b'<svg onload=alert(1)>'))),
                         (422, 'embedded_markup'))

    def test_every_truncation_and_single_byte_corruption_is_contained(self):
        good = riff(vp8x(40, 30), webp_chunk(b'ALPH', bytes(9)), vp8(40, 30), webp_chunk(b'EXIF', b'exif'))
        self.assertEqual(assets.sanitize(good).width, 40)
        for cut in range(len(good)):
            with self.subTest(cut=cut):
                self.assertIn(rejected(good[:cut])[0], (415, 422))
        for position in range(len(good)):
            for value in (0x00, 0xFF, good[position] ^ 0x01):
                try:
                    stored = assets.sanitize(good[:position] + bytes([value]) + good[position + 1:])
                except AssetRejected as error:
                    self.assertIn(error.status, (413, 415, 422))
                else:
                    self.assertLessEqual(set(webp_names(stored.data)), {b'VP8X', b'ALPH', b'VP8 ', b'VP8L'})

    def test_png_renamed_webp_and_the_reverse_are_refused(self):
        self.assertEqual(rejected(png(), 'image/webp'), (415, 'type_mismatch'))
        self.assertEqual(rejected(riff(vp8l(32, 32)), 'image/png'), (415, 'type_mismatch'))


class ApiShapeTests(unittest.TestCase):
    def test_rejections_carry_a_finite_status_and_reason_and_no_input_echo(self):
        error = AssetRejected(422, 'malformed')
        self.assertEqual((error.status, error.reason, str(error)), (422, 'malformed', 'malformed'))
        self.assertEqual(assets.REJECTION_STATUSES, frozenset({413, 415, 422}))

    def test_limits_are_the_specified_ones(self):
        self.assertEqual((assets.MAX_BYTES, assets.MIN_SIDE, assets.MAX_SIDE), (256 * 1024, 16, 1024))
        self.assertEqual(assets.ALLOWED_TYPES, ('image/png', 'image/webp'))


if __name__ == '__main__':
    unittest.main()
