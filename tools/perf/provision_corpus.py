"""Stage an owner-provisioned ZIP of SHA256-named books; publish no book bytes.

The ZIP must contain exactly <sha256>.<epub|pdf|mobi> for the existing corpus.
PERF_CORPUS_URL is supplied by the repository owner after arranging CI access.
"""
import argparse
import io
import os
from pathlib import Path
import urllib.request
import zipfile
from sample import ROOT, read, sha, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--archive', type=Path, help='existing ZIP; otherwise use PERF_CORPUS_URL')
    args = p.parse_args()
    maximum = 256 * 1024 * 1024
    if args.archive:
        content = args.archive.read_bytes()
    else:
        url = os.environ.get('PERF_CORPUS_URL', '')
        if not url.startswith('https://'):
            p.error('owner-provisioned HTTPS PERF_CORPUS_URL is required; no public corpus is configured')
        with urllib.request.urlopen(url, timeout=120) as response:
            content = response.read(maximum + 1)
    if len(content) > maximum:
        p.error('archive exceeds 256 MiB')
    books = read(ROOT / 'tools/regress/corpus.json')['books']
    names = {b['sha256'] + Path(b['filename']).suffix.lower(): b for b in books}
    args.output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if len(archive.infolist()) != 19 or set(archive.namelist()) != set(names):
            p.error('ZIP must contain exactly the 19 SHA-named inputs at its root')
        if sum(i.file_size for i in archive.infolist()) > maximum:
            p.error('expanded archive exceeds 256 MiB')
        for name, book in names.items():
            target = args.output / name
            target.write_bytes(archive.read(name))
            if sha(target) != book['sha256']:
                p.error('input SHA256 mismatch: ' + book['id'])
            book['path'] = name
    write(args.output / 'manifest.json', {'books': books})


if __name__ == '__main__':
    main()
