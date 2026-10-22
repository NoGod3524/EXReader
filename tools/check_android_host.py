#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Static ownership/source checks for the Android host package, plus validation of
the cloud emulator evidence (per-case JSON, screenshots, native log, build)."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
APP = ROOT / 'examples/android/app/src/main'
TEST = ROOT / 'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java'
WORKFLOW = ROOT / '.github/workflows/wp13-android.yml'
DOC = ROOT / 'docs/WP13-ANDROID.md'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return path.read_text(encoding='utf-8')


def static_checks():
    problems = []
    required = [
        APP / 'AndroidManifest.xml',
        APP / 'res/layout/activity_main.xml',
        APP / 'res/values/ids.xml',
        APP / 'java/org/exreader/host/MainActivity.java',
        APP / 'java/org/exreader/host/ReaderView.java',
        APP / 'java/org/exreader/host/NativeLibrary.java',
        APP / 'java/org/exreader/host/ReflowSession.java',
        APP / 'java/org/exreader/host/FixedSession.java',
        APP / 'java/org/exreader/EXReader.java',
        APP / 'java/org/exreader/EXReaderException.java',
        APP / 'cpp/exreader_host_jni.c',
        APP / 'cpp/CMakeLists.txt',
        ROOT / 'examples/android/app/build.gradle',
        ROOT / 'examples/android/uitest/build.gradle',
        TEST,
        WORKFLOW,
        DOC,
        ROOT / 'tools/build_android_host.py',
    ]
    for path in required:
        if not path.is_file():
            problems.append('missing file: ' + str(path.relative_to(ROOT)))
    if problems:
        return problems, {}

    activity = read(APP / 'java/org/exreader/host/MainActivity.java')
    view = read(APP / 'java/org/exreader/host/ReaderView.java')
    native = read(APP / 'java/org/exreader/host/NativeLibrary.java')
    bridge = read(APP / 'cpp/exreader_host_jni.c')
    app_gradle = read(ROOT / 'examples/android/app/build.gradle')
    test = read(TEST)
    workflow = read(WORKFLOW)
    doc = read(DOC)
    layout = read(APP / 'res/layout/activity_main.xml')

    for needle in ['newSingleThreadExecutor', 'onSaveInstanceState', 'takePersistableUriPermission',
                   'MAX_INPUT_BYTES', 'saveProgress', 'setPosition', 'onStop']:
        if needle not in activity:
            problems.append('MainActivity lacks ' + needle)
    for needle in ['onTouchEvent', 'AccessibilityNodeProvider', 'getAccessibilityNodeProvider',
                   'AccessibilityNodeInfo.obtain(ReaderView.this']:
        if needle not in view:
            problems.append('ReaderView lacks ' + needle)
    if 'System.loadLibrary("exreader_host")' not in native:
        problems.append('NativeLibrary does not load exreader_host')
    for symbol in ['exr_library_import_file_unique', 'exr_library_note', 'exr_library_fixed_note',
                   'exr_library_progress', 'exr_anchor_create', 'exr_library_notes']:
        if symbol not in bridge:
            problems.append('JNI bridge lacks ' + symbol)
    if 'androidx' in app_gradle:
        problems.append('app module must not add AndroidX UI dependencies')
    if "abiFilters 'x86_64'" not in app_gradle:
        problems.append('app must pin the x86_64 emulator ABI')
    if 'ndkVersion' not in app_gradle:
        problems.append('app must pin the NDK version')
    for control in ['import_button', 'book_list', 'reader_view', 'page_label', 'select_button',
                    'copy_button', 'annotate_button', 'notes_button', 'note_list', 'status_text',
                    'cancel_button', 'rebuild_view']:
        if '@+id/' + control not in layout:
            problems.append('layout lacks ' + control)
        if control not in activity:
            problems.append('activity does not bind ' + control)

    ids = re.findall(r'step\("([a-z0-9_]+)"', test)
    if len(ids) < 20:
        problems.append('walkthrough has fewer than 20 cases: %d' % len(ids))
    if len(set(ids)) != len(ids):
        problems.append('walkthrough case ids are not unique')
    for needle in ['force-stop', 'setOrientationLeft', 'takeScreenshot', 'validation.json',
                   'physical_device_execution']:
        if needle not in test:
            problems.append('walkthrough lacks ' + needle)
    for needle in ['android-emulator-runner', 'api-level: 34', 'arch: x86_64', 'am instrument',
                   'upload-artifact', 'workflow_dispatch', 'x86_64']:
        if needle not in workflow:
            problems.append('workflow lacks ' + needle)
    if 'physical_device_execution' not in doc or 'x86_64' not in doc:
        problems.append('documentation must state the device scope and ABI')
    stats = {'cases_declared': len(ids), 'unique_cases': len(set(ids))}
    return problems, stats


