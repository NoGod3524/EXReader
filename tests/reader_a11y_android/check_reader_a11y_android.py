#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Acceptance checker for the Android accessibility audit evidence.

Runs on GitHub Actions only. It re-derives every verdict from the retained device
evidence instead of trusting the report, and it keeps two decisions apart:

    audit_completed        every expected case ran and every required artefact exists
    accessibility_accepted every case passed on this exact source/run/attempt

The checker refuses a report that claims acceptance while a case failed, a case was
skipped, the case list shrank, or a screenshot/hierarchy/source identity disagrees.
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

EXPECTED_CASES = [
    "shelf_semantics",
    "hidden_panels",
    "status_announcement",
    "import_picker",
    "shelf_row_and_search",
    "organize_panel",
    "back_navigation",
    "reader_line_nodes",
    "reader_page_turn",
    "reader_toolbar_state",
    "annotate_flow",
    "notes_panel",
    "rotation",
    "large_font",
    "display_scaling",
]

REQUIRED_CAPTURES = [
    "01-shelf-default",
    "02-shelf-hidden",
    "03-shelf-status",
    "04-system-picker",
    "05-shelf-imported",
    "06-shelf-row",
    "07-shelf-search-empty",
    "08-organize",
    "09-back-organize",
    "10-reader",
    "11-back-reader",
    "12-reader-lines",
    "13-reader-actions",
    "15-reader-toolbar",
    "16-reader-select-mode",
    "17-reader-selected",
    "20-notes-panel",
    "22-reader-portrait",
    "23-reader-landscape",
    "24-shelf-font200",
    "25-reader-font200",
    "26-shelf-density480",
]

OPTIONAL_CAPTURES = ["14-reader-turned", "18-annotate-dialog", "19-annotate-saved", "21-notes-back"]

