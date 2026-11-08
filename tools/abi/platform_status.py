#!/usr/bin/env python3
"""Print observed platform artifacts; absent files never inherit a passing ABI."""
import argparse
import hashlib
import json
import os
import struct
import sys
import zipfile
from pathlib import Path

from check_exports import ROOT, DEFAULT_CONTRACT, inspect

MANIFEST = ROOT / 'evidence/platforms-20261108/artifacts.json'
DEFAULT_ROOT = ROOT.parent / 'tmp/platform-delivery-20261108/delivery'


def collect(root, manifest, expected):
    rows = []
    for entry in manifest['artifacts']:
        row = dict(entry, exists=False, observed_sha256=None, observed_size_bytes=None,
                   observed_exports=None, observed_abi=None)
        if entry['kind'] == 'unsupported':
            row['observed_abi'] = 'unsupported'
        if entry.get('path'):
            path = root / entry['path']
            row['exists'] = path.is_file()
            if row['exists']:
                try:
                    row['observed_size_bytes'] = path.stat().st_size
                    with path.open('rb') as stream:
                        row['observed_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if entry['kind'] == 'container':
                        with zipfile.ZipFile(path) as package:
                            bad = package.testzip()
                            if bad:
                                raise ValueError('corrupt ZIP member: ' + bad)
                            if entry['path'].endswith('.aar'):
                                from check_exports import inspect_bytes
                                core = package.read('jni/' + entry['architecture'] + '/libexreader.so')
                                slices = inspect_bytes(core)
                                row['observed_exports'] = 'container/core:' + str(len(slices[0]['symbols']))
                                row['observed_abi'] = 'complete' if expected <= slices[0]['symbols'] else 'MISSING'
                    else:
                        report = inspect(path, expected)
                        row['observed_exports'] = ','.join(str(p['symbol_count']) for p in report['slices'])
                        if entry['kind'] in ('program', 'jni'):
                            row['observed_abi'] = 'n/a (JNI)' if entry['kind'] == 'jni' else 'n/a'
                        elif any(p['missing'] for p in report['slices']):
                            row['observed_abi'] = 'MISSING'
                        elif any(p['extra'] for p in report['slices']):
                            row['observed_abi'] = 'complete+extra'
                        else:
                            row['observed_abi'] = 'strict PASS'
                    if entry.get('sha256') and row['observed_sha256'] != entry['sha256']:
                        row['error'] = 'SHA differs from recorded evidence'
                except (OSError, ValueError, KeyError, IndexError, struct.error, UnicodeError, zipfile.BadZipFile) as error:
                    row['error'] = str(error)
        rows.append(row)
    return rows


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(os.environ.get('EXREADER_PLATFORM_ARTIFACTS', DEFAULT_ROOT)))
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    expected = set(json.loads(DEFAULT_CONTRACT.read_text())['symbols'])
    rows = collect(args.root, json.loads(args.manifest.read_text(encoding='utf-8')), expected)
    if args.json:
        print(json.dumps({'artifact_root': str(args.root), 'artifacts': rows}, ensure_ascii=False, indent=2))
    else:
        print('Artifact root:', args.root)
        print('| Platform/arch | Artifact | Exists | Bytes | SHA-256 (observed) | Exports | ABI | Delivery status |')
        print('|---|---|---|---:|---|---:|---|---|')
        for r in rows:
            print('| ' + ' | '.join(str(v) for v in (
                r['platform']+'/'+r['architecture'], r['path'] or r['target'],
                'yes' if r['exists'] else 'no', r['observed_size_bytes'] if r['exists'] else '—',
                r['observed_sha256'] or '—', r['observed_exports'] or '—',
                r.get('error') or r['observed_abi'] or 'pending', r['status'])) + ' |')
    return int(any(r.get('error') or r['observed_abi'] == 'MISSING' for r in rows))


if __name__ == '__main__':
    sys.exit(main())
