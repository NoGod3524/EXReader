# SPDX-License-Identifier: MIT
"""Actions-only real selected-file owner, stable source and mapping checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    for name in ('probe', 'font', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    args.output.mkdir(parents=True)
    manifest = json.loads((args.fixtures / 'manifest.json').read_text())
    report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  accepted=False, ok=False, checks=[], probe_sha256=hashlib.sha256(args.probe.read_bytes()).hexdigest())

    def check(name, condition):
        report['checks'].append(dict(name=name, passed=bool(condition)))
        print(json.dumps(report['checks'][-1]), flush=True)
        assert condition, name

    def run(name, payload, mode, expected, originals):
        folder = args.output / name
        folder.mkdir(mode=0o700)
        database = folder / 'library.sqlite'
        summary = folder / 'summary.tsv'
        result = subprocess.run([str(args.probe), str(database), str(args.font), str(args.fixtures / payload), str(summary), mode],
                                capture_output=True, text=True, timeout=120)
        (folder / 'execution.log').write_text(result.stdout + result.stderr)
        check(name + '_owner_completed', result.returncode == (0 if expected else 3))
        if expected:
            check(name + '_exact_declared_counts', [int(value) for value in summary.read_text().strip().split('\t')] == expected)
        actual = folder / 'originals.tsv'
        inspect = subprocess.run([str(args.probe), str(database), str(args.font), str(actual), 'unused', 'inspect'], capture_output=True, text=True, timeout=60)
        (folder / 'inspect.log').write_text(inspect.stdout + inspect.stderr)
        check(name + '_public_original_and_product_mapping_readback', inspect.returncode == 0)
        rows = [line.split('\t') for line in actual.read_text().splitlines()]
        observed = {(row[1], row[2], int(row[3])) for row in rows}
        wanted = {(row['format'], row['sha256'], row['bytes']) for row in originals}
        check(name + '_exact_originals_without_duplicate_rows', observed == wanted and len(rows) == len(wanted))

    try:
        run('mixed', 'mixed.uris', 'uri', [1, 0, 0, 20, 10, 1, 9, 20, 1, 0], manifest['mixed'])
        run('gnome_cut', 'bulk.gnome', 'gnome', [1, 0, 0, 40, 40, 0, 0, 40, 0, 0], manifest['bulk'])
        run('bounded_overflow', 'overflow.uris', 'uri', [0, 1, 0, 256, 256, 0, 0, 256, 0, 44], manifest['overflow'][:256])
        run('cancel', 'bulk.uris', 'uri-cancel', [0, 0, 1, 1, 1, 0, 0, 40, 0, 0], manifest['bulk'][:1])
        run('empty', 'empty.uris', 'uri', None, [])
        run('oversize', 'oversize.uris', 'uri', None, [])
        check('every_selected_or_rejected_source_unchanged', all(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256'] for row in manifest['originals']))
        report['ok'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
