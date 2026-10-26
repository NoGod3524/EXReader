# SPDX-License-Identifier: MIT
"""Same-source three-target native UI, unchanged old suites, real executable identities."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import load_results
sys.path.insert(0, str(ROOT / 'tools'))
from check_apple_product import inspect

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    p = argparse.ArgumentParser(); p.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True); args = p.parse_args()
    out = ROOT / 'build/team24-apple' / args.platform; evidence = out / 'evidence'; evidence.mkdir(parents=True, exist_ok=False)
    resources = out / 'resources'; commands = []; phases = []
    result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'platform': args.platform, 'accepted': False, 'commands': commands, 'phases': phases, 'physical_device': False,
        'complete_product': False, 'gaps': ['Ad-hoc macOS/simulator only; physical devices/signing pending',
            'No full live network synchronization claim', 'Physical-device VoiceOver and signed device distribution remain untested']}
    def run(argv, role, timeout=4800):
        argv = list(map(str, argv)); print('Team24 Apple PHASE ' + role, flush=True)
        log = evidence / (role + '.log')
        with log.open('wb') as f: value = subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append({'role': role, 'argv': argv, 'exit': value.returncode})
        if value.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-100:]), flush=True)
            raise RuntimeError(role + ' failed: ' + str(value.returncode))
    try:
        sdks = {}
        for target in ('macos', 'iphonesimulator'):
            roots = list((ROOT / 'sdk-input').glob('team24-apple-sdk-' + target + '-*')); assert len(roots) == 1
            identity = json.loads((roots[0] / 'wave3-packages.json').read_text())
            assert (identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) == (result['source_sha'], result['run_id'], result['attempt'], target)
            sdks[target] = roots[0]
        run([sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources], 'fixtures')
        run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources], 'navigation-fixtures')
        mac = sdks['macos'] / 'sdk'; helper = out / 'make-cfi'
        run(['cc', '-I', mac / 'include', 'tests/apple_host/navigation/make_cfi.c', '-L', mac / 'lib', '-lexreader',
            '-Wl,-rpath,' + str(mac / 'lib'), '-o', helper], 'cfi-build')
        cfi = subprocess.check_output([helper, resources / 'Sample.epub']); (out / 'cfi.txt').write_bytes(cfi)
        run([sys.executable, 'tests/apple_host/navigation/prepare_navigation_fixture.py', '--resources', resources, '--cfi', out / 'cfi.txt'], 'cfi-fixture')
        run([sys.executable, 'tests/apple_host/reading/prepare_reading_fixture.py', '--resources', resources], 'reading-fixtures')
        run([sys.executable, 'tests/apple_host/search/prepare_search_fixture.py', '--resources', resources], 'search-fixtures')
        run([sys.executable, 'tests/apple_host/page_theme/prepare_fixtures.py', '--resources', resources], 'theme-fixtures')
        control_tests = out / 'original-tests'; control_tests.mkdir()
        original = {}
        for suite in ('reading', 'navigation', 'search', 'page_theme'):
            for source in (ROOT / 'tests/apple_host' / suite / 'ui').glob('*.swift'):
                shutil.copyfile(source, control_tests / source.name); assert digest(source) == digest(control_tests / source.name)
                original[str(source.relative_to(ROOT))] = digest(source)
        base_tests = out / 'base-tests'; base_tests.mkdir()
        source = ROOT / 'tests/apple_host/EXReaderHostUITests.swift'
        shutil.copyfile(source, base_tests / source.name); original[str(source.relative_to(ROOT))] = digest(source)
        result['unchanged_old_tests'] = original
        if args.platform == 'macos':
            target = 'macos'; destination = 'platform=macOS'; scheme = 'EXReaderHost-macOS'; suffix = 'Debug'; signing = 'YES'
            result['destination'] = destination
        else:
            target = 'iphonesimulator'; scheme = 'EXReaderHost-iOS'; suffix = 'Debug-iphonesimulator'; signing = 'NO'
            data = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
            prefix = 'iPhone' if args.platform == 'iphone' else 'iPad'
            runtime, name, udid = max((runtime, d['name'], d['udid']) for runtime, values in data['devices'].items()
                for d in values if d.get('isAvailable') and d['name'].startswith(prefix))
            subprocess.run(['xcrun', 'simctl', 'shutdown', udid], capture_output=True)
            run(['xcrun', 'simctl', 'erase', udid], 'erase'); run(['xcrun', 'simctl', 'boot', udid], 'boot')
            run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'boot-ready')
            destination = 'platform=iOS Simulator,id=' + udid; result['destination'] = {'runtime': runtime, 'device': name, 'udid': udid}
        sdk = sdks[target] / 'sdk'; products = sdks[target] / 'raw-products'
        for mode, tests, expected in [('wave3', ROOT / 'tests/reader_team24_apple/ui', 5), ('base', base_tests, 13), ('control', control_tests, 21)]:
            project = out / ('project-' + mode); derived = out / ('derived-' + mode)
            run(['ruby', 'tests/reader_team24_apple/make_project.rb', project, resources, tests, mode], mode + '-project')
            if args.platform != 'macos': subprocess.run(['xcrun', 'simctl', 'uninstall', udid, 'org.exreader.host'], capture_output=True)
            bundle = evidence / (mode + '.xcresult')
            phase = {'mode': mode, 'expected_cases': expected, 'accepted': False}; phases.append(phase)
            failed = None
            try:
                run(['xcodebuild', 'test', '-project', project / 'EXReaderHost.xcodeproj', '-scheme', scheme,
                    '-destination', destination, '-derivedDataPath', derived, '-resultBundlePath', bundle,
                    '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES', '-default-test-execution-time-allowance', '240',
                    '-maximum-test-execution-time-allowance', '360', 'EXR_SDK_DIR=' + str(sdk), 'EXR_PRODUCTS_DIR=' + str(products),
                    'CODE_SIGNING_ALLOWED=' + signing], mode + '-native-ui')
            except Exception as error: failed = error
            app = derived / 'Build/Products' / suffix / 'EXReaderHost.app'
            binary = app / ('Contents/MacOS/EXReaderHost' if args.platform == 'macos' else 'EXReaderHost')
            mapping = derived / 'Build/Products' / suffix / 'EXReaderHost.link.map'
            if binary.is_file():
                info = plistlib.loads((app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')).read_bytes())
                assert info['EXRSourceSHA'] == result['source_sha']
                assert info['CFBundleIdentifier'] == 'org.exreader.host'
                saved = evidence / ('program-' + mode); shutil.copytree(app, saved / 'EXReaderHost.app')
                # The nested archive preserves executable modes when downloaded.
                run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app,
                     saved / ('EXReaderHost-' + args.platform + '.zip')], mode + '-package')
                shutil.copyfile(mapping, saved / 'link.map')
                phase['program'] = {'path': str(binary.relative_to(derived)), 'bytes': binary.stat().st_size,
                    'sha256': digest(binary), 'bundle_id': info['CFBundleIdentifier'],
                    'bundle_source_sha': info['EXRSourceSHA'], 'physical_device': False,
                    'packaged_app': str((saved / ('EXReaderHost-' + args.platform + '.zip')).relative_to(evidence))}
                phase['original_checker'] = inspect(binary, mapping, selector_bytes_candidate=True)
                deps = subprocess.check_output(['otool', '-L', binary], text=True); symbols = subprocess.check_output(['nm', '-g', binary], text=True); link = mapping.read_text(encoding='utf-8', errors='surrogateescape')
                (saved / 'symbols.txt').write_text(symbols); (saved / 'dependencies.txt').write_text(deps)
                assert not re.search(r'libsqlite3(?:\.|\s)', deps)
                assert not re.search(r'libexr_(?:core|library)\.a', link)
                assert len(re.findall(r'\b[Tt]\s+_sqlite3_open_v2\s*$', symbols, re.M)) == 1
                assert len([line for line in link.splitlines() if 'libreader_catalog_sqlite.a' in line and 'sqlite3.c.o' in line]) == 1
                required = ['reader_annotation_import_raw3_run', 'rfl_import_file', 'rfl_font_open', 'roe_run', 'reader_jh_complete', 'reader_sync_view_capture']
                for symbol in required: assert len(re.findall(r'\b[Tt]\s+_' + symbol + r'\s*$', symbols, re.M)) == 1, symbol
                assert not re.search(r'\b[Tt]\s+_exr_(?:anchor_resolve_ex|fixed_anchor_resolve|library_open)\s*$', symbols, re.M)
                assert 'libexreader' in deps
                phase['provider'] = {'installed_five_modules': required, 'single_product_sqlite': True, 'static_sdk': False,
                    'public_product_resolver': False, 'dynamic_sdk': True}
            if bundle.exists():
                try: phase['cases'] = load_results(bundle)
                except Exception as error: phase['result_parse_error'] = str(error)
            if failed: phase['failure'] = str(failed)
            else:
                assert len(phase.get('cases', [])) == expected and all(x['result'] == 'Passed' for x in phase['cases'])
                phase['accepted'] = True
        result['accepted'] = len(phases) == 3 and all(x['accepted'] for x in phases)
    except Exception as error:
        result['failure'] = str(error); print('Team24 Apple FAILURE ' + str(error), flush=True)
    finally:
        result['files'] = {str(path.relative_to(evidence)): {'bytes': path.stat().st_size, 'sha256': digest(path)}
            for path in evidence.rglob('*') if path.is_file() and path.name != 'result.json'}
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({k: v for k, v in result.items() if k not in ('files', 'commands')}), flush=True)
    assert result['accepted'], 'Team24 Apple scoped acceptance incomplete; retain original evidence'
if __name__ == '__main__': main()
