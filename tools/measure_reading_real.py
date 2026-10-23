#!/usr/bin/env python3
"""Real-document Linux baseline. All execution and evidence computation belong in Actions."""
# SPDX-License-Identifier: MIT
import argparse
import copy
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path

from measure_reading_core import ROOT, git, sha256
from measure_reading_pdf import number, require

SDK = "9c69bc4c7efb0cff68ced27562709fe597189041"
CORPUS_REGISTRATION = "ea5c13e081cfba86d9f6dd759439894463e51126"
PROTECTED = ("src", "include", "cmake", "CMakeLists.txt", "tests/fixtures",
             ".github/workflows/native.yml", ".github/workflows/reliability.yml", "bindings")
CONTRACT = ROOT / "tests/reading_real/contract.json"
MANIFEST = ROOT / "tools/reading_corpus/real-v1.json"
BUDGETS = ROOT / "tests/reading_real/budgets.json"


def read(path):
    def reject(value):
        raise ValueError("Non-finite JSON: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def percentile(values, fraction):
    require(bool(values) and all(number(value) for value in values), "Missing/invalid numeric samples")
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def execute(command, stdout, stderr, timeout=180, affinity=False):
    item = {"command": [str(value) for value in command], "stdout": stdout.name,
            "stderr": stderr.name, "exit_code": None}
    environment = os.environ.copy()
    environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    def pin():
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            result = subprocess.run(item["command"], stdout=out, stderr=err, timeout=timeout,
                                    env=environment, preexec_fn=pin if affinity else None)
        item["exit_code"] = result.returncode
        if result.returncode:
            item["failure"] = "process_failure"
    except (OSError, subprocess.TimeoutExpired) as error:
        item["failure"] = type(error).__name__
    for key, path in (("stdout", stdout), ("stderr", stderr)):
        item[key + "_sha256"] = sha256(path)
    return item


def checked_output(command):
    return subprocess.check_output(command, text=True, timeout=30).strip()


def environment():
    cpu = Path("/proc/cpuinfo").read_text()
    return {"runner_os": os.environ.get("RUNNER_OS"), "runner_arch": os.environ.get("RUNNER_ARCH"),
            "runner_image": os.environ.get("ImageOS"), "runner_image_version": os.environ.get("ImageVersion"),
            "platform": platform.platform(), "cpu_model": next((line.split(":", 1)[1].strip()
                for line in cpu.splitlines() if line.startswith("model name")), None),
            "allowed_cpus": sorted(os.sched_getaffinity(0)), "pinned_cpu": min(os.sched_getaffinity(0)),
            "compiler": checked_output(["cc", "--version"]),
            "reference": subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True, check=True).stderr.strip()}


def file_identity(path):
    return {"sha256": sha256(path), "bytes": path.stat().st_size}


def identity(binary, font, manifest, contract, entries, corpus):
    return {"source_sha": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
            "source_clean": not git("status", "--porcelain", "--untracked-files=all"),
            "sdk_candidate": SDK, "sdk_trees": {path: git("rev-parse", "HEAD:" + path) for path in PROTECTED},
            "binary": file_identity(binary), "font": file_identity(font),
            "manifest_sha256": sha256(manifest), "contract_sha256": sha256(contract),
            "inputs": {entry["id"]: file_identity(corpus / entry["path"]) for entry in entries},
            "tools": {path: sha256(ROOT / path) for path in
                ("tools/reading_real_benchmark.c", "tools/measure_reading_real.py", "tools/host_font.py", "tests/reading_real/CMakeLists.txt")}}


