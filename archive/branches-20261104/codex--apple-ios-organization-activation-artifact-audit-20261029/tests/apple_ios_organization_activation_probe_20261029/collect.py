#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only native diagnostic collection and independent original-ZIP audit."""
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from prepare import BASE, BOOK_HASH, CASES, CLASS, FORMAL, FORMAL_HASH, OUT, PACKAGE, PATHS, ROOT, render_ui, replace_once
sys.path.insert(0, str(ROOT / 'tests/apple_host'))
from collect_evidence import command
from evidence_contract import digest, require, tree_digest, inventory
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip

OUTCOMES = {'verification_completed', 'completion_window_failed', 'inapplicable_keyboard',
            'unsupported_return', 'return_did_not_dismiss', 'native_failure_or_exception'}

def native_results(raw):
    payload = json.loads(raw)
    require(isinstance(payload.get('testNodes'), list), 'native test tree missing')
    cases = []
    def walk(node, ancestry):
        require(isinstance(node, dict), 'invalid native node')
        labels = ancestry + [str(node.get('name', '')), str(node.get('nodeIdentifier', ''))]
        if node.get('nodeType') == 'Test Case':
            require(any(CLASS in re.findall(r'[A-Za-z_][A-Za-z_0-9]*', label) for label in labels), 'wrong native test class')
            case = owner(node.get('name') or node.get('nodeIdentifier'))
            cases.append({'name': case, 'result': node.get('result'), 'duration': node.get('duration'),
                          'node_identifier': node.get('nodeIdentifier'), 'class': CLASS})
        for child in node.get('children', []): walk(child, labels)
    for node in payload['testNodes']: walk(node, [])
    require(len(cases) == 6 and {c['name'] for c in cases} == set(CASES), 'wrong native selected cases')
    return cases

def verify_generated(folder, guard):
    retained = folder / 'generated'
    require(inventory(retained) == guard['retained_generated'], 'generated retained bytes differ')
    formal = (ROOT / FORMAL).read_text()
    require(digest(ROOT / FORMAL) == FORMAL_HASH, 'frozen formal source differs')
    require((retained / 'ui/ActivationProbeTests.swift').read_text() ==
            render_ui(formal, (ROOT / PACKAGE / 'ActivationProbeTests.swift').read_text()), 'generated UI reconstruction differs')
    original = (ROOT / 'tests/apple_host/make_xcodeproj.rb').read_text()
    expected = replace_once(original, "['3.40.0', '3.41.0'].include?(sdk_version)",
                            "['3.40.0', '3.41.0', '3.42.0'].include?(sdk_version)")
    expected = replace_once(expected, "page_theme == 'ON' && sdk_version != '3.41.0'",
                            "page_theme == 'ON' && !['3.41.0', '3.42.0'].include?(sdk_version)")
    require((retained / 'make_xcodeproj_sdk342.rb').read_text() == expected, 'retained original generator adapter differs')
    producer_generator = str(Path(guard['producer_workspace']) / 'build/ios-organization-activation-probe/make_xcodeproj_sdk342.rb')
    team = replace_once((ROOT / 'tests/reader_team24_apple/make_project.rb').read_text(),
                        "'tests/apple_host/make_xcodeproj.rb'", repr(producer_generator))
    require((retained / 'make_project_sdk342.rb').read_text() == team, 'retained project adapter differs')
    project = retained / 'project/EXReaderHost.xcodeproj'
    objects = plistlib.loads(command('plutil', '-convert', 'xml1', '-o', '-', project / 'project.pbxproj').encode())['objects']
    targets = [(key, value) for key, value in objects.items() if value.get('isa') == 'PBXNativeTarget'
               and value.get('name') == 'EXReaderHostUITests-iOS']
    require(len(targets) == 1, 'test target ambiguous')
    target_id, target = targets[0]
    phases = [objects[key] for key in target['buildPhases'] if objects[key]['isa'] == 'PBXSourcesBuildPhase']
    require(len(phases) == 1 and len(phases[0]['files']) == 1, 'unexpected test target sources')
    reference = objects[objects[phases[0]['files'][0]]['fileRef']]
    require(reference['path'] == '../ui/ActivationProbeTests.swift', 'selected test source is not retained generated UI')
    configs = objects[target['buildConfigurationList']]['buildConfigurations']
    require(all(objects[c]['buildSettings']['TEST_TARGET_NAME'] == 'EXReaderHost-iOS' for c in configs), 'wrong tested host')
    scheme = ET.fromstring((project / 'xcshareddata/xcschemes/EXReaderHost-iOS.xcscheme').read_text())
    testables = scheme.findall('.//TestableReference')
    require(len(testables) == 1 and testables[0].get('skipped', 'NO') == 'NO'
            and testables[0].find('BuildableReference').get('BlueprintIdentifier') == target_id, 'scheme wiring differs')
    return {'generated_bytes_reconstructed': True, 'native_project_reparsed': True, 'selected_test_source': reference['path']}

