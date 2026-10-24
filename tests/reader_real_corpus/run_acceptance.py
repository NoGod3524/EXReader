#!/usr/bin/env python3
"""Strict runner for the reader real-corpus acceptance package.

The repository stores only this consumer, the fixed manifest, source/licence
records and expectations. Corpus bytes are downloaded and parsed in CI.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FORMATS = ["EPUB", "TXT", "PDF", "HTML", "FB2", "DOCX", "RTF", "MOBI", "CBZ"]
OPS = [
    "import", "readback", "open", "metadata.title", "metadata.entries", "toc",
    "pages.first", "pages.middle", "pages.last", "pages.sequential", "pages.back",
    "find", "anchor.capture", "anchor.resolve", "anchor.resolve_reopen", "reopen",
]
USER_AGENT = "EXReader-reader-real-corpus/1.0 (+https://github.com/NoGod3524/EXReader)"
MAX_BYTES = 64 * 1024 * 1024
MAX_LICENSE_BYTES = 4 * 1024 * 1024


class CorpusError(RuntimeError):
    pass


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_manifest(manifest, mode="run"):
    errors = []
    if manifest.get("schema") != 1:
        errors.append("schema must be 1")
    if manifest.get("dataset_id") != "reader-real-corpus-v1":
        errors.append("unexpected dataset_id")
    if manifest.get("target_per_format") != 2:
        errors.append("target_per_format must be 2")
    files = manifest.get("files") or []
    pending = manifest.get("pending") or []
    ids, paths, hashes = set(), set(), set()
    for entry in files:
        ident = entry.get("id", "")
        if not ident or ident in ids:
            errors.append("duplicate or empty id: %r" % ident)
        ids.add(ident)
        rel = entry.get("path", "")
        if not rel.startswith("assets/") or ".." in Path(rel).parts:
            errors.append("%s: path must stay under assets/" % ident)
        if rel in paths:
            errors.append("%s: duplicate path %s" % (ident, rel))
        paths.add(rel)
        if entry.get("kind") != "real":
            errors.append("%s: only kind=real counts in this dataset" % ident)
        if entry.get("format") not in FORMATS:
            errors.append("%s: unknown format" % ident)
        source = entry.get("source") or {}
        url = source.get("url", "")
        if not url.startswith("https://"):
            errors.append("%s: source URL must be HTTPS" % ident)
        size = source.get("bytes")
        if not isinstance(size, int) or size <= 0:
            errors.append("%s: bytes must be a positive integer" % ident)
        digest = source.get("sha256")
        if mode == "run" or mode == "collect":
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                errors.append("%s: sha256 must be pinned before execution" % ident)
        if isinstance(digest, str) and digest:
            if digest in hashes:
                errors.append("%s: duplicate sha256" % ident)
            hashes.add(digest)
        if not source.get("title") or not source.get("creator"):
            errors.append("%s: published title and creator are required" % ident)
        licence = source.get("license") or {}
        if licence.get("redistribution") is not True:
            errors.append("%s: redistribution must be explicitly true" % ident)
        for key in ("name", "url", "basis"):
            if not licence.get(key):
                errors.append("%s: licence.%s is required" % (ident, key))
        expect = entry.get("expect") or {}
        missing = [op for op in OPS if op not in expect]
        if missing:
            errors.append("%s: missing expectations: %s" % (ident, ", ".join(missing)))
        for op, value in expect.items():
            if op not in OPS:
                errors.append("%s: unknown expectation %s" % (ident, op))
            elif not isinstance(value, str):
                errors.append("%s: expectation %s must be a string" % (ident, op))
    for fmt in FORMATS:
        real = [e for e in files if e.get("format") == fmt]
        if len(real) < 2:
            errors.append("format %s has %d real files (minimum 2)" % (fmt, len(real)))
    if len(files) < 2 * len(FORMATS):
        errors.append("dataset has %d real files; minimum is %d" % (len(files), 2 * len(FORMATS)))
    for item in pending:
        if item.get("status") != "pending" or not item.get("reason"):
            errors.append("pending entries need status=pending and a reason")
    if errors:
        raise CorpusError("; ".join(errors))
    return True


def http_get(url, limit, timeout=90):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        final = response.geturl()
        chunks, total = [], 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise CorpusError("response exceeds %d bytes: %s" % (limit, url))
            chunks.append(chunk)
        return status, final, b"".join(chunks)


def download_manifest(manifest, root, mode, max_files=None):
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    records = []
    selected = manifest["files"][:max_files] if max_files else manifest["files"]
    for index, entry in enumerate(selected, 1):
        ident = entry["id"]
        source = entry["source"]
        target = root / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {"id": ident, "url": source["url"], "status": "failed"}
        started = time.time()
        try:
            declared = source.get("bytes")
            limit = (declared + 1) if isinstance(declared, int) and mode != "pin" else MAX_BYTES
            status, final, data = http_get(source["url"], limit)
            record.update({
                "http_status": status,
                "final_url": final,
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            })
            if mode != "pin":
                if len(data) != declared:
                    raise CorpusError("%s: byte count %d != pinned %d" % (ident, len(data), declared))
                if sha256_bytes(data) != source["sha256"]:
                    raise CorpusError("%s: SHA-256 does not match the pinned value" % ident)
            target.write_bytes(data)
            record["status"] = "ok" if mode == "pin" else "verified"
        except Exception as exc:  # keep collecting the rest of the corpus
            record["error"] = "%s: %s" % (type(exc).__name__, exc)
        record["seconds"] = round(time.time() - started, 3)
        records.append(record)
        print("[%d/%d] %s %s" % (index, len(selected), ident, record["status"]), flush=True)
        time.sleep(0.5)
    (root / ("pin.json" if mode == "pin" else "downloads.json")).write_text(
        json.dumps({"schema": 1, "mode": mode, "records": records}, indent=2) + "\n",
        encoding="utf-8")
    return records


def collect_license_evidence(manifest, root):
    entries = []
    seen = {}
    lic_dir = root / "licenses"
    lic_dir.mkdir(exist_ok=True)
    for entry in manifest["files"]:
        licence = entry["source"]["license"]
        url = licence["url"]
        if url in seen:
            continue
        record = {"url": url, "status": "failed"}
        try:
            status, final, data = http_get(url, MAX_LICENSE_BYTES)
            digest = sha256_bytes(data)
            name = digest + ".txt"
            (lic_dir / name).write_bytes(data)
            record.update({"http_status": status, "final_url": final, "sha256": digest,
                           "bytes": len(data), "path": "licenses/" + name, "status": "ok"})
        except Exception as exc:
            record["error"] = "%s: %s" % (type(exc).__name__, exc)
        seen[url] = record
        entries.append(record)
        time.sleep(0.5)
    (root / "license-evidence.json").write_text(
        json.dumps({"schema": 1, "entries": entries}, indent=2) + "\n", encoding="utf-8")
    return entries


def compare_expectations(expect, result):
    ops = (result or {}).get("ops") or {}
    mismatches = []
    for op, wanted in expect.items():
        actual = ops.get(op)
        if wanted == "report":
            if actual not in ("nonempty", "empty"):
                mismatches.append({"op": op, "expected": "report(nonempty|empty)", "actual": actual})
        elif actual != wanted:
            mismatches.append({"op": op, "expected": wanted, "actual": actual})
    return mismatches


def run_one(manifest_entry, root, consumer, font, timeout):
    ident = manifest_entry["id"]
    outdir = root / "results" / ident
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    source_path = root / manifest_entry["path"]
    command = [
        str(consumer), "--format", manifest_entry["format"], "--file", str(source_path),
        "--font", str(font), "--out", str(outdir), "--query", manifest_entry.get("query", ""),
    ]
    started = time.time()
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout, text=True,
                              encoding="utf-8", errors="replace")
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        code = "timeout"
    elapsed = round(time.time() - started, 3)
    result = None
    parse_error = None
    for line in reversed([l for l in stdout.splitlines() if l.strip()]):
        try:
            result = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if result is None:
        parse_error = "consumer produced no JSON result"
    record = {
        "id": ident, "format": manifest_entry["format"], "path": manifest_entry["path"],
        "command": command, "exit_code": code, "seconds": elapsed,
        "stdout": stdout[-200000:], "stderr": stderr[-200000:],
        "result": result, "parse_error": parse_error,
    }
    mismatches = compare_expectations(manifest_entry["expect"], result)
    readback = outdir / "readback.bin"
    readback_ok = readback.exists() and readback.stat().st_size == manifest_entry["source"]["bytes"] and \
        sha256_file(readback) == manifest_entry["source"]["sha256"]
    record["readback_verified"] = readback_ok
    record["mismatches"] = mismatches
    record["status"] = "accepted" if (code == 0 and result and not mismatches and readback_ok) else "failed"
    if not readback_ok:
        record.setdefault("errors", []).append("public original readback differs from the pinned source")
    if code != 0:
        record.setdefault("errors", []).append("consumer exit code %r" % (code,))
    if parse_error:
        record.setdefault("errors", []).append(parse_error)
    return record


def summarize(manifest, records, args):
    per_format = []
    failures = []
    format_counts = {}
    for fmt in FORMATS:
        entries = [r for r in records if r["format"] == fmt]
        accepted = [r for r in entries if r["status"] == "accepted"]
        failed = [r for r in entries if r["status"] != "accepted"]
        format_counts[fmt] = {
            "real": len(entries), "accepted": len(accepted), "failed": len(failed),
            "pending": len([p for p in manifest.get("pending", []) if p.get("format") == fmt]),
        }
        per_format.append({"format": fmt, **format_counts[fmt],
                           "files": [r["id"] for r in entries]})
        failures.extend({"id": r["id"], "format": fmt, "mismatches": r.get("mismatches", []),
                         "errors": r.get("errors", [])} for r in failed)
    pending = len(manifest.get("pending", []))
    accepted = (len(records) == len(manifest["files"]) and not failures and pending == 0 and
                all(v["real"] >= 2 and v["accepted"] >= 2 for v in format_counts.values()))
    sdk_versions = sorted({(r.get("result") or {}).get("program", {}).get("sdk_version")
                           for r in records if r.get("result")})
    abis = sorted({(r.get("result") or {}).get("program", {}).get("abi")
                   for r in records if r.get("result")})
    summary = {
        "schema": 1,
        "dataset_id": manifest["dataset_id"],
        "accepted": accepted,
        "source": {
            "commit": args.source_commit,
            "run_id": args.run_id,
            "attempt": args.attempt,
            "manifest_path": args.manifest,
            "manifest_sha256": sha256_file(args.manifest),
        },
        "platform": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": platform.python_version(),
        },
        "program": {
            "consumer_path": str(args.consumer),
            "consumer_sha256": sha256_file(args.consumer),
            "font_path": str(args.font), "font_sha256": sha256_file(args.font),
            "sdk_versions": sdk_versions, "abi_versions": abis,
        },
        "counts": {
            "real_files": len(records), "accepted": sum(1 for r in records if r["status"] == "accepted"),
            "failed": len(failures), "pending": pending, "formats": format_counts,
        },
        "per_format": per_format,
        "failures": failures,
        "unsupported": [
            {"format": "PDF", "capability": "authored navigation/TOC", "reason": "no public fixed-document navigation API"},
            {"format": "CBZ", "capability": "text and anchors", "reason": "image-only document property; load_text returns zero bytes"},
            {"format": "TXT", "capability": "document metadata title", "reason": "plain text has no title field"},
            {"format": "HTML/FB2/DOCX/RTF", "capability": "EPUB-style navigation resource", "reason": "format carries no authored navigation document"},
            {"format": "MOBI", "capability": "navigation", "reason": "reported per file; presence depends on the source NCX, not asserted"},
        ],
        "files": records,
    }
    return summary


def write_summary(summary, root):
    path = root / "summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def cmd_pin(args):
    manifest = load_manifest(args.manifest)
    validate_manifest(manifest, "pin")
    root = Path(args.out)
    records = download_manifest(manifest, root, "pin", args.max_files)
    bad = [r for r in records if r["status"] != "ok"]
    print(json.dumps({"records": len(records), "failed": len(bad)}, indent=2))
    return 1 if bad else 0


def cmd_collect(args):
    manifest = load_manifest(args.manifest)
    validate_manifest(manifest, "collect")
    root = Path(args.out)
    records = download_manifest(manifest, root, "collect", args.max_files)
    collect_license_evidence(manifest, root)
    bad = [r for r in records if r["status"] != "verified"]
    print(json.dumps({"records": len(records), "failed": len(bad)}, indent=2))
    return 1 if bad else 0


def cmd_run(args):
    manifest = load_manifest(args.manifest)
    validate_manifest(manifest, "run")
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    download_manifest(manifest, root, "collect", args.max_files)
    collect_license_evidence(manifest, root)
    records = []
    selected = manifest["files"][:args.max_files] if args.max_files else manifest["files"]
    for entry in selected:
        record = run_one(entry, root, Path(args.consumer), Path(args.font), args.timeout)
        records.append(record)
        print("[%s] %s %s" % (entry["format"], entry["id"], record["status"]), flush=True)
    summary = summarize(manifest, records, args)
    path = write_summary(summary, root)
    print(json.dumps({"summary": str(path), "accepted": summary["accepted"],
                      "counts": summary["counts"]}, indent=2, ensure_ascii=False))
    return 0 if summary["accepted"] else 1


def cmd_aggregate(args):
    summaries = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.summaries]
    if len(summaries) < 2:
        raise CorpusError("aggregate needs at least two platform summaries")
    manifest_shas = {s["source"]["manifest_sha256"] for s in summaries}
    commits = {s["source"]["commit"] for s in summaries}
    systems = sorted({s["platform"]["system"] for s in summaries})
    failures = []
    if len(manifest_shas) != 1:
        failures.append("platforms used different manifests")
    if len(commits) != 1 or None in commits:
        failures.append("platforms used different source commits")
    if not {"Windows", "Linux"}.issubset(set(systems)):
        failures.append("Windows and Linux summaries are both required")
    per_file = {}
    for summary in summaries:
        for record in summary["files"]:
            key = record["id"]
            per_file.setdefault(key, {})[summary["platform"]["system"]] = record["status"]
    for ident, states in sorted(per_file.items()):
        if set(states) != {"Windows", "Linux"} or any(v != "accepted" for v in states.values()):
            failures.append("file %s not accepted on both platforms: %r" % (ident, states))
    accepted = not failures and all(s["accepted"] for s in summaries)
    aggregate = {
        "schema": 1,
        "dataset_id": summaries[0]["dataset_id"],
        "accepted": accepted,
        "source": {"commit": summaries[0]["source"]["commit"],
                   "manifest_sha256": summaries[0]["source"]["manifest_sha256"],
                   "runs": [{"run_id": s["source"]["run_id"], "attempt": s["source"]["attempt"],
                             "system": s["platform"]["system"], "accepted": s["accepted"],
                             "counts": s["counts"]} for s in summaries]},
        "platforms": systems,
        "failures": failures,
        "counts": {"real_files": len(per_file), "accepted_files":
                   sum(1 for v in per_file.values() if set(v) == {"Windows", "Linux"} and
                       all(x == "accepted" for x in v.values()))},
    }
    Path(args.out).write_text(json.dumps(aggregate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2, ensure_ascii=False))
    return 0 if accepted else 1


def cmd_verify(args):
    manifest = load_manifest(args.manifest)
    validate_manifest(manifest, "run")
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    problems = []
    listed = {r["id"] for r in summary.get("files", [])}
    expected = {e["id"] for e in manifest["files"]}
    if listed != expected:
        problems.append("summary does not contain exactly the manifest files")
    counts = summary.get("counts", {}).get("formats", {})
    for fmt in FORMATS:
        value = counts.get(fmt, {})
        if value.get("real", 0) < 2:
            problems.append("%s: fewer than two real files" % fmt)
        if summary.get("accepted") and (value.get("accepted", 0) < 2 or value.get("failed", 0) or value.get("pending", 0)):
            problems.append("%s: accepted summary contradicts per-format counts" % fmt)
    if summary.get("accepted") and summary.get("failures"):
        problems.append("accepted summary contains failures")
    if summary.get("accepted") and summary.get("counts", {}).get("pending"):
        problems.append("accepted summary contains pending inputs")
    if problems:
        for problem in problems:
            print("VERIFY FAIL:", problem, file=sys.stderr)
        return 1
    print("verified %d real files; accepted=%s" % (len(listed), summary.get("accepted")))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    pin = sub.add_parser("pin")
    pin.add_argument("--manifest", default="tests/reader_real_corpus/manifest.json")
    pin.add_argument("--out", required=True)
    pin.add_argument("--max-files", type=int)
    pin.set_defaults(func=cmd_pin)

    collect = sub.add_parser("collect")
    collect.add_argument("--manifest", default="tests/reader_real_corpus/manifest.json")
    collect.add_argument("--out", required=True)
    collect.add_argument("--max-files", type=int)
    collect.set_defaults(func=cmd_collect)

    run = sub.add_parser("run")
    run.add_argument("--manifest", default="tests/reader_real_corpus/manifest.json")
    run.add_argument("--out", required=True)
    run.add_argument("--consumer", required=True)
    run.add_argument("--font", required=True)
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("--max-files", type=int)
    run.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", ""))
    run.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    run.add_argument("--attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    run.set_defaults(func=cmd_run)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--summaries", nargs="+", required=True)
    aggregate.add_argument("--out", required=True)
    aggregate.set_defaults(func=cmd_aggregate)

    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", default="tests/reader_real_corpus/manifest.json")
    verify.add_argument("--summary", required=True)
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    try:
        return args.func(args)
    except CorpusError as exc:
        print("CORPUS ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
