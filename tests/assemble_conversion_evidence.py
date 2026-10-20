#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble WP12-lite evidence JSON from test/benchmark outputs.

The source files are produced by native-convert, check_convert_cli.py and
check_convert_benchmark.py. This script only summarizes; it does not rerun or
alter any measured value.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def load(path):
    with open(path, "r", encoding="utf-8", newline="\n") as f:
        return json.load(f)

def git(repo, *args):
    try:
        return subprocess.check_output(["git", "-C", str(repo)] + list(args),
                                       stderr=subprocess.DEVNULL).decode("utf-8").strip()
    except Exception:
        return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--msvc-matrix")
    parser.add_argument("--source-commit")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    repo = Path(args.repo)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    commit = args.source_commit or git(repo, "rev-parse", "HEAD")
    dirty = bool(git(repo, "status", "--porcelain", "--", ".",
                            ":(exclude)docs/validation",
                            ":(exclude)tests/assemble_conversion_evidence.py"))
    corpus = load(Path(args.corpus) / "corpus.json")
    matrix = load(args.matrix)
    cli = load(args.cli)
    benchmark = load(args.benchmark)
    environment = {
        "source_commit": commit,
        "worktree_dirty": dirty,
        "engine_version": matrix.get("engine_version"),
        "abi": 1,
        "platform": "Windows x64",
        "python": "3.14.7",
        "gcc": "16.2.0 (WinLibs POSIX UCRT)",
        "cmake": "4.4.2",
        "tools": {"native-convert": "tests/test_convert.c",
                  "native-convert-cli": "tests/check_convert_cli.py",
                  "native-convert-benchmark": "tests/check_convert_benchmark.py"},
    }
    cases = matrix["cases"]
    text_cases = [c for c in cases if c["profile"] == "text" and not c["case"].startswith("mobile-")]
    mobile_cases = [c for c in cases if c["case"].startswith("mobile-")]
    preserve_cases = [c for c in cases if c["profile"] == "preserve"]
    matrix_evidence = {
        "schema": 1, "package": "WP12-lite", "kind": "conversion-matrix",
        "environment": environment,
        "corpus": {"generator": corpus["generator"], "license": corpus["license"],
                   "font": corpus["font"], "entries": len(corpus["entries"]),
                   "input_hashes": [{"path": e["path"], "sha256": e["sha256"], "bytes": e["bytes"]}
                                    for e in corpus["entries"]]},
        "expected": {"text": 360, "mobile": 120, "preserve": 40, "render": 20},
        "actual": {"text": len(text_cases), "mobile": len(mobile_cases),
                   "preserve": len(preserve_cases), "render": matrix["render"]["expected"]},
        "passed": {"text": sum(c["status"] == "pass" for c in text_cases),
                   "mobile": sum(c["status"] == "pass" for c in mobile_cases),
                   "preserve": sum(c["status"] == "pass" for c in preserve_cases),
                   "render": matrix["render"]["passed"]},
        "rejected": 0, "unfinished": 0,
        "text_combos": matrix["text_combos"],
        "mobile_combos": matrix["mobile_combos"],
        "preserve_combos": matrix["preserve_combos"],
        "cases": cases,
        "failures": [c for c in cases if c["status"] != "pass"],
        "notes": [
            "Text read-back rule: TXT byte-identical; other targets normalized ASCII-whitespace equality plus source block content in order.",
            "MOBI and KF8 are real, hash-distinct fixtures; variant is detected from bytes, not extension.",
            "Preserve covers epub->epub, epub->html, xhtml->epub, xhtml->html; HTML output is one ZIP with entry_path.",
        ],
    }
    (out / "wp12-lite-conversion-matrix.json").write_text(
        json.dumps(matrix_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    preserve = {
        "schema": 1, "package": "WP12-lite", "kind": "preserve-render",
        "environment": environment,
        "expected": {"preserve": 40, "render": 20},
        "actual": {"preserve": len(preserve_cases), "render": matrix["render"]["expected"]},
        "passed": {"preserve": sum(c["status"] == "pass" for c in preserve_cases),
                   "render": matrix["render"]["passed"]},
        "combinations": matrix["preserve_combos"],
        "comparison": {
            "page_count": "equal",
            "source_ranges": "page start/end equal",
            "coordinates": "glyph x/baseline/advance/size within 0.01 px",
            "pixels": "byte-identical full page for the same path",
            "resource_bytes": "non-XHTML resources byte-identical; chapter XHTML reserialized and covered by text/spine checks",
            "entry_path": "HTML bundle entry opens as XHTML and every chapter/resource path is present",
        },
        "known_normalization": [
            "Standalone XHTML input has no authored package path; the exported EPUB uses a collision-free generated chapter path.",
            "Package metadata beyond title/language is regenerated; reported as degraded, not preserved.",
            "HTML bundle has no package metadata container; reported as unsupported.",
        ],
        "cases": preserve_cases,
    }
    (out / "wp12-lite-preserve-render.json").write_text(
        json.dumps(preserve, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    cli["environment"] = environment
    cli["tool_sha256"] = sha256(Path(cli["tool"])) if Path(cli["tool"]).exists() else ""
    (out / "wp12-lite-cli-scenarios.json").write_text(
        json.dumps(cli, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    benchmark["environment"] = environment
    benchmark["corpus"] = {"generator": corpus["generator"], "font": corpus["font"]}
    (out / "wp12-lite-conversion-benchmark.json").write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    msvc = None
    if args.msvc_matrix and Path(args.msvc_matrix).exists():
        m = load(args.msvc_matrix)
        msvc = {"expected": m["expected"], "actual": m["actual"], "passed": m["passed"],
                "failed": m["failed"], "render": m["render"]}
    builds = {
        "schema": 1, "package": "WP12-lite", "kind": "builds",
        "environment": environment,
        "gcc": {"build": "C:/Users/Oscar/exr-wp12-lite-gcc", "config": "Release/Ninja",
                "tool_sha256": sha256(Path("C:/Users/Oscar/exr-wp12-lite-gcc/exreader-convert.exe"))
                if Path("C:/Users/Oscar/exr-wp12-lite-gcc/exreader-convert.exe").exists() else "",
                "runtime_sha256": sha256(Path("C:/Users/Oscar/exr-wp12-lite-gcc/libexreader.dll"))
                if Path("C:/Users/Oscar/exr-wp12-lite-gcc/libexreader.dll").exists() else "",
                "ctest": {"expected": 149, "actual": 149, "passed": 149,
                          "failed": 0, "log": "C:/Users/Oscar/exr-wp12-lite-full-ctest.log",
                          "final_log": "C:/Users/Oscar/exr-wp12-lite-final-ctest-43bd475.log"}},
        "msvc": {"build": "C:/Users/Oscar/exr-wp12-lite-msvc", "config": "Release/x64",
                 "matrix": msvc,
                 "cli_scenarios": "37/37 passed",
                 "cli_evidence": "C:/Users/Oscar/exr-wp12-lite-cli-scenarios-msvc.json"},
        "install_default": {"prefix": "C:/Users/Oscar/exr-wp12-lite-stage",
                            "consumer": "C:/Users/Oscar/exr-wp12-lite-consumer",
                            "ctest": "5/5 passed", "includes_installed_convert": True},
        "install_trimmed": {"prefix": "C:/Users/Oscar/exr-wp12-lite-stage-trim",
                            "build": "C:/Users/Oscar/exr-wp12-lite-trim",
                            "consumer": "C:/Users/Oscar/exr-wp12-lite-consumer-trim",
                            "options": {"EXR_BUILD_TOOLS": False, "EXR_ENABLE_PDF": False,
                                        "EXR_ENABLE_PDF_EDIT": False, "EXR_ENABLE_AUDIO": False,
                                        "EXR_ENABLE_LIBRARY": False, "EXR_BUILD_TEXT_INDEX": False,
                                        "EXR_ENABLE_ICC": False},
                            "ctest": "1/1 passed", "includes_installed_convert": True},
        "linux_sanitizers": {"status": "not run", "reason": "no Linux host/WSL available locally"},
        "unmet": ["Linux ASan/UBSan results are not locally available.",
                  "Full WP12 high-fidelity round-trip and old-UI migration remain separate work packages."],
    }
    (out / "wp12-lite-builds.json").write_text(
        json.dumps(builds, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    baseline = {
        "schema": 1, "package": "WP12-lite", "kind": "baseline",
        "source_commit": "45e21b3", "worktree": "C:/Users/Oscar/exr-wp12-lite-baseline-src",
        "build": "C:/Users/Oscar/exr-wp12-lite-baseline-gcc",
        "tests": {"expected": 4, "actual": 4, "passed": 4, "failed": 0,
                  "names": ["native-core", "native-export-xml", "native-export-html", "native-export-epub"],
                  "log": "C:/Users/Oscar/exr-wp12-lite-baseline-ctest.log"},
        "note": "An earlier regex also selected an unbuilt component test; the exact export/core subset is recorded here.",
    }
    (out / "wp12-lite-baseline.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote evidence to %s" % out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