def owner(value):
    found = re.findall(r'\btest[0-9A-Za-z_]+\b', value or '')
    require(len(found) == 1 and found[0] in CASES, 'unexpected case: ' + str(value))
    return found[0]

def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)

def attachment_role(name):
    for prefix, role in [('activation-probe-receipt-', 'receipt'), ('ios-organization-steps-', 'frozen_steps'),
            ('ios-organization-screen-', 'final_screen'), ('ios-organization-tree-', 'final_tree')]:
        if name.startswith(prefix): return role
    for phase in ('pre-intervention', 'post-intervention', 'post-verify'):
        for kind in ('tree', 'screen'):
            if name.startswith('activation-probe-' + phase + '-' + kind + '-'): return phase + '_' + kind
    return None

def validate_roles(seen, receipts):
    require(all((case, role) in seen for case in CASES for role in ('receipt', 'frozen_steps', 'final_screen', 'final_tree')),
            'partial native trial receipts')
    for case, receipt in receipts.items():
        for sample in receipt['trace']:
            if sample['phase'] != 'poll':
                require(all((case, sample['phase'] + '_' + kind) in seen for kind in ('tree', 'screen')), 'phase capture missing')

def validate_receipt(case, native, receipt):
    require(receipt['schema'] == 1 and receipt['trial'] == case and owner(receipt['test']) == case, 'receipt case differs')
    require(receipt['arm'] == CASES[case] and receipt['product_accepted'] is False and receipt['formal_credit'] == 0,
            'diagnostic scope differs')
    index = list(CASES).index(case)
    require(receipt['observed_order'] == list(CASES)[:index + 1], 'actual trial order differs')
    require(number(receipt['started']) and number(receipt['finished']) and receipt['finished'] >= receipt['started'], 'trial times invalid')
    require(receipt['outcome'] in OUTCOMES and receipt['native_tap_calls'] in (0, 1), 'invalid outcome/activation count')
    require(receipt['return_tap_calls'] in (0, 1), 'Return retried')
    if CASES[case] == 'control': require(receipt['return_tap_calls'] == 0, 'control changed input')
    trace = receipt['trace']
    require(isinstance(trace, list) and len(trace) <= 512, 'unbounded trace')
    previous = receipt['started']
    for sample in trace:
        require(sample['phase'] in ('pre-intervention', 'post-intervention', 'post-verify', 'poll'), 'unknown phase')
        require(all(number(sample[k]) for k in ('started', 'finished', 'duration')), 'invalid sample time')
        require(previous <= sample['started'] <= sample['finished'] <= receipt['finished'] and sample['duration'] >= 0,
                'sample order/overhead differs')
        previous = sample['finished']
        if sample['target_count'] == 1:
            require(sample['target_id'] == 'organization.verify-original' and sample['target_role'] == 'Button', 'wrong target')
    if receipt['freshness_proved']:
        require(receipt['previous_app_stopped'] is True and receipt['initial_state_empty'] is True
                and receipt['initial_books'] == 0 and receipt['prebootstrap_proved'] is True, 'freshness proof missing')
        require(receipt['initial_groups'] == {kind + '.' + status: 0 for kind in ('shelf', 'tag', 'series')
                for status in ('active', 'removed')}, 'initial groups not empty')
        require(receipt['group_id'].startswith('organization.group.') and receipt['book_id'] == 'organization.book.epub:' + BOOK_HASH,
                'fixture/group identity differs')
    if 'native_tap_returned' in receipt:
        require(number(receipt['native_tap_started']) and number(receipt['native_tap_returned']) and number(receipt['deadline'])
                and receipt['started'] <= receipt['native_tap_started'] <= receipt['native_tap_returned'] <= receipt['finished']
                and abs(receipt['deadline'] - receipt['native_tap_returned'] - 60) < 0.000001, 'completion budget differs')
        for sample in trace:
            if sample['phase'] in ('post-verify', 'poll'):
                require(sample['started'] >= receipt['native_tap_returned'], 'post-tap timing differs')
                # A single in-flight AX operation may overrun; no new sample starts afterward.
                require(sample['started'] < receipt['deadline'], 'query started after deadline')
    if receipt['outcome'] == 'verification_completed':
        require(receipt['freshness_proved'] and receipt['native_tap_calls'] == 1 and receipt['completion_observed'] is True,
                'completion lacks prerequisites')
        require(receipt['native_tap_returned'] <= receipt['completion_observed_at'] <= receipt['deadline'], 'late completion accepted')
        require(any(s['phase'] in ('post-verify', 'poll') and '原件验证完成' in s.get('message', '')
                    and receipt['native_tap_returned'] <= s['started'] <= s['finished'] <= receipt['completion_observed_at']
                    for s in trace), 'completion has no within-window native trace sample')
        phases = [s['phase'] for s in trace]
        require(phases[:3] == ['pre-intervention', 'post-intervention', 'post-verify'] and all(p == 'poll' for p in phases[3:]),
                'observation schedule differs')
        before, after = trace[:2]
        require(all(before[k] == after[k] for k in ('group_id', 'book_id', 'selected_group', 'name', 'ordinal')), 'intervention changed identity/value')
        require(all(s['group_count'] == s['book_count'] == 1 and s['group_id'] == receipt['group_id']
                    and s['book_id'] == receipt['book_id'] for s in (before, after)), 'live native identities differ')
        if CASES[case] == 'return':
            require(receipt['return_tap_calls'] == 1 and before['keyboard_count'] == before['return_count'] == 1
                    and before['return_id'] == 'Return' and before['return_enabled'] and before['return_hittable']
                    and after['keyboard_count'] == 0, 'Return comparison not applicable')
    if native == 'Passed': require(receipt['outcome'] == 'verification_completed', 'native pass without original completion')

