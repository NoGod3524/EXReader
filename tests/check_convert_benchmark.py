#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WP12-lite benchmark: new-process time, peak RSS, output volume and hashes.
Batch processing is item-at-a-time; no document queue is retained."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def run(tool, args, cwd):
    started = time.perf_counter()
    proc = subprocess.run([tool] + [str(a) for a in args], cwd=str(cwd),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError("tool failed (%d): %s" % (proc.returncode, proc.stderr.decode("utf-8", "replace")))
    return elapsed, json.loads(proc.stdout.decode("utf-8"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool")
    parser.add_argument("corpus")
    parser.add_argument("work")
    parser.add_argument("json")
    args = parser.parse_args()
    tool = str(Path(args.tool).resolve())
    corpus = Path(args.corpus)
    work = Path(args.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    themes = ["ascii", "chinese", "rtl", "supplementary", "special",
              "whitespace", "structure", "multichapter", "long", "metadata"]
    small = []
    for theme in themes:
        source = corpus / "text" / "txt" / (theme + ".txt")
        if not source.exists():
            raise RuntimeError("missing %s" % source)
        samples = []
        for repeat in range(3):
            output = work / ("small-%s-%d.epub" % (theme, repeat))
            elapsed, report = run(tool, ["--input", source, "--to", "epub", "--output", output], work)
            item = report["items"][0]
            samples.append({"elapsed_seconds": round(elapsed, 6),
                            "peak_rss_bytes": report["peak_rss_bytes"],
                            "output_bytes": item["output_bytes"]})
        small.append({"theme": theme, "input": str(source), "input_sha256": sha256(source),
                      "input_bytes": source.stat().st_size, "samples": samples})
    long_source = corpus / "long" / "one-mib.txt"
    long_samples = []
    for repeat in range(3):
        output = work / ("long-%d.epub" % repeat)
        elapsed, report = run(tool, ["--input", long_source, "--to", "epub", "--output", output], work)
        long_samples.append({"elapsed_seconds": round(elapsed, 6),
                             "peak_rss_bytes": report["peak_rss_bytes"],
                             "output_bytes": report["items"][0]["output_bytes"]})
    batch_dir = work / "batch-out"
    batch_dir.mkdir()
    items = []
    for i in range(100):
        items.append({"id": "b%03d" % i, "input": str(long_source), "to": "epub",
                      "output": "b%03d.epub" % i})
    manifest = work / "batch.json"
    manifest.write_text(json.dumps({"schema": 1, "output_root": "batch-out", "items": items},
                                   ensure_ascii=False), encoding="utf-8")
    elapsed, batch_report = run(tool, ["--batch", manifest], work)
    batch_peak = batch_report["peak_rss_bytes"]
    single_peak = max(s["peak_rss_bytes"] for s in long_samples)
    runtime = {}
    for name in ("libexreader.dll", "exreader.dll", "libexreader.so", "libexreader.dylib"):
        path = Path(tool).parent / name
        if path.exists():
            runtime[name] = {"path": str(path), "sha256": sha256(path)}
    evidence = {
        "schema": 1, "kind": "conversion-benchmark", "tool": tool,
        "tool_sha256": sha256(tool), "engine_version": batch_report["engine_version"],
        "runtime": runtime, "small": small, "one_mib": {
            "input": str(long_source), "input_sha256": sha256(long_source),
            "input_bytes": long_source.stat().st_size, "samples": long_samples},
        "batch_100": {
            "items": 100, "elapsed_seconds": round(elapsed, 6), "peak_rss_bytes": batch_peak,
            "output_bytes": sum(p.stat().st_size for p in batch_dir.glob("*.epub")),
            "single_peak_rss_bytes": single_peak,
            "peak_delta_bytes": batch_peak - single_peak,
            "queue_note": "manifest is loaded once; items are converted and released one at a time; no 100-document queue",
            "unfinished": batch_report["counts"]["unfinished"],
            "failed": batch_report["counts"]["failed"] + batch_report["counts"]["rejected"]},
        "temporary_files_remaining": len(list(work.rglob("*.tmp"))),
    }
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("small=%d one_mib_peak=%d batch_peak=%d outputs_batch=%d" %
          (len(small), single_peak, batch_peak, evidence["batch_100"]["output_bytes"]))
    if batch_report["counts"]["unfinished"] or evidence["batch_100"]["failed"]:
        return 1
    # A 100-item batch must not keep 100 documents resident. Allow the report
    # accumulator and allocator variance, not 100x document memory.
    if batch_peak > single_peak + 32 * 1024 * 1024:
        print("batch peak regression: %d > %d + 32 MiB" % (batch_peak, single_peak), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
