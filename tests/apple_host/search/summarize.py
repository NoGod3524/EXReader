# SPDX-License-Identifier: MIT
"""Check this run's completed jobs and hash-verified producer ZIPs in Actions."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import urllib.request
import zipfile


def require(value, message):
    if not value:
        raise AssertionError(message)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    repo, source, run, attempt, token = (os.environ[name] for name in
        ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GH_TOKEN'))
    base = 'https://api.github.com/repos/' + repo

    def request(path):
        return urllib.request.urlopen(urllib.request.Request(base + path,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}), timeout=90).read()

    jobs = json.loads(request('/actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100'))
    expected_jobs = {'Frozen SDK and installed F1 macos', 'Native search and original adapter contracts',
                     'Frozen SDK and installed F1 iphonesimulator', 'Search UI macos', 'Search UI iphone', 'Search UI ipad'}
    relevant = [row for row in jobs['jobs'] if row['name'] in expected_jobs]
    require(jobs['total_count'] == 7 and len(relevant) == 6 and {row['name'] for row in relevant} == expected_jobs,
            'producer job set differs')
    require(all(row['status'] == 'completed' and row['conclusion'] == 'success' and row['head_sha'] == source
                and row['run_attempt'] == int(attempt) for row in relevant), 'producer failed or source differs')
    artifacts = json.loads(request('/actions/runs/' + run + '/artifacts?per_page=100'))
    expected_names = {'apple-search-sdk-' + target + '-' + run + '-' + attempt for target in ('macos', 'iphonesimulator')}
    expected_names |= {'apple-search-native-' + run + '-' + attempt}
    expected_names |= {'apple-search-ui-' + platform + '-' + run + '-' + attempt for platform in ('macos', 'iphone', 'ipad')}
    require(artifacts['total_count'] == 6 and {row['name'] for row in artifacts['artifacts']} == expected_names,
            'producer artifact set differs')
    now = datetime.datetime.now(datetime.timezone.utc)
    retained = []
    for artifact in artifacts['artifacts']:
        require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                artifact['workflow_run']['id'] == int(run) and artifact['workflow_run']['head_sha'] == source,
                'artifact source/run differs')
        require(datetime.datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > now, 'artifact expired')
        digest = artifact['digest']
        require(isinstance(digest, str) and digest.startswith('sha256:') and len(digest) == 71, 'artifact digest missing')
        data = request('/actions/artifacts/' + str(artifact['id']) + '/zip')
        require(len(data) == artifact['size_in_bytes'] and hashlib.sha256(data).hexdigest() == digest[7:], 'ZIP identity differs')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')

            def read_json(name):
                info = archive.getinfo(name)
                require(0 < info.file_size <= 4 * 1024 * 1024, 'report size differs')
                return json.loads(archive.read(name))

            name = artifact['name']
            reports = {}
            if name.startswith('apple-search-sdk-'):
                reports['sdk'] = read_json('build/sdk-identity.json')
            elif name.startswith('apple-search-native-'):
                for report, count in [('consumer/search-review.json', 10), ('catalog.json', 8), ('mapping/mapping-review.json', 16)]:
                    value = read_json(report)
                    require(value['accepted'] is True and value['failed'] == value['skipped'] == 0 and
                            len(value['checks']) == len({row['id'] for row in value['checks']}) == count and
                            all(row['passed'] is True for row in value['checks']), 'native checks failed or omitted')
                    reports[report] = value
                provider = read_json('search-review.product.json')
                require(provider['installed_search_linked'] is True and provider['static_sdk_linked'] is False and
                        hashlib.sha256(archive.read('search-review')).hexdigest() == provider['binary_sha256'], 'native executable differs')
            else:
                value = read_json('evidence/search-ui.json')
                require(value['accepted'] is True and len(value['cases']) == 3 and len(value['steps']) == 3 and
                        all(row['result'] == 'Passed' for row in value['cases']) and
                        value['provider']['installed_search_linked'] is True and value['provider']['static_sdk_linked'] is False,
                        'UI evidence failed')
                require(name == 'apple-search-ui-' + value['platform'] + '-' + run + '-' + attempt, 'UI platform differs')
                executable = 'evidence/program/EXReaderHost.app/' + ('Contents/MacOS/' if value['platform'] == 'macos' else '') + 'EXReaderHost'
                require(hashlib.sha256(archive.read(executable)).hexdigest() == value['app_sha256'], 'UI executable differs')
                reports['ui'] = value
            for value in reports.values():
                require(value['source_sha'] == source, 'report source differs')
                report_run = value.get('run_id', value.get('run', {}).get('id'))
                report_attempt = value.get('attempt', value.get('run', {}).get('attempt'))
                require(str(report_run) == run and str(report_attempt) == attempt, 'report run/attempt differs')
        retained.append({'id': artifact['id'], 'name': name, 'bytes': len(data), 'digest': digest,
                         'expires_at': artifact['expires_at'], 'reports': reports})
    output = {'accepted': True, 'scope': 'native Apple search interface only', 'source_sha': source,
              'run_id': run, 'attempt': attempt, 'jobs': relevant, 'artifacts': retained,
              'complete_product': False, 'performance_accepted': False, 'physical_device_execution': False}
    destination = Path('build/apple-search-summary')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'summary.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: value for key, value in output.items() if key not in ('jobs', 'artifacts')}))


if __name__ == '__main__':
    main()
