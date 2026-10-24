#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run artifact aggregation for the desktop drop package.

Checks upstream job names, artifact ids, byte sizes, digests and expiry, then
re-downloads every ZIP inside Actions, recomputes its SHA-256, re-extracts the
per-platform report and re-hashes every file that report binds. Anything
missing, cross-source, cross-attempt, tampered or expired rejects the run.
"""
import argparse
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

PLATFORMS = ("windows", "linux", "macos")
API = "https://api.github.com"


class Reject(Exception):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(url, token, opener=None):
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "exr-desktop-drop-aggregate")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    if opener is not None:
        return opener.open(request)
    return urllib.request.urlopen(request)


def api_json(url, token):
    try:
        with _open(url, token) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise Reject(f"API {url} failed: {error.code} {error.reason}") from error


def download_artifact(url, token):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = _open(url, token, opener)
        with response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise Reject(f"artifact download failed: {error.code} {error.reason}") from error
        location = error.headers.get("Location")
        if not location:
            raise Reject("artifact download redirect without a location")
    with urllib.request.urlopen(location) as blob:
        return blob.read()


def pick_artifact(artifacts, name):
    matches = [entry for entry in artifacts if entry.get("name") == name]
    if not matches:
        raise Reject(f"artifact missing: {name}")
    if len(matches) > 1:
        raise Reject(f"artifact duplicated in the run: {name}")
    return matches[0]


def parse_time(text):
    if not text:
        raise Reject("artifact without expires_at")
    cleaned = text.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(cleaned)
    except ValueError as error:
        raise Reject(f"unparsable expires_at: {text}") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def validate_entry(entry, name, now=None):
    if entry.get("expired"):
        raise Reject(f"artifact expired: {name}")
    size = entry.get("size_in_bytes")
    if not isinstance(size, int) or size <= 0:
        raise Reject(f"artifact has no non-zero size: {name}")
    expires = parse_time(entry.get("expires_at"))
    now = now or datetime.now(timezone.utc)
    if expires <= now:
        raise Reject(f"artifact expires_at is already past: {name}")
    return {"id": entry.get("id"), "bytes": size, "expires_at": entry.get("expires_at"),
            "digest": entry.get("digest") or ""}


def validate_download(name, data, entry_meta, api_digest):
    if len(data) != entry_meta["bytes"]:
        raise Reject(f"{name}: downloaded {len(data)} bytes, API says {entry_meta['bytes']}")
    computed = sha256_bytes(data)
    if api_digest:
        if not api_digest.startswith("sha256:"):
            raise Reject(f"{name}: unexpected digest format {api_digest}")
        if api_digest.split(":", 1)[1] != computed:
            raise Reject(f"{name}: digest mismatch, API {api_digest} vs recomputed sha256:{computed}")
    return computed


def resolve_member(names, path):
    candidates = [name for name in names if name == path or name.endswith("/" + path)]
    if len(candidates) != 1:
        raise Reject(f"artifact member {path} resolved to {len(candidates)} entries")
    return candidates[0]


def validate_bindings(report, zip_bytes):
    checked = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        for binding in report.get("bindings", []):
            member = resolve_member(names, binding["path"])
            data = archive.read(member)
            if len(data) != binding["bytes"]:
                raise Reject(f"{binding['path']}: bytes {len(data)} != bound {binding['bytes']}")
            if sha256_bytes(data) != binding["sha256"]:
                raise Reject(f"{binding['path']}: sha256 differs from the bound value")
            checked += 1
    if checked == 0:
        raise Reject("report binds no files")
    return checked


def validate_report(report, source_sha, run_id, attempt, platform):
    if report.get("kind") != "reader-desktop-drop-report":
        raise Reject(f"{platform}: wrong report kind")
    if report.get("platform") != platform:
        raise Reject(f"{platform}: report claims platform {report.get('platform')}")
    if report.get("source_sha") != source_sha:
        raise Reject(f"{platform}: report source {report.get('source_sha')} != {source_sha}")
    run = report.get("run", {})
    if str(run.get("id")) != str(run_id):
        raise Reject(f"{platform}: report run {run.get('id')} != {run_id}")
    if str(run.get("attempt")) != str(attempt):
        raise Reject(f"{platform}: report attempt {run.get('attempt')} != {attempt}")
    if report.get("accepted") is not True:
        raise Reject(f"{platform}: report is not accepted: {report.get('problems')}")
    cases = report.get("cases", {})
    probe = cases.get("probe", [])
    portable = cases.get("portable", [])
    if not probe or not portable:
        raise Reject(f"{platform}: empty case sets")
    failed = [case["name"] for case in probe + portable if case.get("status") == "fail"]
    if failed:
        raise Reject(f"{platform}: failed cases {failed}")
    return {"probe": len(probe), "portable": len(portable),
            "skipped": [case["name"] for case in probe + portable if case.get("status") == "skip"]}


def aggregate(args):
    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    repo = args.repository or os.environ.get("GITHUB_REPOSITORY", "")
    run_id = args.run_id or os.environ.get("GITHUB_RUN_ID", "")
    attempt = args.attempt or os.environ.get("GITHUB_RUN_ATTEMPT", "")
    source_sha = args.source or os.environ.get("GITHUB_SHA", "")
    if not repo or not run_id or not attempt or not source_sha:
        raise Reject("repository, run id, attempt and source revision are required")

    run = api_json(f"{API}/repos/{repo}/actions/runs/{run_id}", token)
    if str(run.get("id")) != str(run_id):
        raise Reject("run lookup returned another run")
    if str(run.get("run_attempt")) != str(attempt):
        raise Reject(f"run attempt is {run.get('run_attempt')}, expected {attempt}")
    if run.get("head_sha") != source_sha:
        raise Reject(f"run head {run.get('head_sha')} != source {source_sha}")
    jobs = api_json(f"{API}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token).get("jobs", [])
    job_names = sorted(job.get("name", "") for job in jobs)
    artifacts = api_json(f"{API}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100", token).get(
        "artifacts", [])

    problems = []
    record = {"schema": 1, "kind": "reader-desktop-drop-aggregate", "source_sha": source_sha,
              "branch": run.get("head_branch"), "run": {"id": run_id, "attempt": attempt,
              "url": run.get("html_url"), "conclusion": run.get("conclusion")},
              "jobs": job_names, "artifacts": [], "platforms": {}, "problems": problems}
    for platform in PLATFORMS:
        name = f"reader-desktop-drop-{platform}-{run_id}-{attempt}"
        try:
            entry = pick_artifact(artifacts, name)
            meta = validate_entry(entry, name)
            data = download_artifact(f"{API}/repos/{repo}/actions/artifacts/{meta['id']}/zip", token)
            computed = validate_download(name, data, meta, entry.get("digest"))
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                member = resolve_member(archive.namelist(), "evidence/report.json")
                report = json.loads(archive.read(member).decode("utf-8"))
            cases = validate_report(report, source_sha, run_id, attempt, platform)
            bindings = validate_bindings(report, data)
            record["artifacts"].append({"platform": platform, "name": name, "id": meta["id"],
                                        "bytes": meta["bytes"], "digest": "sha256:" + computed,
                                        "api_digest": meta["digest"], "expires_at": meta["expires_at"]})
            record["platforms"][platform] = {"cases": cases, "bound_files": bindings}
        except Reject as error:
            problems.append(str(error))
    for platform in PLATFORMS:
        if platform not in record["platforms"]:
            problems.append(f"platform not aggregated: {platform}")
    record["accepted"] = not problems
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default="")
    parser.add_argument("--repository", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        record = aggregate(args)
    except Reject as error:
        print(f"rejected: {error}", file=sys.stderr)
        return 1
    os.makedirs(args.output, exist_ok=True)
    target = os.path.join(args.output, "aggregate.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    for problem in record["problems"]:
        print(f"problem: {problem}", file=sys.stderr)
    print(f"aggregate: {target} accepted={record['accepted']} artifacts={len(record['artifacts'])}")
    return 0 if record["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
