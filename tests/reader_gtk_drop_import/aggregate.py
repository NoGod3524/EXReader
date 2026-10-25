# SPDX-License-Identifier: MIT
"""Authenticate the finished same-attempt job and its raw ZIP, only on Actions."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REQUIRED = {'gtk-drop-ui/report.json': 20, 'gtk-drop-backend/report.json': 23,
            'gtk-batch-evidence.json': None, 'gtk-drop-j03/portable.log': 52, 'gtk-drop-j03/gtk.log': 28,
            'account-ui/result.json': 46, 'account-shelf/shelf-result.json': 14,
            'account-original/report.json': 20, 'account-atspi-fixes/result.json': 10}


def validate(value, source, run, attempt):
    assert value['source_sha'] == source and str(value['run_id']) == str(run) and str(value['attempt']) == str(attempt)
    assert value['ok'] is True and value['drop_import_scope_passed'] is True and value['accepted'] is False
    assert value['complete_product'] is False and value['six_platform_accepted'] is False and value['performance_accepted'] is False
    assert value['settings_whole_page_palette_accepted'] is False and 'error' not in value
    assert re.fullmatch('[0-9a-f]{64}', value['program_sha256'])
    assert set(value['verified']) == set(REQUIRED)
    for name, count in REQUIRED.items():
        assert value['verified'][name]['count'] == count and re.fullmatch('[0-9a-f]{64}', value['verified'][name]['sha256'])
    legacy = value['legacy_reports_external_identity']
    assert set(legacy) == {'account-original/report.json'}
    identity = legacy['account-original/report.json']
    assert identity['source_sha'] == source and str(identity['run_id']) == str(run) and str(identity['attempt']) == str(attempt)
    assert identity['program_sha256'] == value['program_sha256']


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repo, source, run, attempt = (os.environ[name] for name in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    checker_source, checker_run, checker_attempt = source, run, attempt
    recheck = os.environ.get('GTK_DROP_RECHECK_LEGACY') == 'true'
    if recheck:
        # Only this known complete producer round is eligible for a pure
        # checker repair. No program, fixture or old report is rebuilt/edited.
        source, run, attempt = '722eb4384b81a1aef6595efa849d3e017f371389', '40163023408', '1'
        permitted = {'tests/reader_gtk_drop_import/check_evidence.py', 'tests/reader_gtk_drop_import/aggregate.py',
                     '.github/workflows/reader-gtk-drop-import.yml', 'docs/READER-GTK-DROP-IMPORT.md',
                     'docs/validation/reader-gtk-drop-import.json'}
        changed = subprocess.check_output(['git', 'diff', '--name-only', source, 'HEAD'], text=True).splitlines()
        assert set(changed).issubset(permitted), changed
    api = 'https://api.github.com/repos/' + repo
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'}

    def get(path):
        with urllib.request.urlopen(urllib.request.Request(api + path, headers=headers), timeout=60) as response:
            return json.load(response)

    metadata = get('/actions/runs/' + run)
    assert metadata['head_sha'] == source and metadata['run_attempt'] == int(attempt)
    if recheck:
        assert metadata['status'] == 'completed' and metadata['conclusion'] == 'failure'
    assert metadata['path'] == '.github/workflows/reader-gtk-drop-import.yml'
    jobs = get('/actions/runs/' + run + '/attempts/' + attempt + '/jobs?per_page=100')['jobs']
    hosts = [job for job in jobs if job['name'] == 'GTK book file drop paste and retained native suites']
    assert len(hosts) == 1 and hosts[0]['status'] == 'completed' and hosts[0]['conclusion'] == 'failure'
    failed = {step['name'] for step in hosts[0]['steps'] if step['conclusion'] == 'failure'}
    expected_failures = {'Actual settings controls geometry pixels gestures portal and persistence'}
    if recheck:
        expected_failures.add('Authenticate source bound drop paste and retained host reports')
    assert failed == expected_failures, failed
    successes = {step['name'] for step in hosts[0]['steps'] if step['conclusion'] == 'success'}
    required_successes = {'Require fixed common start reviewed J03 and host-only changes',
            'Install reviewed J03 and rerun installed portable and GTK consumers',
            'Explicit file input backend and immutable public original readback',
            'Real pointer drop asynchronous native clipboard cancellation and reopen',
            'Strict source bound folder scope and retained palette failures'}
    if not recheck:
        required_successes.add('Authenticate source bound drop paste and retained host reports')
    assert required_successes.issubset(successes)
    artifacts = get('/actions/runs/' + run + '/artifacts?per_page=100')['artifacts']
    matches = [row for row in artifacts if row['name'] == 'reader-gtk-drop-import-%s-%s' % (run, attempt)]
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
        for name in bundle.namelist():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts

        def raw(relative, limit=4 * 1024 * 1024):
            names = [name for name in bundle.namelist() if name == relative or name.endswith('/' + relative)]
            assert len(names) == 1 and bundle.getinfo(names[0]).file_size <= limit, relative
            content = bundle.read(names[0])
            bound[relative] = hashlib.sha256(content).hexdigest()
            return content

        value = json.loads(raw('gtk-drop-evidence.json'))
        original_summary_sha256 = bound['gtk-drop-evidence.json']
        if recheck:
            assert value['source_sha'] == source and str(value['run_id']) == run and str(value['attempt']) == attempt
            assert value['ok'] is False and value['error'] == 'KeyError(\'attempt\')'
            original_value = value
            staging = Path('build/gtk-drop-recheck')
            for name in set(REQUIRED) | {'account-package/EXReader-Linux/bin/exreader-linux'}:
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw(name, 64 * 1024 * 1024 if name.endswith('/exreader-linux') else 4 * 1024 * 1024))
            environment = dict(os.environ, GITHUB_SHA=source, GITHUB_RUN_ID=run, GITHUB_RUN_ATTEMPT=attempt)
            subprocess.run(['python3', 'tests/reader_gtk_drop_import/check_evidence.py', '--build', str(staging)], env=environment, check=True)
            corrected = staging / 'gtk-drop-evidence.json'
            value = json.loads(corrected.read_text())
            assert value['program_sha256'] == original_value['program_sha256']
            corrected_summary_sha256 = hashlib.sha256(corrected.read_bytes()).hexdigest()
        validate(value, source, run, attempt)
        mutations = [('source_sha', 'foreign'), ('run_id', '0'), ('attempt', '0'), ('ok', False),
                     ('drop_import_scope_passed', False), ('accepted', True), ('complete_product', True),
                     ('six_platform_accepted', True), ('performance_accepted', True), ('program_sha256', ''), ('verified', {}),
                     ('legacy_reports_external_identity', {})]
        for key, replacement in mutations:
            invalid = copy.deepcopy(value)
            invalid[key] = replacement
            try:
                validate(invalid, source, run, attempt)
            except (AssertionError, KeyError):
                continue
            raise AssertionError('protocol accepted ' + key)
        assert hashlib.sha256(raw('account-package/EXReader-Linux/bin/exreader-linux', 64 * 1024 * 1024)).hexdigest() == value['program_sha256']
        for name, row in value['verified'].items():
            assert hashlib.sha256(raw(name)).hexdigest() == row['sha256'], name
        batch = json.loads(raw('gtk-batch-evidence.json'))
        assert batch['source_sha'] == source and str(batch['run_id']) == run and str(batch['attempt']) == attempt
        for name, row in batch['verified'].items():
            assert hashlib.sha256(raw(name)).hexdigest() == row['sha256'], name
    report = dict(accepted=False, authenticated=True, drop_import_scope_passed=True, source_sha=source, run_id=run, attempt=attempt,
                  program_source_sha=source, checker_source_sha=checker_source, checker_run_id=checker_run, checker_attempt=checker_attempt,
                  program_sha256=value['program_sha256'], legacy_reports_external_identity=value['legacy_reports_external_identity'],
                  original_failed_summary_sha256=original_summary_sha256 if recheck else None,
                  corrected_summary_sha256=corrected_summary_sha256 if recheck else None,
                  producer_reports_rechecked_without_program_execution=recheck,
                  host_job_id=hosts[0]['id'], host_job_conclusion=hosts[0]['conclusion'], protocol_rejections=len(mutations),
                  artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                  bound_files=bound, complete_product=False, settings_whole_page_palette_accepted=False)
    Path('build/gtk-drop-summary').mkdir(parents=True, exist_ok=True)
    Path('build/gtk-drop-summary/verified.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
