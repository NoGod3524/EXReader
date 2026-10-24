#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the same-run external link policy artifacts through the GitHub API.

The three platform ZIPs must exist under the exact run/attempt name, carry
strict metadata (id, bytes, sha256 digest, future expiry), download to the
declared digest, and contain a report bound to the tested source, the platform,
the run identity and the bytes of the installed library, header and consumers
inside that same ZIP.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import link_fixtures  # noqa: E402

API = "https://api.github.com"
PLATFORMS = ("Linux", "Windows", "macOS")
EXPECTED_CHECKS = (
    "fixtures-shape",
    "default-cases-exact",
    "custom-cases-exact",
    "group-external-allowed",
    "group-mixed-case-scheme",
    "group-unicode",
    "group-userinfo",
    "group-protocol-relative",
    "group-encoded-separators",
    "group-double-escape",
    "group-path-escape",
    "group-forbidden-scheme",
    "group-unknown-scheme",
    "group-bad-scheme",
    "group-controls",
    "group-invalid-utf8",
    "group-overlong",
    "group-authority",
    "group-internal-allowed",
    "group-fragment-and-cfi",
    "group-escapes",
    "group-spaces",
    "group-escape-boundary",
    "probe-limits",
    "probe-errors",
    "probe-lifetime",
    "probe-interleave",
    "worker-alloc",
    "worker-cancel",
    "worker-lifetime",
    "worker-limits",
    "cpp-consumer",
    "sdk-navigation-handoff",
    "installed-header-parity",
    "installed-library-unhooked",
    "no-network-or-process-symbols",
    "symbol-audit-negative-control",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path, token, accept="application/vnd.github+json"):
    request = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reader-external-link-policy-evidence",
    })
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def download_artifact(repo, artifact_id, token):
    request = urllib.request.Request(
        API + "/repos/{}/actions/artifacts/{}/zip".format(repo, artifact_id),
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "reader-external-link-policy-evidence",
        })
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=120) as response:
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
    payload = json.loads(api("/repos/{}/actions/runs/{}/artifacts?per_page=100".format(repo, run_id),
                             token).decode("utf-8"))
    return payload.get("artifacts", [])


def find_artifact(artifacts, name):
    for artifact in artifacts:
        if artifact.get("name") == name:
            return artifact
    return None


def require_report(report, source, platform):
    if not isinstance(report, dict) or report.get("ok") is not True:
        raise ValueError("report must be a successful object")
    if report.get("source") != source:
        raise ValueError("report source differs")
    if report.get("platform") != platform:
        raise ValueError("report platform differs")
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) != len(EXPECTED_CHECKS):
        raise ValueError("report check count differs")
    if tuple(row.get("name") for row in checks) != EXPECTED_CHECKS:
        raise ValueError("report check names differ")
    for row in checks:
        if not isinstance(row, dict) or row.get("status") != "pass" or not row.get("name"):
            raise ValueError("report contains a non-passing check")
    cases = report.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("report cases missing")
    if cases.get("default") != len(link_fixtures.default_cases()) or \
            cases.get("custom") != len(link_fixtures.custom_cases()):
        raise ValueError("report case counts differ")
    groups = cases.get("groups")
    if not isinstance(groups, dict):
        raise ValueError("report groups missing")
    for group, minimum in link_fixtures.REQUIRED_GROUPS.items():
        if groups.get(group, 0) < minimum:
            raise ValueError("report group %s below minimum" % group)


def report_negative_checks():
    good = {"ok": True, "source": "expected", "platform": "Linux", "cases": None,
            "checks": []}
    # Build a structurally valid report, then break one field at a time.
    values = {
        "cases": {"default": len(link_fixtures.default_cases()),
                  "custom": len(link_fixtures.custom_cases()),
                  "groups": dict(link_fixtures.REQUIRED_GROUPS)},
        "checks": [{"name": name, "status": "pass"} for name in EXPECTED_CHECKS],
    }
    good.update(values)
    require_report(good, "expected", "Linux")
    altered = [
        dict(good, ok=False),
        dict(good, ok="true"),
        dict(good, source="other"),
        dict(good, platform="Windows"),
        dict(good, checks=good["checks"][:-1]),
        dict(good, checks=[dict(good["checks"][0], status="skip")] + good["checks"][1:]),
        dict(good, cases=dict(good["cases"], default=good["cases"]["default"] + 1)),
        dict(good, cases=dict(good["cases"], groups={})),
    ]
    for value in altered:
        try:
            require_report(value, "expected", "Linux")
        except ValueError:
            continue
        raise AssertionError("altered report was accepted")
    return len(altered)


