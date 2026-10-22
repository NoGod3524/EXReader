#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run the real cloud evidence gate against positive and altered copies."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_legacy_migration import gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    checks = []

    def accepted(directory):
        with redirect_stdout(io.StringIO()):
            try:
                return gate(argparse.Namespace(evidence=str(directory), require=['linux', 'windows'], out=None)) == 0
            except (KeyError, ValueError, TypeError, OSError):
                return False

    assert accepted(args.evidence)
    checks.append({'name': 'real two-platform cloud evidence accepted', 'passed': True})
    original_upstream = os.environ['MIGRATION_UPSTREAM_RESULT']
    try:
        for result in ('failure', 'cancelled', 'skipped', ''):
            os.environ['MIGRATION_UPSTREAM_RESULT'] = result
            assert not accepted(args.evidence), result
            checks.append({'name': 'upstream ' + (result or 'missing') + ' refused', 'passed': True})
    finally:
        os.environ['MIGRATION_UPSTREAM_RESULT'] = original_upstream
    changes = [
        ('empty-scenario-evidence', 'scenarios', lambda d: d.clear()),
        ('empty-browser-evidence', 'e2e', lambda d: d.clear()),
        ('empty-identity-evidence', 'identity', lambda d: d.clear()),
        ('string-browser-result', 'e2e', lambda d: d.update(passed='true')),
        ('wrong-source', 'identity', lambda d: d['git'].update(sha='0' * 40)),
        ('wrong-run', 'identity', lambda d: d['workflow'].update(run_id='0')),
        ('wrong-attempt', 'identity', lambda d: d['workflow'].update(attempt='0')),
        ('empty-sdk', 'identity', lambda d: d['sdk'].update(files_sha256={}, prefix_files=0)),
        ('program-mismatch', 'scenarios', lambda d: d['tool'].update(sha256='0' * 64)),
        ('duplicate-case', 'scenarios', lambda d: d['cases'].append(d['cases'][0])),
        ('failed-check', 'scenarios', lambda d: d['cases'][0]['checks'][0].update(ok=False)),
        ('string-case-result', 'scenarios', lambda d: d['cases'][0].update(passed='true')),
        ('incorrect-summary-count', 'scenarios', lambda d: d['summary'].update(checks=0)),
        ('browser-exporter-mismatch', 'e2e', lambda d: d.update(exporter_sha256='0' * 64)),
        ('browser-pack-mismatch', 'e2e', lambda d: d['pack'].update(sha256='0' * 64)),
        ('missing-legacy-source', 'e2e', lambda d: d['legacy_sources'].pop('store.js')),
        ('missing-browser-check', 'e2e', lambda d: d['checks'].pop()),
        ('duplicate-browser-check', 'e2e', lambda d: d['checks'].__setitem__(1, d['checks'][0])),
        ('unknown-browser-check', 'e2e', lambda d: d['checks'][0].update(id='unknown')),
        ('failed-browser-check', 'e2e', lambda d: d['checks'][0].update(ok=False)),
        ('review-source-mismatch', 'review', lambda d: d.update(source_sha='0' * 40)),
        ('missing-review-check', 'review', lambda d: d['checks'].pop()),
        ('duplicate-review-check', 'review', lambda d: d['checks'].__setitem__(1, d['checks'][0])),
        ('unknown-review-check', 'review', lambda d: d['checks'][0].update(name='unknown')),
    ]
    for name, kind, change in changes:
        with tempfile.TemporaryDirectory(prefix='migration-gate-review-') as temporary:
            destination = Path(temporary) / 'evidence'
            shutil.copytree(args.evidence, destination)
            path = destination / (kind + '-linux.json')
            record = json.loads(path.read_text(encoding='utf-8'))
            change(record)
            path.write_text(json.dumps(record), encoding='utf-8')
            assert not accepted(destination), name
            checks.append({'name': name + ' refused', 'passed': True})
    result = {'schema': 1, 'passed': True, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'checks': checks}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'gate_review_checks': len(checks)}))


if __name__ == '__main__':
    main()
