"""Actions-only original-APK control and trace/cache differential, never acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import zipfile

from authenticate import BASE, ROOT, OUT, need, sha

EVIDENCE = OUT / 'evidence'
PACKAGE = 'org.exreader.host'
FIXTURES = ROOT / 'build/android-navigation/fixtures'
SOURCE = ROOT / 'tests/reader_android_navigation_freshness'


def command(argv, log, timeout=600, check=True, env=None):
    log = Path(log); log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('wb') as stream:
        process = subprocess.run(list(map(str, argv)), cwd=ROOT, env=env,
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if check:
        if process.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-80:]), flush=True)
        need(process.returncode == 0, f'command failed; retained {log.relative_to(ROOT)}')
    return process.returncode


def adb(*args):
    return subprocess.check_output(['adb', *map(str, args)], stderr=subprocess.STDOUT, timeout=90)


def describe_apk(path, label):
    path = Path(path)
    certificate = EVIDENCE / f'{label}-certificate.txt'
    signer = Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0/apksigner'
    command([signer, 'verify', '--print-certs', path], certificate)
    lines = certificate.read_text().splitlines()
    certificates = [line.split(': ', 1)[1] for line in lines if 'certificate SHA-256 digest: ' in line]
    need(certificates, 'APK has no authenticated signer certificate digest')
    with zipfile.ZipFile(path) as apk:
        native = [{'path': item.filename, 'bytes': item.file_size,
                   'sha256': hashlib.sha256(apk.read(item)).hexdigest()}
                  for item in apk.infolist() if item.filename.startswith('lib/') and item.filename.endswith('.so')]
    return {'sha256': sha(path), 'bytes': path.stat().st_size,
            'certificate_sha256': certificates, 'native_libraries': native}


def run_group(name, runner, cache=None):
    target = EVIDENCE / name; target.mkdir(exist_ok=True)
    env = dict(os.environ)
    if cache:
        env['NAV_DIAGNOSTIC_CACHE'] = cache
    code = command([sys.executable, runner, '--fixtures', FIXTURES, '--output', target],
                   target / 'runner.log', timeout=1850, check=False, env=env)
    # Retain private reports before the next complete original runner clears data.
    for phase in ('first', 'reopen'):
        for prefix in ('navigation-ui-', 'navigation-trace-'):
            process = subprocess.run(['adb', 'exec-out', 'run-as', PACKAGE, 'cat',
                                      'files/' + prefix + phase + '.json'],
                                     capture_output=True, timeout=90)
            stem = prefix + phase
            (target / (stem + '.read-stdout.txt')).write_bytes(process.stdout)
            (target / (stem + '.read-stderr.txt')).write_bytes(process.stderr)
            (target / (stem + '.read-exit.txt')).write_text(str(process.returncode) + '\n')
            if process.returncode == 0:
                try:
                    report = json.loads(process.stdout)
                except (ValueError, UnicodeError):
                    # adb exec-out may return zero even when remote cat failed.
                    (target / (prefix + phase + '.unavailable.txt')).write_bytes(process.stdout)
                else:
                    need(isinstance(report, dict), 'private report is not a JSON object')
                    (target / (prefix + phase + '.json')).write_bytes(process.stdout)
    result_path = target / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    reports = []
    for phase in ('first', 'reopen'):
        path = target / ('navigation-ui-' + phase + '.json')
        if path.exists():
            report = json.loads(path.read_text())
            reports.append({'phase': phase, 'passed': report['passed'], 'count': report['count'],
                            'failed_check': report.get('failed_check'), 'failure': report.get('failure')})
    item = {'name': name, 'runner_exit': code, 'original_full_suite_passed':
            bool(code == 0 and result and result['accepted'] and result['checks'] == 18),
            'cache_mode': cache, 'reports': reports}
    print(json.dumps(item, ensure_ascii=False), flush=True)
    return item


def gradle(skip, targets):
    # Reuse the producer's exact baseline/OFF flag vector, not the raw candidate.
    workflow = (ROOT / '.github/workflows/reader-android-raw3.yml').read_text()
    import shlex
    lines = [line.strip() for line in workflow.splitlines()
             if line.strip().startswith('gradle ') and '-PexrTestRunner=org.exreader.host.NavigationUiTest ' in line]
    need(len(lines) == 1, 'original baseline Gradle invocation is ambiguous')
    argv = shlex.split(lines[0].split(' 2>&1 | tee ', 1)[0].replace('$PWD', str(ROOT)))
    argv = argv[:argv.index(':app:assembleDebugAndroidTest')]
    need(not any('exrSelectorBytes' in value for value in argv), 'baseline must retain default OFF')
    argv += ['-I', str(SOURCE / 'probe.gradle'), '-PdiagSkipNative=' + str(skip).lower(), *targets]
    (EVIDENCE / ('probe-build-command.json' if skip else 'rebuilt-build-command.json')).write_text(
        json.dumps(argv, indent=2) + '\n')
    return argv


def prepare_resources():
    ca = ROOT / 'build/webdav-android/fixture/public/ca.crt'
    target = ROOT / 'tests/reader_host_session_android/debug/res/raw/host_sync_fixture_ca.crt'
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ca, target)
    # Only original authenticated assets/JNI; no fixture generation or SDK rebuild.
    with zipfile.ZipFile(OUT / 'original-baseline.apk') as apk:
        for name in ('assets/Reader.otf', 'assets/OFL.txt', 'assets/reader-catalog-v1.json',
                     'lib/x86_64/libexreader_jni.so'):
            need(name in apk.namelist(), 'required original APK asset is absent: ' + name)
            relative = name.replace('lib/x86_64/', 'jniLibs/x86_64/')
            path = ROOT / 'examples/android/app/src/main' / relative
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(apk.read(name))


def rebuild_pair():
    toolchain = Path(os.environ['ANDROID_HOME']) / 'ndk/27.2.12479018/build/cmake/android.toolchain.cmake'
    stage = ROOT / 'build/webdav-android/stage-release'
    command(['cmake', '-S', 'extras/webdav', '-B', 'build/navigation-freshness/webdav-release', '-G', 'Ninja',
             '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-26',
             '-DANDROID_STL=c++_static', '-DCMAKE_BUILD_TYPE=Release', '-DEXR_WEBDAV_ANDROID_TESTING=OFF',
             '-DCMAKE_INSTALL_PREFIX=' + str(stage)], EVIDENCE / 'webdav-configure.log')
    command(['cmake', '--build', 'build/navigation-freshness/webdav-release', '--parallel', '2', '--target', 'install'],
            EVIDENCE / 'webdav-build.log')
    command(gradle(False, [':app:assembleDebug', ':app:assembleDebugAndroidTest']),
            EVIDENCE / 'rebuilt-baseline-build.log', timeout=1800)
    host = ROOT / 'examples/android/app/build/outputs/apk/debug/app-debug.apk'
    probe = ROOT / 'examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'
    configs = list((ROOT / 'examples/android/app/build/generated/source/buildConfig').rglob('BuildConfig.java'))
    need(len(configs) == 1 and 'READER_SELECTOR_BYTES_CANDIDATE = false;' in configs[0].read_text(),
         'rebuilt owner lacks explicit baseline/OFF BuildConfig')
    caches = list((ROOT / 'examples/android/app/.cxx').rglob('CMakeCache.txt'))
    need(caches and all('EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=OFF' in path.read_text() for path in caches),
         'rebuilt native owner does not prove selector candidate OFF')
    for number, path in enumerate(caches):
        shutil.copyfile(path, EVIDENCE / f'rebuilt-cmake-{number}.txt')
    shutil.copyfile(configs[0], EVIDENCE / 'rebuilt-BuildConfig.java')
    shutil.copyfile(host, EVIDENCE / 'rebuilt-baseline.apk'); shutil.copyfile(probe, EVIDENCE / 'rebuilt-probe.apk')
    identities = {'scope': 'fixed bd8 source rebuilt baseline/OFF host + trace probe signed together',
                  'same_original_apk': False, 'owner_source': BASE,
                  'host': describe_apk(host, 'rebuilt-host'), 'probe': describe_apk(probe, 'rebuilt-probe')}
    need(identities['host']['certificate_sha256'] == identities['probe']['certificate_sha256'],
         'rebuilt pair signer differs')
    return host, probe, identities


def stage_inventory():
    rows = []
    for name in ('session-android/sdk-stage', 'session-android/product-stage',
                 'session-android/sideload-stage', 'android-search/search-stage',
                 'android-navigation/navigation-stage', 'android-preferences/preferences-stage'):
        stage = ROOT / 'build' / name
        need(stage.is_dir(), 'authenticated installed stage absent: ' + name)
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                rows.append({'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                             'sha256': sha(path)})
    return rows


def compare_cache(group):
    output = []
    for phase in ('first', 'reopen'):
        path = EVIDENCE / group / ('navigation-trace-' + phase + '.json')
        if not path.exists():
            continue
        trace = json.loads(path.read_text()); events = trace['events']
        for before, after in zip(events, events[1:]):
            if before['action'] != 'before-cache' or after['action'] != 'after-cache':
                continue
            if before.get('window_id') != after.get('window_id') or before['label'] != after['label']:
                continue
            label = before['label']
            def matches(event):
                return [row for row in event['rows'] if label in row['text'] and row['visible'] and row['enabled']]
            left, right = matches(before), matches(after)
            if left != right or before.get('ready') != after.get('ready'):
                output.append({'phase': phase, 'before_sequence': before['sequence'],
                               'after_sequence': after['sequence'], 'window_id': before.get('window_id'),
                               'label': label, 'check': before['check'],
                               'cache_return': after['clear_cache_return'],
                               'ready_before': before.get('ready'), 'ready_after': after.get('ready'),
                               'matches_before': left, 'matches_after': right})
    return output


def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    original_host, original_probe = OUT / 'original-baseline.apk', OUT / 'original-navigation.apk'
    original = {'host': describe_apk(original_host, 'original-host'),
                'probe': describe_apk(original_probe, 'original-probe')}
    need(original['host']['certificate_sha256'] == original['probe']['certificate_sha256'], 'original pair differs')
    groups, rebuilt, traced = [], None, None
    stages = stage_inventory()
    try:
        adb('install', '-t', original_host); adb('install', '-t', original_probe)
        groups.append(run_group('original-control', ROOT / 'tests/reader_android_navigation/run_ui.py'))
        prepare_resources()
        command(gradle(True, [':app:assembleDebugAndroidTest']), EVIDENCE / 'trace-probe-build.log', timeout=1200)
        probe = ROOT / 'examples/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'
        shutil.copyfile(probe, EVIDENCE / 'trace-probe.apk')
        traced = describe_apk(probe, 'trace-probe')
        adb('uninstall', PACKAGE + '.test'); adb('install', '-t', probe)
        groups.append(run_group('original-apk-trace', OUT / 'projected_runner.py', 'trace'))
        # A genuine signature denial must be retained, never inferred from a test failure.
        first = EVIDENCE / 'original-apk-trace/first-instrumentation.txt'
        denial = first.read_text(errors='replace') if first.exists() else ''
        mismatch = ('Permission Denial' in denial or 'SecurityException' in denial) and (
            'signature' in denial.lower() or 'not signed' in denial.lower())
        if mismatch:
            need(not groups[-1]['reports'], 'signature denial conflicts with an actual suite report')
            need(sha(original_host) == original['host']['sha256'], 'original APK bytes changed')
            host, probe, rebuilt = rebuild_pair()
            adb('uninstall', PACKAGE + '.test'); adb('uninstall', PACKAGE)
            adb('install', '-t', host); adb('install', '-t', probe)
            groups.append(run_group('rebuilt-pair-trace', OUT / 'projected_runner.py', 'trace'))
            groups.append(run_group('rebuilt-pair-fresh', OUT / 'projected_runner.py', 'fresh'))
        else:
            need(groups[-1]['reports'], 'instrumentation did not start; no signature-denial fallback justified')
            groups.append(run_group('original-apk-fresh', OUT / 'projected_runner.py', 'fresh'))
        need(stage_inventory() == stages, 'authenticated installed SDK or product stage changed')
        subprocess.run(['git', 'diff', '--exit-code'], cwd=ROOT, check=True)
    finally:
        primary_error = traceback.format_exc() if sys.exc_info()[0] is not None else None
        comparisons, collector_errors = {}, []
        for group in groups:
            try:
                comparisons[group['name']] = compare_cache(group['name'])
            except Exception as error:
                collector_errors.append({'group': group['name'], 'type': type(error).__name__, 'error': str(error)})
        result = {'diagnostic_source': os.environ['GITHUB_SHA'], 'producer_source': BASE,
                  'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                  'original': original, 'trace_probe': traced, 'rebuilt': rebuilt,
                  'authenticated_stages': stages, 'groups': groups,
                  'cache_differentials': comparisons, 'primary_error': primary_error,
                  'collector_errors': collector_errors,
                  'accepted': False, 'complete_product': False, 'physical_device': False,
                  'interpretation': 'Full original suite results and paired cache observations only; no product grant.'}
        (EVIDENCE / 'diagnostic.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'diagnostic_source': result['diagnostic_source'], 'accepted': False,
                          'rebuilt_scope_used': rebuilt is not None, 'groups': groups,
                          'cache_differential_counts': {key: len(value) for key, value in result['cache_differentials'].items()},
                          'cache_differential_examples': {key: value[:10] for key, value in result['cache_differentials'].items()}},
                         ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
