#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create the S11 fixture tree inside the Actions temporary workspace.

Only the generated build tree is written. The frozen repository fixtures are
read-only inputs. Large and corrupt inputs are generated here so that no binary
fixture is ever committed; every produced file is recorded with its exact
SHA-256 and length.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

MIB = 1024 * 1024
LARGE_BYTES = 3 * MIB

COPIES = [
    ("text/small.txt", "sample.txt", "TXT"),
    ("epub/sample.epub", "sample.epub", "EPUB"),
    ("epub/changed.epub", "complex-text.epub", "EPUB"),
    ("cbz/comic.cbz", "comic.cbz", "CBZ"),
    ("pdf/public-text.pdf", "pdf-public-text.pdf", "PDF"),
]


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def record(files, root, name, fmt):
    path = os.path.join(root, *name.split("/"))
    files[name] = {
        "path": path,
        "format": fmt,
        "bytes": os.path.getsize(path),
        "sha256": digest(path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true", "S11 fixtures are generated in Actions only"
    fixtures = os.path.abspath(args.fixtures)
    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    files = {}

    for name, source, fmt in COPIES:
        target = os.path.join(out, *name.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(fixtures, source), target)
        record(files, out, name, fmt)

    # A reflow original far above a 256 KiB staging volume, still inside the
    # published 32 MiB bounded-memory ceiling.
    large = os.path.join(out, "text", "large.txt")
    with open(large, "wb") as handle:
        line = b"S11 bounded reflow line with deterministic payload.\n"
        written = 0
        index = 0
        while written < LARGE_BYTES:
            row = (b"%06d " % index) + line
            handle.write(row)
            written += len(row)
            index += 1
    record(files, out, "text/large.txt", "TXT")

    # A corrupt EPUB: readable file, rejected bytes, never modified by an import.
    broken = os.path.join(out, "epub", "broken.epub")
    with open(broken, "wb") as handle:
        handle.write(b"PK\x03\x04 this is not a valid EPUB package\n" * 8)
    record(files, out, "epub/broken.epub", "EPUB")

    data = {
        "root": out,
        "files": files,
        "large_bytes": LARGE_BYTES,
        "oversize_limit": 512 * 1024,
    }
    with open(os.path.join(out, "fixtures.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
    print("s11 fixtures:", out)
    print("files:", len(files), "large_bytes:", LARGE_BYTES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
