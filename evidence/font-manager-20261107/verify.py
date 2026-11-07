#!/usr/bin/env python3
"""Recheck saved acceptance outputs and record this local build's provenance.

python evidence/font-manager-20261107/verify.py <build> <book> <acceptance-work>
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

here = Path(__file__).resolve().parent
root = here.parent.parent
build, book, work = map(Path, sys.argv[1:])


def save(name, data):
    (here / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def records(name):
    return [json.loads(s) for s in (here / name).read_text(encoding="utf-8-sig").splitlines()]


before, after = records("BASELINE-book.jsonl"), records("SERIF-book.jsonl")
a = {r["part"]: r for r in before if r["kind"] == "first_line"}
b = {r["part"]: r for r in after if r["kind"] == "first_line"}
keys = ("start", "end", "codepoints")
same = lambda part: all(a[part][k] == b[part][k] for k in keys)
assert same(15)
assert before[-1]["kind"] == after[-1]["kind"] == "book"
assert before[-1]["missing"] == after[-1]["missing"] == 0
assert before[-1]["parts"] == after[-1]["parts"] == 31
save("BOOK-COMPARISON.json", {
    "reference_part": 15, "reference_page": 0, "first_line_text_and_range_identical": same(15),
    "before_first_line": a[15], "after_first_line": b[15],
    "before_book": before[-1], "after_book": after[-1],
    "chapter_first_lines_identical": [i for i in a if same(i)],
    "chapter_first_lines_different": [i for i in a if not same(i)],
    "note": "Font metrics differ: unchanged layout settings do not imply identical pagination or line height."
})
benchmark = json.loads((here / "BENCHMARK.json").read_text(encoding="utf-8"))
assert benchmark["files"] == 500
assert benchmark["max_ms"]["cold"] <= 1500 and benchmark["max_ms"]["hot"] <= 150
for run in benchmark["runs"]:
    assert run["cold"]["parsed"] == run["hot"]["cached"] == 500
    assert run["cold"]["cached"] == run["hot"]["parsed"] == 0
assert "100% tests passed out of 173" in (here / "CTEST.log").read_text(encoding="utf-8-sig")
assert (here / "MISSING-exit.txt").read_text(encoding="utf-8-sig").strip() == "1"
assert "Font directory not found:" in (here / "MISSING-error.txt").read_text(encoding="utf-8-sig")
sources = [root / p for p in ("src/font_manager.c", "src/font_scan.c", "src/font_cache.c",
                              "src/font_manager_internal.h", "include/exr/font_manager.h")]
reuse = []
for path in sources:
    old = (root / "build/font-manager-original" / path.name).read_text(encoding="utf-8").splitlines()
    new = path.read_text(encoding="utf-8").splitlines()
    reuse.append({"file": str(path.relative_to(root)), "original": len(old), "final": len(new),
                  "unchanged": sum(m.size for m in difflib.SequenceMatcher(None, old, new).get_matching_blocks())})
save("REUSE.json", {"files": reuse, "reused_fraction_of_final": sum(r["unchanged"] for r in reuse) / sum(r["final"] for r in reuse)})
inputs = [book, *sorted((work / "sources").iterdir()), build / "libexreader.dll", build / "exreader-font-manager-probe.exe"]
inputs += sources + [root / p for p in ("tests/test_font_manager.c", "tests/check_font_manager.py", "tests/font_manager_probe.c", "tests/benchmark_font_manager.py")]
cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
save("PROVENANCE.json", {
    "base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "os": platform.platform(), "cpu": os.environ.get("PROCESSOR_IDENTIFIER"), "logical_cpus": os.cpu_count(),
    "compiler": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0],
    "build": str(build.resolve()), "work": str(work.resolve()),
    "cmake_options": [s for s in cache.splitlines() if s.startswith(("EXR_", "CMAKE_BUILD_TYPE:", "CMAKE_C_COMPILER:", "FETCHCONTENT_SOURCE_DIR_"))],
    "inputs": [{"path": str(p.resolve()), "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
})
print("173 tests, 500-file timing, missing-directory failure and reference first line verified")
