#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One diagnostic APK, original 45-case helper, completed-window FrameMetrics ABBA; CI only."""
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
import zipfile

import android_raster_ab_diagnostic as original
from check_parallel_integration import require

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/android-frame-metrics-ab'
original.OUT = OUT
APP, HELPER, TEST = original.APP, original.HELPER, original.TEST
REMOTE = '/sdcard/Android/data/' + APP + '/files/frame-metrics'
BASE = 'c9870ed68df539b2f08cb889817cd81b3e2e8a6b'
MODES = {'A': ('none', 0), 'B': ('software', 1)}
PLAN = {'diagnostic_only': True, 'accepted': False, 'sequence': [['A1', 'A'], ['B1', 'B'], ['B2', 'B'], ['A2', 'A']],
        'method': original.PLAN['method'], 'app_basis': BASE, 'one_apk': True,
        'A_layer': 'View.LAYER_TYPE_NONE (0), original default before the c987 software change',
        'B_layer': 'View.LAYER_TYPE_SOFTWARE (1), c987 production default',
        'frame_source': 'Window.OnFrameMetricsAvailableListener, copied in callback on its dedicated HandlerThread',
        'ordinary_frame_duration': 'FrameMetrics.TOTAL_DURATION; FIRST_DRAW_FRAME == 0',
        'frame_identity': 'pid, per-process window_id, delivered callback sequence (no historic deduplication)',
        'minimum_ordinary_frames_per_phase': 100, 'quantiles': 'nearest rank ceil(q*n), no pooling across phases',
        'pss': 'external PID-validated full process TOTAL PSS at one-second intervals, including a bounded tail sample',
        'warmup': 'Each phase probes its explicit Settings.Global configuration, then the unmodified test clears APP before starting',
        'inconclusive_on': ['missing or mismatched explicit phase/mode/layer', 'callback drops', 'malformed or truncated trace',
                            'trace budget/error', 'sampled PID missing from trace', 'B original case failure',
                            'unexpected A original case failure', 'fewer than 100 ordinary frames', 'sampling error',
                            'no PSS samples', 'changing emulator boot/display period'],
        'scope': ['Completed app-window callback duration, not display presentation or isolated ReaderView time',
                  'Original walkthrough includes screenshots, waits and deliberate process kills',
                  'Force-stop can end undelivered callbacks at the process boundary; no whole-session frame census claim',
                  'Callback collection and file writes add matched diagnostic overhead to both modes',
                  'Sampled TOTAL PSS peak is not continuous or a component-specific allocation',
                  'One API34 x86_64 emulator, two rounds per mode; no product performance budget']}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load(path):
    require(path.stat().st_size <= 16 * 1024 * 1024, 'Diagnostic JSON exceeds bound')
    return json.loads(path.read_text(encoding='utf-8'))


def source_guard():
    allowed = {'examples/android/app/build.gradle', '.github/workflows/reading-input-diagnostic.yml',
               'examples/android/app/src/main/java/org/exreader/host/ReaderView.java',
               'examples/android/app/src/main/java/org/exreader/host/MainActivity.java',
               'examples/android/app/src/main/java/org/exreader/host/FrameMetricsTrace.java',
               'tools/android_raster_ab_diagnostic.py', 'tools/android_frame_metrics_ab.py'}
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines()
    require(set(changed) <= allowed, 'Diagnostic source changed outside its explicit ownership')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
    return changed


def prepare():
    identity = original.cloud()
    OUT.mkdir(parents=True, exist_ok=False)
    save(OUT / 'plan.json', PLAN)
    commands = original.Commands(OUT / 'prepare-commands')
    report = {**identity, 'diagnostic_only': True, 'accepted': False, 'prepared': False, 'errors': []}
    try:
        report['changed_paths'] = source_guard()
        report['A'] = original.read_original(commands, 'A', original.OLD)
        report['B'] = original.read_original(commands, 'B', original.NEW)
        require(report['A']['registry'] == report['B']['registry'], 'Original font/native registries differ')
        app = ROOT / 'examples/android/app/src/main'
        with zipfile.ZipFile(OUT / 'B/app-debug.apk') as archive:
            names = original.zip_members(archive)
            for name in sorted(names):
                if name.startswith('assets/') and not name.endswith('/'):
                    target = app / name
                elif name.startswith('lib/') and name.endswith('.so'):
                    target = app / 'jniLibs' / name[4:]
                else:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        report['prepared'] = True
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        commands.persist()
        save(OUT / 'prepared.json', report)
    require(report['prepared'] and not report['errors'], 'Pinned preparation failed')


