#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run and account for bounded, reproducible SDK reliability campaigns."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

CORPUS = {
    'parser': ['pdf-blend/nonisolated.pdf', 'layout.epub', 'comic.cbz', 'deep.fb2', 'sample.txt'],
    'font': ['fonts/primary.ttf', 'fonts/collection.ttc', 'fonts/pdf-cubic.otf', 'fonts/color.ttf',
             'fonts/bitmap.ttf', 'fonts/cbdt.ttf', 'fonts/variable.ttf', 'shaping/shaping.ttf'],
    'layout': ['sample.txt', 'layout.epub', 'float-both.epub', 'table-fragments-12.epub'],
    'render': ['comic.cbz', 'pdf-color/shading-axial.pdf', 'layout.epub', 'pdf-blend/flat.pdf'],
}
SCHEMA = 2
MAX_CPU_SECONDS = (2**64-1)//10**9
SANITIZER_ENV = {'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1',
                 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                      parse_constant=lambda value: require(False, 'Non-finite JSON number'))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def hash_value(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def source_state(source):
    sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    clean = not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'])
    return sha, clean


def binary_name(target):
    return 'exreader-fuzz'+('' if target == 'parser' else '-'+target)+('.exe' if os.name == 'nt' else '')


def runtime_files(build):
    return sorted(p for p in build.iterdir() if p.is_file() and
                  (p.name.startswith(('libexreader.so', 'libexreader.dylib')) or
                   p.name in ('libexreader.dll', 'exreader.dll')))


def validate_manifest(manifest, acceptance=False):
    require(isinstance(manifest, dict) and type(manifest.get('schema')) is int and manifest['schema'] == SCHEMA,
            'Unsupported build manifest')
    require(hash_value(manifest.get('source_sha'), 40) and type(manifest.get('working_tree_clean')) is bool and
            type(manifest.get('sanitizers_requested')) is bool, 'Invalid build provenance')
    files = manifest.get('files')
    require(isinstance(files, dict) and all(isinstance(k, str) and k == Path(k).name and
            '/' not in k and '\\' not in k and hash_value(v) for k, v in files.items()), 'Invalid build files')
    require(hash_value(files.get('CMakeCache.txt')) and
            all(any(hash_value(files.get(name+suffix)) for suffix in ('', '.exe')) for name in
                ('exreader-fuzz', 'exreader-fuzz-font', 'exreader-fuzz-layout', 'exreader-fuzz-render')),
            'Incomplete driver build')
    require(any(k.startswith(('libexreader.so', 'libexreader.dylib')) or k in ('libexreader.dll', 'exreader.dll')
                for k in files), 'Missing SDK runtime')
    proofs = manifest.get('sanitizer_symbols')
    require(isinstance(proofs, dict), 'Missing instrumentation proof')
    if acceptance:
        require(manifest['working_tree_clean'] is True and manifest['sanitizers_requested'] is True,
                'Build must be clean and request sanitizers')
        require(set(proofs) == set(files)-{'CMakeCache.txt'} and
                all(isinstance(p, dict) and p == {'asan': True, 'ubsan': True} and
                    all(type(v) is bool for v in p.values()) for p in proofs.values()),
                'Missing ASan/UBSan symbols in a driver or runtime')


def seal_build(args):
    source, build = args.source.absolute(), args.build.absolute()
    path = build/'build-manifest.json'
    require(not path.exists(), 'Build manifest already exists; preserve it and choose another build')
    sha, clean = source_state(source)
    cache = build/'CMakeCache.txt'
    sanitized = bool(re.search(r'^EXR_SANITIZE:BOOL=ON$', cache.read_text(encoding='utf-8'), re.M))
    files = [build/binary_name(t) for t in CORPUS]+runtime_files(build)
    proofs = {}
    if sys.platform.startswith('linux') and sanitized:
        for file in files:
            symbols = subprocess.check_output(['nm', '-D', str(file)], text=True)
            proofs[file.name] = {'asan': '__asan_init' in symbols, 'ubsan': '__ubsan_handle_' in symbols}
    manifest = {'schema': SCHEMA, 'source_sha': sha, 'working_tree_clean': clean,
                'sanitizers_requested': sanitized, 'sanitizer_symbols': proofs,
                'files': {p.name: digest(p) for p in [cache, *files]}}
    validate_manifest(manifest, args.require_clean)
    write_json(path, manifest)
    print('Build manifest saved: '+str(path))
    return 0


def log_metrics(raw):
    text = raw.decode('utf-8', 'strict').replace('\r\n', '\n')
    counts = re.findall(r'^fuzz: (\d+) iterations over (\d+) seeds, (\d+) '
                        r'(?:reached a parsed document|completed the selected pipeline), no crash$', text, re.M)
    clocks = re.findall(r'^process_cpu_seconds=(\d+\.\d{9}) requested_cpu_seconds=(\d+)$', text, re.M)
    require(len(counts) == len(clocks) == 1, 'Missing or ambiguous driver accounting')
    iterations, seeds, completed = map(int, counts[0])
    whole, fraction = clocks[0][0].split('.')
    nanos = int(whole)*10**9+int(fraction)
    return {'iterations': iterations, 'corpus_count': seeds, 'completed_exercises': completed,
            'process_cpu_nanoseconds': nanos, 'process_cpu_seconds': nanos/10**9,
            'requested_cpu_seconds': int(clocks[0][1])}


def run(args):
    # Preserve an explicitly chosen ASCII junction for narrow Windows file APIs.
    source, build, output = args.source.absolute(), args.build.absolute(), args.output.absolute()
    require(not output.exists() or not any(output.iterdir()), 'Choose an empty evidence directory')
    sha, clean = source_state(source)
    manifest_path = build/'build-manifest.json'
    manifest = read_json(manifest_path)
    validate_manifest(manifest, args.require_clean)
    require(manifest['source_sha'] == sha, 'Build manifest belongs to another commit')
    require(not args.require_clean or clean, 'Long campaigns require a clean source checkout')
    require(all((build/k).is_file() and digest(build/k) == v for k, v in manifest['files'].items()),
            'Build files differ from sealed manifest')
    binary = build/binary_name(args.target)
    fixtures = source/'tests/fixtures'
    corpus = [fixtures/name for name in CORPUS[args.target]]
    runtimes = runtime_files(build)
    require(all(p.name in manifest['files'] for p in runtimes), 'Unsealed SDK runtime in build directory')
    inputs = [manifest_path, *(build/k for k in manifest['files']), *corpus]
    host_font = fixtures/'fonts/primary.ttf' if args.target in ('layout', 'render') else None
    if host_font:
        inputs.append(host_font)
    fingerprints = {p: digest(p) for p in inputs}
    sizes = {p: p.stat().st_size for p in corpus}
    output.mkdir(parents=True, exist_ok=True)
    (output/'build-manifest.json').write_bytes(manifest_path.read_bytes())
    command = [str(binary), '--seed', str(args.seed), '--cpu-seconds', str(args.cpu_seconds),
               '--save', str(output/'last.bin')]
    if host_font:
        command.extend(['--font', str(host_font)])
    command.extend(map(str, corpus))
    started = time.monotonic()
    timed_out = False
    try:
        environment = os.environ.copy()
        environment.update(SANITIZER_ENV)
        if sys.platform.startswith('linux'):
            environment['LD_LIBRARY_PATH'] = str(build)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment,
                                timeout=args.wall_seconds or args.cpu_seconds*4+1200)
        raw, exit_code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as error:
        raw, exit_code, timed_out = error.stdout or b'', None, True
    except OSError as error:
        raw, exit_code = str(error).encode('utf-8'), None
    wall = time.monotonic()-started
    (output/'run.log').write_bytes(raw)
    try:
        metrics = log_metrics(raw)
    except (ValueError, UnicodeError):
        metrics = dict.fromkeys(('iterations', 'corpus_count', 'completed_exercises',
                                 'process_cpu_seconds', 'process_cpu_nanoseconds', 'requested_cpu_seconds'))
    record, kind = output/'last.bin', output/'last.bin.format'
    report = {
        'schema': SCHEMA, 'target': args.target, 'seed': args.seed, 'effective_seed': args.seed | 1,
        'source_sha': sha, 'working_tree_clean': clean, 'source_unchanged': source_state(source) == (sha, clean),
        'sanitizers_requested': manifest['sanitizers_requested'], **metrics,
        'sanitizer_environment': SANITIZER_ENV,
        'requested_cpu_seconds': args.cpu_seconds, 'wall_seconds': wall,
        'exit_code': exit_code, 'timed_out': timed_out, 'binary_sha256': fingerprints[binary],
        'build_manifest_sha256': fingerprints[manifest_path],
        'runtimes': {p.name: fingerprints[p] for p in runtimes},
        'corpus': [{'file': str(p.relative_to(fixtures)).replace('\\', '/'), 'sha256': fingerprints[p],
                    'bytes': sizes[p]} for p in corpus],
        'host_font_sha256': fingerprints[host_font] if host_font else None,
        'platform': platform.platform(), 'log_sha256': digest(output/'run.log'),
        'last_input_sha256': digest(record) if record.is_file() else None,
        'last_format_sha256': digest(kind) if kind.is_file() else None,
    }
    report['inputs_unchanged'] = all(p.is_file() and digest(p) == value for p, value in fingerprints.items())
    report['passed'] = (exit_code == 0 and not timed_out and metrics['requested_cpu_seconds'] == args.cpu_seconds and
                        metrics['process_cpu_nanoseconds'] is not None and
                        metrics['process_cpu_nanoseconds'] >= args.cpu_seconds*10**9 and
                        0 < metrics['completed_exercises'] <= metrics['iterations'] and
                        metrics['corpus_count'] == len(corpus) and record.is_file() and kind.is_file() and
                        report['inputs_unchanged'] and report['source_unchanged'])
    write_json(output/'report.json', report)
    print(json.dumps({k: report[k] for k in ('target', 'iterations', 'process_cpu_seconds', 'passed')}))
    return 0 if report['passed'] else 1


