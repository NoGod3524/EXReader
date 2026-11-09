"""Collect 3 fresh processes x 16 sequential turns per book; retain every sample.

No retries, trimming, calibration or candidate-dependent thresholds. Book bytes
are only staged under the ignored build directory, never uploaded as evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PLAN = {'processes': 3, 'turns': 16, 'width': 720, 'height': 1040, 'margin': 48,
        'font_size': 24, 'first_excluded': True, 'statistic': 'nearest-rank p95 of 48 turns per book'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def p95(values):
    if not values or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('positive finite samples required')
    return sorted(values)[math.ceil(.95 * len(values)) - 1]


def command(args):
    return subprocess.check_output(list(map(str, args)), text=True, encoding='utf-8', cwd=ROOT).strip()


def cache(path):
    return {line.split(':', 1)[0]: line.split('=', 1)[1]
            for line in (Path(path) / 'CMakeCache.txt').read_text(encoding='utf-8').splitlines()
            if '=' in line and ':' in line.split('=', 1)[0] and not line.startswith('//')}


def environment(args):
    c = cache(args.build)
    sdk = cache(args.sdk_build or args.build / 'sdk')
    compiler = c['CMAKE_C_COMPILER']
    flags = lambda data: {k: v for k, v in data.items() if k.startswith(
        ('CMAKE_C_FLAGS', 'CMAKE_BUILD_TYPE', 'EXR_ENABLE_', 'EXR_BUILD_'))}
    if c['CMAKE_BUILD_TYPE'] != 'Release' or sdk['CMAKE_BUILD_TYPE'] != 'Release':
        raise ValueError('Release probe and SDK required')
    if os.name == 'nt':
        host = json.loads(command(['powershell', '-NoProfile', '-Command',
            '$c=Get-CimInstance Win32_Processor | Select-Object -First 1;'
            '$s=Get-CimInstance Win32_ComputerSystem;'
            '@{cpu=$c.Name;logical_cores=$s.NumberOfLogicalProcessors;ram_bytes=$s.TotalPhysicalMemory} | ConvertTo-Json -Compress']))
        counter = 'Windows/QueryThreadCycleTime'
    else:
        info = Path('/proc/cpuinfo').read_text()
        host = {'cpu': next(line.split(':', 1)[1].strip() for line in info.splitlines()
                            if line.startswith('model name')),
                'logical_cores': os.cpu_count(),
                'ram_bytes': os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')}
        counter = 'Linux/perf_event_open/PERF_COUNT_HW_CPU_CYCLES/user/pinned/no-multiplex'
    host.update(system=platform.system(), machine=platform.machine(), os=platform.platform(),
                runner_label=os.getenv('PERF_RUNNER_LABEL', 'local'),
                image_os=os.getenv('ImageOS'), image_version=os.getenv('ImageVersion'), cpu_index=args.cpu)
    compiler_info = {'path': compiler, 'version': command([compiler, '--version']), 'sha256': sha(compiler),
                     'flags': flags(c), 'sdk_flags': flags(sdk)}
    harness = {p: sha(ROOT / 'tools/perf' / p) for p in
               ('sample.py', 'gate_probe.cmake', 'gate_counters.h', 'CMakeLists.txt',
                'e1_platform.h', 'ratio_document.inc')}
    harness['R3'] = sha(ROOT / 'tools/reading_real_benchmark.c')
    # Executed cycles remain microarchitecture-specific. A changed environment is
    # an invalid comparison (exit 2), never an automatic pass or a rebaseline.
    compatibility = {'host': {k: v for k, v in host.items() if k != 'ram_bytes'},
                     'compiler': {k: v for k, v in compiler_info.items() if k != 'path'},
                     'counter': counter, 'harness': harness, 'font_sha256': sha(args.font), 'plan': PLAN}
    return {'host': host, 'compiler': compiler_info, 'counter': counter}, compatibility


def audit(folder):
    folder = Path(folder)
    data = read(folder / 'capture.json')
    if data['schema'] != 1 or data['plan'] != PLAN or data.get('complete') is not True:
        raise ValueError('incomplete capture or changed plan')
    expected = data['input_sha256']
    if len(expected) != 19 or [r['index'] for r in data['runs']] != [1, 2, 3]:
        raise ValueError('exactly 19 books and 3 processes per book required')
    signatures, values = {}, {b: {'cycles': [], 'wall': [], 'injected': [], 'original': []} for b in expected}
    from ratio_capture import signature
    for run in data['runs']:
        if len(run['books']) != 19 or {b['id'] for b in run['books']} != set(expected):
            raise ValueError('book coverage differs')
        for book in run['books']:
            path = (folder / book['file']).resolve()
            if not path.is_relative_to(folder.resolve()) or sha(path) != book['sha256']:
                raise ValueError('raw path or digest mismatch')
            raw = read(path)
            if raw['success'] is not True or raw['status'] != 0 or len(raw['samples']) != 17:
                raise ValueError('native probe incomplete')
            if [s['phase'] for s in raw['samples']] != ['first'] + ['sequential'] * 16:
                raise ValueError('operation plan differs')
            sig = signature(raw)
            if signatures.setdefault(book['id'], sig) != sig:
                raise ValueError('pixel/text/position signature differs across processes')
            for s in raw['samples'][1:]:
                cycles, added = s['thread_cycles'], s['injected_cycles']
                if type(cycles) is not int or cycles <= 0 or type(added) is not int or not 0 <= added < cycles:
                    raise ValueError('invalid native cycles')
                if not math.isclose(s['cycle_wall_ms'], s['total_ms'], abs_tol=3e-5):
                    raise ValueError('cycle/wall windows differ (including transitions)')
                entry = values[book['id']]
                for key, value in [('cycles', cycles), ('wall', s['total_ms']),
                                   ('injected', added), ('original', cycles - added)]:
                    entry[key].append(value)
    books = {b: {'thread_cycles_p95': p95(v['cycles']), 'wall_ms_p95': p95(v['wall']),
                 'samples': len(v['cycles']), 'injected_fraction': sum(v['injected']) / sum(v['original'])}
             for b, v in values.items()}
    return data, books, signatures


def collect(args):
    args.build, args.font = args.build.resolve(), args.font.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    books = read(args.manifest)['books']
    expected = {b['id']: b['sha256'] for b in read(ROOT / 'tools/regress/corpus.json')['books']}
    if len(books) != 19 or {b['id']: b['sha256'] for b in books} != expected:
        raise ValueError('manifest must contain the exact frozen 19 books')
    if args.fault_book and args.fault_book not in expected:
        raise ValueError('unknown fault book')
    env, compatible = environment(args)
    suffix = '.exe' if os.name == 'nt' else ''
    probe = args.build / ('gate-probe' + suffix)
    dll = args.sdk or args.build / ('libexreader.dll' if os.name == 'nt' else 'sdk/libexreader.so')
    data = {'schema': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'complete': False,
            'environment': env, 'compatibility': compatible, 'plan': PLAN, 'input_sha256': expected,
            'source_revision': command(['git', 'rev-parse', 'HEAD']),
            'source_trees': {p: command(['git', 'rev-parse', 'HEAD:' + p]) for p in ('src', 'include', 'cmake', 'CMakeLists.txt')},
            'probe_sha256': sha(probe), 'sdk_sha256': sha(dll), 'fault_book': args.fault_book,
            'github': {k: os.getenv(k) for k in ('GITHUB_ACTIONS', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
                       'GITHUB_SHA', 'GITHUB_REPOSITORY')}, 'runs': []}
    write(args.output / 'capture.json', data)
    staging = args.build / 'gate-inputs'
    staging.mkdir(exist_ok=True)
    for b in books:
        original = Path(b['path'])
        if not original.is_absolute():
            original = args.manifest.parent / original
        if sha(original) != b['sha256']:
            raise ValueError('input digest mismatch: ' + b['id'])
        target = staging / (b['sha256'] + original.suffix.lower())
        if not target.exists():
            shutil.copyfile(original, target)
        if sha(target) != b['sha256']:
            raise ValueError('staged input digest mismatch')
        b['staged'] = target
    child_env = dict(os.environ, E1_CPU=str(args.cpu), E1_PRIORITY='high', E1_WIDTH='720', E1_HEIGHT='1040', E1_MARGIN='48')
    for index in range(1, 4):
        run = {'index': index, 'books': []}
        data['runs'].append(run)
        for b in books:
            child_env['PERF_GATE_FAULT_PERCENT'] = '25' if b['id'] == args.fault_book else '0'
            cmd = [str(probe), b['staged'].suffix[1:], str(b['staged']), str(args.font), '-', '-']
            if os.name != 'nt':
                cmd = ['taskset', '-c', str(args.cpu), *cmd]
            result = subprocess.run(cmd, env=child_env, capture_output=True, timeout=180,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            name = f'raw/{index}-{b["id"]}.json'
            path = args.output / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(result.stdout)
            if result.stderr:
                path.with_suffix('.stderr.txt').write_bytes(result.stderr)
            if result.returncode:
                raise ValueError(f'native probe failed ({result.returncode}): {b["id"]}; raw retained')
            run['books'].append({'id': b['id'], 'file': name, 'sha256': sha(path)})
            write(args.output / 'capture.json', data)
        print(f'process {index}/3: 19 books complete', flush=True)
    data['complete'] = True
    write(args.output / 'capture.json', data)
    _, summary, _ = audit(args.output)
    write(args.output / 'summary.json', summary)
    return args.output


def arguments(parser):
    for k in ('build', 'font', 'output'):
        parser.add_argument('--' + k, type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'tools/regress/corpus.json')
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--sdk-build', type=Path)
    parser.add_argument('--cpu', type=int, default=3 if os.name == 'nt' else 0)
    parser.add_argument('--fault-book')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    collect(parser.parse_args())
