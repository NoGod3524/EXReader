
#!/usr/bin/env python3
"""Fetch a public PDF corpus for compatibility measurement.

Sources are recorded with their URL and licence note in manifest.json; the
corpus itself is downloaded, not committed (tests/corpus is git-ignored).
"""
# SPDX-License-Identifier: GPL-3.0-only
import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'tests' / 'corpus'

ARCHIVES = [
    ('qpdf', 'https://codeload.github.com/qpdf/qpdf/tar.gz/refs/heads/main',
     'qpdf test suite, Apache-2.0 (github.com/qpdf/qpdf)'),
]

FILES = [
    ('irs-w9.pdf', 'https://www.irs.gov/pub/irs-pdf/fw9.pdf', 'US IRS form W-9, public domain'),
    ('irs-1040.pdf', 'https://www.irs.gov/pub/irs-pdf/f1040.pdf', 'US IRS form 1040, public domain'),
    ('nist-ai-rmf.pdf', 'https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf', 'NIST AI RMF 1.0, public domain'),
]


def fetch(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def save(target, data, source, licence, manifest):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    manifest.append({'path': str(target.relative_to(ROOT)), 'bytes': len(data),
                     'sha256': hashlib.sha256(data).hexdigest(),
                     'source': source, 'licence': licence})


GITHUB_LIST = 'https://api.github.com/repos/mozilla/pdf.js/contents/test/pdfs'


def fetch_pdfjs(limit, max_bytes, manifest):
    """Valid-ish real-world PDFs from the pdf.js test suite (Apache-2.0 repo)."""
    request = urllib.request.Request(GITHUB_LIST, headers={'User-Agent': 'exreader-corpus'})
    with urllib.request.urlopen(request, timeout=60) as response:
        entries = json.loads(response.read())
    picked = [e for e in entries
              if e.get('type') == 'file' and e['name'].lower().endswith('.pdf')
              and 20000 < e.get('size', 0) <= max_bytes]
    picked.sort(key=lambda e: e['size'])
    if limit and len(picked) > limit:
        stride = len(picked) / limit
        picked = [picked[int(i * stride)] for i in range(limit)]  # spread across sizes
    for entry in picked:
        try:
            blob = fetch(entry['download_url'])
        except Exception as exc:                   # noqa: BLE001
            print('  skipped', entry['name'], str(exc)[:80], flush=True)
            continue
        save(ROOT / 'pdfjs' / entry['name'], blob, entry['download_url'],
             'mozilla/pdf.js test suite (Apache-2.0 repo)', manifest)
    print('  pdf.js files', len(picked), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0, help='cap the archive members per source')
    parser.add_argument('--skip-archives', action='store_true')
    parser.add_argument('--pdfjs', type=int, default=0, help='also fetch N pdf.js samples')
    parser.add_argument('--pdfjs-max-bytes', type=int, default=400000)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = []
    if not args.skip_archives:
        for name, url, licence in ARCHIVES:
            print('fetching', name, flush=True)
            data = fetch(url, timeout=300)
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
                members = [m for m in archive.getmembers()
                           if m.isfile() and m.name.endswith('.pdf') and '/qtest/qpdf/' in m.name]
                members.sort(key=lambda m: m.name)
                if args.limit:
                    members = members[:args.limit]
                for member in members:
                    blob = archive.extractfile(member).read()
                    target = ROOT / name / Path(member.name).name
                    save(target, blob, url + '::' + member.name, licence, manifest)
                print('  extracted', len(members), 'pdf files', flush=True)
    if args.pdfjs:
        print('fetching pdf.js samples', flush=True)
        fetch_pdfjs(args.pdfjs, args.pdfjs_max_bytes, manifest)
    for filename, url, licence in FILES:
        try:
            blob = fetch(url)
        except Exception as exc:                   # noqa: BLE001 - record and continue
            print('  skipped', filename, str(exc)[:100], flush=True)
            continue
        save(ROOT / 'public' / filename, blob, url, licence, manifest)
        print('  saved', filename, len(blob), flush=True)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('corpus files:', len(manifest), 'total bytes:', sum(m['bytes'] for m in manifest))


if __name__ == '__main__':
    main()
