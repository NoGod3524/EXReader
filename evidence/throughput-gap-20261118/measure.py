# SPDX-License-Identifier: MIT
"""Capture or summarize the three 1200 px cells with the #257 harness."""
import argparse
import gzip
import json
import math
import os
import platform
from datetime import datetime
from pathlib import Path
from statistics import mean, median
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from bench_large_vs_pdfjs import run_pdfjs_gated
from bench_real_doc import digest_file, run_child_gated

CASES = {
    "real-mixed-120": (120, "image-paint", "shading"),
    "image-heavy-100": (100, "image-paint", "image-decode"),
    "vector-heavy-100": (100, "path", "shading"),
}
WIDTH, ROUNDS, REPEATS = 1200, 5, 3
RAW = HERE / "timings.json.gz"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def capture(library, pdfjs):
    version = load(pdfjs / "node_modules/pdfjs-dist/package.json")["version"]
    if version != "3.11.174":
        raise ValueError(f"Expected PDF.js 3.11.174, got {version}")
    for key in list(os.environ):
        if key.startswith(("EXR_ATTRIBUTION_", "EXR_PDF_")) or key == "EXR_BUFFER_POOL":
            os.environ.pop(key)
    data = {
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dll_sha256": digest_file(library),
        "pdfjs": version,
        "canvas": load(pdfjs / "node_modules/canvas/package.json")["version"],
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "started": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cases": {},
    }
    with tempfile.TemporaryDirectory() as temp:
        child = Path(temp) / "child.json"
        for name, (count, *modes) in CASES.items():
            pdf = ROOT / "tests/fixtures/pdf-large" / f"{name}.pdf"
            case = data["cases"][name] = {"sha256": digest_file(pdf), "repeats": []}
            for repeat in range(REPEATS):
                order = ["full", "pdfjs", *modes]
                if repeat % 2:
                    order.reverse()
                result = {}
                for mode in order:
                    if mode == "pdfjs":
                        row = run_pdfjs_gated(pdfjs, pdf, count, WIDTH, ROUNDS, child, 15, 120)
                    else:
                        os.environ["EXR_ATTRIBUTION_SKIP"] = "" if mode == "full" else mode
                        row = run_child_gated(library, pdf, count, WIDTH, ROUNDS, child, 15, 120)
                    times = [page["render_ms"] for page in row["pages"]]
                    if (row["width"], row["page_count"], row["runs"]) != (WIDTH, count, ROUNDS):
                        raise ValueError(f"Wrong capture shape for {name} {mode}")
                    if [p["page"] for p in row["pages"]] != list(range(1, count + 1)):
                        raise ValueError(f"Wrong page sequence for {name} {mode}")
                    if any(len(page) != ROUNDS or any(not math.isfinite(t) or t <= 0 for t in page)
                           for page in times) or not 0 <= row["pre_cpu_percent"] <= 15:
                        raise ValueError(f"Invalid timings or idle gate for {name} {mode}")
                    if abs(median(map(sum, zip(*times))) - row["round_wall_ms_p50"]) > 0.001:
                        raise ValueError(f"Throughput denominator mismatch for {name} {mode}")
                    result[mode] = {
                        "pre_cpu": row["pre_cpu_percent"], "capture_cpu": row["capture_cpu_percent"],
                        "page_ms": times,
                    }
                    print(f"{name} r{repeat + 1} {mode} {row['throughput_pages_per_s']:.2f} p/s", flush=True)
                case["repeats"].append(result)
                data["last_capture"] = datetime.now().astimezone().isoformat(timespec="seconds")
                checkpoint = RAW.with_suffix(".tmp")
                checkpoint.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0))
                checkpoint.replace(RAW)


def cohort(name, page):
    if page["soft_mask_axial_shadings"]:
        return "gradient + soft mask"
    if name == "image-heavy-100" and page["page"] >= 71:
        return "synthetic multi-image"
    if name == "vector-heavy-100" and page["page"] >= 66:
        return "synthetic dense vector"
    return "other image pages" if page["image_draws"] else "other pages"


