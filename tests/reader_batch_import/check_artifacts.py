#!/usr/bin/env python3
"""Verify the same-run batch-import artifacts through the GitHub API."""
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reader-batch-import-evidence",
    })
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def download_artifact(repo, artifact_id, token):
    req = urllib.request.Request(
        API + "/repos/{}/actions/artifacts/{}/zip".format(repo, artifact_id),
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reader-batch-import-evidence",
        })
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise
        location = exc.headers.get("Location")
        if not location:
            raise
        with urllib.request.urlopen(location, timeout=120) as response:
            return response.read()


def list_artifacts(repo, run_id, token):
    payload = json.loads(request(
        "/repos/{}/actions/runs/{}/artifacts?per_page=100".format(repo, run_id),
        token).decode("utf-8"))
    return payload.get("artifacts", [])


def find_artifact(artifacts, name):
    for artifact in artifacts:
        if artifact.get("name") == name:
            return artifact
    return None


def require_report(report, source, count, names=None):
    if not isinstance(report, dict) or report.get('ok') is not True or report.get('source') != source:
        raise ValueError('report must have exact source and boolean success')
    checks=report.get('checks')
    if not isinstance(checks,list) or len(checks)!=count:
        raise ValueError('report check count differs')
    if any(not isinstance(row,dict) or row.get('ok') is not True or not isinstance(row.get('name'),str) or not row['name'] for row in checks):
        raise ValueError('report contains missing or failed checks')
    if names is not None and {row['name'] for row in checks}!=names:
        raise ValueError('review check names differ')


def report_negative_checks():
    good={'ok':True,'source':'expected','checks':[{'name':'actual','ok':True}]}
    altered=[{},dict(good,source='other'),dict(good,ok='true'),dict(good,checks=[]),dict(good,checks=[{'name':'actual','ok':False}]),dict(good,checks=[{'name':'actual','ok':1}])]
    for value in altered:
        try:require_report(value,'expected',1)
        except ValueError:continue
        raise AssertionError('altered report was accepted')
    require_report(good,'expected',1);return len(altered)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    source = os.environ.get("GITHUB_SHA", "")
    if not token or not repo or not run_id or not attempt:
        print("missing GH_TOKEN/GITHUB_REPOSITORY/GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT")
        return 2
    os.makedirs(args.output, exist_ok=True)
    suffix = "-{}-{}".format(run_id, attempt)
    artifacts = []
    for _ in range(12):
        artifacts = list_artifacts(repo, run_id, token)
        names = {a.get("name") for a in artifacts}
        if all("reader-batch-import-{}{}".format(os_name, suffix) in names
               for os_name in EXPECTED):
            break
        time.sleep(10)
    record = {"run_id": run_id, "attempt": attempt, "source": source,
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "artifacts": [], "ok": True, "failures": [], "altered_reports_rejected":report_negative_checks()}
    for os_name in EXPECTED:
        name = "reader-batch-import-{}{}".format(os_name, suffix)
        artifact = find_artifact(artifacts, name)
        item = {"os": os_name, "name": name}
        record["artifacts"].append(item)
        if not artifact:
            item["error"] = "artifact not found"
            record["failures"].append(name + ": missing")
            record["ok"] = False
            continue
        item["id"] = artifact.get("id")
        item["size_in_bytes"] = artifact.get("size_in_bytes")
        item["digest"] = artifact.get("digest")
        item["expires_at"] = artifact.get("expires_at")
        item["expired"] = artifact.get("expired")
        if (type(artifact.get('id')) is not int or artifact['id']<=0 or
            type(artifact.get('size_in_bytes')) is not int or artifact['size_in_bytes']<=0 or
            artifact.get('expired') is not False or
            re.fullmatch(r'sha256:[0-9a-f]{64}',artifact.get('digest') or '') is None):
            record['failures'].append(name+': missing/invalid strict metadata');record['ok']=False
        if artifact.get("expired"):
            record["failures"].append(name + ": expired")
            record["ok"] = False
        try:
            expires = dt.datetime.fromisoformat(
                artifact["expires_at"].replace("Z", "+00:00"))
            if expires <= dt.datetime.now(dt.timezone.utc):
                record["failures"].append(name + ": expiry in the past")
                record["ok"] = False
        except Exception as exc:
            record["failures"].append(name + ": bad expiry " + str(exc))
            record["ok"] = False
        try:
            data = download_artifact(repo, artifact["id"], token)
        except urllib.error.HTTPError as exc:
            item["error"] = "download HTTP {}".format(exc.code)
            record["failures"].append(name + ": download failed")
            record["ok"] = False
            continue
        digest = hashlib.sha256(data).hexdigest()
        item["sha256"] = digest
        item["downloaded_bytes"] = len(data)
        declared = (artifact.get("digest") or "").split(":", 1)
        if len(declared) == 2 and declared[0] == "sha256" and declared[1] != digest:
            record["failures"].append(name + ": digest mismatch")
            record["ok"] = False
        if artifact.get("size_in_bytes") not in (None, len(data)):
            record["failures"].append(name + ": size mismatch")
            record["ok"] = False
        try:
            bundle = zipfile.ZipFile(io.BytesIO(data))
            report_entry = None
            for entry in bundle.namelist():
                if entry.endswith("rb-evidence/report.json"):
                    report_entry = entry
                    break
            if not report_entry:
                record["failures"].append(name + ": report.json absent")
                record["ok"] = False
            else:
                report = json.loads(bundle.read(report_entry).decode("utf-8"))
                item["report_ok"] = report.get("ok")
                item["report_checks"] = len(report.get("checks", []))
                require_report(report,source,668)
                review_entry=[entry for entry in bundle.namelist() if entry.endswith('rb-review-evidence/review.json')]
                if len(review_entry)!=1:raise ValueError('one review report required')
                review=json.loads(bundle.read(review_entry[0]).decode('utf-8'))
                require_report(review,source,4,{'directory-budget','parent-link','copy-change','concurrent'})
                if review.get('run_id')!=run_id or review.get('attempt')!=attempt:raise ValueError('review run identity differs')
                item['review_checks']=len(review['checks'])
                if os_name=='Linux':
                    tsan_entry=[entry for entry in bundle.namelist() if entry.endswith('rb-review-evidence/tsan.txt')]
                    if len(tsan_entry)!=1:raise ValueError('TSan evidence absent')
                    tsan=bundle.read(tsan_entry[0]).decode('utf-8')
                    if 'failures=0' not in tsan or 'WARNING: ThreadSanitizer' in tsan:raise ValueError('TSan did not pass')
                if not report.get("ok"):
                    record["failures"].append(name + ": report not ok")
                    record["ok"] = False
                if source and report.get("source") and report["source"] != source:
                    record["failures"].append(name + ": source mismatch")
                    record["ok"] = False
        except Exception as exc:
            item["report_error"] = str(exc)
            record["failures"].append(name + ": zip/report " + str(exc))
            record["ok"] = False
    with open(os.path.join(args.output, "artifacts.json"), "w",
              encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
    if not record["ok"]:
        print("artifact evidence failed:", record["failures"])
        return 1
    print("artifact evidence ok:", len(record["artifacts"]), "artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
