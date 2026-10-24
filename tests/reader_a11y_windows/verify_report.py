#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict validator for the Windows accessibility audit evidence.

Recomputes the verdict from the raw records instead of trusting the report:
counts, named statuses, scope coverage, artifact digests, UIA tree contents and
the key trace must all agree, and audit_completed/accessibility_accepted are
re-derived from the checks. A generated report never turns into acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCOPES = {"shelf", "import", "organize", "reading", "annotation", "settings", "keyboard"}
STATUSES = {"pass", "fail", "gap", "not_verified", "error"}
SEVERITIES = {"blocking", "serious", "moderate", "info"}
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TREES = {"t00-launch-empty", "t01-shelf-loaded", "t02-reading", "t03-details-dialog"}
REQUIRED_TREE_CONTROLS = {119: "ListBox", 101: "Edit", 123: "EXReaderPage", 121: "ListBox"}
REQUIRED_DIALOG_CONTROLS = {129: "Edit", 130: "Edit", 132: "Button", 133: "Button"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def flatten(tree, depth=0):
    """Yield every element record of a dumped UIA tree."""
    if not isinstance(tree, dict):
        return
    yield tree
    for child in tree.get("children") or []:
        yield from flatten(child, depth + 1)


def control_ids(tree):
    ids = {}
    for node in flatten(tree.get("tree")):
        if not isinstance(node, dict):
            continue
        hwnd = node.get("native_hwnd") or 0
        if hwnd:
            ids[hwnd] = node.get("class_name") or ""
    return ids


def class_of(tree, wanted):
    """Find the class name of the element whose native handle matches wanted."""
    for node in flatten(tree.get("tree")):
        if not isinstance(node, dict):
            continue
        if int(node.get("native_hwnd") or 0) == wanted:
            return node
    return None


def check_tree_names(output, problems):
    base = Path(output) / "uia"
    present = {path.stem for path in base.glob("*.json")} if base.is_dir() else set()
    missing = sorted(REQUIRED_TREES - present)
    if missing:
        problems.append("missing UIA tree dumps: %s" % ", ".join(missing))
        return {}
    summary = {}
    for name in sorted(REQUIRED_TREES):
        payload = json.loads((base / (name + ".json")).read_text(encoding="utf-8"))
        tree = payload.get("tree")
        if not isinstance(tree, dict) or not payload.get("uia_available"):
            problems.append("%s: no usable UIA tree" % name)
            continue
        nodes = [node for node in flatten(tree) if isinstance(node, dict)]
        summary[name] = {"elements": len(nodes)}
        if len(nodes) < 8:
            problems.append("%s: only %d elements in the tree" % (name, len(nodes)))
        controls = payload.get("control_ids") or {}
        tree_handles = {int(node.get("native_hwnd") or 0) for node in nodes}
        wanted = REQUIRED_DIALOG_CONTROLS if name == "t03-details-dialog" \
            else REQUIRED_TREE_CONTROLS
        for identifier, expected in sorted(wanted.items()):
            handle = controls.get(str(identifier))
            if not handle:
                problems.append("%s: control id %d was not part of the dump"
                                % (name, identifier))
                continue
            if int(handle, 16) not in tree_handles:
                problems.append("%s: control id %d (%s) is missing from the UIA tree"
                                % (name, identifier, expected))
        classes = {(node.get("class_name") or "") for node in nodes}
        for expected in ("ListBox", "Edit"):
            if expected not in classes:
                problems.append("%s: no %s element in the UIA tree" % (name, expected))
    return summary


def check_key_trace(output, problems):
    path = Path(output) / "key-trace.jsonl"
    if not path.is_file():
        problems.append("missing key trace")
        return {}
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            problems.append("key trace has a line that is not JSON")
            return {}
    keys = [event for event in events if event.get("kind") == "key"]
    tabs = [event for event in keys if (event.get("payload") or {}).get("key") == "tab"]
    transports = {(event.get("payload") or {}).get("transport") for event in keys}
    if len(keys) < 40:
        problems.append("key trace records only %d key events" % len(keys))
    if len(tabs) < 20:
        problems.append("key trace records only %d Tab presses" % len(tabs))
    if not transports or None in transports:
        problems.append("key trace has key events without a recorded transport")
    if not keys or any(not (event.get("payload") or {}).get("delivered") for event in keys):
        problems.append("key trace contains undelivered key events")
    return {"events": len(events), "keys": len(keys), "tabs": len(tabs),
            "transports": sorted(str(item) for item in transports)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-source", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--expect-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--expect-attempt", type=int,
                        default=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0") or 0))
    parser.add_argument("--min-checks", type=int, default=40)
    args = parser.parse_args()

    problems = []
    report = json.loads(args.report.read_text(encoding="utf-8"))
    evidence_root = args.report.parent

    if report.get("schema") != 1 or report.get("kind") != "reader-a11y-windows-audit":
        problems.append("unexpected report kind/schema")

    source = report.get("source_sha") or ""
    if not SHA1.match(source):
        problems.append("source_sha is not a 40 character commit hash")
    if args.expect_source and source != args.expect_source:
        problems.append("report source %s is not the checked out source %s"
                        % (source, args.expect_source))
    if args.expect_run_id and str(report.get("run_id")) != str(args.expect_run_id):
        problems.append("report run_id %r is not the current run %r"
                        % (report.get("run_id"), args.expect_run_id))
    if args.expect_attempt and int(report.get("attempt") or 0) != args.expect_attempt:
        problems.append("report attempt %r is not the current attempt %r"
                        % (report.get("attempt"), args.expect_attempt))

    checks = report.get("checks") or []
    seen = set()
    scope_hits = {scope: 0 for scope in SCOPES}
    recomputed = {status: 0 for status in STATUSES}
    blocking = []
    errors = []
    for check in checks:
        identifier = check.get("id")
        if not identifier or identifier in seen:
            problems.append("duplicate or missing check id %r" % (identifier,))
            continue
        seen.add(identifier)
        status = check.get("status")
        severity = check.get("severity")
        if status not in STATUSES:
            problems.append("%s has status %r" % (identifier, status))
            continue
        if severity not in SEVERITIES:
            problems.append("%s has severity %r" % (identifier, severity))
        if check.get("scope") not in SCOPES:
            problems.append("%s has scope %r" % (identifier, check.get("scope")))
        else:
            scope_hits[check["scope"]] += 1
        for key in ("expected", "actual", "title"):
            if not str(check.get(key) or "").strip():
                problems.append("%s has an empty %s" % (identifier, key))
        if not isinstance(check.get("steps"), list) or not check["steps"]:
            problems.append("%s lists no reproduction steps" % identifier)
        recomputed[status] += 1
        if status == "error":
            errors.append(identifier)
        if severity == "blocking" and status in ("fail", "gap", "error"):
            blocking.append(identifier)
        if status == "not_verified" and not str(check.get("reason") or "").strip():
            problems.append("%s is not_verified without a reason" % identifier)

    if len(checks) < args.min_checks:
        problems.append("report has %d checks, fewer than the required %d"
                        % (len(checks), args.min_checks))
    for scope, count in sorted(scope_hits.items()):
        if count == 0:
            problems.append("no check covers the %s flow" % scope)

    counts = report.get("counts") or {}
    if int(counts.get("checks") or -1) != len(checks):
        problems.append("counts.checks %r does not match %d named checks"
                        % (counts.get("checks"), len(checks)))
    for status, value in recomputed.items():
        if int(counts.get(status) or 0) != value:
            problems.append("counts.%s %r does not match %d" % (status, counts.get(status), value))
    if int(counts.get("blocking") or -1) != len(blocking):
        problems.append("counts.blocking %r does not match %d"
                        % (counts.get("blocking"), len(blocking)))
    if sorted(report.get("blocking") or []) != sorted(blocking):
        problems.append("report blocking list does not match the recomputed blocking checks")

    audit_completed = report.get("audit_completed") is True and not errors
    if report.get("audit_completed") is True and errors:
        problems.append("report claims audit_completed while %d checks errored" % len(errors))
    accepted = audit_completed and not blocking
    if report.get("accessibility_accepted") is not accepted:
        problems.append("accessibility_accepted %r disagrees with the recomputed verdict %r"
                        % (report.get("accessibility_accepted"), accepted))
    if report.get("screen_reader_verified") is not False:
        problems.append("automated evidence cannot set screen_reader_verified")
    if not report.get("human_review_required"):
        problems.append("report does not list the human screen-reader review")

    environment = report.get("environment") or {}
    if not SHA256.match(str(environment.get("executable_sha256") or "")):
        problems.append("no audited executable digest")
    transport = (environment.get("keyboard") or {}).get("transport")
    if transport not in ("sendinput", "postmessage"):
        problems.append("no recorded keyboard transport")

    artifacts = report.get("artifacts") or []
    if len(artifacts) < 6:
        problems.append("report lists only %d artifacts" % len(artifacts))
    kinds = {"screenshots": 0, "uia": 0, "crops": 0, "trace": 0}
    for item in artifacts:
        relative = item.get("path") or ""
        path = evidence_root / relative
        if not path.is_file():
            problems.append("artifact %r is missing" % relative)
            continue
        if int(item.get("bytes") or 0) <= 0 or path.stat().st_size <= 0:
            problems.append("artifact %r is empty" % relative)
        if digest(path) != item.get("sha256"):
            problems.append("artifact %r digest does not match" % relative)
        if relative.startswith("screenshots"):
            kinds["screenshots"] += 1
        elif relative.startswith("uia"):
            kinds["uia"] += 1
        elif relative.startswith("focus-crops"):
            kinds["crops"] += 1
        elif relative.endswith(".jsonl"):
            kinds["trace"] += 1
    if kinds["screenshots"] < 4:
        problems.append("fewer than four screenshots")
    if kinds["uia"] < 4:
        problems.append("fewer than four UIA tree dumps")
    if kinds["crops"] < 2:
        problems.append("no focus-indicator capture pair")
    if kinds["trace"] < 1:
        problems.append("no key trace artifact")

    check_tree_names(evidence_root, problems)
    trace_summary = check_key_trace(evidence_root, problems)

    verdict = {
        "schema": 1,
        "kind": "reader-a11y-windows-verification",
        "source_sha": source,
        "run_id": str(report.get("run_id")),
        "attempt": report.get("attempt"),
        "validated_report_sha256": digest(args.report),
        "checks": len(checks),
        "named_statuses": recomputed,
        "blocking": blocking,
        "errors": errors,
        "audit_completed": audit_completed,
        "accessibility_accepted": accepted,
        "screen_reader_verified": False,
        "key_trace": trace_summary,
        "environment": {"keyboard_transport": transport,
                        "executable_sha256": environment.get("executable_sha256"),
                        "screen": environment.get("screen")},
        "problems": problems,
        "accepted": not problems and audit_completed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"accepted": verdict["accepted"],
                      "audit_completed": audit_completed,
                      "accessibility_accepted": accepted,
                      "checks": len(checks),
                      "blocking": blocking,
                      "problems": problems}, ensure_ascii=False, indent=2))
    return 0 if verdict["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
