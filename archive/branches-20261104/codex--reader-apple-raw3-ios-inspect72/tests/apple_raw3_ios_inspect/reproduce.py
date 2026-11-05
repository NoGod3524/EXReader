"""Original two OFF UI cases with failure-only AX observation, never acceptance."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
SOURCE = '72c6bbdd14ebf3be453fa7f0da81119d52675eb5'
RUN = 40203714083


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    out = ROOT / 'build/apple-raw3-ios-reproduce'; out.mkdir(parents=True, exist_ok=False)
    protected = ['src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'apps', 'examples', 'tests/fixtures',
                 'tools/build_apple_product.py', 'tools/build_apple_host.py', 'tools/apple_swift.py',
                 'tools/check_apple_product.py', 'tests/apple_host/make_xcodeproj.rb', 'tests/apple_host/reading']
    subprocess.run(['git', 'diff', '--exit-code', SOURCE, 'HEAD', '--', *protected], cwd=ROOT, check=True)
    cases = ('testFixedCbzAndPdfRealPointRecords', 'testRealTerminationAfterCommitReplaysExactlyOnce')
    original_tests = subprocess.check_output(['git', 'show', SOURCE + ':tests/apple_host/reading/ui/ReadingUITests.swift'], cwd=ROOT).decode()
    diagnostic = (ROOT / 'tests/apple_raw3_ios_inspect/reading/ui/ReadingUITests.swift').read_text()
    # Original helpers and every assertion remain verbatim. Only a new helper,
    # imports and a failure-only tearDown call are added to this separate copy.
    assert diagnostic[diagnostic.index('    private func element('):] == original_tests[original_tests.index('    private func element('):]
    jobs = fetch(f'actions/runs/{RUN}/attempts/1/jobs?per_page=100')['jobs']
    assert any(row['id'] == 121200082795 and row['conclusion'] == 'success' and row['head_sha'] == SOURCE for row in jobs)
    sdk_meta = fetch('actions/artifacts/12603156296')
    assert sdk_meta['name'] == 'raw3-ios-sdk-iphonesimulator-40203714083-1' and not sdk_meta['expired']
    assert sdk_meta['size_in_bytes'] == 21891156 and sdk_meta['digest'] == 'sha256:538d6c2888505d6398e1ce7294f8178de0008d0ddee119d969025cb278845cc1'
    raw = download_artifact_zip(sdk_meta['id'])
    assert len(raw) == sdk_meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == sdk_meta['digest']
    installed = out / 'installed'; installed.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            path = PurePosixPath(name); assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
        archive.extractall(installed)
    sdk = installed / 'sdk'
    sys.path.insert(0, str(ROOT / 'tests/apple_host'))
    from evidence_contract import validate_sdk
    identity = json.loads((installed / 'sdk-identity.json').read_bytes())
    validate_sdk(sdk, identity, SOURCE, RUN, 1, 'iphonesimulator')
    meta = fetch('actions/artifacts/12602953966')
    assert meta['size_in_bytes'] == 182452877 and meta['digest'] == 'sha256:3675f79031dc88ec8abf5217cf70a856a967c74812cd8a8030410bbbf7a48ad3'
    raw = download_artifact_zip(meta['id'])
    assert len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest']
    resources = out / 'resources'; resources.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            path = PurePosixPath(name)
            if len(path.parts) != 2 or path.parts[0] != 'inputs' or name.endswith('/'): continue
            assert path.name not in ('.', '..') and '\\' not in path.name
            (resources / path.name).write_bytes(archive.read(name))
    fixtures = json.loads((resources / 'manifest.json').read_bytes())
    assert all(hashlib.sha256((resources / name).read_bytes()).hexdigest() == sha for name, sha in fixtures.items())
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    runtime, device, udid = max((runtime, row['name'], row['udid']) for runtime, values in devices['devices'].items()
                               for row in values if row.get('isAvailable') and row['name'].startswith('iPhone'))
    subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
    for argv in (['xcrun', 'simctl', 'erase', udid], ['xcrun', 'simctl', 'boot', udid], ['xcrun', 'simctl', 'bootstatus', udid, '-b']):
        subprocess.run(argv, check=True)
    env = dict(os.environ, EXR_APPLE_SDK_VERSION='3.41.0', EXR_APPLE_PAGE_THEME='ON', EXR_APPLE_RAW3='OFF')
    project = out / 'project'
    subprocess.run(['ruby', 'tests/apple_host/make_xcodeproj.rb', str(project), str(resources),
                    'tests/apple_raw3_ios_inspect/reading/ui'], cwd=ROOT, env=env, check=True)
    result = out / 'two-original-cases.xcresult'
    argv = ['xcodebuild', 'test', '-project', str(project / 'EXReaderHost.xcodeproj'), '-scheme', 'EXReaderHost-iOS',
            '-destination', 'platform=iOS Simulator,id=' + udid, '-derivedDataPath', str(out / 'DerivedData'),
            '-resultBundlePath', str(result), '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
            '-default-test-execution-time-allowance', '180', '-maximum-test-execution-time-allowance', '300',
            *['-only-testing:EXReaderHostUITests-iOS/ReadingUITests/' + case for case in cases],
            'EXR_SDK_DIR=' + str(sdk), 'CODE_SIGNING_ALLOWED=NO']
    with (out / 'xcodebuild.log').open('wb') as stream:
        value = subprocess.run(argv, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=1500)
    print('DIAGNOSTIC-ORIGINAL-CASE-EXIT', value.returncode, flush=True)
    lines = (out / 'xcodebuild.log').read_text(errors='replace').splitlines()
    for index, line in enumerate(lines):
        if any(key in line for key in ('error:', 'exceeded execution time', 'failed (', 'passed (')):
            print('DIAGNOSTIC-CASE-LOG', '\n'.join(lines[max(0, index - 3):index + 5]), flush=True)
    attachments = out / 'attachments'
    if result.exists():
        subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(result), '--output-path', str(attachments)], check=True)
    for path in attachments.glob('*'):
        if path.is_file() and path.suffix in ('.txt', '.json'):
            text = path.read_text(errors='replace')
            if 'diagnostic_only' in text or 'failure-target-AX' in text: print('FAILURE-TARGET-AX', text, flush=True)
    report = {'accepted': False, 'diagnostic_only': True, 'source_sha': os.environ['GITHUB_SHA'],
              'original_host_source': SOURCE, 'sdk_source_run': RUN, 'sdk_artifact': sdk_meta,
              'input_artifact': meta, 'original_case_budget': 180, 'original_wait_seconds': 90,
              'host_production_unchanged': True, 'actual_cases': cases, 'xcodebuild_exit': value.returncode,
              'device': device, 'runtime': runtime, 'udid': udid, 'no_failure_recovery_tap': True}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
