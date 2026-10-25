#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the S10 transfer fixtures inside GitHub Actions.

Fixtures are never committed.  The workflow builds them, records the exact
SHA-256 of every delivered file, and every later stage and the strict summary
compare against that manifest instead of a stored constant.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_benchmarks import make_epub  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    make_epub(out / 'S10-Transfer.epub', 2, 4096, single_paragraph=True)
    text = ('EXReader S10 computer transfer fixture. Cafe \u00e9 \u9884\u89c8 \ud55c\uae00.\n') * 64
    (out / 'S10-Transfer.txt').write_text(text, encoding='utf-8')
    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public.pdf', out / 'S10-Transfer.pdf')
    manifest = {}
    for path in sorted(out.iterdir()):
        if path.is_file():
            data = path.read_bytes()
            manifest[path.name] = {'sha256': digest(data), 'bytes': len(data)}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
