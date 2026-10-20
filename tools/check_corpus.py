#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Probe every manifest entry in an isolated process, retaining every outcome.

This checks open/paginate/render/text completion, not visual fidelity or saving.
An expectation must be declared before a matching outcome can count as passed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import time
from threading import Lock

ROOT = Path(__file__).absolute().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def valid_report(report):
    if not isinstance(report, dict) or type(report.get('schema')) is not int or report['schema'] != 1:
        return False
    for key in ('status', 'parts', 'completed_parts', 'pages', 'text_bytes'):
        if type(report.get(key)) is not int or report[key] < 0:
            return False
    return (type(report.get('complete')) is bool and
            isinstance(report.get('engine_version'), str) and bool(report['engine_version']) and
            report.get('stage') in ('arguments', 'font', 'open', 'load', 'paginate', 'render', 'text') and
            report['completed_parts'] <= report['parts'] and
            (not report['complete'] or (report['status'] == 0 and
             report['parts'] == report['completed_parts'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('font', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, help='input root; defaults to manifest parent')
    parser.add_argument('--runtime', type=Path, action='append', default=[])
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--max-pages', type=int, default=0, help='0 = complete; a cap is only sampled coverage')
    parser.add_argument('--workers', type=int, default=1, help='independent document processes, 1..8')
    parser.add_argument('--max-files', type=int, default=0, help='0 = all entries')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('--workers must be in 1..8')
    if not math.isfinite(args.timeout) or args.timeout <= 0 or min(args.max_pages, args.max_files) < 0:
        parser.error('Require a positive finite timeout and nonnegative limits')
    binary, font, manifest = (p.absolute() for p in (args.binary, args.font, args.manifest))
    output = args.output.absolute()
    root = (args.root or manifest.parent).absolute()
    if output.exists():
        parser.error('Choose a new output directory to preserve evidence')
    records = json.loads(manifest.read_text(encoding='utf-8-sig'))
    manifest_complete, declared_target = True, None
    if isinstance(records, dict):
        manifest_complete = records.get('complete', True) is True
        declared_target = records.get('target')
        records = records['files']
    if not isinstance(records, list) or not records:
        parser.error('Manifest must contain a nonempty file list')
    if any(not isinstance(entry, dict) or not isinstance(entry.get('path'), str) or
           not isinstance(entry.get('sha256'), str) for entry in records):
        parser.error('Each manifest entry requires string path and sha256 fields')
    runtimes = sorted(set([p.absolute() for p in args.runtime] +
        list(binary.parent.glob('*.dll')) + list(binary.parent.glob('libexreader*.dylib')) +
        list(binary.parent.glob('libexreader*.so*')) +
        list((binary.parent.parent/'lib').glob('libexreader*.so*')) +
        list((binary.parent.parent/'lib').glob('libexreader*.dylib'))))
    identities = {str(p): digest(p) for p in [binary, font, manifest, *runtimes]}
    tool_hashes = {str(p.relative_to(ROOT)): digest(p) for p in
                  [Path(__file__).absolute(), ROOT/'tools/check_document.c']}
    git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'],
                           capture_output=True, text=True)
    output.mkdir(parents=True)
    seen = set()
    seen_lock = Lock()
    selected = records[:args.max_files] if args.max_files else records
    def inspect(index, entry):
        folder = output/f'{index:05d}'
        folder.mkdir()
        result = {'index': index, 'input': entry, 'classification': 'invalid_input'}
        started = time.monotonic()
        try:
            relative = Path(entry['path'].replace('\\', '/'))
            path = (root/relative).absolute()
            if relative.is_absolute() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Input must stay within the declared corpus root')
            with seen_lock:
                if str(path.resolve()) in seen:
                    raise ValueError('Duplicate input path')
                seen.add(str(path.resolve()))
            before = digest(path)
            result['observed_sha256'] = before
            if before != entry['sha256']:
                raise ValueError('Input hash mismatch')
            command = [str(binary), str(path), str(font), str(args.max_pages)]
            result['command'] = command
            try:
                with (folder/'stdout.json').open('wb') as stdout, (folder/'stderr.log').open('wb') as stderr:
                    process = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout)
                result['exit_code'] = process.returncode
                result['classification'] = 'invalid_report'
                report = json.loads((folder/'stdout.json').read_text(encoding='utf-8'))
                if valid_report(report):
                    result['report'] = report
                    expected = entry.get('expected')
                    consistent_exit = process.returncode == (0 if report['status'] == 0 and report['complete'] else 1)
                    if not consistent_exit:
                        result['classification'] = 'process_failure'
                    elif report['status'] == 0 and not report['complete']:
                        result['classification'] = 'incomplete'
                    elif not isinstance(expected, dict) or not {'status', 'complete'} <= expected.keys():
                        result['classification'] = 'untriaged'
                    elif (type(expected['status']) is not int or type(expected['complete']) is not bool or
                          (expected['status'] != 0 and not entry.get('expectation_reason'))):
                        result['classification'] = 'invalid_expectation'
                    elif all(report.get(k) == v for k, v in expected.items()):
                        result['classification'] = 'passed' if report['complete'] else 'expected_rejection'
                    else:
                        result['classification'] = 'unexpected_outcome'
            except subprocess.TimeoutExpired:
                result['classification'] = 'timeout'
            except (ValueError, UnicodeError):
                result['classification'] = 'invalid_report'
            if digest(path) != before:
                result['classification'] = 'input_changed'
        except (OSError, ValueError, KeyError, TypeError) as error:
            result['error'] = str(error)
        result['wall_seconds'] = time.monotonic()-started
        result['evidence'] = {p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file()}
        (folder/'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        return {'index': index, 'path': entry.get('path'), 'classification': result['classification'],
                'observed': result.get('report'),
                'result': str(folder/'result.json'), 'sha256': digest(folder/'result.json')}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda item: inspect(*item), enumerate(selected)))
    unchanged = all(p.is_file() and digest(p) == sha for name, sha in identities.items() for p in [Path(name)])
    counts = {key: sum(r['classification'] == key for r in results)
              for key in sorted({r['classification'] for r in results})}
    count_matches = declared_target is None or (type(declared_target) is int and declared_target == len(records))
    accepted = unchanged and manifest_complete and count_matches and len(selected) == len(records) and not args.max_pages and all(
        r['classification'] in ('passed', 'expected_rejection') for r in results)
    summary = {'schema': 1, 'source_sha': git.stdout.strip(), 'source_dirty': bool(dirty.stdout.strip()),
               'platform': platform.platform(), 'identities': identities, 'identities_unchanged': unchanged,
               'tool_hashes': tool_hashes,
               'scope': 'open, all-page render, text extraction; no fidelity/save claim',
               'manifest_entries': len(records), 'manifest_complete': manifest_complete,
               'declared_target': declared_target, 'checked_entries': len(results),
               'page_limit': args.max_pages, 'workers': args.workers, 'counts': counts,
               'completed_documents': sum(r['observed'] is not None and r['observed']['complete'] for r in results),
               'accepted': accepted, 'results': results}
    (output/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'checked': len(results), 'counts': counts, 'accepted': accepted}))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
