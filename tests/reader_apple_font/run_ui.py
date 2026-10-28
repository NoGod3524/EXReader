# SPDX-License-Identifier: MIT
"""Actions-only independent native Apple font acceptance; retain failures."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    args = parser.parse_args()
    out = ROOT / 'build/apple-font' / args.platform
    evidence = out / 'evidence'
    evidence.mkdir(parents=True, exist_ok=False)
    result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': args.platform,
              'accepted': False, 'physical_device': False, 'commands': []}

    def run(command, name, timeout=4800):
        command = list(map(str, command))
        print('Apple font phase ' + name, flush=True)
        with (evidence / (name + '.log')).open('wb') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        result['commands'].append({'name': name, 'argv': command, 'exit': process.returncode})
        if process.returncode:
            print('\n'.join((evidence / (name + '.log')).read_text(errors='replace').splitlines()[-100:]), flush=True)
            raise RuntimeError(name + ' failed: ' + str(process.returncode))

    try:
        target = 'macos' if args.platform == 'macos' else 'iphonesimulator'
        roots = list((ROOT / 'sdk-input').glob('team24-apple-sdk-' + target + '-*'))
        assert len(roots) == 1
        package = roots[0]
        identity = json.loads((package / 'wave3-packages.json').read_text())
        assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (
            result['source_sha'], result['run_id'], result['attempt'], target)
        resources = out / 'resources'
        run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures')
        shutil.copyfile(ROOT / 'tests/fixtures/fonts/primary.ttf', resources / 'FontReview.ttf')
        shutil.copyfile(ROOT / 'tests/fixtures/fonts/README.md', resources / 'FontReview-license.txt')
        manifest_path = resources / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['FontReview.ttf'] = sha(resources / 'FontReview.ttf')
        manifest['FontReview-license.txt'] = sha(resources / 'FontReview-license.txt')
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        shutil.copyfile(manifest_path, evidence / 'resource-manifest.json')
        result['fixture'] = {'font_sha256': manifest['FontReview.ttf'], 'license': 'MIT, EXReader contributors',
                             'source': 'tests/fixtures/fonts/primary.ttf', 'manifest_sha256': sha(manifest_path)}
        assert manifest['FontReview.ttf'] != manifest['Reader.otf']
        project, derived = out / 'project', out / 'derived'
        run(['ruby', 'tests/reader_team24_apple/make_project.rb', project, resources,
             ROOT / 'tests/reader_apple_font/ui', 'wave3'], 'project')
        if args.platform == 'macos':
            destination, scheme, suffix, signing = 'platform=macOS', 'EXReaderHost-macOS', 'Debug', 'YES'
        else:
            devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
            prefix = 'iPhone' if args.platform == 'iphone' else 'iPad'
            runtime, name, udid = max((runtime, d['name'], d['udid']) for runtime, values in devices['devices'].items()
                                      for d in values if d.get('isAvailable') and d['name'].startswith(prefix))
            result['device'] = {'runtime': runtime, 'name': name, 'udid': udid}
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
            run(['xcrun', 'simctl', 'erase', udid], 'erase')
            run(['xcrun', 'simctl', 'boot', udid], 'boot')
            run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'boot-ready')
            destination, scheme, suffix, signing = 'platform=iOS Simulator,id=' + udid, 'EXReaderHost-iOS', 'Debug-iphonesimulator', 'NO'
        bundle = evidence / 'font.xcresult'
        failure = None
        try:
            run(['xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', scheme,
                 '-destination', destination, '-derivedDataPath', derived, '-resultBundlePath', bundle,
                 '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
                 '-default-test-execution-time-allowance', '240', '-maximum-test-execution-time-allowance', '360',
                 'EXR_SDK_DIR=' + str(package / 'sdk'), 'EXR_PRODUCTS_DIR=' + str(package / 'raw-products'),
                 'CODE_SIGNING_ALLOWED=' + signing], 'font-native-ui')
        except Exception as error:
            failure = str(error)
        app = derived / 'Build/Products' / suffix / 'EXReaderHost.app'
        binary = app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
        if binary.is_file():
            info = plistlib.loads((app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')).read_bytes())
            assert info['EXRSourceSHA'] == result['source_sha'] and info['CFBundleIdentifier'] == 'org.exreader.host'
            bundled = app / 'Contents/Resources' if args.platform == 'macos' else app
            for name, digest in manifest.items():
                assert sha(bundled / name) == digest, name
            result['program'] = {'sha256': sha(binary), 'bytes': binary.stat().st_size, 'source_sha': info['EXRSourceSHA']}
            run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, evidence / 'EXReaderHost.zip'], 'package')
        if bundle.exists():
            try:
                result['cases'] = load_results(bundle)
            except Exception as error:
                result['result_parse_error'] = str(error)
        if failure:
            result['failure'] = failure
        else:
            assert len(result.get('cases', [])) == 1 and all(case['result'] == 'Passed' for case in result['cases'])
            result['accepted'] = True
    except Exception as error:
        result['failure'] = str(error)
        print('Apple font failure: ' + str(error), flush=True)
    finally:
        result['files'] = {str(path.relative_to(evidence)): {'bytes': path.stat().st_size, 'sha256': sha(path)}
                           for path in evidence.rglob('*') if path.is_file() and path.name != 'result.json'}
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k not in ('files', 'commands')}), flush=True)
    assert result['accepted'], 'Apple font acceptance incomplete; retain failure evidence'


if __name__ == '__main__':
    main()
