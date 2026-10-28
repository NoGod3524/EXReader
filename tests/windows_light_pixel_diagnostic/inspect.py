"""Inspect pixels from the retained Windows common-gate screenshot, Actions only."""
import hashlib
import json
import os
from pathlib import Path
import struct
from zipfile import ZipFile

assert os.environ.get("GITHUB_ACTIONS") == "true"
archive = Path("diagnostic/source.zip")
expected = "e7d1c566f1c1e5379d2a05f52009d76ef506528bdfb083a8c9ff066f0d29c7e2"
assert hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() == expected
with ZipFile(archive) as z:
    matches = [x for x in z.namelist() if x.endswith("wprefs-ui/captures/light.bmp")]
    assert len(matches) == 1, matches
    image = z.read(matches[0])

magic, size, _, _, offset = struct.unpack_from("<2sIHHI", image)
header, width, height, planes, bpp, compression = struct.unpack_from("<IiiHHI", image, 14)
assert magic == b"BM" and size == len(image) and header == 40
assert width > 0 and height > 0 and planes == 1 and bpp == 32 and compression == 0
assert len(image) == offset + width * height * 4

def at(x, y):
    assert 0 <= x < width and 0 <= y < height
    i = offset + ((height - 1 - y) * width + x) * 4
    b, g, r = image[i:i+3]
    return (r, g, b)

def near(pixel, reference, tolerance):
    return all(abs(pixel[i] - reference[i]) <= tolerance for i in range(3))

scale = min((width - 8.0) / 720, (height - 8.0) / 1040)
dx, dy = int((width - 720 * scale) / 2), int((height - 1040 * scale) / 2)
page_w, page_h = int(720 * scale), int(1040 * scale)
corner = at(dx + 6, dy + 6)
surround = at(max(dx - 4, 1), max(dy - 4, 1))
pixels = [at(x, y) for x in range(dx + 40, dx + page_w - 40, 7)
          for y in range(dy + 40, dy + min(page_h, 500) - 10, 5)]
ink = [p for p in pixels if not near(p, corner, 16)]
result = {
    "original_run": 40638398225, "attempt": 1, "original_source": "e330a415b733db18dea5aa6010d13cf3063587fd",
    "artifact_id": 12795210910, "artifact_sha256": expected, "screenshot_sha256": hashlib.sha256(image).hexdigest(),
    "screenshot": matches[0], "client": [width, height], "page_layout": [dx, dy, page_w, page_h],
    "corner": corner, "surround": surround, "ink_samples": len(ink),
    "minimum_ink_rgb_sum": min(map(sum, ink)) if ink else None,
    "conditions": {"corner_white": near(corner, (255, 255, 255), 2),
                   "surround_white": near(surround, (255, 255, 255), 2),
                   "ink_present": bool(ink),
                   "dark_ink": bool(ink) and min(map(sum, ink)) < 260},
    "diagnostic_source": os.environ["GITHUB_SHA"], "diagnostic_run": os.environ["GITHUB_RUN_ID"],
}
Path("diagnostic/result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
