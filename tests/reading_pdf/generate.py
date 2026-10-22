#!/usr/bin/env python3
"""Write tiny distinct-page synthetic PDFs/CBZs before any engine measurement."""
# SPDX-License-Identifier: MIT
import argparse
import json
import struct
import sys
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from measure_reading_pdf import GENERATED_CASES, sha256


def pdf(colors):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               ("<< /Type /Pages /Count %d /Kids [%s] >>" % (len(colors),
                " ".join(f"{3 + page * 2} 0 R" for page in range(len(colors))))).encode()]
    for page, color in enumerate(colors):
        rgb = " ".join(str(int(color[index:index + 2], 16) // 255) for index in (0, 2, 4))
        content = f"{rgb} rg 0 0 32 32 re f\n".encode()
        objects.extend([f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 32 32] /Resources << >> /Contents {4 + page * 2} 0 R >>".encode(),
                        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"endstream"])
    data, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def png(color):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    pixels = b"".join(b"\0" + bytes.fromhex(color) * 32 for _ in range(32))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels, 9)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "kind": "synthetic", "real_document_credit": 0,
                "engine_results_used": False, "generator_sha256": sha256(__file__), "cases": {}}
    for name, definition in GENERATED_CASES.items():
        target = args.output / definition["path"]
        if target.suffix == ".pdf":
            target.write_bytes(pdf(definition["expected_rgba"]))
        else:
            with zipfile.ZipFile(target, "w") as archive:
                for page, color in enumerate(definition["expected_rgba"], 1):
                    entry = zipfile.ZipInfo(f"pages/{page:02d}.png", date_time=(2026, 10, 22, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.external_attr = 0o100644 << 16
                    archive.writestr(entry, png(color))
        manifest["cases"][name] = dict(definition, bytes=target.stat().st_size, sha256=sha256(target))
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"generated": list(manifest["cases"]), "engine_results_used": False}))


if __name__ == "__main__":
    main()
