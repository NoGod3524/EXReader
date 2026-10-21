#!/usr/bin/env python3
"""Run the WP6 bounded-chapter probe over the fixed corpus and summarize it.

The summary keeps every raw record, the runtime/corpus hashes and the exact
command lines.  It never rewrites earlier measurements: the output directory
must be new.  acceptance is reported, not asserted, because the current engine
still rejects chapters above the 32 MiB member limit.
"""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from pathlib import Path

MIB = 1024 * 1024
PLANS = {
    "single10": ("single-10MiB.epub", 0, 64, 16, 8),
    "segmented10": ("segmented-10MiB.epub", 0, 64, 16, 8),
    "single50": ("single-50MiB.epub", 0, 16, 8, 4),
    "segmented50": ("segmented-50MiB.epub", 0, 32, 16, 8),
    "single100": ("single-100MiB.epub", 0, 16, 8, 4),
    "segmented100": ("segmented-100MiB.epub", 0, 32, 16, 8),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(probe, font, book, out, stem, part, max_pages, turns, random, repeat,
             render=True):
    command = [str(probe), str(book), str(font), "--part", str(part),
               "--max-pages", str(max_pages), "--turns", str(turns),
               "--random", str(random), "--cache", "1", "--budget", str(2 * MIB),
               "--checkpoints", "4", "--checkpoint-budget", str(2 * MIB),
               "--checkpoint-interval", "8", "--seed", "20261020"]
    if render:
        command.append("--render")
    name = "%s-%d" % (stem, repeat)
    stdout_path = out / (name + ".json")
    stderr_path = out / (name + ".stderr.log")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1800)
    text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        report = json.loads(text)
    except ValueError:
        report = None
    return {"stem": stem, "repeat": repeat, "command": command,
            "exit": completed.returncode, "stdout": stdout_path.name,
            "stderr": stderr_path.name, "report": report,
            "stdout_sha256": sha256(stdout_path), "stderr_sha256": sha256(stderr_path)}


