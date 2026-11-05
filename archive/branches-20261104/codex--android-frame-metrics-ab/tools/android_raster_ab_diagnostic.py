#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only, original-APK ABBA sampling; never grants product acceptance."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import sys
import threading
import time
import zipfile

from check_parallel_integration import download_artifact_zip, fetch, pages, require

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/android-raster-ab-diagnostic'
APP = 'org.exreader.host'
HELPER = APP + '.uitest'
TEST = HELPER + '.test'
RUNNER = TEST + '/androidx.test.runner.AndroidJUnitRunner'
REMOTE = '/sdcard/Android/data/' + HELPER + '/files/evidence'
APK_NAMES = ('app-debug.apk', 'uitest-debug.apk', 'uitest-debug-androidTest.apk')
PACKAGES = dict(zip(APK_NAMES, (APP, HELPER, TEST)))
OLD = {'run_id': 39991607049, 'attempt': 1,
       'source_sha': 'de9871aca6a54f70c6c1d147ba12f308cedf1004',
       'artifact_id': 12517859271, 'bytes': 157060818,
       'digest': 'a68d1d71afa48a2d05bcc9c44732b619af6139db4bac39fa08c6051922046ec0'}
NEW = {'run_id': 39995947460, 'attempt': 1,
       'source_sha': 'c9870ed68df539b2f08cb889817cd81b3e2e8a6b',
       'artifact_id': 12521340611, 'bytes': 157918559,
       'digest': 'bc456d4fba84acd16d2676867d792038c113e300d7b526901e7e75319416957a'}
