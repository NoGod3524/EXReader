#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only independent original-artifact and private-byte authentication."""
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
from contract import BASE, BUNDLE, CASE, ROOT, STAGES, attachments, case_name, guard, require, sha
from privacy_scan import needles, scan_roots
from archive_contract import safe_extract
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


def validate(directory, source, run, attempt, platform):
    result = json.loads((directory / 'result.json').read_text())
    require((result['source_sha'], result['run_id'], result['attempt'], result['base_sha'], result['platform'], result['sdk_version']) ==
            (source, run, attempt, BASE, platform, '3.42.0'), 'native source/run/platform differs')
    require(result['accepted'] is True and result['failure'] is None, 'native did not pass')
    for flag in ('full_f10_accepted', 'dedicated_forget_tested', 'physical_device', 'secure_field_display_is_secret_absence_proof'):
        require(result[flag] is False, 'overclaimed privacy scope')
    require(result['synthetic_canaries_only'] is True, 'non-synthetic privacy input')
    files = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    require(files == set(result['files']) | {'result.json'}, 'unmanifested native file')
    for name, record in result['files'].items():
        path = directory / name
        require(path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], 'native retained bytes differ')
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
                    all(proof['accepted'] and proof['size_skips'] == 0 for proof in scans.values()), 'independent all-byte privacy scan differs')
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
    return {'accepted': True, 'platform': platform, 'source_sha': source, 'stages': STAGES,
            'binary_sha256': result['program']['sha256'], 'dedicated_forget_tested': False, 'full_f10_accepted': False}


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'darwin', 'Actions macOS only')
    guard()
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/apple-password-privacy-summary'; out.mkdir(parents=True, exist_ok=False)
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'accepted': False,
               'full_f10_accepted': False, 'dedicated_forget_tested': False, 'platforms': {}, 'failure': None}
    def api(path):
        return json.loads(subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path]))
    try:
        jobs = api('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
        expected = {'Privacy oracle rejection controls', 'Privacy SDK macos', 'Privacy SDK iphonesimulator'} | {
            'Privacy native ' + platform for platform in ('macos', 'iphone', 'ipad')}
        producers = [job for job in jobs if job['name'] in expected]
        require(len(producers) == len(expected) and {job['name'] for job in producers} == expected and
                all(job['head_sha'] == source and job['status'] == 'completed' and job['conclusion'] == 'success' for job in producers),
                'current-attempt producer incomplete, failed or blocked')
        artifacts = api('actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
        require(len(artifacts) < 100, 'artifact listing pagination required')
        for platform in ('macos', 'iphone', 'ipad'):
            matches = [item for item in artifacts if item['name'] == 'password-native-' + platform + '-' + run + '-' + attempt]
            require(len(matches) == 1, 'native artifact absent or duplicate')
            artifact = matches[0]
            require(not artifact['expired'] and artifact['workflow_run']['head_sha'] == source and
                    str(artifact['workflow_run']['id']) == run, 'original artifact identity differs')
            path = out / (platform + '-original.zip')
            with path.open('wb') as file:
                subprocess.run(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + '/actions/artifacts/' + str(artifact['id']) + '/zip'],
                               stdout=file, check=True)
            require(path.stat().st_size == artifact['size_in_bytes'] and 'sha256:' + sha(path) == artifact['digest'], 'original ZIP digest differs')
            with tempfile.TemporaryDirectory(prefix='privacy-evidence-') as temporary:
                directory = Path(temporary); safe_extract(path, directory)
                proof = validate(directory, source, run, attempt, platform)
            proof.update(artifact_id=artifact['id'], original_zip_sha256=sha(path), original_zip_bytes=path.stat().st_size)
            summary['platforms'][platform] = proof
        summary['accepted'] = True
    except Exception as error:
        # Never echo arbitrary parsed/framework text or synthetic oracle inputs.
        summary['failure'] = type(error).__name__
    finally:
        (out / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
    require(summary['accepted'], 'Apple privacy slice not accepted; full F10 remains unaccepted')


if __name__ == '__main__': main()
