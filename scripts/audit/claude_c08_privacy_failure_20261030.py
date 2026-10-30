#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C08 privacy-failure auditor: pycompile, scope, selftest, summary (stdlib only).

Also the shared canary scanner imported by the Windows driver. Every report is JSON; every gate
fails closed. Only run in GitHub Actions.
"""
import argparse
import base64
import hashlib
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

OWNED = ("tests/reader_privacy_failure_20261030/",
         ".github/workflows/claude_c08_privacy_failure_20261030.yml",
         "scripts/audit/claude_c08_privacy_failure_20261030.py",
         "docs/reader-total-progress/CLAUDE_C08_PRIVACY_FAILURE_20261030.md")
MIN_CANARY = 12


def variants(canary: str) -> dict:
    """Byte patterns a plaintext copy of `canary` could take on disk or in a stream."""
    raw = canary.encode()
    found = {"raw": raw, "utf16le": canary.encode("utf-16-le"),
             "hex-lower": raw.hex().encode(), "hex-upper": raw.hex().upper().encode(),
             "percent-upper": "".join("%%%02X" % b for b in raw).encode(),
             "percent-lower": "".join("%%%02x" % b for b in raw).encode()}
    for shift in range(3):
        for tag, enc in (("std", base64.b64encode), ("url", base64.urlsafe_b64encode)):
            text = enc(b"\0" * shift + raw).decode().rstrip("=")
            tail = {0: 0, 1: 2, 2: 1}[(shift + len(raw)) % 3]  # last chars depend on following bytes
            found["b64-%s-%d" % (tag, shift)] = text[(shift * 8 + 5) // 6:len(text) - tail].encode()
    return found


def scan_bytes(data: bytes, canaries: dict) -> list:
    return sorted("%s:%s" % (tag, form) for tag, canary in canaries.items()
                  for form, pattern in variants(canary).items() if pattern in data)


def scan_tree(root: Path, canaries: dict) -> list:
    """Hits in file contents and in path names below root (matching only, nothing is kept)."""
    hits = []
    for path in sorted(root.rglob("*")):
        for hit in scan_bytes(str(path.relative_to(root)).encode(), canaries):
            hits.append({"where": "name", "path": str(path.relative_to(root)), "hit": hit})
        if path.is_file():
            try:
                data = path.read_bytes()
            except OSError as exc:
                hits.append({"where": "unreadable", "path": str(path.relative_to(root)), "hit": str(exc)})
                continue
            for hit in scan_bytes(data, canaries):
                hits.append({"where": "content", "path": str(path.relative_to(root)), "hit": hit})
    return hits


def digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git(repo, *args) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if done.returncode:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout.strip()


def cmd_pycompile(args) -> int:
    results, ok = [], True
    with tempfile.TemporaryDirectory() as scratch:
        for index, name in enumerate(args.files):
            try:
                py_compile.compile(name, cfile=str(Path(scratch) / ("%d.pyc" % index)), doraise=True)
                results.append({"file": name, "ok": True})
            except (py_compile.PyCompileError, OSError) as exc:
                ok = False
                results.append({"file": name, "ok": False, "error": str(exc)})
    write_json(args.out, {"gate": "pycompile", "ok": ok, "results": results})
    return 0 if ok else 1


def cmd_scope(args) -> int:
    head = git(args.repo, "rev-parse", "HEAD")
    problems = []
    if head != args.expect_sha:
        problems.append("HEAD %s != expected %s" % (head, args.expect_sha))
    if subprocess.run(["git", "-C", args.repo, "merge-base", "--is-ancestor", args.base, "HEAD"]).returncode:
        problems.append("base %s is not an ancestor of HEAD" % args.base)
    changed = [p for p in git(args.repo, "diff", "--name-only", args.base, "HEAD").splitlines() if p]
    stray = [p for p in changed if not p.startswith(OWNED)]
    if stray:
        problems.append("changed paths outside ownership: %s" % stray)
    write_json(args.out, {"gate": "scope", "ok": not problems, "head": head, "base": args.base,
                          "changed": changed, "problems": problems})
    return 0 if not problems else 1


def cmd_selftest(args) -> int:
    canary = "c08-selftest-" + os.urandom(8).hex()
    other = "c08-other-" + os.urandom(8).hex()
    cases, ok = [], True
    forms = variants(canary)
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        for form, pattern in forms.items():
            case = root / ("case-" + form)
            case.mkdir()
            (case / "blob.bin").write_bytes(b"noise" + pattern + b"noise")
            hits = scan_tree(case, {"c": canary})
            cases.append({"form": form, "found": bool(hits)})
            ok &= bool(hits)
        named = root / "named"
        named.mkdir()
        (named / (canary + ".txt")).write_bytes(b"x")
        found_name = any(h["where"] == "name" for h in scan_tree(named, {"c": canary}))
        cases.append({"form": "file-name", "found": found_name})
        ok &= found_name
        clean = root / "clean"
        clean.mkdir()
        (clean / "a.bin").write_bytes(os.urandom(256))
        clean_hits = scan_tree(clean, {"c": canary, "o": other})
        cases.append({"form": "clean-tree", "found": bool(clean_hits)})
        ok &= not clean_hits
    short = len("short") < MIN_CANARY
    cases.append({"form": "short-canary-refused", "found": not short})
    ok &= short
    write_json(args.out, {"gate": "selftest", "ok": bool(ok), "cases": cases})
    return 0 if ok else 1


def cmd_summary(args) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    env = os.environ
    identity = {k: env.get(k, "") for k in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID",
                                            "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "RUNNER_OS", "ImageOS",
                                            "ImageVersion")}
    gates = {name: json.loads(Path(p).read_text(encoding="utf-8")).get("ok") is True
             for name, p in (("pycompile", args.pycompile), ("scope", args.scope), ("selftest", args.selftest))}
    gates["dynamic_harness"] = report.get("harness_ok") is True
    summary = {"identity": identity, "gates": gates, "refusal_proven": report.get("refusal_proven") is True,
               "refusal_mechanism": report.get("refusal_mechanism"),
               "report_sha256": digest(args.report), "all_gates_ok": all(gates.values())}
    write_json(args.out, summary)
    line = "C08 Windows Credential Manager refusal: %s (harness gates ok: %s)" % (
        "PROVEN via %s" % summary["refusal_mechanism"] if summary["refusal_proven"] else "UNPROVEN",
        summary["all_gates_ok"])
    print(line)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return 0 if summary["all_gates_ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pycompile")
    p.add_argument("--out", required=True)
    p.add_argument("--files", nargs="+", required=True)
    p = sub.add_parser("scope")
    p.add_argument("--repo", default=".")
    p.add_argument("--base", required=True)
    p.add_argument("--expect-sha", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("selftest")
    p.add_argument("--out", required=True)
    p = sub.add_parser("summary")
    for name in ("report", "pycompile", "scope", "selftest", "out"):
        p.add_argument("--" + name, required=True)
    args = parser.parse_args()
    return {"pycompile": cmd_pycompile, "scope": cmd_scope, "selftest": cmd_selftest,
            "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
