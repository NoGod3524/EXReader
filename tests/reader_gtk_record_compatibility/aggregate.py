# SPDX-License-Identifier: MIT
"""Authenticate the finished candidate job, raw ZIP, reports and native screenshots."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import sys
from compatibility_contract import authenticate as authenticate_compatibility
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_gtk_page_background'))
from check_evidence import SDK, REPORTS, LEGACY

REQUIRED = {path: count for path, (count, _) in REPORTS.items()}
REQUIRED.update({'account-package/build.json': None, 'reading-library/stage/include/exr/base.h': None,
                 'reading-library/stage/include/exr/render.h': None, 'gtk-drop-j03/portable.log': 52,
                 'gtk-drop-j03/gtk.log': 28, 'page-background-fixtures/manifest.json': None,
                 'page-background-fixtures/Authored white and original image.epub': None})


def validate(value, source, run, attempt):
    assert value['source_sha'] == source and str(value['run_id']) == str(run) and str(value['attempt']) == str(attempt)
    assert value['ok'] is True and value['page_background_scope_passed'] is True
    assert value['settings_whole_page_palette_accepted'] is True and value['sdk_candidate_source'] == SDK
    assert value['sdk_version'] == '3.41.0' and value['core_version'] == '3.40.0' and value['sdk_abi'] == 1
    assert value['accepted'] is value['complete_product'] is value['six_platform_accepted'] is value['performance_accepted'] is False
    assert 'error' not in value and re.fullmatch('[0-9a-f]{64}', value['program_sha256'])
    assert set(value['verified']) == set(REQUIRED)
    for path, count in REQUIRED.items():
        assert value['verified'][path]['count'] == count and re.fullmatch('[0-9a-f]{64}', value['verified'][path]['sha256'])
    assert set(value['legacy_reports_external_identity']) == LEGACY
    for identity in value['legacy_reports_external_identity'].values():
        assert identity['source_sha'] == source and str(identity['run_id']) == str(run) and str(identity['attempt']) == str(attempt)
        assert identity['program_sha256'] == value['program_sha256']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repo, source, run, attempt = (os.environ[key] for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    api = 'https://api.github.com/repos/' + repo
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'}

    def get(path):
        with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
            return json.load(response)

    metadata = get('/actions/runs/' + run)
    assert metadata['head_sha'] == source and metadata['run_attempt'] == int(attempt)
    assert metadata['path'] == '.github/workflows/reader-gtk-record-compatibility.yml'
    jobs = get('/actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    hosts = [job for job in jobs if job['name'] == 'GTK original suites and actual owner record compatibility']
    assert len(hosts) == 1 and hosts[0]['status'] == 'completed' and hosts[0]['conclusion'] == 'success'
    assert not any(step['conclusion'] == 'failure' for step in hosts[0]['steps'])
    successes = {step['name'] for step in hosts[0]['steps'] if step['conclusion'] == 'success'}
    assert {'Require fixed SDK candidate and unchanged legacy tests',
            'Complete versioned settings suite canvas images authored white and portal',
            'Preserve original batch checker for its own bounded import scope',
            'Build actual frozen old owner and exercise real cross-process record compatibility',
            'Authenticate candidate canvas and all retained non-palette scopes'}.issubset(successes)
    foundation = get('/actions/runs/40165924012')
    assert foundation['head_sha'] == SDK and foundation['status'] == 'completed' and foundation['run_attempt'] == 1
    foundation_jobs = get('/actions/runs/40165924012/attempts/1/jobs?per_page=100')['jobs']
    for platform in ('linux', 'windows', 'macos'):
        consumers = [job for job in foundation_jobs if job['name'] == 'background consumers (' + platform + ')']
        assert len(consumers) == 1 and consumers[0]['conclusion'] == 'success'
    sdk_validation = get('/actions/runs/40166642441')
    assert sdk_validation['head_sha'] == '4a5a793ebe2a98a96ed119334399821e923c19ab'
    assert sdk_validation['status'] == 'completed' and sdk_validation['conclusion'] == 'success'
    version_support = get('/actions/runs/40166479919')
    assert version_support['head_sha'] == 'f680aeaddfb1ecc67ead353554f5b91a5703f72f'
    assert version_support['status'] == 'completed' and version_support['conclusion'] == 'success'
    artifacts = get('/actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    matches = [row for row in artifacts if row['name'] == 'reader-gtk-record-compatibility-%s-%s' % (run, attempt)]
    assert len(matches) == 1
    artifact = matches[0]
    assert artifact['expired'] is False and 0 < artifact['size_in_bytes'] <= 200 * 1024 * 1024
    assert datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    assert re.fullmatch('sha256:[0-9a-f]{64}', artifact['digest'])

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, response, code, message, response_headers, new_url):
            return None

    try:
        urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(api + '/actions/artifacts/%d/zip' % artifact['id'], headers=headers), timeout=60)
        raise AssertionError('artifact did not redirect')
    except urllib.error.HTTPError as response:
        assert response.code == 302
        url = response.headers['Location']
    assert urllib.parse.urlsplit(url).scheme == 'https'
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(200 * 1024 * 1024 + 1)
    assert len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest']
    bound = {}
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        assert len(bundle.infolist()) <= 20000 and sum(row.file_size for row in bundle.infolist()) <= 1024 * 1024 * 1024
        assert len(bundle.namelist()) == len(set(bundle.namelist()))
        for name in bundle.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name

        def raw(relative, limit=4 * 1024 * 1024):
            names = [name for name in bundle.namelist() if name == relative or name.endswith('/' + relative)]
            assert len(names) == 1 and bundle.getinfo(names[0]).file_size <= limit, relative
            content = bundle.read(names[0]);bound[relative] = hashlib.sha256(content).hexdigest()
            return content

        value = json.loads(raw('gtk-page-background-evidence.json'))
        validate(value, source, run, attempt)
        mutations = [('source_sha', 'foreign'), ('run_id', '0'), ('attempt', '0'), ('ok', False),
                     ('page_background_scope_passed', False), ('settings_whole_page_palette_accepted', False),
                     ('sdk_candidate_source', 'foreign'), ('sdk_version', '3.40.0'), ('sdk_abi', 2),
                     ('accepted', True), ('complete_product', True), ('six_platform_accepted', True),
                     ('program_sha256', ''), ('verified', {}), ('legacy_reports_external_identity', {})]
        for key, replacement in mutations:
            invalid = copy.deepcopy(value);invalid[key] = replacement
            try:
                validate(invalid, source, run, attempt)
            except (AssertionError, KeyError):
                continue
            raise AssertionError('protocol accepted ' + key)
        assert hashlib.sha256(raw('account-package/EXReader-Linux/bin/exreader-linux', 64 * 1024 * 1024)).hexdigest() == value['program_sha256']
        for path, row in value['verified'].items():
            assert hashlib.sha256(raw(path)).hexdigest() == row['sha256'], path
        batch = json.loads(raw('gtk-batch-evidence.json'))
        for path, row in batch['verified'].items():
            assert hashlib.sha256(raw(path)).hexdigest() == row['sha256'], path
        fixture = json.loads(raw('page-background-fixtures/manifest.json'))
        original = raw('page-background-fixtures/' + fixture['book'])
        assert hashlib.sha256(original).hexdigest() == fixture['sha256']
        with zipfile.ZipFile(io.BytesIO(original)) as publication:
            assert hashlib.sha256(publication.read('patch.png')).hexdigest() == fixture['image_sha256']
        compatibility = authenticate_compatibility(raw, source, run, attempt)
        settings = json.loads(raw('preferences-ui/result.json'))

        def screenshot_hashes(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in ('sha256', 'screenshot_sha256'):
                        yield child
                    else:
                        yield from screenshot_hashes(child)
            elif isinstance(item, list):
                for child in item:
                    yield from screenshot_hashes(child)

        actual_pngs = set()
        for member in bundle.namelist():
            parts = PurePosixPath(member).parts
            if 'preferences-ui' in parts and member.endswith('.png'):
                relative = '/'.join(parts[parts.index('preferences-ui'):])
                actual_pngs.add(hashlib.sha256(raw(relative, 32 * 1024 * 1024)).hexdigest())
        expected_pngs = set(screenshot_hashes(settings))
        assert expected_pngs and expected_pngs.issubset(actual_pngs)
    report = dict(accepted=True, acceptance_scope='Linux actual GTK records for this explicit old/new owner and SDK pair', authenticated=True, page_background_scope_passed=True,
                  settings_whole_page_palette_accepted=True, source_sha=source, run_id=run, attempt=attempt,
                  sdk_candidate_source=SDK, sdk_foundation_run=40165924012, sdk_validation_run=40166642441,
                  sdk_validator_source='4a5a793ebe2a98a96ed119334399821e923c19ab',
                  shared_version_support_source='f680aeaddfb1ecc67ead353554f5b91a5703f72f',
                  shared_version_support_run=40166479919, program_sha256=value['program_sha256'],
                  record_compatibility=compatibility, record_compatibility_accepted=True, host_job_id=hosts[0]['id'], protocol_rejections=len(mutations), native_pixel_pngs_authenticated=len(expected_pngs),
                  artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                  bound_files=bound, complete_product=False, six_platform_accepted=False, performance_accepted=False)
    Path('build/gtk-record-compatibility-summary').mkdir(parents=True, exist_ok=True)
    Path('build/gtk-record-compatibility-summary/verified.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
