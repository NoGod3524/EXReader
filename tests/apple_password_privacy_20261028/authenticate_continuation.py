#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authenticate a distinct diagnostic continuation, never strict/native/F10 acceptance."""
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from continuation_contract import BASE, BUNDLE, CASE, ROOT, STAGES, attachments, case_name, guard, require, sha, verdict
from continuation_contract import ENTITLEMENT_FILE, admission_app_identity, exact_entitlements, signature_summary, verify_admission_transition, verify_continuation_project
from continuation_contract import validate_checkpoint_timing, timing_scan_counts
from inspect_native import variant_labels
from privacy_scan import needles, scan_roots, inventory
from archive_contract import safe_extract
from log_evidence import attribute_unified_log, verify_product_log
from ui_observations import parse_ui_observations
from continuation_lifecycle import seal_files, verify_lifecycle
sys.path[:0] = [str(ROOT / 'tests/apple_host'), str(ROOT / 'tools')]
from collect_evidence import load_results
from check_apple_product import inspect


def verify_requests(requests, checkpoints, root):
    previous = 0
    for stage in STAGES:
        count = checkpoints[stage]['network_requests']
        require(type(count) is int and previous <= count <= len(requests), 'request checkpoint differs')
        fresh = requests[previous:count]
        if stage in ('remember_closed', 'session_reopened_missing'):
            require(not fresh, 'unexpected credential network request')
        else:
            expected = 'remembered' if stage == 'remember_reopened' else 'session'
            require(fresh and all(value['credential'] == expected for value in fresh), 'wrong native credential')
            shards = {value['path'].rsplit('/', 2)[-2] for value in fresh if value['method'] == 'PROPFIND' and
                      re.fullmatch(re.escape(urlsplit(root).path) + r'exreader-sync-v1/revisions/[0-9a-f]{2}/', value['path'])}
            require(shards == {format(index, '02x') for index in range(256)}, 'native authenticated sweep incomplete')
        previous = count
    require(previous == len(requests), 'requests after final observation')


def verify_ios_admission(directory, source, result, require_program=True):
    """Re-read original app archives, Mach-O section and actual signatures."""
    require(type(require_program) is bool, 'admission program binding mode differs')
    exact_entitlements(ENTITLEMENT_FILE.read_bytes())
    folder = directory / 'ios-admission'
    manifest = json.loads((folder / 'manifest.json').read_text())
    require(set(manifest) == {'pre-sign', 'post-sign', 'installed'}, 'admission phase evidence incomplete')
    observed = {}
    for phase in ('pre-sign', 'post-sign', 'installed'):
        record = manifest[phase]; archive = folder / (phase + '.zip')
        require(archive.stat().st_size == record['archive_bytes'] and sha(archive) == record['archive_sha256'],
                'admission original archive differs')
        with tempfile.TemporaryDirectory(prefix='privacy-admission-') as temporary:
            extracted = Path(temporary); safe_extract(archive, extracted)
            require({path.name for path in extracted.iterdir()} == {'EXReaderHost.app'}, 'admission archive namespace differs')
            app = extracted / 'EXReaderHost.app'
            files = seal_files(app)
            require(files == record['files'], 'admission archive members differ')
            actual = admission_app_identity(app, source, files)
            for key in ('binary', 'info', 'section', 'libraries', 'files'):
                require(actual[key] == record[key], 'admission identity replay differs')
            retained_display = (folder / (phase + '-display.stdout')).read_bytes() + (folder / (phase + '-display.stderr')).read_bytes()
            retained = signature_summary(retained_display, record['signature_verify_exit'], require_valid=phase != 'pre-sign')
            require(retained == record['signature'], 'retained signature summary differs')
            display = subprocess.run(['codesign', '--display', '--verbose=4', app], capture_output=True, timeout=30)
            verification = subprocess.run(['codesign', '--verify', '--strict', app], capture_output=True, timeout=30)
            actual['signature'] = signature_summary(display.stdout + display.stderr, verification.returncode,
                                                     require_valid=phase != 'pre-sign')
            require(actual['signature'] == record['signature'] and
                    display.returncode == record['signature_display_exit'] and
                    verification.returncode == record['signature_verify_exit'], 'actual signature replay differs')
            require(seal_files(app) == files, 'admission verifier changed original extracted app')
            observed[phase] = actual
    expected = dict(verify_admission_transition(observed['pre-sign'], observed['post-sign'], observed['installed']),
                    status='verified-comparison')
    require(result['ios_admission_summary'] == expected, 'admission comparison claim differs')
    # Strict/default authentication still requires the completed program proof.
    # A pinned failure diagnostic can replay the three actual app archives
    # without fabricating a program.zip that a failed native run never wrote.
    if require_program:
        require(observed['post-sign']['binary']['sha256'] == result['program']['sha256'] and
                observed['installed']['libraries']['Frameworks/libexreader.3.42.0.dylib']['sha256'] == result['program']['runtime_sha256'],
                'admission program binding differs')
    roles = [step['role'] for step in result['commands']]
    expected_order = ['build-for-testing', 'admission-pre-sign-archive', 'admission-host-sign',
        'admission-post-sign-display', 'admission-post-sign-verify', 'admission-post-sign-archive',
        'native', 'admission-installed-path', 'admission-installed-display', 'admission-installed-verify',
        'admission-installed-archive']
    require([role for role in roles if role in expected_order] == expected_order,
            'admission build sign native installed order differs')
    return dict(expected, complete_program_binding_checked=require_program,
                native_sequence_acceptance=False, historical_osstatus_proven=False)


