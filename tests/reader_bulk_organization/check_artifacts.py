#!/usr/bin/env python3
"""Verify the same-run bulk organization artifacts through the GitHub API."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"
EXPECTED = ("Windows", "Linux", "macOS")
CHECKS = 21


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def headers(token):
    return {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reader-bulk-organization-evidence"}


def request(path, token):
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers(token)), timeout=120) as response:
        return response.read()


def download_artifact(repo, artifact_id, token):
    req = urllib.request.Request(API + "/repos/{}/actions/artifacts/{}/zip".format(repo, artifact_id), headers=headers(token))
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location")
        if exc.code not in (301, 302, 303, 307, 308) or not location:
            raise
        with urllib.request.urlopen(location, timeout=300) as response:
            return response.read()


def require_report(report, source, count, run_id, attempt):
    if not isinstance(report, dict) or report.get('ok') is not True or report.get('source') != source:
        raise ValueError('report must have exact source and boolean success')
    if report.get('run_id') != run_id or report.get('attempt') != attempt:
        raise ValueError('report run identity differs')
    checks = report.get('checks')
    if not isinstance(checks, list) or len(checks) != count:
        raise ValueError('report check count differs')
    if any(not isinstance(row, dict) or row.get('ok') is not True or not isinstance(row.get('name'), str) or not row['name'] for row in checks):
        raise ValueError('report contains missing or failed checks')
    if len({row['name'] for row in checks}) != count:
        raise ValueError('report check names repeat')
    if report.get('books') != 2202 or report.get('max_batch') != 100:
        raise ValueError('report scale differs')


def altered_reports_rejected():
    good = {'ok': True, 'source': 's', 'run_id': '1', 'attempt': '1', 'books': 2202, 'max_batch': 100,
            'checks': [{'name': 'a', 'ok': True}]}
    altered = [{}, dict(good, source='x'), dict(good, ok='true'), dict(good, checks=[]), dict(good, checks=[{'name': 'a', 'ok': False}]),
               dict(good, checks=[{'name': 'a', 'ok': 1}]), dict(good, run_id='2'), dict(good, books=10), dict(good, max_batch=101)]
    for value in altered:
        try:
            require_report(value, 's', 1, '1', '1')
        except ValueError:
            continue
        raise AssertionError('altered report was accepted')
    require_report(good, 's', 1, '1', '1')
    return len(altered)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    source = os.environ.get("GITHUB_SHA", "")
    if not token or not repo or not run_id or not attempt or not source:
        print("missing GH_TOKEN/GITHUB_REPOSITORY/GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT/GITHUB_SHA")
        return 2
    os.makedirs(args.output, exist_ok=True)
    suffix = "-{}-{}".format(run_id, attempt)
    artifacts = []
    for _ in range(12):
        artifacts = json.loads(request("/repos/{}/actions/runs/{}/artifacts?per_page=100".format(repo, run_id), token).decode("utf-8")).get("artifacts", [])
        names = {a.get("name") for a in artifacts}
        if all("reader-bulk-organization-{}{}".format(name, suffix) in names for name in EXPECTED):
            break
        time.sleep(10)
    record = {"run_id": run_id, "attempt": attempt, "source": source,
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "artifacts": [], "ok": True, "failures": [], "altered_reports_rejected": altered_reports_rejected()}
    for os_name in EXPECTED:
        name = "reader-bulk-organization-{}{}".format(os_name, suffix)
        item = {"os": os_name, "name": name}
        record["artifacts"].append(item)
        found = [a for a in artifacts if a.get("name") == name]
        artifact = found[0] if len(found) == 1 else None
        if not artifact:
            item["error"] = "artifact not found"
            record["failures"].append(name + ": missing")
            record["ok"] = False
            continue
        for field in ("id", "size_in_bytes", "digest", "expires_at", "expired"):
            item[field] = artifact.get(field)
        if (type(artifact.get('id')) is not int or artifact['id'] <= 0 or type(artifact.get('size_in_bytes')) is not int or
                artifact['size_in_bytes'] <= 0 or artifact.get('expired') is not False or
                re.fullmatch(r'sha256:[0-9a-f]{64}', artifact.get('digest') or '') is None):
            record['failures'].append(name + ': missing/invalid strict metadata')
            record['ok'] = False
            continue
        try:
            run = json.loads(request('/repos/%s/actions/runs/%s' % (repo, run_id), token))
            if run['head_sha'] != source or str(run['run_attempt']) != attempt or run['path'] != '.github/workflows/reader-bulk-organization.yml':
                raise ValueError('foreign source/run/workflow')
            jobs = json.loads(request('/repos/%s/actions/runs/%s/attempts/%s/jobs?per_page=100' % (repo, run_id, attempt), token))['jobs']
            runner = {'Linux': 'ubuntu-22.04', 'Windows': 'windows-2022', 'macOS': 'macos-15'}[os_name]
            producers = [j for j in jobs if j['name'] == 'bulk organization (%s)' % runner]
            if len(producers) != 1 or producers[0]['head_sha'] != source or producers[0]['status'] != 'completed' or producers[0]['conclusion'] != 'success':
                raise ValueError('required producer did not succeed')
            item['job_id'] = producers[0]['id']
            if artifact['workflow_run']['head_sha'] != source or str(artifact['workflow_run']['id']) != run_id:
                raise ValueError('foreign artifact')
            expires = dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            if expires <= dt.datetime.now(dt.timezone.utc):
                raise ValueError('expiry in the past')
            data = download_artifact(repo, artifact["id"], token)
            digest = hashlib.sha256(data).hexdigest()
            item["sha256"] = digest
            item["downloaded_bytes"] = len(data)
            if artifact["digest"] != 'sha256:' + digest or artifact["size_in_bytes"] != len(data):
                raise ValueError('digest or size mismatch')
            bundle = zipfile.ZipFile(io.BytesIO(data))
            entries = [entry for entry in bundle.namelist() if entry.endswith('bulk-evidence/report.json')]
            if len(entries) != 1:
                raise ValueError('exactly one report.json is required')
            report = json.loads(bundle.read(entries[0]).decode('utf-8'))
            require_report(report, source, CHECKS, run_id, attempt)
            programs = [entry for entry in bundle.namelist() if entry.endswith('bulk-consumer/bulk-probe' + ('.exe' if os_name == 'Windows' else ''))]
            if len(programs) != 1 or hashlib.sha256(bundle.read(programs[0])).hexdigest() != report['probe_sha256']:
                raise ValueError('consumer identity differs')
            item["report_checks"] = len(report["checks"])
            item["timings"] = report.get("timings")
        except Exception as exc:
            item["report_error"] = str(exc)
            record["failures"].append(name + ": " + str(exc))
            record["ok"] = False
    with open(os.path.join(args.output, "artifacts.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
    if not record["ok"]:
        print("artifact evidence failed:", record["failures"])
        return 1
    print("artifact evidence ok:", len(record["artifacts"]), "artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
