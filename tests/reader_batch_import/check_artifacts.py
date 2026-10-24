#!/usr/bin/env python3
"""Verify the same-run batch-import artifacts through the GitHub API."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"
EXPECTED = ("Windows", "Linux", "macOS")


def request(path, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reader-batch-import-evidence",
    })
    with urllib.request.urlopen(req, timeout=120) as response:
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
              "artifacts": [], "ok": True, "failures": []}
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
            data = request("/repos/{}/actions/artifacts/{}/zip".format(
                repo, artifact["id"]), token)
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