PICKER_PACKAGE = "com.android.documentsui"
APP_PACKAGE = "org.exreader.host"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_SCREENSHOT_BYTES = 20000


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root, source, run_id, attempt):
    problems = []

    def need(path, label):
        if not path.is_file():
            problems.append("missing_evidence:" + label)
            return False
        return True

    if not root.is_dir():
        problems.append("missing_evidence:root")
        return problems
    dev = root / "device"

    files = {
        "source": (root / "source.txt", "source.txt"),
        "run": (root / "run-id.txt", "run-id.txt"),
        "attempt": (root / "attempt.txt", "attempt.txt"),
        "api": (root / "device-api.txt", "device-api.txt"),
        "abi": (root / "device-abi.txt", "device-abi.txt"),
        "installed": (root / "installed-host-apk.txt", "installed-host-apk.txt"),
        "harness": (root / "harness-apks.json", "harness-apks.json"),
        "instrumentation": (root / "instrumentation.txt", "instrumentation.txt"),
        "exit": (root / "audit-exit.txt", "audit-exit.txt"),
        "validation": (dev / "validation.json", "device/validation.json"),
        "build": (root / "host-build.json", "host-build.json"),
    }
    present = {}
    for key, (path, label) in files.items():
        present[key] = need(path, label)
    if problems:
        return problems

    if (root / "source.txt").read_text(encoding="utf-8").strip() != source:
        problems.append("source_mismatch:source.txt")
    if (root / "run-id.txt").read_text(encoding="utf-8").strip() != str(run_id):
        problems.append("run_mismatch:run-id.txt")
    if (root / "attempt.txt").read_text(encoding="utf-8").strip() != str(attempt):
        problems.append("run_mismatch:attempt.txt")
    if (root / "device-api.txt").read_text(encoding="utf-8").strip() != "34":
        problems.append("api_mismatch")
    if (root / "device-abi.txt").read_text(encoding="utf-8").strip() != "x86_64":
        problems.append("abi_mismatch")

    # The installed APK must be the byte-identical host build, not a rebuilt or
    # re-signed copy made for the audit.
    build = read_json(root / "host-build.json")
    if build.get("source_sha") != source:
        problems.append("source_mismatch:host-build.json")
    built = build.get("artifacts", {}).get("app-debug.apk", {})
    installed = (root / "installed-host-apk.txt").read_text(encoding="utf-8").split()
    if not installed:
        problems.append("installed_identity:empty")
    else:
        if installed[0].strip().lower() != str(built.get("sha256", "")).lower():
            problems.append("installed_identity:sha256")
        if len(installed) > 1 and str(built.get("size", "")) != installed[1].strip():
            problems.append("installed_identity:size")
    if int(built.get("size", 0)) <= 0:
        problems.append("installed_identity:build_size")
    if (root / "audit-exit.txt").read_text(encoding="utf-8").strip() != "0":
        problems.append("instrumentation_failed:exit")

    harness = read_json(root / "harness-apks.json")
    for name, record in harness.items():
        path = root / record.get("file", "")
        if not path.is_file():
            problems.append("harness_identity:missing:" + name)
            continue
        if path.stat().st_size != record.get("size"):
            problems.append("harness_identity:size:" + name)
        if sha256(path) != record.get("sha256"):
            problems.append("harness_identity:sha256:" + name)

    text = (root / "instrumentation.txt").read_text(encoding="utf-8", errors="replace")
    if "INSTRUMENTATION_FAILED" in text or "FAILURES!!!" in text:
        problems.append("instrumentation_failed")

    validation = read_json(dev / "validation.json")
    if validation.get("source_sha") != source:
        problems.append("source_mismatch:device")
    if str(validation.get("run_id")) != str(run_id):
        problems.append("run_mismatch:device")
    if str(validation.get("attempt")) != str(attempt):
        problems.append("run_mismatch:device")
    if int(validation.get("sdk", 0)) != 34:
        problems.append("api_mismatch:device")

    cases = validation.get("cases") or []
    ids = [case.get("id") for case in cases]
    if ids != EXPECTED_CASES:
        problems.append("case_set")
    if int(validation.get("skipped", 0)) != 0 or validation.get("skipped") is None:
        problems.append("skipped_cases")
    if int(validation.get("case_count", 0)) != len(EXPECTED_CASES):
        problems.append("case_set:count")

    failed = 0
    for case in cases:
        verdict = case.get("verdict")
        if verdict not in ("pass", "fail"):
            problems.append("case_verdict:" + str(case.get("id")))
            continue
        if verdict == "fail":
            failed += 1
            if not case.get("finding") and not case.get("error"):
                problems.append("case_finding:" + str(case.get("id")))
            if not case.get("patch") and not case.get("error"):
                problems.append("case_finding:" + str(case.get("id")) + ":patch")
        if verdict == "pass" and case.get("finding"):
            problems.append("case_verdict:" + str(case.get("id")) + ":pass_with_finding")
        if not case.get("captures"):
            problems.append("case_captures:" + str(case.get("id")))

    complete = len(ids) == len(EXPECTED_CASES) and len(set(ids)) == len(ids)
    claimed_complete = bool(validation.get("audit_completed"))
    claimed_accepted = bool(validation.get("accessibility_accepted"))
    if claimed_complete != complete:
        problems.append("acceptance_mismatch:audit_completed")
    if claimed_accepted and (not complete or failed):
        problems.append("acceptance_mismatch:accessibility_accepted")
    if int(validation.get("failed", -1)) != failed:
        problems.append("acceptance_mismatch:failed_count")
    if int(validation.get("passed", -1)) != len(cases) - failed:
        problems.append("acceptance_mismatch:passed_count")

    coverage = validation.get("coverage") or {}
    if not coverage.get("account") or coverage["account"].get("implemented") is not False:
        problems.append("coverage:account")
    for surface in ("shelf", "import", "organize", "read", "annotate"):
        entry = coverage.get(surface) or {}
        if entry.get("implemented") is not True or not entry.get("cases"):
            problems.append("coverage:" + surface)
    unverified = validation.get("unverified") or []
    if len(unverified) < 5:
        problems.append("coverage:unverified")
    for entry in unverified:
        if entry.get("status") != "unverified":
            problems.append("coverage:unverified_status")

    declared = set(validation.get("captures") or [])
    for name in REQUIRED_CAPTURES:
        if name not in declared:
            problems.append("missing_capture:" + name)
    for name in sorted(declared):
        if name not in REQUIRED_CAPTURES and name not in OPTIONAL_CAPTURES:
            problems.append("unexpected_capture:" + name)
        tree_path = dev / "trees" / (name + ".json")
        xml_path = dev / "trees" / (name + ".xml")
        shot_path = dev / "shots" / (name + ".png")
        if not tree_path.is_file():
            problems.append("missing_tree:" + name)
            continue
        try:
            tree = read_json(tree_path)
        except Exception:
            problems.append("tree_parse:" + name)
            continue
        if not xml_path.is_file():
            problems.append("missing_xml:" + name)
        else:
            raw = xml_path.read_bytes()
            if len(raw) < 200:
                problems.append("empty_xml:" + name)
            if not shot_path.is_file():
                problems.append("missing_screenshot:" + name)
            else:
                png = shot_path.read_bytes()
                if not png.startswith(PNG_SIGNATURE):
                    problems.append("screenshot_bytes:" + name)
                if len(png) < MIN_SCREENSHOT_BYTES:
                    problems.append("screenshot_bytes:" + name)
                if int(tree.get("screenshot_bytes", -1)) != len(png):
                    problems.append("screenshot_bytes:" + name)
            if int(tree.get("xml_bytes", -1)) != len(raw):
                problems.append("empty_xml:" + name + ":bytes")
            expected = PICKER_PACKAGE if name == "04-system-picker" else APP_PACKAGE
            if 'package="' + expected + '"' not in raw.decode("utf-8", errors="replace"):
                problems.append("xml_package:" + name)
        if tree.get("root_package") != (PICKER_PACKAGE if name == "04-system-picker" else APP_PACKAGE):
            problems.append("root_package:" + name)
        if int(tree.get("display_width", 0)) <= 0 or int(tree.get("display_height", 0)) <= 0:
            problems.append("root_package:" + name + ":display")
        interactive = tree.get("interactive")
        if not isinstance(interactive, list):
            problems.append("tree_parse:" + name + ":interactive")

    return problems