def validate(directory, source, run, attempt, platform):
    result = json.loads((directory / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['base_sha'], result['platform'], result['sdk_version']) ==
            (source, run, attempt, BASE, platform, '3.42.0'), 'native source/run/platform differs')
    require(result['accepted'] is False and result['diagnostic_only'] is True and
            result['sequence_complete'] is True and result['failure'] is None, 'diagnostic sequence incomplete or overclaimed')
    for flag in ('full_f10_accepted', 'dedicated_forget_tested', 'physical_device', 'secure_field_display_is_secret_absence_proof'):
        require(result[flag] is False, 'overclaimed privacy scope')
    require(result['synthetic_canaries_only'] is True, 'non-synthetic privacy input')
    require(result['evidence_sealed'] is True, 'continuation evidence unsealed')
    verify_lifecycle(result['lifecycle'], platform)
    require(result['lifecycle']['admitted_handlers'] >= len(STAGES), 'native checkpoint admissions absent')
    files = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    require(files == set(result['files']) | {'result.json'}, 'unmanifested native file')
    for name, record in result['files'].items():
        path = directory / name
        require(path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], 'native retained bytes differ')
    observed = parse_ui_observations(directory / 'native.log')
    require(observed == result['ui_state_observations'] and observed['observed'],
            'actual finite UI observation evidence absent or differs')
    timing = replay_checkpoint_timing(directory, source, run, attempt, platform)
    commands = result['commands']
    require(commands and all(step['exit'] == 0 for step in commands) and
            {'fixtures', 'project', 'build-for-testing', 'native', 'attachments', 'program-archive'} <=
            {step['role'] for step in commands}, 'native phase missing or failed')
    if platform != 'macos': require(result['simulator_removed_fixture_state'] is True, 'simulator cleanup incomplete')
    cases = load_results(directory / 'privacy.xcresult')
    require(cases == result['cases'] and len(cases) == 1 and case_name(cases[0]['name']) == CASE and
            cases[0]['result'] == 'Passed', 'original native case differs')
    with tempfile.TemporaryDirectory(prefix='privacy-native-') as temporary:
        exported = Path(temporary) / 'attachments'
        subprocess.run(['xcrun', 'xcresulttool', 'export', 'attachments', '--path', str(directory / 'privacy.xcresult'),
                        '--output-path', str(exported)], check=True, capture_output=True)
        stages, screenshots = attachments(exported)
        require(stages == result['native_stages'], 'original native stages differ')
        require({stage: value['sha256'] for stage, value in screenshots.items()} ==
                {stage: value['sha256'] for stage, value in result['screenshots'].items()}, 'original native screenshots differ')

    oracle = json.loads((directory / 'synthetic-oracle-input.json').read_text())
    require((oracle['synthetic_only'], oracle['source_sha'], oracle['run_id'], oracle['attempt']) ==
            (True, source, run, attempt), 'oracle identity differs')
    user, passwords = oracle['user'], oracle['passwords']
    require(re.fullmatch(r'privacy-user-[0-9a-f]{32}', user) and set(passwords) == {'remembered', 'session'} and
            passwords['remembered'] != passwords['session'] and
            all(re.fullmatch(r'Privacy-[0-9a-f]{64}!%:\+', value) for value in passwords.values()), 'invalid synthetic inputs')
    values = {'user': user.encode()}
    for role, password in passwords.items():
        pair = (user + ':' + password).encode()
        values[role] = password.encode(); values[role + '-pair'] = pair
        values[role + '-authorization'] = b'Basic ' + base64.b64encode(pair)
    variants = needles(values)
    checkpoints = result['checkpoints']
    require(list(checkpoints) == STAGES or set(checkpoints) == set(STAGES), 'private checkpoints incomplete')
    require(json.loads((directory / 'checkpoints.json').read_text()) == checkpoints, 'checkpoint manifest differs')
    require(json.loads((directory / 'fixture-failures.json').read_text()) == [], 'fixture observation failed')
    verify_requests(json.loads((directory / 'requests.json').read_text()), checkpoints, result['root'])
    original = (directory / 'source.epub').read_bytes()
    for stage in STAGES:
        checkpoint = checkpoints[stage]
        retained_log = verify_product_log(directory, stage, platform, source, run, attempt)
        attribution = attribute_unified_log((directory / 'sensitive-synthetic-product-logs' / stage / 'host-unified.json').read_bytes(), variants)
        require(attribution == result['log_attribution'][stage] ==
                json.loads((directory / (stage + '-safe-log-attribution.json')).read_text()), 'safe event attribution differs')
        require(retained_log['files'] == {item['path']: {'bytes': item['bytes'], 'sha256': item['sha256']}
                for item in checkpoint['scans']['product-log']['files']}, 'raw retained log differs from scan evidence')
        require(checkpoint['profile_id'] == stages['profile'], 'UI/profile identity differs')
        require(checkpoint['original_bytes'] == len(original) and checkpoint['sdk_original_sha256'] == hashlib.sha256(original).hexdigest(), 'original identity differs')
        archive = directory / (stage + '-product.zip')
        require(checkpoint['archive'] == archive.name and sha(archive) == checkpoint['archive_sha256'], 'private archive differs')
        with tempfile.TemporaryDirectory(prefix='privacy-snapshot-') as temporary:
            snapshot = Path(temporary)
            safe_extract(archive, snapshot)
            labels = set(checkpoint['scans'])
            require(labels == {path.name for path in snapshot.iterdir() if path.is_dir()}, 'private root set differs')
            if platform == 'macos':
                require({'profile', 'product-log'} <= labels <= {'profile', 'product-log', 'preferences', 'cache', 'saved-state'}, 'unexpected macOS roots')
                require(set(checkpoint['absent_mac_roots']) == {'preferences', 'cache', 'saved-state'} - labels, 'macOS root coverage differs')
                profile = snapshot / 'profile'
            else:
                require(labels == {'container', 'product-log'}, 'incomplete simulator container scan')
                profile = snapshot / 'container/Library/Application Support/EXReader'
            scans = scan_roots({label: snapshot / label for label in labels}, variants)
            require(scans == checkpoint['scans'] == json.loads((directory / (stage + '-privacy-scan.json')).read_text()) and
                    all(proof['size_skips'] == 0 for proof in scans.values()), 'independent all-byte privacy scan differs')
            strict_passed = all(proof['accepted'] for proof in scans.values())
            require(type(checkpoint['strict_privacy_passed']) is bool and
                    checkpoint['strict_privacy_passed'] == result['strict_privacy_checks'][stage] == strict_passed,
                    'strict privacy failure was lost during diagnostic continuation')
            expected_files = {label + '/' + record['path'] for label, proof in scans.items() for record in proof['files']}
            actual_files = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob('*') if path.is_file()}
            require(actual_files == expected_files, 'unscanned private archive member')
            metadata = json.loads((profile / 'accounts.json').read_text())
            require(len(metadata) == 1 and metadata[0]['id'] == stages['profile'] and
                    metadata[0]['root'] == result['root'] and metadata[0]['anonymous'] is False, 'actual account differs')
            database = profile / 'accounts' / stages['profile'] / 'library.sqlite'
            with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
                books = connection.execute('SELECT source FROM books ORDER BY id').fetchall()
            require(books == [(original,)], 'actual original changed')

    identity = json.loads((directory / 'sdk-identity.json').read_text())
    target = 'macos' if platform == 'macos' else 'iphonesimulator'
    require((identity['source_sha'], identity['run_id'], identity['attempt'], identity['target']) ==
            (source, run, attempt, target), 'SDK input differs')
    product = identity['product']
    require(product['sdk_version'] == '3.42.0' and product['wave3_enabled'] and product['selector_bytes_candidate'], 'SDK profile differs')
    adapter = json.loads((directory / 'adapter/adapter.json').read_text())
    sources = {str(path.relative_to(ROOT)): sha(path) for path in sorted((ROOT / 'examples/apple').glob('*.swift'))}
    sources['bindings/swift/EXReader.swift'] = sha(ROOT / 'bindings/swift/EXReader.swift')
    require(adapter['source_sha'] == source and adapter['platform'] == platform and adapter['product_sources'] == sources and
            adapter['product_source_changed'] is False and adapter['credential_controls_replaced'] is False and
            adapter['fixture_import_control'] is True, 'owner/source substitution')
    continuation = json.loads((directory / 'adapter/continuation-adapter.json').read_text())
    require(continuation['diagnostic_only'] is True and continuation['source_sha'] == source and
            continuation['platform'] == platform and continuation['strict_test_replaced_only_in_generated_probe_target'] is True,
            'continuation adapter identity differs')
    require(continuation['ios_application_entitlement_linker_only'] is (platform != 'macos') and
            continuation['entitlement_source_sha256'] == sha(ENTITLEMENT_FILE), 'entitlement adapter differs')
    strict_test = ROOT / 'tests/apple_password_privacy_20261028/ui/PasswordPrivacyUITests.swift'
    probe_test = ROOT / 'tests/apple_password_privacy_20261028/continuation_ui/PasswordPrivacyContinuationUITests.swift'
    require(continuation['strict_test_sha256'] == sha(strict_test) and continuation['continuation_test_sha256'] == sha(probe_test),
            'strict or diagnostic test source differs')
    projects = []
    for name in ('strict', 'continuation'):
        path = directory / 'adapter' / (name + '-project.pbxproj')
        require(sha(path) == continuation[name + '_project_sha256'], 'retained generated project differs')
        projects.append(json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(path)])))
    project_delta = verify_continuation_project(*projects, probe_test, ENTITLEMENT_FILE, platform)
    require(project_delta == result['generated_project_delta'], 'producer project equality differs')
    for name, digest in adapter['files'].items(): require(sha(directory / 'adapter' / name) == digest, 'adapter bytes differ')
    generator = (ROOT / 'tests/apple_host/make_xcodeproj.rb').read_text()
    require((directory / 'adapter/original-generator.rb').read_text() == generator, 'old generator differs')
    for before, after in [("['3.40.0', '3.41.0'].include?(sdk_version)", "['3.42.0'].include?(sdk_version)"),
                          ("page_theme == 'ON' && sdk_version != '3.41.0'", "page_theme == 'ON' && sdk_version != '3.42.0'")]:
        require(generator.count(before) == 1, 'generator anchor differs')
        generator = generator.replace(before, after, 1)
    require((directory / 'adapter/derived-generator.rb').read_text() == generator, 'unexpected generated adapter')
    wrapper = (ROOT / 'tests/reader_team24_apple/make_project.rb').read_text()
    require((directory / 'adapter/original-wrapper.rb').read_text() == wrapper, 'old wrapper differs')
    anchor = "'tests/apple_host/make_xcodeproj.rb'"
    require(wrapper.count(anchor) == 1 and (directory / 'adapter/derived-wrapper.rb').read_text() ==
            wrapper.replace(anchor, json.dumps(adapter['generator_path']), 1), 'unexpected derived wrapper')
    require(sha(directory / 'program.zip') == result['program']['archive_sha256'], 'program archive differs')
    with tempfile.TemporaryDirectory(prefix='privacy-program-') as temporary:
        bundle = Path(temporary)
        safe_extract(directory / 'program.zip', bundle)
        app = bundle / 'EXReaderHost.app'
        prefix = app / 'Contents' if platform == 'macos' else app
        info = plistlib.loads((prefix / 'Info.plist').read_bytes())
        require(info['CFBundleIdentifier'] == BUNDLE and info['EXRSourceSHA'] == source and info['EXRSDKVersion'] == '3.42.0' and
                info['EXRPageThemeEnabled'] is True, 'actual application identity differs')
        binary = prefix / ('MacOS/EXReaderHost' if platform == 'macos' else 'EXReaderHost')
        require(sha(binary) == result['program']['sha256'] and binary.stat().st_size == result['program']['bytes'], 'program bytes differ')
        require(sha(prefix / 'Frameworks/libexreader.3.42.0.dylib') == result['program']['runtime_sha256'], 'packaged runtime differs')
        resources = prefix / 'Resources' if platform == 'macos' else prefix
        require((resources / 'Sample.epub').read_bytes() == original, 'actual bundled original differs')
        actual, claimed = inspect(binary, directory / 'EXReaderHost.link.map', True), dict(result['provider_check'])
        actual['dependencies'] = actual['dependencies'].splitlines()[1:]
        claimed['dependencies'] = claimed['dependencies'].splitlines()[1:]
        require(actual == claimed, 'actual binary provider differs')
    if platform != 'macos': verify_ios_admission(directory, source, result)
    else:
        require(result['ios_admission_summary'] == {'status': 'not-required', 'built_and_installed_verified': False,
            'original_osstatus_proven': False, 'full_f10_accepted': False}, 'macOS admission scope changed')
    diagnostic = verdict(result['strict_privacy_checks'])
    require(result['diagnostic_verdict'] == diagnostic, 'diagnostic verdict differs')
    return dict(diagnostic, platform=platform, source_sha=source, stages=STAGES, sequence_complete=True,
                probe_integrity_verified=True, binary_sha256=result['program']['sha256'], dedicated_forget_tested=False,
                ui_state_observations=observed,
                checkpoint_timing=timing,
                ios_admission_summary=result['ios_admission_summary'],
                log_attribution=result['log_attribution'], attribution_limit='sender image categories, not production owner callsites',
                privacy_roots={stage: {label: {'strict_passed': proof['accepted'], 'hit_variant_labels': variant_labels(proof)}
                    for label, proof in result['checkpoints'][stage]['scans'].items()} for stage in STAGES})


