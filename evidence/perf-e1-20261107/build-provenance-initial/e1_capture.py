#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local E1 evidence, using the existing R3 native probe; never grants E3 acceptance.

Build: cmake -S tools/perf -B BUILD -G Ninja -DCMAKE_BUILD_TYPE=Release
       cmake --build BUILD --target e1-probe --parallel 4
Capture: python tools/perf/e1_capture.py --binary BUILD/e1-probe.exe \
         --build BUILD --font FONT --output NEW_DIRECTORY
Verify: repeat with --budgets BASELINE/proposed-budgets.json --output NEW_DIRECTORY
"""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from run_benchmarks import make_epub

CONFIGS = {'default-release': (720, 1040, 48), '1280x800': (1280, 800, 48),
           '2560x1440': (2560, 1440, 48)}
METRICS = ('open_ms', 'first_visible_ms', 'first_render_ms', 'turn_p50_ms',
           'turn_p95_ms', 'turn_max_ms', 'random_p95_ms', 'peak_rss_bytes')


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def write(path, value):
    Path(path).write_bytes(encoded(value))


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                          timeout=kwargs.pop('timeout', 60), **kwargs)


def output(command):
    result = run(command)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode('utf-8-sig', errors='replace').strip()


def powershell(script):
    return json.loads(output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                              '[Console]::OutputEncoding=[Text.UTF8Encoding]::new();' + script]))


def percentile(values, percent):
    if not values or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                             and math.isfinite(v) and v >= 0 for v in values):
        raise ValueError('Missing, negative or non-finite samples')
    return sorted(values)[math.ceil(len(values) * percent / 100) - 1]


def stats(values):
    median = percentile(values, 50)
    return {'n': len(values), 'p50': median, 'p95': percentile(values, 95), 'max': max(values),
            'min': min(values), 'cv_pct': statistics.pstdev(values) / statistics.mean(values) * 100
            if statistics.mean(values) else 0,
            'range_over_median_pct': (max(values) - min(values)) / median * 100
            if median else (0 if max(values) == 0 else None)}


def load_snapshot():
    if os.name != 'nt':
        return {'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else 'unknown'}
    def times():
        idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError('GetSystemTimes failed')
        return idle.value, kernel.value + user.value
    before = times()
    time.sleep(0.5)
    after = times()
    class PowerStatus(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ubyte) for name in ('ac', 'flags', 'percent', 'saver')] + [
            ('remaining', ctypes.c_ulong), ('full', ctypes.c_ulong)]
    power = PowerStatus()
    power_ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))
    class Frequency(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulong) for name in
                    ('number', 'max_mhz', 'current_mhz', 'limit_mhz', 'max_idle', 'current_idle')]
    frequencies = (Frequency * (os.cpu_count() or 1))()
    frequency_ok = ctypes.windll.powrprof.CallNtPowerInformation(11, None, 0, frequencies, ctypes.sizeof(frequencies)) == 0
    return {'utc': utc(), 'sample_seconds': 0.5,
            'ac_line_status': power.ac if power_ok else 'unknown',
            'battery_percent': power.percent if power_ok else 'unknown',
            'battery_saver': power.saver if power_ok else 'unknown',
            'reported_frequency_mhz': [{'cpu': f.number, 'current': f.current_mhz, 'max': f.max_mhz, 'limit': f.limit_mhz}
                                       for f in frequencies] if frequency_ok else 'unknown',
            'cpu_busy_pct': 100 * (1 - (after[0] - before[0]) / (after[1] - before[1]))
            if after[1] > before[1] else None}


def environment(args):
    cache = {}
    for line in (args.build / 'CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        if '=' in line and ':' in line.split('=', 1)[0] and not line.startswith('//'):
            key, value = line.split('=', 1)
            cache[key.split(':', 1)[0]] = value
    compiler = Path(cache['CMAKE_C_COMPILER'])
    env = {'schema': 1, 'advisory': True, 'accepted': False, 'captured_at': utc(),
           'runner_label': os.environ.get('PERF_RUNNER_LABEL', 'local-windows-e1'),
           'os': {'system': platform.system(), 'version': platform.version(),
                  'kernel': platform.release(), 'architecture': platform.machine()},
           'compiler': {'path': str(compiler), 'sha256': sha(compiler),
                        'version': output([compiler, '--version'])},
           'build': {key: value for key, value in cache.items() if key.startswith(
               ('CMAKE_C_FLAGS', 'CMAKE_BUILD_TYPE', 'CMAKE_GENERATOR', 'EXR_ENABLE_',
                'EXR_BUILD_', 'CMAKE_EXE_LINKER_FLAGS'))},
           'source_sha': output(['git', 'rev-parse', 'HEAD']),
           'source_tree': output(['git', 'rev-parse', 'HEAD^{tree}']),
           'worktree_status': output(['git', 'status', '--short']),
           'run': {'id': args.output.name, 'attempt': 1, 'command': [sys.executable, *sys.argv],
                   'ci': False},
           'affinity': {'logical_cpu': args.cpu, 'applied_in_native_before_font_open': os.name == 'nt'},
           'load_at_capture': load_snapshot()}
    if os.name == 'nt':
        details = powershell("$p=@(Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,ProcessorId,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,CurrentClockSpeed);"
                             "$c=Get-CimInstance Win32_ComputerSystem; $o=Get-CimInstance Win32_OperatingSystem;"
                             "$b=Get-CimInstance Win32_BIOS; $battery=@(Get-CimInstance Win32_Battery | Select-Object BatteryStatus,EstimatedChargeRemaining);"
                             "@{cpu=$p;system=@{manufacturer=$c.Manufacturer;model=$c.Model;hypervisor_present=$c.HypervisorPresent;memory_bytes=$c.TotalPhysicalMemory};"
                             "os=@{caption=$o.Caption;build=$o.BuildNumber;free_memory_kib=$o.FreePhysicalMemory};"
                             "bios=@{manufacturer=$b.Manufacturer;version=$b.SMBIOSBIOSVersion};battery=$battery} | ConvertTo-Json -Depth 6")
        env.update(details)
        env['os'].update(system=platform.system(), version=platform.version(), kernel=platform.release(), architecture=platform.machine())
        env['power'] = {'active_scheme': output(['powercfg', '/getactivescheme']),
                        'processor_policy': output(['powercfg', '/query', 'SCHEME_CURRENT', 'SUB_PROCESSOR'])}
        model = (details['system']['manufacturer'] + ' ' + details['system']['model']).lower()
        vm = any(marker in model for marker in ('virtual', 'vmware', 'kvm', 'qemu', 'xen', 'parallels'))
        env['virtualization'] = {'vm_detected_by_smbios': vm,
            'hypervisor_present': details['system']['hypervisor_present'],
            'guest_status': 'detected' if vm else 'no SMBIOS guest signature; hypervisor presence alone is not proof of a VM',
            'method': 'Win32_ComputerSystem Manufacturer/Model and HypervisorPresent'}
    else:
        env.update(cpu='unknown', system={'memory_bytes': 'unknown'}, power='unknown', virtualization='unknown')
    identities = [args.binary, args.font, args.build / 'e1_probe.c', args.build / 'CMakeCache.txt',
                  args.build / 'compile_commands.json', Path(__file__),
                  ROOT / 'tools/perf/CMakeLists.txt', ROOT / 'tools/perf/e1_platform.h',
                  ROOT / 'tools/reading_real_benchmark.c', ROOT / 'tools/run_benchmarks.py',
                  ROOT / 'docs/validation/sdk-baseline.json', ROOT / 'docs/validation/PERF-BASELINE-POLICY.md']
    env['identities'] = {str(path.resolve()): sha(path) for path in identities}
    env['runtime_dlls'] = {str(path): sha(path) for path in sorted(args.binary.parent.glob('*.dll'))}
    if os.name == 'nt':
        imports = re.findall(r'DLL Name: (\S+)', output([compiler.parent / 'objdump.exe', '-p', args.binary]))
        for name in imports:
            candidates = [args.binary.parent / name, Path(os.environ['SystemRoot']) / 'System32' / name,
                          *(Path(folder) / name for folder in os.environ.get('PATH', '').split(os.pathsep))]
            resolved = next((p for p in candidates if p.is_file()), None)
            if resolved is None:
                found = shutil.which(name)
                resolved = Path(found) if found else None
            env['runtime_dlls'][name] = {'path': str(resolved) if resolved else 'unknown',
                                         'sha256': sha(resolved) if resolved else 'unknown'}
            if resolved:
                env['identities'][str(resolved.resolve())] = sha(resolved)
    env['dependencies'] = {}
    source_dirs = {key.removeprefix('FETCHCONTENT_SOURCE_DIR_').lower(): Path(value)
                   for key, value in cache.items() if key.startswith('FETCHCONTENT_SOURCE_DIR_') and value}
    source_dirs.update({p.name.removesuffix('-src'): p for p in (args.build / '_deps').glob('*-src') if p.is_dir()})
    for name, directory in sorted(source_dirs.items()):
        hashes = {str(p.relative_to(directory)).replace('\\', '/'): sha(p)
                  for p in sorted(directory.rglob('*')) if p.is_file() and '.git' not in p.parts}
        env['dependencies'][name] = {'path': str(directory), 'files': len(hashes),
                                      'tree_sha256': hashlib.sha256(encoded(hashes)).hexdigest()}
    env['protected_trees'] = {name: output(['git', 'rev-parse', f'HEAD:{name}']) for name in
                              ('src', 'include', 'cmake', 'CMakeLists.txt', 'tests/fixtures', 'bindings')}
    # Environmental identity excludes dynamic load, paths and the source revision.
    comparable = {key: env[key] for key in ('cpu', 'os', 'compiler', 'build', 'power', 'virtualization', 'affinity')}
    comparable['os'] = {key: value for key, value in comparable['os'].items() if key != 'free_memory_kib'}
    comparable['cpu'] = [{key: value for key, value in cpu.items() if key != 'CurrentClockSpeed'} for cpu in env['cpu']] if isinstance(env['cpu'], list) else env['cpu']
    comparable['compiler'] = {key: value for key, value in env['compiler'].items() if key != 'path'}
    comparable['memory_bytes'] = env['system']['memory_bytes']
    comparable['dependencies'] = {name: value['tree_sha256'] for name, value in env['dependencies'].items()}
    comparable['runtime'] = {Path(name).name: value['sha256'] if isinstance(value, dict) else value
                             for name, value in env['runtime_dlls'].items()}
    env['comparison_key'] = hashlib.sha256(encoded(comparable)).hexdigest()
    env['comparability_rules'] = ['Exact comparison_key, binary/font/input SHA and workload required for local enforcement',
        'Different CPU, OS, compiler, flags, power policy or affinity requires a separate budget',
        'Same-environment historical p95 >1.5x requires manual review; cross-environment automatic gate OFF',
        'Unknown fields cannot establish compatibility; compare per-run load and battery/clock evidence too']
    return env


def metrics(raw):
    if raw.get('success') is not True or raw.get('stage') != 'complete' or raw.get('status') != 0:
        raise ValueError('Native probe did not complete')
    seq = [s['total_ms'] for s in raw['samples'] if s['phase'] == 'sequential']
    random = [s['total_ms'] for s in raw['samples'] if s['phase'] == 'random']
    if len(seq) != 32 or len(random) != 16 or len(raw['samples']) != 49:
        raise ValueError('Expected first + 32 sequential + 16 random operations')
    result = {key: raw[key] for key in ('open_ms', 'first_visible_ms', 'peak_rss_bytes')}
    result.update(first_render_ms=raw['samples'][0]['render_ms'], turn_p50_ms=percentile(seq, 50),
                  turn_p95_ms=percentile(seq, 95), turn_max_ms=max(seq), random_p95_ms=percentile(random, 95))
    for value in result.values():
        percentile([value], 50)
    if raw['peak_rss_bytes'] <= 0:
        raise ValueError('Missing memory high-water mark')
    return result


def signatures(raw):
    return [{key: s[key] for key in ('phase', 'part', 'page', 'width', 'height', 'pixel_hash',
                                      'text_hash', 'position_hash')} for s in raw['samples']]


def summarize(trials):
    if not trials or any('metrics' not in trial for trial in trials):
        return {'stable': False, 'metrics': {}, 'error': 'Missing or failed trial'}
    result = {key: stats([trial['metrics'][key] for trial in trials]) for key in METRICS}
    return {'stable': all(s['range_over_median_pct'] is not None and s['range_over_median_pct'] < 10
                           for s in result.values()), 'metrics': result}


def derive_budget(env, report, sample_hash):
    groups = report['groups']
    return {'schema': 1, 'advisory': True, 'accepted': False, 'status': 'proposal_only',
            'comparison_key': env['comparison_key'], 'source_sha': env['source_sha'],
            'binary_sha256': env['identities'][str(Path(report['binary']).resolve())],
            'font_sha256': report['font_sha256'], 'input_sha256': report['input_sha256'],
            'samples_sha256': sample_hash, 'exporter_sha256': sha(__file__),
            'method': 'nearest-rank p95 across final predeclared complete batch; latency ceil(p95*1.25*1000)/1000 ms; RSS ceil(p95*1.05)+1048576 bytes',
            'eligible': report['measurement_valid'] and all(g['final']['stable'] for g in groups.values()),
            'limits': {name: {key: math.ceil(s['p95'] * 1.05) + 1048576 if key.endswith('_bytes')
                             else math.ceil(s['p95'] * 1.25 * 1000) / 1000
                             for key, s in group['final']['metrics'].items()}
                       for name, group in groups.items()}}


def markdown(env, report, budgets):
    lines = ['# E1 local capture', '', f"Source: `{env['source_sha']}`; comparison key: `{env['comparison_key']}`.",
             '', 'advisory: true; accepted: false. Local strict numeric verification does not restore the required check.',
             '', 'Nearest-rank percentiles. Dispersion = 100*(max-min)/p50 across fresh processes; CV uses population SD.',
             'First visible = font open + publication/pager open + first layout/render. First render excludes layout.',
             'R3 native plan: first RGBA frame, 32 sequential pages, 16 fixed-seed random requests; hashes outside timed rendering.',
             'OS cache is primed before each process; no discarded warmup. Peak RSS includes signature hashing.',
             '', '| Configuration / batch | Metric | p50 | p95 | max | range/p50 % | CV % |',
             '|---|---|---:|---:|---:|---:|---:|']
    for name, group in report['groups'].items():
        for index, batch in enumerate(group['batches'], 1):
            for key, s in batch['summary']['metrics'].items():
                lines.append(f"| {name} / {index} | {key} | {s['p50']:.6f} | {s['p95']:.6f} | {s['max']:.6f} | {s['range_over_median_pct']:.3f} | {s['cv_pct']:.3f} |")
    lines += ['', '## Every retained process', '', '| Configuration / batch / run | open ms | visible ms | first render ms | turn p50 ms | turn p95 ms | peak bytes |', '|---|---:|---:|---:|---:|---:|---:|']
    for name, group in report['groups'].items():
        for b, batch in enumerate(group['batches'], 1):
            for r, trial in enumerate(batch['trials'], 1):
                m = trial.get('metrics', {})
                values = ' | '.join(f'{m[k]:.6f}' if k in m else 'FAILED' for k in
                                    ('open_ms', 'first_visible_ms', 'first_render_ms', 'turn_p50_ms', 'turn_p95_ms', 'peak_rss_bytes'))
                lines.append(f'| {name}/{b}/{r} | {values} |')
    lines += ['', '## Pairwise differences', '', 'Median difference is resolved only if it exceeds both complete-batch observed ranges.',
              '', '| Pair | Metric | median difference % | exceeds both noise ranges |', '|---|---|---:|---|']
    for item in report['comparisons']:
        lines.append(f"| {item['a']} vs {item['b']} | {item['metric']} | {item['difference_pct']:.3f} | {item['exceeds_both_ranges']} |")
    lines += ['', f"Measurement valid: {report['measurement_valid']}; stable budget eligible: {budgets['eligible']}.",
              '', 'Budget limits are script-derived in proposed-budgets.json; all earlier noisy batches remain in samples.json and raw/.']
    if 'verification' in report:
        lines += ['', 'Strict local numeric verification: `' + json.dumps(report['verification']) + '`.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'build', 'font', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--book', type=Path, help='Default: fixed 1 MiB, four-chapter synthetic EPUB')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--max-batches', type=int, default=3)
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--cpu', type=int, default=0)
    parser.add_argument('--budgets', type=Path)
    args = parser.parse_args()
    if args.runs < 3 or args.max_batches < 1 or not math.isfinite(args.interval) or args.interval < 1 or not 0 <= args.cpu < (os.cpu_count() or 1):
        parser.error('Require runs>=3, max-batches>=1, interval>=1s, and an available logical CPU')
    if args.output.exists():
        parser.error('Output directory must not exist; earlier evidence is never overwritten')
    args.binary, args.build, args.font, args.output = (p.resolve() for p in (args.binary, args.build, args.font, args.output))
    args.output.mkdir(parents=True)
    (args.output / 'raw').mkdir()
    env = environment(args)
    write(args.output / 'env.json', env)
    if args.book:
        book = args.book.resolve()
    else:
        book = args.output / 'fixed.epub'
        make_epub(book, 4, 1024 * 1024)
    report = {'schema': 1, 'advisory': True, 'accepted': False, 'started_at': utc(),
              'binary': str(args.binary), 'font_sha256': sha(args.font), 'input_sha256': sha(book),
              'workload': {'configurations': CONFIGS, 'sequential': 32, 'random': 16, 'seed': 20261023,
                           'runs_per_batch': args.runs, 'max_batches': args.max_batches,
                           'interval_seconds': args.interval, 'input': str(book),
                           'disk_cache': 'input/font primed; OS cache not flushed', 'warmup_runs': 0},
              'measurement_valid': True, 'groups': {}, 'comparisons': []}
    frozen = json.loads(args.budgets.read_text(encoding='utf-8')) if args.budgets else None
    if frozen:
        mismatches = [key for key in ('comparison_key', 'source_sha') if env[key] != frozen[key]]
        for key, value in (('binary_sha256', sha(args.binary)), ('font_sha256', sha(args.font)), ('input_sha256', sha(book))):
            if value != frozen[key]:
                mismatches.append(key)
        if mismatches or not frozen['eligible']:
            raise ValueError(f'Frozen budget incompatible or ineligible: {mismatches}')
    expected_signatures = {}
    for name, (width, height, margin) in CONFIGS.items():
        group = {'batches': []}
        report['groups'][name] = group
        for batch_index in range(1, args.max_batches + 1):
            trials = []
            for index in range(1, args.runs + 1):
                time.sleep(args.interval)
                # Prime outside the probe's timings, then let each process start with empty SDK caches.
                book.read_bytes(); args.font.read_bytes()
                trial = {'started_at': utc(), 'load_before': load_snapshot()}
                prefix = f'{name}-b{batch_index}-r{index}'
                command = [str(args.binary), 'epub', str(book), str(args.font), '-', '-']
                trial['command'] = command
                process_env = dict(os.environ, E1_WIDTH=str(width), E1_HEIGHT=str(height), E1_MARGIN=str(margin),
                                   E1_CPU=str(args.cpu), OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
                stdout, stderr = args.output / 'raw' / (prefix + '.json'), args.output / 'raw' / (prefix + '.stderr.txt')
                try:
                    result = run(command, timeout=300, env=process_env)
                    stdout.write_bytes(result.stdout); stderr.write_bytes(result.stderr)
                    trial['exit_code'] = result.returncode
                    if result.returncode:
                        raise ValueError('Nonzero native exit')
                    raw = json.loads(result.stdout)
                    trial['metrics'] = metrics(raw)
                    if any(s['width'] != width or s['height'] != height for s in raw['samples']):
                        raise ValueError('Viewport mismatch')
                    sig = signatures(raw)
                    if name in expected_signatures and sig != expected_signatures[name]:
                        raise ValueError('RGBA/text/position signature mismatch')
                    expected_signatures[name] = sig
                except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
                    trial.pop('metrics', None)
                    trial['error'] = str(error)
                    report['measurement_valid'] = False
                    if not stdout.exists():
                        stdout.write_bytes(getattr(error, 'stdout', None) or b'')
                        stderr.write_bytes(getattr(error, 'stderr', None) or str(error).encode())
                trial.update(stdout=str(stdout.relative_to(args.output)), stdout_sha256=sha(stdout),
                             stderr=str(stderr.relative_to(args.output)), stderr_sha256=sha(stderr),
                             finished_at=utc(), load_after=load_snapshot())
                trials.append(trial)
                print(f'{prefix}: {trial.get("metrics", trial.get("error"))}', flush=True)
            summary = summarize(trials)
            group['batches'].append({'trials': trials, 'summary': summary})
            group['final'] = summary
            group['all_retained'] = summarize([t for batch in group['batches'] for t in batch['trials']])
            write(args.output / 'samples.json', report)
            if summary['stable']:
                break
            print(f'{name} batch {batch_index}: dispersion >=10% or invalid; retaining and repeating full batch', flush=True)
    names = list(CONFIGS)
    for index, a in enumerate(names):
        for b in names[index + 1:]:
            for key in METRICS:
                sa, sb = report['groups'][a]['final']['metrics'].get(key), report['groups'][b]['final']['metrics'].get(key)
                if sa and sb:
                    difference = abs(sa['p50'] - sb['p50'])
                    report['comparisons'].append({'a': a, 'b': b, 'metric': key,
                        'difference_pct': difference / sa['p50'] * 100 if sa['p50'] else 0,
                        'exceeds_both_ranges': difference > max(sa['max'] - sa['min'], sb['max'] - sb['min'])})
    changed = [path for path, digest in env['identities'].items() if sha(path) != digest]
    if changed or output(['git', 'rev-parse', 'HEAD']) != env['source_sha'] or sha(book) != report['input_sha256']:
        report['measurement_valid'] = False
    report['identity_changes'] = changed
    report['finished_at'] = utc()
    if frozen:
        violations = []
        for name, group in report['groups'].items():
            for batch in group['batches']:
                for trial in batch['trials']:
                    for key, value in trial.get('metrics', {}).items():
                        if value > frozen['limits'][name][key]:
                            violations.append({'stdout': trial['stdout'], 'metric': key, 'observed': value, 'limit': frozen['limits'][name][key]})
        report['verification'] = {'frozen_budget_sha256': sha(args.budgets), 'violations': violations,
            'local_numeric_pass': report['measurement_valid'] and not violations and all(g['final']['stable'] for g in report['groups'].values()),
            'e3_restoration_granted': False}
    write(args.output / 'samples.json', report)
    budgets = derive_budget(env, report, sha(args.output / 'samples.json'))
    write(args.output / 'proposed-budgets.json', budgets)
    (args.output / 'summary.md').write_text(markdown(env, report, budgets), encoding='utf-8')
    write(args.output / 'manifest.json', {str(p.relative_to(args.output)): sha(p) for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
    return 0 if budgets['eligible'] and (not frozen or report['verification']['local_numeric_pass']) else 1


if __name__ == '__main__':
    sys.exit(main())
