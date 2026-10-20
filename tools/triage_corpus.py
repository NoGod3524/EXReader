#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Retain independent diagnostics for failed corpus entries; never change expectations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from check_corpus import digest, valid_report
from check_pdf_reference import valid_reference

ROOT = Path(__file__).absolute().parents[1]


def evidence(path):
    return {'path': str(path), 'sha256': digest(path)}


def verified_result(record):
    path = Path(record['result'])
    if digest(path) != record['sha256']:
        raise ValueError('Result evidence hash mismatch: '+str(path))
    result = json.loads(path.read_text(encoding='utf-8'))
    for name, sha in result['evidence'].items():
        if Path(name).name != name or digest(path.parent/name) != sha:
            raise ValueError('Result attachment hash mismatch: '+str(path))
    return result


def limit_kind(reason):
    reason = reason.lower()
    for phrase, kind in (
        ('decoded image cache', 'decoded_image_cache'),
        ('unbreakable content', 'unbreakable_page_height'),
        ('scalar limit', 'inline_scalar_count'),
        ('shaping work', 'shaping_work'),
        ('table', 'table_layout_budget'),
        ('glyph', 'glyph_or_line_budget'),
        ('line buffer', 'glyph_or_line_budget'),
        ('text work', 'text_work'),
    ):
        if phrase in reason:
            return kind
    return 'other_budget'


