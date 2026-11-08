#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Measure manager time (includes cache I/O, excludes process launch and setup).

python tests/benchmark_font_manager.py <probe> <fixtures> <work-dir>
Optionally use --fonts <path> ... to benchmark copies of real fonts.
"""
import argparse
import json
from pathlib import Path
import shutil
import statistics
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("probe", type=Path)
p.add_argument("fixtures", type=Path)
p.add_argument("work", type=Path)
p.add_argument("--fonts", type=Path, nargs="+")
p.add_argument("--hardlinks", action="store_true", help="reuse font bytes via local hard links")
args = p.parse_args()
args.work.mkdir(parents=True, exist_ok=False)
directory = args.work / "fonts"
directory.mkdir()
sources = args.fonts or [args.fixtures / name for name in
                        ("latin-serif.ttf", "cjk-serif.ttf", "cjk-sans.ttf")]
for i in range(500):
    source = sources[i % len(sources)]
    target = directory / f"font-{i:03}{source.suffix}"
    if args.hardlinks:
        target.hardlink_to(source.resolve())
    else:
        shutil.copyfile(source, target)
cache = args.work / "index.cache"
config = args.work / "fonts.conf"
config.write_text("version = 1\nfont_dir = fonts\ncache = index.cache\n", encoding="utf-8")
runs = []
for i in range(5):
    cache.unlink(missing_ok=True)
    pair = {}
    for label in ("cold", "hot"):
        result = subprocess.run([str(args.probe.resolve()), str(config.resolve())],
                                check=True, capture_output=True, encoding="utf-8")
        pair[label] = json.loads(result.stdout)
        assert pair[label]["files"] == 500
        assert pair[label]["parsed"] == (500 if label == "cold" else 0)
        assert pair[label]["cached"] == (0 if label == "cold" else 500)
    runs.append(pair)
result = {"files": 500, "bytes": sum(f.stat().st_size for f in directory.iterdir()),
          "hardlinks": args.hardlinks,
          "sources": [str(s.resolve()) for s in sources], "runs": runs,
          "median_ms": {label: statistics.median(r[label]["ms"] for r in runs)
                        for label in ("cold", "hot")},
          "max_ms": {label: max(r[label]["ms"] for r in runs) for label in ("cold", "hot")}}
print(json.dumps(result, ensure_ascii=False, indent=2))
(args.work / "benchmark.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
assert result["max_ms"]["cold"] <= 1500
assert result["max_ms"]["hot"] <= 150