def validate_report(path):
    row = read_json(path)
    require(isinstance(row, dict) and type(row.get('schema')) is int and row['schema'] == SCHEMA,
            'Unsupported campaign schema')
    require(set(('target source_sha seed effective_seed working_tree_clean source_unchanged '
                 'sanitizers_requested sanitizer_environment inputs_unchanged passed exit_code timed_out requested_cpu_seconds '
                 'process_cpu_seconds process_cpu_nanoseconds wall_seconds iterations completed_exercises '
                 'corpus_count corpus host_font_sha256 binary_sha256 runtimes platform build_manifest_sha256 '
                 'log_sha256 last_input_sha256 last_format_sha256').split()) <= row.keys(), 'Incomplete campaign report')
    target = row.get('target')
    require(isinstance(target, str) and target in CORPUS, 'Unknown campaign target')
    require(hash_value(row.get('source_sha'), 40), 'Invalid source SHA')
    for field in ('passed', 'working_tree_clean', 'source_unchanged', 'sanitizers_requested', 'inputs_unchanged'):
        require(row.get(field) is True, 'Unsuccessful or unverified campaign: '+field)
    require(row['sanitizer_environment'] == SANITIZER_ENV, 'Sanitizer failures must stop the process')
    require(type(row.get('exit_code')) is int and row['exit_code'] == 0 and row.get('timed_out') is False,
            'Campaign exited unsuccessfully')
    require(type(row.get('seed')) is int and 0 <= row['seed'] < 2**64 and
            type(row.get('effective_seed')) is int and row['effective_seed'] == row['seed'] | 1, 'Invalid seed')
    for field in ('iterations', 'completed_exercises', 'corpus_count', 'process_cpu_nanoseconds', 'requested_cpu_seconds'):
        require(type(row.get(field)) is int and row[field] > 0, 'Invalid accounting field: '+field)
    require(row['requested_cpu_seconds'] <= MAX_CPU_SECONDS and
            row['process_cpu_nanoseconds'] >= row['requested_cpu_seconds']*10**9 and
            row['completed_exercises'] <= row['iterations'], 'Invalid CPU budget or exercise count')
    require(positive(row.get('process_cpu_seconds')) and positive(row.get('wall_seconds')) and
            row['process_cpu_seconds'] == row['process_cpu_nanoseconds']/10**9, 'Invalid duration')
    require(isinstance(row.get('platform'), str) and bool(row['platform']), 'Missing platform')
    corpus = row.get('corpus')
    require(isinstance(corpus, list) and len(corpus) == row['corpus_count'] == len(CORPUS[target]) and
            all(isinstance(c, dict) and c.get('file') == name and hash_value(c.get('sha256')) and
                type(c.get('bytes')) is int and c['bytes'] > 0 for c, name in zip(corpus, CORPUS[target])),
            'Incomplete or reordered corpus')
    require(hash_value(row.get('host_font_sha256')) if target in ('layout', 'render') else
            row.get('host_font_sha256') is None, 'Invalid host font fingerprint')
    folder = path.parent
    for name, field in [('run.log', 'log_sha256'), ('last.bin', 'last_input_sha256'),
                        ('last.bin.format', 'last_format_sha256'), ('build-manifest.json', 'build_manifest_sha256')]:
        require(hash_value(row.get(field)) and (folder/name).is_file() and digest(folder/name) == row[field],
                'Missing or changed evidence file: '+str(folder/name))
    metrics = log_metrics((folder/'run.log').read_bytes())
    require(all(row.get(k) == v for k, v in metrics.items()), 'Report disagrees with driver accounting')
    label = (folder/'last.bin.format').read_text(encoding='ascii')
    formats = ('txt', 'html', 'fb2', 'epub', 'docx', 'rtf', 'mobi', 'pdf', 'cbz')
    labels = ('font',) if target == 'font' else formats if target == 'parser' else tuple(target+':'+f for f in formats)
    require(label in labels, 'Evidence belongs to another pipeline')
    manifest = read_json(folder/'build-manifest.json')
    validate_manifest(manifest, acceptance=True)
    require(manifest['source_sha'] == row['source_sha'], 'Report and build use different commits')
    # Acceptance currently uses the sealed Linux ASan/UBSan build.
    name = 'exreader-fuzz'+('' if target == 'parser' else '-'+target)
    require(hash_value(row.get('binary_sha256')) and manifest['files'].get(name) == row['binary_sha256'],
            'Driver fingerprint disagrees with build')
    runtimes = {k: v for k, v in manifest['files'].items() if k.startswith('libexreader.so')}
    require(bool(runtimes) and row.get('runtimes') == runtimes, 'Runtime fingerprint disagrees with build')
    return row


