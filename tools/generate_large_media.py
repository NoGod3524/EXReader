#!/usr/bin/env python3
"""Deterministic 1 GiB media generator for WP12a streaming evidence.

Creates a stored ZIP (CBZ) with a large ignored member plus two tiny PNG pages,
and a 1 GiB PCM WAVE file. Outputs live outside the repository; only this
generator and the resulting hashes are committed.
"""
import argparse
import hashlib
import json
import os
import struct
import time
import zipfile
import zlib


def png_rgba(width, height, pixels):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(pixels[y * width * 4:(y + 1) * width * 4]) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def make_cbz(path, payload_size):
    page = png_rgba(2, 2, [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 0, 255])
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        info = zipfile.ZipInfo("pages/1.png", date_time=(2026, 1, 1, 0, 0, 0))
        archive.writestr(info, page)
        info = zipfile.ZipInfo("pages/2.png", date_time=(2026, 1, 1, 0, 0, 0))
        archive.writestr(info, page)
        info = zipfile.ZipInfo("notes/padding.bin", date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        with archive.open(info, "w") as handle:
            block = b"\0" * (1024 * 1024)
            remaining = payload_size
            while remaining:
                piece = block if remaining >= len(block) else block[:remaining]
                handle.write(piece)
                remaining -= len(piece)
    return page


def make_wav(path, payload_size):
    payload_size -= payload_size % 4
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + payload_size, b"WAVE",
                         b"fmt ", 16, 1, 1, 8000, 16000, 2, 16, b"data", payload_size)
    with open(path, "wb") as handle:
        handle.write(header)
        block = b"\0" * (1024 * 1024)
        remaining = payload_size
        while remaining:
            piece = block if remaining >= len(block) else block[:remaining]
            handle.write(piece)
            remaining -= len(piece)
    return payload_size


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=r"C:\Users\Oscar\exr-wp12a-evidence\large")
    parser.add_argument("--size", type=int, default=1024 * 1024 * 1024)
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    result = {"generator": "tools/generate_large_media.py", "payload_bytes": args.size, "media": {}}
    for name, builder in (("large.cbz", make_cbz), ("large.wav", make_wav)):
        path = os.path.join(args.output, name)
        started = time.time()
        built = builder(path, args.size)
        result["media"][name] = {"path": path.replace("\\", "/"), "bytes": os.path.getsize(path),
                                 "sha256": sha256(path), "build_seconds": round(time.time() - started, 3),
                                 "payload_bytes": built if isinstance(built, int) else args.size}
        print(name, result["media"][name]["bytes"], result["media"][name]["sha256"], flush=True)
    with open(os.path.join(args.output, "media.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
