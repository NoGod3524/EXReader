#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only native Apple bridge consumer against an installed macOS SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('requires the macOS GitHub Actions runner')
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('only GitHub Actions execution is authorized')
    sdk, resources, out = (p.resolve() for p in (args.sdk, args.resources, args.out))
    if out.exists():
        parser.error('choose a fresh output directory to preserve earlier results')
    out.mkdir(parents=True)
    binary = out / 'sdk-review'
    sources = [ROOT / 'examples/apple/HostSDK.swift',
               ROOT / 'tests/apple_host/sdk_review/SDKReview.swift']
    command = ['xcrun', '--sdk', 'macosx', 'swiftc', '-swift-version', '5', '-O',
               '-parse-as-library', '-D', 'EXR_APPLE_HOST_REVIEW',
               '-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-lsqlite3',
               '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib', *sources, '-o', binary]
    with (out / 'build.log').open('w') as log:
        subprocess.run([str(value) for value in command], check=True, stdout=log, stderr=subprocess.STDOUT)
    (out / 'consumer').mkdir()
    shutil.copyfile(ROOT / 'tests/fixtures/pdf-public-text.pdf', out / 'consumer/TextFailure.pdf')
    result = subprocess.run([str(binary), str(resources), str(out / 'consumer')],
                            capture_output=True, text=True, timeout=180)
    (out / 'consumer.log').write_text(result.stdout + result.stderr)
    report_path = out / 'consumer/sdk-review.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    expected = {
        'position-preserves-latest-metadata', 'import-pre-cancel-preserves-library',
        'import-oversize-rejected-before-read', 'import-cancel-during-bounded-read',
        'import-late-cancel-removes-new-row', 'import-late-cancel-preserves-reused-row',
        'import-rollback-failure-reports-retained-row', 'pager-rebinds-after-creator-cancel',
        'pager-current-token-controls-cache-hit', 'pager-render-polls-current-token',
        'pager-seek-propagates-real-limit', 'pager-seek-verifies-target-range-and-eof',
        'snapshot-pager-anchor-uses-document-api', 'fixed-render-polls-current-token',
        'fixed-text-polls-current-token', 'fixed-reuses-after-cancel',
        'fixed-comment-update-keeps-reflow-note-separate', 'fixed-notes-propagates-cancellation',
        'fixed-notes-text-failure-is-propagated',
        'publication-cancel-ordering', 'embedded-nul-note-is-rejected',
    }
    cases = report.get('cases', [])
    ids = [case.get('id') for case in cases]
    passed = (result.returncode == 0 and report.get('schema') == 1 and report.get('passed') is True
              and report.get('checks') == len(expected) and len(ids) == len(set(ids))
              and set(ids) == expected and all(case.get('passed') is True for case in cases))
    source_files = [*sources, ROOT / 'tests/apple_host/run_sdk_review.py',
                    ROOT / 'tests/fixtures/pdf-public-text.pdf']
    sdk_files = [sdk / 'include/exreader.h', sdk / 'include/module.modulemap',
                 *sorted((sdk / 'include/exr').glob('*.h')),
                 *sorted((sdk / 'lib').glob('libexreader*.dylib'))]
    evidence_files = [binary, out / 'build.log', out / 'consumer.log', out / 'consumer/TextFailure.pdf']
    if report_path.exists():
        evidence_files.append(report_path)
    identity = {
        'schema': 1, 'passed': passed, 'checks': len(expected), 'exit_code': result.returncode,
        'source_sha': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'compiler': subprocess.check_output(['xcrun', 'swiftc', '--version'], text=True).strip(),
        'sdk_version': report.get('sdk'), 'abi': report.get('abi'),
        'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'job': os.environ['GITHUB_JOB'],
        'program': {'path': 'sdk-review', 'sha256': digest(binary)},
        'source_files_sha256': {str(path.relative_to(ROOT)): digest(path) for path in source_files},
        'sdk_files_sha256': {str(path.relative_to(sdk)): digest(path) for path in sdk_files},
        'fixtures': {name: digest(resources / name) for name in ['Reader.otf', 'Sample.epub', 'Sample.pdf']},
        'evidence_files_sha256': {str(path.relative_to(out)): digest(path) for path in evidence_files},
        'report_sha256': digest(report_path) if report_path.exists() else None,
        'local_execution': False,
    }
    (out / 'sdk-review-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'checks': len(expected), 'exit_code': result.returncode}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