def summarize():
    data = json.loads(gzip.decompress(RAW.read_bytes()))
    inventory = load(ROOT / "evidence/real-doc-throughput-20261118/page-content.json")
    historical = load(ROOT / "evidence/p95-then-throughput-20261118/results.json")["cases"]
    summary = {}
    for name, (count, *modes) in CASES.items():
        case = data["cases"][name]
        repeats = case["repeats"]
        if len(repeats) != REPEATS or case["sha256"] != inventory[name]["sha256"]:
            raise ValueError(f"Incomplete capture or wrong fixture for {name}")
        sweep_ms, p50, p95, page_means = {}, {}, {}, {}
        for mode in ["full", "pdfjs", *modes]:
            matrices = [repeat[mode]["page_ms"] for repeat in repeats]
            sweep_ms[mode] = [median(map(sum, zip(*matrix))) for matrix in matrices]
            samples = [sorted(t for page in matrix for t in page) for matrix in matrices]
            p50[mode] = median(map(median, samples))
            p95[mode] = median(row[math.ceil(.95 * len(row)) - 1] for row in samples)
            page_means[mode] = [mean(t for row in rows for t in row) for rows in zip(*matrices)]
        signed = [a - b for a, b in zip(page_means["full"], page_means["pdfjs"])]
        ranked = sorted(range(count), key=lambda i: signed[i], reverse=True)
        top = [i for i in ranked[:math.ceil(count / 10)] if signed[i] > 0]
        positive = sum(max(0, d) for d in signed)
        cohorts = {}
        for i, page in enumerate(inventory[name]["pages"]):
            row = cohorts.setdefault(cohort(name, page), {
                "pages": 0, "slower": 0, "net_ms": 0, "positive_ms": 0,
                "ablation_ms": dict.fromkeys(modes, 0),
            })
            row["pages"] += 1
            row["slower"] += signed[i] > 0
            row["net_ms"] += signed[i]
            row["positive_ms"] += max(0, signed[i])
            for mode in modes:
                row["ablation_ms"][mode] += page_means["full"][i] - page_means[mode][i]
        reference = historical[f"{name}@{WIDTH}"]
        baseline = sweep_ms["full"]
        pdfjs_sweeps = sweep_ms["pdfjs"]
        summary[name] = {
            "throughput": {mode: count * 1000 / median(values) for mode, values in sweep_ms.items()},
            "sweep_ms_repeats": sweep_ms,
            "paired_savings_ms": {mode: [a - b for a, b in zip(baseline, sweep_ms[mode])]
                                  for mode in modes},
            "paired_baseline_ratios": [a / b for a, b in zip(baseline, pdfjs_sweeps)],
            "p50_ms": p50,
            "p95_ms": p95,
            "total_ms_ratio": (sum(page_means["full"]) / sum(page_means["pdfjs"])),
            "old_throughput": {mode: reference[mode]["throughput_pages_per_s_median"]
                               for mode in ("exreader", "pdfjs")},
            "slower_pages": sum(d > 0 for d in signed),
            "positive_ms": positive,
            "net_ms": sum(signed),
            "top_decile_positive_share": sum(max(0, signed[i]) for i in top) / positive if positive else 0,
            "top_decile_pages": [i + 1 for i in top],
            "top_decile_swap_net_ms": sum(signed) - sum(signed[i] for i in top),
            "cohorts": cohorts,
            "gates": [repeat[mode]["pre_cpu"] for repeat in repeats for mode in repeat],
        }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--pdfjs-root", type=Path)
    args = parser.parse_args()
    if args.library and args.pdfjs_root:
        capture(args.library.resolve(), args.pdfjs_root.resolve())
    elif args.library or args.pdfjs_root:
        parser.error("Capture requires both --library and --pdfjs-root")
    else:
        summarize()
