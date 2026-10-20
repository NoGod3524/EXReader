#!/usr/bin/env python3
"""Deterministic image fixtures for the WP12a CBZ format matrix.

Requires Pillow (WebP and AVIF plugins included in the pinned development
environment). Outputs are original test patterns, MIT, and are written under
tests/fixtures/images. Re-running this script with the same Pillow build
reproduces byte-identical files; MANIFEST.json records SHA-256 values.
"""
import hashlib
import json
import os
import struct
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "fixtures", "images")


def rgba(width, height, fn):
    image = Image.new("RGBA", (width, height))
    image.putdata([fn(x, y) for y in range(height) for x in range(width)])
    return image


def quadrants(x, y):
    return ((255, 0, 0, 255) if x < 2 else (0, 255, 0, 255)) if y < 2 else ((0, 0, 255, 255) if x < 2 else (255, 255, 0, 255))


def cases():
    return {
        "solid": (4, 4, lambda x, y: (220, 30, 40, 255)),
        "alpha": (8, 6, lambda x, y: (20, 120, 220, x * 255 // 7)),
        "checker": (16, 16, lambda x, y: (0, 0, 0, 255) if (x + y) & 1 else (255, 255, 255, 255)),
        "odd": (17, 9, quadrants),
        "one": (1, 1, lambda x, y: (255, 0, 255, 255)),
        "wide": (255, 1, lambda x, y: (x, 255 - x, (x * 3) & 255, 255)),
        "tall": (1, 255, lambda x, y: ((y * 3) & 255, y, 255 - y, 255)),
        "gray": (32, 8, lambda x, y: (x * 8, x * 8, x * 8, 255)),
        "palette": (12, 12, lambda x, y: [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)][(x // 3 + y // 3) & 3]),
        "transparent": (5, 5, lambda x, y: (x * 40, y * 40, 128, 0)),
        "gradient": (100, 100, lambda x, y: (x * 255 // 99, y * 255 // 99, (x + y) & 255, 255)),
    }


def frame_images():
    frames = []
    for i in range(4):
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for y in range(8):
            for x in range(8):
                if i * 2 <= x < i * 2 + 2:
                    image.putpixel((x, y), (255, 40 * i, 0, 255))
        frames.append(image)
    return frames


def save_all(fmt, name, image, path, **kwargs):
    if fmt == "gif":
        image.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).save(path, save_all=True, append_images=[f.convert("P", palette=Image.Palette.ADAPTIVE, colors=16) for f in kwargs.pop("frames")], duration=80, loop=0, disposal=2, optimize=False, **kwargs)
    elif fmt == "webp":
        image.save(path, save_all=True, append_images=kwargs.pop("frames"), lossless=True, quality=100, method=0, **kwargs)
    elif fmt == "tiff":
        image.save(path, save_all=True, append_images=kwargs.pop("frames"), compression=kwargs.pop("compression", "tiff_lzw"), **kwargs)
    elif fmt == "avif":
        image.save(path, save_all=True, append_images=kwargs.pop("frames"), quality=90, speed=8, **kwargs)


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {"generator": "tools/generate_image_format_fixtures.py", "license": "MIT", "cases": {}}
    formats = {"png": ".png", "bmp": ".bmp", "gif": ".gif", "webp": ".webp", "tiff": ".tif", "avif": ".avif"}
    for fmt, ext in formats.items():
        directory = os.path.join(OUT, fmt)
        os.makedirs(directory, exist_ok=True)
        entries = {}
        for name, (w, h, fn) in cases().items():
            if name == "transparent" and fmt in ("bmp",):
                continue
            image = rgba(w, h, fn)
            path = os.path.join(directory, name + ext)
            if fmt in ("bmp",):
                image.convert("RGB").save(path)
            elif fmt == "gif":
                image.convert("P", palette=Image.Palette.ADAPTIVE, colors=32).save(path, optimize=False)
            elif fmt == "tiff":
                compression = "tiff_deflate" if name in ("checker", "gradient") else "tiff_lzw"
                image.save(path, compression=compression)
            elif fmt == "webp":
                image.save(path, lossless=True, quality=100, method=0)
            elif fmt == "avif":
                image.save(path, quality=90, speed=8)
            else:
                image.save(path)
            entries[name] = {"file": os.path.relpath(path, ROOT).replace("\\", "/"), "width": w, "height": h, "pages": 1}
        if fmt in ("gif", "webp", "tiff", "avif"):
            frames = frame_images()
            path = os.path.join(directory, "animation" + ext)
            save_all(fmt, "animation", frames[0], path, frames=frames[1:])
            entries["animation"] = {"file": os.path.relpath(path, ROOT).replace("\\", "/"), "width": 8, "height": 8, "pages": 4}
        if fmt == "gif":
            # Four 2600x2600 frames expand past the 96 MiB GIF budget while the
            # encoded file stays small; the decoder must reject before allocating.
            big = []
            for index in range(4):
                image = Image.new("RGB", (2600, 2600), (index * 40, 0, 0))
                big.append(image)
            path = os.path.join(directory, "expansion.gif")
            big[0].save(path, save_all=True, append_images=big[1:], duration=80, loop=0, optimize=False)
            entries["expansion"] = {"file": os.path.relpath(path, ROOT).replace("\\", "/"), "width": 2600, "height": 2600, "pages": 4}
        # Error inputs are intentionally damaged variants of a valid file.
        solid = os.path.join(directory, "solid" + ext)
        data = open(solid, "rb").read()
        for name, blob in (("truncated", data[: max(8, len(data) * 3 // 5)]), ("badmagic", b"not an image")):
            path = os.path.join(directory, name + ext)
            open(path, "wb").write(blob)
            entries[name] = {"file": os.path.relpath(path, ROOT).replace("\\", "/"), "error": True}
        manifest["cases"][fmt] = entries
    # A deliberately oversized PNG header is small on disk but rejected by the
    # 8192/16-million-pixel limit before allocation.
    huge = Image.new("RGBA", (9000, 2), (1, 2, 3, 255))
    path = os.path.join(OUT, "png", "huge.png")
    huge.save(path)
    manifest["cases"]["png"]["huge"] = {"file": os.path.relpath(path, ROOT).replace("\\", "/"), "error": True, "limit": True}
    for fmt in formats:
        for name, entry in manifest["cases"][fmt].items():
            full = os.path.join(ROOT, entry["file"])
            entry["bytes"] = os.path.getsize(full)
            entry["sha256"] = hashlib.sha256(open(full, "rb").read()).hexdigest()
    with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
