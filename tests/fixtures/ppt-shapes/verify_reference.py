"""Check manifest RGB samples in PowerPoint's indexed PNG exports (stdlib only)."""
import json
from pathlib import Path
import struct
import zlib


def read_png(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, compressed, palette = 8, b"", []
    while offset < len(data):
        size, kind = struct.unpack_from(">I4s", data, offset)
        chunk = data[offset + 8:offset + 8 + size]
        offset += size + 12
        if kind == b"IHDR":
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            assert color == 3 and depth in (1, 2, 4, 8)
            assert compression == filtering == interlace == 0
        elif kind == b"PLTE":
            palette = [list(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif kind == b"IDAT":
            compressed += chunk
        elif kind == b"IEND":
            break
    raw = zlib.decompress(compressed)
    stride = (width * depth + 7) // 8
    assert len(raw) == height * (stride + 1)
    previous, rows = bytearray(stride), []
    for y in range(height):
        method = raw[y * (stride + 1)]
        assert 0 <= method <= 4
        row = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            left = row[x - 1] if x else 0
            upper_left = previous[x - 1] if x else 0
            up = previous[x]
            if method == 1:
                predictor = left
            elif method == 2:
                predictor = up
            elif method == 3:
                predictor = (left + up) // 2
            elif method == 4:
                base = left + up - upper_left
                a, b, c = abs(base - left), abs(base - up), abs(base - upper_left)
                predictor = left if a <= b and a <= c else up if b <= c else upper_left
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        rows.append(row)
        previous = row
    return width, height, depth, palette, rows


def main():
    directory = Path(__file__).resolve().parent
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    checks = 0
    for fixture in manifest["fixtures"]:
        width, height, depth, palette, rows = read_png(directory / fixture["reference_png"])
        assert (width, height) == (fixture["width_pt"], fixture["height_pt"])
        for sample in fixture["samples"]:
            x, y = map(round, sample["xy_pt"])
            byte = rows[y][x * depth // 8]
            index = byte >> (8 - depth - x * depth % 8) & ((1 << depth) - 1)
            actual = palette[index]
            assert actual == sample["rgb"], (fixture["file"], sample, actual)
            checks += 1
            print(f"{fixture['file']} {sample['name']}: pixel=({x},{y}) "
                  f"expected={sample['rgb']} actual={actual} PASS")
    print(f"PowerPoint reference PNG samples: {checks} passed across {len(manifest['fixtures'])} fixtures")


if __name__ == "__main__":
    main()