def evidence_checks(evidence, build_path, api, target, image, run_id, run_url, workflow_name):
    problems = []
    stats = {}
    build_file = build_path
    if not build_file.is_file():
        return ['missing build.json: ' + str(build_file)], stats
    build = json.loads(build_file.read_text())
    stats['build_sdk'] = build.get('sdk_version')
    stats['build_abi'] = build.get('abi')
    stats['build_ndk'] = build.get('ndk')
    stats['build_gradle'] = build.get('gradle')
    if build.get('abi') != 'x86_64':
        problems.append('build ABI is not x86_64')
    if build.get('sdk_version') != '3.40.0':
        problems.append('unexpected SDK version: %s' % build.get('sdk_version'))
    if build.get('abi_version') != 1:
        problems.append('unexpected ABI epoch')
    native = build.get('native') or {}
    for name in ['lib/x86_64/libexreader.so', 'lib/x86_64/libexreader_jni.so']:
        entry = native.get(name)
        if not entry:
            problems.append('build.json lacks native entry ' + name)
        elif entry.get('machine') != 62:
            problems.append(name + ' is not x86_64')
    artifacts = build.get('artifacts') or {}
    apk = artifacts.get('app-debug.apk') or {}
    apk_copy = evidence / 'artifacts/app-debug.apk'
    if apk_copy.is_file() and apk.get('sha256'):
        if sha256(apk_copy) != apk['sha256']:
            problems.append('evidence APK hash does not match build.json')
    else:
        problems.append('evidence is missing the packaged APK or its hash')

    validation_file = evidence / 'device/validation.json'
    if not validation_file.is_file():
        return problems + ['missing device validation.json'], stats
    validation = json.loads(validation_file.read_text())
    stats['cases'] = len(validation.get('cases') or [])
    stats['api'] = validation.get('api')
    stats['abi'] = validation.get('abi')
    stats['model'] = validation.get('model')
    if validation.get('physical_device_execution') is not False:
        problems.append('physical_device_execution must be false')
    if validation.get('device_is_emulator') is not True:
        problems.append('run did not identify an emulator')
    if validation.get('abi') != 'x86_64':
        problems.append('device ABI is not x86_64: %s' % validation.get('abi'))
    if validation.get('api') != api:
        problems.append('device API %s does not match requested API %s' % (validation.get('api'), api))
    cases = validation.get('cases') or []
    if len(cases) < 20:
        problems.append('fewer than 20 executed cases: %d' % len(cases))
    failed = [case for case in cases if case.get('status') != 'pass']
    if failed:
        problems.append('failed cases: ' + ', '.join(case.get('id', '?') for case in failed))
    summary = validation.get('summary') or {}
    if summary.get('total') != len(cases) or summary.get('passed') != len(cases) - len(failed):
        problems.append('summary does not match the case list')
    for case in cases:
        shot = case.get('screenshot')
        if not shot:
            problems.append('case has no screenshot: ' + str(case.get('id')))
        elif not (evidence / 'device' / shot).is_file():
            problems.append('missing screenshot: ' + shot)
    case_dir = evidence / 'device/cases'
    if not case_dir.is_dir() or len(list(case_dir.glob('*.json'))) < len(cases):
        problems.append('per-case JSON files are incomplete')

    logcat = evidence / 'logcat.txt'
    if logcat.is_file():
        log = logcat.read_text(errors='replace')
        pages = log.count('metric {"event":"page"')
        stats['page_metrics'] = pages
        if pages < 12:
            problems.append('native page metrics are missing or too few: %d' % pages)
        if 'handle open book=' not in log:
            problems.append('native handle open logs are missing')
        if 'handle close book=' not in log:
            problems.append('native handle close logs are missing')
        if ('FATAL EXCEPTION' in log or 'UnsatisfiedLinkError' in log
                or 'Fatal signal' in log):
            problems.append('logcat contains a fatal native/app failure')
    else:
        problems.append('missing logcat.txt')

    instrumentation = evidence / 'instrumentation.txt'
    if instrumentation.is_file():
        text = instrumentation.read_text(errors='replace')
        if 'OK (1 test)' not in text:
            problems.append('instrumentation output does not report a passing test')
        if 'INSTRUMENTATION_FAILED' in text or 'FAILURES!!!' in text:
            problems.append('instrumentation output reports a failure')
    else:
        problems.append('missing instrumentation.txt')

    if not run_id:
        problems.append('workflow run id is required for the evidence')
    merged = {
        'schema': 1,
        'package': validation.get('package', 'org.exreader.host'),
        'branch': build.get('branch'),
        'source_sha': build.get('source_sha'),
        'physical_device_execution': False,
        'build': {key: build.get(key) for key in
                  ['sdk_version', 'core_version', 'library_version', 'abi_version', 'library_schema',
                   'abi', 'android_platform', 'compile_sdk', 'min_sdk', 'target_sdk', 'ndk', 'cmake',
                   'agp', 'gradle', 'artifacts', 'native', 'fixtures']},
        'font': build.get('font'),
        'device': {
            'api': validation.get('api'), 'abi': validation.get('abi'),
            'model': validation.get('model'), 'hardware': validation.get('hardware'),
            'is_emulator': validation.get('device_is_emulator'),
        },
        'emulator': {'api': api, 'target': target, 'image': image, 'arch': 'x86_64'},
        'run': {'workflow': workflow_name, 'id': run_id, 'url': run_url},
        'cases': cases,
        'summary': {'total': len(cases), 'passed': len(cases) - len(failed),
                    'failed': len(failed), 'skipped': 0},
        'limitations': validation.get('limitations') or [],
        'evidence': {
            'instrumentation': 'evidence/instrumentation.txt',
            'logcat': 'evidence/logcat.txt',
            'device_cases': 'evidence/device/cases',
            'screenshots': 'evidence/device/shots',
            'apk': 'evidence/artifacts/app-debug.apk',
        },
        'static': stats,
    }
    if failed:
        merged['failed_cases'] = [case.get('id') for case in failed]
    return problems, merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--api', type=int, default=34)
    parser.add_argument('--target', default='default')
    parser.add_argument('--image', default='system-images;android-34;default;x86_64')
    parser.add_argument('--run-id', default='')
    parser.add_argument('--run-url', default='')
    parser.add_argument('--workflow', default='wp13-android')
    args = parser.parse_args()
    problems, stats = static_checks()
    merged = stats
    if args.evidence:
        if not args.build:
            parser.error('--build is required with --evidence')
        more, merged_evidence = evidence_checks(args.evidence, args.build, args.api, args.target,
                                                args.image, args.run_id, args.run_url, args.workflow)
        problems.extend(more)
        if isinstance(merged_evidence, dict):
            merged = merged_evidence
            merged.setdefault('static', stats)
    report = {'ok': not problems, 'problems': problems, 'summary': merged}
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n')
    if problems:
        sys.exit(1)


if __name__ == '__main__':
    main()
