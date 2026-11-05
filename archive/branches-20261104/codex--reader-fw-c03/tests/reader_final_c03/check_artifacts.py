# SPDX-License-Identifier: MIT
"""Authenticate this run's C03 artifact through the GitHub API (id, bytes, digest, expiry, program hashes)."""
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile

API = 'https://api.github.com'
WORKFLOW = '.github/workflows/reader-final-c03.yml'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *unused):
        return None


def request(path, token):
    return urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                                                       'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'reader-final-c03'})


def call(path, token):
    with urllib.request.urlopen(request(path, token), timeout=120) as r:
        return r.read()


def download(repo, artifact_id, token):
    try:
        with urllib.request.build_opener(NoRedirect).open(request('/repos/%s/actions/artifacts/%s/zip' % (repo, artifact_id), token), timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise
        with urllib.request.urlopen(exc.headers['Location'], timeout=120) as r:
            return r.read()


def main():
    out = sys.argv[sys.argv.index('--output') + 1]
    token, repo = os.environ['GH_TOKEN'], os.environ['GITHUB_REPOSITORY']
    run_id, attempt, source = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_SHA']
    record = {'run_id': run_id, 'attempt': attempt, 'source': source, 'failures': []}
    name = 'reader-final-c03-%s-%s' % (run_id, attempt)
    try:
        run = json.loads(call('/repos/%s/actions/runs/%s' % (repo, run_id), token))
        assert run['head_sha'] == source and str(run['run_attempt']) == attempt and run['path'] == WORKFLOW, 'foreign run/source/workflow'
        jobs = json.loads(call('/repos/%s/actions/runs/%s/attempts/%s/jobs?per_page=100' % (repo, run_id, attempt), token))['jobs']
        producer = [j for j in jobs if j['name'] == 'C03 boundaries (ubuntu-22.04)']
        assert len(producer) == 1 and producer[0]['head_sha'] == source, 'producer job absent'
        record['producer_job'] = {'id': producer[0]['id'], 'status': producer[0]['status'], 'conclusion': producer[0]['conclusion']}
        artifacts = json.loads(call('/repos/%s/actions/runs/%s/artifacts?per_page=100' % (repo, run_id), token))['artifacts']
        match = [a for a in artifacts if a['name'] == name]
        assert len(match) == 1, 'artifact missing'
        a = match[0]
        record['artifact'] = {k: a.get(k) for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at', 'expired')}
        assert a['workflow_run']['head_sha'] == source and str(a['workflow_run']['id']) == run_id
        assert a.get('expired') is False and re.fullmatch(r'sha256:[0-9a-f]{64}', a.get('digest') or '')
        assert dt.datetime.fromisoformat(a['expires_at'].replace('Z', '+00:00')) > dt.datetime.now(dt.timezone.utc)
        data = download(repo, a['id'], token)
        record['downloaded'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        assert 'sha256:' + record['downloaded']['sha256'] == a['digest'] and len(data) == a['size_in_bytes'], 'digest/size differs'
        z = zipfile.ZipFile(io.BytesIO(data))
        res = [n for n in z.namelist() if n.endswith('c03-evidence/result.json')]
        assert len(res) == 1
        report = json.loads(z.read(res[0]).decode('utf-8'))
        record['report'] = {k: report.get(k) for k in ('accepted', 'count', 'source_sha', 'run_id', 'attempt', 'probe_sha256', 'resilience_consumer_sha256')}
        record['report']['failures'] = [f['id'] for f in report.get('failures', [])]
        assert report['source_sha'] == source and str(report['run_id']) == run_id and str(report['attempt']) == attempt
        for stem, key in (('c03-probe/cloud-probe', 'probe_sha256'), ('c03-resilience/resilience-consumer', 'resilience_consumer_sha256')):
            hit = [n for n in z.namelist() if n.endswith(stem)]
            assert len(hit) == 1 and hashlib.sha256(z.read(hit[0])).hexdigest() == report[key], stem + ' hash differs'
        assert report['accepted'] is True and report['count'] == len(report['checks']) and report.get('complete_product') is False
        assert producer[0]['conclusion'] == 'success', 'producer job did not succeed'
    except Exception as exc:
        record['failures'].append(repr(exc))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'artifacts.json'), 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(json.dumps(record['failures']))
    return 1 if record['failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
