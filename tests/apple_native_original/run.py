#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only system folder selection and independent saved-byte readback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results

assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
p = argparse.ArgumentParser()
p.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
a = p.parse_args()
out = ROOT / 'build/apple-native-original' / a.platform
out.mkdir(parents=True, exist_ok=False)
report = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': a.platform,
          'accepted': False, 'physical_device': False, 'commands': []}
def run(role, *args):
    args = [str(x) for x in args]
    with (out / (role + '.log')).open('wb') as log:
        result = subprocess.run(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=4800)
    report['commands'].append({'role': role, 'argv': args, 'exit': result.returncode})
    if result.returncode:
        raise RuntimeError(role + ' failed: ' + str(result.returncode))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
try:
    target = 'macos' if a.platform == 'macos' else 'iphonesimulator'
    sdkroot = ROOT / 'build/raw3-ios-sdk' / target
    identity = json.loads((sdkroot / 'wave3-packages.json').read_text())
    assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (report['source_sha'], report['run_id'], report['attempt'], target)
    resources = out / 'resources'
    run('fixtures', sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources)
    project = out / 'project'
    run('project', 'ruby', 'tests/reader_team24_apple/make_project.rb', project, resources, ROOT / 'tests/apple_native_original/ui', 'wave3')
    if a.platform == 'macos':
        destination = 'platform=macOS'; scheme = 'EXReaderHost-macOS'; suffix = 'Debug'; signing = 'YES'
        saved = Path('/tmp/exreader-native-original-export')
        assert not saved.exists(), 'destination must start absent'
        saved.mkdir()
    else:
        devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
        prefix = 'iPhone' if a.platform == 'iphone' else 'iPad'
        runtime, name, udid = max((runtime, d['name'], d['udid']) for runtime, ds in devices['devices'].items() for d in ds if d.get('isAvailable') and d['name'].startswith(prefix))
        subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
        run('erase', 'xcrun', 'simctl', 'erase', udid)
        run('boot', 'xcrun', 'simctl', 'boot', udid)
        run('boot-ready', 'xcrun', 'simctl', 'bootstatus', udid, '-b')
        report['simulator'] = {'runtime': runtime, 'name': name, 'udid': udid}
        destination = 'platform=iOS Simulator,id=' + udid; scheme = 'EXReaderHost-iOS'; suffix = 'Debug-iphonesimulator'; signing = 'NO'
    derived = out / 'derived'; result = out / 'native.xcresult'
    run('native', 'xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', scheme,
        '-destination', destination, '-derivedDataPath', derived, '-resultBundlePath', result,
        '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '240',
        '-maximum-test-execution-time-allowance', '360', 'EXR_SDK_DIR=' + str(sdkroot / 'sdk'),
        'EXR_PRODUCTS_DIR=' + str(sdkroot / 'raw-products'), 'CODE_SIGNING_ALLOWED=' + signing)
    cases = load_results(result); report['cases'] = cases
    assert len(cases) == 1 and all(case['result'] == 'Passed' for case in cases), cases
    app = derived / 'Build/Products' / suffix / 'EXReaderHost.app'
    info = plistlib.loads((app / ('Contents/Info.plist' if a.platform == 'macos' else 'Info.plist')).read_bytes())
    assert info['EXRSourceSHA'] == report['source_sha'] and info['CFBundleIdentifier'] == 'org.exreader.host'
    binary = app / ('Contents/MacOS/EXReaderHost' if a.platform == 'macos' else 'EXReaderHost')
    report['program'] = {'sha256': sha(binary), 'bundle_id': info['CFBundleIdentifier'], 'source_sha': info['EXRSourceSHA']}
    if a.platform != 'macos':
        container = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', udid, 'org.exreader.host', 'data'], text=True).strip()
        saved = Path(container) / 'Documents'
    source = resources / 'Sample.epub'
    bundled = app / ('Contents/Resources/Sample.epub' if a.platform == 'macos' else 'Sample.epub')
    assert bundled.read_bytes() == source.read_bytes(), 'bundled import fixture differs from source'
    files = list(saved.glob('*.epub'))
    assert len(files) == 1, [str(f) for f in files]
    output = files[0]
    assert source.read_bytes() == output.read_bytes(), 'saved bytes differ from fixture'
    shutil.copyfile(source, out / 'source.epub'); shutil.copyfile(output, out / 'saved.epub')
    report['readback'] = {'filename': output.name, 'source_bytes': source.stat().st_size, 'saved_bytes': output.stat().st_size,
                          'source_sha256': sha(source), 'saved_sha256': sha(output), 'byte_equal': True}
    report['accepted'] = True
except Exception as error:
    report['failure'] = repr(error)
finally:
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
if not report['accepted']: sys.exit(1)