def native_metrics(record, entry, contract):
    require(record["schema"] == 1 and record["success"] is True and record["status"] == 0 and record["engine_version"] == "3.40.0" and
            record["stage"] == "complete" and record["mode"] == entry["format"].lower(), "Native measurement failed")
    for field in ("font_open_ms", "open_ms", "first_visible_ms", "peak_rss_bytes", "baseline_peak_rss_bytes"):
        require(number(record[field]), "Invalid metric " + field)
    require(record["peak_rss_bytes"] > 0 and record["peak_rss_bytes"] >= record["baseline_peak_rss_bytes"], "Invalid RSS")
    samples = record["samples"]
    sequential = [sample for sample in samples if sample["phase"] == "sequential"]
    random = [sample for sample in samples if sample["phase"] == "random"]
    reference = [sample for sample in samples if sample["phase"] == "reference"]
    require(bool(samples) and samples[0]["phase"] == "first" and samples[0]["page"] == 0 and
            len(sequential) == contract["sequential_turns"] and len(random) == contract["random_turns"] and
            len(samples) == 1 + len(sequential) + len(random) + len(reference), "Incomplete native operation plan")
    require([sample["phase"] for sample in samples] ==
            ["first"] + ["sequential"] * len(sequential) + ["random"] * len(random) + ["reference"] * len(reference),
            "Operation order changed")
    expected_random = contract["seed"]
    routes = [(sample["part"], sample["page"]) for sample in samples[:1 + len(sequential)]]
    signatures = {}
    for sample in samples:
        require(type(sample["page"]) is int and sample["page"] >= 0 and type(sample["part"]) is int and sample["part"] >= 0,
                "Invalid page route")
        for field in ("layout_ms", "render_ms", "total_ms", "bitmap_bytes", "workspace_bytes", "peak_workspace_bytes",
                      "index_bytes", "cache_bytes", "checkpoint_bytes", "explicit_snapshot_bytes"):
            require(number(sample[field]), "Invalid operation metric " + field)
        require(type(sample["width"]) is int and type(sample["height"]) is int and
                0 < sample["width"] <= 4096 and 0 < sample["height"] <= 4096 and
                sample["bitmap_bytes"] >= sample["width"] * sample["height"] * 4, "Invalid bitmap size")
        require(isinstance(sample["pixel_hash"], str) and len(sample["pixel_hash"]) == 16 and
                all(char in "0123456789abcdef" for char in sample["pixel_hash"]), "Invalid bitmap hash")
        require(abs(sample["total_ms"] - sample["layout_ms"] - sample["render_ms"]) <= .000003, "Timing accounting changed")
        route = (sample["part"], sample["page"])
        signature = (sample["width"], sample["height"], sample["pixel_hash"])
        require(route not in signatures or signatures[route] == signature, "Same route changed pixels")
        signatures[route] = signature
        if entry["format"].lower() == "epub":
            require(sample["explicit_snapshot_bytes"] == 0 and
                    sample["peak_workspace_bytes"] <= contract["epub"]["workspace_budget"] and
                    sample["cache_bytes"] <= contract["epub"]["page_cache_budget"] and
                    sample["checkpoint_bytes"] <= contract["epub"]["checkpoint_budget"], "Bounded resource contract failed")
    for index, sample in enumerate(sequential):
        if entry["format"].lower() == "pdf":
            require(sample["page"] == (index + 1) % record["page_count"], "Sequential PDF plan changed")
        else:
            previous = routes[index]
            require((sample["part"] == previous[0] and sample["page"] == previous[1] + 1) or
                    (sample["part"] > previous[0] and sample["page"] == 0), "Sequential EPUB route changed")
    for sample in random:
        expected_random = (expected_random * 1664525 + 1013904223) & 0xffffffff
        target = (0, expected_random % record["page_count"]) if entry["format"].lower() == "pdf" else routes[expected_random % len(routes)]
        require((sample["part"], sample["page"]) == target, "Random plan changed")
    require([sample["page"] for sample in reference] == (entry["selected_pages"] if entry["format"].lower() == "pdf" else []),
            "Reference-page selection changed")
    metrics = {field: record[field] for field in ("font_open_ms", "open_ms", "first_visible_ms", "peak_rss_bytes")}
    metrics["fixed_directory_bytes"] = record["fixed_directory_bytes"]
    for field in ("bitmap_bytes", "workspace_bytes", "peak_workspace_bytes", "index_bytes", "cache_bytes",
                  "checkpoint_bytes", "explicit_snapshot_bytes"):
        metrics[field] = max(sample[field] for sample in samples)
    return metrics, signatures


def pixel_difference(native, reference):
    from PIL import Image, ImageChops
    with Image.open(native) as a, Image.open(reference) as b:
        a, b = a.convert("RGB"), b.convert("RGB")
        require(a.size == b.size, "Reference dimensions differ")
        histogram = ImageChops.difference(a, b).histogram()
        mean = sum((index % 256) * count for index, count in enumerate(histogram)) / (a.width * a.height * 3 * 255)
        nonzero = sum(histogram[index] for index in range(len(histogram)) if index % 256)
        # Exact pixels are diagnostic; antialias/font engines differ even for correct pages.
        return {"width": a.width, "height": a.height, "normalized_mean_absolute_error": mean,
                "changed_channel_fraction": nonzero / (a.width * a.height * 3)}