def validate_report(result):
    require(result['product_accepted'] is False and result['formal_credit'] == 0 and result['physical_device_execution'] is False,
            'scope promoted')
    require(result['frozen_product_source'] == BASE and result['sdk_version'] == '3.42.0', 'source/SDK differs')
    require(len(result['cases']) == 6 and {owner(c['name']) for c in result['cases']} == set(CASES), 'six selected cases missing')
    require(all(c['result'] in ('Passed', 'Failed') for c in result['cases']), 'skipped/unknown trial')
    require(set(result['receipts']) == set(CASES), 'receipts missing')
    groups = []
    previous_finish = None
    for case in CASES:
        native = next(c['result'] for c in result['cases'] if owner(c['name']) == case)
        receipt = result['receipts'][case]
        validate_receipt(case, native, receipt)
        if previous_finish is not None: require(previous_finish <= receipt['started'], 'trials overlap or reordered')
        previous_finish = receipt['finished']
        if receipt['freshness_proved']: groups.append(receipt['group_id'])
    require(len(groups) == len(set(groups)), 'fresh group identity reused')

def base_report():
    return {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'frozen_product_source': BASE, 'sdk_version': '3.42.0',
            'product_accepted': False, 'formal_credit': 0, 'physical_device_execution': False,
            'collection_complete': False, 'problems': [], 'cases': [], 'receipts': {}, 'retained': {}}

