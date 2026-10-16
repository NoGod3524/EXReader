"""Independently validate native gray/RGBA PNG structure, CRCs, scanlines and colors."""
import struct
import sys
import zlib
from pathlib import Path


def check(path):
    payload = Path(path).read_bytes()
    if Path(path).suffix == ".bmp":
        assert payload[:2] == b"BM"
        size, offset = struct.unpack_from("<I", payload, 2)[0], struct.unpack_from("<I", payload, 10)[0]
        width, height, planes, depth = struct.unpack_from("<iiHH", payload, 18)
        stride = (width*3+3) & ~3
        assert size == len(payload) == offset+stride*height and planes == 1 and depth == 24
        colors = {payload[offset+y*stride+x*3:offset+y*stride+x*3+3]
                  for y in range(height) for x in range(width)}
        assert bytes((30, 40, 220)) in colors and bytes((60, 180, 30)) in colors
        print(f"BMP verified: {width} x {height}, BGR color pixels")
        return
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    compressed = bytearray()
    width = height = channels = 0
    while pos < len(payload):
        size = struct.unpack_from(">I", payload, pos)[0]
        kind = payload[pos+4:pos+8]
        data = payload[pos+8:pos+8+size]
        crc = struct.unpack_from(">I", payload, pos+8+size)[0]
        assert zlib.crc32(kind+data) == crc, kind
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            assert depth == 8 and color in (0, 6)
            assert compression == filtering == interlace == 0
            channels = 1 if color == 0 else 4
        elif kind == b"IDAT":
            compressed.extend(data)
        pos += 12+size
        if kind == b"IEND":
            break
    assert pos == len(payload) and width and height
    pixels = zlib.decompress(compressed)
    stride = width*channels+1
    assert len(pixels) == stride*height
    assert all(pixels[y*stride] == 0 for y in range(height))
    samples = b"".join(pixels[y*stride+1:(y+1)*stride] for y in range(height))
    if channels == 1:
        assert sum(v < 200 for v in samples) > 1000
    else:
        assert all(a == 255 for a in samples[3::4])
        colors = {samples[i:i+4] for i in range(0, len(samples), 4)}
        assert bytes((220, 40, 30, 255)) in colors
        assert bytes((30, 180, 60, 255)) in colors
        assert bytes((137, 152, 237, 255)) in colors  # Half-transparent blue over white.
    print(f"PNG verified: {width} x {height}, {channels} channels, CRCs and native pixels")


for filename in sys.argv[1:]:
    check(filename)