def member_digest(bundle, suffix):
    matches = [name for name in bundle.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError("expected one member ending %r, found %r" % (suffix, matches[:4]))
    data = bundle.read(matches[0])
    return hashlib.sha256(data).hexdigest(), len(data)


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
    for _ in range(18):
        artifacts = list_artifacts(repo, run_id, token)
        names = {artifact.get("name") for artifact in artifacts}
        if all("reader-external-link-policy-{}{}".format(platform, suffix) in names
               for platform in PLATFORMS):
            break
        time.sleep(10)
    record = {"run_id": run_id, "attempt": attempt, "source": source,
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "artifacts": [], "ok": True, "failures": [],
              "altered_reports_rejected": report_negative_checks()}
    for platform in PLATFORMS:
        name = "reader-external-link-policy-{}{}".format(platform, suffix)
        artifact = find_artifact(artifacts, name)
        item = {"platform": platform, "name": name}
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
        if (type(artifact.get("id")) is not int or artifact["id"] <= 0 or
                type(artifact.get("size_in_bytes")) is not int or artifact["size_in_bytes"] <= 0 or
                artifact.get("expired") is not False or
                re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest") or "") is None):
            record["failures"].append(name + ": missing/invalid strict metadata")
            record["ok"] = False
        try:
            expires = dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            if expires <= dt.datetime.now(dt.timezone.utc):
                record["failures"].append(name + ": expiry in the past")
                record["ok"] = False
        except Exception as error:  # noqa: BLE001 - bad metadata is a failure
            record["failures"].append(name + ": bad expiry " + str(error))
            record["ok"] = False
        try:
            data = download_artifact(repo, artifact["id"], token)
        except urllib.error.HTTPError as error:
            item["error"] = "download HTTP {}".format(error.code)
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
        except Exception as error:  # noqa: BLE001 - unreadable ZIP is a failure
            record["failures"].append(name + ": not a ZIP: " + str(error))
            record["ok"] = False
            continue
        try:
            report_members = [entry for entry in bundle.namelist()
                              if entry.endswith("link-evidence/report.json")]
            if len(report_members) != 1:
                raise ValueError("one report.json required, found %d" % len(report_members))
            report = json.loads(bundle.read(report_members[0]).decode("utf-8"))
            require_report(report, source, platform)
            item["report_checks"] = len(report["checks"])
            item["report_cases"] = report["cases"]["default"]
            if report.get("run_id") != run_id or report.get("attempt") != attempt:
                raise ValueError("report run identity differs")
            library_suffix = ("link-prefix/lib/libreader_link_policy.a"
                              if platform != "Windows"
                              else "link-prefix/lib/reader_link_policy.lib")
            digest_library, size_library = member_digest(bundle, library_suffix)
            if digest_library != report["library"]["sha256"] or \
                    size_library != report["library"]["bytes"]:
                raise ValueError("installed library digest differs from the report")
            item["library_sha256"] = digest_library
            digest_header, _ = member_digest(bundle, "link-prefix/include/reader_link_policy.h")
            if digest_header != report["headers"]["sha256"]:
                raise ValueError("installed header digest differs from the report")
            item["header_sha256"] = digest_header
            for key, filename in (("probe", "link-probe"), ("cpp", "link-cpp-consumer"),
                                  ("worker", "link-worker"), ("sdk", "link-sdk-consumer")):
                digest_binary, size_binary = member_digest(
                    bundle, "link-consumer/{}{}".format(filename,
                                                        ".exe" if platform == "Windows" else ""))
                if digest_binary != report["consumers"][key]["sha256"] or \
                        size_binary != report["consumers"][key]["bytes"]:
                    raise ValueError("%s digest differs from the report" % key)
        except Exception as error:  # noqa: BLE001 - inspection failures are evidence
            item["report_error"] = str(error)
            record["failures"].append(name + ": " + str(error))
            record["ok"] = False
    with open(os.path.join(args.output, "artifacts.json"), "w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
    if not record["ok"]:
        print("artifact evidence failed:", record["failures"])
        return 1
    print("artifact evidence ok:", len(record["artifacts"]), "artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