def summarize(args):
    require(positive(args.minimum_cpu_hours), 'Minimum CPU hours must be positive')
    require(type(args.expected_shards) is int and args.expected_shards > 0, 'Expected shards must be positive')
    require(not args.output.exists(), 'Summary already exists; choose a fresh output path')
    paths = sorted(args.reports.rglob('report.json'))
    require(bool(paths), 'No campaign reports found')
    reports = [validate_report(p) for p in paths]
    require(len({r['source_sha'] for r in reports}) == 1, 'Campaign commits differ')
    require(not args.expected_source_sha or all(r['source_sha'] == args.expected_source_sha for r in reports),
            'Campaign does not match the expected commit')
    require(len({r['build_manifest_sha256'] for r in reports}) == 1, 'Campaign build manifests differ')
    require(all(r['build_manifest_sha256'] == digest(args.build_manifest) for r in reports),
            'Reports differ from the independently downloaded build manifest')
    totals = {}
    for target in CORPUS:
        rows = [r for r in reports if r['target'] == target]
        require(len(rows) == args.expected_shards, target+': missing or unexpected shards')
        require(len({r['effective_seed'] for r in rows}) == len(rows), target+': repeated effective seed')
        if args.first_seed is not None:
            require({r['seed'] for r in rows} == {args.first_seed+2*i for i in range(args.expected_shards)},
                    target+': unexpected seed schedule')
        fingerprints = {json.dumps([r['corpus'], r['host_font_sha256']], sort_keys=True) for r in rows}
        require(len(fingerprints) == 1, target+': corpus changed across shards')
        nanos = sum(r['process_cpu_nanoseconds'] for r in rows)
        require(nanos >= math.ceil(args.minimum_cpu_hours*3600*10**9), target+': insufficient process CPU time')
        totals[target] = {'shards': len(rows), 'process_cpu_nanoseconds': nanos,
                          'process_cpu_seconds': nanos/10**9, 'iterations': sum(r['iterations'] for r in rows)}
    summary = {'schema': SCHEMA, 'passed': True, 'source_sha': reports[0]['source_sha'],
               'build_manifest_sha256': reports[0]['build_manifest_sha256'],
               'minimum_cpu_hours': args.minimum_cpu_hours, 'targets': totals,
               'reports': [{'file': str(p.relative_to(args.reports)), 'sha256': digest(p)} for p in paths]}
    write_json(args.output, summary)
    print('All campaign accounting checks passed; summary saved: '+str(args.output))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    seal = commands.add_parser('seal-build')
    seal.add_argument('--source', type=Path, default=Path('.'))
    seal.add_argument('--build', type=Path, required=True)
    seal.add_argument('--require-clean', action='store_true')
    campaign = commands.add_parser('run')
    campaign.add_argument('--source', type=Path, default=Path('.'))
    campaign.add_argument('--build', type=Path, required=True)
    campaign.add_argument('--output', type=Path, required=True)
    campaign.add_argument('--target', choices=CORPUS, required=True)
    campaign.add_argument('--seed', type=int, required=True)
    campaign.add_argument('--cpu-seconds', type=int, required=True)
    campaign.add_argument('--wall-seconds', type=int)
    campaign.add_argument('--require-clean', action='store_true')
    summary = commands.add_parser('summarize')
    summary.add_argument('--reports', type=Path, required=True)
    summary.add_argument('--output', type=Path, required=True)
    summary.add_argument('--minimum-cpu-hours', type=float, default=24)
    summary.add_argument('--expected-shards', type=int, default=24)
    summary.add_argument('--expected-source-sha')
    summary.add_argument('--build-manifest', type=Path, required=True)
    summary.add_argument('--first-seed', type=int)
    args = parser.parse_args()
    if args.command == 'run' and (not 0 < args.cpu_seconds <= MAX_CPU_SECONDS or not 0 <= args.seed < 2**64 or
                                 (args.wall_seconds is not None and args.wall_seconds <= 0)):
        parser.error('Invalid duration or seed')
    if args.command == 'summarize' and (not positive(args.minimum_cpu_hours) or args.expected_shards <= 0 or
                                      (args.first_seed is not None and
                                       (args.first_seed < 0 or args.first_seed+2*(args.expected_shards-1) >= 2**64))):
        parser.error('Invalid summary budget or shard schedule')
    try:
        return {'run': run, 'summarize': summarize, 'seal-build': seal_build}[args.command](args)
    except (ValueError, OSError, subprocess.SubprocessError, OverflowError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    sys.exit(main())
