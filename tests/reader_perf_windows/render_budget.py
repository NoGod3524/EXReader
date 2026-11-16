#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Repeat the production host render path on a fixed SHA-256 book manifest.

Each baseline/candidate sample starts a fresh process, so their peak working sets
are independent. Retain raw samples and recompute percentiles outside the host.
Display frame pacing and first interactive remain explicitly unmeasured.
"""
import argparse
import hashlib
import json
import os
import platform
import math
import re
import statistics
import subprocess
import tempfile
import urllib.request
from pathlib import Path


def identity(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def metrics(stdout, expected_part=None):
    paths = re.findall(r'^BUDGET load_path=([^\r\n]+)', stdout, re.M)
    raw = re.findall(r'BUDGET raw_render_ms=(\[[^\n]+\])', stdout)
    raw_present = re.findall(r'BUDGET raw_present_ms=(\[[^\n]+\])', stdout)
    summaries = re.findall(
        r'render_p50_ms=([\d.]+) render_p95_ms=([\d.]+) '
        r'present_p50_ms=([\d.]+) present_p95_ms=([\d.]+) '
        r'd2d_last_present_ms=([\d.]+) peak_working_set_bytes=(\d+)', stdout)
    ready = re.findall(
        r'setup_render_ready_ms=([\d.]+) first_interactive_ms=([\d.]+) d2d_present_count=(\d+)', stdout)
    if (len(paths) != 1 or len(raw) != 1 or len(raw_present) != 1
            or len(summaries) != 1 or len(ready) != 1):
        raise ValueError('expected exactly one complete fresh-process cohort with render+present+interactive telemetry')
    if expected_part is not None and not re.fullmatch(
            r'production-bounded-epub part=\d+ part_path=' + re.escape(expected_part), paths[0]):
        raise ValueError('host did not use the fixed production bounded EPUB part')
    samples = json.loads(raw[0])
    present_samples = json.loads(raw_present[0])
    if (len(samples) != 64 or len(present_samples) != 64
            or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in samples)
            or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in present_samples)):
        raise ValueError('expected 64 finite positive raw render and present samples')
    p50, p95 = statistics.median(samples), sorted(samples)[math.ceil(.95*len(samples))-1]
    pp50, pp95 = statistics.median(present_samples), sorted(present_samples)[math.ceil(.95*len(present_samples))-1]
    printed50, printed95, printed_p50, printed_p95, d2d_last, peak = map(float, summaries[0])
    setup, interactive, d2d_count = float(ready[0][0]), float(ready[0][1]), int(ready[0][2])
    if (abs(p50-printed50) > .000002 or abs(p95-printed95) > .000002
            or abs(pp50-printed_p50) > .000002 or abs(pp95-printed_p95) > .000002
            or peak <= 0 or setup <= 0 or interactive < setup or d2d_count < 2):
        raise ValueError('summary disagrees with raw samples or has invalid memory/setup/interactive')
    return dict(load_path=paths[0], raw_render_ms=samples, raw_present_ms=present_samples,
                render_p50_ms=p50, render_p95_ms=p95, present_p50_ms=pp50, present_p95_ms=pp95,
                d2d_last_present_ms=d2d_last, d2d_initial_present_count=d2d_count,
                peak_working_set_bytes=int(peak), setup_render_ready_ms=setup,
                first_interactive_ms=interactive)


LIMITS = {'render_p50_ms': 2.5, 'render_p95_ms': 2.5,
          'present_p50_ms': 2.5, 'present_p95_ms': 2.5,
          'peak_working_set_bytes': 1.25, 'setup_render_ready_ms': 2.5,
          'first_interactive_ms': 2.5}
ABSOLUTE_BUDGETS = {
    'first_interactive_ms': 2500.0,
    'render_p50_ms': 50.0,
    'render_p95_ms': 100.0,
    'present_p50_ms': 50.0,
    'present_p95_ms': 100.0,
    'peak_working_set_bytes': 268435456,
}


def compare(baseline, candidate, budgets=None):
    budgets = dict(ABSOLUTE_BUDGETS, **(budgets or {}))
    ratios = {key: statistics.median(x[key] for x in candidate) /
                   statistics.median(x[key] for x in baseline) for key in LIMITS}
    medians = {key: statistics.median(x[key] for x in candidate) for key in budgets}
    ratios_ok = all(value < LIMITS[key] for key, value in ratios.items())
    budgets_ok = all(medians[key] <= budgets[key] for key in budgets)
    return {'ratios': ratios, 'candidate_medians': medians, 'budgets': budgets,
            'ratios_passed': ratios_ok, 'budgets_passed': budgets_ok,
            'passed': bool(ratios_ok and budgets_ok)}


def fetch_corpus(manifest, directory):
    """Fetch provenance URLs, refusing regenerated upstream files."""
    directory.mkdir(parents=True, exist_ok=True)
    for book in manifest['books']:
        path = directory / book['file']
        if path.is_file() and identity(path)['sha256'] == book['sha256']:
            print('verified cached original:', book['file'])
            continue
        with urllib.request.urlopen(book['source'], timeout=60) as response:
            data = response.read((32 << 20) + 1)
        if len(data) > 32 << 20 or hashlib.sha256(data).hexdigest() != book['sha256']:
            raise ValueError('upstream original changed or exceeded limit: ' + book['file'])
        if path.exists():
            raise ValueError('refusing to overwrite existing mismatched original: ' + str(path))
        with path.open('xb') as output:
            output.write(data)
        print('downloaded and SHA-256 verified:', book['file'], len(data))


def self_check():
    raw = list(range(1, 65))
    praw = [0.5 * x for x in range(1, 65)]
    text = (
        'BUDGET load_path=fixture-document\n'
        'BUDGET setup_render_ready_ms=1.0 first_interactive_ms=2.0 d2d_present_count=2\n'
        'BUDGET raw_render_ms=' + json.dumps(raw) + '\n'
        'BUDGET raw_present_ms=' + json.dumps(praw) + '\n'
        'BUDGET cohort=0 n=64 render_p50_ms=32.500000 render_p95_ms=61.000000 '
        'present_p50_ms=16.250000 present_p95_ms=30.500000 d2d_last_present_ms=0.250000 '
        'peak_working_set_bytes=1024\n'
    )
    parsed = metrics(text)
    assert parsed['render_p95_ms'] == 61 and parsed['present_p95_ms'] == 30.5 and compare([parsed], [parsed])['passed']
    assert not compare([parsed], [dict(parsed, peak_working_set_bytes=2048)])['passed']
    assert not compare([parsed], [dict(parsed, render_p95_ms=200)])['passed']
    assert not compare([parsed], [dict(parsed, present_p95_ms=200)])['passed']
    assert not compare([parsed], [dict(parsed, first_interactive_ms=5000)])['passed']
    assert not compare([parsed], [dict(parsed, peak_working_set_bytes=1280)])['passed']
    bounded = text.replace('fixture-document', 'production-bounded-epub part=1 part_path=OEBPS/body.xhtml')
    assert metrics(bounded, 'OEBPS/body.xhtml')['load_path'].startswith('production-bounded-epub')
    for wrong in [text, bounded.replace('body.xhtml', 'other.xhtml'), bounded + bounded]:
        try:
            metrics(wrong, 'OEBPS/body.xhtml')
        except ValueError:
            continue
        raise AssertionError('wrong or missing production EPUB load path accepted')
    for bad in [text + text, text.replace('61.000000', '62.000000'),
                text.replace('32.500000', '33.500000'),
                text.replace('30.500000', '31.500000'),
                text.replace('16.250000', '17.250000'),
                '\n'.join(text.splitlines()[1:]), '\n'.join(text.splitlines()[:3]),
                text.replace('BUDGET load_path=', 'missing='),
                text.replace('setup_render_ready_ms=1.0', 'setup_render_ready_ms=0'),
                text.replace('first_interactive_ms=2.0', 'first_interactive_ms=0.5'),
                text.replace('d2d_present_count=2', 'd2d_present_count=1'),
                text.replace('BUDGET raw_render_ms=', 'missing='),
                text.replace('BUDGET raw_present_ms=', 'missing='),
                text.replace('[1, 2,', '[0, 2,'), text.replace(', 64]', ']'),
                text.replace('1024', '0'), text.replace('[1, 2,', '[NaN, 2,')]:
        try:
            metrics(bad)
        except ValueError:
            continue
        raise AssertionError('invalid report accepted')
    print('PASS fresh-process budget contract: raw render+present p50/p95 and first_interactive verified; missing/duplicate/nonfinite/zero/mismatched samples rejected; memory/time regressions rejected')
    with tempfile.TemporaryDirectory(prefix='exreader-corpus-contract-') as temporary:
        directory = Path(temporary)
        book = {'file': 'original.epub', 'source': 'data:text/plain,frozen-original',
                'sha256': hashlib.sha256(b'frozen-original').hexdigest()}
        fetch_corpus({'books': [book]}, directory)
        fetch_corpus({'books': [book]}, directory)
        bad = dict(book, file='bad.epub', sha256='0'*64)
        try:
            fetch_corpus({'books': [bad]}, directory)
        except ValueError:
            pass
        else:
            raise AssertionError('changed upstream original accepted')
        assert not (directory / 'bad.epub').exists()
        (directory / book['file']).write_bytes(b'keep-existing')
        try:
            fetch_corpus({'books': [book]}, directory)
        except ValueError:
            pass
        else:
            raise AssertionError('existing mismatched original overwritten')
        assert (directory / book['file']).read_bytes() == b'keep-existing'
    print('PASS fixed production spine path; corpus fetch/cached hash checks; changed original and overwrite refused')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--fetch-corpus', action='store_true', help='Download manifest URLs with strict frozen SHA-256 checks, then exit')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--baseline-binary', type=Path)
    parser.add_argument('--baseline-source', help='Explicit source revision of the baseline executable')
    parser.add_argument('--font', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--corpus', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.fetch_corpus:
        if not args.manifest or not args.corpus:
            parser.error('--manifest/--corpus required with --fetch-corpus')
        fetch_corpus(json.loads(args.manifest.read_text(encoding='utf-8')), args.corpus)
        return 0
    if not all([args.binary, args.font, args.manifest, args.corpus, args.out]) or args.repeats < 2:
        parser.error('--binary/--font/--manifest/--corpus/--out and repeats >=2 required')
    baseline = args.baseline_binary or args.binary
    if args.baseline_binary and not args.baseline_source:
        parser.error('--baseline-source required with --baseline-binary')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    budgets = dict(ABSOLUTE_BUDGETS, **(manifest.get('budgets') or {}))
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    result = {'scope': 'host render + display-present + first-interactive path, independent processes, 8 warmups + 64 alternating page 0/1 samples',
              'platform': platform.platform(), 'processor': platform.processor(),
              'binary': identity(args.binary), 'font': identity(args.font),
              'baseline_binary': identity(baseline), 'baseline_source': args.baseline_source or source,
              'comparison_kind': 'two-binary comparison' if args.baseline_binary else 'same-binary repeatability',
              'manifest': identity(args.manifest), 'exporter': identity(Path(__file__)),
              'source': source,
              'advisory': False, 'accepted': False, 'product_budget_accepted': False,
              'environment': {'logical_cpus': os.cpu_count(), 'ram_bytes': 'unknown',
                              'compiler': 'unknown (see configure/build logs)',
                              'flags': 'unknown (see configure/build logs)',
                              'runner_label': os.environ.get('RUNNER_ENVIRONMENT', 'local Windows'),
                              'run': os.environ.get('GITHUB_RUN_ID'),
                              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT')},
              'display_present_frame': 'measured (compose_page_view + paint_page_view + D2D shell_paint + GdiFlush)',
              'first_interactive': 'measured (cold bounded-EPUB import/open + initial frame present + keyboard selection round-trip)',
              'book_load_path': 'production EPUB import/source/presentation wrapper/bounded pager; fixed spine part',
              'thresholds': LIMITS, 'budgets': budgets, 'repeats': args.repeats, 'books': []}
    failed = False
    for book in manifest['books']:
        path = args.corpus / book['file']
        actual = identity(path)
        if actual['sha256'] != book['sha256']:
            raise SystemExit('fixed corpus hash mismatch: ' + book['file'])
        if not isinstance(book.get('part_path'), str) or not book['part_path']:
            raise SystemExit('fixed spine part missing: ' + book['file'])
        env = dict(os.environ, EXR_AUDIT_BOOK=str(path.resolve()), EXR_BUDGET_SINGLE_PROCESS='1',
                   EXR_BUDGET_PART_PATH=book['part_path'])
        entry = dict(actual, baseline=[], candidate=[])
        for repeat in range(args.repeats):
            # Alternate AB/BA to reduce simple ordering bias; never share a process peak.
            order = [('baseline', baseline), ('candidate', args.binary)]
            if repeat % 2:
                order.reverse()
            for label, binary in order:
                try:
                    run = subprocess.run([str(binary.resolve()), 'render-budget', str(args.font.resolve())],
                                         env=env, capture_output=True, text=True, timeout=180)
                    sample = dict(repeat=repeat, exit=run.returncode, stdout=run.stdout, stderr=run.stderr)
                except (OSError, subprocess.TimeoutExpired) as error:
                    sample = dict(repeat=repeat, exit=None, stdout='', stderr=str(error), error=type(error).__name__)
                try:
                    if sample['exit'] != 0:
                        raise ValueError('host process failed')
                    sample['metrics'] = metrics(sample['stdout'], book['part_path'])
                except ValueError as error:
                    sample['error'] = str(error)
                    failed = True
                entry[label].append(sample)
                print(book['file'], label, repeat, 'exit=', sample['exit'], '\n' + sample['stdout'] + sample['stderr'])
        if all('metrics' in sample for label in ['baseline', 'candidate'] for sample in entry[label]):
            entry['comparison'] = compare([x['metrics'] for x in entry['baseline']],
                                          [x['metrics'] for x in entry['candidate']], budgets)
            failed |= not entry['comparison']['passed']
            print(book['file'], json.dumps(entry['comparison']))
        result['books'].append(entry)
    result['passed'] = bool(result['books']) and not failed
    result['accepted'] = result['passed']
    result['product_budget_accepted'] = result['passed']
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
