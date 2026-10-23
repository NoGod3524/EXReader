#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict representative reading acceptance, executed only in Actions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_corpus import digest


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def registered(manifest, anchor):
    if len(anchor) != 40 or any(c not in '0123456789abcdef' for c in anchor):
        raise ValueError('Full registration SHA required')
    path = manifest.resolve().relative_to(ROOT).as_posix()
    git('merge-base', '--is-ancestor', anchor, 'HEAD')
    if git('show', f'{anchor}:{path}') != manifest.read_bytes():
        raise ValueError('Frozen manifest differs from registration')
    additions = git('log', '--reverse', '--diff-filter=A', '--format=%H', 'HEAD', '--', path).decode().splitlines()
    if not additions or additions[0] != anchor:
        raise ValueError('Registration must be the first addition of this path')
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Tracked source is modified')


def location_probe(binary, font, entry, assets, folder):
    folder.mkdir(parents=True)
    before = digest(assets / entry['path'])
    result = {'id': entry['id'], 'classification': 'invalid_input', 'input_sha256': before}
    start = time.monotonic()
    if before != entry['sha256']:
        raise ValueError('Input hash mismatch before location probe')
    try:
        with (folder / 'stdout.jsonl').open('wb') as out, (folder / 'stderr.log').open('wb') as err:
            proc = subprocess.run([str(binary), str(assets / entry['path']), str(font)],
                                  stdout=out, stderr=err, timeout=entry['limits']['wall_seconds'])
        result['exit_code'] = proc.returncode
        rows = [json.loads(line) for line in (folder / 'stdout.jsonl').read_text().splitlines()]
        report = rows[-1]
        result['observed'] = report
        valid = (report.get('schema') == 1 and type(report.get('status')) is int and
                 type(report.get('complete')) is bool and
                 all(type(report.get(k)) is int and report[k] >= 0 for k in ('units', 'checked', 'empty')) and
                 report['checked'] + report['empty'] <= report['units'] and
                 proc.returncode == (0 if report['status'] == 0 and report['complete'] else 1))
        result['classification'] = ('passed' if valid and report['status'] == 0 and report['complete'] and
            report['checked'] > 0 and report['checked'] + report['empty'] == report['units'] and
            len(rows) == report['units'] + 1 else 'location_failure')
    except subprocess.TimeoutExpired:
        result['classification'] = 'timeout'
    except (ValueError, KeyError, IndexError, UnicodeError):
        result['classification'] = 'invalid_report'
    if digest(assets / entry['path']) != before:
        result['classification'] = 'input_changed'
    result['wall_seconds'] = time.monotonic() - start
    result['evidence'] = {p.name: digest(p) for p in folder.iterdir() if p.is_file()}
    (folder / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def validate_report(report):
    return (report.get('scope') == 'representative-real-v1-only' and
            report.get('historical_1710_accepted') is False and
            report.get('manifest_entries') == 8 and report.get('source_dirty') is False and
            report.get('identities_unchanged') is True and
            len(report.get('documents', [])) == 8 and
            all(r.get('full_classification') == 'passed' and r.get('location_classification') == 'passed'
                for r in report['documents']) and report.get('full_probe_accepted') is True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--registered-at', required=True)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--location', type=Path, required=True)
    p.add_argument('--font', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    for name in ('manifest', 'assets', 'binary', 'location', 'font', 'output'):
        setattr(a, name, getattr(a, name).resolve())
    if a.output.exists():
        p.error('Output already exists; preserve earlier evidence')
    registered(a.manifest, a.registered_at)
    data = json.loads(a.manifest.read_text())
    if (data.get('dataset_id') != 'reading-real-v1' or data.get('complete') is not True or
            data.get('target') != 8 or len(data['files']) != 8 or
            len({x['sha256'] for x in data['files']}) != 8 or
            any(x['expected'] != {'status': 0, 'complete': True} for x in data['files'])):
        raise ValueError('Complete predeclared real-v1 inventory and success expectations required')
    a.output.mkdir(parents=True)
    tracked = [a.manifest, a.binary, a.location, a.font, Path(__file__),
               ROOT / 'tools/reading_corpus/collect.py', ROOT / 'tools/check_corpus.py',
               ROOT / 'tools/check_document.c', ROOT / 'tests/reading_corpus/location.c']
    identities = {str(x.relative_to(ROOT) if x.is_relative_to(ROOT) else x): digest(x) for x in tracked}
    identity_paths = {str(x): digest(x) for x in tracked}
    with (a.output / 'full-controller.log').open('wb') as log:
        subprocess.run([sys.executable, str(ROOT / 'tools/check_corpus.py'), str(a.binary), str(a.font),
                        str(a.manifest), str(a.output / 'full'), '--root', str(a.assets),
                        '--timeout', '120', '--workers', '1'], stdout=log, stderr=subprocess.STDOUT, check=False)
    full = json.loads((a.output / 'full/summary.json').read_text())
    documents = []
    for index, entry in enumerate(data['files']):
        loc = location_probe(a.location, a.font, entry, a.assets, a.output / 'location' / f'{index:05d}')
        item = full['results'][index]
        record = {'id': entry['id'], 'format': entry['format'], 'sha256': entry['sha256'],
                  'full_classification': item['classification'], 'full_observed': item.get('observed'),
                  'full_result': item['result'], 'full_result_sha256': item['sha256'],
                  'location_classification': loc['classification'], 'location_observed': loc.get('observed'),
                  'location_result': f'location/{index:05d}/result.json',
                  'location_result_sha256': digest(a.output / 'location' / f'{index:05d}' / 'result.json')}
        documents.append(record)
        print(json.dumps({'document': record}), flush=True)
    stable = (all(digest(Path(path)) == value for path, value in identity_paths.items()) and
              not git('status', '--porcelain', '--untracked-files=no').strip() and
              all(digest(a.assets / x['path']) == x['sha256'] for x in data['files']))
    report = {'schema': 1, 'scope': 'representative-real-v1-only',
              'historical_1710_accepted': False, 'historical_failures_reproduced': False,
              'complete_product': False, 'source_sha': git('rev-parse', 'HEAD').decode().strip(),
              'source_dirty': bool(git('status', '--porcelain', '--untracked-files=no').strip()),
              'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'manifest_path': a.manifest.relative_to(ROOT).as_posix(), 'manifest_sha256': digest(a.manifest),
              'registration_sha': a.registered_at, 'manifest_entries': 8,
              'font_sha256': digest(a.font), 'identities': identities, 'identities_unchanged': stable,
              'full_probe_accepted': full['accepted'], 'full_counts': full['counts'],
              'location_counts': {k: sum(x['location_classification'] == k for x in documents)
                                  for k in sorted({x['location_classification'] for x in documents})},
              'documents': documents}
    report['accepted'] = validate_report(report)
    (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
            output.write(f"accepted={str(report['accepted']).lower()}\nmanifest_sha256={report['manifest_sha256']}\n")
    print(json.dumps({k: report[k] for k in ('source_sha', 'run_id', 'run_attempt', 'manifest_sha256',
        'registration_sha', 'scope', 'full_counts', 'location_counts', 'accepted')}), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
