# SPDX-License-Identifier: MIT
"""Dependency-free PNG writing and pixel comparison for audit screenshots.

Bytes are always top-down 8-bit RGB, row-major, three bytes per pixel, so the
same buffers that come out of w32.capture_rgb can be cropped, compared and
written without an imaging library.
"""
from __future__ import annotations

import struct
import zlib


def encode_png(width, height, rgb):
    if width <= 0 or height <= 0:
        raise ValueError("empty image")
    stride = width * 3
    if len(rgb) != stride * height:
        raise ValueError("buffer size does not match the image size")
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        raw += rgb[row * stride:(row + 1) * stride]

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def write_png(path, width, height, rgb):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(width, height, rgb))
    return path


def crop(rgb, width, height, rect):
    """Crop a pixel rectangle, clipped to the image; returns (w, h, bytes)."""
    left = max(0, int(rect[0]))
    top = max(0, int(rect[1]))
    right = min(int(width), int(rect[2]))
    bottom = min(int(height), int(rect[3]))
    if right <= left or bottom <= top:
        return (0, 0, b"")
    stride = width * 3
    rows = [rgb[row * stride + left * 3:row * stride + right * 3] for row in range(top, bottom)]
    return (right - left, bottom - top, b"".join(rows))


def changed_bytes(first, second):
    if first == second:
        return 0
    limit = min(len(first), len(second))
    if len(first) != len(second):
        return limit
    return sum(1 for index in range(limit) if first[index] != second[index])


def downsample(rgb, width, height, factor=1):
    """Return a smaller RGB buffer; factor 1 is a no-op."""
    if factor <= 1:
        return (width, height, rgb)
    out_width = max(1, width // factor)
    out_height = max(1, height // factor)
    out = bytearray(out_width * out_height * 3)
    stride = width * 3
    for row in range(out_height):
        source = (row * factor) * stride
        target = row * out_width * 3
        for column in range(out_width):
            base = source + (column * factor) * 3
            out[target + column * 3] = rgb[base]
            out[target + column * 3 + 1] = rgb[base + 1]
            out[target + column * 3 + 2] = rgb[base + 2]
    return (out_width, out_height, bytes(out))