def replay_checkpoint_timing(directory, source, run, attempt, platform):
    """Independent retained-byte/schema replay only, not native/signature credit."""
    before = inventory(directory)
    result = json.loads((directory / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['base_sha'], result['platform']) ==
            (source, run, attempt, BASE, platform) and result['accepted'] is False and
            result['diagnostic_only'] is True and result['full_f10_accepted'] is False and
            result['evidence_sealed'] is True, 'timing retained identity differs')
    verify_lifecycle(result['lifecycle'], platform)
    files = result['files']
    require(type(files) is dict and {path.relative_to(directory).as_posix() for path in directory.rglob('*')
            if path.is_file()} == set(files) | {'result.json'}, 'timing retained inventory differs')
    for name, record in files.items():
        require(type(record) is dict and set(record) == {'bytes', 'sha256'} and type(record['bytes']) is int and
                record['bytes'] >= 0 and type(record['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', record['sha256']) is not None and
                (directory / name).stat().st_size == record['bytes'] and sha(directory / name) == record['sha256'],
                'timing retained member differs')
    document = json.loads((directory / 'checkpoint-timing.json').read_text())
    proof = validate_checkpoint_timing(document, result['checkpoints'], source, run, attempt, platform)
    require(all(row['state'] != 'open' for row in proof['records']), 'timing finalized callback remains open')
    require(proof == result['checkpoint_timing'], 'timing producer summary differs')
    if result['checkpoints']:
        require(json.loads((directory / 'checkpoints.json').read_text()) == result['checkpoints'],
                'timing retained checkpoints differ')
    for row in proof['records']:
        if row['scan_counts']:
            scans = json.loads((directory / (row['stage'] + '-privacy-scan.json')).read_text())
            require(timing_scan_counts(scans) == row['scan_counts'], 'timing original scan counts differ')
    require(inventory(directory) == before, 'timing evidence changed during replay')
    return dict(proof, original_member_count=len(files), original_member_replay=True,
                producer_summary_matched=True, signature_replay_credited=False)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    guard()
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/apple-password-continuation-summary'; out.mkdir(parents=True, exist_ok=False)
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False, 'diagnostic_only': True,
               'probe_integrity_verified': False,
               'full_f10_accepted': False, 'dedicated_forget_tested': False, 'platforms': {}, 'failure': None,
               'timing_replays': {}, 'timing_replay_failures': {}, 'continuation_replay_failures': {}}
    def api(path):
        return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path]))
    try:
        jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
        expected = {'Privacy oracle rejection controls', 'Privacy SDK macos', 'Privacy SDK iphonesimulator'} | {
            'Privacy diagnostic continuation ' + platform for platform in ('macos', 'iphone', 'ipad')}
        producers = [job for job in jobs if job['name'] in expected]
        require(len(producers) == len(expected) and {job['name'] for job in producers} == expected and
                all(job['head_sha'] == source and job['status'] == 'completed' for job in producers),
                'timing current-attempt producer identity incomplete')
        require(all(job['conclusion'] == 'success' for job in producers if job['name'] in {
            'Privacy oracle rejection controls', 'Privacy SDK macos', 'Privacy SDK iphonesimulator'}),
            'timing prerequisite controls or SDK failed')
        all_producers_succeeded = all(job['conclusion'] == 'success' for job in producers)
        artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
        require(len(artifacts) < 100, 'artifact listing pagination required')
        for platform in ('macos', 'iphone', 'ipad'):
            try:
                matches = [item for item in artifacts if item['name'] == 'password-continuation-native-' + platform + '-' + run + '-' + attempt]
                require(len(matches) == 1, 'native artifact absent or duplicate')
                artifact = matches[0]
                require(not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and
                        str(artifact['workflow_run']['id']) == run, 'original artifact identity differs')
                # Do not re-export failed native logs in the safe timing summary
                # artifact. Immutable producer uploads remain retained remotely.
                with tempfile.TemporaryDirectory(prefix='privacy-current-original-') as temporary:
                    path = Path(temporary) / 'original.zip'
                    with path.open('wb') as file:
                        subprocess.run(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(artifact['id']) + '/zip'],
                                       stdout=file, stderr=subprocess.PIPE, check=True)
                    require(path.stat().st_size == artifact['size_in_bytes'] and 'sha256:' + sha(path) == artifact['digest'], 'original ZIP digest differs')
                    directory = Path(temporary) / 'extracted'; directory.mkdir()
                    safe_extract(path, directory)
                    timing = replay_checkpoint_timing(directory, source, run, attempt, platform)
                    timing.update(artifact_id=artifact['id'], original_zip_sha256=sha(path), original_zip_bytes=path.stat().st_size)
                    summary['timing_replays'][platform] = timing
                    if all_producers_succeeded:
                        try:
                            proof = validate(directory, source, run, attempt, platform)
                            proof.update(artifact_id=artifact['id'], original_zip_sha256=sha(path), original_zip_bytes=path.stat().st_size)
                            summary['platforms'][platform] = proof
                        except Exception:
                            summary['continuation_replay_failures'][platform] = 'unavailable-or-invalid'
            except Exception:
                summary['timing_replay_failures'][platform] = 'unavailable-or-invalid'
        # Diagnostic timing does not bypass the ORIGINAL producer gate or any
        # successful-native/program/admission/privacy proof in validate().
        require(len(producers) == len(expected) and {job['name'] for job in producers} == expected and
                all(job['head_sha'] == source and job['status'] == 'completed' and job['conclusion'] == 'success' for job in producers),
                'current-attempt producer incomplete, failed or blocked')
        require(not summary['timing_replay_failures'] and not summary['continuation_replay_failures'] and
                set(summary['timing_replays']) == {'macos', 'iphone', 'ipad'} and
                set(summary['platforms']) == {'macos', 'iphone', 'ipad'}, 'complete continuation/timing replay absent')
        summary['probe_integrity_verified'] = True
    except Exception as error:
        # Never echo arbitrary parsed/framework text or synthetic oracle inputs.
        summary['failure'] = type(error).__name__
    finally:
        (out / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
    require(summary['probe_integrity_verified'], 'diagnostic continuation integrity not verified; strict/native/F10 acceptance remains false')


if __name__ == '__main__': main()
