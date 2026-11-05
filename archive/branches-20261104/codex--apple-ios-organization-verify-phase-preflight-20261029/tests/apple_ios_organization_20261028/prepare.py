#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only new acceptance adapter. Never edits old tests or product owners."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from contract import BASE, PACKAGE, WORKFLOW
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/ios-organization'

def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('baseline adapter anchor changed: ' + old)
    return text.replace(old, new)

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin'
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert source == os.environ['GITHUB_SHA']
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE, source], cwd=ROOT, text=True).splitlines()
    assert changed and all(p.startswith(PACKAGE) or p == WORKFLOW for p in changed), changed
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True)
    OUT.mkdir(parents=True, exist_ok=False)
    evidence = OUT / 'evidence'; evidence.mkdir()
    # The existing exact SDK3.42 package builder retains its candidate guard,
    # installed product identity, signed unpacked executable and theme checks.
    run(sys.executable, 'tests/apple_sdk342_package/run.py', '--target', 'iphonesimulator')
    run(sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', OUT / 'resources')
    run('ruby', '-e', "require 'xcodeproj'")
    original = ROOT / 'tests/apple_host/make_xcodeproj.rb'
    source_text = original.read_text()
    adapted = replace_once(source_text, "['3.40.0', '3.41.0'].include?(sdk_version)",
                           "['3.40.0', '3.41.0', '3.42.0'].include?(sdk_version)")
    adapted = replace_once(adapted, "page_theme == 'ON' && sdk_version != '3.41.0'",
                           "page_theme == 'ON' && !['3.41.0', '3.42.0'].include?(sdk_version)")
    generated = OUT / 'make_xcodeproj_sdk342.rb'; generated.write_text(adapted)
    team_original = ROOT / 'tests/reader_team24_apple/make_project.rb'
    team_adapted = replace_once(team_original.read_text(), "'tests/apple_host/make_xcodeproj.rb'", repr(str(generated)))
    team_generated = OUT / 'make_project_sdk342.rb'; team_generated.write_text(team_adapted)
    run('ruby', team_generated, OUT / 'project', OUT / 'resources', ROOT / PACKAGE / 'ui', 'base')
    for platform in ('iOS', 'macOS'):
        info = plistlib.loads((OUT / 'project' / ('Info-' + platform + '.plist')).read_bytes())
        assert info['EXRSDKVersion'] == '3.42.0' and info['EXRSourceSHA'] == source
    identity = json.loads((ROOT / 'build/apple-sdk342/iphonesimulator/identity.json').read_text())
    assert (identity['source_sha'], identity['run_id'], identity['attempt']) == (
        source, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'])
    assert identity['product']['sdk_version'] == '3.42.0'
    guard = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'common_base': BASE, 'changed_paths': changed, 'sdk_version': '3.42.0', 'sdk_package_identity': identity,
        'adapter_changes': ['explicit 3.42 SDK allowlist', 'explicit 3.42 theme allowlist', 'generated project input path'],
        'old_sources': {str(p.relative_to(ROOT)): digest(p) for p in (original, team_original,
            ROOT / 'tests/apple_host/organization/ui/OrganizationUITests.swift', ROOT / 'examples/apple/HostOrganization.swift',
            ROOT / 'examples/apple/HostViews.swift')},
        'generated_sources': {str(p.relative_to(OUT)): digest(p) for p in (generated, team_generated)},
        'fixtures': {p.name: digest(p) for p in (OUT / 'resources').iterdir() if p.is_file()}}
    (evidence / 'source-guard.json').write_text(json.dumps(guard, indent=2) + '\n')
    run('git', 'diff', '--exit-code')

if __name__ == '__main__': main()
