# SPDX-License-Identifier: MIT
"""Strict same-source aggregation of the J17 producers.

Runs in Actions with a read-only token: lists this run's artifacts through the
API, re-downloads every producer ZIP, recomputes its SHA-256, unzips it in
memory, and re-verifies the identity inside (source SHA, run id, attempt,
platform, failing cases). A missing artifact, a cross-run or cross-attempt
artifact, a size or digest mismatch, or a failing producer rejects the run.

When a producer failed, this job still runs: it prints every non-passing case it
finds in the uploaded reports (DIAG lines) and fails, so the diagnosis stays in
Actions instead of requiring a local artifact download.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import zipfile

API = 'https://api.github.com'
EXPECTED = {
    'macos': 'reader-tts-apple-macos-{run}-{attempt}',
    'ios-simulator': 'reader-tts-apple-ios-{run}-{attempt}',
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def api(path):
    token = os.environ['GH_TOKEN']
    request = urllib.request.Request(
        API + path,
        headers={'Authorization': 'Bearer ' + token,
                 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28',
                 'User-Agent': 'exreader-tts-apple-aggregate'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def download(url):
    token = os.environ['GH_TOKEN']
    headers = {'Authorization': 'Bearer ' + token,
               'Accept': 'application/vnd.github+json',
               'User-Agent': 'exreader-tts-apple-aggregate'}

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers['Location']
        with urllib.request.urlopen(urllib.request.Request(location), timeout=600) as response:
            return response.read()


def diagnose(platform, report):
    """Print every non-passing case of one producer report."""
    for case in report.get('checks', []):
        if case.get('status') != 'pass':
            print('DIAG %s %s %s: %s' % (platform, case.get('status'), case.get('name'), case.get('detail')),
                  flush=True)
    if report.get('platform') == 'ios-simulator':
        for case in (report.get('ipad') or {}).get('checks', []):
            if case.get('status') != 'pass':
                print('DIAG ios-simulator-ipad %s %s: %s' % (case.get('status'), case.get('name'),
                                                             case.get('detail')), flush=True)


def verify_producer(platform, entry, wanted, source_sha, run_id, attempt, artifacts_in_zip):
    require(entry['size_in_bytes'] > 0, '%s is empty' % wanted)
    require(not entry.get('expired'), '%s has expired' % wanted)
    require(entry.get('expires_at'), '%s has no expiry' % wanted)
    require(entry.get('digest', '').startswith('sha256:'), '%s has no sha256 digest' % wanted)
    require(entry['workflow_run']['head_sha'] == source_sha,
            '%s was produced from %s, not the tested source' % (wanted, entry['workflow_run']['head_sha']))

    payload = download(entry['archive_download_url'])
    digest = 'sha256:' + hashlib.sha256(payload).hexdigest()
    require(digest == entry['digest'], '%s digest mismatch: api %s zip %s' % (wanted, entry['digest'], digest))
    require(len(payload) == entry['size_in_bytes'],
            '%s size mismatch: api %d zip %d' % (wanted, entry['size_in_bytes'], len(payload)))

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        artifacts_in_zip.extend(names)
        report_name = next((name for name in names if name.endswith('result.json')), None)
        require(report_name is not None, '%s carries no result.json (has %s)' % (wanted, names[:8]))
        report = json.loads(archive.read(report_name).decode('utf-8'))
        diagnose(platform, report)
        require(report['source_sha'] == source_sha, '%s reports source %r' % (wanted, report['source_sha']))
        require(int(report['run_id']) == int(run_id), '%s reports run %r' % (wanted, report['run_id']))
        require(int(report['attempt']) == int(attempt), '%s reports attempt %r' % (wanted, report['attempt']))
        require(report['platform'] == platform, '%s reports platform %r' % (wanted, report['platform']))
        require(report['counts']['fail'] == 0, '%s carries failing cases: %s' % (wanted, report['counts']))
        require(report['counts']['pass'] > 0, '%s carries no passing case' % wanted)
        pcm = (report.get('probe') or {}).get('pcm')
        if pcm:
            wanted_wav = pcm.get('file') or '.wav'
            wav_name = next((name for name in names if name.endswith(wanted_wav)), None)
            require(wav_name is not None, '%s ships no %s' % (wanted, wanted_wav))
            wav = archive.read(wav_name)
            require(hashlib.sha256(wav).hexdigest() == pcm['sha256'],
                    '%s wav digest does not match its report' % wanted)
            require(len(wav) == pcm['bytes'], '%s wav size does not match its report' % wanted)
        return report, digest


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    repository = os.environ['GITHUB_REPOSITORY']
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    source_sha = os.environ['GITHUB_SHA']
    out = Path('build/tts-apple-evidence')
    out.mkdir(parents=True, exist_ok=True)

    artifacts = api('/repos/%s/actions/runs/%s/artifacts?per_page=100' % (repository, run_id))['artifacts']
    jobs = api('/repos/%s/actions/runs/%s/jobs?per_page=100' % (repository, run_id))['jobs']

    problems = []
    collected = []
    for platform, pattern in EXPECTED.items():
        wanted = pattern.format(run=run_id, attempt=attempt)
        matches = [entry for entry in artifacts if entry['name'] == wanted]
        if len(matches) != 1:
            problems.append('expected exactly one artifact named %s, found %d' % (wanted, len(matches)))
            continue
        entry = matches[0]
        names = []
        try:
            report, digest = verify_producer(platform, entry, wanted, source_sha, run_id, attempt, names)
        except AssertionError as error:
            problems.append(str(error))
            continue
        collected.append({
            'id': entry['id'],
            'name': entry['name'],
            'size_in_bytes': entry['size_in_bytes'],
            'digest': entry['digest'],
            'zip_sha256_recomputed': digest,
            'expires_at': entry['expires_at'],
            'expired': entry['expired'],
            'head_sha': entry['workflow_run']['head_sha'],
            'platform': report['platform'],
            'counts': report['counts'],
            'speech_available': report.get('speech_available'),
            'speech_note': report.get('speech_note'),
            'pcm': (report.get('probe') or {}).get('pcm'),
            'consumer_sha256': report.get('consumer_sha256'),
            'os': report.get('os'),
            'arch': report.get('arch'),
            'entries': len(names),
        })

    for job in jobs:
        if job['name'].endswith('same-source evidence'):
            continue
        if job['conclusion'] != 'success':
            problems.append('producer job %r concluded %r' % (job['name'], job['conclusion']))

    aggregate = {
        'accepted': not problems and len(collected) == len(EXPECTED),
        'schema': 1,
        'package': 'J17 reader-tts-apple',
        'source_sha': source_sha,
        'run_id': int(run_id),
        'attempt': int(attempt),
        'artifacts': collected,
        'jobs': [{'id': job['id'], 'name': job['name'], 'conclusion': job['conclusion']} for job in jobs],
        'platforms': {entry['platform']: entry['counts'] for entry in collected},
        'problems': problems,
    }
    (out / 'result.json').write_text(json.dumps(aggregate, indent=2), encoding='utf-8')
    sys.stdout.write('EVIDENCE_JSON_BEGIN\n')
    sys.stdout.write(json.dumps(aggregate, indent=2) + '\n')
    sys.stdout.write('EVIDENCE_JSON_END\n')
    sys.stdout.flush()
    if problems:
        for problem in problems:
            print('PROBLEM %s' % problem, flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