PLAN = {
    'diagnostic_only': True, 'accepted': False,
    'sequence': [['A1', 'A'], ['B1', 'B'], ['B2', 'B'], ['A2', 'A']],
    'method': 'org.exreader.host.uitest.HostWalkthroughTest#walkthrough',
    'original_case_count': 45, 'sample_interval_seconds': 1,
    'phase_timeout_seconds': 900, 'max_sample_slots': 900,
    'sample_command_timeout_seconds': 5,
    'tail_capture': 'One bounded external sample immediately after method exit retains the final ring-buffer interval',
    'max_raw_sampling_bytes_per_phase': 256 * 1024 * 1024,
    'frame_key': ['actual_dump_pid', 'window', 'IntendedVsync'],
    'frame_duration_ms': '(FrameCompleted - IntendedVsync) / 1000000',
    'ordinary_frame_filter': 'Flags == 0; 0 < IntendedVsync <= FrameCompleted < 2**63-1',
    'frame_metrics': ['count', 'p50_ms', 'p95_ms', 'p99_ms', 'max_ms', 'fraction_over_display_period'],
    'quantile_method': 'nearest rank ceil(q*n), separately for each phase',
    'pss_metrics': ['sample_count', 'median_kib', 'max_kib'],
    'pss_scope': 'Full app process TOTAL PSS, KiB; external dumpsys samples',
    'pss_median_method': 'Arithmetic mean of the middle pair for even sample counts',
    'minimum_usable_frames_per_phase': 100,
    'pairing': ['B1 minus A1', 'B2 minus A2'],
    'aggregation': 'No pooling across phases; paired differences are descriptive only',
    'interpretation': [
        'Font or complete native .so registry differences stop single-factor interpretation',
        'The old 45-step walkthrough includes screenshots, waits and process restarts',
        'Whole-method wall time is not UI frame time; no per-operation latency claim',
        'gfxinfo samples app windows, not an isolated ReaderView render call',
        'Ring buffers may lose frames between polls; gaps and sampler overhead remain visible',
        'TOTAL PSS is a sampled peak, not a continuous or component-specific peak',
        'Fewer than 100 ordinary frames in any phase makes the comparison inconclusive',
        'Two rounds per variant on one emulator do not establish a product performance budget',
    ],
}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def load(path):
    require(path.stat().st_size <= 8 * 1024 * 1024, 'JSON exceeds bounded size: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cloud():
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true', 'Cloud Linux runner required')
    require(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Unexpected repository')
    require(re.fullmatch('[0-9a-f]{40}', os.environ.get('GITHUB_SHA', '')), 'Missing diagnostic SHA')
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        require(re.fullmatch('[1-9][0-9]*', os.environ.get(key, '')), 'Missing cloud run identity')
    return {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT']}


class Commands:
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(parents=True)
        self.records = []
        self.lock = threading.Lock()

    def run(self, argv, timeout=60, checked=False):
        with self.lock:
            stem = str(len(self.records)).zfill(5)
            record = {'argv': list(map(str, argv)), 'timeout_seconds': timeout,
                      'start_monotonic': time.monotonic(), 'start_unix_ns': time.time_ns(),
                      'stdout': stem + '.stdout.txt', 'stderr': stem + '.stderr.txt'}
            self.records.append(record)
        stdout, stderr = self.folder / record['stdout'], self.folder / record['stderr']
        with stdout.open('wb') as out, stderr.open('wb') as err:
            try:
                process = subprocess.Popen(record['argv'], stdout=out, stderr=err)
                try:
                    record['exit_code'] = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                    record.update(exit_code=-1, timed_out=True)
            except OSError as error:
                record.update(exit_code=-1, error=str(error))
        record.update(end_monotonic=time.monotonic(), end_unix_ns=time.time_ns())
        record['duration_seconds'] = record['end_monotonic'] - record['start_monotonic']
        record['stdout_bytes'], record['stderr_bytes'] = stdout.stat().st_size, stderr.stat().st_size
        require(max(record['stdout_bytes'], record['stderr_bytes']) <= 32 * 1024 * 1024,
                'Command output exceeded 32 MiB; raw files retained')
        text = stdout.read_text(encoding='utf-8', errors='replace')
        if checked:
            require(record['exit_code'] == 0, 'Command failed: ' + ' '.join(record['argv'][:6]))
        return record, text

    def adb(self, *args, timeout=60, checked=True):
        return self.run(['adb', *args], timeout=timeout, checked=checked)

    def persist(self):
        save(self.folder / 'commands.json', self.records)


def zip_members(archive):
    entries = archive.infolist()
    require(len(entries) <= 15000, 'ZIP member count exceeded')
    names = [entry.filename for entry in entries]
    require(len(set(names)) == len(names), 'Duplicate ZIP members')
    require(sum(entry.file_size for entry in entries) <= 768 * 1024 * 1024, 'ZIP uncompressed size exceeded')
    for entry in entries:
        path = PurePosixPath(entry.filename)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in entry.filename
                and ':' not in entry.filename and '\x00' not in entry.filename,
                'Unsafe ZIP member')
        require(entry.file_size <= 256 * 1024 * 1024 and not (entry.flag_bits & 1), 'Oversized/encrypted ZIP member')
        require((entry.external_attr >> 16) & 0o170000 != 0o120000, 'ZIP symlink refused')
    return set(names)


def member(archive, name, limit):
    entry = archive.getinfo(name)
    require(not entry.is_dir() and entry.file_size <= limit, 'Unexpected ZIP member size: ' + name)
    return archive.read(entry)


def verified_member(archive, name, identity, limit):
    data = member(archive, name, limit)
    require(len(data) == identity['size'] and hashlib.sha256(data).hexdigest() == identity['sha256'],
            'Original build member hash/size differs: ' + name)
    return data


def apk_registry(path):
    with zipfile.ZipFile(path) as apk:
        names = zip_members(apk)
        require('assets/Reader.otf' in names, 'Reader font missing')
        native = {name: hashlib.sha256(member(apk, name, 128 * 1024 * 1024)).hexdigest()
                  for name in sorted(names) if name.startswith('lib/') and name.endswith('.so')}
        require(any(name.startswith('lib/x86_64/') for name in native), 'x86_64 native registry missing')
        return {'font_sha256': hashlib.sha256(member(apk, 'assets/Reader.otf', 64 * 1024 * 1024)).hexdigest(),
                'native_sha256': native}


def inspect_apk(commands, path, package, test=False):
    sdk = Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0'
    _, badging = commands.run([sdk / 'aapt', 'dump', 'badging', path], checked=True)
    require(re.search(r"^package: name='" + re.escape(package) + "'", badging, re.M), 'Wrong APK package')
    _, signing = commands.run([sdk / 'apksigner', 'verify', '--print-certs', path], checked=True)
    signers = re.findall(r'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\s*$', signing, re.M)
    require(len(signers) == 1, 'Expected exactly one original APK signer')
    result = {'package': package, 'sha256': sha(path), 'bytes': path.stat().st_size,
              'signer_certificate_sha256': signers[0].lower()}
    if test:
        _, manifest = commands.run([sdk / 'aapt', 'dump', 'xmltree', path, 'AndroidManifest.xml'], checked=True)
        require(re.search(r'android:targetPackage[^\r\n]*"' + re.escape(HELPER) + '"', manifest)
                and re.search(r'android:name[^\r\n]*"androidx\.test\.runner\.AndroidJUnitRunner"', manifest),
                'Original test runner/target differs')
        result.update(target_package=HELPER, runner=RUNNER)
    return result


def read_original(commands, variant, pin):
    run = fetch('actions/runs/' + str(pin['run_id']) + '/attempts/' + str(pin['attempt']))
    require(run['id'] == pin['run_id'] and run['run_attempt'] == pin['attempt']
            and run['head_sha'] == pin['source_sha'] and run['event'] == 'workflow_dispatch'
            and run['path'].split('@')[0] == '.github/workflows/wp13-android.yml'
            and run['status'] == 'completed', 'Pinned Android run identity differs')
    if variant == 'A':
        require(run['conclusion'] == 'failure', 'Old failure history changed')
    else:
        require(run['conclusion'] == 'success', 'Reviewed new run conclusion changed')
    artifacts = pages('actions/runs/' + str(pin['run_id']) + '/artifacts', 'artifacts')
    selected = [item for item in artifacts if item['id'] == pin['artifact_id'] or item['name'] == 'EXReader-WP13-Android']
    require(len(selected) == 1, 'Missing/duplicate selected original artifact')
    artifact = selected[0]
    require(artifact['id'] == pin['artifact_id'] and artifact['name'] == 'EXReader-WP13-Android'
            and artifact['size_in_bytes'] == pin['bytes'] and artifact['expired'] is False
            and artifact['digest'] == 'sha256:' + pin['digest']
            and artifact['workflow_run']['id'] == pin['run_id']
            and artifact['workflow_run']['head_sha'] == pin['source_sha'], 'Pinned ZIP metadata differs')
    require(0 < pin['bytes'] <= 256 * 1024 * 1024, 'ZIP byte cap exceeded')
    folder = OUT / variant
    folder.mkdir()
    original = folder / 'original.zip'
    with original.open('w+b') as output:
        download_artifact_zip(pin['artifact_id'], output)
    require(original.stat().st_size == pin['bytes'] and sha(original) == pin['digest'], 'Downloaded ZIP identity differs')
    with zipfile.ZipFile(original) as archive:
        zip_members(archive)
        build_data = member(archive, 'build/android-host/build.json', 4 * 1024 * 1024)
        (folder / 'original-build.json').write_bytes(build_data)
        build = json.loads(build_data)
        require(build['source_sha'] == pin['source_sha'] and build['run_id'] == str(pin['run_id'])
                and build['attempt'] == str(pin['attempt']), 'Original build provenance differs')
        apks = APK_NAMES if variant == 'A' else APK_NAMES[:1]
        inspected = {}
        for name in apks:
            path = folder / name
            path.write_bytes(verified_member(archive, 'build/android-host/artifacts/' + name,
                                            build['artifacts'][name], 128 * 1024 * 1024))
            inspected[name] = inspect_apk(commands, path, PACKAGES[name], name == APK_NAMES[2])
        if variant == 'A':
            require(inspected[APK_NAMES[1]]['signer_certificate_sha256'] == inspected[APK_NAMES[2]]['signer_certificate_sha256'],
                    'Original helper/test signers differ')
            require(0 < len(build['fixtures']) <= 32, 'Fixture count out of bounds')
            fixtures = folder / 'fixtures'
            fixtures.mkdir()
            for name, identity in build['fixtures'].items():
                require(re.fullmatch('[A-Za-z0-9_.-]{1,100}', name) and name not in ('.', '..'), 'Unsafe fixture basename')
                (fixtures / name).write_bytes(verified_member(archive, 'build/android-host/fixtures/' + name,
                                                            identity, 64 * 1024 * 1024))
            original_validation = member(archive, 'build/android-host/evidence/device/validation.json', 8 * 1024 * 1024)
            (folder / 'original-validation.json').write_bytes(original_validation)
            validation = json.loads(original_validation)
            validate_cases(validation)
            require(validation['summary']['passed'] == 43 and validation['summary']['failed'] == 2,
                    'Old original 43/45 failure history differs')
        registry = apk_registry(folder / APK_NAMES[0])
        require(registry['font_sha256'] == build['font']['sha256'], 'APK font differs from original build registry')
    return {'pin': pin, 'original_conclusion': run['conclusion'],
            'run': {key: run[key] for key in ('id', 'run_attempt', 'head_sha', 'event', 'path', 'status', 'conclusion')},
            'artifact': artifact,
            'apks': inspected, 'registry': registry, 'fixtures': build['fixtures'] if variant == 'A' else None}


def validate_cases(validation, expected_order=None):
    cases = validation['cases']
    require(isinstance(cases, list) and len(cases) == 45, 'Original walkthrough did not produce 45 cases')
    order = [case['id'] for case in cases]
    require(len(set(order)) == 45 and all(case['status'] in ('pass', 'fail') for case in cases), 'Case IDs/statuses differ')
    summary = validation['summary']
    require(summary['total'] == 45 and summary['passed'] == sum(case['status'] == 'pass' for case in cases)
            and summary['failed'] == sum(case['status'] == 'fail' for case in cases)
            and summary.get('skipped', 0) == 0, 'Original case summary inconsistent')
    if expected_order is not None:
        require(order == expected_order, 'Original 45-step case order differs')
    return order


def prepare():
    identity = cloud()
    OUT.mkdir(parents=True, exist_ok=False)
    save(OUT / 'plan.json', PLAN)
    commands = Commands(OUT / 'prepare-commands')
    report = {**identity, 'diagnostic_only': True, 'accepted': False, 'prepared': False, 'errors': []}
    try:
        require(re.fullmatch('[1-9][0-9]*', os.environ.get('AB_NEW_ID', '')), 'Reviewed new artifact ID required')
        require(re.fullmatch('[1-9][0-9]*', os.environ.get('AB_NEW_BYTES', '')), 'Reviewed new artifact bytes required')
        require(re.fullmatch('[0-9a-f]{64}', os.environ.get('AB_NEW_DIGEST', '')), 'Reviewed new ZIP digest required')
        new = dict(NEW, artifact_id=int(os.environ['AB_NEW_ID']), bytes=int(os.environ['AB_NEW_BYTES']),
                   digest=os.environ['AB_NEW_DIGEST'])
        require(new == NEW, 'Workflow inputs do not match reviewed new artifact registry')
        report['A'] = read_original(commands, 'A', OLD)
        report['B'] = read_original(commands, 'B', new)
        report['confounds'] = [field for field in ('font_sha256', 'native_sha256')
                               if report['A']['registry'][field] != report['B']['registry'][field]]
        report['single_factor_interpretation_allowed'] = not report['confounds']
        report['app_signers_equal'] = (report['A']['apks'][APK_NAMES[0]]['signer_certificate_sha256'] ==
                                        report['B']['apks'][APK_NAMES[0]]['signer_certificate_sha256'])
        report['prepared'] = True
        parser_check()
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        commands.persist()
        save(OUT / 'prepared.json', report)
    require(report['prepared'] and not report['errors'], 'Preparation failed; inspect prepared.json')


def parse_frames(text):
    pid, window, header = None, None, None
    frames, invalid = [], {}
    def reject(reason):
        invalid[reason] = invalid.get(reason, 0) + 1
    for raw in text.splitlines():
        line = raw.strip()
        match = re.search(r'Graphics info for pid (\d+)', line)
        if match:
            pid, window, header = int(match[1]), None, None
        if line.startswith('Window:'):
            window, header = line[7:].strip(), None
        if line.startswith('Flags,'):
            header = line.rstrip(',').split(',')
            continue
        if line == '---PROFILEDATA---':
            header = None
            continue
        if header is None or not re.match(r'^-?\d+,', line):
            continue
        cells = line.rstrip(',').split(',')
        if len(cells) != len(header):
            reject('column_count')
            continue
        try:
            row = dict(zip(header, map(int, cells)))
            start, end = row['IntendedVsync'], row['FrameCompleted']
            if row['Flags'] != 0:
                reject('nonzero_flags')
            elif not (0 < start <= end < 2**63 - 1):
                reject('incomplete_or_sentinel')
            elif pid is None or not window:
                reject('missing_pid_or_window')
            else:
                frames.append({'pid': pid, 'window': window, 'intended_vsync_ns': start,
                               'frame_completed_ns': end, 'duration_ms': (end - start) / 1e6, 'raw': row})
        except (ValueError, KeyError):
            reject('invalid_number_or_header')
    return frames, invalid


def parse_pss(text, pid):
    actual = re.search(r'\*\* MEMINFO in pid (\d+)', text)
    require(actual and int(actual[1]) == pid, 'meminfo PID changed/missing')
    match = re.search(r'\bTOTAL PSS:\s*(\d+)', text)
    if match is None:
        match = re.search(r'^\s*TOTAL\s+(\d+)\s', text, re.M)
    require(match, 'Full process TOTAL PSS missing')
    return int(match[1])


def parser_check():
    # Executed only in the cloud preparation step, before any emulator measurements.
    sample = ('** Graphics info for pid 17 [org.exreader.host] **\n  Window: reader\n'
              '---PROFILEDATA---\nFlags,IntendedVsync,FrameCompleted,\n'
              '0,1000000,4000000,\n1,2000000,5000000,\n0,3,9223372036854775807,\n---PROFILEDATA---\n')
    frames, invalid = parse_frames(sample)
    require(len(frames) == 1 and frames[0]['duration_ms'] == 3 and frames[0]['pid'] == 17
            and invalid == {'nonzero_flags': 1, 'incomplete_or_sentinel': 1}, 'Framestats parser check failed')
    require(parse_pss('** MEMINFO in pid 17 [org.exreader.host] **\n TOTAL PSS: 1234\n', 17) == 1234,
            'PSS parser check failed')


def sampler(commands, stop, result, origin):
    next_slot, raw_bytes = 0, 0
    result.update(samples=[], missed_slots=[], errors=[], completed=False)
    try:
        while next_slot < PLAN['max_sample_slots'] and not stop.is_set():
            target = origin + next_slot * PLAN['sample_interval_seconds']
            if stop.wait(max(0, target - time.monotonic())):
                break
            actual_slot = int((time.monotonic() - origin) // PLAN['sample_interval_seconds'])
            if actual_slot > next_slot:
                result['missed_slots'].append({'first': next_slot, 'last': actual_slot - 1})
                next_slot = actual_slot
            if next_slot >= PLAN['max_sample_slots']:
                break
            sample = {'slot': next_slot, 'target_monotonic': origin + next_slot,
                      'start_monotonic': time.monotonic(), 'commands': {}}
            result['samples'].append(sample)
            next_slot += 1
            capture_sample(commands, sample, stop)
            raw_bytes += sum(item['stdout_bytes'] + item['stderr_bytes'] for item in sample['commands'].values())
            require(raw_bytes <= PLAN['max_raw_sampling_bytes_per_phase'], 'Raw sampling byte cap reached')
        result['completed'] = True
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        result.update(end_monotonic=time.monotonic(), raw_bytes=raw_bytes,
                      ended_before_method_stop=not stop.is_set())


def capture_sample(commands, sample, stop=None):
    for label, args in (
            ('uptime', ['shell', 'cat', '/proc/uptime']),
            ('pid', ['shell', 'pidof', APP]),
            ('cases', ['shell', 'ls', REMOTE + '/cases'])):
        if stop is not None and stop.is_set():
            break
        record, output = commands.adb(*args, timeout=5, checked=False)
        sample['commands'][label] = record
        if label == 'pid':
            sample['pid'] = int(output.strip()) if re.fullmatch(r'\d+', output.strip()) else None
        elif label == 'uptime':
            sample['device_uptime_raw'] = output.strip()
        else:
            sample['observed_case_files'] = output.splitlines()
    if sample.get('pid') is not None:
        for label, args in (
                ('gfxinfo', ['shell', 'dumpsys', 'gfxinfo', APP, 'framestats']),
                ('meminfo', ['shell', 'dumpsys', 'meminfo', str(sample['pid'])])):
            if stop is not None and stop.is_set():
                break
            record, unused = commands.adb(*args, timeout=5, checked=False)
            sample['commands'][label] = record
    sample['end_monotonic'] = time.monotonic()
    sample['duration_seconds'] = sample['end_monotonic'] - sample['start_monotonic']


def quantile(values, q):
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)] if values else None


def analyse(folder, samples, period_ns):
    unique, conflicts, invalid, pss, by_pid = {}, [], {}, [], {}
    previous, no_overlap = {}, []
    def raw(record):
        return (folder / 'commands' / record['stdout']).read_text(encoding='utf-8', errors='replace')
    for sample in samples['samples']:
        pid = sample.get('pid')
        if pid is not None:
            by_pid.setdefault(str(pid), {'observed_samples': 0, 'frames': 0, 'pss_samples': 0})['observed_samples'] += 1
        graphics = sample['commands'].get('gfxinfo')
        if graphics and graphics['exit_code'] == 0:
            frames, rejected = parse_frames(raw(graphics))
            for reason, count in rejected.items():
                invalid[reason] = invalid.get(reason, 0) + count
            windows = {}
            for frame in frames:
                if frame['pid'] != pid:
                    invalid['pid_race'] = invalid.get('pid_race', 0) + 1
                    continue
                key = (frame['pid'], frame['window'], frame['intended_vsync_ns'])
                windows.setdefault(key[:2], []).append(key[2])
                if key in unique and unique[key]['raw'] != frame['raw']:
                    conflicts.append({'key': key, 'first': unique[key], 'conflicting': frame, 'slot': sample['slot']})
                else:
                    unique.setdefault(key, frame)
            for window, starts in windows.items():
                current = set(starts)
                if window in previous and not (current & previous[window]) and min(current) > max(previous[window]):
                    no_overlap.append({'pid': window[0], 'window': window[1], 'slot': sample['slot'],
                                       'previous_max_intended_vsync_ns': max(previous[window]),
                                       'current_min_intended_vsync_ns': min(current)})
                previous[window] = current
        memory = sample['commands'].get('meminfo')
        if memory and memory['exit_code'] == 0:
            try:
                pss.append({'slot': sample['slot'], 'pid': pid, 'total_pss_kib': parse_pss(raw(memory), pid),
                            'start_monotonic': memory['start_monotonic'], 'duration_seconds': memory['duration_seconds']})
                by_pid[str(pid)]['pss_samples'] += 1
            except ValueError:
                invalid['meminfo_pid_race_or_missing_total'] = invalid.get('meminfo_pid_race_or_missing_total', 0) + 1
    # Conflicting completed keys are excluded from numerical summaries, with both observations retained.
    for conflict in conflicts:
        unique.pop(tuple(conflict['key']), None)
    frames = sorted(unique.values(), key=lambda item: (item['pid'], item['window'], item['intended_vsync_ns']))
    for frame in frames:
        stats = by_pid[str(frame['pid'])]
        stats['frames'] += 1
        stats['first_intended_vsync_ns'] = min(stats.get('first_intended_vsync_ns', frame['intended_vsync_ns']), frame['intended_vsync_ns'])
        stats['last_intended_vsync_ns'] = max(stats.get('last_intended_vsync_ns', 0), frame['intended_vsync_ns'])
    with (folder / 'completed-frames.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['pid', 'window', 'intended_vsync_ns', 'frame_completed_ns', 'duration_ms'])
        for frame in frames:
            writer.writerow([frame[key] for key in ('pid', 'window', 'intended_vsync_ns', 'frame_completed_ns', 'duration_ms')])
    save(folder / 'conflicting-frames.json', conflicts)
    save(folder / 'total-pss-samples.json', pss)
    durations = [frame['duration_ms'] for frame in frames]
    memory = [sample['total_pss_kib'] for sample in pss]
    observed_pids = [sample.get('pid') for sample in samples['samples']]
    live_pids = [pid for index, pid in enumerate(observed_pids) if pid is not None
                 and (index == 0 or pid != observed_pids[index - 1])]
    commands = [command for sample in samples['samples'] for command in sample['commands'].values()]
    return {
        'frames': {'count': len(durations), 'p50_ms': quantile(durations, .50), 'p95_ms': quantile(durations, .95),
                   'p99_ms': quantile(durations, .99), 'max_ms': max(durations, default=None),
                   'fraction_over_display_period': sum(value > period_ns / 1e6 for value in durations) / len(durations)
                   if durations and period_ns else None},
        'total_pss': {'sample_count': len(memory), 'median_kib': statistics.median(memory) if memory else None,
                      'max_kib': max(memory, default=None)},
        'per_pid': by_pid, 'observed_live_pid_segments': live_pids,
        'observed_pid_changes': sum(left != right for left, right in zip(live_pids, live_pids[1:])),
        'no_pid_slots': [sample['slot'] for sample in samples['samples'] if sample.get('pid') is None],
        'invalid_observations': invalid, 'conflicting_completed_keys': len({tuple(item['key']) for item in conflicts}),
        'ring_buffer_no_overlap_possible_gaps': no_overlap,
        'sampling': {'sample_count': len(samples['samples']), 'missed_slots': samples['missed_slots'],
                     'command_count': len(commands), 'command_seconds': sum(item['duration_seconds'] for item in commands),
                     'command_duration_p95_seconds': quantile([item['duration_seconds'] for item in commands], .95),
                     'meminfo_seconds': sum(sample['commands']['meminfo']['duration_seconds'] for sample in samples['samples']
                                            if 'meminfo' in sample['commands']),
                     'failed_commands': [item for item in commands if item['exit_code'] != 0],
                     'ended_before_method_stop': samples['ended_before_method_stop'],
                     'errors': samples['errors'], 'completed': samples['completed']},
    }


def refresh_period(commands):
    record, text = commands.adb('shell', 'dumpsys', 'SurfaceFlinger', '--latency', checked=False)
    first = text.strip().splitlines()[:1]
    return int(first[0]) if record['exit_code'] == 0 and first and re.fullmatch('[0-9]+', first[0]) and 0 < int(first[0]) < 10**9 else None


def phase(label, variant, prepared, identity, expected_order):
    folder = OUT / label
    folder.mkdir()
    commands = Commands(folder / 'commands')
    result = {'label': label, 'variant': variant, 'diagnostic_only': True, 'accepted': False,
              'diagnostic_completed': False, 'errors': []}
    samples, stop, thread = {}, threading.Event(), None
    pin = prepared[variant]['pin']
    try:
        _, result['boot_id_before'] = commands.adb('shell', 'cat', '/proc/sys/kernel/random/boot_id')
        result['display_period_before_ns'] = refresh_period(commands)
        for package in (TEST, HELPER, APP):
            commands.adb('shell', 'am', 'force-stop', package, checked=False)
            commands.adb('uninstall', package, checked=False)
        _, packages = commands.adb('shell', 'pm', 'list', 'packages')
        require(all('package:' + package not in packages.splitlines() for package in (APP, HELPER, TEST)),
                'Phase did not start with all three packages absent')
        installed = {}
        for name in APK_NAMES:
            source = OUT / (variant if name == APK_NAMES[0] else 'A') / name
            commands.adb('install', '-t', '-g', str(source), timeout=180)
            _, paths = commands.adb('shell', 'pm', 'path', PACKAGES[name])
            paths = paths.strip().splitlines()
            require(len(paths) == 1 and paths[0].startswith('package:/'), 'Installed package is not a monolithic original APK')
            pulled = folder / ('installed-' + name)
            commands.adb('pull', paths[0][8:], str(pulled), timeout=90)
            installed[name] = sha(pulled)
            require(installed[name] == sha(source), 'Installed original APK hash differs')
            pulled.unlink()
        result['installed_sha256'] = installed
        _, instrumentations = commands.adb('shell', 'pm', 'list', 'instrumentation')
        require('instrumentation:' + RUNNER + ' (target=' + HELPER + ')' in instrumentations.splitlines(),
                'Installed original helper/test target differs')
        commands.adb('shell', 'pm', 'clear', APP)
        commands.adb('shell', 'pm', 'clear', HELPER)
        commands.adb('shell', 'pm', 'clear', TEST)
        commands.adb('shell', 'rm', '-rf', REMOTE)
        commands.adb('shell', 'mkdir', '-p', '/sdcard/Download')
        for name, fixture in prepared['A']['fixtures'].items():
            if Path(name).suffix not in ('.epub', '.pdf', '.txt'):
                continue
            commands.adb('push', str(OUT / 'A/fixtures' / name), '/sdcard/Download/' + name)
            _, output = commands.adb('shell', 'sha256sum', '/sdcard/Download/' + name)
            require(output.split()[0] == fixture['sha256'], 'Device fixture bytes differ')
        for setting in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
            commands.adb('shell', 'settings', 'put', 'global', setting, '0')
            _, value = commands.adb('shell', 'settings', 'get', 'global', setting)
            require(value.strip() in ('0', '0.0'), 'Animation scale differs')
        commands.adb('shell', 'settings', 'put', 'global', 'hide_error_dialogs', '1')
        commands.adb('shell', 'settings', 'put', 'global', 'anr_show_background', '0')
        commands.adb('logcat', '-c')
        commands.adb('shell', 'dumpsys', 'gfxinfo', APP, 'reset', checked=False)
        argv = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'disableAnalytics', 'true',
                '-e', 'class', PLAN['method'], '-e', 'exr_suite', 'walkthrough',
                '-e', 'exr_source_sha', pin['source_sha'], '-e', 'exr_run_id', identity['run_id'],
                '-e', 'exr_attempt', identity['attempt'], '-e', 'apk_sha256', installed[APK_NAMES[0]],
                '-e', 'test_apk_sha256', installed[APK_NAMES[2]], RUNNER]
        origin = time.monotonic()
        result['method_start_monotonic'] = origin
        thread = threading.Thread(target=sampler, args=(commands, stop, samples, origin), daemon=True)
        thread.start()
        instrumentation, unused = commands.run(argv, timeout=PLAN['phase_timeout_seconds'])
        result['instrumentation'] = instrumentation
        result['method_end_monotonic'] = time.monotonic()
        stop.set()
        thread.join(timeout=30)
        require(not thread.is_alive(), 'Sampler did not stop within bounded command window')
        # One bounded tail dump retains completed frames from the last polling interval.
        tail = {'slot': 'tail', 'after_method': True, 'start_monotonic': time.monotonic(), 'commands': {}}
        samples['samples'].append(tail)
        capture_sample(commands, tail)
        samples['raw_bytes'] += sum(item['stdout_bytes'] + item['stderr_bytes'] for item in tail['commands'].values())
        if instrumentation.get('timed_out'):
            commands.adb('shell', 'am', 'force-stop', HELPER, checked=False)
            commands.adb('shell', 'am', 'force-stop', APP, checked=False)
        commands.adb('logcat', '-d', '-v', 'monotonic', '-s', 'EXRHost:I', 'EXRWalkthrough:I', 'ActivityTaskManager:I', '*:S')
        commands.adb('pull', REMOTE, str(folder / 'device'), timeout=120)
        validation = load(folder / 'device/validation.json')
        validate_cases(validation, expected_order)
        require(validation['source_sha'] == pin['source_sha'] and validation['run_id'] == identity['run_id']
                and validation['attempt'] == identity['attempt'] and validation['apk_sha256'] == installed[APK_NAMES[0]]
                and validation['test_apk_sha256'] == installed[APK_NAMES[2]], 'Fresh original case evidence identity differs')
        result['original_validation_summary'] = validation['summary']
        result['original_failures'] = [case for case in validation['cases'] if case['status'] != 'pass']
        _, result['boot_id_after'] = commands.adb('shell', 'cat', '/proc/sys/kernel/random/boot_id')
        result['display_period_after_ns'] = refresh_period(commands)
        require(result['boot_id_after'] == result['boot_id_before'], 'Emulator rebooted inside phase')
        require(result['display_period_before_ns'] == result['display_period_after_ns'], 'Display period changed inside phase')
        result['diagnostic_completed'] = not instrumentation.get('timed_out') and samples.get('completed', False)
    except Exception as error:
        result['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=30)
        if samples:
            save(folder / 'sampling.json', samples)
            if thread is None or not thread.is_alive():
                try:
                    result['measurements'] = analyse(folder, samples, result.get('display_period_before_ns'))
                except Exception as error:
                    result['errors'].append('Analysis ' + type(error).__name__ + ': ' + str(error))
        commands.persist()
        save(folder / 'phase.json', result)
    return result


def run():
    identity = cloud()
    prepared = load(OUT / 'prepared.json')
    require(prepared['prepared'] and not prepared['errors'] and all(prepared[key] == value for key, value in identity.items()),
            'Preparation is not from this diagnostic run/source')
    require(load(OUT / 'plan.json') == PLAN, 'Predeclared comparison plan changed')
    report = {**identity, 'diagnostic_only': True, 'accepted': False, 'diagnostic_completed': False,
              'single_factor_interpretation_allowed': False, 'inconclusive_reasons': [], 'phases': [], 'paired_differences': None}
    environment = Commands(OUT / 'environment')
    try:
        for argv in (['adb', 'version'], ['adb', 'shell', 'getprop'], ['adb', 'shell', 'wm', 'size'],
                     ['adb', 'shell', 'wm', 'density'], ['adb', 'shell', 'dumpsys', 'display'],
                     ['adb', 'shell', 'dumpsys', 'SurfaceFlinger'], ['adb', 'shell', 'settings', 'list', 'global'],
                     ['adb', 'shell', 'cat', '/proc/sys/kernel/random/boot_id'], ['uname', '-a'], ['lscpu']):
            environment.run(argv, checked=True)
        _, api = environment.adb('shell', 'getprop', 'ro.build.version.sdk')
        require(api.strip() == '34', 'API34 emulator required')
        _, abi = environment.adb('shell', 'getprop', 'ro.product.cpu.abi')
        require(abi.strip() == 'x86_64', 'x86_64 emulator required')
        expected_order = validate_cases(load(OUT / 'A/original-validation.json'))
        for label, variant in PLAN['sequence']:
            report['phases'].append(phase(label, variant, prepared, identity, expected_order))
            save(OUT / 'diagnostic.json', report)
        report['diagnostic_completed'] = all(item['diagnostic_completed'] and not item['errors'] for item in report['phases'])
        reasons = report['inconclusive_reasons']
        if not report['diagnostic_completed']:
            reasons.append('One or more original walkthrough collections incomplete')
        if prepared['confounds']:
            reasons.append('Font/native bytes differ: ' + ', '.join(prepared['confounds']))
        boots = {item.get('boot_id_before') for item in report['phases']} | {item.get('boot_id_after') for item in report['phases']}
        if len(boots) != 1 or None in boots:
            reasons.append('Not one uninterrupted emulator boot')
        periods = {item.get('display_period_before_ns') for item in report['phases']} | {item.get('display_period_after_ns') for item in report['phases']}
        if len(periods) != 1 or None in periods:
            reasons.append('Unknown or varying display refresh period')
        for item in report['phases']:
            measurements = item.get('measurements', {})
            if item['variant'] == 'B' and item.get('original_validation_summary', {}).get('failed', 1):
                reasons.append(item['label'] + ': old original 45-step suite failed; cannot support adopting software layer')
            if measurements.get('frames', {}).get('count', 0) < PLAN['minimum_usable_frames_per_phase']:
                reasons.append(item['label'] + ': fewer than 100 ordinary frames')
            if not measurements.get('total_pss', {}).get('sample_count'):
                reasons.append(item['label'] + ': no full-process TOTAL PSS samples')
            if measurements.get('conflicting_completed_keys'):
                reasons.append(item['label'] + ': conflicting completed-frame identities')
            if measurements.get('sampling', {}).get('errors'):
                reasons.append(item['label'] + ': external sampler failed')
            if measurements.get('sampling', {}).get('ended_before_method_stop'):
                reasons.append(item['label'] + ': sampler ended before original method')
        report['single_factor_interpretation_allowed'] = not reasons
        if not reasons:
            phases = {item['label']: item['measurements'] for item in report['phases']}
            report['paired_differences'] = {}
            for a, b in (('A1', 'B1'), ('A2', 'B2')):
                report['paired_differences'][b + '_minus_' + a] = {
                    group: {metric: phases[b][group][metric] - phases[a][group][metric]
                            for metric in phases[a][group]} for group in ('frames', 'total_pss')}
    except Exception as error:
        report['inconclusive_reasons'].append(type(error).__name__ + ': ' + str(error))
    finally:
        environment.persist()
        save(OUT / 'diagnostic.json', report)
    print(json.dumps({'diagnostic_completed': report['diagnostic_completed'], 'accepted': False,
                      'inconclusive_reasons': report['inconclusive_reasons'],
                      'phases': [{key: item.get(key) for key in ('label', 'variant', 'original_validation_summary',
                                  'original_failures', 'display_period_before_ns', 'measurements', 'errors')}
                                 for item in report['phases']],
                      'paired_differences': report['paired_differences']}))
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    require(len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'run'), 'Use prepare or run')
    if sys.argv[1] == 'prepare':
        prepare()
    else:
        raise SystemExit(run())
