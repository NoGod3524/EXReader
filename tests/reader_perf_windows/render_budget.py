#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Repeat the production host render path on a fixed SHA-256 book manifest.

Each book starts a fresh process; two warm cohorts share that process. Ratios
measure repeatability on this machine, not regression against another revision.
Display frame pacing and first interactive remain explicitly unmeasured.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def identity(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    result = {'scope': 'host render path, 8 warmups + 64 alternating page 0/1 samples per cohort',
              'platform': platform.platform(), 'processor': platform.processor(),
              'binary': identity(args.binary), 'font': identity(args.font),
              'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'display_present_frame': 'missing', 'first_interactive': 'missing',
              'thresholds': {'same_process_repeat_p95_ratio': 2.5, 'peak_ratio': 1.25}, 'books': []}
    failed = False
    for book in manifest['books']:
        path = args.corpus / book['file']
        actual = identity(path)
        if actual['sha256'] != book['sha256']:
            raise SystemExit('fixed corpus hash mismatch: ' + book['file'])
        env = dict(os.environ, EXR_AUDIT_BOOK=str(path.resolve()))
        run = subprocess.run([str(args.binary.resolve()), 'render-budget', str(args.font.resolve())],
                             env=env, capture_output=True, text=True, timeout=180)
        result['books'].append(dict(actual, exit=run.returncode, stdout=run.stdout, stderr=run.stderr))
        failed |= run.returncode != 0
        print(book['file'], 'exit=', run.returncode, '\n' + run.stdout + run.stderr)
    result['passed'] = bool(result['books']) and not failed
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
