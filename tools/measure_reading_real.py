#!/usr/bin/env python3
"""Real-document Linux baseline. All execution and evidence computation belong in Actions."""
# SPDX-License-Identifier: MIT
import argparse
import copy
import json
import math
import os
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from measure_reading_core import ROOT, git, sha256
from measure_reading_pdf import number, require
from check_parallel_integration import fetch, pages

SDK = "9c69bc4c7efb0cff68ced27562709fe597189041"
CORPUS_REGISTRATION = "ea5c13e081cfba86d9f6dd759439894463e51126"
PROTECTED = ("src", "include", "cmake", "CMakeLists.txt", "tests/fixtures",
             ".github/workflows/native.yml", ".github/workflows/reliability.yml", "bindings")
CONTRACT = ROOT / "tests/reading_real/contract.json"
MANIFEST = ROOT / "tools/reading_corpus/real-v1.json"
BUDGETS = ROOT / "tests/reading_real/budgets.json"
EPUB_MEMORY = ("workspace_bytes", "peak_workspace_bytes", "index_bytes", "cache_bytes",
               "checkpoint_bytes", "explicit_snapshot_bytes")
SIGNATURE_FIELDS = ("width", "height", "pixel_hash", "text_start", "text_end", "text_bytes", "text_hash",
                    "position_hash", "position_items")


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


def baseline_origin(budgets, source):
    """An invented or failed earlier run cannot authorize a numeric budget."""
    run = fetch("actions/runs/" + str(budgets["baseline_run_id"]))
    require(run["head_sha"] == budgets["baseline_source_sha"] and
            run["run_attempt"] == budgets["baseline_run_attempt"] and
            run["status"] == "completed" and run["conclusion"] == "success" and
            run["path"] == ".github/workflows/reading-real.yml", "Baseline run identity/status refused")
    require(run["head_sha"] != source and subprocess.run(
        ["git", "merge-base", "--is-ancestor", run["head_sha"], source], cwd=ROOT).returncode == 0,
        "Baseline source must be an earlier ancestor")
    jobs = pages("actions/runs/" + str(run["id"]) + "/jobs", "jobs")
    require(len(jobs) == 1 and jobs[0]["name"] == "reading-performance" and
            jobs[0]["head_sha"] == run["head_sha"] and jobs[0]["status"] == "completed" and
            jobs[0]["conclusion"] == "success", "Baseline performance job refused")
    artifacts = pages("actions/runs/" + str(run["id"]) + "/artifacts", "artifacts")
    matching = [item for item in artifacts if item["name"] == f"reading-real-{run['id']}-{run['run_attempt']}"]
    require(len(matching) == 1, "Baseline artifact missing/duplicate")
    artifact = matching[0]
    require(artifact["id"] == budgets["baseline_artifact_id"] and
            re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest") or "") is not None and
            artifact["digest"] == budgets["baseline_artifact_digest"] and not artifact["expired"] and
            artifact["size_in_bytes"] > 0 and artifact["workflow_run"]["id"] == run["id"] and
            artifact["workflow_run"]["head_sha"] == run["head_sha"], "Baseline artifact identity refused")
    return {"run": run, "jobs": jobs, "artifact": artifact}


def retain_baseline_report(origin, output):
    archive_path = output / ".baseline-input.zip"
    try:
        with archive_path.open("wb") as stream:
            subprocess.run(["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{origin['artifact']['id']}/zip"],
                           stdout=stream, check=True, timeout=120)
        require("sha256:" + sha256(archive_path) == origin["artifact"]["digest"], "Baseline ZIP digest refused")
        with zipfile.ZipFile(archive_path) as archive:
            name = "reading-real/summary.json"
            require(archive.namelist().count(name) == 1 and archive.getinfo(name).file_size <= 16 * 1024 * 1024,
                    "Baseline summary missing, duplicate or oversized")
            (output / "baseline-summary.json").write_bytes(archive.read(name))
        origin["summary_file"] = "baseline-summary.json"
        origin["summary_sha256"] = sha256(output / "baseline-summary.json")
    finally:
        archive_path.unlink(missing_ok=True)