def verify():
    prepared = load(OUT / 'prepared.json')
    identity = original.cloud()
    require(prepared['prepared'] and not prepared['errors']
            and all(prepared[key] == value for key, value in identity.items()), 'Preparation identity differs')
    app = ROOT / 'examples/android/app/build/outputs/apk/debug/app-debug.apk'
    commands = original.Commands(OUT / 'verify-commands')
    result = {**identity, 'diagnostic_only': True, 'accepted': False}
    try:
        result['apk'] = original.inspect_apk(commands, app, APP)
        result['registry'] = original.apk_registry(app)
        require(result['registry'] == prepared['B']['registry'], 'Diagnostic APK changed original font/native bytes')
        with zipfile.ZipFile(app) as diagnostic, zipfile.ZipFile(OUT / 'B/app-debug.apk') as baseline:
            for archive in (diagnostic, baseline):
                original.zip_members(archive)
            def assets(archive):
                return {name: original.hashlib.sha256(archive.read(name)).hexdigest()
                        for name in archive.namelist() if name.startswith('assets/') and not name.endswith('/')}
            require(assets(diagnostic) == assets(baseline), 'Diagnostic APK assets differ from frozen c987 original')
            result['assets'] = assets(diagnostic)
        require(result['apk']['sha256'] != prepared['B']['apks']['app-debug.apk']['sha256'],
                'Diagnostic APK was confused with the original c987 binary')
        (OUT / 'diagnostic-app.apk').write_bytes(app.read_bytes())
        save(OUT / 'diagnostic-build.json', result)
        print(json.dumps(result), flush=True)
    finally:
        commands.persist()


def capture_pss(commands, sample):
    record, output = commands.adb('shell', 'pidof', APP, timeout=5, checked=False)
    sample['commands']['pid'] = record
    sample['pid'] = int(output.strip()) if re.fullmatch('[0-9]+', output.strip()) else None
    if sample['pid'] is not None:
        record, unused = commands.adb('shell', 'dumpsys', 'meminfo', str(sample['pid']), timeout=5, checked=False)
        sample['commands']['meminfo'] = record


def sampler(commands, stop, result, origin):
    result.update(samples=[], errors=[], missed_slots=[], completed=False)
    slot = 0
    try:
        while slot < 900 and not stop.is_set():
            if stop.wait(max(0, origin + slot - time.monotonic())):
                break
            actual = int(time.monotonic() - origin)
            if actual > slot:
                result['missed_slots'].append({'first': slot, 'last': actual - 1})
                slot = actual
            sample = {'slot': slot, 'commands': {}}
            result['samples'].append(sample)
            slot += 1
            capture_pss(commands, sample)
        result['completed'] = True
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        result['ended_before_method_stop'] = not stop.is_set()


def traces(folder, label, variant):
    result = {'files': [], 'ordinary': [], 'first_draw': [], 'pids': [], 'drops': 0, 'errors': []}
    for path in sorted(folder.glob('*.jsonl')):
        require(path.stat().st_size <= 16 * 1024 * 1024 + 4096, 'Trace exceeds declared byte budget')
        raw = path.read_bytes()
        require(raw.endswith(b'\n'), 'Truncated callback trace')
        rows = [json.loads(line) for line in raw.splitlines()]
        require(rows and rows[0]['kind'] == 'start', 'Trace header missing')
        header = rows[0]
        require(header['phase'] == label and header['mode'] == MODES[variant][0]
                and header['layer_type'] == MODES[variant][1], 'Explicit phase/mode/layer mismatch')
        count = 0
        for row in rows[1:]:
            require(row['kind'] in ('frame', 'stop'), 'Trace error or unknown row')
            if row['kind'] == 'stop':
                require(row is rows[-1] and row['frames'] == count, 'Stop marker differs from callback count')
                continue
            count += 1
            require(row['pid'] == header['pid'] and row['window_id'] == header['window_id']
                    and row['phase'] == label and row['mode'] == MODES[variant][0]
                    and row['sequence'] == count, 'Callback identity/sequence differs')
            require(type(row['total_ns']) is int and row['total_ns'] >= 0 and row['intended_vsync_ns'] > 0
                    and row['first_draw'] in (0, 1) and type(row['drop_count']) is int and row['drop_count'] >= 0,
                    'Invalid completed callback metrics')
            result['drops'] += row['drop_count']
            result['first_draw' if row['first_draw'] else 'ordinary'].append(row)
        result['files'].append({'path': path.name, 'bytes': len(raw), 'sha256': original.hashlib.sha256(raw).hexdigest(),
                                'header': header, 'delivered_callbacks': count, 'graceful_stop': rows[-1]['kind'] == 'stop'})
    result['pids'] = sorted({item['header']['pid'] for item in result['files']})
    require(result['files'], 'No completed FrameMetrics trace; explicit settings may have been unreadable')
    return result