def median(records, getter):
    values = [getter(record["report"]) for record in records
              if record["report"] and record["report"].get("status") == 0]
    return statistics.median(values) if values else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", type=Path, help="exreader-wp6-chapter-probe")
    parser.add_argument("font", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--enumerate", type=int, default=0,
                        help="page cap for one full sequential pass per loading case (0 = skip)")
    args = parser.parse_args(argv)
    for path in (args.probe, args.font, args.corpus / "manifest.json"):
        if not path.is_file():
            parser.error("missing input: %s" % path)
    if args.output.exists():
        parser.error("Choose a new output directory to preserve earlier measurements")
    args.output.mkdir(parents=True)
    corpus = json.loads((args.corpus / "manifest.json").read_text(encoding="utf-8"))
    books = {case["name"]: case for case in corpus["cases"]}
    records, cases = [], {}
    for stem, (name, part, max_pages, turns, random) in PLANS.items():
        book = args.corpus / name
        if not book.is_file():
            parser.error("missing corpus member: %s" % book)
        repeats = args.repeats if stem in ("single10", "segmented10") else 1
        runs = [run_case(args.probe, args.font, book, args.output, stem, part,
                         max_pages, turns, random, repeat) for repeat in range(repeats)]
        records.extend(runs)
        good = [r for r in runs if r["report"] and r["report"].get("status") == 0]
        case = {
            "book": name,
            "book_sha256": books[name]["sha256"],
            "chapter_count": books[name]["chapter_count"],
            "body_bytes": books[name]["body_bytes"],
            "part": part,
            "runs": [r["stdout"] for r in runs],
            "exits": [r["exit"] for r in runs],
            "statuses": [r["report"]["status"] if r["report"] else None for r in runs],
            "stages": [r["report"]["stage"] if r["report"] else None for r in runs],
            "errors": [r["report"]["error"] if r["report"] else None for r in runs],
            "passed": len(good) == len(runs),
        }
        if good:
            case["medians"] = {
                "text_bytes": median(runs, lambda r: r["text_bytes"]),
                "nodes": median(runs, lambda r: r["nodes"]),
                "document_owned_bytes": median(runs, lambda r: r["parse_workspace"]["document_owned_bytes"]),
                "projection_bytes": median(runs, lambda r: r["parse_workspace"]["projection_bytes"]),
                "node_array_bytes": median(runs, lambda r: r["parse_workspace"]["node_array_bytes"]),
                "other_bytes": median(runs, lambda r: r["parse_workspace"]["other_bytes"]),
                "chapter_load_ms": median(runs, lambda r: r["timing"]["chapter_load_ms"]),
                "first_page_layout_ms": median(runs, lambda r: r["timing"]["first_page_layout_ms"]),
                "first_paint_ms": median(runs, lambda r: r["timing"]["first_paint_ms"]),
                "first_visible_total_ms": median(runs, lambda r: r["timing"]["first_visible_total_ms"]),
                "enumerated_pages": median(runs, lambda r: r["sequential"]["enumerated"]),
                "random_mismatches": median(runs, lambda r: r["random"]["mismatches"]),
                "restored_checkpoints": median(runs, lambda r: r["random"]["restored_checkpoints"]),
                "page_cache_bytes": median(runs, lambda r: r["random"]["cache_bytes"]),
                "working_set_growth_bytes": median(
                    runs, lambda r: r["memory"]["load_resident_bytes"] - r["memory"]["font_resident_bytes"]),
                "peak_rss_bytes": median(runs, lambda r: r["memory"]["peak_rss_bytes"]),
            }
            case["turn_layout_ms"] = good[0]["report"]["sequential"]["turn_layout_ms"]
            case["turn_render_ms"] = good[0]["report"]["sequential"]["turn_render_ms"]
            case["page_hashes"] = [entry["hash"] for entry in good[0]["report"]["sequential"]["page_hashes"]]
            case["page_ranges"] = [[entry["start"], entry["end"]]
                                   for entry in good[0]["report"]["sequential"]["page_hashes"]]
        if args.enumerate and case["passed"]:
            run = run_case(args.probe, args.font, book, args.output, stem + "-enumerate",
                           part, args.enumerate, 1, 0, 0, render=False)
            report = run["report"]
            case["enumerated"] = {
                "passed": bool(report) and report.get("status") == 0,
                "pages": report["sequential"]["enumerated"] if report else None,
                "hashes": [entry["hash"] for entry in report["sequential"]["page_hashes"]]
                if report else [],
                "ranges": [[entry["start"], entry["end"]]
                           for entry in report["sequential"]["page_hashes"]] if report else [],
                "stdout": run["stdout"],
                "stdout_sha256": run["stdout_sha256"],
            }
            bad = [r for r in runs + [run] if not r["report"]]
            if bad:
                parser.error("unparseable probe output: %s" % bad[0]["stdout"])
        cases[stem] = case
        print("%-13s status=%s stage=%s owned=%s %s" % (
            stem, case["statuses"], case["stages"],
            case.get("medians", {}).get("document_owned_bytes"),
            case["errors"][0] or ""))
    summary = {
        "schema": 1,
        "date": "2026-10-20",
        "scope": "WP6 bounded chapter probe; chapter load, first screen, sequential and fixed random plans",
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "probe_sha256": sha256(args.probe),
        "font_sha256": sha256(args.font),
        "corpus_manifest_sha256": sha256(args.corpus / "manifest.json"),
        "corpus_generator_sha256": corpus["generator_sha256"],
        "peak_metric": "OS process high-water and live working set; the deterministic parse workspace is document_owned_bytes",
        "random_plan": "seed 20261020, one-page cache, 4 checkpoints / 2 MiB every 8 pages, hash compared with the sequential pass",
        "cases": cases,
        "records": [{k: v for k, v in record.items() if k != "report"} for record in records],
        "acceptance": {},
    }
    median_10 = cases["single10"].get("medians", {}).get("document_owned_bytes")
    median_100 = cases["single100"].get("medians", {}).get("document_owned_bytes")
    summary["acceptance"] = {
        "single_10_to_100_residency_increment_bytes": (median_100 - median_10) if median_10 and median_100 else None,
        "limit_bytes": 32 * MIB,
        "single_50_100_open": cases["single50"]["passed"] and cases["single100"]["passed"],
        "segmented_sequential_and_random": all(
            cases[name].get("medians", {}).get("random_mismatches") == 0
            for name in ("segmented10", "segmented50", "segmented100") if cases[name]["passed"]),
        "accepted": False,
        "reason": "10->100 MiB single-chapter residency and open are still unmet; see cases and docs",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())