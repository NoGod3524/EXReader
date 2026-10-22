#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check Android ownership sources and fail closed on complete cloud evidence."""
import argparse
import json
import os
from pathlib import Path
import re

from android_host_evidence import (ROOT, WALKTHROUGH_IDS, check_evidence, check_identity,
    cloud_identity, load, require, sha256)

APP = ROOT/'examples/android/app/src/main'
TEST = ROOT/'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java'
REVIEW = TEST.with_name('HostReviewTest.java')
WORKFLOW = ROOT/'.github/workflows/wp13-android.yml'
DOC = ROOT/'docs/WP13-ANDROID.md'


def static_checks():
    problems = []
    required = [APP/'AndroidManifest.xml', APP/'res/layout/activity_main.xml', APP/'res/values/ids.xml',
        *[APP/('java/org/exreader/host/' + name + '.java') for name in
          ('MainActivity', 'ReaderView', 'NativeLibrary', 'ReflowSession', 'FixedSession')],
        APP/'java/org/exreader/EXReader.java', APP/'java/org/exreader/EXReaderException.java',
        APP/'cpp/exreader_host_jni.c', APP/'cpp/CMakeLists.txt', ROOT/'examples/android/app/build.gradle',
        ROOT/'examples/android/uitest/build.gradle', ROOT/'examples/android/ci/emulator.sh',
        TEST, REVIEW, WORKFLOW, DOC, ROOT/'tools/build_android_host.py', ROOT/'tools/run_android_host_evidence.py']
    for path in required:
        if not path.is_file():
            problems.append('missing file: ' + str(path.relative_to(ROOT)))
    if problems:
        return problems, {}
    activity = (APP/'java/org/exreader/host/MainActivity.java').read_text()
    view = (APP/'java/org/exreader/host/ReaderView.java').read_text()
    native = (APP/'java/org/exreader/host/NativeLibrary.java').read_text()
    bridge = (APP/'cpp/exreader_host_jni.c').read_text()
    app_gradle = (ROOT/'examples/android/app/build.gradle').read_text()
    test, workflow, doc = TEST.read_text(), WORKFLOW.read_text(), DOC.read_text()
    layout = (APP/'res/layout/activity_main.xml').read_text()
    for needle in ('newSingleThreadExecutor', 'onSaveInstanceState', 'takePersistableUriPermission',
                   'MAX_INPUT_BYTES', 'saveProgress', 'setPosition', 'onStop'):
        if needle not in activity:
            problems.append('MainActivity lacks ' + needle)
    for needle in ('onTouchEvent', 'AccessibilityNodeProvider', 'getAccessibilityNodeProvider',
                   'AccessibilityNodeInfo.obtain(ReaderView.this'):
        if needle not in view:
            problems.append('ReaderView lacks ' + needle)
    if 'System.loadLibrary("exreader_host")' not in native:
        problems.append('NativeLibrary does not load exreader_host')
    for symbol in ('exr_library_import_file_unique', 'exr_library_note', 'exr_library_fixed_note',
                   'exr_library_progress', 'exr_anchor_create', 'exr_library_notes'):
        if symbol not in bridge:
            problems.append('JNI bridge lacks ' + symbol)
    if 'androidx' in app_gradle or "abiFilters 'x86_64'" not in app_gradle or 'ndkVersion' not in app_gradle:
        problems.append('app dependency, ABI or NDK contract changed')
    for control in ('import_button', 'book_list', 'reader_view', 'page_label', 'select_button',
                    'copy_button', 'annotate_button', 'notes_button', 'note_list', 'status_text',
                    'cancel_button', 'rebuild_view'):
        if '@+id/' + control not in layout or control not in activity:
            problems.append('layout/activity lacks ' + control)
    ids = re.findall(r'step\("([a-z0-9_]+)"', test)
    if ids != WALKTHROUGH_IDS:
        problems.append('the original 45 named walkthrough cases must remain complete and ordered')
    for needle in ('force-stop', 'setOrientationLeft', 'takeScreenshot', 'validation.json', 'physical_device_execution'):
        if needle not in test:
            problems.append('walkthrough lacks ' + needle)
    for needle in ('android-emulator-runner', 'api-level: 34', 'arch: x86_64', 'upload-artifact',
                   'workflow_dispatch', 'examples/android/ci/emulator.sh'):
        if needle not in workflow:
            problems.append('workflow lacks ' + needle)
    emulator = (ROOT/'examples/android/ci/emulator.sh').read_text()
    if 'adb install' not in emulator or '/sdcard/Download' not in emulator or 'run_android_host_evidence.py' not in emulator:
        problems.append('emulator execution/collection entry point missing')
    if 'physical_device_execution' not in doc or 'x86_64' not in doc:
        problems.append('documentation must state device scope and ABI')
    return problems, {'cases_declared': len(ids), 'unique_cases': len(set(ids))}


def check_gate_review(path, expected):
    from importlib.util import module_from_spec, spec_from_file_location
    script = ROOT/'tests/android_host/check_evidence_gate.py'
    spec = spec_from_file_location('android_gate_review', script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    result = load(path)
    check_identity(result, expected)
    require(result.get('accepted') is True and result.get('script_sha256') == sha256(script),
            'gate regression identity missing')
    checks = result.get('checks', [])
    require([item.get('name') for item in checks] == module.expected_names() and
            all(item.get('passed') is True for item in checks), 'gate regression checks incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--stage', type=Path, default=ROOT/'stage/android-x86_64')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--api', type=int, default=34)
    parser.add_argument('--target', default='default')
    parser.add_argument('--image', default='system-images;android-34;default;x86_64')
    parser.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT', ''))
    parser.add_argument('--source-sha', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--run-url', default='')
    parser.add_argument('--workflow', default='wp13-android')
    parser.add_argument('--upstream', default=os.environ.get('ANDROID_HOST_UPSTREAM', '{}'))
    parser.add_argument('--gate-review', type=Path)
    args = parser.parse_args()
    summary, problems = {}, []
    try:
        require(args.repo.resolve() == ROOT, 'checker must use the tested checkout')
        problems, summary = static_checks()
        if args.evidence:
            require(args.build is not None, 'build evidence is required')
            require(args.api == 34 and args.target == 'default' and
                    args.image == 'system-images;android-34;default;x86_64', 'emulator contract mismatch')
            expected = {**cloud_identity(), 'source_sha': args.source_sha, 'run_id': args.run_id, 'attempt': args.attempt}
            run_url = os.environ.get('GITHUB_SERVER_URL', 'https://github.com') + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + expected['run_id']
            require(not args.run_url or args.run_url == run_url, 'run URL differs from the active cloud execution')
            summary = check_evidence(args.evidence, args.build, args.stage, json.loads(args.upstream), expected)
            summary['run']['url'] = run_url
            if args.gate_review:
                require(os.environ.get('ANDROID_GATE_OUTCOME') == 'success', 'gate regression step did not succeed')
                check_gate_review(args.gate_review, expected)
                summary['gate_review_sha256'] = sha256(args.gate_review)
    except Exception as error:
        problems.append(type(error).__name__ + ': ' + str(error)[:1200])
    report = {'schema': 2, 'accepted': not problems, 'ok': not problems, 'problems': problems, 'summary': summary}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'accepted': report['accepted'], 'problems': problems,
                      'walkthrough': summary.get('summary'), 'review': summary.get('review', {}).get('summary')}))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
