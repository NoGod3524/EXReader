#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only, additive source admission and frozen-prefix diagnostic build."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = '59d350c225b9c0b644cbc4b7a266c52726518e35'
PACKAGE = 'tests/apple_ios_organization_activation_probe_20261029/'
WORKFLOW = '.github/workflows/apple-ios-organization-activation-probe-20261029.yml'
PATHS = [WORKFLOW] + [PACKAGE + name for name in
    ('prepare.py', 'ActivationProbeTests.swift', 'collect.py', 'README.md')]
OUT = ROOT / 'build/ios-organization-activation-probe'
FORMAL = 'tests/apple_ios_organization_20261028/ui/IOSOrganizationAcceptanceTests.swift'
FORMAL_HASH = 'deeed62b7083fb4a3e85ccd866a9a9eb4fdbca8e0c86bb88136b0fca400161ff'
BOOK_HASH = '0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb'
CASES = {f'test0{i}{arm}': 'control' if arm == 'Control' else 'return'
         for i, arm in enumerate(('Control', 'Return', 'Control', 'Return', 'Control', 'Return'), 1)}
CLASS = 'IOSOrganizationActivationProbeTests'

def command(*args):
    return subprocess.check_output(list(map(str, args)), cwd=ROOT, text=True).strip()

def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(text, old, new):
    assert text.count(old) == 1, 'source anchor differs: ' + old
    return text.replace(old, new)

def render_ui(formal, fragment):
    hook_old = '        element.tap()\n'
    hook_new = '        if probeActivation { probeNativeTap(element) } else { element.tap() }\n'
    teardown_old = '    override func tearDownWithError() throws {\n'
    teardown_new = teardown_old + '        emitProbeReceipt()\n'
    renamed = replace_once(formal, 'final class IOSOrganizationAcceptanceTests:', 'final class ' + CLASS + ':')
    hooked = replace_once(replace_once(renamed, hook_old, hook_new), teardown_old, teardown_new)
    assert hooked.endswith('}\n')
    generated = hooked[:-2] + '\n' + fragment + '\n}\n'
    reconstructed = generated[:-(len(fragment) + 4)] + '}\n'
    reconstructed = replace_once(reconstructed, hook_new, hook_old)
    reconstructed = replace_once(reconstructed, teardown_new, teardown_old)
    reconstructed = replace_once(reconstructed, 'final class ' + CLASS + ':', 'final class IOSOrganizationAcceptanceTests:')
    assert reconstructed == formal, 'generated diagnostic changed frozen helper/case bytes'
    return generated

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    source = command('git', 'rev-parse', 'HEAD')
    assert source == os.environ['GITHUB_SHA']
    delta = command('git', 'diff', '--name-status', BASE, source).splitlines()
    assert sorted(delta) == sorted('A\t' + p for p in PATHS), delta
    assert not command('git', 'status', '--porcelain', '--untracked-files=all')
    formal = (ROOT / FORMAL).read_text()
    assert digest(ROOT / FORMAL) == FORMAL_HASH
    assert formal == subprocess.check_output(['git', 'show', BASE + ':' + FORMAL], cwd=ROOT, text=True)
    OUT.mkdir(parents=True, exist_ok=False)
    evidence = OUT / 'evidence'; evidence.mkdir()
    run(sys.executable, 'tests/apple_sdk342_package/run.py', '--target', 'iphonesimulator')
    run(sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', OUT / 'resources')
    assert digest(OUT / 'resources/Sample.epub') == BOOK_HASH, 'historical real EPUB differs'
    original = ROOT / 'tests/apple_host/make_xcodeproj.rb'
    adapted = replace_once(original.read_text(), "['3.40.0', '3.41.0'].include?(sdk_version)",
                           "['3.40.0', '3.41.0', '3.42.0'].include?(sdk_version)")
    adapted = replace_once(adapted, "page_theme == 'ON' && sdk_version != '3.41.0'",
                           "page_theme == 'ON' && !['3.41.0', '3.42.0'].include?(sdk_version)")
    generator = OUT / 'make_xcodeproj_sdk342.rb'; generator.write_text(adapted)
    team_original = ROOT / 'tests/reader_team24_apple/make_project.rb'
    team = replace_once(team_original.read_text(), "'tests/apple_host/make_xcodeproj.rb'", repr(str(generator)))
    team_generator = OUT / 'make_project_sdk342.rb'; team_generator.write_text(team)

    # Preserve every old helper/case byte in a generated copy, except declared
    # class rename and diagnostic hooks. Only the six NEW method selectors run.
    fragment = (ROOT / PACKAGE / 'ActivationProbeTests.swift').read_text()
    generated = render_ui(formal, fragment)
    ui = OUT / 'ui'; ui.mkdir()
    native = ui / 'ActivationProbeTests.swift'; native.write_text(generated)
    run('ruby', team_generator, OUT / 'project', OUT / 'resources', ui, 'base')
    for platform in ('iOS', 'macOS'):
        info = plistlib.loads((OUT / 'project' / ('Info-' + platform + '.plist')).read_bytes())
        assert info['EXRSDKVersion'] == '3.42.0' and info['EXRSourceSHA'] == source
    sdk = json.loads((ROOT / 'build/apple-sdk342/iphonesimulator/identity.json').read_text())
    assert (sdk['source_sha'], sdk['run_id'], sdk['attempt'], sdk['product']['sdk_version']) == (
        source, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], '3.42.0')
    retained = evidence / 'generated'; retained.mkdir()
    for script in (generator, team_generator): shutil.copy2(script, retained / script.name)
    shutil.copytree(ui, retained / 'ui')
    shutil.copytree(OUT / 'project', retained / 'project')
    guard = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'producer_workspace': str(ROOT),
        'frozen_product_source': BASE, 'sdk_version': '3.42.0', 'changed_paths': sorted(PATHS),
        'all_existing_blobs_unchanged': True, 'formal_ui_sha256': FORMAL_HASH,
        'formal_reconstruction_equal': True, 'sdk_package_identity': sdk,
        'selected_cases': list(CASES), 'product_accepted': False, 'formal_credit': 0,
        'adapter_changes': ['SDK342/theme generator allowlists', 'generated project input path',
                            'generated XCTest class rename', 'teardown receipt hook', 'sole activation timing hook',
                            'new six diagnostic methods, old methods not selected'],
        'generated_sources': {str(p.relative_to(OUT)): digest(p) for p in (generator, team_generator, native)},
        'retained_generated': {p.relative_to(retained).as_posix(): digest(p) for p in sorted(retained.rglob('*')) if p.is_file()},
        'fixtures': {p.name: digest(p) for p in (OUT / 'resources').iterdir() if p.is_file()},
        'package_files': {p: digest(ROOT / p) for p in PATHS}}
    (evidence / 'source-guard.json').write_text(json.dumps(guard, indent=2) + '\n')
    run('git', 'diff', '--exit-code')
    print(json.dumps({'source_admitted': True, 'formal_reconstruction_equal': True, 'selected_cases': list(CASES)}))

if __name__ == '__main__': main()
