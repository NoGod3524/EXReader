#!/usr/bin/env python3
"""Verify the same-run local-downloads artifacts through the GitHub API (cloud only).

Rejects missing, failed, cross-source, cross-attempt, wrongly digested or
incompletely covered reports. A generated report never grants a capability by
itself: every named check must be present and individually successful.
"""
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_local_downloads import EXPECTED_CHECKS  # noqa: E402

API = "https://api.github.com"
EXPECTED = ("Windows", "Linux", "macOS")
NAMES = set(EXPECTED_CHECKS)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, token):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reader-local-downloads-evidence"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def download(repo, artifact_id, token):
    req = urllib.request.Request(
        API + "/repos/{}/actions/artifacts/{}/zip".format(repo, artifact_id),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "reader-local-downloads-evidence"})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location")
        if exc.code not in (301, 302, 303, 307, 308) or not location:
            raise
    with urllib.request.urlopen(location, timeout=120) as response:
        return response.read()


def require_report(report, source, run_id, attempt, os_name):
    if not isinstance(report, dict) or report.get("ok") is not True:
        raise ValueError("report must declare boolean success")
    for field, value in (("source", source), ("run_id", run_id), ("attempt", attempt), ("os", os_name)):
        if report.get(field) != value:
            raise ValueError("report %s differs: %r" % (field, report.get(field)))
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) != len(NAMES):
        raise ValueError("report check count differs")
    seen = set()
    for row in checks:
        if not isinstance(row, dict) or row.get("ok") is not True or not isinstance(row.get("name"), str):
            raise ValueError("report contains a missing or failed check")
        seen.add(row["name"])
    if seen != NAMES:
        raise ValueError("report check names differ: %s" % sorted(seen ^ NAMES))
    digests = report.get("consumer_sha256")
    if not isinstance(digests, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(digests.get("probe"))) or \
            not re.fullmatch(r"[0-9a-f]{64}", str(digests.get("cpp"))):
        raise ValueError("consumer digests absent")


def negative_checks():
    good = {"ok": True, "source": "s", "run_id": "1", "attempt": "1", "os": "Linux",
            "checks": [{"name": n, "ok": True} for n in EXPECTED_CHECKS],
            "consumer_sha256": {"probe": "a" * 64, "cpp": "b" * 64}}
    altered = []
    altered.append(dict(good, source="other"))
    altered.append(dict(good, run_id="2"))
    altered.append(dict(good, attempt="2"))
    altered.append(dict(good, ok="true"))
    altered.append(dict(good, checks=good["checks"][:-1]))
    altered.append(dict(good, checks=[dict(good["checks"][0], ok=False)] + good["checks"][1:]))
    altered.append(dict(good, checks=[dict(good["checks"][0], name="renamed")] + good["checks"][1:]))
    altered.append(dict(good, consumer_sha256={"probe": "x", "cpp": "b" * 64}))
    for value in altered:
        try:
            require_report(value, "s", "1", "1", "Linux")
        except ValueError:
            continue
        raise AssertionError("altered report was accepted")
    require_report(good, "s", "1", "1", "Linux")
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
    if not (token and repo and run_id and attempt and source):
        print("missing GH_TOKEN/GITHUB_REPOSITORY/GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT/GITHUB_SHA")
        return 2
    os.makedirs(args.output, exist_ok=True)
    suffix = "-{}-{}".format(run_id, attempt)
    artifacts = []
    for _ in range(12):
        artifacts = json.loads(request("/repos/{}/actions/runs/{}/artifacts?per_page=100".format(repo, run_id),
                                       token).decode("utf-8")).get("artifacts", [])
        names = {a.get("name") for a in artifacts}
        if all("reader-local-downloads-{}{}".format(o, suffix) in names for o in EXPECTED):
            break
        time.sleep(10)
    record = {"run_id": run_id, "attempt": attempt, "source": source,
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "artifacts": [], "ok": True,
              "failures": [], "altered_reports_rejected": negative_checks(), "expected_checks": len(NAMES)}
    for os_name in EXPECTED:
        name = "reader-local-downloads-{}{}".format(os_name, suffix)
        item = {"os": os_name, "name": name}
        record["artifacts"].append(item)
        artifact = next((a for a in artifacts if a.get("name") == name), None)
        if not artifact:
            record["failures"].append(name + ": missing")
            record["ok"] = False
            continue
        for field in ("id", "size_in_bytes", "digest", "expires_at", "expired"):
            item[field] = artifact.get(field)
        if (type(artifact.get("id")) is not int or artifact["id"] <= 0 or
                type(artifact.get("size_in_bytes")) is not int or artifact["size_in_bytes"] <= 0 or
                artifact.get("expired") is not False or
                re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest") or "") is None):
            record["failures"].append(name + ": invalid strict metadata")
            record["ok"] = False
        try:
            expires = dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            if expires <= dt.datetime.now(dt.timezone.utc):
                raise ValueError("expiry in the past")
        except Exception as exc:
            record["failures"].append(name + ": bad expiry " + str(exc))
            record["ok"] = False
        try:
            data = download(repo, artifact["id"], token)
        except urllib.error.HTTPError as exc:
            record["failures"].append("{}: download HTTP {}".format(name, exc.code))
            record["ok"] = False
            continue
        digest = hashlib.sha256(data).hexdigest()
        item["sha256"], item["downloaded_bytes"] = digest, len(data)
        if artifact.get("digest") != "sha256:" + digest:
            record["failures"].append(name + ": digest mismatch")
            record["ok"] = False
        if artifact.get("size_in_bytes") != len(data):
            record["failures"].append(name + ": size mismatch")
            record["ok"] = False
        try:
            bundle = zipfile.ZipFile(io.BytesIO(data))
            entries = [e for e in bundle.namelist() if e.endswith("ld-evidence/report.json")]
            if len(entries) != 1:
                raise ValueError("exactly one report.json required")
            report = json.loads(bundle.read(entries[0]).decode("utf-8"))
            require_report(report, source, run_id, attempt, os_name)
            item["report_ok"], item["report_checks"] = True, len(report["checks"])
            item["consumer_sha256"] = report["consumer_sha256"]
        except Exception as exc:
            item["report_error"] = str(exc)
            record["failures"].append(name + ": zip/report " + str(exc))
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