def summarize_trace(result, period):
    def stats(values):
        return {'count': len(values), 'p50_ms': original.quantile(values, .50), 'p95_ms': original.quantile(values, .95),
                'p99_ms': original.quantile(values, .99), 'max_ms': max(values, default=None)}
    summary = {key: stats([row['total_ns'] / 1e6 for row in result[key]]) for key in ('ordinary', 'first_draw')}
    summary['ordinary']['fraction_over_display_period'] = (
        sum(row['total_ns'] > period for row in result['ordinary']) / len(result['ordinary'])
        if result['ordinary'] and period else None)
    stage_names = ('unknown_delay_ns', 'input_ns', 'animation_ns', 'layout_measure_ns', 'draw_ns', 'sync_ns',
                   'command_issue_ns', 'swap_buffers_ns', 'gpu_ns', 'deadline_ns')
    summary['ordinary_stage_metrics'] = {name: {**stats([row[name] / 1e6 for row in result['ordinary'] if row[name] >= 0]),
                                                       'unavailable': sum(row[name] < 0 for row in result['ordinary'])}
                                         for name in stage_names}
    summary.update(files=result['files'], pids=result['pids'], callback_drop_count=result['drops'])
    return summary


def phase(label, variant, prepared, built, identity, order):
    folder = OUT / label
    folder.mkdir()
    commands = original.Commands(folder / 'commands')
    result = {'label': label, 'variant': variant, 'diagnostic_only': True, 'accepted': False,
              'completed': False, 'errors': []}
    samples, stop, thread = {}, threading.Event(), None
    try:
        _, result['boot_before'] = commands.adb('shell', 'cat', '/proc/sys/kernel/random/boot_id')
        result['period_before_ns'] = original.refresh_period(commands)
        for package in (TEST, HELPER, APP):
            commands.adb('shell', 'am', 'force-stop', package, checked=False)
            commands.adb('uninstall', package, checked=False)
        for key, value in (('mode', MODES[variant][0]), ('phase', label)):
            commands.adb('shell', 'settings', 'put', 'global', 'exreader_frame_metrics_' + key, value)
            _, observed = commands.adb('shell', 'settings', 'get', 'global', 'exreader_frame_metrics_' + key)
            require(observed.strip() == value, 'Shell configuration did not persist')
        installed = {}
        for name in original.APK_NAMES:
            source = OUT / 'diagnostic-app.apk' if name == 'app-debug.apk' else OUT / 'A' / name
            package = original.PACKAGES[name]
            commands.adb('install', '-t', '-g', str(source), timeout=180)
            _, text = commands.adb('shell', 'pm', 'path', package)
            paths = text.strip().splitlines()
            require(len(paths) == 1 and paths[0].startswith('package:'), 'Original package not monolithic')
            pulled = folder / ('installed-' + name)
            commands.adb('pull', paths[0][8:], str(pulled), timeout=90)
            installed[name] = original.sha(pulled)
            require(installed[name] == original.sha(source), 'Installed APK differs')
            pulled.unlink()
        result['installed_sha256'] = installed
        commands.adb('shell', 'rm', '-rf', original.REMOTE)
        commands.adb('shell', 'mkdir', '-p', '/sdcard/Download')
        for name, fixture in prepared['A']['fixtures'].items():
            if Path(name).suffix not in ('.epub', '.pdf', '.txt'):
                continue
            commands.adb('push', str(OUT / 'A/fixtures' / name), '/sdcard/Download/' + name)
            _, text = commands.adb('shell', 'sha256sum', '/sdcard/Download/' + name)
            require(text.split()[0] == fixture['sha256'], 'Original fixture differs')
        for setting in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
            commands.adb('shell', 'settings', 'put', 'global', setting, '0')
        commands.adb('shell', 'settings', 'put', 'global', 'hide_error_dialogs', '1')
        commands.adb('shell', 'settings', 'put', 'global', 'anr_show_background', '0')
        commands.adb('shell', 'am', 'start', '-W', '-n', APP + '/.MainActivity')
        time.sleep(2)
        commands.adb('pull', REMOTE, str(folder / 'probe'), timeout=30)
        probe = traces(folder / 'probe', label, variant)
        result['explicit_configuration_probe'] = {'files': probe['files'], 'pids': probe['pids']}
        commands.adb('shell', 'am', 'force-stop', APP)
        commands.adb('logcat', '-c')
        argv = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'disableAnalytics', 'true',
                '-e', 'class', PLAN['method'], '-e', 'exr_suite', 'walkthrough',
                '-e', 'exr_source_sha', identity['source_sha'], '-e', 'exr_run_id', identity['run_id'],
                '-e', 'exr_attempt', identity['attempt'], '-e', 'apk_sha256', installed['app-debug.apk'],
                '-e', 'test_apk_sha256', installed['uitest-debug-androidTest.apk'], original.RUNNER]
        origin = time.monotonic()
        thread = threading.Thread(target=sampler, args=(commands, stop, samples, origin), daemon=True)
        thread.start()
        result['instrumentation'], unused = commands.run(argv, timeout=900)
        stop.set()
        thread.join(timeout=30)
        require(not thread.is_alive(), 'External sampler did not stop')
        tail = {'slot': 'tail', 'commands': {}}
        capture_pss(commands, tail)
        samples['samples'].append(tail)
        commands.adb('shell', 'am', 'force-stop', APP)
        commands.adb('pull', REMOTE, str(folder / 'traces'), timeout=60)
        commands.adb('pull', original.REMOTE, str(folder / 'device'), timeout=120)
        commands.adb('logcat', '-d', '-v', 'monotonic', '-s', 'EXRFrameMetrics:I', 'EXRHost:I', '*:S')
        validation = load(folder / 'device/validation.json')
        original.validate_cases(validation, order)
        require(all(validation[key] == value for key, value in identity.items()), 'Fresh original case provenance differs')
        require(validation['apk_sha256'] == installed['app-debug.apk']
                and validation['test_apk_sha256'] == installed['uitest-debug-androidTest.apk'], 'Original case APK identity differs')
        result['original_summary'] = validation['summary']
        result['original_failed_ids'] = [case['id'] for case in validation['cases'] if case['status'] != 'pass']
        trace = traces(folder / 'traces', label, variant)
        require(not (set(trace['pids']) & set(probe['pids'])), 'Warmup probe was reused after original pm clear')
        result['frame_metrics'] = summarize_trace(trace, result['period_before_ns'])
        pss, observed_pids, failures = [], set(), []
        for sample in samples['samples']:
            if sample.get('pid') is None:
                continue
            observed_pids.add(sample['pid'])
            record = sample['commands'].get('meminfo')
            if not record or record['exit_code']:
                failures.append({'slot': sample['slot'], 'pid': sample['pid'], 'reason': 'meminfo command'})
                continue
            raw = (folder / 'commands' / record['stdout']).read_text(encoding='utf-8', errors='replace')
            try:
                pss.append({'slot': sample['slot'], 'pid': sample['pid'], 'total_pss_kib': original.parse_pss(raw, sample['pid'])})
            except ValueError:
                failures.append({'slot': sample['slot'], 'pid': sample['pid'], 'reason': 'PID/total differs'})
        result['total_pss'] = {'sample_count': len(pss), 'median_kib': statistics.median(item['total_pss_kib'] for item in pss) if pss else None,
                               'max_kib': max((item['total_pss_kib'] for item in pss), default=None),
                               'observed_pids': sorted(observed_pids), 'failed_samples': failures,
                               'sampled_pids_missing_from_trace': sorted(observed_pids - set(trace['pids']))}
        save(folder / 'total-pss-samples.json', pss)
        _, result['boot_after'] = commands.adb('shell', 'cat', '/proc/sys/kernel/random/boot_id')
        result['period_after_ns'] = original.refresh_period(commands)
        result['completed'] = not result['instrumentation'].get('timed_out') and samples['completed']
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=30)
        if samples:
            save(folder / 'sampling.json', samples)
            result['sampling'] = {key: samples.get(key) for key in ('completed', 'errors', 'missed_slots', 'ended_before_method_stop')}
        commands.persist()
        save(folder / 'phase.json', result)
    return result


