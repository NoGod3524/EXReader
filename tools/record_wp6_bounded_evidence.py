#!/usr/bin/env python3
"""Assemble the WP6 bounded-chapter evidence record from measured artifacts.

Every number is read from a recorded file; this script only normalizes paths,
computes the residency deltas and hashes the inputs.  It refuses to emit a
record when a required artifact is missing.
"""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import re
from pathlib import Path

MIB = 1024 * 1024


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def artifact(path):
    path = Path(path)
    return {"path": str(path), "sha256": sha256(path)}


def median_case(summary, name, key):
    case = summary["cases"].get(name, {})
    return (case.get("medians") or {}).get(key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--ctest-log", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument("--baseline-dll", type=Path, required=True)
    parser.add_argument("--compiler", default="")
    parser.add_argument("--verification", type=Path,
                        help="JSON merged into the record for checks run outside the probe")
    parser.add_argument("--main-repo", type=Path, required=True,
                        help="checkout holding the two protected untracked files")
    args = parser.parse_args(argv)
    protected = {
        "docs/validation/2026-10-19-shading-extent-ci.json":
            "a955abda1e35fd456172b2e78e1d687799e4ab5f1f977dec0efd7684aae9fdc1",
        "src/internal.h":
            "c951b04a1611008b2e97437d6877bebabf29ec2c374a1c8166c9aca14f34e904",
    }
    for name, expected in protected.items():
        actual = sha256(args.main_repo / name)
        if actual != expected:
            raise SystemExit("protected file changed: %s (%s)" % (name, actual))
    baseline = load(args.baseline)
    candidate = load(args.candidate)
    corpus = load(args.corpus / "manifest.json")
    log = args.ctest_log.read_text(encoding="utf-8", errors="replace")
    passed = total = 0
    matches = re.findall(r"([0-9]+)% tests passed(?:, ([0-9]+) tests failed)? out of ([0-9]+)", log)
    if matches:
        percent, failed, total = matches[-1]
        total = int(total)
        failed = int(failed) if failed else 0
        passed = total - failed
    if not total:
        raise SystemExit("ctest log has no summary line: %s" % args.ctest_log)
    def case_record(summary, name):
        case = summary["cases"][name]
        record = {"passed": case["passed"], "statuses": case["statuses"],
                  "stages": case["stages"], "errors": case["errors"],
                  "book_sha256": case["book_sha256"], "book": case["book"],
                  "runs": case["runs"]}
        if case.get("enumerated"):
            record["enumerated"] = case["enumerated"]
        if case.get("medians"):
            record["medians"] = case["medians"]
            record["turn_layout_ms"] = case.get("turn_layout_ms")
            record["turn_render_ms"] = case.get("turn_render_ms")
            record["page_hashes"] = case.get("page_hashes")
            record["page_ranges"] = case.get("page_ranges")
        return record
    equivalence = {"page_counts": {}, "all_equal": True}
    for name in ("single10", "segmented10", "segmented50", "segmented100"):
        left = baseline["cases"].get(name, {}).get("enumerated")
        right = candidate["cases"].get(name, {}).get("enumerated")
        if not left or not right:
            equivalence["page_counts"][name] = {"baseline": None, "candidate": None}
            equivalence["all_equal"] = False
            continue
        same = (left["pages"] == right["pages"] and left["hashes"] == right["hashes"] and
                left["ranges"] == right["ranges"])
        equivalence["page_counts"][name] = {
            "baseline_pages": left["pages"], "candidate_pages": right["pages"],
            "hashes_compared": min(len(left["hashes"]), len(right["hashes"])),
            "equal": same,
        }
        equivalence["all_equal"] = equivalence["all_equal"] and same
    cases = {}
    for name in ("single10", "segmented10", "single50", "segmented50", "single100", "segmented100"):
        cases[name] = {"baseline": case_record(baseline, name),
                       "candidate": case_record(candidate, name)}
    single10 = median_case(candidate, "single10", "document_owned_bytes")
    single100 = median_case(candidate, "single100", "document_owned_bytes")
    record = {
        "schema": 1,
        "date": "2026-10-20",
        "package": "B",
        "work_package": "WP6 bounded in-chapter parsing",
        "branch": "codex/wp6-bounded-chapters",
        "engine_source_sha": args.source_sha,
        "record_policy": "The evidence record is committed after the engine commit it validates; package_source_sha is reported in the package handoff.",
        "base_source_sha": args.base_sha,
        "sdk_version": "3.39.0",
        "abi": 1,
        "library_schema": 6,
        "public_signatures_changed": False,
        "public_snapshot_lifetime_changed": False,
        "protected_untracked_files": protected,
        "scope": "Dependency/ownership design, fixed 10/50/100 MiB corpus, separated parse-workspace metering, exact-size retention fix and regression; windowed DOM not implemented",
        "corpus": {
            "manifest": artifact(args.corpus / "manifest.json"),
            "generator_sha256": corpus["generator_sha256"],
            "mib": corpus["mib"],
            "segment_bytes": corpus["segment_bytes"],
            "cases": [{key: case[key] for key in ("name", "shape", "chapter_count", "body_bytes",
                                                  "file_bytes", "sha256", "block_count",
                                                  "block_kinds")} for case in corpus["cases"]],
        },
        "probe": {
            "source": artifact(Path(__file__).absolute().parent / "wp6_chapter_probe.c"),
            "runner": artifact(Path(__file__).absolute().parent / "run_wp6_bounded_probe.py"),
            "generator": artifact(Path(__file__).absolute().parent / "generate_bounded_chapter_corpus.py"),
            "metric": "document_owned_bytes is the deterministic parse workspace; working set and high-water mark are reported separately",
            "hash": "FNV-1a 64 over page ranges, line/glyph/box fields, positions quantized to 0.01 px",
            "random_plan": candidate["random_plan"],
            "plan": {"turns": 16, "cache_pages": 1, "cache_bytes": 2 * MIB,
                     "checkpoints": 4, "checkpoint_bytes": 2 * MIB, "checkpoint_interval": 8,
                     "seed": 20261020},
        },
        "measurements": {
            "baseline_summary": artifact(args.baseline),
            "candidate_summary": artifact(args.candidate),
            "baseline_probe_sha256": baseline["probe_sha256"],
            "candidate_probe_sha256": candidate["probe_sha256"],
            "font_sha256": candidate["font_sha256"],
            "cases": cases,
            "single_10_to_100_residency": {
                "single10_owned_bytes": single10,
                "single100_owned_bytes": single100,
                "increment_bytes": (single100 - single10) if (single10 and single100) else None,
                "limit_bytes": 32 * MIB,
                "met": False,
                "reason": "single-100MiB is rejected with EXR_LIMIT before a document exists",
            },
        },
        "retention_fix": {
            "file": "src/document.c",
            "function": "model_shrink",
            "invariant": "a finished document keeps exact-size text/node/block/chapter/resource arrays",
            "single10_owned_bytes": {"baseline": median_case(baseline, "single10", "document_owned_bytes"),
                                     "candidate": single10},
            "page_hashes_equal": cases["single10"]["baseline"].get("page_hashes") ==
                                 cases["single10"]["candidate"].get("page_hashes"),
            "regression_test": "tests/test_budget.c retained_workspace",
            "negative_check": "the test fails at the <= payload + 4096 bound when shrinking is disabled",
        },
        "equivalence": equivalence,
        "engine": {
            "candidate_dll": artifact(args.candidate_dll),
            "baseline_dll": artifact(args.baseline_dll),
            "compiler": args.compiler,
            "candidate_probe_sha256": candidate["probe_sha256"],
            "baseline_probe_sha256": baseline["probe_sha256"],
        },
        "regression": {
            "ctest": {"passed": passed, "total": total, "log": artifact(args.ctest_log)},
            "configuration": {"generator": "Ninja", "compiler": "MinGW-w64 GCC (WinLibs POSIX UCRT)",
                              "build_type": "Release", "webp": False, "tiff": False, "avif": False,
                              "fuzz": False},
        },
        "acceptance": {
            "residency_increment_le_32MiB": False,
            "single_50_100_open": False,
            "first_screen_and_turns_measured": True,
            "sequential_and_fixed_random_quantified": True,
            "page_ranges_and_hashes_match_stable_path": cases["single10"]["baseline"].get("page_hashes") ==
                                                         cases["single10"]["candidate"].get("page_hashes"),
            "checkpoint_restore_after_eviction": any(
                (case["candidate"].get("medians") or {}).get("restored_checkpoints", 0) for
                case in cases.values()),
            "css_paragraph_bidi_table_float_ruby_survive_windows": False,
            "linux_asan_ubsan": False,
            "installed_consumer": False,
            "wp7_wp8_wp12_regressions": False,
        },
        "unmet": [
            "Window/segment index and windowed DOM are designed but not implemented",
            "50/100 MiB single chapters still return EXR_LIMIT at the 32 MiB member limit",
            "10->100 MiB parse-residency increment cannot be measured until 100 MiB opens",
            "Checkpoint/random restore across window eviction is not implemented",
            "Cross-window CSS inheritance and CFI/selection/export continuity are not implemented",
        ],
    }
    if args.verification:
        verification = dict(load(args.verification))
        extra_acceptance = verification.pop("acceptance", {}) or {}
        extra_unmet = verification.pop("unmet", []) or []
        record.update(verification)
        record["acceptance"].update(extra_acceptance)
        for item in extra_unmet:
            if item not in record["unmet"]:
                record["unmet"].append(item)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ctest_passed": passed, "ctest_total": total,
                      "single10_owned": single10, "single100_owned": single100}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())