def category(status, reference):
    if status == 6:
        return 'resource_limit'
    if status == 1:
        return 'engine_argument_failure'
    if status == 8:
        return 'font_failure'
    if status == 11:
        return 'unsupported_feature'
    if status == 5 and reference and reference.get('complete'):
        return 'reference_repaired_input' if reference.get('repaired') else 'reference_completed_primary_rejected'
    if reference and reference.get('password_required'):
        return 'reference_requires_password'
    return 'requires_review'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('binary', type=Path)
    parser.add_argument('font', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--pdf-reference', action='store_true')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or not 0 < args.timeout <= 3600:
        parser.error('Require 1..8 workers and a timeout in (0,3600]')
    output, root = args.output.absolute(), args.root.absolute()
    if output.exists():
        parser.error('Choose a new directory to preserve existing evidence')
    if args.pdf_reference and importlib.util.find_spec('pymupdf') is None:
        parser.error('The independent PDF reference requires PyMuPDF')
    summary_path = args.summary.absolute()
    baseline = json.loads(summary_path.read_text(encoding='utf-8-sig'))
    original_hash = digest(summary_path)
    failures, ledger = [], []
    for record in baseline['results']:
        result_path = Path(record['result'])
        original = verified_result(record)
        observed = original.get('report')
        completed = (valid_report(observed) and observed['complete'] and original['classification'] in
                     ('passed', 'unexpected_outcome', 'untriaged', 'invalid_expectation'))
        item = {'baseline_index': original['index'], 'input': original['input'],
                'baseline_result': evidence(result_path), 'baseline_observed': observed,
                'baseline_classification': original['classification'],
                'category': 'baseline_completed' if completed else 'requires_review'}
        path = root/Path(original['input']['path'].replace('\\', '/'))
        if not path.resolve().is_relative_to(root.resolve()) or digest(path) != original['input']['sha256']:
            raise ValueError('Input changed or outside root: '+str(path))
        if original['classification'] == 'timeout':
            item['category'] = 'not_completed_within_baseline_timeout'
        elif not completed:
            entry = dict(original['input'])
            entry['baseline_index'] = original['index']
            item['replay_index'] = len(failures)
            failures.append(entry)
        ledger.append(item)
    output.mkdir(parents=True)
    snapshots = {}
    source_hashes = {}
    for source in (Path(__file__).absolute(), ROOT/'tools/check_corpus.py',
                   ROOT/'tools/check_document.c', ROOT/'tools/check_pdf_reference.py'):
        destination = output/'tools-snapshot'/source.name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(source.read_bytes())
        snapshots[source.name] = evidence(destination)
        source_hashes[str(source)] = digest(destination)
    selected = output/'diagnostic-manifest.json'
    selected.write_text(json.dumps({'files': failures, 'complete': False,
        'target': baseline['manifest_entries'], 'scope': 'diagnostic subset; no acceptance claim'},
        indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    if failures:
        command = [sys.executable, str(ROOT/'tools/check_corpus.py'), str(args.binary.absolute()),
                   str(args.font.absolute()), str(selected), str(output/'replay'), '--root', str(root),
                   '--workers', str(args.workers), '--timeout', str(args.timeout)]
        with (output/'replay-controller.log').open('wb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        replay = json.loads((output/'replay/summary.json').read_text(encoding='utf-8'))
        if len(replay['results']) != len(failures) or not replay['identities_unchanged']:
            raise ValueError('Replay evidence incomplete or runtime changed')
    if args.pdf_reference:
        reference_identity = {'script': evidence(ROOT/'tools/check_pdf_reference.py'),
                              'interpreter': evidence(Path(sys.executable))}
        import pymupdf
        reference_identity['version'] = pymupdf.VersionBind
        reference_identity['native_modules'] = {str(p): digest(p) for pattern in ('*.pyd', '*.so*', '*.dll', '*.dylib')
            for p in Path(pymupdf.__file__).parent.glob(pattern)}
    else:
        reference_identity = None

    def diagnose(item):
        if 'replay_index' not in item:
            return item
        index = item['replay_index']
        folder = output/'replay'/f'{index:05d}'
        replay_path = folder/'result.json'
        result = verified_result(replay['results'][index])
        item['replay_result'] = evidence(replay_path)
        observed = result.get('report')
        if (not valid_report(observed) or result['classification'] not in
                ('passed', 'expected_rejection', 'unexpected_outcome', 'untriaged', 'incomplete')):
            item['category'] = 'diagnostic_'+result['classification']
            return item
        if observed['complete']:
            item['category'] = 'baseline_failure_not_reproduced'
            return item
        reference = None
        if args.pdf_reference:
            stdout, stderr = folder/'reference.json', folder/'reference.stderr.log'
            path = root/Path(item['input']['path'].replace('\\', '/'))
            try:
                with stdout.open('wb') as out, stderr.open('wb') as log:
                    process = subprocess.run([sys.executable, str(ROOT/'tools/check_pdf_reference.py'), str(path)],
                                             stdout=out, stderr=log, timeout=args.timeout)
                candidate = json.loads(stdout.read_text(encoding='utf-8'))
                item['reference_exit'] = process.returncode
                if valid_reference(candidate) and process.returncode == (0 if candidate['complete'] else 1):
                    reference = candidate
                else:
                    item['reference_incomplete'] = True
            except (subprocess.TimeoutExpired, ValueError, UnicodeError):
                item['reference_incomplete'] = True
            item['reference_evidence'] = {'stdout': evidence(stdout), 'stderr': evidence(stderr)}
            item['reference_observed'] = reference
        status = observed['status']
        item['category'] = category(status, reference)
        log = folder/'stderr.log'
        if status == 6:
            item['limit_kind'] = limit_kind(log.read_text(encoding='utf-8', errors='replace'))
        return item

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        ledger = list(pool.map(diagnose, ledger))
    counts = {key: sum(item['category'] == key for item in ledger)
              for key in sorted({item['category'] for item in ledger})}
    # Recheck every source/attachment and input after the independent processes.
    for record in baseline['results']:
        original = verified_result(record)
        if digest(root/Path(original['input']['path'].replace('\\', '/'))) != original['input']['sha256']:
            raise ValueError('Input changed during diagnostics')
    sources_stable = all(digest(Path(p)) == sha for p, sha in source_hashes.items())
    stable = digest(summary_path) == original_hash and sources_stable
    if reference_identity:
        stable = stable and all(digest(Path(p)) == sha for p, sha in reference_identity['native_modules'].items())
        stable = stable and all(digest(Path(reference_identity[k]['path'])) == reference_identity[k]['sha256']
                                for k in ('script', 'interpreter'))
    result = {'schema': 1, 'baseline': evidence(summary_path), 'baseline_unchanged': stable,
              'tool': evidence(Path(__file__).absolute()), 'tools_snapshot': snapshots,
              'source_tools_unchanged': sources_stable, 'reference_identity': reference_identity,
              'scope': 'diagnostic classification only; expectations unchanged; no fidelity/save acceptance',
              'accepted': False, 'baseline_accepted': baseline['accepted'],
              'entries': len(ledger), 'replayed': len(failures),
              'counts': counts, 'results': ledger}
    (output/'classification.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'entries': len(ledger), 'replayed': len(failures), 'counts': counts}))
    return 0 if stable else 1


if __name__ == '__main__':
    raise SystemExit(main())