def audit(summary, output, budgets=None):
    require(summary["schema"] == 1 and summary["scope"] == "linux_representative_reading", "Wrong report scope")
    before = summary["before"]
    require(before == summary["after"] and before["source_clean"] and
            before["source_sha"] == summary["source_sha"] and before["sdk_candidate"] == SDK,
            "Source/input identity changed")
    require(before["contract_sha256"] == summary["contract_sha256"] and
            before["manifest_sha256"] == summary["corpus_manifest_sha256"], "Contract/manifest identity changed")
    require(summary["corpus_registration_sha"] == CORPUS_REGISTRATION, "Corpus registration identity changed")
    contract = summary["contract"]
    require(before["font"]["sha256"] == contract["font_sha256"] and contract == read(CONTRACT), "Font/contract drift")
    entries = summary["files"]
    require(entries == [entry for entry in read(MANIFEST)["files"] if entry.get("performance_representative")] and
            summary["corpus_manifest_sha256"] == sha256(MANIFEST), "Frozen representative manifest changed")
    require(len(entries) >= 6 and {entry["format"].lower() for entry in entries} == {"epub", "pdf"} and
            len({entry["id"] for entry in entries}) == len(entries), "Incomplete/duplicate representative corpus")
    require(len(summary["attempts"]) == len(entries) * contract["processes"], "Missing native process")
    rows = {entry["id"]: [] for entry in entries}
    pooled = {entry["id"]: {f"{phase}_{field}": [] for phase in ("sequential", "random")
                           for field in ("layout_ms", "render_ms", "total_ms")} for entry in entries}
    signatures = {}
    for attempt, (entry, process) in zip(summary["attempts"],
            ((entry, process) for entry in entries for process in range(1, contract["processes"] + 1))):
        require(attempt["case"] == entry["id"] and attempt["process"] == process and attempt["exit_code"] == 0 and
                not attempt.get("failure"), "Failed/misidentified native process")
        require(before["inputs"][entry["id"]] == {"sha256": entry["sha256"], "bytes": entry["size"]}, "Corpus identity drift")
        for key in ("stdout", "stderr"):
            name = attempt[key]
            require(Path(name).name == name and sha256(output / name) == attempt[key + "_sha256"], "Raw output changed/missing")
        record = read(output / attempt["stdout"])
        values, pixels = native_metrics(record, entry, contract)
        require(entry["id"] not in signatures or signatures[entry["id"]] == pixels, "Cross-process pixels changed")
        signatures[entry["id"]] = pixels
        rows[entry["id"]].append(values)
        for phase in ("sequential", "random"):
            for field in ("layout_ms", "render_ms", "total_ms"):
                pooled[entry["id"]][f"{phase}_{field}"].extend(sample[field] for sample in record["samples"]
                                                            if sample["phase"] == phase)
    comparisons = []
    for item in summary["references"]:
        require(item["exit_code"] == 0 and not item.get("failure"), "Reference engine failed")
        for name in ("native", "reference"):
            path = output / item[name]
            require(path.resolve().is_relative_to(output.resolve()) and file_identity(path) == item[name + "_identity"],
                    "Reference/native pixel evidence changed")
        comparisons.append({"case": item["case"], "page": item["page"],
                            **pixel_difference(output / item["native"], output / item["reference"])})
    expected_references = [(entry["id"], page) for entry in entries if entry["format"].lower() == "pdf" for page in entry["selected_pages"]]
    require([(item["case"], item["page"]) for item in comparisons] == expected_references, "Missing/changed reference-page plan")
    results = {name: {key: {"p50": percentile([row[key] for row in values], .5),
                            "p95": percentile([row[key] for row in values], .95)} for key in values[0]}
               for name, values in rows.items()}
    for name, metrics in pooled.items():
        results[name].update({key: {"p50": percentile(values, .5), "p95": percentile(values, .95)}
                              for key, values in metrics.items()})
    if budgets is not None:
        require(summary["budget_sha256"] == sha256(BUDGETS) and budgets == read(BUDGETS), "Budget identity changed")
        require(budgets["schema"] == 1 and budgets["frozen"] is True and
                budgets["contract_sha256"] == summary["contract_sha256"] and
                budgets["corpus_manifest_sha256"] == summary["corpus_manifest_sha256"], "Unfrozen/incompatible budgets")
        require(budgets["baseline_source_sha"] != summary["source_sha"] and budgets["baseline_run_id"] and
                len(budgets["baseline_source_sha"]) == 40, "Budget needs an earlier identified baseline")
        require(budgets["cpu_model"] == summary["environment"]["cpu_model"] and
                budgets["compiler"] == summary["environment"]["compiler"], "Incomparable baseline CPU/compiler")
        require(set(budgets["cases"]) == set(results), "Budget case coverage differs")
        for name, limits in budgets["cases"].items():
            require(set(limits) == set(results[name]), "Budget metric coverage differs")
            for key, maximum in limits.items():
                require(number(maximum) and results[name][key]["p95"] <= maximum, f"Budget exceeded: {name}/{key}")
        require(summary["before"]["binary"]["bytes"] <= budgets["consumer_bytes"], "Consumer size budget exceeded")
        require(summary["installed_sdk"]["bytes"] <= budgets["installed_sdk_bytes"], "Installed SDK size budget exceeded")
        require(set(budgets["pixel_tolerances"]) == {f"{item['case']}/{item['page']}" for item in comparisons},
                "Pixel tolerance coverage differs")
        for item in comparisons:
            require(item["normalized_mean_absolute_error"] <= budgets["pixel_tolerances"][f"{item['case']}/{item['page']}"],
                    f"Pixel difference exceeds reviewed tolerance: {item['case']}/{item['page']}")
    return {"cases": results, "pixel_comparisons": comparisons}


