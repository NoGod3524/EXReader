# SPDX-License-Identifier: MIT
"""Authenticate actual upstream Actions jobs and ZIPs, not self-reported success."""
import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import urllib.parse
import urllib.request
import zipfile

from evidence_contract import EXPECTED_CHECKS, PLATFORMS, package_sha256, required_assets

MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key: ' + key)
        value[key] = item
    return value


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def timestamp(value):
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))


def artifact_name(runner_os, sha, run_id, attempt):
    return 'reader-conflict-actions-%s-%s-%s-%s' % (runner_os, sha, run_id, attempt)


def validate_run(run, sha, run_id, attempt):
    require(run['id'] == run_id and run['head_sha'] == sha and run['run_attempt'] == attempt, 'wrong run identity')
    require(run['path'] == '.github/workflows/reader-explicit-conflict-actions.yml', 'wrong workflow')


def select_job(jobs, runner_os, sha, run_id, attempt):
    label = PLATFORMS[runner_os][0]
    found = [j for j in jobs if j['name'] == 'installed explicit conflict actions (%s)' % label]
    require(len(found) == 1, 'missing or duplicate upstream job: ' + label)
    job = found[0]
    require(job['run_id'] == run_id and job['run_attempt'] == attempt and job['head_sha'] == sha, 'wrong job identity')
    require(job['status'] == 'completed' and job['conclusion'] == 'success', 'upstream job did not complete successfully')
    return job


def select_artifact(artifacts, runner_os, sha, run_id, attempt, job, now):
    name = artifact_name(runner_os, sha, run_id, attempt)
    found = [a for a in artifacts if a['name'] == name]
    require(len(found) == 1, 'missing or duplicate artifact: ' + name)
    artifact = found[0]
    require(isinstance(artifact['id'], int) and artifact['id'] > 0, 'invalid artifact ID')
    require(0 < artifact['size_in_bytes'] <= MAX_ZIP_BYTES, 'empty or oversized artifact')
    require(not artifact['expired'] and timestamp(artifact['expires_at']) > now, 'expired artifact')
    require(timestamp(job['started_at']) <= timestamp(artifact['created_at']) <= timestamp(job['completed_at']), 'artifact outside upstream job lifetime')
    require(artifact['workflow_run']['id'] == run_id and artifact['workflow_run']['head_sha'] == sha, 'wrong artifact source/run')
    digest = artifact['digest']
    require(isinstance(digest, str) and len(digest) == 71 and digest.startswith('sha256:') and all(c in '0123456789abcdef' for c in digest[7:]), 'missing API SHA-256 digest')
    return artifact


def validate_zip(raw, artifact, runner_os, sha, run_id, attempt):
    require(len(raw) == artifact['size_in_bytes'], 'ZIP byte count differs from API')
    require('sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest'], 'ZIP digest differs from API')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        require(len(names) == len(set(names)), 'duplicate ZIP member')
        require(len(names) <= 200 and sum(i.file_size for i in infos) <= MAX_EXPANDED_BYTES, 'ZIP expanded limit')
        for info in infos:
            path = PurePosixPath(info.filename)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in info.filename and ':' not in info.filename, 'unsafe ZIP member')
            require((info.external_attr >> 16) & 0o170000 != 0o120000, 'symlink ZIP member')
        reports = [n for n in names if PurePosixPath(n).name == 'evidence.json']
        require(reports == ['evidence/evidence.json'], 'missing or duplicate evidence report')
        report = decode(archive.read(reports[0]))
        require(report['sha'] == sha and report['run_id'] == run_id and report['run_attempt'] == attempt, 'wrong report source/run/attempt')
        require(report['runner_os'] == runner_os and report['os'] == PLATFORMS[runner_os][1], 'wrong report platform')
        require(report['job'] == 'conflict-actions' and report['matrix_os'] == PLATFORMS[runner_os][0], 'wrong report job')
        require(report['accepted'] is True and report['local_run'] is False, 'non-Actions or unaccepted report')
        require(report['checks'] == EXPECTED_CHECKS, 'missing, duplicate or changed named checks')
        assets = report['assets']
        require(len({a['path'] for a in assets}) == len(assets), 'duplicate asset identity')
        require({a['path']: a['role'] for a in assets} == required_assets(runner_os), 'missing or unexpected consumer/package identity')
        for asset in assets:
            require(asset['path'] in names, 'missing bound binary/package file')
            data = archive.read(asset['path'])
            require(0 < len(data) == asset['bytes'], 'empty or changed asset length')
            require(hashlib.sha256(data).hexdigest() == asset['sha256'], 'changed consumer/package SHA-256')
            if asset['role'] in ('c_consumer', 'cxx_consumer'):
                magic = {'Linux': (b'\x7fELF',), 'Windows': (b'MZ',), 'macOS': (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')}
                require(data.startswith(magic[runner_os]), 'consumer is not a native platform binary')
        require(report['installed_package_sha256'] == package_sha256(assets), 'wrong installed package manifest digest')
    return report


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        require(urllib.parse.urlsplit(newurl).scheme == 'https', 'non-HTTPS API redirect')
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(request.full_url).netloc:
            redirected.remove_header('Authorization')
        return redirected


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    sha, run_id, attempt = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == sha, 'checkout source mismatch')
    base = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY']
    opener = urllib.request.build_opener(SafeRedirect())

    def request(path, binary=False):
        req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
            'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        with opener.open(req, timeout=120) as response:
            raw = response.read(MAX_ZIP_BYTES + 1)
        require(len(raw) <= MAX_ZIP_BYTES, 'API response exceeds limit')
        return raw if binary else decode(raw)

    def pages(path, key):
        values = []
        for page in range(1, 101):
            response = request(path + '?per_page=100&page=' + str(page))
            values.extend(response[key])
            if len(values) >= response['total_count']:
                require(len(values) == response['total_count'], 'inconsistent API pagination')
                return values
        raise ValueError('API pagination limit')

    run = request('/actions/runs/%s/attempts/%s' % (run_id, attempt))
    validate_run(run, sha, run_id, attempt)
    jobs = pages('/actions/runs/%s/attempts/%s/jobs' % (run_id, attempt), 'jobs')
    artifacts = pages('/actions/runs/%s/artifacts' % run_id, 'artifacts')
    require(len({a['id'] for a in artifacts}) == len(artifacts), 'duplicate API artifact ID')
    output = {'accepted': False, 'sha': sha, 'run_id': run_id, 'run_attempt': attempt, 'checks': EXPECTED_CHECKS, 'platforms': []}
    Path('strict-evidence').mkdir(exist_ok=True)
    for runner_os in PLATFORMS:
        job = select_job(jobs, runner_os, sha, run_id, attempt)
        artifact = select_artifact(artifacts, runner_os, sha, run_id, attempt, job, datetime.datetime.now(datetime.timezone.utc))
        raw = request('/actions/artifacts/%s/zip' % artifact['id'], binary=True)
        # Preserve actual source ZIP bytes; never extract or execute downloaded content.
        Path('strict-evidence/%s.zip' % artifact['id']).write_bytes(raw)
        report = validate_zip(raw, artifact, runner_os, sha, run_id, attempt)
        output['platforms'].append({'runner_os': runner_os, 'job': job, 'artifact': artifact,
            'recomputed_zip_sha256': hashlib.sha256(raw).hexdigest(), 'recomputed_zip_bytes': len(raw),
            'assets': report['assets'], 'installed_package_sha256': report['installed_package_sha256']})
    output['accepted'] = True
    Path('strict-evidence/summary.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2), flush=True)


if __name__ == '__main__':
    main()
