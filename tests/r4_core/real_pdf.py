#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the two retained Adobe PDF failures using the frozen R2 inputs in CI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not os.environ.get('GITHUB_ACTIONS'):
        raise SystemExit('Run only in GitHub Actions')
    binary, location, assets, manifest, output = map(Path, sys.argv[1:])
    font = Path('tests/fixtures/fonts/primary.ttf').resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in json.loads(manifest.read_text())['files']:
        if entry['id'] not in ('nist-csf2', 'nasa-solar-system'):
            continue
        source = (assets / entry['path']).resolve()
        row = {'id': entry['id'], 'input_sha256': digest(source), 'results': []}
        if row['input_sha256'] != entry['sha256']:
            raise ValueError('Frozen input identity mismatch')
        for mode, program in (('full', binary), ('location', location)):
            stdout, stderr = output / (entry['id'] + '-' + mode + '.jsonl'), output / (entry['id'] + '-' + mode + '.stderr')
            result = {'mode': mode, 'exit': None, 'report': None}
            try:
                with stdout.open('wb') as out, stderr.open('wb') as err:
                    completed = subprocess.run([str(program.resolve()), str(source), str(font)],
                        stdout=out, stderr=err, timeout=entry['limits']['wall_seconds'])
                result['exit'] = completed.returncode
                result['report'] = json.loads(stdout.read_text().splitlines()[-1])
            except (subprocess.TimeoutExpired, ValueError, IndexError) as error:
                result['failure'] = type(error).__name__
            report = result['report'] or {}
            count = report.get('pages') if mode == 'full' else report.get('units')
            result['passed'] = (result['exit'] == 0 and report.get('status') == 0 and
                report.get('complete') is True and count == entry['source_structure']['pages'])
            result.update(stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
            row['results'].append(result)
            print(json.dumps({'document': entry['id'], **result}), flush=True)
        row['unchanged'] = digest(source) == entry['sha256']
        rows.append(row)
    report = {'schema': 1, 'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'scope': 'two-retained-adobe-pdf-failures-only',
        'historical_1710_accepted': False, 'r2_package_accepted': False,
        'corpus_registration': 'ea5c13e081cfba86d9f6dd759439894463e51126',
        'corpus_tools_sha': '232a1806c38e0775892da2b4dd82fe6cd90414b2',
        'manifest_sha256': digest(manifest), 'binary_sha256': digest(binary),
        'location_sha256': digest(location), 'font_sha256': digest(font), 'documents': rows}
    report['accepted'] = (len(rows) == 2 and all(row['unchanged'] and
        all(result['passed'] for result in row['results']) for row in rows))
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
