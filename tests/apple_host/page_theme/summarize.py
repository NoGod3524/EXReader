# SPDX-License-Identifier: MIT
"""Authenticate exact-source completed producers and their original artifact ZIPs."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    expected_jobs = {'SDK3.41 and installed products macos', 'SDK3.41 and installed products iphonesimulator',
                     'Original OFF ON pixels and theme transaction checks', 'Real page theme UI macos',
                     'Real page theme UI iphone', 'Real page theme UI ipad'}
    jobs = fetch('actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')
    producers = [row for row in jobs['jobs'] if row['name'] in expected_jobs]
    require(jobs['total_count'] == 7 and len(producers) == 6 and {row['name'] for row in producers} == expected_jobs,
            'missing/duplicate producer job')
    require(all(row['status'] == 'completed' and row['conclusion'] == 'success' and row['head_sha'] == source and
                row['run_attempt'] == int(attempt) for row in producers), 'producer failed or source/attempt differs')
    artifact_names = {'apple-theme-sdk-' + target + '-' + run + '-' + attempt for target in ('macos', 'iphonesimulator')}
    artifact_names |= {'apple-theme-native-' + run + '-' + attempt}
    artifact_names |= {'apple-theme-ui-' + target + '-' + run + '-' + attempt for target in ('macos', 'iphone', 'ipad')}
    artifacts = fetch('actions/runs/' + run + '/artifacts?per_page=100')
    require(artifacts['total_count'] == 6 and {row['name'] for row in artifacts['artifacts']} == artifact_names,
            'missing/duplicate/foreign artifact')
    now = datetime.datetime.now(datetime.timezone.utc); retained = []
    for artifact in artifacts['artifacts']:
        require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['id'] == int(run) and
                artifact['workflow_run']['head_sha'] == source and
                datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > now, 'artifact expired or identity differs')
        digest = artifact['digest']
        require(isinstance(digest, str) and digest.startswith('sha256:') and len(digest) == 71, 'missing artifact digest')
        data = download_artifact_zip(artifact['id'])
        require(len(data) == artifact['size_in_bytes'] and hashlib.sha256(data).hexdigest() == digest[7:], 'original artifact ZIP differs')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')

            def report(path):
                require(0 < archive.getinfo(path).file_size <= 16 * 1024 * 1024, 'report size differs')
                value = json.loads(archive.read(path))
                require(value['source_sha'] == source and str(value['run_id']) == run and str(value['attempt']) == attempt,
                        'report source/run/attempt differs')
                return value

            reports = {}
            if artifact['name'].startswith('apple-theme-sdk-'):
                sdk = report('build/sdk-identity.json'); guard = report('build/apple-page-theme/guard.json')
                require(sdk['sdk_version'] == '3.41.0' and sdk['abi'] == 1 and
                        guard['candidate_input_authenticated'] is True and guard['theme_accepted'] is False and
                        guard['sdk_source'] == 'edddc463c06ed5731195cdb8f06b2df6dff7699e' and len(guard['negative_checks']) >= 70,
                        'SDK or source guard differs')
                reports = {'sdk': sdk, 'guard': guard}
            elif artifact['name'].startswith('apple-theme-native-'):
                value = report('native.json')
                require(value['accepted'] is True and value['original_on_off_exact'] is True and value['mixed_version_rejections'] == 5 and
                        value['sdk_version'] == '3.41.0' and value['sdk_abi'] == 1 and value['old_340_migration_tested'] is False,
                        'native theme contract incomplete')
                for mode, count in [('on', 37), ('off', 10)]:
                    raw = report(mode + '/theme-review.json')
                    require(raw == value['reports'][mode] and raw['accepted'] is True and raw['theme_enabled'] == (mode == 'on') and
                            len(raw['checks']) == len({row['id'] for row in raw['checks']}) == count and
                            all(row['passed'] is True for row in raw['checks']), 'native named checks differ')
                    provider = json.loads(archive.read('theme-review-' + mode + '.product.json'))
                    require(provider['static_sdk_linked'] is False and provider['binary_sha256'] == value['binaries'][mode]['sha256'] ==
                            hashlib.sha256(archive.read('theme-review-' + mode)).hexdigest(), 'native executable/provider differs')
                reports['native'] = value
            else:
                value = report('evidence/theme-ui.json')
                require(value['accepted'] is True and len(value['cases']) == len(value['observations']) == 4 and
                        all(row['result'] == 'Passed' for row in value['cases']) and value['system_commands']['served'] == ['dark', 'light'] and
                        value['provider']['static_sdk_linked'] is False and
                        artifact['name'] == 'apple-theme-ui-' + value['platform'] + '-' + run + '-' + attempt, 'UI contract incomplete')
                binary = 'evidence/program/EXReaderHost.app/' + ('Contents/MacOS/' if value['platform'] == 'macos' else '') + 'EXReaderHost'
                require(hashlib.sha256(archive.read(binary)).hexdigest() == value['app_sha256'], 'UI executable differs')
                reports['ui'] = value
        retained.append({'id': artifact['id'], 'name': artifact['name'], 'bytes': len(data), 'digest': digest,
                         'expires_at': artifact['expires_at'], 'reports': reports})
    result = {'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt, 'jobs': producers, 'artifacts': retained,
              'scope': 'SDK3.41 Apple explicit page themes on macOS and iPhone/iPad simulators only',
              'old_340_migration_tested': False, 'six_original_suites_accepted': False,
              'physical_device_execution': False, 'complete_product': False}
    out = Path('build/apple-theme-summary'); out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key not in ('jobs', 'artifacts')}))


if __name__ == '__main__':
    main()