def run():
    identity = original.cloud()
    prepared, built = load(OUT / 'prepared.json'), load(OUT / 'diagnostic-build.json')
    require(load(OUT / 'plan.json') == PLAN and prepared['prepared'] and not prepared['errors'], 'Preparation/plan differs')
    require(all(value[key] == expected for value in (prepared, built) for key, expected in identity.items()), 'Diagnostic build provenance differs')
    report = {**identity, 'diagnostic_only': True, 'accepted': False, 'diagnostic_completed': False,
              'comparison_interpretable': False, 'inconclusive_reasons': [], 'phases': []}
    commands = original.Commands(OUT / 'environment')
    try:
        for argv in (['adb', 'version'], ['adb', 'shell', 'getprop'], ['adb', 'shell', 'wm', 'size'],
                     ['adb', 'shell', 'wm', 'density'], ['adb', 'shell', 'dumpsys', 'display'], ['lscpu']):
            commands.run(argv, checked=True)
        _, api = commands.adb('shell', 'getprop', 'ro.build.version.sdk')
        _, abi = commands.adb('shell', 'getprop', 'ro.product.cpu.abi')
        require(api.strip() == '34' and abi.strip() == 'x86_64', 'API34 x86_64 required')
        order = original.validate_cases(load(OUT / 'A/original-validation.json'))
        for label, variant in PLAN['sequence']:
            report['phases'].append(phase(label, variant, prepared, built, identity, order))
            save(OUT / 'diagnostic.json', report)
        report['diagnostic_completed'] = all(item['completed'] and not item['errors'] for item in report['phases'])
        reasons = report['inconclusive_reasons']
        if not report['diagnostic_completed']:
            reasons.append('One or more phases did not complete')
        boots = {item.get('boot_before') for item in report['phases']} | {item.get('boot_after') for item in report['phases']}
        periods = {item.get('period_before_ns') for item in report['phases']} | {item.get('period_after_ns') for item in report['phases']}
        if len(boots) != 1 or None in boots:
            reasons.append('Not one uninterrupted emulator boot')
        if len(periods) != 1 or None in periods:
            reasons.append('Unknown or varying display refresh period')
        for item in report['phases']:
            frames, memory, sampling = item.get('frame_metrics', {}), item.get('total_pss', {}), item.get('sampling', {})
            if frames.get('callback_drop_count', 1):
                reasons.append(item['label'] + ': callback drops/missing callbacks')
            if frames.get('ordinary', {}).get('count', 0) < PLAN['minimum_ordinary_frames_per_phase']:
                reasons.append(item['label'] + ': fewer than 100 ordinary frames')
            if not memory.get('sample_count') or memory.get('sampled_pids_missing_from_trace'):
                reasons.append(item['label'] + ': missing memory or PID trace')
            if sampling.get('errors') or sampling.get('ended_before_method_stop') or sampling.get('missed_slots'):
                reasons.append(item['label'] + ': incomplete external sampling')
            failures = set(item.get('original_failed_ids', []))
            if (item['variant'] == 'B' and failures) or (failures - {'process_restart_reflow', 'pdf_process_restart'}):
                reasons.append(item['label'] + ': unexpected original walkthrough failure')
        report['comparison_interpretable'] = not reasons
    except Exception as error:
        report['inconclusive_reasons'].append(type(error).__name__ + ': ' + str(error))
    finally:
        for key in ('mode', 'phase'):
            commands.adb('shell', 'settings', 'delete', 'global', 'exreader_frame_metrics_' + key, checked=False)
        commands.persist()
        save(OUT / 'diagnostic.json', report)
        print(json.dumps(report), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    require(len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'verify', 'run'), 'Use prepare, verify or run')
    if sys.argv[1] == 'run':
        sys.exit(run())
    elif sys.argv[1] == 'prepare':
        prepare()
    else:
        verify()
