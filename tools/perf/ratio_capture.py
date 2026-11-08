"""Paired native reference/real-book sampler (measurement only, E3 advisory).

capture --build BUILD --font FONT --output NEW_DIR [--stress]
summarize CAPTURE_DIR
freeze BASELINE_DIR POLICY.json
check POLICY.json CANDIDATE_DIR RESULT.json
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from e1_capture import sha, stats, write, percentile

ROOT = Path(__file__).resolve().parents[2]
TIERS = {'warning': 1.10, 'gate': 1.25, 'hard': 1.50}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def execute(command, env):
    return subprocess.run(list(map(str, command)), env=env, capture_output=True,
                          timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def metrics(samples):
    if not samples or any(not all(isinstance(s[k], (int, float)) and
            math.isfinite(s[k]) and s[k] > 0 for k in ('total_ms', 'reference_ms')) for s in samples):
        raise ValueError('missing/nonpositive/nonfinite paired samples')
    for s in samples:
        if not math.isclose(s['ratio'], s['total_ms'] / s['reference_ms'], rel_tol=2e-5, abs_tol=2e-8):
            raise ValueError('paired ratio mismatch')
    target = percentile([s['total_ms'] for s in samples], 95)
    reference = percentile([s['reference_ms'] for s in samples], 95)
    return {'n': len(samples), 'target_ms': target, 'reference_ms': reference,
            'ratio': target / reference,
            'paired_ratio_p95': percentile([s['ratio'] for s in samples], 95)}


def signature(raw):
    keys = ('phase', 'part', 'page', 'width', 'height', 'pixel_hash', 'text_hash',
            'position_hash', 'text_start', 'text_end', 'position_items')
    return [[s[k] for k in keys] for s in raw['samples']]


def summarize(directory):
    directory = Path(directory)
    manifest = read(directory / 'capture.json')
    runs, signatures = [], {}
    for run in manifest['runs']:
        reference_path = directory / run['reference_file']
        if sha(reference_path) != run['reference_sha256']:
            raise ValueError('reference digest mismatch')
        calibration = read(reference_path)['reference_ms']
        if len(calibration) != 31 or any(not math.isfinite(v) or v <= 0 for v in calibration):
            raise ValueError('invalid calibration observations')
        pooled, books = [], {}
        if len(run['books']) != 19 or len({b['id'] for b in run['books']}) != 19:
            raise ValueError('exactly 19 distinct books required')
        for book in run['books']:
            path = directory / book['file']
            if sha(path) != book['sha256']:
                raise ValueError('raw digest mismatch')
            raw = read(path)
            if not raw['success'] or len(raw['samples']) != 17:
                raise ValueError('native probe incomplete; require first + 16 sequential pages')
            sig = signature(raw)
            if signatures.setdefault(book['id'], sig) != sig:
                raise ValueError('page/pixel/text/position signatures differ between runs')
            samples = [s for s in raw['samples'] if s['phase'] == 'sequential']
            if len(samples) != 16:
                raise ValueError('unexpected sequential operation plan')
            books[book['id']] = metrics(samples)
            pooled.extend(samples)
        runs.append({'index': run['index'], 'calibration_ms': percentile(calibration, 95),
                     **metrics(pooled), 'books': books})
    summary = {k: stats([r[k] for r in runs]) for k in
               ('calibration_ms', 'target_ms', 'reference_ms', 'ratio', 'paired_ratio_p95')}
    eligible = (len(runs) >= 5 and summary['calibration_ms']['range_over_median_pct'] < 3 and
                summary['ratio']['range_over_median_pct'] < 5)
    return {'schema': 1, 'advisory': True, 'accepted': False, 'eligible': eligible,
            'definition': 'pooled 19 x 16 sequential page target_p95 / reference_p95; nearest rank',
            'runs': runs, 'statistics': summary,
            'per_book': {key: {m: stats([r['books'][key][m] for r in runs])
                              for m in ('target_ms', 'reference_ms', 'ratio')}
                         for key in signatures}, 'signatures': signatures}


def capture(args):
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'raw').mkdir()
    env = dict(os.environ, E1_CPU=str(args.cpu), E1_PRIORITY='high',
               E1_WIDTH='720', E1_HEIGHT='1040', E1_MARGIN='48')
    load_mode = getattr(args, 'load_mode', None)
    if load_mode:
        env['LOAD_SANDWICH'] = '1' if load_mode == 'sandwich' else '0'
    suffix = '.exe' if os.name == 'nt' else ''
    names = ('load-probe', 'load-reference') if load_mode else ('ratio-probe', 'perf-reference')
    probe, reference = [args.build / (name + suffix) for name in names]
    worker = args.build / ('perf-reference' + suffix)
    books = read(args.manifest)['books']
    if len(books) != 19 or len({b['id'] for b in books}) != 19:
        raise ValueError('exactly 19 distinct input books required')
    cache = {}
    for line in (args.build/'CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        if '=' in line and ':' in line.split('=', 1)[0] and not line.startswith('//'):
            key, value = line.split('=', 1)
            cache[key.split(':', 1)[0]] = value
    compiler = Path(cache['CMAKE_C_COMPILER'])
    compatibility = {'compiler_sha256': sha(compiler),
        'compiler_version': subprocess.check_output([str(compiler), '--version'], text=True),
        'build': {k: v for k, v in cache.items() if k.startswith(('CMAKE_C_FLAGS',
                   'CMAKE_BUILD_TYPE', 'EXR_ENABLE_', 'EXR_BUILD_'))},
        'font_sha256': sha(args.font), 'reference_sha256': sha(reference),
        'priority': 'high',
        'reference_source_sha256': sha(ROOT/'tools/perf/reference.c'),
        'sampler_sha256': sha(__file__),
        'operation_source_sha256': sha(ROOT/'tools/reading_real_benchmark.c'),
        'document_adapter_sha256': sha(ROOT/'tools/perf/ratio_document.inc'),
        'probe_adapter_sha256': sha(ROOT/'tools/perf/CMakeLists.txt')}
    if load_mode:
        compatibility['load_sources'] = {name: sha(ROOT/'tools/perf'/name) for name in
            ('load_counters.h', 'load_reference.c', 'load_probe.cmake', 'load_capture.py')}
        compatibility['load_platform'] = {'system': platform.platform(),
            'processor': platform.processor(), 'logical_cpu': args.cpu,
            'counter': 'Windows QueryThreadCycleTime; coherent QPC/TSC; schema 2'}
    data = {'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'system': platform.platform(), 'cpu': args.cpu, 'stress': args.stress,
            'compatibility': compatibility,
            'sdk_sha256': sha(args.build/('libexreader.dll' if os.name == 'nt' else 'sdk/libexreader.so')),
            'plan': {'width': 720, 'height': 1040, 'margin': 48, 'font_size': 24,
                     'sequential_pages_per_book': 16, 'first_page_excluded': True},
            'identities': {str(p): sha(p) for p in (probe, reference, args.font,
                args.manifest, ROOT/'tools/perf/reference.c', ROOT/'tools/reading_real_benchmark.c')},
            'input_sha256': {b['id']: sha(b['path']) for b in books}, 'runs': []}
    if load_mode:
        data['plan']['load_mode'] = load_mode
        data['plan']['reference_steps'] = json.loads(execute([reference, '--identity'], env).stdout)['reference_steps']
        data['stress_workers'] = args.stress_workers
        data['worker_sha256'] = sha(worker)
    if any(data['input_sha256'][b['id']] != b['sha256'] for b in books):
        raise ValueError('corpus SHA mismatch')
    # Windows CRT argv is not UTF-8. Stage byte-identical books under ASCII names;
    # run_realbooks' ctypes path uses UTF-8, whereas the native R3 CLI does not.
    inputs = args.build/'ratio-inputs'
    inputs.mkdir(exist_ok=True)
    for book in books:
        suffix = Path(book['path']).suffix.lower()
        if suffix not in ('.epub', '.pdf', '.mobi'):
            raise ValueError('ratio plan supports EPUB, PDF and MOBI only')
        book['native_mode'] = suffix[1:]
        staged = inputs/(book['sha256']+suffix)
        if not staged.exists():
            shutil.copyfile(book['path'], staged)
        if sha(staged) != book['sha256']:
            raise ValueError('staged corpus SHA mismatch')
        book['native_path'] = str(staged)
    busy = []
    telemetry = None
    try:
        for _ in range(getattr(args, 'stress_workers', int(args.stress))):
            # One equal-priority worker on the *same* logical CPU, about half CPU entitlement.
            busy.append(subprocess.Popen([str(worker), '--busy'], env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        if busy:
            data['stress_pid'] = busy[0].pid
            data['stress_pids'] = [p.pid for p in busy]
        if load_mode:
            telemetry = subprocess.Popen(['pwsh', '-NoProfile', '-File', str(ROOT/'tools/perf/preflight.ps1'),
                '-Output', str(args.output/'during-load.json'), '-Seconds', '3', '-SkipPowerDump'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW)
        for index in range(args.runs):
            row = {'index': index + 1, 'reference_file': f'raw/reference-{index+1}.json', 'books': []}
            p = execute([reference], env)
            (args.output / row['reference_file']).write_bytes(p.stdout)
            if p.stderr:
                (args.output / f'raw/reference-{index+1}.stderr.txt').write_bytes(p.stderr)
            if p.returncode:
                raise RuntimeError('reference failed')
            row['reference_sha256'] = sha(args.output / row['reference_file'])
            data['runs'].append(row)
            write(args.output / 'capture.json', data)
            for book in books:
                path = f"raw/{index+1}-{book['id']}.json"
                p = execute([probe, book['native_mode'], book['native_path'], args.font, '-', '-'], env)
                (args.output / path).write_bytes(p.stdout)
                if p.stderr:
                    (args.output / path.replace('.json', '.stderr.txt')).write_bytes(p.stderr)
                if p.returncode:
                    raise RuntimeError(f"native probe failed: {book['id']} (raw retained)")
                row['books'].append({'id': book['id'], 'file': path, 'sha256': sha(args.output/path)})
                write(args.output / 'capture.json', data)
            print(f"run {index+1}/{args.runs}: 19 books complete", flush=True)
        if any(p.poll() is not None for p in busy):
            raise RuntimeError('stress worker exited before capture completed')
        if telemetry:
            _, stderr = telemetry.communicate(timeout=180)
            if telemetry.returncode:
                (args.output/'telemetry-error.txt').write_bytes(stderr)
                raise RuntimeError('telemetry failed')
    finally:
        if telemetry and telemetry.poll() is None:
            telemetry.terminate()
            telemetry.wait(timeout=10)
        for p in busy:
            p.terminate()
            p.wait(timeout=10)
        if busy:
            data['stress_worker_stopped'] = True
        write(args.output / 'capture.json', data)
    if load_mode:
        from load_capture import summarize as load_summarize
        report = load_summarize(args.output)
    else:
        report = summarize(args.output)
    write(args.output / 'summary.json', report)
    print(json.dumps(report['statistics'], indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('capture')
    for key in ('build', 'font', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--manifest', type=Path, default=ROOT/'tools/regress/corpus.json')
    p.add_argument('--cpu', type=int, default=3)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--stress', action='store_true')
    for command in ('summarize', 'freeze', 'check'):
        p = sub.add_parser(command)
        if command == 'check':
            p.add_argument('policy', type=Path)
        p.add_argument('directory', type=Path)
        if command != 'summarize':
            p.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'capture':
        if args.runs < 1:
            parser.error('positive run count required; qualification always requires >=5')
        capture(args)
        return 0
    report = summarize(args.directory)
    if args.command == 'summarize':
        write(args.directory/'summary.json', report)
        print(json.dumps(report['statistics'], indent=2))
        return int(not report['eligible'])
    if args.command == 'freeze':
        if args.output.exists():
            raise ValueError('refusing to overwrite policy')
        anchor = report['statistics']['ratio']['p95']
        write(args.output, {'schema': 1, 'eligible': report['eligible'], 'advisory': True,
              'accepted': False, 'baseline_capture_sha256': sha(args.directory/'capture.json'),
              'capture': read(args.directory/'capture.json'), 'anchor_ratio': anchor,
              'thresholds': {key: anchor*factor for key, factor in TIERS.items()},
              'per_book': {book: {key: row['ratio']['p95']*factor for key, factor in TIERS.items()}
                           for book, row in report['per_book'].items()},
              'signatures': report['signatures']})
        return int(not report['eligible'])
    policy = read(args.policy)
    candidate = read(args.directory/'capture.json')
    # SDK revision/DLL identity is provenance, deliberately not a compatibility key.
    a, b = policy['capture'], candidate
    compatible = all(a[k] == b[k] for k in ('plan', 'input_sha256', 'compatibility'))
    signatures_match = policy['signatures'] == report['signatures']
    ratio = report['statistics']['ratio']['p95']
    exceeded = [k for k, threshold in policy['thresholds'].items() if ratio > threshold]
    book_comparisons = [{'id': book, 'ratio': row['ratio']['p95'],
                         'thresholds': policy['per_book'][book],
                         'exceeded': [k for k, threshold in policy['per_book'][book].items()
                                      if row['ratio']['p95'] > threshold]}
                        for book, row in report['per_book'].items()]
    failed_books = [r['id'] for r in book_comparisons if any(k in r['exceeded'] for k in ('gate', 'hard'))]
    passed = (policy['eligible'] and report['eligible'] and compatible and signatures_match and
              not failed_books and not any(k in exceeded for k in ('gate', 'hard')))
    result = {'advisory': True, 'accepted': False, 'local_numeric_pass': passed,
              'compatible': compatible, 'signatures_match': signatures_match,
              'candidate_ratio': ratio, 'thresholds': policy['thresholds'], 'exceeded': exceeded,
              'book_comparisons': book_comparisons, 'failed_books': failed_books,
              'baseline_eligible': policy['eligible'], 'candidate_eligible': report['eligible']}
    write(args.output, result)
    print(json.dumps(result, indent=2))
    return int(not passed)


if __name__ == '__main__':
    sys.exit(main())
