#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Distinct diagnostic continuation; records strict failures, never grants acceptance."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import zipfile
from urllib.parse import urlsplit
from continuation_contract import BASE, BUNDLE, CASE, ROOT, STAGES, attachments, case_name, guard, require, sha, verdict
from fixture import fixture
from privacy_scan import needles, scan_file, scan_roots, optional_entries, verify_optional_entries
from log_evidence import attribute_unified_log, retain_product_log
from ui_observations import parse_ui_observations
from continuation_lifecycle import ContinuationLifecycle, atomic_result, seal_files, verify_lifecycle, write_unsealed
sys.path[:0] = [str(ROOT / 'tests/apple_host'), str(ROOT / 'tools')]


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    parser = argparse.ArgumentParser(); parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    platform = parser.parse_args().platform
    changes = guard()
    out = ROOT / 'build/apple-password-continuation' / platform
    evidence = out / 'evidence'; evidence.mkdir(parents=True, exist_ok=False)
    result = {'accepted': False, 'diagnostic_only': True, 'sequence_complete': False, 'strict_privacy_checks': {},
              'base_sha': BASE, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'platform': platform, 'sdk_version': '3.42.0', 'changed_paths': changes, 'physical_device': False,
              'full_f10_accepted': False, 'dedicated_forget_tested': False, 'synthetic_canaries_only': True,
              'secure_field_display_is_secret_absence_proof': False,
              'log_scope': 'captured EXReaderHost unified logs including info/debug; not arbitrary OS logs or XCTest input activities',
              'commands': [], 'checkpoints': {}, 'log_attribution': {}, 'failure': None}
    udid = None
    lifecycle = ContinuationLifecycle(platform)
    fixture_records = None
    def run(role, *argv, env=None, capture=False):
        # Never echo argv/env: credentials enter only the XCTest runner environment.
        done = lifecycle.command(argv, cap=4800, check=False, cwd=ROOT, env=env, max_capture=None)
        (evidence / (role + '.log')).write_bytes(done.stdout + done.stderr)
        result['commands'].append({'role': role, 'exit': done.returncode})
        require(done.returncode == 0, role + ' failed')
        return done.stdout.decode().strip() if capture else None
    def helper(role, *paths):
        done = lifecycle.command([sys.executable, ROOT / 'tests/apple_password_privacy_20261028/continuation_lifecycle.py',
            role, *paths], cap=4800, check=False, cwd=ROOT, max_capture=None)
        (evidence / (role + '-helper.log')).write_bytes(done.stdout + done.stderr)
        require(done.returncode == 0, 'bounded frozen helper failed')
        return json.loads(done.stdout)
    try:
        target = 'macos' if platform == 'macos' else 'iphonesimulator'
        install = ROOT / 'build/password-sdk-input' / ('password-sdk-' + target + '-' + result['run_id'] + '-' + result['attempt'])
        identity = json.loads((install / 'identity.json').read_text())
        require((identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) ==
                (result['source_sha'], result['run_id'], result['attempt'], target), 'SDK input identity differs')
        require(identity['product']['sdk_version'] == '3.42.0' and identity['product']['wave3_enabled'] and identity['product']['selector_bytes_candidate'], 'SDK profile differs')
        shutil.copyfile(install / 'identity.json', evidence / 'sdk-identity.json')
        resources, project, derived = out / 'resources', out / 'project', out / 'derived'
        run('fixtures', sys.executable, 'tests/apple_host/prepare_fixtures.py', '--resources', resources)
        original = (resources / 'Sample.epub').read_bytes()
        (evidence / 'source.epub').write_bytes(original)
        shutil.copyfile(resources / 'manifest.json', evidence / 'resource-manifest.json')
        run('project', 'ruby', ROOT / 'tests/apple_password_privacy_20261028/make_continuation_project.rb', project, resources, evidence / 'adapter', platform)
        if platform == 'macos':
            destination, scheme, suffix, signing = 'platform=macOS', 'EXReaderHost-macOS', 'Debug', 'YES'
            require(not (Path.home() / 'Library/Application Support/EXReader').exists(), 'refuse pre-existing product profile')
            require(not (Path.home() / ('Library/Preferences/' + BUNDLE + '.plist')).exists(), 'refuse pre-existing private preferences')
        else:
            devices = json.loads(run('devices', 'xcrun', 'simctl', 'list', 'devices', 'available', '--json', capture=True))
            prefix = 'iPhone' if platform == 'iphone' else 'iPad'
            runtime, name, udid = max((runtime, device['name'], device['udid']) for runtime, items in devices['devices'].items()
                for device in items if device.get('isAvailable') and device['name'].startswith(prefix))
            result['simulator'] = {'runtime': runtime, 'name': name, 'udid': udid}
            lifecycle.command(['xcrun', 'simctl', 'shutdown', udid], check=False)
            run('erase', 'xcrun', 'simctl', 'erase', udid); run('boot', 'xcrun', 'simctl', 'boot', udid)
            run('boot-ready', 'xcrun', 'simctl', 'bootstatus', udid, '-b')
            destination, scheme, suffix, signing = 'platform=iOS Simulator,id=' + udid, 'EXReaderHost-iOS', 'Debug-iphonesimulator', 'NO'
        common = ['-project', project / 'EXReaderHost.xcodeproj', '-scheme', scheme, '-destination', destination,
                  '-derivedDataPath', derived, 'EXR_SDK_DIR=' + str(install / 'sdk'),
                  'EXR_PRODUCTS_DIR=' + str(install / 'products'), 'CODE_SIGNING_ALLOWED=' + signing]
        run('build-for-testing', 'xcodebuild', 'build-for-testing', *common)
        built = derived / 'Build/Products' / suffix; app = built / 'EXReaderHost.app'
        prefix = 'Contents/' if platform == 'macos' else ''
        binary = app / (prefix + ('MacOS/EXReaderHost' if platform == 'macos' else 'EXReaderHost'))
        info = plistlib.loads((app / (prefix + 'Info.plist')).read_bytes())
        require(info['CFBundleIdentifier'] == BUNDLE and info['EXRSourceSHA'] == result['source_sha'] and info['EXRSDKVersion'] == '3.42.0' and info['EXRPageThemeEnabled'] is True, 'actual app identity differs')
        result['provider_check'] = helper('inspect', binary, built / 'EXReaderHost.link.map')
        shutil.copyfile(built / 'EXReaderHost.link.map', evidence / 'EXReaderHost.link.map')
        runtime_library = app / (prefix + 'Frameworks/libexreader.3.42.0.dylib')
        require(runtime_library.is_file(), 'packaged runtime absent')
        user = 'privacy-user-' + secrets.token_hex(16)
        passwords = {role: 'Privacy-' + secrets.token_hex(32) + '!%:+' for role in ('remembered', 'session')}
        authorizations = {role: 'Basic ' + base64.b64encode((user + ':' + value).encode()).decode() for role, value in passwords.items()}
        # These are explicitly synthetic oracle inputs, not product output or real account secrets.
        oracle = {'synthetic_only': True, 'source_sha': result['source_sha'], 'run_id': result['run_id'],
                  'attempt': result['attempt'], 'user': user, 'passwords': passwords}
        (evidence / 'synthetic-oracle-input.json').write_text(json.dumps(oracle, indent=2) + '\n')
        values = {'user': user.encode()}
        for role, password in passwords.items():
            values[role] = password.encode(); values[role + '-pair'] = (user + ':' + password).encode()
            values[role + '-authorization'] = authorizations[role].encode()
        variants = needles(values)
        active_root = [None]
        def locations():
            if udid:
                container = Path(lifecycle.command(['xcrun', 'simctl', 'get_app_container', udid, BUNDLE, 'data']).stdout.decode().strip())
                return container / 'Library/Application Support/EXReader', {'container': container}
            profile = Path.home() / 'Library/Application Support/EXReader'
            roots = {'profile': profile}
            # Only this package's preferences/cache are in scope; never scan a runner's whole home or Keychain.
            extras = {'preferences': Path.home() / ('Library/Preferences/' + BUNDLE + '.plist'),
                      'cache': Path.home() / ('Library/Caches/' + BUNDLE),
                      'saved-state': Path.home() / ('Library/Saved Application State/' + BUNDLE + '.savedState')}
            return profile, (roots, extras)
        def checkpoint(stage, requests):
            require(stage in STAGES and stage == STAGES[len(result['checkpoints'])], 'out-of-order post-exit observation')
            profile, roots = locations()
            metadata = json.loads((profile / 'accounts.json').read_text())
            matches = [value for value in metadata if value['root'] == active_root[0]]
            require(len(metadata) == len(matches) == 1 and matches[0]['anonymous'] is False, 'actual private account differs')
            record = matches[0]; account = profile / 'accounts' / record['id']
            with sqlite3.connect((account / 'library.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as database:
                books = database.execute('SELECT source FROM books ORDER BY id').fetchall()
            require(len(books) == 1 and books[0][0] == original, 'credential operation changed original')
            staging = out / ('snapshot-' + stage); staging.mkdir()
            preferences = []
            if platform == 'macos':
                roots, extras = roots
                extras_before = optional_entries(extras)
                absence = []
                for label, path in extras.items():
                    try: mode = path.lstat().st_mode
                    except FileNotFoundError:
                        absence.append(label); continue
                    if stat.S_ISDIR(mode): roots[label] = path
                    elif stat.S_ISREG(mode):
                        actual = scan_file(path, variants)
                        require(not actual['hits'], 'canary in actual product preferences')
                        destination = staging / label; destination.mkdir()
                        shutil.copyfile(path, destination / path.name)
                        require(sha(destination / path.name) == actual['sha256'] and sha(path) == actual['sha256'], 'preferences changed during copy')
                        preferences.append((path, actual))
                        roots[label] = destination
                    else: require(False, 'linked or special private macOS root')
            else: absence = []
            command = ['xcrun', 'simctl', 'spawn', udid] if udid else []
            done = lifecycle.command(command + ['log', 'show', '--style', 'json', '--info', '--debug', '--last', '30m',
                '--predicate', 'process == "EXReaderHost"'], cap=60, check=False, max_capture=None)
            # Retain complete captured bytes before scan/capture refusal. These
            # sensitive synthetic-only artifacts are never printed to console.
            log_root = retain_product_log(evidence, stage, platform, result['source_sha'], result['run_id'],
                                          result['attempt'], done.stdout, done.stderr, done.returncode)
            require(done.returncode == 0, 'actual product log capture failed')
            require(bool(done.stdout.strip()), 'actual product log capture was empty')
            roots['product-log'] = log_root
            scans = scan_roots(roots, variants)
            (evidence / (stage + '-privacy-scan.json')).write_text(json.dumps(scans, indent=2) + '\n')
            # Primary byte evidence must survive any ancillary attribution issue.
            attribution = attribute_unified_log(done.stdout, variants)
            result['log_attribution'][stage] = attribution
            (evidence / (stage + '-safe-log-attribution.json')).write_text(json.dumps(attribution, indent=2) + '\n')
            # This distinct probe acknowledges complete observation, not clean
            # privacy. The original strict runner still refuses this condition.
            strict_privacy_passed = all(scan['accepted'] for scan in scans.values())
            result['strict_privacy_checks'][stage] = strict_privacy_passed
            destination = evidence / (stage + '-product.zip')
            with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
                for label, proof in scans.items():
                    archive.writestr(label + '/', b'')
                    for item in proof['directories']:
                        archive.writestr(label + '/' + item['path'] + '/', b'')
                    for item in proof['files']:
                        path = roots[label] / item['path']
                        require(sha(path) == item['sha256'] and path.stat().st_size == item['bytes'], 'product file changed before archive')
                        archive.write(path, label + '/' + item['path'])
            # Re-read actual compressed members, not just source metadata. A
            # mutation of an already-read prefix or earlier root cannot certify
            # different bytes than the ones retained as evidence.
            with zipfile.ZipFile(destination) as archive:
                for label, proof in scans.items():
                    for item in proof['files']:
                        checksum, total = hashlib.sha256(), 0
                        with archive.open(label + '/' + item['path']) as file:
                            for data in iter(lambda: file.read(1024 * 1024), b''):
                                checksum.update(data); total += len(data)
                        require((checksum.hexdigest(), total) == (item['sha256'], item['bytes']), 'archived bytes differ from privacy scan')
            require(scan_roots(roots, variants) == scans, 'private files changed before snapshot publication')
            for path, actual in preferences:
                require(scan_file(path, variants) == actual, 'actual preferences changed after copied scan')
            if platform == 'macos': verify_optional_entries(extras, extras_before)
            previous_count = list(result['checkpoints'].values())[-1]['network_requests'] if result['checkpoints'] else 0
            fresh = requests[previous_count:]
            if stage == 'remember_closed': require(not requests, 'unexpected background sync')
            elif stage == 'session_reopened_missing': require(not fresh, 'forgotten persisted/session credential still reached network')
            else:
                expected = 'remembered' if stage == 'remember_reopened' else 'session'
                require(fresh and all(value['credential'] == expected for value in fresh), 'wrong actual native credential used')
                shards = {value['path'].rsplit('/', 2)[-2] for value in fresh if value['method'] == 'PROPFIND' and
                          re.fullmatch(re.escape(urlsplit(active_root[0]).path) + r'exreader-sync-v1/revisions/[0-9a-f]{2}/', value['path'])}
                require(shards == {format(index, '02x') for index in range(256)}, 'authenticated native sweep incomplete')
            result['checkpoints'][stage] = {'profile_id': record['id'], 'network_requests': len(requests), 'scans': scans,
                'strict_privacy_passed': strict_privacy_passed,
                'absent_mac_roots': absence, 'archive': destination.name, 'archive_sha256': sha(destination),
                'sdk_original_sha256': hashlib.sha256(original).hexdigest(), 'original_bytes': len(original)}
            (evidence / 'checkpoints.json').write_text(json.dumps(result['checkpoints'], indent=2) + '\n')
        endpoint = '/privacy-' + secrets.token_hex(12) + '/'
        with fixture(out / 'fixture-private', authorizations, checkpoint, endpoint, lifecycle=lifecycle) as (root, entries, requests, failures, certificate):
            active_root[0] = root
            fixture_records = (requests, failures)
            result['root'] = root
            if udid: run('trust-simulator', 'xcrun', 'simctl', 'keychain', udid, 'add-root-cert', certificate)
            xcresult = evidence / 'privacy.xcresult'
            run('native', 'xcodebuild', 'test-without-building', *common, '-resultBundlePath', xcresult,
                    '-parallel-testing-enabled', 'NO', '-test-timeouts-enabled', 'YES',
                    '-default-test-execution-time-allowance', '240', '-maximum-test-execution-time-allowance', '360',
                    env=dict(os.environ, TEST_RUNNER_EXR_PRIVACY_ROOT=root, TEST_RUNNER_EXR_PRIVACY_USER=user,
                             TEST_RUNNER_EXR_PRIVACY_REMEMBERED=passwords['remembered'], TEST_RUNNER_EXR_PRIVACY_SESSION=passwords['session']))
        # Fixture exit now owns the complete request-thread drain. These reads
        # cannot race an admitted handler, including after a client timeout.
        require(not failures and list(result['checkpoints']) == STAGES, 'privacy observation incomplete')
        require(len([body for body in entries.values() if body == original]) == 1, 'actual remote original differs')
        result['cases'] = helper('cases', xcresult)
        require(len(result['cases']) == 1 and case_name(result['cases'][0]['name']) == CASE and result['cases'][0]['result'] == 'Passed', 'native case failed')
        run('attachments', 'xcrun', 'xcresulttool', 'export', 'attachments', '--path', xcresult, '--output-path', evidence / 'attachments')
        result['native_stages'], result['screenshots'] = attachments(evidence / 'attachments')
        require(all(value['profile_id'] == result['native_stages']['profile'] for value in result['checkpoints'].values()), 'UI/storage profile mismatch')
        run('program-archive', 'ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, evidence / 'program.zip')
        result['program'] = {'sha256': sha(binary), 'bytes': binary.stat().st_size, 'runtime_sha256': sha(runtime_library),
                             'archive_sha256': sha(evidence / 'program.zip')}
        result['diagnostic_verdict'] = verdict(result['strict_privacy_checks'])
        result['sequence_complete'] = True
    except Exception as error:
        # Arbitrary framework exceptions can include typed synthetic values; do not echo them.
        result['failure'] = type(error).__name__
    finally:
        if udid:
            stopped = lifecycle.cleanup_command('simulator-shutdown', ['xcrun', 'simctl', 'shutdown', udid])
            cleaned = lifecycle.cleanup_command('simulator-erase', ['xcrun', 'simctl', 'erase', udid])
            # Do not read a mutable callback-owned dictionary on failed drain.
            if lifecycle.drained:
                result['simulator_removed_fixture_state'] = stopped and cleaned
                if not (stopped and cleaned): result['sequence_complete'] = False
        if lifecycle.certificate_delete is not None and lifecycle.cleanup['certificate'] == 'pending':
            lifecycle.cleanup_command('certificate', lifecycle.certificate_delete)
        try:
            receipt = lifecycle.receipt()
            verify_lifecycle(receipt, platform)
            lifecycle.remaining()
            require(fixture_records is not None, 'drained fixture records absent')
            requests, failures = fixture_records
            (evidence / 'requests.json').write_text(json.dumps(requests, indent=2) + '\n')
            (evidence / 'fixture-failures.json').write_text(json.dumps(failures) + '\n')
            if result['checkpoints']:
                require((evidence / 'checkpoints.json').read_text() == json.dumps(result['checkpoints'], indent=2) + '\n',
                        'stable checkpoint metadata differs')
            try:
                result['ui_state_observations'] = parse_ui_observations(evidence / 'native.log')
            except Exception:
                result['ui_state_observations'] = {'valid': False, 'observed': False,
                    'records': [], 'failure': 'unavailable-or-invalid', 'raw_ui_text_printed': False,
                    'privacy_acceptance': False}
            result['lifecycle'] = receipt
            result['evidence_sealed'] = True
            result['files'] = seal_files(evidence, deadline=lifecycle.deadline)
            lifecycle.remaining()
            atomic_result(evidence, result, deadline=lifecycle.deadline)
            print(json.dumps({key: result[key] for key in ('accepted', 'diagnostic_only', 'sequence_complete', 'strict_privacy_checks',
                  'source_sha', 'platform', 'failure', 'full_f10_accepted', 'log_attribution', 'ui_state_observations',
                  'lifecycle', 'evidence_sealed')}), flush=True)
        except Exception:
            # A live daemon callback cannot be safely cancelled in Python.
            # Publish no normal result/files manifest and inspect no mutable
            # callback-owned dictionaries. Process exit terminates its writers
            # before Actions can upload the raw, explicitly unsealed evidence.
            refusal = write_unsealed(evidence, os.environ['GITHUB_SHA'], platform, lifecycle)
            print(json.dumps(refusal, sort_keys=True), flush=True)
            raise RuntimeError('continuation evidence unsealed; acceptance remains false') from None
    require(result['sequence_complete'], 'diagnostic sequence incomplete; strict/native/F10 acceptance remains false')

if __name__ == '__main__': main()
