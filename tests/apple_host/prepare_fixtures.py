#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the deterministic Apple host fixtures used by the WP13 UI acceptance."""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from run_benchmarks import make_epub  # noqa: E402
from host_font import fetch as host_font  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_unicode_epub(path):
    # One page with scalar pairs, combining marks, ZWJ and regional indicators.
    text = 'Unicode selection: A😀é中 👩🏽‍💻 🇺🇳. Exact source bytes must survive selection, copy and annotations.'
    make_epub(path, 1, 512, single_paragraph=True)
    with zipfile.ZipFile(path) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    with zipfile.ZipFile(path, 'w') as archive:
        for item, content in entries:
            if item.filename == 'OPS/c0.xhtml':
                content = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Unicode</title></head>'
                           '<body><p>' + text + '</p></body></html>').encode('utf-8')
            archive.writestr(item, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--font-cache', type=Path, default=ROOT/'build/host-font-cache')
    args = parser.parse_args()
    out = args.resources.absolute()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    make_epub(out/'Sample.epub', 3, 16384, single_paragraph=True)
    shutil.copyfile(ROOT/'tests/fixtures/pdf-public.pdf', out/'Sample.pdf')
    (out/'Broken.epub').write_bytes(b'not a valid epub payload\n' * 8)
    make_epub(out/'Large.epub', 48, 65536)
    make_unicode_epub(out/'Unicode.epub')
    font = host_font(args.font_cache)
    shutil.copyfile(font/'Reader.otf', out/'Reader.otf')
    shutil.copyfile(font/'OFL.txt', out/'OFL.txt')
    manifest = {path.name: digest(path) for path in sorted(out.iterdir()) if path.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
