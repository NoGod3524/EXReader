#!/usr/bin/env python3
"""Strict same-run aggregation for the J19 reader-tts-linux workflow.

Downloads this run's artifacts through the Actions REST API, binds every artifact
(id, name tokens, byte size, sha256 digest, expiry) to this source, run and
attempt, recomputes the ZIP digest locally, verifies the archived per-file
digests, re-validates every named case against the fixed expectations and only
then writes an accepted summary. Anything missing, cross-source, cross-attempt or
tampered is rejected.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

API_ROOT = "https://api.github.com"


def problem_list():
    return []


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def verify_artifact_meta(meta, expected_name, source_sha, run_id, run_attempt):
    """Checks the artifact record itself against this source/run/attempt."""
    problems = problem_list()
    if meta.get("name") != expected_name:
        problems.append("artifact name %r != expected %r" % (meta.get("name"), expected_name))
    if meta.get("expired"):
        problems.append("artifact %r is expired" % meta.get("name"))
    size = meta.get("size_in_bytes")
    if not isinstance(size, int) or size <= 0:
        problems.append("artifact %r has no byte size (%r)" % (meta.get("name"), size))
    digest = meta.get("digest") or ""
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        problems.append("artifact %r has no sha256 digest (%r)" % (meta.get("name"), digest))
    run = (meta.get("workflow_run") or {})
    if int(run.get("id") or 0) != int(run_id):
        problems.append("artifact %r belongs to run %r, not %r"
                        % (meta.get("name"), run.get("id"), run_id))
    head_sha = run.get("head_sha")
    if head_sha and head_sha != source_sha:
        problems.append("artifact %r was produced from %r, not %r"
                        % (meta.get("name"), head_sha, source_sha))
    if ("-r%s-a%s-" % (run_id, run_attempt)) not in (meta.get("name") or ""):
        problems.append("artifact %r does not carry run/attempt tokens r%s-a%s"
                        % (meta.get("name"), run_id, run_attempt))
    if not (meta.get("expires_at") or "").endswith("Z"):
        problems.append("artifact %r has no expiry timestamp" % meta.get("name"))
    return problems


def verify_zip(zip_bytes, meta):
    problems = problem_list()
    if not zip_bytes:
        problems.append("downloaded ZIP for %r is empty" % meta.get("name"))
        return problems
    if meta.get("size_in_bytes") and len(zip_bytes) != int(meta["size_in_bytes"]):
        problems.append("downloaded ZIP for %r has %d bytes, API reported %s"
                        % (meta.get("name"), len(zip_bytes), meta.get("size_in_bytes")))
    digest = (meta.get("digest") or "").split("sha256:")[-1]
    actual = sha256_bytes(zip_bytes)
    if digest and digest != actual:
        problems.append("ZIP digest mismatch for %r (%s != %s)"
                        % (meta.get("name"), actual, digest))
    return problems


def evidence_prefix(names):
    """Directory inside the artifact that holds the evidence ("" at the root)."""
    for name in names:
        if name.rsplit("/", 1)[-1] == "results.json":
            return name.rsplit("/", 1)[0] if "/" in name else ""
    return None


def scope_entries(actual, prefix):
    """Keeps only the files under the evidence prefix and strips it, so the
    per-file manifest (written relative to the evidence directory) applies."""
    scoped = {}
    for name, digest in actual.items():
        if prefix:
            if not name.startswith(prefix + "/"):
                continue
            scoped[name[len(prefix) + 1:]] = digest
        else:
            scoped[name] = digest
    return scoped


def verify_file_manifest(entries, actual):
    """entries: list of (sha256, relpath) from files.sha256; actual: relpath->sha."""
    problems = problem_list()
    listed = {}
    for line in entries:
        parts = line.strip().split("  ", 1)
        if len(parts) != 2:
            problems.append("malformed manifest line %r" % line)
            continue
        digest, rel = parts
        listed[rel] = digest
    for rel, digest in listed.items():
        if rel not in actual:
            problems.append("manifest lists %r but the archive does not contain it" % rel)
        elif actual[rel] != digest:
            problems.append("archive content of %r does not match the manifest digest" % rel)
    for rel in actual:
        if rel not in listed and rel != "files.sha256":
            problems.append("archive file %r is not covered by files.sha256" % rel)
    return problems


def verify_payload(payload, expected, source_sha, run_id, run_attempt):
    problems = problem_list()
    if payload.get("package") != "J19-reader-tts-linux":
        problems.append("payload package is %r" % payload.get("package"))
    if payload.get("source_sha") != source_sha:
        problems.append("payload source %r != %r" % (payload.get("source_sha"), source_sha))
    if int(payload.get("run_id") or 0) != int(run_id):
        problems.append("payload run %r != %r" % (payload.get("run_id"), run_id))
    if int(payload.get("run_attempt") or 0) != int(run_attempt):
        problems.append("payload attempt %r != %r" % (payload.get("run_attempt"), run_attempt))
    if payload.get("accepted") is not True:
        problems.append("payload is not marked accepted")
    if payload.get("problems"):
        problems.append("payload carries %d problem(s)" % len(payload["problems"]))
    counts = payload.get("counts") or {}
    if int(counts.get("fail") or 0) != 0:
        problems.append("payload has %s failing case(s)" % counts.get("fail"))
    if int(counts.get("skip") or 0) != 0:
        problems.append("payload has %s skipped case(s)" % counts.get("skip"))
    if int(counts.get("other") or 0) != 0:
        problems.append("payload has %s case(s) with an unknown status" % counts.get("other"))
    env = payload.get("env") or {}
    if not env.get("socket"):
        problems.append("payload records no daemon socket")
    if not (env.get("binaries") or {}):
        problems.append("payload records no consumer binary digests")
    for name, info in (env.get("binaries") or {}).items():
        if not info.get("sha256") or int(info.get("bytes") or 0) <= 0:
            problems.append("consumer %r has no digest or size" % name)
    if not env.get("libspeechd_header_sha256"):
        problems.append("payload does not pin the libspeechd header digest")

    cases = payload.get("cases") or []
    total_expected = sum(len(v) for v in expected.values())
    if len(cases) != total_expected:
        problems.append("payload has %d cases, %d were expected" % (len(cases), total_expected))
    for phase, names in expected.items():
        got = [c.get("name") for c in cases if c.get("phase") == phase]
        for want in names:
            if got.count(want) == 0:
                problems.append("missing case %s/%s" % (phase, want))
            elif got.count(want) > 1:
                problems.append("duplicate case %s/%s" % (phase, want))
        for have in got:
            if have not in names:
                problems.append("unexpected case %s/%s" % (phase, have))
    for case in cases:
        label = "%s/%s" % (case.get("phase"), case.get("name"))
        if case.get("status") != "pass":
            problems.append("case %s has status %r" % (label, case.get("status")))
        if not case.get("detail"):
            problems.append("case %s has no detail" % label)
    return problems


def api_get(url, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "j19-reader-tts-linux-aggregate",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, dict(resp.headers), resp.read()


def list_artifacts(repo, run_id, token):
    artifacts = []
    page = 1
    while True:
        url = "%s/repos/%s/actions/runs/%s/artifacts?per_page=100&page=%d" % (API_ROOT, repo, run_id, page)
        status, _, body = api_get(url, token)
        if status != 200:
            raise RuntimeError("artifact list returned %d" % status)
        data = json.loads(body.decode("utf-8"))
        artifacts.extend(data.get("artifacts") or [])
        if len(artifacts) >= int(data.get("total_count") or 0):
            return artifacts
        page += 1


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the API token away from the pre-signed blob host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_artifact(repo, artifact_id, token):
    url = "%s/repos/%s/actions/artifacts/%s/zip" % (API_ROOT, repo, artifact_id)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer %s" % token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "j19-reader-tts-linux-aggregate",
    })
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=300) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError("artifact redirect without a Location header")
        blob = urllib.request.Request(location, headers={
            "User-Agent": "j19-reader-tts-linux-aggregate",
        })
        with urllib.request.urlopen(blob, timeout=300) as resp:
            return resp.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--keys", required=True,
                    help="comma separated job keys that must each produce one artifact")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "0"))
    ap.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "0"))
    ap.add_argument("--source-sha", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""))
    args = ap.parse_args()

    with open(args.expected) as f:
        expected = json.load(f)["phases"]
    keys = [k for k in args.keys.split(",") if k]
    sha_token = args.source_sha
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.downloads, exist_ok=True)

    if not args.token:
        print("no GitHub token available", file=sys.stderr)
        return 3

    artifacts = list_artifacts(args.repo, args.run_id, args.token)
    problems = []
    summary = {
        "schema": 1,
        "package": "J19-reader-tts-linux",
        "source_sha": args.source_sha,
        "run_id": int(args.run_id),
        "run_attempt": int(args.run_attempt),
        "repo": args.repo,
        "jobs": {},
        "problems": problems,
        "accepted": False,
    }
    total_cases = 0
    for key in keys:
        wanted = "reader-tts-linux-%s-r%s-a%s-%s" % (key, args.run_id, args.run_attempt, sha_token)
        matches = [a for a in artifacts if a.get("name") == wanted]
        if len(matches) != 1:
            problems.append("expected exactly one artifact named %r, found %d" % (wanted, len(matches)))
            continue
        meta = matches[0]
        meta_problems = verify_artifact_meta(meta, wanted, args.source_sha, args.run_id,
                                            args.run_attempt)
        problems.extend("%s: %s" % (key, p) for p in meta_problems)
        zip_bytes = download_artifact(args.repo, meta["id"], args.token)
        problems.extend("%s: %s" % (key, p) for p in verify_zip(zip_bytes, meta))
        zip_path = os.path.join(args.downloads, "%s.zip" % wanted)
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        actual = {}
        payload = None
        manifest_text = None
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    data = zf.read(info)
                    actual[info.filename] = sha256_bytes(data)
                    base = info.filename.rsplit("/", 1)[-1]
                    if base == "results.json" and payload is None:
                        payload = json.loads(data.decode("utf-8"))
                    elif base == "files.sha256" and manifest_text is None:
                        manifest_text = data.decode("utf-8")
        except (zipfile.BadZipFile, ValueError) as exc:
            problems.append("%s: unusable ZIP: %s" % (key, exc))
            continue
        if payload is None:
            problems.append("%s: no results.json inside the artifact" % key)
            continue
        prefix = evidence_prefix(list(actual))
        if prefix is None:
            problems.append("%s: results.json is not inside a directory" % key)
            continue
        if not manifest_text:
            problems.append("%s: no files.sha256 inside the artifact" % key)
        else:
            scoped = scope_entries(actual, prefix)
            problems.extend("%s: %s" % (key, p)
                            for p in verify_file_manifest(manifest_text.splitlines(), scoped))
        problems.extend("%s: %s" % (key, p)
                        for p in verify_payload(payload, expected, args.source_sha,
                                                args.run_id, args.run_attempt))
        total_cases += len(payload.get("cases") or [])
        summary["jobs"][key] = {
            "artifact_id": meta["id"],
            "artifact_name": meta["name"],
            "size_in_bytes": meta["size_in_bytes"],
            "zip_sha256": sha256_bytes(zip_bytes),
            "api_digest": meta.get("digest"),
            "expires_at": meta.get("expires_at"),
            "created_at": meta.get("created_at"),
            "cases": len(payload.get("cases") or []),
            "counts": payload.get("counts"),
            "image": (payload.get("env") or {}).get("image"),
            "speech_dispatcher": (payload.get("env") or {}).get("speech_dispatcher"),
            "binaries": (payload.get("env") or {}).get("binaries"),
        }

    summary["cases_total"] = total_cases
    summary["accepted"] = not problems
    with open(os.path.join(args.output, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    lines = ["# J19 reader-tts-linux same-run aggregation", ""]
    lines.append("- source: %s" % args.source_sha)
    lines.append("- run/attempt: %s/%s" % (args.run_id, args.run_attempt))
    lines.append("- accepted: %s" % summary["accepted"])
    lines.append("")
    for key, info in summary["jobs"].items():
        lines.append("## %s" % key)
        lines.append("")
        lines.append("- artifact %s (%s bytes)" % (info["artifact_id"], info["size_in_bytes"]))
        lines.append("- sha256 %s" % info["zip_sha256"])
        lines.append("- expires %s" % info["expires_at"])
        lines.append("- cases %s %s" % (info["cases"], json.dumps(info["counts"])))
        lines.append("- image %s / %s" % (info["image"], info["speech_dispatcher"]))
        lines.append("")
    if problems:
        lines.append("## Problems")
        lines.append("")
        for problem in problems:
            lines.append("- %s" % problem)
    with open(os.path.join(args.output, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    for problem in problems:
        print("PROBLEM %s" % problem)
    print("accepted=%s jobs=%d cases=%d" % (summary["accepted"], len(summary["jobs"]), total_cases))
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