def selfcheck(summary, output, budgets):
    audit(summary, output, budgets)
    changes = {
        "source": lambda s: s.update(source_sha="0" * 40),
        "source_clean": lambda s: s["before"].update(source_clean=False),
        "contract": lambda s: s.update(contract_sha256="0" * 64),
        "manifest": lambda s: s.update(corpus_manifest_sha256="0" * 64),
        "missing_process": lambda s: s["attempts"].pop(),
        "failed_process": lambda s: s["attempts"][0].update(exit_code=1),
        "wrong_process": lambda s: s["attempts"][0].update(process=99),
        "raw_hash": lambda s: s["attempts"][0].update(stdout_sha256="0" * 64),
        "missing_reference": lambda s: s["references"].pop(),
        "pixel_hash": lambda s: s["references"][0]["native_identity"].update(sha256="0" * 64),
        "duplicate_corpus": lambda s: s["files"].append(s["files"][0]),
    }
    for name, change in changes.items():
        mutant = copy.deepcopy(summary)
        change(mutant)
        try:
            audit(mutant, output, budgets)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        raise ValueError("Refusal regression accepted " + name)
    native = read(output / summary["attempts"][0]["stdout"])
    entry = summary["files"][0]
    raw_changes = {
        "native_failure": lambda r: r.update(success=False),
        "nonfinite_timing": lambda r: r.update(open_ms=float("nan")),
        "dropped_operation": lambda r: r["samples"].pop(),
        "random_route": lambda r: next(s for s in r["samples"] if s["phase"] == "random").update(page=999999),
        "bitmap_size": lambda r: r["samples"][0].update(bitmap_bytes=1),
        "timing_accounting": lambda r: r["samples"][0].update(total_ms=999999),
    }
    for name, change in raw_changes.items():
        mutant = copy.deepcopy(native);change(mutant)
        try:
            native_metrics(mutant, entry, summary["contract"])
        except (ValueError, KeyError, TypeError):
            continue
        raise ValueError("Native refusal regression accepted " + name)
    result = {"refusal_checks": len(changes) + len(raw_changes), "passed": True,
              "names": list(changes) + list(raw_changes)}
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--budgets", type=Path)
    args = parser.parse_args()
    require(os.environ.get("GITHUB_ACTIONS") == "true", "Measurements require GitHub Actions")
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    contract = read(CONTRACT);manifest = read(args.manifest)
    entries = [entry for entry in manifest["files"] if entry.get("performance_representative")]
    binary = args.binary.resolve();font = ROOT / contract["font_path"]
    summary = {"schema": 1, "scope": "linux_representative_reading", "accepted": False,
               "measurement_valid": False, "source_sha": args.source_sha, "sdk_candidate": SDK,
               "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
               "corpus_registration_sha": CORPUS_REGISTRATION,
               "contract_path": "tests/reading_real/contract.json", "budget_path": "tests/reading_real/budgets.json",
               "corpus_manifest_sha256": sha256(args.manifest), "contract_sha256": sha256(CONTRACT),
               "budget_sha256": sha256(args.budgets) if args.budgets else None,
               "contract": contract, "files": entries, "attempts": [], "references": [], "problems": [],
               "real_document_credit": 0, "synthetic_credit": 0, "wp16_cpu_credit_seconds": 0,
               "results": None, "complete_product": False}
    try:
        require(len(args.source_sha) == 40, "Use a full source SHA")
        require(subprocess.run(["git", "merge-base", "--is-ancestor", SDK, args.source_sha], cwd=ROOT).returncode == 0,
                "SDK is not an ancestor")
        require(subprocess.run(["git", "merge-base", "--is-ancestor", CORPUS_REGISTRATION, args.source_sha], cwd=ROOT).returncode == 0,
                "First corpus registration is not an ancestor")
        require(git("rev-parse", "HEAD:tools/reading_corpus/real-v1.json") ==
                git("rev-parse", CORPUS_REGISTRATION + ":tools/reading_corpus/real-v1.json"), "Registered manifest blob changed")
        for path in PROTECTED:
            require(git("rev-parse", "HEAD:" + path) == git("rev-parse", SDK + ":" + path), "SDK protected tree changed")
        summary["environment"] = environment()
        require(summary["environment"]["runner_os"] == "Linux" and summary["environment"]["runner_arch"] == "X64" and
                summary["environment"]["runner_image"] == "ubuntu22", "Wrong fixed runner")
        summary["before"] = identity(binary, font, args.manifest, CONTRACT, entries, args.corpus)
        sdk_files = sorted(path for path in args.sdk.rglob("*") if path.is_file())
        summary["installed_sdk"] = {"bytes": sum(path.stat().st_size for path in sdk_files),
            "files": {str(path.relative_to(args.sdk)): file_identity(path) for path in sdk_files}}
        summary["dynamic_dependencies"] = checked_output(["ldd", str(binary)])
        for entry in entries:
            source = args.corpus / entry["path"]
            for process in range(1, contract["processes"] + 1):
                # Warm input page cache without claiming a cold disk or a warm SDK process.
                for path in (source, font):
                    with path.open("rb") as stream:
                        while stream.read(1024 * 1024):
                            pass
                prefix = f"{entry['id']}-{process}"
                dump = output / prefix;dump.mkdir()
                pages = ",".join(str(page) for page in entry["selected_pages"]) if entry["format"].lower() == "pdf" else "-"
                item = execute([binary, entry["format"].lower(), source, font, dump, pages], output / (prefix + ".json"),
                               output / (prefix + ".stderr.log"), contract["process_timeout_seconds"], affinity=True)
                item.update(case=entry["id"], process=process)
                summary["attempts"].append(item)
                try:
                    raw = read(output / item["stdout"])
                    observation = {key: raw.get(key) for key in
                        ("success", "stage", "status", "open_ms", "first_visible_ms", "peak_rss_bytes")}
                    observation.update(case=entry["id"], process=process, exit_code=item["exit_code"],
                                       retained_operations=len(raw.get("samples", [])))
                    if item["exit_code"]:
                        observation["error"] = (output / item["stderr"]).read_text(encoding="utf-8")[:1000]
                    print(json.dumps({"observation": observation}), flush=True)
                except (OSError, ValueError):
                    print(json.dumps({"observation": {"case": entry["id"], "process": process,
                        "exit_code": item["exit_code"], "failure": item.get("failure", "invalid_native_json")}}), flush=True)
            if entry["format"].lower() == "pdf":
                for page in entry["selected_pages"]:
                    prefix = f"{entry['id']}-reference-{page}"
                    item = execute(["pdftoppm", "-f", page + 1, "-l", page + 1, "-singlefile", "-r", "72", "-aa", "yes",
                                    "-aaVector", "yes", source, output / prefix], output / (prefix + ".stdout.log"),
                                   output / (prefix + ".stderr.log"), 180)
                    item.update(case=entry["id"], page=page,
                                native=f"{entry['id']}-1/page-{page}.ppm", reference=prefix + ".ppm")
                    for key in ("native", "reference"):
                        path = output / item[key]
                        if path.is_file():
                            item[key + "_identity"] = file_identity(path)
                    summary["references"].append(item)
        summary["after"] = identity(binary, font, args.manifest, CONTRACT, entries, args.corpus)
        budgets = read(args.budgets) if args.budgets else None
        summary["results"] = audit(summary, output, budgets)
        summary["refusal_regression"] = selfcheck(summary, output, budgets)
        summary["measurement_valid"] = True
        summary["real_document_credit"] = len(entries)
        summary["accepted"] = budgets is not None
        if not budgets:
            summary["problems"].append("baseline_only: numeric performance and reviewed pixel budgets are not frozen")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        summary["problems"].append(str(error))
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("accepted", "measurement_valid", "source_sha", "run_id", "run_attempt",
                                                  "problems", "results")}, allow_nan=False))
    return 0 if summary["measurement_valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
