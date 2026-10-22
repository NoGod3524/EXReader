#!/usr/bin/env python3
"""Run the WP6 bounded-chapter probe over the fixed corpus and summarize it.

The summary keeps every raw record, the runtime/corpus hashes and the exact
command lines.  It never rewrites earlier measurements: the output directory
must be new. The snapshot plan retains its original rejection semantics.
--window-bytes selects the independent bounded reader and its measured gate.
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


def library_record_ok(record, source_bytes):
    report = record.get("report") or {}
    library = report.get("library") or {}
    pages = report.get("sequential", {}).get("page_hashes", [])
    required = ("imported", "progress_stored", "reopened", "resolved", "page_hash_equal", "tail_checked")
    return (record.get("exit") == 0 and report.get("status") == 0 and
            all(library.get(key) is True for key in required) and
            type(library.get("source_bytes")) is int and library["source_bytes"] == source_bytes and
            type(library.get("reference_page")) is int and library["reference_page"] == 0 and
            library.get("reopened_source_bytes") == source_bytes and
            bool(pages) and isinstance(library.get("reference_hash"), str) and
            library["reference_hash"] == library.get("reopened_hash") == pages[0].get("hash") and
            library.get("saved_chapter_offset") == library.get("resolved_offset") == pages[0].get("start") and
            library.get("resolved_state") == 1 and library.get("progress_present") is True and
            type(library.get("tail_bytes_checked")) is int and 0 < library["tail_bytes_checked"] <= 128)


def run_case(probe, font, book, out, stem, part, max_pages, turns, random, repeat,
             render=True, window_bytes=0, library=False):
    command = [str(probe), str(book), str(font), "--part", str(part),
               "--max-pages", str(max_pages), "--turns", str(turns),
               "--random", str(random), "--cache", "1", "--budget", str(2 * MIB),
               "--checkpoints", "4", "--checkpoint-budget", str(2 * MIB),
               "--checkpoint-interval", "8", "--seed", "20261020"]
    if render:
        command.append("--render")
    if window_bytes:
        command.extend(["--window-bytes",str(window_bytes)])
    name = "%s-%d" % (stem, repeat)
    if library:
        command.extend(["--library", str((out / (name + ".sqlite")).absolute())])
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
    parser.add_argument("--window-bytes",type=int,default=0)
    parser.add_argument("--sample-pages",type=int,default=256)
    parser.add_argument("--random-count",type=int,default=16)
    parser.add_argument("--library", action="store_true", help="use the library-enabled probe and verify persisted chapter positions")
    parser.add_argument("--enumerate", type=int, default=0,
                        help="page cap for one full sequential pass per loading case (0 = skip)")
    args = parser.parse_args(argv)
    if args.repeats<1 or args.window_bytes<0 or args.sample_pages<16 or not 1<=args.random_count<=64:
        parser.error("repeats must be positive; window bytes must be nonnegative")
    if args.library and not args.window_bytes:
        parser.error("library measurements require the bounded reader")
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
        if sha256(book)!=books[name]["sha256"]:
            parser.error("corpus hash mismatch: %s" % book)
        if args.window_bytes:
            max_pages,turns,random=args.sample_pages,16,args.random_count
        repeats = args.repeats if args.window_bytes or stem in ("single10", "segmented10") else 1
        runs = [run_case(args.probe, args.font, book, args.output, stem, part,
                         max_pages, turns, random, repeat,window_bytes=args.window_bytes,library=args.library) for repeat in range(repeats)]
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
        if args.library:
            case["library_roundtrip_pass"] = all(library_record_ok(r, books[name]["file_bytes"]) for r in runs)
            case["passed"] = case["passed"] and case["library_roundtrip_pass"]
            case["library_runs"] = [r["report"].get("library") if r["report"] else None for r in runs]
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
            if args.window_bytes:
                case["bounded_runs"]=[r["report"]["bounded"] for r in runs]
                case["medians"]["indexed_and_workspace_bytes"]=median(runs,lambda r:r["bounded"]["index_bytes"]+r["bounded"]["parse_workspace_bytes"])
                case["medians"]["peak_indexed_and_workspace_bytes"]=median(runs,lambda r:r["bounded"]["index_bytes"]+r["bounded"]["peak_parse_workspace_bytes"])
        if args.enumerate and case["passed"]:
            run = run_case(args.probe, args.font, book, args.output, stem + "-enumerate",
                           part, args.enumerate, 1, 0, 0, render=False,
                           window_bytes=max(args.window_bytes,2*MIB) if args.window_bytes else 0,library=args.library)
            report = run["report"]
            case["enumerated"] = {
                "passed": bool(report) and report.get("status") == 0 and
                          (not args.library or library_record_ok(run, books[name]["file_bytes"])),
                "pages": report["sequential"]["enumerated"] if report else None,
                "reached_eof": report["sequential"].get("reached_eof",False) if report else False,
                "all_pages_hash": report["sequential"].get("all_pages_hash") if report else None,
                "hashes": [entry["hash"] for entry in report["sequential"]["page_hashes"]]
                if report else [],
                "ranges": [[entry["start"], entry["end"]]
                           for entry in report["sequential"]["page_hashes"]] if report else [],
                "stdout": run["stdout"],
                "stdout_sha256": run["stdout_sha256"],
            }
            records.append(run)
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
        "runtime_dll_sha256":{p.name:sha256(p) for p in sorted(args.probe.parent.glob("*.dll"))},
        "runner_sha256":sha256(Path(__file__)),
        "window_bytes":args.window_bytes,
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
    if args.window_bytes:
        metric="peak_indexed_and_workspace_bytes"
        first=cases["single10"].get("medians",{}).get(metric)
        last=cases["single100"].get("medians",{}).get(metric)
        delta=last-first if first is not None and last is not None else None
        all_pass=all(c["passed"] for c in cases.values())
        random_ok=all_pass and all(r["report"]["random"]["mismatches"]==0 and
            r["report"]["random"]["restored_checkpoints"]>0 and
            r["report"]["bounded"]["windows_evicted"]>0 for r in records if "-enumerate" not in r["stem"])
        full_ok=not args.enumerate or all(c.get("enumerated",{}).get("reached_eof") for c in cases.values())
        deterministic=all_pass and all(len({tuple(p["hash"] for p in r["report"]["sequential"]["page_hashes"]) for r in records if r["stem"]==name})==1 for name in cases)
        accepted=all_pass and delta is not None and delta<=32*MIB and random_ok and full_ok and deterministic
        summary["acceptance"]={"single_10_to_100_peak_residency_increment_bytes":delta,"limit_bytes":32*MIB,
            "single_50_100_open":cases["single50"]["passed"] and cases["single100"]["passed"],
            "all_cases_pass":all_pass,"evicted_window_random_recovery":random_ok,
            "repeat_page_hashes_equal":deterministic,"requested_full_enumeration":bool(args.enumerate),
            "full_enumeration_pass":full_ok,"accepted":accepted}
    if args.library:
        summary["scope"] = "Stored EPUB bounded chapters, real eviction/random recovery, and persisted chapter-local positions"
        summary["acceptance"]["library_roundtrip_pass"] = all(c.get("library_roundtrip_pass", False) for c in cases.values())
        summary["acceptance"]["accepted"] = (summary["acceptance"]["accepted"] and
                                               summary["acceptance"]["library_roundtrip_pass"])
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if not args.window_bytes or summary["acceptance"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
