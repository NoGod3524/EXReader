#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Retain native results even on failure, and accept only exact passed cases."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import sys
from contract import BASE, CASES
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import command, load_results
from evidence_contract import digest, require, tree_digest

def owner(value):
    names = re.findall(r'\btest[A-Za-z0-9_]+\b', value or '')
    require(len(names) == 1 and names[0] in CASES, 'unknown case: ' + str(value))
    return names[0]

def observations(case, value):
    require(isinstance(value, dict), 'missing native observations')
    if 'LifecycleMembership' in case:
        kind = {'testShelfLifecycleMembershipAndRestart': 'shelf', 'testTagLifecycleMembershipAndRestart': 'tag',
                'testSeriesLifecycleMembershipAndRestart': 'series'}[case]
        require(value['kind'] == kind and value['removed_on'] == '1' and value['removed_off'] == '0', 'toggle/kind differs')
        require(value['group_id'].startswith('organization.group.') and value['book_id'].startswith('organization.book.'), 'missing native identity')
        require(value['final_membership'] == 'member', 'final membership missing')
        require(value['ordinal'] == ('0' if kind == 'tag' else '2'), 'ordinal differs')
        require(value['final_member_label'].endswith(' · ' + value['ordinal']), 'member ordering missing')
    elif case == 'testNestedShelfIdentityAndParentNavigation':
        require(value['parent_id'] != value['child_id'], 'parent and child alias')
        require(all(value[k].startswith('organization.group.') for k in ('parent_id', 'child_id')), 'nested IDs missing')
    else:
        require(value['group_id'].startswith('organization.group.'), 'retained group ID missing')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform', choices=['iphone', 'ipad'], required=True)
    args = p.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    output = ROOT / 'build/ios-organization/evidence'
    output.mkdir(parents=True, exist_ok=True)
    result = {'accepted': False, 'platform': args.platform, 'source_sha': os.environ['GITHUB_SHA'],
        'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'sdk_version': '3.42.0',
        'common_base': BASE, 'physical_device_execution': False, 'complete_product_accepted': False,
        'scope': 'iOS simulator organization; independent-writer stale snapshot, not simultaneous process sync',
        'problems': [], 'cases': [], 'retained': {}}
    try:
        require(command('git', 'rev-parse', 'HEAD') == result['source_sha'], 'checkout differs')
        guard = json.loads((output / 'source-guard.json').read_text())
        require(all(guard[k] == result[k] for k in ('source_sha', 'run_id', 'attempt', 'common_base', 'sdk_version')), 'guard differs')
        destination = (output / 'destination.txt').read_text().splitlines()
        require(len(destination) == 4 and destination[2].lower().startswith(args.platform), 'wrong device family')
        require(destination[0] == 'platform=iOS Simulator,id=' + destination[1], 'destination differs')
        result['device'] = destination[2]; result['runtime'] = destination[3]
        app = ROOT / 'build/ios-organization/DerivedData/Build/Products/Debug-iphonesimulator/EXReaderHost.app'
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        require(info['EXRSourceSHA'] == result['source_sha'] and info['EXRSDKVersion'] == '3.42.0', 'application differs')
        require(info['EXRPageThemeEnabled'] is True, 'theme identity differs')
        result['executable_sha256'] = digest(app / 'EXReaderHost')
        runtime = app / 'Frameworks/libexreader.3.42.0.dylib'
        require(runtime.is_file(), '3.42 runtime missing')
        result['runtime_sha256'] = digest(runtime)
        program = output / 'EXReaderHost.zip'
        command('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, program)
        result['retained']['EXReaderHost.zip'] = digest(program)
        bundle = output / 'organization.xcresult'
        cases = load_results(bundle); result['cases'] = cases
        # Export diagnostics before rejecting failures: no skipped collector.
        attachments = output / 'attachments'
        command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', bundle, '--output-path', attachments)
        manifest = json.loads((attachments / 'manifest.json').read_text())
        failed = {owner(c['name']) for c in cases if c['result'] != 'Passed'}
        # Fixture-only failure diagnostics are visible in decoded Actions logs.
        # They do not substitute for passed cases or the original ZIP audit.
        for group in manifest:
            case = owner(group.get('testIdentifier') or group.get('testName'))
            if case not in failed: continue
            for item in group['attachments']:
                name, filename = item['suggestedHumanReadableName'], item['exportedFileName']
                if not name.startswith(('ios-organization-steps-', 'ios-organization-tree-')): continue
                require(Path(filename).name == filename, 'unsafe diagnostic attachment')
                path = attachments / filename
                require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'invalid diagnostic size')
                with path.open('rb') as stream: prefix = stream.read(65537)
                print(json.dumps({'diagnostic_only': True, 'case': case, 'attachment': filename,
                    'sha256': digest(path), 'truncated': len(prefix) > 65536,
                    'text': prefix[:65536].decode('utf-8', errors='replace')}), flush=True)
        require(len(cases) == len(CASES) and {owner(c['name']) for c in cases} == set(CASES)
                and all(c['result'] == 'Passed' for c in cases), 'native cases missing, skipped or failed')
        seen = set()
        for group in manifest:
            case = owner(group.get('testIdentifier') or group.get('testName'))
            for item in group['attachments']:
                name, filename = item['suggestedHumanReadableName'], item['exportedFileName']
                require(Path(filename).name == filename, 'unsafe attachment')
                path = attachments / filename
                require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'invalid attachment size')
                if name.startswith('ios-organization-steps-'):
                    role = 'steps'; value = json.loads(path.read_text())
                    require(owner(value['test']) == case and value['steps'] == CASES[case], 'step sequence differs')
                    observations(case, value['observations'])
                elif name.startswith('ios-organization-screen-'):
                    role = 'screen'; require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'screen not PNG')
                elif name.startswith('ios-organization-tree-'):
                    role = 'tree'; require('organization.' in path.read_text(), 'native tree missing')
                else: continue
                require((case, role) not in seen, 'duplicate evidence')
                seen.add((case, role))
                result['retained'][str(path.relative_to(output))] = digest(path)
        require(seen == {(c, r) for c in CASES for r in ('steps', 'screen', 'tree')}, 'incomplete evidence')
        result['xcresult_sha256'] = tree_digest(bundle)
        for name in ('source-guard.json', 'destination.txt', 'xcodebuild.log'):
            result['retained'][name] = digest(output / name)
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    (output / 'organization-ui.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result), flush=True)
    return 0 if result['accepted'] else 1

if __name__ == '__main__': raise SystemExit(main())
