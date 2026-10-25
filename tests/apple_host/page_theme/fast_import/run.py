# SPDX-License-Identifier: MIT
"""Consume the actual frozen SDK; verify a real same-turn import on an iPad."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests/apple_host')]
from check_parallel_integration import download_artifact_zip, fetch
from collect_evidence import load_results
from evidence_contract import validate_sdk
from check_apple_product import inspect

BASE = 'f4aa876c4e077201ade122c6a558a90731327daa'
SDK_PRODUCER = '6d53f3c09ddea3ea4f065846dbc53897d3668fcb'
SDK_RUN, SDK_ARTIFACT = 40173677171, 12591915246
SDK_BYTES = 20517508
SDK_DIGEST = 'sha256:f87671e9a3a2cae26a6792f7e0d7afbc793fdb72c190e9f2a8908e2d456a7478'
CASE = 'testFastOwnerImportPublishesWithoutBusyTransition'
INITIALIZATION_CASE = 'testInitializationGateHasNoEarlyImportWindow'
OUT = ROOT / 'build/apple-shelf-publication'


def require(value, message):
    if not value:
        raise ValueError(message)


def run(argv, name, timeout=900):
    with (OUT / name).open('wb') as stream:
        result = subprocess.run([str(v) for v in argv], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        print('\n'.join((OUT / name).read_text(errors='replace').splitlines()[-200:]), flush=True)
        raise RuntimeError('Command failed: ' + name)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    OUT.mkdir(parents=True, exist_ok=True)
    source = os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    allowed = {'examples/apple/HostModel.swift', 'examples/apple/HostViews.swift', 'tests/apple_host/make_xcodeproj.rb',
               '.github/workflows/reader-apple-shelf-publication.yml', 'docs/READER-APPLE-SHELF-PUBLICATION.md',
               'docs/validation/reader-apple-shelf-publication.json'}
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], cwd=ROOT, text=True).splitlines()
    require(all(path in allowed or path.startswith(('tests/apple_host/page_theme/fast_import/', 'tests/apple_host/page_theme/fast_import_ui/')) for path in changed), 'unowned source changed')
    # The installed SDK and modules are an explicit older producer, never relabelled
    # as this host source. All of their production trees remain byte-identical.
    subprocess.run(['git', 'diff', '--exit-code', SDK_PRODUCER, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt',
                    'bindings', 'tests/fixtures', 'apps/reader', 'extras', 'tools/build_apple_product.py'], cwd=ROOT, check=True)
    artifact = fetch('actions/artifacts/' + str(SDK_ARTIFACT))
    require(artifact['workflow_run']['id'] == SDK_RUN and artifact['workflow_run']['head_sha'] == SDK_PRODUCER and
            artifact['name'] == 'apple-theme-sdk-iphonesimulator-' + str(SDK_RUN) + '-1' and not artifact['expired'] and
            artifact['size_in_bytes'] == SDK_BYTES and artifact['digest'] == SDK_DIGEST, 'frozen SDK producer differs')
    raw = download_artifact_zip(SDK_ARTIFACT)
    require(len(raw) == SDK_BYTES and 'sha256:' + hashlib.sha256(raw).hexdigest() == SDK_DIGEST, 'frozen SDK ZIP differs')
    restored = OUT / 'sdk-producer'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate SDK ZIP member')
        for name in archive.namelist():
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe SDK ZIP path')
        archive.extractall(restored)
    sdk = restored / 'stage/iphonesimulator'
    identity = json.loads((restored / 'build/sdk-identity.json').read_text())
    validate_sdk(sdk, identity, SDK_PRODUCER, str(SDK_RUN), '1', 'iphonesimulator')
    require(identity['sdk_version'] == '3.41.0' and identity['abi'] == 1, 'SDK version/ABI differs')
    resources = ROOT / 'build/fast-import-resources'
    run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures.log')
    check = subprocess.run(['ruby', '-e', "require 'xcodeproj'"], capture_output=True)
    if check.returncode:
        run(['gem', 'install', 'xcodeproj', '--no-document'], 'gem.log')
    project = ROOT / 'build/fast-import-project'
    run(['ruby', 'tests/apple_host/make_xcodeproj.rb', project, resources, 'tests/apple_host/page_theme/fast_import_ui'], 'project.log')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], text=True, timeout=180))
    runtime, name, udid = max((runtime, row['name'], row['udid']) for runtime, rows in devices['devices'].items()
                              for row in rows if row.get('isAvailable') and row['name'].startswith('iPad'))
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True, timeout=120)
    run(['xcrun', 'simctl', 'erase', udid], 'erase.log', timeout=180)
    result = OUT / 'ipad.xcresult'
    derived = ROOT / 'build/FastImportDerivedData'
    run(['xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', 'EXReaderHost-iOS',
         '-destination', 'platform=iOS Simulator,id=' + udid, '-derivedDataPath', derived, '-resultBundlePath', result,
         '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '180',
         '-maximum-test-execution-time-allowance', '300', 'EXR_SDK_DIR=' + str(sdk), 'CODE_SIGNING_ALLOWED=NO'], 'xcodebuild.log')
    cases = load_results(result)
    require(len(cases) == 2 and {re.findall(r'test[A-Za-z0-9_]+', row['name'])[0] for row in cases} == {CASE, INITIALIZATION_CASE} and
            all(row['result'] == 'Passed' for row in cases), 'missing/failed/skipped real readiness or fast import case')
    attachments = OUT / 'attachments'
    run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', result, '--output-path', attachments], 'attachments.log')
    observations = {}; screens = set()
    for group in json.loads((attachments / 'manifest.json').read_text()):
        owner = re.findall(r'test[A-Za-z0-9_]+', str(group.get('testIdentifier') or group.get('testName', '')))
        require(len(owner) == 1 and owner[0] in {CASE, INITIALIZATION_CASE}, 'unowned attachment case')
        owner = owner[0]
        for item in group['attachments']:
            filename = item['exportedFileName']; require(Path(filename).name == filename, 'unsafe attachment name')
            path = attachments / filename; label = item['suggestedHumanReadableName']
            if label.startswith('fast-import-observation'):
                require(owner not in observations, 'duplicate observation'); observations[owner] = json.loads(path.read_text())
            elif label.startswith('fast-import-'):
                require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'missing actual screenshot')
                role = next((role for role in ('real-committed-row', 'actual-sdk-page', 'unready-controls-disabled',
                    'actual-backend-rejected-before-begin', 'ordinary-first-import-visible', 'ordinary-first-sdk-page') if label.startswith('fast-import-' + role)), None)
                require(role is not None and (owner, role) not in screens, 'unknown/duplicate screenshot'); screens.add((owner, role))
    require(set(observations) == {CASE, INITIALIZATION_CASE} and screens == {
        (CASE, 'real-committed-row'), (CASE, 'actual-sdk-page'), (INITIALIZATION_CASE, 'unready-controls-disabled'),
        (INITIALIZATION_CASE, 'actual-backend-rejected-before-begin'), (INITIALIZATION_CASE, 'ordinary-first-import-visible'),
        (INITIALIZATION_CASE, 'ordinary-first-sdk-page')}, 'missing raw readiness/fast import observations')
    observation = observations[CASE]
    before, after, fast = (observation[key] for key in ('before', 'after', 'fast'))
    require(before['cached_rows'] == 0 and before['loading'] is False and after['cached_rows'] == 1 and after['loading'] is False and
            after['generation'] > before['generation'] and after['applied_generation'] == after['generation'], 'shelf did not receive committed book')
    require(fast['completed'] is True and fast['busy'] is False and fast['same_main_turn'] is True and
            fast['observed_busy_changes'] == 0 and fast['sdk_books'] == 1 and 'C00P000W00' in observation['real_reader_page'], 'not a genuine same-turn SDK import')
    gate = observations[INITIALIZATION_CASE]
    require(gate['before_gate']['library_ready'] is False and gate['before_gate']['busy'] is False and
            gate['before_gate']['started'] is False and gate['before_gate']['token'] == 0 and
            gate['rejected_gate']['rejected_unready'] == 1 and gate['rejected_gate']['token'] == 0 and
            gate['rejected_gate']['retained_ui_books'] == 0 and gate['rejected_gate']['library_ready'] is False and
            gate['after_gate']['library_ready'] is True and gate['after_gate']['busy'] is False and
            'C00P000W00' in gate['real_reader_page'], 'initialization admission was not tied to actual owner readiness')
    app = derived / 'Build/Products/Debug-iphonesimulator/EXReaderHost.app'
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.41.0' and info['EXRPageThemeEnabled'] is True, 'actual program identity differs')
    provider = inspect(app / 'EXReaderHost', app.parent / 'EXReaderHost.link.map')
    shutil.copytree(app, OUT / 'program/EXReaderHost.app')
    report = {'accepted_fast_import_fixture_only': True, 'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': 'ipad', 'destination': {'udid': udid, 'name': name, 'runtime': runtime},
              'sdk_producer_source': SDK_PRODUCER, 'sdk_producer_run': SDK_RUN, 'sdk_producer_attempt': 1,
              'sdk_artifact': {key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
              'sdk_identity_original': identity, 'provider': provider, 'cases': cases, 'observations': observations,
              'physical_device_execution': False, 'complete_product': False, 'original_six_suites_granted': False}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