def summarise(root, problems):
    dev = root / "device"
    validation = read_json(dev / "validation.json")
    cases = validation.get("cases") or []
    return {
        "kind": "reader-a11y-android-check",
        "problems": problems,
        "refused": bool(problems),
        "audit_completed": bool(validation.get("audit_completed")) and not problems,
        "accessibility_accepted": bool(validation.get("accessibility_accepted")) and not problems,
        "case_count": len(cases),
        "failed_cases": [case.get("id") for case in cases if case.get("verdict") != "pass"],
        "passed_cases": [case.get("id") for case in cases if case.get("verdict") == "pass"],
        "findings": {case.get("id"): case.get("finding") for case in cases if case.get("finding")},
        "captures": validation.get("captures") or [],
        "unverified": [entry.get("item") for entry in (validation.get("unverified") or [])],
    }


CORRUPTIONS = [
    ("missing_screenshot", lambda dev, root, value: (dev / "shots" / "01-shelf-default.png").unlink()),
    ("empty_xml", lambda dev, root, value: (dev / "trees" / "06-shelf-row.xml").write_bytes(b"<")),
    ("source_mismatch", lambda dev, root, value: value.__setitem__("source_sha", "0" * 40)),
    ("acceptance_mismatch", lambda dev, root, value: value.__setitem__("audit_completed", False)),
    ("case_set", lambda dev, root, value: value.__setitem__("cases", value["cases"][:-1])),
    ("skipped_cases", lambda dev, root, value: value.__setitem__("skipped", 2)),
    ("screenshot_bytes", lambda dev, root, value: (dev / "shots" / "10-reader.png").write_bytes(b"x" * 4096)),
    ("installed_identity", lambda dev, root, value: (root / "installed-host-apk.txt").write_text("0" * 64 + " " + "1", encoding="utf-8")),
]


def corruption_suite(root, source, run_id, attempt):
    results = []
    sandbox = root / "corruption"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    for name, mutate in CORRUPTIONS:
        target = sandbox / name
        shutil.copytree(root, target, ignore=shutil.ignore_patterns("corruption"))
        validation_path = target / "device" / "validation.json"
        value = read_json(validation_path)
        try:
            mutate(target / "device", target, value)
        except Exception as error:
            results.append({"corruption": name, "refused": False, "detail": "mutation failed: " + str(error)})
            continue
        validation_path.write_text(json.dumps(value, indent=2), encoding="utf-8")
        observed = validate(target, source, run_id, attempt)
        results.append({"corruption": name, "refused": bool(observed), "observed": observed[:8]})
    shutil.rmtree(sandbox, ignore_errors=True)
    return results


def main():
    parser = argparse.ArgumentParser(description="Android accessibility audit acceptance checker")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--run", default="")
    parser.add_argument("--attempt", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--corruption-suite", action="store_true")
    args = parser.parse_args()

    root = args.evidence.absolute()

    def identity(given, name):
        if given:
            return given
        path = root / name
        return path.read_text(encoding="utf-8").strip() if path.is_file() else ""

    source = identity(args.source, "source.txt")
    run_id = identity(args.run, "run-id.txt")
    attempt = identity(args.attempt, "attempt.txt")
    if not (root / "device" / "validation.json").is_file():
        print(json.dumps({"kind": "reader-a11y-android-check", "refused": True,
                          "problems": ["missing_evidence:device/validation.json"]}, indent=2))
        return 1

    problems = validate(root, source, run_id, attempt)
    summary = summarise(root, problems)
    summary["source_sha"] = source
    summary["run_id"] = run_id
    summary["attempt"] = attempt

    exit_code = 1 if problems else 0
    if args.corruption_suite:
        results = corruption_suite(root, source, run_id, attempt)
        summary["corruption_suite"] = results
        for result in results:
            if not result.get("refused"):
                exit_code = 1
        summary["corruption_suite_passed"] = all(result.get("refused") for result in results)

    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