def verify_baseline_report(budgets, current, output):
    origin = current["baseline_origin"]
    require(origin["summary_file"] == "baseline-summary.json" and
            sha256(output / "baseline-summary.json") == origin["summary_sha256"] == budgets["baseline_summary_sha256"],
            "Baseline summary digest refused")
    baseline = read(output / "baseline-summary.json")
    require(baseline["schema"] == 1 and baseline["scope"] == current["scope"] and
            baseline["source_sha"] == budgets["baseline_source_sha"] == origin["run"]["head_sha"] and
            baseline["run_id"] == str(budgets["baseline_run_id"]) and
            baseline["run_attempt"] == str(budgets["baseline_run_attempt"]) and baseline["measurement_valid"] is True,
            "Baseline report identity or complete measurement refused")
    require(baseline["before"] == baseline["after"] and baseline["before"]["source_clean"] and
            baseline["sdk_candidate"] == current["sdk_candidate"] and
            baseline["before"]["sdk_candidate"] == current["before"]["sdk_candidate"] and
            baseline["before"]["sdk_trees"] == current["before"]["sdk_trees"], "Baseline SDK identity refused")
    require(baseline["contract_sha256"] == current["contract_sha256"] == budgets["contract_sha256"] and
            baseline["corpus_manifest_sha256"] == current["corpus_manifest_sha256"] == budgets["corpus_manifest_sha256"] and
            baseline["contract"] == current["contract"] and baseline["files"] == current["files"] and
            baseline["before"]["font"] == current["before"]["font"] and
            baseline["before"]["inputs"] == current["before"]["inputs"], "Baseline contract/corpus/font refused")
    require(all(baseline["environment"][key] == current["environment"][key] for key in ("cpu_model", "compiler", "reference")) and
            budgets["cpu_model"] == baseline["environment"]["cpu_model"] and
            budgets["compiler"] == baseline["environment"]["compiler"], "Baseline environment refused")
    require(baseline["refusal_regression"]["passed"] is True and
            baseline["signature_refusal_regression"]["passed"] is True, "Baseline evidence refusals were not run")
    results = baseline["results"]
    require(set(results["cases"]) == set(budgets["cases"]) == {entry["id"] for entry in current["files"]},
            "Baseline case coverage differs")
    require(budgets["page_signatures"] == results["page_signatures"], "Frozen signatures do not come from pinned baseline")
    policy = current["contract"]["budget_derivation"]
    for case, limits in budgets["cases"].items():
        require(set(limits) == set(results["cases"][case]), "Baseline metric coverage differs")
        for key, maximum in limits.items():
            measured = results["cases"][case][key]["p95"]
            require(number(measured) and number(maximum), "Invalid baseline-derived budget")
            cap = measured * policy["latency_multiplier_max"] if key.endswith("_ms") else (
                measured if key == "oversize_fallbacks" else 0 if key == "explicit_snapshot_bytes" else
                measured * policy["byte_multiplier_max"] + policy["memory_slack_bytes_max"])
            require(maximum <= cap, "Budget is not bounded by pinned baseline: " + case + "/" + key)
    require(number(budgets["consumer_bytes"]) and number(budgets["installed_sdk_bytes"]) and
            budgets["consumer_bytes"] <= baseline["before"]["binary"]["bytes"] * policy["byte_multiplier_max"] +
            policy["consumer_slack_bytes_max"] and
            budgets["installed_sdk_bytes"] <= baseline["installed_sdk"]["bytes"] * policy["byte_multiplier_max"],
            "Size budget is not bounded by pinned baseline")
    differences = {f"{item['case']}/{item['page']}": item["normalized_mean_absolute_error"]
                   for item in results["pixel_comparisons"]}
    require(set(differences) == set(budgets["pixel_tolerances"]) and all(number(value) and
            value <= differences[key] + policy["external_difference_slack_max"] for key, value in budgets["pixel_tolerances"].items()),
            "External difference boundary is not bounded by pinned baseline")
    return baseline


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
    require(record["schema"] == 1 and record["success"] is True and record["status"] == 0 and
            record["engine_version"] == "3.40.0" and record["engine_abi"] == 1 and
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
    require(abs(record["first_visible_ms"] - record["font_open_ms"] - record["open_ms"] -
                samples[0]["total_ms"]) <= .000003, "First-frame timing includes unmeasured work")
    require([sample["phase"] for sample in samples] ==
            ["first"] + ["sequential"] * len(sequential) + ["random"] * len(random) + ["reference"] * len(reference),
            "Operation order changed")
    expected_random = contract["seed"]
    routes = [(sample["part"], sample["page"]) for sample in samples[:1 + len(sequential)]]
    signatures = {}
    fallback_count = 0
    for sample in samples:
        require(type(sample["page"]) is int and sample["page"] >= 0 and type(sample["part"]) is int and sample["part"] >= 0,
                "Invalid page route")
        memory_fields = EPUB_MEMORY if entry["format"].lower() == "epub" else ("directory_metadata_bytes",)
        for field in ("layout_ms", "render_ms", "total_ms", "bitmap_bytes") + memory_fields:
            require(number(sample[field]), "Invalid operation metric " + field)
        require(type(sample["width"]) is int and type(sample["height"]) is int and
                0 < sample["width"] <= 4096 and 0 < sample["height"] <= 4096 and
                sample["bitmap_bytes"] >= sample["width"] * sample["height"] * 4, "Invalid bitmap size")
        require(isinstance(sample["pixel_hash"], str) and len(sample["pixel_hash"]) == 16 and
                all(char in "0123456789abcdef" for char in sample["pixel_hash"]), "Invalid bitmap hash")
        require(abs(sample["total_ms"] - sample["layout_ms"] - sample["render_ms"]) <= .000003, "Timing accounting changed")
        route = (sample["part"], sample["page"])
        signature = (sample["width"], sample["height"], sample["pixel_hash"])
        require(type(sample["text_start"]) is int and type(sample["text_end"]) is int and
                0 <= sample["text_start"] <= sample["text_end"] and
                sample["text_bytes"] == sample["text_end"] - sample["text_start"] and
                type(sample["position_items"]) is int and sample["position_items"] >= 0 and
                all(isinstance(sample[key], str) and re.fullmatch(r"[0-9a-f]{16}", sample[key]) is not None
                    for key in ("text_hash", "position_hash")), "Invalid UTF-8/position signature evidence")
        signature += tuple(sample[key] for key in SIGNATURE_FIELDS[3:])
        if entry["format"].lower() == "epub":
            require(number(sample["layout_bytes"]) and sample["layout_bytes"] > 0, "Invalid layout size")
            require(type(sample["oversize_fallback"]) is int and sample["oversize_fallback"] in (0, 1), "Invalid fallback marker")
            if sample["oversize_fallback"]:
                require(sample["phase"] == "random" and sample["cache_rejection_status"] == 6 and
                        sample["layout_bytes"] > contract["epub"]["page_cache_budget"] and
                        number(sample["failed_cache_ms"]) and 0 < sample["failed_cache_ms"] <= sample["layout_ms"],
                        "Fallback did not prove oversize cache rejection and complete accounting")
                fallback_count += 1
            else:
                require(sample["cache_rejection_status"] == 0 and sample["failed_cache_ms"] == 0, "Hidden cache rejection")
        require(route not in signatures or signatures[route] == signature, "Same route changed pixels")
        signatures[route] = signature
        if entry["format"].lower() == "epub":
            require(sample["explicit_snapshot_bytes"] == 0 and
                    sample["peak_workspace_bytes"] <= contract["epub"]["workspace_budget"] and
                    sample["cache_bytes"] <= contract["epub"]["page_cache_budget"] and
                    sample["checkpoint_bytes"] <= contract["epub"]["checkpoint_budget"], "Bounded resource contract failed")
    require(record["oversize_fallbacks"] == fallback_count, "Fallback count differs from retained routes")
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
    if entry["format"].lower() == "pdf":
        metrics["fixed_directory_bytes"] = record["fixed_directory_bytes"]
    else:
        metrics["oversize_fallbacks"] = fallback_count
        metrics["layout_bytes"] = max(sample["layout_bytes"] for sample in samples)
    for field in ("bitmap_bytes",) + memory_fields:
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


def fallback_refusals(record, entry, contract):
    native_metrics(record, entry, contract)
    changes = {"not_oversize": ("layout_bytes", contract["epub"]["page_cache_budget"]),
               "no_cache_rejection": ("cache_rejection_status", 0), "no_rejected_get_time": ("failed_cache_ms", 0),
               "changed_route": ("page", 999999), "changed_text": ("text_hash", "0" * 16)}
    for name, (key, value) in changes.items():
        mutant = copy.deepcopy(record)
        next(sample for sample in mutant["samples"] if sample["oversize_fallback"])[key] = value
        try:
            native_metrics(mutant, entry, contract)
        except ValueError:
            continue
        raise ValueError("Oversize refusal accepted " + name)
    result = {"scope": "observed_owned_oversize_consumer_policy_only", "case": entry["id"],
              "positive": 1, "refused": len(changes), "passed": True}
    print(json.dumps({"oversize_refusal_regression": result}), flush=True)
    return result


def frozen_signatures(expected, observed):
    require(expected == observed,
            "Cross-source page RGBA/UTF-8/position signature changed; explicit review and a new frozen baseline required")


def signature_refusals(record, entry, contract):
    _, baseline = native_metrics(record, entry, contract)
    frozen_signatures(baseline, baseline)
    route = (record["samples"][0]["part"], record["samples"][0]["page"])
    for field in ("pixel_hash", "text_hash", "position_hash"):
        mutant = copy.deepcopy(record)
        for sample in mutant["samples"]:
            if (sample["part"], sample["page"]) == route:
                sample[field] = "0" * 16
        # Deliberately stable corruption passes ordinary within-process repeat checks.
        _, changed = native_metrics(mutant, entry, contract)
        try:
            frozen_signatures(baseline, changed)
        except ValueError:
            continue
        raise ValueError("Stable cross-source corruption accepted: " + field)
    result = {"scope": "observed_native_route_signature_guard_only", "case": entry["id"],
              "positive": 1, "stable_corruptions_refused": 3, "passed": True}
    print(json.dumps({"signature_refusal_regression": result}), flush=True)
    return result


def audit(summary, output, budgets=None):
    require(summary["schema"] == 1 and summary["scope"] == "linux_representative_reading", "Wrong report scope")
    require(summary["render_parity_granted"] is False, "External pixel comparison cannot grant render parity")
    require(summary["run_id"] == os.environ["GITHUB_RUN_ID"] and
            summary["run_attempt"] == os.environ["GITHUB_RUN_ATTEMPT"] and
            summary["source_sha"] == os.environ["GITHUB_SHA"], "Cloud run/source/attempt identity changed")
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
    page_signatures = {case: {f"{part}/{page}": dict(zip(SIGNATURE_FIELDS, values))
                             for (part, page), values in routes.items()} for case, routes in signatures.items()}
    if budgets is not None:
        require(summary["budget_sha256"] == sha256(BUDGETS) and budgets == read(BUDGETS), "Budget identity changed")
        require(budgets["schema"] == 1 and budgets["frozen"] is True and
                budgets["contract_sha256"] == summary["contract_sha256"] and
                budgets["corpus_manifest_sha256"] == summary["corpus_manifest_sha256"], "Unfrozen/incompatible budgets")
        require(budgets["baseline_source_sha"] != summary["source_sha"] and budgets["baseline_run_id"] and
                len(budgets["baseline_source_sha"]) == 40, "Budget needs an earlier identified baseline")
        origin = summary["baseline_origin"]
        require(origin["run"]["id"] == budgets["baseline_run_id"] and
                origin["run"]["head_sha"] == budgets["baseline_source_sha"] and
                origin["artifact"]["digest"] == budgets["baseline_artifact_digest"], "Baseline origin changed")
        verify_baseline_report(budgets, summary, output)
        require(budgets["cpu_model"] == summary["environment"]["cpu_model"] and
                budgets["compiler"] == summary["environment"]["compiler"], "Incomparable baseline CPU/compiler")
        require(budgets["signature_policy"] == "exact-baseline-route-rgba-utf8-position" and
                isinstance(budgets["signature_review_record"], str) and budgets["signature_review_record"].strip(),
                "Missing fixed baseline signature review record")
        frozen_signatures(budgets["page_signatures"], page_signatures)
        require(set(budgets["cases"]) == set(results), "Budget case coverage differs")
        for name, limits in budgets["cases"].items():
            require(set(limits) == set(results[name]), "Budget metric coverage differs")
            for key, maximum in limits.items():
                require(number(maximum) and results[name][key]["p95"] <= maximum, f"Budget exceeded: {name}/{key}")
        require(summary["before"]["binary"]["bytes"] <= budgets["consumer_bytes"], "Consumer size budget exceeded")
        require(summary["installed_sdk"]["bytes"] <= budgets["installed_sdk_bytes"], "Installed SDK size budget exceeded")
        require(set(budgets["pixel_tolerances"]) == {f"{item['case']}/{item['page']}" for item in comparisons},
                "Pixel tolerance coverage differs")
        require(isinstance(budgets["pixel_review_record"], str) and budgets["pixel_review_record"].strip(),
                "Missing per-page external difference-boundary review record")
        for item in comparisons:
            require(item["normalized_mean_absolute_error"] <= budgets["pixel_tolerances"][f"{item['case']}/{item['page']}"],
                    f"Pixel difference exceeds reviewed tolerance: {item['case']}/{item['page']}")
    return {"cases": results, "pixel_comparisons": comparisons, "page_signatures": page_signatures}


def selfcheck(summary, output, budgets):
    audit(summary, output, budgets)
    changes = {
        "source": lambda s: s.update(source_sha="0" * 40),
        "run": lambda s: s.update(run_id="0"),
        "attempt": lambda s: s.update(run_attempt="0"),
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
        "fake_fallback": lambda r: r["samples"][0].update(oversize_fallback=1),
        "hidden_cache_rejection": lambda r: r["samples"][0].update(cache_rejection_status=6),
        "changed_selected_text": lambda r: next(s for s in r["samples"] if s["phase"] == "random").update(text_hash="0" * 16),
        "changed_position": lambda r: next(s for s in r["samples"] if s["phase"] == "random").update(position_hash="0" * 16),
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
    summary["render_parity_granted"] = False
    summary["external_pixel_scope"] = "reviewed difference-regression boundaries only; never a correctness/parity score"
    summary["cross_source_signatures_checked"] = False
    summary["memory_telemetry"] = {
        "peak_rss_bytes": "whole-process Linux high-water; components may overlap and are not added",
        "epub": "public chapter workspace/index/cache/checkpoint counters",
        "pdf": "public directory_metadata_bytes excludes provider payload; internal provider cache/workspace unavailable through public API; whole-process RSS covers the overall peak",
        "raw_pdf_chapter_zero_fields": "not applicable; omitted from PDF case metrics and budgets"}
    summary["diagnostic_observations"] = []
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
        budgets = read(args.budgets) if args.budgets else None
        if budgets:
            summary["baseline_origin"] = baseline_origin(budgets, args.source_sha)
            retain_baseline_report(summary["baseline_origin"], output)
            verify_baseline_report(budgets, summary, output)
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
                    try:
                        observation["metrics"], _ = native_metrics(raw, entry, contract)
                        observation["complete_process_valid"] = True
                        if "signature_refusal_regression" not in summary:
                            summary["signature_refusal_regression"] = signature_refusals(raw, entry, contract)
                        if raw["oversize_fallbacks"] and "oversize_refusal_regression" not in summary:
                            summary["oversize_refusal_regression"] = fallback_refusals(raw, entry, contract)
                    except (ValueError, KeyError, TypeError) as error:
                        observation["complete_process_valid"] = False
                        observation["validation_problem"] = str(error)
                    summary["diagnostic_observations"].append(observation)
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
                    if "native_identity" in item and "reference_identity" in item:
                        try:
                            item["diagnostic_pixel_difference"] = pixel_difference(output / item["native"], output / item["reference"])
                        except (OSError, ValueError) as error:
                            item["diagnostic_pixel_problem"] = str(error)
                    print(json.dumps({"reference_observation": item}), flush=True)
                    summary["references"].append(item)
        summary["after"] = identity(binary, font, args.manifest, CONTRACT, entries, args.corpus)
        summary["results"] = audit(summary, output, budgets)
        summary["refusal_regression"] = selfcheck(summary, output, budgets)
        summary["measurement_valid"] = True
        summary["real_document_credit"] = len(entries)
        summary["accepted"] = budgets is not None
        summary["cross_source_signatures_checked"] = budgets is not None
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