def collect():
    output = OUT / 'evidence'; output.mkdir(parents=True, exist_ok=True)
    result = base_report()
    try:
        require(command('git', 'rev-parse', 'HEAD') == result['source_sha'] and result['attempt'] == '1', 'source/attempt differs')
        guard = json.loads((output / 'source-guard.json').read_text())
        require(all(guard[k] == result[k] for k in ('source_sha', 'run_id', 'attempt', 'frozen_product_source', 'sdk_version')), 'guard identity differs')
        require(guard['all_existing_blobs_unchanged'] and guard['formal_reconstruction_equal'] and guard['formal_ui_sha256'] == FORMAL_HASH,
                'frozen source differs')
        require(guard['changed_paths'] == sorted(PATHS) and guard['selected_cases'] == list(CASES), 'admission scope differs')
        destination = (output / 'destination.txt').read_text().splitlines()
        require(len(destination) == 4 and destination[0] == 'platform=iOS Simulator,id=' + destination[1]
                and destination[2:] == ['iPhone SE (3rd generation)', 'com.apple.CoreSimulator.SimRuntime.iOS-26-2'], 'simulator differs')
        result['device'], result['runtime'] = destination[2:]
        app = OUT / 'DerivedData/Build/Products/Debug-iphonesimulator/EXReaderHost.app'
        info = plistlib.loads((app / 'Info.plist').read_bytes())
        require(info['EXRSourceSHA'] == result['source_sha'] and info['EXRSDKVersion'] == '3.42.0' and info['EXRPageThemeEnabled'] is True,
                'tested application differs')
        result['executable_sha256'] = digest(app / 'EXReaderHost')
        result['runtime_sha256'] = digest(app / 'Frameworks/libexreader.3.42.0.dylib')
        command('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, output / 'EXReaderHost.zip')
        result['retained']['EXReaderHost.zip'] = digest(output / 'EXReaderHost.zip')
        installed_path = command('xcrun', 'simctl', 'get_app_container', destination[1], 'org.exreader.host', 'app')
        installed = Path(installed_path)
        installed_info = plistlib.loads((installed / 'Info.plist').read_bytes())
        require(all(installed_info[k] == info[k] for k in ('EXRSourceSHA', 'EXRSDKVersion', 'EXRPageThemeEnabled')), 'installed app identity differs')
        components = ['EXReaderHost', 'Frameworks/libexreader.3.42.0.dylib'] + list(guard['fixtures'])
        installed_hashes = {p: digest(installed / p) for p in components}
        require(all(installed_hashes[p] == digest(app / p) for p in components), 'installed host/runtime/fixtures differ from built app')
        command('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', installed, output / 'EXReaderHost-installed.zip')
        result['retained']['EXReaderHost-installed.zip'] = digest(output / 'EXReaderHost-installed.zip')
        installed_identity = {'command': ['xcrun', 'simctl', 'get_app_container', destination[1], 'org.exreader.host', 'app'],
            'path': installed_path, 'basename': installed.name, 'source_sha': result['source_sha'], 'components': installed_hashes,
            'built_components_equal': True}
        (output / 'installed-app-identity.json').write_text(json.dumps(installed_identity, indent=2) + '\n')
        result['installed_app_verified'] = True
        for path, expected in guard['retained_generated'].items():
            require(digest(OUT / path) == expected, 'used generated source/project changed after admission')
        result['generated_wiring'] = verify_generated(output, guard)
        bundle = output / 'activation.xcresult'
        native_command = ['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', str(bundle), '--format', 'json']
        native_raw = command(*native_command)
        (output / 'native-test-results.json').write_text(native_raw + '\n')
        (output / 'native-command.json').write_text(json.dumps({'argv': native_command,
            'bundle': 'activation.xcresult', 'xcode_version': command('xcodebuild', '-version')}, indent=2) + '\n')
        result['cases'] = native_results(native_raw)
        attachments = output / 'attachments'
        command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', bundle, '--output-path', attachments)
        manifest = json.loads((attachments / 'manifest.json').read_text())
        seen = set()
        for group in manifest:
            case = owner(group.get('testIdentifier') or group.get('testName'))
            for item in group['attachments']:
                name, filename = item['suggestedHumanReadableName'], item['exportedFileName']
                role = attachment_role(name)
                if role is None: continue
                require(Path(filename).name == filename and (case, role) not in seen, 'unsafe/duplicate attachment')
                path = attachments / filename
                require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'invalid attachment size')
                if role == 'receipt': result['receipts'][case] = json.loads(path.read_text())
                elif role.endswith('screen'): require(path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'screenshot not PNG')
                elif role.endswith('tree'): require('Application' in path.read_text(), 'native tree missing')
                elif role == 'frozen_steps': require(owner(json.loads(path.read_text())['test']) == case, 'teardown identity differs')
                seen.add((case, role))
                result['retained'][str(path.relative_to(output))] = digest(path)
        validate_roles(seen, result['receipts'])
        validate_report(result)
        result['xcresult_sha256'] = tree_digest(bundle)
        (output / 'xcresult-inventory.json').write_text(json.dumps(inventory(bundle), indent=2, sort_keys=True) + '\n')
        for name in ('source-guard.json', 'destination.txt', 'xcodebuild.log', 'installed-app-identity.json',
                     'native-test-results.json', 'native-command.json', 'xcresult-inventory.json'):
            result['retained'][name] = digest(output / name)
        result['collection_complete'] = True
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    (output / 'diagnostic.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('receipts', 'retained')}), flush=True)
    for case, receipt in result['receipts'].items():
        print(json.dumps({'diagnostic_only': True, 'case': case, 'arm': receipt.get('arm'), 'outcome': receipt.get('outcome'),
            'freshness_proved': receipt.get('freshness_proved'), 'keyboard_applicable': receipt.get('keyboard_applicable'),
            'native_tap_calls': receipt.get('native_tap_calls'), 'return_tap_calls': receipt.get('return_tap_calls'),
            'trace': receipt.get('trace', [])}), flush=True)
    return 0 if result['collection_complete'] else 1

def safe_names(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)) and all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
            and '\\' not in n for n in names), 'unsafe/duplicate ZIP names')

def extract_evidence(archive, target):
    safe_names(archive)
    require(len(archive.infolist()) <= 20000 and sum(i.file_size for i in archive.infolist()) <= 2 * 1024 ** 3,
            'diagnostic archive exceeds bounded extraction size')
    for item in archive.infolist():
        require(stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK, 'evidence ZIP symlink refused')
    archive.extractall(target)

def audit():
    output = ROOT / 'build/ios-organization-activation-audit'; output.mkdir(parents=True, exist_ok=True)
    summary = base_report(); summary['diagnostic_complete'] = False
    try:
        source, run, attempt = (summary[k] for k in ('source_sha', 'run_id', 'attempt'))
        require(attempt == '1', 'no diagnostic rerun authorized')
        jobs = fetch(f'actions/runs/{run}/attempts/{attempt}/jobs?per_page=100')['jobs']
        producers = [j for j in jobs if j['name'] == 'iPhone organization activation diagnostic']
        require(len(producers) == 1 and producers[0]['head_sha'] == source
                and producers[0]['conclusion'] in ('success', 'failure'), 'producer identity/status missing')
        artifact_name = f'ios-organization-activation-probe-{run}-{attempt}'
        matches = [a for a in fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts'] if a['name'] == artifact_name]
        require(len(matches) == 1, 'artifact missing/ambiguous')
        item = matches[0]
        require(not item['expired'] and item['workflow_run']['head_sha'] == source
                and str(item['workflow_run']['id']) == run, 'artifact source/run differs')
        raw = download_artifact_zip(item['id']); checksum = hashlib.sha256(raw).hexdigest()
        require(len(raw) == item['size_in_bytes'] and item['digest'] == 'sha256:' + checksum, 'original ZIP identity differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            safe_names(archive)
            result = json.loads(archive.read('diagnostic.json'))
            require(all(result[k] == summary[k] for k in ('source_sha', 'run_id', 'attempt', 'frozen_product_source', 'sdk_version')), 'report identity differs')
            require(result['collection_complete'] is True and result['problems'] == [], 'incomplete diagnostic')
            validate_report(result)
            native_raw = archive.read('native-test-results.json')
            require(native_results(native_raw) == result['cases'], 'summary differs from raw native test results')
            for path, expected in result['retained'].items(): require(hashlib.sha256(archive.read(path)).hexdigest() == expected, 'retained digest differs: ' + path)
            guard = json.loads(archive.read('source-guard.json'))
            require(all(guard[k] == summary[k] for k in ('source_sha', 'run_id', 'attempt', 'frozen_product_source', 'sdk_version'))
                    and guard['all_existing_blobs_unchanged'] and guard['formal_reconstruction_equal']
                    and guard['formal_ui_sha256'] == FORMAL_HASH and guard['changed_paths'] == sorted(PATHS)
                    and guard['selected_cases'] == list(CASES), 'source guard differs')
            sdk = guard['sdk_package_identity']
            require((sdk['source_sha'], sdk['run_id'], sdk['attempt'], sdk['product']['sdk_version']) ==
                    (source, run, attempt, '3.42.0'), 'SDK identity differs')
            destination = archive.read('destination.txt').decode().splitlines()
            require(len(destination) == 4 and destination[0] == 'platform=iOS Simulator,id=' + destination[1]
                    and destination[2:] == ['iPhone SE (3rd generation)', 'com.apple.CoreSimulator.SimRuntime.iOS-26-2']
                    and result['device'] == destination[2] and result['runtime'] == destination[3], 'original simulator differs')
            with zipfile.ZipFile(io.BytesIO(archive.read('EXReaderHost.zip'))) as program:
                safe_names(program); prefix = 'EXReaderHost.app/'
                info = plistlib.loads(program.read(prefix + 'Info.plist'))
                require(info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.42.0'
                        and info['EXRPageThemeEnabled'] is True, 'original tested app differs')
                require(hashlib.sha256(program.read(prefix + 'EXReaderHost')).hexdigest() == result['executable_sha256'], 'executable differs')
                require(hashlib.sha256(program.read(prefix + 'Frameworks/libexreader.3.42.0.dylib')).hexdigest() == result['runtime_sha256'], 'runtime differs')
                for name, expected in guard['fixtures'].items(): require(hashlib.sha256(program.read(prefix + name)).hexdigest() == expected, 'fixture differs: ' + name)
            installed = json.loads(archive.read('installed-app-identity.json'))
            require(result['installed_app_verified'] is True and installed['built_components_equal'] is True
                    and installed['source_sha'] == source and installed['basename'] == 'EXReaderHost.app'
                    and installed['command'] == ['xcrun', 'simctl', 'get_app_container', destination[1], 'org.exreader.host', 'app'],
                    'installed app identity missing')
            expected_components = dict(guard['fixtures'], **{'EXReaderHost': result['executable_sha256'],
                    'Frameworks/libexreader.3.42.0.dylib': result['runtime_sha256']})
            require(installed['components'] == expected_components, 'installed components differ')
            with zipfile.ZipFile(io.BytesIO(archive.read('EXReaderHost-installed.zip'))) as program:
                safe_names(program); prefix = installed['basename'] + '/'
                installed_info = plistlib.loads(program.read(prefix + 'Info.plist'))
                require(installed_info['EXRSourceSHA'] == source and installed_info['EXRSDKVersion'] == '3.42.0'
                        and installed_info['EXRPageThemeEnabled'] is True, 'installed retained program differs')
                for path, expected in expected_components.items():
                    require(hashlib.sha256(program.read(prefix + path)).hexdigest() == expected, 'installed retained component differs')
            manifest = json.loads(archive.read('attachments/manifest.json'))
            original_receipts, seen = {}, set()
            for group in manifest:
                case = owner(group.get('testIdentifier') or group.get('testName'))
                for entry in group['attachments']:
                    role = attachment_role(entry['suggestedHumanReadableName'])
                    if role is None: continue
                    filename = entry['exportedFileName']
                    require(Path(filename).name == filename and (case, role) not in seen, 'unsafe/duplicate original attachment')
                    path = 'attachments/' + filename; value = archive.read(path)
                    require(0 < len(value) <= 16 * 1024 * 1024 and result['retained'][path] == hashlib.sha256(value).hexdigest(),
                            'original attachment not bound')
                    if role == 'receipt': original_receipts[case] = json.loads(value)
                    elif role.endswith('screen'): require(value[:8] == b'\x89PNG\r\n\x1a\n', 'original screenshot not PNG')
                    elif role.endswith('tree'): require('Application' in value.decode(), 'original native tree missing')
                    elif role == 'frozen_steps': require(owner(json.loads(value)['test']) == case, 'original teardown case differs')
                    seen.add((case, role))
            require(original_receipts == result['receipts'], 'summary differs from original trial receipts')
            validate_roles(seen, original_receipts)
            with tempfile.TemporaryDirectory(prefix='ios-activation-audit-') as temporary:
                evidence = Path(temporary); extract_evidence(archive, evidence)
                result_inventory = json.loads((evidence / 'xcresult-inventory.json').read_text())
                require(inventory(evidence / 'activation.xcresult') == result_inventory
                        and tree_digest(evidence / 'activation.xcresult') == result['xcresult_sha256'], 'original xcresult inventory/hash differs')
                recorded = json.loads((evidence / 'native-command.json').read_text())
                require(recorded['bundle'] == 'activation.xcresult' and recorded['argv'][:6] ==
                        ['xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path']
                        and recorded['argv'][6] == str(Path(guard['producer_workspace']) /
                            'build/ios-organization-activation-probe/evidence/activation.xcresult')
                        and recorded['argv'][7:] == ['--format', 'json'], 'native result command differs')
                replay = command('xcrun', 'xcresulttool', 'get', 'test-results', 'tests', '--path', evidence / 'activation.xcresult', '--format', 'json')
                (output / 'independent-native-test-results.json').write_text(replay + '\n')
                require(native_results(replay) == result['cases'], 'independent xcresult replay differs')
                summary['generated_wiring'] = verify_generated(evidence, guard)
                summary['independent_xcresult_replayed'] = True
                summary['installed_app_verified'] = True
                summary['producer_xcode_version'] = recorded['xcode_version']
                summary['audit_xcode_version'] = command('xcodebuild', '-version')
        native_passed = sum(c['result'] == 'Passed' for c in result['cases'])
        if native_passed < 6: require(producers[0]['conclusion'] == 'failure', 'native failures were masked')
        else: require(producers[0]['conclusion'] == 'success', 'unexplained producer failure')
        summary.update({'diagnostic_complete': True, 'collection_complete': True,
            'producer_job': producers[0]['id'], 'producer_conclusion': producers[0]['conclusion'],
            'artifact': {'id': item['id'], 'name': artifact_name, 'bytes': len(raw), 'sha256': checksum},
            'native_passed': native_passed, 'native_failed': 6 - native_passed,
            'cases': result['cases'],
            'trials': [{'case': c, 'arm': CASES[c], 'outcome': result['receipts'][c]['outcome'],
                        'freshness_proved': result['receipts'][c]['freshness_proved'],
                        'keyboard_applicable': result['receipts'][c].get('keyboard_applicable')} for c in CASES],
            'root_cause_proved': False, 'no_acceptance_suffix_executed': True})
    except Exception as error:
        summary['problems'].append(type(error).__name__ + ': ' + str(error))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps(summary), flush=True)
    return 0 if summary['diagnostic_complete'] else 1

if __name__ == '__main__':
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    require(len(sys.argv) == 2 and sys.argv[1] in ('collect', 'audit'), 'explicit mode required')
    raise SystemExit(collect() if sys.argv[1] == 'collect' else audit())
